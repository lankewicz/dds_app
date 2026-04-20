"""
============================================================
FILE: dds_report_ranking.py
FUNCTION: Relatório "RANKING" = PDF LEGADO "Presença por Equipe"
          (calendário por mês + % + participações/ausências)
============================================================
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageBreak,
    KeepTogether,
)

from dds_reports_engine import (
    CacheConfig,
    CacheStore,
    ReportResult,
    parse_iso_date,
    daterange,
    format_pt_date,
    gerar_pdf_capa,
    merge_pdfs_with_cleanup,
    stamp_footer_paginacao_geral,
)

# Reuso do carregamento hot/cold já compatibilizado com headerDate flexível
from dds_report_detalhado import _load_day_groups

# -----------------------------
# helpers
# -----------------------------

_MONTHS_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def _month_label_pt(year: int, month: int) -> str:
    return f"{_MONTHS_PT.get(month, str(month))} de {year}"


def _build_key_ranking(start: str, end: str, version: str = "v2") -> str:
    # Mantém o nome como "ranking" (decisão do produto)
    return f"dds_ranking_{start}_{end}_{version}"


def _teams_and_presence(day_groups: Dict[str, List[dict]], days_all: List[str]) -> Tuple[List[str], Dict[str, set], Dict[str, bool], Dict[str, List[str]]]:
    """
    Retorna:
      - lista de equipes (ordenada)
      - present_by_day[day] = set(equipes presentes)
      - has_dds_by_day[day] = True se existe qualquer DDS no dia
      - members_by_team[equipe] = lista (única) de integrantes coletada dos DDS do período
    """
    present_by_day: Dict[str, set] = {}
    has_dds_by_day: Dict[str, bool] = {}
    teams: set = set()
    members: Dict[str, set] = {}

    for day in days_all:
        regs = day_groups.get(day) or []
        has_any = bool(regs)
        has_dds_by_day[day] = has_any
        present = set()

        for r in regs:
            equipe = (r.get("equipe") or "").strip()
            if not equipe:
                continue
            teams.add(equipe)
            present.add(equipe)

            # integrantes (best-effort): união de eletricistas encontrados no período
            for nome in (r.get("eletricistas") or []):
                n = str(nome or "").strip()
                if n:
                    members.setdefault(equipe, set()).add(n)

        present_by_day[day] = present


    # Ranking:
    # 1) maior número de participações
    # 2) nome da equipe (desempate)
    days_with_dds_all = [d for d in days_all if has_dds_by_day.get(d)]

    def _team_rank_key(team: str):
        particip = sum(1 for d in days_with_dds_all if team in (present_by_day.get(d) or set()))
        return (-particip, team.lower())

    teams_sorted = sorted(list(teams), key=_team_rank_key)
    members_by_team = {k: sorted(list(v), key=lambda s: s.lower()) for k, v in members.items()}
    return teams_sorted, present_by_day, has_dds_by_day, members_by_team


def _calendar_grid(
    year: int,
    month: int,
    visible_days: Optional[set[int]] = None,
) -> Tuple[List[List[Optional[int]]], int]:
    """Grid DOM..SAB (7 colunas). Retorna (grid, days_in_month)."""
    first = dt.date(year, month, 1)
     # python weekday: Mon=0..Sun=6 -> queremos Sun=0..Sat=6
    offset = (first.weekday() + 1) % 7
    first = dt.date(year, month, 1)
    # python weekday: Mon=0..Sun=6 -> queremos Sun=0..Sat=6
    offset = (first.weekday() + 1) % 7

    # último dia do mês
    if month == 12:
        next_m = dt.date(year + 1, 1, 1)
    else:
        next_m = dt.date(year, month + 1, 1)
    days_in_month = (next_m - dt.timedelta(days=1)).day

    cells: List[Optional[int]] = [None] * offset + list(range(1, days_in_month + 1))

    if visible_days is not None:
        cells = [
            d if (d is not None and d in visible_days) else None
            for d in cells
        ]

    while len(cells) % 7 != 0:
        cells.append(None)
    grid = [cells[i:i + 7] for i in range(0, len(cells), 7)]
    
    if visible_days is not None:
        while grid and all(v is None for v in grid[0]):
            grid.pop(0)
        while grid and all(v is None for v in grid[-1]):
            grid.pop()
        if not grid:
            grid = [[None] * 7]

    return grid, days_in_month


def _presence_stats_for_month(
    *,
    team: str,
    year: int,
    month: int,
    days_in_scope: List[str],
    present_by_day: Dict[str, set],
    has_dds_by_day: Dict[str, bool],
) -> Tuple[int, int, int]:
    """(participacoes, ausencias, pct_int). Considera somente dias que tiveram DDS."""
    # dias do mês dentro do range
    days_month = [d for d in days_in_scope if d.startswith(f"{year:04d}-{month:02d}-")]
    days_with_dds = [d for d in days_month if has_dds_by_day.get(d)]

    if not days_with_dds:
        return 0, 0, 0

    particip = sum(1 for d in days_with_dds if team in (present_by_day.get(d) or set()))
    aus = len(days_with_dds) - particip
    pct = int(round((particip / max(1, len(days_with_dds))) * 100))
    return particip, aus, pct

def _presence_stats_for_period(
    *,
    team: str,
    start: dt.date,
    end: dt.date,
    present_by_day: Dict[str, set],
    has_dds_by_day: Dict[str, bool],
) -> Tuple[int, int, int]:
    """(participacoes, ausencias, pct_int) considerando o período inteiro."""
    days_period = [d.isoformat() for d in daterange(start, end)]
    days_with_dds = [d for d in days_period if has_dds_by_day.get(d)]

    if not days_with_dds:
        return 0, 0, 0

    particip = sum(1 for d in days_with_dds if team in (present_by_day.get(d) or set()))
    aus = len(days_with_dds) - particip
    pct = int(round((particip / max(1, len(days_with_dds))) * 100))
    return particip, aus, pct

def _legend_table_compact() -> Table:
    """Legenda compacta para caber 3 cards por página."""
    rows = [
        ["", "Participou", "", "Não participou", "", "Sem DDS"]
    ]
    t = Table(rows, colWidths=[0.28 * cm, 1.70 * cm, 0.28 * cm, 2.00 * cm, 0.28 * cm, 1.45 * cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.8),
        ("BACKGROUND", (0, 0), (0, 0), colors.Color(0.20, 0.70, 0.35)),
        ("BACKGROUND", (2, 0), (2, 0), colors.Color(0.85, 0.25, 0.25)),
        ("BACKGROUND", (4, 0), (4, 0), colors.Color(0.75, 0.75, 0.75)),
        ("BOX", (0, 0), (0, 0), 0.2, colors.white),
        ("BOX", (2, 0), (2, 0), 0.2, colors.white),
        ("BOX", (4, 0), (4, 0), 0.2, colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return t


def _stats_table_compact(*, pct: int, particip: int, aus: int, width: float) -> Table:
    rows = [[
        Paragraph(f"<b>{particip}</b><br/><font size='7'>Participações</font>", ParagraphStyle("st1", parent=getSampleStyleSheet()["BodyText"], alignment=TA_CENTER, fontSize=8.5, leading=9.5)),
        Paragraph(f"<b>{aus}</b><br/><font size='7'>Ausências</font>", ParagraphStyle("st2", parent=getSampleStyleSheet()["BodyText"], alignment=TA_CENTER, fontSize=8.5, leading=9.5)),
        Paragraph(f"<b>Presença: {pct}%</b>", ParagraphStyle("st3", parent=getSampleStyleSheet()["BodyText"], alignment=TA_CENTER, fontSize=9.2, leading=10)),
    ]]
    t = Table(rows, colWidths=[width * 0.24, width * 0.22, width * 0.54])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _team_card(
    *,
    team: str,
    members: List[str],
    cal: Table,
    pct: int,
    particip: int,
    aus: int,
    body_width: float,
) -> Table:
    styles = getSampleStyleSheet()
    team_style = ParagraphStyle(
        "team_card_title",
        parent=styles["BodyText"],
        fontSize=10.5,
        leading=11.5,
        alignment=TA_CENTER,
    )
    label_style = ParagraphStyle(
        "team_card_label",
        parent=styles["BodyText"],
        fontSize=8.0,
        leading=9.2,
        alignment=TA_LEFT,
    )
    members_style = ParagraphStyle(
        "team_card_members",
        parent=styles["BodyText"],
        fontSize=7.6,
        leading=8.8,
        alignment=TA_LEFT,
    )

    left_w = body_width * 0.39
    right_w = body_width * 0.61

    members_txt = ", ".join(members) if members else "–"

    left_cell = [
        Paragraph("<b>Equipe:</b>", label_style),
        Paragraph(team, team_style),
        Spacer(1, 0.12 * cm),
        Paragraph("<b>INTEGRANTES:</b>", label_style),
        Paragraph(members_txt, members_style),
    ]

    cal_width = right_w - 10
    try:
        cal._argW = [cal_width / 7.0] * 7
    except Exception:
        pass

    legend = _legend_table_compact()
    stats = _stats_table_compact(pct=pct, particip=particip, aus=aus, width=right_w - 8)

    right_stack = Table(
        [
            [cal],
            [Spacer(1, 0.08 * cm)],
            [legend],
            [Spacer(1, 0.04 * cm)],
            [stats],
        ],
        colWidths=[right_w - 6],
    )
    right_stack.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    outer = Table([[left_cell, right_stack]], colWidths=[left_w, right_w])
    outer.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("LINEAFTER", (0, 0), (0, 0), 0.6, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return outer


def _gerar_pdf_indice_ranking(
    path_saida: Path,
    *,
    entries: List[dict],
    periodo_label: str,
) -> int:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("idx_t", parent=styles["Heading1"], fontSize=17, spaceAfter=8)
    cell_style = ParagraphStyle("idx_c", parent=styles["BodyText"], fontSize=9.2, leading=11)

    doc = SimpleDocTemplate(
        str(path_saida),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=3.0 * cm,
        bottomMargin=1.8 * cm,
        pageCompression=1,
    )

    story: List[Any] = [
        Paragraph("Índice", title_style),
        Paragraph(periodo_label, ParagraphStyle("idx_sub", parent=styles["BodyText"], fontSize=10.2, textColor=colors.grey)),
        Spacer(1, 0.25 * cm),
    ]

    rows: List[list] = [["Pos.", "Equipe", "Página"]]
    for e in entries:
        rows.append([
            Paragraph(str(e.get("ord", "–")), cell_style),
            Paragraph(str(e.get("titulo", "–")), cell_style),
            Paragraph(str(e.get("pagina", "–")), cell_style),
        ])

    table = Table(rows, colWidths=[doc.width * 0.12, doc.width * 0.68, doc.width * 0.20], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
       ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (-1, 0), (-1, -1), "CENTER"),
    ]))
    story.append(table)

    def _on_page(canv, current_doc):
        w, h = A4
        canv.saveState()
        canv.setFont("Helvetica-Bold", 12)
        canv.drawString(2 * cm, h - 1.6 * cm, "DDS - Relatório de Presença por Equipe")
        canv.setFont("Helvetica", 10)
        canv.drawString(2 * cm, h - 2.15 * cm, periodo_label)
        canv.restoreState()

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return len(PdfReader(str(path_saida)).pages)

def _calendar_table_for_team_month(
    *,
    team: str,
    year: int,
    month: int,
    days_in_scope: List[str],
    present_by_day: Dict[str, set],
    has_dds_by_day: Dict[str, bool],
    table_width: Optional[float] = None,
) -> Table:
    """Tabela do calendário com cores por dia."""
    dow = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
    grid, _ = _calendar_grid(year, month)

    visible_days = {
        int(d[-2:])
        for d in days_in_scope
        if d.startswith(f"{year:04d}-{month:02d}-")
    }
    grid, _ = _calendar_grid(year, month, visible_days=visible_days)

    rows: List[List[Any]] = []
    rows.append([
        Paragraph(
            x,
            ParagraphStyle(
                "dow",
                parent=getSampleStyleSheet()["BodyText"],
                alignment=TA_CENTER,
                fontSize=7.8,
                leading=8.2,
            ),
        )
        for x in dow
    ])

    # estilos de background por célula
    style_cmds = [
        ("GRID", (0, 0), (-1, -1), 0.3, colors.Color(0.35, 0.35, 0.35)),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.92, 0.92, 0.92)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 1), (-1, -1), 7.6),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]

    # dias válidos no range (YYYY-MM-DD)
    in_scope = set(days_in_scope)

    for r_idx, week in enumerate(grid, start=1):
        row: List[Any] = []
        for c_idx, day_num in enumerate(week):
            if day_num is None:
                row.append("")
                continue

            day_str = f"{year:04d}-{month:02d}-{day_num:02d}"

            if day_str not in in_scope:
                row.append("")
                continue

            row.append(str(day_num))

            if not has_dds_by_day.get(day_str):
                # sem DDS no dia
                style_cmds.append(("BACKGROUND", (c_idx, r_idx), (c_idx, r_idx), colors.Color(0.75, 0.75, 0.75)))
            else:
                if team in (present_by_day.get(day_str) or set()):
                    style_cmds.append(("BACKGROUND", (c_idx, r_idx), (c_idx, r_idx), colors.Color(0.20, 0.70, 0.35)))
                else:
                    style_cmds.append(("BACKGROUND", (c_idx, r_idx), (c_idx, r_idx), colors.Color(0.85, 0.25, 0.25)))

        rows.append(row)

    usable_width = float(table_width or (A4[0] - 4 * cm))
    col_w = usable_width / 7.0
    t = Table(
        rows,
        colWidths=[col_w] * 7,
        rowHeights=[0.42 * cm] + [0.52 * cm] * (len(rows) - 1),
    )
    t.setStyle(TableStyle(style_cmds))
    return t


def _calendar_table_for_team_period(
    *,
    team: str,
    start: dt.date,
    end: dt.date,
    present_by_day: Dict[str, set],
    has_dds_by_day: Dict[str, bool],
    table_width: Optional[float] = None,
) -> Table:
    """Tabela contínua do período inteiro, sem separar por mês."""
    dow = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]

    all_days = list(daterange(start, end))
    # domingo=0 ... sábado=6
    offset = (start.weekday() + 1) % 7

    cells: List[Optional[dt.date]] = [None] * offset + all_days
    while len(cells) % 7 != 0:
        cells.append(None)
    grid = [cells[i:i + 7] for i in range(0, len(cells), 7)]

    rows: List[List[Any]] = []
    rows.append([
        Paragraph(
            x,
            ParagraphStyle(
                "dow",
                parent=getSampleStyleSheet()["BodyText"],
                alignment=TA_CENTER,
                fontSize=7.8,
                leading=8.2,
            ),
        )
        for x in dow
    ])

    style_cmds = [
        ("GRID", (0, 0), (-1, -1), 0.3, colors.Color(0.35, 0.35, 0.35)),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.92, 0.92, 0.92)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 1), (-1, -1), 7.4),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]

    for r_idx, week in enumerate(grid, start=1):
        row: List[Any] = []
        for c_idx, day_obj in enumerate(week):
            if day_obj is None:
                row.append("")
                continue

            # exibe apenas o dia
            day_str = day_obj.isoformat()
            row.append(day_obj.strftime("%d"))

            if not has_dds_by_day.get(day_str):
                style_cmds.append(("BACKGROUND", (c_idx, r_idx), (c_idx, r_idx), colors.Color(0.75, 0.75, 0.75)))
            else:
                if team in (present_by_day.get(day_str) or set()):
                    style_cmds.append(("BACKGROUND", (c_idx, r_idx), (c_idx, r_idx), colors.Color(0.20, 0.70, 0.35)))
                else:
                    style_cmds.append(("BACKGROUND", (c_idx, r_idx), (c_idx, r_idx), colors.Color(0.85, 0.25, 0.25)))

        rows.append(row)

    usable_width = float(table_width or (A4[0] - 4 * cm))
    col_w = usable_width / 7.0
    t = Table(
        rows,
        colWidths=[col_w] * 7,
        rowHeights=[0.42 * cm] + [0.52 * cm] * (len(rows) - 1),
    )
    t.setStyle(TableStyle(style_cmds))
    return t

def build_or_get_report_ranking(
    *,
    start_date: str,
    end_date: str,
    tz_name: str,
    bucket_name: str,
    cache_prefix: str,
    force: bool = False,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> ReportResult:
    """
    "Ranking" = relatório legado "Presença por Equipe" (calendário mensal).
    """
    if not bucket_name:
        raise ValueError("Bucket de Storage não configurado (DDS_BUCKET_NAME / DDS_REPORTS_BUCKET_NAME).")

    start = parse_iso_date(start_date)
    end = parse_iso_date(end_date)
    if start > end:
        raise ValueError("Data inicial não pode ser maior que a data final.")

    total_range_days = (end - start).days + 1
    signed_ttl = int(os.getenv("DDS_SIGNED_URL_TTL_SECONDS", "3600"))

    def _emit(msg: str, *, processed: int = 0, total: int = 0, stage: str = "", **extra: Any) -> None:
        if not on_progress:
            return
        payload: Dict[str, Any] = {"message": msg, "processed": int(processed), "total": int(total)}
        if stage:
            payload["stage"] = stage
        payload.update(extra or {})
        try:
            on_progress(payload)
        except Exception:
            pass

    key = _build_key_ranking(start_date, end_date)
    final_rel = f"final/{key}.pdf"
    meta_rel = f"final/{key}.meta.json"

    store = CacheStore(CacheConfig(bucket_name=bucket_name, prefix=cache_prefix))
    _emit("Preparando dados (cache/Firestore)...", processed=0, total=total_range_days, stage="prepare")

    # carrega dados com hot/cold (mesma lógica do detalhado)
    day_groups, days_all, days_with_regs, includes_hot, _today, _yesterday = _load_day_groups(
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

    # reuso do PDF final se não inclui hot
    if (not force) and (not includes_hot) and store.blob_exists(final_rel):
        meta_persist = store.read_json(meta_rel) or {}
        urls = _signed_urls()
        meta_return = dict(meta_persist)
        meta_return.update({
            "signed_url": urls.get("inline"),
            "signed_url_download": urls.get("download"),
            "signed_url_expires_seconds": signed_ttl,
        })
        return ReportResult(key=key, gcs_rel_path=final_rel, meta=meta_return)

    teams, present_by_day, has_dds_by_day, members_by_team = _teams_and_presence(day_groups, days_all)
    if not teams:
        raise ValueError("Nenhum DDS encontrado para o período informado.")

    gen_pt = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    periodo_label = f"Período: {format_pt_date(start)} a {format_pt_date(end)}"

    body_rel = f"build/{key}/ranking_body.pdf"
    cover_rel = f"build/{key}/cover.pdf"
    toc_rel = f"build/{key}/toc.pdf"
    merged_rel = f"build/{key}/final_merged.pdf"
    stamped_rel = f"build/{key}/final_stamped.pdf"

    body_path = store._tmp_path(body_rel)
    cover_path = store._tmp_path(cover_rel)
    toc_path = store._tmp_path(toc_rel)
    merged_path = store._tmp_path(merged_rel)
    stamped_path = store._tmp_path(stamped_rel)

    body_path.parent.mkdir(parents=True, exist_ok=True)

    total_days_with_dds = sum(1 for d in days_all if has_dds_by_day.get(d))
    total_particip = sum(len(present_by_day.get(d) or set()) for d in days_all if has_dds_by_day.get(d))
    kpis = {
        "Equipes": str(len(teams)),
        "Dias no intervalo": str(len(days_all)),
        "Dias com DDS": str(total_days_with_dds),
        "Participações": str(total_particip),
    }

    body_doc = SimpleDocTemplate(
        str(body_path),
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=2.4 * cm,
        bottomMargin=1.4 * cm,
        pageCompression=1,
    )

    def _on_body_page(canv, doc):
        w, h = A4
        canv.saveState()
        canv.setFont("Helvetica-Bold", 11.5)
        canv.drawString(1.5 * cm, h - 1.35 * cm, "DDS - Relatório de Presença por Equipe")
        canv.setFont("Helvetica", 9.5)
        canv.drawString(1.5 * cm, h - 1.9 * cm, f"{format_pt_date(start)} a {format_pt_date(end)}")
        canv.restoreState()

    story: List[Any] = []
    toc_base_entries: List[dict] = []
    cards_per_page = 3

    for idx, team in enumerate(teams, start=1):
        # MANTER A SUA HELPER DE PERÍODO JÁ FUNCIONANDO NO AMBIENTE LOCAL
        particip, aus, pct = _presence_stats_for_period(
            team=team,
            start=start,
            end=end,
            present_by_day=present_by_day,
            has_dds_by_day=has_dds_by_day,
        )

        # MANTER A SUA HELPER DE CALENDÁRIO CONTÍNUO JÁ FUNCIONANDO NO AMBIENTE LOCAL
        cal = _calendar_table_for_team_period(
            team=team,
            start=start,
            end=end,
            present_by_day=present_by_day,
            has_dds_by_day=has_dds_by_day,
            table_width=body_doc.width * 0.61 - 10,
        )

        card = _team_card(
            team=team,
            members=members_by_team.get(team, []),
            cal=cal,
            pct=pct,
            particip=particip,
            aus=aus,
            body_width=body_doc.width,
        )

        story.append(KeepTogether([card]))
        if idx < len(teams):
            story.append(Spacer(1, 0.18 * cm))
        if idx % cards_per_page == 0 and idx < len(teams):
            story.append(PageBreak())

        toc_base_entries.append({
            "ord": idx,
            "titulo": team,
        })

    _emit("Gerando corpo do PDF...", processed=total_range_days, total=total_range_days, stage="pdf", teams=len(teams))
    body_doc.build(story, onFirstPage=_on_body_page, onLaterPages=_on_body_page)

    _emit("Gerando capa e índice...", processed=total_range_days, total=total_range_days, stage="toc")
    gerar_pdf_capa(
        cover_path,
        titulo="DDS - Relatório de Presença por Equipe",
        periodo=periodo_label,
        gerado_em=gen_pt,
        kpis=kpis,
    )

    toc_pages_guess = 1
    toc_pages = 1
    for _ in range(4):
        toc_entries: List[dict] = []
        body_start_page = toc_pages_guess + 2  # capa (1) + páginas do índice + 1ª do corpo
        for i, entry in enumerate(toc_base_entries):
            toc_entries.append({
                "ord": entry["ord"],
                "titulo": entry["titulo"],
                "pagina": body_start_page + (i // cards_per_page),
            })

        toc_pages = _gerar_pdf_indice_ranking(
            toc_path,
            entries=toc_entries,
            periodo_label=periodo_label,
        )
        if toc_pages == toc_pages_guess:
            break
        toc_pages_guess = toc_pages

    _emit("Mesclando PDFs...", processed=total_range_days, total=total_range_days, stage="merge")
    merge_pdfs_with_cleanup(
        merged_path,
        [
            (cover_path, False),
            (toc_path, False),
            (body_path, True),
        ],
    )

    stamp_footer_paginacao_geral(
        in_pdf=merged_path,
        out_pdf=stamped_path,
        generation_date_pt=gen_pt,
    )

    _emit("Salvando no cache...", processed=total_range_days, total=total_range_days, stage="upload")
    store.upload_from_tmp(final_rel, stamped_path, content_type="application/pdf")

    final_bytes = int(stamped_path.stat().st_size) if stamped_path.exists() else 0


    meta_persist = {
        "key": key,
        "type": "ranking",
        "start_date": start_date,
        "end_date": end_date,
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "includes_hot": includes_hot,
        "teams": len(teams),
        "cards_per_page": 3,
        "final_pdf_bytes": final_bytes,
    }
    store.write_json(meta_rel, meta_persist)

    urls = _signed_urls()
    meta_return = dict(meta_persist)
    meta_return.update({
        "signed_url": urls.get("inline"),
        "signed_url_download": urls.get("download"),
        "signed_url_expires_seconds": signed_ttl,
    })
    # limpa tmp do build
    for p in (cover_path, toc_path, merged_path, stamped_path):
        try:
            p.unlink()
        except Exception:
            pass

    _emit("Concluído.", processed=total_range_days, total=total_range_days, stage="done")
    return ReportResult(key=key, gcs_rel_path=final_rel, meta=meta_return)