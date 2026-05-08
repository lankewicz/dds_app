import sys
import os

# Adiciona os caminhos necessários
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(base_dir, "monitor"))

try:
    from services.firestore_client import db
    
    # Verifica um documento de equipe
    doc = next(db.collection("dds_teams").limit(1).stream(), None)
    if doc:
        print("Exemplo de Equipe (dds_teams):")
        print(doc.to_dict())
    else:
        print("Nenhuma equipe encontrada em dds_teams")
        
    # Verifica um documento de produção
    prod_doc = next(db.collection("dds_producao_mensal").limit(1).stream(), None)
    if prod_doc:
        print("\nExemplo de Produção (dds_producao_mensal):")
        print(prod_doc.to_dict())
    else:
        print("\nNenhuma produção encontrada em dds_producao_mensal")

except Exception as e:
    print(f"Erro: {e}")
