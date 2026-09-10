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
import uuid
import time


def _json_cache_default(value: typing.Any) -> typing.Any:
    """Converte timestamps do Firestore para ISO sem mascarar tipos inválidos."""
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

def _decode_json_object(payload: bytes) -> dict[str, typing.Any]:
    """Aceita tanto o JSON legado puro quanto o formato atual JSON+GZIP."""
    raw = gzip.decompress(payload) if payload.startswith(b"\x1f\x8b") else payload
    loaded = json.loads(raw.decode("utf-8-sig"))
    return loaded if isinstance(loaded, dict) else {}

TRACKED_FIELDS = (
    "isOnline",
    "statusConexao",
    "identificadorEquipamento",
    "veiculo",
    "colaborador",
    "estadoConsolidado",
    "turno",
    "intervalo",
    "intervalos",
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
        if _operational_value(old_value) != _operational_value(new_value):
            changes[field] = {"anterior": old_value, "novo": new_value}
    return changes


def _operational_value(value):
    if isinstance(value, dict):
        return {k: _operational_value(v) for k, v in value.items()
                if k not in {"eventIdx", "fonteProtocolo", "validacaoProtocolo", "observadoEm"}}
    if isinstance(value, list):
        return sorted((_operational_value(v) for v in value),
                      key=lambda v: json.dumps(v, sort_keys=True, default=str))
    return value


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
def _safe_download_bytes(blob: typing.Any) -> bytes:
    try:
        return blob.download_as_bytes(raw_download=True)
    except TypeError:
        return blob.download_as_bytes()


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

    def _blob_named(self, blob_name: str):
        if (not blob_name or blob_name.startswith("/") or "\\" in blob_name
                or any(part in ("", ".", "..") for part in blob_name.split("/"))):
            raise ValueError("Destino GCS invalido")
        if not self.enabled:
            raise RuntimeError("Cache GCS do ROTALOG não configurado.")
        if self._client is None:
            if self._client_factory is not None:
                self._client = self._client_factory()
            else:
                from google.cloud import storage

                self._client = storage.Client()
        return self._client.bucket(self.bucket_name).blob(blob_name.strip().lstrip("/"))

    def _blob(self):
        return self._blob_named(self.blob_name)

    def acquire_sync_lease(self):
        token = uuid.uuid4().hex
        now = time.time()
        path = self.blob_name.rsplit("/", 1)[0] + "/sync-lease.json.gz"
        def acquire(previous):
            if float(previous.get("expiresAt", 0)) > now:
                return previous
            return {"owner": token, "expiresAt": now + 1800}
        result = self.update_blob(path, acquire)
        return token if result.get("owner") == token else None

    def release_sync_lease(self, token):
        path = self.blob_name.rsplit("/", 1)[0] + "/sync-lease.json.gz"
        self.update_blob(path, lambda previous:
                         {} if previous.get("owner") == token else previous)

    def load(self) -> dict[str, typing.Any]:
        with self._lock:
            try:
                compressed = _safe_download_bytes(self._blob())
            except Exception as exc:
                # 404 é tratado pelo chamador como cache ainda não criado.
                if getattr(exc, "code", None) == 404:
                    return {}
                raise
            return _decode_json_object(compressed)

    def save(self, snapshots: dict[str, typing.Any]) -> None:
        self.save_blob(self.blob_name, snapshots)

    def load_blob(self, blob_name: str) -> dict[str, typing.Any]:
        with self._lock:
            try:
                compressed = _safe_download_bytes(self._blob_named(blob_name))
            except Exception as exc:
                if getattr(exc, "code", None) == 404:
                    return {}
                raise
            return _decode_json_object(compressed)

    def update_blob(self, blob_name, transform):
        """Compare-and-swap: recalcula o merge se outro processo gravar."""
        for tentativa in range(5):
            blob = self._blob_named(blob_name)
            try:
                blob.reload()
                generation = int(blob.generation)
                previous = _decode_json_object(blob.download_as_bytes(raw_download=True, if_generation_match=generation))
            except Exception as exc:
                if getattr(exc, "code", None) == 404:
                    generation, previous = 0, {}
                elif getattr(exc, "code", None) == 412:
                    continue
                else:
                    raise
            merged = transform(previous)
            raw = json.dumps(merged, ensure_ascii=False, default=_json_cache_default).encode("utf-8")
            try:
                blob.content_encoding = "gzip"
                blob.upload_from_string(gzip.compress(raw), content_type="application/json",
                                        if_generation_match=generation)
                return merged
            except Exception as exc:
                if getattr(exc, "code", None) != 412:
                    raise
        raise RuntimeError("Conflito concorrente persistente no JSON RTL")

    def save_blob(self, blob_name: str, payload: dict[str, typing.Any]) -> None:
        with self._lock:
            raw = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=_json_cache_default,
            ).encode("utf-8")
            blob = self._blob_named(blob_name)
            blob.content_encoding = "gzip"
            blob.upload_from_string(
                gzip.compress(raw, compresslevel=6),
                content_type="application/json",
            )

    def list_blob_names(self, prefix: str) -> list[str]:
        if not self.enabled:
            return []
        if self._client is None:
            self._blob()
        return [blob.name for blob in self._client.list_blobs(self.bucket_name, prefix=prefix.strip().lstrip("/"))]

    def upload_bytes(self, blob_name: str, payload: bytes, content_type: str) -> None:
        with self._lock:
            self._blob_named(blob_name).upload_from_string(payload, content_type=content_type)
