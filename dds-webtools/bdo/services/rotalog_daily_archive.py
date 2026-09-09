"""Coleta diária e arquivamento das tabelas históricas do ROTALOG em JSON."""

from __future__ import annotations

import datetime
import gzip
import json
import os
import typing

from google.cloud import storage

from bdo.services.rotalog_crawler_service import CrawlerRotalog


LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=-3))
DEFAULT_PREFIX = "_cache/rotalog/coletas"


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
        bucket_name: str | None = None,
        prefix: str | None = None,
        *,
        client_factory: typing.Callable[[], typing.Any] = storage.Client,
        crawler_factory: typing.Callable[[], CrawlerRotalog] = CrawlerRotalog,
    ):
        self.bucket_name = (bucket_name or os.getenv("DDS_BUCKET_NAME", "")).strip()
        self.prefix = (prefix or os.getenv("ROTALOG_DAILY_ARCHIVE_PREFIX", DEFAULT_PREFIX)).strip().strip("/")
        if not self.bucket_name:
            raise RuntimeError("DDS_BUCKET_NAME não configurado.")
        self.client_factory = client_factory
        self.crawler_factory = crawler_factory

    def _save(self, path: str, payload: dict[str, typing.Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        blob = self.client_factory().bucket(self.bucket_name).blob(path)
        blob.content_encoding = "gzip"
        blob.upload_from_string(gzip.compress(raw, compresslevel=6), content_type="application/json")

    def collect(self, day: datetime.date | None = None) -> dict[str, typing.Any]:
        local_now = datetime.datetime.now(LOCAL_TZ)
        target_day = day or (local_now.date() - datetime.timedelta(days=1))
        day_iso = target_day.isoformat()
        day_br = target_day.strftime("%d/%m/%Y")
        teams_frame, events_frame = self.crawler_factory()._raspar_bloco(day_br, day_br)
        teams = dataframe_records(teams_frame)
        events = dataframe_records(events_frame)
        collected_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        base = f"{self.prefix}/{day_iso}"
        teams_path = f"{base}/equipes.json.gz"
        events_path = f"{base}/eventos.json.gz"
        common = {"schemaVersion": 1, "date": day_iso, "collectedAt": collected_at}
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
        return {
            "status": "success",
            "date": day_iso,
            "collectedAt": collected_at,
            "teams": len(teams),
            "events": len(events),
            "teamsPath": teams_path,
            "eventsPath": events_path,
        }
