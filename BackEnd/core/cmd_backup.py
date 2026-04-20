# =============================================================================
# core/cmd_backup.py
# -----------------------------------------------------------------------------
# BACKUP DDS:
#   - Lê fotos do Firebase Storage (DDS_Fotos/<Empresa>/Fotos|Thumb/...).
#   - Lê metadados do Firestore (coleção DDS) para o mês/empresa.
#   - Copia as fotos do Storage para o Google Drive.
#   - Gera _index_fotos.json com:
#       * dados do Storage
#       * dados do Firestore (db)
#       * localização da foto no Drive (drive_id, drive_path)
#   - Cria/atualiza _backup_ok.json na pasta da empresa/mês.
#   - Envia e-mail com resumo.
# =============================================================================

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote
import base64
import binascii
import datetime as dt
import os

import firebase_admin
from firebase_admin import firestore

from logger import log_manager
from email_utils import send_response
from tui_progress import progress_bus

from dds_storage_backup import load_env_defaults, StorageClient, should_take
from drive_utils import (
    ensure_company_month_folder,
    upload_json,
    upload_or_update_bytes_at_path,
    get_service as drive_get_service,
)

STORAGE_PREFIX = "DDS_Fotos"
_firestore_client: firestore.Client | None = None


# ============================================================================
# Helpers de data / parsing de argumentos
# ============================================================================

def _parse_mes_ano(arg: str) -> tuple[int, int]:
    """Interpreta argumentos como 'OUTUBRO', '2025-10', '10/2025'."""
    MES = {
        "JANEIRO": 1, "FEVEREIRO": 2, "FEV": 2, "MARCO": 3, "MARÇO": 3, "ABRIL": 4,
        "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9,
        "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
        "JAN": 1, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
        "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12,
    }
    toks = (arg or "").replace("/", " ").split()
    ano = mes = None
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


def _parse_subs(arg: str) -> List[str]:
    """Extrai subs=Fotos,Thumb do argumento. Default: ['Fotos', 'Thumb']."""
    for part in (arg or "").split():
        if part.lower().startswith("subs="):
            return [s.strip() for s in part.split("=", 1)[1].split(",") if s.strip()]
    return ["Fotos", "Thumb"]


def _matches_month_by_filename(filename: str, ano: int, mes: int) -> bool:
    """
    Verifica se o arquivo pertence ao mês/ano informados usando
    a data inicial do nome: 'YYYY-MM-DD - ASSUNTO_...jpg'.
    """
    try:
        prefix = filename.split(" - ", 1)[0]
        d = dt.datetime.strptime(prefix, "%Y-%m-%d")
        return d.year == ano and d.month == mes
    except Exception:
        return False


# ============================================================================
# Helpers Firebase / Firestore
# ============================================================================

def _get_firestore_client() -> firestore.Client:
    """Retorna cliente do Firestore inicializado via firebase_admin."""
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client

    # load_env_defaults já aplica GOOGLE_APPLICATION_CREDENTIALS,
    # mas garantimos que exista um app.
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    _firestore_client = firestore.client()
    return _firestore_client


def _url_to_gcs_path(url: str) -> Optional[str]:
    """
    Converte fotoUrl/thumbUrl para caminho GCS, ex:
    https://.../o/DDS_Fotos%2FChicoEletro%2FFotos%2F...jpg?alt=media&token=...
    -> DDS_Fotos/ChicoEletro/Fotos/...jpg
    """
    if not url:
        return None
    if "/o/" not in url:
        return None
    after = url.split("/o/", 1)[1]
    path_enc = after.split("?", 1)[0]
    return unquote(path_enc)


def _simplify_firestore_value(value: Any) -> Any:
    """Converte tipos do Firestore para algo serializável em JSON."""
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_simplify_firestore_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _simplify_firestore_value(v) for k, v in value.items()}
    return value


def _carregar_db_metadata(empresa: str, ano: int, mes: int) -> Dict[str, Dict[str, Any]]:
    """
    Lê os documentos do Firestore para o mês/empresa e devolve:
        gcs_path -> {campos do documento}
    Onde gcs_path é derivado de fotoUrl/thumbUrl (DDS_Fotos/Empresa/Fotos|Thumb/...).
    """
    try:
        db = _get_firestore_client()
    except Exception as e:
        log_manager.add(f"[BACKUP] Firestore indisponível: {e}", "ERROR")
        return {}

    col_name = os.getenv("FIRESTORE_COLLECTION", "DDS")
    col = db.collection(col_name)

    start = f"{ano}-{mes:02d}-01"
    end = f"{ano}-{mes:02d}-31"

    meta: Dict[str, Dict[str, Any]] = {}
    try:
        docs = col.where("headerDate", ">=", start).where("headerDate", "<=", end).stream()
    except Exception as e:
        log_manager.add(
            f"[BACKUP] Erro ao consultar Firestore ({col_name}) {ano}-{mes:02d}: {e}",
            "ERROR",
        )
        return {}

    for doc in docs:
        raw = doc.to_dict() or {}
        cleaned = {str(k): _simplify_firestore_value(v) for k, v in raw.items()}
        cleaned["_id"] = doc.id

        for field in ("fotoUrl", "thumbUrl"):
            url = raw.get(field)
            if not url:
                continue
            gcs_path = _url_to_gcs_path(url)
            if not gcs_path:
                continue
            if f"/{empresa}/" not in gcs_path:
                continue
            meta[gcs_path] = cleaned

    log_manager.add(
        f"[BACKUP] Firestore {col_name}: {empresa} {ano}-{mes:02d} -> {len(meta)} docs",
        "INFO",
    )
    return meta


# ============================================================================
# Helpers GCS / Drive
# ============================================================================

def _gcs_md5_to_hex(md5_b64: Optional[str]) -> Optional[str]:
    """Converte md5_hash (base64) do GCS para hex, igual ao Drive."""
    if not md5_b64:
        return None
    try:
        raw = base64.b64decode(md5_b64)
        return binascii.hexlify(raw).decode("ascii")
    except Exception:
        return None


def _descobrir_empresas_no_storage(env: dict) -> List[str]:
    """
    Descobre empresas olhando a estrutura:
        gs://<bucket>/DDS_Fotos/<Empresa>/...
    """
    bucket = (env.get("bucket") or os.getenv("GCS_BUCKET") or "").strip()
    prefix = env.get("prefix") or os.getenv("GCS_PREFIX") or STORAGE_PREFIX
    raiz = prefix.split("/", 1)[0].strip("/") or STORAGE_PREFIX

    empresas: set[str] = set()
    if not bucket:
        log_manager.add("[BACKUP] GCS_BUCKET não definido.", "ERROR")
        return []

    try:
        gcs = StorageClient(bucket)
        prefix_list = f"{raiz}/"
        log_manager.add(
            f"[BACKUP] Listando empresas em gs://{bucket}/{prefix_list}", "INFO"
        )
        for blob in gcs.list_blobs(prefix=prefix_list):
            # Ex.: DDS_Fotos/ChicoEletro/Fotos/...
            parts = (blob.name or "").split("/")
            if len(parts) >= 2 and parts[0] == raiz:
                emp = parts[1].strip()
                if emp and not emp.startswith("_"):
                    empresas.add(emp)
    except Exception as e:
        log_manager.add(f"[BACKUP] Erro ao acessar Storage: {e}", "ERROR")

    if not empresas:
        log_manager.add("[BACKUP] Nenhuma empresa detectada no Storage.", "WARN")
    else:
        log_manager.add(
            f"[BACKUP] Empresas detectadas no Storage: {', '.join(sorted(empresas))}",
            "INFO",
        )
    return sorted(empresas)

def _push_debug(debug_lines: List[str], msg: str, level: str = "INFO") -> None:
    """
    Adiciona a mensagem no vetor de debug (para o e-mail),
    imprime na tela (stdout) e também registra no log_manager.
    Útil para acompanhar o BACKUP em modo síncrono/CLI.
    """
    debug_lines.append(msg)
    # imprime no console quando rodar backup_debug.py
    try:
        print(msg, flush=True)
    except Exception:
        pass

    # registra no log do sistema (aparece na TUI)
    try:
        log_manager.add(msg, level)
    except Exception:
        pass



# ============================================================================
# Função principal (comando BACKUP)
# ============================================================================

def comando_backup(argumento: Optional[str], sender: str) -> None:
    """
    Executa o BACKUP DDS:

    - Descobre empresas no Firebase Storage (DDS_Fotos/<Empresa>/...).
    - Para cada empresa:
        * Filtra blobs por subpastas (Fotos, Thumb) E pelo mês/ano pedidos.
        * Lê dados correlatos do Firestore (coleção DDS).
        * Copia as fotos do Storage para o Drive (empresa/AAAA-MM/Fotos|Thumb).
        * Gera _index_fotos.json com Storage + Firestore + Drive.
        * Cria/atualiza _backup_ok.json sinalizando sucesso.
    - Envia e-mail com resumo.
    """
    # Ambiente (.env + GOOGLE_APPLICATION_CREDENTIALS)
    env = load_env_defaults()
    bucket = env.get("bucket") or os.getenv("GCS_BUCKET")

    # Serviço de Drive
    svc = drive_get_service()

    ano, mes = _parse_mes_ano(argumento or "")
    subs = _parse_subs(argumento or "")
    month_str = f"{ano}-{mes:02d}"

    debug_lines: List[str] = []
    _push_debug(debug_lines, f"Bucket: {bucket}")
    _push_debug(debug_lines, f"Prefix: {env.get('prefix') or os.getenv('GCS_PREFIX') or STORAGE_PREFIX}")
    _push_debug(debug_lines, f"Mês: {month_str}")
    _push_debug(debug_lines, f"Subs: {', '.join(subs) if subs else '(todas)'}")

    empresas = _descobrir_empresas_no_storage(env)
    _push_debug(debug_lines, f"Empresas detectadas: {', '.join(empresas) or '(nenhuma)'}")


    if not empresas:
        corpo = (
            "Nenhuma empresa detectada no Firebase Storage (DDS_Fotos/<Empresa>/...).\n\n"
            "DEBUG:\n" + "\n".join(debug_lines[:200])
        )
        send_response(sender, "⚠️ BACKUP sem alterações", corpo)
        return

    try:
        progress_bus.start(
            op="backup",
            phase="iniciando",
            month=month_str,
            total=len(empresas),
            bytes_total=0,
            company="ALL",
        )
    except Exception:
        pass

    ok_empresas: List[str] = []

    for i, emp in enumerate(empresas, 1):
        try:
            # Pasta empresa/AAAA-MM no Drive
            month_id, _ = ensure_company_month_folder(svc, year=ano, month=mes, company=emp)

            # Client do Storage para esta empresa
            gcs = StorageClient(bucket)
            prefix_empresa = f"{STORAGE_PREFIX}/{emp}/"

            blobs = list(gcs.list_blobs(prefix=prefix_empresa))
            total_blobs = len(blobs)

            arquivos = []
            for b in blobs:
                if not should_take(b, subs):
                    continue
                fname = Path(b.name).name
                if not _matches_month_by_filename(fname, ano, mes):
                    continue
                arquivos.append(b)

            _push_debug(
                debug_lines,
                f"Empresa {emp}: total_blobs={total_blobs}, "
                f"filtrados={len(arquivos)}, prefix='{prefix_empresa}'"
            )
            for blob in arquivos[:3]:
                _push_debug(debug_lines, f"  - {blob.name}")


            # Metadados do Firestore para esta empresa/mês
            meta_por_gcs = _carregar_db_metadata(emp, ano, mes)

            # Índice JSON desta empresa/mês
            index_json: Dict[str, Any] = {
                "generated_at": dt.datetime.utcnow().isoformat() + "Z",
                "company": emp,
                "month": month_str,
                "by_name": {},
            }

            # Copia cada arquivo + monta entrada no JSON
            for blob in arquivos:
                full_name = blob.name or ""
                parts = full_name.split("/")
                if len(parts) < 3 or parts[0] != STORAGE_PREFIX or parts[1] != emp:
                    continue

                kind = parts[2]                     # Fotos ou Thumb
                path_rel = "/".join(parts[2:])      # Fotos/arquivo.jpg
                filename = parts[-1]
                gcs_path = full_name
                md5_b64 = getattr(blob, "md5_hash", None)
                md5_hex = _gcs_md5_to_hex(md5_b64)

                # Baixa bytes do Storage
                try:
                    data_bytes = blob.download_as_bytes()
                except Exception as e_download:
                    log_manager.add(
                        f"[BACKUP] {emp}: erro ao baixar {gcs_path}: {e_download}",
                        "ERROR",
                    )
                    data_bytes = b""

                # Copia para o Drive (empresa/AAAA-MM/<kind>/arquivo.jpg)
                drive_id: Optional[str] = None
                action = "skipped"

                # Verifica se realmente baixou bytes do Storage
                if not data_bytes or len(data_bytes) == 0:
                    log_manager.add(f"[BACKUP] {emp}: blob vazio ou não baixado {gcs_path}", "WARN")
                else:
                    try:
                        drive_id, action = upload_or_update_bytes_at_path(
                            svc,
                            root_id=month_id,
                            path_parts=[kind],
                            file_name=filename,
                            data=data_bytes,
                            mimetype=blob.content_type or "image/jpeg",
                            gcs_md5_hex=md5_hex,
                            small_limit_mb=5,
                            app_properties={
                                "gcs_bucket": bucket or "",
                                "gcs_path": gcs_path,
                                "gcs_md5_b64": md5_b64 or "",
                                "empresa": emp,
                                "month": month_str,
                            },
                        )
                    except Exception as e_drive:
                        log_manager.add(
                            f"[BACKUP] {emp}: erro ao subir {gcs_path} para Drive: {e_drive}",
                            "ERROR",
                        )


                drive_path = (
                    f"{bucket}/{STORAGE_PREFIX}/{emp}/{month_str}/{kind}/{filename}"
                    if bucket
                    else f"{STORAGE_PREFIX}/{emp}/{month_str}/{kind}/{filename}"
                )

                entry: Dict[str, Any] = {
                    "id": drive_id,
                    "drive_id": drive_id,
                    "drive_path": drive_path,
                    "md5": md5_b64,
                    "kind": kind,
                    "path": path_rel,
                    "gcs_path": gcs_path,
                    "drive_action": action,
                }

                meta = meta_por_gcs.get(gcs_path)
                if meta:
                    entry["db"] = meta

                index_json["by_name"][filename] = entry

            # Sobe JSONs
            upload_json(svc, month_id, "_index_fotos.json", index_json)
            upload_json(
                svc,
                month_id,
                "_backup_ok.json",
                {"empresa": emp, "when": dt.datetime.now().isoformat()},
            )

            ok_empresas.append(emp)
            try:
                progress_bus.update(advance=1)
            except Exception:
                pass
            log_manager.add(f"[BACKUP] {emp}: OK ({i}/{len(empresas)})", "INFO")

        except Exception as e_emp:
            log_manager.add(f"[BACKUP] {emp}: ERRO {e_emp}", "ERROR")
            _push_debug(debug_lines, f"ERRO empresa {emp}: {e_emp!r}", level="ERROR")

    try:
        progress_bus.finish()
    except Exception:
        pass

    debug_text = "\n".join(debug_lines[:200])

    if ok_empresas:
        corpo = (
            f"Empresas processadas: {', '.join(ok_empresas)}\n\n"
            "Amostra dos dados extraídos:\n"
            + debug_text
        )
        send_response(sender, "✅ BACKUP concluído", corpo)
    else:
        corpo = (
            "Nenhuma empresa processada (verifique Firebase Storage e permissões).\n\n"
            "DEBUG:\n" + debug_text
        )
        send_response(sender, "⚠️ BACKUP sem alterações", corpo)
