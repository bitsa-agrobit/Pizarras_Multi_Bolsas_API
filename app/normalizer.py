# app/normalizer.py
from __future__ import annotations
import pandas as pd

# Alias de productos por fuente (extensible)
PRODUCT_ALIASES = {
    "CAC Rosario": {
        "Soja": "Soja",
        "Trigo": "Trigo",
        "Maíz": "Maíz",
        "Girasol": "Girasol",
        # agregá más si hace falta
    },
    "BolsadeCereales BA": {},
    "BCR": {},
    "BCP Bahía Blanca": {},
}

STANDARD_COLUMNS = ["fecha", "producto", "precio", "fuente"]

def _std_cols(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza columnas: fecha, producto, precio, fuente.
    Acepta variantes comunes en csv/tablas.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    rename_map = {}
    cols_lower = {c.lower(): c for c in df.columns}

    # fecha
    for cand in ["fecha", "date", "day"]:
        if cand in cols_lower:
            rename_map[cols_lower[cand]] = "fecha"
            break
    # producto
    for cand in ["producto", "product", "mercaderia", "mercadería", "commodity"]:
        if cand in cols_lower:
            rename_map[cols_lower[cand]] = "producto"
            break
    # precio
    for cand in ["precio", "price", "valor", "cotizacion", "cotización"]:
        if cand in cols_lower:
            rename_map[cols_lower[cand]] = "precio"
            break
    # fuente
    for cand in ["fuente", "source"]:
        if cand in cols_lower:
            rename_map[cols_lower[cand]] = "fuente"
            break

    df = df.rename(columns=rename_map)

    # Asegurar columnas
    for c in STANDARD_COLUMNS:
        if c not in df.columns:
            df[c] = None

    # Orden
    df = df[STANDARD_COLUMNS]
    return df

def _normalize_producto(row: pd.Series) -> str | None:
    fuente = (row.get("fuente") or "").strip()
    prod   = (row.get("producto") or "").strip()
    if not prod:
        return prod
    aliases = PRODUCT_ALIASES.get(fuente, {})
    # si no hay mapping, capitalizar básico
    return aliases.get(prod, prod.capitalize())

def _normalize_fecha(row: pd.Series) -> str | None:
    """Devuelve fecha en dd/mm/yyyy si viene en otro formato común."""
    val = row.get("fecha")
    if not val or pd.isna(val):
        return val
    s = str(val).strip()
    # yyyy-mm-dd -> dd/mm/yyyy
    if "-" in s and len(s) >= 10:
        try:
            y, m, d = s[:10].split("-")
            return f"{d.zfill(2)}/{m.zfill(2)}/{y}"
        except Exception:
            return s
    # si ya viene dd/mm/yyyy lo dejamos
    return s

def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza columnas, fecha y producto; asegura tipos y orden.
    """
    df = _std_cols(df).copy()

    if df.empty:
        return df

    # Normalizar producto y fecha
    df["producto"] = df.apply(_normalize_producto, axis=1)
    df["fecha"]    = df.apply(_normalize_fecha, axis=1)

    # Precio a float
    def to_float(x):
        if x is None or pd.isna(x): 
            return None
        s = str(x).replace(".", "").replace(" ", "").replace("$", "").replace(",", ".")
        try:
            return float(s)
        except Exception:
            return None

    df["precio"] = df["precio"].apply(to_float)

    # Orden final y drop filas totalmente vacías
    df = df[STANDARD_COLUMNS].dropna(how="all")
    return df.reset_index(drop=True)