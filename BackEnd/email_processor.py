# -----------------------------------------------------------------------------
# Módulo: email_processor.py
# Versão: 4.4 (COM TEMPLATES CENTRALIZADOS)
#
# Alterações:
#   - Integração com email_templates.py para respostas padronizadas
#   - Remoção de HTML inline do código
#   - Código mais limpo e manutenível
# -----------------------------------------------------------------------------

from __future__ import annotations
from dataclasses import dataclass

import email as py_email
import imaplib as py_imaplib
import time
import re
import os
import json
import unicodedata
import datetime as dt
import firebase_admin

from email.header import decode_header
from typing import List, Dict, Any, Tuple



# Importações de nossos próprios módulos
from config import APP_CONFIG
from core.models import EmailStats
from logger import log_manager
from imap_utils import mark_read
from folder_utils import make_email_folder, cleanup_non_media
from attachment_processor import process_attachment
from firebase_sender import upload_files, update_list_json, move_to_sent, move_to_ignored, bucket
from email_utils import send_response
from core.dispatcher import interpretar_comando, executar_comando
from core.cmd_ajuda import get_ajuda_html as _get_ajuda_html
from utils.env_config import prefix_from_env
from config import SMTP_USER

# 🎨 NOVO: Importa os templates centralizados
from email_templates import EmailTemplates
from firebase_admin import firestore


# ---------------------------------------------------------------------------
# Helpers globais
# ---------------------------------------------------------------------------

DIAS_SEMANA_PT = [
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
]


def _formatar_data_semana(data: dt.date) -> str:
    """Retorna 'DD/MM/AAAA - Dia-da-semana'."""
    if isinstance(data, dt.datetime):
        data = data.date()
    data_fmt = data.strftime("%d/%m/%Y")
    dia_semana = DIAS_SEMANA_PT[data.weekday()]
    return f"{data_fmt} - {dia_semana}"


def _norm(s: str) -> str:
    """Remove acentos e deixa maiúsculo para comparação confiável."""
    return unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode().upper()

# ---------------------------------------------------------------------------
# DDS ONLINE — Helpers
# ---------------------------------------------------------------------------

PENDING_DIR = os.path.join(os.getcwd(), "data", "online_pending")

def _ensure_pending_dir() -> None:
    os.makedirs(PENDING_DIR, exist_ok=True)

def _pending_path(sender: str) -> str:
    safe = _norm(sender).replace("@", "_AT_").replace(".", "_").replace(" ", "_")
    return os.path.join(PENDING_DIR, f"{safe}.json")

def _load_pending(sender: str) -> Dict[str, Any] | None:
    _ensure_pending_dir()
    p = _pending_path(sender)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        # expiração (se existir)
        exp = data.get("expire_at")
        if exp:
            try:
                exp_dt = dt.datetime.fromisoformat(exp)
                if dt.datetime.utcnow() > exp_dt:
                    os.remove(p)
                    return None
            except Exception:
                pass
        return data
    except Exception:
        return None

def _save_pending(sender: str, state: str, context: Dict[str, Any] | None = None, ttl_hours: int = 24) -> None:
    _ensure_pending_dir()
    payload = {
        "state": state,
        "created_at": dt.datetime.utcnow().isoformat(timespec="seconds"),
        "expire_at": (dt.datetime.utcnow() + dt.timedelta(hours=ttl_hours)).isoformat(timespec="seconds"),
        "context": context or {},
    }
    with open(_pending_path(sender), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def _clear_pending(sender: str) -> None:
    try:
        p = _pending_path(sender)
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        pass

def _is_online_trigger_subject(subject: str) -> bool:
    """
    Detecta qualquer intenção de Reunião ONLINE.
    Aceita:
    - online
    - reunião online
    - dds online
    - on-line
    """
    s = _norm(subject or "")
    if not s:
        return False

    # Se for o padrão clássico de DDS (DD/MM/AAAA - Título), NÃO é reunião online
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}\s*-\s*.+$", subject.strip()):
        return False

    return ("ONLINE" in s) or ("ON-LINE" in s) or ("ON LINE" in s)


def _extract_kv_lines(body: str) -> Dict[str, str]:
    """
    Extrai linhas do tipo:
      Data: 06/01/2026
      Hora: 19:30
      Assunto: NR-10
     Host: TEAM1
      Cohost: E2547
    Aceita separadores ':' ou '=' e variações de 'co-host'.
    """
    out: Dict[str, str] = {}
    if not body:
        return out
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    for ln in lines:
        # normaliza chave mantendo valor original
        m = re.match(r"^(data|hora|assunto|host|cohost|co-host|co_host)\s*[:=]\s*(.+)$", ln.strip(), flags=re.I)
        if not m:
            continue
        k = _norm(m.group(1)).replace("-", "").replace("_", "")
        v = m.group(2).strip()
        if k == "COHOST":
            out["cohost"] = v
        else:
            out[k.lower()] = v
    return out

def _parse_subject_online(subject: str) -> Dict[str, str]:
    """
    Tenta extrair data/hora/assunto do subject em formatos comuns:
      'Reunião ONLINE - 06/01/2026 19:30 - NR-10'
      'DDS ONLINE | 06/01/2026 19:30 | NR-10'
    """
    out: Dict[str, str] = {}
    s = (subject or "").strip()
    if not s:
        return out

    # Captura DD/MM/AAAA e HH:MM em qualquer parte
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}:\d{2})", s)
    if m:
        out["data"] = m.group(1)
        out["hora"] = m.group(2)

        # assunto: tudo que vier depois de data+hora com separador
        tail = s[m.end():].strip()
        tail = re.sub(r"^[\s\-|–—:]+", "", tail).strip()
        if tail:
            out["assunto"] = tail
    return out

def _normalize_team_code(code: str) -> str:
    return _norm(code).replace(" ", "")

def _make_session_id(data_ddmmaa: str, hora_hhmm: str, assunto: str) -> str:
    # data -> yyyymmdd
    d = dt.datetime.strptime(data_ddmmaa, "%d/%m/%Y").date()
    ymd = d.strftime("%Y%m%d")
    hhmm = hora_hhmm.replace(":", "")
    # slug simples do assunto
    slug = _norm(assunto)[:40]
    slug = re.sub(r"[^A-Z0-9]+", "-", slug).strip("-").lower()
    slug = slug or "reuniao"
    return f"dds-{ymd}-{hhmm}-{slug}"

def _firestore_client():
    # firebase_sender já inicializa o app para Storage; aqui garantimos que existe.
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    return firestore.client()

def _save_online_session_firestore(session_id: str, payload: Dict[str, Any]) -> None:
    db = _firestore_client()
    db.collection("DDS_Sessions").document(session_id).set(payload, merge=True)



def _get_trainings_for_date(data: dt.date) -> List[Dict[str, Any]]:
    """
    Retorna lista de treinamentos consultando DIRETAMENTE o Firebase Storage.
    """
    if not data:
        return []

    data_str_iso = data.strftime("%Y-%m-%d")
    prefix = f"DDSv2/{data_str_iso}"
    
    try:
        blobs = bucket.list_blobs(prefix=prefix)
    except Exception as e:
        log_manager.add(f"Erro ao consultar Storage para {data_str_iso}: {e}", "ERROR")
        return []
    
    treinamentos: Dict[str, Dict[str, Any]] = {}
    
    for blob in blobs:
        caminho = blob.name
        partes = caminho.split("/")
        if len(partes) < 3:
            continue
            
        pasta = partes[1]
        arquivo = partes[2]
        
        if arquivo == "" or arquivo == "lista.json":
            continue

        if not pasta.startswith(data_str_iso):
            continue

        match = re.match(r"^\d{4}-\d{2}-\d{2}\s*-\s*(.+)$", pasta)
        if not match:
            continue
            
        titulo = match.group(1).strip()
        titulo_norm = _norm(titulo)
        
        if titulo_norm not in treinamentos:
            treinamentos[titulo_norm] = {
                "titulo": titulo,
                "arquivos": [],
                "path_base": f"DDSv2/{pasta}"
            }
        
        treinamentos[titulo_norm]["arquivos"].append(arquivo)
    
    return list(treinamentos.values())

def _list_all_trainings_sorted(limit: int = 30) -> List[Dict[str, str]]:
    """Lista treinamentos existentes no Firebase Storage (DDSv2) ordenados por data.

    Retorno:
      [{'key': 'YYYY-MM-DD - Titulo', 'data': 'DD/MM/AAAA - Dia', 'titulo': 'Titulo'}]
    """
    try:
        blobs = bucket.list_blobs(prefix="DDSv2/")
    except Exception as e:
        log_manager.add(f"Erro ao listar DDS no Storage: {e}", "ERROR")
        return []

    by_folder: Dict[str, Dict[str, Any]] = {}
    for blob in blobs:
        caminho = blob.name or ""
        partes = caminho.split("/")
        if len(partes) < 3:
            continue

        pasta = partes[1].strip()
        arquivo = partes[2].strip()
        if not pasta or not arquivo or arquivo == "lista.json":
            continue

        m = re.match(r"^(\\d{4}-\\d{2}-\\d{2})\\s*-\\s*(.+)$", pasta)
        if not m:
            continue

        date_iso = m.group(1)
        titulo = (m.group(2) or "").strip()
        if not titulo:
            continue

        if pasta not in by_folder:
            try:
                d = dt.datetime.strptime(date_iso, "%Y-%m-%d").date()
                data_fmt = _formatar_data_semana(d)
            except Exception:
                data_fmt = date_iso
            by_folder[pasta] = {"key": pasta, "data": data_fmt, "titulo": titulo, "date_iso": date_iso}

    items = list(by_folder.values())
    items.sort(key=lambda x: (x.get("date_iso", "9999-99-99"), _norm(x.get("titulo", ""))))

    if limit and limit > 0:
        items = items[: int(limit)]

    return [{"key": i["key"], "data": i["data"], "titulo": i["titulo"]} for i in items]

 
def _list_pastas_para_listar() -> List[str]:
    """
    Retorna a lista de pastas de 2º nível usada pelo LISTAR.
    Mantém a mesma origem (Storage) e ignora lista.json.
    """
    from core.listing_utils import list_pastas_2nivel
    prefixo = prefix_from_env()
    return list_pastas_2nivel(bucket, prefixo)

def _render_listar_embed(current_folder: str = "") -> str:
    """
    Renderiza o HTML EMBUTÍVEL da listagem (estilo LISTAR) com botão APAGAR.
    """
    from core.listing_utils import render_listar_html
    pastas = _list_pastas_para_listar()
    return render_listar_html(
        pastas,
        SMTP_USER,
        embed=True,
        current_folder=current_folder,
    )

def _has_training_for_date(data: dt.date) -> bool:
    """Retorna True se já existir pelo menos um DDS agendado para essa data."""
    return len(_get_trainings_for_date(data)) > 0


def _find_exact_duplicate(data: dt.date, titulo: str, arquivos_novos: List[str]) -> bool:
    """Verifica se já existe um treinamento IDÊNTICO."""
    if not data or not titulo or not arquivos_novos:
        return False
    
    treinamentos = _get_trainings_for_date(data)
    titulo_norm = _norm(titulo)
    
    for treino in treinamentos:
        if _norm(treino["titulo"]) != titulo_norm:
            continue
        
        if _are_same_files(treino["arquivos"], arquivos_novos):
            return True
    
    return False


def _are_same_files(existing_files: List[str], new_files: List[str]) -> bool:
    """Compara duas listas de arquivos."""
    if not existing_files or not new_files:
        return False

    ex_norm = {_norm(x) for x in existing_files}
    new_norm = {_norm(x) for x in new_files}

    return ex_norm == new_norm


# ---------------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------------

class EmailProcessor:
    """Orquestra a busca, interpretação e processamento de e-mails."""

    def __init__(self, stats: EmailStats):
        """Inicializa o processador de e-mails."""
        self.stats = stats

    def process_emails_sync(self, imap: py_imaplib.IMAP4_SSL, messages: List[bytes]) -> Dict[str, int]:
        """Processa o primeiro e-mail de uma lista de forma síncrona."""
        if not messages:
            return {"success": 0, "failed": 0}

        msg_id = messages[0]
        result = self._process_single_email(imap, msg_id)

        if result.get("success"):
            return {"success": 1, "failed": 0}
        else:
            return {"success": 0, "failed": 1}

    def _get_email_body(self, msg: py_email.message.Message) -> str:
        """Extrai o corpo de texto plano de uma mensagem de e-mail."""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and part.get("Content-Disposition") is None:
                    try:
                        return part.get_payload(decode=True).decode(errors="ignore")
                    except Exception:
                        continue
        else:
            if msg.get_content_type() == "text/plain":
                try:
                    return msg.get_payload(decode=True).decode(errors="ignore")
                except Exception:
                    pass
        return "(Corpo do e-mail não é texto plano ou não foi encontrado)"

    def _decode_subject(self, raw_subject: str) -> str:
        """Decodifica o assunto do e-mail para string UTF-8."""
        if not raw_subject:
            return ""
        parts = decode_header(raw_subject)
        return "".join(
            p.decode(enc or "utf-8") if isinstance(p, bytes) else p
            for p, enc in parts
        ).strip()

    def _parse_training_info_from_subject(self, subject: str) -> Tuple[str, str, dt.date | None]:
        """Extrai (data_formatada, titulo, data_dt) a partir do assunto."""
        if not subject:
            return "", "", None

        subject = subject.strip()

        m = re.match(r"^(\d{1,2}/\d{1,2}/\d{4})\s*-\s*(.+)$", subject)
        if m:
            data_str = m.group(1)
            titulo = m.group(2).strip()
            try:
                data_dt = dt.datetime.strptime(data_str, "%d/%m/%Y").date()
                data_fmt = _formatar_data_semana(data_dt)
            except Exception:
                data_dt = None
                data_fmt = data_str
            return data_fmt, titulo, data_dt

        return "", subject, None

    def _get_attachment_names(self, msg: py_email.message.Message) -> List[str]:
        """Retorna lista com os nomes dos anexos enviados pelo usuário."""
        nomes: List[str] = []
        if not msg.is_multipart():
            return nomes

        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                nome = part.get_filename()
                if nome:
                    nomes.append(nome)
        return nomes

    def _process_single_email(self, imap: py_imaplib.IMAP4_SSL, msg_id: bytes) -> Dict[str, Any]:
        """Lógica para processar um único e-mail."""
        start_time = time.time()
        result: Dict[str, Any] = {"success": False, "is_command": False}

        try:
            status, data = imap.fetch(msg_id, "(RFC822)")
            if status != "OK":
                raise ConnectionError("Falha ao buscar dados do e-mail.")

            msg = py_email.message_from_bytes(data[0][1])
            subject = self._decode_subject(msg.get("Subject", ""))
            sender = py_email.utils.parseaddr(msg.get("From"))[1]

            log_manager.add(
                f"Analisando e-mail de '{sender}' com assunto '{subject[:30]}...'",
                "INFO",
            )

            # -----------------------------------------------------------------
            # ✅ PRIORIDADE MÁXIMA: DDS ONLINE (Reunião)
            # - Se há pendência (wizard), sempre processa como ONLINE.
            # - Se assunto indica ONLINE (inclusive "online" sozinho), processa como ONLINE.
            # - Somente se NÃO for ONLINE, segue para comandos e DDS tradicional.
            # -----------------------------------------------------------------
            body_text = self._get_email_body(msg)

            # 1) Primeiro: comandos SEMPRE ganham (mesmo se houver pending de ONLINE)
            comando, argumento = interpretar_comando(subject)

            if comando:
                result["is_command"] = True
                executar_comando(comando, argumento, sender)
                self.stats.comandos += 1
                result["success"] = True
                mark_read(imap, msg_id)
                self.stats.total_processados += 1
                self.stats.sucesso += 1
                return result

            # 2) Depois: fluxo ONLINE (wizard)
            pending = _load_pending(sender)
            is_online_trigger = _is_online_trigger_subject(subject)

            if pending or is_online_trigger:
                handled = self._process_online_meeting_flow(sender, subject, body_text, msg)
                if handled:
                    result["success"] = True
                    mark_read(imap, msg_id)
                    self.stats.total_processados += 1
                    self.stats.sucesso += 1
                    return result          

            if comando:
                # ----------------- CASO COMANDO -----------------
                result["is_command"] = True
                executar_comando(comando, argumento, sender)
                self.stats.comandos += 1
                result["success"] = True

            else:
                # ----------------- CASO NÃO É COMANDO → DDS -----------------
                data_fmt, titulo_fmt, data_dt = self._parse_training_info_from_subject(subject)

                # ⚠️ CRÍTICO: Captura estado ANTES de qualquer processamento
                existia_na_data = bool(data_dt and _has_training_for_date(data_dt))
                
                # Lê os nomes dos anexos recebidos (sem salvar ainda)
                arquivos_recebidos = self._get_attachment_names(msg)
                
                # Verifica se é uma DUPLICATA EXATA
                eh_duplicata_exata = _find_exact_duplicate(data_dt, titulo_fmt, arquivos_recebidos)

                # --- CENÁRIO 1: DUPLICATA EXATA (Ignora o upload) ---
                if eh_duplicata_exata:
                    log_manager.add(f"DDS Duplicado idêntico detectado: {titulo_fmt}", "WARNING")
                    
                    # 🎨 USA TEMPLATE
                    template = EmailTemplates.duplicata_ignorada(titulo_fmt, data_fmt)
                    send_response(
                        to_addr=sender,
                        subject=template["subject"],
                        body=EmailTemplates.texto_simples(template),
                        html_body=template["body_html"]
                    )
                    result["success"] = True

                # --- CENÁRIO 2: CONTEÚDO NOVO (Processa upload) ---
                else:
                    processed_count = self._process_attachments(msg, subject)
                    
                    if processed_count > 0:
                        self.stats.anexos += processed_count
                        result["success"] = True

                        # SUB-CENÁRIO 2.A: CONFLITO DE DATA
                        if existia_na_data:
                            # 🎨 USA TEMPLATE
                            template = EmailTemplates.conflito_data(titulo_fmt, data_fmt)
                            send_response(
                                to_addr=sender,
                                subject=template["subject"],
                                body=EmailTemplates.texto_simples(template),
                                html_body=template["body_html"]
                            )

                        # SUB-CENÁRIO 2.B: SUCESSO (Data livre)
                        else:
                            # 🎨 USA TEMPLATE

                            current_key = ""
                            if data_dt:
                                current_key = f"{data_dt.strftime('%Y-%m-%d')} - {titulo_fmt}".strip()

                            # Lista no MESMO formato do comando LISTAR, com ação APAGAR
                            listar_embed_html = _render_listar_embed(current_folder=current_key)
                            template = EmailTemplates.sucesso_programado(
                                titulo=titulo_fmt,
                                data=data_fmt,
                                treinamentos_agendados_html=listar_embed_html,
                                current_key=current_key,
                            )
                            send_response(
                                to_addr=sender,
                                subject=template["subject"],
                                body=EmailTemplates.texto_simples(template),
                                html_body=template["body_html"]
                            )
                    
                    else:
                        # Falha: Sem anexos válidos
                        self._enviar_ajuda_se_necessario(sender, subject, msg)
                        result["success"] = True

            # Finalização
            mark_read(imap, msg_id)
            self.stats.total_processados += 1
            if result["success"]:
                self.stats.sucesso += 1
            else:
                self.stats.falhas += 1

        except Exception as e:
            log_manager.add(f"Erro crítico no processador de e-mail: {e}", "ERROR")
            self.stats.falhas += 1

        return result
    
    # -------------------------------------------------------------------------
    # DDS ONLINE — fluxo assistido + completo
    # -------------------------------------------------------------------------
    def _process_online_meeting_flow(self, sender: str, subject: str, body_text: str, msg) -> bool:
        """
        Retorna True se o e-mail foi tratado como Reunião DDS Online.
        """
        cover_dir = os.path.join(
            PENDING_DIR,
            _norm(sender).replace("@", "_AT_").replace(".", "_"),
            "CAPA"
        )
        os.makedirs(cover_dir, exist_ok=True)

        saved_covers = 0
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_disposition() != "attachment":
                    continue
                if not part.get_filename():
                    continue

                process_attachment(part, cover_dir)
                saved_covers += 1

        if saved_covers:
            log_manager.add(
                f"ONLINE: {saved_covers} arquivo(s) salvo(s) como CAPA para {sender}",
                "INFO"
            )
        # 1) extrai possíveis campos do subject
        sub = _parse_subject_online(subject)
        # 2) extrai possíveis campos do body (key:value)
        kv = _extract_kv_lines(body_text or "")

        data_str = (kv.get("data") or sub.get("data") or "").strip()
        hora_str = (kv.get("hora") or sub.get("hora") or "").strip()
        assunto = (kv.get("assunto") or sub.get("assunto") or "").strip()
        host_raw = (kv.get("host") or "").strip()
        cohost_raw = (kv.get("cohost") or "").strip()

        # Se for apenas gatilho (sem dados suficientes), abre pendência e pede dados
        missing_any_core = not data_str or not hora_str or not assunto
        if missing_any_core and not _load_pending(sender):
            _save_pending(sender, "awaiting_fields", context={"subject": subject})
            template = EmailTemplates.online_pedir_dados(sender=sender)
            send_response(
                to_addr=sender,
                subject=template["subject"],
                body=EmailTemplates.texto_simples(template),
                html_body=template["body_html"]
            )
            return True

        # Se ainda faltam campos, continua pedindo (mantém pendência)
        if missing_any_core:
            _save_pending(sender, "awaiting_fields", context={"subject": subject})
            template = EmailTemplates.online_pedir_dados(sender=sender)
            send_response(
                to_addr=sender,
                subject=template["subject"],
                body=EmailTemplates.texto_simples(template),
                html_body=template["body_html"]
            )
            return True

        # Host é obrigatório
        if not host_raw:
            _save_pending(sender, "awaiting_fields", context={"subject": subject, "data": data_str, "hora": hora_str, "assunto": assunto})
            template = EmailTemplates.online_erro_host_obrigatorio()
            send_response(
                to_addr=sender,
                subject=template["subject"],
                body=EmailTemplates.texto_simples(template),
                html_body=template["body_html"]
            )
            return True

        # Normaliza codes
        host = _normalize_team_code(host_raw)
        cohost = _normalize_team_code(cohost_raw) if cohost_raw else ""

        # Gera session_id e persiste no Firestore
        try:
            session_id = _make_session_id(data_str, hora_str, assunto)
        except Exception:
            # Se data/hora inválidos, pede novamente
            _save_pending(sender, "awaiting_fields", context={"subject": subject})
            template = EmailTemplates.online_pedir_dados(sender=sender)
            send_response(
                to_addr=sender,
                subject=template["subject"],
                body=EmailTemplates.texto_simples(template),
                html_body=template["body_html"]
            )
            return True

        payload = {
            "type": "online",
            "date": data_str,
            "time": hora_str,
            "timezone": "America/Sao_Paulo",
            "subject": assunto,
            "status": "scheduled",
            "createdByEmail": sender,
            "updatedAt": firestore.SERVER_TIMESTAMP,
            "roles": {
                "hostTeams": [host],
                "cohostTeams": ([cohost] if cohost else []),
                "participant": ["*"],
            },
            # canal padrão (você pode mudar depois, mas já deixa pronto)
            "channelName": session_id,
        }

        try:
            _save_online_session_firestore(session_id, payload)
        except Exception as e:
            log_manager.add(f"Falha ao salvar sessão online no Firestore: {e}", "ERROR")
            # não consome o e-mail silenciosamente: pede novamente (sem perder fluxo)
            _save_pending(sender, "awaiting_fields", context={"subject": subject})
            template = EmailTemplates.online_pedir_dados(sender=sender)
            send_response(
                to_addr=sender,
                subject=template["subject"],
                body=EmailTemplates.texto_simples(template),
                html_body=template["body_html"]
            )
            return True

        # Sucesso: limpa pendência e confirma
        _clear_pending(sender)
        template = EmailTemplates.online_confirmacao(
            data=data_str,
            hora=hora_str,
            assunto=assunto,
            session_id=session_id,
            host=host,
            cohost=cohost
        )
        send_response(
            to_addr=sender,
            subject=template["subject"],
            body=EmailTemplates.texto_simples(template),
            html_body=template["body_html"]
        )
        return True
    

    def _enviar_ajuda_se_necessario(self, sender, subject, msg):
        """Envia e-mail de ajuda quando não consegue processar."""
        log_manager.add(f"E-mail de '{sender}' inválido. Enviando resposta com ajuda.", "INFO")
        
        # 🎨 USA TEMPLATE
        template = EmailTemplates.falha_processamento(
            assunto=subject,
            motivo="Sem anexos válidos ou formato incorreto"
        )
        send_response(
            to_addr=sender,
            subject=template["subject"],
            body=EmailTemplates.texto_simples(template),
            html_body=template["body_html"]
        )

    def _process_attachments(self, msg: py_email.message.Message, subject: str) -> int:
        """Extrai, salva e envia anexos de um e-mail."""
        processed_count = 0
        folder_path = None

        if msg.is_multipart():
            for part in msg.walk():
                disp = (part.get_content_disposition() or "").lower()
                if disp != "attachment":
                    continue

                if part.get_filename():
                    if processed_count == 0:
                        folder_path = make_email_folder(subject)
                    process_attachment(part, folder_path)
                    processed_count += 1

        if processed_count > 0 and folder_path:
            cleanup_non_media(folder_path)
            if upload_files(folder_path):
                update_list_json()
                move_to_sent(folder_path)
            else:
                move_to_ignored(folder_path)

        return processed_count

    def _move_to_trash(self, imap: py_imaplib.IMAP4_SSL, msg_id: bytes):
        """Marca o e-mail como deletado e limpa da caixa de entrada."""
        try:
            imap.store(msg_id, "+FLAGS", "\\Deleted")
        except Exception as e:
            log_manager.add(
                f"Falha ao marcar e-mail {msg_id.decode()} para exclusão: {e}",
                "WARNING",
            )