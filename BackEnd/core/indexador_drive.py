"""
core/indexador_drive.py

Rotina para indexar arquivos do Google Drive (Meu Drive e Drives Compartilhados),
com indicador detalhado de progresso em janela Tkinter (ttkbootstrap opcional).

Recursos:
- Autenticação OAuth (credentials.json -> token.json)
- Duas fases para melhor desempenho e paths corretos:
  (1) Carrega todas as pastas (id, nome, pai) para montar o caminho completo
  (2) Carrega todos os arquivos (exceto pastas) com metadados essenciais
- Gera índice em CSV e, se pandas/pyarrow estiverem instalados, também em Parquet
- Suporta filtrar por uma pasta raiz específica (folder_id) 
- Progresso detalhado: estágio, páginas, itens por segundo, estimativa, logs
- Tratamento de rate limit com retentativa exponencial

Dependências:
  pip install google-api-python-client google-auth google-auth-oauthlib
  (opcional) pip install pandas pyarrow ttkbootstrap

Arquivos esperados:
  - credentials.json (OAuth client) ao lado do script
  - token.json será criado no primeiro login

Uso CLI (sem GUI):
  python core/indexador_drive.py --no-gui --saida ./data/index_drive.csv

Uso GUI (padrão):
  python core/indexador_drive.py --saida ./data/index_drive.csv

"""
from __future__ import annotations

import os
import sys
import time
import json
import math
import queue
import threading
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

# Google API
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Opcional: pandas
try:
    import pandas as pd  # type: ignore
except Exception:
    pd = None  # degrade para CSV apenas

# GUI: Tkinter + (opcional) ttkbootstrap
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
try:
    import ttkbootstrap as tb  # type: ignore
    _HAS_TTKB = True
except Exception:
    _HAS_TTKB = False

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
]

DEFAULT_FIELDS_FILES = (
    "nextPageToken, files("
    "id, name, mimeType, size, md5Checksum, parents, createdTime, modifiedTime,"
    " trashed, owners(displayName,emailAddress), webViewLink, driveId)"
)
DEFAULT_FIELDS_FOLDERS = (
    "nextPageToken, files(id, name, parents, mimeType, driveId, trashed)"
)

@dataclass
class IndexItem:
    id: str
    name: str
    mimeType: str
    size: Optional[int]
    md5: Optional[str]
    createdTime: str
    modifiedTime: str
    trashed: bool
    owner_name: Optional[str]
    owner_email: Optional[str]
    webViewLink: Optional[str]
    driveId: Optional[str]
    parents: List[str] = field(default_factory=list)
    path: Optional[str] = None
    ext: Optional[str] = None

    @staticmethod
    def from_api(d: dict) -> "IndexItem":
        size = int(d.get("size")) if d.get("size") is not None else None
        owners = d.get("owners") or []
        owner_name = owners[0].get("displayName") if owners else None
        owner_email = owners[0].get("emailAddress") if owners else None
        name = d.get("name") or ""
        ext = None
        if "." in name:
            _, _, tail = name.rpartition(".")
            ext = tail.lower() or None
        return IndexItem(
            id=d.get("id"),
            name=name,
            mimeType=d.get("mimeType"),
            size=size,
            md5=d.get("md5Checksum"),
            createdTime=d.get("createdTime"),
            modifiedTime=d.get("modifiedTime"),
            trashed=bool(d.get("trashed")),
            owner_name=owner_name,
            owner_email=owner_email,
            webViewLink=d.get("webViewLink"),
            driveId=d.get("driveId"),
            parents=d.get("parents") or [],
            path=None,
            ext=ext,
        )

class DriveIndexer:
    def __init__(
        self,
        credentials_path: str = "credentials.json",
        token_path: str = "token.json",
        folder_id: Optional[str] = None,
        include_shared_drives: bool = True,
        page_size: int = 1000,
        logger: Optional[callable] = None,
    ) -> None:
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.folder_id = folder_id
        self.include_shared_drives = include_shared_drives
        self.page_size = max(1, min(1000, page_size))
        self._service = None
        self._log = logger or (lambda msg: None)

    # ---------- AUTH ----------
    def _get_creds(self) -> Credentials:
        creds: Optional[Credentials] = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"Arquivo de credenciais não encontrado: {self.credentials_path}"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open(self.token_path, "w", encoding="utf-8") as token:
                token.write(creds.to_json())
        return creds

    def _service_build(self):
        if self._service is None:
            self._log("Autenticando no Google Drive…")
            creds = self._get_creds()
            self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
            self._log("✔ Autenticado e serviço construído.")
        return self._service

    # ---------- LISTAGEM BASE ----------
    def _list_files_paged(self, query: Optional[str], fields: str) -> Iterator[Tuple[List[dict], Optional[str]]]:
        svc = self._service_build()
        page_token = None
        while True:
            try:
                req = (
                    svc.files()
                    .list(
                        q=query,
                        fields=fields,
                        pageSize=self.page_size,
                        pageToken=page_token,
                        includeItemsFromAllDrives=self.include_shared_drives,
                        supportsAllDrives=self.include_shared_drives,
                        corpora="allDrives" if self.include_shared_drives else "user",
                    )
                )
                resp = req.execute()
                files = resp.get("files", [])
                page_token = resp.get("nextPageToken")
                yield files, page_token
                if not page_token:
                    break
            except HttpError as e:
                status = getattr(e, "status_code", None) or getattr(e, "resp", None)
                self._log(f"HttpError: {e}. Retentando em 2s…")
                time.sleep(2)
            except Exception as e:
                self._log(f"Erro inesperado ao listar arquivos: {e}")
                raise

    # ---------- FASE 1: CARREGAR TODAS AS PASTAS ----------
    def carregar_pastas(self) -> Dict[str, Tuple[str, Optional[str], Optional[str]]]:
        """Retorna dict: id_pasta -> (nome, parent_id, driveId)."""
        self._log("Fase 1/2: Carregando pastas…")
        q = "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if self.folder_id:
            q += f" and '{self.folder_id}' in parents"
        pastas: Dict[str, Tuple[str, Optional[str], Optional[str]]] = {}
        total = 0
        for files, nxt in self._list_files_paged(q, DEFAULT_FIELDS_FOLDERS):
            for f in files:
                if f.get("trashed"):
                    continue
                pid = f.get("id")
                pname = f.get("name")
                parents = f.get("parents") or []
                parent = parents[0] if parents else None
                driveId = f.get("driveId")
                pastas[pid] = (pname, parent, driveId)
                total += 1
            self._log(f"  Pastas carregadas: {total} (page_token={'…' if nxt else 'fim'})")
        self._log(f"✔ Pastas totais: {total}")
        return pastas

    # ---------- PATH BUILD ----------
    def _resolver_path(self, file_parents: List[str], pastas: Dict[str, Tuple[str, Optional[str], Optional[str]]], drives_map: Dict[str, str]) -> str:
        # Constrói caminho a partir do primeiro parent (se existir)
        if not file_parents:
            return "/"
        cur = file_parents[0]
        partes = []
        drive_name: Optional[str] = None
        visited = set()
        while cur and cur not in visited:
            visited.add(cur)
            info = pastas.get(cur)
            if not info:
                # pode ser raiz do drive; interrompe
                break
            name, parent, driveId = info
            partes.append(name)
            if driveId and not drive_name:
                drive_name = drives_map.get(driveId)
            cur = parent
        partes.reverse()
        prefix = f"/{drive_name}" if drive_name else ""
        return prefix + "/" + "/".join(partes) if partes else prefix or "/"

    def _map_drives(self) -> Dict[str, str]:
        """Retorna dict driveId -> driveName (para Drives Compartilhados)."""
        if not self.include_shared_drives:
            return {}
        svc = self._service_build()
        out: Dict[str, str] = {}
        page_token = None
        while True:
            try:
                resp = svc.drives().list(pageSize=100, pageToken=page_token).execute()
                for d in resp.get("drives", []):
                    out[d.get("id")] = d.get("name")
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
            except HttpError:
                time.sleep(1)
        return out

    # ---------- FASE 2: CARREGAR ARQUIVOS ----------
    def carregar_arquivos(self, pastas: Dict[str, Tuple[str, Optional[str], Optional[str]]]) -> Iterator[IndexItem]:
        self._log("Fase 2/2: Carregando arquivos…")
        q = "mimeType != 'application/vnd.google-apps.folder' and trashed = false"
        if self.folder_id:
            q += f" and '{self.folder_id}' in parents"
        drives_map = self._map_drives()
        for files, nxt in self._list_files_paged(q, DEFAULT_FIELDS_FILES):
            for f in files:
                try:
                    it = IndexItem.from_api(f)
                    it.path = self._resolver_path(it.parents, pastas, drives_map)
                    yield it
                except Exception as e:
                    self._log(f"  ! Falha ao processar item {f.get('id')}: {e}")
            self._log(f"  Página processada (page_token={'…' if nxt else 'fim'})")

    # ---------- INDEXAÇÃO COMPLETA ----------
    def indexar(self) -> List[IndexItem]:
        t0 = time.time()
        pastas = self.carregar_pastas()
        itens: List[IndexItem] = []
        cont = 0
        for it in self.carregar_arquivos(pastas):
            itens.append(it)
            cont += 1
            if cont % 500 == 0:
                dt = time.time() - t0
                rate = cont / dt if dt else 0.0
                self._log(f"  Arquivos: {cont} | {rate:.1f} it/s | elapsed {dt:.0f}s")
        dt = time.time() - t0
        rate = cont / dt if dt else 0.0
        self._log(f"✔ Concluído. {cont} arquivos em {dt:.1f}s ({rate:.1f} it/s)")
        return itens

# ---------- Persistência ----------

def salvar_indice(
    itens: List[IndexItem],
    saida_csv: str,
    saida_parquet: Optional[str] = None,
    logger: Optional[callable] = None,
) -> None:
    log = logger or (lambda m: None)
    log(f"Salvando índice em CSV: {saida_csv}")
    os.makedirs(os.path.dirname(os.path.abspath(saida_csv)) or ".", exist_ok=True)
    # Monta linhas planas
    rows = []
    for it in itens:
        rows.append({
            "id": it.id,
            "driveId": it.driveId,
            "path": it.path,
            "name": it.name,
            "ext": it.ext,
            "mimeType": it.mimeType,
            "size": it.size,
            "md5": it.md5,
            "createdTime": it.createdTime,
            "modifiedTime": it.modifiedTime,
            "trashed": it.trashed,
            "owner_name": it.owner_name,
            "owner_email": it.owner_email,
            "webViewLink": it.webViewLink,
        })
    # CSV
    import csv
    with open(saida_csv, "w", newline="", encoding="utf-8") as fp:
        if rows:
            w = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        else:
            fp.write("")
    log("✔ CSV salvo.")

    # Parquet (opcional)
    if saida_parquet and pd is not None:
        log(f"Salvando índice em Parquet: {saida_parquet}")
        df = pd.DataFrame(rows)
        os.makedirs(os.path.dirname(os.path.abspath(saida_parquet)) or ".", exist_ok=True)
        try:
            df.to_parquet(saida_parquet, index=False)
            log("✔ Parquet salvo.")
        except Exception as e:
            log(f"! Falha ao salvar Parquet: {e}")

# ---------- GUI de Progresso ----------

class ProgressWindow:
    def __init__(self, root: tk.Tk, title: str = "Indexador do Google Drive") -> None:
        self.root = root
        self.title = title
        if _HAS_TTKB and isinstance(root, tb.Window):
            root.title(self.title)
        else:
            root.title(self.title)
        root.geometry("880x560")

        # Estilos
        self.style = ttk.Style(root)
        self.style.theme_use("clam")

        # Cabeçalho
        frm_top = ttk.Frame(root)
        frm_top.pack(fill="x", padx=10, pady=(10, 6))

        self.lbl_stage = ttk.Label(frm_top, text="Pronto.")
        self.lbl_stage.pack(side="left")

        # Barras de progresso
        frm_prog = ttk.Frame(root)
        frm_prog.pack(fill="x", padx=10, pady=6)

        self.pb_stage = ttk.Progressbar(frm_prog, orient="horizontal", mode="determinate")
        self.pb_stage.pack(fill="x", pady=4)
        self.pb_stage["maximum"] = 2
        self.pb_stage["value"] = 0

        self.pb_page = ttk.Progressbar(frm_prog, orient="horizontal", mode="indeterminate")
        self.pb_page.pack(fill="x", pady=4)

        # Estatísticas
        frm_stats = ttk.Frame(root)
        frm_stats.pack(fill="x", padx=10, pady=6)
        self.var_stats = tk.StringVar(value="Arquivos: 0 | Páginas: 0 | Velocidade: 0 it/s | Elapsed: 0s | ETA: —")
        lbl_stats = ttk.Label(frm_stats, textvariable=self.var_stats)
        lbl_stats.pack(side="left")

        # Log
        frm_log = ttk.Frame(root)
        frm_log.pack(fill="both", expand=True, padx=10, pady=(6, 10))
        self.txt = scrolledtext.ScrolledText(frm_log, height=20)
        self.txt.pack(fill="both", expand=True)
        self.txt.configure(font=("Consolas", 10))

        # Rodapé (ações)
        frm_actions = ttk.Frame(root)
        frm_actions.pack(fill="x", padx=10, pady=(0, 10))

        self.btn_run = ttk.Button(frm_actions, text="Iniciar indexação", command=self.on_run)
        self.btn_run.pack(side="left")
        self.btn_save = ttk.Button(frm_actions, text="Salvar em…", command=self.on_choose_output)
        self.btn_save.pack(side="left", padx=8)

        # Saída padrão
        self.output_csv = os.path.join("data", "index_drive.csv")
        self.output_parquet = os.path.join("data", "index_drive.parquet")

        # Estado
        self._thread: Optional[threading.Thread] = None
        self._q: "queue.Queue[str]" = queue.Queue()
        self._start_time = None
        self._files_count = 0
        self._pages_count = 0

        self.root.after(200, self._drain_log)

    def log(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self._q.put(f"[{ts}] {msg}\n")

    def _drain_log(self):
        try:
            while True:
                line = self._q.get_nowait()
                self.txt.insert("end", line)
                self.txt.see("end")
        except queue.Empty:
            pass
        self.root.after(200, self._drain_log)

    def on_choose_output(self):
        path = filedialog.asksaveasfilename(
            title="Salvar índice CSV",
            defaultextension=".csv",
            initialfile=os.path.basename(self.output_csv),
            filetypes=[("CSV", "*.csv")],
        )
        if path:
            self.output_csv = path
            base, _ = os.path.splitext(path)
            self.output_parquet = base + ".parquet"
            self.log(f"Saída definida: CSV={self.output_csv} | Parquet={self.output_parquet}")

    def on_run(self):
        if self._thread and self._thread.is_alive():
            messagebox.showinfo("Indexação", "Já está em execução.")
            return
        self._files_count = 0
        self._pages_count = 0
        self._start_time = time.time()
        self.pb_stage["value"] = 0
        self.lbl_stage.configure(text="Iniciando…")
        self.pb_page.start(50)
        self.txt.delete("1.0", "end")
        self._thread = threading.Thread(target=self._run_index, daemon=True)
        self._thread.start()

    def _run_index(self):
        self.log("Preparando indexação…")
        indexer = DriveIndexer(logger=self.log)
        try:
            # FASE 1 — PASTAS
            self.lbl_stage.configure(text="Fase 1/2: Carregando pastas…")
            pastas = indexer.carregar_pastas()
            self.pb_stage["value"] = 1
            self.log(f"Pastas mapeadas: {len(pastas)}")

            # FASE 2 — ARQUIVOS
            self.lbl_stage.configure(text="Fase 2/2: Carregando arquivos…")
            itens: List[IndexItem] = []
            last_update = time.time()
            for files, nxt in indexer._list_files_paged(
                query=("mimeType != 'application/vnd.google-apps.folder' and trashed = false"),
                fields=DEFAULT_FIELDS_FILES,
            ):
                self._pages_count += 1
                for f in files:
                    try:
                        it = IndexItem.from_api(f)
                        it.path = indexer._resolver_path(it.parents, pastas, indexer._map_drives())
                        itens.append(it)
                        self._files_count += 1
                    except Exception as e:
                        self.log(f"! Erro item {f.get('id')}: {e}")
                now = time.time()
                if now - last_update > 0.5:
                    # Atualiza estatísticas
                    elapsed = now - (self._start_time or now)
                    rate = (self._files_count / elapsed) if elapsed else 0.0
                    self.var_stats.set(
                        f"Arquivos: {self._files_count} | Páginas: {self._pages_count} | "
                        f"Velocidade: {rate:.1f} it/s | Elapsed: {elapsed:.0f}s | ETA: —"
                    )
                    last_update = now
                self.log(f"Página #{self._pages_count} processada (page_token={'…' if nxt else 'fim'})")
            self.pb_page.stop()
            self.pb_stage["value"] = 2
            self.lbl_stage.configure(text="Salvando índice…")

            salvar_indice(itens, self.output_csv, self.output_parquet, logger=self.log)
            elapsed = time.time() - (self._start_time or time.time())
            rate = (self._files_count / elapsed) if elapsed else 0.0
            self.var_stats.set(
                f"Arquivos: {self._files_count} | Páginas: {self._pages_count} | "
                f"Velocidade: {rate:.1f} it/s | Elapsed: {elapsed:.0f}s | ETA: —"
            )
            self.lbl_stage.configure(text="Concluído.")
            self.log("✔ Indexação finalizada.")
        except Exception as e:
            self.pb_page.stop()
            self.lbl_stage.configure(text="Falha.")
            self.log(f"✖ Erro fatal: {e}")
            messagebox.showerror("Erro", str(e))

# ---------- CLI ----------

def _main(argv: List[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Indexador do Google Drive com progresso detalhado")
    p.add_argument("--credentials", default="credentials.json")
    p.add_argument("--token", default="token.json")
    p.add_argument("--folder-id", default=None, help="Opcional: id de uma pasta raiz para limitar o escopo")
    p.add_argument("--saida", default=os.path.join("data", "index_drive.csv"))
    p.add_argument("--parquet", default=None, help="Caminho .parquet (se omitido, salva ao lado do CSV)")
    p.add_argument("--no-gui", action="store_true", help="Executa sem janela gráfica")
    args = p.parse_args(argv)

    if args.no_gui:
        # Modo headless com logs no console
        print("[Indexador] Iniciando (sem GUI)…")
        idx = DriveIndexer(
            credentials_path=args.credentials,
            token_path=args.token,
            folder_id=args.folder_id,
            logger=lambda m: print(m, flush=True),
        )
        itens = idx.indexar()
        parquet_path = args.parquet or os.path.splitext(args.saida)[0] + ".parquet"
        salvar_indice(itens, args.saida, parquet_path, logger=lambda m: print(m, flush=True))
        print("[Indexador] Concluído.")
        return 0

    # GUI
    if _HAS_TTKB:
        app = tb.Window(themename="flatly")
    else:
        app = tk.Tk()
    gui = ProgressWindow(app, title="Indexador do Google Drive")
    app.mainloop()
    return 0

if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
