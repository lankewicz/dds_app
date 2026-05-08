import pandas as pd

def format_approver_name(name):
    """
    Formata o nome do aprovador para o padrão: PRIMEIRO NOME + INICIAL DO ÚLTIMO.
    Ex: "SILVANA BARBOSA REZENDE" -> "SILVANA R."
    """
    if not name or pd.isna(name) or name == "-":
        return "-"
    parts = str(name).strip().split()
    first = parts[0].upper()
    if len(parts) == 1:
        return first
    last_initial = parts[-1][0].upper()
    return f"{first} {last_initial}."

def format_currency(value):
    """Formata valor numérico para string de moeda R$."""
    if value is None: return "R$ 0,00"
    return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
