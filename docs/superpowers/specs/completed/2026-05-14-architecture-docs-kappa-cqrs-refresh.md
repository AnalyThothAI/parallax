# Architecture Docs Refresh: Kappa/CQRS Alignment

> **Scope.** Refresh project-level architecture docs and add missing module-level
> docs so a fresh agent can read the docs alone and produce code that follows
> the Kappa/CQRS invariants that landed in the 2026-05-13 Token Radar hard cut,
> without needing chat history or the long plan artefact in
> `docs/superpowers/plans/`.

## Background

The 2026-05-13 hard cut
(`docs/superpowers/plans/active/2026-05-13-token-radar-kappa-cqrs-hard-cut-plan-cn.md`,
status Complete, merged 2026-05-13 16:54) re-architected Token Radar around
Kappa/CQRS principles:

- Material facts are the only business truth (`events`, `token_intents`,
  `token_intent_resolutions`, `asset_identity_*`, `price_observations`).
- Provider raw frames are inputs, not facts. A single value type
  `MarketObservation` plus `MarketContext{event_anchor, decision_latest,
  readiness}` is the only market fact contract.
- Read models (`token_radar_rows`, `pulse_candidates`) have exactly one runtime
  writer.
- Wake hints (`NOTIFY` channels: `market_observation_written`,
  `resolution_updated`, `token_radar_updated`) are hints; correctness comes
  from DB material facts plus periodic catch-up.
- Live observation persistence passes a budget policy
  (`first_seen | heartbeat | significant_price_change | gate_field_change |
  provider_state_change`) before a raw frame becomes a `decision_latest` fact.
- No runtime compatibility layer: `_overlay_live_market`,
  `token_market_price_baselines`, `liveMarketUpdates[0]`, and old
  `anchor_price` / `live_market` top-level fields are removed.

Several docs absorbed parts of this change, but the system-wide invariants and
the module-level details that an agent needs in order to extend the system
correctly are scattered or missing.

## Current State Audit

| Doc | Status | Gap |
|---|---|---|
| `docs/ARCHITECTURE.md` | partial | Has role markers, Pulse Agent Runtime, Asset Profile Facts; top data-flow omits `asset_market` lane; does not name `MarketObservation` / `MarketContext` / `WakeBus` / `WakeListener`; Kappa/CQRS invariants are not stated as invariants |
| `src/parallax/domains/token_intel/ARCHITECTURE.md` | current | Already states `event_anchor` / `decision_latest` / `readiness` / single-writer / wake-not-truth |
| `docs/CONTRACTS.md` | current | Token Radar `market` block, `live_market_update` payload, profile/search inspect contracts already aligned |
| `docs/FRONTEND.md` | current | Layer map and conventions already reflect the post-hard-cut frontend |
| `AGENTS.md` / `CLAUDE.md` | outdated | One-line system description does not name Kappa/CQRS; an agent reading only the router cannot infer facts → projection → read model → surfaces |
| `docs/RELIABILITY.md` | outdated | Lacks write budget, wake-not-truth + catch-up cadence, one-writer-per-read-model, provider connection state observability, snapshot gate outcomes |
| `docs/TESTING.md` | drift | Says frontend tests live in `web/src/test/`; `docs/FRONTEND.md` and the production source say `web/tests/` |
| `src/parallax/domains/asset_market/ARCHITECTURE.md` | missing | Hosts four runtime workers, the `MarketObservation` types, the write budget policy, the identity-evidence ledger; no module map exists |
| `src/parallax/domains/pulse_lab/ARCHITECTURE.md` | missing | Signal Pulse pipeline (factor snapshot → candidate gate → agent route → decision → audit ledger) is split across CONTRACTS, token_intel module doc, and RELIABILITY |
| Cross-domain worker inventory | missing | No single doc lists each worker's fact writes, wake-in channels, wake-out channels, catch-up cadence; an agent has to read 11 worker classes to get the runtime picture |

## Goal

A fresh agent that reads only `AGENTS.md` (or `CLAUDE.md`),
`docs/ARCHITECTURE.md`, the relevant module `ARCHITECTURE.md`,
`docs/RELIABILITY.md`, `docs/WORKERS.md`, and `docs/CONTRACTS.md` can correctly
answer the following without inspecting the long hard-cut plan or running grep:

1. Which tables are business facts and which are derived read models.
2. Which worker is the only runtime writer of each derived read model.
3. What value type represents a market observation, and which two time roles it
   may take.
4. When a raw provider frame is allowed to become a persisted observation.
5. Which `NOTIFY` channels exist, which worker emits them, which worker
   consumes them, and what the catch-up cadence is if a `NOTIFY` is dropped.
6. Which surfaces are allowed to call providers vs. read persisted facts.
7. How the Pulse Agent route policy and audit ledger work, and what the
   abstain decision contract is.

The metric is falsifiable: pick one of the seven questions, hand the docs to a
fresh agent, ask the question, and verify the agent answers correctly from the
docs alone.

## First Principles

- A router file (`AGENTS.md`, `CLAUDE.md`) routes; it does not state
  architecture invariants. The invariants live in `ARCHITECTURE.md`. Router
  files name the main system shape in one sentence so agents do not start from
  a blank slate.
- Global `ARCHITECTURE.md` owns invariants and the cross-domain map. It must
  not duplicate module internals.
- Each domain `ARCHITECTURE.md` owns its stage map, contracts that only its
  code can produce, and the boundaries that its surfaces must respect.
- `WORKERS.md` is the runtime inventory. Workers cross domains, so it lives at
  the project level, not under any one domain. Each row is a pointer to the
  worker class; the doc itself is not the source of truth for any worker's
  behaviour.
- `RELIABILITY.md` owns operational invariants (what must hold in production),
  not architectural invariants. The two have different audiences: deploy/ops
  vs. write-code.

## Architecture Invariants (Kappa/CQRS)

These nine invariants are the canonical re-statement of the hard cut's
`DG1`–`DG9`. They go into `docs/ARCHITECTURE.md` as a top-level section called
**`Architecture Invariants (Kappa/CQRS)`**, placed immediately after the scope
sentence and before `Package Roots`.

Each invariant is one sentence agents can apply when writing or reviewing code.

1. **Facts-first persistence.** `events`, `event_entities`, `token_evidence`,
   `token_intents`, `token_intent_lookup_keys`, `token_intent_resolutions`,
   `registry_assets`, `asset_identity_evidence`, `asset_identity_current`, and
   `price_observations` are the business fact tables. Every other persisted
   table is a derived read model that can be rebuilt from these facts.
2. **One material market fact type.** Market data from any provider is
   normalised into a `MarketObservation` (value type in
   `domains/asset_market/types/market_observation.py`) before persistence;
   provider raw frames are inputs, not facts.
3. **Two market time roles.** `MarketContext.event_anchor` serves event-time
   and back-testing; `MarketContext.decision_latest` serves current decision,
   UI, and Signal Pulse. The two roles are persisted in distinct partitions
   (`observation_kind`) of `price_observations` and must never overwrite each
   other.
4. **One writer per read model.** Each derived read model has exactly one
   runtime writer: `token_radar_rows` is written only by
   `TokenRadarProjectionWorker`; `pulse_candidates`, `pulse_agent_runs`,
   `pulse_agent_run_steps` are written only by `PulseCandidateWorker`. New read
   models must declare their single writer in the module doc.
5. **Wake is not truth.** PostgreSQL `NOTIFY` channels
   (`market_observation_written`, `resolution_updated`,
   `token_radar_updated`) carry hint payloads only; consumers re-read DB on
   wake. Every listener must have an `interval_seconds` catch-up so a missed
   `NOTIFY` cannot stall the pipeline.
6. **No runtime compatibility layer.** Hard cuts delete the old runtime path.
   No `_overlay_*`, no `fallback_to_v2_snapshot`, no "if missing fall back to
   the old field". Migration code and rollback docs may reference removed
   names; runtime, public API, and frontend code may not.
7. **Material observation write budget.** `LivePriceGateway` persists a
   `decision_latest` row only when `should_persist_live_observation` returns
   `True` (`first_seen` / `heartbeat` / `significant_price_change` /
   `gate_field_change` / `provider_state_change`). Every other valid frame
   updates the in-process cache and may fan out over WS, but it does not
   become a fact.
8. **Observable IO state.** Each WS provider exposes a connection state
   (`disconnected | connecting | authenticating | subscribed | streaming |
   failed`) with a `last_state_change_at_ms`. The snapshot gate exposes outcome
   counters (`immediate_complete | debounced_complete | debounced_timeout |
   non_tw_channel`). Both surface through `/api/status`.
9. **Audit ledger truth.** Every Signal Pulse decision must be replayable
   from `pulse_agent_runs` and `pulse_agent_run_steps`. Insufficient data
   finishes as an abstain decision with the audit row written; no path may
   return a decision without an audit row, and no path may invent a confidence
   or display status to avoid abstaining.

## Target Doc Ownership

| Doc | Owns | Does not own |
|---|---|---|
| `AGENTS.md` / `CLAUDE.md` | One-sentence system description naming Kappa/CQRS; router table | Invariants, module contracts |
| `docs/ARCHITECTURE.md` | Architecture invariants, package roots, dependency direction, domain map, conceptual data-flow, role markers, asset profile facts lane, link table to module docs | Per-module stage maps, worker internals, public payload shapes |
| `docs/CONTRACTS.md` | HTTP, WebSocket, CLI, config public payload shapes | Internal types, worker behaviour |
| `docs/FRONTEND.md` | `web/` layer map, conventions, test layout, UI verification gate | Backend contracts |
| `docs/RELIABILITY.md` | Operational invariants: single-worker, foreground-only, docker state, coverage label, MCP boundary, Pulse audit ledger, **new:** write budget, wake-not-truth + catch-up, one-writer-per-read-model, provider state observability, snapshot gate outcomes | Architectural invariants |
| `docs/TESTING.md` | Test rules, completion gate command, verification artefact requirement | Test inventory, fixture layout |
| `docs/WORKFLOW.md` | Lane sequence, worktree policy, completion gates | Doc content |
| `docs/DESIGN_DISCIPLINE.md` | Spec vs plan boundary, audit-before-design, reuse-before-create, scoring rules | Lane mechanics |
| `docs/WORKERS.md` (new) | Cross-domain worker inventory table; lifecycle and supervision patterns | Per-worker behaviour (link to module doc and code) |
| `docs/SETUP.md` | Install, run, docker | Architecture |
| `docs/SECURITY.md` | Secret handling, authn changes | Architecture |
| `domains/token_intel/ARCHITECTURE.md` | Token Radar stage map, factor snapshot contract, identity boundary, hard boundaries | Provider details, Signal Pulse runtime, asset profile internals |
| `domains/asset_market/ARCHITECTURE.md` (new) | Asset identity evidence ledger, anchor/live/profile/discovery worker stage maps, `MarketObservation`/`MarketContext` schema, material observation persistence policy, provider capability model | Token Radar projection, Pulse runtime |
| `domains/pulse_lab/ARCHITECTURE.md` (new) | Pulse candidate gate, agent route policy, stage runtime, decision persistence, audit ledger semantics, abstain contract | Token Radar projection, asset market internals |

## docs/ARCHITECTURE.md Changes

Re-organise as follows; existing prose stays when it already matches.

1. Keep the existing scope sentence.
2. New section **`Architecture Invariants (Kappa/CQRS)`** between scope and
   `Package Roots`, containing the nine invariants above as a numbered list.
3. Existing data-flow diagram (`GMGN public stream → domains/ingestion → ...`)
   must include `domains/asset_market` as an explicit lane that runs in
   parallel to `domains/token_intel`, because `asset_market` writes the
   `event_anchor` / `decision_latest` facts that Token Radar projection reads:

   ```
   GMGN public stream
     → domains/ingestion
     → domains/evidence
         ├─ domains/asset_market (identity / anchor / live / profile / discovery)
         └─ domains/token_intel (projection + scoring + read models)
     → domains/social_enrichment
     → domains/closed_loop_harness
     → domains/notifications and domains/pulse_lab
     → app/surfaces/api + app/surfaces/cli
   ```

4. `Package Roots`, `Role Markers`, `Domains` tables stay. Name
   `MarketObservation` / `MarketContext` / `MarketReadiness` in the
   `domains/asset_market` row of the `Domains` table (cross-domain value
   types). Name `WakeBus` / `WakeListener` in the `app/runtime` row of the
   `Package Roots` table (composition-root primitives). These are descriptive
   mentions, not new role markers.
5. `Module Architecture Documents` table gains two rows linking to the new
   `asset_market` and `pulse_lab` module docs.
6. `Pulse Agent Runtime` section stays where it is, with a forward link to
   `domains/pulse_lab/ARCHITECTURE.md`.
7. `Asset Profile Facts` section stays where it is, with a forward link to
   `domains/asset_market/ARCHITECTURE.md`.

## docs/RELIABILITY.md Changes

Add five operational invariants after the existing `Pulse Agent Audit Ledger`
section:

- **Material observation write budget.** Live market frames are persisted only
  through `should_persist_live_observation`; the synthetic flat-market budget
  is `100 targets × 5 fps × 10 minutes → ≤ 1500 persisted rows` and is
  guarded by `tests/benchmark/test_live_observation_write_budget.py`.
- **Wake hints and catch-up.** Every listener
  (`TokenRadarProjectionWorker`, `PulseCandidateWorker`, etc.) must run on a
  bounded `interval_seconds` even when `NOTIFY` is healthy. A dropped
  `NOTIFY` recovers on the next interval; service correctness must not
  depend on `NOTIFY` delivery.
- **One writer per read model.** A second runtime writer of any
  `token_radar_rows`, `pulse_candidates`, or future read model is a
  reliability incident and an architecture-test violation; ops paths and
  CLI rebuilds are explicit exceptions and must call the same projection
  service the worker uses.
- **Provider connection state.** OKX DEX WS, GMGN direct WS, and any future
  streaming provider must expose state transitions on the supervisor and
  through `/api/status`. Workers must treat
  `provider_state_change=true` as a `first_seen`-equivalent budget trigger.
- **Snapshot gate observability.** `CollectorService` exposes
  `immediate_complete`, `debounced_complete`, `debounced_timeout`, and
  `non_tw_channel` counters via `/api/status`. A non-trivial
  `debounced_timeout` rate is a reliability signal even when ingest looks
  healthy.

## docs/TESTING.md Changes

Two edits:

- Replace `web/src/test/` references with `web/tests/` to align with
  `docs/FRONTEND.md` and current source layout.
- Add a one-line note that the cross-domain worker inventory lives in
  `docs/WORKERS.md`; new worker tests should keep their module path mirrored
  there.

## AGENTS.md / CLAUDE.md Changes

The `What this is` paragraph must add one Kappa/CQRS sentence after the
existing description, naming facts → projection → read model → surfaces and
wake-not-truth. Example shape (final wording lives in the plan):

> The pipeline is Kappa/CQRS: material facts in PostgreSQL are the only
> business truth; derived read models (Token Radar rows, Signal Pulse
> candidates, etc.) have exactly one runtime writer and are rebuildable;
> wake hints (`NOTIFY`) only nudge consumers, which always re-read DB and
> run a bounded catch-up loop.

The `Where to read what` table gets a row pointing at `docs/WORKERS.md`. Both
router files must change in lock-step.

## docs/WORKERS.md (new)

### Section 1 — Worker Inventory

Single table whose rows correspond to runtime worker classes. Columns:

| Column | Meaning |
|---|---|
| Worker | Class name |
| Owner | Domain package |
| File | Path to the worker class |
| Reads | Tables / read models / providers consumed (semantic, not SQL) |
| Writes | Tables / read models written (a worker may write zero — e.g. collector) |
| Wake-in | `NOTIFY` channels listened to, or `poll-only`, or `provider-driven` |
| Wake-out | `NOTIFY` channels emitted, or `none` |
| Catch-up cadence | `interval_seconds` setting or `continuous` |

The set of rows is fixed by the current `app/runtime/app.py` task list (one
row per `*_task` field):

`CollectorService`, `IngestService` (transactional, not a long-running worker
but documented because every other worker depends on the facts it writes),
`AnchorPriceWorker`, `LivePriceGateway`, `ResolutionRefreshWorker`,
`AssetProfileRefreshWorker`, `TokenRadarProjectionWorker`,
`PulseCandidateWorker`, `EnrichmentWorker`, `HarnessOpsWorker`,
`NotificationWorker`, `NotificationDeliveryWorker`.

### Section 2 — Lifecycle and Supervision

Short prose covering:

- All workers run as `asyncio.create_task` in `app/runtime/app.py`'s
  `_start_workers`.
- Workers expose `run()` and `stop()`; the supervisor cancels and joins on
  shutdown.
- `WakeBus` is constructed once in `app/runtime` and injected into workers;
  domain code uses `WakeBus` / `WakeListener` and never opens `LISTEN`
  connections directly.
- Catch-up cadence is configured per worker; defaults live in
  `platform/config/settings.py`.
- A worker that needs to wake another worker calls a `WakeBus.notify_*`
  method named after the channel; new channels are added as new methods, not
  ad-hoc `pg_notify` calls.
- New workers must be added to this inventory, to `app.py` task list, and to
  the relevant domain `ARCHITECTURE.md` in the same change.

### Section 3 — Update Triggers

This file must be updated in the same change as any of:

- A new worker class.
- A worker gaining or losing a wake-in or wake-out channel.
- A change to a catch-up cadence default.
- A worker moving between domains.

## domains/asset_market/ARCHITECTURE.md (new)

Mirror the structure of `domains/token_intel/ARCHITECTURE.md`. Sections:

1. **Scope.** Asset identity, market observations, and asset profile facts.
   Link out to `../token_intel/ARCHITECTURE.md` for projection and
   `../../../../docs/CONTRACTS.md` for public payloads.
2. **Stage Map.** Table with Stage / Code owner / Persisted facts / Invariant:
   - Asset identity evidence (Tweet CA mentions, GMGN payload identity, OKX
     symbol candidates, OKX exact address) → `asset_identity_evidence`,
     `asset_identity_current`.
   - Anchor market observation → `price_observations(kind=event_anchor)`.
   - Live market observation → `price_observations(kind=decision_latest)`,
     subject to the material persistence policy.
   - Asset profile refresh → `asset_profiles`.
   - Resolution refresh and discovery → updated `token_intent_resolutions`
     and `registry_assets`, plus a `resolution_updated` wake notification.
3. **MarketObservation / MarketContext schema.** Frozen dataclass field list
   with semantics (not the literal class source). Note `raw_payload_hash`
   discipline (no raw payload in the dataclass).
4. **Material Observation Persistence Policy.** Five rules
   (`first_seen | heartbeat | significant_price_change | gate_field_change |
   provider_state_change`) and the write-budget target from the hard cut.
5. **Provider Capability Model.** `MarketCapability` enum semantics,
   `ProviderHealth` shape, the rule that provider health reports configured
   capabilities only.
6. **Hard Boundaries.** Provider raw frames never reach `factor_snapshot`;
   identity evidence never reaches scoring; CLI ops are the only place that
   may instantiate concrete provider clients outside `app/runtime`.
7. **Update Triggers.** When any of the above moves, update this file.

## domains/pulse_lab/ARCHITECTURE.md (new)

Same skeleton as the asset_market doc. Sections:

1. **Scope.** Signal Pulse: turning Token Radar projection rows into agent
   decisions; owning candidate selection, route policy, stage runtime,
   decision persistence, and the audit ledger.
2. **Stage Map.** Stage / Code owner / Persisted facts / Invariant:
   - Candidate gate (`pulse_candidate_gate.py`) → admission decision; reads
     `factor_snapshot_json.market.decision_latest`,
     `normalization.cohort_status`, and gate fields.
   - Route policy (`agent_routing.py`) → `cex | meme | research_only`
     decision and completeness gates.
   - Stage runtime (`integrations/openai_agents/`) → Analyst / Critic / Judge
     stages with typed outputs.
   - Decision persistence (`pulse_repository.py`) → `pulse_candidates`,
     `decision_*` columns, `decision_json`.
   - Audit ledger → `pulse_agent_runs`, `pulse_agent_run_steps`.
3. **Public Decision Contract.** Re-state the `decision` block shape from
   `docs/CONTRACTS.md` semantics (`route`, `recommendation`, `confidence`,
   `abstain_reason`, `stage_count`, `summary_zh`, `invalidation_conditions`,
   `residual_risks`, `evidence_event_ids`). Abstain is decision semantics,
   not a pulse status.
4. **Provider Boundary.** Only `integrations/openai_agents/` runs OpenAI
   Agents stages; `domains/pulse_lab` may not import OpenAI primitives.
   Composition lives in `app/runtime/providers_wiring.py`.
5. **Hard Boundaries.** No fallback to legacy `thesis_json`,
   `radar_score_json`, or `market_context_json`; no decision without an
   audit row; route policy is deterministic and config-driven; `agent_brief`
   is search-side, not pulse-side.
6. **Update Triggers.** When candidate gate, route policy, stage runtime,
   decision schema, or audit ledger shape moves, update this file.

## Out of Scope

- `docs/generated/*` — regenerated by `make docs-generated`; not touched.
- Module ARCHITECTURE.md files for `evidence`, `ingestion`, `notifications`,
  `closed_loop_harness`, `social_enrichment`, `account_quality` — out of
  scope until a future round; their stage descriptions remain in the global
  ARCHITECTURE.md Domains table.
- Frontend architecture refresh — `docs/FRONTEND.md` is current.
- CONTRACTS.md edits — current; future contract changes follow the existing
  versioned-spec rule.
- Code changes (other than docstrings co-located with new docs, if any) — the
  hard cut shipped; this round is documentation only.
- Translation of existing CN specs — out of scope.

## Risks

- **Doc drift between router and ARCHITECTURE.md.** Mitigated by the existing
  "mirror AGENTS.md and CLAUDE.md when one changes" rule; the new Kappa/CQRS
  sentence applies the same rule.
- **Module doc duplication.** Mitigated by the doc-ownership table: anything
  that exists in `docs/CONTRACTS.md` or `docs/ARCHITECTURE.md` is linked, not
  re-stated, in module docs.
- **Worker inventory rot.** `docs/WORKERS.md` becomes the single place that
  must change with every worker change. Mitigated by the explicit Update
  Triggers section and by adding the doc to the lint or architecture test
  that already runs on PR (out of scope for this spec; recorded as a
  follow-up).

## Evolution Path

- After this refresh ships, the architecture tests
  (`tests/architecture/test_src_domain_architecture.py`) gain one additional
  assertion: every worker present in `app/runtime/app.py`'s task list is
  listed in `docs/WORKERS.md`. This is a future ticket, not part of this
  spec.
- A later round can add module ARCHITECTURE.md files for the remaining
  domains (`evidence`, `ingestion`, `notifications`,
  `closed_loop_harness`, `social_enrichment`, `account_quality`) once a
  recurring need shows up.

## Update Triggers

Update this spec only if the docs refresh itself is re-scoped (e.g., user
asks to also rewrite CONTRACTS or to delay the module docs). Otherwise the
spec stays as-is and the implementation plan tracks deviations.
