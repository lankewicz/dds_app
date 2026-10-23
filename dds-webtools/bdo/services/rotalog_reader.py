"""Leitura dos resultados do coletor externo Rotalog; não executa raspagem.

Fontes: Orange Pi privado, Firebase Storage e arquivos locais de compatibilidade.
Não importa crawler, agenda coleta ou publica resultados operacionais.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import tempfile
import threading
import time
import typing

from bdo.services.rotalog_change_tracker import RotalogGcsSnapshotStore, RotalogLocalCache
from bdo.services.rotalog_team_file_repository import LOCAL_TZ, RotalogTeamFileRepository
from bdo.services.rotalog_execution_log import RotalogExecutionLog

logger = logging.getLogger(__name__)
_local_cache = RotalogLocalCache(os.getenv("ROTALOG_CACHE_PATH", os.path.join(tempfile.gettempdir(), "dds-rotalog", "monitor-cache.json")))
_durable_cache_store = RotalogGcsSnapshotStore(
    os.getenv("DDS_BUCKET_NAME", "dds-treinamentos.firebasestorage.app"),
    os.getenv("ROTALOG_GCS_CACHE_BLOB", "dados/chicoeletro/rotalog/equipes/current/index.json.gz"),
)
_durable_cache_state = {"hydrated": False, "source": "not_loaded", "reads": 0}
_durable_cache_lock = threading.RLock()
_team_file_repository = RotalogTeamFileRepository(_durable_cache_store)
_execution_log = RotalogExecutionLog(_durable_cache_store)

def get_rotalog_live_snapshots(force: bool = False) -> dict[str, dict[str, typing.Any]]:
    """Retorna a base ROTALOG em memória, hidratada com TTL adaptativo ou forçada via F5."""
    _hydrate_durable_cache_once(force=force)
    return _local_cache.snapshot()

def get_rotalog_live_snapshot(team_key: str) -> dict[str, typing.Any] | None:
    _hydrate_durable_cache_once()
    return _local_cache.get(normalize_team_key(team_key))

def get_rotalog_team_current(team_key: str) -> dict[str, typing.Any] | None:
    normalized = normalize_team_key(team_key)
    local = get_rotalog_live_snapshot(normalized)
    if local:
        return local
    if not _durable_cache_store.enabled:
        return None
    return _team_file_repository.load_current(normalized) or None

def get_rotalog_team_daily(team_key: str, day: str) -> dict[str, typing.Any] | None:
    datetime.date.fromisoformat(day)
    return _team_file_repository.load_daily(normalize_team_key(team_key), day) or None

def get_rotalog_team_daily_today(team_key: str) -> dict[str, typing.Any] | None:
    day = datetime.datetime.now(LOCAL_TZ).date().isoformat()
    return get_rotalog_team_daily(team_key, day)

def get_rotalog_execution_log(day: str | None = None) -> dict[str, typing.Any]:
    selected_day = day or datetime.datetime.now(LOCAL_TZ).date().isoformat()
    datetime.date.fromisoformat(selected_day)
    return _execution_log.load(selected_day)

def get_adaptive_rotalog_cache_ttl_seconds() -> int:
    """Calcula o TTL do cache baseado na grade horária operacional:
    - 07:00 às 18:00: 3 minutos (180s)
    - 18:00 às 07:00: 30 minutos (1800s)
    """
    now_hour = datetime.datetime.now(LOCAL_TZ).hour
    if 7 <= now_hour < 18:
        return 180
    return 1800

def _hydrate_durable_cache_once(force: bool = False) -> None:
    """Hidrata snapshots e índice; suporta Schema v2 (equipes), v1 (snapshots), TTL adaptativo e force para F5."""
    with _durable_cache_lock:
        ttl = get_adaptive_rotalog_cache_ttl_seconds()
        if (not force
                and _durable_cache_state["hydrated"]
                and time.monotonic() - _durable_cache_state.get("loaded_at", 0) < ttl):
            return
        local_snapshot = _local_cache.snapshot()
        remote_payload = None
        remote_source = "empty"

        # Orange privado primeiro; Firebase Storage se falhar ou não configurado.
        try:
            from bdo.services.rotalog_monitor_source import load_monitor_index

            def load_firebase():
                if not _durable_cache_store.enabled:
                    return {}
                _durable_cache_state["reads"] += 1
                return _durable_cache_store.load()

            remote_payload, remote_source = load_monitor_index(load_firebase)
        except Exception as exc:
            logger.warning("Não foi possível hidratar o índice de turnos: %s", type(exc).__name__)

        # Tentativa 2: Fallback local se GCS vazio ou desabilitado
        if not remote_payload:
            from pathlib import Path
            import gzip
            candidate_paths = [
                os.getenv("ROTALOG_INDEX_PATH"),
                os.path.join(os.getenv("ROTALOG_LOCAL_DATA_DIR", ""), "rotalog", "equipes", "current", "index.json"),
                os.path.join(os.getenv("ROTALOG_LOCAL_DATA_DIR", ""), "rotalog", "equipes", "current", "index.json.gz"),
                os.path.join("dados-local", "rotalog", "equipes", "current", "index.json"),
                os.path.join("dados-local", "rotalog", "equipes", "current", "index.json.gz"),
                r"D:\programas\dds-coletor-rtl\dados-local\rotalog\equipes\current\index.json",
                r"D:\programas\dds-coletor-rtl\dados-local\rotalog\equipes\current\index.json.gz",
                "/home/orangepi/dds-coletor-rtl/dados-local/rotalog/equipes/current/index.json",
                "/home/orangepi/dds-coletor-rtl/dados-local/rotalog/equipes/current/index.json.gz",
            ]
            for p_str in candidate_paths:
                if not p_str or not os.path.isfile(p_str):
                    continue
                try:
                    p = Path(p_str)
                    payload_bytes = p.read_bytes()
                    raw = gzip.decompress(payload_bytes) if payload_bytes.startswith(b"\x1f\x8b") else payload_bytes
                    loaded = json.loads(raw.decode("utf-8-sig"))
                    if isinstance(loaded, dict) and loaded:
                        remote_payload = loaded
                        remote_source = "local_file"
                        logger.info("Cache ROTALOG hidratado a partir do arquivo local: %s", p_str)
                        break
                except Exception as exc:
                    logger.debug("Falha ao ler cache local de %s: %s", p_str, exc)

        if not remote_payload:
            _durable_cache_state.update({
                "hydrated": True,
                "source": "local" if local_snapshot else "empty",
                "loaded_at": time.monotonic(),
            })
            return

        try:
            # Schema v2: equipes | Schema v1: snapshots
            remote_snapshots = remote_payload.get("equipes") if isinstance(remote_payload.get("equipes"), dict) else None
            if remote_snapshots is None:
                remote_snapshots = remote_payload.get("snapshots") if isinstance(remote_payload.get("snapshots"), dict) else None
            if remote_snapshots is None:
                # Compatibilidade com o formato legado direto
                remote_snapshots = remote_payload

            if isinstance(remote_snapshots, dict):
                collected_at = (
                    remote_payload.get("lastCollectedAt")
                    or remote_payload.get("updatedAtIso")
                    or remote_payload.get("collectedAt")
                )
                for team_code, snapshot in remote_snapshots.items():
                    if isinstance(snapshot, dict):
                        if collected_at:
                            snapshot.setdefault("lastCollectedAt", collected_at)
                        snapshot.setdefault("teamKey", team_code)
                _local_cache.replace(remote_snapshots)

            source = remote_source
            _durable_cache_state.update({"hydrated": True, "source": source, "loaded_at": time.monotonic()})
        except Exception as exc:
            logger.warning("Erro ao processar payload do cache ROTALOG: %s", exc)
            _durable_cache_state.update({"hydrated": False, "source": "error"})

def normalize_team_key(raw: str) -> str:
    return re.sub(r"[^A-Z0-9_-]", "_", raw.strip().upper())
