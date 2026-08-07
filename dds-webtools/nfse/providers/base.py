from abc import ABC, abstractmethod
from typing import Dict, Any

class NfseProvider(ABC):
    """Interface abstrata desacoplada para provedores de emissão e consulta de NFS-e."""

    @abstractmethod
    def emitir_sincrono(self, dps_payload: Dict[str, Any], rascunho_dados: Dict[str, Any]) -> Dict[str, Any]:
        """Transmite a DPS de forma síncrona para a API do emissor."""
        pass

    @abstractmethod
    def emitir_assincrono(self, dps_payload: Dict[str, Any], rascunho_dados: Dict[str, Any]) -> Dict[str, Any]:
        """Transmite a DPS de forma assíncrona para a fila do emissor."""
        pass

    @abstractmethod
    def consultar_nfse(self, chave_acesso: str) -> Dict[str, Any]:
        """Consulta dados completos da NFS-e autorizada pela chave de acesso."""
        pass

    @abstractmethod
    def consultar_eventos(self, chave_acesso: str) -> Dict[str, Any]:
        """Consulta histórico de eventos (cancelamento, substituição) da NFS-e."""
        pass

    @abstractmethod
    def cancelar_nfse(self, chave_acesso: str, motivo: str) -> Dict[str, Any]:
        """Solicita o cancelamento da NFS-e."""
        pass
