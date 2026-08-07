import re
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
from datetime import datetime, timedelta
from nfse.config import nfse_settings

def validar_rascunho_nfse(
    contrato_numero: str,
    pedido_numero: str,
    municipio_nome: str,
    codigo_ibge_prestacao: str,
    codigo_ibge_incidencia: str,
    tomador_cnpj: str,
    servico_codigo: str,
    valor_bruto: Decimal,
    base_iss: Decimal,
    aliquota_iss: Decimal,
    valor_iss: Decimal,
    iss_retido: bool,
    valor_pis: Decimal,
    valor_cofins: Decimal,
    valor_csll: Decimal,
    valor_ir: Decimal,
    valor_inss: Decimal,
    valor_liquido: Decimal,
    descricao_texto: str,
    aprovado_humano: bool = False,
    certificado_validade: Optional[datetime] = None,
    pedidos_faturados_existentes: Optional[List[str]] = None
) -> List[str]:
    """
    Suíte completa de validação fiscal para identificação de erros e alertas impeditivos.
    Retorna uma lista de strings descrevendo todas as divergências/erros encontrados.
    """
    alertas: List[str] = []

    # 1. Validação de Contrato (Dígitos)
    digits_contrato = re.sub(r"\D", "", contrato_numero or "")
    if len(digits_contrato) != 10:
        alertas.append(
            f"Alerta de Contrato: Número do contrato '{contrato_numero}' possui {len(digits_contrato)} dígitos "
            f"(esperado padrão de 10 dígitos, ex: 4600025149)."
        )
    if contrato_numero == "4500025149":
        alertas.append(
            f"Divergência Registrada: Contrato informado '{contrato_numero}' diverge do padrão habitual '4600025149'."
        )

    # 2. Validação de Tomador (CNPJ)
    digits_cnpj = re.sub(r"\D", "", tomador_cnpj or "")
    if not digits_cnpj or len(digits_cnpj) != 14:
        alertas.append("Erro Impeditivo: Tomador principal não possui CNPJ válido com 14 dígitos.")

    # 3. Código de Serviço
    if not servico_codigo:
        alertas.append("Erro Impeditivo: Código do serviço LC 116 ou municipal ausente.")

    # 4. Pedido Faturado / Duplicado
    if pedidos_faturados_existentes and pedido_numero in pedidos_faturados_existentes:
        alertas.append(f"Erro Impeditivo: O pedido '{pedido_numero}' já se encontra faturado no sistema.")

    # 5. Conciliação de Valor Líquido
    iss_desconto = valor_iss if iss_retido else Decimal("0.00")
    esperado_liquido = valor_bruto - iss_desconto - valor_pis - valor_cofins - valor_csll - valor_ir - valor_inss
    esperado_liquido = esperado_liquido.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if abs(valor_liquido - esperado_liquido) > Decimal("0.01"):
        alertas.append(
            f"Divergência de Conciliação: Valor líquido informado (R$ {valor_liquido:.2f}) difere "
            f"da conciliação calculada (R$ {esperado_liquido:.2f})."
        )

    # 6. Confronto de Valores no Texto Gerado vs Campos Estruturados
    if descricao_texto:
        m_inss = re.search(r"VALOR_INSS=([\d,\.]+)", descricao_texto)
        if m_inss:
            raw_str = m_inss.group(1)
            v_inss_text_str = raw_str.replace(".", "").replace(",", ".")
            try:
                v_inss_text = Decimal(v_inss_text_str)
                if abs(v_inss_text - valor_inss) > Decimal("0.01"):
                    alertas.append(
                        f"Divergência Texto x Estruturado: Texto descreve VALOR_INSS={raw_str}, "
                        f"mas campo oficial retido é R$ {valor_inss:.2f}."
                    )
            except Exception:
                pass

        m_iss = re.search(r"VALOR_ISS=([\d,\.]+)", descricao_texto)
        if m_iss:
            v_iss_text_str = m_iss.group(1).replace(".", "").replace(",", ".")
            try:
                v_iss_text = Decimal(v_iss_text_str)
                if abs(v_iss_text - valor_iss) > Decimal("0.01"):
                    alertas.append(
                        f"Divergência Texto x Estruturado: Texto descreve VALOR_ISS={v_iss_text_str}, "
                        f"mas campo oficial da nota é R$ {valor_iss:.2f}."
                    )
            except Exception:
                pass

    # 7. Município Prestação x Incidência
    if codigo_ibge_prestacao != codigo_ibge_incidencia and codigo_ibge_incidencia != "":
        alertas.append(
            f"Alerta Territorial: Município da prestação ({codigo_ibge_prestacao}) "
            f"é diferente do município de incidência ({codigo_ibge_incidencia})."
        )

    # 8. Certificado Digital A1
    if certificado_validade:
        agora = datetime.utcnow()
        if certificado_validade < agora:
            alertas.append("Erro Impeditivo: Certificado Digital A1 encontra-se VENCIDO.")
        elif certificado_validade < agora + timedelta(days=30):
            dias_restantes = (certificado_validade - agora).days
            alertas.append(f"Aviso de Segurança: Certificado Digital A1 vencerá em {dias_restantes} dias.")

    # 9. Trava de Aprovação Humana
    if not aprovado_humano:
        alertas.append("Bloqueio de Emissão: Tentativa de emissão sem aprovação humana prévia.")

    # 10. Proteção Estrita contra Chamadas Acidentais em Produção
    if nfse_settings.NFSE_ENV == "producao" and not nfse_settings.ALLOW_PRODUCTION_EMISSION:
        alertas.append(
            "Bloqueio de Segurança de Ambiente: Tentativa de comunicação em produção com trava de segurança "
            "ALLOW_PRODUCTION_EMISSION desativada."
        )

    return alertas
