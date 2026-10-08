# -----------------------------------------------------------------------------
# Arquivo : monitor/services/turnos_service.py
# Objetivo: Fachada (Facade) de alto nível para o serviço de turnos e monitor.
#           Reexporta módulos especializados, orquestra endpoints da API
#           e gerencia ouvintes em segundo plano do Firestore.
# -----------------------------------------------------------------------------

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from services.firestore_client import db
from services.teams_service import list_teams_map
from services.monitor_config_service import get_monitor_polling_seconds, get_monitor_rules
from services.messaging_service import CURRENT_SETOR

# 1. Reexportação de Utilitários e Constantes
from monitor.services.turnos_common import (
    APP_TITLE,
    DEFAULT_EMPRESA,
    POLLING_DEFAULT_SEC,
    DDS_HISTORY_DAYS,
    DDS_COLLECTION,
    DDS_TIMEZONE,
    DDS_MUTABLE_REFRESH_SEC,
    DDS_LAST_BUSINESS_REFRESH_SEC,
    DDS_BUCKET_NAME,
    DDS_CALENDAR_SOURCE_BLOB,
    DDS_CALENDAR_CACHE_BLOB,
    DDS_DAY_CACHE_PREFIX,
    DDS_PRESENCE_MODE,
    DDS_JSON_REFRESH_SEC,
    MONITOR_VIEW_CACHE_PREFIX,
    MONITOR_VIEW_CACHE_TTL_SEC,
    MONITOR_VIEW_LOCK_COLLECTION,
    get_monitor_source_ttl_seconds,
    WEBTOOLS_ROOT_COLLECTION,
    WEBTOOLS_MONITOR_DOC,
    AUTO_CLOSE_OPEN_HOURS_DEFAULT,
    AUTO_DESATUALIZA_FECHADO_HOURS_DEFAULT,
    AUTO_DESATUALIZA_INTERVALO_HOURS_DEFAULT,
    AUTO_REASON_CLOSE_OPEN,
    AUTO_REASON_DESAT_FECHADO,
    AUTO_REASON_DESAT_DESLOCAMENTO,
    AUTO_REASON_DESAT_INTERVALO,
    AUTO_REASON_INACTIVE_UNKNOWN,
    to_utc_dt,
    _get_now,
    _utc_now,
    _utc_now_iso,
    _parse_iso_datetime,
    _local_today,
    _local_day_key,
    _same_utc_dt,
    normalize_estado,
    normalize_rotalog_turn_state,
    string_list,
    extract_participantes,
    _normalize_text,
    _normalized_alias_matches,
    _build_team_aliases,
    _DatetimeEncoder,
    _storage_client,
    _storage_bucket,
    _storage_blob_name,
    _storage_read_json,
    _storage_write_json,
)

# 2. Reexportação de Gestão de Presença e Cache DDS
from monitor.services.dds_presence_service import (
    _DDS_DAY_CACHE,
    _DDS_CALENDAR_CACHE,
    _RECENT_7D_DDS_CACHE,
    _recent_history_days,
    _last_business_day,
    _mutable_dds_days,
    _prune_dds_day_cache,
    _should_refresh_dds_day,
    _extract_dds_day,
    _parse_dds_time_value,
    _combine_dds_day_time,
    _dds_day_to_effective_contact_dt,
    _extract_dds_timestamp,
    _collect_manifest_days,
    _calendar_payload_to_days,
    _load_calendar_source_days,
    _calendar_cache_is_fresh,
    _load_dds_calendar_days,
    _day_cache_blob,
    _serialize_day_cache,
    _deserialize_day_cache,
    _load_storage_day_cache,
    _save_storage_day_cache,
    _day_refresh_seconds,
    _should_refresh_day_entry,
    _build_day_cache_entry,
    _load_day_presence_with_cache,
    _force_refresh_days,
    _build_manual_refresh_days,
    _latest_dds_ts_for_aliases,
    _load_dds_presence_for_day,
    _load_recent_dds_presence,
    _load_day_dds_teams,
    _load_today_dds_teams,
    _load_recent_7d_dds_teams,
    _has_dds_in_recent_map,
    invalidate_dds_day_cache,
    get_team_dds_data,
)

# 3. Reexportação de Activity Feed e Eventos
from monitor.services.turnos_activity_service import (
    _webtools_monitor_ref,
    _monitor_subcollection,
    _turno_doc_ref,
    _team_doc_ref,
    _safe_merge,
    _activity_event_id,
    _activity_label,
    _activity_feed_item,
    _update_activity_feed,
    _record_team_activity,
    _read_activity_feed,
    get_activity_feed,
    _persist_team_activity_if_newer,
    _manual_inactive_blocks_activity,
    _persist_team_active_state,
    _apply_dds_activity_trigger,
    _describe_team_change_details,
)

# 4. Reexportação do Construtor da Torre de Controle
from monitor.services.torre_monitor_builder import (
    _MONITOR_VIEW_CACHE,
    _monitor_view_cache_blob,
    _read_monitor_view_cache,
    _write_monitor_view_cache,
    _invalidate_monitor_view_cache,
    _patch_monitor_view_cache,
    _rotalog_json_snapshots,
    _overlay_rotalog_json,
    _build_pure_torre_items,
    _build_dds_controlled_items,
)

# 5. Reexportação de Sincronização Legada
from monitor.services.turnos_legacy_sync import (
    consolidate_single_team,
    consolidate_team_across_all_companies,
    update_realtime_view,
)

logger = logging.getLogger(__name__)

_LOCAL_CACHE_REFRESH_LOCK = threading.Lock()
_LOCAL_CACHE_REFRESH_IN_FLIGHT: set[str] = set()


# ---------------------------------------------------------------------------
# Endpoints e Funções de Orquestração do Monitor
# ---------------------------------------------------------------------------

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
    from monitor.services.dds_presence_service import _cache_lock as dds_lock
    from monitor.services.torre_monitor_builder import _cache_lock as torre_lock

    with dds_lock:
        _DDS_DAY_CACHE.clear()
        _DDS_CALENDAR_CACHE.clear()
        _RECENT_7D_DDS_CACHE.clear()
        _RECENT_7D_DDS_CACHE.update({"fetched_at": 0.0, "teams": {}})

    with torre_lock:
        _MONITOR_VIEW_CACHE.clear()

    try:
        from services.teams_service import clear_teams_cache
        clear_teams_cache()
    except ImportError:
        pass


def update_productivity_metadata(empresa: str = DEFAULT_EMPRESA):
    """
    Atualiza o documento de metadados da produtividade com a última competência
    e listas de filtros disponíveis (cidades, bases, etc).
    """
    try:
        from produtividade.services.productivity_service import get_latest_competence, list_productivity_data

        year, month = get_latest_competence()
        if not year or not month:
            return

        competencia = f"{year}-{month:02d}"
        data_latest = list_productivity_data(year=year, month=month)

        cities = sorted(list(set(d.get("cityBase") for d in data_latest if d.get("cityBase"))))
        bases = sorted(list(set(d.get("base") for d in data_latest if d.get("base"))))
        agencies = sorted(list(set(d.get("agency") for d in data_latest if d.get("agency"))))

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


def _cached_turnos_response(
    cached: dict[str, Any],
    active: bool | None,
    setor: str,
    *,
    stale: bool = False,
) -> dict[str, Any]:
    items = cached.get("items") or []
    if active is not None:
        items = [item for item in items if bool(item.get("active")) is active]
    cached_response = {key: value for key, value in cached.items() if key != "_cachedAt"}
    return {
        **cached_response,
        "items": items,
        "activeFilter": active,
        "currentSector": setor,
        "cachedView": True,
        "staleCache": stale,
    }


def _claim_monitor_cache_refresh(empresa: str, lease_seconds: int = 45) -> bool:
    """Claims a short Firestore lease so only one server refreshes a stale view."""
    transaction = db.transaction()
    lock_ref = db.collection(MONITOR_VIEW_LOCK_COLLECTION).document(empresa)
    now = _utc_now()

    @firestore.transactional
    def claim(transaction):
        snapshot = lock_ref.get(transaction=transaction)
        expires_at = to_utc_dt(snapshot.to_dict().get("expiresAt")) if snapshot.exists else None
        if expires_at and expires_at > now:
            return False
        transaction.set(lock_ref, {
            "empresa": empresa,
            "expiresAt": now + timedelta(seconds=lease_seconds),
            "updatedAt": firestore.SERVER_TIMESTAMP,
        }, merge=True)
        return True

    try:
        return bool(claim(transaction))
    except Exception as exc:
        logger.warning("Não foi possível obter trava de atualização do cache (%s): %s", empresa, exc)
        return False


def _release_monitor_cache_refresh(empresa: str) -> None:
    try:
        db.collection(MONITOR_VIEW_LOCK_COLLECTION).document(empresa).delete()
    except Exception:
        pass


def list_turnos(
    empresa: str,
    active: bool | None = None,
    *,
    manual_refresh: bool = False,
    setor: str = CURRENT_SETOR,
    _skip_cache: bool = False,
    files_only: bool = False,
) -> dict[str, Any]:
    if files_only:
        return _list_turnos_from_files(empresa, active, setor, manual_refresh=manual_refresh)
    refresh_lease_claimed = False
    local_refresh_claimed = False
    cached = _read_monitor_view_cache(empresa) if not manual_refresh else None
    if cached and cached.get("items") and not _skip_cache:
        cached_at = _parse_iso_datetime(cached.get("_cachedAt"))
        cache_age = (_utc_now() - cached_at).total_seconds() if cached_at else None
        if cache_age is not None and cache_age < get_monitor_source_ttl_seconds():
            return _cached_turnos_response(cached, active, setor)

        with _LOCAL_CACHE_REFRESH_LOCK:
            if empresa in _LOCAL_CACHE_REFRESH_IN_FLIGHT:
                return _cached_turnos_response(cached, active, setor, stale=True)
            _LOCAL_CACHE_REFRESH_IN_FLIGHT.add(empresa)
            local_refresh_claimed = True

        if not _claim_monitor_cache_refresh(empresa):
            with _LOCAL_CACHE_REFRESH_LOCK:
                _LOCAL_CACHE_REFRESH_IN_FLIGHT.discard(empresa)
            local_refresh_claimed = False
            return _cached_turnos_response(cached, active, setor, stale=True)
        refresh_lease_claimed = True

    try:
        now = _get_now()
        rotalog_snapshots = _rotalog_json_snapshots(force=manual_refresh)

        try:
            teams_map = list_teams_map(active=None) or {}
        except Exception as exc:
            logger.warning("Não foi possível carregar teams_map em list_turnos: %s", exc)
            teams_map = {}

        now_local = now.astimezone(ZoneInfo(DDS_TIMEZONE)) if DDS_TIMEZONE else now
        today_iso = now_local.date().isoformat()
        recent_7d_dds = _load_recent_7d_dds_teams(now_local, manual_refresh=manual_refresh)
        today_dds_teams = _load_today_dds_teams(today_iso, manual_refresh=manual_refresh)

        from monitor.services.dds_control_projection import sync_recent_daily_projections
        daily_projections = sync_recent_daily_projections(limit_days=25, manual_refresh=manual_refresh)

        pure_items = _build_pure_torre_items(
            rotalog_snapshots,
            now,
            teams_map=teams_map,
            recent_7d_dds=recent_7d_dds,
            manual_refresh=manual_refresh,
            daily_projections=daily_projections,
        ) if rotalog_snapshots else []
        telemetry_keys = {str(it.get("teamKey") or "").strip().upper() for it in pure_items}
        dds_items = _build_dds_controlled_items(
            telemetry_keys,
            now,
            teams_map=teams_map,
            recent_7d_dds=recent_7d_dds,
            manual_refresh=manual_refresh,
            today_dds_teams=today_dds_teams,
            daily_projections=daily_projections,
        )
        all_items = pure_items + dds_items

        if all_items:
            all_items.sort(key=lambda x: (str(x.get("equipe") or ""), str(x.get("teamKey") or "")))

        full_result = {
            "empresa": empresa,
            "serverTime": now.isoformat(),
            "manualRefresh": manual_refresh,
            "persistenceMode": os.getenv("ROTALOG_PERSISTENCE_MODE", "json").strip().lower(),
            "items": all_items,
            "dataSource": "torre_controle",
        }
        _write_monitor_view_cache(empresa, full_result)

        items = all_items if active is None else [it for it in all_items if bool(it.get("active")) is active]
        return {
            **full_result,
            "items": items,
            "activeFilter": active,
            "currentSector": setor,
        }
    finally:
        if refresh_lease_claimed:
            _release_monitor_cache_refresh(empresa)
        if local_refresh_claimed:
            with _LOCAL_CACHE_REFRESH_LOCK:
                _LOCAL_CACHE_REFRESH_IN_FLIGHT.discard(empresa)


# Campos de histórico DDS que são carregados separadamente via /api/turnos/dds
_DDS_HEAVY_FIELDS = {"ddsHistory", "ddsDays", "ddsTimes", "ddsPhotos"}


def _list_turnos_from_files(
    empresa: str, active: bool | None, setor: str, *, manual_refresh: bool = False,
) -> dict[str, Any]:
    """Atualiza a tela apenas com arquivos consolidados, sem consultar registros fonte."""
    from monitor.services.dds_control_projection import sync_recent_daily_projections
    from monitor.services.torre_monitor_builder import _cache_lock

    cached = _read_monitor_view_cache(empresa) or {}
    teams_map = {
        str(item.get("teamKey") or "").strip().upper(): {
            **item,
            "displayName": item.get("equipe"),
            "members": item.get("participantes") or [],
        }
        for item in cached.get("items") or []
        if item.get("teamKey")
    }
    now = _get_now()
    today = now.astimezone(ZoneInfo(DDS_TIMEZONE)).date()
    projections = sync_recent_daily_projections(limit_days=25, manual_refresh=True)
    _, by_day = projections
    today_teams = (by_day.get(today.isoformat()) or {}).get("teams") or {}
    recent_teams: dict[str, dict[str, Any]] = {}
    for day in sorted(by_day):
        if not (today - timedelta(days=6)).isoformat() <= day <= today.isoformat():
            continue
        for key, entry in (by_day[day].get("teams") or {}).items():
            recent_teams[key] = {
                **entry,
                "completedAt": entry.get("completedAt") or f"{day}T07:00:00-03:00",
                "date": day,
            }
    snapshots = _rotalog_json_snapshots(force=True)
    from bdo.services.rotalog_sync_task import _durable_cache_state
    pure_items = _build_pure_torre_items(
        snapshots, now, teams_map=teams_map, recent_7d_dds=recent_teams,
        daily_projections=projections,
    )
    telemetry_keys = {str(item.get("teamKey") or "").strip().upper() for item in pure_items}
    dds_items = _build_dds_controlled_items(
        telemetry_keys, now, teams_map=teams_map, recent_7d_dds=recent_teams,
        today_dds_teams=today_teams, daily_projections=projections,
    )
    items = sorted(pure_items + dds_items, key=lambda item: (
        str(item.get("equipe") or ""), str(item.get("teamKey") or ""),
    ))
    result = {
        "empresa": empresa, "serverTime": now.isoformat(),
        "manualRefresh": manual_refresh, "persistenceMode": "json",
        "items": items, "dataSource": "monitor_files",
        "rotalogSource": _durable_cache_state.get("source", "unknown"),
    }
    # O histórico DDS da segunda requisição usa esta mesma leitura dos arquivos.
    with _cache_lock:
        _MONITOR_VIEW_CACHE[empresa] = {**result, "_cachedAt": _utc_now_iso()}
    return {
        **result,
        "items": items if active is None else [item for item in items if bool(item.get("active")) is active],
        "activeFilter": active, "currentSector": setor,
    }


def _strip_dds_history(item: dict[str, Any]) -> dict[str, Any]:
    """Remove campos pesados de DDS de um item, mantendo apenas ddsToday."""
    return {k: v for k, v in item.items() if k not in _DDS_HEAVY_FIELDS}


def list_turnos_dds(empresa: str, active: bool | None = None) -> dict[str, Any]:
    """
    Retorna apenas os campos de histórico DDS por equipe, lendo do cache.
    Usado pelo endpoint GET /api/turnos/dds para carga lazy no frontend.
    """
    cache = _read_monitor_view_cache(empresa)
    if not cache or not cache.get("items"):
        res = list_turnos(empresa=empresa, active=active, files_only=True)
        all_items = res.get("items") or []
    else:
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


# ---------------------------------------------------------------------------
# Gestor de Ouvintes Firestore (Listeners)
# ---------------------------------------------------------------------------

class FirestoreListenerManager:
    def __init__(self):
        self.watches = []
        self.initial_equipes_done = False
        self.initial_dds_done = False

    def start(self):
        print("Iniciando ouvintes em segundo plano do Firestore...")

        # 1. Listener para o Collection Group 'equipes' (turno/{empresa}/equipes) DESABILITADO:
        # A persistência opera no modo JSON/Storage (index.json.gz), eliminando leituras
        # e snapshots desnecessários de centenas de documentos a cada inicialização do servidor.

        # 2. Somente DDS de hoje em diante; histórico é carregado sob demanda e mantido em cache.
        try:
            limite_data = datetime.now().strftime("%Y-%m-%d")
            print(f"Iniciando ouvinte de DDS a partir de hoje: headerDate >= {limite_data}")
            dds_query = db.collection(DDS_COLLECTION).where(filter=FieldFilter("headerDate", ">=", limite_data))
            watch_dds = dds_query.on_snapshot(self._on_dds_snapshot)
            self.watches.append(watch_dds)
        except Exception as e:
            print(f"Erro ao iniciar ouvinte de DDS: {e}")

    def stop(self):
        print("Parando ouvintes em segundo plano do Firestore...")
        for watch in self.watches:
            try:
                watch.unsubscribe()
            except Exception:
                pass
        self.watches.clear()

    def _on_equipes_snapshot(self, col_snapshot, changes, read_time):
        if not self.initial_equipes_done:
            self.initial_equipes_done = True
            print(f"Snapshot inicial de equipes carregado: {len(changes)} documentos. Ignorando sincronização inicial.")
            return

        print(f"Alteração em equipes detectada: {len(changes)} alterações.")
        teams_to_sync: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
        for change in changes:
            if change.type.name in ('ADDED', 'MODIFIED'):
                doc = change.document
                path = doc.reference.path
                parts = path.split("/")
                if len(parts) == 4 and parts[0] == "turno" and parts[2] == "equipes":
                    empresa = parts[1]
                    team_key = parts[3]
                    data = doc.to_dict() or {}
                    is_rotalog_update = str(data.get("deviceIdLastWriter") or "").upper() == "ROTALOG_AUTO_SYNC"
                    event_dt = data.get("serverUpdatedAt") or data.get("updatedAt") or _utc_now()
                    _record_team_activity(
                        empresa=empresa,
                        team_key=team_key,
                        equipe=data.get("equipe") or team_key,
                        source="rotalog" if is_rotalog_update else "turno",
                        activity_at=event_dt,
                        event_ref=doc.reference.path,
                        active_after_event=True,
                        extra={"estado": data.get("estado"), "nocSs": data.get("nocSs")},
                        persist_history=not is_rotalog_update,
                        persist_team=not is_rotalog_update,
                    )
                    detail_line = _describe_team_change_details(data, team_key=team_key, empresa=empresa)
                    teams_to_sync[(empresa, team_key)] = (detail_line, data)

        for (empresa, team_key), (detail, turno_data) in teams_to_sync.items():
            print(detail)
            threading.Thread(
                target=consolidate_single_team,
                args=(empresa, team_key),
                kwargs={"turno_data": turno_data},
                daemon=True
            ).start()

    def _on_dds_snapshot(self, col_snapshot, changes, read_time):
        if not self.initial_dds_done:
            self.initial_dds_done = True
            print(f"Snapshot inicial de DDS carregado: {len(changes)} documentos. Ignorando sincronização inicial.")
            return

        print(f"Alteração em DDS detectada: {len(changes)} alterações.")
        for change in changes:
            if change.type.name in ('ADDED', 'MODIFIED'):
                doc = change.document
                data = doc.to_dict() or {}
                equipe_name = data.get("equipe")
                header_date = data.get("headerDate")
                day = _extract_dds_day(header_date)

                if day:
                    print(f"Invalidando cache de presença de DDS para a data {day}")
                    invalidate_dds_day_cache(day)

                if equipe_name:
                    team_keys = get_team_keys_for_equipe_name(equipe_name)
                    print(f"Gatilho de atividade DDS: equipe={equipe_name}, data={day}, equipesEncontradas={team_keys}")
                    for team_key in team_keys:
                        try:
                            event_data = {**data, "eventRef": doc.reference.path}
                            if getattr(doc, "create_time", None):
                                event_data["_doc_create_time"] = doc.create_time
                            if getattr(doc, "update_time", None):
                                event_data["_doc_update_time"] = doc.update_time
                            _apply_dds_activity_trigger(team_key, event_data, day, empresa=DEFAULT_EMPRESA)
                        except Exception as exc:
                            print(f"Erro ao aplicar gatilho de atividade DDS para {team_key}: {exc}")
                        print(f"Sincronizando a equipe {team_key} devido à atualização de DDS da equipe {equipe_name}.")
                        threading.Thread(
                            target=consolidate_team_across_all_companies,
                            args=(team_key,),
                            daemon=True
                        ).start()
