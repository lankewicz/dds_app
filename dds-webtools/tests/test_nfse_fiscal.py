import sys
from pathlib import Path
from decimal import Decimal

# Inclui nfse no path
_MODULE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_MODULE_DIR / "nfse"))
sys.path.insert(0, str(_MODULE_DIR))

from nfse.calculator import calcular_tributos_nfse
from nfse.validator import validar_rascunho_nfse
from nfse.providers.factory import get_nfse_provider

def test_nota_4226_corbelia():
    """NFS-e 4226 Corbélia: Bruto 677.23 | ISS 5% (33.86) | PIS/COFINS/CSLL 31.49 | IR 10.16 | INSS 23.70 | Líquido 578.02"""
    calc = calcular_tributos_nfse(
        valor_bruto="677.23",
        aliquota_iss_perc="5.00",
        iss_retido=True,
        aliquota_pis_perc="0.65",
        aliquota_cofins_perc="3.00",
        aliquota_csll_perc="1.00",
        aliquota_ir_perc="1.50",
        aliquota_inss_perc="3.50",
        municipio_nome="CORBELIA",
        codigo_ibge_prestacao="4106308"
    )
    
    assert calc["valor_bruto"] == Decimal("677.23")
    assert calc["valor_iss"] == Decimal("33.86")
    assert calc["total_retencoes_federais"] == Decimal("31.49")
    assert calc["valor_ir"] == Decimal("10.16")
    assert calc["valor_inss"] == Decimal("23.70")
    assert calc["valor_liquido"] == Decimal("578.02")

def test_nota_4227_coronel_domingos_soares():
    """NFS-e 4227 Coronel Domingos Soares: Bruto 2335.09 | ISS 3% (70.05) | PIS/COFINS/CSLL 108.58 | IR 35.03 | INSS 81.73 | Líquido 2039.70"""
    calc = calcular_tributos_nfse(
        valor_bruto="2335.09",
        aliquota_iss_perc="3.00",
        iss_retido=True,
        aliquota_inss_perc="3.50",
        municipio_nome="CORONEL DOMINGOS SOARES",
        codigo_ibge_prestacao="4106456"
    )
    
    assert calc["valor_iss"] == Decimal("70.05")
    assert calc["total_retencoes_federais"] == Decimal("108.58")
    assert calc["valor_ir"] == Decimal("35.03")
    assert calc["valor_inss"] == Decimal("81.73")
    assert calc["valor_liquido"] == Decimal("2039.70")

def test_nota_4228_coronel_vivida():
    """NFS-e 4228 Coronel Vivida: Bruto 3491.12 | ISS 5% (174.56) | PIS/COFINS/CSLL 162.34 | IR 52.37 | INSS 122.19 | Líquido 2979.66"""
    calc = calcular_tributos_nfse(
        valor_bruto="3491.12",
        aliquota_iss_perc="5.00",
        iss_retido=True,
        aliquota_inss_perc="3.50",
        municipio_nome="CORONEL VIVIDA",
        codigo_ibge_prestacao="4106506"
    )
    
    assert calc["valor_iss"] == Decimal("174.56")
    assert calc["total_retencoes_federais"] == Decimal("162.34")
    assert calc["valor_ir"] == Decimal("52.37")
    assert calc["valor_inss"] == Decimal("122.19")
    assert calc["valor_liquido"] == Decimal("2979.66")

def test_nota_4229_cruz_machado():
    """NFS-e 4229 Cruz Machado: Bruto 894.33 | ISS 5% (44.72) | PIS/COFINS/CSLL 41.59 | IR 13.41 | INSS 44.72 | Líquido 749.89"""
    calc = calcular_tributos_nfse(
        valor_bruto="894.33",
        aliquota_iss_perc="5.00",
        iss_retido=True,
        aliquota_inss_perc="5.00",
        municipio_nome="CRUZ MACHADO",
        codigo_ibge_prestacao="4106803"
    )
    
    assert calc["valor_iss"] == Decimal("44.72")
    assert calc["total_retencoes_federais"] == Decimal("41.59")
    assert calc["valor_ir"] == Decimal("13.41")
    assert calc["valor_inss"] == Decimal("44.72")
    assert calc["valor_liquido"] == Decimal("749.89")

def test_nota_4230_cruzeiro_do_iguacu():
    """NFS-e 4230 Cruzeiro do Iguaçu: Bruto 2331.79 | ISS 5% (116.59) | PIS/COFINS/CSLL 108.43 | IR 34.98 | INSS 81.61 | Líquido 1990.18"""
    calc = calcular_tributos_nfse(
        valor_bruto="2331.79",
        aliquota_iss_perc="5.00",
        iss_retido=True,
        aliquota_inss_perc="3.50",
        municipio_nome="CRUZEIRO DO IGUACU",
        codigo_ibge_prestacao="4106571"
    )
    
    assert calc["valor_iss"] == Decimal("116.59")
    assert calc["total_retencoes_federais"] == Decimal("108.43")
    assert calc["valor_ir"] == Decimal("34.98")
    assert calc["valor_inss"] == Decimal("81.61")
    assert calc["valor_liquido"] == Decimal("1990.18")

def test_nota_4231_diamante_do_sul_isencao_ir():
    """NFS-e 4231 Diamante do Sul: Bruto 321.50 | ISS 3% (9.65) | PIS/COFINS/CSLL 14.95 | IR 0.00 (Isento < 10.00) | INSS 11.25 | Líquido 285.65"""
    calc = calcular_tributos_nfse(
        valor_bruto="321.50",
        aliquota_iss_perc="3.00",
        iss_retido=True,
        aliquota_inss_perc="3.50",
        usar_isencao_ir_pequeno_valor=True,
        municipio_nome="DIAMANTE DO SUL",
        codigo_ibge_prestacao="4107157"
    )
    
    assert calc["valor_iss"] == Decimal("9.65")
    assert calc["total_retencoes_federais"] == Decimal("14.95")
    assert calc["valor_ir"] == Decimal("0.00")
    assert calc["valor_inss"] == Decimal("11.25")
    assert calc["valor_liquido"] == Decimal("285.65")

def test_validacao_discrepancias_reais():
    """Valida a detecção de erros e divergências reais conforme Seção 8 do documento."""
    
    # 1. Contrato com 11 dígitos
    alertas_1 = validar_rascunho_nfse(
        contrato_numero="46000251749",
        pedido_numero="PED-TESTE",
        municipio_nome="CORBELIA",
        codigo_ibge_prestacao="4106308",
        codigo_ibge_incidencia="4106308",
        tomador_cnpj="04370282000170",
        servico_codigo="7.05",
        valor_bruto=Decimal("677.23"),
        base_iss=Decimal("677.23"),
        aliquota_iss=Decimal("5.00"),
        valor_iss=Decimal("33.86"),
        iss_retido=True,
        valor_pis=Decimal("4.40"),
        valor_cofins=Decimal("20.32"),
        valor_csll=Decimal("6.77"),
        valor_ir=Decimal("10.16"),
        valor_inss=Decimal("23.70"),
        valor_liquido=Decimal("578.02"),
        descricao_texto="",
        aprovado_humano=True
    )
    assert any("possui 11 dígitos" in a for a in alertas_1)

    # 2. Descrição com VALOR_INSS=31,30 vs retido real 44,72
    alertas_2 = validar_rascunho_nfse(
        contrato_numero="4600025149",
        pedido_numero="PED-TESTE-2",
        municipio_nome="CRUZ MACHADO",
        codigo_ibge_prestacao="4106803",
        codigo_ibge_incidencia="4106803",
        tomador_cnpj="04370282000170",
        servico_codigo="7.05",
        valor_bruto=Decimal("894.33"),
        base_iss=Decimal("894.33"),
        aliquota_iss=Decimal("5.00"),
        valor_iss=Decimal("44.72"),
        iss_retido=True,
        valor_pis=Decimal("5.81"),
        valor_cofins=Decimal("26.83"),
        valor_csll=Decimal("8.94"),
        valor_ir=Decimal("13.41"),
        valor_inss=Decimal("44.72"),
        valor_liquido=Decimal("749.89"),
        descricao_texto="SERVICOS - VALOR_INSS=31,30 - BASE_ISS=894,33 - VALOR_ISS=44,72",
        aprovado_humano=True
    )
    assert any("Texto descreve VALOR_INSS=31,30" in a for a in alertas_2)

def test_mock_provider():
    """Testa o funcionamento isolado do MockNfseProvider."""
    provider = get_nfse_provider("mock")
    res = provider.emitir_sincrono({}, {"pedido_id": 1})
    assert res["sucesso"] is True
    assert res["status"] == "Autorizado"
    assert "chave_acesso_nacional" in res
