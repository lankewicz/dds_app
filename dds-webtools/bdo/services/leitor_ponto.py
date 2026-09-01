# d:\programas\DDS\dds-webtools\bdo\services\leitor_ponto.py
import unicodedata
from io import StringIO, BytesIO
import pandas as pd

from bdo.services.leitor_ponto_pdf import extrair_cartao_ponto_pdf_bytes

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
        if filename.lower().endswith(".pdf"):
            return extrair_cartao_ponto_pdf_bytes(file_bytes)
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

    metricas = {
        "Total Normais": encontrar_coluna(df, ["Total Normais", "TOTAL NORMAIS", "Normais"]),
        "Total Noturno": encontrar_coluna(df, ["Total Noturno", "TOTAL NOTURNO", "Noturno"]),
        "Extra 50%D": encontrar_coluna(df, ["Extra   50%D", "Extra 50%D", "EXTRA 50%D", "Extra 50% D"]),
        "Extra 100%D": encontrar_coluna(df, ["Extra   100%D", "Extra 100%D", "EXTRA 100%D", "Extra 100% D"]),
        "Extra 50%N": encontrar_coluna(df, ["Extra   50%N", "Extra 50%N", "EXTRA 50%N", "Extra 50% N"]),
        "Extra 100%N": encontrar_coluna(df, ["Extra   100%N", "Extra 100%N", "EXTRA 100%N", "Extra 100% N"]),
        "Interjornada": encontrar_coluna(df, ["Interjornada", "INTERJORNADA", "Inter jornada"]),
    }

    def texto_limpo(valor):
        if pd.isna(valor):
            return ""
        return str(valor).strip()

    registros = []
    ignorados = 0
    for _, linha in df.iterrows():
        try:
            nome = texto_limpo(linha.get(col_nome))
            cpf = texto_limpo(linha.get(col_cpf, ""))
            pis = texto_limpo(linha.get(col_pis, ""))
            data = linha.get(col_data)

            if isinstance(data, str):
                data = data.strip().split()[0]
                data = pd.to_datetime(data, dayfirst=True, errors="coerce")
            elif isinstance(data, (float, int)):
                data = pd.to_datetime("1899-12-30") + pd.to_timedelta(data, unit="D")

            if not nome or pd.isna(data):
                ignorados += 1
                continue

            chave = f"{cpf}__{data.date()}" if cpf else f"{pis}__{data.date()}"

            registro = {
                "Nome": nome.upper(),
                "CPF": cpf,
                "PIS": pis,
                "Data": data.date(),
                **{
                    nome_metrica: tempo_para_decimal(
                        linha.get(coluna, "") if coluna else ""
                    )
                    for nome_metrica, coluna in metricas.items()
                },
                "chave_unica": chave,
            }
            registros.append(registro)
        except Exception as e:
            ignorados += 1
            print(f"[ERRO] Falha ao processar linha em {filename}: {e}")

    result = pd.DataFrame(registros)
    result.attrs["registros_lidos"] = len(df)
    result.attrs["registros_ignorados"] = ignorados
    return result
