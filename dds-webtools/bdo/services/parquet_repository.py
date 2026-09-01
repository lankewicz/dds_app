"""Repositório versionado de datasets Parquet no Cloud Storage.

Os arquivos são imutáveis. Uma gravação cria novas versões e só se torna
visível depois da troca atômica do ``manifest.json``. Consultas continuam
lendo a versão anterior durante uma importação.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import storage


SCHEMA_VERSION = 1
DEFAULT_PREFIX = "webtools/bdo"
MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    date_column: str | None
    key_columns: tuple[str, ...]

    @property
    def partitioned(self) -> bool:
        return bool(self.date_column)


DATASETS: dict[str, DatasetSpec] = {
    "boletim": DatasetSpec("boletim", "DATA", ("chave_unica",)),
    "ponto": DatasetSpec("ponto", "Data", ("chave_unica",)),
    "boletim_var": DatasetSpec("boletim_var", None, ("_chave",)),
    "relacao_nomes": DatasetSpec("relacao_nomes", None, ("Nome_Boletim",)),
    "contrato_boletim": DatasetSpec(
        "contrato_boletim", None, ("Contrato", "Boletim", "Ano", "Mes")
    ),
    "rotalog_equipes": DatasetSpec(
        "rotalog_equipes", "Data", ("Data", "Veículo", "Contrato", "Eletricista 1", "Eletricista 2")
    ),
    "rotalog_eventos": DatasetSpec(
        "rotalog_eventos", "Data", ("Data", "Protocolo", "Evento", "Inicio Deslo", "Veículo")
    ),
}


@dataclass
class ImportStats:
    processed: int = 0
    new: int = 0
    updated: int = 0
    ignored: int = 0
    duplicate_input: int = 0
    partitions_written: int = 0

    def merge(self, other: "ImportStats") -> None:
        for field in asdict(self):
            setattr(self, field, getattr(self, field) + getattr(other, field))

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class ManifestConflict(RuntimeError):
    """Outro processo publicou uma versão durante esta importação."""


class ObjectStore:
    def download(self, name: str) -> tuple[bytes, int]:
        raise NotImplementedError

    def upload(
        self,
        name: str,
        payload: bytes,
        *,
        content_type: str,
        if_generation_match: int | None = None,
    ) -> int:
        raise NotImplementedError

    def delete(self, name: str) -> None:
        raise NotImplementedError


class GCSObjectStore(ObjectStore):
    def __init__(self, bucket_name: str):
        if not bucket_name:
            raise RuntimeError("DDS_BUCKET_NAME não configurado.")
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)

    def download(self, name: str) -> tuple[bytes, int]:
        blob = self.bucket.blob(name)
        try:
            blob.reload()
            return blob.download_as_bytes(), int(blob.generation or 0)
        except NotFound:
            raise FileNotFoundError(name) from None

    def upload(
        self,
        name: str,
        payload: bytes,
        *,
        content_type: str,
        if_generation_match: int | None = None,
    ) -> int:
        blob = self.bucket.blob(name)
        kwargs: dict[str, Any] = {"content_type": content_type}
        if if_generation_match is not None:
            kwargs["if_generation_match"] = if_generation_match
        blob.upload_from_string(payload, **kwargs)
        blob.reload()
        return int(blob.generation or 0)

    def delete(self, name: str) -> None:
        try:
            self.bucket.blob(name).delete()
        except NotFound:
            pass


class LocalObjectStore(ObjectStore):
    """Backend de desenvolvimento/testes com semântica de geração."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, name: str) -> Path:
        target = (self.root / name).resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError("Caminho fora do armazenamento local.")
        return target

    @staticmethod
    def _generation(path: Path) -> int:
        return path.stat().st_mtime_ns if path.exists() else 0

    def download(self, name: str) -> tuple[bytes, int]:
        path = self._path(name)
        with self._lock:
            if not path.exists():
                raise FileNotFoundError(name)
            return path.read_bytes(), self._generation(path)

    def upload(
        self,
        name: str,
        payload: bytes,
        *,
        content_type: str,
        if_generation_match: int | None = None,
    ) -> int:
        del content_type
        path = self._path(name)
        with self._lock:
            current = self._generation(path)
            if if_generation_match is not None and current != if_generation_match:
                raise PreconditionFailed("Geração local divergente")
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=path.name, dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_name, path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
            return self._generation(path)

    def delete(self, name: str) -> None:
        path = self._path(name)
        with self._lock:
            if path.exists():
                path.unlink()


def create_object_store() -> ObjectStore:
    local_dir = os.getenv("BOLETIM_X_PONTO_LOCAL_STORAGE_DIR", "").strip()
    if local_dir:
        return LocalObjectStore(local_dir)
    return GCSObjectStore(os.getenv("DDS_BUCKET_NAME", "").strip())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_manifest() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": 0,
        "updated_at": None,
        "datasets": {},
    }


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")


def _parquet_bytes(df: pd.DataFrame) -> bytes:
    stream = io.BytesIO()
    df.to_parquet(stream, index=False, compression="snappy")
    return stream.getvalue()


def _read_parquet(payload: bytes) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(payload))


def _normal_value(value: Any) -> Any:
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, float):
        return round(value, 10)
    return value


def _rows_equal(left: pd.Series, right: pd.Series, columns: Iterable[str]) -> bool:
    return all(_normal_value(left.get(c)) == _normal_value(right.get(c)) for c in columns)


class ParquetStorageRepository:
    """Acesso aos Parquets particionados e versionados."""

    def __init__(
        self,
        store: ObjectStore | None = None,
        *,
        prefix: str | None = None,
        manifest_ttl_seconds: float = 2.0,
    ):
        self.store = store or create_object_store()
        self.prefix = (
            prefix
            or os.getenv("BOLETIM_X_PONTO_STORAGE_PREFIX")
            or DEFAULT_PREFIX
        ).strip("/")
        self.manifest_path = f"{self.prefix}/{MANIFEST_NAME}"
        self.manifest_ttl_seconds = manifest_ttl_seconds
        self._manifest_cache: tuple[dict[str, Any], int, float] | None = None
        self._frame_cache: dict[tuple[str, int], pd.DataFrame] = {}
        self._write_lock = threading.RLock()

    def get_manifest(self, *, force: bool = False) -> tuple[dict[str, Any], int]:
        now = time.monotonic()
        if not force and self._manifest_cache:
            manifest, generation, cached_at = self._manifest_cache
            if now - cached_at <= self.manifest_ttl_seconds:
                return manifest, generation
        try:
            payload, generation = self.store.download(self.manifest_path)
            manifest = json.loads(payload.decode("utf-8"))
        except FileNotFoundError:
            manifest, generation = _empty_manifest(), 0
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise RuntimeError("Versão do manifesto Parquet não suportada.")
        self._manifest_cache = (manifest, generation, now)
        return manifest, generation

    @staticmethod
    def _dataset_entry(manifest: dict[str, Any], spec: DatasetSpec) -> dict[str, Any]:
        return manifest.setdefault("datasets", {}).setdefault(
            spec.name,
            {
                "date_column": spec.date_column,
                "key_columns": list(spec.key_columns),
                "partitioned": spec.partitioned,
                "partitions": {},
                "summary": {},
            },
        )

    def _load_version(self, info: dict[str, Any]) -> pd.DataFrame:
        path = str(info["path"])
        generation = int(info.get("generation") or 0)
        key = (path, generation)
        cached = self._frame_cache.get(key)
        if cached is not None:
            return cached.copy()
        payload, real_generation = self.store.download(path)
        df = _read_parquet(payload)
        self._frame_cache[(path, real_generation)] = df
        return df.copy()

    @staticmethod
    def _wanted_partitions(
        spec: DatasetSpec,
        entry: dict[str, Any],
        data_ini: Any = None,
        data_fim: Any = None,
    ) -> list[str]:
        available = sorted(entry.get("partitions", {}))
        if not spec.partitioned or data_ini is None or data_fim is None:
            return available
        start = pd.Timestamp(data_ini).to_period("M")
        end = pd.Timestamp(data_fim).to_period("M")
        wanted = {str(p) for p in pd.period_range(start, end, freq="M")}
        return [p for p in available if p in wanted]

    def read(
        self,
        dataset: str,
        data_ini: Any = None,
        data_fim: Any = None,
        *,
        columns: list[str] | None = None,
    ) -> pd.DataFrame:
        spec = DATASETS[dataset]
        manifest, _ = self.get_manifest()
        entry = manifest.get("datasets", {}).get(dataset, {})
        frames = []
        for partition in self._wanted_partitions(spec, entry, data_ini, data_fim):
            info = entry.get("partitions", {}).get(partition)
            if info:
                frames.append(self._load_version(info))
        if not frames:
            return pd.DataFrame(columns=columns or [])
        df = pd.concat(frames, ignore_index=True, sort=False)
        if spec.date_column and spec.date_column in df.columns:
            dates = pd.to_datetime(df[spec.date_column], errors="coerce")
            df[spec.date_column] = dates
            if data_ini is not None:
                df = df[dates >= pd.Timestamp(data_ini)]
            if data_fim is not None:
                df = df[dates <= pd.Timestamp(data_fim)]
        if columns is not None:
            for col in columns:
                if col not in df.columns:
                    df[col] = None
            df = df[columns]
        return df.reset_index(drop=True)

    @staticmethod
    def _partition_frames(df: pd.DataFrame, spec: DatasetSpec) -> dict[str, pd.DataFrame]:
        if not spec.partitioned:
            return {"all": df.copy()}
        if spec.date_column not in df.columns:
            raise ValueError(f"Coluna de data ausente em {spec.name}: {spec.date_column}")
        out = df.copy()
        out[spec.date_column] = pd.to_datetime(out[spec.date_column], errors="coerce")
        out = out[out[spec.date_column].notna()].copy()
        if out.empty:
            return {}
        periods = out[spec.date_column].dt.to_period("M").astype(str)
        return {str(key): part.copy() for key, part in out.groupby(periods)}

    @staticmethod
    def _ensure_key(df: pd.DataFrame, spec: DatasetSpec) -> pd.DataFrame:
        out = df.copy()
        missing = [c for c in spec.key_columns if c not in out.columns]
        if missing:
            raise ValueError(f"Chaves ausentes em {spec.name}: {', '.join(missing)}")
        out["__repo_key"] = (
            out[list(spec.key_columns)].fillna("").astype(str).agg("\x1f".join, axis=1)
        )
        empty_key = out["__repo_key"].str.replace("\x1f", "", regex=False) == ""
        if empty_key.any():
            raise ValueError(f"Há registros sem chave válida em {spec.name}.")
        return out

    @classmethod
    def _upsert_frame(
        cls, current: pd.DataFrame, incoming: pd.DataFrame, spec: DatasetSpec
    ) -> tuple[pd.DataFrame, ImportStats]:
        stats = ImportStats(processed=len(incoming))
        if incoming.empty:
            return current.copy(), stats
        new = cls._ensure_key(incoming, spec)
        before = len(new)
        new = new.drop_duplicates("__repo_key", keep="last")
        stats.duplicate_input = before - len(new)
        stats.ignored += stats.duplicate_input

        if current is None or current.empty:
            stats.new = len(new)
            return new.drop(columns="__repo_key").reset_index(drop=True), stats

        old = cls._ensure_key(current, spec).drop_duplicates("__repo_key", keep="last")
        old_idx = old.set_index("__repo_key", drop=False)
        new_idx = new.set_index("__repo_key", drop=False)
        compare_columns = sorted((set(old.columns) | set(new.columns)) - {"__repo_key"})
        changed_keys: list[str] = []
        for key, row in new_idx.iterrows():
            if key not in old_idx.index:
                stats.new += 1
                changed_keys.append(key)
            elif _rows_equal(old_idx.loc[key], row, compare_columns):
                stats.ignored += 1
            else:
                stats.updated += 1
                changed_keys.append(key)

        if not changed_keys:
            return old.drop(columns="__repo_key").reset_index(drop=True), stats
        kept = old[~old["__repo_key"].isin(changed_keys)]
        changed = new[new["__repo_key"].isin(changed_keys)]
        result = pd.concat([kept, changed], ignore_index=True, sort=False)
        return result.drop(columns="__repo_key").reset_index(drop=True), stats

    @staticmethod
    def _partition_metadata(df: pd.DataFrame, spec: DatasetSpec) -> dict[str, Any]:
        meta: dict[str, Any] = {"rows": int(len(df))}
        if spec.date_column and spec.date_column in df.columns:
            dates = pd.to_datetime(df[spec.date_column], errors="coerce").dropna()
            if not dates.empty:
                meta["date_min"] = dates.min().strftime("%Y-%m-%d")
                meta["date_max"] = dates.max().strftime("%Y-%m-%d")
        values_to_collect = {
            "Contrato": "contracts",
            "Funcionário": "employees",
            "Nome": "names",
            "Nome_Boletim": "boletim_names",
        }
        for column, target in values_to_collect.items():
            if column in df.columns:
                meta[target] = sorted(
                    {str(v).strip() for v in df[column].dropna() if str(v).strip()}
                )
        return meta

    @staticmethod
    def _refresh_summary(entry: dict[str, Any]) -> None:
        parts = list(entry.get("partitions", {}).values())
        summary: dict[str, Any] = {
            "rows": sum(int(part.get("rows") or 0) for part in parts)
        }
        mins = [part.get("date_min") for part in parts if part.get("date_min")]
        maxes = [part.get("date_max") for part in parts if part.get("date_max")]
        if mins:
            summary["date_min"] = min(mins)
        if maxes:
            summary["date_max"] = max(maxes)
        for field in ("contracts", "employees", "names", "boletim_names"):
            summary[field] = sorted(
                {value for part in parts for value in part.get(field, [])}
            )
        entry["summary"] = summary

    def upsert(
        self, dataset: str, df: pd.DataFrame, *, max_retries: int = 3
    ) -> ImportStats:
        spec = DATASETS[dataset]
        partitions = self._partition_frames(df, spec)
        if not partitions:
            return ImportStats()

        with self._write_lock:
            for attempt in range(max_retries):
                manifest, manifest_generation = self.get_manifest(force=True)
                manifest = json.loads(json.dumps(manifest))
                entry = self._dataset_entry(manifest, spec)
                written_paths: list[str] = []
                attempt_total = ImportStats()
                revision = int(manifest.get("revision") or 0) + 1
                try:
                    for partition, incoming in partitions.items():
                        current_info = entry.get("partitions", {}).get(partition)
                        current = (
                            self._load_version(current_info)
                            if current_info
                            else pd.DataFrame()
                        )
                        merged, stats = self._upsert_frame(current, incoming, spec)
                        attempt_total.merge(stats)
                        if stats.new == 0 and stats.updated == 0:
                            continue
                        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                        path = (
                            f"{self.prefix}/datasets/{dataset}/partition={partition}/"
                            f"r{revision:08d}-{stamp}-{uuid.uuid4().hex[:8]}.parquet"
                        )
                        generation = self.store.upload(
                            path,
                            _parquet_bytes(merged),
                            content_type="application/vnd.apache.parquet",
                            if_generation_match=0,
                        )
                        written_paths.append(path)
                        entry.setdefault("partitions", {})[partition] = {
                            "path": path,
                            "generation": generation,
                            "updated_at": _utc_now(),
                            **self._partition_metadata(merged, spec),
                        }
                        attempt_total.partitions_written += 1

                    if attempt_total.partitions_written == 0:
                        return attempt_total
                    self._refresh_summary(entry)
                    manifest["revision"] = revision
                    manifest["updated_at"] = _utc_now()
                    new_generation = self.store.upload(
                        self.manifest_path,
                        _json_bytes(manifest),
                        content_type="application/json; charset=utf-8",
                        if_generation_match=manifest_generation,
                    )
                    self._manifest_cache = (
                        manifest,
                        new_generation,
                        time.monotonic(),
                    )
                    return attempt_total
                except PreconditionFailed:
                    for path in written_paths:
                        self.store.delete(path)
                    self._manifest_cache = None
                    if attempt + 1 >= max_retries:
                        raise ManifestConflict(
                            "Os dados foram atualizados por outro usuário. Tente novamente."
                        ) from None
                except Exception:
                    for path in written_paths:
                        self.store.delete(path)
                    raise
        return ImportStats()

    def summary(self, dataset: str) -> dict[str, Any]:
        manifest, _ = self.get_manifest()
        return dict(
            manifest.get("datasets", {}).get(dataset, {}).get("summary", {})
        )

    def revision(self) -> int:
        manifest, _ = self.get_manifest()
        return int(manifest.get("revision") or 0)

    def invalidate_cache(self) -> None:
        self._manifest_cache = None
        self._frame_cache.clear()
