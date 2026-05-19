import os
import sys

base_dir = os.path.dirname(os.path.abspath(__file__))

# Permitir imports locais dentro de monitor, admin e vexpenses
sys.path.insert(0, os.path.join(base_dir, "monitor"))
sys.path.insert(0, os.path.join(base_dir, "admin"))
sys.path.insert(0, os.path.join(base_dir, "vexpenses"))
sys.path.insert(0, os.path.join(base_dir, "token_server"))

# Configuração de Credenciais: Local (arquivo) vs Cloud Run (ADC)
local_key = r"d:\programas\DDS\firebase_config.json"
if os.path.exists(local_key):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_key
    print(f"DEBUG: Usando credenciais locais de {local_key}")
else:
    print("DEBUG: Arquivo de chave local não encontrado. Assumindo ambiente Cloud Run (ADC).")

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

app = FastAPI(title=APP_TITLE)

listener_manager = None

@app.on_event("startup")
def startup_event():
    global listener_manager
    try:
        from monitor.services.turnos_service import FirestoreListenerManager
        listener_manager = FirestoreListenerManager()
        listener_manager.start()
    except Exception as e:
        print(f"Error starting background listener: {e}")

@app.on_event("shutdown")
def shutdown_event():
    global listener_manager
    if listener_manager:
        try:
            listener_manager.stop()
        except Exception as e:
            print(f"Error stopping background listener: {e}")

# Static files for Monitor
app.mount("/static", StaticFiles(directory=os.path.join(base_dir, "monitor", "static")), name="static_monitor")
# Static files for Admin (Flask handles its own static files inside WSGI, but if it fails we could mount them too)

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
from fastapi.responses import JSONResponse, RedirectResponse

class LoginPayload(BaseModel):
    email: str

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    public_paths = ["/login", "/api/login", "/static", "/favicon.ico"]
    if not any(request.url.path.startswith(p) for p in public_paths):
        user_email = request.cookies.get("user_email")
        if not user_email:
            return RedirectResponse(url="/login")
    return await call_next(request)

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user_email = request.cookies.get("user_email")
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

@app.post("/api/login")
async def api_login(payload: LoginPayload):
    try:
        email = payload.email.lower().strip()
        from monitor.services.firestore_client import db
        user_doc = db.collection("dds_users").document(email).get()
        
        if user_doc.exists and user_doc.to_dict().get("active"):
            response = JSONResponse(content={"ok": True})
            response.set_cookie(key="user_email", value=email, max_age=604800, httponly=True)
            return response
        
        return JSONResponse(content={"ok": False, "message": "E-mail não autorizado"}, status_code=401)
    except Exception as e:
        print(f"Erro no login: {e}")
        return JSONResponse(content={"ok": False, "message": "Erro interno no servidor"}, status_code=500)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("user_email")
    return response

# O Monitor vai ficar em /monitor, mas as APIs podem continuar em /api
# No monitor_routes, os endpoints de HTML eram /, /inativas, /lixeira
app.include_router(monitor_router)
app.include_router(team_form_router)
app.include_router(producao_import_router)
app.include_router(messaging_router)
app.include_router(token_router)
app.include_router(produtividade_router)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
