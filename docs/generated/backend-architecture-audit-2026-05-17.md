# Backend Architecture Audit, 2026-05-17

Scope: backend source under `src/gmgn_twitter_intel/**/*.py`. Generated caches and local `__pycache__` files are excluded. I read and indexed all 329 tracked Python source files, 54472 LOC, including 59 Alembic migration files. The per-file ledger at the end includes a SHA-256 prefix as the read marker.

## Executive Summary

The backend has a coherent target architecture: domain packages, Kappa/CQRS, PostgreSQL facts as truth, rebuildable read models, single runtime writer per read model, provider wiring centralized in `app/runtime/providers_wiring.py`, and explicit worker inventory in `docs/WORKERS.md`. The automatic architecture tests are meaningful and currently pass.

The implementation is not yet mature enough to call "stable". The main weakness is not conceptual architecture, but concentration: several files have grown into high-coupling coordination centers. `PulseRepository`, `PulseCandidateWorker`, `create_api_router`, `cli.main`, `providers_wiring`, and `TokenRadarProjection` carry too many reasons to change. This makes KISS fragile even though the documented boundaries mostly hold.

Current verification is red: `ruff check src` fails, `mypy src` fails with 15 errors, and `pytest tests/unit -q` has 1 failing test caused by conflicting Pulse harness manifest expectations. `tests/architecture -q` and `tests/contract -q` pass, and `compileall src tests` passes.

## Area Size

| Area | Files | LOC |
|---|---:|---:|
| `__init__.py` | 1 | 1 |
| `__main__.py` | 1 | 4 |
| `app/__init__.py` | 1 | 0 |
| `app/runtime` | 16 | 3644 |
| `app/surfaces` | 7 | 3320 |
| `cli.py` | 1 | 9 |
| `domains/__init__.py` | 1 | 0 |
| `domains/account_quality` | 7 | 655 |
| `domains/asset_market` | 42 | 7574 |
| `domains/closed_loop_harness` | 15 | 2196 |
| `domains/evidence` | 13 | 1565 |
| `domains/ingestion` | 10 | 680 |
| `domains/notifications` | 11 | 2294 |
| `domains/pulse_lab` | 23 | 6119 |
| `domains/social_enrichment` | 11 | 1247 |
| `domains/token_intel` | 58 | 10769 |
| `domains/watchlist_intel` | 10 | 1679 |
| `integrations/__init__.py` | 1 | 0 |
| `integrations/binance` | 3 | 264 |
| `integrations/coingecko` | 2 | 94 |
| `integrations/gmgn` | 5 | 1004 |
| `integrations/marketlane` | 2 | 76 |
| `integrations/okx` | 6 | 894 |
| `integrations/openai_agents` | 10 | 2429 |
| `platform/__init__.py` | 1 | 0 |
| `platform/config` | 2 | 1230 |
| `platform/db` | 65 | 6668 |
| `platform/logging` | 2 | 32 |
| `platform/paths` | 2 | 25 |

## Verification Snapshot

| Command | Result | Signal |
|---|---|---|
| `uv run pytest tests/architecture -q` | PASS, 82 passed | Documented architecture guards currently hold. |
| `uv run pytest tests/contract -q` | PASS, 5 passed | OpenAPI/contract tests currently hold. |
| `uv run python -m compileall src tests` | PASS | Source parses and compiles. |
| `uv run ruff check src` | FAIL, 4 errors | Import ordering and one B009 plus one long line. |
| `uv run mypy src` | FAIL, 15 errors in 9 files | Type drift in market/profile/watchlist/Pulse paths. |
| `uv run pytest tests/unit -q` | FAIL, 967 passed, 1 failed, 13 skipped | Pulse harness manifest contract conflict. |

## Failure Details

Ruff failures:

- `domains/notifications/services/notification_rules.py:1`: import block unsorted.
- `domains/pulse_lab/runtime/pulse_candidate_worker.py:1`: import block unsorted.
- `domains/pulse_lab/runtime/pulse_candidate_worker.py:734`: `getattr` with constant private attribute, B009.
- `domains/pulse_lab/services/agent_harness_eval.py:105`: line length 121 > 120.

Mypy failures:

- `domains/asset_market/read_models/token_profile_read_model.py:143`: list comprehension returns `list[str | None]` where `list[str]` is expected.
- `domains/asset_market/runtime/market_tick_stream_worker.py:111-112`: `stream_dex_market` may be `None`.
- `domains/asset_market/runtime/market_tick_poll_worker.py:298-299`: `Any` returned where `list[Mapping[str, Any]]` is declared.
- `domains/asset_market/runtime/live_price_gateway.py:153-223`: nullable target rows flow into latest-tick lookups and return type is `Any`.
- `domains/watchlist_intel/repositories/watchlist_intel_repository.py:704,745`: `social_event` may be `None`.
- `integrations/openai_agents/watchlist_summary_agent_client.py:8` and `pulse_decision_agent_client.py:11`: `jsonref` has no stubs or `py.typed`.
- `domains/pulse_lab/repositories/pulse_repository.py:1800`: missing return type annotation.
- `domains/asset_market/runtime/event_anchor_backfill_worker.py:98`: provider bundle type does not match `AssetMarketProviders`.

Unit failure:

- `tests/unit/integrations/openai_agents/test_pulse_decision_two_stage.py:970` expects `manifest["runtime"]["tools_enabled"] is True`.
- `tests/unit/domains/pulse_lab/test_agent_harness_eval_v2.py:288` expects `"tools_enabled" not in manifest["runtime"]`.
- Implementation in `domains/pulse_lab/services/agent_harness.py:64-77` has `stages`, `max_turns_per_stage`, `tool_names_by_stage`, `route_tool_budgets`, `safety_net_enabled`, and `timeout_seconds`, but no `tools_enabled`.

## Size Hotspots

| File | LOC | Why It Matters |
|---|---:|---|
| `domains/pulse_lab/repositories/pulse_repository.py` | 1858 | Pulse storage concerns are concentrated in one repository class. |
| `app/surfaces/cli/main.py` | 1350 | CLI parsing, dispatch, and command behavior live together. |
| `domains/pulse_lab/runtime/pulse_candidate_worker.py` | 1345 | Candidate scanning, LLM call, audit ledger, eval, and failures share one worker. |
| `app/surfaces/api/http.py` | 1335 | All HTTP routes are registered inside one function. |
| `platform/config/settings.py` | 1230 | Application and worker config schemas plus default YAML live together. |
| `integrations/openai_agents/pulse_decision_agent_client.py` | 1085 | SDK orchestration, prompts/tools, validation, and fallback handling are coupled. |
| `domains/closed_loop_harness/repositories/harness_repository.py` | 1065 | Harness table writes and read summaries share one repository. |
| `domains/token_intel/services/token_radar_projection.py` | 1057 | Projection orchestration, grouping, market context, ranking, and helpers share one module. |
| `app/runtime/providers_wiring.py` | 969 | All concrete provider construction and adapter glue live together. |
| `domains/notifications/services/notification_rules.py` | 908 | Notification candidate selection and rule evaluation are dense and broad. |

## Target Data Flow Read

Declared and mostly implemented chain:

```text
GMGN WS frame
  -> ingestion normalizer / CollectorService
  -> evidence IngestService transaction
  -> events, event_entities, token_evidence, token_intents, token_intent_resolutions
  -> registry_assets, asset_identity_evidence/current
  -> inline market_ticks + enriched_events
  -> asset_market capture tier / market tick stream-poll / profile current
  -> token_intel TokenRadarProjection
  -> token_radar_rows.factor_snapshot_json
  -> pulse_lab / notifications / watchlist / API / WS / CLI
```

Important maturity positives:

- Facts versus read models are documented and architecture guarded.
- `DBPoolBundle` separates API, worker, wake, and tool pools.
- Long-running workers inherit `WorkerBase`; the canonical worker registry and docs are tested in lockstep.
- `market_ticks` has a single repository write path and multiple authorized capture lanes; `LivePriceGateway` is cache/fan-out only.
- Migration graph has 59 files, no duplicate revisions, no branches, and one head: `20260517_0059`.

Important maturity gaps:

- Green architecture tests do not imply green release gates. Lint, typecheck, and unit tests fail today.
- The Pulse harness test suite has contradictory expectations: one test asserts `runtime.tools_enabled` exists, another asserts it must not exist.
- Some architecture wording says `integrations/*` must not import `domains/*`, but `integrations/openai_agents` imports Pulse domain queries/services/types. This may be an intentional adapter exception, but it is not reflected consistently in global docs and guards.
- Several runtime paths use `Any`, `SimpleNamespace`, private attribute probes, and dynamic `getattr`, which weakens the typed architecture and is now visible in mypy failures.

## Findings

### P0. Verification Gates Are Red

Evidence:

- `ruff check src` fails in `domains/notifications/services/notification_rules.py`, `domains/pulse_lab/runtime/pulse_candidate_worker.py`, and `domains/pulse_lab/services/agent_harness_eval.py`.
- `mypy src` reports 15 errors in market/profile/watchlist/Pulse/OpenAI paths.
- `pytest tests/unit -q` fails at `tests/unit/integrations/openai_agents/test_pulse_decision_two_stage.py:970` because `build_pulse_harness_manifest()` omits `runtime.tools_enabled`, while `tests/unit/domains/pulse_lab/test_agent_harness_eval_v2.py:288` asserts that field must not exist.

Impact: current code cannot pass the repo's own backend quality gate. Before large refactors, the repository needs a green baseline or every refactor will mix architecture movement with pre-existing failures.

Recommendation: fix the Pulse manifest contract first, then ruff, then mypy. Decide whether `tools_enabled` is removed or restored, and update both tests and docs to one contract.

### P1. Runtime Composition Is Correct But Over-Centralized

Evidence:

- `app/runtime/bootstrap.py` is 707 LOC; `_construct_workers` is 204 lines and knows all canonical workers plus provider availability rules.
- `app/runtime/providers_wiring.py` is 969 LOC and mixes provider dataclasses, adapter classes, OKX/GmGN/Binance/Marketlane/OpenAI construction, provider health, chain-id mapping, fallback quote selection, and cleanup.

Impact: adding one provider, one worker, or one domain option changes the same two files. This is acceptable for early-stage wiring but becomes a merge-conflict and regression hotspot as the system grows.

Recommendation: keep `bootstrap()` as the process entrypoint, but split implementation into `app/runtime/provider_wiring/{asset_market,openai,gmgn,okx,binance,marketlane}.py` and `app/runtime/worker_factories/{asset_market,pulse,watchlist,notifications}.py`. The top-level bootstrap should read like a table of factories, not a construction script.

### P1. Public Surfaces Are Too Fat

Evidence:

- `app/surfaces/api/http.py` is 1335 LOC; `create_api_router()` alone is 777 lines.
- `app/surfaces/cli/main.py` is 1350 LOC; `main()` is 611 lines and `build_parser()` is 215 lines.
- HTTP handlers instantiate read services and reach into runtime worker objects for `live_price_gateway`, `pulse_candidate`, `enrichment`, and `harness_ops` status.

Impact: surfaces are close to becoming orchestration layers. The documented rule says surfaces should translate public inputs/outputs and not own scoring, resolution, SQL joins, or provider calls. Today they mostly obey that, but the file shape makes accidental drift likely.

Recommendation: split API routers by surface: `status`, `events`, `radar`, `search`, `watchlist`, `pulse`, `harness`, `notifications`, `admin`. Move auth, validators, and shared runtime access into a tiny dependency module. Split CLI into command modules with parser registration per command.

### P1. Pulse Lab Has The Highest Coupling Risk

Evidence:

- `domains/pulse_lab/repositories/pulse_repository.py` is 1858 LOC; `PulseRepository` is 1684 lines.
- `domains/pulse_lab/runtime/pulse_candidate_worker.py` is 1345 LOC; `_run_job()` is 326 lines and does run-id generation, gate/route/completeness, harness manifest, audit creation, LLM call, step persistence, eval-case creation, decision persistence, failure persistence, and job state transitions.

Impact: the single-writer invariant is good, but the writer has too many responsibilities. This is the most likely place for audit ledger regressions, partial writes, and hard-to-test edge cases.

Recommendation: split Pulse into explicit use cases: `PulseTriggerScanner`, `PulseJobRunner`, `PulseAuditLedgerWriter`, `PulseFailureRecorder`, `PulseEvalRecorder`. Split repository by table cluster: jobs/budget, candidates, runs/steps, harness/evals, summary read model.

### P1. Integration Boundary Is Ambiguous

Evidence: `integrations/openai_agents/pulse_decision_agent_client.py` imports `domains/pulse_lab.queries.agent_tool_queries`, `domains/pulse_lab.services.agent_harness`, `domains/pulse_lab.services.prompt_loader`, and `domains/pulse_lab.types.agent_decision`. The global architecture says integrations wrap external APIs and do not import domains or app.

Impact: OpenAI adapter is doing domain-shaped orchestration. That may be the right tradeoff for the current Agent runtime, but the rule and the implementation disagree. When docs and tests disagree, future agents will make inconsistent changes.

Recommendation: choose one. Either codify `integrations/openai_agents` as a sanctioned domain-adapter exception with a guard, or move Pulse-specific tool/query/prompt assembly behind a Pulse domain provider interface so the integration layer only translates external SDK calls.

### P1. Type Safety Is Not Strong Enough For The Architecture

Evidence: `mypy src` fails in `token_profile_read_model.py`, `market_tick_stream_worker.py`, `market_tick_poll_worker.py`, `live_price_gateway.py`, `watchlist_intel_repository.py`, `pulse_repository.py`, `event_anchor_backfill_worker.py`, and both OpenAI agent clients. Several failures are real optionality problems around `None` filtering and provider availability.

Impact: Kappa/CQRS code relies on stable payload shapes. If optional/dynamic shapes are not typed, missing market ticks or profile rows can turn into runtime-only failures.

Recommendation: replace `Any`/`SimpleNamespace` provider bundles with narrow protocols and typed dataclasses. Add typed row mappers for market targets, profile quality flags, watchlist social events, and Pulse harness manifests.

### P2. Runtime Compatibility Naming Still Leaks Into New Paths

Evidence: `market_overlay` exists in `app/surfaces/api/schemas.py`, `domains/token_intel/read_models/token_target_social_timeline_service.py`, `domains/token_intel/read_models/search_agent_brief.py`, and `domains/asset_market/read_models/market_candles_service.py`. There are tests asserting old runtime overlays are gone from other surfaces, so this appears to be a new chart/candle payload with an old name.

Impact: this is not necessarily a behavior bug, but it weakens the "no runtime compatibility layer" rule. Names like `overlay` make it harder to tell if code is a legacy bridge or a first-class read model.

Recommendation: rename this concept to a first-class product term such as `market_series` or `market_candles`, and update contracts/tests together.

### P2. Helper Duplication Is A Symptom Of Missing Primitive Policy

Evidence from static scan excluding migrations:

- `_now_ms` appears 41 times.
- `_int_or_none` appears 15 times.
- `_dict`, `_json`, `_clean`, `_mapping`, `_stable_id`, and `_normalize_symbol` are repeated across domains.

Impact: small duplication is fine, but repeated parsing/normalization helpers across market, pulse, token intel, notifications, and integrations create subtly different behavior.

Recommendation: do not create a generic `utils.py`. Either keep helpers local when semantics are domain-specific, or introduce explicitly named primitives such as `platform/time.py`, `platform/json_values.py`, or per-domain `normalization.py`, then add architecture rules for what may import them.

### P2. Generic JobQueue Looks Unused In Runtime

Evidence: `app/runtime/job_queue.py` is 326 LOC and has unit tests, but source imports only reference it from tests and `WorkerBase` has only an optional `job_queue` slot. Current workers appear to use domain repositories directly for queues.

Impact: this is a KISS smell. Either the abstraction is the intended queue core but not adopted, or it is retained speculative infrastructure.

Recommendation: make a decision. Adopt it in enrichment/watchlist/pulse/notification queues, or remove it and keep queue semantics in domain repositories.

### P3. Unwired Adapter Surface Exists

Evidence: `integrations/coingecko/search_client.py` is present and tested, but no runtime source imports it except its own package `__init__`.

Impact: low immediate risk, but it creates an implied provider option not present in settings, wiring, worker inventory, or architecture docs.

Recommendation: remove it if obsolete, or document it as an offline/reference adapter and add explicit wiring only when product scope needs it.

## Decomposition Plan

1. Green baseline first: resolve the Pulse `tools_enabled` contract conflict, run `ruff --fix` where safe, fix mypy errors without broad casts, and rerun `ruff`, `mypy`, `unit`, `architecture`, and `contract`.
2. Split HTTP and CLI surfaces without behavior changes. Move route groups and command handlers only; keep response models and repository calls unchanged.
3. Split provider wiring by provider family. Preserve `wire_providers()` as the public composition function and move concrete construction into focused modules.
4. Split worker construction by domain. Keep `CANONICAL_WORKER_NAMES` and worker scheduler unchanged, but delegate construction to small domain factories.
5. Refactor Pulse behind use-case boundaries. Start with repository split because it is low behavior risk, then split `_run_job()` into audit/run/eval/failure services.
6. Normalize compatibility naming. Rename `market_overlay` only after tests are green and contracts are updated.
7. Add guards for the lessons above: file-size warning test, integration/domain exception test, and a test that `make check` is green before generated verification artefacts are accepted.

## File Inventory Ledger

Read marker: first 12 chars of SHA-256 for the exact file contents read during this audit.

| # | File | Role | LOC | Necessity | What It Does | Read Marker |
|---:|---|---|---:|---|---|---|
| 1 | `__init__.py` | 包标记/导出 | 1 | 必要: package/export | GMGN Twitter intelligence service. | `bde6a3e6ab7a` |
| 2 | `__main__.py` | 入口 shim | 4 | 必要: 入口兼容 | Module execution entrypoint that delegates to CLI main. | `307299fda7b7` |
| 3 | `app/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 4 | `app/runtime/__init__.py` | 包标记/导出 | 4 | 必要: package/export | Python package marker and selected public re-exports. | `f659d96fcf19` |
| 5 | `app/runtime/app.py` | 运行时组合/生命周期 | 214 | 必要但偏大 | Defines functions create_app. | `6a0601de2e88` |
| 6 | `app/runtime/bootstrap.py` | 运行时组合/生命周期 | 707 | 必要但建议拆分 | Defines Runtime, _PooledIngestStore, _DisabledWorker, ... | `9d3cbbc017c0` |
| 7 | `app/runtime/db_pool_bundle.py` | 运行时组合/生命周期 | 252 | 必要但偏大 | Defines DBPoolBundle, AdvisoryLockConnection. | `0e84a509cd2b` |
| 8 | `app/runtime/job_queue.py` | 运行时组合/生命周期 | 326 | 需确认: 抽象未接线 | Defines BackoffPolicy, JobQueueDescriptor, JobQueue. | `a8240a96fea7` |
| 9 | `app/runtime/llm_gateway.py` | 运行时组合/生命周期 | 112 | 必要 | Defines LLMGateway. | `2f9a1fcaecf1` |
| 10 | `app/runtime/providers_wiring.py` | 运行时组合/生命周期 | 969 | 必要但建议拆分 | Defines IngestionProviders, AssetMarketProviders, OkxProviderBundle, ... | `34c632d78459` |
| 11 | `app/runtime/repository_session.py` | 运行时组合/生命周期 | 127 | 必要 | Defines RepositorySession, PooledRepository. | `642fb986fe72` |
| 12 | `app/runtime/telemetry.py` | 运行时组合/生命周期 | 111 | 必要 | Defines TelemetryRegistry. | `5b58f79dd996` |
| 13 | `app/runtime/wake_bus.py` | 运行时组合/生命周期 | 48 | 必要 | Defines WakeBus. | `04be9b24708b` |
| 14 | `app/runtime/wake_waiter.py` | 运行时组合/生命周期 | 73 | 必要 | Defines WakeWaiter. | `4d9747f58ef3` |
| 15 | `app/runtime/worker_base.py` | 运行时组合/生命周期 | 383 | 必要但偏大 | Defines WorkerStatus, WorkerBase. | `e06740e1cfce` |
| 16 | `app/runtime/worker_registry.py` | 运行时组合/生命周期 | 57 | 必要 | Small constants or package glue. | `fa1031a9f8a7` |
| 17 | `app/runtime/worker_result.py` | 运行时组合/生命周期 | 13 | 必要 | Defines WorkerResult. | `c6a25aaa117e` |
| 18 | `app/runtime/worker_scheduler.py` | 运行时组合/生命周期 | 163 | 必要 | Defines WorkerScheduler. | `f440393e03dd` |
| 19 | `app/runtime/worker_status.py` | 运行时组合/生命周期 | 85 | 必要 | Defines functions workers_status_payload, canonical_workers_status_payload, canonical_worker_statuses, empty_worker_status, ... | `abe06e51b063` |
| 20 | `app/surfaces/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 21 | `app/surfaces/api/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 22 | `app/surfaces/api/http.py` | HTTP/WS surface | 1335 | 必要但建议拆分 | Defines ApiUnauthorized, ApiBadRequest. | `f6bc134096c7` |
| 23 | `app/surfaces/api/schemas.py` | HTTP/WS surface | 367 | 必要但偏大 | Defines ApiSchema, ApiEnvelope, BootstrapData, ... | `e1083fb1d7be` |
| 24 | `app/surfaces/api/ws.py` | HTTP/WS surface | 268 | 必要但偏大 | Defines ClientSubscription, PublicWebSocketHub. | `01d15d0c1b6f` |
| 25 | `app/surfaces/cli/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 26 | `app/surfaces/cli/main.py` | CLI surface | 1350 | 必要但建议拆分 | Defines functions build_parser, main. | `e2dcf636e947` |
| 27 | `cli.py` | 入口 shim | 9 | 必要: 入口兼容 | Installed command shim that re-exports CLI parser/main. | `a8c20b54dc37` |
| 28 | `domains/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 29 | `domains/account_quality/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 30 | `domains/account_quality/interfaces.py` | 域接口/跨域契约 | 7 | 必要 | Small constants or package glue. | `1e0eb0d11454` |
| 31 | `domains/account_quality/read_models/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 32 | `domains/account_quality/read_models/account_alert_service.py` | 读模型服务 | 31 | 必要 | Defines AccountAlertService. | `63db241fd0f5` |
| 33 | `domains/account_quality/read_models/account_quality_service.py` | 读模型服务 | 238 | 必要但偏大 | Defines AccountQualityService. | `6a7f4385ca56` |
| 34 | `domains/account_quality/repositories/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 35 | `domains/account_quality/repositories/account_quality_repository.py` | Repository/SQL | 379 | 必要但偏大 | Defines AccountQualityRepository. | `61be9a61dd9b` |
| 36 | `domains/asset_market/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 37 | `domains/asset_market/identity_evidence_policy.py` | 领域模块 | 162 | 必要 | Defines functions select_current_identity. | `a9e5242e8a02` |
| 38 | `domains/asset_market/interfaces.py` | 域接口/跨域契约 | 55 | 必要 | Small constants or package glue. | `7fae23d523de` |
| 39 | `domains/asset_market/market_field_facts.py` | 领域模块 | 93 | 必要 | Defines functions field_status, field_fact, aggregate_market_status. | `2ca87f2fb801` |
| 40 | `domains/asset_market/profile_source_selection.py` | 领域模块 | 69 | 必要 | Defines functions select_gmgn_stream_source, select_okx_dex_source. | `f78f60d23303` |
| 41 | `domains/asset_market/providers.py` | Provider 协议 | 185 | 必要 | Defines MarketCapability, ProviderHealth, DexProviderTemporarilyUnavailable, ... | `3afbfb178ce5` |
| 42 | `domains/asset_market/queries/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 43 | `domains/asset_market/queries/pending_asset_profile_query.py` | Query/SQL 读侧 | 172 | 必要 | Defines PendingAssetProfileQuery. | `bc175e2ac8f4` |
| 44 | `domains/asset_market/queries/token_profile_source_query.py` | Query/SQL 读侧 | 217 | 必要但偏大 | Defines TokenProfileSourceQuery. | `7dffe4d5fe1d` |
| 45 | `domains/asset_market/read_models/__init__.py` | 包标记/导出 | 1 | 必要: package/export | Python package marker and selected public re-exports. | `5384bfdb2df3` |
| 46 | `domains/asset_market/read_models/market_candles_service.py` | 读模型服务 | 139 | 必要 | Defines MarketCandlesService. | `f7cb7f1445bd` |
| 47 | `domains/asset_market/read_models/message_price_payload.py` | 读模型服务 | 45 | 必要 | Defines functions message_price_payload. | `d1fce13a4f88` |
| 48 | `domains/asset_market/read_models/token_profile_read_model.py` | 读模型服务 | 154 | 必要 | Defines TokenProfileReadModel. | `787927892d9a` |
| 49 | `domains/asset_market/repositories/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 50 | `domains/asset_market/repositories/asset_profile_repository.py` | Repository/SQL | 199 | 必要 | Defines AssetProfileRepository. | `84c768af66c5` |
| 51 | `domains/asset_market/repositories/cex_token_profile_repository.py` | Repository/SQL | 101 | 必要 | Defines CexTokenProfileRepository. | `77d2dea14a2b` |
| 52 | `domains/asset_market/repositories/discovery_repository.py` | Repository/SQL | 285 | 必要但偏大 | Defines DiscoveryRepository. | `b31a698d1f7b` |
| 53 | `domains/asset_market/repositories/enriched_event_repository.py` | Repository/SQL | 168 | 必要 | Defines EnrichedEventRepository. | `fa3241810821` |
| 54 | `domains/asset_market/repositories/identity_evidence_repository.py` | Repository/SQL | 287 | 必要但偏大 | Defines IdentityEvidenceRepository. | `63639bc823e7` |
| 55 | `domains/asset_market/repositories/market_tick_repository.py` | Repository/SQL | 222 | 必要但偏大 | Defines MarketTickRepository. | `319de365b319` |
| 56 | `domains/asset_market/repositories/registry_repository.py` | Repository/SQL | 713 | 必要但建议拆分 | Defines RegistryRepository. | `ab319c0cc957` |
| 57 | `domains/asset_market/repositories/token_capture_tier_repository.py` | Repository/SQL | 159 | 必要 | Defines TokenCaptureTierRepository. | `99be2d458b24` |
| 58 | `domains/asset_market/repositories/token_profile_current_repository.py` | Repository/SQL | 129 | 必要 | Defines TokenProfileCurrentRepository. | `d8d9f61f8ea0` |
| 59 | `domains/asset_market/runtime/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 60 | `domains/asset_market/runtime/asset_profile_refresh_worker.py` | Worker/runtime | 125 | 必要 | Defines AssetProfileRefreshWorker. | `9422bf994b41` |
| 61 | `domains/asset_market/runtime/event_anchor_backfill_worker.py` | Worker/runtime | 266 | 必要但偏大 | Async backfill worker for inline-pending event anchors. The collector hot path persists ``enriched_events`` ro | `04a71c3c8daa` |
| 62 | `domains/asset_market/runtime/live_price_gateway.py` | Worker/runtime | 389 | 必要但偏大 | Defines LiveMarketSnapshot, LiveMarketEmit, LivePriceGateway. | `24d0e24104de` |
| 63 | `domains/asset_market/runtime/market_tick_poll_worker.py` | Worker/runtime | 546 | 必要但建议拆分 | Defines MarketTickPollWorker, _ChainTarget, _CexTarget, ... | `0ab947fff947` |
| 64 | `domains/asset_market/runtime/market_tick_stream_worker.py` | Worker/runtime | 339 | 必要但偏大 | Defines MarketTickStreamWorker, _TargetParts, _StreamPersistResult. | `69e61b7fa8ba` |
| 65 | `domains/asset_market/runtime/resolution_refresh_worker.py` | Worker/runtime | 721 | 必要但建议拆分 | Defines ResolutionRefreshWorker. | `183713112123` |
| 66 | `domains/asset_market/runtime/token_capture_tier_worker.py` | Worker/runtime | 237 | 必要但偏大 | Defines TokenCaptureTierWorker, _Candidate. | `43c27e0cd121` |
| 67 | `domains/asset_market/runtime/token_profile_current_worker.py` | Worker/runtime | 91 | 必要 | Defines TokenProfileCurrentWorker. | `339476ab7221` |
| 68 | `domains/asset_market/services/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 69 | `domains/asset_market/services/asset_market_sync.py` | 领域服务 | 64 | 必要 | Defines functions sync_cex_routes. | `f976a65dd04e` |
| 70 | `domains/asset_market/services/asset_profile_refresh.py` | 领域服务 | 149 | 必要 | Defines functions refresh_asset_profiles_once, select_due_asset_profile_rows, fetch_asset_profile, write_ready_asset_profile, ... | `63a00b22269d` |
| 71 | `domains/asset_market/services/cex_token_profile_sync.py` | 领域服务 | 67 | 必要 | Defines functions sync_cex_token_profiles. | `6e389068ffb2` |
| 72 | `domains/asset_market/services/event_market_capture.py` | 领域服务 | 441 | 必要但偏大 | Defines TickLookup, CaptureResult, _CaptureRequest, ... | `3056a7104773` |
| 73 | `domains/asset_market/services/token_profile_current_projection.py` | 领域服务 | 358 | 必要但偏大 | Defines functions project_token_profile_current. | `d19591b37f3c` |
| 74 | `domains/asset_market/services/us_equity_symbol_sync.py` | 领域服务 | 147 | 必要 | Defines NasdaqTraderSymbol, NasdaqTraderSymbolClient. | `c788d98ed498` |
| 75 | `domains/asset_market/types/__init__.py` | 包标记/导出 | 21 | 必要: package/export | Python package marker and selected public re-exports. | `4be0f1743837` |
| 76 | `domains/asset_market/types/market_tick.py` | 值对象/类型 | 49 | 必要 | Defines MarketTick, EnrichedEventCapture. | `ee6d12eacf81` |
| 77 | `domains/asset_market/types/market_tick_id.py` | 值对象/类型 | 9 | 必要 | Defines functions market_tick_id. | `d12f2d124751` |
| 78 | `domains/closed_loop_harness/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 79 | `domains/closed_loop_harness/interfaces.py` | 域接口/跨域契约 | 7 | 必要 | Small constants or package glue. | `169c91648072` |
| 80 | `domains/closed_loop_harness/read_models/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 81 | `domains/closed_loop_harness/read_models/harness_service.py` | 读模型服务 | 154 | 必要 | Defines HarnessService. | `c6fe5433dd77` |
| 82 | `domains/closed_loop_harness/repositories/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 83 | `domains/closed_loop_harness/repositories/harness_repository.py` | Repository/SQL | 1065 | 必要但建议拆分 | Defines HarnessRepository. | `95e7bd1cf7f0` |
| 84 | `domains/closed_loop_harness/runtime/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 85 | `domains/closed_loop_harness/runtime/harness_ops_worker.py` | Worker/runtime | 111 | 必要 | Defines HarnessOpsWorker. | `9b0870f92e8b` |
| 86 | `domains/closed_loop_harness/scoring/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 87 | `domains/closed_loop_harness/scoring/harness_credit.py` | 评分/规则 | 45 | 必要 | Defines functions assign_cluster_credits, update_weight_stat. | `e02fe705428c` |
| 88 | `domains/closed_loop_harness/scoring/harness_scoring.py` | 评分/规则 | 49 | 必要 | Defines functions base_event_score, price_move_penalty, event_score, combined_score, ... | `3c34c7072e51` |
| 89 | `domains/closed_loop_harness/scoring/harness_settlement.py` | 评分/规则 | 24 | 必要 | Defines functions actual_return, expected_return, abnormal_return, normalized_outcome. | `20b8960e7045` |
| 90 | `domains/closed_loop_harness/services/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 91 | `domains/closed_loop_harness/services/harness_ops.py` | 领域服务 | 307 | 必要但偏大 | Defines functions materialize_market_ready_seeds, settle_harness_snapshots, attribute_harness_credits, update_harness_weights. | `7de6e8dfea68` |
| 92 | `domains/closed_loop_harness/services/harness_snapshot_builder.py` | 领域服务 | 434 | 必要但偏大 | Defines HarnessSnapshotBuilder. | `27485df46d2f` |
| 93 | `domains/evidence/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 94 | `domains/evidence/interfaces.py` | 域接口/跨域契约 | 42 | 必要 | Small constants or package glue. | `b708d4b2b895` |
| 95 | `domains/evidence/repositories/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 96 | `domains/evidence/repositories/entity_repository.py` | Repository/SQL | 170 | 必要 | Defines EntityRepository. | `622892e82c9f` |
| 97 | `domains/evidence/repositories/evidence_repository.py` | Repository/SQL | 274 | 必要但偏大 | Defines EvidenceRepository. | `c6ddaf6d1e6d` |
| 98 | `domains/evidence/services/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 99 | `domains/evidence/services/entity_extractor.py` | 领域服务 | 367 | 必要但偏大 | Defines TextSurface, ExtractedEntity. | `bd17cf5df61c` |
| 100 | `domains/evidence/services/ingest_service.py` | 领域服务 | 513 | 必要但建议拆分 | Defines PreparedIngest, IngestService. | `3dbd4e157c44` |
| 101 | `domains/evidence/types/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 102 | `domains/evidence/types/entity.py` | 值对象/类型 | 9 | 必要 | Small constants or package glue. | `8c56e657f15e` |
| 103 | `domains/evidence/types/tweet_identity.py` | 值对象/类型 | 15 | 必要 | Defines functions logical_dedup_key, canonical_tweet_url. | `c6321b56f1c9` |
| 104 | `domains/evidence/types/tweet_text.py` | 值对象/类型 | 75 | 必要 | Defines TextProjection. | `e616714011af` |
| 105 | `domains/evidence/types/twitter_event.py` | 值对象/类型 | 100 | 必要 | Defines Source, Author, Media, ... | `2a79c674b839` |
| 106 | `domains/ingestion/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 107 | `domains/ingestion/interfaces.py` | 域接口/跨域契约 | 17 | 必要 | Defines IngestedEvent. | `2bc396887c27` |
| 108 | `domains/ingestion/providers.py` | Provider 协议 | 29 | 必要 | Defines IngestStoreProtocol, EventPublisherProtocol, UpstreamClientProtocol. | `0a523967d76b` |
| 109 | `domains/ingestion/runtime/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 110 | `domains/ingestion/runtime/collector_service.py` | Worker/runtime | 227 | 必要但偏大 | Defines CollectorStatus, CollectorService. | `409f9259e863` |
| 111 | `domains/ingestion/services/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 112 | `domains/ingestion/services/normalizer.py` | 领域服务 | 270 | 必要但偏大 | Defines functions parse_gmgn_frame, normalize_gmgn_payload. | `3454f407c2a7` |
| 113 | `domains/ingestion/services/subscriptions.py` | 领域服务 | 28 | 必要 | Defines functions normalize_handles, event_matches_handles. | `a070ec7e488e` |
| 114 | `domains/ingestion/types/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 115 | `domains/ingestion/types/gmgn_token_payload.py` | 值对象/类型 | 109 | 必要 | Defines functions parse_gmgn_token_payload. | `6c3a4381dec3` |
| 116 | `domains/notifications/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 117 | `domains/notifications/interfaces.py` | 域接口/跨域契约 | 7 | 必要 | Small constants or package glue. | `73414d459a78` |
| 118 | `domains/notifications/repositories/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 119 | `domains/notifications/repositories/notification_repository.py` | Repository/SQL | 676 | 必要但建议拆分 | Defines NotificationRepository. | `46c9a356f110` |
| 120 | `domains/notifications/runtime/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 121 | `domains/notifications/runtime/notification_delivery.py` | Worker/runtime | 228 | 必要但偏大 | Defines AppriseNotificationAdapter, PushDeerNotificationAdapter, DeliveryClaim, ... | `675322dd3b12` |
| 122 | `domains/notifications/runtime/notification_worker.py` | Worker/runtime | 194 | 必要 | Defines NotificationProcessResult, NotificationWorker. | `60b96347db36` |
| 123 | `domains/notifications/services/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 124 | `domains/notifications/services/notification_rules.py` | 领域服务 | 908 | 必要但建议拆分 | Defines _PulseExternalPushPolicy, NotificationRuleEngine. | `4134dd81db82` |
| 125 | `domains/notifications/services/pulse_surface_card.py` | 领域服务 | 256 | 必要但偏大 | Pulse SurfaceCard renderer. Renders signal_pulse_candidate notification body from FinalDecision v2. Replaces t | `9f55c2c1488e` |
| 126 | `domains/notifications/types.py` | 领域模块 | 25 | 必要 | Defines NotificationCandidate. | `9956cca834fc` |
| 127 | `domains/pulse_lab/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 128 | `domains/pulse_lab/interfaces.py` | 域接口/跨域契约 | 88 | 必要 | Small constants or package glue. | `64d4d493b56b` |
| 129 | `domains/pulse_lab/prompts/__init__.py` | 包标记/导出 | 1 | 必要: package/export | Pulse agent stage prompts (markdown). | `24956a4377c7` |
| 130 | `domains/pulse_lab/providers.py` | Provider 协议 | 44 | 必要 | Defines PulseDecisionResult, PulseDecisionProvider. | `67132c66f294` |
| 131 | `domains/pulse_lab/queries/agent_tool_queries.py` | Query/SQL 读侧 | 316 | 必要但偏大 | Defines functions fetch_target_recent_tweets, fetch_target_price_action, fetch_official_token_profile, fetch_evidence_event_urls. | `52db5d3462c9` |
| 132 | `domains/pulse_lab/read_models/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 133 | `domains/pulse_lab/read_models/signal_pulse_service.py` | 读模型服务 | 338 | 必要但偏大 | Defines SignalPulseService. | `c86b9c6f1a14` |
| 134 | `domains/pulse_lab/repositories/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 135 | `domains/pulse_lab/repositories/pulse_repository.py` | Repository/SQL | 1858 | 必要但建议拆分 | Defines PulseAdmissionClaim, PulseRepository. | `0ff203ea8a20` |
| 136 | `domains/pulse_lab/runtime/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 137 | `domains/pulse_lab/runtime/pulse_candidate_worker.py` | Worker/runtime | 1345 | 必要但建议拆分 | Defines PulseCandidateContext, PulseTriggerThresholds, PulseCandidateWorker. | `4e738cb7e45f` |
| 138 | `domains/pulse_lab/services/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 139 | `domains/pulse_lab/services/agent_harness.py` | 领域服务 | 177 | 必要 | Defines functions build_pulse_harness_manifest, pulse_harness_hash. | `0ae8a5109dec` |
| 140 | `domains/pulse_lab/services/agent_harness_eval.py` | 领域服务 | 317 | 必要但偏大 | Deterministic eval grader v2 for the two-stage Pulse Agent Desk. v2 hard cut (plan 2026-05-16 Task 10): * v1 g | `5ca5ccb4060d` |
| 141 | `domains/pulse_lab/services/agent_routing.py` | 领域服务 | 128 | 必要 | Defines CompletenessResult. | `f2134e35de74` |
| 142 | `domains/pulse_lab/services/decision_mapping.py` | 领域服务 | 29 | 必要 | Defines functions candidate_fields_from_decision. | `140408a8ce0e` |
| 143 | `domains/pulse_lab/services/prompt_loader.py` | 领域服务 | 82 | 必要 | Load pulse agent prompts from markdown files with route-specific sections. Each prompt file lives at ``domains | `7afc52ab9f00` |
| 144 | `domains/pulse_lab/services/pulse_admission_policy.py` | 领域服务 | 87 | 必要 | Defines PulseAdmissionDecision, PulseAdmissionPolicy. | `382b73f6825c` |
| 145 | `domains/pulse_lab/services/pulse_candidate_gate.py` | 领域服务 | 211 | 必要但偏大 | Defines PulseGateResult, PulseGateThresholds. | `0e636c9209bc` |
| 146 | `domains/pulse_lab/services/pulse_edge_events.py` | 领域服务 | 178 | 必要 | Defines functions build_pulse_edge_state, diff_pulse_edge_events, pulse_edge_signature. | `eb38d0a82e92` |
| 147 | `domains/pulse_lab/services/pulse_timeline_context.py` | 领域服务 | 592 | 必要但建议拆分 | Defines functions build_pulse_timeline_context. | `cb53e70afeb9` |
| 148 | `domains/pulse_lab/types/__init__.py` | 包标记/导出 | 31 | 必要: package/export | Python package marker and selected public re-exports. | `efe56fcf5097` |
| 149 | `domains/pulse_lab/types/agent_decision.py` | 值对象/类型 | 297 | 必要但偏大 | Defines BullBearView, TradePlaybook, InvestigationReport, ... | `4dddac7fb3ad` |
| 150 | `domains/social_enrichment/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 151 | `domains/social_enrichment/interfaces.py` | 域接口/跨域契约 | 21 | 必要 | Small constants or package glue. | `855eba675b70` |
| 152 | `domains/social_enrichment/providers.py` | Provider 协议 | 30 | 必要 | Defines SocialEventEnrichmentProvider. | `d249c19ed249` |
| 153 | `domains/social_enrichment/repositories/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 154 | `domains/social_enrichment/repositories/enrichment_repository.py` | Repository/SQL | 474 | 必要但偏大 | Defines EnrichmentRepository. | `43ef109f1113` |
| 155 | `domains/social_enrichment/runtime/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 156 | `domains/social_enrichment/runtime/enrichment_worker.py` | Worker/runtime | 236 | 必要但偏大 | Defines EnrichmentWorker. | `ec661c0b6fba` |
| 157 | `domains/social_enrichment/services/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 158 | `domains/social_enrichment/services/watched_event_gate.py` | 领域服务 | 142 | 必要 | Defines functions watched_social_event_priority, should_enqueue_watched_social_event_text, event_text. | `74aa9719da70` |
| 159 | `domains/social_enrichment/types/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 160 | `domains/social_enrichment/types/social_event_extraction.py` | 值对象/类型 | 344 | 必要但偏大 | Defines AnchorTermPayload, SocialTokenCandidatePayload, SocialEventPayload, ... | `b63d35932599` |
| 161 | `domains/token_intel/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 162 | `domains/token_intel/_constants.py` | 领域模块 | 22 | 必要 | Small constants or package glue. | `0ac16fa0a094` |
| 163 | `domains/token_intel/interfaces.py` | 域接口/跨域契约 | 74 | 必要 | Small constants or package glue. | `e6000c8e3aee` |
| 164 | `domains/token_intel/queries/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 165 | `domains/token_intel/queries/event_rebuild_query.py` | Query/SQL 读侧 | 23 | 必要 | Defines EventRebuildQuery. | `5b2bc66a5b6a` |
| 166 | `domains/token_intel/queries/event_token_projection_query.py` | Query/SQL 读侧 | 203 | 必要但偏大 | Defines EventTokenProjectionQuery. | `cfb28c6175e6` |
| 167 | `domains/token_intel/queries/search_events_query.py` | Query/SQL 读侧 | 513 | 必要但建议拆分 | Defines SearchEventsQuery. | `0e0dddea27a9` |
| 168 | `domains/token_intel/queries/stocks_radar_query.py` | Query/SQL 读侧 | 69 | 必要 | Defines StocksRadarQuery. | `aa1fcc2a9a4d` |
| 169 | `domains/token_intel/queries/token_radar_source_query.py` | Query/SQL 读侧 | 271 | 必要但偏大 | Defines TokenRadarSourceQuery. | `e12ef765cc26` |
| 170 | `domains/token_intel/read_models/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 171 | `domains/token_intel/read_models/asset_flow_service.py` | 读模型服务 | 222 | 必要但偏大 | Defines AssetFlowService. | `96713bd5c102` |
| 172 | `domains/token_intel/read_models/catalyst_ranking_service.py` | 读模型服务 | 180 | 必要 | Defines CatalystRankingService. | `f329c6a8dd45` |
| 173 | `domains/token_intel/read_models/search_agent_brief.py` | 读模型服务 | 384 | 必要但偏大 | Defines functions build_token_agent_brief, build_topic_agent_brief. | `f8cf291a3fc9` |
| 174 | `domains/token_intel/read_models/search_inspect_service.py` | 读模型服务 | 165 | 必要 | Defines SearchInspectService. | `8f7a051607d2` |
| 175 | `domains/token_intel/read_models/search_service.py` | 读模型服务 | 328 | 必要但偏大 | Defines SearchPage, SearchCursorError, _CursorState, ... | `96b65c4b9bae` |
| 176 | `domains/token_intel/read_models/stocks_radar_service.py` | 读模型服务 | 177 | 必要 | Defines StocksRadarService. | `1db7a54a6dc9` |
| 177 | `domains/token_intel/read_models/token_case_service.py` | 读模型服务 | 177 | 必要 | Defines TokenCaseTargetNotFound, TokenCaseInvalidScope, TokenCaseService. | `4d38fb9e8a37` |
| 178 | `domains/token_intel/read_models/token_target_cursor.py` | 读模型服务 | 21 | 必要 | Defines TokenTargetCursorError. | `3ca2fc8ad13e` |
| 179 | `domains/token_intel/read_models/token_target_post_serializer.py` | 读模型服务 | 71 | 必要 | Defines functions token_target_post_payload. | `75f0d1a4af22` |
| 180 | `domains/token_intel/read_models/token_target_posts_service.py` | 读模型服务 | 88 | 必要 | Defines TokenTargetPostsCursorError, TokenTargetPostsRangeError, TokenTargetPostsSortError, ... | `9726421fea07` |
| 181 | `domains/token_intel/read_models/token_target_social_timeline_service.py` | 读模型服务 | 223 | 必要但偏大 | Defines TokenTargetSocialTimelineService. | `68d2d13cfb3e` |
| 182 | `domains/token_intel/read_models/token_target_stage_builder.py` | 读模型服务 | 239 | 必要但偏大 | Defines TokenTargetStageBuild. | `be6d1be75a9d` |
| 183 | `domains/token_intel/repositories/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 184 | `domains/token_intel/repositories/intent_resolution_repository.py` | Repository/SQL | 161 | 必要 | Defines IntentResolutionRepository. | `1e071a3da81f` |
| 185 | `domains/token_intel/repositories/projection_repository.py` | Repository/SQL | 373 | 必要但偏大 | Defines ProjectionRepository. | `1a2360d5e49e` |
| 186 | `domains/token_intel/repositories/signal_repository.py` | Repository/SQL | 156 | 必要 | Defines SignalAlert, SignalRepository. | `b9e253334303` |
| 187 | `domains/token_intel/repositories/token_evidence_repository.py` | Repository/SQL | 82 | 必要 | Defines TokenEvidenceRepository. | `da36a9f74b1c` |
| 188 | `domains/token_intel/repositories/token_factor_evaluation_repository.py` | Repository/SQL | 146 | 必要 | Defines TokenFactorEvaluationRepository. | `bad5154a8012` |
| 189 | `domains/token_intel/repositories/token_intent_lookup_repository.py` | Repository/SQL | 132 | 必要 | Defines TokenIntentLookupRepository. | `67362c1e1308` |
| 190 | `domains/token_intel/repositories/token_intent_repository.py` | Repository/SQL | 136 | 必要 | Defines TokenIntentRepository. | `ca89b95a144d` |
| 191 | `domains/token_intel/repositories/token_radar_repository.py` | Repository/SQL | 344 | 必要但偏大 | Defines TokenRadarRepository. | `67ab64aed55e` |
| 192 | `domains/token_intel/repositories/token_target_repository.py` | Repository/SQL | 322 | 必要但偏大 | Defines TokenTargetRepository. | `2a1249d86302` |
| 193 | `domains/token_intel/runtime/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 194 | `domains/token_intel/runtime/token_intent_rebuild.py` | Worker/runtime | 162 | 必要 | Defines functions rebuild_recent_token_intents, rebuild_event_token_intents. | `7d1575939bcc` |
| 195 | `domains/token_intel/runtime/token_radar_projection_worker.py` | Worker/runtime | 252 | 必要但偏大 | Defines TokenRadarProjectionWorker. | `d92338a65225` |
| 196 | `domains/token_intel/runtime/token_resolution_refresh.py` | Worker/runtime | 100 | 必要 | Defines functions refresh_recent_token_state, reprocess_recent_token_intents, deferred_token_radar_projection. | `ad9870278a7b` |
| 197 | `domains/token_intel/scoring/__init__.py` | 包标记/导出 | 15 | 必要: package/export | Python package marker and selected public re-exports. | `5c48348ca72b` |
| 198 | `domains/token_intel/scoring/baseline_scoring.py` | 评分/规则 | 108 | 必要 | Defines functions token_baseline_v2, baseline_health, robust_z_score, ewma_stats. | `f20c57f95af0` |
| 199 | `domains/token_intel/scoring/cross_section_normalizer.py` | 评分/规则 | 69 | 必要 | Per-window cross-sectional rank normalization within an active cohort. | `176ef2f060ea` |
| 200 | `domains/token_intel/scoring/diffusion_health.py` | 评分/规则 | 152 | 必要 | Defines functions text_fingerprint, diffusion_health. | `579e363ba53b` |
| 201 | `domains/token_intel/scoring/factor_cohort.py` | 评分/规则 | 42 | 必要 | Cohort membership for cross-sectional factor normalization. | `af267fa97a81` |
| 202 | `domains/token_intel/scoring/factor_diagnostics.py` | 评分/规则 | 98 | 必要 | Defines functions factor_distribution_report. | `766d37a44e48` |
| 203 | `domains/token_intel/scoring/factor_snapshot.py` | 评分/规则 | 864 | 必要但建议拆分 | Defines functions build_token_factor_snapshot. | `9ae609307c59` |
| 204 | `domains/token_intel/scoring/factor_snapshot_contract.py` | 评分/规则 | 170 | 必要 | Defines functions require_token_factor_snapshot, is_token_factor_snapshot. | `7163b5d237fa` |
| 205 | `domains/token_intel/scoring/post_text_quality.py` | 评分/规则 | 93 | 必要 | Defines functions post_text_features, post_quality_score. | `dd90d18772ba` |
| 206 | `domains/token_intel/scoring/scoring_common.py` | 评分/规则 | 84 | 必要 | Defines functions score_payload, apply_risk_caps, contribution, cap, ... | `ad0dfbef99a1` |
| 207 | `domains/token_intel/scoring/social_signal_features.py` | 评分/规则 | 152 | 必要 | Defines functions source_weighted_effective_authors, time_to_nth_independent_author_ms, public_followup_author_count, author_entropy. | `74f61755f003` |
| 208 | `domains/token_intel/scoring/token_radar_feature_builder.py` | 评分/规则 | 374 | 必要但偏大 | Defines RadarFeatureSet. | `03fcba05bfc0` |
| 209 | `domains/token_intel/services/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 210 | `domains/token_intel/services/atomic_mention.py` | 领域服务 | 70 | 必要 | Per-mention atomic signal helpers (pure functions, no I/O). | `c27114e60196` |
| 211 | `domains/token_intel/services/deterministic_token_resolver.py` | 领域服务 | 490 | 必要但偏大 | Defines MentionKeys, DeterministicResolution, DeterministicTokenResolver. | `e8e19683f1ac` |
| 212 | `domains/token_intel/services/query_parser.py` | 领域服务 | 100 | 必要 | Defines SearchIntent. | `8e0da9d01672` |
| 213 | `domains/token_intel/services/search_aliases.py` | 领域服务 | 100 | 必要 | Defines functions canonical_symbol_for_query, fuzzy_canonical_symbol_for_query, target_symbols_for_or_query, expanded_lexical_query. | `406ea2464430` |
| 214 | `domains/token_intel/services/token_evidence_builder.py` | 领域服务 | 197 | 必要 | Defines TokenEvidenceInput. | `54bdc968f7c7` |
| 215 | `domains/token_intel/services/token_factor_evaluation.py` | 领域服务 | 383 | 必要但偏大 | Defines functions settle_token_factor_scores. | `7534418231ba` |
| 216 | `domains/token_intel/services/token_intent_builder.py` | 领域服务 | 223 | 必要但偏大 | Defines TokenIntentEvidenceLink, TokenIntentInput. | `d48aefc907cf` |
| 217 | `domains/token_intel/services/token_intent_resolver.py` | 领域服务 | 112 | 必要 | Defines TokenIntentResolver. | `12695b0c10d5` |
| 218 | `domains/token_intel/services/token_radar_projection.py` | 领域服务 | 1057 | 必要但建议拆分 | Defines TokenRadarProjection. | `692b82efa751` |
| 219 | `domains/watchlist_intel/__init__.py` | 包标记/导出 | 1 | 必要: package/export | Watchlist account-level topic intelligence. | `acff8ba83b06` |
| 220 | `domains/watchlist_intel/interfaces.py` | 域接口/跨域契约 | 13 | 必要 | Small constants or package glue. | `66dbc0b8a435` |
| 221 | `domains/watchlist_intel/providers.py` | Provider 协议 | 32 | 必要 | Defines HandleTopicSummaryProvider. | `583443419624` |
| 222 | `domains/watchlist_intel/repositories/__init__.py` | 包标记/导出 | 3 | 必要: package/export | Python package marker and selected public re-exports. | `b1a46a55bdc7` |
| 223 | `domains/watchlist_intel/repositories/watchlist_intel_repository.py` | Repository/SQL | 899 | 必要但建议拆分 | Defines WatchlistIntelRepository. | `6845404facbc` |
| 224 | `domains/watchlist_intel/runtime/__init__.py` | 包标记/导出 | 3 | 必要: package/export | Python package marker and selected public re-exports. | `fac283c2198f` |
| 225 | `domains/watchlist_intel/runtime/handle_summary_worker.py` | Worker/runtime | 266 | 必要但偏大 | Defines HandleSummaryWorker. | `59b0c38ecfa1` |
| 226 | `domains/watchlist_intel/services/__init__.py` | 包标记/导出 | 7 | 必要: package/export | Python package marker and selected public re-exports. | `ebe98d6d86e6` |
| 227 | `domains/watchlist_intel/services/handle_summary_service.py` | 领域服务 | 376 | 必要但偏大 | Defines HandleSummaryTriggerConfig, HandleSummaryInputs, WatchlistHandleSummaryService, ... | `9b198ec6f859` |
| 228 | `domains/watchlist_intel/types/__init__.py` | 包标记/导出 | 79 | 必要: package/export | Python package marker and selected public re-exports. | `bec08452f0ad` |
| 229 | `integrations/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 230 | `integrations/binance/__init__.py` | 包标记/导出 | 1 | 必要: package/export | Binance public web adapters. | `fecbae4d84f8` |
| 231 | `integrations/binance/cex_profile_client.py` | 外部适配器 | 91 | 必要 | Defines BinanceCexProfileClient. | `9a4370bcfb4e` |
| 232 | `integrations/binance/web3_token_client.py` | 外部适配器 | 172 | 必要 | Defines BinanceWeb3TokenMetadata, BinanceWeb3TokenClient. | `e84df5d7c4bb` |
| 233 | `integrations/coingecko/__init__.py` | 包标记/导出 | 6 | 必要: package/export | Python package marker and selected public re-exports. | `6c7aeed03536` |
| 234 | `integrations/coingecko/search_client.py` | 外部适配器 | 88 | 需确认: 源码未接线 | Defines CoingeckoSearchHit, CoingeckoSearchClient. | `4e3849edb1f9` |
| 235 | `integrations/gmgn/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 236 | `integrations/gmgn/direct_ws.py` | 外部适配器 | 216 | 必要但偏大 | Defines UpstreamIdleTimeoutError, DirectGmgnWebSocketClient. | `ee827cb3fc0e` |
| 237 | `integrations/gmgn/directory_client.py` | 外部适配器 | 167 | 必要 | Defines GmgnDirectoryError, GmgnDirectoryEntry, GmgnDirectoryPage, ... | `d33e69377834` |
| 238 | `integrations/gmgn/openapi_client.py` | 外部适配器 | 446 | 必要但偏大 | Defines GmgnTokenInfo, GmgnTokenKlineCandle, GmgnTokenInfoLookup, ... | `0e17d017f55f` |
| 239 | `integrations/gmgn/openapi_gateway.py` | 外部适配器 | 175 | 必要 | Defines GmgnOpenApiRoute, GmgnOpenApiGateway, _WeightedLeakyBucket. | `f5dec074054a` |
| 240 | `integrations/marketlane/__init__.py` | 包标记/导出 | 5 | 必要: package/export | Python package marker and selected public re-exports. | `43930f3d4cde` |
| 241 | `integrations/marketlane/quote_provider.py` | 外部适配器 | 71 | 必要 | Defines MarketlaneQuoteProvider. | `50dab04be357` |
| 242 | `integrations/okx/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 243 | `integrations/okx/cex_client.py` | 外部适配器 | 206 | 必要但偏大 | Defines OkxClientError, OkxCexClient. | `ca81428fae1b` |
| 244 | `integrations/okx/chains.py` | 外部适配器 | 22 | 必要 | Small constants or package glue. | `a31934dcc4d4` |
| 245 | `integrations/okx/dex_client.py` | 外部适配器 | 264 | 必要但偏大 | Defines OkxDexClient. | `12ed12aaa5e2` |
| 246 | `integrations/okx/dex_ws_client.py` | 外部适配器 | 340 | 必要但偏大 | Defines OkxDexWsClientError, OkxDexPriceInfoUpdate, OkxDexWebSocketMarketProvider. | `3b35e94c852d` |
| 247 | `integrations/okx/models.py` | 外部适配器 | 62 | 必要 | Defines OkxCexInstrument, OkxCexTicker, OkxCandle, ... | `6fa0db95e79c` |
| 248 | `integrations/openai_agents/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 249 | `integrations/openai_agents/instructor_safety_net.py` | 外部适配器 | 243 | 必要但偏大 | Instructor-backed safety net for openai-agents-python SDK call failures. Design: - Does NOT participate in the | `5f9e52818058` |
| 250 | `integrations/openai_agents/pulse_decision_agent_client.py` | 外部适配器 | 1085 | 必要但建议拆分 | Defines PulseDecisionAgentResult, _JsonOutputSchema, OpenAIAgentsPulseDecisionClient. | `57a2c07d2416` |
| 251 | `integrations/openai_agents/social_event_agent_client.py` | 外部适配器 | 223 | 必要但偏大 | Defines OpenAIAgentsSocialEventClient. | `3bce8f434deb` |
| 252 | `integrations/openai_agents/tools/__init__.py` | 包标记/导出 | 46 | 必要: package/export | Python package marker and selected public re-exports. | `909186bb447e` |
| 253 | `integrations/openai_agents/tools/_context.py` | 外部适配器 | 61 | 必要 | Internal shared types for Investigator tools. Lives in a private module so individual tool files can import `` | `d1b03dba8077` |
| 254 | `integrations/openai_agents/tools/official_profile.py` | 外部适配器 | 68 | 必要 | ``get_official_token_profile``: pull the canonical asset_profiles row. Returns the most recent ``status='ready | `f1461cd1fbd9` |
| 255 | `integrations/openai_agents/tools/price_action.py` | 外部适配器 | 86 | 必要 | ``get_target_price_action``: summarise market_ticks for a Pulse target. Aggregates the configured time window  | `ef02c10392cc` |
| 256 | `integrations/openai_agents/tools/recent_tweets.py` | 外部适配器 | 100 | 必要 | ``get_target_recent_tweets``: fetch 24h tweets for a Pulse target. Ranked by ``token_intent_resolutions.resolu | `87e01dc26b10` |
| 257 | `integrations/openai_agents/watchlist_summary_agent_client.py` | 外部适配器 | 517 | 必要但建议拆分 | Defines WatchlistTopicPayload, WatchlistHandleSummaryPayload, _WatchlistOutputSchema, ... | `41a71f2db1df` |
| 258 | `platform/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 259 | `platform/config/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 260 | `platform/config/settings.py` | 配置模型 | 1230 | 必要但建议拆分 | Defines ApiConfig, PostgresConfig, StorageConfig, ... | `b0f2b29df501` |
| 261 | `platform/db/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 262 | `platform/db/alembic/env.py` | Alembic 环境 | 62 | 必要 | Defines functions run_migrations_offline, run_migrations_online. | `6afcd0ac8894` |
| 263 | `platform/db/alembic/versions/20260506_0001_initial_postgresql.py` | DB 迁移 | 740 | 历史必要: schema 链 | Defines functions upgrade, downgrade. | `af5075f7cf85` |
| 264 | `platform/db/alembic/versions/20260506_0002_postgres_queue_claims.py` | DB 迁移 | 46 | 历史必要: schema 链 | Defines functions upgrade, downgrade. | `367398b57e71` |
| 265 | `platform/db/alembic/versions/20260506_0003_enrichment_stale_running_claims.py` | DB 迁移 | 32 | 历史必要: schema 链 | Support stale-running enrichment job recovery. | `b7aca1a04626` |
| 266 | `platform/db/alembic/versions/20260506_0004_projection_operations.py` | DB 迁移 | 209 | 历史必要: schema 链 | Add PostgreSQL projection operation tables. | `4537abe7350f` |
| 267 | `platform/db/alembic/versions/20260506_0005_asset_identity_resolution.py` | DB 迁移 | 401 | 历史必要: schema 链 | Add asset identity resolution tables. | `ab47e1c9d516` |
| 268 | `platform/db/alembic/versions/20260507_0006_asset_market_sync_indexes.py` | DB 迁移 | 31 | 历史必要: schema 链 | Add indexes for asset market refresh scheduling. | `a1df76309a25` |
| 269 | `platform/db/alembic/versions/20260507_0007_token_radar_v3_intents.py` | DB 迁移 | 301 | 历史必要: schema 链 | Add Token Radar V3 intent and read-model tables. | `c3230e6c2324` |
| 270 | `platform/db/alembic/versions/20260507_0008_token_radar_deterministic_registry.py` | DB 迁移 | 268 | 历史必要: schema 链 | Add token radar deterministic registry and price observations. | `f975672e973a` |
| 271 | `platform/db/alembic/versions/20260507_0009_token_discovery_results.py` | DB 迁移 | 70 | 历史必要: schema 链 | Replace discovery task queue with discovery result facts. | `0d17c39a6d55` |
| 272 | `platform/db/alembic/versions/20260507_0010_agents_sdk_model_run_audit.py` | DB 迁移 | 55 | 历史必要: schema 链 | Add OpenAI Agents SDK run audit columns. | `be051d352a75` |
| 273 | `platform/db/alembic/versions/20260508_0011_event_price_observations.py` | DB 迁移 | 78 | 历史必要: schema 链 | Add message attribution to price observations. | `2b843c3f5e1c` |
| 274 | `platform/db/alembic/versions/20260508_0012_prune_legacy_token_radar_projection.py` | DB 迁移 | 46 | 历史必要: schema 链 | Prune non-current token radar projection rows. | `73a409a8b732` |
| 275 | `platform/db/alembic/versions/20260508_0013_retire_legacy_token_resolutions.py` | DB 迁移 | 27 | 历史必要: schema 链 | Retire non-current token resolver policies. | `926505873cf4` |
| 276 | `platform/db/alembic/versions/20260508_0014_prune_token_radar_v6_projection.py` | DB 迁移 | 46 | 历史必要: schema 链 | Prune token radar rows outside the v6 auditable contract. | `330306ed9092` |
| 277 | `platform/db/alembic/versions/20260508_0015_signal_pulse_agent_hard_cut.py` | DB 迁移 | 224 | 历史必要: schema 链 | Add Signal Lab Pulse agent storage foundation. | `b4e962b34ce5` |
| 278 | `platform/db/alembic/versions/20260509_0016_account_profile_gmgn_directory_columns.py` | DB 迁移 | 41 | 历史必要: schema 链 | Add GMGN account directory columns to account_profiles. | `582a915c958d` |
| 279 | `platform/db/alembic/versions/20260509_0017_demote_search_only_registry_assets.py` | DB 迁移 | 91 | 历史必要: schema 链 | Demote unretained OKX DEX search-only registry assets. | `5ca4ed90109a` |
| 280 | `platform/db/alembic/versions/20260509_0018_demote_search_tail_candidate_audit_refs.py` | DB 迁移 | 85 | 历史必要: schema 链 | Demote search-only tails still referenced only by candidate audit lists. | `141e544ba334` |
| 281 | `platform/db/alembic/versions/20260509_0019_demote_symbol_search_tail_targets.py` | DB 迁移 | 89 | 历史必要: schema 链 | Demote symbol-search tails while preserving explicit address targets. | `45319768533f` |
| 282 | `platform/db/alembic/versions/20260509_0020_sweep_symbol_search_tail_assets.py` | DB 迁移 | 89 | 历史必要: schema 链 | Sweep remaining symbol-search tail assets. | `db1c960adc71` |
| 283 | `platform/db/alembic/versions/20260510_0021_asset_identity_evidence_hard_cut.py` | DB 迁移 | 207 | 历史必要: schema 链 | Add asset identity evidence ledger and current identity read model. | `bae53f434da4` |
| 284 | `platform/db/alembic/versions/20260510_0022_token_radar_factor_snapshot_hard_cut.py` | DB 迁移 | 66 | 历史必要: schema 链 | Add token radar factor snapshot hard-cut storage. | `2c2c86d40a42` |
| 285 | `platform/db/alembic/versions/20260510_0023_drop_signal_pulse_legacy_json_fields.py` | DB 迁移 | 26 | 历史必要: schema 链 | Drop legacy Signal Pulse score-centered JSON fields. | `4e19d652fc75` |
| 286 | `platform/db/alembic/versions/20260511_0024_price_observation_field_indexes.py` | DB 迁移 | 109 | 历史必要: schema 链 | Add field-aware price observation indexes and radar coverage. | `92350c4d9184` |
| 287 | `platform/db/alembic/versions/20260511_0025_token_radar_production_read_models.py` | DB 迁移 | 112 | 历史必要: schema 链 | Add production read models for token radar. | `7e4c42490864` |
| 288 | `platform/db/alembic/versions/20260511_0026_token_factor_eval_diagnostics.py` | DB 迁移 | 91 | 历史必要: schema 链 | Add token factor evaluation diagnostics columns and indexes. | `862e7cd05e55` |
| 289 | `platform/db/alembic/versions/20260511_0027_prune_legacy_pulse_factor_snapshots.py` | DB 迁移 | 31 | 历史必要: schema 链 | Prune Pulse rows carrying legacy token factor snapshots. | `9149d3e1b0f8` |
| 290 | `platform/db/alembic/versions/20260511_0028_prune_gmgn_payload_market_data.py` | DB 迁移 | 89 | 历史必要: schema 链 | Hard-cut GMGN payload market data. | `5c1d943c550e` |
| 291 | `platform/db/alembic/versions/20260511_0029_anchor_live_hard_cut.py` | DB 迁移 | 70 | 历史必要: schema 链 | Hard-cut Token Radar anchor/live market boundary. | `74995637ed23` |
| 292 | `platform/db/alembic/versions/20260511_0030_prune_pulse_snapshots_without_market.py` | DB 迁移 | 32 | 历史必要: schema 链 | Prune Pulse rows missing token factor market section. | `1e622d94fd3d` |
| 293 | `platform/db/alembic/versions/20260512_0031_prune_legacy_pulse_factor_contracts.py` | DB 迁移 | 31 | 历史必要: schema 链 | Prune Pulse rows carrying non-current token factor contracts. | `dad468491d47` |
| 294 | `platform/db/alembic/versions/20260512_0032_search_v2_hard_cut.py` | DB 迁移 | 51 | 历史必要: schema 链 | Hard cut search v2 FTS and trigram indexes. | `26f820b98a81` |
| 295 | `platform/db/alembic/versions/20260512_0033_reconcile_search_v2_local_revision.py` | DB 迁移 | 16 | 历史必要: schema 链 | Reconcile search v2 local migration head. | `8413fc40fdb4` |
| 296 | `platform/db/alembic/versions/20260512_0034_us_equity_symbol_universe.py` | DB 迁移 | 49 | 历史必要: schema 链 | Add US equity symbol universe for non-crypto cashtag classification. | `5d9c958f3ca8` |
| 297 | `platform/db/alembic/versions/20260513_0035_asset_profiles.py` | DB 迁移 | 58 | 历史必要: schema 链 | Add current asset profile facts. | `215e5dfc4fb3` |
| 298 | `platform/db/alembic/versions/20260513_0036_token_radar_kappa_cqrs_hard_cut.py` | DB 迁移 | 344 | 历史必要: schema 链 | Hard-cut Token Radar market facts into Kappa/CQRS observation roles. | `19bb02057f2c` |
| 299 | `platform/db/alembic/versions/20260514_0037_unified_agent_runtime_phase0b.py` | DB 迁移 | 142 | 历史必要: schema 链 | Hard-cut Signal Pulse to unified agent runtime decisions. | `97e2c409456b` |
| 300 | `platform/db/alembic/versions/20260514_0038_agent_harness_closed_loop.py` | DB 迁移 | 107 | 历史必要: schema 链 | Add closed-loop agent harness ledger. | `a339ccf4ce6b` |
| 301 | `platform/db/alembic/versions/20260514_0039_reconcile_local_agent_harness_revision.py` | DB 迁移 | 16 | 历史必要: schema 链 | Reconcile local agent harness migration head. | `804724f42d8c` |
| 302 | `platform/db/alembic/versions/20260514_0040_repair_pulse_agent_job_cooldown.py` | DB 迁移 | 39 | 历史必要: schema 链 | Repair pulse agent job cooldown column on pre-existing tables. | `15434ad138a1` |
| 303 | `platform/db/alembic/versions/20260514_0041_pulse_worker_edge_notifications_hard_cut.py` | DB 迁移 | 184 | 历史必要: schema 链 | Hard-cut Signal Pulse worker to edge-state notifications. | `8fd65f7d8a77` |
| 304 | `platform/db/alembic/versions/20260514_0042_harden_pulse_agent_run_outcome.py` | DB 迁移 | 18 | 历史必要: schema 链 | Harden Signal Pulse agent run outcome contract. | `0d69b6fec592` |
| 305 | `platform/db/alembic/versions/20260514_0043_token_radar_listed_lookup_index.py` | DB 迁移 | 32 | 历史必要: schema 链 | Add Token Radar listed-at lookup index. | `46f143ed80f2` |
| 306 | `platform/db/alembic/versions/20260514_0044_pulse_harness_hash_history.py` | DB 迁移 | 45 | 历史必要: schema 链 | Allow Pulse harness hash history per model identity. | `5fbb2153ebac` |
| 307 | `platform/db/alembic/versions/20260514_0045_watchlist_handle_intel.py` | DB 迁移 | 96 | 历史必要: schema 链 | Add watchlist handle intel summary tables. | `f37ae2480da0` |
| 308 | `platform/db/alembic/versions/20260515_0046_event_anchor_capture_redesign.py` | DB 迁移 | 176 | 历史必要: schema 链 | Add event-anchored market tick capture facts. | `2b6172b0d4be` |
| 309 | `platform/db/alembic/versions/20260516_0047_market_ticks_gmgn_dex_quote_provider.py` | DB 迁移 | 30 | 历史必要: schema 链 | Allow GMGN DEX quote market tick provider facts. | `363e6de3452d` |
| 310 | `platform/db/alembic/versions/20260516_0048_agent_safety_net_audit.py` | DB 迁移 | 52 | 历史必要: schema 链 | Add safety_net audit columns to agent run-step tables. PR 2 of unified-agent-worker-runtime. PR 1 wrote safety | `392308176e6d` |
| 311 | `platform/db/alembic/versions/20260516_0049_enriched_event_async_backfill.py` | DB 迁移 | 89 | 历史必要: schema 链 | Async event-anchor backfill: pending-backfill index + narrow trigger allowance. The collector hot path can no  | `9e4ef8c3d4e4` |
| 312 | `platform/db/alembic/versions/20260516_0050_drop_legacy_asset_stack.py` | DB 迁移 | 78 | 历史必要: schema 链 | Drop legacy asset stack and orphan price tables. P0 follow-up to the 2026-05-16 backend architecture audit. Th | `3ddcace69b0c` |
| 313 | `platform/db/alembic/versions/20260516_0051_pulse_agent_desk_redesign.py` | DB 迁移 | 61 | 历史必要: schema 链 | Pulse agent desk redesign: drop narrative_type + flip stage CHECK to two-stage. Atomic hard cut performed alon | `899a166c0ade` |
| 314 | `platform/db/alembic/versions/20260517_0052_token_profile_current.py` | DB 迁移 | 68 | 历史必要: schema 链 | Add canonical token profile current read model. | `47b648464177` |
| 315 | `platform/db/alembic/versions/20260517_0053_reconcile_legacy_asset_stack_drop.py` | DB 迁移 | 54 | 历史必要: schema 链 | Reconcile legacy asset stack drop after duplicate local 0050 revision. Some local/dev databases were stamped w | `133ff69d28bc` |
| 316 | `platform/db/alembic/versions/20260517_0054_token_radar_materialized_listed_at.py` | DB 迁移 | 59 | 历史必要: schema 链 | Materialize Token Radar listed-at time. | `966f87b1fd5d` |
| 317 | `platform/db/alembic/versions/20260517_0055_public_read_path_indexes.py` | DB 迁移 | 73 | 历史必要: schema 链 | Add indexed public read path lookups. | `c6e5aa3bb72f` |
| 318 | `platform/db/alembic/versions/20260517_0056_recent_payload_batch_indexes.py` | DB 迁移 | 61 | 历史必要: schema 链 | Add event indexes for batched recent payload hydration. | `4244e5df1bd0` |
| 319 | `platform/db/alembic/versions/20260517_0057_cex_token_static_icons.py` | DB 迁移 | 30 | 历史必要: schema 链 | Add static CEX token icon source fields. | `117634b0d84e` |
| 320 | `platform/db/alembic/versions/20260517_0058_binance_profile_sources.py` | DB 迁移 | 109 | 历史必要: schema 链 | Move Binance token profiles into source cache tables. | `95c2a881fe18` |
| 321 | `platform/db/alembic/versions/20260517_0059_pulse_control_plane_kiss.py` | DB 迁移 | 50 | 历史必要: schema 链 | Add Signal Pulse admission budgets and suppression state. | `176893f18f38` |
| 322 | `platform/db/json_safety.py` | 数据库基础设施 | 19 | 必要 | Defines functions postgres_safe_json, postgres_safe_text. | `e36ff17256df` |
| 323 | `platform/db/postgres_audit.py` | 数据库基础设施 | 354 | 必要但偏大 | Defines PostgresOperationalAudit, PostgresQueryAudit, ProjectionValidationAudit. | `619b0b12746d` |
| 324 | `platform/db/postgres_client.py` | 数据库基础设施 | 190 | 必要 | Defines functions with_password_from_file, local_docker_host_dsn, create_pool, connect_postgres, ... | `66cccc21f6e5` |
| 325 | `platform/db/postgres_migrations.py` | 数据库基础设施 | 23 | 必要 | Defines functions alembic_config, upgrade_head, latest_migration_version. | `58fdb3c26759` |
| 326 | `platform/logging/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 327 | `platform/logging/setup.py` | 日志基础设施 | 32 | 必要 | Defines functions setup_logging. | `0da6fd5a8b8d` |
| 328 | `platform/paths/__init__.py` | 包标记/导出 | 0 | 必要: package/export | Python package marker and selected public re-exports. | `e3b0c44298fc` |
| 329 | `platform/paths/runtime_paths.py` | 运行路径基础设施 | 25 | 必要 | Defines functions app_home, app_log_path, config_path, workers_config_path. | `e6a8141d0ab7` |
