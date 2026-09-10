# -----------------------------------------------------------------------------
# Arquivo : services/messaging_service.py
# Objetivo: Gerenciar as mensagens de comunicação entre equipes e setores
#           usando a coleção mensagens_comunicacao no Firestore.
# -----------------------------------------------------------------------------

from __future__ import annotations

import os
from typing import Any, List, Optional
from datetime import datetime, timezone, timedelta
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from services.firestore_client import db

COLLECTION_MENSAGENS = "mensagens_comunicacao"
# Setor padrão deste monitor (pode ser configurado via ENV)
CURRENT_SETOR = os.getenv("DDS_MONITOR_SETOR", "OFICINA")

import time
import threading

_cache_lock = threading.Lock()
_unread_map_cache: dict[str, Any] = {"data": None, "timestamp": 0.0}
_last_messages_cache: dict[str, Any] = {"data": None, "timestamp": 0.0}
_unread_counts_cache: dict[str, dict[str, Any]] = {}
_MESSAGES_CACHE_TTL_SECONDS = 30.0

def invalidate_messages_cache():
    """Invalida os caches de mensagens na memória RAM."""
    with _cache_lock:
        _unread_map_cache["timestamp"] = 0.0
        _last_messages_cache["timestamp"] = 0.0
        _unread_counts_cache.clear()

def get_all_unread_counts_map() -> dict[str, dict[str, int]]:
    """
    Retorna um mapeamento global: { fromEquipe: { toSetor: quantidade } }
    Isso permite que o monitor mostre notificações dinâmicas ao trocar de setor.
    Reutiliza cache RAM de 30s.
    """
    now = time.monotonic()
    with _cache_lock:
        if _unread_map_cache["data"] is not None and (now - float(_unread_map_cache["timestamp"]) < _MESSAGES_CACHE_TTL_SECONDS):
            return dict(_unread_map_cache["data"])

    query = (
        db.collection(COLLECTION_MENSAGENS)
        .where(filter=FieldFilter("status", "==", "NÃO LIDO"))
    )
    
    # Estrutura: { teamKey: { 'OFICINA': 2, 'ALMOX': 1 } }
    global_counts = {}
    for snap in query.stream():
        data = snap.to_dict()
        from_equipe = data.get("fromEquipe")
        to_setor = data.get("toSetor")
        
        if from_equipe and to_setor:
            if from_equipe not in global_counts:
                global_counts[from_equipe] = {}
            
            global_counts[from_equipe][to_setor] = global_counts[from_equipe].get(to_setor, 0) + 1
            
    with _cache_lock:
        _unread_map_cache["data"] = global_counts
        _unread_map_cache["timestamp"] = now

    return dict(global_counts)


def get_last_messages_map() -> dict[str, datetime]:
    """
    Retorna um mapa de equipe (nome ou key) -> timestamp da última mensagem enviada por ela.
    Limitamos aos últimos 10 dias para performance. Reutiliza cache RAM de 30s.
    """
    now = time.monotonic()
    with _cache_lock:
        if _last_messages_cache["data"] is not None and (now - float(_last_messages_cache["timestamp"]) < _MESSAGES_CACHE_TTL_SECONDS):
            return dict(_last_messages_cache["data"])

    cutoff = datetime.now(timezone.utc) - timedelta(days=10)
    query = (
        db.collection(COLLECTION_MENSAGENS)
        .where(filter=FieldFilter("serverUpdatedAt", ">=", cutoff))
    )
    
    # Como não podemos fazer order_by facilmente sem índices complexos cruzados,
    # fazemos o max localmente por equipe.
    last_msgs = {}
    for snap in query.stream():
        data = snap.to_dict()
        from_equipe = data.get("fromEquipe")
        ts = data.get("serverUpdatedAt")
        if from_equipe and ts:
            if from_equipe not in last_msgs or ts > last_msgs[from_equipe]:
                last_msgs[from_equipe] = ts

    with _cache_lock:
        _last_messages_cache["data"] = last_msgs
        _last_messages_cache["timestamp"] = now

    return dict(last_msgs)


def get_unread_counts(setor: str = CURRENT_SETOR) -> dict[str, int]:
    """
    Retorna um mapeamento de equipe -> quantidade de mensagens NÃO LIDAS
    destinadas ao setor atual vindas de cada equipe. Reutiliza cache RAM de 30s.
    """
    now = time.monotonic()
    with _cache_lock:
        cached = _unread_counts_cache.get(setor)
        if cached and (now - float(cached.get("timestamp", 0)) < _MESSAGES_CACHE_TTL_SECONDS):
            return dict(cached.get("data") or {})

    query = (
        db.collection(COLLECTION_MENSAGENS)
        .where(filter=FieldFilter("toSetor", "==", setor))
        .where(filter=FieldFilter("status", "==", "NÃO LIDO"))
    )
    
    counts = {}
    for snap in query.stream():
        data = snap.to_dict()
        from_equipe = data.get("fromEquipe")
        if from_equipe:
            counts[from_equipe] = counts.get(from_equipe, 0) + 1

    with _cache_lock:
        _unread_counts_cache[setor] = {"data": counts, "timestamp": now}

    return counts

def get_open_threads(setor: str = CURRENT_SETOR) -> List[dict[str, Any]]:
    """
    Busca todas as mensagens que não estão CONCLUIDAS e que envolvem o setor.
    Se o setor for 'TODOS', traz todas as mensagens não concluídas.
    """
    if setor == "TODOS":
        query = db.collection(COLLECTION_MENSAGENS).where(filter=FieldFilter("status", "!=", "CONCLUIDA"))
        messages = []
        for snap in query.stream():
            msg = snap.to_dict()
            msg["id"] = snap.id
            messages.append(msg)
    else:
        # Busca mensagens destinadas ao setor ou enviadas pelo setor que não estão concluídas
        query_to = db.collection(COLLECTION_MENSAGENS).where(filter=FieldFilter("toSetor", "==", setor)).where(filter=FieldFilter("status", "!=", "CONCLUIDA"))
        query_from = db.collection(COLLECTION_MENSAGENS).where(filter=FieldFilter("fromEquipe", "==", setor)).where(filter=FieldFilter("status", "!=", "CONCLUIDA"))
        
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
        .where(filter=FieldFilter("threadId", "==", thread_id))
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
    Se o setor for 'TODOS', marca todas as mensagens não lidas da thread.
    """
    query = db.collection(COLLECTION_MENSAGENS).where(filter=FieldFilter("threadId", "==", thread_id)).where(filter=FieldFilter("status", "==", "NÃO LIDO"))
    
    if setor != "TODOS":
        query = query.where(filter=FieldFilter("toSetor", "==", setor))
    
    count = 0
    batch = db.batch()
    for snap in query.stream():
        batch.update(snap.reference, {"status": "LIDO"})
        count += 1
    
    if count > 0:
        batch.commit()
        invalidate_messages_cache()
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
    invalidate_messages_cache()
    return doc_ref.id

def conclude_thread(thread_id: str) -> int:
    """
    Marca todas as mensagens de uma thread como CONCLUIDA.
    """
    query = db.collection(COLLECTION_MENSAGENS).where(filter=FieldFilter("threadId", "==", thread_id))
    
    count = 0
    batch = db.batch()
    for snap in query.stream():
        batch.update(snap.reference, {"status": "CONCLUIDA"})
        count += 1
    
    if count > 0:
        batch.commit()
        invalidate_messages_cache()
    return count

def _to_datetime(ts: Any) -> datetime:
    if not ts:
        return datetime.min.replace(tzinfo=timezone.utc)
    if hasattr(ts, "to_datetime"):
        return ts.to_datetime()
    if isinstance(ts, datetime):
        return ts
    return datetime.min.replace(tzinfo=timezone.utc)
