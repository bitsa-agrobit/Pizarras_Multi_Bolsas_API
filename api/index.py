# api/index.py
import os, sys, importlib, importlib.util, traceback
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# 1) PYTHONPATH: root del repo (index.py está en /api)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 2) En cloud: nunca Oracle salvo que se habilite explícito
os.environ.setdefault("DEV_SKIP_DB", "1")
if os.getenv("DEV_SKIP_DB") == "1":
    try:
        import oracledb  # si existe, OK
    except Exception:
        class _NoOracle:
            def __getattr__(self, name):
                raise RuntimeError("Oracle client disabled in cloud (DEV_SKIP_DB=1)")
        sys.modules["oracledb"] = _NoOracle()

errors = {}
imported_from = None
app = None

def find_fastapi_app(module):
    for name in ("app", "api", "application", "fastapi_app"):
        if hasattr(module, name):
            return getattr(module, name)
    try:
        from fastapi import FastAPI as _F
        for name, obj in vars(module).items():
            if isinstance(obj, _F):
                return obj
    except Exception:
        pass
    return None

# 3) Import por módulo
for cand in ("app.main", "app.app", "backend.main", "main"):
    try:
        m = importlib.import_module(cand)
        a = find_fastapi_app(m)
        if a is not None:
            app = a
            imported_from = cand
            break
        else:
            errors[cand] = "Module imported but no FastAPI instance found"
    except Exception as e:
        errors[cand] = f"{type(e).__name__}: {e}"

# 4) Fallback: cargar por ruta de archivo (evita problemas de paquete)
if app is None:
    for rel in (("app", "main.py"), ("app", "app.py"), ("main.py",)):
        p = ROOT.joinpath(*rel)
        if p.exists():
            try:
                spec = importlib.util.spec_from_file_location("app_dynamic", str(p))
                mod = importlib.util.module_from_spec(spec)
                assert spec and spec.loader
                spec.loader.exec_module(mod)  # ejecuta el archivo
                a = find_fastapi_app(mod)
                if a is not None:
                    app = a
                    imported_from = f"file:{p.relative_to(ROOT)}"
                    break
                else:
                    errors[f"file:{p.relative_to(ROOT)}"] = "Loaded but no FastAPI instance found"
            except Exception as e:
                errors[f"file:{p.relative_to(ROOT)}"] = f"{type(e).__name__}: {e}"

# 5) Si no se pudo, exponer diagnóstico (sin crashear)
if app is None:
    app = FastAPI()

    @app.get("/__import_error__")
    def import_error():
        return JSONResponse(
            status_code=500,
            content={"error": "Could not import FastAPI app", "errors": errors},
        )

# 6) Raíz amigable (solo si no existe "/")
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
                "imported_from": imported_from,
            }
except Exception:
    pass