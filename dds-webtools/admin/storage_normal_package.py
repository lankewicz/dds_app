"""
============================================================
FILE: storage_normal_package.py
FUNCTION: Create the DDS NORMAL "package" in Firebase Storage / GCS
          to preserve app compatibility:
          - Create folder: DDSv2/YYYY-MM-DD - <ASSUNTO>/
Upload Slide1..SlideN.JPG (placeholders)
          - Update DDSv2/lista.json (append paths) atomically
============================================================
"""

from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont
from google.cloud import storage
from training_management.indexing import rebuild_lista_json


def _load_fonts() -> Tuple[ImageFont.ImageFont, ImageFont.ImageFont, ImageFont.ImageFont]:
    try:
        title = ImageFont.truetype("DejaVuSans-Bold.ttf", 72)
        sub = ImageFont.truetype("DejaVuSans-Bold.ttf", 48)
        body = ImageFont.truetype("DejaVuSans.ttf", 42)
        return title, sub, body
    except Exception:
        f = ImageFont.load_default()
        return f, f, f


def _sanitize_subject_for_folder(subject: str, *, max_len: int = 80) -> str:
    """
    Sanitiza o assunto para usar como nome de pasta:
    - remove apenas separadores de path (/, \)
    - remove chars de controle
    - colapsa espaços
    - preserva acentos (como no seu exemplo de lista.json)
    """
    s = (subject or "").strip().upper()
    s = s.replace("/", " ").replace("\\", " ")
    s = re.sub(r"\s+", " ", s)
    # Remove apenas caracteres de controle (0x00-0x1F e 0x7F)
    s = re.sub(r"[\x00-\x1F\x7F]", "", s).strip()
    if not s:
        s = "DDS"
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


def parse_date_yyyy_mm_dd(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return d.strftime("%Y-%m-%d")


def month_ref(date_yyyy_mm_dd: str) -> str:
    return date_yyyy_mm_dd[:7]


def make_session_id_normal(date_yyyy_mm_dd: str, folder_id: str) -> str:
    # sessionId determinístico o suficiente: usa data + hash leve do folder_id
    # (mantém curta e estável; evita caracteres estranhos)
    d = datetime.strptime(date_yyyy_mm_dd, "%Y-%m-%d").strftime("%Y%m%d")
    slug = re.sub(r"[^A-Z0-9]+", "_", folder_id.upper())[:32].strip("_")
    return f"DDS_NORMAL_{d}_{slug}"


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



def delete_normal_package_and_update_lista_json(
    *,
    bucket_name: str,
    base_prefix: str,
    folder_id: str,
) -> Dict[str, Any]:
    """
    Delete a DDS NORMAL folder and remove its slide paths from DDSv2/lista.json.

    - Deletes all objects under: {base_prefix}/{folder_id}/
    - Removes from lista.json any entries that start with that prefix
    """
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    folder_prefix = f"{base_prefix}/{folder_id}".replace("//", "/").strip("/")
    prefix = f"{folder_prefix}/"

    # 1) List objects to delete
    blobs = list(bucket.list_blobs(prefix=prefix))
    object_names = [b.name for b in blobs]

    # 2) Update lista.json atomically: remove paths under this folder
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

    # 3) Delete objects (best-effort after lista.json is consistent)
    deleted = 0
    for name in object_names:
        try:
            bucket.blob(name).delete()
            deleted += 1
        except Exception:
            # best-effort: keep going
            pass

    return {
        "folderPrefix": prefix,
        "objectsFound": len(object_names),
        "objectsDeleted": deleted,
        "removedFromLista": removed_from_lista,
    }


def render_placeholder_slide_normal(payload: Dict[str, Any], size: Tuple[int, int] = (1920, 1080)) -> bytes:
    """Placeholder Slide1.JPG para DDS NORMAL (slideshow)."""
    img = Image.new("RGB", size, (240, 242, 245))
    draw = ImageDraw.Draw(img)
    font_title, font_sub, font_body = _load_fonts()

    C_TITLE = (28, 52, 84)
    C_TEXT1 = (51, 65, 85)
    C_TEXT2 = (71, 85, 105)
    C_DIV   = (100, 116, 139)
    C_FOOT  = (100, 116, 139)

    margin_x = 90
    width, height = size
    y = 80

    # Logos (mesma lógica do online, com fallback)
    def _safe_load_rgba(path: str):
        try:
            return Image.open(path).convert("RGBA")
        except Exception:
            return None

    def _paste_logo(im_rgba, x0, y0, target_w, target_h):
        src_w, src_h = im_rgba.size
        if src_w <= 0 or src_h <= 0:
            return
        scale = min(target_w / src_w, target_h / src_h)
        nw = max(1, int(src_w * scale))
        nh = max(1, int(src_h * scale))
        resized = im_rgba.resize((nw, nh), Image.LANCZOS)
        px = x0 + (target_w - nw) // 2
        py = y0 + (target_h - nh) // 2
        img.paste(resized, (px, py), resized)

    base_path = os.path.dirname(os.path.abspath(__file__))
    assets_path = os.path.join(base_path, "assets")
    logo_chico_path = os.path.join(assets_path, "logo_chico.png")
    logo_dds_path   = os.path.join(assets_path, "logo_dds.png")

    chico = _safe_load_rgba(logo_chico_path)
    if chico:
        _paste_logo(chico, margin_x, 30, 260, 120)
    else:
        draw.rectangle([margin_x, 30, margin_x + 180, 130], fill=(74, 85, 104))
        draw.text((margin_x + 20, 65), "ChicoEletro", font=font_sub, fill=(255, 255, 255))

    dds = _safe_load_rgba(logo_dds_path)
    if dds:
        _paste_logo(dds, width - margin_x - 120, 30, 120, 100)
    else:
        cx = width - margin_x - 50
        cy = 80
        r = 50
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 140, 66))
        draw.text((width - margin_x - 80, 58), "DDS", font=font_sub, fill=(255, 255, 255))

    y = 160

    title_text = "DDS"
    try:
        tw = float(draw.textlength(title_text, font=font_title))
    except Exception:
        bbox = draw.textbbox((0, 0), title_text, font=font_title)
        tw = float(bbox[2] - bbox[0])
    draw.text(((width - tw) / 2, y - 60), title_text, font=font_title, fill=C_TITLE)
    y += 40

    draw.line([(margin_x, y), (width - margin_x, y)], fill=C_DIV, width=2)
    y += 60

    draw.text((margin_x, y), "Assunto:", font=font_body, fill=C_TEXT2)
    y += 60

    subject = (payload.get("subject") or "").strip()
    if not subject:
        subject = "DDS"
    draw.text((margin_x, y), subject, font=font_sub, fill=C_TITLE)
    y += 120

    date_iso = (payload.get("date") or "").strip()
    date_br = date_iso
    try:
        date_br = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        pass
    draw.text((margin_x, y), f"Data: {date_br}", font=font_body, fill=C_TEXT1)

    footer = "Treinamento (slideshow) — gerado automaticamente pelo painel DDS."
    draw.text((margin_x, height - 80), footer, font=font_body, fill=C_FOOT)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()


@dataclass
class NormalPackageResult:
    session_id: str
    folder_id: str
    slide_path: str
    meta_path: str
    lista_path: str
    payload: Dict[str, Any]


def create_normal_package_and_update_lista_json(
    *,
    bucket_name: str,
    base_prefix: str,
    date_yyyy_mm_dd: str,
    subject: str,
    timezone_name: str = "America/Sao_Paulo",
    slides_count: int = 1,
    status: str = "scheduled",
) -> NormalPackageResult:
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    date_yyyy_mm_dd = parse_date_yyyy_mm_dd(date_yyyy_mm_dd)
    subject_clean = _sanitize_subject_for_folder(subject)

    # Pasta nomeada por data + assunto (como você pediu)
    base_folder = f"{date_yyyy_mm_dd} - {subject_clean}"

    # Evita colisão se existir outra pasta idêntica:
    # tenta "- 2", "- 3", ... usando a existência do reuniao.json como sinal
    folder_id = base_folder
    for n in range(2, 50):
        test_slide1 = f"{base_prefix}/{folder_id}/Slide1.JPG".replace("//", "/")
        if not bucket.blob(test_slide1).exists():
            break
        folder_id = f"{base_folder} - {n}"

    folder_prefix = f"{base_prefix}/{folder_id}".replace("//", "/")
    slides_count = max(1, int(slides_count))

    # IMPORTANTE: DDS NORMAL -> lista.json deve conter SOMENTE slides
    slide_paths = [f"{folder_prefix}/Slide{n}.JPG" for n in range(1, slides_count + 1)]
    lista_path = f"{base_prefix}/lista.json"

    session_id = make_session_id_normal(date_yyyy_mm_dd, folder_id)

    # Observação: DDS NORMAL não precisa de reuniao.json para o app,
    # mas mantemos um payload retornado para a UI/controle do painel.
    payload: Dict[str, Any] = {
        "type": "normal",
        "version": 1,
        "subject": (subject or "").strip(),
        "date": date_yyyy_mm_dd,
        "timezone": timezone_name,
        "sessionId": session_id,
        "status": status,
        "source": "site",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }

    # Placeholders: criamos Slide1..SlideN (o usuário pode sobrescrever via upload)
    for slide_path in slide_paths:
        slide_bytes = render_placeholder_slide_normal(payload, size=(1920, 1080))
        bucket.blob(slide_path).upload_from_string(slide_bytes, content_type="image/jpeg")

    # DDS NORMAL: lista.json inclui apenas os slides
    new_paths = slide_paths
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

    return NormalPackageResult(
        session_id=session_id,
        folder_id=folder_id,
        slide_path=slide_paths[0],
        meta_path="",
        lista_path=lista_path,
        payload=payload,
    )
