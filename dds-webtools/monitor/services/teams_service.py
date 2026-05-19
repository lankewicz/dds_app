# -----------------------------------------------------------------------------
# Arquivo : services/teams_service.py
# Objetivo: Ler e gravar o cadastro-base das equipes em dds_teams/{teamKey},
#           incluindo os vínculos estruturados dos equipamentos, os metadados
#           da última alteração e o histórico detalhado das mudanças.
# -----------------------------------------------------------------------------

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from services.firestore_client import db
# NOTE: turnos_service imports teams_service, so we use local imports inside
# functions below to avoid a circular import at module load time.


COLLECTION_NAME = "dds_teams"
TRASH_COLLECTION_NAME = "monitor/trash/dds_teams"
DDS_TRASH_COLLECTION_NAME = "monitor/trash/DDS"
MENSAGENS_COLLECTION_NAME = "mensagens_comunicacao"
MENSAGENS_TRASH_COLLECTION_NAME = "monitor/trash/mensagens_comunicacao"
REQUESTS_COLLECTION_NAME = "monitor/requests/prefix_changes"
EQUIPMENT_HISTORY_SUBCOLLECTION = "equipment_history"
EQUIPMENT_TYPES = ("tablet", "cameraCopel", "cameraVeicular")

_TEAMS_CACHE: dict[str, Any] = {
    "data": None,
    "updatedAt": None
}
TEAMS_CACHE_TTL_SEC = 300 # 5 minutos


EQUIPMENT_DEFAULTS: dict[str, dict[str, Any]] = {
    "tablet": {
        "kind": "tablet",
        "label": "Tablet",
        "supportsPatrimonio": True,
        "supportsImei": True,
        "supportsPhoneNumber": True,
    },
    "cameraCopel": {
        "kind": "cameraCopel",
        "label": "Câmera Copel",
        "supportsPatrimonio": True,
        "supportsImei": False,
        "supportsPhoneNumber": False,
    },
    "cameraVeicular": {
        "kind": "cameraVeicular",
        "label": "Câmera veicular",
        "supportsPatrimonio": False,
        "supportsImei": True,
        "supportsPhoneNumber": True,
        "supportsEmail": False,
    },
}


def clear_teams_cache():
    """Limpa o cache em memória das equipes."""
    global _TEAMS_CACHE
    _TEAMS_CACHE["data"] = None
    _TEAMS_CACHE["updatedAt"] = None


def get_team(team_key: str) -> dict[str, Any] | None:
    # Tenta busca exata
    doc_ref = db.collection(COLLECTION_NAME).document(team_key)
    snap = doc_ref.get()
    
    if not snap.exists:
        # Tenta busca case-insensitive
        for doc in db.collection(COLLECTION_NAME).stream():
            if doc.id.upper() == team_key.upper():
                snap = doc
                break
    
    if not snap.exists:
        return None
        
    data = snap.to_dict() or {}
    data["teamKey"] = snap.id # Garante o ID real
    equipment = _read_equipment_map(data)
    data["active"] = bool(data.get("active", True))
    data["equipment"] = equipment
    data["tablet"] = equipment["tablet"]["summary"]
    data["cameraCopel"] = equipment["cameraCopel"]["summary"]
    data["cameraVeicular"] = equipment["cameraVeicular"]["summary"]
    data["_exists"] = True
    return data


def list_teams_map(active: bool | None = None) -> dict[str, dict[str, Any]]:
    return _list_collection_teams_map(COLLECTION_NAME, active=active)


def list_trash_teams_map() -> dict[str, dict[str, Any]]:
    return _list_collection_teams_map(TRASH_COLLECTION_NAME)


def _list_collection_teams_map(collection_name: str, active: bool | None = None) -> dict[str, dict[str, Any]]:
    global _TEAMS_CACHE
    
    # Cache apenas para a coleção principal e sem filtro de active (para permitir filtros posteriores em memória)
    if collection_name == COLLECTION_NAME:
        now = datetime.now(timezone.utc)
        if _TEAMS_CACHE["data"] is not None and _TEAMS_CACHE["updatedAt"] is not None:
            age = (now - _TEAMS_CACHE["updatedAt"]).total_seconds()
            if age < TEAMS_CACHE_TTL_SEC:
                # Filtra o cache se necessário
                if active is None:
                    return _TEAMS_CACHE["data"]
                return {k: v for k, v in _TEAMS_CACHE["data"].items() if v.get("active") == active}

    out: dict[str, dict[str, Any]] = {}
    for snap in db.collection(collection_name).stream():
        data = snap.to_dict() or {}
        team_active = bool(data.get("active", True))
        if active is not None and team_active is not active:
            continue
        equipment = _read_equipment_map(data)
        out[snap.id] = {
            **data,
            "teamKey": snap.id,
            "active": team_active,
            "equipment": equipment,
            "tablet": equipment["tablet"]["summary"],
            "cameraCopel": equipment["cameraCopel"]["summary"],
            "cameraVeicular": equipment["cameraVeicular"]["summary"],
            "_exists": True,
        }
    
    if collection_name == COLLECTION_NAME:
        _TEAMS_CACHE["data"] = out
        _TEAMS_CACHE["updatedAt"] = datetime.now(timezone.utc)
        
    if active is not None:
        return {k: v for k, v in out.items() if v.get("active") == active}
        
    return out


def move_to_trash(team_key: str) -> None:
    # 1. Localiza o ID correto (case-insensitive)
    actual_team_key = team_key
    source_ref = db.collection(COLLECTION_NAME).document(team_key)
    snap = source_ref.get()
    
    if not snap.exists:
        for doc in db.collection(COLLECTION_NAME).stream():
            if doc.id.upper() == team_key.upper():
                actual_team_key = doc.id
                source_ref = doc.reference
                snap = doc
                break
                
    if not snap.exists:
        # Se não existe no dds_teams, ainda assim tentamos limpar os resquícios no monitor
        _cleanup_team_runtime_and_realtime(team_key)
        return

    dest_ref = db.collection(TRASH_COLLECTION_NAME).document(actual_team_key)
    data = snap.to_dict() or {}
    data["deletedAt"] = firestore.SERVER_TIMESTAMP
    
    # 1. Move documento da equipe e histórico de equipamentos
    batch = db.batch()
    batch.set(dest_ref, data)
    
    history_snaps = source_ref.collection(EQUIPMENT_HISTORY_SUBCOLLECTION).get()
    for h_snap in history_snaps:
        h_dest_ref = dest_ref.collection(EQUIPMENT_HISTORY_SUBCOLLECTION).document(h_snap.id)
        batch.set(h_dest_ref, h_snap.to_dict())
        batch.delete(h_snap.reference)
    
    batch.delete(source_ref)
    batch.commit()

    # 2. Identifica todos os possíveis nomes desta equipe para encontrar registros
    aliases = _get_team_aliases(team_key, data)

    # 3. Move registros de DDS para a lixeira (usando aliases)
    _move_collection_records(aliases, "equipe", turnos_service.DDS_COLLECTION, DDS_TRASH_COLLECTION_NAME)

    # 4. Move histórico de mensagens para a lixeira (usando aliases)
    _move_collection_records(aliases, "fromEquipe", MENSAGENS_COLLECTION_NAME, MENSAGENS_TRASH_COLLECTION_NAME)
    _move_collection_records(aliases, "toEquipe", MENSAGENS_COLLECTION_NAME, MENSAGENS_TRASH_COLLECTION_NAME)

    # 5. Limpa estado em tempo real e caches
    _cleanup_team_runtime_and_realtime(team_key)
    turnos_service.clear_all_monitor_caches()


def _cleanup_team_runtime_and_realtime(team_key: str) -> None:
    """Limpa a equipe de todas as coleções de estado imediato."""
    # Remove do monitor realtime legado (para compatibilidade durante migração)
    legacy_realtime_col = db.collection("monitor").document("realtime").collection("equipes")
    legacy_realtime_col.document(team_key).delete()
    
    # Remove de todas as empresas no 'turno' (tanto o estado bruto quanto a visão realtime)
    for empresa_snap in db.collection("turno").stream():
        empresa_ref = empresa_snap.reference
        
        # 1. Remove da visão realtime consolidada
        realtime_col = empresa_ref.collection("realtime")
        realtime_col.document(team_key).delete()
        for doc in realtime_col.stream():
            if doc.id.upper() == team_key.upper():
                doc.reference.delete()

        # 2. Remove do estado bruto (coleção 'equipes')
        equipes_col = empresa_ref.collection("equipes")
        equipes_col.document(team_key).delete()
        for doc in equipes_col.stream():
            if doc.id.upper() == team_key.upper():
                doc.reference.delete()


def _delete_doc_and_subcollections(doc_ref: Any, batch_size: int = 400) -> None:
    """Deleta um documento e todas as suas subcoleções recursivamente."""
    # 1. Deleta subcoleções primeiro
    for col_ref in doc_ref.collections():
        # Deleta documentos da subcoleção em lotes
        docs = col_ref.list_documents(page_size=batch_size)
        for doc in docs:
            _delete_doc_and_subcollections(doc, batch_size)
    
    # 2. Deleta o documento em si
    doc_ref.delete()


def _get_team_aliases(team_key: str, team_data: dict[str, Any]) -> set[str]:
    """Retorna conjunto de nomes que podem identificar a equipe nos registros."""
    from services.turnos_service import _normalize_text
    aliases = {team_key}
    
    display_name = team_data.get("displayName")
    if display_name:
        aliases.add(display_name)
    
    # Adiciona versões normalizadas para garantir o 'match'
    normalized = set()
    for a in aliases:
        if not a: continue
        n = _normalize_text(a)
        if n: normalized.add(n)
        
    return aliases | normalized


def restore_from_trash(team_key: str) -> None:
    source_ref = db.collection(TRASH_COLLECTION_NAME).document(team_key)
    dest_ref = db.collection(COLLECTION_NAME).document(team_key)

    snap = source_ref.get()
    if not snap.exists:
        return

    data = snap.to_dict() or {}
    data.pop("deletedAt", None)
    
    batch = db.batch()
    batch.set(dest_ref, data)
    
    # Restaura histórico
    history_snaps = source_ref.collection(EQUIPMENT_HISTORY_SUBCOLLECTION).get()
    for h_snap in history_snaps:
        h_dest_ref = dest_ref.collection(EQUIPMENT_HISTORY_SUBCOLLECTION).document(h_snap.id)
        batch.set(h_dest_ref, h_snap.to_dict())
        batch.delete(h_snap.reference)
        
    batch.delete(source_ref)
    batch.commit()

    # Restaura registros de DDS da lixeira para a coleção principal
    _move_dds_records(team_key, DDS_TRASH_COLLECTION_NAME, turnos_service.DDS_COLLECTION)


def permanently_delete(team_key: str) -> list[str]:
    """Exclui permanentemente todos os vestígios da equipe e seus dados vinculados."""
    logs = []
    logs.append(f"Iniciando faxina completa para: {team_key}")
    
    # 1. Busca robusta pelo documento da equipe (pode estar com case diferente no ID)
    actual_team_key = team_key
    snap_trash = db.collection(TRASH_COLLECTION_NAME).document(team_key).get()
    if not snap_trash.exists:
        # Tenta buscar por case-insensitive na lixeira
        all_trash = db.collection(TRASH_COLLECTION_NAME).stream()
        for doc in all_trash:
            if doc.id.upper() == team_key.upper():
                actual_team_key = doc.id
                snap_trash = doc
                logs.append(f"Encontrado ID correspondente na lixeira: {actual_team_key}")
                break
    
    snap_main = db.collection(COLLECTION_NAME).document(actual_team_key).get()
    data = (snap_trash.to_dict() or snap_main.to_dict()) if (snap_trash.exists or snap_main.exists) else {}
    aliases = _get_team_aliases(actual_team_key, data)
    logs.append(f"Aliases identificados: {', '.join(aliases)}")

    # 2. Deleta as imagens do Storage vinculadas aos DDS desta equipe
    img_count = _delete_team_storage_images(aliases)
    if img_count > 0:
        logs.append(f"Imagens removidas do Storage: {img_count}")

    # 3. Deleta documentos base e lixeira
    _delete_doc_and_subcollections(db.collection(TRASH_COLLECTION_NAME).document(actual_team_key))
    _delete_doc_and_subcollections(db.collection(COLLECTION_NAME).document(actual_team_key))
    logs.append("Cadastro base e histórico de equipamentos removidos.")

    # 4. Deleta DDS (Principal e Lixeira)
    dds_count = _delete_collection_records(aliases, "equipe", turnos_service.DDS_COLLECTION)
    dds_trash_count = _delete_collection_records(aliases, "equipe", DDS_TRASH_COLLECTION_NAME)
    if dds_count or dds_trash_count:
        logs.append(f"Registros de DDS removidos: {dds_count} (ativos), {dds_trash_count} (lixeira)")

    # 5. Deleta Mensagens (Principal e Lixeira)
    msg_count = _delete_collection_records(aliases, "fromEquipe", MENSAGENS_COLLECTION_NAME)
    msg_count += _delete_collection_records(aliases, "toEquipe", MENSAGENS_COLLECTION_NAME)
    msg_trash_count = _delete_collection_records(aliases, "fromEquipe", MENSAGENS_TRASH_COLLECTION_NAME)
    msg_trash_count += _delete_collection_records(aliases, "toEquipe", MENSAGENS_TRASH_COLLECTION_NAME)
    if msg_count or msg_trash_count:
        logs.append(f"Mensagens removidas: {msg_count} (ativas), {msg_trash_count} (lixeira)")

    # 6. Deleta solicitações pendentes ou vinculadas
    req_count = _delete_collection_records({actual_team_key, team_key}, "oldPrefix", REQUESTS_COLLECTION_NAME)
    req_count += _delete_collection_records({actual_team_key, team_key}, "newPrefix", REQUESTS_COLLECTION_NAME)
    if req_count > 0:
        logs.append(f"Solicitações de alteração limpas: {req_count}")

    # 7. Limpa estado runtime (turno, realtime) e caches
    _cleanup_team_runtime_and_realtime(actual_team_key)
    if actual_team_key != team_key:
        _cleanup_team_runtime_and_realtime(team_key)
    turnos_service.clear_all_monitor_caches()
    logs.append("Caches do monitor e estado em tempo real limpos.")
    
    logs.append(f"Exclusão de '{actual_team_key}' concluída com sucesso.")
    return logs


def _move_collection_records(keys: set[str], field: str, source_col: str, dest_col: str) -> int:
    """Move registros de qualquer coleção filtrando por um campo."""
    total = 0
    for key in keys:
        if not key: continue
        query = db.collection(source_col).where(filter=FieldFilter(field, "==", key))
        snaps = query.get()
        total += len(snaps)
        for i in range(0, len(snaps), 400):
            batch = db.batch()
            for snap in snaps[i : i + 400]:
                batch.set(db.collection(dest_col).document(snap.id), snap.to_dict())
                batch.delete(snap.reference)
            batch.commit()
    return total


def _delete_collection_records(keys: set[str], field: str, collection: str) -> int:
    """Remove permanentemente registros de uma coleção."""
    total = 0
    for key in keys:
        if not key: continue
        query = db.collection(collection).where(filter=FieldFilter(field, "==", key))
        snaps = query.get()
        total += len(snaps)
        for i in range(0, len(snaps), 400):
            batch = db.batch()
            for snap in snaps[i : i + 400]:
                batch.delete(snap.reference)
            batch.commit()
    return total


def _delete_team_storage_images(aliases: set[str]) -> int:
    """Localiza todos os registros de DDS e deleta os arquivos do storage vinculados."""
    collections = [turnos_service.DDS_COLLECTION, DDS_TRASH_COLLECTION_NAME]
    bucket = turnos_service._storage_bucket()
    count = 0
    
    for col in collections:
        for alias in aliases:
            if not alias: continue
            query = db.collection(col).where(filter=FieldFilter("equipe", "==", alias))
            for snap in query.stream():
                data = snap.to_dict() or {}
                # Campos comuns de imagem/foto
                photo_fields = ["photoUrl", "photoPath", "signatureUrl", "vistoriasPhotos"]
                for field in photo_fields:
                    val = data.get(field)
                    if not val: continue
                    
                    if isinstance(val, list):
                        paths = val
                    else:
                        paths = [val]
                        
                    for path in paths:
                        if not isinstance(path, str): continue
                        if _safe_delete_storage_path(bucket, path):
                            count += 1
    return count


def _safe_delete_storage_path(bucket, path: str) -> bool:
    """Tenta extrair o blob name e deletar."""
    try:
        # Se for uma URL do Firebase, tenta extrair o path
        # Ex: https://firebasestorage.googleapis.com/v0/b/.../o/DDSv2%2Fimage.jpg?alt=media
        blob_name = path
        if "firebasestorage.googleapis.com" in path:
            import urllib.parse
            parts = path.split("/o/")
            if len(parts) > 1:
                blob_name = urllib.parse.unquote(parts[1].split("?")[0])
        
        blob = bucket.blob(blob_name)
        if blob.exists():
            blob.delete()
            return True
    except Exception:
        pass
    return False


def get_team_trash_preview(team_key: str) -> dict[str, Any]:
    """
    Retorna um resumo do que será movido para a lixeira para exibição no modal de confirmação.
    """
    team_doc = get_team(team_key) or {}
    
    # Conta histórico de equipamentos
    history_count = 0
    ref = db.collection(COLLECTION_NAME).document(team_key).collection(EQUIPMENT_HISTORY_SUBCOLLECTION)
    # Stream is heavy but for count we can use aggregation if available, 
    # but let's just use a simple query for now or stream.
    history_snaps = ref.get()
    history_count = len(history_snaps)
    
    # Conta registros de DDS
    dds_count = 0
    dds_query = db.collection(turnos_service.DDS_COLLECTION).where(filter=FieldFilter("equipe", "==", team_key))
    dds_snaps = dds_query.get()
    dds_count = len(dds_snaps)
    
    return {
        "teamKey": team_key,
        "displayName": team_doc.get("displayName") or team_key,
        "membersCount": len(team_doc.get("members") or []),
        "ddsCount": dds_count,
        "equipmentHistoryCount": history_count,
    }




def list_equipment_history(team_key: str, limit: int = 20) -> list[dict[str, Any]]:
    query = (
        db.collection(COLLECTION_NAME)
        .document(team_key)
        .collection(EQUIPMENT_HISTORY_SUBCOLLECTION)
        .order_by("changedAt", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )

    items: list[dict[str, Any]] = []
    for snap in query.stream():
        data = snap.to_dict() or {}
        items.append({
            "id": snap.id,
            "teamKey": team_key,
            "equipmentType": str(data.get("equipmentType") or "").strip(),
            "equipmentLabel": str(data.get("equipmentLabel") or "").strip(),
            "before": _normalize_equipment_payload(data.get("before"), str(data.get("equipmentType") or "")),
            "after": _normalize_equipment_payload(data.get("after"), str(data.get("equipmentType") or "")),
            "changeReason": _clean_str(data.get("changeReason")),
            "changedByName": _clean_str(data.get("changedByName")) or "MONITOR WEB",
            "changedByDeviceModel": _clean_str(data.get("changedByDeviceModel")) or "DDS_TURNOS_MONITOR",
            "changedAt": _normalize_timestamp_string(data.get("changedAt")),
        })
    return items


def set_team_active_state(
    team_key: str,
    active: bool,
    *,
    reason: str = "MANUAL",
    empresa: str | None = None,
) -> dict[str, Any]:
    """
    Ativa ou desativa uma equipe, gravando os metadados de controle manual
    para evitar reativação automática indevida.
    Recebe `empresa` para consolidar apenas aquela empresa no realtime, evitando
    uma varredura desnecessária em todas as empresas.
    """
    team = get_team(team_key)
    if not team:
        raise ValueError(f"Equipe '{team_key}' não encontrada.")

    actual_team_key = team.get("teamKey") or team_key
    team_ref = db.collection(COLLECTION_NAME).document(actual_team_key)

    if active:
        # Ativação: Limpa metadados de inatividade
        payload = {
            "active": True,
            "autoInactiveReason": firestore.DELETE_FIELD,
            "autoInactiveAt": firestore.DELETE_FIELD,
            "autoInactiveLastSeenUpdatedAt": firestore.DELETE_FIELD,
            "autoInactiveLastSeenDdsDay": firestore.DELETE_FIELD,
            "autoReactivatedAt": firestore.SERVER_TIMESTAMP,
        }
    else:
        # Desativação: Grava o motivo e o checkpoint
        payload = {
            "active": False,
            "autoInactiveReason": reason,
            "autoInactiveAt": firestore.SERVER_TIMESTAMP,
            "autoInactiveLastSeenUpdatedAt": firestore.SERVER_TIMESTAMP,
        }

    team_ref.set(payload, merge=True)
    clear_teams_cache()

    # Atualiza o realtime para refletir a mudança imediatamente
    try:
        if empresa:
            from services.turnos_service import consolidate_single_team
            consolidate_single_team(empresa, actual_team_key)
        else:
            from services.turnos_service import consolidate_team_across_all_companies
            consolidate_team_across_all_companies(actual_team_key)
    except Exception as exc:
        # Não engolir: a equipe foi alterada no Firestore, mas o realtime pode
        # estar desatualizado. Logamos para diagnóstico.
        import logging
        logging.getLogger(__name__).warning(
            "[set_team_active_state] Falha ao consolidar equipe %s: %s",
            actual_team_key, exc
        )

    return get_team(actual_team_key) or {**team, **payload, "active": active}


def save_team(
    team_key: str,
    payload: dict[str, Any],
    *,
    changed_by_name: str = "MONITOR WEB",
    changed_by_device_model: str = "DDS_TURNOS_MONITOR",
    consolidate: bool = True,
) -> dict[str, Any]:
    team_ref = db.collection(COLLECTION_NAME).document(team_key)
    previous_snap = team_ref.get()
    previous_data = previous_snap.to_dict() or {}
    previous_equipment = _read_equipment_map(previous_data)
    incoming_equipment = _read_equipment_map(payload)
    clean_equipment = _resolve_equipment_for_save(previous_equipment, incoming_equipment)

    # Garante que o teamKey salvo no documento seja o ID real (case-correct)
    team_key_to_save = previous_snap.id if previous_snap.exists else team_key

    clean_payload = {
        "teamKey": team_key_to_save,
        "displayName": str(payload.get("displayName") or team_key).strip(),
        "members": _string_list(payload.get("members")),
        "equipment": clean_equipment,
        "tablet": clean_equipment["tablet"]["summary"] or None,
        "cameraCopel": clean_equipment["cameraCopel"]["summary"] or None,
        "cameraVeicular": clean_equipment["cameraVeicular"]["summary"] or None,
        "active": bool(payload.get("active", True)),
    }

    team_ref.set(clean_payload, merge=True)
    _write_equipment_history(
        team_ref,
        team_key,
        previous_equipment,
        clean_equipment,
        changed_by_name=changed_by_name,
        changed_by_device_model=changed_by_device_model,
    )
    
    # Notifica o monitor sobre a mudança de forma granular (rápido)
    if consolidate:
        try:
            from services.turnos_service import consolidate_team_across_all_companies
            consolidate_team_across_all_companies(team_key)
        except Exception:
            pass
        
    return get_team(team_key) or {**clean_payload, "_exists": True}


def _resolve_equipment_for_save(
    previous_equipment: dict[str, dict[str, Any]],
    current_equipment: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for equipment_type in EQUIPMENT_TYPES:
        before = previous_equipment.get(equipment_type) or _normalize_equipment_payload({}, equipment_type)
        current = current_equipment.get(equipment_type) or _normalize_equipment_payload({}, equipment_type)
        changed = _equipment_history_signature(before) != _equipment_history_signature(current)
        merged = {
            **current,
            "lastChangedAt": before.get("lastChangedAt"),
            "lastChangeReason": before.get("lastChangeReason"),
        }
        if changed:
            change_reason = _clean_str(current.get("changeReason") or current.get("lastChangeReason"))
            if not change_reason:
                label = current.get("label") or before.get("label") or equipment_type
                raise ValueError(f"Informe o motivo da alteração do equipamento {label}.")
            merged["lastChangedAt"] = _utc_now_iso()
            merged["lastChangeReason"] = change_reason
        out[equipment_type] = _normalize_equipment_payload(merged, equipment_type)
    return out


def _write_equipment_history(
    team_ref,
    team_key: str,
    previous_equipment: dict[str, dict[str, Any]],
    current_equipment: dict[str, dict[str, Any]],
    *,
    changed_by_name: str,
    changed_by_device_model: str,
) -> None:
    for equipment_type in EQUIPMENT_TYPES:
        before = previous_equipment.get(equipment_type) or _normalize_equipment_payload({}, equipment_type)
        after = current_equipment.get(equipment_type) or _normalize_equipment_payload({}, equipment_type)
        if _equipment_history_signature(before) == _equipment_history_signature(after):
            continue

        team_ref.collection(EQUIPMENT_HISTORY_SUBCOLLECTION).document().set({
            "teamKey": team_key,
            "equipmentType": equipment_type,
            "equipmentLabel": after.get("label") or before.get("label") or EQUIPMENT_DEFAULTS.get(equipment_type, {}).get("label") or equipment_type,
            "before": _history_equipment_payload(before),
            "after": _history_equipment_payload(after),
            "changeReason": _clean_str(after.get("lastChangeReason")),
            "changedByName": _clean_str(changed_by_name) or "MONITOR WEB",
            "changedByDeviceModel": _clean_str(changed_by_device_model) or "DDS_TURNOS_MONITOR",
            "changedAt": firestore.SERVER_TIMESTAMP,
        })


def _read_equipment_map(source: dict[str, Any]) -> dict[str, dict[str, Any]]:
    structured = source.get("equipment") if isinstance(source, dict) else None
    out: dict[str, dict[str, Any]] = {}
    for equipment_type in EQUIPMENT_TYPES:
        value = None
        if isinstance(structured, dict):
            value = structured.get(equipment_type)
        if value is None and isinstance(source, dict):
            value = source.get(equipment_type)
        legacy_value = source.get(equipment_type) if isinstance(source, dict) else None
        out[equipment_type] = _normalize_equipment_payload(value or legacy_value, equipment_type)
    return out


def _normalize_equipment_payload(value: Any, equipment_type: str) -> dict[str, Any]:
    default = EQUIPMENT_DEFAULTS.get(equipment_type, {
        "kind": equipment_type,
        "label": equipment_type,
        "supportsPatrimonio": False,
        "supportsImei": False,
        "supportsPhoneNumber": False,
    })

    if isinstance(value, str):
        raw = value.strip()
        value = {"summary": raw, "serial": raw} if raw else {}
    elif not isinstance(value, dict):
        value = {}

    serial = _clean_str(value.get("serial"))
    patrimonio = _clean_str(value.get("patrimonio")) if default.get("supportsPatrimonio") else None
    imei = _clean_str(value.get("imei")) if default.get("supportsImei") else None
    phone_number = _clean_str(value.get("phoneNumber") or value.get("numeroTelefone")) if default.get("supportsPhoneNumber") else None
    email = _clean_str(value.get("email"))
    summary = _clean_str(value.get("summary")) or _summarize_equipment(serial, patrimonio, imei, phone_number, email)

    return {
        "kind": default["kind"],
        "label": default["label"],
        "summary": summary or "",
        "serial": serial,
        "patrimonio": patrimonio,
        "imei": imei,
        "phoneNumber": phone_number,
        "email": email,
        "lastChangedAt": _normalize_timestamp_string(value.get("lastChangedAt")),
        "lastChangeReason": _clean_str(value.get("lastChangeReason")),
        "changeReason": _clean_str(value.get("changeReason")),
        "supportsPatrimonio": bool(default.get("supportsPatrimonio")),
        "supportsImei": bool(default.get("supportsImei")),
        "supportsPhoneNumber": bool(default.get("supportsPhoneNumber")),
    }


def _summarize_equipment(serial: str | None, patrimonio: str | None, imei: str | None, phone_number: str | None, email: str | None) -> str:
    for candidate in (serial, patrimonio, imei, phone_number, email):
        text = _clean_str(candidate)
        if text:
            return text
    return ""


def _history_equipment_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": value.get("kind"),
        "label": value.get("label"),
        "summary": _clean_str(value.get("summary")),
        "serial": _clean_str(value.get("serial")),
        "patrimonio": _clean_str(value.get("patrimonio")),
        "imei": _clean_str(value.get("imei")),
        "phoneNumber": _clean_str(value.get("phoneNumber")),
        "email": _clean_str(value.get("email")),
        "lastChangedAt": _normalize_timestamp_string(value.get("lastChangedAt")),
        "lastChangeReason": _clean_str(value.get("lastChangeReason")),
    }


def _equipment_history_signature(value: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _clean_str(value.get("serial")),
        _clean_str(value.get("patrimonio")),
        _clean_str(value.get("imei")),
        _clean_str(value.get("phoneNumber")),
        _clean_str(value.get("email")),
    )


def _normalize_timestamp_string(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "to_datetime"):
        value = value.to_datetime()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    text = str(value).strip()
    return text or None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if item is None:
            continue
        name = str(item).strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out
