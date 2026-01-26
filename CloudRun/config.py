"""
============================================================
FILE: config.py
FUNCTION: Centralized configuration for DDS Admin Site.
         Reads environment variables and provides defaults.
============================================================
"""

import os


def env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


class Config:
    # ---------------------------------------------------------
    # Flask session / security
    # ---------------------------------------------------------
    SECRET_KEY = env("APP_SECRET_KEY", "")

    # ---------------------------------------------------------
    # Simple admin authentication (MVP)
    # ---------------------------------------------------------
    ADMIN_PASSWORD = env("ADMIN_PASSWORD", "")

    # ---------------------------------------------------------
    # Firebase Storage / Google Cloud Storage
    # ---------------------------------------------------------
    BUCKET_NAME = env("DDS_BUCKET_NAME", "")
    BASE_PREFIX = env("DDS_BASE_PREFIX", "DDSv2")

    # ---------------------------------------------------------
    # Signed URL (Cloud Run)
    # ---------------------------------------------------------
    # Em Cloud Run, para gerar Signed URLs V4 sem chave privada,
    # o back-end deve assinar via IAMCredentials (signBlob).
    # Configure com a Service Account que assinará as URLs (normalmente
    # a mesma do serviço): dds-admin-sa@dds-treinamentos.iam.gserviceaccount.com
    SIGNING_SERVICE_ACCOUNT = env("SIGNING_SERVICE_ACCOUNT", "")

    # ---------------------------------------------------------
    # UI / Scheduling
    # ---------------------------------------------------------
    TIMEZONE_NAME = env("DDS_TIMEZONE", "America/Sao_Paulo")

    # ---------------------------------------------------------
    # Optional features
    # ---------------------------------------------------------
    ENABLE_FIRESTORE = env("ENABLE_FIRESTORE", "false").lower() in ("1", "true", "yes")
