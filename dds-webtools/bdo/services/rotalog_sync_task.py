"""
Serviço de Sincronização e Reconciliação do ROTALOG Tempo Real com o Firebase Firestore.
Lê o turno do ROTALOG e o turno do DDS, analisa qual informação é mais recente por timestamp
e aplica o estado mais recente no DDS nos documentos do Firestore.
Inclui verificação por Hash/Fingerprint para evitar gravações redundantes no Firestore (Otimização de Custos).
Inclui o RotalogBackgroundScheduler para checagem automática periódica a cada 5 minutos (300s).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import time
import typing
import firebase_admin
from firebase_admin import credentials, firestore

from bdo.services.rotalog_tempo_real_service import extrair_dados_tempo_real
from bdo.services.rotalog_team_file_repository import (
    LOCAL_TZ,
    RotalogTeamFileRepository,
)
from bdo.services.rotalog_change_tracker import (
    RotalogGcsSnapshotStore,
    RotalogLocalCache,
    changed_fields,
    compact_snapshot,
)

logger = logging.getLogger(__name__)

_firestore_db = None
_sync_execution_lock = threading.Lock()
_cache_path = os.environ.get(
    "ROTALOG_CACHE_PATH",
    os.path.join(tempfile.gettempdir(), "dds-rotalog", "monitor-cache.json"),
)
_local_cache = RotalogLocalCache(_cache_path)
_equipment_index_cache: dict[str, typing.Any] = {"data": {}, "team_docs": {}, "loaded_at": 0.0}
_EQUIPMENT_INDEX_TTL_SECONDS = 86400  # 24 horas
_durable_cache_store = RotalogGcsSnapshotStore(
    os.getenv("DDS_BUCKET_NAME", "dds-treinamentos.firebasestorage.app"),
    os.getenv("ROTALOG_GCS_CACHE_BLOB", "_cache/rotalog/monitor-snapshot.json.gz"),
)
_durable_cache_state: dict[str, typing.Any] = {
    "hydrated": False,
    "source": "not_loaded",
    "reads": 0,
    "writes": 0,
    "equipment_loaded_from_firestore": False,
    "equipment_firestore_reads": 0,
}
_durable_cache_lock = threading.RLock()
_team_file_repository = RotalogTeamFileRepository(_durable_cache_store)
_ROTALOG_PERSISTENCE_MODE = os.getenv("ROTALOG_PERSISTENCE_MODE", "json").strip().lower()
_json_activity_feed: list[dict[str, typing.Any]] = []


def get_rotalog_live_snapshots() -> dict[str, dict[str, typing.Any]]:
    """Retorna a base ROTALOG em memória, hidratada uma vez pelo JSON/GCS."""
    _hydrate_durable_cache_once()
    return _local_cache.snapshot()


def get_rotalog_activity_feed(limit: int = 30) -> dict[str, typing.Any]:
    _hydrate_durable_cache_once()
    snapshots = _local_cache.snapshot()
    abertas = sum(
        1
        for snapshot in snapshots.values()
        if bool((snapshot.get("turno") or {}).get("aberto"))
        or str(snapshot.get("estadoConsolidado") or "").upper() in {"ABERTO", "INTERVALO", "DESLOCAMENTO_ESPECIAL"}
    )
    comerciais = sum(int(snapshot.get("ssPendentesComercialCount") or 0) for snapshot in snapshots.values())
    emergenciais = sum(int(snapshot.get("ssPendentesEmergenciaCount") or 0) for snapshot in snapshots.values())
    now_local = datetime.datetime.now(LOCAL_TZ)
    formatted_items = []
    for item in _json_activity_feed:
        label = str(item.get("label") or "").upper()
        if " - FILA:" in label or "DADOS OPERACIONAIS ATUALIZADOS" in label:
            continue
        hora = item.get("time") or ""
        dt = None
        if item.get("activityAt"):
            try:
                dt = datetime.datetime.fromisoformat(str(item["activityAt"]).replace("Z", "+00:00")).astimezone(LOCAL_TZ)
                if dt > now_local + datetime.timedelta(minutes=1):
                    continue
                if not hora:
                    hora = dt.strftime("%H:%M")
            except Exception:
                pass
        formatted_items.append({**item, "time": hora or now_local.strftime("%H:%M")})

    return {
        "items": formatted_items[: max(1, min(int(limit or 30), 100))],
        "summary": {"abertas": abertas, "comerciais": comerciais, "emergenciais": emergenciais},
        "source": "json",
    }


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
    if not _durable_cache_store.enabled:
        return None
    return _team_file_repository.load_daily(normalize_team_key(team_key), day) or None

def get_rotalog_team_daily_today(team_key: str) -> dict[str, typing.Any] | None:
    day = datetime.datetime.now(LOCAL_TZ).date().isoformat()
    return get_rotalog_team_daily(team_key, day)

def _hydrate_durable_cache_once() -> None:
    """Hidrata snapshots e índice uma vez; falhas no GCS não interrompem a raspagem."""
    with _durable_cache_lock:
        if _durable_cache_state["hydrated"]:
            return
        local_snapshot = _local_cache.snapshot()
        if not _durable_cache_store.enabled:
            _durable_cache_state.update({"hydrated": True, "source": "local" if local_snapshot else "disabled"})
            return
        try:
            remote_payload = _durable_cache_store.load()
            _durable_cache_state["reads"] += 1
            remote_snapshots = remote_payload.get("snapshots") if isinstance(remote_payload.get("snapshots"), dict) else None
            if remote_snapshots is None:
                # Compatibilidade com o primeiro formato, que continha somente snapshots.
                remote_snapshots = remote_payload
            if not local_snapshot and remote_snapshots:
                _local_cache.replace(remote_snapshots)
            equipment_index = remote_payload.get("equipmentIndex")
            team_docs = remote_payload.get("teamDocs")
            remote_feed = remote_payload.get("activityFeed")
            if isinstance(remote_feed, list):
                _json_activity_feed[:] = [item for item in remote_feed if isinstance(item, dict)][:30]
            if isinstance(equipment_index, dict) and equipment_index:
                _equipment_index_cache["data"] = equipment_index
                _equipment_index_cache["team_docs"] = team_docs if isinstance(team_docs, dict) else {}
                _equipment_index_cache["loaded_at"] = time.monotonic()
            source = "gcs" if remote_payload else "gcs_empty"
            _durable_cache_state.update({"hydrated": True, "source": source})
        except Exception as exc:
            logger.warning("Não foi possível hidratar o cache ROTALOG no GCS: %s", exc)
            _durable_cache_state.update({"hydrated": True, "source": "gcs_error"})

def _persist_durable_cache() -> bool:
    if not _durable_cache_store.enabled:
        return False
    try:
        _durable_cache_store.save({
            "version": 2,
            "updatedAtIso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "snapshots": _local_cache.snapshot(),
            "equipmentIndex": _equipment_index_cache.get("data") or {},
            "teamDocs": _equipment_index_cache.get("team_docs") or {},
            "activityFeed": _json_activity_feed[:30],
        })
        _durable_cache_state["writes"] += 1
        _durable_cache_state["equipment_loaded_from_firestore"] = False
        return True
    except Exception as exc:
        logger.warning("Não foi possível persistir o cache ROTALOG no GCS: %s", exc)
        return False


def _extract_clean_member_names(data: dict[str, typing.Any]) -> list[str]:
    names = []
    raw_list = []
    for key in ("members", "eletricistas", "participantes", "membersSnapshot"):
        val = data.get(key)
        if isinstance(val, list):
            raw_list.extend(val)

    for item in raw_list:
        if isinstance(item, str):
            cleaned = re.sub(r"^\d+\s*[-_]\s*", "", item.strip())
            cleaned = re.sub(r"\(\d+\)", "", cleaned).strip().upper()
            if cleaned:
                names.append(cleaned)
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("nome") or "").strip().upper()
            if name:
                names.append(name)
    return names


def _get_equipment_identifier_index(db) -> dict[str, str]:
    """Carrega uma vez por hora a relação CA/MA/LO/CB/PG e integrantes -> equipe."""
    now = time.monotonic()
    cached = _equipment_index_cache.get("data") or {}
    if cached and now - float(_equipment_index_cache.get("loaded_at") or 0) < _EQUIPMENT_INDEX_TTL_SECONDS:
        return cached

    index: dict[str, str] = {}
    team_docs: dict[str, dict[str, typing.Any]] = {}
    for snap in db.collection("dds_teams").stream():
        _durable_cache_state["equipment_firestore_reads"] += 1
        team_key = snap.id.upper()
        data = snap.to_dict() or {}
        team_docs[team_key] = data

        # 1. Identificadores de equipamento e veículos (CA, MA, LO, CB, PG, etc.)
        identifiers = set()
        equipment = data.get("equipment") if isinstance(data.get("equipment"), dict) else {}
        tablet = equipment.get("tablet") if isinstance(equipment.get("tablet"), dict) else {}
        if isinstance(tablet, dict) and tablet.get("identifier"):
            identifiers.add(str(tablet.get("identifier")))

        for field_key in ("tablet", "identificador", "patrimonio", "veiculo", "placa", "equipamento"):
            val = data.get(field_key)
            if isinstance(val, str):
                identifiers.add(val)
            elif isinstance(val, dict) and val.get("identifier"):
                identifiers.add(str(val.get("identifier")))

        for raw_id in identifiers:
            clean_id = str(raw_id).strip().upper().replace(" ", "")
            if clean_id:
                if clean_id not in index:
                    index[clean_id] = team_key
                from bdo.services.rotalog_tempo_real_service import _extract_numeric_tablet_id
                numeric_part = _extract_numeric_tablet_id(clean_id)
                if numeric_part and f"NUMERIC_TABLET:{numeric_part}" not in index:
                    index[f"NUMERIC_TABLET:{numeric_part}"] = team_key

        # 2. Integrantes / Eletricistas da equipe para fallback por nome
        member_names = _extract_clean_member_names(data)
        for name in member_names:
            name_clean = re.sub(r"[^A-Z0-9\s]", "", name).strip()
            if name_clean:
                index[f"MEMBER_NAME:{name_clean}"] = team_key

    _equipment_index_cache["data"] = index
    _equipment_index_cache["team_docs"] = team_docs
    _equipment_index_cache["loaded_at"] = now
    _durable_cache_state["equipment_loaded_from_firestore"] = True
    logger.info("Índice de equipamentos e integrantes carregado: %s relações.", len(index))
    return index


def get_firestore_client():
    global _firestore_db
    if _firestore_db is not None:
        return _firestore_db

    if not firebase_admin._apps:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        config_path = os.path.join(root_dir, "firebase_config.json")

        if not os.path.exists(config_path):
            config_path = os.path.join(os.path.dirname(__file__), "..", "firebase_config.json")

        if os.path.exists(config_path):
            cred = credentials.Certificate(config_path)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()

    _firestore_db = firestore.client()
    return _firestore_db


def normalize_team_key(raw: str) -> str:
    return re.sub(r"[^A-Z0-9_-]", "_", raw.strip().upper())


def _calcular_fingerprint(eq: dict[str, typing.Any]) -> str:
    """
    Gera um hash MD5 único baseado nas propriedades chaves de estado e SSs da equipe.
    Utilizado para detectar se houve alteração real antes de gravar no Firestore.
    """
    payload_resumido = {
        "codigo": eq.get("equipe_codigo"),
        "estado": eq.get("estado_consolidado"),
        "inicio_ms": eq.get("turno", {}).get("inicio_ms"),
        "fim_ms": eq.get("turno", {}).get("fim_ms"),
        "intervalo_inicio": eq.get("intervalo", {}).get("inicio_ms"),
        "atividade": eq.get("atividade_atual"),
        "bdo": eq.get("bdo_list", []),
        "ss_andamento": eq.get("ss_em_andamento"),
        "ss_executadas": eq.get("ss_executadas"),
        "ss_pendentes": eq.get("ss_pendentes", []),
    }
    raw_bytes = json.dumps(payload_resumido, sort_keys=True).encode("utf-8")
    return hashlib.md5(raw_bytes).hexdigest()


def _extrair_timestamp_dds(dds_data: dict[str, typing.Any]) -> int:
    """Retorna o timestamp em milissegundos da última alteração do DDS."""
    if not dds_data:
        return 0

    if dds_data.get("clientUpdatedAtMs"):
        return int(dds_data["clientUpdatedAtMs"])

    if dds_data.get("lastEventAtClientMs"):
        return int(dds_data["lastEventAtClientMs"])

    iso_str = dds_data.get("updatedAtIso")
    if iso_str:
        try:
            dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1000)
        except Exception:
            pass

    return 0


def _extrair_timestamp_rotalog(rotalog_dict: dict[str, typing.Any]) -> int:
    """Retorna o timestamp em milissegundos do evento mais recente do Rotalog."""
    timestamps = []
    turno = rotalog_dict.get("turno", {})
    intervalo = rotalog_dict.get("intervalo", {})

    if turno.get("fim_ms"):
        timestamps.append(int(turno["fim_ms"]))
    if turno.get("inicio_ms"):
        timestamps.append(int(turno["inicio_ms"]))
    if intervalo.get("inicio_ms"):
        timestamps.append(int(intervalo["inicio_ms"]))

    for ss in rotalog_dict.get("ss_em_andamento", []):
        iso = ss.get("inicio_iso")
        if iso:
            try:
                dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
                timestamps.append(int(dt.timestamp() * 1000))
            except Exception:
                pass

    return max(timestamps) if timestamps else 0


def _event_id(team_key: str, fingerprint: str) -> str:
    """ID determinístico: uma repetição após falha não duplica o evento."""
    return f"{team_key}_{fingerprint}"


def _service_id(team_key: str, service: dict[str, typing.Any]) -> str:
    """ID estável da ocorrência; enriquecer o protocolo não recria o histórico."""
    identity = {
        "teamKey": team_key,
        "inicio": service.get("inicioIso") or service.get("inicioDeslocamento"),
        "sequencia": service.get("sequencia"),
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode("utf-8")
    ).hexdigest()[:32]
    return f"{team_key}_{digest}"


def _compact_event_changes(
    changes: dict[str, dict[str, typing.Any]],
) -> dict[str, dict[str, typing.Any]]:
    """Evita copiar listas inteiras de serviços para cada evento de auditoria."""
    compacted: dict[str, dict[str, typing.Any]] = {}
    list_fields = {"ssExecutadas", "ssEmAndamento", "ssPendentes"}
    for field, values in changes.items():
        if field in list_fields:
            old = values.get("anterior") or []
            new = values.get("novo") or []
            compacted[field] = {
                "quantidadeAnterior": len(old),
                "quantidadeNova": len(new),
            }
        else:
            compacted[field] = values
    return compacted


def _deve_aplicar_estado_rotalog(
    estado_rotalog: str,
    rotalog_ms: int,
    dds_data: dict[str, typing.Any],
    dds_exists: bool,
    forcar: bool = False,
) -> bool:
    if estado_rotalog == "DESCONHECIDO":
        return False
    if not dds_exists:
        return True

    dds_ms = _extrair_timestamp_dds(dds_data)
    ultimo_gravador_foi_rotalog = (
        str(dds_data.get("deviceIdLastWriter") or "").upper() in ("ROTALOG_AUTO_SYNC", "ADMIN_FECHAR_TODOS")
    )
    if not ultimo_gravador_foi_rotalog and dds_ms > rotalog_ms:
        return False

    estado_dds = str(dds_data.get("estado") or "").strip().upper()

    # Se Rotalog detectou ABERTO ou INTERVALO e no DDS o turno está FECHADO, reabre automaticamente
    if estado_rotalog in ("ABERTO", "INTERVALO") and estado_dds == "FECHADO":
        return True

    if rotalog_ms > dds_ms:
        return True

    if forcar and ultimo_gravador_foi_rotalog:
        return True
    return bool(
        ultimo_gravador_foi_rotalog
        and estado_dds != estado_rotalog
        and rotalog_ms >= dds_ms
    )

def _build_team_base_payload(
    eq: dict[str, typing.Any],
    team_key: str,
    eq_codigo: str,
    current_team_data: dict[str, typing.Any],
) -> dict[str, typing.Any]:
    """Retorna somente campos de dds_teams cujo valor realmente mudou."""
    payload: dict[str, typing.Any] = {}
    equipamento_id = eq.get("identificador_equipamento")
    if equipamento_id:
        desired_tablet = {
            "identifier": equipamento_id,
            "kind": "tablet",
            "label": "Tablet",
        }
        current_equipment = current_team_data.get("equipment")
        current_tablet = current_equipment.get("tablet") if isinstance(current_equipment, dict) else None
        desired_fields = {
            "currentTablet": equipamento_id,
            "rotalogTablet": equipamento_id,
            "tablet": equipamento_id,
        }
        for field, desired_value in desired_fields.items():
            if current_team_data.get(field) != desired_value:
                payload[field] = desired_value
        if current_tablet != desired_tablet:
            payload["equipment"] = {"tablet": desired_tablet}

    is_open = eq.get("estado_consolidado") in (
        "ABERTO", "INTERVALO", "DESLOCAMENTO_ESPECIAL"
    ) or bool(eq.get("turno", {}).get("aberto"))
    if is_open:
        desired_active_fields = {
            "active": True,
            "teamKey": team_key,
            "equipe": eq_codigo,
            "deactivatedReason": None,
            "reactivatedBy": "ROTALOG_AUTO_SYNC",
        }
        for field, desired_value in desired_active_fields.items():
            if current_team_data.get(field) != desired_value:
                payload[field] = desired_value
    return payload

def _build_rotalog_document(
    eq: dict[str, typing.Any],
    empresa: str,
    team_key: str,
    timestamp_iso: str,
    fila_counts: dict[str, int],
) -> dict[str, typing.Any]:
    return {
        "empresa": empresa,
        "equipe": eq["equipe_codigo"],
        "teamKey": team_key,
        "groupRaw": eq["group_raw"],
        "veiculo": eq["veiculo"],
        "identificadorEquipamento": eq.get("identificador_equipamento"),
        "origemResolucaoEquipe": eq.get("origem_resolucao"),
        "colaborador": eq["colaborador"],
        "statusConexao": eq["status_conexao"],
        "isOnline": eq["is_online"],
        "estadoConsolidado": eq["estado_consolidado"],
        "turno": eq["turno"],
        "intervalo": eq["intervalo"],
        "intervalos": eq.get("intervalos") or [],
        "atividadeAtual": eq["atividade_atual"],
        "bdoList": eq["bdo_list"],
        "ssExecutadasCount": len(eq["ss_executadas"]),
        "ssExecutadas": eq["ss_executadas"],
        "ssEmAndamento": eq["ss_em_andamento"],
        "ssPendentesCount": len(eq["ss_pendentes"]),
        "ssPendentesEmergenciaCount": fila_counts.get("emergencia", 0),
        "ssPendentesComercialCount": fila_counts.get("comercial", 0),
        "ssPendentes": eq["ss_pendentes"],
        "eventTimestampMs": _extrair_timestamp_rotalog(eq),
        "updatedAtIso": timestamp_iso,
    }


def _event_datetime_iso(value: typing.Any, fallback_iso: str) -> str | None:
    """Normaliza ms, ISO ou HH:mm usando o dia local da detecção como referência."""
    if value in (None, ""):
        return None
    try:
        fallback = datetime.datetime.fromisoformat(str(fallback_iso).replace("Z", "+00:00"))
        if fallback.tzinfo is None:
            fallback = fallback.replace(tzinfo=datetime.timezone.utc)
        fallback_local = fallback.astimezone(LOCAL_TZ)
        if isinstance(value, (int, float)) or str(value).strip().isdigit():
            numeric = float(value)
            seconds = numeric / 1000 if numeric > 100_000_000_000 else numeric
            return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc).astimezone(LOCAL_TZ).isoformat()
        raw = str(value).strip()
        if re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", raw):
            parts = [int(part) for part in raw.split(":")]
            candidate = datetime.datetime.combine(
                fallback_local.date(),
                datetime.time(parts[0], parts[1], parts[2] if len(parts) > 2 else 0),
                tzinfo=LOCAL_TZ,
            )
            # Uma hora noturna detectada logo após a meia-noite pertence ao dia anterior.
            if candidate > fallback_local + datetime.timedelta(hours=2):
                candidate -= datetime.timedelta(days=1)
            return candidate.isoformat()
        parsed = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LOCAL_TZ)
        return parsed.astimezone(LOCAL_TZ).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _rotalog_change_activity_at(
    previous: dict[str, typing.Any],
    current: dict[str, typing.Any],
    fallback_iso: str,
) -> str:
    """Escolhe o horário real do evento; usa a detecção somente como fallback."""
    old_state = str(previous.get("estadoConsolidado") or "").upper()
    new_state = str(current.get("estadoConsolidado") or "").upper()
    candidates: list[typing.Any] = []

    if old_state != new_state:
        turno = current.get("turno") or {}
        intervalo = current.get("intervalo") or {}
        if new_state == "FECHADO":
            candidates.extend((turno.get("fim_iso"), turno.get("fimIso"), turno.get("fim_ms")))
        elif new_state == "INTERVALO":
            candidates.extend((intervalo.get("inicioIso"), intervalo.get("inicio_iso"), intervalo.get("inicio_ms")))
        elif new_state == "ABERTO":
            candidates.extend((turno.get("inicio_iso"), turno.get("inicioIso"), turno.get("inicio_ms")))

    old_activity = previous.get("atividadeAtual") or {}
    new_activity = current.get("atividadeAtual") or {}
    if new_activity and old_activity != new_activity:
        status = str(new_activity.get("status") or "").upper()
        if status == "DESLOCAMENTO":
            candidates.extend((new_activity.get("inicioDeslocamento"), new_activity.get("inicioIso")))
        elif status == "EXECUCAO":
            candidates.extend((new_activity.get("inicioExecucao"), new_activity.get("inicioIso")))
        elif status == "CONCLUSAO":
            candidates.extend((new_activity.get("termino"), new_activity.get("fimIso"), new_activity.get("retorno")))
        else:
            candidates.append(new_activity.get("inicioIso"))

    if len(current.get("ssExecutadas") or []) != len(previous.get("ssExecutadas") or []):
        completed = (current.get("ssExecutadas") or [])[-1:]
        if completed:
            candidates.extend((completed[0].get("termino"), completed[0].get("fimIso"), completed[0].get("retorno")))

    now_local = datetime.datetime.now(LOCAL_TZ)
    for candidate in candidates:
        resolved = _event_datetime_iso(candidate, fallback_iso)
        if resolved:
            try:
                res_dt = datetime.datetime.fromisoformat(resolved).astimezone(LOCAL_TZ)
                if res_dt <= now_local + datetime.timedelta(minutes=1):
                    return res_dt.isoformat()
            except Exception:
                pass
    return now_local.isoformat()

def _describe_rotalog_change(
    previous: dict[str, typing.Any],
    current: dict[str, typing.Any],
    changes: dict[str, dict[str, typing.Any]],
) -> str | None:
    team_key = str(current.get("teamKey") or current.get("equipe") or "EQUIPE").upper()
    old_state = str(previous.get("estadoConsolidado") or "DESCONHECIDO").upper()
    new_state = str(current.get("estadoConsolidado") or "DESCONHECIDO").upper()
    if old_state != new_state:
        return f"{team_key} - {old_state} → {new_state}"

    old_activity = previous.get("atividadeAtual") or {}
    new_activity = current.get("atividadeAtual") or {}
    old_status = str(old_activity.get("status") or "").upper()
    new_status = str(new_activity.get("status") or "").upper()
    service_type = new_activity.get("tipo") or old_activity.get("tipo") or "serviço"
    if new_activity and (old_activity != new_activity):
        return f"{team_key} - {service_type} - {new_status or 'ATUALIZADO'}"

    # Mudanças exclusivas na fila não entram no feed; seguimos avaliando
    # alterações mais relevantes que possam ter ocorrido no mesmo ciclo.
    old_running = len(previous.get("ssEmAndamento") or [])
    new_running = len(current.get("ssEmAndamento") or [])
    if old_running != new_running:
        if old_running > 0 and new_running == 0:
            return f"{team_key} - SEM EXECUÇÃO"
        return f"{team_key} - Em andamento: {old_running} → {new_running}"
    old_done = len(previous.get("ssExecutadas") or [])
    new_done = len(current.get("ssExecutadas") or [])
    if old_done != new_done:
        return f"{team_key} - Executados: {old_done} → {new_done}"
    return None

def _persistir_somente_json(
    equipas: list[dict[str, typing.Any]],
    empresa: str,
    timestamp_iso: str,
    fila_por_equipe: dict[str, dict[str, int]],
    *,
    gcs_reads_before: int,
    gcs_writes_before: int,
    firestore_reads: int,
) -> dict[str, typing.Any]:
    updates: dict[str, dict[str, typing.Any]] = {}
    feed_items: list[dict[str, typing.Any]] = []
    skipped = 0
    for eq in equipas:
        eq_codigo = str(eq.get("equipe_codigo") or "").strip().upper()
        if not eq_codigo:
            continue
        team_key = normalize_team_key(eq_codigo)
        current = _build_rotalog_document(
            eq,
            empresa,
            team_key,
            timestamp_iso,
            fila_por_equipe.get(eq_codigo, {}),
        )
        previous = _local_cache.get(team_key)
        needs_full_upgrade = not previous or not previous.get("teamKey")
        changes = changed_fields(previous, current)
        if not needs_full_upgrade and not changes:
            skipped += 1
            continue
        current["version"] = int((previous or {}).get("version") or 0) + 1
        updates[team_key] = current
        if previous and changes:
            activity_at = _rotalog_change_activity_at(previous, current, timestamp_iso)
            description = _describe_rotalog_change(previous, current, changes)
            if description:
                try:
                    act_dt = datetime.datetime.fromisoformat(activity_at).astimezone(LOCAL_TZ)
                    hora_str = act_dt.strftime("%H:%M")
                except Exception:
                    hora_str = datetime.datetime.now(LOCAL_TZ).strftime("%H:%M")
                feed_items.append({
                    "eventId": f"{team_key}_{hashlib.md5((activity_at + description).encode('utf-8')).hexdigest()[:12]}",
                    "empresa": empresa,
                    "teamKey": team_key,
                    "equipe": eq_codigo,
                    "source": "rotalog_json",
                    "label": description,
                    "time": hora_str,
                    "activityAt": activity_at,
                })

    daily_file_writes = 0
    scheduled_file_writes = 0
    if updates:
        _local_cache.set_many(updates)
        local_day = datetime.datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00")).astimezone(LOCAL_TZ).date().isoformat()
        if _durable_cache_store.enabled:
            for document in updates.values():
                try:
                    _team_file_repository.merge_and_save_daily(document, local_day)
                    daily_file_writes += 1
                except Exception as exc:
                    logger.warning("Não foi possível persistir arquivos da equipe %s: %s", document.get("teamKey"), exc)
    if feed_items:
        combined = feed_items + _json_activity_feed
        seen = set()
        deduplicated = []
        for item in sorted(combined, key=lambda entry: str(entry.get("activityAt") or ""), reverse=True):
            event_id = item.get("eventId")
            if event_id in seen:
                continue
            seen.add(event_id)
            deduplicated.append(item)
        _json_activity_feed[:] = deduplicated[:30]
    should_persist = bool(updates) or bool(_durable_cache_state.get("equipment_loaded_from_firestore"))
    persisted = _persist_durable_cache() if should_persist else False
    monthly_result = {"executed": False, "reason": "storage_disabled"}
    turn_check_result = {"executed": False, "reason": "storage_disabled"}
    if _durable_cache_store.enabled:
        try:
            turn_check_result = _team_file_repository.record_daily_turn_check(len(equipas))
            if turn_check_result.get("executed"):
                scheduled_file_writes += 1
        except Exception as exc:
            logger.warning("Falha ao registrar checagem diária dos turnos: %s", exc)
            turn_check_result = {"executed": False, "reason": "error", "error": str(exc)}
    if _durable_cache_store.enabled:
        try:
            monthly_result = _team_file_repository.consolidate_month_once_per_day()
            if monthly_result.get("executed"):
                scheduled_file_writes += 3
        except Exception as exc:
            logger.warning("Falha na consolidação mensal ROTALOG: %s", exc)
            monthly_result = {"executed": False, "reason": "error", "error": str(exc)}
    fila_emergencia = sum(item["emergencia"] for item in fila_por_equipe.values())
    fila_comercial = sum(item["comercial"] for item in fila_por_equipe.values())
    return {
        "status": "success",
        "persistenceMode": "json",
        "updatedAtIso": timestamp_iso,
        "totalEquipesRotalog": len(equipas),
        "equipesAtualizadasJson": len(updates),
        "ignoradosSemMudanca": skipped,
        "servicosPendentesTotal": fila_emergencia + fila_comercial,
        "servicosPendentesEmergencia": fila_emergencia,
        "servicosPendentesComercial": fila_comercial,
        "servicosPendentesPorEquipe": fila_por_equipe,
        "aplicadosNoDdsRotalogMaisRecente": 0,
        "preservadosDdsMaisRecente": 0,
        "turnosRotalogSalvos": 0,
        "eventosHistoricosSalvos": 0,
        "servicosFinalizadosSalvos": 0,
        "leiturasFirestore": firestore_reads,
        "gravacoesFirestore": 0,
        "cacheDuravelOrigem": _durable_cache_state.get("source"),
        "leiturasCloudStorage": int(_durable_cache_state.get("reads", 0)) - gcs_reads_before,
        "gravacoesCloudStorage": int(_durable_cache_state.get("writes", 0)) - gcs_writes_before,
        "cacheDuravelPersistidoNesteCiclo": persisted,
        "gravacoesJsonDiario": daily_file_writes,
        "gravacoesRotinasAgendadas": scheduled_file_writes,
        "gravacoesArquivosEquipe": daily_file_writes + scheduled_file_writes,
        "gravacoesCloudStorageTotal": (
            int(_durable_cache_state.get("writes", 0)) - gcs_writes_before
            + daily_file_writes
            + scheduled_file_writes
        ),
        "consolidacaoMensal": monthly_result,
        "checagemDiariaTurnos": turn_check_result,
    }

def _executar_sincronizacao_rotalog(
    empresa: str = "ChicoEletro",
    forcar: bool = False,
    equipes_filtro: set[str] | None = None,
) -> dict[str, typing.Any]:
    """
    Executa a raspagem do Rotalog Tempo Real, lê os dados do DDS no Firestore,
    compara recência e altera o Firestore SOMENTE SE HOUVER MUDANÇA (Diff Hash Check).
    """
    db = get_firestore_client()
    gcs_reads_before = int(_durable_cache_state.get("reads", 0))
    gcs_writes_before = int(_durable_cache_state.get("writes", 0))
    _hydrate_durable_cache_once()
    timestamp_now = datetime.datetime.now(datetime.timezone.utc)
    timestamp_iso = timestamp_now.isoformat()

    logger.info("Iniciando captura Rotalog Tempo Real...")
    equipment_reads_before = int(_durable_cache_state.get("equipment_firestore_reads", 0))
    equipment_index = _get_equipment_identifier_index(db)
    equipment_firestore_reads = int(_durable_cache_state.get("equipment_firestore_reads", 0)) - equipment_reads_before
    equipas = extrair_dados_tempo_real(identificador_para_equipe=equipment_index)
    logger.info(f"Rotalog extraído: {len(equipas)} equipes capturadas.")
    fila_por_equipe: dict[str, dict[str, int]] = {}
    for eq in equipas:
        codigo = str(eq.get("equipe_codigo") or "").strip().upper()
        pendentes = eq.get("ss_pendentes") or []
        emergencia = sum(1 for item in pendentes if str(item.get("tipo") or "").strip().upper() == "EMERGENCIA")
        comercial = sum(1 for item in pendentes if str(item.get("tipo") or "").strip().upper() == "COMERCIAL")
        fila_por_equipe[codigo] = {
            "total": emergencia + comercial,
            "emergencia": emergencia,
            "comercial": comercial,
        }
    fila_emergencia = sum(item["emergencia"] for item in fila_por_equipe.values())
    fila_comercial = sum(item["comercial"] for item in fila_por_equipe.values())
    fila_total = fila_emergencia + fila_comercial
    logger.info(
        "Fila ROTALOG: %s serviço(s) pendente(s) — %s emergência e %s comercial.",
        fila_total,
        fila_emergencia,
        fila_comercial,
    )
    if _ROTALOG_PERSISTENCE_MODE != "firestore":
        return _persistir_somente_json(
            equipas,
            empresa,
            timestamp_iso,
            fila_por_equipe,
            gcs_reads_before=gcs_reads_before,
            gcs_writes_before=gcs_writes_before,
            firestore_reads=equipment_firestore_reads,
        )

    rotalog_updated = 0
    dds_applied = 0
    dds_preserved = 0
    skipped_unchanged = 0
    history_events = 0
    completed_services_saved = 0
    firestore_reads = equipment_firestore_reads
    firestore_writes = 0
    durable_cache_dirty = False

    batch = db.batch()
    op_count = 0
    pending_cache: dict[str, dict[str, typing.Any]] = {}
    pending_team_cache: dict[str, dict[str, typing.Any]] = {}

    def commit_batch() -> None:
        nonlocal batch, op_count, pending_cache, pending_team_cache, firestore_writes, durable_cache_dirty
        if op_count == 0:
            return
        batch.commit()
        firestore_writes += op_count
        if pending_cache:
            _local_cache.set_many(pending_cache)
            durable_cache_dirty = True
        cached_team_docs = _equipment_index_cache.get("team_docs")
        if pending_team_cache and isinstance(cached_team_docs, dict):
            for cached_team_key, updates in pending_team_cache.items():
                cached_team_docs.setdefault(cached_team_key, {}).update(updates)
        batch = db.batch()
        op_count = 0
        pending_cache = {}
        pending_team_cache = {}

    for eq in equipas:
        eq_codigo = eq["equipe_codigo"].strip().upper()
        if not eq_codigo:
            continue

        team_key = normalize_team_key(eq_codigo)
        if equipes_filtro and team_key not in equipes_filtro:
            continue
        current_fingerprint = _calcular_fingerprint(eq)

        doc_rotalog = {
            "empresa": empresa,
            "equipe": eq_codigo,
            "teamKey": team_key,
            "groupRaw": eq["group_raw"],
            "veiculo": eq["veiculo"],
            "identificadorEquipamento": eq.get("identificador_equipamento"),
            "origemResolucaoEquipe": eq.get("origem_resolucao"),
            "colaborador": eq["colaborador"],
            "statusConexao": eq["status_conexao"],
            "isOnline": eq["is_online"],
            "estadoConsolidado": eq["estado_consolidado"],
            "turno": eq["turno"],
            "intervalo": eq["intervalo"],
            "intervalos": eq.get("intervalos") or [],
            "atividadeAtual": eq["atividade_atual"],
            "bdoList": eq["bdo_list"],
            "ssExecutadasCount": len(eq["ss_executadas"]),
            "ssExecutadas": eq["ss_executadas"],
            "ssEmAndamento": eq["ss_em_andamento"],
            "ssPendentesCount": len(eq["ss_pendentes"]),
            "ssPendentesEmergenciaCount": fila_por_equipe.get(eq_codigo, {}).get("emergencia", 0),
            "ssPendentesComercialCount": fila_por_equipe.get(eq_codigo, {}).get("comercial", 0),            "ssPendentes": eq["ss_pendentes"],
            "updatedAtIso": timestamp_iso
        }

        current_snapshot = compact_snapshot(doc_rotalog)
        previous_snapshot = _local_cache.get(team_key)

        # Cache vazio: uma única leitura recupera o último snapshot persistido.
        if previous_snapshot is None:
            existing_rotalog = db.collection("turnos_rotalog").document(team_key).get()
            firestore_reads += 1
            if existing_rotalog.exists:
                previous_snapshot = compact_snapshot(existing_rotalog.to_dict() or {})
                if not forcar and not changed_fields(previous_snapshot, current_snapshot):
                    _local_cache.set(team_key, current_snapshot)
                    durable_cache_dirty = True
                    skipped_unchanged += 1
                    continue

        changes = changed_fields(previous_snapshot, current_snapshot)
        if not forcar and not changes:
            skipped_unchanged += 1
            continue

        # O DDS é consultado apenas quando houve mudança real no Rotalog.
        ref_dds_app = db.collection("turno").document(empresa).collection("equipes").document(team_key)
        dds_doc = ref_dds_app.get()
        firestore_reads += 1
        dds_data = dds_doc.to_dict() if dds_doc.exists else {}

        # Salvar documento em /turnos_rotalog/{team_key}
        ref_rotalog = db.collection("turnos_rotalog").document(team_key)
        batch.set(ref_rotalog, doc_rotalog, merge=True)
        op_count += 1
        rotalog_updated += 1

        # Um único evento compacto por mudança detectada. Uma sincronização
        # forçada sem diff não cria auditoria artificial.
        if changes:
            event_ref = db.collection("rotalog_eventos_tempo_real").document(
                _event_id(team_key, current_fingerprint)
            )
            event_doc = {
                "empresa": empresa,
                "equipe": eq_codigo,
                "teamKey": team_key,
                "origem": "ROTALOG",
                "alteracoes": _compact_event_changes(changes),
                "ocorridoEmMs": _extrair_timestamp_rotalog(eq) or None,
                "detectadoEm": timestamp_now,
                "detectadoEmIso": timestamp_iso,
                "fingerprint": current_fingerprint,
            }
            batch.set(event_ref, event_doc, merge=False)
            op_count += 1
            history_events += 1

        # Serviços concluídos são materializados uma única vez para consultas históricas.
        previous_service_ids = {
            _service_id(team_key, service)
            for service in ((previous_snapshot or {}).get("ssExecutadas") or [])
        }
        for service in eq.get("ss_executadas", []):
            service_id = _service_id(team_key, service)
            if service_id in previous_service_ids:
                continue
            service_doc = {
                **service,
                "empresa": empresa,
                "equipe": eq_codigo,
                "teamKey": team_key,
                "statusAtual": "FINALIZADO",
                "origem": "ROTALOG",
                "primeiraLeituraEm": timestamp_now,
                "ultimaLeituraEm": timestamp_now,
            }
            batch.set(
                db.collection("rotalog_servicos").document(service_id),
                service_doc,
                merge=True,
            )
            op_count += 1
            completed_services_saved += 1

        rotalog_ms = _extrair_timestamp_rotalog(eq)
        dds_ms = _extrair_timestamp_dds(dds_data)

        # Se a equipe está com o turno aberto ou em atividade no Rotalog, força active = True
        is_turno_aberto_rotalog = eq["estado_consolidado"] in ("ABERTO", "INTERVALO", "DESLOCAMENTO_ESPECIAL") or bool(eq.get("turno", {}).get("aberto"))

        # A leitura de dds_teams usada para montar o índice também alimenta este
        # diff, evitando tanto uma leitura adicional quanto writes idênticos.
        ref_team_base = db.collection("dds_teams").document(team_key)
        cached_team_docs = _equipment_index_cache.get("team_docs")
        current_team_data = cached_team_docs.get(team_key, {}) if isinstance(cached_team_docs, dict) else {}
        team_base_payload = _build_team_base_payload(eq, team_key, eq_codigo, current_team_data)
        equipamento_id = eq.get("identificador_equipamento")
        cached_index = _equipment_index_cache.get("data")
        if equipamento_id and isinstance(cached_index, dict):
            cached_index[equipamento_id] = team_key

        if team_base_payload:
            batch.set(ref_team_base, team_base_payload, merge=True)
            op_count += 1
            pending_team_cache[team_key] = team_base_payload

        # 2. Análise de Recência: Se Rotalog for MAIS RECENTE que o DDS
        deve_aplicar_rotalog = _deve_aplicar_estado_rotalog(
            eq["estado_consolidado"],
            rotalog_ms,
            dds_data,
            dds_doc.exists,
            forcar=forcar,
        )
        if deve_aplicar_rotalog:
            novo_estado_dds = {
                "empresa": empresa,
                "equipe": eq_codigo,
                "estado": eq["estado_consolidado"],
                "isOpen": is_turno_aberto_rotalog,
                "openedAtClientMs": eq["turno"]["inicio_ms"] or dds_data.get("openedAtClientMs"),
                "closedAtClientMs": eq["turno"]["fim_ms"] if eq["estado_consolidado"] == "FECHADO" else None,
                "clientUpdatedAtMs": rotalog_ms,
                "serverUpdatedAt": firestore.SERVER_TIMESTAMP,
                "updatedAtIso": timestamp_iso,
                "deviceIdLastWriter": "ROTALOG_AUTO_SYNC",
                "bdoList": eq["bdo_list"],
                "rotalogSnapshot": doc_rotalog,
                "rotalogFingerprint": current_fingerprint,
                "origemAtualizacao": "ROTALOG_MAIS_RECENTE"
            }
            atividade = eq.get("atividade_atual") or {}
            atividade_status = atividade.get("status")
            novo_estado_dds["atividadeStatus"] = atividade_status
            novo_estado_dds["monitorStatus"] = (
                "EXECUTANDO" if atividade_status == "EXECUCAO" else
                atividade_status or eq["estado_consolidado"]
            )
            if is_turno_aberto_rotalog:
                novo_estado_dds["active"] = True

            batch.set(ref_dds_app, novo_estado_dds, merge=True)

            # [OTIMIZAÇÃO FIREBASE]: Gravação duplicada na coleção legada 'empresas/turnos_estado' desativada.
            # A coleção oficial e ativa usada por todo o App e Web Monitor é 'turno/ChicoEletro/equipes'.
            # Caso precise reativar a gravação no caminho legado no futuro, desconmente a linha abaixo:
            # ref_dds_web = db.collection("empresas").document(empresa).collection("turnos_estado").document(team_key)
            # batch.set(ref_dds_web, novo_estado_dds, merge=True)

            dds_applied += 1
        else:
            update_payload = {
                "rotalogSnapshot": doc_rotalog,
                "rotalogFingerprint": current_fingerprint,
                "rotalogUpdatedAt": firestore.SERVER_TIMESTAMP,
                "origemAtualizacao": "DDS_MAIS_RECENTE"
            }
            atividade = eq.get("atividade_atual") or {}
            atividade_status = atividade.get("status")
            update_payload["atividadeStatusRotalog"] = atividade_status
            update_payload["monitorStatusRotalog"] = (
                "EXECUTANDO" if atividade_status == "EXECUCAO" else
                atividade_status or eq["estado_consolidado"]
            )
            if not dds_doc.exists:
                update_payload.update({
                    "empresa": empresa,
                    "equipe": eq_codigo,
                    "estado": "DESCONHECIDO",
                    "isOpen": False,
                    "updatedAtIso": timestamp_iso,
                })
            if is_turno_aberto_rotalog:
                update_payload["active"] = True

            batch.set(ref_dds_app, update_payload, merge=True)

            # [OTIMIZAÇÃO FIREBASE]: Gravação duplicada na coleção legada 'empresas/turnos_estado' desativada.
            # ref_dds_web = db.collection("empresas").document(empresa).collection("turnos_estado").document(team_key)
            # batch.set(ref_dds_web, update_payload, merge=True)

            dds_preserved += 1

        op_count += 1
        pending_cache[team_key] = current_snapshot

        if op_count >= 400:
            commit_batch()

    commit_batch()
    should_persist_durable_cache = (
        durable_cache_dirty
        or bool(_durable_cache_state.get("equipment_loaded_from_firestore"))
    )
    durable_cache_persisted = _persist_durable_cache() if should_persist_durable_cache else False

    return {
        "status": "success",
        "updatedAtIso": timestamp_iso,
        "totalEquipesRotalog": len(equipas),
        "servicosPendentesTotal": fila_total,
        "servicosPendentesEmergencia": fila_emergencia,
        "servicosPendentesComercial": fila_comercial,
        "servicosPendentesPorEquipe": fila_por_equipe,
        "turnosRotalogSalvos": rotalog_updated,
        "aplicadosNoDdsRotalogMaisRecente": dds_applied,
        "preservadosDdsMaisRecente": dds_preserved,
        "ignoradosSemMudanca": skipped_unchanged,
        "eventosHistoricosSalvos": history_events,
        "servicosFinalizadosSalvos": completed_services_saved,
        "leiturasFirestore": firestore_reads,
        "gravacoesFirestore": firestore_writes,
        "cacheDuravelOrigem": _durable_cache_state.get("source"),
        "leiturasCloudStorage": int(_durable_cache_state.get("reads", 0)) - gcs_reads_before,
        "gravacoesCloudStorage": int(_durable_cache_state.get("writes", 0)) - gcs_writes_before,
        "cacheDuravelPersistidoNesteCiclo": durable_cache_persisted,
    }


def executar_sincronizacao_rotalog(
    empresa: str = "ChicoEletro",
    forcar: bool = False,
    equipes_filtro: set[str] | None = None,
) -> dict[str, typing.Any]:
    """Garante uma única sincronização por processo, inclusive via endpoint manual."""
    if not _sync_execution_lock.acquire(blocking=False):
        return {
            "status": "skipped",
            "reason": "sync_already_running",
            "message": "Já existe uma sincronização do Rotalog em andamento.",
        }
    try:
        normalized_filter = (
            {normalize_team_key(value) for value in equipes_filtro}
            if equipes_filtro else None
        )
        return _executar_sincronizacao_rotalog(
            empresa=empresa,
            forcar=forcar,
            equipes_filtro=normalized_filter,
        )
    finally:
        _sync_execution_lock.release()


def get_dynamic_sync_interval_seconds(default_override: int | None = None) -> int:
    """
    Retorna o intervalo dinâmico de sincronização do Rotalog:
    - 3600s (1 hora) entre 22:00 e 05:50 (Noturno)
    - 590s (9 min e 50s) entre 05:50 e 22:00 (Diurno)
    """
    if default_override and default_override not in (300, 590):
        return default_override

    now = datetime.datetime.now()
    current_time = now.time()
    night_start = datetime.time(22, 0, 0)
    night_end = datetime.time(5, 50, 0)

    if current_time >= night_start or current_time < night_end:
        return 3600 # 1 hora na madrugada

    return 590 # 9m 50s durante o dia


class RotalogBackgroundScheduler:
    """
    Scheduler em background que executa a sincronização do Rotalog:
    - A cada 9m50s (590s) durante o dia (05:50 às 22:00)
    - A cada 1 hora (3600s) durante a noite (22:00 às 05:50)
    """
    def __init__(self, interval_seconds: int = 590, empresa: str = "ChicoEletro"):
        self.interval_seconds = interval_seconds
        self.empresa = empresa
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"RotalogBackgroundScheduler iniciado (intervalo dinâmico diurno/noturno).")

    def stop(self):
        self._running = False
        logger.info("RotalogBackgroundScheduler encerrado.")

    def _loop(self):
        time.sleep(5)
        while self._running:
            current_interval = get_dynamic_sync_interval_seconds(self.interval_seconds)
            try:
                logger.info(f"Executando sincronização periódica do Rotalog (próxima checagem em {current_interval // 60} min / {current_interval}s)...")
                res = executar_sincronizacao_rotalog(empresa=self.empresa)
                if isinstance(res, dict):
                    if res.get("persistenceMode") == "json":
                        logger.info(
                            "Sincronização JSON concluída: %s equipe(s) atualizada(s), %s sem mudança; "
                            "%s leituras e %s gravações Firestore; Cloud Storage: %s total "
                            "(%s diário(s), %s snapshot global, %s rotina(s) agendada(s)).",
                            res.get("equipesAtualizadasJson", 0),
                            res.get("ignoradosSemMudanca", 0),
                            res.get("leiturasFirestore", 0),
                            res.get("gravacoesFirestore", 0),
                            res.get("gravacoesCloudStorageTotal", 0),
                            res.get("gravacoesJsonDiario", 0),
                            res.get("gravacoesCloudStorage", 0),
                            res.get("gravacoesRotinasAgendadas", 0),
                        )
                    else:
                        logger.info(
                            "Sincronização concluída: %s aplicadas, %s DDS preservadas, %s sem mudança; "
                            "%s leituras e %s gravações Firestore "
                            "(%s snapshots, %s eventos, %s serviços finalizados).",
                            res.get("aplicadosNoDdsRotalogMaisRecente", 0),
                            res.get("preservadosDdsMaisRecente", 0),
                            res.get("ignoradosSemMudanca", 0),
                            res.get("leiturasFirestore", 0),
                            res.get("gravacoesFirestore", 0),
                            res.get("turnosRotalogSalvos", 0),
                            res.get("eventosHistoricosSalvos", 0),
                            res.get("servicosFinalizadosSalvos", 0),
                        )
            except Exception as e:
                logger.error(f"Erro no loop do RotalogBackgroundScheduler: {e}")

            for _ in range(current_interval):
                if not self._running:
                    break
                time.sleep(1)
