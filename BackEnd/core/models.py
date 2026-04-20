# -----------------------------------------------------------------------------
# Módulo: core/models.py
# Versão: 4.1
#
# Descrição:
#   Define as estruturas de dados centrais (dataclasses) e tipos enumerados
#   (Enums) utilizados em toda a aplicação DDS v4.1. Isolar esses modelos
#   aqui melhora a organização e a clareza do código.
#
# Principais Componentes:
#   - StatusType(Enum): Define os possíveis status da aplicação para a TUI.
#   - EmailStats(dataclass): Estrutura para armazenar estatísticas de e-mails.
#   - SystemMetrics(dataclass): Estrutura para armazenar métricas de sistema.
#
# Histórico de Alterações:
#   - 29/08/2025 (Gemini): Criação do módulo e migração das classes de main.py v4.0.
# -----------------------------------------------------------------------------

from dataclasses import dataclass
from enum import Enum
from typing import Optional

class StatusType(Enum):
    """Define os status operacionais da aplicação para exibição na interface."""
    IDLE = "🟢 Em Espera"
    PROCESSING = "🔄 Processando"
    ERROR = "🔴 Erro"
    SUCCESS = "✅ Sucesso"
    WARNING = "⚠️ Aviso"

@dataclass
class EmailStats:
    """Armazena estatísticas relacionadas ao processamento de e-mails."""
    total_processados: int = 0
    sucesso: int = 0
    falhas: int = 0
    comandos: int = 0
    anexos: int = 0
    tempo_medio: float = 0.0
    # Adicionando os atributos de status aqui
    current_status: StatusType = StatusType.IDLE
    current_task: str = "Aguardando..."

@dataclass
class SystemMetrics:
    """Armazena métricas de desempenho e estado do sistema."""
    ciclos_completos: int = 0
    uptime: float = 0.0
    emails_por_hora: float = 0.0
    taxa_sucesso: float = 0.0
    ultimo_erro: Optional[str] = None
    memoria_uso: float = 0.0 # Exemplo, pode ser preenchido por uma função utilitária

