# -----------------------------------------------------------------------------
# Módulo: email_utils.py
# Versão: 4.2 (Suporte a HTML)
# -----------------------------------------------------------------------------

import os
import smtplib
from email.message import EmailMessage
from typing import Optional, List

from config import SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASS

def send_response(
    to_addr: str,
    subject: str,
    body: str,
    attachments: Optional[List[str]] = None,
    html_body: Optional[str] = None  # <-- Novo parâmetro
) -> None:
    """
    Envia um e-mail via SMTP com suporte a anexos e corpo em HTML.
    """
    msg = EmailMessage()
    msg['From'] = SMTP_USER
    msg['To'] = to_addr
    msg['Subject'] = subject
    
    # Define o corpo de texto puro (para clientes de e-mail que não suportam HTML)
    msg.set_content(body)

    # Se um corpo HTML for fornecido, anexa como uma alternativa
    if html_body:
        msg.add_alternative(html_body, subtype='html')

    if attachments:
        for file_path in attachments:
            if not os.path.exists(file_path):
                continue
            ctype, encoding = 'application', 'octet-stream'
            if '.' in file_path:
                ext = file_path.split('.')[-1].lower()
                if ext == 'pdf': ctype, encoding = 'application', 'pdf'
                elif ext in ['jpg', 'jpeg', 'png', 'gif']: ctype, encoding = 'image', ext
            with open(file_path, 'rb') as fp:
                msg.add_attachment(fp.read(), maintype=ctype, subtype=encoding, filename=os.path.basename(file_path))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)