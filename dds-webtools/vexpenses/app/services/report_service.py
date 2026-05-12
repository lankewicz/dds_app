# Finalidade: gerar relatórios agregados usando Firestore e processamento em memória.
from __future__ import annotations
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytz
import pandas as pd
from app.core.firestore import db, COL_REQUESTS, COL_SUMMARIES
from app.schemas.reports import MonthlyReportRow, SummaryReportOut, TopUserReportRow

# Cache global simples
_REPORT_CACHE = {}
_CACHE_TTL = 86400 # 24 horas (dados só mudam no import ou rebuild manual)

class ReportService:
    def __init__(self, _db=None) -> None:
        pass

    def _prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Garante que o DataFrame tenha as colunas de cálculo de Glosa e Reprovação."""
        if df.empty:
            for col in ["valor_repro", "valor_glosa"]:
                if col not in df.columns:
                    df[col] = 0.0
            return df
            
        # Converter centavos do Firestore para Reais (float) para cálculos e exibição
        df["valor_solicitado"] = pd.to_numeric(df["valor_solicitado"], errors='coerce').fillna(0) / 100.0
        df["valor_aprovado"] = pd.to_numeric(df["valor_aprovado"], errors='coerce').fillna(0) / 100.0
        df["valor_repro"] = pd.to_numeric(df.get("valor_repro", 0), errors='coerce').fillna(0) / 100.0
        df["valor_glosa"] = pd.to_numeric(df.get("valor_glosa", 0), errors='coerce').fillna(0) / 100.0
        
        return df

    @staticmethod
    def clear_cache():
        global _REPORT_CACHE
        _REPORT_CACHE = {}
        
        # Limpar cache persistente no Firestore
        COL_SUMMARIES.document("default_summary").delete()
        COL_SUMMARIES.document("default_monthly").delete()
        COL_SUMMARIES.document("default_filters").delete()
        
        from app.core.logging import get_logger
        get_logger(__name__).info("Cache de relatórios (Memória e Firestore) limpo.")

    @classmethod
    def rebuild_all_caches(cls, task_id: str = None):
        """
        Reconstrói todos os caches agregados (Total e por Mês).
        Suporta rastreamento de progresso via task_id.
        """
        from app.core.logging import get_logger
        from app.core.firestore import db
        import pandas as pd
        from datetime import datetime
        from google.cloud import firestore
        
        logger = get_logger(__name__)
        service = cls()
        
        def update_task(progress: int, message: str):
            if task_id:
                try:
                    db.collection("vexpenses").document("data").collection("system_tasks").document(task_id).update({
                        "progress": progress,
                        "message": message
                    })
                except:
                    pass

        logger.info("Iniciando reconstrução completa de caches...")
        update_task(5, "Limpando caches antigos...")
        cls.clear_cache()
        
        # 1. Obter todos os dados para verificar integridade
        update_task(10, "Carregando dados do Firestore...")
        docs = list(COL_REQUESTS.stream())
        if not docs:
            logger.warning("Nenhum dado encontrado para processar.")
            update_task(100, "Concluído: Nenhum dado encontrado.")
            return

        # 2. Corrigir inconsistências de Ano/Mês nos registros individuais (Self-healing)
        update_task(20, f"Verificando integridade de {len(docs)} registros...")
        correction_batch = db.batch()
        corrections_count = 0
        
        data_list = []
        for i, doc in enumerate(docs):
            d = doc.to_dict()
            d["id_doc"] = doc.id
            data_list.append(d)
            
            # Progresso parcial na leitura
            if i % 1000 == 0 and i > 0:
                update_task(20 + int((i/len(docs)) * 10), f"Lendo registros... ({i}/{len(docs)})")
                
            try:
                dt_str = d.get("data_solicitacao", "")
                if not dt_str: continue
                
                dt = datetime.fromisoformat(dt_str.split('T')[0])
                actual_year = dt.year
                actual_month = dt.month
                
                stored_year = d.get("ano")
                stored_month = d.get("mes")
                
                if stored_year != actual_year or stored_month != actual_month:
                    corrections_count += 1
                    correction_batch.update(doc.reference, {
                        "ano": actual_year,
                        "mes": actual_month
                    })
                    if corrections_count % 450 == 0:
                        correction_batch.commit()
                        correction_batch = db.batch()
            except Exception:
                continue
        
        if corrections_count > 0:
            correction_batch.commit()
            logger.info(f"Integridade restaurada: {corrections_count} registros corrigidos.")

        # 3. Processar DataFrame para novos summaries
        update_task(35, "Analisando dados...")
        df = pd.DataFrame(data_list)
        if df.empty:
            logger.warning("Nenhum dado encontrado para reconstruir cache.")
            update_task(100, "Concluído: DataFrame vazio.")
            return
            
        # Garantir tipos numéricos e identificar quem precisa de migração
        for col in ["valor_solicitado", "valor_aprovado", "valor_glosa", "valor_repro"]:
            df[col] = pd.to_numeric(df.get(col, 0), errors='coerce').fillna(0)
        
        # MIGRACAO AUTOMATICA: Se houver registros antigos sem campos ou com imprecisão decimal, atualiza o Firestore
        if "status" in df.columns:
            # Detectar quem não tem os campos OU quem tem valores com muitas casas decimais (imprecisão de float)
            needs_calc = (df["valor_glosa"] == 0) & (df["valor_repro"] == 0) & (df["status"].str.contains("aprov|reprov", case=False, na=False))
            needs_round = (df["valor_glosa"] != df["valor_glosa"].round(2)) | (df["valor_repro"] != df["valor_repro"].round(2))
            needs_fix = needs_calc | needs_round
            
            if needs_fix.any():
                total_to_fix = needs_fix.sum()
                logger.info(f"Detectados {total_to_fix} registros antigos. Iniciando migração automática...")
                update_task(40, f"Migrando {total_to_fix} registros antigos...")
                batch = db.batch()
                batch_count = 0
                fixed_count = 0
                
                for idx, row in df[needs_fix].iterrows():
                    sol = float(row["valor_solicitado"])
                    app = float(row["valor_aprovado"])
                    s_norm = str(row["status"]).lower()
                    
                    v_repro = round(sol, 2) if "reprov" in s_norm else 0.0
                    v_glosa = round(max(0.0, sol - app), 2) if "aprov" in s_norm and "reprov" not in s_norm else 0.0
                    
                    df.at[idx, "valor_glosa"] = v_glosa
                    df.at[idx, "valor_repro"] = v_repro
                    
                    doc_id = str(row.get("id_doc"))
                    if doc_id:
                        batch.update(COL_REQUESTS.document(doc_id), {
                            "valor_glosa": v_glosa,
                            "valor_repro": v_repro
                        })
                        batch_count += 1
                        fixed_count += 1
                        
                    if batch_count >= 450:
                        batch.commit()
                        batch = db.batch()
                        batch_count = 0
                        update_task(40 + int((fixed_count/total_to_fix) * 30), f"Migrando... ({fixed_count}/{total_to_fix})")
                
                if batch_count > 0:
                    batch.commit()
                logger.info("Migração automática concluída.")
                update_task(70, "Migração concluída. Gerando índices...")

        df["data_dt"] = pd.to_datetime(df["data_solicitacao"], errors='coerce')
        df = df.dropna(subset=["data_dt"])
        df["ano_val"] = df["data_dt"].dt.year
        df["mes_val"] = df["data_dt"].dt.month
        df["dia_val"] = df["data_dt"].dt.day
        
        # 3. Gerar fragmentos mensais
        grouped = df.groupby(["ano_val", "mes_val"]).agg({
            "valor_solicitado": "sum",
            "valor_aprovado": "sum",
            "valor_repro": "sum",
            "valor_glosa": "sum",
            "data_dt": "count"
        }).reset_index()
        
        logger.info(f"Gerando {len(grouped)} fragmentos mensais...")
        for i, (_, row) in enumerate(grouped.iterrows()):
            y, m = int(row["ano_val"]), int(row["mes_val"])
            cache_data = {
                "ano": y,
                "mes": m,
                "quantidade": int(row["data_dt"]),
                "total_solicitado": int(row["valor_solicitado"]),
                "total_aprovado": int(row["valor_aprovado"]),
                "total_reprovado": int(row["valor_repro"]),
                "total_glosado": int(row["valor_glosa"]),
                "updated_at": datetime.now(timezone.utc)
            }
            COL_SUMMARIES.document(f"month_{y}_{m}").set(cache_data)
            update_task(70 + int((i/len(grouped)) * 10), f"Gerando meses... ({i+1}/{len(grouped)})")
        
        # 4. Gerar fragmentos diários
        daily_grouped = df.groupby(["ano_val", "mes_val", "dia_val"]).agg({
            "valor_solicitado": "sum",
            "valor_aprovado": "sum",
            "valor_repro": "sum",
            "valor_glosa": "sum",
            "data_dt": "count"
        }).reset_index()
        
        logger.info(f"Gerando {len(daily_grouped)} fragmentos diários...")
        for i, (_, row) in enumerate(daily_grouped.iterrows()):
            y, m, d = int(row["ano_val"]), int(row["mes_val"]), int(row["dia_val"])
            cache_data = {
                "tipo": "day",
                "ano": y,
                "mes": m,
                "dia": d,
                "quantidade": int(row["data_dt"]),
                "total_solicitado": int(row["valor_solicitado"]),
                "total_aprovado": int(row["valor_aprovado"]),
                "total_reprovado": int(row["valor_repro"]),
                "total_glosado": int(row["valor_glosa"]),
                "last_updated": firestore.SERVER_TIMESTAMP
            }
            COL_SUMMARIES.document(f"day_{y}_{m}_{d}").set(cache_data)
            if i % 50 == 0:
                update_task(80 + int((i/len(daily_grouped)) * 10), f"Gerando dias... ({i+1}/{len(daily_grouped)})")
        
        # 5. Gerar Resumo Geral e Filtros
        update_task(95, "Finalizando caches...")
        service.summary()
        service.get_filter_options()
        
        logger.info("Caches reconstruídos com sucesso.")
        update_task(100, "Concluído com sucesso!")
        if task_id:
            db.collection("vexpenses").document("data").collection("system_tasks").document(task_id).update({
                "status": "completed",
                "finished_at": datetime.now(timezone.utc)
            })

    def _get_base_query(
        self,
        data_inicio: date | None = None,
        data_fim: date | None = None,
        aprovador: str | None = None,
        usuario: str | None = None,
        status: str | None = None,
        ano: int | None = None,
        mes: int | None = None,
        ignore_limit: bool = False,
        **kwargs
    ):
        cache_key = f"{data_inicio}_{data_fim}_{aprovador}_{usuario}_{status}_{ano}_{mes}"
        now = datetime.now().timestamp()
        
        if cache_key in _REPORT_CACHE:
            entry = _REPORT_CACHE[cache_key]
            if now - entry['time'] < _CACHE_TTL:
                return entry['data'].copy()

        try:
            query = COL_REQUESTS
            query = query.select([
                "valor_solicitado", 
                "valor_aprovado", 
                "data_solicitacao", 
                "status", 
                "usuario_origem", 
                "aprovador",
                "id_alocacao",
                "valor_glosa",
                "valor_repro"
            ])
            
            # Filtros nativos do Firestore (podem exigir índices compostos)
            if data_inicio:
                query = query.where("data_solicitacao", ">=", data_inicio.isoformat())
            if data_fim:
                query = query.where("data_solicitacao", "<=", data_fim.isoformat())
            if status:
                query = query.where("status", "==", status.strip())
            
            # Filtros nativos de Ano e Mês (Novo)
            if ano:
                query = query.where("ano", "==", int(ano))
            if mes:
                query = query.where("mes", "==", int(mes))
            if usuario:
                query = query.where("usuario_origem", "==", usuario.strip())
            if aprovador:
                query = query.where("aprovador", "==", aprovador.strip())

            if not ignore_limit:
                query = query.limit(20000)

            docs = list(query.stream())
        except Exception as e:
            from app.core.logging import get_logger
            get_logger(__name__).warning(f"Consulta nativa falhou (provável falta de índice composto): {e}. Usando fallback em memória.")
            # Fallback: Se a consulta complexa falhar, tentar carregar dados sem filtros nativos.
            fallback_query = COL_REQUESTS
            if not ignore_limit:
                fallback_query = fallback_query.limit(20000)
            docs = list(fallback_query.stream())

        data = []
        for doc in docs:
            d = doc.to_dict()
            
            # Filtros em memória (Seguros, não exigem índices)
            if ano or mes:
                try:
                    dt_str = d.get("data_solicitacao", "")
                    dt = datetime.fromisoformat(dt_str.split('T')[0])
                    if ano and dt.year != int(ano): continue
                    if mes and dt.month != int(mes): continue
                except Exception: continue

            # Fallback de filtros em memória se a query nativa falhou ou não cobriu todos os campos
            if aprovador and aprovador.upper().strip() != (d.get("aprovador") or "").upper().strip():
                continue
            if usuario and usuario.upper().strip() != (d.get("usuario_origem") or "").upper().strip():
                continue
            if status and status.upper().strip() != (d.get("status") or "").upper().strip():
                continue
                
            data.append(d)
            
        df = pd.DataFrame(data)
        if not df.empty:
            # Garantir tipos numéricos
            df["valor_solicitado"] = pd.to_numeric(df["valor_solicitado"], errors='coerce').fillna(0.0)
            df["valor_aprovado"] = pd.to_numeric(df["valor_aprovado"], errors='coerce').fillna(0.0)
            
        _REPORT_CACHE[cache_key] = {'time': now, 'data': df.copy()}
        return df.copy()

    def summary(
        self,
        data_inicio: date | None = None,
        data_fim: date | None = None,
        aprovador: str | None = None,
        usuario: str | None = None,
        status: str | None = None,
        ano: int | None = None,
        mes: int | None = None,
    ) -> SummaryReportOut:
        # Se for apenas um mês específico e sem outros filtros, podemos usar o fragmento de cache (muito rápido)
        is_monthly_fragment = ano and mes and not any([data_inicio, data_fim, aprovador, usuario, status])
        if is_monthly_fragment:
            doc = COL_SUMMARIES.document(f"month_{ano}_{mes}").get()
            if doc.exists:
                d = doc.to_dict()
                total_sol = Decimal(str(d["total_solicitado"]))
                total_app = Decimal(str(d["total_aprovado"]))
                total_reg = int(d["quantidade"])
                total_repro = Decimal(str(d["total_reprovado"]))
                total_glosa = Decimal(str(d.get("total_glosado", 0)))
                
                return SummaryReportOut(
                    total_registros=total_reg,
                    total_solicitado=(total_sol / 100).quantize(Decimal("0.01")),
                    total_aprovado=(total_app / 100).quantize(Decimal("0.01")),
                    total_reprovado=(total_repro / 100).quantize(Decimal("0.01")),
                    total_glosado=(total_glosa / 100).quantize(Decimal("0.01")),
                    diferenca_total=((total_sol - total_app) / 100).quantize(Decimal("0.01")),
                    ticket_medio_solicitado=(total_sol / Decimal(total_reg * 100) if total_reg > 0 else Decimal(0)).quantize(Decimal("0.01")),
                    ticket_medio_aprovado=(total_app / Decimal(total_reg * 100) if total_reg > 0 else Decimal(0)).quantize(Decimal("0.01"))
                )

        # Lógica de Fragmentos (Cache Ultra Rápido)
        is_default = not any([data_inicio, data_fim, aprovador, usuario, status, ano, mes])
        is_yearly_fragment = ano and not any([mes, data_inicio, data_fim, aprovador, usuario, status])
        
        if is_default or is_yearly_fragment:
            # Buscar todos os documentos de resumo (coleção summaries é pequena, scan é instantâneo)
            docs = COL_SUMMARIES.stream()
            
            total_sol = Decimal(0)
            total_app = Decimal(0)
            total_repro = Decimal(0)
            total_glosa = Decimal(0)
            total_reg = 0
            found_fragments = False
            
            for doc in docs:
                if doc.id.startswith("month_"):
                    d = doc.to_dict()
                    # Se for filtro de ano, ignorar meses de outros anos
                    if is_yearly_fragment and d.get("ano") != int(ano):
                        continue
                        
                    found_fragments = True
                    total_sol += Decimal(str(d.get("total_solicitado", 0))) / 100
                    total_app += Decimal(str(d.get("total_aprovado", 0))) / 100
                    total_repro += Decimal(str(d.get("total_reprovado", 0))) / 100
                    total_glosa += Decimal(str(d.get("total_glosado", 0))) / 100
                    total_reg += int(d.get("quantidade", 0))
            
            if found_fragments:
                diferenca = total_sol - total_app
                media_sol = total_sol / total_reg if total_reg > 0 else Decimal(0)
                media_app = total_app / total_reg if total_reg > 0 else Decimal(0)
                
                return SummaryReportOut(
                    total_registros=total_reg,
                    total_solicitado=total_sol.quantize(Decimal("0.01")),
                    total_aprovado=total_app.quantize(Decimal("0.01")),
                    total_reprovado=total_repro.quantize(Decimal("0.01")),
                    total_glosado=total_glosa.quantize(Decimal("0.01")),
                    diferenca_total=diferenca.quantize(Decimal("0.01")),
                    ticket_medio_solicitado=media_sol.quantize(Decimal("0.01")),
                    ticket_medio_aprovado=media_app.quantize(Decimal("0.01"))
                )

        df = self._get_base_query(data_inicio, data_fim, aprovador, usuario, status, ano, mes)
        if df.empty:
            return SummaryReportOut(total_registros=0, total_solicitado=Decimal(0), total_aprovado=Decimal(0), total_reprovado=Decimal(0), total_glosado=Decimal(0), diferenca_total=Decimal(0), ticket_medio_solicitado=Decimal(0), ticket_medio_aprovado=Decimal(0))

        # Calcular Glosa/Repro em tempo real
        df = self._prepare_dataframe(df)

        total_registros = len(df)
        total_solicitado = Decimal(str(df["valor_solicitado"].sum()))
        total_aprovado = Decimal(str(df["valor_aprovado"].sum()))
        total_reprovado = Decimal(str(df["valor_repro"].sum()))
        total_glosado = Decimal(str(df["valor_glosa"].sum()))

        media_solicitado = Decimal(str(df["valor_solicitado"].mean())) if total_registros > 0 else Decimal(0)
        media_aprovado = Decimal(str(df["valor_aprovado"].mean())) if total_registros > 0 else Decimal(0)

        result = SummaryReportOut(
            total_registros=total_registros,
            total_solicitado=total_solicitado.quantize(Decimal("0.01")),
            total_aprovado=total_aprovado.quantize(Decimal("0.01")),
            total_reprovado=total_reprovado.quantize(Decimal("0.01")),
            total_glosado=total_glosado.quantize(Decimal("0.01")),
            diferenca_total=(total_solicitado - total_aprovado).quantize(Decimal("0.01")),
            ticket_medio_solicitado=media_solicitado.quantize(Decimal("0.01")),
            ticket_medio_aprovado=media_aprovado.quantize(Decimal("0.01")),
        )
        
        if is_default:
            COL_SUMMARIES.document("default_summary").set({
                "total_registros": total_registros,
                "total_solicitado": int((total_solicitado * 100).to_integral_value()),
                "total_aprovado": int((total_aprovado * 100).to_integral_value()),
                "total_reprovado": int((total_reprovado * 100).to_integral_value()),
                "total_glosado": int((total_glosado * 100).to_integral_value()),
                "diferenca_total": int(((total_solicitado - total_aprovado) * 100).to_integral_value()),
                "ticket_medio_solicitado": int((media_solicitado * 100).to_integral_value()),
                "ticket_medio_aprovado": int((media_aprovado * 100).to_integral_value()),
                "updated_at": datetime.now(timezone.utc)
            })
        return result

    def monthly(
        self,
        data_inicio: date | None = None,
        data_fim: date | None = None,
        aprovador: str | None = None,
        usuario: str | None = None,
        status: str | None = None,
        ano: int | None = None,
        mes: int | None = None,
        sort_by: str = "ano",
        order: str = "desc"
    ) -> list[MonthlyReportRow]:
        # Mapeamento de colunas para ordenação (casamento com o schema)
        sort_map = {
            "ano": "ano",
            "mes": "mes",
            "quantidade": "quantidade",
            "total_solicitado": "total_solicitado",
            "total_aprovado": "total_aprovado",
            "total_glosado": "total_glosado",
            "total_reprovado": "total_reprovado"
        }
        target_sort = sort_map.get(sort_by, "ano")
        is_asc = order.lower() == "asc"

        # Tentar carregar dos fragmentos de cache se não houver filtros complexos
        is_standard = not any([data_inicio, data_fim, aprovador, usuario, status])
        
        if is_standard:
            # Buscar todos os documentos de resumo
            docs = COL_SUMMARIES.stream() 
            
            cached_months = []
            for doc in docs:
                if doc.id.startswith("month_"):
                    d = doc.to_dict()
                    # Filtrar pelo ano se solicitado
                    if ano and d.get("ano") != int(ano):
                        continue
                    # Filtrar pelo mes se solicitado (novo)
                    if mes and d.get("mes") != int(mes):
                        continue
                    cached_months.append(MonthlyReportRow(
                        ano=d["ano"],
                        mes=d["mes"],
                        quantidade=d["quantidade"],
                        total_solicitado=(Decimal(str(d["total_solicitado"])) / 100).quantize(Decimal("0.01")),
                        total_aprovado=(Decimal(str(d["total_aprovado"])) / 100).quantize(Decimal("0.01")),
                        total_reprovado=(Decimal(str(d["total_reprovado"])) / 100).quantize(Decimal("0.01")),
                        total_glosado=(Decimal(str(d.get("total_glosado", 0))) / 100).quantize(Decimal("0.01"))
                    ))
            
            if cached_months:
                return sorted(cached_months, key=lambda x: (getattr(x, target_sort), x.mes if target_sort == "ano" else 0), reverse=not is_asc)

        # Fallback: Processamento completo se houver filtros ou cache vazio
        df = self._get_base_query(data_inicio, data_fim, aprovador, usuario, status, ano, mes)
        if df.empty: 
            return []

        # Preparar dados em tempo real
        df = self._prepare_dataframe(df)
        df["data_dt"] = pd.to_datetime(df["data_solicitacao"], errors='coerce')
        df = df.dropna(subset=["data_dt"])
        if df.empty: return []

        df["ano_val"] = df["data_dt"].dt.year
        df["mes_val"] = df["data_dt"].dt.month

        # Mapeamento para o DataFrame
        df_sort_map = {
            "ano": "ano_val",
            "mes": "mes_val",
            "quantidade": "data_dt",
            "total_solicitado": "valor_solicitado",
            "total_aprovado": "valor_aprovado",
            "total_glosado": "valor_glosa",
            "total_reprovado": "valor_repro"
        }
        df_sort_col = df_sort_map.get(sort_by, "ano_val")

        grouped = df.groupby(["ano_val", "mes_val"]).agg({
            "valor_solicitado": "sum",
            "valor_aprovado": "sum",
            "valor_repro": "sum",
            "valor_glosa": "sum",
            "data_dt": "count"
        }).reset_index().sort_values([df_sort_col, "mes_val" if df_sort_col == "ano_val" else df_sort_col], ascending=is_asc)

        result = []
        for _, row in grouped.iterrows():
            result.append(MonthlyReportRow(
                ano=int(row["ano_val"]),
                mes=int(row["mes_val"]),
                quantidade=int(row["data_dt"]),
                total_solicitado=Decimal(str(row["valor_solicitado"])).quantize(Decimal("0.01")),
                total_aprovado=Decimal(str(row["valor_aprovado"])).quantize(Decimal("0.01")),
                total_reprovado=Decimal(str(row["valor_repro"])).quantize(Decimal("0.01")),
                total_glosado=Decimal(str(row["valor_glosa"])).quantize(Decimal("0.01"))
            ))
        return result

    def top_users(self, limit=20, sort_by: str = "total_solicitado", order: str = "desc", **kwargs) -> list[TopUserReportRow]:
        try:
            df = self._get_base_query(**kwargs)
            if df.empty: return []

            # Calcular em tempo real
            df = self._prepare_dataframe(df)

            grouped = df.groupby("usuario_origem").agg({
                "id_alocacao": "count",
                "valor_solicitado": "sum",
                "valor_aprovado": "sum",
                "valor_repro": "sum",
                "valor_glosa": "sum"
            }).reset_index()

            # Mapeamento de ordenação para o DataFrame
            df_sort_map = {
                "usuario_origem": "usuario_origem",
                "quantidade": "id_alocacao",
                "total_solicitado": "valor_solicitado",
                "total_aprovado": "valor_aprovado",
                "total_reprovado": "valor_repro",
                "total_glosado": "valor_glosa"
            }
            df_sort_col = df_sort_map.get(sort_by, "valor_solicitado")
            is_asc = order.lower() == "asc"

            grouped = grouped.sort_values(df_sort_col, ascending=is_asc).head(limit)
            
            result = []
            for _, row in grouped.iterrows():
                result.append(TopUserReportRow(
                    usuario_origem=row["usuario_origem"],
                    quantidade=int(row["id_alocacao"]),
                    total_solicitado=Decimal(str(row["valor_solicitado"])).quantize(Decimal("0.01")),
                    total_aprovado=Decimal(str(row["valor_aprovado"])).quantize(Decimal("0.01")),
                    total_reprovado=Decimal(str(row["valor_repro"])).quantize(Decimal("0.01")),
                    total_glosado=Decimal(str(row["valor_glosa"])).quantize(Decimal("0.01"))
                ))
            return result
        except Exception as e:
            from app.core.logging import get_logger
            get_logger(__name__).error(f"Erro em top_users: {e}", exc_info=True)
            raise e


    def daily(self, year: int, month: int, **kwargs):
        # Tentar carregar dos fragmentos diários se não houver filtros complexos
        is_standard = not any([kwargs.get('data_inicio'), kwargs.get('data_fim'), kwargs.get('aprovador'), kwargs.get('usuario'), kwargs.get('status')])
        
        if is_standard:
            # Buscar todos os documentos de resumo (coleção pequena, filtrar em memória é eficiente e evita índices)
            docs = COL_SUMMARIES.stream()
            
            cached_days = []
            for doc in docs:
                if doc.id.startswith(f"day_{year}_{month}_"):
                    d = doc.to_dict()
                    cached_days.append({
                        "dia": d.get("dia"),
                        "total_solicitado": d.get("total_solicitado", 0) / 100.0,
                        "total_aprovado": d.get("total_aprovado", 0) / 100.0,
                        "total_reprovado": d.get("total_reprovado", 0) / 100.0,
                        "total_glosado": d.get("total_glosado", 0) / 100.0,
                        "quantidade": d.get("quantidade", 0)
                    })
            
            if cached_days:
                return sorted(cached_days, key=lambda x: x["dia"])

        # Fallback: Processamento completo se houver filtros ou cache vazio
        kwargs['ano'] = year
        kwargs['mes'] = month
        df = self._get_base_query(**kwargs)
        if df.empty: return []
        
        df["data_dt"] = pd.to_datetime(df["data_solicitacao"], errors='coerce')
        df = df.dropna(subset=["data_dt"])
        
        mask = (df["data_dt"].dt.year == int(year)) & (df["data_dt"].dt.month == int(month))
        df_month = df[mask].copy()
        
        if df_month.empty: return []
        
        df_month["dia"] = df_month["data_dt"].dt.day
        
        # Calcular em tempo real
        df_month = self._prepare_dataframe(df_month)

        grouped = df_month.groupby("dia").agg({
            "valor_solicitado": "sum",
            "valor_aprovado": "sum",
            "valor_repro": "sum",
            "valor_glosa": "sum",
            "id_alocacao": "count"
        }).reset_index().sort_values("dia")
        
        # Renomear para o padrão esperado pelo frontend
        grouped = grouped.rename(columns={
            "valor_solicitado": "total_solicitado",
            "valor_aprovado": "total_aprovado",
            "valor_repro": "total_reprovado",
            "valor_glosa": "total_glosado",
            "id_alocacao": "quantidade"
        })
        
        return grouped.to_dict(orient="records")

    def get_filter_options(self):
        cache_doc = COL_SUMMARIES.document("default_filters").get()
        if cache_doc.exists:
            data_full = cache_doc.to_dict()
            data = data_full.get("data", {})
            updated_at = data_full.get("updated_at")
            
            # Só usa cache se tiver os campos novos (anos) e estiver no TTL
            if "anos" in data and updated_at:
                if (datetime.now() - updated_at.replace(tzinfo=None)).total_seconds() < _CACHE_TTL:
                    return data

        # Fallback: scan Firestore
        docs = COL_REQUESTS.select(["usuario_origem", "aprovador", "data_solicitacao"]).stream()
        users = set()
        approvers = set()
        years = set()
        
        count = 0
        for doc in docs:
            count += 1
            d = doc.to_dict()
            u = d.get("usuario_origem")
            a = d.get("aprovador")
            dt_str = d.get("data_solicitacao")
            
            if u: users.add(u.strip())
            if a: approvers.add(a.strip())
            if dt_str:
                try:
                    # Tentar parsear ISO format ou string simples
                    y = datetime.fromisoformat(dt_str.split('T')[0]).year
                    years.add(y)
                except: pass

        result = {
            "aprovadores": sorted([x for x in approvers if x]),
            "usuarios": sorted([x for x in users if x]),
            "anos": sorted(list(years), reverse=True)
        }
        
        from app.core.logging import get_logger
        get_logger(__name__).info(f"Filtros reconstruídos. Processados {count} docs. Encontrados: {len(users)} usuários, {len(approvers)} aprovadores, {len(years)} anos.")
        
        COL_SUMMARIES.document("default_filters").set({
            "data": result,
            "updated_at": datetime.now(timezone.utc)
        })
        return result

    def export_csv(self, output_dir: Path, **kwargs) -> Path:
        from app.services.export_service import ExportService
        df = self._get_base_query(**kwargs)
        df = self._prepare_dataframe(df)
        return ExportService.export_csv(
            df, output_dir, 
            sort_by=kwargs.get("sort_by", "data_solicitacao"),
            order=kwargs.get("order", "asc")
        )

    def export_xlsx(self, output_dir: Path, **kwargs) -> Path:
        from app.services.export_service import ExportService
        df = self._get_base_query(**kwargs)
        df = self._prepare_dataframe(df)
        return ExportService.export_xlsx(
            df, output_dir, 
            sort_by=kwargs.get("sort_by", "data_solicitacao"),
            order=kwargs.get("order", "asc")
        )

    def export_pdf(self, output_dir: Path, **kwargs) -> Path:
        from app.services.export_service import ExportService
        df = self._get_base_query(**kwargs)
        df = self._prepare_dataframe(df)
        return ExportService.export_pdf(
            df, output_dir, 
            sort_by=kwargs.get("sort_by", "data_solicitacao"),
            order=kwargs.get("order", "asc")
        )
