"""
Serviço de captura e estruturação de dados do ROTALOG Tempo Real (/paginas/tempoReal).
Extrai marcadores de Turno (T), Intervalo, Emergências, Serviços Comerciais e status de conectividade de cada equipe,
estruturando as Ordens de Serviço (SS) com tratamento de Protocolos (removendo o sufixo .x.y) para integração com o BDO.
"""

from __future__ import annotations

import datetime
import logging
import html as html_lib
import os
import re
import time
import typing
from bs4 import BeautifulSoup
import requests

from boletim_x_ponto.services.rotalog_crawler_service import CrawlerRotalog

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


def _convert_ms_to_iso(ms: int | str | None) -> str | None:
    if not ms or not str(ms).isdigit():
        return None
    try:
        dt = datetime.datetime.fromtimestamp(int(ms) / 1000.0, tz=datetime.timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def _convert_ms_to_hora(ms: int | str | None) -> str:
    if not ms or not str(ms).isdigit():
        return ""
    try:
        dt = datetime.datetime.fromtimestamp(int(ms) / 1000.0, tz=datetime.timezone.utc)
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


def _obter_inicio_dia_operacional_ms() -> int:
    """Retorna o timestamp em ms da mudança do dia (meia-noite 00:00:00)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    meia_noite = datetime.datetime.combine(now.date(), datetime.time(0, 0, 0), tzinfo=datetime.timezone.utc)
    return int(meia_noite.timestamp() * 1000)


def consolidar_turno_por_contexto(
    marcadores_t: list[dict[str, typing.Any]],
    eventos_servico_ms: list[int],
    tem_atividade_andamento: bool = False,
    retorno_ultimo_servico_ms: int | None = None,
) -> dict[str, typing.Any]:
    """Classifica o turno da equipe no Rotalog.

    Abre automaticamente se a equipe possui serviço em andamento (à esquerda da linha vermelha)
    ou se executou qualquer serviço no dia operacional.
    Caso o turno feche sem marcador T explícito, prioriza o horário de RETORNO da equipe no último serviço.
    Se não houver RETORNO, assume o horário de TÉRMINO do último serviço.
    """
    inicio_dia_ms = _obter_inicio_dia_operacional_ms()
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

    # 1. Se possui atividade em andamento no momento (à esquerda da linha vermelha) -> ABERTO
    if tem_atividade_andamento:
        inicio_t = services_today[0] if services_today else (all_services[-1] if all_services else None)
        result.update({
            "aberto": True,
            "inicio_ms": inicio_t,
            "inicio_iso": _convert_ms_to_iso(inicio_t) if inicio_t else None,
            "classificacao": "ABERTO",
        })
        return result

    # 2. Se possui marcadores T de encerramento/abertura
    if markers:
        last_t = int(markers[-1]["start"])
        has_service_after = any(value > last_t for value in all_services)
        has_service_before = any(value < last_t for value in all_services)

        if has_service_after:
            result.update({
                "aberto": True,
                "inicio_ms": last_t,
                "inicio_iso": _convert_ms_to_iso(last_t),
                "classificacao": "ABERTO",
            })
            return result

        if has_service_before:
            opening_ms = None
            for marker in reversed(markers[:-1]):
                candidate = int(marker["start"])
                if any(candidate < value < last_t for value in all_services):
                    opening_ms = candidate
                    break
            if opening_ms is None and all_services:
                opening_ms = all_services[0]

            result.update({
                "inicio_ms": opening_ms,
                "inicio_iso": _convert_ms_to_iso(opening_ms) if opening_ms else None,
                "fim_ms": last_t,
                "fim_iso": _convert_ms_to_iso(last_t),
                "classificacao": "FECHADO",
            })
            return result

    # 3. Sem marcador T, mas com serviços executados no dia atual (após 00:00) -> ABERTO
    if services_today:
        result.update({
            "aberto": True,
            "inicio_ms": services_today[0],
            "inicio_iso": _convert_ms_to_iso(services_today[0]),
            "classificacao": "ABERTO",
        })
        return result

    # 4. Sem indicação CLARA de fim de turno (sem T) e sem serviço em andamento:
    # Prioridade 1: Horário de Retorno da equipe (se houver)
    # Prioridade 2: Horário de Término do último serviço
    if all_services:
        primeiro_servico_ms = all_services[0]
        fim_turno_ms = retorno_ultimo_servico_ms if retorno_ultimo_servico_ms else all_services[-1]

        result.update({
            "aberto": False,
            "inicio_ms": primeiro_servico_ms,
            "inicio_iso": _convert_ms_to_iso(primeiro_servico_ms),
            "fim_ms": fim_turno_ms,
            "fim_iso": _convert_ms_to_iso(fim_turno_ms),
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
        return []

    js_clean = re.sub(r"new Date\((\d+)\)", r"\1", timeline_script)
    pattern = r'\{"start":\s*(\d+)\s*,\s*"end":\s*(\d+|\w+)\s*,\s*"editable":\s*(true|false)\s*,\s*"group":\s*"(.*?)"\s*,\s*"className":\s*"(.*?)"\s*,\s*"content":\s*"(.*?)"\}'

    raw_items = []
    for match in re.finditer(pattern, js_clean):
        start_ms, end_ms, editable, group, class_name, content = match.groups()
        raw_items.append({
            "start": int(start_ms) if start_ms.isdigit() else 0,
            "end": int(end_ms) if end_ms.isdigit() else None,
            "group": group.strip(),
            "className": class_name.strip(),
            "content": content.strip()
        })

    equipas_map: dict[str, dict[str, typing.Any]] = {}

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
        popup_info = (
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
                "ssId": prot_real,
                "protocolo": prot_real,
                "protocoloBruto": popup_info.get("protocoloBruto") or prot_real,
                "categoria": categoria,
                "tipo": tipo_real,
                "status": "CONCLUSAO",
                "inicioDeslocamento": popup_info.get("inicioDeslocamento") or hora_inicio,
                "inicioExecucao": popup_info.get("inicioExecucao") or hora_inicio,
                "termino": hora_fim,
                "retorno": popup_info.get("retorno") or hora_fim,
                "sequencia": popup_info.get("sequencia") or "",
                "latitude": popup_info.get("latitude"),
                "longitude": popup_info.get("longitude"),
                "geolocalizacao": popup_info.get("geolocalizacao"),                "inicioIso": _convert_ms_to_iso(item["start"]),
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
                "ssId": prot_real,
                "protocolo": prot_real,
                "protocoloBruto": popup_info.get("protocoloBruto") or prot_real,
                "status": status_str,
                "categoria": categoria,
                "tipo": tipo_real,
                "inicioDeslocamento": popup_info.get("inicioDeslocamento") or hora_inicio,
                "inicioExecucao": popup_info.get("inicioExecucao") or (hora_inicio if status_str == "EXECUCAO" else ""),
                "termino": popup_info.get("termino") or "",
                "retorno": popup_info.get("retorno") or "",
                "sequencia": popup_info.get("sequencia") or "",
                "latitude": popup_info.get("latitude"),
                "longitude": popup_info.get("longitude"),
                "geolocalizacao": popup_info.get("geolocalizacao"),                "inicioIso": _convert_ms_to_iso(item["start"]),
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
    protocolos_ausentes = []
    for eq in resultado:
        for service in eq.get("ss_em_andamento", []):
            if not service.get("protocolo"):
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
        logger.warning(
            "ROTALOG: %s serviço(s) em andamento sem protocolo no conteúdo recebido:\n%s",
            len(protocolos_ausentes),
            linhas_protocolos,
        )
    for eq in resultado:
        eventos_servico_ms = eq.pop("eventos_servico_ms", [])
        tem_andamento = bool(eq.get("ss_em_andamento") or eq.get("atividade_atual"))
        retorno_ultimo_ms = None
        if eq.get("ss_executadas"):
            last_exec = eq["ss_executadas"][-1]
            retorno_ultimo_ms = last_exec.get("retornoMs")

        turno_contextual = consolidar_turno_por_contexto(
            eq["turno_marcadores_t"],
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

    return resultado
