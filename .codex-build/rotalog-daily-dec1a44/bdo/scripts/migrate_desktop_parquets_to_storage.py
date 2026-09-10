"""Migra a base desktop atual por leitura, sem alterar seus arquivos."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from bdo.services.parquet_repository import ParquetStorageRepository


FILES = {
    "boletim": "RegistroBoletim.parquet",
    "ponto": "RegistroPonto.parquet",
    "boletim_var": "boletim_var.parquet",
    "relacao_nomes": "relacao_nomes.parquet",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "desktop_data_dir",
        type=Path,
        help="Pasta data do desktop, usada somente para leitura.",
    )
    args = parser.parse_args()
    source = args.desktop_data_dir.resolve()
    repository = ParquetStorageRepository()

    for dataset, filename in FILES.items():
        path = source / filename
        if not path.exists():
            print(f"{dataset}: ausente")
            continue
        df = pd.read_parquet(path)
        if dataset == "boletim" and "chave_unica" not in df.columns:
            dates = pd.to_datetime(df["DATA"], errors="coerce").dt.strftime(
                "%Y-%m-%d"
            )
            df["chave_unica"] = (
                df["BOLETIM"].fillna("").astype(str).str.strip()
                + "__" + dates.fillna("") + "__"
                + df["Funcionário"].fillna("").astype(str).str.strip().str.upper()
            )
        if dataset == "ponto" and "chave_unica" not in df.columns:
            identity = df["CPF"].fillna("").astype(str).str.strip()
            identity = identity.where(
                identity != "", df["PIS"].fillna("").astype(str).str.strip()
            )
            dates = pd.to_datetime(df["Data"], errors="coerce").dt.strftime("%Y-%m-%d")
            df["chave_unica"] = identity + "__" + dates.fillna("")
        stats = repository.upsert(dataset, df)
        print(
            f"{dataset}: processados={stats.processed}, novos={stats.new}, "
            f"atualizados={stats.updated}, ignorados={stats.ignored}"
        )

    relation_path = source / "relacao_contrato_boletim.csv"
    if relation_path.exists():
        relation = pd.read_csv(relation_path, sep=None, engine="python", dtype=str)
        relation = relation.rename(columns={
            "contrato": "Contrato",
            "boletim": "Boletim",
            "data_medicao": "Data_Medicao",
        })
        dates = pd.to_datetime(
            relation["Data_Medicao"], errors="coerce", dayfirst=True
        )
        relation["Ano"] = dates.dt.year.astype("Int64")
        relation["Mes"] = dates.dt.month.astype("Int64")
        relation = relation.dropna(
            subset=["Contrato", "Boletim", "Ano", "Mes"]
        )
        stats = repository.upsert("contrato_boletim", relation)
        print(
            f"contrato_boletim: processados={stats.processed}, "
            f"novos={stats.new}, atualizados={stats.updated}, "
            f"ignorados={stats.ignored}"
        )

    print(f"Revisão publicada: {repository.revision()}")


if __name__ == "__main__":
    main()
