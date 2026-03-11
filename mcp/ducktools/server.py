import os
import json
import subprocess
import re
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# Configuração do Workspace
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", os.getcwd())).resolve()
SKILLS_DIR = (Path(__file__).parent.parent.parent / "skills").resolve()
TODO_FILE = WORKSPACE_DIR / ".mcp_todo.json"

# Limites para economizar tokens
MAX_LINES_PER_READ = 400
MAX_SEARCH_RESULTS = 10
MAX_CMD_OUTPUT_LENGTH = 3000

# Variável global para manter a sessão do navegador
_browser_driver = None

mcp = FastMCP("DuckTools MCP")

# --- FUNÇÕES AUXILIARES ---

def get_safe_path(filepath: str) -> Path:
    target_path = (WORKSPACE_DIR / filepath).resolve()
    
    # Permite acesso ao Workspace OU à pasta de Skills
    in_workspace = str(target_path).startswith(str(WORKSPACE_DIR))
    in_skills = str(target_path).startswith(str(SKILLS_DIR))
    
    if not (in_workspace or in_skills):
        raise ValueError(f"Acesso negado: Path Traversal detectado para {filepath}")
    return target_path

def load_todos() -> list:
    if not TODO_FILE.exists(): return []
    with open(TODO_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_todos(todos: list):
    with open(TODO_FILE, "w", encoding="utf-8") as f: json.dump(todos, f, indent=4)

# --- TOOLS DE EXPLORAÇÃO E LEITURA OTIMIZADA ---

@mcp.tool()
def list_directory(subpath: str = "") -> str:
    """Lista arquivos e pastas em um diretório para exploração (não lê conteúdo)."""
    target = get_safe_path(subpath)
    if not target.exists() or not target.is_dir():
        return f"Erro: Diretório não encontrado: {subpath}"
    
    ignore = {".git", "node_modules", "__pycache__", "venv", ".venv"}
    items = []
    for item in target.iterdir():
        if item.name in ignore: continue
        kind = "DIR " if item.is_dir() else "FILE"
        items.append(f"[{kind}] {item.name}")
    
    return "\n".join(items) if items else "Diretório vazio."

@mcp.tool()
def get_file_info(filepath: str) -> str:
    """Retorna o número total de linhas e o tamanho do arquivo para planejamento de leitura."""
    path = get_safe_path(filepath)
    if not path.exists(): return "Erro: Arquivo não encontrado."
    
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        
    return f"Arquivo: {filepath}\nTotal de linhas: {len(lines)}\nTamanho: {path.stat().st_size} bytes."

@mcp.tool()
def read_file_lines(filepath: str, start_line: int, end_line: int) -> str:
    """
    Lê APENAS um bloco específico de linhas de um arquivo (paginação).
    As linhas são indexadas a partir de 1. Máximo de 200 linhas por vez.
    """
    if end_line - start_line > MAX_LINES_PER_READ:
        return f"Erro: Você pediu muitas linhas. O máximo permitido é {MAX_LINES_PER_READ} por vez para poupar tokens."
        
    path = get_safe_path(filepath)
    if not path.exists(): return "Erro: Arquivo não encontrado."
    
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        
    start_idx = max(0, start_line - 1)
    end_idx = min(len(lines), end_line)
    
    output = []
    for i in range(start_idx, end_idx):
        # Retorna o código com os números das linhas ao lado para facilitar a edição posterior
        line_content = lines[i].rstrip('\n')
        output.append(f"{i+1} | {line_content}")
        
    return "\n".join(output)

# --- TOOLS DE EDIÇÃO PARCIAL ---

@mcp.tool()
def create_file(filepath: str, content: str) -> str:
    """Cria um novo arquivo com o conteúdo especificado. Falha se o arquivo já existir."""
    path = get_safe_path(filepath)
    warning = ""
    
    if str(path).startswith(str(SKILLS_DIR)):
        rel_path = path.relative_to(SKILLS_DIR)
        path = WORKSPACE_DIR / rel_path
        warning = f" (NOTA: Acesso a 'skills' redirecionado para workspace: '{rel_path}')"

    if path.exists():
        return f"Erro: O arquivo '{path.name}' já existe. Use edit_file_lines para modificá-lo.{warning}"
    
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        
    return f"Sucesso: Arquivo '{path.name}' criado.{warning}"

@mcp.tool()
def edit_file_lines(filepath: str, start_line: int, end_line: int, new_content: str) -> str:
    """
    Substitui um bloco específico de linhas (start_line até end_line) pelo new_content.
    Use start_line = end_line para substituir apenas uma linha.
    Para adicionar sem apagar, reescreva a linha original junto com a nova no new_content.
    """
    path = get_safe_path(filepath)
    warning = ""

    if str(path).startswith(str(SKILLS_DIR)):
        rel_path = path.relative_to(SKILLS_DIR)
        path = WORKSPACE_DIR / rel_path
        warning = f" (NOTA: Acesso a 'skills' redirecionado para workspace: '{rel_path}')"

    if not path.exists():
        # Se não existe, cria o arquivo com o novo conteúdo
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"Arquivo {path.name} não existia e foi criado com o novo conteúdo.{warning}"

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    lines = content.split('\n')
    start_idx = max(0, start_line - 1)
    end_idx = min(len(lines), end_line)
    
    # Prepara o novo conteúdo dividindo-o em linhas
    new_lines = new_content.split('\n')
    
    # Substitui o pedaço específico
    lines[start_idx:end_idx] = new_lines
    
    with open(path, "w", encoding="utf-8") as f:
        f.write('\n'.join(lines))
        
    return f"Sucesso: Arquivo {path.name} modificado. Linhas {start_line} a {end_line} foram atualizadas.{warning}"

# --- TOOLS DE BUSCA (RAG) E TERMINAL ---

@mcp.tool()
def search_codebase(query: str) -> str:
    """
    Busca um termo no código e retorna as ocorrências com contexto (+2 e -2 linhas ao redor).
    Funciona como um mini-RAG para encontrar onde editar.
    """
    results = []
    ignore_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv"}
    match_count = 0
    
    for root, dirs, files in os.walk(WORKSPACE_DIR):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            if match_count >= MAX_SEARCH_RESULTS:
                break
            filepath = Path(root) / file
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for i, line in enumerate(lines):
                        if query in line:
                            rel_path = filepath.relative_to(WORKSPACE_DIR)
                            context_start = max(0, i - 2)
                            context_end = min(len(lines), i + 3)
                            
                            snippet = f"--- Encontrado em {rel_path} (Linhas {context_start+1} a {context_end}) ---\n"
                            for j in range(context_start, context_end):
                                prefix = ">> " if j == i else "   "
                                snippet += f"{prefix}{j+1} | {lines[j].strip()}\n"
                                
                            results.append(snippet)
                            match_count += 1
                            if match_count >= MAX_SEARCH_RESULTS:
                                break
            except UnicodeDecodeError:
                pass 
                
    if not results: return f"Nenhum resultado encontrado para '{query}'."
    results.append(f"\nExibindo {match_count} resultados (limitado para poupar tokens).")
    return "\n".join(results)

@mcp.tool()
def fetch_webpage(url: str, extract_text: bool = True) -> str:
    """
    Busca o conteúdo HTML ou texto de uma URL de forma estática (rápido, sem carregar navegador/Selenium).
    Use extract_text=True para obter apenas o texto limpo.
    """
    import urllib.request
    from urllib.error import URLError, HTTPError
    import html
    import re
    
    if not url.startswith("http"): url = "http://" + url
    req = urllib.request.Request(
        url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            html_content = response.read().decode('utf-8', errors='ignore')
            
            if not extract_text:
                limit = MAX_CMD_OUTPUT_LENGTH * 2
                return html_content[:limit] + ("\n...[HTML TRUNCADO]..." if len(html_content) > limit else "")
            
            # Limpeza rápida
            text = re.sub(r'<(script|style|head).*?>.*?</\1>', ' ', html_content, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = html.unescape(text)
            text = re.sub(r'[ \t]+', ' ', text)
            text = re.sub(r'\n\s*\n', '\n', text).strip()
            
            if len(text) > MAX_CMD_OUTPUT_LENGTH:
                return text[:MAX_CMD_OUTPUT_LENGTH] + "\n\n...[TEXTO TRUNCADO PARA ECONOMIZAR TOKENS]..."
            return text
            
    except HTTPError as e: return f"Erro HTTP {e.code}: {e.reason}"
    except URLError as e: return f"Erro de URL: {e.reason}"
    except Exception as e: return f"Erro inesperado: {str(e)}"

@mcp.tool()
def execute_command(command: str) -> str:
    """Executa um comando de terminal. A saída é truncada se for muito longa."""
    try:
        result = subprocess.run(
            command, shell=True, cwd=WORKSPACE_DIR, capture_output=True, text=True, timeout=30
        )
        output = f"Exit code: {result.returncode}\n"
        output += f"STDOUT:\n{result.stdout}\n" if result.stdout else ""
        output += f"STDERR:\n{result.stderr}\n" if result.stderr else ""
        
        # Otimização de token: Trunca a saída se for um log gigante (ex: npm install)
        if len(output) > MAX_CMD_OUTPUT_LENGTH:
            return output[:MAX_CMD_OUTPUT_LENGTH] + "\n\n...[SAÍDA TRUNCADA PARA ECONOMIZAR TOKENS]..."
        return output
    except Exception as e:
        return f"Erro ao executar comando: {str(e)}"

# --- TOOLS DE TODO (TAREFAS) ---

@mcp.tool()
def add_todo(task: str) -> str:
    """Adiciona uma tarefa."""
    todos = load_todos()
    new_id = max([t.get("id", 0) for t in todos], default=0) + 1
    todos.append({"id": new_id, "task": task, "status": "pending"})
    save_todos(todos)
    return f"Tarefa {new_id} adicionada."

@mcp.tool()
def list_todos() -> str:
    """Lista tarefas pendentes e completas."""
    todos = load_todos()
    if not todos: return "Nenhuma tarefa."
    return "\n".join(f"[{'x' if t['status'] == 'completed' else ' '}] {t['id']}: {t['task']}" for t in todos)

@mcp.tool()
def complete_todo(task_id: int) -> str:
    """Marca uma tarefa como concluída."""
    todos = load_todos()
    for t in todos:
        if t["id"] == task_id:
            t["status"] = "completed"
            save_todos(todos)
            return f"Tarefa {task_id} concluída!"
    return "Tarefa não encontrada."


# --- TOOLS DE AUTOMAÇÃO DE NAVEGADOR ---

@mcp.tool()
def browser_automation(action: str, url: str = "", selector: str = "", by: str = "css", text: str = "", script: str = "") -> str:
    """
    Automação de navegador usando Microsoft Edge (Selenium).
    Ações:
    - 'navigate': Vai para uma URL (forneça 'url').
    - 'click': Clica em um elemento (forneça 'selector' e opcionalmente 'by').
    - 'type': Digita texto em um elemento (forneça 'selector', 'text'). Ex: text='{ENTER}' para pressionar Enter.
    - 'scroll': Rola a página. Ex: script='window.scrollBy(0, 500)' ou vazio para rolar 1 tela.
    - 'get_text': Pega o texto de um elemento (forneça 'selector') ou da página.
    - 'get_html': Pega o HTML de um elemento (forneça 'selector') ou da página.
    - 'execute_script': Executa JS (forneça 'script').
    - 'close': Fecha o navegador.
    
    'by' pode ser: 'css' (padrão), 'id', 'name', 'xpath', 'link_text', 'class_name', 'tag_name'.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.edge.service import Service as EdgeService
        from selenium.webdriver.edge.options import Options as EdgeOptions
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.keys import Keys
        from webdriver_manager.microsoft import EdgeChromiumDriverManager
    except ImportError:
        return "Erro: Módulos 'selenium' ou 'webdriver_manager' não estão instalados. Execute 'pip install selenium webdriver-manager'."

    global _browser_driver
    if action == "close":
        if _browser_driver:
            try:
                _browser_driver.quit()
            except:
                pass
            _browser_driver = None
            return "Navegador fechado."
        return "Navegador já estava fechado."

    if _browser_driver is None:
        try:
            options = EdgeOptions()
            # options.add_argument("--headless") # Descomente se não quiser abrir a janela do navegador
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            service = EdgeService(EdgeChromiumDriverManager().install())
            _browser_driver = webdriver.Edge(service=service, options=options)
            _browser_driver.implicitly_wait(10)
        except Exception as e:
            return f"Erro ao inicializar o Microsoft Edge: {str(e)}"

    driver = _browser_driver
    
    by_map = {
        "css": By.CSS_SELECTOR,
        "id": By.ID,
        "name": By.NAME,
        "xpath": By.XPATH,
        "link_text": By.LINK_TEXT,
        "class_name": By.CLASS_NAME,
        "tag_name": By.TAG_NAME
    }
    locator_by = by_map.get(by.lower(), By.CSS_SELECTOR)

    try:
        if action == "navigate":
            if not url: return "Erro: 'url' não fornecida."
            if not url.startswith("http"): url = "http://" + url
            driver.get(url)
            return f"Navegou para {url}. Título: {driver.title}"
            
        elif action == "click":
            if not selector: return "Erro: 'selector' não fornecido."
            element = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((locator_by, selector)))
            element.click()
            return f"Clicou em {selector}."
            
        elif action == "type":
            if not selector: return "Erro: 'selector' não fornecido."
            element = WebDriverWait(driver, 10).until(EC.presence_of_element_located((locator_by, selector)))
            element.clear()
            if text.upper() == "{ENTER}":
                element.send_keys(Keys.ENTER)
                return f"Pressionou ENTER no elemento {selector}."
            else:
                element.send_keys(text)
                return f"Digitou texto no elemento {selector}."
                
        elif action == "scroll":
            if script:
                driver.execute_script(script)
                return f"Scroll executado: {script}"
            else:
                driver.execute_script("window.scrollBy(0, window.innerHeight);")
                return "Rolou a página uma tela para baixo."
                
        elif action == "get_text":
            if selector:
                element = WebDriverWait(driver, 10).until(EC.presence_of_element_located((locator_by, selector)))
                return element.text
            else:
                return driver.find_element(By.TAG_NAME, "body").text
                
        elif action == "get_html":
            if selector:
                element = WebDriverWait(driver, 10).until(EC.presence_of_element_located((locator_by, selector)))
                return element.get_attribute('outerHTML')
            else:
                return driver.page_source
                
        elif action == "execute_script":
            if not script: return "Erro: 'script' não fornecido."
            res = driver.execute_script(script)
            return f"Script executado. Retorno: {res}"
            
        else:
            return f"Ação desconhecida: {action}"
            
    except Exception as e:
        return f"Erro ao executar '{action}': {str(e)}"

if __name__ == "__main__":
    mcp.run(transport="stdio")