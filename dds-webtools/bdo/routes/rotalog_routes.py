"""
Rotas FastAPI para consulta e sincronização do ROTALOG Tempo Real.
"""

from __future__ import annotations

import hashlib
import logging
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from bdo.services.rotalog_tempo_real_service import extrair_dados_tempo_real
from bdo.services.rotalog_sync_task import (
    executar_sincronizacao_rotalog,
    get_rotalog_execution_log,
    get_rotalog_live_snapshot,
    get_rotalog_live_snapshots,
    get_rotalog_team_current,
    get_rotalog_team_daily,
    get_rotalog_team_daily_today,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rotalog", tags=["rotalog"])


@router.get("/tempo-real")
async def get_rotalog_tempo_real():
    """
    Retorna o status capturado em tempo real de todas as equipes no Rotalog.
    """
    try:
        dados = list(get_rotalog_live_snapshots().values())
        return JSONResponse(content={"ok": True, "totalEquipes": len(dados), "equipes": dados})
    except Exception as e:
        logger.error(f"Erro ao capturar Rotalog Tempo Real: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-now")
def trigger_rotalog_sync(empresa: str = "ChicoEletro"):
    """
    Força a sincronização imediata dos status do Rotalog com o Firestore.
    """
    try:
        res = executar_sincronizacao_rotalog(empresa=empresa)
        return JSONResponse(content={"ok": True, "result": res})
    except Exception as e:
        logger.error(f"Erro ao executar sincronização Rotalog: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync-log")
async def get_sync_log(date: str | None = None):
    """Retorna o log diário das tentativas de raspagem; sem data, usa hoje em Brasília."""
    try:
        document = get_rotalog_execution_log(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Data inválida; use YYYY-MM-DD.")
    if not document:
        raise HTTPException(status_code=404, detail="Log de raspagem não encontrado.")
    return {"ok": True, "log": document}


@router.get("/teams/{team_key}/current")
async def team_current(team_key: str):
    document = get_rotalog_team_current(team_key)
    if not document:
        raise HTTPException(status_code=404, detail="Equipe não encontrada.")
    return {"ok": True, "team": document}


@router.get("/teams/{team_key}/daily")
async def team_daily(team_key: str, date: str):
    try:
        document = get_rotalog_team_daily(team_key, date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Data inválida; use YYYY-MM-DD.")
    if not document:
        raise HTTPException(status_code=404, detail="Diário não encontrado.")
    return {"ok": True, "daily": document}

def _mobile_team_view(document: dict) -> dict:
    daily_current = document.get("current") or {}
    activity = daily_current.get("service") or document.get("atividadeAtual") or {}
    turn_status = (
        daily_current.get("turnStatus")
        or document.get("estadoConsolidado")
        or (document.get("turno") or {}).get("status")
    )
    version = daily_current.get("version") or document.get("version") or 1
    updated_at = document.get("updatedAt") or document.get("updatedAtIso") or ""

    start_travel = activity.get("inicioDeslocamento") or activity.get("inicioIso")
    start_exec = activity.get("inicioExecucao")
    end_exec = activity.get("fimExecucao") or activity.get("termino") or activity.get("fimIso")
    return_at = activity.get("retorno")
    status_atual = activity.get("statusAtual") or activity.get("status")

    return {
        "teamKey": document.get("teamKey") or document.get("equipe"),
        "version": version,
        "updatedAt": updated_at,
        "turnStatus": turn_status,
        "service": ({
            "type": activity.get("tipo"),
            "category": activity.get("categoria"),
            "status": status_atual,
            "startTravel": start_travel,
            "startExecution": start_exec,
            "endExecution": end_exec,
            "returnAt": return_at,
        } if activity else None),
    }


@router.get("/mobile/{team_key}/current")
async def mobile_team_current(team_key: str, request: Request):
    if not getattr(request.state, "mobile_user", None):
        raise HTTPException(status_code=401, detail="Não autenticado.")

    document = None
    try:
        document = get_rotalog_team_daily_today(team_key)
    except Exception as exc:
        logger.warning("Erro ao carregar diário hoje para %s: %s", team_key, exc)

    if not document:
        try:
            document = get_rotalog_live_snapshot(team_key)
        except Exception as exc:
            logger.warning("Erro ao carregar live snapshot para %s: %s", team_key, exc)

    if not document:
        raise HTTPException(status_code=404, detail="Diário da equipe não encontrado.")

    updated_at = str(document.get("updatedAt") or document.get("updatedAtIso") or "")
    daily_current = document.get("current") or {}
    version = str(daily_current.get("version") or document.get("version") or "")
    etag_raw = f"{team_key}_{updated_at}_{version}"
    etag = f'"{hashlib.md5(etag_raw.encode("utf-8")).hexdigest()}"'

    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match.strip() == etag:
        return Response(status_code=304, headers={"ETag": etag})

    view = _mobile_team_view(document)
    return JSONResponse(content={"ok": True, "team": view}, headers={"ETag": etag})


@router.get("/mobile/{team_key}/daily")
async def mobile_team_daily(team_key: str, request: Request):
    if not getattr(request.state, "mobile_user", None):
        raise HTTPException(status_code=401, detail="Não autenticado.")

    document = None
    try:
        document = get_rotalog_team_daily_today(team_key)
    except Exception as exc:
        logger.warning("Erro ao carregar diário hoje para %s: %s", team_key, exc)

    if not document:
        try:
            document = get_rotalog_live_snapshot(team_key)
        except Exception as exc:
            logger.warning("Erro ao carregar live snapshot para %s: %s", team_key, exc)

    if not document:
        raise HTTPException(status_code=404, detail="Diário da equipe não encontrado.")
    return {"ok": True, "daily": document}

