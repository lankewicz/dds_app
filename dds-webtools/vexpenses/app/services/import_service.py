# Finalidade: realizar leitura do Excel, validação, upsert e geração de lote de importação no Firestore.
from __future__ import annotations
from pathlib import Path
import pandas as pd
from datetime import datetime
from google.cloud import firestore

from app.core.firestore import db, COL_REQUESTS, COL_BATCHES, COL_ERRORS
from app.services.normalization import (
    build_record_hash,
    clean_text,
    parse_date,
    parse_decimal,
    to_cents,
    validate_columns,
)

class ImportService:
    def __init__(self, _db=None) -> None:
        pass

    def create_batch(self, source_filename: str, total_rows: int) -> dict:
        """Cria um registro de lote com status pendente."""
        batch_ref = COL_BATCHES.document()
        batch_id = batch_ref.id
        batch_data = {
            "id": batch_id,
            "source_filename": source_filename,
            "total_rows": total_rows,
            "inserted_count": 0,
            "updated_count": 0,
            "unchanged_count": 0,
            "error_count": 0,
            "status": "processing",
            "progress": 0,
            "imported_at": datetime.now()
        }
        batch_ref.set(batch_data)
        return batch_data

    def process_import_task(self, batch_id: str, file_path: Path, source_filename: str):
        """Tarefa de background otimizada com WriteBatch e Cache de Hashes."""
        from app.core.logging import get_logger
        logger = get_logger(__name__)
        
        try:
            df = pd.read_excel(file_path)
            validate_columns(df)
            total_rows = len(df)
            
            # 1. Carregar hashes existentes em memória para evitar N chamadas de 'get()'
            logger.info(f"Carregando hashes existentes para o lote {batch_id}...")
            existing_hashes = {}
            docs = COL_REQUESTS.select(["record_hash"]).stream()
            for doc in docs:
                existing_hashes[doc.id] = doc.to_dict().get("record_hash")
            
            inserted = 0
            updated = 0
            unchanged = 0
            error_count = 0
            
            # Contadores de progresso real
            p_inserted = 0
            p_updated = 0
            now = datetime.now()
            
            # Preparar operações
            operations = []
            
            for index, row in df.iterrows():
                row_number = index + 2
                
                try:
                    id_alocacao = clean_text(row.get("Identificação da alocação"))
                    usuario_origem = clean_text(row.get("Usuário"))
                    data_solicitacao = parse_date(row.get("Data da Solicitação"))
                    previsao_uso = parse_date(row.get("Previsão de Uso"))
                    valor_solicitado = parse_decimal(row.get("Valor Solicitado"))
                    justificativa = clean_text(row.get("Justificativa"))
                    status = clean_text(row.get("Status"))
                    aprovador = clean_text(row.get("Aprovador"))
                    data_aprovacao = parse_date(row.get("Data Aprovação"))
                    valor_aprovado = parse_decimal(row.get("Valor Aprovado"))

                    if not id_alocacao and not usuario_origem and not justificativa:
                        continue

                    if not id_alocacao:
                        if status and "aprovad" in status.lower() and "reprovad" not in status.lower():
                            raise ValueError("Identificação da alocação é obrigatória para solicitações aprovadas.")
                        import hashlib
                        raw_id = f"{usuario_origem}|{data_solicitacao}|{valor_solicitado}|{justificativa}"
                        id_alocacao = f"fallback_{hashlib.md5(raw_id.encode()).hexdigest()[:10]}"

                    if not usuario_origem: raise ValueError("Usuário não informado.")
                    if not data_solicitacao: raise ValueError("Data da Solicitação não informada.")
                    if status:
                        s_lower = status.lower()
                        if "pendente" in s_lower or "enviado" in s_lower:
                            continue

                    sol = to_cents(valor_solicitado)
                    app = to_cents(valor_aprovado)
                    s_norm = (status or "").lower().strip()
                    
                    # Calcular Glosa e Reprovação na escrita (Write-Time Computed Fields)
                    if "reprov" in s_norm:
                        v_repro = sol
                        v_glosa = 0
                    elif "aprov" in s_norm:
                        v_glosa = max(0, sol - app)
                        v_repro = 0
                    else:
                        v_glosa = 0
                        v_repro = 0

                    payload = {
                        "id_alocacao": id_alocacao,
                        "usuario_origem": usuario_origem,
                        "data_solicitacao": data_solicitacao.isoformat() if data_solicitacao else None,
                        "ano": data_solicitacao.year if data_solicitacao else None,
                        "mes": data_solicitacao.month if data_solicitacao else None,
                        "previsao_uso": previsao_uso.isoformat() if previsao_uso else None,
                        "valor_solicitado": sol,
                        "justificativa": justificativa,
                        "status": status,
                        "aprovador": aprovador,
                        "data_aprovacao": data_aprovacao.isoformat() if data_aprovacao else None,
                        "valor_aprovado": app,
                        "valor_glosa": v_glosa,
                        "valor_repro": v_repro,
                        "import_batch_id": batch_id,
                    }
                    record_hash = build_record_hash(payload)
                    payload["record_hash"] = record_hash

                    # Comparar com o cache em memória
                    if id_alocacao not in existing_hashes:
                        operations.append(("set", id_alocacao, payload))
                        inserted += 1
                    elif existing_hashes[id_alocacao] != record_hash:
                        operations.append(("update", id_alocacao, payload))
                        updated += 1
                    else:
                        unchanged += 1

                except Exception as exc:
                    COL_ERRORS.document().set({
                        "batch_id": batch_id,
                        "row_number": row_number,
                        "message": str(exc),
                        "created_at": now
                    })
                    error_count += 1

            # Garantir lotes de pelo menos 50 itens (ou o total disponível), respeitando o limite de 500 do Firestore
            BATCH_SIZE = max(50, min(500, int(total_rows * 0.01)))
            total_ops = len(operations)
            
            logger.info(f"Executando {total_ops} operações com lotes dinâmicos de {BATCH_SIZE} itens...")
            
            for i in range(0, total_ops, BATCH_SIZE):
                # Checar cancelamento a cada lote
                batch_doc = COL_BATCHES.document(batch_id).get()
                if batch_doc.exists and batch_doc.to_dict().get("status") == "cancelled":
                    logger.info(f"Lote {batch_id} cancelado antes do commit do lote {i}.")
                    return

                chunk = operations[i : i + BATCH_SIZE]
                firestore_batch = db.batch()
                
                for op_type, doc_id, data in chunk:
                    doc_ref = COL_REQUESTS.document(doc_id)
                    if op_type == "set":
                        firestore_batch.set(doc_ref, data)
                    else:
                        firestore_batch.update(doc_ref, data)
                
                firestore_batch.commit()
                
                # Atualizar progresso real baseado no que foi enviado para o Firestore
                for op_type, _, _ in chunk:
                    if op_type == "set": p_inserted += 1
                    else: p_updated += 1

                processed_so_far = i + len(chunk)
                COL_BATCHES.document(batch_id).update({
                    "inserted_count": p_inserted,
                    "updated_count": p_updated,
                    "unchanged_count": unchanged,
                    "error_count": error_count,
                    "progress": int((processed_so_far / total_ops) * 100) if total_ops > 0 else 100
                })

            # Finalizar lote
            COL_BATCHES.document(batch_id).update({
                "inserted_count": p_inserted,
                "updated_count": p_updated,
                "unchanged_count": unchanged,
                "error_count": error_count,
                "status": "completed",
                "progress": 100,
                "finished_at": datetime.now()
            })
            
            # Disparar tarefas pós-importação
            self.process_post_import(batch_id)

        except Exception as e:
            logger.error(f"Erro fatal no processamento do lote {batch_id}: {e}", exc_info=True)
            COL_BATCHES.document(batch_id).update({
                "status": "failed",
                "error_message": str(e)
            })

    def get_batch_status(self, batch_id: str) -> dict | None:
        doc = COL_BATCHES.document(batch_id).get()
        return doc.to_dict() if doc.exists else None

    def cancel_batch(self, batch_id: str) -> bool:
        """Marca o lote para cancelamento."""
        doc_ref = COL_BATCHES.document(batch_id)
        doc = doc_ref.get()
        if doc.exists and doc.to_dict().get("status") == "processing":
            doc_ref.update({"status": "cancelled"})
            return True
        return False

    def import_xlsx(self, file_path: Path, original_filename: str | None = None) -> dict:
        """Versão síncrona mantida para compatibilidade."""
        df = pd.read_excel(file_path)
        batch = self.create_batch(original_filename or file_path.name, len(df))
        self.process_import_task(batch["id"], file_path, original_filename or file_path.name)
        return self.get_batch_status(batch["id"])

    @staticmethod
    def process_post_import(batch_id: str | None = None):
        from app.services.report_service import ReportService
        from app.services.consistency_service import ConsistencyService
        from app.core.logging import get_logger
        
        logger = get_logger(__name__)
        logger.info(f"Processamento pós-importação iniciado (Batch: {batch_id})")
        ReportService.rebuild_all_caches()
        ConsistencyService.run_test()
        logger.info(f"Processamento pós-importação finalizado (Batch: {batch_id})")
