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
uv run parallax init      # create config.yaml + workers.yaml
uv run parallax serve     # run collector + API in one ASGI worker
uv run parallax db migrate
```

`init` writes `~/.parallax/config.yaml` for application and
provider settings, plus `~/.parallax/workers.yaml` for worker
runtime knobs. Existing deployments from before the worker-runtime hard
cut must create `workers.yaml` before starting the service; rerun
`uv run parallax init --force` only when you intentionally
want to rewrite the default config files.

For real data, edit the operator-owned files in `~/.parallax/`
instead of adding repository-local `.env` files or editing generated examples.
`config.yaml` must point at the live PostgreSQL store and contain the provider
credentials/endpoints needed by the enabled data lanes, including GMGN OpenAPI
for exact token profiles and OKX provider settings for discovery, market data,
or DEX WebSocket lanes when those workers are enabled. Keep secrets out of
terminal output, docs, tests, and commits.

Use `uv run parallax config` to inspect both config paths and the effective
worker settings. Inspect the running process through authenticated
`/api/status` and `/api/ops/diagnostics`; a new CLI process cannot report the
state of an already-running scheduler.

Useful live-data smoke checks:

```bash
uv run parallax config
uv run parallax ops refresh-asset-profiles --limit 5
uv run parallax ops rebuild-token-profiles --limit 500
uv run parallax ops repair-token-profile-images --limit 500
uv run parallax ops mirror-token-images --limit 50
uv run parallax ops rebuild-token-profiles --limit 500
uv run parallax asset-flow --window 1h --scope all --limit 20
```

The first command confirms the real config paths. The profile refresh command
exercises the GMGN exact-token profile lane that feeds `asset_profiles.logo_url`
for DEX token icon source URLs. `rebuild-token-profiles` admits exact profile
and evidence logo sources into `token_image_source_dirty_targets`; the repair
command re-enqueues already-current rows whose icons were stuck before source
admission existed. The mirror command copies eligible provider images into
`~/.parallax/cache/token-images`, and the final rebuild projects
`token_profile_current.logo_url` to local `/api/token-images/{image_id}` paths
or `NULL`. Provider blocks, rate limits, unsupported image types, and missing
mirror rows should surface as explicit diagnostic results or fallback marks,
not as fake public profile facts.

Macro live-data debugging starts the same way: first run
`uv run parallax config` and confirm `config_path` /
`workers_config_path` point at `~/.parallax/`. Report only paths,
booleans, and diagnostic command status; do not paste WebSocket tokens, API
keys, provider passwords, or full config payloads into docs or chat.

Macro freshness is normally owned by the `macro_sync` worker. Docker/runtime
uses the packaged `macrodata` executable when the console script is healthy, or
the installed Python package entrypoint when the script is absent or stale. It
must not depend on `uv run macrodata` or a host-local macrodata checkout.
The worker reads the formal `workers.macro_sync.bundle_names` list; the default
set is `macro-core`, `macro-calendar-core`, `treasury-auction-core`, and
`fed-text-core`.
Provide a FRED API key either as `providers.macrodata.fred_api_key` in the
operator-owned `~/.parallax/config.yaml`, or through the environment /
deployment secret manager named by `providers.macrodata.fred_api_key_env`
(default `FINANCE_FRED_API_KEY`). `uv run parallax config` and macro sync
diagnostics report only whether a key is configured, never the key value. Tune
`workers.macro_sync.macrodata_timeout_seconds` below the worker hard timeout so
a stuck macrodata child process is killed and recorded as source-health
failure.

For an operator-triggered repair of one bounded window, use the same sync
service as the worker:

```bash
uv run parallax macro sync --bundle macro-core --start YYYY-MM-DD --end YYYY-MM-DD
uv run parallax macro status
```

A good macro status has `history_ready=true`, a history coverage ratio above
the configured threshold, no required concept below minimum history for pages
claiming `ready`, a recent `latest_sync_run`, `facts_max_observed_at` near the
expected upstream date, and `projection_behind_facts=false` after projection
catches up. If facts exist but no macro snapshot exists yet,
`projection_behind_facts=true`; that means projection has not caught up, not
that source facts are missing. The `macrodata_cli` block must show the expected
package version and `required_bundle_series_available=true`; otherwise the
runtime is using an old packaged `macrodata-cli` bundle and sync cannot import
all Parallax-required series. The installed macrodata runtime must also expose
history commands for the configured event bundles before the default worker
cadence can refresh decision-console catalysts. FRED public CSV timeouts or a
missing optional FRED API key are source-health gaps; they should appear as partial
coverage/data gaps and are not frontend defects.

The full CLI surface is documented by `uv run parallax --help`.
Treat that output as the source of truth — do not enumerate commands
here. A snapshot lives at `generated/cli-help.md`.

## Docker Compose

```bash
export GITHUB_TOKEN="$(gh auth token)"  # required when GitHub dependencies are private
make docker-check
make docker-up
make docker-status
make docker-logs
make docker-down
```

Bind-mounts host `~/.parallax/` into the container, including
both `config.yaml` and `workers.yaml`; PostgreSQL data is pinned to the
`parallax-postgres` named volume.

`make docker-check` verifies the Docker CLI, the Compose plugin, and daemon
access before the build starts. If it reports that the Docker daemon is not
reachable, start Docker Desktop or grant the current terminal access to the
Docker socket before rerunning `make docker-up`.

PostgreSQL observability is part of the compose runtime. The PostgreSQL image
loads `pg_stat_statements`, PoWA, `pg_stat_kcache`, `pg_qualstats`, and
`pg_wait_sampling`; slow logs are mounted under
`~/.parallax/postgres-logs`.

```bash
./scripts/pgbadger_report.sh
./scripts/powa_configure.sh
```

`pgbadger_report.sh` writes
`~/.parallax/reports/pgbadger/pgbadger-latest.html`.
`powa_configure.sh` configures the local PoWA GUCs and server row with bounded
retention, takes snapshots, and prints only non-secret server metadata plus
current/history row counts.

## Frontend (`web/`)

```bash
cd web
npm install
npm run dev          # vite dev server with API proxy
npm run build        # production bundle
npm run preview      # serve the build locally
```

See `FRONTEND.md` for architecture and component conventions.
