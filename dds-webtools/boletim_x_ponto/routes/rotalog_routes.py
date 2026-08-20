"""
Rotas FastAPI para consulta e sincronização do ROTALOG Tempo Real.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from boletim_x_ponto.services.rotalog_tempo_real_service import extrair_dados_tempo_real
from boletim_x_ponto.services.rotalog_sync_task import executar_sincronizacao_rotalog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rotalog", tags=["rotalog"])


@router.get("/tempo-real")
async def get_rotalog_tempo_real():
    """
    Retorna o status capturado em tempo real de todas as equipes no Rotalog.
    """
    try:
        dados = extrair_dados_tempo_real()
        return JSONResponse(content={"ok": True, "totalEquipes": len(dados), "equipes": dados})
    except Exception as e:
        logger.error(f"Erro ao capturar Rotalog Tempo Real: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-now")
async def trigger_rotalog_sync(empresa: str = "ChicoEletro"):
    """
    Força a sincronização imediata dos status do Rotalog com o Firestore.
    """
    try:
        res = executar_sincronizacao_rotalog(empresa=empresa)
        return JSONResponse(content={"ok": True, "result": res})
    except Exception as e:
        logger.error(f"Erro ao executar sincronização Rotalog: {e}")
        raise HTTPException(status_code=500, detail=str(e))
