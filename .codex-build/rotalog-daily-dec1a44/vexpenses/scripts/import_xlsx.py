# Finalidade: executar importação da planilha Excel via linha de comando.
from pathlib import Path
import sys

from app import models  # noqa: F401
from app.core.database import Base, SessionLocal, engine
from app.services.import_service import ImportService


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python scripts/import_xlsx.py caminho_do_arquivo.xlsx")
        return 1

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"Arquivo não encontrado: {file_path}")
        return 1

    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        service = ImportService(db)
        batch = service.import_xlsx(file_path)
        print("Importação concluída com sucesso.")
        print(f"Lote: {batch.id}")
        print(f"Arquivo: {batch.source_filename}")
        print(f"Linhas: {batch.total_rows}")
        print(f"Inseridas: {batch.inserted_count}")
        print(f"Atualizadas: {batch.updated_count}")
        print(f"Sem alteração: {batch.unchanged_count}")
        print(f"Erros: {batch.error_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
