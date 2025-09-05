FROM python:3.11-slim

# 1) Dependencias del sistema mínimas (Playwright ya instala el resto con --with-deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2) Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 3) Instalar Chromium + dependencias vía Playwright CLI (forma soportada)
RUN python -m playwright install --with-deps chromium

# 4) Copiar tu app
COPY app ./app
COPY templates ./templates
COPY data ./data

ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
