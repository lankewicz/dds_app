import os
import firebase_admin
from firebase_admin import credentials, firestore

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = r'd:\programas\DDS\firebase_config.json'
cred = credentials.Certificate(r'd:\programas\DDS\firebase_config.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

docs = db.collection('dds_producao_mensal').stream()
competencias = set()
for d in docs:
    data = d.to_dict()
    competencias.add(f"{data.get('year')}-{data.get('monthNumber'):02d}")

print(f"Competencias encontradas: {sorted(list(competencias))}")
