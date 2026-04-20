# visual_utils.py - Cabeçalho com layout de 3 colunas (20% | 60% | 20%)

import os
import datetime
from reportlab.lib.units import cm

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

# --- CONFIGURAÇÃO DOS CAMINHOS ---
BASE_DIR = os.path.dirname(__file__)
LOGO_ESQUERDA = os.path.join(BASE_DIR, 'init', 'imagens', 'logo_chico_relat.png')
LOGO_DIREITA = os.path.join(BASE_DIR, 'init', 'imagens', 'logo_dds_relat.png')


def header_footer(canvas, doc, titulo='DDS - Relatório'):
    """
    Desenha um cabeçalho estruturado em 3 colunas e um rodapé padrão.
    """
    canvas.saveState()
    
    # --- Configurações Gerais ---
    width, height = canvas._pagesize
    largura_util = width - doc.leftMargin - doc.rightMargin
    altura_logo_cm = 1.2  # Altura padrão para os logos
    y_pos_logos = height - (1.2 * cm) - (altura_logo_cm * cm) # Posição Y dos logos
    y_pos_titulo = height - (1.8 * cm) # Posição Y do título

    # --- Coluna 1: Logo da Esquerda (20%) ---
    coluna1_x = doc.leftMargin
    if os.path.exists(LOGO_ESQUERDA):
        try:
            canvas.drawImage(LOGO_ESQUERDA,
                             coluna1_x,
                             y_pos_logos,
                             height=altura_logo_cm * cm,
                             preserveAspectRatio=True,
                             mask='auto',
                             anchor='sw') # 'sw' = south-west (canto inferior esquerdo)
        except Exception as e:
            print(f"Erro ao desenhar logo esquerda: {e}")

    # --- Coluna 2: Título (60% Centralizado) ---
    coluna2_x_inicio = doc.leftMargin + (largura_util * 0.20)
    largura_coluna2 = largura_util * 0.60
    
    # --- Coluna 2: Título (suporte a múltiplas linhas) ---
    linhas_titulo = str(titulo).splitlines()

    canvas.setFont('Helvetica-Bold', 14)
    line_height = 16  # espaço entre linhas

    # Centraliza o bloco de linhas verticalmente em torno de y_pos_titulo
    total_height = line_height * len(linhas_titulo)
    y_atual = y_pos_titulo + (total_height / 2) - line_height

    for linha in linhas_titulo:
        canvas.drawCentredString(
            coluna2_x_inicio + (largura_coluna2 / 2),
            y_atual,
            linha
        )
        y_atual -= line_height

    # --- Coluna 3: Logo da Direita (20%) ---
    if os.path.exists(LOGO_DIREITA) and PILImage:
        try:
            img = PILImage.open(LOGO_DIREITA)
            img_w, img_h = img.size
            
            # Calcula a largura proporcional à altura definida
            aspect_ratio = img_w / img_h
            largura_logo = (altura_logo_cm * cm) * aspect_ratio
            
            # Calcula a posição X para alinhar à direita
            coluna3_x_final = width - doc.rightMargin
            logo_x = coluna3_x_final - largura_logo
            
            canvas.drawImage(LOGO_DIREITA,
                             logo_x,
                             y_pos_logos,
                             height=altura_logo_cm * cm,
                             preserveAspectRatio=True,
                             mask='auto',
                             anchor='sw')
        except Exception as e:
            print(f"Erro ao desenhar logo direita: {e}")

    # --- Rodapé (Ocupa a largura total) ---
    canvas.setFont('Helvetica', 9)
    canvas.drawString(doc.leftMargin,
                      doc.bottomMargin / 2,
                      f'Data da geração: {datetime.date.today().strftime("%d/%m/%Y")}')
    canvas.drawCentredString(width / 2,
                             doc.bottomMargin / 2,
                             f'Página {canvas.getPageNumber()}')

    canvas.restoreState()