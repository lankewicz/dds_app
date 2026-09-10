from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import os
import uuid
from app.core.logging import LOG_FILE
from app.core.config import settings

router = APIRouter(prefix="/system", tags=["Sistema"])

@router.get("/info")
def get_system_info():
    revision = os.environ.get("K_REVISION", settings.app_revision)
    if "-" in revision:
        parts = revision.split("-")
        if len(parts) >= 2:
            revision = "-".join(parts[-2:])
            
    return {
        "app_name": settings.app_name,
        "version": revision,
        "env": settings.app_env
    }

@router.get("/logs", response_class=FileResponse)
def get_app_logs():
    if not os.path.exists(LOG_FILE):
        raise HTTPException(status_code=404, detail="Arquivo de log não encontrado.")
    return FileResponse(LOG_FILE, filename="app.log")

@router.get("/logs/tail")
def tail_logs(lines: int = 100):
    if not os.path.exists(LOG_FILE):
        return {"logs": "Arquivo de log não encontrado."}
    
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        content = f.readlines()
        return {"logs": "".join(content[-lines:])}

@router.post("/reset-database")
def reset_database(background_tasks: BackgroundTasks):
    from app.core.firestore import db, COL_REQUESTS, COL_BATCHES, COL_ERRORS, COL_SUMMARIES, COL_CONSISTENCY, COL_SYSTEM_TASKS
    
    task_id = str(uuid.uuid4())
    task_ref = COL_SYSTEM_TASKS.document(task_id)
    
    task_ref.set({
        "id": task_id,
        "type": "reset_database",
        "status": "processing",
        "progress": 0,
        "message": "Iniciando limpeza...",
        "created_at": datetime.now()
    })
    
    def run_reset():
        try:
            from app.services.report_service import ReportService
            
            collections = [
                COL_REQUESTS, 
                COL_BATCHES, 
                COL_ERRORS, 
                COL_SUMMARIES, 
                COL_CONSISTENCY
            ]
            
            total_steps = len(collections) + 1
            for i, coll_ref in enumerate(collections):
                task_ref.update({
                    "progress": int((i / total_steps) * 100),
                    "message": f"Limpando coleção {i+1} de {len(collections)}..."
                })
                
                while True:
                    docs = list(coll_ref.limit(100).stream())
                    if not docs: break
                    batch = db.batch()
                    for d in docs: batch.delete(d.reference)
                    batch.commit()

            task_ref.update({"progress": 90, "message": "Limpando caches..."})
            ReportService.clear_cache()
            
            task_ref.update({
                "status": "completed",
                "progress": 100,
                "message": "Limpeza concluída com sucesso!",
                "finished_at": datetime.now()
            })
        except Exception as e:
            task_ref.update({
                "status": "failed",
                "message": f"Erro: {str(e)}",
                "finished_at": datetime.now()
            })

    background_tasks.add_task(run_reset)
    return {"task_id": task_id}

@router.get("/tasks/{task_id}")
def get_task_status(task_id: str):
    from app.core.firestore import COL_SYSTEM_TASKS
    doc = COL_SYSTEM_TASKS.document(task_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return doc.to_dict()

@router.post("/rebuild-cache")
def rebuild_cache(background_tasks: BackgroundTasks):
    from app.services.report_service import ReportService
    from app.core.firestore import COL_SYSTEM_TASKS
    
    task_id = str(uuid.uuid4())
    task_ref = COL_SYSTEM_TASKS.document(task_id)
    task_ref.set({
        "id": task_id,
        "type": "rebuild_cache",
        "status": "processing",
        "progress": 0,
        "message": "Iniciando reconstrução de índices...",
        "created_at": datetime.now()
    })
    
    background_tasks.add_task(ReportService.rebuild_all_caches, task_id)
    return {"status": "success", "task_id": task_id, "message": "Reconstrução de cache iniciada em segundo plano."}

@router.post("/consistency-test")
def run_consistency_test():
    from app.services.consistency_service import ConsistencyService
    report = ConsistencyService.run_test()
    return report
