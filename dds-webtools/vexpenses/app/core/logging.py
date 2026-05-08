import logging
import sys
from pathlib import Path

# Configuração básica de logging
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = "app.log"

def setup_logging():
    # Garantir que o logger raiz tenha o nível correto
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(LOG_FORMAT)

    # Handler para console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Handler para arquivo
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logging.info("Logging inicializado. Gravando em %s", LOG_FILE)

def get_logger(name: str):
    return logging.getLogger(name)
