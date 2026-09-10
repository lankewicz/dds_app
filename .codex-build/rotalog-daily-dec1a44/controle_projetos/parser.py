import re
import os
import sqlite3
from datetime import datetime
from pypdf import PdfReader

try:
    from database import obter_conexao
except ImportError:
    from controle_projetos.database import obter_conexao

def limpar_linha(linha):
    # Remove marcas de rodapé de página que se misturam com o texto
    linha = re.sub(r'PÁGINA:\s*\d+/\d+', '', linha)
    linha = re.sub(r'PÁGINA:\s*\d+', '', linha)
    return linha.strip()

def importar_projeto_pdf(pdf_path):
    if not os.path.exists(pdf_path):
        print(f"Erro: Arquivo PDF não encontrado em: {pdf_path}")
        return None

    print(f"Analisando PDF de projeto: {pdf_path}...")
    reader = PdfReader(pdf_path)
    
    projeto_id = None
    titulo = "Projeto Sem Título"
    
    # Estruturas (PS e Trechos)
    # { 'PS 1': { 'tipo': 'PS', 'tarefas': [...] } }
    estruturas = {}
    
    modo_tarefas = False
    estrutura_atual = None
    
    # Regex para capturar Projeto e Título
    re_projeto = re.compile(r'PROJETO\s*:\s*(.+)$', re.IGNORECASE)
    re_titulo = re.compile(r'TITULO DA OBRA\s*:\s*(.+)$', re.IGNORECASE)
    
    # Regex para detectar início de seções de tarefas
    re_tarefas_ps = re.compile(r'TAREFAS\s+NO\s+PS\s*:\s*(\d+)', re.IGNORECASE)
    re_tarefas_trecho = re.compile(r'TAREFAS\s+NO\s+TRECHO\s*:\s*([\d\s\-]+)', re.IGNORECASE)
    
    # Regex para capturar linhas de tarefas
    # Formato: [ITEM_NUM] [CÓDIGO_MIT] [DESCRIÇÃO] [QTDE] [SINAL]
    # Ex: 1 743 LEV. POSTE ATE 10,5M ATE 1000 DAN 1 -
    # Ex: 20 862 CONCRETAGEM 0,570 +
    # Pega: item, codigo (3 ou 4 digitos), descrição, quantidade (número decimal), sinal (+ ou - ou *+ ou *-)
    re_tarefa_linha = re.compile(r'^\s*(\d+)\s+(\d{3,4})\s+(.+?)\s+([\d.,]+)\s+([\+\-\*]+)\s*$', re.IGNORECASE)
    # Fallback se o sinal sumir devido ao rodapé
    re_tarefa_fallback = re.compile(r'^\s*(\d+)\s+(\d{3,4})\s+(.+?)\s+([\d.,]+)\s*$', re.IGNORECASE)

    for page_num, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text:
            continue
            
        lines = text.split('\n')
        for line in lines:
            line_clean = limpar_linha(line)
            if not line_clean:
                continue
                
            # 1. Tentar ler Projeto ID
            match_proj = re_projeto.search(line_clean)
            if match_proj and not projeto_id:
                projeto_id = match_proj.group(1).strip()
                continue
                
            # 2. Tentar ler Título
            match_tit = re_titulo.search(line_clean)
            if match_tit and titulo == "Projeto Sem Título":
                titulo = match_tit.group(1).strip()
                continue
                
            # 3. Tentar detectar início de TAREFAS NO PS
            match_tps = re_tarefas_ps.search(line_clean)
            if match_tps:
                modo_tarefas = True
                ps_num = match_tps.group(1).strip()
                estrutura_atual = f"PS {ps_num}"
                if estrutura_atual not in estruturas:
                    estruturas[estrutura_atual] = {"tipo": "PS", "tarefas": []}
                continue
                
            # 4. Tentar detectar início de TAREFAS NO TRECHO
            match_tt = re_tarefas_trecho.search(line_clean)
            if match_tt:
                modo_tarefas = True
                trecho_id = match_tt.group(1).strip().replace(" ", "")
                estrutura_atual = f"Trecho {trecho_id}"
                if estrutura_atual not in estruturas:
                    estruturas[estrutura_atual] = {"tipo": "TRECHO", "tarefas": []}
                continue
                
            # 5. Se estivermos lendo tarefas, verificar se a linha é uma linha de dados
            if modo_tarefas and estrutura_atual:
                # Se a linha mudar de seção, podemos resetar (opcional)
                if "MÓDULOS NO" in line_clean or "MATERIAIS NO" in line_clean:
                    modo_tarefas = False
                    continue
                    
                match_tar = re_tarefa_linha.match(line_clean)
                if match_tar:
                    item_num = int(match_tar.group(1))
                    codigo_mit = int(match_tar.group(2))
                    descricao = match_tar.group(3).strip()
                    qtde = float(match_tar.group(4).replace(",", "."))
                    sinal = match_tar.group(5).strip()
                    
                    # Normaliza sinal
                    if "+" in sinal:
                      sinal_norm = "+"
                    else:
                      sinal_norm = "-"
                        
                    estruturas[estrutura_atual]["tarefas"].append({
                        "codigo": codigo_mit,
                        "descricao": descricao,
                        "quantidade": qtde,
                        "sinal": sinal_norm
                    })
                else:
                    # Tentar fallback se o sinal foi perdido no rodapé
                    match_fall = re_tarefa_fallback.match(line_clean)
                    if match_fall:
                        item_num = int(match_fall.group(1))
                        codigo_mit = int(match_fall.group(2))
                        # Verifica se não é um cabeçalho
                        if codigo_mit >= 50 and codigo_mit <= 2000:
                            descricao = match_fall.group(3).strip()
                            qtde = float(match_fall.group(4).replace(",", "."))
                            # Default para '-' se a descrição original do PDF sugerir remoção
                            sinal_norm = "-" if "retirada" in line_clean.lower() or "remoc" in line_clean.lower() else "+"
                            
                            estruturas[estrutura_atual]["tarefas"].append({
                                "codigo": codigo_mit,
                                "descricao": descricao,
                                "quantidade": qtde,
                                "sinal": sinal_norm
                            })

    if not projeto_id:
        print("Aviso: Não foi possível extrair o ID do projeto do PDF.")
        # Gerar um ID temporário baseado no timestamp
        projeto_id = f"PROJ-{int(datetime.now().timestamp())}"
        
    print(f"Projeto Extraído: {projeto_id} - {titulo}")
    print(f"Total de estruturas encontradas: {len(estruturas)}")
    
    # Persistir no banco de dados SQLite
    conn = obter_conexao()
    cursor = conn.cursor()
    
    try:
        # 1. Inserir ou substituir projeto
        cursor.execute(
            "INSERT OR REPLACE INTO projetos (id, titulo, data_importacao) VALUES (?, ?, ?)",
            (projeto_id, titulo, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        
        # 2. Inserir estruturas e suas tarefas
        for est_nome, est_dados in estruturas.items():
            # Inserir estrutura
            cursor.execute(
                "INSERT INTO projeto_estruturas (projeto_id, identificador, tipo, descricao_resumida) VALUES (?, ?, ?, ?)",
                (projeto_id, est_nome, est_dados["tipo"], est_nome)
            )
            est_id = cursor.lastrowid
            
            # Inserir tarefas
            for tar in est_dados["tarefas"]:
                cursor.execute(
                    "INSERT INTO projeto_tarefas (estrutura_id, atividade_codigo, quantidade, sinal) VALUES (?, ?, ?, ?)",
                    (est_id, tar["codigo"], tar["quantidade"], tar["sinal"])
                )
                
        conn.commit()
        print("Importação gravada com sucesso no banco de dados!")
        return projeto_id
    except Exception as e:
        conn.rollback()
        print(f"Erro ao salvar no banco de dados: {e}")
        return None
    finally:
        conn.close()
