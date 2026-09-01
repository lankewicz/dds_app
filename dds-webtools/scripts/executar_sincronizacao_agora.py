"""
Script para disparar a sincronização do Rotalog imediatamente
e abrir/manter fechados os turnos com base na atividade real do dia.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, root_dir)
sys.path.insert(0, os.path.join(root_dir, "monitor"))
load_dotenv(os.path.join(root_dir, ".env"))

from bdo.services.rotalog_sync_task import _executar_sincronizacao_rotalog


def rodar_sync_agora():
    print("Iniciando sincronização inteligente do Rotalog...")
    res = _executar_sincronizacao_rotalog(empresa="ChicoEletro", forcar=True)
    print(f"Sincronização concluída: {res}")


if __name__ == "__main__":
    rodar_sync_agora()
