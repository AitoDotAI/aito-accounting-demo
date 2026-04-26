# syntax=docker/dockerfile:1.7

# ── Stage 1: Build the Next.js static export ──────────────────────
FROM node:20-bookworm-slim AS frontend-build
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY frontend ./
ENV NODE_ENV=production
RUN npx next build

# Result: /app/frontend/out/ contains the static site


# ── Stage 2: Python runtime + serve the API ───────────────────────
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

# uv is the fast resolver/installer the project uses locally
COPY --from=ghcr.io/astral-sh/uv:0.5.18 /uv /uvx /usr/local/bin/

WORKDIR /app

# Install Python deps first for layer cache
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# App source + fixtures + precomputed predictions
COPY src ./src
COPY data ./data
# Static frontend from stage 1
COPY --from=frontend-build /app/frontend/out ./frontend/out

# Azure App Service / Container Apps inject PORT; default to 8200 for local
ENV PORT=8200 \
    PATH="/app/.venv/bin:$PATH"

EXPOSE 8200

CMD ["sh", "-c", "uvicorn src.app:app --host 0.0.0.0 --port ${PORT:-8200}"]
