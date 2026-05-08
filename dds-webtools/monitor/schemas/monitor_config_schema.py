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
    fechadoViraDesatualizadoHoras: int = Field(..., ge=1)
    desatualizadoCriticoHoras: int = Field(..., ge=1)

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.alertaVermelhoMin < self.alertaAmareloMin:
            raise ValueError("O alerta vermelho deve ser maior ou igual ao amarelo.")
        if self.alertaPiscoMin < self.alertaVermelhoMin:
            raise ValueError("O alerta em pisco deve ser maior ou igual ao vermelho.")
        if self.desatualizadoCriticoHoras < self.fechadoViraDesatualizadoHoras:
            raise ValueError("O crítico deve ser maior ou igual ao tempo para virar desatualizado.")
        return self


class MonitorConfigPayload(BaseModel):
    pollingSeconds: int = Field(..., ge=15)
    rules: MonitorRulesPayload
