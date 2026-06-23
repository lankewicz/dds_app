import os
import json
from google.cloud import firestore

local_key = r"d:\programas\DDS\firebase_config.json"
if os.path.exists(local_key):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_key

db = firestore.Client()
BASE_DOC_PATH = db.collection("webtools").document("producao")

INDEX_FILE = r"d:\programas\DDS\dds-webtools\controle_projetos\static\images\estruturas\estruturas_index.json"

def populate_db():
    if not os.path.exists(INDEX_FILE):
        print(f"Erro: Arquivo {INDEX_FILE} nao encontrado!")
        return

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    collection_ref = BASE_DOC_PATH.collection("estruturas_padrao")
    
    total_added = 0
    total_skipped = 0

    print("Buscando documentos existentes no Firestore para conferência local...")
    try:
        existing_docs = {doc.id: doc.to_dict() for doc in collection_ref.stream()}
        print(f"Encontrados {len(existing_docs)} documentos já existentes no Firestore.")
    except Exception as e:
        print(f"Erro ao obter documentos existentes: {e}. Prosseguindo considerando banco vazio.")
        existing_docs = {}

    print("Iniciando populacao do banco de dados no Firestore...")

    for net_type, structures in data.items():
        print(f"Rede: {net_type}")
        for est in structures:
            name = est["estrutura"]
            doc_id = f"{net_type}_{name}"
            
            doc_ref = collection_ref.document(doc_id)
            
            # Imagens
            imagens = []
            if est["desenho"]:
                imagens.append(est["desenho"])
            if est["titulo"]:
                imagens.append(est["titulo"])
                
            payload = {
                "id": doc_id,
                "nome": name,
                "tipo_rede": net_type,
                "imagens": imagens,
                "ativo": True
            }
            
            if doc_id not in existing_docs:
                # Inicializar array de atividades vazio se for novo
                payload["atividades"] = []
                doc_ref.set(payload)
                print(f"  [NOVO] Estrutura {doc_id} adicionada.")
                total_added += 1
            else:
                # Se ja existe, atualizar apenas campos basicos e preservar as atividades ja salvas
                existing_data = existing_docs[doc_id]
                payload["atividades"] = existing_data.get("atividades", [])
                doc_ref.update(payload)
                print(f"  [ATUALIZADO] Estrutura {doc_id} atualizada (preservando atividades).")
                total_skipped += 1

    print(f"\nConcluido! {total_added} novos registros adicionados, {total_skipped} atualizados.")

if __name__ == "__main__":
    populate_db()
