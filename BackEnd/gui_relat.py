#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
relatorio_fotos_gui.py
----------------------
Pequena interface gráfica para disparar o comando:

    relatorio <<mes>> FOTO

usando a lógica já existente em core.cmd_relatorio.comando_relatorio.
O relatório é gerado e enviado por e-mail da mesma forma que no fluxo via e-mail.
"""

from __future__ import annotations

import threading
import datetime as dt
import tkinter as tk
from tkinter import ttk, messagebox

try:
    # Ajuste o import se o pacote/core estiver em outro caminho
    from core.cmd_relatorio import comando_relatorio
except ImportError as e:
    raise SystemExit(
        "Erro ao importar core.cmd_relatorio. "
        "Certifique-se de executar este script a partir da raiz do projeto "
        "e que o pacote 'core' está acessível no PYTHONPATH.\n\n"
        f"Detalhes: {e}"
    ) from e


MESES_PT = [
    "01 - Janeiro",
    "02 - Fevereiro",
    "03 - Março",
    "04 - Abril",
    "05 - Maio",
    "06 - Junho",
    "07 - Julho",
    "08 - Agosto",
    "09 - Setembro",
    "10 - Outubro",
    "11 - Novembro",
    "12 - Dezembro",
]


class RelatorioFotosGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Relatório DDS - Fotos (Drive)")
        self.root.geometry("420x220")
        self.root.minsize(400, 200)

        # Variáveis
        mes_atual = dt.date.today().month
        self.mes_var = tk.StringVar(value=f"{mes_atual:02d} - {MESES_PT[mes_atual - 1].split(' - ', 1)[1]}")
        self.email_var = tk.StringVar(value="")  # você pode colocar um default aqui se quiser
        self.status_var = tk.StringVar(value="Pronto para gerar o relatório.")
        self._worker_thread: threading.Thread | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 8}

        frame = ttk.Frame(self.root)
        frame.pack(fill="both", expand=True)

        # Linha 1: Mês
        lbl_mes = ttk.Label(frame, text="Mês do relatório:")
        lbl_mes.grid(row=0, column=0, sticky="w", **pad)

        cb_mes = ttk.Combobox(
            frame,
            textvariable=self.mes_var,
            values=MESES_PT,
            state="readonly",
            width=20,
        )
        cb_mes.grid(row=0, column=1, sticky="w", **pad)

        # Linha 2: E-mail destino
        lbl_email = ttk.Label(frame, text="E-mail de destino:")
        lbl_email.grid(row=1, column=0, sticky="w", **pad)

        entry_email = ttk.Entry(frame, textvariable=self.email_var, width=30)
        entry_email.grid(row=1, column=1, sticky="we", **pad)

        # Linha 3: Botão
        self.btn_gerar = ttk.Button(
            frame,
            text="Gerar relatório com fotos",
            command=self.on_click_gerar,
        )
        self.btn_gerar.grid(row=2, column=0, columnspan=2, pady=(15, 5))

        # Linha 4: Status
        lbl_status = ttk.Label(frame, textvariable=self.status_var, anchor="w")
        lbl_status.grid(row=3, column=0, columnspan=2, sticky="we", padx=10, pady=(5, 5))

        # Barra de progresso indeterminada (para indicar processamento)
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=4, column=0, columnspan=2, sticky="we", padx=10, pady=(0, 10))

        # Configurações de grid
        frame.columnconfigure(0, weight=0)
        frame.columnconfigure(1, weight=1)

    def _set_status(self, text: str) -> None:
        """Atualiza o texto de status na barra inferior."""
        self.status_var.set(text)

    def _set_running(self, running: bool) -> None:
        """Habilita/desabilita botão e controla a barra de progresso."""
        if running:
            self.btn_gerar.config(state="disabled")
            self.progress.start(10)
        else:
            self.btn_gerar.config(state="normal")
            self.progress.stop()
    

    # ------------------------------------------------------------------ #
    # CALLBACKS
    # ------------------------------------------------------------------ #

    def on_click_gerar(self) -> None:
        """Dispara o comando em uma thread separada."""
        mes_display = self.mes_var.get().strip()
        email = self.email_var.get().strip()

        if not email:
            messagebox.showwarning("E-mail obrigatório", "Informe o e-mail de destino para receber o relatório.")
            return

        try:
            # mes_display = "10 - Outubro" -> "10"
            mes_num_str = mes_display.split(" ", 1)[0]
            mes_num = int(mes_num_str)
        except Exception:
            messagebox.showerror("Mês inválido", f"Mês selecionado inválido: '{mes_display}'.")
            return

        # Comando no formato já esperado pelo cmd_relatorio: "10 FOTO"
        argumento = f"{mes_num} FOTO"

        if self._worker_thread and self._worker_thread.is_alive():
            messagebox.showinfo("Em andamento", "Já existe um relatório sendo gerado. Aguarde terminar.")
            return

        self.btn_gerar.config(state="disabled")
        self.status_var.set(f"Gerando relatório de {mes_num:02d}/{dt.date.today().year} com fotos…")
        self.progress.start(10)

        self._worker_thread = threading.Thread(
            target=self._run_comando_relatorio,
            args=(argumento, email),
            daemon=True,
        )
        self._worker_thread.start()

    def _run_comando_relatorio(self, argumento: str, email: str):
        """
        Executa comando_relatorio em thread separada.

        Esta função é o alvo da thread criada em on_click_gerar.
        Aqui chamamos comando_relatorio de forma síncrona e,
        ao final, agendamos a atualização da UI com root.after.
        """
        self._set_status("Gerando relatório, aguarde…")
        self._set_running(True)

        anexos = []
        erro = None

        try:
            # manter_arquivos=True -> NÃO apaga os PDFs
            anexos = comando_relatorio(argumento, email, manter_arquivos=True)
        except Exception as e:
            erro = e

        def on_finish():
            self._set_running(False)
            if erro:
                messagebox.showerror("Erro", f"Ocorreu um erro: {erro}")
                self._set_status("Erro ao gerar relatório.")
            else:
                if anexos:
                    # normalmente aqui terá só o relatorio_fotos_YYYY-MM.pdf
                    msg = f"Relatório gerado e salvo em:\n{anexos[0]}"
                else:
                    msg = "Relatório gerado, mas nenhum anexo foi retornado."
                messagebox.showinfo("Concluído", msg)
                self._set_status(msg.replace("\n", " "))

        # Volta para a thread da UI
        self.root.after(0, on_finish)



def main() -> None:
    root = tk.Tk()
    app = RelatorioFotosGUI(root)
    root.mainloop()



if __name__ == "__main__":
    main()
