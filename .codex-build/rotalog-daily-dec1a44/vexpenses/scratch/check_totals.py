import os
import sys
from google.cloud import firestore
from decimal import Decimal

# Adicionar o diretório raiz ao path
sys.path.append(r"d:\programas\DDS\dds-webtools")

# Inicializar Firestore
db = firestore.Client(project="dds-treinamentos")
docs = db.collection("vexpenses").document("data").collection("balance_requests").stream()

stats = {}
total_solicitado = Decimal(0)
total_aprovado = Decimal(0)
count = 0

for doc in docs:
    d = doc.to_dict()
    status = d.get("status", "SEM STATUS")
    val_sol = Decimal(str(d.get("valor_solicitado", 0)))
    val_apr = Decimal(str(d.get("valor_aprovado", 0)))
    
    if status not in stats:
        stats[status] = {"count": 0, "solicitado": Decimal(0), "aprovado": Decimal(0)}
    
    stats[status]["count"] += 1
    stats[status]["solicitado"] += val_sol
    stats[status]["aprovado"] += val_apr
    
    total_solicitado += val_sol
    total_aprovado += val_apr
    count += 1

print(f"Total de Registros: {count}")
print(f"Total Solicitado Geral: {total_solicitado}")
print(f"Total Aprovado Geral: {total_aprovado}")
print(f"Diferenca Total (Glosas/Reprovados): {total_solicitado - total_aprovado}")
print("-" * 30)
for status, data in stats.items():
    print(f"Status: {status}")
    print(f"  Qtd: {data['count']}")
    print(f"  Solicitado: {data['solicitado']}")
    print(f"  Aprovado: {data['aprovado']}")
    print(f"  Diferenca: {data['solicitado'] - data['aprovado']}")
