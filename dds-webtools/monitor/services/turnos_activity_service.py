# -----------------------------------------------------------------------------
# Arquivo : monitor/services/turnos_activity_service.py
# Objetivo: Gestão do feed de atividades, auditoria de eventos e registros de
#           timeline de equipes no Firestore.
# -----------------------------------------------------------------------------

from __future__ import annotations

import os
import re
import threading
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from google.cloud import firestore
from services.firestore_client import db
from bdo.services.rotalog_tempo_real_service import formatar_protocolo_copel

from monitor.services.turnos_common import (
    AUTO_REASON_INACTIVE_UNKNOWN,
    DDS_TIMEZONE,
    DEFAULT_EMPRESA,
    WEBTOOLS_MONITOR_DOC,
    WEBTOOLS_ROOT_COLLECTION,
    _local_day_key,
    _normalize_text,
    _parse_iso_datetime,
    _utc_now,
    normalize_estado,
    to_utc_dt,
)


def _webtools_monitor_ref():
    return db.collection(WEBTOOLS_ROOT_COLLECTION).document(WEBTOOLS_MONITOR_DOC)


def _monitor_subcollection(name: str):
    return _webtools_monitor_ref().collection(name)


def _turno_doc_ref(empresa: str, team_key: str):
    return db.collection("turno").document(empresa).collection("equipes").document(team_key)


def _team_doc_ref(team_key: str):
    return db.collection("dds_teams").document(team_key)


def _safe_merge(doc_ref, payload: dict[str, Any]) -> None:
    if not payload:
        return
    try:
        doc_ref.set(payload, merge=True)
    except Exception:
        pass


def _activity_event_id(team_key: str, source: str, activity_at: datetime | None = None) -> str:
    dt = to_utc_dt(activity_at) or _utc_now()
    safe_team = re.sub(r"[^A-Z0-9_\-]", "_", _normalize_text(team_key) or "UNKNOWN")
    safe_source = re.sub(r"[^a-z0-9_\-]", "_", str(source or "unknown").lower())
    return f"{dt.strftime('%Y%m%dT%H%M%S%f')}_{safe_team}_{safe_source}"


def _activity_label(source: str, extra: dict[str, Any] | None = None) -> str:
    extra = extra or {}
    source_key = str(source or "").lower()
    estado = normalize_estado(extra.get("estado")) if extra.get("estado") else ""
    if source_key == "dds":
        return "Execução de DDS"
    if source_key == "mensagem":
        return "Mensagem enviada"
    if source_key == "team_members_changed":
        return "Alteração de membro da equipe"
    if source_key == "team_activated":
        return "Equipe ativada"
    if source_key == "team_deactivated":
        return "Equipe inativada"
    if source_key == "turno":
        if estado == "ABERTO":
            return "Abertura de turno"
        if estado == "FECHADO":
            return "Fechamento de turno"
        if estado == "INTERVALO":
            return "Início de intervalo"
        if estado == "DESLOCAMENTO_ESPECIAL":
            return "Deslocamento especial"
        if estado == "DESATUALIZADO":
            return "Status desatualizado"
        return "Alteração de turno"
    return str(source or "Atividade")


def _activity_feed_item(
    *,
    empresa: str,
    team_key: str,
    equipe: str | None,
    source: str,
    activity_dt: datetime,
    event_id: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    local_dt = activity_dt.astimezone(ZoneInfo(DDS_TIMEZONE)) if DDS_TIMEZONE else activity_dt
    return {
        "eventId": event_id,
        "empresa": empresa,
        "teamKey": team_key,
        "equipe": equipe or team_key,
        "source": source,
        "label": _activity_label(source, extra),
        "time": local_dt.strftime("%H:%M"),
        "activityAt": activity_dt.isoformat(),
    }


_ACTIVITY_FEED_CACHE: dict[str, list[dict[str, Any]]] = {}
_ACTIVITY_FEED_LOCK = threading.RLock()


def _update_activity_feed(empresa: str, feed_item: dict[str, Any], limit: int = 5) -> None:
    """Mantém um documento pequeno com as últimas atividades para a tela."""
    ref = _monitor_subcollection("activity_feed").document(empresa)
    try:
        with _ACTIVITY_FEED_LOCK:
            current = _ACTIVITY_FEED_CACHE.get(empresa)
            if current is None:
                snap = ref.get()
                current = list((snap.to_dict() or {}).get("items") or []) if snap.exists else []
            items = [feed_item]
            seen = {feed_item.get("eventId")}
            for item in current:
                event_id = item.get("eventId")
                if event_id in seen:
                    continue
                seen.add(event_id)
                items.append(item)
            items.sort(key=lambda item: str(item.get("activityAt") or ""), reverse=True)
            compact_items = items[:limit]
            ref.set({"empresa": empresa, "items": compact_items, "updatedAt": firestore.SERVER_TIMESTAMP}, merge=True)
            _ACTIVITY_FEED_CACHE[empresa] = compact_items
    except Exception as exc:
        print(f"[activity_feed] Erro ao atualizar feed: {exc}")


def _record_team_activity(
    *,
    empresa: str,
    team_key: str,
    equipe: str | None,
    source: str,
    activity_at: Any = None,
    event_ref: str | None = None,
    active_after_event: bool | None = None,
    extra: dict[str, Any] | None = None,
    persist_history: bool = True,
    persist_team: bool = True,
) -> None:
    activity_dt = to_utc_dt(activity_at) or _parse_iso_datetime(activity_at) or _utc_now()
    day_key = _local_day_key(activity_dt) or _utc_now().strftime("%Y-%m-%d")
    event_id = _activity_event_id(team_key, source, activity_dt)
    extra = dict(extra or {})
    feed_item = _activity_feed_item(
        empresa=empresa,
        team_key=team_key,
        equipe=equipe,
        source=source,
        activity_dt=activity_dt,
        event_id=event_id,
        extra=extra,
    )
    payload = {
        **feed_item,
        "activityDay": day_key,
        "eventRef": event_ref,
        "activeAfterEvent": active_after_event,
        "receivedAt": firestore.SERVER_TIMESTAMP,
        **extra,
    }
    if persist_history:
        _monitor_subcollection("activity_events").document(day_key).collection("events").document(event_id).set(payload, merge=True)
        _monitor_subcollection("activity_state").document(f"{empresa}_{team_key}").set(
            {
                "empresa": empresa,
                "teamKey": team_key,
                "equipe": equipe or team_key,
                "active": active_after_event,
                "lastActivityAt": activity_dt,
                "lastActivitySource": source,
                "lastEventId": event_id,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
    _update_activity_feed(empresa, feed_item)
    if persist_team:
        _safe_merge(
            _team_doc_ref(team_key),
            {
                "lastActivityAt": activity_dt,
                "lastActivitySource": source,
                "lastActivityEventId": event_id,
                "updatedAt": firestore.SERVER_TIMESTAMP,
                **({"active": active_after_event} if isinstance(active_after_event, bool) else {}),
            },
        )


def _read_activity_feed(empresa: str, limit: int = 5) -> dict[str, Any]:
    try:
        snap = _monitor_subcollection("activity_feed").document(empresa).get()
        data = snap.to_dict() if snap.exists else {}
        items = list((data or {}).get("items") or [])
        return {"empresa": empresa, "items": items[: max(1, min(int(limit or 5), 20))], "cached": snap.exists}
    except Exception as exc:
        print(f"[activity_feed] Erro ao ler feed: {exc}")
        return {"empresa": empresa, "items": [], "cached": False, "error": str(exc)}


def get_activity_feed(empresa: str = DEFAULT_EMPRESA, limit: int = 30) -> dict[str, Any]:
    if os.getenv("ROTALOG_PERSISTENCE_MODE", "json").strip().lower() != "firestore":
        try:
            from bdo.services.rotalog_sync_task import get_rotalog_activity_feed
            result = get_rotalog_activity_feed(limit=limit)
            return {"empresa": empresa, **result}
        except Exception as exc:
            return {
                "empresa": empresa,
                "items": [],
                "summary": {"abertas": 0, "comerciais": 0, "emergenciais": 0},
                "source": "json",
                "error": str(exc),
            }
    return _read_activity_feed(empresa, limit=limit)


def _persist_team_activity_if_newer(
    team_key: str,
    *,
    current_activity_at: Any = None,
    activity_at: datetime | None = None,
    activity_source: str,
    dds_day: str | None = None,
) -> None:
    if not activity_at:
        return
    current_dt = to_utc_dt(current_activity_at) or _parse_iso_datetime(current_activity_at)
    if current_dt and activity_at <= current_dt:
        return
    payload: dict[str, Any] = {
        "lastActivityAt": activity_at,
        "lastActivitySource": activity_source,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if dds_day:
        payload["lastActivityDdsDay"] = dds_day
    _safe_merge(_team_doc_ref(team_key), payload)


def _manual_inactive_blocks_activity(team_data: dict[str, Any], activity_dt: datetime | None, activity_day: str | None) -> bool:
    if team_data.get("autoInactiveReason") != "MANUAL":
        return False
    inactive_at = to_utc_dt(team_data.get("autoInactiveAt"))
    if not inactive_at:
        return False
    if activity_dt:
        return activity_dt <= inactive_at
    inactive_day = _local_day_key(inactive_at)
    return bool(activity_day and inactive_day and activity_day <= inactive_day)


def _persist_team_active_state(
    team_key: str,
    *,
    active: bool,
    reason: str | None = None,
    source_dt: Any = None,
    source_dds_day: str | None = None,
    source_kind: str | None = None,
) -> None:
    payload: dict[str, Any] = {"active": active}

    if active:
        payload.update(
            {
                "autoInactiveReason": firestore.DELETE_FIELD,
                "autoInactiveAt": firestore.DELETE_FIELD,
                "autoReactivatedAt": firestore.SERVER_TIMESTAMP,
            }
        )
        activity_dt = to_utc_dt(source_dt)
        if activity_dt:
            payload["autoInactiveLastSeenUpdatedAt"] = activity_dt
            payload["lastActivityAt"] = activity_dt
            payload["lastActivitySource"] = source_kind or "unknown"
            payload["lastActivityUpdatedAt"] = firestore.SERVER_TIMESTAMP
        else:
            payload["autoInactiveLastSeenUpdatedAt"] = firestore.DELETE_FIELD
        if source_dds_day:
            payload["autoInactiveLastSeenDdsDay"] = source_dds_day
            payload["lastActivityDdsDay"] = source_dds_day
        else:
            payload["autoInactiveLastSeenDdsDay"] = firestore.DELETE_FIELD
    else:
        payload.update(
            {
                "autoInactiveReason": reason or AUTO_REASON_INACTIVE_UNKNOWN,
                "autoInactiveAt": firestore.SERVER_TIMESTAMP,
            }
        )
        if source_dt is not None:
            payload["autoInactiveLastSeenUpdatedAt"] = source_dt
        if source_dds_day:
            payload["autoInactiveLastSeenDdsDay"] = source_dds_day

    _safe_merge(_team_doc_ref(team_key), payload)


def _apply_dds_activity_trigger(team_key: str, data: dict[str, Any], day: str | None, *, empresa: str = DEFAULT_EMPRESA) -> None:
    from monitor.services.dds_presence_service import (
        _extract_dds_timestamp,
        _dds_day_to_effective_contact_dt,
    )

    team_snap = _team_doc_ref(team_key).get()
    team_data = team_snap.to_dict() or {}
    if not team_data:
        return
    event_dt = _extract_dds_timestamp(data, day) or _dds_day_to_effective_contact_dt(day) or _utc_now()
    _persist_team_activity_if_newer(
        team_key,
        current_activity_at=team_data.get("lastActivityAt"),
        activity_at=event_dt,
        activity_source="dds",
        dds_day=day,
    )
    if not bool(team_data.get("active", True)):
        if _manual_inactive_blocks_activity(team_data, event_dt, day):
            print(f"DDS trigger ignored for {team_key}: manual inactive is newer than DDS activity.")
            return
        _persist_team_active_state(team_key, active=True, source_dt=event_dt, source_dds_day=day)
    _record_team_activity(
        empresa=empresa,
        team_key=team_key,
        equipe=data.get("equipe") or team_data.get("displayName") or team_key,
        source="dds",
        activity_at=event_dt,
        event_ref=data.get("eventRef"),
        active_after_event=True,
        extra={"ddsDay": day, "headerDate": data.get("headerDate"), "headerTitle": data.get("headerTitle")},
    )


def _describe_team_change_details(data: dict[str, Any], team_key: str = "", empresa: str = "") -> str:
    """Formata a mensagem de sincronização no padrão:
    E3V75 - ChicoEletro - Atividade: EXECUCAO - Emergência: CHAVE - Protocolo: 50954710 - (Via Rotalog).
    """
    if not data:
        return f"{team_key} - {empresa} - (Via Rotalog)."

    equipe_code = data.get("equipe") or team_key or "EQUIPE"
    empresa_str = data.get("empresa") or empresa or "ChicoEletro"

    # 1. Atividade / Status
    atividade_status = (
        data.get("atividadeStatus") or
        data.get("monitorStatus") or
        data.get("estado") or
        data.get("estadoConsolidado") or
        "TURNO ABERTO"
    )
    if atividade_status == "EXECUCAO":
        atividade_str = "EXECUCAO"
    elif atividade_status == "DESLOCAMENTO":
        atividade_str = "DESLOCAMENTO"
    elif atividade_status == "INTERVALO":
        atividade_str = "INTERVALO"
    elif atividade_status == "FECHADO":
        atividade_str = "TURNO FECHADO"
    elif atividade_status == "ABERTO":
        atividade_str = "TURNO ABERTO"
    else:
        atividade_str = str(atividade_status)

    # 2. Busca serviço em andamento ou último executado
    rotalog_snap = data.get("rotalogSnapshot") if isinstance(data.get("rotalogSnapshot"), dict) else {}
    bdo_list = data.get("bdoList") or rotalog_snap.get("bdoList") or rotalog_snap.get("ssExecutadas") or []
    ss_andamento = (
        rotalog_snap.get("ssEmAndamento") or
        data.get("ssEmAndamento") or
        ([data.get("atividadeAtual")] if data.get("atividadeAtual") else []) or
        ([rotalog_snap.get("atividade_atual")] if rotalog_snap.get("atividade_atual") else []) or
        (bdo_list if isinstance(bdo_list, list) else [])
    )

    servico_str = ""
    protocolo_str = ""

    if isinstance(ss_andamento, list) and ss_andamento and isinstance(ss_andamento[0], dict):
        ss1 = ss_andamento[0]
        cat = str(ss1.get("categoria") or "").upper()

        raw_proto = str(
            ss1.get("protocolo") or
            ss1.get("protocoloBruto") or
            ss1.get("ssId") or
            data.get("nocSs") or
            data.get("protocolo") or
            ""
        ).strip()

        proto_limpo = formatar_protocolo_copel(raw_proto)

        raw_tipo = str(ss1.get("tipo") or ss1.get("descricao") or ss1.get("nome") or "").strip()
        tipo_limpo = re.sub(r"\.\d+(\.\d+)?$", "", raw_tipo) if raw_tipo else ""

        if tipo_limpo and proto_limpo and tipo_limpo == proto_limpo:
            alt_tipo = str(ss1.get("descricao") or ss1.get("nome") or ss1.get("tipoServico") or "").strip()
            if alt_tipo:
                tipo_limpo = alt_tipo

        if "EMERG" in cat:
            servico_str = f"Emergência: {tipo_limpo}" if tipo_limpo else "Emergência"
        elif "COMER" in cat:
            servico_str = f"Comercial : {tipo_limpo}" if tipo_limpo else "Comercial"
        elif cat:
            servico_str = f"{cat}: {tipo_limpo}" if tipo_limpo else cat
        elif tipo_limpo:
            servico_str = f"Serviço: {tipo_limpo}"

        if proto_limpo:
            protocolo_str = f"Protocolo: {proto_limpo}"

    # 3. Origem
    origem = data.get("origemAtualizacao") or data.get("deviceIdLastWriter") or data.get("reactivatedBy")
    if origem in ("ROTALOG_AUTO_SYNC", "ROTALOG_MAIS_RECENTE"):
        origem_str = "(Via Rotalog)"
    elif origem == "DDS_MAIS_RECENTE":
        origem_str = "(Via Tablet/App DDS)"
    elif origem:
        origem_str = f"(Via {origem})"
    else:
        origem_str = "(Via Rotalog)"

    parts = [f"{equipe_code} - {empresa_str}", f"Atividade: {atividade_str}"]
    if servico_str:
        parts.append(servico_str)
    if protocolo_str:
        parts.append(protocolo_str)
    parts.append(origem_str)

    return " - ".join(parts) + "."
