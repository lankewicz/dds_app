"""dds_reports_engine.py

Relatórios DDS (execução) no Cloud Run.

Objetivos:
  - Seleção por range (data inicial/final)
  - Preview no browser (iframe) + download
  - Cache em 2 níveis:
      L1: /tmp (instância)
      L2: Cloud Storage (pasta/prefixo configurável)
  - Política hot/cold:
      * hoje e ontem: sempre reconsulta Firestore e regenera artefatos
      * anteriores: usa cache (JSON diário + PDF diário)

Modelo de paginação:
  - Capa: conta na paginação geral, mas sem número impresso
  - Sumário: arábico contínuo dentro da paginação geral
  - Corpo: segue a paginação física total do relatório

Para preservar o cache diário sem quebrar a numeração por intervalo,
os PDFs diários são gerados com cabeçalho estático (sem página fixa) e a
paginação geral é aplicada apenas no PDF final, com overlay leve de texto.
""" 

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import io
import logging
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Callable
from functools import lru_cache

from google.cloud import storage


# -----------------------------
# Firestore (firebase-admin)
# -----------------------------
try:
    import firebase_admin
    from firebase_admin import firestore
except Exception:  # pragma: no cover
    firebase_admin = None
    firestore = None


def _ensure_firebase() -> None:
    if firebase_admin is None or firestore is None:
        raise RuntimeError("firebase-admin não está disponível")
    if firebase_admin._apps:
        return
    # Cloud Run: ADC via service account do serviço
    firebase_admin.initialize_app()


def _firestore_client():
    _ensure_firebase()
    return firestore.client()


# -----------------------------
# PDF deps
# -----------------------------
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, Flowable
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.units import cm
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader

from pypdf import PdfReader, PdfWriter

import aiohttp

from dds_reports_image_pipeline import (
    THUMB_CACHE_JPEG_QUALITY,
    THUMB_CACHE_MAX_BYTES,
    THUMB_CACHE_MAX_PX,
    normalize_image_inplace,
    prepare_thumb_for_pdf,
)

# =============================
# Cache leve de assets PDF
# =============================


@lru_cache(maxsize=8)
def _load_image_reader(path: str) -> Optional[ImageReader]:
    try:
        if path and os.path.exists(path):
            return ImageReader(path)
    except Exception:
        pass
    return None


@lru_cache(maxsize=4)
def _logo_assets(base_dir_str: str) -> Tuple[Optional[str], Optional[str], Optional[Any], Optional[Any], Optional[float]]:
    base_dir = Path(base_dir_str)
    logo_left, logo_right = _logo_paths(base_dir)

    left_reader = _load_image_reader(logo_left) if logo_left else None
    right_reader = _load_image_reader(logo_right) if logo_right else None

    logo_right_width = None
    if right_reader:
        try:
            w0, h0 = right_reader.getSize()
            if h0:
                logo_right_width = (1.2 * cm) * (float(w0) / float(h0))
        except Exception:
            logo_right_width = None

    return logo_left, logo_right, left_reader, right_reader, logo_right_width


def _draw_header_footer(
   canv: Any,
    doc: Any,
    *,
    titulo: str,
    page_label: Optional[str],
    generation_date_pt: Optional[str],
    logo_left_reader: Optional[Any],
    logo_right_reader: Optional[Any],
    logo_right_width: Optional[float],
    draw_header: bool = True,
    draw_footer: bool = True,
) -> None:
    w, h = doc.pagesize
    left_margin = float(doc.leftMargin)
    right_margin = float(doc.rightMargin)
    bottom_margin = float(doc.bottomMargin)

    largura_util = w - left_margin - right_margin
    altura_logo_cm = 1.2
    y_pos_logos = h - (1.2 * cm) - (altura_logo_cm * cm)
    y_pos_titulo = h - (1.8 * cm)

    canv.saveState()

    if draw_header:
        if logo_left_reader:
            try:
                canv.drawImage(
                    logo_left_reader,
                    left_margin,
                    y_pos_logos,
                    height=altura_logo_cm * cm,
                    preserveAspectRatio=True,
                    mask="auto",
                    anchor="sw",
                )
            except Exception:
                pass

        coluna2_x_inicio = left_margin + (largura_util * 0.20)
        largura_coluna2 = largura_util * 0.60
        linhas = str(titulo).splitlines()
        canv.setFont("Helvetica-Bold", 14)
        line_height = 16
        total_height = line_height * len(linhas)
        y_atual = y_pos_titulo + (total_height / 2) - line_height
        for linha in linhas:
            canv.drawCentredString(coluna2_x_inicio + (largura_coluna2 / 2), y_atual, linha)
            y_atual -= line_height

        if logo_right_reader and logo_right_width:
            try:
                coluna3_x_final = w - right_margin
                logo_x = coluna3_x_final - float(logo_right_width)
                canv.drawImage(
                    logo_right_reader,
                    logo_x,
                    y_pos_logos,
                    width=float(logo_right_width),
                    height=altura_logo_cm * cm,
                    preserveAspectRatio=True,
                    mask="auto",
                    anchor="sw",
                )
            except Exception:
                pass

    if draw_footer:
        canv.setFont("Helvetica", 9)
        if generation_date_pt:
            canv.drawString(left_margin, bottom_margin / 2, f"Data da geração: {generation_date_pt}")
        if page_label:
            canv.drawCentredString(w / 2, bottom_margin / 2, f"Página {page_label}")

    canv.restoreState()

# =============================
# Utilidades
# =============================


def parse_iso_date(value: str) -> dt.date:
    value = (value or "").strip()
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def format_pt_date(d: dt.date) -> str:
    return d.strftime("%d/%m/%Y")


def daterange(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    cur = start
    while cur <= end:
        yield cur
        cur += dt.timedelta(days=1)


def roman_lower(n: int) -> str:
    # 1..3999
    if n <= 0:
        return ""
    vals = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    out = []
    x = n
    for v, s in vals:
        while x >= v:
            out.append(s)
            x -= v
    return "".join(out).lower()


def sha1_hex(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()


def parse_duracao_para_segundos(duracao_str: str) -> int:
    import re
    if not isinstance(duracao_str, str):
        return 0
    minutos, segundos = 0, 0
    m = re.search(r"(\d+)\s*min", duracao_str, re.IGNORECASE)
    if m:
        minutos = int(m.group(1))
    s = re.search(r"(\d+)\s*s", duracao_str, re.IGNORECASE)
    if s:
        segundos = int(s.group(1))
    if minutos == 0 and segundos == 0 and duracao_str.strip().isdigit():
        segundos = int(duracao_str.strip())
    return minutos * 60 + segundos


def formatar_segundos_para_duracao(total_segundos: int) -> str:
    if total_segundos < 0:
        total_segundos = 0
    m, s = divmod(total_segundos, 60)
    return f"{m}min {s}s"


# =============================
# Cache (L1: /tmp, L2: GCS)
# =============================


@dataclass(frozen=True)
class CacheConfig:
    bucket_name: str
    prefix: str
    tmp_root: Path = Path("/tmp/dds_reports")


class CacheStore:
    def __init__(self, cfg: CacheConfig):
        self.cfg = cfg
        self.client = storage.Client()
        self.bucket = self.client.bucket(cfg.bucket_name)

        self.cfg.tmp_root.mkdir(parents=True, exist_ok=True)

    def _obj(self, rel: str) -> str:
        rel = rel.lstrip("/")
        pref = (self.cfg.prefix or "").strip().strip("/")
        return f"{pref}/{rel}" if pref else rel

    def _tmp_path(self, rel: str) -> Path:
        # mantém subpastas
        p = self.cfg.tmp_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def blob_exists(self, rel: str, *, timeout: float = 5.0) -> bool:
        blob = self.bucket.blob(self._obj(rel))
        try:
            return bool(blob.exists(client=self.client, timeout=timeout))
        except Exception as e:
            logging.warning("GCS blob_exists falhou (rel=%s): %s", rel, e)
            return False

    def download_to_tmp(self, rel: str, *, timeout: float = 60.0) -> Path:
        lp = self._tmp_path(rel)
        if lp.exists() and lp.stat().st_size > 0:
            return lp
        blob = self.bucket.blob(self._obj(rel))
        blob.download_to_filename(str(lp), timeout=timeout)
        return lp

    def upload_from_tmp(self, rel: str, local_path: Path, *, content_type: str, timeout: float = 60.0) -> None:
        blob = self.bucket.blob(self._obj(rel))
        blob.upload_from_filename(str(local_path), content_type=content_type, timeout=timeout)  


    def generate_signed_url(
        self,
        rel: str,
        *,
        expires_seconds: int = 3600,
        disposition: str = "inline",
        filename: Optional[str] = None,
        response_type: Optional[str] = None,
    ) -> Optional[str]:
        """Gera Signed URL (v4) para um objeto do cache no GCS.

        - disposition: "inline" (preview) ou "attachment" (download)
        - filename: nome sugerido no Content-Disposition
        """
        try:
            blob = self.bucket.blob(self._obj(rel))
            if not filename:
                filename = Path(rel).name
            response_disposition = f'{disposition}; filename="{filename}"'
            url = blob.generate_signed_url(
                version="v4",
                expiration=dt.timedelta(seconds=int(expires_seconds)),
                method="GET",
                response_disposition=response_disposition,
                response_type=response_type,
            )
            return url
        except Exception as e:
            logging.warning("Falha ao gerar signed URL (rel=%s): %s", rel, e)
            return None

    def read_json(self, rel: str) -> Optional[dict]:
        try:
            lp = self.download_to_tmp(rel)
            return json.loads(lp.read_text("utf-8"))
        except Exception:
            return None

    def write_json(self, rel: str, payload: dict) -> None:
        lp = self._tmp_path(rel)
        lp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
        self.upload_from_tmp(rel, lp, content_type="application/json")


# =============================
# Imagens (cache por URL)
# =============================


def _is_probably_jpeg(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(2) == b"\xff\xd8"
    except Exception:
        return False

class ImageCache:
    def __init__(self, store: CacheStore):
        self.store = store

    def _rel_for_url(self, url: str) -> str:
        # guarda como jpg/bin, mas preserva extensão se vier
        h = sha1_hex(url)
        return f"img-cache/{h}.bin"

    def local_path_for_url(self, url: str) -> Path:
        rel = self._rel_for_url(url)
        return self.store._tmp_path(rel)

    async def ensure_cached(self, urls: List[str], *, stats: Optional[Dict[str, int]] = None) -> Dict[str, Path]:
        """Garante que as URLs estejam cacheadas localmente (/tmp) e, se possível, no GCS.

        Também normaliza (best-effort) o cache para JPEG reduzido, sem tocar no arquivo/origem original.
        """
        urls = [u for u in (urls or []) if u]
        urls_unique = list(dict.fromkeys(urls))
        out: Dict[str, Path] = {}

        def bump(k: str, v: int = 1) -> None:
            if stats is None:
                return
            stats[k] = int(stats.get(k, 0)) + int(v)

        async def maybe_normalize_and_upload(u: str, lp: Path) -> None:
            """Normaliza cache local e re-sobe pro GCS (best-effort)."""
            try:
                if (not lp.exists()) or lp.stat().st_size <= 0:
                    return

                size0 = int(lp.stat().st_size)
                is_jpeg = _is_probably_jpeg(lp)
                bump("bytes_in", size0)

                # critério: se não for JPEG ou estiver grande demais, normaliza
                if (not is_jpeg) or (size0 > THUMB_CACHE_MAX_BYTES):
                    changed = await asyncio.to_thread(
                        _normalize_image_inplace,
                        lp,
                        max_px=THUMB_CACHE_MAX_PX,
                        quality=THUMB_CACHE_JPEG_QUALITY,
                    )
                    if changed:
                        bump("normalized", 1)
                        size1 = int(lp.stat().st_size) if lp.exists() else 0
                        bump("bytes_out", size1)
                        # upload best-effort como image/jpeg (mesmo rel .bin)
                        try:
                            rel = self._rel_for_url(u)
                            await asyncio.to_thread(self.store.upload_from_tmp, rel, lp, content_type="image/jpeg")
                        except Exception:
                            pass
                    else:
                        bump("normalized_skipped", 1)
                else:
                    bump("normalized_skipped", 1)
                    bump("bytes_out", size0)
            except Exception:
                bump("normalized_errors", 1)

        # 1) se já existe local, ok
        to_check_gcs: List[str] = []
        for u in urls_unique:
            lp = self.local_path_for_url(u)
            if lp.exists() and lp.stat().st_size > 0:
                out[u] = lp
                bump("cache_hit_local", 1)
                await maybe_normalize_and_upload(u, lp)
            else:
                to_check_gcs.append(u)

        # 2) se existe no GCS, baixa (CONCORRENTE + timeout)
        to_download: List[str] = []
        if to_check_gcs:
            sem_gcs = asyncio.Semaphore(16)

            async def _check_one(u: str) -> Tuple[str, Optional[Path]]:
                rel = self._rel_for_url(u)
                async with sem_gcs:
                    try:
                        exists = await asyncio.to_thread(self.store.blob_exists, rel, timeout=3.0)
                        if not exists:
                            return (u, None)
                        lp = await asyncio.to_thread(self.store.download_to_tmp, rel, timeout=45.0)
                        if lp.exists() and lp.stat().st_size > 0:
                            return (u, lp)
                    except Exception:
                        return (u, None)
                return (u, None)

            checked = await asyncio.gather(*[_check_one(u) for u in to_check_gcs])
            for u, lp in checked:
                if lp is not None:
                    out[u] = lp
                    bump("cache_hit_gcs", 1)
                    await maybe_normalize_and_upload(u, lp)
                else:
                    to_download.append(u)

        # 3) baixa por HTTP (concorrente) e sobe pro GCS
        if to_download:
            timeout = aiohttp.ClientTimeout(total=30)
            sem = asyncio.Semaphore(10)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async def _fetch(u: str) -> Tuple[str, Optional[bytes]]:
                    async with sem:
                        for _ in range(3):
                            try:
                                async with session.get(u) as r:
                                    if r.status == 200:
                                        return u, await r.read()
                            except Exception:
                                await asyncio.sleep(0.5)
                        return u, None

                results = await asyncio.gather(*[_fetch(u) for u in to_download])
                for u, data in results:
                    if not data:
                        bump("download_failed", 1)
                        continue

                    bump("downloaded", 1)
                    rel = self._rel_for_url(u)
                    lp = self.store._tmp_path(rel)
                    try:
                        lp.write_bytes(data)
                        out[u] = lp
                        await maybe_normalize_and_upload(u, lp)

                        # upload best-effort (se já normalizou vira image/jpeg)
                        try:
                            ct = "image/jpeg" if _is_probably_jpeg(lp) else "application/octet-stream"
                            self.store.upload_from_tmp(rel, lp, content_type=ct)
                        except Exception:
                            pass
                    except Exception:
                        bump("download_errors", 1)
                        continue
        if stats is not None:
            stats["total"] = len(urls_unique)
        return out


# =============================
# Firestore -> dataset diário
# =============================


def _normalize_dds_doc(d: dict) -> Optional[dict]:
    """Normaliza um documento DDS para o formato usado nos PDFs."""
    header_date = (d.get("headerDate") or "").strip()
    if not header_date:
        return None

    # duracao em segundos (com regra +120s se 0 < t < 120)
    total_segundos = parse_duracao_para_segundos(d.get("duracao", "0s"))
    if 0 < total_segundos < 120:
        total_segundos += 120

    return {
        "headerDate": header_date,
        "headerTitle": d.get("headerTitle", "–"),
        "equipe": d.get("equipe", "–"),
        "dataHora": d.get("dataHora", "–"),
        "duracao": formatar_segundos_para_duracao(total_segundos),
        "duracao_seg": total_segundos,
        "eletricistas": d.get("eletricistas", []) or [],
        "tema": d.get("tema", "–"),
        "thumbUrl": d.get("thumbUrl"),
        "fotoUrl": d.get("fotoUrl"),
    }


def fetch_dds_range(start_date: str, end_date: str) -> Dict[str, List[dict]]:
    """Busca DDS no Firestore por range de headerDate (YYYY-MM-DD)."""
    db = _firestore_client()

    # Query por range no mesmo campo
    q = (
        db.collection("DDS")
        .where("headerDate", ">=", start_date)
        .where("headerDate", "<=", end_date)
        .order_by("headerDate")
    )

    groups: Dict[str, List[dict]] = {}
    for doc in q.stream():
        raw = doc.to_dict() or {}
        norm = _normalize_dds_doc(raw)
        if not norm:
            continue
        day = norm["headerDate"]
        groups.setdefault(day, []).append(norm)

    return groups


def fetch_dds_day(day: str) -> List[dict]:
    db = _firestore_client()
    q = db.collection("DDS").where("headerDate", "==", day)
    out: List[dict] = []
    for doc in q.stream():
        raw = doc.to_dict() or {}
        norm = _normalize_dds_doc(raw)
        if norm:
            out.append(norm)
    return out


def _rank_equipes(groups_by_day: Dict[str, List[dict]]) -> Dict[str, int]:
    """Ranking por presença (1 por equipe por dia)."""
    seen: set[Tuple[str, str]] = set()
    counts: Dict[str, int] = {}
    for day, regs in (groups_by_day or {}).items():
        for r in regs:
            equipe = (r.get("equipe") or "").strip()
            if not equipe:
                continue
            k = (equipe, day)
            if k in seen:
                continue
            seen.add(k)
            counts[equipe] = counts.get(equipe, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0].lower())))


# =============================
# PDF: corpo diário (com fotos, sem header/footer)
# =============================


class ClickableImage(Flowable):
    def __init__(self, img: Image, url: str):
        super().__init__()
        self.img = img
        self.url = url
        w, h = img.wrap(0, 0)
        self.width, self.height = w, h

    def draw(self):
        canv = self.canv
        x, y = 0, 0
        self.img.drawOn(canv, x, y)
        if self.url:
            canv.linkURL(self.url, (x, y, x + self.width, y + self.height), relative=1, thickness=0)


def gerar_pdf_diario_com_fotos_body(
    *,
    day: str,
    regs: List[dict],
    path_saida: Path,
    image_paths: Dict[str, Path],
    equipe_ranking: Dict[str, int],
    header_title: str = "DDS - Relatório com Fotos",
    base_dir: Optional[Path] = None,
):
    """Gera o PDF diário (apenas corpo) para um dia (YYYY-MM-DD)."""
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("Cell", parent=styles["BodyText"], alignment=TA_LEFT, leading=12)
    title_style = ParagraphStyle("SessionTitle", parent=styles["Heading2"], alignment=TA_LEFT, spaceBefore=12)

    # Margens: mantemos as mesmas do relatório atual (top=3cm, bottom=2cm)
    doc = SimpleDocTemplate(
        str(path_saida),
        pagesize=landscape(A4),
        topMargin=3 * cm,
        bottomMargin=2 * cm,
        pageCompression=1,
    )
    usable_width = doc.width
    story: List[Any] = []

    # Ordenação por ranking (presenças desc) e nome
    registros = sorted(
        regs or [],
        key=lambda r: (-int(equipe_ranking.get((r.get("equipe") or "").strip(), 0)), (r.get("equipe") or "").lower()),
    )

    # Cabeçalho do dia (conteúdo, não header/footer)
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

    data_rows: List[list] = [["Equipe", "Duração", "Qtd", "Participantes", "Tema", "Foto"]]

    THUMB_W, THUMB_H = 60, 45
    pdf_thumb_dir = path_saida.parent / "pdf_opt" / day

    for r in registros:
        url_thumb = (r.get("thumbUrl") or r.get("fotoUrl") or "").strip()
        link_final = (r.get("fotoUrl") or r.get("thumbUrl") or "").strip() or None

        thumb_flowable: Any = Paragraph("–", cell_style)
        if url_thumb and url_thumb in image_paths:
            local_raw = image_paths[url_thumb]
            final_path = prepare_thumb_for_pdf(local_raw, pdf_thumb_dir, THUMB_W, THUMB_H)
            if final_path.exists():
                img_obj = Image(str(final_path), width=THUMB_W, height=THUMB_H)
                thumb_flowable = ClickableImage(img_obj, link_final) if link_final else img_obj

        # fallback: link textual se falhou
        if isinstance(thumb_flowable, Paragraph) and link_final:
            thumb_flowable = Paragraph(f'<link href="{link_final}"><u>Link</u></link>', cell_style)

        participantes = "<br/>".join(r.get("eletricistas", []) or []) or "–"

        data_rows.append([
            Paragraph(r.get("equipe", "–"), cell_style),
            str(r.get("duracao", "–")),
            str(len(r.get("eletricistas", []) or [])),
            Paragraph(participantes, cell_style),
            Paragraph(r.get("tema", "–"), cell_style),
            thumb_flowable,
        ])

    col_widths = [usable_width * x for x in [0.13, 0.07, 0.06, 0.26, 0.30, 0.18]]
    table = Table(data_rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))

    base_dir = base_dir or Path(__file__).resolve().parent
    _, _, logo_left_reader, logo_right_reader, logo_right_width = _logo_assets(str(base_dir.resolve()))
    def _on_page(canv: Any, current_doc: Any) -> None:
        _draw_header_footer(
            canv,
            current_doc,
            titulo=header_title,
            page_label=None,
            generation_date_pt=None,
            logo_left_reader=logo_left_reader,
            logo_right_reader=logo_right_reader,
            logo_right_width=logo_right_width,
            draw_header=True,
            draw_footer=False,
        )

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)


# =============================
# PDF: capa + sumário
# =============================


def _logo_paths(base_dir: Path) -> Tuple[Optional[str], Optional[str]]:
    # Preferir logos "Relat" (para igualar o BackEnd), fallback para os padrões.
    candidates_left = [
        base_dir / "assets" / "logo_chico_Relat.png",
        base_dir / "assets" / "logo_chico_relat.png",
        base_dir / "assets" / "logo_chico.png",
    ]
    candidates_right = [
        base_dir / "assets" / "logo_dds_Relat.png",
        base_dir / "assets" / "logo_dds_relat.png",
        base_dir / "assets" / "logo_dds.png",
    ]

    left = next((str(p) for p in candidates_left if p.exists()), None)
    right = next((str(p) for p in candidates_right if p.exists()), None)
    return left, right


def gerar_pdf_capa(path_saida: Path, *, titulo: str, periodo: str, gerado_em: str, kpis: Dict[str, str]) -> None:
    w, h = landscape(A4)
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(w, h), pageCompression=1)

    base_dir = Path(__file__).resolve().parent
    logo_left, logo_right = _logo_paths(base_dir)

    # fundo simples
    c.setFillColor(colors.white)
    c.rect(0, 0, w, h, fill=1, stroke=0)

    # logos
    top_y = h - 2.2 * cm
    if logo_left:
        c.drawImage(logo_left, 2.0 * cm, top_y, height=1.6 * cm, preserveAspectRatio=True, mask='auto')
    if logo_right:
        c.drawImage(logo_right, w - 4.0 * cm, top_y, height=1.6 * cm, preserveAspectRatio=True, mask='auto')

    # título
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(w / 2, h - 3.2 * cm, titulo)
    c.setFont("Helvetica", 12)
    c.drawCentredString(w / 2, h - 4.1 * cm, periodo)

    # KPIs
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2.0 * cm, h - 6.0 * cm, "Resumo")
    c.setFont("Helvetica", 11)
    y = h - 6.8 * cm
    for label, val in kpis.items():
        c.drawString(2.2 * cm, y, f"{label}: {val}")
        y -= 0.65 * cm

    c.setFont("Helvetica", 10)
    c.drawString(2.0 * cm, 2.0 * cm, f"Gerado em: {gerado_em}")

    c.showPage()
    c.save()

    path_saida.write_bytes(buf.getvalue())


def gerar_pdf_sumario(
    path_saida: Path,
    *,
    entries: List[dict],
    header_title: str = "DDS - Relatório com Fotos",
    base_dir: Optional[Path] = None,
) -> int:
    """Gera um PDF com o sumário e cabeçalho estático. Retorna o número de páginas."""
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("T", parent=styles["Heading1"], fontSize=18, spaceAfter=10)
    cell_style = ParagraphStyle("Cell", parent=styles["BodyText"], alignment=TA_LEFT, leading=12)

    doc = SimpleDocTemplate(
        str(path_saida),
        pagesize=landscape(A4),
        topMargin=3 * cm,
        bottomMargin=2 * cm,
        pageCompression=1,
    )
    story: List[Any] = []
    story.append(Paragraph("Sumário", title_style))
    story.append(Spacer(1, 6))

    rows: List[list] = [["Data", "Título", "Página"]]
    for e in entries:
        rows.append([
            Paragraph(e.get("data", "–"), cell_style),
            Paragraph(e.get("titulo", "–"), cell_style),
            Paragraph(str(e.get("pagina", "–")), cell_style),
        ])

    table = Table(rows, colWidths=[doc.width * 0.18, doc.width * 0.67, doc.width * 0.15], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (-1, 0), (-1, -1), "CENTER"),
    ]))
    story.append(table)

    base_dir = base_dir or Path(__file__).resolve().parent
    _, _, logo_left_reader, logo_right_reader, logo_right_width = _logo_assets(str(base_dir.resolve()))
    def _on_page(canv: Any, current_doc: Any) -> None:
        _draw_header_footer(
            canv,
            current_doc,
            titulo=header_title,
            page_label=None,
            generation_date_pt=None,
            logo_left_reader=logo_left_reader,
            logo_right_reader=logo_right_reader,
            logo_right_width=logo_right_width,
            draw_header=True,
            draw_footer=False,
        )

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return len(PdfReader(str(path_saida)).pages)


# =============================
# PDF: merge + stamp (header/footer + paginação B)
# =============================


def _make_footer_overlay_page(
    *,
    page_size: Tuple[float, float],
    left_margin: float,
    bottom_margin: float,
    page_label: Optional[str],
    generation_date_pt: Optional[str],
) -> Any:
    w, h = page_size
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(w, h), pageCompression=1)

    c.setFont("Helvetica", 9)
    if generation_date_pt:
        c.drawString(left_margin, bottom_margin / 2, f"Data da geração: {generation_date_pt}")
    if page_label:
        c.drawCentredString(w / 2, bottom_margin / 2, f"Página {page_label}")

    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def stamp_footer_paginacao_geral(
    *,
    in_pdf: Path,
    out_pdf: Path,
    generation_date_pt: str,
) -> None:
    """Aplica rodapé textual leve com paginação geral contínua.

    Regras:
      - capa conta como página 1, mas não recebe número impresso;
      - demais páginas recebem numeração arábica contínua física do PDF.
    """
    reader = PdfReader(str(in_pdf))
    writer = PdfWriter()

    left_margin = 72  # 1 inch
    bottom_margin = 2 * cm


    for idx, page in enumerate(reader.pages):
        if idx == 0:
            writer.add_page(page)
            continue

        overlay = _make_footer_overlay_page(
            page_size=(float(page.mediabox.width), float(page.mediabox.height)),
            left_margin=left_margin,
            bottom_margin=float(bottom_margin),
            page_label=str(idx + 1),
            generation_date_pt=generation_date_pt,
        )
        page.merge_page(overlay)
        writer.add_page(page)

    out_pdf.write_bytes(b"")
    with out_pdf.open("wb") as f:
        writer.write(f)


def merge_pdfs(output_path: Path, inputs: List[Path]) -> None:
    writer = PdfWriter()
    for p in inputs:
        r = PdfReader(str(p))
        for page in r.pages:
            writer.add_page(page)
    with output_path.open("wb") as f:
        writer.write(f)




def merge_pdfs_with_cleanup(output_path: Path, inputs: List[Tuple[Path, bool]]) -> None:
    """Merge de PDFs lendo um a um e podendo remover arquivos temporários.

    inputs: lista de (path, delete_after_read)
    """
    writer = PdfWriter()
    for p, delete_after in inputs:
        try:
            with p.open("rb") as fh:
                r = PdfReader(fh)
                for page in r.pages:
                    writer.add_page(page)
        finally:
            if delete_after:
                try:
                    p.unlink()
                except Exception:
                    pass
    with output_path.open("wb") as f:
        writer.write(f)


# =============================
# Orquestração (relatório com fotos)
# =============================


@dataclass(frozen=True)
class ReportResult:
    key: str
    gcs_rel_path: str
    meta: dict


def _build_key_photos(start: str, end: str, version: str = "v1") -> str:
    return f"dds_fotos_{start}_{end}_1_{version}"


def _tz_today_yesterday(tz_name: str) -> Tuple[dt.date, dt.date]:
    try:
        from zoneinfo import ZoneInfo
        now = dt.datetime.now(ZoneInfo(tz_name))
    except Exception:
        now = dt.datetime.now()
    today = now.date()
    return today, today - dt.timedelta(days=1)


def build_or_get_report_photos(
    *,
    start_date: str,
    end_date: str,
    tz_name: str,
    bucket_name: str,
    cache_prefix: str,
    force: bool = False,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> ReportResult:
    """Gera (ou reaproveita) o relatório com fotos para o range."""
    if not bucket_name:
        raise ValueError("Bucket de Storage não configurado (DDS_BUCKET_NAME / DDS_REPORTS_BUCKET_NAME).")

    start = parse_iso_date(start_date)
    end = parse_iso_date(end_date)
    if start > end:
        raise ValueError("Data inicial não pode ser maior que a data final.")

    total_range_days = (end - start).days + 1
    signed_ttl = int(os.getenv("DDS_SIGNED_URL_TTL_SECONDS", "3600"))

    def _emit(message: str, *, processed: int = 0, total: int = 0, day: Optional[str] = None, **extra: Any) -> None:
        if not on_progress:
            return
        payload: Dict[str, Any] = {
            "message": message,
            "processed": int(processed),
            "total": int(total),
        }
        if day:
            payload["day"] = day
        if extra:
            payload.update(extra)
        try:
            on_progress(payload)
        except Exception:
            pass

    key = _build_key_photos(start_date, end_date)
    final_rel = f"final/{key}.pdf"
    meta_rel = f"final/{key}.meta.json"

    store = CacheStore(CacheConfig(bucket_name=bucket_name, prefix=cache_prefix))
    _emit("Preparando dados (cache/Firestore)...", processed=0, total=total_range_days, stage="prepare")
    base_dir = Path(__file__).resolve().parent
    generation_date_pt = dt.datetime.now().strftime("%d/%m/%Y")

    today, yesterday = _tz_today_yesterday(tz_name)
    includes_hot = any(d in (today, yesterday) for d in daterange(start, end))

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

    # Se não inclui hot dates, podemos reaproveitar o PDF final do cache
    if (not force) and (not includes_hot) and store.blob_exists(final_rel):
        meta_persist = store.read_json(meta_rel) or {}
        urls = _signed_urls()
        meta_return = dict(meta_persist)
        meta_return.update({
            "signed_url": urls.get("inline"),
            "signed_url_download": urls.get("download"),
            "signed_url_expires_seconds": signed_ttl,
        })
        _emit(
            "Relatório reaproveitado do cache.",
            processed=total_range_days,
            total=total_range_days,
            stage="done",
            final_pdf_bytes=meta_persist.get("final_pdf_bytes"),
            signed_url=urls.get("inline"),
        )
        return ReportResult(key=key, gcs_rel_path=final_rel, meta=meta_return)

    # --------------------
    # Dataset diário (JSON)
    # --------------------
    day_groups: Dict[str, List[dict]] = {}

    # Checa se há cache frio faltando
    cold_missing = False
    for d in daterange(start, end):
        if d < yesterday:
            day = d.strftime("%Y-%m-%d")
            if not store.blob_exists(f"day-cache/{day}.json"):
                cold_missing = True
                break

    if cold_missing:
        # Bulk fetch (1 query) para popular caches (melhor 1 grande do que N pequenos)
        fetched = fetch_dds_range(start_date, end_date)
        for day, regs in fetched.items():
            store.write_json(f"day-cache/{day}.json", {"day": day, "regs": regs})

    # Carrega dias frios do cache; dias quentes serão buscados e sobrescritos
    for d in daterange(start, end):
        day = d.strftime("%Y-%m-%d")
        if d < yesterday:
            payload = store.read_json(f"day-cache/{day}.json")
            regs = (payload or {}).get("regs") or []
            day_groups[day] = regs

    # Hot days: sempre consulta Firestore e atualiza cache
    for hot in (yesterday, today):
        if start <= hot <= end:
            day = hot.strftime("%Y-%m-%d")
            regs = fetch_dds_day(day)
            store.write_json(f"day-cache/{day}.json", {"day": day, "regs": regs})
            day_groups[day] = regs

    # Se range não contém hot, ainda precisamos carregar os dias frios restantes (que podem ter vindo do bulk)
    for d in daterange(start, end):
        day = d.strftime("%Y-%m-%d")
        if day not in day_groups:
            payload = store.read_json(f"day-cache/{day}.json")
            regs = (payload or {}).get("regs") or []
            day_groups[day] = regs

    # Filtra dias sem registros (para não criar páginas vazias)
    days_all = [d.strftime("%Y-%m-%d") for d in daterange(start, end)]
    days_with_regs = [day for day in days_all if (day_groups.get(day) or [])]

    # KPIs
    total_regs = sum(len(day_groups.get(day) or []) for day in days_with_regs)
    equipes = set()
    total_participantes = 0
    total_duracao_seg = 0
    for day in days_with_regs:
        for r in day_groups[day] or []:
            equipes.add((r.get("equipe") or "").strip())
            total_participantes += len(r.get("eletricistas") or [])
            total_duracao_seg += int(r.get("duracao_seg") or 0)

    # Ranking equipes (para ordenar dentro do dia)
    ranking = _rank_equipes({d: day_groups[d] for d in days_with_regs})

    # --------------------
    # PDFs diários (body)
    # --------------------
    image_cache = ImageCache(store)

    daily_entries: List[Dict[str, Any]] = []  # {day, rel, page_count, pdf_bytes, images{...}}
    processed_days = 0

    for day in days_all:
        processed_days += 1

        regs = day_groups.get(day) or []
        if not regs:
            _emit(
                f"Sem registros no dia {day}; pulando.",
                processed=processed_days,
                total=total_range_days,
                stage="day",
                day=day,
                skipped=True,
            )
            continue

        day_date = parse_iso_date(day)
        is_hot = day_date in (today, yesterday)

        daily_rel = f"daily-body/photos/{day}.pdf"
        daily_meta_rel = f"daily-body/photos/{day}.meta.json"

        # cold days: reusa cache só se NÃO for force
        if (not force) and (not is_hot):
            # 1) se já temos meta no cache, não precisa nem baixar o PDF agora
            if store.blob_exists(daily_meta_rel):
                meta_day = store.read_json(daily_meta_rel) or {}
                pc = int(meta_day.get("page_count") or 0)
                if pc > 0:
                    pb = int(meta_day.get("pdf_bytes") or 0)
                    images_meta = meta_day.get("images") or {}
                    daily_entries.append({
                        "day": day,
                        "rel": daily_rel,
                        "page_count": pc,
                        "pdf_bytes": pb,
                        "images": images_meta,
                        "source": "cache-meta",
                    })
                    _emit(
                        f"Dia {day} reaproveitado do cache (meta).",
                        processed=processed_days,
                        total=total_range_days,
                        stage="day",
                        day=day,
                        cached=True,
                        page_count=pc,
                        daily_pdf_bytes=pb,
                        images_total=images_meta.get("total"),
                        images_normalized=images_meta.get("normalized"),
                    )
                    continue

            # 2) se existe PDF no cache, baixa só para medir páginas e bytes (e cria meta)
            if store.blob_exists(daily_rel):
                _emit(
                    f"Baixando PDF diário do cache para o dia {day}...",
                    processed=processed_days,
                    total=total_range_days,
                    stage="download",
                    day=day,
                )
                lp = store.download_to_tmp(daily_rel)
                pb = int(lp.stat().st_size) if lp.exists() else 0
                pc = len(PdfReader(str(lp)).pages) if lp.exists() else 0

                meta_day = {
                    "day": day,
                    "page_count": pc,
                    "pdf_bytes": pb,
                    "source": "cache",
                    "generated_at": dt.datetime.utcnow().isoformat() + "Z",
                }
                try:
                    store.write_json(daily_meta_rel, meta_day)
                except Exception:
                    pass

                daily_entries.append({
                    "day": day,
                    "rel": daily_rel,
                    "page_count": pc,
                    "pdf_bytes": pb,
                    "images": {},
                    "source": "cache",
                })

                _emit(
                    f"Dia {day} reaproveitado do cache.",
                    processed=processed_days,
                    total=total_range_days,
                    stage="day",
                    day=day,
                    cached=True,
                    page_count=pc,
                    daily_pdf_bytes=pb,
                )

                # não manter em /tmp (range grande)
                try:
                    lp.unlink()
                except Exception:
                    pass
                continue

        # Caso contrário, gera / regenera diário
        _emit(
            f"Preparando imagens do dia {day}...",
            processed=processed_days,
            total=total_range_days,
            stage="images",
            day=day,
        )

        urls = list({(r.get("thumbUrl") or r.get("fotoUrl") or "").strip()
                    for r in regs if (r.get("thumbUrl") or r.get("fotoUrl"))})
        url_list = [u for u in urls if u]

        image_paths: Dict[str, Path] = {}
        img_stats: Dict[str, int] = {"total": len(url_list)}

        if url_list:
            image_paths = asyncio.run(image_cache.ensure_cached(url_list, stats=img_stats))

        _emit(
            f"Gerando o relatório para o dia {day}",
            processed=processed_days,
            total=total_range_days,
            stage="day",
            day=day,
            images_total=img_stats.get("total", 0),
            images_cache_hit=int(img_stats.get("cache_hit_local", 0)) + int(img_stats.get("cache_hit_gcs", 0)),
            images_downloaded=img_stats.get("downloaded", 0),
            images_normalized=img_stats.get("normalized", 0),
            images_bytes_in=img_stats.get("bytes_in", 0),
            images_bytes_out=img_stats.get("bytes_out", 0),
        )

        daily_tmp = store._tmp_path(daily_rel)
        gerar_pdf_diario_com_fotos_body(
            day=day,
            regs=regs,
            path_saida=daily_tmp,
            image_paths=image_paths,
            equipe_ranking=ranking,
            header_title="DDS - Relatório com Fotos",
            base_dir=base_dir,
        )


        try:
            store.upload_from_tmp(daily_rel, daily_tmp, content_type="application/pdf")
        except Exception:
            pass

        pb = int(daily_tmp.stat().st_size) if daily_tmp.exists() else 0
        pc = len(PdfReader(str(daily_tmp)).pages) if daily_tmp.exists() else 0

        meta_day = {
            "day": day,
            "page_count": pc,
            "pdf_bytes": pb,
            "source": "generated" if is_hot or force else "rebuild",
            "generated_at": dt.datetime.utcnow().isoformat() + "Z",
            "images": dict(img_stats),
        }
        try:
            store.write_json(daily_meta_rel, meta_day)
        except Exception:
            pass

        daily_entries.append({
            "day": day,
            "rel": daily_rel,
            "page_count": pc,
            "pdf_bytes": pb,
            "images": dict(img_stats),
            "source": meta_day["source"],
        })

        # limpeza: thumbs otimizadas e PDF diário não ficam acumulando no /tmp
        try:
            shutil.rmtree(daily_tmp.parent / "pdf_opt" / day, ignore_errors=True)
        except Exception:
            pass
        try:
            daily_tmp.unlink()
        except Exception:
            pass

    # --------------------
    # Capa + Sumário
    # --------------------

    gen_pt = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    periodo = f"Período: {format_pt_date(start)} a {format_pt_date(end)}"
    kpis = {
        "DDS no período": str(total_regs),
        "Equipes": str(len([e for e in equipes if e])),
        "Participações": str(total_participantes),
        "Duração total": formatar_segundos_para_duracao(total_duracao_seg),
    }

    cover_rel = f"build/{key}/cover.pdf"
    toc_rel = f"build/{key}/toc.pdf"
    merged_rel = f"build/{key}/final_merged.pdf"
    stamped_rel = f"build/{key}/final_stamped.pdf"

    cover_path = store._tmp_path(cover_rel)
    toc_path = store._tmp_path(toc_rel)
    merged_path = store._tmp_path(merged_rel)
    stamped_path = store._tmp_path(stamped_rel)

    _emit("Gerando capa e sumário...", processed=total_range_days, total=total_range_days, stage="toc")
    gerar_pdf_capa(
        cover_path,
        titulo="DDS - Relatório com Fotos",
        periodo=periodo,
        gerado_em=gen_pt,
        kpis=kpis,
    )

    toc_pages_guess = 1
    toc_pages = 1
    for _ in range(4):
        toc_entries = []
        page_cursor = toc_pages_guess + 2  # capa (1) + páginas do sumário + 1ª página do corpo
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
            page_cursor += int(pc)

        toc_pages = gerar_pdf_sumario(
            toc_path,
            entries=toc_entries,
            header_title="DDS - Relatório com Fotos",
            base_dir=base_dir,
        )
        if toc_pages == toc_pages_guess:
            break
        toc_pages_guess = toc_pages

    # --------------------
    # merge final: capa + toc + diários (baixando 1 a 1)
    # --------------------
    _emit("Mesclando PDFs...", processed=total_range_days, total=total_range_days, stage="merge")
    merge_inputs: List[Tuple[Path, bool]] = [(cover_path, False), (toc_path, False)]
    for e in daily_entries:
        lp = store.download_to_tmp(e["rel"])
        merge_inputs.append((lp, True))  # delete_after_read=True

    merge_pdfs_with_cleanup(merged_path, merge_inputs)

    stamp_footer_paginacao_geral(
        in_pdf=merged_path,
        out_pdf=stamped_path,
        generation_date_pt=generation_date_pt,
    )

    # grava final no cache
    _emit("Salvando relatório final no cache...", processed=total_range_days, total=total_range_days, stage="upload")
    store.upload_from_tmp(final_rel, stamped_path, content_type="application/pdf")

    final_pdf_bytes = int(stamped_path.stat().st_size) if stamped_path.exists() else 0

    # limpeza /tmp
    for p in (merged_path, stamped_path, cover_path, toc_path):
        try:
            p.unlink()
        except Exception:
            pass

    _emit(
        "Relatório final gerado e salvo no cache.",
        processed=total_range_days,
        total=total_range_days,
        stage="done",
        final_pdf_bytes=final_pdf_bytes,
    )

    meta_persist = {
        "key": key,
        "type": "fotos",
        "start_date": start_date,
        "end_date": end_date,
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "includes_hot": includes_hot,
        "days": [e["day"] for e in daily_entries],
        "toc_pages": toc_pages,
        "total_regs": total_regs,
        "teams": len([e for e in equipes if e]),
        "participants": total_participantes,
        "duration_total_seconds": total_duracao_seg,
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

    _emit(
        "URL de visualização gerada.",
        processed=total_range_days,
        total=total_range_days,
        stage="done",
        signed_url=urls.get("inline"),
    )

    return ReportResult(key=key, gcs_rel_path=final_rel, meta=meta_return)

def materialize_report_to_tmp(*, bucket_name: str, cache_prefix: str, rel_path: str) -> Path:
    """Garante que um artefato em GCS esteja disponível localmente em /tmp e retorna o path."""
    store = CacheStore(CacheConfig(bucket_name=bucket_name, prefix=cache_prefix))
    return store.download_to_tmp(rel_path)


# =============================
# Página rápida: Presença das Equipes (matriz por dia)
# =============================


def get_presence_matrix(
    *,
    start_date: str,
    end_date: str,
    tz_name: str,
    bucket_name: str,
    cache_prefix: str,
    team_q: str = "",
    sort: str = "name",
    only_absences: bool = False,
) -> Dict[str, Any]:
    """Retorna uma matriz de presença por equipe x dia (para visualização rápida no admin-site).

    - Usa a mesma política hot/cold do relatório:
        * hoje e ontem: reconsulta Firestore
        * dias anteriores: prioriza cache day-cache/<YYYY-MM-DD>.json
    - Não gera PDF.
    """
    start = parse_iso_date(start_date)
    end = parse_iso_date(end_date)
    if start > end:
        raise ValueError("Data inicial não pode ser maior que a data final.")

    store = CacheStore(CacheConfig(bucket_name=bucket_name, prefix=cache_prefix))
    today, yesterday = _tz_today_yesterday(tz_name)

    days_all = [d.strftime("%Y-%m-%d") for d in daterange(start, end)]

    # 1) Detecta cache frio faltando (para fazer 1 bulk fetch)
    cold_missing = False
    for d in daterange(start, end):
        if d < yesterday:
            day = d.strftime("%Y-%m-%d")
            if not store.blob_exists(f"day-cache/{day}.json"):
                cold_missing = True
                break

    if cold_missing:
        fetched = fetch_dds_range(start_date, end_date)
        for day, regs in fetched.items():
            store.write_json(f"day-cache/{day}.json", {"day": day, "regs": regs})

    # 2) Carrega dias do cache (cold) e busca no Firestore (hot)
    day_groups: Dict[str, List[dict]] = {}
    for d in daterange(start, end):
        day = d.strftime("%Y-%m-%d")
        if d < yesterday:
            payload = store.read_json(f"day-cache/{day}.json")
            day_groups[day] = (payload or {}).get("regs") or []

    for hot in (yesterday, today):
        if start <= hot <= end:
            day = hot.strftime("%Y-%m-%d")
            regs = fetch_dds_day(day)
            store.write_json(f"day-cache/{day}.json", {"day": day, "regs": regs})
            day_groups[day] = regs

    for d in daterange(start, end):
        day = d.strftime("%Y-%m-%d")
        if day not in day_groups:
            payload = store.read_json(f"day-cache/{day}.json")
            day_groups[day] = (payload or {}).get("regs") or []

    # 3) Calcula presença por dia
    day_has_any: List[bool] = []
    present_by_day: List[set] = []
    team_set: set = set()
    total_regs = 0

    for day in days_all:
        regs = day_groups.get(day) or []
        total_regs += len(regs)
        present = set()
        for r in regs:
            eq = (r.get("equipe") or "").strip()
            if eq:
                present.add(eq)
                team_set.add(eq)
        present_by_day.append(present)
        day_has_any.append(len(regs) > 0)


    teams = sorted(team_set, key=lambda x: x.lower())

    # filtro textual opcional por equipe (aceita termos separados por ; , ou espaço)
    q = (team_q or "").strip()
    if q:
        tokens = [t.lower() for t in re.split(r"[;,\s]+", q) if t.strip()]
        if tokens:
            teams = [team for team in teams if all(tok in team.lower() for tok in tokens)]
    # 4) Matriz equipe x dia
    matrix: Dict[str, List[Optional[int]]] = {}
    team_stats: Dict[str, Dict[str, Any]] = {}
    total_days = len(days_all)
    active_days = sum(1 for x in day_has_any if x)

    for team in teams:
        row: List[Optional[int]] = []
        present_count = 0
        for i, _day in enumerate(days_all):
            if not day_has_any[i]:
                row.append(None)  # dia sem nenhum DDS no dataset
                continue
            v = 1 if team in present_by_day[i] else 0
            row.append(v)
            if v == 1:
                present_count += 1

        pct_range = (present_count / total_days * 100.0) if total_days else 0.0
        pct_active = (present_count / active_days * 100.0) if active_days else 0.0
        matrix[team] = row
        team_stats[team] = {
            "present": present_count,
            "absent": max(0, active_days - present_count),
            "pct_range": pct_range,
            "pct_active": pct_active,
            "pct_absent_active": (max(0, active_days - present_count) / active_days * 100.0) if active_days else 0.0,
        }

    # ordenação opcional da grade
    sort_key = (sort or "name").strip().lower()
    if sort_key == "present":
        teams = sorted(teams, key=lambda t: (-int(team_stats[t]["present"]), t.lower()))
    elif sort_key == "absent":
        teams = sorted(teams, key=lambda t: (-int(team_stats[t]["absent"]), t.lower()))
    elif sort_key == "pct_present":
        teams = sorted(teams, key=lambda t: (-float(team_stats[t]["pct_active"]), t.lower()))
    elif sort_key == "pct_absent":
        teams = sorted(teams, key=lambda t: (-float(team_stats[t]["pct_absent_active"]), t.lower()))
    else:
        teams = sorted(teams, key=lambda t: t.lower())

    # 5) Totais por dia (quantas equipes tiveram DDS no dia)
    day_totals = [len(present_by_day[i]) if day_has_any[i] else 0 for i in range(len(days_all))]

    return {
        "start_date": start_date,
        "end_date": end_date,
        "days": days_all,
        "day_has_any": day_has_any,
        "teams": teams,
        "matrix": matrix,
        "team_stats": team_stats,
        "day_totals": day_totals,
        "total_regs": total_regs,
        "active_days": active_days,
        "total_days": total_days,
    }
