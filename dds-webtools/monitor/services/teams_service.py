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

from services.firestore_client import db
import services.turnos_service as turnos_service


COLLECTION_NAME = "dds_teams"
TRASH_COLLECTION_NAME = "dds_teams_trash"
DDS_TRASH_COLLECTION_NAME = "dds_trash"
EQUIPMENT_HISTORY_SUBCOLLECTION = "equipment_history"
EQUIPMENT_TYPES = ("tablet", "cameraCopel", "cameraVeicular")


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
        "supportsPatrimonio": True,
        "supportsImei": False,
        "supportsPhoneNumber": False,
    },
}


def get_team(team_key: str) -> dict[str, Any] | None:
    snap = db.collection(COLLECTION_NAME).document(team_key).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    equipment = _read_equipment_map(data)
    data["teamKey"] = team_key
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
    return out


def move_to_trash(team_key: str) -> None:
    source_ref = db.collection(COLLECTION_NAME).document(team_key)
    dest_ref = db.collection(TRASH_COLLECTION_NAME).document(team_key)

    snap = source_ref.get()
    if not snap.exists:
        return

    data = snap.to_dict() or {}
    data["deletedAt"] = firestore.SERVER_TIMESTAMP
    
    # Inicia transação ou batch para garantir que tudo seja movido
    batch = db.batch()
    batch.set(dest_ref, data)
    
    # Move histórico de equipamentos
    history_snaps = source_ref.collection(EQUIPMENT_HISTORY_SUBCOLLECTION).get()
    for h_snap in history_snaps:
        h_dest_ref = dest_ref.collection(EQUIPMENT_HISTORY_SUBCOLLECTION).document(h_snap.id)
        batch.set(h_dest_ref, h_snap.to_dict())
        batch.delete(h_snap.reference)
    
    batch.delete(source_ref)
    batch.commit()

    # Move registros de DDS (Treinamentos/Histórico) para a lixeira de DDS
    _move_dds_records(team_key, turnos_service.DDS_COLLECTION, DDS_TRASH_COLLECTION_NAME)

    # Remove o estado em tempo real (turno) para evitar que o monitor a recrie como inativa
    for empresa_snap in db.collection("turno").stream():
        doc_ref = empresa_snap.reference.collection("equipes").document(team_key)
        doc_ref.delete()


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


def permanently_delete(team_key: str) -> None:
    # 1. Deleta da lixeira (e seu histórico)
    trash_ref = db.collection(TRASH_COLLECTION_NAME).document(team_key)
    _delete_doc_and_subcollections(trash_ref)
    
    # 2. Deleta também da coleção principal (caso esteja lá por algum motivo)
    main_ref = db.collection(COLLECTION_NAME).document(team_key)
    _delete_doc_and_subcollections(main_ref)

    # 3. Deleta registros de turno e histórico de DDS (coleção principal)
    turnos_service.delete_team_runtime_and_history(team_key)

    # 4. Limpa também a lixeira de DDS
    _delete_dds_trash_records(team_key)


def _move_dds_records(team_key: str, source_col: str, dest_col: str) -> None:
    """
    Move registros de DDS entre as coleções principal e lixeira.
    Isso garante que treinamentos 'sumam' dos relatórios ao ir para a lixeira.
    """
    # Identifica as chaves de busca (literal e normalizada se necessário)
    keys = {team_key}
    
    for key in keys:
        query = db.collection(source_col).where("equipe", "==", key)
        snaps = query.get()
        if not snaps:
            continue
            
        # Processa em lotes (Firestore limit 500)
        for i in range(0, len(snaps), 400):
            chunk = snaps[i : i + 400]
            batch = db.batch()
            for snap in chunk:
                batch.set(db.collection(dest_col).document(snap.id), snap.to_dict())
                batch.delete(snap.reference)
            batch.commit()


def _delete_dds_trash_records(team_key: str) -> None:
    """
    Remove permanentemente registros de DDS da lixeira.
    """
    query = db.collection(DDS_TRASH_COLLECTION_NAME).where("equipe", "==", team_key)
    snaps = query.get()
    for i in range(0, len(snaps), 400):
        chunk = snaps[i : i + 400]
        batch = db.batch()
        for snap in chunk:
            batch.delete(snap.reference)
        batch.commit()


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
    dds_query = db.collection(turnos_service.DDS_COLLECTION).where("equipe", "==", team_key)
    dds_snaps = dds_query.get()
    dds_count = len(dds_snaps)
    
    return {
        "teamKey": team_key,
        "displayName": team_doc.get("displayName") or team_key,
        "membersCount": len(team_doc.get("members") or []),
        "ddsCount": dds_count,
        "equipmentHistoryCount": history_count,
    }


def _delete_doc_and_subcollections(doc_ref) -> None:
    # Deleta histórico de equipamentos
    history_snaps = doc_ref.collection(EQUIPMENT_HISTORY_SUBCOLLECTION).get()
    for h_snap in history_snaps:
        h_snap.reference.delete()
    
    # Deleta o documento principal
    doc_ref.delete()


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


def save_team(
    team_key: str,
    payload: dict[str, Any],
    *,
    changed_by_name: str = "MONITOR WEB",
    changed_by_device_model: str = "DDS_TURNOS_MONITOR",
) -> dict[str, Any]:
    team_ref = db.collection(COLLECTION_NAME).document(team_key)
    previous_snap = team_ref.get()
    previous_data = previous_snap.to_dict() or {}
    previous_equipment = _read_equipment_map(previous_data)
    incoming_equipment = _read_equipment_map(payload)
    clean_equipment = _resolve_equipment_for_save(previous_equipment, incoming_equipment)

    clean_payload = {
        "teamKey": team_key,
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
