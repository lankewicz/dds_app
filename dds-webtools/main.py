import os
import sys
import json
import secrets
import uuid

base_dir = os.path.dirname(os.path.abspath(__file__))


def _is_sensitive_env_name(name: str) -> bool:
    upper_name = name.upper()
    return any(
        marker in upper_name
        for marker in ("PASSWORD", "SENHA", "SECRET", "KEY", "TOKEN", "CERTIFICATE")
    )

# Permitir imports locais dentro de monitor, admin e vexpenses
sys.path.insert(0, os.path.join(base_dir, "monitor"))
sys.path.insert(0, os.path.join(base_dir, "admin"))
sys.path.insert(0, os.path.join(base_dir, "vexpenses"))
sys.path.insert(0, os.path.join(base_dir, "token_server"))
sys.path.insert(0, os.path.join(base_dir, "boletim_x_ponto"))
sys.path.insert(0, os.path.join(base_dir, "controle_projetos"))

# Configuração de Credenciais: Local (arquivo) vs Cloud Run (ADC)
local_key = r"d:\programas\DDS\firebase_config.json"
if os.path.exists(local_key):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_key
    print(f"DEBUG: Usando credenciais locais de {local_key}")
else:
    print("DEBUG: Arquivo de chave local não encontrado. Assumindo ambiente Cloud Run (ADC).")

# Carrega env.yaml para desenvolvimento local automaticamente
env_yaml_path = os.path.join(base_dir, "env.yaml")
if os.path.exists(env_yaml_path):
    try:
        with open(env_yaml_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k not in os.environ:
                        os.environ[k] = v
                        print_val = "***" if _is_sensitive_env_name(k) else v
                        print(f"DEBUG Local: {k}={print_val}")
    except Exception as e:
        print(f"Erro ao carregar env.yaml local: {e}")

# Carrega arquivo .env local se existir (ignorado pelo deploy e git)
env_path = os.path.join(base_dir, ".env")
if os.path.exists(env_path):
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
        print("DEBUG Local: Carregou arquivo .env local")
        # Mostra as chaves carregadas do .env no log de depuração
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k = line.split("=", 1)[0].strip()
                    print_val = "***" if _is_sensitive_env_name(k) else os.environ.get(k)
                    print(f"DEBUG Local (.env): {k}={print_val}")
    except Exception as e:
        print(f"Erro ao carregar .env local: {e}")



from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.wsgi import WSGIMiddleware

# Monitor imports
from monitor.routes.monitor_routes import router as monitor_router
from monitor.routes.team_form_routes import router as team_form_router
from produtividade.routes.producao_import_routes import router as producao_import_router
from monitor.routes.messaging_routes import router as messaging_router
from monitor.services.turnos_service import APP_TITLE

# Admin import
from admin.web_app import app as flask_app

# VExpenses import
from vexpenses.app.main import app as vexpenses_app

# Token Server import
from token_server.routes import router as token_router

# Produtividade import
from produtividade.routes.prod_routes import router as produtividade_router

# Boletim x Ponto import
from boletim_x_ponto.routes.boletim_routes import router as boletim_router
from boletim_x_ponto.routes.rotalog_routes import router as rotalog_router

# Controle de Projetos import
from controle_projetos.routes.projeto_routes import router as projeto_router

listener_manager = None

rotalog_scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global listener_manager, rotalog_scheduler
    try:
        from monitor.services.turnos_service import FirestoreListenerManager
        listener_manager = FirestoreListenerManager()
        listener_manager.start()
    except Exception as e:
        print(f"Error starting background listener: {e}")

    rotalog_execution_mode = os.getenv("ROTALOG_EXECUTION_MODE", "embedded").strip().lower()
    rotalog_enabled = (
        rotalog_execution_mode == "embedded"
        and os.getenv("ROTALOG_SCHEDULER_ENABLED", "true").strip().lower() in {
            "1", "true", "yes", "on"
        }
    )
    if rotalog_enabled:
        try:
            from boletim_x_ponto.services.rotalog_sync_task import RotalogBackgroundScheduler
            interval_seconds = max(60, int(os.getenv("ROTALOG_SYNC_INTERVAL_SECONDS", "590")))
            rotalog_scheduler = RotalogBackgroundScheduler(interval_seconds=interval_seconds)
            rotalog_scheduler.start()
        except Exception as e:
            print(f"Error starting Rotalog background scheduler: {e}")

    yield

    if listener_manager:
        try:
            listener_manager.stop()
        except Exception as e:
            print(f"Error stopping background listener: {e}")

    if rotalog_scheduler:
        try:
            rotalog_scheduler.stop()
        except Exception as e:
            print(f"Error stopping Rotalog background scheduler: {e}")

class CacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        # JS e CSS são versionados por parâmetro, então podem ter cache longo
        if path.endswith((".js", ".css")):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            # Imagens, favicons, etc. têm cache de 1 dia para evitar retenção de updates
            response.headers["Cache-Control"] = "public, max-age=86400"
        return response

app = FastAPI(title=APP_TITLE, lifespan=lifespan)

from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Static files for Monitor
app.mount("/static", CacheStaticFiles(directory=os.path.join(base_dir, "monitor", "static")), name="static_monitor")
# Static files for Controle de Projetos
app.mount("/controle-projetos/static", CacheStaticFiles(directory=os.path.join(base_dir, "controle_projetos", "static")), name="static_controle_projetos")

# Modifica o Flask app para não usar prefixo se estivermos montando em /admin
# O Flask app_bp já tem url_prefix='/admin', então se montarmos o WSGI no '/', ele pega '/admin'
app.mount("/admin", WSGIMiddleware(flask_app))

# Monta o app FastAPI do VExpenses
app.mount("/vexpenses", vexpenses_app)

templates = Jinja2Templates(directory=os.path.join(base_dir, "templates"))

def format_number(value):
    try:
        if value is None: return "0,00"
        formatted = "{:,.2f}".format(float(value))
        return formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return value

templates.env.filters['format_number'] = format_number

from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from portal_auth import (
    PORTAL_AREAS,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    InvalidSessionError,
    UnauthorizedUserError,
    authenticate_portal_request,
    authorize_mobile_team,
    cookie_is_secure,
    create_session_cookie,
    has_permission,
    has_write_permission,
    is_root_email,
    required_permission_for_path,
    verify_firebase_id_token,
)

class LoginPayload(BaseModel):
    id_token: str
    csrf_token: str


class AccessUpdatePayload(BaseModel):
    active: bool
    role: str
    permissions: list[str] = Field(default_factory=list)
    write_permissions: list[str] = Field(default_factory=list)
    approved: bool = False


class CreateAccessUserPayload(BaseModel):
    name: str
    email: str
    password: str


def _firebase_web_api_key() -> str:
    configured = os.getenv("FIREBASE_WEB_API_KEY", "").strip()
    if configured:
        return configured

    # Conveniência exclusiva do desenvolvimento Android/local. Em produção,
    # configure FIREBASE_WEB_API_KEY no ambiente do Cloud Run.
    google_services_path = os.path.join(os.path.dirname(base_dir), "google-services.json")
    try:
        with open(google_services_path, "r", encoding="utf-8") as config_file:
            config = json.load(config_file)
        for client in config.get("client", []):
            package_name = (
                client.get("client_info", {})
                .get("android_client_info", {})
                .get("package_name")
            )
            if package_name == "com.chicoeletro.dds.app":
                return client["api_key"][0]["current_key"]
    except (OSError, KeyError, IndexError, TypeError, ValueError):
        pass
    return ""


def _is_public_path(path: str) -> bool:
    exact_paths = {
        "/login", "/api/login", "/request-access", "/api/request-access", "/favicon.ico"
    }
    public_prefixes = (
        "/static/",
        "/controle-projetos/static/",
    )
    return path in exact_paths or path.startswith(public_prefixes)


_SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS"}

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/rotalog/mobile/"):
        authorization = request.headers.get("authorization", "")
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        try:
            claims = verify_firebase_id_token(token)
        except InvalidSessionError:
            return JSONResponse(status_code=401, content={"ok": False, "message": "Token Firebase inválido ou ausente."})
        team_key = request.url.path.split("/api/rotalog/mobile/", 1)[1].split("/", 1)[0]
        from monitor.services.firestore_client import db
        try:
            if not authorize_mobile_team(claims, team_key, db):
                return JSONResponse(status_code=403, content={"ok": False, "message": "Este dispositivo não está vinculado à equipe solicitada."})
        except Exception as auth_err:
            print(f"Erro na verificação de autorização de equipe {team_key}: {auth_err}")
        if request.method not in _SAFE_HTTP_METHODS:
            return JSONResponse(status_code=405, content={"ok": False, "message": "Método não permitido."})
        request.state.mobile_user = claims
        return await call_next(request)

    portal_user = None
    required_permission = None
    if not _is_public_path(request.url.path):
        from monitor.services.firestore_client import db
        try:
            portal_user = authenticate_portal_request(
                request.cookies.get(SESSION_COOKIE_NAME, ""), db
            )
        except (InvalidSessionError, UnauthorizedUserError):
            response = RedirectResponse(url="/login", status_code=303)
            response.delete_cookie(SESSION_COOKIE_NAME, path="/")
            return response

        request.state.portal_user = portal_user
        required_permission = required_permission_for_path(request.url.path)
        if not has_permission(portal_user, required_permission):
            wants_json = (
                "/api/" in request.url.path
                or request.url.path.startswith("/api/")
                or "application/json" in request.headers.get("accept", "").lower()
            )
            if wants_json:
                return JSONResponse(
                    status_code=403,
                    content={
                        "ok": False,
                        "message": "Você não possui permissão para esta área.",
                        "required_permission": required_permission,
                    },
                )
            return RedirectResponse(
                url=f"/forbidden?permission={required_permission}", status_code=303
            )

        if (
            required_permission is not None
            and request.method not in _SAFE_HTTP_METHODS
            and not has_write_permission(portal_user, required_permission)
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "ok": False,
                    "message": "Seu acesso a esta área é somente leitura.",
                    "required_permission": required_permission,
                },
            )

        # O app Flask montado via WSGI não enxerga request.state. O cabeçalho é
        # gerado apenas depois da validação da session cookie neste middleware.
        request.scope["headers"] = [
            (name, value)
            for name, value in request.scope["headers"]
            if name not in {
                b"x-portal-user",
                b"x-portal-role",
                b"x-portal-root",
                b"x-portal-permissions",
                b"x-portal-write-permissions",
            }
        ] + [
            (b"x-portal-user", portal_user["email"].encode("utf-8")),
            (b"x-portal-role", portal_user["role"].encode("utf-8")),
            (b"x-portal-root", str(portal_user["is_root"]).lower().encode("ascii")),
            (
                b"x-portal-permissions",
                ",".join(portal_user["permissions"]).encode("utf-8"),
            ),
            (
                b"x-portal-write-permissions",
                ",".join(portal_user["write_permissions"]).encode("utf-8"),
            ),
        ]
    response = await call_next(request)

    if (
        portal_user
        and required_permission is not None
        and request.method not in _SAFE_HTTP_METHODS
    ):
        try:
            from google.cloud import firestore
            from monitor.services.firestore_client import db
            forwarded_for = request.headers.get("x-forwarded-for", "")
            client_ip = forwarded_for.split(",", 1)[0].strip() if forwarded_for else None
            if not client_ip and request.client:
                client_ip = request.client.host
            db.collection("portal_change_audit").document().set({
                "requestId": str(uuid.uuid4()),
                "actorEmail": portal_user["email"],
                "module": required_permission,
                "method": request.method,
                "path": request.url.path,
                "statusCode": response.status_code,
                "clientIp": client_ip,
                "createdAt": firestore.SERVER_TIMESTAMP,
            })
        except Exception as audit_error:
            print(f"Falha ao registrar auditoria da alteração: {audit_error}")

    return response

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    portal_user = request.state.portal_user
    user_email = portal_user["email"]
    revision = os.environ.get("K_REVISION", "local")
    if "-" in revision:
        parts = revision.split("-")
        if len(parts) >= 2: revision = "-".join(parts[-2:])
            
    return templates.TemplateResponse("landing.html", {
        "request": request, 
        "app_title": APP_TITLE,
        "revision": revision,
        "user_email": user_email,
        "portal_user": portal_user,
        "has_permission": lambda permission: has_permission(portal_user, permission),
    })


@app.get("/forbidden", response_class=HTMLResponse)
async def forbidden(request: Request):
    permission = request.query_params.get("permission", "")
    return templates.TemplateResponse("forbidden.html", {
        "request": request,
        "app_title": APP_TITLE,
        "permission_name": PORTAL_AREAS.get(permission, permission),
        "user_email": request.state.portal_user["email"],
    }, status_code=403)


@app.get("/request-access", response_class=HTMLResponse)
async def request_access(request: Request):
    csrf_token = secrets.token_urlsafe(32)
    response = templates.TemplateResponse("request_access.html", {
        "request": request,
        "app_title": APP_TITLE,
        "csrf_token": csrf_token,
    })
    response.set_cookie(
        key="request_access_csrf",
        value=csrf_token,
        max_age=900,
        httponly=True,
        secure=cookie_is_secure(),
        samesite="strict",
        path="/",
    )
    return response


@app.post("/api/request-access")
async def submit_access_request(payload: CreateAccessUserPayload, request: Request):
    csrf_cookie = request.cookies.get("request_access_csrf", "")
    csrf_header = request.headers.get("x-csrf-token", "")
    if not csrf_cookie or not secrets.compare_digest(csrf_cookie, csrf_header):
        return JSONResponse(
            status_code=403,
            content={"ok": False, "message": "Página expirada. Recarregue e tente novamente."},
        )

    name = " ".join(payload.name.strip().split())
    email = payload.email.strip().lower()
    if len(name) < 2 or "@" not in email:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "Informe nome e e-mail válidos."},
        )
    if len(payload.password) < 8:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "A senha deve ter pelo menos 8 caracteres."},
        )
    if is_root_email(email):
        return JSONResponse(
            status_code=403,
            content={"ok": False, "message": "Contas ROOT não podem ser criadas por solicitação pública."},
        )

    from firebase_admin import auth as firebase_auth
    from google.cloud import firestore
    from monitor.services.firestore_client import db
    from portal_auth import ensure_firebase_app

    ensure_firebase_app()
    try:
        auth_user = firebase_auth.create_user(
            email=email,
            password=payload.password,
            display_name=name,
            disabled=False,
        )
    except firebase_auth.EmailAlreadyExistsError:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "message": "Este e-mail já possui uma conta. Entre ou procure um administrador."},
        )
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "Não foi possível criar a conta com os dados informados."},
        )

    user_data = {
        "email": email,
        "name": name,
        "firebaseUid": auth_user.uid,
        "active": True,
        "role": "user",
        "permissions": ["monitor", "produtividade"],
        "writePermissions": [],
        "approvalStatus": "pending",
        "createdAt": firestore.SERVER_TIMESTAMP,
        "createdBy": email,
    }
    audit_entry = {
        "action": "self_request_created",
        "targetEmail": email,
        "actorEmail": email,
        "permissions": ["monitor", "produtividade"],
        "writePermissions": [],
        "approvalStatus": "pending",
        "createdAt": firestore.SERVER_TIMESTAMP,
    }
    try:
        batch = db.batch()
        batch.set(db.collection("dds_users").document(email), user_data)
        batch.set(db.collection("portal_access_audit").document(), audit_entry)
        batch.commit()
    except Exception:
        firebase_auth.delete_user(auth_user.uid)
        raise

    response = JSONResponse(content={
        "ok": True,
        "message": "Conta criada. Você já pode acessar Monitor de Turnos e Produtividade em modo de leitura.",
    })
    response.delete_cookie("request_access_csrf", path="/")
    return response


@app.get("/access-control", response_class=HTMLResponse)
async def access_control(request: Request):
    from monitor.services.firestore_client import db

    users = []
    for snapshot in db.collection("dds_users").stream():
        data = snapshot.to_dict() or {}
        raw_permissions = data.get("permissions") or []
        if isinstance(raw_permissions, dict):
            raw_permissions = [key for key, allowed in raw_permissions.items() if allowed]
        raw_write_permissions = data.get("writePermissions") or []
        if isinstance(raw_write_permissions, dict):
            raw_write_permissions = [key for key, allowed in raw_write_permissions.items() if allowed]
        users.append({
            "email": str(data.get("email") or snapshot.id).strip().lower(),
            "name": str(data.get("name") or "").strip(),
            "active": bool(data.get("active")),
            "role": str(data.get("role") or "user").strip().lower(),
            "permissions": set(raw_permissions if isinstance(raw_permissions, list) else []),
            "write_permissions": set(raw_write_permissions if isinstance(raw_write_permissions, list) else []),
            "approved": str(data.get("approvalStatus") or "approved").lower() == "approved",
            "is_root": is_root_email(str(data.get("email") or snapshot.id)),
        })
    users.sort(key=lambda item: item["email"])

    csrf_token = secrets.token_urlsafe(32)
    response = templates.TemplateResponse("access_control.html", {
        "request": request,
        "app_title": APP_TITLE,
        "users": users,
        "areas": PORTAL_AREAS,
        "csrf_token": csrf_token,
        "current_email": request.state.portal_user["email"],
        "current_is_root": request.state.portal_user["is_root"],
    })
    response.set_cookie(
        key="access_csrf",
        value=csrf_token,
        max_age=1800,
        httponly=True,
        secure=cookie_is_secure(),
        samesite="strict",
        path="/",
    )
    return response


@app.put("/api/access-control/users/{email}")
async def update_access_user(email: str, payload: AccessUpdatePayload, request: Request):
    csrf_cookie = request.cookies.get("access_csrf", "")
    csrf_header = request.headers.get("x-csrf-token", "")
    if not csrf_cookie or not secrets.compare_digest(csrf_cookie, csrf_header):
        return JSONResponse(
            status_code=403,
            content={"ok": False, "message": "Token de segurança inválido."},
        )

    normalized_email = email.strip().lower()
    role = payload.role.strip().lower()
    if "@" not in normalized_email or role not in {"admin", "user"}:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "Usuário ou papel inválido."},
        )

    permissions = sorted(set(payload.permissions))
    if any(permission not in PORTAL_AREAS or permission == "admin" for permission in permissions):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "Permissão desconhecida."},
        )
    write_permissions = sorted(set(payload.write_permissions))
    if any(permission not in permissions for permission in write_permissions):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "Gravação exige acesso de leitura ao mesmo módulo."},
        )

    current_email = request.state.portal_user["email"]
    current_is_root = request.state.portal_user["is_root"]
    target_is_root = is_root_email(normalized_email)
    if target_is_root and (not payload.active or role != "admin" or not payload.approved):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "Uma conta ROOT não pode ser desativada ou rebaixada."},
        )

    from google.cloud import firestore
    from monitor.services.firestore_client import db

    existing_snapshot = db.collection("dds_users").document(normalized_email).get()
    existing_data = existing_snapshot.to_dict() if existing_snapshot.exists else {}
    if not current_is_root:
        existing_active = bool(existing_data.get("active"))
        existing_role = str(existing_data.get("role") or "user").strip().lower()
        existing_approved = str(existing_data.get("approvalStatus") or "approved").lower() == "approved"
        if payload.active != existing_active or role != existing_role or payload.approved != existing_approved:
            return JSONResponse(
                status_code=403,
                content={"ok": False, "message": "Somente uma conta ROOT pode alterar status ou papel."},
            )

    user_update = {
        "email": normalized_email,
        "active": payload.active,
        "role": role,
        "permissions": permissions if role == "user" else [],
        "writePermissions": write_permissions if role == "user" else [],
        "approvalStatus": "approved" if payload.approved else "pending",
        "accessUpdatedAt": firestore.SERVER_TIMESTAMP,
        "accessUpdatedBy": current_email,
    }
    audit_entry = {
        "action": "update_access",
        "targetEmail": normalized_email,
        "actorEmail": current_email,
        "active": payload.active,
        "role": role,
        "permissions": permissions if role == "user" else [],
        "writePermissions": write_permissions if role == "user" else [],
        "approvalStatus": "approved" if payload.approved else "pending",
        "createdAt": firestore.SERVER_TIMESTAMP,
    }
    batch = db.batch()
    batch.set(db.collection("dds_users").document(normalized_email), user_update, merge=True)
    batch.set(db.collection("portal_access_audit").document(), audit_entry)
    batch.commit()
    return {"ok": True}


@app.post("/api/access-control/users")
async def create_access_user(payload: CreateAccessUserPayload, request: Request):
    csrf_cookie = request.cookies.get("access_csrf", "")
    csrf_header = request.headers.get("x-csrf-token", "")
    if not csrf_cookie or not secrets.compare_digest(csrf_cookie, csrf_header):
        return JSONResponse(
            status_code=403,
            content={"ok": False, "message": "Token de segurança inválido."},
        )

    name = " ".join(payload.name.strip().split())
    email = payload.email.strip().lower()
    if len(name) < 2 or "@" not in email:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "Informe nome e e-mail válidos."},
        )
    if len(payload.password) < 8:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "A senha inicial deve ter pelo menos 8 caracteres."},
        )

    actor_email = request.state.portal_user["email"]
    actor_is_root = request.state.portal_user["is_root"]
    if is_root_email(email) and not actor_is_root:
        return JSONResponse(
            status_code=403,
            content={"ok": False, "message": "Somente um ROOT pode criar outra conta ROOT."},
        )

    from firebase_admin import auth as firebase_auth
    from google.cloud import firestore
    from monitor.services.firestore_client import db
    from portal_auth import ensure_firebase_app

    ensure_firebase_app()
    try:
        auth_user = firebase_auth.create_user(
            email=email,
            password=payload.password,
            display_name=name,
            disabled=False,
        )
    except firebase_auth.EmailAlreadyExistsError:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "message": "Este e-mail já existe no Firebase Authentication."},
        )
    except ValueError as error:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": f"Não foi possível criar a conta: {error}"},
        )

    user_data = {
        "email": email,
        "name": name,
        "firebaseUid": auth_user.uid,
        "active": True,
        "role": "user",
        "permissions": ["monitor", "produtividade"],
        "writePermissions": [],
        "approvalStatus": "pending",
        "createdAt": firestore.SERVER_TIMESTAMP,
        "createdBy": actor_email,
    }
    audit_entry = {
        "action": "create_inactive_user",
        "targetEmail": email,
        "actorEmail": actor_email,
        "active": True,
        "role": "user",
        "permissions": ["monitor", "produtividade"],
        "writePermissions": [],
        "approvalStatus": "pending",
        "createdAt": firestore.SERVER_TIMESTAMP,
    }
    try:
        batch = db.batch()
        batch.set(db.collection("dds_users").document(email), user_data)
        batch.set(db.collection("portal_access_audit").document(), audit_entry)
        batch.commit()
    except Exception:
        # Evita deixar uma conta Firebase órfã se a autorização não puder ser registrada.
        firebase_auth.delete_user(auth_user.uid)
        raise

    return {"ok": True, "email": email, "active": True, "approval_status": "pending"}

@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    csrf_token = secrets.token_urlsafe(32)
    firebase_api_key = _firebase_web_api_key()
    response = templates.TemplateResponse("login.html", {
        "request": request,
        "app_title": APP_TITLE,
        "csrf_token": csrf_token,
        "firebase_api_key": firebase_api_key,
    })
    response.set_cookie(
        key="portal_csrf",
        value=csrf_token,
        max_age=600,
        httponly=True,
        secure=cookie_is_secure(),
        samesite="strict",
        path="/",
    )
    return response

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(
        os.path.join(base_dir, "monitor", "static", "favicon-portal.svg"),
        media_type="image/svg+xml"
    )

@app.post("/api/login")
async def api_login(payload: LoginPayload, request: Request):
    try:
        csrf_cookie = request.cookies.get("portal_csrf", "")
        if not csrf_cookie or not secrets.compare_digest(csrf_cookie, payload.csrf_token):
            return JSONResponse(
                content={"ok": False, "message": "Sessão de login expirada. Recarregue a página."},
                status_code=403,
            )

        session_cookie = create_session_cookie(payload.id_token)
        from firebase_admin import auth as firebase_auth
        claims = firebase_auth.verify_id_token(payload.id_token, check_revoked=True)
        from monitor.services.firestore_client import db
        from portal_auth import authorize_portal_user
        authorize_portal_user(claims, db)

        response = JSONResponse(content={"ok": True})
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_cookie,
            max_age=SESSION_MAX_AGE_SECONDS,
            httponly=True,
            secure=cookie_is_secure(),
            samesite="lax",
            path="/",
        )
        response.delete_cookie("portal_csrf", path="/")
        return response
    except (InvalidSessionError, UnauthorizedUserError) as e:
        return JSONResponse(content={"ok": False, "message": str(e)}, status_code=401)
    except Exception as e:
        print(f"Erro no login: {e}")
        return JSONResponse(content={"ok": False, "message": "Erro interno no servidor"}, status_code=500)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response

# O Monitor vai ficar em /monitor, mas as APIs podem continuar em /api
# No monitor_routes, os endpoints de HTML eram /, /inativas, /lixeira
app.include_router(monitor_router)
app.include_router(team_form_router)
app.include_router(producao_import_router)
app.include_router(messaging_router)
app.include_router(token_router)
app.include_router(produtividade_router)
app.include_router(boletim_router)
app.include_router(rotalog_router)
app.include_router(projeto_router)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8081))
    uvicorn.run(app, host="0.0.0.0", port=port)
