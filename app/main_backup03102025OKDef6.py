# backend/main.py
# API de pizarras (FastAPI) usando requests + BeautifulSoup.
# Endpoints:
#   - GET  /api/health
#   - GET  /api/cotizaciones?plaza=rosario|bahia|cordoba|quequen|darsena|locales&only_base=1
#   - POST /api/start?plaza=<plaza>&interval_min=<min>        (inicia scheduler en memoria)
#   - POST /api/export/oracle?plaza=<plaza>                   (inserta TEST_EMAN.TB_REF)
#   - GET  /api/csv?plaza=<plaza>&only_base=1                 (descarga CSV)
#
# Cambios "quirúrgicos":
# - Exportación Oracle: mapeo de granos a códigos reales Oracle (10,200,210,220,230).
# - Validación previa contra <ORACLE_SCHEMA>.GRANO (si el código no existe, se omite).
# - UVALUE: hash <= 16 dígitos (evita ORA-01438).
# - Fix ORA-00933 en validación GRANO (usar ROWNUM=1).
# - Conserva normalizaciones/HTML parsing existentes.

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Dict, Any, List, Optional, Tuple
import requests
import re
import time
import unicodedata
from bs4 import BeautifulSoup
import threading
import io
import csv
import os
import hashlib

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
# Utilidades de normalización
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

    if p_in in ("rosario", "ros", "ros-spot"):
        return "rosario", "Rosario"
    if p_na in ("bahia", "bahia blanca", "bbca", "bb", "bahia-blanca", "bahia_blanca"):
        return "bahia", "Bahía Blanca"
    if p_na in ("cordoba", "cba", "cor", "cb"):
        return "cordoba", "Córdoba"
    if p_na in ("quequen", "qqn", "que"):
        return "quequen", "Quequén"
    if p_na in ("darsena", "dar"):
        return "darsena", "Dársena"
    if p_na in ("locales", "local", "loc", "mercado local", "mercadolocal"):
        return "locales", "Locales"
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
    s = s.replace("\xa0", " ").replace("\u2009", " ").replace("\u202f", " ")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^0-9,.\-]", "", s)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        if "," in s:
            s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

def _looks_like_future(name: str) -> bool:
    if not name:
        return False
    return bool(re.search(r"\b(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)\b", name, re.I) or
                re.search(r"\b\d{2}/\d{4}\b", name) or
                re.search(r"(ROS|BAHIA|CHICAGO|MATBA|CBOT)", name, re.I))

# ---------------------------
# Cache simple
# ---------------------------

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
# Parsing con BeautifulSoup
# ---------------------------

def _find_plaza_tables(soup: BeautifulSoup, titulo_text: str) -> List[BeautifulSoup]:
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

    names = [_strip_accents(_td_text(h)).lower() for h in heads]
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
    currency = forced_currency or _detect_currency(table_tag, default_currency=("ARS" if order_idx == 0 else "USD"))
    rows = table_tag.find_all("tr")
    items: List[Dict[str, Any]] = []

    header = _header_map(table_tag)
    header_cols = set(header.values()) if header else set()

    for r_idx, tr in enumerate(rows):
        classes = " ".join(tr.get("class", [])).lower()
        if "head" in classes or "encabezado" in classes:
            continue

        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        if header and r_idx == 0 and len(header_cols) > 0:
            continue

        prod_idx = header.get("producto", 0) if header else 0
        producto = _td_text(tds[prod_idx]) if prod_idx < len(tds) else _td_text(tds[0])

        pna = _strip_accents(producto).lower()
        if not producto or pna in ("producto", "pesos/tn", "dolares/tn", "dólares/tn"):
            continue

        precio = None
        if header and "actual" in header and header["actual"] < len(tds):
            precio_txt = _td_text(tds[header["actual"]])
            precio = _clean_num(precio_txt)

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
# Endpoints de datos
# ---------------------------

@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "service": APP_TITLE, "ts": time.time()}

@app.get("/api/cotizaciones")
def cotizaciones(
    plaza: str = Query("rosario"),
    only_base: int = Query(1),
) -> Dict[str, Any]:
    plaza_norm, _ = normalize_plaza(plaza)
    cache_key = f"{plaza_norm}|ob={int(only_base==1)}"

    cached = _cache_get(cache_key)
    if cached is not None:
        return {"items": cached, "plaza": plaza_norm, "source_url": SOURCE_URL, "cached": True}

    try:
        items = scrape_plaza(plaza_norm)
        if int(only_base) == 1:
            items = [it for it in items if not _looks_like_future(it.get("producto", ""))]
        _cache_set(cache_key, items)
        return {"items": items, "plaza": plaza_norm, "source_url": SOURCE_URL, "cached": False}
    except requests.Timeout:
        return {"items": [], "plaza": plaza_norm, "source_url": SOURCE_URL, "error": "timeout"}
    except Exception as ex:
        return {"items": [], "plaza": plaza_norm, "source_url": SOURCE_URL, "error": f"{type(ex).__name__}: {ex}"}

# ---------------------------
# Scheduler en memoria
# ---------------------------

_SCHEDULERS: Dict[str, threading.Timer] = {}

def _schedule_job(plaza_norm: str, interval_min: int):
    try:
        items = scrape_plaza(plaza_norm)
        _cache_set(f"{plaza_norm}|ob=1", [it for it in items if not _looks_like_future(it.get("producto",""))])
        _cache_set(f"{plaza_norm}|ob=0", items)
    except Exception:
        pass
    t = threading.Timer(interval_min * 60, _schedule_job, args=(plaza_norm, interval_min))
    _SCHEDULERS[plaza_norm] = t
    t.daemon = True
    t.start()

@app.post("/api/start")
def start_automation(
    plaza: str = Query("rosario"),
    interval_min: int = Query(1440, ge=1, le=60*24*7),
):
    plaza_norm, _ = normalize_plaza(plaza)
    t_prev = _SCHEDULERS.get(plaza_norm)
    if t_prev:
        try: t_prev.cancel()
        except Exception: pass
    _schedule_job(plaza_norm, interval_min)
    return {"ok": True, "plaza": plaza_norm, "interval_min": interval_min}

# ---------------------------
# CSV
# ---------------------------

@app.get("/api/csv")
def csv_cotizaciones(
    plaza: str = Query("rosario"),
    only_base: int = Query(1)
):
    plaza_norm, _ = normalize_plaza(plaza)
    payload = cotizaciones(plaza_norm, only_base)
    items = payload.get("items", [])
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["plaza", "producto", "moneda", "precio"])
    for it in items:
        writer.writerow([plaza_norm, it.get("producto",""), it.get("moneda",""), it.get("precio")])
    buf.seek(0)
    fn = f"cotizaciones_{plaza_norm}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'}
    )

# ---------------------------
# Exportación ORACLE (<ORACLE_SCHEMA>.TB_REF)
# ---------------------------

# Mapa de productos → códigos Oracle en GRANO
_GRAIN_MAP = {
    "Trigo": 10,
    "Trigo Art 12": 10,  # mapea al Trigo estándar
    "Maiz": 200,
    "Soja": 210,
    "Sorgo": 220,
    "Girasol": 230,
}

_PIZARRA_MAP = {"rosario":"ROS", "bahia":"BHI", "cordoba":"CBA", "quequen":"QQN", "darsena":"DAR", "locales":"LOC"}

def _oracle_connect():
    import oracledb
    client_dir = os.environ.get("ORACLE_CLIENT_LIB_DIR")
    try:
        if client_dir:
            oracledb.init_oracle_client(lib_dir=client_dir)  # thick explícito
        else:
            oracledb.init_oracle_client()  # thick si IC está en el contenedor
    except Exception:
        # fallback a thin si no hay IC
        pass
    host = os.environ.get("ORACLE_HOST")
    port = int(os.environ.get("ORACLE_PORT", "1521"))
    service = os.environ.get("ORACLE_SERVICE") or os.environ.get("ORACLE_SID")
    user = os.environ.get("ORACLE_USER")
    password = os.environ.get("ORACLE_PASSWORD")
    if not all([host, port, service, user, password]):
        raise RuntimeError("Faltan variables ORACLE_* para la conexión.")
    dsn = f"{host}:{port}/{service}"
    return oracledb.connect(user=user, password=password, dsn=dsn)

def _uvalue16(grano: int, siglo: int, cosecha: str, pizarra: str, fechavig: int,
              mes: Optional[str], ejercicio: Optional[int], precioref: float) -> int:
    """
    UVALUE <= 16 dígitos (NUMBER(16)):
    generamos hash y lo truncamos a 16 dígitos, evitando 0.
    """
    base = f"{grano}|{siglo}|{cosecha}|{pizarra}|{fechavig}|{mes or ''}|{ejercicio or ''}|{precioref:.2f}"
    h = hashlib.blake2b(base.encode("utf-8"), digest_size=8).hexdigest()  # 64 bits
    n = int(h, 16)
    n = n % (10**16)  # máximo 16 dígitos
    if n == 0:
        n = 1
    return n

def _schema() -> str:
    # Permite configurar el esquema destino; por defecto TEST_EMAN
    return os.environ.get("ORACLE_SCHEMA", "TEST_EMAN").strip()

def _grain_exists(conn, grano_code: int) -> bool:
    # FIX compatibilidad (evita ORA-00933 en versiones <12c): usar ROWNUM en lugar de FETCH FIRST
    cur = conn.cursor()
    cur.execute(f"SELECT 1 FROM {_schema()}.GRANO WHERE GRANO = :g AND ROWNUM = 1", {"g": grano_code})
    return cur.fetchone() is not None

@app.post("/api/export/oracle")
def export_oracle(
    plaza: str = Query("rosario"),
    only_base: int = Query(1)
):
    from datetime import datetime

    plaza_norm, _ = normalize_plaza(plaza)
    payload = cotizaciones(plaza_norm, only_base)
    items = payload.get("items", [])
    rows = [it for it in items if isinstance(it.get("precio"), (int, float)) and (it.get("precio") or 0) > 0]

    if not rows:
        return JSONResponse({"ok": False, "error": "sin_datos"}, status_code=400)

    # Valores fijos compatibles con definición de TB_REF
    siglo = 21                             # NUMBER(3)
    cosecha = "0"                          # VARCHAR2(5) placeholder
    pizarra = _PIZARRA_MAP.get(plaza_norm, "UNK")
    fechavig = int(datetime.now().strftime("%Y%m%d"))   # NUMBER(10)
    mes = None
    ejercicio = None

    inserted = 0
    skipped = 0
    conn = None
    try:
        conn = _oracle_connect()
        cur = conn.cursor()

        for it in rows:
            prod = it.get("producto")
            grano = _GRAIN_MAP.get(prod, 0)
            if grano == 0:
                # Producto no mapeado → se omite
                skipped += 1
                continue

            # Validar que el código exista en <SCHEMA>.GRANO
            if not _grain_exists(conn, grano):
                skipped += 1
                continue

            precioref = float(it.get("precio") or 0.0)
            precioref = round(precioref, 2)  # NUMBER(16,2)

            uvalue = _uvalue16(grano, siglo, cosecha, pizarra, fechavig, mes, ejercicio, precioref)

            # Idempotente por UVALUE (PK)
            cur.execute(f"""
                MERGE INTO {_schema()}.TB_REF t
                USING (SELECT :grano AS grano,
                              :siglo AS siglo,
                              :cosecha AS cosecha,
                              :pizarra AS pizarra,
                              :fechavig AS fechavig,
                              :mes AS mes,
                              :ejercicio AS ejercicio,
                              :precioref AS precioref,
                              :uvalue AS uvalue
                       FROM dual) s
                ON (t.UVALUE = s.uvalue)
                WHEN NOT MATCHED THEN
                  INSERT (GRANO, SIGLO, COSECHA, PIZARRA, FECHAVIG, MES, EJERCICIO, PRECIOREF, UVALUE)
                  VALUES (s.grano, s.siglo, s.cosecha, s.pizarra, s.fechavig, s.mes, s.ejercicio, s.precioref, s.uvalue)
            """, {
                "grano": grano,
                "siglo": siglo,
                "cosecha": cosecha,
                "pizarra": pizarra,
                "fechavig": fechavig,
                "mes": mes,
                "ejercicio": ejercicio,
                "precioref": precioref,
                "uvalue": uvalue,
            })
            inserted += 1

        conn.commit()
        return {"ok": True, "exported": inserted, "skipped": skipped, "plaza": plaza_norm}
    except Exception as ex:
        return JSONResponse({"ok": False, "error": f"{type(ex).__name__}: {ex}"}, status_code=500)
    finally:
        try:
            if conn: conn.close()
        except Exception:
            pass

# ---------------------------
# Main
# ---------------------------

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("APP_PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)