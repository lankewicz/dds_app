# -----------------------------------------------------------------------------
# Arquivo : services/turnos_service.py
# Objetivo: Consolidar a leitura do monitor web, cruzando turno/{empresa}/equipes
#           com dds_teams/{teamKey}, e aplicar as regras de alerta e filtro de
#           equipes ativas/inativas.
#           Também cruza a coleção DDS do app para montar o histórico visual
# -----------------------------------------------------------------------------

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from google.cloud import firestore, storage
from google.cloud.firestore_v1.base_query import FieldFilter
from services.firestore_client import db
from services.teams_service import list_teams_map
from services.monitor_config_service import get_monitor_polling_seconds, get_monitor_rules
from services.messaging_service import get_unread_counts, get_all_unread_counts_map, get_last_messages_map, CURRENT_SETOR
from concurrent.futures import ThreadPoolExecutor
import threading

_pending_lock = threading.Lock()

APP_TITLE = "DDS - Monitor de Turnos"
DEFAULT_EMPRESA = os.getenv("DDS_EMPRESA_PADRAO", "ChicoEletro")

POLLING_DEFAULT_SEC = int(os.getenv("DDS_POLLING_SEGUNDOS", "600"))
DDS_HISTORY_DAYS = int(os.getenv("DDS_HISTORY_DAYS", "20"))
DDS_COLLECTION = os.getenv("DDS_COLLECTION_NAME", "DDS")
DDS_TIMEZONE = os.getenv("DDS_TIMEZONE", "America/Sao_Paulo")
DDS_MUTABLE_REFRESH_SEC = int(os.getenv("DDS_MUTABLE_REFRESH_SEC", "1800"))
DDS_LAST_BUSINESS_REFRESH_SEC = int(os.getenv("DDS_LAST_BUSINESS_REFRESH_SEC", "3600"))
DDS_BUCKET_NAME = os.getenv("DDS_BUCKET_NAME", "dds-treinamentos.firebasestorage.app")
DDS_CALENDAR_SOURCE_BLOB = os.getenv("DDS_CALENDAR_SOURCE_BLOB", "DDSv2/lista.json")
DDS_CALENDAR_CACHE_BLOB = os.getenv("DDS_CALENDAR_CACHE_BLOB", "_cache/dds_calendar_history.json")
DDS_DAY_CACHE_PREFIX = os.getenv("DDS_DAY_CACHE_PREFIX", "_cache/days")
MONITOR_VIEW_CACHE_PREFIX = os.getenv("MONITOR_VIEW_CACHE_PREFIX", "_cache/monitor")
MONITOR_VIEW_CACHE_TTL_SEC = int(os.getenv("MONITOR_VIEW_CACHE_TTL_SEC", "86400"))
WEBTOOLS_ROOT_COLLECTION = os.getenv("WEBTOOLS_ROOT_COLLECTION", "webtools")
WEBTOOLS_MONITOR_DOC = os.getenv("WEBTOOLS_MONITOR_DOC", "monitor")
AUTO_CLOSE_OPEN_HOURS_DEFAULT = int(os.getenv("DDS_AUTO_CLOSE_OPEN_HOURS", "16"))
AUTO_DESATUALIZA_FECHADO_HOURS_DEFAULT = int(os.getenv("DDS_AUTO_DESATUALIZA_FECHADO_HOURS", "48"))
AUTO_DESATUALIZA_INTERVALO_HOURS_DEFAULT = int(os.getenv("DDS_AUTO_DESATUALIZA_INTERVALO_HOURS", "8"))

AUTO_REASON_CLOSE_OPEN = "AUTO_CLOSE_OPEN_TIMEOUT"
AUTO_REASON_DESAT_FECHADO = "AUTO_DESATUALIZADO_FECHADO_TIMEOUT"
AUTO_REASON_DESAT_DESLOCAMENTO = "AUTO_DESATUALIZADO_DESLOCAMENTO_TIMEOUT"
AUTO_REASON_DESAT_INTERVALO = "AUTO_DESATUALIZADO_INTERVALO_TIMEOUT"
AUTO_REASON_INACTIVE_UNKNOWN = "AUTO_INACTIVE_DESCONHECIDO"

_DDS_DAY_CACHE: dict[str, dict[str, Any]] = {}
_DDS_CALENDAR_CACHE: dict[str, Any] = {}
_STORAGE_CLIENT = None
# In-process cache da visão completa do monitor (por empresa)
_MONITOR_VIEW_CACHE: dict[str, dict[str, Any]] = {}
_cache_lock = threading.Lock()


def get_monitor_config() -> dict[str, Any]:
    rules = get_monitor_rules()
    polling_seconds = get_monitor_polling_seconds()
    return {
        "defaultEmpresa": DEFAULT_EMPRESA,
        "pollingSeconds": polling_seconds or POLLING_DEFAULT_SEC,
        "rules": rules,
    }


def clear_all_monitor_caches():
    """Limpa todos os caches em memória do monitor."""
    global _DDS_DAY_CACHE, _DDS_CALENDAR_CACHE, _MONITOR_VIEW_CACHE
    with _cache_lock:
        _DDS_DAY_CACHE.clear()
        _DDS_CALENDAR_CACHE.clear()
        _MONITOR_VIEW_CACHE.clear()

    # Limpa cache do Storage (DDS Calendar)
    _DDS_CALENDAR_CACHE.pop("payload", None)

    # Também limpa o cache de equipes se existir no outro serviço
    try:
        from services.teams_service import clear_teams_cache
        clear_teams_cache()
    except ImportError:
        pass


def update_productivity_metadata(empresa: str = DEFAULT_EMPRESA):
    """
    Atualiza o documento de metadados da produtividade com a \u00faltima compet\u00eancia 
    e listas de filtros dispon\u00edveis (cidades, bases, etc).
    """
    try:
        from produtividade.services.productivity_service import get_latest_competence, list_productivity_data
        
        # 1. Busca a \u00faltima compet\u00eancia usando o m\u00e9todo de varredura (por enquanto)
        year, month = get_latest_competence()
        if not year or not month:
            return

        competencia = f"{year}-{month:02d}"
        
        # 2. Busca todos os dados apenas daquela compet\u00eancia para extrair metadados geogr\u00e1ficos
        data_latest = list_productivity_data(year=year, month=month)
        
        cities = sorted(list(set(d.get("cityBase") for d in data_latest if d.get("cityBase"))))
        bases = sorted(list(set(d.get("base") for d in data_latest if d.get("base"))))
        agencies = sorted(list(set(d.get("agency") for d in data_latest if d.get("agency"))))

        # 3. Salva no documento 'meta' da produtividade
        db.collection("webtools").document("producao_mensal").collection("metadata").document(empresa).set({
            "lastCompetencia": competencia,
            "lastYear": year,
            "lastMonth": month,
            "availableCities": cities,
            "availableBases": bases,
            "availableAgencies": agencies,
            "updatedAt": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
    except Exception as e:
        print(f"[update_productivity_metadata] Erro: {e}")


def to_utc_dt(ts: Any):
    if not ts:
        return None

    if hasattr(ts, "to_datetime"):
        dt = ts.to_datetime()
    elif isinstance(ts, datetime):
        dt = ts
    elif isinstance(ts, str):
        text = ts.strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            parsed_dt = None
            for fmt in (
                "%d-%m-%Y - %H:%M",
                "%d-%m-%Y %H:%M:%S",
                "%d-%m-%Y %H:%M",
                "%d/%m/%Y - %H:%M",
                "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
            ):
                try:
                    parsed_dt = datetime.strptime(text, fmt)
                    break
                except Exception:
                    continue
            if parsed_dt is not None:
                dt = parsed_dt
            else:
                return None
    else:
        return None

    if getattr(dt, "tzinfo", None) is None:
        try:
            tz = ZoneInfo(DDS_TIMEZONE)
        except Exception:
            tz = timezone(timedelta(hours=-3))
        dt = dt.replace(tzinfo=tz).astimezone(timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt

def _get_now() -> datetime:
    try:
        return datetime.now(ZoneInfo(DDS_TIMEZONE))
    except Exception:
        # Fallback manual para UTC-3 se ZoneInfo falhar
        return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3)))


def normalize_estado(value: str | None) -> str:
    raw = (value or "DESCONHECIDO").strip().upper()
    aliases = {
        "ESPECIAL": "DESLOCAMENTO_ESPECIAL",
        "DESLOCAMENTO": "DESLOCAMENTO_ESPECIAL",
    }
    return aliases.get(raw, raw)


def string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []

    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if item is None:
            continue
        name = str(item).strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def extract_participantes(data: dict[str, Any]) -> list[str]:
    participants = string_list(data.get("membersSnapshot"))
    if participants:
        return participants

    for key in ("members", "eletricistas", "participantes"):
        participants = string_list(data.get(key))
        if participants:
            return participants

    return []


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _storage_client() -> storage.Client:
    global _STORAGE_CLIENT
    if _STORAGE_CLIENT is None:
        _STORAGE_CLIENT = storage.Client()
        try:
            from requests.adapters import HTTPAdapter
            adapter = HTTPAdapter(pool_connections=60, pool_maxsize=60)
            _STORAGE_CLIENT._http.mount("https://", adapter)
            _STORAGE_CLIENT._http._auth_request.session.mount("https://", adapter)
        except Exception:
            pass
    return _STORAGE_CLIENT


def _storage_bucket():
    return _storage_client().bucket(DDS_BUCKET_NAME)


def _storage_blob_name(*parts: str) -> str:
    clean = [str(part or "").strip("/") for part in parts if str(part or "").strip("/")]
    return "/".join(clean)


def _storage_read_json(blob_name: str) -> dict[str, Any] | None:
    try:
        blob = _storage_bucket().blob(blob_name)
        raw = blob.download_as_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _storage_write_json(blob_name: str, payload: dict[str, Any]) -> None:
    try:
        blob = _storage_bucket().blob(blob_name)
        blob.upload_from_string(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            content_type="application/json; charset=utf-8",
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Cache da visão completa do monitor (_cache/monitor/{empresa}/current_view.json)
# ---------------------------------------------------------------------------

def _monitor_view_cache_blob(empresa: str) -> str:
    safe = re.sub(r"[^\w\-]", "_", empresa)
    return _storage_blob_name(MONITOR_VIEW_CACHE_PREFIX, safe, "current_view.json")


class _DatetimeEncoder(json.JSONEncoder):
    """Serializa datetime/set que o json padrão não suporta."""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, set):
            return sorted(obj)
        return super().default(obj)


def _read_monitor_view_cache(empresa: str) -> dict[str, Any] | None:
    """
    Lê o cache da visão completa do monitor. Retorna None se:
    - Não encontrado
    - Expirado (MONITOR_VIEW_CACHE_TTL_SEC)
    """
    # 1. Cache em memória (mais rápido — evita round-trip ao Storage)
    with _cache_lock:
        mem = _MONITOR_VIEW_CACHE.get(empresa)
    if mem:
        cached_at_str = mem.get("_cachedAt")
        if cached_at_str:
            try:
                cached_at = datetime.fromisoformat(cached_at_str)
                if cached_at.tzinfo is None:
                    cached_at = cached_at.replace(tzinfo=timezone.utc)
                age = (_utc_now() - cached_at).total_seconds()
                if age < MONITOR_VIEW_CACHE_TTL_SEC:
                    return mem
            except Exception:
                pass

    # 2. Storage (Cloud Run reiniciado ou outra instância)
    blob_name = _monitor_view_cache_blob(empresa)
    raw = _storage_read_json(blob_name)
    if not raw:
        return None

    cached_at_str = raw.get("_cachedAt")
    if not cached_at_str:
        return None
    try:
        cached_at = datetime.fromisoformat(cached_at_str)
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=timezone.utc)
        age = (_utc_now() - cached_at).total_seconds()
        if age >= MONITOR_VIEW_CACHE_TTL_SEC:
            return None
    except Exception:
        return None

    with _cache_lock:
        _MONITOR_VIEW_CACHE[empresa] = raw
    return raw


def _write_monitor_view_cache(empresa: str, payload: dict[str, Any]) -> None:
    """Persiste a visão completa no cache em memória e no Storage."""
    stamped = {**payload, "_cachedAt": _utc_now_iso()}
    with _cache_lock:
        _MONITOR_VIEW_CACHE[empresa] = stamped
    try:
        blob_name = _monitor_view_cache_blob(empresa)
        blob = _storage_bucket().blob(blob_name)
        blob.upload_from_string(
            json.dumps(stamped, ensure_ascii=False, cls=_DatetimeEncoder),
            content_type="application/json; charset=utf-8",
        )
    except Exception:
        pass  # Falha no Storage não impede a resposta; o cache em memória ainda funciona


def _invalidate_monitor_view_cache(empresa: str) -> None:
    """Invalida o cache — chamado antes de um recálculo forçado."""
    with _cache_lock:
        _MONITOR_VIEW_CACHE.pop(empresa, None)
    try:
        blob_name = _monitor_view_cache_blob(empresa)
        _storage_bucket().blob(blob_name).delete()
    except Exception:
        pass


def _patch_monitor_view_cache(empresa: str, team_item: dict[str, Any]) -> None:
    """
    Atualiza apenas UMA equipe dentro do cache existente, evitando um recálculo total.
    Se o cache não existir, não faz nada (o próximo GET criará o cache completo).
    """
    cache = _read_monitor_view_cache(empresa)
    if not cache:
        return

    items = cache.get("items") or []
    team_key = team_item.get("teamKey")
    
    # Substitui ou adiciona o item
    found = False
    new_items = []
    for it in items:
        if it.get("teamKey") == team_key:
            new_items.append(team_item)
            found = True
        else:
            new_items.append(it)
    
    if not found:
        new_items.append(team_item)
        # Mantém a ordenação por nome da equipe
        new_items.sort(key=lambda x: (str(x.get("equipe") or ""), str(x.get("teamKey") or "")))

    # Atualiza o timestamp do cache para não expirar imediatamente por idade
    # (damos uma sobrevida ao cache pois ele acabou de ser 'refrescado' com um dado novo)
    updated_cache = {
        **cache,
        "items": new_items,
        "serverTime": _utc_now_iso(),
        "_cachedAt": _utc_now_iso(),
        "manualRefresh": False
    }
    
    with _cache_lock:
        _MONITOR_VIEW_CACHE[empresa] = updated_cache
    try:
        blob_name = _monitor_view_cache_blob(empresa)
        blob = _storage_bucket().blob(blob_name)
        blob.upload_from_string(
            json.dumps(updated_cache, ensure_ascii=False, cls=_DatetimeEncoder),
            content_type="application/json; charset=utf-8",
        )
    except Exception:
        pass



def get_team_dds_data(empresa: str, team_key: str) -> dict[str, Any]:
    """
    Retorna ddsHistory, ddsDays, ddsTimes e ddsPhotos para uma equipe específica,
    buscando do cache do monitor. Usado pelo team_form_service para enriquecer
    a resposta do /api/team-form com dados de presença no DDS.
    """
    cache = _read_monitor_view_cache(empresa)
    if cache:
        items = cache.get("items") or []
        for it in items:
            if it.get("teamKey") == team_key:
                return {
                    "ddsHistory": it.get("ddsHistory") or [],
                    "ddsDays": it.get("ddsDays") or [],
                    "ddsTimes": it.get("ddsTimes") or {},
                    "ddsPhotos": it.get("ddsPhotos") or {},
                    "ddsToday": it.get("ddsToday") or "neutral",
                }
    return {"ddsHistory": [], "ddsDays": [], "ddsTimes": {}, "ddsPhotos": {}, "ddsToday": "neutral"}


def _parse_iso_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return to_utc_dt(value)
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _local_today() -> datetime.date:
    return _get_now().date()


def _recent_history_days(days: int = DDS_HISTORY_DAYS) -> list[str]:
    today = _local_today()
    return [
        (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(days - 1, -1, -1)
    ]


def _last_business_day(ref_day: datetime.date) -> datetime.date:
    day = ref_day - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _mutable_dds_days(recent_days: list[str]) -> set[str]:
    today = _local_today()
    today_key = today.strftime("%Y-%m-%d")
    last_business_key = _last_business_day(today).strftime("%Y-%m-%d")
    return {day for day in recent_days if day in {today_key, last_business_key}}


def _prune_dds_day_cache(valid_days: set[str]) -> None:
    with _cache_lock:
        stale_days = [day for day in _DDS_DAY_CACHE.keys() if day not in valid_days]
        for day in stale_days:
            _DDS_DAY_CACHE.pop(day, None)


def _should_refresh_dds_day(day: str, mutable_days: set[str]) -> bool:
    with _cache_lock:
        entry = _DDS_DAY_CACHE.get(day)
    if entry is None:
        return True

    if entry.get("frozen"):
        return False

    if day not in mutable_days:
        return False

    fetched_at = entry.get("fetched_at")
    if not isinstance(fetched_at, datetime):
        return True

    age_sec = (_get_now() - fetched_at).total_seconds()
    return age_sec >= DDS_MUTABLE_REFRESH_SEC

def _normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_dds_day(header_date: Any) -> str | None:
    raw = str(header_date or "").strip()
    if not raw:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", raw)
    return m.group(1) if m else None


def _local_day_key(dt: datetime | None) -> str | None:
    if not dt:
        return None
    try:
        local_dt = dt.astimezone(ZoneInfo(DDS_TIMEZONE)) if DDS_TIMEZONE else dt
        return local_dt.strftime("%Y-%m-%d")
    except Exception:
        return dt.strftime("%Y-%m-%d")


def _webtools_monitor_ref():
    return db.collection(WEBTOOLS_ROOT_COLLECTION).document(WEBTOOLS_MONITOR_DOC)


def _monitor_subcollection(name: str):
    return _webtools_monitor_ref().collection(name)


def _parse_dds_time_value(value: Any) -> tuple[int, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"\b(\d{1,2})[:hH](\d{2})\b", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour, minute
    return None


def _combine_dds_day_time(day: str | None, time_value: Any) -> datetime | None:
    if not day:
        return None
    parsed = _parse_dds_time_value(time_value)
    if not parsed:
        return None
    hour, minute = parsed
    try:
        local_tz = ZoneInfo(DDS_TIMEZONE)
    except Exception:
        local_tz = timezone(timedelta(hours=-3))
    try:
        local_dt = datetime.strptime(day, "%Y-%m-%d").replace(
            hour=hour, minute=minute, second=0, microsecond=0, tzinfo=local_tz
        )
        return local_dt.astimezone(timezone.utc)
    except Exception:
        return None


def _dds_day_to_effective_contact_dt(day: str | None) -> datetime | None:
    """Fallback quando existe DDS, mas o documento não traz timestamp aproveitável."""
    if not day:
        return None
    today_key = _local_today().strftime("%Y-%m-%d")
    if day == today_key:
        return _get_now().astimezone(timezone.utc)
    try:
        local_tz = ZoneInfo(DDS_TIMEZONE)
    except Exception:
        local_tz = timezone(timedelta(hours=-3))
    try:
        local_dt = datetime.strptime(day, "%Y-%m-%d").replace(
            hour=12, minute=0, second=0, microsecond=0, tzinfo=local_tz
        )
        return local_dt.astimezone(timezone.utc)
    except Exception:
        return None


def _extract_dds_timestamp(data: dict[str, Any], day: str | None = None) -> datetime | None:
    """Extrai a melhor data/hora disponível do documento DDS."""
    for key in (
        "executedAt",
        "submittedAt",
        "sentAt",
        "serverUpdatedAt",
        "updatedAt",
        "createdAt",
        "timestamp",
        "dataHora",
        "horaConclusao",
        "_doc_create_time",
        "_doc_update_time",
    ):
        dt = to_utc_dt(data.get(key)) or _parse_iso_datetime(data.get(key))
        if dt:
            return dt

    combined = _combine_dds_day_time(day or _extract_dds_day(data.get("headerDate")), data.get("hora"))
    if combined:
        return combined
    return _dds_day_to_effective_contact_dt(day or _extract_dds_day(data.get("headerDate")))


def _activity_event_id(team_key: str, source: str, activity_at: datetime | None = None) -> str:
    dt = to_utc_dt(activity_at) or _utc_now()
    safe_team = re.sub(r"[^A-Z0-9_\-]", "_", _normalize_text(team_key) or "UNKNOWN")
    safe_source = re.sub(r"[^a-z0-9_\-]", "_", str(source or "unknown").lower())
    return f"{dt.strftime('%Y%m%dT%H%M%S%f')}_{safe_team}_{safe_source}"


def _activity_label(source: str, extra: dict[str, Any] | None = None) -> str:
    extra = extra or {}
    source_key = str(source or "").lower()
    estado = normalize_estado(extra.get("estado")) if extra.get("estado") else ""
    if source_key == "dds":
        return "Execução de DDS"
    if source_key == "mensagem":
        return "Mensagem enviada"
    if source_key == "team_members_changed":
        return "Alteração de membro da equipe"
    if source_key == "team_activated":
        return "Equipe ativada"
    if source_key == "team_deactivated":
        return "Equipe inativada"
    if source_key == "turno":
        if estado == "ABERTO":
            return "Abertura de turno"
        if estado == "FECHADO":
            return "Fechamento de turno"
        if estado == "INTERVALO":
            return "Início de intervalo"
        if estado == "DESLOCAMENTO_ESPECIAL":
            return "Deslocamento especial"
        if estado == "DESATUALIZADO":
            return "Status desatualizado"
        return "Alteração de turno"
    return str(source or "Atividade")


def _activity_feed_item(
    *,
    empresa: str,
    team_key: str,
    equipe: str | None,
    source: str,
    activity_dt: datetime,
    event_id: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    local_dt = activity_dt.astimezone(ZoneInfo(DDS_TIMEZONE)) if DDS_TIMEZONE else activity_dt
    return {
        "eventId": event_id,
        "empresa": empresa,
        "teamKey": team_key,
        "equipe": equipe or team_key,
        "source": source,
        "label": _activity_label(source, extra),
        "time": local_dt.strftime("%H:%M"),
        "activityAt": activity_dt.isoformat(),
    }


def _update_activity_feed(empresa: str, feed_item: dict[str, Any], limit: int = 5) -> None:
    """Mantém um documento pequeno com as últimas atividades para a tela."""
    ref = _monitor_subcollection("activity_feed").document(empresa)
    try:
        snap = ref.get()
        current = (snap.to_dict() or {}).get("items") if snap.exists else []
        items = [feed_item]
        seen = {feed_item.get("eventId")}
        for item in current or []:
            event_id = item.get("eventId")
            if event_id in seen:
                continue
            seen.add(event_id)
            items.append(item)
        items.sort(key=lambda item: str(item.get("activityAt") or ""), reverse=True)
        ref.set({"empresa": empresa, "items": items[:limit], "updatedAt": firestore.SERVER_TIMESTAMP}, merge=True)
    except Exception as exc:
        print(f"[activity_feed] Erro ao atualizar feed: {exc}")


def _record_team_activity(
    *,
    empresa: str,
    team_key: str,
    equipe: str | None,
    source: str,
    activity_at: Any = None,
    event_ref: str | None = None,
    active_after_event: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    activity_dt = to_utc_dt(activity_at) or _parse_iso_datetime(activity_at) or _utc_now()
    day_key = _local_day_key(activity_dt) or _utc_now().strftime("%Y-%m-%d")
    event_id = _activity_event_id(team_key, source, activity_dt)
    extra = dict(extra or {})
    feed_item = _activity_feed_item(
        empresa=empresa,
        team_key=team_key,
        equipe=equipe,
        source=source,
        activity_dt=activity_dt,
        event_id=event_id,
        extra=extra,
    )
    payload = {
        **feed_item,
        "activityDay": day_key,
        "eventRef": event_ref,
        "activeAfterEvent": active_after_event,
        "receivedAt": firestore.SERVER_TIMESTAMP,
        **extra,
    }
    _monitor_subcollection("activity_events").document(day_key).collection("events").document(event_id).set(payload, merge=True)
    _monitor_subcollection("activity_state").document(f"{empresa}_{team_key}").set(
        {
            "empresa": empresa,
            "teamKey": team_key,
            "equipe": equipe or team_key,
            "active": active_after_event,
            "lastActivityAt": activity_dt,
            "lastActivitySource": source,
            "lastEventId": event_id,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    _update_activity_feed(empresa, feed_item)
    _safe_merge(
        _team_doc_ref(team_key),
        {
            "lastActivityAt": activity_dt,
            "lastActivitySource": source,
            "lastActivityEventId": event_id,
            "updatedAt": firestore.SERVER_TIMESTAMP,
            **({"active": active_after_event} if isinstance(active_after_event, bool) else {}),
        },
    )


def _read_activity_feed(empresa: str, limit: int = 5) -> dict[str, Any]:
    try:
        snap = _monitor_subcollection("activity_feed").document(empresa).get()
        data = snap.to_dict() if snap.exists else {}
        items = list((data or {}).get("items") or [])
        return {"empresa": empresa, "items": items[: max(1, min(int(limit or 5), 20))], "cached": snap.exists}
    except Exception as exc:
        print(f"[activity_feed] Erro ao ler feed: {exc}")
        return {"empresa": empresa, "items": [], "cached": False, "error": str(exc)}


def get_activity_feed(empresa: str = DEFAULT_EMPRESA, limit: int = 5) -> dict[str, Any]:
    return _read_activity_feed(empresa, limit=limit)


def _persist_team_activity_if_newer(
    team_key: str,
    *,
    current_activity_at: Any = None,
    activity_at: datetime | None = None,
    activity_source: str,
    dds_day: str | None = None,
) -> None:
    if not activity_at:
        return
    current_dt = to_utc_dt(current_activity_at) or _parse_iso_datetime(current_activity_at)
    if current_dt and activity_at <= current_dt:
        return
    payload: dict[str, Any] = {
        "lastActivityAt": activity_at,
        "lastActivitySource": activity_source,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if dds_day:
        payload["lastActivityDdsDay"] = dds_day
    _safe_merge(_team_doc_ref(team_key), payload)


def _manual_inactive_blocks_activity(team_data: dict[str, Any], activity_dt: datetime | None, activity_day: str | None) -> bool:
    if team_data.get("autoInactiveReason") != "MANUAL":
        return False
    inactive_at = to_utc_dt(team_data.get("autoInactiveAt"))
    if not inactive_at:
        return False
    if activity_dt:
        return activity_dt <= inactive_at
    inactive_day = _local_day_key(inactive_at)
    return bool(activity_day and inactive_day and activity_day <= inactive_day)


def _apply_dds_activity_trigger(team_key: str, data: dict[str, Any], day: str | None, *, empresa: str = DEFAULT_EMPRESA) -> None:
    team_snap = _team_doc_ref(team_key).get()
    team_data = team_snap.to_dict() or {}
    if not team_data:
        return
    event_dt = _extract_dds_timestamp(data, day) or _dds_day_to_effective_contact_dt(day) or _utc_now()
    _persist_team_activity_if_newer(
        team_key,
        current_activity_at=team_data.get("lastActivityAt"),
        activity_at=event_dt,
        activity_source="dds",
        dds_day=day,
    )
    if not bool(team_data.get("active", True)):
        if _manual_inactive_blocks_activity(team_data, event_dt, day):
            print(f"DDS trigger ignored for {team_key}: manual inactive is newer than DDS activity.")
            return
        _persist_team_active_state(team_key, active=True, source_dt=event_dt, source_dds_day=day)
    _record_team_activity(
        empresa=empresa,
        team_key=team_key,
        equipe=data.get("equipe") or team_data.get("displayName") or team_key,
        source="dds",
        activity_at=event_dt,
        event_ref=data.get("eventRef"),
        active_after_event=True,
        extra={"ddsDay": day, "headerDate": data.get("headerDate"), "headerTitle": data.get("headerTitle")},
    )


def _collect_manifest_days(value: Any, out: set[str]) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            _collect_manifest_days(key, out)
            _collect_manifest_days(inner, out)
        return

    if isinstance(value, list):
        for inner in value:
            _collect_manifest_days(inner, out)
        return

    text = str(value or "")
    if not text:
        return

    for match in re.finditer(r"\b(\d{4}-\d{2}-\d{2})\b", text):
        out.add(match.group(1))


def _calendar_payload_to_days(payload: dict[str, Any] | None) -> set[str]:
    if not isinstance(payload, dict):
        return set()

    days: set[str] = set()
    if isinstance(payload.get("past_days"), list):
        days.update(str(day).strip() for day in payload.get("past_days") if str(day).strip())
    if isinstance(payload.get("current_manifest_days"), list):
        days.update(str(day).strip() for day in payload.get("current_manifest_days") if str(day).strip())

    if days:
        return {day for day in days if _extract_dds_day(day)}

    _collect_manifest_days(payload, days)
    return {day for day in days if _extract_dds_day(day)}


def _load_calendar_source_days() -> set[str] | None:
    payload = _storage_read_json(DDS_CALENDAR_SOURCE_BLOB)
    if payload is None:
        return None
    return _calendar_payload_to_days(payload)


def _calendar_cache_is_fresh(payload: dict[str, Any]) -> bool:
    refreshed_on = str(payload.get("refreshed_on") or "").strip()
    if refreshed_on and refreshed_on == _local_today().strftime("%Y-%m-%d"):
        return True

    updated_at = _parse_iso_datetime(payload.get("updated_at"))
    if not updated_at:
        return False

    local_now = datetime.now(ZoneInfo(DDS_TIMEZONE)) if DDS_TIMEZONE else datetime.now(timezone.utc)
    local_updated = updated_at.astimezone(ZoneInfo(DDS_TIMEZONE)) if DDS_TIMEZONE else updated_at
    return local_updated.date() == local_now.date()


def _load_dds_calendar_days(force_refresh: bool = False) -> set[str] | None:
    cached_payload = _DDS_CALENDAR_CACHE.get("payload") if isinstance(_DDS_CALENDAR_CACHE.get("payload"), dict) else None
    if cached_payload and not force_refresh and _calendar_cache_is_fresh(cached_payload):
        return _calendar_payload_to_days(cached_payload)

    storage_payload = _storage_read_json(DDS_CALENDAR_CACHE_BLOB)
    if storage_payload and not force_refresh and _calendar_cache_is_fresh(storage_payload):
        _DDS_CALENDAR_CACHE["payload"] = storage_payload
        return _calendar_payload_to_days(storage_payload)

    source_days = _load_calendar_source_days()
    if source_days is None:
        fallback_payload = storage_payload or cached_payload
        if isinstance(fallback_payload, dict):
            _DDS_CALENDAR_CACHE["payload"] = fallback_payload
            return _calendar_payload_to_days(fallback_payload)
        return None

    today_key = _local_today().strftime("%Y-%m-%d")
    prior_payload = storage_payload or cached_payload or {}
    prior_past_days = {
        str(day).strip()
        for day in (prior_payload.get("past_days") or [])
        if str(day).strip()
    }

    source_past_days = {day for day in source_days if day <= today_key}
    merged_payload = {
        "updated_at": _utc_now_iso(),
        "refreshed_on": today_key,
        "source_blob": DDS_CALENDAR_SOURCE_BLOB,
        "cache_blob": DDS_CALENDAR_CACHE_BLOB,
        "past_days": sorted(prior_past_days | source_past_days),
        "current_manifest_days": sorted(source_days),
    }
    _storage_write_json(DDS_CALENDAR_CACHE_BLOB, merged_payload)
    _DDS_CALENDAR_CACHE["payload"] = merged_payload
    return _calendar_payload_to_days(merged_payload)


def _day_cache_blob(day: str) -> str:
    return _storage_blob_name(DDS_DAY_CACHE_PREFIX, f"{day}.json")


def _serialize_day_cache(day: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": day,
        "updated_at": (entry.get("fetched_at") or _utc_now()).isoformat() if isinstance(entry.get("fetched_at"), datetime) else _utc_now_iso(),
        "frozen": bool(entry.get("frozen")),
        "has_any": bool(entry.get("has_any")),
        "teams_executed": sorted(str(team).strip() for team in (entry.get("present") or set()) if str(team).strip()),
        "team_timestamps": {k: (v.isoformat() if hasattr(v, "isoformat") else str(v)) for k, v in (entry.get("team_timestamps") or {}).items()},
        "team_photos": {k: str(v) for k, v in (entry.get("team_photos") or {}).items() if v},
    }


def _deserialize_day_cache(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    day = _extract_dds_day(payload.get("date"))
    if not day:
        return None
    teams_executed = {str(team).strip() for team in (payload.get("teams_executed") or []) if str(team).strip()}
    team_timestamps = {k: _parse_iso_datetime(v) for k, v in (payload.get("team_timestamps") or {}).items()}
    team_photos = {k: str(v) for k, v in (payload.get("team_photos") or {}).items() if v}
    return {
        "date": day,
        "present": teams_executed,
        "team_timestamps": team_timestamps,
        "team_photos": team_photos,
        "has_any": bool(payload.get("has_any")) or bool(teams_executed),
        "fetched_at": _parse_iso_datetime(payload.get("updated_at")),
        "frozen": bool(payload.get("frozen")),
        "pending_team_keys": set(),
    }


def _load_storage_day_cache(day: str) -> dict[str, Any] | None:
    payload = _storage_read_json(_day_cache_blob(day))
    entry = _deserialize_day_cache(payload)
    if not entry:
        return None
    with _cache_lock:
        _DDS_DAY_CACHE[day] = entry
    return entry


def _save_storage_day_cache(day: str, entry: dict[str, Any]) -> None:
    _storage_write_json(_day_cache_blob(day), _serialize_day_cache(day, entry))


def _day_refresh_seconds(day: str, mutable_days: set[str], manual_refresh: bool = False) -> int | None:
    if day not in mutable_days:
        return None
    if manual_refresh:
        return 0

    today_key = _local_today().strftime("%Y-%m-%d")
    if day == today_key:
        return max(15, int(get_monitor_polling_seconds()))
    return max(60, DDS_LAST_BUSINESS_REFRESH_SEC)


def _should_refresh_day_entry(entry: dict[str, Any] | None, ttl_sec: int | None) -> bool:
    if entry is None:
        return True
    if ttl_sec is None:
        return False

    fetched_at = entry.get("fetched_at")
    if not isinstance(fetched_at, datetime):
        return True

    age_sec = (_utc_now() - fetched_at).total_seconds()
    return age_sec >= ttl_sec


def _build_day_cache_entry(
    day: str,
    *,
    present: set[str],
    team_timestamps: dict[str, Any],
    has_any: bool,
    frozen: bool,
    team_photos: dict[str, Any] = None,
) -> dict[str, Any]:
    return {
        "date": day,
        "present": set(present or set()),
        "team_timestamps": dict(team_timestamps or {}),
        "team_photos": dict(team_photos or {}),
        "has_any": bool(has_any),
        "fetched_at": _utc_now(),
        "frozen": bool(frozen),
        "pending_team_keys": set(),
    }


def _load_day_presence_with_cache(
    day: str,
    *,
    mutable_days: set[str],
    calendar_days: set[str] | None,
    manual_refresh: bool = False,
) -> dict[str, Any]:
    with _cache_lock:
        entry = _DDS_DAY_CACHE.get(day)
    if entry is None:
        entry = _load_storage_day_cache(day)

    ttl_sec = _day_refresh_seconds(day, mutable_days, manual_refresh=manual_refresh)
    calendar_known = calendar_days is not None
    day_in_calendar = calendar_known and day in calendar_days

    # Fallback para fins de semana caso o calendário não esteja disponível
    from datetime import datetime
    is_weekend = False
    try:
        is_weekend = datetime.strptime(day, "%Y-%m-%d").weekday() in (5, 6)
    except Exception:
        pass

    is_non_business = (calendar_known and not day_in_calendar) or (not calendar_known and is_weekend)

    if is_non_business:
        if entry is None or entry.get("has_any") or entry.get("present"):
            entry = _build_day_cache_entry(day, present=set(), team_timestamps={}, team_photos={}, has_any=False, frozen=True)
            with _cache_lock:
                _DDS_DAY_CACHE[day] = entry
            _save_storage_day_cache(day, entry)
        else:
            entry["frozen"] = True
            entry["pending_team_keys"] = set()
        return entry

    if not _should_refresh_day_entry(entry, ttl_sec):
        return entry

    carry_present = set(entry.get("present") or set()) if entry else set()
    carry_photos = dict(entry.get("team_photos") or {}) if entry else {}
    present, has_any_dds, team_timestamps, team_photos = _load_dds_presence_for_day(day, carry_present, carry_photos)
    frozen = day not in mutable_days
    entry = _build_day_cache_entry(day, present=present, team_timestamps=team_timestamps, team_photos=team_photos, has_any=has_any_dds or bool(carry_present), frozen=frozen)
    with _cache_lock:
        _DDS_DAY_CACHE[day] = entry
    _save_storage_day_cache(day, entry)
    return entry


def _force_refresh_days(days: set[str]) -> None:
    for day in days:
        with _cache_lock:
            entry = _DDS_DAY_CACHE.get(day)
        if not entry:
            entry = _load_storage_day_cache(day) or {"date": day, "pending_team_keys": set()}
            with _cache_lock:
                _DDS_DAY_CACHE[day] = entry
        entry["fetched_at"] = None


def _build_manual_refresh_days(recent_days: list[str]) -> set[str]:
    mutable_days = _mutable_dds_days(recent_days)
    return {day for day in recent_days if day in mutable_days}


def _build_team_aliases(team_key: str, team_data: dict[str, Any], turno_data: dict[str, Any], equipe_label: str) -> set[str]:
    aliases = {
        _normalize_text(team_key),
        _normalize_text(team_data.get("teamKey")),
        _normalize_text(team_data.get("displayName")),
        _normalize_text(turno_data.get("equipe")),
        _normalize_text(equipe_label),
    }
    return {a for a in aliases if a}

def _normalized_alias_matches(value: str | None, alias: str | None) -> bool:
    """Compara equipe por chave exata ou por token.

    Exemplo:
    - E3X93
    - E3X93 - FULANO
    - Equipe E3X93
    """
    norm_value = _normalize_text(value)
    norm_alias = _normalize_text(alias)
    if not norm_value or not norm_alias:
        return False
    if norm_value == norm_alias:
        return True

    token_re = rf"(?<![A-Z0-9]){re.escape(norm_alias)}(?![A-Z0-9])"
    if re.search(token_re, norm_value):
        return True

    reverse_re = rf"(?<![A-Z0-9]){re.escape(norm_value)}(?![A-Z0-9])"
    return bool(re.search(reverse_re, norm_alias))

def _latest_dds_ts_for_aliases(
    recent_dds_days: list[str],
    dds_timestamps_by_day: dict[str, dict[str, Any]],
    aliases: set[str],
) -> datetime | None:
    latest_ts = None
    for day in reversed(recent_dds_days):
        day_ts_map = dds_timestamps_by_day.get(day) or {}
        for alias in aliases:
            ts = to_utc_dt(day_ts_map.get(alias))
            if not ts:
                for present_name, raw_ts in day_ts_map.items():
                    if _normalized_alias_matches(present_name, alias):
                        ts = to_utc_dt(raw_ts)
                        if ts:
                            break
            if ts:
                if not latest_ts or ts > latest_ts:
                    latest_ts = ts
    return latest_ts


def _load_dds_presence_for_day(
    day: str,
    carry_present: set[str] | None = None,
    carry_photos: dict[str, Any] | None = None,
) -> tuple[set[str], bool, dict[str, Any], dict[str, Any]]:
    present = set(carry_present or set())
    team_timestamps: dict[str, Any] = {}
    team_photos: dict[str, Any] = dict(carry_photos or {})
    has_any_dds = False
    end_key = f"{day}\uf8ff"

    query = (
        db.collection(DDS_COLLECTION)
        .where(filter=FieldFilter("headerDate", ">=", day))
        .where(filter=FieldFilter("headerDate", "<=", end_key))
    )

    for snap in query.stream():
        data = snap.to_dict() or {}
        if getattr(snap, "create_time", None):
            data["_doc_create_time"] = snap.create_time
        if getattr(snap, "update_time", None):
            data["_doc_update_time"] = snap.update_time
        snap_day = _extract_dds_day(data.get("headerDate"))
        if snap_day != day:
            continue

        has_any_dds = True
        equipe = _normalize_text(data.get("equipe") or data.get("teamName") or data.get("teamKey"))
        ts = _extract_dds_timestamp(data, snap_day)
        photo_url = data.get("fotoUrl") or data.get("thumbUrl") or data.get("photoUrl")
        if equipe:
            present.add(equipe)
            if ts:
                current_ts = to_utc_dt(team_timestamps.get(equipe))
                if not current_ts or ts > current_ts:
                    team_timestamps[equipe] = ts
            if photo_url:
                team_photos[equipe] = photo_url

    return present, has_any_dds, team_timestamps, team_photos


def _load_recent_dds_presence(
    days: int = DDS_HISTORY_DAYS,
    *,
    manual_refresh: bool = False,
) -> tuple[list[str], dict[str, set[str]], set[str], set[str], set[str] | None, dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:

    """
    Retorna:
      - recent_days: lista ascendente dos últimos N dias corridos (YYYY-MM-DD)
      - present_by_day[day]: conjunto normalizado das equipes com DDS no dia
      - days_with_any_dds: conjunto dos dias que tiveram pelo menos um DDS
      - mutable_days: dias que ainda podem ser atualizados (hoje e último dia útil)
      - calendar_days: conjunto de dias válidos vindos do calendário persistente, quando disponível
      - dds_timestamps_by_day: mapa de dia -> {equipe -> timestamp}
      - dds_photos_by_day: mapa de dia -> {equipe -> photo_url}
    """
    recent_days = _recent_history_days(days)
    mutable_days = _mutable_dds_days(recent_days)
    _prune_dds_day_cache(set(recent_days))

    if manual_refresh:
        _force_refresh_days(_build_manual_refresh_days(recent_days))

    calendar_days = _load_dds_calendar_days(force_refresh=False)
    present_by_day: dict[str, set[str]] = {day: set() for day in recent_days}
    dds_timestamps_by_day: dict[str, dict[str, Any]] = {day: {} for day in recent_days}
    dds_photos_by_day: dict[str, dict[str, Any]] = {day: {} for day in recent_days}
    days_with_any_dds: set[str] = set()

    from concurrent.futures import ThreadPoolExecutor

    def load_day(day):
        return day, _load_day_presence_with_cache(
            day,
            mutable_days=mutable_days,
            calendar_days=calendar_days,
            manual_refresh=manual_refresh,
        )

    with ThreadPoolExecutor(max_workers=min(len(recent_days), 20)) as executor:
        results = list(executor.map(load_day, recent_days))

    for day, entry in results:
        present_by_day[day] = set(entry.get("present") or set())
        dds_timestamps_by_day[day] = dict(entry.get("team_timestamps") or {})
        dds_photos_by_day[day] = dict(entry.get("team_photos") or {})
        if entry.get("has_any"):
            days_with_any_dds.add(day)

    return recent_days, present_by_day, days_with_any_dds, mutable_days, calendar_days, dds_timestamps_by_day, dds_photos_by_day


def _turno_doc_ref(empresa: str, team_key: str):
    return db.collection("turno").document(empresa).collection("equipes").document(team_key)


def _team_doc_ref(team_key: str):
    return db.collection("dds_teams").document(team_key)


def _safe_merge(doc_ref, payload: dict[str, Any]) -> None:
    if not payload:
        return
    try:
        doc_ref.set(payload, merge=True)
    except Exception:
        pass


def _same_utc_dt(left: Any, right: Any) -> bool:
    left_dt = to_utc_dt(left)
    right_dt = to_utc_dt(right)
    return left_dt == right_dt


def _persist_auto_turno_state(
    empresa: str,
    team_key: str,
    *,
    current_estado: str,
    current_reason: Any,
    current_source_dt: Any,
    new_estado: str,
    reason: str,
    source_dt: Any,
) -> None:
    if (
        current_estado == new_estado
        and current_reason == reason
        and _same_utc_dt(current_source_dt, source_dt)
    ):
        return

    payload: dict[str, Any] = {
        "estado": new_estado,
        "autoStateReason": reason,
        "autoStateAt": firestore.SERVER_TIMESTAMP,
    }
    if source_dt is not None:
        payload["autoStateSourceUpdatedAt"] = source_dt
    _safe_merge(_turno_doc_ref(empresa, team_key), payload)


def _persist_reopen_after_activity(
    empresa: str,
    team_key: str,
    *,
    current_estado: str,
    current_reason: Any,
) -> None:
    if current_estado == "ABERTO" and not current_reason:
        return

    payload = {
        "estado": "ABERTO",
        "autoStateReason": firestore.DELETE_FIELD,
        "autoStateAt": firestore.DELETE_FIELD,
        "autoStateSourceUpdatedAt": firestore.DELETE_FIELD,
        "autoReopenedAt": firestore.SERVER_TIMESTAMP,
    }
    _safe_merge(_turno_doc_ref(empresa, team_key), payload)


def _persist_team_active_state(
    team_key: str,
    *,
    active: bool,
    reason: str | None = None,
    source_dt: Any = None,
    source_dds_day: str | None = None,
    source_kind: str | None = None,
) -> None:
    payload: dict[str, Any] = {"active": active}

    if active:
        payload.update(
            {
                "autoInactiveReason": firestore.DELETE_FIELD,
                "autoInactiveAt": firestore.DELETE_FIELD,
                "autoReactivatedAt": firestore.SERVER_TIMESTAMP,
            }
        )
        activity_dt = to_utc_dt(source_dt)
        if activity_dt:
            payload["autoInactiveLastSeenUpdatedAt"] = activity_dt
            payload["lastActivityAt"] = activity_dt
            payload["lastActivitySource"] = source_kind or "unknown"
            payload["lastActivityUpdatedAt"] = firestore.SERVER_TIMESTAMP
        else:
            payload["autoInactiveLastSeenUpdatedAt"] = firestore.DELETE_FIELD
        if source_dds_day:
            payload["autoInactiveLastSeenDdsDay"] = source_dds_day
            payload["lastActivityDdsDay"] = source_dds_day
        else:
            payload["autoInactiveLastSeenDdsDay"] = firestore.DELETE_FIELD
    else:
        payload.update(
            {
                "autoInactiveReason": reason or AUTO_REASON_INACTIVE_UNKNOWN,
                "autoInactiveAt": firestore.SERVER_TIMESTAMP,
            }
        )
        if source_dt is not None:
            payload["autoInactiveLastSeenUpdatedAt"] = source_dt
        if source_dds_day:
            payload["autoInactiveLastSeenDdsDay"] = source_dds_day

    _safe_merge(_team_doc_ref(team_key), payload)


def _persist_team_inactive_checkpoint(
    team_key: str,
    *,
    source_dt: Any = None,
    source_dds_day: str | None = None,
) -> None:
    payload: dict[str, Any] = {}
    if source_dt is not None:
        payload["autoInactiveLastSeenUpdatedAt"] = source_dt
    if source_dds_day:
        payload["autoInactiveLastSeenDdsDay"] = source_dds_day
    _safe_merge(_team_doc_ref(team_key), payload)

def list_turnos(empresa: str, active: bool | None = None, *, manual_refresh: bool = False, setor: str = CURRENT_SETOR) -> dict[str, Any]:
    # ------------------------------------------------------------------
    # Cache de vis\u00e3o completa: serve do cache quando n\u00e3o \u00e9 refresh manual.
    # O cache guarda TODAS as equipes; o filtro active/setor \u00e9 aplicado
    # em mem\u00f3ria aqui mesmo, sem custo extra de Firestore.
    # ------------------------------------------------------------------
    if not manual_refresh:
        cached = _read_monitor_view_cache(empresa)
        # L\u00f3gica de Reset Di\u00e1rio (00:00): se mudou o dia, ignora cache
        if cached:
            cached_at_str = cached.get("_cachedAt")
            if cached_at_str:
                cached_day = cached_at_str.split('T')[0]
                today_day = _utc_now_iso().split('T')[0]
                if cached_day != today_day:
                    cached = None # For\u00e7a rec\u00e1lculo
        
        if cached:
            # Remove chave interna antes de retornar
            cached = {k: v for k, v in cached.items() if k != "_cachedAt"}
            # Aplica filtro de active em mem\u00f3ria (se solicitado)
            if active is not None:
                cached = {
                    **cached,
                    "items": [it for it in (cached.get("items") or []) if bool(it.get("active")) is active],
                    "activeFilter": active,
                    "currentSector": setor,
                    "cachedView": True,
                }
            else:
                cached = {**cached, "activeFilter": active, "currentSector": setor, "cachedView": True}
            return cached

    col_ref = db.collection("turno").document(empresa).collection("equipes")
    turno_docs = {doc.id: (doc.to_dict() or {}) for doc in col_ref.stream()}
    teams_map = list_teams_map(active=None)
    recent_days_res = _load_recent_dds_presence(manual_refresh=manual_refresh)
    recent_dds_days = recent_days_res[0]
    dds_present_by_day = recent_days_res[1]
    dds_days_with_any = recent_days_res[2]
    mutable_dds_days = recent_days_res[3]
    calendar_days = recent_days_res[4]
    dds_timestamps_by_day = recent_days_res[5]
    dds_photos_by_day = recent_days_res[6]

    unread_counts = get_unread_counts(setor=setor)
    unread_map_global = get_all_unread_counts_map()
    last_messages_map = get_last_messages_map()

    rules = get_monitor_rules()
    now = _get_now()
    pending_by_day: dict[str, set[str]] = {day: set() for day in mutable_dds_days}

    all_keys = set(turno_docs.keys()) | set(teams_map.keys())

    def process_task(team_key):
        return _process_single_team(
            team_key=team_key,
            empresa=empresa,
            team_data=teams_map.get(team_key) or {},
            data=turno_docs.get(team_key) or {},
            recent_dds_days=recent_dds_days,
            dds_present_by_day=dds_present_by_day,
            dds_days_with_any=dds_days_with_any,
            mutable_dds_days=mutable_dds_days,
            calendar_days=calendar_days,
            dds_timestamps_by_day=dds_timestamps_by_day,
            dds_photos_by_day=dds_photos_by_day,
            unread_counts=unread_counts,
            unread_map_global=unread_map_global,
            last_messages_map=last_messages_map,
            now=now,
            rules=rules,
            pending_by_day=pending_by_day,
            active_filter=None,  # cache sempre cont\u00e9m TODAS as equipes
        )

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(process_task, all_keys))

    all_items = [it for it in results if it]

    for day in recent_dds_days:
        entry = _DDS_DAY_CACHE.get(day)
        if not entry:
            continue
        if day not in mutable_dds_days:
            entry["frozen"] = True
            entry["pending_team_keys"] = set()
            continue
        pending = pending_by_day.get(day, set())
        entry["pending_team_keys"] = pending
        if not pending:
            entry["frozen"] = True

    all_items.sort(key=lambda x: (str(x.get("equipe") or ""), str(x.get("teamKey") or "")))

    full_result = {
        "empresa": empresa,
        "serverTime": now.isoformat(),
        "manualRefresh": manual_refresh,
        "items": all_items,
    }

    # Grava no cache para próximas requisições não-forçadas
    _write_monitor_view_cache(empresa, full_result)

    # Aplica filtros de active/setor antes de retornar
    items = all_items if active is None else [it for it in all_items if bool(it.get("active")) is active]
    # Remove campos pesados de DDS do payload de status (serão carregados lazy via /api/turnos/dds)
    status_items = [_strip_dds_history(it) for it in items]
    return {
        **full_result,
        "items": status_items,
        "activeFilter": active,
        "currentSector": setor,
    }


# Campos de histórico DDS que são carregados separadamente via /api/turnos/dds
_DDS_HEAVY_FIELDS = {"ddsHistory", "ddsDays", "ddsTimes", "ddsPhotos"}


def _strip_dds_history(item: dict[str, Any]) -> dict[str, Any]:
    """Remove campos pesados de DDS de um item, mantendo apenas ddsToday."""
    return {k: v for k, v in item.items() if k not in _DDS_HEAVY_FIELDS}


def list_turnos_dds(empresa: str, active: bool | None = None) -> dict[str, Any]:
    """
    Retorna apenas os campos de histórico DDS por equipe, lendo do cache.
    Usado pelo endpoint GET /api/turnos/dds para carga lazy no frontend.
    """
    cache = _read_monitor_view_cache(empresa)
    if not cache:
        return {"empresa": empresa, "items": [], "cached": False}

    all_items = cache.get("items") or []
    if active is not None:
        all_items = [it for it in all_items if bool(it.get("active")) is active]

    dds_items = [
        {
            "teamKey": it.get("teamKey"),
            "ddsHistory": it.get("ddsHistory") or [],
            "ddsDays": it.get("ddsDays") or [],
            "ddsTimes": it.get("ddsTimes") or {},
            "ddsPhotos": it.get("ddsPhotos") or {},
            "ddsToday": it.get("ddsToday") or "neutral",
            "lastContact": it.get("lastContact"),
            "lastContactSource": it.get("lastContactSource"),
            "active": it.get("active"),
            "estado": it.get("estado"),
            "updatedAt": it.get("updatedAt"),
        }
        for it in all_items
    ]

    return {"empresa": empresa, "items": dds_items, "cached": True}


def _send_pre_inactivation_warning(
    empresa: str,
    team_key: str,
    total_hours_no_contact: int,
    hours_remaining: int,
    stage_start_str: str,
) -> None:
    dias = total_hours_no_contact // 24
    horas_resto = total_hours_no_contact % 24

    if dias > 0:
        tempo_str = f"{dias} dia(s) e {horas_resto} hora(s)" if horas_resto > 0 else f"{dias} dia(s)"
    else:
        tempo_str = f"{horas_resto} hora(s)"

    msg_body = (
        f"Você está a {tempo_str} sem comunicação com o DDS.\n\n"
        f"Dentro de {hours_remaining} hora(s) sua equipe será marcada como INATIVA.\n\n"
        f"Acesse o aplicativo de DDS e realize o DDS e informe o status de seu turno."
    )

    try:
        # Atualiza a notificação no documento da equipe para ser lida pelo aplicativo Android
        db.collection("turno").document(empresa).collection("equipes").document(team_key).set({
            "lastPreInactiveWarningAt": firestore.SERVER_TIMESTAMP,
            "lastPreInactiveWarningSentAt": firestore.SERVER_TIMESTAMP,
            "lastPreInactiveWarningMsg": msg_body,
            "lastPreInactiveWarningStage": stage_start_str,
            "preInactiveWarningActive": True,
        }, merge=True)

        # Grava na coleção de mensagens de comunicação
        db.collection("mensagens_comunicacao").add({
            "empresa": empresa,
            "fromEquipe": "SISTEMA_DDS",
            "toEquipe": team_key,
            "toSetor": "TODOS",
            "mensagem": msg_body,
            "tipo": "ALERTA_PRE_INATIVACAO",
            "status": "NÃO LIDO",
            "createdAt": firestore.SERVER_TIMESTAMP,
            "serverUpdatedAt": firestore.SERVER_TIMESTAMP,
        })
    except Exception as e:
        print(f"[WARN] Erro ao registrar alerta pre-inativacao para {team_key}: {e}")


def _process_single_team(
    *,
    team_key: str,
    empresa: str,
    team_data: dict[str, Any],
    data: dict[str, Any],
    recent_dds_days: list[str],
    dds_present_by_day: dict[str, set[str]],
    dds_days_with_any: set[str],
    mutable_dds_days: set[str],
    calendar_days: set[str] | None,
    dds_timestamps_by_day: dict[str, dict[str, Any]],
    dds_photos_by_day: dict[str, dict[str, Any]],
    unread_counts: dict[str, int],
    unread_map_global: dict[str, dict[str, int]],
    last_messages_map: dict[str, datetime],
    now: datetime,
    rules: dict[str, Any],
    pending_by_day: dict[str, set[str]],
    active_filter: bool | None = None
) -> dict[str, Any] | None:
    alerta_amarelo_min = int(rules.get("alertaAmareloMin") or 15)
    alerta_vermelho_min = int(rules.get("alertaVermelhoMin") or 30)
    alerta_pisco_min = int(rules.get("alertaPiscoMin") or 60)
    auto_close_open_h = int(rules.get("autoCloseOpenHours") or AUTO_CLOSE_OPEN_HOURS_DEFAULT)
    auto_desat_fechado_h = int(
        rules.get("autoDesatualizaFechadoHours") or AUTO_DESATUALIZA_FECHADO_HOURS_DEFAULT
    )
    auto_desat_intervalo_h = int(
        rules.get("autoDesatualizaIntervaloHours") or AUTO_DESATUALIZA_INTERVALO_HOURS_DEFAULT
    )
    critico_desat_h = int(rules.get("desatualizadoCriticoHoras") or 16)

    team_active = bool(team_data.get("active", True)) if team_data else True
    has_turno_doc = bool(data)
    equipe = team_data.get("displayName") or data.get("equipe") or team_key
    estado_original = normalize_estado(data.get("estado") or "DESCONHECIDO")
    ss = data.get("nocSs")
    motivo = data.get("lastMotivoOutro") or data.get("lastMotivo")
    participantes = string_list(team_data.get("members")) or extract_participantes(data)
    aliases = _build_team_aliases(team_key, team_data, data, equipe)
    latest_dds_ts = _latest_dds_ts_for_aliases(recent_dds_days, dds_timestamps_by_day, aliases)
    latest_dds_day = latest_dds_ts.strftime("%Y-%m-%d") if latest_dds_ts else None
    if not latest_dds_ts:
        for day in reversed(recent_dds_days):
            presentes_no_dia = dds_present_by_day.get(day) or set()
            found_dds = any(
                alias in presentes_no_dia
                or any(_normalized_alias_matches(present_name, alias) for present_name in presentes_no_dia)
                for alias in aliases
            )
            if found_dds:
                latest_dds_day = day
                latest_dds_ts = _dds_day_to_effective_contact_dt(day)
                break

    ts = data.get("serverUpdatedAt") or data.get("updatedAt")
    dt = to_utc_dt(ts)
    
    # ÚLTIMO CONTATO: Max entre sinal do Turno, DDS, Mensagens e lastActivityAt consolidado
    last_contact_dt = dt
    last_contact_src = "T" if dt else None

    team_activity_dt = to_utc_dt(team_data.get("lastActivityAt"))
    if team_activity_dt and (not last_contact_dt or team_activity_dt > last_contact_dt):
        last_contact_dt = team_activity_dt
        last_contact_src = str(team_data.get("lastActivitySource") or "A")[:1].upper()

    if latest_dds_ts:
        if not last_contact_dt or latest_dds_ts > last_contact_dt:
            last_contact_dt = latest_dds_ts
            last_contact_src = "D"
            
    # Mensagens enviadas pelos aliases
    for alias in aliases:
        msg_ts = last_messages_map.get(alias)
        if msg_ts:
            if not last_contact_dt or msg_ts > last_contact_dt:
                last_contact_dt = msg_ts
                last_contact_src = "M"

    minutos = None
    horas = None
    if dt:
        minutos = int((now - dt).total_seconds() // 60)
        horas = minutos // 60
    elif has_turno_doc:
        minutos = 10**9
        horas = 10**9

    # 3. Checkpoints de inativação manual
    last_seen_auto_inactive_dt = to_utc_dt(team_data.get("autoInactiveLastSeenUpdatedAt"))
    last_seen_auto_inactive_dds_day = team_data.get("autoInactiveLastSeenDdsDay")
    inactive_at = to_utc_dt(team_data.get("autoInactiveAt"))

    has_inactive_checkpoint = bool(last_seen_auto_inactive_dt or last_seen_auto_inactive_dds_day)
    manual_inactive = team_data.get("autoInactiveReason") == "MANUAL"

    # Nova comunicação de turno: sinal mais novo que o checkpoint de inativação
    new_turno_communication = bool(
        dt and last_seen_auto_inactive_dt and dt > last_seen_auto_inactive_dt
    )

    # Nova comunicação de DDS: usa TIMESTAMP, não apenas dia, para detectar DDS no mesmo dia
    new_dds_communication = bool(
        latest_dds_ts
        and inactive_at
        and latest_dds_ts > inactive_at
    )

    # Nova mensagem enviada após a inativação
    latest_message_dt = None
    for alias in aliases:
        msg_ts = last_messages_map.get(alias)
        if msg_ts and (not latest_message_dt or msg_ts > latest_message_dt):
            latest_message_dt = msg_ts
    new_message_communication = bool(
        latest_message_dt
        and inactive_at
        and latest_message_dt > inactive_at
    )

    if not team_active:
        # Equipes com active=False mas sem checkpoint são tratadas como manual_inactive.
        # Isso evita que equipes desativadas antes do sistema de checkpoints sejam
        # reativadas automaticamente na próxima consolidação.
        if not has_inactive_checkpoint:
            if not dt and not latest_dds_day:
                # Sem nenhum dado: não reativar
                pass
            elif manual_inactive:
                # Manual sem checkpoint: grava checkpoint e mantém inativa
                _persist_team_inactive_checkpoint(
                    team_key,
                    source_dt=last_contact_dt,
                    source_dds_day=latest_dds_day,
                )
            else:
                # Sem checkpoint e sem inativação manual: assume nova comunicação
                new_turno_communication = bool(dt)
                new_dds_communication = bool(latest_dds_day)

        if new_turno_communication or new_dds_communication or new_message_communication:
            activity_dt = latest_dds_ts or latest_message_dt or dt
            activity_day = latest_dds_day
            activity_kind = "dds" if latest_dds_ts else ("mensagem" if latest_message_dt else "turno")
            _persist_team_activity_if_newer(
                team_key,
                current_activity_at=team_data.get("lastActivityAt"),
                activity_at=activity_dt,
                activity_source=activity_kind,
                dds_day=activity_day,
            )
            _persist_team_active_state(
                team_key,
                active=True,
                source_dt=activity_dt,
                source_dds_day=activity_day,
            )
            _record_team_activity(
                empresa=empresa,
                team_key=team_key,
                equipe=equipe,
                source="team_activated",
                activity_at=activity_dt,
                active_after_event=True,
                extra={"reason": activity_kind},
            )
            team_active = True
        elif has_inactive_checkpoint:
            auto_inactivate_h = int(rules.get("autoInactivateHours") or 96)
            recent_contact = last_contact_dt and (now - last_contact_dt).total_seconds() < auto_inactivate_h * 3600
            if recent_contact and not manual_inactive:
                _persist_team_active_state(
                    team_key,
                    active=True,
                    source_dt=dt,
                    source_dds_day=latest_dds_day,
                )
                team_active = True

    estado = estado_original
    auto_state_reason = data.get("autoStateReason")
    auto_state_source_dt = to_utc_dt(data.get("autoStateSourceUpdatedAt"))

    # Data inicial do estágio atual (calcula horas de permanência no estado atual)
    state_start_dt = auto_state_source_dt or dt or last_contact_dt
    horas_estagio = int((now - state_start_dt).total_seconds() // 3600) if state_start_dt else (horas or 0)

    # Inativação automática por tempo no estágio DESATUALIZADO ou inatividade extrema
    if estado_original in ["DESCONHECIDO", "FECHADO", "DESATUALIZADO"]:
        if team_active:
            auto_inactivate_h = int(rules.get("autoInactivateHours") or 48)
            reactivated_at = to_utc_dt(team_data.get("autoReactivatedAt"))
            is_grace_period = reactivated_at and (now - reactivated_at).total_seconds() < auto_inactivate_h * 3600
            recent_contact = last_contact_dt and (now - last_contact_dt).total_seconds() < auto_inactivate_h * 3600

            # Inativa se esteve DESATUALIZADO pelo tempo de inativação OU se ficou sem contato além da carência
            is_desat_timeout = (estado_original == "DESATUALIZADO" and horas_estagio >= auto_inactivate_h)
            if last_contact_dt and (is_desat_timeout or not recent_contact) and not is_grace_period:
                _persist_team_active_state(
                    team_key,
                    active=False,
                    reason=AUTO_REASON_INACTIVE_UNKNOWN,
                    source_dt=dt,
                    source_dds_day=latest_dds_day,
                )
                _record_team_activity(
                    empresa=empresa,
                    team_key=team_key,
                    equipe=equipe,
                    source="team_deactivated",
                    activity_at=now,
                    active_after_event=False,
                    extra={"reason": AUTO_REASON_INACTIVE_UNKNOWN},
                )
                team_active = False

    # Equipe DESCONHECIDO sem nenhum contato nunca registrado -> inativa automaticamente
    if estado_original == "DESCONHECIDO" and not last_contact_dt and team_active:
        _persist_team_active_state(
            team_key,
            active=False,
            reason=AUTO_REASON_INACTIVE_UNKNOWN,
            source_dt=None,
            source_dds_day=None,
        )
        _record_team_activity(
            empresa=empresa,
            team_key=team_key,
            equipe=equipe,
            source="team_deactivated",
            activity_at=now,
            active_after_event=False,
            extra={"reason": AUTO_REASON_INACTIVE_UNKNOWN},
        )
        team_active = False

    if active_filter is not None and team_active is not active_filter:
        return None

    if (
        estado_original == "FECHADO"
        and auto_state_reason == AUTO_REASON_CLOSE_OPEN
        and dt
        and auto_state_source_dt
        and dt > auto_state_source_dt
    ):
        estado = "ABERTO"
        _persist_reopen_after_activity(
            empresa,
            team_key,
            current_estado=estado_original,
            current_reason=auto_state_reason,
        )
    elif estado_original == "ABERTO" and dt and horas_estagio >= auto_close_open_h:
        estado = "FECHADO"
        _persist_auto_turno_state(
            empresa,
            team_key,
            current_estado=estado_original,
            current_reason=auto_state_reason,
            current_source_dt=auto_state_source_dt,
            new_estado="FECHADO",
            reason=AUTO_REASON_CLOSE_OPEN,
            source_dt=dt,
        )
        horas_estagio = 0  # Reseta o relógio do novo estágio FECHADO
    elif estado_original == "FECHADO" and horas_estagio >= auto_desat_fechado_h:
        estado = "DESATUALIZADO"
        _persist_auto_turno_state(
            empresa,
            team_key,
            current_estado=estado_original,
            current_reason=auto_state_reason,
            current_source_dt=auto_state_source_dt,
            new_estado="DESATUALIZADO",
            reason=AUTO_REASON_DESAT_FECHADO,
            source_dt=dt,
        )
        horas_estagio = 0  # Reseta o relógio do novo estágio DESATUALIZADO
    elif (
        estado_original == "DESLOCAMENTO_ESPECIAL"
        and horas_estagio >= auto_desat_fechado_h
    ):
        estado = "DESATUALIZADO"
        _persist_auto_turno_state(
            empresa,
            team_key,
            current_estado=estado_original,
            current_reason=auto_state_reason,
            current_source_dt=auto_state_source_dt,
            new_estado="DESATUALIZADO",
            reason=AUTO_REASON_DESAT_DESLOCAMENTO,
            source_dt=dt,
        )
        horas_estagio = 0
    elif estado_original == "INTERVALO" and horas_estagio >= auto_desat_intervalo_h:
        estado = "DESATUALIZADO"
        _persist_auto_turno_state(
            empresa,
            team_key,
            current_estado=estado_original,
            current_reason=auto_state_reason,
            current_source_dt=auto_state_source_dt,
            new_estado="DESATUALIZADO",
            reason=AUTO_REASON_DESAT_INTERVALO,
            source_dt=dt,
        )
        horas_estagio = 0

    critico = bool(estado == "DESATUALIZADO" and horas_estagio >= critico_desat_h)

    # Disparo automático de aviso pré-inativação: inicia 12 horas antes da inativação e reenvia a cada 60 min (3600s)
    if team_active and estado == "DESATUALIZADO":
        auto_inactivate_h = int(rules.get("autoInactivateHours") or 48)
        horas_restantes = auto_inactivate_h - horas_estagio
        
        if 0 < horas_restantes <= 12:
            last_sent_dt = to_utc_dt(team_data.get("lastPreInactiveWarningSentAt"))
            should_send = (not last_sent_dt) or ((now - last_sent_dt).total_seconds() >= 3600)
            
            if should_send:
                stage_key = str(state_start_dt)
                total_no_contact_h = int((now - last_contact_dt).total_seconds() // 3600) if last_contact_dt else horas_estagio
                _send_pre_inactivation_warning(
                    empresa=empresa,
                    team_key=team_key,
                    total_hours_no_contact=total_no_contact_h,
                    hours_remaining=horas_restantes,
                    stage_start_str=stage_key,
                )

    alerta = None
    if minutos is not None:
        if minutos >= alerta_pisco_min:
            alerta = "PULSE"
        elif minutos >= alerta_vermelho_min:
            alerta = "RED"
        elif minutos >= alerta_amarelo_min:
            alerta = "YELLOW"

    dds_history: list[str] = []
    dds_times: dict[str, str] = {}
    dds_photos: dict[str, str] = {}
    for day in recent_dds_days:
        from datetime import datetime
        is_weekend = False
        try:
            is_weekend = datetime.strptime(day, "%Y-%m-%d").weekday() in (5, 6)
        except Exception:
            pass

        is_non_business = (calendar_days is not None and day not in calendar_days) or (calendar_days is None and is_weekend)
        if is_non_business:
            dds_history.append("neutral")
            continue

        if day not in dds_days_with_any:
            dds_history.append("neutral")
            if day in pending_by_day:
                with _pending_lock:
                    pending_by_day[day].add(team_key)
            continue

        presentes_no_dia = dds_present_by_day.get(day) or set()
        encontrou_dds = any(
            alias in presentes_no_dia
            or any(_normalized_alias_matches(present_name, alias) for present_name in presentes_no_dia)
            for alias in aliases
        )
        dds_history.append("ok" if encontrou_dds else "fail")
        if day in pending_by_day and not encontrou_dds:
            with _pending_lock:
                pending_by_day[day].add(team_key)

        if encontrou_dds:
            day_ts_map = dds_timestamps_by_day.get(day) or {}
            day_ts = None
            for alias in aliases:
                ts = to_utc_dt(day_ts_map.get(alias))
                if not ts:
                    for present_name, raw_ts in day_ts_map.items():
                        if _normalized_alias_matches(present_name, alias):
                            ts = to_utc_dt(raw_ts)
                            if ts:
                                break
                if ts:
                    if not day_ts or ts > day_ts:
                        day_ts = ts
            if day_ts:
                try:
                    local_ts = day_ts.astimezone(ZoneInfo(DDS_TIMEZONE)) if DDS_TIMEZONE else day_ts
                    dds_times[day] = local_ts.strftime("%H:%M")
                except Exception:
                    pass

            day_photo_map = dds_photos_by_day.get(day) or {}
            day_photo = None
            for alias in aliases:
                day_photo = day_photo_map.get(alias)
                if not day_photo:
                    for present_name, p_url in day_photo_map.items():
                        if _normalized_alias_matches(present_name, alias):
                            day_photo = p_url
                            if day_photo:
                                break
                if day_photo:
                    break
            if day_photo:
                dds_photos[day] = day_photo

    dds_today = dds_history[-1] if dds_history else "neutral"
    unread_map = unread_map_global.get(team_key) or unread_map_global.get(equipe) or {}
    last_was_descanso_semanal = bool(data.get("lastWasDescansoSemanal", False))
    
    return {
        "teamKey": team_key,
        "equipe": equipe,
        "setor": team_data.get("setor") or data.get("setor") or "TODOS",
        "estado": estado,
        "estadoOriginal": estado_original,
        "ss": ss or "-",
        "motivo": motivo or "-",
        "updatedAt": dt.isoformat() if dt else None,
        "minutosDesdeAtualizacao": minutos,
        "critico": critico,
        "alerta": alerta,
        "participantes": participantes,
        "active": team_active,
        "lastContact": last_contact_dt.isoformat() if last_contact_dt else None,
        "lastContactSource": last_contact_src,
        "ddsHistory": dds_history,
        "ddsToday": dds_today,
        "ddsDays": recent_dds_days,
        "ddsTimes": dds_times,
        "ddsPhotos": dds_photos,
        "unreadMessages": unread_counts.get(equipe, 0) or unread_counts.get(team_key, 0),
        "unreadMap": unread_map,
        "lastWasDescansoSemanal": last_was_descanso_semanal,
        "teamType": team_data.get("teamType") or data.get("teamType"),
        "motorista": team_data.get("motorista"),
        "coringas": team_data.get("coringas") or [],
    }


def update_realtime_view(empresa: str = DEFAULT_EMPRESA, manual_refresh: bool = False, **kwargs) -> dict[str, Any]:
    """
    Força a atualização da visão em tempo real e persiste no Firestore para consumo
    via onSnapshot no monitor. Também invalida e regrava o cache de visão completa.
    """
    # Invalida o cache antes de recalcular para garantir dados frescos
    _invalidate_monitor_view_cache(empresa)

    data = list_turnos(empresa=empresa, manual_refresh=manual_refresh, **kwargs)

    # Persiste no Firestore com itens completos (com DDS) para o listener em tempo real
    # Lemos do cache completo (antes do strip) para persistir os campos DDS
    full_cache = _read_monitor_view_cache(empresa)
    full_items = (full_cache.get("items") or []) if full_cache else data["items"]

    batch = db.batch()
    count = 0
    for item in full_items:
        # Persiste na coleção 'realtime'
        doc_ref = db.collection("turno").document(empresa).collection("realtime").document(item["teamKey"])
        batch.set(doc_ref, {
            **item,
            "viewUpdatedAt": firestore.SERVER_TIMESTAMP
        })
        count += 1
        if count >= 400:
            batch.commit()
            batch = db.batch()
            count = 0
            
    if count > 0:
        batch.commit()
        
    # Salva metadado da última atualização
    sync_time = _get_now().isoformat()
    db.collection("turno").document(empresa).set({
        "lastViewUpdate": sync_time,
        "lastViewUpdateBy": "MONITOR_SYNC"
    }, merge=True)
    
    # Atualiza metadados de produtividade
    update_productivity_metadata(empresa)
    
    # Retorna items sem DDS heavy (lazy loading via /api/turnos/dds)
    return {**data, "lastViewUpdate": sync_time}


_CONSOLIDATION_LOCKS = {} # { (empresa, team_key): last_consolidated_timestamp }
_locks_mutex = threading.Lock()


def consolidate_single_team(empresa: str, team_key: str) -> dict[str, Any]:
    """
    Consolida a visão de uma ÚNICA equipe e salva no Firestore Realtime.
    Evita buscar toda a base de dados do turno, mas utiliza o cache de DDS
    para garantir consistência e performance.
    """
    import time
    now_ts = time.time()
    lock_key = (empresa, team_key)
    with _locks_mutex:
        last_sync = _CONSOLIDATION_LOCKS.get(lock_key, 0)
        if now_ts - last_sync < 2.0:
            return {"ok": True, "skipped": True}
        _CONSOLIDATION_LOCKS[lock_key] = now_ts

    now = _get_now()
    rules = get_monitor_rules()
    
    # 1. Busca dados da equipe e do turno
    from services.teams_service import get_team
    from services.turno_equipes_service import get_turno_equipe
    team_data = get_team(team_key) or {}
    turno_doc = get_turno_equipe(empresa, team_key) or {}
    
    if not team_data and not turno_doc:
        # Se não existe em lugar nenhum, remove do realtime se existir
        db.collection("turno").document(empresa).collection("realtime").document(team_key).delete()
        return {"ok": True, "deleted": True}

    # 2. Carrega dependências de DDS e Mensagens (reutilizando caches e loaders)
    (
        recent_dds_days,
        dds_present_by_day,
        dds_days_with_any,
        mutable_dds_days,
        calendar_days,
        dds_timestamps_by_day,
        dds_photos_by_day,
    ) = _load_recent_dds_presence(manual_refresh=False)
    
    from services.messaging_service import get_unread_counts, get_all_unread_counts_map, get_last_messages_map
    unread_counts = get_unread_counts() # Setor padrão
    unread_map_global = get_all_unread_counts_map()
    last_messages_map = get_last_messages_map()

    # 3. Processa a equipe individualmente
    item = _process_single_team(
        team_key=team_key,
        empresa=empresa,
        team_data=team_data,
        data=turno_doc,
        recent_dds_days=recent_dds_days,
        dds_present_by_day=dds_present_by_day,
        dds_days_with_any=dds_days_with_any,
        mutable_dds_days=mutable_dds_days,
        calendar_days=calendar_days,
        dds_timestamps_by_day=dds_timestamps_by_day,
        dds_photos_by_day=dds_photos_by_day,
        unread_counts=unread_counts,
        unread_map_global=unread_map_global,
        last_messages_map=last_messages_map,
        now=now,
        rules=rules,
        pending_by_day={} # Não precisamos rastrear pendências globais na consolidação granular
    )
    
    if item:
        # 4. Salva no Firestore Realtime
        db.collection("turno").document(empresa).collection("realtime").document(team_key).set(item)
        
        # 5. ATUALIZAÇÃO INCREMENTAL: Em vez de invalidar tudo, 'remenda' o cache existente
        _patch_monitor_view_cache(empresa, item)

    return {"ok": True, "item": item}


def consolidate_team_across_all_companies(team_key: str):
    """Consolida a visão de uma equipe em todas as empresas registradas."""
    for empresa_doc in db.collection("turno").stream():
        consolidate_single_team(empresa_doc.id, team_key)


def get_team_keys_for_equipe_name(equipe_name: str) -> list[str]:
    if not equipe_name:
        return []
    norm_name = _normalize_text(equipe_name)
    teams = list_teams_map()
    matching_keys = []
    for team_key, team_data in teams.items():
        aliases = {
            _normalize_text(team_key),
            _normalize_text(team_data.get("teamKey")),
            _normalize_text(team_data.get("displayName")),
        }
        if any(_normalized_alias_matches(norm_name, alias) for alias in aliases):
            matching_keys.append(team_key)
    return matching_keys


def invalidate_dds_day_cache(day: str):
    with _cache_lock:
        _DDS_DAY_CACHE.pop(day, None)
    try:
        blob_name = _day_cache_blob(day)
        _storage_bucket().blob(blob_name).delete()
    except Exception:
        pass


class FirestoreListenerManager:
    def __init__(self):
        self.watches = []
        self.initial_equipes_done = False
        self.initial_dds_done = False
        self.initial_messages_done = False

    def start(self):
        print("Starting Firestore background listeners...")
        
        # 1. Listener para o Collection Group 'equipes' (turno/{empresa}/equipes)
        try:
            equipes_query = db.collection_group("equipes")
            watch_equipes = equipes_query.on_snapshot(self._on_equipes_snapshot)
            self.watches.append(watch_equipes)
        except Exception as e:
            print(f"Error starting equipes listener: {e}")

        # 2. Listener para a coleção 'DDS' (Filtrado pelos últimos 7 dias para reduzir leituras)
        try:
            from datetime import datetime, timedelta
            limite_data = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            print(f"Starting DDS listener filtered by headerDate >= {limite_data}")
            dds_query = db.collection(DDS_COLLECTION).where(filter=FieldFilter("headerDate", ">=", limite_data))
            watch_dds = dds_query.on_snapshot(self._on_dds_snapshot)
            self.watches.append(watch_dds)
        except Exception as e:
            print(f"Error starting DDS listener: {e}")

        # 3. Listener para a coleção 'mensagens_comunicacao'
        try:
            msg_query = db.collection("mensagens_comunicacao")
            watch_msg = msg_query.on_snapshot(self._on_messages_snapshot)
            self.watches.append(watch_msg)
        except Exception as e:
            print(f"Error starting messages listener: {e}")

    def stop(self):
        print("Stopping Firestore background listeners...")
        for watch in self.watches:
            try:
                watch.unsubscribe()
            except Exception:
                pass
        self.watches.clear()

    def _on_equipes_snapshot(self, col_snapshot, changes, read_time):
        if not self.initial_equipes_done:
            self.initial_equipes_done = True
            print(f"Equipes initial snapshot loaded: {len(changes)} documents. Skipping initial sync.")
            return

        print(f"Equipes change detected: {len(changes)} changes.")
        for change in changes:
            if change.type.name in ('ADDED', 'MODIFIED'):
                doc = change.document
                path = doc.reference.path
                parts = path.split("/")
                if len(parts) == 4 and parts[0] == "turno" and parts[2] == "equipes":
                    empresa = parts[1]
                    team_key = parts[3]
                    data = doc.to_dict() or {}
                    event_dt = data.get("serverUpdatedAt") or data.get("updatedAt") or _utc_now()
                    _record_team_activity(
                        empresa=empresa,
                        team_key=team_key,
                        equipe=data.get("equipe") or team_key,
                        source="turno",
                        activity_at=event_dt,
                        event_ref=doc.reference.path,
                        active_after_event=True,
                        extra={"estado": data.get("estado"), "nocSs": data.get("nocSs")},
                    )
                    print(f"Syncing team {team_key} for company {empresa} due to equipes update.")
                    threading.Thread(
                        target=consolidate_single_team,
                        args=(empresa, team_key),
                        daemon=True
                    ).start()

    def _on_dds_snapshot(self, col_snapshot, changes, read_time):
        if not self.initial_dds_done:
            self.initial_dds_done = True
            print(f"DDS initial snapshot loaded: {len(changes)} documents. Skipping initial sync.")
            return

        print(f"DDS change detected: {len(changes)} changes.")
        for change in changes:
            if change.type.name in ('ADDED', 'MODIFIED'):
                doc = change.document
                data = doc.to_dict() or {}
                equipe_name = data.get("equipe")
                header_date = data.get("headerDate")
                day = _extract_dds_day(header_date)
                
                if day:
                    print(f"Invalidating DDS cache for day {day}")
                    invalidate_dds_day_cache(day)
                
                if equipe_name:
                    team_keys = get_team_keys_for_equipe_name(equipe_name)
                    print(f"DDS activity trigger: equipe={equipe_name}, day={day}, matchedTeams={team_keys}")
                    for team_key in team_keys:
                        try:
                            event_data = {**data, "eventRef": doc.reference.path}
                            if getattr(doc, "create_time", None):
                                event_data["_doc_create_time"] = doc.create_time
                            if getattr(doc, "update_time", None):
                                event_data["_doc_update_time"] = doc.update_time
                            _apply_dds_activity_trigger(team_key, event_data, day, empresa=DEFAULT_EMPRESA)
                        except Exception as exc:
                            print(f"Error applying DDS activity trigger for {team_key}: {exc}")
                        print(f"Syncing team {team_key} due to DDS update of equipe {equipe_name}.")
                        threading.Thread(
                            target=consolidate_team_across_all_companies,
                            args=(team_key,),
                            daemon=True
                        ).start()

    def _on_messages_snapshot(self, col_snapshot, changes, read_time):
        if not self.initial_messages_done:
            self.initial_messages_done = True
            print(f"Messages initial snapshot loaded: {len(changes)} documents. Skipping initial sync.")
            return

        print(f"Messages change detected: {len(changes)} changes.")
        teams_to_sync = set()
        for change in changes:
            if change.type.name in ('ADDED', 'MODIFIED'):
                doc = change.document
                data = doc.to_dict() or {}
                from_equipe = data.get("fromEquipe")
                to_equipe = data.get("toEquipe")
                
                event_dt = data.get("sentAt") or data.get("timestamp") or data.get("serverUpdatedAt") or _utc_now()
                for name in (from_equipe, to_equipe):
                    if name:
                        matched = get_team_keys_for_equipe_name(name)
                        teams_to_sync.update(matched)
                        for team_key in matched:
                            _record_team_activity(
                                empresa=DEFAULT_EMPRESA,
                                team_key=team_key,
                                equipe=name,
                                source="mensagem",
                                activity_at=event_dt,
                                event_ref=doc.reference.path,
                                active_after_event=True,
                            )
        
        for team_key in teams_to_sync:
            print(f"Syncing team {team_key} due to message update.")
            threading.Thread(
                target=consolidate_team_across_all_companies,
                args=(team_key,),
                daemon=True
            ).start()
