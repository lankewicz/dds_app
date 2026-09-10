# Finalidade: concentrar regras de normalização e conversão dos dados da planilha.
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import unicodedata
from typing import Any

import pandas as pd


EXPECTED_COLUMNS = [
    "Usuário",
    "Data da Solicitação",
    "Previsão de Uso",
    "Valor Solicitado",
    "Justificativa",
    "Status",
    "Aprovador",
    "Data Aprovação",
    "Valor Aprovado",
    "Identificação da alocação",
]


# Mapeamento de variações de nomes de colunas
COLUMN_MAPPING = {
    "Valor Solic": "Valor Solicitado",
    "Data Apro": "Data Aprovação",
}


def normalize_header(text: str) -> str:
    """Remove acentos, converte para minúsculo e limpa espaços."""
    if not isinstance(text, str):
        return ""
    # Normalizar para decompor caracteres acentuados
    normalized = unicodedata.normalize('NFKD', text)
    # Filtrar apenas caracteres ASCII (remove acentos)
    clean = "".join([c for c in normalized if not unicodedata.combining(c)])
    return clean.lower().strip()


def validate_columns(df: pd.DataFrame) -> None:
    # 1. Limpeza básica inicial
    df.columns = [str(c).strip() for c in df.columns]
    
    # 2. Mapeamento de variações conhecidas (antes da normalização pesada)
    for current, canonical in COLUMN_MAPPING.items():
        if current in df.columns and canonical not in df.columns:
            df.rename(columns={current: canonical}, inplace=True)

    # 3. Mapeamento baseado em normalização
    # Criamos um mapa de: normalized_name -> original_name_in_df
    df_normalized_map = {normalize_header(c): c for c in df.columns}
    
    # 4. Verificar se as colunas esperadas (normalizadas) existem
    missing = []
    rename_map = {}
    
    for expected in EXPECTED_COLUMNS:
        norm_expected = normalize_header(expected)
        if norm_expected in df_normalized_map:
            # Encontrou uma correspondência normalizada
            original_in_df = df_normalized_map[norm_expected]
            if original_in_df != expected:
                rename_map[original_in_df] = expected
        else:
            missing.append(expected)

    # Aplicar renomeação para nomes canônicos
    if rename_map:
        df.rename(columns=rename_map, inplace=True)

    if missing:
        # Tentar uma mensagem mais amigável listando o que foi encontrado
        found_cols = ", ".join(df.columns)
        raise ValueError(f"Colunas obrigatórias ausentes: {', '.join(missing)}. Encontradas: {found_cols}")


def clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    
    # Remover prefixos indesejados como "CARTÃO ", "CARTAO " (case-insensitive)
    import re
    # Busca por CART e 2 ou 3 caracteres (cobrindo CARTÃO, CARTAO, CARTÕES, CARTOES) no início da string
    text = re.sub(r"^CART\w{2,3}[\s\-]*", "", text, flags=re.IGNORECASE)
    
    return text or None


def parse_date(value: Any) -> date | None:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None

    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Data inválida: {value}")
    return parsed.date()


def parse_decimal(value: Any) -> Decimal:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return Decimal("0.00")

    if isinstance(value, str):
        # Remover símbolos de moeda e espaços (ex: "R$ 1.234,56" -> "1.234,56")
        clean_value = value.replace("R$", "").replace("$", "").strip()
        # Se usar formato brasileiro: 1.234,56 -> 1234.56
        if "," in clean_value and "." in clean_value:
            if clean_value.rfind(",") > clean_value.rfind("."):
                clean_value = clean_value.replace(".", "").replace(",", ".")
        elif "," in clean_value:
            clean_value = clean_value.replace(",", ".")
        
        # Remover qualquer outro caractere que não seja número, ponto ou sinal de menos
        import re
        clean_value = re.sub(r"[^\d.-]", "", clean_value)
        
        try:
            decimal_value = Decimal(clean_value)
        except Exception:
            decimal_value = Decimal("0.00")
    else:
        try:
            decimal_value = Decimal(str(value))
        except Exception:
            decimal_value = Decimal("0.00")

    return decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_record_hash(payload: dict[str, Any]) -> str:
    ordered_values = [
        payload.get("id_alocacao"),
        payload.get("usuario_origem"),
        payload.get("data_solicitacao"),
        payload.get("previsao_uso"),
        payload.get("valor_solicitado"),
        payload.get("justificativa"),
        payload.get("status"),
        payload.get("aprovador"),
        payload.get("data_aprovacao"),
        payload.get("valor_aprovado"),
    ]
    raw = "|".join("" if value is None else str(value) for value in ordered_values)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def to_cents(value: Any) -> int:
    """Converte qualquer valor para centavos (inteiro)."""
    from decimal import Decimal, ROUND_HALF_UP
    if value is None or pd.isna(value):
        return 0
    # Converte para Decimal para precisão, multiplica por 100 e arredonda
    d_val = Decimal(str(value))
    return int((d_val * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

