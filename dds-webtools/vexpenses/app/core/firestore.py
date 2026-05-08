from google.cloud import firestore

db = firestore.Client()

# Referências unificadas no Firestore
ROOT_DOC = db.collection("vexpenses").document("data")
COL_REQUESTS = ROOT_DOC.collection("balance_requests")
COL_SUMMARIES = ROOT_DOC.collection("summaries")
COL_BATCHES = ROOT_DOC.collection("import_batches")
COL_ERRORS = ROOT_DOC.collection("import_errors")
COL_CONSISTENCY = ROOT_DOC.collection("consistency_reports")
COL_SYSTEM_TASKS = ROOT_DOC.collection("system_tasks")
