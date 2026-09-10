import re
import os
import sys

# Ajusta caminhos para permitir execução direta
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)
sys.path.insert(0, os.path.join(base_dir, "monitor"))

# Configuração de Credenciais Locais se existirem
local_key = r"d:\programas\DDS\firebase_config.json"
if os.path.exists(local_key):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_key
    print(f"DEBUG: Usando credenciais locais de {local_key}")

from pypdf import PdfReader
from monitor.services.firestore_client import db

MANUAL_PATH = r"D:\programas\GerenciadorTarefas\MIT 163108_Atividades de Construção.pdf"

def limpar_linhas(texto):
    if not texto:
        return []
    linhas = texto.split("\n")
    linhas_limpas = []
    for l in linhas:
        l_strip = l.strip()
        if not l_strip:
            continue
        # Ignorar cabeçalhos de folha Copel
        if "MANUAL DE INSTRUÇÕES" in l_strip or "Título: FISCALIZAÇÃO" in l_strip or "Módulo: ATIVIDADES" in l_strip or "Órgão Emissor:" in l_strip:
            continue
        # Ignorar linhas de numeração de folha soltas
        if re.match(r'^\d+\s+\d+\s+\d+$', l_strip):
            continue
        linhas_limpas.append(l_strip)
    return linhas_limpas

def carregar_atividades_mit():
    if not os.path.exists(MANUAL_PATH):
        print(f"Erro: Arquivo do manual não encontrado em: {MANUAL_PATH}")
        return
        
    print("Lendo o manual MIT 163108...")
    reader = PdfReader(MANUAL_PATH)
    
    atividades = []
    
    # Estado da máquina
    codigo_ativo = None
    desc_acumulada = []
    
    # Regex para início de item: número de 3 ou 4 dígitos seguido de palavra em maiúscula
    re_inicio_item = re.compile(r'^\s*(\d{3,4})\s+([A-ZÇÃÉÍÓÚÂÊÔ].*)$')
    
    # Regex para fim de item com US: exige que comece com dígito para não pegar pontos e traços órfãos
    re_valores_fim = re.compile(r'\s+(\d+[\d,.]*)\s+(\d+[\d,.]*|-)\s*$')

    # Ler a partir da página 5 (índice 4) até a página 42 (índice 41)
    for p_idx in range(4, 42):
        text = reader.pages[p_idx].extract_text()
        linhas = limpar_linhas(text)
        
        for linha in linhas:
            # 1. Verificar se a linha contém o fim do item (valores de US)
            match_valores = re_valores_fim.search(linha)
            
            # 2. Verificar se a linha é o início de um novo item
            match_inicio = re_inicio_item.match(linha)
            
            if match_inicio:
                # Se já tínhamos um item ativo pendente, salvamos
                if codigo_ativo is not None:
                    desc_completa = " ".join(desc_acumulada)
                    atividades.append((codigo_ativo, desc_completa, 0.0, 0.0))
                
                # Inicia novo item
                codigo_ativo = int(match_inicio.group(1))
                corpo_linha = match_inicio.group(2)
                
                # Se o início já continha os valores de US no final
                if match_valores:
                    # Remove os valores do corpo da descrição
                    corpo_linha = re_valores_fim.sub("", corpo_linha)
                    desc_acumulada = [corpo_linha.strip()]
                    
                    us_m = float(match_valores.group(1).replace(",", "."))
                    us_d_str = match_valores.group(2).replace(",", ".")
                    us_d = 0.0 if us_d_str == "-" else float(us_d_str)
                    
                    desc_completa = " ".join(desc_acumulada)
                    atividades.append((codigo_ativo, desc_completa, us_m, us_d))
                    
                    # Reseta estado
                    codigo_ativo = None
                    desc_acumulada = []
                else:
                    desc_acumulada = [corpo_linha]
            
            elif codigo_ativo is not None:
                # Se a linha atual é a final do item ativo
                if match_valores:
                    linha_limpa_valores = re_valores_fim.sub("", linha).strip()
                    if linha_limpa_valores:
                        desc_acumulada.append(linha_limpa_valores)
                        
                    us_m = float(match_valores.group(1).replace(",", "."))
                    us_d_str = match_valores.group(2).replace(",", ".")
                    us_d = 0.0 if us_d_str == "-" else float(us_d_str)
                    
                    desc_completa = " ".join(desc_acumulada)
                    
                    # Limpeza de hífens órfãos como "pós-" no final do texto
                    desc_completa = re.sub(r'\s*-\s*$', '', desc_completa)
                    
                    atividades.append((codigo_ativo, desc_completa, us_m, us_d))
                    
                    # Reseta estado
                    codigo_ativo = None
                    desc_acumulada = []
                else:
                    # Apenas adiciona à descrição acumulada
                    desc_acumulada.append(linha)
                    
    # Filtrar itens repetidos e inválidos
    atividades_unicas = {}
    for item in atividades:
        if item[0] < 50 or item[0] > 2000:
            continue
        atividades_unicas[item[0]] = item

    print(f"Total de {len(atividades_unicas)} atividades parsed do PDF.")

    # Upload em lotes para o Firestore (/copel_mit_atividades)
    print("Enviando atividades para o Firestore...")
    batch = db.batch()
    count = 0
    total_enviado = 0
    
    for cod, desc, us_m, us_d in atividades_unicas.values():
        # 1. Normalizar texto comum e remover múltiplos espaços/erros de OCR
        if int(cod) == 616:
            # Special normalization as requested by user to keep "PA RA"
            desc_norm = desc.replace("ARE NITO", "ARENITO")
            desc_norm = desc_norm.replace("POST E", "POSTE")
            desc_norm = desc_norm.replace("60 0", "600")
            desc_norm = re.sub(r'\s+', ' ', desc_norm).strip()
        else:
            desc_norm = desc.replace("ARE NITO", "ARENITO")
            desc_norm = desc_norm.replace("PA RA", "PARA")
            desc_norm = desc_norm.replace("POST E", "POSTE")
            desc_norm = desc_norm.replace("60 0", "600")
            desc_norm = desc_norm.replace("ANCO RAGEM", "ANCORAGEM")
            desc_norm = re.sub(r'\s+', ' ', desc_norm).strip()
        
        # 2. Capturar a forma de pagamento (unidade)
        # Ex: "CADEIA DE ISOLADORES... , POR CADEIA Compreende..." -> "POR CADEIA"
        match_unidade = re.search(r',\s*(POR\s+[A-ZÇÃÉÍÓÚÂÊÔ]+)\b', desc_norm)
        
        if match_unidade:
            forma_pagamento = match_unidade.group(1).strip()
            # tarefa (nome curto) é tudo antes de ", POR ..."
            tarefa = desc_norm[:match_unidade.start()].strip()
            # descricao (detalhada) é tudo depois do ", POR ..."
            descricao_detalhada = desc_norm[match_unidade.end():].strip()
        else:
            forma_pagamento = "UNIDADE"
            tarefa = desc_norm
            descricao_detalhada = ""
 
        doc_ref = db.collection("webtools").document("producao").collection("atividades_mit").document(str(cod))
        batch.set(doc_ref, {
            "codigo": int(cod),
            "tarefa": tarefa,
            "forma_pagamento": forma_pagamento,
            "descricao": descricao_detalhada if descricao_detalhada else tarefa,
            "us_montagem": float(us_m),
            "us_desmontagem": float(us_d)
        })
        count += 1
        
        # Firestore limita lote de gravação em 500 operações
        if count == 400:
            batch.commit()
            total_enviado += count
            print(f"Progresso: {total_enviado} enviados...")
            batch = db.batch()
            count = 0
            
    if count > 0:
        batch.commit()
        total_enviado += count
        
    print(f"Concluído! {total_enviado} atividades cadastradas no Firestore (/webtools/producao/atividades_mit).")

if __name__ == "__main__":
    carregar_atividades_mit()
