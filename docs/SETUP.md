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
uv run gmgn-twitter-intel init      # create config.yaml + workers.yaml
uv run gmgn-twitter-intel serve     # run collector + API in one ASGI worker
uv run gmgn-twitter-intel db migrate
```

`init` writes `~/.gmgn-twitter-intel/config.yaml` for application and
provider settings, plus `~/.gmgn-twitter-intel/workers.yaml` for worker
runtime knobs. Existing deployments from before the worker-runtime hard
cut must create `workers.yaml` before starting the service; rerun
`uv run gmgn-twitter-intel init --force` only when you intentionally
want to rewrite the default config files.

Use `uv run gmgn-twitter-intel config` to inspect both config paths and
the effective worker settings. Use
`uv run gmgn-twitter-intel ops worker-status` to inspect the canonical
worker status map and queue depths without starting the upstream
collector.

The full CLI surface is documented by `uv run gmgn-twitter-intel --help`.
Treat that output as the source of truth — do not enumerate commands
here. A snapshot lives at `generated/cli-help.md`.

## Docker Compose

```bash
export GITHUB_TOKEN="$(gh auth token)"  # required when GitHub dependencies are private
docker compose up -d --build app
docker compose ps
docker compose logs -f --tail=100 app
docker compose down
```

Bind-mounts host `~/.gmgn-twitter-intel/` into the container, including
both `config.yaml` and `workers.yaml`; PostgreSQL data is pinned to the
`gmgn-twitter-intel-postgres` named volume.

## Frontend (`web/`)

```bash
cd web
npm install
npm run dev          # vite dev server with API proxy
npm run build        # production bundle
npm run preview      # serve the build locally
```

See `FRONTEND.md` for architecture and component conventions.
