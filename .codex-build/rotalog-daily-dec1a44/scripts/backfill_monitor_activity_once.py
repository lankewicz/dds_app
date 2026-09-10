# -----------------------------------------------------------------------------
# Arquivo : scripts/backfill_monitor_activity_once.py
# Objetivo: Script de uso único para reconstruir e popular o histórico/estado de
#           atividade das equipes no Firestore, usando DDS executados, turno atual
#           e, opcionalmente, a coleção DDS como fontes de atividade.
#           Cria monitor de progresso em terminal e em monitor_backfill_jobs.
# -----------------------------------------------------------------------------

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
import traceback
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

# Permite rodar com:
#   python scripts/backfill_monitor_activity_once.py
# a partir da raiz do dds-webtools.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_query import FieldFilter
except Exception as exc:
    print("[ERRO] Dependências Google não encontradas.")
    print("       Instale/valide requirements.txt antes de rodar este script.")
    print(f"       Detalhe: {exc}")
    raise


DEFAULT_EMPRESA = os.getenv("DDS_EMPRESA_PADRAO", "ChicoEletro")
DEFAULT_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT") or "dds-treinamentos"
DEFAULT_TZ = os.getenv("DDS_TIMEZONE", "America/Sao_Paulo")

DDS_TEAMS_COLLECTION = os.getenv("DDS_TEAMS_COLLECTION", "dds_teams")
DDS_COLLECTION = os.getenv("DDS_COLLECTION_NAME", "DDS")
DDS_TRAINING_EXEC_COLLECTION = os.getenv("DDS_TRAINING_EXEC_COLLECTION", "dds_training_exec")
WEBTOOLS_ROOT_COLLECTION = os.getenv("WEBTOOLS_ROOT_COLLECTION", "webtools")
WEBTOOLS_MONITOR_DOC = os.getenv("WEBTOOLS_MONITOR_DOC", "monitor")
MONITOR_ACTIVITY_EVENTS_SUBCOLLECTION = os.getenv("MONITOR_ACTIVITY_EVENTS_SUBCOLLECTION", "activity_events")
MONITOR_ACTIVITY_STATE_SUBCOLLECTION = os.getenv("MONITOR_ACTIVITY_STATE_SUBCOLLECTION", "activity_state")
MONITOR_ACTIVITY_FEED_SUBCOLLECTION = os.getenv("MONITOR_ACTIVITY_FEED_SUBCOLLECTION", "activity_feed")
MONITOR_BACKFILL_JOBS_SUBCOLLECTION = os.getenv("MONITOR_BACKFILL_JOBS_SUBCOLLECTION", "backfill_jobs")

BATCH_LIMIT = 400


@dataclass
class TeamRecord:
    team_key: str
    equipe: str
    active: bool
    team_data: dict[str, Any] = field(default_factory=dict)
    turno_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActivityEvent:
    team_key: str
    equipe: str
    empresa: str
    source: str
    activity_at: datetime
    event_ref: str | None = None
    title: str | None = None
    active_after_event: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def event_id(self) -> str:
        base = "|".join(
            [
                self.empresa,
                self.team_key,
                self.source,
                self.activity_at.isoformat(),
                self.event_ref or "",
                self.title or "",
            ]
        )
        digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
        safe_team = re.sub(r"[^A-Z0-9_\-]", "_", normalize_text(self.team_key) or "UNKNOWN")
        safe_source = re.sub(r"[^a-z0-9_\-]", "_", str(self.source or "unknown").lower())
        return f"{self.activity_at.strftime('%Y%m%dT%H%M%S%f')}_{safe_team}_{safe_source}_{digest}"

    @property
    def activity_day(self) -> str:
        return local_day_key(self.activity_at)



def webtools_monitor_ref(db):
    return db.collection(WEBTOOLS_ROOT_COLLECTION).document(WEBTOOLS_MONITOR_DOC)


def monitor_subcollection(db, name: str):
    return webtools_monitor_ref(db).collection(name)


def event_label(source: str, extra: dict[str, Any] | None = None) -> str:
    extra = extra or {}
    source_key = str(source or "").lower()
    estado = normalize_text(extra.get("estado")) if extra.get("estado") else ""
    if source_key == "dds":
        return "Execução de DDS"
    if source_key == "turno":
        if estado == "ABERTO":
            return "Abertura de turno"
        if estado == "FECHADO":
            return "Fechamento de turno"
        if estado == "INTERVALO":
            return "Início de intervalo"
        if estado == "DESLOCAMENTO_ESPECIAL":
            return "Deslocamento especial"
        return "Alteração de turno"
    if source_key == "mensagem":
        return "Mensagem enviada"
    return str(source or "Atividade")


def feed_item_from_event(event: ActivityEvent) -> dict[str, Any]:
    local_dt = event.activity_at.astimezone(get_tz())
    return {
        "eventId": event.event_id,
        "empresa": event.empresa,
        "teamKey": event.team_key,
        "equipe": event.equipe,
        "source": event.source,
        "label": event_label(event.source, event.extra),
        "time": local_dt.strftime("%H:%M"),
        "activityAt": event.activity_at.isoformat(),
    }


def write_activity_feed(db, *, empresa: str, events: list[ActivityEvent], commit: bool) -> None:
    if not events:
        return
    items = [feed_item_from_event(ev) for ev in sorted(events, key=lambda ev: ev.activity_at, reverse=True)[:5]]
    if not commit:
        return
    monitor_subcollection(db, MONITOR_ACTIVITY_FEED_SUBCOLLECTION).document(empresa).set(
        {"empresa": empresa, "items": items, "updatedAt": firestore.SERVER_TIMESTAMP, "backfilled": True},
        merge=True,
    )


class FirestoreBatchWriter:
    def __init__(self, db, commit: bool):
        self.db = db
        self.commit_enabled = commit
        self.batch = db.batch()
        self.pending = 0
        self.total_writes = 0
        self.total_commits = 0

    def set(self, ref, payload: dict[str, Any], *, merge: bool = True) -> None:
        if not self.commit_enabled:
            self.total_writes += 1
            return

        self.batch.set(ref, payload, merge=merge)
        self.pending += 1
        self.total_writes += 1
        if self.pending >= BATCH_LIMIT:
            self.commit()

    def commit(self) -> None:
        if not self.commit_enabled:
            self.pending = 0
            return
        if self.pending <= 0:
            return
        self.batch.commit()
        self.total_commits += 1
        self.batch = self.db.batch()
        self.pending = 0


class ProgressMonitor:
    def __init__(self, *, db, job_ref, total: int, commit: bool, update_every: int = 10):
        self.db = db
        self.job_ref = job_ref
        self.total = max(0, total)
        self.commit = commit
        self.update_every = max(1, update_every)
        self.started = time.time()
        self.last_print_len = 0
        self.processed = 0
        self.events_found = 0
        self.events_written = 0
        self.state_written = 0
        self.teams_reactivated = 0
        self.errors = 0

    def start(self, params: dict[str, Any]) -> None:
        print("=" * 90)
        print("BACKFILL MONITOR ACTIVITY - USO ÚNICO")
        print("=" * 90)
        print(f"Modo       : {'GRAVAÇÃO REAL (--commit)' if self.commit else 'SIMULAÇÃO / DRY-RUN'}")
        print(f"Equipes    : {self.total}")
        print(f"Job ID     : {self.job_ref.id if self.job_ref else '-'}")
        print(f"Parâmetros : {json.dumps(params, ensure_ascii=False, default=str)}")
        print("-" * 90)
        self._update_job_doc(status="running", extra={"params": params})

    def update(
        self,
        *,
        team_key: str,
        active_before: bool | None,
        latest_source: str | None,
        latest_at: datetime | None,
        team_events: int,
        writes_added: int,
        reactivated: bool,
        state_updated: bool = False,
        error: bool = False,
        force: bool = False,
    ) -> None:
        self.processed += 1
        self.events_found += team_events
        self.events_written += writes_added
        if reactivated:
            self.teams_reactivated += 1
        if state_updated:
            self.state_written += 1
        if error:
            self.errors += 1

        elapsed = max(0.001, time.time() - self.started)
        rate = self.processed / elapsed
        remaining = max(0, self.total - self.processed)
        eta = remaining / rate if rate > 0 else 0
        pct = (self.processed / self.total * 100) if self.total else 100.0

        latest_str = "-"
        if latest_at:
            latest_str = format_local_dt(latest_at)

        line = (
            f"[{self.processed:>5}/{self.total:<5} {pct:>6.2f}%] "
            f"{team_key:<12} "
            f"active={str(active_before):<5} "
            f"eventos={team_events:<3} "
            f"latest={str(latest_source or '-'):<8} {latest_str:<16} "
            f"reativou={'sim' if reactivated else 'não':<3} "
            f"ETA={format_duration(eta)}"
        )

        # Linha dinâmica no terminal.
        print("\r" + line + " " * max(0, self.last_print_len - len(line)), end="", flush=True)
        self.last_print_len = len(line)

        if force or self.processed % self.update_every == 0 or self.processed == self.total:
            print()
            self._update_job_doc(status="running")

    def finish(self, *, writer: FirestoreBatchWriter, status: str = "done", error_detail: str | None = None) -> None:
        elapsed = time.time() - self.started
        print()
        print("-" * 90)
        print(f"Status              : {status}")
        print(f"Tempo total         : {format_duration(elapsed)}")
        print(f"Equipes processadas : {self.processed}/{self.total}")
        print(f"Eventos encontrados : {self.events_found}")
        print(f"Writes estimados    : {writer.total_writes}")
        print(f"Commits Firestore   : {writer.total_commits}")
        print(f"Equipes reativadas  : {self.teams_reactivated}")
        print(f"Erros               : {self.errors}")
        if not self.commit:
            print()
            print("ATENÇÃO: este foi um DRY-RUN. Nada foi gravado no Firestore.")
            print("Para gravar de verdade, rode novamente com --commit.")
        print("=" * 90)
        self._update_job_doc(status=status, extra={"errorDetail": error_detail} if error_detail else None)

    def _update_job_doc(self, *, status: str, extra: dict[str, Any] | None = None) -> None:
        if not self.commit or self.job_ref is None:
            return

        pct = (self.processed / self.total * 100) if self.total else 100.0
        payload = {
            "status": status,
            "totalTeams": self.total,
            "processedTeams": self.processed,
            "progressPercent": round(pct, 2),
            "eventsFound": self.events_found,
            "eventsWritten": self.events_written,
            "stateWritten": self.state_written,
            "teamsReactivated": self.teams_reactivated,
            "errors": self.errors,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        }
        if self.processed == 0:
            payload["startedAt"] = firestore.SERVER_TIMESTAMP
        if status in {"done", "failed"}:
            payload["finishedAt"] = firestore.SERVER_TIMESTAMP
        if extra:
            payload.update(extra)
        try:
            self.job_ref.set(payload, merge=True)
        except Exception as exc:
            print(f"\n[WARN] Falha ao atualizar documento de progresso: {exc}")


def init_firestore(project_id: str | None, service_account: str | None, force_adc: bool = False):
    """Inicializa Firestore.

    Ordem:
    1. Tenta usar services.firestore_client.db do próprio projeto, se disponível.
    2. Usa firebase_admin com service account, se informado.
    3. Usa Application Default Credentials.

    Para login local via ADC:
        gcloud auth application-default login
        gcloud config set project dds-treinamentos
    """
    if not force_adc:
        try:
            from services.firestore_client import db as project_db  # type: ignore

            print("[auth] Usando services.firestore_client.db do projeto local.")
            return project_db
        except Exception as exc:
            print(f"[auth] Não foi possível usar services.firestore_client.db: {exc}")
            print("[auth] Tentando firebase_admin / Application Default Credentials...")

    import firebase_admin
    from firebase_admin import credentials, firestore as fb_firestore

    if not firebase_admin._apps:
        options = {"projectId": project_id} if project_id else None
        if service_account:
            print(f"[auth] Usando service account: {service_account}")
            cred = credentials.Certificate(service_account)
            firebase_admin.initialize_app(cred, options=options)
        else:
            print("[auth] Usando Application Default Credentials.")
            print("[auth] Se falhar, rode: gcloud auth application-default login")
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, options=options)

    return fb_firestore.client()


def normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_local_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def get_tz():
    if ZoneInfo:
        try:
            return ZoneInfo(DEFAULT_TZ)
        except Exception:
            pass
    return timezone(timedelta(hours=-3))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def today_local() -> date:
    return datetime.now(get_tz()).date()


def to_utc_dt(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, dt_time.min)
    elif hasattr(value, "to_datetime"):
        dt = value.to_datetime()
    else:
        text = str(value or "").strip()
        if not text:
            return None

        # Firestore console / strings comuns
        text = text.replace("Z", "+00:00")

        # Exemplos: "2026-05-20 14:33:30", "2026-05-20T14:33:30-03:00"
        try:
            dt = datetime.fromisoformat(text)
        except Exception:
            # Tenta extrair yyyy-mm-dd e hora hh:mm
            day_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
            time_match = re.search(r"\b(\d{1,2})[:hH](\d{2})(?::(\d{2}))?\b", text)
            if not day_match:
                return None

            local_tz = get_tz()
            hh = int(time_match.group(1)) if time_match else 12
            mm = int(time_match.group(2)) if time_match else 0
            ss = int(time_match.group(3)) if time_match and time_match.group(3) else 0
            try:
                dt = datetime.strptime(day_match.group(1), "%Y-%m-%d").replace(
                    hour=hh,
                    minute=mm,
                    second=ss,
                    microsecond=0,
                    tzinfo=local_tz,
                )
            except Exception:
                return None

    if dt.tzinfo is None:
        # Dados sem timezone são tratados como horário local do DDS.
        dt = dt.replace(tzinfo=get_tz())
    return dt.astimezone(timezone.utc)


def format_local_dt(value: datetime | None) -> str:
    if not value:
        return "-"
    return value.astimezone(get_tz()).strftime("%d/%m %H:%M")


def local_day_key(value: datetime | None) -> str:
    if not value:
        return today_local().strftime("%Y-%m-%d")
    return value.astimezone(get_tz()).strftime("%Y-%m-%d")


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def month_keys_between(start: date, end: date) -> list[str]:
    keys = []
    cursor = date(start.year, start.month, 1)
    end_month = date(end.year, end.month, 1)
    while cursor <= end_month:
        keys.append(f"{cursor.year:04d}-{cursor.month:02d}")
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return keys


def is_between(value: datetime, start: date, end: date) -> bool:
    local_d = value.astimezone(get_tz()).date()
    return start <= local_d <= end


def aliases_for_team(team: TeamRecord) -> set[str]:
    aliases = {
        normalize_text(team.team_key),
        normalize_text(team.equipe),
        normalize_text(team.team_data.get("teamKey")),
        normalize_text(team.team_data.get("displayName")),
        normalize_text(team.turno_data.get("equipe")),
    }
    return {a for a in aliases if a}


def alias_matches(value: Any, aliases: set[str]) -> bool:
    norm = normalize_text(value)
    if not norm:
        return False
    if norm in aliases:
        return True
    for alias in aliases:
        if not alias:
            continue
        token_re = rf"(?<![A-Z0-9]){re.escape(alias)}(?![A-Z0-9])"
        if re.search(token_re, norm):
            return True
    return False


def extract_training_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = (
        data.get("executedTrainings")
        or data.get("trainings")
        or data.get("items")
        or data.get("executions")
        or []
    )

    if isinstance(raw, dict):
        values = []
        for key, value in raw.items():
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("trainingId", key)
                values.append(item)
            else:
                values.append({"trainingId": key, "value": value})
        return values

    if isinstance(raw, list):
        out = []
        for idx, value in enumerate(raw):
            if isinstance(value, dict):
                out.append(dict(value))
            else:
                out.append({"index": idx, "value": value})
        return out

    return []


def extract_event_dt_from_training(item: dict[str, Any], doc_data: dict[str, Any]) -> datetime | None:
    for key in (
        "executedAt",
        "submittedAt",
        "sentAt",
        "serverUpdatedAt",
        "updatedAt",
        "createdAt",
        "timestamp",
        "completedAt",
        "finishedAt",
        "dataHora",
    ):
        dt = to_utc_dt(item.get(key))
        if dt:
            return dt

    for key in ("executedAt", "updatedAt", "serverUpdatedAt", "createdAt"):
        dt = to_utc_dt(doc_data.get(key))
        if dt:
            return dt

    # Caso haja trainingId/data/hora em string.
    for key in ("headerDate", "date", "dia", "trainingId"):
        day_raw = str(item.get(key) or "").strip()
        match = re.search(r"(\d{4}-\d{2}-\d{2})", day_raw)
        if match:
            day = match.group(1)
            hour = item.get("hora") or item.get("horaConclusao") or item.get("time")
            return to_utc_dt(f"{day} {hour}") if hour else to_utc_dt(f"{day} 12:00")

    return None


def get_title_from_training(item: dict[str, Any]) -> str | None:
    for key in ("title", "headerTitle", "tema", "trainingTitle", "nome", "assunto"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return None


def load_teams(db, empresa: str, only_team: str | None = None) -> list[TeamRecord]:
    teams: dict[str, TeamRecord] = {}

    for snap in db.collection(DDS_TEAMS_COLLECTION).stream():
        data = snap.to_dict() or {}
        team_key = str(data.get("teamKey") or snap.id).strip()
        if not team_key:
            continue
        if only_team and normalize_text(team_key) != normalize_text(only_team):
            continue

        equipe = str(data.get("displayName") or data.get("equipe") or team_key).strip()
        teams[team_key] = TeamRecord(
            team_key=team_key,
            equipe=equipe or team_key,
            active=bool(data.get("active", True)),
            team_data=data,
            turno_data={},
        )

    for snap in db.collection("turno").document(empresa).collection("equipes").stream():
        data = snap.to_dict() or {}
        team_key = snap.id
        if only_team and normalize_text(team_key) != normalize_text(only_team):
            continue

        existing = teams.get(team_key)
        if existing:
            existing.turno_data = data
            existing.equipe = str(existing.equipe or data.get("equipe") or team_key).strip()
        else:
            teams[team_key] = TeamRecord(
                team_key=team_key,
                equipe=str(data.get("equipe") or team_key).strip(),
                active=True,
                team_data={},
                turno_data=data,
            )

    return sorted(teams.values(), key=lambda t: (normalize_text(t.equipe), normalize_text(t.team_key)))


def collect_dds_exec_events(db, team: TeamRecord, empresa: str, start: date, end: date) -> list[ActivityEvent]:
    events: list[ActivityEvent] = []
    month_keys = month_keys_between(start, end)

    for month_key in month_keys:
        ref = (
            db.collection(DDS_TRAINING_EXEC_COLLECTION)
            .document(team.team_key)
            .collection("months")
            .document(month_key)
        )

        try:
            snap = ref.get()
        except Exception as exc:
            print(f"\n[WARN] Falha lendo {ref.path}: {exc}")
            continue

        if not snap.exists:
            continue

        doc_data = snap.to_dict() or {}
        trainings = extract_training_list(doc_data)

        # Alguns documentos podem trazer um único resumo no topo.
        if not trainings and (doc_data.get("executedAt") or doc_data.get("updatedAt")):
            trainings = [doc_data]

        for item in trainings:
            activity_at = extract_event_dt_from_training(item, doc_data)
            if not activity_at or not is_between(activity_at, start, end):
                continue

            title = get_title_from_training(item)
            event_ref = f"{ref.path}#{item.get('trainingId') or item.get('id') or item.get('index') or activity_at.isoformat()}"

            events.append(
                ActivityEvent(
                    team_key=team.team_key,
                    equipe=team.equipe,
                    empresa=empresa,
                    source="dds",
                    activity_at=activity_at,
                    event_ref=event_ref,
                    title=title,
                    active_after_event=True,
                    extra={
                        "month": month_key,
                        "trainingId": item.get("trainingId") or item.get("id"),
                        "trainingTitle": title,
                        "sourceCollection": DDS_TRAINING_EXEC_COLLECTION,
                    },
                )
            )

    return events


def collect_turno_event(db, team: TeamRecord, empresa: str, start: date, end: date, include_outside_range: bool) -> list[ActivityEvent]:
    data = dict(team.turno_data or {})
    if not data:
        return []

    activity_at = None
    for key in ("serverUpdatedAt", "updatedAt", "lastUpdateAt", "timestamp", "createdAt"):
        activity_at = to_utc_dt(data.get(key))
        if activity_at:
            break

    if not activity_at:
        return []

    if not include_outside_range and not is_between(activity_at, start, end):
        return []

    return [
        ActivityEvent(
            team_key=team.team_key,
            equipe=team.equipe,
            empresa=empresa,
            source="turno",
            activity_at=activity_at,
            event_ref=f"turno/{empresa}/equipes/{team.team_key}",
            active_after_event=True,
            extra={
                "estado": data.get("estado"),
                "nocSs": data.get("nocSs"),
                "motivo": data.get("lastMotivoOutro") or data.get("lastMotivo"),
            },
        )
    ]


def collect_dds_collection_events(db, team: TeamRecord, empresa: str, start: date, end: date) -> list[ActivityEvent]:
    """Fallback opcional lendo a coleção geral DDS.

    Atenção: pode custar mais leituras. Use só se precisar reconstruir algo que
    não esteja em dds_training_exec.
    """
    events: list[ActivityEvent] = []
    aliases = aliases_for_team(team)
    end_key = f"{end.strftime('%Y-%m-%d')}\uf8ff"

    try:
        query = (
            db.collection(DDS_COLLECTION)
            .where(filter=FieldFilter("headerDate", ">=", start.strftime("%Y-%m-%d")))
            .where(filter=FieldFilter("headerDate", "<=", end_key))
        )
        snaps = query.stream()
    except Exception as exc:
        print(f"\n[WARN] Falha consultando coleção {DDS_COLLECTION}: {exc}")
        return events

    for snap in snaps:
        data = snap.to_dict() or {}
        if not alias_matches(data.get("equipe") or data.get("teamName") or data.get("teamKey"), aliases):
            continue

        activity_at = None
        for key in (
            "executedAt",
            "submittedAt",
            "sentAt",
            "serverUpdatedAt",
            "updatedAt",
            "createdAt",
            "timestamp",
            "dataHora",
        ):
            activity_at = to_utc_dt(data.get(key))
            if activity_at:
                break

        if not activity_at:
            header_day = str(data.get("headerDate") or "").strip()[:10]
            if re.match(r"^\d{4}-\d{2}-\d{2}$", header_day):
                activity_at = to_utc_dt(f"{header_day} {data.get('hora') or '12:00'}")

        if not activity_at or not is_between(activity_at, start, end):
            continue

        events.append(
            ActivityEvent(
                team_key=team.team_key,
                equipe=team.equipe,
                empresa=empresa,
                source="dds",
                activity_at=activity_at,
                event_ref=snap.reference.path,
                title=data.get("headerTitle") or data.get("tema"),
                active_after_event=True,
                extra={
                    "headerDate": data.get("headerDate"),
                    "headerTitle": data.get("headerTitle"),
                    "sourceCollection": DDS_COLLECTION,
                },
            )
        )

    return events


def dedupe_events(events: list[ActivityEvent]) -> list[ActivityEvent]:
    seen = set()
    out = []
    for ev in sorted(events, key=lambda e: (e.activity_at, e.source, e.event_ref or "")):
        key = (ev.team_key, ev.source, ev.activity_at.isoformat(), ev.event_ref or ev.title or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
    return out


def choose_latest_event(events: list[ActivityEvent]) -> ActivityEvent | None:
    if not events:
        return None
    return max(events, key=lambda ev: ev.activity_at)


def should_reactivate_team(team: TeamRecord, latest: ActivityEvent | None, reactivate_days: int, respect_manual_inactive: bool) -> bool:
    if not latest:
        return False

    cutoff = now_utc() - timedelta(days=reactivate_days)
    if latest.activity_at < cutoff:
        return False

    if respect_manual_inactive:
        reason = team.team_data.get("autoInactiveReason")
        inactive_at = to_utc_dt(team.team_data.get("autoInactiveAt"))
        if reason == "MANUAL" and inactive_at and inactive_at > latest.activity_at:
            return False

    return True


def write_event(writer: FirestoreBatchWriter, event: ActivityEvent) -> None:
    event_ref = (
        monitor_subcollection(writer.db, MONITOR_ACTIVITY_EVENTS_SUBCOLLECTION)
        .document(event.activity_day)
        .collection("events")
        .document(event.event_id)
    )

    payload = {
        "eventId": event.event_id,
        "empresa": event.empresa,
        "teamKey": event.team_key,
        "equipe": event.equipe,
        "source": event.source,
        "label": event_label(event.source, event.extra),
        "time": event.activity_at.astimezone(get_tz()).strftime("%H:%M"),
        "activityAt": event.activity_at,
        "activityDay": event.activity_day,
        "eventRef": event.event_ref,
        "title": event.title,
        "activeAfterEvent": event.active_after_event,
        "receivedAt": firestore.SERVER_TIMESTAMP,
        "backfilled": True,
    }
    payload.update({k: v for k, v in event.extra.items() if v is not None})
    writer.set(event_ref, payload, merge=True)


def write_state_and_team(
    writer: FirestoreBatchWriter,
    *,
    team: TeamRecord,
    latest: ActivityEvent | None,
    active_after: bool,
    update_dds_teams: bool,
) -> None:
    if not latest:
        return

    state_id = f"{latest.empresa}_{team.team_key}"
    state_ref = monitor_subcollection(writer.db, MONITOR_ACTIVITY_STATE_SUBCOLLECTION).document(state_id)
    state_payload = {
        "empresa": latest.empresa,
        "teamKey": team.team_key,
        "equipe": team.equipe,
        "active": active_after,
        "lastActivityAt": latest.activity_at,
        "lastActivitySource": latest.source,
        "lastEventId": latest.event_id,
        "lastEventRef": latest.event_ref,
        "updatedAt": firestore.SERVER_TIMESTAMP,
        "backfilled": True,
    }
    writer.set(state_ref, state_payload, merge=True)

    if not update_dds_teams:
        return

    team_ref = writer.db.collection(DDS_TEAMS_COLLECTION).document(team.team_key)
    team_payload = {
        "lastActivityAt": latest.activity_at,
        "lastActivitySource": latest.source,
        "lastActivityEventId": latest.event_id,
        "lastActivityEventRef": latest.event_ref,
        "updatedAt": firestore.SERVER_TIMESTAMP,
        "backfilledActivityAt": firestore.SERVER_TIMESTAMP,
    }

    if active_after:
        team_payload.update(
            {
                "active": True,
                "autoInactiveReason": firestore.DELETE_FIELD,
                "autoInactiveAt": firestore.DELETE_FIELD,
                "autoReactivatedAt": firestore.SERVER_TIMESTAMP,
                "autoInactiveLastSeenUpdatedAt": latest.activity_at,
            }
        )

    writer.set(team_ref, team_payload, merge=True)


def process_team(
    db,
    writer: FirestoreBatchWriter,
    *,
    team: TeamRecord,
    empresa: str,
    start: date,
    end: date,
    sources: set[str],
    include_turno_outside_range: bool,
    update_dds_teams: bool,
    reactivate_days: int,
    respect_manual_inactive: bool,
) -> tuple[int, ActivityEvent | None, bool, int]:
    events: list[ActivityEvent] = []

    if "dds_exec" in sources:
        events.extend(collect_dds_exec_events(db, team, empresa, start, end))

    if "turno" in sources:
        events.extend(collect_turno_event(db, team, empresa, start, end, include_turno_outside_range))

    if "dds_collection" in sources:
        events.extend(collect_dds_collection_events(db, team, empresa, start, end))

    # Futuro: mensagens_comunicacao pode ser incluído aqui, mas não é default
    # porque pode gerar muitas leituras sem índice específico por equipe.

    events = dedupe_events(events)
    latest = choose_latest_event(events)

    reactivated = should_reactivate_team(
        team,
        latest,
        reactivate_days=reactivate_days,
        respect_manual_inactive=respect_manual_inactive,
    )

    active_after = bool(team.active or reactivated)

    writes_before = writer.total_writes
    for ev in events:
        ev.active_after_event = active_after if ev == latest else ev.active_after_event
        write_event(writer, ev)

    if latest:
        write_state_and_team(
            writer,
            team=team,
            latest=latest,
            active_after=active_after,
            update_dds_teams=update_dds_teams,
        )

    writes_added = writer.total_writes - writes_before
    return len(events), latest, reactivated, writes_added


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill de atividade das equipes do monitor no Firestore.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT_ID, help="ID do projeto Firebase/GCP.")
    parser.add_argument("--service-account", default=None, help="Caminho para JSON de service account. Se omitido, usa ADC.")
    parser.add_argument("--force-adc", action="store_true", help="Ignora services.firestore_client e força firebase_admin/ADC.")
    parser.add_argument("--empresa", default=DEFAULT_EMPRESA, help="Empresa/documento em turno/{empresa}.")
    parser.add_argument("--start", default=(today_local() - timedelta(days=60)).strftime("%Y-%m-%d"), help="Data inicial YYYY-MM-DD.")
    parser.add_argument("--end", default=today_local().strftime("%Y-%m-%d"), help="Data final YYYY-MM-DD.")
    parser.add_argument("--team", default=None, help="Processa apenas uma equipe, ex.: E3X93.")
    parser.add_argument(
        "--sources",
        default="dds_exec,turno",
        help="Fontes: dds_exec,turno,dds_collection. Separe por vírgula.",
    )
    parser.add_argument("--include-turno-outside-range", action="store_true", default=True, help="Inclui turno atual mesmo fora do período.")
    parser.add_argument("--no-include-turno-outside-range", dest="include_turno_outside_range", action="store_false")
    parser.add_argument("--update-dds-teams", action="store_true", default=True, help="Atualiza dds_teams/{teamKey}.")
    parser.add_argument("--no-update-dds-teams", dest="update_dds_teams", action="store_false")
    parser.add_argument("--reactivate-days", type=int, default=7, help="Reativa se a última atividade estiver dentro dos últimos N dias.")
    parser.add_argument("--respect-manual-inactive", action="store_true", default=True, help="Mantém inativação manual se ela for posterior à atividade.")
    parser.add_argument("--ignore-manual-inactive", dest="respect_manual_inactive", action="store_false")
    parser.add_argument("--commit", action="store_true", help="Grava no Firestore. Sem isso, roda em simulação.")
    parser.add_argument("--job-id", default=None, help="ID do documento em monitor_backfill_jobs. Se omitido, gera automaticamente.")
    parser.add_argument("--progress-every", type=int, default=10, help="Atualiza documento/linha de progresso a cada N equipes.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    start = parse_local_date(args.start)
    end = parse_local_date(args.end)
    if end < start:
        raise SystemExit("--end não pode ser menor que --start")

    sources = {s.strip() for s in str(args.sources or "").split(",") if s.strip()}
    allowed_sources = {"dds_exec", "turno", "dds_collection"}
    unknown = sources - allowed_sources
    if unknown:
        raise SystemExit(f"Fonte(s) inválida(s): {sorted(unknown)}. Permitidas: {sorted(allowed_sources)}")

    db = init_firestore(args.project, args.service_account, force_adc=args.force_adc)

    print("[load] Buscando equipes em dds_teams e turno/{empresa}/equipes...")
    teams = load_teams(db, args.empresa, only_team=args.team)
    if not teams:
        print("[AVISO] Nenhuma equipe encontrada.")
        return 0

    job_id = args.job_id or f"backfill_{datetime.now(get_tz()).strftime('%Y%m%d_%H%M%S')}"
    job_ref = monitor_subcollection(db, MONITOR_BACKFILL_JOBS_SUBCOLLECTION).document(job_id)

    writer = FirestoreBatchWriter(db, commit=args.commit)
    progress = ProgressMonitor(db=db, job_ref=job_ref, total=len(teams), commit=args.commit, update_every=args.progress_every)

    params = {
        "project": args.project,
        "empresa": args.empresa,
        "start": args.start,
        "end": args.end,
        "team": args.team,
        "sources": sorted(sources),
        "includeTurnoOutsideRange": args.include_turno_outside_range,
        "updateDdsTeams": args.update_dds_teams,
        "reactivateDays": args.reactivate_days,
        "respectManualInactive": args.respect_manual_inactive,
        "commit": args.commit,
    }
    progress.start(params)

    latest_events_for_feed: list[ActivityEvent] = []

    try:
        for team in teams:
            try:
                team_events, latest, reactivated, writes_added = process_team(
                    db,
                    writer,
                    team=team,
                    empresa=args.empresa,
                    start=start,
                    end=end,
                    sources=sources,
                    include_turno_outside_range=args.include_turno_outside_range,
                    update_dds_teams=args.update_dds_teams,
                    reactivate_days=args.reactivate_days,
                    respect_manual_inactive=args.respect_manual_inactive,
                )

                if latest:
                    latest_events_for_feed.append(latest)

                progress.update(
                    team_key=team.team_key,
                    active_before=team.active,
                    latest_source=latest.source if latest else None,
                    latest_at=latest.activity_at if latest else None,
                    team_events=team_events,
                    writes_added=writes_added,
                    reactivated=reactivated,
                    state_updated=latest is not None,
                )
            except KeyboardInterrupt:
                raise
            except Exception:
                print()
                print(f"[ERRO] Falha processando equipe {team.team_key}:")
                print(traceback.format_exc())
                if latest:
                    latest_events_for_feed.append(latest)

                progress.update(
                    team_key=team.team_key,
                    active_before=team.active,
                    latest_source=None,
                    latest_at=None,
                    team_events=0,
                    writes_added=0,
                    reactivated=False,
                    state_updated=False,
                    error=True,
                    force=True,
                )

        writer.commit()
        write_activity_feed(db, empresa=args.empresa, events=latest_events_for_feed, commit=args.commit)
        progress.finish(writer=writer, status="done")
        return 0
    except KeyboardInterrupt:
        writer.commit()
        progress.finish(writer=writer, status="failed", error_detail="Interrompido pelo usuário.")
        return 130
    except Exception as exc:
        writer.commit()
        progress.finish(writer=writer, status="failed", error_detail=str(exc))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
