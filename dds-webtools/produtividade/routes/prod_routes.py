import os
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Configura o diretório de templates relativo a este arquivo
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(base_dir, "templates"))

def format_number(value):
    try:
        if value is None: return "0,00"
        formatted = "{:,.2f}".format(float(value))
        return formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return value

templates.env.filters['format_number'] = format_number


from produtividade.services.productivity_service import get_productivity_matrix, get_latest_competence
from produtividade.services.cache_service import get_filters_cache

router = APIRouter(prefix="/produtividade", tags=["Produtividade"])

@router.get("/", response_class=HTMLResponse)
async def productivity_home(request: Request, ano: int = None, cidade: str = None, regiao: str = None, agencia: str = None):
    # Se não informar ano, busca o último disponível no banco
    if not ano:
        latest_year, _ = get_latest_competence()
        ano = latest_year or datetime.now().year

    # Busca os dados em formato de matriz (Linhas=Meses, Colunas=Equipes)
    regiao = request.query_params.get("regiao")
    cidade = request.query_params.get("cidade")
    agencia = request.query_params.get("agencia")
    contrato = request.query_params.get("contrato")
    
    data = get_productivity_matrix(year=ano, region=regiao, city=cidade, agency=agencia, contract=contrato)
    filters = get_filters_cache()
    
    return templates.TemplateResponse("index_prod.html", {
        "request": request,
        "page_title": "Dashboard de Produtividade",
        "data": data,
        "filters": filters,
        "selected_ano": ano,
        "selected_regiao": regiao,
        "selected_cidade": cidade,
        "selected_agencia": agencia,
        "selected_contrato": contrato
    })

@router.get("/api/data")
async def get_raw_data(year: int = None, month: int = None):
    data = list_productivity_data(year=year, month=month)
    return {"ok": True, "data": data}
