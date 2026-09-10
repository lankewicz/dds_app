# -----------------------------------------------------------------------------
# Arquivo : services/firestore_client.py
# Objetivo: Centralizar a criação do cliente Firestore usado pelo monitor.
# -----------------------------------------------------------------------------

from google.cloud import firestore


db = firestore.Client()
