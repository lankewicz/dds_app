"""Read-only, company-scoped current event windows from the collector."""
from __future__ import annotations

from copy import deepcopy
import json
import logging
import os
import threading
import time

from bdo.services.rotalog_change_tracker import RotalogGcsSnapshotStore
from rotalog_event_contract import company_key, validate_window

logger = logging.getLogger(__name__)
_cache = {}
_lock = threading.RLock()


def event_blob(company):
    """Explicit roots for additional companies; never reuse the default company's root."""
    roots = json.loads(os.getenv("ROTALOG_COMPANY_STORAGE_PREFIXES", "{}"))
    if not isinstance(roots, dict):
        raise ValueError("Raízes de empresas inválidas")
    root = next((v for k, v in roots.items() if company_key(k) == company_key(company)), None)
    if root is None:
        configured = os.getenv("ROTALOG_EMPRESA", os.getenv("DDS_EMPRESA_PADRAO", "ChicoEletro"))
        if company_key(company) != company_key(configured):
            raise ValueError("Empresa sem raiz de eventos configurada")
        prefix = os.getenv("ROTALOG_TEAM_STORAGE_PREFIX", "").strip().strip("/")
        if prefix:
            if not prefix.endswith("/equipes"):
                raise ValueError("Raiz de equipes inválida")
            root = prefix[:-len("/equipes")]
        else:
            index = os.getenv("ROTALOG_GCS_CACHE_BLOB", "dados/chicoeletro/rotalog/equipes/current/index.json.gz").strip().strip("/")
            suffix = "/equipes/current/index.json.gz"
            if not index.endswith(suffix):
                raise ValueError("Raiz do índice inválida")
            root = index[:-len(suffix)]
    if not isinstance(root, str) or not root.strip("/") or any(p in (".", "..") for p in root.split("/")):
        raise ValueError("Raiz de eventos inválida")
    return root.strip("/") + "/events/current/index.json.gz"


def read_activity_window(company):
    from bdo.services.rotalog_reader import get_adaptive_rotalog_cache_ttl_seconds

    bucket = os.getenv("DDS_BUCKET_NAME", "dds-treinamentos.firebasestorage.app")
    with _lock:
        try:
            blob = event_blob(company)
        except (TypeError, ValueError):
            return {"available": False, "items": None, "updatedAt": None, "source": "rotalog_events"}
        key = (company_key(company), bucket, blob)
        entry = _cache.get(key, {})
        if time.monotonic() - entry.get("checked", float("-inf")) >= get_adaptive_rotalog_cache_ttl_seconds():
            try:
                store = RotalogGcsSnapshotStore(bucket, blob)
                payload = validate_window(store.load_blob(blob), company)
                entry = {"payload": payload, "available": True}
            except Exception as exc:
                logger.warning("Arquivo de eventos indisponível para %s (%s)", company, type(exc).__name__)
                entry = {**entry, "available": False}
            entry["checked"] = time.monotonic()
            _cache[key] = entry
        payload = entry.get("payload") or {}
        return deepcopy({**payload, "available": entry.get("available", False), "items": payload.get("items"),
                         "updatedAt": payload.get("updatedAt"), "source": "rotalog_events"})
