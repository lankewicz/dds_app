import json
import io
from typing import List, Optional
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Query
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import pandas as pd

from nfse.config import nfse_settings
from nfse.calculator import calcular_tributos_nfse
from nfse.validator import validar_rascunho_nfse
from nfse.providers.factory import get_nfse_provider

_MODULE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_MODULE_DIR / "templates"))

router = APIRouter()

# In-memory storage / cache simulation integrated with Boletim Cidades data
_pedidos_store = []
_rascunhos_store = {}
_nfse_store = {}
_auditoria_store = []

def _init_demo_data():
    if _pedidos_store:
        return
        
    test_notes = [
        {"id": 1, "nfse_num": "4226", "mun": "CORBELIA", "ibge": "4106308", "bruto": "677.23", "aliq_iss": "5.00", "inss": "23.70", "pedido_num": "PED-4226", "boletim": "BOL-2026-01", "contrato": "4600025149"},
        {"id": 2, "nfse_num": "4227", "mun": "CORONEL DOMINGOS SOARES", "ibge": "4106456", "bruto": "2335.09", "aliq_iss": "3.00", "inss": "81.73", "pedido_num": "PED-4227", "boletim": "BOL-2026-01", "contrato": "4600025149"},
        {"id": 3, "nfse_num": "4228", "mun": "CORONEL VIVIDA", "ibge": "4106506", "bruto": "3491.12", "aliq_iss": "5.00", "inss": "122.19", "pedido_num": "PED-4228", "boletim": "BOL-2026-01", "contrato": "46000251749"}, # Discrepancia: 11 dígitos
        {"id": 4, "nfse_num": "4229", "mun": "CRUZ MACHADO", "ibge": "4106803", "bruto": "894.33", "aliq_iss": "5.00", "inss": "44.72", "pedido_num": "PED-4229", "boletim": "BOL-2026-01", "contrato": "4600025149"},
        {"id": 5, "nfse_num": "4230", "mun": "CRUZEIRO DO IGUACU", "ibge": "4106571", "bruto": "2331.79", "aliq_iss": "5.00", "inss": "81.61", "pedido_num": "PED-4230", "boletim": "BOL-2026-01", "contrato": "4600025149"},
        {"id": 6, "nfse_num": "4231", "mun": "DIAMANTE DO SUL", "ibge": "4107157", "bruto": "321.50", "aliq_iss": "3.00", "inss": "11.25", "pedido_num": "PED-4231", "boletim": "BOL-2026-01", "contrato": "4600025149"}
    ]

    for n in test_notes:
        calc = calcular_tributos_nfse(
            valor_bruto=n["bruto"],
            aliquota_iss_perc=n["aliq_iss"],
            iss_retido=True,
            contrato_numero=n["contrato"],
            municipio_nome=n["mun"],
            codigo_ibge_prestacao=n["ibge"]
        )
        
        status = "Pendente de conferência"
        if n["id"] == 1:
            status = "Aprovado"
        elif n["id"] == 3:
            status = "Rejeitado"

        ped = {
            "id": n["id"],
            "numero_pedido": n["pedido_num"],
            "boletim": n["boletim"],
            "contrato_numero": n["contrato"],
            "municipio_nome": n["mun"],
            "codigo_ibge_prestacao": n["ibge"],
            "periodo_medicao": "2026/01",
            "valor_bruto": float(calc["valor_bruto"]),
            "valor_liquido": float(calc["valor_liquido"]),
            "item_pedido_codigo": "4504472658",
            "descricao_servico": f"Manutenção de redes de distribuição de energia elétrica - {n['mun']}",
            "status": status,
            "faturado": False,
            "nf_numero": n["nfse_num"],
            "created_at": datetime.utcnow().isoformat()
        }
        _pedidos_store.append(ped)

        # Valida divergências
        alertas = validar_rascunho_nfse(
            contrato_numero=n["contrato"],
            pedido_numero=n["pedido_num"],
            municipio_nome=n["mun"],
            codigo_ibge_prestacao=n["ibge"],
            codigo_ibge_incidencia=n["ibge"],
            tomador_cnpj="04370282000170",
            servico_codigo="7.05",
            valor_bruto=calc["valor_bruto"],
            base_iss=calc["base_iss"],
            aliquota_iss=calc["aliquota_iss"],
            valor_iss=calc["valor_iss"],
            iss_retido=True,
            valor_pis=calc["valor_pis"],
            valor_cofins=calc["valor_cofins"],
            valor_csll=calc["valor_csll"],
            valor_ir=calc["valor_ir"],
            valor_inss=calc["valor_inss"],
            valor_liquido=calc["valor_liquido"],
            descricao_texto=calc["descricao_analitica"],
            aprovado_humano=(status == "Aprovado")
        )

        _rascunhos_store[n["id"]] = {
            "id": n["id"],
            "pedido_id": n["id"],
            "valor_bruto": float(calc["valor_bruto"]),
            "base_iss": float(calc["base_iss"]),
            "aliquota_iss": float(calc["aliquota_iss"]),
            "valor_iss": float(calc["valor_iss"]),
            "iss_retido": True,
            "valor_inss": float(calc["valor_inss"]),
            "valor_ir": float(calc["valor_ir"]),
            "valor_pis": float(calc["valor_pis"]),
            "valor_cofins": float(calc["valor_cofins"]),
            "valor_csll": float(calc["valor_csll"]),
            "total_retencoes_federais": float(calc["total_retencoes_federais"]),
            "cbs_valor": float(calc["cbs_valor"]),
            "ibs_estadual_valor": float(calc["ibs_estadual_valor"]),
            "valor_liquido": float(calc["valor_liquido"]),
            "codigo_ibge_prestacao": n["ibge"],
            "codigo_ibge_incidencia": n["ibge"],
            "item_lc116": "7.05",
            "codigo_tributacao_nacional": "07.05.02",
            "codigo_tributacao_municipal": "4221903",
            "nbs": "101024220",
            "indicador_operacao": "020201",
            "classificacao_tributaria": "000001",
            "descricao_analitica": calc["descricao_analitica"],
            "descricao_sintetica": calc["descricao_sintetica"],
            "divergencias": alertas,
            "aprovado": (status == "Aprovado")
        }

@router.get("/boletim-cidades/nfse", response_class=HTMLResponse)
async def get_nfse_dashboard(request: Request):
    _init_demo_data()
    return templates.TemplateResponse("index_nfse.html", {
        "request": request,
        "page_title": "NFS-e Manager - PUTON & DAL MOLIN LTDA",
        "pedidos_json": json.dumps(_pedidos_store, ensure_ascii=False),
        "rascunhos_json": json.dumps(_rascunhos_store, ensure_ascii=False),
        "emissor_cnpj": nfse_settings.EMISSOR_CNPJ,
        "emissor_razao": nfse_settings.EMISSOR_RAZAO,
        "ambiente": nfse_settings.NFSE_ENV
    })

@router.get("/api/nfse/pedidos")
async def api_listar_pedidos():
    _init_demo_data()
    return JSONResponse(content=_pedidos_store)

@router.get("/api/nfse/rascunhos/{pedido_id}")
async def api_obter_rascunho(pedido_id: int):
    _init_demo_data()
    if pedido_id not in _rascunhos_store:
        raise HTTPException(status_code=404, detail="Rascunho não encontrado.")
    return JSONResponse(content=_rascunhos_store[pedido_id])

@router.post("/api/nfse/rascunhos/{pedido_id}/aprovar")
async def api_aprovar_rascunho(pedido_id: int):
    _init_demo_data()
    if pedido_id not in _rascunhos_store:
        raise HTTPException(status_code=404, detail="Rascunho não encontrado.")
    
    _rascunhos_store[pedido_id]["aprovado"] = True
    _rascunhos_store[pedido_id]["divergencias"] = [
        d for d in _rascunhos_store[pedido_id]["divergencias"] if "sem aprovação humana" not in d
    ]
    
    for p in _pedidos_store:
        if p["id"] == pedido_id:
            p["status"] = "Aprovado"
            break
            
    _auditoria_store.append({
        "id": len(_auditoria_store) + 1,
        "acao": "APROVACAO_HUMANA_NFSE",
        "entidade": "Pedido",
        "entidade_id": pedido_id,
        "usuario": "conferente@putondalmolin.com.br",
        "timestamp": datetime.utcnow().isoformat()
    })

    return JSONResponse(content={"sucesso": True, "mensagem": "NFS-e aprovada para emissão."})

@router.post("/api/nfse/emitir")
async def api_emitir_nfse(payload: dict):
    _init_demo_data()
    pedido_id = payload.get("pedido_id")
    provedor_nome = payload.get("provedor", "mock")
    
    if pedido_id not in _rascunhos_store:
        raise HTTPException(status_code=404, detail="Rascunho não encontrado.")
        
    rascunho = _rascunhos_store[pedido_id]
    if not rascunho.get("aprovado"):
        raise HTTPException(status_code=400, detail="A emissão requer aprovação humana prévia.")

    provider = get_nfse_provider(provedor_nome)
    res = provider.emitir_sincrono(rascunho, {"pedido_id": pedido_id})
    
    if res.get("sucesso"):
        for p in _pedidos_store:
            if p["id"] == pedido_id:
                p["status"] = "Autorizado"
                p["faturado"] = True
                p["nf_numero"] = res.get("numero_nfse")
                break
                
        _auditoria_store.append({
            "id": len(_auditoria_store) + 1,
            "acao": "EMISSAO_NFSE_SUCESSO",
            "entidade": "NFSe",
            "entidade_id": pedido_id,
            "usuario": "operador@putondalmolin.com.br",
            "timestamp": datetime.utcnow().isoformat()
        })
        return JSONResponse(content=res)
    else:
        for p in _pedidos_store:
            if p["id"] == pedido_id:
                p["status"] = "Rejeitado"
                break
        raise HTTPException(status_code=400, detail=res.get("mensagem", "Erro na transmissão"))

@router.get("/api/nfse/auditoria")
async def api_listar_auditoria():
    return JSONResponse(content=_auditoria_store)
