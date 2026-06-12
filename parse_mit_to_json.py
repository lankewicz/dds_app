import re
import os
import json
from pypdf import PdfReader

MANUAL_PATH = r"D:\programas\GerenciadorTarefas\MIT 163108_Atividades de Construção.pdf"
OUTPUT_PATH = r"d:\programas\DDS\parsed_mit.json"

def limpar_linhas(texto):
    if not texto:
        return []
    linhas = texto.split("\n")
    linhas_limpas = []
    for l in linhas:
        l_strip = l.strip()
        if not l_strip:
            continue
        if "MANUAL DE INSTRUÇÕES" in l_strip or "Título: FISCALIZAÇÃO" in l_strip or "Módulo: ATIVIDADES" in l_strip or "Órgão Emissor:" in l_strip:
            continue
        if re.match(r'^\d+\s+\d+\s+\d+$', l_strip):
            continue
        linhas_limpas.append(l_strip)
    return linhas_limpas

def parse_mit():
    if not os.path.exists(MANUAL_PATH):
        print(f"Erro: Arquivo do manual não encontrado em: {MANUAL_PATH}")
        return
        
    print("Lendo o manual MIT 163108...")
    reader = PdfReader(MANUAL_PATH)
    atividades = []
    
    codigo_ativo = None
    desc_acumulada = []
    
    re_inicio_item = re.compile(r'^\s*(\d{3,4})\s+([A-ZÇÃÉÍÓÚÂÊÔ].*)$')
    re_valores_fim = re.compile(r'\s+(\d+[\d,.]*)\s+(\d+[\d,.]*|-)\s*$')

    # Ler a partir da página 5 (índice 4) até a página 42 (índice 41)
    for p_idx in range(4, 42):
        text = reader.pages[p_idx].extract_text()
        linhas = limpar_linhas(text)
        
        for linha in linhas:
            match_valores = re_valores_fim.search(linha)
            match_inicio = re_inicio_item.match(linha)
            
            if match_inicio:
                if codigo_ativo is not None:
                    desc_completa = " ".join(desc_acumulada)
                    atividades.append((codigo_ativo, desc_completa, 0.0, 0.0))
                
                codigo_ativo = int(match_inicio.group(1))
                corpo_linha = match_inicio.group(2)
                
                if match_valores:
                    corpo_linha = re_valores_fim.sub("", corpo_linha)
                    desc_acumulada = [corpo_linha.strip()]
                    
                    us_m = float(match_valores.group(1).replace(",", "."))
                    us_d_str = match_valores.group(2).replace(",", ".")
                    us_d = 0.0 if us_d_str == "-" else float(us_d_str)
                    
                    desc_completa = " ".join(desc_acumulada)
                    atividades.append((codigo_ativo, desc_completa, us_m, us_d))
                    
                    codigo_ativo = None
                    desc_acumulada = []
                else:
                    desc_acumulada = [corpo_linha]
            
            elif codigo_ativo is not None:
                if match_valores:
                    linha_limpa_valores = re_valores_fim.sub("", linha).strip()
                    if linha_limpa_valores:
                        desc_acumulada.append(linha_limpa_valores)
                        
                    us_m = float(match_valores.group(1).replace(",", "."))
                    us_d_str = match_valores.group(2).replace(",", ".")
                    us_d = 0.0 if us_d_str == "-" else float(us_d_str)
                    
                    desc_completa = " ".join(desc_acumulada)
                    desc_completa = re.sub(r'\s*-\s*$', '', desc_completa)
                    
                    atividades.append((codigo_ativo, desc_completa, us_m, us_d))
                    
                    codigo_ativo = None
                    desc_acumulada = []
                else:
                    desc_acumulada.append(linha)
                    
    atividades_unicas = {}
    for item in atividades:
        if item[0] < 50 or item[0] > 2000:
            continue
        atividades_unicas[item[0]] = item

    output_list = []
    for cod, desc, us_m, us_d in atividades_unicas.values():
        desc_norm = desc.replace("ARE NITO", "ARENITO")
        desc_norm = desc_norm.replace("PA RA", "PARA")
        desc_norm = desc_norm.replace("POST E", "POSTE")
        desc_norm = desc_norm.replace("60 0", "600")
        desc_norm = desc_norm.replace("ANCO RAGEM", "ANCORAGEM")
        desc_norm = re.sub(r'\s+', ' ', desc_norm).strip()
        
        match_unidade = re.search(r',\s*(POR\s+[A-ZÇÃÉÍÓÚÂÊÔ]+)\b', desc_norm)
        
        if match_unidade:
            forma_pagamento = match_unidade.group(1).strip()
            tarefa = desc_norm[:match_unidade.start()].strip()
            descricao_detalhada = desc_norm[match_unidade.end():].strip()
        else:
            forma_pagamento = "UNIDADE"
            tarefa = desc_norm
            descricao_detalhada = ""
            
        output_list.append({
            "codigo": int(cod),
            "tarefa": tarefa,
            "forma_pagamento": forma_pagamento,
            "descricao_detalhada": descricao_detalhada if descricao_detalhada else tarefa,
            "us_montagem": float(us_m),
            "us_desmontagem": float(us_d),
            "raw_text": desc_norm
        })
        
    output_list = sorted(output_list, key=lambda x: x["codigo"])
    
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output_list, f, ensure_ascii=False, indent=2)
        
    print(f"Sucesso! Gerou {len(output_list)} itens em {OUTPUT_PATH}")

if __name__ == "__main__":
    parse_mit()
