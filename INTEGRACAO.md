# 🦆 Integrando o DuckHunt em Seus Projetos

O DuckHunt foi projetado para ser facilmente integrado a qualquer projeto **Python** ou **Node.js**. Em vez de precisar recriar a lógica de conexão com LLMs, carregamento de agentes e chamadas do protocolo MCP, o DuckHunt atua como um servidor API compatível com o formato da **OpenAI**. 

Isso significa que você pode usar as bibliotecas padrão que já conhece (`openai` no Python ou Node.js), e o DuckHunt fará a "mágica" nos bastidores: ele gerenciará o modelo selecionado (seja GPT, Claude, Gemini ou Local) e executará as ferramentas MCP de forma autônoma (Agent Loop) antes de retornar a resposta final para a sua aplicação.

---

## 🚀 1. Iniciando a API do DuckHunt

Antes de conectar seu projeto, você precisa configurar um modelo rodando o DuckHunt interativamente e depois iniciar o servidor API.

1. Abra o terminal e rode `python app.py`.
2. Configure um modelo com `/models` e feche o app.
3. Inicie o servidor API rodando:

```bash
uvicorn duckhunt_api:api_app --host 0.0.0.0 --port 8000
```
O servidor agora estará rodando na porta `8000` (ex: `http://localhost:8000/v1`).

---

## 🐍 2. Integração com Projetos Python

Para projetos Python, basta utilizar a biblioteca oficial da `openai` e alterar o parâmetro `base_url` para apontar para o DuckHunt.

### Instalação

```bash
pip install openai
```

### Exemplo de Código

```python
from openai import OpenAI

# Inicializa o cliente apontando para a API local do DuckHunt
client = OpenAI(
    api_key="sk-duckhunt", # A chave não importa, o DuckHunt gerencia isso
    base_url="http://localhost:8000/v1"
)

def perguntar_ao_duckhunt():
    response = client.chat.completions.create(
        model="duckhunt-agent", # O modelo real configurado no app.py será utilizado
        messages=[
            {"role": "user", "content": "Verifique o arquivo README.md do meu projeto e faça um resumo."}
        ],
        stream=True
    )

    print("DuckHunt: ", end="", flush=True)
    for chunk in response:
        if chunk.choices[0].delta.content is not None:
            print(chunk.choices[0].delta.content, end="", flush=True)

if __name__ == "__main__":
    perguntar_ao_duckhunt()
```

O DuckHunt irá receber a requisição, executar ferramentas (como ler o arquivo localmente via MCP), processar tudo com o LLM, e quando estiver pronto, devolverá o resumo em formato de texto para o seu código.

---

## 🟢 3. Integração com Projetos Node.js

Para projetos Node.js, TypeScript ou React/Next.js (server-side), o processo é idêntico. Basta usar o SDK oficial da `openai` apontando para o servidor do DuckHunt.

### Instalação

```bash
npm install openai
```

### Exemplo de Código

```javascript
import { OpenAI } from 'openai';

// Inicializa o cliente apontando para a API local do DuckHunt
const openai = new OpenAI({
  apiKey: 'sk-duckhunt', // A chave é ignorada pelo servidor local
  baseURL: 'http://localhost:8000/v1',
});

async function perguntarAoDuckhunt() {
  console.log("Aguardando resposta do DuckHunt...");
  
  const response = await openai.chat.completions.create({
    model: 'duckhunt-agent', // O modelo real é gerenciado pelo servidor
    messages: [
      { role: 'user', content: 'Use suas ferramentas para verificar o clima e me dizer se devo levar guarda-chuva hoje.' }
    ],
    stream: false, // Pode usar stream: true se preferir
  });

  console.log("DuckHunt:", response.choices[0].message.content);
}

perguntarAoDuckhunt();
```

---

## 💡 Por que usar dessa forma?

1. **Abstração Total:** Seu projeto principal não precisa saber nada sobre ferramentas, MCP, prompts complexos ou tokens do Anthropic/Gemini/Azure. Seu código apenas envia a pergunta e recebe a resposta pronta.
2. **Flexibilidade de Modelos:** O usuário da sua aplicação pode usar o `app.py` para trocar o modelo base do agente de GPT-4o para Llama 3 local a qualquer momento. Seu código fonte em Node/Python **não precisará de nenhuma alteração**.
3. **Agent Loop Integrado:** O endpoint `/v1/chat/completions` já cuida de interceptar as "tool_calls", chamar o servidor MCP e devolver para o LLM. A API final só responderá quando o agente tiver concluído sua tarefa.
