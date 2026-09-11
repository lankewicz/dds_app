"""Executa a raspagem Rotalog localmente com suporte a sincronização no Firebase Storage.

Os snapshots e históricos ficam no diretório informado em --output-dir (dados-local).
Com a flag --firebase, os arquivos e o snapshot consolidado (index.json.gz) são
enviados diretamente para o Firebase Storage, alimentando o Monitor de Turnos no Cloud Run.
Use --once para um teste único; sem essa opção o processo permanece em ciclo.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from bdo.services.rotalog_change_tracker import (
    RotalogGcsSnapshotStore,
    changed_fields,
)
from bdo.services.rotalog_execution_log import RotalogExecutionLog
from bdo.services.rotalog_sync_task import _build_rotalog_document, normalize_team_key
from bdo.services.rotalog_team_file_repository import (
    RotalogTeamFileRepository,
    merge_daily_document,
)
from bdo.services.rotalog_tempo_real_service import extrair_dados_tempo_real


TZ = ZoneInfo(os.getenv("DDS_TIMEZONE", "America/Sao_Paulo"))
LOG = logging.getLogger("rotalog-local")


def _load_json(path: Path, fallback):
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
            return value if isinstance(value, type(fallback)) else fallback
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
    temporary.replace(path)


def _queue_counts(team: dict) -> dict[str, int]:
    pending = team.get("ss_pendentes") or []
    return {
        "emergencia": sum(1 for item in pending if str(item.get("tipo") or "").upper() == "EMERGENCIA"),
        "comercial": sum(1 for item in pending if str(item.get("tipo") or "").upper() == "COMERCIAL"),
    }


def _init_firebase_storage():
    """Inicializa Firebase Admin e os repositórios GCS caso as credenciais estejam disponíveis."""
    try:
        import firebase_admin
        from firebase_admin import credentials
        from google.cloud import storage

        cred_candidates = [
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            os.getenv("FIREBASE_CREDENTIALS"),
            str(ROOT / "firebase_config.json"),
            str(ROOT / "serviceAccountKey.json"),
            str(ROOT / "firebase_credentials.json"),
            str(ROOT.parent / "firebase_config.json"),
            str(ROOT.parent / "serviceAccountKey.json"),
        ]
        cred_path = next((p for p in cred_candidates if p and os.path.isfile(p)), None)

        client_factory = None
        if cred_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
            client_factory = lambda: storage.Client.from_service_account_json(cred_path)
            if not firebase_admin._apps:
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                LOG.info("Firebase inicializado via credencial de arquivo: %s", cred_path)
        else:
            if not firebase_admin._apps:
                firebase_admin.initialize_app()
                LOG.info("Firebase inicializado com credenciais padrão do ambiente")

        bucket_name = os.getenv("DDS_BUCKET_NAME", "dds-treinamentos.firebasestorage.app")
        blob_name = os.getenv(
            "ROTALOG_GCS_CACHE_BLOB",
            "dados/chicoeletro/rotalog/equipes/current/index.json.gz",
        )
        store = RotalogGcsSnapshotStore(bucket_name, blob_name, client_factory=client_factory)
        team_repo = RotalogTeamFileRepository(store)
        exec_log = RotalogExecutionLog(store)
        return store, team_repo, exec_log
    except Exception as exc:
        LOG.warning("Não foi possível inicializar conexão com Firebase Storage: %s", exc)
        return None, None, None


class LocalRotalogRunner:
    def __init__(self, output_dir: Path, empresa: str, enable_firebase: bool = False):
        self.output_dir = output_dir
        self.empresa = empresa
        self.index_path = output_dir / "rotalog" / "equipes" / "current" / "index.json"
        self.log_path = output_dir / "rotalog" / "logs" / "execucoes.jsonl"
        self.enable_firebase = enable_firebase
        self.firebase_store = None
        self.team_repo = None
        self.exec_log = None

        if self.enable_firebase:
            self.firebase_store, self.team_repo, self.exec_log = _init_firebase_storage()

    @property
    def firebase_enabled(self) -> bool:
        return bool(self.firebase_store and self.firebase_store.enabled)

    def run_once(self) -> dict:
        started_clock = time.perf_counter()
        started_at = datetime.now(TZ)
        previous = _load_json(self.index_path, {}).get("equipes", {})
        if not isinstance(previous, dict):
            previous = {}

        # Se o cache local estiver vazio e o Firebase Storage estiver ativo,
        # hidrata automaticamente o histórico anterior diretamente da nuvem
        if not previous and self.firebase_enabled:
            try:
                remote_payload = self.firebase_store.load()
                remote_snapshots = (
                    remote_payload.get("snapshots")
                    if isinstance(remote_payload.get("snapshots"), dict)
                    else remote_payload
                )
                if isinstance(remote_snapshots, dict) and remote_snapshots:
                    previous = remote_snapshots
                    _write_json(self.index_path, {
                        "schemaVersion": 1,
                        "company": self.empresa,
                        "lastCollectedAt": remote_payload.get("updatedAtIso") or datetime.now(TZ).isoformat(),
                        "equipes": previous,
                    })
                    LOG.info("Cache local inicial hidratado com %d equipes do Firebase Storage", len(previous))
            except Exception as exc:
                LOG.warning("Não foi possível pré-carregar cache inicial do Storage: %s", exc)

        try:
            teams = extrair_dados_tempo_real(snapshots_anteriores=previous)
            scraped_at = datetime.now(TZ)
            timestamp = scraped_at.isoformat()
            day = scraped_at.date().isoformat()
            updates = {}
            ignored = 0

            for team in teams:
                code = str(team.get("equipe_codigo") or "").strip().upper()
                if not code:
                    continue
                team_key = normalize_team_key(code)
                document = _build_rotalog_document(
                    team, self.empresa, team_key, timestamp, _queue_counts(team)
                )
                old = previous.get(team_key)
                document["historyDay"] = day
                document["version"] = 1 if not old or old.get("historyDay") != day else int(old.get("version") or 0) + 1

                if old and not changed_fields(old, document) and old.get("historyDay") == day:
                    ignored += 1
                    document = {**old, "lastCollectedAt": timestamp}
                else:
                    document["lastCollectedAt"] = timestamp
                    updates[team_key] = document

                    # 1. Grava no disco local
                    current_path = self.output_dir / "rotalog" / "equipes" / "current" / f"{team_key}.json"
                    _write_json(current_path, document)
                    daily_path = self.output_dir / "rotalog" / "equipes" / "daily" / day / f"{team_key}.json"
                    merged_daily = merge_daily_document(_load_json(daily_path, {}), document, day)
                    _write_json(daily_path, merged_daily)

                    # 2. Grava no Firebase Storage (GCS) se ativado
                    if self.firebase_enabled and self.team_repo:
                        try:
                            self.team_repo.save_current(document)
                            self.team_repo.merge_and_save_daily(document, day)
                        except Exception as exc:
                            LOG.error("Erro ao sincronizar equipe %s no Storage: %s", team_key, exc)

                previous[team_key] = document

            # Grava o índice único local
            _write_json(self.index_path, {
                "schemaVersion": 1,
                "company": self.empresa,
                "lastCollectedAt": timestamp,
                "equipes": previous,
            })

            # Grava o índice único consolidado (index.json.gz) no Firebase Storage
            firebase_uploaded = False
            if self.firebase_enabled and self.firebase_store:
                try:
                    self.firebase_store.save({
                        "version": 2,
                        "updatedAtIso": timestamp,
                        "snapshots": previous,
                    })
                    firebase_uploaded = True
                except Exception as exc:
                    LOG.error("Erro ao salvar snapshot consolidado no Firebase Storage: %s", exc)

            finished_at = datetime.now(TZ)
            duration_total = round(time.perf_counter() - started_clock, 3)

            # Registra auditoria no log do Firebase Storage
            if self.firebase_enabled and self.exec_log:
                try:
                    self.exec_log.record(
                        status="success",
                        started_at=started_at,
                        finished_at=finished_at,
                        duration_seconds=duration_total,
                        details={
                            "totalTeams": len(teams),
                            "updatedTeams": len(updates),
                            "ignoredTeams": ignored,
                            "scrapeDurationSeconds": round((scraped_at - started_at).total_seconds(), 3),
                        },
                    )
                except Exception as exc:
                    LOG.warning("Erro ao gravar log diário de execução no Storage: %s", exc)

            result = {
                "status": "success",
                "startedAt": started_at.isoformat(),
                "finishedAt": finished_at.isoformat(),
                "durationSeconds": duration_total,
                "scrapeDurationSeconds": round((scraped_at - started_at).total_seconds(), 3),
                "totalTeams": len(teams),
                "updatedTeams": len(updates),
                "ignoredTeams": ignored,
                "firebaseUploaded": firebase_uploaded,
            }
        except Exception as exc:
            result = {
                "status": "error",
                "startedAt": started_at.isoformat(),
                "finishedAt": datetime.now(TZ).isoformat(),
                "durationSeconds": round(time.perf_counter() - started_clock, 3),
                "error": str(exc),
                "firebaseUploaded": False,
            }
            LOG.exception("Falha na raspagem local")

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="dados-local", help="Diretório local para JSONs")
    parser.add_argument("--interval-seconds", type=int, default=120, help="Intervalo entre raspagens (segundos)")
    parser.add_argument("--empresa", default="ChicoEletro")
    parser.add_argument("--firebase", action="store_true", help="Ativa sincronização automática com Firebase Storage")
    parser.add_argument("--once", action="store_true", help="Executa somente uma vez")
    args = parser.parse_args()
    if args.interval_seconds < 30:
        parser.error("--interval-seconds deve ser no mínimo 30")

    load_dotenv(ROOT / ".env")
    enable_firebase = args.firebase or os.getenv("ROTALOG_UPLOAD_FIREBASE", "false").strip().lower() in ("true", "1", "yes")

    runner = LocalRotalogRunner(Path(args.output_dir).resolve(), args.empresa, enable_firebase=enable_firebase)
    while True:
        result = runner.run_once()
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if args.once:
            return 0 if result["status"] == "success" else 1
        elapsed = float(result["durationSeconds"])
        time.sleep(max(1, args.interval_seconds - elapsed))


if __name__ == "__main__":
    raise SystemExit(main())
