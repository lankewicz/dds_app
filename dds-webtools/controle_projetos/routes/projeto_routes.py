import os
import shutil
import fitz
import re
from typing import List, Optional
from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from controle_projetos.firestore_service import (
    listar_projetos_db,
    listar_estruturas_db,
    listar_tarefas_estrutura_db,
    pesquisar_atividades_db,
    lancar_poste_db,
    lancar_lote_db,
    obter_dashboard_semanal_db,
    listar_lancamentos_db,
    importar_projeto_pdf_firestore,
    obter_resumo_projeto_db,
    BASE_DOC_PATH
)

# Configura o diretório de templates relativo a este arquivo
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(base_dir, "templates"))

router = APIRouter(prefix="/controle-projetos")

UPLOAD_DIR = os.path.join(base_dir, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

class EditarProjetoPayload(BaseModel):
    titulo: str

# Pydantic models for request bodies from mobile client
class LancamentoPostePayload(BaseModel):
    equipe_numero: int
    data_execucao: str
    projeto_id: str
    estrutura_id: int
    tarefas_completadas: List[int]

class ItemLote(BaseModel):
    codigo: int
    quantidade: float
    tipo: str
    elementos: Optional[int] = None
    distancia: Optional[float] = None
    horas: Optional[float] = None

class LancamentoLotePayload(BaseModel):
    equipe_numero: int
    data_execucao: str
    projeto_id: Optional[str] = None
    itens: List[ItemLote]

# 0. Rota para renderizar a interface HTML principal
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def ver_controle_projetos(request: Request):
    user_email = request.headers.get("X-Portal-User")
    return templates.TemplateResponse("index_projetos.html", {
        "request": request,
        "user_email": user_email
    })

# 1. Endpoint de Carga/Importação de PDF de Projeto
@router.post("/api/projetos/importar")
async def importar_projeto(file: UploadFile = File(...)):
    temp_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        projeto_id = importar_projeto_pdf_firestore(temp_path)
        if not projeto_id:
            raise HTTPException(status_code=400, detail="Falha ao extrair dados do PDF do projeto.")
            
        # Obter detalhes do projeto importado
        proj_doc = BASE_DOC_PATH.collection("projetos").document(projeto_id).get()
        proj = proj_doc.to_dict()
        
        return {
            "sucesso": True,
            "projeto_id": proj["id"],
            "titulo": proj["titulo"],
            "data_importacao": proj["data_importacao"],
            "formato": proj.get("formato", "DETALHADO")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno de importação: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# 1.1 Endpoint de Edição do Título/Descrição do Projeto
@router.put("/api/projetos/{projeto_id}")
def editar_projeto_titulo(projeto_id: str, payload: EditarProjetoPayload):
    try:
        from controle_projetos.firestore_service import atualizar_titulo_projeto_db
        atualizar_titulo_projeto_db(projeto_id, payload.titulo)
        return {"sucesso": True}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. Listar Todos os Projetos
@router.get("/api/projetos")
def listar_projetos():
    try:
        return listar_projetos_db()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. Listar Estruturas de um Projeto
@router.get("/api/projetos/{projeto_id}/estruturas")
def listar_estruturas(projeto_id: str):
    try:
        return listar_estruturas_db(projeto_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 4. Listar Tarefas de uma Estrutura (do Projeto)
@router.get("/api/estruturas/{estrutura_id}/tarefas")
def listar_tarefas_estrutura(estrutura_id: int):
    try:
        return listar_tarefas_estrutura_db(estrutura_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 5. Pesquisar Atividades do MIT 163108
@router.get("/api/atividades")
def pesquisar_atividades(q: Optional[str] = None):
    try:
        return pesquisar_atividades_db(q)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 6. Registrar Lançamento Detalhado por Poste (Abordagem A)
@router.post("/api/lancamento/poste")
def lancar_poste(payload: LancamentoPostePayload):
    try:
        return lancar_poste_db(
            equipe_numero=payload.equipe_numero,
            data_execucao=payload.data_execucao,
            projeto_id=payload.projeto_id,
            estrutura_id=payload.estrutura_id,
            tarefas_completadas=payload.tarefas_completadas
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 7. Registrar Lançamento Rápido por Lote (Abordagem B)
@router.post("/api/lancamento/lote")
def lancar_lote(payload: LancamentoLotePayload):
    try:
        # Converter payload de itens para formato de lista de dicts
        itens_dict = [it.dict() for it in payload.itens]
        return lancar_lote_db(
            equipe_numero=payload.equipe_numero,
            data_execucao=payload.data_execucao,
            projeto_id=payload.projeto_id,
            itens=itens_dict
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 8. Obter Consolidado Gráfico Semanal (Equipes 1 a 8)
@router.get("/api/dashboard/semanal")
def obter_dashboard_semanal(semana: Optional[str] = None):
    try:
        return obter_dashboard_semanal_db(semana)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 9. Listar últimos lançamentos com descrição formatada
@router.get("/api/lancamentos")
def listar_lancamentos(limite: int = 50):
    try:
        return listar_lancamentos_db(limite)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 10. Obter resumo consolidado (saldo físico-financeiro e US) de um projeto
@router.get("/api/projetos/{projeto_id}/resumo")
def obter_resumo_projeto(projeto_id: str):
    try:
        return obter_resumo_projeto_db(projeto_id)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class EditarMitPayload(BaseModel):
    tarefa: str
    forma_pagamento: str
    descricao: str
    us_montagem: float
    us_desmontagem: float

# 11. Salvar alterações em uma atividade do MIT
@router.put("/api/atividades/{codigo}")
def editar_atividade_mit(codigo: int, payload: EditarMitPayload):
    try:
        from controle_projetos.firestore_service import atualizar_atividade_mit_db
        atualizar_atividade_mit_db(codigo, payload.dict())
        return {"sucesso": True}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ConfirmarMitPayload(BaseModel):
    codigo: int
    tarefa: str
    categoria: str
    forma_pagamento: str
    descricao: str
    us_montagem: float
    us_desmontagem: float
    calculo_dinamico: Optional[bool] = False
    tipo_calculo: Optional[str] = None
    ativo: Optional[bool] = True
    tipo_equipe: Optional[str] = "CONSTRUCAO"

# 12. Rota HTML para revisão do MIT
@router.get("/revisar-mit", response_class=HTMLResponse)
def ver_revisao_mit(request: Request):
    user_email = request.headers.get("X-Portal-User")
    return templates.TemplateResponse("revisar_mit.html", {
        "request": request,
        "user_email": user_email
    })

# 13. API para listar atividades pendentes e salvas
@router.get("/api/mit-import/pendentes")
def listar_mit_pendentes(equipe: str = "CONSTRUCAO"):
    try:
        import json
        from controle_projetos.firestore_service import BASE_DOC_PATH
        
        collection_name = "atividades_mit"
        if equipe == "EP":
            collection_name = "atividades_mit_ep"
        elif equipe == "LV":
            collection_name = "atividades_mit_lv"
        elif equipe == "STC":
            collection_name = "atividades_mit_stc"

        # 1. Carregar atividades cadastradas no Firestore
        cadastradas = {}
        docs = BASE_DOC_PATH.collection(collection_name).stream()
        for d in docs:
            dict_data = d.to_dict()
            cadastradas[dict_data["codigo"]] = dict_data
            
        # 2. Determinar fonte JSON e carregar dados estruturados
        parsed_data = []
        if equipe in ("EP", "LV"):
            # Ler o JSON de manutenção (MIT 160904)
            caminhos_tentados = [
                r"d:\programas\DDS\catalogo_mit_copel_bdo_flat_validado.json",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "catalogo_mit_copel_bdo_flat_validado.json"),
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "catalogo_mit_copel_bdo_flat_validado.json"),
                os.path.join(os.getcwd(), "catalogo_mit_copel_bdo_flat_validado.json"),
                os.path.abspath("catalogo_mit_copel_bdo_flat_validado.json")
            ]
            json_path = None
            for path in caminhos_tentados:
                if os.path.exists(path):
                    json_path = path
                    break
            
            if json_path:
                with open(json_path, "r", encoding="utf-8") as f:
                    raw_wrapper = json.load(f)
                raw_manutencao = raw_wrapper.get("servicos", [])
                
                # Mapear formato flat para o padrão com us_montagem e us_desmontagem
                for item in raw_manutencao:
                    # Se for equipe LV, opcionalmente mostramos apenas tarefas que possuem códigos LV
                    possui_lv = any("LV" in x.get("codigo_pm", "") for x in item.get("codigos_pm", []))
                    if equipe == "LV" and not possui_lv:
                        continue
                        
                    codigo = int(item["codigo"])
                    us_montagem = 0.0
                    us_desmontagem = 0.0
                    for c_pm in item.get("codigos_pm", []):
                        pm_code = c_pm.get("codigo_pm", "")
                        us_val = c_pm.get("us", 0.0)
                        if "M" in pm_code:
                            us_montagem = us_val
                        elif "D" in pm_code:
                            us_desmontagem = us_val
                    
                    parsed_data.append({
                        "codigo": codigo,
                        "tarefa": item.get("nome_curto", ""),
                        "categoria": item.get("secao", "Geral"),
                        "forma_pagamento": item.get("unidade_medida_inferida", "UNIDADE").upper(),
                        "descricao_detalhada": item.get("descricao_detalhada", ""),
                        "us_montagem": us_montagem,
                        "us_desmontagem": us_desmontagem,
                        "raw_text": f"Códigos Copel: {', '.join([x.get('codigo_pm','') for x in item.get('codigos_pm',[])])}"
                    })
        elif equipe == "STC":
            # Sem JSON baseline, carrega apenas o que estiver no Firestore
            pass
        else:
            # Construção: parsed_mit_v2.json
            caminhos_tentados = [
                r"d:\programas\DDS\parsed_mit_v2.json",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "parsed_mit_v2.json"),
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "parsed_mit_v2.json"),
                os.path.join(os.getcwd(), "parsed_mit_v2.json"),
                os.path.abspath("parsed_mit_v2.json")
            ]
            json_path = None
            for path in caminhos_tentados:
                if os.path.exists(path):
                    json_path = path
                    break
            
            if json_path:
                with open(json_path, "r", encoding="utf-8") as f:
                    parsed_data = json.load(f)
            
        # 3. Anotar cada item com o estado de salvamento no Firestore
        ret = []
        codigos_processados = set()
        for item in parsed_data:
            cod = item["codigo"]
            codigos_processados.add(cod)
            if cod in cadastradas:
                item["salvo"] = True
                item["tarefa"] = cadastradas[cod].get("tarefa", item["tarefa"])
                item["categoria"] = cadastradas[cod].get("categoria", item["categoria"])
                item["forma_pagamento"] = cadastradas[cod].get("forma_pagamento", item["forma_pagamento"])
                item["descricao_detalhada"] = cadastradas[cod].get("descricao", item["descricao_detalhada"])
                item["us_montagem"] = cadastradas[cod].get("us_montagem", item["us_montagem"])
                item["us_desmontagem"] = cadastradas[cod].get("us_desmontagem", item["us_desmontagem"])
                item["calculo_dinamico"] = cadastradas[cod].get("calculo_dinamico", False)
                item["tipo_calculo"] = cadastradas[cod].get("tipo_calculo", None)
                item["ativo"] = cadastradas[cod].get("ativo", True)
            else:
                item["salvo"] = False
                item["calculo_dinamico"] = False
                item["tipo_calculo"] = None
                item["ativo"] = True
            ret.append(item)
            
        # Adicionar novos criados apenas no Firestore
        for cod, cad in cadastradas.items():
            if cod not in codigos_processados:
                ret.append({
                    "codigo": cod,
                    "tarefa": cad.get("tarefa", ""),
                    "categoria": cad.get("categoria", ""),
                    "forma_pagamento": cad.get("forma_pagamento", "UNIDADE"),
                    "descricao_detalhada": cad.get("descricao", ""),
                    "us_montagem": cad.get("us_montagem", 0.0),
                    "us_desmontagem": cad.get("us_desmontagem", 0.0),
                    "calculo_dinamico": cad.get("calculo_dinamico", False),
                    "tipo_calculo": cad.get("tipo_calculo", None),
                    "ativo": cad.get("ativo", True),
                    "salvo": True,
                    "raw_text": "Item incluído manualmente"
                })
                
        return ret
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 14. API para confirmar e salvar um item no Firestore
@router.post("/api/mit-import/confirmar")
def confirmar_item_mit(payload: ConfirmarMitPayload):
    try:
        from controle_projetos.firestore_service import atualizar_atividade_mit_db
        atualizar_atividade_mit_db(payload.codigo, payload.dict(), payload.tipo_equipe)
        return {"sucesso": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 15. API para excluir uma atividade do MIT
@router.delete("/api/atividades/{codigo}")
def deletar_atividade_mit(codigo: int):
    try:
        from controle_projetos.firestore_service import excluir_atividade_mit_db
        excluir_atividade_mit_db(codigo)
        return {"sucesso": True}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# ROTAS PARA O CATÁLOGO DE ESTRUTURAS PADRÃO
# ==========================================

class EstruturaAtividadesPayload(BaseModel):
    atividades: List[int]

# 16. Rota HTML para gerenciar o catálogo de estruturas padrão
@router.get("/estruturas", response_class=HTMLResponse)
def ver_catalogo_estruturas(request: Request):
    user_email = request.headers.get("X-Portal-User")
    return templates.TemplateResponse("revisar_estruturas.html", {
        "request": request,
        "user_email": user_email
    })

# 17. API para listar todas as estruturas padrão
@router.get("/api/estruturas")
def listar_estruturas_padrao(q: Optional[str] = None, rede: Optional[str] = None):
    try:
        estruturas = []
        docs = BASE_DOC_PATH.collection("estruturas_padrao").stream()
        for doc in docs:
            est = doc.to_dict()
            estruturas.append(est)
            
        # Filtros
        if rede:
            estruturas = [e for e in estruturas if e.get("tipo_rede") == rede]
        if q:
            q_clean = q.strip().lower()
            estruturas = [e for e in estruturas if q_clean in e.get("nome", "").lower() or q_clean in e.get("tipo_rede", "").lower()]
            
        # Ordenação por tipo de rede e nome
        estruturas = sorted(estruturas, key=lambda x: (x.get("tipo_rede", ""), x.get("nome", "")))
        return estruturas
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 18. API para obter detalhes de uma estrutura padrão e suas atividades do MIT
@router.get("/api/estruturas/{doc_id}")
def obter_detalhes_estrutura_padrao(doc_id: str):
    try:
        doc = BASE_DOC_PATH.collection("estruturas_padrao").document(doc_id).get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Estrutura padrão não encontrada.")
            
        est = doc.to_dict()
        
        # Carregar detalhes de cada atividade do MIT associada
        atividades_detalhes = []
        for cod in est.get("atividades", []):
            mit_info = _get_mit_info(cod)
            atividades_detalhes.append(mit_info)
            
        est["atividades_detalhes"] = atividades_detalhes
        return est
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 19. API para atualizar as atividades MIT de uma estrutura padrão
@router.post("/api/estruturas/{doc_id}/atividades")
def atualizar_atividades_estrutura_padrao(doc_id: str, payload: EstruturaAtividadesPayload):
    try:
        doc_ref = BASE_DOC_PATH.collection("estruturas_padrao").document(doc_id)
        if not doc_ref.get().exists:
            raise HTTPException(status_code=404, detail="Estrutura padrão não encontrada.")
            
        doc_ref.update({
            "atividades": payload.atividades
        })
        return {"sucesso": True}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 20. API para excluir uma estrutura padrão
@router.delete("/api/estruturas/{doc_id}")
def deletar_estrutura_padrao(doc_id: str):
    try:
        doc_ref = BASE_DOC_PATH.collection("estruturas_padrao").document(doc_id)
        if not doc_ref.get().exists:
            raise HTTPException(status_code=404, detail="Estrutura padrão não encontrada.")
        doc_ref.delete()
        return {"sucesso": True}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class EditarEstruturaPayload(BaseModel):
    nome: str
    tipo_rede: str
    ntc: Optional[str] = ""

# 20.1 API para editar metadados de uma estrutura padrão
@router.put("/api/estruturas/{doc_id}")
def editar_estrutura_padrao(doc_id: str, payload: EditarEstruturaPayload):
    try:
        estrutura_nome = re.sub(r'[^a-zA-Z0-9-]', '', payload.nome).strip()
        tipo_rede = payload.tipo_rede.strip().upper()
        
        if not estrutura_nome:
            raise HTTPException(status_code=400, detail="Nome inválido.")
            
        new_doc_id = f"{tipo_rede}_{estrutura_nome}"
        
        old_ref = BASE_DOC_PATH.collection("estruturas_padrao").document(doc_id)
        old_snap = old_ref.get()
        if not old_snap.exists:
            raise HTTPException(status_code=404, detail="Estrutura original não encontrada.")
            
        old_data = old_snap.to_dict()
        
        # Se o doc_id mudou, precisamos garantir que o novo doc_id não colida com outra existente
        if new_doc_id != doc_id:
            new_ref = BASE_DOC_PATH.collection("estruturas_padrao").document(new_doc_id)
            if new_ref.get().exists:
                raise HTTPException(status_code=400, detail=f"A estrutura '{estrutura_nome}' já existe na categoria '{tipo_rede}'.")
                
            # Copiar dados antigos e aplicar novas alterações
            new_data = {**old_data, "id": new_doc_id, "nome": estrutura_nome, "tipo_rede": tipo_rede}
            if payload.ntc is not None:
                new_data["ntc"] = payload.ntc.strip()
                
            # Salvar o novo e apagar o antigo
            new_ref.set(new_data)
            old_ref.delete()
            
            return {"sucesso": True, "id": new_doc_id, "nome": estrutura_nome, "tipo_rede": tipo_rede}
        else:
            # Apenas atualizar os campos do documento atual
            update_data = {
                "nome": estrutura_nome,
                "tipo_rede": tipo_rede
            }
            if payload.ntc is not None:
                update_data["ntc"] = payload.ntc.strip()
            old_ref.update(update_data)
            
            return {"sucesso": True, "id": doc_id, "nome": estrutura_nome, "tipo_rede": tipo_rede}
            
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

import unicodedata
import json

# Conjuntos padrão caso o arquivo JSON de configuração não seja encontrado
PALAVRAS_TITULO = {
    "ESTRUTURA", "ESTRUTURAS", "TRANSFORMADOR", "TRANSFORMADORES",
    "MONOFASICO", "MONOFÁSICO", "TRIFASICO", "TRIFÁSICO",
    "CONVENCIONAL", "AUTOPROTEGIDO", "PARA", "RAIOS",
    "PARA-RAIOS", "SECCIONADORA", "FACA", "UNIPOLAR",
    "REDE", "LONGO", "COM", "DE", "DA", "DO", "AO",
    "AEREA", "AÉREA", "COMPACTA", "PROTEGIDA",
    "SECUNDARIA", "SECUNDÁRIA", "ISOLADA", "DISTRIBUICAO",
    "DISTRIBUIÇÃO", "MONTAGEM"
}

PALAVRAS_DESCARTE = {
    "COPEL", "COMPANHIA", "PARANAENSE", "ENERGIA", "PARANA",
    "PARANÁ", "GOVERNO", "NTC", "PAGINA", "PÁGINA", "PAGE",
    "JANEIRO", "JAN", "FEVEREIRO", "FEV", "MARCO", "MARÇO", "MAR",
    "ABRIL", "ABR", "MAIO", "MAI", "JUNHO", "JUN", "JULHO", "JUL",
    "AGOSTO", "AGO", "SETEMBRO", "SET", "OUTUBRO", "OUT", "NOVEMBRO",
    "NOV", "DEZEMBRO", "DEZ", "EXCLUSIVO", "MANUTENCAO", "MANUTENÇÃO"
}

# Tentar carregar as configurações do arquivo JSON externo para facilitar manutenção
CONFIG_WORDS_PATH = os.path.join(base_dir, "controle_projetos", "config_palavras.json")
if os.path.exists(CONFIG_WORDS_PATH):
    try:
        with open(CONFIG_WORDS_PATH, "r", encoding="utf-8") as f:
            wdata = json.load(f)
            if "palavras_titulo" in wdata:
                PALAVRAS_TITULO = set(wdata["palavras_titulo"])
            if "palavras_descarte" in wdata:
                PALAVRAS_DESCARTE = set(wdata["palavras_descarte"])
    except Exception as e:
        print(f"Aviso: erro ao carregar {CONFIG_WORDS_PATH}: {e}")

def remover_acentos(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")

def limpar_linha(texto: str) -> str:
    texto = texto.replace("\x00", " ")
    texto = texto.replace("\n", " ")
    texto = texto.replace("–", "-").replace("—", "-").replace("\x13", "-").replace("\x96", "-")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()

def normalizar_texto_base(texto: str) -> str:
    texto = limpar_linha(texto).upper()
    texto = remover_acentos(texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()

def normalizar_codigo_estrutura(texto: str) -> str:
    texto = normalizar_texto_base(texto)
    texto = re.sub(r"[^A-Z0-9\-/ ]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    partes = re.split(r"\s*-\s*", texto)
    partes = [re.sub(r"\s+", "", p.strip()) for p in partes if p.strip()]
    return "-".join(partes)

def linha_eh_ruido(linha: str) -> bool:
    l = normalizar_texto_base(linha)
    if not l or len(l) <= 1:
        return True
    if re.fullmatch(r"\d+", l):
        return True
    if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", l):
        return True
    if any(p in l.split() for p in PALAVRAS_DESCARTE):
        if not re.search(r"\b[A-Z]{1,4}\d+[A-Z0-9]*\b", l) and "-" not in l:
            return True
    return False

def candidato_tem_palavra_de_titulo(codigo: str) -> bool:
    partes = re.split(r"[- ]+", normalizar_texto_base(codigo))
    partes = [p for p in partes if p]
    return any(p in PALAVRAS_TITULO for p in partes)

def extrair_candidatos_estrutura(texto: str) -> List[tuple]:
    linhas = [limpar_linha(l) for l in texto.splitlines()]
    linhas = [l for l in linhas if l.strip()]

    padrao_composto = re.compile(
        r"\b[A-Z]{1,4}\d*[A-Z0-9]*"
        r"(?:\s*[-–—]\s*[A-Z0-9]{1,8}(?:\s+[A-Z0-9]{1,8})*)+\b",
        re.I,
    )

    padrao_simples = re.compile(
        r"\b[A-Z]{1,4}\d+[A-Z0-9]*\b",
        re.I,
    )

    candidatos = []

    for i, linha in enumerate(linhas):
        linha_norm = normalizar_texto_base(linha)
        for palavra in PALAVRAS_DESCARTE:
            linha_norm = re.sub(rf"\b{re.escape(remover_acentos(palavra.upper()))}\b", " ", linha_norm)
        linha_norm = re.sub(r"\s+", " ", linha_norm).strip()

        # Primeiro tenta códigos compostos
        for m in padrao_composto.finditer(linha_norm):
            bruto = m.group(0)
            codigo = normalizar_codigo_estrutura(bruto)
            if not codigo or candidato_tem_palavra_de_titulo(codigo) or len(codigo) > 35:
                continue
            pontuacao = 100 + i
            if "-" in codigo:
                pontuacao += 40
            if re.search(r"\d", codigo):
                pontuacao += 20
            candidatos.append((codigo, i, pontuacao))

        # Códigos simples
        for m in padrao_simples.finditer(linha_norm):
            bruto = m.group(0)
            codigo = normalizar_codigo_estrutura(bruto)
            if not codigo or candidato_tem_palavra_de_titulo(codigo) or codigo.startswith("NTC") or len(codigo) > 12:
                continue
            if codigo in {"13", "34", "138", "345", "2011", "2012", "2013", "2014", "2018", "2019", "2020"}:
                continue
            pontuacao = 80 + i
            if re.search(r"\d", codigo):
                pontuacao += 20
            candidatos.append((codigo, i, pontuacao))

    melhores = {}
    for codigo, idx, score in candidatos:
        if codigo not in melhores or score > melhores[codigo][1]:
            melhores[codigo] = (idx, score)

    return [(codigo, idx_score[0], idx_score[1]) for codigo, idx_score in melhores.items()]

def extrair_ntc(texto: str) -> Optional[str]:
    texto_norm = normalizar_texto_base(texto)
    m = re.search(r"\bNTC\s*(\d{3})\s*[- ]?\s*(\d{3})\b", texto_norm)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    m = re.search(r"\b(\d{3})\s*[- ]\s*(\d{3})\b", texto_norm)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return None

def escolher_melhor_estrutura(texto: str) -> Optional[str]:
    candidatos = extrair_candidatos_estrutura(texto)
    if not candidatos:
        return None
    candidatos.sort(key=lambda x: (x[2], x[1]), reverse=True)
    return candidatos[0][0]

def retangulos_cabecalho_direito(page) -> List[fitz.Rect]:
    w = page.rect.width
    h = page.rect.height
    proporcoes = [
        (0.55, 0.00, 1.00, 0.16),
        (0.58, 0.00, 1.00, 0.18),
        (0.60, 0.02, 1.00, 0.17),
        (0.52, 0.00, 1.00, 0.18),
        (0.50, 0.00, 1.00, 0.20),
    ]
    return [fitz.Rect(w * x0, h * y0, w * x1, h * y1) for x0, y0, x1, y1 in proporcoes]

def extract_name_and_ntc(doc, filename=""):
    import re
    import os
    if len(doc) == 0:
        return None, None
    page = doc[0]
    
    # 1. Tentar ler texto direto do cabeçalho direito usando retângulos dinâmicos
    textos_cabecalho = []
    for rect in retangulos_cabecalho_direito(page):
        t = page.get_text("text", clip=rect) or ""
        if t.strip():
            textos_cabecalho.append(t)
            
    texto_direto = "\n".join(textos_cabecalho)
    
    # Verificar se o texto obtido parece saudável/legível (ASCII/Unicode normal)
    ntc_val = extrair_ntc(texto_direto)
    if ntc_val and not any(c in texto_direto for c in "□■●"):
        estrutura = escolher_melhor_estrutura(texto_direto)
        if estrutura:
            return estrutura, ntc_val
            
    # 2. Fallback para fontes customizadas Type3 (ex: B1.pdf antigo)
    ntc_blocks = page.get_text("blocks", clip=(400, 50, 580, 80))
    if not ntc_blocks:
        ntc_blocks = page.get_text("blocks", clip=(380, 40, 590, 85))
        
    struct_blocks = page.get_text("blocks", clip=(400, 80, 580, 115))
    if not struct_blocks:
        struct_blocks = page.get_text("blocks", clip=(380, 80, 590, 120))
        
    ntc_blocks = [b for b in ntc_blocks if b[4].strip()]
    struct_blocks = [b for b in struct_blocks if b[4].strip()]
    
    if not ntc_blocks:
        return None, None
        
    if not struct_blocks:
        struct_blocks = page.get_text("blocks", clip=(350, 80, 590, 130))
        struct_blocks = [b for b in struct_blocks if b[4].strip()]
        
    if not struct_blocks:
        return None, None
        
    ntc_raw = ntc_blocks[0][4].replace("\n", "").strip()
    struct_raw = struct_blocks[-1][4].replace("\n", "").strip()
    
    mapping = {}
    unique_chars = []
    for char in ntc_raw:
        if char not in unique_chars:
            unique_chars.append(char)
            
    standard_prefix = "NTC 856 "
    for i, char in enumerate(unique_chars):
        if i < len(standard_prefix):
            mapping[char] = standard_prefix[i]
            
    ntc_decoded = "".join(mapping.get(c, "?") for c in ntc_raw).strip()
    
    struct_decoded_chars = []
    for c in struct_raw:
        struct_decoded_chars.append(mapping.get(c, None))
        
    filename_clean = re.sub(r'[^a-zA-Z0-9-]', '', os.path.splitext(filename)[0]).upper()
    if len(struct_decoded_chars) == len(filename_clean):
        for i, decoded in enumerate(struct_decoded_chars):
            if decoded is None:
                mapping[struct_raw[i]] = filename_clean[i]
                struct_decoded_chars[i] = filename_clean[i]
                
    struct_name = "".join(c if c is not None else "?" for c in struct_decoded_chars).strip()
    struct_name = re.sub(r'[^a-zA-Z0-9-]', '', struct_name)
    ntc_decoded = re.sub(r'[^a-zA-Z0-9\s-]', '', ntc_decoded)
    
    return struct_name, ntc_decoded

def aparar_margens_brancas(img, tolerancia: int = 245, margem: int = 35):
    from PIL import Image, ImageChops
    img = img.convert("RGB")
    fundo = Image.new("RGB", img.size, (255, 255, 255))
    diff = ImageChops.difference(img, fundo)
    gray = diff.convert("L")
    mask = gray.point(lambda p: 255 if p > (255 - tolerancia) else 0)
    bbox = mask.getbbox()
    if not bbox:
        return img
    left, top, right, bottom = bbox
    left = max(0, left - margem)
    top = max(0, top - margem)
    right = min(img.width, right + margem)
    bottom = min(img.height, bottom + margem)
    return img.crop((left, top, right, bottom))

# 21. API para ANALISAR padrão de estrutura em PDF (extrair metadados e gerar imagens temporárias)
@router.post("/api/estruturas/analisar")
async def analisar_estrutura_pdf(tipo_rede: str = Form(...), file: UploadFile = File(...)):
    try:
        import fitz
        import uuid
        
        pdf_bytes = await file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if len(doc) == 0:
            raise HTTPException(status_code=400, detail="PDF inválido ou vazio.")
            
        # Extrair nome e NTC do conteúdo do PDF usando nossa lógica avançada
        estrutura_nome, ntc_decoded = extract_name_and_ntc(doc, file.filename)
        
        if not estrutura_nome:
            estrutura_nome = os.path.splitext(file.filename)[0]
            ntc_decoded = ""
            
        imagens_temp_urls = []
        temp_id = str(uuid.uuid4())
        
        # Percorrer todas as páginas do PDF e renderizar em alta resolução, removendo cabeçalho e rodapé
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            
            # Renderizar página a 300 DPI
            zoom = 300 / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            from PIL import Image
            import io
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            
            width, height = img.size
            top_crop = int(height * 0.13) # Remove o quadro superior do logotipo e NTC
            bottom_crop = int(height * 0.10) # Remove a linha preta inferior e rodapé de metadados
            
            cropped_img = img.crop((0, top_crop, width, height - bottom_crop))
            cropped_img = aparar_margens_brancas(cropped_img, tolerancia=245, margem=45)
            
            img_byte_arr = io.BytesIO()
            cropped_img.save(img_byte_arr, format='PNG')
            img_bytes = img_byte_arr.getvalue()
            
            temp_filename = f"temp_{temp_id}_{page_idx + 1}.png"
            
            from monitor.services.turnos_service import DDS_BUCKET_NAME, _storage_bucket
            gcs_success = False
            temp_url = None
            if DDS_BUCKET_NAME:
                try:
                    bucket = _storage_bucket()
                    blob_name = f"estruturas/temp/{temp_filename}"
                    blob = bucket.blob(blob_name)
                    blob.upload_from_string(img_bytes, content_type="image/png")
                    try:
                        blob.make_public()
                    except Exception:
                        pass
                    temp_url = f"https://storage.googleapis.com/{DDS_BUCKET_NAME}/{blob_name}"
                    gcs_success = True
                except Exception as e:
                    print(f"Erro ao salvar desenho temporario no GCS: {e}")
                    
            if not gcs_success:
                local_dir = os.path.join(base_dir, "controle_projetos", "static", "images", "temp")
                os.makedirs(local_dir, exist_ok=True)
                out_path = os.path.join(local_dir, temp_filename)
                with open(out_path, "wb") as f:
                    f.write(img_bytes)
                temp_url = f"/controle-projetos/static/images/temp/{temp_filename}"
                
            imagens_temp_urls.append(temp_url)
            
        doc.close()
        
        return {
            "sucesso": True,
            "nome_sugerido": estrutura_nome,
            "ntc_sugerido": ntc_decoded,
            "tipo_rede_sugerido": tipo_rede,
            "imagens_temp": imagens_temp_urls
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ConfirmarEstruturaPayload(BaseModel):
    nome: str
    ntc: str
    tipo_rede: str
    imagens_temp: List[str]
    override: bool = False

# 21.1 API para CONFIRMAR a gravação final da estrutura padrão
@router.post("/api/estruturas/confirmar")
def confirmar_estrutura_pdf(payload: ConfirmarEstruturaPayload):
    try:
        estrutura_nome = re.sub(r'[^a-zA-Z0-9-]', '', payload.nome).strip()
        ntc_decoded = re.sub(r'[^a-zA-Z0-9\s-]', '', payload.ntc).strip()
        tipo_rede = payload.tipo_rede.strip().upper()
        
        doc_id = f"{tipo_rede}_{estrutura_nome}"
        doc_ref = BASE_DOC_PATH.collection("estruturas_padrao").document(doc_id)
        doc_snap = doc_ref.get()
        
        if doc_snap.exists and not payload.override:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "exists",
                    "message": f"A estrutura '{estrutura_nome}' ja existe na categoria '{tipo_rede}'. Deseja substituir?",
                    "id": doc_id,
                    "nome": estrutura_nome,
                    "tipo_rede": tipo_rede
                }
            )
            
        from monitor.services.turnos_service import DDS_BUCKET_NAME, _storage_bucket
        imagens_urls = []
        
        for idx, temp_url in enumerate(payload.imagens_temp, start=1):
            desenho_filename = f"{estrutura_nome}_desenho_{idx}.png"
            final_url = None
            
            # Se for GCS
            if DDS_BUCKET_NAME and temp_url.startswith("https://storage.googleapis.com/"):
                try:
                    bucket = _storage_bucket()
                    prefix_url = f"https://storage.googleapis.com/{DDS_BUCKET_NAME}/"
                    source_blob_name = temp_url.replace(prefix_url, "")
                    dest_blob_name = f"estruturas/{tipo_rede}/{desenho_filename}"
                    
                    source_blob = bucket.blob(source_blob_name)
                    if source_blob.exists():
                        new_blob = bucket.copy_blob(source_blob, bucket, dest_blob_name)
                        try:
                            new_blob.make_public()
                        except Exception:
                            pass
                        final_url = f"https://storage.googleapis.com/{DDS_BUCKET_NAME}/{dest_blob_name}"
                        # Deletar original temporário
                        source_blob.delete()
                    else:
                        final_url = temp_url
                except Exception as e:
                    print(f"Erro ao mover blob temporario GCS: {e}")
                    final_url = temp_url
            else:
                # Local fallback
                try:
                    temp_filename = os.path.basename(temp_url)
                    source_path = os.path.join(base_dir, "controle_projetos", "static", "images", "temp", temp_filename)
                    
                    local_dir = os.path.join(base_dir, "controle_projetos", "static", "images", "estruturas", tipo_rede)
                    os.makedirs(local_dir, exist_ok=True)
                    dest_path = os.path.join(local_dir, desenho_filename)
                    
                    if os.path.exists(source_path):
                        import shutil
                        shutil.copy(source_path, dest_path)
                        os.remove(source_path)
                        
                    final_url = f"/controle-projetos/static/images/estruturas/{tipo_rede}/{desenho_filename}"
                except Exception as e:
                    print(f"Erro ao mover arquivo temporario local: {e}")
                    final_url = temp_url
                    
            imagens_urls.append(final_url)
            
        # Gravar no Firestore
        payload_db = {
            "id": doc_id,
            "nome": estrutura_nome,
            "tipo_rede": tipo_rede,
            "imagens": imagens_urls,
            "ativo": True,
            "ntc": ntc_decoded
        }
        
        if doc_snap.exists:
            existing_data = doc_snap.to_dict()
            payload_db["atividades"] = existing_data.get("atividades", [])
            existing_imgs = existing_data.get("imagens", [])
            merged_imgs = list(set(existing_imgs + imagens_urls))
            payload_db["imagens"] = merged_imgs
            doc_ref.update(payload_db)
        else:
            payload_db["atividades"] = []
            doc_ref.set(payload_db)
            
        return {
            "sucesso": True,
            "id": doc_id,
            "nome": estrutura_nome,
            "tipo_rede": tipo_rede,
            "imagens": payload_db["imagens"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 22. API para fazer upload manual de imagem para uma estrutura padrão
@router.post("/api/estruturas/{doc_id}/imagens")
async def upload_imagem_estrutura(doc_id: str, file: UploadFile = File(...)):
    try:
        doc_ref = BASE_DOC_PATH.collection("estruturas_padrao").document(doc_id)
        doc_snap = doc_ref.get()
        if not doc_snap.exists:
            raise HTTPException(status_code=404, detail="Estrutura padrão não encontrada.")
            
        est = doc_snap.to_dict()
        tipo_rede = est.get("tipo_rede", "RDA")
        nome_estrutura = est.get("nome", "ESTRUTURA")
        
        # O nome da imagem deve ser baseado na estrutura e um sequencial
        # Ex: RDC-C1-01.png, RDC-C1-02.jpg
        # Vamos substituir sublinhados por hifens no prefixo
        prefixo = f"{tipo_rede}-{nome_estrutura}".replace("_", "-")
        
        # Calcular o proximo sequencial
        imagens_atuais = est.get("imagens", [])
        
        max_seq = 0
        for img_url in imagens_atuais:
            fname = os.path.basename(img_url)
            if fname.startswith(prefixo):
                parts = os.path.splitext(fname)[0].split('-')
                if len(parts) >= 3:
                    try:
                        seq_val = int(parts[-1])
                        if seq_val > max_seq:
                            max_seq = seq_val
                    except ValueError:
                        pass
        
        next_seq = max_seq + 1
        ext = os.path.splitext(file.filename)[1].lower() or ".png"
        new_filename = f"{prefixo}-{next_seq:02d}{ext}"
        
        # Ler bytes da imagem
        file_bytes = await file.read()
        
        # Gravação no GCS ou Local
        from monitor.services.turnos_service import DDS_BUCKET_NAME, _storage_bucket
        gcs_success = False
        img_url = None
        if DDS_BUCKET_NAME:
            try:
                bucket = _storage_bucket()
                blob_name = f"estruturas/{tipo_rede}/{new_filename}"
                blob = bucket.blob(blob_name)
                blob.upload_from_string(file_bytes, content_type=file.content_type)
                try:
                    blob.make_public()
                except Exception as pe:
                    print(f"Aviso: nao foi possivel tornar o blob publico: {pe}")
                img_url = f"https://storage.googleapis.com/{DDS_BUCKET_NAME}/{blob_name}"
                gcs_success = True
            except Exception as e:
                print(f"Erro ao salvar imagem manual no GCS: {e}")
                
        if not gcs_success:
            local_dir = os.path.join(base_dir, "controle_projetos", "static", "images", "estruturas", tipo_rede)
            os.makedirs(local_dir, exist_ok=True)
            out_path = os.path.join(local_dir, new_filename)
            with open(out_path, "wb") as f:
                f.write(file_bytes)
            img_url = f"/controle-projetos/static/images/estruturas/{tipo_rede}/{new_filename}"
            
        # Atualizar array de imagens no Firestore
        imagens_atuais.append(img_url)
        doc_ref.update({"imagens": imagens_atuais})
        
        return {"sucesso": True, "url": img_url}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 23. API para deletar uma imagem de uma estrutura padrão
class DeletarImagemPayload(BaseModel):
    url: str

@router.delete("/api/estruturas/{doc_id}/imagens")
def deletar_imagem_estrutura(doc_id: str, payload: DeletarImagemPayload):
    try:
        doc_ref = BASE_DOC_PATH.collection("estruturas_padrao").document(doc_id)
        doc_snap = doc_ref.get()
        if not doc_snap.exists:
            raise HTTPException(status_code=404, detail="Estrutura padrão não encontrada.")
            
        est = doc_snap.to_dict()
        imagens_atuais = est.get("imagens", [])
        
        target_url = payload.url
        if target_url not in imagens_atuais:
            raise HTTPException(status_code=404, detail="Imagem não associada a esta estrutura.")
            
        # Remover da lista
        imagens_atuais.remove(target_url)
        doc_ref.update({"imagens": imagens_atuais})
        
        # Opcional: Deletar o arquivo do GCS ou Local
        if not target_url.startswith("http"):
            rel_path = target_url.replace("/controle-projetos/static", "")
            rel_path = rel_path.lstrip("/").lstrip("\\")
            local_path = os.path.join(base_dir, "controle_projetos", "static", rel_path)
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except Exception as e:
                    print(f"Erro ao excluir arquivo físico: {e}")
        else:
            from monitor.services.turnos_service import DDS_BUCKET_NAME, _storage_bucket
            if DDS_BUCKET_NAME and target_url.startswith(f"https://storage.googleapis.com/{DDS_BUCKET_NAME}/"):
                try:
                    bucket = _storage_bucket()
                    blob_name = target_url.replace(f"https://storage.googleapis.com/{DDS_BUCKET_NAME}/", "")
                    blob = bucket.blob(blob_name)
                    if blob.exists():
                        blob.delete()
                except Exception as e:
                    print(f"Erro ao deletar blob do GCS: {e}")
                    
        return {"sucesso": True}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 15. API para exportar e publicar o catálogo do Firestore no Firebase Storage como JSON
@router.post("/api/mit-import/publicar")
def publicar_catalogo_mit(equipe: str = "CONSTRUCAO"):
    try:
        from controle_projetos.firestore_service import BASE_DOC_PATH
        from monitor.services.turnos_service import DDS_BUCKET_NAME, _storage_bucket
        
        if not DDS_BUCKET_NAME:
            raise HTTPException(status_code=500, detail="Bucket name do Firebase Storage não configurado.")
            
        bucket = _storage_bucket()
        
        # Determinar coleções do Firestore a exportar
        if equipe in ("EP", "LV"):
            # Para manutenção, exportamos ambas as coleções consolidadas no mesmo arquivo
            docs_ep = BASE_DOC_PATH.collection("atividades_mit_ep").stream()
            docs_lv = BASE_DOC_PATH.collection("atividades_mit_lv").stream()
            
            # Unificar
            atividades = {}
            for d in docs_ep:
                data = d.to_dict()
                atividades[data["codigo"]] = data
            for d in docs_lv:
                data = d.to_dict()
                if data["codigo"] in atividades:
                    # Garantir que se houver us de LV, mesclamos
                    atividades[data["codigo"]]["us_montagem"] = max(atividades[data["codigo"]].get("us_montagem", 0.0), data.get("us_montagem", 0.0))
                    atividades[data["codigo"]]["us_desmontagem"] = max(atividades[data["codigo"]].get("us_desmontagem", 0.0), data.get("us_desmontagem", 0.0))
                else:
                    atividades[data["codigo"]] = data
                    
            list_atividades = list(atividades.values())
            blob_name = "catalogo/catalogo_mit_manutencao.json"
        elif equipe == "STC":
            docs = BASE_DOC_PATH.collection("atividades_mit_stc").stream()
            list_atividades = [d.to_dict() for d in docs]
            blob_name = "catalogo/catalogo_mit_stc.json"
        else:
            # CONSTRUCAO
            docs = BASE_DOC_PATH.collection("atividades_mit").stream()
            list_atividades = [d.to_dict() for d in docs]
            blob_name = "catalogo/catalogo_mit_construcao.json"
            
        # Converter para JSON string
        import json
        json_content = json.dumps(list_atividades, indent=2, ensure_ascii=False)
        
        # Fazer upload para o Storage
        blob = bucket.blob(blob_name)
        blob.upload_from_string(json_content, content_type="application/json")
        
        return {"sucesso": True, "items_exportados": len(list_atividades), "caminho": blob_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


