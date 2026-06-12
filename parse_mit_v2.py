import re
import os
import json
from pypdf import PdfReader

MANUAL_PATH = r"D:\programas\GerenciadorTarefas\MIT 163108_Atividades de Construção.pdf"
OUTPUT_PATH = r"d:\programas\DDS\parsed_mit_v2.json"

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

# Mapeamento de categorias conhecidas para corrigir encodings
MAP_CATEGORIAS = {
    "4.1": "4.1 - LEVANTAMENTO CADASTRAL",
    "4.2": "4.2 - LEVANTAMENTO TOPOGRÁFICO",
    "4.3": "4.3 - PROJETOS E ORÇAMENTOS",
    "4.4": "4.4 - CAVAS E VALETAS",
    "4.5": "4.5 - POSTES",
    "4.6": "4.6 - ESTRUTURAS PRIMÁRIAS",
    "4.7": "4.7 - ESTRUTURAS SECUNDÁRIAS",
    "4.8": "4.8 - ESTAIS E ANCORAGENS",
    "4.9": "4.9 - LANÇAMENTO E TRACIONAMENTO DE CABOS DA PRIMÁRIA",
    "4.10": "4.10 - LANÇAMENTO E TRACIONAMENTO DE CABOS DA SECUNDÁRIA",
    "4.11": "4.11 - LIGAÇÕES, AMARRAÇÕES E EMENDAS",
    "4.12": "4.12 - ATERRAMENTOS E SECCIONAMENTOS",
    "4.13": "4.13 - EQUIPAMENTOS",
    "4.14": "4.14 - ILUMINAÇÃO PÚBLICA",
    "4.15": "4.15 - LIGAÇÃO DE UNIDADE CONSUMIDORA",
    "4.16": "4.16 - TRANSPORTES E DESLOCAMENTOS",
    "4.17": "4.17 - PODA DE ÁRVORES E ROÇADA EM FAIXA DE SERVIDÃO",
    "4.18": "4.18 - NUMERAÇÃO E IDENTIFICAÇÃO DA REDE",
    "4.19": "4.19 - OPERAÇÃO E DESLIGAMENTOS DA REDE",
    "4.20": "4.20 - ATIVIDADES COM REDE ENERGIZADA (LINHA VIVA)",
    "4.21": "4.21 - ATIVIDADES DE REDE PRIMÁRIA COMPACTA (RDC)",
    "4.22": "4.22 - ATIVIDADES DE REDE SECUNDÁRIA ISOLADA (RSI)",
    "4.23": "4.23 - ATIVIDADES DIVERSAS",
    "4.24": "4.24 - ATIVIDADES PARA SERVIÇOS EMERGENCIAIS",
    "4.25": "4.25 - ATIVIDADES COM O BIG JUMPER",
    "4.26": "4.26 - ATIVIDADES DE SISTEMAS FOTOVOLTAICOS - SIGFI",
    "4.27": "4.27 - ATIVIDADES DE REDE SUBTERRÂNEA CABO DIRETAMENTE ENTERRADO"
}

def parse_mit():
    if not os.path.exists(MANUAL_PATH):
        print(f"Erro: Arquivo do manual não encontrado em: {MANUAL_PATH}")
        return
        
    print("Lendo o manual MIT 163108...")
    reader = PdfReader(MANUAL_PATH)
    atividades = []
    
    codigo_ativo = None
    desc_acumulada = []
    categoria_ativa = "Não Categorizado"
    
    re_inicio_item = re.compile(r'^\s*(\d{3,4})\s+([A-ZÇÃÉÍÓÚÂÊÔ].*)$')
    re_valores_fim = re.compile(r'\s+(\d+[\d,.]*)\s+(\d+[\d,.]*|-)\s*$')
    re_categoria = re.compile(r'^\s*(4\.\d+)\s*[\-\uFFFD\s]+\s*(.+)$')

    # Ler a partir da página 5 (índice 4) até a página 42 (índice 41)
    for p_idx in range(4, 42):
        text = reader.pages[p_idx].extract_text()
        linhas = limpar_linhas(text)
        
        for linha in linhas:
            # 1. Verificar se a linha define uma nova categoria
            match_cat = re_categoria.match(linha)
            if match_cat:
                prefix = match_cat.group(1)
                categoria_ativa = MAP_CATEGORIAS.get(prefix, f"{prefix} - {match_cat.group(2).strip()}")
                print(f"DEBUG: Mudou para categoria: {categoria_ativa}")
                continue
                
            match_valores = re_valores_fim.search(linha)
            match_inicio = re_inicio_item.match(linha)
            
            if match_inicio:
                if codigo_ativo is not None:
                    desc_completa = " ".join(desc_acumulada)
                    atividades.append((codigo_ativo, desc_completa, 0.0, 0.0, categoria_ativa))
                
                codigo_ativo = int(match_inicio.group(1))
                corpo_linha = match_inicio.group(2)
                
                if match_valores:
                    corpo_linha = re_valores_fim.sub("", corpo_linha)
                    desc_acumulada = [corpo_linha.strip()]
                    
                    us_m = float(match_valores.group(1).replace(",", "."))
                    us_d_str = match_valores.group(2).replace(",", ".")
                    us_d = 0.0 if us_d_str == "-" else float(us_d_str)
                    
                    desc_completa = " ".join(desc_acumulada)
                    atividades.append((codigo_ativo, desc_completa, us_m, us_d, categoria_ativa))
                    
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
                    
                    atividades.append((codigo_ativo, desc_completa, us_m, us_d, categoria_ativa))
                    
                    codigo_ativo = None
                    desc_acumulada = []
                else:
                    desc_acumulada.append(linha)
                    
    atividades_unicas = {}
    for item in atividades:
        if item[0] < 50 or item[0] > 2000:
            continue
        atividades_unicas[item[0]] = item

    # Dicionário de substituições para corrigir espaçamentos gerados pelo parser de PDF
    REPLACEMENTS = {
        "ARE NITO": "ARENITO",
        "PA RA": "PARA",
        "POST E": "POSTE",
        "60 0": "600",
        "ANCO RAGEM": "ANCORAGEM",
        "DIRET AMENTE": "DIRETAMENTE",
        "PO R": "POR",
        "VA LA": "VALA",
        "VALA S": "VALAS",
        "LIG AÇÕES": "LIGAÇÕES",
        "LIG AÇÃO": "LIGAÇÃO",
        "MONT AGEM": "MONTAGEM",
        "D E": "DE",
        "FOTOV OLTAICO": "FOTOVOLTAICO",
        "ESTRUT URA": "ESTRUTURA",
        "FREQ UENCIA": "FREQUENCIA",
        "CONT ROLADOR": "CONTROLADOR",
        "INTERLIGA ÇÃO": "INTERLIGAÇÃO",
        "INTERLIGAÇÕE S": "INTERLIGAÇÕES",
        "MEDI ÇÃO": "MEDIÇÃO",
        "M ÓDULOS": "MÓDULOS",
        "EQUIP AMENTO S": "EQUIPAMENTOS",
        "EQUIP AMENTOS": "EQUIPAMENTOS",
        "EMERGEN CIAIS": "EMERGENCIAIS",
        "DOMIN GOS": "DOMINGOS",
        "FERIADO S": "FERIADOS",
        "ESTAD O": "ESTADO",
        "QU ANTIDADE": "QUANTIDADE",
        "TRABALH ADAS": "TRABALHADAS",
        "CONTEMPLAD A": "CONTEMPLADA",
        "EL EMENTO": "ELEMENTO",
        "ELEM ENTO": "ELEMENTO",
        "EME RGENCIAL": "EMERGENCIAL",
        "ATIV IDADE": "ATIVIDADE",
        "RESPECTIV A": "RESPECTIVA",
        "DESL IGAMENTO": "DESLIGAMENTO",
        "CONV OCAÇÃO": "CONVOCAÇÃO",
        "TRAV ESSIAS": "TRAVESSIAS",
        "DESMONT AGEM": "DESMONTAGEM",
        "COBERTUR A": "COBERTURA",
        "INSTAL AÇÃO": "INSTALAÇÃO",
        "DESLOCA MENTO": "DESLOCAMENTO",
        "RETIRAD A": "RETIRADA",
        "INSTALAÇÃ O": "INSTALAÇÃO",
        "IDENTIFICAÇÃ O": "IDENTIFICAÇÃO",
        "CADASTR AL": "CADASTRAL",
        "VALET AS": "VALETAS"
    }

    output_list = []
    for cod, desc, us_m, us_d, cat in atividades_unicas.values():
        desc_norm = desc
        for broken_word, correct_word in REPLACEMENTS.items():
            desc_norm = desc_norm.replace(broken_word, correct_word)
            
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
            "categoria": cat,
            "forma_pagamento": forma_pagamento,
            "descricao_detalhada": descricao_detalhada,
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
