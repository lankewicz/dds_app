"""
============================================================
FILE: storage_online_package.py
FUNCTION: Create and update the DDS ONLINE "package" in Firebase Storage
          to preserve app compatibility:
          - Create folder: DDSv2/YYYY-MM-DD - DDS ONLINE - HHMM/
          - Upload Slide1.JPG (1920x1080 placeholder)
          - Upload reuniao.json (meeting metadata)
          - Update DDSv2/lista.json (append paths) atomically

NOTES:
- This module uses google-cloud-storage directly for GCS preconditions
  (if_generation_match) to avoid silent overwrites of lista.json.
- Pillow is used to render the placeholder image.
============================================================
"""

from __future__ import annotations

import io
import json
import re
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont
from google.cloud import storage
from training_management.indexing import rebuild_lista_json




# -----------------------------
# Helpers
# -----------------------------
# -------------------------------------------------------------------------
# ARQUIVO: storage_online_package.py
# FUNÇÃO: Alias de compatibilidade para a função usada pelo painel (admin).
# -------------------------------------------------------------------------
# =============================================================================
# FILE: storage_online_package.py
# FUNCTION: Compatibility aliases for admin_routes.py imports
# =============================================================================

def upload_slides_to_online_folder(
    *,
    bucket_name: str,
    folder_prefix: str,
    slides: list[tuple[int, bytes]],
) -> None:
    """
    Upload JPG slides to an existing online session folder.
    Paths: {folder_prefix}/Slide{n}.JPG
    """
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    for n, data in slides:
        path = f"{folder_prefix}/Slide{n}.JPG"
        bucket.blob(path).upload_from_string(
            data,
            content_type="image/jpeg",
        )

def create_online_package_and_update_lista_json(
    *,
    bucket_name: str,
    base_prefix: str,
    date_yyyy_mm_dd: str,
    time_hhmm: str,
    host_team: str,
    subject: str,
    duration_min: int,
    timezone_name: str = "America/Sao_Paulo",
    slides_count: int = 1,
):
    return create_or_update_online_package(
        bucket_name=bucket_name,
        base_prefix=base_prefix,
        date_yyyy_mm_dd=date_yyyy_mm_dd,
        time_hhmm=time_hhmm,
        host_team=host_team,
        subject=subject,
        duration_min=duration_min,
        timezone_name=timezone_name,
        slides_count=slides_count,
        status="scheduled",
    )


def normalize_team(team: str) -> str:
    team = (team or "").strip().upper()
    team = re.sub(r"[^A-Z0-9_-]+", "", team)
    return team


def parse_date_yyyy_mm_dd(date_str: str) -> str:
    """Accepts 'YYYY-MM-DD' and returns the same canonical format."""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return d.strftime("%Y-%m-%d")


def parse_time_hhmm(time_str: str) -> str:
    """Accepts 'HH:MM' and returns the same canonical format."""
    t = datetime.strptime(time_str, "%H:%M")
    return t.strftime("%H:%M")


def make_session_id(team: str, date_yyyy_mm_dd: str, time_hhmm: str) -> str:
    team = normalize_team(team)
    d = datetime.strptime(date_yyyy_mm_dd, "%Y-%m-%d").strftime("%Y%m%d")
    hhmm = time_hhmm.replace(":", "")
    return f"DDS_{team}_{d}_{hhmm}"


def make_training_folder_id(date_yyyy_mm_dd: str, time_hhmm: str) -> str:
    """Folder id (training id) without subject to avoid breaking the current app.

    IMPORTANT: includes HHMM to avoid collisions if multiple online sessions
    are scheduled on the same day.
    """
    hhmm = time_hhmm.replace(":", "")
    return f"{date_yyyy_mm_dd} - DDS ONLINE - {hhmm}"


def month_ref(date_yyyy_mm_dd: str) -> str:
    # YYYY-MM
    return date_yyyy_mm_dd[:7]


# -----------------------------
# Placeholder slide rendering
# -----------------------------

def _load_fonts() -> Tuple[ImageFont.ImageFont, ImageFont.ImageFont, ImageFont.ImageFont]:
    """Try to load DejaVu fonts, fallback to default."""
    try:
        title = ImageFont.truetype("DejaVuSans-Bold.ttf", 72)
        sub = ImageFont.truetype("DejaVuSans-Bold.ttf", 48)
        body = ImageFont.truetype("DejaVuSans.ttf", 42)
        return title, sub, body
    except Exception:
        f = ImageFont.load_default()
        return f, f, f


def render_placeholder_slide(payload: Dict[str, Any], size: Tuple[int, int] = (1920, 1080)) -> bytes:
    """Render Slide1.JPG with basic meeting info."""
    # Fundo cinza claro (como no preview)
    img = Image.new("RGB", size, (240, 242, 245))  # #F0F2F5
    draw = ImageDraw.Draw(img)

    font_title, font_sub, font_body = _load_fonts()

# Paleta aproximada do preview (hex -> rgb)
    C_TITLE = (28, 52, 84)      # #1C3454
    C_TEXT1 = (51, 65, 85)      # #334155
    C_TEXT2 = (71, 85, 105)     # #475569
    C_DIV   = (100, 116, 139)   # #64748B
    C_FOOT  = (100, 116, 139)   # #64748B
    C_WARN  = (220, 38, 38)     # #DC2626

    margin_x = 90
    margin_y = 30
    width, height = size
    content_w = width - (2 * margin_x)
    y = 80

    # -----------------------------
    # Logos (com fallback)
    # assets/logo_chico.png e assets/logo_dds.png ao lado deste arquivo
    # -----------------------------
    def _safe_load_rgba(path: str) -> Image.Image | None:
        try:
            im = Image.open(path).convert("RGBA")
            return im
        except Exception:
            return None

    def _paste_logo(im_rgba: Image.Image, x0: int, y0: int, target_w: int, target_h: int) -> None:
        # Mantém proporção
        src_w, src_h = im_rgba.size
        if src_w <= 0 or src_h <= 0:
            return
        scale = min(target_w / src_w, target_h / src_h)
        nw = max(1, int(src_w * scale))
        nh = max(1, int(src_h * scale))
        resized = im_rgba.resize((nw, nh), Image.LANCZOS)
        # Centraliza dentro do box
        px = x0 + (target_w - nw) // 2
        py = y0 + (target_h - nh) // 2
        img.paste(resized, (px, py), resized)

    base_path = os.path.dirname(os.path.abspath(__file__))
    assets_path = os.path.join(base_path, "assets")
    logo_chico_path = os.path.join(assets_path, "logo_chico.png")
    logo_dds_path   = os.path.join(assets_path, "logo_dds.png")

    # Chico (esquerda)
    chico = _safe_load_rgba(logo_chico_path)
    if not chico:
        draw.rectangle([margin_x, margin_y, margin_x + 180, margin_y + 100], fill=(74, 85, 104))
        draw.text((margin_x + 20, margin_y + 35), "ChicoEletro", font=font_sub, fill=(255, 255, 255))
    else:
        _paste_logo(chico, margin_x, margin_y, 260, 120)

    # DDS (direita)
    dds = _safe_load_rgba(logo_dds_path)
    if not dds:
        # fallback: círculo laranja
        cx = width - margin_x - 50
        cy = margin_y + 50
        r = 50
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 140, 66))
        draw.text((width - margin_x - 80, margin_y + 28), "DDS", font=font_sub, fill=(255, 255, 255))
    else:
        _paste_logo(dds, width - margin_x - 120, margin_y, 120, 100)

    y = 160

    # -----------------------------
    # Título centralizado
    # -----------------------------
    title_text = "DDS ONLINE"
    if hasattr(draw, "textlength"):
        tw = float(draw.textlength(title_text, font=font_title))
    else:
        bbox = draw.textbbox((0, 0), title_text, font=font_title)
        tw = float(bbox[2] - bbox[0])

    draw.text(((width - tw) / 2, y - 60), title_text, font=font_title, fill=C_TITLE)
    y += 40

    # Linha divisória
    draw.line([(margin_x, y), (width - margin_x, y)], fill=C_DIV, width=2)
    y += 60

    # -----------------------------
    # Assunto (label + 2 linhas no máx.)
    # -----------------------------
    draw.text((margin_x, y), "Assunto:", font=font_body, fill=C_TEXT2)
    y += 60

    def _wrap_text_max_lines(text: str, font: ImageFont.ImageFont, max_width: int, max_lines: int = 2) -> List[str]:
        text = (text or "").strip()
        if not text:
            return []
        words = text.split()
        lines: List[str] = []
        cur: List[str] = []

        def _w(s: str) -> float:
            if hasattr(draw, "textlength"):
                return float(draw.textlength(s, font=font))
            bbox = draw.textbbox((0, 0), s, font=font)
            return float(bbox[2] - bbox[0])

        for word in words:
            trial = (" ".join(cur + [word])).strip()
            if not cur or _w(trial) <= max_width:
                cur.append(word)
            else:
                lines.append(" ".join(cur))
                cur = [word]
                if len(lines) >= max_lines:
                    break

        if len(lines) < max_lines and cur:
            lines.append(" ".join(cur))

        # Se estourou, aplica reticências na última linha
        if len(lines) > max_lines:
            lines = lines[:max_lines]

        if words and len(lines) == max_lines:
            # Verifica se sobrou palavra não usada; se sim, ellipsis
            used = " ".join(lines).split()
            if len(used) < len(words):
                last = lines[-1]
                ell = "…"
                # Encurta até caber com reticências
                while last and _w(last + ell) > max_width:
                    last = " ".join(last.split()[:-1])
                lines[-1] = (last + ell).strip() if last else ell
        return lines

    subject = (payload.get("subject") or "").strip()
    subject_lines = _wrap_text_max_lines(subject, font=font_sub, max_width=content_w, max_lines=2)
    for line in subject_lines:
        draw.text((margin_x, y), line, font=font_sub, fill=C_TITLE)
        y += 70
    y += 20

    # -----------------------------
    # Responsável/Anfitrião
    # -----------------------------
    host_team = (payload.get("hostTeam") or "").strip()
    draw.text((margin_x, y), f"Responsável/Anfitrião: {host_team}", font=font_body, fill=C_TEXT1)
    y += 80

    # -----------------------------
    # Data e Hora (DD/MM/AAAA)
    # -----------------------------
    date_iso = (payload.get("date") or "").strip()  # esperado YYYY-MM-DD
    time_hhmm = (payload.get("time") or "").strip() # esperado HH:MM
    date_br = date_iso
    try:
        date_br = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        pass
    draw.text((margin_x, y), f"Quando: {date_br} às {time_hhmm}", font=font_body, fill=C_TEXT1)
    y += 80

    # Duração
    dur = payload.get("durationMin")
    if dur is not None:
        draw.text((margin_x, y), f"Duração: {int(dur)} minutos", font=font_body, fill=C_TEXT1)
        y += 100

    # -----------------------------
    # IMPORTANTE (bloco vermelho)
    # -----------------------------
    box_padding = 30
    box_height = 180   # espaço extra após o texto
    box_x0 = margin_x - 20
    box_y0 = y - 20
    box_x1 = width - margin_x + 20
    box_y1 = box_y0 + box_height
    draw.rectangle([box_x0, box_y0, box_x1, box_y1], fill=C_WARN)
    # Título do alerta
    draw.text(
         (margin_x + box_padding, box_y0 + 25),
        "⚠️ IMPORTANTE",
        font=font_sub,
        fill=(255, 255, 255),
    )

    # Texto principal (centralizado verticalmente no bloco)
    draw.text(
        (margin_x + box_padding, box_y0 + 90),
        "Entre no canal com pelo menos 5 minutos de antecedência\n"
        "para evitar atrasos no início do DDS.",
        font=font_body,
        fill=(255, 255, 255),
    )

    y = box_y1 + 40
 
    # -----------------------------
    # Footer + encode JPEG (SEMPRE por último)
    # -----------------------------
    footer = "Gerado automaticamente pelo painel DDS."
    draw.text((margin_x, height - 80), footer, font=font_body, fill=C_FOOT)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()


# -----------------------------
# Storage operations
# -----------------------------

@dataclass
class OnlinePackageResult:
    """
    Result object returned to the admin panel.

    payload: the exact metadata saved as reuniao.json (compatible with app logic)
    """
    session_id: str
    folder_id: str
    slide_path: str
    meta_path: str
    lista_path: str
    payload: Dict[str, Any]



def _download_lista_json(bucket: storage.Bucket, lista_path: str) -> Tuple[List[str], int]:
    blob = bucket.blob(lista_path)
    if not blob.exists():
        return [], 0
    blob.reload()
    generation = int(blob.generation or 0)
    raw = blob.download_as_bytes()
    data = json.loads(raw.decode("utf-8"))
    files = data.get("files") or []
    return files, generation


def _upload_lista_json_atomic(
    bucket: storage.Bucket,
    lista_path: str,
    files: List[str],
    if_generation_match: int,
) -> None:
    blob = bucket.blob(lista_path)
    payload = json.dumps({"files": files}, ensure_ascii=False, indent=2).encode("utf-8")

    # if_generation_match:
    # - 0 means "only create if missing" (new object)
    # - >0 means "only update if current generation matches" (atomic update)
    blob.upload_from_string(
        payload,
        content_type="application/json",
        if_generation_match=if_generation_match if if_generation_match > 0 else 0,
    )


def _merge_paths(existing: List[str], new_paths: List[str]) -> List[str]:
    s = set(existing)
    for p in new_paths:
        if p not in s:
            existing.append(p)
            s.add(p)
    return existing


def delete_online_package_and_update_lista_json(
    *,
    bucket_name: str,
    base_prefix: str,
    folder_id: str,
) -> Dict[str, Any]:
    """
    Delete a DDS ONLINE folder and remove its file paths from DDSv2/lista.json.

    ONLINE folders contain:
      - Slide*.JPG
      - reuniao.json
    We delete everything under the folder prefix and remove matching entries from lista.json.
    """
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    folder_prefix = f"{base_prefix}/{folder_id}".replace("//", "/").strip("/")
    prefix = f"{folder_prefix}/"

    blobs = list(bucket.list_blobs(prefix=prefix))
    object_names = [b.name for b in blobs]

    lista_path = f"{base_prefix}/lista.json"
    removed_from_lista = 0

    for attempt in (1, 2):
        try:
            rebuild_lista_json(
                bucket_name=bucket_name,
                base_prefix=base_prefix,
            )
            break
        except Exception:
            if attempt == 2:
                raise

    deleted = 0
    for name in object_names:
        try:
            bucket.blob(name).delete()
            deleted += 1
        except Exception:
            pass
    return {
        "folderPrefix": prefix,
        "objectsFound": len(object_names),
        "objectsDeleted": deleted,
        "removedFromLista": removed_from_lista,
    }


def create_or_update_online_package(
    *,
    bucket_name: str,
    base_prefix: str,
    date_yyyy_mm_dd: str,
    time_hhmm: str,
    host_team: str,
    subject: str,
    duration_min: int,
    timezone_name: str = "America/Sao_Paulo",
    status: str = "scheduled",
    slides_count: int = 1,
) -> OnlinePackageResult:
    """Create or update the online package in storage and update DDSv2/lista.json.

    This function is idempotent for the same (team, date, time) because:
    - session_id is deterministic
    - folder_id is deterministic

    If called twice, it overwrites Slide1.JPG and reuniao.json safely and
    ensures lista.json contains the two paths.
    """

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    date_yyyy_mm_dd = parse_date_yyyy_mm_dd(date_yyyy_mm_dd)
    time_hhmm = parse_time_hhmm(time_hhmm)
    host_team = normalize_team(host_team)

    session_id = make_session_id(host_team, date_yyyy_mm_dd, time_hhmm)
    folder_id = make_training_folder_id(date_yyyy_mm_dd, time_hhmm)

    folder_prefix = f"{base_prefix}/{folder_id}".replace("//", "/")
    slides_count = max(1, int(slides_count))
    slide_paths = [
        f"{folder_prefix}/Slide{n}.JPG"
        for n in range(1, slides_count + 1)
    ]
    meta_path = f"{folder_prefix}/reuniao.json"
    lista_path = f"{base_prefix}/lista.json"

    payload: Dict[str, Any] = {
        "type": "online",
        "version": 1,
        "hostTeam": host_team,
        "subject": (subject or "").strip(),
        "date": date_yyyy_mm_dd,
        "time": time_hhmm,
        "timezone": timezone_name,
        "durationMin": int(duration_min),
        "sessionId": session_id,
        "channelName": session_id,
        "month_ref": month_ref(date_yyyy_mm_dd),
        "status": status,
        "source": "site",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }

    # Upload placeholder slides (Slide1..SlideN)
    for n, slide_path in enumerate(slide_paths, start=1):
        slide_bytes = render_placeholder_slide(payload, size=(1920, 1080))
        bucket.blob(slide_path).upload_from_string(
            slide_bytes,
            content_type="image/jpeg",
        )

    # Upload reuniao.json
    meta_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    bucket.blob(meta_path).upload_from_string(meta_bytes, content_type="application/json")

    # Update lista.json atomically (two attempts)
    new_paths = slide_paths + [meta_path]
    # Rebuild lista.json (ensures pruning rules are applied)
    for attempt in (1, 2):
        try:
            rebuild_lista_json(
                bucket_name=bucket_name,
                base_prefix=base_prefix,
                timezone_name=timezone_name
            )
            break
        except Exception:
            if attempt == 2:
                raise

    return OnlinePackageResult(
        session_id=session_id,
        folder_id=folder_id,
        slide_path=slide_paths[0],
        meta_path=meta_path,
        lista_path=lista_path,
        payload=payload,
    )

def list_online_packages_from_lista_json(
    *,
    bucket_name: str,
    base_prefix: str,
    month: str | None = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Build a list of online sessions by scanning DDSv2/lista.json and reading reuniao.json.

    This is used by the admin dashboard (no Firestore dependency).
    """

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    lista_path = f"{base_prefix}/lista.json"
    files, _gen = _download_lista_json(bucket, lista_path)

    # Filter for reuniao.json entries under folders matching 'YYYY-MM-DD - DDS ONLINE - HHMM'
    pattern = re.compile(r"^" + re.escape(base_prefix) + r"/(\d{4}-\d{2}-\d{2} - DDS ONLINE - \d{4})/reuniao\.json$")

    meta_paths: List[str] = []
    for p in files:
        m = pattern.match(p)
        if not m:
            continue
        folder_id = m.group(1)
        if month and not folder_id.startswith(month):
            # month here expects 'YYYY-MM'
            continue
        meta_paths.append(p)

    # Sort by folder_id descending (date + hhmm)
    meta_paths.sort(reverse=True)
    meta_paths = meta_paths[:limit]

    sessions: List[Dict[str, Any]] = []
    for meta_path in meta_paths:
        try:
            raw = bucket.blob(meta_path).download_as_bytes()
            data = json.loads(raw.decode("utf-8"))
            sessions.append(data)
        except Exception:
            # Skip malformed entries
            continue

    return sessions

def update_online_package(
    *,
    bucket_name: str,
    base_prefix: str,
    date_yyyy_mm_dd: str,
    time_hhmm: str,
    host_team: str,
    subject: str,
    duration_min: int,
    timezone_name: str = "America/Sao_Paulo",
    status: str = "scheduled",
):
    # Edit/cancel path
    return create_or_update_online_package(
        bucket_name=bucket_name,
        base_prefix=base_prefix,
        date_yyyy_mm_dd=date_yyyy_mm_dd,
        time_hhmm=time_hhmm,
        host_team=host_team,
        subject=subject,
        duration_min=duration_min,
        timezone_name=timezone_name,
        status=status,
    )


def list_online_sessions_from_storage(
    bucket_name: str,
    base_prefix: str,
    limit: int = 100,
    month: str | None = None,
    team: str | None = None,
):
    # Dashboard list path
    sessions = list_online_packages_from_lista_json(
        bucket_name=bucket_name,
        base_prefix=base_prefix,
        month=month,
        limit=limit,
    )

    if team:
        t = team.strip().upper()
        sessions = [s for s in sessions if (s.get("hostTeam") or "").strip().upper() == t]

    return sessions
def list_normal_packages_from_lista_json(
    *,
    bucket_name: str,
    base_prefix: str,
    month: str | None = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    Build a list of NORMAL trainings by scanning DDSv2/lista.json and grouping slide paths
    under folders matching 'YYYY-MM-DD - <ASSUNTO>/' (excluding 'DDS ONLINE - HHMM').

    We do NOT read Firestore, and we do NOT require reuniao.json for NORMAL.
    """
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    lista_path = f"{base_prefix}/lista.json"
    files, _gen = _download_lista_json(bucket, lista_path)

    # Example paths:
    # DDSv2/2026-01-12 - SONO/Slide1.JPG
    # DDSv2/2026-01-16 - TALABARTE E TRAVA QUEDA/TALABARTE ... Slide1.jpg
    #
    # We capture folder_id = "YYYY-MM-DD - <ASSUNTO>" and accept any filename containing Slide<digits>.
    # Exclude DDS ONLINE folders explicitly.
    folder_pattern = re.compile(
        r"^"
        + re.escape(base_prefix)
        + r"/(\d{4}-\d{2}-\d{2} - (?!DDS ONLINE - \d{4}).+?)/(.+)$"
    )
    slide_num_pattern = re.compile(r"(?i)\bslide\s*(\d+)\b")

    grouped: dict[str, list[int]] = defaultdict(list)
    first_slide_path: dict[str, str] = {}

    for p in files:
        m = folder_pattern.match(p)
        if not m:
            continue
        folder_id = m.group(1)  # "YYYY-MM-DD - ASSUNTO"
        filename = m.group(2)

        # Month filter uses folder_id prefix "YYYY-MM"
        if month and not folder_id.startswith(month):
            continue

        sm = slide_num_pattern.search(filename)
        if not sm:
            continue

        n = int(sm.group(1))
        grouped[folder_id].append(n)
        # Track first slide path for potential preview/use
        if n == 1 and folder_id not in first_slide_path:
            first_slide_path[folder_id] = p

    # Sort folders desc by date (folder_id begins with YYYY-MM-DD)
    folder_ids = sorted(grouped.keys(), reverse=True)[:limit]

    sessions: List[Dict[str, Any]] = []
    for folder_id in folder_ids:
        date = folder_id[:10]
        subject = folder_id[13:].strip() if len(folder_id) > 13 else ""
        nums = grouped.get(folder_id) or []
        slides_count = max(nums) if nums else 0

        sessions.append(
            {
                "type": "normal",
                "version": 1,
                "folderId": folder_id,
                "date": date,
                "subject": subject,
                # Fields that exist in ONLINE but not in NORMAL:
                "hostTeam": "",
                "time": "",
                "durationMin": None,
                "status": "scheduled",
                "slidesCount": slides_count,
                "slidePath": first_slide_path.get(folder_id, ""),
                "source": "storage-lista",
            }
        )

    return sessions

def list_all_sessions_from_storage(
    *,
    bucket_name: str,
    base_prefix: str,
    limit_online: int = 60,
    limit_normal: int = 200,
    month: str | None = None,
    team: str | None = None,
) -> List[Dict[str, Any]]:
    """
    Dashboard helper: returns ONLINE + NORMAL sessions.
    - ONLINE: read reuniao.json (has sessionId, hostTeam, time, duration)
    - NORMAL: derived from slide folders listed in lista.json (no sessionId)
    """
    online = list_online_packages_from_lista_json(
        bucket_name=bucket_name,
        base_prefix=base_prefix,
        month=month,
        limit=limit_online,
    )
    if team:
        t = team.strip().upper()
        online = [s for s in online if (s.get("hostTeam") or "").strip().upper() == t]

    normal = list_normal_packages_from_lista_json(
        bucket_name=bucket_name,
        base_prefix=base_prefix,
        month=month,
        limit=limit_normal,
    )

    return online + normal


def list_all_folders_from_storage(
    *,
    bucket_name: str,
    base_prefix: str,
) -> List[Dict[str, Any]]:
    """
    LISTAGEM REAL (EXPLORADOR):
    Varre o bucket fisicamente em busca de pastas, ignorando o lista.json.
    Permite ver treinamentos que estão arquivados ou fora do 'limite de 5' do App.
    """
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    prefix = base_prefix.strip("/") + "/"
    # delimiter='/' faz o GCS retornar os "diretórios" em blobs.prefixes
    iterator = bucket.list_blobs(prefix=prefix, delimiter='/')
    
    # Executa o iterador para preencher os prefixes
    for _ in iterator:
        pass
    
    raw_prefixes = iterator.prefixes # Ex: ["DDSv2/2026-01-01 - DDS ONLINE - 0800/", ...]
    
    # Pegamos o que está ATUALMENTE no lista.json para marcar o status
    lista_path = f"{base_prefix}/lista.json"
    files_in_index, _ = _download_lista_json(bucket, lista_path)
    files_in_index_set = set(files_in_index)

    folders = []
    for pref in sorted(list(raw_prefixes), reverse=True):
        folder_id = pref.replace(prefix, "").strip("/")
        if not folder_id: continue
        
        # Tenta extrair info básica do nome
        date = folder_id[:10]
        subject = folder_id[13:] if len(folder_id) > 13 else "Sem Assunto"
        is_online = "DDS ONLINE" in folder_id.upper()
        
        # Verifica se PELO MENOS UM arquivo desta pasta está no lista.json
        # (Isso define se ela está "Publicada" ou não)
        is_published = any(f.startswith(pref) for f in files_in_index_set)

        folders.append({
            "folderId": folder_id,
            "date": date,
            "subject": subject,
            "type": "online" if is_online else "normal",
            "is_published": is_published,
            "full_prefix": pref
        })

    return folders
    return folders