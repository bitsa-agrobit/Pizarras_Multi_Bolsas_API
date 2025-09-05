from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
import pandas as pd

from .config import DATA_DIR
from .scrapers import run_selected

app = FastAPI()
templates = Jinja2Templates(directory="templates")

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