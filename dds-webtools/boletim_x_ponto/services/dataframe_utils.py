# d:\programas\DDS\dds-webtools\boletim_x_ponto\services\dataframe_utils.py
from __future__ import annotations
from collections.abc import Iterable, Sequence
from typing import Literal, cast
from difflib import get_close_matches
import pandas as pd

def _filtrar_periodo(df: pd.DataFrame, di, dfim) -> pd.DataFrame:
    if df is None or df.empty or "Data" not in df.columns:
        return pd.DataFrame()
    return df[(df["Data"] >= di) & (df["Data"] <= dfim)]

def resolver_base_ponto(df_ponto: pd.DataFrame,
                        df_relacao: pd.DataFrame,
                        nome_boletim: str,
                        data_ini,
                        data_fim,
                        corte_similaridade: float = 0.75):
    """
    Decide como filtrar o DF de ponto para um funcionário do BOLETIM:
    1) Relação por CPF
    2) Relação por PIS
    3) Relação por Nome_Ponto_Mapeado (case-insensitive)
    4) Fallback por similaridade de nome (get_close_matches), se nada acima resolver.

    Retorna: (df_filtrado_no_periodo, origem, identificador_usado)
      - origem ∈ {"CPF","PIS","NOME_MAPEADO","SIMILARIDADE","INEXISTENTE"}
      - identificador_usado: o CPF/PIS/Nome aplicado (ou None)
    """
    if df_ponto is None or df_ponto.empty or not isinstance(df_ponto, pd.DataFrame):
        return pd.DataFrame(), "INEXISTENTE", None

    di = pd.to_datetime(data_ini)
    dfim = pd.to_datetime(data_fim)

    # 1) Relação
    if df_relacao is not None and not df_relacao.empty:
        rel = df_relacao[df_relacao["Nome_Boletim"] == nome_boletim]
        if not rel.empty:
            r = rel.iloc[0]
            cpf = str(r.get("CPF_Ponto") or "").strip()
            pis = str(r.get("PIS_Ponto") or "").strip()
            nome_map = str(r.get("Nome_Ponto_Mapeado") or "").strip()

            if cpf and "CPF" in df_ponto.columns and not df_ponto[df_ponto["CPF"] == cpf].empty:
                base = df_ponto[df_ponto["CPF"] == cpf]
                base = base[(base["Data"] >= di) & (base["Data"] <= dfim)]
                return base, "CPF", cpf

            if pis and "PIS" in df_ponto.columns and not df_ponto[df_ponto["PIS"] == pis].empty:
                base = df_ponto[df_ponto["PIS"] == pis]
                base = base[(base["Data"] >= di) & (base["Data"] <= dfim)]
                return base, "PIS", pis

            if nome_map and "Nome" in df_ponto.columns:
                mask = df_ponto["Nome"].astype(str).str.upper() == nome_map.upper()
                if mask.any():
                    base = df_ponto[mask]
                    base = base[(base["Data"] >= di) & (base["Data"] <= dfim)]
                    return base, "NOME_MAPEADO", nome_map

    # 2) Fallback por similaridade
    if "Nome" in df_ponto.columns:
        nomes = df_ponto["Nome"].dropna().astype(str).unique().tolist()
        alvos = [n.upper() for n in nomes]
        match = get_close_matches(str(nome_boletim).upper(), alvos, n=1, cutoff=corte_similaridade)
        if match:
            nome_real = next(n for n in nomes if n.upper() == match[0])
            base = df_ponto[df_ponto["Nome"] == nome_real]
            base = base[(base["Data"] >= di) & (base["Data"] <= dfim)]
            return base, "SIMILARIDADE", nome_real

    return pd.DataFrame(), "INEXISTENTE", None


def _strip_series(s: pd.Series) -> pd.Series:
    try:
        return s.astype(str).str.strip()
    except Exception:
        return s


def promote_first_row_as_header_if_needed(
    df: pd.DataFrame, expected_header_keys: Sequence[str] = ("Data", "DATA", "Dia", "date", "Date")
) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    if isinstance(df.columns, pd.RangeIndex):
        primeira_linha = _strip_series(df.iloc[0])
        if any(key in set(primeira_linha.values) for key in expected_header_keys):
            new_cols = list(primeira_linha.values)
            df2 = df.rename(columns=dict(zip(df.columns, new_cols))).iloc[1:].reset_index(drop=True)
            return df2

    return df


def normalize_date_column(
    df: pd.DataFrame,
    candidates: Sequence[str] = ("Data", "DATA", "Dia", "DIA", "date", "Date"),
    target_name: str = "Data",
    dayfirst: bool = True,
) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    if target_name not in df.columns:
        lower_map = {str(c).lower(): c for c in df.columns}
        for cand in candidates:
            key = str(cand).lower()
            if key in lower_map:
                df = df.rename(columns={lower_map[key]: target_name})
                break

    idx_name = str(df.index.name) if df.index.name is not None else ""
    if target_name not in df.columns and idx_name:
        if idx_name.lower() in [str(c).lower() for c in candidates]:
            df = df.reset_index().rename(columns={df.columns[0]: target_name})

    if target_name in df.columns:
        df[target_name] = pd.to_datetime(df[target_name], dayfirst=dayfirst, errors="coerce")
        df = df[df[target_name].notna()].copy()

    return df


def coerce_numeric_columns(
    df: pd.DataFrame,
    include: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
    errors: Literal["raise", "coerce"] = "coerce",
) -> pd.DataFrame:
    cols = (
        list(include)
        if include is not None
        else [c for c in df.columns if c not in (exclude or [])]
    )
    for c in cols:
        try:
            df[c] = pd.to_numeric(df[c], errors=cast(Literal["raise", "coerce"], errors))
        except Exception:
            pass
    return df


def normalizar_df_ponto(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    df = promote_first_row_as_header_if_needed(df, expected_header_keys=("Data", "DATA", "Dia"))
    df = normalize_date_column(
        df,
        candidates=("Data", "DATA", "Dia", "DIA", "date", "Date"),
        target_name="Data",
        dayfirst=True,
    )

    colunas_possiveis = [
        "Total Normais",
        "Total Noturno",
        "Extra 50%D",
        "Extra 100%D",
        "Extra 50%N",
        "Extra 100%N",
        "Deslocamento",
        "DESLOC.",
        "DESLOC",
        "KM",
        "KM Rodado",
        "Serviços",
        "SERV.",
        "Interjornada",
    ]
    existentes = [c for c in colunas_possiveis if c in df.columns]
    if existentes:
        df = coerce_numeric_columns(df, include=existentes)

    return df


def normalizar_df_boletim(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    df = promote_first_row_as_header_if_needed(
        df, expected_header_keys=("Data", "DATA", "Dia", "Funcionário", "Registro", "Contrato")
    )
    df = normalize_date_column(
        df, candidates=("Data", "DATA", "Dia", "date", "Date"), target_name="Data", dayfirst=True
    )

    colunas_possiveis = [
        "SERV.",
        "KM",
        "HORA NORMAL",
        "H.E.",
        "H.E.D.",
        "H.E.N.",
        "H.E.N.D.",
        "S.A.",
        "H.N.",
        "DESLOC.",
        "PROD.",
    ]
    existentes = [c for c in colunas_possiveis if c in df.columns]
    df = coerce_numeric_columns(df, include=existentes)

    return df


def groupby_sum_by_date(df: pd.DataFrame, date_col: str = "Data") -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    if date_col not in df.columns:
        return pd.DataFrame()

    if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
        coer = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
        if coer.notna().any():
            df = df.assign(**{date_col: coer}).loc[coer.notna()].copy()
        else:
            return pd.DataFrame()

    agrupado = df.groupby(df[date_col].dt.date, dropna=True).sum(numeric_only=True)
    if agrupado.empty:
        return pd.DataFrame()
    agrupado.index.name = date_col
    return agrupado.reset_index()


def horas_decimal_para_hhmm(valor) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "0:00"

    try:
        s = str(valor).strip().replace(",", ".")
        f = float(s)
    except Exception:
        return "0:00"

    negativo = f < 0
    f = abs(f)

    horas = int(f)
    minutos = round((f - horas) * 60)

    if minutos == 60:
        horas += 1
        minutos = 0

    s = f"{horas}:{minutos:02d}"
    return f"-{s}" if negativo else s


def hhmm_para_decimal(texto: str) -> float | None:
    if texto is None:
        return None

    t = str(texto).strip()
    if not t:
        return None

    negativo = t.startswith("-")
    if negativo:
        t = t[1:].strip()

    if ":" not in t:
        try:
            v = float(t.replace(",", "."))
            return -v if negativo else v
        except Exception:
            return None

    hh, mm = t.split(":", 1)
    try:
        h = int(hh)
        m = int(mm)
        if m < 0 or m > 59:
            return None
        dec = h + (m / 60.0)
        return -dec if negativo else dec
    except Exception:
        return None


def preparar_df_ponto_para_comparacao(df_ponto: pd.DataFrame, data_ini=None, data_fim=None) -> pd.DataFrame:
    if df_ponto is None or df_ponto.empty:
        return pd.DataFrame()

    df_norm = normalizar_df_ponto(df_ponto)

    if "Data" not in df_norm.columns:
        return pd.DataFrame()

    if data_ini is not None and data_fim is not None:
        di = pd.to_datetime(data_ini)
        dfim = pd.to_datetime(data_fim)
        df_norm = df_norm[(df_norm["Data"] >= di) & (df_norm["Data"] <= dfim)]

    return groupby_sum_by_date(df_norm, date_col="Data")


def preparar_df_boletim_para_comparacao(df_boletim: pd.DataFrame) -> pd.DataFrame:
    df_boletim = normalizar_df_boletim(df_boletim)
    if "Data" not in df_boletim.columns:
        colunas_visiveis = list(map(str, df_boletim.columns))
        raise ValueError(
            f"Coluna 'Data' não encontrada em df_boletim após normalização. Colunas: {colunas_visiveis[:12]}"
        )
    return df_boletim

__all__ = [
    "coerce_numeric_columns",
    "groupby_sum_by_date",
    "hhmm_para_decimal",
    "horas_decimal_para_hhmm",
    "normalizar_df_boletim",
    "normalizar_df_ponto",
    "normalize_date_column",
    "preparar_df_boletim_para_comparacao",
    "preparar_df_ponto_para_comparacao",
    "promote_first_row_as_header_if_needed",
    "resolver_base_ponto",
]
