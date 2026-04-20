# drive_utils.py
# Utilidades de integração com Google Drive (Shared Drives suportado)
# - Autenticação via token em .secrets/token_drive.json
# - Criação/garantia de pastas
# - Upload (stream / in-memory / update se já existir)
# - Listagem por nível e RECURSIVA (entra em subpastas como Fotos/ e Thumb/)
# - Índice name -> (id, md5)
# - Funções helpers para montar árvore por empresa/mês

from __future__ import annotations

import os
import io
import time
import random
import hashlib
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

from dotenv import load_dotenv
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import (
    MediaIoBaseUpload,
    MediaInMemoryUpload,
    MediaIoBaseDownload,
)
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/drive"]


# =============================================================================
# Ambiente / Serviço
# =============================================================================

def _qs(s: str) -> str:
    """Escapa aspas simples para a sintaxe do Drive (q=...)."""
    return s.replace("'", "\\'")

def _load_env():
    """Carrega .env de caminhos comuns do projeto."""
    for p in [".init/.env", "./init/.env", ".env", "init/.env"]:
        if Path(p).exists():
            load_dotenv(p)
            break

def _token_path() -> Path:
    tp = Path(".secrets/token_drive.json")
    tp.parent.mkdir(parents=True, exist_ok=True)
    return tp

def get_service():
    """Cria o serviço do Drive usando token local (sem fluxo interativo)."""
    _load_env()
    token_path = _token_path()
    if not token_path.exists():
        raise RuntimeError(
            "Token do Drive não encontrado (.secrets/token_drive.json). "
            "Autorize no Windows e copie para o servidor Linux."
        )
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# =============================================================================
# Helpers de pasta/arquivo
# =============================================================================

def _first_or_none(lst: List[Dict[str, Any]]):
    return lst[0] if lst else None

def _find_child_folder(svc, parent_id: str, name: str) -> Optional[str]:
    """
    Retorna o ID da pasta filha 'name' dentro de parent_id, ou None se não existir.
    Usa 'allDrives' + includeItemsFromAllDrives para suportar Shared Drives.
    """
    q = (
        f"name = '{_qs(name)}' and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"trashed = false and '{parent_id}' in parents"
    )
    res = svc.files().list(
        q=q,
        fields="files(id,name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora="allDrives",
        pageSize=1,
    ).execute()
    f = _first_or_none(res.get("files", []))
    return f["id"] if f else None

def find_child_file(svc, parent_id: str, name: str):
    """Busca um arquivo pelo nome dentro do parent (seguro p/ Shared Drives). Retorna dict (id, name, md5Checksum, size, modifiedTime) ou None."""
    safe = _qs(name)
    q = f"name = '{safe}' and '{parent_id}' in parents and trashed = false"
    try:
        resp = svc.files().list(
            q=q,
            corpora="allDrives",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            pageSize=1,
            fields="files(id,name,md5Checksum,size,modifiedTime)",
        ).execute()
    except HttpError:
        # retry leve
        time.sleep(0.5)
        resp = svc.files().list(
            q=q,
            corpora="allDrives",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            pageSize=1,
            fields="files(id,name,md5Checksum,size,modifiedTime)",
        ).execute()
    files = resp.get("files", [])
    return files[0] if files else None

def _find_child_file(svc, parent_id: str, name: str) -> Optional[str]:
    """Compat: retorna apenas o ID (use find_child_file para metadados)."""
    f = find_child_file(svc, parent_id, name)
    return f["id"] if f else None

def ensure_folder(svc, parent_id: str, name: str) -> str:
    """Garante uma pasta filha 'name' sob parent_id e retorna seu id."""
    fid = _find_child_folder(svc, parent_id, name)
    if fid:
        return fid
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    f = svc.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
    return f["id"]


# =============================================================================
# Listagens (nível e recursiva)
# =============================================================================

def list_name_id_md5_in_folder(svc, folder_id: str) -> dict[str, tuple[str, str]]:
    """
    Mapa name -> (file_id, md5Checksum) para uma pasta (apenas 1 nível).
    Ignora arquivos Google (Docs/Sheets/etc.).
    """
    out: dict[str, tuple[str, str]] = {}
    page_token = None
    while True:
        res = svc.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id,name,md5Checksum,mimeType)",
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="allDrives",
            pageToken=page_token,
        ).execute()
        for f in res.get("files", []):
            if (f.get("mimeType", "") or "").startswith("application/vnd.google-apps."):
                continue
            name = f.get("name")
            if name:
                out[name] = (f.get("id"), (f.get("md5Checksum") or "").lower())
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return out

def list_name_id_md5_in_folder_recursive(svc, folder_id: str) -> dict[str, tuple[str, str]]:
    """
    Mapa name -> (file_id, md5Checksum) para a pasta e TODAS as subpastas.
    Ignora itens Google (Docs/Sheets/Slides). Suporta Shared Drives.
    """
    out: dict[str, tuple[str, str]] = {}
    stack = [folder_id]
    total = 0
    while stack:
        fid = stack.pop()
        page_token = None
        while True:
            res = svc.files().list(
                q=f"'{fid}' in parents and trashed=false",
                fields="nextPageToken, files(id,name,md5Checksum,mimeType)",
                pageSize=1000,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="allDrives",
                pageToken=page_token,
            ).execute()
            for f in res.get("files", []):
                name = f.get("name")
                mt = (f.get("mimeType") or "")
                if not name:
                    continue
                if mt == "application/vnd.google-apps.folder":
                    stack.append(f["id"])
                    continue
                if mt.startswith("application/vnd.google-apps."):
                    continue
                out.setdefault(name, (f.get("id"), (f.get("md5Checksum") or "").lower()))
                total += 1
                if total % 1000 == 0:
                    # log leve a cada 1000 itens
                    try:
                        print(f"[drive_utils] indexados {total} arquivos (parcial)…", flush=True)
                    except Exception:
                        pass
            page_token = res.get("nextPageToken")
            if not page_token:
                break
    return out


# =============================================================================
# Download / Upload básicos
# =============================================================================

def download_file_bytes(svc, file_id: str) -> bytes:
    """Baixa um arquivo do Drive por file_id (streaming)."""
    req = svc.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req, chunksize=1024 * 1024)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()

def upload_text(svc, parent_id: str, name: str, content: str) -> str:
    media = MediaInMemoryUpload(content.encode("utf-8"), mimetype="text/plain")
    body = {"name": name, "parents": [parent_id]}
    f = svc.files().create(
        body=body, media_body=media, fields="id", supportsAllDrives=True
    ).execute()
    return f["id"]

def upload_json(svc, parent_id: str, name: str, data: Dict[str, Any]) -> str:
    """
    Envia (ou atualiza) um arquivo JSON para o Google Drive.

    - Se já existir um arquivo com o mesmo nome na pasta: faz UPDATE (conteúdo).
    - Se não existir: cria.
    Retorna o fileId.
    """
    import json
    from googleapiclient.http import MediaInMemoryUpload

    # Serializa para bytes UTF-8
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    media = MediaInMemoryUpload(payload, mimetype="application/json")

    # Procura arquivo existente com mesmo nome na pasta
    q = f"'{parent_id}' in parents and name = '{name}' and trashed = false"
    resp = svc.files().list(
        q=q,
        corpora="allDrives",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        pageSize=1,
        fields="files(id,name)",
    ).execute()
    files = resp.get("files", [])

    if files:
        # Atualiza conteúdo do JSON existente
        file_id = files[0]["id"]
        svc.files().update(
            fileId=file_id,
            media_body=media,
            supportsAllDrives=True,
        ).execute()
        return file_id
    else:
        # Cria um novo arquivo
        body = {"name": name, "parents": [parent_id]}
        f = svc.files().create(
            body=body,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        ).execute()
        return f["id"]


def upload_stream(
    svc,
    parent_id: str,
    name: str,
    stream: io.BytesIO,
    mimetype: str = "application/octet-stream",
    *,
    resumable: bool = True,
    chunksize_mb: int = 8,
) -> str:
    """
    Envia conteúdo binário para o Drive. Por padrão, resumível.
    Nome não pode ter subpastas; se quiser árvore real, crie pastas antes e use name simples.
    """
    media = MediaIoBaseUpload(
            io.BytesIO(data),
            mimetype or "application/octet-stream",
            chunksize=chunksize,
            resumable=resumable,
        )
    body = {"name": name, "parents": [parent_id]}
    f = svc.files().create(
        body=body, media_body=media, fields="id", supportsAllDrives=True
    ).execute()
    return f["id"]


# =============================================================================
# Montagem de caminhos (árvores) e uploads por caminho
# =============================================================================

def ensure_path(svc, root_id: str, parts: List[str]) -> str:
    """Garante a existência de uma sequência de pastas sob root_id e retorna o id da última pasta."""
    pid = root_id
    for p in [x for x in parts if x]:
        pid = ensure_folder(svc, pid, p)
    return pid

def ensure_month_folder(svc, year: int, month: int) -> Tuple[str, str]:
    """
    Retorna (month_folder_id, yyyy_mm) criando a árvore:
    DRIVE_ROOT_ID / <bucket> / <prefix em partes> / YYYY-MM
    (Para único tenant/empresa.)
    """
    root_id = os.environ["DRIVE_ROOT_ID"]  # obrigatório
    bucket = os.getenv("GCS_BUCKET", "dds-treinamentos.firebasestorage.app")
    prefix = os.getenv("GCS_PREFIX", "DDS_Fotos/ChicoEletro")
    yyyy_mm = f"{year:04d}-{month:02d}"

    pid = ensure_folder(svc, root_id, bucket)
    for part in [p for p in prefix.split("/") if p]:
        pid = ensure_folder(svc, pid, part)
    mid = ensure_folder(svc, pid, yyyy_mm)
    return mid, yyyy_mm

def ensure_company_month_folder(svc, year: int, month: int, company: str) -> Tuple[str, str]:
    """
    Retorna (company_month_id, yyyy_mm) criando a árvore:
    DRIVE_ROOT_ID / <bucket> / <prefix em partes> / <Empresa> / YYYY-MM
    (Para multiempresa.)
    """
    root_id = os.environ["DRIVE_ROOT_ID"]
    bucket = os.getenv("GCS_BUCKET", "dds-treinamentos.firebasestorage.app")
    prefix = os.getenv("GCS_PREFIX", "DDS_Fotos/")
    yyyy_mm = f"{year:04d}-{month:02d}"

    pid = ensure_folder(svc, root_id, bucket)
    for part in [p for p in prefix.split("/") if p]:
        pid = ensure_folder(svc, pid, part)
    pid = ensure_folder(svc, pid, company)
    mid = ensure_folder(svc, pid, yyyy_mm)
    return mid, yyyy_mm

def upload_bytes_at_path(
    svc,
    root_id: str,
    path_parts: List[str],
    file_name: str,
    data: bytes,
    mimetype: str,
) -> str:
    """Cria subpastas em path_parts e sobe o arquivo (resumable por stream)."""
    folder_id = ensure_path(svc, root_id, path_parts)
    return upload_stream(svc, folder_id, file_name, io.BytesIO(data), mimetype)

def upload_bytes_at_path_fast(
    svc,
    root_id: str,
    path_parts: List[str],
    file_name: str,
    data: bytes,
    mimetype: str,
) -> str:
    """Variante NÃO-RESUMÍVEL (1 request) – ideal para arquivos pequenos (<5 MB)."""
    folder_id = ensure_path(svc, root_id, path_parts)
    media = MediaInMemoryUpload(data, mimetype=mimetype, resumable=False)
    body = {"name": file_name, "parents": [folder_id]}
    f = svc.files().create(
        body=body, media_body=media, fields="id", supportsAllDrives=True
    ).execute()
    return f["id"]


# =============================================================================
# Upload inteligente (create/update/skip) com appProperties
# =============================================================================

def _mb(n: int) -> int:
    return n * 1024 * 1024

def _md5_hex_of_bytes(b: bytes) -> str:
    h = hashlib.md5()
    h.update(b)
    return h.hexdigest()

def _metadata_differs(svc, file_id: str, new_props: Optional[Dict[str, str]]) -> bool:
    """Compara appProperties atuais vs. as novas (ignora se None)."""
    if not new_props:
        return False
    cur = (
        svc.files()
        .get(fileId=file_id, fields="appProperties", supportsAllDrives=True)
        .execute()
        .get("appProperties")
        or {}
    )
    return cur != new_props

def _retry(call, *args, **kwargs):
    """Backoff simples para 429/5xx."""
    for i in range(5):
        try:
            return call(*args, **kwargs)
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", None)
            if status in (429, 500, 502, 503, 504):
                time.sleep((2 ** i) + random.random() * 0.25)
                continue
            raise
    # última tentativa sem capturar
    return call(*args, **kwargs)

def upload_or_update_bytes_at_path(
    svc,
    root_id: str,
    path_parts: List[str],
    file_name: str,
    data: bytes,
    mimetype: str,
    *,
    gcs_md5_hex: str | None = None,
    small_limit_mb: int = 5,
    app_properties: dict[str, str] | None = None,
) -> tuple[str | None, str]:
    """
    Sobe o arquivo no caminho alvo, evitando duplicar:
    - se existir e MD5 for igual (ou, na falta de MD5, tamanho igual): 'skipped'
      (mas se appProperties diferirem, faz update somente de metadados: 'metadata')
    - se existir e for diferente: 'updated'
    - se não existir: 'created'
    Retorna (file_id, action).
    """
    # 1) Garante pasta destino
    folder_id = ensure_path(svc, root_id, path_parts)

    # 2) Descobre arquivo existente
    existing = find_child_file(svc, folder_id, file_name)  # dict com id, md5Checksum, size
    existing_id = existing["id"] if existing else None
    existing_md5 = (existing.get("md5Checksum") or "").lower() if existing else ""
    size_bytes = len(data)

    # 3) Critério de igualdade de conteúdo
    local_md5 = (gcs_md5_hex or "").lower() if gcs_md5_hex else ""
    if not local_md5 and size_bytes <= _mb(small_limit_mb):
        # custo baixo; calcula MD5 local para evitar upload desnecessário
        local_md5 = _md5_hex_of_bytes(data)

    same_content = False
    if existing:
        if existing_md5 and local_md5:
            same_content = (existing_md5 == local_md5)
        elif not existing_md5 and not local_md5:
            # sem MD5, usa tamanho como heurística
            try:
                same_content = int(existing.get("size") or -1) == size_bytes
            except Exception:
                same_content = False

    # 4) Se conteúdo igual, talvez só atualizar metadados
    if existing and same_content:
        if _metadata_differs(svc, existing_id, app_properties):
            _retry(
                svc.files().update,
                fileId=existing_id,
                body={"appProperties": app_properties},
                fields="id,md5Checksum,appProperties",
                supportsAllDrives=True,
            ).execute()
            return existing_id, "metadata"
        return existing_id, "skipped"

    # 5) Preparar upload agora (evita criar 'media' sem necessidade)
    resumable = size_bytes > _mb(small_limit_mb)
    chunksize = _mb(8) if resumable else None
    media = MediaIoBaseUpload(
        io.BytesIO(data),
        mimetype or "application/octet-stream",
        chunksize=chunksize,
        resumable=resumable,
    )

    # 6) Update vs Create
    if existing:
        file = _retry(
            svc.files().update,
            fileId=existing_id,
            media_body=media,
            body={"appProperties": app_properties} if app_properties else None,
            fields="id,md5Checksum",
            supportsAllDrives=True,
        ).execute()
        return file["id"], "updated"
    else:
        body = {"name": file_name, "parents": [folder_id]}
        if app_properties:
            body["appProperties"] = app_properties
        file = _retry(
            svc.files().create,
            body=body,
            media_body=media,
            fields="id,md5Checksum",
            supportsAllDrives=True,
        ).execute()
        return file["id"], "created"
