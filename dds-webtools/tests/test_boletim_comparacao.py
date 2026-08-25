import pandas as pd

from boletim_x_ponto.services.comparacao import (
    _limpa_boletim,
    dfs_sem_ponto,
    montar_tres_grids,
)
from boletim_x_ponto.services.constantes import HEADERS_VIZ
from boletim_x_ponto.services.rotalog_service import mapear_presenca_funcionario_por_data


def test_numero_boletim_remove_zeros_iniciais():
    assert _limpa_boletim("00000123") == "123"
    assert _limpa_boletim("00000") == "0"


def test_grid_usa_mapa_quando_boletim_agregado_esta_vazio():
    day = pd.Timestamp("2026-07-01")
    bulletin = pd.DataFrame([
        {"Data": day, "Boletim": "", "Horas Normais": 8.0}
    ])
    rows, _, _, _ = montar_tres_grids(
        ["01/07/2026"],
        bulletin,
        pd.DataFrame(),
        pd.DataFrame(),
        bol_map={day: "42341"},
    )
    assert rows[0][2] == "42341"


def test_sem_ponto_diferenca_repete_boletim():
    day = pd.Timestamp("2026-07-01")
    bulletin = pd.DataFrame([{
        "Data": day,
        "Horas Normais": 8.0,
        "Extra 50%D": 2.0,
    }])
    _, difference = dfs_sem_ponto(
        day, day, HEADERS_VIZ, df_b_f=bulletin
    )
    assert difference.iloc[0]["Horas Normais"] == 8.0
    assert difference.iloc[0]["Extra 50%D"] == 2.0


def test_julho_preserva_trinta_e_um_dias_sem_linha_embutida_de_totais():
    dates = [f"{day:02d}/07/2026" for day in range(1, 32)]
    last_day = pd.DataFrame([
        {"Data": pd.Timestamp("2026-07-31"), "Horas Normais": 8.0}
    ])
    bulletin, point, difference, _ = montar_tres_grids(
        dates, last_day, last_day, last_day
    )
    assert len(bulletin) == len(point) == len(difference) == 31
    assert bulletin[-1][0] == "31/07/2026"


def test_rotalog_remove_matricula_e_marca_presenca_por_dia():
    rotalog = pd.DataFrame([
        {
            "Data": pd.Timestamp("2026-07-01"),
            "Eletricista 1": "12345 - JOÃO DA SILVA",
            "Eletricista 2": "",
        },
        {
            "Data": pd.Timestamp("2026-07-02"),
            "Eletricista 1": "MARIA",
            "Eletricista 2": "",
        },
    ])
    result = mapear_presenca_funcionario_por_data(rotalog, "JOAO DA SILVA")
    assert result[pd.Timestamp("2026-07-01")] == "✓"
    assert result[pd.Timestamp("2026-07-02")] == "✕"
