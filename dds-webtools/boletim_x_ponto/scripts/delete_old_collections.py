# d:\programas\DDS\dds-webtools\boletim_x_ponto\scripts\delete_old_collections.py
import os
import sys
from pathlib import Path
from google.cloud import firestore

# Setup path so we can import firestore client config if needed
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Setup Google Application Credentials for local execution
local_key = r"d:\programas\DDS\firebase_config.json"
if os.path.exists(local_key):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_key
    print(f"Using local credentials: {local_key}")

db = firestore.Client()

def print_progress_bar(iteration: int, total: int, prefix: str = '', suffix: str = '', decimals: int = 1, length: int = 40, fill: str = '█', print_end: str = "\r"):
    """
    Call in a loop to create terminal progress bar.
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    print(f'\r{prefix} |{bar}| {percent}% {suffix}', end=print_end)
    if iteration == total: 
        print()

def delete_collection_in_batches(collection_name: str):
    print(f"Fetching document references from collection '{collection_name}'...")
    
    # Use select([]) to only retrieve document IDs (fast and cheap)
    docs = list(db.collection(collection_name).select([]).stream())
    total_docs = len(docs)
    
    if total_docs == 0:
        print(f"Collection '{collection_name}' is empty or does not exist. Skipping.\n")
        return
        
    print(f"Deleting {total_docs} documents from '{collection_name}'...")
    print_progress_bar(0, total_docs, prefix='Progress:', suffix='Complete', length=40)
    
    batch = db.batch()
    count = 0
    deleted_count = 0
    
    for doc in docs:
        batch.delete(doc.reference)
        count += 1
        deleted_count += 1
        
        if count >= 500:
            batch.commit()
            batch = db.batch()
            count = 0
            
        print_progress_bar(deleted_count, total_docs, prefix='Progress:', suffix=f'({deleted_count}/{total_docs})', length=40)
        
    if count > 0:
        batch.commit()
        print_progress_bar(total_docs, total_docs, prefix='Progress:', suffix=f'({total_docs}/{total_docs})', length=40)
        
    print(f"Collection '{collection_name}' deleted successfully!\n")

def main():
    print("Starting deletion of old root-level Firestore collections...\n")
    
    old_collections = [
        "webtools_boletim_x_ponto_mappings",
        "webtools_boletim_x_ponto_boletins",
        "webtools_boletim_x_ponto_ponto",
        "webtools_boletim_x_ponto_vars",
        "webtools_boletim_x_ponto_contrato_boletim",
        "webtools_boletim_x_ponto"  # Metadata collection
    ]
    
    for coll in old_collections:
        try:
            delete_collection_in_batches(coll)
        except Exception as e:
            print(f"Error deleting collection '{coll}': {e}\n")
            
    print("Cleanup process finished!")

if __name__ == "__main__":
    main()
