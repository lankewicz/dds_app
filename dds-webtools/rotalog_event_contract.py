"""Pure validation shared by the Storage reader and the Orange events API."""
from datetime import datetime

STATUSES = frozenset({"DESLOCAMENTO", "EXECUCAO", "CONCLUSAO", "TURNO_ABERTO",
                      "TURNO_FECHADO", "INTERVALO_INICIADO", "INTERVALO_ENCERRADO"})


def company_key(value):
    return str(value).strip().casefold()


def timestamp(value):
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("Data de evento inválida")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Data de evento sem fuso")
    return parsed


def validate_window(payload, company):
    if not isinstance(payload, dict) or type(payload.get("schemaVersion")) is not int or payload["schemaVersion"] != 1:
        raise ValueError("Schema de eventos incompatível")
    if not isinstance(payload.get("company"), str) or company_key(payload["company"]) != company_key(company):
        raise ValueError("Arquivo de outra empresa")
    if payload.get("timezone") != "America/Sao_Paulo" or type(payload.get("windowHours")) is not int or payload["windowHours"] != 24:
        raise ValueError("Janela de eventos incompatível")
    timestamp(payload.get("updatedAt"))
    if not isinstance(payload.get("items"), list):
        raise ValueError("Lista de eventos inválida")
    by_id = {}
    for item in payload["items"]:
        if not isinstance(item, dict):
            raise ValueError("Evento inválido")
        for field in ("id", "teamKey", "entityId", "status", "timeSource"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError("Campo obrigatório de evento inválido")
        if item["status"] not in STATUSES or "type" not in item or item["type"] not in ("C", "E", None):
            raise ValueError("Tipo ou status de evento inválido")
        if "protocol" not in item or (item["protocol"] is not None and not isinstance(item["protocol"], str)):
            raise ValueError("Protocolo inválido")
        timestamp(item.get("occurredAt"))
        by_id[item["id"]] = dict(item)
    return {**payload, "items": sorted(by_id.values(), key=lambda i: (timestamp(i["occurredAt"]), i["id"]), reverse=True)}
