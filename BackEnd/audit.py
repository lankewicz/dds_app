#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auditoria_firebase_drive.py
Versão: 1.0

Descrição:
    Lista e relaciona arquivos entre Firebase Storage (URLs no Firestore)
    e Google Drive (backup). Gera relatório de correspondência e arquivos
    não encontrados.

Uso:
    python auditoria_firebase_drive.py --mes 10 --ano 2025
    python auditoria_firebase_drive.py --mes outubro --ano 2025 --output relatorio.json
    python auditoria_firebase_drive.py --mes 08 --ano 2025 --csv
"""

from __future__ import annotations

import os
import re
import sys
import json
import csv
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote
from collections import defaultdict

# Firebase
import firebase_admin
from firebase_admin import credentials, firestore

# Drive utils
from drive_utils import (
    get_service,
    ensure_company_month_folder,
    list_name_id_md5_in_folder_recursive,
)

# =============================================================================
# Utilidades
# =============================================================================

MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3,
    "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}


def interpretar_mes(texto: str) -> Optional[int]:
    """Converte nome do mês ou número para int (1-12)."""
    txt = texto.lower().strip()
    if txt in MESES_PT:
        return MESES_PT[txt]
    if txt.isdigit():
        num = int(txt)
        return num if 1 <= num <= 12 else None
    return None


def gcs_path_from_url(url: str | None) -> str | None:
    """Extrai o caminho GCS de uma URL do Firebase Storage."""
    if not url or "/o/" not in url:
        return None
    try:
        enc = url.split("/o/", 1)[1].split("?", 1)[0]
        enc = enc.replace("~2F", "/").replace("%2F", "/")
        return unquote(enc).lstrip("/")
    except Exception:
        return None


def nome_arquivo_from_url(url: str | None) -> str | None:
    """Extrai apenas o nome do arquivo de uma URL."""
    path = gcs_path_from_url(url)
    return path.rsplit("/", 1)[-1] if path else None


# =============================================================================
# Conexão Firebase
# =============================================================================

def conectar_firebase() -> firestore.Client:
    """Inicializa Firebase Admin SDK e retorna cliente Firestore."""
    if not firebase_admin._apps:
        base = Path(__file__).parent
        cred_path = base / "init" / "serviceAccountKey.json"
        if not cred_path.exists():
            raise FileNotFoundError(
                f"Credencial Firebase não encontrada: {cred_path}"
            )
        cred = credentials.Certificate(str(cred_path))
        firebase_admin.initialize_app(cred)
    return firestore.client()


# =============================================================================
# Coleta de dados
# =============================================================================

def coletar_urls_firestore(db: firestore.Client, ano: int, mes: int) -> List[Dict]:
    """
    Busca registros DDS do mês/ano no Firestore e extrai fotoUrl e thumbUrl.
    Retorna lista de dicts com: {id, headerDate, equipe, fotoUrl, thumbUrl, ...}
    """
    registros = []
    yyyy_mm = f"{ano:04d}-{mes:02d}"
    
    print(f"🔍 Buscando registros no Firestore para {yyyy_mm}...")
    
    for doc in db.collection("DDS").stream():
        d = doc.to_dict() or {}
        header_date = d.get("headerDate", "")
        
        # Filtra pelo mês/ano
        if not header_date.startswith(yyyy_mm):
            continue
        
        registros.append({
            "id": doc.id,
            "headerDate": header_date,
            "equipe": d.get("equipe", "—"),
            "fotoUrl": d.get("fotoUrl"),
            "thumbUrl": d.get("thumbUrl"),
        })
    
    print(f"✅ {len(registros)} registros encontrados no Firestore")
    return registros


def listar_subpastas(svc, parent_id: str) -> List[Tuple[str, str]]:
    """Lista todas as subpastas (name, id) dentro de uma pasta."""
    subpastas = []
    page_token = None
    
    while True:
        try:
            response = svc.files().list(
                q=f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                spaces='drive',
                fields='nextPageToken, files(id, name)',
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            
            subpastas.extend([(f['name'], f['id']) for f in response.get('files', [])])
            page_token = response.get('nextPageToken')
            
            if not page_token:
                break
        except Exception as e:
            print(f"   ⚠️  Erro ao listar subpastas: {e}")
            break
    
    return subpastas


def indexar_drive_empresas(svc, ano: int, mes: int, root_folder_id: str = None) -> Dict[str, Tuple[str, str]]:
    """
    Indexa TODAS as subpastas na pasta raiz do Drive para o mês/ano.
    Retorna: {nome_arquivo: (file_id, md5_checksum)}
    """
    print(f"📂 Indexando Google Drive para {ano:04d}-{mes:02d}...")
    
    # Usar pasta específica ou tentar via variável de ambiente
    if not root_folder_id:
        root_folder_id = os.getenv("DRIVE_AUDIT_ROOT_ID", "1rFDdK7ljtNz0RBavlh0lalF690Ld4zjR")
    
    print(f"📁 Pasta raiz: {root_folder_id}")
    
    # Listar todas as subpastas (empresas)
    print("🔍 Listando subpastas (empresas)...")
    subpastas = listar_subpastas(svc, root_folder_id)
    
    if not subpastas:
        print("⚠️  Nenhuma subpasta encontrada!")
        return {}
    
    print(f"🏢 {len(subpastas)} empresa(s) encontrada(s): {', '.join(n for n, _ in subpastas)}")
    
    # Indexar cada empresa
    indice_unificado: Dict[str, Tuple[str, str]] = {}
    yyyy_mm = f"{ano:04d}-{mes:02d}"
    
    for emp_nome, emp_id in subpastas:
        print(f"\n   📂 Processando: {emp_nome}")
        
        # Buscar pasta do mês dentro da empresa
        mes_pastas = listar_subpastas(svc, emp_id)
        mes_encontrada = None
        
        for mes_nome, mes_id in mes_pastas:
            if mes_nome == yyyy_mm:
                mes_encontrada = mes_id
                break
        
        if not mes_encontrada:
            print(f"      ⚠️  Pasta {yyyy_mm} não encontrada em {emp_nome}")
            continue
        
        try:
            # Indexar recursivamente (inclui Fotos/, Thumb/, etc.)
            idx = list_name_id_md5_in_folder_recursive(svc, mes_encontrada)
            
            for nome, (fid, md5) in idx.items():
                indice_unificado.setdefault(nome, (fid, md5))
            
            print(f"      ✅ {len(idx)} arquivo(s) indexado(s)")
        except Exception as e:
            print(f"      ⚠️  Erro ao indexar: {e}")
    
    print(f"\n✅ Total indexado no Drive: {len(indice_unificado)} arquivo(s)")
    return indice_unificado


# =============================================================================
# Análise e Relatório
# =============================================================================

def analisar_correspondencia(
    registros_firestore: List[Dict],
    indice_drive: Dict[str, Tuple[str, str]]
) -> Dict:
    """
    Cruza dados Firestore x Drive e gera estatísticas.
    """
    resultado = {
        "total_registros": len(registros_firestore),
        "total_drive": len(indice_drive),
        "fotos_encontradas": 0,
        "fotos_nao_encontradas": 0,
        "thumbs_encontradas": 0,
        "thumbs_nao_encontradas": 0,
        "detalhes": [],
        "ausentes_drive": [],
        "presentes_drive": []
    }
    
    print("\n🔄 Analisando correspondência...")
    
    for reg in registros_firestore:
        foto_url = reg.get("fotoUrl")
        thumb_url = reg.get("thumbUrl")
        
        foto_nome = nome_arquivo_from_url(foto_url)
        thumb_nome = nome_arquivo_from_url(thumb_url)
        
        foto_path = gcs_path_from_url(foto_url)
        thumb_path = gcs_path_from_url(thumb_url)
        
        # Verificar foto
        foto_status = "—"
        foto_drive_id = None
        if foto_nome:
            if foto_nome in indice_drive:
                foto_status = "✅ Encontrada"
                foto_drive_id = indice_drive[foto_nome][0]
                resultado["fotos_encontradas"] += 1
            else:
                foto_status = "❌ Ausente"
                resultado["fotos_nao_encontradas"] += 1
        
        # Verificar thumb
        thumb_status = "—"
        thumb_drive_id = None
        if thumb_nome:
            if thumb_nome in indice_drive:
                thumb_status = "✅ Encontrada"
                thumb_drive_id = indice_drive[thumb_nome][0]
                resultado["thumbs_encontradas"] += 1
            else:
                thumb_status = "❌ Ausente"
                resultado["thumbs_nao_encontradas"] += 1
        
        detalhe = {
            "firestore_id": reg["id"],
            "data": reg["headerDate"],
            "equipe": reg["equipe"],
            "foto_nome": foto_nome or "—",
            "foto_gcs_path": foto_path or "—",
            "foto_status": foto_status,
            "foto_drive_id": foto_drive_id or "—",
            "thumb_nome": thumb_nome or "—",
            "thumb_gcs_path": thumb_path or "—",
            "thumb_status": thumb_status,
            "thumb_drive_id": thumb_drive_id or "—",
        }
        
        resultado["detalhes"].append(detalhe)
        
        # Registrar ausentes
        if foto_nome and foto_status.startswith("❌"):
            resultado["ausentes_drive"].append({
                "tipo": "foto",
                "nome": foto_nome,
                "gcs_path": foto_path,
                "registro": reg["id"]
            })
        
        if thumb_nome and thumb_status.startswith("❌"):
            resultado["ausentes_drive"].append({
                "tipo": "thumb",
                "nome": thumb_nome,
                "gcs_path": thumb_path,
                "registro": reg["id"]
            })
    
    return resultado


def exibir_resumo(resultado: Dict):
    """Exibe resumo formatado na tela."""
    print("\n" + "="*70)
    print("📊 RESUMO DA AUDITORIA")
    print("="*70)
    print(f"Total de registros Firestore: {resultado['total_registros']}")
    print(f"Total de arquivos no Drive:   {resultado['total_drive']}")
    print()
    print(f"Fotos encontradas no Drive:   {resultado['fotos_encontradas']} ✅")
    print(f"Fotos NÃO encontradas:         {resultado['fotos_nao_encontradas']} ❌")
    print()
    print(f"Thumbs encontradas no Drive:  {resultado['thumbs_encontradas']} ✅")
    print(f"Thumbs NÃO encontradas:        {resultado['thumbs_nao_encontradas']} ❌")
    print("="*70)
    
    if resultado["ausentes_drive"]:
        print(f"\n⚠️  {len(resultado['ausentes_drive'])} arquivo(s) ausente(s) no Drive:")
        for i, item in enumerate(resultado["ausentes_drive"][:10], 1):
            print(f"   {i}. [{item['tipo']}] {item['nome']}")
        if len(resultado["ausentes_drive"]) > 10:
            print(f"   ... e mais {len(resultado['ausentes_drive']) - 10}")


def salvar_json(resultado: Dict, caminho: str):
    """Salva resultado completo em JSON."""
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"💾 JSON salvo: {caminho}")


def salvar_csv(resultado: Dict, caminho: str):
    """Salva detalhes em CSV."""
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "firestore_id", "data", "equipe",
            "foto_nome", "foto_gcs_path", "foto_status", "foto_drive_id",
            "thumb_nome", "thumb_gcs_path", "thumb_status", "thumb_drive_id"
        ])
        writer.writeheader()
        writer.writerows(resultado["detalhes"])
    print(f"💾 CSV salvo: {caminho}")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Auditoria de correspondência Firebase Storage ↔ Google Drive"
    )
    parser.add_argument("--mes", required=True, help="Mês (nome ou número: 'outubro' ou '10')")
    parser.add_argument("--ano", type=int, required=True, help="Ano (ex: 2025)")
    parser.add_argument("--output", default="auditoria_resultado.json", help="Arquivo JSON de saída")
    parser.add_argument("--csv", action="store_true", help="Gerar também CSV")
    parser.add_argument("--drive-root", default="11sbxf371SzmX7vTp010cIhU_vOJVW1tl", 
                       help="ID da pasta raiz no Drive com as empresas (padrão: pasta DDS_Fotos)")
    
    args = parser.parse_args()
    
    # Interpretar mês
    mes = interpretar_mes(args.mes)
    if not mes:
        print(f"❌ Mês inválido: {args.mes}")
        sys.exit(1)
    
    ano = args.ano
    
    print(f"🚀 Iniciando auditoria: {mes:02d}/{ano}")
    print(f"📁 Pasta Drive (nível empresas): https://drive.google.com/drive/folders/{args.drive_root}")
    
    try:
        # 1. Conectar Firebase
        db = conectar_firebase()
        
        # 2. Coletar URLs do Firestore
        registros = coletar_urls_firestore(db, ano, mes)
        
        if not registros:
            print("⚠️  Nenhum registro encontrado no Firestore para este período")
            sys.exit(0)
        
        # 3. Indexar Drive
        svc = get_service()
        indice_drive = indexar_drive_empresas(svc, ano, mes, args.drive_root)
        
        # 4. Análise
        resultado = analisar_correspondencia(registros, indice_drive)
        
        # 5. Exibir resumo
        exibir_resumo(resultado)
        
        # 6. Salvar arquivos
        salvar_json(resultado, args.output)
        
        if args.csv:
            csv_path = args.output.replace(".json", ".csv")
            salvar_csv(resultado, csv_path)
        
        print(f"\n✅ Auditoria concluída!")
        
    except Exception as e:
        print(f"\n❌ Erro fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()