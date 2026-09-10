"""Log diário das tentativas de sincronização do Rotalog."""

from __future__ import annotations

import datetime
import typing

from bdo.services.rotalog_team_file_repository import LOCAL_TZ


class RotalogExecutionLog:
    def __init__(self, store, root_prefix: str = "dados/chicoeletro/rotalog/logs"):
        self.store = store
        self.root_prefix = root_prefix.strip().strip("/")

    def path(self, day: str) -> str:
        datetime.date.fromisoformat(day)
        return f"{self.root_prefix}/{day}.json.gz"

    def load(self, day: str) -> dict[str, typing.Any]:
        return self.store.load_blob(self.path(day))

    def record(
        self,
        status: str,
        *,
        started_at: datetime.datetime,
        finished_at: datetime.datetime,
        duration_seconds: float,
        details: dict[str, typing.Any] | None = None,
    ) -> dict[str, typing.Any]:
        local_start = started_at.astimezone(LOCAL_TZ)
        local_finish = finished_at.astimezone(LOCAL_TZ)
        day = local_start.date().isoformat()
        entry = {
            "startedAt": local_start.isoformat(),
            "finishedAt": local_finish.isoformat(),
            "status": status,
            "durationSeconds": round(max(0.0, duration_seconds), 3),
            **(details or {}),
        }

        def merge(previous):
            entries = list(previous.get("entries") or [])
            entries.append(entry)
            successes = sum(item.get("status") == "success" for item in entries)
            skipped = sum(item.get("status") == "skipped" for item in entries)
            failures = sum(item.get("status") == "failed" for item in entries)
            durations = [
                float(item.get("durationSeconds") or 0)
                for item in entries
                if item.get("status") == "success"
            ]
            return {
                "schemaVersion": 1,
                "date": day,
                "timezone": str(LOCAL_TZ),
                "updatedAt": local_finish.isoformat(),
                "summary": {
                    "attempts": len(entries),
                    "successes": successes,
                    "skipped": skipped,
                    "failures": failures,
                    "averageDurationSeconds": round(sum(durations) / len(durations), 3) if durations else 0,
                    "maximumDurationSeconds": round(max(durations), 3) if durations else 0,
                },
                "entries": entries,
            }

        return self.store.update_blob(self.path(day), merge)
