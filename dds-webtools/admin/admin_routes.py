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
import os
import io
import json
import time
import threading
import queue
import inspect
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import Any, Dict, Optional, Callable
import re
import logging

from training_management.deletion import handle_training_delete_request


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
    send_file,
    abort,
    Response,
    stream_with_context,
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
    list_all_folders_from_storage,
)


from storage_normal_package import (
    create_normal_package_and_update_lista_json,
    delete_normal_package_and_update_lista_json,
)

try:
    from firestore_sessions import upsert_dds_session
except Exception:  # pragma: no cover
    upsert_dds_session = None

# DDS Reports (execução)
# --------------------------------------------------------------------
# IMPORT DEFENSIVO:
#   - Engine base (Fotos + Presence Matrix) NÃO pode cair por causa de
#     módulos opcionais (Detalhado/Ranking).
# --------------------------------------------------------------------
_DDS_REPORTS_IMPORT_ERROR = None

build_or_get_report_photos = None
materialize_report_to_tmp = None
get_presence_matrix = None

build_or_get_report_detalhado = None
build_or_get_report_ranking = None

# Presença PDF antiga foi descontinuada: "presenca" agora é PAINEL.
build_or_get_report_presenca = None

try:
    from dds_reports_engine import (
        build_or_get_report_photos,
        materialize_report_to_tmp,
        get_presence_matrix,
    )
except Exception as e:  # pragma: no cover
    logging.exception("Falha ao importar engine base de relatórios (dds_reports_engine): %s", e)
    _DDS_REPORTS_IMPORT_ERROR = f"engine:{type(e).__name__}: {e}"

# módulos opcionais
try:
    from dds_report_detalhado import build_or_get_report_detalhado
except Exception as e:  # pragma: no cover
    logging.exception("Falha ao importar relatório detalhado (dds_report_detalhado): %s", e)
    _DDS_REPORTS_IMPORT_ERROR = (_DDS_REPORTS_IMPORT_ERROR or "") + f" | detalhado:{type(e).__name__}: {e}"
    build_or_get_report_detalhado = None

try:
    from dds_report_ranking import build_or_get_report_ranking
except Exception as e:  # pragma: no cover
    logging.exception("Falha ao importar relatório ranking (dds_report_ranking): %s", e)
    _DDS_REPORTS_IMPORT_ERROR = (_DDS_REPORTS_IMPORT_ERROR or "") + f" | ranking:{type(e).__name__}: {e}"
    build_or_get_report_ranking = None

admin_bp = Blueprint("admin", __name__, url_prefix="")


# ===========================
# Versão (Cloud Run K_REVISION)
# ===========================
@admin_bp.app_context_processor
def inject_revision():
    rev = (os.getenv("K_REVISION") or os.getenv("APP_REVISION") or "local").strip()
    if "-" in rev:
        parts = rev.split("-")
        if len(parts) >= 2:
            rev = "-".join(parts[-2:])
    return {"app_revision_short": rev}


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

    source_credentials, _ = google_auth_default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
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

    # Fallback: Se estiver no Cloud Run e sem SA configurada, tenta descobrir a SA padrão do serviço
    if not signing_sa and (os.getenv("K_SERVICE") or os.getenv("K_REVISION")):
        try:
            source_creds, _ = google_auth_default()
            if hasattr(source_creds, "service_account_email"):
                signing_sa = source_creds.service_account_email
        except Exception:
            pass

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
            service_account_email=signing_sa,
         )

    if os.getenv("K_SERVICE") or os.getenv("K_REVISION"):
        # Se mesmo após o fallback não tivermos uma SA, lançamos o erro explicativo.
        raise RuntimeError(
            "SIGNING_SERVICE_ACCOUNT não configurada e não foi possível detectar a SA padrão no Cloud Run. "
            "Configure a variável de ambiente SIGNING_SERVICE_ACCOUNT para gerar Signed URLs."
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
def _cache_obj_name(cache_prefix: str, rel: str) -> str:
    """Monta o nome do objeto no bucket para um caminho relativo do cache."""
    rel = (rel or "").lstrip("/")
    pref = (cache_prefix or "").strip().strip("/")
    return f"{pref}/{rel}" if pref else rel

 
def _materialize_gcs_to_tmp(*, bucket_name: str, cache_prefix: str, rel_path: str) -> Path:
    """
    Fallback para baixar um arquivo do cache direto do GCS para /tmp,
    sem depender de materialize_report_to_tmp.
    """
    rel = (rel_path or "").lstrip("/")
    tmp_root = Path("/tmp/dds_reports")
    local_path = tmp_root / rel
    local_path.parent.mkdir(parents=True, exist_ok=True)

    # reuso local
    try:
        if local_path.exists() and local_path.stat().st_size > 0:
            return local_path
    except Exception:
        pass

    obj = _cache_obj_name(cache_prefix, rel)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(obj)
    if not blob.exists():
        raise FileNotFoundError(f"Objeto não encontrado no GCS: {obj}")

    blob.download_to_filename(str(local_path))
    return local_path

 

def _sign_get_url(
    *,
    bucket_name: str,
    object_name: str,
    minutes: int = 60,
    disposition: str = "inline",
    filename: str = "arquivo.pdf",
    response_type: str = "application/pdf",
) -> Optional[str]:
    """Gera Signed URL (V4) para GET (preview/download) direto do GCS."""
    try:
        signing_sa = (current_app.config.get("SIGNING_SERVICE_ACCOUNT") or "").strip()

        # Fallback: Se estiver no Cloud Run e sem SA configurada, tenta descobrir a SA padrão do serviço
        if not signing_sa and (os.getenv("K_SERVICE") or os.getenv("K_REVISION")):
            try:
                source_creds, _ = google_auth_default()
                if hasattr(source_creds, "service_account_email"):
                    signing_sa = source_creds.service_account_email
            except Exception:
                pass

        if signing_sa:
            creds = _get_signing_credentials(signing_sa, lifetime_seconds=max(3600, minutes * 60))
            client = storage.Client(credentials=creds)
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(object_name)
            return blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=minutes),
                method="GET",
                response_disposition=f'{disposition}; filename="{filename}"',
                response_type=response_type,
                credentials=creds,
                service_account_email=signing_sa,
            )

        if os.getenv("K_SERVICE") or os.getenv("K_REVISION"):
            raise RuntimeError(
                "SIGNING_SERVICE_ACCOUNT não configurada e não detectada no Cloud Run. "
                "Configure a service account assinadora para gerar Signed URLs."
            )


        client = _gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=minutes),
            method="GET",
            response_disposition=f'{disposition}; filename="{filename}"',
            response_type=response_type,
        )
    except Exception:
        return None


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
                or "text/event-stream" in (request.headers.get("Accept") or "").lower()
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


def _parse_yyyy_mm_dd(raw: str) -> date:
    raw = (raw or "").strip()
    return datetime.strptime(raw, "%Y-%m-%d").date()

def _days_total(start_date: str, end_date: str) -> int:
    s = _parse_yyyy_mm_dd(start_date)
    e = _parse_yyyy_mm_dd(end_date)
    if e < s:
        raise ValueError("A data final não pode ser menor que a data inicial.")
    return (e - s).days + 1


_MESES_PT_ABREV = (
    "JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
    "JUL", "AGO", "SET", "OUT", "NOV", "DEZ",
)


def _fmt_date_br(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return raw


def _build_presence_print_meta(days, day_has_any, hide_nodata: bool) -> Dict[str, Any]:
    """
    Monta a lista de colunas efetivamente visíveis na tabela de presença,
    os grupos de mês para o cabeçalho e o tamanho do papel para impressão.
    Regra:
      - até 40 dias visíveis -> A4 paisagem
      - acima de 40 dias visíveis -> A3 paisagem
    """
    visible_days = []
    day_has_any = list(day_has_any or [])

    for idx, raw_day in enumerate(days or []):
        has_any = bool(day_has_any[idx]) if idx < len(day_has_any) else True
        if hide_nodata and not has_any:
           continue

        d = datetime.strptime(str(raw_day)[:10], "%Y-%m-%d").date()
        visible_days.append({
            "idx": idx,
            "iso": d.isoformat(),
            "day_label": f"{d.day:02d}",
            "month": d.month,
            "year": d.year,
            "month_label": f"{_MESES_PT_ABREV[d.month - 1]}/{str(d.year)[2:]}",
            "has_any": has_any,
        })

    month_groups = []
    for item in visible_days:
        key = (item["year"], item["month"])
        if month_groups and month_groups[-1]["key"] == key:
            month_groups[-1]["colspan"] += 1
        else:
            month_groups.append({
                "key": key,
                "label": item["month_label"],
                "colspan": 1,
                "tone": "a" if len(month_groups) % 2 == 0 else "b",
            })

    visible_days_count = len(visible_days)
    paper_size = "A4" if visible_days_count <= 40 else "A3"

    return {
        "visible_days": visible_days,
        "visible_days_count": visible_days_count,
        "month_groups": month_groups,
        "paper_size": paper_size,
    }

def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
 

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
    return redirect(next_url)


# ------------------------------------------------------------------
# Presença (página rápida) — matriz Equipe × Dia (sem gerar PDF)
# ------------------------------------------------------------------
@admin_bp.get("/dds-presenca")
@login_required
def dds_presenca():
    today = date.today()
    start_default = (today - timedelta(days=13)).strftime("%Y-%m-%d")
    end_default = today.strftime("%Y-%m-%d")

    start_date = (request.args.get("start_date") or start_default).strip()
    end_date = (request.args.get("end_date") or end_default).strip()

    team_q = (request.args.get("team_q") or "").strip()
    sort = (request.args.get("sort") or "name").strip().lower()
    hide_nodata = (request.args.get("hide_nodata") or "0").strip().lower() in ("1", "true", "yes", "on")
    view = (request.args.get("view") or "all").strip().lower()
    only_absences = (request.args.get("only_absences") or "0").strip().lower() in ("1", "true", "yes", "on")

    reports_bucket = (current_app.config.get("REPORTS_BUCKET_NAME") or "").strip() or (current_app.config.get("BUCKET_NAME") or "").strip()
    cache_prefix = (current_app.config.get("REPORTS_CACHE_PREFIX") or "").strip()
    tz_name = (current_app.config.get("TIMEZONE_NAME") or "America/Sao_Paulo").strip()

    if not reports_bucket:
        flash("REPORTS_BUCKET_NAME/DDS_BUCKET_NAME não configurado.", "error")
        return redirect(url_for("admin.dashboard"))

 
    if get_presence_matrix is None:
        flash("Módulo de presença não carregou (engine desatualizada).", "error")
        return redirect(url_for("admin.dds_reports"))

    try:
        data = get_presence_matrix(
            start_date=start_date,
            end_date=end_date,
            tz_name=tz_name,
            bucket_name=reports_bucket,
            cache_prefix=cache_prefix,
            team_q=team_q,
            sort=sort,
            only_absences=only_absences,
        )
    except Exception as e:
        current_app.logger.exception("Erro ao montar presença: %s", e)
        flash(f"Erro ao carregar presença: {e}", "error")
        return redirect(url_for("admin.dashboard"))

    print_meta = _build_presence_print_meta(
        days=_rget(data, "days", []) or [],
        day_has_any=_rget(data, "day_has_any", []) or [],
        hide_nodata=hide_nodata,
    )

    date_range_label = f"{_fmt_date_br(start_date)} a {_fmt_date_br(end_date)}"        

    return render_template(
        "dds_presence.html",
        start_date=start_date,
        end_date=end_date,
        team_q=team_q,
        sort=sort,
        hide_nodata=hide_nodata,
        view=view,
        only_absences=only_absences,
        data=data,
        print_meta=print_meta,
        date_range_label=date_range_label,
    )


@admin_bp.post("/logout")
@login_required
def logout():
    session.clear()
    flash("Logout realizado.", "success")
    return redirect(url_for("admin.login"))

@admin_bp.get("/")
@login_required
def dashboard():
    """Dashboard: list sessions from Storage (reuniao.json + normal packages)."""
    month = (request.args.get("month") or "").strip()  # expects YYYY-MM
    team = (request.args.get("team") or "").strip().upper()

    # Filtro de status (derivado): agendado | concluido | cancelado
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

    # ============================================================
    # Status derivado (regra de ouro):
    #   - Cancelado: status raw == 'canceled'
    #   - Concluído: date < hoje
    #   - Agendado:  date >= hoje
    # ============================================================
    today = date.today()

    def _derive_status_key(s: Dict[str, Any]) -> str:
        raw = (s.get("status") or "").strip().lower()
        if raw == "canceled":
            return "cancelado"
        d = (s.get("date") or "").strip()
        try:
            if d:
                dd = datetime.strptime(d, "%Y-%m-%d").date()
                if dd < today:
                    return "concluido"
        except Exception:
            pass
        return "agendado"

    def _status_label(key: str) -> str:
        return {
            "agendado": "Agendado",
            "concluido": "Concluído",
            "cancelado": "Cancelado",
        }.get(key, key)

    for s in sessions_list:
        k = _derive_status_key(s)
        s["status_key"] = k
        s["status_label"] = _status_label(k)

    # Filter status (optional)
    if status:
        sessions_list = [s for s in sessions_list if (s.get("status_key") or "") == status]


    # Sort by date/time descending when present
    def _key(x: Dict[str, Any]):
        # NORMAL has empty time -> still sorts correctly by date, then time.
        return (x.get("date", ""), x.get("time", ""))

    sessions_list.sort(key=_key, reverse=True)
    # ============================================================
    # Contagem por mês (para o template não fazer O(n²))
    # month_counts: {"2026-02": 5, "2026-01": 10, ...}
    # ============================================================
    month_counts: Dict[str, int] = {}
    for s in sessions_list:
        d = (s.get("date") or "").strip()
        if len(d) >= 7:
            ym = d[:7]
            month_counts[ym] = month_counts.get(ym, 0) + 1


    # ============================================================
    # Calcular estatísticas para o dashboard
    # ============================================================
    stats = {
        "total": len(sessions_list),
        "agendado": len([s for s in sessions_list if s.get("status_key") == "agendado"]),
        "concluido": len([s for s in sessions_list if s.get("status_key") == "concluido"]),
        "cancelado": len([s for s in sessions_list if s.get("status_key") == "cancelado"]),
        "online": len([s for s in sessions_list if s.get("type") == "online"]),
        "normal": len([s for s in sessions_list if s.get("type") == "normal"]),
    }

    return render_template(
        "dashboard.html",
        sessions=sessions_list,
        stats=stats,
        month_counts=month_counts,
        month=month,
        team=team,
        status=status,
        base_prefix=base_prefix,
        now=datetime.now(),
    )


@admin_bp.get("/explorer")
@login_required
def explorer():
    """Explorador: lista todas as pastas reais do Bucket (sem filtros do App)."""
    bucket = current_app.config.get("BUCKET_NAME")
    base_prefix = current_app.config.get("BASE_PREFIX")

    month = request.args.get("month", "").strip()
    status = request.args.get("status", "").strip()
    
    if not bucket:
        flash("DDS_BUCKET_NAME não configurado.", "error")
        folders = []
    else:
        try:
            folders = list_all_folders_from_storage(
                bucket_name=bucket,
                base_prefix=base_prefix
            )
        except Exception as e:
            current_app.logger.exception("Erro no explorador: %s", e)
            flash(f"Erro ao ler storage: {e}", "error")
            folders = []

    # Aplica os filtros
    if month:
        folders = [f for f in folders if f["date"].startswith(month)]
    if status == "publicado":
        folders = [f for f in folders if f["is_published"]]
    elif status == "arquivado":
        folders = [f for f in folders if not f["is_published"]]

    # Calcula as estatísticas
    today_str = date.today().strftime("%Y-%m-%d")
    stats = {
        "total": len(folders),
        "agendado": len([f for f in folders if f["is_published"] and f["date"] >= today_str]),
        "concluido": len([f for f in folders if f["is_published"] and f["date"] < today_str]),
        "arquivado": len([f for f in folders if not f["is_published"]]),
        "online": len([f for f in folders if f.get("type") == "online"]),
        "normal": len([f for f in folders if f.get("type") == "normal"]),
    }

    return render_template(
        "explorer.html",
        folders=folders,
        stats=stats,
        month=month,
        status=status,
        base_prefix=base_prefix,
        now=datetime.now(),
    )




def _calc_pt_status(sess: Dict[str, Any]) -> str:
    """
    Status em PT-BR:
      - Cancelado: se status == 'canceled'
      - Concluído: se data < hoje
      - Agendado: se data >= hoje
    Obs: continua compatível com o que você já grava em lista.json/reuniao.json.
    """
    raw = (sess.get("status") or "").strip().lower()
    if raw == "canceled":
        return "Cancelado"

    d = (sess.get("date") or "").strip()
    today = date.today().strftime("%Y-%m-%d")
    if d and d < today:
        return "Concluído"
    return "Agendado"


@admin_bp.get("/report")
@login_required
def report():
    """
    Relatório simples (print-friendly) por mês/status.
    A ideia é abrir no browser e imprimir em PDF.
    """
    month = (request.args.get("month") or "").strip()  # YYYY-MM
    status = (request.args.get("status") or "").strip()  # Agendado|Concluído|Cancelado|Todos

    bucket = current_app.config.get("BUCKET_NAME")
    base_prefix = current_app.config.get("BASE_PREFIX")

    sessions_list: list[Dict[str, Any]] = []
    if bucket:
        sessions_list = list_all_sessions_from_storage(
            bucket_name=bucket,
            base_prefix=base_prefix,
            month=month or None,
            team=None,
        )

    # status calculado (PT-BR)
    for s in sessions_list:
        s["status_pt"] = _calc_pt_status(s)

    # filtro por status (opcional)
    if status and status.lower() != "todos":
        sessions_list = [s for s in sessions_list if s.get("status_pt") == status]

    # ordenação crescente (mais “relatório”)
    def _key(x: Dict[str, Any]):
        return (x.get("date", ""), x.get("time", ""))

    sessions_list.sort(key=_key)

    return render_template(
        "report.html",
        sessions=sessions_list,
        month=month,
        status=status or "Todos",
        now=datetime.now(),
    )


# ============================================================
# DDS Reports (execução - Firestore DDS)
# ============================================================

@admin_bp.get("/dds-reports")
@login_required
def dds_reports():
    """Tela de solicitação de relatórios DDS (execução)."""
    # defaults: mês atual (1º dia) -> hoje
    today = date.today()
    start_default = today.replace(day=1).strftime("%Y-%m-%d")
    end_default = today.strftime("%Y-%m-%d")

    start_date = (request.args.get("start_date") or start_default).strip()
    end_date = (request.args.get("end_date") or end_default).strip()
    rtype = (request.args.get("type") or "fotos").strip().lower()


    return render_template(
        "dds_reports.html",
        start_date=start_date,
        end_date=end_date,
        rtype=rtype,
    )


@admin_bp.post("/dds-reports/generate")
@login_required
def dds_reports_generate():
    if (build_or_get_report_photos is None) and (build_or_get_report_detalhado is None) and (build_or_get_report_ranking is None):

        flash("Módulo de relatórios não carregou (dependências ausentes).", "error")
        return redirect(url_for("admin.dds_reports"))

    start_date = (request.form.get("start_date") or "").strip()
    end_date = (request.form.get("end_date") or "").strip()
    rtype = (request.form.get("type") or "fotos").strip().lower()
    force = (request.form.get("force") or "").strip().lower() in ("1", "true", "yes", "on")

    # "presenca" agora é o PAINEL (não gera PDF / não usa SSE)
    if rtype == "presenca":
        return redirect(url_for("admin.dds_presenca", start_date=start_date, end_date=end_date))


    try:
        # valida datas cedo (para não entrar na tela de progresso com parâmetros ruins)
        _ = _days_total(start_date, end_date)
    except Exception as e:
        flash(f"Erro ao gerar relatório: {e}", "error")
        return redirect(url_for("admin.dds_reports", start_date=start_date, end_date=end_date, type=rtype))

    # Em vez de gerar no POST (bloqueia e pode estourar timeout),
    # redireciona para uma tela com SSE (progresso em tempo real).
    return redirect(url_for(
        "admin.dds_reports_progress",
        start_date=start_date,
        end_date=end_date,
        type=rtype,
        force=("1" if force else "0"),
    ))


@admin_bp.get("/dds-reports/progress")
@login_required
def dds_reports_progress():
    """Página que mostra progresso via SSE e redireciona ao final."""
    today = date.today()
    start_default = today.replace(day=1).strftime("%Y-%m-%d")
    end_default = today.strftime("%Y-%m-%d")

    start_date = (request.args.get("start_date") or start_default).strip()
    end_date = (request.args.get("end_date") or end_default).strip()
    rtype = (request.args.get("type") or "fotos").strip().lower()
    force = (request.args.get("force") or "0").strip().lower() in ("1", "true", "yes", "on")

    # Presença: não gera PDF — abre o painel (matriz Equipe × Dia)
    if rtype == "presenca":
        return redirect(url_for("admin.dds_presenca", start_date=start_date, end_date=end_date))


    try:
        total_days = _days_total(start_date, end_date)
    except Exception as e:
        flash(f"Datas inválidas: {e}", "error")
        return redirect(url_for("admin.dds_reports", start_date=start_date, end_date=end_date, type=rtype))

    return render_template(
        "dds_reports_progress.html",
        start_date=start_date,
        end_date=end_date,
        rtype=rtype,
        force=force,
        total_days=total_days,
    )


@admin_bp.get("/dds-reports/generate/stream")
@login_required
def dds_reports_generate_stream():
    """
    SSE stream de progresso:
      - emite progress {message, processed, total, percent, day?}
      - emite done {key, show_url}
      - emite error {message}
    """
    if (build_or_get_report_photos is None) and (build_or_get_report_detalhado is None) and (build_or_get_report_ranking is None):

        return Response(
            _sse("error", {"message": "Módulo de relatórios não carregou (dependências ausentes)."}),
            headers={"Content-Type": "text/event-stream"},
        )

    start_date = (request.args.get("start_date") or "").strip()
    end_date = (request.args.get("end_date") or "").strip()
    rtype = (request.args.get("type") or "fotos").strip().lower()
    force = (request.args.get("force") or "0").strip().lower() in ("1", "true", "yes", "on")

    # Presença: não gera PDF — abre o painel (matriz Equipe × Dia)
    if rtype == "presenca":
        show_url = url_for("admin.dds_presenca", start_date=start_date, end_date=end_date)
        return Response(
            _sse("done", {"key": "", "show_url": show_url}),
            headers={"Content-Type": "text/event-stream"},
        )


    reports_bucket = (current_app.config.get("REPORTS_BUCKET_NAME") or "").strip() or (current_app.config.get("BUCKET_NAME") or "").strip()
    cache_prefix = (current_app.config.get("REPORTS_CACHE_PREFIX") or "").strip()
    tz_name = (current_app.config.get("TIMEZONE_NAME") or "America/Sao_Paulo").strip()

    try:
        total_days = _days_total(start_date, end_date)
    except Exception as e:
        return Response(
            _sse("error", {"message": f"Datas inválidas: {e}"}),
            headers={"Content-Type": "text/event-stream"},
        )

    q: "queue.SimpleQueue[Dict[str, Any]]" = queue.SimpleQueue()
    done_flag = threading.Event()
    result_holder: Dict[str, Any] = {"result": None, "error": None}

    def on_progress(payload: Dict[str, Any]) -> None:
        # payload esperado: {message, processed, total, day?}
        q.put({"type": "progress", "payload": payload})

    def worker():
        try:
            builders = {
                "fotos": build_or_get_report_photos,
                "detalhado": build_or_get_report_detalhado,
                "ranking": build_or_get_report_ranking,
            }
            fn = builders.get(rtype)
            if fn is None:
                raise ValueError(f"Tipo de relatório inválido ou não habilitado: {rtype}")

            kwargs = dict(
                start_date=start_date,
                end_date=end_date,
                tz_name=tz_name,
                bucket_name=reports_bucket,
                cache_prefix=cache_prefix,
                force=force,
            )

            # passa callback só se a engine suportar (evita quebrar versões antigas)
            try:
                sig = inspect.signature(fn)

                if "on_progress" in sig.parameters:
                    kwargs["on_progress"] = on_progress
            except Exception:
                pass

            result = fn(**kwargs)
            result_holder["result"] = result
        except Exception as e:
            result_holder["error"] = str(e)
        finally:
            done_flag.set()

    threading.Thread(target=worker, daemon=True).start()

    @stream_with_context
    def gen():
        # "comentário" SSE para acordar proxies
        yield ": init\n\n"
        yield _sse("progress", {
            "message": "Iniciando geração do relatório...",
            "processed": 0,
            "total": total_days,
            "percent": 0,
        })

        last_keepalive = time.monotonic()

        while not done_flag.is_set():
            # consome eventos do worker
            try:
                item = q.get_nowait()
                if item.get("type") == "progress":
                    p = item.get("payload") or {}
                    processed = int(p.get("processed") or 0)
                    total = int(p.get("total") or total_days)
                    percent = int((processed / total) * 100) if total > 0 else 0
                    out = dict(p)
                    out.setdefault("total", total)
                    out.setdefault("processed", processed)
                    out["percent"] = max(0, min(100, percent))
                    yield _sse("progress", out)
            except Exception:
                pass

            # keepalive a cada ~10s (evita “travado” visual e alguns buffers)
            now = time.monotonic()
            if now - last_keepalive >= 10.0:
                yield ": keepalive\n\n"
                last_keepalive = now

            time.sleep(0.15)

        # finalização
        if result_holder["error"]:
            yield _sse("error", {"message": result_holder["error"]})
            return

        result = result_holder["result"]
        key = _rget(result, "key") or ""
        if not key:
            yield _sse("error", {"message": "Relatório concluído, mas não foi possível determinar o 'key'."})
            return

        show_url = url_for("admin.dds_reports_show", key=key)
        yield _sse("done", {"key": key, "show_url": show_url})

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return Response(gen(), headers=headers)


@admin_bp.get("/dds-reports/show/<key>")
@login_required
def dds_reports_show(key: str):
    reports_bucket = (current_app.config.get("REPORTS_BUCKET_NAME") or "").strip() or (current_app.config.get("BUCKET_NAME") or "").strip()
    cache_prefix = (current_app.config.get("REPORTS_CACHE_PREFIX") or "").strip()

    # lê meta se existir
    meta = {}
    try:
        if materialize_report_to_tmp is not None:
            meta_rel = f"final/{key}.meta.json"
            meta_path = materialize_report_to_tmp(bucket_name=reports_bucket, cache_prefix=cache_prefix, rel_path=meta_rel)
            if meta_path.exists():
                import json as _json
                meta = _json.loads(meta_path.read_text("utf-8"))
    except Exception:
        meta = {}

    
    # Signed URLs (preview/download) direto do GCS — evita servir PDF grande pelo Cloud Run
    try:
        minutes = int(os.getenv("DDS_REPORTS_SIGNED_URL_MINUTES", "60"))
    except Exception:
        minutes = 60

    try:
        rel_pdf = f"final/{key}.pdf"
        obj_pdf = _cache_obj_name(cache_prefix, rel_pdf)
        fname = f"{key}.pdf"
        view_url = _sign_get_url(
            bucket_name=reports_bucket,
            object_name=obj_pdf,
            minutes=minutes,
            disposition="inline",
            filename=fname,
            response_type="application/pdf",
        )
        dl_url = _sign_get_url(
            bucket_name=reports_bucket,
            object_name=obj_pdf,
            minutes=minutes,
            disposition="attachment",
            filename=fname,
            response_type="application/pdf",
        )
        if view_url:
            meta["signed_url"] = view_url
        if dl_url:
            meta["signed_url_download"] = dl_url
        meta["signed_url_expires_minutes"] = minutes
    except Exception:
        pass

    return render_template(
        "dds_report_show.html",
        key=key,
        meta=meta,
    )


def _send_cached_pdf(*, key: str, as_attachment: bool) -> Any:
    reports_bucket = (current_app.config.get("REPORTS_BUCKET_NAME") or "").strip() or (current_app.config.get("BUCKET_NAME") or "").strip()
    cache_prefix = (current_app.config.get("REPORTS_CACHE_PREFIX") or "").strip()
    if not reports_bucket:
        abort(500, "Bucket não configurado")


    rel = f"final/{key}.pdf"
    try:
        if materialize_report_to_tmp is not None:
            local_path = materialize_report_to_tmp(bucket_name=reports_bucket, cache_prefix=cache_prefix, rel_path=rel)
        else:
            # fallback robusto
            local_path = _materialize_gcs_to_tmp(bucket_name=reports_bucket, cache_prefix=cache_prefix, rel_path=rel)
    except Exception as e:
        abort(404, f"Relatório não encontrado: {e}")

    if not local_path.exists() or local_path.stat().st_size <= 0:
        abort(404, "Relatório vazio ou não encontrado")

    fname = f"{key}.pdf"
    return send_file(
        str(local_path),
        mimetype="application/pdf",
        as_attachment=as_attachment,
        download_name=fname,
        conditional=True,
        max_age=0,
    )


@admin_bp.get("/dds-reports/view/<key>")
@login_required
def dds_reports_view(key: str):
    return _send_cached_pdf(key=key, as_attachment=False)


@admin_bp.get("/dds-reports/download/<key>")
@login_required
def dds_reports_download(key: str):
    return _send_cached_pdf(key=key, as_attachment=True)


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


@admin_bp.get("/explorer/slides")
@login_required
def explorer_slides():
    """Retorna lista de URLs assinadas para os slides de uma pasta."""
    folder_id = (request.args.get("folderId") or "").strip()
    if not folder_id:
        return jsonify({"ok": False, "error": "folderId é obrigatório"}), 400

    bucket_name = current_app.config.get("BUCKET_NAME")
    base_prefix = current_app.config.get("BASE_PREFIX")
    if not bucket_name:
        return jsonify({"ok": False, "error": "Bucket não configurado"}), 500

    prefix = f"{base_prefix}/{folder_id}/".replace("//", "/")
    
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=prefix))
    
    # Filtra slides
    slide_regex = re.compile(r"(?i)slide\s*(\d+)\.(jpg|jpeg|png)")
    slides = []
    
    for blob in blobs:
        filename = blob.name.split("/")[-1]
        match = slide_regex.search(filename)
        if match:
            idx = int(match.group(1))
            url = _sign_get_url(
                bucket_name=bucket_name,
                object_name=blob.name,
                minutes=20,
                response_type="image/jpeg"
            )
            slides.append({"index": idx, "url": url})
    
    # Ordena por índice
    slides.sort(key=lambda x: x["index"])
    
    return jsonify({"ok": True, "slides": slides})



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
    Encaminha a exclusão de treinamentos e trata o redirecionamento se for form.
    """
    from flask import flash, redirect, url_for
    
    # Executa a exclusão (que retorna um JSON por padrão)
    resp = handle_training_delete_request()
    
    # Se for uma requisição de formulário, queremos redirecionar com flash
    if request.form:
        result_json = resp.get_json() if hasattr(resp, "get_json") else {}
        if result_json.get("ok"):
            # Extrai o nome amigável do folderId (YYYY-MM-DD - NOME)
            folder_id = request.form.get("folderId", "")
            training_name = folder_id[13:] if len(folder_id) > 13 else folder_id
            
            # Pega contagem de arquivos deletados do objeto 'result' interno
            res_data = result_json.get("result") or {}
            deleted_count = res_data.get("objectsDeleted", 0)
            
            flash(f"Treinamento '{training_name}' excluído com sucesso. {deleted_count} arquivos foram apagados do servidor.", "success")
        else:
            flash(f"Erro ao excluir: {result_json.get('error')}", "error")
            
        target = request.form.get("redirect") or "dashboard"
        if target == "explorer":
            return redirect(url_for("admin.explorer"))
        return redirect(url_for("admin.dashboard"))
    
    return resp


@admin_bp.post("/maintenance/rebuild-index")
@login_required
def maintenance_rebuild_index():
    """
    Rota de manutenção para limpar e reconstruir o DDSv2/lista.json.
    Pode ser chamada pelo Cloud Scheduler para automação.
    """
    from training_management.indexing import rebuild_lista_json

    bucket = current_app.config.get("BUCKET_NAME")
    base_prefix = current_app.config.get("BASE_PREFIX")
    tz = (current_app.config.get("TIMEZONE_NAME") or "America/Sao_Paulo").strip()

    if not bucket:
        return jsonify({"ok": False, "error": "DDS_BUCKET_NAME não configurado."}), 500

    try:
        result = rebuild_lista_json(
            bucket_name=bucket,
            base_prefix=base_prefix,
            timezone_name=tz
        )
        if result.get("ok"):
            current_app.logger.info(f"Índice reconstruído com sucesso: {result.get('details')}")
        return jsonify(result)
    except Exception as e:
        current_app.logger.exception("Erro crítico ao reconstruir índice: %s", e)
        return jsonify({"ok": False, "error": f"Erro interno: {str(e)}"}), 500