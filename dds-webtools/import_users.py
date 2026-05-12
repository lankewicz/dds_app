import pandas as pd
import os
import sys

# Ajusta path para importar o client do firestore
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(base_dir, "monitor"))

# Configuração de Credenciais
local_key = r"d:\programas\DDS\firebase_config.json"
if os.path.exists(local_key):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_key

from services.firestore_client import db

def import_whitelist():
    csv_path = os.path.join(base_dir, "users_12_05_2026 12_16_43.csv")
    if not os.path.exists(csv_path):
        print(f"Erro: Arquivo {csv_path} não encontrado.")
        return

    print(f"Lendo {csv_path}...")
    df = pd.read_csv(csv_path)
    
    # A coluna de e-mail no seu CSV é 'User principal name'
    emails = df['User principal name'].dropna().unique()
    
    print(f"Encontrados {len(emails)} e-mails únicos. Iniciando importação para 'dds_users'...")
    
    batch = db.batch()
    count = 0
    
    for email in emails:
        email = email.lower().strip()
        user_ref = db.collection("dds_users").document(email)
        batch.set(user_ref, {
            "email": email,
            "active": True,
            "role": "user", # Padrão inicial
            "imported_at": pd.Timestamp.now()
        }, merge=True)
        
        count += 1
        if count % 400 == 0:
            batch.commit()
            batch = db.batch()
            print(f"Processados {count}...")

    batch.commit()
    print(f"Sucesso! {count} usuários importados para a whitelist.")

if __name__ == "__main__":
    import_whitelist()
