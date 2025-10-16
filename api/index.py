# api/index.py
import os
import sys
from pathlib import Path

# 1) Asegurar que el root del repo esté en sys.path (index.py está en /api)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 2) En cloud, nunca DB Oracle a menos que lo habilites explícito
os.environ.setdefault("DEV_SKIP_DB", "1")

# 3) Intentar distintos paths de import
_last_error = None
for candidate in ("app.main", "backend.main", "main"):
    try:
        module = __import__(candidate, fromlist=["app"])
        app = getattr(module, "app")
        # Log rápido a stderr para ver en Vercel de dónde importó
        print(f"[index.py] Loaded FastAPI app from {candidate}", file=sys.stderr)
        break
    except Exception as e:
        _last_error = e
else:
    # 4) Fallback: no tirar 500 silencioso; devolver diagnóstico
    import traceback
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    print("[index.py] IMPORT ERROR — could not import FastAPI app", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)

    app = FastAPI()

    @app.get("/__import_error__")
    def import_error():
        return JSONResponse(
            status_code=500,
            content={
                "error": "Could not import FastAPI app",
                "tried": ["app.main", "backend.main", "main"],
                "detail": f"{type(_last_error).__name__}: {_last_error}",
            },
        )