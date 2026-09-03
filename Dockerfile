# Tek imaj: frontend derlenir, backend + calisma zamani icine konur.
# Hedef makinede yalnizca docker (veya podman) gerekir.

# ---------- 1) frontend ----------
FROM docker.io/library/node:20-alpine AS web
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 2) calisma zamani ----------
FROM docker.io/library/python:3.12-slim
# nodejs sadece stats.py icin gerekli: eventsstat sayfasindaki Nuxt IIFE'si
# guvenli bicimde ancak calistirilarak JSON'a cevrilebiliyor.
RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY --from=web /build/dist frontend/dist

# Veritabani ve lig konfigurasyonu disaridan baglanir
ENV BETODDS_DATA=/app/data \
    BETODDS_STATIC=/app/frontend/dist \
    PYTHONUNBUFFERED=1
VOLUME ["/app/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", \
     "--host", "0.0.0.0", "--port", "8000"]
