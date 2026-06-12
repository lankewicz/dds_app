import os
import re
import datetime
from typing import List, Optional
from fastapi import HTTPException
from pypdf import PdfReader
from google.cloud import firestore

from monitor.services.firestore_client import db

# Caminho base no Firestore para a empresa, contrato e setor
BASE_DOC_PATH = db.collection("webtools").document("producao")

# Caches locais para otimizar desempenho e reduzir operações de leitura do Firestore
_mit_cache = {}
_project_cache = {}

def _get_mit_info(codigo: int) -> dict:
    """Busca informações de descrição e US no Firestore e armazena em cache na memória."""
    global _mit_cache
    if not _mit_cache:
        # Carrega todas as atividades estáticas uma única vez
        docs = BASE_DOC_PATH.collection("atividades_mit").stream()
        for doc in docs:
            d = doc.to_dict()
            _mit_cache[d["codigo"]] = d
            
    raw_info = _mit_cache.get(codigo, None)
    if raw_info:
        # Mapeamento de compatibilidade:
        # - "tarefa" é o nome curto (ex: COLETA DE DADOS...)
        # - "descricao" no Firestore é a descrição detalhada (ex: Compreende a obtenção...)
        # - Para as tabelas do front exibirem o nome curto sem quebrar o layout, mapeamos "descricao" para o nome curto (tarefa)
        #   e criamos "descricao_detalhada" para abrigar a explicação longa.
        tarefa_curta = raw_info.get("tarefa", raw_info.get("descricao", f"Atividade {codigo}"))
        desc_detalhada = raw_info.get("descricao", tarefa_curta)
        
        return {
            "codigo": raw_info["codigo"],
            "tarefa": tarefa_curta,
            "descricao": tarefa_curta,
            "descricao_detalhada": desc_detalhada,
            "forma_pagamento": raw_info.get("forma_pagamento", "UNIDADE"),
            "us_montagem": raw_info.get("us_montagem", 0.0),
            "us_desmontagem": raw_info.get("us_desmontagem", 0.0),
            "calculo_dinamico": raw_info.get("calculo_dinamico", False),
            "tipo_calculo": raw_info.get("tipo_calculo", None),
            "ativo": raw_info.get("ativo", True)
        }
        
    return {
        "codigo": codigo,
        "tarefa": f"Atividade {codigo}",
        "descricao": f"Atividade {codigo}",
        "descricao_detalhada": f"Atividade {codigo}",
        "us_montagem": 0.0,
        "us_desmontagem": 0.0,
        "calculo_dinamico": False,
        "tipo_calculo": None,
        "ativo": True
    }

def _get_project_title(projeto_id: str) -> Optional[str]:
    """Busca o título do projeto e armazena em cache na memória."""
    global _project_cache
    if not projeto_id:
        return None
    if projeto_id not in _project_cache:
        doc = BASE_DOC_PATH.collection("projetos").document(projeto_id).get()
        if doc.exists:
            _project_cache[projeto_id] = doc.to_dict().get("titulo")
        else:
            _project_cache[projeto_id] = "Projeto Desconhecido"
    return _project_cache[projeto_id]

# 1. Pesquisar Atividades do MIT 163108
def pesquisar_atividades_db(q: Optional[str] = None) -> List[dict]:
    # Força carregamento do cache
    _get_mit_info(0)
    
    results = list(_mit_cache.values())
    if q:
        q_clean = q.strip().lower()
        if q_clean.isdigit():
            # Filtra por código exato ou parcial
            results = [a for a in results if q_clean in str(a["codigo"])]
        else:
            # Filtra por descrição
            results = [a for a in results if q_clean in a["descricao"].lower()]
            
    # Retorna ordenado pelo código (retorna todas as atividades para listagem administrativa completa)
    # Mapeia descrição para compatibilidade usando _get_mit_info para garantir o preenchimento de campos corretos
    results_mapped = [_get_mit_info(a["codigo"]) for a in results]
    results_mapped = sorted(results_mapped, key=lambda x: x["codigo"])
    return results_mapped

# 2. Listar Todos os Projetos
def listar_projetos_db() -> List[dict]:
    docs = BASE_DOC_PATH.collection("projetos").order_by("data_importacao", direction=firestore.Query.DESCENDING).stream()
    return [doc.to_dict() for doc in docs]

# 3. Listar Estruturas de um Projeto
def listar_estruturas_db(projeto_id: str) -> List[dict]:
    docs = BASE_DOC_PATH.collection("estruturas").where("projeto_id", "==", projeto_id).stream()
    estruturas = [doc.to_dict() for doc in docs]
    # Ordena pelo identificador ex: PS 1, PS 2
    # Ordenação natural rápida
    try:
        def extrair_numero(s):
            m = re.search(r'\d+', s["identificador"])
            return int(m.group(0)) if m else 0
        import re
        estruturas = sorted(estruturas, key=extrair_numero)
    except Exception:
        estruturas = sorted(estruturas, key=lambda x: x["identificador"])
    return estruturas

# 4. Listar Tarefas de uma Estrutura (do Projeto)
def listar_tarefas_estrutura_db(estrutura_id: int) -> List[dict]:
    doc = BASE_DOC_PATH.collection("estruturas").document(str(estrutura_id)).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Estrutura não encontrada.")
    
    est = doc.to_dict()
    tarefas = []
    
    for t in est.get("tarefas", []):
        mit_info = _get_mit_info(t["codigo"])
        tarefas.append({
            "id": t["id"],
            "estrutura_id": est["id"],
            "atividade_codigo": t["codigo"],
            "quantidade": t["quantidade"],
            "sinal": t["sinal"],
            "descricao": mit_info.get("descricao", ""),
            "descricao_detalhada": mit_info.get("descricao_detalhada", ""),
            "forma_pagamento": mit_info.get("forma_pagamento", "UNIDADE"),
            "us_montagem": mit_info["us_montagem"],
            "us_desmontagem": mit_info["us_desmontagem"]
        })
    return tarefas

# 5. Validar Saldo do Projeto
def validar_saldo_projeto(projeto_id: str, codigo_mit: int, quantidade_nova: float, tipo_lancamento: str):
    """Verifica se o saldo de lançamentos de uma atividade não estoura o previsto no projeto."""
    proj_doc = BASE_DOC_PATH.collection("projetos").document(projeto_id).get()
    if not proj_doc.exists:
        # Se não há projeto cadastrado (como em lançamentos manuais rápidos sem obra vinculada), não há limite
        return
    
    proj_data = proj_doc.to_dict()
    totais_previstos = proj_data.get("totais_previstos", {})
    
    codigo_str = str(codigo_mit)
    key_tipo = "montagem" if tipo_lancamento.upper() == "MONTAGEM" else "desmontagem"
    
    limite = totais_previstos.get(codigo_str, {}).get(key_tipo, 0.0)
    if limite <= 0.0:
        # Se não está no projeto, não deveria ser lançado se o controle é rígido
        raise HTTPException(
            status_code=400, 
            detail=f"Atividade {codigo_mit} ({tipo_lancamento}) não está prevista no projeto {projeto_id}."
        )
        
    # Somar tudo o que já foi lançado desse código e tipo neste projeto
    lancamentos_query = BASE_DOC_PATH.collection("lancamentos")\
        .where("projeto_id", "==", projeto_id)\
        .where("atividade_codigo", "==", int(codigo_mit))\
        .where("tipo", "==", tipo_lancamento.upper())\
        .stream()
        
    acumulado = sum(float(l.to_dict().get("quantidade", 0.0)) for l in lancamentos_query)
    
    if acumulado + quantidade_nova > limite:
        restante = max(0.0, limite - acumulado)
        raise HTTPException(
            status_code=400,
            detail=f"Limite excedido no Projeto {projeto_id} para a atividade {codigo_mit} ({tipo_lancamento}). Previsto: {limite}, Já realizado: {acumulado}, Tentativa: {quantidade_nova}, Saldo restante: {restante:.2f}."
        )

# 6. Registrar Lançamento Detalhado por Poste (Abordagem A)
def lancar_poste_db(
    equipe_numero: int,
    data_execucao: str,
    projeto_id: str,
    estrutura_id: int,
    tarefas_completadas: List[int]
) -> dict:
    # Buscar estrutura
    est_doc = BASE_DOC_PATH.collection("estruturas").document(str(estrutura_id)).get()
    if not est_doc.exists:
        raise HTTPException(status_code=404, detail="Estrutura não encontrada.")
        
    est_data = est_doc.to_dict()
    # Filtrar tarefas que foram marcadas como completas
    tarefas = [t for t in est_data.get("tarefas", []) if t["id"] in tarefas_completadas]
    
    if not tarefas:
        raise HTTPException(status_code=400, detail="Nenhuma tarefa válida selecionada para lançamento.")
        
    # Validar limite do saldo antes de gravar
    for t in tarefas:
        tipo = "MONTAGEM" if t["sinal"] == "+" else "DESMONTAGEM"
        validar_saldo_projeto(projeto_id, t["codigo"], t["quantidade"], tipo)
        
    # Gravar em lote (batch) para consistência
    batch = db.batch()
    for t in tarefas:
        tipo = "MONTAGEM" if t["sinal"] == "+" else "DESMONTAGEM"
        l_ref = BASE_DOC_PATH.collection("lancamentos").document() # Auto UUID
        codigo_mit = int(t["codigo"])
        mit = _get_mit_info(codigo_mit)
        qtde = float(t["quantidade"])
        us_unitario = mit["us_montagem"] if tipo == "MONTAGEM" else mit["us_desmontagem"]
        us_calculada = qtde * us_unitario
        
        batch.set(l_ref, {
            "equipe_numero": int(equipe_numero),
            "data_execucao": data_execucao,
            "projeto_id": projeto_id,
            "estrutura_id": int(estrutura_id),
            "atividade_codigo": codigo_mit,
            "quantidade": qtde,
            "tipo": tipo,
            "origem": "POSTE",
            "us_calculada": round(us_calculada, 4)
        })
        
    batch.commit()
    return {"sucesso": True, "mensagem": f"{len(tarefas)} tarefas lançadas com sucesso!"}

# 7. Registrar Lançamento Rápido por Lote (Abordagem B)
def lancar_lote_db(
    equipe_numero: int,
    data_execucao: str,
    projeto_id: Optional[str] = None,
    itens: List[dict] = []
) -> dict:
    if not itens:
        raise HTTPException(status_code=400, detail="Lista de itens vazia.")
        
    # Se houver projeto_id informado, validar o saldo acumulado antes de gravar
    if projeto_id:
        for it in itens:
            validar_saldo_projeto(projeto_id, it["codigo"], it["quantidade"], it["tipo"])
            
    # Gravar em lote
    batch = db.batch()
    for it in itens:
        l_ref = BASE_DOC_PATH.collection("lancamentos").document()
        codigo_mit = int(it["codigo"])
        mit = _get_mit_info(codigo_mit)
        
        # Obter parâmetros adicionais
        elementos = it.get("elementos")
        distancia = it.get("distancia")
        horas = it.get("horas")
        
        # Converter para tipos corretos
        elementos_val = int(elementos) if elementos is not None else None
        distancia_val = float(distancia) if distancia is not None else None
        horas_val = float(horas) if horas is not None else None
        
        is_dinamico = mit.get("calculo_dinamico", False)
        tipo_calculo = mit.get("tipo_calculo")
        tipo_lanc = it["tipo"].upper()
        
        if is_dinamico:
            # Calcular US dinâmica
            if tipo_calculo in ["deslocamento", "deslocamento_adicional", "deslocamento_cancelado"]:
                # Formula: 0.045 * elementos * distancia
                us_calculada = 0.045 * (elementos_val or 0) * (distancia_val or 0.0)
            elif tipo_calculo == "deslocamento_simples":
                # Formula: 0.045 * distancia
                us_calculada = 0.045 * (distancia_val or 0.0)
            elif tipo_calculo in ["hora_extra", "transporte_meios_alternativos"]:
                # Formula: (horas + 2) * elementos
                us_calculada = ((horas_val or 0.0) + 2.0) * (elementos_val or 0)
            else:
                # Fallback genérico para outros cálculos ou quantidade padrão
                us_calculada = float(it["quantidade"])
                
            quantidade_final = us_calculada
        else:
            quantidade_final = float(it["quantidade"])
            us_unitario = mit["us_montagem"] if tipo_lanc == "MONTAGEM" else mit["us_desmontagem"]
            us_calculada = quantidade_final * us_unitario
            
        launch_doc = {
            "equipe_numero": int(equipe_numero),
            "data_execucao": data_execucao,
            "projeto_id": projeto_id,
            "estrutura_id": None,
            "atividade_codigo": codigo_mit,
            "quantidade": quantidade_final,
            "tipo": tipo_lanc,
            "origem": "LOTE",
            "us_calculada": round(us_calculada, 4)
        }
        
        # Adicionar parâmetros de cálculo se existirem ou se for dinâmico
        if elementos_val is not None:
            launch_doc["elementos"] = elementos_val
        if distancia_val is not None:
            launch_doc["distancia"] = distancia_val
        if horas_val is not None:
            launch_doc["horas"] = horas_val
            
        batch.set(l_ref, launch_doc)
        
    batch.commit()
    return {"sucesso": True, "mensagem": f"{len(itens)} itens de lote registrados!"}

# Helper: Calcular intervalo de datas da semana ISO
def obter_intervalo_semana(semana_str: str):
    # semana_str format: YYYY-Www (ex: 2026-W22)
    parts = semana_str.split("-W")
    ano = int(parts[0])
    semana = int(parts[1])
    
    # Segunda-feira da semana
    monday = datetime.date.fromisocalendar(ano, semana, 1)
    # Domingo da semana
    sunday = datetime.date.fromisocalendar(ano, semana, 7)
    
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")

# 8. Obter Consolidado Gráfico Semanal (Equipes 1 a 8)
def obter_dashboard_semanal_db(semana: Optional[str] = None) -> dict:
    if not semana:
        semana = datetime.datetime.now().strftime("%Y-W%W")
        
    # Calcular intervalo de datas da semana
    dt_inicio, dt_fim = obter_intervalo_semana(semana)
    
    # Query lançamentos no intervalo da semana
    lancamentos_query = BASE_DOC_PATH.collection("lancamentos")\
        .where("data_execucao", ">=", dt_inicio)\
        .where("data_execucao", "<=", dt_fim)\
        .stream()
        
    # Inicializar resumo para as 8 equipes
    resumo_equipes = {i: {"equipe": i, "montagem": 0.0, "desmontagem": 0.0, "total": 0.0} for i in range(1, 9)}
    
    for doc in lancamentos_query:
        l = doc.to_dict()
        eq = l.get("equipe_numero")
        if eq not in resumo_equipes:
            continue
            
        mit = _get_mit_info(l["atividade_codigo"])
        tipo = l.get("tipo")
        qtde = float(l.get("quantidade", 0.0))
        
        # Obter US pre-calculada se disponível no documento
        us_valor = l.get("us_calculada")
        if us_valor is None:
            us_valor = qtde * (mit["us_montagem"] if tipo == "MONTAGEM" else mit["us_desmontagem"])
            
        if tipo == "MONTAGEM":
            resumo_equipes[eq]["montagem"] += us_valor
        else:
            resumo_equipes[eq]["desmontagem"] += us_valor
            
        resumo_equipes[eq]["total"] += us_valor
        
    # Arredondar valores
    for eq in resumo_equipes:
        resumo_equipes[eq]["montagem"] = round(resumo_equipes[eq]["montagem"], 2)
        resumo_equipes[eq]["desmontagem"] = round(resumo_equipes[eq]["desmontagem"], 2)
        resumo_equipes[eq]["total"] = round(resumo_equipes[eq]["total"], 2)
        
    return {
        "semana": semana,
        "dados": list(resumo_equipes.values())
    }

# 9. Listar últimos lançamentos com descrição formatada
def listar_lancamentos_db(limite: int = 50) -> List[dict]:
    # Lançamentos mais recentes
    docs = BASE_DOC_PATH.collection("lancamentos")\
        .order_by("data_execucao", direction=firestore.Query.DESCENDING)\
        .limit(limite)\
        .stream()
        
    historico = []
    for doc in docs:
        l = doc.to_dict()
        mit = _get_mit_info(l["atividade_codigo"])
        tipo = l.get("tipo")
        qtde = float(l.get("quantidade", 0.0))
        
        # Calcular ou obter US individual
        us_calculada = l.get("us_calculada")
        if us_calculada is None:
            us_calculada = qtde * (mit["us_montagem"] if tipo == "MONTAGEM" else mit["us_desmontagem"])
        
        historico.append({
            "id": doc.id,
            "equipe_numero": l["equipe_numero"],
            "data_execucao": l["data_execucao"],
            "quantidade": l["quantidade"],
            "tipo": l["tipo"],
            "origem": l["origem"],
            "projeto_titulo": _get_project_title(l.get("projeto_id")),
            "mit_codigo": mit["codigo"],
            "mit_descricao": mit["descricao"],
            "us_calculada": us_calculada
        })
        
    return historico

def _reconstruct_floats(nums_str: str) -> List[float]:
    nums_dot = nums_str.replace(",", ".")
    raw_tokens = nums_dot.split()
    tokens = []
    for tok in raw_tokens:
        if not tokens:
            tokens.append(tok)
            continue
        prev = tokens[-1]
        if tok.startswith('.'):
            tokens[-1] = prev + tok
        elif prev.endswith('.'):
            tokens[-1] = prev + tok
        elif tok.isdigit() and '.' in prev:
            parts = prev.split('.')
            decimals = parts[1]
            if len(decimals) < 3:
                tokens[-1] = prev + tok
            else:
                tokens.append(tok)
        else:
            tokens.append(tok)
            
    floats = []
    for tok in tokens:
        try:
            floats.append(float(tok))
        except ValueError:
            pass
    return floats

def _resolver_quantidades_global(codigo_mit: int, floats: List[float], us_m: float, us_d: float) -> tuple:
    qty_m = 0.0
    qty_d = 0.0
    
    if len(floats) >= 5:
        qty_m = floats[0]
        qty_d = floats[1]
    elif len(floats) >= 3:
        val = floats[0]
        us_val = floats[1]
        
        is_m = False
        is_d = False
        
        if us_m > 0 and abs(val * us_m - us_val) < 0.05:
            is_m = True
        if us_d > 0 and abs(val * us_d - us_val) < 0.05:
            is_d = True
            
        if is_m and is_d:
            qty_m = val
        elif is_m:
            qty_m = val
        elif is_d:
            qty_d = val
        else:
            if us_m > 0 and us_d == 0:
                qty_m = val
            elif us_d > 0 and us_m == 0:
                qty_d = val
            else:
                qty_m = val
    elif len(floats) == 1:
        val = floats[0]
        if us_m > 0:
            qty_m = val
        else:
            qty_d = val
            
    return qty_m, qty_d

# 10. Importação de PDF do Projeto no Firestore
def importar_projeto_pdf_firestore(pdf_path: str) -> Optional[str]:
    if not os.path.exists(pdf_path):
        print(f"Erro: Arquivo PDF não encontrado em: {pdf_path}")
        return None

    # Calcular hash do arquivo para prevenção de duplicidade
    import hashlib
    sha256_hash = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    file_hash = sha256_hash.hexdigest()

    filename = os.path.basename(pdf_path)
    # Se os primeiros 7 caracteres forem dígitos, extraímos como projeto_id
    projeto_id = None
    tipo_lista = "I" # Inicial por padrão
    
    if len(filename) >= 7 and filename[:7].isdigit():
        projeto_id = filename[:7]
        # Para considerar complementar deve ter no nome do arquivo a letra C após o ID
        rest_name = filename[7:]
        if "C" in rest_name.upper():
            tipo_lista = "C"
        else:
            tipo_lista = "I"
        print(f"DEBUG: Detectado ID do projeto [{projeto_id}] e Tipo [{tipo_lista}] a partir do nome do arquivo.")

    print(f"Analisando PDF de projeto: {pdf_path}...")
    reader = PdfReader(pdf_path)
    
    titulo = "Projeto Sem Título"
    
    # { 'PS 1': { 'tipo': 'PS', 'tarefas': [...] } }
    estruturas = {}
    
    # Determinar se é projeto do tipo Geral ou poste a poste
    is_global = False
    for page in reader.pages:
        text_page = page.extract_text() or ""
        text_no_space = re.sub(r'\s+', '', text_page.upper())
        if "RELAODETAREFASDOPROJETO" in text_no_space or "RELAÇÃODETAREFASDOPROJETO" in text_no_space:
            is_global = True
            break
            
    print(f"DEBUG: Formato detectado: {'GERAL (GLOBAL)' if is_global else 'POSTE A POSTE'}")
    
    # Regex para leitura do cabeçalho do projeto
    re_projeto = re.compile(r'PROJETO\s*:\s*(.+)$', re.IGNORECASE)
    re_titulo = re.compile(r'TITULO DA OBRA\s*:\s*(.+)$', re.IGNORECASE)
    
    if is_global:
        # { codigo_mit: { 'montagem': qty_m, 'desmontagem': qty_d } }
        tarefas_gerais = {}
        
        # Regex para ler linhas de tarefa global
        re_linha_global = re.compile(r'^(\d+)\s+(\d{8})\s+(.+)$')
        modo_relacao_tarefas = False
        
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if not text:
                continue
                
            lines = text.split('\n')
            for line in lines:
                line_clean = line.strip()
                # Limpa marcas de página
                line_clean = re.sub(r'PÁGINA:\s*\d+/\d+', '', line_clean)
                line_clean = re.sub(r'PÁGINA:\s*\d+', '', line_clean).strip()
                if not line_clean:
                    continue
                    
                match_proj = re_projeto.search(line_clean)
                if match_proj and not projeto_id:
                    proj_extracted = match_proj.group(1).strip()
                    match_digits = re.match(r'^(\d{7})', proj_extracted)
                    if match_digits:
                        projeto_id = match_digits.group(1)
                    else:
                        projeto_id = proj_extracted
                    continue
                    
                # Procura pelo título
                match_tit = re.search(r'(?:T[IÍí]TULO\s+DA\s+OBRA|T[IÍí]TULO\s+DAOBRA)\s*(?::)?\s*(.+)$', line_clean, re.IGNORECASE)
                if match_tit and titulo == "Projeto Sem Título":
                    titulo = match_tit.group(1).strip()
                    continue
                    
                # Detecta início e fim da tabela de tarefas
                text_no_space = re.sub(r'\s+', '', line_clean.upper())
                if "RELAODETAREFASDOPROJETO" in text_no_space or "RELAÇÃODETAREFASDOPROJETO" in text_no_space:
                    modo_relacao_tarefas = True
                    continue
                
                if modo_relacao_tarefas:
                    if "RELAODEMATERIAISDOPROJETO" in text_no_space or "RELAÇÃODEMATERIAISDOPROJETO" in text_no_space or "TOTAL:" in line_clean.upper():
                        if "TOTAL:" in line_clean.upper():
                            modo_relacao_tarefas = False
                        continue
                        
                if modo_relacao_tarefas:
                    match_head = re_linha_global.match(line_clean)
                    if match_head:
                        code_task = int(match_head.group(2))
                        # Código MIT são os últimos 3 caracteres do código de 8 dígitos
                        codigo_mit = int(str(code_task)[-3:])
                        
                        # Buscar US para resolver quantidades
                        mit = _get_mit_info(codigo_mit)
                        us_m = mit["us_montagem"]
                        us_d = mit["us_desmontagem"]
                        
                        rest = match_head.group(3)
                        match_nums = re.search(r'\s+([\d\s,.]+)$', rest)
                        if match_nums:
                            nums_str = match_nums.group(1).strip()
                            floats = _reconstruct_floats(nums_str)
                            qty_m, qty_d = _resolver_quantidades_global(codigo_mit, floats, us_m, us_d)
                            
                            if codigo_mit not in tarefas_gerais:
                                tarefas_gerais[codigo_mit] = {"montagem": 0.0, "desmontagem": 0.0}
                            
                            tarefas_gerais[codigo_mit]["montagem"] += qty_m
                            tarefas_gerais[codigo_mit]["desmontagem"] += qty_d
    else:
        # Formato Poste a Poste original
        modo_tarefas = False
        estrutura_atual = None
        
        re_tarefas_ps = re.compile(r'TAREFAS\s+NO\s+PS\s*:\s*(\d+)', re.IGNORECASE)
        re_tarefas_trecho = re.compile(r'TAREFAS\s+NO\s+TRECHO\s*:\s*([\d\s\-]+)', re.IGNORECASE)
        
        re_tarefa_linha = re.compile(r'^\s*(\d+)\s+(\d{3,4})\s+(.+?)\s+([\d.,]+)\s+([\+\-\*]+)\s*$', re.IGNORECASE)
        re_tarefa_fallback = re.compile(r'^\s*(\d+)\s+(\d{3,4})\s+(.+?)\s+([\d.,]+)\s*$', re.IGNORECASE)

        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if not text:
                continue
                
            lines = text.split('\n')
            for line in lines:
                line_clean = line.strip()
                line_clean = re.sub(r'PÁGINA:\s*\d+/\d+', '', line_clean)
                line_clean = re.sub(r'PÁGINA:\s*\d+', '', line_clean).strip()
                if not line_clean:
                    continue
                    
                match_proj = re_projeto.search(line_clean)
                if match_proj and not projeto_id:
                    proj_extracted = match_proj.group(1).strip()
                    match_digits = re.match(r'^(\d{7})', proj_extracted)
                    if match_digits:
                        projeto_id = match_digits.group(1)
                    else:
                        projeto_id = proj_extracted
                    continue
                    
                match_tit = re_titulo.search(line_clean)
                if match_tit and titulo == "Projeto Sem Título":
                    titulo = match_tit.group(1).strip()
                    continue
                    
                match_tps = re_tarefas_ps.search(line_clean)
                if match_tps:
                    modo_tarefas = True
                    estrutura_atual = f"PS {match_tps.group(1).strip()}"
                    if estrutura_atual not in estruturas:
                        estruturas[estrutura_atual] = {"tipo": "PS", "tarefas": []}
                    continue
                    
                match_tt = re_tarefas_trecho.search(line_clean)
                if match_tt:
                    modo_tarefas = True
                    trecho_id = match_tt.group(1).strip().replace(" ", "")
                    estrutura_atual = f"Trecho {trecho_id}"
                    if estrutura_atual not in estruturas:
                        estruturas[estrutura_atual] = {"tipo": "TRECHO", "tarefas": []}
                    continue
                    
                if modo_tarefas and estrutura_atual:
                    if "MÓDULOS NO" in line_clean or "MATERIAIS NO" in line_clean:
                        modo_tarefas = False
                        continue
                        
                    match_tar = re_tarefa_linha.match(line_clean)
                    if match_tar:
                        estruturas[estrutura_atual]["tarefas"].append({
                            "codigo": int(match_tar.group(2)),
                            "quantidade": float(match_tar.group(4).replace(",", ".")),
                            "sinal": "+" if "+" in match_tar.group(5) else "-"
                        })
                    else:
                        match_fall = re_tarefa_fallback.match(line_clean)
                        if match_fall:
                            codigo_mit = int(match_fall.group(2))
                            if codigo_mit >= 50 and codigo_mit <= 2000:
                                sinal_norm = "-" if "retirada" in line_clean.lower() or "remoc" in line_clean.lower() else "+"
                                estruturas[estrutura_atual]["tarefas"].append({
                                    "codigo": codigo_mit,
                                    "quantidade": float(match_fall.group(4).replace(",", ".")),
                                    "sinal": sinal_norm
                                })

    if not projeto_id:
        projeto_id = f"PROJ-{int(datetime.datetime.now().timestamp())}"
        
    print(f"Projeto Extraído: {projeto_id} - {titulo} | Lista: {tipo_lista} | Geral: {is_global}")
    
    # Obter dados do projeto existente se houver
    proj_ref = BASE_DOC_PATH.collection("projetos").document(projeto_id)
    proj_doc = proj_ref.get()
    projeto_existente = proj_doc.to_dict() if proj_doc.exists else None

    if projeto_existente:
        # Verificar se este arquivo/hash já foi importado
        arquivos_importados = projeto_existente.get("arquivos_importados", [])
        for arq in arquivos_importados:
            if arq.get("hash") == file_hash or arq.get("nome") == filename:
                raise HTTPException(
                    status_code=409,
                    detail=f"Este arquivo '{filename}' (ou uma cópia idêntica) já foi importado para o projeto {projeto_id} em {arq.get('data_importacao')}."
                )
                
        if tipo_lista == "I":
            # Verificar se já existe alguma lista Inicial ("I") importada
            tem_inicial = any(arq.get("tipo") == "I" for arq in arquivos_importados)
            if tem_inicial:
                raise HTTPException(
                    status_code=409,
                    detail=f"O projeto {projeto_id} já possui uma lista inicial cadastrada. Para adicionar mais tarefas ou alterar quantidades, envie uma lista complementar (contendo a letra 'C' no nome do arquivo)."
                )

    # Construir ou atualizar arquivos_importados
    novo_arquivo_info = {
        "nome": filename,
        "hash": file_hash,
        "tipo": tipo_lista,
        "data_importacao": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    arquivos_importados = projeto_existente.get("arquivos_importados", []) if projeto_existente else []
    if not any(arq.get("hash") == file_hash or arq.get("nome") == filename for arq in arquivos_importados):
        arquivos_importados.append(novo_arquivo_info)

    # Obter contadores de IDs
    counter_ref = BASE_DOC_PATH.collection("counters").document("global")
    counter_doc = counter_ref.get()
    if counter_doc.exists:
        c_data = counter_doc.to_dict()
        last_est_id = c_data.get("last_structure_id", 0)
        last_task_id = c_data.get("last_task_id", 0)
    else:
        last_est_id = 0
        last_task_id = 0

    if is_global:
        # 1. Calcular totais previstos para gravação/mesclagem
        totais_previstos = {}
        for cod_mit, qts in tarefas_gerais.items():
            cod_str = str(cod_mit)
            totais_previstos[cod_str] = {
                "montagem": round(qts["montagem"], 2),
                "desmontagem": round(qts["desmontagem"], 2)
            }
            
        if projeto_existente:
            # Mesclar totais_previstos
            existing_previstos = projeto_existente.get("totais_previstos", {})
            merged_previstos = {}
            for c_str, vals in existing_previstos.items():
                merged_previstos[c_str] = {
                    "montagem": float(vals.get("montagem", 0.0)),
                    "desmontagem": float(vals.get("desmontagem", 0.0))
                }
            for c_str, vals in totais_previstos.items():
                if c_str not in merged_previstos:
                    merged_previstos[c_str] = {"montagem": 0.0, "desmontagem": 0.0}
                merged_previstos[c_str]["montagem"] = round(merged_previstos[c_str]["montagem"] + vals["montagem"], 2)
                merged_previstos[c_str]["desmontagem"] = round(merged_previstos[c_str]["desmontagem"] + vals["desmontagem"], 2)
            totais_previstos = merged_previstos
            if titulo == "Projeto Sem Título" and "titulo" in projeto_existente:
                titulo = projeto_existente["titulo"]
                
        # Buscar ou criar a estrutura Geral
        est_geral_id = None
        est_geral_data = None
        
        if projeto_existente:
            est_query = BASE_DOC_PATH.collection("estruturas")\
                .where("projeto_id", "==", projeto_id)\
                .where("identificador", "==", "Geral").stream()
            for doc in est_query:
                est_geral_id = doc.id
                est_geral_data = doc.to_dict()
                break
                
        if not est_geral_id:
            last_est_id += 1
            est_geral_id = str(last_est_id)
            est_geral_data = {
                "id": int(est_geral_id),
                "projeto_id": projeto_id,
                "identificador": "Geral",
                "tipo": "LOTE",
                "descricao_resumida": "Geral",
                "tarefas": []
            }
            
        # Mesclar tarefas da estrutura Geral
        tarefas_dict = {} # { (codigo, sinal): { 'id': task_id, 'quantidade': qtde } }
        for t in est_geral_data.get("tarefas", []):
            tarefas_dict[(t["codigo"], t["sinal"])] = {
                "id": t["id"],
                "quantidade": float(t["quantidade"])
            }
            
        for cod_mit, qts in tarefas_gerais.items():
            if qts["montagem"] > 0:
                key = (cod_mit, "+")
                if key in tarefas_dict:
                    tarefas_dict[key]["quantidade"] = round(tarefas_dict[key]["quantidade"] + qts["montagem"], 3)
                else:
                    last_task_id += 1
                    tarefas_dict[key] = {
                        "id": last_task_id,
                        "quantidade": round(qts["montagem"], 3)
                    }
            if qts["desmontagem"] > 0:
                key = (cod_mit, "-")
                if key in tarefas_dict:
                    tarefas_dict[key]["quantidade"] = round(tarefas_dict[key]["quantidade"] + qts["desmontagem"], 3)
                else:
                    last_task_id += 1
                    tarefas_dict[key] = {
                        "id": last_task_id,
                        "quantidade": round(qts["desmontagem"], 3)
                    }
                    
        # Reconverte tarefas_dict para lista
        tarefas_db = []
        for (cod_mit, sinal), t_info in tarefas_dict.items():
            tarefas_db.append({
                "id": t_info["id"],
                "codigo": cod_mit,
                "quantidade": t_info["quantidade"],
                "sinal": sinal
            })
            
        est_geral_data["tarefas"] = tarefas_db
        
        # Gravar projeto e estrutura Geral no Firestore
        proj_ref.set({
            "id": projeto_id,
            "titulo": titulo,
            "data_importacao": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "totais_previstos": totais_previstos,
            "formato": "GERAL",
            "arquivos_importados": arquivos_importados
        })
        
        BASE_DOC_PATH.collection("estruturas").document(est_geral_id).set(est_geral_data)
        
        # Gravar contadores
        counter_ref.set({
            "last_structure_id": last_est_id,
            "last_task_id": last_task_id
        }, merge=True)
        
        print(f"Importação Geral Concluída! {projeto_id} gravado no Firestore.")
        return projeto_id
        
    else:
        # Formato Poste a Poste: Calcular totais_previstos
        totais_previstos = {}
        for est_nome, est_dados in estruturas.items():
            for tar in est_dados["tarefas"]:
                cod_str = str(tar["codigo"])
                tipo_us = "montagem" if tar["sinal"] == "+" else "desmontagem"
                qtde = tar["quantidade"]
                
                if cod_str not in totais_previstos:
                    totais_previstos[cod_str] = {"montagem": 0.0, "desmontagem": 0.0}
                totais_previstos[cod_str][tipo_us] += qtde
                
        # Arredondar
        for c in totais_previstos:
            totais_previstos[c]["montagem"] = round(totais_previstos[c]["montagem"], 2)
            totais_previstos[c]["desmontagem"] = round(totais_previstos[c]["desmontagem"], 2)

        if projeto_existente:
            # Mesclar totais_previstos
            existing_previstos = projeto_existente.get("totais_previstos", {})
            merged_previstos = {}
            for c_str, vals in existing_previstos.items():
                merged_previstos[c_str] = {
                    "montagem": float(vals.get("montagem", 0.0)),
                    "desmontagem": float(vals.get("desmontagem", 0.0))
                }
            for c_str, vals in totais_previstos.items():
                if c_str not in merged_previstos:
                    merged_previstos[c_str] = {"montagem": 0.0, "desmontagem": 0.0}
                merged_previstos[c_str]["montagem"] = round(merged_previstos[c_str]["montagem"] + vals["montagem"], 2)
                merged_previstos[c_str]["desmontagem"] = round(merged_previstos[c_str]["desmontagem"] + vals["desmontagem"], 2)
            totais_previstos = merged_previstos
            if titulo == "Projeto Sem Título" and "titulo" in projeto_existente:
                titulo = projeto_existente["titulo"]

        # Buscar estruturas existentes se for Complementar
        existing_estruturas = {}
        if projeto_existente:
            est_query = BASE_DOC_PATH.collection("estruturas").where("projeto_id", "==", projeto_id).stream()
            for doc in est_query:
                d = doc.to_dict()
                existing_estruturas[d["identificador"]] = {"doc_id": doc.id, "data": d}

        proj_ref.set({
            "id": projeto_id,
            "titulo": titulo,
            "data_importacao": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "totais_previstos": totais_previstos,
            "formato": "DETALHADO",
            "arquivos_importados": arquivos_importados
        })

        batch = db.batch()
        batch_count = 0
        
        for est_nome, est_dados in estruturas.items():
            est_id_str = None
            est_data = None
            
            if est_nome in existing_estruturas:
                est_id_str = existing_estruturas[est_nome]["doc_id"]
                est_data = existing_estruturas[est_nome]["data"]
            else:
                last_est_id += 1
                est_id_str = str(last_est_id)
                est_data = {
                    "id": int(est_id_str),
                    "projeto_id": projeto_id,
                    "identificador": est_nome,
                    "tipo": est_dados["tipo"],
                    "descricao_resumida": est_nome,
                    "tarefas": []
                }
                
            # Mesclar tarefas
            tarefas_dict = {}
            for t in est_data.get("tarefas", []):
                tarefas_dict[(t["codigo"], t["sinal"])] = {
                    "id": t["id"],
                    "quantidade": float(t["quantidade"])
                }
                
            for t in est_dados["tarefas"]:
                key = (t["codigo"], t["sinal"])
                if key in tarefas_dict:
                    tarefas_dict[key]["quantidade"] = round(tarefas_dict[key]["quantidade"] + t["quantidade"], 3)
                else:
                    last_task_id += 1
                    tarefas_dict[key] = {
                        "id": last_task_id,
                        "quantidade": round(t["quantidade"], 3)
                    }
                    
            tarefas_db = []
            for (cod, sinal), t_info in tarefas_dict.items():
                tarefas_db.append({
                    "id": t_info["id"],
                    "codigo": cod,
                    "quantidade": t_info["quantidade"],
                    "sinal": sinal
                })
                
            est_data["tarefas"] = tarefas_db
            
            est_ref = BASE_DOC_PATH.collection("estruturas").document(est_id_str)
            batch.set(est_ref, est_data)
            batch_count += 1
            
            if batch_count == 400:
                batch.commit()
                batch = db.batch()
                batch_count = 0
                
        if batch_count > 0:
            batch.commit()
            
        counter_ref.set({
            "last_structure_id": last_est_id,
            "last_task_id": last_task_id
        }, merge=True)
        
        print(f"Importação Poste-a-Poste Concluída! {projeto_id} gravado/mesclado.")
        return projeto_id

# 11. Obter Resumo de Progresso e Saldo Físico-Financeiro do Projeto
def obter_resumo_projeto_db(projeto_id: str) -> dict:
    proj_doc = BASE_DOC_PATH.collection("projetos").document(projeto_id).get()
    if not proj_doc.exists:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
        
    proj_data = proj_doc.to_dict()
    totais_previstos = proj_data.get("totais_previstos", {})
    
    # Query lançamentos para este projeto
    lancamentos_query = BASE_DOC_PATH.collection("lancamentos").where("projeto_id", "==", projeto_id).stream()
    
    totais_realizados = {}
    itens_realizados = []
    realizado_us_por_atividade = {}
    
    for doc in lancamentos_query:
        l = doc.to_dict()
        cod = str(l["atividade_codigo"])
        tipo = l["tipo"].lower() # 'montagem' ou 'desmontagem'
        qtde = float(l.get("quantidade", 0.0))
        
        # Obter US pré-calculada do lançamento
        us_lanc = l.get("us_calculada")
        if us_lanc is None:
            mit_temp = _get_mit_info(int(l["atividade_codigo"]))
            us_lanc = qtde * (mit_temp["us_montagem"] if tipo == "montagem" else mit_temp["us_desmontagem"])
            
        if cod not in totais_realizados:
            totais_realizados[cod] = {"montagem": 0.0, "desmontagem": 0.0}
            realizado_us_por_atividade[cod] = 0.0
            
        totais_realizados[cod][tipo] += qtde
        realizado_us_por_atividade[cod] += us_lanc
        
        if l.get("estrutura_id") is not None:
            itens_realizados.append({
                "estrutura_id": int(l["estrutura_id"]),
                "atividade_codigo": int(l["atividade_codigo"]),
                "tipo": l["tipo"].upper()
            })
        
    # Calcular US totais previstas e realizadas
    previsto_us = 0.0
    realizado_us = 0.0
    
    # Carregar cache MIT
    _get_mit_info(0)
    
    # Processar totais para retorno formatado
    atividades_resumo = []
    chaves_atividades = set(list(totais_previstos.keys()) + list(totais_realizados.keys()))
    
    for cod_str in chaves_atividades:
        cod = int(cod_str)
        mit = _get_mit_info(cod)
        
        prev = totais_previstos.get(cod_str, {"montagem": 0.0, "desmontagem": 0.0})
        real = totais_realizados.get(cod_str, {"montagem": 0.0, "desmontagem": 0.0})
        
        # Calcular US prevista
        p_m_us = prev["montagem"] * mit["us_montagem"]
        p_d_us = prev["desmontagem"] * mit["us_desmontagem"]
        previsto_us += p_m_us + p_d_us
        
        # Obter US realizada do acumulado pré-calculado
        r_us_total = realizado_us_por_atividade.get(cod_str, 0.0)
        realizado_us += r_us_total
        
        if mit.get("calculo_dinamico"):
            r_m_us = r_us_total if real["montagem"] > 0 else 0.0
            r_d_us = r_us_total if real["desmontagem"] > 0 and real["montagem"] == 0 else 0.0
        else:
            r_m_us = real["montagem"] * mit["us_montagem"]
            r_d_us = real["desmontagem"] * mit["us_desmontagem"]
        
        atividades_resumo.append({
            "codigo": cod,
            "descricao": mit.get("descricao", ""),
            "forma_pagamento": mit.get("forma_pagamento", "UNIDADE"),
            "previsto": prev,
            "realizado": {
                "montagem": round(real["montagem"], 2),
                "desmontagem": round(real["desmontagem"], 2)
            },
            "us_montagem": mit["us_montagem"],
            "us_desmontagem": mit["us_desmontagem"],
            "previsto_us": round(p_m_us + p_d_us, 2),
            "realizado_us": round(r_us_total, 2)
        })
        
    progresso = (realizado_us / previsto_us * 100) if previsto_us > 0 else 0.0
    
    # Ordenar resumo pelo código de atividade
    atividades_resumo = sorted(atividades_resumo, key=lambda x: x["codigo"])
    
    return {
        "id": proj_data["id"],
        "titulo": proj_data["titulo"],
        "data_importacao": proj_data["data_importacao"],
        "progresso_geral": round(progresso, 2),
        "previsto_us": round(previsto_us, 2),
        "realizado_us": round(realizado_us, 2),
        "atividades": atividades_resumo,
        "itens_realizados": itens_realizados,
        "arquivos_importados": proj_data.get("arquivos_importados", [])
    }

# 12. Atualizar Descrição/Título do Projeto no Firestore
def atualizar_titulo_projeto_db(projeto_id: str, novo_titulo: str):
    proj_ref = BASE_DOC_PATH.collection("projetos").document(projeto_id)
    if not proj_ref.get().exists:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    proj_ref.update({"titulo": novo_titulo})
    
    # Atualizar cache local
    global _project_cache
    if "_project_cache" in globals():
        _project_cache[projeto_id] = novo_titulo

# 13. Salvar alterações em uma atividade do MIT no Firestore
def atualizar_atividade_mit_db(codigo: int, payload: dict):
    doc_ref = BASE_DOC_PATH.collection("atividades_mit").document(str(codigo))
    
    data = {
        "codigo": int(codigo),
        "tarefa": payload.get("tarefa", ""),
        "categoria": payload.get("categoria", ""),
        "forma_pagamento": payload.get("forma_pagamento", "UNIDADE"),
        "descricao": payload.get("descricao", ""),
        "us_montagem": float(payload.get("us_montagem", 0.0)),
        "us_desmontagem": float(payload.get("us_desmontagem", 0.0)),
        "calculo_dinamico": bool(payload.get("calculo_dinamico", False)),
        "tipo_calculo": payload.get("tipo_calculo") if payload.get("calculo_dinamico") else None,
        "ativo": bool(payload.get("ativo", True))
    }
    
    doc_ref.set(data)
    
    # Limpar/recarregar no cache local em memória
    global _mit_cache
    if _mit_cache:
        _mit_cache[codigo] = data

def excluir_atividade_mit_db(codigo: int):
    doc_ref = BASE_DOC_PATH.collection("atividades_mit").document(str(codigo))
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="Atividade não encontrada no MIT.")
    doc_ref.delete()
    
    global _mit_cache
    if _mit_cache and codigo in _mit_cache:
        del _mit_cache[codigo]


