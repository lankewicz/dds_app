# d:\programas\DDS\dds-webtools\boletim_x_ponto\services\leitor_pdf.py
import re
import fitz  # PyMuPDF
import pandas as pd

def extrair_dados_pdf(file_or_path, set_arquivo=None):
    try:
        if isinstance(file_or_path, bytes):
            doc = fitz.open(stream=file_or_path, filetype="pdf")
        elif hasattr(file_or_path, "read"):
            content = file_or_path.read()
            doc = fitz.open(stream=content, filetype="pdf")
        else:
            doc = fitz.open(file_or_path)
            
        texto_completo = ""
        total_paginas = len(doc)
        for i, pagina in enumerate(doc):
            texto_completo += pagina.get_text("text", sort=True) + "\n"
            if set_arquivo:
                set_arquivo(((i + 1) / total_paginas) * 100)
        doc.close()
    except Exception as e:
        print(f"[ERRO] Falha ao abrir PDF: {e}")
        return None, {}

    cabecalho = {"BOLETIM": None, "Data de Medição": None, "Contrato": None}
    linhas = texto_completo.split("\n")
    for i, linha in enumerate(linhas):
        if i + 1 < len(linhas):
            linha_seguinte = lines_clean = linhas[i + 1].strip()
            if "BOLETIM" in linha.upper() and "MEDIÇÃO" not in linha.upper():
                numeros = re.findall(r"\d{5,}", linha_seguinte)
                if numeros:
                    cabecalho["BOLETIM"] = numeros[-1]
            if "DATA MEDIÇÃO" in linha and "CONTRATO" in linha:
                partes = linha_seguinte.split()
                if len(partes) > 0:
                    cabecalho["Data de Medição"] = partes[0]
                if len(partes) > 1:
                    cabecalho["Contrato"] = partes[-1]
    return texto_completo, cabecalho


def parse_horas_funcionarios(texto):
    dados_extraidos = []
    registro_atual, funcionario_atual = None, None
    regex_ct = re.compile(r"CENTRO DE TRABALHO\s*-\s*(T\d+)-(.+)")

    for linha in texto.split("\n"):
        match = regex_ct.search(linha)
        if match:
            registro_atual = match.group(1).strip()
            funcionario_atual = match.group(2).strip().split("PROD.")[0].strip()
            continue

        if registro_atual and re.match(r"^\d{2}\.\d{2}\.\d{4}", linha.strip()):
            partes = re.split(r"\s{2,}", linha.strip())
            if len(partes) >= 12:
                dados_extraidos.append(
                    {
                        "Registro": registro_atual,
                        "Funcionário": funcionario_atual,
                        "DATA": partes[0],
                        "SERV.": partes[1],
                        "KM": partes[2],
                        "HORA NORMAL": partes[3],
                        "H.E.": partes[4],
                        "H.E.D.": partes[5],
                        "H.E.N.": partes[6],
                        "H.E.N.D.": partes[7],
                        "S.A.": partes[8],
                        "H.N.": partes[9],
                        "DESLOC.": partes[10],
                        "PROD.": partes[11],
                    }
                )

    if not dados_extraidos:
        return pd.DataFrame()

    df = pd.DataFrame(dados_extraidos)
    colunas_numericas = [
        "SERV.",
        "KM",
        "HORA NORMAL",
        "H.E.",
        "H.E.D.",
        "H.E.N.",
        "H.E.N.D.",
        "S.A.",
        "H.N.",
        "DESLOC.",
        "PROD.",
    ]
    for col in colunas_numericas:
        if col in df.columns:
            df[col] = df[col].str.replace(",", ".", regex=False)
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def extrair_cartao_ponto(texto):
    linhas = texto.split("\n")
    registros = []
    funcionario = None

    for linha in linhas:
        if linha.startswith("Nome do funcionário:"):
            funcionario = linha.split(":", 1)[1].strip()
            continue

        if re.match(r"\d{2}/\d{2}/\d{4}", linha):
            partes = linha.strip().split()
            if len(partes) >= 7:
                registros.append(
                    {
                        "Funcionário": funcionario,
                        "DATA": partes[0],
                        "ENTRADA 1": partes[1],
                        "SAÍDA 1": partes[2],
                        "ENTRADA 2": partes[3],
                        "SAÍDA 2": partes[4],
                        "ENTRADA 3": partes[5],
                        "SAÍDA 3": partes[6],
                    }
                )

    return pd.DataFrame(registros)


_MAP_TERMO_POR_VAR = {
    "VAR000": "HORA NORMAL",
    "VAR001": "H.E.",
    "VAR002": "H.E.N.",
    "VAR003": "H.E.D.",
    "VAR004": "H.E.N.D.",
    "VAR005": "S.A.",
    "VAR006": "H.N.",
    "VAR007": "KM",
    "VAR008": "DESLOC.",
}

def _ptbr_float(s: str | None) -> float | None:
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except Exception:
        return None


def parse_valor_us(texto: str) -> float | None:
    m = re.search(r'R\$\s*([0-9\.\,]{3,})', texto)
    return _ptbr_float(m.group(1)) if m else None


def _slice_bloco_var(texto: str) -> str:
    cab = re.search(r'DESCRI[ÇC][ÃA]O\s+US\s+M[EÉ]DIA\s+QTDE\s+TOTAL', texto, flags=re.IGNORECASE)
    if not cab:
        return ""
    return texto[cab.end():]


def parse_var_itens(texto: str) -> pd.DataFrame:
    bloco = _slice_bloco_var(texto)
    if not bloco:
        return pd.DataFrame(columns=['var_code', 'descrição', 'US', 'qtde', 'total'])

    padrao = re.compile(
        r'^(VAR\d{3})\s*-\s*(.*?)\s+([0-9\.,]+)\s+([0-9\.,]+)\s+([0-9\.,]+)$',
        flags=re.MULTILINE
    )
    rows = []
    for m in padrao.finditer(bloco):
        rows.append({
            'var_code': m.group(1).strip(),
            'descrição': m.group(2).strip(),
            'US': _ptbr_float(m.group(3)),
            'qtde': _ptbr_float(m.group(4)),
            'total': _ptbr_float(m.group(5)),
        })
    df = pd.DataFrame(rows, columns=['var_code', 'descrição', 'US', 'qtde', 'total'])
    return df


def montar_dataset_var(cabecalho: dict, texto: str, incluir_termo: bool = True) -> pd.DataFrame:
    df_var = parse_var_itens(texto)
    if df_var.empty:
        cols = ['contrato','boletim','data_medicao','valor_us','var_code','descrição','US','qtde']
        if incluir_termo:
            cols.insert(cols.index('descrição'), 'termo')
        return pd.DataFrame(columns=cols)

    valor_us = parse_valor_us(texto)
    df_var.insert(0, 'contrato', cabecalho.get('Contrato'))
    df_var.insert(1, 'boletim', cabecalho.get('BOLETIM'))
    df_var.insert(2, 'data_medicao', cabecalho.get('Data de Medição'))
    df_var.insert(3, 'valor_us', valor_us)

    if incluir_termo:
        df_var.insert(5, 'termo', df_var['var_code'].map(_MAP_TERMO_POR_VAR))

    base_cols = ['contrato','boletim','data_medicao','valor_us','var_code']
    if incluir_termo:
        out_cols = base_cols + ['termo','descrição','US','qtde']
    else:
        out_cols = base_cols + ['descrição','US','qtde']
    return df_var[out_cols]


def extrair_var_dataset(file_or_path, set_arquivo=None, incluir_termo: bool = True) -> pd.DataFrame:
    texto, cab = extrair_dados_pdf(file_or_path, set_arquivo=set_arquivo)
    if not texto:
        return pd.DataFrame(columns=['contrato','boletim','data_medicao','valor_us',
                                     'var_code'] + (['termo'] if incluir_termo else []) +
                                    ['descrição','US','qtde'])
    return montar_dataset_var(cab, texto, incluir_termo=incluir_termo)
