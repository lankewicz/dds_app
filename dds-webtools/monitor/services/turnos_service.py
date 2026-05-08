# -----------------------------------------------------------------------------
# Arquivo : services/turnos_service.py
# Objetivo: Consolidar a leitura do monitor web, cruzando turno/{empresa}/equipes
#           com dds_teams/{teamKey}, e aplicar as regras de alerta e filtro de
#           equipes ativas/inativas.
#           Também cruza a coleção DDS do app para montar o histórico visual
# -----------------------------------------------------------------------------

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from google.cloud import firestore, storage
from services.firestore_client import db
from services.teams_service import list_teams_map
from services.monitor_config_service import get_monitor_polling_seconds, get_monitor_rules
from services.messaging_service import get_unread_counts, CURRENT_SETOR

APP_TITLE = "DDS - Monitor de Turnos"
DEFAULT_EMPRESA = os.getenv("DDS_EMPRESA_PADRAO", "ChicoEletro")

POLLING_DEFAULT_SEC = int(os.getenv("DDS_POLLING_SEGUNDOS", "600"))
DDS_HISTORY_DAYS = int(os.getenv("DDS_HISTORY_DAYS", "20"))
DDS_COLLECTION = os.getenv("DDS_COLLECTION_NAME", "DDS")
DDS_TIMEZONE = os.getenv("DDS_TIMEZONE", "America/Sao_Paulo")
DDS_MUTABLE_REFRESH_SEC = int(os.getenv("DDS_MUTABLE_REFRESH_SEC", "1800"))
DDS_LAST_BUSINESS_REFRESH_SEC = int(os.getenv("DDS_LAST_BUSINESS_REFRESH_SEC", "3600"))
DDS_BUCKET_NAME = os.getenv("DDS_BUCKET_NAME", "dds-treinamentos.firebasestorage.app")
DDS_CALENDAR_SOURCE_BLOB = os.getenv("DDS_CALENDAR_SOURCE_BLOB", "DDSv2/lista.json")
DDS_CALENDAR_CACHE_BLOB = os.getenv("DDS_CALENDAR_CACHE_BLOB", "_cache/dds_calendar_history.json")
DDS_DAY_CACHE_PREFIX = os.getenv("DDS_DAY_CACHE_PREFIX", "_cache/days")
AUTO_CLOSE_OPEN_HOURS_DEFAULT = int(os.getenv("DDS_AUTO_CLOSE_OPEN_HOURS", "16"))
AUTO_DESATUALIZA_FECHADO_HOURS_DEFAULT = int(os.getenv("DDS_AUTO_DESATUALIZA_FECHADO_HOURS", "48"))
AUTO_DESATUALIZA_INTERVALO_HOURS_DEFAULT = int(os.getenv("DDS_AUTO_DESATUALIZA_INTERVALO_HOURS", "8"))

AUTO_REASON_CLOSE_OPEN = "AUTO_CLOSE_OPEN_TIMEOUT"
AUTO_REASON_DESAT_FECHADO = "AUTO_DESATUALIZADO_FECHADO_TIMEOUT"
AUTO_REASON_DESAT_DESLOCAMENTO = "AUTO_DESATUALIZADO_DESLOCAMENTO_TIMEOUT"
AUTO_REASON_DESAT_INTERVALO = "AUTO_DESATUALIZADO_INTERVALO_TIMEOUT"
AUTO_REASON_INACTIVE_UNKNOWN = "AUTO_INACTIVE_DESCONHECIDO"

_DDS_DAY_CACHE: dict[str, dict[str, Any]] = {}
_DDS_CALENDAR_CACHE: dict[str, Any] = {}
_STORAGE_CLIENT = None


def get_monitor_config() -> dict[str, Any]:
    rules = get_monitor_rules()
    polling_seconds = get_monitor_polling_seconds()
    return {
        "defaultEmpresa": DEFAULT_EMPRESA,
        "pollingSeconds": polling_seconds or POLLING_DEFAULT_SEC,
        "rules": rules,
    }


def to_utc_dt(ts: Any):
    if not ts:
        return None

    if hasattr(ts, "to_datetime"):
        dt = ts.to_datetime()
    else:
        dt = ts

    if getattr(dt, "tzinfo", None) is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt


def normalize_estado(value: str | None) -> str:
    raw = (value or "DESCONHECIDO").strip().upper()
    aliases = {
        "ESPECIAL": "DESLOCAMENTO_ESPECIAL",
        "DESLOCAMENTO": "DESLOCAMENTO_ESPECIAL",
    }
    return aliases.get(raw, raw)


def string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []

    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if item is None:
            continue
        name = str(item).strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def extract_participantes(data: dict[str, Any]) -> list[str]:
    participants = string_list(data.get("membersSnapshot"))
    if participants:
        return participants

    for key in ("members", "eletricistas", "participantes"):
        participants = string_list(data.get(key))
        if participants:
            return participants

    return []


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _storage_client() -> storage.Client:
    global _STORAGE_CLIENT
    if _STORAGE_CLIENT is None:
        _STORAGE_CLIENT = storage.Client()
    return _STORAGE_CLIENT


def _storage_bucket():
    return _storage_client().bucket(DDS_BUCKET_NAME)


def _storage_blob_name(*parts: str) -> str:
    clean = [str(part or "").strip("/") for part in parts if str(part or "").strip("/")]
    return "/".join(clean)


def _storage_read_json(blob_name: str) -> dict[str, Any] | None:
    try:
        blob = _storage_bucket().blob(blob_name)
        if not blob.exists():
            return None
        raw = blob.download_as_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _storage_write_json(blob_name: str, payload: dict[str, Any]) -> None:
    try:
        blob = _storage_bucket().blob(blob_name)
        blob.upload_from_string(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            content_type="application/json; charset=utf-8",
        )
    except Exception:
        pass


def _parse_iso_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _local_today() -> datetime.date:
    try:
        tz = ZoneInfo(DDS_TIMEZONE)
    except Exception:
        tz = timezone.utc
    return datetime.now(tz).date()


def _recent_history_days(days: int = DDS_HISTORY_DAYS) -> list[str]:
    today = _local_today()
    return [
        (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(days - 1, -1, -1)
    ]


def _last_business_day(ref_day: datetime.date) -> datetime.date:
    day = ref_day - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _mutable_dds_days(recent_days: list[str]) -> set[str]:
    today = _local_today()
    today_key = today.strftime("%Y-%m-%d")
    last_business_key = _last_business_day(today).strftime("%Y-%m-%d")
    return {day for day in recent_days if day in {today_key, last_business_key}}


def _prune_dds_day_cache(valid_days: set[str]) -> None:
    stale_days = [day for day in _DDS_DAY_CACHE.keys() if day not in valid_days]
    for day in stale_days:
        _DDS_DAY_CACHE.pop(day, None)


def _should_refresh_dds_day(day: str, mutable_days: set[str]) -> bool:
    entry = _DDS_DAY_CACHE.get(day)
    if entry is None:
        return True

    if entry.get("frozen"):
        return False

    if day not in mutable_days:
        return False

    fetched_at = entry.get("fetched_at")
    if not isinstance(fetched_at, datetime):
        return True

    age_sec = (datetime.now(timezone.utc) - fetched_at).total_seconds()
    return age_sec >= DDS_MUTABLE_REFRESH_SEC

def _normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_dds_day(header_date: Any) -> str | None:
    raw = str(header_date or "").strip()
    if not raw:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", raw)
    return m.group(1) if m else None


def _collect_manifest_days(value: Any, out: set[str]) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            _collect_manifest_days(key, out)
            _collect_manifest_days(inner, out)
        return

    if isinstance(value, list):
        for inner in value:
            _collect_manifest_days(inner, out)
        return

    text = str(value or "")
    if not text:
        return

    for match in re.finditer(r"\b(\d{4}-\d{2}-\d{2})\b", text):
        out.add(match.group(1))


def _calendar_payload_to_days(payload: dict[str, Any] | None) -> set[str]:
    if not isinstance(payload, dict):
        return set()

    days: set[str] = set()
    if isinstance(payload.get("past_days"), list):
        days.update(str(day).strip() for day in payload.get("past_days") if str(day).strip())
    if isinstance(payload.get("current_manifest_days"), list):
        days.update(str(day).strip() for day in payload.get("current_manifest_days") if str(day).strip())

    if days:
        return {day for day in days if _extract_dds_day(day)}

    _collect_manifest_days(payload, days)
    return {day for day in days if _extract_dds_day(day)}


def _load_calendar_source_days() -> set[str] | None:
    payload = _storage_read_json(DDS_CALENDAR_SOURCE_BLOB)
    if payload is None:
        return None
    return _calendar_payload_to_days(payload)


def _calendar_cache_is_fresh(payload: dict[str, Any]) -> bool:
    refreshed_on = str(payload.get("refreshed_on") or "").strip()
    if refreshed_on and refreshed_on == _local_today().strftime("%Y-%m-%d"):
        return True

    updated_at = _parse_iso_datetime(payload.get("updated_at"))
    if not updated_at:
        return False

    local_now = datetime.now(ZoneInfo(DDS_TIMEZONE)) if DDS_TIMEZONE else datetime.now(timezone.utc)
    local_updated = updated_at.astimezone(ZoneInfo(DDS_TIMEZONE)) if DDS_TIMEZONE else updated_at
    return local_updated.date() == local_now.date()


def _load_dds_calendar_days(force_refresh: bool = False) -> set[str] | None:
    cached_payload = _DDS_CALENDAR_CACHE.get("payload") if isinstance(_DDS_CALENDAR_CACHE.get("payload"), dict) else None
    if cached_payload and not force_refresh and _calendar_cache_is_fresh(cached_payload):
        return _calendar_payload_to_days(cached_payload)

    storage_payload = _storage_read_json(DDS_CALENDAR_CACHE_BLOB)
    if storage_payload and not force_refresh and _calendar_cache_is_fresh(storage_payload):
        _DDS_CALENDAR_CACHE["payload"] = storage_payload
        return _calendar_payload_to_days(storage_payload)

    source_days = _load_calendar_source_days()
    if source_days is None:
        fallback_payload = storage_payload or cached_payload
        if isinstance(fallback_payload, dict):
            _DDS_CALENDAR_CACHE["payload"] = fallback_payload
            return _calendar_payload_to_days(fallback_payload)
        return None

    today_key = _local_today().strftime("%Y-%m-%d")
    prior_payload = storage_payload or cached_payload or {}
    prior_past_days = {
        str(day).strip()
        for day in (prior_payload.get("past_days") or [])
        if str(day).strip()
    }

    source_past_days = {day for day in source_days if day <= today_key}
    merged_payload = {
        "updated_at": _utc_now_iso(),
        "refreshed_on": today_key,
        "source_blob": DDS_CALENDAR_SOURCE_BLOB,
        "cache_blob": DDS_CALENDAR_CACHE_BLOB,
        "past_days": sorted(prior_past_days | source_past_days),
        "current_manifest_days": sorted(source_days),
    }
    _storage_write_json(DDS_CALENDAR_CACHE_BLOB, merged_payload)
    _DDS_CALENDAR_CACHE["payload"] = merged_payload
    return _calendar_payload_to_days(merged_payload)


def _day_cache_blob(day: str) -> str:
    return _storage_blob_name(DDS_DAY_CACHE_PREFIX, f"{day}.json")


def _serialize_day_cache(day: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": day,
        "updated_at": (entry.get("fetched_at") or _utc_now()).isoformat() if isinstance(entry.get("fetched_at"), datetime) else _utc_now_iso(),
        "frozen": bool(entry.get("frozen")),
        "has_any": bool(entry.get("has_any")),
        "teams_executed": sorted(str(team).strip() for team in (entry.get("present") or set()) if str(team).strip()),
    }


def _deserialize_day_cache(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    day = _extract_dds_day(payload.get("date"))
    if not day:
        return None
    teams_executed = {str(team).strip() for team in (payload.get("teams_executed") or []) if str(team).strip()}
    return {
        "date": day,
        "present": teams_executed,
        "has_any": bool(payload.get("has_any")) or bool(teams_executed),
        "fetched_at": _parse_iso_datetime(payload.get("updated_at")),
        "frozen": bool(payload.get("frozen")),
        "pending_team_keys": set(),
    }


def _load_storage_day_cache(day: str) -> dict[str, Any] | None:
    payload = _storage_read_json(_day_cache_blob(day))
    entry = _deserialize_day_cache(payload)
    if not entry:
        return None
    _DDS_DAY_CACHE[day] = entry
    return entry


def _save_storage_day_cache(day: str, entry: dict[str, Any]) -> None:
    _storage_write_json(_day_cache_blob(day), _serialize_day_cache(day, entry))


def _day_refresh_seconds(day: str, mutable_days: set[str], manual_refresh: bool = False) -> int | None:
    if day not in mutable_days:
        return None
    if manual_refresh:
        return 0

    today_key = _local_today().strftime("%Y-%m-%d")
    if day == today_key:
        return max(15, int(get_monitor_polling_seconds()))
    return max(60, DDS_LAST_BUSINESS_REFRESH_SEC)


def _should_refresh_day_entry(entry: dict[str, Any] | None, ttl_sec: int | None) -> bool:
    if entry is None:
        return True
    if ttl_sec is None:
        return False

    fetched_at = entry.get("fetched_at")
    if not isinstance(fetched_at, datetime):
        return True

    age_sec = (_utc_now() - fetched_at).total_seconds()
    return age_sec >= ttl_sec


def _build_day_cache_entry(
    day: str,
    *,
    present: set[str],
    has_any: bool,
    frozen: bool,
) -> dict[str, Any]:
    return {
        "date": day,
        "present": set(present or set()),
        "has_any": bool(has_any),
        "fetched_at": _utc_now(),
        "frozen": bool(frozen),
        "pending_team_keys": set(),
    }


def _load_day_presence_with_cache(
    day: str,
    *,
    mutable_days: set[str],
    calendar_days: set[str] | None,
    manual_refresh: bool = False,
) -> dict[str, Any]:
    entry = _DDS_DAY_CACHE.get(day)
    if entry is None:
        entry = _load_storage_day_cache(day)

    ttl_sec = _day_refresh_seconds(day, mutable_days, manual_refresh=manual_refresh)
    calendar_known = calendar_days is not None
    day_in_calendar = calendar_known and day in calendar_days

    if calendar_known and not day_in_calendar:
        if entry is None or entry.get("has_any") or entry.get("present"):
            entry = _build_day_cache_entry(day, present=set(), has_any=False, frozen=True)
            _DDS_DAY_CACHE[day] = entry
            _save_storage_day_cache(day, entry)
        else:
            entry["frozen"] = True
            entry["pending_team_keys"] = set()
        return entry

    if not _should_refresh_day_entry(entry, ttl_sec):
        return entry

    carry_present = set(entry.get("present") or set()) if entry else set()
    present, has_any_dds = _load_dds_presence_for_day(day, carry_present)
    frozen = day not in mutable_days
    entry = _build_day_cache_entry(day, present=present, has_any=has_any_dds or bool(carry_present), frozen=frozen)
    _DDS_DAY_CACHE[day] = entry
    _save_storage_day_cache(day, entry)
    return entry


def _force_refresh_days(days: set[str]) -> None:
    for day in days:
        entry = _DDS_DAY_CACHE.get(day)
        if not entry:
            entry = _load_storage_day_cache(day) or {"date": day, "pending_team_keys": set()}
            _DDS_DAY_CACHE[day] = entry
        entry["fetched_at"] = None


def _build_manual_refresh_days(recent_days: list[str]) -> set[str]:
    mutable_days = _mutable_dds_days(recent_days)
    return {day for day in recent_days if day in mutable_days}


def _build_team_aliases(team_key: str, team_data: dict[str, Any], turno_data: dict[str, Any], equipe_label: str) -> set[str]:
    aliases = {
        _normalize_text(team_key),
        _normalize_text(team_data.get("displayName")),
        _normalize_text(turno_data.get("equipe")),
        _normalize_text(equipe_label),
    }
    return {a for a in aliases if a}


def _latest_dds_day_for_aliases(
    recent_dds_days: list[str],
    dds_present_by_day: dict[str, set[str]],
    aliases: set[str],
) -> str | None:
    for day in reversed(recent_dds_days):
        presentes_no_dia = dds_present_by_day.get(day) or set()
        if any(alias in presentes_no_dia for alias in aliases):
            return day
    return None


def _load_dds_presence_for_day(day: str, carry_present: set[str] | None = None) -> tuple[set[str], bool]:
    present = set(carry_present or set())
    has_any_dds = False
    end_key = f"{day}\uf8ff"

    query = (
        db.collection(DDS_COLLECTION)
        .where("headerDate", ">=", day)
        .where("headerDate", "<=", end_key)
    )

    for snap in query.stream():
        data = snap.to_dict() or {}
        snap_day = _extract_dds_day(data.get("headerDate"))
        if snap_day != day:
            continue

        has_any_dds = True
        equipe = _normalize_text(data.get("equipe"))
        if equipe:
            present.add(equipe)

    return present, has_any_dds


def _load_recent_dds_presence(
    days: int = DDS_HISTORY_DAYS,
    *,
    manual_refresh: bool = False,
) -> tuple[list[str], dict[str, set[str]], set[str], set[str], set[str] | None]:

    """
    Retorna:
      - recent_days: lista ascendente dos últimos N dias corridos (YYYY-MM-DD)
      - present_by_day[day]: conjunto normalizado das equipes com DDS no dia
      - days_with_any_dds: conjunto dos dias que tiveram pelo menos um DDS
      - mutable_days: dias que ainda podem ser atualizados (hoje e último dia útil)
      - calendar_days: conjunto de dias válidos vindos do calendário persistente, quando disponível
    """
    recent_days = _recent_history_days(days)
    mutable_days = _mutable_dds_days(recent_days)
    _prune_dds_day_cache(set(recent_days))

    if manual_refresh:
        _force_refresh_days(_build_manual_refresh_days(recent_days))

    calendar_days = _load_dds_calendar_days(force_refresh=False)
    present_by_day: dict[str, set[str]] = {day: set() for day in recent_days}
    days_with_any_dds: set[str] = set()

    for day in recent_days:
        entry = _load_day_presence_with_cache(
            day,
            mutable_days=mutable_days,
            calendar_days=calendar_days,
            manual_refresh=manual_refresh,
        )
        present_by_day[day] = set(entry.get("present") or set())
        if entry.get("has_any"):
            days_with_any_dds.add(day)

    return recent_days, present_by_day, days_with_any_dds, mutable_days, calendar_days


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


def _same_utc_dt(left: Any, right: Any) -> bool:
    left_dt = to_utc_dt(left)
    right_dt = to_utc_dt(right)
    return left_dt == right_dt


def _persist_auto_turno_state(
    empresa: str,
    team_key: str,
    *,
    current_estado: str,
    current_reason: Any,
    current_source_dt: Any,
    new_estado: str,
    reason: str,
    source_dt: Any,
) -> None:
    if (
        current_estado == new_estado
        and current_reason == reason
        and _same_utc_dt(current_source_dt, source_dt)
    ):
        return

    payload: dict[str, Any] = {
        "estado": new_estado,
        "autoStateReason": reason,
        "autoStateAt": firestore.SERVER_TIMESTAMP,
    }
    if source_dt is not None:
        payload["autoStateSourceUpdatedAt"] = source_dt
    _safe_merge(_turno_doc_ref(empresa, team_key), payload)


def _persist_reopen_after_activity(
    empresa: str,
    team_key: str,
    *,
    current_estado: str,
    current_reason: Any,
) -> None:
    if current_estado == "ABERTO" and not current_reason:
        return

    payload = {
        "estado": "ABERTO",
        "autoStateReason": firestore.DELETE_FIELD,
        "autoStateAt": firestore.DELETE_FIELD,
        "autoStateSourceUpdatedAt": firestore.DELETE_FIELD,
        "autoReopenedAt": firestore.SERVER_TIMESTAMP,
    }
    _safe_merge(_turno_doc_ref(empresa, team_key), payload)


def _persist_team_active_state(
    team_key: str,
    *,
    active: bool,
    reason: str | None = None,
    source_dt: Any = None,
    source_dds_day: str | None = None,
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
        if source_dt is not None:
            payload["autoInactiveLastSeenUpdatedAt"] = source_dt
        else:
            payload["autoInactiveLastSeenUpdatedAt"] = firestore.DELETE_FIELD
        if source_dds_day:
            payload["autoInactiveLastSeenDdsDay"] = source_dds_day
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


def _persist_team_inactive_checkpoint(
    team_key: str,
    *,
    source_dt: Any = None,
    source_dds_day: str | None = None,
) -> None:
    payload: dict[str, Any] = {}
    if source_dt is not None:
        payload["autoInactiveLastSeenUpdatedAt"] = source_dt
    if source_dds_day:
        payload["autoInactiveLastSeenDdsDay"] = source_dds_day
    _safe_merge(_team_doc_ref(team_key), payload)

def list_turnos(empresa: str, active: bool | None = True, *, manual_refresh: bool = False, setor: str = CURRENT_SETOR) -> dict[str, Any]:
    col_ref = db.collection("turno").document(empresa).collection("equipes")
    turno_docs = {doc.id: (doc.to_dict() or {}) for doc in col_ref.stream()}
    teams_map = list_teams_map(active=None)
    recent_dds_days, dds_present_by_day, dds_days_with_any, mutable_dds_days, calendar_days = _load_recent_dds_presence(manual_refresh=manual_refresh)
    
    unread_counts = get_unread_counts(setor=setor)

    rules = get_monitor_rules()
    alerta_amarelo_min = int(rules.get("alertaAmareloMin") or 15)
    alerta_vermelho_min = int(rules.get("alertaVermelhoMin") or 30)
    alerta_pisco_min = int(rules.get("alertaPiscoMin") or 60)
    auto_close_open_h = int(rules.get("autoCloseOpenHours") or AUTO_CLOSE_OPEN_HOURS_DEFAULT)
    auto_desat_fechado_h = int(
        rules.get("autoDesatualizaFechadoHours") or AUTO_DESATUALIZA_FECHADO_HOURS_DEFAULT
    )
    auto_desat_intervalo_h = int(
        rules.get("autoDesatualizaIntervaloHours") or AUTO_DESATUALIZA_INTERVALO_HOURS_DEFAULT
    )
    critico_desat_h = int(rules.get("desatualizadoCriticoHoras") or 16)

    now = datetime.now(timezone.utc)
    items = []
    pending_by_day: dict[str, set[str]] = {day: set() for day in mutable_dds_days}

    all_keys = set(turno_docs.keys()) | set(teams_map.keys())
    
    for team_key in all_keys:
        team_data = teams_map.get(team_key) or {}
        data = turno_docs.get(team_key) or {}
        team_active = bool(team_data.get("active", True)) if team_data else True
        has_turno_doc = bool(data)
        equipe = team_data.get("displayName") or data.get("equipe") or team_key
        estado_original = normalize_estado(data.get("estado") or "DESCONHECIDO")
        ss = data.get("nocSs")
        motivo = data.get("lastMotivoOutro") or data.get("lastMotivo")
        participantes = string_list(team_data.get("members")) or extract_participantes(data)
        aliases = _build_team_aliases(team_key, team_data, data, equipe)
        latest_dds_day = _latest_dds_day_for_aliases(recent_dds_days, dds_present_by_day, aliases)

        ts = data.get("serverUpdatedAt")
        dt = to_utc_dt(ts)

        minutos = None
        horas = None
        if dt:
            minutos = int((now - dt).total_seconds() // 60)
            horas = minutos // 60
        elif has_turno_doc:
            minutos = 10**9
            horas = 10**9

        last_seen_auto_inactive_dt = to_utc_dt(team_data.get("autoInactiveLastSeenUpdatedAt"))
        last_seen_auto_inactive_dds_day = str(team_data.get("autoInactiveLastSeenDdsDay") or "").strip() or None

        has_inactive_checkpoint = bool(last_seen_auto_inactive_dt or last_seen_auto_inactive_dds_day)
        fallback_dds_day = None
        if last_seen_auto_inactive_dt:
            fallback_dds_day = last_seen_auto_inactive_dt.strftime("%Y-%m-%d")
        effective_inactive_dds_day = last_seen_auto_inactive_dds_day or fallback_dds_day

        new_turno_communication = bool(
            dt and last_seen_auto_inactive_dt and dt > last_seen_auto_inactive_dt
        )
        new_dds_communication = bool(
            latest_dds_day
            and effective_inactive_dds_day
            and latest_dds_day > effective_inactive_dds_day
        )

        if not team_active:
            if not has_inactive_checkpoint and (dt or latest_dds_day):
                new_turno_communication = bool(dt)
                new_dds_communication = bool(latest_dds_day)

            if new_turno_communication or new_dds_communication:
                _persist_team_active_state(
                    team_key,
                    active=True,
                    source_dt=dt,
                    source_dds_day=latest_dds_day,
                )
                team_active = True
            elif not has_inactive_checkpoint:
                _persist_team_inactive_checkpoint(
                    team_key,
                    source_dt=dt,
                    source_dds_day=latest_dds_day,
                )

        if estado_original == "DESCONHECIDO":
            if team_active:
                recent_turno = dt and (now - dt).total_seconds() < 48 * 3600
                recent_dds = False
                if latest_dds_day:
                    try:
                        dds_date = datetime.strptime(latest_dds_day, "%Y-%m-%d").date()
                        if (_local_today() - dds_date).days <= 2:
                            recent_dds = True
                    except Exception:
                        pass
                
                # Se não temos sinal recente, inativamos os DESCONHECIDO
                if not recent_turno and not recent_dds:
                    _persist_team_active_state(
                        team_key,
                        active=False,
                        reason=AUTO_REASON_INACTIVE_UNKNOWN,
                        source_dt=dt,
                        source_dds_day=latest_dds_day,
                    )
                    team_active = False

        if active is not None and team_active is not active:
            continue

        estado = estado_original
        auto_state_reason = data.get("autoStateReason")
        auto_state_source_dt = to_utc_dt(data.get("autoStateSourceUpdatedAt"))

        if (
            estado_original == "FECHADO"
            and auto_state_reason == AUTO_REASON_CLOSE_OPEN
            and dt
            and auto_state_source_dt
            and dt > auto_state_source_dt
        ):
            estado = "ABERTO"
            _persist_reopen_after_activity(
                empresa,
                team_key,
                current_estado=estado_original,
                current_reason=auto_state_reason,
            )
        elif estado_original == "ABERTO" and dt and horas is not None and horas >= auto_close_open_h:
            estado = "FECHADO"
            _persist_auto_turno_state(
                empresa,
                team_key,
                current_estado=estado_original,
                current_reason=auto_state_reason,
                current_source_dt=auto_state_source_dt,
                new_estado="FECHADO",
                reason=AUTO_REASON_CLOSE_OPEN,
                source_dt=dt,
            )
        elif estado_original == "FECHADO" and dt and horas is not None and horas >= auto_desat_fechado_h:
            estado = "DESATUALIZADO"
            _persist_auto_turno_state(
                empresa,
                team_key,
                current_estado=estado_original,
                current_reason=auto_state_reason,
                current_source_dt=auto_state_source_dt,
                new_estado="DESATUALIZADO",
                reason=AUTO_REASON_DESAT_FECHADO,
                source_dt=dt,
            )
        elif (
            estado_original == "DESLOCAMENTO_ESPECIAL"
            and dt
            and horas is not None
            and horas >= auto_desat_fechado_h
        ):
            estado = "DESATUALIZADO"
            _persist_auto_turno_state(
                empresa,
                team_key,
                current_estado=estado_original,
                current_reason=auto_state_reason,
                current_source_dt=auto_state_source_dt,
                new_estado="DESATUALIZADO",
                reason=AUTO_REASON_DESAT_DESLOCAMENTO,
                source_dt=dt,
            )
        elif estado_original == "INTERVALO" and dt and horas is not None and horas >= auto_desat_intervalo_h:
            estado = "DESATUALIZADO"
            _persist_auto_turno_state(
                empresa,
                team_key,
                current_estado=estado_original,
                current_reason=auto_state_reason,
                current_source_dt=auto_state_source_dt,
                new_estado="DESATUALIZADO",
                reason=AUTO_REASON_DESAT_INTERVALO,
                source_dt=dt,
            )

        critico = bool(estado == "DESATUALIZADO" and horas is not None and horas >= critico_desat_h)

        alerta = None
        if minutos is not None:
            if minutos >= alerta_pisco_min:
                alerta = "PULSE"
            elif minutos >= alerta_vermelho_min:
                alerta = "RED"
            elif minutos >= alerta_amarelo_min:
                alerta = "YELLOW"

        dds_history: list[str] = []
        for day in recent_dds_days:
            day_known_by_calendar = calendar_days is None or day in calendar_days
            if not day_known_by_calendar:
                dds_history.append("neutral")
                continue

            if day not in dds_days_with_any:
                dds_history.append("neutral")
                if day in pending_by_day:
                    pending_by_day[day].add(team_key)
                continue

            presentes_no_dia = dds_present_by_day.get(day) or set()
            encontrou_dds = any(alias in presentes_no_dia for alias in aliases)
            dds_history.append("ok" if encontrou_dds else "fail")
            if day in pending_by_day and not encontrou_dds:
                pending_by_day[day].add(team_key)

        dds_today = dds_history[-1] if dds_history else "neutral"
        items.append(
            {
                "teamKey": team_key,
                "equipe": equipe,
                "estado": estado,
                "estadoOriginal": estado_original,
                "ss": ss or "-",
                "motivo": motivo or "-",
                "updatedAt": dt.isoformat() if dt else None,
                "minutosDesdeAtualizacao": minutos,
                "critico": critico,
                "alerta": alerta,
                "participantes": participantes,
                "active": team_active,
                "ddsHistory": dds_history,
                "ddsToday": dds_today,
                "ddsDays": recent_dds_days,
                "unreadMessages": unread_counts.get(equipe, 0) or unread_counts.get(team_key, 0),
            }
        )
    for day in recent_dds_days:
        entry = _DDS_DAY_CACHE.get(day)
        if not entry:
            continue

        if day not in mutable_dds_days:
            entry["frozen"] = True
            entry["pending_team_keys"] = set()
            continue

        pending = pending_by_day.get(day, set())
        entry["pending_team_keys"] = pending
        if not pending:
            entry["frozen"] = True

    items.sort(key=lambda x: (str(x.get("equipe") or ""), str(x.get("teamKey") or "")))
    return {
        "empresa": empresa,
        "serverTime": now.isoformat(),
        "activeFilter": active,
        "manualRefresh": manual_refresh,
        "currentSector": setor,
        "items": items,
    }


def delete_team_runtime_and_history(team_key: str) -> None:
    """
    Remove o estado em tempo real (turno) e todos os registros de DDS vinculados
    à equipe de forma permanente.
    """
    # 1. Remove das subcoleções de equipes de cada empresa na coleção 'turno'
    for empresa_snap in db.collection("turno").stream():
        doc_ref = empresa_snap.reference.collection("equipes").document(team_key)
        doc_ref.delete()

    # 2. Remove registros da coleção DDS (histórico de reuniões)
    # Busca pelo team_key literal e pela versão normalizada
    keys_to_clean = {team_key, _normalize_text(team_key)}
    for key in keys_to_clean:
        if not key:
            continue
        query = db.collection(DDS_COLLECTION).where("equipe", "==", key)
        # Firestore delete limit is 500, but we assume it's not THAT many records 
        # for a single team in one go. For safety, we stream and delete.
        for snap in query.stream():
            snap.reference.delete()
