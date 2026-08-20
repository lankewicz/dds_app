"""
Serviço de captura e estruturação de dados do ROTALOG Tempo Real (/paginas/tempoReal).
Extrai marcadores de Turno (T), Intervalo, Emergências, Serviços Comerciais e status de conectividade de cada equipe,
estruturando as Ordens de Serviço (SS) com tratamento de Protocolos (removendo o sufixo .x.y) para integração com o BDO.
"""

from __future__ import annotations

import datetime
import os
import re
import time
import typing
from bs4 import BeautifulSoup
import requests

from boletim_x_ponto.services.rotalog_crawler_service import CrawlerRotalog

URL_BASE = "https://www.copel.com/rtlweb"
URL_TEMPO_REAL = f"{URL_BASE}/paginas/tempoReal"


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


def extrair_dados_tempo_real(crawler: CrawlerRotalog | None = None, max_tentativas: int = 3) -> list[dict[str, typing.Any]]:
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
            meta = parse_group_string(group_raw)
            equipas_map[group_raw] = {
                "group_raw": group_raw,
                "equipe_codigo": meta["equipe_codigo"],
                "veiculo": meta["veiculo"],
                "colaborador": meta["colaborador"],
                "status_conexao": meta["status_conexao"],
                "is_online": meta["is_online"],
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
                "atividade_atual": None,
                "bdo_list": [],
                "ss_executadas": [],
                "ss_em_andamento": [],
                "ss_pendentes": []
            }

        eq_dict = equipas_map[group_raw]
        cls = item["className"]
        cnt = item["content"]

        # 1. Marcador de Turno "T"
        if cnt == "T" and cls == "tempoRealMacro":
            eq_dict["turno_marcadores_t"].append({
                "start": item["start"],
                "end": item["end"]
            })

        # 2. Marcador de Intervalo
        elif cnt == "INTERVALO" or "intervalo" in cls.lower():
            eq_dict["intervalo"]["em_intervalo"] = True
            eq_dict["intervalo"]["inicio_ms"] = item["start"]
            if isinstance(item["end"], int):
                eq_dict["intervalo"]["fim_ms"] = item["end"]

        # 3. SSs Executadas (BDO)
        elif "Executado" in cls:
            prot_limpo = limpar_protocolo(cnt)
            categoria = "EMERGENCIA" if "Emergencia" in cls else "COMERCIAL"
            hora_inicio = _convert_ms_to_hora(item["start"])
            hora_fim = _convert_ms_to_hora(item["end"]) if isinstance(item["end"], int) else ""

            ss_item = {
                "ssId": prot_limpo,
                "protocoloBruto": cnt,
                "categoria": categoria,
                "tipo": cnt,
                "status": "CONCLUSAO",
                "inicioDeslocamento": hora_inicio,
                "inicioExecucao": hora_inicio,
                "termino": hora_fim,
                "retorno": hora_fim,
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
            prot_limpo = limpar_protocolo(cnt)
            status_str = "DESLOCAMENTO" if "EmDeslocamento" in cls else "EXECUCAO"
            categoria = "EMERGENCIA" if "Emergencia" in cls else "COMERCIAL"
            hora_inicio = _convert_ms_to_hora(item["start"])

            ss_andamento = {
                "ssId": prot_limpo,
                "protocoloBruto": cnt,
                "status": status_str,
                "categoria": categoria,
                "tipo": cnt,
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

    resultado = list(equipas_map.values())
    for eq in resultado:
        t_list = sorted(eq["turno_marcadores_t"], key=lambda x: x["start"])
        if t_list:
            primeiro_t = t_list[0]
            eq["turno"]["aberto"] = True
            eq["turno"]["inicio_ms"] = primeiro_t["start"]
            eq["turno"]["inicio_iso"] = _convert_ms_to_iso(primeiro_t["start"])

            if len(t_list) >= 2:
                ultimo_t = t_list[-1]
                if (ultimo_t["start"] - primeiro_t["start"]) > 600_000:
                    eq["turno"]["fim_ms"] = ultimo_t["start"]
                    eq["turno"]["fim_iso"] = _convert_ms_to_iso(ultimo_t["start"])

        if eq["turno"]["inicio_ms"] and not eq["turno"]["fim_ms"]:
            if eq["intervalo"]["em_intervalo"]:
                eq["estado_consolidado"] = "INTERVALO"
            elif eq["atividade_atual"] and eq["atividade_atual"]["status"] == "DESLOCAMENTO":
                eq["estado_consolidado"] = "DESLOCAMENTO_ESPECIAL"
            else:
                eq["estado_consolidado"] = "ABERTO"
        elif eq["turno"]["inicio_ms"] and eq["turno"]["fim_ms"]:
            eq["estado_consolidado"] = "FECHADO"
        else:
            eq["estado_consolidado"] = "FECHADO"

    return resultado
