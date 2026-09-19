# -----------------------------------------------------------------------------
# Arquivo : monitor/services/turnos_common.py
# Objetivo: Utilitários compartilhados, constantes, helpers de data/hora,
#           serialização e acesso ao Cloud Storage.
# -----------------------------------------------------------------------------

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from google.cloud import storage

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
DDS_PRESENCE_MODE = os.getenv("DDS_PRESENCE_MODE", "json").strip().lower()
DDS_JSON_REFRESH_SEC = int(os.getenv("DDS_JSON_REFRESH_SEC", "60"))
MONITOR_VIEW_CACHE_PREFIX = os.getenv("MONITOR_VIEW_CACHE_PREFIX", "_cache/monitor")
MONITOR_VIEW_CACHE_TTL_SEC = int(os.getenv("MONITOR_VIEW_CACHE_TTL_SEC", "86400"))
WEBTOOLS_ROOT_COLLECTION = os.getenv("WEBTOOLS_ROOT_COLLECTION", "webtools")
WEBTOOLS_MONITOR_DOC = os.getenv("WEBTOOLS_MONITOR_DOC", "monitor")
AUTO_CLOSE_OPEN_HOURS_DEFAULT = int(os.getenv("DDS_AUTO_CLOSE_OPEN_HOURS", "16"))
AUTO_DESATUALIZA_FECHADO_HOURS_DEFAULT = int(os.getenv("DDS_AUTO_DESATUALIZA_FECHADO_HOURS", "48"))
AUTO_DESATUALIZA_INTERVALO_HOURS_DEFAULT = int(os.getenv("DDS_AUTO_DESATUALIZA_INTERVALO_HOURS", "8"))

AUTO_REASON_CLOSE_OPEN = "AUTO_CLOSE_OPEN_TIMEOUT"
AUTO_REASON_DESAT_FECHADO = "AUTO_DESATUALIZADO_FECHADO_TIMEOUT"
AUTO_REASON_DESAT_DESLOCAMENTO = "AUTO_DESATUALIZADO_DESLOCAMENTO_TIMEOUT"
AUTO_REASON_DESAT_INTERVALO = "AUTO_DESATUALIZADO_INTERVALO_TIMEOUT"
AUTO_REASON_INACTIVE_UNKNOWN = "AUTO_INACTIVE_DESCONHECIDO"

_STORAGE_CLIENT = None


def to_utc_dt(ts: Any):
    if not ts:
        return None

    if hasattr(ts, "to_datetime"):
        dt = ts.to_datetime()
    elif isinstance(ts, datetime):
        dt = ts
    elif isinstance(ts, str):
        text = ts.strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            parsed_dt = None
            for fmt in (
                "%d-%m-%Y - %H:%M",
                "%d-%m-%Y %H:%M:%S",
                "%d-%m-%Y %H:%M",
                "%d/%m/%Y - %H:%M",
                "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
            ):
                try:
                    parsed_dt = datetime.strptime(text, fmt)
                    break
                except Exception:
                    continue
            if parsed_dt is not None:
                dt = parsed_dt
            else:
                return None
    else:
        return None

    if getattr(dt, "tzinfo", None) is None:
        try:
            tz = ZoneInfo(DDS_TIMEZONE)
        except Exception:
            tz = timezone(timedelta(hours=-3))
        dt = dt.replace(tzinfo=tz).astimezone(timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt


def _get_now() -> datetime:
    try:
        return datetime.now(ZoneInfo(DDS_TIMEZONE))
    except Exception:
        return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3)))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _parse_iso_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return to_utc_dt(value)
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _local_today() -> datetime.date:
    return _get_now().date()


def _local_day_key(dt: datetime | None) -> str | None:
    if not dt:
        return None
    try:
        local_dt = dt.astimezone(ZoneInfo(DDS_TIMEZONE)) if DDS_TIMEZONE else dt
        return local_dt.strftime("%Y-%m-%d")
    except Exception:
        return dt.strftime("%Y-%m-%d")


def _same_utc_dt(left: Any, right: Any) -> bool:
    left_dt = to_utc_dt(left)
    right_dt = to_utc_dt(right)
    return left_dt == right_dt


def normalize_estado(value: str | None) -> str:
    raw = (value or "DESCONHECIDO").strip().upper()
    aliases = {
        "ESPECIAL": "DESLOCAMENTO_ESPECIAL",
        "DESLOCAMENTO": "DESLOCAMENTO_ESPECIAL",
    }
    return aliases.get(raw, raw)


def normalize_rotalog_turn_state(value: str | None) -> str:
    """ROTALOG DESLOCAMENTO é etapa do serviço, nunca deslocamento especial."""
    raw = (value or "DESCONHECIDO").strip().upper()
    if raw == "DESLOCAMENTO":
        return "ABERTO"
    return normalize_estado(raw)


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


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalized_alias_matches(value: str | None, alias: str | None) -> bool:
    """Compara equipe por chave exata ou por token."""
    norm_value = _normalize_text(value)
    norm_alias = _normalize_text(alias)
    if not norm_value or not norm_alias:
        return False
    if norm_value == norm_alias:
        return True

    token_re = rf"(?<![A-Z0-9]){re.escape(norm_alias)}(?![A-Z0-9])"
    if re.search(token_re, norm_value):
        return True

    return False


def _build_team_aliases(team_key: str, team_data: dict[str, Any], turno_data: dict[str, Any], equipe_label: str) -> set[str]:
    aliases = {
        _normalize_text(team_key),
        _normalize_text(team_data.get("teamKey")),
        _normalize_text(team_data.get("displayName")),
        _normalize_text(turno_data.get("equipe")),
        _normalize_text(equipe_label),
    }
    return {a for a in aliases if a}


class _DatetimeEncoder(json.JSONEncoder):
    """Serializa datetime/set que o json padrão não suporta."""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, set):
            return sorted(obj)
        return super().default(obj)


def _storage_client() -> storage.Client:
    global _STORAGE_CLIENT
    if _STORAGE_CLIENT is None:
        _STORAGE_CLIENT = storage.Client()
        try:
            from requests.adapters import HTTPAdapter
            adapter = HTTPAdapter(pool_connections=200, pool_maxsize=200)
            _STORAGE_CLIENT._http.mount("https://", adapter)
            _STORAGE_CLIENT._http._auth_request.session.mount("https://", adapter)
        except Exception:
            pass
    return _STORAGE_CLIENT


def _storage_bucket():
    return _storage_client().bucket(DDS_BUCKET_NAME)


def _storage_blob_name(*parts: str) -> str:
    clean = [str(part or "").strip("/") for part in parts if str(part or "").strip("/")]
    return "/".join(clean)


def _storage_read_json(blob_name: str) -> dict[str, Any] | None:
    try:
        blob = _storage_bucket().blob(blob_name)
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
