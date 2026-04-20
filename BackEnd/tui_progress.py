#tui_progress.py
import threading, time
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn, 
    TimeElapsedColumn, TimeRemainingColumn, DownloadColumn,
    TransferSpeedColumn, TaskProgressColumn
)
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

@dataclass
class Snapshot:
    active: bool = False
    op: str = ""         # "backup" | "limpar"
    phase: str = ""      # "descobrindo", "copiando", "verificando", "apagando", ...
    month: str = ""      # "YYYY-MM"
    company: str = "ALL"
    current: int = 0
    total: int = 0
    bytes_done: int = 0
    bytes_total: int = 0
    pct: float = 0.0
    started_at: float = 0.0
    error_count: int = 0
    md5_mismatch: int = 0
    last_errors: List[str] = None

class ProgressBus:
    def __init__(self):
        self._lock = threading.Lock()
        self._console = Console()
        
        # Mapeamento de cores por tipo de operação
        self._op_colors = {
            "backup": "cyan",
            "limpar": "yellow",
            "verificar": "green",
            "restaurar": "magenta"
        }
        
        # Emojis/ícones por fase
        self._phase_icons = {
            "descobrindo": "🔍",
            "copiando": "📦",
            "verificando": "✓",
            "apagando": "🗑️",
            "finalizando": "✨"
        }
        
        self._progress = Progress(
            SpinnerColumn(spinner_name="dots"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(
                bar_width=None,
                style="bar.back",
                complete_style="bar.complete",
                finished_style="bar.finished",
                pulse_style="bar.pulse"
            ),
            TaskProgressColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            TextColumn("•"),
            TimeRemainingColumn(),
            TransferSpeedColumn(),
            expand=True,
            console=self._console
        )
        self._task_id: Optional[int] = None
        self._snap = Snapshot()

    def _get_color(self, op: str) -> str:
        """Retorna a cor para a operação"""
        return self._op_colors.get(op.lower(), "blue")

    def _get_icon(self, phase: str) -> str:
        """Retorna o ícone para a fase"""
        return self._phase_icons.get(phase.lower(), "▶")

    def _format_description(self, op: str, phase: str, month: str, company: str) -> str:
        """Formata a descrição com cores e ícones"""
        color = self._get_color(op)
        icon = self._get_icon(phase)
        
        return (
            f"{icon} "
            f"[bold {color}]{op.upper()}[/bold {color}] "
            f"[dim]│[/dim] "
            f"[{color}]{phase}[/{color}] "
            f"[dim]│[/dim] "
            f"[bold white]{month}[/bold white] "
            f"[dim]│[/dim] "
            f"[yellow]{company}[/yellow]"
        )

    def start(self, *, op: str, phase: str, month: str, total: int, bytes_total: int = 0, company: str = "ALL"):
        with self._lock:
            if self._task_id is not None:
                try:
                    self._progress.remove_task(self._task_id)
                except Exception:
                    pass
            try:
                self._progress.stop()
            except Exception:
                pass
            
            self._progress.start()
            
            desc = self._format_description(op, phase, month, company)
            self._task_id = self._progress.add_task(
                desc, 
                total=max(int(total or 0), 1),
                start=True
            )
            
            self._snap = Snapshot(
                True, op, phase, month, company, 
                0, int(total or 0),
                0, int(bytes_total or 0), 
                0.0, time.time(),
                0, 0, []
            )

    def update(self, *, advance: int = 0, phase: Optional[str] = None, add_bytes: int = 0):
        with self._lock:
            if self._task_id is None:
                return
            
            if phase:
                self._snap.phase = phase
                desc = self._format_description(
                    self._snap.op, 
                    phase, 
                    self._snap.month, 
                    self._snap.company
                )
                self._progress.update(self._task_id, description=desc)
            
            if advance:
                self._progress.update(self._task_id, advance=int(advance))
                self._snap.current += int(advance)
            
            if add_bytes:
                self._snap.bytes_done += int(add_bytes)
            
            if self._snap.total:
                self._snap.pct = min(100.0, 100.0 * self._snap.current / max(self._snap.total, 1))

    def finish(self):
        with self._lock:
            if self._task_id is not None:
                try:
                    self._progress.update(self._task_id, completed=self._progress.tasks[0].total)
                    # Pequena pausa para mostrar 100%
                    time.sleep(0.5)
                except Exception:
                    pass
            
            self._task_id = None
            self._snap.active = False
            
            try:
                self._progress.stop()
            except Exception:
                pass
            
            # Mostra resumo ao finalizar
            self._show_summary()

    def _show_summary(self):
        """Mostra um resumo bonito ao finalizar"""
        if not self._snap.op:
            return
            
        elapsed = time.time() - self._snap.started_at
        color = self._get_color(self._snap.op)
        
        summary_lines = [
            f"[bold {color}]✓ {self._snap.op.upper()} CONCLUÍDO[/bold {color}]",
            f"",
            f"[dim]Mês:[/dim] [white]{self._snap.month}[/white]",
            f"[dim]Empresa:[/dim] [yellow]{self._snap.company}[/yellow]",
            f"[dim]Arquivos:[/dim] [white]{self._snap.current:,}/{self._snap.total:,}[/white]",
        ]
        
        if self._snap.bytes_total > 0:
            summary_lines.append(
                f"[dim]Dados:[/dim] [white]{self._format_bytes(self._snap.bytes_done)}[/white]"
            )
        
        summary_lines.append(f"[dim]Tempo:[/dim] [white]{self._format_time(elapsed)}[/white]")
        
        if self._snap.error_count > 0:
            summary_lines.append(f"[dim]Erros:[/dim] [red]{self._snap.error_count}[/red]")
        
        if self._snap.md5_mismatch > 0:
            summary_lines.append(f"[dim]MD5 mismatch:[/dim] [red]{self._snap.md5_mismatch}[/red]")
        
        panel = Panel(
            "\n".join(summary_lines),
            border_style=color,
            padding=(1, 2)
        )
        
        self._console.print(panel)

    def _format_bytes(self, bytes_val: int) -> str:
        """Formata bytes em formato legível"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.2f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.2f} PB"

    def _format_time(self, seconds: float) -> str:
        """Formata tempo em formato legível"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}min"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h {minutes}min"

    def note_error(self, msg: str):
        with self._lock:
            self._snap.error_count += 1
            self._snap.last_errors = (self._snap.last_errors or [])
            self._snap.last_errors.append(msg.strip())
            # mantém só os 5 últimos
            self._snap.last_errors = self._snap.last_errors[-5:]
            
            # Mostra erro em vermelho
            self._console.print(f"[red]✗[/red] {msg}", style="dim")

    def note_md5_mismatch(self, blob: str, gcs_hex: str, drive_hex: str):
        with self._lock:
            self._snap.md5_mismatch += 1
            error_msg = f"MD5 diff: {blob} gcs={gcs_hex} drive={drive_hex}"
            self.note_error(error_msg)

    def renderable(self):
        with self._lock:
            return self._progress if self._snap.active else None

    def snapshot(self) -> Dict:
        with self._lock:
            return asdict(self._snap)

    def has_active(self) -> bool:
        with self._lock:
            return self._snap.active

progress_bus = ProgressBus()