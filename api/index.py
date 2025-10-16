# api/index.py
# Trampolín ASGI para Vercel (Serverless Python)
# Intenta importar tu instancia FastAPI "app" desde rutas comunes.
try:
    from app.main import app        # si tu app está en app/main.py (CASO MÁS PROBABLE)
except Exception:
    try:
        from backend.main import app  # si está en backend/main.py
    except Exception:
        from main import app          # si está en main.py en la raíz
