from __future__ import annotations
from datetime import datetime
from app.core.firestore import db, COL_REQUESTS, COL_SUMMARIES, COL_CONSISTENCY
from app.core.logging import get_logger

logger = get_logger(__name__)

class ConsistencyService:
    @staticmethod
    def run_test() -> dict:
        """
        Realiza testes de consistência nos dados do Firestore.
        1. Compara soma de solicitações com resumos cacheados.
        2. Verifica integridade de campos obrigatórios.
        3. Registra o resultado em uma coleção de auditoria.
        """
        now = datetime.now()
        logger.info("Iniciando teste de consistência...")

        try:
            # 1. Obter todos os documentos para validação total
            # Nota: Em bases muito grandes, isso deve ser feito via agregação ou processamento em lote.
            # Para o volume atual do VExpenses, o stream() é aceitável.
            docs = list(COL_REQUESTS.stream())
            total_count = len(docs)
            
            sum_solicitado = 0.0
            sum_aprovado = 0.0
            invalid_records = []

            for doc in docs:
                d = doc.to_dict()
                v_sol = d.get("valor_solicitado", 0.0)
                v_apr = d.get("valor_aprovado", 0.0)
                
                sum_solicitado += v_sol
                sum_aprovado += v_apr

                # Validações básicas
                issues = []
                if not d.get("usuario_origem"):
                    issues.append("Usuário ausente")
                if not d.get("data_solicitacao"):
                    issues.append("Data ausente")
                if v_apr > v_sol + 0.01: # Tolerância de centavos
                    issues.append(f"Valor aprovado ({v_apr}) maior que solicitado ({v_sol})")
                
                if issues:
                    invalid_records.append({
                        "id_alocacao": doc.id,
                        "issues": issues
                    })

            # 2. Comparar com o resumo cacheado (se existir)
            summary_doc = COL_SUMMARIES.document("default_summary").get()
            cache_diff = {}
            if summary_doc.exists:
                s = summary_doc.to_dict()
                cache_diff = {
                    "diff_solicitado": sum_solicitado - s.get("total_solicitado", 0.0),
                    "diff_aprovado": sum_aprovado - s.get("total_aprovado", 0.0),
                    "is_consistent": abs(sum_solicitado - s.get("total_solicitado", 0.0)) < 0.1
                }

            report = {
                "timestamp": now,
                "total_records": total_count,
                "calculated_solicitado": sum_solicitado,
                "calculated_aprovado": sum_aprovado,
                "invalid_records_count": len(invalid_records),
                "invalid_records_sample": invalid_records[:10], # Apenas os primeiros 10
                "cache_validation": cache_diff,
                "status": "success" if not invalid_records and (not cache_diff or cache_diff.get("is_consistent")) else "warning"
            }

            # Salvar relatório no Firestore
            COL_CONSISTENCY.add(report)
            
            logger.info(f"Teste de consistência finalizado. Status: {report['status']}")
            return report

        except Exception as e:
            logger.error(f"Erro ao executar teste de consistência: {e}", exc_info=True)
            return {"status": "error", "message": str(e), "timestamp": now}
