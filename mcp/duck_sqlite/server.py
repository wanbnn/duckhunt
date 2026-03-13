import os
import sqlite3
import json
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# Configuração do Workspace
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", os.getcwd())).resolve()
try:
    os.chdir(WORKSPACE_DIR)
except Exception as e:
    pass

# Inicializa o servidor FastMCP
mcp = FastMCP("DuckTools - SQLite MCP")

def get_safe_path(filepath: str) -> Path:
    """Resolve o caminho e garante que ele seja acessível dentro do workspace."""
    try:
        target_path = Path(os.path.join(WORKSPACE_DIR, filepath)).resolve()
    except Exception:
        target_path = Path(os.path.join(WORKSPACE_DIR, filepath)).absolute()
        
    # Garante que não saia do workspace
    try:
        target_path.relative_to(WORKSPACE_DIR)
    except ValueError:
        raise ValueError(f"Acesso negado: O caminho {filepath} está fora do workspace.")
    
    return target_path

@mcp.tool()
def list_sqlite_files(subpath: str = "") -> str:
    """List all .db, .sqlite, .sqlite3 files in a directory for exploration."""
    try:
        target = get_safe_path(subpath)
        if not target.exists() or not target.is_dir():
            return f"Error: Directory not found: {subpath}"
        
        items = []
        extensions = {".db", ".sqlite", ".sqlite3", ".s3db", ".sl3"}
        for item in target.iterdir():
            if item.is_file() and item.suffix.lower() in extensions:
                items.append(item.name)
        
        return json.dumps(items) if items else "No SQLite files found in this directory."
    except Exception as e:
        return f"Error listing files: {str(e)}"

@mcp.tool()
def list_tables(db_path: str) -> str:
    """List all tables in the specified SQLite database."""
    path = get_safe_path(db_path)
    if not path.exists():
        return f"Error: Database file not found at {db_path}"
    
    try:
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return json.dumps(tables)
    except Exception as e:
        return f"Error listing tables: {str(e)}"

@mcp.tool()
def get_table_schema(db_path: str, table_name: str) -> str:
    """Get the schema (columns, types, pk) for a specific table in the SQLite database."""
    path = get_safe_path(db_path)
    if not path.exists():
        return f"Error: Database file not found at {db_path}"
    
    try:
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        try:
            cursor.execute(f"PRAGMA table_info('{table_name}');")
            columns = [
                {"name": row[1], "type": row[2], "notnull": bool(row[3]), "pk": bool(row[5])} 
                for row in cursor.fetchall()
            ]
            return json.dumps(columns)
        finally:
            conn.close()
    except Exception as e:
        return f"Error getting schema: {str(e)}"

@mcp.tool()
def execute_query(db_path: str, query: str) -> str:
    """
    Execute a read SQL query against the SQLite database and return results as JSON.
    For SELECT queries, returns a list of objects. For others, returns status.
    """
    path = get_safe_path(db_path)
    if not path.exists():
        return f"Error: Database file not found at {db_path}"
    
    try:
        # Connect in read-only mode if possible for safety, 
        # but the user said "pode executar query" which might include updates.
        # SQLite doesn't have a simple RO flag in connect() that works everywhere,
        # but we can check the query.
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute(query)
            
            # Simple check for data-returning queries
            is_select = query.strip().upper().startswith("SELECT") or "RETURNING" in query.upper()
            
            if is_select:
                results = [dict(row) for row in cursor.fetchall()]
                return json.dumps(results, default=str)
            else:
                conn.commit()
                changes = conn.total_changes
                return f"Query executed successfully. Changes: {changes}"
        finally:
            conn.close()
    except Exception as e:
        return f"Error executing query: {str(e)}"

@mcp.tool()
def describe_database(db_path: str) -> str:
    """Get a comprehensive summary of all tables and their columns in the database."""
    path = get_safe_path(db_path)
    if not path.exists():
        return f"Error: Database file not found at {db_path}"
    
    try:
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [row[0] for row in cursor.fetchall()]
            
            db_summary = {}
            for table in tables:
                cursor.execute(f"PRAGMA table_info('{table}');")
                columns = [f"{row[1]} ({row[2]})" for row in cursor.fetchall()]
                db_summary[table] = columns
                
            return json.dumps(db_summary, indent=2)
        finally:
            conn.close()
    except Exception as e:
        return f"Error describing database: {str(e)}"

if __name__ == "__main__":
    mcp.run()
