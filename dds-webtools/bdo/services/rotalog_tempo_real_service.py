"""
Serviço de captura e estruturação de dados do ROTALOG Tempo Real (/paginas/tempoReal).
Extrai marcadores de Turno (T), Intervalo, Emergências, Serviços Comerciais e status de conectividade de cada equipe,
estruturando as Ordens de Serviço (SS) com tratamento de Protocolos (removendo o sufixo .x.y) para integração com o BDO.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import logging
import html as html_lib
import os
import re
import threading
import time
import typing
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import requests

from bdo.services.rotalog_crawler_service import CrawlerRotalog

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
URL_BASE = "https://www.copel.com/rtlweb"
URL_TEMPO_REAL = f"{URL_BASE}/paginas/tempoReal"
logger = logging.getLogger(__name__)


def equipe_codigo_valido(value: str | None) -> bool:
    """Rejeita cabeçalhos/placeholders como ``veiculo?`` da timeline."""
    return bool(re.fullmatch(r"E[A-Z0-9]{3,7}", str(value or "").strip().upper()))


def limpar_protocolo(protocolo_raw: str | None) -> str:
    """
    Remove o sufixo .x.y do protocolo (ex: '20265422950239.2.1' -> '20265422950239').
    """
    if not protocolo_raw:
        return ""
    prot = str(protocolo_raw).strip()
    return re.sub(r"\.\d+(\.\d+)?$", "", prot)


def formatar_protocolo_copel(protocolo_raw: str | None) -> str | None:
    limpo = limpar_protocolo(protocolo_raw)
    return limpo or None


def _convert_ms_to_iso(ms: int | str | None) -> str | None:
    if not ms or not str(ms).isdigit():
        return None
    try:
        dt = datetime.datetime.fromtimestamp(int(ms) / 1000.0, tz=LOCAL_TZ)
        return dt.isoformat()
    except Exception:
        return None


def _convert_ms_to_hora(ms: int | str | None) -> str:
    if not ms or not str(ms).isdigit():
        return ""
    try:
        dt = datetime.datetime.fromtimestamp(int(ms) / 1000.0, tz=LOCAL_TZ)
        return dt.strftime("%H:%M")
    except Exception:
        return ""


def parse_group_string(group_raw: str) -> dict[str, str]:
    """
    Parseia strings de grupo como:
    - 'E3733-CA127 BRUNNO PEDRO (online)'
    - 'E3188- EDIVAN ANDERSON (50 min)'
    """
    group_clean = group_raw.strip()
    
    status_conexao = ""
    m_status = re.search(r"\((.*?)\)$", group_clean)
    if m_status:
        status_conexao = m_status.group(1).strip()
        group_clean = re.sub(r"\s*\((.*?)\)$", "", group_clean).strip()

    partes = group_clean.split(" ", 1)
    cod_veic = partes[0] if partes else group_clean
    nome_colab = partes[1].strip() if len(partes) > 1 else ""

    if "-" in cod_veic:
        sub = cod_veic.split("-", 1)
        eq_codigo = sub[0].strip()
        veiculo = sub[1].strip()
    else:
        eq_codigo = cod_veic.strip()
        veiculo = ""

    return {
        "equipe_codigo": eq_codigo,
        "veiculo": veiculo,
        "colaborador": nome_colab,
        "status_conexao": status_conexao,
        "is_online": "online" in status_conexao.lower()
    }


REGIONAL_PREFIXES = ("CA", "CB", "LO", "MA", "PG")


def _extract_numeric_tablet_id(raw_id: str) -> str:
    """Extrai a parte numérica do tablet ignorando o prefixo da regional (CA, CB, LO, MA, PG)."""
    if not raw_id:
        return ""
    clean = str(raw_id).strip().upper().replace(" ", "")
    for prefix in REGIONAL_PREFIXES:
        if clean.startswith(prefix) and len(clean) > len(prefix):
            return clean[len(prefix):]
    return clean


def resolver_equipe_group(
    meta: dict[str, str],
    identificador_para_equipe: dict[str, str] | None = None,
) -> dict[str, str]:
    """Resolve grupos ``veiculo?-E...``, ``veiculo?-CA...`` e ``veiculo?-MA...`` por tablet ou integrantes."""
    resolved = dict(meta)
    equipe_original = str(meta.get("equipe_codigo") or "").strip().upper()
    identificador = str(meta.get("veiculo") or "").strip().upper().replace(" ", "")
    colaborador = str(meta.get("colaborador") or "").strip().upper()

    resolved["equipe_codigo_original"] = equipe_original
    resolved["identificador_equipamento"] = identificador
    resolved["origem_resolucao"] = "PREFIXO_EQUIPE"

    if equipe_codigo_valido(equipe_original):
        resolved["equipe_codigo"] = equipe_original
        return resolved
    if equipe_codigo_valido(identificador):
        resolved["equipe_codigo"] = identificador
        resolved["origem_resolucao"] = "VEICULO_COM_PREFIXO_EQUIPE"
        return resolved

    lookup = {str(key).strip().upper(): str(value).strip().upper()
              for key, value in (identificador_para_equipe or {}).items()}

    # 1. Busca direta por identificador de tablet/veículo (ex: CA085, MA974, MA965)
    equipe_mapeada = lookup.get(identificador)
    if equipe_codigo_valido(equipe_mapeada):
        resolved["equipe_codigo"] = equipe_mapeada
        resolved["origem_resolucao"] = "IDENTIFICACAO_TABLET"
        return resolved

    # 2. Busca por número do tablet (ignora variação regional CA/CB/LO/MA/PG caso a equipe tenha mudado de regional)
    numeric_id = _extract_numeric_tablet_id(identificador)
    if numeric_id:
        equipe_numerica = lookup.get(f"NUMERIC_TABLET:{numeric_id}")
        if equipe_codigo_valido(equipe_numerica):
            resolved["equipe_codigo"] = equipe_numerica
            resolved["origem_resolucao"] = "TABLET_NUMERICO_TRANSITORIO"
            return resolved

    # 3. Busca por integrantes / eletricistas (ex: WELLINGTON WILLIAN -> E3P14)
    if colaborador:
        colab_clean = re.sub(r"[^A-Z0-9\s]", "", colaborador)
        tokens = [t for t in colab_clean.split() if len(t) >= 3]

        if tokens:
            candidate_counts: dict[str, int] = {}
            for key, t_code in lookup.items():
                if key.startswith("MEMBER_NAME:"):
                    name_part = key[12:]
                    for token in tokens:
                        if token in name_part:
                            candidate_counts[t_code] = candidate_counts.get(t_code, 0) + 1

            if candidate_counts:
                sorted_candidates = sorted(candidate_counts.items(), key=lambda x: x[1], reverse=True)
                top_team, top_score = sorted_candidates[0]
                if top_score >= 1 and (len(sorted_candidates) == 1 or top_score > sorted_candidates[1][1]):
                    resolved["equipe_codigo"] = top_team
                    resolved["origem_resolucao"] = "INTEGRANTES_EQUIPE"
                    return resolved
                elif top_score >= 2:
                    resolved["equipe_codigo"] = top_team
                    resolved["origem_resolucao"] = "INTEGRANTES_EQUIPE"
                    return resolved

    resolved["equipe_codigo"] = ""
    resolved["origem_resolucao"] = "NAO_RELACIONADO"
    return resolved


def _obter_inicio_dia_operacional_ms(now: datetime.datetime | None = None) -> int:
    """Retorna o timestamp em ms da mudança do dia (meia-noite 00:00:00)."""
    now = (now or datetime.datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)
    meia_noite = datetime.datetime.combine(now.date(), datetime.time(0, 0, 0), tzinfo=LOCAL_TZ)
    return int(meia_noite.timestamp() * 1000)


def consolidar_turno_por_contexto(
    marcadores_t: list[dict[str, typing.Any]],
    eventos_servico_ms: list[int],
    tem_atividade_andamento: bool = False,
    retorno_ultimo_servico_ms: int | None = None,
    now: datetime.datetime | None = None,
) -> dict[str, typing.Any]:
    """Classifica o turno da equipe no Rotalog.

    - Se a equipe dá deslocamento/execução para um serviço -> ABERTO automaticamente (mesmo sem T).
    - Se a equipe ficou mais de 2 horas com o último serviço fechado/retornado sem novo deslocamento -> FECHADO.
    - O encerramento do turno fechado assume o horário de RETORNO (ou término) do último serviço.
    - Se a equipe estiver dentro da janela de 2 horas desde o último retorno e sem T de encerramento -> ABERTO aguardando despacho.
    """
    now = (now or datetime.datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)
    inicio_dia_ms = _obter_inicio_dia_operacional_ms(now)
    now_ms = int(now.timestamp() * 1000)

    markers = sorted(
        (item for item in marcadores_t if item.get("start")),
        key=lambda item: int(item["start"]),
    )
    all_services = sorted(int(value) for value in eventos_servico_ms if value)
    services_today = [v for v in all_services if v >= inicio_dia_ms]

    result = {
        "aberto": False,
        "inicio_ms": None,
        "inicio_iso": None,
        "fim_ms": None,
        "fim_iso": None,
        "classificacao": "DESCONHECIDO",
    }

    if not markers and not all_services:
        return result

    # 1. Se possui atividade em andamento no momento (deslocamento ou execução) -> ABERTO AUTOMATICAMENTE
    if tem_atividade_andamento:
        inicio_t = None
        if markers:
            inicio_t = int(markers[-1]["start"])
        if not inicio_t:
            inicio_t = services_today[0] if services_today else (all_services[-1] if all_services else None)

        result.update({
            "aberto": True,
            "inicio_ms": inicio_t,
            "inicio_iso": _convert_ms_to_iso(inicio_t) if inicio_t else None,
            "classificacao": "ABERTO",
        })
        return result

    # 2. Se NÃO possui atividade em andamento no momento:
    fim_turno_ms = retorno_ultimo_servico_ms if retorno_ultimo_servico_ms else (all_services[-1] if all_services else None)

    # Verifica se há marcador T novo de reabertura recente DEPOIS do último serviço
    if markers and fim_turno_ms:
        last_t = int(markers[-1]["start"])
        if last_t > fim_turno_ms:
            # Se for uma abertura recente nas últimas 2 horas
            if (now_ms - last_t) < 2 * 3600 * 1000:
                result.update({
                    "aberto": True,
                    "inicio_ms": last_t,
                    "inicio_iso": _convert_ms_to_iso(last_t),
                    "fim_ms": None,
                    "fim_iso": None,
                    "classificacao": "ABERTO",
                })
                return result

    if all_services and fim_turno_ms:
        tempo_sem_servico_ms = now_ms - fim_turno_ms
        duas_horas_ms = 2 * 3600 * 1000

        # Início correspondente ao turno deste lote de serviços
        inicio_ms = None
        if markers:
            for m in reversed(markers):
                t_val = int(m["start"])
                if t_val <= all_services[-1]:
                    inicio_ms = t_val
                    break
        if not inicio_ms:
            inicio_ms = services_today[0] if services_today else all_services[0]

        # REGRA DE FECHAMENTO AUTOMÁTICO POR INATIVIDADE:
        # 1. Plantão Noturno (termina às 08:00):
        #    - A partir das 08:00, se a equipe era do plantão da madrugada/noite (início antes das 08:00 ou último serviço antes das 08:00)
        #      e não executou novos serviços pós-08:00, fecha o turno automaticamente no RETORNO do último serviço (ou conclusão).
        # 2. Turno Diurno (após 20:00):
        #    - A partir das 20:00, se ficou mais de 2 horas sem novo serviço ou possui marcador T de fim explícito -> FECHADO.
        # 3. Durante o expediente diurno (entre 08:00 e 20:00 para equipes do dia): permanece ABERTO aguardando novos despachos.
        hora_atual_local = now.hour
        dt_inicio = datetime.datetime.fromtimestamp(inicio_ms / 1000, LOCAL_TZ) if inicio_ms else None
        dt_fim_servico = datetime.datetime.fromtimestamp(fim_turno_ms / 1000, LOCAL_TZ) if fim_turno_ms else None

        dia_atual = now.date()
        servicos_hoje_existentes = bool(services_today)
        marcadores_hoje_existentes = bool(markers and any(
            datetime.datetime.fromtimestamp(int(m["start"]) / 1000, LOCAL_TZ).date() == dia_atual
            for m in markers if m.get("start")
        ))
        sem_atividade_hoje = (not servicos_hoje_existentes and not marcadores_hoje_existentes)

        era_plantao_madrugada = False
        if dt_fim_servico:
            if dt_fim_servico.date() < dia_atual or (dt_fim_servico.date() == dia_atual and dt_fim_servico.hour < 8):
                era_plantao_madrugada = True

        tem_marcador_fim = bool(markers and int(markers[-1]["start"]) >= fim_turno_ms)
        fim_fechamento_ms = int(markers[-1]["start"]) if (tem_marcador_fim and int(markers[-1]["start"]) > fim_turno_ms) else fim_turno_ms

        fechar_plantao_08h = (hora_atual_local >= 8 and era_plantao_madrugada and tempo_sem_servico_ms >= duas_horas_ms)
        fechar_diurno_20h = (hora_atual_local >= 20 and tempo_sem_servico_ms >= duas_horas_ms)
        fechar_inatividade_longa = (tempo_sem_servico_ms >= int(2.5 * 3600 * 1000))

        deve_fechar = (
            tem_marcador_fim
            or sem_atividade_hoje
            or fechar_plantao_08h
            or fechar_diurno_20h
            or fechar_inatividade_longa
        )

        if deve_fechar:
            result.update({
                "aberto": False,
                "inicio_ms": inicio_ms,
                "inicio_iso": _convert_ms_to_iso(inicio_ms),
                "fim_ms": fim_fechamento_ms,
                "fim_iso": _convert_ms_to_iso(fim_fechamento_ms),
                "classificacao": "FECHADO",
            })
            return result
        else:
            # Antes das 20h ou dentro da tolerância aguardando próximo despacho
            result.update({
                "aberto": True,
                "inicio_ms": inicio_ms,
                "inicio_iso": _convert_ms_to_iso(inicio_ms),
                "fim_ms": None,
                "fim_iso": None,
                "classificacao": "ABERTO",
            })
            return result

    if markers:
        last_t = int(markers[-1]["start"])
        result.update({
            "aberto": False,
            "inicio_ms": last_t,
            "inicio_iso": _convert_ms_to_iso(last_t),
            "fim_ms": last_t,
            "fim_iso": _convert_ms_to_iso(last_t),
            "classificacao": "FECHADO",
        })
        return result

    result["classificacao"] = "DESCONHECIDO"
    result["aberto"] = False
    return result


def intervalo_ativo_por_contexto(
    intervalo: dict[str, typing.Any],
    eventos_servico_ms: list[int],
) -> bool:
    """Mantém intervalo somente até surgir uma atividade de serviço posterior."""
    if not intervalo.get("em_intervalo"):
        return False
    inicio = intervalo.get("inicio_ms")
    if not isinstance(inicio, int):
        return False
    return not any(int(evento) > inicio for evento in eventos_servico_ms if evento)


def formatar_protocolo_copel(proto_raw: str | None) -> str:
    """Formatador de protocolos da Copel:
    - Comercial: 14 dígitos (Ex: 20265259525570.4.2 -> 20265259525570)
    - Emergencial: 8 dígitos (Ex: 50954710 -> 50954710)
    """
    if not proto_raw:
        return ""
    clean = re.sub(r"\.\d+(\.\d+)?$", "", str(proto_raw).strip())
    m_com = re.search(r"\b(202\d{11})\b", clean)
    if m_com:
        return m_com.group(1)
    m_em = re.search(r"\b(\d{7,8})\b", clean)
    if m_em:
        return m_em.group(1)
    m_any = re.search(r"\b(\d{5,14})\b", clean)
    if m_any:
        return m_any.group(1)
    return ""


def _parse_rotalog_popups(html: str) -> dict[str, dict[str, typing.Any]]:
    """Parseia todos os popups/tooltips do Rotalog em HTML/JS contendo protocolo, tipo, categoria e horários."""
    popups = {}
    if not html:
        return popups

    normalized_html = html_lib.unescape(html)
    normalized_html = normalized_html.replace(r"\/", "/").replace(r"\n", " ").replace(r"\r", " ")
    normalized_html = re.sub(r"\\x3[cC]", "<", normalized_html)
    normalized_html = re.sub(r"\\x3[eE]", ">", normalized_html)
    text_clean = re.sub(r"<.*?>", " ", normalized_html)
    text_clean = text_clean.replace("&nbsp;", " ").replace("\r", "\n")

    blocks = []
    marker_pattern = re.compile(
        r"(?:L\.)?(?:marker|circleMarker)\s*\(\s*\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\].*?\)(.*?)(?=(?:L\.)?(?:marker|circleMarker)\s*\(|$)",
        re.DOTALL | re.IGNORECASE,
    )
    for marker_match in marker_pattern.finditer(normalized_html):
        latitude, longitude, marker_tail = marker_match.groups()
        if re.search(r"Equipe\s*:", marker_tail, re.IGNORECASE) and re.search(r"Protocolo\s*:", marker_tail, re.IGNORECASE):
            blocks.append(f"{marker_tail} Latitude: {latitude} Longitude: {longitude}")

    blocks += re.findall(r"(Sequ[êe]ncia:.*?(?=Sequ[êe]ncia:|$))", text_clean, re.DOTALL | re.IGNORECASE)
    blocks += re.findall(r"(Equipe:.*?(?=Equipe:|$))", text_clean, re.DOTALL | re.IGNORECASE)
    blocks += re.findall(r"bindPopup\(['\"](.*?)['\"]\)", normalized_html, re.DOTALL | re.IGNORECASE)
    blocks += re.findall(r"bindTooltip\(['\"](.*?)['\"]\)", normalized_html, re.DOTALL | re.IGNORECASE)

    for block in blocks:
        text = re.sub(r"\s+", " ", block)
        m_eq = re.search(r"Equipe[\s:-]*([^\s<]+)", text, re.IGNORECASE)
        m_prot = re.search(r"Protocolo[\s:-]*([0-9\.]+)", text, re.IGNORECASE)
        m_cat = re.search(r"Categoria[\s:-]*([^\s<:]+)", text, re.IGNORECASE)
        m_tipo = re.search(r"Tipo[\s:-]*([A-Z0-9\-_]+)", text, re.IGNORECASE)
        m_desl = re.search(r"In[íi]cio\s+Deslocamento[\s:-]*(\d{2}:\d{2})", text, re.IGNORECASE)
        m_exec = re.search(r"In[íi]cio\s+Execu[çc][ãa]o[\s:-]*(\d{2}:\d{2})", text, re.IGNORECASE)
        m_term = re.search(r"T[ée]rmino[\s:-]*(\d{2}:\d{2})", text, re.IGNORECASE)
        m_ret = re.search(r"Retorno[\s:-]*(\d{2}:\d{2})", text, re.IGNORECASE)
        m_seq = re.search(r"Sequ[êe]ncia[\s:-]*(\d+)", text, re.IGNORECASE)
        m_stat = re.search(r"Status[\s:-]*([^\s<:]+)", text, re.IGNORECASE)
        m_lat = re.search(r"Latitude\s*:\s*(-?\d+(?:\.\d+)?)", text, re.IGNORECASE)
        m_lng = re.search(r"Longitude\s*:\s*(-?\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if m_eq:
            equipe_raw = m_eq.group(1).strip().upper().rstrip("-")
            eq_match = re.search(r"\b(E[A-Z0-9]{3,7})\b", equipe_raw)
            identifier_match = re.search(r"\b((?:CA|CB|LO|MA|PG)\d+)\b", equipe_raw)
            eq = eq_match.group(1) if eq_match else ""
            identifier = identifier_match.group(1) if identifier_match else ""
            raw_p = m_prot.group(1) if m_prot else ""
            clean_p = formatar_protocolo_copel(raw_p)

            data = {
                "equipe": eq,
                "equipeRaw": equipe_raw,
                "identificadorEquipamento": identifier,
                "protocolo": clean_p,
                "protocoloBruto": raw_p,
                "categoria": m_cat.group(1).strip().upper() if m_cat else "",
                "tipo": m_tipo.group(1).strip().upper() if m_tipo else "",
                "inicioDeslocamento": m_desl.group(1) if m_desl else "",
                "inicioExecucao": m_exec.group(1) if m_exec else "",
                "termino": m_term.group(1) if m_term else "",
                "retorno": m_ret.group(1) if m_ret else "",
                "sequencia": m_seq.group(1) if m_seq else "",
                "status": m_stat.group(1).strip().upper() if m_stat else "",
                "latitude": float(m_lat.group(1)) if m_lat else None,
                "longitude": float(m_lng.group(1)) if m_lng else None,
                "geolocalizacao": (
                    {"latitude": float(m_lat.group(1)), "longitude": float(m_lng.group(1))}
                    if m_lat and m_lng else None
                ),            }
            popup_keys = []
            if eq:
                popup_keys.append(eq)
            if identifier:
                popup_keys.append(f"IDENTIFIER:{identifier}")
            for popup_key in popup_keys:
                existing = popups.get(popup_key) or {}
                merged = dict(existing)
                merged.update({key: value for key, value in data.items() if value not in (None, "")})
                popups[popup_key] = merged
                if merged.get("tipo"):
                    typed_key = f"{popup_key}_{merged['tipo']}"
                    typed_existing = popups.get(typed_key) or {}
                    typed_merged = dict(typed_existing)
                    typed_merged.update({key: value for key, value in merged.items() if value not in (None, "")})
                    popups[typed_key] = typed_merged
    return popups


def _service_merge_key(service: dict[str, typing.Any]) -> tuple[typing.Any, ...]:
    return (
        service.get("status"),
        service.get("tipo"),
        service.get("protocolo") or service.get("protocoloBruto"),
        service.get("sequencia"),
        service.get("inicioIso"),
        service.get("fimIso"),
    )


def _merge_service_lists(target: list[dict[str, typing.Any]], incoming: list[dict[str, typing.Any]]) -> None:
    known = {_service_merge_key(item) for item in target}
    for item in incoming:
        key = _service_merge_key(item)
        if key not in known:
            target.append(item)
            known.add(key)


def consolidar_equipes_duplicadas(equipes: list[dict[str, typing.Any]]) -> list[dict[str, typing.Any]]:
    """Une linhas diferentes do ROTALOG que resolvem para o mesmo código de equipe."""
    consolidadas: dict[str, dict[str, typing.Any]] = {}
    duplicadas: dict[str, int] = {}
    for equipe in equipes:
        codigo = str(equipe.get("equipe_codigo") or "").strip().upper()
        atual = consolidadas.get(codigo)
        if atual is None:
            consolidadas[codigo] = equipe
            continue

        duplicadas[codigo] = duplicadas.get(codigo, 1) + 1
        grupos = [part.strip() for part in str(atual.get("group_raw") or "").split(" | ") if part.strip()]
        novo_grupo = str(equipe.get("group_raw") or "").strip()
        if novo_grupo and novo_grupo not in grupos:
            grupos.append(novo_grupo)
        atual["group_raw"] = " | ".join(grupos)
        atual["is_online"] = bool(atual.get("is_online") or equipe.get("is_online"))
        for field in ("veiculo", "identificador_equipamento", "origem_resolucao"):
            if not atual.get(field) and equipe.get(field):
                atual[field] = equipe[field]
        colaboradores = [part.strip() for part in str(atual.get("colaborador") or "").split(" / ") if part.strip()]
        novo_colaborador = str(equipe.get("colaborador") or "").strip()
        if novo_colaborador and novo_colaborador not in colaboradores:
            colaboradores.append(novo_colaborador)
        atual["colaborador"] = " / ".join(colaboradores)

        for field in ("turno_marcadores_t", "eventos_servico_ms"):
            atual.setdefault(field, []).extend(equipe.get(field) or [])
        for field in ("bdo_list", "ss_executadas", "ss_em_andamento", "ss_pendentes"):
            _merge_service_lists(atual.setdefault(field, []), equipe.get(field) or [])
        intervalos = {item.get("inicio_ms"): dict(item) for item in atual.get("intervalos", []) if item.get("inicio_ms")}
        for item in equipe.get("intervalos") or []:
            key = item.get("inicio_ms")
            if key:
                intervalos[key] = {**intervalos.get(key, {}), **{k: v for k, v in item.items() if v is not None}}
        atual["intervalos"] = sorted(intervalos.values(), key=lambda item: item.get("inicio_ms") or 0)

        inicio_atual = atual.get("intervalo", {}).get("inicio_ms") or 0
        inicio_novo = equipe.get("intervalo", {}).get("inicio_ms") or 0
        if inicio_novo > inicio_atual:
            atual["intervalo"] = equipe["intervalo"]
        atividades = atual.get("ss_em_andamento") or []
        if atividades:
            atual["atividade_atual"] = max(
                atividades,
                key=lambda item: str(item.get("inicioIso") or ""),
            )

    if duplicadas:
        linhas_duplicadas = "\n".join(
            f"  {equipe}: {quantidade} registros consolidados"
            for equipe, quantidade in sorted(duplicadas.items())
        )
        logger.info("Equipes ROTALOG consolidadas por código:\n%s", linhas_duplicadas)
    return list(consolidadas.values())

def extrair_dados_tempo_real(
    crawler: CrawlerRotalog | None = None,
    max_tentativas: int = 3,
    identificador_para_equipe: dict[str, str] | None = None,
    snapshots_anteriores: dict[str, dict[str, typing.Any]] | None = None,
) -> list[dict[str, typing.Any]]:
    """
    Realiza a requisição autenticada à página /paginas/tempoReal do Rotalog,
    parseia o payload de script JavaScript da timeline (PrimeFaces) e do mapa (Leaflet),
    e retorna uma lista de dicionários com o status completo e o BDO de cada equipe.
    """
    if crawler is None:
        crawler = CrawlerRotalog()

    resp = None
    for tentativa in range(1, max_tentativas + 1):
        try:
            session = crawler._criar_sessao_autenticada()
            resp = session.get(URL_TEMPO_REAL, verify=False, timeout=60)
            if resp.status_code == 200:
                break
        except Exception as e:
            if tentativa == max_tentativas:
                raise RuntimeError(f"Erro de conexão com Rotalog após {max_tentativas} tentativas: {e}")
            time.sleep(2)

    if not resp or resp.status_code != 200:
        raise RuntimeError(f"Falha ao acessar Rotalog Tempo Real: HTTP {resp.status_code if resp else 'No Response'}")

    html = resp.text
    popups_map = _parse_rotalog_popups(html)
    soup = BeautifulSoup(html, "html.parser")

    scripts = soup.find_all("script")
    timeline_script = ""
    for s in scripts:
        text = s.string or s.text or ""
        if "timelineAlert" in text or 'PrimeFaces.cw("Timeline"' in text:
            timeline_script = text
            break

    if not timeline_script:
        raise RuntimeError("Resposta Copel sem timeline; coleta nao confirmada.")

    js_clean = re.sub(r"new Date\((\d+)\)", r"\1", timeline_script)
    pattern = r'\{"start":\s*(\d+)\s*,\s*"end":\s*(\d+|\w+)\s*,\s*"editable":\s*(true|false)\s*,\s*"group":\s*"(.*?)"\s*,\s*"className":\s*"(.*?)"\s*,\s*"content":\s*"(.*?)"\}'

    raw_items = []
    for idx, match in enumerate(re.finditer(pattern, js_clean)):
        start_ms, end_ms, editable, group, class_name, content = match.groups()
        raw_items.append({
            "idx": idx,
            "start": int(start_ms) if start_ms.isdigit() else 0,
            "end": int(end_ms) if end_ms.isdigit() else None,
            "group": group.strip(),
            "className": class_name.strip(),
            "content": content.strip()
        })

    equipas_map: dict[str, dict[str, typing.Any]] = {}
    if not raw_items:
        raise RuntimeError("Timeline sem eventos reconhecidos; preservar ultimo snapshot.")

    for item in raw_items:
        group_raw = item["group"]
        if group_raw not in equipas_map:
            meta = resolver_equipe_group(
                parse_group_string(group_raw), identificador_para_equipe
            )
            if not equipe_codigo_valido(meta["equipe_codigo"]):
                logger.warning(
                    "Grupo Rotalog sem relação de equipe: %s (identificador=%s)",
                    group_raw,
                    meta.get("identificador_equipamento") or "-",
                )
                continue
            equipas_map[group_raw] = {
                "group_raw": group_raw,
                "equipe_codigo": meta["equipe_codigo"],
                "veiculo": meta["veiculo"],
                "colaborador": meta["colaborador"],
                "status_conexao": meta["status_conexao"],
                "is_online": meta["is_online"],
                "origem_resolucao": meta.get("origem_resolucao"),
                "identificador_equipamento": meta.get("identificador_equipamento"),
                "turno_marcadores_t": [],
                "turno": {
                    "aberto": False,
                    "inicio_ms": None,
                    "inicio_iso": None,
                    "fim_ms": None,
                    "fim_iso": None
                },
                "intervalo": {
                    "em_intervalo": False,
                    "inicio_ms": None,
                    "fim_ms": None
                },
                "intervalos": [],
                "atividade_atual": None,
                "bdo_list": [],
                "ss_executadas": [],
                "ss_em_andamento": [],
                "ss_pendentes": [],
                "eventos_servico_ms": [],
            }

        eq_dict = equipas_map.get(group_raw)
        if eq_dict is None:
            continue
        cls = item["className"]
        cnt = item["content"]
        eq_code = eq_dict["equipe_codigo"]
        equipment_identifier = str(eq_dict.get("identificador_equipamento") or "").strip().upper()
        popup_info = {}  # Popups globais nao identificam univocamente cada evento.
        unused_popup_info = (
            popups_map.get(f"{eq_code}_{cnt}")
            or popups_map.get(f"IDENTIFIER:{equipment_identifier}_{cnt}")
            or popups_map.get(eq_code)
            or popups_map.get(f"IDENTIFIER:{equipment_identifier}")
            or {}
        )

        # 1. Marcador de Turno "T"
        if cnt == "T" and cls == "tempoRealMacro":
            eq_dict["turno_marcadores_t"].append({
                "start": item["start"],
                "end": item["end"]
            })

        # 2. Marcador de Intervalo
        elif cnt == "INTERVALO" or "intervalo" in cls.lower():
            interval_record = {
                "inicio_ms": item["start"],
                "inicioIso": _convert_ms_to_iso(item["start"]),
                "fim_ms": item["end"] if isinstance(item["end"], int) else None,
                "fimIso": _convert_ms_to_iso(item["end"]) if isinstance(item["end"], int) else None,
            }
            existing_interval = next((value for value in eq_dict["intervalos"] if value.get("inicio_ms") == item["start"]), None)
            if existing_interval:
                existing_interval.update({key: value for key, value in interval_record.items() if value is not None})
            else:
                eq_dict["intervalos"].append(interval_record)
            inicio_atual = eq_dict["intervalo"].get("inicio_ms")
            if not isinstance(inicio_atual, int) or item["start"] >= inicio_atual:
                eq_dict["intervalo"].update({"em_intervalo": True, **interval_record})

        # 3. SSs Executadas (BDO)
        elif "Executado" in cls:
            eq_dict["eventos_servico_ms"].append(item["start"])
            prot_real = popup_info.get("protocolo") or formatar_protocolo_copel(cnt)
            tipo_real = popup_info.get("tipo") or cnt
            categoria = popup_info.get("categoria") or ("EMERGENCIA" if "Emergencia" in cls else "COMERCIAL")
            hora_inicio = _convert_ms_to_hora(item["start"])
            hora_fim = popup_info.get("termino") or (_convert_ms_to_hora(item["end"]) if isinstance(item["end"], int) else "")

            ss_item = {
                "eventIdx": item.get("idx"),
                "ssId": prot_real,
                "protocolo": prot_real,
                "protocoloBruto": popup_info.get("protocoloBruto") or prot_real,
                "categoria": categoria,
                "tipo": tipo_real,
                "status": "CONCLUSAO",
                "camposEstimados": ["inicioDeslocamento", "retorno"],
                "inicioDeslocamento": popup_info.get("inicioDeslocamento") or hora_inicio,
                "inicioExecucao": popup_info.get("inicioExecucao") or hora_inicio,
                "termino": hora_fim,
                "retorno": popup_info.get("retorno") or hora_fim,
                "sequencia": popup_info.get("sequencia") or "",
                "latitude": popup_info.get("latitude"),
                "longitude": popup_info.get("longitude"),
                "geolocalizacao": popup_info.get("geolocalizacao"),
                "inicioIso": _convert_ms_to_iso(item["start"]),
                "fimIso": _convert_ms_to_iso(item["end"]) if isinstance(item["end"], int) else None,
                "transitions": [
                    {"status": "EXECUCAO", "timestampMs": item["start"], "hora": hora_inicio},
                    {"status": "CONCLUSAO", "timestampMs": item["end"] if isinstance(item["end"], int) else item["start"], "hora": hora_fim}
                ]
            }

            eq_dict["ss_executadas"].append(ss_item)
            eq_dict["bdo_list"].append(ss_item)

        # 4. SSs em Deslocamento ou Execução
        elif "EmDeslocamento" in cls or "EmExecucao" in cls:
            eq_dict["eventos_servico_ms"].append(item["start"])
            prot_real = popup_info.get("protocolo") or formatar_protocolo_copel(cnt)
            tipo_real = popup_info.get("tipo") or cnt
            status_str = "DESLOCAMENTO" if "EmDeslocamento" in cls else "EXECUCAO"
            categoria = popup_info.get("categoria") or ("EMERGENCIA" if "Emergencia" in cls else "COMERCIAL")
            hora_inicio = _convert_ms_to_hora(item["start"])

            ss_andamento = {
                "eventIdx": item.get("idx"),
                "ssId": prot_real,
                "protocolo": prot_real,
                "protocoloBruto": popup_info.get("protocoloBruto") or prot_real,
                "status": status_str,
                "camposEstimados": ["inicioDeslocamento"] if status_str == "EXECUCAO" else [],
                "categoria": categoria,
                "tipo": tipo_real,
                "inicioDeslocamento": popup_info.get("inicioDeslocamento") or hora_inicio,
                "inicioExecucao": popup_info.get("inicioExecucao") or (hora_inicio if status_str == "EXECUCAO" else ""),
                "termino": popup_info.get("termino") or "",
                "retorno": popup_info.get("retorno") or "",
                "sequencia": popup_info.get("sequencia") or "",
                "latitude": popup_info.get("latitude"),
                "longitude": popup_info.get("longitude"),
                "geolocalizacao": popup_info.get("geolocalizacao"),
                "inicioIso": _convert_ms_to_iso(item["start"]),
                "inicioHora": hora_inicio,
                "transitions": [
                    {"status": status_str, "timestampMs": item["start"], "hora": hora_inicio}
                ]
            }

            eq_dict["ss_em_andamento"].append(ss_andamento)
            eq_dict["atividade_atual"] = ss_andamento
            eq_dict["bdo_list"].append(ss_andamento)

        # 5. SSs Pendentes (Fila)
        elif "Pendente" in cls:
            eq_dict["ss_pendentes"].append({
                "sequencia": cnt,
                "tipo": "EMERGENCIA" if "Emergencia" in cls else "COMERCIAL"
            })

    resultado = consolidar_equipes_duplicadas(list(equipas_map.values()))

    # 1. Reaproveita o snapshot anterior. A listagem historica de eventos pertence
    # exclusivamente ao job diario das 04:30 e nao participa do tempo real.
    resolvidos_pelo_snapshot = _enriquecer_com_snapshot_anterior(
        resultado, snapshots_anteriores or {}
    )
    hoje_local = datetime.datetime.now(LOCAL_TZ).date()
    data_minima_tempo_real = hoje_local - datetime.timedelta(days=1)

    def _servico_recente_sem_protocolo(srv: dict[str, typing.Any]) -> bool:
        if not _servico_precisa_detalhes(srv) or not srv.get("inicioIso"):
            return False
        try:
            data_servico = (
                datetime.datetime.fromisoformat(srv["inicioIso"])
                .astimezone(LOCAL_TZ)
                .date()
            )
        except (TypeError, ValueError):
            return False
        return data_minima_tempo_real <= data_servico <= hoje_local

    candidatos_iniciais = 0
    for eq in resultado:
        for srv in eq.get("ss_executadas", []) + eq.get("ss_em_andamento", []):
            if _servico_recente_sem_protocolo(srv):
                candidatos_iniciais += 1

    indices_sem_protocolo = {
        srv.get("eventIdx")
        for eq in resultado
        for srv in (eq.get("ss_executadas", []) + eq.get("ss_em_andamento", []))
        if srv.get("eventIdx") is not None and _servico_recente_sem_protocolo(srv)
    }
    logger.info(
        "Enriquecimento incremental: candidatos=%s; resolvidos_pelo_snapshot=%s; "
        "consultas_individuais=%s",
        candidatos_iniciais,
        resolvidos_pelo_snapshot,
        len(indices_sem_protocolo),
    )

    # 2. Consulta individualmente apenas os quadrados que a listagem nao resolveu.
    try:
        vs_input = soup.find("input", {"name": "javax.faces.ViewState"})
        view_state = vs_input["value"] if vs_input and vs_input.get("value") else None
        if 'session' in locals() and session and view_state and raw_items:
            cliques_by_idx = _forcar_cliques_timeline_tempo_real(
                session, view_state, raw_items, event_indices=indices_sem_protocolo
            )
            if cliques_by_idx:
                for eq in resultado:
                    for srv in (eq.get("ss_executadas", []) + eq.get("ss_em_andamento", [])):
                        ev_idx = srv.get("eventIdx")
                        if ev_idx is not None and ev_idx in cliques_by_idx:
                            popup_data = cliques_by_idx[ev_idx]
                            if popup_data.get("protocolo"):
                                srv["protocolo"] = popup_data["protocolo"]
                                srv["protocoloBruto"] = popup_data["protocoloBruto"]
                                srv["ssId"] = popup_data["protocolo"]
                            if popup_data.get("categoria"):
                                srv["categoria"] = popup_data["categoria"]
                            if popup_data.get("tipo"):
                                srv["tipo"] = popup_data["tipo"]
                            if popup_data.get("sequencia"):
                                srv["sequencia"] = popup_data["sequencia"]
                            if popup_data.get("latitude") is not None:
                                srv["latitude"] = popup_data["latitude"]
                                srv["longitude"] = popup_data["longitude"]
                                srv["geolocalizacao"] = {
                                    "latitude": popup_data["latitude"],
                                    "longitude": popup_data["longitude"],
                                }
                            if popup_data.get("inicioDeslocamento"):
                                srv["inicioDeslocamento"] = popup_data["inicioDeslocamento"]
                            if popup_data.get("inicioExecucao"):
                                srv["inicioExecucao"] = popup_data["inicioExecucao"]
                            if popup_data.get("termino"):
                                srv["termino"] = popup_data["termino"]
                            if popup_data.get("retorno"):
                                srv["retorno"] = popup_data["retorno"]
                            srv["detalhesStatus"] = srv.get("status")
                            srv["camposEstimados"] = [
                                f for f in srv.get("camposEstimados", [])
                                if not popup_data.get(f)
                            ]
                            srv["fonteProtocolo"] = "POPUP"
                logger.info("Enriquecimento via cliques forçados na timeline: %s eventos vinculados 1-a-1 com sucesso.", len(cliques_by_idx))
    except Exception as exc:
        logger.warning("Falha ao executar cliques forçados na timeline do Tempo Real: %s", exc)

    # 3. Conclui consolidacao de equipes e status de turno.
    for eq in resultado:
        eventos_servico_ms = eq.pop("eventos_servico_ms", [])
        tem_andamento = bool(eq.get("ss_em_andamento") or eq.get("atividade_atual"))
        retorno_ultimo_ms = None
        if eq.get("ss_executadas"):
            def _srv_sort_key(srv):
                for k in ("fim_ms", "end", "end_ms"):
                    v = srv.get(k)
                    if isinstance(v, (int, float)) and v > 1000000000000:
                        return int(v)
                for k in ("fimIso", "inicioIso"):
                    v = str(srv.get(k) or "")
                    if len(v) >= 10:
                        try:
                            return int(datetime.datetime.fromisoformat(v).timestamp() * 1000)
                        except Exception:
                            pass
                return 0
            sorted_exec = sorted(eq["ss_executadas"], key=_srv_sort_key)
            last_exec = sorted_exec[-1]
            retorno_str = last_exec.get("retorno") or last_exec.get("termino")
            if retorno_str and len(str(retorno_str).strip()) == 5:
                base_day = None
                for k in ("fimIso", "inicioIso"):
                    v = str(last_exec.get(k) or "")
                    if len(v) >= 10 and v[4] == "-" and v[7] == "-":
                        base_day = v[:10]
                        break
                if not base_day:
                    base_day = datetime.datetime.now(LOCAL_TZ).date().isoformat()
                try:
                    dt = datetime.datetime.fromisoformat(f"{base_day}T{retorno_str}:00").replace(tzinfo=LOCAL_TZ)
                    retorno_ultimo_ms = int(dt.timestamp() * 1000)
                except Exception:
                    pass
            if not retorno_ultimo_ms:
                for k in ("fim_ms", "end", "end_ms"):
                    v = last_exec.get(k)
                    if isinstance(v, (int, float)) and v > 1000000000000:
                        retorno_ultimo_ms = int(v)
                        break

        turno_contextual = consolidar_turno_por_contexto(
            eq.get("turno_marcadores_t") or [],
            eventos_servico_ms,
            tem_atividade_andamento=tem_andamento,
            retorno_ultimo_servico_ms=retorno_ultimo_ms,
        )
        eq["turno"] = {key: value for key, value in turno_contextual.items() if key != "classificacao"}
        eq["intervalo"]["em_intervalo"] = intervalo_ativo_por_contexto(
            eq["intervalo"], eventos_servico_ms
        )

        if turno_contextual["classificacao"] == "ABERTO":
            if eq["intervalo"]["em_intervalo"]:
                eq["estado_consolidado"] = "INTERVALO"
            else:
                eq["estado_consolidado"] = "ABERTO"
        elif turno_contextual["classificacao"] == "FECHADO":
            eq["estado_consolidado"] = "FECHADO"
        else:
            eq["estado_consolidado"] = "DESCONHECIDO"

    logger.info("Enriquecimento de servicos e consolidacao de turnos concluidos.")
    # 4. Verificação final de serviços que ainda não possuem protocolo após todas as fontes de enriquecimento
    protocolos_ausentes = []
    for eq in resultado:
        for service in eq.get("ss_em_andamento", []) + eq.get("ss_executadas", []):
            if not _eh_protocolo_valido(service.get("protocolo")):
                protocolos_ausentes.append({
                    "equipe": eq.get("equipe_codigo"),
                    "equipamento": eq.get("identificador_equipamento"),
                    "tipo": service.get("tipo"),
                    "status": service.get("status"),
                })
    if protocolos_ausentes:
        linhas_protocolos = "\n".join(
            f"  {str(item.get('equipe') or ''):<6} | "
            f"equipamento={str(item.get('equipamento') or ''):<6} | "
            f"tipo={str(item.get('tipo') or ''):<5} | "
            f"status={str(item.get('status') or ''):<12}"
            for item in protocolos_ausentes
        )
        logger.info(
            "ROTALOG: %s serviço(s) em andamento ainda sem protocolo no final:\n%s",
            len(protocolos_ausentes),
            linhas_protocolos,
        )

    return resultado


def _extrair_hora_string(texto: typing.Any) -> str:
    if not texto:
        return ""
    m = re.search(r"(\d{2}:\d{2})", str(texto).strip())
    return m.group(1) if m else ""


def _obter_eventos_tabela_dia(session: requests.Session, data_str: str | None = None) -> list[dict[str, typing.Any]]:
    """Consulta a página /paginas/listagemEventos reutilizando a sessão autenticada."""
    import math

    if not data_str:
        now_local = datetime.datetime.now(LOCAL_TZ)
        data_str = now_local.strftime("%d/%m/%Y")

    url_eventos = f"{URL_BASE}/paginas/listagemEventos"
    try:
        resp_page = session.get(url_eventos, verify=False, timeout=30)
        if resp_page.status_code != 200:
            return []
        soup_page = BeautifulSoup(resp_page.text, "html.parser")
        view_state_elem = soup_page.find("input", {"name": "javax.faces.ViewState"})
        if not view_state_elem:
            return []
        view_state = view_state_elem["value"]

        post_data = {
            "form": "form",
            "form:j_idt27:dataInicial_input": data_str,
            "form:j_idt27:dataFinal_input": data_str,
            "form:veiculo": "",
            "form:contrato_input": "",
            "form:j_idt40": "",
            "javax.faces.ViewState": view_state,
        }

        resp_search = session.post(url_eventos, data=post_data, verify=False, timeout=45)
        if resp_search.status_code != 200:
            return []

        m_ev = re.search(r"widget_form_tbListagemEventos.*?rowCount:(\d+)", resp_search.text)
        row_count_ev = int(m_ev.group(1)) if m_ev else 0
        page_size_ev = 50
        total_pages_ev = math.ceil(row_count_ev / page_size_ev) if row_count_ev > 0 else 1

        soup_search = BeautifulSoup(resp_search.text, "html.parser")
        tbls = soup_search.find_all("table")
        if len(tbls) < 2:
            return []

        headers = [th.text.strip().replace("\n", " ") for th in tbls[1].find_all("th") if th.text.strip()]
        headers_clean = [re.sub(r"Filter by.*", "", h).strip() for h in headers]

        headers_ajax = {
            "Faces-Request": "partial/ajax",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        eventos = []

        def parse_eventos_tr(soup_ctx):
            for tr in soup_ctx.find_all("tr"):
                tds = tr.find_all("td")
                if not tds:
                    continue
                cells = [td.text.strip().replace("\n", " ") for td in tds]
                if len(cells) == len(headers_clean):
                    row = dict(zip(headers_clean, cells))
                    veic = str(row.get("Veículo") or row.get("Veiculo") or "").strip().upper()
                    prot_raw = str(row.get("Protocolo") or "").strip()
                    if veic and prot_raw:
                        eventos.append({
                            "equipe": veic,
                            "tablet": str(row.get("Tablet") or "").strip(),
                            "protocolo": formatar_protocolo_copel(prot_raw),
                            "protocoloBruto": prot_raw,
                            "tipo": str(row.get("Tipo") or "").strip().upper(),
                            "codigo": str(row.get("Codigo") or row.get("Código") or "").strip().upper(),
                            "inicioDeslocamento": _extrair_hora_string(row.get("Inicio Deslo") or row.get("Início Deslo")),
                            "inicioExecucao": _extrair_hora_string(row.get("Inicio Exec") or row.get("Início Exec")),
                            "fimExecucao": _extrair_hora_string(row.get("Fim Exec")),
                            "retorno": _extrair_hora_string(row.get("Retorno")),
                            "contrato": str(row.get("Contrato") or "").strip(),
                            "agencia": str(row.get("Agência") or row.get("Agencia") or "").strip(),
                        })

        for page in range(total_pages_ev):
            offset = page * page_size_ev
            if offset == 0:
                parse_eventos_tr(tbls[1])
            else:
                ajax_data = {
                    "javax.faces.partial.ajax": "true",
                    "javax.faces.source": "form:tbListagemEventos",
                    "javax.faces.partial.execute": "form:tbListagemEventos",
                    "javax.faces.partial.render": "form:tbListagemEventos",
                    "form:tbListagemEventos": "form:tbListagemEventos",
                    "form:tbListagemEventos_pagination": "true",
                    "form:tbListagemEventos_first": str(offset),
                    "form:tbListagemEventos_rows": str(page_size_ev),
                    "form:tbListagemEventos_encodeFeature": "true",
                    "form": "form",
                    "form:j_idt27:dataInicial_input": data_str,
                    "form:j_idt27:dataFinal_input": data_str,
                    "javax.faces.ViewState": view_state,
                }
                try:
                    resp_ajax = session.post(url_eventos, data=ajax_data, headers=headers_ajax, verify=False, timeout=30)
                    soup_ajax = BeautifulSoup(resp_ajax.text, "html.parser")
                    update = soup_ajax.find("update", {"id": "form:tbListagemEventos"})
                    if update:
                        parse_eventos_tr(BeautifulSoup(update.text, "html.parser"))
                except Exception:
                    pass

        return eventos
    except Exception as exc:
        logger.warning("Não foi possível obter eventos da tbListagemEventos: %s", exc)
        return []


def _enriquecer_tabela_segura(equipes, eventos):
    """Associa uma linha a um unico servico por equipe, data, tipo e inicio."""
    propostas = []
    for eq in equipes:
        for srv in eq.get("ss_executadas", []) + eq.get("ss_em_andamento", []):
            if _eh_protocolo_valido(srv.get("protocolo")):
                continue
            inicio = srv.get("inicioIso")
            if not inicio:
                continue
            data = datetime.datetime.fromisoformat(inicio).astimezone(LOCAL_TZ).date().isoformat()
            hora = _extrair_hora_string(srv.get("inicioExecucao"))
            tipo = str(srv.get("tipo") or "").strip().upper()
            candidatos = [
                ev for ev in eventos
                if ev.get("equipe") == eq.get("equipe_codigo")
                and ev.get("dataReferencia") == data
                and tipo and tipo == str(ev.get("tipo") or ev.get("codigo") or "").strip().upper()
                and hora and hora == ev.get("inicioExecucao")
                and _eh_protocolo_valido(ev.get("protocolo"))
            ]
            if len(candidatos) == 1:
                propostas.append((srv, candidatos[0]))
            else:
                srv["validacaoProtocolo"] = "AMBIGUO" if candidatos else "NAO_ENCONTRADO"
    for srv, ev in propostas:
        if sum(other is ev for _, other in propostas) != 1:
            srv["validacaoProtocolo"] = "AMBIGUO"
            continue
        srv.update(protocolo=ev["protocolo"], protocoloBruto=ev.get("protocoloBruto"),
                   ssId=ev["protocolo"], fonteProtocolo="LISTAGEM_EVENTOS",
                   validacaoProtocolo="EQUIPE_DATA_TIPO_INICIO_UNICOS")
        for origem, destino in (("inicioDeslocamento", "inicioDeslocamento"),
                                ("fimExecucao", "termino"), ("retorno", "retorno")):
            if not srv.get(destino) and ev.get(origem):
                srv[destino] = ev[origem]


def _enriquecer_com_snapshot_anterior(
    equipes: list[dict[str, typing.Any]],
    snapshots: dict[str, dict[str, typing.Any]],
) -> int:
    """Reaproveita detalhes somente quando equipe, inicio e tipo identificam um servico."""
    if not equipes or not snapshots:
        return 0

    resolvidos = 0
    campos = (
        "protocolo",
        "protocoloBruto",
        "ssId",
        "categoria",
        "sequencia",
        "latitude",
        "longitude",
        "geolocalizacao",
        "inicioDeslocamento",
        "inicioExecucao",
        "retorno",
    )
    for eq in equipes:
        equipe_codigo = str(eq.get("equipe_codigo") or "").strip().upper()
        team_key = re.sub(r"[^A-Z0-9_-]+", "", equipe_codigo)
        anterior = snapshots.get(team_key) or snapshots.get(equipe_codigo) or {}
        servicos_anteriores = (
            (anterior.get("ssExecutadas") or [])
            + (anterior.get("ssEmAndamento") or [])
        )
        for srv in (eq.get("ss_executadas") or []) + (eq.get("ss_em_andamento") or []):
            inicio = str(srv.get("inicioIso") or "")
            tipo = str(srv.get("tipo") or "").strip().upper()
            if not inicio or not tipo:
                continue
            candidatos = [
                item
                for item in servicos_anteriores
                if str(item.get("inicioIso") or "") == inicio
                and str(item.get("tipo") or "").strip().upper() == tipo
                and _eh_protocolo_valido(item.get("protocolo"))
            ]
            if len(candidatos) != 1:
                continue
            anterior_srv = candidatos[0]
            if (_eh_protocolo_valido(srv.get("protocolo"))
                    and srv["protocolo"] != anterior_srv["protocolo"]):
                continue
            for campo in campos:
                valor = anterior_srv.get(campo)
                missing = srv.get(campo) in (None, "")
                estimated = (campo in srv.get("camposEstimados", [])
                             and campo not in anterior_srv.get("camposEstimados", [])
                             and bool(anterior_srv.get("detalhesStatus")))
                missing = missing or estimated
                if campo in {"protocolo", "protocoloBruto", "ssId"}:
                    missing = not _eh_protocolo_valido(srv.get(campo))
                if missing and valor not in (None, ""):
                    srv[campo] = valor
                    if estimated:
                        srv["camposEstimados"].remove(campo)
            if anterior_srv.get("detalhesStatus") and anterior_srv.get("detalhesStatus") == srv.get("status"):
                srv["detalhesStatus"] = anterior_srv["detalhesStatus"]
            srv["fonteProtocolo"] = anterior_srv.get("fonteProtocolo") or "SNAPSHOT_ANTERIOR"
            srv["validacaoProtocolo"] = anterior_srv.get("validacaoProtocolo") or "EQUIPE_INICIO_TIPO_UNICOS"
            resolvidos += 1
    return resolvidos


def _servico_precisa_detalhes(srv):
    """A mudanca de etapa pode exigir novos detalhes, mesmo com protocolo conhecido."""
    if not _eh_protocolo_valido(srv.get("protocolo")):
        return True
    status = srv.get("status") or srv.get("statusAtual")
    fields = ["inicioDeslocamento"]
    if status in {"EXECUCAO", "CONCLUSAO"}:
        fields.append("inicioExecucao")
    if status == "CONCLUSAO":
        fields.append("termino")
        fields.append("retorno")
    return (any(not srv.get(f) for f in fields)
            or any(f in srv.get("camposEstimados", []) for f in fields)
            or srv.get("detalhesStatus") != status)


def _enriquecer_servicos_com_tabela_eventos(
    equipes: list[dict[str, typing.Any]],
    eventos_tabela: list[dict[str, typing.Any]],
) -> None:
    """Cruza os serviços extraídos da timeline com os protocolos detalhados da tbListagemEventos."""
    _enriquecer_tabela_segura(equipes, eventos_tabela)


def _obter_dados_timeline_equipes(
    session: requests.Session,
    equipes_filtro: set[str] | None = None,
) -> dict[str, list[dict[str, typing.Any]]]:
    """Obtém os links de timelines individuais (/paginas/timeline?id=...) e raspa marcadores com protocolos e coordenadas."""
    from concurrent.futures import ThreadPoolExecutor

    team_urls: dict[str, str] = {}
    try:
        r_dash = session.get(f"{URL_BASE}/paginas/dashboard", verify=False, timeout=20)
        if r_dash.status_code == 200:
            soup_dash = BeautifulSoup(r_dash.text, "html.parser")
            for a in soup_dash.find_all("a", href=True):
                href = a["href"]
                if "timeline?id=" in href:
                    text = a.text.strip()
                    if not text and a.find_parent("tr"):
                        text = a.find_parent("tr").text
                    m = re.search(r"\b(E[A-Z0-9]{3,7})\b", text)
                    if m:
                        code = m.group(1).upper()
                        if not equipes_filtro or code in equipes_filtro:
                            team_urls[code] = f"https://www.copel.com{href}" if href.startswith("/rtlweb") else (f"{URL_BASE}{href}" if href.startswith("/") else f"{URL_BASE}/{href}")
    except Exception as exc:
        logger.warning("Falha ao mapear links de timelines do dashboard: %s", exc)

    if not team_urls:
        return {}

    pattern_marker = re.compile(
        r'markerServico\s*=\s*L\.marker\(\[\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*\].*?'
        r'bindPopup\(["\'](.*?)["\']\).*?'
        r'bindTooltip\(["\'](.*?)["\']',
        re.DOTALL | re.IGNORECASE,
    )

    def _fetch_timeline(eq: str, url: str) -> tuple[str, list[dict[str, typing.Any]]]:
        try:
            r = session.get(url, verify=False, timeout=15)
            if r.status_code != 200:
                return eq, []
            matches = pattern_marker.findall(r.text)
            servicos = []
            for lat, lng, popup, seq in matches:
                m_prot = re.search(r"Protocolo[\s:-]*([0-9\.]+)", popup, re.IGNORECASE)
                m_tipo = re.search(r"Tipo[\s:-]*([^<]+)", popup, re.IGNORECASE)
                m_desl = re.search(r"Inicio\s+deslocamento[\s:-]*(\d{2}:\d{2})", popup, re.IGNORECASE)
                m_exec = re.search(r"Inicio\s+Execu[çc][ãa]o[\s:-]*(\d{2}:\d{2})", popup, re.IGNORECASE)
                m_term = re.search(r"Termino\s+Execu[çc][ãa]o[\s:-]*(\d{2}:\d{2})", popup, re.IGNORECASE)
                if m_prot:
                    prot_raw = m_prot.group(1).strip()
                    clean_prot = formatar_protocolo_copel(prot_raw)
                    servicos.append({
                        "sequencia": seq.strip(),
                        "protocolo": clean_prot,
                        "protocoloBruto": prot_raw,
                        "tipo": m_tipo.group(1).strip() if m_tipo else "",
                        "latitude": float(lat),
                        "longitude": float(lng),
                        "inicioDeslocamento": m_desl.group(1) if m_desl else "",
                        "inicioExecucao": m_exec.group(1) if m_exec else "",
                        "fimExecucao": m_term.group(1) if m_term else "",
                    })
            return eq, servicos
        except Exception:
            return eq, []

    results: dict[str, list[dict[str, typing.Any]]] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(_fetch_timeline, eq, url) for eq, url in team_urls.items()]
        for f in futures:
            eq, srvs = f.result()
            if srvs:
                results[eq] = srvs

    return results


def _eh_protocolo_valido(prot: typing.Any) -> bool:
    """Verifica se uma string representa um protocolo real e não um tipo/placeholder de serviço."""
    if not prot:
        return False
    prot_str = str(prot).strip().upper()
    if prot_str in ["UC", "CHAVE", "TRAFO", "ALIM", "ALIMENTADOR", "RISCO", "9901", "196", "NONE", "NULL", ""]:
        return False
    return bool(re.fullmatch(r"\d{7,15}(?:\.\d+)*", prot_str))


def _enriquecer_servicos_com_timelines_equipes(
    equipes: list[dict[str, typing.Any]],
    timelines_map: dict[str, list[dict[str, typing.Any]]],
) -> None:
    """Enriquece as ocorrências de cada equipe com protocolos e coordenadas extraídos de sua timeline individual."""
    if not timelines_map or not equipes:
        return

    for eq in equipes:
        eq_codigo = (eq.get("equipe_codigo") or eq.get("veiculo") or "").strip().upper()
        servicos_tl = timelines_map.get(eq_codigo, [])
        if not servicos_tl:
            continue

        todos_servicos = (eq.get("ss_executadas") or []) + (eq.get("ss_em_andamento") or [])
        for idx, srv in enumerate(todos_servicos):
            if _eh_protocolo_valido(srv.get("protocolo")):
                continue

            matched = None
            seq_srv = str(srv.get("sequencia") or "").strip()
            hora_ini = str(srv.get("inicioExecucao") or srv.get("inicioDeslocamento") or "").strip()[:5]
            hora_fim = str(srv.get("termino") or srv.get("retorno") or "").strip()[:5]

            # 1. Tenta casar por sequência
            if seq_srv:
                for s_tl in servicos_tl:
                    if s_tl.get("sequencia") == seq_srv:
                        matched = s_tl
                        break

            # 2. Tenta casar por horário de início ou fim
            if not matched:
                for s_tl in servicos_tl:
                    tl_ini = s_tl.get("inicioExecucao") or s_tl.get("inicioDeslocamento") or ""
                    tl_fim = s_tl.get("fimExecucao") or ""
                    if hora_ini and tl_ini and hora_ini == tl_ini:
                        matched = s_tl
                        break
                    if hora_fim and tl_fim and hora_fim == tl_fim:
                        matched = s_tl
                        break

            # 3. Fallback por índice posicional
            if not matched and idx < len(servicos_tl):
                matched = servicos_tl[idx]

            if matched:
                if matched.get("protocolo"):
                    srv["protocolo"] = matched["protocolo"]
                    srv["protocoloBruto"] = matched.get("protocoloBruto") or matched["protocolo"]
                    srv["ssId"] = matched["protocolo"]
                if matched.get("latitude") is not None:
                    srv["latitude"] = matched["latitude"]
                    srv["longitude"] = matched["longitude"]
                    srv["geolocalizacao"] = {
                        "latitude": matched["latitude"],
                        "longitude": matched["longitude"],
                    }
                if matched.get("sequencia") and not srv.get("sequencia"):
                    srv["sequencia"] = matched["sequencia"]
                if matched.get("inicioDeslocamento") and not srv.get("inicioDeslocamento"):
                    srv["inicioDeslocamento"] = matched["inicioDeslocamento"]
                if matched.get("inicioExecucao") and not srv.get("inicioExecucao"):
                    srv["inicioExecucao"] = matched["inicioExecucao"]
                if matched.get("fimExecucao") and not srv.get("termino"):
                    srv["termino"] = matched["fimExecucao"]


_CLIQUE_EVENTOS_CACHE: dict[tuple[int, int | None, str], dict[str, typing.Any]] = {}
_CLIQUE_CACHE_LOCK = threading.RLock()


def _forcar_cliques_timeline_tempo_real(
    session: requests.Session,
    view_state: str,
    raw_items: list[dict[str, typing.Any]],
    event_indices: set[int] | None = None,
) -> dict[int, dict[str, typing.Any]]:
    """
    Simula o clique em cada quadrado/evento da timeline na página /paginas/tempoReal,
    disparando o evento AJAX 'select' com 'form:cm-patientregistry-facesheet-timeline_eventIdx'.
    Reutiliza eventos concluidos e consulta novos eventos sequencialmente na sessao JSF.
    """
    global _CLIQUE_EVENTOS_CACHE
    service_items = [
        item for item in raw_items
        if (event_indices is None or item.get("idx") in event_indices)
        and (
            "tempoRealExecutado" in item.get("className", "")
            or "tempoRealEmExecucao" in item.get("className", "")
            or "tempoRealEmDeslocamento" in item.get("className", "")
            or "tempoRealPendente" in item.get("className", "")
        )
    ]

    if not service_items or not view_state:
        return {}

    url_tempo_real = f"{URL_BASE}/paginas/tempoReal"
    headers = {
        "Faces-Request": "partial/ajax",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }

    cliques_by_idx: dict[int, dict[str, typing.Any]] = {}
    items_to_fetch: list[dict[str, typing.Any]] = []

    with _CLIQUE_CACHE_LOCK:
        for item in service_items:
            idx = item["idx"]
            cls = item.get("className", "")
            start_ms = item.get("start")
            end_ms = item.get("end")
            group = item.get("group", "")
            is_executado = "tempoRealExecutado" in cls

            cache_key = (start_ms, end_ms, group, item.get("content"), idx)
            if is_executado and cache_key in _CLIQUE_EVENTOS_CACHE:
                cached = dict(_CLIQUE_EVENTOS_CACHE[cache_key])
                cached["eventIdx"] = idx
                cliques_by_idx[idx] = cached
            else:
                items_to_fetch.append(item)

    if not items_to_fetch:
        return cliques_by_idx

    def _fetch_event_popup(item: dict[str, typing.Any]) -> tuple[int, dict[str, typing.Any] | None, tuple | None, bool]:
        idx = item["idx"]
        cls = item.get("className", "")
        start_ms = item.get("start")
        end_ms = item.get("end")
        group = item.get("group", "")
        is_executado = "tempoRealExecutado" in cls
        cache_key = (start_ms, end_ms, group, item.get("content"), idx) if is_executado else None

        payload = {
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": "form:cm-patientregistry-facesheet-timeline",
            "javax.faces.partial.execute": "form:cm-patientregistry-facesheet-timeline",
            "javax.faces.partial.render": "form:panelAtualizacaoMapa",
            "javax.faces.behavior.event": "select",
            "javax.faces.partial.event": "select",
            "form:cm-patientregistry-facesheet-timeline_eventIdx": str(idx),
            "form": "form",
            "javax.faces.ViewState": view_state,
        }
        try:
            r = session.post(url_tempo_real, data=payload, headers=headers, verify=False, timeout=8)
            if r.status_code == 200:
                popups = re.findall(
                    r"voarParaCoordenadaZoom\(\s*\[(-?\d+\.\d+),\s*(-?\d+\.\d+)\],\s*\d+,\s*['\"](.*?)['\"]\s*\)",
                    r.text,
                    re.DOTALL,
                )
                for lat, lng, popup in popups:
                    p_clean = popup.replace(r"\'", "'").replace(r"\n", " ").replace("<BR />", "\n").replace("<br />", "\n")
                    m_prot = re.search(r"Protocolo[\s:-]*([0-9\.]+)", p_clean, re.IGNORECASE)
                    m_seq = re.search(r"Sequ[eê]ncia[\s:-]*([^\n]+)", p_clean, re.IGNORECASE)
                    m_status = re.search(r"Status[\s:-]*([^\n]+)", p_clean, re.IGNORECASE)
                    m_tipo = re.search(r"Tipo[\s:-]*([^\n]+)", p_clean, re.IGNORECASE)
                    m_cat = re.search(r"Categoria[\s:-]*([^\n]+)", p_clean, re.IGNORECASE)
                    m_desl = re.search(r"In[ií]cio\s+Deslocamento[\s:-]*(\d{2}:\d{2})", p_clean, re.IGNORECASE)
                    m_exec = re.search(r"In[ií]cio\s+Execu[çc][ãa]o[\s:-]*(\d{2}:\d{2})", p_clean, re.IGNORECASE)
                    m_term = re.search(r"T[eé]rmino[\s:-]*(\d{2}:\d{2})", p_clean, re.IGNORECASE)
                    m_ret = re.search(r"Retorno[\s:-]*(\d{2}:\d{2})", p_clean, re.IGNORECASE)

                    prot_raw = m_prot.group(1).strip() if m_prot else None
                    clean_prot = formatar_protocolo_copel(prot_raw) if prot_raw else None

                    ini_desl_val = m_desl.group(1) if m_desl else None
                    ini_exec_val = m_exec.group(1) if m_exec else None
                    if ini_desl_val and ini_exec_val and ini_exec_val < ini_desl_val:
                        ini_exec_val = ini_desl_val

                    data = {
                        "eventIdx": idx,
                        "protocolo": clean_prot or prot_raw,
                        "protocoloBruto": prot_raw,
                        "sequencia": m_seq.group(1).strip() if m_seq else None,
                        "status": m_status.group(1).strip() if m_status else None,
                        "tipo": m_tipo.group(1).strip() if m_tipo else item.get("content", ""),
                        "categoria": m_cat.group(1).strip() if m_cat else None,
                        "latitude": float(lat),
                        "longitude": float(lng),
                        "inicioDeslocamento": ini_desl_val,
                        "inicioExecucao": ini_exec_val,
                        "termino": m_term.group(1) if m_term else None,
                        "retorno": m_ret.group(1) if m_ret else None,
                        "start_ms": item.get("start"),
                        "end_ms": item.get("end"),
                    }
                    equipe_popup = re.search(r"Equipe[\s:-]*(E[A-Z0-9]{3,7})\b", p_clean, re.IGNORECASE)
                    equipe_item = parse_group_string(group).get("equipe_codigo", "")
                    if not equipe_popup or equipe_popup.group(1).upper() != equipe_item.upper():
                        linha_timeline = " ".join(str(group or "").split()) or "<linha vazia>"
                        equipe_encontrada = equipe_popup.group(1).upper() if equipe_popup else "<ausente>"
                        logger.warning(
                            "Popup sem identidade de equipe confirmada: evento=%s; linha=%r; "
                            "equipe_linha=%s; equipe_popup=%s",
                            idx,
                            linha_timeline,
                            equipe_item or "<ausente>",
                            equipe_encontrada,
                        )
                        return idx, None, None, False
                    if data.get("tipo") != item.get("content"):
                        return idx, None, None, False
                    if data.get("inicioExecucao") != _convert_ms_to_hora(start_ms):
                        return idx, None, None, False
                    return idx, data, cache_key, is_executado
        except Exception:
            pass
        return idx, None, None, False

    popup_started = time.monotonic()
    for item in items_to_fetch:
        if time.monotonic() - popup_started >= 120:
            logger.warning("Limite de 120s dos popups atingido; detalhes restantes pendentes.")
            break
        try:
            idx, data, cache_key, is_executado = _fetch_event_popup(item)
            if data:
                cliques_by_idx[idx] = data
                if is_executado and cache_key and data.get("protocolo"):
                    with _CLIQUE_CACHE_LOCK:
                        _CLIQUE_EVENTOS_CACHE[cache_key] = data
        except Exception:
            pass

    return cliques_by_idx



