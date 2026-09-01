"""Crawler ROTALOG adaptado para gravar nos Parquets versionados da versão web."""

from __future__ import annotations

import concurrent.futures
from datetime import datetime, timedelta
import math
import os
import re
import unicodedata
import warnings
import pandas as pd
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from bdo.services.parquet_repository import (
    ImportStats,
    ParquetStorageRepository,
)

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL_BASE = "https://www.copel.com/rtlweb"
URL_DASHBOARD = f"{URL_BASE}/paginas/dashboard"
URL_LOGIN_ACTION = f"{URL_BASE}/paginas/j_security_check"
URL_LISTAGEM_EVENTOS = f"{URL_BASE}/paginas/listagemEventos"


def dividir_periodo_em_intervalos(data_inicio_str: str, data_fim_str: str, dias_por_chunk: int = 5) -> list[tuple[str, str]]:
    """Divide um período de datas em blocos menores (ex.: 5 dias cada)."""
    try:
        dt_ini = datetime.strptime(data_inicio_str, "%d/%m/%Y")
        dt_fim = datetime.strptime(data_fim_str, "%d/%m/%Y")
    except Exception:
        return [(data_inicio_str, data_fim_str)]

    if (dt_fim - dt_ini).days < dias_por_chunk:
        return [(data_inicio_str, data_fim_str)]

    intervalos = []
    atual = dt_ini
    while atual <= dt_fim:
        proximo = min(atual + timedelta(days=dias_por_chunk - 1), dt_fim)
        intervalos.append((atual.strftime("%d/%m/%Y"), proximo.strftime("%d/%m/%Y")))
        atual = proximo + timedelta(days=1)

    return intervalos


class CrawlerRotalog:
    def __init__(self, usuario: str | None = None, senha: str | None = None):
        self.usuario = usuario or os.getenv("ROTALOG_USUARIO", "").strip()
        self.senha = senha or os.getenv("ROTALOG_SENHA", "").strip()

        if not self.usuario or not self.senha:
            raise RuntimeError(
                "Credenciais do ROTALOG não configuradas. "
                "Defina ROTALOG_USUARIO e ROTALOG_SENHA no arquivo .env."
            )

    def _criar_sessao_autenticada(self) -> requests.Session:
        """Cria e autentica uma sessão HTTP individual."""
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/x-www-form-urlencoded",
        })
        session.get(URL_DASHBOARD, verify=False, timeout=30)
        payload = {"j_username": self.usuario, "j_password": self.senha}
        resp = session.post(URL_LOGIN_ACTION, data=payload, verify=False, timeout=30)
        if resp.status_code != 200 or "j_security_check" in resp.text:
            raise PermissionError("Falha na autenticação do portal Copel RTLWeb.")
        return session

    def _raspar_bloco(self, data_inicio: str, data_fim: str, progress_callback=None) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Raspagem isolada de um bloco de datas em uma sessão própria."""
        session = self._criar_sessao_autenticada()

        resp_page = session.get(URL_LISTAGEM_EVENTOS, verify=False, timeout=30)
        soup_page = BeautifulSoup(resp_page.text, "html.parser")
        view_state = soup_page.find("input", {"name": "javax.faces.ViewState"})["value"]

        post_data = {
            "form": "form",
            "form:j_idt27:dataInicial_input": data_inicio,
            "form:j_idt27:dataFinal_input": data_fim,
            "form:veiculo": "",
            "form:contrato_input": "",
            "form:j_idt40": "",
            "javax.faces.ViewState": view_state,
        }

        resp_search = session.post(URL_LISTAGEM_EVENTOS, data=post_data, verify=False, timeout=60)
        soup_search = BeautifulSoup(resp_search.text, "html.parser")

        view_state_elem = soup_search.find("input", {"name": "javax.faces.ViewState"})
        if view_state_elem:
            view_state = view_state_elem["value"]

        m_eq = re.search(r"widget_form_tbEquipes.*?rowCount:(\d+)", resp_search.text)
        row_count_eq = int(m_eq.group(1)) if m_eq else 0

        m_ev = re.search(r"widget_form_tbListagemEventos.*?rowCount:(\d+)", resp_search.text)
        row_count_ev = int(m_ev.group(1)) if m_ev else 0

        headers_ajax = {
            "Faces-Request": "partial/ajax",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        # 1. EQUIPES (Tabela #0)
        rows0_data = []
        elet1_full_list = []
        elet2_full_list = []
        page_size_eq = 25
        total_pages_eq = math.ceil(row_count_eq / page_size_eq) if row_count_eq > 0 else 1

        tbls = soup_search.find_all("table")
        headers0 = [th.text.strip().replace("\n", " ") for th in tbls[0].find_all("th") if th.text.strip()] if tbls else []

        def parse_equipes_tr(soup_ctx):
            for tr in soup_ctx.find_all("tr"):
                tds = tr.find_all("td")
                if not tds:
                    continue
                cells = [td.text.strip().replace("\n", " ") for td in tds]
                spans_title = [
                    span["title"].strip()
                    for span in tr.find_all("span", title=True)
                    if " - " in span.get("title", "")
                ]
                e1 = spans_title[0] if len(spans_title) > 0 else ""
                e2 = spans_title[1] if len(spans_title) > 1 else ""

                if len(cells) >= len(headers0):
                    rows0_data.append(cells[:len(headers0)])
                    elet1_full_list.append(e1)
                    elet2_full_list.append(e2)

        for page in range(total_pages_eq):
            offset = page * page_size_eq
            if offset == 0 and tbls:
                parse_equipes_tr(tbls[0])
            else:
                ajax_data = {
                    "javax.faces.partial.ajax": "true",
                    "javax.faces.source": "form:tbEquipes",
                    "javax.faces.partial.execute": "form:tbEquipes",
                    "javax.faces.partial.render": "form:tbEquipes",
                    "form:tbEquipes": "form:tbEquipes",
                    "form:tbEquipes_pagination": "true",
                    "form:tbEquipes_first": str(offset),
                    "form:tbEquipes_rows": str(page_size_eq),
                    "form:tbEquipes_encodeFeature": "true",
                    "form": "form",
                    "form:j_idt27:dataInicial_input": data_inicio,
                    "form:j_idt27:dataFinal_input": data_fim,
                    "javax.faces.ViewState": view_state,
                }
                resp_ajax = session.post(URL_LISTAGEM_EVENTOS, data=ajax_data, headers=headers_ajax, verify=False, timeout=30)
                soup_ajax = BeautifulSoup(resp_ajax.text, "html.parser")
                update = soup_ajax.find("update", {"id": "form:tbEquipes"})
                if update:
                    parse_equipes_tr(BeautifulSoup(update.text, "html.parser"))

        df_eq = pd.DataFrame(rows0_data, columns=headers0[:len(rows0_data[0])] if rows0_data else [])
        if not df_eq.empty:
            df_eq["Eletricista 1 (Matrícula e Nome)"] = elet1_full_list
            df_eq["Eletricista 2 (Matrícula e Nome)"] = elet2_full_list

        # 2. EVENTOS (Tabela #1)
        rows1_data = []
        page_size_ev = 50
        total_pages_ev = math.ceil(row_count_ev / page_size_ev) if row_count_ev > 0 else 1
        headers1_clean = []

        if len(tbls) > 1:
            headers1 = [th.text.strip().replace("\n", " ") for th in tbls[1].find_all("th") if th.text.strip()]
            headers1_clean = [re.sub(r"Filter by.*", "", h).strip() for h in headers1]

        def parse_eventos_tr(soup_ctx):
            for tr in soup_ctx.find_all("tr"):
                tds = tr.find_all("td")
                if not tds:
                    continue
                cells = [td.text.strip().replace("\n", " ") for td in tds]
                if len(cells) == len(headers1_clean):
                    rows1_data.append(cells)

        for page in range(total_pages_ev):
            offset = page * page_size_ev
            if offset == 0 and len(tbls) > 1:
                parse_eventos_tr(tbls[1])
            else:
                ajax_data = {
                    "javax.faces.partial.ajax": "true",
                    "javax.faces.source": "form:tbListagemEventos",
                    "javax.faces.partial.execute": "form:tbListagemEventos",
                    "javax.faces.partial.render": "form:tbListagemEventos",
                    "form:tbListagemEventos": "form:tbListagemEventos",
                    "form:tbListagemEventos_pagination": "true",
                    "form:tbListagemEventos_first": str(offset),
                    "form:tbListagemEventos_rows": str(page_size_ev),
                    "form:tbListagemEventos_encodeFeature": "true",
                    "form": "form",
                    "form:j_idt27:dataInicial_input": data_inicio,
                    "form:j_idt27:dataFinal_input": data_fim,
                    "javax.faces.ViewState": view_state,
                }
                resp_ajax = session.post(URL_LISTAGEM_EVENTOS, data=ajax_data, headers=headers_ajax, verify=False, timeout=30)
                soup_ajax = BeautifulSoup(resp_ajax.text, "html.parser")
                update = soup_ajax.find("update", {"id": "form:tbListagemEventos"})
                if update:
                    parse_eventos_tr(BeautifulSoup(update.text, "html.parser"))

        df_ev = pd.DataFrame(rows1_data, columns=headers1_clean if rows1_data else [])

        return df_eq, df_ev

    def obter_dados_rotalog(self, data_inicio: str, data_fim: str, callback_progresso=None, max_workers: int = 4) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Executa a captura em paralelo por blocos de 5 dias para velocidade máxima.
        """
        chunks = dividir_periodo_em_intervalos(data_inicio, data_fim, dias_por_chunk=5)
        total_chunks = len(chunks)

        if callback_progresso:
            callback_progresso(5, f"Período dividido em {total_chunks} blocos. Iniciando {max_workers} trabalhadores simultâneos...")

        dfs_equipes = []
        dfs_eventos = []
        concluidos = 0

        def _task_worker(chunk):
            nonlocal concluidos
            d_i, d_f = chunk
            df_eq, df_ev = self._raspar_bloco(d_i, d_f)
            concluidos += 1
            if callback_progresso:
                pct = 10 + int((concluidos / total_chunks) * 85)
                callback_progresso(pct, f"Concluído bloco {concluidos}/{total_chunks} ({d_i} a {d_f}) • {len(df_eq)} equipes, {len(df_ev)} eventos")
            return df_eq, df_ev

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            resultados = list(executor.map(_task_worker, chunks))

        for df_eq, df_ev in resultados:
            if df_eq is not None and not df_eq.empty:
                dfs_equipes.append(df_eq)
            if df_ev is not None and not df_ev.empty:
                dfs_eventos.append(df_ev)

        df_equipes_final = pd.concat(dfs_equipes, ignore_index=True).drop_duplicates() if dfs_equipes else pd.DataFrame()
        df_eventos_final = pd.concat(dfs_eventos, ignore_index=True).drop_duplicates() if dfs_eventos else pd.DataFrame()


        if callback_progresso:
            callback_progresso(100, f"Concluído! Total: {len(df_equipes_final)} equipes e {len(df_eventos_final)} eventos.")

        return df_equipes_final, df_eventos_final


def _normalizar_cabecalho(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    return " ".join(
        text.encode("ascii", "ignore").decode("ascii").lower().split()
    )


def _coluna(df: pd.DataFrame, *nomes: str) -> str:
    wanted = {_normalizar_cabecalho(nome) for nome in nomes}
    for column in df.columns:
        if _normalizar_cabecalho(column) in wanted:
            return str(column)
    raise ValueError(f"Coluna ROTALOG ausente. Esperada: {', '.join(nomes)}")


def preparar_equipes(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    result = df.copy()
    date_column = _coluna(result, "Data Referência - Turno", "Data Referencia - Turno")
    raw = result[date_column].astype(str).str.extract(
        r"(\d{2}/\d{2}/\d{4})", expand=False
    )
    result["Data"] = pd.to_datetime(raw, format="%d/%m/%Y", errors="coerce")
    return result[result["Data"].notna()].copy()


def preparar_eventos(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    result = df.copy()
    start_column = _coluna(result, "Inicio Deslo", "Início Deslo")
    result["Data"] = pd.to_datetime(
        result[start_column], errors="coerce", dayfirst=True
    ).dt.floor("D")
    return result[result["Data"].notna()].copy()


def sincronizar_rotalog(
    repository: ParquetStorageRepository,
    data_ini: str,
    data_fim: str,
) -> dict[str, object]:
    inicio = pd.Timestamp(data_ini)
    fim = pd.Timestamp(data_fim)
    if fim < inicio:
        raise ValueError("A data final deve ser igual ou posterior à data inicial.")
    if (fim - inicio).days > 62:
        raise ValueError("O crawler aceita no máximo 63 dias por execução.")

    crawler = CrawlerRotalog()
    equipes_raw, eventos_raw = crawler.obter_dados_rotalog(
        inicio.strftime("%d/%m/%Y"),
        fim.strftime("%d/%m/%Y"),
    )
    equipes = preparar_equipes(equipes_raw)
    eventos = preparar_eventos(eventos_raw)
    stats_equipes = (
        repository.upsert("rotalog_equipes", equipes) if not equipes.empty else ImportStats()
    )
    stats_eventos = (
        repository.upsert("rotalog_eventos", eventos) if not eventos.empty else ImportStats()
    )
    return {
        "equipes": stats_equipes.to_dict(),
        "eventos": stats_eventos.to_dict(),
        "equipes_capturadas": len(equipes),
        "eventos_capturados": len(eventos),
    }
