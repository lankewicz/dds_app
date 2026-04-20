# Module: firebase_sender.py
# Description: Envia arquivos processados para o Firebase Storage sob o prefixo 'DDSv2/'
#              e atualiza o lista.json listando todos os blobs existentes em 'DDSv2/'.
#              Também move pastas locais para 'ENVIADOS' ou 'IGNORADOS' após a tentativa de envio.
# Change Log:
#   29-05-25:  • Criação do módulo para integração com Firebase Storage.
#   30-05-25:  • Ajustado upload para prefixar 'DDSv2/' nos paths de Storage.
#   31-05-25:  • Adicionado download automático de 'DDSv2/lista.json' após atualização.
#   12-06-25:  • Removida dependência de Firestore; verificação de duplicidade via Storage API.
#   13-06-25:  • Pastas movidas para 'ENVIADOS' ou 'IGNORADOS' conforme resultado do upload.
#   13-06-25:  • Atualização de lista.json para listar todos os arquivos (blobs) em 'DDSv2/'.
# Guia de Comentários:
#   - upload_files(): faz upload em 'DDSv2/<rel_folder>/<file>' e checa se blob já existe.
#       • Se algum arquivo já existir, considera a pasta inteira como 'IGNORADOS'.
#       • Se nenhum arquivo existir, faz upload e retorna True (sucesso).
#   - update_list_json(): lista todos os blobs sob 'DDSv2/' e salva em 'lista.json' no root local
#       e no Storage (em 'lista.json').
#   - move_to_sent(): move a pasta local para 'ENVIADOS'.
#   - move_to_ignored(): move a pasta local para 'IGNORADOS'.

import os
import logging
import json
from firebase_admin import credentials, initialize_app, storage
from config import FIREBASE_CREDENTIAL_PATH, FIREBASE_BUCKET, DDS_BASE, SENT_BASE, IGNORED_BASE

logger = logging.getLogger(__name__)

# Inicializa Firebase Admin SDK para storage
cred = credentials.Certificate(FIREBASE_CREDENTIAL_PATH)
initialize_app(cred, {'storageBucket': FIREBASE_BUCKET})
bucket = storage.bucket()

def upload_files(folder: str) -> bool:
    """
    Tenta fazer upload de todos os arquivos em 'folder' para o Storage sob 'DDSv2/<rel_folder>/'.
    - Se **qualquer** blob dentro de 'DDSv2/<rel_folder>/' já existir, interrompe e retorna False,
      indicando que a pasta deve ser movida para 'IGNORADOS'.
    - Caso contrário, faz upload de todos e retorna True.
    """
    rel_folder = os.path.relpath(folder, DDS_BASE)  # ex: '2025-06-10 - TEMA X'
    # Primeiro, verifica duplicidade: percorre todos os arquivos locais e olha se blob existe
    for root, _, files in os.walk(folder):
        for f in files:
            blob_path = f"DDSv2/{rel_folder}/{f}"
            blob = bucket.blob(blob_path)
            if blob.exists():
                logger.warning("Blob já existe (%s). Pasta marcada como ignorada.", blob_path)
                return False  # qualquer arquivo já existe → descartar pasta inteira

    # Se chegou aqui, nenhum arquivo existe: faz upload de cada arquivo
    for root, _, files in os.walk(folder):
        for f in files:
            local_path = os.path.join(root, f)
            blob_path = f"DDSv2/{rel_folder}/{f}"
            blob = bucket.blob(blob_path)
            try:
                blob.upload_from_filename(local_path)
                logger.info("Upload concluído: %s", blob_path)
            except Exception as e:
                logger.error("Falha no upload de %s: %s", blob_path, e)
                # Se falhar algum, considerar tudo como erro (mas não mover para IGNORED)
                return False

    return True

def update_list_json() -> None:
    """
    Lista todos os blobs existentes sob o prefixo 'DDSv2/' no Storage
    e gera um arquivo 'lista.json' na raiz local do projeto, contendo:
        { "files": [<lista de paths completos dos blobs>] }
    Em seguida, faz upload de 'lista.json' para o Storage no path 'lista.json'.
    """
    blobs = bucket.list_blobs(prefix="DDSv2/")
    all_paths = [blob.name for blob in blobs]  # ex: ['DDSv2/2025-06-10 - TEMA X/arq1.jpg', ...]
    data = {"files": sorted(all_paths)}

    # 1) Cria arquivo 'lista.json' na raiz do projeto
    local_path = os.path.join(os.getcwd(), 'lista.json')
    try:
        with open(local_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Arquivo 'lista.json' criado em: %s", local_path)
    except Exception as e:
        logger.error("Erro criando lista.json local: %s", e)
        return

    # 2) Faz upload de 'lista.json' para o Storage no path raiz 'lista.json'
    try:
        blob = bucket.blob('DDSv2/lista.json')
        blob.upload_from_filename(local_path)
        logger.info("Arquivo 'lista.json' enviado para o bucket em 'lista.json'.")
    except Exception as e:
        logger.error("Erro ao enviar lista.json para o bucket: %s", e)

def move_to_sent(folder: str) -> None:
    """
    Move o diretório 'folder' (em DDS_BASE) para a pasta 'ENVIADOS' (SENT_BASE),
    preservando o nome da subpasta.
    """
    os.makedirs(SENT_BASE, exist_ok=True)
    dest = os.path.join(SENT_BASE, os.path.basename(folder))
    try:
        os.replace(folder, dest)
        logger.info("Pasta movida para ENVIADOS: %s", dest)
    except Exception as e:
        logger.error("Erro movendo pasta para ENVIADOS: %s", e)

def move_to_ignored(folder: str) -> None:
    """
    Move o diretório 'folder' (em DDS_BASE) para a pasta 'IGNORADOS' (IGNORED_BASE),
    preservando o nome da subpasta.
    """
    os.makedirs(IGNORED_BASE, exist_ok=True)
    dest = os.path.join(IGNORED_BASE, os.path.basename(folder))
    try:
        os.replace(folder, dest)
        logger.info("Pasta movida para IGNORADOS: %s", dest)
    except Exception as e:
        logger.error("Erro movendo pasta para IGNORADOS: %s", e)


def delete_folder_in_storage(folder_name: str) -> bool:
    """
    Deleta todos os blobs em 'DDSv2/<folder_name>/' no Storage.
    Retorna True se ao menos um blob foi deletado, False caso não exista nada.
    """
    prefix = f"DDSv2/{folder_name}/"
    blobs = list(bucket.list_blobs(prefix=prefix))
    if not blobs:
        logger.warning("Nenhum blob encontrado para apagar em: %s", prefix)
        return False

    for blob in blobs:
        try:
            blob.delete()
            logger.info("Blob excluído: %s", blob.name)
        except Exception as e:
            logger.error("Falha ao deletar %s: %s", blob.name, e)
            # continuar tentando apagar o resto
    return True