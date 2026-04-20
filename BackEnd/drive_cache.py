#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
drive_cache.py
Gerencia o cache de dados do relatório (JSON) no Google Drive.
Agora salva sempre uma cópia local na raiz para conferência.
"""

import json
import datetime
import os
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configuração (Reusa a mesma chave do robô)
CAMINHO_SA_JSON = "./init/drive_sa.json"
SCOPES = ['https://www.googleapis.com/auth/drive']

class DateEncoder(json.JSONEncoder):
    """Converte datas do Python para String no JSON"""
    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        return super().default(obj)

def _get_service():
    if not os.path.exists(CAMINHO_SA_JSON):
        return None
    creds = service_account.Credentials.from_service_account_file(CAMINHO_SA_JSON, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def _json_hook_dates(dct):
    """Tenta converter strings ISO de volta para datetime ao ler o JSON"""
    for k, v in dct.items():
        if isinstance(v, str):
            # Tenta detectar formato ISO (YYYY-MM-DD...)
            if len(v) >= 10 and v[4] == '-' and v[7] == '-':
                try:
                    # Tenta converter
                    if "T" in v:
                        dct[k] = datetime.datetime.fromisoformat(v)
                    else:
                        dct[k] = datetime.date.fromisoformat(v)
                except ValueError:
                    pass
    return dct

def buscar_cache_drive(yyyy_mm):
    """
    Procura no Drive por um arquivo chamado 'DDS_CACHE_YYYY-MM.json'.
    Retorna o dicionário de dados ou None se não achar.
    SALVA UMA CÓPIA LOCAL SE ENCONTRAR.
    """
    service = _get_service()
    if not service:
        print("[Cache] Erro: Credencial do robô não encontrada.")
        return None

    filename = f"DDS_CACHE_{yyyy_mm}.json"
    print(f"[Cache] Verificando existência de '{filename}' no Drive...")

    # Busca pelo nome (trash=false)
    q = f"name = '{filename}' and trashed = false"
    res = service.files().list(q=q, spaces='drive', fields='files(id, name)').execute()
    files = res.get('files', [])

    if not files:
        print("[Cache] Nenhum cache encontrado. Será necessário consultar o Firestore.")
        return None

    # Se achou, baixa o primeiro
    file_id = files[0]['id']
    print(f"[Cache] Cache encontrado (ID: {file_id}). Baixando...")
    
    try:
        content = service.files().get_media(fileId=file_id).execute()
        
        # --- SALVA CÓPIA LOCAL ---
        try:
            with open(filename, "wb") as f_local:
                f_local.write(content)
            print(f"[Cache] 💾 Cópia local salva: {os.path.abspath(filename)}")
        except Exception as e_local:
            print(f"[Cache] Aviso: Não foi possível salvar cópia local: {e_local}")
        # -------------------------

        # Decodifica JSON e reconstrói as datas
        dados = json.loads(content, object_hook=_json_hook_dates)
        
        # O JSON salva chaves como strings, mas seu relatório espera chaves como Datas?
        dados_corrigidos = {}
        for k, v in dados.items():
            try:
                if len(k) == 10 and k[4] == '-' and k[7] == '-':
                     key_date = datetime.date.fromisoformat(k)
                     dados_corrigidos[key_date] = v
                else:
                    dados_corrigidos[k] = v
            except:
                dados_corrigidos[k] = v
                
        print("[Cache] Dados carregados com sucesso do Drive!")
        return dados_corrigidos

    except Exception as e:
        print(f"[Cache] Erro ao ler arquivo de cache: {e}")
        return None

def salvar_cache_drive(yyyy_mm, dados):
    """
    Salva o dicionário de dados no Drive como JSON.
    TAMBÉM SALVA UMA CÓPIA LOCAL.
    """
    service = _get_service()
    if not service: return

    filename = f"DDS_CACHE_{yyyy_mm}.json"
    print(f"[Cache] Salvando '{filename}' no Drive para uso futuro...")

    # 1. Verifica se já existe para atualizar (ou deletar e criar novo)
    q = f"name = '{filename}' and trashed = false"
    res = service.files().list(q=q, fields='files(id)').execute()
    files = res.get('files', [])
    
    # Prepara o conteúdo JSON na memória
    json_str = json.dumps(dados, cls=DateEncoder, indent=2)
    
    # Salva LOCALMENTE (permanente para debug)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(json_str)
    print(f"[Cache] 💾 Cópia local criada: {os.path.abspath(filename)}")

    # Usa o arquivo local para fazer o upload
    media = MediaIoBaseUpload(filename, mimetype='application/json')

    try:
        if files:
            # Atualiza arquivo existente
            file_id = files[0]['id']
            service.files().update(fileId=file_id, media_body=media).execute()
            print(f"[Cache] Cache ATUALIZADO no Drive (ID: {file_id}).")
        else:
            # Cria novo
            file_metadata = {'name': filename}
            service.files().create(body=file_metadata, media_body=media).execute()
            print(f"[Cache] Novo cache CRIADO no Drive.")
    except Exception as e:
        print(f"[Cache] Erro ao subir cache: {e}")
    # Não removemos o arquivo local, conforme solicitado