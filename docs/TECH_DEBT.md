# Tech Debt

> **Scope.** Append-only log of tracked technical debt. Verification artefacts that surface follow-up items append rows here rather than burying them in per-feature `verification.md` files.

## Schema

| Field | Meaning |
|-------|---------|
| Description | One-line summary of the debt. |
| Introduced | Commit SHA or spec slug that introduced it. |
| Area | One of `collector`, `pipeline`, `storage`, `retrieval`, `api`, `web`, `harness`, `infra`. |
| Severity | `low`, `medium`, `high`. |
| Impact | One sentence on what it costs us to leave this. |
| Owner | Name or `unowned`. |

Order rows by severity (high first) then by date introduced (oldest first).

## Open

| Description | Introduced | Area | Severity | Impact | Owner |
|-------------|------------|------|----------|--------|-------|
| Repository `make check-all` baseline is red before frontend changes: current macro terminal verification stops at `ruff format --check` with 74 unchanged Python files; prior shadcn frontend verification saw the same baseline class at 57 files, and a temporary mechanical format pass then exposed 101 mypy errors in 34 unchanged backend/worker files | pre-2026-05-22 baseline, detected by `2026-05-22-shadcn-frontend-system-hardening`; recounted by `2026-05-26-macro-terminal-ui-navigation-hard-cut` | harness | high | Blocks the documented repository completion gate even when targeted backend and frontend gates pass; needs a backend typing/format cleanup separate from frontend hard-cut branches | unowned |
| Frontend `npm test -- --run` baseline is red before rates-workbench changes: `useSignalPulseQueries` expects `/api/social-events/by-ids` while runtime calls `/api/events/by-ids`, and `WatchlistPage` source-navigator coverage times out at 5000ms | pre-2026-06-01 baseline, detected by `2026-06-01-rates-workbench-clarity-redesign` | harness | high | Blocks the documented frontend full-test gate even when targeted macro/rates, architecture, E2E, typecheck, lint, and build gates pass | unowned |
| Docker `/readyz` remains red after the shadcn frontend rebuild because `market_tick_stream` reports `WorkerRunSoftTimeout` and OKX DEX WS is failed while DB/migrations and GMGN WS are healthy | pre-2026-05-22 runtime baseline, detected by `2026-05-22-shadcn-frontend-system-hardening` | pipeline | high | App container can serve `/healthz` and the frontend, but operator readiness stays false until the market tick stream / OKX provider runtime issue is isolated | unowned |
| `watched_event_gate` is still biased toward English / explicit entity language, so some Chinese account posts without CA, symbol, or resolved target can miss social-event extraction before Watchlist handle summaries see them | 2026-05-14-watchlist-handle-intel | pipeline | medium | Watchlist summaries can underrepresent Chinese narrative-only posts until the watched-event gate gets a multilingual semantic pass | unowned |
| `scripts/regen_ws_protocol.py` produces a sparse table because `src/parallax/app/surfaces/api/ws.py` uses JSON dicts not typed message classes | 2026-05-09 (harness-restructure) | api | low | The auto-generated `docs/generated/ws-protocol.md` doesn't fully document the wire protocol until message classes exist | unowned |
| Legacy `assets`, `asset_aliases`, `asset_venues`, `asset_market_snapshots` tables are unused by runtime after 2026-05-16 harness hard-cut but remain in the schema. Follow-up migration should `DROP TABLE` them along with orphan `current_market_field_facts` and `token_market_price_baselines` flagged by the same audit | 2026-05-16 (backend-architecture-audit P0 hard-cut) | storage | medium | Empty/unused tables consume cluster metadata, surface in db-schema docs, and risk being re-wired by future contributors. Architecture tests already ban writes from src/, but tables themselves still exist | unowned |
| 6 FK columns lack leading indexes: `token_intent_resolutions.{asset_id,primary_venue_id}`, `token_intent_resolution_candidates.{asset_id,venue_id}`, `asset_signal_snapshots.{asset_id,primary_venue_id}`. The duplicate-token audit added them live (`idx_tir_*`, `idx_tirc_*`, `idx_asssnap_*`) via `CREATE INDEX CONCURRENTLY` because cascade `SET NULL` on bulk DELETE was scanning sequentially and blocking production INSERTs for 10+ min. Indexes are NOT in alembic migrations. The old `token_radar_rows` FK-index portion is resolved by the 2026-05-23 Token Radar storage hard cut, which drops that table. | 2026-05-12 (duplicate-token-audit) | storage | high | Any future bulk DELETE on `assets` / `asset_venues` will refuse to be fast on a fresh DB; add an alembic revision that creates these remaining indexes so testcontainers and prod re-init have them | unowned |

## Integration tests against pre-hard-cut asset registry（来自 spec 2026-05-10-tests-and-lint-production-grade, P6 pre-flight）

P5 wired auto-testcontainers, which converted what were previously `OperationalError`-skipped
integration tests into hard-fail surface. P6 pre-flight originally enumerated a broader set
of failing tests that predated either the `2026-05-10-token-identity-evidence-hard-cut` work,
the `events` schema rename to `source_provider/source_transport`, or other API changes. The
table below keeps only open rows backed by tests that still exist in the current tree; deleted
historical integration files are not retained as compatibility breadcrumbs.

To unstick: rewrite each listed test against the current API surface — most need to seed
`asset_identity_evidence`/`asset_identity_current` instead of `registry_assets.symbol`,
and any direct event insert needs to use the full `events(source_provider, source_transport, …)`
shape (cf. `src/parallax/domains/evidence/repositories/evidence_repository.py:60`).

| Test | Surface to rewrite against | Notes |
|------|----------------------------|-------|
| `tests/integration/test_resolution_refresh_worker.py::test_resolution_refresh_worker_resolves_recent_symbol_and_emits_resolution_wake` | `asset_identity_evidence` / `asset_identity_current` | drop `registry_assets.symbol` reads |
| `tests/integration/test_resolution_refresh_worker.py::test_dex_symbol_discovery_retains_top_three_per_chain` | same | symbol selector → identity-current |
| `tests/integration/test_resolution_refresh_worker.py::test_dex_symbol_discovery_excludes_stale_unretained_search_assets_from_result` | `RegistryRepository.upsert_chain_asset` (no symbol/name/decimals) | seed identity via evidence repo |
| `tests/integration/test_resolution_refresh_worker.py::test_address_discovery_remains_uncapped` | same | SELECT via identity-current |
| `tests/integration/test_api_http.py::test_api_exposes_recent_search_and_signal_read_models` | `CliRuntime` API | `tokens` attr removed |
| `tests/integration/test_api_http.py::test_api_signal_pulse_reads_pulse_candidates_after_hard_cut` | `PulseRepository.upsert_candidate` signature | drop `thesis=` kwarg |
| `tests/integration/test_api_http.py::test_api_asset_flow_scope_filters_watched_mentions` | identity-current seeding | empty result vs {BONK,PEPE} |
| `tests/integration/test_api_http.py::test_api_target_posts_returns_full_post_pages_and_requires_target_identity` | identity API | IndexError |
| `tests/integration/test_api_http.py::test_api_target_social_timeline_returns_buckets_authors_and_posts` | identity API | IndexError |
| `tests/integration/test_cli.py::CliTests::test_recent_search_asset_flow_and_alerts_use_postgres_runtime_store` | CLI runtime JSON output | Decimal serialization |

Suggested follow-up owner: `unowned` (whoever next picks up the hard-cut family of specs).

## CLI ops sync directory tests pinned to legacy config.yaml schema（来自 spec 2026-05-10-tests-and-lint-production-grade, P6 pre-flight）

`tests/integration/test_cli.py::test_cli_ops_sync_gmgn_directory_dispatches_to_runner` and
`tests/integration/test_cli.py::test_cli_ops_sync_gmgn_directory_emits_error_on_directory_failure` invoke `cli.main(...)`
without isolating `HOME`, so `load_settings()` reads the developer's
`~/.parallax/config.yaml`. The current dev environment has legacy
`pulse_agent_trigger_min_rank_score`, `pulse_agent_gate_*` keys that `LlmConfig(extra='forbid')`
rejects.

To unstick: either (a) `monkeypatch.setenv("HOME", str(tmp_path))` and seed a minimal
`~/.parallax/config.yaml` per test, or (b) refactor the runner so the test never reaches `load_settings`.

## mypy strict overrides（来自 spec 2026-05-10-tests-and-lint-production-grade）

以下包当前以 `disallow_untyped_defs = false` 等放宽设置通过 mypy。每条都需要后续按包消化（一个 sprint 摘掉一两条）。`no_implicit_optional` 与 `warn_unused_ignores` 等基础项仍全局严格。

| 模块 glob | 放宽项 | follow-up |
|---|---|---|
| `parallax.app.*` | `disallow_untyped_defs/incomplete_defs/untyped_decorators = false`；`disallow_any_generics/disallow_subclassing_any/warn_return_any = false`；`disable_error_code = [arg-type, attr-defined, union-attr, index, operator, assignment, no-untyped-call]` | TODO: 由独立 spec 处理 wiring & runtime 类型注解；目标是按子包逐条移除放宽项 |
| `parallax.integrations.*` | 同上 | TODO: external connector 类型注解；目标是逐 connector（GMGN/OKX/notification providers）补齐 Protocol 与返回类型 |

## Closed

| Description | Introduced | Resolved | Resolution |
|-------------|------------|----------|------------|
| `handle_summary` reconcile counted signal events by scanning `social_event_extractions` joined to `events` with `lower(coalesce(...))` and a correlated `COUNT(*)`, causing production statement timeouts | 2026-05-14-watchlist-handle-intel | 2026-05-20-token-radar-retention-watchlist-summary-hard-cut | Added `watchlist_handle_signal_events` and `watchlist_handle_signal_stats`, made enrichment maintain the event-idempotent stats ledger, rewrote reconcile to stats-only SQL, and added bounded stats backfill CLI |
| `token_radar_rows` mixed hot current reads, retained rank history, and full JSONB audit history in one append-heavy table, causing disproportionate DB bloat and slow detail-page reads | pre-2026-05-23 Token Radar | 2026-05-27-token-radar-kiss-current-row-hard-cut | Hard-cut online serving to `token_radar_current_rows` plus `token_radar_publication_state`; removed legacy history/audit hot paths, fallback readers, and clean-reset compatibility commands |
| Token Radar idempotency test lived under `tests/unit/`, depended on live DSNs, and skipped when source rows were absent | 2026-05-10 (tests-and-lint-production-grade, P6 pre-flight) | 2026-05-18 (test-system-hard-cut Task 5) | Moved to `tests/integration/test_token_radar_idempotency.py`, seeded disposable PostgreSQL current facts, removed live DSN/skips/private `_source_rows` monkeypatch, and asserted two real projection rebuilds are semantically stable |
| `MarketRepository` was added to `domains/asset_market/interfaces.py` even though only `app/runtime/repository_session.py` consumed it | 2026-05-10 (src-domain-package-restructure, Task 4) | 2026-05-16 (backend-architecture-audit P0 hard-cut) | Deleted `AssetRepository` and `MarketRepository` classes from runtime. Architecture test `test_legacy_asset_repository_is_not_imported` guards regressions |
| Watchlist page still combined live `/api/recent` replay for sidebar counts with handle-intel summary/timeline endpoints for the main panel | 2026-05-14-watchlist-handle-intel | 2026-05-16-watchlist-page-single-source-hard-cut | Added Watchlist overview read endpoints, moved selected-handle facts and sidebar rows onto persisted watchlist data, and added frontend architecture gates that reject the old account-case/live-buffer path |
| Token Radar v1 factor snapshot mixed presence/data-quality facts into scoring families, which made many factors saturate near 100 and reduced IC/dispersion usefulness | pre-2026-05-11 Token Radar | 2026-05-11-token-factor-engineering-hard-cut | Replaced runtime contract with `token_factor_snapshot_v2_alpha_gated`: identity/market/data availability are gates or data-health, alpha families are social-first, anchor market context is explicit, and diagnostics/settlement evaluate v2 rows by score version |
