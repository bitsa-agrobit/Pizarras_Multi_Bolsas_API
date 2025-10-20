#!/usr/bin/env python3
# scripts/merge_json.py
import json
import os
import glob
import datetime
from pathlib import Path

# Dónde publicar los archivos que sirve GitHub Pages:
# - Por defecto, raíz del repo (OUTPUT_DIR=".")
# - Si tu Pages usa /docs, seteá OUTPUT_DIR="docs" (desde el workflow)
OUTPUT_DIR = os.getenv("OUTPUT_DIR", ".").strip() or "."
OUT_ROOT = Path(__file__).resolve().parents[1] / OUTPUT_DIR

TODAY = datetime.date.today().strftime("%Y-%m-%d")

def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def normalize_item(plaza: str, row: dict):
    # Ajustá los campos si tus JSON individuales difieren
    return {
        "plaza": plaza,
        "producto": row.get("producto"),
        "precio": row.get("precio"),
        "moneda": row.get("moneda", "ARS"),
        "anterior": row.get("anterior", "s/c"),
        "variacion": row.get("variacion", "s/c"),
        "unidad": row.get("unidad", "tn"),
        "fecha": row.get("fecha", TODAY),
        "fuente": row.get("fuente", "bolsadecereales.com/camara-arbitral"),
        "only_base": row.get("only_base", 1),
    }

def guess_plaza_from_filename(name: str) -> str:
    n = name.lower()
    if "rosario" in n or "ros" in n:
        return "Rosario"
    if "bahia" in n or "bahía" in n or "bbca" in n:
        return "Bahía Blanca"
    if "local" in n or "loc" in n:
        return "Locales"
    if "quequen" in n:
        return "Quequén"
    if "darsena" in n or "dársena" in n:
        return "Dársena"
    return "Desconocida"

def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    # Busca JSON individuales donde normalmente los publicás
    search_roots = [OUT_ROOT]  # raíz (o docs/) que sirve Pages
    # Si también querés mirar en data/ históricos por si ya existen, se incluye:
    patterns = [
        "cotizaciones_*.json",   # raíz/docs
        "data/**/*.json"         # por si guardaste históricos con ese patrón
    ]

    candidates = []
    for pat in patterns:
        for base in search_roots:
            candidates.extend(glob.glob(str(base / pat), recursive=True))

    items = []
    plazas = set()

    for path in candidates:
        fname = os.path.basename(path)
        if not fname.startswith("cotizaciones_"):
            continue
        plaza = guess_plaza_from_filename(fname)
        try:
            data = load_json(Path(path))
        except Exception:
            # tolerante a errores
            continue

        # si el JSON tiene {"items": [...]}, usar eso; si es lista directa, usarla
        rows = data.get("items") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            continue

        for r in rows:
            items.append(normalize_item(plaza, r))
        if plaza != "Desconocida":
            plazas.add(plaza)

    payload = {
        "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Pizarras_Multi_Bolsas_API",
        "plazas": sorted(plazas),
        "items": items,
        "by_plaza": {},
    }

    # Construir by_plaza
    by = {}
    for it in items:
        by.setdefault(it["plaza"], []).append(it)
    payload["by_plaza"] = by

    # Salidas
    out_today_dir = OUT_ROOT / "data" / TODAY
    out_today_dir.mkdir(parents=True, exist_ok=True)

    with open(OUT_ROOT / "all.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(out_today_dir / "all.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[merge_json] OK -> {OUT_ROOT/'all.json'} ({len(items)} items)")
    print(f"[merge_json] OK -> {out_today_dir/'all.json'}")

if __name__ == "__main__":
    main()