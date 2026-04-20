import os
import firebase_admin
from firebase_admin import firestore

# Garante credenciais iguais às do backup
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "init/serviceAccountKey.json")

if not firebase_admin._apps:
    firebase_admin.initialize_app()

db = firestore.client()

def main():
    print("\n=== Listando coleções disponíveis ===")
    for c in db.collections():
        print("-", c.id)
    print("=" * 40)

    # Troque abaixo pelo nome que você quer inspecionar
    col_name = os.getenv("FIRESTORE_COLLECTION", "Treinamentos")
    print("Usando coleção:", col_name)

    col = db.collection(col_name)
    docs = list(col.limit(5).stream())
    print(f"Total retornado (sem filtro): {len(docs)}")

    for d in docs:
        data = d.to_dict() or {}
        print("ID:", d.id)
        # Mostra todos os campos conhecidos
        for k, v in data.items():
            print(f"  {k}: {v}")
        print("-" * 40)


if __name__ == "__main__":
    main()
