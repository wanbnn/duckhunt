import sys
import random
import math
import pygame
import json
import threading
import queue

# Inicialização do Pygame
pygame.init()

# Constantes
WIDTH, HEIGHT = 800, 600
FPS = 60
BACKGROUND_COLOR = (135, 206, 235)  # Azul céu (fundo)
FLOOR_COLOR = (100, 200, 100)       # Verde do gramado/piso
DUCK_SPEED = 2
INTERACTION_DISTANCE = 150

# Caminho do Sprite
SPRITE_PATH = "sprites/LeUkV4.png"

# Setup da tela
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Duck Room Interativo")
clock = pygame.time.Clock()

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
    def __init__(self):
        self.frame_index = 0
        self.animation_speed = 0.15 + random.uniform(-0.05, 0.05)
        
        # Vetor de direção aleatória
        angle = random.uniform(0, 2 * math.pi)
        self.vx = math.cos(angle) * DUCK_SPEED
        self.vy = math.sin(angle) * DUCK_SPEED
        
        self.facing_right = self.vx > 0
        self.frames = walk_right_frames if self.facing_right else walk_left_frames
        self.image = self.frames[int(self.frame_index)]
        
        self.rect = self.image.get_rect()
        # Inicia numa posição aleatória dentro do piso
        self.rect.x = random.randint(0, WIDTH - self.rect.width)
        self.rect.y = random.randint(HEIGHT // 2, HEIGHT - self.rect.height)
        
        self.message = ""
        self.message_timer = 0

    def update(self):
        # Movimentação e animação
        if self.message_timer == 0:
            self.rect.x += self.vx
            self.rect.y += self.vy
            
            # Anima os sprites
            self.frame_index += self.animation_speed
            if self.frame_index >= len(self.frames):
                self.frame_index = 0
        else:
            # Se ele para, volta pro frame 0 (idle)
            self.frame_index = 0
            
        # Comportamento: 1% de chance de mudar de direção aleatoriamente
        if random.random() < 0.01:
            angle = random.uniform(0, 2 * math.pi)
            self.vx = math.cos(angle) * DUCK_SPEED
            self.vy = math.sin(angle) * DUCK_SPEED
            self.update_facing()

        # Colisões com as bordas da tela
        if self.rect.left < 0 or self.rect.right > WIDTH:
            self.vx *= -1
            self.rect.x = max(0, min(self.rect.x, WIDTH - self.rect.width))
            self.update_facing()
            
        # Manter os patos dentro da parte inferior ("piso") do ambiente
        floor_top = HEIGHT // 2 - 50
        if self.rect.top < floor_top or self.rect.bottom > HEIGHT:
            self.vy *= -1
            self.rect.y = max(floor_top, min(self.rect.y, HEIGHT - self.rect.height))
            
        # Lógica do tempo do balão de fala
        if self.message_timer > 0:
            self.message_timer -= 1
        else:
            self.message = ""
            
        # Atualiza a imagem atual baseado no frame index
        self.image = self.frames[int(self.frame_index) % len(self.frames)]
            
    def update_facing(self):
        facing_right = self.vx > 0
        if facing_right != self.facing_right:
            self.facing_right = facing_right
            self.frames = walk_right_frames if self.facing_right else walk_left_frames

    def draw(self, surface):
        surface.blit(self.image, self.rect)
        if self.message:
            self.draw_speech_bubble(surface)
            
    def draw_speech_bubble(self, surface):
        # Renderiza texto
        text = font.render(self.message, True, (0, 0, 0))
        text_rect = text.get_rect()
        
        # Centraliza o texto um pouco acima do pato
        text_rect.centerx = self.rect.centerx
        text_rect.bottom = self.rect.top - 15
        
        # Cria as bordas do balão com padding
        bubble_rect = text_rect.copy()
        bubble_rect.inflate_ip(20, 15)
        
        # Fundo do balão (Branco) e Borda (Preto)
        pygame.draw.ellipse(surface, (255, 255, 255), bubble_rect)
        pygame.draw.ellipse(surface, (0, 0, 0), bubble_rect, 2)
        
        # Desenha a pontinha do balão apontando para o pato
        polygon_points = [
            (bubble_rect.centerx - 5, bubble_rect.bottom - 4),
            (bubble_rect.centerx + 5, bubble_rect.bottom - 4),
            (bubble_rect.centerx, self.rect.top - 5)
        ]
        pygame.draw.polygon(surface, (255, 255, 255), polygon_points)
        pygame.draw.polygon(surface, (0, 0, 0), polygon_points, 2)
        
        # Desenha novamente a linha inferiror e re-preenche o poly para mesclar bordas perfeitas
        pygame.draw.line(surface, (255,255,255), (bubble_rect.centerx - 4, bubble_rect.bottom - 4), (bubble_rect.centerx + 4, bubble_rect.bottom - 4), 3)

        # Copia o texto por cima de tudo
        surface.blit(text, text_rect)


class DuckRoom:
    def __init__(self, agent_mode=False, num_ducks=6):
        self.ducks = [Duck() for _ in range(num_ducks)]
        self.agent_mode = agent_mode
        self.msg_queue = queue.Queue()
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
                    duck_idx = msg_data.get("duck", 0) % len(self.ducks)
                    text = msg_data.get("message", "")
                    
                    duck = self.ducks[duck_idx]
                    # Corta o texto se for muito longo para o balão, mas mostra o final para dar efeito de digitação real-time
                    duck.message = text.replace('\n', ' ')
                    if len(duck.message) > 40:
                        duck.message = "..." + duck.message[-37:]
                    duck.message_timer = int(FPS * 5) # Aparece por 5 segundos
                    duck.vx *= -1
                    duck.update_facing()

            # Checando interações de diálogo entre os patos (somente se não estiver em agent_mode ou como filler)
            if not self.agent_mode:
                self.check_interactions()

            # Desenho (Renderização)
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

            # Atualiza display e controla FPS
            pygame.display.flip()
            clock.tick(FPS)

        pygame.quit()

    def check_interactions(self):
        for i in range(len(self.ducks)):
            for j in range(i + 1, len(self.ducks)):
                d1 = self.ducks[i]
                d2 = self.ducks[j]
                
                # Distância euclidiana entre os dois patos
                dx = d1.rect.centerx - d2.rect.centerx
                dy = d1.rect.centery - d2.rect.centery
                dist = math.hypot(dx, dy)
                
                if dist < INTERACTION_DISTANCE:
                    # Chance de 3% por frame de iniciar conversa se estiverem próximos
                    if d1.message_timer == 0 and random.random() < 0.03:
                        d1.message = random.choice(MESSAGES)
                        d1.message_timer = int(FPS * 2.5) # Aparece por 2.5 segundos
                        
                        # Inverte a direção simulando pausa/virada para o parceiro
                        d1.vx *= -1
                        d1.update_facing()

                    # O outro responde com chance similar e independente
                    if d2.message_timer == 0 and random.random() < 0.03:
                        # Pequeno truque para não falar igual
                        options = [m for m in MESSAGES if m != d1.message]
                        d2.message = random.choice(options)
                        d2.message_timer = int(FPS * 2.5)
                        
                        d2.vx *= -1
                        d2.update_facing()

if __name__ == "__main__":
    agent_mode = "--agent-mode" in sys.argv
    
    num_ducks = 6
    if "--ducks" in sys.argv:
        try:
            idx = sys.argv.index("--ducks")
            num_ducks = int(sys.argv[idx+1])
        except (ValueError, IndexError):
            pass
            
    print("Iniciando a sala dos patos... Pressione Fechar na janela para sair.")
    room = DuckRoom(agent_mode=agent_mode, num_ducks=num_ducks)
    room.run()
