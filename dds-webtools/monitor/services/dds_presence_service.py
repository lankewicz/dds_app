# -----------------------------------------------------------------------------
# Arquivo : monitor/services/dds_presence_service.py
# Objetivo: Gestão de presença, calendário e cache de DDS (Storage e Firestore).
# -----------------------------------------------------------------------------

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from google.cloud.firestore_v1.base_query import FieldFilter
from services.firestore_client import db
from services.monitor_config_service import get_monitor_polling_seconds

from monitor.services.turnos_common import (
    DDS_BUCKET_NAME,
    DDS_CALENDAR_CACHE_BLOB,
    DDS_CALENDAR_SOURCE_BLOB,
    DDS_COLLECTION,
    DDS_DAY_CACHE_PREFIX,
    DDS_HISTORY_DAYS,
    DDS_LAST_BUSINESS_REFRESH_SEC,
    DDS_MUTABLE_REFRESH_SEC,
    DDS_PRESENCE_MODE,
    DDS_TIMEZONE,
    _get_now,
    _local_today,
    _normalize_text,
    _normalized_alias_matches,
    _parse_iso_datetime,
    _storage_blob_name,
    _storage_bucket,
    _storage_read_json,
    _storage_write_json,
    _utc_now,
    _utc_now_iso,
    to_utc_dt,
)

logger = logging.getLogger(__name__)

_DDS_DAY_CACHE: dict[str, dict[str, Any]] = {}
_DDS_CALENDAR_CACHE: dict[str, Any] = {}
_RECENT_7D_DDS_CACHE: dict[str, Any] = {"fetched_at": 0.0, "teams": {}}
_cache_lock = threading.Lock()


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
    with _cache_lock:
        stale_days = [day for day in _DDS_DAY_CACHE.keys() if day not in valid_days]
        for day in stale_days:
            _DDS_DAY_CACHE.pop(day, None)


def _should_refresh_dds_day(day: str, mutable_days: set[str]) -> bool:
    with _cache_lock:
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

    age_sec = (_get_now() - fetched_at).total_seconds()
    return age_sec >= DDS_MUTABLE_REFRESH_SEC


def _extract_dds_day(header_date: Any) -> str | None:
    raw = str(header_date or "").strip()
    if not raw:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", raw)
    return m.group(1) if m else None


def _parse_dds_time_value(value: Any) -> tuple[int, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"\b(\d{1,2})[:hH](\d{2})\b", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour, minute
    return None


def _combine_dds_day_time(day: str | None, time_value: Any) -> datetime | None:
    if not day:
        return None
    parsed = _parse_dds_time_value(time_value)
    if not parsed:
        return None
    hour, minute = parsed
    try:
        local_tz = ZoneInfo(DDS_TIMEZONE)
    except Exception:
        local_tz = timezone(timedelta(hours=-3))
    try:
        local_dt = datetime.strptime(day, "%Y-%m-%d").replace(
            hour=hour, minute=minute, second=0, microsecond=0, tzinfo=local_tz
        )
        return local_dt.astimezone(timezone.utc)
    except Exception:
        return None


def _dds_day_to_effective_contact_dt(day: str | None) -> datetime | None:
    """Fallback quando existe DDS, mas o documento não traz timestamp aproveitável."""
    if not day:
        return None
    today_key = _local_today().strftime("%Y-%m-%d")
    if day == today_key:
        return _get_now().astimezone(timezone.utc)
    try:
        local_tz = ZoneInfo(DDS_TIMEZONE)
    except Exception:
        local_tz = timezone(timedelta(hours=-3))
    try:
        local_dt = datetime.strptime(day, "%Y-%m-%d").replace(
            hour=12, minute=0, second=0, microsecond=0, tzinfo=local_tz
        )
        return local_dt.astimezone(timezone.utc)
    except Exception:
        return None


def _extract_dds_timestamp(data: dict[str, Any], day: str | None = None) -> datetime | None:
    """Extrai a melhor data/hora disponível do documento DDS."""
    for key in (
        "executedAt",
        "submittedAt",
        "sentAt",
        "serverUpdatedAt",
        "updatedAt",
        "createdAt",
        "timestamp",
        "dataHora",
        "horaConclusao",
        "_doc_create_time",
        "_doc_update_time",
    ):
        dt = to_utc_dt(data.get(key)) or _parse_iso_datetime(data.get(key))
        if dt:
            return dt

    combined = _combine_dds_day_time(day or _extract_dds_day(data.get("headerDate")), data.get("hora"))
    if combined:
        return combined

    return None


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
        "team_timestamps": {k: (v.isoformat() if hasattr(v, "isoformat") else str(v)) for k, v in (entry.get("team_timestamps") or {}).items()},
        "team_photos": {k: str(v) for k, v in (entry.get("team_photos") or {}).items() if v},
    }


def _deserialize_day_cache(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    day = _extract_dds_day(payload.get("date"))
    if not day:
        return None
    control_teams = payload.get("teams") if isinstance(payload.get("teams"), dict) else {}
    teams_executed = {
        str(team).strip()
        for team in ((payload.get("teams_executed") or []) if not control_teams else control_teams.keys())
        if str(team).strip()
    }
    team_timestamps = {k: _parse_iso_datetime(v) for k, v in (payload.get("team_timestamps") or {}).items()}
    if control_teams:
        team_timestamps.update({
            str(team).strip(): _parse_iso_datetime(details.get("completedAt"))
            for team, details in control_teams.items()
            if str(team).strip() and isinstance(details, dict) and details.get("completedAt")
        })
    team_photos = {k: str(v) for k, v in (payload.get("team_photos") or {}).items() if v}
    return {
        "date": day,
        "present": teams_executed,
        "team_timestamps": team_timestamps,
        "team_photos": team_photos,
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
    with _cache_lock:
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
    team_timestamps: dict[str, Any],
    has_any: bool,
    frozen: bool,
    team_photos: dict[str, Any] = None,
) -> dict[str, Any]:
    return {
        "date": day,
        "present": set(present or set()),
        "team_timestamps": dict(team_timestamps or {}),
        "team_photos": dict(team_photos or {}),
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
    with _cache_lock:
        entry = _DDS_DAY_CACHE.get(day)
    if entry is None:
        entry = _load_storage_day_cache(day)

    ttl_sec = _day_refresh_seconds(day, mutable_days, manual_refresh=manual_refresh)
    calendar_known = calendar_days is not None
    day_in_calendar = calendar_known and day in calendar_days

    # Fallback para fins de semana caso o calendário não esteja disponível
    is_weekend = False
    try:
        is_weekend = datetime.strptime(day, "%Y-%m-%d").weekday() in (5, 6)
    except Exception:
        pass

    is_non_business = (calendar_known and not day_in_calendar) or (not calendar_known and is_weekend)

    if is_non_business:
        if entry is None or entry.get("has_any") or entry.get("present"):
            entry = _build_day_cache_entry(day, present=set(), team_timestamps={}, team_photos={}, has_any=False, frozen=True)
            with _cache_lock:
                _DDS_DAY_CACHE[day] = entry
            _save_storage_day_cache(day, entry)
        else:
            entry["frozen"] = True
            entry["pending_team_keys"] = set()
        return entry

    if not _should_refresh_day_entry(entry, ttl_sec):
        return entry

    carry_present = set(entry.get("present") or set()) if entry else set()
    carry_photos = dict(entry.get("team_photos") or {}) if entry else {}
    present, has_any_dds, team_timestamps, team_photos = _load_dds_presence_for_day(day, carry_present, carry_photos)
    frozen = day not in mutable_days
    entry = _build_day_cache_entry(day, present=present, team_timestamps=team_timestamps, team_photos=team_photos, has_any=has_any_dds or bool(carry_present), frozen=frozen)
    with _cache_lock:
        _DDS_DAY_CACHE[day] = entry
    _save_storage_day_cache(day, entry)
    return entry


def _force_refresh_days(days: set[str]) -> None:
    for day in days:
        with _cache_lock:
            entry = _DDS_DAY_CACHE.get(day)
        if not entry:
            entry = _load_storage_day_cache(day) or {"date": day, "pending_team_keys": set()}
            with _cache_lock:
                _DDS_DAY_CACHE[day] = entry
        entry["fetched_at"] = None


def _build_manual_refresh_days(recent_days: list[str]) -> set[str]:
    mutable_days = _mutable_dds_days(recent_days)
    return {day for day in recent_days if day in mutable_days}


def _latest_dds_ts_for_aliases(
    recent_dds_days: list[str],
    dds_timestamps_by_day: dict[str, dict[str, Any]],
    aliases: set[str],
) -> datetime | None:
    latest_ts = None
    for day in reversed(recent_dds_days):
        day_ts_map = dds_timestamps_by_day.get(day) or {}
        for alias in aliases:
            ts = to_utc_dt(day_ts_map.get(alias))
            if not ts:
                for present_name, raw_ts in day_ts_map.items():
                    if _normalized_alias_matches(present_name, alias):
                        ts = to_utc_dt(raw_ts)
                        if ts:
                            break
            if ts:
                if not latest_ts or ts > latest_ts:
                    latest_ts = ts
    return latest_ts


def _load_dds_presence_for_day(
    day: str,
    carry_present: set[str] | None = None,
    carry_photos: dict[str, Any] | None = None,
) -> tuple[set[str], bool, dict[str, Any], dict[str, Any]]:
    present = set(carry_present or set())
    team_timestamps: dict[str, Any] = {}
    team_photos: dict[str, Any] = dict(carry_photos or {})
    has_any_dds = False
    end_key = f"{day}\uf8ff"

    query = (
        db.collection(DDS_COLLECTION)
        .where(filter=FieldFilter("headerDate", ">=", day))
        .where(filter=FieldFilter("headerDate", "<=", end_key))
    )

    for snap in query.stream():
        data = snap.to_dict() or {}
        if getattr(snap, "create_time", None):
            data["_doc_create_time"] = snap.create_time
        if getattr(snap, "update_time", None):
            data["_doc_update_time"] = snap.update_time
        snap_day = _extract_dds_day(data.get("headerDate"))
        if snap_day != day:
            continue

        has_any_dds = True
        equipe = _normalize_text(data.get("equipe") or data.get("teamName") or data.get("teamKey"))
        ts = _extract_dds_timestamp(data, snap_day)
        photo_url = data.get("fotoUrl") or data.get("thumbUrl") or data.get("photoUrl")
        if equipe:
            present.add(equipe)
            if ts:
                current_ts = to_utc_dt(team_timestamps.get(equipe))
                if not current_ts or ts > current_ts:
                    team_timestamps[equipe] = ts
            if photo_url:
                team_photos[equipe] = photo_url

    return present, has_any_dds, team_timestamps, team_photos


def _load_recent_dds_presence(
    days: int = DDS_HISTORY_DAYS,
    *,
    manual_refresh: bool = False,
) -> tuple[list[str], dict[str, set[str]], set[str], set[str], set[str] | None, dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    recent_days = _recent_history_days(days)
    mutable_days = _mutable_dds_days(recent_days)
    _prune_dds_day_cache(set(recent_days))

    if manual_refresh:
        _force_refresh_days(_build_manual_refresh_days(recent_days))

    calendar_days = _load_dds_calendar_days(force_refresh=False)
    present_by_day: dict[str, set[str]] = {day: set() for day in recent_days}
    dds_timestamps_by_day: dict[str, dict[str, Any]] = {day: {} for day in recent_days}
    dds_photos_by_day: dict[str, dict[str, Any]] = {day: {} for day in recent_days}
    days_with_any_dds: set[str] = set()

    from concurrent.futures import ThreadPoolExecutor

    def load_day(day):
        return day, _load_day_presence_with_cache(
            day,
            mutable_days=mutable_days,
            calendar_days=calendar_days,
            manual_refresh=manual_refresh,
        )

    with ThreadPoolExecutor(max_workers=min(len(recent_days), 20)) as executor:
        results = list(executor.map(load_day, recent_days))

    for day, entry in results:
        present_by_day[day] = set(entry.get("present") or set())
        dds_timestamps_by_day[day] = dict(entry.get("team_timestamps") or {})
        dds_photos_by_day[day] = dict(entry.get("team_photos") or {})
        if entry.get("has_any"):
            days_with_any_dds.add(day)

    return recent_days, present_by_day, days_with_any_dds, mutable_days, calendar_days, dds_timestamps_by_day, dds_photos_by_day


def _load_day_dds_teams(day_iso: str, manual_refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Retorna mapa {teamKey: {"completedAt": iso_str}} do JSON de controle de DDS para o dia especificado."""
    if DDS_PRESENCE_MODE == "json":
        try:
            from monitor.services.dds_control_projection import load_daily_projection
            payload = load_daily_projection(day_iso)
            if payload and isinstance(payload.get("teams"), dict):
                return {str(k).strip().upper(): v for k, v in payload["teams"].items() if isinstance(v, dict)}
        except Exception as exc:
            logger.warning("Não foi possível carregar projeção diária DDS para %s: %s", day_iso, exc)

    try:
        entry = _load_day_presence_with_cache(
            day_iso,
            mutable_days={day_iso},
            calendar_days=None,
            manual_refresh=manual_refresh,
        )
        if entry:
            present = entry.get("present") or set()
            timestamps = entry.get("team_timestamps") or {}
            res: dict[str, dict[str, Any]] = {}
            for t in present:
                safe_t = str(t).strip().upper()
                ts = timestamps.get(t) or timestamps.get(safe_t)
                ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts) if ts else None
                res[safe_t] = {"completedAt": ts_iso}
            return res
    except Exception as exc:
        logger.warning("Não foi possível carregar cache de dias para DDS de %s: %s", day_iso, exc)

    return {}


def _load_today_dds_teams(today_iso: str, manual_refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Retorna mapa {teamKey: {"completedAt": iso_str}} do JSON de controle de DDS de hoje."""
    return _load_day_dds_teams(today_iso, manual_refresh=manual_refresh)


def _load_recent_7d_dds_teams(now_local: datetime, manual_refresh: bool = False) -> dict[str, dict[str, Any]]:
    """
    Retorna mapa {safe_team_key: {"completedAt": iso_str, "date": day_iso}}
    das equipes que concluíram DDS em qualquer um dos últimos 7 dias.
    """
    import time
    now_ts = time.time()
    if not manual_refresh and (now_ts - _RECENT_7D_DDS_CACHE.get("fetched_at", 0.0)) < 60.0:
        return _RECENT_7D_DDS_CACHE.get("teams", {})

    recent_days = [(now_local.date() - timedelta(days=i)).isoformat() for i in range(7)]
    recent_map: dict[str, dict[str, Any]] = {}

    for day in recent_days:
        day_teams = _load_day_dds_teams(day, manual_refresh=manual_refresh)
        for t_key, info in day_teams.items():
            safe_k = str(t_key).strip().upper()
            completed = info.get("completedAt") or f"{day}T07:00:00-03:00"
            if safe_k not in recent_map:
                recent_map[safe_k] = {
                    "completedAt": completed,
                    "date": day,
                }
            else:
                prev_completed = recent_map[safe_k].get("completedAt") or ""
                if completed > prev_completed:
                    recent_map[safe_k] = {
                        "completedAt": completed,
                        "date": day,
                    }

    _RECENT_7D_DDS_CACHE["fetched_at"] = now_ts
    _RECENT_7D_DDS_CACHE["teams"] = recent_map
    return recent_map


def _has_dds_in_recent_map(safe_key: str, recent_dds_teams: dict[str, dict[str, Any]]) -> tuple[bool, dict[str, Any] | None]:
    if not recent_dds_teams:
        return False, None
    if safe_key in recent_dds_teams:
        return True, recent_dds_teams[safe_key]
    for t_code, entry_val in recent_dds_teams.items():
        if _normalized_alias_matches(t_code, safe_key):
            return True, entry_val
    return False, None


def invalidate_dds_day_cache(day: str):
    with _cache_lock:
        _DDS_DAY_CACHE.pop(day, None)
    try:
        blob_name = _day_cache_blob(day)
        _storage_bucket().blob(blob_name).delete()
    except Exception:
        pass


def get_team_dds_data(empresa: str, team_key: str) -> dict[str, Any]:
    """
    Retorna ddsHistory, ddsDays, ddsTimes e ddsPhotos para uma equipe específica.
    """
    from monitor.services.torre_monitor_builder import _read_monitor_view_cache
    cache = _read_monitor_view_cache(empresa)
    if cache:
        items = cache.get("items") or []
        for it in items:
            if it.get("teamKey") == team_key:
                return {
                    "ddsHistory": it.get("ddsHistory") or [],
                    "ddsDays": it.get("ddsDays") or [],
                    "ddsTimes": it.get("ddsTimes") or {},
                    "ddsPhotos": it.get("ddsPhotos") or {},
                    "ddsToday": it.get("ddsToday") or "neutral",
                }
    return {"ddsHistory": [], "ddsDays": [], "ddsTimes": {}, "ddsPhotos": {}, "ddsToday": "neutral"}
