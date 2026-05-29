# d:\programas\DDS\dds-webtools\boletim_x_ponto\services\leitor_ponto.py
import unicodedata
from io import StringIO, BytesIO
import pandas as pd

def tempo_para_decimal(valor):
    try:
        if pd.isna(valor) or str(valor).strip() == "":
            return 0.0
        if isinstance(valor, (float, int)):
            return round(float(valor), 2)
        partes = str(valor).strip().replace(",", ".").split(":")
        if len(partes) == 2:
            horas = int(partes[0])
            minutos = int(partes[1])
            return round(horas + minutos / 60, 2)
        return round(float(partes[0]), 2)
    except:
        return 0.0


def detectar_delimitador_conteudo(texto):
    if texto.count("\t") > texto.count(";") and texto.count("\t") > texto.count(","):
        return "\t"
    elif texto.count(";") > texto.count(","):
        return ";"
    else:
        return ","


def normalizar_coluna(nome):
    return (
        unicodedata.normalize("NFKD", nome)
        .encode("ASCII", "ignore")
        .decode("utf-8")
        .strip()
        .lower()
    )


def encontrar_coluna(df, opcoes):
    normalizado = {normalizar_coluna(col): col for col in df.columns}
    for opcao in opcoes:
        chave = normalizar_coluna(opcao)
        if chave in normalizado:
            return normalizado[chave]
    return None


def ler_arquivo_compativel_bytes(file_bytes: bytes, filename: str) -> pd.DataFrame | None:
    try:
        if filename.lower().endswith(".csv"):
            try:
                texto = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                texto = file_bytes.decode("latin-1")
            delimitador = detectar_delimitador_conteudo(texto)
            return pd.read_csv(StringIO(texto), sep=delimitador)
        elif filename.lower().endswith((".xls", ".xlsx")):
            try:
                return pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
            except Exception:
                try:
                    texto = file_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    texto = file_bytes.decode("latin-1")
                delimitador = detectar_delimitador_conteudo(texto)
                return pd.read_csv(StringIO(texto), sep=delimitador)
    except Exception as e:
        print(f"[ERRO] Falha ao ler {filename}: {e}")
        return None


def extrair_ponto_dataframe(file_bytes: bytes, filename: str) -> pd.DataFrame:
    df = ler_arquivo_compativel_bytes(file_bytes, filename)
    if df is None or df.empty:
        return pd.DataFrame()

    col_nome = encontrar_coluna(df, ["Nome do funcionário", "funcionário", "nome"])
    col_data = encontrar_coluna(df, ["Dia", "Data"])
    col_cpf = encontrar_coluna(df, ["CPF do funcionário", "cpf"])
    col_pis = encontrar_coluna(df, ["PIS do funcionário", "pis"])

    if not col_nome or not col_data:
        print(f"[IGNORADO] {filename} - Colunas obrigatórias ausentes.")
        return pd.DataFrame()

    registros = []
    for _, linha in df.iterrows():
        try:
            nome = str(linha.get(col_nome)).strip()
            cpf = str(linha.get(col_cpf, "")).strip()
            pis = str(linha.get(col_pis, "")).strip()
            data = linha.get(col_data)

            if isinstance(data, str):
                data = data.strip().split()[0]
                data = pd.to_datetime(data, dayfirst=True, errors="coerce")
            elif isinstance(data, (float, int)):
                data = pd.to_datetime("1899-12-30") + pd.to_timedelta(data, unit="D")

            if pd.isna(data):
                continue

            chave = f"{cpf}__{data.date()}" if cpf else f"{pis}__{data.date()}"

            registro = {
                "Nome": nome.upper(),
                "CPF": cpf,
                "PIS": pis,
                "Data": data.date(),
                "Total Normais": tempo_para_decimal(linha.get("Total Normais", "")),
                "Total Noturno": tempo_para_decimal(linha.get("Total Noturno", "")),
                "Extra 50%D": tempo_para_decimal(linha.get("Extra   50%D", "")),
                "Extra 100%D": tempo_para_decimal(linha.get("Extra   100%D", "")),
                "Extra 50%N": tempo_para_decimal(linha.get("Extra   50%N", "")),
                "Extra 100%N": tempo_para_decimal(linha.get("Extra   100%N", "")),
                "Interjornada": tempo_para_decimal(linha.get("Interjornada", "")),
                "chave_unica": chave,
            }
            registros.append(registro)
        except Exception as e:
            print(f"[ERRO] Falha ao processar linha em {filename}: {e}")

    return pd.DataFrame(registros)
