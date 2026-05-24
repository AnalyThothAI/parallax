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

For real data, edit the operator-owned files in `~/.gmgn-twitter-intel/`
instead of adding repository-local `.env` files or editing generated examples.
`config.yaml` must point at the live PostgreSQL store and contain the provider
credentials/endpoints needed by the enabled data lanes, including GMGN OpenAPI
for exact token profiles and OKX provider settings for discovery, market data,
or DEX WebSocket lanes when those workers are enabled. Keep secrets out of
terminal output, docs, tests, and commits.

Use `uv run gmgn-twitter-intel config` to inspect both config paths and
the effective worker settings. Use
`uv run gmgn-twitter-intel ops worker-status` to inspect the canonical
worker status map and queue depths without starting the upstream
collector.

Useful live-data smoke checks:

```bash
uv run gmgn-twitter-intel config
uv run gmgn-twitter-intel ops worker-status
uv run gmgn-twitter-intel ops refresh-asset-profiles --limit 5
uv run gmgn-twitter-intel ops mirror-token-images --limit 50 --source-limit 500
uv run gmgn-twitter-intel ops rebuild-token-profiles --limit 500
uv run gmgn-twitter-intel asset-flow --window 1h --scope all --limit 20
```

The first command confirms the real config paths. The profile refresh command
exercises the GMGN exact-token profile lane that feeds `asset_profiles.logo_url`
for DEX token icon source URLs. The mirror command copies eligible provider
images into `~/.gmgn-twitter-intel/cache/token-images`, and the rebuild command
projects `token_profile_current.logo_url` to local `/api/token-images/{image_id}`
paths or `NULL`. Provider blocks, rate limits, unsupported image types, and
missing mirror rows should surface as explicit diagnostic results or fallback
marks, not as fake public profile facts.

Macro live-data debugging starts the same way: first run
`uv run gmgn-twitter-intel config` and confirm `config_path` /
`workers_config_path` point at `~/.gmgn-twitter-intel/`. Report only paths,
booleans, and diagnostic command status; do not paste WebSocket tokens, API
keys, provider passwords, or full config payloads into docs or chat.

Chart-ready macro pages require history, not just a single as-of bundle:

```bash
uv run macrodata bundle history macro-core --start YYYY-MM-DD --end YYYY-MM-DD \
  | uv run gmgn-twitter-intel macro import-bundle --stdin
uv run gmgn-twitter-intel macro project-once
uv run gmgn-twitter-intel macro status
```

A good macro status has `history_ready=true`, a history coverage ratio above
the configured threshold, no required concept below minimum history for pages
claiming `ready`, and a latest snapshot using `macro_regime_v4`. FRED public
CSV timeouts or a missing optional FRED API key are source-health gaps; they
should appear as partial coverage/data gaps and are not frontend defects.

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
