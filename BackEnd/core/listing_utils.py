# =============================================================================
# Nome do arquivo : core/listing_utils.py
# Data            : 16/01/2026
# Função          : Utilitários reutilizáveis para LISTAR DDS (Storage) e render HTML.
# =============================================================================

from __future__ import annotations

from datetime import datetime
from collections import defaultdict, OrderedDict
from typing import Dict, List, Tuple, Optional
import re

from urllib.parse import quote
from html import escape


def list_pastas_2nivel(bucket, prefix: str) -> List[str]:
    """
    Lista o 2º nível sob o prefixo, robusto mesmo se DDS_PREFIX contiver subpastas.
    Ex.: prefix='DDSv2/Docs/' -> retorna ['2025-10 - Assunto', ...]
    """
    names = set()
    prefix_norm = prefix if prefix.endswith("/") else prefix + "/"
    plen = len(prefix_norm)

    for blob in bucket.list_blobs(prefix=prefix_norm):
        rel = (blob.name or "")[plen:]
        first = rel.split("/", 1)[0]
        if first:
            names.add(first)

    names.discard("lista.json")
    return sorted(names, reverse=True)


def _parse_date(folder_name: str) -> Optional[datetime]:
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


def _format_date(dt: Optional[datetime]) -> str:
    """Formata data como dd/mm/yy (baseado no 1º dia do mês quando não houver dia)."""
    if not dt:
        return "N/A"
    return dt.strftime("%d/%m/%y")


def _get_month_label(dt: datetime) -> str:
    """Retorna label do mês/ano (PT-BR)."""
    month_names = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
    }
    return f"{month_names.get(dt.month, dt.strftime('%B'))}/{dt.year}"


def _group_by_month(pastas: List[str]) -> "OrderedDict[str, List[Tuple[str, Optional[datetime]]]]":
    """Agrupa pastas por mês/ano (nome inicia com YYYY-MM[-DD])."""
    groups: Dict[str, List[Tuple[str, datetime]]] = defaultdict(list)
    order_key: Dict[str, datetime] = {}
    no_date_items: List[Tuple[str, Optional[datetime]]] = []

    for folder in pastas:
        dt = _parse_date(folder)
        if dt:
            label = _get_month_label(dt)
            groups[label].append((folder, dt))
            prev = order_key.get(label)
            if prev is None or dt > prev:
                order_key[label] = dt
        else:
            no_date_items.append((folder, None))

    sorted_labels = sorted(order_key.keys(), key=lambda k: order_key[k], reverse=True)
    sorted_groups: "OrderedDict[str, List[Tuple[str, Optional[datetime]]]]" = OrderedDict()
    for lbl in sorted_labels:
        sorted_groups[lbl] = groups[lbl]

    if no_date_items:
        sorted_groups["Outros"] = no_date_items

    return sorted_groups


def _css() -> str:
    return """
    <style>
        .dds-listar-wrap { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; background: white; margin: 0; padding: 0; }
        .dds-listar-container { max-width: 1000px; margin: 0 auto; background: white; border: 1px solid #dee2e6; overflow: hidden; }
        .dds-listar-header { background: #2c3e90; padding: 25px 0; text-align: center; margin: 0; width: 100%; }
        .dds-listar-company-name { font-size: 28px; font-weight: 700; margin: 0 0 5px 0; letter-spacing: 1px; color: #ffffff; }
        .dds-listar-company-name .highlight { color: #ffd700; }
        .dds-listar-system-title { font-size: 24px; font-weight: 600; margin: 10px 0 5px 0; color: #ffffff; }
        .dds-listar-system-subtitle { font-size: 14px; margin: 0; font-weight: 300; letter-spacing: 0.5px; color: #e8e8e8; }
        .dds-listar-divider { width: 60px; height: 2px; background: #ffd700; margin: 12px auto; }
        .dds-listar-content { padding: 20px 30px; }
        .dds-listar-empty { text-align: center; padding: 40px 20px; color: #666; }
        .dds-listar-section { margin-bottom: 30px; }
        .dds-listar-section-header { background: #667eea; color: white; padding: 10px 18px; border-radius: 6px; font-size: 15px; font-weight: 600; margin-bottom: 12px; }
        .dds-listar-table { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
        .dds-listar-thead { background: #f8f9fa; }
        .dds-listar-th { padding: 12px 14px; text-align: left; font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #495057; border-bottom: 2px solid #dee2e6; }
        .dds-listar-td { padding: 12px 14px; border-bottom: 1px solid #e9ecef; font-size: 14px; }
        .dds-listar-tr:last-child .dds-listar-td { border-bottom: none; }
        .dds-listar-tbody .dds-listar-tr:nth-child(odd) { background-color: #f8f9fa; }
        .dds-listar-tbody .dds-listar-tr:nth-child(even) { background-color: #ffffff; }
        .dds-listar-tbody .dds-listar-tr:hover { background-color: #e9ecef !important; }
        .dds-listar-date { color: #212529; font-weight: 500; font-family: 'Courier New', monospace; width: 120px; }
        .dds-listar-subject { color: #000000; }
        .dds-listar-action { text-align: center; width: 120px; }
        .dds-listar-delete { display: inline-block; padding: 8px 16px; background: #dc3545; color: white !important; text-decoration: none; border-radius: 6px; font-size: 12px; font-weight: 500; transition: all 0.2s ease; }
        .dds-listar-delete:hover { background: #c82333; transform: translateY(-1px); box-shadow: 0 4px 8px rgba(220, 53, 69, 0.3); }
        .dds-listar-footer { padding: 18px 30px; background: #f8f9fa; text-align: center; color: #6c757d; font-size: 12px; border-top: 1px solid #dee2e6; }
        .dds-listar-current { outline: 2px solid #0d6efd; outline-offset: -2px; background: #eef5ff !important; }
    </style>
    """


def render_listar_html(
    pastas: List[str],
    smtp_user: str,
    *,
    embed: bool = False,
    current_folder: str = "",
) -> str:
    grouped = _group_by_month(pastas)

    parts: List[str] = []
    parts.append(_css())

    if embed:
        parts.append('<div class="dds-listar-wrap">')
        parts.append('<div class="dds-listar-content">')
    else:
        parts.append("""
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body class="dds-listar-wrap">
            <div class="dds-listar-container">
                <div class="dds-listar-header">
                    <h1 class="dds-listar-company-name">
                        <span class="highlight">⚡</span> CHICO ELÉTRO <span class="highlight">⚡</span>
                    </h1>
                    <div class="dds-listar-divider"></div>
                    <h2 class="dds-listar-system-title">🛡️ Sistema DDS</h2>
                    <p class="dds-listar-system-subtitle">Diálogo Diário de Segurança</p>
                </div>
                <div class="dds-listar-content">
        """)

    if not pastas:
        parts.append("""
            <div class="dds-listar-empty">
                <h3>📂 Nenhuma pasta encontrada</h3>
                <p>Não há documentos DDS armazenados no momento.</p>
            </div>
        """)
    else:
        parts.append(f"""
            <div style="text-align: right; margin-bottom: 20px; color: #6c757d;">
                <strong>{len(pastas)}</strong> documento(s) encontrado(s)
            </div>
        """)

        for group_label, folders in grouped.items():
            parts.append(f"""
                <div class="dds-listar-section">
                    <div class="dds-listar-section-header">{escape(group_label)}</div>
                    <table class="dds-listar-table">
                        <thead class="dds-listar-thead">
                            <tr>
                                <th class="dds-listar-th">Data</th>
                                <th class="dds-listar-th">Assunto</th>
                                <th class="dds-listar-th" style="text-align:center;">Ação</th>
                            </tr>
                        </thead>
                        <tbody class="dds-listar-tbody">
            """)

            for folder, dt in folders:
                parts_folder = (folder or "").split(" - ", 1)
                assunto_part = parts_folder[1] if len(parts_folder) > 1 else "(Sem assunto)"
                date_formatted = _format_date(dt)
                mailto = f"mailto:{smtp_user}?subject=APAGAR%20{quote(folder, safe='')}"
                tr_cls = "dds-listar-tr"
                if current_folder and folder == current_folder:
                    tr_cls += " dds-listar-current"

                parts.append(f"""
                            <tr class="{tr_cls}">
                                <td class="dds-listar-td dds-listar-date">{escape(date_formatted)}</td>
                                <td class="dds-listar-td dds-listar-subject">{escape(assunto_part)}</td>
                                <td class="dds-listar-td dds-listar-action">
                                    <a href="{mailto}" class="dds-listar-delete">🗑️ Apagar</a>
                                </td>
                            </tr>
                """)

            parts.append("""
                        </tbody>
                    </table>
                </div>
            """)

    if embed:
        parts.append("</div></div>")
    else:
        parts.append("""
                </div>
                <div class="dds-listar-footer">
                    Sistema Chico Elétro • Responda este e-mail com <strong>LISTAR</strong> para atualizar a listagem
                </div>
            </div>
        </body>
        </html>
        """)

    return "".join(parts)
