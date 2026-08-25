"""Detecção incremental de mudanças do monitor Rotalog.

O cache é apenas um acelerador local. O Firestore continua sendo a fonte
compartilhada entre portal, tablet e monitor.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import typing


TRACKED_FIELDS = (
    "estadoConsolidado",
    "turno",
    "intervalo",
    "atividadeAtual",
    "ssExecutadas",
    "ssEmAndamento",
    "ssPendentes",
)


def compact_snapshot(document: dict[str, typing.Any]) -> dict[str, typing.Any]:
    """Retém somente campos operacionais cuja mudança deve gerar persistência."""
    return {field: document.get(field) for field in TRACKED_FIELDS}


def changed_fields(
    previous: dict[str, typing.Any] | None,
    current: dict[str, typing.Any],
) -> dict[str, dict[str, typing.Any]]:
    """Retorna o diff de primeiro nível, sem registrar leituras idênticas."""
    if previous is None:
        return {
            field: {"anterior": None, "novo": current.get(field)}
            for field in TRACKED_FIELDS
            if current.get(field) is not None
        }

    changes: dict[str, dict[str, typing.Any]] = {}
    for field in TRACKED_FIELDS:
        old_value = previous.get(field)
        new_value = current.get(field)
        if old_value != new_value:
            changes[field] = {"anterior": old_value, "novo": new_value}
    return changes


class RotalogLocalCache:
    """Cache JSON thread-safe com substituição atômica do arquivo."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        self._data: dict[str, dict[str, typing.Any]] | None = None

    def _load(self) -> dict[str, dict[str, typing.Any]]:
        if self._data is not None:
            return self._data
        try:
            with open(self.path, "r", encoding="utf-8") as stream:
                loaded = json.load(stream)
                self._data = loaded if isinstance(loaded, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._data = {}
        return self._data

    def get(self, team_key: str) -> dict[str, typing.Any] | None:
        with self._lock:
            value = self._load().get(team_key)
            return dict(value) if isinstance(value, dict) else None

    def set(self, team_key: str, snapshot: dict[str, typing.Any]) -> None:
        self.set_many({team_key: snapshot})

    def set_many(self, snapshots: dict[str, dict[str, typing.Any]]) -> None:
        with self._lock:
            self._load().update(snapshots)
            self._flush()

    def _flush(self) -> None:
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix="rotalog-cache-", suffix=".json", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self._data, stream, ensure_ascii=False, sort_keys=True)
            os.replace(temp_path, self.path)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
