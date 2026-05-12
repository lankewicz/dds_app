from datetime import datetime
from google.cloud import firestore
from monitor.services.firestore_client import db

TARGET_COLLECTION = "dds_producao_mensal"

def get_latest_competence():
    """
    Busca no Firestore qual é a competência (ano/mês) mais recente com dados.
    Ordenação feita em memória para evitar a necessidade de índice composto imediato.
    """
    docs = db.collection(TARGET_COLLECTION).stream()
    latest_year = 0
    latest_month = 0
    
    found = False
    for doc in docs:
        data = doc.to_dict()
        y = data.get("year", 0)
        m = data.get("monthNumber", 0)
        if y > latest_year or (y == latest_year and m > latest_month):
            latest_year = y
            latest_month = m
            found = True
            
    if found:
        return latest_year, latest_month
    return None, None

def list_productivity_data(year: int = None, month: int = None, city: str = None, region: str = None, agency: str = None, contract: str = None, start_month_key: str = None, end_month_key: str = None):
    """
    Busca os dados de produtividade filtrados por ano, mês, cidade, região (base), agência ou período.
    """
    try:
        query = db.collection(TARGET_COLLECTION)
        
        if year:
            query = query.where("year", "==", year)
        if month:
            query = query.where("monthNumber", "==", month)
        if city:
            query = query.where("cityBase", "==", city)
        if region:
            query = query.where("base", "==", region)
        if agency:
            query = query.where("agency", "==", agency)
        if contract:
            query = query.where("contract", "==", str(contract))
        
        if start_month_key and end_month_key:
            query = query.where("monthKey", ">=", start_month_key).where("monthKey", "<=", end_month_key)
            
        docs = query.stream()
        
        results = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            results.append(data)
            
        return results
    except Exception as e:
        print(f"Erro ao buscar dados no Firestore: {e}")
        return []

def get_productivity_matrix(year: int = None, city: str = None, region: str = None, agency: str = None, contract: str = None, tipo: str = None, limit_months: int = 24):
    """
    Retorna os dados formatados em matriz.
    """
    try:
        data = list_productivity_data(year=year, city=city, region=region, agency=agency, contract=contract)
        
        if not data:
            return {"months": [], "teams": [], "matrix": {}}

        months_set = set()
        teams_map = {} 
        matrix = {} 

        for d in data:
            mk = str(d.get("monthKey", "")).replace("-", "_") # Normaliza para underscore
            tk = d.get("teamKey")
            metrics = d.get("metrics", {})
            val = metrics.get("totalUs", 0)
            
            # Novas métricas detalhadas
            serv_emerg = metrics.get("emergencyServices", 0)
            serv_com = metrics.get("commercialEffective", 0) + metrics.get("commercialBlocked", 0)
            total_serv = metrics.get("totalServices", 0)
            km = metrics.get("km", 0)
            sa = metrics.get("soVar05", 0)

            months_set.add(mk)
            if tk not in teams_map:
                teams_map[tk] = {
                    "teamKey": tk,
                    "displayName": d.get("displayName", tk),
                    "cityBase": d.get("cityBase"),
                    "base": d.get("base"),
                    "agency": d.get("agency"),
                    "plate": d.get("plate"),
                    "members": d.get("members", []),
                    "contract": d.get("contract"),
                    "goal": d.get("goal"),
                    "total_sum": 0,
                    "count": 0,
                    "total_servicos": 0,
                    "total_emergenciais": 0,
                    "total_comerciais": 0,
                    "total_km": 0,
                    "total_sa": 0
                }
            
            teams_map[tk]["total_sum"] += val
            teams_map[tk]["count"] += 1
            teams_map[tk]["total_servicos"] += total_serv
            teams_map[tk]["total_emergenciais"] += serv_emerg
            teams_map[tk]["total_comerciais"] += serv_com
            teams_map[tk]["total_km"] += km
            teams_map[tk]["total_sa"] += sa
            
            if mk not in matrix:
                matrix[mk] = {}
            
            matrix[mk][tk] = {
                "val": round(val, 2),
                "servicos": total_serv,
                "emergenciais": serv_emerg,
                "comerciais": serv_com,
                "km": km,
                "sa": sa,
                "plate": d.get("plate"),
                "members": d.get("members", []),
                "agency": d.get("agency"),
                "contract": d.get("contract"),
                "displayName": d.get("displayName"),
                "goal": d.get("goal")
            }

        # Filtrar por Tipo de Equipe (Cesto / Escada)
        if tipo:
            tipo = tipo.upper()
            filtered_teams = {}
            for tk, tm in teams_map.items():
                target = tm.get("goal", {}).get("targetUs", 0) if tm.get("goal") else 0
                name = tm.get("displayName", "").upper()
                
                is_cesto = (target == 811) or ("CESTO" in name)
                is_escada = (target == 859) or ("ESCADA" in name) or (not is_cesto and target > 0)
                
                if tipo == "CESTO" and is_cesto:
                    filtered_teams[tk] = tm
                elif tipo == "ESCADA" and is_escada and not is_cesto:
                    filtered_teams[tk] = tm
            
            teams_map = filtered_teams

        # Ordenar e limitar meses
        sorted_months = sorted(list(months_set), reverse=True)[:limit_months]
        sorted_months.reverse() 
        
        # Calcular médias e ordenar equipes pela média (descendente)
        for tk in teams_map:
            tm = teams_map[tk]
            tm["average"] = tm["total_sum"] / tm["count"] if tm["count"] > 0 else 0

        sorted_teams = sorted(teams_map.values(), key=lambda x: x.get("average", 0), reverse=True)

        # Identificar Top 3 de cada mês para medalhas
        monthly_rankings = {}
        for mk, mk_data in matrix.items():
            # Filtra apenas quem está no teams_map (respeitando o filtro de tipo)
            filtered_mk = {tk: val for tk, val in mk_data.items() if tk in teams_map}
            sorted_mk = sorted(filtered_mk.items(), key=lambda x: x[1].get("val", 0), reverse=True)
            monthly_rankings[mk] = {
                "gold": sorted_mk[0][0] if len(sorted_mk) > 0 else None,
                "silver": sorted_mk[1][0] if len(sorted_mk) > 1 else None,
                "bronze": sorted_mk[2][0] if len(sorted_mk) > 2 else None
            }

        return {
            "months": sorted_months,
            "teams": sorted_teams,
            "matrix": matrix,
            "rankings": monthly_rankings
        }
    except Exception as e:
        print(f"Erro ao gerar matriz: {e}")
        return {"months": [], "teams": [], "matrix": {}, "error": str(e)}
