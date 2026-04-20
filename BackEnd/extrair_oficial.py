#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
extrair_oficial.py
-----------------------
Versão Final + Barra de Progresso:
- Mostra contador em tempo real (Analisados X de Y).
- Busca inteligente em subpastas (Fotos, Thumb, Thumbs).
- Ignora pastas duplicadas vazias.
"""

import sys
import os
import json
import datetime as dt
from pathlib import Path
from typing import Dict, Optional, List

from google.oauth2 import service_account
from googleapiclient.discovery import build
from core.cmd_relatorio import _load_or_fetch_grupos, _yyyy_mm

CAMINHO_SA_JSON = "./init/drive_sa.json"
SCOPES = ['https://www.googleapis.com/auth/drive']

# --- AUTENTICAÇÃO ---
def get_robot_service():
    if not os.path.exists(CAMINHO_SA_JSON):
        print(f"[ERRO] Arquivo {CAMINHO_SA_JSON} não encontrado.")
        sys.exit(1)
    creds = service_account.Credentials.from_service_account_file(CAMINHO_SA_JSON, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

# --- CLASSE DE MAPEAMENTO INTELIGENTE ---
class DriveMonthMapper:
    def __init__(self, service, month_str):
        self.svc = service
        self.month_str = month_str
        self.company_folders = {} 
        self.files_cache = {}
        self._map_month_folders()

    def _map_month_folders(self):
        print(f"   [Mapeamento] Buscando pastas '{self.month_str}' no Drive...")
        # Busca todas as pastas com o nome do mês
        q = f"name = '{self.month_str}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        try:
            resp = self.svc.files().list(
                q=q, fields="files(id, name, parents)",
                corpora="allDrives", includeItemsFromAllDrives=True, supportsAllDrives=True
            ).execute()
            
            candidates = resp.get("files", [])
            for folder in candidates:
                parents = folder.get('parents', [])
                if not parents: continue
                parent_id = parents[0]
                parent_name = self._get_folder_name(parent_id)
                if parent_name:
                    self.company_folders[parent_name] = folder['id']
        except Exception as e:
            print(f"[ERRO] Falha ao mapear pastas: {e}")

    def _get_folder_name(self, folder_id):
        try:
            res = self.svc.files().get(fileId=folder_id, fields="name").execute()
            return res.get('name')
        except: return None

    def get_file_id_smart(self, company, filename):
        """
        Procura o arquivo em 'Fotos', depois em 'Thumb', depois em 'Thumbs'.
        """
        month_id = self.company_folders.get(company)
        if not month_id: return None, None

        subfolder_cache_key = f"{month_id}_subs"
        if subfolder_cache_key not in self.files_cache:
            self.files_cache[subfolder_cache_key] = self._list_children_map(month_id, folder_only=True)
        
        subs_map = self.files_cache[subfolder_cache_key]
        
        # Tenta variações de nomes de pasta
        tentativas = ["Fotos", "Thumb", "Thumbs", "fotos", "thumb", "thumbs"]
        
        for pasta_alvo in tentativas:
            sub_id = subs_map.get(pasta_alvo)
            
            if sub_id:
                if sub_id not in self.files_cache:
                    self.files_cache[sub_id] = self._list_children_map(sub_id, folder_only=False)
                
                files_in_sub = self.files_cache[sub_id]
                # Verifica se o arquivo existe nessa pasta
                if filename in files_in_sub:
                    return files_in_sub[filename], pasta_alvo

        return None, None

    def _list_children_map(self, parent_id, folder_only=False):
        file_map = {}
        q = f"'{parent_id}' in parents and trashed = false"
        if folder_only:
            q += " and mimeType = 'application/vnd.google-apps.folder'"
        page = None
        while True:
            resp = self.svc.files().list(
                q=q, fields="nextPageToken, files(id, name)",
                pageSize=1000, corpora="allDrives", includeItemsFromAllDrives=True, supportsAllDrives=True,
                pageToken=page
            ).execute()
            for f in resp.get('files', []):
                file_map[f['name']] = f['id']
            page = resp.get('nextPageToken')
            if not page: break
        return file_map

# --- LÓGICA PRINCIPAL ---
def _extrair_gcs_path(url: str) -> Optional[str]:
    if not url or "/o/" not in url: return None
    from urllib.parse import unquote
    try:
        enc = url.split("/o/", 1)[1].split("?", 1)[0]
        return unquote(enc.replace("~2F", "/")).lstrip("/")
    except: return None

def processar(ano: int, mes: int):
    yyyy_mm = _yyyy_mm(ano, mes)
    print(f"\n--- EXTRAÇÃO DE FOTOS: {yyyy_mm} ---")
    
    grupos = _load_or_fetch_grupos(ano, mes)
    if not grupos: return

    # Conta total de itens para a barra de progresso
    total_items = sum(len(regs) for regs in grupos.values())
    print(f"Total de registros no banco: {total_items}")

    svc = get_robot_service()
    mapper = DriveMonthMapper(svc, yyyy_mm)
    
    print(f"Cruzando dados...")
    companies = {}
    processed_count = 0
    found_count = 0
    not_found_count = 0

    for data, regs in grupos.items():
        for r in regs:
            processed_count += 1
            
            # 1. Validações básicas
            url = r.get("thumbUrl") or r.get("fotoUrl")
            if not url: 
                _print_progress(processed_count, total_items, found_count)
                continue
            
            path = _extrair_gcs_path(url)
            if not path: 
                _print_progress(processed_count, total_items, found_count)
                continue
            
            parts = path.split("/")
            # Lógica para pegar o nome da empresa
            # Se vier DDS_Fotos/Empresa/..., pega index 1. Se vier Empresa/..., pega index 0.
            company = parts[1] if len(parts) > 1 and parts[0] == "DDS_Fotos" else parts[0]
            filename = os.path.basename(path)
            
            # 2. Busca Inteligente no Drive
            fid, folder_name = mapper.get_file_id_smart(company, filename)
            
            if fid:
                found_count += 1
                rel_path = f"{folder_name}/{filename}"
                
                comp_data = companies.setdefault(company, {"by_path": {}, "by_name": {}})
                meta = {"id": fid, "name": filename, "path": rel_path}
                
                comp_data["by_path"][rel_path] = meta
                comp_data["by_name"][filename] = meta
            else:
                not_found_count += 1
            
            # Atualiza barra a cada 5 itens para não travar o terminal
            if processed_count % 5 == 0 or processed_count == total_items:
                _print_progress(processed_count, total_items, found_count)

    print(f"\n\n--- RESUMO FINAL ---")
    print(f"Total Processado: {processed_count}")
    print(f"Encontrados: {found_count}")
    print(f"Não encontrados: {not_found_count}")

    if found_count > 0:
        base = Path("data/indexes")
        for company, data in companies.items():
            p = base / company / yyyy_mm / "INDEX.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "company": company, "month": yyyy_mm, 
                "by_path": data["by_path"], "by_name": data["by_name"]
            }
            p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"✔ INDEX.json gerado: {p}")
    else:
        print("Nenhum arquivo encontrado. Verifique se os nomes dos arquivos no Banco batem com os do Drive.")

def _print_progress(current, total, found):
    """Imprime barra de progresso na mesma linha"""
    percent = (current / total) * 100
    bar_length = 30
    filled_length = int(bar_length * current // total)
    bar = '█' * filled_length + '-' * (bar_length - filled_length)
    
    sys.stdout.write(f"\r|{bar}| {percent:.1f}% ({current}/{total}) | Encontrados: {found}")
    sys.stdout.flush()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python extrair_oficial.py 2025-09")
        sys.exit()
    arg = sys.argv[1]
    if "-" in arg: a, m = map(int, arg.split("-"))
    else: a, m = dt.datetime.now().year, int(arg)
    processar(a, m)