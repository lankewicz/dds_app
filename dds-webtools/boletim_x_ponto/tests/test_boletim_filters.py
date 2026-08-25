from __future__ import annotations

import pandas as pd

from boletim_x_ponto.services.boletim_service import BoletimXPontoService


class FakeRepository:
    def __init__(self):
        self.last_read = None

    def summary(self, dataset):
        assert dataset == "boletim"
        return {"contracts": ["ANTIGO", "ATUAL"]}

    def read(self, dataset, data_ini=None, data_fim=None):
        if dataset == "relacao_nomes":
            return pd.DataFrame()
        self.last_read = (dataset, data_ini, data_fim)
        return pd.DataFrame({
            "Contrato": [" ATUAL ", "ATUAL", None, "", "OUTRO"]
        })


def test_lista_contratos_globais_quando_periodo_nao_e_informado():
    repository = FakeRepository()
    service = BoletimXPontoService(repository=repository)

    assert service.get_contracts() == ["ANTIGO", "ATUAL"]
    assert repository.last_read is None


def test_lista_somente_contratos_lidos_no_periodo():
    repository = FakeRepository()
    service = BoletimXPontoService(repository=repository)

    contracts = service.get_contracts("2026-07-01", "2026-07-31")

    assert contracts == ["ATUAL", "OUTRO"]
    assert repository.last_read == (
        "boletim",
        "2026-07-01",
        "2026-07-31",
    )
