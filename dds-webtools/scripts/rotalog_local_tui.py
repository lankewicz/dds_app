"""Painel de terminal para o Rotalog (Orange Pi).

Pode rodar em dois modos:
1. Modo Visualizador (Recomendado): python scripts/rotalog_local_tui.py --view
   Monitora em tempo real os dados gravados pelo serviço systemd (sem rodar raspagem própria).
2. Modo Executor: python scripts/rotalog_local_tui.py --firebase
   Executa os ciclos de raspagem diretamente nesta tela.

Teclas: q para sair do painel; r para forçar leitura/execução.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import curses
except ImportError:  # Windows não oferece curses na distribuição padrão do Python.
    curses = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from scripts.run_rotalog_local import LocalRotalogRunner


TZ = ZoneInfo(os.getenv("DDS_TIMEZONE", "America/Sao_Paulo"))


class TuiState:
    def __init__(self, interval_seconds: int, viewer_mode: bool = False):
        self.interval_seconds = interval_seconds
        self.viewer_mode = viewer_mode
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.run_now = threading.Event()
        self.running = False
        self.started_at: datetime | None = None
        self.next_run: datetime | None = datetime.now(TZ)
        self.last_result: dict | None = None
        self.history: list[dict] = []

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "running": self.running,
                "started_at": self.started_at,
                "next_run": self.next_run,
                "last_result": dict(self.last_result) if self.last_result else None,
                "history": list(self.history),
                "viewer_mode": self.viewer_mode,
            }


def _worker(runner: LocalRotalogRunner, state: TuiState) -> None:
    while not state.stop.is_set():
        with state.lock:
            state.running = True
            state.started_at = datetime.now(TZ)
            state.next_run = None
        result = runner.run_once()
        with state.lock:
            state.running = False
            state.last_result = result
            state.history = (state.history + [result])[-100:]
            state.next_run = datetime.now(TZ) + timedelta(seconds=max(0, state.interval_seconds - result["durationSeconds"]))

        wait_seconds = max(1, state.interval_seconds - float(result["durationSeconds"]))
        deadline = time.monotonic() + wait_seconds
        while not state.stop.is_set() and time.monotonic() < deadline:
            if state.run_now.wait(timeout=min(0.5, max(0.1, deadline - time.monotonic()))):
                state.run_now.clear()
                break


def _load_history_from_logs(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    entries = []
    try:
        with log_path.open("r", encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return entries[-100:]


def _viewer_worker(state: TuiState, output_dir: Path) -> None:
    log_path = output_dir / "rotalog" / "logs" / "execucoes.jsonl"
    index_path = output_dir / "rotalog" / "equipes" / "current" / "index.json"
    tmp_path = index_path.with_suffix(".tmp")

    while not state.stop.is_set():
        history = _load_history_from_logs(log_path)
        last = history[-1] if history else None
        is_scraping = tmp_path.exists()

        with state.lock:
            state.history = history
            state.last_result = last
            state.running = is_scraping
            if last and last.get("finishedAt"):
                try:
                    fin = datetime.fromisoformat(str(last["finishedAt"]))
                    next_run = fin + timedelta(seconds=state.interval_seconds)
                    state.next_run = next_run
                except Exception:
                    state.next_run = None
            else:
                state.next_run = None

        state.stop.wait(timeout=1.0)


def _format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "-"
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _line(screen, row: int, text: str, width: int, attr: int = 0) -> None:
    try:
        screen.addnstr(row, 0, text, max(0, width - 1), attr)
    except curses.error:
        pass


def _draw(screen, state: TuiState, output_dir: Path, runner: LocalRotalogRunner | None) -> None:
    screen.erase()
    height, width = screen.getmaxyx()
    data = state.snapshot()
    now = datetime.now(TZ)
    history = data["history"]
    successful = [item for item in history if item.get("status") == "success"]
    errors = len(history) - len(successful)
    average = sum(float(item.get("durationSeconds") or 0) for item in successful) / len(successful) if successful else None
    total_updates = sum(int(item.get("updatedTeams") or 0) for item in successful)
    total_ignored = sum(int(item.get("ignoredTeams") or 0) for item in successful)

    is_viewer = data["viewer_mode"]
    mode_badge = "VISUALIZADOR DO SERVIÇO" if is_viewer else "EXECUTOR DIRETO"
    title = f" ROTALOG — Orange Pi [{mode_badge}] "
    _line(screen, 0, title.center(width, "="), width, curses.A_BOLD)
    _line(screen, 2, f"Destino: {output_dir}  |  Servico Systemd: rotalog.service", width)
    _line(screen, 3, f"Intervalo: {state.interval_seconds}s  |  Agora: {now:%d/%m/%Y %H:%M:%S}", width)

    if data["running"]:
        _line(screen, 5, "STATUS: RASPANDO / ATUALIZANDO DADOS...", width, curses.A_BOLD)
    else:
        next_run = data["next_run"]
        if next_run:
            remaining = (next_run - now).total_seconds()
            if remaining > 0:
                _line(screen, 5, f"STATUS: AGUARDANDO  |  proxima raspagem estimada: {next_run:%H:%M:%S}  |  em: {_format_duration(remaining)}", width, curses.A_BOLD)
            else:
                _line(screen, 5, f"STATUS: AGUARDANDO CICLO DO SERVICO...", width, curses.A_BOLD)
        else:
            _line(screen, 5, "STATUS: AGUARDANDO INICIO DOS REGISTROS...", width, curses.A_BOLD)

    last = data["last_result"]
    _line(screen, 7, "ULTIMA EXECUCAO DO SERVICO", width, curses.A_UNDERLINE)
    if last:
        upload_flag = "  |  nuvem: OK" if last.get("firebaseUploaded") else "  |  nuvem: PENDENTE/LOCAL"
        _line(screen, 8, f"Resultado: {last.get('status', '-').upper()}  |  inicio: {str(last.get('startedAt', '-'))[11:19]}  |  fim: {str(last.get('finishedAt', '-'))[11:19]}", width)
        _line(screen, 9, f"Tempo total: {last.get('durationSeconds', '-')}s  |  raspagem: {last.get('scrapeDurationSeconds', '-')}s", width)
        _line(screen, 10, f"Equipes: {last.get('totalTeams', '-')}  |  atualizadas: {last.get('updatedTeams', '-')}  |  ignoradas: {last.get('ignoredTeams', '-')}{upload_flag}", width)
        if last.get("error"):
            _line(screen, 11, f"Erro: {last['error']}", width, curses.A_BOLD)
    else:
        _line(screen, 8, "Aguardando registros do servico em execucoes.jsonl...", width)

    _line(screen, 13, "SESSAO / HISTORICO RECENTE", width, curses.A_UNDERLINE)
    _line(screen, 14, f"Ciclos: {len(history)}  |  sucesso: {len(successful)}  |  erros: {errors}  |  media: {_format_duration(average)}", width)
    _line(screen, 15, f"Equipes atualizadas: {total_updates}  |  ignoradas: {total_ignored}", width)
    _line(screen, 17, "Arquivos: equipes/current/index.json  |  equipes/daily/AAAA-MM-DD  |  logs/execucoes.jsonl", width)

    if is_viewer:
        _line(screen, height - 2, "Teclas: q = sair do visualizador (o servico continuara rodando)", width, curses.A_REVERSE)
    else:
        _line(screen, height - 2, "Teclas: r = executar agora   q = encerrar execucao", width, curses.A_REVERSE)

    screen.refresh()


def _curses_main(screen, runner: LocalRotalogRunner | None, state: TuiState, output_dir: Path) -> None:
    curses.curs_set(0)
    screen.timeout(250)

    if state.viewer_mode:
        worker = threading.Thread(target=_viewer_worker, args=(state, output_dir), daemon=True)
    else:
        worker = threading.Thread(target=_worker, args=(runner, state), daemon=True)

    worker.start()
    try:
        while True:
            _draw(screen, state, output_dir, runner)
            key = screen.getch()
            if key in (ord("q"), ord("Q")):
                break
            if key in (ord("r"), ord("R")) and not state.viewer_mode:
                state.run_now.set()
    finally:
        state.stop.set()
        worker.join(timeout=3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="dados-local")
    parser.add_argument("--interval-seconds", type=int, default=120)
    parser.add_argument("--empresa", default="ChicoEletro")
    parser.add_argument("--firebase", action="store_true", help="Ativa sincronização automática com Firebase Storage")
    parser.add_argument("--view", action="store_true", help="Abre como visualizador passivo do serviço systemd (sem raspar)")
    args = parser.parse_args()
    if args.interval_seconds < 30:
        parser.error("--interval-seconds deve ser no minimo 30")
    if curses is None:
        parser.error("Este painel requer curses; execute-o no Linux do Orange Pi.")

    load_dotenv(ROOT / ".env")
    enable_firebase = args.firebase or os.getenv("ROTALOG_UPLOAD_FIREBASE", "false").strip().lower() in ("true", "1", "yes")

    output_dir = Path(args.output_dir).resolve()

    if args.view:
        runner = None
        state = TuiState(args.interval_seconds, viewer_mode=True)
    else:
        runner = LocalRotalogRunner(output_dir, args.empresa, enable_firebase=enable_firebase)
        state = TuiState(args.interval_seconds, viewer_mode=False)

    curses.wrapper(_curses_main, runner, state, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
