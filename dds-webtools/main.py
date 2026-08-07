import os
import sys

base_dir = os.path.dirname(os.path.abspath(__file__))

# Permitir imports locais dentro de monitor, admin e vexpenses
sys.path.insert(0, os.path.join(base_dir, "monitor"))
sys.path.insert(0, os.path.join(base_dir, "admin"))
sys.path.insert(0, os.path.join(base_dir, "vexpenses"))
sys.path.insert(0, os.path.join(base_dir, "token_server"))
sys.path.insert(0, os.path.join(base_dir, "boletim_x_ponto"))
sys.path.insert(0, os.path.join(base_dir, "controle_projetos"))
sys.path.insert(0, os.path.join(base_dir, "boletim_cidades"))

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
                        print_val = "***" if any(x in k.upper() for x in ["PASSWORD", "SECRET", "KEY", "TOKEN"]) else v
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
                    print_val = "***" if any(x in k.upper() for x in ["PASSWORD", "SECRET", "KEY", "TOKEN"]) else os.environ.get(k)
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

# Controle de Projetos import
from controle_projetos.routes.projeto_routes import router as projeto_router

# Boletim Cidades (Financeiro) import
from boletim_cidades.routes.cidades_routes import router as cidades_router

# NFS-e Manager import
from nfse.routes import router as nfse_router

listener_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global listener_manager
    try:
        from monitor.services.turnos_service import FirestoreListenerManager
        listener_manager = FirestoreListenerManager()
        listener_manager.start()
    except Exception as e:
        print(f"Error starting background listener: {e}")
    yield
    if listener_manager:
        try:
            listener_manager.stop()
        except Exception as e:
            print(f"Error stopping background listener: {e}")

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

from pydantic import BaseModel
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse

class LoginPayload(BaseModel):
    email: str

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    public_paths = [
        "/login",
        "/api/login",
        "/static",
        "/favicon.ico",
        "/controle-projetos/static",
        "/controle-projetos/revisar-mit",
        "/controle-projetos/api/mit-import",
        "/controle-projetos/estruturas",
        "/controle-projetos/api/estruturas",
        "/boletim-cidades",
        "/api/nfse"
    ]
    if not any(request.url.path.startswith(p) for p in public_paths):
        user_email = request.cookies.get("__session")
        if not user_email:
            return RedirectResponse(url="/login")
    return await call_next(request)

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user_email = request.cookies.get("__session")
    revision = os.environ.get("K_REVISION", "local")
    if "-" in revision:
        parts = revision.split("-")
        if len(parts) >= 2: revision = "-".join(parts[-2:])
            
    return templates.TemplateResponse("landing.html", {
        "request": request, 
        "app_title": APP_TITLE,
        "revision": revision,
        "user_email": user_email
    })

@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "app_title": APP_TITLE
    })

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(
        os.path.join(base_dir, "monitor", "static", "favicon-portal.svg"),
        media_type="image/svg+xml"
    )

@app.post("/api/login")
async def api_login(payload: LoginPayload):
    try:
        email = payload.email.lower().strip()
        from monitor.services.firestore_client import db
        user_doc = db.collection("dds_users").document(email).get()
        
        if user_doc.exists and user_doc.to_dict().get("active"):
            response = JSONResponse(content={"ok": True})
            response.set_cookie(key="__session", value=email, max_age=604800, httponly=True)
            return response
        
        return JSONResponse(content={"ok": False, "message": "E-mail não autorizado"}, status_code=401)
    except Exception as e:
        print(f"Erro no login: {e}")
        return JSONResponse(content={"ok": False, "message": "Erro interno no servidor"}, status_code=500)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("__session")
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
app.include_router(projeto_router)
app.include_router(cidades_router)
app.include_router(nfse_router)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8081))
    uvicorn.run(app, host="0.0.0.0", port=port)
