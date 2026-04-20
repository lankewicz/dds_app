# -----------------------------------------------------------------------------
# Módulo: relatorio.py
# Versão: 5.2 (Híbrido - Estrutura Nova com Engine de Fotos Antiga)
#
# Descrição:
#   Geração de relatórios em PDF.
#   - Recuperada a lógica de CACHE em DISCO e OTIMIZAÇÃO PIL da versão antiga
#     para garantir que as fotos apareçam.
# -----------------------------------------------------------------------------

from __future__ import annotations

import os
import sys
import re
import datetime
import json
import hashlib
import asyncio
from collections import defaultdict
from io import BytesIO
from functools import partial
from typing import Dict, List, Optional
from pathlib import Path

# --- Dependências externas ---
try:
    import aiohttp
    from PIL import Image as PILImage  # Essencial para tratamento de fotos
    from reportlab.platypus import (
         SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, Flowable, PageBreak, KeepTogether
    )
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.units import cm
    from reportlab.lib.pagesizes import A4, landscape
    from rich.progress import track
except ImportError as e:
    print(f"❌ Dependência ausente: {e}. Instale os requisitos (reportlab, pillow, aiohttp).")
    sys.exit(1)

# --- Módulos locais ---
from logger import log_manager
from visual_utils import header_footer
from config import CACHE_DIR # Certifique-se que CACHE_DIR está definido no config.py

# Se CACHE_DIR não vier do config, define um padrão
if not 'CACHE_DIR' in globals():
    CACHE_DIR = Path("data/cache")

class ClickableImage(Flowable):
    """
    Flowable que desenha uma Image e registra um link clicável sobre ela.
    """
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
            canv.linkURL(
                self.url,
                (x, y, x + self.width, y + self.height),
                relative=1,
                thickness=0,
            )

# =============================================================================
# Utilidades de Conversão e Arquivo
# =============================================================================

def parse_duracao_para_segundos(duracao_str: str) -> int:
    if not isinstance(duracao_str, str): return 0
    minutos, segundos = 0, 0
    m = re.search(r'(\d+)\s*min', duracao_str, re.IGNORECASE)
    if m: minutos = int(m.group(1))
    s = re.search(r'(\d+)\s*s', duracao_str, re.IGNORECASE)
    if s: segundos = int(s.group(1))
    if minutos == 0 and segundos == 0 and duracao_str.strip().isdigit():
        segundos = int(duracao_str.strip())
    return minutos * 60 + segundos

def formatar_segundos_para_duracao(total_segundos: int) -> str:
    if total_segundos < 0: total_segundos = 0
    m, s = divmod(total_segundos, 60)
    return f"{m}min {s}s"



# =============================================================================
# Ranking / Relatórios Sintéticos
# =============================================================================

def _filtrar_grupos_por_mes(
    grupos_por_data: Dict[datetime.date, List[dict]],
    ano: int,
    mes: int
) -> Dict[datetime.date, List[dict]]:
    """Retorna somente as datas do ano/mês informado."""
    out: Dict[datetime.date, List[dict]] = {}
    for d, regs in (grupos_por_data or {}).items():
        if isinstance(d, datetime.date) and d.year == ano and d.month == mes:
            out[d] = regs or []
    return out


def calcular_presencas_por_equipe(
    grupos_por_data: Dict[datetime.date, List[dict]]
) -> Dict[str, int]:
    """
    Conta presenças por equipe (1 presença por DDS registrado para a equipe).
    Retorna dict ordenado desc: {equipe: presencas}.
    """
    contagem: Dict[str, int] = defaultdict(int)
    seen: set[tuple[str, datetime.date]] = set()
    for data, regs in (grupos_por_data or {}).items():
        for r in (regs or []):
            equipe = (r.get("equipe") or "–").strip()
            if not equipe or equipe in ("–", "—"):
                continue
            key = (equipe, data)
            if key in seen:
                continue
            seen.add(key)
            contagem[equipe] += 1
    # ordena desc por presenças, e asc por nome para desempate
    return dict(sorted(contagem.items(), key=lambda x: (-x[1], x[0].lower())))


def detalhar_presencas_por_equipe(
    grupos_por_data: Dict[datetime.date, List[dict]]
) -> Dict[str, List[dict]]:
    """
    Retorna: {equipe: [{"data": date, "tema": str}, ...]} ordenado por data asc dentro de cada equipe.
    """
    detalhe: Dict[str, List[dict]] = defaultdict(list)
    seen: set[tuple[str, datetime.date, str]] = set()
    for data, regs in (grupos_por_data or {}).items():
        for r in (regs or []):
            equipe = (r.get("equipe") or "–").strip()
            if not equipe or equipe == "–" or equipe == "—":
                continue
            tema = (r.get("tema", "–") or "–").strip()
            key = (equipe, data, tema)
            if key in seen:
                continue
            seen.add(key)
            detalhe[equipe].append({"data": data, "tema": tema})

    for equipe in list(detalhe.keys()):
        detalhe[equipe] = sorted(detalhe[equipe], key=lambda x: x["data"])
    return detalhe

# =============================================================================
# Lógica de Imagem (Trazida da versão antiga para estabilidade)
# =============================================================================

def _pt_to_px(pt: float, dpi: int) -> int:
    return max(1, int(round(pt * dpi / 72.0)))

def _prepare_thumb_for_pdf(src_path: Path, out_dir: Path, width_pt: float, height_pt: float, dpi: int = 120, quality: int = 70) -> Path:
    """
    Redimensiona e converte a imagem para JPEG usando PIL. 
    Isso evita erros do ReportLab com formatos desconhecidos.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    src_path = Path(src_path)
    
    if not src_path.exists():
        return src_path

    # Calcula pixels alvo
    w_px = _pt_to_px(width_pt, dpi)
    h_px = _pt_to_px(height_pt, dpi)

    # Hash para cache do processamento
    h_str = f"{src_path.resolve()}|{src_path.stat().st_mtime}|{w_px}x{h_px}|q{quality}"
    h = hashlib.md5(h_str.encode("utf-8")).hexdigest()[:16]
    
    out_path = out_dir / f"{src_path.stem}_opt_{h}.jpg"
    if out_path.exists():
        return out_path

    try:
        with PILImage.open(src_path) as im:
            im = im.convert("RGB") # Remove alpha/transparência que quebra PDF
            im.thumbnail((w_px, h_px), resample=PILImage.LANCZOS)
            
            # Cria fundo branco para garantir tamanho exato (opcional, aqui apenas salva)
            im.save(out_path, format="JPEG", quality=quality, optimize=True)
        return out_path
    except Exception as e:
        log_manager.add(f"[Imagem] Erro ao processar {src_path.name}: {e}", "WARNING")
        return src_path # Retorna original em caso de erro

async def baixar_thumbs_em_disco(urls: List[str]) -> Dict[str, str]:
    """
    Baixa as thumbs para o disco (CACHE_DIR) com retentativas.
    Retorna Dict[url, caminho_local_str].
    """
    cache_file = CACHE_DIR / "thumb_map.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    cache_map = {}
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f: cache_map = json.load(f)
        except: pass

    urls_to_fetch = []
    
    # Verifica o que já temos
    for url in urls:
        if not url: continue
        
        # Nome de arquivo seguro
        clean_name = re.sub(r'[^\w\-\.]', '_', url.split('?')[0][-50:])
        if not clean_name.lower().endswith(('.jpg', '.jpeg', '.png')):
            clean_name += ".jpg"
            
        local_path = CACHE_DIR / clean_name
        
        # Se já está no map e arquivo existe, ok. Se não, adiciona lista.
        if url in cache_map and Path(cache_map[url]).exists():
            continue
        
        # Atualiza map previsto
        cache_map[url] = str(local_path)
        if not local_path.exists():
            urls_to_fetch.append((url, local_path))

    # Baixar pendentes
    if urls_to_fetch:
        sem = asyncio.Semaphore(10)
        async with aiohttp.ClientSession() as session:
            async def fetch(u, path):
                async with sem:
                    for _ in range(3): # 3 tentativas
                        try:
                            async with session.get(u, timeout=15) as r:
                                if r.status == 200:
                                    content = await r.read()
                                    with open(path, 'wb') as f: f.write(content)
                                    return
                        except:
                            await asyncio.sleep(0.5)
            
            # Executa downloads
            tasks = [fetch(u, p) for u, p in urls_to_fetch]
            if tasks:
                log_manager.add(f"[relatorio] Baixando {len(tasks)} novas imagens...", "INFO")
                await asyncio.gather(*tasks)

    # Salva mapa atualizado
    with open(cache_file, 'w') as f: json.dump(cache_map, f)
    
    # Retorna apenas o que existe
    return {u: p for u, p in cache_map.items() if Path(p).exists()}


# =============================================================================
# Coleta de Dados (Compatível com Standalone)
# =============================================================================

def carregar_db():
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        raise RuntimeError("Firebase Admin SDK não instalado.")
    if not firebase_admin._apps:
        from config import FIREBASE_CREDENTIAL_PATH, FIREBASE_BUCKET
        cred = credentials.Certificate(FIREBASE_CREDENTIAL_PATH)
        firebase_admin.initialize_app(cred, {'storageBucket': FIREBASE_BUCKET})
    return firestore.client()

def buscar_e_agrupar(db) -> Dict[datetime.date, List[dict]]:
    grupos = defaultdict(list)
    for doc in db.collection("DDS").stream():
        d = doc.to_dict() or {}
        try:
            date_obj = datetime.datetime.strptime(d.get("headerDate", ""), "%Y-%m-%d").date()
            duracao_str = d.get("duracao", "0s")
            total_segundos = parse_duracao_para_segundos(duracao_str)
            
            # Regra de negócio (soma 120s se for muito curto)
            if 0 < total_segundos < 120:
                total_segundos += 120
                
            grupos[date_obj].append({
                "headerTitle": d.get("headerTitle", "–"),
                "equipe": d.get("equipe", "–"),
                "dataHora": d.get("dataHora", "–"),
                "duracao": formatar_segundos_para_duracao(total_segundos),
                "eletricistas": d.get("eletricistas", []) or [],
                "tema": d.get("tema", "–"),
                "thumbUrl": d.get("thumbUrl"),
                "fotoUrl": d.get("fotoUrl"),
            })
        except: continue
    return grupos

def interpretar_mes(argumento_str: str) -> tuple[Optional[int], bool]:
    txt = (argumento_str or "").lower()
    usar_foto = "foto" in txt
    meses = {
        "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5, "junho": 6,
        "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12
    }
    for nome, num in meses.items():
        if nome in txt: return num, usar_foto
    m = re.search(r"\b(1[0-2]|[1-9])\b", txt)
    if m: return int(m.group(1)), usar_foto
    return None, usar_foto


# =============================================================================
# GERAÇÃO DOS RELATÓRIOS
# =============================================================================

async def gerar_pdf_com_foto(
    grupos_por_data: Dict[datetime.date, List[dict]],
    path_saida: str,
    resolver_fn=None, # Mantido para compatibilidade, mas ignorado nesta lógica
    link_resolver=None,
    equipe_ranking: Optional[Dict[str, int]] = None,
):
    """
    Gera PDF com fotos usando cache em disco e processamento PIL.
    """
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("Cell", parent=styles["BodyText"], alignment=TA_LEFT, leading=12)
    title_style = ParagraphStyle("SessionTitle", parent=styles["Heading2"], alignment=TA_LEFT, spaceBefore=12)

    doc = SimpleDocTemplate(path_saida, pagesize=landscape(A4), topMargin=3*cm, bottomMargin=2*cm)
    usable_width = doc.width
    story = []

    # 1. Extrair URLs
    all_urls = []
    for regs in grupos_por_data.values():
        for r in regs:
            u = r.get("thumbUrl") or r.get("fotoUrl")
            if u: all_urls.append(u)
            
    # 2. Baixar e Cachear em Disco (Lógica Antiga Robustecida)
    # Se resolver_fn for None, usamos o download HTTP padrão
    path_map = {}
    if resolver_fn is None:
        path_map = await baixar_thumbs_em_disco(list(set(all_urls)))

    on_every_page = partial(header_footer, titulo="DDS - Relatório com Fotos")
    
    # Configurações de Thumb
    THUMB_W, THUMB_H = 60, 45 # Tamanho no PDF (points)
    PDF_THUMB_DIR = CACHE_DIR / "pdf_opt" # Cache de imagens já convertidas para PDF
    # Ranking default (se o caller não passar) — ordena equipes do mês/dataset por presenças desc
    if equipe_ranking is None:
         equipe_ranking = calcular_presencas_por_equipe(grupos_por_data)

    total_dias = len(grupos_por_data)
    for i, date_obj in enumerate(sorted(grupos_por_data), start=1):
        # registros = sorted(grupos_por_data[date_obj], key=lambda r: r.get("equipe", ""))
        registros = sorted(
            grupos_por_data[date_obj],
            key=lambda r: (-int(equipe_ranking.get((r.get("equipe") or "").strip(), 0)), (r.get("equipe") or "").lower())
        )        

        # Cabeçalho do dia
        story.append(Paragraph(registros[0].get("headerTitle", "DDS"), title_style))
        story.append(Spacer(1, 4))
        story.append(Paragraph(f'Data: {date_obj.strftime("%d/%m/%Y")}', styles["Normal"]))
        story.append(Spacer(1, 6))

        # Cabeçalho da Tabela
        data_rows = [["Equipe", "Duração", "Qtd", "Participantes", "Tema", "Foto"]]

        for r in registros:
            url_thumb = r.get("thumbUrl") or r.get("fotoUrl")
            link_final = r.get("fotoUrl") or r.get("thumbUrl")
            
            thumb_flowable = Paragraph("–", cell_style)
            
            # Tenta pegar imagem do cache
            if url_thumb and url_thumb in path_map:
                local_raw = path_map[url_thumb]
                
                # Processa imagem (Redimensiona e converte p/ JPG)
                final_path = _prepare_thumb_for_pdf(
                    Path(local_raw), 
                    PDF_THUMB_DIR, 
                    THUMB_W, THUMB_H
                )
                
                if final_path.exists():
                    img_obj = Image(str(final_path), width=THUMB_W, height=THUMB_H)
                    if link_final:
                        thumb_flowable = ClickableImage(img_obj, link_final)
                    else:
                        thumb_flowable = img_obj
            
            # Fallback para link de texto se imagem falhou mas existe link
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

        # Estilo da tabela
        # Colunas: Equipe, Duração, Qtd, Participantes, Tema, Foto
        col_widths = [usable_width * x for x in [0.13, 0.07, 0.06, 0.26, 0.30, 0.18]]
        table = Table(data_rows, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(table)
        story.append(Spacer(1, 12))

        try:
            log_manager.add(f"[relatorio] página {i}/{total_dias} processada", "DEBUG")
        except: pass

    doc.build(story, onFirstPage=on_every_page, onLaterPages=on_every_page)



def gerar_pdf_sintetico_analitico(
    grupos_por_data: Dict[datetime.date, List[dict]],
    ano: int,
    mes: int,
    path_saida: str,
):
    """
    Relatório:
    1) Sintético (ranking de presenças por equipe)
    2) Analítico (por equipe: Data - Treinamento/tema)
    """
    grupos_mes = _filtrar_grupos_por_mes(grupos_por_data, ano, mes)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Titulo",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=10
    )
    h2_style = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=10,
        spaceAfter=6
    )
    cell_style = ParagraphStyle("Cell", parent=styles["BodyText"], alignment=TA_LEFT, leading=12)

    doc = SimpleDocTemplate(path_saida, pagesize=landscape(A4), topMargin=3*cm, bottomMargin=2*cm)
    story = []

    on_every_page = partial(header_footer, titulo="DDS - Presenças (Sintético + Analítico)")

    # --------------------------
    # Sintético (Ranking)
    # --------------------------
    ranking = calcular_presencas_por_equipe(grupos_mes)
    meses_pt = ["janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro"]
    mes_label = f"{meses_pt[mes-1].capitalize()} de {ano}" if 1 <= mes <= 12 else f"Mês {mes}/{ano}"

    story.append(Paragraph("Relatório de Presenças — Sintético + Analítico", title_style))
    story.append(Paragraph(f"Período: <b>{mes_label}</b>", styles["Normal"]))
    story.append(Spacer(1, 10))

    if not ranking:
        story.append(Paragraph("Nenhum DDS encontrado para o período informado.", styles["Normal"]))
        doc.build(story, onFirstPage=on_every_page, onLaterPages=on_every_page)
        return

    data_rows = [["Ordem", "Equipe", "Presenças"]]
    for idx, (equipe, presencas) in enumerate(ranking.items(), start=1):
        data_rows.append([str(idx), Paragraph(equipe, cell_style), str(presencas)])

    table = Table(data_rows, colWidths=[doc.width * 0.10, doc.width * 0.70, doc.width * 0.20], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (-1, 0), (-1, -1), "CENTER"),
    ]))
    story.append(table)
    story.append(PageBreak())

    # --------------------------
    # Analítico (por equipe)
    # --------------------------
    detalhe = detalhar_presencas_por_equipe(grupos_mes)

    for equipe, presencas in ranking.items():
        itens = detalhe.get(equipe, [])
        cab = [
            Paragraph(f"Equipe: <b>{equipe}</b>", h2_style),
            Paragraph(f"Total de presenças no mês: <b>{presencas}</b>", styles["Normal"]),
            Spacer(1, 6),
        ]

        rows = [["Data", "Treinamento"]]
        for it in itens:
            d = it["data"].strftime("%d/%m/%Y")
            tema = it.get("tema") or "–"
            rows.append([d, Paragraph(str(tema), cell_style)])

        t = Table(rows, colWidths=[doc.width * 0.18, doc.width * 0.82], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]))

        story.append(KeepTogether(cab + [t, Spacer(1, 12)]))

    doc.build(story, onFirstPage=on_every_page, onLaterPages=on_every_page)

def gerar_pdf_detalhado(grupos_por_data: Dict[datetime.date, List[dict]], path_saida: str):
    """Gera relatório PDF detalhado (sem fotos)."""
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("Cell", parent=styles["BodyText"], alignment=TA_LEFT, leading=12)
    title_style = ParagraphStyle("SessionTitle", parent=styles["Heading2"], alignment=TA_LEFT, spaceBefore=12)

    doc = SimpleDocTemplate(path_saida, pagesize=landscape(A4), topMargin=3*cm, bottomMargin=2*cm)
    usable_width = doc.width
    story = []
    on_every_page = partial(header_footer, titulo="DDS - Relatório Detalhado")

    equipe_ranking = calcular_presencas_por_equipe(grupos_por_data)

    for date_obj in sorted(grupos_por_data):
#        registros = sorted(grupos_por_data[date_obj], key=lambda r: r.get("equipe", ""))
        registros = sorted(
            grupos_por_data[date_obj],
            key=lambda r: (-int(equipe_ranking.get((r.get("equipe") or "").strip(), 0)), (r.get("equipe") or "").lower())
        )
        
        story.append(Paragraph(registros[0].get("headerTitle", "DDS"), title_style))
        story.append(Spacer(1, 4))
        story.append(Paragraph(f'Data: {date_obj.strftime("%d/%m/%Y")}', styles["Normal"]))
        story.append(Spacer(1, 6))

        data_rows = [["Equipe", "Data Hora", "Qtd", "Participantes", "Tema"]]
        for r in registros:
            data_rows.append([
                Paragraph(r.get("equipe", "–"), cell_style),
                Paragraph(r.get("dataHora", "–"), cell_style),
                str(len(r.get("eletricistas", []) or [])),
                Paragraph("<br/>".join(r.get("eletricistas", []) or []) or "–", cell_style),
                Paragraph(r.get("tema", "–"), cell_style),
            ])

        table = Table(data_rows, colWidths=[usable_width * x for x in [0.20, 0.15, 0.05, 0.30, 0.30]], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(table)
        story.append(Spacer(1, 12))

    doc.build(story, onFirstPage=on_every_page, onLaterPages=on_every_page)
