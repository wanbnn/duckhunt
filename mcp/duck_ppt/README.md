# PowerPoint Automator MCP Server

Este é um servidor MCP (Model Context Protocol) utilizando transporte `stdio` desenvolvido para automatizar a criação e manipulação de apresentações do Microsoft PowerPoint no Windows usando a biblioteca `win32com.client`.

Com ele, você pode automatizar a criação de slides completos, adicionando textos, formas, gráficos interativos baseados em dados do Excel, e aplicar temas/layouts de forma programática.

## Pré-requisitos

1. **Sistema Operacional:** Windows.
2. **Microsoft Office:** O Microsoft PowerPoint (e preferencialmente o Excel, caso utilize a ferramenta de gráficos) precisa estar instalado na máquina host, pois a biblioteca `win32com` realiza *interop* com a aplicação desktop.
3. **Pacotes Python:** Você precisará do `pywin32` além do `mcp`.

### Instalação das dependências

No diretório raiz ou ambiente virtual do seu projeto, execute:

```bash
pip install pywin32 mcp
```

## Configuração do `mcp/config.json`

Para utilizar o servidor no seu cliente MCP (como o VS Code Claude, etc.), você deve registrá-lo no arquivo `config.json`. 

Exemplo de configuração:

```json
{
  "mcpServers": {
    "duck_ppt": {
      "command": "python",
      "args": ["mcp/duck_ppt/server.py"],
      "env": {}
    }
  }
}
```

## Ferramentas Disponíveis (`Tools`)

O servidor expõe as seguintes ferramentas para criar suas automações com PowerPoint:

### `list_templates()`
Lista todos os templates disponíveis (`.pptx`, `.potx`, `.thmx`) salvos na pasta `mcp/duck_ppt/templates`. Você deve escolher um desses templates para criar uma nova apresentação.

### `create_presentation(template_name: str)`
Abre o PowerPoint e cria uma nova apresentação **baseada no template escolhido** da pasta `templates`. Nunca cria apresentações vazias; você sempre precisa fornecer um nome de arquivo válido de template listado em `list_templates()`.

### `get_presentation_info()`
Retorna a quantidade total de slides que a apresentação atual (template aberto) possui.

### `get_slide_info(slide_index: int)`
Lê um slide específico e retorna os nomes das "Shapes" (caixas de texto, títulos) que possuem texto escrito. **É o primeiro passo para conseguir reaproveitar um slide de template**, pois permite que a IA saiba os nomes dos elementos para editá-los depois.

### `duplicate_slide(slide_index: int)`
Cria uma cópia idêntica de um slide já existente, ideal para reutilizar infográficos, layouts avançados ou estrutura visual pré-existente do template. Retorna o número do novo slide copiado.

### `delete_slide(slide_index: int)`
Exclui um slide da apresentação (útil para limpar slides do template base que você não for utilizar).

### `update_shape_text(slide_index: int, shape_name: str, new_text: str)`
Atualiza o texto de um elemento existente no slide (pelo seu nome descoberto com `get_slide_info`). Muito usado logo após duplicar um slide de layout rico para preenchê-lo com os novos dados sem precisar redesenhar nada.

### `add_slide(layout_type: int)`
**[NÃO RECOMENDADO]** Adiciona um novo slide usando layouts básicos do PowerPoint. Como isso geralmente cria slides sem fundo ou com design "chapado", você deve sempre priorizar o uso de `duplicate_slide` e a edição dos elementos pré-existentes do template.

### `add_text_to_slide(slide_index: int, title: str, body_text: str)`
**[NÃO RECOMENDADO]** Preenche os marcadores de texto padrão. Sempre prefira usar `update_shape_text` para garantir que a formatação rica do template original seja preservada.

### `add_textbox(slide_index: int, text: str, left: float, top: float, width: float, height: float, font_size: int, bold: bool)`
Adiciona uma caixa de texto personalizada em posições exatas (medidas em pontos). Útil para criar layouts livres e infográficos.

### `add_chart(slide_index: int, chart_type: int, data: list, title: str)`
Insere um gráfico nativo do Office embutindo uma planilha Excel nos bastidores.
- **`chart_type`:** O tipo de gráfico do Excel (ex: `51` para colunas agrupadas, `4` para linhas, `5` para pizza).
- **`data`:** Uma lista de dicionários com os dados. Ex: `[{"Mes": "Jan", "Vendas": 1500}, {"Mes": "Fev", "Vendas": 2300}]`.

### `apply_theme(theme_path: str)`
Aplica um tema existente (`.thmx`) à apresentação ativa. Você deve fornecer o caminho absoluto do arquivo `.thmx`.

### `save_presentation(file_path: str)`
Salva a apresentação atual no caminho absoluto especificado (ex: `C:\Caminho\Para\apresentacao.pptx`).
