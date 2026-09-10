# -----------------------------------------------------------------------------
# Arquivo : services/turno_equipes_service.py
# Objetivo: Ler e gravar o documento operacional em
#           turno/{empresa}/equipes/{teamKey}.
# -----------------------------------------------------------------------------

from __future__ import annotations

from typing import Any

from google.cloud import firestore

from services.firestore_client import db
from services.turnos_service import normalize_estado, string_list


def get_turno_equipe(empresa: str, team_key: str) -> dict[str, Any] | None:
    snap = db.collection("turno").document(empresa).collection("equipes").document(team_key).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    data["teamKey"] = team_key
    data["empresa"] = empresa
    data["_exists"] = True
    return data


def save_turno_equipe(
    empresa: str,
    team_key: str,
    payload: dict[str, Any],
    *,
    members_snapshot: list[str] | None = None,
    touch_activity: bool = True,
) -> dict[str, Any]:
    clean_payload = {
        "estado": normalize_estado(payload.get("estado") or "DESCONHECIDO"),
        "nocSs": _clean_str(payload.get("nocSs")),
        "lastMotivo": _clean_str(payload.get("motivo")),
        "lastMotivoOutro": None,
        "horaEntradaMonitor": _clean_str(payload.get("horaEntrada")),
        "horaSaidaMonitor": _clean_str(payload.get("horaSaida")),
        "observacoesMonitor": _clean_str(payload.get("observacoes")),
        "membersSnapshot": string_list(members_snapshot or []),
        "updatedByName": "MONITOR WEB",
        "updatedByDeviceModel": "DDS_TURNOS_MONITOR",
    }
    if touch_activity:
        clean_payload["serverUpdatedAt"] = firestore.SERVER_TIMESTAMP
    db.collection("turno").document(empresa).collection("equipes").document(team_key).set(clean_payload, merge=True)
    clean_payload["empresa"] = empresa
    clean_payload["teamKey"] = team_key
    return clean_payload


def _clean_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
