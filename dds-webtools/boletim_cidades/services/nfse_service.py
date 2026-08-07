# dds-webtools/boletim_cidades/services/nfse_service.py
from __future__ import annotations
import os
import time
import uuid
from typing import Dict, Any
from nfse.calculator import calcular_tributos_nfse
from nfse.providers.factory import get_nfse_provider

PRESTADOR_CNPJ = os.environ.get("PRESTADOR_CNPJ", "85482594000177")

def emitir_nfse(payload_dados: dict[str, Any]) -> dict[str, Any]:
    """
    Emissão unificada de NFS-e integrada ao módulo dds-webtools/nfse.
    Utiliza o motor fiscal Decimal e o provedor ativo (Mock, PatoBrancoCidade360 ou SefinNacional).
    """
    ref = payload_dados.get("referencia") or f"BOLETIM_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    val_bruto = payload_dados.get("valor_servicos", 0.0)
    aliq_iss = payload_dados.get("aliquota_iss", 5.0)
    
    # Motor de Cálculo Decimal Unificado
    calc = calcular_tributos_nfse(
        valor_bruto=val_bruto,
        aliquota_iss_perc=aliq_iss,
        municipio_nome=payload_dados.get("municipio", "PATO BRANCO"),
        codigo_ibge_prestacao=str(payload_dados.get("codigo_municipio", "4118501"))
    )

    provider = get_nfse_provider()
    res = provider.emitir_sincrono(calc, {"referencia": ref})

    return {
        "ok": res.get("sucesso", False),
        "status": res.get("status", "desconhecido"),
        "referencia": ref,
        "numero_nf": res.get("numero_nfse", ""),
        "codigo_verificacao": res.get("codigo_verificacao", ""),
        "valor_servicos": float(calc["valor_bruto"]),
        "aliquota_iss": float(calc["aliquota_iss"]),
        "valor_iss": float(calc["valor_iss"]),
        "valor_liquido": float(calc["valor_liquido"]),
        "pdf_url": res.get("pdf_url", ""),
        "mensagem": res.get("mensagem", "Processamento realizado pelo módulo unificado NFS-e."),
        "data_emissao": time.strftime("%Y-%m-%dT%H:%M:%S")
    }

    # Estrutura do payload Focus NFe v2
    nfse_body = {
        "data_emissao": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "prestador": {
            "cnpj": payload_dados.get("prestador_cnpj", PRESTADOR_CNPJ),
            "inscricao_municipal": payload_dados.get("prestador_im", "")
        },
        "tomador": {
            "cnpj": payload_dados.get("tomador_cnpj", ""),
            "cpf": payload_dados.get("tomador_cpf", ""),
            "razao_social": payload_dados.get("tomador_razao", "Tomador do Serviço"),
            "email": payload_dados.get("tomador_email", ""),
            "endereco": {
                "logradouro": payload_dados.get("tomador_logradouro", ""),
                "numero": payload_dados.get("tomador_numero", ""),
                "bairro": payload_dados.get("tomador_bairro", ""),
                "codigo_municipio": payload_dados.get("codigo_municipio", ""),
                "uf": payload_dados.get("uf", "SP"),
                "cep": payload_dados.get("tomador_cep", "")
            }
        },
        "servico": {
            "valor_servicos": val_bruto,
            "aliquota": aliq_iss,
            "iss_retido": payload_dados.get("iss_retido", False),
            "item_lista_servico": payload_dados.get("item_lista_servico", "07.02"),
            "codigo_tributacao_municipio": payload_dados.get("codigo_tributacao_municipio", ""),
            "discriminacao": payload_dados.get("discriminacao", f"Prestação de serviços referente ao Boletim: {payload_dados.get('boletim', '')}")
        }
    }

    url = f"{_get_base_url()}/nfse?ref={ref}"
    headers = {
        "Content-Type": "application/json"
    }

    try:
        # Autenticação Basic Auth com Token
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, url, NFSE_API_TOKEN, "")
        handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
        opener = urllib.request.build_opener(handler)

        req = urllib.request.Request(url, data=json.dumps(nfse_body).encode("utf-8"), headers=headers, method="POST")
        with opener.open(req, timeout=15) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            return {
                "ok": True,
                "status": res_data.get("status", "processando"),
                "referencia": ref,
                "numero_nf": res_data.get("numero", ""),
                "codigo_verificacao": res_data.get("codigo_verificacao", ""),
                "pdf_url": res_data.get("url_danfe") or res_data.get("caminho_pdf", ""),
                "mensagem": "Requisição de NFS-e enviada à API.",
                "resposta_raw": res_data
            }
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8")
        return {
            "ok": False,
            "status": "erro",
            "referencia": ref,
            "mensagem": f"Erro da API Focus NFe (HTTP {err.code}): {err_body}"
        }
    except Exception as ex:
        return {
            "ok": False,
            "status": "erro",
            "referencia": ref,
            "mensagem": f"Falha de conexão com API NFS-e: {str(ex)}"
        }


def consultar_status_nfse(ref: str) -> dict[str, Any]:
    """Consulta o status de processamento da NFS-e via referência."""
    if not NFSE_API_TOKEN or ref.startswith("BOLETIM_"):
        return {
            "ok": True,
            "status": "autorizada",
            "simulado": True,
            "referencia": ref,
            "mensagem": "NFS-e autorizada no ambiente simulado local."
        }

    url = f"{_get_base_url()}/nfse/{ref}"
    try:
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, url, NFSE_API_TOKEN, "")
        handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
        opener = urllib.request.build_opener(handler)

        req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, method="GET")
        with opener.open(req, timeout=10) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            return {
                "ok": True,
                "status": res_data.get("status", "desconhecido"),
                "referencia": ref,
                "numero_nf": res_data.get("numero", ""),
                "pdf_url": res_data.get("url_danfe") or res_data.get("caminho_pdf", ""),
                "resposta_raw": res_data
            }
    except Exception as ex:
        return {"ok": False, "mensagem": str(ex)}
