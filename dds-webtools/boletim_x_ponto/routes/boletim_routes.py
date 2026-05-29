# d:\programas\DDS\dds-webtools\boletim_x_ponto\routes\boletim_routes.py
from __future__ import annotations
import os
import io
import datetime
import zipfile
from typing import List, Optional
from pydantic import BaseModel
import pandas as pd

from fastapi import APIRouter, Request, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from boletim_x_ponto.services.boletim_service import BoletimXPontoService
from boletim_x_ponto.services.exportador_service import (
    exportar_comparacao_individual_excel,
    exportar_comparacao_individual_pdf,
    exportar_diferencas_individual_excel,
    exportar_diferencas_individual_pdf,
    exportar_totais_consolidados_zip,
)

# Configura o diretório de templates relativo a este arquivo
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(base_dir, "templates"))

router = APIRouter()
service = BoletimXPontoService()

class MappingPayload(BaseModel):
    nome_boletim: str
    nome_ponto_mapeado: str
    cpf_ponto: str
    pis_ponto: str

@router.get("/boletim-x-ponto", response_class=HTMLResponse)
def get_dashboard(request: Request):
    """Renderiza a página principal do Boletim x Ponto"""
    return templates.TemplateResponse(
        "index_boletim.html",
        {
            "request": request,
            "page_title": "Boletim x Ponto",
        }
    )

@router.get("/boletim-x-ponto/api/filtros")
def get_filtros():
    """Retorna os limites de data e a lista de contratos cadastrados"""
    try:
        dt_min, dt_max = service.get_date_limits()
        contratos = service.get_contracts()
        return {
            "ok": True,
            "data_min": dt_min,
            "data_max": dt_max,
            "contratos": contratos
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "message": f"Erro ao obter filtros: {str(e)}"}
        )

@router.get("/boletim-x-ponto/api/funcionarios")
def get_funcionarios(
    data_ini: str = Query(..., description="Data Inicial YYYY-MM-DD"),
    data_fim: str = Query(..., description="Data Final YYYY-MM-DD"),
    contrato: Optional[str] = Query(None, description="Contrato opcional")
):
    """Retorna os funcionários com boletins no período e contrato especificados"""
    try:
        funcionarios = service.get_employees(data_ini, data_fim, contrato)
        return {
            "ok": True,
            "funcionarios": funcionarios
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "message": f"Erro ao obter funcionários: {str(e)}"}
        )

@router.get("/boletim-x-ponto/api/comparar")
def comparar(
    employee: str = Query(..., description="Nome do Funcionário"),
    data_ini: str = Query(..., description="Data Inicial YYYY-MM-DD"),
    data_fim: str = Query(..., description="Data Final YYYY-MM-DD"),
    format: str = Query("decimal", description="Formato de exibição: 'decimal' ou 'hhmm'")
):
    """Retorna os grids triplet de Boletim, Ponto e Diferença para o funcionário no período"""
    try:
        dados = service.get_comparison_grids(employee, data_ini, data_fim, format)
        return {
            "ok": True,
            **dados
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "message": f"Erro ao calcular comparação: {str(e)}"}
        )

@router.post("/boletim-x-ponto/api/upload/boletim")
async def upload_boletim(file: UploadFile = File(...)):
    """Recebe o arquivo PDF do Boletim e insere seus dados no banco Parquet semente"""
    try:
        contents = await file.read()
        novos = service.upload_boletim(contents, file.filename)
        # Recarrega dados em memória após a persistência
        service.load_data()
        return {
            "ok": True,
            "message": f"Upload processado com sucesso. {novos} novos registros inseridos.",
            "novos_registros": novos
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": f"Erro ao processar PDF de Boletim: {str(e)}"}
        )

@router.post("/boletim-x-ponto/api/upload/ponto")
async def upload_ponto(file: UploadFile = File(...)):
    """Recebe o arquivo CSV ou Excel de Ponto e insere seus dados no banco Parquet semente"""
    try:
        contents = await file.read()
        novos = service.upload_ponto(contents, file.filename)
        # Recarrega dados em memória após a persistência
        service.load_data()
        return {
            "ok": True,
            "message": f"Upload processado com sucesso. {novos} novos registros inseridos.",
            "novos_registros": novos
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": f"Erro ao processar planilha de Ponto: {str(e)}"}
        )

@router.get("/boletim-x-ponto/api/mapping")
def get_mapping():
    """Retorna os mapeamentos de nomes cadastrados"""
    try:
        mapping = service.get_name_mapping()
        return {
            "ok": True,
            "mapping": mapping
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "message": f"Erro ao obter mapeamentos: {str(e)}"}
        )

@router.post("/boletim-x-ponto/api/mapping")
def save_mapping(payload: MappingPayload):
    """Salva ou atualiza um mapeamento de nome entre Boletim e Ponto"""
    try:
        service.update_name_mapping(
            nome_boletim=payload.nome_boletim,
            nome_ponto_mapeado=payload.nome_ponto_mapeado,
            cpf_ponto=payload.cpf_ponto,
            pis_ponto=payload.pis_ponto
        )
        # Recarrega dados após salvar
        service.load_data()
        return {
            "ok": True,
            "message": "Mapeamento atualizado com sucesso."
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "message": f"Erro ao salvar mapeamento: {str(e)}"}
        )

@router.get("/boletim-x-ponto/api/export/individual")
def export_individual(
    employee: str = Query(..., description="Nome do Funcionário"),
    data_ini: str = Query(..., description="Data Inicial YYYY-MM-DD"),
    data_fim: str = Query(..., description="Data Final YYYY-MM-DD"),
    format: str = Query("excel", description="Formato de exportação: 'excel' ou 'pdf'"),
    report_type: str = Query("comparacao", description="Tipo de relatório: 'comparacao' ou 'diferenca'"),
    hour_format: str = Query("decimal", description="Formato das horas: 'decimal' ou 'hhmm'")
):
    """Exporta o relatório individual de comparação ou diferença em Excel ou PDF"""
    try:
        dt_ini = pd.to_datetime(data_ini)
        dt_fim = pd.to_datetime(data_fim)
        format_hhmm = (hour_format.lower() == "hhmm")

        # Recupera os dataframes alinhados
        from boletim_x_ponto.services.comparacao import montar_triplet_comparacao
        df_b_f, df_p_f, df_d, _, _, _ = montar_triplet_comparacao(
            service.df_boletim, service.df_ponto, service.df_relacao_nomes, employee, dt_ini, dt_fim
        )

        if df_b_f.empty and df_p_f.empty:
            raise HTTPException(status_code=404, detail="Nenhum dado encontrado para gerar o relatório.")

        clean_name = "".join(c for c in employee if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")

        if format.lower() == "excel":
            if report_type.lower() == "comparacao":
                file_bytes = exportar_comparacao_individual_excel(
                    df_b_f, df_p_f, df_d, employee, dt_ini, dt_fim, format_hhmm
                )
                filename = f"comparacao_{clean_name}_{data_ini}_a_{data_fim}.xlsx"
            else:
                file_bytes = exportar_diferencas_individual_excel(
                    df_d, employee, dt_ini, dt_fim, format_hhmm
                )
                filename = f"diferencas_{clean_name}_{data_ini}_a_{data_fim}.xlsx"

            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            
        elif format.lower() == "pdf":
            if report_type.lower() == "comparacao":
                file_bytes = exportar_comparacao_individual_pdf(
                    df_b_f, df_p_f, df_d, employee, dt_ini, dt_fim, format_hhmm
                )
                filename = f"comparacao_{clean_name}_{data_ini}_a_{data_fim}.pdf"
            else:
                file_bytes = exportar_diferencas_individual_pdf(
                    df_d, employee, dt_ini, dt_fim, format_hhmm
                )
                filename = f"diferencas_{clean_name}_{data_ini}_a_{data_fim}.pdf"

            media_type = "application/pdf"
            
        else:
            raise HTTPException(status_code=400, detail="Formato inválido. Use 'excel' ou 'pdf'.")

        return StreamingResponse(
            io.BytesIO(file_bytes),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao exportar relatório: {str(e)}")

@router.get("/boletim-x-ponto/api/export/totais-consolidados")
def export_totais_consolidados(
    contratos: str = Query(..., description="Contratos separados por vírgula"),
    data_ini: str = Query(..., description="Data Inicial YYYY-MM-DD"),
    data_fim: str = Query(..., description="Data Final YYYY-MM-DD"),
    hour_format: str = Query("decimal", description="Formato das horas: 'decimal' ou 'hhmm'")
):
    """Exporta os totais consolidados dos contratos em um arquivo ZIP com planilhas Excel"""
    try:
        dt_ini = pd.to_datetime(data_ini)
        dt_fim = pd.to_datetime(data_fim)
        format_hhmm = (hour_format.lower() == "hhmm")

        lista_contratos = [c.strip() for c in contratos.split(",") if c.strip()]
        if not lista_contratos:
            raise HTTPException(status_code=400, detail="Nenhum contrato especificado.")

        zip_bytes = exportar_totais_consolidados_zip(
            service, lista_contratos, dt_ini, dt_fim, format_hhmm
        )

        filename = f"totais_consolidados_{data_ini}_a_{data_fim}.zip"
        return StreamingResponse(
            io.BytesIO(zip_bytes),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao exportar totais consolidados: {str(e)}")
