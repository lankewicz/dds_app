import json
import os
from produtividade.services.productivity_service import db, TARGET_COLLECTION

CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "filters_cache.json")

def build_filters_cache():
    """
    Varre o Firestore e cria um cache das opções de filtros disponíveis.
    """
    print("Construindo cache de filtros...")
    docs = db.collection(TARGET_COLLECTION).stream()
    
    bases = set()
    cities = set()
    agencies = set()
    contracts = set()
    teams = {} # teamKey -> displayName
    
    agency_to_cities = {} # agency -> set(cities)

    for d in docs:
        data = d.to_dict()
        base = data.get("base")
        city = data.get("cityBase")
        agencia = data.get("agency")
        contract = data.get("contract")

        if base: bases.add(base)
        if city: cities.add(city)
        if agencia: agencies.add(agencia)
        if contract: contracts.add(str(contract))
        
        # Mapeia relação
        if agencia and city:
            if agencia not in agency_to_cities:
                agency_to_cities[agencia] = set()
            agency_to_cities[agencia].add(city)
        
        tk = data.get("teamKey")
        dn = data.get("displayName")
        if tk: teams[tk] = dn or tk

    cache_data = {
        "regioes": sorted(list(bases)),
        "cidades": sorted(list(cities)),
        "agencias": sorted(list(agencies)),
        "contratos": sorted(list(contracts)),
        "agency_to_cities": {k: sorted(list(v)) for k, v in agency_to_cities.items()},
        "equipes": [{"id": k, "nome": v} for k, v in sorted(teams.items())]
    }

    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=4, ensure_ascii=False)
    
    return cache_data

def get_filters_cache():
    """
    Retorna o cache. Se não existir, constrói.
    """
    if not os.path.exists(CACHE_FILE):
        return build_filters_cache()
    
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
