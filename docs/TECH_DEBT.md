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
| Docker `/readyz` remains red after the shadcn frontend rebuild because `market_tick_stream` reports `WorkerRunSoftTimeout` and OKX DEX WS is failed while DB/migrations and GMGN WS are healthy | pre-2026-05-22 runtime baseline, detected by `2026-05-22-shadcn-frontend-system-hardening` | pipeline | high | App container can serve `/healthz` and the frontend, but operator readiness stays false until the market tick stream / OKX provider runtime issue is isolated | unowned |
| Macro/timsun parity gaps remain after the decision-console hard cut; `docs/references/MACRO_TIMSUN_SOURCE_GAP_MAP.md` now classifies the remaining trade-map, Fed communication, FedWatch, VIX futures/options, crypto derivatives, global-dollar, OFR/STFM funding, Treasury auction-tail, economy surprise, and credit microstructure gaps by implemented/public/license/model source gate before any deleted terminal page can be restored | 2026-06-16-macro-decision-console | pipeline | high | Parallax now has a usable public-data macro decision console and source-backed event/crypto bundles, but deeper timsun-style parity still needs explicit source gates and successor specs; no hidden routes, compatibility aliases, static future-source rows, or runtime placeholder labels should be reintroduced meanwhile | unowned |
| `watched_event_gate` is still biased toward English / explicit entity language, so some Chinese account posts without CA, symbol, or resolved target can miss social-event extraction before Watchlist handle summaries see them | 2026-05-14-watchlist-handle-intel | pipeline | medium | Watchlist summaries can underrepresent Chinese narrative-only posts until the watched-event gate gets a multilingual semantic pass | unowned |
| `scripts/regen_ws_protocol.py` documents WebSocket type literals from `src/parallax/app/surfaces/api/ws.py`, but field-level schemas remain sparse because the runtime still sends JSON dicts instead of typed message classes | 2026-05-09 (harness-restructure) | api | low | The auto-generated `docs/generated/ws-protocol.md` exposes message kinds but cannot fully document per-message fields until typed payload contracts exist | unowned |

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
| `tests/integration/test_api_http.py::test_api_asset_flow_scope_filters_watched_mentions` | identity-current seeding | empty result vs {BONK,PEPE} |
| `tests/integration/test_api_http.py::test_api_target_posts_returns_full_post_pages_and_requires_target_identity` | identity API | IndexError |
| `tests/integration/test_api_http.py::test_api_target_social_timeline_returns_buckets_authors_and_posts` | identity API | IndexError |
| `tests/integration/test_cli.py::CliTests::test_recent_search_asset_flow_and_alerts_use_postgres_runtime_store` | CLI runtime JSON output | Decimal serialization |

Suggested follow-up owner: `unowned` (whoever next picks up the hard-cut family of specs).

## mypy strict overrides（来自 spec 2026-05-10-tests-and-lint-production-grade）

以下包当前以 `disallow_untyped_defs = false` 等放宽设置通过 mypy。每条都需要后续按包消化（一个 sprint 摘掉一两条）。`no_implicit_optional` 与 `warn_unused_ignores` 等基础项仍全局严格。

| 模块 glob | 放宽项 | follow-up |
|---|---|---|
| `parallax.app.*` | `disallow_untyped_defs/incomplete_defs/untyped_decorators = false`；`disallow_any_generics/disallow_subclassing_any/warn_return_any = false`；`disable_error_code = [arg-type, attr-defined, union-attr, index, operator, assignment, no-untyped-call]` | TODO: 由独立 spec 处理 wiring & runtime 类型注解；目标是按子包逐条移除放宽项 |
| `parallax.integrations.*` | 同上 | TODO: external connector 类型注解；目标是逐 connector（GMGN/OKX/notification providers）补齐 Protocol 与返回类型 |

## Closed

| Description | Introduced | Resolved | Resolution |
|-------------|------------|----------|------------|
| Legacy `assets`, `asset_aliases`, `asset_venues`, `asset_market_snapshots`, `current_market_field_facts`, and `token_market_price_baselines` remained listed as open storage debt after the hard-cut drop migrations had landed | 2026-05-16 (backend-architecture-audit P0 hard-cut) | 2026-06-12-kappa-cqrs-governance-root-fix Root241 | `20260516_0050_drop_legacy_asset_stack.py` and `20260517_0053_reconcile_legacy_asset_stack_drop.py` drop the legacy/orphan tables idempotently; open debt row removed and architecture guard prevents this resolved claim from returning to `Open` |
| Duplicate-token audit FK-index follow-up remained listed as open after the same hard-cut drop removed the affected legacy FK columns/tables | 2026-05-12 (duplicate-token-audit) | 2026-06-12-kappa-cqrs-governance-root-fix Root241 | `20260516_0050_drop_legacy_asset_stack.py` drops `token_intent_resolutions.{asset_id,primary_venue_id}` and the legacy candidate/snapshot tables, so the live `idx_tir_*`, `idx_tirc_*`, and `idx_asssnap_*` backfill is no longer required for fresh schemas; open debt row removed and covered by the stale-debt guard |
| `handle_summary` reconcile counted signal events by scanning `social_event_extractions` joined to `events` with `lower(coalesce(...))` and a correlated `COUNT(*)`, causing production statement timeouts | 2026-05-14-watchlist-handle-intel | 2026-05-20-token-radar-retention-watchlist-summary-hard-cut | Added `watchlist_handle_signal_events` and `watchlist_handle_signal_stats`, made enrichment maintain the event-idempotent stats ledger, rewrote reconcile to stats-only SQL, and added bounded stats backfill CLI |
| `token_radar_rows` mixed hot current reads, retained rank history, and full JSONB audit history in one append-heavy table, causing disproportionate DB bloat and slow detail-page reads | pre-2026-05-23 Token Radar | 2026-05-27-token-radar-kiss-current-row-hard-cut | Hard-cut online serving to `token_radar_current_rows` plus `token_radar_publication_state`; removed legacy history/audit hot paths, fallback readers, and clean-reset compatibility commands |
| Token Radar idempotency test lived under `tests/unit/`, depended on live DSNs, and skipped when source rows were absent | 2026-05-10 (tests-and-lint-production-grade, P6 pre-flight) | 2026-05-18 (test-system-hard-cut Task 5) | Moved to `tests/integration/test_token_radar_idempotency.py`, seeded disposable PostgreSQL current facts, removed live DSN/skips/private `_source_rows` monkeypatch, and asserted two real projection rebuilds are semantically stable |
| `MarketRepository` was added to `domains/asset_market/interfaces.py` even though only `app/runtime/repository_session.py` consumed it | 2026-05-10 (src-domain-package-restructure, Task 4) | 2026-05-16 (backend-architecture-audit P0 hard-cut) | Deleted `AssetRepository` and `MarketRepository` classes from runtime. Architecture test `test_legacy_asset_repository_is_not_imported` guards regressions |
| Watchlist page still combined live `/api/recent` replay for sidebar counts with handle-intel summary/timeline endpoints for the main panel | 2026-05-14-watchlist-handle-intel | 2026-05-16-watchlist-page-single-source-hard-cut | Added Watchlist overview read endpoints, moved selected-handle facts and sidebar rows onto persisted watchlist data, and added frontend architecture gates that reject the old account-case/live-buffer path |
| Token Radar v1 factor snapshot mixed presence/data-quality facts into scoring families, which made many factors saturate near 100 and reduced IC/dispersion usefulness | pre-2026-05-11 Token Radar | 2026-05-11-token-factor-engineering-hard-cut | Replaced runtime contract with `token_factor_snapshot_v2_alpha_gated`: identity/market/data availability are gates or data-health, alpha families are social-first, anchor market context is explicit, and diagnostics/settlement evaluate v2 rows by score version |
