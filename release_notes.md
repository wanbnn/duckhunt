# DuckHunt v2.0.0 — Release Notes

## 🎨 Visual Overhaul Completo

### Nova Paleta de Cores — Enterprise Dark-Mode
A paleta visual foi completamente redesenhada, substituindo as cores vibrantes e "infantis" (vermelho, amarelo, verde primários) por uma estética **profissional escura** inspirada em IDEs modernas como Tokyo Night:

| Antes (v1.x)          | Agora (v2.0.0)                  | Uso                  |
|------------------------|----------------------------------|----------------------|
| `#FF6B6B` (vermelho)  | `#7AA2F7` (azul suave)           | Ações primárias      |
| `#FF8E53` (laranja)   | `#9D7CD8` (roxo muted)          | Agentes/secundário   |
| `#FFC857` (amarelo)   | `#73DACA` (teal)                 | Sucesso/confirmação  |
| `#4ECB71` (verde)     | `#E0AF68` (âmbar quente)        | Avisos               |
| `#6C5CE7` (roxo)      | `#F7768E` (rosa suave)          | Erros                |
| emojis coloridos       | ícones geométricos (◈ ◆ ▸ ⬡)   | Menu/navegação       |

### Layout Profissional
- **Separadores limpos** com caractere `─` ao invés de linhas genéricas
- **Painéis com bordas sutis** usando `#3B4261` ao invés de cores gritantes
- **Tipografia consistente** com hierarquia visual clara (primary, dim, text)
- **Status bar refinada** com labels `MODEL`, `AGENT`, `SKILLS` em caps
- **Menu de comandos** usando ícones geométricos ao invés de emojis

---

## ⌨️ Navegação por Teclado (InquirerPy)

### Seleção de Agente
- **Antes:** Digitar número manualmente
- **Agora:** Navegar com `↑↓` setas, selecionar com `Enter`
- Indicador visual `▸` mostra a opção selecionada
- Separador visual entre opções e cancelar

### Seleção de Skills
- **Antes:** Digitar IDs separados por vírgula
- **Agora:** Checkbox interativo com `Space` para marcar/desmarcar, `Enter` para confirmar
- Suporte à seleção múltipla com feedback visual `☑`

### Seleção de Agentes Multi-Agent
- **Antes:** Digitar IDs manualmente
- **Agora:** Checkbox com ícones distintos por agente e navegação por setas
- Cada agente ganha uma cor e ícone únicos para identidade visual

> **Nota:** Se `InquirerPy` não estiver disponível, o fallback numérico continua funcionando.

---

## 🤖 Multi-Agent — Melhorias no Chat

### Auto-Scroll
- O painel de cada agente agora **rola automaticamente** para sempre exibir as linhas mais recentes
- Indicador visual `··· scroll ···` quando o conteúdo é truncado
- O número de linhas visíveis se adapta ao tamanho do terminal (`terminal_height - 8`)

### Identidade Visual por Agente
- Cada agente recebe uma **cor e ícone distintos** do palette de 6 variações:
  - `◆` Azul, `◇` Roxo, `▸` Teal, `▹` Âmbar, `◈` Laranja, `◉` Violeta
- Bordas dos painéis seguem a cor do respectivo agente

### Indicador de Rodada
- Cada painel agora mostra `R1`, `R2`, etc. no subtítulo
- Separadores entre rodadas: `─── Agente · R1 ───`

### Sinergia entre Agentes
- Novas regras de colaboração no prompt dos agentes:
  1. Validação obrigatória antes de declarar conclusão
  2. Cada agente deve complementar o trabalho dos outros
  3. Dev testa, QA revisa, PO valida requisitos
  4. Passagem de tarefa clara entre agentes

### Conclusão Profissional
- Mensagem final inclui contagem de rodadas e agentes:
  `✓ Multi-Agent concluído • 3 rodada(s) • 4 agentes`

---

## 🔄 Animações Melhoradas

### Startup
- **Antes:** Pato andando com emoji por cada step
- **Agora:** Progress bar com percentual, spinner `⠋⠙⠹`, checkmarks `✓` conforme avança
- Painel com borda, título "Startup", e todos os steps anteriores visíveis como concluídos

### Execução de Ferramentas
- **Antes:** Emoji de pato andando
- **Agora:** Spinner de dots unicode (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`) com texto muted
- Apresentação clean e profissional

### Conexão MCP
- **Antes:** Pato andando
- **Agora:** Spinner de dots com texto "Conectando aos servidores MCP..."
- Mensagem de conclusão: `✓ MCP conectado · N ferramentas disponíveis`

---

## 📋 Outras Melhorias

### Notificações
- `✓` para sucesso (em vez de ✅ emoji)
- `✗` para erro (em vez de ❌ emoji)
- `›` para informações (em vez de 💡 emoji)
- Bordas dos painéis seguem a paleta profissional

### Versão
- Atualizada para `v2.0.0`
- Badge de versão na banner com cores da nova paleta

### Dependência Adicionada
- `InquirerPy` adicionado ao `requirements.txt`
  - Habilita seleção por setas e checkboxes no terminal
  - Instalação: `pip install InquirerPy`

---

## Resumo de Mudanças por Arquivo

| Arquivo            | Alterações                                             |
|--------------------|--------------------------------------------------------|
| `app.py`           | Paleta de cores, InquirerPy, multi-agent UI, animações |
| `requirements.txt` | Adicionado `InquirerPy`                                |
| `release_notes.md` | Este documento                                         |

---

*DuckHunt v2.0.0 — Professional Terminal Intelligence*
