"""
Script para fechar o turno de TODAS as equipes no Firestore.
Atualiza turno/ChicoEletro/equipes e empresas/ChicoEletro/turnos_estado,
definindo estado = 'FECHADO' e isOpen = False.
"""

from __future__ import annotations

import datetime
import os
import sys
from typing import Any

# Adiciona dds-webtools e monitor ao sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, root_dir)
sys.path.insert(0, os.path.join(root_dir, "monitor"))

from google.cloud import firestore
from monitor.services.firestore_client import db
from monitor.services.turnos_service import consolidate_single_team


def fechar_todos_os_turnos(empresa: str = "ChicoEletro") -> dict[str, Any]:
    print(f"Iniciando fechamento de turnos para todas as equipes da empresa '{empresa}'...")
    
    col_ref = db.collection("turno").document(empresa).collection("equipes")
    snaps = list(col_ref.stream())
    
    if not snaps:
        print("Nenhuma equipe encontrada em turno/equipes.")
        return {"status": "success", "closed_count": 0}

    timestamp_now = datetime.datetime.now(datetime.timezone.utc)
    timestamp_ms = int(timestamp_now.timestamp() * 1000)
    timestamp_iso = timestamp_now.isoformat()

    batch = db.batch()
    op_count = 0
    closed_count = 0

    for snap in snaps:
        team_key = snap.id
        doc_data = snap.to_dict() or {}
        
        update_payload = {
            "empresa": empresa,
            "equipe": doc_data.get("equipe") or team_key,
            "estado": "FECHADO",
            "isOpen": False,
            "closedAtClientMs": timestamp_ms,
            "clientUpdatedAtMs": timestamp_ms,
            "updatedAtIso": timestamp_iso,
            "serverUpdatedAt": firestore.SERVER_TIMESTAMP,
            "deviceIdLastWriter": "ADMIN_FECHAR_TODOS",
            "origemAtualizacao": "ADMIN_FECHAR_TODOS",
            "monitorStatus": "FECHADO"
        }

        # 1. Atualiza coleção oficial: turno/{empresa}/equipes/{team_key}
        ref_dds_app = db.collection("turno").document(empresa).collection("equipes").document(team_key)
        batch.set(ref_dds_app, update_payload, merge=True)

        # 2. [OTIMIZAÇÃO FIREBASE]: Gravação na coleção legada 'empresas/turnos_estado' desativada.
        # Descomente abaixo para reativar caso necessário:
        # ref_dds_web = db.collection("empresas").document(empresa).collection("turnos_estado").document(team_key)
        # batch.set(ref_dds_web, update_payload, merge=True)

        op_count += 1
        closed_count += 1

        if op_count >= 400:
            batch.commit()
            batch = db.batch()
            op_count = 0

    if op_count > 0:
        batch.commit()

    print(f"Atualizados {closed_count} documentos de equipes para estado 'FECHADO'.")

    # Consolida cada equipe para atualizar a visão em tempo real
    print("Consolidando visão do monitor em tempo real...")
    for snap in snaps:
        try:
            consolidate_single_team(empresa, snap.id)
        except Exception as e:
            print(f"Erro ao consolidar {snap.id}: {e}")

    print("Concluído com sucesso!")
    return {
        "status": "success",
        "closed_count": closed_count,
        "timestamp_iso": timestamp_iso
    }


if __name__ == "__main__":
    fechar_todos_os_turnos()
