import json
from pathlib import Path
from main import cotizaciones

def dump(plaza: str, only_base: int):
    data = cotizaciones(plaza, only_base)
    Path("public").mkdir(exist_ok=True, parents=True)
    fn = f"public/cotizaciones_{data['plaza']}.json"
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

for plaza in ["rosario", "bahia", "cordoba", "quequen", "darsena", "locales"]:
    dump(plaza, 1)
    dump(plaza, 0)

print("OK")
