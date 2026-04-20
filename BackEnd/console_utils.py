# Module: console_utils.py
# Description: Captura tecla sem bloqueio no terminal, compatível Windows/Linux.
# Change Log:
#   07-06-25:  • Extraído para módulo separado console_utils.
# Guia de Comentários:
#   - kbhit(): retorna True se houver tecla pressionada.
#   - getch(): lê um caractere sem bloqueio.
  
import os
import sys
import time
import logging

if os.name == 'nt':
    import msvcrt

    def kbhit() -> bool:
        return msvcrt.kbhit()

    def getch() -> str:
        return msvcrt.getch().decode('utf-8', errors='ignore')

else:
    import select
    import termios
    import tty

    def kbhit() -> bool:
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        return bool(dr)

    def getch() -> str:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return ch



logger = logging.getLogger(__name__)

def timeit_command(func):
    """
    Decorator que mede o tempo de execução de qualquer comando
    e emite um INFO no logger.
    """
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            # para e-mails: args[0] costuma ser o destinatário / sender
            # para Telegram: args[0] pode ser Update, mas focamos em nome do func
            logger.info(
                "Comando %s executado em %.2f s",
                func.__name__,
                elapsed
            )
    return wrapper