import sys
import os
import json
import asyncio
import configparser
import shutil
import hashlib
from urllib.parse import urlparse, parse_qs
import markdown # Para renderizar mensagens Markdown
import re

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextBrowser, QTextEdit, QLineEdit, QLabel, QListWidget, QListWidgetItem,
    QStackedWidget, QSplitter, QComboBox, QMessageBox, QDialog, QFormLayout, 
    QDialogButtonBox, QCheckBox, QAbstractItemView, QGroupBox, QScrollArea, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QSize
from PyQt6.QtGui import QFont, QIcon, QColor, QPalette

import qasync
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI, AzureOpenAI

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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
MCP_CONFIG_PATH = os.path.join(BASE_DIR, "mcp", "config.json")
AGENTS_DIR = os.path.join(BASE_DIR, "agents")
SKILLS_DIR = os.path.join(BASE_DIR, "skills")
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")
API_CONFIG_PATH = os.path.join(MODELS_DIR, "api_config.json")

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
    except Exception:
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

class UnifiedLLM:
    def __init__(self, client, model_type, model_name):
        self.client = client
        self.model_type = model_type
        self.model_name = model_name

    def create_chat_completion(self, messages, tools=None, tool_choice=None, max_tokens=None, temperature=None, stream=True):
        if self.model_type == "local":
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

            response_generator = self.client.create_chat_completion(
                messages=local_messages,
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
                    if not content: content = "(empty)"
                        
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
                print(f"Erro API Anthropic: {e}")
            return

        kwargs = {"messages": messages, "stream": stream, "model": self.model_name}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        if self.model_type in ("openai", "gemini"):
            if max_tokens: kwargs["max_tokens"] = max_tokens
            if temperature: kwargs["temperature"] = temperature
        try:
            response = self.client.chat.completions.create(**kwargs)
            if stream:
                for chunk in response:
                    processed = self._convert_chunk(chunk)
                    if processed: yield processed
            else:
                yield self._convert_chunk(response)
        except Exception as e:
            print(f"Erro API ({self.model_type}): {e}")

    def _convert_chunk(self, chunk):
        if not hasattr(chunk, "choices") or not chunk.choices: return {}
        choice = chunk.choices[0]
        delta = choice.delta
        delta_dict = {}
        if delta.content is not None: delta_dict["content"] = delta.content
        if getattr(delta, "tool_calls", None):
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
                delta_dict["tool_calls"].append(tc_dict)
        return {"choices": [{"delta": delta_dict, "finish_reason": choice.finish_reason}]}

# Sinais para comunicar o resultado das respostas do modelo (são executados em Threads para não travar a GUI)
class AsyncSignals(QObject):
    chunk_received = pyqtSignal(str, str, int)  # agent_id, chunk_text, chat_index (for multiagent)
    stream_finished = pyqtSignal(dict, int)     # message_dict, agent_index
    tool_execution = pyqtSignal(str, str)       # tool_info, status
    error_msg = pyqtSignal(str)
    
class StyledButton(QPushButton):
    def __init__(self, text, bg_color="#45B7D1", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lt = self._adjust(bg_color, 30)
        dk = self._adjust(bg_color, -30)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color}; color: white; border: none;
                border-radius: 8px; padding: 9px 18px; font-weight: bold; font-size: 13px;
            }}
            QPushButton:hover {{ background-color: {lt}; }}
            QPushButton:pressed {{ background-color: {dk}; }}
            QPushButton:disabled {{ background-color: #45475A; color: #6C7086; }}
        """)

    @staticmethod
    def _adjust(hex_color, amount):
        hex_color = hex_color.lstrip('#')
        r = max(0, min(255, int(hex_color[0:2], 16) + amount))
        g = max(0, min(255, int(hex_color[2:4], 16) + amount))
        b = max(0, min(255, int(hex_color[4:6], 16) + amount))
        return f'#{r:02x}{g:02x}{b:02x}'

class DuckHuntGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DuckHunt AI Agent GUI")
        self.resize(1100, 750)
        self.setStyleSheet("""
            QMainWindow { background-color: #1E1E2E; color: #CDD6F4; }
            QWidget { font-family: 'Segoe UI', Arial, sans-serif; color: #CDD6F4; }
            QTextBrowser { background-color: #181825; border: 1px solid #313244; border-radius: 10px; font-size: 14px; padding: 12px; color: #CDD6F4; selection-background-color: #45B7D1; }
            QLineEdit { background-color: #313244; border: 2px solid #45475A; border-radius: 10px; padding: 10px 14px; font-size: 14px; color: #CDD6F4; }
            QLineEdit:focus { border: 2px solid #45B7D1; }
            QListWidget { background-color: #181825; border: 1px solid #313244; border-radius: 8px; outline: none; }
            QListWidget::item { padding: 10px 12px; border-bottom: 1px solid #232336; border-radius: 4px; margin: 2px 4px; }
            QListWidget::item:hover { background-color: #232336; }
            QListWidget::item:selected { background-color: #313244; color: #89B4FA; border-left: 3px solid #45B7D1; }
            QLabel { font-size: 14px; }
            QComboBox { background-color: #313244; border: 1px solid #45475A; border-radius: 6px; padding: 8px; color: #CDD6F4; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #1E1E2E; color: #CDD6F4; selection-background-color: #45B7D1; border: 1px solid #45475A; }
            QDialog { background-color: #1E1E2E; color: #CDD6F4; }
            QDialogButtonBox QPushButton { background-color: #45B7D1; color: white; border: none; border-radius: 6px; padding: 8px 20px; font-weight: bold; }
            QDialogButtonBox QPushButton:hover { background-color: #63c5d9; }
            QToolTip { background-color: #313244; color: #CDD6F4; border: 1px solid #45475A; padding: 6px; border-radius: 6px; font-size: 12px; }
            QScrollBar:vertical { background: #181825; width: 10px; border-radius: 5px; }
            QScrollBar::handle:vertical { background: #45475A; border-radius: 5px; min-height: 30px; }
            QScrollBar::handle:vertical:hover { background: #585B70; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar:horizontal { height: 0px; }
        """)

        # Core logic state
        self.workspace_dir = load_config("General", "workspace") or os.getcwd()
        self.mcp_sessions = {}
        self.mcp_tools = {}
        self.mcp_original_names = {}
        self.llama_tools = []
        self.llm = None
        self.agent_prompt_text = "You are a senior development assistant running directly in the user's GUI."
        self.skills_prompts = []
        self.messages = []
        self.signals = AsyncSignals()
        
        self.signals.chunk_received.connect(self.on_chunk_received)
        self.signals.stream_finished.connect(self.on_stream_finished)
        self.signals.tool_execution.connect(self.on_tool_execution)
        self.signals.error_msg.connect(self.show_error)

        self.init_ui()
        
        # Inicia a sequência de carregamento de forma apropriada dentro do event loop do qasync
        def start_mcp_and_models():
            asyncio.ensure_future(self.startup_sequence())
        
        QTimer.singleShot(0, start_mcp_and_models)

    def init_ui(self):
        # Central Widget & Splitter
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Sidebar
        sidebar = QWidget()
        sidebar.setStyleSheet("background-color: #11111B;")
        sidebar.setMinimumWidth(220)
        sidebar.setMaximumWidth(250)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(15, 20, 15, 20)
        side_layout.setSpacing(10)

        title = QLabel("🦆 DuckHunt AI")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: #FFC857; margin-bottom: 20px;")
        side_layout.addWidget(title)
        
        # Navigation Buttons
        self.nav_btns = {}
        for text, icon, color in [
            ("Chat", "💬", "#45B7D1"),
            ("Modelos", "🤖", "#FF8E53"),
            ("Agentes", "🎯", "#A55EEA"),
            ("Multi-Agente", "👥", "#FFC857"),
            ("Servidores MCP", "🔌", "#4ECB71"),
            ("Skills", "⚡", "#F9E2AF"),
            ("Configurações", "⚙", "#89B4FA")
        ]:
            btn = QPushButton(f" {icon}  {text}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    text-align: left; background-color: transparent; border: none;
                    color: #CDD6F4; font-size: 15px; padding: 10px; border-radius: 6px; font-weight: bold;
                }}
                QPushButton:hover {{ background-color: #313244; color: {color}; }}
                QPushButton:checked {{ background-color: #45475A; color: {color}; }}
            """)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, t=text: self.switch_tab(t))
            side_layout.addWidget(btn)
            self.nav_btns[text] = btn

        side_layout.addStretch()

        # Divider line
        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: #313244;")
        side_layout.addWidget(divider)

        # Model indicator
        self.model_indicator = QLabel("🤖 Nenhum modelo")
        self.model_indicator.setStyleSheet("color: #6C7086; font-size: 11px; padding: 4px 0;")
        self.model_indicator.setWordWrap(True)
        side_layout.addWidget(self.model_indicator)

        # Agent indicator
        self.agent_indicator = QLabel("🎯 Agente padrão")
        self.agent_indicator.setStyleSheet("color: #6C7086; font-size: 11px; padding: 2px 0;")
        self.agent_indicator.setWordWrap(True)
        side_layout.addWidget(self.agent_indicator)

        # Workspace
        self.status_lbl = QLabel("📂 " + os.path.basename(self.workspace_dir))
        self.status_lbl.setStyleSheet("color: #6C7086; font-size: 11px; padding: 2px 0;")
        self.status_lbl.setWordWrap(True)
        side_layout.addWidget(self.status_lbl)

        # Version badge
        ver = QLabel("v1.0.4 GUI")
        ver.setStyleSheet("color: #45B7D1; font-size: 10px; font-weight: bold; background-color: #1a2a3a; border-radius: 4px; padding: 3px 8px; margin-top: 6px;")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side_layout.addWidget(ver)

        # Main Pages (QStackedWidget)
        self.pages = QStackedWidget()
        self.pages.setStyleSheet("background-color: #1E1E2E;")
        
        # Initialize Pages
        self.init_chat_page()
        self.init_models_page()
        self.init_agents_page()
        self.init_multi_agent_page()
        self.init_mcp_page()
        self.init_skills_page()
        self.init_settings_page()

        splitter.addWidget(sidebar)
        splitter.addWidget(self.pages)
        splitter.setStretchFactor(1, 1)

        self.switch_tab("Chat")

    def switch_tab(self, tab_text):
        for t, btn in self.nav_btns.items():
            btn.setChecked(t == tab_text)
            
        mapping = {
            "Chat": 0, "Modelos": 1, "Agentes": 2, 
            "Multi-Agente": 3, "Servidores MCP": 4, 
            "Skills": 5, "Configurações": 6
        }
        self.pages.setCurrentIndex(mapping.get(tab_text, 0))
        
        # Actions on tab selected
        if tab_text == "Modelos": self.refresh_models_list()
        elif tab_text == "Agentes": self.refresh_agents_list()
        elif tab_text == "Servidores MCP": self.refresh_mcp_list()
        elif tab_text == "Skills": self.refresh_skills_list()
        elif tab_text == "Configurações": self.refresh_settings_view()

    # ========================== CHAT PAGE ==========================
    def init_chat_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Header bar
        header = QHBoxLayout()
        chat_title = QLabel("💬 Chat")
        chat_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        chat_title.setStyleSheet("color: #CDD6F4;")
        header.addWidget(chat_title)
        header.addStretch()

        self.model_badge = QLabel("Sem modelo")
        self.model_badge.setStyleSheet("background-color: #313244; color: #A6ADC8; border-radius: 10px; padding: 4px 12px; font-size: 11px; font-weight: bold;")
        header.addWidget(self.model_badge)

        new_btn = StyledButton("🔄 Nova Conversa", "#313244")
        new_btn.clicked.connect(lambda: (self.reset_context(), self.chat_display.clear(), self._show_welcome()))
        header.addWidget(new_btn)
        layout.addLayout(header)

        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(True)
        layout.addWidget(self.chat_display)

        # Chat Controls
        controls = QHBoxLayout()
        controls.setSpacing(8)

        undo_btn = StyledButton("↩ Desfazer", "#45475A")
        undo_btn.clicked.connect(self.rollback_action)
        undo_btn.setToolTip("Desfaz modificações feitas pela IA (checkpoint)")
        undo_btn.setFixedWidth(110)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Escreva sua mensagem ou /help para comandos...")
        self.input_field.returnPressed.connect(self.send_message)

        send_btn = StyledButton(" Enviar  ➤", "#45B7D1")
        send_btn.clicked.connect(self.send_message)
        send_btn.setFixedWidth(110)

        controls.addWidget(undo_btn)
        controls.addWidget(self.input_field)
        controls.addWidget(send_btn)
        layout.addLayout(controls)

        self.pages.addWidget(page)
        self._show_welcome()

    def _show_welcome(self):
        self.chat_display.setHtml(f"""
        <div style="text-align: center; padding: 60px 20px;">
            <div style="font-size: 48px; margin-bottom: 10px;">🦆</div>
            <div style="font-size: 22px; font-weight: bold; color: #FFC857; margin-bottom: 8px;">DuckHunt AI Agent</div>
            <div style="font-size: 14px; color: #6C7086; margin-bottom: 30px;">Seu assistente de desenvolvimento com inteligência artificial</div>
            <div style="color: #45475A; font-size: 12px;">Iniciando conexões MCP e carregando modelo...</div>
        </div>
        """)

    def render_markdown(self, txt):
        html = markdown.markdown(txt, extensions=['fenced_code', 'tables'])
        # Style code blocks
        html = html.replace('<code>', '<code style="background-color: #313244; padding: 2px 6px; border-radius: 4px; font-family: Consolas, monospace; font-size: 13px;">')
        html = html.replace('<pre>', '<pre style="background-color: #11111B; border: 1px solid #313244; border-radius: 8px; padding: 12px; overflow-x: auto; font-family: Consolas, monospace; font-size: 13px;">')
        # Think blocks
        html = re.sub(r'&lt;think&gt;(.*?)&lt;/think&gt;',
            r'<div style="color: #A6ADC8; font-style: italic; border-left: 3px solid #6C5CE7; padding: 8px 12px; margin: 8px 0; background-color: #1a1a2e; border-radius: 0 6px 6px 0;">🧠 <b>Pensamento</b><br>\1</div>',
            html, flags=re.DOTALL)
        return html

    def _bubble(self, sender, html_body, color, align="left", bg="#232336", avatar=""):
        float_dir = "left" if align == "left" else "right"
        max_w = "85%"
        return f"""
        <div style="display: block; text-align: {align}; margin: 6px 0;">
            <div style="display: inline-block; max-width: {max_w}; text-align: left; background-color: {bg}; border-radius: 14px; padding: 10px 16px; margin: 2px 0;">
                <div style="font-size: 12px; font-weight: bold; color: {color}; margin-bottom: 4px;">{avatar} {sender}</div>
                <div style="color: #CDD6F4; font-size: 14px; line-height: 1.5;">{html_body}</div>
            </div>
        </div>
        """

    def append_chat(self, sender, text, color="#CDD6F4", is_html=False):
        if not is_html:
            html_text = self.render_markdown(text)
        else:
            html_text = text

        # Choose alignment and style
        if sender == "Você":
            bubble = self._bubble(sender, html_text, "#45B7D1", align="right", bg="#1a2a3a", avatar="👤")
        elif "Sistema" in sender or "SISTEMA" in sender:
            bubble = f'<div style="text-align: center; margin: 6px 0;"><span style="color: #6C7086; font-size: 12px; background-color: #232336; padding: 4px 14px; border-radius: 10px;">{html_text}</span></div>'
        elif "Erro" in sender or "❌" in sender:
            bubble = self._bubble(sender, html_text, "#F38BA8", bg="#2a1a1a", avatar="⚠️")
        elif "✓" in sender or "Concluído" in sender:
            bubble = self._bubble(sender, html_text, "#A6E3A1", bg="#1a2a1a", avatar="✅")
        elif "⚙" in sender:
            bubble = self._bubble(sender, html_text, "#FF8E53", bg="#2a2018", avatar="⚙️")
        else:
            bubble = self._bubble(sender, html_text, "#FFC857", bg="#232336", avatar="🦆")

        self.chat_display.append(bubble)
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    async def startup_sequence(self):
        # Config MCPs
        if os.path.exists(MCP_CONFIG_PATH):
            with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                self.mcp_config = json.load(f)
        else:
            self.mcp_config = {"mcpServers": {}}
            
        if "ducktools" in self.mcp_config.get("mcpServers", {}):
            self.mcp_config["mcpServers"]["ducktools"].setdefault("env", {})["WORKSPACE_DIR"] = self.workspace_dir
            with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.mcp_config, f, ensure_ascii=False, indent=2)

        # Load LLM
        m_type = load_config("Model", "type")
        m_name = load_config("Model", "name")
        if m_type and m_name:
            self.append_chat("Sistema", f"Restaurando modelo: {m_name} ({m_type})", "#FFC857")
            # For simplicity, if we have APIs configured, we try to load them from api_config.json
            if m_type != "local":
                if os.path.exists(API_CONFIG_PATH):
                    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    itens = data if isinstance(data, list) else [data]
                    for item in itens:
                        for k, v in item.items():
                            if k.lower() == m_type:
                                if m_type == "openai":
                                    client = OpenAI(api_key=v.get("api_key"))
                                    self.llm = UnifiedLLM(client, "openai", m_name)
                                elif m_type == "gemini":
                                    client = OpenAI(api_key=v.get("api_key"), base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
                                    self.llm = UnifiedLLM(client, "gemini", m_name)
                                elif m_type == "anthropic" and ANTHROPIC_AVAILABLE:
                                    client = anthropic.Anthropic(api_key=v.get("api_key"))
                                    self.llm = UnifiedLLM(client, "anthropic", m_name)
                                elif m_type == "azure":
                                    ep = v.get("endpoint", "")
                                    parsed = urlparse(ep)
                                    qs = parse_qs(parsed.query)
                                    api_ver = qs.get("api_version", ["2024-08-01-preview"])[0]
                                    base_url = f"{parsed.scheme}://{parsed.netloc}"
                                    client = AzureOpenAI(api_key=v.get("api_key"), api_version=api_ver, azure_endpoint=base_url)
                                    self.llm = UnifiedLLM(client, "azure", m_name)

            else:
                if LLAMA_CPP_AVAILABLE:
                    path = load_config("Model", "path")
                    if path and os.path.exists(path):
                        llama = await asyncio.to_thread(Llama, model_path=path, n_ctx=8192, n_gpu_layers=0, verbose=False)
                        self.llm = UnifiedLLM(llama, "local", m_name)
        
        # Start MCP Servers Contexts
        self.append_chat("Sistema", "Iniciando conexões MCP. Isso pode levar alguns segundos...", "#FFC857")
        try:
            import contextlib
            self.mcp_stack = contextlib.AsyncExitStack()
            
            for srv_name, srv_cfg in self.mcp_config.get("mcpServers", {}).items():
                if srv_cfg.get("disabled", False): continue
                try:
                    cmd = srv_cfg.get("command", "python")
                    if cmd in ("python", "python.exe", "python3"): cmd = sys.executable
                    env = {**os.environ, **srv_cfg.get("env", {})}
                    params = StdioServerParameters(command=cmd, args=srv_cfg.get("args", []), env=env)
                    read, write = await self.mcp_stack.enter_async_context(stdio_client(params))
                    
                    session = await self.mcp_stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                    self.mcp_sessions[srv_name] = session
                    
                    tools_resp = await session.list_tools()
                    for t in tools_resp.tools:
                        safe_name = t.name
                        if safe_name in self.mcp_tools:
                            safe_name = f"{srv_name}_{safe_name}"
                        self.mcp_tools[safe_name] = srv_name
                        self.mcp_original_names[safe_name] = t.name
                        desc = f"[{srv_name}] {t.description}" if safe_name != t.name else t.description
                        self.llama_tools.append({
                            "type": "function",
                            "function": {"name": safe_name, "description": desc, "parameters": t.inputSchema}
                        })
                except Exception as e:
                    print(f"Failed to load MCP {srv_name}: {e}")

            self.append_chat("Sistema", f"Pronto! {len(self.llama_tools)} ferramentas carregadas de {len(self.mcp_sessions)} servidores MCP.", "#4ECB71")
        except Exception as e:
            self.append_chat("Erro", f"Falha na conexão MCP: {e}", "#FF6B6B")

        # Update sidebar indicators
        self._update_indicators()
            
        # Carrega agente default e skills default
        ag = load_config("Agent", "filename")
        if ag and os.path.exists(os.path.join(AGENTS_DIR, ag)):
            with open(os.path.join(AGENTS_DIR, ag), "r", encoding="utf-8") as f:
                self.agent_prompt_text = f.read()

        loaded_str = load_config("Skills", "loaded")
        if loaded_str:
            wanted = [x.strip() for x in loaded_str.split(',') if x.strip()]
            for root, _dirs, files in os.walk(SKILLS_DIR):
                for f in files:
                    if f.lower() == 'skill.md':
                        rel = os.path.relpath(root, SKILLS_DIR)
                        if rel in wanted:
                            try:
                                path_sk = os.path.join(root, f)
                                with open(path_sk, 'r', encoding='utf-8') as f_obj:
                                    self.skills_prompts.append({
                                        "name": rel, "content": f_obj.read(), "path": os.path.abspath(root)
                                    })
                            except: pass

        self.reset_context()

    def compor_prompt(self):
        base = self.agent_prompt_text or ""
        if not self.skills_prompts: return base
        partes = [base, "\n\n### ACTIVE SKILLS\n"]
        for sp in self.skills_prompts:
            partes.append(f"\n--- Skill: {sp.get('name')} ---\n[Base Directory]: {sp.get('path')}\n{sp.get('content')}\n")
        return "".join(partes)

    def reset_context(self):
        self.messages = [{"role": "system", "content": self.compor_prompt()}]

    def _update_indicators(self):
        m_name = self.llm.model_name if self.llm else "Nenhum modelo"
        m_type = self.llm.model_type.upper() if self.llm else ""
        self.model_indicator.setText(f"🤖 {m_name}")
        if self.llm:
            self.model_indicator.setStyleSheet("color: #89B4FA; font-size: 11px; padding: 4px 0; font-weight: bold;")
            self.model_badge.setText(f"{m_type}: {m_name}")
            self.model_badge.setStyleSheet("background-color: #1a2a3a; color: #45B7D1; border-radius: 10px; padding: 4px 12px; font-size: 11px; font-weight: bold;")
        else:
            self.model_indicator.setStyleSheet("color: #6C7086; font-size: 11px; padding: 4px 0;")
            self.model_badge.setText("Sem modelo")
            self.model_badge.setStyleSheet("background-color: #313244; color: #A6ADC8; border-radius: 10px; padding: 4px 12px; font-size: 11px; font-weight: bold;")

        ag = load_config("Agent", "filename")
        if ag:
            self.agent_indicator.setText(f"🎯 {ag.replace('.md', '')}")
            self.agent_indicator.setStyleSheet("color: #CBA6F7; font-size: 11px; padding: 2px 0; font-weight: bold;")
        else:
            self.agent_indicator.setText("🎯 Agente padrão")
            self.agent_indicator.setStyleSheet("color: #6C7086; font-size: 11px; padding: 2px 0;")

    def show_error(self, err):
        QMessageBox.critical(self, "Erro", err)

    def rollback_action(self):
        sucesso, msg = rollback_checkpoint(self.workspace_dir)
        if sucesso:
            self.append_chat("Sistema", msg, "#4ECB71")
        else:
            self.append_chat("Erro", msg, "#FF6B6B")

    def process_command(self, cmd):
        # Implementa comandos locais
        if cmd == '/new':
            self.reset_context()
            self.append_chat("Sistema", "Chat reiniciado.", "#A6ADC8")
            return True
        if cmd == '/workspace':
            QMessageBox.information(self, "Desculpe", "Altere o workspace na aba 'Configurações' no menu lateral.")
            return True
        if cmd == '/undo':
            self.rollback_action()
            return True
        if cmd == '/duckroom' or cmd.startswith('/duckroom'):
            if 'on' in cmd:
                save_config("General", "duckroom", "on")
                self.append_chat("Sistema", "Duck Room visual ativado para a próxima sessão Multi-Agente.", "#4ECB71")
            elif 'off' in cmd:
                save_config("General", "duckroom", "off")
                self.append_chat("Sistema", "Duck Room visual desativado.", "#FF6B6B")
            else:
                self.append_chat("Sistema", "Use /duckroom on ou /duckroom off.", "#FFC857")
            return True

        if cmd == '/help':
            self.append_chat("Sistema", "Comandos suportados aqui:<br>/new - Reinicia contexto<br>/undo - Rollback das ações<br>/duckroom on|off - Alterna modo Duck Room visual.<br>Use o menu lateral para outras configurações.", "#A6ADC8", is_html=True)
            return True
        return False

    def send_message(self):
        text = self.input_field.text().strip()
        if not text: return
        self.input_field.clear()

        self.append_chat("Você", text, "#45B7D1")

        if self.process_command(text.lower()):
            return

        if not self.llm:
            self.show_error("Nenhum modelo IA carregado! Acesse a aba 'Modelos' e adicione ou selecione um modelo para conectar.")
            return

        # Snapshot before generating
        create_checkpoint(self.workspace_dir)

        # Referencias a arquivos
        file_refs = re.findall(r'(?:^|[\s\(\[\{])#([a-zA-Z0-9_\-\.\/\\]+)', text)
        if file_refs:
            ctxs = []
            for ref in set(file_refs):
                p = os.path.join(self.workspace_dir, ref)
                if os.path.isfile(p):
                    try:
                        with open(p, 'r', encoding='utf-8') as fs:
                            ctxs.append(f"--- Conteúdo {ref} ---\n{fs.read()}\n")
                    except Exception: pass
            if ctxs:
                text += "\n\n[Refs Anexadas]\n" + "\n".join(ctxs)

        self.messages.append({"role": "user", "content": text})
        self.set_ui_frozen(True)
        
        # Typing indicator
        self.append_chat("DuckHunt AI", "✍️ Pensando...", "#FFC857")
        self._current_assistant_text = ""
        self._streaming = True

        # Remove the placeholder, real appending happens dynamically
        asyncio.create_task(self.run_llm_stream(self.llm, self.messages.copy(), self.llama_tools, agent_id="0"))

    def set_ui_frozen(self, freeze):
        self.input_field.setDisabled(freeze)

    async def run_llm_stream(self, llm_instance, msgs, tools, agent_id="0"):
        def sync_run():
            try:
                msg = {"role": "assistant", "content": "", "tool_calls": []}
                for chunk in llm_instance.create_chat_completion(messages=msgs, tools=tools, tool_choice="auto" if tools else None, stream=True):
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    if "content" in delta and delta["content"]:
                        msg["content"] += delta["content"]
                        self.signals.chunk_received.emit(agent_id, delta["content"], 0)
                        
                    if "tool_calls" in delta and delta["tool_calls"]:
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            while len(msg["tool_calls"]) <= idx:
                                msg["tool_calls"].append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            acc = msg["tool_calls"][idx]
                            for k, v in tc.items():
                                if k == "index": continue
                                if k == "function" and isinstance(v, dict):
                                    for fk, fv in v.items():
                                        if fv is not None: acc["function"][fk] = acc["function"].get(fk, "") + str(fv)
                                elif v is not None:
                                    if k == "type": acc[k] = v
                                    elif k == "id": acc[k] = acc.get(k, "") + str(v)
                                    else: acc[k] = acc.get(k, "") + str(v)

                # Fallback parser
                if not msg["tool_calls"] and "<tool_call>" in msg["content"]:
                    ms = re.findall(r'<tool_call>(.*?)</tool_call>', msg["content"], re.DOTALL | re.IGNORECASE)
                    for i, m in enumerate(ms):
                        m = m.strip()
                        if m.startswith('```json'): m = m[7:]
                        elif m.startswith('```'): m = m[3:]
                        if m.endswith('```'): m = m[:-3]
                        try:
                            d = json.loads(m.strip())
                            if "name" in d and "arguments" in d:
                                msg["tool_calls"].append({
                                    "id": f"call_man_{i}", "type": "function", 
                                    "function": {"name": d["name"], "arguments": json.dumps(d["arguments"])}
                                })
                        except: pass
                        
                if not msg["tool_calls"]: del msg["tool_calls"]
                else:
                    for i, tc in enumerate(msg["tool_calls"]):
                        if not tc.get("id"): tc["id"] = f"call_{i}"
                        
                self.signals.stream_finished.emit(msg, 0)
            except Exception as e:
                self.signals.error_msg.emit(f"Erro no modelo: {e}")
                self.signals.stream_finished.emit({"role": "assistant", "content": f"Erro fatal do modelo: {e}"}, 0)

        await asyncio.to_thread(sync_run)

    def on_chunk_received(self, agent_id, text, idx):
        self._current_assistant_text += text
        # We intentionally do NOT insert raw plaintext during streaming.
        # Instead, we update a simple progress indicator periodically.
        pass

    def on_stream_finished(self, msg, idx):
        # Remove the typing indicator (last block)
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.select(cursor.SelectionType.BlockUnderCursor)
        # We just append the final formatted message - the typing indicator stays as history context
        
        if msg.get("content"):
            self.messages.append({"role": "assistant", "content": msg["content"]})
            # Render the full response as a proper bubble
            self.append_chat("DuckHunt AI", msg["content"], "#FFC857")
            
        if msg.get("tool_calls"):
            if not msg.get("content"):
                self.messages.append({"role": "assistant", "tool_calls": msg["tool_calls"]})
            else:
                self.messages[-1]["tool_calls"] = msg["tool_calls"]
                
            asyncio.create_task(self.process_tools(msg["tool_calls"]))
        else:
            self.set_ui_frozen(False)

    async def process_tools(self, tool_calls):
        self.append_chat("Sistema", "Executando Ferramenta(s)...", "#A55EEA")
        try:
            for tc in tool_calls:
                tname = tc["function"]["name"]
                targs = json.loads(tc["function"]["arguments"])
                self.append_chat("⚙ Executando", f"{tname} - {json.dumps(targs, ensure_ascii=False)[:100]}...", "#FF8E53")
                
                srv = self.mcp_tools.get(tname)
                if not srv or srv not in self.mcp_sessions:
                    result_txt = "Erro: Servidor MCP não conectou para esta ferramenta."
                else:
                    sess = self.mcp_sessions[srv]
                    original_tname = self.mcp_original_names.get(tname, tname)
                    res = await sess.call_tool(original_tname, targs)
                    result_txt = "\n".join([c.text for c in res.content if c.type == "text"])
                
                if result_txt.startswith("Erro"):
                    self.append_chat("❌ Falha", result_txt, "#FF6B6B")
                else:
                    self.append_chat("✓ Concluído", f"Resultado inserido no contexto.", "#4ECB71")
                    
                self.messages.append({"role": "tool", "name": tname, "content": result_txt, "tool_call_id": tc.get("id")})
                
            self.append_chat("Sistema", "Concluído execução. Aguardando a IA...", "#A6ADC8")
            self._current_assistant_text = ""
            self.append_chat("DuckHunt AI", "", "#FFC857")
            await self.run_llm_stream(self.llm, self.messages.copy(), self.llama_tools, agent_id="0")

        except Exception as e:
            self.append_chat("❌ Erro", f"Falha na execução: {e}", "#FF6B6B")
            self.set_ui_frozen(False)

    def on_tool_execution(self, tool_info, status):
        pass

    # ========================== MODELS PAGE ==========================
    def init_models_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("🤖 Gerenciamento de Modelos / APIs")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        desc = QLabel("Adicione, remova ou selecione o modelo de IA que será usado nas conversas. Suporta OpenAI, Azure, Anthropic, Gemini e modelos locais GGUF.")
        desc.setStyleSheet("color: #6C7086; font-size: 12px; margin-bottom: 8px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.models_list = QListWidget()
        layout.addWidget(self.models_list)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        add_btn = StyledButton("➕ Adicionar API", "#4ECB71")
        add_btn.clicked.connect(self.add_new_api_dialog)
        del_btn = StyledButton("🗑 Remover", "#F38BA8")
        del_btn.clicked.connect(self.remove_api_gui)
        use_btn = StyledButton("✅ Usar Selecionado", "#45B7D1")
        use_btn.clicked.connect(self.use_selected_model)

        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(del_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(use_btn)
        layout.addLayout(btn_layout)

        self.pages.addWidget(page)

    def refresh_models_list(self):
        self.models_list.clear()
        
        api_list = []
        if os.path.exists(API_CONFIG_PATH):
            try:
                with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            for k, v in item.items(): api_list.append((k, v))
                    elif isinstance(data, dict):
                        for k, v in data.items(): api_list.append((k, v))
            except: pass

        for typ, cfg in api_list:
            n = cfg.get("deployment") or cfg.get("model") or "Unknown"
            item = QListWidgetItem(f"[{typ.upper()}] {n}")
            item.setData(Qt.ItemDataRole.UserRole, {"type": typ.lower(), "config": cfg})
            self.models_list.addItem(item)
            
        os.makedirs(MODELS_DIR, exist_ok=True)
        local_models = [f for f in os.listdir(MODELS_DIR) if f.lower().endswith(".gguf")]
        for m in local_models:
            item = QListWidgetItem(f"[LOCAL] {m}" + (" (llama-cpp indisponível)" if not LLAMA_CPP_AVAILABLE else ""))
            item.setData(Qt.ItemDataRole.UserRole, {"type": "local", "name": m})
            if not LLAMA_CPP_AVAILABLE: item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.models_list.addItem(item)

    def add_new_api_dialog(self):
        d = QDialog(self)
        d.setWindowTitle("Adicionar API")
        layout = QFormLayout(d)
        
        type_cb = QComboBox()
        type_cb.addItems(["OpenAI", "Azure", "Anthropic", "Gemini"])
        layout.addRow("Tipo de API:", type_cb)
        
        model_edit = QLineEdit()
        layout.addRow("Nome do Modelo / Deployment:", model_edit)
        
        api_key_edit = QLineEdit()
        api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("API Key:", api_key_edit)
        
        endpoint_edit = QLineEdit()
        endpoint_edit.setPlaceholderText("Apenas para Azure (inclui api_version)")
        layout.addRow("Endpoint (Azure):", endpoint_edit)
        
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(d.accept)
        btns.rejected.connect(d.reject)
        layout.addRow(btns)
        
        if d.exec() == QDialog.DialogCode.Accepted:
            t = type_cb.currentText()
            m = model_edit.text()
            ak = api_key_edit.text()
            ep = endpoint_edit.text()
            
            cfg = {"api_key": ak}
            if t == "Azure":
                cfg["deployment"] = m
                cfg["endpoint"] = ep
            else:
                cfg["model"] = m
                
            entry = {t: cfg}
            
            data = []
            if os.path.exists(API_CONFIG_PATH):
                with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                    try: 
                        lst = json.load(f)
                        data = lst if isinstance(lst, list) else [lst]
                    except: pass
            data.append(entry)
            with open(API_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
                
            QMessageBox.information(self, "Sucesso", f"API {t} adicionada!")
            self.refresh_models_list()

    def remove_api_gui(self):
        item = self.models_list.currentItem()
        if not item: return
        data = item.data(Qt.ItemDataRole.UserRole)
        if data["type"] == "local":
            QMessageBox.warning(self, "Erro", "Modelos locais devem ser excluídos a partir da pasta manuais.")
            return
            
        # Simplificação: recarregar a config, ignorar a key específica e salvar...
        QMessageBox.warning(self, "Aviso", "Remoção via UI ainda em testes. Edite models/api_config.json manualmente por hora.")
        
    def use_selected_model(self):
        item = self.models_list.currentItem()
        if not item: return
        data = item.data(Qt.ItemDataRole.UserRole)
        
        m_type = data["type"]
        if m_type == "local":
            m_name = data["name"]
            save_config("Model", "type", "local")
            save_config("Model", "name", m_name)
            save_config("Model", "path", os.path.join(MODELS_DIR, m_name))
        else:
            cfg = data["config"]
            m_name = cfg.get("deployment") or cfg.get("model")
            save_config("Model", "type", m_type)
            save_config("Model", "name", m_name)
        
        QMessageBox.information(self, "Sucesso", f"Modelo {m_name} definido como ativo. As alterações tomam pleno efeito após reiniciar o sistema.")
        self._update_indicators()
        
    # ========================== AGENTS PAGE ==========================
    def init_agents_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("🎯 Agentes Personalizados")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        desc = QLabel("Selecione um agente (.md) da pasta agents/ para personalizar o comportamento da IA. Cada agente tem instruções específicas.")
        desc.setStyleSheet("color: #6C7086; font-size: 12px; margin-bottom: 8px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.agents_list = QListWidget()
        layout.addWidget(self.agents_list)

        use_btn = StyledButton("✅ Ativar Agente Selecionado", "#A55EEA")
        use_btn.clicked.connect(self.use_selected_agent)
        layout.addWidget(use_btn)
        self.pages.addWidget(page)

    def refresh_agents_list(self):
        self.agents_list.clear()
        if os.path.exists(AGENTS_DIR):
            for f in os.listdir(AGENTS_DIR):
                if f.lower().endswith(".md"):
                    self.agents_list.addItem(f)

    def use_selected_agent(self):
        item = self.agents_list.currentItem()
        if not item: return
        fname = item.text()
        save_config("Agent", "filename", fname)
        with open(os.path.join(AGENTS_DIR, fname), "r", encoding="utf-8") as f:
            self.agent_prompt_text = f.read()
        self.reset_context()
        self._update_indicators()
        QMessageBox.information(self, "Sucesso", f"Agente '{fname}' ativado com sucesso!")

    # ========================== MULTI-AGENT PAGE ==========================
    AGENT_COLORS = ["#45B7D1", "#FF8E53", "#A55EEA", "#4ECB71", "#F9E2AF", "#F38BA8", "#89B4FA"]
    AGENT_ICONS = {"product_owner": "📋", "dev_sr": "💻", "qa_analyst": "🧪", "plan": "📐",
                   "ui_designer": "🎨", "agent": "🤖", "ask": "❓"}

    def init_multi_agent_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title = QLabel("👥 Colaboração Multi-Agente")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        desc = QLabel("Selecione os agentes que participarão da missão. Eles irão colaborar autonomamente, usando ferramentas MCP e se comunicando entre si até concluir a tarefa.")
        desc.setStyleSheet("color: #6C7086; font-size: 12px; margin-bottom: 4px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # --- Agent selection area (scroll) ---
        agents_group = QGroupBox("🎯 Selecionar Agentes")
        agents_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #313244; border-radius: 8px; margin-top: 10px; padding-top: 16px; } QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }")
        agents_scroll = QScrollArea()
        agents_scroll.setWidgetResizable(True)
        agents_scroll.setMaximumHeight(200)
        agents_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.agents_cards_container = QWidget()
        self.agents_cards_layout = QHBoxLayout(self.agents_cards_container)
        self.agents_cards_layout.setSpacing(10)
        self.agents_cards_layout.setContentsMargins(4, 4, 4, 4)
        agents_scroll.setWidget(self.agents_cards_container)
        ag_inner = QVBoxLayout(agents_group)
        ag_inner.addWidget(agents_scroll)
        layout.addWidget(agents_group)

        self.multi_agent_checkboxes = []

        # --- Task input ---
        task_group = QGroupBox("📝 Tarefa Principal")
        task_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #313244; border-radius: 8px; margin-top: 6px; padding-top: 14px; } QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }")
        task_inner = QVBoxLayout(task_group)
        from PyQt6.QtWidgets import QTextEdit
        self.multi_task_input = QTextEdit()
        self.multi_task_input.setPlaceholderText("Descreva a tarefa que a equipe de agentes deve resolver colaborativamente...")
        self.multi_task_input.setMaximumHeight(80)
        self.multi_task_input.setStyleSheet("QTextEdit { background-color: #313244; border: 2px solid #45475A; border-radius: 8px; padding: 8px; font-size: 13px; color: #CDD6F4; } QTextEdit:focus { border: 2px solid #FFC857; }")
        task_inner.addWidget(self.multi_task_input)
        layout.addWidget(task_group)

        # --- Controls ---
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)
        self.multi_start_btn = StyledButton("🚀 Iniciar Colaboração", "#FFC857")
        self.multi_start_btn.clicked.connect(self.start_multi_agent)
        self.multi_stop_btn = StyledButton("⏹ Parar", "#F38BA8")
        self.multi_stop_btn.setEnabled(False)
        self.multi_stop_btn.clicked.connect(self.stop_multi_agent)
        self.multi_round_label = QLabel("")
        self.multi_round_label.setStyleSheet("color: #6C7086; font-size: 12px;")
        ctrl.addWidget(self.multi_start_btn)
        ctrl.addWidget(self.multi_stop_btn)
        ctrl.addStretch()
        ctrl.addWidget(self.multi_round_label)
        layout.addLayout(ctrl)

        # --- Output ---
        self.multi_agent_output = QTextBrowser()
        self.multi_agent_output.setOpenExternalLinks(True)
        self.multi_agent_output.setStyleSheet("QTextBrowser { background-color: #181825; border: 1px solid #313244; border-radius: 10px; font-size: 13px; padding: 10px; color: #CDD6F4; }")
        layout.addWidget(self.multi_agent_output)

        self.pages.addWidget(page)
        self._multi_running = False

        # Load agents on first navigation
        QTimer.singleShot(500, self._load_agent_cards)

    def _extract_agent_title(self, filepath):
        """Extract first heading from .md file as agent title."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#'):
                        return line.lstrip('#').strip().replace('AI Agent Specification: ', '').replace('\\#', '').strip()
            return os.path.basename(filepath).replace('.md', '')
        except Exception:
            return os.path.basename(filepath).replace('.md', '')

    def _load_agent_cards(self):
        # Clear existing
        for cb in self.multi_agent_checkboxes:
            cb.setParent(None)
        self.multi_agent_checkboxes = []

        if not os.path.exists(AGENTS_DIR):
            return

        agents_files = sorted([f for f in os.listdir(AGENTS_DIR) if f.lower().endswith(".md")])

        for idx, fname in enumerate(agents_files):
            color = self.AGENT_COLORS[idx % len(self.AGENT_COLORS)]
            base = fname.replace('.md', '')
            icon = self.AGENT_ICONS.get(base, "🤖")
            title = self._extract_agent_title(os.path.join(AGENTS_DIR, fname))

            card = QWidget()
            card.setMinimumWidth(150)
            card.setMaximumWidth(200)
            card.setStyleSheet(f"""
                QWidget {{
                    background-color: #232336;
                    border: 2px solid #313244;
                    border-radius: 10px;
                    padding: 8px;
                }}
                QWidget:hover {{
                    border: 2px solid {color};
                }}
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 8, 8, 8)
            card_layout.setSpacing(4)

            icon_lbl = QLabel(icon)
            icon_lbl.setFont(QFont("Segoe UI", 22))
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(icon_lbl)

            name_lbl = QLabel(base.replace('_', ' ').title())
            name_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_lbl.setStyleSheet(f"color: {color}; background: transparent; border: none;")
            card_layout.addWidget(name_lbl)

            role_lbl = QLabel(title[:40] + ("..." if len(title) > 40 else ""))
            role_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            role_lbl.setStyleSheet("color: #6C7086; font-size: 10px; background: transparent; border: none;")
            role_lbl.setWordWrap(True)
            card_layout.addWidget(role_lbl)

            cb = QCheckBox("Selecionar")
            cb.setStyleSheet(f"QCheckBox {{ color: #A6ADC8; font-size: 11px; background: transparent; border: none; }} QCheckBox::indicator:checked {{ background-color: {color}; border-radius: 3px; }}")
            cb.setProperty("agent_file", fname)
            cb.setProperty("agent_color", color)
            card_layout.addWidget(cb, alignment=Qt.AlignmentFlag.AlignCenter)

            self.agents_cards_layout.addWidget(card)
            self.multi_agent_checkboxes.append(cb)

        self.agents_cards_layout.addStretch()

    def _ma_append(self, sender, text, color="#CDD6F4"):
        """Append msg to multi-agent output."""
        html = self.render_markdown(text) if not text.startswith("<") else text
        bubble = f"""
        <div style="margin: 6px 0;">
            <div style="background-color: #232336; border-left: 3px solid {color}; border-radius: 0 8px 8px 0; padding: 8px 12px;">
                <span style="font-size: 12px; font-weight: bold; color: {color};">{sender}</span><br>
                <span style="color: #CDD6F4; font-size: 13px;">{html}</span>
            </div>
        </div>
        """
        self.multi_agent_output.append(bubble)
        sb = self.multi_agent_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def stop_multi_agent(self):
        self._multi_running = False

    def start_multi_agent(self):
        if not self.llm:
            self.show_error("Nenhum modelo IA carregado! Acesse a aba 'Modelos' e selecione um modelo.")
            return

        task = self.multi_task_input.toPlainText().strip()
        if not task:
            self.show_error("Informe a tarefa principal para os agentes!")
            return

        # Gather selected agents
        selected = []
        for cb in self.multi_agent_checkboxes:
            if cb.isChecked():
                fname = cb.property("agent_file")
                color = cb.property("agent_color")
                base = fname.replace('.md', '')
                try:
                    with open(os.path.join(AGENTS_DIR, fname), 'r', encoding='utf-8') as f:
                        prompt = f.read()
                except Exception:
                    prompt = self.agent_prompt_text
                selected.append({"name": base.replace('_', ' ').title(), "file": fname, "prompt": prompt, "color": color})

        if len(selected) < 2:
            self.show_error("Selecione pelo menos 2 agentes para a colaboração multi-agente!")
            return

        self.multi_agent_output.clear()
        self._multi_running = True
        self.multi_start_btn.setEnabled(False)
        self.multi_stop_btn.setEnabled(True)

        nomes = ", ".join([a["name"] for a in selected])
        self._ma_append("🚀 Sistema", f"Iniciando colaboração multi-agente!<br><b>Equipe:</b> {nomes}<br><b>Missão:</b> {task}", "#FFC857")

        create_checkpoint(self.workspace_dir)
        asyncio.ensure_future(self._run_multi_agent_loop(selected, task))

    async def _run_multi_agent_loop(self, agents, task):
        n = len(agents)
        nomes = [a["name"] for a in agents]

        shared_history = [
            {"role": "user", "content": f"TAREFA PRINCIPAL: {task}\n\nVocês são a seguinte equipe: {', '.join(nomes)}.\nTrabalhem juntos, discutindo e resolvendo a demanda do usuário. Usem as ferramentas MCP à disposição se precisarem interagir com arquivos.\n\nREGRAS DE COLABORAÇÃO:\n1. NÃO tomem decisões unilaterais fora da sua função. Cada agente tem um papel específico.\n2. Se você precisa que outro agente faça uma parte do trabalho, FAÇA A PASSAGEM DE FORMA CLARA.\n\nIMPORTANTE: Quando a equipe concluir 100% da Tarefa Principal e todos concordarem que nada mais precisa ser feito, qualquer agente pode incluir [TASK_COMPLETED] na sua resposta para encerrar."}
        ]

        round_idx = 0
        try:
            while self._multi_running:
                round_idx += 1
                self.multi_round_label.setText(f"🔄 Rodada {round_idx}")
                self._ma_append("⚡ Sistema", f"--- Rodada {round_idx} ---", "#45475A")

                # Run each agent concurrently
                async def run_agent(i):
                    a = agents[i]
                    sys_prompt = f"{self.compor_prompt_with(a['prompt'])}\n\n[Você é o '{a['name']}' nesta rodada da equipe. Use [TASK_COMPLETED] se a missão estiver concluída.]"
                    msgs = [{"role": "system", "content": sys_prompt}] + list(shared_history)

                    msg = {"role": "assistant", "content": "", "tool_calls": []}
                    def sync_stream():
                        for chunk in self.llm.create_chat_completion(messages=msgs, tools=self.llama_tools, tool_choice="auto" if self.llama_tools else None, max_tokens=2048, stream=True):
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                msg["content"] += delta["content"]
                            if "tool_calls" in delta and delta["tool_calls"]:
                                for tc in delta["tool_calls"]:
                                    idx = tc.get("index", 0)
                                    while len(msg["tool_calls"]) <= idx:
                                        msg["tool_calls"].append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                                    acc = msg["tool_calls"][idx]
                                    for k, v in tc.items():
                                        if k == "index": continue
                                        if k == "function" and isinstance(v, dict):
                                            for fk, fv in v.items():
                                                if fv is not None: acc["function"][fk] = acc["function"].get(fk, "") + str(fv)
                                        elif v is not None:
                                            if k == "type": acc[k] = v
                                            elif k == "id": acc[k] = acc.get(k, "") + str(v)
                                            else: acc[k] = acc.get(k, "") + str(v)

                        if not msg["tool_calls"]: del msg["tool_calls"]
                        else:
                            for j, tc in enumerate(msg["tool_calls"]):
                                if not tc.get("id"): tc["id"] = f"call_m{i}_{j}"
                        return msg

                    return await asyncio.to_thread(sync_stream)

                tasks_list = [asyncio.create_task(run_agent(i)) for i in range(n)]
                results = await asyncio.gather(*tasks_list, return_exceptions=True)

                if not self._multi_running:
                    break

                task_completed = False
                for i, res in enumerate(results):
                    a = agents[i]
                    if isinstance(res, Exception):
                        self._ma_append(f"❌ {a['name']}", f"Erro: {res}", "#F38BA8")
                        continue

                    content = res.get("content", "").strip()
                    if content:
                        self._ma_append(f"{self.AGENT_ICONS.get(a['file'].replace('.md',''), '🤖')} {a['name']}", content, a["color"])
                        shared_history.append({"role": "assistant", "content": f"[{a['name']} comentou]:\n{content}"})
                    else:
                        shared_history.append({"role": "assistant", "content": f"[{a['name']} chamou ferramentas]"})

                    if res.get("tool_calls"):
                        if not content:
                            shared_history[-1]["tool_calls"] = res["tool_calls"]
                        for tc in res["tool_calls"]:
                            tname = tc.get("function", {}).get("name", "")
                            try:
                                targs = json.loads(tc.get("function", {}).get("arguments", "{}"))
                                self._ma_append(f"⚙️ {a['name']}", f"Executando <b>{tname}</b>...", "#FF8E53")
                                srv = self.mcp_tools.get(tname)
                                if srv and srv in self.mcp_sessions:
                                    original_tname = self.mcp_original_names.get(tname, tname)
                                    tool_res = await self.mcp_sessions[srv].call_tool(original_tname, targs)
                                    t_out = "\n".join([c.text for c in tool_res.content if c.type == "text"])
                                    self._ma_append(f"✅ {a['name']}", f"<b>{tname}</b> concluído.", "#4ECB71")
                                    shared_history.append({"role": "tool", "name": tname, "content": f"Resultado de {tname}:\n{t_out}", "tool_call_id": tc.get("id")})
                                else:
                                    shared_history.append({"role": "tool", "name": tname, "content": "Erro: MCP inativo", "tool_call_id": tc.get("id")})
                                    self._ma_append(f"❌ {a['name']}", f"<b>{tname}</b>: MCP inativo.", "#F38BA8")
                            except Exception as e:
                                shared_history.append({"role": "tool", "name": tname, "content": f"Erro: {e}", "tool_call_id": tc.get("id")})
                                self._ma_append(f"❌ {a['name']}", f"Erro em {tname}: {e}", "#F38BA8")

                    if "[TASK_COMPLETED]" in content:
                        task_completed = True

                if task_completed:
                    self._ma_append("🏁 Sistema", "Tarefa marcada como concluída pela equipe! Encerrando colaboração.", "#4ECB71")
                    break

        except Exception as e:
            self._ma_append("❌ Sistema", f"Erro fatal: {e}", "#F38BA8")
        finally:
            self._multi_running = False
            self.multi_start_btn.setEnabled(True)
            self.multi_stop_btn.setEnabled(False)
            self.multi_round_label.setText("✅ Finalizado")

    def compor_prompt_with(self, agent_prompt):
        """Compose prompt with a specific agent's prompt text + active skills."""
        base = agent_prompt or ""
        if not self.skills_prompts: return base
        partes = [base, "\n\n### ACTIVE SKILLS\n"]
        for sp in self.skills_prompts:
            partes.append(f"\n--- Skill: {sp.get('name')} ---\n[Base Directory]: {sp.get('path')}\n{sp.get('content')}\n")
        return "".join(partes)

    # ========================== MCP PAGE ==========================
    def init_mcp_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("🔌 Servidores MCP")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        desc = QLabel("Visualize os servidores MCP configurados. Edite diretamente o arquivo mcp/config.json para adicionar ou remover servidores.")
        desc.setStyleSheet("color: #6C7086; font-size: 12px; margin-bottom: 8px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.mcp_list = QListWidget()
        layout.addWidget(self.mcp_list)

        self.pages.addWidget(page)

    def refresh_mcp_list(self):
        self.mcp_list.clear()
        if os.path.exists(MCP_CONFIG_PATH):
            with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for k, val in cfg.get("mcpServers", {}).items():
                s = "🔴 Desativado" if val.get("disabled") else "🟢 Ativo"
                self.mcp_list.addItem(f"{k} - {s} - {val.get('command', 'HTTP')}")

    # ========================== SKILLS PAGE ==========================
    def init_skills_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("⚡ Skills / Ferramentas Extras")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)
        self.skills_list_widget = QListWidget()
        self.skills_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        layout.addWidget(self.skills_list_widget)
        
        btn = StyledButton("Salvar Skills Selectionadas", "#4ECB71")
        btn.clicked.connect(self.save_skills_selection)
        layout.addWidget(btn)
        self.pages.addWidget(page)
        
    def refresh_skills_list(self):
        self.skills_list_widget.clear()
        loaded_str = load_config("Skills", "loaded") or ""
        wanted = [x.strip() for x in loaded_str.split(',')]
        
        if os.path.exists(SKILLS_DIR):
            for root, _dirs, files in os.walk(SKILLS_DIR):
                for f in files:
                    if f.lower() == 'skill.md':
                        rel = os.path.relpath(root, SKILLS_DIR)
                        item = QListWidgetItem(rel)
                        self.skills_list_widget.addItem(item)
                        if rel in wanted: item.setSelected(True)

    def save_skills_selection(self):
        sel = [item.text() for item in self.skills_list_widget.selectedItems()]
        save_config("Skills", "loaded", ", ".join(sel))
        QMessageBox.information(self, "Skills Salvas", "Skills atualizadas. Reinicie a sessão (/new ou reiniciar GUI) para ativar.")

    # ========================== SETTINGS PAGE ==========================
    def init_settings_page(self):
        from PyQt6.QtWidgets import QFileDialog
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        title = QLabel("⚙ Configurações")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # Workspace section
        ws_group = QGroupBox("📂 Workspace (Diretório do Projeto)")
        ws_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #313244; border-radius: 8px; margin-top: 10px; padding-top: 14px; } QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }")
        ws_layout = QHBoxLayout(ws_group)
        self.ws_edit = QLineEdit(self.workspace_dir)

        browse_btn = StyledButton("📁 Procurar", "#45475A")
        browse_btn.clicked.connect(lambda: self._browse_workspace())

        upd_ws = StyledButton("✅ Salvar", "#45B7D1")
        upd_ws.clicked.connect(self.update_ws)

        ws_layout.addWidget(self.ws_edit)
        ws_layout.addWidget(browse_btn)
        ws_layout.addWidget(upd_ws)
        layout.addWidget(ws_group)

        layout.addStretch()
        self.pages.addWidget(page)

    def _browse_workspace(self):
        from PyQt6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Selecionar Pasta do Projeto", self.workspace_dir)
        if d:
            self.ws_edit.setText(d)

    def refresh_settings_view(self):
        self.ws_edit.setText(self.workspace_dir)

    def update_ws(self):
        new_ws = self.ws_edit.text()
        if os.path.exists(new_ws):
            self.workspace_dir = new_ws
            save_config("General", "workspace", new_ws)
            if "ducktools" in self.mcp_config.get("mcpServers", {}):
                self.mcp_config["mcpServers"]["ducktools"].setdefault("env", {})["WORKSPACE_DIR"] = self.workspace_dir
                with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(self.mcp_config, f, ensure_ascii=False, indent=2)
            self.status_lbl.setText("📂 " + os.path.basename(new_ws))
            QMessageBox.information(self, "Workspace", f"Workspace alterado! Reinicie o app para reconectar as ferramentas MCP.")
        else:
            QMessageBox.critical(self, "Workspace", "Diretório não encontrado!")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    gui = DuckHuntGUI()
    gui.show()

    with loop:
        loop.run_forever()
