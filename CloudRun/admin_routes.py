"""
============================================================
FILE: admin_routes.py
FUNCTION: Flask Blueprint implementing the DDS ONLINE admin panel:
          - /admin/login, /admin/logout
          - /admin dashboard
          - create/edit/cancel DDS ONLINE sessions

          This panel preserves backward compatibility with the existing app by
          writing a Storage package (Slide1.JPG + reuniao.json) and updating
          DDSv2/lista.json.
============================================================
"""

from __future__ import annotations

import functools
import io
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import re


from PIL import Image
from werkzeug.datastructures import FileStorage

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
    jsonify,
)

from google.cloud import storage

# Signed URL em Cloud Run (sem chave privada)
# -------------------------------------------
# No Cloud Run, as credenciais padrão do ambiente são "token-only" (Compute Engine
# Credentials). Para assinar V4 Signed URLs, precisamos de credenciais capazes de
# assinar via IAMCredentials (signBlob). A abordagem recomendada é usar
# impersonated_credentials, desde que a Service Account do serviço tenha
# roles/iam.serviceAccountTokenCreator sobre a Service Account que fará a assinatura.
from google.auth import default as google_auth_default
from google.auth import impersonated_credentials


from storage_online_package import (
    list_all_sessions_from_storage,
    list_online_sessions_from_storage,
    update_online_package,
    create_online_package_and_update_lista_json,
)

from storage_normal_package import (
    create_normal_package_and_update_lista_json,
    delete_normal_package_and_update_lista_json,
)

try:
    from firestore_sessions import upsert_dds_session
except Exception:  # pragma: no cover
    upsert_dds_session = None


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# ===========================
# Upload direto (GCS Signed URL)
# ===========================
def _gcs_client() -> storage.Client:
    return storage.Client()

 
def _get_signing_credentials(target_service_account: str, *, lifetime_seconds: int = 3600):
    """Obtém credenciais "assináveis" via IAMCredentials (signBlob).

    - Em Cloud Run, as credenciais padrão (metadata server) não possuem chave privada.
    - Com impersonation, o Google assina via API IAMCredentials.

    Requisitos:
      - API iamcredentials.googleapis.com habilitada
      - A SA do serviço (Cloud Run) deve ter roles/iam.serviceAccountTokenCreator
        sobre a SA informada em target_service_account.
    """
    if not target_service_account:
        raise ValueError("SIGNING_SERVICE_ACCOUNT não configurada.")

    source_credentials, _ = google_auth_default()
    return impersonated_credentials.Credentials(
        source_credentials=source_credentials,
        target_principal=target_service_account,
        target_scopes=["https://www.googleapis.com/auth/devstorage.read_write"],
        lifetime=lifetime_seconds,
    )


def _sign_put_url(*, bucket_name: str, object_name: str, content_type: str, minutes: int = 15) -> str:
    """
    Gera Signed URL (V4) para upload via PUT direto no GCS.
    Observação: em Cloud Run, pode exigir que a service account tenha permissão
    iam.serviceAccounts.signBlob (ex.: roles/iam.serviceAccountTokenCreator).
    """
    # Preferir assinatura via IAMCredentials em Cloud Run (sem chave privada).
    signing_sa = (current_app.config.get("SIGNING_SERVICE_ACCOUNT") or "").strip()
    if signing_sa:
        creds = _get_signing_credentials(signing_sa, lifetime_seconds=max(3600, minutes * 60))
        client = storage.Client(credentials=creds)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=minutes),
            method="PUT",
            content_type=content_type or "application/octet-stream",
            credentials=creds,
        )

    # Fallback (dev/local): funciona quando a credencial ativa possui chave privada
    # (ex.: GOOGLE_APPLICATION_CREDENTIALS apontando para uma Service Account JSON).
    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=minutes),
        method="PUT",
        content_type=content_type or "application/octet-stream",
    )
# ============================================================
# FILE: admin_routes.py
# FUNCTION: Date/time normalization helpers for form inputs.
# ============================================================


def normalize_date_to_yyyy_mm_dd(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Data é obrigatória.")

    # HTML <input type="date"> -> YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        datetime.strptime(raw, "%Y-%m-%d")  # valida
        return raw

    # fallback: DD/MM/YYYY
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", raw):
        d = datetime.strptime(raw, "%d/%m/%Y")
        return d.strftime("%Y-%m-%d")

    raise ValueError(f"Data inválida: '{raw}'. Use YYYY-MM-DD.")
    

def normalize_time_hhmm(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Hora é obrigatória.")

    # HTML <input type="time"> -> HH:MM
    if re.fullmatch(r"\d{2}:\d{2}", raw):
        datetime.strptime(raw, "%H:%M")  # valida
        return raw

    raise ValueError(f"Hora inválida: '{raw}'. Use HH:MM.")


def login_required(view):
    """Decorator enforcing MVP login."""

    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            # Para chamadas via fetch/API, não redirecionar HTML (isso quebra .json()).
            wants_json = (
                request.is_json
                or "application/json" in (request.headers.get("Accept") or "").lower()
                or request.path.endswith("/sessions/prepare")
            )
            if wants_json:
                return jsonify({
                    "ok": False,
                    "error": "Não autenticado. Faça login novamente.",
                    "redirect": url_for("admin.login", next=request.path),
                }), 401
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)

    return wrapper

def _rget(result, key, default=None):
    if result is None:
        return default
    if isinstance(result, dict):
        return result.get(key, default)
    return getattr(result, key, default)



@admin_bp.get("/login")
def login():
    next_url = request.args.get("next") or url_for("admin.dashboard")
    return render_template("login.html", next_url=next_url)


@admin_bp.post("/login")
def login_post():
    admin_password = current_app.config.get("ADMIN_PASSWORD", "")
    if not admin_password:
        flash("ADMIN_PASSWORD não está configurada no serviço.", "error")
        return redirect(url_for("admin.login"))

    password = (request.form.get("password") or "").strip()
    next_url = (request.form.get("next_url") or "").strip() or url_for("admin.dashboard")

    if password != admin_password:
        flash("Senha inválida.", "error")
        return redirect(url_for("admin.login", next=next_url))

    session["is_admin"] = True
    flash("Login realizado com sucesso.", "success")
    return redirect(next_url)


@admin_bp.post("/logout")
@login_required
def logout():
    session.clear()
    flash("Logout realizado.", "success")
    return redirect(url_for("admin.login"))


@admin_bp.get("")
@login_required
def dashboard():
    """Dashboard: list sessions from Storage (reuniao.json)."""
    month = (request.args.get("month") or "").strip()  # expects YYYY-MM
    team = (request.args.get("team") or "").strip().upper()
    status = (request.args.get("status") or "").strip().lower()

    bucket = current_app.config.get("BUCKET_NAME")
    base_prefix = current_app.config.get("BASE_PREFIX")

    if not bucket:
        flash("DDS_BUCKET_NAME não configurado.", "error")
        sessions_list: list[Dict[str, Any]] = []
    else:
        sessions_list = list_all_sessions_from_storage(
            bucket_name=bucket,
            base_prefix=base_prefix,
            month=month or None,
            team=team or None,
        )

    # Filter status (optional)
    if status:
        sessions_list = [s for s in sessions_list if (s.get("status") or "").lower() == status]

    # Sort by date/time descending when present
    def _key(x: Dict[str, Any]):
        # NORMAL has empty time -> still sorts correctly by date, then time.
        return (x.get("date", ""), x.get("time", ""))

    sessions_list.sort(key=_key, reverse=True)

    return render_template(
        "dashboard.html",
        sessions=sessions_list,
        month=month,
        team=team,
        status=status,
        base_prefix=base_prefix,
        now=datetime.now(),
    )


@admin_bp.get("/sessions/new")
@login_required
def session_new():
    return render_template(
        "session_form.html",
        heading="Novo agendamento DDS ONLINE",
        action_url=url_for("admin.session_new_post"),
        form={
            "hostTeam": "",
            "date": "",
            "time": "",
            "durationMin": 30,
            "subject": "",
            "status": "scheduled",
        },

        show_status=False,
    )

  

@admin_bp.post("/sessions/prepare")
@login_required
def session_prepare_uploads():
    """
    Prepara a sessão (cria package no Storage) e retorna Signed URLs para upload direto.
    Evita estourar 32MB (Cloud Run) porque o browser faz PUT direto no GCS.

    Body JSON esperado:
      {
        ddsType, hostTeam?, date, time?, durationMin?, subject,
        slidesCount: int,
        slides: [{name, type, size}]
    }
    """
    bucket = current_app.config.get("BUCKET_NAME")
    base_prefix = current_app.config.get("BASE_PREFIX")
    tz = (current_app.config.get("TIMEZONE_NAME") or "America/Sao_Paulo").strip()

    if not bucket:
        return jsonify({"ok": False, "error": "DDS_BUCKET_NAME não configurado."}), 400

    data = request.get_json(silent=True) or {}

    dds_type = (data.get("ddsType") or "online").strip().lower()
    if dds_type not in ("online", "normal"):
        return jsonify({"ok": False, "error": "ddsType inválido (use 'online' ou 'normal')."}), 400

    # Textos padronizados em MAIÚSCULA (como solicitado)
    host_team = (data.get("hostTeam") or "").strip().upper()
    subject = (data.get("subject") or "").strip().upper()

    try:
        date = normalize_date_to_yyyy_mm_dd(data.get("date", ""))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400





    slides = data.get("slides") or []
    upload_count = int(data.get("slidesCount") or len(slides) or 0)
    upload_count = max(0, min(59, upload_count))  # reserva 1 p/ placeholder

    # Por padrão, manter placeholder como Slide1
    include_placeholder = bool(data.get("includePlaceholder", True))
    slides_count = upload_count + (1 if include_placeholder else 0)
    slides_count = max(1, min(60, slides_count))

    # ============================================================
    # DDS NORMAL (slideshow) — pasta nomeada por assunto
    # ============================================================
    if dds_type == "normal":
        if not subject:
            return jsonify({"ok": False, "error": "Assunto (subject) é obrigatório para DDS Normal."}), 400

        try:
            result = create_normal_package_and_update_lista_json(
                bucket_name=bucket,
                base_prefix=base_prefix,
                date_yyyy_mm_dd=date,
                subject=subject,
                slides_count=slides_count,
                timezone_name=tz,
                status="scheduled",
            )

            folder_id = _rget(result, "folder_id") or _rget(result, "folderId")
            payload = _rget(result, "payload") or {}
            session_id = payload.get("sessionId") or _rget(result, "session_id")

            if not folder_id:
                return jsonify({"ok": False, "error": "Falha ao determinar folderId para DDS Normal."}), 500

            folder_prefix = f"{base_prefix}/{folder_id}".replace("//", "/").strip("/")

            # Signed URLs para uploads do usuário
            items = []

            # DDS NORMAL: uploads começam em Slide1 (overwrite do placeholder)
            for i in range(upload_count):
                idx = 1 + i
                object_name = f"{folder_prefix}/Slide{idx}.JPG"
                upload_url = _sign_put_url(
                    bucket_name=bucket,
                    object_name=object_name,
                    content_type="image/jpeg",
                    minutes=20,
                )
                items.append({
                    "index": idx,
                    "objectName": object_name,
                    "uploadUrl": upload_url,
                })

            # dashboard hoje lista apenas ONLINE; por ora retornamos editUrl para o dashboard.
            edit_url = url_for("admin.dashboard")
            return jsonify({
                "ok": True,
                "ddsType": "normal",
                "sessionId": session_id,
                "folderId": folder_id,
                "folderPrefix": folder_prefix,
                "slides": items,
                "editUrl": edit_url,
            })
        except Exception as e:
            current_app.logger.exception("Erro em DDS Normal /prepare: %s", e)
            return jsonify({"ok": False, "error": f"Erro interno ao preparar DDS Normal: {e}"}), 500

    # ============================================================
    # DDS ONLINE (reunião) — mantém fluxo atual
    # ============================================================
    if not host_team:
        return jsonify({"ok": False, "error": "Equipe (hostTeam) é obrigatória para DDS On-line."}), 400

    try:
        time = normalize_time_hhmm(data.get("time", ""))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    duration_min = _safe_int(str(data.get("durationMin") or "30"), 30)
 

    try:
        # 1) cria package e determina folder_prefix
        result = create_online_package_and_update_lista_json(
            bucket_name=bucket,
            base_prefix=base_prefix,
            date_yyyy_mm_dd=date,
            time_hhmm=time,
            host_team=host_team,
            subject=subject,
            duration_min=duration_min,
            slides_count=slides_count,
            timezone_name=tz,
        )
       

        folder_id = _rget(result, "folder_id") or _rget(result, "folderId")
        payload = _rget(result, "payload") or {}
        session_id = payload.get("sessionId") or _rget(result, "session_id")

        if not folder_id:
            return jsonify({"ok": False, "error": "Falha ao determinar folderId para upload."}), 500

        folder_prefix = f"{base_prefix}/{folder_id}".replace("//", "/").strip("/")

        # 2) gera signed urls APENAS para os uploads do usuário.
        #    Se placeholder estiver ativo, começamos no Slide2.
        items = []
        start_index = 2 if include_placeholder else 1
        for i in range(upload_count):
            idx = start_index + i
            object_name = f"{folder_prefix}/Slide{idx}.JPG"
            upload_url = _sign_put_url(
                bucket_name=bucket,
                object_name=object_name,
                content_type="image/jpeg",
                minutes=20,
            )
            items.append({
                "index": idx,
                "objectName": object_name,
                "uploadUrl": upload_url,
            })

        edit_url = url_for("admin.session_edit", session_id=session_id) if session_id else url_for("admin.dashboard")
        return jsonify({
            "ok": True,
            "sessionId": session_id,
            "folderId": folder_id,
            "folderPrefix": folder_prefix,
            "slides": items,
            "editUrl": edit_url,
        })
    except Exception as e:
        current_app.logger.exception("Erro em /admin/sessions/prepare: %s", e)
        return jsonify({"ok": False, "error": f"Erro interno ao preparar uploads: {e}"}), 500


def _safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _iter_uploaded_slides(files) -> list[tuple[int, FileStorage]]:
    """
    Read inputs slide_1, slide_2, ... from request.files and return sorted list.
    """
    out: list[tuple[int, FileStorage]] = []
    for key in files.keys():
        if not key.startswith("slide_"):
            continue
        try:
            n = int(key.split("_", 1)[1])
        except Exception:
            continue
        f = files.get(key)
        if f and getattr(f, "filename", ""):
            out.append((n, f))
    out.sort(key=lambda x: x[0])
    return out


def _normalize_to_jpeg_1920x1080(file: FileStorage) -> bytes:
    """
    Convert uploaded image to JPEG 1920x1080.
    Deterministic output; prevents unexpected formats.
    """
    # Ensure we start from the beginning
    try:
        file.stream.seek(0)
    except Exception:
        pass

    img = Image.open(file.stream).convert("RGB")
    img = img.resize((1920, 1080))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()

def _maybe_upsert_firestore(payload: Dict[str, Any]) -> None:
    if not current_app.config.get("ENABLE_FIRESTORE"):
        return
    if upsert_dds_session is None:
        return
    try:
        upsert_dds_session(payload)
    except Exception as e:
        # Do not block Storage compatibility path.
        current_app.logger.exception("Firestore upsert failed: %s", e)


@admin_bp.post("/sessions/new")
@login_required
def session_new_post():
    bucket = current_app.config.get("BUCKET_NAME")
    base_prefix = current_app.config.get("BASE_PREFIX")
    tz = (current_app.config.get("TIMEZONE_NAME") or "America/Sao_Paulo").strip()

    if not bucket:
        flash("DDS_BUCKET_NAME não configurado.", "error")
        return redirect(url_for("admin.session_new"))

    host_team = (request.form.get("hostTeam") or "").strip()
    subject = (request.form.get("subject") or "").strip()

    try:
        date = normalize_date_to_yyyy_mm_dd(request.form.get("date", ""))
        time = normalize_time_hhmm(request.form.get("time", ""))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.session_new"))


    duration_min = _safe_int((request.form.get("durationMin") or "30").strip(), 30)

    # Importante:
    # - Quando o frontend usa upload direto para GCS (recommended path), este POST
    #   deve chegar SEM binários grandes (evita 413). Nesse caso, slidesCount pode vir via form.
    # - Mantemos compatibilidade para uploads pequenos via multipart (fallback).
    slides_count = _safe_int((request.form.get("slidesCount") or "").strip(), 0)

    slides_files = request.files.getlist("slides")
    slides_files = [f for f in slides_files if f and getattr(f, "filename", "")]
    if slides_count <= 0:
        slides_count = len(slides_files) if slides_files else 1
    

    if not host_team:
        flash("Equipe (hostTeam) é obrigatória.", "error")
        return redirect(url_for("admin.session_new"))

    # Create package in Storage + update lista.json
    result = create_online_package_and_update_lista_json(
        bucket_name=bucket,
        base_prefix=base_prefix,
        date_yyyy_mm_dd=date,
        time_hhmm=time,
        host_team=host_team,
        subject=subject,
        duration_min=duration_min,
        slides_count=slides_count,
        timezone_name=tz,
    )
    
    # Fallback (multipart pequeno):
    # Se vierem arquivos aqui, ainda fazemos upload via backend.
    # Para a rota moderna (upload direto), os JPGs já estarão no GCS
    # e este bloco normalmente NÃO executa.
    if slides_files:
        try:
            from storage_online_package import upload_slides_to_online_folder

            slides_bytes = []
            for idx, f in enumerate(slides_files, start=1):
                # Reserva Slide1 para placeholder -> uploads começam no Slide2
                slides_bytes.append((idx + 1, _normalize_to_jpeg_1920x1080(f)))

            folder_id = _rget(result, "folder_id") or _rget(result, "folderId")
            if folder_id:
                folder_prefix = f"{base_prefix}/{folder_id}".replace("//", "/")
                upload_slides_to_online_folder(bucket_name=bucket, folder_prefix=folder_prefix, slides=slides_bytes)
        except Exception as e:
            flash(f"Falha ao enviar slides (fallback): {e}", "warning")

    # Optional Firestore mirror
    payload = getattr(result, "payload", None) if result is not None else None
    if payload is None and isinstance(result, dict):
        payload = result.get("payload")

    if payload:
        _maybe_upsert_firestore(payload)

    payload = _rget(result, "payload") or {}
    session_id = payload.get("sessionId") or _rget(result, "session_id")

    if session_id:
        flash(f"Sessão criada: {session_id}", "success")

        # REGRA:
        # - Sem anexos (fluxo padrão): cria placeholder e volta para o dashboard
        # - Com anexos (fallback multipart): pode ir para edição
        if not slides_files:
            return redirect(url_for("admin.dashboard"))

        return redirect(url_for("admin.session_edit", session_id=session_id))

    flash("Sessão criada, mas não foi possível determinar o sessionId.", "warning")
    return redirect(url_for("admin.dashboard"))



@admin_bp.get("/sessions/<session_id>/edit")
@login_required
def session_edit(session_id: str):
    # Fetch metadata from Storage based on session_id. We use folderId stored in JSON file.
    bucket = current_app.config.get("BUCKET_NAME")
    base_prefix = current_app.config.get("BASE_PREFIX")

    if not bucket:
        flash("DDS_BUCKET_NAME não configurado.", "error")
        return redirect(url_for("admin.dashboard"))

    # Best-effort: list sessions and find matching sessionId
    sessions_list = list_online_sessions_from_storage(
        bucket_name=bucket,
        base_prefix=base_prefix,
        limit=200
    )
    data: Optional[Dict[str, Any]] = next((s for s in sessions_list if s.get("sessionId") == session_id), None)

    if not data:
        flash("Sessão não encontrada no Storage (reuniao.json).", "error")
        return redirect(url_for("admin.dashboard"))

    # For edit, convert date/time into HTML input formats (YYYY-MM-DD, HH:MM)
    return render_template(
        "session_form.html",
        heading=f"Editar sessão {session_id}",
        action_url=url_for("admin.session_edit_post", session_id=session_id),
        form={
            "hostTeam": data.get("hostTeam", ""),
            "date": data.get("date", ""),
            "time": data.get("time", ""),
            "durationMin": data.get("durationMin", 30),
            "subject": data.get("subject", ""),
            "status": data.get("status", "scheduled"),
        },
        show_status=True,
    )


@admin_bp.post("/sessions/<session_id>/edit")
@login_required
def session_edit_post(session_id: str):
    bucket = current_app.config.get("BUCKET_NAME")
    base_prefix = current_app.config.get("BASE_PREFIX")
    tz = (current_app.config.get("TIMEZONE_NAME") or "America/Sao_Paulo").strip()

    if not bucket:
        flash("DDS_BUCKET_NAME não configurado.", "error")
        return redirect(url_for("admin.dashboard"))

    # For edit, we keep the sessionId stable (folder is derived from date/time).
    # If date/time changes, folderId changes. We'll update the package in-place by creating the new folder
    # and updating lista.json; old entries will remain (acceptable for MVP) unless you implement cleanup.

    host_team = (request.form.get("hostTeam") or "").strip()
    subject = (request.form.get("subject") or "").strip()

    try:
        date = normalize_date_to_yyyy_mm_dd(request.form.get("date", ""))
        time = normalize_time_hhmm(request.form.get("time", ""))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.session_edit", session_id=session_id))
    
    duration_min = _safe_int((request.form.get("durationMin") or "30").strip(), 30)
    status = (request.form.get("status") or "scheduled").strip().lower()

    result = update_online_package(
        bucket_name=bucket,
        base_prefix=base_prefix,
        date_yyyy_mm_dd=date,
        time_hhmm=time,
        host_team=host_team,
        subject=subject,
        duration_min=duration_min,
        timezone_name=tz,
        status=status,
    )

    # Optional slide uploads (multi-file). Order selected in file picker becomes Slide1, Slide2, ...
    slides_files = request.files.getlist("slides")
    slides_files = [f for f in slides_files if f and getattr(f, "filename", "")]
    if slides_files:
        try:
            from storage_online_package import upload_slides_to_online_folder

            slides_bytes = []
            for idx, f in enumerate(slides_files, start=1):
                # Reserva Slide1 para placeholder -> uploads começam no Slide2
                slides_bytes.append((idx + 1, _normalize_to_jpeg_1920x1080(f)))

            folder_id = _rget(result, "folder_id") or _rget(result, "folderId")
            if folder_id:
                folder_prefix = f"{base_prefix}/{folder_id}".replace("//", "/")
                upload_slides_to_online_folder(bucket_name=bucket, folder_prefix=folder_prefix, slides=slides_bytes)
        except Exception as e:
            flash(f"Falha ao enviar slides: {e}", "warning")

    payload = _rget(result, "payload") or {}
    session_id2 = payload.get("sessionId") or _rget(result, "session_id")

    _maybe_upsert_firestore(payload)

    flash("Sessão atualizada.", "success")
    return redirect(url_for("admin.session_edit", session_id=session_id2 or session_id))


@admin_bp.post("/sessions/<session_id>/cancel")
@login_required
def session_cancel(session_id: str):
    # Cancel by updating metadata + placeholder slide (status=canceled)
    bucket = current_app.config.get("BUCKET_NAME")
    base_prefix = current_app.config.get("BASE_PREFIX")
    tz = (current_app.config.get("TIMEZONE_NAME") or "America/Sao_Paulo").strip()

    if not bucket:
        flash("DDS_BUCKET_NAME não configurado.", "error")
        return redirect(url_for("admin.dashboard"))

    # Load current data
    sessions_list = list_online_sessions_from_storage(bucket, base_prefix, limit=200)
    data = next((s for s in sessions_list if s.get("sessionId") == session_id), None)

    if not data:
        flash("Sessão não encontrada.", "error")
        return redirect(url_for("admin.dashboard"))

    result = update_online_package(
        bucket_name=bucket,
        base_prefix=base_prefix,
        date_yyyy_mm_dd=data.get("date"),
        time_hhmm=data.get("time"),
        host_team=data.get("hostTeam"),
        subject=data.get("subject"),
        duration_min=int(data.get("durationMin") or 30),
        timezone_name=tz,
        status="canceled",
    )

    payload = _rget(result, "payload") or {}
    _maybe_upsert_firestore(payload)

    flash("Sessão cancelada.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.post("/sessions/delete")
@login_required
def session_delete():
    """
    Delete a session folder from Storage and remove its entries from DDSv2/lista.json.

    Accepts JSON or form-encoded:
      - type: "online" | "normal"
      - folderId: "YYYY-MM-DD - ... "
    """
    bucket = current_app.config.get("BUCKET_NAME")
    base_prefix = current_app.config.get("BASE_PREFIX")
    if not bucket:
        return jsonify({"ok": False, "error": "DDS_BUCKET_NAME não configurado."}), 400

    data = request.get_json(silent=True) or request.form or {}
    dds_type = (data.get("type") or data.get("ddsType") or "").strip().lower()
    folder_id = (data.get("folderId") or "").strip()

    if dds_type not in ("online", "normal"):
        return jsonify({"ok": False, "error": "type inválido (use 'online' ou 'normal')."}), 400
    if not folder_id:
        return jsonify({"ok": False, "error": "folderId é obrigatório."}), 400

    # Safety: only allow deleting inside BASE_PREFIX and with expected naming prefix YYYY-MM-DD
    if not re.match(r"^\d{4}-\d{2}-\d{2}\s-\s", folder_id):
        return jsonify({"ok": False, "error": "folderId inválido."}), 400

    try:
        if dds_type == "online":
            result = delete_online_package_and_update_lista_json(
                bucket_name=bucket,
                base_prefix=base_prefix,
                folder_id=folder_id,
            )
        else:
            result = delete_normal_package_and_update_lista_json(
                bucket_name=bucket,
                base_prefix=base_prefix,
                folder_id=folder_id,
            )
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        current_app.logger.exception("Erro ao excluir pacote (%s): %s", dds_type, e)
        return jsonify({"ok": False, "error": f"Erro interno ao excluir: {e}"}), 500