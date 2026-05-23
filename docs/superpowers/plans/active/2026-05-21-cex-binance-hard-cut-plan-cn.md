# CEX Binance Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把项目内所有 CEX identity/routing/quote/candle/OI/radar 链路 hard cut 到 Binance USDT 永续，把 `coinglass-cli` 打包进 Docker，并删除 OKX CEX runtime、配置、CLI、测试 fixture 和旧 DB 数据。

**Architecture:** `cex_tokens` 继续作为 CEX token identity，但当前 CEX identity 必须由 Binance USDT perpetual feed 支撑。`price_feeds` 的 CEX 当前集合只允许 `provider='binance'`, `feed_type='cex_swap'`, `quote_symbol='USDT'`；所有 CEX market ticks 写 `source_provider='binance_cex_rest'`。OKX 只允许继续承担 DEX discovery / quote / WS 角色，不作为 CEX fallback 或 compatibility path。

**Tech Stack:** Python, PostgreSQL/Alembic, httpx, psycopg, pytest, uv Git dependencies, Docker Compose, existing worker/provider wiring, existing CLI ops surface.

## Execution status, 2026-05-21

代码链路已按 hard cut 方向实现并完成本地验证：

- `coinglass-cli` 已以 pinned Git dependency 打包进 Docker，最终 runtime image 不包含 `gcc` / `git` build toolchain。
- OKX CEX runtime provider、配置项、CLI sync command、CEX read/write source 常量已移除或切到 Binance。
- Binance USD-M futures client、universe sync CLI、cleanup ops CLI、read-path Binance-only filters、CEX tick/candle/event anchor wiring 已接入。
- 新增 `cex_oi_radar_board` worker foundation：Binance-backed universe 读取、OI/ticker/premiumIndex builder、deterministic scoring、独立 OI/radar tables、`/api/cex/radar-board` read-only API。
- final subagent review 发现并已修复两项 hard-cut blocker：symbol-only CEX resolution 现在必须有 Binance feed；legacy `enriched_events.tick_id` 指向的旧 OKX CEX tick 会在读路径被拒绝。
- Alembic 仅做 `market_ticks.source_provider` additive / `NOT VALID` 约束变更；provider-dependent destructive cleanup 留给显式 ops command。
- 已验证：
  - `uv lock --check`
  - `uv run ruff check .`
  - `git diff --check`
  - CEX/Binance/cleanup/OI-radar/API/integration targeted suite: `257 passed`
  - CEX read-path / resolver regression suite: `43 passed`
  - full `tests/unit`: `1401 passed, 1 skipped, 12 failed`
  - `docker compose build app`
  - `docker compose run --rm --no-deps app coinglass-cli --help`
  - `docker compose run --rm --no-deps app coinglass-cli canary`
  - `docker compose run --rm --no-deps app gmgn-twitter-intel --help`
  - `docker compose run --rm --no-deps app sh -lc 'command -v gcc || true; command -v git || true'` confirmed both absent.

仍需在真实运行环境执行的 operator 步骤：

- 确认 `uv run gmgn-twitter-intel config` 指向 `~/.gmgn-twitter-intel/`，只报告路径和 redacted booleans。
- 备份并执行 `scripts/cex_binance_config_hard_cut.py`，迁移真实 operator config。
- 跑 `ops sync-binance-usdt-perp-universe --execute` 写入 Binance USDT perpetual universe。
- 维护窗口内先 `--dry-run` 再 `--execute` 跑 `ops cex-binance-hard-cut-cleanup`，确认 Binance canonical feed count 超过阈值后清旧 OKX CEX 数据。

Known unrelated failures / blocked environment checks:

- `tests/architecture/test_src_domain_architecture.py::test_raw_sql_is_owned_by_repositories_queries_or_app_runtime` 仍会因既有 `pulse_lab/services/pulse_policy_evaluator.py` 和 `pulse_lab/services/pulse_agent_cost_report.py` 失败；这两个文件不在本次 hard cut diff 内。
- full `tests/unit` baseline 仍有既有 notifications / pulse claim verifier / worker settings / watchlist 失败；本次新增的 token radar / resolver CEX read-path 期望漂移已修复。
- `tests/postgres_test_utils.py` 仍因本机 `127.0.0.1:55432` PostgreSQL test database 不可用而跳过 1 个单测级 Postgres case。

---

## Pre-flight

- [ ] Confirm runtime config paths with `uv run gmgn-twitter-intel config`; report only redacted booleans and paths.
- [ ] Back up operator config before any hard-cut code is used:
  ```bash
  cp ~/.gmgn-twitter-intel/config.yaml ~/.gmgn-twitter-intel/config.yaml.pre-cex-binance-hard-cut
  ```
- [ ] After Task 0 creates the standalone config migration script, run its dry-run before rebuilding Docker. The script must not import `Settings`,
      because the new `extra="forbid"` settings model will reject old `providers.okx.cex_*` keys:
  ```bash
  uv run python scripts/cex_binance_config_hard_cut.py --dry-run
  ```
- [ ] Apply the config migration before running new CLI or Docker:
  ```bash
  uv run python scripts/cex_binance_config_hard_cut.py --execute
  ```
- [ ] Confirm the worktree is on branch `codex/cex-binance-hard-cut` or an equivalent feature branch before edits.
- [ ] Run `uv run ruff check .` and record baseline status.
- [ ] Run targeted baseline tests around CEX/market paths:
  ```bash
  uv run pytest \
    tests/unit/test_okx_clients.py \
    tests/unit/test_asset_market_sync.py \
    tests/unit/test_providers_wiring.py \
    tests/unit/test_provider_capabilities.py \
    tests/unit/test_market_tick_repository.py \
    tests/unit/test_event_market_capture.py \
    tests/unit/test_market_candles_service.py \
    tests/unit/test_deterministic_token_resolver.py \
    tests/integration/test_cli.py \
    -q
  ```
- [ ] Confirm current Binance USD-M universe manually:
  ```bash
  curl -fsSL https://fapi.binance.com/fapi/v1/exchangeInfo \
    | jq '[.symbols[] | select(.status=="TRADING" and .contractType=="PERPETUAL" and .quoteAsset=="USDT")] | length'
  ```
  Expected: a positive count above 400.

Known-failing baseline tests:

- None expected for the targeted baseline. If existing dirty work causes unrelated failures, record the exact test names before editing.

Docker ordering invariant:

- `compose.yaml` runs `migrate` before `app`. Any Alembic migration in this PR must be safe before Binance universe sync has run.
- Provider-dependent cleanup must live in an explicit ops command with `--dry-run` / `--execute`, not in automatic startup migration.
- The first migration may reject new OKX CEX writes with a `NOT VALID` check constraint while tolerating old rows until cleanup validates it.

## File-level edits

### Dependency and Docker packaging

- Modify `pyproject.toml`
  - Add `"coinglass-cli"` to project dependencies.
  - Add a pinned Git source in `[tool.uv.sources]`:
    ```toml
    coinglass-cli = { git = "https://github.com/AnalyThothAI/coinglass-cli.git", rev = "<pinned_commit>" }
    ```
  - Keep the existing `marketlane-cli` source unchanged.
- Modify `uv.lock`
  - Run `uv lock` after selecting the exact `coinglass-cli` commit.
  - Do not leave an unpinned branch-only dependency.
- Verify Docker packaging
  - The current Dockerfile already installs production dependencies through `uv sync --frozen --no-dev`.
  - Only add Playwright browser install steps if the enabled CoinGlass command path requires browser transport in production.
  - Required smoke commands:
    ```bash
    docker compose build app
    docker compose run --rm --no-deps app coinglass-cli --help
    docker compose run --rm --no-deps app coinglass-cli canary
    ```
  - If browser transport is enabled, also verify:
    ```bash
    docker compose run --rm --no-deps app coinglass-cli oi-history --symbol BTC --time-type 2 --lookback 1d
    ```

### Binance integration

- Create `src/gmgn_twitter_intel/integrations/binance/usdm_futures_client.py`
  - Define `BinanceUsdmFuturesClient`.
  - Implement `exchange_info()`, `usdt_perpetual_routes()`, `ticker_24hr(symbol=None)`, `premium_index(symbol=None)`, `open_interest_hist(symbol, period, limit)`, `ticker(symbol)`, and `candles(symbol, interval, limit)`.
  - Normalize route records from `exchangeInfo.baseAsset`, `quoteAsset`, `symbol`, `status`, and `contractType`; never infer base from `BTCUSDT` string slicing.
  - Return domain-facing records with explicit `provider='binance'`, `feed_type='cex_swap'`, `quote_symbol='USDT'`, `native_market_id=symbol`.
- Modify `src/gmgn_twitter_intel/app/runtime/provider_wiring/binance.py`
  - Add `BinanceUsdmFuturesMarketProvider` implementing existing `CexMarketProvider`.
  - Keep Binance profile clients separate from futures clients.
  - Add provider health capability for Binance CEX quote/profile without mentioning OKX CEX.

### OKX CEX removal and provider wiring

- Modify `src/gmgn_twitter_intel/app/runtime/provider_wiring/okx.py`
  - Remove `OkxCexMarketProvider`, `okx_cex_market()`, and CEX wiring from the OKX bundle.
  - Keep OKX DEX discovery / quote / WS providers intact.
  - If OKX DEX imports HTTP helpers from `integrations/okx/cex_client.py`, first move shared helpers into `src/gmgn_twitter_intel/integrations/okx/http_utils.py`.
- Modify `src/gmgn_twitter_intel/app/runtime/provider_wiring/types.py`
  - Replace `sync_cex_market` and `message_cex_market` with a single `cex_market`.
  - Remove CEX fields from `OkxProviderBundle`, or rename the bundle to `OkxDexProviderBundle`.
- Modify `src/gmgn_twitter_intel/app/runtime/provider_wiring/asset_market.py`
  - Wire `AssetMarketProviders.cex_market` from Binance only.
  - Continue wiring `dex_discovery_market`, `dex_quote_market`, and `stream_dex_market` from OKX/GMGN as before.
  - Provider health should report Binance CEX and OKX DEX as separate capabilities.
- Delete `src/gmgn_twitter_intel/integrations/okx/cex_client.py` after moving shared helpers.

### Settings and CLI

- Modify `src/gmgn_twitter_intel/platform/config/settings.py`
  - Remove `OkxProviderConfig.cex_base_url`, `cex_sync_enabled`, and `cex_inst_types`.
  - Add Binance fields: `cex_profile_base_url`, `usdm_futures_base_url`, `cex_universe_quote_symbol`, `cex_universe_contract_type`.
  - Keep `providers.okx` DEX-only in `default_config_yaml()`.
  - Update accessors so no `okx_cex_*` property remains.
- Modify `src/gmgn_twitter_intel/app/surfaces/cli/commands/config.py`
  - Remove OKX CEX config diagnostics.
  - Show Binance futures configured/enabled booleans without secrets.
- Modify `src/gmgn_twitter_intel/app/surfaces/cli/parser.py`
  - Remove `sync-okx-cex-universe`.
  - Add `sync-binance-usdt-perp-universe` with `--dry-run` and `--execute`.
- Modify `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
  - Remove `OkxCexClient` imports and command handler.
  - Add `sync-binance-usdt-perp-universe` handler.
  - Add cleanup command `cex-binance-hard-cut-cleanup` with `--dry-run`, `--execute`, and `--min-binance-feeds`.
    This command owns destructive SQL cleanup after Binance sync.
- Create `scripts/cex_binance_config_hard_cut.py`
  - Read `~/.gmgn-twitter-intel/config.yaml` by default, or an explicit `--config-path`.
  - Remove `providers.okx.cex_base_url`, `providers.okx.cex_sync_enabled`, and `providers.okx.cex_inst_types`.
  - Add `providers.binance.cex_profile_base_url`, `providers.binance.usdm_futures_base_url`,
    `providers.binance.cex_universe_quote_symbol`, and `providers.binance.cex_universe_contract_type`.
  - Write a timestamped backup on `--execute`.
  - Do not import application `Settings`; this must work while the old config still contains now-invalid keys.

### Registry and resolver

- Create `src/gmgn_twitter_intel/domains/asset_market/services/binance_usdt_perp_universe_sync.py`
  - Implement `sync_binance_usdt_perp_universe(registry, routes, observed_at_ms, dry_run, execute)`.
  - Upsert Binance-backed `cex_tokens` and `price_feeds`.
  - Remove or plan removal of non-Binance-backed `cex_tokens` in `--execute`.
  - Return counts: `binance_usdt_perp_seen`, `cex_tokens_to_insert`, `cex_tokens_to_delete`, `pricefeeds_to_insert`, `old_okx_cex_rows_to_delete`, `duration_ms`.
- Modify or retire `src/gmgn_twitter_intel/domains/asset_market/services/asset_market_sync.py`
  - Remove OKX ticker-shape parsing.
  - If the filename remains, make it delegate to explicit route sync with no OKX defaults.
- Modify `src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py`
  - Add `upsert_cex_route(route, observed_at_ms, commit=False)`.
  - Add `binance_usdt_perp_pricefeeds()` and cleanup helpers.
  - Change `find_preferred_cex_pricefeed(base_symbol)` to only return canonical Binance USDT swap.
  - Change `active_live_market_targets(...)` so CEX active targets only select Binance canonical USDT swap feeds.
- Modify every duplicated preferred CEX feed read path, not only `RegistryRepository`:
  - `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py`
  - `src/gmgn_twitter_intel/domains/token_intel/queries/event_token_projection_query.py`
  - `src/gmgn_twitter_intel/domains/token_intel/repositories/token_target_repository.py`
  - `src/gmgn_twitter_intel/domains/account_quality/repositories/account_quality_repository.py`
  - Each query must filter `provider='binance'`, `feed_type='cex_swap'`, `quote_symbol='USDT'`, `status='canonical'`.
- Modify `src/gmgn_twitter_intel/domains/token_intel/services/deterministic_token_resolver.py`
  - Ensure explicit `exchange=okx` does not create or select OKX CEX routes.
  - Ensure symbol-only CEX resolution requires a Binance-backed feed.

### Market facts and CEX reads

- Modify `src/gmgn_twitter_intel/domains/asset_market/types/market_tick.py`
  - Replace `okx_cex_rest` with `binance_cex_rest` in `MarketTickSourceProvider`.
- Modify `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_poll_worker.py`
  - Rename CEX source constant to `binance_cex_rest`.
  - Read provider from `providers.cex_market`.
  - Write CEX ticks with `exchange='binance'`, `target_id='binance:<symbol>'`, `source_provider='binance_cex_rest'`.
- Modify `src/gmgn_twitter_intel/domains/asset_market/services/event_market_capture.py`
  - Use `providers.cex_market`.
  - Replace comments and source constants from OKX CEX to Binance CEX.
- Modify `src/gmgn_twitter_intel/domains/asset_market/runtime/event_anchor_backfill_worker.py`
  - Use `providers.cex_market`.
  - Write CEX backfill ticks as Binance.
- Modify `src/gmgn_twitter_intel/domains/asset_market/read_models/market_candles_service.py`
  - Emit `candle_source='binance_cex_candles'` for CEX tokens.
  - Call Binance CEX candle provider for CEX tokens.
- Modify `src/gmgn_twitter_intel/app/runtime/worker_factories/asset_market.py`
  - Construct market tick poll and event anchor backfill when `cex_market` or DEX providers are present.
- Modify `src/gmgn_twitter_intel/app/surfaces/api/routes_search.py`
  - Pass `cex_market` instead of `message_cex_market`.
- Modify `src/gmgn_twitter_intel/domains/asset_market/runtime/live_price_gateway.py`
  - Preserve `open_interest_usd` from latest `market_ticks` in the live payload instead of hardcoding `None`.

### Storage / migrations

- Create additive migration `src/gmgn_twitter_intel/platform/db/alembic/versions/20260521_0072_cex_binance_source_provider_additive.py`
  - This migration must be safe when Docker runs `db migrate` before Binance universe sync.
  - Drop the old `market_ticks_source_provider_check`.
  - Add the new check as `NOT VALID` so old OKX CEX rows can remain temporarily, but new writes must use the new provider set:
    ```sql
    ALTER TABLE market_ticks
      DROP CONSTRAINT IF EXISTS market_ticks_source_provider_check;

    ALTER TABLE market_ticks
      ADD CONSTRAINT market_ticks_source_provider_check
      CHECK (source_provider IN ('okx_dex_ws', 'okx_dex_rest', 'gmgn_dex_quote', 'binance_cex_rest'))
      NOT VALID;
    ```
- Create `src/gmgn_twitter_intel/domains/asset_market/services/cex_binance_hard_cut_cleanup.py`
  - Implement the SQL cleanup transaction used by the ops command.
  - Inputs: `dry_run`, `execute`, `min_binance_feeds`, `now_ms`.
  - Acquire an advisory transaction lock before modifying rows.
  - Abort unless Binance canonical USDT perp feed count is at least `min_binance_feeds`.
  - Dry-run returns counts only; execute returns before/after counts and `constraint_validated`.
- Lifecycle-safe current resolution cleanup
  - Do not mutate current `token_intent_resolutions` in place.
  - For current `CexToken` resolutions that have a Binance feed but point at an OKX/legacy pricefeed, supersede the old row and insert a new current row with the Binance pricefeed and reason `cex_binance_hard_cut_repointed`.
  - For current `CexToken` resolutions with no Binance USDT perp feed, supersede the old row and insert a new current NIL row with reason `cex_binance_hard_cut_removed`.
  - Required shape:
    ```sql
    WITH clock AS (
      SELECT %(now_ms)s::bigint AS now_ms
    ),
    binance_feed AS (
      SELECT DISTINCT ON (subject_id)
        subject_id AS target_id,
        pricefeed_id
      FROM price_feeds
      WHERE subject_type = 'CexToken'
        AND provider = 'binance'
        AND feed_type = 'cex_swap'
        AND quote_symbol = 'USDT'
        AND status = 'canonical'
      ORDER BY subject_id, updated_at_ms DESC, native_market_id ASC
    ),
    to_repoint AS (
      SELECT tir.*, binance_feed.pricefeed_id AS binance_pricefeed_id
      FROM token_intent_resolutions tir
      JOIN binance_feed ON binance_feed.target_id = tir.target_id
      WHERE tir.is_current = true
        AND tir.target_type = 'CexToken'
        AND COALESCE(tir.pricefeed_id, '') <> binance_feed.pricefeed_id
    ),
    superseded AS (
      UPDATE token_intent_resolutions tir
      SET record_status = 'superseded',
          is_current = false,
          superseded_at_ms = (SELECT now_ms FROM clock)
      FROM to_repoint
      WHERE tir.resolution_id = to_repoint.resolution_id
      RETURNING to_repoint.*
    )
    INSERT INTO token_intent_resolutions(
      resolution_id, intent_id, event_id, resolution_status, resolver_policy_version,
      target_type, target_id, pricefeed_id, reason_codes_json, candidate_ids_json,
      lookup_keys_json, record_status, is_current, decision_time_ms, created_at_ms
    )
    SELECT
      'cex-binance-hard-cut-repointed:' || resolution_id,
      intent_id, event_id, resolution_status, resolver_policy_version,
      target_type, target_id, binance_pricefeed_id,
      COALESCE(reason_codes_json, '[]'::jsonb) || '["cex_binance_hard_cut_repointed"]'::jsonb,
      candidate_ids_json, lookup_keys_json,
      'current', true, (SELECT now_ms FROM clock), (SELECT now_ms FROM clock)
    FROM superseded
    ON CONFLICT (resolution_id) DO NOTHING;
    ```
  - Add the equivalent `to_remove` CTE that inserts `resolution_status='NIL'`, `target_type=NULL`, `target_id=NULL`, `pricefeed_id=NULL`, and reason `cex_binance_hard_cut_removed`.
- Do not mutate Token Radar storage from this asset-market cleanup. The command
  reports impacted Token Radar counts, then operators run
  `ops reset-token-radar-postgres-hard-cut --execute` so the Token Radar owner clears
  current/history/audit storage and projection controls in one place.
- Detach OKX CEX event anchors:
    ```sql
    UPDATE enriched_events
    SET tick_id = NULL,
        tick_lag_ms = NULL,
        capture_method = 'unavailable',
        capture_reason = 'cex_okx_removed'
    WHERE tick_id IN (
      SELECT tick_id
      FROM market_ticks
      WHERE target_type = 'cex_symbol'
        AND (target_id LIKE 'okx:%' OR source_provider = 'okx_cex_rest')
      );
    ```
- Mark old OKX CEX backfill jobs terminal so they do not retry against a removed provider:
    ```sql
    UPDATE event_anchor_backfill_jobs
    SET status = 'failed',
        last_reason = 'cex_okx_removed',
        updated_at_ms = %(now_ms)s
    WHERE target_type = 'cex_symbol'
      AND target_id LIKE 'okx:%'
      AND status = 'pending';
    ```
- Delete OKX CEX data:
    ```sql
    DELETE FROM market_ticks
    WHERE target_type = 'cex_symbol'
      AND (target_id LIKE 'okx:%' OR source_provider = 'okx_cex_rest');

    DELETE FROM token_capture_tier
    WHERE target_type = 'cex_symbol'
      AND target_id LIKE 'okx:%';

    DELETE FROM price_observations
    WHERE provider IN ('okx_cex', 'okx')
       OR pricefeed_id LIKE 'pricefeed:cex:okx:%';

    DELETE FROM price_feeds
    WHERE provider = 'okx'
      AND feed_type LIKE 'cex_%';
    ```
- Delete CEX tokens not backed by Binance USDT perp after Binance sync:
    ```sql
    DELETE FROM cex_tokens
    WHERE NOT EXISTS (
      SELECT 1
      FROM price_feeds
      WHERE price_feeds.subject_type = 'CexToken'
        AND price_feeds.subject_id = cex_tokens.cex_token_id
        AND price_feeds.provider = 'binance'
        AND price_feeds.feed_type = 'cex_swap'
        AND price_feeds.quote_symbol = 'USDT'
        AND price_feeds.status = 'canonical'
    );
    ```
- Validate the final check constraint after OKX CEX ticks are gone:
    ```sql
    ALTER TABLE market_ticks
      VALIDATE CONSTRAINT market_ticks_source_provider_check;
    ```
- Update schema tests in `tests/integration/test_postgres_schema_runtime.py`.
- Update generated schema docs after migration.

### Tests

- Create `tests/unit/test_binance_usdm_futures_client.py`
  - `test_exchange_info_filters_trading_usdt_perpetual`
  - `test_route_uses_base_asset_and_quote_asset_for_1000_tokens`
  - `test_ticker_maps_quote_volume_and_close_time`
  - `test_open_interest_hist_maps_sum_open_interest_value`
- Create `tests/unit/test_binance_usdt_perp_universe_sync.py`
  - `test_dry_run_reports_insert_delete_counts_without_writes`
  - `test_execute_upserts_binance_cex_tokens_and_pricefeeds`
  - `test_execute_deletes_non_binance_backed_cex_tokens`
- Modify `tests/unit/test_settings.py`
  - Remove OKX CEX assertions.
  - Add Binance futures config assertions.
- Create `tests/unit/test_cex_binance_config_hard_cut_script.py`
  - Prove old OKX CEX keys are removed, Binance futures keys are added, backups are written only on `--execute`,
    and the script does not import application `Settings`.
- Create `tests/unit/test_cex_binance_hard_cut_cleanup.py`
  - Prove dry-run returns counts only.
  - Prove execute aborts below `--min-binance-feeds`.
  - Prove current resolutions are superseded/reinserted instead of mutated in place.
  - Prove cleanup deletes OKX CEX rows in FK-safe order and validates the source-provider constraint.
- Modify `tests/unit/test_providers_wiring.py` and `tests/unit/test_provider_capabilities.py`
  - Remove OKX CEX wiring tests.
  - Add Binance CEX provider wiring tests.
- Modify `tests/unit/test_asset_market_sync.py`
  - Replace OKX sync tests with Binance route sync tests.
- Modify `tests/unit/test_market_tick_repository.py`, `tests/unit/test_event_market_capture.py`, `tests/unit/test_market_candles_service.py`, `tests/unit/test_live_price_gateway.py`
  - Replace `okx_cex_rest` CEX fixtures with `binance_cex_rest`.
- Modify `tests/unit/test_deterministic_token_resolver.py`, `tests/unit/test_token_intent_resolver.py`, `tests/unit/test_token_radar_projection.py`, `tests/unit/test_event_token_projection.py`
  - Ensure CEX preferred feeds are Binance USDT swap.
  - Ensure explicit OKX CEX no longer resolves.
- Modify Pulse tests that assert CEX provider names:
  - `tests/unit/test_pulse_evidence_packet_builder.py`
  - `tests/unit/test_pulse_evidence_completeness_gate.py`
  - `tests/unit/test_pulse_display_status.py`
  - `tests/integration/test_pulse_evidence_repository.py`
- Modify CLI tests:
  - `tests/integration/test_cli.py`
  - Remove `sync-okx-cex-universe`.
  - Add `sync-binance-usdt-perp-universe`.
- Keep historical Alembic migration tests aware that old files may contain `okx_cex`.

### CEX OI/radar board foundation

- Create `src/gmgn_twitter_intel/domains/cex_market_intel/__init__.py`
- Create `src/gmgn_twitter_intel/domains/cex_market_intel/repositories/cex_derivative_series_repository.py`
  - Batch upsert Binance OI history points keyed by `(source_provider, exchange, instrument, family, period, timestamp_ms)`.
- Create `src/gmgn_twitter_intel/domains/cex_market_intel/repositories/cex_oi_radar_repository.py`
  - Write `cex_oi_radar_runs`.
  - Replace rows for a `run_id` in `cex_oi_radar_rows`.
  - Query latest succeeded or partial run.
- Create `src/gmgn_twitter_intel/domains/cex_market_intel/services/binance_oi_radar_builder.py`
  - Read Binance-backed `price_feeds`.
  - Fetch `ticker/24hr`, `premiumIndex`, and `openInterestHist`.
  - Compute latest OI USD, OI 4h/24h deltas, price 24h change, volume gate, funding label, bucket, and composite score.
- Create `src/gmgn_twitter_intel/domains/cex_market_intel/scoring/oi_radar_scoring.py`
  - Keep scoring deterministic and artifact-free.
  - Gate low quote-volume symbols before ranking.
- Create `src/gmgn_twitter_intel/domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py`
  - Worker uses advisory lock, rate limiter, hard timeout, and partial-run degradation.
- Create `src/gmgn_twitter_intel/app/runtime/worker_factories/cex_market_intel.py`
  - Construct `cex_oi_radar_board` only when Binance CEX provider is available.
- Modify `src/gmgn_twitter_intel/app/runtime/worker_registry.py`
  - Add `cex_oi_radar_board`.
- Modify `src/gmgn_twitter_intel/platform/config/settings.py`
  - Add `CexOiRadarBoardWorkerSettings`.
- Modify `src/gmgn_twitter_intel/app/runtime/repository_session.py`
  - Wire CEX market intel repositories.
- Create `src/gmgn_twitter_intel/app/surfaces/api/routes_cex.py`
  - Add read-only `/api/cex/radar-board`.
- Modify API route registration where existing routes are mounted.
- Create migration `src/gmgn_twitter_intel/platform/db/alembic/versions/20260521_0073_cex_oi_radar_board.py`
  - Add `cex_derivative_series_points`.
  - Add `cex_oi_radar_runs`.
  - Add `cex_oi_radar_rows`.
- Create tests:
  - `tests/unit/domains/cex_market_intel/test_oi_radar_scoring.py`
  - `tests/unit/domains/cex_market_intel/test_binance_oi_radar_builder.py`
  - `tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py`
  - `tests/integration/domains/cex_market_intel/test_cex_oi_radar_repository.py`
  - API contract test for `/api/cex/radar-board`.

### Docs

- Modify `docs/ARCHITECTURE.md`
  - Replace OKX CEX REST references with Binance CEX REST.
  - State OKX is DEX-only in current runtime.
- Modify `docs/CONTRACTS.md`
  - Update provider config contract.
  - Update ops CLI contract.
- Modify `docs/WORKERS.md`
  - Update market tick poll and event anchor CEX provider descriptions.
- Modify `src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md`
  - State CEX market facts are Binance-only.
- Regenerate:
  - `docs/generated/cli-help.md`
  - `docs/generated/db-schema.md`

## Task breakdown

### Task 0: Package CoinGlass and add operational safety gates

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `scripts/cex_binance_config_hard_cut.py`
- Modify: `Dockerfile` only if production CoinGlass browser transport is enabled
- Create or modify dependency/source architecture tests if present

- [ ] Add pinned `coinglass-cli` Git dependency and update `uv.lock`.
- [ ] Verify `uv sync --frozen` on a clean environment.
- [ ] Add standalone config migration script that can remove old `providers.okx.cex_*` keys before new `Settings` parsing runs.
- [ ] Add dry-run/execute tests for the config migration script using fixture YAML.
- [ ] Build Docker and verify `coinglass-cli` exists in the image:
  ```bash
  docker compose build app
  docker compose run --rm --no-deps app coinglass-cli --help
  docker compose run --rm --no-deps app coinglass-cli canary
  ```
  Expected: all commands exit `0`; if browser transport is disabled, record that browser-heavy commands are intentionally not part of V1 smoke.

### Task 1: Lock hard-cut expectations with tests

**Files:**
- Create: `tests/unit/test_binance_usdm_futures_client.py`
- Create: `tests/unit/test_binance_usdt_perp_universe_sync.py`
- Modify: `tests/unit/test_settings.py`
- Modify: `tests/unit/test_providers_wiring.py`
- Modify: `tests/unit/test_provider_capabilities.py`
- Modify: `tests/integration/test_cli.py`

- [ ] Add failing tests that prove Binance futures config exists and OKX CEX config is gone.
- [ ] Add failing tests for Binance exchangeInfo parsing, including `1000BONKUSDT`.
- [ ] Add failing tests for Binance universe sync dry-run and execute output.
- [ ] Add failing CLI tests proving `sync-okx-cex-universe` is absent and `sync-binance-usdt-perp-universe` exists.
- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/test_binance_usdm_futures_client.py \
    tests/unit/test_binance_usdt_perp_universe_sync.py \
    tests/unit/test_cex_binance_config_hard_cut_script.py \
    tests/unit/test_cex_binance_hard_cut_cleanup.py \
    tests/unit/test_settings.py \
    tests/unit/test_providers_wiring.py \
    tests/unit/test_provider_capabilities.py \
    tests/integration/test_cli.py \
    -q
  ```
  Expected: fails on missing Binance futures client, settings, provider wiring, and CLI command.

### Task 2: Add Binance USD-M futures provider

**Files:**
- Create: `src/gmgn_twitter_intel/integrations/binance/usdm_futures_client.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/provider_wiring/binance.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/providers.py`

- [ ] Implement `BinanceUsdmFuturesClient` with httpx and deterministic parser helpers.
- [ ] Implement `BinanceUsdmFuturesMarketProvider` that returns existing `CexTicker` and `MarketCandle` shapes.
- [ ] Add route shape for Binance USDT perpetual universe.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_binance_usdm_futures_client.py -q
  ```
  Expected: pass.

### Task 3: Hard-cut config and provider wiring

**Files:**
- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/provider_wiring/types.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/provider_wiring/asset_market.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/provider_wiring/okx.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/config.py`
- Delete: `src/gmgn_twitter_intel/integrations/okx/cex_client.py` after shared helper extraction.

- [ ] Remove OKX CEX settings and accessors.
- [ ] Add Binance futures settings and defaults.
- [ ] Replace `sync_cex_market` / `message_cex_market` with single Binance-backed `cex_market`.
- [ ] Remove OKX CEX provider construction while keeping OKX DEX providers.
- [ ] Update config command output.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_settings.py tests/unit/test_providers_wiring.py tests/unit/test_provider_capabilities.py -q
  ```
  Expected: pass.

### Task 4: Replace OKX CEX universe sync with Binance USDT perp sync

**Files:**
- Create: `src/gmgn_twitter_intel/domains/asset_market/services/binance_usdt_perp_universe_sync.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/services/asset_market_sync.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/parser.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
- Modify: `tests/unit/test_asset_market_sync.py`
- Modify: `tests/integration/test_cli.py`

- [ ] Implement explicit Binance route sync.
- [ ] Remove OKX ticker-shape parsing from active sync path.
- [ ] Add registry helpers for Binance-backed CEX feeds and cleanup counts.
- [ ] Remove `sync-okx-cex-universe` CLI parser and handler.
- [ ] Add `sync-binance-usdt-perp-universe --dry-run --execute`.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_asset_market_sync.py tests/unit/test_binance_usdt_perp_universe_sync.py tests/integration/test_cli.py -q
  ```
  Expected: pass.

### Task 5: Hard-cut CEX registry preference and resolution

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/deterministic_token_resolver.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/queries/event_token_projection_query.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_target_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/account_quality/repositories/account_quality_repository.py`
- Modify: `tests/unit/test_deterministic_token_resolver.py`
- Modify: `tests/unit/test_token_intent_resolver.py`
- Modify: `tests/unit/test_token_radar_projection.py`
- Modify: `tests/unit/test_event_token_projection.py`
- Modify account-quality tests that assert CEX market target construction.

- [ ] Change preferred CEX feed SQL to Binance USDT swap only.
- [ ] Replace every duplicated CEX preferred-feed lateral query with Binance-only filters.
- [ ] Ensure explicit OKX CEX exchange lookup does not resolve.
- [ ] Ensure CEX target payloads surface Binance `provider/native_market_id`.
- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/test_deterministic_token_resolver.py \
    tests/unit/test_token_intent_resolver.py \
    tests/unit/test_token_radar_projection.py \
    tests/unit/test_event_token_projection.py \
    -q
  ```
  Expected: pass.

### Task 6: Switch CEX market facts, event anchors, and candles to Binance

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/asset_market/types/market_tick.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_poll_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/services/event_market_capture.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/event_anchor_backfill_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/read_models/market_candles_service.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_factories/asset_market.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/routes_search.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/live_price_gateway.py`
- Modify CEX provider-name tests listed in File-level edits.

- [ ] Replace CEX source constants with `binance_cex_rest`.
- [ ] Read CEX provider from `providers.cex_market`.
- [ ] Make CEX event anchor comments and skip reasons Binance-specific.
- [ ] Change CEX candle source to `binance_cex_candles`.
- [ ] Preserve `open_interest_usd` in live market payloads for CEX ticks.
- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/test_market_tick_repository.py \
    tests/unit/test_event_market_capture.py \
    tests/unit/test_market_candles_service.py \
    tests/unit/test_live_price_gateway.py \
    tests/unit/test_pulse_evidence_packet_builder.py \
    tests/unit/test_pulse_evidence_completeness_gate.py \
    tests/unit/test_pulse_display_status.py \
    tests/integration/test_pulse_evidence_repository.py \
    -q
  ```
  Expected: pass.

### Task 7: Add additive migration and lifecycle-safe SQL cleanup

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260521_0072_cex_binance_source_provider_additive.py`
- Create: `src/gmgn_twitter_intel/domains/asset_market/services/cex_binance_hard_cut_cleanup.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/parser.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
- Modify: `tests/integration/test_postgres_schema_runtime.py`
- Create or modify cleanup-focused tests under `tests/integration/`

- [ ] Add migration that drops old `market_ticks.source_provider` check and adds Binance-only CEX provider check as `NOT VALID`.
- [ ] Add `ops cex-binance-hard-cut-cleanup --dry-run --execute --min-binance-feeds`.
- [ ] Implement cleanup as one SQL transaction with advisory lock, Binance feed threshold, lifecycle-safe resolution supersede/insert, read-model deletion, OKX CEX tick detachment/deletion, CEX token deletion, and constraint validation.
- [ ] Add tests proving old current CEX resolutions are not mutated in place: they are superseded and replaced with either Binance-repointed or NIL current rows.
- [ ] Add schema/runtime tests for the new check constraint, validated constraint state after cleanup, and absence of OKX CEX rows after cleanup.
- [ ] Run:
  ```bash
  uv run pytest tests/integration/test_postgres_schema_runtime.py tests/integration/test_cli.py -q
  ```
  Expected: pass.

### Task 8: Add Binance-only OI/radar board foundation

**Files:**
- Create: `src/gmgn_twitter_intel/domains/cex_market_intel/repositories/cex_derivative_series_repository.py`
- Create: `src/gmgn_twitter_intel/domains/cex_market_intel/repositories/cex_oi_radar_repository.py`
- Create: `src/gmgn_twitter_intel/domains/cex_market_intel/services/binance_oi_radar_builder.py`
- Create: `src/gmgn_twitter_intel/domains/cex_market_intel/scoring/oi_radar_scoring.py`
- Create: `src/gmgn_twitter_intel/domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py`
- Create: `src/gmgn_twitter_intel/app/runtime/worker_factories/cex_market_intel.py`
- Create: `src/gmgn_twitter_intel/app/surfaces/api/routes_cex.py`
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260521_0073_cex_oi_radar_board.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_registry.py`
- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- Create tests under `tests/unit/domains/cex_market_intel/` and `tests/integration/domains/cex_market_intel/`

- [ ] Add OI/radar schema and repository methods.
- [ ] Add deterministic scoring and builder from Binance-only inputs.
- [ ] Add worker with advisory lock, request-rate control, and partial degradation.
- [ ] Add read-only API route for latest board.
- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/domains/cex_market_intel \
    tests/integration/domains/cex_market_intel \
    -q
  ```
  Expected: pass.

### Task 9: Update docs and generated artifacts

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/WORKERS.md`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md`
- Regenerate: `docs/generated/cli-help.md`
- Regenerate: `docs/generated/db-schema.md`

- [ ] Replace current OKX CEX runtime docs with Binance-only CEX docs.
- [ ] Keep OKX DEX docs intact.
- [ ] Regenerate CLI help and DB schema docs with existing repo commands.
- [ ] Run generated-doc tests:
  ```bash
  uv run pytest tests/integration/test_docs_generated.py -q
  ```
  Expected: pass.

### Task 10: Full verification and residue scan

**Files:**
- No code edits in this task unless verification exposes a miss.

- [ ] Run targeted CEX suite:
  ```bash
  uv run pytest \
    tests/unit/test_binance_usdm_futures_client.py \
    tests/unit/test_binance_usdt_perp_universe_sync.py \
    tests/unit/test_settings.py \
    tests/unit/test_providers_wiring.py \
    tests/unit/test_provider_capabilities.py \
    tests/unit/test_asset_market_sync.py \
    tests/unit/test_market_tick_repository.py \
    tests/unit/test_event_market_capture.py \
    tests/unit/domains/cex_market_intel \
    tests/integration/domains/cex_market_intel \
    tests/unit/test_market_candles_service.py \
    tests/unit/test_deterministic_token_resolver.py \
    tests/integration/test_cli.py \
    tests/integration/test_postgres_schema_runtime.py \
    -q
  ```
- [ ] Run architecture residue scan:
  ```bash
  rg -n "OkxCex|okx_cex_rest|sync-okx-cex-universe|cex_inst_types|cex_sync_enabled|message_cex_market|sync_cex_market" \
    src tests docs/ARCHITECTURE.md docs/CONTRACTS.md docs/WORKERS.md \
    --glob '!src/gmgn_twitter_intel/platform/db/alembic/versions/*'
  ```
  Expected: no runtime/test/doc hits except planned hard-cut spec and completed-plan text.
- [ ] Run:
  ```bash
  uv run ruff check .
  ```
  Expected: pass.
- [ ] Run broad test smoke:
  ```bash
  uv run pytest -q
  ```
  Expected: pass or only documented unrelated baseline failures.

## PR breakdown

Because this is a breaking hard cut, land as **one production PR** after all tasks pass. Use review slices internally:

1. **Slice 0 — Packaging and operational gates**: Task 0.
2. **Slice 1 — Binance provider and tests**: Tasks 1-2.
3. **Slice 2 — Config and provider wiring hard cut**: Task 3.
4. **Slice 3 — Universe sync and registry preference**: Tasks 4-5.
5. **Slice 4 — Market facts/candles/event anchors**: Task 6.
6. **Slice 5 — Additive migration and SQL cleanup command**: Task 7.
7. **Slice 6 — Binance OI/radar board foundation**: Task 8.
8. **Slice 7 — Docs and final verification**: Tasks 9-10.

Do not merge a partial slice to main unless it still passes full runtime startup without OKX CEX compatibility code.

## Rollout order

Do not use `make docker-up` for the first hard-cut rollout, because it starts `app` immediately after `migrate`. Use explicit steps so config migration, Binance sync, and cleanup finish before the app starts.

1. Create DB backup.
2. Back up and migrate operator config:
   ```bash
   cp ~/.gmgn-twitter-intel/config.yaml ~/.gmgn-twitter-intel/config.yaml.pre-cex-binance-hard-cut
   uv run python scripts/cex_binance_config_hard_cut.py --dry-run
   uv run python scripts/cex_binance_config_hard_cut.py --execute
   ```
3. Stop app and workers.
4. Build images and verify packaged dependency:
   ```bash
   docker compose build app migrate
   docker compose run --rm --no-deps app coinglass-cli --help
   docker compose run --rm --no-deps app coinglass-cli canary
   ```
5. Start Postgres and apply additive migration. This migration must be safe before Binance universe sync:
   ```bash
   docker compose up -d postgres
   docker compose run --rm migrate
   ```
6. Run Binance universe sync dry-run:
   ```bash
   docker compose run --rm --no-deps app gmgn-twitter-intel ops sync-binance-usdt-perp-universe --dry-run
   ```
   Expected: `binance_usdt_perp_seen >= 400`.
7. Run Binance universe sync execute:
   ```bash
   docker compose run --rm --no-deps app gmgn-twitter-intel ops sync-binance-usdt-perp-universe --execute
   ```
8. Run SQL cleanup dry-run:
   ```bash
   docker compose run --rm --no-deps app gmgn-twitter-intel ops cex-binance-hard-cut-cleanup --dry-run --min-binance-feeds 400
   ```
   Expected: cleanup counts are plausible and no abort reason is present.
9. Run SQL cleanup execute:
   ```bash
   docker compose run --rm --no-deps app gmgn-twitter-intel ops cex-binance-hard-cut-cleanup --execute --min-binance-feeds 400
   ```
   Expected: OKX CEX rows are removed and `market_ticks_source_provider_check` is validated.
10. Clean-reset Token Radar derived storage:
   ```bash
   docker compose run --rm --no-deps app gmgn-twitter-intel ops reset-token-radar-postgres-hard-cut --execute
   ```
   Expected: Token Radar current/history/audit storage starts from zero and the next projection rebuilds from current material facts.
11. Start app:
   ```bash
   docker compose up -d app
   ```
11. Run worker catch-up once or allow scheduled catch-up:
   - `resolution_refresh`
   - `token_radar_projection`
   - `token_capture_tier`
   - `market_tick_poll`
12. Verify DB absence queries, constraint validation, and product smoke below.

## Rollback

Rollback is DB backup + code rollback. There is no runtime OKX fallback.

1. Stop app and workers.
2. Restore DB backup taken before hard-cut cleanup.
3. Deploy previous code revision.
4. Start app and workers.
5. Run `uv run gmgn-twitter-intel config` and confirm OKX CEX config returns only on the old code path.

The destructive cleanup command is not safely reversible from production tables because it deletes OKX CEX facts and routes. The backup is the rollback artifact.

## Acceptance test commands

- AC0: CoinGlass is packaged into the Docker image.
  ```bash
  docker compose build app
  docker compose run --rm --no-deps app coinglass-cli --help
  docker compose run --rm --no-deps app coinglass-cli canary
  ```
  Expected: all commands exit `0`.

- AC1: Binance universe sync dry-run returns expected count.
  ```bash
  uv run gmgn-twitter-intel ops sync-binance-usdt-perp-universe --dry-run
  ```
  Expected JSON fields: `binance_usdt_perp_seen`, `cex_tokens_to_insert`, `cex_tokens_to_delete`, `pricefeeds_to_insert`, `old_okx_cex_rows_to_delete`.

- AC2: OKX CEX CLI is gone.
  ```bash
  uv run gmgn-twitter-intel ops --help | rg "sync-okx-cex-universe"
  ```
  Expected: no match.

- AC3: Binance CEX CLI exists.
  ```bash
  uv run gmgn-twitter-intel ops --help | rg "sync-binance-usdt-perp-universe"
  ```
  Expected: match.

- AC3b: Cleanup CLI exists and supports dry-run/execute.
  ```bash
  uv run gmgn-twitter-intel ops --help | rg "cex-binance-hard-cut-cleanup"
  ```
  Expected: match.

- AC4: Runtime residue scan has no OKX CEX compatibility code.
  ```bash
  rg -n "OkxCex|okx_cex_rest|sync-okx-cex-universe|cex_inst_types|cex_sync_enabled|message_cex_market|sync_cex_market" \
    src tests docs/ARCHITECTURE.md docs/CONTRACTS.md docs/WORKERS.md \
    --glob '!src/gmgn_twitter_intel/platform/db/alembic/versions/*'
  ```
  Expected: no runtime/test/doc hits except hard-cut planning docs if included in the search.

- AC5: DB has no OKX CEX rows after cleanup.
  ```sql
  SELECT count(*) FROM price_feeds WHERE provider = 'okx' AND feed_type LIKE 'cex_%';
  SELECT count(*) FROM market_ticks WHERE source_provider = 'okx_cex_rest';
  SELECT count(*) FROM market_ticks WHERE target_type = 'cex_symbol' AND target_id LIKE 'okx:%';
  SELECT count(*) FROM token_capture_tier WHERE target_type = 'cex_symbol' AND target_id LIKE 'okx:%';
  SELECT count(*) FROM price_observations WHERE provider IN ('okx_cex', 'okx') OR pricefeed_id LIKE 'pricefeed:cex:okx:%';
  ```
  Expected: all counts are `0`.

- AC5b: `market_ticks.source_provider` final check is validated.
  ```sql
  SELECT convalidated
  FROM pg_constraint
  WHERE conname = 'market_ticks_source_provider_check';
  ```
  Expected: `true`.

- AC6: DB has Binance USDT perp feeds.
  ```sql
  SELECT count(*)
  FROM price_feeds
  WHERE provider = 'binance'
    AND feed_type = 'cex_swap'
    AND quote_symbol = 'USDT'
    AND status = 'canonical';
  ```
  Expected: count above `400`.

- AC7: CEX market tick can be written with Binance provider.
  ```bash
  uv run pytest tests/unit/test_event_market_capture.py tests/unit/test_market_tick_repository.py -q
  ```
  Expected: pass, with fixtures asserting `binance_cex_rest`.

- AC8: Binance-only OI/radar board foundation passes.
  ```bash
  uv run pytest tests/unit/domains/cex_market_intel tests/integration/domains/cex_market_intel -q
  ```
  Expected: pass, with rows using `target_id='binance:<symbol>USDT'`.

- AC9: Latest board API is read-only and Binance-only.
  ```bash
  uv run pytest tests/integration/test_api_http.py -q
  ```
  Expected: pass, including `/api/cex/radar-board` contract coverage if route tests live in this file.

- AC10: Full verification.
  ```bash
  uv run ruff check .
  uv run pytest -q
  ```
  Expected: pass or only unrelated baseline failures recorded in Pre-flight.

## Verification artifact

Create `docs/superpowers/plans/active/2026-05-21-cex-binance-hard-cut-verification-cn.md` before declaring implementation complete. It must include:

- Baseline test status.
- Exact Binance universe dry-run output with secrets absent.
- Config migration result.
- Docker packaging result for `coinglass-cli`.
- Additive migration result.
- SQL cleanup dry-run and execute results.
- DB absence query results.
- Constraint validation result.
- Residue scan result.
- Targeted pytest commands and broad pytest result.
- Product smoke notes for Token Case, live market, and Pulse evidence.
