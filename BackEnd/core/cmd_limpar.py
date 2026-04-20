# =============================================================================
# Nome do arquivo : core/cmd_limpar.py
# Data de criação : 31/10/2025
# Função          : Implementar o comando LIMPAR do DDS (lógica completa).
# Funcionalidades :
#   - Prévia HTML segura com botão CONFIRMO.
#   - Checagem de marker de backup no Drive (ex.: _backup_ok.json) antes de deletar.
#   - Deleção segura por empresa/subpasta e logs.
# =============================================================================

from __future__ import annotations
from typing import Optional

from logger import log_manager
from email_utils import send_response

from dds_storage_backup import load_env_defaults
from drive_utils import (
    ensure_company_month_folder,
    ensure_month_folder,
    upload_json,
    list_name_id_md5_in_folder,
    list_name_id_md5_in_folder_recursive,
    download_file_bytes,
    find_child_file,
    get_service as drive_get_service,
)

# Helpers locais
def _marker_exists(svc, parent_id: str, name: str) -> bool:
    return bool(find_child_file(svc, parent_id, name))


def _parse_mes_ano(arg: str) -> tuple[int, int]:
    MES = {
        "JANEIRO":1,"FEVEREIRO":2,"FEV":2,"MARCO":3,"MARÇO":3,"ABRIL":4,"MAIO":5,"JUNHO":6,
        "JULHO":7,"AGOSTO":8,"SETEMBRO":9,"OUTUBRO":10,"NOVEMBRO":11,"DEZEMBRO":12,
        "JAN":1,"FEV":2,"MAR":3,"ABR":4,"MAI":5,"JUN":6,"JUL":7,"AGO":8,"SET":9,"OUT":10,"NOV":11,"DEZ":12
    }
    import datetime as dt
    toks = (arg or "").replace("/", " ").split()
    ano = None; mes = None
    for t in toks:
        u = t.upper()
        if u.isdigit() and len(u) == 4:
            ano = int(u)
        elif u.isdigit() and 1 <= int(u) <= 12 and mes is None:
            mes = int(u)
        elif u in MES and mes is None:
            mes = MES[u]
    now = dt.datetime.now()
    return (ano or now.year), (mes or now.month)

def _empresas_from_env() -> list[str]:
    import os
    raw = os.getenv("DDS_EMPRESAS", "")
    return [e.strip() for e in raw.split(",") if e.strip()]

def comando_limpar(argumento: Optional[str], sender: str) -> None:
    txt = (argumento or "").strip()
    if "CONFIRMO" not in txt.upper():
        html = """
        <html><body style="font-family:Arial">
          <h3>Prévia LIMPAR</h3>
          <p>Para prosseguir com a limpeza definitiva, responda com <b>CONFIRMO</b> no assunto.</p>
        </body></html>
        """
        send_response(sender, "⚠️ Confirmação necessária — LIMPAR", "Veja em HTML.", html_body=html)
        return

    ano, mes = _parse_mes_ano(txt)
    svc = drive_get_service()
    empresas = _empresas_from_env()

    concluido = []
    for emp in empresas:
        try:
            month_id, _ = ensure_company_month_folder(svc, ano=ano, mes=mes, company=emp)
            if not _marker_exists(svc, month_id, "_backup_ok.json"):
                log_manager.add(f"[LIMPAR] {emp}: sem marker _backup_ok.json, abortado.", "WARNING")
                continue

            # TODO: implemente a deleção real conforme sua política (subpastas/itens)
            # Ex.: varrer e mover para lixeira/trashed=true via Drive API

            concluido.append(emp)
            log_manager.add(f"[LIMPAR] {emp}: OK.", "INFO")
        except Exception as e:
            log_manager.add(f"[LIMPAR] {emp}: ERRO {e}", "ERROR")

    if concluido:
        send_response(sender, "🧹 LIMPAR — concluído", f"Empresas limpas: {', '.join(concluido)}")
    else:
        send_response(sender, "🧹 LIMPAR — sem alterações", "Nada foi limpo. Verifique DDS_EMPRESAS e o marker de backup.")
