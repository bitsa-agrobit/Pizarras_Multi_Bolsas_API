from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import csv
from datetime import datetime
import pandas as pd

from .config import DATA_DIR
from .scrapers import run_selected

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Habilitar CORS para el front en Vite (5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path("data/out")

def _latest_csv() -> Path | None:
    # 1) Prioriza la carpeta del día (YYYY-MM-DD) si existe
    today = datetime.today().strftime("%Y-%m-%d")
    p_today = DATA_DIR / today / "pizarra_normalizada.csv"
    if p_today.exists():
        return p_today

    # 2) Si no hay del día, toma el archivo más reciente que encuentre
    candidates = list(DATA_DIR.glob("*/pizarra_normalizada.csv"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)

@app.get("/api/cotizaciones")
def api_cotizaciones():
    """
    Devuelve un JSON con la tabla normalizada:
    [{fecha, producto, precio, fuente}, ...]
    """
    csv_path = _latest_csv()
    if not csv_path:
        return JSONResponse({"items": [], "message": "No hay CSV normalizado"}, status_code=200)

    items = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # normalizar tipos
            try:
                precio = float(str(row.get("precio", "0")).replace(".", "").replace(",", "."))
            except Exception:
                precio = None
            items.append({
                "fecha": row.get("fecha"),
                "producto": row.get("producto"),
                "precio": precio,
                "fuente": row.get("fuente"),
            })
    return {"items": items, "source": str(csv_path)}

@app.post("/api/scrape")
def api_scrape():
    """
    Opción mínima: reusar tu flujo existente que genera el CSV (playwright/bs4).
    Si ya tenés una función utilitaria, llamala acá.
    """
    # TODO: Importar y ejecutar tu rutina existente:
    # from app.scrapers import run_selected
    # run_selected(fecha_iso=..., sources=[...])
    return {"ok": True, "message": "Scraping lanzado (stub)."}

@app.get("/api/csv")
def api_csv():
    """
    Devuelve el CSV más reciente (para 'Descargar CSV' en el front).
    """
    csv_path = _latest_csv()
    if not csv_path:
        return JSONResponse({"message": "No hay CSV para descargar"}, status_code=404)
    return FileResponse(csv_path, media_type="text/csv", filename=csv_path.name)

@app.post("/api/export/oracle")
def api_export_oracle():
    """
    Dejá este stub y lo conectamos a tu inserción en Oracle.
    """
    # TODO: Llamar tu módulo de export a Oracle
    return {"ok": True, "message": "Export a Oracle (stub)"}

#Hasta aquí llega la parte del cíodigo nuevo para que tome las cotizaciones desde la API

#Parte del código anterior
@app.get("/health")
def health():
    return {"ok": True}

@app.get("/ui/autofill", response_class=HTMLResponse)
def autofill_form(request: Request):
    ctx = {"request": request, "errors": [], "fecha": datetime.today().strftime("%d/%m/%Y"),
           "sources":["bcr_locales","bdec_bsas","bcp_bahia"]}
    return templates.TemplateResponse("autofill_form.html", ctx)

@app.post("/ui/autofill/submit", response_class=HTMLResponse)
def autofill_submit(
    request: Request,
    fecha: str = Form(...),
    bcr_locales: str | None = Form(None),
    bdec_bsas: str | None = Form(None),
    bcp_bahia: str | None = Form(None),
):
    messages, rows = [], []

    # normalizar fecha del form a ISO
    fecha_iso = None
    try:
        dt = datetime.strptime(fecha, "%d/%m/%Y")
        fecha_iso = dt.strftime("%Y-%m-%d")
        fecha = dt.strftime("%d/%m/%Y")
    except Exception:
        try:
            dt = datetime.strptime(fecha, "%Y-%m-%d")
            fecha_iso = dt.strftime("%Y-%m-%d")
            fecha = dt.strftime("%d/%m/%Y")
        except Exception:
            messages.append("Fecha inválida. Usá dd/mm/aaaa.")

    selected = []
    if bcr_locales: selected.append("bcr_locales")
    if bdec_bsas:   selected.append("bdec_bsas")
    if bcp_bahia:   selected.append("bcp_bahia")

    if not selected:
        messages.append("Seleccioná al menos una fuente.")

    df = pd.DataFrame()
    if fecha_iso and selected:
        df = run_selected(selected, fecha_iso=fecha_iso)

    if df is None or df.empty:
        messages.append("No se obtuvieron datos de las fuentes seleccionadas.")
    else:
        # guardar CSV “del día”
        out_dir = Path(DATA_DIR) / "out" / fecha_iso
        out_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_dir / "pizarra_multi_bolsas.csv", index=False)
        rows = df.to_dict(orient="records")

    ctx = {"request": request, "fecha": fecha, "rows": rows, "messages": messages}
    return templates.TemplateResponse("autofill_result.html", ctx)