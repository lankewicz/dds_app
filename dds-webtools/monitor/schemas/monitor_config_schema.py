# -----------------------------------------------------------------------------
# Arquivo : schemas/monitor_config_schema.py
# Objetivo: Validar o payload da tela de configuração dos tempos do monitor.
# -----------------------------------------------------------------------------

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class MonitorRulesPayload(BaseModel):
    alertaAmareloMin: int = Field(..., ge=1)
    alertaVermelhoMin: int = Field(..., ge=1)
    alertaPiscoMin: int = Field(..., ge=1)
    autoDesatualizaFechadoHours: int | None = Field(None, ge=1)
    fechadoViraDesatualizadoHoras: int | None = Field(None, ge=1)
    desatualizadoCriticoHoras: int = Field(..., ge=1)

    @model_validator(mode="after")
    def validate_ranges(self):
        # Fallback para garantir que temos o valor de fechado
        fechado_val = self.autoDesatualizaFechadoHours or self.fechadoViraDesatualizadoHoras
        if fechado_val is None:
            raise ValueError("O tempo para equipe fechada virar desatualizada é obrigatório.")

        if self.alertaVermelhoMin < self.alertaAmareloMin:
            raise ValueError("O alerta vermelho deve ser maior ou igual ao amarelo.")
        if self.alertaPiscoMin < self.alertaVermelhoMin:
            raise ValueError("O alerta em pisco deve ser maior ou igual ao vermelho.")
        if self.desatualizadoCriticoHoras < fechado_val:
            raise ValueError("O crítico deve ser maior ou igual ao tempo para virar desatualizado.")
        return self


class MonitorConfigPayload(BaseModel):
    pollingSeconds: int = Field(..., ge=15)
    rules: MonitorRulesPayload
