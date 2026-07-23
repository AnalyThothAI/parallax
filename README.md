# Parallax

Parallax is an evidence-first market research service. It ingests social,
news, macro, DEX/CEX, and provider observations; persists material facts in
PostgreSQL; builds deterministic current views; and exposes them through one
React console, HTTP/WebSocket APIs, and a JSON CLI.

Parallax is not a trading bot or a chat product. Provider frames are inputs,
not business truth.

## Architecture

```text
providers
  -> ingestion adapters
  -> PostgreSQL material facts
  -> durable dirty targets / bounded catch-up
  -> single-writer current read models
  -> HTTP / WebSocket / CLI / React
```

The core rules are:

- PostgreSQL material facts are the only business truth.
- Current rows use stable product/window/target keys, never run or attempt IDs.
- Each current read model has exactly one writer and is rebuildable from facts.
- Unchanged projections write zero serving rows.
- Workers recover by re-reading PostgreSQL at bounded intervals; there is no
  wake-message correctness dependency.
- Public reads never call providers or execute models.
- Missing evidence is explicit `unavailable` or `insufficient_evidence`, never
  a fabricated zero or fallback.

The dormant provider-neutral model-execution library remains isolated from
production composition and owns no worker, queue, product state, or API field.

See [Architecture](docs/ARCHITECTURE.md) for the data and module boundaries.

## Product surfaces

| Surface | Purpose |
|---|---|
| React console | Token Radar, Search, Token Case, Stocks, News, Macro, Watchlist, and notifications |
| HTTP | health/readiness, authenticated status, and persisted read APIs |
| WebSocket | authenticated replay and live persisted events |
| JSON CLI | config, DB, research reads, queue inspection, and explicit repair/rebuild commands |
| PostgreSQL | facts, control state, read models, and side-effect ledgers |

Exact HTTP fields come from
[OpenAPI](docs/generated/openapi.json). The current CLI snapshot is
[cli-help.md](docs/generated/cli-help.md).

## Runtime configuration

Live runs use operator-owned files:

```text
~/.parallax/config.yaml
~/.parallax/workers.yaml
~/.parallax/postgres_password
~/.parallax/logs/
~/.parallax/cache/
```

Repository fixtures and `.env` files are not runtime truth. Before diagnosing
real data, confirm the active paths without printing secrets:

```bash
uv run parallax config
```

## Quick start

```bash
make sync
make init
make db-migrate
make serve
```

The console is served at `http://127.0.0.1:8765/`.

Docker Compose:

```bash
make docker-up
make docker-status
make docker-logs
make docker-down
```

Useful read-only checks:

```bash
curl -fsS http://127.0.0.1:8765/healthz
curl -fsS http://127.0.0.1:8765/readyz
uv run parallax config
uv run parallax db health
uv run parallax recent --limit 20
uv run parallax ops queue-inspect --status active
uv run parallax macro status
```

Mutating maintenance commands require their explicit execution flag where a
dry-run mode exists.

## Development

```bash
make check
make test-integration   # when the changed seam requires PostgreSQL
make test-contract      # when a public contract changes
cd web && npm run lint && npm run typecheck
```

No repository-wide command or coverage percentage is a universal completion
gate. Select the smallest commands that cross the changed seam and record what
ran. Non-trivial changes use the four-file SDD workflow under
`docs/sdd/features/active/`.

## Documentation

| Need | Source |
|---|---|
| Install and deployment | [docs/SETUP.md](docs/SETUP.md) |
| Data and module architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Public config/API/WS/CLI contracts | [docs/CONTRACTS.md](docs/CONTRACTS.md) |
| Operations, workers, reliability, diagnosis | [docs/OPERATIONS.md](docs/OPERATIONS.md) |
| Development, SDD, design, testing | [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) |
| Frontend boundaries | [docs/FRONTEND.md](docs/FRONTEND.md) |
| Secrets and authentication | [docs/SECURITY.md](docs/SECURITY.md) |
| PostgreSQL performance | [docs/references/POSTGRES_PERFORMANCE.md](docs/references/POSTGRES_PERFORMANCE.md) |

Domain-specific maps live at
`src/parallax/domains/<domain>/ARCHITECTURE.md`. Generated artifacts live in
`docs/generated/` and must have checked-in generators.

## Non-goals

- no trade execution;
- no compatibility aliases for retired contracts;
- no provider response, queue, process cache, or projection as alternate truth;
- no hidden provider calls or mutations in read APIs;
- no repository-local live credentials.
