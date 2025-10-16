# api/index.py
import os, sys
from pathlib import Path

# Asegurar que el root del repo está en el sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# En cloud, nunca Oracle a menos que se habilite explícitamente
os.environ.setdefault("DEV_SKIP_DB", "1")

# Importar tu FastAPI real desde app/main.py
from app.main import app

# (opcional) endpoint raíz amigable si no existe "/"
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
    pass