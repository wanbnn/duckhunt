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

# --- TOOLS DE SLIDES (APRESENTAÇÕES) ---

@mcp.tool()
def manage_slides(action: str, filepath: str, slide_content: str = "", slide_index: int = -1, slide_bg: str = "") -> str:
    """
    Gerencia apresentações de slides em HTML com suporte a estilos avançados.
    
    O modelo deve gerar o HTML/CSS do conteúdo do slide (slide_content) com total liberdade criativa.
    Use slide_bg para definir cor ou imagem de fundo (ex: 'background: #333;' ou 'background-image: url(...)').
    
    Args:
    - action: 'create' (novo arquivo), 'add' (novo slide), 'update' (edita slide), 'delete' (remove), 'list' (lista).
    - filepath: Caminho do arquivo .html.
    - slide_content: Conteúdo HTML dentro do slide <div>. Use tags <script> para gráficos se necessário.
    - slide_index: Índice do slide (começa em 1). Se -1 em add, adiciona ao fim.
    - slide_bg: CSS para o atributo style do container do slide (opcional).
    """
    path = get_safe_path(filepath)
    
    # Proteção: Se tentar salvar em 'skills', redireciona para 'workspace'
    if str(path).startswith(str(SKILLS_DIR)):
        rel_path = path.relative_to(SKILLS_DIR)
        path = WORKSPACE_DIR / rel_path
    
    html_template = """<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Apresentação</title>
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({startOnLoad:true, theme: 'dark'});
        
        document.addEventListener('DOMContentLoaded', () => {
            const container = document.querySelector('.slide-container');
            const slides = document.querySelectorAll('.slide');
            const prevBtn = document.getElementById('prev-btn');
            const nextBtn = document.getElementById('next-btn');
            const pageIndicator = document.getElementById('page-indicator');
            
            function updateActiveSlide() {
                const h = window.innerHeight;
                const currentScroll = container.scrollTop;
                const index = Math.round(currentScroll / h);
                
                if (pageIndicator) {
                    pageIndicator.innerText = `${index + 1} / ${slides.length}`;
                }
            }

            if (slides.length > 0) {
                container.focus();
                updateActiveSlide();
                
                // Scroll navigation
                container.addEventListener('scroll', () => {
                    requestAnimationFrame(updateActiveSlide);
                });

                const navigate = (direction) => {
                    const h = window.innerHeight;
                    const currentScroll = container.scrollTop;
                    const index = Math.round(currentScroll / h);
                    
                    let newIndex = index + direction;
                    if (newIndex < 0) newIndex = 0;
                    if (newIndex >= slides.length) newIndex = slides.length - 1;
                    
                    slides[newIndex].scrollIntoView({ behavior: 'smooth' });
                };

                window.addEventListener('keydown', (e) => {
                    if (['ArrowRight', 'ArrowDown', ' '].includes(e.key)) {
                        e.preventDefault();
                        navigate(1);
                    } else if (['ArrowLeft', 'ArrowUp'].includes(e.key)) {
                        e.preventDefault();
                        navigate(-1);
                    }
                });
                
                if (prevBtn) prevBtn.addEventListener('click', () => navigate(-1));
                if (nextBtn) nextBtn.addEventListener('click', () => navigate(1));
            }
        });
    </script>
    <style>
        /* Reset e Base */
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Inter', system-ui, -apple-system, sans-serif; 
            background: #000; 
            color: #fff; 
            height: 100vh; 
            width: 100vw;
            overflow: hidden;
        }
        
        /* Container com Scroll Snap */
        .slide-container { 
            height: 100vh; 
            width: 100vw;
            overflow-y: auto; 
            scroll-snap-type: y mandatory; 
            scroll-behavior: smooth;
            /* Hide scrollbar */
            scrollbar-width: none;
            -ms-overflow-style: none;
        }
        .slide-container::-webkit-scrollbar { 
            display: none; 
        }
        
        /* Slide Individual */
        .slide { 
            width: 100vw; 
            height: 100vh; 
            scroll-snap-align: start;
            position: relative; 
            overflow: hidden;
            display: flex; 
            flex-direction: column; 
            justify-content: center; 
            align-items: center;
            background: #111; 
            padding: 2rem;
        }
        
        /* Classes utilitárias para o conteúdo */
        .content-wrapper { 
            max-width: 1400px; 
            width: 100%; 
            margin: 0 auto; 
            z-index: 10; 
            display: flex; 
            flex-direction: column; 
            height: 100%; 
            justify-content: center;
            /* Permite rolagem interna se o conteúdo exceder a altura da tela (evita cortes) */
            overflow-y: auto;
            scrollbar-width: none;
        }
        .content-wrapper::-webkit-scrollbar { display: none; }
        
        /* Tipografia Responsiva */
        h1 { font-size: clamp(2.5rem, 5vw, 4.5rem); line-height: 1.1; margin-bottom: 1.5rem; font-weight: 800; letter-spacing: -0.03em; }
        h2 { font-size: clamp(2rem, 4vw, 3.5rem); line-height: 1.2; margin-bottom: 1.5rem; font-weight: 700; letter-spacing: -0.02em; }
        h3 { font-size: clamp(1.5rem, 3vw, 2.5rem); margin-bottom: 1rem; font-weight: 600; }
        p { font-size: clamp(1rem, 1.5vw, 1.6rem); line-height: 1.6; color: rgba(255,255,255,0.9); margin-bottom: 1.5rem; max-width: 70ch; }
        ul, ol { margin-left: 2rem; margin-bottom: 1.5rem; }
        li { font-size: clamp(1rem, 1.5vw, 1.5rem); line-height: 1.6; margin-bottom: 0.8rem; }
        
        /* Gráficos e Imagens Responsivos */
        .chart-container {
            position: relative;
            width: 100%;
            height: 50vh; /* Altura padrão para gráficos */
            min-height: 300px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        img, canvas, svg, .mermaid {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }
        
        .grid { display: grid; gap: 2rem; width: 100%; }
        .cols-2 { grid-template-columns: 1fr 1fr; }
        .cols-3 { grid-template-columns: 1fr 1fr 1fr; }
        
        /* Ajuste para grids em telas menores */
        @media (max-width: 768px) {
            .cols-2, .cols-3 { grid-template-columns: 1fr; }
            .slide { padding: 1rem; }
        }
        
        .card { background: rgba(255,255,255,0.08); padding: 2rem; border-radius: 1rem; border: 1px solid rgba(255,255,255,0.1); backdrop-filter: blur(10px); }
        .tag { display: inline-block; padding: 0.5rem 1rem; background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); border-radius: 99px; font-size: 1rem; font-weight: bold; margin-right: 0.5rem; text-transform: uppercase; letter-spacing: 0.05em; }
        
        /* Controls */
        .controls {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            z-index: 1000;
            display: flex;
            align-items: center;
            gap: 1rem;
            background: rgba(0, 0, 0, 0.6);
            padding: 0.5rem 1rem;
            border-radius: 2rem;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
            transition: opacity 0.3s ease;
            opacity: 0.4;
        }
        .controls:hover { opacity: 1; }
        
        .control-btn {
            background: none;
            border: none;
            color: white;
            cursor: pointer;
            padding: 0.5rem;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s;
        }
        .control-btn:hover { background: rgba(255,255,255,0.2); }
        .control-btn svg { width: 24px; height: 24px; fill: currentColor; }
        
        .page-indicator {
            font-size: 0.9rem;
            font-weight: 600;
            color: rgba(255,255,255,0.8);
            min-width: 40px;
            text-align: center;
        }

        /* Impressão */
        @media print { 
            .slide-container { overflow: visible; height: auto; }
            .slide { page-break-after: always; height: 100vh; } 
            .controls { display: none; }
        }
    </style>
</head>
<body>
    <div class="slide-container">
<!-- SLIDES_START -->
<!-- SLIDES_END -->
    </div>
    
    <div class="controls">
        <button class="control-btn" id="prev-btn" title="Anterior">
            <svg viewBox="0 0 24 24"><path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/></svg>
        </button>
        <span class="page-indicator" id="page-indicator">1 / --</span>
        <button class="control-btn" id="next-btn" title="Próximo">
            <svg viewBox="0 0 24 24"><path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/></svg>
        </button>
    </div>
</body>
</html>"""

    if action == "create":
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_template)
        return f"Apresentação criada em {path.name}."

    if not path.exists():
        return "Erro: Arquivo não existe. Use action='create' primeiro."

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extrai slides existentes usando regex não-guloso até o marcador
    # O padrão procura por <div class="slide" ...> ... </div><!-- /SLIDE -->
    slide_pattern = re.compile(r'(<div class="slide".*?>.*?</div><!-- /SLIDE -->)', re.DOTALL)
    slides = slide_pattern.findall(content)

    if action == "list":
        return f"Encontrados {len(slides)} slides."

    # Prepara novo conteúdo
    # Garante que o style tenha background se fornecido
    style_attr = f'style="{slide_bg}"' if slide_bg else 'style=""'
    new_slide = f'<div class="slide" {style_attr}>\n{slide_content}\n</div><!-- /SLIDE -->'

    if action == "add":
        if slide_index < 1:
            slides.append(new_slide)
        else:
            slides.insert(slide_index - 1, new_slide)
            
    elif action == "update":
        if slide_index < 1 or slide_index > len(slides):
            return f"Erro: Slide {slide_index} inválido (Total: {len(slides)})."
        slides[slide_index - 1] = new_slide
        
    elif action == "delete":
        if slide_index < 1 or slide_index > len(slides):
            return f"Erro: Slide {slide_index} inválido."
        slides.pop(slide_index - 1)
    
    # Reconstrói o arquivo preservando cabeçalho e rodapé
    if "<!-- SLIDES_START -->" in content and "<!-- SLIDES_END -->" in content:
        parts = content.split("<!-- SLIDES_START -->")
        header = parts[0] + "<!-- SLIDES_START -->\n"
        footer = "\n<!-- SLIDES_END -->" + content.split("<!-- SLIDES_END -->")[1]
        
        new_content = header + "\n".join(slides) + footer
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"Sucesso: {action} realizado. Total de slides: {len(slides)}."
    else:
        return "Erro: Estrutura do arquivo corrompida (marcadores não encontrados)."

if __name__ == "__main__":
    mcp.run(transport="stdio")