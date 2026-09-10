import sys
import os

# Adiciona o diretório raiz ao path para importar os serviços
sys.path.append(os.path.join(os.getcwd(), "monitor"))

from services.firestore_client import db
from services.turnos_service import update_realtime_view

def migrate_and_sync():
    print("Iniciando migracao e sincronismo inicial...")

    # 1. Migrar Configuracoes
    print("Migrando configuracoes...")
    old_config = db.collection("app_config").document("monitor_turnos").get()
    if old_config.exists:
        db.collection("monitor").document("config").set(old_config.to_dict())
        print("Configuracoes migradas.")
    else:
        print("Nenhuma configuracao antiga encontrada.")

    # 2. Migrar Requests de Prefixo
    print("Migrando solicitacoes de prefixo...")
    old_requests = db.collection("prefix_change_requests").get()
    for doc in old_requests:
        db.collection("monitor/requests/prefix_changes").document(doc.id).set(doc.to_dict())
        doc.reference.delete()
    print(f"{len(old_requests)} solicitacoes migradas.")

    # 3. Migrar Lixeira de Equipes
    print("Migrando lixeira de equipes...")
    old_trash_teams = db.collection("dds_teams_trash").get()
    for doc in old_trash_teams:
        db.collection("monitor/trash/dds_teams").document(doc.id).set(doc.to_dict())
        doc.reference.delete()
    print(f"{len(old_trash_teams)} equipes migradas na lixeira.")

    # 4. Migrar Lixeira de DDS
    print("Migrando lixeira de DDS...")
    old_trash_dds = db.collection("dds_trash").get()
    for doc in old_trash_dds:
        db.collection("monitor/trash/DDS").document(doc.id).set(doc.to_dict())
        doc.reference.delete()
    print(f"{len(old_trash_dds)} registros de DDS migrados na lixeira.")

    # 5. Sincronismo Inicial do Realtime
    print("Gerando visualizacao em tempo real (onSnapshot)...")
    try:
        res = update_realtime_view()
        print(f"Sincronismo concluido: {res.get('teamsSynced')} equipes processadas.")
    except Exception as e:
        print(f"Erro no sincronismo: {e}")

    print("\nTudo pronto! O Monitor ja pode ser utilizado com os dados antigos.")

if __name__ == "__main__":
    migrate_and_sync()
