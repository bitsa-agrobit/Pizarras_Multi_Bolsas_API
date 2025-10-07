# main.py
# API de pizarras (FastAPI) sin Playwright: requests + regex, cache simple en memoria.
# Endpoints:
#   - GET /api/health
#   - GET /api/cotizaciones?plaza=rosario|bahia|locales&only_base=1
# Sin dependencias nuevas.

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional, Tuple
import requests
import re
import time

APP_TITLE = "Pizarras Granos API"
SOURCE_URL = "https://www.bolsadecereales.com/camara-arbitral"

app = FastAPI(title=APP_TITLE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ajustá si querés restringir
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Utilidades
# ---------------------------

def normalize_plaza(p: str) -> Tuple[str, str]:
    """
    Devuelve (plaza_normalizada, etiqueta_busqueda) donde etiqueta es el texto tal como
    aparece en el HTML para localizar el bloque. IMPORTANTE: sin flags (?i) adentro.
    """
    p = (p or "").strip().lower()
    if p in ("rosario", "ros", "ros-spot"):
        return "rosario", "Rosario"
    if p in ("bahia", "bahía", "bahia blanca", "bahía blanca", "bbca", "bb"):
        # En el HTML aparece “Bahía Blanca” con tilde
        return "bahia", "Bahía Blanca"
    if p in ("loc", "local", "locales", "mercado local"):
        return "locales", "Locales"  # hoy sin bloque estable
    return "rosario", "Rosario"


def fetch_html(url: str, timeout: int = 25) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "es-AR,es;q=0.9",
        "Cache-Control": "no-cache",
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def _clean_num(val: str) -> Optional[float]:
    s = (val or "").strip().lower()
    if s in ("s/c", "sc", "s / c", "-", ""):
        return None
    s = s.replace("\xa0", " ").replace(" ", "")
    s = s.replace(".", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# Cache en memoria: { plaza_norm: (ts_seg, data_list) }
_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_CACHE_TTL = 120.0  # segundos


def _extract_table_block(html: str, titulo_text: str) -> str:
    """
    Extrae la PRIMERA tabla de cotizaciones posterior al título de la plaza.
    Usamos IGNORECASE vía flags, y NO metemos (?i) dentro del patrón.
    """
    # 1) localizar el título
    m = re.search(
        rf'<div[^>]*class="[^"]*titulo-tabla[^"]*"[^>]*>\s*{re.escape(titulo_text)}\s*</div>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return ""
    start = m.end()

    # 2) desde allí, tomar la primera tabla de cotizaciones
    mtab = re.search(
        r'<table[^>]*class="[^"]*tabla-cotizaciones[^"]*"[^>]*>(.*?)</table>',
        html[start:],
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not mtab:
        return ""
    return mtab.group(1)


def parse_items_from_block(block_html: str) -> List[Dict[str, Any]]:
    """
    Parsea filas con estructura:
      <td colspan="2">Producto</td> <td>Actual</td> <td>Anterior</td> <td>Var</td>
    Por lo tanto: product = tds[0], actual = tds[1], anterior = tds[2], var = tds[3]
    """
    items: List[Dict[str, Any]] = []

    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", block_html, flags=re.IGNORECASE | re.DOTALL):
        # Ignorar encabezados
        if re.search(r'class="[^"]*(head|encabezado)[^"]*"', row, flags=re.IGNORECASE):
            continue

        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.IGNORECASE | re.DOTALL)
        if len(tds) < 2:
            continue

        def _strip_html(x: str) -> str:
            x = re.sub(r"<[^>]+>", "", x)
            return x.strip()

        producto = _strip_html(tds[0])
        if not producto or producto.lower() in ("producto", "pesos/tn", "dólares/tn", "dolares/tn"):
            continue

        # “Actual” debería ser tds[1]; si viene vacío y hay más celdas, probamos la siguiente.
        actual = _strip_html(tds[1]) if len(tds) >= 2 else ""
        if (actual == "" or _clean_num(actual) is None) and len(tds) >= 3:
            actual = _strip_html(tds[2])

        precio = _clean_num(actual)

        items.append({
            "producto": producto,
            "precio": precio,
            "moneda": "ARS",        # bloque de Pesos/TN
            "anterior": "s/c",      # opcional (no lo usamos en el front)
            "variacion": "s/c",
        })

    return items


def scrape_plaza(plaza_norm: str) -> List[Dict[str, Any]]:
    if plaza_norm == "locales":
        return []  # hoy sin fuente clara

    html = fetch_html(SOURCE_URL)
    titulo_text = "Rosario" if plaza_norm == "rosario" else "Bahía Blanca"
    block = _extract_table_block(html, titulo_text)
    if not block:
        return []

    items = parse_items_from_block(block)

    # normalización simple de nombres
    rename = {
        "trigo": "Trigo",
        "maiz": "Maiz",
        "maíz": "Maiz",
        "soja": "Soja",
        "sorgo": "Sorgo",
        "girasol": "Girasol",
        "trigo art 12": "Trigo Art 12",
    }
    norm_items: List[Dict[str, Any]] = []
    for it in items:
        key = rename.get(it["producto"].strip().lower(), it["producto"].strip())
        norm_items.append({**it, "producto": key})
    return norm_items


def get_cached(plaza_norm: str) -> Optional[List[Dict[str, Any]]]:
    pack = _CACHE.get(plaza_norm)
    if not pack:
        return None
    ts, data = pack
    if time.time() - ts < _CACHE_TTL:
        return data
    return None


def set_cached(plaza_norm: str, data: List[Dict[str, Any]]) -> None:
    _CACHE[plaza_norm] = (time.time(), data)


# ---------------------------
# Endpoints
# ---------------------------

@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "service": APP_TITLE, "ts": time.time()}


@app.get("/api/cotizaciones")
def cotizaciones(
    plaza: str = Query("rosario"),
    only_base: int = Query(1),  # mantenido por compatibilidad; hoy no filtra nada extra
) -> Dict[str, Any]:
    plaza_norm, _ = normalize_plaza(plaza)

    cached = get_cached(plaza_norm)
    if cached is not None:
        return {"items": cached, "plaza": plaza_norm, "source_url": SOURCE_URL, "cached": True}

    try:
        items = scrape_plaza(plaza_norm)
        set_cached(plaza_norm, items)
        return {"items": items, "plaza": plaza_norm, "source_url": SOURCE_URL, "cached": False}
    except requests.Timeout:
        return {
            "items": [],
            "plaza": plaza_norm,
            "source_url": SOURCE_URL,
            "error": "timeout",
        }
    except Exception as ex:
        return {
            "items": [],
            "plaza": plaza_norm,
            "source_url": SOURCE_URL,
            "error": f"{type(ex).__name__}: {ex}",
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)