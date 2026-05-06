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

RUN python -m pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY src ./src
COPY --from=web-builder /app/web/dist ./src/gmgn_twitter_intel/web/dist

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8765

CMD ["gmgn-twitter-intel", "serve"]
