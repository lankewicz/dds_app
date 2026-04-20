# =============================================================================
# Nome do arquivo : core/cmd_apagar.py
# Data de criação : 31/10/2025
# Versão          : 2.0 (COM TEMPLATES)
# Função          : Implementar o comando APAGAR do DDS.
# Funcionalidades :
#   - Apagar pasta/coleção no Storage pelo nome (2º nível sob DDS_PREFIX).
#   - Atualizar listagem (list.json), se aplicável.
#   - Enviar e-mail formatado de sucesso/erro para o solicitante.
# =============================================================================

from __future__ import annotations
import re
import datetime as dt
from email_utils import send_response
from logger import log_manager
from utils.env_config import prefix_from_env
from firebase_sender import delete_folder_in_storage, update_list_json, bucket
from email_templates import EmailTemplates


def _extrair_data_titulo(folder_name: str) -> tuple[str | None, str | None]:
    """
    Extrai data e título do nome da pasta.
    
    Formato esperado: "YYYY-MM-DD - TÍTULO"
    
    Returns:
        (data_formatada, titulo) ou (None, None) se não conseguir extrair
    """
    # Padrão: "2025-11-17 - Segurança no Trabalho"
    match = re.match(r"^(\d{4}-\d{2}-\d{2})\s*-\s*(.+)$", folder_name)
    
    if not match:
        return None, None
    
    data_str_iso = match.group(1)
    titulo = match.group(2).strip()
    
    try:
        # Converte para formato brasileiro com dia da semana
        data_obj = dt.datetime.strptime(data_str_iso, "%Y-%m-%d").date()
        dias_semana = [
            "Segunda-feira", "Terça-feira", "Quarta-feira",
            "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"
        ]
        data_formatada = f"{data_obj.strftime('%d/%m/%Y')} - {dias_semana[data_obj.weekday()]}"
        return data_formatada, titulo
    except Exception:
        # Se falhar, retorna pelo menos o título
        return data_str_iso, titulo


def _verificar_existencia_pasta(folder_name: str, prefixo: str) -> tuple[bool, int]:
    """
    Verifica se a pasta existe no Storage e conta quantos arquivos tem.
    
    Returns:
        (existe: bool, num_arquivos: int)
    """
    alvo = f"{prefixo.rstrip('/')}/{folder_name}"
    
    try:
        blobs = list(bucket.list_blobs(prefix=alvo))
        # Filtra apenas arquivos reais (não pastas vazias)
        arquivos_reais = [b for b in blobs if not b.name.endswith('/') and b.name != alvo + '/lista.json']
        return len(arquivos_reais) > 0, len(arquivos_reais)
    except Exception as e:
        log_manager.add(f"[APAGAR] Erro ao verificar existência: {e}", "ERROR")
        return False, 0


def comando_apagar(argumento: str, sender: str):
    """
    Executa o comando APAGAR e envia resposta formatada.
    
    Args:
        argumento: Nome da pasta a ser apagada (ex: "2025-11-17 - Segurança")
        sender: E-mail do solicitante
    """
    folder_name = (argumento or "").strip()
    
    # =========================================================================
    # VALIDAÇÃO: Argumento vazio
    # =========================================================================
    if not folder_name:
        log_manager.add(f"[APAGAR] Comando sem argumento enviado por {sender}", "WARNING")
        
        # 🎨 USA TEMPLATE DE ERRO
        template = EmailTemplates.erro_argumento_vazio("APAGAR")
        
        send_response(
            to_addr=sender,
            subject=template["subject"],
            body=EmailTemplates.texto_simples(template),
            html_body=template["body_html"]
        )
        return

    # =========================================================================
    # PREPARAÇÃO: Remove prefixo se vier no argumento
    # =========================================================================
    prefixo = prefix_from_env()
    if folder_name.startswith(prefixo):
        folder_name = folder_name[len(prefixo):].lstrip('/')
    
    alvo = f"{prefixo.rstrip('/')}/{folder_name}"
    log_manager.add(f"[APAGAR] Solicitação de {sender} para apagar: '{alvo}'", "INFO")

    # =========================================================================
    # VERIFICAÇÃO: Pasta existe?
    # =========================================================================
    existe, num_arquivos = _verificar_existencia_pasta(folder_name, prefixo)
    
    if not existe:
        log_manager.add(f"[APAGAR] Pasta não encontrada: '{alvo}'", "WARNING")
        
        # Tenta extrair informações mesmo que não exista
        data_fmt, titulo = _extrair_data_titulo(folder_name)
        titulo_display = titulo if titulo else folder_name
        
        # 🎨 USA TEMPLATE DE ERRO
        template = EmailTemplates.erro_exclusao(
            titulo=titulo_display,
            motivo="Treinamento não encontrado no sistema"
        )
        
        send_response(
            to_addr=sender,
            subject=template["subject"],
            body=EmailTemplates.texto_simples(template),
            html_body=template["body_html"]
        )
        return

    # =========================================================================
    # EXECUÇÃO: Tenta apagar
    # =========================================================================
    try:
        sucesso = delete_folder_in_storage(folder_name)
        
        if not sucesso:
            raise Exception("Função delete_folder_in_storage retornou False")
        
        log_manager.add(f"[APAGAR] Pasta '{alvo}' apagada com sucesso ({num_arquivos} arquivos)", "INFO")
        
        # Atualiza o list.json
        try:
            update_list_json()
            log_manager.add(f"[APAGAR] list.json atualizado com sucesso", "INFO")
        except Exception as e:
            log_manager.add(f"[APAGAR] Aviso: Falha ao atualizar list.json: {e}", "WARNING")
        
        # Extrai informações para o e-mail de confirmação
        data_fmt, titulo = _extrair_data_titulo(folder_name)
        
        if not titulo:
            titulo = folder_name
        if not data_fmt:
            data_fmt = "Data não especificada"
        
        # 🎨 USA TEMPLATE DE SUCESSO
        template = EmailTemplates.confirmacao_exclusao(titulo, data_fmt)
        
        send_response(
            to_addr=sender,
            subject=template["subject"],
            body=EmailTemplates.texto_simples(template),
            html_body=template["body_html"]
        )
        
    except Exception as e:
        # =====================================================================
        # ERRO: Falha ao apagar
        # =====================================================================
        log_manager.add(f"[APAGAR] Erro ao apagar '{alvo}': {e}", "ERROR")
        
        data_fmt, titulo = _extrair_data_titulo(folder_name)
        titulo_display = titulo if titulo else folder_name
        
        # 🎨 USA TEMPLATE DE ERRO
        template = EmailTemplates.erro_exclusao(
            titulo=titulo_display,
            motivo=f"Erro técnico: {str(e)}"
        )
        
        send_response(
            to_addr=sender,
            subject=template["subject"],
            body=EmailTemplates.texto_simples(template),
            html_body=template["body_html"]
        )