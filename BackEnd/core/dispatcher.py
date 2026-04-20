# =============================================================================
# Nome do arquivo : core/dispatcher.py
# Data de criação : 31/10/2025
# Função          : Despachante central de comandos do DDS.
# Funcionalidades :
#   - interpretar_comando(subject): detecta o comando e extrai argumento.
#   - executar_comando(comando, argumento, sender): roteia p/ core/cmd_*.py
#     com fallback ao legacy (commands.py) quando necessário.
#   - run_background(...): executa comandos longos em thread daemon (backup/limpar).
#   - Preferência por módulos novos (ajuda, listar, apagar, relatorio, backup, limpar).
# =============================================================================

from __future__ import annotations
import threading
from typing import Optional, Tuple
from logger import log_manager
from email_utils import send_response

# Importa APENAS dos módulos novos
from core.cmd_ajuda     import comando_ajuda     as _cmd_ajuda
from core.cmd_listar    import comando_listar    as _cmd_listar
from core.cmd_apagar    import comando_apagar    as _cmd_apagar
from core.cmd_relatorio import comando_relatorio as _cmd_relatorio
from core.cmd_backup    import comando_backup    as _cmd_backup
from core.cmd_limpar    import comando_limpar    as _cmd_limpar

# --------------------------------------------------------------------------------------


__all__ = ["interpretar_comando", "executar_comando", "run_background"]


def interpretar_comando(subject: str) -> Tuple[Optional[str], str]:
    """Normaliza o assunto e detecta o comando + argumento."""
    subject = (subject or "").strip().upper()

    mapeamento = {
        "AJUDA": "ajuda",
        "HELP": "ajuda",
        "LISTAR": "listar",
        "LIST": "listar",
        "APAGAR": "apagar",
        "DELETE": "apagar",
        "RELATORIO": "relatorio",
        "REPORT": "relatorio",
        "BACKUP": "backup",
        "LIMPAR": "limpar",
        "CLEAN": "limpar",
    }

    for chave, cmd in mapeamento.items():
        if subject.startswith(chave):
            return cmd, subject[len(chave):].strip()
    return None, ""


def run_background(name: str, fn, *args, **kwargs) -> threading.Thread:
    th = threading.Thread(
        target=fn, args=args, kwargs=kwargs, daemon=True, name=f"cmd-{name}"
    )
    th.start()
    return th


def executar_comando(comando: str, argumento: str, sender: str):
    """Despacha para o comando correspondente; BACKUP e LIMPAR (com CONFIRMO) em background."""
    log_manager.add(
        f"Executando comando '{comando}' com argumento '{argumento}' para {sender}", "INFO"
    )
    try:
        dispatch = {
            "ajuda": _cmd_ajuda,
            "listar": _cmd_listar,
            "apagar": _cmd_apagar,
            "relatorio": _cmd_relatorio,
            "backup": _cmd_backup,
            "limpar": _cmd_limpar,
        }

        if comando not in dispatch:
            raise ValueError(f"Comando desconhecido: {comando}")

        # Longos em background
        if comando == "backup":
            # MODO DEBUG: executar BACKUP de forma síncrona (sem thread)
            log_manager.add("BACKUP executando em modo síncrono (debug)", "INFO")
            dispatch[comando](argumento, sender)
            log_manager.add("BACKUP (modo síncrono) concluído.", "INFO")
            return

        if comando == "limpar" and "CONFIRMO" in (argumento or "").upper():
            run_background("limpar", dispatch[comando], argumento, sender)
            send_response(
                sender,
                "⏳ LIMPAR (CONFIRMO) iniciado",
                "Executando em segundo plano. Você receberá um e-mail ao concluir.",
            )
            log_manager.add("LIMPAR (CONFIRMO) em background", "INFO")
            return

        # Demais comandos síncronos
        dispatch[comando](argumento, sender)
        log_manager.add(f"Comando '{comando}' executado com sucesso.", "SUCCESS")
    except Exception as e:
        log_manager.add(f"Erro ao executar comando '{comando}': {e}", "ERROR")
        send_response(
            sender,
            f"❌ ERRO no Comando {comando.upper()}",
            f"Ocorreu um erro inesperado: {e}",
        )
