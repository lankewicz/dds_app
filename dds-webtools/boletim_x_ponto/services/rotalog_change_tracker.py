"""Detecção incremental de mudanças do monitor Rotalog.

O cache é apenas um acelerador local. O Firestore continua sendo a fonte
compartilhada entre portal, tablet e monitor.
"""

from __future__ import annotations

import datetime
import gzip
import json
import os
import tempfile
import threading
import typing


def _json_cache_default(value: typing.Any) -> typing.Any:
    """Converte timestamps do Firestore para ISO sem mascarar tipos inválidos."""
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

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

    def snapshot(self) -> dict[str, dict[str, typing.Any]]:
        with self._lock:
            return {key: dict(value) for key, value in self._load().items() if isinstance(value, dict)}

    def replace(self, snapshots: dict[str, dict[str, typing.Any]]) -> None:
        with self._lock:
            self._data = {key: dict(value) for key, value in snapshots.items() if isinstance(value, dict)}
            self._flush()

    def _flush(self) -> None:
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix="rotalog-cache-", suffix=".json", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self._data, stream, ensure_ascii=False, sort_keys=True, default=_json_cache_default)
            os.replace(temp_path, self.path)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
class RotalogGcsSnapshotStore:
    """Snapshot JSON gzip durável; não realiza nenhuma operação no Firestore."""

    def __init__(
        self,
        bucket_name: str,
        blob_name: str,
        *,
        client_factory: typing.Callable[[], typing.Any] | None = None,
    ):
        self.bucket_name = bucket_name.strip()
        self.blob_name = blob_name.strip().lstrip("/")
        self._client_factory = client_factory
        self._client = None
        self._lock = threading.RLock()

    @property
    def enabled(self) -> bool:
        return bool(self.bucket_name and self.blob_name)

    def _blob(self):
        if not self.enabled:
            raise RuntimeError("Cache GCS do ROTALOG não configurado.")
        if self._client is None:
            if self._client_factory is not None:
                self._client = self._client_factory()
            else:
                from google.cloud import storage

                self._client = storage.Client()
        return self._client.bucket(self.bucket_name).blob(self.blob_name)

    def load(self) -> dict[str, typing.Any]:
        with self._lock:
            try:
                compressed = self._blob().download_as_bytes()
            except Exception as exc:
                # 404 é tratado pelo chamador como cache ainda não criado.
                if getattr(exc, "code", None) == 404:
                    return {}
                raise
            loaded = json.loads(gzip.decompress(compressed).decode("utf-8"))
            return loaded if isinstance(loaded, dict) else {}

    def save(self, snapshots: dict[str, typing.Any]) -> None:
        with self._lock:
            raw = json.dumps(
                snapshots,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=_json_cache_default,
            ).encode("utf-8")
            blob = self._blob()
            blob.content_encoding = "gzip"
            blob.upload_from_string(
                gzip.compress(raw, compresslevel=6),
                content_type="application/json",
            )
