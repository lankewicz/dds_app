"""Migra, somente por leitura, os caches ROTALOG existentes do desktop."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from boletim_x_ponto.services.parquet_repository import ParquetStorageRepository


def load_equipes(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    raw = df["Data Referência - Turno"].astype(str).str.extract(
        r"(\d{2}/\d{2}/\d{4})", expand=False
    )
    df["Data"] = pd.to_datetime(
        raw, format="%d/%m/%Y", errors="coerce"
    )
    return df[df["Data"].notna()].copy()


def load_eventos(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["Data"] = pd.to_datetime(
        df["Inicio Deslo"], errors="coerce", dayfirst=True
    ).dt.floor("D")
    return df[df["Data"].notna()].copy()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("desktop_data_dir", type=Path)
    args = parser.parse_args()

    sources = {
        "rotalog_equipes": (
            args.desktop_data_dir / "RegistroRotalog_Equipes.parquet",
            load_equipes,
        ),
        "rotalog_eventos": (
            args.desktop_data_dir / "RegistroRotalog_Eventos.parquet",
            load_eventos,
        ),
    }
    repository = ParquetStorageRepository()
    for dataset, (path, loader) in sources.items():
        if not path.exists():
            print(f"{dataset}: ausente")
            continue
        stats = repository.upsert(dataset, loader(path))
        print(
            f"{dataset}: processados={stats.processed}, novos={stats.new}, "
            f"atualizados={stats.updated}, ignorados={stats.ignored}"
        )


if __name__ == "__main__":
    main()
