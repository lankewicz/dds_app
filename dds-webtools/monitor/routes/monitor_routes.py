# -----------------------------------------------------------------------------
# Arquivo : routes/monitor_routes.py
# Objetivo: Expor a página principal do monitor, a página de equipes inativas
#           e os endpoints já existentes de configuração e leitura dos turnos.
# -----------------------------------------------------------------------------

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.encoders import jsonable_encoder

import os
from schemas.monitor_config_schema import MonitorConfigPayload
from services.monitor_config_service import save_monitor_settings
from services.turnos_service import APP_TITLE, DEFAULT_EMPRESA, get_monitor_config, list_turnos, update_realtime_view
from services.teams_service import list_trash_teams_map, move_to_trash, restore_from_trash, permanently_delete, get_team_trash_preview, get_team, save_team
from services.requests_service import list_pending_requests, approve_request, reject_request


def get_app_version() -> str:
    """Extrai a versão simplificada da revisão atual (ex: 00113-dx8)."""
    revision = os.environ.get('K_REVISION', 'local')
    if "-" in revision:
        parts = revision.split("-")
        if len(parts) >= 2:
            revision = "-".join(parts[-2:])
    return revision


templates = Jinja2Templates(directory="templates")
router = APIRouter()


def _render_home(request: Request, page_mode: str, page_title: str):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_title": APP_TITLE,
            "page_title": page_title,
            "page_mode": page_mode,
            "app_version": get_app_version(),
        },
    )


@router.get("/monitor", response_class=HTMLResponse)
def home(request: Request):
    return _render_home(request, page_mode="active", page_title="Monitor de Turnos")


@router.get("/monitor/inativas", response_class=HTMLResponse)
def home_inativas(request: Request):
    return _render_home(request, page_mode="inactive", page_title="Equipes Inativas")


@router.get("/monitor/lixeira", response_class=HTMLResponse)
def home_lixeira(request: Request):
    return _render_home(request, page_mode="trash", page_title="Lixeira de Equipes")


@router.get("/api/config")
def config():
    return JSONResponse(jsonable_encoder(get_monitor_config()))

@router.put("/api/config")
def update_config(payload: MonitorConfigPayload):
    try:
        saved = save_monitor_settings(payload.model_dump())
        return JSONResponse({
            "ok": True,
            "message": "Configurações salvas com sucesso.",
            "defaultEmpresa": DEFAULT_EMPRESA,
            **saved,
        })
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/turnos")
def turnos(
    empresa: str = Query(DEFAULT_EMPRESA),
    active: str | None = Query("true"), # Mudado para string para aceitar 'all'
    refresh: str | None = Query(None),
    setor: str = Query(None),
):
    # Converte a string do filtro para boolean ou None
    active_bool = None
    if active and active.lower() == "true":
        active_bool = True
    elif active and active.lower() == "false":
        active_bool = False
    # Se for 'all' ou qualquer outra coisa, active_bool continua None (todas)
    
    manual_refresh = str(refresh or "").strip().lower() in {"1", "true", "manual", "force"}
    kwargs = {"empresa": empresa, "active": active_bool, "manual_refresh": manual_refresh}
    if setor:
        kwargs["setor"] = setor
    return JSONResponse(jsonable_encoder(list_turnos(**kwargs)))


@router.post("/api/internal/sync-realtime")
def sync_realtime(
    empresa: str = Query(DEFAULT_EMPRESA),
    refresh: str | None = Query(None),
    setor: str = Query(None),
):
    manual_refresh = str(refresh or "").strip().lower() in {"1", "true", "manual", "force"}
    kwargs = {"empresa": empresa, "manual_refresh": manual_refresh}
    if setor:
        kwargs["setor"] = setor
    return JSONResponse(jsonable_encoder(update_realtime_view(**kwargs)))


@router.get("/api/requests")
def get_requests():
    return JSONResponse(jsonable_encoder(list_pending_requests()))


@router.post("/api/requests/{request_id}/approve")
def approve(request_id: str):
    approve_request(request_id)
    return JSONResponse({"ok": True})


@router.post("/api/requests/{request_id}/reject")
def reject(request_id: str):
    reject_request(request_id)
    return JSONResponse({"ok": True})


@router.get("/api/teams/trash")
def get_trash_teams():
    return JSONResponse(jsonable_encoder(list_trash_teams_map()))


@router.post("/api/teams/{team_key}/trash")
def move_team_trash(team_key: str):
    move_to_trash(team_key)
    return JSONResponse({"ok": True, "message": f"Equipe {team_key} movida para a lixeira."})


@router.delete("/api/teams/{team_key}/trash")
def restore_team_trash(team_key: str):
    restore_from_trash(team_key)
    return JSONResponse({"ok": True, "message": f"Equipe {team_key} restaurada."})


@router.delete("/api/teams/{team_key}/permanent")
def delete_team_permanent(team_key: str):
    logs = permanently_delete(team_key)
    return JSONResponse({
        "ok": True, 
        "logs": logs,
        "message": f"Equipe {team_key} e todo seu histórico foram apagados permanentemente."
    })


@router.get("/api/teams/{team_key}/trash-preview")
def get_trash_preview(team_key: str):
    return JSONResponse(jsonable_encoder(get_team_trash_preview(team_key)))


@router.patch("/api/teams/{team_key}/active")
def toggle_team_active(team_key: str, active: bool):
    team = get_team(team_key)
    if not team:
        return JSONResponse({"ok": False, "message": "Equipe não encontrada"}, status_code=404)
    
    save_team(team_key, {**team, "active": active})
    
    # Força atualização do tempo real e limpa caches para que a equipe suma/apareça na hora
    update_realtime_view()
    from services.turnos_service import clear_all_monitor_caches
    clear_all_monitor_caches()
    
    return JSONResponse(jsonable_encoder({"ok": True, "message": f"Equipe {'ativada' if active else 'ocultada'} com sucesso."}))
