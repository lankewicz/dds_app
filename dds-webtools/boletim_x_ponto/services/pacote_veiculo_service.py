"""Geração do pacote WEB por veículo/equipe."""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any

import pandas as pd

from boletim_x_ponto.services.comparacao import montar_triplet_comparacao
from boletim_x_ponto.services.constantes import HEADERS_VIZ
from boletim_x_ponto.services.exportador_service import exportar_comparacao_individual_excel
from boletim_x_ponto.services.veiculos_service import normalizar_veiculo


def _safe_name(value: str, fallback: str = "arquivo") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "")).strip("_")
    return cleaned or fallback


def _vehicle_column(df: pd.DataFrame) -> str | None:
    if df is None:
        return None
    for column in df.columns:
        if str(column).strip().casefold() in {"veículo", "veiculo", "equipe"}:
            return column
    normalized = {
        re.sub(r"[^A-Z0-9]+", "", str(column).upper()): column
        for column in df.columns
    }
    for candidate in ("VEICULO", "EQUIPE"):
        if candidate in normalized:
            return normalized[candidate]
    return None


def filtrar_rotalog_veiculo(
    df: pd.DataFrame,
    veiculo: str,
    contrato: str | None = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    column = _vehicle_column(df)
    if not column:
        return pd.DataFrame(columns=df.columns)
    result = df[df[column].map(normalizar_veiculo) == normalizar_veiculo(veiculo)].copy()
    if contrato and "Contrato" in result:
        result = result[
            result["Contrato"].astype(str).str.strip() == str(contrato).strip()
        ]
    return result.reset_index(drop=True)


def gerar_pacote_veiculo_zip(
    service: Any,
    veiculo: str,
    data_ini: str,
    data_fim: str,
    contrato: str | None = None,
    format_hhmm: bool = False,
) -> bytes:
    view = service.get_vehicle_comparison(veiculo, data_ini, data_fim, contrato)
    employees = sorted({
        str(row.get("funcionario") or "").strip()
        for row in view.get("linhas", [])
        if str(row.get("funcionario") or "").strip()
        and str(row.get("funcionario") or "").strip() != "Não identificado"
    })

    equipes = service.repository.read("rotalog_equipes", data_ini, data_fim)
    eventos = service.repository.read("rotalog_eventos", data_ini, data_fim)
    equipes = filtrar_rotalog_veiculo(equipes, veiculo, contrato)
    eventos = filtrar_rotalog_veiculo(eventos, veiculo, contrato)

    output = io.BytesIO()
    vehicle_name = _safe_name(normalizar_veiculo(veiculo), "veiculo")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        rotalog_buffer = io.BytesIO()
        with pd.ExcelWriter(rotalog_buffer, engine="openpyxl") as writer:
            equipes.to_excel(writer, sheet_name="Equipes_Turnos", index=False)
            eventos.to_excel(writer, sheet_name="Eventos_Protocolos", index=False)
        archive.writestr(
            f"ROTALOG_Equipe_{vehicle_name}.xlsx", rotalog_buffer.getvalue()
        )

        for employee in employees:
            bulletin, point = service._get_employee_dataframes(
                employee, data_ini, data_fim
            )
            df_b, df_p, df_d, _, _, _ = montar_triplet_comparacao(
                bulletin,
                point,
                service.df_relacao_nomes,
                employee,
                pd.Timestamp(data_ini),
                pd.Timestamp(data_fim),
            )
            has_metrics = any(
                (not frame.empty) and header in frame.columns
                for frame in (df_b, df_p, df_d)
                for header in HEADERS_VIZ
            )
            if not has_metrics:
                archive.writestr(
                    f"SEM_COMPARACAO_{_safe_name(employee, 'funcionario')}.txt",
                    f"Não foram encontrados dados comparáveis para {employee} no período.",
                )
                continue
            report = exportar_comparacao_individual_excel(
                df_b,
                df_p,
                df_d,
                employee,
                pd.Timestamp(data_ini),
                pd.Timestamp(data_fim),
                format_hhmm,
            )
            archive.writestr(
                f"Comparacao_{_safe_name(employee, 'funcionario')}.xlsx", report
            )

        archive.writestr(
            "LEIA-ME.txt",
            "Pacote gerado pela versão WEB.\n"
            "Inclui os dados do ROTALOG e uma comparação por eletricista.\n"
            "Os PDFs originais dos cartões-ponto não fazem parte do pacote porque "
            "a base Parquet armazena os registros processados, não os arquivos de origem.\n",
        )
    return output.getvalue()
