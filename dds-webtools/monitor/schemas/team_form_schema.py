# -----------------------------------------------------------------------------
# Arquivo : schemas/team_form_schema.py
# Objetivo: Definir o payload validado do formulário da equipe, incluindo os
#           equipamentos vinculados, metadados da última alteração e motivo
#           transitório para persistência do histórico.
# -----------------------------------------------------------------------------

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class EquipmentPayload(BaseModel):
    summary: str | None = None
    serial: str | None = None
    patrimonio: str | None = None
    imei: str | None = None
    phoneNumber: str | None = None
    email: str | None = None
    lastChangedAt: str | None = None
    lastChangeReason: str | None = None
    changeReason: str | None = None


class TeamEquipmentPayload(BaseModel):
    tablet: EquipmentPayload = Field(default_factory=EquipmentPayload)
    cameraCopel: EquipmentPayload = Field(default_factory=EquipmentPayload)
    cameraVeicular: EquipmentPayload = Field(default_factory=EquipmentPayload)


class TeamBasePayload(BaseModel):
    teamKey: str
    displayName: str
    members: List[str] = Field(default_factory=list)
    equipment: TeamEquipmentPayload = Field(default_factory=TeamEquipmentPayload)
    active: bool = True


class TeamTurnoPayload(BaseModel):
    empresa: str
    teamKey: str
    estado: str | None = None
    nocSs: str | None = None
    motivo: str | None = None
    horaEntrada: str | None = None
    horaSaida: str | None = None
    observacoes: str | None = None


class TeamFormPayload(BaseModel):
    team: TeamBasePayload
    turno: TeamTurnoPayload
