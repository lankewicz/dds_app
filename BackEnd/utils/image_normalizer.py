"""
image_normalizer.py — utilitário simples para normalizar imagens no pipeline de anexos.
- PNG → JPG (fundo branco, se houver transparência)
- Retorna o caminho final do arquivo (pode ser o mesmo, se nada mudar)
"""
from PIL import Image
import os
import logging

log = logging.getLogger(__name__)

JPEG_QUALITY = int(os.getenv("DDS_JPEG_QUALITY", "88"))  # override via env, se quiser

def normalize_if_png(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext != ".png":
        return path

    try:
        with Image.open(path) as im:
            # Se tiver alpha, achata em branco
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                rgba = im.convert("RGBA")
                bg.paste(rgba, mask=rgba.split()[-1])
                img_rgb = bg
            else:
                img_rgb = im.convert("RGB")

            out_path = os.path.splitext(path)[0] + ".jpg"
            img_rgb.save(out_path, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)

        # Remove o PNG original (best effort)
        try:
            os.remove(path)
        except Exception:
            pass

        log.info("PNG normalizado para JPG: %s → %s", path, out_path)
        return out_path

    except Exception as e:
        log.warning("Falha normalizando PNG (%s): %s", path, e)
        return path