# Architecture

> **Scope.** Owns Python-service package boundaries, dependency direction, and conceptual data flow for `gmgn-twitter-intel`. Frontend (`web/`) architecture lives in `FRONTEND.md`. Public interface contracts live in `CONTRACTS.md`.

The service is organised around domain packages, explicit integration adapters, platform infrastructure, and app surfaces. Boundaries are mechanically enforced by `tests/test_src_domain_architecture.py` and `tests/test_project_structure.py::test_project_uses_domain_package_src_layout`.

```
GMGN public stream
  → domains/ingestion           (raw frame normalisation, snapshot gate)
  → domains/evidence            (transactional facts: events, evidence, intents, resolutions, asset identity)
  → domains/asset_market        (background workers: event_anchor and decision_latest observations, profile refresh, discovery)
  → domains/token_intel         (token_radar_rows projection, scoring, search read model)
  → domains/social_enrichment   (watched-event extraction)
  → domains/closed_loop_harness (signal seeds, settlement, outcomes)
  → domains/pulse_lab           (candidate gate, agent route, decision, audit ledger)
  → domains/watchlist_intel     (handle timeline read model and account topic summaries)
  → domains/notifications       (rules, delivery)
  → app/surfaces/api + app/surfaces/cli
```

This repository is the system of record for agent work: if a production
decision changes, update the nearest architecture / contract / reliability
document in the same change. A fresh agent must not need chat history to know
where token identity is extracted, resolved, refreshed, scored, and served.

## Architecture Invariants (Kappa/CQRS)

These nine invariants govern how data flows through the service. Code that
violates them is wrong even if tests pass; tests that depend on a violation
are wrong too.

1. **Facts-first persistence.** `events`, `event_entities`, `token_evidence`,
   `token_intents`, `token_intent_lookup_keys`, `token_intent_resolutions`,
   `registry_assets`, `asset_identity_evidence`, `asset_identity_current`,
   and `price_observations` are the business fact tables. Every other
   persisted table is a derived read model that can be rebuilt from these
   facts.
2. **One material market fact type.** Market data from any provider is
   normalised into a `MarketObservation`
   (`domains/asset_market/types/market_observation.py`) before persistence;
   provider raw frames are inputs, not facts.
3. **Two market time roles.** `MarketContext.event_anchor` serves event-time
   and back-testing; `MarketContext.decision_latest` serves current
   decision, UI, and Signal Pulse. The two roles are persisted in distinct
   partitions (`observation_kind`) of `price_observations` and must never
   overwrite each other.
4. **One writer per read model.** Each derived read model has exactly one
   runtime writer: `token_radar_rows` is written only by
   `TokenRadarProjectionWorker`; `pulse_candidates`, `pulse_agent_runs`,
   `pulse_agent_run_steps` are written only by `PulseCandidateWorker`. New
   read models must declare their single writer in the owning module's
   ARCHITECTURE.md.
5. **Wake is not truth.** PostgreSQL `NOTIFY` channels
   (`market_observation_written`, `resolution_updated`,
   `token_radar_updated`) carry hint payloads only; consumers re-read DB on
   wake. Every listener must have a bounded `interval_seconds` catch-up so
   a missed `NOTIFY` cannot stall the pipeline.
6. **No runtime compatibility layer.** Hard cuts delete the old runtime
   path. No `_overlay_*`, no `fallback_to_v2_snapshot`, no "if missing fall
   back to the old field". Migration code and rollback docs may reference
   removed names; runtime, public API, and frontend code may not.
7. **Material observation write budget.** `LivePriceGateway` persists a
   `decision_latest` row only when `should_persist_live_observation`
   returns `True` (`first_seen` / `heartbeat` /
   `significant_price_change` / `gate_field_change` /
   `provider_state_change`). Every other valid frame updates the in-process
   cache and may fan out over WS, but it does not become a fact.
8. **Observable IO state.** Each WS provider exposes a connection state
   (`disconnected | connecting | authenticating | subscribed | streaming |
   failed`) with a `last_state_change_at_ms`. The snapshot gate exposes
   outcome counters (`immediate_complete | debounced_complete |
   debounced_timeout | non_tw_channel`). Both surface through
   `/api/status`.
9. **Audit ledger truth.** Every Signal Pulse decision must be replayable
   from `pulse_agent_runs` and `pulse_agent_run_steps`. Insufficient data
   finishes as an abstain decision with the audit row written; no path may
   return a decision without an audit row, and no path may invent a
   confidence or display status to avoid abstaining.

Cross-cutting primitives that implement these invariants:

- `MarketObservation`, `MarketContext`, `MarketReadiness` — value types in
  `domains/asset_market/types/market_observation.py`; the only market fact
  contract across domains.
- `runtime.bootstrap()` — composition entry point that builds
  `DBPoolBundle`, provider wiring, repositories, the canonical worker
  map, `WorkerScheduler`, API/WebSocket surfaces, readiness dependencies,
  and lifecycle ownership.
- `DBPoolBundle` — owns `api_pool`, `worker_pool`, and `wake_pool`.
  HTTP/WebSocket reads use the API pool, background workers use the
  worker pool, and wake emit/listen traffic uses the wake pool so read
  traffic cannot be starved by projection or listener work.
- `worker_registry.py` and `WorkerScheduler` — declare the canonical
  worker keys/classes and own worker start/stop/status semantics.
- Wake emission/listening is composed via
  `DBPoolBundle.wake_emitter()` and `DBPoolBundle.wake_listener()`.
  Domain workers receive wake dependencies by injection and never call
  `pg_notify` directly.
- `should_persist_live_observation` — single decision function in
  `domains/asset_market/services/live_observation_policy.py`; the live
  write budget gate.

## Package Roots

| Root | Responsibility |
|------|----------------|
| `app/` | Composition root plus HTTP, WebSocket, and CLI surfaces. `app/runtime/bootstrap.py` wires `DBPoolBundle`, providers, repositories, the canonical worker registry, `WorkerScheduler`, readiness, and lifecycle. `app/surfaces/{api,cli}/` translate public inputs and outputs. Wake mechanics flow through `DBPoolBundle.wake_emitter()` / `wake_listener()`. |
| `domains/` | Product domains. Each domain owns its repositories, queries, services / scoring, read models, and runtime workers. |
| `integrations/` | External adapters for GMGN, OKX, and OpenAI Agents. They translate third-party API shapes but do not own product decisions. |
| `platform/` | Config, PostgreSQL infrastructure (client, migrations, audit, Alembic), logging, and runtime paths. Platform never imports product domains. |

Top-level entry shims `cli.py` and `__main__.py` exist only because `pyproject.toml` points the installed command at `gmgn_twitter_intel.cli:main`. They contain no logic.

## Role Markers

Plans and subsystem architecture docs may tag files with these role markers.
They are descriptive labels for ownership and data-flow review; dependency
direction is still enforced by the package rules below.

| Marker | Meaning |
|--------|---------|
| `[ADAPTER]` | Translates third-party shapes such as GMGN, OKX, Marketlane, or OpenAI Agents into internal values. Does not own product decisions. |
| `[COMMAND]` | Handles write-side use cases: ingesting events, resolving identity, refreshing facts, or writing material observations. |
| `[FACT]` | Owns persisted business facts or value types that represent those facts. |
| `[WAKE]` | Emits or consumes wake hints such as LISTEN/NOTIFY. Wake hints are never the source of correctness. |
| `[PROJECTION]` | Builds derived read models from facts. Projection output must be rebuildable. |
| `[READ MODEL]` | Product-facing derived state such as Token Radar rows, profile blocks, or Signal Pulse candidates. |
| `[QUERY]` | Owns read-side queries over facts or read models. |
| `[SCORING]` | Computes deterministic scores, gates, readiness, and diagnostics from query results. |
| `[SURFACE]` | HTTP, WebSocket, or CLI translation layer. Surfaces do not perform provider calls, scoring, token resolution, or raw SQL joins. |
| `[UI]` | Frontend code that consumes public contracts. |
| `[DELETE]` | Legacy runtime path scheduled for removal by an active hard-cut plan. |

## Domains

| Domain | Owns |
|--------|------|
| `domains/ingestion/` | GMGN public-stream frame handling, snapshot gate, handle filtering, raw public-stream normalisation, collector status. |
| `domains/evidence/` | Canonical Twitter event model, event identity, text projection, entity extraction, evidence and entity persistence, ingest orchestration. |
| `domains/asset_market/` | Asset registry, chain/address identity, asset identity evidence/current identity selection, exact-token profile facts, `price_observations` (`event_anchor` and `decision_latest` roles via `MarketObservation`/`MarketContext`/`MarketReadiness`), live price gateway, discovery, and CEX route sync. |
| `domains/token_intel/` | Token evidence, token intents, deterministic resolution, target-first search read model, token-target views, Token Radar feature aggregation, `token_factor_snapshot_v3_social_attention` construction, factor-snapshot projection, evaluation diagnostics, audit queries, signal alerts. |
| `domains/social_enrichment/` | Watched-event gate, social-event extraction schema, OpenAI Agents enrichment lifecycle, enrichment worker. |
| `domains/closed_loop_harness/` | Social-event harness extraction, attention seeds, snapshots, settlement, outcomes, credits, weights, harness health, ops worker, score-bucket read models. |
| `domains/notifications/` | Notification rules, repository, delivery, workers, candidate types. |
| `domains/pulse_lab/` | Signal Pulse read model, factor-snapshot candidate gate / worker, unified decision runtime policy, stage replay ledger, and pulse persistence. |
| `domains/watchlist_intel/` | Watchlist handle-level topic summaries, signal/all handle timeline read model, summary job queue, and handle summary worker. |
| `domains/account_quality/` | Account-quality snapshots, account-quality read service, account-alert read service. |

## Module Architecture Documents

Global architecture stays intentionally small. Important subsystems keep their
own maps next to the code they describe, and this file links to them.

| Module | File | Covers |
|--------|------|--------|
| Token Radar and token identity | [`src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`](../src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md) | GMGN frame to token evidence, intents, deterministic resolution, discovery / reprocess, market observations, radar projection, and hard identity boundaries. |
| Asset market and material observations | [`src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md`](../src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md) | Asset identity evidence ledger, `MarketObservation` schema, anchor / live / profile / discovery workers, material observation write budget, provider capability model. |
| Signal Pulse pipeline | [`src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md`](../src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md) | Candidate gate, agent route policy, stage runtime, decision persistence, audit ledger, abstain contract. |

When a subsystem needs more than a short row here, add
`src/gmgn_twitter_intel/domains/<domain>/ARCHITECTURE.md` and link it from this
table. Keep local docs minimal, current, and tied to code changes.

## Dependency Direction

Within a domain, the allowed sequence is:

```
types/config → repositories/queries → services/scoring → read_models/runtime → app surfaces
```

| Layer | May import from |
|-------|-----------------|
| `domains/<d>/types`, `domains/<d>/config` | stdlib, third-party, same-domain `types`. |
| `domains/<d>/providers.py` | stdlib, third-party typing primitives, and same-domain or interface value types. Pure provider contracts only; no `integrations/*`, `platform/db`, or `platform/paths`. |
| `domains/<d>/repositories`, `domains/<d>/queries` | own domain's `types`, `platform/db`, stdlib, third-party. **Never** imports `services/`, `runtime/`, `read_models/`. Owns SQL. |
| `domains/<d>/services`, `domains/<d>/scoring` | own domain's `types`, `providers.py`, `repositories`, `queries`, plus other domains' `interfaces.py` only. **No `integrations/*`, `platform/db`, or `platform/paths`.** |
| `domains/<d>/read_models` | own domain's `types`, `repositories`, `queries`, plus other domains' `interfaces.py`. **No raw SQL** — query modules live in `repositories/` or `queries/`. |
| `domains/<d>/runtime` | own domain's `services`, `providers.py`, `repositories`, `queries`, `scoring`, plus other domains' `interfaces.py`. **No `integrations/*`, `platform/db`, or `platform/paths`.** |
| `app/runtime/providers_wiring.py` | Service-process composition module. The only service-runtime file that joins concrete `integrations/*` clients with domain Provider contracts. It may translate supplier shapes such as OKX chain indexes into domain values. |
| `app/runtime/bootstrap.py` | Runtime orchestration: builds `DBPoolBundle`, repositories, workers, surfaces, readiness dependencies, and lifecycle. Imports `wire_providers(...)` / `WiredProviders`; does not import concrete integrations or domain provider modules directly. |
| `app/runtime/worker_registry.py` and `app/runtime/worker_scheduler.py` | Canonical worker key/class inventory plus start, stop, close, status, and unhealthy-reason semantics. |
| `app/runtime` | composition root: may import any domain runtime, repository, or interface to wire the process, subject to the dedicated Provider wiring rule above. |
| `app/surfaces/api`, `app/surfaces/cli` | domain `interfaces.py` and read services. **No domain SQL, scoring, settlement, token resolution, or notification rules** — surfaces translate public inputs into domain calls. |
| `platform/*` | stdlib, third-party. **Never** imports `domains/`, `integrations/`, or `app/`. |
| `integrations/*` | stdlib, third-party, `platform/*`. They wrap external APIs; they do not import `domains/` or `app/`. |

Cross-domain imports MUST go through the target domain's `interfaces.py` (or `_constants.py` for leaf data). `tests/test_src_domain_architecture.py::test_cross_domain_imports_use_interfaces` enforces this.

Raw SQL (`conn.execute(...)`) lives ONLY in `repositories/`, `queries/`, `platform/db/`, or `app/runtime/` health checks. `tests/test_src_domain_architecture.py::test_raw_sql_is_owned_by_repositories_queries_or_app_runtime` enforces this.

Transaction ownership follows the same rule: domain services and runtime workers use repository/session Unit of Work methods, not `platform.db.postgres_client.transaction` directly. Repositories and `app/runtime/repository_session.py` own the concrete PostgreSQL transaction context.

Provider modules are intentionally sparse. Only domains with real inbound cross-cutting dependencies have `providers.py` today: `ingestion`, `asset_market`, `social_enrichment`, `pulse_lab`, and `watchlist_intel`. Do not add empty provider files.

CLI ops remain a separate operational surface exception: they may construct external clients for explicit operator commands, while service runtime construction stays centralized in `app/runtime/providers_wiring.py`.

## Pulse Agent Runtime

Signal Pulse is the first concrete strategy on the unified Agent Runtime Core.
`domains/pulse_lab/services/agent_routing.py` owns deterministic route policy
(`cex`, `meme`, or `research_only`) and completeness gates. The Pulse worker
turns a factor snapshot into a route, writes an agent run, short-circuits
research-only or hard-blocked rows to an abstain decision, and otherwise calls
the configured `PulseDecisionProvider`.

OpenAI-specific stage execution lives only under `integrations/openai_agents/`.
That adapter runs the Analyst, Critic, and Judge stages with typed outputs and
returns domain values; it does not own routing, persistence, product thresholds,
or SQL. `app/runtime/providers_wiring.py` is the composition point that binds
the concrete adapter to the `pulse_lab` provider protocol.

The audit ledger is PostgreSQL: `pulse_agent_runs` records the final outcome and
route, `pulse_agent_run_steps` records replayable stage inputs/prompts/outputs,
and `pulse_candidates.decision_*` plus `decision_json` are the public decision
source. Signal Pulse public payloads expose `decision`, `factor_snapshot`,
`gate`, and `fact_card`.

## Asset Profile Facts

Resolved DEX asset profile facts live in `domains/asset_market`, not in Token
Radar scoring snapshots. The runtime profile lane is:

```
resolved Asset(chain,address)
  → AssetProfileRefreshWorker
  → dex_profile_market.token_profile(...)
  → asset_profiles
  → TokenProfileReadModel
  → /api/token-radar + /api/search/inspect + CLI asset-flow
  → shared frontend TokenProfileCard
```

Only `asset_market` workers and ops commands may call the profile provider.
HTTP handlers, CLI read commands, Token Radar projection, Search read models,
and frontend components read persisted `asset_profiles` through
`TokenProfileReadModel`. Official links and descriptions must be visible without
running a narrative agent; future narrative jobs may consume profile facts, but
they do not own official profile data.

## Generated and reference material

- `docs/generated/{cli-help,ws-protocol,score-versions,db-schema}.md` — regenerated by `make docs-generated`. Score-version paths reflect `domains/token_intel/scoring/`.
- `docs/CONTRACTS.md` — public HTTP / WebSocket / CLI surface contracts.
- `docs/references/` — papers and external API references underpinning algorithm choices.

To find code, prefer `ls src/gmgn_twitter_intel/domains/<domain>/` over a memorised file list. This file pins the package map; per-file responsibilities live in the code and its tests.
