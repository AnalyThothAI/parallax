# Architecture Docs Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring project docs into alignment with the 2026-05-13 Token Radar Kappa/CQRS hard cut so a fresh agent can produce code that follows the invariants without chat history or the hard-cut plan artefact.

**Architecture:** Centralise nine Kappa/CQRS invariants at the top of `docs/ARCHITECTURE.md`. Add two new module ARCHITECTURE.md files (`domains/asset_market/`, `domains/pulse_lab/`). Add a cross-domain worker inventory at `docs/WORKERS.md`. Patch routers (`AGENTS.md`, `CLAUDE.md`), operational doc (`docs/RELIABILITY.md`), and one stale path reference in `docs/TESTING.md`. No code changes.

**Tech Stack:** Markdown, GitHub-flavored. No build artefacts, no generated docs.

---

## Status

**Status:** Pending
**Date:** 2026-05-14
**Owning spec:** `docs/superpowers/specs/active/2026-05-14-architecture-docs-kappa-cqrs-refresh.md`
**Worktree:** `.worktrees/architecture-docs-kappa-cqrs-refresh/`
**Branch:** `codex/architecture-docs-kappa-cqrs-refresh`

## Pre-flight

- [ ] Create worktree (the new module ARCHITECTURE.md files land under `src/`, which triggers `WORKFLOW.md` worktree policy):

  ```bash
  git worktree add .worktrees/architecture-docs-kappa-cqrs-refresh -b codex/architecture-docs-kappa-cqrs-refresh main
  ```

- [ ] Verify worktree state:

  ```bash
  git worktree list
  git -C .worktrees/architecture-docs-kappa-cqrs-refresh branch --show-current
  git -C .worktrees/architecture-docs-kappa-cqrs-refresh status --short
  ```

  Expected: branch is `codex/architecture-docs-kappa-cqrs-refresh`, status clean.

- [ ] Baseline (docs-only change does not need full test suite, but architecture tests must still pass):

  ```bash
  cd .worktrees/architecture-docs-kappa-cqrs-refresh
  uv run pytest tests/architecture/test_src_domain_architecture.py tests/integration/test_docs_generated.py -q
  ```

  Expected: pass.

All subsequent task commands assume CWD is the worktree root.

---

## Task 1 — docs/ARCHITECTURE.md: invariants, data-flow, module table

**Files:**
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1:** Replace the existing top data-flow diagram. The current diagram ends with `→ app/surfaces/api + app/surfaces/cli`. Replace the entire fenced block plus the line `This repository is the system of record for agent work: ...` paragraph that immediately follows the diagram is NOT changed; only the diagram itself.

  Current:

  ```
  GMGN public stream
    → domains/ingestion
    → domains/evidence
    → domains/token_intel
    → domains/social_enrichment
    → domains/closed_loop_harness
    → domains/notifications and domains/pulse_lab
    → app/surfaces/api + app/surfaces/cli
  ```

  New:

  ```
  GMGN public stream
    → domains/ingestion           (raw frame normalisation, snapshot gate)
    → domains/evidence            (transactional facts: events, evidence, intents, resolutions, asset identity)
    → domains/asset_market        (background workers: event_anchor and decision_latest observations, profile refresh, discovery)
    → domains/token_intel         (token_radar_rows projection, scoring, search read model)
    → domains/social_enrichment   (watched-event extraction)
    → domains/closed_loop_harness (signal seeds, settlement, outcomes)
    → domains/pulse_lab           (candidate gate, agent route, decision, audit ledger)
    → domains/notifications       (rules, delivery)
    → app/surfaces/api + app/surfaces/cli
  ```

- [ ] **Step 2:** Insert a new top-level section **`## Architecture Invariants (Kappa/CQRS)`** immediately before the existing `## Package Roots` line. The full section content is:

  ```markdown
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
  - `WakeBus`, `WakeListener` — composition-root primitives in
    `app/runtime/wake_bus.py`; the only place that owns
    `LISTEN/NOTIFY` mechanics. Domain workers receive these by injection.
  - `should_persist_live_observation` — single decision function in
    `domains/asset_market/services/live_observation_policy.py`; the live
    write budget gate.
  ```

- [ ] **Step 3:** In the `Module Architecture Documents` table, replace the existing single row plus the paragraph after it with the updated three-row table:

  Current table (one row plus a paragraph):

  ```markdown
  | Module | File | Covers |
  |--------|------|--------|
  | Token Radar and token identity | [`src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`](../src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md) | GMGN frame to token evidence, intents, deterministic resolution, discovery / reprocess, market observations, radar projection, and hard identity boundaries. |

  When a subsystem needs more than a short row here, add
  `src/gmgn_twitter_intel/domains/<domain>/ARCHITECTURE.md` and link it from this
  table. Keep local docs minimal, current, and tied to code changes.
  ```

  New table (three rows; the trailing paragraph stays):

  ```markdown
  | Module | File | Covers |
  |--------|------|--------|
  | Token Radar and token identity | [`src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`](../src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md) | GMGN frame to token evidence, intents, deterministic resolution, discovery / reprocess, market observations, radar projection, and hard identity boundaries. |
  | Asset market and material observations | [`src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md`](../src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md) | Asset identity evidence ledger, `MarketObservation` schema, anchor / live / profile / discovery workers, material observation write budget, provider capability model. |
  | Signal Pulse pipeline | [`src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md`](../src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md) | Candidate gate, agent route policy, stage runtime, decision persistence, audit ledger, abstain contract. |

  When a subsystem needs more than a short row here, add
  `src/gmgn_twitter_intel/domains/<domain>/ARCHITECTURE.md` and link it from this
  table. Keep local docs minimal, current, and tied to code changes.
  ```

- [ ] **Step 4:** In the existing `Domains` table, locate the row whose `Domain` column is `domains/asset_market/`. Replace its `Owns` cell to additionally name the new value types. The full updated row is:

  ```markdown
  | `domains/asset_market/` | Asset registry, chain/address identity, asset identity evidence/current identity selection, exact-token profile facts, anchor and live `price_observations` (`event_anchor`, `decision_latest` roles via `MarketObservation`/`MarketContext`/`MarketReadiness`), live price gateway, discovery, and CEX route sync. |
  ```

- [ ] **Step 5:** In the existing `Package Roots` table, locate the row whose `Root` column is `app/`. Append one sentence to its `Responsibility` cell so the row reads:

  ```markdown
  | `app/` | Composition root plus HTTP, WebSocket, and CLI surfaces. `app/runtime/` wires domains; `app/surfaces/{api,cli}/` translate public inputs and outputs. `app/runtime/wake_bus.py` owns the `WakeBus` / `WakeListener` `LISTEN`/`NOTIFY` mechanics injected into domain workers. |
  ```

- [ ] **Step 6:** Verify the file:

  ```bash
  rg -n "^## Architecture Invariants \(Kappa/CQRS\)$" docs/ARCHITECTURE.md
  rg -n "asset_market/ARCHITECTURE.md" docs/ARCHITECTURE.md
  rg -n "pulse_lab/ARCHITECTURE.md" docs/ARCHITECTURE.md
  rg -n "WakeBus / WakeListener" docs/ARCHITECTURE.md
  rg -n "MarketObservation" docs/ARCHITECTURE.md
  ```

  Expected: every command emits at least one match.

- [ ] **Step 7:** Run the architecture tests to confirm no link/path assertions broke:

  ```bash
  uv run pytest tests/architecture/test_src_domain_architecture.py tests/integration/test_docs_generated.py -q
  ```

  Expected: pass.

- [ ] **Step 8:** Commit:

  ```bash
  git add docs/ARCHITECTURE.md
  git commit -m "docs(architecture): state Kappa/CQRS invariants and add module links"
  ```

---

## Task 2 — docs/RELIABILITY.md: operational invariants

**Files:**
- Modify: `docs/RELIABILITY.md`

- [ ] **Step 1:** Append the following five sections after the existing `## Pulse Agent Audit Ledger` section (which is currently the last section in the file). Insert the entire block verbatim, preserving the leading blank line.

  ```markdown

  ## Material observation write budget

  Live market frames are persisted to `price_observations(kind='decision_latest')`
  only through
  `domains/asset_market/services/live_observation_policy.should_persist_live_observation`.
  Persistence triggers are exactly `first_seen`, `heartbeat`,
  `significant_price_change`, `gate_field_change`, and
  `provider_state_change`. Every other valid frame may update the in-process
  cache and fan out over WS, but it is not a fact. The synthetic flat-market
  budget is `100 targets × 5 fps × 10 minutes → ≤ 1500 persisted rows`, guarded
  by `tests/benchmark/test_live_observation_write_budget.py`. Tightening the
  thresholds is a config change; loosening them requires a benchmark update in
  the same commit.

  ## Wake hints and catch-up

  PostgreSQL `NOTIFY` channels (`market_observation_written`,
  `resolution_updated`, `token_radar_updated`) are wake hints, not delivery
  guarantees. Every listener
  (`TokenRadarProjectionWorker`, `PulseCandidateWorker`, future workers) runs
  on a bounded `interval_seconds` catch-up loop even when `NOTIFY` is healthy.
  A dropped `NOTIFY` recovers on the next interval; service correctness must
  not depend on `NOTIFY` delivery.

  ## One writer per read model

  Each derived read model has exactly one runtime writer. A second runtime
  writer of `token_radar_rows`, `pulse_candidates`, or any future read model
  is both a reliability incident and an architecture-test violation. Ops paths
  and CLI rebuilds are explicit exceptions and must call the same projection
  service the worker uses; they do not run their own SQL.

  ## Provider connection state

  Streaming providers (OKX DEX WS, GMGN direct WS, and any future streaming
  source) expose a connection state with a `last_state_change_at_ms` and
  publish it through `/api/status`. State values are `disconnected`,
  `connecting`, `authenticating`, `subscribed`, `streaming`, and `failed`.
  Workers must treat `provider_state_change=true` as a `first_seen`-equivalent
  budget trigger so the first fresh frame after recovery is persisted.

  ## Snapshot gate observability

  `CollectorService` exposes snapshot gate outcome counters
  (`immediate_complete`, `debounced_complete`, `debounced_timeout`,
  `non_tw_channel`) through `/api/status`. A non-trivial `debounced_timeout`
  rate is a reliability signal even when raw ingest looks healthy.
  ```

- [ ] **Step 2:** Verify:

  ```bash
  rg -n "^## Material observation write budget$|^## Wake hints and catch-up$|^## One writer per read model$|^## Provider connection state$|^## Snapshot gate observability$" docs/RELIABILITY.md | wc -l
  ```

  Expected: `5`.

- [ ] **Step 3:** Commit:

  ```bash
  git add docs/RELIABILITY.md
  git commit -m "docs(reliability): add Kappa/CQRS operational invariants"
  ```

---

## Task 3 — docs/TESTING.md: align frontend path, link WORKERS.md

**Files:**
- Modify: `docs/TESTING.md`

- [ ] **Step 1:** Find the frontend section header. The current header reads:

  ```markdown
  ## Frontend (`web/src/test/`)
  ```

  Replace it with:

  ```markdown
  ## Frontend (`web/tests/`)
  ```

- [ ] **Step 2:** Inside the same Frontend section, find the bullet that currently reads:

  ```markdown
  - Component and hook tests use Vitest + Testing Library; place them in `web/src/test/`.
  ```

  Replace with:

  ```markdown
  - Component and hook tests use Vitest + Testing Library; place them in `web/tests/component/` or `web/tests/unit/` per the layout in `docs/FRONTEND.md`.
  ```

- [ ] **Step 3:** Inside the same Frontend section, find the bullet:

  ```markdown
  - Domain-logic units in `web/src/domain/` should have unit tests independent of React.
  ```

  Replace with:

  ```markdown
  - Pure model and helper units under `web/src/features/<name>/model/` and `web/src/shared/` should have unit tests independent of React, placed in `web/tests/unit/` mirroring the source path.
  ```

- [ ] **Step 4:** Inside the same Frontend section, find the bullet:

  ```markdown
  - API client wrappers in `web/src/api/` should have contract tests asserting the shapes documented in `CONTRACTS.md`.
  ```

  Replace with:

  ```markdown
  - Feature API hooks under `web/src/features/<name>/api/` and the typed client under `web/src/lib/api/` should have contract tests asserting the shapes documented in `CONTRACTS.md`.
  ```

- [ ] **Step 5:** Add a new top-level section at the end of the file (after `Completion verification`):

  ```markdown

  ## Worker inventory

  Cross-domain runtime worker inventory (fact writes, wake channels, catch-up
  cadence) lives in `docs/WORKERS.md`. A new worker must appear in that
  inventory, in `app/runtime/app.py`'s task list, and in the owning domain's
  `ARCHITECTURE.md` in the same change.
  ```

- [ ] **Step 6:** Verify:

  ```bash
  rg -n "web/src/test/" docs/TESTING.md
  rg -n "^## Frontend \(\`web/tests/\`\)$" docs/TESTING.md
  rg -n "^## Worker inventory$" docs/TESTING.md
  ```

  Expected: the first command emits zero matches; the second and third each emit one match.

- [ ] **Step 7:** Commit:

  ```bash
  git add docs/TESTING.md
  git commit -m "docs(testing): align frontend test path with web/tests and link WORKERS"
  ```

---

## Task 4 — domains/asset_market/ARCHITECTURE.md (new)

**Files:**
- Create: `src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md`

- [ ] **Step 1:** Create the file with the exact content below:

  ````markdown
  # Asset Market Architecture

  > **Scope.** Owns asset identity evidence, the `MarketObservation` fact
  > model, anchor / live / profile / discovery workers, and the live
  > observation write budget. Global package boundaries live in
  > `../../../../docs/ARCHITECTURE.md`; Token Radar projection lives in
  > `../token_intel/ARCHITECTURE.md`; public payload shapes live in
  > `../../../../docs/CONTRACTS.md`.

  Asset Market is the only domain that may call market and identity
  providers in the service runtime. It writes the facts that Token Radar
  projection and Signal Pulse consume; it does not own ranking, decisions,
  or read-model projection.

  ## Stage Map

  | Stage | Code owner | Persisted facts | Invariant |
  |-------|------------|-----------------|-----------|
  | Asset identity evidence | `identity_evidence_policy.py`, `repositories/identity_evidence_repository.py` | `asset_identity_evidence`, `asset_identity_current` | Tweet CA mentions, GMGN payloads, OKX symbol candidates, and OKX exact address hits are separate evidence kinds. One deterministic policy selects current canonical symbol/name/confidence. |
  | Event anchor observation | `services/anchor_price_observation.py`, `runtime/anchor_price_worker.py` | `price_observations(observation_kind='event_anchor')` | One `event_anchor` row per resolution (`source_resolution_id` is unique on the `event_anchor` partition). Anchor describes the event-time observation; it is never overwritten by live data. |
  | Live decision-latest observation | `runtime/live_price_gateway.py`, `services/live_observation_policy.py` | `price_observations(observation_kind='decision_latest')` | Raw provider frames update an in-process cache. Only frames that pass `should_persist_live_observation` become facts. `provider_state_change` after reconnect is a `first_seen`-equivalent trigger. |
  | Asset profile refresh | `runtime/asset_profile_refresh_worker.py`, `services/asset_profile_refresh.py`, `repositories/asset_profile_repository.py` | `asset_profiles` | Resolved DEX assets are enriched through the GMGN exact-token profile role. Profile facts are asset-level current facts and never resolver evidence, ranking factors, or `factor_snapshot_json` fields. |
  | Resolution refresh and discovery | `runtime/resolution_refresh_worker.py`, `repositories/discovery_repository.py` | refreshed `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence/current`, `token_discovery_results` | Recent NIL / AMBIGUOUS lookup keys are refreshed through OKX DEX, then affected intents are reprocessed. Successful refresh emits `resolution_updated` so downstream readers wake; the worker itself does not run inline Token Radar projection. |
  | CEX route sync | `services/asset_market_sync.py` | `cex_tokens`, `price_feeds` | Maintains token/feed routing without refreshing prices. |
  | US equity symbol sync | `services/us_equity_symbol_sync.py` | `registry_assets` (MarketInstrument rows) | Confirms US equity symbols so the deterministic resolver can elevate them above DEX same-symbol assets. |

  ## MarketObservation Schema

  `domains/asset_market/types/market_observation.py` defines the cross-domain
  market fact contract. All providers normalise into these frozen value
  types before any persistence call.

  - `MarketTargetRef(target_type, target_id)` — the resolved target the
    observation belongs to. `target_type` is `Asset` or `CexToken`.
  - `MarketObservation` — single market sample, with `observed_at_ms`,
    `received_at_ms`, `source`, `provider`, `pricefeed_id`, `price_usd`,
    `price_quote`, `quote_symbol`, `price_basis`, `market_cap_usd`,
    `liquidity_usd`, `holders`, `volume_24h_usd`, `open_interest_usd`, and
    `raw_payload_hash`. The dataclass intentionally does not carry the raw
    payload; `raw_payload_hash` is the audit anchor.
  - `MarketReadiness(anchor_status, latest_status, dex_floor_status,
    missing_fields, stale_fields)` — derived per-target readiness facts
    surfaced through `factor_snapshot.market.readiness`.
  - `MarketContext(event_anchor, decision_latest, readiness)` — the public
    market shape. Token Radar projection emits one `MarketContext` per row;
    the API and frontend consume it as-is.

  ## Material Observation Persistence Policy

  `services/live_observation_policy.should_persist_live_observation` is the
  single decision point for whether a live frame becomes a fact. It returns
  `LiveObservationPersistDecision(should_persist, reason)` where `reason` is
  one of:

  | Reason | Trigger |
  |--------|---------|
  | `first_seen` | No previous persisted `decision_latest` exists for `(target_type, target_id, provider, pricefeed_id)`. |
  | `heartbeat` | `now_ms - previous.observed_at_ms ≥ live_observation_heartbeat_seconds * 1000` (default `60s`). |
  | `significant_price_change` | `abs(new_price - last_price) / last_price ≥ live_observation_min_price_change_pct` (default `0.005`). |
  | `gate_field_change` | One of `holders`, `liquidity_usd`, `market_cap_usd`, `volume_24h_usd`, `open_interest_usd` changes missing/present status, or a DEX floor threshold is crossed. |
  | `provider_state_change` | Stream reconnect/recover. The first fresh frame after recovery is persisted. |

  Non-material reasons are `debounced` (inside
  `live_observation_min_write_interval_seconds`, default `5s`) and
  `not_material`. Debounce is an extra guard, not the correctness rule.

  Write budget target: `100 targets × 5 fps × 10 min → ≤ 1500 persisted
  rows`. Enforced by
  `tests/benchmark/test_live_observation_write_budget.py`.

  ## Provider Capability Model

  `providers.py` exposes narrow protocols; there is no `MarketDataSource`
  god interface.

  - `MarketCapability` enum: `QUOTE_CEX`, `QUOTE_DEX_EXACT`, `STREAM_DEX`,
    `SEARCH_DEX`, `PROFILE_DEX_EXACT`, `CANDLES_DEX_EXACT`.
  - `ProviderHealth(provider, capabilities, configured, last_error)` —
    health reports the configured capabilities, not every capability the
    provider could theoretically support. Keep health aligned with actual
    wiring.

  Concrete provider clients (OKX CEX, OKX DEX, OKX DEX WS, GMGN OpenAPI,
  GMGN direct WS, Marketlane) are wired in
  `app/runtime/providers_wiring.py`. Asset Market services and workers
  receive provider protocols by injection and may not import
  `integrations/*`.

  ## Wake Channels

  | Channel | Emitter | Listener |
  |---------|---------|----------|
  | `market_observation_written` | `AnchorPriceWorker`, `LivePriceGateway` (after persisted material observation only) | `TokenRadarProjectionWorker` |
  | `resolution_updated` | `ResolutionRefreshWorker` | `TokenRadarProjectionWorker` |

  Wake mechanics live in `app/runtime/wake_bus.py` (`WakeBus` for emit,
  `WakeListener` for receive). Asset Market workers receive a `WakeBus`
  instance by injection; they never call `pg_notify` directly. See
  `../../../../docs/WORKERS.md` for the cross-domain inventory.

  ## Hard Boundaries

  - Provider raw frames never reach `factor_snapshot_json`. Token Radar
    projection reads `price_observations`, not provider clients.
  - Identity evidence and asset identity selection never feed scoring
    families. They are gates and `data_health` inputs only.
  - `LivePriceGateway` may fan out raw frames to WS for debug/recent
    display, but Token Radar business cache patches use the persisted
    `decision_latest` shape only.
  - CLI ops commands may instantiate concrete provider clients for explicit
    operator commands; service runtime wiring stays centralised in
    `app/runtime/providers_wiring.py`.
  - LLM enrichment may label watched social events, but token identity
    resolution stays deterministic and does not call an LLM in the hot
    path.

  ## Update Triggers

  Update this file in the same change as any of:

  - `MarketObservation` / `MarketContext` / `MarketReadiness` schema.
  - A new persistence trigger or threshold default in the live observation
    policy.
  - A new market `MarketCapability` value or `ProviderHealth` field.
  - A worker gaining or losing a wake-in or wake-out channel.
  - Asset identity evidence kinds or the policy that selects current
    identity.
  - Discovery admission, retained candidate, or reprocess behaviour visible
    to Token Radar.
  ````

- [ ] **Step 2:** Verify:

  ```bash
  test -f src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md
  rg -n "^# Asset Market Architecture$" src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md
  rg -n "should_persist_live_observation" src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md
  rg -n "MarketCapability" src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md
  ```

  Expected: file exists; each `rg` emits at least one match.

- [ ] **Step 3:** Commit:

  ```bash
  git add src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md
  git commit -m "docs(asset_market): add module ARCHITECTURE.md"
  ```

---

## Task 5 — domains/pulse_lab/ARCHITECTURE.md (new)

**Files:**
- Create: `src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md`

- [ ] **Step 1:** Create the file with the exact content below:

  ````markdown
  # Pulse Lab Architecture

  > **Scope.** Owns Signal Pulse: candidate gate, agent route policy, stage
  > runtime, decision persistence, and the audit ledger. Global package
  > boundaries live in `../../../../docs/ARCHITECTURE.md`; the public Pulse
  > decision contract lives in `../../../../docs/CONTRACTS.md`; operational
  > rules for the audit ledger live in
  > `../../../../docs/RELIABILITY.md`.

  Signal Pulse is the first concrete strategy on the unified Agent Runtime
  Core. It turns Token Radar projection rows into agent decisions and
  persists a replayable audit trail. It does not own ranking, projection,
  asset identity, or market data.

  ## Stage Map

  | Stage | Code owner | Persisted facts | Invariant |
  |-------|------------|-----------------|-----------|
  | Candidate gate | `services/pulse_candidate_gate.py` | none (in-memory admission) | Reads `factor_snapshot_json.market.decision_latest`, `normalization.cohort_status`, and gate fields. Fails closed when target rows lack material `decision_latest` or have an insufficient/all-tied cohort. |
  | Agent route policy | `services/agent_routing.py` | none (in-memory decision) | Deterministic route assignment to `cex`, `meme`, or `research_only`. Completeness gates are config-driven. |
  | Stage runtime | `integrations/openai_agents/` (out of domain; called by injection) | none in this domain | Runs Analyst / Critic / Judge stages with typed outputs and returns domain values. Does not own routing, persistence, product thresholds, or SQL. |
  | Pulse worker | `runtime/pulse_candidate_worker.py` | `pulse_candidates`, `pulse_agent_runs`, `pulse_agent_run_steps`, `pulse_candidates.decision_*` columns, `pulse_candidates.decision_json` | The only runtime writer of these tables. Runs as a normal `asyncio` task; listens to `token_radar_updated` for wake; runs `interval_seconds` catch-up. |
  | Audit ledger | `repositories/pulse_repository.py` | `pulse_agent_runs`, `pulse_agent_run_steps` | Every worker run writes one `pulse_agent_runs` row. Every Analyst / Critic / Judge stage, plus research-only short-circuits, writes one `pulse_agent_run_steps` row. `prompt_text` is operational audit data and must never contain secrets or credentials. |

  ## Public Decision Contract

  The product-facing decision payload (also documented in
  `../../../../docs/CONTRACTS.md`):

  ```json
  {
    "route": "meme | cex | research_only",
    "recommendation": "trade_candidate | token_watch | high_info_rejection | high_conviction | abstain",
    "confidence": 0.0,
    "abstain_reason": "string or null",
    "stage_count": 0,
    "summary_zh": "string",
    "invalidation_conditions": ["string"],
    "residual_risks": ["string"],
    "evidence_event_ids": ["event-id"]
  }
  ```

  - Default Signal Pulse listings hide rows where
    `decision.recommendation = "abstain"`. Abstain is decision semantics,
    not a `pulse_status`.
  - Rows with insufficient data return an abstain decision with the audit
    row written. No path may return a non-abstain decision without an audit
    row, and no path may invent a confidence or display status to avoid
    abstaining.

  ## Wake Channels

  | Channel | Direction | Counterpart |
  |---------|-----------|-------------|
  | `token_radar_updated` | listen | emitted by `TokenRadarProjectionWorker` after a successful window write |

  Pulse worker also runs `interval_seconds` catch-up so a missed
  `NOTIFY` cannot stall agent decisions.

  ## Provider Boundary

  - Only `integrations/openai_agents/` runs OpenAI Agents stages.
  - `domains/pulse_lab` may not import OpenAI primitives or any other
    concrete LLM client.
  - Composition lives in `app/runtime/providers_wiring.py`, which binds a
    concrete adapter to the `pulse_lab` provider protocol.

  ## Hard Boundaries

  - No fallback to legacy Signal Pulse `thesis_json`, `radar_score_json`,
    or `market_context_json`. Public Signal Pulse payloads expose
    `factor_snapshot`, `decision`, `gate`, and `fact_card`, not old
    score/thesis JSON fields.
  - No decision without an audit row.
  - Route policy is deterministic and config-driven; routes are not
    selected by the LLM.
  - `agent_brief` is a search-side payload, not a Pulse-side payload.
  - Pulse never writes `token_radar_rows`; that is
    `TokenRadarProjectionWorker`'s table.

  ## Update Triggers

  Update this file in the same change as any of:

  - Candidate gate inputs or thresholds.
  - Agent route values (`cex` / `meme` / `research_only`) or the policy
    that selects them.
  - Stage runtime interface (Analyst / Critic / Judge contract).
  - Decision payload schema or `recommendation` enum.
  - Audit ledger column shape.
  - Pulse worker wake channels or catch-up cadence.
  ````

- [ ] **Step 2:** Verify:

  ```bash
  test -f src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md
  rg -n "^# Pulse Lab Architecture$" src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md
  rg -n "token_radar_updated" src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md
  rg -n "abstain" src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md
  ```

  Expected: file exists; each `rg` emits at least one match.

- [ ] **Step 3:** Commit:

  ```bash
  git add src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md
  git commit -m "docs(pulse_lab): add module ARCHITECTURE.md"
  ```

---

## Task 6 — docs/WORKERS.md (new)

**Files:**
- Create: `docs/WORKERS.md`

- [ ] **Step 1:** Create the file with the exact content below:

  ````markdown
  # Workers

  > **Scope.** Cross-domain runtime worker inventory: each long-running
  > worker's fact writes, wake-in and wake-out channels, and catch-up
  > cadence. Domain stage maps live in each domain's `ARCHITECTURE.md`;
  > operational invariants live in `RELIABILITY.md`; the architecture
  > invariants this inventory implements live in `ARCHITECTURE.md`.

  Every worker listed here runs as an `asyncio.create_task` in
  `app/runtime/app.py`'s `_start_workers`. Wake mechanics flow through
  `app/runtime/wake_bus.py`. Worker correctness must not depend on
  `NOTIFY` delivery — every listener has a bounded `interval_seconds`
  catch-up.

  ## Worker Inventory

  | Worker | Owner | File | Reads | Writes | Wake-in | Wake-out | Catch-up |
  |--------|-------|------|-------|--------|---------|----------|----------|
  | `CollectorService` | `ingestion` | `domains/ingestion/runtime/collector_service.py` | GMGN public stream (WS) | none direct; calls `IngestService` per frame | provider-driven (WS) | none | continuous WS |
  | `IngestService` | `evidence` | `domains/evidence/services/ingest_service.py` | normalised frames | `events`, `event_entities`, `token_evidence`, `token_intents`, `token_intent_lookup_keys`, `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence`, `asset_identity_current` (single transaction) | per-frame call from collector | none | n/a (transactional, not a task) |
  | `AnchorPriceWorker` | `asset_market` | `domains/asset_market/runtime/anchor_price_worker.py` | pending intents, anchor providers | `price_observations(kind='event_anchor')` | poll | `market_observation_written` | `interval_seconds` |
  | `LivePriceGateway` | `asset_market` | `domains/asset_market/runtime/live_price_gateway.py` | OKX DEX WS, OKX CEX quote | `price_observations(kind='decision_latest')` (only when `should_persist_live_observation` returns `True`) | provider-driven (WS + poll) | `market_observation_written` (on persisted observation only) | continuous WS + provider poll |
  | `ResolutionRefreshWorker` | `asset_market` | `domains/asset_market/runtime/resolution_refresh_worker.py` | NIL / AMBIGUOUS lookup keys, OKX DEX discovery | refreshed `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence/current`, `token_discovery_results` | poll | `resolution_updated` | `interval_seconds` |
  | `AssetProfileRefreshWorker` | `asset_market` | `domains/asset_market/runtime/asset_profile_refresh_worker.py` | resolved DEX assets due for refresh, GMGN exact-token profile | `asset_profiles` | poll | none | `interval_seconds` |
  | `TokenRadarProjectionWorker` | `token_intel` | `domains/token_intel/runtime/token_radar_projection_worker.py` | facts via `token_radar_source_query`, `price_observations`, `asset_identity_current` | `token_radar_rows`, `projection_runs`, `projection_offsets`, `token_score_evaluations` | `market_observation_written`, `resolution_updated` | `token_radar_updated` | `interval_seconds` |
  | `PulseCandidateWorker` | `pulse_lab` | `domains/pulse_lab/runtime/pulse_candidate_worker.py` | `token_radar_rows` latest per target/window/scope, gate fields, route policy | `pulse_candidates`, `pulse_candidates.decision_*`, `pulse_candidates.decision_json`, `pulse_agent_runs`, `pulse_agent_run_steps` | `token_radar_updated` | none | `interval_seconds` |
  | `EnrichmentWorker` | `social_enrichment` | `domains/social_enrichment/runtime/enrichment_worker.py` | watched events queue, OpenAI Agents enrichment | enrichment label rows, `model_run` audit | poll | none | `interval_seconds` |
  | `HarnessOpsWorker` | `closed_loop_harness` | `domains/closed_loop_harness/runtime/harness_ops_worker.py` | due signal seeds, market observations | `asset_signal_snapshots`, `asset_signal_outcomes`, `pulse_playbook_snapshots`, `pulse_playbook_outcomes` | poll | none | `interval_seconds` |
  | `NotificationWorker` | `notifications` | `domains/notifications/runtime/notification_worker.py` | notification rules, candidate rows | notification rule evaluations | poll | none | `interval_seconds` |
  | `NotificationDeliveryWorker` | `notifications` | `domains/notifications/runtime/notification_delivery.py` | pending deliveries | delivery rows | poll | none | `interval_seconds` |

  `IngestService` is documented here because every other worker depends
  on the facts its transaction writes; it is not a long-running task
  itself.

  ## Wake Channels

  | Channel | Emitter | Listener | Hint payload |
  |---------|---------|----------|--------------|
  | `market_observation_written` | `AnchorPriceWorker`, `LivePriceGateway` | `TokenRadarProjectionWorker` | `{target_type, target_id}` |
  | `resolution_updated` | `ResolutionRefreshWorker` | `TokenRadarProjectionWorker` | `{lookup_keys: [...]}` |
  | `token_radar_updated` | `TokenRadarProjectionWorker` | `PulseCandidateWorker` | `{window, scope}` |

  Wake payloads are hints; consumers re-read DB on wake. Adding a new
  channel means adding a new method to `WakeBus` and a new branch to the
  consumer's `WakeListener` invocation.

  ## Lifecycle and Supervision

  - All workers expose `run()` and `stop()`.
  - `app/runtime/app.py._start_workers` constructs `WakeBus` and
    `WakeListener` once and injects them into workers that need them.
  - Workers are started as `asyncio.create_task(worker.run())`.
  - The runtime supervisor task watches worker tasks, logs cancellations,
    and triggers shutdown on unexpected exits.
  - On shutdown, the runtime calls `stop()` on each worker, then awaits
    the tasks.
  - `WakeBus` and `WakeListener` are the only places that own
    `LISTEN/NOTIFY` mechanics. Domain workers never call `pg_notify`
    directly.
  - Catch-up cadence defaults live in `platform/config/settings.py`.

  ## Adding a Worker

  When introducing a new worker, do all of the following in the same
  change:

  1. Implement the worker class with `run()` / `stop()` and accept the
     domain provider protocols plus an optional `WakeBus` /
     `WakeListener` by injection.
  2. Wire it in `app/runtime/app.py`: add a `<name>_worker` and
     `<name>_task` field on the runtime dataclass, construct in the
     wiring section, create the task in `_start_workers`, and cancel in
     the shutdown helper.
  3. Add a row to this file's worker inventory.
  4. Add or update the wake channels table here if the worker introduces
     a channel.
  5. Document the worker in the owning domain's `ARCHITECTURE.md` Stage
     Map.
  6. If the worker writes a new derived table, declare it as a read model
     and name its single writer (`Architecture Invariants` #4 in
     `ARCHITECTURE.md`).

  ## Update Triggers

  Update this file in the same change as any of:

  - A new worker class or removal of an existing one.
  - A worker gaining or losing a wake-in or wake-out channel.
  - A change to a catch-up cadence default.
  - A worker moving between domains.
  - A new `NOTIFY` channel name or hint payload shape.
  ````

- [ ] **Step 2:** Verify the inventory matches `app/runtime/app.py`'s worker task list. The expected workers are listed in `app.py`'s runtime dataclass under `*_task` fields.

  ```bash
  test -f docs/WORKERS.md
  rg -n "CollectorService|AnchorPriceWorker|LivePriceGateway|ResolutionRefreshWorker|AssetProfileRefreshWorker|TokenRadarProjectionWorker|PulseCandidateWorker|EnrichmentWorker|HarnessOpsWorker|NotificationWorker|NotificationDeliveryWorker" docs/WORKERS.md | wc -l
  rg -n "^\| `Collector|^\| `Ingest|^\| `Anchor|^\| `Live|^\| `Resolution|^\| `Asset|^\| `TokenRadar|^\| `PulseCandidate|^\| `Enrichment|^\| `HarnessOps|^\| `Notification" docs/WORKERS.md | wc -l
  ```

  Expected: first `rg` emits at least 11; second `rg` emits at least 12 (one per inventory row, including IngestService).

- [ ] **Step 3:** Cross-check the worker list against the source:

  ```bash
  rg -n "_task: asyncio\\.Task \\| None" src/gmgn_twitter_intel/app/runtime/app.py
  ```

  Expected: the `*_task` fields listed match the workers in the inventory (collector, supervisor, enrichment, harness_ops, notification, notification_delivery, anchor_price, asset_profile_refresh, resolution_refresh, live_price_gateway, token_radar_projection, pulse_candidate). `supervisor_task` is the runtime supervisor and is not a worker.

- [ ] **Step 4:** Commit:

  ```bash
  git add docs/WORKERS.md
  git commit -m "docs(workers): add cross-domain worker inventory"
  ```

---

## Task 7 — AGENTS.md and CLAUDE.md: Kappa/CQRS one-liner and WORKERS row

**Files:**
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1:** In `AGENTS.md`, locate the `What this is` section. The current paragraph reads:

  ```markdown
  ## What this is

  `gmgn-twitter-intel`: a single Python service that ingests GMGN's anonymous public WebSocket, extracts Twitter-mentioned crypto entities, scores them, and serves results over HTTP / WebSocket / CLI to a small React frontend. One PostgreSQL store. See `docs/ARCHITECTURE.md`.
  ```

  Replace with:

  ```markdown
  ## What this is

  `gmgn-twitter-intel`: a single Python service that ingests GMGN's anonymous public WebSocket, extracts Twitter-mentioned crypto entities, scores them, and serves results over HTTP / WebSocket / CLI to a small React frontend. One PostgreSQL store. See `docs/ARCHITECTURE.md`.

  The pipeline is Kappa/CQRS: PostgreSQL material facts (`events`,
  `token_intents`, `token_intent_resolutions`, `asset_identity_*`,
  `price_observations`) are the only business truth. Derived read models
  (`token_radar_rows`, `pulse_candidates`, ...) each have exactly one
  runtime writer and are rebuildable. `NOTIFY` is a wake hint; every
  listener re-reads DB and runs a bounded `interval_seconds` catch-up.
  Provider raw frames are inputs, not facts.
  ```

- [ ] **Step 2:** In `AGENTS.md`, locate the `Where to read what` table. Add two new rows (immediately after the `Operational invariants` row, before `Active / done specs & plans`):

  Current rows in that region:

  ```markdown
  | Operational invariants | `docs/RELIABILITY.md` |
  | Active / done specs & plans | `docs/superpowers/{specs,plans}/{active,completed}/` |
  ```

  Replace with:

  ```markdown
  | Operational invariants | `docs/RELIABILITY.md` |
  | Cross-domain worker inventory | `docs/WORKERS.md` |
  | Module architecture maps | `src/gmgn_twitter_intel/domains/<domain>/ARCHITECTURE.md` (currently `token_intel`, `asset_market`, `pulse_lab`) |
  | Active / done specs & plans | `docs/superpowers/{specs,plans}/{active,completed}/` |
  ```

- [ ] **Step 3:** In `CLAUDE.md`, apply the identical two edits as Steps 1 and 2 above. Both router files must mirror.

- [ ] **Step 4:** Verify both files match in the changed sections:

  ```bash
  diff <(sed -n '/^## What this is$/,/^## /p' AGENTS.md | sed '$d') <(sed -n '/^## What this is$/,/^## /p' CLAUDE.md | sed '$d')
  rg -n "Cross-domain worker inventory" AGENTS.md CLAUDE.md
  rg -n "Module architecture maps" AGENTS.md CLAUDE.md
  rg -n "Kappa/CQRS" AGENTS.md CLAUDE.md
  ```

  Expected: `diff` emits no output (the `What this is` blocks are identical); each `rg` emits two matches (one per file).

- [ ] **Step 5:** Commit:

  ```bash
  git add AGENTS.md CLAUDE.md
  git commit -m "docs(routers): name Kappa/CQRS pipeline and link WORKERS + module docs"
  ```

---

## Task 8 — Verification

**Files:**
- No new files. Run cross-checks and run the architecture test suite.

- [ ] **Step 1:** Confirm every claimed link target exists:

  ```bash
  test -f docs/ARCHITECTURE.md
  test -f docs/RELIABILITY.md
  test -f docs/TESTING.md
  test -f docs/WORKERS.md
  test -f docs/FRONTEND.md
  test -f docs/CONTRACTS.md
  test -f docs/WORKFLOW.md
  test -f docs/DESIGN_DISCIPLINE.md
  test -f AGENTS.md
  test -f CLAUDE.md
  test -f src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md
  test -f src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md
  test -f src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md
  ```

  Expected: every command exits 0.

- [ ] **Step 2:** Confirm no stale wording survives in updated docs:

  ```bash
  rg -n "web/src/test/" docs/TESTING.md
  rg -n "live_market comes from process-local gateway" docs/ARCHITECTURE.md src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md || true
  rg -n "anchor_price_usd|live_market_usd" docs/ARCHITECTURE.md docs/CONTRACTS.md docs/WORKERS.md src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md || true
  ```

  Expected: first command emits zero matches; second and third commands emit zero matches (or only inside fenced removed-name lists, which is allowed).

- [ ] **Step 3:** Confirm the architecture test suite still passes:

  ```bash
  uv run pytest tests/architecture/test_src_domain_architecture.py tests/integration/test_docs_generated.py -q
  ```

  Expected: pass with same counts as the pre-flight baseline.

- [ ] **Step 4:** Confirm full lint/test gate still passes:

  ```bash
  uv run ruff check .
  uv run pytest -q
  ```

  Expected: ruff clean; pytest counts unchanged from baseline (doc-only change).

- [ ] **Step 5:** Confirm `make check-all` exits 0:

  ```bash
  make check-all
  ```

  Expected: exit code 0. If a generated-doc cleanliness test trips because
  `docs/generated/*` is unchanged, the docs in this PR are not generated
  files and the assertion should remain clean.

- [ ] **Step 6:** Final cross-link audit:

  ```bash
  for f in docs/ARCHITECTURE.md docs/RELIABILITY.md docs/TESTING.md docs/WORKERS.md AGENTS.md CLAUDE.md src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md; do
    echo "=== $f ==="
    rg -n "ARCHITECTURE\.md|WORKERS\.md|RELIABILITY\.md|CONTRACTS\.md|FRONTEND\.md|TESTING\.md|WORKFLOW\.md|DESIGN_DISCIPLINE\.md" "$f" | head -20
  done
  ```

  Expected: every reference resolves to a file that exists in Step 1.

- [ ] **Step 7:** Create the verification artefact at
  `docs/superpowers/plans/active/2026-05-14-architecture-docs-kappa-cqrs-refresh-verification.md`
  using the project's verification template
  (`docs/superpowers/_templates/verification-template.md`). Paste the full
  `make check-all` output, the coverage line, the skipped-tests count, and a
  one-line note on which UI flows (none — docs only) were exercised
  manually.

- [ ] **Step 8:** Commit verification artefact:

  ```bash
  git add docs/superpowers/plans/active/2026-05-14-architecture-docs-kappa-cqrs-refresh-verification.md
  git commit -m "docs(verification): record architecture docs refresh verification"
  ```

---

## PR / Commit Breakdown

One hard cut. Use the per-task commits above for reviewability. Merge order
matches the task order. The branch is `codex/architecture-docs-kappa-cqrs-refresh`.

Eight commits total:

1. Task 1 — `docs(architecture): state Kappa/CQRS invariants and add module links`
2. Task 2 — `docs(reliability): add Kappa/CQRS operational invariants`
3. Task 3 — `docs(testing): align frontend test path with web/tests and link WORKERS`
4. Task 4 — `docs(asset_market): add module ARCHITECTURE.md`
5. Task 5 — `docs(pulse_lab): add module ARCHITECTURE.md`
6. Task 6 — `docs(workers): add cross-domain worker inventory`
7. Task 7 — `docs(routers): name Kappa/CQRS pipeline and link WORKERS + module docs`
8. Task 8 — `docs(verification): record architecture docs refresh verification`

## Rollout Order

This is documentation only. No service restart, no migrations, no runtime
state changes.

1. Merge the branch into `main` after verification artefact is recorded.
2. Move spec and plan to `docs/superpowers/specs/completed/` and
   `docs/superpowers/plans/completed/` in the same PR or an immediate
   follow-up commit on `main` per `WORKFLOW.md`.

## Rollback

Revert the merge commit. No state to restore.

## Acceptance Test Commands

- AC1 invariants visible:

  ```bash
  rg -n "^## Architecture Invariants \(Kappa/CQRS\)$" docs/ARCHITECTURE.md
  ```

  Expected: one match.

- AC2 module docs exist:

  ```bash
  test -f src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md
  test -f src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md
  ```

  Expected: both pass.

- AC3 worker inventory exists and covers all runtime workers:

  ```bash
  rg -n "^\| `[A-Z]" docs/WORKERS.md | wc -l
  ```

  Expected: at least 12 (one row per inventory entry).

- AC4 router files mirror:

  ```bash
  diff <(sed -n '/^## What this is$/,/^## /p' AGENTS.md | sed '$d') <(sed -n '/^## What this is$/,/^## /p' CLAUDE.md | sed '$d')
  ```

  Expected: no output.

- AC5 architecture tests pass:

  ```bash
  uv run pytest tests/architecture/test_src_domain_architecture.py tests/integration/test_docs_generated.py -q
  ```

  Expected: pass.

- AC6 full gate:

  ```bash
  make check-all
  ```

  Expected: exit code 0.
