# Finalidade: inicializar rapidamente o banco SQLite local para testes.
from app import models  # noqa: F401
from app.core.database import Base, engine


def main() -> None:
    Base.metadata.create_all(bind=engine)
    print("Banco inicializado com sucesso.")


if __name__ == "__main__":
    main()
