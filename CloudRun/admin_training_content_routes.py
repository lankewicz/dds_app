from __future__ import annotations

import io
import mimetypes
import os
import re
from typing import Any, Dict, List, Optional

from flask import abort, current_app, render_template, request, send_file
from google.cloud import storage

from storage_online_package import list_all_sessions_from_storage


_SLIDE_NUM_RE = re.compile(r"slide\s*(\d+)", re.IGNORECASE)
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_SKIP_FILES = {"reuniao.json", "lista.json"}


def _gcs_client() -> storage.Client:
    return storage.Client()


def _safe_folder_prefix(base_prefix: str, folder_id: str) -> str:
    return f"{(base_prefix or '').strip().strip('/')}/{folder_id.strip()}".strip("/") + "/"


def _find_session(
    *,
    bucket_name: str,
    base_prefix: str,
    dds_type: str,
    folder_id: str,
    session_id: str,
) -> Optional[Dict[str, Any]]:
    sessions = list_all_sessions_from_storage(
        bucket_name=bucket_name,
        base_prefix=base_prefix,
        month=None,
        team=None,
    )

    for item in sessions:
        if dds_type and (item.get("type") or "").strip().lower() != dds_type:
            continue
        if folder_id and (item.get("folderId") or "").strip() == folder_id:
            return item
        if session_id and (item.get("sessionId") or "").strip() == session_id:
            return item
    return None


def _is_image_name(name: str) -> bool:
    ext = os.path.splitext((name or "").lower())[1]
    return ext in _IMAGE_EXTENSIONS


def _entry_sort_key(entry: Dict[str, Any]):
    name = entry.get("name") or ""
    match = _SLIDE_NUM_RE.search(name)
    slide_num = int(match.group(1)) if match else 999999
    image_rank = 0 if entry.get("is_image") else 1
    return (image_rank, slide_num, name.lower())


def _list_training_files(*, bucket_name: str, base_prefix: str, folder_id: str) -> List[Dict[str, Any]]:
    folder_prefix = _safe_folder_prefix(base_prefix, folder_id)
    client = _gcs_client()
    bucket = client.bucket(bucket_name)

    entries: List[Dict[str, Any]] = []
    for blob in bucket.list_blobs(prefix=folder_prefix):
        if not blob.name or blob.name.endswith("/"):
            continue

        name = blob.name[len(folder_prefix):]
        if not name or "/" in name:
            continue
        if name.lower() in _SKIP_FILES:
            continue

        entries.append(
            {
                "name": name,
                "blob_name": blob.name,
                "size": int(blob.size or 0),
                "content_type": blob.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream",
                "is_image": _is_image_name(name),
            }
        )

    entries.sort(key=_entry_sort_key)
    return entries


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes or 0)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{int(num_bytes or 0)} B"


def register_training_content_routes(admin_bp, login_required) -> None:
    @admin_bp.get("/sessions/content")
    @login_required
    def session_content():
        bucket_name = current_app.config.get("BUCKET_NAME")
        base_prefix = current_app.config.get("BASE_PREFIX")

        dds_type = (request.args.get("type") or "").strip().lower()
        folder_id = (request.args.get("folderId") or "").strip()
        session_id = (request.args.get("sessionId") or "").strip()

        if dds_type not in ("online", "normal"):
            abort(400, description="Tipo de DDS inválido.")
        if not folder_id and not session_id:
            abort(400, description="folderId ou sessionId é obrigatório.")
        if not bucket_name:
            abort(500, description="DDS_BUCKET_NAME não configurado.")

        session_data = _find_session(
            bucket_name=bucket_name,
            base_prefix=base_prefix,
            dds_type=dds_type,
            folder_id=folder_id,
            session_id=session_id,
        )
        if not session_data:
            abort(404, description="Treinamento não encontrado.")

        resolved_folder_id = (session_data.get("folderId") or folder_id).strip()
        if not resolved_folder_id:
            abort(404, description="folderId do treinamento não encontrado.")

        files = _list_training_files(
            bucket_name=bucket_name,
            base_prefix=base_prefix,
            folder_id=resolved_folder_id,
        )
        image_files = [item for item in files if item.get("is_image")]
        other_files = [item for item in files if not item.get("is_image")]

        for item in files:
            item["size_label"] = _format_size(item.get("size") or 0)

        return render_template(
            "session_content.html",
            session_item=session_data,
            folder_id=resolved_folder_id,
            image_files=image_files,
            other_files=other_files,
            all_files=files,
        )

    @admin_bp.get("/sessions/content/asset")
    @login_required
    def session_content_asset():
        bucket_name = current_app.config.get("BUCKET_NAME")
        base_prefix = current_app.config.get("BASE_PREFIX")

        folder_id = (request.args.get("folderId") or "").strip()
        blob_name = (request.args.get("blob") or "").strip()
        download = (request.args.get("download") or "").strip() == "1"

        if not bucket_name:
            abort(500, description="DDS_BUCKET_NAME não configurado.")
        if not folder_id or not blob_name:
            abort(400, description="Parâmetros inválidos.")

        allowed_prefix = _safe_folder_prefix(base_prefix, folder_id)
        if not blob_name.startswith(allowed_prefix):
            abort(403, description="Arquivo fora do prefixo permitido.")

        client = _gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            abort(404, description="Arquivo não encontrado.")

        data = blob.download_as_bytes()
        filename = os.path.basename(blob_name)
        mimetype = blob.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

        return send_file(
            io.BytesIO(data),
            mimetype=mimetype,
            download_name=filename,
            as_attachment=download,
            max_age=0,
        )
