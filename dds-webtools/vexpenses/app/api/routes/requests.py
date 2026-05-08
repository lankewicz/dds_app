# Finalidade: endpoints para consulta das solicitações a partir do Firestore.
from datetime import date
from fastapi import APIRouter, HTTPException, Query
from google.cloud import firestore

from app.core.firestore import db
from app.schemas.requests import BalanceRequestOut, PaginatedBalanceRequests

router = APIRouter(prefix="/solicitacoes", tags=["Solicitações"])
# Referências unificadas no Firestore
ROOT_DOC = db.collection("vexpenses").document("data")
COL_REQUESTS = ROOT_DOC.collection("balance_requests")

@router.get("", response_model=PaginatedBalanceRequests)
def list_requests(
    data_inicio: date | None = Query(default=None),
    data_fim: date | None = Query(default=None),
    status: str | None = Query(default=None),
    aprovador: str | None = Query(default=None),
    usuario: str | None = Query(default=None),
    ano: int | None = Query(default=None),
    mes: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> PaginatedBalanceRequests:
    query = COL_REQUESTS

    if data_inicio:
        query = query.where("data_solicitacao", ">=", data_inicio.isoformat())
    if data_fim:
        query = query.where("data_solicitacao", "<=", data_fim.isoformat())
    if status:
        query = query.where("status", "==", status.strip())
    if usuario:
        query = query.where("usuario_origem", "==", usuario.strip())
    if aprovador:
        query = query.where("aprovador", "==", aprovador.strip())
    if ano:
        query = query.where("ano", "==", int(ano))
    if mes:
        query = query.where("mes", "==", int(mes))

    # Agora usamos apenas a query nativa para economia de custo.
    # Se faltar um índice composto (ex: usuario + ano + mes + data_solicitacao), 
    # o Firestore lançará uma exceção.
    try:
        docs = list(query.order_by("data_solicitacao", direction=firestore.Query.DESCENDING).stream())
    except Exception as e:
        from app.core.logging import get_logger
        logger = get_logger(__name__)
        logger.warning(f"Consulta ordenada falhou (índice ausente?): {e}. Tentando fallback sem ordenação nativa.")
        try:
            # Fallback 1: Mesma query mas sem order_by (exige menos índices)
            docs = list(query.stream())
            # Ordenamos em memória para manter a experiência do usuário
            docs.sort(key=lambda x: x.to_dict().get("data_solicitacao", ""), reverse=True)
        except Exception as e2:
            logger.error(f"Falha total na consulta: {e2}")
            # Se tudo falhar, retornamos lista vazia para evitar 500 no frontend
            docs = []

    items = []
    from datetime import datetime
    for doc in docs:
        d = doc.to_dict()
        
        # Filtro de segurança em memória: validar se a data real corresponde ao filtro
        # Isso evita que dados inconsistentes no banco (ex: campo 'mes' divergente da 'data_solicitacao') "vazem"
        if ano or mes:
            try:
                dt_str = d.get("data_solicitacao", "")
                dt = datetime.fromisoformat(dt_str.split('T')[0])
                if ano and dt.year != int(ano): continue
                if mes and dt.month != int(mes): continue
            except:
                pass # Se a data for inválida, mantemos o comportamento original do Firestore

        items.append(d)

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_items = items[start:end]

    return PaginatedBalanceRequests(
        items=[BalanceRequestOut.model_validate(item) for item in paginated_items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{id_alocacao}", response_model=BalanceRequestOut)
def get_request(id_alocacao: str) -> BalanceRequestOut:
    doc = COL_REQUESTS.document(id_alocacao).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    return BalanceRequestOut.model_validate(doc.to_dict())
