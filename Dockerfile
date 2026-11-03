# FINN — single-container deploy (Next.js UI + FastAPI API).
# Works on Render, Hugging Face Spaces (Docker), Fly.io, Railway, or any Docker host.

# ---- 1. Build the Next.js frontend (standalone output) ----
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Empty base URL => browser calls same-origin /api/v1, proxied to FastAPI.
ENV NEXT_PUBLIC_API_BASE_URL="" \
    BACKEND_INTERNAL_URL="http://127.0.0.1:8000" \
    NEXT_TELEMETRY_DISABLED=1 \
    NEXT_OUTPUT=standalone
RUN npm run build

# ---- 2. Runtime: Python 3.12 + the node binary ----
FROM python:3.12-slim
COPY --from=web /usr/local/bin/node /usr/local/bin/node
WORKDIR /app

COPY backend/pyproject.toml backend/
COPY backend/app backend/app
COPY backend/alembic.ini backend/
COPY backend/seed backend/seed
RUN pip install --no-cache-dir ./backend

COPY --from=web /web/.next/standalone frontend/
COPY --from=web /web/.next/static frontend/.next/static
COPY --from=web /web/public frontend/public
COPY deploy/start.sh /app/start.sh
RUN chmod +x /app/start.sh && useradd -m -u 1000 finn && chown -R finn /app
USER finn

ENV FINN_ENV=production \
    FINN_DATABASE_URL=sqlite:////app/backend/data/finn.db \
    FINN_FRONTEND_ORIGIN=* \
    FINN_AUTO_REFRESH_HOURS=4 \
    PORT=7860
EXPOSE 7860
CMD ["/app/start.sh"]
