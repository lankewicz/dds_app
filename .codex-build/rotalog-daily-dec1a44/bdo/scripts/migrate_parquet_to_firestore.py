# d:\programas\DDS\dds-webtools\bdo\scripts\migrate_parquet_to_firestore.py
import os
import sys
from pathlib import Path
import pandas as pd
from google.cloud import firestore

# Setup path so we can import firestore client config if needed
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Setup Google Application Credentials for local execution
local_key = r"d:\programas\DDS\firebase_config.json"
if os.path.exists(local_key):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_key
    print(f"Using local credentials: {local_key}")

db = firestore.Client()
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

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

def upload_collection_in_batches(subcollection_name: str, records: list, doc_id_field: str | None = None):
    print(f"Uploading {len(records)} records to subcollection 'webtools/bdo/{subcollection_name}'...")
    parent_doc = db.collection("webtools").document("bdo")
    coll_ref = parent_doc.collection(subcollection_name)
    
    batch = db.batch()
    count = 0
    total_uploaded = 0
    total_records = len(records)

    if total_records == 0:
        print(f"No records to upload to {subcollection_name}.\n")
        return

    print_progress_bar(0, total_records, prefix='Progress:', suffix='Complete', length=40)

    for record in records:
        # Resolve document reference
        if doc_id_field and record.get(doc_id_field):
            doc_id = str(record[doc_id_field]).strip()
            doc_ref = coll_ref.document(doc_id)
        else:
            doc_ref = coll_ref.document()

        batch.set(doc_ref, record)
        count += 1
        total_uploaded += 1

        if count >= 500:
            batch.commit()
            batch = db.batch()
            count = 0
            
        print_progress_bar(total_uploaded, total_records, prefix='Progress:', suffix=f'({total_uploaded}/{total_records})', length=40)

    if count > 0:
        batch.commit()
        print_progress_bar(total_records, total_records, prefix='Progress:', suffix=f'({total_records}/{total_records})', length=40)
    print(f"Finished uploading to {subcollection_name}!\n")

def clean_dict(d: dict) -> dict:
    cleaned = {}
    for k, v in d.items():
        if pd.isna(v):
            cleaned[k] = None
        elif isinstance(v, (pd.Timestamp, pd.DatetimeTZDtype)):
            cleaned[k] = v.strftime("%Y-%m-%d")
        else:
            cleaned[k] = v
    return cleaned

def main():
    print("Starting Parquet to Firestore Migration...\n")

    # 1. Relação Nomes (Mappings)
    path_mappings = DATA_DIR / "relacao_nomes.parquet"
    if path_mappings.exists():
        df_map = pd.read_parquet(path_mappings)
        # Saneamento de colunas e nomes
        df_map = df_map.drop_duplicates(subset=["Nome_Boletim"], keep="last")
        records_map = []
        for _, row in df_map.iterrows():
            d = row.to_dict()
            # Certificar de que as chaves não têm acentuação corrompida ou espaços indesejados
            cleaned = {
                "Nome_Boletim": str(d.get("Nome_Boletim", "")).strip(),
                "Nome_Ponto_Mapeado": str(d.get("Nome_Ponto_Mapeado", "")).strip(),
                "CPF_Ponto": str(d.get("CPF_Ponto", "")).strip(),
                "PIS_Ponto": str(d.get("PIS_Ponto", "")).strip()
            }
            records_map.append(cleaned)
        
        # O ID do documento será o Nome_Boletim normalizado para evitar duplicados
        upload_collection_in_batches("mappings", records_map, doc_id_field="Nome_Boletim")
    else:
        print("relacao_nomes.parquet not found, skipping mappings migration.")

    # 2. Registro Boletim
    path_boletim = DATA_DIR / "RegistroBoletim.parquet"
    contratos = set()
    funcionarios_boletim = set()
    datas_boletim = []

    if path_boletim.exists():
        df_bol = pd.read_parquet(path_boletim)
        
        # Normalizar colunas de acentuação corrompida
        col_map = {}
        for col in df_bol.columns:
            if "Funcion" in col:
                col_map[col] = "Funcionário"
            elif "Medi" in col:
                col_map[col] = "Data de Medição"
        if col_map:
            df_bol = df_bol.rename(columns=col_map)

        # Trata tipos e limpa registros duplicados
        df_bol = df_bol.drop_duplicates(subset=["chave_unica"])
        
        records_bol = []
        for _, row in df_bol.iterrows():
            d = row.to_dict()
            cleaned = clean_dict(d)
            
            # Padroniza strings
            cleaned["BOLETIM"] = str(cleaned.get("BOLETIM", "")).strip()
            cleaned["Contrato"] = str(cleaned.get("Contrato", "")).strip()
            cleaned["Registro"] = str(cleaned.get("Registro", "")).strip()
            cleaned["Funcionário"] = str(cleaned.get("Funcionário", "")).strip()
            
            if cleaned["Contrato"]:
                contratos.add(cleaned["Contrato"])
            if cleaned["Funcionário"]:
                funcionarios_boletim.add(cleaned["Funcionário"])
            if cleaned.get("DATA"):
                datas_boletim.append(cleaned["DATA"])
                
            records_bol.append(cleaned)

        upload_collection_in_batches("boletins", records_bol, doc_id_field="chave_unica")
    else:
        print("RegistroBoletim.parquet not found, skipping boletins migration.")

    # 3. Registro Ponto
    path_ponto = DATA_DIR / "RegistroPonto.parquet"
    nomes_ponto = set()
    datas_ponto = []

    if path_ponto.exists():
        df_pto = pd.read_parquet(path_ponto)
        df_pto = df_pto.drop_duplicates(subset=["chave_unica"])
        
        records_pto = []
        for _, row in df_pto.iterrows():
            d = row.to_dict()
            cleaned = clean_dict(d)
            
            cleaned["Nome"] = str(cleaned.get("Nome", "")).strip()
            cleaned["CPF"] = str(cleaned.get("CPF", "")).strip()
            cleaned["PIS"] = str(cleaned.get("PIS", "")).strip()
            
            if cleaned["Nome"]:
                nomes_ponto.add(cleaned["Nome"])
            if cleaned.get("Data"):
                datas_ponto.append(cleaned["Data"])
                
            records_pto.append(cleaned)
            
        upload_collection_in_batches("ponto", records_pto, doc_id_field="chave_unica")
    else:
        print("RegistroPonto.parquet not found, skipping ponto migration.")

    # 4. Calcular e salvar Metadados
    print("Calculating and uploading metadata...")
    all_dates = datas_boletim + datas_ponto
    data_min = min(all_dates) if all_dates else "2026-05-21"
    data_max = max(all_dates) if all_dates else "2026-05-21"

    meta_doc = {
        "contratos": sorted(list(contratos)),
        "data_min": data_min,
        "data_max": data_max,
        "nomes_ponto": sorted(list(nomes_ponto)),
        "funcionarios_boletim": sorted(list(funcionarios_boletim))
    }

    db.collection("webtools").document("bdo").set(meta_doc)
    print("Metadata written successfully to webtools/bdo:")
    print(f"  Contracts: {meta_doc['contratos']}")
    print(f"  Date range: {data_min} to {data_max}")
    print(f"  Unique Ponto Names: {len(nomes_ponto)}")
    print(f"  Unique Boletim Employees: {len(funcionarios_boletim)}")
    print("\nMigration finished successfully!")

if __name__ == "__main__":
    main()
