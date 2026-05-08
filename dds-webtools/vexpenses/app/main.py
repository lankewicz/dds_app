# Finalidade: ponto de entrada da aplicação FastAPI (Versão Firestore).
import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging, get_logger

logger = get_logger(__name__)

def create_application() -> FastAPI:
    # Inicializar logs
    setup_logging()
    
    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        version="0.1.0",
        description="API para importar planilhas de solicitações de saldo e gerar relatórios no Firestore.",
    )

    app.include_router(api_router)

    # Garantir que o diretório static existe
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_path = os.path.join(base_dir, "static")
    if not os.path.exists(static_path):
        os.makedirs(static_path)

    # Montar arquivos estáticos (CSS, JS, Imagens)
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    templates = Jinja2Templates(directory=static_path)

    @app.get("/health", tags=["health"])
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", tags=["gui"])
    def get_gui(request: Request):
        revision = os.environ.get("K_REVISION", settings.app_revision)
        if "-" in revision:
            parts = revision.split("-")
            if len(parts) >= 2:
                revision = "-".join(parts[-2:])
        
        return templates.TemplateResponse(
            request=request,
            name="index.html", 
            context={"revision": revision}
        )

    return app

app = create_application()
