"""
============================================================
FILE: training_management/__init__.py
FUNCTION: Pacote para centralizar operações de gestão de treinamentos.
============================================================
"""

from .deletion import handle_training_delete_request

__all__ = ["handle_training_delete_request"]