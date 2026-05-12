# -----------------------------------------------------------------------------
# Arquivo : services/team_form_service.py
# Objetivo: Montar e persistir o payload combinado do formulário da equipe,
#           separando cadastro-base, equipamentos e situação atual do turno.
# -----------------------------------------------------------------------------

from __future__ import annotations
from typing import Any
from google.cloud import firestore

from services.firestore_client import db
from services.teams_service import get_team, list_equipment_history, save_team
from services.turno_equipes_service import get_turno_equipe, save_turno_equipe
from services.turnos_service import normalize_estado, string_list, to_utc_dt, update_realtime_view

def get_team_form_data(empresa: str, team_key: str) -> dict[str, Any]:
    team_doc = get_team(team_key) or {}
    turno_doc = get_turno_equipe(empresa, team_key) or {}

    display_name = _first_text(
        team_doc.get("displayName"),
        turno_doc.get("equipe"),
        team_key,
    )
    members = string_list(team_doc.get("members")) or string_list(turno_doc.get("membersSnapshot"))

    turno_updated_at = to_utc_dt(turno_doc.get("serverUpdatedAt"))
    turno_payload = {
        "empresa": empresa,
        "teamKey": team_key,
        "estado": normalize_estado(turno_doc.get("estado") or "DESCONHECIDO"),
        "nocSs": _first_text(turno_doc.get("nocSs"), default=""),
        "motivo": _first_text(turno_doc.get("lastMotivoOutro"), turno_doc.get("lastMotivo"), default=""),
        "horaEntrada": _first_text(turno_doc.get("horaEntradaMonitor"), default=""),
        "horaSaida": _first_text(turno_doc.get("horaSaidaMonitor"), default=""),
        "observacoes": _first_text(turno_doc.get("observacoesMonitor"), default=""),
        "updatedAt": turno_updated_at.isoformat() if turno_updated_at else None,
    }

    equipment = team_doc.get("equipment") or {}
    team_payload = {
        "teamKey": team_key,
        "displayName": display_name,
        "members": members,
        "equipment": equipment,
        "active": bool(team_doc.get("active", True)),
    }

    return {
        "empresa": empresa,
        "teamKey": team_key,
        "team": team_payload,
        "turno": turno_payload,
        "equipmentHistory": list_equipment_history(team_key),
        "meta": {
            "teamDocExists": bool(team_doc.get("_exists")),
            "turnoDocExists": bool(turno_doc.get("_exists")),
        },
    }

def save_team_form_data(payload: dict[str, Any]) -> dict[str, Any]:
    team_payload = payload.get("team") or {}
    turno_payload = payload.get("turno") or {}

    team_key = _first_text(team_payload.get("teamKey"), turno_payload.get("teamKey"))
    empresa = _first_text(turno_payload.get("empresa"), payload.get("empresa"))
    if not team_key:
        raise ValueError("teamKey é obrigatório.")
    if not empresa:
        raise ValueError("empresa é obrigatória.")

    team_doc = get_team(team_key)
    was_active = bool(team_doc.get("active", True)) if team_doc else True

    saved_team = save_team(team_key, team_payload)
    is_active = bool(saved_team.get("active", True))

    original_turno = get_turno_equipe(empresa, team_key) or {}

    # Determina se houve mudança em campos operacionais para decidir se atualiza o 
    # timestamp de atividade (touch_activity). Alterações puras de cadastro ou 
    # equipamentos não devem atualizar o serverUpdatedAt operacional.
    touch = False
    if not original_turno:
        touch = True
    else:
        # Compara campos operacionais (estado, nocSs, motivo, horários, observações)
        if normalize_estado(turno_payload.get("estado")) != original_turno.get("estado"):
            touch = True
        elif _first_text(turno_payload.get("nocSs"), default=None) != original_turno.get("nocSs"):
            touch = True
        elif _first_text(turno_payload.get("motivo"), default=None) != original_turno.get("lastMotivo"):
            touch = True
        elif _first_text(turno_payload.get("horaEntrada"), default=None) != original_turno.get("horaEntradaMonitor"):
            touch = True
        elif _first_text(turno_payload.get("horaSaida"), default=None) != original_turno.get("horaSaidaMonitor"):
            touch = True
        elif _first_text(turno_payload.get("observacoes"), default=None) != original_turno.get("observacoesMonitor"):
            touch = True

    saved_turno = save_turno_equipe(
        empresa,
        team_key,
        turno_payload,
        members_snapshot=saved_team.get("members") or [],
        touch_activity=touch,
    )

    _sync_manual_active_state(team_key, is_active, was_active)

    # Força atualização do realtime para que a equipe suma/apareça na hora
    update_realtime_view(empresa=empresa)

    return {
        "ok": True,
        "message": "Equipe salva com sucesso.",
        "empresa": empresa,
        "teamKey": team_key,
        "team": saved_team,
        "equipmentHistory": list_equipment_history(team_key),
        "turno": {
            "empresa": empresa,
            "teamKey": team_key,
            "estado": saved_turno.get("estado"),
            "nocSs": saved_turno.get("nocSs") or "",
            "motivo": saved_turno.get("lastMotivo") or "",
            "horaEntrada": saved_turno.get("horaEntradaMonitor") or "",
            "horaSaida": saved_turno.get("horaSaidaMonitor") or "",
            "observacoes": saved_turno.get("observacoesMonitor") or "",
        },
    }

def _first_text(*values: Any, default: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return default

def _sync_manual_active_state(team_key: str, active: bool, was_active: bool = True) -> None:
    if active == was_active:
        return

    team_ref = db.collection("dds_teams").document(team_key)
    if active:
        team_ref.set(
            {
                "autoInactiveReason": firestore.DELETE_FIELD,
                "autoInactiveAt": firestore.DELETE_FIELD,
                "autoInactiveLastSeenUpdatedAt": firestore.DELETE_FIELD,
                "autoInactiveLastSeenDdsDay": firestore.DELETE_FIELD,
            },
            merge=True,
        )
        return

    team_ref.set(
        {
            "autoInactiveReason": "MANUAL",
            "autoInactiveAt": firestore.SERVER_TIMESTAMP,
            "autoInactiveLastSeenUpdatedAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )