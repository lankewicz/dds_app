# -----------------------------------------------------------------------------
# Módulo: main.py
# Versão: 4.1 (Final com correção de renderização)
#
# Histórico de Alterações:
#   - 29/08/2025 (Gemini): Criação do orquestrador principal para a arquitetura v4.1.
#   - 29/08/2025 (Gemini): Adicionada atualização completa da UI no início do loop.
# -----------------------------------------------------------------------------

import asyncio
import sys
import time
import requests
import psutil
import locale
import os
import hashlib
from datetime import datetime, timezone

# Importações da biblioteca 'rich'
from rich.live import Live
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

# --- Importações dos Módulos do Nosso Projeto ---
from config import APP_CONFIG, inicializar_pastas
from core.models import EmailStats, SystemMetrics, StatusType
from logger import log_manager
from tui import DDSInterface
from tui_progress import progress_bus
from email_processor import EmailProcessor
from console_utils import kbhit, getch
from imap_utils import connect_imap, fetch_unseen

def _mask_token(token: str, head: int = 8, tail: int = 6) -> str:
    if not token:
        return ""
    if len(token) <= head + tail:
        return token
    return f"{token[:head]}…{token[-tail:]}"

def _short_hash(token: str) -> str:
    if not token:
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
def handle_keyboard_input(interface: DDSInterface) -> bool:
    """Verifica e trata a entrada do teclado de forma não bloqueante."""
    if not kbhit():
        return False
    
    key = getch().lower()
    
    if key == 'q':
        if Confirm.ask("\n[red]Deseja realmente sair?[/red]"):
            return True
    elif key == 't':
        new_interval = Prompt.ask(
            f"\n[yellow]Novo intervalo em segundos (atual: {APP_CONFIG.INTERVAL})[/yellow]",
            default=str(APP_CONFIG.INTERVAL)
        )
        try:
            APP_CONFIG.INTERVAL = max(5, int(new_interval))
            log_manager.add(f"Intervalo alterado para {APP_CONFIG.INTERVAL}s", "SUCCESS")
        except ValueError:
            log_manager.add("Valor de intervalo inválido.", "ERROR")
    elif key == 'l':
        log_manager.logs.clear()
        log_manager.add("Logs da interface foram limpos.", "SUCCESS")
    elif key == 'd':
        APP_CONFIG.DEBUG_MODE = not APP_CONFIG.DEBUG_MODE
        status = "ativado" if APP_CONFIG.DEBUG_MODE else "desativado"
        log_manager.add(f"Modo debug {status}.", "INFO")
        
    return False


async def main_async():
    """O loop de execução principal e assíncrono da aplicação."""
    stats = EmailStats()
    metrics = SystemMetrics()
    processor = EmailProcessor(stats)
    interface = DDSInterface(stats, metrics)

    layout = interface.get_renderable(progress_bus.renderable())

    # --- NOVO: Health-check do servidor de token (via env) ---
    # Exemplo: https://dds-token-server.onrender.com/health
    TOKEN_HEALTH_URL = os.getenv("TOKEN_STATUS_URL", "").strip()
    TOKEN_REFRESH_SECONDS = int(os.getenv("TOKEN_REFRESH_SECONDS", "600"))

    # --- NOVO: Keepalive do próprio serviço (Render) ---
    # Exemplo: https://dds-token-server.onrender.com/health
    KEEPALIVE_URL = os.getenv("KEEPALIVE_URL", "").strip() 
    KEEPALIVE_SECONDS = int(os.getenv("KEEPALIVE_SECONDS", "600"))

    # Força 1ª checagem imediatamente
    _last_token_refresh = -1e18
    _last_keepalive = -1e18

    # Se a URL não estiver definida, já deixa isso visível na TUI
    if not TOKEN_HEALTH_URL:
        setattr(metrics, "token_server_status", "OFF (TOKEN_STATUS_URL não definida)")
        setattr(metrics, "token_server_checked_at", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
 
    if not KEEPALIVE_URL:
        setattr(metrics, "keepalive_status", "OFF (KEEPALIVE_URL não definida)")
        setattr(metrics, "keepalive_checked_at", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
 

    with Live(layout, console=Console(), screen=True, auto_refresh=True, refresh_per_second=6) as live:
        while True:
            try:
                # --- NOVO: Health-check do servidor de token no máximo 1x a cada TOKEN_REFRESH_SECONDS ---
                now = time.time()
                if TOKEN_HEALTH_URL and (now - _last_token_refresh) >= TOKEN_REFRESH_SECONDS:
                    try:
                        r = requests.get(TOKEN_HEALTH_URL, timeout=8)
                        if r.status_code == 200:
                            setattr(metrics, "token_server_status", "ON")
                        else:
                            setattr(metrics, "token_server_status", f"OFF ({r.status_code})")
                        setattr(metrics, "token_server_checked_at", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
                    except Exception:
                        setattr(metrics, "token_server_status", "OFF")
                        setattr(metrics, "token_server_checked_at", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
 
                    _last_token_refresh = now         

                # --- NOVO: Keepalive do próprio serviço (Render), no máximo 1x a cada KEEPALIVE_SECONDS ---
                if KEEPALIVE_URL and (now - _last_keepalive) >= KEEPALIVE_SECONDS:
                    try:
                        r = requests.get(KEEPALIVE_URL, timeout=8)
                        if r.status_code == 200:
                            setattr(metrics, "keepalive_status", "ON")
                        else:
                            setattr(metrics, "keepalive_status", f"OFF ({r.status_code})")
                        setattr(metrics, "keepalive_checked_at", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
                    except Exception:
                        setattr(metrics, "keepalive_status", "OFF")
                        setattr(metrics, "keepalive_checked_at", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
                    _last_keepalive = now                          

                # Envia o status atual para o servidor web
                try:
                    snap = progress_bus.snapshot()
                    stats_data = {
                        "ciclo": metrics.ciclos_completos,
                        "uptime_str": f"{int(divmod(time.time() - interface.start_time, 3600)[0]):02d}h {int(divmod(time.time() - interface.start_time, 60)[0] % 60):02d}m",
                        "total_processados": stats.total_processados,
                        "sucesso": stats.sucesso,
                        "falhas": stats.falhas,
                        "anexos": getattr(stats, "anexos", 0),
                        "comandos": stats.comandos,
                        "tempo_medio": f"{stats.tempo_medio:.2f}s",
                        "status": stats.current_status.value,
                        "op": snap.get("op",""),
                        "phase": snap.get("phase",""),
                        "month": snap.get("month",""),
                        "company": snap.get("company","ALL"),
                        "current": snap.get("current",0),
                        "total": snap.get("total",0),
                        "pct": f"{snap.get('pct',0):.0f}%",
                        "copy_errors": snap.get("error_count", 0),
                        "md5_mismatch": snap.get("md5_mismatch", 0),
                        "last_errors": snap.get("last_errors", []),
                    }
                    requests.post(
                        "http://127.0.0.1:8080/update_status", # Use 127.0.0.1 se estiver na mesma máquina
                        json=stats_data,
                        timeout=1
                    )
                except requests.exceptions.RequestException:
                    # Falha ao conectar com o servidor web, ignora silenciosamente
                    pass
      
                emails_processados_neste_ciclo = 0
                
                metrics.ciclos_completos += 1
                log_manager.add(f"Iniciando Ciclo #{metrics.ciclos_completos}", "INFO")
                stats.current_status = StatusType.PROCESSING
                stats.current_task = "Verificando e-mails..."
                
                live.update(interface.get_renderable(progress_bus.renderable()), refresh=True)

                imap = None
                try:
                    imap = connect_imap()
                    unseen_ids = fetch_unseen(imap)
                    
                    if unseen_ids:
                        log_manager.add(f"Encontrados {len(unseen_ids)} novos e-mails.", "INFO")
                        # Chamamos a função síncrona que processa apenas 1 e-mail
                        results = processor.process_emails_sync(imap, unseen_ids)
                        emails_processados_neste_ciclo = results.get('success', 0)
                        log_manager.add(f"Processados: {results.get('success', 0)} sucesso, {results.get('failed', 0)} falhas.", "SUCCESS")
                        
                        imap.expunge()
                    else:
                        log_manager.add("Nenhum e-mail novo encontrado.", "INFO")

                except Exception as e:
                    log_manager.add(f"Erro no ciclo de e-mail: {e}", "ERROR")
                    metrics.ultimo_erro = str(e)[:50]
                finally:
                    if imap:
                        imap.logout()

                # --- LÓGICA DE ESPERA CONDICIONAL ---
                # Se processamos um e-mail, pulamos direto para o próximo ciclo.
                if emails_processados_neste_ciclo > 0:
                    log_manager.add("E-mail processado. Verificando novamente...", "INFO")
                    await asyncio.sleep(1) # Uma pequena pausa para não sobrecarregar
                    continue # Pula para a próxima iteração do while

                # Se não havia e-mails, iniciamos o período de espera normal.
                stats.current_status = StatusType.IDLE
                stats.current_task = f"Aguardando {APP_CONFIG.INTERVAL}s..."
                
                progress = Progress(
                    SpinnerColumn(),
                    TextColumn("[cyan]Próximo ciclo[/cyan]"),
                    BarColumn(bar_width=80),
                    TextColumn("[green]{task.completed:.0f}s decorrido[/green]  |  [yellow]{task.remaining:.0f}s restante[/yellow]"),
                    expand=True
                )
                wait_task = progress.add_task("wait", total=APP_CONFIG.INTERVAL)

                for _ in range(APP_CONFIG.INTERVAL):
                    metrics.memoria_uso = psutil.virtual_memory().percent
                    if stats.total_processados > 0:
                        uptime_horas = (time.time() - interface.start_time) / 3600
                        metrics.emails_por_hora = stats.total_processados / uptime_horas

                    live.update(interface.get_renderable(progress), refresh=True)
                    progress.advance(wait_task)

                    if handle_keyboard_input(interface):
                        log_manager.add("Sinal de encerramento recebido.", "WARNING")
                        return
                    
                    await asyncio.sleep(1)

            except KeyboardInterrupt:
                log_manager.add("Interrupção manual detectada.", "WARNING")
                if Confirm.ask("\n[red]Deseja realmente sair?[/red]"):
                    return
            except Exception as e:
                log_manager.add(f"Erro crítico no loop principal: {e}", "ERROR")
                metrics.ultimo_erro = str(e)[:50]
                await asyncio.sleep(20)
                
def main():
    """Ponto de entrada síncrono que inicializa e executa a aplicação."""
    try:
        # --- INÍCIO DA CORREÇÃO ---
        # Define o locale para Português (Brasil) para datas, meses, etc.
        try:
            locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
        except locale.Error:
            print("Aviso: Locale 'pt_BR.UTF-8' não encontrado. Usando locale padrão do sistema.")
        # --- FIM DA CORREÇÃO ---
        
        print("🚀 Inicializando Sistema DDS v4.1...")
        inicializar_pastas()
        asyncio.run(main_async())
    except Exception as e:
        print(f"\n❌ Erro fatal e inesperado: {e}")
        sys.exit(1)
    finally:
        print("\n👋 Sistema DDS encerrado. Até logo!")

if __name__ == '__main__':
    main()