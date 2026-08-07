import httpx
from typing import Dict, Any
from nfse.providers.base import NfseProvider
from nfse.config import nfse_settings

class SefinNacionalProvider(NfseProvider):
    """
    Conector desacoplado preparado para a API Federal da Sefin Nacional (Emissor Público Nacional).
    URLs:
      - Produção Restrita: https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional
      - Produção: https://sefin.nfse.gov.br/SefinNacional
    Permanecerá desativado até autorização para uso da API Federal pelo município.
    """

    def __init__(self):
        self.ativo = False
        self.base_url = (
            nfse_settings.SEFIN_NACIONAL_PROD if nfse_settings.NFSE_ENV == "producao"
            else nfse_settings.SEFIN_NACIONAL_PROD_RESTRITA
        )

    def _check_ativo(self):
        if not self.ativo:
            raise NotImplementedError(
                "O conector SefinNacionalProvider encontra-se desativado. "
                "Pato Branco opera atualmente via API municipal Cidade360."
            )

    def emitir_sincrono(self, dps_payload: Dict[str, Any], rascunho_dados: Dict[str, Any]) -> Dict[str, Any]:
        self._check_ativo()
        url = f"{self.base_url}/nfse"
        return {"sucesso": False, "mensagem": "Conector Sefin Nacional não ativado."}

    def emitir_assincrono(self, dps_payload: Dict[str, Any], rascunho_dados: Dict[str, Any]) -> Dict[str, Any]:
        self._check_ativo()
        return {"sucesso": False, "mensagem": "Conector Sefin Nacional não ativado."}

    def consultar_nfse(self, chave_acesso: str) -> Dict[str, Any]:
        self._check_ativo()
        url = f"{self.base_url}/nfse/{chave_acesso}"
        return {"sucesso": False, "mensagem": "Conector Sefin Nacional não ativado."}

    def consultar_dps(self, dps_id: str) -> Dict[str, Any]:
        self._check_ativo()
        url = f"{self.base_url}/dps/{dps_id}"
        return {"sucesso": False, "mensagem": "Conector Sefin Nacional não ativado."}

    def consultar_eventos(self, chave_acesso: str) -> Dict[str, Any]:
        self._check_ativo()
        url = f"{self.base_url}/nfse/{chave_acesso}/eventos"
        return {"sucesso": False, "mensagem": "Conector Sefin Nacional não ativado."}

    def cancelar_nfse(self, chave_acesso: str, motivo: str) -> Dict[str, Any]:
        self._check_ativo()
        url = f"{self.base_url}/nfse/{chave_acesso}/eventos"
        return {"sucesso": False, "mensagem": "Conector Sefin Nacional não ativado."}
