"""Leitura do índice de turnos: Orange Pi privado, depois Firebase Storage."""

from __future__ import annotations

import gzip
import json
import logging
import os
from typing import Any, Callable

import requests

logger = logging.getLogger(__name__)


def validate_index(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Índice de turnos não é um objeto JSON")
    teams = payload.get("equipes", payload.get("snapshots"))
    if not isinstance(teams, dict) or not all(isinstance(value, dict) for value in teams.values()):
        raise ValueError("Índice de turnos sem mapa de equipes válido")
    return payload


def load_monitor_index(firebase_loader: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], str]:
    url = os.getenv("ROTALOG_ORANGE_INDEX_URL", "").strip()
    if url:
        try:
            timeout = max(0.1, min(10.0, float(os.getenv("ROTALOG_ORANGE_TIMEOUT_SECONDS", "2"))))
            with requests.Session() as session:
                # Proxy SOCKS exclusivo do Orange; Firebase usa sua conexão normal.
                session.trust_env = False
                proxy = os.getenv("ROTALOG_ORANGE_PROXY", "").strip()
                proxies = {"http": proxy, "https": proxy} if proxy else {}
                response = session.get(url, timeout=(timeout, timeout), proxies=proxies, allow_redirects=False)
                if response.status_code != 200:
                    raise ValueError(f"HTTP {response.status_code}")
                raw = response.content
                if raw.startswith(b"\x1f\x8b"):
                    raw = gzip.decompress(raw)
                payload = validate_index(json.loads(raw.decode("utf-8-sig")))
                return payload, "orangepi"
        except Exception as exc:
            logger.warning("Orange indisponível ou índice inválido (%s); lendo Firebase.", type(exc).__name__)
    payload = firebase_loader()
    if not payload:
        return {}, "empty"
    return validate_index(payload), "firebase"
