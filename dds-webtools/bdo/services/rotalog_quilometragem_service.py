"""Serviço de consulta e reconciliação da Quilometragem ROTALOG (Copel).

Lê os arquivos diários e mensais compactados em GZIP (.json.gz) gravados pelo coletor
tanto localmente (dados-local/) quanto no Firebase Storage (GCS).
Fornece acesso instantâneo O(1) por protocolo de serviço e por equipe.
"""

from __future__ import annotations

import datetime
import gzip
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo(os.getenv("DDS_TIMEZONE", "America/Sao_Paulo"))

# Cache em memória: { cache_key: (timestamp, data_dict) }
_KM_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_KM_CACHE_TTL_SECONDS = 60.0
_KM_LOCK = threading.RLock()


def normalize_empresa_key(empresa: str | None) -> str:
    """Normaliza o nome da empresa em minúsculas e sem caracteres especiais (ex: 'ChicoEletro' -> 'chicoeletro', 'DDS' -> 'dds')."""
    raw = str(empresa or os.getenv("DDS_EMPRESA_PADRAO", "dds")).strip().lower()
    return re.sub(r"[^a-z0-9_-]+", "", raw) or "dds"


def _safe_date_iso(target_date: str | None) -> str:
    if target_date:
        return datetime.date.fromisoformat(target_date).isoformat()
    return datetime.datetime.now(LOCAL_TZ).date().isoformat()


def _get_local_search_paths(relative_path: str) -> list[Path]:
    """Retorna candidatos de caminhos locais para busca do arquivo .json.gz."""
    candidates: list[Path] = []
    
    # 1. Variável de ambiente configurada
    custom_dir = os.getenv("ROTALOG_LOCAL_DATA_DIR")
    if custom_dir:
        candidates.append(Path(custom_dir) / relative_path)
    
    # 2. Pasta dados-local relativa ao diretório do projeto ou raiz
    candidates.append(Path("dados-local") / relative_path)
    candidates.append(Path(__file__).resolve().parents[2] / "dados-local" / relative_path)
    
    # 3. Pasta do coletor separado (dds-coletor-rtl)
    candidates.append(Path(r"D:\programas\dds-coletor-rtl\dados-local") / relative_path)
    candidates.append(Path("/home/orangepi/dds-coletor-rtl/dados-local") / relative_path)
    
    return candidates


def _load_json_gz_bytes(payload: bytes) -> dict[str, Any]:
    raw = gzip.decompress(payload) if payload.startswith(b"\x1f\x8b") else payload
    loaded = json.loads(raw.decode("utf-8-sig"))
    return loaded if isinstance(loaded, dict) else {}


def _read_from_local_or_gcs(rel_local: str, gcs_blob_path: str, bucket_name: str | None = None) -> dict[str, Any] | None:
    # Tentativa 1: Local
    for p in _get_local_search_paths(rel_local):
        if p.exists() and p.is_file():
            try:
                data = _load_json_gz_bytes(p.read_bytes())
                if data:
                    return data
            except Exception as exc:
                logger.debug("Falha ao ler arquivo local %s: %s", p, exc)

    # Tentativa 2: GCS / Firebase Storage
    b_name = bucket_name or os.getenv("DDS_BUCKET_NAME", "dds-treinamentos.firebasestorage.app")
    if b_name:
        try:
            from bdo.services.rotalog_change_tracker import RotalogGcsSnapshotStore
            store = RotalogGcsSnapshotStore(b_name, gcs_blob_path)
            data = store.load_blob(gcs_blob_path)
            if data and isinstance(data, dict):
                return data
        except Exception as exc:
            logger.debug("Arquivo GCS não encontrado em %s: %s", gcs_blob_path, exc)

    return None


def obter_quilometragem_diaria(
    empresa: str | None = None,
    data: str | None = None,
    *,
    permitir_fallback_ontem: bool = True,
) -> dict[str, Any]:
    """Carrega o mapa consolidado de quilometragem diária.
    
    Se 'data' não for informada e o arquivo de hoje ainda não estiver pronto,
    faz fallback automático para ontem (D-1).
    """
    empresa_key = normalize_empresa_key(empresa)
    target_date = _safe_date_iso(data)
    cache_key = f"km_diario_{empresa_key}_{target_date}"
    now = time.monotonic()

    with _KM_LOCK:
        cached = _KM_CACHE.get(cache_key)
        if cached and (now - cached[0] < _KM_CACHE_TTL_SECONDS):
            return cached[1]

    rel_local = f"rotalog/quilometragem/diario/{target_date}.json.gz"
    gcs_path = f"dados/{empresa_key}/rotalog/quilometragem/diario/{target_date}.json.gz"

    data_obj = _read_from_local_or_gcs(rel_local, gcs_path)

    # Se hoje não tiver arquivo ainda e fallback_ontem for True:
    if not data_obj and permitir_fallback_ontem and not data:
        ontem = (datetime.datetime.now(LOCAL_TZ).date() - datetime.timedelta(days=1)).isoformat()
        fallback_local = f"rotalog/quilometragem/diario/{ontem}.json.gz"
        fallback_gcs = f"dados/{empresa_key}/rotalog/quilometragem/diario/{ontem}.json.gz"
        data_obj = _read_from_local_or_gcs(fallback_local, fallback_gcs)
        if data_obj:
            logger.info("Quilometragem de hoje ainda não disponível. Usando ontem (%s).", ontem)

    result = data_obj or {}

    with _KM_LOCK:
        _KM_CACHE[cache_key] = (now, result)

    return result


def obter_quilometragem_mensal(
    empresa: str | None = None,
    mes: str | None = None,
) -> dict[str, Any]:
    """Carrega o mapa consolidado de fechamento de quilometragem mensal (AAAA-MM)."""
    empresa_key = normalize_empresa_key(empresa)
    if not mes:
        mes = datetime.datetime.now(LOCAL_TZ).strftime("%Y-%m")
    
    cache_key = f"km_mensal_{empresa_key}_{mes}"
    now = time.monotonic()

    with _KM_LOCK:
        cached = _KM_CACHE.get(cache_key)
        if cached and (now - cached[0] < _KM_CACHE_TTL_SECONDS):
            return cached[1]

    rel_local = f"rotalog/quilometragem/mensal/{mes}.json.gz"
    gcs_path = f"dados/{empresa_key}/rotalog/quilometragem/mensal/{mes}.json.gz"

    data_obj = _read_from_local_or_gcs(rel_local, gcs_path) or {}

    with _KM_LOCK:
        _KM_CACHE[cache_key] = (now, data_obj)

    return data_obj


def obter_quilometragem_equipe(
    empresa: str | None,
    team_key: str,
    data: str | None = None,
) -> dict[str, Any] | None:
    """Retorna {kmInformado, kmAutorizadoFinal, contrato} para a equipe especificada."""
    km_doc = obter_quilometragem_diaria(empresa, data)
    equipes_map = km_doc.get("totaisPorEquipe") or {}
    key = str(team_key or "").strip().upper()
    return equipes_map.get(key)


def obter_quilometragem_protocolo(
    empresa: str | None,
    protocolo: str,
    data: str | None = None,
) -> dict[str, Any] | None:
    """Retorna {equipe, kmInformado, kmAutorizadoFinal} para o protocolo/OS."""
    km_doc = obter_quilometragem_diaria(empresa, data)
    protocolos_map = km_doc.get("protocolos") or {}
    prot = str(protocolo or "").strip()
    return protocolos_map.get(prot)
