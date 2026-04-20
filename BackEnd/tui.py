# -----------------------------------------------------------------------------
# Módulo: tui.py
# Versão: 4.1 (Final com correção de renderização completa)
#
# Histórico de Alterações:
#   - 29/08/2025 (Gemini): Módulo criado.
#   - 29/08/2025 (Gemini): Corrigido argumento 'progress' e alinhamento de painéis.
# -----------------------------------------------------------------------------

import datetime
import time
from typing import Optional

from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress, BarColumn, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from config import APP_CONFIG
from core.models import EmailStats, SystemMetrics, StatusType
from logger import log_manager

class DDSInterface:
    def __init__(self, stats: EmailStats, metrics: SystemMetrics):
        self.stats = stats
        self.metrics = metrics
        self.start_time = time.time()

    def _create_header_panel(self) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_row(Align.center(Text(
            "📡 SISTEMA DDS - Processador Inteligente de E-mails 📡",
            style=f"bold white on {APP_CONFIG.THEME['primary']}"
        )))
        grid.add_row(Align.center(Text(
            f"v4.1 | {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            style="dim white"
        )))
        return Panel(grid, border_style=APP_CONFIG.THEME['border'], height=3)

    def _create_stats_panel(self) -> Panel:
        uptime_seconds = time.time() - self.start_time
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        uptime_str = f"{int(hours):02d}h {int(minutes):02d}m"
        taxa_sucesso = (self.stats.sucesso / max(self.stats.total_processados, 1)) * 100

        table = Table.grid(padding=(0, 2))
        table.add_column(style=APP_CONFIG.THEME['primary'], no_wrap=True)
        table.add_column(style="white", no_wrap=True)

        table.add_row("🔄 Ciclos", str(self.metrics.ciclos_completos))
        table.add_row("🕐 Uptime", uptime_str)
        table.add_row("📧 E-mails", str(self.stats.total_processados))
        table.add_row("✅ Sucesso", f"{self.stats.sucesso} ({taxa_sucesso:.1f}%)")
        table.add_row("❌ Falhas", str(self.stats.falhas))
        table.add_row("⚡ Comandos", str(self.stats.comandos))
        table.add_row("📎 Anexos", str(getattr(self.stats, "anexos", 0)))
        table.add_row("⏱️ T. Médio", f"{self.stats.tempo_medio:.2f}s")
        table.add_row(" ", " ")
        table.add_row("📊 Status", self.stats.current_status.value)
        table.add_row("📝 Tarefa", self.stats.current_task[:25])
        
        return Panel(
            table,
            title=f"[bold {APP_CONFIG.THEME['primary']}]📊 Estatísticas[/]",
            border_style=APP_CONFIG.THEME['primary'],
            padding=(0, 1)
        )

    def _create_logs_panel(self) -> Panel:
        """Cria o painel de logs."""
        logs = log_manager.get_formatted_logs()
        
        # --- CORREÇÃO AQUI ---
        # Trocamos Text() por Text.from_markup() para que a rich interprete as tags de cor.
        logs_text = Text.from_markup("\n".join(logs[-20:])) if logs else Text("Aguardando atividades...", style="dim")
        
        return Panel(
            logs_text,
            title=f"[bold {APP_CONFIG.THEME['success']}]📋 Logs de Atividade[/]",
            border_style=APP_CONFIG.THEME['success'],
            padding=(0, 1)
        )


    def _create_metrics_panel(self) -> Panel:
        # Import local para não quebrar em ambientes sem psutil
        try:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=0.0)
            import os
            # Usa raiz do sistema (ou altere para a pasta de dados do seu app)
            disk_percent = psutil.disk_usage(os.path.sep).percent
        except Exception:
            cpu_percent = None
            disk_percent = None

        table = Table.grid(padding=(0, 2))
        table.add_column(style="magenta")
        table.add_column(justify="right", style="white")

        # NOVOS: CPU e Disco (se disponíveis)
        if cpu_percent is not None:
            table.add_row("💻 CPU", f"{cpu_percent:.1f}%")
        if disk_percent is not None:
            table.add_row("💾 Disco", f"{disk_percent:.1f}%")

        table.add_row("🧠 RAM Usage", f"{self.metrics.memoria_uso:.1f}%")
        table.add_row("📨 E-mails/hora", f"{self.metrics.emails_por_hora:.1f}")
        table.add_row("⏰ Intervalo", f"{APP_CONFIG.INTERVAL}s")

        # --- NOVO: Status do servidor de token (health-check) ---
        token_srv = getattr(self.metrics, "token_server_status", None)
        token_chk = getattr(self.metrics, "token_server_checked_at", None)

        # Sempre mostrar (para ficar fácil localizar na TUI)
        srv_txt = str(token_srv or "-")
        if srv_txt.startswith("ON"):
            srv_txt = f"[green]{srv_txt}[/green]"
        elif srv_txt.startswith("OFF"):
            srv_txt = f"[red]{srv_txt}[/red]"
        table.add_row("🛰️ Servidor de token", srv_txt)
        if token_chk:
            table.add_row("🕒 Checado (UTC)", str(token_chk))


        # --- NOVO: Keepalive do serviço (Render) ---
        ka_srv = getattr(self.metrics, "keepalive_status", None)
        ka_chk = getattr(self.metrics, "keepalive_checked_at", None)
        ka_txt = str(ka_srv or "-")
        if ka_txt.startswith("ON"):
            ka_txt = f"[green]{ka_txt}[/green]"
        elif ka_txt.startswith("OFF"):
            ka_txt = f"[red]{ka_txt}[/red]"
        table.add_row("🧷 Keepalive", ka_txt)
        if ka_chk:
            table.add_row("🕒 Keepalive (UTC)", str(ka_chk))


        # NOVO: Batch Size (se existir no APP_CONFIG)
        bs = getattr(APP_CONFIG, "BATCH_SIZE", None)
        if bs:
            table.add_row("🔄 Batch Size", str(bs))

        if self.metrics.ultimo_erro:
            table.add_row(" ", " ")
            table.add_row(f"[red]Último Erro[/]", f"[red]{self.metrics.ultimo_erro[:25]}[/red]")

        return Panel(
            table,
            title=f"[bold magenta]🖥️ Métricas do Sistema[/]",
            border_style="magenta",
            padding=(0, 1)
        )


    def _create_footer_panel(self, progress: Optional[Progress] = None) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_row(Align.center(Text(
            "T - Alterar Intervalo | L - Limpar Logs | D - Debug | Q - Sair",
            style="yellow"
        )))
        grid.add_row(progress if progress else "")
        return Panel(grid, border_style="yellow", height=5)
        
    def get_renderable(self, progress: Optional[Progress] = None) -> Layout:
        """Cria e retorna o objeto de layout completo para ser renderizado."""
        layout = Layout(name="root")
        layout.split(
            Layout(self._create_header_panel(), name="header", size=3),
            Layout(name="content", ratio=1),
            Layout(self._create_footer_panel(progress), name="footer", size=5)
        )
        layout["content"].split_row(
            self._create_stats_panel(),
            self._create_logs_panel(),
            self._create_metrics_panel(),
        )
        return layout