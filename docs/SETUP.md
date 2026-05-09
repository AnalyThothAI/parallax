# Setup

> **Scope.** Owns install, dev-loop, and deployment commands for both the Python service and the `web/` frontend. Runtime invariants live in `RELIABILITY.md`.

## Python service

```bash
uv sync
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

Bring up the service:

```bash
uv run gmgn-twitter-intel init      # create ~/.gmgn-twitter-intel/config.yaml
uv run gmgn-twitter-intel serve     # run collector + API in one ASGI worker
uv run gmgn-twitter-intel db migrate
```

The full CLI surface is documented by `uv run gmgn-twitter-intel --help`. Treat that output as the source of truth — do not enumerate commands here. A snapshot lives at `generated/cli-help.md`.

## Docker Compose

```bash
docker compose up -d --build app
docker compose ps
docker compose logs -f --tail=100 app
docker compose down
```

Bind-mounts host `~/.gmgn-twitter-intel/` into the container; PostgreSQL data is pinned to the `gmgn-twitter-intel-postgres` named volume.

## Frontend (`web/`)

```bash
cd web
npm install
npm run dev          # vite dev server with API proxy
npm run build        # production bundle
npm run preview      # serve the build locally
```

See `FRONTEND.md` for architecture and component conventions.
