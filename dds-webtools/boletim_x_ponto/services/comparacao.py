# d:\programas\DDS\dds-webtools\boletim_x_ponto\services\comparacao.py
from __future__ import annotations
import math
from typing import Dict, Iterable, List, Tuple
import pandas as pd

from boletim_x_ponto.services.constantes import HEADERS_VIZ, MAP_BOL, MAP_PTO
from boletim_x_ponto.services.dataframe_utils import (
    preparar_df_boletim_para_comparacao,
    preparar_df_ponto_para_comparacao,
    resolver_base_ponto,
    groupby_sum_by_date,
)

def _decimal_to_hhmm(v: float | int | None) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    try:
        neg = v < 0
        v = abs(float(v))
        h = int(v)
        m = int(round((v - h) * 60))
        if m >= 60:
            h += 1
            m -= 60
        s = f"{h:d}:{m:02d}"
        return f"-{s}" if neg else s
    except Exception:
        return str(v)


def _format_df(df: pd.DataFrame, exibir_hhmm: bool) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Data"] + (["Boletim"] if "Boletim" in (df.columns if df is not None else []) else []) + HEADERS_VIZ)

    out = df.copy()
    if "Data" in out.columns:
        out["Data"] = pd.to_datetime(out["Data"], errors="coerce").dt.floor("D")

    for col in HEADERS_VIZ:
        if col in out.columns:
            if exibir_hhmm:
                out[col] = out[col].apply(_decimal_to_hhmm)
            else:
                out[col] = pd.to_numeric(out[col], errors="coerce").round(2)
    return out


def ensure_boletim(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Data", "Boletim"] + HEADERS_VIZ)
    if "Boletim" in df.columns:
        return df
    out = df.copy()
    out["Boletim"] = ""
    cols = ["Data", "Boletim"] + [c for c in HEADERS_VIZ if c in out.columns]
    return out[cols]


def _limpa_boletim(valor) -> str:
    if pd.isna(valor):
        return ""
    s = str(valor).strip()
    if s.endswith(".0"):
        try:
            s = str(int(float(s)))
        except Exception:
            pass
    if s.isdigit():
        s = s.lstrip("0") or "0"
    return s


def map_boletim_por_data(
    dados_df: pd.DataFrame,
    funcionario: str,
    data_ini,
    data_fim,
) -> Dict[pd.Timestamp, str]:
    if dados_df is None or dados_df.empty:
        return {}

    try:
        di_date = pd.Timestamp(data_ini).date()
    except Exception:
        di_date = data_ini
    try:
        df_date = pd.Timestamp(data_fim).date()
    except Exception:
        df_date = data_fim

    mask = (
        (dados_df["Funcionário"] == funcionario)
        & (pd.to_datetime(dados_df["DATA"], errors="coerce").dt.date >= di_date)
        & (pd.to_datetime(dados_df["DATA"], errors="coerce").dt.date <= df_date)
    )
    dfb = dados_df.loc[mask, ["DATA", "BOLETIM"]].copy()
    if dfb.empty:
        return {}

    dfb["DATA"] = pd.to_datetime(dfb["DATA"], errors="coerce").dt.floor("D")
    dfb["BOL_LIMPO"] = dfb["BOLETIM"].map(_limpa_boletim)

    out = {}
    for d, grupo in dfb.groupby("DATA", sort=True):
        vals = [v for v in grupo["BOL_LIMPO"].tolist() if v]
        out[d] = vals[0] if vals else ""
    return out


def _row_as_list(row: pd.Series, headers: Iterable[str]) -> List[str]:
    lst = []
    for h in headers:
        v = row.get(h, None)
        if pd.isna(v):
            lst.append("")
        elif isinstance(v, (int, float)):
            num = round(float(v), 2)
            if abs(num) < 1e-9:
                num = 0.0
            lst.append(f"{num:.2f}".replace(".", ","))
        else:
            s = str(v)
            if "." in s and "," not in s:
                try:
                    float(s)
                    s = s.replace(".", ",")
                except Exception:
                    pass
            lst.append(s)
    return lst


def montar_tres_grids(
    datas_mes: List[str],
    df_b: pd.DataFrame,
    df_p: pd.DataFrame,
    df_d: pd.DataFrame,
    bol_map: Dict[pd.Timestamp, str] | None = None,
    rotalog_map: Dict[pd.Timestamp, str] | None = None,
) -> Tuple[List[List[str]], List[List[str]], List[List[str]], List[str]]:
    def to_map(df: pd.DataFrame) -> Dict[pd.Timestamp, pd.Series]:
        if df is None or df.empty or "Data" not in df.columns:
            return {}
        dfx = df.copy()
        dfx["Data"] = pd.to_datetime(dfx["Data"], errors="coerce").dt.floor("D")
        return {d: row for d, row in dfx.set_index("Data").iterrows()}

    map_b = to_map(df_b)
    map_p = to_map(df_p)
    map_d = to_map(df_d)

    presentes = set()
    for df in (df_b, df_p, df_d):
        if df is not None and not df.empty:
            presentes |= set([c for c in df.columns if c in HEADERS_VIZ])
    headers_vis = [h for h in HEADERS_VIZ if h in presentes] or HEADERS_VIZ[:]

    dados_b: List[List[str]] = []
    dados_p: List[List[str]] = []
    dados_d: List[List[str]] = []

    for dstr in datas_mes:
        try:
            dkey = pd.to_datetime(dstr, dayfirst=True, errors="coerce").floor("D")
        except Exception:
            dkey = None

        # --- Boletim
        row_b = map_b.get(dkey, None)
        if row_b is not None:
            linha_b = [dstr, (rotalog_map or {}).get(dkey, "?")]
            if "Boletim" in (df_b.columns if df_b is not None else []):
                bol_val = row_b.get("Boletim", "")
                if pd.isna(bol_val) or not str(bol_val).strip():
                    bol_val = (bol_map or {}).get(dkey, "")
            else:
                bol_val = (bol_map or {}).get(dkey, "")
            linha_b.append("" if pd.isna(bol_val) else str(bol_val))
            linha_b += _row_as_list(row_b, headers_vis)
        else:
            linha_b = [dstr, (rotalog_map or {}).get(dkey, "?")]
            bol_val = (bol_map or {}).get(dkey, "") if bol_map else ""
            linha_b.append(bol_val or "")
            linha_b += [""] * len(headers_vis)
        dados_b.append(linha_b)

        # --- Ponto
        row_p = map_p.get(dkey, None)
        if row_p is not None:
            linha_p = [dstr] + _row_as_list(row_p, headers_vis)
        else:
            linha_p = [dstr] + [""] * len(headers_vis)
        dados_p.append(linha_p)

        # --- Diferença
        row_d = map_d.get(dkey, None)
        if row_d is not None:
            linha_d = [dstr] + _row_as_list(row_d, headers_vis)
        else:
            linha_d = [dstr] + [""] * len(headers_vis)
        dados_d.append(linha_d)

    return dados_b, dados_p, dados_d, headers_vis


def dfs_sem_ponto(
    di_date,
    df_date,
    headers_viz: Iterable[str],
    df_b_f: pd.DataFrame | None = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if df_b_f is not None and not df_b_f.empty and "Data" in df_b_f.columns:
        base_datas = df_b_f[["Data"]].copy()
    else:
        base = pd.date_range(pd.Timestamp(di_date), pd.Timestamp(df_date), freq="D")
        base_datas = pd.DataFrame({"Data": base})
    df_p_f = base_datas.copy()
    for h in headers_viz:
        df_p_f[h] = None

    if df_b_f is not None and not df_b_f.empty:
        available = [h for h in headers_viz if h in df_b_f.columns]
        df_d = df_b_f[["Data"] + available].copy()
        for h in headers_viz:
            if h not in df_d.columns:
                df_d[h] = 0.0
            else:
                df_d[h] = pd.to_numeric(df_d[h], errors="coerce").fillna(0.0)
    else:
        df_d = base_datas.copy()
        for h in headers_viz:
            df_d[h] = 0.0

    return df_p_f, df_d


def montar_triplet_comparacao(
    dados_df: pd.DataFrame,
    df_ponto: pd.DataFrame,
    df_relacao: pd.DataFrame,
    funcionario: str,
    data_ini,
    data_fim,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str | None, set, bool]:
    try:
        di_date = pd.Timestamp(data_ini).date()
    except Exception:
        di_date = data_ini if hasattr(data_ini, "year") else None
    try:
        df_date = pd.Timestamp(data_fim).date()
    except Exception:
        df_date = data_fim if hasattr(data_fim, "year") else None

    # Filtrar Boletim
    df_b_base = dados_df[
        (dados_df["Funcionário"] == funcionario)
        & (dados_df["DATA"].dt.date >= di_date)
        & (dados_df["DATA"].dt.date <= df_date)
    ].copy()

    if df_b_base.empty:
        return (
            pd.DataFrame(columns=["Data", "Boletim"] + HEADERS_VIZ),
            pd.DataFrame(columns=["Data"] + HEADERS_VIZ),
            pd.DataFrame(columns=["Data"] + HEADERS_VIZ),
            None,
            set(),
            True,
        )

    # Metadados
    registro = None
    if "Registro" in df_b_base.columns:
        regs = df_b_base["Registro"].dropna().astype(str).str.strip()
        regs = regs[regs != ""]
        if not regs.empty:
            registro = regs.iloc[0]

    boletins_set: set = set()
    if "BOLETIM" in df_b_base.columns:
        bol = (
            df_b_base["BOLETIM"]
            .dropna().astype(str).str.strip()
            .str.replace(r"\.0+$", "", regex=True)
        )
        boletins_set = {b for b in bol.tolist() if b}

    df_b_norm = preparar_df_boletim_para_comparacao(df_b_base)
    df_b = groupby_sum_by_date(
        df_b_norm.rename(columns={"DATA": "Data"}) if "DATA" in df_b_norm.columns else df_b_norm,
        "Data",
    )
    
    df_b_f = df_b.rename(
        columns={k: v for k, v in MAP_BOL.items() if k in df_b.columns}
    ).copy()
    if "Data" in df_b_f.columns:
        df_b_f["Data"] = pd.to_datetime(df_b_f["Data"], errors="coerce").dt.floor("D")

    # Filtro Ponto
    sem_ponto = False
    if df_ponto is None or df_ponto.empty:
        sem_ponto = True
        df_p_f, df_d = dfs_sem_ponto(di_date, df_date, HEADERS_VIZ, df_b_f)
    else:
        df_ponto_sel, _, _ = resolver_base_ponto(
            df_ponto, df_relacao, funcionario, data_ini, data_fim, corte_similaridade=0.75
        )
        if df_ponto_sel is None or df_ponto_sel.empty:
            sem_ponto = True
            df_p_f, df_d = dfs_sem_ponto(di_date, df_date, HEADERS_VIZ, df_b_f)
        else:
            df_p = preparar_df_ponto_para_comparacao(df_ponto_sel, data_ini, data_fim)
            inv_map_pto = {v: k for k, v in MAP_PTO.items()}
            df_p_f = df_p.rename(
                columns={k: inv_map_pto[k] for k in df_p.columns if k in inv_map_pto}
            ).copy()
            if "Data" in df_p_f.columns:
                df_p_f["Data"] = pd.to_datetime(df_p_f["Data"], errors="coerce").dt.floor("D")

            df_m = pd.merge(df_b_f, df_p_f, on="Data", how="outer", suffixes=("_B", "_P")).sort_values("Data")
            for h in HEADERS_VIZ:
                if f"{h}_B" not in df_m.columns: df_m[f"{h}_B"] = 0.0
                if f"{h}_P" not in df_m.columns: df_m[f"{h}_P"] = 0.0
                df_m[f"{h}_B"] = pd.to_numeric(df_m[f"{h}_B"], errors="coerce").fillna(0.0)
                df_m[f"{h}_P"] = pd.to_numeric(df_m[f"{h}_P"], errors="coerce").fillna(0.0)
                df_m[h] = df_m[f"{h}_B"] - df_m[f"{h}_P"]
            df_d = df_m[["Data"] + [h for h in HEADERS_VIZ if h in df_m.columns]].copy()

    for _h in HEADERS_VIZ:
        if _h in df_d.columns:
            s = pd.to_numeric(df_d[_h], errors="coerce").round(2)
            s = s.where(s.abs() >= 5e-4, 0.0)
            df_d[_h] = s

    keep_b = (["Data"] + (["Boletim"] if "Boletim" in df_b_f.columns else [])
              + [h for h in HEADERS_VIZ if h in df_b_f.columns])
    df_b_f = df_b_f[keep_b].copy() if "Data" in df_b_f.columns else pd.DataFrame(
        columns=["Data", "Boletim"] + HEADERS_VIZ
    )

    keep_p = ["Data"] + [h for h in HEADERS_VIZ if h in df_p_f.columns]
    df_p_f = df_p_f[keep_p].copy() if "Data" in df_p_f.columns else pd.DataFrame(
        columns=["Data"] + HEADERS_VIZ
    )

    keep_d = ["Data"] + [h for h in HEADERS_VIZ if h in df_d.columns]
    df_d = df_d[keep_d].copy() if "Data" in df_d.columns else pd.DataFrame(
        columns=["Data"] + HEADERS_VIZ
    )

    return df_b_f, df_p_f, df_d, registro, boletins_set, sem_ponto
