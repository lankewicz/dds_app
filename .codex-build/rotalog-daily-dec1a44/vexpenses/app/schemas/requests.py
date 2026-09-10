# Finalidade: schemas de consulta e retorno das solicitações importadas.
from datetime import date, datetime
from decimal import Decimal

from typing import Any
from pydantic import BaseModel, ConfigDict, field_validator


class BalanceRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_alocacao: str
    usuario_origem: str
    data_solicitacao: date
    previsao_uso: date | None
    valor_solicitado: Decimal
    justificativa: str | None
    status: str | None
    aprovador: str | None
    data_aprovacao: date | None
    valor_aprovado: Decimal | None
    source_filename: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("valor_solicitado", "valor_aprovado", mode="before")
    @classmethod
    def parse_numeric(cls, v: Any) -> Decimal:
        if v is None or v == "":
            return Decimal("0.00")
        try:
            if isinstance(v, (int, float)):
                # No Firestore os dados estão em centavos (ex: 10500 = R$ 105,00)
                return (Decimal(str(v)) / 100).quantize(Decimal("0.01"))
            if isinstance(v, str):
                clean_v = v.replace("R$", "").replace("$", "").replace(".", "").replace(",", ".").strip()
                # Assume que se vier do Firestore como string, também está em centavos
                return (Decimal(clean_v) / 100).quantize(Decimal("0.01"))
        except:
            return Decimal("0.00")
        return Decimal("0.00")

    @field_validator("data_solicitacao", "previsao_uso", "data_aprovacao", mode="before")
    @classmethod
    def parse_dates(cls, v: Any) -> date | None:
        if v is None or v == "":
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.split("T")[0]).date()
            except:
                return None
        return None
class PaginatedBalanceRequests(BaseModel):
    items: list[BalanceRequestOut]
    total: int
    page: int
    page_size: int
