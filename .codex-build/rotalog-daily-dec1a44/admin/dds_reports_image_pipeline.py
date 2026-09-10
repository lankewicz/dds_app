# -----------------------------------------------------------------------------
# Módulo: dds_reports_image_pipeline.py
# Finalidade: Centralizar a normalização e a geração de thumbs/fotos usadas
#             pelos relatórios DDS, mantendo o PDF leve e a lógica isolada.
# -----------------------------------------------------------------------------

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageOps

logger = logging.getLogger(__name__)

# Configurações padrão via variáveis de ambiente
THUMB_CACHE_MAX_PX = int(os.getenv("DDS_THUMB_CACHE_MAX_PX", "1600"))
THUMB_CACHE_MAX_BYTES = int(os.getenv("DDS_THUMB_CACHE_MAX_BYTES", "1500000"))
THUMB_CACHE_JPEG_QUALITY = int(os.getenv("DDS_THUMB_CACHE_QUALITY", "78"))

PDF_THUMB_MAX_SIDE_PX = int(os.getenv("DDS_PDF_THUMB_MAX_SIDE_PX", "160"))
PDF_THUMB_DPI = int(os.getenv("DDS_PDF_THUMB_DPI", "96"))
PDF_THUMB_JPEG_QUALITY = int(os.getenv("DDS_PDF_THUMB_QUALITY", "50"))


def pt_to_px(pt: float, dpi: int) -> int:
    """Converte pontos para pixels com base no DPI."""
    return max(1, int(round(pt * dpi / 72.0)))


def _to_rgb_without_alpha(im: PILImage.Image) -> PILImage.Image:
    """Remove o canal alfa, aplicando fundo branco caso exista transparência."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in (im.info or {})):
        im_rgba = im.convert("RGBA")
        bg = PILImage.new("RGB", im_rgba.size, (255, 255, 255))
        bg.paste(im_rgba, mask=im_rgba.split()[-1])
        return bg
    return im.convert("RGB")


def normalize_image_inplace(
    src_path: Path,
    *,
    max_px: int = THUMB_CACHE_MAX_PX,
    quality: int = THUMB_CACHE_JPEG_QUALITY,
) -> bool:
    """Normaliza a imagem local em cache para reduzir custo de memória e tamanho do PDF."""
    try:
        if not src_path.is_file() or src_path.stat().st_size <= 0:
            return False

        with PILImage.open(src_path) as im:
            im = ImageOps.exif_transpose(im)
            
            if max(im.size) > max_px:
                im.thumbnail((max_px, max_px), resample=PILImage.LANCZOS)
            
            im = _to_rgb_without_alpha(im)

            # Salva temporariamente e depois substitui para evitar corrupção de arquivo
            tmp_path = src_path.with_name(f"{src_path.name}.tmp")
            im.save(tmp_path, format="JPEG", quality=quality, optimize=True, progressive=True)
            
            tmp_path.replace(src_path)
            
        return True
    except Exception as exc:
        logger.warning("Falha ao normalizar imagem in-place (%s): %s", src_path, exc)
        return False


def prepare_thumb_for_pdf(
    src_path: Path,
    out_dir: Path,
    width_pt: float,
    height_pt: float,
    *,
    dpi: int = PDF_THUMB_DPI,
    quality: int = PDF_THUMB_JPEG_QUALITY,
    max_side_px: int = PDF_THUMB_MAX_SIDE_PX,
) -> Path:
    """Gera uma thumb JPEG pronta para PDF com sistema de cache (hash).

    Observação: no layout atual do relatório (60x45 pt), a área visível já fica
    abaixo de 160 px. O parâmetro max_side_px fica como teto para futuras telas
    ou layouts maiores, sem deixar a thumb crescer demais.
    """
    if not src_path.is_file():
        return src_path

    out_dir.mkdir(parents=True, exist_ok=True)

    w_px = pt_to_px(width_pt, dpi)
    h_px = pt_to_px(height_pt, dpi)

    if max_side_px > 0 and max(w_px, h_px) > max_side_px:
        scale = float(max_side_px) / float(max(w_px, h_px))
        w_px = max(1, int(round(w_px * scale)))
        h_px = max(1, int(round(h_px * scale)))

    # Geração da chave de cache única
    cache_key = f"{src_path.resolve()}|{src_path.stat().st_mtime}|{w_px}x{h_px}|q{quality}"
    cache_hash = hashlib.md5(cache_key.encode("utf-8")).hexdigest()[:16]
    
    out_path = out_dir / f"{src_path.stem}_opt_{cache_hash}.jpg"
    if out_path.exists():
        return out_path

    try:
        with PILImage.open(src_path) as im:
            im = ImageOps.exif_transpose(im)
            im = _to_rgb_without_alpha(im)
            im.thumbnail((w_px, h_px), resample=PILImage.LANCZOS)
            im.save(out_path, format="JPEG", quality=quality, optimize=True, progressive=True)
        return out_path
    except Exception as exc:
        logger.warning("Falha ao preparar thumb para PDF (%s): %s", src_path, exc)
        return src_path