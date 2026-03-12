import sys
import os
import random
import math
import pygame
import json
import threading
import queue

# Inicialização do Pygame
pygame.init()

# Constantes
FPS = 60
BACKGROUND_COLOR = (135, 206, 235)  # Azul céu (fundo)
FLOOR_COLOR = (100, 200, 100)       # Verde do gramado/piso

# Posições dos patos
SITTING_POSITIONS = [
    (162, 390), (162, 571),
    (524, 390), (524, 571),
    (844, 390), (844, 571),
    (1158, 390), (1158, 571)
]

# Caminhos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPRITE_PATH = os.path.join(BASE_DIR, "sprites", "ducks.png")
BACKGROUND_PATH = os.path.join(BASE_DIR, "sprites", "background.png")

# Setup da tela
try:
    bg_image = pygame.image.load(BACKGROUND_PATH)
    WIDTH, HEIGHT = bg_image.get_width(), bg_image.get_height()
except Exception as e:
    print(f"Erro ao carregar o fundo: {e}")
    bg_image = None
    WIDTH, HEIGHT = 1366, 768

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Duck Room Interativo (Office AI Agents)")
clock = pygame.time.Clock()

if bg_image:
    bg_image = bg_image.convert()

# Carregando o sprite dos patos
try:
    sheet = pygame.image.load(SPRITE_PATH).convert_alpha()
    
    # Cada frame do pato tem aproximadamente 32x32.
    FRAME_WIDTH = 32
    FRAME_HEIGHT = 32
    
    walk_right_frames = []
    walk_left_frames = []
    
    max_size = 64 # Vamos redimensionar para 64x64
    
    # A linha 2 (index 2) possui 6 frames (andando para a direita)
    for col in range(6):
        rect = pygame.Rect(col * FRAME_WIDTH, 2 * FRAME_HEIGHT, FRAME_WIDTH, FRAME_HEIGHT)
        frame = pygame.Surface((FRAME_WIDTH, FRAME_HEIGHT), pygame.SRCALPHA)
        frame.blit(sheet, (0, 0), rect)
        frame = pygame.transform.smoothscale(frame, (max_size, max_size))
        walk_right_frames.append(frame)
        
    # A linha 3 (index 3) possui 6 frames (andando para a esquerda)
    for col in range(6):
        rect = pygame.Rect(col * FRAME_WIDTH, 3 * FRAME_HEIGHT, FRAME_WIDTH, FRAME_HEIGHT)
        frame = pygame.Surface((FRAME_WIDTH, FRAME_HEIGHT), pygame.SRCALPHA)
        frame.blit(sheet, (0, 0), rect)
        frame = pygame.transform.smoothscale(frame, (max_size, max_size))
        walk_left_frames.append(frame)
        
    if not walk_right_frames:
        raise ValueError("Frames não encontrados.")
        
except Exception as e:
    print(f"Erro ao carregar o sprite do pato: {e}")
    # Fallback
    fallback_surface = pygame.Surface((64, 64))
    fallback_surface.fill((255, 105, 180))
    walk_right_frames = [fallback_surface]
    walk_left_frames = [fallback_surface]

# Fonte para os balões de diálogo
font = pygame.font.SysFont("comicsansms", 14, bold=True)

# Mensagens que os patos podem falar
MESSAGES = [
    "Quack!", 
    "Quack quack?", 
    "Quack.", 
    "Honk?", 
    "*waddle*", 
    "Tem pão?",
    "Que dia lindo!",
    "Bora nadar?"
]

class Duck:
    def __init__(self, duck_id):
        self.duck_id = duck_id
        self.frame_index = 0
        self.animation_speed = 0.05 + random.uniform(0.01, 0.03) 
        
        self.facing_right = True
        self.frames = walk_right_frames
        self.image = self.frames[int(self.frame_index)]
        self.rect = self.image.get_rect()
        
        # Estado e Movimentação
        self.base_pos = SITTING_POSITIONS[duck_id % len(SITTING_POSITIONS)]
        self.rect.centerx = self.base_pos[0]
        self.rect.bottom = self.base_pos[1]
        self.state = 0 # 0=WORKING, 1=WALKING, 2=IDLING, 3=RETURNING
        self.target_pos = None
        self.state_timer = 0
        
        self.message = ""
        self.message_timer = 0
        self.last_stream_text = ""

    def update(self):
        if self.message_timer > 0:
            self.message_timer -= 1
        else:
            self.message = ""

        if self.state == 0: # WORKING
            self.frame_index += self.animation_speed
            if self.frame_index >= len(self.frames):
                self.frame_index = 0
                
            # Interação aleatória (Levantar da mesa e andar)
            # Chance ligeiramente aumentada se não tem mensagem rodando
            if self.message_timer == 0 and random.random() < 0.001: 
                self.state = 1 # WALKING
                # Vai para áreas livres ou visitar um colega na mesa
                if random.random() < 0.6:
                    self.target_pos = random.choice([(100, 315), (700, 315), (1250, 315), (100, 490), (700, 490), (1250, 490)])
                else:
                    target_desk = random.choice(SITTING_POSITIONS)
                    self.target_pos = (target_desk[0] - 40, target_desk[1] + random.randint(-15, 15))
                self.update_facing()

        elif self.state in [1, 3]: # WALKING or RETURNING
            self.move_towards(self.target_pos)
            self.frame_index += 0.15 # Anda mais rápido
            if self.frame_index >= len(self.frames):
                self.frame_index = 0
                
            if self.at_target():
                if self.state == 1:
                    self.state = 2 # IDLING no lugar
                    self.state_timer = int(FPS * random.uniform(3, 8))
                    self.facing_right = random.choice([True, False])
                    self.update_frames()
                    if random.random() < 0.3: # Chance de soltar um balão de conversa random aqui
                        self.message = random.choice(MESSAGES)
                        self.message_timer = int(FPS * 3)
                elif self.state == 3:
                    self.state = 0 # DE VOLTA AO TRABALHO
                    self.facing_right = True # vira para a mesa
                    self.update_frames()

        elif self.state == 2: # IDLING
            self.frame_index += self.animation_speed
            if self.frame_index >= len(self.frames):
                self.frame_index = 0
            
            self.state_timer -= 1
            if self.state_timer <= 0:
                self.state = 3 # RETURNING
                self.target_pos = self.base_pos
                self.update_facing()
                
        self.image = self.frames[int(self.frame_index) % len(self.frames)]

    def move_towards(self, pos):
        dx = pos[0] - self.rect.centerx
        dy = pos[1] - self.rect.bottom
        dist = math.hypot(dx, dy)
        speed = 2
        if dist < speed:
            self.rect.centerx = pos[0]
            self.rect.bottom = pos[1]
        else:
            self.rect.centerx += int(speed * dx / dist)
            self.rect.bottom += int(speed * dy / dist)

    def at_target(self):
        return self.rect.centerx == self.target_pos[0] and self.rect.bottom == self.target_pos[1]

    def update_facing(self):
        self.facing_right = self.target_pos[0] > self.rect.centerx
        self.update_frames()

    def update_frames(self):
        self.frames = walk_right_frames if self.facing_right else walk_left_frames

    def draw(self, surface):
        surface.blit(self.image, self.rect)
        if self.message:
            self.draw_speech_bubble(surface)
            
    def draw_speech_bubble(self, surface):
        if not self.message:
            return
            
        # Quebra a string em múltiplas linhas baseada no tamanho do texto para efeito "stream"
        words = self.message.split(' ')
        lines = []
        current_line = []
        max_width = 250
        
        for word in words:
            # Dividir palavras muito longas que porventura não tenham espaço
            if not current_line and font.size(word)[0] > max_width:
                lines.append(word[:20] + "-") # Exemplo simples de quebra
                continue

            current_line.append(word)
            text_w, _ = font.size(' '.join(current_line))
            if text_w > max_width:
                current_line.pop()
                lines.append(' '.join(current_line))
                current_line = [word]
                
        if current_line:
            lines.append(' '.join(current_line))
            
        # Limita para as últimas linhas pra não tapar a tela inteira quando o stream for longo
        max_lines = 8
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
            
        line_surfaces = [font.render(line, True, (0, 0, 0)) for line in lines]
        if not line_surfaces:
            return
            
        max_line_width = max(surf.get_width() for surf in line_surfaces)
        total_height = sum(surf.get_height() for surf in line_surfaces)
        
        text_rect = pygame.Rect(0, 0, max_line_width, total_height)
        text_rect.centerx = self.rect.centerx
        text_rect.bottom = self.rect.top - 15
        
        bubble_rect = text_rect.copy()
        bubble_rect.inflate_ip(20, 15)
        
        # Garante que o balão não saia muito pelos lados
        screen_width = surface.get_width()
        if bubble_rect.left < 5:
            delta = 5 - bubble_rect.left
            bubble_rect.x += delta
            text_rect.x += delta
        elif bubble_rect.right > screen_width - 5:
            delta = bubble_rect.right - (screen_width - 5)
            bubble_rect.x -= delta
            text_rect.x -= delta
        
        # Fundo arredondado
        pygame.draw.rect(surface, (255, 255, 255), bubble_rect, border_radius=10)
        pygame.draw.rect(surface, (0, 0, 0), bubble_rect, 2, border_radius=10)
        
        # Pontinha apontando pro patinho
        polygon_points = [
            (self.rect.centerx - 8, bubble_rect.bottom - 2),
            (self.rect.centerx + 8, bubble_rect.bottom - 2),
            (self.rect.centerx, self.rect.top - 5)
        ]
        # Restringe pontinha pra ficar dentro da base do balao horizontalmente
        polygon_points[0] = (max(bubble_rect.left + 5, polygon_points[0][0]), polygon_points[0][1])
        polygon_points[1] = (min(bubble_rect.right - 5, polygon_points[1][0]), polygon_points[1][1])
        
        pygame.draw.polygon(surface, (255, 255, 255), polygon_points)
        pygame.draw.polygon(surface, (0, 0, 0), polygon_points, 2)
        
        # Render linhas
        y_offset = text_rect.y
        for surf in line_surfaces:
            surface.blit(surf, (text_rect.x, y_offset))
            y_offset += surf.get_height()


class DuckRoom:
    def __init__(self, agent_mode=False, num_ducks=8):
        self.ducks = [Duck(i) for i in range(num_ducks)]
        self.agent_mode = agent_mode
        self.msg_queue = queue.Queue()
        self.current_task = ""
        if self.agent_mode:
            self.thread = threading.Thread(target=self.read_stdin, daemon=True)
            self.thread.start()

    def read_stdin(self):
        try:
            for line in iter(sys.stdin.readline, ''):
                if not line.strip(): continue
                data = json.loads(line)
                self.msg_queue.put(data)
        except Exception:
            pass

    def run(self):
        running = True
        while running:
            # Gerenciamento de eventos
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            # Atualização da lógica dos patos
            for duck in self.ducks:
                duck.update()

            # Processa as mensagens da fila no modo agente
            if self.agent_mode:
                while not self.msg_queue.empty():
                    msg_data = self.msg_queue.get_nowait()
                    
                    msg_type = msg_data.get("type", "message")
                    if msg_type == "task":
                        self.current_task = msg_data.get("message", "")
                        continue
                        
                    duck_idx = msg_data.get("duck", 0) % len(self.ducks)
                    text = msg_data.get("message", "")
                    
                    duck = self.ducks[duck_idx]
                    
                    # Força o pato agente a voltar pro lugar se for chamado pra falar
                    if duck.state != 0:
                        duck.state = 3
                        duck.target_pos = duck.base_pos
                        duck.update_facing()
                    
                    # Atualiza o texto da mensagem e mantemos visível (para suportar stream longo)
                    duck.message = text
                    # Reseta timer enquanto a mensagem não esvaziar
                    duck.message_timer = int(FPS * 10) 

            # Checando interações de diálogo entre os patos (somente se não estiver em agent_mode ou como filler)
            if not self.agent_mode:
                self.check_interactions()

            # Desenho (Renderização)
            if globals().get('bg_image'):
                screen.blit(bg_image, (0, 0))
            else:
                screen.fill(BACKGROUND_COLOR)
                # Piso para parecer um "Room"
                floor_rect = (0, HEIGHT // 2 + 50, WIDTH, HEIGHT // 2 - 50)
                pygame.draw.rect(screen, FLOOR_COLOR, floor_rect)
                # Linha de horizonte
                pygame.draw.line(screen, (80, 160, 80), (0, HEIGHT // 2 + 50), (WIDTH, HEIGHT // 2 + 50), 3)
            
            # Ordena e desenha patos baseado na coordenada Y (Efeito de profundidade/3D)
            self.ducks.sort(key=lambda d: d.rect.bottom)
            for duck in self.ducks:
                duck.draw(screen)
                
            if getattr(self, "current_task", ""):
                self.draw_task_box(screen)

            # Atualiza display e controla FPS
            pygame.display.flip()
            clock.tick(FPS)

        pygame.quit()

    def draw_task_box(self, surface):
        if not self.current_task: return
        
        font_task = pygame.font.SysFont("comicsansms", 20, bold=True)
        max_width = 800
        words = self.current_task.split(' ')
        lines = []
        current_line = []
        for word in words:
            current_line.append(word)
            w, _ = font_task.size(' '.join(current_line))
            if w > max_width - 40:
                current_line.pop()
                lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))
            
        line_surfaces = [font_task.render(line, True, (0, 0, 0)) for line in lines]
        max_w = max((surf.get_width() for surf in line_surfaces), default=0)
        total_h = sum(surf.get_height() for surf in line_surfaces)
        
        # Evita bugs visuais se max_w não tiver um valor alto default
        if max_w < 200: max_w = 200
        box_w = max_w + 50
        box_h = total_h + 30
        box_rect = pygame.Rect(surface.get_width() // 2 - box_w // 2, 20, box_w, box_h)
        
        # Fundo do aviso
        pygame.draw.rect(surface, (255, 255, 240), box_rect, border_radius=15)
        pygame.draw.rect(surface, (100, 100, 100), box_rect, 3, border_radius=15)
        
        # Pinos amarelos tipo post-it / task label (Opcional, decorativo)
        title_surf = font.render("CURRENT TASK", True, (255, 80, 80))
        surface.blit(title_surf, (box_rect.x + 15, box_rect.y + 5))
        pygame.draw.line(surface, (200, 200, 200), (box_rect.x + 10, box_rect.y + 25), (box_rect.right - 10, box_rect.y + 25), 2)
        
        y_offset = box_rect.y + 35
        for surf in line_surfaces:
            surface.blit(surf, (box_rect.centerx - surf.get_width() // 2, y_offset))
            y_offset += surf.get_height()

    def check_interactions(self):
        for i in range(len(self.ducks)):
            d1 = self.ducks[i]
            # Em modo parado nas mesas, a interação será simulada apenas com balões, sem mover os patos.
            if d1.message_timer == 0 and random.random() < 0.005: 
                d1.message = random.choice(MESSAGES)
                d1.message_timer = int(FPS * 3.5)
                
                # Opcional: outro responde
                for j in range(len(self.ducks)):
                    if i != j:
                        d2 = self.ducks[j]
                        dist = math.hypot(d1.rect.centerx - d2.rect.centerx, d1.rect.centery - d2.rect.centery)
                        if dist < 200 and d2.message_timer == 0 and random.random() < 0.5:
                            options = [m for m in MESSAGES if m != d1.message]
                            d2.message = random.choice(options)
                            d2.message_timer = int(FPS * 3.5)

if __name__ == "__main__":
    agent_mode = "--agent-mode" in sys.argv
    
    num_ducks = 8
    if "--ducks" in sys.argv:
        try:
            idx = sys.argv.index("--ducks")
            num_ducks = int(sys.argv[idx+1])
        except (ValueError, IndexError):
            pass
            
    print("Iniciando a sala dos patos... Pressione Fechar na janela para sair.")
    room = DuckRoom(agent_mode=agent_mode, num_ducks=num_ducks)
    room.run()
