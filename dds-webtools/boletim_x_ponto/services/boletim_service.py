# d:\programas\DDS\dds-webtools\boletim_x_ponto\services\boletim_service.py
from __future__ import annotations
import csv
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
import pandas as pd

from boletim_x_ponto.services.constantes import HEADERS_VIZ, MAP_BOL, MAP_PTO
from boletim_x_ponto.services.dataframe_utils import (
    resolver_base_ponto,
    preparar_df_ponto_para_comparacao,
    preparar_df_boletim_para_comparacao,
    normalizar_df_boletim,
    normalizar_df_ponto,
)
from boletim_x_ponto.services.comparacao import montar_triplet_comparacao, montar_tres_grids, map_boletim_por_data
from boletim_x_ponto.services.leitor_pdf import extrair_dados_pdf, parse_horas_funcionarios, extrair_var_dataset
from boletim_x_ponto.services.leitor_ponto import extrair_ponto_dataframe

class BoletimXPontoService:
    def __init__(self):
        self.tipos_texto_boletim = ["BOLETIM", "Contrato", "Registro", "Funcionário"]
        self.tipos_data_boletim = ["DATA", "Data de Medição"]

        self.df_relacao_nomes = pd.DataFrame()

        self.load_data()

    @property
    def parent_doc_ref(self):
        from monitor.services.firestore_client import db
        return db.collection("webtools").document("boletim_x_ponto")

    def load_data(self):
        try:
            docs = self.parent_doc_ref.collection("mappings").stream()
            records = [doc.to_dict() for doc in docs]
            self.df_relacao_nomes = pd.DataFrame(records)
            self.df_relacao_nomes = self._sanear_relacao_nomes(self.df_relacao_nomes)
        except Exception as e:
            print(f"[ERRO] Falha ao carregar mappings do Firestore: {e}")
            self.df_relacao_nomes = self._sanear_relacao_nomes(None)

    def _criar_empty_boletim_df(self) -> pd.DataFrame:
        cols = self.tipos_texto_boletim + self.tipos_data_boletim + [
            "SERV.", "KM", "HORA NORMAL", "H.E.", "H.E.D.", "H.E.N.", "H.E.N.D.", "S.A.", "H.N.", "DESLOC.", "PROD."
        ]
        df = pd.DataFrame(columns=cols)
        return self._padronizar_tipos_boletim(df)

    def _criar_empty_ponto_df(self) -> pd.DataFrame:
        cols = [
            "Nome", "CPF", "PIS", "Data", "Total Normais", "Total Noturno",
            "Extra 50%D", "Extra 100%D", "Extra 50%N", "Extra 100%N", "Interjornada", "chave_unica"
        ]
        return pd.DataFrame(columns=cols)

    def _criar_empty_var_df(self) -> pd.DataFrame:
        cols = [
            "contrato", "boletim", "data_medicao", "valor_us", "var_code", "termo", "descrição", "US", "qtde",
            "competencia", "us_global", "_chave"
        ]
        return pd.DataFrame(columns=cols)

    def _sanear_relacao_nomes(self, df: pd.DataFrame | None) -> pd.DataFrame:
        cols = ["Nome_Boletim", "Nome_Ponto_Mapeado", "CPF_Ponto", "PIS_Ponto"]
        if df is None or df.empty:
            return pd.DataFrame({c: [] for c in cols})
        
        # Garante que colunas mínimas existem
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        
        df = df.drop_duplicates(subset=["Nome_Boletim"], keep="last").copy()
        for c in cols:
            df[c] = df[c].astype(str).fillna("").str.strip()
        return df[cols]

    def _padronizar_tipos_boletim(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in self.tipos_texto_boletim:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        for col in self.tipos_data_boletim:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
        
        non_text_date = [c for c in df.columns if c not in self.tipos_texto_boletim + self.tipos_data_boletim]
        for col in non_text_date:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        return df

    def _criar_chave_unica_boletim(self, df: pd.DataFrame) -> pd.Series:
        df_temp = df.copy()
        df_temp["DATA_STR"] = pd.to_datetime(df_temp["DATA"], errors="coerce").dt.strftime("%Y-%m-%d")
        return (
            df_temp["BOLETIM"].astype(str).str.strip()
            + "__"
            + df_temp["DATA_STR"]
            + "__"
            + df_temp["Funcionário"].astype(str).str.strip().str.upper()
        )

    def get_date_limits(self) -> Tuple[str, str]:
        try:
            meta = self.parent_doc_ref.get()
            if meta.exists:
                data = meta.to_dict()
                return data.get("data_min", "2026-05-21"), data.get("data_max", "2026-05-21")
        except Exception as e:
            print(f"[ERRO] Falha ao obter limites de data do Firestore: {e}")
        
        today = pd.Timestamp.now().strftime("%Y-%m-%d")
        return today, today

    def get_contracts(self) -> List[str]:
        try:
            meta = self.parent_doc_ref.get()
            if meta.exists:
                data = meta.to_dict()
                return data.get("contratos", [])
        except Exception as e:
            print(f"[ERRO] Falha ao obter contratos do Firestore: {e}")
        return []

    def get_employees(self, data_ini: str, data_fim: str, contrato: str | None = None) -> List[str]:
        try:
            di = pd.to_datetime(data_ini).strftime("%Y-%m-%d")
            dfim = pd.to_datetime(data_fim).strftime("%Y-%m-%d")
            
            query = self.parent_doc_ref.collection("boletins") \
                      .where("DATA", ">=", di) \
                      .where("DATA", "<=", dfim)
            if contrato:
                query = query.where("Contrato", "==", contrato)
            
            docs = query.select(["`Funcionário`"]).stream()
            funcs = set()
            for doc in docs:
                f = doc.get("Funcionário")
                if f:
                    funcs.add(str(f).strip())
            return sorted(list(funcs))
        except Exception as e:
            print(f"[ERRO] Falha ao obter funcionários do Firestore: {e}")
            return []

    def _get_employee_dataframes(self, employee: str, data_ini: str, data_fim: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        di = pd.to_datetime(data_ini).strftime("%Y-%m-%d")
        dfim = pd.to_datetime(data_fim).strftime("%Y-%m-%d")
        
        # 1. Boletim DataFrame
        docs_b = self.parent_doc_ref.collection("boletins") \
                   .where("Funcionário", "==", employee) \
                   .where("DATA", ">=", di) \
                   .where("DATA", "<=", dfim) \
                   .stream()
        records_b = [doc.to_dict() for doc in docs_b]
        df_b = pd.DataFrame(records_b)
        if df_b.empty:
            df_b = self._criar_empty_boletim_df()
        else:
            df_b = self._padronizar_tipos_boletim(df_b)
            
        # 2. Ponto DataFrame
        cpf = None
        pis = None
        nome_map = None
        
        if not self.df_relacao_nomes.empty:
            rel = self.df_relacao_nomes[self.df_relacao_nomes["Nome_Boletim"] == employee]
            if not rel.empty:
                r = rel.iloc[0]
                cpf = str(r.get("CPF_Ponto") or "").strip()
                pis = str(r.get("PIS_Ponto") or "").strip()
                nome_map = str(r.get("Nome_Ponto_Mapeado") or "").strip()
        
        records_p = []
        if cpf:
            docs_p = self.parent_doc_ref.collection("ponto") \
                       .where("CPF", "==", cpf) \
                       .where("Data", ">=", di) \
                       .where("Data", "<=", dfim) \
                       .stream()
            records_p = [doc.to_dict() for doc in docs_p]
        elif pis:
            docs_p = self.parent_doc_ref.collection("ponto") \
                       .where("PIS", "==", pis) \
                       .where("Data", ">=", di) \
                       .where("Data", "<=", dfim) \
                       .stream()
            records_p = [doc.to_dict() for doc in docs_p]
        elif nome_map:
            docs_p = self.parent_doc_ref.collection("ponto") \
                       .where("Nome", "==", nome_map) \
                       .where("Data", ">=", di) \
                       .where("Data", "<=", dfim) \
                       .stream()
            records_p = [doc.to_dict() for doc in docs_p]
        else:
            from difflib import get_close_matches
            meta = self.parent_doc_ref.get()
            if meta.exists:
                nomes_ponto = meta.to_dict().get("nomes_ponto", [])
                match = get_close_matches(str(employee).upper(), [n.upper() for n in nomes_ponto], n=1, cutoff=0.75)
                if match:
                    nome_real = next((n for n in nomes_ponto if n.upper() == match[0]), None)
                    if nome_real:
                        docs_p = self.parent_doc_ref.collection("ponto") \
                                   .where("Nome", "==", nome_real) \
                                   .where("Data", ">=", di) \
                                   .where("Data", "<=", dfim) \
                                   .stream()
                        records_p = [doc.to_dict() for doc in docs_p]
                        
        df_p = pd.DataFrame(records_p)
        if df_p.empty:
            df_p = self._criar_empty_ponto_df()
        else:
            df_p["Data"] = pd.to_datetime(df_p["Data"], errors="coerce")
            df_p = df_p[df_p["Data"].notna()].copy()
            
        return df_b, df_p

    def get_comparison_grids(self, employee: str, data_ini: str, data_fim: str, format: str = "decimal") -> Dict[str, Any]:
        di = pd.to_datetime(data_ini)
        dfim = pd.to_datetime(data_fim)
        di_str = di.strftime("%Y-%m-%d")
        dfim_str = dfim.strftime("%Y-%m-%d")
        
        df_b_emp, df_p_emp = self._get_employee_dataframes(employee, di_str, dfim_str)
        
        df_b_f, df_p_f, df_d, registro, boletins_set, sem_ponto = montar_triplet_comparacao(
            df_b_emp, df_p_emp, self.df_relacao_nomes, employee, di, dfim
        )

        dates_mes = pd.date_range(di, dfim, freq="D").strftime("%d/%m/%Y").tolist()
        bol_map = map_boletim_por_data(df_b_emp, employee, di, dfim)

        grid_b, grid_p, grid_d, headers_vis = montar_tres_grids(
            dates_mes, df_b_f, df_p_f, df_d, bol_map
        )

        # Se format for HH:MM, precisamos formatar os grids de decimal para HH:MM
        exibir_hhmm = (format.lower() == "hhmm")
        if exibir_hhmm:
            # Re-formata grids para exibir como horas
            grid_b_hhmm = []
            grid_p_hhmm = []
            grid_d_hhmm = []
            for row in grid_b:
                new_row = row[:2]
                for val in row[2:]:
                    new_row.append(self._decimal_to_hhmm_str(val))
                grid_b_hhmm.append(new_row)
            for row in grid_p:
                new_row = [row[0]]
                for val in row[1:]:
                    new_row.append(self._decimal_to_hhmm_str(val))
                grid_p_hhmm.append(new_row)
            for row in grid_d:
                new_row = [row[0]]
                for val in row[1:]:
                    new_row.append(self._decimal_to_hhmm_str(val))
                grid_d_hhmm.append(new_row)
            grid_b, grid_p, grid_d = grid_b_hhmm, grid_p_hhmm, grid_d_hhmm

        # Calcula totais
        totais_b = ["TOTAIS", ""]
        totais_p = ["TOTAIS"]
        totais_d = ["TOTAIS"]

        # Soma colunas
        def somar_col(grid, start_idx):
            cols_count = len(grid[0]) if grid else 0
            tots = []
            for col_idx in range(start_idx, cols_count):
                vals = []
                for row in grid:
                    v = row[col_idx]
                    if v not in ("", "-", None):
                        try:
                            if exibir_hhmm:
                                v_dec = self._hhmm_to_decimal(v)
                            else:
                                v_dec = float(str(v).replace(",", "."))
                            if v_dec:
                                vals.append(v_dec)
                        except:
                            pass
                total_soma = sum(vals)
                if exibir_hhmm:
                    tots.append(self._decimal_to_hhmm_str(total_soma))
                else:
                    tots.append(f"{total_soma:.2f}".replace(".", ","))
            return tots

        if grid_b:
            totais_b += somar_col(grid_b, 2)
        if grid_p:
            totais_p += somar_col(grid_p, 1)
        if grid_d:
            totais_d += somar_col(grid_d, 1)

        return {
            "headers": headers_vis,
            "grid_boletim": grid_b,
            "grid_ponto": grid_p,
            "grid_diferenca": grid_d,
            "totais_boletim": totais_b,
            "totais_ponto": totais_p,
            "totais_diferenca": totais_d,
            "registro": registro or "-",
            "boletins": sorted(list(boletins_set)),
            "sem_ponto": sem_ponto
        }

    def _decimal_to_hhmm_str(self, val: Any) -> str:
        if val in ("", "-", None):
            return ""
        try:
            v = float(str(val).replace(",", "."))
            if abs(v) < 1e-9:
                return "0:00"
            neg = v < 0
            v = abs(v)
            h = int(v)
            m = int(round((v - h) * 60))
            if m >= 60:
                h += 1
                m -= 60
            s = f"{h}:{m:02d}"
            return f"-{s}" if neg else s
        except:
            return str(val)

    def _hhmm_to_decimal(self, s: str) -> float:
        if not s or s.strip() == "":
            return 0.0
        s = s.strip()
        neg = s.startswith("-")
        if neg:
            s = s[1:]
        if ":" in s:
            try:
                h, m = s.split(":", 1)
                dec = int(h) + int(m) / 60.0
                return -dec if neg else dec
            except:
                return 0.0
        try:
            val = float(s.replace(",", "."))
            return -val if neg else val
        except:
            return 0.0

    def get_name_mapping(self) -> List[Dict[str, str]]:
        return self.df_relacao_nomes.to_dict(orient="records")

    def update_name_mapping(self, nome_boletim: str, nome_ponto_mapeado: str, cpf_ponto: str, pis_ponto: str):
        nome_boletim = str(nome_boletim).strip()
        nome_ponto_mapeado = str(nome_ponto_mapeado).strip()
        cpf_ponto = str(cpf_ponto).strip()
        pis_ponto = str(pis_ponto).strip()
        
        doc_ref = self.parent_doc_ref.collection("mappings").document(nome_boletim)
        doc_ref.set({
            "Nome_Boletim": nome_boletim,
            "Nome_Ponto_Mapeado": nome_ponto_mapeado,
            "CPF_Ponto": cpf_ponto,
            "PIS_Ponto": pis_ponto
        })
        
        # Reload mappings
        self.load_data()

    def get_boletins_df(self, lista_contratos: List[str], dt_ini: str, dt_fim: str) -> pd.DataFrame:
        di = pd.to_datetime(dt_ini).strftime("%Y-%m-%d")
        dfim = pd.to_datetime(dt_fim).strftime("%Y-%m-%d")
        
        records = []
        chunk_size = 30
        for i in range(0, len(lista_contratos), chunk_size):
            chunk = lista_contratos[i:i + chunk_size]
            query = self.parent_doc_ref.collection("boletins") \
                      .where("Contrato", "in", chunk) \
                      .where("DATA", ">=", di) \
                      .where("DATA", "<=", dfim)
            docs = query.stream()
            records.extend([doc.to_dict() for doc in docs])
            
        df = pd.DataFrame(records)
        if df.empty:
            return self._criar_empty_boletim_df()
            
        return self._padronizar_tipos_boletim(df)

    def upload_boletim(self, file_bytes: bytes, filename: str) -> int:
        texto, cabecalho = extrair_dados_pdf(file_bytes)
        boletim = str(cabecalho.get("BOLETIM", "")).strip()
        if not boletim:
            raise ValueError(f"Não foi possível extrair o número do boletim do arquivo: {filename}")

        df = parse_horas_funcionarios(texto)
        if df is None or df.empty:
            return 0

        df["BOLETIM"] = boletim
        df["Data de Medição"] = cabecalho.get("Data de Medição")
        df["Contrato"] = cabecalho.get("Contrato")

        df = self._padronizar_tipos_boletim(df)
        df = df.rename(columns={
            "HN": "H.N.", "HE": "H.E.", "HED": "H.E.D.", "HEN": "H.E.N.", "HEND": "H.E.N.D.", "SA": "S.A."
        })
        
        df = df.dropna(subset=["DATA", "Funcionário"])
        df["chave_unica"] = self._criar_chave_unica_boletim(df)

        from monitor.services.firestore_client import db
        df = df.drop_duplicates(subset=["chave_unica"])
        keys = df["chave_unica"].tolist()
        doc_refs = [self.parent_doc_ref.collection("boletins").document(k) for k in keys]
        
        existentes_set = set()
        chunk_size = 500
        for i in range(0, len(doc_refs), chunk_size):
            chunk_refs = doc_refs[i:i + chunk_size]
            snapshots = db.get_all(chunk_refs)
            for snap in snapshots:
                if snap.exists:
                    existentes_set.add(snap.id)
                    
        novos_df = df[~df["chave_unica"].isin(existentes_set)].copy()
        novos_count = len(novos_df)
        
        def clean_dict_local(d: dict) -> dict:
            cleaned = {}
            for k, v in d.items():
                if pd.isna(v):
                    cleaned[k] = None
                elif isinstance(v, (pd.Timestamp, pd.DatetimeTZDtype)):
                    cleaned[k] = v.strftime("%Y-%m-%d")
                else:
                    cleaned[k] = v
            return cleaned

        if novos_count > 0:
            batch = db.batch()
            count = 0
            for _, row in novos_df.iterrows():
                record = clean_dict_local(row.to_dict())
                ref = self.parent_doc_ref.collection("boletins").document(record["chave_unica"])
                batch.set(ref, record)
                count += 1
                if count >= 500:
                    batch.commit()
                    batch = db.batch()
                    count = 0
            if count > 0:
                batch.commit()

            # Update metadata document
            try:
                meta_ref = self.parent_doc_ref
                meta_snap = meta_ref.get()
                
                new_contracts = set(novos_df["Contrato"].dropna().unique())
                new_employees = set(novos_df["Funcionário"].dropna().unique())
                new_dates = pd.to_datetime(novos_df["DATA"], errors="coerce").dt.strftime("%Y-%m-%d").dropna().tolist()
                
                if meta_snap.exists:
                    meta_data = meta_snap.to_dict()
                    current_contracts = set(meta_data.get("contratos", []))
                    current_employees = set(meta_data.get("funcionarios_boletim", []))
                    current_min = meta_data.get("data_min", "2026-05-21")
                    current_max = meta_data.get("data_max", "2026-05-21")
                    
                    all_contracts = sorted(list(current_contracts | new_contracts))
                    all_employees = sorted(list(current_employees | new_employees))
                    all_dates = new_dates + [current_min, current_max]
                    all_dates = [d for d in all_dates if d]
                    data_min = min(all_dates) if all_dates else current_min
                    data_max = max(all_dates) if all_dates else current_max
                    
                    meta_ref.update({
                        "contratos": all_contracts,
                        "funcionarios_boletim": all_employees,
                        "data_min": data_min,
                        "data_max": data_max
                    })
            except Exception as em:
                print(f"[AVISO] Falha ao atualizar metadados do Boletim: {em}")

        # Atualiza relação contrato x boletim no Firestore
        contrato = cabecalho.get("Contrato")
        data_medicao = cabecalho.get("Data de Medição")
        if contrato and data_medicao:
            self._persistir_relacao_contrato_boletim(contrato, boletim, data_medicao)

        # Processa e persiste boletim_var no Firestore
        try:
            dfv = extrair_var_dataset(file_bytes, set_arquivo=None, incluir_termo=True)
            if dfv is not None and not dfv.empty:
                dfv = dfv.copy()
                dfv["data_medicao"] = pd.to_datetime(dfv["data_medicao"], errors="coerce", dayfirst=True)
                dfv["competencia"] = dfv["data_medicao"].dt.strftime("%Y-%m")
                for c in ["contrato", "boletim", "var_code", "descrição", "termo", "competencia"]:
                    if c in dfv.columns:
                        dfv[c] = dfv[c].astype("string").str.strip()
                for c in ["US", "qtde", "valor_us"]:
                    if c in dfv.columns:
                        dfv[c] = pd.to_numeric(dfv[c], errors="coerce").astype("float64")
                dfv["us_global"] = dfv["valor_us"].astype("float64")
                dfv["_chave"] = (
                    dfv["boletim"].fillna("").astype(str) + "|" +
                    dfv["competencia"].fillna("").astype(str) + "|" +
                    dfv["var_code"].fillna("").astype(str) + "|" +
                    dfv["US"].fillna(pd.NA).astype(str) + "|" +
                    dfv["qtde"].fillna(pd.NA).astype(str)
                ).astype("string")

                dfv = dfv.drop_duplicates(subset=["_chave"])
                keys = dfv["_chave"].tolist()
                doc_refs = [self.parent_doc_ref.collection("vars").document(k) for k in keys]
                
                existentes_set = set()
                chunk_size = 500
                for i in range(0, len(doc_refs), chunk_size):
                    chunk_refs = doc_refs[i:i + chunk_size]
                    snapshots = db.get_all(chunk_refs)
                    for snap in snapshots:
                        if snap.exists:
                            existentes_set.add(snap.id)
                            
                novos_dfv = dfv[~dfv["_chave"].isin(existentes_set)].copy()
                if not novos_dfv.empty:
                    batch = db.batch()
                    count = 0
                    for _, row in novos_dfv.iterrows():
                        record = clean_dict_local(row.to_dict())
                        ref = self.parent_doc_ref.collection("vars").document(record["_chave"])
                        batch.set(ref, record)
                        count += 1
                        if count >= 500:
                            batch.commit()
                            batch = db.batch()
                            count = 0
                    if count > 0:
                        batch.commit()
        except Exception as ev:
            print(f"[AVISO] Falha ao processar boletim_var: {ev}")

        return novos_count

    def _persistir_relacao_contrato_boletim(self, contrato: str, boletim: str, data_medicao: Any):
        contrato = str(contrato).strip()
        boletim = str(boletim).strip()
        
        data_str = ""
        if data_medicao:
            try:
                data_str = pd.to_datetime(data_medicao, errors="coerce", dayfirst=True).date().isoformat()
            except:
                data_str = str(data_medicao)

        doc_id = f"{contrato}__{boletim}"
        try:
            self.parent_doc_ref.collection("contrato_boletim").document(doc_id).set({
                "contrato": contrato,
                "boletim": boletim,
                "data_medicao": data_str
            })
        except Exception as e:
            print(f"[ERRO] Falha ao salvar relação contrato-boletim no Firestore: {e}")

    def upload_ponto(self, file_bytes: bytes, filename: str) -> int:
        df = extrair_ponto_dataframe(file_bytes, filename)
        if df is None or df.empty:
            return 0

        # Converte coluna Data para datetime
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
        df = df[df["Data"].notna()].copy()

        def get_ponto_key(row):
            cpf = str(row.get("CPF", "")).strip()
            pis = str(row.get("PIS", "")).strip()
            d_str = row["Data"].strftime("%Y-%m-%d")
            return f"{cpf}__{d_str}" if cpf else f"{pis}__{d_str}"

        df["chave_unica"] = df.apply(get_ponto_key, axis=1)
        df = df.drop_duplicates(subset=["chave_unica"])

        from monitor.services.firestore_client import db
        keys = df["chave_unica"].tolist()
        doc_refs = [self.parent_doc_ref.collection("ponto").document(k) for k in keys]
        
        existentes_set = set()
        chunk_size = 500
        for i in range(0, len(doc_refs), chunk_size):
            chunk_refs = doc_refs[i:i + chunk_size]
            snapshots = db.get_all(chunk_refs)
            for snap in snapshots:
                if snap.exists:
                    existentes_set.add(snap.id)
                    
        novos_df = df[~df["chave_unica"].isin(existentes_set)].copy()
        novos_count = len(novos_df)
        
        def clean_dict_local(d: dict) -> dict:
            cleaned = {}
            for k, v in d.items():
                if pd.isna(v):
                    cleaned[k] = None
                elif isinstance(v, (pd.Timestamp, pd.DatetimeTZDtype)):
                    cleaned[k] = v.strftime("%Y-%m-%d")
                else:
                    cleaned[k] = v
            return cleaned

        if novos_count > 0:
            batch = db.batch()
            count = 0
            for _, row in novos_df.iterrows():
                record = clean_dict_local(row.to_dict())
                ref = self.parent_doc_ref.collection("ponto").document(record["chave_unica"])
                batch.set(ref, record)
                count += 1
                if count >= 500:
                    batch.commit()
                    batch = db.batch()
                    count = 0
            if count > 0:
                batch.commit()

            # Update metadata document
            try:
                meta_ref = self.parent_doc_ref
                meta_snap = meta_ref.get()
                
                new_names = set(novos_df["Nome"].dropna().unique())
                new_dates = pd.to_datetime(novos_df["Data"], errors="coerce").dt.strftime("%Y-%m-%d").dropna().tolist()
                
                if meta_snap.exists:
                    meta_data = meta_snap.to_dict()
                    current_names = set(meta_data.get("nomes_ponto", []))
                    current_min = meta_data.get("data_min", "2026-05-21")
                    current_max = meta_data.get("data_max", "2026-05-21")
                    
                    all_names = sorted(list(current_names | new_names))
                    all_dates = new_dates + [current_min, current_max]
                    all_dates = [d for d in all_dates if d]
                    data_min = min(all_dates) if all_dates else current_min
                    data_max = max(all_dates) if all_dates else current_max
                    
                    meta_ref.update({
                        "nomes_ponto": all_names,
                        "data_min": data_min,
                        "data_max": data_max
                    })
            except Exception as em:
                print(f"[AVISO] Falha ao atualizar metadados do Ponto: {em}")
                
        return novos_count

    def calcular_totais_funcionario(self, funcionario_nome: str, data_ini: str | pd.Timestamp, data_fim: str | pd.Timestamp) -> Dict[str, Any] | None:
        try:
            dt_ini = pd.to_datetime(data_ini)
            dt_fim = pd.to_datetime(data_fim)
            di_str = dt_ini.strftime("%Y-%m-%d")
            dfim_str = dt_fim.strftime("%Y-%m-%d")

            df_boletim_func, df_ponto_func = self._get_employee_dataframes(funcionario_nome, di_str, dfim_str)

            if df_boletim_func.empty and df_ponto_func.empty:
                return None

            campos = {
                "HORA_NORMAL": ("HORA NORMAL", "Total Normais"),
                "HORA_NOTURNA": ("H.N.", "Total Noturno"),
                "EXTRA_50_D": ("H.E.", "Extra 50%D"),
                "EXTRA_100_D": ("H.E.D.", "Extra 100%D"),
                "EXTRA_50_N": ("H.E.N.", "Extra 50%N"),
                "EXTRA_100_N": ("H.E.N.D.", "Extra 100%N"),
            }
            totais = {"Funcionário": funcionario_nome}
            for nome_amigavel, (campo_b, campo_p) in campos.items():
                soma_b = df_boletim_func[campo_b].sum() if campo_b in df_boletim_func else 0
                soma_p = df_ponto_func[campo_p].sum() if campo_p in df_ponto_func else 0
                totais[f"Boletim {nome_amigavel}"] = round(soma_b, 2)
                totais[f"Ponto {nome_amigavel}"] = round(soma_p, 2)
                totais[f"Diferença {nome_amigavel}"] = round(soma_b - soma_p, 2)
            return totais
        except Exception as e:
            print(f"Erro ao calcular totais para '{funcionario_nome}': {e}")
            return None
