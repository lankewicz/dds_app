# -----------------------------------------------------------------------------
# Arquivo : services/crash_reports_service.py
# Objetivo: Leitura, contagem e remoção de relatórios de erros/fechamentos anormais
#           enviados pelos dispositivos Android para o Firestore (monitor_crash_reports).
# Autor   : Valdinei Lankewicz
# -----------------------------------------------------------------------------

from __future__ import annotations
import logging
from typing import Any, Dict, List
from google.cloud import firestore

logger = logging.getLogger(__name__)

def _get_db():
    from services.firestore_client import db
    return db

def list_crash_reports(limit: int = 50) -> List[Dict[str, Any]]:
    """Lê os últimos relatórios de erros gravados pelos apps Android."""
    db = _get_db()
    reports = []
    try:
        query = (
            db.collection("monitor_crash_reports")
            .order_by("timestampMs", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        for doc in query.stream():
            data = doc.to_dict() or {}
            data["id"] = doc.id
            reports.append(data)
    except Exception as exc:
        logger.error(f"Erro ao listar relatórios de crash no Firestore: {exc}")
        # Fallback se não houver índice composto por timestampMs
        try:
            docs = db.collection("monitor_crash_reports").limit(limit).stream()
            for doc in docs:
                data = doc.to_dict() or {}
                data["id"] = doc.id
                reports.append(data)
            reports.sort(key=lambda x: x.get("timestampMs", 0), reverse=True)
        except Exception as inner_exc:
            logger.error(f"Erro no fallback de listagem de crash reports: {inner_exc}")
    return reports

def delete_crash_report(report_id: str) -> bool:
    """Exclui um relatório de erro específico do Firestore."""
    db = _get_db()
    try:
        db.collection("monitor_crash_reports").document(report_id).delete()
        return True
    except Exception as exc:
        logger.error(f"Erro ao excluir crash report {report_id}: {exc}")
        return False

def clear_all_crash_reports() -> int:
    """Limpa todos os relatórios de erros do Firestore."""
    db = _get_db()
    count = 0
    try:
        docs = list(db.collection("monitor_crash_reports").stream())
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
            count += 1
            if count % 400 == 0:
                batch.commit()
                batch = db.batch()
        if count % 400 != 0:
            batch.commit()
    except Exception as exc:
        logger.error(f"Erro ao limpar todos os crash reports: {exc}")
    return count
