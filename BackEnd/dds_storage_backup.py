
# -*- coding: utf-8 -*-
"""
=============================================================================
Arquivo: dds_storage_backup.py
Propósito: BACKUP e LIMPEZA do Firebase Storage (Google Cloud Storage)
           para DDS_Fotos/ChicoEletro (Fotos/Thumb) com suporte a:
             - backup local (espelho de diretórios),
             - espelho para outro bucket,
             - manifesto CSV + verificação de integridade (MD5),
             - listagem com soma de espaço total,
             - limpeza por idade (dias) OU por mês/ano (YYYY-MM),
             - auto-detecção de credenciais em ./init/serviceAccountKey.json
               e carregamento de .env de locais comuns.

Garantias:
  - DRY-RUN disponível para simular sem alterar nada.
  - Não remove funcionalidades anteriores; só acrescenta.

Histórico:
  - 2025-09-03: v1.1 – adiciona cleanup por mês, soma de espaço e auto-credenciais.
=============================================================================
"""
import os
import sys
import csv
import base64
import hashlib
import argparse
import datetime as dt
from pathlib import Path
from typing import Iterable, Optional, Tuple, List

from dotenv import load_dotenv
from google.cloud import storage
from tqdm import tqdm

# --------------------------- Helpers --------------------------------------
def human_readable_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    s = 0
    f = float(n)
    while f >= 1024 and s < len(units) - 1:
        f /= 1024.0
        s += 1
    return f"{f:.2f} {units[s]}"

# --------------------------- Config & Utilidades ---------------------------
def load_env_defaults() -> dict:
    """
    Carrega .env (se existir) e retorna defaults úteis para a CLI.

    - Carrega .env de locais comuns: ./, ./init, pasta do script e script/init
    - Se GOOGLE_APPLICATION_CREDENTIALS não estiver setada, tenta aplicar
      ./init/serviceAccountKey.json (relativo ao CWD e ao script).
    """
    # 1) Carrega .env de múltiplos lugares sem sobrescrever variáveis já setadas
    here = Path(__file__).resolve().parent
    candidates = [
        Path(".") / ".env",
        Path(".") / "init" / ".env",
        here / ".env",
        here / "init" / ".env",
    ]
    for envp in candidates:
        if envp.exists():
            load_dotenv(dotenv_path=envp, override=False)

    # 2) Aplicar automaticamente a credencial se ainda não estiver setada
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        cred_candidates = [
            Path(".") / "init" / "serviceAccountKey.json",
            here / "init" / "serviceAccountKey.json",
        ]
        for cp in cred_candidates:
            if cp.exists():
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(cp.resolve())
                print(f"[INFO] GOOGLE_APPLICATION_CREDENTIALS aplicado automaticamente: {cp}")
                break

    return {
        "bucket": os.getenv("GCS_BUCKET", "dds-treinamentos.firebasestorage.app"),
        "prefix": os.getenv("GCS_PREFIX", "DDS_Fotos/ChicoEletro"),
        "local_backup_dir": os.getenv("LOCAL_BACKUP_DIR", ""),
    }

def md5_of_file(path: Path) -> str:
    """Calcula MD5 (base64) de um arquivo local, igual ao md5_hash do GCS."""
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    # md5 do GCS é em base64
    return base64.b64encode(h.digest()).decode("utf-8")

def ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

def utc_now() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)

# --------------------------- Núcleo GCS ------------------------------------
class StorageClient:
    """Encapsula operações no Google Cloud Storage."""

    def __init__(self, bucket_name: str):
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)

    def list_blobs(self, prefix: str) -> Iterable[storage.Blob]:
        """Lista blobs a partir de um prefixo (recursivo)."""
        return self.client.list_blobs(self.bucket, prefix=prefix)

    def download(self, blob: storage.Blob, dest: Path) -> Tuple[Path, bool]:
        """
        Faz download do blob para dest. Retorna (path, ok_integridade).
        ok_integridade=True quando MD5 local == md5_hash do blob.
        """
        ensure_dir(dest)
        blob.download_to_filename(str(dest))
        # Valida integridade usando MD5 base64 do GCS
        blob_md5 = blob.md5_hash  # já vem em base64
        local_md5 = md5_of_file(dest)
        return dest, (blob_md5 == local_md5)

    def copy_to_bucket(self, blob: storage.Blob, dest_bucket_name: str, dest_name: Optional[str] = None) -> storage.Blob:
        """Copia blob para outro bucket mantendo metadados."""
        dest_bucket = self.client.bucket(dest_bucket_name)
        dest_name = dest_name or blob.name
        return self.client.copy_blob(blob, self.bucket, dest_bucket.blob(dest_name))

    def delete_blob(self, blob: storage.Blob) -> None:
        """Remove o blob do bucket."""
        blob.delete()

# --------------------------- Pipeline de Backup -----------------------------
def should_take(blob: storage.Blob, subs: List[str]) -> bool:
    """Filtra por subpastas (ex.: Fotos, Thumb). Se lista vazia, pega tudo."""
    if not subs:
        return True
    # nome completo do blob: ex 'DDS_Fotos/ChicoEletro/Fotos/...'
    for s in subs:
        if f"/{s}/" in blob.name:
            return True
    return False

def local_path_for(root: Path, blob_name: str) -> Path:
    """Monta caminho local espelhando o caminho do Storage."""
    return root / blob_name  # mantemos a mesma estrutura/prefixo

def write_manifest_header(csv_path: Path) -> None:
    new = not csv_path.exists()
    if new:
        ensure_dir(csv_path)
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["blob_name", "size", "updated_utc", "md5_base64", "local_path", "local_ok"])

def append_manifest(csv_path: Path, row: List) -> None:
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(row)

def backup_objects(
    gcs: StorageClient,
    prefix: str,
    subs: List[str],
    to_local: Optional[Path],
    mirror_bucket: Optional[str],
    manifest_csv: Optional[Path],
    dry_run: bool
) -> None:
    """Executa o backup: local, mirror ou ambos. Também registra manifesto."""
    blobs = list(gcs.list_blobs(prefix=prefix))
    if not blobs:
        print("Nenhum objeto encontrado para o prefixo informado.")
        return

    if manifest_csv:
        write_manifest_header(manifest_csv)

    pbar = tqdm(blobs, desc="Processando objetos", unit="obj")
    for blob in pbar:
        if not should_take(blob, subs):
            continue

        pbar.set_postfix_str(blob.name[:80])

        # Mirror para outro bucket
        if mirror_bucket:
            if dry_run:
                print(f"[DRY-RUN] Mirror: {blob.name} -> gs://{mirror_bucket}/{blob.name}")
            else:
                gcs.copy_to_bucket(blob, mirror_bucket)

        # Backup local
        local_ok = None
        local_path_str = ""
        if to_local:
            local_path = local_path_for(to_local, blob.name)
            local_path_str = str(local_path)
            if dry_run:
                print(f"[DRY-RUN] Download: gs://{gcs.bucket.name}/{blob.name} -> {local_path}")
            else:
                _, local_ok = gcs.download(blob, local_path)

        # Manifesto
        if manifest_csv:
            append_manifest(
                manifest_csv,
                [blob.name, blob.size, blob.updated.isoformat(), blob.md5_hash, local_path_str, local_ok]
            )

# --------------------------- Limpeza (Cleanup) ------------------------------
def cleanup_objects(
    gcs: StorageClient,
    prefix: str,
    subs: List[str],
    older_than_days: int,
    dry_run: bool
) -> None:
    """Remove objetos mais antigos que X dias no prefixo/subs informados."""
    if older_than_days <= 0:
        print("older_than_days deve ser > 0 para limpeza.")
        return

    threshold = utc_now() - dt.timedelta(days=older_than_days)
    print(f"Threshold para limpeza: {threshold.isoformat()} (UTC)")

    # Listagem e filtro
    blobs = [b for b in gcs.list_blobs(prefix=prefix) if should_take(b, subs)]
    to_delete = [b for b in blobs if b.updated.replace(tzinfo=dt.timezone.utc) < threshold]

    if not to_delete:
        print("Nada para limpar com os critérios atuais.")
        return

    pbar = tqdm(to_delete, desc="Limpando objetos", unit="del")
    for blob in pbar:
        pbar.set_postfix_str(blob.name[:80])
        if dry_run:
            print(f"[DRY-RUN] DELETE: gs://{gcs.bucket.name}/{blob.name} (updated={blob.updated})")
        else:
            gcs.delete_blob(blob)

def cleanup_objects_in_month(
    gcs: StorageClient,
    prefix: str,
    subs: List[str],
    year: int,
    month: int,
    dry_run: bool
) -> None:
    """Remove objetos cujo 'updated' esteja dentro do mês/ano informados (UTC)."""
    if not (1 <= month <= 12):
        print("Mês inválido (1..12).")
        return

    start = dt.datetime(year, month, 1, tzinfo=dt.timezone.utc)
    # calcular primeiro dia do próximo mês
    if month == 12:
        end = dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc)
    else:
        end = dt.datetime(year, month + 1, 1, tzinfo=dt.timezone.utc)

    print(f"Faixa para limpeza (UTC): {start.isoformat()} <= updated < {end.isoformat()}")

    # Listagem e filtro
    blobs = [b for b in gcs.list_blobs(prefix=prefix) if should_take(b, subs)]
    to_delete: List[storage.Blob] = []
    for b in blobs:
        upd = b.updated.replace(tzinfo=dt.timezone.utc)
        if start <= upd < end:
            to_delete.append(b)

    if not to_delete:
        print("Nada para limpar para o mês especificado.")
        return

    total_size = sum(b.size or 0 for b in to_delete)
    print(f"Encontrados {len(to_delete)} objetos (~{human_readable_bytes(total_size)}) para remoção.")

    pbar = tqdm(to_delete, desc="Limpando objetos (por mês)", unit="del")
    for blob in pbar:
        pbar.set_postfix_str(blob.name[:80])
        if dry_run:
            print(f"[DRY-RUN] DELETE: gs://{gcs.bucket.name}/{blob.name} (updated={blob.updated})")
        else:
            gcs.delete_blob(blob)

# --------------------------- CLI -------------------------------------------
def parse_args() -> argparse.Namespace:
    env = load_env_defaults()
    p = argparse.ArgumentParser(
        description="Backup/Limpeza para Firebase Storage (DDS_Fotos/ChicoEletro).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    p.add_argument("--bucket", default=env["bucket"], help="Nome do bucket GCS/Firebase.")
    p.add_argument("--prefix", default=env["prefix"], help="Prefixo raiz (ex.: DDS_Fotos/ChicoEletro).")
    p.add_argument("--sub", nargs="*", default=["Fotos", "Thumb"], help="Subpastas a considerar (ex.: Fotos Thumb). Vazio = tudo.")
    p.add_argument("--backup-local", type=str, default=env["local_backup_dir"], help="Diretório local para espelhamento (opcional).")
    p.add_argument("--mirror-bucket", type=str, default=None, help="Bucket destino para espelhamento na nuvem (opcional).")
    p.add_argument("--manifest", type=str, default=None, help="Caminho do CSV de manifesto (opcional).")
    p.add_argument("--list", action="store_true", help="Apenas lista objetos (não faz backup).")
    p.add_argument("--cleanup", action="store_true", help="Executa limpeza (deleção).")
    p.add_argument("--older-than-days", type=int, default=0, help="Idade mínima (dias) para limpeza.")
    p.add_argument("--cleanup-ym", type=str, default=None, help="Limpeza por mês (YYYY-MM). Ex: 2025-07")
    p.add_argument("--dry-run", action="store_true", help="Não escreve/ apaga nada (somente simula).")
    return p.parse_args()

def main() -> None:
    args = parse_args()

    # Preparos
    to_local = Path(args.backup_local).resolve() if getattr(args, "backup_local", None) else None
    manifest = Path(args.manifest).resolve() if getattr(args, "manifest", None) else None
    subs = args.sub or []

    # Cliente
    gcs = StorageClient(args.bucket)

    # Apenas listar (diagnóstico)
    if args.list:
        print(f"Listando objetos em gs://{args.bucket}/{args.prefix} ...")
        count = 0
        total_bytes = 0
        for blob in gcs.list_blobs(prefix=args.prefix):
            if should_take(blob, subs):
                size = blob.size or 0
                print(f"- {blob.name} | {size} bytes | updated={blob.updated} | md5={blob.md5_hash}")
                count += 1
                total_bytes += size
        print(f"Total de arquivos: {count} | Espaço total ~ {human_readable_bytes(total_bytes)} ({total_bytes} bytes)")

    # Backup
    do_backup = bool(to_local or args.mirror_bucket)
    if do_backup:
        backup_objects(
            gcs=gcs,
            prefix=args.prefix,
            subs=subs,
            to_local=to_local,
            mirror_bucket=args.mirror_bucket,
            manifest_csv=manifest,
            dry_run=args.dry_run
        )

    # Limpeza
    if args.cleanup:
        if args.cleanup_ym:
            try:
                y_str, m_str = args.cleanup_ym.split("-")
                y, m = int(y_str), int(m_str)
            except Exception:
                print("Formato inválido de --cleanup-ym. Use YYYY-MM, ex.: 2025-07")
            else:
                cleanup_objects_in_month(
                    gcs=gcs,
                    prefix=args.prefix,
                    subs=subs,
                    year=y,
                    month=m,
                    dry_run=args.dry_run
                )
        elif args.older_than_days > 0:
            cleanup_objects(
                gcs=gcs,
                prefix=args.prefix,
                subs=subs,
                older_than_days=args.older_than_days,
                dry_run=args.dry_run
            )
        else:
            print("Nenhum critério de limpeza informado. Use --cleanup-ym YYYY-MM ou --older-than-days N.")

    if not (args.list or do_backup or args.cleanup):
        print("Nada a fazer. Use --list, --backup-local, --mirror-bucket ou --cleanup.")

if __name__ == "__main__":
    main()
