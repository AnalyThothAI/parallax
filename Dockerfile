# syntax=docker/dockerfile:1.7

FROM node:22-slim AS web-builder

WORKDIR /app/web

COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web ./
RUN npm run build


FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY src ./src
COPY --from=web-builder /app/web/dist ./src/gmgn_twitter_intel/web/dist

RUN --mount=type=secret,id=github_token \
    set -eu; \
    cleanup() { \
        if [ -n "${token:-}" ]; then \
            git config --global --unset-all url."https://x-access-token:${token}@github.com/".insteadOf || true; \
        fi; \
    }; \
    trap cleanup EXIT; \
    if [ -s /run/secrets/github_token ]; then \
        token="$(cat /run/secrets/github_token)"; \
        git config --global url."https://x-access-token:${token}@github.com/".insteadOf "https://github.com/"; \
    fi; \
    uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8765

CMD ["gmgn-twitter-intel", "serve"]
