# =============================================================================
# Nome do arquivo : utils/env_config.py
# Data de criação : 31/10/2025
# Função          : Leitura de variáveis de ambiente e conversões seguras.
# Funcionalidades :
#   - empresas_from_env() -> lista de empresas (DDS_EMPRESAS)
#   - prefix_from_env() -> prefixo no Storage/Drive (DDS_PREFIX)
#   - to_bool / to_int com padrão
# =============================================================================

from __future__ import annotations
import os

def to_bool(v: str | None, default: bool=False) -> bool:
    if v is None: return default
    return str(v).strip().lower() in {"1","true","on","yes","y","sim"}

def to_int(v: str | None, default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default

def empresas_from_env() -> list[str]:
    raw = os.getenv("DDS_EMPRESAS", "")
    return [e.strip() for e in raw.split(",") if e.strip()]

def prefix_from_env() -> str:
    return (os.getenv("DDS_PREFIX") or "DDSv2/").strip()
