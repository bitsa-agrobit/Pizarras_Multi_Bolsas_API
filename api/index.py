# api/index.py
import os
import sys
import importlib
from pathlib import Path

# 1) Asegurar que el root del repo esté en sys.path (index.py está en /api)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 2) En cloud, nunca DB Oracle a menos que lo habilites explícito
os.environ.setdefault("DEV_SKIP_DB", "1")

# 3) Si Oracle está deshabilitado, inyectar stub para evitar errores de import
if os.getenv("DEV_SKIP_DB", "1") == "1":
    try:
        import oracledb  # si existe, no hacemos nada
    except Exception:
        class _NoOracle:
            def __getattr__(self, name):
                raise RuntimeError("Oracle client disabled in cloud (DEV_SKIP_DB=1)")
        sys.modules["oracledb"] = _NoOracle()

_last_error = None
_imported_from = None

# 4) Intentar distintos módulos comunes
for candidate in ("app.main", "backend.main", "main"):
    try:
        module = importlib.import_module(candidate)
        app = getattr(module, "app")
        print(f"[index.py] Loaded FastAPI app from {candidate}", file=sys.stderr)
        _imported_from = candidate
        break
    except Exception as e:
        _last_error = e

# 5) Si falló el import, exponer app mínima con diagnóstico
if _imported_from is None:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    import traceback

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

# 6) Agregar un root “friendly” si tu app real no lo define
try:
    existing_paths = {getattr(r, "path", "") for r in getattr(app.router, "routes", [])}
    if "/" not in existing_paths:
        @app.get("/")
        def root():
            return {
                "name": "Pizarras Multi Bolsas API",
                "status": "ok",
                "docs": "/docs",
                "health": "/api/health",
                "oracle_health": "/api/health/oracle",
                "example": "/api/cotizaciones?plaza=Rosario&only_base=1"
            }
except Exception:
    # no bloquear el arranque por esto
    pass