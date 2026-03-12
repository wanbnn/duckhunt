
import os
import json
import asyncio
import re
import time
import random
import configparser
import sys
from itertools import cycle
from urllib.parse import urlparse, parse_qs
import shutil
import hashlib

# Rich UI
from rich.console import Console, Group
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.text import Text
from rich.prompt import Prompt
from rich.status import Status
from rich.table import Table
from rich.align import Align
from rich.rule import Rule
from rich.style import Style
from rich.columns import Columns
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

# Arrow-key interactive menus
try:
    from InquirerPy import inquirer
    from InquirerPy.separator import Separator
    INQUIRER_AVAILABLE = True
except Exception as _inq_err:
    INQUIRER_AVAILABLE = False
    print(f"[WARN] InquirerPy indisponível ({_inq_err}). Instale com: pip install InquirerPy")

try:
    from llama_cpp import Llama
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    Llama = None
    LLAMA_CPP_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    anthropic = None
    ANTHROPIC_AVAILABLE = False

from openai import OpenAI, AzureOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

console = Console()

# ══════════════════════════════════════════════════════════════
#  DESIGN SYSTEM — Professional Dark-Mode Palette
# ══════════════════════════════════════════════════════════════

# Primary palette: cool slate + blue accents (enterprise aesthetic)
C_PRIMARY    = "#7AA2F7"   # Soft blue — primary actions
C_SECONDARY  = "#9D7CD8"   # Muted purple — secondary/agent
C_ACCENT     = "#73DACA"   # Teal — success/highlights
C_WARNING    = "#E0AF68"   # Warm amber — warnings
C_ERROR      = "#F7768E"   # Soft red — errors
C_DIM        = "#565F89"   # Slate gray — muted text
C_TEXT       = "#C0CAF5"   # Light blue-white — main text
C_SURFACE    = "#1A1B26"   # Dark background (reference)
C_BORDER     = "#3B4261"   # Panel borders
C_HIGHLIGHT  = "#BB9AF7"   # Highlight/selection
C_SUCCESS    = "#9ECE6A"   # Green — confirmations
C_TOOL       = "#FF9E64"   # Orange — tool execution

# Gradient for branding text (subtle cool tones)
GRADIENT_COLORS = [
    "#7AA2F7", "#7DCFFF", "#73DACA", "#9ECE6A",
    "#BB9AF7", "#9D7CD8", "#7AA2F7", "#7DCFFF",
]

# Loading animation frames (clean dots instead of duck spam)
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

DUCK_FRAMES = [
    "  🦆        ",
    "   🦆       ",
    "    🦆      ",
    "     🦆     ",
    "      🦆    ",
    "       🦆   ",
    "        🦆  ",
    "       🦆   ",
    "      🦆    ",
    "     🦆     ",
    "    🦆      ",
    "   🦆       ",
]

PROGRESS_BAR = ["░", "▒", "▓", "█"]

def gradient_text(text_str, colors=None):
    """Cria texto com efeito gradiente sutil."""
    if colors is None:
        colors = GRADIENT_COLORS
    t = Text()
    for i, char in enumerate(text_str):
        color = colors[i % len(colors)]
        t.append(char, style=Style(color=color, bold=True))
    return t

def notify_success(msg):
    console.print(
        Panel(
            Text.from_markup(f"[bold {C_SUCCESS}]✓ {msg}[/bold {C_SUCCESS}]"),
            border_style=C_ACCENT,
            padding=(0, 1),
            expand=False,
        )
    )

def notify_error(msg):
    console.print(
        Panel(
            Text.from_markup(f"[bold {C_ERROR}]✗ {msg}[/bold {C_ERROR}]"),
            border_style=C_ERROR,
            padding=(0, 1),
            expand=False,
        )
    )

def notify_info(msg):
    console.print(
        Panel(
            Text.from_markup(f"[{C_PRIMARY}]› {msg}[/{C_PRIMARY}]"),
            border_style=C_DIM,
            padding=(0, 1),
            expand=False,
        )
    )

def animated_separator(label="", style=None):
    if style is None:
        style = C_BORDER
    if label:
        console.print(Rule(f"[bold {C_TEXT}]{label}[/bold {C_TEXT}]", style=style, characters="─"))
    else:
        console.print(Rule(style=C_DIM, characters="─"))

def status_bar(model_name=None, agent_name=None, skills_list=None):
    """Barra de status compacta e profissional."""
    parts = []
    if model_name:
        parts.append(f"[bold {C_PRIMARY}]⬡ MODEL [/bold {C_PRIMARY}][{C_TEXT}]{model_name}[/{C_TEXT}]")
    else:
        parts.append(f"[{C_DIM}]⬡ MODEL — none[/{C_DIM}]")
    if agent_name:
        parts.append(f"[bold {C_SECONDARY}]◈ AGENT [/bold {C_SECONDARY}][{C_TEXT}]{agent_name}[/{C_TEXT}]")
    if skills_list:
        names = ", ".join([s.get('name', '?') for s in skills_list])
        parts.append(f"[bold {C_ACCENT}]⚡ SKILLS [/bold {C_ACCENT}][{C_TEXT}]{names}[/{C_TEXT}]")
    console.print(
        Panel(
            "  │  ".join(parts),
            border_style=C_BORDER,
            padding=(0, 1),
            expand=True,
        )
    )

# Configurações de Diretório
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
MCP_CONFIG_PATH = os.path.join("mcp", "config.json")
AGENTS_DIR = os.path.join(BASE_DIR, "agents")
SKILLS_DIR = os.path.join(BASE_DIR, "skills")
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")

def save_config(section, key, value):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if not config.has_section(section):
        config.add_section(section)
    config.set(section, key, str(value))
    with open(CONFIG_FILE, 'w') as f:
        config.write(f)

def load_config(section, key):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if config.has_option(section, key):
        return config.get(section, key)
    return None

def get_checkpoint_dir(workspace_dir):
    user_dir = os.path.expanduser("~")
    duckhunt_cache = os.path.join(user_dir, ".duckhunt", "cache")
    ws_hash = hashlib.md5(workspace_dir.encode('utf-8')).hexdigest()[:8]
    ws_name = os.path.basename(os.path.normpath(workspace_dir))
    return os.path.join(duckhunt_cache, f"{ws_name}_{ws_hash}", "checkpoint")

def create_checkpoint(workspace_dir):
    ckpt_dir = get_checkpoint_dir(workspace_dir)
    try:
        if os.path.exists(ckpt_dir):
            shutil.rmtree(ckpt_dir, ignore_errors=True)
            
        def ignore_func(d, files):
            ignored = {'.git', 'node_modules', 'venv', 'env', '__pycache__', '.pytest_cache', '.next', '.nuxt', 'dist', 'build', '.duckhunt'}
            return [f for f in files if f in ignored or os.path.join(d, f) == ckpt_dir]
            
        shutil.copytree(workspace_dir, ckpt_dir, ignore=ignore_func, dirs_exist_ok=True)
        return True
    except Exception as e:
        console.print(f"[dim red]Erro ao criar checkpoint: {e}[/dim red]")
        return False

def rollback_checkpoint(workspace_dir):
    ckpt_dir = get_checkpoint_dir(workspace_dir)
    if not os.path.exists(ckpt_dir):
        return False, "Nenhum checkpoint encontrado para este workspace."
    try:
        def ignore_func(d, files):
            ignored = {'.git', 'node_modules', 'venv', 'env', '__pycache__', '.pytest_cache', '.next', '.nuxt', 'dist', 'build', '.duckhunt'}
            return [f for f in files if f in ignored]
        
        shutil.copytree(ckpt_dir, workspace_dir, ignore=ignore_func, dirs_exist_ok=True)
        return True, "Rollback concluído com sucesso."
    except Exception as e:
        return False, f"Erro no rollback: {e}"

SYSTEM_PROMPT = """
You are a **senior development assistant running directly in the user's terminal**.
You have **tools (Tools / Function Calling)** to interact with the system.

### ABSOLUTE RULES

1. To perform actions (**create/edit files, read directories, run commands**), you **MUST use the provided tools**.
2. **Tool Format:** If the native call fails, you **MUST write the action using the format below:**

```
<tool_call>
{"name": "tool_name", "arguments": {"param1": "value1"}}
</tool_call>
```

3. **NEVER** write standalone terminal commands or scripts asking the user to copy and paste them. **Execute them yourself.**
4. **Call the tool, wait for the result**, and if additional context is needed, **read the file first before proceeding.**
5. **Thinking Process:** You **MUST ALWAYS** start your response with a `<think>...</think>` block. Inside this block, you should:
   - Analyze the user's request.
   - Plan the necessary steps.
   - Decide which tools to use.
   - Review the results of previous actions.
   - **ONLY AFTER** closing the `</think>` tag, you should provide the final response or tool calls.
"""

class UnifiedLLM:
    def __init__(self, client, model_type, model_name):
        self.client = client
        self.model_type = model_type
        self.model_name = model_name

    def create_chat_completion(self, messages, tools=None, tool_choice=None, max_tokens=None, temperature=None, stream=True):
        if self.model_type == "local":
            # Adaptação para modelos locais:
            # 1. Injeta definições de ferramentas no prompt do sistema
            # 2. Não passa 'tools' nativamente para evitar bloqueio na geração do llama-cpp-python
            local_messages = [m.copy() for m in messages]
            
            if tools:
                tools_list = [t.get('function', {}) for t in tools]
                tools_injection = f"\n\n### AVAILABLE TOOLS\nUse the <tool_call> format to invoke tools.\nTools Schema:\n{json.dumps(tools_list, indent=2)}"
                
                system_found = False
                for msg in local_messages:
                    if msg.get('role') == 'system':
                        msg['content'] = msg.get('content', '') + tools_injection
                        system_found = True
                        break
                
                if not system_found:
                    local_messages.insert(0, {"role": "system", "content": tools_injection})

            # Gera a resposta via yield from para funcionar como generator
            response_generator = self.client.create_chat_completion(
                messages=local_messages,
                # tools=tools, # Desabilitado para garantir resposta
                # tool_choice=tool_choice,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=stream
            )
            
            if stream:
                yield from response_generator
            else:
                yield response_generator
            return

        if self.model_type == "anthropic":
            if not ANTHROPIC_AVAILABLE: return
            sys_msg = ""
            anthropic_messages = []
            
            tools_injection = ""
            if tools:
                tools_list = [t.get('function', {}) for t in tools]
                tools_injection = f"\n\n### AVAILABLE TOOLS\nUse the <tool_call> format to invoke tools.\nTools Schema:\n{json.dumps(tools_list, indent=2)}"
            
            for m in messages:
                role = m.get("role", "")
                if role == "system":
                    sys_msg += m.get("content", "") + "\n"
                else:
                    mapped_role = "assistant" if role == "assistant" else "user"
                    content = m.get("content", "") or ""
                    if role == "assistant" and m.get("tool_calls"):
                        for tc in m["tool_calls"]:
                            try:
                                args = json.loads(tc['function']['arguments'])
                            except:
                                args = tc['function']['arguments']
                            content += f"\n<tool_call>\n{json.dumps({'name': tc['function']['name'], 'arguments': args})}\n</tool_call>"
                    if role == "tool":
                        content = f"Tool '{m.get('name', 'unknown')}' Result:\n{m.get('content', '')}"
                    if not content:
                        content = "(empty)"
                        
                    if anthropic_messages and anthropic_messages[-1]["role"] == mapped_role:
                        anthropic_messages[-1]["content"] += f"\n\n{content}"
                    else:
                        anthropic_messages.append({"role": mapped_role, "content": content})

            sys_msg += tools_injection

            try:
                if stream:
                    with self.client.messages.stream(
                        max_tokens=max_tokens or 4096,
                        system=sys_msg,
                        messages=anthropic_messages,
                        model=self.model_name
                    ) as stream_ctx:
                        for text in stream_ctx.text_stream:
                            yield {"choices": [{"delta": {"content": text}, "finish_reason": None}]}
                        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}
                else:
                    resp = self.client.messages.create(
                        max_tokens=max_tokens or 4096,
                        system=sys_msg,
                        messages=anthropic_messages,
                        model=self.model_name
                    )
                    yield {"choices": [{"delta": {"content": resp.content[0].text}, "finish_reason": "stop"}]}
            except Exception as e:
                console.print(f"[red]Erro API Anthropic: {e}[/red]")
            return

        kwargs = {
            "messages": messages,
            "stream": stream,
            "model": self.model_name
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        if self.model_type in ("openai", "gemini"):
            if max_tokens: kwargs["max_tokens"] = max_tokens
            if temperature: kwargs["temperature"] = temperature
        
        # Azure ignora max_tokens e temperature

        try:
            response = self.client.chat.completions.create(**kwargs)
            if stream:
                for chunk in response:
                    processed = self._convert_chunk(chunk)
                    if processed:
                        yield processed
            else:
                yield self._convert_chunk(response)
        except Exception as e:
            console.print(f"[red]Erro API ({self.model_type}): {e}[/red]")

    def _convert_chunk(self, chunk):
        if not hasattr(chunk, "choices") or not chunk.choices: return {}
        choice = chunk.choices[0]
        delta = choice.delta
        delta_dict = {}
        if hasattr(delta, "content") and delta.content is not None: 
            delta_dict["content"] = delta.content
            
        # Preserve Gemini thought signatures (extra_content) in assistant messages
        # This is REQUIRED for Gemini tools to work in follow-up calls
        if hasattr(delta, "extra_content") and delta.extra_content:
            # Ensure extra_content is a dictionary if we intend to update it
            if isinstance(delta.extra_content, dict):
                delta_dict.setdefault("extra_content", {}).update(delta.extra_content)
            else:
                delta_dict["extra_content"] = delta.extra_content

        if getattr(delta, "tool_calls", None):
            # Initialize tool_calls list if it doesn't exist in delta_dict
            if "tool_calls" not in delta_dict:
                delta_dict["tool_calls"] = []
            for tc in delta.tool_calls:
                if hasattr(tc, "model_dump"):
                    tc_dict = tc.model_dump(exclude_unset=True)
                else:
                    tc_dict = {"index": getattr(tc, "index", None)}
                    if getattr(tc, "id", None): tc_dict["id"] = tc.id
                    if getattr(tc, "type", None): tc_dict["type"] = tc.type
                    if getattr(tc, "function", None):
                        tc_dict["function"] = {}
                        if getattr(tc.function, "name", None): tc_dict["function"]["name"] = tc.function.name
                        if getattr(tc.function, "arguments", None): tc_dict["function"]["arguments"] = tc.function.arguments
                    # Preserve extra_content inside individual tool calls if present
                    ext = getattr(tc, "extra_content", None)
                    if ext:
                        # Ensure extra_content is a dictionary if we intend to update it
                        if isinstance(ext, dict):
                            tc_dict.setdefault("extra_content", {}).update(ext)
                        else:
                            tc_dict["extra_content"] = ext
                delta_dict["tool_calls"].append(tc_dict)
        return {"choices": [{"delta": delta_dict, "finish_reason": choice.finish_reason}]}

async def gerenciar_agentes(current_prompt: str) -> str:
    try:
        if not os.path.exists(AGENTS_DIR):
            notify_error(f"Pasta de agentes não encontrada em '{AGENTS_DIR}'.")
            return current_prompt

        agentes = [f for f in os.listdir(AGENTS_DIR) if f.lower().endswith(".md")]
        if not agentes:
            notify_error(f"Nenhum agente (.md) encontrado em '{AGENTS_DIR}'.")
            return current_prompt

        # Arrow-key selection with InquirerPy
        if INQUIRER_AVAILABLE:
            choices = [{"name": f"  ◈ {a.replace('.md', '')}", "value": a} for a in agentes]
            choices.append(Separator("─" * 40))
            choices.append({"name": f"  ✗ Cancelar", "value": None})
            
            arquivo = await inquirer.select(
                message="Selecione o agente",
                choices=choices,
                pointer="▸",
                qmark="◈",
                amark="✓",
                instruction="(↑↓ navegar, Enter selecionar)",
            ).execute_async()
            
            if arquivo is None:
                return current_prompt
        else:
            # Fallback: numbered list
            table = Table(title="◈ Agentes Disponíveis", title_style=f"bold {C_SECONDARY}", border_style=C_BORDER)
            table.add_column("", justify="center", style=f"bold {C_PRIMARY}", no_wrap=True, width=4)
            table.add_column("Agente", style=C_TEXT)
            for i, nome in enumerate(agentes, 1):
                table.add_row(str(i), nome.replace('.md', ''))
            console.print(table)

            escolha = Prompt.ask(f"\n[{C_SECONDARY}]Escolha o agente[/{C_SECONDARY}] [{C_DIM}](c=cancelar)[/{C_DIM}]").strip().lower()
            if escolha == 'c':
                return current_prompt
            if not escolha.isdigit() or not (0 <= int(escolha) - 1 < len(agentes)):
                notify_error("Opção inválida.")
                return current_prompt
            arquivo = agentes[int(escolha) - 1]
        
        try:
            with open(os.path.join(AGENTS_DIR, arquivo), 'r', encoding='utf-8') as f:
                conteudo = f.read()
            notify_success(f"Agente '{arquivo.replace('.md', '')}' ativado")
            save_config("Agent", "filename", arquivo)
            return conteudo
        except Exception as e:
            notify_error(f"Erro ao ler o agente: {e}")
            return current_prompt
    except KeyboardInterrupt:
        return current_prompt

async def gerenciar_skills(current_skills: list = None) -> list | str | None:
    """Retorna lista de skills selecionadas, 'CLEAR' para limpar, ou None para cancelar."""
    try:
        if not os.path.exists(SKILLS_DIR):
            notify_error(f"Pasta de skills não encontrada em '{SKILLS_DIR}'.")
            return None

        encontrados = []
        for root, _dirs, files in os.walk(SKILLS_DIR):
            for f in files:
                if f.lower() == 'skill.md':
                    encontrados.append((os.path.relpath(root, SKILLS_DIR), os.path.join(root, f)))

        if not encontrados and not current_skills:
            notify_error("Nenhuma skill encontrada.")
            return None

        has_loaded = current_skills and len(current_skills) > 0

        # InquirerPy checkbox
        if INQUIRER_AVAILABLE:
            choices = []
            # "Clear" option first if skills are loaded
            if has_loaded:
                loaded_names = ", ".join([s.get("name", "?") for s in current_skills])
                choices.append({"name": f"  ✗ Limpar skills carregadas ({loaded_names})", "value": "CLEAR"})
                choices.append(Separator("─" * 40))
            for idx, (rel, _) in enumerate(encontrados):
                choices.append({"name": f"  ⚡ {rel}", "value": idx})
            
            selected = await inquirer.checkbox(
                message="Skills",
                choices=choices,
                pointer="▸",
                qmark="⚡",
                amark="✓",
                enabled_symbol="◉",
                disabled_symbol="○",
                instruction="(↑↓ navegar, Space marcar, Enter confirmar)",
            ).execute_async()
            
            if not selected:
                return None
            if "CLEAR" in selected:
                return "CLEAR"
            indices = selected
        else:
            # Fallback: numbered table
            table = Table(title="⚡ Skills", title_style=f"bold {C_ACCENT}", border_style=C_BORDER)
            table.add_column("", justify="center", style=f"bold {C_PRIMARY}", no_wrap=True, width=4)
            table.add_column("Skill", style=C_TEXT)
            
            offset = 0
            if has_loaded:
                loaded_names = ", ".join([s.get("name", "?") for s in current_skills])
                table.add_row("0", f"[{C_ERROR}]✗ Limpar skills ({loaded_names})[/{C_ERROR}]")
                offset = 0  # 0 = clear
            
            for i, (rel, _) in enumerate(encontrados, 1):
                table.add_row(str(i), rel)
            console.print(table)

            escolha = Prompt.ask(f"\n[{C_ACCENT}]Selecione skills (ex.: 1,3)[/{C_ACCENT}] [{C_DIM}](c=cancelar)[/{C_DIM}]").strip().lower()
            if escolha == 'c': return None
            
            nums = [int(t) for t in escolha.replace(',', ' ').split() if t.isdigit()]
            if 0 in nums and has_loaded:
                return "CLEAR"
            indices = [n - 1 for n in nums]

        selecionados = []
        for idx in set(indices):
            if 0 <= idx < len(encontrados):
                rel, caminho = encontrados[idx]
                try:
                    skill_root_dir = os.path.abspath(os.path.dirname(caminho))
                    with open(caminho, 'r', encoding='utf-8') as f:
                        selecionados.append({
                            "name": rel, 
                            "content": f.read(),
                            "path": skill_root_dir
                        })
                except Exception as e:
                    notify_error(f"Erro na skill '{rel}': {e}")

        if selecionados:
            nomes = ", ".join([s["name"] for s in selecionados])
            notify_success(f"Skills ativadas: {nomes}")
            save_config("Skills", "loaded", nomes)
            return selecionados
        notify_error("Nenhuma skill válida selecionada.")
        return None
    except KeyboardInterrupt:
        return None

def get_unloaded_skills_info(skills_prompts: list) -> list:
    loaded_names = {sp.get("name") for sp in (skills_prompts or [])}
    unloaded = []
    if os.path.exists(SKILLS_DIR):
        for root, _dirs, files in os.walk(SKILLS_DIR):
            for f in files:
                if f.lower() == 'skill.md':
                    rel_name = os.path.relpath(root, SKILLS_DIR)
                    if rel_name in loaded_names:
                        continue
                    
                    caminho = os.path.join(root, f)
                    try:
                        with open(caminho, 'r', encoding='utf-8') as sf:
                            content = sf.read()
                            
                        # Try to extract description from frontmatter
                        description = "Nenhuma descrição disponível."
                        desc_match = re.search(r'^description:\s*(.+)$', content, re.MULTILINE)
                        if desc_match:
                            description = desc_match.group(1).strip()
                            
                        unloaded.append({"name": rel_name, "description": description})
                    except Exception:
                        pass
    return unloaded

def load_skill_by_name(skill_name: str, skills_prompts: list) -> bool:
    if not os.path.exists(SKILLS_DIR):
        return False
        
    for root, _dirs, files in os.walk(SKILLS_DIR):
        for f in files:
            if f.lower() == 'skill.md':
                rel_name = os.path.relpath(root, SKILLS_DIR)
                if rel_name == skill_name:
                    # check if already loaded
                    if any(sp.get("name") == skill_name for sp in skills_prompts):
                        return True
                        
                    caminho = os.path.join(root, f)
                    try:
                        with open(caminho, 'r', encoding='utf-8') as sf:
                            content = sf.read()
                        
                        skill_root_dir = os.path.abspath(os.path.dirname(caminho))
                        skills_prompts.append({
                            "name": rel_name,
                            "content": content,
                            "path": skill_root_dir
                        })
                        save_config("Skills", "loaded", ", ".join([s["name"] for s in skills_prompts]))
                        return True
                    except Exception as e:
                        notify_error(f"Erro ao carregar skill '{skill_name}': {e}")
                        return False
    return False

def compor_prompt_sistema(agent_prompt_text: str, skills_prompts: list) -> str:
    partes = [agent_prompt_text or ""]
    
    if skills_prompts:
        partes.append("\n\n### ACTIVE SKILLS (EXTENSIONS)\n")
        partes.append("The following skills are loaded. When executing scripts or accessing files from these skills, use the 'Base Directory' provided for each.\n")
        
        for sp in skills_prompts:
            partes.append(f"\n--- Skill: {sp.get('name', '(skill)')} ---")
            partes.append(f"\n[Base Directory]: {sp.get('path')}") 
            partes.append(f"\n[Instructions]:\n{sp.get('content', '')}\n")
            
    unloaded = get_unloaded_skills_info(skills_prompts)
    if unloaded:
        partes.append("\n\n### AVAILABLE SKILLS (UNLOADED)\n")
        partes.append("You have the ability to dynamically load specialized skills into your context when needed using the `load_duckhunt_skill` tool. These skills provide specialized knowledge and tools for specific tasks.\n")
        partes.append("Available skills:\n")
        for u in unloaded:
            partes.append(f"- **{u['name']}**: {u['description']}\n")
            
    return "".join(partes)
def stream_and_accumulate(llm, messages, tools):
    """
    Renderiza o pensamento em um painel e a resposta normal em Markdown em tempo real.
    """
    response_gen = llm.create_chat_completion(
        messages=messages,
        tools=tools,
        tool_choice="auto",
        max_tokens=2048,
        temperature=0.3,
        stream=True
    )
    
    message = {"role": "assistant", "content": "", "tool_calls": []}
    
    # Variáveis para parsing visual no terminal
    raw_content = ""

    # Live UI para atualizar a interface fluida
    with Live(auto_refresh=True, console=console, refresh_per_second=15) as live:
        for chunk in response_gen:
            delta = chunk["choices"][0].get("delta", {})
            
            if "content" in delta and delta["content"]:
                raw_content += delta["content"]
                message["content"] += delta["content"]
                
                # --- PARSER DO BLOCO DE PENSAMENTO ---
                think_text = ""
                main_text = ""
                
                # Checa se existe a tag <think>
                if "<think>" in raw_content:
                    parts = raw_content.split("<think>", 1)
                    main_text += parts[0]
                    
                    think_parts = parts[1].split("</think>", 1)
                    think_text = think_parts[0]
                    
                    if len(think_parts) > 1:
                        main_text += think_parts[1]
                else:
                    main_text = raw_content
                
                # --- MONTAGEM DA INTERFACE RICH ---
                renderables = []
                if think_text.strip():
                    renderables.append(
                        Panel(
                            Text(think_text.strip(), style="dim italic"), 
                            title="🧠 Processo de Pensamento", 
                            border_style="dim",
                            padding=(0, 1)
                        )
                    )
                if main_text.strip():
                    renderables.append(Markdown(main_text.strip()))
                
                # Atualiza a tela ao vivo
                if renderables:
                    live.update(Group(*renderables))
                
            # Acumula chamadas de ferramentas nativas
            if "tool_calls" in delta and delta["tool_calls"]:
                for tc_chunk in delta["tool_calls"]:
                    index = tc_chunk.get("index")
                    if index is None:
                        tc_id = tc_chunk.get("id")
                        if tc_id:
                            found_idx = next((i for i, t in enumerate(message["tool_calls"]) if t.get("id") == tc_id), None)
                            if found_idx is not None:
                                index = found_idx
                            else:
                                index = len(message["tool_calls"])
                        else:
                            index = max(0, len(message["tool_calls"]) - 1)
                            
                    while len(message["tool_calls"]) <= index:
                        message["tool_calls"].append({
                            "id": "", "type": "function", "function": {"name": "", "arguments": ""}
                        })
                    tc_acc = message["tool_calls"][index]
                    
                    for k, v in tc_chunk.items():
                        if k == "index": continue
                        if k == "function" and isinstance(v, dict):
                            for fk, fv in v.items():
                                if fv is not None:
                                    if fk in ["name", "arguments"]:
                                        tc_acc["function"][fk] = tc_acc["function"].get(fk, "") + str(fv)
                                    else:
                                        if isinstance(fv, str):
                                            tc_acc["function"][fk] = tc_acc["function"].get(fk, "") + fv
                                        else:
                                            tc_acc["function"][fk] = fv
                        elif v is not None:
                            if k == "type":
                                tc_acc[k] = v # Não concatena 'type' para evitar 'functionfunction' no Azure
                            elif k == "id":
                                tc_acc[k] = tc_acc.get(k, "") + str(v)
                            else:
                                if isinstance(v, str):
                                    tc_acc[k] = tc_acc.get(k, "") + v
                                else:
                                    tc_acc[k] = v
                                    
                    # Accumulate extra_content for Gemini
                    if "extra_content" in tc_chunk and tc_chunk["extra_content"]:
                        if "extra_content" not in tc_acc or not isinstance(tc_acc["extra_content"], dict): 
                            tc_acc["extra_content"] = {}
                        if isinstance(tc_chunk["extra_content"], dict):
                            tc_acc["extra_content"].update(tc_chunk["extra_content"])
                        
            # Accumulate top-level extra_content for Gemini
            if "extra_content" in delta and delta["extra_content"]:
                if "extra_content" not in message or not isinstance(message["extra_content"], dict): 
                    message["extra_content"] = {}
                if isinstance(delta["extra_content"], dict):
                    message["extra_content"].update(delta["extra_content"])
                        
    # --- FALLBACK: PARSER MANUAL DE TOOL CALL ---
    if not message["tool_calls"] and "<tool_call>" in message["content"]:
        matches = re.findall(r'<tool_call>(.*?)</tool_call>', message["content"], re.DOTALL | re.IGNORECASE)
        for i, match in enumerate(matches):
            clean_match = match.strip()
            if clean_match.startswith('```json'): clean_match = clean_match[7:]
            elif clean_match.startswith('```'): clean_match = clean_match[3:]
            if clean_match.endswith('```'): clean_match = clean_match[:-3]
            try:
                tool_data = json.loads(clean_match.strip())
                if "name" in tool_data and "arguments" in tool_data:
                    message["tool_calls"].append({
                        "id": f"call_manual_{i}",
                        "type": "function",
                        "function": {"name": tool_data["name"], "arguments": json.dumps(tool_data["arguments"])}
                    })
            except json.JSONDecodeError:
                pass

    if not message["tool_calls"]: del message["tool_calls"]
    return message

def banner():
    bn = """

\033[49m                  \033[38;2;4;4;4;49m▄\033[38;2;5;5;5;49m▄▄▄▄▄▄▄▄▄▄\033[49m                     \033[m
\033[49m            \033[38;2;0;0;0;49m▄\033[38;2;3;3;3;49m▄\033[38;2;5;4;5;49m▄\033[38;2;39;8;9;48;2;5;5;5m▄\033[38;2;52;10;10;48;2;5;3;5m▄\033[38;2;35;11;11;48;2;5;3;5m▄\033[38;2;109;17;17;48;2;21;11;11m▄\033[38;2;219;42;29;48;2;67;17;12m▄\033[38;2;242;154;134;48;2;63;45;45m▄\033[38;2;246;184;175;48;2;68;61;60m▄▄\033[38;2;242;130;68;48;2;53;9;10m▄\033[38;2;242;99;34;48;2;53;9;10m▄\033[38;2;248;47;34;48;2;53;9;10m▄▄▄\033[38;2;239;43;32;48;2;53;9;10m▄\033[38;2;36;13;13;48;2;5;3;5m▄\033[38;2;44;9;10;48;2;5;3;5m▄\033[38;2;52;11;10;48;2;5;3;5m▄\033[38;2;44;9;10;48;2;37;23;21m▄\033[38;2;5;4;5;49m▄▄\033[49m               \033[m
\033[49m         \033[38;2;6;0;6;49m▄\033[38;2;4;4;4;49m▄\033[38;2;17;8;8;48;2;9;0;9m▄\033[38;2;121;32;25;48;2;6;4;6m▄\033[38;2;179;36;27;48;2;40;12;10m▄\033[38;2;126;27;23;48;2;89;19;15m▄\033[38;2;98;22;19;48;2;189;34;26m▄\033[38;2;5;4;5;48;2;131;17;18m▄\033[38;2;5;4;5;48;2;119;18;18m▄\033[38;2;5;4;5;48;2;71;12;13m▄\033[38;2;172;141;121;48;2;32;7;8m▄\033[38;2;228;71;56;48;2;192;36;27m▄\033[48;2;248;47;34m     \033[38;2;49;12;10;48;2;164;36;29m▄\033[38;2;5;4;5;48;2;74;31;26m▄\033[38;2;5;4;5;48;2;69;29;25m▄\033[38;2;20;6;7;48;2;80;30;27m▄\033[38;2;91;24;20;48;2;187;25;25m▄\033[38;2;169;36;28;48;2;243;45;33m▄\033[38;2;248;47;34;48;2;198;32;27m▄\033[38;2;248;47;34;48;2;90;19;15m▄\033[38;2;221;41;31;48;2;62;14;11m▄\033[38;2;130;27;21;48;2;5;4;5m▄\033[38;2;70;16;13;48;2;5;3;5m▄\033[38;2;5;4;5;49m▄\033[38;2;5;3;5;49m▄\033[38;2;5;0;5;49m▄\033[38;2;0;0;0;49m▄\033[49m         \033[m
\033[49m       \033[38;2;5;0;5;49m▄\033[38;2;9;4;5;48;2;5;5;5m▄\033[38;2;102;21;16;48;2;9;4;5m▄\033[38;2;235;163;129;48;2;93;32;26m▄\033[38;2;244;210;190;48;2;163;62;45m▄\033[38;2;245;220;210;48;2;244;168;142m▄\033[38;2;245;224;217;48;2;244;216;201m▄\033[38;2;245;224;217;48;2;204;147;101m▄\033[38;2;225;122;103;48;2;33;25;22m▄\033[38;2;222;47;35;48;2;22;10;9m▄\033[38;2;225;47;34;48;2;52;14;12m▄\033[48;2;248;47;34m        \033[38;2;232;45;33;48;2;123;18;18m▄\033[38;2;212;45;34;48;2;21;9;9m▄\033[38;2;43;10;11;48;2;5;4;5m▄\033[38;2;33;20;13;48;2;5;4;5m▄\033[38;2;63;36;12;48;2;5;4;5m▄\033[38;2;229;109;83;48;2;140;32;25m▄\033[48;2;248;47;34m  \033[38;2;236;42;32;48;2;248;47;34m▄\033[38;2;204;46;35;48;2;247;47;34m▄\033[38;2;195;43;33;48;2;194;24;24m▄\033[38;2;194;38;31;48;2;107;23;21m▄\033[38;2;208;38;29;48;2;37;14;12m▄\033[38;2;168;36;29;48;2;12;5;6m▄\033[38;2;5;4;5;48;2;6;3;6m▄\033[38;2;6;3;6;49m▄\033[49m        \033[m
\033[49m     \033[38;2;14;8;8;49m▄\033[38;2;7;4;5;48;2;6;4;6m▄\033[38;2;177;36;27;48;2;11;4;6m▄\033[38;2;248;47;34;48;2;145;26;21m▄\033[38;2;245;197;189;48;2;246;81;54m▄\033[38;2;245;222;214;48;2;244;205;180m▄\033[48;2;245;224;217m  \033[38;2;244;190;156;48;2;245;220;209m▄\033[38;2;243;94;35;48;2;244;194;161m▄\033[38;2;248;47;34;48;2;246;77;45m▄\033[48;2;248;47;34m             \033[38;2;248;47;34;48;2;246;146;132m▄\033[38;2;248;47;34;48;2;246;151;141m▄\033[48;2;248;47;34m   \033[38;2;53;17;16;48;2;108;23;21m▄\033[48;2;5;4;5m  \033[38;2;5;4;5;48;2;38;10;10m▄\033[38;2;86;12;13;48;2;166;22;22m▄\033[38;2;156;21;22;48;2;220;35;29m▄\033[38;2;232;40;31;48;2;196;30;26m▄\033[38;2;144;32;25;48;2;23;6;7m▄\033[38;2;9;5;6;48;2;6;3;6m▄\033[38;2;5;3;5;49m▄\033[49m      \033[m
\033[49m    \033[38;2;5;5;5;48;2;4;4;4m▄\033[38;2;11;5;6;48;2;6;4;6m▄\033[38;2;237;43;32;48;2;163;28;23m▄\033[38;2;238;43;32;48;2;239;47;34m▄\033[38;2;247;54;34;48;2;248;47;34m▄\033[38;2;245;208;197;48;2;248;47;34m▄\033[38;2;245;204;190;48;2;246;93;72m▄\033[38;2;248;47;34;48;2;247;103;92m▄\033[38;2;248;47;34;48;2;246;111;92m▄\033[38;2;248;47;34;48;2;246;64;34m▄\033[48;2;248;47;34m                    \033[38;2;237;42;32;48;2;209;38;31m▄\033[38;2;191;23;24;48;2;162;30;23m▄\033[38;2;117;39;34;48;2;9;6;7m▄\033[38;2;17;6;6;48;2;5;4;5m▄\033[38;2;22;12;7;48;2;5;4;5m▄\033[38;2;167;95;79;48;2;80;17;16m▄\033[38;2;191;23;24;48;2;192;24;24m▄\033[38;2;191;23;24;48;2;218;34;29m▄\033[38;2;229;39;31;48;2;188;35;28m▄\033[38;2;143;21;20;48;2;13;7;7m▄\033[38;2;19;5;6;48;2;5;5;5m▄\033[38;2;6;6;6;49m▄\033[49m    \033[m
\033[49m   \033[38;2;4;4;4;48;2;6;6;6m▄\033[38;2;11;4;5;48;2;5;4;5m▄\033[38;2;159;31;26;48;2;141;25;20m▄\033[38;2;191;23;24;48;2;218;35;29m▄\033[38;2;191;23;24;48;2;198;26;25m▄\033[38;2;198;31;25;48;2;247;53;34m▄\033[38;2;244;64;51;48;2;244;190;164m▄\033[38;2;247;61;44;48;2;243;192;159m▄\033[38;2;244;84;34;48;2;248;47;34m▄\033[38;2;240;125;34;48;2;248;47;34m▄\033[38;2;241;132;52;48;2;248;47;34m▄\033[38;2;246;204;196;48;2;248;47;34m▄\033[38;2;246;205;197;48;2;248;47;34m▄▄▄▄\033[38;2;244;190;167;48;2;248;47;34m▄\033[38;2;241;132;53;48;2;248;47;34m▄\033[38;2;243;160;109;48;2;248;47;34m▄▄\033[38;2;240;126;40;48;2;248;47;34m▄\033[38;2;240;124;34;48;2;248;47;34m▄\033[38;2;242;104;34;48;2;248;47;34m▄\033[38;2;247;61;42;48;2;248;47;34m▄\033[38;2;247;57;35;48;2;248;47;34m▄\033[38;2;247;56;34;48;2;248;47;34m▄\033[48;2;248;47;34m   \033[38;2;247;47;34;48;2;248;47;34m▄\033[38;2;209;31;27;48;2;248;47;34m▄\033[38;2;191;23;24;48;2;200;26;26m▄\033[48;2;191;23;24m \033[38;2;191;23;24;48;2;189;23;24m▄\033[38;2;191;23;24;48;2;198;28;26m▄\033[38;2;191;23;24;48;2;235;173;144m▄\033[38;2;191;23;24;48;2;199;56;54m▄\033[48;2;191;23;24m  \033[38;2;191;23;24;48;2;192;23;24m▄\033[38;2;222;36;29;48;2;199;26;25m▄\033[38;2;204;37;30;48;2;36;8;8m▄\033[38;2;5;4;5;48;2;4;4;4m▄\033[38;2;6;6;6;49m▄\033[49m   \033[m
\033[49m  \033[48;2;4;4;4m \033[48;2;5;4;5m \033[38;2;168;26;23;48;2;167;25;22m▄\033[38;2;238;86;57;48;2;217;34;29m▄\033[38;2;222;135;127;48;2;198;34;26m▄\033[38;2;198;46;42;48;2;209;73;55m▄\033[38;2;197;34;25;48;2;225;82;30m▄\033[38;2;191;24;24;48;2;230;98;32m▄\033[38;2;191;23;24;48;2;230;124;89m▄\033[38;2;133;17;18;48;2;223;93;30m▄\033[38;2;30;7;8;48;2;228;53;31m▄\033[38;2;30;7;8;48;2;227;38;30m▄▄▄▄▄▄▄▄\033[38;2;33;7;8;48;2;228;38;30m▄\033[38;2;161;20;21;48;2;235;41;32m▄\033[38;2;168;20;21;48;2;235;42;32m▄\033[38;2;168;20;21;48;2;234;52;32m▄\033[38;2;168;20;21;48;2;230;96;32m▄\033[38;2;168;20;21;48;2;231;120;80m▄\033[38;2;190;23;24;48;2;230;99;37m▄\033[38;2;196;25;25;48;2;238;99;33m▄\033[38;2;199;32;32;48;2;248;61;45m▄\033[38;2;198;50;50;48;2;246;98;75m▄\033[38;2;217;81;40;48;2;246;57;34m▄\033[38;2;233;119;36;48;2;230;40;31m▄\033[38;2;207;51;32;48;2;191;23;24m▄\033[48;2;191;23;24m          \033[38;2;233;41;31;48;2;226;38;30m▄\033[38;2;163;25;24;48;2;40;8;9m▄\033[38;2;10;7;7;48;2;9;6;6m▄\033[38;2;4;4;4;48;2;0;0;0m▄\033[49m  \033[m
\033[49m  \033[38;2;5;4;5;48;2;7;3;7m▄\033[38;2;117;30;29;48;2;6;4;5m▄\033[38;2;228;124;118;48;2;173;42;24m▄\033[38;2;185;24;25;48;2;231;96;60m▄\033[38;2;103;14;15;48;2;201;53;27m▄\033[38;2;5;4;5;48;2;191;27;26m▄\033[38;2;14;8;8;48;2;103;22;21m▄\033[38;2;174;24;23;48;2;86;12;13m▄\033[38;2;239;133;34;48;2;86;12;13m▄\033[38;2;241;147;31;48;2;81;23;16m▄\033[38;2;254;237;15;48;2;127;71;21m▄▄▄\033[38;2;254;237;15;48;2;135;124;12m▄▄▄▄▄▄▄▄\033[38;2;254;237;15;48;2;58;53;8m▄\033[38;2;254;237;15;48;2;5;4;5m▄▄▄\033[38;2;247;230;16;48;2;83;12;13m▄\033[38;2;46;36;14;48;2;86;12;13m▄\033[38;2;8;7;5;48;2;111;15;16m▄\033[38;2;8;6;5;48;2;190;23;24m▄\033[38;2;72;11;12;48;2;201;45;26m▄\033[38;2;155;19;20;48;2;212;70;28m▄\033[38;2;189;23;24;48;2;219;78;30m▄\033[38;2;191;23;24;48;2;219;76;29m▄\033[38;2;192;24;24;48;2;218;84;29m▄\033[38;2;244;83;34;48;2;194;24;24m▄\033[38;2;234;42;32;48;2;191;23;24m▄\033[48;2;191;23;24m       \033[38;2;247;47;34;48;2;223;43;32m▄\033[38;2;142;31;23;48;2;59;11;11m▄\033[38;2;5;4;5;48;2;6;4;6m▄\033[49m  \033[m
\033[49m  \033[48;2;5;4;5m \033[38;2;123;24;19;48;2;131;26;20m▄\033[38;2;122;29;23;48;2;204;30;27m▄\033[38;2;5;4;5;48;2;114;18;19m▄\033[48;2;5;4;5m  \033[38;2;230;131;26;48;2;174;64;25m▄\033[38;2;250;220;18;48;2;225;109;32m▄\033[38;2;166;120;22;48;2;251;215;19m▄\033[38;2;136;82;20;48;2;251;218;18m▄\033[38;2;181;155;20;48;2;254;237;15m▄\033[38;2;249;215;18;48;2;254;237;15m▄\033[48;2;254;237;15m              \033[38;2;252;234;15;48;2;219;205;14m▄\033[38;2;249;232;15;48;2;204;190;13m▄\033[38;2;249;232;15;48;2;203;188;13m▄\033[38;2;250;210;20;48;2;5;4;5m▄\033[38;2;245;173;27;48;2;11;5;6m▄\033[38;2;69;41;14;48;2;43;8;9m▄\033[38;2;9;6;6;48;2;168;23;23m▄\033[38;2;6;4;5;48;2;184;25;25m▄\033[38;2;153;25;25;48;2;222;44;30m▄\033[38;2;200;31;26;48;2;236;109;33m▄\033[38;2;238;115;36;48;2;206;39;27m▄\033[38;2;198;39;26;48;2;191;23;24m▄\033[48;2;191;23;24m     \033[38;2;198;26;25;48;2;208;30;27m▄\033[38;2;162;44;35;48;2;163;45;35m▄\033[48;2;5;4;5m \033[49m  \033[m
\033[49m  \033[48;2;5;4;5m \033[38;2;91;13;14;48;2;111;21;17m▄\033[48;2;28;6;7m \033[48;2;5;4;5m \033[38;2;24;15;13;48;2;6;4;5m▄\033[38;2;185;131;22;48;2;166;92;28m▄\033[38;2;230;198;18;48;2;253;235;15m▄\033[38;2;22;14;7;48;2;179;166;12m▄\033[38;2;129;117;113;48;2;15;13;13m▄\033[38;2;245;224;217;48;2;24;22;22m▄\033[38;2;66;59;58;48;2;10;8;9m▄\033[38;2;11;7;8;48;2;129;119;10m▄\033[38;2;251;234;15;48;2;254;237;15m▄\033[48;2;254;237;15m            \033[38;2;240;224;14;48;2;253;236;15m▄\033[38;2;117;106;104;48;2;131;108;27m▄\033[38;2;170;155;151;48;2;5;4;5m▄\033[38;2;20;18;18;48;2;5;4;5m▄\033[38;2;5;4;5;48;2;221;206;14m▄\033[38;2;149;125;28;48;2;254;237;15m▄\033[48;2;254;237;15m \033[38;2;252;227;17;48;2;199;170;23m▄\033[38;2;249;203;21;48;2;16;10;6m▄\033[38;2;105;26;14;48;2;41;23;20m▄\033[38;2;18;11;11;48;2;190;27;26m▄\033[38;2;223;81;70;48;2;225;151;147m▄\033[38;2;204;33;27;48;2;198;39;26m▄\033[38;2;95;34;30;48;2;193;24;24m▄\033[38;2;191;168;161;48;2;188;25;25m▄\033[38;2;156;117;111;48;2;189;25;25m▄\033[38;2;183;38;32;48;2;191;23;24m▄\033[48;2;191;23;24m \033[48;2;198;26;25m \033[38;2;235;42;32;48;2;164;44;35m▄\033[38;2;107;14;15;48;2;10;4;5m▄\033[38;2;5;4;5;48;2;0;0;0m▄\033[49m \033[m
\033[49m  \033[38;2;4;4;4;48;2;5;4;5m▄\033[38;2;5;4;5;48;2;77;12;13m▄\033[38;2;45;24;21;48;2;173;42;33m▄\033[38;2;31;20;17;48;2;5;4;5m▄\033[38;2;135;77;35;48;2;98;53;17m▄\033[48;2;249;200;22m \033[48;2;230;198;18m \033[48;2;22;14;7m \033[38;2;5;4;5;48;2;90;82;81m▄\033[38;2;5;4;5;48;2;170;155;151m▄\033[38;2;5;4;5;48;2;46;42;41m▄\033[48;2;11;7;8m \033[48;2;251;234;15m \033[48;2;254;237;15m \033[38;2;251;215;19;48;2;254;237;15m▄\033[38;2;241;141;32;48;2;254;237;15m▄▄▄\033[38;2;231;135;33;48;2;254;237;15m▄\033[38;2;246;177;26;48;2;254;237;15m▄\033[48;2;254;237;15m     \033[48;2;5;4;5m \033[38;2;18;16;16;48;2;167;153;148m▄\033[38;2;24;22;22;48;2;245;224;217m▄\033[38;2;7;6;6;48;2;27;24;24m▄\033[48;2;5;4;5m \033[48;2;42;39;6m \033[48;2;254;237;15m  \033[38;2;254;237;15;48;2;254;236;15m▄\033[38;2;135;125;10;48;2;130;93;16m▄\033[48;2;51;9;10m \033[38;2;239;44;33;48;2;228;38;30m▄\033[48;2;108;17;16m \033[38;2;221;201;195;48;2;221;201;194m▄\033[38;2;11;7;8;48;2;11;8;8m▄\033[38;2;67;57;55;48;2;72;62;60m▄\033[48;2;36;23;21m \033[48;2;162;20;21m \033[38;2;192;23;24;48;2;198;26;25m▄\033[38;2;195;25;24;48;2;244;45;33m▄\033[38;2;107;14;15;48;2;119;19;18m▄\033[48;2;5;4;5m \033[49m \033[m
\033[49m  \033[38;2;0;0;0;49m▄\033[38;2;5;5;5;48;2;4;4;4m▄\033[38;2;10;7;7;48;2;5;4;5m▄\033[38;2;123;77;19;48;2;96;44;16m▄\033[38;2;246;177;26;48;2;243;157;30m▄\033[38;2;243;160;29;48;2;253;227;17m▄\033[38;2;240;138;33;48;2;244;221;16m▄\033[38;2;242;159;29;48;2;119;108;10m▄\033[38;2;81;69;16;48;2;5;4;5m▄\033[38;2;91;74;22;48;2;5;4;5m▄\033[38;2;152;102;20;48;2;5;4;5m▄\033[38;2;136;103;21;48;2;133;123;10m▄\033[38;2;58;51;50;48;2;254;237;15m▄\033[38;2;188;89;81;48;2;233;191;20m▄\033[38;2;245;214;198;48;2;117;84;12m▄\033[38;2;240;134;54;48;2;147;116;109m▄\033[38;2;239;132;34;48;2;148;135;131m▄\033[38;2;240;129;44;48;2;147;129;120m▄\033[38;2;232;110;32;48;2;142;75;21m▄\033[38;2;234;126;33;48;2;87;66;28m▄\033[38;2;225;66;33;48;2;117;108;10m▄\033[38;2;140;124;17;48;2;254;237;15m▄\033[38;2;217;197;20;48;2;254;237;15m▄\033[38;2;247;229;16;48;2;254;237;15m▄\033[48;2;254;237;15m \033[38;2;58;54;7;48;2;5;4;5m▄\033[48;2;5;4;5m   \033[38;2;57;34;22;48;2;5;4;5m▄\033[38;2;241;225;14;48;2;42;39;6m▄\033[48;2;254;237;15m   \033[38;2;140;117;15;48;2;135;125;10m▄\033[38;2;16;10;10;48;2;29;8;8m▄\033[38;2;152;38;30;48;2;221;40;30m▄\033[38;2;242;47;34;48;2;163;23;22m▄\033[38;2;180;28;25;48;2;41;27;24m▄\033[38;2;56;14;12;48;2;73;44;37m▄\033[38;2;106;19;17;48;2;62;39;34m▄\033[38;2;181;28;27;48;2;84;18;17m▄\033[38;2;164;25;23;48;2;179;22;23m▄\033[38;2;215;46;35;48;2;195;25;25m▄\033[38;2;245;47;34;48;2;222;36;29m▄\033[48;2;107;14;15m \033[48;2;5;4;5m \033[49m \033[m
\033[49m  \033[48;2;4;4;4m \033[48;2;5;4;5m \033[38;2;81;45;14;48;2;73;41;14m▄\033[38;2;254;237;15;48;2;246;224;17m▄\033[38;2;248;196;22;48;2;249;193;22m▄\033[38;2;239;132;34;48;2;239;135;33m▄\033[48;2;239;132;34m \033[38;2;239;132;34;48;2;239;130;34m▄\033[38;2;241;147;31;48;2;254;237;15m▄\033[38;2;166;154;12;48;2;201;181;22m▄\033[38;2;189;71;29;48;2;165;45;28m▄\033[38;2;244;86;34;48;2;197;71;30m▄\033[38;2;201;34;28;48;2;238;150;73m▄\033[38;2;128;26;21;48;2;240;159;89m▄\033[38;2;132;27;21;48;2;243;192;157m▄\033[38;2;139;32;21;48;2;239;131;34m▄\033[38;2;191;61;27;48;2;239;132;34m▄\033[38;2;221;81;30;48;2;239;130;34m▄\033[38;2;240;122;34;48;2;237;61;32m▄\033[48;2;239;132;34m \033[38;2;239;132;34;48;2;237;130;34m▄\033[38;2;239;131;34;48;2;100;57;20m▄\033[38;2;244;86;34;48;2;17;12;9m▄\033[38;2;143;31;23;48;2;207;192;14m▄\033[38;2;100;78;27;48;2;254;237;15m▄\033[38;2;248;232;15;48;2;244;227;16m▄\033[38;2;254;237;15;48;2;26;18;13m▄\033[38;2;252;225;17;48;2;5;4;5m▄\033[38;2;247;182;24;48;2;5;4;5m▄\033[38;2;239;132;34;48;2;220;166;23m▄\033[38;2;239;132;34;48;2;254;237;15m▄▄\033[38;2;246;181;25;48;2;254;237;15m▄\033[48;2;254;237;15m \033[38;2;247;190;24;48;2;236;180;24m▄\033[38;2;183;110;25;48;2;164;91;27m▄\033[38;2;24;15;14;48;2;12;8;8m▄\033[38;2;9;7;7;48;2;175;25;24m▄\033[38;2;46;23;20;48;2;247;47;34m▄\033[38;2;46;23;20;48;2;246;47;34m▄\033[38;2;32;16;15;48;2;246;47;34m▄\033[38;2;5;4;5;48;2;92;17;16m▄\033[38;2;5;4;5;48;2;7;5;6m▄\033[38;2;35;9;9;48;2;45;14;13m▄\033[38;2;177;38;31;48;2;231;44;32m▄\033[38;2;64;10;11;48;2;107;14;15m▄\033[38;2;4;4;4;48;2;5;4;5m▄\033[49m \033[m
\033[49m  \033[48;2;4;4;4m \033[48;2;5;4;5m \033[38;2;58;13;12;48;2;75;42;15m▄\033[38;2;245;177;26;48;2;253;230;16m▄\033[38;2;254;237;15;48;2;254;236;15m▄\033[38;2;254;234;15;48;2;247;138;28m▄\033[38;2;254;233;16;48;2;241;144;32m▄\033[38;2;254;233;16;48;2;242;127;32m▄\033[48;2;254;237;15m \033[38;2;254;237;15;48;2;242;224;15m▄\033[38;2;222;204;18;48;2;87;57;14m▄\033[38;2;105;96;12;48;2;32;9;9m▄\033[38;2;44;11;10;48;2;23;6;7m▄\033[38;2;180;34;26;48;2;8;4;5m▄\033[38;2;98;14;15;48;2;30;7;8m▄\033[38;2;182;23;24;48;2;25;7;7m▄\033[38;2;150;19;20;48;2;45;21;18m▄\033[38;2;150;19;20;48;2;86;39;33m▄\033[38;2;150;19;20;48;2;92;39;32m▄\033[38;2;6;4;5;48;2;174;28;23m▄\033[38;2;57;13;11;48;2;243;56;33m▄\033[38;2;60;14;12;48;2;247;57;34m▄\033[38;2;189;40;32;48;2;240;54;33m▄\033[38;2;58;14;14;48;2;241;46;33m▄\033[38;2;126;104;26;48;2;46;27;24m▄\033[38;2;254;237;15;48;2;244;228;15m▄\033[48;2;254;237;15m \033[38;2;253;231;16;48;2;250;209;20m▄\033[38;2;251;213;19;48;2;239;133;34m▄\033[48;2;239;132;34m   \033[38;2;249;204;21;48;2;239;132;34m▄\033[38;2;254;236;15;48;2;254;237;15m▄\033[38;2;167;101;22;48;2;247;187;24m▄\033[38;2;52;30;13;48;2;181;100;27m▄\033[48;2;48;30;26m \033[38;2;74;45;38;48;2;42;26;23m▄\033[38;2;66;40;34;48;2;45;27;24m▄\033[38;2;120;67;19;48;2;110;61;19m▄\033[38;2;158;87;24;48;2;144;80;24m▄\033[48;2;5;4;5m  \033[38;2;216;33;28;48;2;171;21;22m▄\033[38;2;121;21;18;48;2;109;18;18m▄\033[48;2;5;4;5m \033[49m  \033[m
\033[49m  \033[49;38;2;6;6;6m▀\033[38;2;6;6;6;48;2;6;4;6m▄\033[38;2;5;4;5;48;2;46;8;9m▄\033[38;2;102;56;17;48;2;197;133;24m▄\033[38;2;245;172;27;48;2;250;211;20m▄\033[38;2;254;236;15;48;2;254;237;15m▄\033[48;2;254;237;15m     \033[38;2;253;229;16;48;2;243;218;18m▄\033[38;2;70;48;30;48;2;9;7;6m▄\033[38;2;61;15;13;48;2;185;46;35m▄\033[38;2;225;40;31;48;2;112;27;19m▄\033[38;2;194;27;25;48;2;206;34;28m▄\033[38;2;217;34;29;48;2;232;40;31m▄\033[38;2;201;28;26;48;2;214;33;28m▄\033[38;2;192;24;25;48;2;193;26;25m▄\033[38;2;192;105;28;48;2;117;19;20m▄\033[38;2;194;43;28;48;2;49;28;22m▄\033[38;2;106;43;35;48;2;169;34;26m▄\033[38;2;94;55;32;48;2;148;34;26m▄\033[38;2;245;213;19;48;2;85;74;14m▄\033[38;2;254;237;15;48;2;248;197;22m▄\033[48;2;254;237;15m    \033[38;2;254;237;15;48;2;252;226;17m▄\033[38;2;254;237;15;48;2;252;225;17m▄▄\033[38;2;250;211;20;48;2;254;236;15m▄\033[38;2;203;132;29;48;2;253;235;15m▄\033[38;2;8;6;6;48;2;89;50;16m▄\033[38;2;24;15;14;48;2;22;14;13m▄\033[38;2;73;44;37;48;2;74;45;38m▄\033[38;2;72;44;37;48;2;74;45;38m▄\033[38;2;158;32;21;48;2;30;17;8m▄\033[38;2;94;26;16;48;2;121;64;19m▄\033[38;2;5;4;5;48;2;6;5;6m▄\033[38;2;11;5;6;48;2;5;4;5m▄\033[38;2;144;25;25;48;2;18;12;11m▄\033[38;2;154;22;23;48;2;180;30;26m▄\033[38;2;10;7;7;48;2;20;8;8m▄\033[38;2;4;4;4;48;2;3;3;3m▄\033[49m  \033[m
\033[49m   \033[49;38;2;8;0;8m▀\033[38;2;5;5;5;48;2;5;4;5m▄\033[38;2;5;5;5;48;2;43;23;11m▄\033[38;2;36;27;12;48;2;161;83;23m▄\033[38;2;179;86;30;48;2;244;168;27m▄\033[38;2;247;187;24;48;2;254;237;15m▄\033[38;2;254;234;15;48;2;254;237;15m▄\033[48;2;254;237;15m     \033[38;2;248;226;16;48;2;154;128;19m▄\033[38;2;163;113;21;48;2;99;25;20m▄\033[38;2;58;20;17;48;2;227;43;32m▄\033[38;2;63;21;17;48;2;229;60;31m▄\033[38;2;62;20;17;48;2;218;39;30m▄\033[38;2;53;16;16;48;2;228;40;31m▄\033[38;2;115;80;28;48;2;91;49;20m▄\033[38;2;206;146;23;48;2;85;19;15m▄\033[38;2;253;229;16;48;2;159;117;19m▄\033[38;2;254;237;15;48;2;250;210;20m▄\033[48;2;254;237;15m      \033[38;2;251;213;19;48;2;254;237;15m▄\033[38;2;72;50;12;48;2;254;237;15m▄\033[38;2;89;69;60;48;2;154;141;14m▄\033[38;2;72;46;40;48;2;98;77;19m▄\033[38;2;82;63;59;48;2;130;119;115m▄\033[38;2;82;60;54;48;2;73;59;56m▄\033[38;2;51;31;27;48;2;39;24;21m▄\033[38;2;48;29;26;48;2;24;15;14m▄\033[38;2;57;35;30;48;2;18;11;11m▄\033[38;2;17;12;10;48;2;122;97;30m▄\033[38;2;8;6;6;48;2;16;11;10m▄\033[48;2;5;4;5m \033[38;2;5;4;5;48;2;70;17;13m▄\033[38;2;5;4;5;48;2;96;15;15m▄\033[38;2;4;4;4;48;2;26;7;8m▄\033[49;38;2;5;4;5m▀\033[49;38;2;0;0;0m▀\033[49m  \033[m
\033[49m     \033[49;38;2;0;0;0m▀\033[38;2;4;4;4;48;2;5;4;5m▄\033[38;2;5;3;5;48;2;10;6;6m▄\033[38;2;7;5;5;48;2;149;61;32m▄\033[38;2;33;27;7;48;2;241;156;28m▄\033[38;2;219;89;29;48;2;245;176;26m▄\033[38;2;241;145;32;48;2;254;237;15m▄\033[38;2;251;214;19;48;2;254;237;15m▄\033[48;2;254;237;15m   \033[38;2;254;237;15;48;2;252;235;15m▄\033[38;2;254;237;15;48;2;245;227;16m▄▄▄\033[38;2;254;237;15;48;2;244;227;16m▄\033[38;2;254;237;15;48;2;249;231;16m▄\033[48;2;254;237;15m   \033[38;2;249;203;21;48;2;254;237;15m▄\033[38;2;160;126;16;48;2;254;237;15m▄\033[38;2;60;48;18;48;2;254;237;15m▄\033[38;2;35;33;6;48;2;254;237;15m▄▄\033[38;2;18;14;8;48;2;115;89;32m▄\033[38;2;33;20;18;48;2;16;11;6m▄\033[38;2;75;47;40;48;2;81;57;50m▄\033[38;2;25;18;17;48;2;75;60;56m▄\033[38;2;59;36;31;48;2;17;11;11m▄\033[38;2;14;9;9;48;2;70;43;36m▄\033[38;2;38;23;21;48;2;40;25;22m▄\033[38;2;18;11;11;48;2;20;13;12m▄\033[38;2;10;7;7;48;2;65;40;34m▄\033[38;2;6;5;6;48;2;18;12;11m▄\033[48;2;5;4;5m  \033[38;2;4;4;4;48;2;5;4;5m▄\033[49;38;2;0;0;0m▀▀\033[49m     \033[m
\033[49m        \033[38;2;0;0;0;48;2;5;4;5m▄▄\033[38;2;5;4;5;48;2;7;6;6m▄\033[38;2;5;4;5;48;2;56;11;10m▄\033[38;2;8;6;6;48;2;167;96;24m▄\033[38;2;23;14;8;48;2;220;146;27m▄\033[38;2;36;19;9;48;2;237;129;34m▄\033[38;2;122;69;18;48;2;251;219;18m▄\033[38;2;240;140;32;48;2;253;227;17m▄\033[38;2;241;146;31;48;2;254;237;15m▄▄▄▄▄▄▄▄\033[38;2;108;65;37;48;2;110;83;34m▄\033[38;2;66;54;51;48;2;28;25;25m▄\033[38;2;68;42;35;48;2;191;171;165m▄\033[38;2;28;17;16;48;2;107;84;78m▄\033[38;2;45;28;24;48;2;73;45;38m▄\033[48;2;74;45;38m \033[48;2;39;24;21m \033[38;2;32;20;18;48;2;73;44;37m▄\033[38;2;33;21;19;48;2;29;18;16m▄\033[38;2;24;15;14;48;2;59;36;31m▄\033[38;2;8;6;6;48;2;64;39;33m▄\033[38;2;5;4;5;48;2;33;21;18m▄\033[48;2;5;4;5m  \033[38;2;6;4;6;48;2;5;4;5m▄\033[49;38;2;5;4;5m▀\033[49;38;2;0;0;0m▀\033[49m        \033[m
\033[49m            \033[49;38;2;7;6;6m▀\033[49;38;2;4;4;4m▀▀\033[38;2;6;4;6;48;2;6;5;6m▄\033[38;2;5;4;5;48;2;39;8;9m▄\033[38;2;5;4;5;48;2;111;59;18m▄\033[38;2;5;4;5;48;2;123;69;19m▄▄▄▄▄▄▄\033[38;2;5;4;5;48;2;56;33;21m▄\033[38;2;5;4;5;48;2;19;12;12m▄\033[38;2;5;4;5;48;2;73;44;37m▄\033[38;2;5;4;5;48;2;51;31;27m▄\033[38;2;5;4;5;48;2;38;24;21m▄\033[38;2;5;4;5;48;2;39;24;21m▄\033[38;2;5;4;5;48;2;21;14;13m▄\033[48;2;5;4;5m    \033[38;2;0;0;0;48;2;6;4;6m▄\033[49;38;2;6;4;6m▀\033[49m            \033[m
\033[49m                 \033[49;38;2;5;5;5m▀\033[49;38;2;4;4;4m▀▀▀▀▀▀▀▀\033[49;38;2;5;4;5m▀▀▀\033[49;38;2;5;5;5m▀\033[49;38;2;4;4;4m▀▀\033[49;38;2;5;5;5m▀\033[49m                 \033[m
\033[49m                                                  \033[m

    """
    text = Text.from_ansi(bn)
    
    sub = gradient_text("DuckHunt AI Agent — Terminal Intelligence")
    
    ver_line = Text()
    ver_line.append("  ─ ", style=C_DIM)
    ver_line.append("v2.0.0", style=f"bold {C_PRIMARY}")
    ver_line.append("  •  ", style=C_DIM)
    ver_line.append("● Ready", style=f"bold {C_SUCCESS}")
    ver_line.append("  •  ", style=C_DIM)
    ver_line.append("Powered by DuckTools", style=f"{C_DIM}")
    ver_line.append("  ─", style=C_DIM)
    
    content = Group(
        Align.center(text),
        Text(""),
        Align.center(sub),
        Align.center(ver_line),
    )

    return Panel(
        content,
        border_style=C_BORDER,
        title=f"[bold {C_ACCENT}]◈ System Ready[/bold {C_ACCENT}]",
        subtitle=f"[{C_DIM}]/help for commands[/{C_DIM}]",
        padding=(0, 1),
    )

def animated_startup():
    """Animação de startup com progress bar profissional."""
    startup_steps = [
        ("▸", "Inicializando núcleo", C_PRIMARY),
        ("▸", "Carregando engine de IA", C_SECONDARY),
        ("▸", "Preparando conexões MCP", C_ACCENT),
        ("▸", "Sistema operacional", C_SUCCESS),
    ]
    
    with Live(console=console, refresh_per_second=20) as live:
        completed = []
        for step_idx, (icon, step_text, color) in enumerate(startup_steps):
            for frame_idx in range(8):
                spinner = SPINNER_FRAMES[frame_idx % len(SPINNER_FRAMES)]
                progress_pct = int(((step_idx * 8 + frame_idx) / (len(startup_steps) * 8)) * 100)
                bar_filled = int(progress_pct / 2.5)
                bar = f"[{C_PRIMARY}]{'█' * bar_filled}{'░' * (40 - bar_filled)}[/{C_PRIMARY}] [{C_DIM}]{progress_pct}%[/{C_DIM}]"
                
                lines = Text()
                for done_text, done_color in completed:
                    lines.append(f"  ✓ {done_text}\n", style=f"{done_color} dim")
                lines.append(f"  {spinner} {step_text}...\n", style=f"bold {color}")
                
                display = Group(lines, Text.from_markup(f"  {bar}"))
                live.update(
                    Panel(display, border_style=C_BORDER, expand=False, padding=(0, 2), title=f"[{C_DIM}]Startup[/{C_DIM}]")
                )
                time.sleep(0.04)
            completed.append((step_text, color))
    console.print()

async def adicionar_nova_api():
    console.print(f"\n[bold {C_SECONDARY}]◈ Adicionar Nova API[/bold {C_SECONDARY}]")
    
    tipo = Prompt.ask(
        "[yellow]Escolha o tipo de API[/yellow]", 
        choices=["OpenAI", "Azure", "Anthropic", "Gemini"], 
        default="OpenAI"
    )
    
    novo_modelo = {}
    
    if tipo == "OpenAI":
        modelo = Prompt.ask("[yellow]Nome do modelo (ex: gpt-4o)[/yellow]")
        api_key = Prompt.ask("[yellow]API Key[/yellow]", password=True)
        novo_modelo = {tipo: {"model": modelo, "api_key": api_key}}
        
    elif tipo == "Azure":
        deployment = Prompt.ask("[yellow]Nome do Deployment (ex: gpt-4o)[/yellow]")
        endpoint = Prompt.ask("[yellow]Endpoint com API Version (ex: https://seu-recurso.openai.azure.com/?api_version=2024-08-01-preview)[/yellow]")
        api_key = Prompt.ask("[yellow]API Key[/yellow]", password=True)
        novo_modelo = {tipo: {"deployment": deployment, "endpoint": endpoint, "api_key": api_key}}
        
    elif tipo == "Anthropic":
        modelo = Prompt.ask("[yellow]Nome do modelo (ex: claude-3-5-sonnet-20241022)[/yellow]")
        api_key = Prompt.ask("[yellow]API Key[/yellow]", password=True)
        novo_modelo = {tipo: {"model": modelo, "api_key": api_key}}
        
    elif tipo == "Gemini":
        modelo = Prompt.ask("[yellow]Nome do modelo (ex: gemini-2.0-flash)[/yellow]")
        api_key = Prompt.ask("[yellow]API Key[/yellow]", password=True)
        novo_modelo = {tipo: {"model": modelo, "api_key": api_key}}

    api_cfg_path = os.path.join(MODELS_DIR, "api_config.json")
    data = []
    if os.path.exists(api_cfg_path):
        try:
            with open(api_cfg_path, "r", encoding="utf-8") as f:
                content = json.load(f)
                if isinstance(content, list):
                    data = content
                elif isinstance(content, dict):
                    data = [content]
        except Exception:
            pass
            
    data.append(novo_modelo)
    
    os.makedirs(MODELS_DIR, exist_ok=True)
    with open(api_cfg_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        
    notify_success(f"API '{tipo}' adicionada com sucesso!")

async def gerenciar_modelos(current_llm):
    while True:
        os.makedirs(MODELS_DIR, exist_ok=True)
        modelos = [f for f in os.listdir(MODELS_DIR) if f.lower().endswith(".gguf")]
        
        api_list = []
        api_cfg_path = os.path.join(MODELS_DIR, "api_config.json")
        if os.path.exists(api_cfg_path):
            try:
                with open(api_cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            for k, v in item.items():
                                api_list.append({"type": k, "config": v})
                    elif isinstance(data, dict):
                        for k, v in data.items():
                            api_list.append({"type": k, "config": v})
            except Exception as e:
                console.print(f"[red]Erro ao ler api_config.json: {e}[/red]")

        opcoes = []
        for api in api_list:
            cfg = api["config"]
            name = cfg.get("deployment") or cfg.get("model") or "Unknown"
            opcoes.append({"label": f"[{api['type']}] {name}", "value": api})
        
        for m in modelos:
            if LLAMA_CPP_AVAILABLE:
                opcoes.append({"label": f"[Local] {m}", "value": m})
            else:
                opcoes.append({"label": f"[Local - INDISPONÍVEL] {m} (llama-cpp não instalado)", "value": None})
        
        console.print()
        table = Table(title="⬡ Modelos Disponíveis", title_style=f"bold {C_PRIMARY}", border_style=C_BORDER)
        table.add_column("", justify="center", style=f"bold {C_PRIMARY}", no_wrap=True, width=4)
        table.add_column("Modelo", style=C_TEXT)

        if not opcoes:
            table.add_row("-", f"[{C_DIM}]Nenhum modelo configurado.[/{C_DIM}]")
        else:
            for i, opt in enumerate(opcoes, 1):
                table.add_row(str(i), opt['label'])

        console.print(table)
        console.print(f"  [{C_DIM}][[/{C_DIM}][bold {C_ERROR}]c[/bold {C_ERROR}][{C_DIM}]] Cancelar   [[/{C_DIM}][bold {C_SUCCESS}]a[/bold {C_SUCCESS}][{C_DIM}]] Add API   [[/{C_DIM}][bold {C_WARNING}]e[/bold {C_WARNING}][{C_DIM}]] Editar   [[/{C_DIM}][bold {C_ERROR}]r[/bold {C_ERROR}][{C_DIM}]] Remover[/{C_DIM}]")
        
        escolha = Prompt.ask("\n[yellow]Digite o número do modelo para usar ou a opção desejada (c/a/e/r)[/yellow]").strip().lower()
        if escolha == 'c': return current_llm
        if escolha == 'a':
            await adicionar_nova_api()
            continue
            
        if escolha == 'r' or escolha == 'e':
            if not api_list:
                notify_error("Não há APIs configuradas para alterar.")
                continue
                
            idx_str = Prompt.ask(f"[yellow]Qual ID do modelo deseja {'editar' if escolha == 'e' else 'remover'}?[/yellow]").strip()
            if idx_str.isdigit():
                idx = int(idx_str) - 1
                if 0 <= idx < len(api_list):
                    api_alvo = api_list[idx]
                    if escolha == 'r':
                        api_list.pop(idx)
                        notify_success(f"API removida com sucesso!")
                    else:
                        tipo = api_alvo["type"]
                        cfg = api_alvo["config"]
                        console.print(f"\n[bold #A55EEA]✏️ Editando API {tipo}[/bold #A55EEA]")
                        
                        if tipo == "Azure":
                            cfg["deployment"] = Prompt.ask("[yellow]Nome do Deployment[/yellow]", default=cfg.get("deployment", ""))
                            cfg["endpoint"] = Prompt.ask("[yellow]Endpoint com API Version[/yellow]", default=cfg.get("endpoint", ""))
                            cfg["api_key"] = Prompt.ask("[yellow]API Key[/yellow]", password=True, default=cfg.get("api_key", ""))
                        else:
                            cfg["model"] = Prompt.ask("[yellow]Nome do modelo[/yellow]", default=cfg.get("model", ""))
                            cfg["api_key"] = Prompt.ask("[yellow]API Key[/yellow]", password=True, default=cfg.get("api_key", ""))
                        
                        api_list[idx]["config"] = cfg
                        notify_success(f"API '{tipo}' editada com sucesso!")
                    
                    # Salva alterações de volta no api_config.json
                    nova_lista = [{a["type"]: a["config"]} for a in api_list]
                    with open(api_cfg_path, "w", encoding="utf-8") as f:
                        json.dump(nova_lista, f, indent=4)
                else:
                    notify_error("ID inválido ou não é uma API configurável.")
            continue
            
        if escolha.isdigit() and 0 <= int(escolha) - 1 < len(opcoes):
            selecionado = opcoes[int(escolha) - 1]["value"]
            
            if selecionado is None:
                notify_error("Este modelo local não pode ser carregado pois 'llama-cpp-python' não está instalado.")
                continue

            if current_llm is not None: del current_llm
            
            if isinstance(selecionado, str):
                caminho_modelo = os.path.join(MODELS_DIR, selecionado)
                with Status(f"[cyan]Carregando '{selecionado}' no motor inferência...", console=console, spinner="dots"):
                    try:
                        llama = await asyncio.to_thread(
                            Llama, model_path=caminho_modelo, n_ctx=8192, n_gpu_layers=0, verbose=False
                        )
                        console.print(f"[green]✓ Modelo '{selecionado}' carregado com sucesso![/green]")
                        notify_success(f"Modelo local '{selecionado}' pronto!")
                        save_config("Model", "type", "local")
                        save_config("Model", "name", selecionado)
                        save_config("Model", "path", caminho_modelo)
                        return UnifiedLLM(llama, "local", selecionado)
                    except Exception as e:
                        notify_error(f"Erro ao carregar: {e}")
                        return None
            else:
                tipo = selecionado["type"]
                cfg = selecionado["config"]
                try:
                    if tipo == "Azure":
                        ep = cfg.get("endpoint", "")
                        parsed = urlparse(ep)
                        qs = parse_qs(parsed.query)
                        api_ver = qs.get("api_version", ["2024-08-01-preview"])[0]
                        base_url = f"{parsed.scheme}://{parsed.netloc}" # Azure base
                        
                        client = AzureOpenAI(
                            api_key=cfg.get("api_key"),
                            api_version=api_ver,
                            azure_endpoint=base_url
                        )
                        mdl = cfg.get("deployment")
                        console.print(f"[green]✓ Cliente Azure ('{mdl}') configurado![/green]")
                        notify_success(f"Azure '{mdl}' configurado!")
                        save_config("Model", "type", "azure")
                        save_config("Model", "name", mdl)
                        return UnifiedLLM(client, "azure", mdl)
                    elif tipo == "OpenAI":
                        client = OpenAI(api_key=cfg.get("api_key"))
                        mdl = cfg.get("model")
                        console.print(f"[green]✓ Cliente OpenAI ('{mdl}') configurado![/green]")
                        notify_success(f"OpenAI '{mdl}' configurado!")
                        save_config("Model", "type", "openai")
                        save_config("Model", "name", mdl)
                        return UnifiedLLM(client, "openai", mdl)
                    elif tipo == "Gemini":
                        client = OpenAI(
                            api_key=cfg.get("api_key"),
                            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                        )
                        mdl = cfg.get("model")
                        console.print(f"[green]✓ Cliente Gemini ('{mdl}') configurado![/green]")
                        notify_success(f"Gemini '{mdl}' configurado!")
                        save_config("Model", "type", "gemini")
                        save_config("Model", "name", mdl)
                        return UnifiedLLM(client, "gemini", mdl)
                    elif tipo == "Anthropic":
                        if not ANTHROPIC_AVAILABLE:
                            notify_error("A biblioteca 'anthropic' não está instalada. Execute 'pip install anthropic'.")
                            continue
                        client = anthropic.Anthropic(api_key=cfg.get("api_key"))
                        mdl = cfg.get("model")
                        console.print(f"[green]✓ Cliente Anthropic ('{mdl}') configurado![/green]")
                        notify_success(f"Anthropic '{mdl}' configurado!")
                        save_config("Model", "type", "anthropic")
                        save_config("Model", "name", mdl)
                        return UnifiedLLM(client, "anthropic", mdl)
                except Exception as e:
                    notify_error(f"Erro ao configurar API: {e}")
                    return None
        else:
            console.print("[red]Opção inválida.[/red]")

def autoload_agent():
    fname = load_config("Agent", "filename")
    if fname:
        p = os.path.join(AGENTS_DIR, fname)
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    notify_success(f"Agente '{fname}' restaurado.")
                    return f.read()
            except: pass
    return None

def autoload_skills():
    loaded_str = load_config("Skills", "loaded")
    if not loaded_str: return []
    
    wanted = [x.strip() for x in loaded_str.split(',') if x.strip()]
    restored = []
    
    for root, _dirs, files in os.walk(SKILLS_DIR):
        for f in files:
            if f.lower() == 'skill.md':
                rel = os.path.relpath(root, SKILLS_DIR)
                if rel in wanted:
                    try:
                        path = os.path.join(root, f)
                        skill_root_dir = os.path.abspath(os.path.dirname(path))
                        with open(path, 'r', encoding='utf-8') as f_obj:
                            restored.append({
                                "name": rel,
                                "content": f_obj.read(),
                                "path": skill_root_dir
                            })
                    except: pass
    if restored:
        names = ", ".join([s["name"] for s in restored])
        notify_success(f"Skills restauradas: {names}")
    return restored

async def autoload_model():
    m_type = load_config("Model", "type")
    m_name = load_config("Model", "name")
    
    if not m_type or not m_name: return None
    
    with Status(f"[bold #45B7D1]🤖 Restaurando modelo: {m_name}...[/bold #45B7D1]", console=console, spinner="dots12"):
        try:
            if m_type == "local":
                path = load_config("Model", "path")
                if path and os.path.exists(path):
                    if not LLAMA_CPP_AVAILABLE:
                        notify_error(f"Modelo Local '{m_name}' não pode ser restaurado (llama-cpp não instalado).")
                        return None
                    llama = await asyncio.to_thread(Llama, model_path=path, n_ctx=8192, n_gpu_layers=0, verbose=False)
                    notify_success(f"Modelo Local '{m_name}' restaurado.")
                    return UnifiedLLM(llama, "local", m_name)
            else:
                # APIs: Read api_config.json again to find config
                api_cfg_path = os.path.join(MODELS_DIR, "api_config.json")
                if os.path.exists(api_cfg_path):
                    with open(api_cfg_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        itens = data if isinstance(data, list) else [data]
                        
                        for item in itens:
                            for k, v in item.items():
                                if k.lower() == m_type:
                                    if (v.get("model") == m_name) or (v.get("deployment") == m_name):
                                        if m_type == "azure":
                                            ep = v.get("endpoint", "")
                                            parsed = urlparse(ep)
                                            qs = parse_qs(parsed.query)
                                            api_ver = qs.get("api_version", ["2024-08-01-preview"])[0]
                                            base_url = f"{parsed.scheme}://{parsed.netloc}"
                                            client = AzureOpenAI(api_key=v.get("api_key"), api_version=api_ver, azure_endpoint=base_url)
                                            notify_success(f"Azure '{m_name}' restaurado.")
                                            return UnifiedLLM(client, "azure", m_name)
                                        elif m_type == "openai":
                                            client = OpenAI(api_key=v.get("api_key"))
                                            notify_success(f"OpenAI '{m_name}' restaurado.")
                                            return UnifiedLLM(client, "openai", m_name)
                                        elif m_type == "gemini":
                                            client = OpenAI(
                                                api_key=v.get("api_key"),
                                                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                                            )
                                            notify_success(f"Gemini '{m_name}' restaurado.")
                                            return UnifiedLLM(client, "gemini", m_name)
                                        elif m_type == "anthropic":
                                            if not ANTHROPIC_AVAILABLE:
                                                notify_error(f"Anthropic '{m_name}' não pode ser restaurado (biblioteca anthropic não instalada).")
                                                return None
                                            client = anthropic.Anthropic(api_key=v.get("api_key"))
                                            notify_success(f"Anthropic '{m_name}' restaurado.")
                                            return UnifiedLLM(client, "anthropic", m_name)
        except Exception: pass
    return None

def gerenciar_mcp():
    if not os.path.exists(MCP_CONFIG_PATH):
        notify_error(f"Arquivo de configuração {MCP_CONFIG_PATH} não encontrado.")
        return

    while True:
        with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
            mcp_config = json.load(f)

        console.print("\n[bold #A55EEA]🔌 Gerenciar Servidores MCP[/bold #A55EEA]")
        
        servers = list(mcp_config.get("mcpServers", {}).items())
        
        table = Table(title="Servidores Configurados", title_style="bold #FFC857", border_style="#FFC857")
        table.add_column("ID", justify="center", style="bold #45B7D1", no_wrap=True)
        table.add_column("Nome", style="white")
        table.add_column("Status", style="bold")
        table.add_column("Tipo", style="white")
        
        if not servers:
            table.add_row("-", "Nenhum servidor configurado", "-", "-")
        else:
            for i, (name, cfg) in enumerate(servers, 1):
                status = "[red]Desativado[/red]" if cfg.get("disabled") else "[green]Ativado[/green]"
                typ = cfg.get("type", "stdio" if "command" in cfg else "unknown")
                table.add_row(str(i), name, status, typ)
                
        console.print(table)
        console.print("  [dim][[/dim][bold #FF6B6B]c[/bold #FF6B6B][dim]] Cancelar[/dim]   [dim][[/dim][bold #4ECB71]a[/bold #4ECB71][dim]] Adicionar[/dim]   [dim][[/dim][bold #FFC857]t[/bold #FFC857][dim]] Alternar Status[/dim]   [dim][[/dim][bold #FF6B6B]r[/bold #FF6B6B][dim]] Remover[/dim]")
        
        escolha = Prompt.ask("\n[yellow]Digite a opção desejada (c/a/t/r)[/yellow]").strip().lower()
        if escolha == 'c': break
        
        if escolha == 'a':
            name = Prompt.ask("[yellow]Nome do novo servidor[/yellow]")
            typ = Prompt.ask("[yellow]Tipo (stdio/sse)[/yellow]", choices=["stdio", "sse"], default="stdio")
            
            new_cfg = {"type": typ}
            if typ == "stdio":
                new_cfg["command"] = Prompt.ask("[yellow]Comando (ex: npx, python)[/yellow]")
                args_str = Prompt.ask("[yellow]Argumentos (separados por espaço)[/yellow]")
                new_cfg["args"] = args_str.split() if args_str else []
            else:
                new_cfg["url"] = Prompt.ask("[yellow]URL do servidor SSE[/yellow]")
                
            mcp_config.setdefault("mcpServers", {})[name] = new_cfg
            with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(mcp_config, f, ensure_ascii=False, indent=2)
            notify_success(f"Servidor '{name}' adicionado! (As alterações terão efeito no próximo reinício)")
            
        elif escolha in ('t', 'r'):
            if not servers:
                notify_error("Nenhum servidor para alterar.")
                continue
            idx_str = Prompt.ask("[yellow]Qual ID do servidor?[/yellow]").strip()
            if idx_str.isdigit():
                idx = int(idx_str) - 1
                if 0 <= idx < len(servers):
                    srv_name = servers[idx][0]
                    if escolha == 't':
                        current_status = mcp_config["mcpServers"][srv_name].get("disabled", False)
                        mcp_config["mcpServers"][srv_name]["disabled"] = not current_status
                        with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
                            json.dump(mcp_config, f, ensure_ascii=False, indent=2)
                        notify_success(f"Status do '{srv_name}' alterado! (As alterações terão efeito no próximo reinício)")
                    elif escolha == 'r':
                        del mcp_config["mcpServers"][srv_name]
                        with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
                            json.dump(mcp_config, f, ensure_ascii=False, indent=2)
                        notify_success(f"Servidor '{srv_name}' removido! (As alterações terão efeito no próximo reinício)")
                else:
                    notify_error("ID inválido.")

async def run_multi_agents(llm, tools, workspace_dir, mcp_sessions, mcp_tools, mcp_original_names, agent_prompt_text, skills_prompts):
    animated_separator("Multi-Agent Collaboration", C_SECONDARY)
    
    agentes_nomes = []
    agentes_prompts = []
    
    # Agent color palette for distinct visual identity per agent
    AGENT_COLORS = [C_PRIMARY, C_SECONDARY, C_ACCENT, C_WARNING, C_TOOL, C_HIGHLIGHT]
    AGENT_ICONS  = ["◆", "◇", "▸", "▹", "◈", "◉"]
    
    agentes_files = []
    if os.path.exists(AGENTS_DIR):
        agentes_files = [f for f in os.listdir(AGENTS_DIR) if f.lower().endswith(".md")]
        
    if agentes_files and INQUIRER_AVAILABLE:
        # Legend panel explaining controls
        legend = Text()
        legend.append("  ↑ ↓  ", style=f"bold {C_PRIMARY}")
        legend.append("Navegar entre agentes\n", style=C_TEXT)
        legend.append("  Tab  ", style=f"bold {C_ACCENT}")
        legend.append("Marcar / desmarcar agente\n", style=C_TEXT)
        legend.append("  Enter", style=f"bold {C_SUCCESS}")
        legend.append("  Confirmar seleção\n", style=C_TEXT)
        legend.append("  Esc  ", style=f"bold {C_ERROR}")
        legend.append("Cancelar e voltar ao chat", style=C_TEXT)
        console.print(Panel(
            legend,
            title=f"[bold {C_DIM}]Controles[/bold {C_DIM}]",
            border_style=C_BORDER,
            expand=False,
            padding=(0, 2),
        ))
        
        choices = [{"name": f"  {AGENT_ICONS[i % len(AGENT_ICONS)]} {a.replace('.md', '')}", "value": a} for i, a in enumerate(agentes_files)]
        
        inquirer_ok = False
        try:
            selected = await inquirer.checkbox(
                message="Selecione os agentes para colaboração",
                choices=choices,
                pointer="▸",
                qmark="◈",
                amark="✓",
                enabled_symbol="◉",
                disabled_symbol="○",
                instruction="",
                long_instruction="Tab=marcar  Enter=confirmar  Esc=cancelar",
                mandatory=False,
                raise_keyboard_interrupt=False,
                keybindings={
                    "toggle": [{"key": "tab"}],
                },
                border=True,
            ).execute_async()
            inquirer_ok = True
        except (KeyboardInterrupt, EOFError):
            selected = None
            inquirer_ok = True
        except Exception:
            # prompt_toolkit console error — fall through to table fallback
            inquirer_ok = False
        
        if inquirer_ok:
            if not selected:
                notify_info("Seleção cancelada.")
                return
            for fname in selected:
                nome = fname.replace(".md", "")
                agentes_nomes.append(nome)
                try:
                    with open(os.path.join(AGENTS_DIR, fname), 'r', encoding='utf-8') as f:
                        agentes_prompts.append(f.read())
                except Exception:
                    agentes_prompts.append(agent_prompt_text)
    
    # Fallback: table + text input (when InquirerPy unavailable or console error)
    if not agentes_nomes and agentes_files:
        table = Table(title="◈ Agentes Disponíveis", title_style=f"bold {C_SECONDARY}", border_style=C_BORDER)
        table.add_column("", justify="center", style=f"bold {C_PRIMARY}", no_wrap=True, width=4)
        table.add_column("Agente", style=C_TEXT)
        for i, anome in enumerate(agentes_files, 1):
            table.add_row(str(i), anome.replace(".md", ""))
        console.print(table)
        console.print(f"\n  [{C_DIM}]↑↓ = navegar   Tab = marcar   Enter = confirmar   Esc = cancelar[/{C_DIM}]")
        console.print(f"  [{C_DIM}]Ou digite IDs separados por vírgula (ex: 1,3,5)[/{C_DIM}]")
        
        agentes_input = Prompt.ask(f"\n[{C_SECONDARY}]Agentes[/{C_SECONDARY}]")
        if not agentes_input.strip(): return
        
        for item in agentes_input.split(","):
            item = item.strip()
            if not item: continue
            if item.isdigit() and 0 <= int(item) - 1 < len(agentes_files):
                fname = agentes_files[int(item) - 1]
                nome = fname.replace(".md", "")
                agentes_nomes.append(nome)
                try:
                    with open(os.path.join(AGENTS_DIR, fname), 'r', encoding='utf-8') as f:
                        agentes_prompts.append(f.read())
                except Exception:
                    agentes_prompts.append(agent_prompt_text)
            else:
                agentes_nomes.append(item)
                agentes_prompts.append(agent_prompt_text)
    
    if not agentes_files:
        notify_error("Nenhum agente encontrado.")
        return
            
    n_agents = len(agentes_nomes)
    if n_agents == 0: return
    
    agentes_models = [llm] * n_agents
    
    if INQUIRER_AVAILABLE:
        try:
            same_model = await inquirer.confirm(
                message="Deseja usar o mesmo modelo atual para TODOS os agentes?",
                default=True,
                qmark="◈"
            ).execute_async()
        except Exception:
            same_model = True
    else:
        ans = Prompt.ask(f"[{C_WARNING}]Deseja usar o mesmo modelo atual para TODOS os agentes?[/{C_WARNING}]", choices=["s", "n"], default="s")
        same_model = (ans == "s")

    if not same_model:
        for i, name in enumerate(agentes_nomes):
            animated_separator(f"Modelo para o agente '{name}'")
            chosen_m = await gerenciar_modelos(llm)
            if chosen_m:
                agentes_models[i] = chosen_m
    
    animated_separator("Tarefa")
    task = Prompt.ask(f"[bold {C_WARNING}]Tarefa para a equipe[/bold {C_WARNING}]")
    if not task.strip(): return
    
    duckroom_proc = None
    if load_config("General", "duckroom") == "on":
        import subprocess
        duck_script = os.path.join(BASE_DIR, "modules", "duck_room.py")
        try:
            duckroom_proc = subprocess.Popen(
                [sys.executable, duck_script, "--agent-mode", "--ducks", str(n_agents)], 
                stdin=subprocess.PIPE, 
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True, 
                encoding="utf-8"
            )
            # Envia a tarefa para aparecer no balão central (UI) do Duck Room
            try:
                task_msg = json.dumps({"type": "task", "message": task})
                duckroom_proc.stdin.write(task_msg + "\n")
                duckroom_proc.stdin.flush()
            except Exception as e:
                pass
        except Exception as e:
            notify_error(f"Duck Room: {e}")
        
    from rich.layout import Layout
    
    # Auto-scroll: show only the latest N lines per agent
    terminal_height = console.size.height
    max_visible_lines = max(15, terminal_height - 8)
    
    layout = Layout()
    layout.split_row(*[Layout(name=f"agent_{i}") for i in range(n_agents)])
    
    agent_texts = {i: "" for i in range(n_agents)}
    shared_history = [
        {"role": "user", "content": f"TAREFA PRINCIPAL: {task}\n\nVocês são a seguinte equipe: {', '.join(agentes_nomes)}.\nTrabalhem juntos, discutindo e resolvendo a demanda do usuário. Usem as ferramentas MCP à disposição se precisarem interagir com arquivos.\n\nREGRAS DE COLABORAÇÃO:\n1. NÃO tomem decisões unilaterais fora da sua função. Cada agente tem um papel específico (ex: Product Owner cria/organiza demandas, Dev constrói/executa, QA analisa falhas, etc).\n2. Se você precisa que outro agente faça uma parte do trabalho, FAÇA A PASSAGEM DA TAREFA DE FORMA CLARA, citando o agente que deve assumir e passando o contexto necessário.\n3. Sempre VALIDE seu trabalho antes de declarar conclusão. Dev deve testar, QA deve revisar, PO deve validar requisitos.\n4. Mantenham SINERGIA: cada agente deve complementar o trabalho dos outros, garantindo coesão na entrega final.\n\nIMPORTANTE: Quando a equipe concluir 100% da Tarefa Principal e todos concordarem que nada mais precisa ser feito (o código foi concluído, as validações e entregas feitas), qualquer agente pode simplesmente incluir a palavra-chave exata [TASK_COMPLETED] na sua resposta para encerrar este ciclo de colaboração."}
    ]
    
    def get_layout(round_num=0):
        for i, name in enumerate(agentes_nomes):
            color = AGENT_COLORS[i % len(AGENT_COLORS)]
            icon = AGENT_ICONS[i % len(AGENT_ICONS)]
            txt = agent_texts[i]
            
            # AUTO-SCROLL: keep only the latest visible lines
            lines = txt.split("\n")
            if len(lines) > max_visible_lines:
                txt = f"[{C_DIM}]··· scroll ···[/{C_DIM}]\n" + "\n".join(lines[-max_visible_lines:])
            
            try:
                panel_text = Text.from_markup(txt)
            except Exception:
                panel_text = Text(txt)
                
            panel_text.no_wrap = False
            panel_text.overflow = "fold"
            
            panel = Panel(
                panel_text,
                title=f"[bold {color}]{icon} {name}[/bold {color}]",
                subtitle=f"[{C_DIM}]R{round_num + 1}[/{C_DIM}]",
                border_style=color,
                expand=True,
                padding=(0, 1),
            )
            layout[f"agent_{i}"].update(panel)
        return layout

    with Live(get_layout(), console=console, refresh_per_second=15) as live:
        round_idx = 0
        while True:
            # Cria processos de consumos para cada agente concorrente para rodarem simultaneamente
            streams = []
            for i, name in enumerate(agentes_nomes):
                custom_base_sys = compor_prompt_sistema(agentes_prompts[i], skills_prompts)
                sys_prompt = f"{custom_base_sys}\n\n[Você é o '{name}' nesta rodada da equipe. Lembre-se, use [TASK_COMPLETED] se a missão de todos já estiver concluída e finalizada no projeto.]"
                msgs = [{"role": "system", "content": sys_prompt}]
                msgs.extend(shared_history)
                streams.append(agentes_models[i].create_chat_completion(messages=msgs, tools=tools, tool_choice="auto", max_tokens=2048, stream=True))

            async def consume_stream(i, generator):
                message = {"role": "assistant", "content": "", "tool_calls": []}
                def get_next():
                    try: return next(generator)
                    except StopIteration: return None
                    except Exception as e: return {"error": str(e)}

                while True:
                    chunk = await asyncio.to_thread(get_next)
                    if chunk is None or "error" in chunk: break
                    
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    if "content" in delta and delta["content"]:
                        message["content"] += delta["content"]
                        from rich.markup import escape
                        agent_texts[i] += escape(delta["content"])
                        
                        if duckroom_proc and duckroom_proc.poll() is None:
                            try:
                                msg_json = json.dumps({"duck": i, "message": message["content"]})
                                duckroom_proc.stdin.write(msg_json + "\n")
                                duckroom_proc.stdin.flush()
                            except Exception: pass
                            
                        live.update(get_layout(round_idx))
                        
                    if "tool_calls" in delta and delta["tool_calls"]:
                        for tc_chunk in delta["tool_calls"]:
                            index = tc_chunk.get("index")
                            if index is None:
                                tc_id = tc_chunk.get("id")
                                if tc_id:
                                    found_idx = next((idx_search for idx_search, t in enumerate(message["tool_calls"]) if t.get("id") == tc_id), None)
                                    if found_idx is not None:
                                        index = found_idx
                                    else:
                                        index = len(message["tool_calls"])
                                else:
                                    index = max(0, len(message["tool_calls"]) - 1)
                                    
                            while len(message["tool_calls"]) <= index:
                                message["tool_calls"].append({
                                    "id": "", "type": "function", "function": {"name": "", "arguments": ""}
                                })
                            
                            tc_acc = message["tool_calls"][index]
                            for k, v in tc_chunk.items():
                                if k == "index": continue
                                if k == "function" and isinstance(v, dict):
                                    for fk, fv in v.items():
                                        if fv is not None:
                                            if fk in ["name", "arguments"]:
                                                tc_acc["function"][fk] = tc_acc["function"].get(fk, "") + str(fv)
                                            else:
                                                if isinstance(fv, str):
                                                    tc_acc["function"][fk] = tc_acc["function"].get(fk, "") + fv
                                                else:
                                                    tc_acc["function"][fk] = fv
                                elif v is not None:
                                    if k == "type":
                                        tc_acc[k] = v
                                    elif k == "id":
                                        tc_acc[k] = tc_acc.get(k, "") + str(v)
                                    else:
                                        if isinstance(v, str):
                                            tc_acc[k] = tc_acc.get(k, "") + v
                                        else:
                                            tc_acc[k] = v
                            
                            # Accumulate extra_content for Gemini
                            if "extra_content" in tc_chunk and tc_chunk["extra_content"]:
                                if "extra_content" not in tc_acc or not isinstance(tc_acc["extra_content"], dict): 
                                    tc_acc["extra_content"] = {}
                                if isinstance(tc_chunk["extra_content"], dict):
                                    tc_acc["extra_content"].update(tc_chunk["extra_content"])
                        
                    # Accumulate top-level extra_content for Gemini
                    if "extra_content" in delta and delta["extra_content"]:
                        if "extra_content" not in message or not isinstance(message["extra_content"], dict): 
                            message["extra_content"] = {}
                        if isinstance(delta["extra_content"], dict):
                            message["extra_content"].update(delta["extra_content"])
                            
                # --- FALLBACK: PARSER MANUAL DE TOOL CALL ---
                if not message.get("tool_calls") and "<tool_call>" in message.get("content", ""):
                    if "tool_calls" not in message: message["tool_calls"] = []
                    matches = re.findall(r'<tool_call>(.*?)</tool_call>', message["content"], re.DOTALL | re.IGNORECASE)
                    for match_idx, match in enumerate(matches):
                        clean_match = match.strip()
                        if clean_match.startswith('```json'): clean_match = clean_match[7:]
                        elif clean_match.startswith('```'): clean_match = clean_match[3:]
                        if clean_match.endswith('```'): clean_match = clean_match[:-3]
                        try:
                            tool_data = json.loads(clean_match.strip())
                            if "name" in tool_data and "arguments" in tool_data:
                                message["tool_calls"].append({
                                    "id": f"call_manual_m_{match_idx}",
                                    "type": "function",
                                    "function": {"name": tool_data["name"], "arguments": json.dumps(tool_data["arguments"])}
                                })
                        except json.JSONDecodeError:
                            pass

                if message.get("tool_calls"):
                    for idx_tc, tc in enumerate(message["tool_calls"]):
                        if not tc.get("id"):
                            tc["id"] = f"call_m{i}_{idx_tc}"
                            
                # Limpa tool_calls se for array vazio
                if "tool_calls" in message and not message["tool_calls"]:
                    del message["tool_calls"]
                    
                return message

            tasks = [asyncio.create_task(consume_stream(i, streams[i])) for i in range(n_agents)]
            results = await asyncio.gather(*tasks)

            # Sincroniza e Processa ferramentas (execução sequencial no final do round de cada agente)
            for i, name in enumerate(agentes_nomes):
                res = results[i]
                agent_texts[i] += f"\n\n[{C_DIM}]─── {name} · R{round_idx+1} ───[/{C_DIM}]\n"
                
                ast_msg = {"role": "assistant"}
                
                content_text = res.get("content", "").strip()
                if content_text:
                    ast_msg["content"] = f"[{name} comentou]:\n{content_text}"
                else:
                    ast_msg["content"] = f"[{name} chamou ferramentas]"
                    
                if res.get("tool_calls"):
                    ast_msg["tool_calls"] = res["tool_calls"]
                    
                if "extra_content" in res:
                    ast_msg["extra_content"] = res["extra_content"]
                    
                if ast_msg.get("content") or ast_msg.get("tool_calls"):
                    shared_history.append(ast_msg)
                
                if res.get("tool_calls"):
                    for tc in res["tool_calls"]:
                        tname = tc.get("function", {}).get("name")
                        try:
                            targs = json.loads(tc.get("function", {}).get("arguments", "{}"))
                            agent_texts[i] += f"\n[bold {C_TOOL}]▸ {tname}[/bold {C_TOOL}]"
                            live.update(get_layout(round_idx))
                            
                            target_srv = mcp_tools.get(tname)
                            if target_srv and target_srv in mcp_sessions:
                                sess = mcp_sessions[target_srv]
                                original_tname = mcp_original_names.get(tname, tname)
                                tool_res = await sess.call_tool(original_tname, targs)
                                t_out = "\n".join([c.text for c in tool_res.content if c.type == "text"])
                                agent_texts[i] += f"\n[{C_SUCCESS}]✓ {tname}[/{C_SUCCESS}]\n"
                                shared_history.append({"role": "tool", "name": tname, "content": f"Resultado de {tname}:\n{t_out}", "tool_call_id": tc.get("id")})
                            else:
                                agent_texts[i] += f"\n[{C_ERROR}]✗ {tname}: MCP inativo[/{C_ERROR}]\n"
                                shared_history.append({"role": "tool", "name": tname, "content": f"Erro: MCP inativo", "tool_call_id": tc.get("id")})
                        except Exception as e:
                            agent_texts[i] += f"\n[{C_ERROR}]✗ {tname}: {e}[/{C_ERROR}]\n"
                            shared_history.append({"role": "tool", "name": tname, "content": f"Erro de processamento: {e}", "tool_call_id": tc.get("id")})
                            
            live.update(get_layout(round_idx))
            
            task_completed = any("[TASK_COMPLETED]" in res.get("content", "") for res in results)
            if task_completed:
                break
                
            round_idx += 1
            
    if duckroom_proc and duckroom_proc.poll() is None:
        duckroom_proc.terminate()
        
    notify_success(f"Multi-Agent concluído • {round_idx + 1} rodada(s) • {n_agents} agentes")

async def run_chat_loop():
    animated_startup()
    console.print(banner())
    
    try:
        default_ws = os.getcwd()
        last_ws = load_config("General", "workspace")

        animated_separator("Workspace")
        
        if last_ws and os.path.exists(last_ws):
            use_last = Prompt.ask(f"[bold {C_WARNING}]Usar último workspace[/bold {C_WARNING}] [{C_DIM}]'{last_ws}'[/{C_DIM}]", choices=["s", "n"], default="s")
            if use_last == "s":
                workspace_dir = last_ws
            else:
                user_ws = Prompt.ask(f"[bold {C_WARNING}]Caminho do projeto[/bold {C_WARNING}]", default=default_ws).strip('"')
                workspace_dir = user_ws or default_ws
        else:
            user_ws = Prompt.ask(f"[bold {C_WARNING}]Caminho do projeto[/bold {C_WARNING}]", default=default_ws).strip('"')
            workspace_dir = user_ws or default_ws
        
        save_config("General", "workspace", workspace_dir)
        notify_success(f"Workspace: {workspace_dir}")
    except Exception:
        workspace_dir = os.getcwd()

    if not os.path.exists(MCP_CONFIG_PATH):
        notify_error(f"{MCP_CONFIG_PATH} não encontrado.")
        return

    with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
        mcp_config = json.load(f)

    if "ducktools" in mcp_config.get("mcpServers", {}):
        mcp_config["mcpServers"]["ducktools"].setdefault("env", {})["WORKSPACE_DIR"] = workspace_dir
        with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(mcp_config, f, ensure_ascii=False, indent=2)

    import contextlib

    async with contextlib.AsyncExitStack() as stack:
        mcp_sessions = {}
        mcp_tools = {}
        mcp_original_names = {}
        llama_tools = []

        animated_separator("MCP Protocol")
        
        with Live(console=console, refresh_per_second=20) as live:
            for i in range(12):
                spinner = SPINNER_FRAMES[i % len(SPINNER_FRAMES)]
                msg = Text()
                msg.append(f"  {spinner} ", style=f"bold {C_PRIMARY}")
                msg.append("Conectando aos servidores MCP...", style=C_TEXT)
                live.update(msg)
                await asyncio.sleep(0.06)
        
        with Status(f"[bold {C_PRIMARY}]Inicializando protocolo MCP...[/bold {C_PRIMARY}]", console=console, spinner="dots12"):
            for srv_name, srv_cfg in mcp_config.get("mcpServers", {}).items():
                if srv_cfg.get("disabled", False):
                    continue

                typ = srv_cfg.get("type", "stdio")
                if "command" in srv_cfg and "type" not in srv_cfg: typ = "stdio"

                try:
                    if typ == "stdio":
                        cmd = srv_cfg.get("command", "python")
                        if cmd in ("python", "python.exe", "python3"): cmd = sys.executable
                        env = {**os.environ, **srv_cfg.get("env", {})}
                        params = StdioServerParameters(command=cmd, args=srv_cfg.get("args", []), env=env)
                        read, write = await stack.enter_async_context(stdio_client(params))
                    elif typ in ("http", "sse"):
                        try:
                            from mcp.client.sse import sse_client
                            read, write = await stack.enter_async_context(sse_client(srv_cfg.get("url")))
                        except ImportError:
                            notify_error(f"Não foi possível importar sse_client para {srv_name}.")
                            continue
                    else:
                        notify_error(f"Tipo MCP desconhecido: {typ}")
                        continue

                    session = await stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                    mcp_sessions[srv_name] = session
                    
                    tools_resp = await session.list_tools()
                    for t in tools_resp.tools:
                        safe_name = t.name
                        if safe_name in mcp_tools:
                            safe_name = f"{srv_name}_{safe_name}"
                        mcp_tools[safe_name] = srv_name
                        mcp_original_names[safe_name] = t.name
                        desc = f"[{srv_name}] {t.description}" if safe_name != t.name else t.description
                        llama_tools.append({
                            "type": "function",
                            "function": {"name": safe_name, "description": desc, "parameters": t.inputSchema}
                        })
                except Exception as e:
                    notify_error(f"Erro em {srv_name}: {e}")

        n_tools = len(llama_tools)
        notify_success(f"MCP conectado · {n_tools} ferramentas disponíveis")

        animated_separator("Configurações")
        saved_agent = autoload_agent()
        agent_prompt_text = saved_agent if saved_agent else SYSTEM_PROMPT
        
        skills_prompts = autoload_skills()
        
        messages = [{"role": "system", "content": compor_prompt_sistema(agent_prompt_text, skills_prompts)}]
        llm = None 

        llm = await autoload_model()
        if not llm:
            animated_separator("Modelo")
            llm = await gerenciar_modelos(llm)

        console.print()
        menu_table = Table(box=None, show_header=False, padding=(0, 2))
        menu_table.add_column(style=f"bold {C_PRIMARY}")
        menu_table.add_column(style=C_TEXT)
        menu_table.add_row("⬡ /models",       "Gerenciar modelos de IA")
        menu_table.add_row("⬡ /multi",        "Modo multi-agentes colaborativo")
        menu_table.add_row("⬡ /agents",       "Carregar agente personalizado")
        menu_table.add_row("⬡ /skills",       "Gerenciar skills")
        menu_table.add_row("⬡ /mcp",          "Gerenciar Servidores MCP")
        menu_table.add_row("⬡ /server",       "Iniciar servidor de API")
        menu_table.add_row("⬡ /workspace",    "Alterar diretório do projeto")
        menu_table.add_row("⬡ /duckroom",     "Duck Room (on/off)")
        menu_table.add_row("↻ /new",          "Reiniciar conversa")
        menu_table.add_row("↩ /undo",         "Desfazer última ação do modelo")
        menu_table.add_row("? /help",         "Lista de comandos")
        menu_table.add_row("✗ /sair",         "Encerrar")

        console.print(Panel(
            menu_table,
            title=f"[bold {C_ACCENT}]Comandos[/bold {C_ACCENT}]",
            border_style=C_BORDER,
            expand=False,
            padding=(1, 2),
        ))
        
        model_name = llm.model_name if llm else None
        agent_file = load_config("Agent", "filename")
        status_bar(model_name, agent_file, skills_prompts if skills_prompts else None)

        # 4. LOOP INFINITO DO CHAT
        while True:
            try:
                console.print()
                animated_separator(style="dim")
                
                from datetime import datetime
                ts = datetime.now().strftime("%H:%M")
                user_input = Prompt.ask(f"[{C_DIM}]{ts}[/{C_DIM}] [bold {C_PRIMARY}]Você[/bold {C_PRIMARY}] [bold {C_ACCENT}]›[/bold {C_ACCENT}]")
                cmd = user_input.strip().lower()
                
                if cmd in ['/sair', '/exit', '/quit', 'sair', 'exit', 'quit']:
                    console.print()
                    farewell = gradient_text("◈ Encerrando DuckHunt — Até logo!")
                    console.print(Align.center(farewell))
                    console.print()
                    break
                if cmd == '/server':
                    return "START_SERVER"
                if cmd in ['/models', '/model', '/modelo']:
                    animated_separator("Modelo")
                    llm = await gerenciar_modelos(llm)
                    model_name = llm.model_name if llm else None
                    status_bar(model_name, load_config("Agent", "filename"), skills_prompts if skills_prompts else None)
                    continue
                if cmd in ['/agents', '/agent', '/agente']:
                    animated_separator("Agente")
                    novo_prompt = await gerenciar_agentes(agent_prompt_text)
                    if novo_prompt != agent_prompt_text:
                        agent_prompt_text = novo_prompt
                        messages = [{"role": "system", "content": compor_prompt_sistema(agent_prompt_text, skills_prompts)}]
                        notify_info("Contexto reiniciado com o novo agente.")
                    continue
                if cmd == '/mcp':
                    gerenciar_mcp()
                    continue
                if cmd in ['/skills', '/skill']:
                    animated_separator("Skills")
                    resultado = await gerenciar_skills(current_skills=skills_prompts)
                    if resultado == "CLEAR":
                        skills_prompts = []
                        messages = [{"role": "system", "content": compor_prompt_sistema(agent_prompt_text, skills_prompts)}]
                        notify_info("Skills removidas. Contexto reiniciado.")
                    elif resultado:
                        existentes = {s.get("name") for s in skills_prompts}
                        for sk in resultado:
                            if sk.get("name") not in existentes:
                                skills_prompts.append(sk)
                        messages = [{"role": "system", "content": compor_prompt_sistema(agent_prompt_text, skills_prompts)}]
                        notify_success("Contexto atualizado com novas skills.")
                    continue
                
                if cmd in ['/multi']:
                    await run_multi_agents(llm, llama_tools, workspace_dir, mcp_sessions, mcp_tools, mcp_original_names, agent_prompt_text, skills_prompts)
                    continue
                
                if cmd == '/new':
                    messages = [{"role": "system", "content": compor_prompt_sistema(agent_prompt_text, skills_prompts)}]
                    notify_info("Chat reiniciado.")
                    continue
                
                if cmd in ['/duckroom on', '/duckroom off']:
                    if cmd == '/duckroom on':
                        save_config("General", "duckroom", "on")
                        notify_success("Duck Room ativado para o modo multi-agentes!")
                    else:
                        save_config("General", "duckroom", "off")
                        notify_success("Duck Room desativado.")
                    continue
                
                if cmd in ['/undo', '/rollback']:
                    sucesso, msg_status = rollback_checkpoint(workspace_dir)
                    if sucesso:
                        notify_success(msg_status)
                    else:
                        notify_error(msg_status)
                    continue
                
                if cmd == '/workspace':
                    novo_ws = Prompt.ask(f"[bold {C_WARNING}]Novo caminho do projeto[/bold {C_WARNING}]", default=workspace_dir).strip('"')
                    if novo_ws and os.path.exists(novo_ws):
                        workspace_dir = novo_ws
                        save_config("General", "workspace", workspace_dir)
                        notify_success(f"Workspace alterado para: {workspace_dir}")
                        
                        if "ducktools" in mcp_config.get("mcpServers", {}):
                            mcp_config["mcpServers"]["ducktools"].setdefault("env", {})["WORKSPACE_DIR"] = workspace_dir
                            with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
                                json.dump(mcp_config, f, ensure_ascii=False, indent=2)
                            notify_info("A mudança no ducktools terá efeito no próximo reinício da aplicação.")
                    elif novo_ws:
                        notify_error(f"Diretório '{novo_ws}' não encontrado.")
                    continue
                
                if cmd == '/help':
                    console.print(Panel(
                        menu_table,
                        title=f"[bold {C_ACCENT}]Comandos[/bold {C_ACCENT}]",
                        border_style=C_BORDER,
                        expand=False,
                        padding=(1, 2),
                    ))
                    continue

                if not user_input.strip(): continue
                if llm is None:
                    notify_error("Nenhum modelo carregado! Use /models.")
                    continue

                # Cria checkpoint silencioso antes de processar a chamada do modelo
                create_checkpoint(workspace_dir)

                # Processa referências a arquivos (ex: #arquivo.txt)
                file_refs = re.findall(r'(?:^|[\s\(\[\{])#([a-zA-Z0-9_\-\.\/\\]+)', user_input)
                if file_refs:
                    contextos = []
                    for ref in set(file_refs):
                        file_path = os.path.join(workspace_dir, ref)
                        if os.path.isfile(file_path):
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    conteudo = f.read()
                                contextos.append(f"--- Conteúdo de {ref} ---\n{conteudo}\n--- Fim de {ref} ---")
                                notify_info(f"Arquivo referenciado '{ref}' incluído no contexto.")
                            except Exception as e:
                                notify_error(f"Erro ao ler '{ref}': {e}")
                    
                    if contextos:
                        user_input += "\n\n[Referências de Arquivos Anexadas Pelo Sistema]\n" + "\n\n".join(contextos)

                messages.append({"role": "user", "content": user_input})

                # LOOP DE RACIOCÍNIO E FERRAMENTAS
                while True:
                    # Built-in tools para o AI
                    ai_tools = list(llama_tools)
                    ai_tools.append({
                        "type": "function",
                        "function": {
                            "name": "load_duckhunt_skill",
                            "description": "Loads a specific DuckHunt skill into your current context. Call this when the user needs specialized knowledge or integrations (e.g., payment gateways) that are listed in your AVAILABLE SKILLS.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "skill_name": {
                                        "type": "string",
                                        "description": "The exact name of the skill to load (e.g. 'abacate-pay')"
                                    }
                                },
                                "required": ["skill_name"]
                            }
                        }
                    })
                    
                    # Executa a geração em uma thread para não bloquear o Asyncio
                    message = await asyncio.to_thread(stream_and_accumulate, llm, messages, ai_tools)
                    messages.append(message) 
                    
                    if "tool_calls" not in message:
                        break
                    
                    # Processa as ferramentas com visual aprimorado
                    for tool_call in message["tool_calls"]:
                        tool_name = tool_call["function"]["name"]
                        tool_args = json.loads(tool_call["function"]["arguments"])
                        
                        tool_display = Text()
                        tool_display.append("▸ ", style=f"bold {C_TOOL}")
                        tool_display.append(tool_name, style=f"bold {C_WARNING}")
                        tool_display.append(f"\n{json.dumps(tool_args, indent=2, ensure_ascii=False)[:300]}", style=C_DIM)
                        console.print(Panel(
                            tool_display,
                            title=f"[bold {C_TOOL}]Tool Execution[/bold {C_TOOL}]",
                            border_style=C_TOOL,
                            expand=False,
                            padding=(0, 1),
                        ))
                        
                        # Animação de processamento
                        with Live(console=console, refresh_per_second=12) as live:
                            task_done = False
                            frame_idx = 0
                            
                            async def run_tool():
                                nonlocal task_done
                                try:
                                    if tool_name == "load_duckhunt_skill":
                                        req_skill = tool_args.get("skill_name")
                                        if not req_skill:
                                            return "Error: skill_name not provided."
                                        if any(s.get("name") == req_skill for s in skills_prompts):
                                            return f"Skill '{req_skill}' is already loaded in your context."
                                            
                                        sucesso = load_skill_by_name(req_skill, skills_prompts)
                                        if sucesso:
                                            messages[0]["content"] = compor_prompt_sistema(agent_prompt_text, skills_prompts)
                                            notify_success(f"Skill '{req_skill}' ativada dinamicamente pelo modelo.")
                                            return f"Success: Skill '{req_skill}' has been loaded. Its instructions are now available in your system prompt."
                                        else:
                                            return f"Error: Skill '{req_skill}' not found or failed to load."
                                            
                                    target_srv = mcp_tools.get(tool_name)
                                    if not target_srv or target_srv not in mcp_sessions:
                                        return f"Erro: Servidor MCP para a ferramenta '{tool_name}' não encontrado."
                                    sess = mcp_sessions[target_srv]
                                    original_tname = mcp_original_names.get(tool_name, tool_name)
                                    result = await sess.call_tool(original_tname, tool_args)
                                    return "\n".join([c.text for c in result.content if c.type == "text"])
                                except Exception as e:
                                    return f"Erro: {str(e)}"
                                finally:
                                    task_done = True
                            
                            tool_task = asyncio.create_task(run_tool())
                            
                            while not task_done:
                                spinner = SPINNER_FRAMES[frame_idx % len(SPINNER_FRAMES)]
                                anim_text = Text()
                                anim_text.append(f"  {spinner} ", style=f"bold {C_PRIMARY}")
                                anim_text.append("Processando...", style=f"{C_DIM} italic")
                                live.update(anim_text)
                                frame_idx += 1
                                await asyncio.sleep(0.08)
                            
                            tool_result_text = await tool_task
                        
                        if tool_result_text.startswith("Erro:"):
                            notify_error(tool_result_text)
                        else:
                            console.print(f"  [bold {C_SUCCESS}]✓[/bold {C_SUCCESS}] [{C_DIM}]Concluído[/{C_DIM}]")

                        messages.append({"role": "tool", "name": tool_name, "content": tool_result_text, "tool_call_id": tool_call["id"]})

            except KeyboardInterrupt:
                console.print("\n[dim italic]Operação cancelada. Digite '/sair' para encerrar.[/dim italic]")
            except Exception as e:
                notify_error(f"Erro inesperado: {str(e)}")

if __name__ == "__main__":
    start_server = False
    try:
        result = asyncio.run(run_chat_loop())
        if result == "START_SERVER":
            start_server = True
    except KeyboardInterrupt:
        console.print()
        farewell = gradient_text("◈ Encerrando DuckHunt — Até logo!")
        console.print(Align.center(farewell))
        console.print()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        notify_error(f"Erro fatal: {e}")
        if hasattr(e, "exceptions"):
            for i, ex in enumerate(e.exceptions, 1):
                console.print(f"[red]  -> {i}. {ex}[/red]")
    finally:
        if start_server:
            import subprocess
            import sys
            console.print("\n[bold #4ECB71]🚀 Iniciando Uvicorn para DuckHunt API Server em http://0.0.0.0:8000[/bold #4ECB71]")
            console.print("[dim italic]Pressione Ctrl+C para encerrar[/dim italic]\n")
            try:
                subprocess.run([sys.executable, "-m", "uvicorn", "duckhunt_api:api_app", "--host", "0.0.0.0", "--port", "8000"])
            except KeyboardInterrupt:
                pass
        try:
            import sys
            sys.exit(0)
        except SystemExit:
            pass