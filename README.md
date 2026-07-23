# Parallax

**Parallax Market Research System** is an evidence-first research system for
turning social, news, macro, and DEX/CEX market flow into replayable evidence,
current research views, and operator alerts.

Parallax is built around the idea that a market event becomes more trustworthy
when it can be observed from several independent angles: social attention,
token identity, liquidity, derivatives positioning, news, and macro evidence.
Provider adapters are inputs to that research loop; the product boundary is
durable evidence, rebuildable current views, and operator workflows built on
top of them.

## Research Direction

Parallax is a market research workbench, not a trading bot and not a chat UI.
Its core research loop is:

```text
Information flow
  -> Material facts
  -> Identity and market context
  -> Deterministic current views
  -> Explicit evidence conclusions and gaps
  -> Operator console and notifications
```

The system should answer four questions for every asset, event, or candidate:

- **What happened?** Preserve the raw market/social/news observation as durable
  evidence.
- **What is it really about?** Resolve token identity, asset venue, author,
  topic, macro concept, and related market target.
- **Why is it worth attention?** Show deterministic gates, factor snapshots,
  source evidence, freshness, and missing fields.
- **What does the evidence support?** Keep conclusions, confirmations,
  contradictions, freshness, samples, and invalidation conditions tied to the
  exact facts that support them.

## Architecture At A Glance

```text
Social/event streams     News feeds / OpenNews / CryptoPanic
Macrodata bundles       DEX / CEX / market-data providers
         |              |
         v              v
  ingestion and provider adapters
         |
         v
  PostgreSQL material facts
         |
         v
  identity, market context, and deterministic projections
         |
         v
  Token Radar / Search / Token Case / Watchlist / Stocks / News / Macro
         |
         v
  diagnostics and notifications
         |
         v
  React console / HTTP API / WebSocket / JSON CLI
```

Parallax follows a Kappa/CQRS model:

- **Facts are truth.** Business observations live in PostgreSQL tables such as
  `events`, `token_intents`, `token_intent_resolutions`, `asset_identity_*`,
  `market_ticks`, `enriched_events`, `news_items`, and `macro_observations`.
- **Read models are rebuildable.** Current serving rows use stable product,
  window, scope, and target keys. They are not keyed by run ids, attempts,
  timestamp-derived generations, or UUIDs.
- **One writer per read model.** Worker-owned models are declared in the worker
  manifest; transactionally maintained models such as `market_tick_current`
  are documented by their owning domain service.
- **Catch-up is durable.** Workers re-read PostgreSQL state on bounded
  intervals without a message-delivery dependency.
- **Evidence judgments are explicit.** Macro conclusions expose their rule
  version, rule hits, evidence references, freshness, confirmations,
  contradictions, and invalidation conditions. Missing capability is reported
  as unavailable rather than inferred.
- **The retained model-execution library is dormant.** Production bootstrap,
  workers, status, APIs, and frontend instantiate no model-backed product
  consumer.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[docs/WORKERS.md](docs/WORKERS.md) for the canonical implementation map.

## Product Surfaces

| Surface | Role |
| --- | --- |
| React console | Operator workbench for Radar, Search, Token Case, Stocks, News, Macro, Watchlist, Ops, and notifications. |
| HTTP API | Authenticated `/api/*` read surfaces, health checks, bootstrap, token images, status, and diagnostics. |
| WebSocket | Authenticated `/ws` replay/live stream for events, subscriptions, notifications, and live market updates. |
| JSON CLI | Scriptable local/operator interface for config, DB health, read-model queries, macro sync/status, and ops repair commands. |
| PostgreSQL | Durable system of record for facts, bounded control rows, current read models, and required side-effect ledgers. |

## Research Console Model

The product is organized around information flow rather than a generic chat
pane:

| Panel | Purpose |
| --- | --- |
| Flow Tape | Chronological social, news, macro, market, and watchlist events with provenance and data-health badges. |
| Radar Board | Deterministic gates and ranked targets: why a target entered the current Token Radar view. |
| Evidence Dossier | One selected target with source posts, resolved identity, market ticks, profiles, News facts, and macro context. |
| News Evidence | Source-backed story membership, entity resolution, fact candidates, provider observations, content classification, and market scope. |
| Macro Evidence | Six fixed pages over one completed-session snapshot: Overview, Cross-asset, Rates & Inflation, Growth & Labor, Liquidity & Funding, and Credit. |
| Ops Console | Worker status, queue depth, provider health, retries, stale projections, and safe repair actions. |

Tooling should be safe by default:

- Prefer read-only inspection and dry-run repair commands.
- Show the exact fact rows or read-model keys a tool will touch before execute.
- Keep credentials, tokens, and secret-bearing provider payloads out of public
  UI and sanitized operator output.
- Expose replay, rebuild, enqueue, and export actions as operator tools, not
  hidden side effects inside read APIs.
- Treat unsupported evidence as an explicit gap, never a zero, proxy, or hidden
  fallback.

## Main Domains

| Domain | Responsibility |
| --- | --- |
| `ingestion` | Provider event normalization, source lifecycle, snapshot gates, and ingest entrypoint. |
| `evidence` | Canonical event model, entity extraction, material evidence, transactional persistence, and Watchlist reads. |
| `asset_market` | Asset identity, discovery, profiles, token images, market facts, transactionally maintained current ticks, and post-commit live updates. |
| `token_intel` | Token evidence, deterministic resolution, transparent Token Radar factors, fact-only search/inspection, and diagnostics. |
| `news_intel` | Configured news ingestion, canonical facts, deterministic token/fact/story extraction, source health, and fact-only News page rows. |
| `macro_intel` | Macrodata sync, macro observations, compact series, and one atomic six-document evidence snapshot. |
| `notifications` | Notification rules, candidates, side-effect delivery, and delivery ledger state. |

## Runtime Names

Parallax uses one product/runtime identity across the active project:

| Surface | Value |
| --- | --- |
| Python package/distribution | `parallax` |
| Installed CLI command | `parallax` |
| Python import package | `parallax` |
| Operator config directory | `~/.parallax/` |
| Compose project/data volume names | `parallax*` |
| Current GitHub repository target | `AnalyThothAI/parallax` |

## Runtime Configuration

Live-data runs use operator-owned files under `~/.parallax/`.
Repository fixtures, generated examples, and `.env` files are not runtime truth.

```text
~/.parallax/config.yaml       application, providers, credentials, storage
~/.parallax/workers.yaml      worker cadence, leases, retries, and timeouts
~/.parallax/postgres_password local PostgreSQL secret for Compose
~/.parallax/logs/             service logs
~/.parallax/cache/            local media mirrors and runtime cache
```

Before debugging real provider data, always confirm the active paths:

```bash
uv run parallax config
```

Report only paths, redacted booleans, status fields, and command results. Do not
paste WebSocket tokens, API keys, provider passwords, secret-bearing DSNs, or raw
credential payloads into issues, docs, commits, or chat.

## Quick Start

Install dependencies and create local runtime config:

```bash
make sync
make init
make config
```

Run the service in the foreground:

```bash
make serve
```

Apply database migrations when needed:

```bash
make db-migrate
make db-health
```

Run with Docker Compose:

```bash
make docker-up
make docker-status
make docker-logs
make docker-down
```

The app serves the production frontend at:

```text
http://127.0.0.1:8765/
```

The frontend reads `/api/bootstrap`, then uses the configured token for
authenticated API and WebSocket calls. External clients should authenticate with
`Authorization: Bearer <ws_token>` for HTTP and an auth message for `/ws`.

## Common Operator Commands

```bash
uv run parallax --help
uv run parallax config
uv run parallax db health
uv run parallax recent --limit 20
uv run parallax asset-flow --window 1h --scope all --limit 20
uv run parallax ops queue-inspect --status active
uv run parallax macro status
```

The CLI is intentionally JSON-oriented so it can be called from scripts and
other agents. Treat `uv run parallax --help` as the source of truth for
the current command surface. A generated snapshot lives at
[docs/generated/cli-help.md](docs/generated/cli-help.md).

## Frontend Development

```bash
cd web
npm install
npm run dev
npm run typecheck
npm run lint
npm run build
```

Frontend architecture is harness-constrained. Before changing UI code, read
[docs/FRONTEND.md](docs/FRONTEND.md). Feature CSS must live with the owning
feature or component, shared UI primitives own their own styles, and
`npm run lint` runs both ESLint and the frontend architecture harness.

## Verification

Fast local gates:

```bash
make check
```

Full completion gate:

```bash
make check-all
```

`make check-all` runs backend lint/type/unit/architecture/contract checks,
frontend type/lint/architecture checks, integration/e2e/golden lanes, and
coverage. See [docs/TESTING.md](docs/TESTING.md) and
[docs/WORKFLOW.md](docs/WORKFLOW.md) before claiming a behavior change is done.

## Documentation Map

| Need | Source |
| --- | --- |
| Install, local run, Docker | [docs/SETUP.md](docs/SETUP.md) |
| Backend architecture and boundaries | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Frontend architecture | [docs/FRONTEND.md](docs/FRONTEND.md) |
| Public config/API/WS/CLI contracts | [docs/CONTRACTS.md](docs/CONTRACTS.md) |
| Worker inventory and runtime ownership | [docs/WORKERS.md](docs/WORKERS.md) |
| Worker flow and debugging | [docs/WORKER_FLOW.md](docs/WORKER_FLOW.md) |
| Testing and completion gates | [docs/TESTING.md](docs/TESTING.md) |
| Spec, plan, verification workflow | [docs/WORKFLOW.md](docs/WORKFLOW.md) |
| Security and secrets handling | [docs/SECURITY.md](docs/SECURITY.md) |
| Reliability invariants | [docs/RELIABILITY.md](docs/RELIABILITY.md) |
| Design discipline | [docs/DESIGN_DISCIPLINE.md](docs/DESIGN_DISCIPLINE.md) |
| PostgreSQL performance diagnostics | [docs/references/POSTGRES_PERFORMANCE.md](docs/references/POSTGRES_PERFORMANCE.md) |

## Non-Goals

- Parallax is not a trading bot and does not execute trades.
- Parallax is not a complete social or market-data firehose; coverage depends
  on the configured provider set and each provider's permitted data surface.
- Parallax does not treat job queues, provider raw frames, process caches, or
  derived projections as material facts.
- Parallax does not use repository-local `.env` files as live runtime config.
