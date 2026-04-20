# =============================================================================
# Nome do arquivo : core/cmd_relatorio.py
# Data de criação : 31/10/2025
# Função          : Implementar o comando RELATORIO do DDS (lógica completa).
# Funcionalidades :
#   - Tenta carregar dados do CACHE JSON no Drive (Economia de Firestore).
#   - Se não houver cache, lê dados mensais do Firestore/DB e salva o cache no Drive.
#   - (Opcional) Resolver imagens via índice do Drive (por empresa/mês) e gerar relatório com fotos.
#   - Gerar PDFs (detalhado + presença) e enviar por e-mail com anexos.
# =============================================================================


from __future__ import annotations
import os
import json
import time
import re

import asyncio
import datetime as dt
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from logger import log_manager
from tui_progress import progress_bus
from email_utils import send_response

# Firestore + PDFs
from relatorio import (
    interpretar_mes as _interpretar_mes_legacy,
    carregar_db as carregar_db_relatorio,
    buscar_e_agrupar as buscar_e_agrupar_relatorio,
    gerar_pdf_detalhado,
    gerar_pdf_com_foto,
    gerar_pdf_sintetico_analitico,
)
from relatorio_presenca import gerar_pdf_presenca


# ------------------------------- Helpers internos -------------------------------

MESES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
]

def _yyyy_mm(ano: int, mes: int) -> str:
    return f"{ano:04d}-{mes:02d}"

def _parse_periodo_argumento(argumento: str) -> tuple[Optional[int], Optional[int], bool]:
    """
    Interpreta mês/ano a partir do argumento do comando.

    Regras:
      - Se ano vier no argumento, usa o ano informado.
      - Se ano NÃO vier, o caller deve assumir ano atual (compatibilidade).
      - Mês continua compatível com a lógica legacy (nome do mês ou número).
      - Reconhece formatos adicionais:
          * YYYY-MM  (ex.: 2025-12)
          * YYYY/MM  (ex.: 2025/12)
          * MM/YYYY  (ex.: 12/2025)
          * "dezembro 2025", "dezembro/2025"
      - "foto" pode aparecer em qualquer posição.

    Retorno:
      (ano|None, mes|None, usar_foto)
    """
    txt = (argumento or "").strip()
    txt_l = txt.lower()

    usar_foto = "foto" in txt_l

    # Normaliza separadores para facilitar matching
    norm = re.sub(r"\s+", " ", txt_l)

    # 1) Detecta formatos com ano e mês juntos (prioritário)
    #    YYYY-MM / YYYY/MM
    m = re.search(r"\b(\d{4})\s*[-/]\s*(0?[1-9]|1[0-2])\b", norm)
    if m:
        ano = int(m.group(1))
        mes = int(m.group(2))
        return ano, mes, usar_foto

    #    MM-YYYY / MM/YYYY
    m = re.search(r"\b(0?[1-9]|1[0-2])\s*[-/]\s*(\d{4})\b", norm)
    if m:
        mes = int(m.group(1))
        ano = int(m.group(2))
        return ano, mes, usar_foto

    # 2) Caso não tenha vindo combinado, tenta extrair ANO solto (ex.: "dezembro 2025")
    ano: Optional[int] = None
    y = re.search(r"\b(\d{4})\b", norm)
    if y:
        try:
            ano = int(y.group(1))
        except Exception:
            ano = None

    # 3) Mês: delega para a lógica legacy (mantém compatibilidade total)
    mes_num, usar_foto_legacy = _interpretar_mes_legacy(argumento)
    usar_foto = usar_foto or bool(usar_foto_legacy)

    return ano, mes_num, usar_foto
 

def _data_treinamento_do_nome(file_name: str) -> Optional[dt.date]:
    import re
    m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})\b", file_name or "")
    if not m:
        return None
    y, mth, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return dt.date(y, mth, d)
    except ValueError:
        return None


def _load_or_fetch_grupos(ano: int, mes: int) -> Dict[dt.date, list]:
    """
    Busca os dados de DDS do Firestore e agrupa por data.
    """
    yyyy_mm_str = _yyyy_mm(ano, mes)
    log_manager.add(f"[Relatório] Coletando dados para {yyyy_mm_str}...", "INFO")

    try:
        db = carregar_db_relatorio()
        todos_os_grupos = buscar_e_agrupar_relatorio(db)
    except Exception as e:
        log_manager.add(f"[Relatório] Erro ao consultar Firestore: {e}", "ERROR")
        return {}

    out = {
        data: regs
        for data, regs in todos_os_grupos.items()
        if data.month == mes and data.year == ano
    }

    log_manager.add(f"[Relatório] Registros encontrados: {sum(len(v) for v in out.values())}", "INFO")
    return out

# ---- Indexadores e resolvers (Drive) ----
def _build_drive_index_for_month(
    ano: int,
    mes: int,
    grupos_por_data: Dict[dt.date, List[dict]],
) -> None:
    """
    Gera/atualiza data/indexes/<EMPRESA>/YYYY-MM/INDEX.json para o mês informado,
    a partir das URLs (thumbUrl/fotoUrl) presentes em grupos_por_data.
    """
    from urllib.parse import unquote

    yyyy_mm_str = _yyyy_mm(ano, mes)
    base = Path("data/indexes")
    svc = drive_get_service()

    # company -> {"by_path": {rel_path: meta}, "by_name": {name: meta}}
    companies: Dict[str, Dict[str, Dict[str, dict]]] = {}

    def _add_entry(company: str, rel_path: str, file_name: str, file_id: str) -> None:
        c = companies.setdefault(company, {"by_path": {}, "by_name": {}})
        meta = {"id": file_id, "name": file_name}
        c["by_path"].setdefault(rel_path, meta)
        c["by_name"].setdefault(file_name, meta)

    def _search_file_id(name: str) -> Optional[str]:
        """Busca um arquivo no Drive pelo nome e retorna o id."""
        if not name:
            return None
        try:
            name_q = name.replace("'", "\\'")
            q = f"name = '{name_q}' and trashed = false"
            result = (
                svc.files()
                .list(
                    q=q,
                    pageSize=5,
                    fields="files(id, name, mimeType)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            files = result.get("files", [])
            if not files:
                # log_manager.add(f"Arquivo não encontrado: {name}", "DEBUG")
                return None
            return files[0]["id"]
        except Exception as e:
            log_manager.add(f"[Drive-Índice] Erro busca '{name}': {e}", "ERROR")
            return None

    # Varre todos os registros do mês e tenta construir o índice
    for data, regs in grupos_por_data.items():
        for r in regs:
            url_or = (r.get("thumbUrl") or r.get("fotoUrl") or "").strip()
            if not url_or:
                continue

            file_name = os.path.basename(url_or.split("?", 1)[0])
            if not file_name:
                continue

            gcs_path = None
            if "/o/" in url_or:
                try:
                    enc = url_or.split("/o/", 1)[1].split("?", 1)[0]
                    enc = enc.replace("~2F", "/")
                    gcs_path = unquote(enc).lstrip("/")
                except Exception:
                    gcs_path = None

            company = "default"
            rel_path = file_name
            if gcs_path and gcs_path.startswith("DDS_Fotos/"):
                parts = gcs_path.split("/")
                if len(parts) >= 4:
                    company = parts[1] or "default"
                    month_part = parts[2]
                    if month_part != yyyy_mm_str:
                        continue
                    rel_path = "/".join(parts[3:]) or file_name

            fid = _search_file_id(file_name)
            if not fid:
                continue

            _add_entry(company, rel_path, file_name, fid)

    if not companies:
        return

    for company, data in companies.items():
        by_path = data.get("by_path") or {}
        by_name = data.get("by_name") or {}
        if not by_path and not by_name:
            continue

        emp_dir = base / company / yyyy_mm_str
        emp_dir.mkdir(parents=True, exist_ok=True)
        idx_path = emp_dir / "INDEX.json"

        payload = {
            "company": company,
            "month": yyyy_mm_str,
            "generated_at": dt.datetime.utcnow().isoformat() + "Z",
            "by_path": by_path,
            "by_name": by_name,
        }
        try:
            idx_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                "utf-8",
            )
        except Exception as e:
            log_manager.add(f"[Drive-Índice] Erro ao gravar índice: {e}", "ERROR")

def _load_local_index_for_month(ano: int, mes: int) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Lê data/indexes/<EMPRESA>/YYYY-MM/INDEX.json
    """
    base = Path("data/indexes")
    by_path: Dict[str, str] = {}
    by_name: Dict[str, str] = {}
    yyyy_mm_str = _yyyy_mm(ano, mes)

    if not base.exists():
        return by_path, by_name

    for emp_dir in base.iterdir():
        if not emp_dir.is_dir():
            continue
        idx = emp_dir / yyyy_mm_str / "INDEX.json"
        if not idx.exists():
            continue

        try:
            j = json.loads(idx.read_text("utf-8"))
            company = j.get("company") or emp_dir.name
            base_gcs_prefix = f"DDS_Fotos/{company}/{yyyy_mm_str}/"

            bp = j.get("by_path") or {}
            if isinstance(bp, dict):
                for rel_path, meta in bp.items():
                    if not isinstance(meta, dict): continue
                    fid = meta.get("id")
                    if not fid: continue
                    
                    rel_key = (rel_path or "").lstrip("/")
                    name = os.path.basename(rel_key) if rel_key else (meta.get("name") or "")
                    gcs_key = f"{base_gcs_prefix}{rel_key}" if rel_key else ""
                    
                    if gcs_key: by_path.setdefault(gcs_key, fid)
                    if name: by_name.setdefault(name, fid)

            bn = j.get("by_name") or {}
            if isinstance(bn, dict):
                for name, meta in bn.items():
                    if not isinstance(meta, dict): continue
                    fid = meta.get("id")
                    if fid and name:
                        by_name.setdefault(name, fid)

        except Exception as e:
            log_manager.add(f"[Drive-Índice] erro lendo índice {idx}: {e}", "ERROR")
            continue

    return by_path, by_name


def _drive_link_for_file_id(svc, file_id: str) -> Optional[str]:
    try:
        try:
            svc.permissions().create(
                fileId=file_id,
                body={"role": "reader", "type": "anyone"},
                supportsAllDrives=True,
            ).execute()
        except Exception: pass
        meta = svc.files().get(fileId=file_id, fields="webViewLink", supportsAllDrives=True).execute()
        return meta.get("webViewLink")
    except Exception:
        return None

_DEBUG_FOTOS_MAX = 80
_debug_fotos_count = 0


def _resolve_bytes_drive_first_month_cached(
    svc,
    ano: int,
    mes: int,
    by_path: Dict[str, str],
    by_name: Dict[str, str],
    name: str,
    url_or: Optional[str] = None,
) -> Optional[bytes]:
    """
    Tenta resolver bytes usando o índice local (by_path/by_name).
    """
    from urllib.parse import unquote

    global _debug_fotos_count
    debug_this = _debug_fotos_count < _DEBUG_FOTOS_MAX
    if debug_this: _debug_fotos_count += 1

    gcs_path = None
    rel_path = None
    name_key = name

    if url_or and "/o/" in url_or:
        enc = url_or.split("/o/", 1)[1].split("?", 1)[0]
        enc = enc.replace("~2F", "/")
        gcs_path = unquote(enc).lstrip("/")
        name_key = os.path.basename(gcs_path)

        m = re.search(r"(Fotos/.*|Thumb/.*)$", gcs_path)
        if m: rel_path = m.group(1)

    # 1) Tenta by_path
    if rel_path:
        fid = by_path.get(rel_path)
        if fid:
            try: return download_file_bytes(svc, fid)
            except Exception: pass

    # 2) Tenta by_name
    fid = by_name.get(name_key)
    if fid:
        try: return download_file_bytes(svc, fid)
        except Exception: pass

    return None

# --------------------------------- Comando ------------------------------------


def comando_relatorio(argumento: str, sender: str, manter_arquivos: bool = False) -> List[str]:
    """
    Executa o comando RELATORIO DDS.
    - Se 'foto' estiver no argumento → relatório com fotos (Firebase).
    - Caso contrário → relatórios detalhado e presença.
    """
    t_start = time.perf_counter()

    ano_arg, mes_num, usar_foto = _parse_periodo_argumento(argumento)
    if not mes_num:
        send_response(sender, "❌ Erro no Relatório", f"Mês inválido: '{argumento}'.")
        return []

    # Regra solicitada: se ano vier no argumento usa ele; senão usa o ano atual.
    ano_ref = int(ano_arg) if isinstance(ano_arg, int) and ano_arg > 0 else dt.datetime.now().year

    mes_str = MESES_PT[mes_num - 1].capitalize()

    log_manager.add(f"[Relatório] Iniciando geração para {mes_str}/{ano_ref}...", "INFO")

    grupos_filtrados = _load_or_fetch_grupos(ano_ref, mes_num)
    if not grupos_filtrados:
        send_response(sender, "⚠️ Relatório Vazio", f"Nenhum registro encontrado para {mes_str}/{ano_ref}.")
        return []

    anexos: List[str] = []

    try:
        if usar_foto:
            # -----------------------------------------------------------------
            # RELATÓRIO COM FOTOS (via Firebase)
            # -----------------------------------------------------------------
            path = f"relatorio_fotos_{ano_ref}-{mes_num:02d}.pdf"
            log_manager.add(
                f"[Relatório Fotos] Gerando relatório com fotos (Firebase URLs) → {path}",
                "INFO",
            )

            try:
                progress_bus.start(
                    op="relatorio-fotos",
                    phase="Baixando thumbs",
                    total=sum(len(v) for v in grupos_filtrados.values()),
                    bytes_total=0,
                    month=f"{ano_ref}-{mes_num:02d}",
                    company="ALL",
                )
            except Exception:
                pass

            asyncio.run(
                gerar_pdf_com_foto(
                    grupos_filtrados,
                    path,
                    resolver_fn=None,      # Drive desativado
                    link_resolver=None,    # links virão do próprio Firestore
                )
            )

            try:
                progress_bus.finish()
            except Exception:
                pass

            anexos.append(path)
            assunto = f"📸 Relatório com Fotos - {mes_str}/{ano_ref}"
            corpo = (
                 f"Segue em anexo o relatório com fotos dos DDS do mês {mes_str} de {ano_ref}.\n\n"
                f"As imagens foram carregadas diretamente do Firebase (thumbUrl/fotoUrl)."
            )

            log_manager.add("[Relatório Fotos] PDF com fotos gerado com sucesso!", "SUCCESS")

        else:
            # -----------------------------------------------------------------
            # RELATÓRIOS SEM FOTOS (DETALHADO + PRESENÇA + RANKING)
            # -----------------------------------------------------------------
            detalhado_path = f"relatorio_detalhado_{ano_ref}-{mes_num:02d}.pdf"
            presenca_path = f"relatorio_presenca_{ano_ref}-{mes_num:02d}.pdf"
            ranking_path   = f"relatorio_ranking_{ano_ref}-{mes_num:02d}.pdf"

            log_manager.add(
                "[Relatório] Gerando relatórios PDF (detalhado + presença + ranking)...",
                "INFO",
            )
            gerar_pdf_detalhado(grupos_filtrados, detalhado_path)
            gerar_pdf_presenca(grupos_filtrados, presenca_path)
            gerar_pdf_sintetico_analitico(
                grupos_filtrados,
                ano_ref,
                mes_num,
                ranking_path,
            )

            anexos.extend([detalhado_path, presenca_path, ranking_path])

            assunto = f"📊 Relatórios DDS - {mes_str}"
            corpo = (
                f"Seguem em anexo os relatórios de DDS referentes a {mes_str} de {ano_ref}:\n\n"
                f"• Relatório Detalhado\n"
                f"• Relatório de Presença por Equipe\n"
                f"• Relatório de Ranking (Sintético + Analítico)"
            )

            log_manager.add("[Relatório] Relatórios PDF (sem fotos) gerados com sucesso!", "SUCCESS")

        # ---------------------------------------------------------------------
        # Envio
        # ---------------------------------------------------------------------
        send_response(sender, assunto, corpo, attachments=list(anexos))
        dur = time.perf_counter() - t_start
        log_manager.add(f"[Relatório] Enviado para {sender} em {dur:.1f}s.", "SUCCESS")

    except Exception as e:
        try:
            progress_bus.finish()
        except Exception:
            pass

        log_manager.add(f"[Relatório] Erro ao gerar/enviar: {e}", "ERROR")
        try:
            send_response(sender, "❌ Erro ao gerar relatório", f"Ocorreu um erro: {e}")
        except Exception:
            pass

    finally:
        if not manter_arquivos:
            for anexo_path in anexos:
                try:
                    if os.path.exists(anexo_path):
                        os.remove(anexo_path)
                except Exception:
                    pass

    return anexos