# Module: imap_utils.py
# Description: Funções utilitárias para conectar ao IMAP,
#              buscar e-mails não lidos e marcá-los como lidos.
# Change Log:
#   05-06-25:  • Implementação inicial de conexão e busca de e-mails.
# Guia de Comentários:
#   - connect_imap(): retorna instância logada de IMAP4_SSL.
#   - fetch_unseen(): retorna lista de IDs de mensagens UNSEEN.
#   - mark_read(): adiciona flag \\Seen à mensagem.

import imaplib
import logging
from config import IMAP_SERVER, IMAP_PORT, IMAP_USER, IMAP_PASS, MAILBOX

logger = logging.getLogger(__name__)

def connect_imap() -> imaplib.IMAP4_SSL:
    """Conecta ao servidor IMAP por SSL e faz login."""
    imap = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    imap.login(IMAP_USER, IMAP_PASS)
    return imap

def fetch_unseen(imap: imaplib.IMAP4_SSL) -> list[bytes]:
    """Retorna lista de IDs de e-mails não lidos (UNSEEN)."""
    imap.select(MAILBOX)
    status, data = imap.search(None, 'UNSEEN')
    if status != 'OK':
        logger.error("Falha ao buscar e-mails: %s", status)
        return []
    return data[0].split()

def mark_read(imap: imaplib.IMAP4_SSL, msg_id: bytes) -> None:
    """Marca mensagem como lida adicionando flag \\Seen."""
    imap.store(msg_id, '+FLAGS', '\\Seen')
