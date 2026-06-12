import re
import json
import os
from pypdf import PdfReader

# Adjust paths to run and locate Firebase configuration
import sys
base_dir = r"d:\programas\DDS"
sys.path.insert(0, os.path.join(base_dir, "dds-webtools"))
local_key = os.path.join(base_dir, "firebase_config.json")
if os.path.exists(local_key):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_key
    print(f"DEBUG: Using local key {local_key}")

from monitor.services.firestore_client import db

PDF_PATH = os.path.join(base_dir, "dds-webtools", "produtividade", "MIT 163108_Atividades de Construção.pdf")
OUTPUT_PATH = os.path.join(base_dir, "parsed_mit_v2.json")

def is_header_footer(line):
    line = line.strip()
    if not line:
        return True
    if re.search(r'\d{1,2}\s+\d{1,2}/\d{1,2}/\d{4}', line):
        return True
    if re.match(r'^\d+\s+\d+\s+\d+$', line):
        return True
    ignore_phrases = [
        "MANUAL DE INSTRUÇÕES",
        "Título: FISCALIZAÇÃO",
        "Módulo: ATIVIDADES",
        "Órgão Emissor:",
        "Visto:",
        "Aprovado:",
        "Folha"
    ]
    for phrase in ignore_phrases:
        if phrase in line:
            return True
    return False

# OCR corrections dictionary
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

def clean_ocr_text(text):
    for broken, fixed in REPLACEMENTS.items():
        text = text.replace(broken, fixed)
    return re.sub(r'\s+', ' ', text).strip()

def parse_mit():
    print("Reading PDF:", PDF_PATH)
    reader = PdfReader(PDF_PATH)
    
    all_lines = []
    for p_idx in range(4, len(reader.pages)):
        text = reader.pages[p_idx].extract_text() or ''
        has_desmontagem = "DESMONTAGEM" in text
        lines = text.split('\n')
        for l in lines:
            if is_header_footer(l):
                continue
            all_lines.append((l.strip(), has_desmontagem, p_idx))
            
    re_categoria = re.compile(r'^\s*(4\.\d+)\s*[\-\uFFFD\s]+\s*(.+)$')
    re_inicio_item = re.compile(r'^\s*(\d{3,4})\s+([A-ZÇÃÉÍÓÚÂÊÔ].*)$')
    re_codigo_sozinho = re.compile(r'^\s*(\d{3,4})\s*$')
    
    active_category = "Não Categorizado"
    items_raw = []
    current_item = None
    
    idx = 0
    while idx < len(all_lines):
        text_line, has_desmontagem, page_num = all_lines[idx]
        
        match_cat = re_categoria.match(text_line)
        if match_cat:
            prefix = match_cat.group(1)
            active_category = f"{prefix} - {match_cat.group(2).strip()}"
            idx += 1
            continue
            
        is_item_start = False
        codigo = None
        titulo = ''
        
        match_item = re_inicio_item.match(text_line)
        if match_item:
            is_item_start = True
            codigo = int(match_item.group(1))
            titulo = match_item.group(2).strip()
        else:
            match_code_only = re_codigo_sozinho.match(text_line)
            if match_code_only and idx + 1 < len(all_lines):
                next_line = all_lines[idx+1][0]
                if re.match(r'^[A-ZÇÃÉÍÓÚÂÊÔ]', next_line) and not re.match(r'^\d', next_line):
                    is_item_start = True
                    codigo = int(match_code_only.group(1))
                    titulo = next_line
                    idx += 1
                    
        if is_item_start:
            if current_item:
                items_raw.append(current_item)
            current_item = {
                "codigo": codigo,
                "titulo": titulo,
                "category": active_category,
                "lines": [],
                "has_desmontagem": has_desmontagem
            }
        else:
            if current_item:
                current_item["lines"].append(text_line)
                current_item["has_desmontagem"] = has_desmontagem
                
        idx += 1
        
    if current_item:
        items_raw.append(current_item)
        
    print(f"Parsed {len(items_raw)} raw items from PDF.")
    
    # Common formulas or dynamic activities by code
    DYNAMIC_CODES = {
        863: "deslocamento",
        879: "hora_extra",
        690: "deslocamento_adicional",
        698: "transporte_postes_demanda",
        861: "deslocamento_cancelado",
        880: "transporte_meios_alternativos",
        938: "deslocamento_simples"
    }
    
    processed_items = []
    for item in items_raw:
        codigo = item["codigo"]
        titulo = item["titulo"]
        category = item["category"]
        lines = item["lines"]
        has_desmontagem = item["has_desmontagem"]
        
        cleaned_item_lines = []
        for l in lines:
            if "ITEM" in l and "ATIVIDADES" in l:
                continue
            if "MONTAGEM" in l or "DESMONTAGEM" in l:
                continue
            cleaned_item_lines.append(l)
            
        full_text = " ".join([titulo] + cleaned_item_lines)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        
        us_montagem = 0.0
        us_desmontagem = 0.0
        calculo_dinamico = False
        tipo_calculo = None
        forma_pagamento = "UNIDADE"
        
        # Determine payment form
        match_pagamento = re.search(r',\s*(POR\s+[A-ZÇÃÉÍÓÚÂÊÔ/]+\s*[A-ZÇÃÉÍÓÚÂÊÔ/]*)\b', full_text, re.IGNORECASE)
        if match_pagamento:
            forma_pagamento = match_pagamento.group(1).strip().upper()
            tarefa_titulo = full_text[:match_pagamento.start()].strip()
            desc_detalhada = full_text[match_pagamento.end():].strip()
        else:
            match_fallback = re.search(r'\b(POR\s+[A-ZÇÃÉÍÓÚÂÊÔ]+)\b', full_text, re.IGNORECASE)
            if match_fallback:
                forma_pagamento = match_fallback.group(1).strip().upper()
                tarefa_titulo = full_text[:match_fallback.start()].strip()
                desc_detalhada = full_text[match_fallback.end():].strip()
            else:
                tarefa_titulo = full_text
                desc_detalhada = ""
                
        if codigo in DYNAMIC_CODES:
            calculo_dinamico = True
            tipo_calculo = DYNAMIC_CODES[codigo]
            
        # Check for formulas in description
        re_formula = re.compile(r'\(\s*[A-Za-z\d\s\-–\+x\*\/,]+\s*\).{0,20}$')
        if not calculo_dinamico:
            if re_formula.search(desc_detalhada) or "t x n" in desc_detalhada or "D – 50" in desc_detalhada:
                calculo_dinamico = True
                tipo_calculo = "outros"
                
        if calculo_dinamico:
            us_montagem = 0.0
            us_desmontagem = 0.0
        else:
            if has_desmontagem:
                match_val = re.search(r'\s+(\d+[\d,.]*|-)\s+(\d+[\d,.]*|-)\s*$', desc_detalhada)
                if match_val:
                    m_val = match_val.group(1).replace(",", ".")
                    d_val = match_val.group(2).replace(",", ".")
                    us_montagem = float(m_val) if m_val != "-" else 0.0
                    us_desmontagem = float(d_val) if d_val != "-" else 0.0
                    desc_detalhada = desc_detalhada[:match_val.start()].strip()
            else:
                match_val = re.search(r'\s+(\d+[\d,.]*|-)\s*$', desc_detalhada)
                if match_val:
                    m_val = match_val.group(1).replace(",", ".")
                    us_montagem = float(m_val) if m_val != "-" else 0.0
                    us_desmontagem = 0.0
                    desc_detalhada = desc_detalhada[:match_val.start()].strip()
                    
        # Apply OCR corrections now only to title and detailed description text
        tarefa_titulo = clean_ocr_text(tarefa_titulo)
        desc_detalhada = clean_ocr_text(desc_detalhada)
                    
        processed_items.append({
            "codigo": codigo,
            "tarefa": tarefa_titulo,
            "categoria": category,
            "forma_pagamento": forma_pagamento,
            "descricao_detalhada": desc_detalhada,
            "us_montagem": us_montagem,
            "us_desmontagem": us_desmontagem,
            "calculo_dinamico": calculo_dinamico,
            "tipo_calculo": tipo_calculo,
            "raw_text": full_text
        })
        
    return processed_items

def main():
    # 1. Load already saved items from Firestore to print comparison stats
    try:
        docs = db.collection("webtools").document("producao").collection("atividades_mit").stream()
        saved_codes = {int(d.id) for d in docs}
        print(f"Firestore currently has {len(saved_codes)} activities confirmed.")
    except Exception as e:
        print("Could not query Firestore:", e)
        saved_codes = set()
        
    # 2. Parse the activities
    parsed_items = parse_mit()
    
    # 3. Print breakdown
    new_items = [x for x in parsed_items if x["codigo"] not in saved_codes]
    print(f"Total parsed: {len(parsed_items)}")
    print(f"Already saved in Firestore: {len(parsed_items) - len(new_items)}")
    print(f"New pending items to review: {len(new_items)}")
    print("New codes list:", [x["codigo"] for x in new_items])
    
    # 4. Save to JSON
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(parsed_items, f, ensure_ascii=False, indent=2)
    print("Successfully updated file:", OUTPUT_PATH)

if __name__ == "__main__":
    main()
