from __future__ import annotations

import pandas as pd

from boletim_x_ponto.services.parquet_repository import (
    LocalObjectStore,
    ParquetStorageRepository,
)


def make_repository(tmp_path):
    return ParquetStorageRepository(
        LocalObjectStore(tmp_path),
        prefix="tests/boletim_x_ponto",
        manifest_ttl_seconds=0,
    )


def test_particiona_le_e_publica_manifesto(tmp_path):
    repository = make_repository(tmp_path)
    source = pd.DataFrame([
        {
            "chave_unica": "B1__2026-01-31__ANA",
            "DATA": pd.Timestamp("2026-01-31"),
            "Funcionário": "ANA",
            "Contrato": "10",
            "HORA NORMAL": 8.0,
        },
        {
            "chave_unica": "B2__2026-02-01__ANA",
            "DATA": pd.Timestamp("2026-02-01"),
            "Funcionário": "ANA",
            "Contrato": "10",
            "HORA NORMAL": 7.0,
        },
    ])

    stats = repository.upsert("boletim", source)

    assert stats.processed == 2
    assert stats.new == 2
    assert stats.partitions_written == 2
    manifest, _ = repository.get_manifest(force=True)
    parts = manifest["datasets"]["boletim"]["partitions"]
    assert sorted(parts) == ["2026-01", "2026-02"]
    january = repository.read("boletim", "2026-01-01", "2026-01-31")
    assert january["chave_unica"].tolist() == ["B1__2026-01-31__ANA"]
    assert repository.summary("boletim")["rows"] == 2
    assert repository.summary("boletim")["contracts"] == ["10"]


def test_upsert_classifica_novos_atualizados_e_ignorados(tmp_path):
    repository = make_repository(tmp_path)
    initial = pd.DataFrame([
        {"chave_unica": "A", "Data": pd.Timestamp("2026-07-01"), "Nome": "ANA", "Total Normais": 8.0},
        {"chave_unica": "B", "Data": pd.Timestamp("2026-07-02"), "Nome": "BIA", "Total Normais": 7.0},
    ])
    repository.upsert("ponto", initial)

    incoming = pd.DataFrame([
        {"chave_unica": "A", "Data": pd.Timestamp("2026-07-01"), "Nome": "ANA", "Total Normais": 8.0},
        {"chave_unica": "B", "Data": pd.Timestamp("2026-07-02"), "Nome": "BIA", "Total Normais": 9.0},
        {"chave_unica": "C", "Data": pd.Timestamp("2026-07-03"), "Nome": "CAIO", "Total Normais": 6.0},
    ])
    stats = repository.upsert("ponto", incoming)

    assert stats.processed == 3
    assert stats.new == 1
    assert stats.updated == 1
    assert stats.ignored == 1
    result = repository.read("ponto", "2026-07-01", "2026-07-31")
    values = result.set_index("chave_unica")["Total Normais"].to_dict()
    assert values == {"A": 8.0, "B": 9.0, "C": 6.0}


def test_dataset_unico_relacao_nomes(tmp_path):
    repository = make_repository(tmp_path)
    first = pd.DataFrame([{
        "Nome_Boletim": "ANA",
        "Nome_Ponto_Mapeado": "ANA SILVA",
        "CPF_Ponto": "1",
        "PIS_Ponto": "",
    }])
    repository.upsert("relacao_nomes", first)
    second = first.copy()
    second.loc[0, "CPF_Ponto"] = "2"

    stats = repository.upsert("relacao_nomes", second)

    assert stats.updated == 1
    assert repository.read("relacao_nomes").iloc[0]["CPF_Ponto"] == "2"
