# Architecture

> **Scope.** Owns Python-service package boundaries, dependency direction, and conceptual data flow for `gmgn-twitter-intel`. Frontend (`web/`) architecture lives in `FRONTEND.md`. Public interface contracts live in `CONTRACTS.md`.

The service is organised around domain packages, explicit integration adapters, platform infrastructure, and app surfaces. Boundaries are mechanically enforced by `tests/architecture/test_src_domain_architecture.py` and `tests/architecture/test_project_structure.py::test_project_uses_domain_package_src_layout`.

```
GMGN public stream
  → domains/ingestion           (raw frame normalisation, snapshot gate)
  → domains/evidence            (transactional facts: events, evidence, intents, resolutions, asset identity)
  → domains/asset_market        (market tick capture, capture-tier projection, profile refresh/current projection, discovery)
  → domains/token_intel         (Token Radar current-row publication, scoring, search read model)
  → domains/narrative_intel     (per-mention semantics and token discussion digests)
  → domains/social_enrichment   (watched-event extraction)
  → domains/pulse_lab           (candidate gate, agent route, decision, audit ledger)
  → domains/watchlist_intel     (handle timeline read model and account topic summaries)
  → domains/news_intel          (configured news ingestion, news facts, story and page read models)
  → domains/equity_event_intel  (SEC/IR/company-event facts, calendar, cited briefs, earnings page read models)
  → domains/cex_market_intel    (centralized exchange derivative radar read models)
  → domains/macro_intel         (macro observation facts and regime view snapshots)
  → domains/notifications       (rules, delivery)
  → app/surfaces/api + app/surfaces/cli
```

Macro intelligence has a normal runtime fact-ingest lane. `macro_sync` claims
bounded date windows in PostgreSQL before provider IO, runs the packaged
`macrodata-cli` executable from the installed image, and writes
`macro_observations`, `macro_import_runs`, `macro_sync_windows`, and
`macro_sync_runs`. The Docker image installs `macrodata-cli` from its versioned
Git source (`v0.1.5`) and uses its `macrodata` executable; runtime must not use
`uv run` or depend on a host-local checkout path.

```text
macro_sync windows
  -> packaged macrodata bundle history macro-core
  -> macro_observations / macro_import_runs / macro_sync_runs
  -> wake hint
  -> macro_view_projection
  -> feature engine and regime state machine
  -> macro_regime_v4 in macro_view_snapshots
  -> /api/macro
  -> web /macro
```

`macro import-bundle` remains an offline replay/seed tool for saved
macrodata envelopes; it is not the normal freshness path. `macro sync` is an
operator-triggered execution of the same sync service used by `macro_sync`.
`macro_regime_v4` readiness requires both latest coverage and required history
coverage; one-point history is projected as `partial` with structured gaps
rather than `ready`.

This repository is the system of record for agent work: if a production
decision changes, update the nearest architecture / contract / reliability
document in the same change. A fresh agent must not need chat history to know
where token identity is extracted, resolved, refreshed, scored, and served.

Worker runtime inventory is not inferred from `workers.yaml` or factory
registries. `WorkerManifest v1` (`app/runtime/worker_manifest.py`) is the only
source for worker existence, lane, kind, class path, start priority, queue-depth
ownership, idempotency evidence, side-effect ledger evidence, and wake
contracts. `workers.yaml` supplies runtime knobs for manifest workers only and
unknown worker keys fail startup.

## Architecture Invariants (Kappa/CQRS)

These eleven invariants govern how data flows through the service. Code that
violates them is wrong even if tests pass; tests that depend on a violation
are wrong too.

1. **Facts-first persistence.** `events`, `event_entities`, `token_evidence`,
   `token_intents`, `token_intent_lookup_keys`, `token_intent_resolutions`,
   `registry_assets`, `asset_identity_evidence`, `asset_identity_current`,
   `market_ticks`, `enriched_events`, `news_provider_items`, `news_items`,
   `news_item_entities`, `news_token_mentions`, `news_fact_candidates`,
   `equity_event_sources`, `equity_expected_events`,
   `equity_provider_documents`, `equity_event_documents`,
   `equity_company_events`, `equity_event_source_spans`,
   `equity_event_fact_candidates`, and `macro_observations` are
   the business fact tables. Control plane tables such as
   `event_anchor_backfill_jobs`, `pulse_trigger_dirty_targets`,
   `narrative_admission_dirty_targets`, `discussion_digest_dirty_targets`,
   `token_profile_current_dirty_targets`, `token_image_source_dirty_targets`,
   `asset_profile_refresh_targets`, `token_capture_tier_dirty_targets`, and
   `news_fetch_runs` own worker scheduling state and are not product truth.
   `macro_import_runs`, `macro_sync_windows`, `macro_sync_runs`,
   `macro_projection_dirty_targets`, and notification delivery rows record
   importer/sync, projection scheduling, or side-effect control state; macro
   product state still rebuilds from `macro_observations`. Every derived read
   model can be rebuilt from the facts.
2. **Append-only market tick facts.** Market data from any provider is
   normalised into `MarketTick`
   (`domains/asset_market/types/market_tick.py`) before persistence.
   `market_ticks` are append-only provider tick facts; provider raw frames
   are inputs, not facts.
3. **Event projections are committed with events.** `enriched_events` rows
   are event projection rows committed in the same ingest transaction as
   `events`. Inline ingest capture writes Tier 3 `market_ticks` and the
   corresponding enriched event rows; when an event anchor is missing, ingest
   enqueues a short-lived `event_anchor_backfill_jobs` control-plane row.
   Downstream readers do not reconstruct event market context from provider
   frames or worker job state.
4. **Public event token mentions are projections.** HTTP recent, WebSocket
   replay/live event payloads, and watchlist timelines read token mentions
   through the shared event-token projection over `token_intent_resolutions`,
   identity tables, `enriched_events`, and `market_ticks`. Public payloads do
   not return raw resolution fact rows.
5. **One writer per read model.** Each derived read model has exactly one
   runtime writer: `token_radar_current_rows`,
   `token_radar_publication_state`, `token_radar_rank_source_events`,
   `token_radar_target_features`, and `token_radar_target_first_seen` are
   written only by `TokenRadarProjectionWorker`; Token Radar online serving
   reads only `token_radar_current_rows` plus
   `token_radar_publication_state`. `token_radar_rank_source_events` is lazy
   evidence/detail, not leaderboard service. `token_radar_target_features` is
   projection-private intermediate state, not an API, CLI, Pulse,
   notification, or repair read path. `token_radar_current_rows` stores scalar
   `rank_score`, `quality_status`, `degraded_reasons_json`, and
   `factor_snapshot_json`; legacy top-level `asset_json`,
   `primary_venue_json`, `target_json`, `attention_json`, `market_json`,
   `price_json`, and `score_json` blocks are not a live contract. Retired
   `token_radar_rank_history`, `token_radar_snapshot_audit`, and
   `token_radar_projection_coverage` do not participate in online service.
   `token_capture_tier` is written only by
   `TokenCaptureTierWorker`; `pulse_agent_jobs`, `pulse_candidate_edge_state`,
   `pulse_candidate_run_budget`, `pulse_target_run_budget`,
   `pulse_agent_runs`, `pulse_agent_run_steps`,
   `pulse_agent_runtime_versions`, `pulse_agent_eval_cases`,
   `pulse_agent_eval_results`, `pulse_candidates`, and
   `pulse_playbook_snapshots` are written only by `PulseCandidateWorker`.
   `narrative_admissions` is written only by `NarrativeAdmissionWorker`;
   `token_mention_semantics` is written only by `MentionSemanticsWorker`;
   `token_discussion_digests` is written only by
   `TokenDiscussionDigestWorker`. New
   read models must declare their single writer in the owning module's
   ARCHITECTURE.md. `token_profile_current` is written only by
   `TokenProfileCurrentWorker`; it may expose token logos only from ready
   local rows in `token_image_assets`. `news_story_groups` and `news_story_members`
   are written only by `NewsStoryProjectionWorker`;
   `news_items.content_class`, `news_items.content_tags_json`, and
   `news_items.content_classification_json` are written by
   `NewsItemProcessWorker` as item-level material facts;
   `news_item_agent_runs` and `news_item_agent_briefs` are written only by
   `NewsItemBriefWorker`; `news_page_rows` is written only by
   `NewsPageProjectionWorker`; `news_source_quality_rows` is written only by
   `NewsSourceQualityProjectionWorker`. `cex_oi_radar_rows`,
   `cex_oi_radar_publication_state`, and `cex_detail_snapshots` are written
   only by `CexOiRadarBoardWorker`;
   `equity_event_story_groups` and `equity_event_story_members` are written
   only by `EquityEventStoryProjectionWorker`;
   `equity_event_agent_runs` and `equity_event_agent_briefs` are written only
   by `EquityEventBriefWorker`;
   `equity_event_page_rows`, `equity_event_calendar_rows`,
   `equity_event_alert_candidates`, and `equity_company_timeline_rows` are
   written only by `EquityEventPageProjectionWorker`;
   `macro_observation_series_rows` and `macro_view_snapshots` are written only
   by `MacroViewProjectionWorker`.
   Single writer is necessary but not sufficient for runtime safety. A current
   read model must also have a bounded physical lifecycle: row count must be
   proportional to product cardinality and active windows, not to worker run
   count, wake count, retry count, or wall-clock uptime. Serving primary keys
   for current read models must not include `generation_id`, `run_id`,
   `attempt_id`, timestamp-derived ids, or UUIDs. Those identities are allowed
   only in audit/control ledgers with explicit retention or in short
   transaction staging that is not a public serving contract. Active pointers
   hide old generations from readers; they do not make the storage, indexes,
   planner statistics, autovacuum work, or replication/WAL pressure bounded.
   Current-row projections must expose an observable unchanged path: when the
   source signature or dirty-target content did not change, the worker updates
   publication state at most and writes zero serving rows. Use `payload_hash`
   or `IS DISTINCT FROM` gates; do not delete/reinsert unchanged current rows.
6. **Wake is not truth.** PostgreSQL `NOTIFY` channels
   (`market_tick_written`, `market_tick_current_updated`,
   `resolution_updated`, `token_radar_updated`) carry hint payloads only;
   consumers re-read DB on wake. Market tick writers wake
   `MarketTickCurrentProjectionWorker`, which emits
   `market_tick_current_updated` after `market_tick_current` changes; Token
   Radar listens to that current-ready channel. Every listener must have a
   bounded `interval_seconds` loop that re-reads durable queues or bounded
   read models so a missed `NOTIFY` cannot stall the pipeline. Runtime workers
   must not compensate for missed wakes by scanning large fact windows; missed
   enqueue recovery belongs to explicit bounded ops repair commands that
   enqueue control rows only.
7. **No runtime compatibility layer.** Hard cuts delete the old runtime
   path. No `_overlay_*`, no `fallback_to_v2_snapshot`, no "if missing fall
   back to the old field". Migration code and rollback docs may reference
   removed names; runtime, public API, and frontend code may not.
8. **Capture lanes own market persistence.** `MarketTickStreamWorker` writes
   Tier 1 WebSocket ticks, `MarketTickPollWorker` writes Tier 2 REST ticks,
   and ingest inline capture writes Tier 3 ticks. `LivePriceGateway` is
   cache/publish only; it never writes market facts.
9. **Observable IO state.** Each WS provider exposes a connection state
   (`disconnected | connecting | authenticating | subscribed | streaming |
   failed`) with a `last_state_change_at_ms`. The snapshot gate exposes
   outcome counters (`immediate_complete | debounced_complete |
   debounced_timeout | non_tw_channel`). Both surface through
   `/api/status`.
10. **Audit ledger truth.** Every Signal Pulse decision must be replayable
   from `pulse_agent_runs` and `pulse_agent_run_steps`. Insufficient data
   finishes as an abstain decision with the audit row written; no path may
   return a decision without an audit row, and no path may invent a
   confidence or display status to avoid abstaining.
11. **Agent execution is an operational plane, not product truth.**
   `AgentExecutionGateway` owns OpenAI Agents SDK execution mechanics:
   runner construction, structured-output strategy selection, trace
   metadata, usage, safety-net fallback, lane bulkheads, rate limits,
   timeouts, circuit breakers, reservation, and request/result audit
   envelopes. Model capability adaptation belongs here: domains submit
   stage specs with Pydantic output types and never branch on provider,
   model, or response format. Domain
   workers still own admission, claim, retry, finalize, read-model writes,
   and business validation. There is no central durable `agent_tasks`
   queue; PostgreSQL domain facts and read models remain the truth. Pulse
   multi-stage runs use `pulse.pipeline` as a parent reservation. Every
   LLM-backed worker that can burn business attempts reserves lane capacity,
   circuit, and RPM before durable queue claim; batch workers request explicit
   `rate_units` for the maximum provider calls they want to execute and claim
   only the actual `reservation.rate_units` returned by the gateway. Pulse
   parent reservations also reserve child lane capacity/RPM before job claim.
   No-start backpressure does not claim work, write business run ledgers, or
   burn provider attempts. Provider-started validation/publication failures
   write the domain run ledger with `execution_started=true`. Lane `priority`
   is an operator-facing policy label rather than a strict scheduler.

Cross-cutting primitives that implement these invariants:

- `MarketTick` — value type in
  `domains/asset_market/types/market_tick.py`; the append-only provider
  tick fact contract across domains.
- `enriched_events` — event projection rows written with `events` so
  social-signal context can be replayed without provider calls.
- `token_capture_tier` — rebuildable capture-control projection with
  `TokenCaptureTierWorker` as its only runtime writer.
- `token_image_assets` — rebuildable local media mirror state written only by
  `TokenImageMirrorWorker`. Provider logo URLs are source inputs for the
  mirror and are never public image URLs.
- `runtime.bootstrap()` — composition entry point that builds
  `DBPoolBundle`, provider wiring, repositories, the canonical worker
  map, `WorkerScheduler`, API/WebSocket surfaces, readiness dependencies,
  and lifecycle ownership.
- `DBPoolBundle` — owns `api_pool`, `worker_pool`, `lock_pool`, and
  `wake_pool`. HTTP/WebSocket reads use the API pool, background worker
  SQL uses the worker pool, long-lived single-writer advisory locks use
  the lock pool, and wake emit/listen traffic uses the wake pool so read
  and worker traffic cannot be starved by projection locks or listeners.
- `worker_manifest.py` and `WorkerScheduler` — declare the canonical
  worker keys/classes/lane contracts and own worker start/stop/status semantics.
- `LLMGateway` and `AgentExecutionGateway` — `LLMGateway` owns low-level
  OpenAI transport/client/trace-export lifecycle; `AgentExecutionGateway`
  is the single agent execution path used by Social, Watchlist,
  Narrative, Pulse, and future LLM lanes. It resolves the lane capability
  profile and chooses the structured-output strategy before any provider
  call.
- Wake emission/listening is composed via
  `DBPoolBundle.wake_emitter()` and `DBPoolBundle.wake_listener()`.
  Domain workers receive wake dependencies by injection and never call
  `pg_notify` directly.

## Package Roots

| Root | Responsibility |
|------|----------------|
| `app/` | Composition root plus HTTP, WebSocket, and CLI surfaces. `app/runtime/bootstrap.py` wires `DBPoolBundle`, providers, repositories, manifest-owned workers, `WorkerScheduler`, readiness, and lifecycle. `app/surfaces/{api,cli}/` translate public inputs and outputs. Wake mechanics flow through `DBPoolBundle.wake_emitter()` / `wake_listener()`. |
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
| `[ADAPTER]` | Translates third-party shapes such as GMGN, OKX, macrodata-cli, or OpenAI Agents into internal values. Does not own product decisions. |
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
| `domains/asset_market/` | Asset registry, chain/address identity, asset identity evidence/current identity selection, exact-token profile source cache and current profile projection, append-only `market_ticks`, rebuildable `token_capture_tier`, cache/publish-only live price gateway, discovery, and CEX route sync. |
| `domains/token_intel/` | Token evidence, token intents, deterministic resolution, target-first search read model, token-target views, Token Radar feature aggregation, current-row publication state, `token_factor_snapshot_v3_social_attention` construction, factor-snapshot projection, evaluation diagnostics, signal alerts. |
| `domains/narrative_intel/` | Per-mention trade stance / attention valence labels, token-window discussion digests, semantic coverage, narrative evidence refs, and the narrative read model consumed by API composition and Pulse evidence packets. |
| `domains/social_enrichment/` | Watched-event gate, social-event extraction schema and facts, OpenAI Agents enrichment lifecycle, enrichment worker. |
| `domains/notifications/` | Notification rules, repository, delivery, workers, candidate types. |
| `domains/pulse_lab/` | Signal Pulse read model, factor-snapshot candidate gate / worker, unified decision runtime policy, stage replay ledger, and pulse persistence. |
| `domains/watchlist_intel/` | Watchlist handle-level topic summaries, signal/all handle timeline read model, summary job queue, and handle summary worker. |
| `domains/news_intel/` | Configured news source ingestion, news item facts, token mention observations, deterministic story grouping, fact candidates, item-scoped agent brief read model, and the News page read model. |
| `domains/cex_market_intel/` | Centralized exchange derivative series and Binance OI radar board projection. |
| `domains/macro_intel/` | `macro_sync` fact ingest from packaged macrodata-cli bundles, macro sync/import audit, deterministic macro feature/regime/scenario scoring, and the Macro read model. |
| `domains/account_quality/` | Account-quality snapshots, account-quality read service, account-alert read service. |

## Module Architecture Documents

Global architecture stays intentionally small. Important subsystems keep their
own maps next to the code they describe, and this file links to them.

| Module | File | Covers |
|--------|------|--------|
| Token Radar and token identity | [`src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`](../src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md) | GMGN frame to token evidence, intents, deterministic resolution, discovery / reprocess, market ticks, radar projection, and hard identity boundaries. |
| Narrative intelligence | `src/gmgn_twitter_intel/domains/narrative_intel/ARCHITECTURE.md` | Mention semantics, token discussion digest generation, evidence refs, semantic coverage, and narrative worker state machines. |
| Asset market and market tick capture | [`src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md`](../src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md) | Asset identity evidence ledger, `MarketTick` schema, capture-tier / stream / poll workers, cache-only live fan-out, profile / discovery workers, provider capability model. |
| CEX market intelligence | [`src/gmgn_twitter_intel/domains/cex_market_intel/ARCHITECTURE.md`](../src/gmgn_twitter_intel/domains/cex_market_intel/ARCHITECTURE.md) | Binance USDT perpetual universe consumption, OI radar board read model, CEX detail snapshots, and snapshot-only Token Case / Agent read paths. |
| Signal Pulse pipeline | [`src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md`](../src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md) | Candidate gate, agent route policy, stage runtime, decision persistence, audit ledger, abstain contract. |
| News intelligence | [`src/gmgn_twitter_intel/domains/news_intel/ARCHITECTURE.md`](../src/gmgn_twitter_intel/domains/news_intel/ARCHITECTURE.md) | Configured source ingestion, raw news item facts, token mention observations, story grouping, fact candidates, and the News page read model. |
| Macro intelligence | [`src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md`](../src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md) | `macro_sync` fact ingest, macro observation facts, deterministic `macro_regime_v4` feature/regime/scenario scoring, module v3 views, and Macro projection ownership. |

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
| `app/runtime/worker_manifest.py` and `app/runtime/worker_scheduler.py` | Canonical worker key/class/lane inventory plus start, stop, close, status, and unhealthy-reason semantics. |
| `app/runtime` | composition root: may import any domain runtime, repository, or interface to wire the process, subject to the dedicated Provider wiring rule above. |
| `app/surfaces/api`, `app/surfaces/cli` | domain `interfaces.py` and read services. **No domain SQL, scoring, settlement, token resolution, or notification rules** — surfaces translate public inputs into domain calls. |
| `platform/*` | stdlib, third-party. **Never** imports `domains/`, `integrations/`, or `app/`. |
| `integrations/*` | stdlib, third-party, `platform/*`. They wrap external APIs; they do not import `domains/` or `app/`. |

Cross-domain imports MUST go through the target domain's `interfaces.py` (or `_constants.py` for leaf data). `tests/architecture/test_src_domain_architecture.py::test_cross_domain_imports_use_interfaces` enforces this.

Raw SQL (`conn.execute(...)`) lives ONLY in `repositories/`, `queries/`, `platform/db/`, or `app/runtime/` health checks. `tests/architecture/test_src_domain_architecture.py::test_raw_sql_is_owned_by_repositories_queries_or_app_runtime` enforces this.

Legacy `assets`, `asset_aliases`, `asset_venues`, and `asset_market_snapshots` tables have no runtime writers. `tests/architecture/test_worker_runtime_contracts.py::test_legacy_asset_tables_have_no_runtime_writers` enforces this; `test_legacy_asset_repository_is_not_imported` bans the deleted `AssetRepository` / `MarketRepository` classes. SocialEvent closed-loop harness tables are deleted; Pulse market reads go through `RegistryRepository.chain_token_market_target(...)` + `MarketTickRepository.latest_at_or_before(...)` rather than `asset_market_snapshots`.

Transaction ownership follows the same rule: domain services and runtime workers use repository/session Unit of Work methods, not `platform.db.postgres_client.transaction` directly. Repositories and `app/runtime/repository_session.py` own the concrete PostgreSQL transaction context.

PostgreSQL table lifecycle follows the hot/cold contract in
`docs/references/POSTGRES_PERFORMANCE.md`: compact read models are the only hot
serving inputs, detail/evidence queries are bounded by selected read-model keys,
and control-plane tables are leased with bounded work and terminal evidence.
Runtime workers must not use cold history/audit tables as freshness, fallback,
or queue-maintenance state; cold projections need their own spec and writer.

Provider modules are intentionally sparse. Only domains with real inbound cross-cutting dependencies have `providers.py` today: `ingestion`, `asset_market`, `social_enrichment`, `pulse_lab`, and `watchlist_intel`. Do not add empty provider files.

CLI ops remain a separate operational surface exception: they may construct external clients for explicit operator commands, while service runtime construction stays centralized in `app/runtime/providers_wiring.py`.

## Pulse Agent Runtime

Signal Pulse is the first concrete strategy on the unified Agent Runtime Core.
`domains/pulse_lab/services/agent_routing.py` owns deterministic route policy
(`cex`, `meme`, or `research_only`) and completeness gates. The Pulse worker
turns a factor snapshot into a route, writes an agent run, short-circuits
research-only or hard-blocked rows to an abstain decision, and otherwise calls
the configured `PulseDecisionProvider`.

OpenAI-specific SDK execution lives only under `integrations/openai_agents/`.
Signal Pulse uses the two-stage `Investigator -> DecisionMaker` runtime, with
`research_only_gate` for deterministic hard-blocks. Pulse-specific orchestration
is domain-owned: `domains/pulse_lab/services/pulse_decision_runtime.py` loads
stage prompts, builds stage input contracts, assembles request audit hashes,
validates cited evidence ids, and enriches final evidence URLs;
`domains/pulse_lab/services/agent_tool_runtime.py` owns tool query behavior,
budgets, truncation, and contributed event ids. The OpenAI adapter wraps Agent / Runner /
`function_tool`, schema parsing, usage/tool-call extraction, safety net, and SDK
errors only. It may import Pulse provider protocols/types, but not Pulse
queries or services.
The runtime manifest's `runtime.tool_names_by_stage` is the only tool contract:
"tools enabled" means a stage has a non-empty tool list; there is no separate
boolean flag.
`app/runtime/provider_wiring/openai.py` is the composition point that creates the
domain runtimes and injects them into the concrete adapter bound to the
`pulse_lab` provider protocol.

The audit ledger is PostgreSQL: `pulse_agent_runs` records the final outcome and
route, `pulse_agent_run_steps` records replayable stage inputs/prompts/outputs,
and `pulse_candidates.decision_*` plus `decision_json` are the public decision
source. Signal Pulse public payloads expose `decision`, `factor_snapshot`,
`gate`, and `fact_card`.

Narrative Intelligence sits upstream of Pulse decisioning and downstream of
Token Radar discovery. API surfaces may compose Token Radar / Token Case rows
with `NarrativeReadModel`, but they do not run providers, score rows, or write
narrative read models. Narrative digest rows are sealed epochs: public reads
compose the last ready epoch with the current `narrative_admissions` source
frontier and expose the delta through `discussion_digest.currentness`.
Fingerprint mismatch alone is not a reason to blank the narrative. Pulse may
include a ready discussion digest in its sealed evidence packet as context, but
stale/updating digest prose is not primary evidence; Pulse hidden/internal
candidate state never triggers narrative workers and never writes
`token_mention_semantics` or `token_discussion_digests`.

## Asset Profile Facts

Resolved DEX asset profile facts live in `domains/asset_market`, not in Token
Radar scoring snapshots. The runtime profile lane is:

```
resolved Asset(chain,address)
  → asset_profile_refresh_targets
  → AssetProfileRefreshWorker
  → dex_profile_sources[].token_profile(...)
  → asset_profiles (GMGN OpenAPI + Binance Web3 source caches)
  → token_profile_current_dirty_targets
  → TokenProfileCurrentWorker
  → token_profile_current
  → TokenProfileReadModel
  → /api/token-radar + /api/search/inspect + CLI asset-flow
  → shared frontend TokenProfileCard
```

Only `asset_market` workers and explicit ops commands may call the profile provider.
HTTP handlers, CLI read commands, Token Radar projection, Search read models,
and frontend components read persisted `token_profile_current` through
`TokenProfileReadModel`. The current profile projection only marks rows
`ready` when the selected source has a usable logo; it also promotes exact
GMGN stream snapshot icons, exact OKX DEX evidence, and Binance CEX profile
source-cache rows already stored in PostgreSQL; it does not use request-time
fallback or symbol-only CEX matching. `cex_tokens` remains identity/routing
only; CEX profile data lives in `cex_token_profiles`.
Official links and descriptions must be visible without running a narrative
agent; future narrative jobs may consume profile facts, but they do not own
official profile data.

## Market Data Provider Matrix

This matrix is the source of truth for which upstream provider feeds each
market-data lane, which lanes are allowed to write `market_ticks` /
`enriched_events`, and which lanes are read-only. It supersedes any older
phrasing in this doc or `WORKERS.md` that described OKX as a "fallback" to a
GMGN price WebSocket — GMGN's public WebSocket is a *social* ingestion stream,
not a price source. The active spec and plan that pin this layout are
`docs/superpowers/specs/active/2026-05-16-price-pipeline-throughput-recovery-cn.md`
and `docs/superpowers/plans/active/2026-05-16-price-pipeline-throughput-recovery-plan-cn.md`.

| Layer | Primary | Fallback | Writes facts | Notes |
|---|---|---|---|---|
| Social ingestion | GMGN DirectWS | none | `events`, `token_intents`, `token_intent_resolutions` | Not a price source |
| Tier 1 price stream | OKX DEX WS | none | `market_ticks(source_tier='tier1_ws')` | `chain_token` only; CEX symbols never enter Tier 1 |
| Tier 2 DEX poll | GMGN OpenAPI REST | OKX DEX REST | `market_ticks(source_tier='tier2_poll')` | No GMGN price WS in the official skills repo |
| Tier 2 CEX poll | Binance USD-M REST | none | `market_ticks(source_tier='tier2_poll')` | CEX WS intentionally out of this pass |
| Event anchor DEX backfill | GMGN OpenAPI REST | OKX DEX REST | `market_ticks`, narrow `enriched_events` lifecycle update; `event_anchor_backfill_jobs` control state | Same `dex_quote_market` provider stack as Tier 2 |
| Event anchor CEX backfill | Binance USD-M REST | none | `market_ticks`, narrow `enriched_events` lifecycle update; `event_anchor_backfill_jobs` control state | Same `cex_market` provider as Tier 2 |
| Frontend `/ws` | latest `market_ticks` read model | none | no facts | `LivePriceGateway` fan-out only; no upstream provider calls |

Consequences for code review:

- Only `MarketTickStreamWorker`, `MarketTickPollWorker`, ingest inline Tier 3
  capture, and `EventAnchorBackfillWorker` may write `market_ticks`. The
  inventory in `WORKERS.md` lists every runtime writer.
- `EventAnchorBackfillWorker` consumes `event_anchor_backfill_jobs`; it must not
  page directly through `enriched_events` as a retry queue. `enriched_events`
  records only event-anchor fact lifecycle: pending, ready, or terminal
  unavailable.
- `LivePriceGateway` reads the latest `market_ticks` fan-out; it does not
  hold its own upstream WebSocket or REST clients.
- GMGN's public WebSocket is consumed only by the `collector` social
  ingestion path. Any code that wires it as a price provider is wrong.

## Generated and reference material

- `docs/generated/{cli-help,ws-protocol,score-versions,db-schema}.md` — regenerated by `make docs-generated`. Score-version paths reflect `domains/token_intel/scoring/`.
- `docs/CONTRACTS.md` — public HTTP / WebSocket / CLI surface contracts.
- `docs/references/` — papers and external API references underpinning algorithm choices.

To find code, prefer `ls src/gmgn_twitter_intel/domains/<domain>/` over a memorised file list. This file pins the package map; per-file responsibilities live in the code and its tests.
