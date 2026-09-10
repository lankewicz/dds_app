# -----------------------------------------------------------------------------
# Arquivo : services/requests_service.py
# Objetivo: Gerenciar as solicitações de alteração de prefixo vindas dos tablets.
# -----------------------------------------------------------------------------

from services.firestore_client import db
import services.turnos_service as turnos_service
from datetime import datetime, timezone
from google.cloud.firestore_v1.base_query import FieldFilter

def list_pending_requests():
    """Lista todas as solicitações de alteração de prefixo pendentes."""
    docs = db.collection("monitor/requests/prefix_changes").where(filter=FieldFilter("status", "==", "PENDING")).stream()
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
    doc_ref = db.collection("monitor/requests/prefix_changes").document(request_id)
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
        
        dds_docs = db.collection(turnos_service.DDS_COLLECTION).where(filter=FieldFilter("equipe", "==", old_prefix)).stream()
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
        # A) Move o cadastro de equipes (dds_teams)
        cleanup_batch = db.batch()
        old_team_ref = db.collection("dds_teams").document(old_prefix)
        new_team_ref = db.collection("dds_teams").document(new_prefix)
        
        team_snap = old_team_ref.get()
        if team_snap.exists:
            team_data = team_snap.to_dict()
            team_data["teamKey"] = new_prefix # Atualiza a chave interna
            team_data["updatedAt"] = firestore.SERVER_TIMESTAMP
            cleanup_batch.set(new_team_ref, team_data)
            
            # Migra histórico de equipamentos
            history_docs = old_team_ref.collection("equipment_history").stream()
            for h_doc in history_docs:
                cleanup_batch.set(new_team_ref.collection("equipment_history").document(h_doc.id), h_doc.to_dict())
                cleanup_batch.delete(h_doc.reference)
            
            cleanup_batch.delete(old_team_ref)

        # B) Remove das equipes ativas no monitor (turno/{empresa}/equipes/{prefixo})
        # O monitor irá recriar a nova equipe automaticamente no próximo sync
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
    doc_ref = db.collection("monitor/requests/prefix_changes").document(request_id)
    doc_ref.update({
        "status": "REJECTED",
        "rejectedAt": datetime.now(timezone.utc).isoformat()
    })
    return True
