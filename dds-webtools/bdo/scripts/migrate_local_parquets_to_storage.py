"""Migra as bases Parquet locais para partições versionadas no Storage.

O script é idempotente: uma nova execução classifica registros iguais como
ignorados e não publica novas versões desnecessárias.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Callable

import pandas as pd

from bdo.services.parquet_repository import (
    ImportStats,
    ParquetStorageRepository,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def _load_relation_contract() -> pd.DataFrame:
    path = DATA_DIR / "relacao_contrato_boletim.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, sep=None, engine="python", dtype=str)
    df = df.rename(columns={
        "contrato": "Contrato",
        "boletim": "Boletim",
        "data_medicao": "Data_Medicao",
    })
    dates = pd.to_datetime(df.get("Data_Medicao"), errors="coerce", dayfirst=True)
    df["Ano"] = dates.dt.year.astype("Int64")
    df["Mes"] = dates.dt.month.astype("Int64")
    return df.dropna(subset=["Contrato", "Boletim", "Ano", "Mes"])


def _sources() -> list[tuple[str, Path, Callable[[], pd.DataFrame] | None]]:
    return [
        ("boletim", DATA_DIR / "RegistroBoletim.parquet", None),
        ("ponto", DATA_DIR / "RegistroPonto.parquet", None),
        ("boletim_var", DATA_DIR / "boletim_var.parquet", None),
        ("relacao_nomes", DATA_DIR / "relacao_nomes.parquet", None),
        ("contrato_boletim", DATA_DIR / "relacao_contrato_boletim.csv", _load_relation_contract),
    ]


def migrate(repository: ParquetStorageRepository, dry_run: bool = False) -> dict:
    result: dict[str, dict] = {}
    for dataset, path, loader in _sources():
        if not path.exists():
            result[dataset] = {"status": "ausente"}
            continue
        df = loader() if loader else pd.read_parquet(path)
        if dry_run:
            stats = ImportStats(processed=len(df), new=len(df))
        else:
            stats = repository.upsert(dataset, df)
        result[dataset] = {
            "status": "simulado" if dry_run else "migrado",
            **stats.to_dict(),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--local-dir",
        help="Usa uma pasta local no lugar do Firebase Storage.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.local_dir:
        os.environ["BOLETIM_X_PONTO_LOCAL_STORAGE_DIR"] = args.local_dir

    repository = ParquetStorageRepository()
    result = migrate(repository, dry_run=args.dry_run)
    print("Migração Parquet")
    print("=" * 60)
    for dataset, stats in result.items():
        print(
            f"{dataset:22} {stats.get('status'):10} "
            f"processados={stats.get('processed', 0):7} "
            f"novos={stats.get('new', 0):7} "
            f"atualizados={stats.get('updated', 0):7} "
            f"ignorados={stats.get('ignored', 0):7}"
        )
    if not args.dry_run:
        print(f"Revisão publicada: {repository.revision()}")


if __name__ == "__main__":
    main()
