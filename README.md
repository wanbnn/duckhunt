# DuckHunt - [CLI]
![hg](https://img.shields.io/badge/-HuggingFace-FDEE21?style=for-the-badge&logo=HuggingFace&logoColor=black)
![python](https://img.shields.io/badge/Python-FFD43B?style=for-the-badge&logo=python&logoColor=black)

Bem-vindo ao DuckHunt! Este é um projeto focado em interações via CLI (Command Line Interface), envolvendo capacidades de Model Context Protocol (MCP), LLMs, modelos locais ou remotos (como a OpenAI/Azure) e agentes autônomos.

Este projeto foi projetado para ser inicializado da maneira mais fácil possível. Nós incluímos scripts automatizados para ambiente Windows e Linux que cuidam da criação de ambientes virtuais (`.venv`) e da instalação de todos os pacotes necessários, para que você possa iniciar a aplicação sem dores de cabeça.

![Demo](output.gif)

---

## � Integração com Projetos Externos (API)

O DuckHunt agora pode ser usado como um **servidor de API compatível com OpenAI**! Isso permite que você o integre facilmente em seus projetos **Python** e **Node.js** sem precisar lidar com múltiplos SDKs (Anthropic, Gemini, Azure) ou implementar chamadas de ferramentas MCP manualmente. O DuckHunt gerencia tudo para você.

Veja o guia completo de integração em [INTEGRACAO.md](INTEGRACAO.md).

---

## �🛠️ Pré-requisitos (O que instalar antes de tudo)

Antes de executar os scripts automatizados, você precisa apenas garantir que o básico está no seu sistema.

### Windows
1. **Python**: É obrigatório ter o [Python](https://www.python.org/downloads/) (versão 3.8+ recomendada) instalado no seu sistema. *Lembre-se de marcar a opção "Add Python to PATH" durante a instalação do Python.*
> **Nota para compilação C/C++**: A dependência `llama-cpp-python` requer compilação. No Windows, você não precisa instalar ferramentas de compilação adicionais, pois o nosso arquivo `start.bat` já está programado para utilizar os binários embutidos na pasta `mingw64` fornecida com o projeto, configurando tudo de forma transparente.

### Linux
No Linux, além do Python, você precisa garantir a instalação dos pacotes de `venv` (ambientes virtuais) e dos compiladores básicos para que os pacotes em C/C++ (como o `llama-cpp-python`) sejam instalados com sucesso. 

Para distribuições baseadas em **Debian/Ubuntu**, execute o seguinte comando no terminal:
```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip build-essential
```
*(O pacote `build-essential` fornece o `gcc` e `g++` necessários para as extensões de compilação).*

---

## 🚀 Como Instalar e Rodar (Automatizado)

Os arquivos `start.bat` e `start.sh` foram criados para fazer todo o trabalho por você. Eis como utilizá-los:

### No Windows (Usando `start.bat`)

O arquivo **`start.bat`** verifica automaticamente a existência do ambiente virtual. Se este for o primeiro uso, ele criará a pasta `.venv`, instalará os itens listados em `requirements.txt` e iniciará o DuckHunt.

**Como usar:**
1. Navegue até a pasta do projeto.
2. Dê dois cliques em `start.bat`.
3. **Ou**, se preferir usar o terminal (`CMD` ou `PowerShell`), digite:
   ```cmd
   .\start.bat
   ```

> **Sempre que você fechar e quiser abrir novamente**, basta executar o `start.bat`. Ele identificará que o `.venv` já existe e pulará direto para a execução (`app.py`), tornando a inicialização instantânea!

### No Linux (Usando `start.sh`)

O funcionamento do **`start.sh`** é equivalente ao do Windows. Ele cria o `.venv`, baixa e instala dependências e executa o `app.py`.

**Como usar:**
1. Abra um terminal na pasta do projeto.
2. Dê permissão de execução ao script (necessário apenas na primeira vez):
   ```bash
   chmod +x start.sh
   ```
3. Rode o script:
   ```bash
   ./start.sh
   ```

> **Nota:** Assim como no Windows, rodar o `start.sh` na segunda vez será muito mais rápido, ele apenas ativará o ambiente virtual e executará o `app.py`.

---

## 📁 Principais Extensões e Configurações

A pasta do projeto contém arquivos onde você pode personalizar o seu ambiente:

- **`config.ini`**: Configuração global (workspace, tipo de modelo utilizado – como `azure`, `openai` ou `local`, scripts do agente).
- **`app.py`**: Arquivo principal que engatilha a CLI.
- **`models/api_config.json`**: Use para credenciais e endpoints da API.
- **`mcp/config.json`**: Configurações de servidores externos e ferramentas (Model Context Protocol).
- **`skills/` & `agents/`**: Diretórios com as lógicas customizadas dos agentes no DuckHunt.

---

## 🦙 Adicionando Modelos Locais (GGUF)

Como o DuckHunt suporta o **llama-cpp-python**, você pode rodar modelos locais localizados inteiramente na sua máquina que estiverem no formato `.gguf`. 

**Passo a passo:**
1. Baixe o modelo que deseja (ex: do [HuggingFace](https://huggingface.co/)) que possua a extensão `.gguf`.
2. Coloque o arquivo `.gguf` dentro da pasta raiz **`models/`** do projeto (ex: `c:\duckhunt\models\meumodelo.gguf`).
3. Abra o arquivo **`config.ini`** na raiz do projeto.
4. Localize a seção `[Model]` e altere as propriedades para apontar para o seu modelo local:
   ```ini
   [Model]
   type = local
   name = meumodelo.gguf
   ```
Ou simplesmente escreva /models no chat do DuckHunt para selecionar o modelo local.

Ao fazer isso, a próxima vez que você iniciar o DuckHunt, o `app.py` tentará carregar o modelo correspondente utilizando o llama-cpp sem depender de conexões cloud!

---

### Dependências instaladas (em Background)
Os scripts instalarão sob a pasta `.venv` pacotes cruciais como:
- `rich` (Para uma Interface de Linha de Comando bonita)
- `llama-cpp-python` (Para chamadas ao modelo LLM local usando C++)
- `openai` (Para chamadas de API cloud)
- `mcp` (Protocolo de uso de ferramentas do Agente)
