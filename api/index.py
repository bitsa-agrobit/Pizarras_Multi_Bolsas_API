# api/index.py
import os
import sys
import importlib
from pathlib import Path

# 1) PYTHONPATH al root del repo (index.py está en /api)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 2) En cloud, nunca Oracle a menos que lo habilites explícito
os.environ.setdefault("DEV_SKIP_DB", "1")

# 3) Si Oracle está deshabilitado, inyectar stub para evitar errores de import
if os.getenv("DEV_SKIP_DB", "1") == "1":
    try:
        import oracledb  # si existe, no hacer nada
    except Exception:
        class _NoOracle:
            def __getattr__(self, name):
                raise RuntimeError("Oracle client disabled in cloud (DEV_SKIP_DB=1)")
        sys.modules["oracledb"] = _NoOracle()

_last_error = None
_imported_from = None

# 4) Intentar importar módulo que contenga la app
for candidate in ("app.main", "backend.main", "main"):
    try:
        module = importlib.import_module(candidate)
        _imported_from = candidate
        break
    except Exception as e:
        _last_error = e
        module = None

if module is not None:
    # 5) Obtener la instancia FastAPI: primero 'app', luego nombres comunes, luego detección por tipo
    try:
        app = getattr(module, "app")
    except AttributeError:
        for name in ("api", "application", "fastapi_app"):
            if hasattr(module, name):
                app = getattr(module, name)
                break
        else:
            # detección por tipo
            try:
                from fastapi import FastAPI
                for name, obj in vars(module).items():
                    if isinstance(obj, FastAPI):
                        app = obj
                        break
                else:
                    raise AttributeError("No FastAPI instance found (looked for app/api/application)")
            except Exception as e:
                _last_error = e
                app = None

# 6) Si aún no tenemos 'app', exponer diagnóstico sin crashear
if module is None or app is None:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    import traceback

    print("[index.py] IMPORT ERROR — could not import FastAPI app", file=sys.stderr)
    if _last_error:
        traceback.print_exc(file=sys.stderr)

    app = FastAPI()

    @app.get("/__import_error__")
    def import_error():
        detail = f"{type(_last_error).__name__}: {_last_error}" if _last_error else "unknown"
        return JSONResponse(
            status_code=500,
            content={
                "error": "Could not import FastAPI app",
                "tried": ["app.main", "backend.main", "main"],
                "detail": detail,
            },
        )
else:
    # Log de dónde cargó
    print(f"[index.py] Loaded FastAPI app from '{_imported_from}'", file=sys.stderr)

# 7) Agregar un root “friendly” si tu app no define "/"
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
                "example": "/api/cotizaciones?plaza=Rosario&only_base=1",
                "imported_from": _imported_from,
            }
except Exception:
    pass