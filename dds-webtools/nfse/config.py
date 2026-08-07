import os
from pydantic_settings import BaseSettings

class NfseSettings(BaseSettings):
    PROJECT_NAME: str = "NFS-e Manager - PUTON & DAL MOLIN LTDA"
    API_PREFIX: str = "/api/nfse"
    
    # Fiscal Environment Isolation (homologacao | producao)
    NFSE_ENV: str = os.getenv("NFSE_ENV", "homologacao").lower()
    ALLOW_PRODUCTION_EMISSION: bool = os.getenv("ALLOW_PRODUCTION_EMISSION", "false").lower() == "true"
    
    # Issuer Company (PUTON & DAL MOLIN LTDA)
    EMISSOR_CNPJ: str = "85482594000177"
    EMISSOR_RAZAO: str = "PUTON & DAL MOLIN LTDA"
    EMISSOR_IM: str = "123456"
    EMISSOR_UF: str = "PR"
    EMISSOR_MUNICIPIO_IBGE: str = "4118501"  # Pato Branco/PR IBGE
    EMISSOR_MUNICIPIO_NOME: str = "PATO BRANCO"
    
    # Active Provider (mock | pato_branco | sefin_nacional)
    DEFAULT_PROVIDER: str = os.getenv("DEFAULT_PROVIDER", "mock")
    
    # Pato Branco / Cidade360 API Base URL
    PATO_BRANCO_API_BASE: str = os.getenv(
        "PATO_BRANCO_API_BASE",
        "https://webapp1-patobranco.cidade360.cloud/Nfse.Api/NotaNacional"
    )
    PATO_BRANCO_TEST_IBGE: str = "3542404"  # IBGE de teste conforme documentação municipal
    
    # Federal Sefin Nacional URLs
    SEFIN_NACIONAL_PROD_RESTRITA: str = "https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional"
    SEFIN_NACIONAL_PROD: str = "https://sefin.nfse.gov.br/SefinNacional"

nfse_settings = NfseSettings()
