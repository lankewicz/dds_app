"""Visão comparativa por veículo/equipe baseada nos dados do ROTALOG."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

import pandas as pd

from bdo.services.constantes import HEADERS_VIZ, MAP_BOL, MAP_PTO


METRICAS_BOLETIM = {visual: origem for origem, visual in MAP_BOL.items()}
METRICAS_PONTO = dict(MAP_PTO)


def normalizar_texto(valor) -> str:
    texto = "" if valor is None else str(valor).strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^A-Z0-9]+", " ", texto.upper())
    return " ".join(texto.split())


def nome_sem_matricula(valor) -> str:
    return re.sub(r"^\s*\d{4,8}\s*[-–—]?\s*", "", str(valor or "")).strip()


def normalizar_veiculo(valor) -> str:
    """Agrupa variações como E3188 (2) e E3188 (3) em E3188."""
    texto = str(valor or "").strip().upper()
    return re.sub(r"\s*\(\d+\)\s*$", "", texto).strip()


def _coluna(df: pd.DataFrame, *candidatas: str) -> str | None:
    if df is None:
        return None
    exatas = {str(c): c for c in df.columns}
    normalizadas = {normalizar_texto(c): c for c in df.columns}
    for candidata in candidatas:
        if candidata in exatas:
            return exatas[candidata]
        encontrada = normalizadas.get(normalizar_texto(candidata))
        if encontrada is not None:
            return encontrada
    return None


def _data_turno(valor):
    encontrado = re.search(r"(\d{2}/\d{2}/\d{4})", str(valor or ""))
    if not encontrado:
        return pd.NaT
    return pd.to_datetime(
        encontrado.group(1), format="%d/%m/%Y", errors="coerce"
    ).normalize()


def _data_hora(valor):
    """Converte os horários textuais do ROTALOG em timestamp local."""
    texto = str(valor or "").strip()
    if not texto:
        return pd.NaT
    encontrado = re.search(r"(\d{2}/\d{2}/\d{2,4})\s+(\d{2}:\d{2})", texto)
    if not encontrado:
        return pd.NaT
    return pd.to_datetime(
        f"{encontrado.group(1)} {encontrado.group(2)}",
        dayfirst=True,
        errors="coerce",
    )


def _iso_data_hora(valor) -> str | None:
    convertido = _data_hora(valor)
    return convertido.isoformat() if pd.notna(convertido) else None


def _detalhes_turno(valor, dia, duracao="") -> dict:
    """Extrai abertura e encerramento de textos como '(01/07) 23:39'."""
    texto = str(valor or "").strip()
    ano = pd.Timestamp(dia).year
    pares = re.findall(
        r"\((\d{2}/\d{2}(?:/\d{2,4})?)\)\s*(\d{2}:\d{2})",
        texto,
    )
    if len(pares) < 2:
        referencia = re.search(r"(\d{2}/\d{2}/\d{4})", texto)
        horas = re.findall(r"(?<!\d)(\d{2}:\d{2})(?!\d)", texto)
        if referencia and len(horas) >= 2:
            data_referencia = pd.to_datetime(
                referencia.group(1), format="%d/%m/%Y", errors="coerce"
            )
            if pd.notna(data_referencia):
                data_texto = data_referencia.strftime("%d/%m/%Y")
                pares = [(data_texto, horas[-2]), (data_texto, horas[-1])]
    datas = []
    for data_texto, hora in pares[-2:]:
        if data_texto.count("/") == 1:
            data_texto = f"{data_texto}/{ano}"
        datas.append(pd.to_datetime(
            f"{data_texto} {hora}", dayfirst=True, errors="coerce"
        ))
    if len(datas) < 2:
        return {
            "inicio": None, "fim": None,
            "inicio_exibicao": "-", "fim_exibicao": "-",
            "duracao": str(duracao or ""),
        }
    inicio, fim = datas[0], datas[1]
    if pd.notna(inicio) and pd.notna(fim) and fim < inicio:
        fim = fim + pd.DateOffset(years=1)
    return {
        "inicio": inicio.isoformat() if pd.notna(inicio) else None,
        "fim": fim.isoformat() if pd.notna(fim) else None,
        "inicio_exibicao": inicio.strftime("%d/%m %H:%M") if pd.notna(inicio) else "-",
        "fim_exibicao": fim.strftime("%d/%m %H:%M") if pd.notna(fim) else "-",
        "duracao": str(duracao or ""),
    }


def _data_evento(row: pd.Series):
    valor_data = row.get("Data")
    if pd.notna(valor_data):
        convertido = pd.to_datetime(valor_data, errors="coerce", dayfirst=True)
        if pd.notna(convertido):
            return convertido.normalize()
    for coluna in ("Inicio Deslo", "Inicio Exec", "Fim Exec", "Retorno"):
        encontrado = re.search(r"(\d{2}/\d{2}/\d{2,4})", str(row.get(coluna, "")))
        if encontrado:
            return pd.to_datetime(
                encontrado.group(1), dayfirst=True, errors="coerce"
            ).normalize()
    return pd.NaT


def _tempo_decimal(valor) -> float:
    if isinstance(valor, (int, float)) and pd.notna(valor):
        return float(valor)
    encontrado = re.match(r"^\s*(-?)(\d+):(\d{2})\s*$", str(valor or ""))
    if not encontrado:
        return 0.0
    sinal = -1 if encontrado.group(1) else 1
    return sinal * (int(encontrado.group(2)) + int(encontrado.group(3)) / 60.0)


def _valor_bruto_json(valor) -> str:
    """Mantém a representação importada, removendo apenas nulos do DataFrame."""
    if valor is None or (not isinstance(valor, (list, dict)) and pd.isna(valor)):
        return ""
    if isinstance(valor, pd.Timestamp):
        return valor.isoformat()
    return str(valor)


def listar_veiculos(
    df_equipes: pd.DataFrame,
    df_eventos: pd.DataFrame,
    contrato: str | None = None,
) -> list[str]:
    valores: set[str] = set()
    for origem in (df_equipes, df_eventos):
        if origem is None or origem.empty:
            continue
        df = origem
        coluna_contrato = _coluna(df, "Contrato")
        if contrato and coluna_contrato:
            df = df[df[coluna_contrato].astype(str).str.strip() == str(contrato).strip()]
        coluna_veiculo = _coluna(df, "Veículo", "Veiculo", "Equipe")
        if coluna_veiculo:
            valores.update(normalizar_veiculo(v) for v in df[coluna_veiculo].dropna())
    return sorted(v for v in valores if v.startswith("E3"))


def _resolver_nome(
    nome_rotalog: str,
    relacao: pd.DataFrame,
    candidatos_boletim: list[str],
) -> tuple[str, str]:
    nome_limpo = nome_sem_matricula(nome_rotalog)
    alvo = normalizar_texto(nome_limpo)
    if relacao is not None and not relacao.empty:
        for _, row in relacao.iterrows():
            nome_b = str(row.get("Nome_Boletim", "") or "").strip()
            nome_p = str(row.get("Nome_Ponto_Mapeado", "") or "").strip()
            if alvo and alvo in {normalizar_texto(nome_b), normalizar_texto(nome_p)}:
                return nome_b or nome_p, nome_p or nome_b

    melhor, score = nome_limpo, 0.0
    for candidato in candidatos_boletim:
        atual = SequenceMatcher(None, alvo, normalizar_texto(candidato)).ratio()
        if atual > score:
            melhor, score = candidato, atual
    nome_b = melhor if score >= 0.72 else nome_limpo
    nome_p = nome_b
    if relacao is not None and not relacao.empty and "Nome_Boletim" in relacao:
        mask = relacao["Nome_Boletim"].astype(str).map(normalizar_texto) == normalizar_texto(nome_b)
        encontrados = relacao[mask]
        if not encontrados.empty:
            mapeado = str(encontrados.iloc[-1].get("Nome_Ponto_Mapeado", "") or "").strip()
            if mapeado:
                nome_p = mapeado
    return nome_b, nome_p


def _indice_metricas(
    df: pd.DataFrame,
    coluna_nome: str,
    coluna_data: str,
    metricas: dict[str, str],
    data_ini,
    data_fim,
) -> dict:
    if df is None or df.empty or coluna_nome not in df or coluna_data not in df:
        return {}
    base = df.copy()
    base["_nome"] = base[coluna_nome].astype(str).map(normalizar_texto)
    base["_dia"] = pd.to_datetime(base[coluna_data], errors="coerce").dt.normalize()
    base = base[base["_dia"].between(pd.Timestamp(data_ini), pd.Timestamp(data_fim))]
    colunas = [origem for origem in metricas.values() if origem in base]
    for coluna in colunas:
        base[coluna] = pd.to_numeric(base[coluna], errors="coerce").fillna(0.0)
    if not colunas:
        return {}
    return base.groupby(["_nome", "_dia"])[colunas].sum().to_dict("index")


def construir_visao_veiculo(
    df_equipes: pd.DataFrame,
    df_eventos: pd.DataFrame,
    df_boletim: pd.DataFrame,
    df_ponto: pd.DataFrame,
    relacao: pd.DataFrame,
    veiculo: str,
    data_ini,
    data_fim,
    contrato: str | None = None,
) -> dict:
    inicio, fim = pd.Timestamp(data_ini).normalize(), pd.Timestamp(data_fim).normalize()
    equipes = df_equipes.copy() if df_equipes is not None else pd.DataFrame()
    coluna_veiculo = _coluna(equipes, "Veículo", "Veiculo", "Equipe")
    if equipes.empty or not coluna_veiculo:
        return {
            "headers": HEADERS_VIZ,
            "linhas": [],
            "servicos": {},
            "eventos": [],
            "eventos_brutos": {"colunas": [], "linhas": []},
        }

    coluna_turno = _coluna(equipes, "Data Referência - Turno")
    coluna_contrato = _coluna(equipes, "Contrato")
    if contrato and coluna_contrato:
        equipes = equipes[
            equipes[coluna_contrato].astype(str).str.strip() == str(contrato).strip()
        ]
    equipes["_veiculo"] = equipes[coluna_veiculo].map(normalizar_veiculo)
    if "Data" in equipes:
        equipes["_dia"] = pd.to_datetime(equipes["Data"], errors="coerce").dt.normalize()
    else:
        equipes["_dia"] = equipes[coluna_turno].map(_data_turno) if coluna_turno else pd.NaT
    equipes = equipes[
        (equipes["_veiculo"] == normalizar_veiculo(veiculo))
        & equipes["_dia"].between(inicio, fim)
    ]

    if contrato and df_boletim is not None and "Contrato" in df_boletim:
        df_boletim = df_boletim[
            df_boletim["Contrato"].astype(str).str.strip() == str(contrato).strip()
        ]
    indice_bol = _indice_metricas(
        df_boletim, "Funcionário", "DATA", METRICAS_BOLETIM, inicio, fim
    )
    indice_ponto = _indice_metricas(
        df_ponto, "Nome", "Data", METRICAS_PONTO, inicio, fim
    )
    candidatos = (
        df_boletim["Funcionário"].dropna().astype(str).unique().tolist()
        if df_boletim is not None and not df_boletim.empty and "Funcionário" in df_boletim
        else []
    )

    servicos: dict[str, list[dict]] = {}
    eventos_lista: list[dict] = []
    eventos_brutos_colunas: list[str] = []
    eventos_brutos_linhas: list[dict] = []
    eventos = df_eventos.copy() if df_eventos is not None else pd.DataFrame()
    coluna_veiculo_evento = _coluna(eventos, "Veículo", "Veiculo", "Equipe")
    if not eventos.empty and coluna_veiculo_evento:
        coluna_contrato_evento = _coluna(eventos, "Contrato")
        if contrato and coluna_contrato_evento:
            eventos = eventos[
                eventos[coluna_contrato_evento].astype(str).str.strip() == str(contrato).strip()
            ]
        eventos["_veiculo"] = eventos[coluna_veiculo_evento].map(normalizar_veiculo)
        eventos = eventos[eventos["_veiculo"] == normalizar_veiculo(veiculo)].copy()
        eventos["_dia"] = eventos.apply(_data_evento, axis=1)
        eventos = eventos[eventos["_dia"].between(inicio, fim)]
        dedupe = [
            c for c in ("Protocolo", "Evento", "Inicio Deslo", "Inicio Exec", "Fim Exec")
            if c in eventos
        ]
        colunas_detalhe = {
            "veiculo": coluna_veiculo_evento,
            "tablet": _coluna(eventos, "Tablet"),
            "agencia": _coluna(eventos, "Agência", "Agencia"),
            "contrato": coluna_contrato_evento,
            "eletricista_1": _coluna(eventos, "Eletricista 1"),
            "eletricista_2": _coluna(eventos, "Eletricista 2"),
            "protocolo": _coluna(eventos, "Protocolo"),
            "evento": _coluna(eventos, "Evento"),
            "tipo": _coluna(eventos, "Tipo"),
            "codigo": _coluna(eventos, "Codigo", "Código"),
            "grupos": _coluna(eventos, "Grupos"),
            "impedimento": _coluna(eventos, "Imped", "Impedimento"),
            "inicio_deslocamento": _coluna(eventos, "Inicio Deslo"),
            "tempo_deslocamento": _coluna(eventos, "Tempo Deslo"),
            "inicio_execucao": _coluna(eventos, "Inicio Exec"),
            "fim_execucao": _coluna(eventos, "Fim Exec"),
            "tempo_execucao": _coluna(eventos, "Tempo Exec"),
            "retorno": _coluna(eventos, "Retorno"),
            "tempo_retorno": _coluna(eventos, "Tempo Retorno"),
            "km_informado": _coluna(eventos, "Informado com limitador (km)"),
            "km_autorizado": _coluna(eventos, "Autorizado final(km)", "Autorizado Final (km)"),
            "acoes": _coluna(eventos, "Ações", "Acoes"),
        }

        def texto_evento(row, chave: str) -> str:
            coluna = colunas_detalhe.get(chave)
            valor = row.get(coluna, "") if coluna else ""
            return "" if pd.isna(valor) else str(valor).strip()

        if dedupe:
            eventos = eventos.drop_duplicates(subset=dedupe)
        eventos_brutos_colunas = [
            str(coluna) for coluna in eventos.columns
            if not str(coluna).startswith("_")
        ]
        eventos_brutos_linhas = [
            {coluna: _valor_bruto_json(row.get(coluna, "")) for coluna in eventos_brutos_colunas}
            for _, row in eventos.iterrows()
        ]
        for dia, grupo in eventos.groupby("_dia", sort=True):
            registros = []
            for _, row in grupo.iterrows():
                inicio_deslocamento = texto_evento(row, "inicio_deslocamento")
                inicio_execucao = texto_evento(row, "inicio_execucao")
                fim_execucao = texto_evento(row, "fim_execucao")
                retorno = texto_evento(row, "retorno")
                registro = {
                    "data": dia.strftime("%Y-%m-%d"),
                    "data_exibicao": dia.strftime("%d/%m/%Y"),
                    "veiculo": texto_evento(row, "veiculo"),
                    "tablet": texto_evento(row, "tablet"),
                    "agencia": texto_evento(row, "agencia"),
                    "contrato": texto_evento(row, "contrato"),
                    "eletricista_1": texto_evento(row, "eletricista_1"),
                    "eletricista_2": texto_evento(row, "eletricista_2"),
                    "protocolo": texto_evento(row, "protocolo"),
                    "evento": texto_evento(row, "evento"),
                    "tipo": texto_evento(row, "tipo"),
                    "codigo": texto_evento(row, "codigo"),
                    "grupos": texto_evento(row, "grupos"),
                    "impedimento": texto_evento(row, "impedimento"),
                    "inicio_deslocamento": inicio_deslocamento,
                    "tempo_deslocamento": texto_evento(row, "tempo_deslocamento"),
                    "inicio_execucao": inicio_execucao,
                    "fim_execucao": fim_execucao,
                    "tempo_execucao": texto_evento(row, "tempo_execucao"),
                    "retorno": retorno,
                    "tempo_retorno": texto_evento(row, "tempo_retorno"),
                    "km_informado": texto_evento(row, "km_informado"),
                    "km_autorizado": texto_evento(row, "km_autorizado"),
                    "acoes": texto_evento(row, "acoes"),
                    "inicio_deslocamento_iso": _iso_data_hora(inicio_deslocamento),
                    "inicio_execucao_iso": _iso_data_hora(inicio_execucao),
                    "fim_execucao_iso": _iso_data_hora(fim_execucao),
                    "retorno_iso": _iso_data_hora(retorno),
                }
                registros.append(registro)
                eventos_lista.append(registro)
            servicos[dia.strftime("%Y-%m-%d")] = registros

    colunas_eletricista = [
        coluna for coluna in (
            _coluna(equipes, "Eletricista 1 (Matrícula e Nome)", "Eletricista 1"),
            _coluna(equipes, "Eletricista 2 (Matrícula e Nome)", "Eletricista 2"),
        ) if coluna
    ]
    coluna_tempo = _coluna(equipes, "Tempo em Atividade")
    coluna_duracao_turno = _coluna(equipes, "Tempo Turno")
    linhas: list[dict] = []
    nomes_cache: dict[str, tuple[str, str]] = {}
    for dia, grupo in equipes.groupby("_dia", sort=True):
        horas_rotalog = (
            max((_tempo_decimal(v) for v in grupo[coluna_tempo]), default=0.0)
            if coluna_tempo else 0.0
        )
        eletricistas = []
        for coluna in colunas_eletricista:
            eletricistas.extend(
                nome_sem_matricula(v) for v in grupo[coluna].dropna()
                if nome_sem_matricula(v)
            )
        eletricistas = list(dict.fromkeys(eletricistas)) or ["Não identificado"]
        boletim_total = [0.0] * len(HEADERS_VIZ)
        ponto_total = [0.0] * len(HEADERS_VIZ)
        detalhes_eletricistas = []
        for eletricista in eletricistas:
            chave_nome = normalizar_texto(eletricista)
            if chave_nome not in nomes_cache:
                nomes_cache[chave_nome] = _resolver_nome(eletricista, relacao, candidatos)
            nome_b, nome_p = nomes_cache[chave_nome]
            registro_b = indice_bol.get((normalizar_texto(nome_b), dia), {})
            registro_p = indice_ponto.get((normalizar_texto(nome_p), dia), {})
            boletim_individual = [
                float(registro_b.get(METRICAS_BOLETIM.get(h, ""), 0.0))
                for h in HEADERS_VIZ
            ]
            ponto_individual = [
                float(registro_p.get(METRICAS_PONTO[h], 0.0)) for h in HEADERS_VIZ
            ]
            boletim_total = [a + b for a, b in zip(boletim_total, boletim_individual)]
            ponto_total = [a + b for a, b in zip(ponto_total, ponto_individual)]
            detalhes_eletricistas.append({
                "nome": nome_b,
                "nome_rotalog": eletricista,
                "nome_ponto": nome_p,
                "boletim": boletim_individual,
                "ponto": ponto_individual,
            })
        diferenca = [round(b - p, 4) for b, p in zip(boletim_total, ponto_total)]
        dia_chave = dia.strftime("%Y-%m-%d")
        turno_texto = ""
        if coluna_turno:
            turno_texto = next((str(v) for v in grupo[coluna_turno] if str(v).strip()), "")
        duracao_turno = ""
        if coluna_duracao_turno:
            duracao_turno = next((str(v) for v in grupo[coluna_duracao_turno] if str(v).strip()), "")
        linhas.append({
            "data": dia_chave,
            "data_exibicao": dia.strftime("%d/%m/%Y"),
            "funcionario": " / ".join(item["nome"] for item in detalhes_eletricistas),
            "eletricistas": detalhes_eletricistas,
            "rotalog": horas_rotalog,
            "turno": _detalhes_turno(turno_texto, dia, duracao_turno),
            "boletim": [round(v, 4) for v in boletim_total],
            "ponto": [round(v, 4) for v in ponto_total],
            "diferenca": diferenca,
            "quantidade_servicos": len(servicos.get(dia_chave, [])),
        })
    return {
        "headers": HEADERS_VIZ,
        "linhas": linhas,
        "servicos": servicos,
        "eventos": eventos_lista,
        "eventos_brutos": {
            "colunas": eventos_brutos_colunas,
            "linhas": eventos_brutos_linhas,
        },
    }
