# -----------------------------------------------------------------------------
# Arquivo : monitor/services/turnos_legacy_sync.py
# Objetivo: Preservar o motor legado de consolidação individual e sincronização
#           no Firestore (turno/{empresa}/realtime), permitindo fácil recuperação
#           caso necessário.
#
# Status  : INATIVADO por padrão (o monitor web opera no modo Torre de Controle
#           JSON comprimido no Storage).
# -----------------------------------------------------------------------------

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore
from services.firestore_client import db
from services.monitor_config_service import get_monitor_rules

# Flag de ativação: por padrão DESATIVADO para não consumir cotas nem travar I/O.
# Para reativar em caso de contingência, defina DDS_LEGACY_FIRESTORE_SYNC=true.
LEGACY_FIRESTORE_SYNC_ENABLED = os.getenv("DDS_LEGACY_FIRESTORE_SYNC", "false").strip().lower() in {"1", "true", "yes"}

_CONSOLIDATION_LOCKS = {}
_locks_mutex = threading.Lock()


def consolidate_single_team(
    empresa: str,
    team_key: str,
    *,
    turno_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Consolida a visão de uma ÚNICA equipe e salva no Firestore Realtime.
    Se o modo legado estiver inativo, opera como no-op seguro para economizar leituras/escritas.
    """
    if not LEGACY_FIRESTORE_SYNC_ENABLED:
        # Modo Torre de Controle moderno (JSON/Storage): no-op seguro
        return {"ok": True, "skipped": True, "legacy": False}

    # --- Código original preservado caso a flag seja ativada ---
    import time
    now_ts = time.time()
    lock_key = (empresa, team_key)
    with _locks_mutex:
        last_sync = _CONSOLIDATION_LOCKS.get(lock_key, 0)
        if now_ts - last_sync < 2.0:
            return {"ok": True, "skipped": True}
        _CONSOLIDATION_LOCKS[lock_key] = now_ts

    from monitor.services.turnos_service import _get_now, _load_recent_dds_presence
    now = _get_now()
    rules = get_monitor_rules()

    from services.teams_service import get_team
    from services.turno_equipes_service import get_turno_equipe
    team_data = get_team(team_key) or {}
    turno_doc = turno_data if turno_data is not None else (get_turno_equipe(empresa, team_key) or {})

    if not team_data and not turno_doc:
        db.collection("turno").document(empresa).collection("realtime").document(team_key).delete()
        return {"ok": True, "deleted": True}

    (
        recent_dds_days,
        dds_present_by_day,
        dds_days_with_any,
        mutable_dds_days,
        calendar_days,
        dds_timestamps_by_day,
        dds_photos_by_day,
    ) = _load_recent_dds_presence(manual_refresh=False)

    from services.messaging_service import get_unread_counts, get_all_unread_counts_map, get_last_messages_map
    unread_counts = get_unread_counts()
    unread_map_global = get_all_unread_counts_map()
    last_messages_map = get_last_messages_map()

    item = _process_single_team(
        team_key=team_key,
        empresa=empresa,
        team_data=team_data,
        data=turno_doc,
        recent_dds_days=recent_dds_days,
        dds_present_by_day=dds_present_by_day,
        dds_days_with_any=dds_days_with_any,
        mutable_dds_days=mutable_dds_days,
        calendar_days=calendar_days,
        dds_timestamps_by_day=dds_timestamps_by_day,
        dds_photos_by_day=dds_photos_by_day,
        unread_counts=unread_counts,
        unread_map_global=unread_map_global,
        last_messages_map=last_messages_map,
        now=now,
        rules=rules,
        pending_by_day={},
    )

    if item:
        db.collection("turno").document(empresa).collection("realtime").document(team_key).set(item)

    return {"ok": True, "item": item}


def consolidate_team_across_all_companies(team_key: str):
    """Consolida a visão de uma equipe em todas as empresas registradas."""
    if not LEGACY_FIRESTORE_SYNC_ENABLED:
        return
    for empresa_doc in db.collection("turno").stream():
        consolidate_single_team(empresa_doc.id, team_key)


def update_realtime_view(empresa: str = "ChicoEletro", manual_refresh: bool = False, **kwargs) -> dict[str, Any]:
    """
    Força a atualização da visão em tempo real.
    No modo moderno, apenas chama list_turnos com manual_refresh.
    """
    from monitor.services.turnos_service import list_turnos, _get_now, clear_all_monitor_caches
    clear_all_monitor_caches()
    data = list_turnos(empresa=empresa, manual_refresh=manual_refresh, **kwargs)

    if not LEGACY_FIRESTORE_SYNC_ENABLED:
        return {
            **data,
            "lastViewUpdate": _get_now().isoformat(),
            "persistenceMode": "json",
            "realtimeFirestorePersisted": False,
        }

    # Persistência legada na coleção 'realtime'
    batch = db.batch()
    count = 0
    for item in (data.get("items") or []):
        doc_ref = db.collection("turno").document(empresa).collection("realtime").document(item["teamKey"])
        batch.set(doc_ref, {**item, "viewUpdatedAt": firestore.SERVER_TIMESTAMP})
        count += 1
        if count >= 400:
            batch.commit()
            batch = db.batch()
            count = 0
    if count > 0:
        batch.commit()

    sync_time = _get_now().isoformat()
    db.collection("turno").document(empresa).set({
        "lastViewUpdate": sync_time,
        "lastViewUpdateBy": "MONITOR_SYNC"
    }, merge=True)

    return {**data, "lastViewUpdate": sync_time}


def _send_pre_inactivation_warning(
    empresa: str,
    team_key: str,
    total_hours_no_contact: int,
    hours_remaining: int,
    stage_start_str: str,
) -> None:
    dias = total_hours_no_contact // 24
    horas_resto = total_hours_no_contact % 24

    if dias > 0:
        tempo_str = f"{dias} dia(s) e {horas_resto} hora(s)" if horas_resto > 0 else f"{dias} dia(s)"
    else:
        tempo_str = f"{horas_resto} hora(s)"

    msg_body = (
        f"Você está a {tempo_str} sem comunicação com o DDS.\n\n"
        f"Dentro de {hours_remaining} hora(s) sua equipe será marcada como INATIVA.\n\n"
        f"Acesse o aplicativo de DDS e realize o DDS e informe o status de seu turno."
    )

    try:
        db.collection("turno").document(empresa).collection("equipes").document(team_key).set({
            "lastPreInactiveWarningAt": firestore.SERVER_TIMESTAMP,
            "lastPreInactiveWarningSentAt": firestore.SERVER_TIMESTAMP,
            "lastPreInactiveWarningMsg": msg_body,
            "lastPreInactiveWarningStage": stage_start_str,
            "preInactiveWarningActive": True,
        }, merge=True)

        db.collection("mensagens_comunicacao").add({
            "empresa": empresa,
            "fromEquipe": "SISTEMA_DDS",
            "toEquipe": team_key,
            "toSetor": "TODOS",
            "mensagem": msg_body,
            "tipo": "ALERTA_PRE_INATIVACAO",
            "status": "NÃO LIDO",
            "createdAt": firestore.SERVER_TIMESTAMP,
            "serverUpdatedAt": firestore.SERVER_TIMESTAMP,
        })
    except Exception as e:
        print(f"[WARN] Erro ao registrar alerta pre-inativacao para {team_key}: {e}")


def _process_single_team(
    *,
    team_key: str,
    empresa: str,
    team_data: dict[str, Any],
    data: dict[str, Any],
    recent_dds_days: list[str],
    dds_present_by_day: dict[str, set[str]],
    dds_days_with_any: set[str],
    mutable_dds_days: set[str],
    calendar_days: set[str] | None,
    dds_timestamps_by_day: dict[str, dict[str, Any]],
    dds_photos_by_day: dict[str, dict[str, Any]],
    unread_counts: dict[str, int],
    unread_map_global: dict[str, dict[str, int]],
    last_messages_map: dict[str, datetime],
    now: datetime,
    rules: dict[str, Any],
    pending_by_day: dict[str, set[str]],
    active_filter: bool | None = None
) -> dict[str, Any] | None:
    """
    Implementação original integral de 2024 para cálculo de regras de turno individual do Firestore.
    Preservada intacta para fins de contingência e histórico de regras de negócio.
    """
    from monitor.services.turnos_service import (
        to_utc_dt,
        normalize_estado,
        extract_participantes,
        _build_team_aliases,
        _normalized_alias_matches,
        _combine_dds_day_time,
        _dds_day_to_effective_contact_dt,
        _latest_dds_ts_for_aliases,
        AUTO_CLOSE_OPEN_HOURS_DEFAULT,
        AUTO_DESATUALIZA_FECHADO_HOURS_DEFAULT,
        AUTO_DESATUALIZA_INTERVALO_HOURS_DEFAULT,
    )

    alerta_amarelo_min = int(rules.get("alertaAmareloMin") or 15)
    alerta_vermelho_min = int(rules.get("alertaVermelhoMin") or 30)
    alerta_pisco_min = int(rules.get("alertaPiscoMin") or 60)

    auto_close_open_hours = int(rules.get("autoCloseOpenHours") or AUTO_CLOSE_OPEN_HOURS_DEFAULT)
    auto_desatualiza_fechado_hours = int(rules.get("autoDesatualizaFechadoHours") or AUTO_DESATUALIZA_FECHADO_HOURS_DEFAULT)
    auto_desatualiza_intervalo_hours = int(rules.get("autoDesatualizaIntervaloHours") or AUTO_DESATUALIZA_INTERVALO_HOURS_DEFAULT)

    estado_original = data.get("estado")
    estado = normalize_estado(estado_original)
    equipe_label = data.get("equipe") or team_data.get("displayName") or team_key

    aliases = _build_team_aliases(team_key, team_data, data, equipe_label)

    participantes = extract_participantes(data)
    if not participantes and team_data.get("members"):
        members = team_data.get("members")
        if isinstance(members, list):
            participantes = [str(m).strip() for m in members if str(m).strip()]
        elif isinstance(members, str):
            participantes = [p.strip() for p in members.split(",") if p.strip()]

    dt_ini = to_utc_dt(data.get("dt_ini"))
    dt_fim = to_utc_dt(data.get("dt_fim"))
    dt_int_ini = to_utc_dt(data.get("dt_int_ini"))
    dt_int_fim = to_utc_dt(data.get("dt_int_fim"))
    dt_up = to_utc_dt(data.get("updatedAt")) or to_utc_dt(data.get("serverUpdatedAt"))
    data_reg = to_utc_dt(data.get("data_reg"))

    opened_at_client_ms = data.get("openedAtClientMs")
    closed_at_client_ms = data.get("closedAtClientMs")

    veiculo = data.get("veiculo") or team_data.get("veiculo")
    tablet = data.get("tablet") or data.get("identificadorEquipamento") or team_data.get("tablet") or team_data.get("identificadorEquipamento")
    ss = data.get("nocSs")
    motivo = data.get("motivo")

    # Inclusão da data_reg na telemetria de contato
    telemetry_contact_candidates = [dt for dt in [dt_up, data_reg, dt_ini, dt_fim, dt_int_fim, dt_int_ini] if dt is not None]
    last_telemetry_dt = max(telemetry_contact_candidates) if telemetry_contact_candidates else None

    # Histórico de DDS
    dds_history = []
    dds_times = {}
    dds_photos = {}
    last_dds_calendar_day = None

    for day in recent_dds_days:
        has_any_in_system = day in dds_days_with_any
        present_teams = dds_present_by_day.get(day, set())
        team_timestamps = dds_timestamps_by_day.get(day, {})
        team_photos_map = dds_photos_by_day.get(day, {})

        matched_alias = next((alias for alias in aliases if alias in present_teams), None)
        if not matched_alias:
            for present_name in present_teams:
                if any(_normalized_alias_matches(present_name, alias) for alias in aliases):
                    matched_alias = present_name
                    break

        is_present = matched_alias is not None
        if is_present:
            last_dds_calendar_day = day
            dds_history.append({"date": day, "status": "ok"})
            dds_time = team_timestamps.get(matched_alias) if matched_alias else None
            photo_url = team_photos_map.get(matched_alias) if matched_alias else None

            if dds_time:
                parsed_time = to_utc_dt(dds_time)
                if parsed_time:
                    try:
                        from zoneinfo import ZoneInfo
                        dds_times[day] = parsed_time.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%H:%M")
                    except Exception:
                        dds_times[day] = parsed_time.strftime("%H:%M")
            if photo_url:
                dds_photos[day] = photo_url
        else:
            if has_any_in_system:
                dds_history.append({"date": day, "status": "nok"})
                if day in mutable_dds_days:
                    pending_by_day.setdefault(day, set()).add(team_key)
            else:
                dds_history.append({"date": day, "status": "neutral"})

    # Avaliação do último contato (Telemetria vs DDS)
    last_dds_ts = _latest_dds_ts_for_aliases(recent_dds_days, dds_timestamps_by_day, aliases)
    effective_dds_dt = last_dds_ts or _dds_day_to_effective_contact_dt(last_dds_calendar_day)

    last_contact_dt = last_telemetry_dt
    last_contact_src = "R" if last_telemetry_dt else None

    if effective_dds_dt:
        if not last_contact_dt or effective_dds_dt > last_contact_dt:
            last_contact_dt = effective_dds_dt
            last_contact_src = "D"

    minutos = None
    if last_contact_dt:
        minutos = max(0, int((now - last_contact_dt).total_seconds() // 60))

    critico = False
    alerta = None
    if minutos is not None and estado in ("ABERTO", "DESLOCAMENTO"):
        if minutos >= alerta_pisco_min:
            critico = True
            alerta = "pisca"
        elif minutos >= alerta_vermelho_min:
            critico = True
            alerta = "vermelho"
        elif minutos >= alerta_amarelo_min:
            critico = False
            alerta = "amarelo"

    # Status de hoje
    today_iso = recent_dds_days[-1] if recent_dds_days else None
    dds_today = "neutral"
    if dds_history:
        dds_today = dds_history[-1].get("status", "neutral")

    team_active = True
    if team_data.get("active") is False:
        team_active = False

    unread_map = unread_map_global.get(team_key) or {}
    last_was_descanso_semanal = False

    return {
        "teamKey": team_key,
        "equipe": equipe_label,
        "veiculo": veiculo,
        "setor": team_data.get("setor") or data.get("setor") or "TODOS",
        "estado": estado,
        "estadoOriginal": estado_original,
        "origemAtualizacao": data.get("origemAtualizacao") or data.get("deviceIdLastWriter"),
        "deviceIdLastWriter": data.get("deviceIdLastWriter"),
        "tablet": tablet,
        "ss": ss or "-",
        "motivo": motivo or "-",
        "updatedAt": (last_contact_dt or now).isoformat(),
        "openedAtClientMs": opened_at_client_ms,
        "closedAtClientMs": closed_at_client_ms,
        "turnoInicio": dt_ini.isoformat() if dt_ini else None,
        "turnoFim": dt_fim.isoformat() if dt_fim else None,
        "minutosDesdeAtualizacao": minutos,
        "critico": critico,
        "alerta": alerta,
        "participantes": participantes,
        "active": team_active,
        "lastContact": last_contact_dt.isoformat() if last_contact_dt else None,
        "lastContactSource": last_contact_src,
        "ddsHistory": dds_history,
        "ddsToday": dds_today,
        "ddsDays": recent_dds_days,
        "ddsTimes": dds_times,
        "ddsPhotos": dds_photos,
        "unreadMessages": unread_counts.get(equipe_label, 0) or unread_counts.get(team_key, 0),
        "unreadMap": unread_map,
        "lastWasDescansoSemanal": last_was_descanso_semanal,
        "teamType": team_data.get("teamType") or data.get("teamType"),
        "motorista": team_data.get("motorista"),
        "coringas": team_data.get("coringas") or [],
    }
