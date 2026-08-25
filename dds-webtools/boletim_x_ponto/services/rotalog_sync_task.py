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

from boletim_x_ponto.services.rotalog_tempo_real_service import extrair_dados_tempo_real
from boletim_x_ponto.services.rotalog_change_tracker import (
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
_equipment_index_cache: dict[str, typing.Any] = {"data": {}, "loaded_at": 0.0}
_EQUIPMENT_INDEX_TTL_SECONDS = 3600


def _get_equipment_identifier_index(db) -> dict[str, str]:
    """Carrega uma vez por hora a relação CA/MA/LO/CB/PG -> equipe."""
    now = time.monotonic()
    cached = _equipment_index_cache.get("data") or {}
    if cached and now - float(_equipment_index_cache.get("loaded_at") or 0) < _EQUIPMENT_INDEX_TTL_SECONDS:
        return cached

    index: dict[str, str] = {}
    for snap in db.collection("dds_teams").stream():
        data = snap.to_dict() or {}
        equipment = data.get("equipment") if isinstance(data.get("equipment"), dict) else {}
        tablet = equipment.get("tablet") if isinstance(equipment.get("tablet"), dict) else {}
        identifier = str(tablet.get("identifier") or "").strip().upper().replace(" ", "")
        if identifier and identifier not in index:
            index[identifier] = snap.id.upper()
    _equipment_index_cache["data"] = index
    _equipment_index_cache["loaded_at"] = now
    logger.info("Índice de equipamentos carregado: %s relações.", len(index))
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
    identity = {
        "teamKey": team_key,
        "protocolo": service.get("ssId") or service.get("protocoloBruto"),
        "tipo": service.get("tipo"),
        "inicio": service.get("inicioIso"),
        "fim": service.get("fimIso"),
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
    dds_ms = _extrair_timestamp_dds(dds_data)
    if not dds_exists or rotalog_ms > dds_ms:
        return True
    ultimo_gravador_foi_rotalog = (
        str(dds_data.get("deviceIdLastWriter") or "").upper() == "ROTALOG_AUTO_SYNC"
    )
    if forcar and ultimo_gravador_foi_rotalog:
        return True
    return bool(
        ultimo_gravador_foi_rotalog
        and dds_data.get("estado") != estado_rotalog
        and rotalog_ms >= dds_ms
    )


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
    timestamp_now = datetime.datetime.now(datetime.timezone.utc)
    timestamp_iso = timestamp_now.isoformat()

    logger.info("Iniciando captura Rotalog Tempo Real...")
    equipment_index = _get_equipment_identifier_index(db)
    equipas = extrair_dados_tempo_real(identificador_para_equipe=equipment_index)
    logger.info(f"Rotalog extraído: {len(equipas)} equipes capturadas.")

    rotalog_updated = 0
    dds_applied = 0
    dds_preserved = 0
    skipped_unchanged = 0
    history_events = 0
    completed_services_saved = 0
    firestore_reads = 0

    batch = db.batch()
    op_count = 0
    pending_cache: dict[str, dict[str, typing.Any]] = {}

    def commit_batch() -> None:
        nonlocal batch, op_count, pending_cache
        if op_count == 0:
            return
        batch.commit()
        if pending_cache:
            _local_cache.set_many(pending_cache)
        batch = db.batch()
        op_count = 0
        pending_cache = {}

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
            "atividadeAtual": eq["atividade_atual"],
            "bdoList": eq["bdo_list"],
            "ssExecutadasCount": len(eq["ss_executadas"]),
            "ssExecutadas": eq["ss_executadas"],
            "ssEmAndamento": eq["ss_em_andamento"],
            "ssPendentesCount": len(eq["ss_pendentes"]),
            "ssPendentes": eq["ss_pendentes"],
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

        if is_turno_aberto_rotalog:
            # Ativa no cadastro base dds_teams/{team_key} se estiver inativa
            ref_team_base = db.collection("dds_teams").document(team_key)
            batch.set(ref_team_base, {
                "active": True,
                "teamKey": team_key,
                "equipe": eq_codigo,
                "deactivatedReason": None,
                "reactivatedBy": "ROTALOG_AUTO_SYNC"
            }, merge=True)
            op_count += 1

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

            ref_dds_web = db.collection("empresas").document(empresa).collection("turnos_estado").document(team_key)
            batch.set(ref_dds_web, novo_estado_dds, merge=True)

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

            ref_dds_web = db.collection("empresas").document(empresa).collection("turnos_estado").document(team_key)
            batch.set(ref_dds_web, update_payload, merge=True)

            dds_preserved += 1

        op_count += 2
        pending_cache[team_key] = current_snapshot

        if op_count >= 400:
            commit_batch()

    commit_batch()

    return {
        "status": "success",
        "updatedAtIso": timestamp_iso,
        "totalEquipesRotalog": len(equipas),
        "turnosRotalogSalvos": rotalog_updated,
        "aplicadosNoDdsRotalogMaisRecente": dds_applied,
        "preservadosDdsMaisRecente": dds_preserved,
        "ignoradosSemMudanca": skipped_unchanged,
        "eventosHistoricosSalvos": history_events,
        "servicosFinalizadosSalvos": completed_services_saved,
        "leiturasFirestore": firestore_reads,
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


class RotalogBackgroundScheduler:
    """
    Scheduler em background que executa a sincronização do Rotalog a cada 5 minutos (300s).
    """
    def __init__(self, interval_seconds: int = 300, empresa: str = "ChicoEletro"):
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
        logger.info(f"RotalogBackgroundScheduler iniciado (checagem a cada {self.interval_seconds}s / {self.interval_seconds // 60}min).")

    def stop(self):
        self._running = False
        logger.info("RotalogBackgroundScheduler encerrado.")

    def _loop(self):
        time.sleep(5)
        while self._running:
            try:
                logger.info(f"Executando sincronização periódica do Rotalog ({self.interval_seconds // 60} min)...")
                res = executar_sincronizacao_rotalog(empresa=self.empresa)
                logger.info(f"Sincronização concluída com sucesso: {res['aplicadosNoDdsRotalogMaisRecente']} aplicadas, {res['ignoradosSemMudanca']} sem mudança.")
            except Exception as e:
                logger.error(f"Erro no loop do RotalogBackgroundScheduler: {e}")

            for _ in range(self.interval_seconds):
                if not self._running:
                    break
                time.sleep(1)
