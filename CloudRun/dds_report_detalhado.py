# =====================================================================
# FILE: dds_report_detalhado.py
# PURPOSE: Relatório DDS Detalhado (sem fotos) — geração e cache no Cloud Run.
# =====================================================================

"""dds_report_detalhado.py

Relatórios DDS (Cloud Run) — Relatório DETALHADO (sem fotos).

Objetivo:
  - Recriar o relatório detalhado do BackEnd (tabela por dia, sem imagens),
    mantendo o mesmo padrão do Cloud Run:
      * range start/end
      * cache hot/cold (day-cache JSON)
      * cache de PDFs diários (para dias frios)
      * capa + sumário
      * merge + paginação (modelo B) via stamp do engine

IMPORTANTE:
  - Não altera a lógica dos relatórios existentes (Fotos e Presença).
  - Este módulo é independente e pode ser plugado via admin_routes.py.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.units import cm

from pypdf import PdfReader

# Reuso controlado do engine (não modifica o arquivo do engine)
from reportlab.lib.pagesizes import A4, landscape

# Página padrão: manter compatível com os relatórios existentes (landscape A4)
REPORT_PAGE_SIZE = landscape(A4)

# Reuso controlado do engine (não modifica o arquivo do engine)
from dds_reports_engine import (
    CacheConfig,
    CacheStore,
    ReportResult,
    daterange,
    parse_iso_date,
    format_pt_date,
    parse_duracao_para_segundos,
    formatar_segundos_para_duracao,
    gerar_pdf_capa,
    gerar_pdf_sumario,
    merge_pdfs_with_cleanup,
    stamp_footer_paginacao_geral,
    _tz_today_yesterday,
    _rank_equipes,
    _logo_assets,
    _draw_header_footer,
)

# Firestore: usamos o client do engine (mesma inicialização) e normalizamos aqui
from dds_reports_engine import _firestore_client
def _build_key_detalhado(start: str, end: str, version: str = "v1") -> str:
    return f"dds_detalhado_{start}_{end}_{version}"


def _compute_kpis(day_groups: Dict[str, List[dict]], days_with_regs: List[str]) -> Tuple[int, int, int, int]:
    total_regs = sum(len(day_groups.get(day) or []) for day in days_with_regs)
    equipes = set()
    total_participantes = 0
    total_duracao_seg = 0
    for day in days_with_regs:
        for r in day_groups.get(day) or []:
            equipes.add((r.get("equipe") or "").strip())
            total_participantes += len(r.get("eletricistas") or [])
            total_duracao_seg += int(r.get("duracao_seg") or 0)
    teams = len([e for e in equipes if e])
    return total_regs, teams, total_participantes, total_duracao_seg


def _pdf_page_count(path: Path) -> int:
    try:
        return len(PdfReader(str(path)).pages)
    except Exception:
        return 0


# =============================
# Dataset (Firestore + cache isolado para "detalhado")
# =============================

_DAYCACHE_NS = "detalhado"  # não usa o day-cache global para não afetar relatórios já estáveis

def _extract_day(header_date: str) -> Optional[str]:
    hd = (header_date or "").strip()
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", hd)
    return m.group(1) if m else None


def _normalize_dds_doc_v2(d: dict) -> Optional[dict]:
    """Normaliza um documento DDS para o formato do relatório detalhado.

    Aceita headerDate no formato:
      - YYYY-MM-DD
      - YYYY-MM-DD ... (qualquer sufixo)
    """
    header_date_raw = (d.get("headerDate") or "").strip()
    day = _extract_day(header_date_raw)
    if not day:
        return None

    total_segundos = parse_duracao_para_segundos(d.get("duracao", "0s"))
    if 0 < total_segundos < 120:
        total_segundos += 120

    return {
        "headerDate": day,
        "headerTitle": d.get("headerTitle", "–"),
        "equipe": d.get("equipe", "–"),
        "dataHora": d.get("dataHora", "–"),
        "duracao": formatar_segundos_para_duracao(total_segundos),
        "duracao_seg": total_segundos,
        "eletricistas": d.get("eletricistas", []) or [],
        "tema": d.get("tema", "–"),
    }


def _fetch_dds_range_v2(start_date: str, end_date: str) -> Dict[str, List[dict]]:
    """Busca DDS no Firestore por range de headerDate (prefixo YYYY-MM-DD)."""
    db = _firestore_client()
    end_key = f"{end_date}\uf8ff"
    q = (
        db.collection("DDS")
        .where("headerDate", ">=", start_date)
        .where("headerDate", "<=", end_key)
        .order_by("headerDate")
    )

    groups: Dict[str, List[dict]] = {}
    for doc in q.stream():
        raw = doc.to_dict() or {}
        norm = _normalize_dds_doc_v2(raw)
        if not norm:
            continue
        day = norm["headerDate"]
        groups.setdefault(day, []).append(norm)
    return groups


def _fetch_dds_day_v2(day: str) -> List[dict]:
    db = _firestore_client()
    end_key = f"{day}\uf8ff"
    q = db.collection("DDS").where("headerDate", ">=", day).where("headerDate", "<=", end_key).order_by("headerDate")
    out: List[dict] = []
    for doc in q.stream():
        raw = doc.to_dict() or {}
        norm = _normalize_dds_doc_v2(raw)
        if norm:
            out.append(norm)
    return out


def _daycache_rel(day: str) -> str:
    return f"day-cache/{_DAYCACHE_NS}/{day}.json"


def _load_day_groups(
    *,
    start_date: str,
    end_date: str,
    tz_name: str,
    store: CacheStore,
) -> Tuple[Dict[str, List[dict]], List[str], List[str], bool, dt.date, dt.date]:
    """Carrega day_groups respeitando hot/cold, usando cache isolado do detalhado."""
    start = parse_iso_date(start_date)
    end = parse_iso_date(end_date)
    today, yesterday = _tz_today_yesterday(tz_name)
    includes_hot = any(d in (today, yesterday) for d in daterange(start, end))

    days_all = [d.strftime("%Y-%m-%d") for d in daterange(start, end)]
    day_groups: Dict[str, List[dict]] = {}

    # Cold cache: detecta faltas e preenche via bulk fetch (uma query)
    cold_missing = False
    for d in daterange(start, end):
        if d < yesterday:
            day = d.strftime("%Y-%m-%d")
            if not store.blob_exists(_daycache_rel(day)):
                cold_missing = True
                break

    if cold_missing:
        fetched = _fetch_dds_range_v2(start_date, end_date)
        for day, regs in fetched.items():
            store.write_json(_daycache_rel(day), {"day": day, "regs": regs})

    # Carrega dias frios do cache
    for d in daterange(start, end):
        day = d.strftime("%Y-%m-%d")
        if d < yesterday:
            payload = store.read_json(_daycache_rel(day))
            day_groups[day] = (payload or {}).get("regs") or []

    # Hot days: sempre consulta Firestore e atualiza cache isolado
    for hot in (yesterday, today):
        if start <= hot <= end:
            day = hot.strftime("%Y-%m-%d")
            regs = _fetch_dds_day_v2(day)
            store.write_json(_daycache_rel(day), {"day": day, "regs": regs})
            day_groups[day] = regs

    # Resto: garante que todos os dias tenham entrada
    for d in daterange(start, end):
        day = d.strftime("%Y-%m-%d")
        if day not in day_groups:
            payload = store.read_json(_daycache_rel(day))
            day_groups[day] = (payload or {}).get("regs") or []

    days_with_regs = [day for day in days_all if (day_groups.get(day) or [])]
    return day_groups, days_all, days_with_regs, includes_hot, today, yesterday

def gerar_pdf_diario_detalhado_body(
    *,
    day: str,
    regs: List[dict],
    path_saida: Path,
    equipe_ranking: Dict[str, int],
) -> None:
    """Gera o PDF diário (apenas corpo) do relatório detalhado."""
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("Cell", parent=styles["BodyText"], alignment=TA_LEFT, leading=12)
    title_style = ParagraphStyle("SessionTitle", parent=styles["Heading2"], alignment=TA_LEFT, spaceBefore=12)

    doc = SimpleDocTemplate(
        str(path_saida),
        pagesize=REPORT_PAGE_SIZE,
        topMargin=3 * cm,
        bottomMargin=2 * cm,
        pageCompression=1,
    )
    story: List[Any] = []

    # Ordenação por ranking (presenças desc) e nome
    registros = sorted(
        regs or [],
        key=lambda r: (-int(equipe_ranking.get((r.get("equipe") or "").strip(), 0)), (r.get("equipe") or "").lower()),
    )

    # Cabeçalho do dia
    if registros:
        story.append(Paragraph(registros[0].get("headerTitle", "DDS"), title_style))
    else:
        story.append(Paragraph("DDS", title_style))

    story.append(Spacer(1, 4))
    try:
        date_obj = parse_iso_date(day)
        story.append(Paragraph(f"Data: {format_pt_date(date_obj)}", styles["Normal"]))
    except Exception:
        story.append(Paragraph(f"Data: {day}", styles["Normal"]))
    story.append(Spacer(1, 6))

    # Tabela (mesmo conjunto de colunas do BackEnd)
    data_rows: List[list] = [["Equipe", "Data Hora", "Qtd", "Participantes", "Tema"]]

    for r in registros:
        participantes = "<br/>".join(r.get("eletricistas", []) or []) or "–"
        data_rows.append([
            Paragraph(r.get("equipe", "–"), cell_style),
            Paragraph(str(r.get("dataHora", "–")), cell_style),
            str(len(r.get("eletricistas", []) or [])),
            Paragraph(participantes, cell_style),
            Paragraph(r.get("tema", "–"), cell_style),
        ])

    col_widths = [doc.width * x for x in [0.20, 0.15, 0.05, 0.30, 0.30]]
    table = Table(data_rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (2, 1), (2, -1), "CENTER"),
    ]))
    story.append(table)

    base_dir = Path(__file__).resolve().parent
    _, _, logo_left_reader, logo_right_reader, logo_right_width = _logo_assets(str(base_dir.resolve()))

    def _on_page(canv: Any, current_doc: Any) -> None:
        _draw_header_footer(
            canv,
            current_doc,
            titulo="DDS - Relatório Detalhado",
            page_label=None,
            generation_date_pt=None,
            logo_left_reader=logo_left_reader,
            logo_right_reader=logo_right_reader,
            logo_right_width=logo_right_width,
            draw_header=True,
            draw_footer=False,
        )

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)


def build_or_get_report_detalhado(
    *,
    start_date: str,
    end_date: str,
    tz_name: str,
    bucket_name: str,
    cache_prefix: str,
    force: bool = False,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> ReportResult:
    """Gera (ou reaproveita) o relatório detalhado (sem fotos)."""
    if not bucket_name:
        raise ValueError("Bucket de Storage não configurado (DDS_BUCKET_NAME / DDS_REPORTS_BUCKET_NAME).")

    total_range_days = (parse_iso_date(end_date) - parse_iso_date(start_date)).days + 1
    signed_ttl = int(os.getenv("DDS_SIGNED_URL_TTL_SECONDS", "3600"))

    def _emit(message: str, *, processed: int = 0, total: int = 0, stage: str = "", day: Optional[str] = None, **extra: Any) -> None:
        if not on_progress:
            return
        payload: Dict[str, Any] = {"message": message, "processed": int(processed), "total": int(total)}
        if stage:
            payload["stage"] = stage
        if day:
            payload["day"] = day
        if extra:
            payload.update(extra)
        try:
            on_progress(payload)
        except Exception:
            pass

    key = _build_key_detalhado(start_date, end_date)
    final_rel = f"final/{key}.pdf"
    meta_rel = f"final/{key}.meta.json"

    store = CacheStore(CacheConfig(bucket_name=bucket_name, prefix=cache_prefix))
    _emit("Preparando dados (cache/Firestore)...", processed=0, total=total_range_days, stage="prepare")

    day_groups, days_all, days_with_regs, includes_hot, today, yesterday = _load_day_groups(
        start_date=start_date, end_date=end_date, tz_name=tz_name, store=store
    )

    def _signed_urls() -> Dict[str, Optional[str]]:
        return {
            "inline": store.generate_signed_url(
                final_rel,
                expires_seconds=signed_ttl,
                disposition="inline",
                filename=f"{key}.pdf",
                response_type="application/pdf",
            ),
            "download": store.generate_signed_url(
                final_rel,
                expires_seconds=signed_ttl,
                disposition="attachment",
                filename=f"{key}.pdf",
                response_type="application/pdf",
            ),
        }

    # Reaproveita final do cache quando possível
    if (not force) and (not includes_hot) and store.blob_exists(final_rel):
        meta_persist = store.read_json(meta_rel) or {}
        urls = _signed_urls()
        meta_return = dict(meta_persist)
        meta_return.update({
            "signed_url": urls.get("inline"),
            "signed_url_download": urls.get("download"),
            "signed_url_expires_seconds": signed_ttl,
        })
        _emit("Relatório reaproveitado do cache.", processed=total_range_days, total=total_range_days, stage="done")
        return ReportResult(key=key, gcs_rel_path=final_rel, meta=meta_return)

    # Filtra dias vazios
    days_with_regs = [d for d in days_all if (day_groups.get(d) or [])]
    total_regs, teams, participants, duration_total_seconds = _compute_kpis(day_groups, days_with_regs)

    ranking = _rank_equipes({d: day_groups[d] for d in days_with_regs})

    # PDFs diários (body)
    daily_entries: List[Dict[str, Any]] = []
    processed_days = 0

    for day in days_all:
        processed_days += 1
        regs = day_groups.get(day) or []
        if not regs:
            _emit(f"Sem registros no dia {day}; pulando.", processed=processed_days, total=total_range_days, stage="day", day=day, skipped=True)
            continue

        day_date = parse_iso_date(day)
        is_hot = day_date in (today, yesterday)

        daily_rel = f"daily-body/detalhado/{day}.pdf"
        daily_meta_rel = f"daily-body/detalhado/{day}.meta.json"

        if (not force) and (not is_hot):
            meta_day = store.read_json(daily_meta_rel) or {}
            pc = int(meta_day.get("page_count") or 0)
            pb = int(meta_day.get("pdf_bytes") or 0)
            if pc > 0:
                daily_entries.append({"day": day, "rel": daily_rel, "page_count": pc, "pdf_bytes": pb, "source": "cache-meta"})
                _emit(f"Dia {day} reaproveitado do cache (meta).", processed=processed_days, total=total_range_days, stage="day", day=day, cached=True, page_count=pc, daily_pdf_bytes=pb)
                continue

            if store.blob_exists(daily_rel):
                lp = store.download_to_tmp(daily_rel)
                pb = int(lp.stat().st_size) if lp.exists() else 0
                pc = _pdf_page_count(lp)
                meta_day = {"day": day, "page_count": pc, "pdf_bytes": pb, "source": "cache", "generated_at": dt.datetime.utcnow().isoformat() + "Z"}
                try:
                    store.write_json(daily_meta_rel, meta_day)
                except Exception:
                    pass
                daily_entries.append({"day": day, "rel": daily_rel, "page_count": pc, "pdf_bytes": pb, "source": "cache"})
                _emit(f"Dia {day} reaproveitado do cache.", processed=processed_days, total=total_range_days, stage="day", day=day, cached=True, page_count=pc, daily_pdf_bytes=pb)
                try:
                    lp.unlink()
                except Exception:
                    pass
                continue

        _emit(f"Gerando o relatório para o dia {day}", processed=processed_days, total=total_range_days, stage="day", day=day)
        daily_tmp = store._tmp_path(daily_rel)
        gerar_pdf_diario_detalhado_body(day=day, regs=regs, path_saida=daily_tmp, equipe_ranking=ranking)

        # sobe PDF diário e meta
        uploaded_ok = False
        upload_error = None
        try:
            store.upload_from_tmp(daily_rel, daily_tmp, content_type="application/pdf")
            uploaded_ok = True
        except Exception as e:
            upload_error = e
            try:
                _emit(
                    f"Falha ao subir cache diário do detalhado para {day}; seguindo com arquivo local.",
                    processed=processed_days,
                    total=total_range_days,
                    stage="day",
                    day=day,
                    warning=True,
                )
            except Exception:
                pass

        pb = int(daily_tmp.stat().st_size) if daily_tmp.exists() else 0
        pc = _pdf_page_count(daily_tmp)

        meta_day = {"day": day, "page_count": pc, "pdf_bytes": pb, "source": "generated" if is_hot or force else "rebuild", "generated_at": dt.datetime.utcnow().isoformat() + "Z"}
        try:
            store.write_json(daily_meta_rel, meta_day)
        except Exception:
            pass

        daily_entries.append({
            "day": day,
            "rel": daily_rel,
            "page_count": pc,
            "pdf_bytes": pb,
            "source": meta_day["source"],
            "local_tmp": str(daily_tmp),
            "uploaded_ok": uploaded_ok,
            "upload_error": str(upload_error) if upload_error else "",
        })

        # Só remove o arquivo temporário se ele já estiver no bucket.
        if uploaded_ok:
            try:
                daily_tmp.unlink()
            except Exception:
                pass

    # Capa + Sumário + Merge + Stamp
    gen_pt = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    periodo = f"Período: {format_pt_date(parse_iso_date(start_date))} a {format_pt_date(parse_iso_date(end_date))}"
    kpis = {
        "DDS no período": str(total_regs),
        "Equipes": str(teams),
        "Participações": str(participants),
        "Duração total": formatar_segundos_para_duracao(duration_total_seconds),
    }

    cover_rel = f"build/{key}/cover.pdf"
    toc_rel = f"build/{key}/toc.pdf"
    merged_rel = f"build/{key}/merged.pdf"
    stamped_rel = f"build/{key}/final_stamped.pdf"

    cover_path = store._tmp_path(cover_rel)
    toc_path = store._tmp_path(toc_rel)
    merged_path = store._tmp_path(merged_rel)
    stamped_path = store._tmp_path(stamped_rel)

    _emit("Gerando capa e sumário...", processed=total_range_days, total=total_range_days, stage="toc")
    gerar_pdf_capa(cover_path, titulo="DDS - Relatório Detalhado", periodo=periodo, gerado_em=gen_pt, kpis=kpis)

    toc_entries: List[dict] = []
    page_cursor = 1
    for e in daily_entries:
        day = e["day"]
        pc = int(e.get("page_count") or 0)
        regs = day_groups.get(day) or []
        titulo_dia = (regs[0].get("headerTitle") if regs else "DDS") or "DDS"
        toc_entries.append({
            "data": format_pt_date(parse_iso_date(day)),
            "titulo": str(titulo_dia),
            "pagina": page_cursor,
        })
        page_cursor += pc

    toc_pages = gerar_pdf_sumario(toc_path, entries=toc_entries, header_title="DDS - Relatório Detalhado")

    _emit("Mesclando PDFs...", processed=total_range_days, total=total_range_days, stage="merge")
    merge_inputs: List[Tuple[Path, bool]] = [(cover_path, False), (toc_path, False)]
    for e in daily_entries:
        lp = None

        local_tmp = Path(str(e.get("local_tmp") or "")).expanduser() if e.get("local_tmp") else None
        if local_tmp and local_tmp.exists() and local_tmp.stat().st_size > 0:
            lp = local_tmp
        else:
            try:
                lp = store.download_to_tmp(e["rel"])
            except Exception as ex:
                raise RuntimeError(
                    f"PDF diário ausente para {e.get('day')}: {e.get('rel')} "
                    f"(não encontrado no bucket e sem arquivo local disponível)"
                ) from ex

        merge_inputs.append((lp, True))
    merge_pdfs_with_cleanup(merged_path, merge_inputs)

    _emit("Aplicando cabeçalho/rodapé...", processed=total_range_days, total=total_range_days, stage="stamp")
    stamp_footer_paginacao_geral(
        in_pdf=merged_path,
        out_pdf=stamped_path,
        generation_date_pt=dt.datetime.now().strftime("%d/%m/%Y"),
    )
    _emit("Salvando relatório final no cache...", processed=total_range_days, total=total_range_days, stage="upload")
    store.upload_from_tmp(final_rel, stamped_path, content_type="application/pdf")
    final_pdf_bytes = int(stamped_path.stat().st_size) if stamped_path.exists() else 0

    # limpeza /tmp
    for p in (merged_path, stamped_path, cover_path, toc_path):
        try:
            p.unlink()
        except Exception:
            pass

    meta_persist = {
        "key": key,
        "type": "detalhado",
        "start_date": start_date,
        "end_date": end_date,
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "includes_hot": includes_hot,
        "days": [e["day"] for e in daily_entries],
        "toc_pages": toc_pages,
        "total_regs": total_regs,
        "teams": teams,
        "participants": participants,
        "duration_total_seconds": duration_total_seconds,
        "final_pdf_bytes": final_pdf_bytes,
        "daily_count": len(daily_entries),
    }
    store.write_json(meta_rel, meta_persist)

    urls = _signed_urls()
    meta_return = dict(meta_persist)
    meta_return.update({
        "signed_url": urls.get("inline"),
        "signed_url_download": urls.get("download"),
        "signed_url_expires_seconds": signed_ttl,
    })

    _emit("Relatório final gerado.", processed=total_range_days, total=total_range_days, stage="done", final_pdf_bytes=final_pdf_bytes)
    return ReportResult(key=key, gcs_rel_path=final_rel, meta=meta_return)
