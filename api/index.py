# api/index.py
import os, sys, importlib
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DEV_SKIP_DB", "1")
if os.getenv("DEV_SKIP_DB") == "1":
    try:
        import oracledb
    except Exception:
        class _NoOracle:
            def __getattr__(self, name):
                raise RuntimeError("Oracle client disabled in cloud (DEV_SKIP_DB=1)")
        sys.modules["oracledb"] = _NoOracle()

tried = ("app.main", "app.app", "backend.main", "main")
_last_error = None
_imported_from = None
module = None

for cand in tried:
    try:
        module = importlib.import_module(cand)
        _imported_from = cand
        break
    except Exception as e:
        _last_error = e

def _find_fastapi_app(m):
    for name in ("app", "api", "application", "fastapi_app"):
        if hasattr(m, name):
            return getattr(m, name)
    from fastapi import FastAPI
    for name, obj in vars(m).items():
        if isinstance(obj, FastAPI):
            return obj
    return None

app = _find_fastapi_app(module) if module else None

if app is None:
    app = FastAPI()
    @app.get("/__import_error__")
    def import_error():
        return JSONResponse(
            status_code=500,
            content={
                "error": "Could not import FastAPI app",
                "tried": list(tried),
                "detail": f"{type(_last_error).__name__}: {_last_error}" if _last_error else "unknown",
            },
        )

try:
    existing = {getattr(r, "path", "") for r in getattr(app.router, "routes", [])}
    if "/" not in existing:
        @app.get("/")
        def root():
            return {
                "name": "Pizarras Multi Bolsas API",
                "status": "ok",
                "docs": "/docs",
                "health": "/api/health",
                "oracle_health": "/api/health/oracle",
                "example": "/api/cotizaciones?plaza=Rosario&only_base=1",
                "imported_from": _imported_from,
            }
except Exception:
    pass