from nfse.providers.base import NfseProvider
from nfse.providers.mock_provider import MockNfseProvider
from nfse.providers.patobranco_provider import PatoBrancoCidade360Provider
from nfse.providers.sefin_provider import SefinNacionalProvider
from nfse.config import nfse_settings

def get_nfse_provider(provider_name: str = None) -> NfseProvider:
    """
    Fábrica desacoplada de provedores NFS-e.
    Isola a aplicação de chamadas específicas de um emissor municipal ou federal.
    """
    name = (provider_name or nfse_settings.DEFAULT_PROVIDER).lower()
    
    if name == "pato_branco" or name == "cidade360":
        return PatoBrancoCidade360Provider()
    elif name == "sefin_nacional" or name == "federal":
        return SefinNacionalProvider()
    else:
        return MockNfseProvider()
