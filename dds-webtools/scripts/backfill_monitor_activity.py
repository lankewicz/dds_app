# -----------------------------------------------------------------------------
# Arquivo : scripts/backfill_monitor_activity.py
# Objetivo: Script de uso único para popular o histórico e o estado consolidado
#           de atividade das equipes no Firestore, usando dados antigos de DDS,
#           turno e, opcionalmente, mensagens. O script cria documentos em
#           monitor_activity_events e monitor_activity_state, e pode atualizar
#           dds_teams/{teamKey} com lastActivityAt/lastActivitySource/active.
# -----------------------------------------------------------------------------

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from google.cloud import firestore

# Permite executar a partir da raiz do projeto dds-webtools.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MONITOR_ROOT = PROJECT_ROOT / "monitor"
if str(MONITOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITOR_ROOT))

from services.firestore_client import db  # noqa: E402

DEFAULT_EMPRESA = os.getenv("DDS_EMPRESA_PADRAO", "ChicoEletro")
DDS_TIMEZONE = os.getenv("DDS_TIMEZONE", "America/Sao_Paulo")
ACTIVITY_STATE_COLLECTION = os.getenv("MONITOR_ACTIVITY_STATE_COLLECTION", "monitor_activity_state")
ACTIVITY_EVENTS_COLLECTION = os.getenv("MONITOR_ACTIVITY_EVENTS_COLLECTION", "monitor_activity_events")
DDS_TEAMS_COLLECTION = os.getenv("DDS_TEAMS_COLLECTION", "dds_teams")
DDS_TRAINING_EXEC_COLLECTION = os.getenv("DDS_TRAINING_EXEC_COLLECTION", "dds_training_exec")
DDS_COLLECTION = os.getenv("DDS_COLLECTION_NAME", "DDS")
MESSAGES_COLLECTION = os.getenv("MESSAGES_COLLECTION", "mensagens_comunicacao")


@dataclass
class ActivityEvent:
    empresa: str
    team_key: str
    equipe: str
    source: str
    activity_at: datetime
    event_ref: str
    active_after_event: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def activity_day(self) -> str:
        return local_day_key(self.activity_at)

    @property
    def event_id(self) -> str:
        base = f"{self.empresa}|{self.team_key}|{self.source}|{self.activity_at.isoformat()}|{self.event_ref}"
        digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
        safe_team = re.sub(r"[^A-Z0-9_\-]", "_", normalize_text(self.team_key) or "UNKNOWN")
        safe_source = re.sub(r"[^a-z0-9_\-]", "_", str(self.source or "unknown").lower())
        return f"{self.activity_at.strftime('%Y%m%dT%H%M%S')}_{safe_team}_{safe_source}_{digest}"


def get_tz():
    try:
        return ZoneInfo(DDS_TIMEZONE)
    except Exception:
        return timezone(timedelta(hours=-3))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def alias_matches(value: str | None, alias: str | None) -> bool:
    norm_value = normalize_text(value)
    norm_alias = normalize_text(alias)
    if not norm_value or not norm_alias:
        return False
    if norm_value == norm_alias:
        return True
    token_re = rf"(?<![A-Z0-9]){re.escape(norm_alias)}(?![A-Z0-9])"
    if re.search(token_re, norm_value):
        return True
    reverse_re = rf"(?<![A-Z0-9]){re.escape(norm_value)}(?![A-Z0-9])"
    return bool(re.search(reverse_re, norm_alias))


def to_utc_dt(value: Any) -> datetime | None:
    if not value:
        return None

    if hasattr(value, "to_datetime"):
        dt = value.to_datetime()
    elif isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def local_day_key(value: datetime) -> str:
    return value.astimezone(get_tz()).strftime("%Y-%m-%d")


def parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def month_keys(start_day: date, end_day: date) -> list[str]:
    cursor = date(start_day.year, start_day.month, 1)
    last = date(end_day.year, end_day.month, 1)
    out: list[str] = []
    while cursor <= last:
        out.append(cursor.strftime("%Y-%m"))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return out


def in_period(dt: datetime, start_day: date, end_day: date) -> bool:
    local_day = dt.astimezone(get_tz()).date()
    return start_day <= local_day <= end_day


def first_dt(data: dict[str, Any], keys: Iterable[str]) -> datetime | None:
    for key in keys:
        dt = to_utc_dt(data.get(key))
        if dt:
            return dt
    return None


def read_teams(selected: set[str] | None = None) -> dict[str, dict[str, Any]]:
    teams: dict[str, dict[str, Any]] = {}
    for snap in db.collection(DDS_TEAMS_COLLECTION).stream():
        if selected and snap.id not in selected:
            continue
        data = snap.to_dict() or {}
        teams[snap.id] = data
    return teams


def build_alias_index(teams: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for team_key, data in teams.items():
        aliases = {
            normalize_text(team_key),
            normalize_text(data.get("teamKey")),
            normalize_text(data.get("displayName")),
            normalize_text(data.get("equipe")),
        }
        index[team_key] = {a for a in aliases if a}
    return index


def find_team_keys(name: str, alias_index: dict[str, set[str]]) -> list[str]:
    matches: list[str] = []
    for team_key, aliases in alias_index.items():
        if any(alias_matches(name, alias) for alias in aliases):
            matches.append(team_key)
    return matches


def iter_training_items(raw: Any):
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, dict):
                yield str(key), value
    elif isinstance(raw, list):
        for idx, value in enumerate(raw):
            if isinstance(value, dict):
                training_id = str(value.get("trainingId") or value.get("id") or idx)
                yield training_id, value


def collect_dds_training_exec_events(
    *,
    empresa: str,
    teams: dict[str, dict[str, Any]],
    start_day: date,
    end_day: date,
) -> list[ActivityEvent]:
    events: list[ActivityEvent] = []
    months = month_keys(start_day, end_day)
    for team_key, team_data in teams.items():
        equipe = str(team_data.get("displayName") or team_data.get("teamKey") or team_key)
        for ym in months:
            ref = (
                db.collection(DDS_TRAINING_EXEC_COLLECTION)
                .document(team_key)
                .collection("months")
                .document(ym)
            )
            snap = ref.get()
            if not snap.exists:
                continue
            month_data = snap.to_dict() or {}
            raw_items = (
                month_data.get("executedTrainings")
                or month_data.get("trainings")
                or month_data.get("items")
                or {}
            )
            for training_id, item in iter_training_items(raw_items):
                activity_at = first_dt(
                    item,
                    (
                        "executedAt",
                        "submittedAt",
                        "sentAt",
                        "serverUpdatedAt",
                        "updatedAt",
                        "createdAt",
                        "timestamp",
                    ),
                )
                if not activity_at or not in_period(activity_at, start_day, end_day):
                    continue

                events.append(
                    ActivityEvent(
                        empresa=empresa,
                        team_key=team_key,
                        equipe=str(item.get("teamName") or equipe or team_key),
                        source="dds",
                        activity_at=activity_at,
                        event_ref=f"{ref.path}#executedTrainings/{training_id}",
                        active_after_event=True,
                        extra={
                            "trainingId": training_id,
                            "headerTitle": item.get("headerTitle") or item.get("title") or item.get("tema"),
                            "month": ym,
                            "origin": "dds_training_exec",
                        },
                    )
                )
    return events


def collect_dds_collection_events(
    *,
    empresa: str,
    alias_index: dict[str, set[str]],
    start_day: date,
    end_day: date,
) -> list[ActivityEvent]:
    events: list[ActivityEvent] = []
    start_key = start_day.strftime("%Y-%m-%d")
    end_key = end_day.strftime("%Y-%m-%d") + "\uf8ff"
    query = (
        db.collection(DDS_COLLECTION)
        .where(filter=firestore.FieldFilter("headerDate", ">=", start_key))
        .where(filter=firestore.FieldFilter("headerDate", "<=", end_key))
    )
    for snap in query.stream():
        data = snap.to_dict() or {}
        equipe = str(data.get("equipe") or data.get("teamName") or "").strip()
        if not equipe:
            continue
        activity_at = first_dt(
            data,
            (
                "executedAt",
                "submittedAt",
                "sentAt",
                "serverUpdatedAt",
                "updatedAt",
                "createdAt",
                "timestamp",
                "dataHora",
            ),
        )
        if not activity_at:
            header_day = str(data.get("headerDate") or "")[:10]
            if re.match(r"^\d{4}-\d{2}-\d{2}$", header_day):
                local_dt = datetime.strptime(header_day, "%Y-%m-%d").replace(hour=12, tzinfo=get_tz())
                activity_at = local_dt.astimezone(timezone.utc)
        if not activity_at or not in_period(activity_at, start_day, end_day):
            continue

        for team_key in find_team_keys(equipe, alias_index):
            events.append(
                ActivityEvent(
                    empresa=empresa,
                    team_key=team_key,
                    equipe=equipe,
                    source="dds",
                    activity_at=activity_at,
                    event_ref=snap.reference.path,
                    active_after_event=True,
                    extra={
                        "headerDate": data.get("headerDate"),
                        "headerTitle": data.get("headerTitle") or data.get("tema") or data.get("title"),
                        "origin": "DDS",
                    },
                )
            )
    return events


def collect_turno_events(
    *,
    empresa: str,
    teams: dict[str, dict[str, Any]],
    start_day: date,
    end_day: date,
) -> list[ActivityEvent]:
    events: list[ActivityEvent] = []
    col = db.collection("turno").document(empresa).collection("equipes")
    for snap in col.stream():
        if snap.id not in teams:
            # Mantém turno mesmo que ainda não exista em dds_teams.
            team_data = {}
        else:
            team_data = teams[snap.id]
        data = snap.to_dict() or {}
        activity_at = first_dt(data, ("serverUpdatedAt", "updatedAt", "createdAt", "timestamp"))
        if not activity_at or not in_period(activity_at, start_day, end_day):
            continue
        equipe = str(team_data.get("displayName") or data.get("equipe") or snap.id)
        events.append(
            ActivityEvent(
                empresa=empresa,
                team_key=snap.id,
                equipe=equipe,
                source="turno",
                activity_at=activity_at,
                event_ref=snap.reference.path,
                active_after_event=True,
                extra={
                    "estado": data.get("estado"),
                    "nocSs": data.get("nocSs"),
                    "origin": "turno_equipes",
                },
            )
        )
    return events


def collect_message_events(
    *,
    empresa: str,
    alias_index: dict[str, set[str]],
    start_day: date,
    end_day: date,
) -> list[ActivityEvent]:
    events: list[ActivityEvent] = []
    for snap in db.collection(MESSAGES_COLLECTION).stream():
        data = snap.to_dict() or {}
        activity_at = first_dt(data, ("sentAt", "timestamp", "serverUpdatedAt", "updatedAt", "createdAt"))
        if not activity_at or not in_period(activity_at, start_day, end_day):
            continue
        for raw_name in (data.get("fromEquipe"), data.get("toEquipe")):
            name = str(raw_name or "").strip()
            if not name:
                continue
            for team_key in find_team_keys(name, alias_index):
                events.append(
                    ActivityEvent(
                        empresa=empresa,
                        team_key=team_key,
                        equipe=name,
                        source="mensagem",
                        activity_at=activity_at,
                        event_ref=snap.reference.path,
                        active_after_event=True,
                        extra={"origin": "mensagens_comunicacao"},
                    )
                )
    return events


def latest_by_team(events: list[ActivityEvent]) -> dict[str, ActivityEvent]:
    latest: dict[str, ActivityEvent] = {}
    for ev in events:
        current = latest.get(ev.team_key)
        if current is None or ev.activity_at > current.activity_at:
            latest[ev.team_key] = ev
    return latest


def commit_batch(batch, dry_run: bool) -> None:
    if dry_run:
        return
    batch.commit()


def write_events_and_state(
    *,
    events: list[ActivityEvent],
    teams: dict[str, dict[str, Any]],
    dry_run: bool,
    update_dds_teams: bool,
    reactivate_days: int,
) -> dict[str, int]:
    stats = {"events": 0, "state": 0, "dds_teams": 0, "batches": 0}
    batch = db.batch()
    ops = 0
    cutoff = now_utc() - timedelta(days=reactivate_days)
    latest = latest_by_team(events)

    def add_set(ref, payload, merge=True):
        nonlocal batch, ops
        batch.set(ref, payload, merge=merge)
        ops += 1
        if ops >= 450:
            commit_batch(batch, dry_run)
            stats["batches"] += 1
            batch = db.batch()
            ops = 0

    for ev in events:
        event_ref = (
            db.collection(ACTIVITY_EVENTS_COLLECTION)
            .document(ev.activity_day)
            .collection("events")
            .document(ev.event_id)
        )
        payload = {
            "eventId": ev.event_id,
            "empresa": ev.empresa,
            "teamKey": ev.team_key,
            "equipe": ev.equipe,
            "source": ev.source,
            "activityAt": ev.activity_at,
            "activityDay": ev.activity_day,
            "eventRef": ev.event_ref,
            "activeAfterEvent": ev.active_after_event,
            "receivedAt": firestore.SERVER_TIMESTAMP,
            **ev.extra,
        }
        add_set(event_ref, payload, merge=True)
        stats["events"] += 1

    for team_key, ev in latest.items():
        state_id = f"{ev.empresa}_{team_key}"
        team_data = teams.get(team_key) or {}
        current_active = bool(team_data.get("active", True)) if team_data else True
        inactive_reason = team_data.get("autoInactiveReason")
        inactive_at = to_utc_dt(team_data.get("autoInactiveAt"))
        manual_blocks = inactive_reason == "MANUAL" and inactive_at and ev.activity_at <= inactive_at
        should_reactivate = ev.activity_at >= cutoff and not manual_blocks
        active_value = True if should_reactivate else current_active

        state_ref = db.collection(ACTIVITY_STATE_COLLECTION).document(state_id)
        add_set(
            state_ref,
            {
                "empresa": ev.empresa,
                "teamKey": team_key,
                "equipe": ev.equipe,
                "active": active_value,
                "lastActivityAt": ev.activity_at,
                "lastActivitySource": ev.source,
                "lastActivityEventId": ev.event_id,
                "updatedAt": firestore.SERVER_TIMESTAMP,
                "backfilledAt": firestore.SERVER_TIMESTAMP,
                "reactivatedByBackfill": bool(should_reactivate),
            },
            merge=True,
        )
        stats["state"] += 1

        if update_dds_teams:
            team_payload: dict[str, Any] = {
                "lastActivityAt": ev.activity_at,
                "lastActivitySource": ev.source,
                "lastActivityEventId": ev.event_id,
                "updatedAt": firestore.SERVER_TIMESTAMP,
                "backfilledActivityAt": firestore.SERVER_TIMESTAMP,
            }
            if should_reactivate:
                team_payload.update(
                    {
                        "active": True,
                        "autoInactiveReason": firestore.DELETE_FIELD,
                        "autoInactiveAt": firestore.DELETE_FIELD,
                        "autoReactivatedAt": firestore.SERVER_TIMESTAMP,
                        "autoInactiveLastSeenUpdatedAt": ev.activity_at,
                    }
                )
            add_set(db.collection(DDS_TEAMS_COLLECTION).document(team_key), team_payload, merge=True)
            stats["dds_teams"] += 1

    if ops:
        commit_batch(batch, dry_run)
        stats["batches"] += 1

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill de atividade do monitor de turnos.")
    parser.add_argument("--empresa", default=DEFAULT_EMPRESA)
    parser.add_argument("--start", required=True, help="Data inicial YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Data final YYYY-MM-DD")
    parser.add_argument("--team", action="append", help="Filtra uma equipe. Pode repetir.")
    parser.add_argument("--sources", default="dds_exec,turno", help="Fontes: dds_exec,dds_collection,turno,mensagem")
    parser.add_argument("--reactivate-days", type=int, default=7, help="Janela para reativar equipe por atividade recente")
    parser.add_argument("--update-dds-teams", action="store_true", help="Atualiza dds_teams/{teamKey}")
    parser.add_argument("--commit", action="store_true", help="Grava no Firestore. Sem isso roda em dry-run.")
    args = parser.parse_args()

    start_day = parse_day(args.start)
    end_day = parse_day(args.end)
    if end_day < start_day:
        raise SystemExit("--end não pode ser menor que --start")

    selected = set(args.team or []) or None
    sources = {s.strip().lower() for s in str(args.sources or "").split(",") if s.strip()}
    dry_run = not args.commit

    teams = read_teams(selected)
    alias_index = build_alias_index(teams)
    events: list[ActivityEvent] = []

    print(f"Backfill activity | empresa={args.empresa} | período={args.start}..{args.end} | dry_run={dry_run}")
    print(f"Equipes carregadas: {len(teams)}")
    print(f"Fontes: {sorted(sources)}")

    if "dds_exec" in sources:
        chunk = collect_dds_training_exec_events(
            empresa=args.empresa,
            teams=teams,
            start_day=start_day,
            end_day=end_day,
        )
        print(f"Eventos dds_training_exec: {len(chunk)}")
        events.extend(chunk)

    if "dds_collection" in sources:
        chunk = collect_dds_collection_events(
            empresa=args.empresa,
            alias_index=alias_index,
            start_day=start_day,
            end_day=end_day,
        )
        print(f"Eventos DDS: {len(chunk)}")
        events.extend(chunk)

    if "turno" in sources:
        chunk = collect_turno_events(
            empresa=args.empresa,
            teams=teams,
            start_day=start_day,
            end_day=end_day,
        )
        print(f"Eventos turno: {len(chunk)}")
        events.extend(chunk)

    if "mensagem" in sources:
        chunk = collect_message_events(
            empresa=args.empresa,
            alias_index=alias_index,
            start_day=start_day,
            end_day=end_day,
        )
        print(f"Eventos mensagem: {len(chunk)}")
        events.extend(chunk)

    events.sort(key=lambda ev: (ev.team_key, ev.activity_at, ev.source, ev.event_ref))
    print(f"Total de eventos coletados: {len(events)}")
    print(f"Equipes com estado calculado: {len(latest_by_team(events))}")

    stats = write_events_and_state(
        events=events,
        teams=teams,
        dry_run=dry_run,
        update_dds_teams=args.update_dds_teams,
        reactivate_days=args.reactivate_days,
    )

    print("Resultado:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    if dry_run:
        print("DRY-RUN: nada foi gravado. Use --commit para gravar no Firestore.")
    else:
        print("Backfill concluído e gravado no Firestore.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
