# Finalidade: concentrar o roteamento principal da API.
from fastapi import APIRouter

from app.api.routes.imports import router as imports_router
from app.api.routes.reports import router as reports_router
from app.api.routes.requests import router as requests_router
from app.api.routes.system import router as system_router

api_router = APIRouter(prefix="/api")
api_router.include_router(imports_router)
api_router.include_router(requests_router)
api_router.include_router(reports_router)
api_router.include_router(system_router)
