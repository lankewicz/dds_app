"""Completa lacunas do historico existente, sem alterar o estado operacional atual."""
import copy
import datetime
import re
import unicodedata

from bdo.services.rotalog_team_file_repository import LOCAL_TZ, _eh_protocolo_valido
from bdo.services.rotalog_tempo_real_service import formatar_protocolo_copel


def _columns(row):
    return {unicodedata.normalize("NFKD", str(k)).encode("ascii", "ignore").decode().lower().strip(): v
            for k, v in row.items()}


def _timestamp(value, day):
    if value in (None, "", "-"):
        return None
    raw = str(value).strip()
    try:
        parsed = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%H:%M"):
            try:
                parsed = datetime.datetime.strptime(raw, fmt)
                if fmt == "%H:%M":
                    parsed = datetime.datetime.combine(datetime.date.fromisoformat(day), parsed.time())
                break
            except ValueError:
                pass
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    return parsed.astimezone(LOCAL_TZ).isoformat()


def normalize_events(rows, day):
    events = {}
    for row in rows:
        r = _columns(row)
        team = str(r.get("veiculo") or r.get("equipe") or "").strip().upper()
        if not re.fullmatch(r"E[A-Z0-9]{3,7}", team):
            continue
        event = {
            "protocolo": formatar_protocolo_copel(str(r.get("protocolo") or "")),
            "tipo": str(r.get("codigo") or r.get("tipo") or "").strip().upper(),
            "inicioDeslocamento": _timestamp(r.get("inicio deslo"), day),
            "inicioExecucao": _timestamp(r.get("inicio exec"), day),
            "fimExecucao": _timestamp(r.get("fim exec"), day),
            "retorno": _timestamp(r.get("retorno"), day),
        }
        if not _eh_protocolo_valido(event["protocolo"]):
            continue
        # Descarta linhas de outra data; horarios completos preservam viradas de dia.
        start = event["inicioDeslocamento"] or event["inicioExecucao"]
        if not start or start[:10] != day:
            continue
        values = events.setdefault(team, [])
        if event not in values:
            values.append(event)
    return events


def normalize_turns(rows, day):
    grouped = {}
    for raw in rows:
        row = _columns(raw)
        team = str(row.get("veiculo") or row.get("equipe") or "").strip().upper()
        if not re.fullmatch(r"E[A-Z0-9]{3,7}", team):
            continue
        label = str(row.get("data referencia - turno") or "")
        dates = re.findall(r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}(?::\d{2})?", label)
        start = _timestamp(row.get("inicio turno") or (dates[0] if dates else None), day)
        end = _timestamp(row.get("fim turno") or (dates[1] if len(dates) > 1 else None), day)
        if start and start[:10] == day:
            turn = {"inicio": start, "fim": end}
            if turn not in grouped.setdefault(team, []):
                grouped[team].append(turn)
    return {team: turns[0] for team, turns in grouped.items() if len(turns) == 1}


def reconcile_document(previous, events, day, collected_at, turn=None):
    result = copy.deepcopy(previous)
    if not result or result.get("date") != day:
        return result
    proposals = []
    for service in result.get("services") or []:
        matches = []
        for idx, event in enumerate(events):
            protocol = service.get("protocolo")
            if _eh_protocolo_valido(protocol):
                if protocol != event["protocolo"]:
                    continue
            elif str(service.get("tipo") or "").upper() != event["tipo"]:
                continue
            if not any(service.get(f) and _timestamp(service[f], day) == event.get(f)
                       for f in ("inicioDeslocamento", "inicioExecucao")):
                continue
            matches.append(idx)
        if len(matches) == 1:
            proposals.append((service, matches[0]))
    changed = False
    for service, idx in proposals:
        if sum(other == idx for _, other in proposals) != 1:
            continue
        added = []
        for key, value in events[idx].items():
            missing = service.get(key) in (None, "", "-") or key in service.get("camposEstimados", [])
            if key == "protocolo":
                missing = not _eh_protocolo_valido(service.get(key))
            if missing and value not in (None, "", "-"):
                trial = {**service, key: value}
                times = [_timestamp(trial.get(f), day) for f in
                         ("inicioDeslocamento", "inicioExecucao", "fimExecucao", "retorno")]
                times = [t for t in times if t]
                if times != sorted(times):
                    continue
                service[key] = value
                if key in service.get("camposEstimados", []):
                    service["camposEstimados"].remove(key)
                added.append(key)
        if added:
            service["reconciliacaoDiaria"] = {
                "coletadoEm": collected_at, "camposPreenchidos": added,
                "fonte": "LISTAGEM_EVENTOS",
            }
            changed = True
    if turn:
        target = result.setdefault("turno", {})
        for field in ("inicio", "fim"):
            if not target.get(field) and turn.get(field):
                target[field] = turn[field]
                changed = True
    if changed:
        result["reconciledAt"] = collected_at
    return result
