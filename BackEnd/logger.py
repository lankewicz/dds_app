# -----------------------------------------------------------------------------
# Módulo: logger.py
# Versão: 4.1
#
# Descrição:
#   Fornece uma classe, LogManager, para gerenciar os registros de atividade
#   da aplicação. As mensagens são armazenadas em memória (deque) e formatadas
#   para serem exibidas na interface TUI com cores e ícones.
#
# Principais Componentes:
#   - LogManager: Classe que armazena, gerencia e formata as entradas de log.
#
# Histórico de Alterações:
#   - 29/08/2025 (Gemini): Criação do módulo e migração da classe de main.py v4.0.
# -----------------------------------------------------------------------------

import datetime
from collections import deque
from typing import List, Dict

# Importa a configuração de tema para usar as cores definidas
from config import APP_CONFIG

class LogManager:
    """Gerencia logs em memória para exibição na interface do usuário."""

    def __init__(self, max_entries: int = APP_CONFIG.MAX_LOG_ENTRIES):
        """Inicializa o gerenciador de logs."""
        self.logs: deque = deque(maxlen=max_entries)
        self.error_logs: deque = deque(maxlen=10)
        self.success_logs: deque = deque(maxlen=10)

    def add(self, message: str, level: str = "INFO"):
        """Adiciona uma nova entrada de log."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        entry = {
            'time': timestamp,
            'level': level.upper(),
            'message': message
        }
        self.logs.append(entry)

        if entry['level'] == "ERROR":
            self.error_logs.append(entry)
        elif entry['level'] == "SUCCESS":
            self.success_logs.append(entry)

    def get_formatted_logs(self) -> List[str]:
        """Retorna uma lista de strings de log formatadas para o 'rich'."""
        formatted = []
        
        # Mapeamento de níveis para ícones e cores
        level_map: Dict[str, Dict[str, str]] = {
            'INFO':    {'icon': '📝', 'color': APP_CONFIG.THEME['info']},
            'SUCCESS': {'icon': '✅', 'color': APP_CONFIG.THEME['success']},
            'WARNING': {'icon': '⚠️', 'color': APP_CONFIG.THEME['warning']},
            'ERROR':   {'icon': '❌', 'color': APP_CONFIG.THEME['error']},
            'DEBUG':   {'icon': '🔍', 'color': APP_CONFIG.THEME['primary']}
        }
        default_style = {'icon': '📌', 'color': 'white'}

        for log in self.logs:
            style = level_map.get(log['level'], default_style)
            color = style['color']
            icon = style['icon']
            
            formatted_message = f"[{color}]{log['time']} {icon} {log['message']}[/{color}]"
            formatted.append(formatted_message)
            
        return formatted

# --- Instância Única (Singleton) ---
# Criamos uma única instância do LogManager para ser usada em toda a aplicação.
# Outros módulos podem simplesmente fazer `from logger import log_manager`.
log_manager = LogManager()