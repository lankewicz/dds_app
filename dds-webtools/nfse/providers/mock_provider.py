import time
import uuid
from typing import Dict, Any
from nfse.providers.base import NfseProvider

class MockNfseProvider(NfseProvider):
    """Provedor simulado para testes automatizados, desenvolvimento local e homologação offline."""

    def emitir_sincrono(self, dps_payload: Dict[str, Any], rascunho_dados: Dict[str, Any]) -> Dict[str, Any]:
        time.sleep(0.1)
        
        ref_id = rascunho_dados.get("pedido_id", 1)
        num_nfse = str(int(time.time()) % 100000 + 4000)
        chave = f"4126088548259400017756001000000{num_nfse.zfill(7)}1002345678"
        codigo_verificacao = uuid.uuid4().hex[:8].upper()
        
        raw_resp = {
            "sucesso": True,
            "ambiente": "simulado",
            "mensagem": "NFS-e autorizada com sucesso (Modo Simulado Local).",
            "numero_nfse": num_nfse,
            "chave_acesso_nacional": chave,
            "codigo_verificacao": codigo_verificacao,
            "data_autorizacao": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
        
        return {
            "sucesso": True,
            "status": "Autorizado",
            "numero_nfse": num_nfse,
            "chave_acesso_nacional": chave,
            "codigo_verificacao": codigo_verificacao,
            "pdf_url": f"/api/nfse/pdf-simulado/{num_nfse}",
            "xml_url": f"/api/nfse/xml-simulado/{num_nfse}",
            "resposta_api_raw": str(raw_resp)
        }

    def emitir_assincrono(self, dps_payload: Dict[str, Any], rascunho_dados: Dict[str, Any]) -> Dict[str, Any]:
        protocolo = f"PROT_{uuid.uuid4().hex[:12].upper()}"
        return {
            "sucesso": True,
            "status": "Em transmissão",
            "protocolo": protocolo,
            "mensagem": "Lote de DPS recebido e em processamento assíncrono simulado."
        }

    def consultar_nfse(self, chave_acesso: str) -> Dict[str, Any]:
        return {
            "sucesso": True,
            "status": "Autorizado",
            "chave_acesso_nacional": chave_acesso,
            "mensagem": "Consulta simulada realizada com sucesso."
        }

    def consultar_eventos(self, chave_acesso: str) -> Dict[str, Any]:
        return {
            "sucesso": True,
            "eventos": [
                {
                    "tipo": "EMISSAO",
                    "data": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "descricao": "NFS-e emitida e autorizada"
                }
            ]
        }

    def cancelar_nfse(self, chave_acesso: str, motivo: str) -> Dict[str, Any]:
        return {
            "sucesso": True,
            "status": "Cancelado",
            "protocolo_cancelamento": f"CANC_{uuid.uuid4().hex[:10].upper()}",
            "mensagem": f"NFS-e {chave_acesso} cancelada com sucesso (Simulado). Motivo: {motivo}"
        }
