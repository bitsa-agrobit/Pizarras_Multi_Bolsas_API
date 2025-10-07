import os
import re
import time
import json
from datetime import datetime, timezone, date
from typing import Dict, List, Optional, Tuple

import oracledb
import httpx
from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from bs4 import BeautifulSoup

# --- Cache en memoria por plaza (último scrape OK) ---
CACHE = {
    "rosario": {"items": [], "fetched_at": None},
    "bahia":   {"items": [], "fetched_at": None},
    "locales": {"items": [], "fetched_at": None},
}

# Tiempo máximo (min) que consideramos “vigente” el cache si falla el scrape
CACHE_MAX_AGE_MIN = 1440  # 24hs

# --------------------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------------------

SOURCE_URL = "https://www.bolsadecereales.com/camara-arbitral"

PLAZA_CODES = {
    "rosario": "ROS",
    "bahia": "BAH",
    "locales": "LOC",
}

# Orden y lista “base” (para only_base=1)
PRODUCT_ORDER = ["Trigo", "Maiz", "Soja", "Girasol", "Sorgo", "Cebada Forrajera"]
PRODUCTS_BASE = set(["Trigo", "Maiz", "Soja", "Girasol", "Sorgo"])

# Mapeo a códigos internos (según tu ERP)
GRAIN_CODE = {
    "Trigo": 10,
    "Maiz": 200,
    "Soja": 210,
    "Sorgo": 220,
    "Girasol": 230,
    # "Cebada Forrajera": 240,  # si más adelante lo querés usar
}

# Estado "start" simple en memoria (para no romper el botón del front)
START_CONFIG: Dict[str, object] = {
    "enabled": False,
    "plaza": None,
    "interval_min": None,
    "url": SOURCE_URL,
    "started_at_utc": None,
}

app = FastAPI()

# Si usás el proxy de Vite, CORS no es estrictamente necesario,
# pero lo dejo abierto por si querés exponer la API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------------------
# Utilitarios
# --------------------------------------------------------------------------------------

def parse_price(text: str) -> Optional[float]:
    """
    Convierte precios estilo ES (p.ej. '480.000,00', '0,00', 's/c') a float.
    Devuelve None si es 's/c' o vacío.
    """
    if not text:
        return None
    s = text.strip().lower()
    if "s/c" in s or s == "-" or s == "sc":
        return None
    # Mantener sólo dígitos, puntos y comas
    s = re.sub(r"[^0-9\.,\-]", "", s)
    if not s:
        return None
    # Quitar separadores de miles (.)
    s = s.replace(".", "")
    # Cambiar coma por punto para decimales
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def find_block_label_for_table(table_tag) -> str:
    """
    Busca el rótulo del bloque (Rosario / Bahía / Mercado Local) buscando headings previos.
    Si no encuentra, devuelve 'rosario' por defecto.
    """
    heading = table_tag.find_previous(["h2", "h3", "h4", "strong", "span"])
    if heading and heading.get_text(strip=True):
        t = heading.get_text(" ", strip=True).lower()
        if "rosario" in t:
            return "rosario"
        if "bahía" in t or "bahia" in t:
            return "bahia"
        if "mercado local" in t or "local" in t or "locales" in t:
            return "locales"
    return "rosario"


def detect_currency_from_table(table_tag) -> str:
    """
    Detecta moneda (ARS/USD) mirando el encabezado del bloque o la tabla.
    """
    # Mirar celdas de encabezado
    head = table_tag.find("tr", class_="head")
    if head:
        txt = head.get_text(" ", strip=True).lower()
        if "dólares" in txt or "dolares" in txt:
            return "USD"
        if "pesos" in txt:
            return "ARS"
    # Encabezados alternativos
    txt_table = table_tag.get_text(" ", strip=True).lower()
    if "dólares" in txt_table or "dolares" in txt_table:
        return "USD"
    if "pesos" in txt_table:
        return "ARS"
    # Por defecto, ARS
    return "ARS"


def normalize_product_name(name: str) -> str:
    """
    Limpia y normaliza nombres: 'Maiz' / 'Maíz' => 'Maiz', etc.
    """
    if not name:
        return ""
    n = name.strip()
    # Normalización mínima
    n = n.replace("Maíz", "Maiz")
    n = re.sub(r"\s+", " ", n)
    return n


def clarion_date(dt: date) -> int:
    """
    Clarion date = días desde 1800-12-28.
    """
    base = date(1800, 12, 28)
    return (dt - base).days


def mes_ejercicio(dt: date) -> Tuple[str, int]:
    """
    Devuelve ('OCT25', 2025) según fecha.
    """
    abbr = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"][dt.month - 1]
    yy = f"{dt.year % 100:02d}"
    return f"{abbr}{yy}", dt.year


def read_site_html(url: str) -> str:
    """
    Descarga el HTML del sitio con httpx, con reintentos y backoff.
    Forzamos HTTP/1.1 (http2=False) para evitar dependencia de 'h2'.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }

    attempts = 3
    backoff = 1.6  # exponencial: 1.6^n

    last_err = None
    for i in range(attempts):
        try:
            timeout = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=5.0)
            with httpx.Client(http2=False, timeout=timeout, follow_redirects=True, headers=headers) as client:
                r = client.get(url)
                r.raise_for_status()
                return r.text
        except Exception as e:
            last_err = e
            if i < attempts - 1:
                time.sleep(backoff ** i)
    raise last_err


def scrape_items(url: str) -> Dict[str, List[Dict[str, object]]]:
    """
    Parsea todas las tablas de la página y devuelve items agrupados por plaza.
    Estructura:
    {
      "rosario": [{producto, precio, moneda, anterior, variacion}, ...],
      "bahia": [...]
      "locales": [...]
    }
    """
    html = read_site_html(url)
    soup = BeautifulSoup(html, "html.parser")

    all_by_plaza: Dict[str, List[Dict[str, object]]] = {"rosario": [], "bahia": [], "locales": []}

    tables = soup.find_all("table")
    for tbl in tables:
        # Algunas tablas no son cotizaciones
        if "tabla-cotizaciones" not in (tbl.get("class") or []):
            # Si el sitio cambia clases, lo consideramos por columnas (Producto/Actual/Anterior/Var)
            header_text = tbl.get_text(" ", strip=True).lower()
            if "producto" not in header_text or "anterior" not in header_text:
                continue

        plaza = find_block_label_for_table(tbl)  # rosario/bahia/locales
        moneda = detect_currency_from_table(tbl)  # ARS/USD

        # filas de datos
        for tr in tbl.find_all("tr"):
            # saltar encabezados
            tr_cls = (tr.get("class") or [])
            if "head" in tr_cls or "encabezado" in tr_cls:
                continue

            tds = tr.find_all("td")
            if len(tds) < 3:
                continue

            # patrón de columna: [producto, (a veces col-spans), actual, anterior, var]
            # Buscamos el primer td no vacío como producto
            prod_td = None
            for td in tds:
                txt = td.get_text(" ", strip=True)
                if txt:
                    prod_td = td
                    break
            if prod_td is None:
                continue

            producto = normalize_product_name(prod_td.get_text(" ", strip=True))

            # Heurística: las últimas 3 celdas suelen ser Actual, Anterior, Var
            txts = [td.get_text(" ", strip=True) for td in tds]
            # Intentar tomar las 3 últimas no vacías como actual, anterior, var
            last = [t for t in txts if t != ""]
            if len(last) >= 3:
                actual, anterior, variacion = last[-3], last[-2], last[-1]
            else:
                # fallback: algunas filas con 3/4 celdas exactas
                if len(tds) >= 5:
                    actual = tds[-3].get_text(" ", strip=True)
                    anterior = tds[-2].get_text(" ", strip=True)
                    variacion = tds[-1].get_text(" ", strip=True)
                else:
                    # si no hay columnas completas, salteamos
                    continue

            precio = parse_price(actual)
            anterior_txt = anterior or "s/c"
            variacion_txt = variacion or "s/c"

            # Excluir filas vacías o rótulos
            if not producto or producto.lower() in ("producto", "productos", "pesos/tn", "dólares/tn", "dolares/tn"):
                continue

            all_by_plaza[plaza].append({
                "producto": producto,
                "precio": precio,
                "moneda": moneda,
                "anterior": anterior_txt,
                "variacion": variacion_txt,
            })

    return all_by_plaza


def dedupe_and_sort(items: List[Dict[str, object]], only_base: bool = False) -> List[Dict[str, object]]:
    """
    - Deduplica por (producto, moneda) prefiriendo precio no nulo.
    - Filtra por base si solo querés productos base.
    - Ordena por PRODUCT_ORDER, y luego USD después de ARS para el mismo producto.
    """
    if only_base:
        items = [it for it in items if normalize_product_name(it["producto"]) in PRODUCTS_BASE]

    keep: Dict[Tuple[str, str], Dict[str, object]] = {}
    for it in items:
        key = (normalize_product_name(it["producto"]), it.get("moneda") or "")
        prev = keep.get(key)
        if prev is None:
            keep[key] = it
        else:
            # si el nuevo tiene precio y el anterior no, quedate con el nuevo
            if prev.get("precio") is None and it.get("precio") is not None:
                keep[key] = it

    def sort_key(it):
        prod = normalize_product_name(it["producto"])
        try:
            idx = PRODUCT_ORDER.index(prod)
        except ValueError:
            idx = 999
        # ARS primero, USD después
        mon = it.get("moneda")
        mon_rank = 0 if mon == "ARS" else 1
        return (idx, mon_rank, prod)

    out = sorted(keep.values(), key=sort_key)
    # Remover NaN/Inf si algo raro se coló
    clean = []
    for it in out:
        p = it.get("precio")
        if isinstance(p, float):
            if not (p == p) or p == float("inf") or p == float("-inf"):
                it = dict(it)
                it["precio"] = None
        clean.append(it)
    return clean


# --------------------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/cotizaciones")
def api_cotizaciones(
    plaza: str = Query("rosario"),
    only_base: int = Query(0, description="1 = solo productos base"),
    debug: int = Query(0),
    max_age_min: int = Query(CACHE_MAX_AGE_MIN, description="edad máxima del cache para usar fallback"),
):
    plaza = plaza.lower().strip()
    if plaza not in PLAZA_CODES:
        plaza = "rosario"

    dbg = {}
    try:
        t0 = time.time()
        all_by_plaza = scrape_items(SOURCE_URL)
        items = dedupe_and_sort(all_by_plaza.get(plaza, []), only_base=bool(only_base))
        # actualizar cache
        CACHE[plaza] = {"items": items, "fetched_at": datetime.now(timezone.utc).isoformat()}

        payload = {
            "items": items,
            "plaza": plaza,
            "source_url": SOURCE_URL,
        }
        if debug:
            dbg["scrape_ms"] = int((time.time() - t0) * 1000)
            dbg["counts"] = {k: len(v) for k, v in all_by_plaza.items()}
            payload["debug"] = dbg
        return JSONResponse(payload)

    except Exception as e:
        # fallback: usar cache si disponible y no muy viejo
        cached = CACHE.get(plaza) or {}
        items = cached.get("items") or []
        fetched_at = cached.get("fetched_at")

        use_cache = False
        if items and fetched_at:
            try:
                ts = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            except Exception:
                ts = None
            if ts:
                age_min = (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
                if age_min <= max_age_min:
                    use_cache = True
                    dbg["cache_age_min"] = round(age_min, 1)

        if use_cache:
            payload = {
                "items": items,
                "plaza": plaza,
                "source_url": SOURCE_URL,
                "cached": True,
                "error": f"{type(e).__name__}: {e}",
            }
            if debug:
                payload["debug"] = dbg
            return JSONResponse(payload, status_code=200)

        # sin cache útil → error “vacío”
        return JSONResponse(
            {"items": [], "plaza": plaza, "source_url": SOURCE_URL, "error": f"{type(e).__name__}: {e}"},
            status_code=200,
        )


@app.get("/api/csv")
def api_csv(
    plaza: str = Query("rosario"),
    only_base: int = Query(0),
    fallback_cache: int = Query(0, description="1 = si falla scrape, usa cache"),
):
    plaza = plaza.lower().strip()
    if plaza not in PLAZA_CODES:
        plaza = "rosario"
    try:
        all_by_plaza = scrape_items(SOURCE_URL)
        items = dedupe_and_sort(all_by_plaza.get(plaza, []), only_base=bool(only_base))
        # actualizar cache (opcional)
        CACHE[plaza] = {"items": items, "fetched_at": datetime.now(timezone.utc).isoformat()}

    except Exception as e:
        if fallback_cache:
            cached = CACHE.get(plaza) or {}
            items = cached.get("items") or []
        else:
            items = []

    # CSV en memoria
    rows = ["producto,precio,moneda,anterior,variacion"]
    for it in items:
        producto = it["producto"].replace(",", " ")
        precio = "" if it["precio"] is None else f"{it['precio']:.2f}"
        moneda = it.get("moneda") or ""
        anterior = (it.get("anterior") or "").replace(",", ".")
        variacion = (it.get("variacion") or "").replace(",", ".")
        rows.append(f"{producto},{precio},{moneda},{anterior},{variacion}")

    csv_text = "\n".join(rows)
    filename = f"cotizaciones_{plaza}.csv"
    headers = {
        "Content-Type": "text/csv",
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    return PlainTextResponse(csv_text, headers=headers)


@app.get("/api/health/oracle")
def api_health_oracle():
    try:
        _ = os.environ.get("ORACLE_CLIENT_LIB_DIR")
        # Intentar init en thick; si ya se inicializó, oracledb lanza excepción: la ignoramos.
        try:
            if _:
                oracledb.init_oracle_client(lib_dir=_)
            else:
                oracledb.init_oracle_client()  # buscará en rutas conocidas
        except Exception:
            pass

        dsn = os.environ.get("ORACLE_DSN")
        user = os.environ.get("ORACLE_USER")
        pwd = os.environ.get("ORACLE_PASSWORD") or os.environ.get("ORACLE_PASS")

        assert dsn and user and pwd, "Faltan ORACLE_DSN / ORACLE_USER / ORACLE_PASSWORD"

        with oracledb.connect(user=user, password=pwd, dsn=dsn, encoding="UTF-8") as con:
            cur = con.cursor()
            cur.execute("select 1 from dual")
            val = cur.fetchone()[0]
        return {"ok": True, "mode": "thick", "ping": int(val)}
    except Exception as e:
        return {"ok": False, "oracle_disabled": True, "reason": f"{type(e).__name__}: {e}"}


def build_oracle_rows(plaza: str, only_base: bool) -> List[Dict[str, object]]:
    """
    Convierte cotizaciones (filtradas/deduplicadas) a filas Oracle TB_REF.
    Regla: preferimos ARS; si un producto base no tiene ARS, y sólo hay USD, lo incluimos tal cual.
    """
    all_by_plaza = scrape_items(SOURCE_URL)
    raw = dedupe_and_sort(all_by_plaza.get(plaza, []), only_base=only_base)

    # Preferencia ARS sobre USD: agrupamos por producto
    by_prod: Dict[str, Dict[str, object]] = {}
    for it in raw:
        prod = normalize_product_name(it["producto"])
        if prod not in PRODUCTS_BASE:
            continue
        cur = it.get("moneda")
        if prod not in by_prod:
            by_prod[prod] = it
        else:
            # si ya hay una y la nueva es ARS, reemplazo
            if cur == "ARS":
                by_prod[prod] = it

    today = datetime.now().date()
    fv = clarion_date(today)
    mes, ejercicio = mes_ejercicio(today)
    pizarra = PLAZA_CODES.get(plaza, "ROS")

    # Generar filas
    seq_base = int(time.time() * 1000)  # secuencia simple
    rows = []
    idx = 0
    for prod in PRODUCT_ORDER:
        if prod not in by_prod:
            continue
        it = by_prod[prod]
        precio = it.get("precio")
        if precio is None:
            continue
        grano = GRAIN_CODE.get(prod)
        if not grano:
            continue

        rows.append({
            "GRANO": grano,
            "SIGLO": 0,
            "COSECHA": "0000",
            "PIZARRA": pizarra,
            "FECHAVIG": fv,
            "MES": mes,
            "EJERCICIO": ejercicio,
            "PRECIOREF": float(precio),
            "UVALUE": seq_base + idx,
        })
        idx += 1

    return rows


@app.get("/api/export/oracle/preview")
def api_export_preview(plaza: str = Query("rosario"), only_base: int = Query(1)):
    plaza = plaza.lower().strip()
    if plaza not in PLAZA_CODES:
        plaza = "rosario"
    try:
        rows = build_oracle_rows(plaza, only_base=bool(only_base))
        return {"plaza": plaza, "count": len(rows), "rows": rows}
    except Exception as e:
        return JSONResponse({"plaza": plaza, "count": 0, "error": f"{type(e).__name__}: {e}"}, status_code=200)


@app.post("/api/export/oracle")
def api_export_oracle(
    plaza: str = Query("rosario"),
    only_base: int = Query(1),
    overwrite: int = Query(0),
):
    plaza = plaza.lower().strip()
    if plaza not in PLAZA_CODES:
        plaza = "rosario"
    try:
        rows = build_oracle_rows(plaza, only_base=bool(only_base))
        if not rows:
            return {"ok": False, "exported": 0, "plaza": plaza, "reason": "No hay filas exportables"}

        dsn = os.environ.get("ORACLE_DSN")
        user = os.environ.get("ORACLE_USER")
        pwd = os.environ.get("ORACLE_PASSWORD") or os.environ.get("ORACLE_PASS")
        if not (dsn and user and pwd):
            return {"ok": False, "exported": 0, "plaza": plaza, "oracle_disabled": True, "reason": "Credenciales Oracle no configuradas"}

        # Init thick (si aplica)
        try:
            libdir = os.environ.get("ORACLE_CLIENT_LIB_DIR")
            if libdir:
                oracledb.init_oracle_client(lib_dir=libdir)
        except Exception:
            pass

        with oracledb.connect(user=user, password=pwd, dsn=dsn, encoding="UTF-8") as con:
            cur = con.cursor()

            if overwrite:
                # Borrar por llave “del día” y pizarra
                pizarra = rows[0]["PIZARRA"]
                fechavig = rows[0]["FECHAVIG"]
                mes = rows[0]["MES"]
                ejercicio = rows[0]["EJERCICIO"]
                cur.execute(
                    """
                    DELETE FROM TEST_EMAN.TB_REF
                     WHERE PIZARRA = :p
                       AND FECHAVIG = :fv
                       AND MES = :m
                       AND EJERCICIO = :e
                    """,
                    p=pizarra, fv=fechavig, m=mes, e=ejercicio
                )

            # Insert batch
            data = [
                (
                    r["GRANO"], r["SIGLO"], r["COSECHA"], r["PIZARRA"],
                    r["FECHAVIG"], r["MES"], r["EJERCICIO"], r["PRECIOREF"], r["UVALUE"]
                )
                for r in rows
            ]
            cur.executemany(
                """
                INSERT INTO TEST_EMAN.TB_REF
                (GRANO, SIGLO, COSECHA, PIZARRA, FECHAVIG, MES, EJERCICIO, PRECIOREF, UVALUE)
                VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9)
                """,
                data
            )
            con.commit()
        return {"ok": True, "exported": len(rows), "plaza": plaza}
    except oracledb.Error as dbex:
        return {"ok": False, "exported": 0, "plaza": plaza, "error": str(dbex)}
    except Exception as e:
        return {"ok": False, "exported": 0, "plaza": plaza, "error": f"{type(e).__name__}: {e}"}


# ---------------------- Automatización liviana (para no romper el botón) ----------------------

@app.post("/api/start")
def api_start(plaza: str = Query("rosario"), interval_min: int = Query(1440)):
    plaza = plaza.lower().strip()
    if plaza not in PLAZA_CODES:
        plaza = "rosario"
    START_CONFIG.update({
        "enabled": True,
        "plaza": plaza,
        "interval_min": interval_min,
        "url": SOURCE_URL,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True, "message": "Automatización iniciada", "config": START_CONFIG}


@app.get("/api/start/config")
def api_start_config():
    if not START_CONFIG.get("enabled"):
        return {"enabled": False, "message": "Sin configuración cargada"}
    return START_CONFIG

@app.get("/api/cache/status")
def api_cache_status():
    # No exponemos los items para no inflar la respuesta; solo metadatos
    return {
        plaza: {
            "count": len(CACHE[plaza]["items"] or []),
            "fetched_at": CACHE[plaza]["fetched_at"],
        }
        for plaza in CACHE.keys()
    }