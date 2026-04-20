
# =============================================================================
# Nome do arquivo : utils/date_parse.py
# Data de criação : 31/10/2025
# Função          : Funções utilitárias para parsing de mês/ano e nomes de meses PT-BR.
# Funcionalidades :
#   - parse_mes_ano(texto) -> (ano:int, mes:int)
#   - meses_pt (lista com nomes dos meses)
# =============================================================================

from __future__ import annotations
import datetime as _dt

meses_pt = [
    "janeiro","fevereiro","março","abril","maio","junho",
    "julho","agosto","setembro","outubro","novembro","dezembro"
]

_MES = {
    "JANEIRO":1,"FEVEREIRO":2,"FEV":2,"MARCO":3,"MARÇO":3,"MAR":3,
    "ABRIL":4,"ABR":4,"MAIO":5,"MAI":5,"JUNHO":6,"JUN":6,
    "JULHO":7,"JUL":7,"AGOSTO":8,"AGO":8,"SETEMBRO":9,"SET":9,
    "OUTUBRO":10,"OUT":10,"NOVEMBRO":11,"NOV":11,"DEZEMBRO":12,"DEZ":12
}

def parse_mes_ano(texto: str) -> tuple[int, int]:
    """Aceita 'junho 2025', '06/2025', '2025-06', 'jun 25' etc."""
    toks = (texto or "").replace("/", " ").replace("-", " ").split()
    ano = None; mes = None
    for t in toks:
        u = t.upper()
        if u.isdigit():
            v = int(u)
            if 1900 <= v <= 2100:
                ano = v
            elif 1 <= v <= 12 and mes is None:
                mes = v
        elif u in _MES and mes is None:
            mes = _MES[u]
    now = _dt.datetime.now()
    return (ano or now.year), (mes or now.month)
