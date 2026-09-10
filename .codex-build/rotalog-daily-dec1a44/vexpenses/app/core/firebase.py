# Finalidade: inicializar o SDK do Firebase Admin.
import firebase_admin
from firebase_admin import credentials, firestore, storage
import os

def initialize_firebase():
    """Inicializa o app Firebase se ainda não estiver inicializado."""
    if not firebase_admin._apps:
        # Tenta carregar credenciais do ambiente ou arquivo local
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        else:
            # No Cloud Run, ele usa as credenciais padrão do ambiente (Application Default Credentials)
            firebase_admin.initialize_app()

def get_firestore():
    initialize_firebase()
    return firestore.client()

def get_storage():
    initialize_firebase()
    return storage.bucket()

db = get_firestore()
# bucket = get_storage() # Opcional se for usar Storage
