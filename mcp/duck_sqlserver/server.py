import os
import pyodbc
from pathlib import Path
from mcp.server.fastmcp import FastMCP
import json

# Configuração do Workspace
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", os.getcwd())).resolve()
try:
    os.chdir(WORKSPACE_DIR)
except Exception as e:
    pass

# Inicializa o servidor FastMCP
mcp = FastMCP("DuckTools - SQL Server MCP")

# Configurações via variáveis de ambiente
DB_SERVER = os.environ.get("DB_SERVER")
DB_NAME = os.environ.get("DB_DB")
DB_TRUSTED_CONNECTION = str(os.environ.get("DB_TRUSTED_CONNECTION", "false")).lower() in ("true", "1", "yes")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_ENCRYPT = str(os.environ.get("DB_ENCRYPT", "true")).lower() in ("true", "1", "yes")
DB_TRUST_SERVER_CERTIFICATE = str(os.environ.get("DB_TRUST_SERVER_CERTIFICATE", "true")).lower() in ("true", "1", "yes")

def get_driver():
    """Obtém o melhor driver ODBC disponível instalado."""
    try:
        drivers = pyodbc.drivers()
        preferred_drivers = [
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "ODBC Driver 13 for SQL Server",
            "SQL Server Native Client 11.0",
            "SQL Server"
        ]
        for driver in preferred_drivers:
            if driver in drivers:
                return "{" + driver + "}"
    except Exception:
        pass
    return "{SQL Server}"

def get_connection_string():
    """Constrói a string de conexão baseada nas variáveis de ambiente."""
    if not DB_SERVER or not DB_NAME:
        raise ValueError("As variáveis de ambiente DB_SERVER e DB_DB devem estar configuradas.")
    
    driver = get_driver()
    conn_str = f"DRIVER={driver};SERVER={DB_SERVER};DATABASE={DB_NAME};"
    
    if DB_TRUSTED_CONNECTION:
        conn_str += "Trusted_Connection=yes;"
    else:
        if DB_USER and DB_PASSWORD:
            conn_str += f"UID={DB_USER};PWD={DB_PASSWORD};"
            
    if DB_ENCRYPT:
        conn_str += "Encrypt=yes;"
        
    if DB_TRUST_SERVER_CERTIFICATE:
        conn_str += "TrustServerCertificate=yes;"
        
    return conn_str

def get_connection():
    """Retorna a conexão pyodbc."""
    return pyodbc.connect(get_connection_string())

@mcp.tool()
def execute_query(query: str) -> str:
    """Execute a read-only SQL query against the SQL Server database and return the results as JSON.
    Do not use this for destructive operations.
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            if cursor.description: 
                columns = [column[0] for column in cursor.description]
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return json.dumps(results, default=str)
            else:
                conn.commit()
                return "Query executed successfully. No data returned."
    except Exception as e:
        return f"Error executing query: {str(e)}"

@mcp.tool()
def list_tables() -> str:
    """List all tables in the SQL Server database."""
    query = "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"
    return execute_query(query)

@mcp.tool()
def get_table_schema(table_name: str) -> str:
    """Get the schema details for a specific table in the SQL Server database."""
    query = f"SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{table_name}'"
    return execute_query(query)

if __name__ == "__main__":
    mcp.run()
