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

