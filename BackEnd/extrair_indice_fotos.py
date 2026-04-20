#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
extrair_indice_fotos.py (Versão Debug + Fix Root)
"""

from __future__ import annotations

import sys
import os
import json
import datetime as dt
from pathlib import Path
from typing import Dict, Optional, Tuple, List

from logger import log_manager
from drive_utils import get_service as drive_get_service
from core.cmd_relatorio import _load_or_fetch_grupos, _yyyy_mm

# --- CLASSE DE CACHE OTIMIZADA E CORRIGIDA ---

class DrivePathCache:
    def __init__(self, service):
        self.svc = service
        self.folder_id_cache: Dict[str, str] = {}
        self.file_map_cache: Dict[str, Dict[str, str]] = {}

    def find_folder_id_by_path(self, path_parts: List[str]) -> Optional[str]:
        """
        Tenta encontrar o ID da última pasta na lista path_parts.
        Se falhar no primeiro item (ex: DDS_Fotos), tenta pular e buscar o segundo (ex: ChicoEletro) globalmente.
        """
        full_path_key = "/".join(path_parts)
        if full_path_key in self.folder_id_cache:
            return self.folder_id_cache[full_path_key]

        parent_id = None
        
        # Tenta resolver a árvore sequencialmente
        # path_parts ex: ['DDS_Fotos', 'ChicoEletro', '2025-09']
        for i, part in enumerate(path_parts):
            found_id = self._search_folder(part, parent_id)
            
            if not found_id:
                # FIX: Se falhou na primeira pasta (ex: DDS_Fotos), pode ser que ela seja o Shared Drive
                # Então tentamos buscar a SEGUNDA pasta (ChicoEletro) direto na raiz global
                if i == 0 and len(path_parts) > 1:
                    print(f"   [DEBUG] '{part}' não encontrado (pode ser root). Tentando '{path_parts[1]}' globalmente...")
                    continue # Pula o DDS_Fotos, o próximo loop vai buscar ChicoEletro sem parent_id
                
                # Se falhou e não é o caso acima, quebrou o caminho
                print(f"   [DEBUG] Falha ao encontrar pasta: '{part}' dentro de parent_id={parent_id}")
                self.folder_id_cache[full_path_key] = None
                return None

            parent_id = found_id
        
        self.folder_id_cache[full_path_key] = parent_id
        return parent_id

    def _search_folder(self, name: str, parent_id: Optional[str]) -> Optional[str]:
        name_q = name.replace("'", "\\'")
        query_parts = [
            f"name = '{name_q}'",
            "mimeType = 'application/vnd.google-apps.folder'",
            "trashed = false"
        ]
        if parent_id:
            query_parts.append(f"'{parent_id}' in parents")
        
        q = " and ".join(query_parts)
        try:
            resp = self.svc.files().list(
                q=q, pageSize=1, fields="files(id, name)",
                corpora="allDrives", includeItemsFromAllDrives=True, supportsAllDrives=True
            ).execute()
            files = resp.get("files", [])
            if files:
                return files[0]["id"]
        except Exception as e:
            print(f"   [ERRO API] Buscando pasta {name}: {e}")
        return None

    def get_files_map_in_folder(self, folder_id: str) -> Dict[str, str]:
        if folder_id in self.file_map_cache: return self.file_map_cache[folder_id]

        print(f"   [DEBUG] Listando arquivos na pasta ID: {folder_id} ...")
        file_map = {}
        page_token = None
        try:
            while True:
                resp = self.svc.files().list(
                    q=f"'{folder_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
                    pageSize=1000, fields="nextPageToken, files(id, name)",
                    corpora="allDrives", includeItemsFromAllDrives=True, supportsAllDrives=True,
                    pageToken=page_token
                ).execute()
                for f in resp.get("files", []):
                    file_map[f["name"]] = f["id"]
                page_token = resp.get("nextPageToken")
                if not page_token: break
            self.file_map_cache[folder_id] = file_map
        except Exception as e:
            print(f"   [ERRO API] Listando arquivos: {e}")
        return file_map

# --- FUNÇÕES DE SUPORTE ---

def _parse_mes_argumento(arg: str) -> Tuple[int, int]:
    txt = (arg or "").strip()
    agora = dt.datetime.now()
    if "-" in txt or "/" in txt:
        sep = "-" if "-" in txt else "/"
        p_ano, p_mes = txt.split(sep, 1)
        return int(p_ano), int(p_mes)
    return agora.year, int(txt)

def _extrair_gcs_path(url: str) -> Optional[str]:
    if not url or "/o/" not in url: return None
    from urllib.parse import unquote
    try:
        enc = url.split("/o/", 1)[1].split("?", 1)[0]
        return unquote(enc.replace("~2F", "/")).lstrip("/")
    except: return None

def gerar_indice_fotos(ano: int, mes: int) -> None:
    yyyy_mm_str = _yyyy_mm(ano, mes)
    print(f"\n>>> Iniciando extração para: {yyyy_mm_str}")

    grupos = _load_or_fetch_grupos(ano, mes)
    if not grupos:
        print(f"Nenhum dado no Firestore para {yyyy_mm_str}.")
        return

    svc = drive_get_service()
    drive_cache = DrivePathCache(svc)
    base_indexes = Path("data/indexes")
    base_indexes.mkdir(parents=True, exist_ok=True)

    companies = {}
    total_urls = 0
    found_count = 0

    print(f">>> Processando URLs do Firestore...")

    for data, regs in grupos.items():
        for r in regs:
            url = (r.get("thumbUrl") or r.get("fotoUrl") or "").strip()
            if not url: continue

            gcs_path = _extrair_gcs_path(url)
            if not gcs_path: continue

            total_urls += 1
            parts = gcs_path.split("/")
            
            # Lógica de Path: DDS_Fotos/Empresa/Mes/...
            if len(parts) >= 3 and parts[0] == "DDS_Fotos":
                company = parts[1]
                # Ajuste o range do path prefix conforme necessidade
                # Tenta localizar a pasta do MÊS (ex: DDS_Fotos/ChicoEletro/2025-09)
                path_prefix = parts[:3] 
            else:
                # Caminho fora do padrão
                continue

            file_name = os.path.basename(gcs_path)
            rel_path = "/".join(parts[3:])
            
            # --- A MÁGICA DO DEBUG ---
            # Só debuga o PRIMEIRO arquivo para não poluir o log
            if total_urls == 1:
                print(f"   [Exemplo Caminho] Procurando estrutura: {path_prefix}")

            folder_id = drive_cache.find_folder_id_by_path(path_prefix)
            
            fid = None
            if folder_id:
                folder_files = drive_cache.get_files_map_in_folder(folder_id)
                fid = folder_files.get(file_name)
            
            if fid:
                found_count += 1
                comp_data = companies.setdefault(company, {"by_path": {}, "by_name": {}})
                meta = {"id": fid, "name": file_name, "path": rel_path}
                comp_data["by_path"][rel_path] = meta
                comp_data["by_name"][file_name] = meta

    print(f"\n>>> Resumo:")
    print(f"    URLs analisadas: {total_urls}")
    print(f"    Arquivos encontrados no Drive: {found_count}")

    if not companies:
        print("\n[ATENÇÃO] Nenhuma empresa indexada. Verifique os logs [DEBUG] acima.")
        print("Possível causa: O Service Account não tem permissão na pasta DDS_Fotos ou ChicoEletro.")
        return

    for company, data in companies.items():
        emp_dir = base_indexes / company / yyyy_mm_str
        emp_dir.mkdir(parents=True, exist_ok=True)
        idx_path = emp_dir / "INDEX.json"
        
        payload = {
            "company": company,
            "month": yyyy_mm_str,
            "generated_at": dt.datetime.utcnow().isoformat() + "Z",
            "by_path": data["by_path"],
            "by_name": data["by_name"],
        }
        idx_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✔ INDEX.json salvo para {company}")

def main():
    argv = sys.argv[1:]
    if not argv:
        print("Uso: python extrair_indice_fotos.py YYYY-MM")
        sys.exit(1)
    try:
        ano, mes = _parse_mes_argumento(argv[0])
        gerar_indice_fotos(ano, mes)
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    main()