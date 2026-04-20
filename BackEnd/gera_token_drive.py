#!/usr/bin/env python
# gera_token_drive.py
# Gera/atualiza o .secrets/token_drive.json usado por drive_utils.get_service()

from __future__ import annotations

from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/drive"]

# Usa exatamente o arquivo definido no .env
CRED_PATH = Path("init/credentials_drive.json")
TOKEN_PATH = Path(".secrets/token_drive.json")


def main():
    if not CRED_PATH.exists():
        raise SystemExit(f"Credenciais OAuth não encontradas: {CRED_PATH}")

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[INFO] Token expirado, tentando refresh…")
            creds.refresh(Request())
        else:
            print("[INFO] Abrindo navegador para autenticar no Google…")
            flow = InstalledAppFlow.from_client_secrets_file(str(CRED_PATH), SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print(f"[OK] Novo token salvo em {TOKEN_PATH}")
    else:
        print("[OK] Token existente ainda é válido; nada a fazer.")


if __name__ == "__main__":
    main()
