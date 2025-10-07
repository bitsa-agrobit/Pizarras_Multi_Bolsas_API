# backend/main.py
# API de pizarras (FastAPI) usando requests + BeautifulSoup, cache simple en memoria.
# Endpoints:
#   - GET /api/health
#   - GET /api/cotizaciones?plaza=rosario|bahia|cordoba|quequen|darsena|locales&only_base=1
# Compatibles con Docker (puerto 8000/8001 según compose). Sin nuevas dependencias.

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional, Tuple
import requests
import re
import time
import unicodedata
from bs4 import BeautifulSoup

APP_TITLE = "Pizarras Granos API"
SOURCE_URL = "https://www.bolsadecereales.com/camara-arbitral"

app = FastAPI(title=APP_TITLE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Utilidades
# ---------------------------

def _strip_accents(s: str) -> str:
    if not isinstance(s, str):
        return s
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def normalize_plaza(p: str) -> Tuple[str, str]:
    """
    Devuelve (plaza_normalizada, etiqueta_titulo) tal como aparece en el HTML:
    "Rosario", "Bahía Blanca", "Córdoba", "Quequén", "Dársena".
    """
    p_in = (p or "").strip().lower()
    p_na = _strip_accents(p_in)

    # Rosario
    if p_in in ("rosario", "ros", "ros-spot"):
        return "rosario", "Rosario"

    # Bahía Blanca
    if p_na in ("bahia", "bahia blanca", "bbca", "bb", "bahia-blanca", "bahia_blanca"):
        return "bahia", "Bahía Blanca"

    # Córdoba
    if p_na in ("cordoba", "cba", "cor", "cb"):
        return "cordoba", "Córdoba"

    # Quequén
    if p_na in ("quequen", "qqn", "que"):
        return "quequen", "Quequén"

    # Dársena
    if p_na in ("darsena", "dar"):
        return "darsena", "Dársena"

    # Locales (sin bloque estable en fuente)
    if p_na in ("locales", "local", "loc", "mercado local", "mercadolocal"):
        return "locales", "Locales"

    # Default conservador
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
    """
    Limpia símbolos y espacios raros. Soporta:
      "$ 275.730", "u$s 275.730", "ARS 275.730", "275.730,00", "275,730.00"
    """
    s = (val or "").strip()
    s_low = s.lower()
    if s_low in ("s/c", "sc", "s / c", "-", ""):
        return None

    # Normalizar espacios (NBSP/thin-space)
    s = s.replace("\xa0", " ").replace("\u2009", " ").replace("\u202f", " ")
    s = re.sub(r"\s+", " ", s)

    # Eliminar todo lo que no sea dígito, coma, punto o signo
    s = re.sub(r"[^0-9,.\-]", "", s)

    # Si tiene coma y punto, asumir formato ES: "1.234,56" -> "1234.56"
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        # Solo coma => decimal ES
        if "," in s:
            s = s.replace(",", ".")
        # Solo punto => decimal EN (dejar)
        # Sin separadores => dejar

    try:
        return float(s)
    except ValueError:
        return None


def _looks_like_future(name: str) -> bool:
    if not name:
        return False
    # Meses + formatos comunes (ENE, FEB, 11/2025, ROS, MATBA, etc.)
    return bool(re.search(r"\b(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)\b", name, re.I) or
                re.search(r"\b\d{2}/\d{4}\b", name) or
                re.search(r"(ROS|BAHIA|CHICAGO|MATBA|CBOT)", name, re.I))


# Cache en memoria: { cache_key: (ts_seg, data_list) }
_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_CACHE_TTL = 120.0  # segundos

def _cache_get(key: str) -> Optional[List[Dict[str, Any]]]:
    pack = _CACHE.get(key)
    if not pack:
        return None
    ts, data = pack
    if time.time() - ts < _CACHE_TTL:
        return data
    return None

def _cache_set(key: str, data: List[Dict[str, Any]]) -> None:
    _CACHE[key] = (time.time(), data)


# ---------------------------
# Parsing de la página
# ---------------------------

def _find_plaza_tables(soup: BeautifulSoup, titulo_text: str) -> List[BeautifulSoup]:
    """
    Busca el <div class="titulo-tabla">titulo_text</div> y devuelve las
    <table class="tabla-cotizaciones"> hasta el próximo título.
    """
    titles = soup.select("div.titulo-tabla")
    start_idx = -1
    for idx, t in enumerate(titles):
        ttxt = (t.get_text() or "").strip()
        if _strip_accents(ttxt).lower() == _strip_accents(titulo_text).lower():
            start_idx = idx
            break

    if start_idx == -1:
        return []

    start_node = titles[start_idx]
    end_node = titles[start_idx + 1] if start_idx + 1 < len(titles) else None

    tables: List[BeautifulSoup] = []
    for sib in start_node.find_all_next():
        if end_node and sib == end_node:
            break
        if sib.name == "table" and "tabla-cotizaciones" in (sib.get("class") or []):
            tables.append(sib)

    # Fallback defensivo
    if not tables:
        candidates = start_node.find_all_next("table", class_="tabla-cotizaciones")
        if end_node:
            limited = []
            for tbl in candidates:
                if tbl.find_previous("div", class_="titulo-tabla") == start_node:
                    limited.append(tbl)
                else:
                    break
            tables = limited
        else:
            tables = candidates

    return tables


def _detect_currency(table_tag: BeautifulSoup, default_currency: str) -> str:
    """
    Detecta ARS/USD por encabezado (thead o primer tr). Fallback a default_currency.
    """
    header_text = ""
    thead = table_tag.find("thead")
    if thead:
        header_text = thead.get_text(" ", strip=True)
    else:
        first_tr = table_tag.find("tr")
        if first_tr:
            header_text = first_tr.get_text(" ", strip=True)

    h = _strip_accents((header_text or "").lower())
    if "dolares" in h or "dólares" in h:
        return "USD"
    if "pesos" in h:
        return "ARS"
    return default_currency


def _td_text(td) -> str:
    txt = td.get_text(" ", strip=True)
    txt = re.sub(r"\s+", " ", txt or "")
    return txt.strip()


def _header_map(table_tag: BeautifulSoup) -> Dict[str, int]:
    """
    Intenta mapear las columnas por nombre para identificar 'Actual'.
    Retorna dict como {'producto': idx, 'actual': idx, 'anterior': idx, 'var': idx}
    Si no encuentra encabezados claros, retorna {} y se usará fallback.
    """
    # Buscar th en thead o primera fila
    heads = []
    thead = table_tag.find("thead")
    if thead:
        tr = thead.find("tr")
        if tr:
            heads = tr.find_all(["th", "td"])
    else:
        first_tr = table_tag.find("tr")
        if first_tr:
            heads = first_tr.find_all(["th", "td"])

    if not heads:
        return {}

    names = [ _strip_accents(_td_text(h)).lower() for h in heads ]
    m: Dict[str, int] = {}
    for i, n in enumerate(names):
        if "producto" in n or "mercaderia" in n:
            m["producto"] = i
        if "actual" in n or "precio" in n:
            m["actual"] = i
        if "anterior" in n:
            m["anterior"] = i
        if re.search(r"\bvar(iaz|iaci|iación|iacion)?\b", n):
            m["var"] = i
    return m


def _parse_table(table_tag: BeautifulSoup, forced_currency: Optional[str], order_idx: int) -> List[Dict[str, Any]]:
    """
    Parsea una tabla de cotizaciones: detecta moneda, ubica columna 'Actual' por encabezado
    y/o usa fallback buscando la primera celda numérica utilizable.
    """
    currency = forced_currency or _detect_currency(table_tag, default_currency=("ARS" if order_idx == 0 else "USD"))
    rows = table_tag.find_all("tr")
    items: List[Dict[str, Any]] = []

    # Determinar si la primera fila es encabezado
    header = _header_map(table_tag)
    header_cols = set(header.values()) if header else set()

    for r_idx, tr in enumerate(rows):
        classes = " ".join(tr.get("class", [])).lower()
        if "head" in classes or "encabezado" in classes:
            continue

        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        # Si hay encabezado detectado y esta fila coincide con él, saltear
        if header and r_idx == 0 and len(header_cols) > 0:
            # si el primer TR era encabezado y no thead, lo saltamos
            continue

        # Producto (por header si existe, sino tds[0])
        prod_idx = header.get("producto", 0) if header else 0
        producto = _td_text(tds[prod_idx]) if prod_idx < len(tds) else _td_text(tds[0])

        pna = _strip_accents(producto).lower()
        if not producto or pna in ("producto", "pesos/tn", "dolares/tn", "dólares/tn"):
            continue

        # Valor "Actual": por header si existe
        precio = None
        if header and "actual" in header and header["actual"] < len(tds):
            precio_txt = _td_text(tds[header["actual"]])
            precio = _clean_num(precio_txt)

        # Fallback: buscar primera celda numérica en las siguientes 3-4 columnas
        if precio is None:
            for i in range(1, min(5, len(tds))):
                if i == prod_idx:
                    continue
                txt = _td_text(tds[i])
                num = _clean_num(txt)
                if num is not None or txt.lower() in ("s/c", "s / c", "-", ""):
                    precio = _clean_num(txt)
                    break

        items.append({
            "producto": producto.strip(),
            "precio": precio,
            "moneda": currency,
            "anterior": "s/c",
            "variacion": "s/c",
        })

    # Normalización de nombres
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


def scrape_plaza(plaza_norm: str) -> List[Dict[str, Any]]:
    # "Locales" hoy no tiene bloque estable en la fuente pública.
    if plaza_norm == "locales":
        return []

    html = fetch_html(SOURCE_URL)
    soup = BeautifulSoup(html, "html.parser")

    label_map = {
        "rosario": "Rosario",
        "bahia": "Bahía Blanca",
        "cordoba": "Córdoba",
        "quequen": "Quequén",
        "darsena": "Dársena",
    }
    titulo_text = label_map.get(plaza_norm, "Rosario")

    tables = _find_plaza_tables(soup, titulo_text)
    if not tables:
        return []

    items: List[Dict[str, Any]] = []
    for idx, tbl in enumerate(tables):
        currency = _detect_currency(tbl, default_currency=("ARS" if idx == 0 else "USD"))
        items += _parse_table(tbl, forced_currency=currency, order_idx=idx)

    return items


# ---------------------------
# Endpoints
# ---------------------------

@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "service": APP_TITLE, "ts": time.time()}


@app.get("/api/cotizaciones")
def cotizaciones(
    plaza: str = Query("rosario"),
    only_base: int = Query(1),
) -> Dict[str, Any]:
    """
    Respuesta:
      { items: [{producto, precio, moneda, ...}], plaza: <norm>, source_url, cached? }
    Nota: aplicamos filtro de 'base' si only_base=1 (conservador; no rompe compatibilidad).
    """
    plaza_norm, _ = normalize_plaza(plaza)
    cache_key = f"{plaza_norm}|ob={int(only_base==1)}"

    cached = _cache_get(cache_key)
    if cached is not None:
        return {"items": cached, "plaza": plaza_norm, "source_url": SOURCE_URL, "cached": True}

    try:
        items = scrape_plaza(plaza_norm)

        # Filtrado conservador: si only_base=1 ocultamos entradas que parezcan futuros/entregas
        if int(only_base) == 1:
            items = [it for it in items if not _looks_like_future(it.get("producto", ""))]

        _cache_set(cache_key, items)
        return {"items": items, "plaza": plaza_norm, "source_url": SOURCE_URL, "cached": False}
    except requests.Timeout:
        return {"items": [], "plaza": plaza_norm, "source_url": SOURCE_URL, "error": "timeout"}
    except Exception as ex:
        return {"items": [], "plaza": plaza_norm, "source_url": SOURCE_URL, "error": f"{type(ex).__name__}: {ex}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)