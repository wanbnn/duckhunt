# SQL Server MCP Server

Este é um servidor MCP (Model Context Protocol) usando transporte `stdio` projetado para conectar e realizar consultas em bancos de dados SQL Server. 

O servidor disponibiliza ferramentas (`tools`) para:
- `execute_query(query)`: Executar queries SQL no banco de dados.
- `list_tables()`: Listar todas as tabelas do banco de dados.
- `get_table_schema(table_name)`: Obter o schema (colunas e tipos de dados) de uma tabela específica.

## Dependências

Este servidor requer o pacote Python `pyodbc` além do `mcp`. 
Você também precisa ter instalado em sua máquina o Driver ODBC para SQL Server (como o `ODBC Driver 17 for SQL Server`).

Para instalar a dependência `pyodbc`:
```bash
pip install pyodbc
```

## Configuração do `mcp/config.json`

Você deve registrar este servidor no arquivo `mcp/config.json` do seu cliente MCP (por exemplo, na configuração do VS Code Claude ou similar).

Existem duas formas principais de se conectar: usando **Autenticação do Windows** (Trusted Connection) ou **Usuário e Senha do SQL Server**.

### 1. Com Autenticação do Windows (Trusted Connection)

Se você utiliza o login do Windows para acessar o banco, a propriedade `DB_TRUSTED_CONNECTION` deve ser `true`. As propriedades `DB_USER` e `DB_PASSWORD` podem ser omitidas.

```json
{
  "mcpServers": {
    "sqlserver": {
      "command": "python",
      "args": ["mcp/sqlserver/server.py"],
      "env": {
        "DB_SERVER": "localhost\\SQLEXPRESS",
        "DB_DB": "meu_banco_de_dados",
        "DB_TRUSTED_CONNECTION": "true"
      }
    }
  }
}
```

### 2. Com Usuário e Senha do SQL Server

Se o banco requer um login específico, defina `DB_TRUSTED_CONNECTION` como `false` (ou apenas não envie) e adicione o `DB_USER` e o `DB_PASSWORD`.

```json
{
  "mcpServers": {
    "sqlserver": {
      "command": "python",
      "args": ["mcp/sqlserver/server.py"],
      "env": {
        "DB_SERVER": "127.0.0.1,1433",
        "DB_DB": "meu_banco_de_dados",
        "DB_TRUSTED_CONNECTION": "false",
        "DB_USER": "sa",
        "DB_PASSWORD": "sua_senha_super_secreta"
      }
    }
  }
}
```

## Variáveis de Ambiente

| Variável | Descrição |
|----------|-----------|
| `DB_SERVER` | O endereço do servidor de banco de dados (ex: `localhost`, `192.168.0.10,1433`, `SRV\SQLEXPRESS`). |
| `DB_DB` | O nome do banco de dados a ser conectado (ex: `master`, `meu_banco`). |
| `DB_TRUSTED_CONNECTION` | Se `"true"`, utiliza a Autenticação do Windows para o SQL Server. |
| `DB_USER` | Obrigatório se `DB_TRUSTED_CONNECTION` for `false`. Nome do usuário do SQL Server. |
| `DB_PASSWORD` | Obrigatório se `DB_TRUSTED_CONNECTION` for `false`. Senha do usuário. |
