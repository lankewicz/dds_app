# -----------------------------------------------------------------------------
# Arquivo : services/requests_service.py
# Objetivo: Gerenciar as solicitações de alteração de prefixo vindas dos tablets.
# -----------------------------------------------------------------------------

from services.firestore_client import db
from datetime import datetime, timezone

def list_pending_requests():
    """Lista todas as solicitações de alteração de prefixo pendentes."""
    docs = db.collection("prefix_change_requests").where("status", "==", "PENDING").stream()
    requests = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        requests.append(data)
    
    # Ordena por data (mais antigos primeiro para aprovação)
    requests.sort(key=lambda x: x.get("requestedAt", ""))
    return requests

def approve_request(request_id: str):
    """Aprova uma solicitação de alteração e migra o histórico no Firebase."""
    doc_ref = db.collection("prefix_change_requests").document(request_id)
    req_data = doc_ref.get().to_dict()
    
    if not req_data:
        return False

    old_prefix = req_data.get("oldPrefix")
    new_prefix = req_data.get("newPrefix")
    reason = req_data.get("reason")

    # 1. Se for mudança de veículo, migra o histórico no Firestore
    if reason == "VEHICLE_CHANGE":
        # Busca registros na coleção DDS
        batch = db.batch()
        count = 0
        
        dds_docs = db.collection("DDS").where("equipe", "==", old_prefix).stream()
        for doc in dds_docs:
            batch.update(doc.reference, {"equipe": new_prefix})
            count += 1
            if count >= 400:
                batch.commit()
                batch = db.batch()
                count = 0
        
        if count > 0:
            batch.commit()

        # --- NOVA FAXINA: Remove rastro da equipe antiga para sumir do monitor ---
        cleanup_batch = db.batch()
        
        # A) Remove do cadastro de equipes (dds_teams)
        old_team_ref = db.collection("dds_teams").document(old_prefix)
        cleanup_batch.delete(old_team_ref)

        # B) Remove das equipes ativas no monitor (turno/{empresa}/equipes/{prefixo})
        # Como não temos a empresa no pedido, buscamos em todas as empresas (geralmente é uma só)
        empresas_docs = db.collection("turno").stream()
        for emp_doc in empresas_docs:
            old_shift_ref = db.collection("turno").document(emp_doc.id).collection("equipes").document(old_prefix)
            cleanup_batch.delete(old_shift_ref)
        
        cleanup_batch.commit()
        # -----------------------------------------------------------------------

    # 2. Atualiza o status do pedido
    doc_ref.update({
        "status": "APPROVED",
        "approvedAt": datetime.now(timezone.utc).isoformat()
    })
    return True

def reject_request(request_id: str):
    """Rejeita uma solicitação de alteração."""
    doc_ref = db.collection("prefix_change_requests").document(request_id)
    doc_ref.update({
        "status": "REJECTED",
        "rejectedAt": datetime.now(timezone.utc).isoformat()
    })
    return True
