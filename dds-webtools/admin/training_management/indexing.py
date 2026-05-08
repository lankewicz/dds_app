"""
============================================================
FILE: training_management/indexing.py
FUNCTION: Rebuild the DDSv2/lista.json index from scratch by
          scanning the bucket and applying cleanup rules.
============================================================
"""

from __future__ import annotations
import json
import re
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
from typing import Any, Dict, List, Set

from google.cloud import storage

logger = logging.getLogger(__name__)

def rebuild_lista_json(
    *,
    bucket_name: str,
    base_prefix: str,
    timezone_name: str = "America/Sao_Paulo",
    past_keep_count: int = 5,
) -> Dict[str, Any]:
    """
    Scans the bucket under base_prefix and recreates lista.json.
    
    Rules:
    1. Only folders starting with YYYY-MM-DD are considered trainings.
    2. Keeps ALL future trainings (date >= today).
    3. Keeps only the last 'past_keep_count' past trainings (date < today).
    4. For Online folders: includes Slide*.JPG and reuniao.json.
    5. For Normal folders: includes only Slide*.JPG.
    """
    
    if not bucket_name:
        return {"ok": False, "error": "Bucket name not configured."}

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    
    prefix = base_prefix.strip("/") + "/"
    logger.info(f"Scanning bucket {bucket_name} with prefix {prefix}")
    
    # 1. List all blobs under base_prefix
    blobs = list(bucket.list_blobs(prefix=prefix))
    
    # 2. Group blobs by folder
    # Pattern: base_prefix/YYYY-MM-DD - SOMETHING/file
    folder_pattern = re.compile(r"^" + re.escape(prefix) + r"(\d{4}-\d{2}-\d{2}.*?)/(.*)$")
    
    folders_content = defaultdict(list)
    for blob in blobs:
        match = folder_pattern.match(blob.name)
        if match:
            folder_id = match.group(1) # "YYYY-MM-DD - ..."
            folders_content[folder_id].append(blob.name)
            
    if not folders_content:
        return {"ok": False, "error": "Nenhuma pasta de treinamento encontrada no prefixo informado."}

    # 3. Categorize folders into Past and Future
    tz = ZoneInfo(timezone_name)
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    
    past_folders = []
    future_folders = []
    
    for folder_id in folders_content.keys():
        date_part = folder_id[:10] # YYYY-MM-DD
        if date_part < today_str:
            past_folders.append(folder_id)
        else:
            future_folders.append(folder_id)
            
    # Sort folders (descending for past to get most recent, ascending for future)
    past_folders.sort(reverse=True) 
    future_folders.sort()
    
    selected_past = past_folders[:past_keep_count]
    selected_folders = set(selected_past + future_folders)
    
    logger.info(f"Selected {len(future_folders)} future and {len(selected_past)} past folders.")

    # 4. Rebuild the file list
    # We follow the established logic for Online vs Normal packages
    new_files_list: List[str] = []
    
    # Regex for slides (case insensitive)
    slide_regex = re.compile(r"(?i)slide\s*\d+\.jpg")
    
    # Sort selected folders descending (latest first) for the final json
    for folder_id in sorted(list(selected_folders), reverse=True):
        is_online = "DDS ONLINE" in folder_id.upper()
        blobs_in_folder = folders_content[folder_id]
        
        for blob_name in blobs_in_folder:
            # Check if it's a slide
            filename = blob_name.split("/")[-1]
            if slide_regex.search(filename):
                new_files_list.append(blob_name)
            # Check if it's reuniao.json for Online
            elif is_online and filename.lower() == "reuniao.json":
                new_files_list.append(blob_name)
                
    # 5. Upload e Verificação com Retry (até 3 tentativas)
    lista_path = f"{base_prefix}/lista.json".replace("//", "/")
    payload_data = {"files": new_files_list}
    payload_bytes = json.dumps(payload_data, ensure_ascii=False, indent=2).encode("utf-8")
    
    max_attempts = 3
    last_error = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            blob = bucket.blob(lista_path)
            # Atualiza geração para garantir atomicidade em cada tentativa
            generation = 0
            if blob.exists():
                blob.reload()
                generation = blob.generation
            
            blob.upload_from_string(
                payload_bytes,
                content_type="application/json",
                if_generation_match=generation if generation > 0 else 0
            )
            
            # Verificação pós-gravação
            verified_raw = blob.download_as_bytes()
            verified_data = json.loads(verified_raw.decode("utf-8"))
            
            if "files" not in verified_data or not isinstance(verified_data["files"], list):
                raise ValueError("Estrutura JSON inválida detectada na releitura.")
                
            if len(verified_data["files"]) != len(new_files_list):
                raise ValueError(f"Divergência na contagem: esperado {len(new_files_list)}, lido {len(verified_data['files'])}")
            
            logger.info(f"Índice {lista_path} gravado e verificado com sucesso na tentativa {attempt}.")
            return {
                "ok": True,
                "message": "Índice reconstruído e verificado com sucesso.",
                "details": {
                    "attempts": attempt,
                    "future_folders": len(future_folders),
                    "past_folders_kept": len(selected_past),
                    "total_folders": len(selected_folders),
                    "total_files": len(new_files_list),
                    "removed_past_count": len(past_folders) - len(selected_past)
                }
            }

        except Exception as e:
            last_error = e
            logger.warning(f"Tentativa {attempt} de reconstruir o índice falhou: {e}")
            if attempt < max_attempts:
                import time
                time.sleep(1) # Pequena pausa antes de tentar novamente
            
    logger.error(f"Todas as {max_attempts} tentativas de reconstruir o índice falharam. Último erro: {last_error}")
    return {"ok": False, "error": f"Falha persistente após {max_attempts} tentativas: {last_error}"}
