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
import threading
import time
import typing
import firebase_admin
from firebase_admin import credentials, firestore

from boletim_x_ponto.services.rotalog_tempo_real_service import extrair_dados_tempo_real

logger = logging.getLogger(__name__)

_firestore_db = None


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
        "bdo_len": len(eq.get("bdo_list", [])),
        "ss_andamento": eq.get("ss_em_andamento"),
        "ss_pendentes_len": len(eq.get("ss_pendentes", []))
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

    return max(timestamps) if timestamps else int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)


def executar_sincronizacao_rotalog(empresa: str = "ChicoEletro", forcar: bool = False) -> dict[str, typing.Any]:
    """
    Executa a raspagem do Rotalog Tempo Real, lê os dados do DDS no Firestore,
    compara recência e altera o Firestore SOMENTE SE HOUVER MUDANÇA (Diff Hash Check).
    """
    db = get_firestore_client()
    timestamp_now = datetime.datetime.now(datetime.timezone.utc)
    timestamp_iso = timestamp_now.isoformat()

    logger.info("Iniciando captura Rotalog Tempo Real...")
    equipas = extrair_dados_tempo_real()
    logger.info(f"Rotalog extraído: {len(equipas)} equipes capturadas.")

    rotalog_updated = 0
    dds_applied = 0
    dds_preserved = 0
    skipped_unchanged = 0

    batch = db.batch()
    op_count = 0

    for eq in equipas:
        eq_codigo = eq["equipe_codigo"].strip().upper()
        if not eq_codigo:
            continue

        team_key = normalize_team_key(eq_codigo)
        current_fingerprint = _calcular_fingerprint(eq)

        # 1. Ler estado atual no Firestore para comparar Hash (evitar escritas desnecessárias)
        ref_dds_app = db.collection("turno").document(empresa).collection("equipes").document(team_key)
        dds_doc = ref_dds_app.get()
        dds_data = dds_doc.to_dict() if dds_doc.exists else {}

        last_fingerprint = dds_data.get("rotalogFingerprint", "")

        # Se não houve nenhuma mudança de estado/SS no Rotalog e o documento já existe, pula escrita no Firestore!
        if not forcar and dds_doc.exists and last_fingerprint == current_fingerprint:
            skipped_unchanged += 1
            continue

        doc_rotalog = {
            "empresa": empresa,
            "equipe": eq_codigo,
            "teamKey": team_key,
            "groupRaw": eq["group_raw"],
            "veiculo": eq["veiculo"],
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

        # Salvar documento em /turnos_rotalog/{team_key}
        ref_rotalog = db.collection("turnos_rotalog").document(team_key)
        batch.set(ref_rotalog, doc_rotalog, merge=True)
        op_count += 1
        rotalog_updated += 1

        rotalog_ms = _extrair_timestamp_rotalog(eq)
        dds_ms = _extrair_timestamp_dds(dds_data)

        # 2. Análise de Recência: Se Rotalog for MAIS RECENTE que o DDS
        if rotalog_ms > dds_ms or not dds_doc.exists:
            novo_estado_dds = {
                "empresa": empresa,
                "equipe": eq_codigo,
                "estado": eq["estado_consolidado"],
                "isOpen": eq["estado_consolidado"] != "FECHADO",
                "openedAtClientMs": eq["turno"]["inicio_ms"] or dds_data.get("openedAtClientMs"),
                "closedAtClientMs": eq["turno"]["fim_ms"] if eq["estado_consolidado"] == "FECHADO" else None,
                "clientUpdatedAtMs": rotalog_ms,
                "updatedAtIso": timestamp_iso,
                "deviceIdLastWriter": "ROTALOG_AUTO_SYNC",
                "bdoList": eq["bdo_list"],
                "rotalogSnapshot": doc_rotalog,
                "rotalogFingerprint": current_fingerprint,
                "origemAtualizacao": "ROTALOG_MAIS_RECENTE"
            }
            batch.set(ref_dds_app, novo_estado_dds, merge=True)

            ref_dds_web = db.collection("empresas").document(empresa).collection("turnos_estado").document(team_key)
            batch.set(ref_dds_web, novo_estado_dds, merge=True)

            dds_applied += 1
        else:
            update_payload = {
                "rotalogSnapshot": doc_rotalog,
                "rotalogFingerprint": current_fingerprint,
                "origemAtualizacao": "DDS_MAIS_RECENTE"
            }
            batch.set(ref_dds_app, update_payload, merge=True)

            ref_dds_web = db.collection("empresas").document(empresa).collection("turnos_estado").document(team_key)
            batch.set(ref_dds_web, update_payload, merge=True)

            dds_preserved += 1

        op_count += 2

        if op_count >= 400:
            batch.commit()
            batch = db.batch()
            op_count = 0

    if op_count > 0:
        batch.commit()

    return {
        "status": "success",
        "updatedAtIso": timestamp_iso,
        "totalEquipesRotalog": len(equipas),
        "turnosRotalogSalvos": rotalog_updated,
        "aplicadosNoDdsRotalogMaisRecente": dds_applied,
        "preservadosDdsMaisRecente": dds_preserved,
        "ignoradosSemMudanca": skipped_unchanged
    }


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
