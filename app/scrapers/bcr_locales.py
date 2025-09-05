from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import pandas as pd, re, os
from pathlib import Path
from ..config import DATA_DIR, SAVE_DEBUG_HTML

URL = "https://www.bcr.com.ar/es/mercados/mercado-de-granos/cotizaciones/cotizaciones-locales-0"

PRODUCTOS = ["Soja", "Maíz", "Trigo", "Girasol", "Sorgo"]

def _out_dir(fecha_iso:str) -> Path:
    d = Path(DATA_DIR) / "out" / fecha_iso; d.mkdir(parents=True, exist_ok=True); return d

def _to_num(t: str) -> float | None:
    if not t: return None
    t = t.replace("$","").replace("US$","").replace("ARS","").replace(".","").replace(",",".").strip()
    try: return float(t)
    except: return None

def scrape(fecha_iso: str) -> pd.DataFrame:
    out = _out_dir(fecha_iso)

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        page = b.new_page(viewport={"width":1440,"height":900})
        page.goto(URL, wait_until="networkidle", timeout=60000)
        # cookies
        for txt in ("Aceptar", "Acepto", "No, gracias", "OK"):
            try: page.get_by_text(txt, exact=False).first.click(timeout=1200)
            except: pass
        html = page.content()
        if SAVE_DEBUG_HTML:
            (out/"bcr_locales_raw.html").write_text(html,encoding="utf-8")
            (out/"bcr_locales.png").write_bytes(page.screenshot(full_page=True))
        b.close()

    soup = BeautifulSoup(html, "lxml")
    rows = []
    fecha_ui = datetime.strptime(fecha_iso, "%Y-%m-%d").strftime("%d/%m/%Y")

    # buscar bloques con “Cotizaciones” o tablas con productos
    # 1) tablas
    for table in soup.select("table"):
        for tr in table.select("tbody tr, tr"):
            tds = [td.get_text(" ",strip=True) for td in tr.select("td,th")]
            if len(tds) < 2: continue
            texto = " ".join(tds)
            prod = next((p for p in PRODUCTOS if re.search(rf"\b{p}\b", texto, re.I)), None)
            if not prod: continue
            # buscar número
            m = re.search(r"(\$|US\$)?\s*([\d\.]+,\d{1,2}|\d+)", texto)
            if not m: continue
            precio = _to_num(m.group(0))
            if precio is None: continue
            rows.append({"fecha":fecha_ui,"producto":prod,"precio":precio,"fuente":"BCR – Locales"})

    # 2) fallback: textos sueltos
    if not rows:
        block = soup.find(string=re.compile("Cotizaciones", re.I))
        block = block.find_parent(["section","div"]) if block else soup
        text = block.get_text(" ",strip=True)
        for prod in PRODUCTOS:
            m = re.search(rf"{prod}.*?(\$|US\$)?\s*([\d\.]+,\d+|\d+)", text, re.I)
            if not m: continue
            precio = _to_num(m.group(0)); 
            if precio is None: continue
            rows.append({"fecha":fecha_ui,"producto":prod,"precio":precio,"fuente":"BCR – Locales"})

    return pd.DataFrame(rows)