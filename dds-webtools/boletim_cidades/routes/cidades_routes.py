# D:\programas\DDS\dds-webtools\boletim_cidades\routes\cidades_routes.py
from __future__ import annotations
import os
import json
import re
import io
import tempfile
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from google.cloud import firestore

# --- paths ---
_MODULE_DIR = Path(__file__).resolve().parent.parent
_DATA_DIR = _MODULE_DIR / "data"
_ISS_CSV = _DATA_DIR / "iss.csv"
_ISS_OVERRIDES = _DATA_DIR / "iss_overrides.json"
_PARQUET = _DATA_DIR / "_dados.parquet"

# --- templates (Jinja2) ---
templates = Jinja2Templates(directory=str(_MODULE_DIR / "templates"))

router = APIRouter()


# =====================================================================
# Helpers
# =====================================================================
def _get_firestore_db():
    try:
        return firestore.Client()
    except Exception:
        return None


def _load_overrides_local() -> dict:
    try:
        if _ISS_OVERRIDES.exists():
            with open(_ISS_OVERRIDES, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return {}


def _save_overrides_local(overrides: dict):
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(_ISS_OVERRIDES, "w", encoding="utf-8") as f:
            json.dump(overrides, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


_overrides_cache = None
_overrides_cache_time = 0.0


def _load_overrides() -> dict:
    global _overrides_cache, _overrides_cache_time
    import time
    now = time.time()
    
    # 30-second cache check
    if _overrides_cache is not None and (now - _overrides_cache_time) < 30.0:
        return _overrides_cache

    # 1. Load local cache as default fallback
    local_data = _load_overrides_local()
    
    # 2. Try Firestore
    try:
        db = _get_firestore_db()
        if db:
            doc_ref = db.collection("boletim_cidades").document("iss_overrides")
            doc = doc_ref.get()
            if doc.exists:
                db_data = doc.to_dict() or {}
                if db_data:
                    # Sync local cache
                    _save_overrides_local(db_data)
                    _overrides_cache = db_data
                    _overrides_cache_time = now
                    return db_data
    except Exception as e:
        print(f"Error loading overrides from Firestore: {e}")
        
    _overrides_cache = local_data
    _overrides_cache_time = now
    return local_data


def _save_overrides(overrides: dict):
    global _overrides_cache, _overrides_cache_time
    import time
    _overrides_cache = overrides
    _overrides_cache_time = time.time()

    # 1. Save to local cache
    _save_overrides_local(overrides)
    
    # 2. Save to Firestore
    try:
        db = _get_firestore_db()
        if db:
            doc_ref = db.collection("boletim_cidades").document("iss_overrides")
            doc_ref.set(overrides)
    except Exception as e:
        print(f"Error saving overrides to Firestore: {e}")


def _load_parquet() -> pd.DataFrame:
    if _PARQUET.exists():
        try:
            df = pd.read_parquet(_PARQUET)
            df["Copiado"] = df["Copiado"].astype(bool)
            return df
        except Exception:
            pass
    return pd.DataFrame()


def _save_parquet(df: pd.DataFrame):
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(_PARQUET, index=False)
    except Exception:
        pass


def _df_to_rows(df: pd.DataFrame, overrides: dict) -> list[dict]:
    """Converte DataFrame para lista de dicts serializáveis para o frontend."""
    rows = []
    for _, row in df.iterrows():
        codigo = str(row.get("CodigoMunicipio", "")).strip()
        if not codigo and isinstance(row.get("d_fiscal", ""), str):
            m = re.search(r"(\d{7})", row["d_fiscal"])
            if m:
                codigo = m.group(1)

        aliq_default = "0"
        municipio_name = str(row.get("Municipio") or "").strip()
        
        if codigo and codigo in overrides:
            val = overrides[codigo]
            if isinstance(val, dict):
                aliq_default = str(val.get("aliq", "0"))
                if val.get("municipio"):
                    municipio_name = str(val["municipio"]).strip()
            else:
                aliq_default = str(val)
        elif row.get("ALIQ_ISS") is not None and not pd.isna(row.get("ALIQ_ISS")):
            aliq_default = str(row["ALIQ_ISS"])

        val_num = float(row["Valor_num"]) if pd.notna(row.get("Valor_num")) else 0.0

        rows.append({
            "id": int(row["ID"]),
            "boletim": str(row.get("Boletim") or ""),
            "contrato": str(row.get("Contrato") or ""),
            "municipio": municipio_name,
            "pedido": str(row.get("Pedido") or ""),
            "valor": val_num,
            "copiado": bool(row.get("Copiado", False)),
            "codigo": codigo,
            "aliq": aliq_default,
        })
    return rows


# =====================================================================
# Routes
# =====================================================================

@router.get("/boletim-cidades", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """Renderiza a página principal do Boletim Cidades."""
    df = _load_parquet()
    overrides = _load_overrides()

    rows = _df_to_rows(df, overrides) if not df.empty else []
    total_files = len(df["Arquivo"].unique()) if not df.empty else 0
    total_rows = len(df) if not df.empty else 0
    copied_rows = int(df["Copiado"].sum()) if not df.empty else 0

    active_boletim = rows[0]["boletim"] if rows else ""
    active_contrato = rows[0]["contrato"] if rows else ""

    # Load universal counters from Firestore
    counters = {"nf_emitidas": 0, "boletins_processados": 0}
    try:
        db = _get_firestore_db()
        if db:
            doc = db.collection("boletim_cidades").document("universal_counters").get()
            if doc.exists:
                d = doc.to_dict() or {}
                counters["nf_emitidas"] = d.get("nf_emitidas", 0)
                counters["boletins_processados"] = d.get("boletins_processados", 0)
    except Exception:
        pass

    return templates.TemplateResponse("index_cidades.html", {
        "request": request,
        "page_title": "Boletim Cidades Financeiro",
        "rows_json": json.dumps(rows, ensure_ascii=False),
        "overrides_json": json.dumps(overrides, ensure_ascii=False),
        "total_files": total_files,
        "total_rows": total_rows,
        "copied_rows": copied_rows,
        "pending_rows": total_rows - copied_rows,
        "counters": counters,
        "active_boletim": active_boletim,
        "active_contrato": active_contrato,
    })


@router.post("/boletim-cidades/api/processar")
async def processar_pdfs(files: list[UploadFile] = File(...)):
    """Recebe PDFs, extrai dados e salva em parquet."""
    try:
        from boletim_cidades.extrator.boletim_sumarizacao import processar_lista_boletins

        # Salva arquivos temporários para o pdfplumber processar
        temp_files = []
        for f in files:
            content = await f.read()
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            tmp.write(content)
            tmp.flush()
            tmp.seek(0)
            # Cria um wrapper com atributo .name para compatibilidade
            tmp.name_display = f.filename
            temp_files.append(tmp)

        # Processa usando a função existente
        df_new = processar_lista_boletins(temp_files, iss_csv_path=_ISS_CSV)

        # Cleanup temp files
        for tmp in temp_files:
            try:
                tmp.close()
                os.unlink(tmp.name)
            except Exception:
                pass

        if df_new.empty:
            return JSONResponse({"ok": False, "message": "Nenhum dado extraído dos PDFs."})

        _save_parquet(df_new)
        overrides = _load_overrides()
        rows = _df_to_rows(df_new, overrides)

        return JSONResponse({
            "ok": True,
            "message": f"{len(files)} arquivos processados, {len(df_new)} registros extraídos.",
            "rows": rows,
            "total_files": len(df_new["Arquivo"].unique()),
            "total_rows": len(df_new),
            "copied_rows": int(df_new["Copiado"].sum()),
            "pending_rows": int((~df_new["Copiado"]).sum()),
        })
    except Exception as e:
        return JSONResponse({"ok": False, "message": f"Erro: {str(e)}"}, status_code=500)


@router.get("/boletim-cidades/api/dados")
async def get_dados():
    """Retorna os dados atuais em JSON."""
    df = _load_parquet()
    overrides = _load_overrides()
    rows = _df_to_rows(df, overrides) if not df.empty else []
    total_files = len(df["Arquivo"].unique()) if not df.empty else 0
    return JSONResponse({
        "ok": True,
        "rows": rows,
        "total_files": total_files,
        "total_rows": len(df),
        "copied_rows": int(df["Copiado"].sum()) if not df.empty else 0,
        "pending_rows": int((~df["Copiado"]).sum()) if not df.empty else 0,
    })


@router.post("/boletim-cidades/api/marcar-copiado")
async def marcar_copiado(request: Request):
    """Marca um registro como copiado e salva override de alíquota."""
    body = await request.json()
    row_id = body.get("id")
    override_codigo = body.get("override_codigo")
    override_value = body.get("override_value")

    df = _load_parquet()
    if df.empty:
        return JSONResponse({"ok": False, "message": "Sem dados."})

    df.loc[df["ID"] == row_id, "Copiado"] = True
    _save_parquet(df)

    # Salvar override se fornecido
    if override_codigo and override_value:
        overrides = _load_overrides()
        overrides[str(override_codigo)] = str(override_value)
        _save_overrides(overrides)

    return JSONResponse({"ok": True})


@router.post("/boletim-cidades/api/marcar-pendente")
async def marcar_pendente(request: Request):
    """Marca um registro como pendente."""
    body = await request.json()
    row_id = body.get("id")

    df = _load_parquet()
    if df.empty:
        return JSONResponse({"ok": False, "message": "Sem dados."})

    df.loc[df["ID"] == row_id, "Copiado"] = False
    _save_parquet(df)

    return JSONResponse({"ok": True})


@router.post("/boletim-cidades/api/overrides")
async def salvar_override(request: Request):
    """Salva uma alíquota override para um código de município."""
    body = await request.json()
    codigo = str(body.get("codigo", "")).strip()
    valor = body.get("valor")
    municipio = body.get("municipio")

    if not codigo:
        return JSONResponse({"ok": False, "message": "Código inválido."})

    overrides = _load_overrides()
    
    if valor == "delete" or valor == "" or valor is None:
        overrides.pop(codigo, None)
    else:
        if isinstance(valor, dict):
            overrides[codigo] = {
                "aliq": str(valor.get("aliq", "0")).strip(),
                "municipio": str(valor.get("municipio", "")).strip()
            }
        else:
            # Get existing or create new dict
            existing = overrides.get(codigo)
            if not isinstance(existing, dict):
                existing = {"aliq": str(valor).strip(), "municipio": ""}
            else:
                existing["aliq"] = str(valor).strip()
            
            if municipio is not None:
                existing["municipio"] = str(municipio).strip()
                
            overrides[codigo] = existing

    _save_overrides(overrides)
    return JSONResponse({"ok": True})


@router.get("/boletim-cidades/api/counters")
async def get_counters():
    """Retorna os contadores universais do Firestore."""
    try:
        db = _get_firestore_db()
        if db:
            doc_ref = db.collection("boletim_cidades").document("universal_counters")
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict() or {}
                return JSONResponse({
                    "ok": True,
                    "counters": {
                        "nf_emitidas": data.get("nf_emitidas", 0),
                        "boletins_processados": data.get("boletins_processados", 0)
                    }
                })
    except Exception:
        pass
    return JSONResponse({
        "ok": True,
        "counters": {
            "nf_emitidas": 0,
            "boletins_processados": 0
        }
    })


@router.post("/boletim-cidades/api/counters/increment")
async def increment_counter(request: Request):
    """Incrementa de forma atômica um contador no Firestore."""
    body = await request.json()
    counter = body.get("counter")
    amount = int(body.get("amount", 1))
    
    if counter not in ("nf_emitidas", "boletins_processados"):
        return JSONResponse({"ok": False, "message": "Contador inválido."})
        
    try:
        db = _get_firestore_db()
        if db:
            doc_ref = db.collection("boletim_cidades").document("universal_counters")
            # Tenta update atômico
            doc_ref.update({
                counter: firestore.Increment(amount)
            })
            updated = doc_ref.get().to_dict() or {}
            return JSONResponse({
                "ok": True,
                "counters": {
                    "nf_emitidas": updated.get("nf_emitidas", 0),
                    "boletins_processados": updated.get("boletins_processados", 0)
                }
            })
    except Exception:
        # Se falhar porque não existe, inicializa com set(merge=True)
        try:
            db = _get_firestore_db()
            if db:
                doc_ref = db.collection("boletim_cidades").document("universal_counters")
                doc_ref.set({
                    "nf_emitidas": amount if counter == "nf_emitidas" else 0,
                    "boletins_processados": amount if counter == "boletins_processados" else 0
                }, merge=True)
                updated = doc_ref.get().to_dict() or {}
                return JSONResponse({
                    "ok": True,
                    "counters": {
                        "nf_emitidas": updated.get("nf_emitidas", 0),
                        "boletins_processados": updated.get("boletins_processados", 0)
                    }
                })
        except Exception as ex:
            return JSONResponse({"ok": False, "message": str(ex)}, status_code=500)
            
    return JSONResponse({"ok": False, "message": "Firestore indisponível."})
