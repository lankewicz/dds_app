# Finalidade: centralizar as configurações carregadas do ambiente.
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sistema de Solicitações de Saldo"
    app_env: str = "development"
    app_debug: bool = True
    default_timezone: str = "America/Sao_Paulo"
    upload_tmp_dir: str = "./tmp/uploads"
    csv_export_dir: str = "./tmp/exports"
    app_revision: str = "012-rx9"  # Fallback ou valor fixo se não houver ambiente
    
    # Firebase Settings
    firebase_project_id: str | None = None
    firebase_storage_bucket: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
