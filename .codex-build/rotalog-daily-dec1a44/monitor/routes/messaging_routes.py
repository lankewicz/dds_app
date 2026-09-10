# -----------------------------------------------------------------------------
# Arquivo : routes/messaging_routes.py
# Objetivo: Expor os endpoints para gestão de mensagens de comunicação.
# -----------------------------------------------------------------------------

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.encoders import jsonable_encoder

from schemas.messaging_schema import MessageCreate, ThreadMarkRead, ThreadConclude
from services.messaging_service import (
    get_open_threads,
    get_thread_messages,
    mark_thread_as_read,
    send_message,
    conclude_thread,
    CURRENT_SETOR
)

router = APIRouter(prefix="/api/mensagens", tags=["messaging"])

@router.get("/threads")
def list_threads(setor: str = Query(CURRENT_SETOR)):
    """
    Lista as threads abertas (não concluídas) para o setor.
    """
    return JSONResponse(jsonable_encoder({"threads": get_open_threads(setor)}))

@router.get("/thread/{thread_id}")
def get_thread(thread_id: str):
    """
    Retorna todas as mensagens de uma thread.
    """
    return JSONResponse(jsonable_encoder({"messages": get_thread_messages(thread_id)}))

@router.post("/read")
def mark_read(payload: ThreadMarkRead, setor: str = Query(CURRENT_SETOR)):
    """
    Marca uma thread como lida para o setor.
    """
    count = mark_thread_as_read(payload.threadId, setor)
    return JSONResponse({"ok": True, "count": count})

@router.post("/send")
def post_message(payload: MessageCreate):
    """
    Envia uma nova mensagem.
    """
    try:
        msg_id = send_message(
            thread_id=payload.threadId,
            subject=payload.subject,
            content=payload.content,
            to_equipe=payload.toEquipe,
            to_setor=payload.toSetor,
            from_equipe=payload.fromEquipe or CURRENT_SETOR
        )
        return JSONResponse({"ok": True, "id": msg_id})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@router.post("/conclude")
def conclude(payload: ThreadConclude):
    """
    Conclui uma conversa.
    """
    count = conclude_thread(payload.threadId)
    return JSONResponse({"ok": True, "count": count})
