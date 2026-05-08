# -----------------------------------------------------------------------------
# Arquivo : services/monitor_config_service.py
# Objetivo: Persistir e ler as configurações do monitor de turnos no Firestore,
#           com fallback para os valores padrão vindos das variáveis de ambiente.
# -----------------------------------------------------------------------------

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from services.firestore_client import db


CONFIG_COLLECTION = "app_config"
CONFIG_DOC_ID = "monitor_turnos"
CONFIG_CACHE_TTL_SEC = int(os.getenv("DDS_CONFIG_CACHE_TTL_SEC", "30"))

DEFAULT_MONITOR_RULES = {
    "alertaAmareloMin": int(os.getenv("DDS_ALERTA_AMARELO", "15")),
    "alertaVermelhoMin": int(os.getenv("DDS_ALERTA_VERMELHO", "30")),
    "alertaPiscoMin": int(os.getenv("DDS_ALERTA_PISCO", "60")),
    "fechadoViraDesatualizadoHoras": int(os.getenv("DDS_FECHADO_DESATUALIZA", "8")),
    "desatualizadoCriticoHoras": int(os.getenv("DDS_CRITICO_DESATUALIZA", "16")),
}
DEFAULT_POLLING_SECONDS = int(os.getenv("DDS_POLLING_SEGUNDOS", "600"))

_CONFIG_CACHE: dict[str, Any] = {
    "data": None,
    "fetched_at": None,
}


def get_monitor_settings(force_refresh: bool = False) -> dict[str, Any]:
    if not force_refresh and _is_cache_valid():
        return _CONFIG_CACHE["data"]

    snap = db.collection(CONFIG_COLLECTION).document(CONFIG_DOC_ID).get()
    stored = snap.to_dict() or {}
    settings = _merge_with_defaults(stored)
    _CONFIG_CACHE["data"] = settings
    _CONFIG_CACHE["fetched_at"] = datetime.now(timezone.utc)
    return settings


def get_monitor_rules(force_refresh: bool = False) -> dict[str, int]:
    settings = get_monitor_settings(force_refresh=force_refresh)
    return dict(settings.get("rules") or DEFAULT_MONITOR_RULES)


def get_monitor_polling_seconds(force_refresh: bool = False) -> int:
    settings = get_monitor_settings(force_refresh=force_refresh)
    return int(settings.get("pollingSeconds") or DEFAULT_POLLING_SECONDS)


def save_monitor_settings(payload: dict[str, Any]) -> dict[str, Any]:
    clean = _normalize_payload(payload)
    db.collection(CONFIG_COLLECTION).document(CONFIG_DOC_ID).set({
        **clean,
        "updatedAt": firestore.SERVER_TIMESTAMP,
        "updatedByName": "MONITOR WEB",
        "updatedByDeviceModel": "DDS_TURNOS_MONITOR",
    }, merge=True)
    _CONFIG_CACHE["data"] = clean
    _CONFIG_CACHE["fetched_at"] = datetime.now(timezone.utc)
    return clean


def _is_cache_valid() -> bool:
    fetched_at = _CONFIG_CACHE.get("fetched_at")
    if not isinstance(fetched_at, datetime):
        return False
    age_sec = (datetime.now(timezone.utc) - fetched_at).total_seconds()
    return age_sec < CONFIG_CACHE_TTL_SEC and isinstance(_CONFIG_CACHE.get("data"), dict)


def _merge_with_defaults(stored: dict[str, Any]) -> dict[str, Any]:
    raw_rules = stored.get("rules") if isinstance(stored.get("rules"), dict) else {}
    rules = {
        "alertaAmareloMin": _coerce_int(raw_rules.get("alertaAmareloMin"), DEFAULT_MONITOR_RULES["alertaAmareloMin"]),
        "alertaVermelhoMin": _coerce_int(raw_rules.get("alertaVermelhoMin"), DEFAULT_MONITOR_RULES["alertaVermelhoMin"]),
        "alertaPiscoMin": _coerce_int(raw_rules.get("alertaPiscoMin"), DEFAULT_MONITOR_RULES["alertaPiscoMin"]),
        "fechadoViraDesatualizadoHoras": _coerce_int(raw_rules.get("fechadoViraDesatualizadoHoras"), DEFAULT_MONITOR_RULES["fechadoViraDesatualizadoHoras"]),
        "desatualizadoCriticoHoras": _coerce_int(raw_rules.get("desatualizadoCriticoHoras"), DEFAULT_MONITOR_RULES["desatualizadoCriticoHoras"]),
    }
    return {
        "pollingSeconds": _coerce_int(stored.get("pollingSeconds"), DEFAULT_POLLING_SECONDS),
        "rules": rules,
    }


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    merged = _merge_with_defaults(payload or {})
    polling_seconds = max(15, _coerce_int(merged.get("pollingSeconds"), DEFAULT_POLLING_SECONDS))
    rules = merged["rules"]

    alerta_amarelo = max(1, _coerce_int(rules.get("alertaAmareloMin"), DEFAULT_MONITOR_RULES["alertaAmareloMin"]))
    alerta_vermelho = max(alerta_amarelo, _coerce_int(rules.get("alertaVermelhoMin"), DEFAULT_MONITOR_RULES["alertaVermelhoMin"]))
    alerta_pisco = max(alerta_vermelho, _coerce_int(rules.get("alertaPiscoMin"), DEFAULT_MONITOR_RULES["alertaPiscoMin"]))
    fechado_desat = max(1, _coerce_int(rules.get("fechadoViraDesatualizadoHoras"), DEFAULT_MONITOR_RULES["fechadoViraDesatualizadoHoras"]))
    desat_critico = max(fechado_desat, _coerce_int(rules.get("desatualizadoCriticoHoras"), DEFAULT_MONITOR_RULES["desatualizadoCriticoHoras"]))

    return {
        "pollingSeconds": polling_seconds,
        "rules": {
            "alertaAmareloMin": alerta_amarelo,
            "alertaVermelhoMin": alerta_vermelho,
            "alertaPiscoMin": alerta_pisco,
            "fechadoViraDesatualizadoHoras": fechado_desat,
            "desatualizadoCriticoHoras": desat_critico,
        },
    }


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return int(default)
