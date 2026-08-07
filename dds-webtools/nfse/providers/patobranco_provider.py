import httpx
from typing import Dict, Any
from nfse.providers.base import NfseProvider
from nfse.config import nfse_settings

class PatoBrancoCidade360Provider(NfseProvider):
    """
    Conector oficial para a API do Município de Pato Branco / Cidade360 PRONIM.
    API Base: https://webapp1-patobranco.cidade360.cloud/Nfse.Api/NotaNacional/
    """

    def __init__(self):
        self.base_url = nfse_settings.PATO_BRANCO_API_BASE.rstrip("/")
        self.env = nfse_settings.NFSE_ENV
        self.allow_prod = nfse_settings.ALLOW_PRODUCTION_EMISSION

    def _check_safety(self):
        if self.env == "producao" and not self.allow_prod:
            raise PermissionError(
                "Proteção de Produção Ativada: Chamada para a API de produção da Cidade360 bloqueada. "
                "Defina ALLOW_PRODUCTION_EMISSION=true para liberar emissões reais."
            )

    def emitir_sincrono(self, dps_payload: Dict[str, Any], rascunho_dados: Dict[str, Any]) -> Dict[str, Any]:
        self._check_safety()
        
        # Em homologação, utiliza o código IBGE de referência municipal (3542404)
        if self.env == "homologacao":
            dps_payload["ibge_referencia_teste"] = nfse_settings.PATO_BRANCO_TEST_IBGE

        url = f"{self.base_url}/EnviarSincrono"
        headers = {"Content-Type": "application/json"}

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, json=dps_payload, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "sucesso": True,
                        "status": "Autorizado" if data.get("Sucesso") else "Rejeitado",
                        "numero_nfse": str(data.get("NumeroNfse", "")),
                        "chave_acesso_nacional": data.get("ChaveAcesso", ""),
                        "codigo_verificacao": data.get("CodigoVerificacao", ""),
                        "pdf_url": data.get("UrlDanfse", ""),
                        "xml_url": data.get("UrlXml", ""),
                        "resposta_api_raw": response.text
                    }
                else:
                    return {
                        "sucesso": False,
                        "status": "Rejeitado",
                        "mensagem": f"Erro HTTP {response.status_code} na API Cidade360: {response.text}",
                        "resposta_api_raw": response.text
                    }
        except Exception as ex:
            return {
                "sucesso": False,
                "status": "Erro Conexao",
                "mensagem": f"Falha ao conectar à API Cidade360 de Pato Branco: {str(ex)}"
            }

    def emitir_assincrono(self, dps_payload: Dict[str, Any], rascunho_dados: Dict[str, Any]) -> Dict[str, Any]:
        self._check_safety()
        url = f"{self.base_url}/EnviarAssincrono"
        headers = {"Content-Type": "application/json"}

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, json=dps_payload, headers=headers)
                data = response.json() if response.status_code == 200 else {}
                return {
                    "sucesso": response.status_code == 200,
                    "protocolo": data.get("Protocolo", ""),
                    "resposta_api_raw": response.text
                }
        except Exception as ex:
            return {"sucesso": False, "mensagem": str(ex)}

    def consultar_nfse(self, chave_acesso: str) -> Dict[str, Any]:
        url = f"{self.base_url}/ConsultarNFSe/{chave_acesso}"
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(url)
                return {
                    "sucesso": response.status_code == 200,
                    "resposta_api_raw": response.text
                }
        except Exception as ex:
            return {"sucesso": False, "mensagem": str(ex)}

    def consultar_eventos(self, chave_acesso: str) -> Dict[str, Any]:
        url = f"{self.base_url}/ConsultarEventos/{chave_acesso}"
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(url)
                return {
                    "sucesso": response.status_code == 200,
                    "resposta_api_raw": response.text
                }
        except Exception as ex:
            return {"sucesso": False, "mensagem": str(ex)}

    def cancelar_nfse(self, chave_acesso: str, motivo: str) -> Dict[str, Any]:
        self._check_safety()
        return {
            "sucesso": False,
            "mensagem": "Cancelamento síncrono Cidade360 requer assinatura digital de evento de cancelamento."
        }
