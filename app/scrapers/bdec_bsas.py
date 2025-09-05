from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import pandas as pd, re
from pathlib import Path
from ..config import DATA_DIR, SAVE_DEBUG_HTML

URL = "https://www.bolsadecereales.com/comercializacion"
PRODUCTOS = ["Soja","Maíz","Trigo","Girasol","Cebada","Sorgo"]

def _out_dir(fecha_iso): 
    d = Path(DATA_DIR)/"out"/fecha_iso; d.mkdir(parents=True, exist_ok=True); return d

def _to_num(t): 
    t = (t or "").replace("$","").replace("US$","").replace(".","").replace(",",".").strip()
    try: return float(t)
    except: return None

def scrape(fecha_iso: str) -> pd.DataFrame:
    out = _out_dir(fecha_iso)
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(viewport={"width":1440,"height":900})
        page.goto(URL, wait_until="networkidle", timeout=60000)
        for txt in ("Aceptar","Acepto","No, gracias","OK"):
            try: page.get_by_text(txt, exact=False).first.click(timeout=1200)
            except: pass
        html = page.content()
        if SAVE_DEBUG_HTML:
            (out/"bdec_raw.html").write_text(html, encoding="utf-8")
            (out/"bdec.png").write_bytes(page.screenshot(full_page=True))
        b.close()

    soup = BeautifulSoup(html,"lxml")
    fecha_ui = datetime.strptime(fecha_iso,"%Y-%m-%d").strftime("%d/%m/%Y")
    rows = []

    # Tablas/Series con “Precio Cámara”, “Pizarra”, etc.
    for table in soup.select("table"):
        for tr in table.select("tbody tr, tr"):
            tds=[td.get_text(" ",strip=True) for td in tr.select("td,th")]
            if len(tds)<2: continue
            texto=" ".join(tds)
            prod = next((p for p in PRODUCTOS if re.search(rf"\b{p}\b", texto, re.I)), None)
            if not prod: continue
            m = re.search(r"(\$|US\$)?\s*([\d\.]+,\d+|\d+)", texto)
            if not m: continue
            precio = _to_num(m.group(0))
            if precio is None: continue
            rows.append({"fecha":fecha_ui,"producto":prod,"precio":precio,"fuente":"BdeC – Comercialización"})

    return pd.DataFrame(rows)