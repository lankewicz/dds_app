"""Coleta diária e arquivamento das tabelas históricas do ROTALOG em JSON."""

from __future__ import annotations

import datetime
import gzip
import json
import os
import re
import typing
import unicodedata

from google.cloud import storage

from bdo.services.rotalog_crawler_service import CrawlerRotalog


LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=-3))
DEFAULT_PREFIX = "dados"
ARCHIVE_KINDS = {"equipes", "eventos"}


def company_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").strip())
    key = re.sub(r"[^a-z0-9]+", "-", normalized.encode("ascii", "ignore").decode("ascii").lower()).strip("-")
    if not key:
        raise ValueError("Empresa inválida.")
    return key


def _json_value(value: typing.Any) -> typing.Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        if value != value:
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        value = value.item()
    return value


def dataframe_records(frame) -> list[dict[str, typing.Any]]:
    return [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


class DailyRotalogArchive:
    def __init__(
        self,
        company: str | None = None,
        bucket_name: str | None = None,
        prefix: str | None = None,
        *,
        client_factory: typing.Callable[[], typing.Any] = storage.Client,
        crawler_factory: typing.Callable[[], CrawlerRotalog] = CrawlerRotalog,
    ):
        self.company = (company or os.getenv("ROTALOG_EMPRESA", "")).strip()
        if not self.company:
            raise RuntimeError("ROTALOG_EMPRESA não configurada.")
        self.company_key = company_key(self.company)
        self.bucket_name = (bucket_name or os.getenv("DDS_BUCKET_NAME", "")).strip()
        self.prefix = (prefix or os.getenv("ROTALOG_DAILY_ARCHIVE_PREFIX", DEFAULT_PREFIX)).strip().strip("/")
        if not self.bucket_name:
            raise RuntimeError("DDS_BUCKET_NAME não configurado.")
        self.client_factory = client_factory
        self.crawler_factory = crawler_factory

    def path(self, day: datetime.date | str, kind: str) -> str:
        if kind not in ARCHIVE_KINDS:
            raise ValueError("Tipo de arquivo ROTALOG inválido.")
        day_iso = day.isoformat() if isinstance(day, datetime.date) else str(day)
        datetime.date.fromisoformat(day_iso)
        return f"{self.prefix}/{self.company_key}/rotalog/diario/{day_iso}/{kind}.json.gz"

    def _save(self, path: str, payload: dict[str, typing.Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        blob = self.client_factory().bucket(self.bucket_name).blob(path)
        blob.content_encoding = "gzip"
        blob.upload_from_string(gzip.compress(raw, compresslevel=6), content_type="application/json")

    def load(self, day: datetime.date | str, kind: str) -> dict[str, typing.Any]:
        path = self.path(day, kind)
        blob = self.client_factory().bucket(self.bucket_name).blob(path)
        try:
            raw = blob.download_as_bytes(raw_download=True)
        except TypeError:
            raw = blob.download_as_bytes()
        decoded = gzip.decompress(raw) if raw.startswith(b"\x1f\x8b") else raw
        payload = json.loads(decoded.decode("utf-8-sig"))
        if payload.get("companyKey") != self.company_key:
            raise ValueError("Arquivo pertence a outra empresa.")
        return payload

    def collect(
        self,
        day: datetime.date | None = None,
        *,
        now: datetime.datetime | None = None,
    ) -> dict[str, typing.Any]:
        local_now = (now or datetime.datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)
        target_day = day or (local_now.date() - datetime.timedelta(days=1))
        day_iso = target_day.isoformat()
        day_br = target_day.strftime("%d/%m/%Y")
        teams_frame, events_frame = self.crawler_factory()._raspar_bloco(day_br, day_br)
        teams = dataframe_records(teams_frame)
        events = dataframe_records(events_frame)
        collected_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        teams_path = self.path(target_day, "equipes")
        events_path = self.path(target_day, "eventos")
        common = {
            "schemaVersion": 2,
            "company": self.company,
            "companyKey": self.company_key,
            "date": day_iso,
            "collectedAt": collected_at,
        }
        self._save(teams_path, {
            **common,
            "source": "https://www.copel.com/rtlweb/paginas/equipes",
            "count": len(teams),
            "records": teams,
        })
        self._save(events_path, {
            **common,
            "source": "https://www.copel.com/rtlweb/paginas/listagemEventos",
            "count": len(events),
            "records": events,
        })
        reconciliation = self.reconcile(target_day, events, collected_at, teams)
        return {
            "status": "success",
            "date": day_iso,
            "collectedAt": collected_at,
            "teams": len(teams),
            "events": len(events),
            "teamsPath": teams_path,
            "eventsPath": events_path,
            "reconciliation": reconciliation,
        }

    def reconcile(self, day, events, collected_at, teams=None):
        from bdo.services.rotalog_change_tracker import RotalogGcsSnapshotStore
        from bdo.services.rotalog_team_file_repository import RotalogTeamFileRepository
        from bdo.services.rotalog_daily_reconciliation import normalize_events, normalize_turns, reconcile_document
        day_iso = day.isoformat()
        grouped = normalize_events(events, day_iso)
        turns = normalize_turns(teams or [], day_iso)
        if not grouped and not turns:
            return {"teamsUpdated": 0, "reason": "no_matching_events"}
        root = f"{self.prefix}/{self.company_key}/rotalog/equipes"
        store = RotalogGcsSnapshotStore(
            self.bucket_name, f"{root}/current/index.json.gz",
            client_factory=self.client_factory,
        )
        repository = RotalogTeamFileRepository(store, root_prefix=root)
        updated = 0
        for team in grouped.keys() | turns.keys():
            rows = grouped.get(team, [])
            turn = turns.get(team)
            path = repository.daily_path(day_iso, team)
            previous = store.load_blob(path)
            if not previous:
                continue
            if reconcile_document(previous, rows, day_iso, collected_at, turn) == previous:
                continue
            store.update_blob(path, lambda current, rows=rows, turn=turn:
                              reconcile_document(current, rows, day_iso, collected_at, turn))
            updated += 1
        monthly = repository.consolidate_month(day_iso[:7])
        return {"teamsUpdated": updated, "monthly": monthly}
