# Finalidade: endpoints para upload e acompanhamento das importações no Firestore.
from pathlib import Path
import shutil
import uuid
from fastapi import APIRouter, File, HTTPException, UploadFile, BackgroundTasks

from app.core.config import settings
from app.schemas.imports import ImportBatchSummary
from app.services.import_service import ImportService
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/importacoes", tags=["Importações"])

@router.post("/upload", response_model=ImportBatchSummary)
def upload_import_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> ImportBatchSummary:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Envie um arquivo Excel .xlsx.")

    upload_dir = Path(settings.upload_tmp_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = upload_dir / f"{uuid.uuid4().hex}_{file.filename}"

    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # 1. Ler o arquivo para contar linhas (rápido)
        import pandas as pd
        df = pd.read_excel(destination)
        total_rows = len(df)
        
        service = ImportService()
        # 2. Criar lote com status 'processing'
        batch = service.create_batch(file.filename, total_rows)
        
        # 3. Disparar o processamento real em background
        background_tasks.add_task(service.process_import_task, batch["id"], destination, file.filename)
        
        return ImportBatchSummary.model_validate(batch)
    except Exception as e:
        logger.error(f"Erro inesperado no upload do arquivo {file.filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@router.get("/{batch_id}", response_model=ImportBatchSummary)
def get_import_status(batch_id: str):
    service = ImportService()
    batch = service.get_batch_status(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
    return ImportBatchSummary.model_validate(batch)

@router.post("/{batch_id}/cancel")
def cancel_import(batch_id: str):
    service = ImportService()
    success = service.cancel_batch(batch_id)
    if not success:
        raise HTTPException(status_code=400, detail="Não foi possível cancelar o lote (já finalizado ou inexistente).")
    return {"status": "success", "message": "Cancelamento solicitado."}
