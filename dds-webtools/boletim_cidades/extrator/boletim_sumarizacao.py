from pathlib import Path
import re
import unicodedata
import pandas as pd

try:
    import pdfplumber
except Exception:
    pdfplumber = None

# -----------------------------
# Regex helpers (mais tolerantes)
# -----------------------------
CEP_RE = re.compile(r"^\d{5}-\d{3}$")
UF_RE = re.compile(r"^(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)$")
DFISCAL_CODE_RE = re.compile(r"^\d{7}$")
PEDIDO_RE = re.compile(r"^\d{9,12}$")  # alguns têm 9–12 dígitos
NUM_PTBR_1TO3DEC_RE = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{1,3}$")
MONEY_PTBR_RE = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{2}$")
RS_TOKEN_RE = re.compile(r"^R\$\s*$|^R\$$")  # aceita "R$" e "R$ " (com espaço fino)
CURRENCY_RE = re.compile(r"^(R\$|BRL)$", re.I)
RE_10D          = re.compile(r"^\d{10}$")
RE_CONTRATO_46  = re.compile(r"^46000\d{5}$")  # exatamente 10 dígitos, prefixo 46000
RE_SOMENTE_NUM  = re.compile(r"^\d+$")

COMBINED_UF_DFISCAL_RE = re.compile(r"^([A-Z]{2})(\d{7})$")

# -----------------------------
# Normalização leve para OCR
# -----------------------------
def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def _norm(s: str) -> str:
    s2 = _strip_accents(s).upper()
    s2 = re.sub(r"\s+", " ", s2).strip()
    return s2

# -----------------------------
# Agrupar tokens por linha (melhor tolerância vertical)
# -----------------------------
def _tokens_by_line(words, y_tolerance=2.0):
    """
    words: resultado de page.extract_words(x_tolerance=?, y_tolerance=?)
    Devolve lista de linhas, cada linha = lista de strings (tokens) na ordem de x.
    """
    # buckets por faixa [y0, y1]
    rows = []
    for w in words:
        y = w["top"]
        placed = False
        for row in rows:
            # row bbox: (ymin, ymax, tokens)
            ymin, ymax, toks = row
            if ymin - y_tolerance <= y <= ymax + y_tolerance:
                # expande faixa e adiciona
                row[0] = min(ymin, y)
                row[1] = max(ymax, y)
                toks.append(w)
                placed = True
                break
        if not placed:
            rows.append([y, y, [w]])

    # ordenar por y e por x
    rows.sort(key=lambda r: r[0])
    for _, __, toks in rows:
        toks.sort(key=lambda w: w["x0"])
        # juntar hífen de quebra de linha (palavra-  seguido de proxima palavra colada)
        out = []
        prev = None
        for t in toks:
            text = t["text"]
            if prev and out and out[-1].endswith("-") and t["x0"] - prev["x1"] < 2:
                out[-1] = out[-1][:-1] + text  # "palavra-" + "seguinte" -> "palavraseguinte"
            else:
                out.append(text)
            prev = t
        yield out

# -----------------------------
# Cabeçalho robusto por proximidade + fallback regex
# -----------------------------
def _join_digit_runs(tokens):
    """
    Junta runs de dígitos quebrados por espaços em um único número.
    Ex.: ["46000","17057"] -> ["4600017057"]. Mantém tokens não numéricos.
    """
    out = []
    buf = ""
    for t in tokens:
        # usa o regex declarado no topo (RE_SOMENTE_NUM)
        if RE_SOMENTE_NUM.match(t):
            buf += t
        else:
            if buf:
                out.append(buf)
                buf = ""
            out.append(t)
    if buf:
        out.append(buf)
    return out

def _parse_header(page):
    """
    Extrai Boletim e Contrato com regras mais tolerantes:
      - BOLETIM: primeiro número de 10 dígitos que surge na mesma linha de
        'BOLETIM' ou nas 3 linhas seguintes; ignora padrão de contrato
        ^46000\d{5}$.
      - CONTRATO: primeiro número de 10 dígitos que case ^46000\d{5}$ na linha
        de 'CONTRATO' ou até 2 linhas abaixo.
    """
    words = page.extract_words(x_tolerance=3, y_tolerance=3) or []
    linhas = list(_tokens_by_line(words))
    linhas_norm = [[_norm(tok) for tok in linha] for linha in linhas]

    boletim = None
    contrato = None

    # --- BOLETIM ---
    for i, toks_norm in enumerate(linhas_norm):

        if any(tok == "BOLETIM" for tok in toks_norm):
            candidatos = []
            candidatos.extend(linhas[i])
            candidatos.extend(_join_digit_runs(linhas[i]))
            for j in (i + 1, i + 2, i + 3):
                if 0 <= j < len(linhas):
                    candidatos.extend(linhas[j])
                    candidatos.extend(_join_digit_runs(linhas[j]))

            for raw in candidatos:
                if RE_10D.match(raw) and not RE_CONTRATO_46.match(raw):
                    boletim = raw
                    break
            if boletim:
                break

    # --- CONTRATO ---
    for i, toks_norm in enumerate(linhas_norm):

        if any(tok.startswith("CONTRATO") for tok in toks_norm):

            candidatos = []
            for j in (i, i + 1, i + 2):
                if 0 <= j < len(linhas):
                    candidatos.extend(linhas[j])
                    candidatos.extend(_join_digit_runs(linhas[j]))

            cand_46 = [c for c in candidatos if RE_CONTRATO_46.match(c)]
            if cand_46:
                contrato = cand_46[0]
                break


    if boletim and contrato and boletim == contrato:
        boletim = None

    return {"Boletim": boletim, "Contrato": contrato}
# -----------------------------
# Parser da linha de totalização (mais flexível)
# -----------------------------
def _try_parse_sum_line(tokens):
    """
    Espera um padrão do tipo:
    MUNICIPIO ... CEP ... UF DFISCAL ... PEDIDO ... US ... [R$] VALOR_US ... [R$] VALOR_TOTAL
    - "US" pode estar ausente (alguns layouts).
    - "R$" pode vir colado/isolado/omitido (quando já há símbolo no número).
    Retorna: {"Municipio", "d_fiscal", "Pedido", "US", "Valor_US", "Valor"} (strings pt-BR para números).
    """
    # normalização leve de tokens de moeda
    toks = []
    for t in tokens:
        tt = t.replace("\u00a0", " ").strip()  # NBSP
        toks.append(tt)

    # localizar CEP
    for i, tok in enumerate(toks):
        if CEP_RE.match(tok):
            municipio = " ".join(toks[:i]).strip()
            if not municipio or len(municipio) > 80:
                return None

            # UF + DFISCAL (com tolerância para tokens mesclados ou separados)
            d_fiscal = None
            j = -1

            # Caso A: Token combinado (ex: "PR4100707" or "PR 4100707" com espaço interno no token)
            if i + 1 < len(toks):
                tok1 = toks[i + 1]
                m_comb = COMBINED_UF_DFISCAL_RE.match(tok1) or COMBINED_UF_DFISCAL_RE.match(tok1.replace(" ", ""))
                if m_comb and UF_RE.match(m_comb.group(1)):
                    d_fiscal = f"{m_comb.group(1)} {m_comb.group(2)}"
                    j = i + 2

            # Caso B: Tokens separados (ex: "PR", "4101002")
            if d_fiscal is None and i + 2 < len(toks):
                tok1 = toks[i + 1]
                tok2 = toks[i + 2]
                if UF_RE.match(tok1) and DFISCAL_CODE_RE.match(tok2):
                    d_fiscal = f"{tok1} {tok2}"
                    j = i + 3

            if d_fiscal is None:
                return None

            # Pedido
            if j >= len(toks) or not PEDIDO_RE.match(toks[j]):
                return None
            pedido = toks[j]
            j += 1

            # US (opcional) — quantidade com 1–3 decimais pt-BR
            US = None
            if j < len(toks) and NUM_PTBR_1TO3DEC_RE.match(toks[j]):
                US = toks[j]
                j += 1

            # Valor_US (opcional se houver US)
            Valor_US = None
            # aceitar presença opcional de "R$"
            if j < len(toks) and RS_TOKEN_RE.match(toks[j]):
                j += 1
            if j < len(toks) and MONEY_PTBR_RE.match(toks[j]):
                Valor_US = toks[j]
                j += 1

            # Valor total (obrigatório)
            if j < len(toks) and RS_TOKEN_RE.match(toks[j]):
                j += 1
            if j < len(toks) and MONEY_PTBR_RE.match(toks[j]):
                Valor = toks[j]
            else:
                # algumas vezes só há um valor (sem valor_us). Nesses casos, trate esse único como total
                if Valor_US:
                    Valor = Valor_US
                    Valor_US = None
                else:
                    return None

            out = {
                "Municipio": municipio,
                "d_fiscal": d_fiscal,
                "Pedido": pedido,
                "Valor": Valor
            }
            if US:
                out["US"] = US
            if Valor_US:
                out["Valor_US"] = Valor_US
            return out
    return None

# -----------------------------
# Utilitários numéricos (conversão pt-BR -> float)
# -----------------------------
def _ptbr_to_float(s: str | None) -> float | None:
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    # remove pontos como milhar e troca vírgula por ponto
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

# -----------------------------
# Pipeline principal (mais robusto)
# -----------------------------
def processar_pasta_boletins(
    pasta_boletins: str | Path,
    recursive: bool = True,
    on_progress=None,
    iss_csv_path: str | Path | None = None
) -> pd.DataFrame:
    """
    Retorna DataFrame com colunas:
    Copiado(bool), Boletim, Fornecedor, Contrato, Municipio, d_fiscal, Pedido,
    US(str), Valor_US(str), Valor(str),
    US_num(float), Valor_US_num(float), Valor_num(float),
    ALIQ_ISS, VALOR_INSS, CodigoMunicipio, Arquivo, ArquivoAbs
    """
    if pdfplumber is None:
        raise RuntimeError("pdfplumber não está instalado. pip install pdfplumber")

    pasta = Path(pasta_boletins)
    pdfs = sorted(pasta.rglob("*.pdf") if recursive else pasta.glob("*.pdf"))

    # Carrega alíquotas com tolerância a ; e ,
    aliq = None
    if iss_csv_path:
        iss_path = Path(iss_csv_path)
        if iss_path.exists():
            try:
                aliq = pd.read_csv(iss_path, dtype={"CodigoMunicipio": "string"})
            except Exception:
                aliq = pd.read_csv(iss_path, sep=";", decimal=",", dtype={"CodigoMunicipio": "string"})

    registros = []
    for idx, pdf in enumerate(pdfs, start=1):
        if on_progress:
            on_progress(f"({idx}/{len(pdfs)}) {pdf.name}", "batch_step", {"arquivo": str(pdf)})
        try:
            with pdfplumber.open(str(pdf)) as doc:
                if not doc.pages:
                    continue
                header = _parse_header(doc.pages[0])

                rows = []
                for pnum, page in enumerate(doc.pages, start=1):
                    words = page.extract_words(x_tolerance=2, y_tolerance=2) or []
                    for tokens in _tokens_by_line(words):
                        rec = _try_parse_sum_line(tokens)
                        if rec:
                            rows.append(rec)
                            if on_progress:
                                on_progress(
                                    f"[{pdf.name} p{pnum}] {rec.get('Municipio','?')} | {rec.get('Pedido','?')} | {rec.get('Valor','?')}",
                                    "line_match",
                                    {"registro": rec, "pagina": pnum}
                                )
                if not rows:
                    continue

                df = pd.DataFrame(rows)
                # add header cols
                df.insert(0, "Boletim", header.get("Boletim"))
                df.insert(1, "Contrato", header.get("Contrato"))

                # CodigoMunicipio para merge externo
                df["CodigoMunicipio"] = df["d_fiscal"].str.extract(r"(\d{7})")

                # Merge de alíquotas (se houver)
                if aliq is not None and "CodigoMunicipio" in aliq.columns:
                    use_cols = [c for c in aliq.columns if c in ("CodigoMunicipio", "AliquotaISS", "VALOR_INSS")]
                    df = df.merge(aliq[use_cols].drop_duplicates("CodigoMunicipio"), on="CodigoMunicipio", how="left")
                    df.rename(columns={"AliquotaISS": "ALIQ_ISS"}, inplace=True)
                else:
                    df["ALIQ_ISS"] = None
                    df["VALOR_INSS"] = None

                # Conversões numéricas paralelas (mantém string original)
                df["US_num"] = df.get("US").map(_ptbr_to_float) if "US" in df.columns else None
                df["Valor_US_num"] = df.get("Valor_US").map(_ptbr_to_float) if "Valor_US" in df.columns else None
                df["Valor_num"] = df.get("Valor").map(_ptbr_to_float) if "Valor" in df.columns else None

                # Metadados do arquivo
                df["Copiado"] = False
                try:
                    df["Arquivo"] = str(pdf.relative_to(pasta))
                except Exception:
                    df["Arquivo"] = str(pdf)
                df["ArquivoAbs"] = str(pdf.resolve())

                registros.append(df)

        except Exception as e:
            if on_progress:
                on_progress(f"[ERRO] {pdf.name}: {e}", "error", {"erro": str(e)})
            # continue o processamento dos demais arquivos

    if not registros:
        # Garante esquema vazio consistente (apenas colunas desejadas)
        cols = [
            "Copiado", "Boletim", "Contrato", "Municipio", "d_fiscal", "Pedido",
            "Valor_num", "ALIQ_ISS", "CodigoMunicipio", "Arquivo", "ArquivoAbs", "ID"
        ]
        return pd.DataFrame(columns=cols)

    out = pd.concat(registros, ignore_index=True)

    # Ordenação e tipos finais úteis
    out["ID"] = range(len(out))
    col_order = [
        "Copiado", "Boletim", "Contrato", "Municipio", "d_fiscal", "Pedido",
        "Valor_num", "ALIQ_ISS", "CodigoMunicipio", "Arquivo", "ArquivoAbs", "ID"
    ]

    for c in col_order:
        if c not in out.columns:
            out[c] = None
    out = out[col_order]

    # Tipos (onde fizer sentido)
    out["Copiado"] = out["Copiado"].astype(bool)

    return out


def processar_lista_boletins(
    arquivos,
    on_progress=None,
    iss_csv_path: str | Path | None = None
) -> pd.DataFrame:
    """
    Processa uma lista de arquivos do tipo uploaded_file ou file-like objects.
    """
    # Carrega alíquotas com tolerância a ; e ,
    aliq = None
    if iss_csv_path:
        iss_path = Path(iss_csv_path)
        if iss_path.exists():
            try:
                aliq = pd.read_csv(iss_path, dtype={"CodigoMunicipio": "string"})
            except Exception:
                aliq = pd.read_csv(iss_path, sep=";", decimal=",", dtype={"CodigoMunicipio": "string"})

    registros = []
    for idx, arq in enumerate(arquivos, start=1):
        nome_arquivo = getattr(arq, "name", f"arquivo_{idx}.pdf")
        if on_progress:
            on_progress(f"({idx}/{len(arquivos)}) {nome_arquivo}", "batch_step", {"arquivo": nome_arquivo})
        try:
            with pdfplumber.open(arq) as doc:
                if not doc.pages:
                    continue
                header = _parse_header(doc.pages[0])

                rows = []
                for pnum, page in enumerate(doc.pages, start=1):
                    words = page.extract_words(x_tolerance=2, y_tolerance=2) or []
                    for tokens in _tokens_by_line(words):
                        rec = _try_parse_sum_line(tokens)
                        if rec:
                            rows.append(rec)
                            if on_progress:
                                on_progress(
                                    f"[{nome_arquivo} p{pnum}] {rec.get('Municipio','?')} | {rec.get('Pedido','?')} | {rec.get('Valor','?')}",
                                    "line_match",
                                    {"registro": rec, "pagina": pnum}
                                )
                if not rows:
                    continue

                df = pd.DataFrame(rows)
                # add header cols
                df.insert(0, "Boletim", header.get("Boletim"))
                df.insert(1, "Contrato", header.get("Contrato"))
                df["CodigoMunicipio"] = df["d_fiscal"].str.extract(r"(\d{7})")

                # Merge de alíquotas (se houver)
                if aliq is not None and "CodigoMunicipio" in aliq.columns:
                    use_cols = [c for c in aliq.columns if c in ("CodigoMunicipio", "AliquotaISS", "VALOR_INSS")]
                    df = df.merge(aliq[use_cols].drop_duplicates("CodigoMunicipio"), on="CodigoMunicipio", how="left")
                    df.rename(columns={"AliquotaISS": "ALIQ_ISS"}, inplace=True)
                else:
                    df["ALIQ_ISS"] = None
                    df["VALOR_INSS"] = None

                # Conversões numéricas paralelas
                df["US_num"] = df.get("US").map(_ptbr_to_float) if "US" in df.columns else None
                df["Valor_US_num"] = df.get("Valor_US").map(_ptbr_to_float) if "Valor_US" in df.columns else None
                df["Valor_num"] = df.get("Valor").map(_ptbr_to_float) if "Valor" in df.columns else None

                # Metadados do arquivo
                df["Copiado"] = False
                df["Arquivo"] = nome_arquivo
                df["ArquivoAbs"] = nome_arquivo

                registros.append(df)

        except Exception as e:
            if on_progress:
                on_progress(f"[ERRO] {nome_arquivo}: {e}", "error", {"erro": str(e)})

    if not registros:
        # Garante esquema vazio consistente (apenas colunas desejadas)
        cols = [
            "Copiado", "Boletim", "Contrato", "Municipio", "d_fiscal", "Pedido",
            "Valor_num", "ALIQ_ISS", "CodigoMunicipio", "Arquivo", "ArquivoAbs", "ID"
        ]
        return pd.DataFrame(columns=cols)

    out = pd.concat(registros, ignore_index=True)

    # Ordenação e tipos finais úteis
    out["ID"] = range(len(out))
    col_order = [
        "Copiado", "Boletim", "Contrato", "Municipio", "d_fiscal", "Pedido",
        "Valor_num", "ALIQ_ISS", "CodigoMunicipio", "Arquivo", "ArquivoAbs", "ID"
    ]

    for c in col_order:
        if c not in out.columns:
            out[c] = None
    out = out[col_order]

    # Tipos (onde fizer sentido)
    out["Copiado"] = out["Copiado"].astype(bool)

    return out
