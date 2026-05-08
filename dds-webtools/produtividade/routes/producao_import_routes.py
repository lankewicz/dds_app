# -----------------------------------------------------------------------------
# Arquivo : routes/producao_import_routes.py
# Objetivo: Expor o preview e a importação confirmada da planilha-base mensal de
#           produção BMG enviada pela tela de configurações do monitor.
# -----------------------------------------------------------------------------

from __future__ import annotations

import json
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from produtividade.services.producao_import_service import analyze_import_file, get_last_import_job


router = APIRouter()


@router.get("/api/producao/import/last")
def read_last_import_job():
    data = get_last_import_job()
    return JSONResponse(jsonable_encoder({"ok": True, "job": data}))


@router.post("/api/producao/import/preview")
async def preview_import(
    file: UploadFile = File(...),
    monthNumber: int | None = Form(None),
    year: int | None = Form(None),
):
    try:
        file_bytes = await file.read()
        data = analyze_import_file(
            file_name=file.filename or "importacao.xlsx",
            file_bytes=file_bytes,
            selected_month_number=monthNumber,
            selected_year=year,
            commit=False,
        )
        return JSONResponse(jsonable_encoder(data))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao analisar o arquivo: {exc}") from exc


@router.post("/api/producao/import/execute")
async def execute_import(
    file: UploadFile = File(...),
    monthNumber: int | None = Form(None),
    year: int | None = Form(None),
    resolutions: str | None = Form(None),
):
    try:
        parsed_resolutions = json.loads(resolutions) if resolutions else {}
        file_bytes = await file.read()
        data = analyze_import_file(
            file_name=file.filename or "importacao.xlsx",
            file_bytes=file_bytes,
            selected_month_number=monthNumber,
            selected_year=year,
            commit=True,
            resolutions=parsed_resolutions,
        )
        return JSONResponse(jsonable_encoder(data))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao importar o arquivo: {exc}") from exc
