# d:\programas\DDS\dds-webtools\bdo\routes\boletim_routes.py
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
from starlette.concurrency import run_in_threadpool

from bdo.services.boletim_service import BoletimXPontoService
from bdo.services.exportador_service import (
    exportar_comparacao_individual_excel,
    exportar_comparacao_individual_pdf,
    exportar_diferencas_individual_excel,
    exportar_diferencas_individual_pdf,
    exportar_totais_consolidados_zip,
    exportar_totais_separados_por_contrato_zip,
)
from bdo.services.pacote_veiculo_service import gerar_pacote_veiculo_zip
from bdo.services.rotalog_crawler_service import sincronizar_rotalog

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

class RotalogCrawlerPayload(BaseModel):
    data_ini: str
    data_fim: str


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

@router.get("/boletim-x-ponto/print/funcionarios", response_class=HTMLResponse)
def print_funcionarios(
    request: Request,
    contrato: str = Query(..., description="Contrato selecionado"),
    data_ini: str = Query(..., description="Data Inicial YYYY-MM-DD"),
    data_fim: str = Query(..., description="Data Final YYYY-MM-DD"),
    hour_format: str = Query("decimal", description="decimal ou hhmm"),
    hide_zeros: bool = Query(False),
):
    """Página imprimível, com uma folha por funcionário do contrato."""
    try:
        employees = service.get_employees(data_ini, data_fim, contrato)
        reports = []

        def zero_value(value) -> bool:
            text = str(value or "").strip().replace("−", "-")
            if text in {"0", "0,0", "0,00", "0.0", "0.00", "0:00", "00:00", "-0,00", "-0.00", "-0:00"}:
                return True
            try:
                return abs(float(text.replace(",", "."))) < 1e-9
            except (TypeError, ValueError):
                return False

        for employee in employees:
            data = service.get_comparison_grids(
                employee, data_ini, data_fim, hour_format
            )
            if hide_zeros:
                for key, start in (
                    ("grid_boletim", 3),
                    ("grid_ponto", 1),
                    ("grid_diferenca", 1),
                ):
                    data[key] = [
                        row[:start] + ["" if zero_value(v) else v for v in row[start:]]
                        for row in data[key]
                    ]
                for key, start in (
                    ("totais_boletim", 3),
                    ("totais_ponto", 1),
                    ("totais_diferenca", 1),
                ):
                    row = data[key]
                    data[key] = row[:start] + ["" if zero_value(v) else v for v in row[start:]]
            reports.append({"employee": employee, "data": data})

        return templates.TemplateResponse(
            "print_funcionarios.html",
            {
                "request": request,
                "contrato": contrato,
                "data_ini": pd.Timestamp(data_ini).strftime("%d/%m/%Y"),
                "data_fim": pd.Timestamp(data_fim).strftime("%d/%m/%Y"),
                "reports": reports,
            },
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Erro ao preparar impressão: {error}")

@router.get("/boletim-x-ponto/api/filtros")
def get_filtros(
    data_ini: Optional[str] = Query(None, description="Data inicial opcional YYYY-MM-DD"),
    data_fim: Optional[str] = Query(None, description="Data final opcional YYYY-MM-DD"),
):
    """Retorna limites globais e contratos presentes no período informado."""
    try:
        dt_min, dt_max = service.get_date_limits()
        contratos = service.get_contracts(data_ini, data_fim)
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

@router.post("/boletim-x-ponto/api/import/rotalog")
async def importar_rotalog(payload: RotalogCrawlerPayload):
    """Executa o crawler e publica equipes/eventos nos Parquets versionados."""
    try:
        result = await run_in_threadpool(
            sincronizar_rotalog,
            service.repository,
            payload.data_ini,
            payload.data_fim,
        )
        return {"ok": True, **result}
    except (ValueError, RuntimeError, PermissionError) as error:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": str(error)},
        )
    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "message": f"Erro ao sincronizar ROTALOG: {error}"},
        )

@router.get("/boletim-x-ponto/api/veiculos")
def get_veiculos(
    data_ini: str = Query(..., description="Data Inicial YYYY-MM-DD"),
    data_fim: str = Query(..., description="Data Final YYYY-MM-DD"),
    contrato: Optional[str] = Query(None, description="Contrato opcional"),
):
    """Lista os veículos/equipes do ROTALOG presentes no filtro."""
    try:
        return {
            "ok": True,
            "veiculos": service.get_vehicles(data_ini, data_fim, contrato),
        }
    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "message": f"Erro ao obter veículos: {error}"},
        )

@router.get("/boletim-x-ponto/api/veiculos/comparar")
def comparar_veiculo(
    veiculo: str = Query(..., description="Veículo/equipe"),
    data_ini: str = Query(..., description="Data Inicial YYYY-MM-DD"),
    data_fim: str = Query(..., description="Data Final YYYY-MM-DD"),
    contrato: Optional[str] = Query(None, description="Contrato opcional"),
):
    """Cruza ROTALOG, Boletim e Ponto por veículo, eletricista e dia."""
    try:
        return {
            "ok": True,
            **service.get_vehicle_comparison(
                veiculo, data_ini, data_fim, contrato
            ),
        }
    except Exception as error:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "message": f"Erro ao comparar veículo: {error}"},
        )

@router.get("/boletim-x-ponto/api/export/veiculo-pacote")
def export_vehicle_package(
    veiculo: str = Query(..., description="Veículo/equipe"),
    data_ini: str = Query(..., description="Data Inicial YYYY-MM-DD"),
    data_fim: str = Query(..., description="Data Final YYYY-MM-DD"),
    contrato: Optional[str] = Query(None, description="Contrato opcional"),
    hour_format: str = Query("decimal", description="decimal ou hhmm"),
):
    """Exporta ROTALOG e comparações dos eletricistas em um único ZIP."""
    try:
        payload = gerar_pacote_veiculo_zip(
            service,
            veiculo,
            data_ini,
            data_fim,
            contrato,
            hour_format.lower() == "hhmm",
        )
        safe_vehicle = "".join(
            character for character in veiculo
            if character.isalnum() or character in ("-", "_")
        ) or "veiculo"
        filename = f"pacote_equipe_{safe_vehicle}_{data_ini}_a_{data_fim}.zip"
        return StreamingResponse(
            io.BytesIO(payload),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as error:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar pacote do veículo: {error}",
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

async def _process_uploads(files: List[UploadFile], processor):
    summary = {
        "arquivos_lidos": len(files),
        "arquivos_importados": 0,
        "arquivos_ignorados": 0,
        "registros_processados": 0,
        "registros_atualizados": 0,
        "registros_novos": 0,
        "registros_ignorados": 0,
        "detalhes": [],
    }
    for upload in files:
        filename = upload.filename or "arquivo_sem_nome"
        try:
            payload = await upload.read()
            stats = await run_in_threadpool(processor, payload, filename)
            values = stats.to_dict()
            summary["registros_processados"] += values["processed"]
            summary["registros_atualizados"] += values["updated"]
            summary["registros_novos"] += values["new"]
            summary["registros_ignorados"] += values["ignored"]
            if values["processed"] > 0:
                summary["arquivos_importados"] += 1
                status = "importado"
            else:
                summary["arquivos_ignorados"] += 1
                status = "ignorado"
            summary["detalhes"].append({
                "arquivo": filename, "status": status, **values
            })
        except Exception as error:
            summary["arquivos_ignorados"] += 1
            summary["detalhes"].append({
                "arquivo": filename,
                "status": "ignorado",
                "motivo": str(error),
            })
    summary["message"] = (
        f"{summary['arquivos_lidos']} arquivos lidos; "
        f"{summary['arquivos_importados']} importados; "
        f"{summary['arquivos_ignorados']} ignorados. "
        f"{summary['registros_processados']} registros processados; "
        f"{summary['registros_atualizados']} atualizados; "
        f"{summary['registros_novos']} novos; "
        f"{summary['registros_ignorados']} ignorados."
    )
    return summary

@router.post("/boletim-x-ponto/api/upload/boletim")
async def upload_boletim(files: List[UploadFile] = File(...)):
    summary = await _process_uploads(files, service.upload_boletim)
    return {"ok": True, **summary}

@router.post("/boletim-x-ponto/api/upload/ponto")
async def upload_ponto(files: List[UploadFile] = File(...)):
    summary = await _process_uploads(files, service.upload_ponto)
    return {"ok": True, **summary}

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
        from bdo.services.comparacao import montar_triplet_comparacao
        df_boletim, df_ponto = service._get_employee_dataframes(employee, data_ini, data_fim)
        df_b_f, df_p_f, df_d, _, _, _ = montar_triplet_comparacao(
            df_boletim, df_ponto, service.df_relacao_nomes, employee, dt_ini, dt_fim
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
    hour_format: str = Query("decimal", description="Formato das horas: 'decimal' ou 'hhmm'"),
    mode: str = Query("combined", description="'combined' ou 'separate'"),
):
    """Exporta os totais consolidados dos contratos em um arquivo ZIP com planilhas Excel"""
    try:
        dt_ini = pd.to_datetime(data_ini)
        dt_fim = pd.to_datetime(data_fim)
        format_hhmm = (hour_format.lower() == "hhmm")

        lista_contratos = [c.strip() for c in contratos.split(",") if c.strip()]
        if not lista_contratos:
            raise HTTPException(status_code=400, detail="Nenhum contrato especificado.")

        if mode.lower() == "separate":
            zip_bytes = exportar_totais_separados_por_contrato_zip(
                service, lista_contratos, dt_ini, dt_fim, format_hhmm
            )
            filename = f"totais_por_contrato_{data_ini}_a_{data_fim}.zip"
        else:
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
