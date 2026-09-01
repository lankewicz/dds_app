"""Extração de cartão-ponto PDF adaptada da versão desktop."""

import re

import fitz
import pandas as pd


def extrair_cartao_ponto_pdf_bytes(file_bytes: bytes):
    caminho_pdf = '<upload>'
    """
    Lê relatórios de Cartão de Ponto em formato PDF (como Control iD) e extrai os registros.
    Retorna um DataFrame pandas com colunas padronizadas para ingestão pelo leitor de ponto.
    """
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        print(f"[ERRO] Falha ao abrir PDF de Ponto '{caminho_pdf}': {e}")
        return pd.DataFrame()

    registros = []
    total_paginas = len(doc)

    func_atual = ""
    cpf_atual = ""
    pis_atual = ""

    for pag_idx, pagina in enumerate(doc):
        if False:
            try:
                set_arquivo(((pag_idx + 1) / total_paginas) * 100)
            except Exception:
                pass

        texto_pag = pagina.get_text("text", sort=True)

        # 1. Metadados de Cabeçalho por página
        m_func = re.search(r"NOME DO FUNCION[ÁA]RIO\s*:\s*([^\n\r]+)", texto_pag, re.IGNORECASE)
        if m_func:
            raw_func = m_func.group(1).strip()
            if "CPF DO FUNCIONÁRIO" in raw_func.upper():
                raw_func = re.split(r"CPF\s+DO", raw_func, flags=re.IGNORECASE)[0].strip()
            func_atual = raw_func

        m_cpf = re.search(r"CPF DO FUNCION[ÁA]RIO\s*:\s*([\d\.\-]+)", texto_pag, re.IGNORECASE)
        if m_cpf:
            cpf_atual = re.sub(r"\D", "", m_cpf.group(1).strip())

        m_pis = re.search(r"PIS DO FUNCION[ÁA]RIO\s*:\s*([\d\.\-]+)", texto_pag, re.IGNORECASE)
        if m_pis:
            pis_atual = re.sub(r"\D", "", m_pis.group(1).strip())

        if not func_atual:
            m_func_alt = re.search(r"FUNCION[ÁA]RIO\s*:\s*([^\n\r]+)", texto_pag, re.IGNORECASE)
            if m_func_alt:
                func_atual = m_func_alt.group(1).strip()

        # 2. Posicionamento de colunas usando a API "words" do PyMuPDF
        words = pagina.get_text("words")  # (x0, y0, x1, y1, text, block_no, line_no, word_no)
        if not words:
            continue

        cols_x = {
            "normais": None,
            "noturno": None,
            "falta_atraso": None,
            "extra_50d": None,
            "extra_100d": None,
            "extra_50n": None,
            "extra_100n": None,
            "interjornada": None,
        }

        # Procura marcadores de cabeçalho registrando a coordenada X inicial (w[0])
        for i, w in enumerate(words):
            txt_upper = w[4].upper()
            x_start = w[0]

            if txt_upper == "TOTAL" and i + 1 < len(words) and words[i + 1][4].upper() == "NORMAIS":
                cols_x["normais"] = x_start
            elif txt_upper == "NORMAIS" and cols_x["normais"] is None:
                cols_x["normais"] = x_start
            elif txt_upper == "TOTAL" and i + 1 < len(words) and words[i + 1][4].upper() == "NOTURNO":
                cols_x["noturno"] = x_start
            elif txt_upper == "NOTURNO" and cols_x["noturno"] is None:
                cols_x["noturno"] = x_start
            elif "50%D" in txt_upper:
                # Usa X inicial da palavra "EXTRA" anterior se presente
                x_extra = words[i - 1][0] if i > 0 and "EXTRA" in words[i - 1][4].upper() else x_start
                cols_x["extra_50d"] = x_extra
            elif "100%D" in txt_upper:
                x_extra = words[i - 1][0] if i > 0 and "EXTRA" in words[i - 1][4].upper() else x_start
                cols_x["extra_100d"] = x_extra
            elif "50%N" in txt_upper:
                x_extra = words[i - 1][0] if i > 0 and "EXTRA" in words[i - 1][4].upper() else x_start
                cols_x["extra_50n"] = x_extra
            elif "100%N" in txt_upper:
                x_extra = words[i - 1][0] if i > 0 and "EXTRA" in words[i - 1][4].upper() else x_start
                cols_x["extra_100n"] = x_extra
            elif txt_upper == "FALTA" and cols_x["falta_atraso"] is None:
                cols_x["falta_atraso"] = x_start
            elif "INTERJORNADA" in txt_upper:
                cols_x["interjornada"] = x_start

        # Fallbacks dinâmicos por largura de página se não detectado no cabeçalho
        pag_w = pagina.rect.width if pagina.rect.width > 0 else 842.0
        scale = pag_w / 842.0

        defaults_x = {
            "normais": 520.0 * scale,
            "noturno": 560.0 * scale,
            "falta_atraso": 640.0 * scale,
            "extra_50d": 695.0 * scale,
            "extra_100d": 745.0 * scale,
            "extra_50n": 770.0 * scale,
            "extra_100n": 790.0 * scale,
            "interjornada": 815.0 * scale,
        }

        for k, v in defaults_x.items():
            if cols_x[k] is None:
                cols_x[k] = v

        x_min_totais = (cols_x["normais"] or (480.0 * scale)) - 30.0

        # Agrupa palavras em linhas por coordenada y0
        words_ordenados = sorted(words, key=lambda item: (round(item[1] / 3.0), item[0]))
        linhas_words = []
        linha_atual = []
        y_ref = None
        for w in words_ordenados:
            if y_ref is None or abs(w[1] - y_ref) <= 3.5:
                linha_atual.append(w)
                y_ref = w[1]
            else:
                linhas_words.append(linha_atual)
                linha_atual = [w]
                y_ref = w[1]
        if linha_atual:
            linhas_words.append(linha_atual)

        for lw in linhas_words:
            if not lw:
                continue

            # Apenas linhas que começam com a data (x0 próximo da margem esquerda)
            primeira_palavra = lw[0]
            if primeira_palavra[0] > 80.0 * scale:
                continue

            m_data = re.match(r"^(\d{2}/\d{2}/\d{4})", primeira_palavra[4])
            if not m_data:
                continue

            data_str = m_data.group(1)

            reg = {
                "Nome do funcionário": func_atual,
                "CPF do funcionário": cpf_atual,
                "PIS do funcionário": pis_atual,
                "Dia": data_str,
                "Total Normais": "",
                "Total Noturno": "",
                "Extra 50%D": "",
                "Extra 100%D": "",
                "Extra 50%N": "",
                "Extra 100%N": "",
                "Interjornada": "",
            }

            palavras_totais = [
                w for w in lw 
                if w[0] >= x_min_totais and re.match(r"^\d{1,3}:\d{2}$", w[4])
            ]

            for w in palavras_totais:
                x_start = w[0]
                val = w[4]

                melhor_col, menor_dist = None, 999999.0
                for col_name, col_x in cols_x.items():
                    if col_x is not None:
                        dist = abs(x_start - col_x)
                        if dist < menor_dist:
                            menor_dist = dist
                            melhor_col = col_name

                if melhor_col and menor_dist <= 35.0 * scale:
                    if melhor_col == "normais":
                        reg["Total Normais"] = val
                    elif melhor_col == "noturno":
                        reg["Total Noturno"] = val
                    elif melhor_col == "extra_50d":
                        reg["Extra 50%D"] = val
                    elif melhor_col == "extra_100d":
                        reg["Extra 100%D"] = val
                    elif melhor_col == "extra_50n":
                        reg["Extra 50%N"] = val
                    elif melhor_col == "extra_100n":
                        reg["Extra 100%N"] = val
                    elif melhor_col == "interjornada":
                        reg["Interjornada"] = val

            registros.append(reg)

    doc.close()
    return pd.DataFrame(registros)
