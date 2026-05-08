# -----------------------------------------------------------------------------
# Arquivo : services/messaging_service.py
# Objetivo: Gerenciar as mensagens de comunicação entre equipes e setores
#           usando a coleção mensagens_comunicacao no Firestore.
# -----------------------------------------------------------------------------

from __future__ import annotations

import os
from typing import Any, List, Optional
from datetime import datetime, timezone
from google.cloud import firestore
from services.firestore_client import db

COLLECTION_MENSAGENS = "mensagens_comunicacao"
# Setor padrão deste monitor (pode ser configurado via ENV)
CURRENT_SETOR = os.getenv("DDS_MONITOR_SETOR", "OFICINA")

def get_unread_counts(setor: str = CURRENT_SETOR) -> dict[str, int]:
    """
    Retorna um mapeamento de equipe -> quantidade de mensagens NÃO LIDAS
    destinadas ao setor atual vindas de cada equipe.
    """
    query = (
        db.collection(COLLECTION_MENSAGENS)
        .where("toSetor", "==", setor)
        .where("status", "==", "NÃO LIDO")
    )
    
    counts = {}
    for snap in query.stream():
        data = snap.to_dict()
        from_equipe = data.get("fromEquipe")
        if from_equipe:
            counts[from_equipe] = counts.get(from_equipe, 0) + 1
    return counts

def get_open_threads(setor: str = CURRENT_SETOR) -> List[dict[str, Any]]:
    """
    Busca todas as mensagens que não estão CONCLUIDAS e que envolvem o setor.
    Agrupa por threadId retornando a mais recente de cada.
    """
    # Como o Firestore não suporta Group By, buscamos todas as abertas e agrupamos em memória
    # Ou filtramos pelas destinadas ao setor ou enviadas pelo setor.
    
    # Busca mensagens destinadas ao setor ou enviadas pelo setor que não estão concluídas
    query_to = db.collection(COLLECTION_MENSAGENS).where("toSetor", "==", setor).where("status", "!=", "CONCLUIDA")
    query_from = db.collection(COLLECTION_MENSAGENS).where("fromEquipe", "==", setor).where("status", "!=", "CONCLUIDA")
    
    messages = []
    seen_ids = set()
    
    for snap in query_to.stream():
        if snap.id not in seen_ids:
            msg = snap.to_dict()
            msg["id"] = snap.id
            messages.append(msg)
            seen_ids.add(snap.id)
            
    for snap in query_from.stream():
        if snap.id not in seen_ids:
            msg = snap.to_dict()
            msg["id"] = snap.id
            messages.append(msg)
            seen_ids.add(snap.id)
            
    # Agrupar por threadId
    threads = {}
    for msg in messages:
        tid = msg.get("threadId")
        if not tid: continue
        
        # Converte timestamp para comparação se necessário
        ts = msg.get("timestamp")
        
        if tid not in threads:
            threads[tid] = msg
        else:
            existing_ts = threads[tid].get("timestamp")
            if ts and existing_ts:
                # Compara firestore.Timestamp ou datetime
                if _to_datetime(ts) > _to_datetime(existing_ts):
                    threads[tid] = msg
            elif ts:
                threads[tid] = msg

    return sorted(threads.values(), key=lambda x: _to_datetime(x.get("timestamp")), reverse=True)

def get_thread_messages(thread_id: str) -> List[dict[str, Any]]:
    """
    Retorna todas as mensagens de uma conversa específica, ordenadas por tempo.
    """
    query = (
        db.collection(COLLECTION_MENSAGENS)
        .where("threadId", "==", thread_id)
    )
    
    result = []
    for snap in query.stream():
        msg = snap.to_dict()
        msg["id"] = snap.id
        result.append(msg)
    
    # Ordena em memória para evitar a necessidade de índices compostos complexos no Firestore
    return sorted(result, key=lambda x: _to_datetime(x.get("timestamp")))

def mark_thread_as_read(thread_id: str, setor: str = CURRENT_SETOR) -> int:
    """
    Marca como LIDO todas as mensagens destinadas ao setor nesta thread.
    """
    query = (
        db.collection(COLLECTION_MENSAGENS)
        .where("threadId", "==", thread_id)
        .where("toSetor", "==", setor)
        .where("status", "==", "NÃO LIDO")
    )
    
    count = 0
    batch = db.batch()
    for snap in query.stream():
        batch.update(snap.reference, {"status": "LIDO"})
        count += 1
    
    if count > 0:
        batch.commit()
    return count

def send_message(
    thread_id: str,
    subject: str,
    content: str,
    to_equipe: Optional[str] = None,
    to_setor: Optional[str] = None,
    from_equipe: str = CURRENT_SETOR
) -> str:
    """
    Cria uma nova mensagem em uma thread.
    """
    doc_data = {
        "threadId": thread_id,
        "fromEquipe": from_equipe,
        "toSetor": to_setor,
        "toEquipe": to_equipe,
        "subject": subject,
        "content": content,
        "status": "NÃO LIDO",
        "timestamp": firestore.SERVER_TIMESTAMP
    }
    
    doc_ref = db.collection(COLLECTION_MENSAGENS).document()
    doc_ref.set(doc_data)
    return doc_ref.id

def conclude_thread(thread_id: str) -> int:
    """
    Marca todas as mensagens de uma thread como CONCLUIDA.
    """
    query = db.collection(COLLECTION_MENSAGENS).where("threadId", "==", thread_id)
    
    count = 0
    batch = db.batch()
    for snap in query.stream():
        batch.update(snap.reference, {"status": "CONCLUIDA"})
        count += 1
    
    if count > 0:
        batch.commit()
    return count

def _to_datetime(ts: Any) -> datetime:
    if not ts:
        return datetime.min.replace(tzinfo=timezone.utc)
    if hasattr(ts, "to_datetime"):
        return ts.to_datetime()
    if isinstance(ts, datetime):
        return ts
    return datetime.min.replace(tzinfo=timezone.utc)
