import re
import json
import os
from pypdf import PdfReader

PDF_PATH = r"d:\programas\DDS\dds-webtools\produtividade\MIT 163108_Atividades de Construção.pdf"

def is_header_footer(line):
    line = line.strip()
    if not line:
        return True
    # If it's a version/date like "16  21/07/2025" or similar
    if re.search(r'\d{1,2}\s+\d{1,2}/\d{1,2}/\d{4}', line):
        return True
    # Page numbers/codes like "31 08 28"
    if re.match(r'^\d+\s+\d+\s+\d+$', line):
        return True
    # Title / Module / Header elements
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

def parse_mit():
    reader = PdfReader(PDF_PATH)
    
    # 1. Read all lines of the PDF sequentially and tag them with context
    all_lines = []
    for p_idx in range(4, len(reader.pages)):
        text = reader.pages[p_idx].extract_text() or ''
        
        # Determine if this page has desmontagem
        has_desmontagem = "DESMONTAGEM" in text
        
        lines = text.split('\n')
        for l in lines:
            if is_header_footer(l):
                continue
            all_lines.append((l.strip(), has_desmontagem, p_idx))
            
    # 2. Iterate and group into items
    re_categoria = re.compile(r'^\s*(4\.\d+)\s*[\-\uFFFD\s]+\s*(.+)$')
    re_inicio_item = re.compile(r'^\s*(\d{3,4})\s+([A-ZÇÃÉÍÓÚÂÊÔ].*)$')
    
    active_category = "Não Categorizado"
    items_raw = []
    current_item = None
    
    for text_line, has_desmontagem, page_num in all_lines:
        # Check category
        match_cat = re_categoria.match(text_line)
        if match_cat:
            prefix = match_cat.group(1)
            active_category = f"{prefix} - {match_cat.group(2).strip()}"
            continue
            
        # Check item start
        match_item = re_inicio_item.match(text_line)
        if match_item:
            if current_item:
                items_raw.append(current_item)
            current_item = {
                "codigo": int(match_item.group(1)),
                "titulo": match_item.group(2).strip(),
                "category": active_category,
                "lines": [],
                "has_desmontagem": has_desmontagem,
                "page_end": page_num
            }
        else:
            if current_item:
                current_item["lines"].append(text_line)
                # Keep updating has_desmontagem to the page where the item ends
                current_item["has_desmontagem"] = has_desmontagem
                current_item["page_end"] = page_num
                
    if current_item:
        items_raw.append(current_item)
        
    print(f"DEBUG: Found {len(items_raw)} raw items.")
    
    # 3. Process each item's text and extract values
    processed_items = []
    
    # Common formulas or dynamic activities by code
    DYNAMIC_CODES = {
        863: "deslocamento",
        879: "hora_extra",
        690: "deslocamento_adicional",
        698: "transporte_postes_demanda",
        861: "deslocamento_cancelado",
        880: "transporte_meios_alternativos"
    }
    
    for item in items_raw:
        codigo = item["codigo"]
        titulo = item["titulo"]
        category = item["category"]
        lines = item["lines"]
        has_desmontagem = item["has_desmontagem"]
        
        # Clean header junk from description lines if any got in
        cleaned_item_lines = []
        for l in lines:
            if "ITEM" in l and "ATIVIDADES" in l:
                continue
            if "MONTAGEM" in l or "DESMONTAGEM" in l:
                continue
            cleaned_item_lines.append(l)
            
        # Combine title and lines
        full_text = " ".join([titulo] + cleaned_item_lines)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        
        # Values extraction
        us_montagem = 0.0
        us_desmontagem = 0.0
        calculo_dinamico = False
        tipo_calculo = None
        forma_pagamento = "UNIDADE"
        
        # Determine payment form (e.g. POR KM, POR UNIDADE)
        match_pagamento = re.search(r',\s*(POR\s+[A-ZÇÃÉÍÓÚÂÊÔ/]+\s*[A-ZÇÃÉÍÓÚÂÊÔ/]*)\b', full_text, re.IGNORECASE)
        if match_pagamento:
            forma_pagamento = match_pagamento.group(1).strip().upper()
            # Split details
            tarefa_titulo = full_text[:match_pagamento.start()].strip()
            desc_detalhada = full_text[match_pagamento.end():].strip()
        else:
            # Fallback patterns
            match_fallback = re.search(r'\b(POR\s+[A-ZÇÃÉÍÓÚÂÊÔ]+)\b', full_text, re.IGNORECASE)
            if match_fallback:
                forma_pagamento = match_fallback.group(1).strip().upper()
                tarefa_titulo = full_text[:match_fallback.start()].strip()
                desc_detalhada = full_text[match_fallback.end():].strip()
            else:
                tarefa_titulo = full_text
                desc_detalhada = ""
                
        # If the code is known to be dynamic, mark it
        if codigo in DYNAMIC_CODES:
            calculo_dinamico = True
            tipo_calculo = DYNAMIC_CODES[codigo]
            
        # Extract values or formulas from the end of desc_detalhada
        # Try to find formulas like ( 0,450 x D ) or ( t x n ) or 0,113 x ( D - 50 )
        re_formula = re.compile(r'\(\s*[A-Za-z\d\s\-–\+x\*\/,]+\s*\).{0,20}$')
        
        # If it's not marked dynamic, but ends with a formula:
        if not calculo_dinamico:
            if re_formula.search(desc_detalhada) or "t x n" in desc_detalhada or "D – 50" in desc_detalhada:
                calculo_dinamico = True
                tipo_calculo = "outros"
                
        if calculo_dinamico:
            us_montagem = 0.0
            us_desmontagem = 0.0
        else:
            # Standard numeric extraction
            if has_desmontagem:
                # Expect two values at the end, e.g. "3,40 1,36" or "4,70 -"
                match_val = re.search(r'\s+(\d+[\d,.]*|-)\s+(\d+[\d,.]*|-)\s*$', desc_detalhada)
                if match_val:
                    m_val = match_val.group(1).replace(",", ".")
                    d_val = match_val.group(2).replace(",", ".")
                    us_montagem = float(m_val) if m_val != "-" else 0.0
                    us_desmontagem = float(d_val) if d_val != "-" else 0.0
                    # Remove from description
                    desc_detalhada = desc_detalhada[:match_val.start()].strip()
            else:
                # Expect only one value at the end, e.g. "7,749"
                match_val = re.search(r'\s+(\d+[\d,.]*|-)\s*$', desc_detalhada)
                if match_val:
                    m_val = match_val.group(1).replace(",", ".")
                    us_montagem = float(m_val) if m_val != "-" else 0.0
                    us_desmontagem = 0.0
                    # Remove from description
                    desc_detalhada = desc_detalhada[:match_val.start()].strip()
                    
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

if __name__ == "__main__":
    items = parse_mit()
    print(f"Total processed: {len(items)}")
    
    # Save a sample to test
    with open("test_parsed_mit.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
        
    # Print some key items to verify
    for code in [850, 854, 621, 690, 863, 879]:
        item = next((x for x in items if x["codigo"] == code), None)
        if item:
            print(f"\nCode: {item['codigo']} | {item['tarefa']}")
            print(f"  Category: {item['categoria']}")
            print(f"  Pagamento: {item['forma_pagamento']}")
            print(f"  US Montagem: {item['us_montagem']} | US Desmontagem: {item['us_desmontagem']}")
            print(f"  Dinamico: {item['calculo_dinamico']} | Tipo: {item['tipo_calculo']}")
            print(f"  Desc: {item['descricao_detalhada'][:200]}...")
