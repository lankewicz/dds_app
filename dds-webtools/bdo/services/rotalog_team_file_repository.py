"""Arquivos operacionais ROTALOG por equipe.

Current e daily usam JSON gzip. O consolidado mensal usa Parquet e é derivado
exclusivamente dos arquivos diários, sem gravar dados operacionais no Firestore.
"""

from __future__ import annotations

import datetime
import hashlib
import io
import logging
import os
import threading
import typing
from zoneinfo import ZoneInfo

from bdo.services.rotalog_change_tracker import RotalogGcsSnapshotStore

logger = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo(os.getenv("DDS_TIMEZONE", "America/Sao_Paulo"))


def _safe_team_key(value: str) -> str:
    key = str(value or "").strip().upper()
    if not re.fullmatch(r"E[A-Z0-9]{3,7}", key):
        raise ValueError("Codigo de equipe invalido")
    return key


def _iso_local(value: typing.Any, day: str | None = None) -> str | None:
    if value in (None, "", "-"):
        return None
    raw = str(value).strip()
    if len(raw) == 5 and raw[2] == ":" and day:
        try:
            return datetime.datetime.fromisoformat(f"{day}T{raw}:00").replace(tzinfo=LOCAL_TZ).isoformat()
        except ValueError:
            return None
    try:
        parsed = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LOCAL_TZ)
        return parsed.astimezone(LOCAL_TZ).isoformat()
    except ValueError:
        return None


def _extrair_data_base(service: dict[str, typing.Any], day: str) -> str:
    """Extrai a data base real do serviço (YYYY-MM-DD), evitando assumir horas futuras."""
    for field in ("inicioIso", "inicio_iso", "fimIso", "fim_iso"):
        val = str(service.get(field) or "").strip()
        if len(val) >= 10 and val[4] == "-" and val[7] == "-":
            try:
                datetime.date.fromisoformat(val[:10])
                return val[:10]
            except ValueError:
                pass

    for field in ("inicio_ms", "timestampMs", "start"):
        val = service.get(field)
        if isinstance(val, (int, float)) and val > 1000000000000:
            dt = datetime.datetime.fromtimestamp(val / 1000, LOCAL_TZ)
            return dt.date().isoformat()

    hora_str = str(service.get("inicioDeslocamento") or service.get("inicioExecucao") or "").strip()
    if len(hora_str) == 5 and hora_str[2] == ":":
        try:
            ref_dt = datetime.datetime.fromisoformat(f"{day}T{hora_str}:00").replace(tzinfo=LOCAL_TZ)
            agora = datetime.datetime.now(LOCAL_TZ)
            if day == agora.date().isoformat() and ref_dt > agora + datetime.timedelta(minutes=15):
                ontem = (datetime.date.fromisoformat(day) - datetime.timedelta(days=1)).isoformat()
                return ontem
        except Exception:
            pass

    return day


def _formatar_horarios_servico(
    service: dict[str, typing.Any],
    base_day: str,
) -> dict[str, str | None]:
    """Formata os 4 tempos operacionais com suporte a virada de meia-noite e sem inversões."""
    raw_desloc = service.get("inicioDeslocamento") or service.get("inicioIso")
    raw_exec = service.get("inicioExecucao") or service.get("inicioIso")
    raw_fim = service.get("termino") or service.get("fimIso") or service.get("fimExecucao")
    raw_retorno = service.get("retorno")

    cur_day = datetime.date.fromisoformat(base_day)
    prev_dt: datetime.datetime | None = None

    result: dict[str, str | None] = {
        "inicioDeslocamento": None,
        "inicioExecucao": None,
        "fimExecucao": None,
        "retorno": None,
    }

    for key, raw_val in [
        ("inicioDeslocamento", raw_desloc),
        ("inicioExecucao", raw_exec),
        ("fimExecucao", raw_fim),
        ("retorno", raw_retorno),
    ]:
        if not raw_val or str(raw_val).strip() in ("", "-"):
            continue

        raw_str = str(raw_val).strip()
        dt_val: datetime.datetime | None = None

        if len(raw_str) == 5 and raw_str[2] == ":":
            try:
                candidate = datetime.datetime.fromisoformat(f"{cur_day.isoformat()}T{raw_str}:00").replace(tzinfo=LOCAL_TZ)
                # Virada de meia-noite REAL: só avança de dia se o anterior era noite (>= 21h) e o atual é madrugada (< 06h)
                if prev_dt and prev_dt.hour >= 21 and int(raw_str[:2]) < 6:
                    cur_day = cur_day + datetime.timedelta(days=1)
                    candidate = datetime.datetime.fromisoformat(f"{cur_day.isoformat()}T{raw_str}:00").replace(tzinfo=LOCAL_TZ)
                dt_val = candidate
            except ValueError:
                dt_val = None
        else:
            try:
                parsed = datetime.datetime.fromisoformat(raw_str.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=LOCAL_TZ)
                dt_val = parsed.astimezone(LOCAL_TZ)
            except ValueError:
                dt_val = None

        if dt_val:
            prev_dt = dt_val
            result[key] = dt_val.isoformat()

    # Normalização de coerência cronológica estrita:
    # 1. inicioExecucao não pode ser anterior a inicioDeslocamento (artefato de hora de abertura de chamado no call center)
    if result["inicioDeslocamento"] and result["inicioExecucao"]:
        if result["inicioExecucao"] < result["inicioDeslocamento"]:
            result["inicioExecucao"] = result["inicioDeslocamento"]

    # 2. fimExecucao não pode ser anterior a inicioExecucao
    if result["inicioExecucao"] and result["fimExecucao"]:
        if result["fimExecucao"] < result["inicioExecucao"]:
            result["fimExecucao"] = result["inicioExecucao"]

    # 3. retorno não pode ser anterior a fimExecucao
    if result["fimExecucao"] and result["retorno"]:
        if result["retorno"] < result["fimExecucao"]:
            result["retorno"] = result["fimExecucao"]

    return result


import re

def _eh_protocolo_valido(prot: typing.Any) -> bool:
    if not prot:
        return False
    s = str(prot).strip()
    return bool(re.match(r"^\d{7,15}(\.\d+)*$", s))


def _service_id(team_key: str, service: dict[str, typing.Any]) -> str:
    existing = str(service.get("serviceId") or "").strip()
    if existing:
        if not existing.startswith(team_key + "_"):
            raise ValueError("serviceId pertence a outra equipe")
        return existing
    identity = "|".join(
        str(value or "")
        for value in (
            team_key,
            service.get("inicioIso") or service.get("inicioDeslocamento") or service.get("inicioExecucao"),
            service.get("sequencia"),
        )
    )
    return f"{team_key}_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"


def compact_service(team_key: str, day: str, service: dict[str, typing.Any]) -> dict[str, typing.Any]:
    lat = service.get("latitude")
    lon = service.get("longitude")
    if lat is None and isinstance(service.get("geolocalizacao"), dict):
        lat = service["geolocalizacao"].get("latitude")
        lon = service["geolocalizacao"].get("longitude")

    fila_conclusao = service.get("filaNaConclusao")
    if fila_conclusao is None and service.get("servicosPendentesNaConclusao") is not None:
        fila_conclusao = {
            "emergencia": int(service.get("emergenciasPendentesNaConclusao") or 0),
            "comercial": int(service.get("comerciaisPendentesNaConclusao") or 0),
        }
    elif isinstance(fila_conclusao, dict):
        fila_conclusao = {
            "emergencia": int(fila_conclusao.get("emergencia") or 0),
            "comercial": int(fila_conclusao.get("comercial") or 0),
        }

    status_atual = service.get("status") or service.get("statusAtual")
    base_day = _extrair_data_base(service, day)
    horarios = _formatar_horarios_servico(service, base_day)

    result = {
        "categoria": service.get("categoria"),
        "tipo": service.get("tipo"),
        "protocolo": service.get("protocolo") or service.get("ssId") or None,
        "inicioDeslocamento": horarios["inicioDeslocamento"],
        "inicioExecucao": horarios["inicioExecucao"],
        "fimExecucao": horarios["fimExecucao"],
        "retorno": horarios["retorno"],
        "latitude": lat,
        "longitude": lon,
        "serviceId": _service_id(team_key, service),
        "statusAtual": status_atual,
        "sequencia": service.get("sequencia") or None,
        "baseDay": base_day,
        "camposEstimados": list(service.get("camposEstimados") or []),
    }
    if fila_conclusao is not None and status_atual == "CONCLUSAO":
        result["filaNaConclusao"] = fila_conclusao
    return result


def _compact_interval(day: str, interval: dict[str, typing.Any]) -> dict[str, typing.Any] | None:
    start = _iso_local(interval.get("inicioIso"), day)
    if not start and interval.get("inicio_ms"):
        start = _iso_local(datetime.datetime.fromtimestamp(int(interval["inicio_ms"]) / 1000, datetime.timezone.utc).isoformat(), day)
    if not start:
        return None
    end = _iso_local(interval.get("fimIso"), day)
    if not end and interval.get("fim_ms"):
        end = _iso_local(datetime.datetime.fromtimestamp(int(interval["fim_ms"]) / 1000, datetime.timezone.utc).isoformat(), day)
    return {"inicio": start, "fim": end}


def _merge_service_records(team_key, records):
    """Mescla somente identidade exata; conserva conflitos de identificador."""
    result = {}
    keys = {}
    for incoming in records:
        item = dict(incoming)
        sid = _service_id(team_key, item)
        start = item.get("inicioDeslocamento") or item.get("inicioExecucao")
        prot = str(item.get("protocolo") or "").strip()
        key = (team_key, start, prot) if start and _eh_protocolo_valido(prot) else None
        target = keys.get(key, sid) if key else sid
        old = result.get(target, {})
        old_prot = str(old.get("protocolo") or "").strip()
        old_start = old.get("inicioDeslocamento") or old.get("inicioExecucao")
        if old and ((old_prot and prot and old_prot != prot) or
                    (old_start and start and old_start != start)):
            suffix = hashlib.sha256(repr((sid, start, prot)).encode()).hexdigest()[:24]
            target = f"{team_key}_{suffix}"
            old = result.get(target, {})
        merged = dict(old)
        old_time = old.get("observadoEm")
        new_time = item.get("observadoEm")
        stale = bool(old_time and new_time and
                     datetime.datetime.fromisoformat(new_time) < datetime.datetime.fromisoformat(old_time))
        for field, value in item.items():
            if value is not None and value != "" and (not stale or merged.get(field) in (None, "")):
                merged[field] = value
        if old.get("statusAtual") == "CONCLUSAO" and item.get("statusAtual") in ("EXECUCAO", "DESLOCAMENTO"):
            merged["statusAtual"] = "CONCLUSAO"
        tipos = list(old.get("historicoTipos") or [])
        for tipo in (old.get("tipo"), item.get("tipo")):
            if tipo and tipo not in tipos:
                tipos.append(tipo)
        if tipos:
            merged["historicoTipos"] = tipos
        merged["serviceId"] = target
        result[target] = merged
        if key:
            keys[key] = target
    return result


def merge_daily_document(
    previous: dict[str, typing.Any] | None,
    current: dict[str, typing.Any],
    day: str,
) -> dict[str, typing.Any]:
    team_key = _safe_team_key(current.get("teamKey") or current.get("equipe"))
    previous = previous or {}
    if previous.get("teamKey") and previous["teamKey"] != team_key:
        raise ValueError("Historico pertence a outra equipe")
    if previous.get("date") and previous["date"] != day:
        raise ValueError("Historico pertence a outra data")
    records = [dict(s) for s in previous.get("services", [])]
    for field in ("ssExecutadas", "ssEmAndamento", "services"):
        for raw in current.get(field) or []:
            item = compact_service(team_key, day, raw)
            item["observadoEm"] = current.get("updatedAtIso")
            for meta in ("fonteProtocolo", "validacaoProtocolo", "protocoloBruto"):
                if raw.get(meta) is not None:
                    item[meta] = raw[meta]
            if item.get("statusAtual") == "CONCLUSAO" and "filaNaConclusao" not in item:
                item["filaNaConclusao"] = {
                    "emergencia": int(current.get("ssPendentesEmergenciaCount") or 0),
                    "comercial": int(current.get("ssPendentesComercialCount") or 0),
                }
            records.append(item)
    service_map = _merge_service_records(team_key, records)

    interval_map = {
        str(item.get("inicio")): dict(item)
        for item in ((previous.get("turno") or {}).get("intervalos") or [])
        if isinstance(item, dict) and item.get("inicio")
    }
    raw_intervals = current.get("intervalos") or []
    if not raw_intervals and current.get("intervalo"):
        raw_intervals = [current["intervalo"]]
    for raw_interval in raw_intervals:
        compact_interval = _compact_interval(day, raw_interval)
        if compact_interval:
            previous_interval = interval_map.get(compact_interval["inicio"], {})
            interval_map[compact_interval["inicio"]] = {
                **previous_interval,
                **{key: value for key, value in compact_interval.items() if value is not None},
            }

    turno = current.get("turno") or {}
    services = [
        srv for srv in sorted(service_map.values(), key=lambda item: str(item.get("inicioDeslocamento") or item.get("inicioExecucao") or ""))
        if (srv.get("baseDay") == day or str(srv.get("inicioDeslocamento") or srv.get("inicioExecucao") or "")[:10] == day)
    ]
    activity_raw = current.get("atividadeAtual") or {}
    current_service = compact_service(team_key, day, activity_raw) if activity_raw else None

    # GARANTIA ESTRITA: No máximo 1 único serviço pode estar em EXECUCAO/DESLOCAMENTO por equipe
    active_in_list = [srv for srv in services if srv.get("statusAtual") in ("EXECUCAO", "DESLOCAMENTO")]
    if active_in_list:
        if current_service is None:
            for srv in active_in_list:
                srv["statusAtual"] = "REDIRECIONADO"
                srv["semExecucaoType"] = "REDIRECIONADO"
                srv["fimExecucao"] = srv.get("fimExecucao") or srv.get("inicioExecucao") or srv.get("inicioDeslocamento")
                srv["retorno"] = srv["fimExecucao"]
        elif len(active_in_list) > 1:
            active_most_recent = max(active_in_list, key=lambda item: str(item.get("inicioDeslocamento") or item.get("inicioExecucao") or ""))
            for srv in active_in_list:
                if srv != active_most_recent:
                    proximo_ini = active_most_recent.get("inicioDeslocamento") or active_most_recent.get("inicioExecucao")
                    srv["statusAtual"] = "REDIRECIONADO"
                    srv["semExecucaoType"] = "REDIRECIONADO"
                    srv["fimExecucao"] = proximo_ini or srv.get("inicioExecucao") or srv.get("inicioDeslocamento")
                    srv["retorno"] = srv["fimExecucao"]

    prev_version = int((previous.get("current") or {}).get("version") or 0)
    prev_date = str(previous.get("date") or "")
    if prev_date != day:
        daily_version = 1
    else:
        daily_version = (prev_version + 1) if previous else 1

    return {
        "schemaVersion": 1,
        "teamKey": team_key,
        "date": day,
        "updatedAt": current.get("updatedAtIso"),
        "current": {
            "version": daily_version,
            "turnStatus": current.get("estadoConsolidado"),
            "service": current_service,
        },
        "turno": {
            "status": current.get("estadoConsolidado"),
            "inicio": _iso_local(turno.get("inicio_iso"), day),
            "fim": _iso_local(turno.get("fim_iso"), day),
            "ultimoServicoId": services[-1]["serviceId"] if services else None,
            "intervalos": sorted(interval_map.values(), key=lambda item: str(item.get("inicio") or "")),
        },
        "services": services,
    }


class RotalogTeamFileRepository:
    def __init__(self, store: RotalogGcsSnapshotStore, root_prefix: str | None = None):
        self.store = store
        self.root_prefix = (root_prefix or os.getenv("ROTALOG_TEAM_STORAGE_PREFIX", "dados/chicoeletro/rotalog/equipes")).strip().strip("/")
        self._daily_cache: dict[tuple[str, str], dict[str, typing.Any]] = {}
        self._monthly_state: dict[str, typing.Any] | None = None
        self._turn_check_state: dict[str, typing.Any] | None = None
        self._lock = threading.RLock()

    def current_path(self, team_key: str) -> str:
        return f"{self.root_prefix}/current/{_safe_team_key(team_key)}.json.gz"

    def daily_path(self, day: str, team_key: str) -> str:
        if datetime.date.fromisoformat(day).isoformat() != day:
            raise ValueError("Data invalida")
        return f"{self.root_prefix}/daily/{day}/{_safe_team_key(team_key)}.json.gz"

    def index_path(self) -> str:
        return f"{self.root_prefix}/current/index.json.gz"

    def _save_current_at(self, path: str, document: dict[str, typing.Any]) -> None:
        if hasattr(self.store, "update_blob"):
            def escolher(previous):
                old = previous.get("updatedAtIso") or previous.get("updatedAt")
                new = document.get("updatedAtIso") or document.get("updatedAt")
                if old and new and datetime.datetime.fromisoformat(str(old).replace("Z", "+00:00")) > datetime.datetime.fromisoformat(str(new).replace("Z", "+00:00")):
                    return previous
                return document
            self.store.update_blob(path, escolher)
        else:
            self.store.save_blob(path, document)

    def save_current(self, document: dict[str, typing.Any]) -> None:
        path = self.current_path(document.get("teamKey") or document.get("equipe"))
        self._save_current_at(path, document)

    def load_current(self, team_key: str) -> dict[str, typing.Any]:
        return self.store.load_blob(self.current_path(team_key))

    def merge_and_save_daily(self, current: dict[str, typing.Any], day: str) -> dict[str, typing.Any]:
        team_key = _safe_team_key(current.get("teamKey") or current.get("equipe"))
        cache_key = (day, team_key)
        with self._lock:
            if hasattr(self.store, "update_blob"):
                daily_path = self.daily_path(day, team_key)
                merged = self.store.update_blob(
                    daily_path,
                    lambda previous: merge_daily_document(previous, current, day),
                )
                self._daily_cache[cache_key] = merged
                return merged
            previous = self._daily_cache.get(cache_key)
            if previous is None:
                previous = self.store.load_blob(self.daily_path(day, team_key))
            merged = merge_daily_document(previous, current, day)
            if merged != previous:
                self.store.save_blob(self.daily_path(day, team_key), merged)
            self._daily_cache[cache_key] = merged
            return merged

    def save_index(self, index: dict[str, typing.Any]) -> None:
        self.store.save_blob(self.index_path(), index)

    def load_daily(self, team_key: str, day: str) -> dict[str, typing.Any]:
        cache_key = (day, _safe_team_key(team_key))
        with self._lock:
            self._daily_cache[cache_key] = self.store.load_blob(self.daily_path(day, team_key))
            return dict(self._daily_cache[cache_key])

    def consolidate_month(self, month: str) -> dict[str, typing.Any]:
        import pandas as pd

        prefix = f"{self.root_prefix}/daily/{month}-"
        service_rows: list[dict[str, typing.Any]] = []
        interval_rows: list[dict[str, typing.Any]] = []
        files = self.store.list_blob_names(prefix)
        for blob_name in files:
            daily = self.store.load_blob(blob_name)
            team_key = daily.get("teamKey")
            day = daily.get("date")
            for service in daily.get("services") or []:
                location = service.get("geolocalizacao") or {}
                service_rows.append({
                    "teamKey": team_key,
                    "date": day,
                    **{key: value for key, value in service.items() if key != "geolocalizacao"},
                    "latitude": location.get("latitude"),
                    "longitude": location.get("longitude"),
                })
            for position, interval in enumerate((daily.get("turno") or {}).get("intervalos") or [], start=1):
                interval_rows.append({
                    "teamKey": team_key,
                    "date": day,
                    "sequence": position,
                    "inicio": interval.get("inicio"),
                    "fim": interval.get("fim"),
                })

        outputs = {
            "month": month,
            "dailyFiles": len(files),
            "services": len(service_rows),
            "intervals": len(interval_rows),
        }
        for name, rows in (("services", service_rows), ("intervals", interval_rows)):
            frame = pd.DataFrame(rows)
            buffer = io.BytesIO()
            frame.to_parquet(buffer, index=False, engine="pyarrow", compression="snappy")
            self.store.upload_bytes(
                f"{self.root_prefix}/monthly/{month}/{name}.parquet",
                buffer.getvalue(),
                "application/vnd.apache.parquet",
            )
        return outputs

    def turn_check_state_path(self) -> str:
        return f"{self.root_prefix}/daily-turn-check-state.json.gz"

    def record_daily_turn_check(
        self,
        team_count: int,
        now: datetime.datetime | None = None,
    ) -> dict[str, typing.Any]:
        """Registra a primeira raspagem completa do dia feita a partir das 06:00."""
        local_now = (now or datetime.datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)
        check_day = local_now.date().isoformat()
        if local_now.hour < 6:
            return {"executed": False, "reason": "scheduled_for_06:00", "checkDay": check_day}
        with self._lock:
            if self._turn_check_state is None:
                self._turn_check_state = self.store.load_blob(self.turn_check_state_path())
            if self._turn_check_state.get("lastCheckDay") == check_day:
                return {"executed": False, "reason": "already_checked_today", **self._turn_check_state}
            state = {
                "schemaVersion": 1,
                "lastCheckDay": check_day,
                "checkedAt": local_now.isoformat(),
                "teamCount": int(team_count),
                "source": "first_successful_rotalog_scrape_after_06:00",
            }
            self.store.save_blob(self.turn_check_state_path(), state)
            self._turn_check_state = state
            return {"executed": True, **state}
    def monthly_state_path(self) -> str:
        return f"{self.root_prefix}/monthly/build-state.json.gz"

    def consolidate_month_once_per_day(
        self, now: datetime.datetime | None = None,
    ) -> dict[str, typing.Any]:
        """Reescreve o mensal no máximo uma vez por data local, mesmo após reinício."""
        local_now = (now or datetime.datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)
        build_day = local_now.date().isoformat()
        if local_now.hour < 4:
            return {"executed": False, "reason": "scheduled_for_04:00", "buildDay": build_day}
        with self._lock:
            state = self.store.load_blob(self.monthly_state_path())
            if state.get("lastBuildDay") == build_day:
                return {"executed": False, "reason": "already_built_today", **state}
            target_date = local_now.date()
            if target_date.day == 1:
                target_date = target_date.replace(day=1) - datetime.timedelta(days=1)
            month = target_date.strftime("%Y-%m")
            result = self.consolidate_month(month)
            state = {
                "schemaVersion": 1,
                "lastBuildDay": build_day,
                "lastBuiltMonth": month,
                "lastBuiltAt": local_now.isoformat(),
                "result": result,
            }
            self.store.save_blob(self.monthly_state_path(), state)
            return {"executed": True, **state}
