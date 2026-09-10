"""Regras puras de presença do ROTALOG, sem dependências de interface."""

from __future__ import annotations

import re
import unicodedata

import pandas as pd


def normalizar_nome_rotalog(valor) -> str:
    nome = "" if valor is None else str(valor).strip()
    nome = re.sub(r"^\s*\d+\s*[-–—]\s*", "", nome)
    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join(ch for ch in nome if not unicodedata.combining(ch))
    nome = re.sub(r"[^A-Z0-9]+", " ", nome.upper())
    return " ".join(nome.split())


def mapear_presenca_funcionario_por_data(
    df_equipes: pd.DataFrame, funcionario: str
) -> dict[pd.Timestamp, str]:
    if df_equipes is None or df_equipes.empty:
        return {}
    alvo = normalizar_nome_rotalog(funcionario)
    if not alvo:
        return {}

    df = df_equipes.copy()
    date_column = next(
        (column for column in ("Data", "Data Referência - Turno") if column in df.columns),
        None,
    )
    if not date_column:
        return {}
    if date_column == "Data Referência - Turno":
        raw_dates = df[date_column].astype(str).str.extract(
            r"(\d{2}/\d{2}/\d{4})", expand=False
        )
        df["_data_rotalog"] = pd.to_datetime(
            raw_dates, format="%d/%m/%Y", errors="coerce"
        ).dt.floor("D")
    else:
        df["_data_rotalog"] = pd.to_datetime(
            df[date_column], errors="coerce", dayfirst=True
        ).dt.floor("D")
    df = df.dropna(subset=["_data_rotalog"])

    name_columns = [
        column
        for column in (
            "Eletricista 1 (Matrícula e Nome)",
            "Eletricista 2 (Matrícula e Nome)",
            "Eletricista 1",
            "Eletricista 2",
            "Eletricista",
        )
        if column in df.columns
    ]
    result = {}
    for day, group in df.groupby("_data_rotalog"):
        found = any(
            normalizar_nome_rotalog(value) == alvo
            for column in name_columns
            for value in group[column].dropna()
        )
        result[pd.Timestamp(day).floor("D")] = "✓" if found else "✕"
    return result
