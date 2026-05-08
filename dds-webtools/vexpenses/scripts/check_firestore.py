from google.cloud import firestore

# Especificando o projeto explicitamente
db = firestore.Client(project="dds-treinamentos")
collections = ["vexpenses_balance_requests", "vexpenses_import_batches", "vexpenses_import_errors"]

print("--- Diagnóstico Firestore VExpenses ---")
for col_name in collections:
    try:
        # Nota: select([]) evita baixar os dados completos, apenas conta
        docs = db.collection(col_name).select([]).get()
        print(f"Coleção '{col_name}': {len(docs)} documentos encontrados.")
        
        if len(docs) > 0:
            # Pegar um exemplo completo para ver as chaves
            sample = db.collection(col_name).limit(1).get()[0].to_dict()
            print(f"  Chaves do exemplo: {list(sample.keys())}")
            if 'data_solicitacao' in sample:
                print(f"  Valor de data_solicitacao: {sample['data_solicitacao']} (tipo: {type(sample['data_solicitacao'])})")
    except Exception as e:
        print(f"Erro ao acessar {col_name}: {e}")
print("---------------------------------------")
