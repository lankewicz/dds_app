# =============================================================================
# Nome do arquivo : commands.py
# Data de criação : 31/10/2025
# Função          : Ponte de compatibilidade entre o código legado e os módulos em core/.
# Funcionalidades :
#   - Wrappers _comando_* que delegam para core/cmd_*.py (fonte única de verdade).
#   - Shim "lazy" para reexportar interpretar_comando/executar_comando/run_background
#     a partir de core/dispatcher, evitando import circular.
# =============================================================================

# -----------------------------------------------------------------------------
# Wrappers legacy (mantêm a API antiga: _comando_*)
# -----------------------------------------------------------------------------
def _comando_ajuda(argumento: str, sender: str):
    from core.cmd_ajuda import comando_ajuda
    return comando_ajuda(argumento, sender)

def _comando_listar(argumento: str, sender: str):
    from core.cmd_listar import comando_listar
    return comando_listar(argumento, sender)

def _comando_apagar(argumento: str, sender: str):
    from core.cmd_apagar import comando_apagar
    return comando_apagar(argumento, sender)

def _comando_relatorio(argumento: str, sender: str):
    from core.cmd_relatorio import comando_relatorio
    return comando_relatorio(argumento, sender)

def _comando_backup(argumento: str, sender: str):
    from core.cmd_backup import comando_backup
    return comando_backup(argumento, sender)

def _comando_limpar(argumento: str, sender: str):
    from core.cmd_limpar import comando_limpar
    return comando_limpar(argumento, sender)


# -----------------------------------------------------------------------------
# (Opcional) Reexports temporários de helpers legacy
# Descomente se algum código antigo ainda importar estes nomes de commands.py.
# -----------------------------------------------------------------------------
# from utils.date_parse import parse_mes_ano as _parse_mes_ano
# from utils.env_config import empresas_from_env as _empresas_from_env


# -----------------------------------------------------------------------------
# Dispatcher shim (fase 1) — versão LAZY (sem import no topo)
# -----------------------------------------------------------------------------
# Mantemos TODA a lógica no core; estes wrappers apenas delegam
# para core/dispatcher no MOMENTO DA CHAMADA, evitando import circular.
_legacy_interpretar = globals().get("interpretar_comando")
_legacy_executar    = globals().get("executar_comando")
_legacy_run_bg      = globals().get("run_background")

def interpretar_comando(*args, **kwargs):
    try:
        from core import dispatcher as _dispatcher
        return _dispatcher.interpretar_comando(*args, **kwargs)
    except Exception:
        if _legacy_interpretar:
            return _legacy_interpretar(*args, **kwargs)
        raise

def executar_comando(*args, **kwargs):
    try:
        from core import dispatcher as _dispatcher
        return _dispatcher.executar_comando(*args, **kwargs)
    except Exception:
        if _legacy_executar:
            return _legacy_executar(*args, **kwargs)
        raise

def run_background(*args, **kwargs):
    try:
        from core import dispatcher as _dispatcher
        return _dispatcher.run_background(*args, **kwargs)
    except Exception:
        if _legacy_run_bg:
            return _legacy_run_bg(*args, **kwargs)
        raise
