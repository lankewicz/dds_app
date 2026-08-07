from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any

def _to_decimal(val: Any) -> Decimal:
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val or "0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _fmt_dec(val: Decimal) -> str:
    """Formata Decimal no padrão brasileiro de exibição (ex: 677,23)."""
    return f"{val:.2f}".replace(".", ",")

def calcular_tributos_nfse(
    valor_bruto: Decimal | float | str,
    aliquota_iss_perc: Decimal | float | str = "5.00",
    iss_retido: bool = True,
    aliquota_pis_perc: Decimal | float | str = "0.65",
    aliquota_cofins_perc: Decimal | float | str = "3.00",
    aliquota_csll_perc: Decimal | float | str = "1.00",
    aliquota_ir_perc: Decimal | float | str = "1.50",
    aliquota_inss_perc: Decimal | float | str = "3.50",
    usar_isencao_ir_pequeno_valor: bool = True,
    contrato_numero: str = "4600025149",
    municipio_nome: str = "CORBELIA",
    codigo_ibge_prestacao: str = "4106308",
    item_lc116: str = "7.05",
    pedido_item: str = "4504472658",
    cbs_valor: Decimal | float | str = "0.00",
    ibs_valor: Decimal | float | str = "0.00"
) -> Dict[str, Any]:
    """
    Cálculo fiscal estrito em Decimal para NFS-e.
    Aplica quantização de centavos (ROUND_HALF_UP) e fórmula de conciliação oficial.
    """
    v_bruto = _to_decimal(valor_bruto)
    aliq_iss = _to_decimal(aliquota_iss_perc)
    
    # 1. ISS
    base_iss = v_bruto
    v_iss = (base_iss * (aliq_iss / Decimal("100.00"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    # 2. Retenções Federais
    aliq_pis = _to_decimal(aliquota_pis_perc)
    aliq_cofins = _to_decimal(aliquota_cofins_perc)
    aliq_csll = _to_decimal(aliquota_csll_perc)
    aliq_ir = _to_decimal(aliquota_ir_perc)
    aliq_inss = _to_decimal(aliquota_inss_perc)
    
    aliq_federais_total = aliq_pis + aliq_cofins + aliq_csll
    v_ir = (v_bruto * (aliq_ir / Decimal("100.00"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if usar_isencao_ir_pequeno_valor and v_ir < Decimal("10.00"):
        v_ir = Decimal("0.00")
        
    v_inss = (v_bruto * (aliq_inss / Decimal("100.00"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    total_retencoes_federais = (v_bruto * (aliq_federais_total / Decimal("100.00"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    v_pis = (v_bruto * (aliq_pis / Decimal("100.00"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    v_cofins = (v_bruto * (aliq_cofins / Decimal("100.00"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    v_csll = total_retencoes_federais - v_pis - v_cofins
    
    v_cbs = _to_decimal(cbs_valor)
    v_ibs = _to_decimal(ibs_valor)
    
    # 3. Conciliação de Valor Líquido
    v_iss_desconto = v_iss if iss_retido else Decimal("0.00")
    v_liquido = v_bruto - v_iss_desconto - v_pis - v_cofins - v_csll - v_ir - v_inss
    v_liquido = v_liquido.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    # 4. Geração Automática das Descrições no Padrão Exigido
    desc_analitica = (
        f"SERVICOS PRESTADOS CONFORME CONTRATO {contrato_numero} NO MUNICIPIO DE {municipio_nome.upper()} "
        f"- MUN_PREST={codigo_ibge_prestacao} - SERV_LC={item_lc116} - ALIQ_ISS={int(aliq_iss) if aliq_iss % 1 == 0 else aliq_iss} "
        f"- VALOR_INSS={_fmt_dec(v_inss)} - PED_IT={pedido_item}[1-999] "
        f"- BASE_ISS={_fmt_dec(base_iss)} - VALOR_ISS={_fmt_dec(v_iss)}"
    )
    
    desc_sintetica = (
        f"SERVIÇOS DE MANUTENÇÃO DE REDES DE DISTRIBUIÇÃO DE ENERGIA ELÉTRICA - CONTRATO {contrato_numero} "
        f"- MUNICÍPIO {municipio_nome.upper()} ({codigo_ibge_prestacao}) - VALOR BRUTO: R$ {_fmt_dec(v_bruto)}"
    )

    return {
        "valor_bruto": v_bruto,
        "base_iss": base_iss,
        "aliquota_iss": aliq_iss,
        "valor_iss": v_iss,
        "iss_retido": iss_retido,
        "valor_pis": v_pis,
        "valor_cofins": v_cofins,
        "valor_csll": v_csll,
        "total_retencoes_federais": total_retencoes_federais,
        "valor_ir": v_ir,
        "valor_inss": v_inss,
        "cbs_valor": v_cbs,
        "ibs_estadual_valor": v_ibs,
        "valor_liquido": v_liquido,
        "descricao_analitica": desc_analitica,
        "descricao_sintetica": desc_sintetica
    }
