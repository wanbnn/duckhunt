import os
import sys
import json
import asyncio
import contextlib
import re
from urllib.parse import urlparse, parse_qs

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

# Importa módulos internos e configurações do app original
from app import (
    UnifiedLLM, 
    autoload_model, 
    autoload_agent, 
    autoload_skills, 
    compor_prompt_sistema,
    SYSTEM_PROMPT,
    MCP_CONFIG_PATH,
    status_bar,
    notify_error,
    console
)

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Variáveis globais de estado
_llm = None
_mcp_stack = None
_mcp_sessions = {}
_mcp_tools = {}
_llama_tools = []
_system_prompt = ""

# Configuração do FastAPI
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    global _llm, _mcp_stack, _mcp_sessions, _mcp_tools, _llama_tools, _system_prompt
    
    # 1. Carrega o Modelo (deve estar configurado no config.ini ou via CLI previamente)
    print("Iniciando DuckHunt API...")
    _llm = await autoload_model()
    if getattr(app.state, "duckhunt_test", False):
        yield
        return

    if not _llm:
        print("AVISO: Nenhum modelo configurado. Configure um modelo no app principal (app.py) primeiro.")
    else:
        print(f"Modelo carregado: {_llm.model_name}")

    # 2. Configura Prompts e Skills
    saved_agent = autoload_agent()
    agent_prompt_text = saved_agent if saved_agent else SYSTEM_PROMPT
    skills_prompts = autoload_skills()
    _system_prompt = compor_prompt_sistema(agent_prompt_text, skills_prompts)

    # 3. Conecta aos servidores MCP
    _mcp_stack = contextlib.AsyncExitStack()
    try:
        if os.path.exists(MCP_CONFIG_PATH):
            with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                mcp_config = json.load(f)
            
            for srv_name, srv_cfg in mcp_config.get("mcpServers", {}).items():
                if srv_cfg.get("disabled", False): continue
                
                typ = srv_cfg.get("type", "stdio")
                if "command" in srv_cfg and "type" not in srv_cfg: typ = "stdio"
                
                if typ == "stdio":
                    cmd = srv_cfg.get("command", "python")
                    if cmd in ("python", "python.exe", "python3"): cmd = sys.executable
                    env = {**os.environ, **srv_cfg.get("env", {})}
                    params = StdioServerParameters(command=cmd, args=srv_cfg.get("args", []), env=env)
                    read, write = await _mcp_stack.enter_async_context(stdio_client(params))
                else:
                    try:
                        from mcp.client.sse import sse_client
                        read, write = await _mcp_stack.enter_async_context(sse_client(srv_cfg.get("url")))
                    except ImportError:
                        continue
                
                session = await _mcp_stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                _mcp_sessions[srv_name] = session
                
                tools_resp = await session.list_tools()
                for t in tools_resp.tools:
                    _mcp_tools[t.name] = srv_name
                    _llama_tools.append({
                        "type": "function",
                        "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema}
                    })
            print(f"Servidores MCP conectados. {len(_llama_tools)} ferramentas disponíveis.")
    except Exception as e:
        print(f"Erro ao inicializar MCP: {e}")

    yield

    # Cleanup
    if _mcp_stack:
        await _mcp_stack.aclose()
        print("Recursos liberados.")

api_app = FastAPI(
    title="DuckHunt API", 
    description="API compatível com OpenAI para integração de projetos ao DuckHunt.",
    lifespan=lifespan
)

class ChatRequest(BaseModel):
    model: str = "default"
    messages: list
    stream: bool = False
    max_tokens: int = 2048
    temperature: float = 0.3

async def run_agent_loop(messages: list, stream: bool, max_tokens: int, temperature: float):
    # Clona as mensagens para não alterar o histórico original do client
    local_messages = [{"role": "system", "content": _system_prompt}] + messages
    
    # Loop de raciocínio (Agent Loop)
    while True:
        # Gera a resposta via motor unificado
        response_gen = _llm.create_chat_completion(
            messages=local_messages,
            tools=_llama_tools if _llama_tools else None,
            tool_choice="auto" if _llama_tools else None,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=False # Sempre geramos blocos inteiros para processar ferramentas, a menos que seja o bloco final
        )
        
        # Pega a resposta completa gerada
        chunk = next(response_gen)
        delta = chunk["choices"][0].get("delta", {})
        
        message_content = delta.get("content", "") or ""
        tool_calls = delta.get("tool_calls", [])
        
        # Faz parsing manual caso seja necessário (llama.cpp)
        if not tool_calls and "<tool_call>" in message_content:
            matches = re.findall(r'<tool_call>(.*?)</tool_call>', message_content, re.DOTALL | re.IGNORECASE)
            for i, match in enumerate(matches):
                clean_match = match.strip()
                if clean_match.startswith('```json'): clean_match = clean_match[7:]
                elif clean_match.startswith('```'): clean_match = clean_match[3:]
                if clean_match.endswith('```'): clean_match = clean_match[:-3]
                try:
                    tool_data = json.loads(clean_match.strip())
                    if "name" in tool_data and "arguments" in tool_data:
                        tool_calls.append({
                            "id": f"call_manual_{i}",
                            "type": "function",
                            "function": {"name": tool_data["name"], "arguments": json.dumps(tool_data["arguments"])}
                        })
                except json.JSONDecodeError:
                    pass

        # Adiciona a resposta do assistente ao histórico local
        assistant_msg = {"role": "assistant", "content": message_content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        local_messages.append(assistant_msg)
        
        # Se não há tool calls, o agente terminou a resposta
        if not tool_calls:
            return assistant_msg

        # Executa as ferramentas interceptadas
        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_args = json.loads(tool_call["function"]["arguments"])
            
            tool_result_text = ""
            try:
                target_srv = _mcp_tools.get(tool_name)
                if not target_srv or target_srv not in _mcp_sessions:
                    tool_result_text = f"Erro: Servidor MCP para a ferramenta '{tool_name}' não encontrado."
                else:
                    sess = _mcp_sessions[target_srv]
                    result = await sess.call_tool(tool_name, tool_args)
                    tool_result_text = "\n".join([c.text for c in result.content if c.type == "text"])
            except Exception as e:
                tool_result_text = f"Erro ao executar ferramenta: {str(e)}"
            
            # Adiciona o resultado da ferramenta ao histórico
            local_messages.append({
                "role": "tool",
                "name": tool_name,
                "content": tool_result_text,
                "tool_call_id": tool_call.get("id", "manual_call")
            })
        
        # Após adicionar os resultados das ferramentas, o loop continua para o LLM processar os resultados

@api_app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    if not _llm:
        raise HTTPException(status_code=500, detail="Nenhum modelo configurado no DuckHunt. Configure via app.py primeiro.")

    # Se streaming não for requisitado, roda o loop do agente e retorna
    if not request.stream:
        final_msg = await run_agent_loop(request.messages, stream=False, max_tokens=request.max_tokens, temperature=request.temperature)
        
        return {
            "id": "chatcmpl-duckhunt",
            "object": "chat.completion",
            "model": _llm.model_name,
            "choices": [{
                "index": 0,
                "message": final_msg,
                "finish_reason": "stop"
            }]
        }
    
    # Se streaming for requisitado, rodamos o agente normalmente. 
    # O DuckHunt faz o raciocínio em backgroud e depois "streama" o resultado final para manter a compatibilidade
    # de forma simples sem quebrar clientes OpenAI
    async def stream_generator():
        final_msg = await run_agent_loop(request.messages, stream=False, max_tokens=request.max_tokens, temperature=request.temperature)
        
        # Envia um chunk inicial vazio
        yield f"data: {json.dumps({'id': 'chatcmpl-duckhunt', 'object': 'chat.completion.chunk', 'model': _llm.model_name, 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': ''}}]})}\n\n"
        
        # Envia o conteúdo real char-by-char (ou word-by-word) para simular streaming
        content = final_msg.get("content", "")
        # Em uma implementação real, o stream viria do LLM. Aqui simplificamos por causa do Agent Loop.
        chunk_size = 10
        for i in range(0, len(content), chunk_size):
            text_chunk = content[i:i+chunk_size]
            payload = {
                "id": "chatcmpl-duckhunt",
                "object": "chat.completion.chunk",
                "model": _llm.model_name,
                "choices": [{"index": 0, "delta": {"content": text_chunk}}]
            }
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.01)
            
        yield f"data: {json.dumps({'id': 'chatcmpl-duckhunt', 'object': 'chat.completion.chunk', 'model': _llm.model_name, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    uvicorn.run("duckhunt_api:api_app", host="0.0.0.0", port=1686, reload=True)
