"""Importa tipo de equipe e dados de tablet da planilha previamente extraída.

Por padrão apenas simula. Use ``--apply`` para gravar no Firestore.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.cloud import firestore


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "monitor"))

from services.firestore_client import db  # noqa: E402


TYPE_MAP = {
    "NR-10": "STC",
    "NR-10 - CESTO": "STC_CESTO",
    "EP": "EP",
    "LV": "LINHA_VIVA",
}
IGNORED_TABLET_VALUES = {"CA826 / CA 061", "CA826 / CA061"}
SOURCE_NAME = "Pasta2.xlsx"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_identifier(value: Any) -> str:
    raw = _text(value).upper()
    if raw in IGNORED_TABLET_VALUES:
        return ""
    text = re.sub(r"\s+", "", raw)
    return text if re.fullmatch(r"[A-Z]{1,3}\d{2,5}", text) else ""


def _normalize_phone(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    digits = re.sub(r"\D", "", str(value))
    return digits if 10 <= len(digits) <= 13 else ""


def _empty_equipment(kind: str, label: str) -> dict[str, Any]:
    return {
        "kind": kind, "label": label, "summary": "", "identifier": None,
        "serial": None, "patrimonio": None, "imei": None, "phoneNumber": None,
        "email": None, "lastChangedAt": None, "lastChangeReason": None,
    }


def _equipment_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    structured = data.get("equipment") if isinstance(data.get("equipment"), dict) else {}
    definitions = {"tablet": "Tablet", "cameraCopel": "Câmera Copel", "cameraVeicular": "Câmera veicular"}
    result: dict[str, dict[str, Any]] = {}
    for kind, label in definitions.items():
        raw = structured.get(kind)
        if not isinstance(raw, dict):
            legacy = data.get(kind)
            raw = {"summary": legacy, "serial": legacy} if isinstance(legacy, str) else {}
        result[kind] = {**_empty_equipment(kind, label), **raw, "kind": kind, "label": label}
    return result


def _history_value(value: dict[str, Any]) -> dict[str, Any]:
    allowed = ("kind", "label", "summary", "identifier", "serial", "patrimonio", "imei", "phoneNumber", "email", "lastChangedAt", "lastChangeReason")
    return {key: value.get(key) for key in allowed}


def build_changes(rows: list[dict[str, Any]], teams: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    changes: list[dict[str, Any]] = []
    missing: list[str] = []
    for row in rows:
        team_key = _text(row.get("vehicle")).upper()
        snap = teams.get(team_key)
        if not snap:
            missing.append(team_key)
            continue

        before = snap.to_dict() or {}
        update: dict[str, Any] = {}
        fields: list[dict[str, Any]] = []
        mapped_type = TYPE_MAP.get(_text(row.get("type")).upper())
        current_type = _text(before.get("teamType")).upper()
        if mapped_type and current_type != mapped_type:
            update["teamType"] = mapped_type
            fields.append({"field": "teamType", "before": before.get("teamType"), "after": mapped_type})

        equipment_before = _equipment_map(before)
        equipment_after = copy.deepcopy(equipment_before)
        tablet = equipment_after["tablet"]
        identifier = _normalize_identifier(row.get("tablet"))
        phone = _normalize_phone(row.get("tabletNumberRaw"))
        equipment_fields: list[dict[str, Any]] = []
        if identifier and not _text(tablet.get("identifier")):
            tablet["identifier"] = identifier
            equipment_fields.append({"field": "equipment.tablet.identifier", "before": None, "after": identifier})
        if phone and not _text(tablet.get("phoneNumber")):
            tablet["phoneNumber"] = phone
            equipment_fields.append({"field": "equipment.tablet.phoneNumber", "before": None, "after": phone})

        if equipment_fields:
            tablet["lastChangedAt"] = datetime.now(timezone.utc)
            tablet["lastChangeReason"] = "Importação inicial da planilha de equipes"
            if not _text(tablet.get("summary")):
                tablet["summary"] = identifier or phone
            update["equipment"] = equipment_after
            if not _text(before.get("tablet")):
                update["tablet"] = tablet.get("summary") or None
            fields.extend(equipment_fields)

        if update:
            changes.append({
                "teamKey": snap.id, "ref": snap.reference, "update": update,
                "fields": fields, "equipmentBefore": equipment_before,
                "equipmentAfter": equipment_after, "equipmentChanged": bool(equipment_fields),
                "excelRow": row.get("excelRow"),
            })
    return changes, missing


def apply_changes(changes: list[dict[str, Any]]) -> None:
    batch = db.batch()
    for item in changes:
        batch.set(item["ref"], item["update"], merge=True)
        if item["equipmentChanged"]:
            batch.set(item["ref"].collection("equipment_history").document(), {
                "teamKey": item["teamKey"], "equipmentType": "tablet", "equipmentLabel": "Tablet",
                "before": _history_value(item["equipmentBefore"]["tablet"]),
                "after": _history_value(item["equipmentAfter"]["tablet"]),
                "changeReason": "Importação inicial da planilha de equipes",
                "changedByName": "IMPORTAÇÃO CONTROLADA", "changedByDeviceModel": "DDS_WEBTOOLS",
                "origin": "spreadsheet_import", "source": SOURCE_NAME,
                "changedAt": firestore.SERVER_TIMESTAMP,
            })
        batch.set(db.collection("portal_change_audit").document(), {
            "action": "team_metadata_imported", "teamKey": item["teamKey"],
            "actorEmail": "valdinei.pco@gmail.com", "origin": "spreadsheet_import",
            "source": SOURCE_NAME, "sourceRow": item["excelRow"], "changes": item["fields"],
            "createdAt": firestore.SERVER_TIMESTAMP,
        })
    batch.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rows_json", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rows = json.loads(args.rows_json.read_text(encoding="utf-8"))
    snaps = list(db.collection("dds_teams").stream())
    changes, missing = build_changes(rows, {snap.id.upper(): snap for snap in snaps})

    field_counts: dict[str, int] = {}
    for item in changes:
        for field in item["fields"]:
            field_counts[field["field"]] = field_counts.get(field["field"], 0) + 1
    print(json.dumps({
        "mode": "apply" if args.apply else "dry-run", "spreadsheetRows": len(rows),
        "firestoreTeams": len(snaps), "teamsChanged": len(changes),
        "fieldChanges": field_counts, "missingTeams": sorted(set(missing)),
        "teams": [{"teamKey": item["teamKey"], "fields": item["fields"]} for item in changes],
    }, ensure_ascii=False, indent=2, default=str))
    if args.apply and changes:
        apply_changes(changes)
        print(json.dumps({"applied": len(changes), "status": "ok"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
