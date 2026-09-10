# -----------------------------------------------------------------------------
# Arquivo : routes/team_form_routes.py
# Objetivo: Expor o GET/PUT do formulário combinado da equipe.
# -----------------------------------------------------------------------------

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from schemas.team_form_schema import TeamFormPayload
from services.team_form_service import get_team_form_data, save_team_form_data


router = APIRouter()


@router.get("/api/team-form")
def read_team_form(
    empresa: str = Query(...),
    teamKey: str = Query(...),
):
    team_key = teamKey.strip()
    empresa = empresa.strip()
    if not team_key:
        raise HTTPException(status_code=400, detail="teamKey é obrigatório.")
    if not empresa:
        raise HTTPException(status_code=400, detail="empresa é obrigatória.")
    return JSONResponse(jsonable_encoder(get_team_form_data(empresa, team_key)))


@router.put("/api/team-form")
def update_team_form(payload: TeamFormPayload):
    try:
        data = save_team_form_data(payload.model_dump())
        return JSONResponse(jsonable_encoder(data))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
