"""Painel de terminal para a raspagem local do Rotalog.

Teclas: q para encerrar; r para solicitar o proximo ciclo imediatamente.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import curses
except ImportError:  # Windows nao oferece curses na distribuicao padrao do Python.
    curses = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from scripts.run_rotalog_local import LocalRotalogRunner


TZ = ZoneInfo(os.getenv("DDS_TIMEZONE", "America/Sao_Paulo"))


class TuiState:
    def __init__(self, interval_seconds: int):
        self.interval_seconds = interval_seconds
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


def _draw(screen, state: TuiState, output_dir: Path, runner: LocalRotalogRunner) -> None:
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

    cloud_status = "ATIVO (Firebase Storage)" if runner.firebase_enabled else "DESATIVADO (Apenas Local)"
    title = " ROTALOG LOCAL — Orange Pi "
    _line(screen, 0, title.center(width, "="), width, curses.A_BOLD)
    _line(screen, 2, f"Destino: {output_dir}  |  Nuvem: {cloud_status}", width)
    _line(screen, 3, f"Intervalo: {state.interval_seconds}s  |  Agora: {now:%d/%m/%Y %H:%M:%S}", width)

    if data["running"]:
        elapsed = (now - data["started_at"]).total_seconds() if data["started_at"] else 0
        _line(screen, 5, f"STATUS: RASPANDO  |  iniciado: {data['started_at']:%H:%M:%S}  |  tempo atual: {_format_duration(elapsed)}", width, curses.A_BOLD)
    else:
        next_run = data["next_run"]
        remaining = (next_run - now).total_seconds() if next_run else 0
        _line(screen, 5, f"STATUS: AGUARDANDO  |  proxima raspagem: {next_run:%H:%M:%S}  |  em: {_format_duration(remaining)}", width, curses.A_BOLD)

    last = data["last_result"]
    _line(screen, 7, "ULTIMA EXECUCAO", width, curses.A_UNDERLINE)
    if last:
        upload_flag = "  |  nuvem: OK" if last.get("firebaseUploaded") else ("  |  nuvem: FALHA" if runner.firebase_enabled else "")
        _line(screen, 8, f"Resultado: {last.get('status', '-').upper()}  |  inicio: {str(last.get('startedAt', '-'))[11:19]}  |  fim: {str(last.get('finishedAt', '-'))[11:19]}", width)
        _line(screen, 9, f"Tempo total: {last.get('durationSeconds', '-')}s  |  raspagem: {last.get('scrapeDurationSeconds', '-')}s", width)
        _line(screen, 10, f"Equipes: {last.get('totalTeams', '-')}  |  atualizadas: {last.get('updatedTeams', '-')}  |  ignoradas: {last.get('ignoredTeams', '-')}{upload_flag}", width)
        if last.get("error"):
            _line(screen, 11, f"Erro: {last['error']}", width, curses.A_BOLD)
    else:
        _line(screen, 8, "Aguardando a primeira execucao...", width)

    _line(screen, 13, "SESSAO ATUAL", width, curses.A_UNDERLINE)
    _line(screen, 14, f"Ciclos: {len(history)}  |  sucesso: {len(successful)}  |  erros: {errors}  |  media: {_format_duration(average)}", width)
    _line(screen, 15, f"Equipes atualizadas: {total_updates}  |  ignoradas: {total_ignored}", width)
    _line(screen, 17, "Arquivos: equipes/current/index.json  |  equipes/daily/AAAA-MM-DD  |  logs/execucoes.jsonl", width)
    _line(screen, height - 2, "Teclas: r = executar agora   q = encerrar com seguranca", width, curses.A_REVERSE)
    screen.refresh()


def _curses_main(screen, runner: LocalRotalogRunner, state: TuiState, output_dir: Path) -> None:
    curses.curs_set(0)
    screen.timeout(250)
    worker = threading.Thread(target=_worker, args=(runner, state), daemon=True)
    worker.start()
    try:
        while True:
            _draw(screen, state, output_dir, runner)
            key = screen.getch()
            if key in (ord("q"), ord("Q")):
                break
            if key in (ord("r"), ord("R")):
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
    args = parser.parse_args()
    if args.interval_seconds < 30:
        parser.error("--interval-seconds deve ser no minimo 30")
    if curses is None:
        parser.error("Este painel requer curses; execute-o no Linux do Orange Pi.")

    load_dotenv(ROOT / ".env")
    enable_firebase = args.firebase or os.getenv("ROTALOG_UPLOAD_FIREBASE", "false").strip().lower() in ("true", "1", "yes")

    output_dir = Path(args.output_dir).resolve()
    runner = LocalRotalogRunner(output_dir, args.empresa, enable_firebase=enable_firebase)
    state = TuiState(args.interval_seconds)
    curses.wrapper(_curses_main, runner, state, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
