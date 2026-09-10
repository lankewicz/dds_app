# Finalidade: endpoints de relatórios agregados e exportação usando Firestore.
from datetime import date
from pathlib import Path
from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.core.config import settings
from app.schemas.reports import MonthlyReportRow, SummaryReportOut, TopUserReportRow
from app.services.report_service import ReportService

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])

@router.get("/resumo-geral", response_model=SummaryReportOut)
def get_summary_report(
    data_inicio: date | None = Query(default=None),
    data_fim: date | None = Query(default=None),
    aprovador: str | None = Query(default=None),
    usuario: str | None = Query(default=None),
    status: str | None = Query(default=None),
    ano: int | None = Query(default=None),
    mes: int | None = Query(default=None),
) -> SummaryReportOut:
    service = ReportService()
    return service.summary(data_inicio=data_inicio, data_fim=data_fim, aprovador=aprovador, usuario=usuario, status=status, ano=ano, mes=mes)

@router.get("/por-mes", response_model=list[MonthlyReportRow])
def get_monthly_report(
    data_inicio: date | None = Query(default=None),
    data_fim: date | None = Query(default=None),
    aprovador: str | None = Query(default=None),
    usuario: str | None = Query(default=None),
    status: str | None = Query(default=None),
    ano: int | None = Query(default=None),
    mes: int | None = Query(default=None),
    sort_by: str = Query(default="ano"),
    order: str = Query(default="desc"),
) -> list[MonthlyReportRow]:
    service = ReportService()
    return service.monthly(
        data_inicio=data_inicio, 
        data_fim=data_fim, 
        aprovador=aprovador, 
        usuario=usuario, 
        status=status, 
        ano=ano, 
        mes=mes,
        sort_by=sort_by,
        order=order
    )

@router.get("/por-dia")
def get_daily_report(
    ano: int,
    mes: int,
    data_inicio: date | None = Query(default=None),
    data_fim: date | None = Query(default=None),
    aprovador: str | None = Query(default=None),
    usuario: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    service = ReportService()
    return service.daily(
        year=ano, 
        month=mes, 
        data_inicio=data_inicio, 
        data_fim=data_fim, 
        aprovador=aprovador, 
        usuario=usuario, 
        status=status
    )

@router.get("/top-usuarios", response_model=list[TopUserReportRow])
def get_top_users(
    limite: int = Query(default=20, ge=1, le=200),
    data_inicio: date | None = Query(default=None),
    data_fim: date | None = Query(default=None),
    aprovador: str | None = Query(default=None),
    usuario: str | None = Query(default=None),
    status: str | None = Query(default=None),
    ano: int | None = Query(default=None),
    mes: int | None = Query(default=None),
    sort_by: str = Query(default="total_solicitado"),
    order: str = Query(default="desc"),
) -> list[TopUserReportRow]:
    service = ReportService()
    return service.top_users(
        limit=limite, 
        data_inicio=data_inicio, 
        data_fim=data_fim, 
        aprovador=aprovador, 
        usuario=usuario, 
        status=status, 
        ano=ano, 
        mes=mes,
        sort_by=sort_by,
        order=order
    )

@router.get("/exportar-csv")
def export_csv(
    data_inicio: date | None = Query(default=None),
    data_fim: date | None = Query(default=None),
    aprovador: str | None = Query(default=None),
    usuario: str | None = Query(default=None),
    status: str | None = Query(default=None),
    ano: int | None = Query(default=None),
    mes: int | None = Query(default=None),
) -> FileResponse:
    service = ReportService()
    output_dir = Path(settings.csv_export_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = service.export_csv(
        output_dir=output_dir, data_inicio=data_inicio, data_fim=data_fim, aprovador=aprovador, usuario=usuario, status=status, ano=ano, mes=mes
    )
    return FileResponse(path=csv_path, media_type="text/csv", filename=csv_path.name)

@router.get("/exportar-xlsx")
def export_xlsx(
    data_inicio: date | None = Query(default=None),
    data_fim: date | None = Query(default=None),
    aprovador: str | None = Query(default=None),
    usuario: str | None = Query(default=None),
    status: str | None = Query(default=None),
    ano: int | None = Query(default=None),
    mes: int | None = Query(default=None),
    sort_by: str = Query(default="data_solicitacao"),
    order: str = Query(default="asc"),
) -> FileResponse:
    service = ReportService()
    output_dir = Path(settings.csv_export_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = service.export_xlsx(
        output_dir=output_dir, 
        data_inicio=data_inicio, 
        data_fim=data_fim, 
        aprovador=aprovador, 
        usuario=usuario,
        status=status,
        ano=ano,
        mes=mes,
        sort_by=sort_by,
        order=order
    )
    return FileResponse(path=file_path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=file_path.name)

@router.get("/exportar-pdf")
def export_pdf(
    data_inicio: date | None = Query(default=None),
    data_fim: date | None = Query(default=None),
    aprovador: str | None = Query(default=None),
    usuario: str | None = Query(default=None),
    status: str | None = Query(default=None),
    ano: int | None = Query(default=None),
    mes: int | None = Query(default=None),
    sort_by: str = Query(default="data_solicitacao"),
    order: str = Query(default="asc"),
) -> FileResponse:
    service = ReportService()
    output_dir = Path(settings.csv_export_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = service.export_pdf(
        output_dir=output_dir, 
        data_inicio=data_inicio, 
        data_fim=data_fim, 
        aprovador=aprovador, 
        usuario=usuario,
        status=status,
        ano=ano,
        mes=mes,
        sort_by=sort_by,
        order=order
    )
    return FileResponse(path=file_path, media_type="application/pdf", filename=file_path.name)

@router.get("/filtros")
def get_filters():
    service = ReportService()
    return service.get_filter_options()
