# -----------------------------------------------------------------------------
# Módulo: email_templates.py
# Versão: 1.0
#
# Descrição:
#   Centraliza todos os templates de e-mail do sistema, garantindo
#   consistência visual e facilitando manutenção.
#
# Uso:
#   from email_templates import EmailTemplates
#   EmailTemplates.sucesso_programado(titulo="Segurança", data="17/11/2025")
# -----------------------------------------------------------------------------

from typing import Dict, List, Optional
import datetime as dt


class EmailTemplates:
    """Gerenciador centralizado de templates de e-mail."""
    
    # =========================================================================
    # ESTILOS BASE
    # =========================================================================
    
    @staticmethod
    def _base_style() -> str:
        """Retorna CSS base para todos os e-mails."""
        return """
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                color: #333;
                margin: 0;
                padding: 0;
                background-color: #f4f6f9;
            }
            .container {
                max-width: 600px;
                margin: 20px auto;
                background-color: #ffffff;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }
            .header {
                padding: 30px 20px;
                text-align: center;
            }
            .header.success {
                background: linear-gradient(135deg, #0b5ed7 0%, #0d6efd 100%);
                color: white;
            }
            .header.warning {
                background: linear-gradient(135deg, #ffc107 0%, #ffb300 100%);
                color: #333;
            }
            .header.error {
                background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
                color: white;
            }
            .header.info {
                background: linear-gradient(135deg, #6c757d 0%, #5a6268 100%);
                color: white;
            }
            .header h1 {
                margin: 0;
                font-size: 24px;
                font-weight: 600;
            }
            .header .icon {
                font-size: 48px;
                margin-bottom: 10px;
            }
            .content {
                padding: 30px;
            }
            .info-box {
                background-color: #f8f9fa;
                border-left: 4px solid #0d6efd;
                padding: 15px;
                margin: 20px 0;
                border-radius: 4px;
            }
            .info-box.warning {
                border-left-color: #ffc107;
                background-color: #fff3cd;
            }
            .info-box strong {
                color: #0d6efd;
            }
            .info-box.warning strong {
                color: #856404;
            }
            .action-list {
                background-color: #f8f9fa;
                padding: 15px 20px;
                border-radius: 8px;
                margin: 20px 0;
            }
            .action-list ul {
                margin: 10px 0;
                padding-left: 20px;
            }
            .action-list li {
                margin: 8px 0;
            }
            .code {
                background-color: #f1f3f5;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Courier New', monospace;
                font-size: 14px;
                color: #d63384;
            }
            .footer {
                background-color: #f8f9fa;
                padding: 20px;
                text-align: center;
                color: #6c757d;
                font-size: 13px;
                border-top: 1px solid #dee2e6;
            }
            .button {
                display: inline-block;
                padding: 12px 24px;
                background-color: #0d6efd;
                color: white;
                text-decoration: none;
                border-radius: 6px;
                font-weight: 500;
                margin: 10px 0;
            }
            .divider {
                height: 1px;
                background-color: #dee2e6;
                margin: 25px 0;
            }

            /* Lista de treinamentos agendados */
            .schedule {
                margin: 18px 0;
            }
            .schedule h2 {
                margin: 0 0 10px 0;
                font-size: 16px;
                font-weight: 600;
                color: #333;
            }
            .schedule .item {
                padding: 10px 12px;
                border: 1px solid #e9ecef;
                border-radius: 8px;
                margin: 8px 0;
                background: #ffffff;
            }
            .schedule .item .meta {
                font-size: 12px;
                color: #6c757d;
                margin-bottom: 4px;
            }
            .schedule .item .title {
                font-size: 14px;
                color: #212529;
                font-weight: 600;
            }
            .schedule .item.current {
                border: 1px solid #0d6efd;
                background: #eef5ff;
                box-shadow: 0 1px 0 rgba(13, 110, 253, 0.15);
            }
            .schedule .badge {
                display: inline-block;
                font-size: 11px;
                font-weight: 700;
                padding: 2px 8px;
                border-radius: 999px;
                background: #0d6efd;
                color: #fff;
                margin-left: 8px;
                vertical-align: middle;
            }            
        </style>
        """
    
    @staticmethod
    def _wrap_html(header_class: str, icon: str, title: str, content: str) -> Dict[str, str]:
        """
        Envolve o conteúdo no template HTML base.
        
        Returns:
            Dict com 'subject', 'body_text' e 'body_html'
        """
        html = f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            {EmailTemplates._base_style()}
        </head>
        <body>
            <div class="container">
                <div class="header {header_class}">
                    <div class="icon">{icon}</div>
                    <h1>{title}</h1>
                </div>
                <div class="content">
                    {content}
                </div>
                <div class="footer">
                    <p>Sistema de Gerenciamento de DDS</p>
                    <p style="margin: 5px 0;">Este é um e-mail automático, não responda.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return {
            "subject": f"{icon} {title}",
            "body_html": html
        }
    
    # =========================================================================
    # TEMPLATES DE SUCESSO
    # =========================================================================

    @staticmethod
    def _schedule_html(
        treinamentos: List[Dict[str, str]],
        current_key: str = "",
        limit: int = 30,
    ) -> str:
        """Renderiza a lista de treinamentos agendados em HTML.

        treinamentos: [{'key': 'YYYY-MM-DD - Titulo', 'data': 'DD/MM/AAAA - Dia', 'titulo': '...'}]
        current_key: key do treinamento atual (para destaque)
        """
        if not treinamentos:
            return ""

        shown = treinamentos[: max(0, int(limit))] if limit else treinamentos
        items_html = []
        for t in shown:
            key = (t.get("key") or "").strip()
            is_current = bool(current_key and key and key == current_key)
            cls = "item current" if is_current else "item"
            badge = '<span class="badge">Atual</span>' if is_current else ""
            items_html.append(
                f"""
                <div class="{cls}">
                    <div class="meta">📅 {t.get('data','')}</div>
                    <div class="title">📋 {t.get('titulo','')}{badge}</div>
                </div>
                """
            )
        extra = ""
        if limit and len(treinamentos) > len(shown):
            extra = (
                f"<p style=\"color:#6c757d;font-size:12px;margin-top:8px;\">"
                f"Mostrando {len(shown)} de {len(treinamentos)} treinamentos. Use <span class=\"code\">LISTAR</span> para ver todos."
                f"</p>"
            )

        return (
            "<div class=\"schedule\">"
            "<h2>📌 Treinamentos já agendados</h2>"
            + "".join(items_html)
            + extra
            + "</div>"
        )

    @staticmethod
    def sucesso_programado(
        titulo: str,
        data: str,
        treinamentos_agendados_html: str = "",
        current_key: str = "",
    ) -> Dict[str, str]:
        """Template: DDS programado com sucesso (inclui listagem no estilo LISTAR, com APAGAR)."""
        content = f"""
        <p>Olá,</p>
        
        <p>Seu treinamento foi programado com sucesso! 🎉</p>
        
        <div class="info-box">
            <strong>📋 Treinamento:</strong> {titulo}<br>
            <strong>📅 Data:</strong> {data}
        </div>
        
        <p>O material já está disponível no sistema e será exibido automaticamente na data programada.</p>

        <div class="divider"></div>

        <p style="margin: 0 0 10px 0;"><strong>📌 Treinamentos já agendados</strong></p>
        {treinamentos_agendados_html}
        
        <div class="divider"></div>
        
        <p style="color: #6c757d; font-size: 14px;">
            <strong>💡 Dica:</strong> Use o comando <span class="code">LISTAR</span> para ver todos os treinamentos agendados.
        </p>
        """
        
        return EmailTemplates._wrap_html(
            header_class="success",
            icon="✅",
            title="Treinamento Programado",
            content=content
        )
    

    # =========================================================================
    # TEMPLATES — DDS ONLINE (REUNIÃO)
    # =========================================================================

    @staticmethod
    def online_pedir_dados(sender: str = "") -> Dict[str, str]:
        """Template: Solicita dados obrigatórios para agendar Reunião DDS Online."""
        sender_info = f"<p><strong>Remetente:</strong> {sender}</p>" if sender else ""
        content = f"""
        <p>Olá,</p>
        <p>Recebemos sua solicitação para agendar uma <strong>Reunião DDS Online</strong>, mas precisamos de alguns dados para concluir.</p>
        {sender_info}

        <div class="info-box warning">
            <strong>✅ Responda este e-mail preenchendo exatamente neste formato:</strong><br><br>
            <span class="code">Data:</span> DD/MM/AAAA<br>
            <span class="code">Hora:</span> HH:MM<br>
            <span class="code">Assunto:</span> (título do DDS online)<br>
            <span class="code">Host:</span> (código da equipe, ex.: TEAM1)<br>
            <span class="code">Cohost:</span> (opcional, ex.: E2547)
        </div>

        <div class="action-list">
            <strong>📌 Exemplo</strong>
           <ul>
                <li><span class="code">Data: 06/01/2026</span></li>
                <li><span class="code">Hora: 19:30</span></li>
               <li><span class="code">Assunto: NR-10 – Reciclagem</span></li>
                <li><span class="code">Host: TEAM1</span></li>
                <li><span class="code">Cohost: E2547</span></li>
            </ul>
        </div>

        <p style="color: #6c757d; font-size: 14px;">
            <strong>Observação:</strong> O campo <span class="code">Host</span> é obrigatório.
        </p>
        """
        return EmailTemplates._wrap_html(
            header_class="warning",
            icon="🗓️",
            title="Dados Necessários — Reunião DDS Online",
            content=content
        )

    @staticmethod
    def online_erro_host_obrigatorio() -> Dict[str, str]:
        """Template: Host ausente."""
        content = f"""
        <p>Olá,</p>
        <p>Não foi possível agendar a reunião porque o campo <strong>Host</strong> não foi informado.</p>

        <div class="info-box warning">
            <strong>✅ Informe pelo menos:</strong><br><br>
            <span class="code">Host: TEAM1</span>
        </div>

        <p>Responda este e-mail com o Host e, se necessário, também inclua:</p>
        <div class="action-list">
            <ul>
                <li><span class="code">Data: DD/MM/AAAA</span></li>
                <li><span class="code">Hora: HH:MM</span></li>
                <li><span class="code">Assunto:</span> título</li>
                <li><span class="code">Cohost:</span> opcional</li>
            </ul>
        </div>
        """
        return EmailTemplates._wrap_html(
            header_class="error",
            icon="⚠️",
            title="Host Obrigatório",
            content=content
        )

    @staticmethod
    def online_confirmacao(data: str, hora: str, assunto: str, session_id: str, host: str, cohost: str = "") -> Dict[str, str]:
        """Template: Confirmação de reunião agendada."""
        cohost_line = f"<br><strong>🤝 Cohost:</strong> {cohost}" if cohost else ""
        content = f"""
        <p>Olá,</p>
        <p>Sua <strong>Reunião DDS Online</strong> foi agendada com sucesso.</p>

        <div class="info-box">
            <strong>📅 Data:</strong> {data}<br>
            <strong>⏰ Hora:</strong> {hora}<br>
            <strong>📌 Assunto:</strong> {assunto}<br>
            <strong>🎙️ Host:</strong> {host}
            {cohost_line}
            <br><strong>🆔 Session ID:</strong> <span class="code">{session_id}</span>
        </div>

        <div class="divider"></div>

        <p style="color: #6c757d; font-size: 14px;">
            <strong>Dica:</strong> Guarde o <span class="code">Session ID</span> para localizar a reunião e vincular conteúdos.
        </p>
        """
        return EmailTemplates._wrap_html(
            header_class="success",
            icon="✅",
            title="Reunião DDS Online Agendada",
            content=content
        )
    
    @staticmethod
    def duplicata_ignorada(titulo: str, data: Optional[str] = None) -> Dict[str, str]:
        """Template: Duplicata detectada e ignorada."""
        data_info = f"<strong>📅 Data:</strong> {data}<br>" if data else ""
        
        content = f"""
        <p>Olá,</p>
        
        <p>Detectamos que este treinamento já está cadastrado em nossa base de dados.</p>
        
        <div class="info-box info">
            <strong>📋 Treinamento:</strong> {titulo}<br>
            {data_info}
            <strong>📎 Status:</strong> Conteúdo idêntico encontrado
        </div>
        
        <p>Para evitar duplicidade no sistema, este envio foi automaticamente ignorado.</p>
        
        <div class="action-list">
            <strong>🔧 O que você pode fazer:</strong>
            <ul>
                <li>Se deseja atualizar o conteúdo, envie arquivos diferentes</li>
                <li>Use <span class="code">LISTAR</span> para ver os treinamentos cadastrados</li>
                <li>Use <span class="code">APAGAR</span> para remover o treinamento existente</li>
            </ul>
        </div>
        """
        
        return EmailTemplates._wrap_html(
            header_class="info",
            icon="♻️",
            title="Treinamento Já Cadastrado",
            content=content
        )
    
    # =========================================================================
    # TEMPLATES DE AVISO
    # =========================================================================
    
    @staticmethod
    def conflito_data(titulo: str, data: str) -> Dict[str, str]:
        """Template: Conflito de data detectado."""
        content = f"""
        <p>Olá,</p>
        
        <p><strong>⚠️ Atenção:</strong> Já existe um treinamento agendado para esta data!</p>
        
        <div class="info-box warning">
            <strong>📋 Novo treinamento:</strong> {titulo}<br>
            <strong>📅 Data:</strong> {data}<br>
            <strong>📊 Status:</strong> Salvo, mas há conflito
        </div>
        
        <p>O sistema salvou ambos os treinamentos, mas isso pode causar confusão para os usuários, 
        pois dois cards diferentes aparecerão para o mesmo dia.</p>
        
        <div class="action-list">
            <strong>🎯 Ações recomendadas:</strong>
            <ul>
                <li><strong>Manter ambos:</strong> Se realmente precisa de dois treinamentos no mesmo dia</li>
                <li><strong>Remover o incorreto:</strong> Use <span class="code">APAGAR</span> seguido do título completo</li>
                <li><strong>Verificar agendados:</strong> Use <span class="code">LISTAR</span> para ver todos os DDS</li>
            </ul>
        </div>
        
        <div class="divider"></div>
        
        <p style="color: #856404; font-size: 14px;">
            <strong>💡 Exemplo:</strong> Para remover, envie um e-mail com assunto: 
            <span class="code">APAGAR {data} - {titulo}</span>
        </p>
        """
        
        return EmailTemplates._wrap_html(
            header_class="warning",
            icon="⚠️",
            title="Conflito de Data Detectado",
            content=content
        )
    
    # =========================================================================
    # TEMPLATES DE ERRO
    # =========================================================================
    
    @staticmethod
    def falha_processamento(assunto: str, motivo: str = "não identificado") -> Dict[str, str]:
        """Template: Falha ao processar e-mail."""
        content = f"""
        <p>Olá,</p>
        
        <p>Não foi possível processar seu e-mail.</p>
        
        <div class="info-box warning">
            <strong>📧 Assunto recebido:</strong> {assunto}<br>
            <strong>❌ Motivo:</strong> {motivo}
        </div>
        
        <div class="action-list">
            <strong>✅ Formato correto para envio de DDS:</strong>
            <ul>
                <li><strong>Assunto:</strong> <span class="code">DD/MM/AAAA - Título do Treinamento</span></li>
                <li><strong>Anexos:</strong> Imagens (JPG, PNG) ou PDFs</li>
                <li><strong>Exemplo:</strong> <span class="code">17/11/2025 - Segurança no Trabalho</span></li>
            </ul>
        </div>
        
        <div class="action-list">
            <strong>📌 Comandos disponíveis:</strong>
            <ul>
                <li><span class="code">LISTAR</span> - Ver todos os treinamentos agendados</li>
                <li><span class="code">APAGAR DD/MM/AAAA - Título</span> - Remover um treinamento</li>
                <li><span class="code">AJUDA</span> - Ver instruções completas</li>
            </ul>
        </div>
        
        <div class="divider"></div>
        
        <p style="color: #6c757d; font-size: 14px;">
            <strong>💬 Precisa de ajuda?</strong> Envie um e-mail com assunto <span class="code">AJUDA</span> 
            para receber instruções detalhadas.
        </p>
        """
        
        return EmailTemplates._wrap_html(
            header_class="error",
            icon="⚠️",
            title="Falha ao Processar",
            content=content
        )
    
    # =========================================================================
    # TEMPLATES DE COMANDOS
    # =========================================================================
    
    @staticmethod
    def listagem_dds(treinamentos: List[Dict[str, str]]) -> Dict[str, str]:
        """Template: Lista de treinamentos agendados."""
        if not treinamentos:
            lista_html = '<p style="text-align: center; color: #6c757d; padding: 20px;">Nenhum treinamento agendado.</p>'
        else:
            items = []
            for t in treinamentos:
                items.append(f"""
                <div class="info-box" style="margin: 15px 0;">
                    <strong>📅 {t['data']}</strong><br>
                    <strong style="color: #333;">📋 {t['titulo']}</strong><br>
                    <span style="color: #6c757d; font-size: 14px;">📎 {t['arquivos']} arquivo(s)</span>
                </div>
                """)
            lista_html = "".join(items)
        
        content = f"""
        <p>Olá,</p>
        
        <p>Aqui estão todos os treinamentos agendados no sistema:</p>
        
        <div class="divider"></div>
        
        {lista_html}
        
        <div class="divider"></div>
        
        <div class="action-list">
            <strong>🔧 Ações disponíveis:</strong>
            <ul>
                <li>Para remover: <span class="code">APAGAR DD/MM/AAAA - Título</span></li>
                <li>Para adicionar: Envie um e-mail com data e anexos</li>
            </ul>
        </div>
        """
        
        return EmailTemplates._wrap_html(
            header_class="success",
            icon="📋",
            title=f"Treinamentos Agendados ({len(treinamentos)})",
            content=content
        )
    
    @staticmethod
    def confirmacao_exclusao(titulo: str, data: str) -> Dict[str, str]:
        """Template: Confirmação de exclusão."""
        content = f"""
        <p>Olá,</p>
        
        <p>O treinamento foi removido do sistema com sucesso.</p>
        
        <div class="info-box">
            <strong>🗑️ Treinamento removido:</strong><br>
            <strong>📋 Título:</strong> {titulo}<br>
            <strong>📅 Data:</strong> {data}
        </div>
        
        <p>Todos os arquivos associados foram deletados do Firebase Storage.</p>
        
        <div class="divider"></div>
        
        <p style="color: #6c757d; font-size: 14px;">
            <strong>💡 Dica:</strong> Você pode enviar um novo treinamento para esta data a qualquer momento.
        </p>
        """
        
        return EmailTemplates._wrap_html(
            header_class="success",
            icon="✅",
            title="Treinamento Removido",
            content=content
        )
    
    @staticmethod
    def erro_exclusao(titulo: str, motivo: str = "não encontrado") -> Dict[str, str]:
        """Template: Erro ao tentar excluir."""
        content = f"""
        <p>Olá,</p>
        
        <p>Não foi possível remover o treinamento solicitado.</p>
        
        <div class="info-box warning">
            <strong>📋 Treinamento:</strong> {titulo}<br>
            <strong>❌ Motivo:</strong> {motivo}
        </div>
        
        <div class="action-list">
            <strong>✅ Verifique:</strong>
            <ul>
                <li>Se a data está no formato <span class="code">DD/MM/AAAA</span></li>
                <li>Se o título está escrito exatamente como aparece na listagem</li>
                <li>Use <span class="code">LISTAR</span> para ver os treinamentos disponíveis</li>
            </ul>
        </div>
        
        <div class="divider"></div>
        
        <p style="color: #856404; font-size: 14px;">
            <strong>💡 Exemplo correto:</strong> <span class="code">APAGAR 17/11/2025 - Segurança no Trabalho</span>
        </p>
        """
        
        return EmailTemplates._wrap_html(
            header_class="error",
            icon="❌",
            title="Erro ao Remover",
            content=content
        )
    
    # =========================================================================
    # UTILITÁRIOS
    # =========================================================================
    
    @staticmethod
    def texto_simples(template: Dict[str, str]) -> str:
        """
        Converte HTML para texto simples (fallback).
        Remove tags HTML e mantém apenas o conteúdo.
        """
        import re
        html = template.get("body_html", "")
        # Remove tags HTML
        texto = re.sub(r'<[^>]+>', '', html)
        # Remove espaços múltiplos
        texto = re.sub(r'\s+', ' ', texto)
        return texto.strip()