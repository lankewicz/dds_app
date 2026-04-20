# utils/image_ingest.py
from io import BytesIO
from typing import Tuple, Optional
from PIL import Image, ImageOps
import filetype

try:
    from pillow_heif import register_heif_opener  # HEIC/HEIF/AVIF
    register_heif_opener()
except Exception:
    pass

ACCEPTED_MIME = {
    "image/jpeg","image/jpg","image/png","image/webp",
    "image/heic","image/heif","image/avif","image/tiff","image/bmp","image/gif"
}
DEFAULT_JPEG_QUALITY = 90
THUMB_MAX = 1280

def sniff_mime(content: bytes) -> Optional[str]:
    kind = filetype.guess(content)
    return kind.mime if kind else None

def _needs_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA","LA") or ("transparency" in img.info)

def _open_image(content: bytes) -> Image.Image:
    img = Image.open(BytesIO(content))
    return ImageOps.exif_transpose(img)

def _to_webp(img: Image.Image) -> bytes:
    if img.mode not in ("RGB","RGBA"):
        img = img.convert("RGBA")
    buf = BytesIO(); img.save(buf, "WEBP", quality=90, method=6); return buf.getvalue()

def _to_jpeg(img: Image.Image, quality: int = DEFAULT_JPEG_QUALITY) -> bytes:
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = BytesIO(); img.save(buf, "JPEG", quality=quality, optimize=True); return buf.getvalue()

def normalize_image(content: bytes, force_jpeg: bool=False, jpeg_bg: str="#FFFFFF") -> Tuple[bytes,str,dict]:
    """
    Retorna: (conteudo_normalizado, mime_final, meta)
    meta: {original_mime, stored_mime, stored_ext, converted, width, height}
    """
    mime = sniff_mime(content)
    if not mime or mime not in ACCEPTED_MIME:
        raise ValueError(f"MIME não suportado: {mime or 'desconhecido'}")

    img = _open_image(content)

    # GIF animado: usar 1º frame (estático)
    if mime == "image/gif":
        try: img.seek(0); img = img.convert("RGBA")
        except Exception: pass

    has_alpha = _needs_alpha(img)

    if force_jpeg and has_alpha:
        # achata alpha em fundo sólido para salvar em JPEG
        bg = Image.new("RGB", img.size, jpeg_bg)
        if img.mode != "RGBA": img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1])
        out = _to_jpeg(bg); out_mime, out_ext = "image/jpeg", ".jpg"
    elif has_alpha:
        out = _to_webp(img); out_mime, out_ext = "image/webp", ".webp"
    else:
        out = _to_jpeg(img); out_mime, out_ext = "image/jpeg", ".jpg"

    w, h = img.size
    meta = {
        "original_mime": mime, "stored_mime": out_mime, "stored_ext": out_ext,
        "converted": out_mime != mime, "width": w, "height": h
    }
    return out, out_mime, meta

def make_thumb(content_normalized: bytes, max_side: int = THUMB_MAX) -> Tuple[bytes,str]:
    img = Image.open(BytesIO(content_normalized))
    w, h = img.size
    scale = max(w, h) / max_side if max(w, h) > max_side else 1.0
    if scale > 1.0:
        img = img.resize((int(w/scale), int(h/scale)), Image.LANCZOS)

    if _needs_alpha(img):
        return _to_webp(img), "image/webp"
    return _to_jpeg(img), "image/jpeg"
