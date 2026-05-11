# Token Radar Anchor / Live Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Token Radar's database-backed current-price path and hard-split persisted anchor price from transient live price, with no compatibility fields, no dual writes, and no old `market_update/current_market` fallback.

**Architecture:** Persist one message-bound anchor price through a renamed AnchorPriceWorker and `token_market_price_baselines`. Delete the DB ticker cache path (`current_market_field_facts`, current-market read model, periodic refresh observations, WS live observations) and replace it with a process-local LivePriceGateway that publishes `live_market_update` and serves `/api/live-market` from memory. Token Radar HTTP rows expose `anchor_price`; frontend stores `live_market` separately and computes deltas locally.

**Tech Stack:** Python 3, PostgreSQL/Alembic, FastAPI, existing OKX CEX/DEX provider adapters, React/TypeScript, TanStack Query, pytest, Vitest, ruff.

---

## Hard-Cut Rules

- No `current_market` field in `/api/token-radar` rows.
- No `/api/current-market` endpoint.
- No WebSocket `market_update` payload.
- No `CurrentMarketRepository`, `CurrentMarketService`, `current_market_field_facts`, or `backfill-current-market-field-facts`.
- No live/refresh worker writes to `price_observations`.
- No TokenDiscovery pricefeed or price-observation side effects for DEX search.
- No `message_quote` compatibility branch. The canonical anchor observation kind is `message_anchor`; migration rewrites existing `message_quote` baselines/observations once.
- No frontend parser fallback from `anchor_price` to `current_market`.

## Pre-flight

- [ ] Create worktree:
  ```bash
  git worktree add .worktrees/token-radar-anchor-live-hard-cut -b codex/token-radar-anchor-live-hard-cut main
  ```
- [ ] Verify worktree:
  ```bash
  cd .worktrees/token-radar-anchor-live-hard-cut
  git branch --show-current
  git status --short
  ```
  Expected branch: `codex/token-radar-anchor-live-hard-cut`. Expected status: clean, except intentionally carried worktree-local files.
- [ ] Run baseline checks:
  ```bash
  uv run ruff check .
  uv run pytest -q
  npm --prefix web test -- --run
  ```
  Expected: record current failures before editing. Do not start implementation if failures are unrelated and unexplained.

## File Structure

### Schema and repositories

- Create Alembic migration `src/gmgn_twitter_intel/platform/db/alembic/versions/20260511_0029_anchor_live_hard_cut.py`
  - Delete non-anchor price observations.
  - Rewrite `message_quote` to `message_anchor`.
  - Drop `current_market_field_facts`.
  - Drop current-market price indexes.
  - Add anchor-only partial unique/indexes.
- Modify `src/gmgn_twitter_intel/domains/asset_market/repositories/price_observation_repository.py`
  - Remove `_write_current_market_field_facts(...)`.
  - Remove `backfill_current_market_field_facts(...)`.
  - Keep baseline upsert for `observation_kind="message_anchor"` only.
  - Reject runtime writes with missing `source_resolution_id` unless explicitly marked as future settlement kind.
- Delete `src/gmgn_twitter_intel/domains/asset_market/repositories/current_market_repository.py`.
- Delete `src/gmgn_twitter_intel/domains/asset_market/read_models/current_market_service.py`.
- Modify `src/gmgn_twitter_intel/app/runtime/repository_session.py`
  - Remove `current_market` from `RepositorySession`.
- Modify `src/gmgn_twitter_intel/domains/asset_market/interfaces.py`
  - Remove `CurrentMarketRepository`, `CurrentMarketService`, and `sync_dex_prices` exports.

### Anchor worker

- Rename `src/gmgn_twitter_intel/domains/asset_market/queries/pending_market_observation_query.py` to `src/gmgn_twitter_intel/domains/asset_market/queries/pending_anchor_price_query.py`.
- Rename `src/gmgn_twitter_intel/domains/asset_market/services/message_market_observation.py` to `src/gmgn_twitter_intel/domains/asset_market/services/anchor_price_observation.py`.
- Rename `src/gmgn_twitter_intel/domains/asset_market/runtime/message_market_observation_worker.py` to `src/gmgn_twitter_intel/domains/asset_market/runtime/anchor_price_worker.py`.
- Rename public names:
  - `PendingMarketObservationQuery` -> `PendingAnchorPriceQuery`
  - `observe_message_market(...)` -> `observe_anchor_prices(...)`
  - `MessageMarketObservationWorker` -> `AnchorPriceWorker`
- Change all anchor writes to `observation_kind="message_anchor"`.

### Identity and route workers

- Modify `src/gmgn_twitter_intel/domains/asset_market/services/asset_market_sync.py`
  - Rename `sync_cex_universe(...)` to `sync_cex_routes(...)`.
  - Remove `price_observations` parameter and all ticker observation writes.
  - Delete `sync_dex_prices(...)` and DEX refresh constants.
- Delete `src/gmgn_twitter_intel/domains/asset_market/runtime/asset_market_sync_worker.py`.
- Delete `src/gmgn_twitter_intel/domains/asset_market/services/market_freshness_demand.py`.
- Modify `src/gmgn_twitter_intel/domains/asset_market/runtime/token_discovery_worker.py`
  - Remove `pricefeeds_written` and `price_observations_written` counters.
  - Remove DEX `upsert_pricefeed(...)` and `insert_observation(...)` from `_write_dex_candidate(...)`.
  - Continue writing `asset_identity_evidence.raw_payload_json` with OKX candidate metadata.
- Modify `src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py`
  - Replace `find_assets_by_symbol_with_latest_observation(...)` with identity-evidence metadata reads.
  - Remove `chain_assets_needing_radar_price_refresh(...)`.
  - Replace `active_dex_market_stream_targets(...)` with `active_live_market_targets(...)` returning hot Asset and CexToken targets.

### Live price gateway

- Delete `src/gmgn_twitter_intel/domains/asset_market/runtime/dex_market_stream_worker.py`.
- Create `src/gmgn_twitter_intel/domains/asset_market/runtime/live_price_gateway.py`
  - `LivePriceGateway`: selects hot targets, streams DEX prices, polls CEX tickers, updates in-memory cache, publishes `live_market_update`.
  - `LiveMarketCache`: process-local target snapshot map.
  - `LiveMarketSnapshot`: normalized payload builder.
- Modify `src/gmgn_twitter_intel/app/runtime/app.py`
  - Replace `asset_market_sync_worker`, `message_market_observation_worker`, and `dex_market_stream_worker` runtime fields with `anchor_price_worker`, optional `cex_route_sync_worker` if implemented, and `live_price_gateway`.
  - Start only AnchorPriceWorker, TokenDiscoveryWorker, TokenRadarProjectionWorker, Pulse/Notification workers, and LivePriceGateway.

### Token Radar projection/API

- Modify `src/gmgn_twitter_intel/domains/token_intel/_constants.py`
  - `TOKEN_RADAR_PROJECTION_VERSION = "token-radar-v12-anchor-live-hard-cut"`
  - `TOKEN_RADAR_SOURCE_TABLE = "token_intent_resolutions+asset_identity_current+anchor_price"`
- Modify `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
  - Delete `_hydrate_current_market(...)`.
  - Delete `_row_with_current_market(...)`, `_missing_current_market_fields(...)`, and `MARKET_FRESH_MS`.
  - Build market/factor facts from anchor baselines and identity metadata only.
  - Remove DB live market freshness as a high-alert blocker input.
- Modify `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py`
  - Remove `_market_freshness_block_reason(...)` and the hard block it produces.
  - Make missing market metadata a risk/data-health fact, not a blocker.
  - Keep `timing_response` display-only with zero rank contribution until a settlement sampler exists.
- Modify `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py`
  - Constructor becomes `AssetFlowService(token_radar=...)`.
  - `_public_row(...)` returns `anchor_price`, not `current_market`.
  - Projection payload reports `anchor_coverage`, not `market_hydration`.
- Modify `src/gmgn_twitter_intel/app/surfaces/api/http.py`
  - `/api/token-radar` constructs `AssetFlowService(token_radar=repos.token_radar)`.
  - Delete `/api/current-market`.
  - Add `/api/live-market` that reads `runtime.live_price_gateway.snapshot(...)` only.
- Modify `src/gmgn_twitter_intel/app/surfaces/api/ws.py`
  - Route `live_market_update` through `market_targets`.
  - Delete routing branch for `market_update`.
- Modify `src/gmgn_twitter_intel/app/surfaces/cli/main.py`
  - Delete `current-market` command.
  - Delete `ops backfill-current-market-field-facts`.
  - Change route sync command to call `sync_cex_routes(...)` and report no observation counters.
- Modify `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py`
  - Read price/market facts from `anchor_price` and factor snapshot identity metadata, not `row.current_market`.

### Frontend

- Modify `web/src/api/types.ts`
  - Delete `CurrentMarketSnapshot` from `AssetFlowRow`.
  - Replace `MarketUpdatePayload` with `LiveMarketUpdatePayload`.
  - Add `AnchorPriceSnapshot` and `LiveMarketSnapshot`.
- Modify `web/src/api/useIntelSocket.ts`
  - Store `liveMarketUpdates`.
  - Accept only `payload.type === "live_market_update"` for market target updates.
- Rename `web/src/features/live/marketUpdatePatch.ts` to `web/src/features/live/liveMarketUpdatePatch.ts`.
  - Patch `row.live_market`, not `row.current_market`.
- Modify `web/src/lib/tokenRadar.ts`
  - Delete `requiredCurrentMarket(...)`.
  - Require `row.anchor_price`.
  - Use `row.live_market` when present for current display price.
  - Compute delta fields from `live_market.price_usd` and `anchor_price.price_usd`.
- Modify `web/src/App.tsx` and related tests
  - Subscribe to market targets as today.
  - Apply `liveMarketUpdates`.
  - Render missing live price as missing/stale without contract fallback.
- Regenerate or hard-edit `web/src/api/openapi.ts` after API schema changes. No `/api/current-market` operation remains.

### Docs

- Modify `docs/ARCHITECTURE.md`.
- Modify `docs/CONTRACTS.md`.
- Modify `docs/FRONTEND.md`.
- Modify `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`.
- Regenerate `docs/generated/cli-help.md` after CLI removal.

---

## Task 1: Schema And Price Repository Hard Cut

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260511_0029_anchor_live_hard_cut.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/price_observation_repository.py`
- Delete: `src/gmgn_twitter_intel/domains/asset_market/repositories/current_market_repository.py`
- Delete: `src/gmgn_twitter_intel/domains/asset_market/read_models/current_market_service.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/interfaces.py`
- Delete tests: `tests/test_current_market_repository.py`
- Modify tests: `tests/test_price_observation_read_models.py`, `tests/integration/test_price_observation_repository.py`, `tests/unit/test_price_observation_repository_policy.py`, `tests/unit/test_postgres_schema.py`

- [ ] **Step 1: Write failing tests for removed current-market read model**

  Replace `tests/test_price_observation_read_models.py` with anchor baseline assertions:

  ```python
  def test_insert_message_anchor_writes_baseline_without_current_market_facts(tmp_path):
      conn = connect_test_db(tmp_path)
      repo = PriceObservationRepository(conn)

      observation = repo.insert_observation(
          provider="okx",
          pricefeed_id="feed-1",
          observed_at_ms=1_778_000_001_000,
          subject_type="Asset",
          subject_id="asset:solana:token:abc",
          price_usd=0.42,
          price_basis="usd",
          source_event_id="event-1",
          source_intent_id="intent-1",
          source_resolution_id="resolution-1",
          observation_kind="message_anchor",
          event_received_at_ms=1_778_000_000_000,
      )

      baseline = conn.execute(
          "SELECT * FROM token_market_price_baselines WHERE resolution_id = %s",
          ("resolution-1",),
      ).fetchone()

      assert observation["observation_kind"] == "message_anchor"
      assert baseline["event_price_observation_kind"] == "message_anchor"
      assert baseline["event_price_usd"] == 0.42
      with pytest.raises(Exception):
          conn.execute("SELECT COUNT(*) FROM current_market_field_facts").fetchone()
  ```

- [ ] **Step 2: Run focused tests and verify red**

  ```bash
  uv run pytest tests/test_price_observation_read_models.py tests/integration/test_price_observation_repository.py -q
  ```

  Expected failures: `message_anchor` is not used for baselines yet; `current_market_field_facts` still exists/writes.

- [ ] **Step 3: Add destructive hard-cut migration**

  Create migration body:

  ```python
  """Hard-cut Token Radar anchor/live market boundary."""

  from __future__ import annotations

  from alembic import op

  revision = "20260511_0029"
  down_revision = "20260511_0028"
  branch_labels = None
  depends_on = None


  def upgrade() -> None:
      op.execute("UPDATE price_observations SET observation_kind = 'message_anchor' WHERE observation_kind = 'message_quote'")
      op.execute(
          """
          UPDATE token_market_price_baselines
          SET event_price_observation_kind = 'message_anchor'
          WHERE event_price_observation_kind = 'message_quote'
          """
      )
      op.execute(
          """
          DELETE FROM price_observations
          WHERE COALESCE(observation_kind, '') <> 'message_anchor'
          """
      )
      with op.get_context().autocommit_block():
          for name in (
              "idx_current_market_field_facts_latest",
              "idx_price_observations_current_price",
              "idx_price_observations_current_market_cap",
              "idx_price_observations_current_liquidity",
              "idx_price_observations_current_holders",
              "idx_price_observations_current_volume_24h",
              "idx_price_observations_current_open_interest",
              "idx_price_observations_message_resolution_latest",
          ):
              op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
          op.execute(
              """
              CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_price_observations_message_anchor_resolution
              ON price_observations(source_resolution_id)
              WHERE observation_kind = 'message_anchor' AND source_resolution_id IS NOT NULL
              """
          )
          op.execute(
              """
              CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_anchor_subject_time
              ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
              WHERE observation_kind = 'message_anchor'
              """
          )
      op.execute("DROP TABLE IF EXISTS current_market_field_facts")


  def downgrade() -> None:
      op.execute(
          """
          CREATE TABLE IF NOT EXISTS current_market_field_facts (
            subject_type TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            field_key TEXT NOT NULL,
            value_json JSONB NOT NULL,
            observed_at_ms BIGINT NOT NULL,
            provider TEXT NOT NULL,
            source_observation_id TEXT NOT NULL,
            updated_at_ms BIGINT NOT NULL,
            PRIMARY KEY(subject_type, subject_id, field_key, source_observation_id)
          )
          """
      )
      with op.get_context().autocommit_block():
          op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_anchor_subject_time")
          op.execute("DROP INDEX CONCURRENTLY IF EXISTS uq_price_observations_message_anchor_resolution")
          op.execute(
              """
              CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_current_market_field_facts_latest
              ON current_market_field_facts(
                subject_type, subject_id, field_key, observed_at_ms DESC, source_observation_id DESC
              )
              """
          )
  ```

  Downgrade recreates the table shape only; deleted refresh rows are intentionally not restored.

- [ ] **Step 4: Remove current-market side effects from `PriceObservationRepository`**

  In `insert_observation(...)`:

  - Delete the call to `self._write_current_market_field_facts(...)`.
  - Change baseline condition to:

    ```python
    if observation_kind == "message_anchor" and source_event_id and source_intent_id and source_resolution_id:
        self._upsert_price_baseline(...)
    ```

  - Delete `_write_current_market_field_facts(...)`.
  - Delete `backfill_current_market_field_facts(...)`.
  - Keep `provider == "gmgn_payload"` rejection.

- [ ] **Step 5: Remove current-market repository wiring**

  Delete the repository/service files and remove imports/fields from `repository_session.py` and `asset_market/interfaces.py`.

- [ ] **Step 6: Run focused schema/repository tests**

  ```bash
  uv run pytest tests/test_price_observation_read_models.py tests/integration/test_price_observation_repository.py tests/unit/test_price_observation_repository_policy.py tests/unit/test_postgres_schema.py -q
  ```

  Expected: all pass; no test imports `CurrentMarketRepository`.

- [ ] **Step 7: Commit**

  ```bash
  git add src/gmgn_twitter_intel/platform/db/alembic/versions/20260511_0029_anchor_live_hard_cut.py \
          src/gmgn_twitter_intel/domains/asset_market/repositories/price_observation_repository.py \
          src/gmgn_twitter_intel/app/runtime/repository_session.py \
          src/gmgn_twitter_intel/domains/asset_market/interfaces.py \
          tests/test_price_observation_read_models.py \
          tests/integration/test_price_observation_repository.py \
          tests/unit/test_price_observation_repository_policy.py \
          tests/unit/test_postgres_schema.py
  git add -u src/gmgn_twitter_intel/domains/asset_market/repositories/current_market_repository.py \
             src/gmgn_twitter_intel/domains/asset_market/read_models/current_market_service.py \
             tests/test_current_market_repository.py
  git commit -m "refactor: hard cut current market persistence"
  ```

## Task 2: Rename Message Quotes To Anchor Prices

**Files:**
- Move: `src/gmgn_twitter_intel/domains/asset_market/queries/pending_market_observation_query.py` -> `src/gmgn_twitter_intel/domains/asset_market/queries/pending_anchor_price_query.py`
- Move: `src/gmgn_twitter_intel/domains/asset_market/services/message_market_observation.py` -> `src/gmgn_twitter_intel/domains/asset_market/services/anchor_price_observation.py`
- Move: `src/gmgn_twitter_intel/domains/asset_market/runtime/message_market_observation_worker.py` -> `src/gmgn_twitter_intel/domains/asset_market/runtime/anchor_price_worker.py`
- Modify: imports in `src/gmgn_twitter_intel/app/runtime/app.py`
- Move tests: `tests/unit/test_message_market_observation.py` -> `tests/unit/test_anchor_price_observation.py`
- Modify integration tests that assert `message_quote`.

- [ ] **Step 1: Write failing anchor worker tests**

  In `tests/unit/test_anchor_price_observation.py`, assert:

  ```python
  def test_anchor_price_observation_writes_dex_message_anchor_per_resolution():
      result = observe_anchor_prices(
          repos=repos,
          dex_market=dex_market,
          now_ms=1_778_000_005_000,
          limit=100,
      )

      assert result["anchor_observations_written"] == 1
      observation = repos.price_observations.observations[0]
      assert observation["provider"] == "okx"
      assert observation["observation_kind"] == "message_anchor"
      assert observation["source_resolution_id"] == "resolution-1"
      assert observation["event_received_at_ms"] == 1_778_000_000_000
      assert observation["price_usd"] == 0.42
  ```

  Also assert the second run with the same `resolution_id` selects no rows.

- [ ] **Step 2: Run focused tests and verify red**

  ```bash
  uv run pytest tests/unit/test_anchor_price_observation.py tests/integration/test_price_observation_repository.py -q
  ```

  Expected: missing module/names and old `message_quote` assertions fail.

- [ ] **Step 3: Rename files and public names**

  Use `git mv` for the three production files and unit test file. Replace class/function/query names with Anchor names. Update imports in app runtime and tests.

- [ ] **Step 4: Change pending query to anchor semantics**

  In `PendingAnchorPriceQuery.pending_rows(...)`, replace the `NOT EXISTS` condition with:

  ```sql
  AND NOT EXISTS (
    SELECT 1
    FROM price_observations po
    WHERE po.source_resolution_id = token_intent_resolutions.resolution_id
      AND po.observation_kind = 'message_anchor'
  )
  ```

  Remove `message_payload` and `message_quote` from query logic.

- [ ] **Step 5: Change anchor writes**

  In `anchor_price_observation.py`, write:

  ```python
  repos.price_observations.insert_observation(
      provider="okx",
      pricefeed_id=str(row.get("pricefeed_id") or "") or None,
      observed_at_ms=price.observed_at_ms or now_ms,
      subject_type=str(row["target_type"]),
      subject_id=str(row["target_id"]),
      price_usd=price.price_usd,
      price_quote=None,
      quote_symbol="USD",
      price_basis="usd",
      market_cap_usd=None,
      liquidity_usd=None,
      volume_24h_usd=None,
      open_interest_usd=None,
      holders=None,
      observation_kind="message_anchor",
      source_event_id=str(row["event_id"]),
      source_intent_id=str(row["intent_id"]),
      source_resolution_id=str(row["resolution_id"]),
      event_received_at_ms=int(row["event_received_at_ms"]),
      raw_payload={**price.raw, "payload_hash": _payload_hash(price.raw)},
      commit=False,
  )
  ```

  Result counters:

  ```python
  {
      "rows_selected": len(rows),
      "cex_ticker_requests": 0,
      "dex_price_requests": 0,
      "anchor_observations_written": 0,
      "skipped_missing_pricefeed": 0,
      "skipped_missing_provider": 0,
      "skipped_missing_market": 0,
  }
  ```

- [ ] **Step 6: Run anchor tests**

  ```bash
  uv run pytest tests/unit/test_anchor_price_observation.py tests/unit/test_token_target_stage_builder.py tests/unit/test_token_target_posts_service.py tests/integration/test_price_observation_repository.py -q
  ```

  Expected: pass; no assertion expects `message_quote`.

- [ ] **Step 7: Commit**

  ```bash
  git add -A src/gmgn_twitter_intel/domains/asset_market/queries \
             src/gmgn_twitter_intel/domains/asset_market/services \
             src/gmgn_twitter_intel/domains/asset_market/runtime \
             src/gmgn_twitter_intel/app/runtime/app.py \
             tests/unit/test_anchor_price_observation.py \
             tests/unit/test_token_target_stage_builder.py \
             tests/unit/test_token_target_posts_service.py \
             tests/integration/test_price_observation_repository.py
  git commit -m "refactor: rename message market observations to anchor prices"
  ```

## Task 3: Remove Price Refresh Workers And Discovery Price Side Effects

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/asset_market/services/asset_market_sync.py`
- Delete: `src/gmgn_twitter_intel/domains/asset_market/runtime/asset_market_sync_worker.py`
- Delete: `src/gmgn_twitter_intel/domains/asset_market/services/market_freshness_demand.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/token_discovery_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/app.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/main.py`
- Delete/replace tests: `tests/unit/test_asset_market_sync.py`, `tests/test_market_freshness_demand.py`
- Modify tests: `tests/integration/test_token_discovery_worker.py`, `tests/integration/test_registry_repository.py`, `tests/integration/test_cli.py`

- [ ] **Step 1: Write failing route-only CEX sync test**

  Replace CEX sync test with:

  ```python
  def test_sync_cex_routes_writes_instruments_and_feeds_without_observations():
      result = sync_cex_routes(
          registry=registry,
          cex_market=cex_market,
          inst_types=("SPOT",),
          observed_at_ms=1_778_000_000_000,
      )

      assert result["cex_tokens_written"] == 1
      assert result["pricefeeds_written"] == 1
      assert "price_observations_written" not in result
      assert price_observations.observations == []
  ```

- [ ] **Step 2: Write failing discovery no-price-side-effect tests**

  In token discovery tests, assert after a symbol and address hit:

  ```python
  assert result["assets_written"] == 1
  assert "pricefeeds_written" not in result
  assert "price_observations_written" not in result
  assert repos.price_observations.observations == []
  assert repos.registry.pricefeeds == []
  assert repos.identity_evidence.rows[0]["raw_payload"]["marketCap"] == "12345"
  ```

- [ ] **Step 3: Run focused tests and verify red**

  ```bash
  uv run pytest tests/unit/test_asset_market_sync.py tests/integration/test_token_discovery_worker.py tests/integration/test_registry_repository.py -q
  ```

  Expected: old sync/worker names and old counters still exist.

- [ ] **Step 4: Rewrite `asset_market_sync.py` to route-only**

  Keep only:

  ```python
  def sync_cex_routes(
      *,
      registry: Any,
      cex_market: Any,
      inst_types: tuple[str, ...] | list[str],
      observed_at_ms: int,
  ) -> dict[str, Any]:
      normalized_inst_types = [str(inst_type).strip().upper() for inst_type in inst_types if str(inst_type).strip()]
      cex_tokens_written = 0
      pricefeeds_written = 0
      affected_lookup_keys: set[str] = set()
      for inst_type in normalized_inst_types:
          for ticker in cex_market.tickers(inst_type=inst_type):
              base_symbol, quote_symbol = _base_quote_from_inst_id(ticker.inst_id)
              if not base_symbol or not quote_symbol:
                  continue
              cex_token = registry.upsert_cex_token(
                  base_symbol=base_symbol,
                  project_id=None,
                  source="okx_cex",
                  observed_at_ms=observed_at_ms,
                  commit=False,
              )
              cex_tokens_written += 1
              registry.upsert_pricefeed(
                  feed_type=f"cex_{ticker.inst_type.lower()}",
                  provider="okx",
                  subject_type="CexToken",
                  subject_id=str(cex_token["cex_token_id"]),
                  native_market_id=ticker.inst_id,
                  base_cex_token_id=str(cex_token["cex_token_id"]),
                  base_symbol=base_symbol,
                  quote_symbol=quote_symbol,
                  observed_at_ms=observed_at_ms,
                  commit=False,
              )
              pricefeeds_written += 1
              affected_lookup_keys.update(_symbol_lookup_keys(base_symbol))
      registry.conn.commit()
      return {
          "inst_types": normalized_inst_types,
          "cex_tokens_written": cex_tokens_written,
          "pricefeeds_written": pricefeeds_written,
          "affected_lookup_keys": sorted(affected_lookup_keys),
      }
  ```

  Delete `sync_dex_prices(...)`, `DEX_PRICE_BATCH_SIZE` from this module if AnchorPriceWorker owns its own batch size, DEX freshness constants, `_needs_address_search(...)`, and imports tied only to DEX refresh.

- [ ] **Step 5: Remove runtime AssetMarketSyncWorker**

  Delete `asset_market_sync_worker.py`. In `app.py`, remove:

  - `asset_market_sync_worker` runtime field/task.
  - construction under `settings.okx_cex_sync_enabled or settings.okx_dex_configured`.
  - start/stop/close/status references for this worker.

  Keep AnchorPriceWorker construction in its own block when either CEX or DEX quote provider is configured.

- [ ] **Step 6: Remove discovery price writes**

  In `_write_dex_candidate(...)`, stop after:

  ```python
  repos.identity_evidence.recompute_current_identity(str(asset["asset_id"]), now_ms=now_ms, commit=False)
  return str(asset["asset_id"])
  ```

  Delete the `upsert_pricefeed(...)` and `insert_observation(...)` block.

  In `_merge_lookup_result(...)`, `_empty_result(...)`, and `_lookup_result(...)`, remove `pricefeeds_written` and `price_observations_written`.

- [ ] **Step 7: Move symbol dominance metadata to identity evidence**

  In `RegistryRepository.find_assets_by_symbol_with_latest_observation(...)`, rename to `find_assets_by_symbol_with_identity_metadata(...)` and replace price observation lateral joins with latest OKX identity evidence:

  ```sql
  LEFT JOIN LATERAL (
    SELECT raw_payload_json, observed_at_ms, provider
    FROM asset_identity_evidence
    WHERE asset_identity_evidence.asset_id = registry_assets.asset_id
      AND asset_identity_evidence.provider = 'okx'
      AND asset_identity_evidence.lookup_mode IN ('symbol_search', 'exact_address')
    ORDER BY observed_at_ms DESC, evidence_id DESC
    LIMIT 1
  ) identity_metadata ON true
  ```

  Extract `market_cap_usd`, `liquidity_usd`, and `holders` from `raw_payload_json` using the same key aliases currently mapped on `DexTokenCandidate`.

  Update `DeterministicTokenResolver` to call the renamed method.

- [ ] **Step 8: Delete DEX refresh selector and freshness demand**

  Remove `RegistryRepository.chain_assets_needing_radar_price_refresh(...)`, delete `market_freshness_demand.py`, delete `tests/test_market_freshness_demand.py`, and replace integration tests with identity metadata dominance tests.

- [ ] **Step 9: Update CLI sync command**

  In `cli/main.py`, replace `sync_cex_universe(...)` import/call with `sync_cex_routes(...)`. Remove any output or tests expecting `price_observations_written`.

- [ ] **Step 10: Run focused tests**

  ```bash
  uv run pytest tests/unit/test_asset_market_sync.py tests/integration/test_token_discovery_worker.py tests/integration/test_registry_repository.py tests/integration/test_cli.py -q
  ```

  Expected: pass; no DEX refresh worker/function imports remain.

- [ ] **Step 11: Commit**

  ```bash
  git add -A src/gmgn_twitter_intel/domains/asset_market \
             src/gmgn_twitter_intel/domains/token_intel/services/deterministic_token_resolver.py \
             src/gmgn_twitter_intel/app/runtime/app.py \
             src/gmgn_twitter_intel/app/surfaces/cli/main.py \
             tests/unit/test_asset_market_sync.py \
             tests/integration/test_token_discovery_worker.py \
             tests/integration/test_registry_repository.py \
             tests/integration/test_cli.py
  git add -u tests/test_market_freshness_demand.py
  git commit -m "refactor: remove token radar price refresh workers"
  ```

## Task 4: Add LivePriceGateway Without DB Writes

**Files:**
- Delete: `src/gmgn_twitter_intel/domains/asset_market/runtime/dex_market_stream_worker.py`
- Create: `src/gmgn_twitter_intel/domains/asset_market/runtime/live_price_gateway.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/app.py`
- Replace tests: `tests/test_asset_market_stream_worker.py` -> `tests/test_live_price_gateway.py`

- [ ] **Step 1: Write failing live gateway test**

  Create `tests/test_live_price_gateway.py`:

  ```python
  async def test_live_price_gateway_publishes_update_without_writing_observation():
      published = []
      gateway = LivePriceGateway(
          stream_provider=stream_provider,
          cex_market=None,
          repository_session=lambda: session,
          projection_version="token-radar-v12-anchor-live-hard-cut",
          subscription_limit=10,
          hot_target_ttl_seconds=60,
          cex_poll_interval_seconds=30,
          reconnect_delay_seconds=0.1,
          on_live_market_update=published.append,
      )

      result = await gateway.run_once(now_ms=1_778_000_000_000)

      assert result["updates_received"] == 1
      assert result["observations_written"] == 0
      assert session.price_observations.calls == []
      assert session.current_market_calls == []
      assert published == [
          {
              "type": "live_market_update",
              "target_type": "Asset",
              "target_id": "asset:solana:token:abc",
              "provider": "okx_dex_ws_price_info",
              "observed_at_ms": 1_778_000_000_500,
              "live_market": {
                  "status": "live",
                  "price_usd": 0.42,
                  "price_quote": None,
                  "quote_symbol": "USD",
                  "price_basis": "usd",
                  "market_cap_usd": None,
                  "liquidity_usd": None,
                  "holders": None,
                  "volume_24h_usd": None,
                  "observed_at_ms": 1_778_000_000_500,
                  "received_at_ms": 1_778_000_000_000,
                  "age_ms": 0,
                  "provider": "okx_dex_ws_price_info",
              },
          }
      ]
      assert gateway.snapshot(target_type="Asset", target_id="asset:solana:token:abc", now_ms=1_778_000_001_500)["status"] == "live"
  ```

- [ ] **Step 2: Run test and verify red**

  ```bash
  uv run pytest tests/test_live_price_gateway.py -q
  ```

  Expected: module missing.

- [ ] **Step 3: Implement `LiveMarketCache`**

  Add:

  ```python
  @dataclass(frozen=True, slots=True)
  class LiveMarketSnapshot:
      target_type: str
      target_id: str
      status: str
      price_usd: float | None
      price_quote: float | None
      quote_symbol: str | None
      price_basis: str
      market_cap_usd: float | None
      liquidity_usd: float | None
      holders: int | None
      volume_24h_usd: float | None
      observed_at_ms: int | None
      received_at_ms: int | None
      provider: str | None
  ```

  `to_payload(now_ms)` returns the exact `live_market` dict used by API/WS and computes `age_ms`.

- [ ] **Step 4: Implement `LivePriceGateway.run_once(...)`**

  Runtime behavior:

  - Read hot targets from `repos.registry.active_live_market_targets(...)`.
  - Stream DEX targets through existing `stream_provider.stream_price_info(...)`.
  - Poll CEX targets through `cex_market.ticker(inst_id=...)` when `cex_market` is configured.
  - Update cache.
  - Publish `type="live_market_update"`.
  - Never call `repos.registry.upsert_pricefeed(...)`, `repos.price_observations.insert_observation(...)`, `repos.conn.commit()`, or `repos.current_market`.

- [ ] **Step 5: Replace registry hot target selector**

  Replace `active_dex_market_stream_targets(...)` with `active_live_market_targets(...)`.

  Required row shape:

  ```python
  {
      "target_type": "Asset" | "CexToken",
      "target_id": "asset:solana:token:abc",
      "chain_id": "solana",
      "address": "abc",
      "native_market_id": "BTC-USDT",
      "quote_symbol": "USDT",
      "provider": "okx",
  }
  ```

  Assets come from `token_radar_rows` joined to `registry_assets`. CEX tokens come from `token_radar_rows` joined to preferred `price_feeds`.

- [ ] **Step 6: Wire app runtime**

  Replace `dex_market_stream_worker` fields with `live_price_gateway`. Use:

  ```python
  runtime.live_price_gateway = LivePriceGateway(
      stream_provider=providers.asset_market.stream_dex_market,
      cex_market=providers.asset_market.message_cex_market,
      repository_session=lambda: repository_session(db_pool),
      projection_version=TOKEN_RADAR_PROJECTION_VERSION,
      subscription_limit=settings.okx_dex_ws_subscription_limit,
      hot_target_ttl_seconds=settings.okx_dex_ws_hot_target_ttl_seconds,
      reconnect_delay_seconds=settings.okx_dex_ws_reconnect_delay_seconds,
      on_live_market_update=hub.publish,
  )
  ```

  Start/stop/close the gateway using the old stream worker lifecycle slots renamed to `live_price_gateway_task`.

- [ ] **Step 7: Run focused tests**

  ```bash
  uv run pytest tests/test_live_price_gateway.py tests/integration/test_registry_repository.py -q
  ```

  Expected: pass; `tests/test_asset_market_stream_worker.py` no longer exists.

- [ ] **Step 8: Commit**

  ```bash
  git add -A src/gmgn_twitter_intel/domains/asset_market/runtime \
             src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py \
             src/gmgn_twitter_intel/app/runtime/app.py \
             tests/test_live_price_gateway.py
  git add -u tests/test_asset_market_stream_worker.py
  git commit -m "feat: add live price gateway without persistence"
  ```

## Task 5: Remove DB Current Market From Token Radar Projection And Scoring

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/_constants.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py`
- Modify tests: `tests/unit/test_token_radar_projection.py`, `tests/golden/test_token_radar_corpus.py`

- [ ] **Step 1: Write failing projection hard-cut tests**

  In `tests/unit/test_token_radar_projection.py`:

  ```python
  def test_token_radar_projection_uses_anchor_live_hard_cut_contract():
      assert TOKEN_RADAR_PROJECTION_VERSION == "token-radar-v12-anchor-live-hard-cut"
      assert TOKEN_RADAR_SOURCE_TABLE == "token_intent_resolutions+asset_identity_current+anchor_price"
      assert PROJECTION_VERSION == TOKEN_RADAR_PROJECTION_VERSION
  ```

  Replace current-market hydration tests with:

  ```python
  def test_projection_does_not_call_current_market_repository():
      repos = type("Repos", (), {"conn": object(), "token_radar": token_radar})()

      TokenRadarProjection(repos=repos).rebuild(window="1h", scope="all", now_ms=1_778_000_000_000)

      assert not hasattr(repos, "current_market")
  ```

  Add anchor market assertion:

  ```python
  market = _market([source_row_with_event_anchor_price], resolved=True, now_ms=1_778_000_060_000)
  assert market["market_status"] == "anchored"
  assert market["anchor_price_usd"] == 0.42
  assert market["price_at_social_start"] == 0.42
  assert market["price_change_since_social_pct"] is None
  assert market["event_price_readiness"]["status"] == "ready"
  ```

- [ ] **Step 2: Run focused projection tests and verify red**

  ```bash
  uv run pytest tests/unit/test_token_radar_projection.py tests/golden/test_token_radar_corpus.py -q
  ```

  Expected: old version/source table and current-market calls fail.

- [ ] **Step 3: Update constants**

  Set:

  ```python
  TOKEN_RADAR_PROJECTION_VERSION = "token-radar-v12-anchor-live-hard-cut"
  TOKEN_RADAR_SOURCE_TABLE = "token_intent_resolutions+asset_identity_current+anchor_price"
  ```

- [ ] **Step 4: Remove current-market hydration**

  In `TokenRadarProjection.rebuild(...)`, delete:

  ```python
  source_rows = self._hydrate_current_market(
      source_rows,
      now_ms=computed_at_ms,
      score_since_ms=score_since_ms,
  )
  ```

  Delete `_hydrate_current_market(...)`, `_row_with_current_market(...)`, `_market_field(...)`, `_missing_current_market_fields(...)`, and `MARKET_FRESH_MS`.

- [ ] **Step 5: Build market facts from anchor baselines**

  Rewrite `_market(...)` so resolved rows use `event_price_*` and `first_price_*` columns:

  ```python
  anchor_price_usd = social_start.get("event_price_usd")
  anchor_price_quote = social_start.get("event_price_quote")
  anchor_observed_at_ms = _int_or_none(social_start.get("event_price_observed_at_ms"))
  status = "anchored" if anchor_price_usd is not None or anchor_price_quote is not None else "missing"
  ```

  Return fields:

  ```python
  {
      "market_status": status,
      "market_observation_status": "ready" if status == "anchored" else "missing_anchor",
      "price_change_status": "live_not_persisted" if status == "anchored" else "missing_anchor",
      "provider": social_start.get("event_price_provider"),
      "pricefeed_id": social_start.get("pricefeed_id"),
      "native_market_id": social_start.get("native_market_id"),
      "anchor_price_usd": anchor_price_usd,
      "anchor_price_quote": anchor_price_quote,
      "anchor_quote_symbol": social_start.get("event_price_quote_symbol"),
      "anchor_price_basis": social_start.get("event_price_basis"),
      "anchor_observed_at_ms": anchor_observed_at_ms,
      "anchor_lag_ms": max(0, anchor_observed_at_ms - int(social_start["received_at_ms"])) if anchor_observed_at_ms else None,
      "price_at_social_start": anchor_price_usd or anchor_price_quote,
      "price_at_reference": None,
      "price_change_since_social_pct": None,
      "price_change_before_social_pct": None,
      "live_price_persisted": False,
  }
  ```

- [ ] **Step 6: Remove market freshness gate**

  In `factor_snapshot.py`, delete `_market_freshness_block_reason(...)` and this block:

  ```python
  market_status = market.get("market_status") or market.get("market_observation_status")
  if freshness_reason := _market_freshness_block_reason(market_status):
      blocked_reasons.append(freshness_reason)
      discard_cap_reasons.append(freshness_reason)
  ```

  Keep DEX floor checks only when metadata values are present. Missing metadata adds `market_metadata_missing` to `risk_reasons`, not `blocked_reasons`.

- [ ] **Step 7: Make timing display-only**

  In `factor_snapshot.py`, set timing score contribution to zero when live DB price is absent:

  ```python
  timing_family["score"] = 0
  timing_family["data_health"] = "anchor_only"
  timing_family["facts"]["price_change_status"] = "live_not_persisted"
  ```

  In `_composite(...)`, exclude `timing_response` from rank weight by using only attention/diffusion/semantic families for `raw_alpha_score`.

- [ ] **Step 8: Run focused tests**

  ```bash
  uv run pytest tests/unit/test_token_radar_projection.py tests/golden/test_token_radar_corpus.py -q
  ```

  Expected: pass; no projection test requires `repos.current_market`.

- [ ] **Step 9: Commit**

  ```bash
  git add src/gmgn_twitter_intel/domains/token_intel/_constants.py \
          src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py \
          src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py \
          src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py \
          tests/unit/test_token_radar_projection.py \
          tests/golden/test_token_radar_corpus.py
  git commit -m "refactor: project token radar from anchor prices"
  ```

## Task 6: Hard-Cut HTTP, WebSocket, CLI, And Pulse Read Models

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/http.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/ws.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/main.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/app.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py`
- Modify tests: `tests/unit/test_asset_flow_service.py`, `tests/integration/test_api_http.py`, `tests/integration/test_api_websocket.py`, `tests/integration/test_cli.py`, `tests/unit/test_signal_pulse_service.py`

- [ ] **Step 1: Write failing API contract tests**

  In HTTP tests:

  ```python
  def test_api_token_radar_returns_anchor_price_not_current_market(client):
      data = client.get("/api/token-radar", headers=auth).json()["data"]
      row = data["targets"][0]

      assert "anchor_price" in row
      assert "current_market" not in row
      assert data["projection"]["anchor_coverage"]["status"] in {"ready", "partial", "missing"}
  ```

  Remove `/api/current-market` tests and add:

  ```python
  def test_api_live_market_reads_runtime_cache(client):
      response = client.get(
          "/api/live-market",
          params={"target_type": "Asset", "target_id": "asset:solana:token:abc"},
          headers=auth,
      )
      assert response.json()["data"]["status"] in {"live", "stale", "missing", "unsupported"}
  ```

- [ ] **Step 2: Write failing WS contract tests**

  Replace websocket market tests:

  ```python
  async def test_websocket_routes_live_market_update_for_explicit_market_target_subscription():
      await hub.publish({
          "type": "live_market_update",
          "target_type": "Asset",
          "target_id": "asset:solana:token:abc",
          "live_market": {"status": "live", "price_usd": 0.42},
      })
      assert received["type"] == "live_market_update"
  ```

  Add assertion that `market_update` is ignored because it is no longer a supported payload type.

- [ ] **Step 3: Run focused tests and verify red**

  ```bash
  uv run pytest tests/unit/test_asset_flow_service.py tests/integration/test_api_http.py tests/integration/test_api_websocket.py tests/integration/test_cli.py tests/unit/test_signal_pulse_service.py -q
  ```

- [ ] **Step 4: Rewrite `AssetFlowService` public row**

  Constructor:

  ```python
  class AssetFlowService:
      def __init__(self, *, token_radar: Any) -> None:
          self.token_radar = token_radar
  ```

  `_public_row(...)` returns:

  ```python
  {
      "_lane": row.get("lane"),
      "intent": row.get("intent_json") or {},
      "target": _target_from_snapshot(factor_snapshot),
      "attention": _attention_from_snapshot(factor_snapshot),
      "anchor_price": _anchor_price_from_snapshot(factor_snapshot),
      "live_market": _missing_live_market(factor_snapshot),
      "resolution": row.get("resolution_json") or {},
      "score": _composite_from_snapshot(factor_snapshot),
      "factor_snapshot": factor_snapshot,
      "data_health": row.get("data_health_json") or {},
      "source_event_ids": row.get("source_event_ids_json") or [],
  }
  ```

  `projection` uses:

  ```python
  "anchor_coverage": _anchor_coverage([*targets, *attention])
  ```

  Delete `_subjects_from_rows(...)`, `_missing_current_market(...)`, and `_market_hydration(...)`.

- [ ] **Step 5: Update API routes**

  In `/token-radar`, call `AssetFlowService(token_radar=repos.token_radar)`.

  Delete `/current-market`.

  Add:

  ```python
  @router.get("/live-market")
  async def live_market(
      request: Request,
      target_type: Annotated[str, Query()] = "",
      target_id: Annotated[str, Query()] = "",
  ) -> JSONResponse:
      runtime = _authenticated_runtime(request)
      parsed_target_type = _target_type(target_type)
      if not parsed_target_type or not target_id:
          raise ApiBadRequest("target_required", field="target_id")
      gateway = runtime.live_price_gateway
      if gateway is None:
          snapshot = {"target_type": parsed_target_type, "target_id": target_id, "status": "unsupported"}
      else:
          snapshot = gateway.snapshot(target_type=parsed_target_type, target_id=target_id, now_ms=_now_ms())
      return _json({"ok": True, "data": snapshot})
  ```

- [ ] **Step 6: Update WebSocket routing**

  In `_payload_matches_subscription(...)`, replace the market branch with:

  ```python
  if payload.get("type") == "live_market_update":
      target = _market_target(payload)
      return bool(target and target in client.market_targets)
  if payload.get("type") == "market_update":
      return False
  ```

- [ ] **Step 7: Remove CLI current-market commands**

  Remove parser setup for:

  - `current-market`
  - `ops backfill-current-market-field-facts`

  Delete command handlers and update CLI integration snapshots.

- [ ] **Step 8: Update Pulse read model**

  In `_row_market_facts(...)`, read:

  ```python
  anchor = _dict(row.get("anchor_price"))
  for key in ("price_usd", "market_cap_usd", "liquidity_usd", "holders", "volume_24h_usd"):
      if key in anchor and anchor.get(key) is not None:
          facts[key] = anchor.get(key)
  ```

  Do not inspect `row.current_market`.

- [ ] **Step 9: Run focused tests**

  ```bash
  uv run pytest tests/unit/test_asset_flow_service.py tests/integration/test_api_http.py tests/integration/test_api_websocket.py tests/integration/test_cli.py tests/unit/test_signal_pulse_service.py -q
  ```

- [ ] **Step 10: Commit**

  ```bash
  git add src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py \
          src/gmgn_twitter_intel/app/surfaces/api/http.py \
          src/gmgn_twitter_intel/app/surfaces/api/ws.py \
          src/gmgn_twitter_intel/app/surfaces/cli/main.py \
          src/gmgn_twitter_intel/app/runtime/app.py \
          src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py \
          tests/unit/test_asset_flow_service.py \
          tests/integration/test_api_http.py \
          tests/integration/test_api_websocket.py \
          tests/integration/test_cli.py \
          tests/unit/test_signal_pulse_service.py
  git commit -m "refactor: expose anchor and live market contracts"
  ```

## Task 7: Frontend Anchor / Live Contract Hard Cut

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/api/useIntelSocket.ts`
- Move: `web/src/features/live/marketUpdatePatch.ts` -> `web/src/features/live/liveMarketUpdatePatch.ts`
- Move: `web/src/features/live/marketUpdatePatch.test.ts` -> `web/src/features/live/liveMarketUpdatePatch.test.ts`
- Modify: `web/src/lib/tokenRadar.ts`
- Modify: `web/src/lib/tokenRadar.test.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`
- Modify: `web/src/api/openapi.ts`

- [ ] **Step 1: Write failing frontend contract tests**

  In `web/src/lib/tokenRadar.test.ts`:

  ```ts
  it("requires anchor_price and does not require current_market", () => {
    const row = assetFlowRowFixture();
    delete (row as Partial<AssetFlowRow>).current_market;
    row.anchor_price = {
      status: "ready",
      price_usd: 0.42,
      price_quote: null,
      quote_symbol: "USD",
      price_basis: "usd",
      provider: "okx",
      anchor_observed_at_ms: 1778000000500,
      event_received_at_ms: 1778000000000,
      anchor_lag_ms: 500,
    };

    expect(tokenRadarRowToTokenItem(row, "1h", "all").market.price).toBe(0.42);
  });
  ```

  In live patch tests:

  ```ts
  expect(patched.targets[0].live_market?.price_usd).toBe(0.5);
  expect(patched.targets[0].current_market).toBeUndefined();
  ```

- [ ] **Step 2: Run focused frontend tests and verify red**

  ```bash
  npm --prefix web test -- --run web/src/lib/tokenRadar.test.ts web/src/features/live/liveMarketUpdatePatch.test.ts
  ```

- [ ] **Step 3: Update TypeScript API types**

  Delete:

  ```ts
  export type CurrentMarketSnapshot = {
    target_type?: string | null;
    target_id?: string | null;
    market_status: string;
    fields: Record<string, MarketFieldFact>;
  };
  export type MarketUpdatePayload = {
    type: "market_update";
    target_type: string;
    target_id: string;
    provider?: string | null;
    observed_at_ms?: number | null;
    current_market: CurrentMarketSnapshot;
  };
  current_market: CurrentMarketSnapshot;
  ```

  Add:

  ```ts
  export type AnchorPriceSnapshot = {
    status: "ready" | "missing" | "pending" | "error" | string;
    price_usd?: number | null;
    price_quote?: number | null;
    quote_symbol?: string | null;
    price_basis?: string | null;
    provider?: string | null;
    anchor_observed_at_ms?: number | null;
    event_received_at_ms?: number | null;
    anchor_lag_ms?: number | null;
  };

  export type LiveMarketSnapshot = {
    status: "live" | "stale" | "missing" | "unsupported" | string;
    price_usd?: number | null;
    price_quote?: number | null;
    quote_symbol?: string | null;
    price_basis?: string | null;
    provider?: string | null;
    observed_at_ms?: number | null;
    received_at_ms?: number | null;
    age_ms?: number | null;
  };

  export type LiveMarketUpdatePayload = {
    type: "live_market_update";
    target_type: string;
    target_id: string;
    provider?: string | null;
    observed_at_ms?: number | null;
    live_market: LiveMarketSnapshot;
  };
  ```

  `AssetFlowRow` has:

  ```ts
  anchor_price: AnchorPriceSnapshot;
  live_market?: LiveMarketSnapshot | null;
  ```

- [ ] **Step 4: Update socket hook**

  Rename state:

  ```ts
  const [liveMarketUpdates, setLiveMarketUpdates] = useState<LiveMarketUpdatePayload[]>([]);
  ```

  Replace payload branch:

  ```ts
  if (payload.type === "live_market_update") {
    setLiveMarketUpdates((current) => [payload as LiveMarketUpdatePayload, ...current].slice(0, 100));
  }
  ```

  Return `liveMarketUpdates`, not `marketUpdates`.

- [ ] **Step 5: Update live patcher**

  Rename function to:

  ```ts
  export function patchTokenRadarLiveMarketUpdate(queryClient: QueryClient, update: LiveMarketUpdatePayload)
  ```

  Row patch:

  ```ts
  return { ...row, live_market: update.live_market };
  ```

- [ ] **Step 6: Update token radar parser**

  Delete `requiredCurrentMarket(...)`.

  Add:

  ```ts
  function requiredAnchorPrice(row: AssetFlowRow): AnchorPriceSnapshot {
    const anchor = row.anchor_price;
    if (!anchor || typeof anchor !== "object") {
      throw new Error("token_radar_contract:anchor_price");
    }
    return anchor;
  }
  ```

  Compute:

  ```ts
  const anchor = requiredAnchorPrice(row);
  const live = row.live_market ?? null;
  const displayPrice = optionalNullableNumber(live?.price_usd) ?? optionalNullableNumber(anchor.price_usd);
  const liveDeltaPct =
    optionalNullableNumber(live?.price_usd) != null && optionalNullableNumber(anchor.price_usd) != null
      ? ((live.price_usd! - anchor.price_usd!) / anchor.price_usd!) * 100
      : null;
  ```

  Use `displayPrice` for `market.price`; add `anchor_price`, `live_price`, and `live_change_since_anchor_pct` to `TokenMarketBlock`.

- [ ] **Step 7: Update App wiring**

  Replace all `marketUpdates` usage with `liveMarketUpdates` and call `patchTokenRadarLiveMarketUpdate(...)`. Remove helpers named `currentMarketFromPriceFixture`.

- [ ] **Step 8: Update OpenAPI artifact**

  Remove `"/api/current-market"` and `current_market_api_current_market_get`. Add `"/api/live-market"` shape if `openapi.ts` is manually maintained; otherwise regenerate with the repo's existing command and commit the generated result.

- [ ] **Step 9: Run frontend tests**

  ```bash
  npm --prefix web test -- --run
  npm --prefix web run build
  ```

  Expected: pass; no TypeScript reference to `MarketUpdatePayload` or `current_market` remains except historical docs/tests removed in later tasks.

- [ ] **Step 10: Commit**

  ```bash
  git add -A web/src/api/types.ts \
             web/src/api/useIntelSocket.ts \
             web/src/features/live \
             web/src/lib/tokenRadar.ts \
             web/src/lib/tokenRadar.test.ts \
             web/src/App.tsx \
             web/src/App.test.tsx \
             web/src/api/openapi.ts
  git commit -m "refactor: switch frontend to anchor and live market"
  ```

## Task 8: Documentation And Contract Sweep

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/FRONTEND.md`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`
- Modify: `docs/generated/cli-help.md`
- Modify or delete stale active docs only if they describe code that this plan removes.

- [ ] **Step 1: Update architecture docs**

  Replace wording that says Token Radar reads current-market snapshots with:

  ```text
  Token Radar persists message-bound anchor prices through AnchorPriceWorker and token_market_price_baselines.
  Live price is served from LivePriceGateway memory via /api/live-market and live_market_update WebSocket payloads.
  Postgres is not used as a ticker cache.
  ```

- [ ] **Step 2: Update contracts**

  `/api/token-radar` row contract includes `anchor_price` and optional `live_market`; it does not include `current_market`.

  `/ws` contract lists `live_market_update`; it does not list `market_update`.

  `/api/live-market` replaces `/api/current-market`.

- [ ] **Step 3: Regenerate CLI help**

  ```bash
  uv run gmgn-twitter-intel --help > docs/generated/cli-help.md
  ```

  Verify removed commands:

  ```bash
  rg -n "current-market|backfill-current-market-field-facts" docs/generated/cli-help.md
  ```

  Expected: no matches.

- [ ] **Step 4: Run docs grep**

  ```bash
  rg -n "current_market|current-market|market_update|message_quote|AssetMarketSyncWorker|DexMarketStreamWorker|backfill-current-market-field-facts" docs src web tests
  ```

  Expected matches are limited to migration history and this plan/spec. Production code and live contracts have no matches for old public names.

- [ ] **Step 5: Commit**

  ```bash
  git add docs/ARCHITECTURE.md \
          docs/CONTRACTS.md \
          docs/FRONTEND.md \
          src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md \
          docs/generated/cli-help.md
  git commit -m "docs: document anchor live market boundary"
  ```

## Task 9: Full Verification And Cleanup

**Files:**
- Create: `docs/superpowers/plans/active/2026-05-11-token-radar-anchor-live-hard-cut-verification-cn.md`
- Modify: `docs/TECH_DEBT.md` only if verification finds non-trivial follow-up.

- [ ] **Step 1: Run stale-symbol grep**

  ```bash
  rg -n "CurrentMarketRepository|CurrentMarketService|current_market_field_facts|backfill_current_market_field_facts|backfill-current-market-field-facts|DexMarketStreamWorker|AssetMarketSyncWorker|market_update|MarketUpdatePayload|message_quote|sync_dex_prices|chain_assets_needing_radar_price_refresh|market_freshness_demand" src tests web docs
  ```

  Expected: only migration history, completed/active plan/spec references, and intentional historical notes. No production runtime or frontend contract references.

- [ ] **Step 2: Run backend checks**

  ```bash
  uv run ruff check .
  uv run pytest -q
  ```

  Expected: pass.

- [ ] **Step 3: Run frontend checks**

  ```bash
  npm --prefix web test -- --run
  npm --prefix web run build
  ```

  Expected: pass.

- [ ] **Step 4: Run full project gate**

  ```bash
  make check-all
  ```

  Expected: pass. Save full output into the verification artifact.

- [ ] **Step 5: Manual smoke test**

  Start local app using the existing setup command from `docs/SETUP.md`. Verify:

  - `/api/token-radar` row contains `anchor_price`.
  - `/api/token-radar` row does not contain `current_market`.
  - `/api/live-market?target_type=Asset&target_id=asset:solana:token:abc` returns `live`, `stale`, `missing`, or `unsupported` after replacing the sample id with a target from the local Token Radar response.
  - WebSocket sends `live_market_update` to subscribed market target.
  - `price_observations` row count does not change after live WebSocket updates.

- [ ] **Step 6: Write verification artifact**

  Include:

  - commands and full outputs;
  - coverage;
  - skipped tests;
  - E2E golden path;
  - remaining risks.

- [ ] **Step 7: Final commit**

  ```bash
  git add docs/superpowers/plans/active/2026-05-11-token-radar-anchor-live-hard-cut-verification-cn.md docs/TECH_DEBT.md
  git commit -m "test: verify token radar anchor live hard cut"
  ```

## Acceptance Criteria Mapping

- AC1: `tests/integration/test_asset_ingest_flow.py` continues asserting GMGN payload `mc/p` does not write current-market or anchor price during ingest.
- AC2: `tests/unit/test_anchor_price_observation.py` asserts one `message_anchor` per current `source_resolution_id`.
- AC3: anchor worker idempotency test plus partial unique index `uq_price_observations_message_anchor_resolution`.
- AC4: `tests/integration/test_token_discovery_worker.py` asserts no pricefeed or price observation writes.
- AC5: `tests/unit/test_asset_market_sync.py` asserts CEX route sync has no observation counter/write.
- AC6: `tests/test_live_price_gateway.py` asserts WS live update publishes and `price_observations` remains untouched.
- AC7: `tests/unit/test_asset_flow_service.py` and API tests assert `/api/token-radar` has `anchor_price` and no `current_market`.
- AC8: `web/src/features/live/liveMarketUpdatePatch.test.ts` asserts frontend computes/patches live state without projection rebuild.
- AC9: factor settlement tests are updated to report missing exit price unless an explicit settlement observation exists.
- AC10: stale grep plus tests fail if live gateway or deleted workers call `insert_observation(...)`.

## Rollout Order

1. Apply Alembic migration `20260511_0029`.
2. Deploy backend hard cut and frontend hard cut together. There is no compatibility window.
3. Restart runtime so old workers are gone and LivePriceGateway owns live updates.
4. Run smoke test and confirm live updates do not mutate `price_observations`.

## Rollback

This is a destructive hard cut. Rollback is not data-complete because migration deletes non-anchor refresh observations and drops `current_market_field_facts`.

Operational rollback procedure:

1. Revert code deployment to the previous release.
2. Run Alembic downgrade only to recreate `current_market_field_facts` shape.
3. Run the old backfill command only if restored from a pre-cut branch.
4. Accept that deleted refresh observations are not restored unless recovered from database backup.

Because the user explicitly requested no compatibility code, this plan does not include dual contracts or two-phase rollout.

## Verification Artifact

Create `docs/superpowers/plans/active/2026-05-11-token-radar-anchor-live-hard-cut-verification-cn.md` before declaring completion. It must include the full `make check-all` output plus manual smoke-test evidence.
