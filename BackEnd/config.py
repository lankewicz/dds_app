# -----------------------------------------------------------------------------
# Módulo: config.py
# Versão: 4.1
#
# Descrição:
#   Módulo responsável por centralizar todas as configurações da aplicação.
#   Carrega variáveis de ambiente do arquivo .env e define constantes, caminhos
#   e parâmetros de comportamento do sistema.
#
# Principais Componentes:
#   - AppConfig: Classe que agrupa configurações de comportamento da aplicação.
#   - inicializar_pastas(): Função para garantir que os diretórios de dados existam.
#
# Histórico de Alterações:
#   - 29/08/2025 (Gemini): Criação do módulo para a arquitetura v4.1.


import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env localizado na pasta 'init'
# A base é o diretório onde este arquivo de configuração está.
BASE_DIR = Path(__file__).parent
load_dotenv(dotenv_path=BASE_DIR / 'init' / '.env')

# --- 1. Configurações de Caminhos (Paths) ---
ROOT_DATA = BASE_DIR / 'DADOS'
DDS_BASE = ROOT_DATA / 'DDS'
SENT_BASE = ROOT_DATA / 'ENVIADOS'
IGNORED_BASE = ROOT_DATA / 'IGNORADOS'
CACHE_DIR = ROOT_DATA / 'CACHE' # Pasta para cache de thumbnails dos relatórios

# --- 2. Configurações de Conexão (IMAP/SMTP) ---
IMAP_SERVER = os.getenv('IMAP_SERVER', 'imap.gmail.com')
IMAP_PORT = int(os.getenv('IMAP_PORT', 993))
IMAP_USER = os.getenv('EMAIL')
IMAP_PASS = os.getenv('SENHA')
MAILBOX = os.getenv('IMAP_MAILBOX', 'INBOX')

SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USER = os.getenv('EMAIL')
SMTP_PASS = os.getenv('SENHA')

# --- 3. Configurações do Firebase ---
# O caminho para a credencial é construído a partir da pasta 'init'
FIREBASE_CREDENTIAL_PATH = BASE_DIR / 'init' / os.getenv('FIREBASE_CREDENTIAL_PATH', 'serviceAccountKey.json')
FIREBASE_BUCKET = os.getenv('FIREBASE_BUCKET')

# --- 4. Configurações da Aplicação ---
class AppConfig:
    """Agrupa configurações de comportamento da aplicação."""
    # Intervalo em segundos entre os ciclos de verificação de e-mail
    INTERVAL = int(os.getenv("PROCESS_INTERVAL", "60"))
    # Número máximo de entradas a serem mantidas no log da interface
    MAX_LOG_ENTRIES = 50
    # Tamanho do lote de e-mails a serem processados por ciclo
    BATCH_SIZE = 1
    # Ativa/desativa o modo de depuração com mais logs
    DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"
    # Tema de cores para a interface 'rich'
    THEME = {
        'primary': 'cyan',
        'success': 'green',
        'warning': 'yellow',
        'error': 'red',
        'info': 'blue',
        'border': 'bright_blue'
    }

# Instancia a configuração da aplicação para ser importada por outros módulos
APP_CONFIG = AppConfig()

# --- 5. Inicialização ---
def inicializar_pastas():
    """Garante que todas as pastas de dados necessárias existam."""
    print("Verificando e criando pastas de dados...")
    for path in [ROOT_DATA, DDS_BASE, SENT_BASE, IGNORED_BASE, CACHE_DIR]:
        path.mkdir(parents=True, exist_ok=True)
    print("Pastas de dados prontas.")

# Caracteres inválidos em nomes de arquivo/pasta
INVALID_CHARS = '<>:"/\\|?*'