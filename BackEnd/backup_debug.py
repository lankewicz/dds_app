#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
backup_debug.py
---------------
Roda o comando BACKUP de forma síncrona direto pela linha de comando,
sem passar pelo dispatcher / e-mail.
"""

from core.cmd_backup import comando_backup

# Se quiser logar por e-mail mesmo, use seu próprio endereço
SENDER_DEBUG = "valdinei.pco@gmail.com"  # ajuste se quiser

if __name__ == "__main__":
    import sys
    argumento = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    comando_backup(argumento, SENDER_DEBUG)
