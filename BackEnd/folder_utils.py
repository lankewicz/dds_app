# Module: folder_utils.py
# Description: Geração e criação de pastas de trabalho para cada e-mail,
#              usando data extraída do assunto ou data atual, com assunto sanitizado.
# Change Log:
#   29-05-25:  • Implementação inicial de funções de pasta com data atual.
#   30-05-25:  • Adicionada extração de data do subject em vários formatos.
#   31-05-25:  • Ajustes para suportar formatos DD/MM/YYYY, MM-DD-YY, etc.
# Guia de Comentários:
#   - parse_subject_to_folder(): tenta extrair data e tema do subject.
#   - make_email_folder(): utiliza parse_subject_to_folder para nomear e criar pasta.

import os
import logging

logger = logging.getLogger(__name__)
import re
from datetime import date
from email.header import decode_header, make_header
from config import DDS_BASE, INVALID_CHARS

# Padrões de data suportados
DATE_PATTERNS = [
    r"^(?P<year>\d{4})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})[\s-]+(?P<text>.+)$",
    r"^(?P<day>\d{1,2})[./-](?P<month>\d{1,2})[./-](?P<year>\d{2,4})[\s-]+(?P<text>.+)$",
    r"^(?P<day>\d{1,2})[./-](?P<month>\d{1,2})[\s-]+(?P<text>.+)$",
]

INVALID_CHARS = INVALID_CHARS  # importado do config


def sanitize_text(text: str) -> str:
    """Decodifica header MIME, remove caracteres inválidos e normaliza espaços."""
    decoded = str(make_header(decode_header(text)))
    for c in INVALID_CHARS:
        decoded = decoded.replace(c, '_')
    return re.sub(r'[_\s]+', ' ', decoded).strip().upper()


def parse_subject_to_folder(raw_subject: str) -> (str, date):
    """
    Tenta extrair data e texto do subject usando padrões definidos.
    Se extrair, converte para date e texto sanitizado.
    Se não, usa data atual e todo subject como texto.
    Retorna (folder_name, date_obj).
    """
    decoded = str(make_header(decode_header(raw_subject or ""))).strip()
    for pat in DATE_PATTERNS:
        m = re.match(pat, decoded)
        if m:
            gd = m.groupdict()
            year = int(gd.get('year')) if 'year' in gd and gd['year'] else date.today().year
            month = int(gd.get('month'))
            day = int(gd.get('day'))
            text = gd.get('text')
            try:
                date_obj = date(year, month, day)
            except ValueError:
                date_obj = date.today()
            clean_text = sanitize_text(text)
            folder_date = date_obj.strftime('%Y-%m-%d')
            return f"{folder_date} - {clean_text}", date_obj
    # fallback: hoje e todo subject (sem prefixo de data para ser ignorado pelo indexador se não for um DDS válido)
    today = date.today()
    clean_text = sanitize_text(decoded)
    return clean_text, today


def make_email_folder(subject: str) -> str:
    """
    Gera e cria pasta em DDS_BASE com base no subject:
      - Extrai data e texto via parse_subject_to_folder.
      - Cria e retorna o caminho completo.
    """
    folder_name, _ = parse_subject_to_folder(subject)
    full_path = os.path.join(DDS_BASE, folder_name)
    os.makedirs(full_path, exist_ok=True)
    return full_path


def cleanup_non_media(folder: str) -> None:
    """
    Remove arquivos que não são imagens ou vídeos de 'folder'.
    Se houver subpastas vazias, remove-as. Não remove o 'folder' raiz.
    """
    # Extensões válidas de imagens e vídeos
    media_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp',
                  '.mp4', '.mov', '.avi', '.mkv', '.wmv'}

    for root, dirs, files in os.walk(folder, topdown=False):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in media_exts:
                try:
                    os.remove(os.path.join(root, f))
                    logger.info("Removido não-mídia: %s", f)
                except Exception as e:
                    logger.error("Erro removendo %s: %s", f, e)
        # checar se diretório vazio após remoções
        # se for subpasta e vazia, remove
        if root != folder and not os.listdir(root):
            try:
                os.rmdir(root)
                logger.info("Subpasta vazia removida: %s", root)
            except Exception as e:
                logger.error("Erro removendo subpasta %s: %s", root, e)
