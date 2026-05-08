# Finalidade: schemas das respostas de relatórios e agregações.
from decimal import Decimal

from pydantic import BaseModel


class SummaryReportOut(BaseModel):
    total_registros: int
    total_solicitado: Decimal
    total_aprovado: Decimal
    total_reprovado: Decimal
    total_glosado: Decimal = Decimal("0.00")
    diferenca_total: Decimal
    ticket_medio_solicitado: Decimal
    ticket_medio_aprovado: Decimal


class MonthlyReportRow(BaseModel):
    ano: int
    mes: int
    quantidade: int
    total_solicitado: Decimal
    total_aprovado: Decimal
    total_reprovado: Decimal
    total_glosado: Decimal = Decimal("0.00")


class TopUserReportRow(BaseModel):
    usuario_origem: str
    quantidade: int
    total_solicitado: Decimal
    total_aprovado: Decimal
    total_reprovado: Decimal
    total_glosado: Decimal = Decimal("0.00")
