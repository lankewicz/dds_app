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

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    revision = os.environ.get("K_REVISION", "local")
    if "-" in revision:
        parts = revision.split("-")
        if len(parts) >= 2:
            revision = "-".join(parts[-2:])
            
    return templates.TemplateResponse("landing.html", {
        "request": request, 
        "app_title": APP_TITLE,
        "revision": revision
    })

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
