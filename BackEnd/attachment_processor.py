# attachment_processor.py (revisão segura)
# Processa partes de mensagem, decodifica nomes de anexos,
# salva arquivos simples e extrai arquivos compactados em subpastas.
# Mudanças principais:
# - Corrige 'path' fora de escopo.
# - Centraliza normalização de imagens em utils.image_normalizer.normalize_if_png.
# - Usa TemporaryDirectory (limpeza automática).
# - Hardening contra ZipSlip: garante que o destino final fique dentro de 'folder'.
# - Aceita attachments 'inline' com filename.
# - Fallback: se .gz não for tar, salva como arquivo simples (evita erro enganoso).
# - Remove imports não usados.

import os
import re
import zipfile
import tarfile
import logging
import tempfile
from email.header import decode_header, make_header

# Bibliotecas opcionais
try:
    import rarfile  # pip install rarfile (pode exigir unrar no SO)
except ImportError:
    rarfile = None
try:
    import py7zr  # pip install py7zr
except ImportError:
    py7zr = None

from utils.image_normalizer import normalize_if_png
from config import INVALID_CHARS

logger = logging.getLogger(__name__)

SUPPORTED_ARCHIVES = {
    ".zip", ".tar", ".gz", ".tgz", ".tar.gz", ".rar", ".7z"
}

def sanitize_filename(raw_name: str) -> str:
    """Decodifica header MIME, remove chars inválidos e evita caminhos."""
    decoded = str(make_header(decode_header(raw_name)))
    # troca separadores de caminho e sequências potencialmente perigosas
    decoded = decoded.replace("/", "_").replace("\\", "_").replace("..", ".")
    for c in INVALID_CHARS:
        decoded = decoded.replace(c, "_")
    decoded = re.sub(r"[_\s]+", " ", decoded).strip()
    return decoded

def _safe_join(base_dir: str, rel_name: str) -> str:
    """
    Gera um caminho seguro dentro de base_dir.
    Lança ValueError se escapar da pasta (ZipSlip).
    """
    dest = os.path.normpath(os.path.join(base_dir, rel_name))
    base_norm = os.path.normpath(base_dir)
    if os.path.commonprefix([os.path.normcase(dest), os.path.normcase(base_norm)]) != os.path.normcase(base_norm):
        raise ValueError(f"Caminho inseguro detectado: {rel_name!r}")
    return dest

def _save_simple_file(data: bytes, folder: str, filename: str) -> str:
    """Salva payload binário em folder/filename, normaliza PNG se aplicável. Retorna caminho final."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    with open(path, "wb") as f:
        f.write(data)
    logger.info("Salvo arquivo simples: %s", path)
    # Normalização pós-salva (ex.: PNG → JPG) centralizada
    try:
        final_path = normalize_if_png(path)
        if final_path != path:
            logger.info("Normalizado: %s → %s", path, final_path)
            path = final_path
    except Exception as e:
        logger.warning("Falha normalizando imagem (%s): %s", path, e)
    return path

def _try_extract_archive(data: bytes, folder: str, filename: str) -> bool:
    """
    Tenta extrair um arquivo compactado para subpastas dentro de 'folder'.
    Retorna True se extraiu, False se deve cair no fluxo de arquivo simples.
    """
    # Usamos pasta temporária com cleanup automático
    with tempfile.TemporaryDirectory(prefix="dds_") as temp_dir:
        archive_path = os.path.join(temp_dir, filename)
        with open(archive_path, "wb") as f:
            f.write(data)

        # Detecta formato via conteúdo quando possível
        ext = os.path.splitext(filename)[1].lower()
        extracted = False
        try:
            if zipfile.is_zipfile(archive_path):
                with zipfile.ZipFile(archive_path) as z:
                    z.extractall(temp_dir)
                extracted = True
            elif tarfile.is_tarfile(archive_path):
                with tarfile.open(archive_path) as t:
                    # Segurança extra: recusa membros com paths inseguros
                    for member in t.getmembers():
                        rel = sanitize_filename(member.name)
                        _safe_join(folder, rel)
                    t.extractall(temp_dir)
                extracted = True
            elif ext == ".rar" and rarfile:
                with rarfile.RarFile(archive_path) as r:
                    # checagem prévia
                    for info in r.infolist():
                        rel = sanitize_filename(info.filename)
                        _safe_join(folder, rel)
                    r.extractall(temp_dir)
                extracted = True
            elif ext == ".7z" and py7zr:
                with py7zr.SevenZipFile(archive_path, mode="r") as sz:
                    # py7zr não dá tamanhos antes facilmente; seguimos com extração
                    sz.extractall(path=temp_dir)
                extracted = True
            else:
                # Pode ser .gz “puro” (não tar). Nesses casos preferimos NÃO falhar.
                # Sinaliza ao chamador para salvar como simples.
                logger.info("Arquivo %s não reconhecido como pacote extraível; fallback para salvar simples.", filename)
                return False
        except Exception as e:
            logger.error("Falha ao extrair %s: %s", filename, e)
            return False

        if not extracted:
            return False

        # Move conteúdos extraídos para 'folder'
        for root, _, files in os.walk(temp_dir):
            for f in files:
                # pula o próprio arquivo de entrada, se aparecer no walk
                if root == temp_dir and f == filename:
                    continue
                src = os.path.join(root, f)
                rel = os.path.relpath(src, temp_dir)
                clean_rel = sanitize_filename(rel)
                try:
                    dest = _safe_join(folder, clean_rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    os.replace(src, dest)
                    logger.info("Extraído e salvo: %s", dest)
                    # Normalização pós-extração (ex.: PNG → JPG)
                    try:
                        final_path = normalize_if_png(dest)
                        if final_path != dest:
                            logger.info("Normalizado: %s → %s", dest, final_path)
                    except Exception as e:
                        logger.warning("Falha normalizando imagem extraída (%s): %s", dest, e)
                except Exception as e:
                    logger.error("Falha movendo arquivo extraído (%s): %s", clean_rel, e)
        return True

def process_attachment(part, folder: str) -> None:
    """
    Processa uma parte de e-mail:
      - Se é pacote suportado, tenta extrair; se falhar, salva como simples.
      - Caso contrário, salva diretamente como arquivo simples.
    Aceita 'attachment' e 'inline' (quando tiver filename).
    """
    disp = (part.get_content_disposition() or "").lower()
    if disp not in ("attachment", "inline"):
        logger.debug("Ignorado (nem attachment nem inline): %s", part.get_content_type())
        return

    raw_name = part.get_filename()
    if not raw_name:
        logger.debug("Ignorado sem filename: %s", part.get_content_type())
        return

    filename = sanitize_filename(raw_name)
    data = part.get_payload(decode=True) or b""

    # Heurística de “parece pacote” pela extensão — mas validamos por conteúdo no _try_extract_archive
    ext = os.path.splitext(filename)[1].lower()
    if ext in SUPPORTED_ARCHIVES:
        logger.info("Possível arquivo compactado: %s", filename)
        if _try_extract_archive(data, folder, filename):
            return  # ok, já extraímos

    # fallback / arquivo simples
    _save_simple_file(data, folder, filename)
