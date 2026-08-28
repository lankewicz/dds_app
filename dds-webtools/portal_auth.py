"""Firebase Authentication helpers for the DDS web portal."""

from __future__ import annotations

import os
import threading
import time
from datetime import timedelta
from typing import Any, Mapping

import firebase_admin
from firebase_admin import auth as firebase_auth


SESSION_COOKIE_NAME = "__session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 5

PORTAL_AREAS = {
    "admin": "Painel Administrativo",
    "monitor": "Monitor de Turnos",
    "vexpenses": "VExpenses",
    "produtividade": "Monitor de Produtividade",
    "boletim_x_ponto": "Boletim x Ponto",
    "controle_projetos": "Controle de Projetos",
}

DEFAULT_ROOT_EMAILS = {
    "valdinei.pco@gmail.com",
    "valdinei@chicoeletro.com.br",
}

_PATH_PERMISSIONS = (
    ("/access-control", "admin"),
    ("/api/access-control", "admin"),
    ("/admin", "admin"),
    ("/vexpenses", "vexpenses"),
    ("/produtividade", "produtividade"),
    ("/boletim-x-ponto", "boletim_x_ponto"),
    ("/api/rotalog", "boletim_x_ponto"),
    ("/controle-projetos", "controle_projetos"),
    ("/monitor", "monitor"),
    ("/api/config", "monitor"),
    ("/api/crash-reports", "monitor"),
    ("/api/turnos", "monitor"),
    ("/api/activity-feed", "monitor"),
    ("/api/internal/sync-realtime", "monitor"),
    ("/api/requests", "monitor"),
    ("/api/teams", "monitor"),
    ("/api/team-form", "monitor"),
    ("/api/mensagens", "monitor"),
    ("/api/producao", "monitor"),
)


class PortalAuthError(Exception):
    """Base error for portal authentication failures."""


class InvalidSessionError(PortalAuthError):
    """The Firebase session cookie is absent, invalid, expired or revoked."""


class UnauthorizedUserError(PortalAuthError):
    """The authenticated identity is not allowed to use the portal."""


def root_emails() -> set[str]:
    configured = os.getenv("PORTAL_ROOT_EMAILS", "")
    extra = {item.strip().lower() for item in configured.split(",") if item.strip()}
    return DEFAULT_ROOT_EMAILS | extra


def is_root_email(email: str) -> bool:
    return email.strip().lower() in root_emails()


def ensure_firebase_app() -> None:
    if not firebase_admin._apps:
        project_id = (
            os.getenv("GOOGLE_CLOUD_PROJECT")
            or os.getenv("GCP_PROJECT")
            or "dds-treinamentos"
        )
        options = {"projectId": project_id}
        signing_sa = os.getenv("SIGNING_SERVICE_ACCOUNT")
        if signing_sa:
            options["serviceAccountId"] = signing_sa
        firebase_admin.initialize_app(options=options)


def create_session_cookie(id_token: str) -> str:
    if not id_token or not id_token.strip():
        raise InvalidSessionError("ID token ausente.")
    ensure_firebase_app()
    try:
        return firebase_auth.create_session_cookie(
            id_token.strip(),
            expires_in=timedelta(seconds=SESSION_MAX_AGE_SECONDS),
        )
    except Exception as exc:
        print(f"Erro ao criar session cookie no Firebase: {type(exc).__name__}: {exc}")
        raise InvalidSessionError("ID token inválido.") from exc


def verify_session_cookie(session_cookie: str) -> Mapping[str, Any]:
    if not session_cookie:
        raise InvalidSessionError("Sessão ausente.")
    ensure_firebase_app()
    try:
        return firebase_auth.verify_session_cookie(session_cookie, check_revoked=True)
    except Exception as exc:
        raise InvalidSessionError("Sessão inválida ou expirada.") from exc


def verify_firebase_id_token(id_token: str) -> Mapping[str, Any]:
    if not id_token or not id_token.strip():
        raise InvalidSessionError("ID token ausente.")
    ensure_firebase_app()
    try:
        return firebase_auth.verify_id_token(id_token.strip(), check_revoked=False)
    except Exception as exc:
        raise InvalidSessionError("ID token inválido ou expirado.") from exc


_MOBILE_TEAM_CACHE: dict[tuple[str, str], tuple[bool, float]] = {}
_MOBILE_TEAM_CACHE_LOCK = threading.RLock()
_MOBILE_TEAM_CACHE_TTL = 3600


def authorize_mobile_team(claims: Mapping[str, Any], team_key: str, db: Any) -> bool:
    uid = str(claims.get("uid") or claims.get("sub") or "").strip()
    normalized = str(team_key or "").strip().upper()
    if not uid or not normalized:
        return False
    cache_key = (uid, normalized)
    now = time.monotonic()
    with _MOBILE_TEAM_CACHE_LOCK:
        cached = _MOBILE_TEAM_CACHE.get(cache_key)
        if cached and now - cached[1] < _MOBILE_TEAM_CACHE_TTL:
            return cached[0]
    snapshot = db.collection("dds_teams").document(normalized).get()
    data = snapshot.to_dict() if snapshot.exists else {}
    authorized = {str(value) for value in (data.get("authorizedAppUids") or [])}
    allowed = not authorized or uid in authorized or uid == str(data.get("updatedByUid") or "")
    with _MOBILE_TEAM_CACHE_LOCK:
        _MOBILE_TEAM_CACHE[cache_key] = (allowed, now)
    return allowed

def authorize_portal_user(claims: Mapping[str, Any], db: Any) -> dict[str, Any]:
    email = str(claims.get("email") or "").strip().lower()
    if not email:
        raise UnauthorizedUserError("A conta Firebase não possui e-mail.")

    if os.getenv("REQUIRE_VERIFIED_EMAIL", "false").lower() in {"1", "true", "yes"}:
        if not claims.get("email_verified"):
            raise UnauthorizedUserError("Confirme seu e-mail antes de acessar o portal.")

    user_doc = db.collection("dds_users").document(email).get()
    user_data = user_doc.to_dict() if user_doc.exists else {}
    is_root = is_root_email(email)
    if not is_root and (not user_data or not user_data.get("active")):
        raise UnauthorizedUserError("Usuário não autorizado ou inativo.")

    raw_permissions = user_data.get("permissions") or []
    if isinstance(raw_permissions, Mapping):
        raw_permissions = [key for key, allowed in raw_permissions.items() if allowed]
    if not isinstance(raw_permissions, (list, tuple, set)):
        raw_permissions = []
    permissions = sorted({
        str(item).strip()
        for item in raw_permissions
        if str(item).strip() in PORTAL_AREAS and str(item).strip() != "admin"
    })
    raw_write_permissions = user_data.get("writePermissions") or []
    if isinstance(raw_write_permissions, Mapping):
        raw_write_permissions = [
            key for key, allowed in raw_write_permissions.items() if allowed
        ]
    if not isinstance(raw_write_permissions, (list, tuple, set)):
        raw_write_permissions = []
    write_permissions = sorted({
        str(item).strip()
        for item in raw_write_permissions
        if str(item).strip() in permissions
    })

    return {
        "uid": str(claims.get("uid") or claims.get("sub") or ""),
        "email": email,
        "role": "root" if is_root else str(user_data.get("role") or "user").strip().lower(),
        "permissions": permissions,
        "write_permissions": write_permissions,
        "approval_status": str(user_data.get("approvalStatus") or "approved").lower(),
        "is_root": is_root,
    }


def authenticate_portal_request(session_cookie: str, db: Any) -> dict[str, Any]:
    return authorize_portal_user(verify_session_cookie(session_cookie), db)


def cookie_is_secure() -> bool:
    configured = os.getenv("PORTAL_COOKIE_SECURE")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes"}
    return bool(os.getenv("K_SERVICE"))


def has_permission(user: Mapping[str, Any], permission: str | None) -> bool:
    if permission is None:
        return True
    role = str(user.get("role") or "").lower()
    is_admin = role in {"admin", "root"}
    if permission == "admin":
        return is_admin
    if is_admin:
        return True
    return permission in set(user.get("permissions") or [])


def required_permission_for_path(path: str) -> str | None:
    normalized = path.rstrip("/") or "/"
    for prefix, permission in _PATH_PERMISSIONS:
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return permission
    return None


def has_write_permission(user: Mapping[str, Any], permission: str | None) -> bool:
    if permission is None:
        return True
    role = str(user.get("role") or "").lower()
    if role in {"admin", "root"}:
        return True
    return permission in set(user.get("write_permissions") or [])
