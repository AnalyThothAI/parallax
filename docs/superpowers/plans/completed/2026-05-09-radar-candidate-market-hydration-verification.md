# Radar Candidate Market Hydration Verification

**Date:** 2026-05-09
**Branch:** `codex/radar-candidate-market-hydration-spec`
**Spec:** `docs/superpowers/specs/2026-05-09-radar-candidate-market-hydration.md`
**Plan:** `docs/superpowers/plans/2026-05-09-radar-candidate-market-hydration.md`

## Commands

| Command | Result |
|---------|--------|
| `uv run pytest tests/test_token_radar_projection.py -q` | Passed: `12 passed` |
| `uv run pytest tests/test_registry_repository.py::test_radar_price_refresh_selects_current_candidates_not_cold_registry_assets tests/test_asset_market_sync.py::test_sync_okx_dex_prices_refreshes_active_dex_venues_in_batches -q` | Passed for executable tests: `1 passed, 1 skipped` |
| `uv run pytest tests/test_asset_market_sync.py tests/test_registry_repository.py -q` | Passed for executable tests: `7 passed, 6 skipped` |
| `uv run pytest tests/test_message_market_observation.py -q` | Passed: `2 passed` |
| `uv run pytest tests/test_token_radar_projection.py tests/test_asset_market_sync.py tests/test_message_market_observation.py tests/test_registry_repository.py tests/test_asset_flow_service.py tests/test_token_radar_audit_cli.py tests/golden/test_token_radar_corpus.py -q` | Passed for executable tests: `37 passed, 10 skipped` |
| `uv run ruff check .` | Passed: `All checks passed!` |
| `uv run pytest` | Passed for executable tests: `336 passed, 133 skipped` |
| `uv run python -m compileall src tests` | Passed |
| Read-only SQL check against `parallax-postgres-1` for the candidate-scoped selector | Passed; returned recent current candidate assets without SQL/schema errors |

Skipped tests are the repo's existing environment-gated integration tests. The full suite completed successfully with those skips.

## Diff Summary

- Added the detailed spec for radar candidate market hydration.
- Added this implementation plan and marked executed steps complete.
- Bumped token radar projection contract to `token-radar-v7-candidate-hydration`.
- Added explicit `market_readiness` and `event_price_readiness` blocks to radar projection rows and `data_health_json`.
- Added `RegistryRepository.chain_assets_needing_radar_price_refresh`, which selects stale/missing Asset targets from current resolver rows and recent events instead of global active registry history.
- Changed OKX DEX price sync to use the radar candidate selector and report `refresh_universe = "radar_candidates"`.
- Changed message/start price observation selection to prioritize recent one-hour rows before old backlog.
- Added regression coverage for projection contract/readiness, DEX selector ownership, and message quote ordering.

## Operational Cleanup

The local Docker PostgreSQL store was cleaned after the implementation verification.

- Backup directory: `/tmp/gmgn_pollution_cleanup_20260509_183318/`
- Backed up before deletion:
  - `registry_assets.csv`: 5322 deleted asset rows plus header
  - `price_feeds.csv`: 5839 deleted pricefeed rows plus header
  - `price_observations.csv`: 23113 deleted observation rows plus header
  - `current_referenced_demoted_assets.csv`: 15 retained current target rows plus header
- Deleted in one transaction:
  - `price_observations`: 23113
  - `price_feeds`: 5839
  - `registry_assets`: 5322
- Repaired after deletion:
  - 15 `demoted_search / okx_dex_search` assets still referenced by current resolutions were restored to `candidate` instead of deleted.
- Post-cleanup validation:
  - `registry_assets.status = 'demoted_search'`: 0
  - missing current Asset targets: 0

Additional cleanup after Docker data-flow verification found current resolutions still pointing at newly accumulated `demoted_search / okx_dex_search` assets.

- Backup directory: `/tmp/gmgn_demoted_search_cleanup_20260509_191006/`
- Backed up before deletion:
  - `registry_assets.csv`: 52 deleted asset rows plus header
  - `price_feeds.csv`: 59 deleted pricefeed rows plus header
  - `price_observations.csv`: 1237 deleted observation rows plus header
  - `current_resolutions.csv`: 249 current resolution rows plus header
- Repaired before deletion:
  - 249 current resolutions targeting demoted search assets were reset to `NIL` with reason `DEMOTED_SEARCH_ASSET_PURGED`.
- Deleted in one transaction:
  - `price_observations`: 1237
  - `price_feeds`: 59
  - `registry_assets`: 52
- Post-cleanup validation:
  - `registry_assets.status = 'demoted_search'`: 0
  - current resolutions targeting demoted registry assets: 0

## State Machine Boundary

The token extraction state machine was not rewritten.

- `token_evidence_builder.py` was not changed.
- `token_intent_builder.py` was not changed.
- `deterministic_token_resolver.py` was not changed.
- `TOKEN_RADAR_RESOLVER_POLICY_VERSION` remains `token_radar_v5_identity_resolver`.

Only the radar projection contract and market hydration scheduling changed.

## Runtime Query Hotfix

Docker verification after the first merge exposed a runtime bug: the token radar projection source query could saturate PostgreSQL on larger windows because price observation lookup used `OR` inside lateral subqueries. The hotfix keeps the same output semantics but splits lookups into index-friendly lateral paths:

- latest feed price via `pricefeed_id, observed_at_ms`
- latest subject price via `subject_type, subject_id, observed_at_ms`
- message-scoped event price via `source_resolution_id`
- event-history and before-event prices via `subject_type, subject_id, observed_at_ms`

Additional hotfix verification:

| Command | Result |
|---------|--------|
| `uv run pytest tests/test_token_radar_projection.py -q` | Passed: `14 passed` |
| `uv run ruff check src/parallax/pipeline/token_radar_projection.py tests/test_token_radar_projection.py` | Passed: `All checks passed!` |
| `uv run ruff check .` | Passed: `All checks passed!` |
| `uv run pytest` | Passed for executable tests: `338 passed, 133 skipped` |
| `uv run python -m compileall src tests` | Passed |
| Hotfix `_source_rows` 24h/all against Docker PostgreSQL | Passed: `42689` rows in `17.287s` |
| Hotfix `TokenRadarProjectionWorker.rebuild_once()` against Docker PostgreSQL | Passed: `622` rows written across all windows/scopes in `54.516s` |
| Direct `AssetFlowService.asset_flow(window='5m', scope='all')` against Docker PostgreSQL | Passed: `5` targets, `5` attention rows, `fresh`, `0.09s` |

## A+B Projection Ownership And Historical Tail Cleanup

The A+B hard cut was implemented and verified in the isolated worktree `codex/radar-hydration-cleanup`.

### Code-Level Verification

| Command | Result |
|---------|--------|
| `uv run ruff check .` | Passed: `All checks passed!` |
| `uv run pytest` | Passed for executable tests: `343 passed, 134 skipped` |
| `uv run python -m compileall src tests` | Passed |
| `uv run pytest tests/test_cli.py tests/test_token_radar_projection_worker.py tests/test_token_radar_projection.py tests/test_asset_flow_service.py -q` | Passed after removing stale CLI V6 wording: `37 passed, 5 skipped` |
| `git diff --check` | Passed |

### Runtime Verification

The Docker app was rebuilt from this worktree and restarted with migration `20260509_0020`.

| Check | Result |
|-------|--------|
| `docker compose ps` | `app` and `postgres` healthy; app exposed at `127.0.0.1:8765` |
| `/readyz` | `ok=true`, `migration_version=20260509_0020`, `token_radar_projection.worker_running=true`, `last_error=null` |
| Asset-market refresh result | `projection.status=deferred_to_worker`, confirming market sync no longer synchronously rebuilds radar windows |
| Token discovery result | `projection.status=deferred_to_worker`, confirming discovery no longer synchronously rebuilds radar windows |

Latest live HTTP reads after rebuild:

| Endpoint | Result |
|----------|--------|
| `/api/token-radar?window=5m&scope=all&limit=10` | `ok=true`, `target_count=10`, `attention_count=5`, `projection.status=fresh`, `market_hydration={fresh:15, stale:1, missing:5, pending:0, status:partial, total:21}` |
| `/api/token-radar?window=5m&scope=matched&limit=10` | `ok=true`, `target_count=0`, `attention_count=0`, `projection.status=missing`, `market_hydration.total=0` |
| `/api/token-radar?window=1h&scope=matched&limit=10` | `ok=true`, `target_count=1`, `attention_count=0`, `projection.status=fresh`, `market_hydration={fresh:1, stale:0, missing:0, pending:0, status:ready, total:1}` |

The current `5m/matched` empty state is input-driven: the latest worker tick saw no matched source rows for that short watched-account window. The read path now returns an explicit missing projection instead of silently showing stale or fabricated rows.

### Historical Search-Candidate Cleanup

Migration `20260509_0020_sweep_symbol_search_tail_assets.py` demotes unprotected `okx_dex_search` symbol-search tail candidates after the top three per `(symbol, chain_id)` ranking.

The protection boundary is before ranking:

- current `CHAIN_ADDRESS_EXACT` targets are excluded from demotion;
- current `ADDRESS_UNIQUE_ACROSS_TRACKED_CHAINS` targets are excluded from demotion;
- protected exact CA rows therefore do not consume the search-candidate top-three budget and are not demoted.

Post-migration live check:

| Query | Result |
|-------|--------|
| unprotected active search candidates with rank greater than 3 | `0` |
| active unprotected search candidates retained across all symbols/chains | `4937` |

This means the historical long tail was cleared without deleting the bounded top-three search candidates or touching current exact-address CA resolutions.

### Behavioral Boundaries

- No compatibility fallback was added for prior radar projection versions.
- `token_evidence_builder.py`, `token_intent_builder.py`, and `deterministic_token_resolver.py` remain untouched.
- The mature token extraction and resolver state machine continues to produce CA/address resolutions; the new cleanup only changes downstream search-candidate stewardship and projection hydration ownership.

## Risks And Follow-Ups

- The new DEX refresh selector depends on current token intent resolutions. If resolver refresh is delayed, DEX market hydration follows the delayed resolved set rather than unresolved attention rows.
- The current implementation keeps cold registry refresh out of the radar-critical DEX path. A separate low-priority cold steward can be reintroduced later if cold asset pages need best-effort updates.
- Postgres integration tests were skipped by the existing test harness in this local run. The selector SQL was additionally checked against the live local PostgreSQL container with a read-only query.
- This is a hard-cut projection version. Downstream readers must consume `token-radar-v7-candidate-hydration`; there is no legacy projection fallback.
