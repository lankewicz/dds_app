import os
import shutil
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
    user_email = request.cookies.get("user_email")
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

# 12. Rota HTML para revisão do MIT
@router.get("/revisar-mit", response_class=HTMLResponse)
def ver_revisao_mit(request: Request):
    user_email = request.cookies.get("user_email")
    return templates.TemplateResponse("revisar_mit.html", {
        "request": request,
        "user_email": user_email
    })

# 13. API para listar atividades pendentes e salvas
@router.get("/api/mit-import/pendentes")
def listar_mit_pendentes():
    try:
        import json
        from controle_projetos.firestore_service import BASE_DOC_PATH
        
        # 1. Carregar atividades cadastradas no Firestore
        cadastradas = {}
        docs = BASE_DOC_PATH.collection("atividades_mit").stream()
        for d in docs:
            dict_data = d.to_dict()
            cadastradas[dict_data["codigo"]] = dict_data
            
        # 2. Ler o JSON gerado pelo parser
        json_path = r"d:\programas\DDS\parsed_mit_v2.json"
        if not os.path.exists(json_path):
            json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "parsed_mit_v2.json")
        if not os.path.exists(json_path):
            raise HTTPException(status_code=404, detail="Arquivo parsed_mit_v2.json não encontrado. Execute o script de parse primeiro.")
            
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
        atualizar_atividade_mit_db(payload.codigo, payload.dict())
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

