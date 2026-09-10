"""
============================================================
FILE: training_management/deletion.py
FUNCTION: Centraliza a exclusão de treinamentos DDS (online/normal),
          removendo a lógica de exclusão do admin_routes.py.
============================================================
"""

from __future__ import annotations

import re

from flask import current_app, jsonify, request

from storage_normal_package import delete_normal_package_and_update_lista_json
from storage_online_package import delete_online_package_and_update_lista_json


def handle_training_delete_request():
    """
    Exclui uma pasta de treinamento do Storage e remove suas entradas do
    DDSv2/lista.json.

    Aceita JSON ou form-data:
      - type: "online" | "normal"
      - folderId: "YYYY-MM-DD - ... "
    """
    bucket = current_app.config.get("BUCKET_NAME")
    base_prefix = current_app.config.get("BASE_PREFIX")
    if not bucket:
        return jsonify({"ok": False, "error": "DDS_BUCKET_NAME não configurado."}), 400

    data = request.get_json(silent=True) or request.form or {}
    dds_type = (data.get("type") or data.get("ddsType") or "").strip().lower()
    folder_id = (data.get("folderId") or "").strip()

    if dds_type not in ("online", "normal"):
        return jsonify(
            {"ok": False, "error": "type inválido (use 'online' ou 'normal')."}
        ), 400

    if not folder_id:
        return jsonify({"ok": False, "error": "folderId é obrigatório."}), 400

    # Segurança: permitir exclusão somente dentro do padrão esperado
    # YYYY-MM-DD - NOME DO TREINAMENTO
    if not re.match(r"^\d{4}-\d{2}-\d{2}\s-\s", folder_id):
        return jsonify({"ok": False, "error": "folderId inválido."}), 400

    try:
        if dds_type == "online":
            result = delete_online_package_and_update_lista_json(
                bucket_name=bucket,
                base_prefix=base_prefix,
                folder_id=folder_id,
            )
        else:
            result = delete_normal_package_and_update_lista_json(
                bucket_name=bucket,
                base_prefix=base_prefix,
                folder_id=folder_id,
            )

        return jsonify({"ok": True, "result": result})
    except Exception as e:
        current_app.logger.exception("Erro ao excluir pacote (%s): %s", dds_type, e)
        return jsonify({"ok": False, "error": f"Erro interno ao excluir: {e}"}), 500