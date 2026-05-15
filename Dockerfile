# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim AS web-builder

WORKDIR /app/web

COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    set -eu; \
    for attempt in 1 2 3 4 5; do \
        npm ci \
            --fetch-retries=6 \
            --fetch-retry-factor=2 \
            --fetch-retry-mintimeout=10000 \
            --fetch-retry-maxtimeout=120000 \
            --fetch-timeout=300000 \
        && exit 0; \
        npm cache verify || true; \
        sleep "$((attempt * 5))"; \
    done; \
    exit 1

COPY web ./
RUN npm run build


FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN set -eu; \
    printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\n' > /etc/apt/apt.conf.d/80-retries; \
    for attempt in 1 2 3 4 5; do \
        apt-get update \
        && apt-get install -y --no-install-recommends git \
        && rm -rf /var/lib/apt/lists/* \
        && exit 0; \
        rm -rf /var/lib/apt/lists/*; \
        sleep "$((attempt * 5))"; \
    done; \
    exit 1

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
