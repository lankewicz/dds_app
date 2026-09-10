import os
import sys
from pathlib import Path

# Adiciona o diretório raiz ao sys.path para conseguir importar as configurações do app
sys.path.append(str(Path(__file__).parent.parent))

try:
    from app.core.firestore import db
    from google.cloud import firestore
    print("✅ Conectado ao Firestore com sucesso.")
except ImportError as e:
    print(f"❌ Erro ao importar dependências: {e}")
    print("Certifique-se de rodar o script a partir da raiz do projeto.")
    sys.exit(1)

def migrate_glosa():
    root_doc = db.collection("vexpenses").document("data")
    col_ref = root_doc.collection("balance_requests")
    
    print("🔍 Buscando registros para migração...")
    # Buscamos todos os documentos. 
    # Poderíamos filtrar por quem não tem o campo, mas o stream() é eficiente.
    docs = list(col_ref.stream())
    total = len(docs)
    print(f"📊 Total de registros encontrados: {total}")
    
    batch = db.batch()
    count = 0
    updated = 0
    skipped = 0
    
    for i, doc in enumerate(docs):
        data = doc.to_dict()
        
        # Se já tiver os campos, pulamos para economizar escrita
        if "valor_glosa" in data and "valor_repro" in data:
            skipped += 1
            continue
            
        sol = float(data.get("valor_solicitado") or 0)
        app = float(data.get("valor_aprovado") or 0)
        status = str(data.get("status") or "").lower()
        
        v_glosa = 0.0
        v_repro = 0.0
        
        if "reprov" in status:
            v_repro = round(sol, 2)
        elif "aprov" in status:
            v_glosa = round(max(0.0, sol - app), 2)
        
        # Prepara a atualização
        batch.update(doc.reference, {
            "valor_glosa": v_glosa,
            "valor_repro": v_repro
        })
        
        count += 1
        updated += 1
        
        # O Firestore permite no máximo 500 operações por batch
        if count >= 450:
            print(f"🚀 Enviando lote de 450 atualizações ({i+1}/{total})...")
            batch.commit()
            batch = db.batch()
            count = 0
            
    # Envia o restante
    if count > 0:
        print(f"🚀 Enviando lote final de {count} atualizações...")
        batch.commit()
        
    print("\n✅ MIGRACAO CONCLUIDA!")
    print(f"📝 Atualizados: {updated}")
    print(f"⏭️  Pulados (já tinham o campo): {skipped}")
    print(f"📈 Total processado: {total}")

if __name__ == "__main__":
    confirm = input("⚠️ Isso atualizará TODOS os registros no Firestore. Deseja continuar? (s/n): ")
    if confirm.lower() == 's':
        migrate_glosa()
    else:
        print("❌ Operação cancelada.")
