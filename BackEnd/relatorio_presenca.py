# relatorio_presenca.py - Geração de relatório de presença por equipe em formato de calendário
# Versão melhorada visualmente com cores modernas e estatísticas

import os
import sys
import datetime
import calendar
from collections import defaultdict
from functools import partial

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.pagesizes import A4
from reportlab.graphics.shapes import Drawing, Rect, String, Circle
from reportlab.graphics.charts.piecharts import Pie
from reportlab.platypus.flowables import Flowable

import firebase_admin
from firebase_admin import credentials, firestore

from visual_utils import header_footer

# ==================== PALETA DE CORES MODERNA ====================
COR_PRESENTE = colors.HexColor('#10B981')      # Verde moderno
COR_AUSENTE = colors.HexColor('#EF4444')       # Vermelho moderno
COR_SEM_DDS = colors.HexColor('#F3F4F6')       # Cinza claro
COR_HEADER_CAL = colors.HexColor('#1E3A8A')    # Azul escuro
COR_TEXTO_HEADER = colors.white
COR_BORDA = colors.HexColor('#9CA3AF')         # Cinza médio
COR_DESTAQUE = colors.HexColor('#F59E0B')      # Laranja

MESES_PT = ["janeiro","fevereiro","março","abril","maio","junho",
            "julho","agosto","setembro","outubro","novembro","dezembro"]

def carregar_db():
    """Conecta e retorna o cliente do Firestore."""
    base = os.path.dirname(os.path.abspath(__file__))
    tentativas = [
        os.path.join(base, 'init', 'serviceAccountKey.json'),
        os.path.join(base, os.pardir, 'init', 'serviceAccountKey.json'),
    ]
    for sa_path in tentativas:
        sa_path = os.path.normpath(sa_path)
        if os.path.isfile(sa_path):
            if not firebase_admin._apps:
                cred = credentials.Certificate(sa_path)
                firebase_admin.initialize_app(cred)
            return firestore.client()
    raise FileNotFoundError("Arquivo serviceAccountKey.json não encontrado.")

def buscar_e_agrupar(db):
    """Busca registros no Firestore e agrupa por data."""
    grupos = defaultdict(list)
    for doc in db.collection('DDS').stream():
        d = doc.to_dict()
        try:
            date_obj = datetime.datetime.strptime(d.get('headerDate', ''), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            continue
        grupos[date_obj].append({
            'equipe': d.get('equipe', '—'),
            'eletricistas': d.get('eletricistas', []),
        })
    return grupos


class BarraProgressoFlowable(Flowable):
    """Flowable customizado para barra de progresso."""
    
    def __init__(self, percentual, largura=150, altura=20):
        Flowable.__init__(self)
        self.percentual = percentual
        self.largura = largura
        self.altura = altura
        # informa o tamanho para o mecanismo de layout
        self.width = largura
        self.height = altura
    
    def wrap(self, availWidth, availHeight):
        # ReportLab usa isso para calcular a altura da linha
        return self.width, self.height
        
    def draw(self):
        # Fundo da barra
        self.canv.setFillColor(COR_SEM_DDS)
        self.canv.setStrokeColor(COR_BORDA)
        self.canv.setLineWidth(0.5)
        self.canv.rect(0, 0, self.largura, self.altura, fill=1, stroke=1)
        
        # Barra de progresso
        largura_progresso = self.largura * (self.percentual / 100)
        
        if self.percentual >= 80:
            cor_barra = COR_PRESENTE
        elif self.percentual >= 60:
            cor_barra = COR_DESTAQUE
        else:
            cor_barra = COR_AUSENTE
        
        self.canv.setFillColor(cor_barra)
        self.canv.setStrokeColor(cor_barra)
        self.canv.rect(0, 0, largura_progresso, self.altura, fill=1, stroke=0)
        
        # Texto do percentual
        self.canv.setFont('Helvetica-Bold', 10)
        self.canv.setFillColor(colors.white if self.percentual > 30 else colors.black)
        texto = f'{self.percentual:.0f}%'
        texto_largura = self.canv.stringWidth(texto, 'Helvetica-Bold', 10)
        self.canv.drawString((self.largura - texto_largura) / 2, 5, texto)


def gerar_pdf_presenca(grupos, output_path):
    """Função principal de geração do PDF com melhorias visuais."""
    styles = getSampleStyleSheet()
    
    # Estilos personalizados
    estilo_titulo = ParagraphStyle(
        'TituloEquipe',
        parent=styles['Heading1'],
        fontSize=13,
        textColor=COR_HEADER_CAL,
        spaceAfter=4,
        fontName='Helvetica-Bold'
    )
    
    estilo_subtitulo = ParagraphStyle(
        'SubtituloMes',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#6B7280'),
        spaceAfter=10,
        fontName='Helvetica-Oblique'
    )
    
    estilo_participante = ParagraphStyle(
        'Participante',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=10,
        leftIndent=3
    )
    
    estilo_stats = ParagraphStyle(
        'Stats',
        parent=styles['Normal'],
        fontSize=9,
        fontName='Helvetica-Bold',
        textColor=COR_HEADER_CAL,
        leading=11
    )
    
    estilo_legenda = ParagraphStyle(
        'Legenda',
        parent=styles['Normal'],
        fontSize=8,
        leading=10
    )

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
        topMargin=3*cm,
        bottomMargin=2*cm
    )
    story = []

    hoje = datetime.date.today()
    equipes = sorted({r['equipe'] for regs in grupos.values() for r in regs if r['equipe'] != '—'})
    equipes_todas = sorted({r['equipe'] for regs in grupos.values() for r in regs if r['equipe'] != '—'})
    datas_dds = sorted(grupos.keys())
    meses = sorted({(d.year, d.month) for d in datas_dds})

  
    def _ranking_equipes_no_mes(_ano: int, _mes: int) -> list[str]:
        """
        Ordena por:
          1) Presença (%) desc, considerando SOMENTE dias em que houve DDS
          2) Equipe (nome) asc
        """
        # equipes existentes no mês (a partir dos registros)
        equipes_mes_set = set()
        # denominador: dias do mês em que houve DDS (qualquer equipe)
        dias_com_dds = [
            d for d in grupos.keys()
            if d.year == _ano and d.month == _mes
        ]
        total_dias_dds = len(dias_com_dds)

        # presenças por equipe (no máximo 1 presença por dia)
        presencas = defaultdict(int)
        for d in dias_com_dds:
            regs = grupos.get(d) or []
            equipes_no_dia = {
                (r.get("equipe") or "—").strip()
                for r in regs
                if (r.get("equipe") or "—").strip() not in ("", "—")
            }
            for eq in equipes_no_dia:
                equipes_mes_set.add(eq)
                presencas[eq] += 1

        # monta lista com percentual
        itens = []
        for eq in sorted(equipes_mes_set):
            p = presencas.get(eq, 0)
            perc = (p / total_dias_dds * 100.0) if total_dias_dds > 0 else 0.0
            itens.append((eq, perc))

        # ordena por presença% desc, depois equipe asc
        itens.sort(key=lambda x: (-x[1], x[0].lower()))
        return [eq for eq, _ in itens]

    # Geração por mês: equipes ordenadas por quem mais participou naquele mês
    for ano, mes in meses:
        equipes_mes = _ranking_equipes_no_mes(ano, mes)
        # fallback se por algum motivo não houver contagem (mantém compatibilidade)
        if not equipes_mes:
            equipes_mes = [e for e in equipes_todas]

        for equipe in equipes_mes:
            # =============== CABEÇALHO DA EQUIPE ===============
            #titulo = Paragraph(
            #    f'<b>Equipe: {equipe}</b>',
            #    estilo_titulo
            #)

            # =============== CABEÇALHO DA EQUIPE ===============
            titulo_label = Paragraph('<b>Equipe:</b>', estilo_titulo)
            titulo_valor = Paragraph(f'<b>{equipe}</b>', estilo_titulo)
            
            
            # =============== LISTA DE INTEGRANTES ===============
            participantes_raw = {
                eletricista.strip().upper()
                for d, regs in grupos.items()
                if d.year == ano and d.month == mes
                for r in regs
                if r['equipe'] == equipe
                for eletricista in r.get('eletricistas', [])
            }
            participantes = sorted(list(participantes_raw))
            
            label_integrantes = Paragraph('<b>INTEGRANTES:</b>', estilo_stats)
            lista_participantes = [Paragraph(f'• {p}', estilo_participante) for p in participantes]
            
            if not lista_participantes:
                lista_participantes = [Paragraph('— Nenhum integrante', estilo_participante)]
            
            # =============== CALENDÁRIO ===============
            cal = calendar.Calendar(firstweekday=6)
            dias_do_mes = list(cal.itermonthdates(ano, mes))
            
            # Cabeçalho do calendário
            data_calendario = [['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb']]
            
            linha_calendario = []
            bg_colors = []
            text_colors = []
            
            # Estatísticas
            presencas = 0
            ausencias = 0
            total_dias_uteis = 0
            
            for dia in dias_do_mes:
                if len(linha_calendario) == 7:
                    data_calendario.append(linha_calendario)
                    linha_calendario = []

                if dia.month != mes:
                    linha_calendario.append('')
                    bg_colors.append(None)
                    text_colors.append(colors.black)
                    continue

                cor_fundo = None
                cor_texto = colors.black
                
                if dia in grupos:
                    # Só considera dias em que houve DDS
                    total_dias_uteis += 1
                    equipes_no_dia = {r['equipe'] for r in grupos[dia]}
                    if equipe in equipes_no_dia:
                        cor_fundo = COR_PRESENTE
                        cor_texto = colors.white
                        presencas += 1
                    else:
                        cor_fundo = COR_AUSENTE
                        cor_texto = colors.white
                        ausencias += 1
                else:
                    # Dia sem DDS → não entra no cálculo
                    cor_fundo = COR_SEM_DDS
  
                linha_calendario.append(f'{dia.day}')
                bg_colors.append(cor_fundo)
                text_colors.append(cor_texto)
            
            if linha_calendario:
                data_calendario.append(linha_calendario)

            # Criar tabela do calendário
            tabela_calendario = Table(
                data_calendario,
                colWidths=[1.15*cm]*7,
                rowHeights=[0.85*cm]*len(data_calendario)
            )
            
            style_cmds = [
                ('GRID', (0,0), (-1,-1), 0.5, COR_BORDA),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('BACKGROUND', (0,0), (-1,0), COR_HEADER_CAL),
                ('TEXTCOLOR', (0,0), (-1,0), COR_TEXTO_HEADER),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,0), 8),
            ]

            # Aplicar cores nas células
            row_idx = 1
            col_idx = 0
            for i, cor in enumerate(bg_colors):
                if cor is not None:
                    style_cmds.append(('BACKGROUND', (col_idx, row_idx), (col_idx, row_idx), cor))
                    style_cmds.append(('TEXTCOLOR', (col_idx, row_idx), (col_idx, row_idx), text_colors[i]))
                    style_cmds.append(('FONTNAME', (col_idx, row_idx), (col_idx, row_idx), 'Helvetica-Bold'))
                col_idx += 1
                if col_idx == 7:
                    col_idx = 0
                    row_idx += 1
            
            tabela_calendario.setStyle(TableStyle(style_cmds))
            
            # =============== ESTATÍSTICAS ===============
            percentual_presenca = (presencas / total_dias_uteis * 100) if total_dias_uteis > 0 else 0
            
            # Barra de progresso
            barra = BarraProgressoFlowable(percentual_presenca, largura=8.5*cm, altura=0.6*cm)          
              
            # Texto de estatísticas
            stats_texto = Paragraph(
                f'<b>Presença: {percentual_presenca:.0f}%</b><br/>'
                f'<font size=8>Participações: {presencas} | Ausências: {ausencias}</font>',
                estilo_stats
            )
            
            # Legenda aprimorada com cores (horizontal, como no layout desejado)
            legenda_data = [[
                Paragraph('<font color="#10B981">■</font> Participou', estilo_legenda),
                Paragraph('<font color="#EF4444">■</font> Não participou', estilo_legenda),
                Paragraph('<font color="#9CA3AF">■</font> Sem DDS', estilo_legenda),
            ]]
            
            tabela_legenda = Table(
                legenda_data,
                colWidths=[3*cm, 3*cm, 3*cm],
                rowHeights=[0.5*cm]
            )
            tabela_legenda.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 4),
            ]))
            # =============== MONTAGEM DO LAYOUT ===============
            
            # Bloco esquerdo: Info da equipe
#            bloco_esquerda_content = [
#                [titulo],
#                [subtitulo],
#                [Spacer(1, 0.2*cm)],
#                [label_integrantes],
#            ] + [[p] for p in lista_participantes]
            bloco_esquerda_content = [
                [titulo_label],
                [titulo_valor],
                [Spacer(1, 0.15*cm)],
                [label_integrantes],
            ] + [[p] for p in lista_participantes]



            bloco_esquerda = Table(
                bloco_esquerda_content,
                colWidths=[7*cm]
            )
            bloco_esquerda.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ]))
            
            # Bloco direito: Calendário, legenda e barra de presença
            bloco_direita_content = [
                [tabela_calendario],
                #[Spacer(1, 0.1*cm)],
                [tabela_legenda],
                #[Spacer(1, 0.1*cm)],
                [barra],                # só a barra, ocupando os 8.5 cm da coluna
                #[Spacer(1, 0.1*cm)],
                [stats_texto]
            ]
            
            bloco_direita = Table(
                bloco_direita_content,
                colWidths=[8.5*cm]
            )
            bloco_direita.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ]))
            
            # Layout final
            layout_principal = Table(
                [[bloco_esquerda, bloco_direita]],
                colWidths=[7.5*cm, 9*cm],
                style=[
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ]
            )
            
            # Adicionar linha separadora sutil
            linha_sep = Table([['']], colWidths=[17*cm], rowHeights=[0.05*cm])
            linha_sep.setStyle(TableStyle([
                ('LINEABOVE', (0,0), (-1,-1), 0.5, COR_BORDA),
            ]))
            
            # Adicionar à story
            story.append(KeepTogether([
                layout_principal,
                Spacer(1, 0.5*cm),
                linha_sep,
                Spacer(1, 0.8*cm)
            ]))

    # =============== GERAR PDF ===============
    # titulo_relatorio = "DDS - Relatório de Presença por Equipe"
    # Como o comando filtra por mês, normalmente "meses" terá apenas 1 item (ano, mes).
    # Usamos isso para exibir "Dezembro de 2025" no cabeçalho.
    if meses:
        ano_h, mes_h = meses[0]
        titulo_relatorio = f"DDS - Relatório de Presença por Equipe\n{MESES_PT[mes_h-1].capitalize()} de {ano_h}"
    else:
        titulo_relatorio = "DDS - Relatório de Presença por Equipe"
    on_every_page = partial(header_footer, titulo=titulo_relatorio)
    
    doc.build(story, onFirstPage=on_every_page, onLaterPages=on_every_page)
    print(f"✅ Relatório de presença gerado: {output_path}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Gerar relatório de presença DDS.')
    parser.add_argument('--saida', default='relatorio_presenca.pdf', 
                       help='Caminho do arquivo PDF de saída')
    args = parser.parse_args()

    try:
        db = carregar_db()
        grupos = buscar_e_agrupar(db)

        if not grupos:
            print("Nenhum registro encontrado no banco de dados.")
            sys.exit(1)

        gerar_pdf_presenca(grupos, args.saida)
        print(f"✅ Relatório gerado com sucesso: {args.saida}")

    except Exception as e:
        print(f"❌ Erro ao gerar relatório: {e}")
        sys.exit(1)