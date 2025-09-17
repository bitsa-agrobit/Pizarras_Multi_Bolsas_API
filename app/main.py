from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from playwright.async_api import async_playwright
import csv, io, datetime as dt
from typing import Literal

DEFAULT_URL = "https://www.bolsadecereales.com/camara-arbitral"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def _to_float_or_none(txt: str):
    if not txt or txt.lower().strip() == "s/c":
        return None
    t = txt.strip().replace(".", "").replace(",", ".")
    try:
        return float(t)
    except:
        return None

async def _scrape_items(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent="Mozilla/5.0")
        page = await ctx.new_page()
        await page.goto(url, wait_until="networkidle")

        rows = await page.locator("table.tabla-cotizaciones.half tbody tr").all()

        items = []
        current_currency = None  # "ARS" o "USD"

        for r in rows:
            tds = await r.locator("td").all_inner_texts()
            tds = [t.replace("\n", " ").strip() for t in tds]
            if not tds:
                continue

            joined = " ".join(tds).upper()
            if "PRODUCTO" in joined and ("PESOS/TN" in joined or "DÓLARES/TN" in joined or "DOLARES/TN" in joined):
                current_currency = "ARS" if "PESOS/TN" in joined else "USD"
                continue
            if "ANTERIOR" in joined and "VAR" in joined and len(tds) <= 3:
                continue
            if tds[0].upper() in ("PRODUCTO", "ANTERIOR", "VAR", "ACTUAL"):
                continue

            producto = tds[0].strip()
            actual   = tds[2].strip() if len(tds) > 2 else ""
            anterior = tds[3].strip() if len(tds) > 3 else ""
            variacion= tds[4].strip() if len(tds) > 4 else ""
            precio = _to_float_or_none(actual)

            # limpiar filas vacías/encabezados
            if not producto or producto.upper() in ("PRODUCTO","ANTERIOR","VAR","ACTUAL"):
                continue

            items.append({
                "producto": producto,
                "precio": precio,
                "moneda": current_currency or "USD",
                "anterior": anterior,
                "variacion": variacion
            })

        await browser.close()

        # dedup por (producto, moneda)
        dedup = {}
        for it in items:
            dedup[(it["producto"], it["moneda"])] = it
        return list(dedup.values())

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.get("/api/cotizaciones")
async def cotizaciones(url: str = Query(DEFAULT_URL)):
    try:
        items = await _scrape_items(url)
        return {"items": items}
    except Exception as e:
        import traceback; traceback.print_exc()
        # 200 con debug para que el front no pinte error rojo
        return JSONResponse(status_code=200, content={"items": [], "debug": f"playwright_failed: {e}"})

@app.get("/api/csv")
async def export_csv(
    url: str = Query(DEFAULT_URL),
    sc: Literal["sc", "blank", "null"] = "blank"   # cómo escribir precios sin cotización
):
    try:
        items = await _scrape_items(url)

        buf = io.StringIO(newline="")
        w = csv.writer(buf)
        w.writerow(["producto","precio","moneda","anterior","variacion","timestamp"])
        now = dt.datetime.now().isoformat(timespec="seconds")

        for it in items:
            precio = it.get("precio")
            # representación elegida para “sin cotización”
            if precio is None:
                if sc == "sc":
                    precio_out = "s/c"
                elif sc == "null":
                    precio_out = "NULL"
                else:  # "blank"
                    precio_out = ""
            else:
                precio_out = precio  # número

            w.writerow([
                it.get("producto",""),
                precio_out,
                it.get("moneda",""),
                it.get("anterior",""),
                it.get("variacion",""),
                now
            ])

        csv_text = buf.getvalue()
        buf.close()

        return Response(
            content=csv_text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="cotizaciones.csv"'}
        )
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})