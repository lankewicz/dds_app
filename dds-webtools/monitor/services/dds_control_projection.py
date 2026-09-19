"""Leitura das projeções compactas de presença de DDS no Firebase Storage."""

from __future__ import annotations

import gzip
import json
import os
from typing import Any

from google.cloud import storage


DDS_BUCKET_NAME = os.getenv("DDS_BUCKET_NAME", "dds-treinamentos.firebasestorage.app")
DDS_CONTROL_PREFIX = os.getenv(
    "DDS_CONTROL_PREFIX", "dados/chicoeletro/dds/controle"
).strip("/")

_CLIENT: storage.Client | None = None


def _client() -> storage.Client:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = storage.Client()
    return _CLIENT


def daily_blob_name(day: str) -> str:
    return f"{DDS_CONTROL_PREFIX}/daily/{day}.json.gz"


def load_daily_projection(day: str) -> dict[str, Any] | None:
    """Baixa e valida a Torre de Controle diária. Ausência não consulta Firestore."""
    try:
        raw = _client().bucket(DDS_BUCKET_NAME).blob(daily_blob_name(day)).download_as_bytes()
        if raw.startswith(b"\x1f\x8b"):
            raw = gzip.decompress(raw)
        payload = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(payload, dict) or payload.get("date") != day:
            return None
        return payload
    except Exception:
        return None


import re
import threading
import time
from monitor.services.turnos_common import _normalized_alias_matches

_PROJECTIONS_LOCK = threading.Lock()
_PROJECTIONS_CACHE: dict[str, dict[str, Any]] = {}
_LAST_SYNC_TIME: float = 0.0
_SYNC_TTL_SECONDS: float = 60.0


def sync_recent_daily_projections(
    limit_days: int = 25,
    manual_refresh: bool = False,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """
    Sincroniza os últimos `limit_days` (default 25 dias úteis) do Storage verificando MD5/ETag.
    Se o hash do arquivo no Storage for idêntico ao que já está em memória, não faz download.
    """
    global _LAST_SYNC_TIME
    now_ts = time.time()
    with _PROJECTIONS_LOCK:
        if not manual_refresh and _PROJECTIONS_CACHE and (now_ts - _LAST_SYNC_TIME) < _SYNC_TTL_SECONDS:
            sorted_days = sorted(_PROJECTIONS_CACHE.keys())
            recent = sorted_days[-limit_days:]
            return recent, {d: _PROJECTIONS_CACHE[d] for d in recent}

        try:
            prefix = f"{DDS_CONTROL_PREFIX}/daily/"
            blobs = list(_client().bucket(DDS_BUCKET_NAME).list_blobs(prefix=prefix))
        except Exception:
            sorted_days = sorted(_PROJECTIONS_CACHE.keys())
            recent = sorted_days[-limit_days:]
            return recent, {d: _PROJECTIONS_CACHE[d] for d in recent}

        daily_blobs: list[tuple[str, Any]] = []
        for b in blobs:
            name = getattr(b, "name", "") or ""
            if not name.endswith(".json.gz"):
                continue
            match = re.search(r"(\d{4}-\d{2}-\d{2})\.json\.gz$", name)
            if match:
                daily_blobs.append((match.group(1), b))

        daily_blobs.sort(key=lambda x: x[0])
        recent_blobs = daily_blobs[-limit_days:] if len(daily_blobs) > limit_days else daily_blobs

        for day_iso, b in recent_blobs:
            remote_hash = getattr(b, "md5_hash", None) or getattr(b, "etag", None) or getattr(b, "updated", None)
            cached = _PROJECTIONS_CACHE.get(day_iso)
            if cached and remote_hash and cached.get("hash") == remote_hash:
                continue

            try:
                raw = b.download_as_bytes()
                if raw.startswith(b"\x1f\x8b"):
                    raw = gzip.decompress(raw)
                payload = json.loads(raw.decode("utf-8-sig"))
                if isinstance(payload, dict) and payload.get("date") == day_iso:
                    raw_teams = payload.get("teams") or {}
                    teams_map = {
                        str(k).strip().upper(): v
                        for k, v in raw_teams.items()
                        if isinstance(v, dict)
                    }
                    _PROJECTIONS_CACHE[day_iso] = {
                        "hash": remote_hash,
                        "date": day_iso,
                        "teams": teams_map,
                    }
            except Exception:
                pass

        _LAST_SYNC_TIME = now_ts
        sorted_days = sorted(_PROJECTIONS_CACHE.keys())
        recent_days = sorted_days[-limit_days:]
        return recent_days, {d: _PROJECTIONS_CACHE[d] for d in recent_days}


def _extract_completed_time(completed_at: str | None) -> str | None:
    if not completed_at:
        return None
    try:
        text = str(completed_at).strip()
        if "T" in text:
            return text.split("T")[1][:5]
        parts = text.split()
        if len(parts) > 1 and ":" in parts[1]:
            return parts[1][:5]
        return None
    except Exception:
        return None


def get_team_dds_presence(
    team_key: str,
    available_days: list[str],
    projections_by_day: dict[str, dict[str, Any]],
    today_iso: str,
) -> dict[str, Any]:
    """
    Retorna o dicionário com ddsDays, ddsHistory, ddsTimes, ddsPhotos e ddsToday para a equipe.
    """
    safe_key = str(team_key or "").strip().upper()
    history: list[str] = []
    times: dict[str, str] = {}
    has_today = False

    for day in available_days:
        day_entry = projections_by_day.get(day, {})
        teams_map = day_entry.get("teams", {})
        matched_entry = teams_map.get(safe_key)
        if not matched_entry:
            for t_code, entry_val in teams_map.items():
                if _normalized_alias_matches(t_code, safe_key):
                    matched_entry = entry_val
                    break

        if matched_entry and isinstance(matched_entry, dict):
            history.append("ok")
            c_time = _extract_completed_time(matched_entry.get("completedAt"))
            if c_time:
                times[day] = c_time
            if day == today_iso:
                has_today = True
        else:
            history.append("fail")

    return {
        "ddsDays": available_days,
        "ddsHistory": history,
        "ddsTimes": times,
        "ddsPhotos": {},
        "ddsToday": "ok" if has_today else "neutral",
    }


