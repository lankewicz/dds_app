# =============================================================================
# Nome do arquivo : core/cmd_listar.py
# Data de criação : 31/10/2025
# Função          : Implementar o comando LISTAR do DDS.
# Funcionalidades :
#   - Listar as pastas (2º nível) sob o prefixo no Storage (ex.: DDSv2/AAAA-MM - Assunto/…).
#   - Montar HTML com tabela (Data, Assunto, Ação) e link rápido para APAGAR.
#   - Enviar e-mail HTML para o solicitante.
# =============================================================================

from __future__ import annotations


from email_utils import send_response
from utils.env_config import prefix_from_env

from logger import log_manager

# Usa o mesmo cliente (bucket) do projeto
from firebase_sender import bucket
from urllib.parse import quote
from html import escape

from config import SMTP_USER
from core.listing_utils import list_pastas_2nivel, render_listar_html

def _parse_date(folder_name: str) -> datetime | None:
    """
    Extrai data do nome da pasta. Aceita:
      - 'YYYY-MM-DD - Assunto'
      - 'YYYY-MM - Assunto'
      - 'YYYY-MM'
    Quando não houver dia, assume dia=1.
    """
    s = (folder_name or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})(?:-(\d{2}))?\b", s)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or "1")
    try:
        return datetime(y, mo, d)
    except ValueError:
        return None

def _format_date(dt: datetime) -> str:
    """Formata data como ddm/mm/yyyy (baseado no 1º dia do mês)"""
    return dt.strftime("%d/%m/%y")

def _get_month_label(dt: datetime) -> str:
    """Retorna label do mês/ano (em PT-BR)"""
    month_names = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    return f"{month_names.get(dt.month, dt.strftime('%B'))}/{dt.year}"

def _group_by_month(pastas: list[str]) -> dict[str, list[tuple[str, datetime]]]:
    """Agrupa pastas por mês/ano (nome inicia com YYYY-MM[-DD])."""
    groups: dict[str, list[tuple[str, datetime]]] = defaultdict(list)
    order_key: dict[str, datetime] = {}  # label -> max datetime do grupo
    no_date_items: list[tuple[str, None]] = []

    for folder in pastas:
        dt = _parse_date(folder)
        if dt:
            label = _get_month_label(dt)
            groups[label].append((folder, dt))
            # Mantém a data mais recente como chave de ordenação
            prev = order_key.get(label)
            if prev is None or dt > prev:
                order_key[label] = dt
        else:
            no_date_items.append((folder, None))

    # Ordenar grupos por data (mais recente primeiro) usando a order_key
    sorted_labels = sorted(order_key.keys(), key=lambda k: order_key[k], reverse=True)
    sorted_groups: "OrderedDict[str, list[tuple[str, datetime]]]" = OrderedDict()
    for lbl in sorted_labels:
        sorted_groups[lbl] = groups[lbl]

    if no_date_items:
        sorted_groups["Outros"] = no_date_items

    return sorted_groups

def comando_listar(argumento: str, sender: str):
    log_manager.add(f"[LISTAR] Iniciando comando para {sender}", "INFO")

    prefixo = prefix_from_env()  # <- ESSENCIAL: define antes de usar
    pastas = list_pastas_2nivel(bucket, prefixo)

    html_final = render_listar_html(pastas, SMTP_USER, embed=False)

    send_response(
        sender,
        "📂 Relatório DDS - Documentos de Segurança",
        f"Relatório com {len(pastas)} documento(s).",
        html_body=html_final
    )

    
    log_manager.add(f"[LISTAR] E-mail enviado para {sender}", "INFO")