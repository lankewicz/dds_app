from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pytz
import pandas as pd
from fpdf import FPDF
from app.core.utils import format_approver_name

class ExportService:
    @staticmethod
    def export_csv(df: pd.DataFrame, output_dir: Path, sort_by: str = "data_solicitacao", order: str = "asc") -> Path:
        if not df.empty: 
            ascending = True if order.lower() == "asc" else False
            sort_cols = [sort_by] if sort_by in df.columns else ["data_solicitacao"]
            if "id_alocacao" in df.columns and "id_alocacao" not in sort_cols:
                sort_cols.append("id_alocacao")
            df = df.sort_values(sort_cols, ascending=ascending)
            cols = ["data_solicitacao", "usuario_origem", "aprovador", "valor_solicitado", "valor_aprovado", "valor_glosa", "valor_repro", "status", "justificativa"]
            df = df[[c for c in cols if c in df.columns]]
            
        tz_br = pytz.timezone('America/Sao_Paulo')
        timestamp = datetime.now(tz_br).strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"solicitacoes_saldo_{timestamp}.csv"
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        return output_path

    @staticmethod
    def export_xlsx(df: pd.DataFrame, output_dir: Path, sort_by: str = "data_solicitacao", order: str = "asc") -> Path:
        tz_br = pytz.timezone('America/Sao_Paulo')
        timestamp = datetime.now(tz_br).strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"relatorio_{timestamp}.xlsx"

        if df.empty:
            df.to_excel(output_path, index=False)
            return output_path

        # 1. Preparar Dados
        ascending = True if order.lower() == "asc" else False
        sort_cols = [sort_by] if sort_by in df.columns else ["data_solicitacao"]
        if "id_alocacao" in df.columns and "id_alocacao" not in sort_cols:
            sort_cols.append("id_alocacao")
        df = df.sort_values(sort_cols, ascending=ascending)
        if "aprovador" in df.columns:
            df["aprovador"] = df["aprovador"].apply(format_approver_name)

        cols_map = {
            "data_solicitacao": "Data",
            "usuario_origem": "Usuário",
            "aprovador": "Aprovador",
            "valor_solicitado": "Solicitado",
            "valor_aprovado": "Aprovado",
            "valor_glosa": "Glosado",
            "valor_repro": "Reprovado",
            "status": "Status",
            "justificativa": "Justificativa"
        }
        df_export = df[[c for c in cols_map.keys() if c in df.columns]].copy()
        df_export = df_export.rename(columns=cols_map)
        num_rows = len(df_export)

        # 2. Criar Excel com Múltiplas Abas e Fórmulas
        with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
            df_export.to_excel(writer, sheet_name='Lançamentos', index=False)
            workbook = writer.book
            worksheet = writer.sheets['Lançamentos']
            
            # Formatos
            header_fmt = workbook.add_format({'bold': True, 'bg_color': '#1e293b', 'font_color': 'white', 'border': 1})
            money_fmt = workbook.add_format({'num_format': 'R$ #,##0.00', 'border': 1})
            total_fmt = workbook.add_format({'bold': True, 'bg_color': '#f8fafc', 'num_format': 'R$ #,##0.00', 'border': 1})
            total_label_fmt = workbook.add_format({'bold': True, 'bg_color': '#f8fafc', 'border': 1, 'align': 'right'})

            for col_num, value in enumerate(df_export.columns.values):
                worksheet.write(0, col_num, value, header_fmt)

            last_row = num_rows + 1
            worksheet.write(last_row, 0, "TOTAIS", total_label_fmt)
            for col_idx in [3, 4, 5, 6]:
                col_letter = chr(65 + col_idx)
                formula = f"=SUM({col_letter}2:{col_letter}{last_row})"
                worksheet.write_formula(last_row, col_idx, formula, total_fmt)
            
            worksheet.set_column('A:A', 12)
            worksheet.set_column('B:C', 25)
            worksheet.set_column('D:G', 15)

            # Aba Dashboard
            worksheet_dash = workbook.add_worksheet('Dashboard')
            status_counts = df['status'].value_counts()
            worksheet_dash.write('A1', 'Status', header_fmt)
            worksheet_dash.write('B1', 'Qtd', header_fmt)
            for i, (status, count) in enumerate(status_counts.items()):
                worksheet_dash.write(i+1, 0, status)
                worksheet_dash.write(i+1, 1, count)

            chart_pie = workbook.add_chart({'type': 'doughnut'})
            chart_pie.add_series({
                'name': 'Distribuição de Status',
                'categories': ['Dashboard', 1, 0, len(status_counts), 0],
                'values':     ['Dashboard', 1, 1, len(status_counts), 1],
                'data_labels': {'percentage': True},
            })
            chart_pie.set_title({'name': 'Distribuição por Status'})
            worksheet_dash.insert_chart('D2', chart_pie)

        return output_path

    @staticmethod
    def export_pdf(df: pd.DataFrame, output_dir: Path, sort_by: str = "data_solicitacao", order: str = "asc") -> Path:
        if not df.empty:
            ascending = True if order.lower() == "asc" else False
            sort_cols = [sort_by] if sort_by in df.columns else ["data_solicitacao"]
            if "id_alocacao" in df.columns and "id_alocacao" not in sort_cols:
                sort_cols.append("id_alocacao")
            df = df.sort_values(sort_cols, ascending=ascending)

        t_sol = float(df["valor_solicitado"].sum()) if not df.empty else 0
        t_app = float(df["valor_aprovado"].sum()) if not df.empty else 0
        t_glosa = float(df["valor_glosa"].sum()) if not df.empty else 0
        t_repro = float(df["valor_repro"].sum()) if not df.empty else 0
        t_reg = len(df)
        
        tz_br = pytz.timezone('America/Sao_Paulo')
        timestamp = datetime.now(tz_br).strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"relatorio_{timestamp}.pdf"
        
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        
        pdf.set_font("Arial", "B", 16)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 10, "Relatório de Gestão Financeira - VExpenses", ln=True, align='L')
        pdf.set_font("Arial", "", 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 5, f"Extraído em: {datetime.now(tz_br).strftime('%d/%m/%Y %H:%M')}", ln=True, align='L')
        pdf.ln(5)
        
        pdf.set_fill_color(248, 250, 252)
        pdf.rect(10, 32, 190, 30, 'F')
        
        pdf.set_xy(15, 35)
        pdf.set_font("Arial", "B", 9)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(45, 5, "TOTAL REGISTROS", align='L')
        pdf.cell(45, 5, "TOTAL SOLICITADO", align='L')
        pdf.cell(45, 5, "TOTAL APROVADO", align='L')
        
        pdf.set_xy(15, 40)
        pdf.set_font("Arial", "B", 12)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(45, 8, f"{t_reg}", align='L')
        pdf.cell(45, 8, f"R$ {t_sol:,.2f}", align='L')
        pdf.cell(45, 8, f"R$ {t_app:,.2f}", align='L')
        
        pdf.set_xy(15, 50)
        pdf.set_font("Arial", "B", 9)
        pdf.set_text_color(180, 83, 9)
        pdf.cell(45, 5, "TOTAL GLOSADO", align='L')
        pdf.set_text_color(185, 28, 28)
        pdf.cell(45, 5, "TOTAL REPROVADO", align='L')
        
        pdf.set_xy(15, 55)
        pdf.set_font("Arial", "B", 12)
        pdf.set_text_color(217, 119, 6)
        pdf.cell(45, 8, f"R$ {t_glosa:,.2f}", align='L')
        pdf.set_text_color(220, 38, 38)
        pdf.cell(45, 8, f"R$ {t_repro:,.2f}", align='L')
        
        pdf.set_xy(10, 68)
        pdf.ln(5)
        
        col_widths = [18, 35, 25, 20, 20, 20, 20, 22]
        headers = ["Data", "Usuário", "Aprovador", "Solicit.", "Aprov.", "Glosa", "Repro", "Status"]
        
        pdf.set_fill_color(30, 41, 59)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 8)
        for i, h in enumerate(headers):
            pdf.cell(col_widths[i], 8, h, border=0, fill=True, align='C')
        pdf.ln()
        
        pdf.set_text_color(30, 41, 59)
        pdf.set_font("Arial", "", 7)
        fill = False
        for _, row in df.iterrows():
            aprov = format_approver_name(row.get("aprovador", "-"))
            sol = float(row.get("valor_solicitado", 0))
            app = float(row.get("valor_aprovado", 0))
            glosa = float(row.get("valor_glosa", 0))
            repro = float(row.get("valor_repro", 0))

            pdf.set_fill_color(248, 250, 252) if fill else pdf.set_fill_color(255, 255, 255)
            pdf.cell(col_widths[0], 6, str(row.get("data_solicitacao", ""))[:10], border='B', fill=fill, align='C')
            pdf.cell(col_widths[1], 6, str(row.get("usuario_origem", "-"))[:20], border='B', fill=fill)
            pdf.cell(col_widths[2], 6, aprov[:15], border='B', fill=fill)
            pdf.cell(col_widths[3], 6, f"{sol:.2f}", border='B', fill=fill, align='R')
            pdf.cell(col_widths[4], 6, f"{app:.2f}", border='B', fill=fill, align='R')
            
            if glosa > 0: pdf.set_text_color(217, 119, 6)
            pdf.cell(col_widths[5], 6, f"{glosa:.2f}", border='B', fill=fill, align='R')
            pdf.set_text_color(30, 41, 59)
            
            if repro > 0: pdf.set_text_color(220, 38, 38)
            pdf.cell(col_widths[6], 6, f"{repro:.2f}", border='B', fill=fill, align='R')
            pdf.set_text_color(30, 41, 59)
            
            pdf.cell(col_widths[7], 6, str(row.get("status", "-"))[:12], border='B', fill=fill, align='C')
            pdf.ln()
            fill = not fill
            
        pdf.output(str(output_path))
        return output_path
