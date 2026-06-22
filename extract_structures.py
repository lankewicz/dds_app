import os
import re
import json
import fitz  # PyMuPDF
from PIL import Image, ImageChops
from io import BytesIO
from pathlib import Path
from typing import Union, Optional, Dict, List
from google.cloud import storage

# Carregar credenciais locais do Firebase
local_key = r"d:\programas\DDS\firebase_config.json"
if os.path.exists(local_key):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_key

storage_client = storage.Client()
BUCKET_NAME = "dds-treinamentos.firebasestorage.app"
bucket = storage_client.bucket(BUCKET_NAME)

BASE_INPUT_DIR = r"D:\CE\Engenharia - Documentos\OBRAS PARTICULARES\NORMAS TECNICAS\COPEL 2022"
BASE_OUTPUT_DIR = r"d:\programas\DDS\dds-webtools\controle_projetos\static\images\estruturas"

NETWORKS = ["RDA", "RDC", "RDP", "RSI"]

def nome_arquivo_seguro(texto: str) -> str:
    texto = texto.upper().strip()
    texto = texto.replace("–", "-").replace("—", "-")
    texto = re.sub(r"\s+", "-", texto)
    texto = re.sub(r"[^A-Z0-9_\-]", "_", texto)
    texto = re.sub(r"_+", "_", texto)
    return texto.strip("_-")

def renderizar_clip_pdf(
    page: fitz.Page,
    clip: fitz.Rect,
    escala: float = 4.0
) -> Image.Image:
    pix = page.get_pixmap(
        matrix=fitz.Matrix(escala, escala),
        clip=clip,
        alpha=False
    )
    img = Image.open(BytesIO(pix.tobytes("png")))
    return img.convert("RGB")

def aparar_margens_brancas(
    img: Image.Image,
    tolerancia: int = 245,
    margem: int = 35
) -> Image.Image:
    """
    Remove margens brancas ao redor do desenho/tabela.
    """
    img = img.convert("RGB")
    fundo = Image.new("RGB", img.size, (255, 255, 255))
    diff = ImageChops.difference(img, fundo)
    gray = diff.convert("L")

    # Quanto menor o valor aqui, mais sensível ao cinza/claro.
    mask = gray.point(lambda p: 255 if p > (255 - tolerancia) else 0)
    bbox = mask.getbbox()

    if not bbox:
        return img

    left, top, right, bottom = bbox
    left = max(0, left - margem)
    top = max(0, top - margem)
    right = min(img.width, right + margem)
    bottom = min(img.height, bottom + margem)

    return img.crop((left, top, right, bottom))

def clip_pagina_1_estrutura_completa(page: fitz.Page) -> fitz.Rect:
    """
    Página 1:
    recorta a área da estrutura de transição completa,
    removendo cabeçalho e rodapé.
    """
    w = page.rect.width
    h = page.rect.height
    return fitz.Rect(
        w * 0.04,   # esquerda
        h * 0.12,   # abaixo do cabeçalho
        w * 0.96,   # direita
        h * 0.94    # acima do rodapé
    )

def clip_pagina_2_estrutura_base(page: fitz.Page) -> fitz.Rect:
    """
    Página 2:
    recorta apenas o desenho da estrutura base,
    removendo cabeçalho, observações e rodapé.
    """
    w = page.rect.width
    h = page.rect.height
    return fitz.Rect(
        w * 0.05,
        h * 0.12,
        w * 0.95,
        h * 0.72
    )

def upload_image_to_gcs(img: Image.Image, dest_blob_name: str) -> str:
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_bytes = img_byte_arr.getvalue()
    
    blob = bucket.blob(dest_blob_name)
    blob.upload_from_string(img_bytes, content_type="image/png")
    try:
        blob.make_public()
    except Exception as e:
        print(f"      Erro ao tornar blob público: {e}")
    return f"https://storage.googleapis.com/{BUCKET_NAME}/{dest_blob_name}"

def extract_structures():
    print("Iniciando extração de estruturas e upload para o Firebase Storage...")
    os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)
    
    index_data = {}
    
    for net in NETWORKS:
        net_dir = os.path.join(BASE_INPUT_DIR, net)
        if not os.path.exists(net_dir):
            print(f"Pasta não encontrada: {net_dir}")
            continue
            
        print(f"\nProcessando rede: {net}")
        index_data[net] = []
        
        net_output_dir = os.path.join(BASE_OUTPUT_DIR, net)
        os.makedirs(net_output_dir, exist_ok=True)
        
        files = [f for f in os.listdir(net_dir) if f.lower().endswith(".pdf")]
        for file in files:
            structure_name = os.path.splitext(file)[0]
            pdf_path = os.path.join(net_dir, file)
            
            print(f"  Estrutura: {structure_name} ({file})")
            
            try:
                doc = fitz.open(pdf_path)
                num_pages = len(doc)
                if num_pages == 0:
                    print(f"    PDF vazio: {file}")
                    doc.close()
                    continue
                
                url_desenho = None
                url_titulo = None
                
                # Processar página 1 (sempre esperado)
                page1 = doc[0]
                clip1 = clip_pagina_1_estrutura_completa(page1)
                img1 = renderizar_clip_pdf(page1, clip1, escala=4.0)
                img1 = aparar_margens_brancas(img1, tolerancia=245, margem=45)
                
                # Salvar localmente
                desenho_filename = f"{structure_name}_desenho.png"
                out_path1 = os.path.join(net_output_dir, desenho_filename)
                img1.save(out_path1)
                
                # Upload para Firebase Storage
                blob_name1 = f"estruturas/{net}/{desenho_filename}"
                print(f"    Carregando desenho no Firebase Storage...")
                url_desenho = upload_image_to_gcs(img1, blob_name1)
                
                # Processar página 2 (se existir)
                if num_pages >= 2:
                    page2 = doc[1]
                    clip2 = clip_pagina_2_estrutura_base(page2)
                    img2 = renderizar_clip_pdf(page2, clip2, escala=4.0)
                    img2 = aparar_margens_brancas(img2, tolerancia=245, margem=45)
                    
                    # Salvar localmente
                    titulo_filename = f"{structure_name}_titulo.png"
                    out_path2 = os.path.join(net_output_dir, titulo_filename)
                    img2.save(out_path2)
                    
                    # Upload para Firebase Storage
                    blob_name2 = f"estruturas/{net}/{titulo_filename}"
                    print(f"    Carregando título/detalhe no Firebase Storage...")
                    url_titulo = upload_image_to_gcs(img2, blob_name2)
                
                doc.close()
                
                # Salvar no index com as URLs públicas do Firebase Storage
                index_data[net].append({
                    "estrutura": structure_name,
                    "desenho": url_desenho,
                    "titulo": url_titulo
                })
                print(f"    Sucesso: desenho={url_desenho}, titulo={url_titulo}")
                
            except Exception as e:
                print(f"    Erro ao processar {file}: {e}")
                
    # Salvar index JSON com as URLs de storage
    index_path = os.path.join(BASE_OUTPUT_DIR, "estruturas_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=4)
        
    print(f"\nÍndice JSON salvo com sucesso em: {index_path}")

if __name__ == "__main__":
    extract_structures()
