# Token Radar Market Boundary Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split Token Radar scoring from live/current market data so `$TROLL`-style fresh-price/stale-market-cap bugs cannot reappear.

**Architecture:** Keep tweet extraction provider-free and keep discovery/search asynchronous. Add an `asset_market` field-aware current market read model derived from existing `price_observations`; Token Radar projection consumes that read model for scoring context, while API/frontend consume it for current market display. This is a hard cut: no `factor_snapshot.market_quality.facts` fallback for live price, and no price-only provider response may refresh market cap/liquidity/holders.

**Tech Stack:** Python 3.13, PostgreSQL, psycopg, pytest, FastAPI, React/TypeScript, TanStack Query, Vitest.

---

**Status**: Implemented, pending human review
**Date**: 2026-05-11
**Owning spec**: `docs/superpowers/specs/active/2026-05-11-token-radar-market-boundary-hard-cut-cn.md`
**Worktree**: `.worktrees/token-radar-market-boundary-hard-cut/`
**Branch**: `codex/token-radar-market-boundary-hard-cut`

## Architecture Review

The spec matches production-grade token intelligence practice:

- **Extraction is local and deterministic.** Tweets should be parsed into CA/cashtag/payload evidence without network calls. Provider outages must not block ingest.
- **Resolution is registry-backed and fail-closed.** Symbol-only mentions can resolve from CEX registry or retained DEX candidates, but unresolved or stale evidence should produce `NIL` / `AMBIGUOUS`, not guessed identity.
- **Discovery is asynchronous enrichment.** OKX DEX search belongs in discovery/reprocess, never in the synchronous tweet path.
- **Market data is field-aware.** Industrial market-data systems do not treat one tick timestamp as proof that every field in a record refreshed. Price, market cap, liquidity, holders, OI, and volume need separate source capability and freshness.
- **Consumers get purpose-built read models.** Radar scoring needs immutable scoring context; frontend needs current market state; Pulse/notifications need audited gates. One JSON object cannot safely serve all three.

The plan deliberately keeps KISS:

- No new generic market-data platform.
- No new provider in this implementation.
- No synchronous OKX/CEX search in ingest.
- No WebSocket market fanout in v1; frontend gets near-realtime via current-market hydration on existing Token Radar polling. A WS event can be added later if a provider-backed stream exists.
- No compatibility fallback such as `current_market or factor_snapshot.market_quality.facts`.

## Pre-flight

- [ ] Create the worktree from the repository root:
  ```bash
  git worktree add .worktrees/token-radar-market-boundary-hard-cut -b codex/token-radar-market-boundary-hard-cut main
  ```
- [ ] Copy this plan and the owning spec into the worktree if they were authored in the main checkout.
- [ ] In the worktree, verify location and branch:
  ```bash
  git worktree list
  git status --short
  git branch --show-current
  ```
  Expected branch: `codex/token-radar-market-boundary-hard-cut`.
- [ ] Confirm the owning spec status is `Approved for implementation planning`.
- [ ] Record baseline:
  ```bash
  uv run ruff check src tests
  uv run pytest -q
  uv run python -m compileall src tests
  npm test -- --run
  npm run build
  ```

Baseline result before implementation:

- `uv run ruff check src tests`: passed.
- `uv run python -m compileall src tests`: passed.
- `uv run pytest -q`: 448 passed, 146 skipped.
- `npm run build` in `web/`: passed after `npm install`.
- `npm test -- --run` in `web/`: failed one existing frontend test:
  `src/App.test.tsx > App Token Radar social heat cockpit > renders radar rows with mock-aligned semantic fields and selected state`
  because Testing Library could not find role `button` with name `select token $UPEG`.

## Implementation Result

Executed in worktree `.worktrees/token-radar-market-boundary-hard-cut/` on branch
`codex/token-radar-market-boundary-hard-cut`.

Fresh verification after implementation:

- `uv run ruff check src tests`: passed.
- `uv run python -m compileall src tests`: passed.
- `uv run pytest -q`: 454 passed, 152 skipped.
- `npm run build` in `web/`: passed.
- `npm run typecheck -- --pretty false` in `web/`: passed.
- `npm test -- --run` in `web/`: 16 files passed, 90 tests passed.
- `npm test -- --run --fileParallelism=true --pool=forks --isolate=true --reporter=dot`
  in `web/`: 16 files passed, 90 tests passed.

Implementation note: `market_field_facts.py` lives at
`src/parallax/domains/asset_market/market_field_facts.py`, not under
`services/`, so repositories can consume pure field policy without violating the
repository/query architecture guard.

## File Structure

### New Python files

- `src/parallax/domains/asset_market/market_field_facts.py`
  - Owns field capability policy, field freshness calculation, aggregate market status, and pure `MarketFieldFact` / `CurrentMarketSnapshot` assembly helpers.
  - No SQL, no provider calls, no imports from `token_intel`.
- `src/parallax/domains/asset_market/repositories/current_market_repository.py`
  - Owns SQL for field-aware current market snapshots derived from `price_observations`.
  - Reads latest capable observation per field; excludes `okx_dex_price` from market cap/liquidity/holders by policy.
- `src/parallax/domains/asset_market/read_models/__init__.py`
  - Package marker for asset-market read models.
- `src/parallax/domains/asset_market/read_models/current_market_service.py`
  - Small read service wrapper used by API/CLI; delegates SQL to `CurrentMarketRepository`.

### Modified Python files

- `src/parallax/domains/asset_market/interfaces.py`
  - Export `CurrentMarketRepository` and `CurrentMarketService`.
- `src/parallax/app/runtime/repository_session.py`
  - Add `current_market: CurrentMarketRepository` to `RepositorySession`.
- `src/parallax/domains/asset_market/services/asset_market_sync.py`
  - Stop copying stale market metadata into `okx_dex_price` observations.
- `src/parallax/domains/asset_market/services/message_market_observation.py`
  - Stop copying stale market metadata into DEX `message_quote` observations.
- `src/parallax/domains/asset_market/repositories/registry_repository.py`
  - Make `find_assets_by_symbol_with_latest_observation()` return field-aware market fields using provider capability filters.
  - Add `market_cap_status`, `liquidity_status`, `holders_status`, and field observed-at columns for resolver use.
- `src/parallax/domains/token_intel/services/deterministic_token_resolver.py`
  - Require resolver dominance fields to have current field provenance; stale/missing provider fields cannot create `MARKET_DOMINANT_CHAIN_ASSET`.
- `src/parallax/domains/token_intel/_constants.py`
  - Bump `TOKEN_RADAR_PROJECTION_VERSION` to `token-radar-v10-current-market`.
  - Change `TOKEN_RADAR_SOURCE_TABLE` to `token_intent_resolutions+asset_identity_current+current_market`.
- `src/parallax/domains/token_intel/queries/token_radar_source_query.py`
  - Remove current-market latest-row lateral joins from `price_observations`.
  - Keep event-history/message/before/first price joins for timing evidence.
- `src/parallax/domains/token_intel/services/token_radar_projection.py`
  - Hydrate source rows with `repos.current_market.current_for_subjects(subjects, now_ms=now_ms)`.
  - Build market context from field-aware snapshots.
  - Keep projection provider-free.
- `src/parallax/domains/token_intel/scoring/factor_snapshot.py`
  - Keep market-quality facts as scoring provenance, not live price.
  - Add field status/provenance facts needed for gates and audits.
- `src/parallax/domains/token_intel/read_models/asset_flow_service.py`
  - Require a current-market repository/service.
  - Return `current_market` per row.
  - Remove `market` and `price` aliases sourced from factor snapshot.
- `src/parallax/app/surfaces/api/http.py`
  - Construct `AssetFlowService(token_radar=repos.token_radar, current_market=repos.current_market)`.
  - Add `/api/current-market` for direct target reads.
- `src/parallax/app/surfaces/cli/main.py`
  - Construct `AssetFlowService` with `current_market`.
  - Add or extend ops audit output for current-market field facts.
- `src/parallax/app/runtime/app.py`
  - Construct notification `AssetFlowService` with current-market repository.
- `src/parallax/app/runtime/providers_wiring.py`
  - Share one serialized OKX DEX provider across sync/message/discovery to avoid independent client quota races.
- `src/parallax/domains/token_intel/ARCHITECTURE.md`
  - Document `asset_market current market read model -> TokenRadarProjection` boundary.
- `docs/ARCHITECTURE.md`
  - Link `asset_market` current market read model responsibility.

### Modified frontend files

- `web/src/api/types.ts`
  - Add `MarketFieldFact`, `CurrentMarketSnapshot`, and `AssetFlowRow.current_market`.
  - Remove runtime dependency on `AssetFlowRow.price` / `AssetFlowRow.market` for Token Radar.
- `web/src/lib/tokenRadar.ts`
  - Read price/market cap/liquidity/holders/status from `row.current_market`.
  - Keep factor snapshot required for scoring.
- `web/src/lib/tokenRadar.test.ts`
  - Add anti-regression test that a row without `current_market` throws, even if factor snapshot market facts contain price.
- `web/src/components/TokenRadarRow.tsx`
  - Render field-level stale/missing states when market cap differs from price freshness.
- `web/src/components/TokenRadarRow.test.tsx`
  - Assert fresh price + stale market cap renders as partial/stale, not fully fresh.
- `web/src/App.test.tsx`
  - Update fixtures to use `current_market`.

### Tests to add or rewrite

- `tests/test_asset_market_sync.py`
- `tests/test_message_market_observation.py`
- `tests/test_current_market_repository.py`
- `tests/test_registry_repository.py`
- `tests/test_deterministic_token_resolver.py`
- `tests/test_token_radar_projection.py`
- `tests/test_asset_flow_service.py`
- `tests/test_api_http.py`
- `tests/test_api_health.py`
- `tests/test_postgres_audit.py`
- `tests/test_project_structure.py`
- `web/src/lib/tokenRadar.test.ts`
- `web/src/components/TokenRadarRow.test.tsx`
- `web/src/App.test.tsx`

## Task 1: Stop Price-Only Copy-Forward

**Files:**

- Modify: `src/parallax/domains/asset_market/services/asset_market_sync.py:256-271`
- Modify: `src/parallax/domains/asset_market/services/message_market_observation.py:169-187`
- Test: `tests/test_asset_market_sync.py`
- Test: `tests/test_message_market_observation.py`

- [ ] **Step 1: Write failing asset sync regression**

  Update `tests/test_asset_market_sync.py::test_sync_dex_prices_refreshes_active_dex_venues_in_batches` expected observation fields:
  ```python
  assert price_observations.observations[-1]["provider"] == "okx_dex_price"
  assert price_observations.observations[-1]["price_usd"] == 0.00002237
  assert price_observations.observations[-1]["market_cap_usd"] is None
  assert price_observations.observations[-1]["liquidity_usd"] is None
  assert price_observations.observations[-1]["holders"] is None
  ```

- [ ] **Step 2: Add message quote regression**

  Add this assertion to `tests/test_message_market_observation.py::test_message_market_observation_writes_dex_message_quote_per_message`:
  ```python
  for observation in repos.price_observations.observations:
      assert observation["provider"] == "okx_dex_price"
      assert observation["price_usd"] == 1.23
      assert observation["market_cap_usd"] is None
      assert observation["liquidity_usd"] is None
      assert observation["holders"] is None
  ```

- [ ] **Step 3: Run the focused failing tests**

  ```bash
  uv run pytest tests/test_asset_market_sync.py::test_sync_dex_prices_refreshes_active_dex_venues_in_batches tests/test_message_market_observation.py::test_message_market_observation_writes_dex_message_quote_per_message -q
  ```
  Expected: both tests fail because current code copies metadata into `okx_dex_price`.

- [ ] **Step 4: Remove metadata copy-forward in `sync_dex_prices`**

  In `asset_market_sync.py`, change the `okx_dex_price` insert block to:
  ```python
  price_observations.insert_observation(
      provider="okx_dex_price",
      pricefeed_id=str(pricefeed["pricefeed_id"]),
      observed_at_ms=price.observed_at_ms or observed_at_ms,
      subject_type="Asset",
      subject_id=str(asset["asset_id"]),
      price_usd=price.price_usd,
      price_basis="usd",
      market_cap_usd=None,
      liquidity_usd=None,
      volume_24h_usd=None,
      open_interest_usd=None,
      holders=None,
      raw_payload={**price.raw, "payload_hash": _payload_hash(price.raw)},
      commit=False,
  )
  ```

- [ ] **Step 5: Remove metadata copy-forward in `message_market_observation`**

  In `_write_dex_observation`, change the DEX message quote insert to:
  ```python
  repos.price_observations.insert_observation(
      provider="okx_dex_price",
      pricefeed_id=str(pricefeed["pricefeed_id"]),
      observed_at_ms=price.observed_at_ms or now_ms,
      subject_type="Asset",
      subject_id=str(row["target_id"]),
      price_usd=price.price_usd,
      price_basis="usd",
      market_cap_usd=None,
      liquidity_usd=None,
      holders=None,
      source_event_id=str(row["event_id"]),
      source_intent_id=str(row["intent_id"]),
      source_resolution_id=str(row["resolution_id"]),
      observation_kind="message_quote",
      event_received_at_ms=int(row["event_received_at_ms"]),
      raw_payload={**price.raw, "payload_hash": _payload_hash(price.raw)},
      commit=False,
  )
  ```

- [ ] **Step 6: Verify focused tests pass**

  ```bash
  uv run pytest tests/test_asset_market_sync.py::test_sync_dex_prices_refreshes_active_dex_venues_in_batches tests/test_message_market_observation.py::test_message_market_observation_writes_dex_message_quote_per_message -q
  ```
  Expected: `2 passed`.

- [ ] **Step 7: Commit**

  ```bash
  git add src/parallax/domains/asset_market/services/asset_market_sync.py src/parallax/domains/asset_market/services/message_market_observation.py tests/test_asset_market_sync.py tests/test_message_market_observation.py
  git commit -m "fix: stop copying dex market metadata into price-only observations"
  ```

## Task 2: Add Field-Aware Current Market Read Model

**Files:**

- Create: `src/parallax/domains/asset_market/services/market_field_facts.py`
- Create: `src/parallax/domains/asset_market/repositories/current_market_repository.py`
- Create: `src/parallax/domains/asset_market/read_models/__init__.py`
- Create: `src/parallax/domains/asset_market/read_models/current_market_service.py`
- Modify: `src/parallax/domains/asset_market/interfaces.py`
- Modify: `src/parallax/app/runtime/repository_session.py`
- Test: `tests/test_current_market_repository.py`
- Test: `tests/test_project_structure.py`

- [ ] **Step 1: Write failing repository tests**

  Create `tests/test_current_market_repository.py` with these three tests:
  ```python
  from __future__ import annotations

  from parallax.domains.asset_market.repositories.current_market_repository import CurrentMarketRepository
  from parallax.domains.asset_market.repositories.price_observation_repository import PriceObservationRepository
  from tests.postgres_test_utils import connect_postgres_test
  from tests.postgres_test_utils import reset_postgres_schema as migrate


  SUBJECT_TYPE = "Asset"
  SUBJECT_ID = "asset:solana:token:TROLL"


  def test_current_market_keeps_price_fresh_while_market_cap_stale(tmp_path):
      conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
      try:
          migrate(conn)
          observations = PriceObservationRepository(conn)
          observations.insert_observation(
              provider="okx_dex_search",
              pricefeed_id="feed-search",
              observed_at_ms=1_700_000_000_000,
              subject_type=SUBJECT_TYPE,
              subject_id=SUBJECT_ID,
              price_usd=0.051,
              price_basis="usd",
              market_cap_usd=51_000_000,
              liquidity_usd=3_000_000,
              holders=52_000,
          )
          observations.insert_observation(
              provider="okx_dex_price",
              pricefeed_id="feed-price",
              observed_at_ms=1_700_086_400_000,
              subject_type=SUBJECT_TYPE,
              subject_id=SUBJECT_ID,
              price_usd=0.104,
              price_basis="usd",
              market_cap_usd=51_000_000,
              liquidity_usd=3_000_000,
              holders=52_000,
          )
          snapshot = CurrentMarketRepository(conn).current_for_subjects(
              [{"target_type": SUBJECT_TYPE, "target_id": SUBJECT_ID}],
              now_ms=1_700_086_430_000,
          )[(SUBJECT_TYPE, SUBJECT_ID)]
      finally:
          conn.close()

      assert snapshot["fields"]["price_usd"]["value"] == 0.104
      assert snapshot["fields"]["price_usd"]["status"] == "fresh"
      assert snapshot["fields"]["market_cap_usd"]["value"] == 51_000_000
      assert snapshot["fields"]["market_cap_usd"]["status"] == "stale"
      assert snapshot["fields"]["market_cap_usd"]["observed_at_ms"] == 1_700_000_000_000
      assert snapshot["fields"]["market_cap_usd"]["provider"] == "okx_dex_search"
      assert snapshot["market_status"] == "partial"


  def test_current_market_updates_market_cap_from_full_metadata_provider(tmp_path):
      conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
      try:
          migrate(conn)
          observations = PriceObservationRepository(conn)
          observations.insert_observation(
              provider="okx_dex_search",
              pricefeed_id="feed-search",
              observed_at_ms=1_700_086_420_000,
              subject_type=SUBJECT_TYPE,
              subject_id=SUBJECT_ID,
              price_usd=0.104,
              price_basis="usd",
              market_cap_usd=100_000_000,
              liquidity_usd=4_100_000,
              holders=55_000,
          )
          snapshot = CurrentMarketRepository(conn).current_for_subjects(
              [{"target_type": SUBJECT_TYPE, "target_id": SUBJECT_ID}],
              now_ms=1_700_086_430_000,
          )[(SUBJECT_TYPE, SUBJECT_ID)]
      finally:
          conn.close()

      assert snapshot["fields"]["market_cap_usd"]["value"] == 100_000_000
      assert snapshot["fields"]["market_cap_usd"]["status"] == "fresh"
      assert snapshot["market_status"] == "fresh"


  def test_current_market_reads_cex_ticker_fields(tmp_path):
      conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
      try:
          migrate(conn)
          observations = PriceObservationRepository(conn)
          observations.insert_observation(
              provider="okx_cex",
              pricefeed_id="feed-btc",
              observed_at_ms=1_700_086_420_000,
              subject_type="CexToken",
              subject_id="cex_token:BTC",
              price_usd=70_000,
              price_quote=70_000,
              quote_symbol="USDT",
              price_basis="quote_as_usd",
              volume_24h_usd=1_000_000,
              open_interest_usd=2_000_000,
          )
          snapshot = CurrentMarketRepository(conn).current_for_subjects(
              [{"target_type": "CexToken", "target_id": "cex_token:BTC"}],
              now_ms=1_700_086_430_000,
          )[("CexToken", "cex_token:BTC")]
      finally:
          conn.close()

      assert snapshot["fields"]["price_usd"]["status"] == "fresh"
      assert snapshot["fields"]["volume_24h_usd"]["value"] == 1_000_000
      assert snapshot["fields"]["open_interest_usd"]["value"] == 2_000_000
      assert snapshot["market_status"] == "fresh"
  ```

- [ ] **Step 2: Run failing tests**

  ```bash
  uv run pytest tests/test_current_market_repository.py -q
  ```
  Expected: import failure because repository does not exist.

- [ ] **Step 3: Implement pure market field helpers**

  Create `market_field_facts.py`:
  ```python
  from __future__ import annotations

  from typing import Any

  DEFAULT_PRICE_FRESH_MS = 5 * 60 * 1000
  DEFAULT_MARKET_METADATA_FRESH_MS = 5 * 60 * 1000
  RESOLUTION_MARKET_FRESH_MS = 24 * 60 * 60 * 1000

  PRICE_CAPABLE_PROVIDERS = frozenset({"okx_dex_search", "okx_dex_price", "okx_dex_ws_price_info", "okx_cex"})
  DEX_METADATA_CAPABLE_PROVIDERS = frozenset({"okx_dex_search", "okx_dex_ws_price_info"})
  CEX_MARKET_CAPABLE_PROVIDERS = frozenset({"okx_cex"})


  def field_status(*, value: Any, observed_at_ms: int | None, now_ms: int, fresh_ms: int) -> str:
      if value is None or observed_at_ms is None:
          return "missing"
      age_ms = max(0, int(now_ms) - int(observed_at_ms))
      return "fresh" if age_ms <= int(fresh_ms) else "stale"


  def field_fact(
      *,
      value: Any,
      observed_at_ms: int | None,
      now_ms: int,
      provider: str | None,
      observation_id: str | None,
      fresh_ms: int,
  ) -> dict[str, Any]:
      age_ms = max(0, int(now_ms) - int(observed_at_ms)) if observed_at_ms is not None else None
      return {
          "value": _json_number(value),
          "status": field_status(value=value, observed_at_ms=observed_at_ms, now_ms=now_ms, fresh_ms=fresh_ms),
          "observed_at_ms": int(observed_at_ms) if observed_at_ms is not None else None,
          "age_ms": age_ms,
          "provider": provider,
          "source_observation_id": observation_id,
      }


  def aggregate_market_status(*, target_type: str, fields: dict[str, dict[str, Any]]) -> str:
      required = ("price_usd",) if target_type == "CexToken" else (
          "price_usd",
          "market_cap_usd",
          "liquidity_usd",
          "holders",
      )
      statuses = [str(fields.get(key, {}).get("status") or "missing") for key in required]
      if all(status == "fresh" for status in statuses):
          return "fresh"
      if any(status == "fresh" for status in statuses):
          return "partial"
      if any(status == "stale" for status in statuses):
          return "stale"
      return "missing"


  def _json_number(value: Any) -> Any:
      if value is None:
          return None
      try:
          numeric = float(value)
      except (TypeError, ValueError):
          return value
      return int(numeric) if numeric.is_integer() else numeric
  ```

- [ ] **Step 4: Implement field-aware repository**

  Create `current_market_repository.py` with `current_for_subjects(subjects, now_ms=now_ms)`. Use one `VALUES` CTE and one LATERAL query per field:
  ```python
  class CurrentMarketRepository:
      def __init__(self, conn: Any):
          self.conn = conn

      def current_for_subjects(self, subjects: list[dict[str, Any]], *, now_ms: int) -> dict[tuple[str, str], dict[str, Any]]:
          normalized = _subjects(subjects)
          if not normalized:
              return {}
          values_sql = ",".join(["(%s, %s)"] * len(normalized))
          params: list[Any] = []
          for subject_type, subject_id in normalized:
              params.extend([subject_type, subject_id])
          rows = self.conn.execute(
              f"""
              WITH requested(subject_type, subject_id) AS (VALUES {values_sql})
              SELECT
                requested.subject_type,
                requested.subject_id,
                price.observation_id AS price_observation_id,
                price.provider AS price_provider,
                price.observed_at_ms AS price_observed_at_ms,
                price.price_usd,
                price.price_quote,
                price.quote_symbol,
                price.price_basis,
                market_cap.observation_id AS market_cap_observation_id,
                market_cap.provider AS market_cap_provider,
                market_cap.observed_at_ms AS market_cap_observed_at_ms,
                market_cap.market_cap_usd,
                liquidity.observation_id AS liquidity_observation_id,
                liquidity.provider AS liquidity_provider,
                liquidity.observed_at_ms AS liquidity_observed_at_ms,
                liquidity.liquidity_usd,
                holders.observation_id AS holders_observation_id,
                holders.provider AS holders_provider,
                holders.observed_at_ms AS holders_observed_at_ms,
                holders.holders,
                volume_24h.observation_id AS volume_24h_observation_id,
                volume_24h.provider AS volume_24h_provider,
                volume_24h.observed_at_ms AS volume_24h_observed_at_ms,
                volume_24h.volume_24h_usd,
                open_interest.observation_id AS open_interest_observation_id,
                open_interest.provider AS open_interest_provider,
                open_interest.observed_at_ms AS open_interest_observed_at_ms,
                open_interest.open_interest_usd
              FROM requested
              LEFT JOIN LATERAL (
                SELECT *
                FROM price_observations
                WHERE subject_type = requested.subject_type
                  AND subject_id = requested.subject_id
                  AND provider IN ('okx_dex_search', 'okx_dex_price', 'okx_dex_ws_price_info', 'okx_cex')
                  AND (price_usd IS NOT NULL OR price_quote IS NOT NULL)
                ORDER BY observed_at_ms DESC, observation_id DESC
                LIMIT 1
              ) price ON true
              LEFT JOIN LATERAL (
                SELECT *
                FROM price_observations
                WHERE subject_type = requested.subject_type
                  AND subject_id = requested.subject_id
                  AND provider IN ('okx_dex_search', 'okx_dex_ws_price_info')
                  AND market_cap_usd IS NOT NULL
                ORDER BY observed_at_ms DESC, observation_id DESC
                LIMIT 1
              ) market_cap ON true
              LEFT JOIN LATERAL (
                SELECT *
                FROM price_observations
                WHERE subject_type = requested.subject_type
                  AND subject_id = requested.subject_id
                  AND provider IN ('okx_dex_search', 'okx_dex_ws_price_info')
                  AND liquidity_usd IS NOT NULL
                ORDER BY observed_at_ms DESC, observation_id DESC
                LIMIT 1
              ) liquidity ON true
              LEFT JOIN LATERAL (
                SELECT *
                FROM price_observations
                WHERE subject_type = requested.subject_type
                  AND subject_id = requested.subject_id
                  AND provider IN ('okx_dex_search', 'okx_dex_ws_price_info')
                  AND holders IS NOT NULL
                ORDER BY observed_at_ms DESC, observation_id DESC
                LIMIT 1
              ) holders ON true
              LEFT JOIN LATERAL (
                SELECT *
                FROM price_observations
                WHERE subject_type = requested.subject_type
                  AND subject_id = requested.subject_id
                  AND provider IN ('okx_cex', 'okx_dex_search', 'okx_dex_ws_price_info')
                  AND volume_24h_usd IS NOT NULL
                ORDER BY observed_at_ms DESC, observation_id DESC
                LIMIT 1
              ) volume_24h ON true
              LEFT JOIN LATERAL (
                SELECT *
                FROM price_observations
                WHERE subject_type = requested.subject_type
                  AND subject_id = requested.subject_id
                  AND provider IN ('okx_cex')
                  AND open_interest_usd IS NOT NULL
                ORDER BY observed_at_ms DESC, observation_id DESC
                LIMIT 1
              ) open_interest ON true
              """,
              params,
          ).fetchall()
          return {_key(row): _snapshot(row, now_ms=now_ms) for row in rows}
  ```
  Implement `_subjects`, `_key`, and `_snapshot` in the same file using `market_field_facts.field_fact()` and `aggregate_market_status()`.

- [ ] **Step 5: Add read model wrapper**

  Create `read_models/current_market_service.py`:
  ```python
  from __future__ import annotations

  from typing import Any


  class CurrentMarketService:
      def __init__(self, *, current_market):
          self.current_market = current_market

      def current_market_snapshot(self, *, target_type: str, target_id: str, now_ms: int) -> dict[str, Any]:
          snapshots = self.current_market.current_for_subjects(
              [{"target_type": target_type, "target_id": target_id}],
              now_ms=now_ms,
          )
          return snapshots.get((target_type, target_id)) or {
              "target_type": target_type,
              "target_id": target_id,
              "market_status": "missing",
              "fields": {},
          }
  ```

- [ ] **Step 6: Export and wire repository**

  Add `CurrentMarketRepository` to `asset_market/interfaces.py` and `app/runtime/repository_session.py`.
  ```python
  from .repositories.current_market_repository import CurrentMarketRepository
  from .read_models.current_market_service import CurrentMarketService
  ```
  Add dataclass field:
  ```python
  current_market: CurrentMarketRepository
  ```
  Add constructor entry:
  ```python
  current_market=CurrentMarketRepository(conn),
  ```

- [ ] **Step 7: Verify focused tests**

  ```bash
  uv run pytest tests/test_current_market_repository.py tests/test_project_structure.py -q
  ```
  Expected: all selected tests pass.

- [ ] **Step 8: Commit**

  ```bash
  git add src/parallax/domains/asset_market/services/market_field_facts.py src/parallax/domains/asset_market/repositories/current_market_repository.py src/parallax/domains/asset_market/read_models src/parallax/domains/asset_market/interfaces.py src/parallax/app/runtime/repository_session.py tests/test_current_market_repository.py tests/test_project_structure.py
  git commit -m "feat: add field-aware current market read model"
  ```

## Task 3: Make Symbol Resolution Use Field-Provenance Market Evidence

**Files:**

- Modify: `src/parallax/domains/asset_market/repositories/registry_repository.py:193-225`
- Modify: `src/parallax/domains/token_intel/services/deterministic_token_resolver.py:299-340`
- Test: `tests/test_registry_repository.py`
- Test: `tests/test_deterministic_token_resolver.py`

- [ ] **Step 1: Add registry regression for polluted latest row**

  Add `tests/test_registry_repository.py::test_symbol_lookup_ignores_okx_price_only_market_metadata_for_dominance`:
  ```python
  def test_symbol_lookup_ignores_okx_price_only_market_metadata_for_dominance(tmp_path):
      conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
      try:
          migrate(conn)
          registry = RegistryRepository(conn)
          identity = IdentityEvidenceRepository(conn)
          observations = PriceObservationRepository(conn)
          asset = registry.upsert_chain_asset(
              chain_id="solana",
              address="5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
              observed_at_ms=1_700_000_000_000,
          )
          _write_identity(identity, asset, symbol="TROLL", observed_at_ms=1_700_000_000_000)
          observations.insert_observation(
              provider="okx_dex_search",
              pricefeed_id="feed-search",
              observed_at_ms=1_700_000_000_000,
              subject_type="Asset",
              subject_id=asset["asset_id"],
              price_usd=0.051,
              price_basis="usd",
              market_cap_usd=51_000_000,
              liquidity_usd=3_000_000,
              holders=52_000,
          )
          observations.insert_observation(
              provider="okx_dex_price",
              pricefeed_id="feed-price",
              observed_at_ms=1_700_086_400_000,
              subject_type="Asset",
              subject_id=asset["asset_id"],
              price_usd=0.104,
              price_basis="usd",
              market_cap_usd=100_000_000,
              liquidity_usd=4_000_000,
              holders=55_000,
          )
          row = registry.find_assets_by_symbol_with_latest_observation("TROLL")[0]
      finally:
          conn.close()

      assert row["price_usd"] == 0.104
      assert row["market_cap_usd"] == 51_000_000
      assert row["market_cap_observed_at_ms"] == 1_700_000_000_000
      assert row["market_cap_provider"] == "okx_dex_search"
  ```

- [ ] **Step 2: Add resolver stale-dominance regression**

  In `tests/test_deterministic_token_resolver.py`, add:
  ```python
  def test_symbol_dominance_requires_field_freshness():
      registry = FakeRegistry(
          cex_token=None,
          assets=[
              {
                  "asset_id": "asset-1",
                  "market_cap_usd": 100_000_000,
                  "liquidity_usd": 4_000_000,
                  "holders": 55_000,
                  "market_cap_status": "stale",
                  "liquidity_status": "stale",
                  "holders_status": "stale",
              }
          ],
      )
      decision = DeterministicTokenResolver(registry=registry).resolve(
          intent_id="intent-1",
          event_id="event-1",
          keys=MentionKeys(symbol="TROLL"),
          decision_time_ms=1_700_086_430_000,
      )

      assert decision.resolution_status == "AMBIGUOUS"
      assert "NO_MARKET_DOMINANT_CHAIN_ASSET" in decision.reason_codes
  ```
  If the existing `FakeRegistry` in that test file has a different constructor, extend it with `assets` and `cex_token` fields.

- [ ] **Step 3: Run failing tests**

  ```bash
  uv run pytest tests/test_registry_repository.py::test_symbol_lookup_ignores_okx_price_only_market_metadata_for_dominance tests/test_deterministic_token_resolver.py::test_symbol_dominance_requires_field_freshness -q
  ```
  Expected: both fail with current latest-row / status-blind logic.

- [ ] **Step 4: Make registry symbol lookup field-aware**

  Replace the `latest_price` lateral join inside `find_assets_by_symbol_with_latest_observation()` with separate `latest_price`, `market_cap`, `liquidity`, and `holders` joins. Use the same provider capability filters as `CurrentMarketRepository`:
  ```sql
  LEFT JOIN LATERAL (
    SELECT *
    FROM price_observations
    WHERE price_observations.subject_type = 'Asset'
      AND price_observations.subject_id = registry_assets.asset_id
      AND price_observations.provider IN ('okx_dex_search', 'okx_dex_price', 'okx_dex_ws_price_info')
      AND price_observations.price_usd IS NOT NULL
    ORDER BY observed_at_ms DESC, observation_id DESC
    LIMIT 1
  ) latest_price ON true
  LEFT JOIN LATERAL (
    SELECT *
    FROM price_observations
    WHERE price_observations.subject_type = 'Asset'
      AND price_observations.subject_id = registry_assets.asset_id
      AND price_observations.provider IN ('okx_dex_search', 'okx_dex_ws_price_info')
      AND price_observations.market_cap_usd IS NOT NULL
    ORDER BY observed_at_ms DESC, observation_id DESC
    LIMIT 1
  ) market_cap ON true
  ```
  Repeat for `liquidity` and `holders`, selecting:
  ```sql
  latest_price.price_usd,
  latest_price.observed_at_ms AS price_observed_at_ms,
  latest_price.provider AS price_provider,
  market_cap.market_cap_usd,
  market_cap.observed_at_ms AS market_cap_observed_at_ms,
  market_cap.provider AS market_cap_provider,
  liquidity.liquidity_usd,
  liquidity.observed_at_ms AS liquidity_observed_at_ms,
  liquidity.provider AS liquidity_provider,
  holders.holders,
  holders.observed_at_ms AS holders_observed_at_ms,
  holders.provider AS holders_provider
  ```

- [ ] **Step 5: Add status fields for resolver**

  In Python after fetching rows, enrich each row:
  ```python
  def _resolution_field_status(row: dict[str, Any], key: str) -> str:
      observed_at_ms = row.get(f"{key}_observed_at_ms")
      value = row.get(f"{key}_usd") if key in {"market_cap", "liquidity"} else row.get(key)
      if value is None or observed_at_ms is None:
          return "missing"
      return "fresh"
  ```
  Add keys:
  ```python
  item["market_cap_status"] = _resolution_field_status(item, "market_cap")
  item["liquidity_status"] = _resolution_field_status(item, "liquidity")
  item["holders_status"] = _resolution_field_status(item, "holders")
  ```
  This method is intentionally binary for resolver input because `find_assets_by_symbol_with_latest_observation()` only selects capable-provider fields. Time-window policy is enforced in the resolver.

- [ ] **Step 6: Make dominance require usable statuses**

  In `deterministic_token_resolver.py`, add:
  ```python
  RESOLUTION_MARKET_FRESH_MS = 24 * 60 * 60 * 1000
  ```
  Update `_dominance_eligible(row)`:
  ```python
  def _dominance_eligible(row: dict[str, Any]) -> bool:
      present = sum(
          1
          for key in ("market_cap_usd", "holders", "liquidity_usd")
          if row.get(key) is not None and _decimal(row.get(key)) > 0
      )
      if present < 2:
          return False
      return _fresh_resolution_market_fields(row) >= 2
  ```
  Add:
  ```python
  def _fresh_resolution_market_fields(row: dict[str, Any]) -> int:
      count = 0
      for value_key, observed_key in (
          ("market_cap_usd", "market_cap_observed_at_ms"),
          ("liquidity_usd", "liquidity_observed_at_ms"),
          ("holders", "holders_observed_at_ms"),
      ):
          if row.get(value_key) is None or row.get(observed_key) is None:
              continue
          try:
              age_ms = max(0, int(row.get("decision_time_ms") or 0) - int(row[observed_key]))
          except (TypeError, ValueError):
              continue
          if age_ms <= RESOLUTION_MARKET_FRESH_MS:
              count += 1
      return count
  ```
  In `_resolve_symbol`, before `_market_dominant_asset(assets)`, attach `decision_time_ms` to each row:
  ```python
  assets = [{**row, "decision_time_ms": decision_time_ms} for row in assets]
  ```

- [ ] **Step 7: Verify focused tests**

  ```bash
  uv run pytest tests/test_registry_repository.py::test_symbol_lookup_ignores_okx_price_only_market_metadata_for_dominance tests/test_deterministic_token_resolver.py::test_symbol_dominance_requires_field_freshness -q
  ```
  Expected: selected tests pass.

- [ ] **Step 8: Commit**

  ```bash
  git add src/parallax/domains/asset_market/repositories/registry_repository.py src/parallax/domains/token_intel/services/deterministic_token_resolver.py tests/test_registry_repository.py tests/test_deterministic_token_resolver.py
  git commit -m "fix: use field-provenance market data for symbol dominance"
  ```

## Task 4: Hydrate Token Radar From Current Market

**Files:**

- Modify: `src/parallax/domains/token_intel/_constants.py`
- Modify: `src/parallax/domains/token_intel/queries/token_radar_source_query.py`
- Modify: `src/parallax/domains/token_intel/services/token_radar_projection.py`
- Modify: `src/parallax/domains/token_intel/scoring/factor_snapshot.py`
- Test: `tests/test_token_radar_projection.py`
- Test: `tests/golden/test_token_radar_corpus.py`

- [ ] **Step 1: Add projection hydration regression**

  In `tests/test_token_radar_projection.py`, add a fake `current_market` repository and assert it is used:
  ```python
  class FakeCurrentMarket:
      def __init__(self):
          self.calls = []

      def current_for_subjects(self, subjects, *, now_ms):
          self.calls.append({"subjects": subjects, "now_ms": now_ms})
          return {
              ("Asset", "asset-1"): {
                  "target_type": "Asset",
                  "target_id": "asset-1",
                  "market_status": "partial",
                  "fields": {
                      "price_usd": {"value": 0.104, "status": "fresh", "observed_at_ms": now_ms - 30_000, "age_ms": 30_000, "provider": "okx_dex_price"},
                      "market_cap_usd": {"value": 51_000_000, "status": "stale", "observed_at_ms": now_ms - 86_400_000, "age_ms": 86_400_000, "provider": "okx_dex_search"},
                      "liquidity_usd": {"value": 3_000_000, "status": "stale", "observed_at_ms": now_ms - 86_400_000, "age_ms": 86_400_000, "provider": "okx_dex_search"},
                      "holders": {"value": 52_000, "status": "stale", "observed_at_ms": now_ms - 86_400_000, "age_ms": 86_400_000, "provider": "okx_dex_search"},
                  },
              }
          }
  ```
  Use it in a projection test:
  ```python
  repos = type("Repos", (), {"conn": object(), "token_radar": token_radar, "current_market": current_market})()
  ```
  Assert:
  ```python
  facts = token_radar.rows[0]["factor_snapshot_json"]["families"]["market_quality"]["facts"]
  assert facts["market_status"] == "partial"
  assert facts["field_statuses"]["price_usd"] == "fresh"
  assert facts["field_statuses"]["market_cap_usd"] == "stale"
  assert current_market.calls
  ```

- [ ] **Step 2: Bump projection source/version constants**

  In `_constants.py`:
  ```python
  TOKEN_RADAR_PROJECTION_VERSION = "token-radar-v10-current-market"
  TOKEN_RADAR_SOURCE_TABLE = "token_intent_resolutions+asset_identity_current+current_market"
  ```
  Update `tests/test_token_radar_projection.py::test_token_radar_projection_uses_factor_snapshot_contract` expected constants.

- [ ] **Step 3: Remove latest current market joins from source query**

  In `token_radar_source_query.py` remove selected columns:
  ```sql
  COALESCE(latest_feed_price.provider, latest_subject_price.provider) AS market_provider,
  COALESCE(latest_feed_price.observed_at_ms, latest_subject_price.observed_at_ms) AS market_observed_at_ms,
  COALESCE(latest_feed_price.price_usd, latest_subject_price.price_usd) AS market_price_usd,
  COALESCE(latest_feed_price.price_quote, latest_subject_price.price_quote) AS market_price_quote,
  COALESCE(latest_feed_price.quote_symbol, latest_subject_price.quote_symbol) AS market_quote_symbol,
  COALESCE(latest_feed_price.price_basis, latest_subject_price.price_basis) AS market_price_basis,
  COALESCE(latest_feed_price.market_cap_usd, latest_subject_price.market_cap_usd) AS market_market_cap_usd,
  COALESCE(latest_feed_price.liquidity_usd, latest_subject_price.liquidity_usd) AS market_liquidity_usd,
  COALESCE(latest_feed_price.volume_24h_usd, latest_subject_price.volume_24h_usd) AS market_volume_24h_usd,
  COALESCE(latest_feed_price.open_interest_usd, latest_subject_price.open_interest_usd) AS market_open_interest_usd,
  COALESCE(latest_feed_price.holders, latest_subject_price.holders) AS market_holders,
  ```
  Remove LATERAL joins named `latest_feed_price` and `latest_subject_price`. Keep `preferred_price_feed`, `first_price`, `message_event_price`, `event_history_price`, and `before_event_price`.

- [ ] **Step 4: Add current-market hydration helper to projection**

  In `TokenRadarProjection.rebuild()`, after reading source rows:
  ```python
  source_rows = self.source.source_rows(since_ms=since_ms, scope=scope, now_ms=now_ms)
  source_rows = self._hydrate_current_market(source_rows, now_ms=now_ms)
  ```
  Add method:
  ```python
  def _hydrate_current_market(self, rows: list[dict[str, Any]], *, now_ms: int) -> list[dict[str, Any]]:
      subjects = [
          {"target_type": row.get("target_type"), "target_id": row.get("target_id")}
          for row in rows
          if row.get("target_type") and row.get("target_id")
      ]
      snapshots = self.repos.current_market.current_for_subjects(subjects, now_ms=now_ms)
      hydrated = []
      for row in rows:
          snapshot = snapshots.get((str(row.get("target_type")), str(row.get("target_id"))))
          hydrated.append(_row_with_current_market(row, snapshot))
      return hydrated
  ```
  Add pure helper `_row_with_current_market(row, snapshot)` in the same module. It maps current-market fields into existing `market_*` keys consumed by `_market()`:
  ```python
  def _row_with_current_market(row: dict[str, Any], snapshot: dict[str, Any] | None) -> dict[str, Any]:
      if not snapshot:
          return {**row, "current_market_snapshot": None}
      fields = snapshot.get("fields") if isinstance(snapshot.get("fields"), dict) else {}
      price = fields.get("price_usd") or {}
      market_cap = fields.get("market_cap_usd") or {}
      liquidity = fields.get("liquidity_usd") or {}
      holders = fields.get("holders") or {}
      return {
          **row,
          "current_market_snapshot": snapshot,
          "market_provider": price.get("provider"),
          "market_observed_at_ms": price.get("observed_at_ms"),
          "market_price_usd": price.get("value"),
          "market_price_status": price.get("status"),
          "market_market_cap_usd": market_cap.get("value"),
          "market_market_cap_status": market_cap.get("status"),
          "market_liquidity_usd": liquidity.get("value"),
          "market_liquidity_status": liquidity.get("status"),
          "market_holders": holders.get("value"),
          "market_holders_status": holders.get("status"),
          "market_status_from_current": snapshot.get("market_status"),
          "market_field_statuses": {key: value.get("status") for key, value in fields.items() if isinstance(value, dict)},
      }
  ```

- [ ] **Step 5: Make `_market()` use current-market aggregate/statuses**

  In `_market()`, replace row-level freshness-only status with:
  ```python
  current_status = str(latest.get("market_status_from_current") or "")
  market_status = current_status or ("fresh" if fresh else "stale")
  ```
  Add to returned market dict:
  ```python
  "field_statuses": latest.get("market_field_statuses") or {},
  "market_cap_status": latest.get("market_market_cap_status"),
  "liquidity_status": latest.get("market_liquidity_status"),
  "holders_status": latest.get("market_holders_status"),
  ```

- [ ] **Step 6: Add field statuses to factor snapshot market facts**

  In `_market_quality_family`, add:
  ```python
  field_statuses = market.get("field_statuses") if isinstance(market.get("field_statuses"), dict) else {}
  facts = {
      "target_market_type": target_market_type,
      "market_status": _optional_str(market.get("market_status") or market.get("market_observation_status")),
      "holders": _optional_int(market.get("holders")),
      "liquidity_usd": _optional_float(market.get("liquidity_usd")),
      "market_cap_usd": _optional_float(market.get("market_cap_usd")),
      "volume_24h_usd": _optional_float(market.get("volume_24h_usd")),
      "open_interest_usd": _optional_float(market.get("open_interest_usd")),
      "native_market_id": _optional_str(market.get("native_market_id")),
      "field_statuses": {
          "price_usd": _optional_str(field_statuses.get("price_usd")),
          "market_cap_usd": _optional_str(field_statuses.get("market_cap_usd") or market.get("market_cap_status")),
          "liquidity_usd": _optional_str(field_statuses.get("liquidity_usd") or market.get("liquidity_status")),
          "holders": _optional_str(field_statuses.get("holders") or market.get("holders_status")),
      },
  }
  ```
  Do not add `price_usd` to factor facts as a frontend live price source.

- [ ] **Step 7: Verify focused projection tests**

  ```bash
  uv run pytest tests/test_token_radar_projection.py tests/golden/test_token_radar_corpus.py -q
  ```
  Expected: selected tests pass after fixture updates.

- [ ] **Step 8: Commit**

  ```bash
  git add src/parallax/domains/token_intel/_constants.py src/parallax/domains/token_intel/queries/token_radar_source_query.py src/parallax/domains/token_intel/services/token_radar_projection.py src/parallax/domains/token_intel/scoring/factor_snapshot.py tests/test_token_radar_projection.py tests/golden/test_token_radar_corpus.py
  git commit -m "feat: hydrate token radar from current market snapshots"
  ```

## Task 5: Hard-Cut API and Frontend to `current_market`

**Files:**

- Modify: `src/parallax/domains/token_intel/read_models/asset_flow_service.py`
- Modify: `src/parallax/app/surfaces/api/http.py`
- Modify: `src/parallax/app/surfaces/cli/main.py`
- Modify: `src/parallax/app/runtime/app.py`
- Modify: `web/src/api/types.ts`
- Modify: `web/src/lib/tokenRadar.ts`
- Modify: `web/src/components/TokenRadarRow.tsx`
- Test: `tests/test_asset_flow_service.py`
- Test: `tests/test_api_http.py`
- Test: `web/src/lib/tokenRadar.test.ts`
- Test: `web/src/components/TokenRadarRow.test.tsx`
- Test: `web/src/App.test.tsx`

- [ ] **Step 1: Rewrite AssetFlowService tests around `current_market`**

  In `tests/test_asset_flow_service.py`, replace the test asserting `price == market == factor_snapshot.families.market_quality.facts` with:
  ```python
  def test_asset_flow_exposes_current_market_from_asset_market_read_model():
      current_market = FakeCurrentMarket(
          {
              ("CexToken", "cex_token:BTC"): {
                  "target_type": "CexToken",
                  "target_id": "cex_token:BTC",
                  "market_status": "fresh",
                  "fields": {
                      "price_usd": {"value": 70_000, "status": "fresh", "age_ms": 15_000},
                      "volume_24h_usd": {"value": 123_000_000, "status": "fresh"},
                      "open_interest_usd": {"value": 45_000_000, "status": "fresh"},
                  },
              }
          }
      )
      service = AssetFlowService(token_radar=FakeTokenRadar(rows=[radar_row(lane="resolved", symbol="BTC", asset_id="cex_token:BTC", target_type="CexToken")]), current_market=current_market)

      result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

      row = result["targets"][0]
      assert row["current_market"]["market_status"] == "fresh"
      assert row["current_market"]["fields"]["price_usd"]["value"] == 70_000
      assert "price" not in row
      assert "market" not in row
  ```

- [ ] **Step 2: Make AssetFlowService require current market**

  Change constructor:
  ```python
  class AssetFlowService:
      def __init__(self, *, token_radar, current_market):
          self.token_radar = token_radar
          self.current_market = current_market
  ```
  In `asset_flow()`, after `rows`:
  ```python
  market_snapshots = self.current_market.current_for_subjects(
      [_target_ref_from_snapshot(row.get("factor_snapshot_json")) for row in rows],
      now_ms=now_ms or _now_ms(),
  )
  targets = [
      _public_row(row, market_snapshot=market_snapshots.get(_target_key_from_snapshot(row.get("factor_snapshot_json"))))
      for row in rows
      if row.get("lane") == "resolved"
  ]
  ```
  Add `_target_ref_from_snapshot` and `_target_key_from_snapshot` helpers. `_public_row` returns:
  ```python
  "current_market": market_snapshot or {"market_status": "missing", "fields": {}},
  ```
  Remove `"market": market` and `"price": market`.

- [ ] **Step 3: Update API and CLI construction**

  In `api/http.py`:
  ```python
  data = AssetFlowService(token_radar=repos.token_radar, current_market=repos.current_market).asset_flow(
      since_ms=since_ms,
      limit=limit,
      scope=scope,
      now_ms=_now_ms(),
  )
  ```
  Add endpoint:
  ```python
  @router.get("/current-market")
  async def current_market(request: Request, target_type: Annotated[str, Query()] = "", target_id: Annotated[str, Query()] = "") -> JSONResponse:
      runtime = _authenticated_runtime(request)
      parsed_target_type = _target_type(target_type)
      if not parsed_target_type or not target_id:
          raise ApiBadRequest("target_required", field="target_id")
      with runtime.repositories() as repos:
          snapshot = CurrentMarketService(current_market=repos.current_market).current_market_snapshot(
              target_type=parsed_target_type,
              target_id=target_id,
              now_ms=_now_ms(),
          )
      return _json({"ok": True, "data": snapshot})
  ```
  Import `CurrentMarketService` and reuse the existing `_now_ms()` helper if present; otherwise add a local helper mirroring other API code.

- [ ] **Step 4: Update frontend types**

  In `web/src/api/types.ts`, define:
  ```ts
  export type MarketFieldFact = {
    value?: number | string | null;
    status: "fresh" | "partial" | "stale" | "missing" | "unsupported" | "rate_limited" | "provider_error" | string;
    observed_at_ms?: number | null;
    age_ms?: number | null;
    provider?: string | null;
    source_observation_id?: string | null;
  };

  export type CurrentMarketSnapshot = {
    target_type?: string | null;
    target_id?: string | null;
    market_status: "fresh" | "partial" | "stale" | "missing" | string;
    fields: Record<string, MarketFieldFact>;
  };
  ```
  Replace the `AssetFlowRow.price` field with:
  ```ts
  current_market: CurrentMarketSnapshot;
  ```

- [ ] **Step 5: Update `tokenRadar.ts` hard cut**

  Replace market facts price reads:
  ```ts
  const currentMarket = requiredObject(row.current_market, "current_market") as CurrentMarketSnapshot;
  const marketFields = currentMarket.fields ?? {};
  const priceField = marketFields.price_usd ?? marketFields.price_quote;
  const marketPrice = optionalNullableNumber(priceField?.value);
  ```
  Build `market` block from current market:
  ```ts
  market: {
    market_status: currentMarket.market_status,
    price: marketPrice,
    market_cap: optionalNullableNumber(marketFields.market_cap_usd?.value),
    liquidity: optionalNullableNumber(marketFields.liquidity_usd?.value),
    pool_status: currentMarket.market_status === "fresh" ? "ready" : "missing",
    holder_count: optionalNullableNumber(marketFields.holders?.value),
    volume_24h: optionalNullableNumber(marketFields.volume_24h_usd?.value),
    snapshot_age_ms: optionalNullableNumber(priceField?.age_ms),
    snapshot_received_at_ms: optionalNullableNumber(priceField?.observed_at_ms),
    market_observation_status: currentMarket.market_status,
    price_change_status: priceChangeStatus
  }
  ```
  Remove `optionalNullableNumber(marketFacts.price_usd)` and `optionalNullableNumber(marketFacts.snapshot_age_ms)` as live price sources.

- [ ] **Step 6: Add frontend anti-regression test**

  In `web/src/lib/tokenRadar.test.ts`, add:
  ```ts
  it("does not read live price from factor snapshot market facts", () => {
    const row = productionFactorSnapshotRow();
    row.current_market = {
      market_status: "partial",
      fields: {
        price_usd: { value: 0.104, status: "fresh", age_ms: 30_000 },
        market_cap_usd: { value: 51_000_000, status: "stale", age_ms: 86_400_000 }
      }
    };
    row.factor_snapshot.families.market_quality.facts.price_usd = 999;

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.market.price).toBe(0.104);
    expect(item.market.market_cap).toBe(51_000_000);
    expect(item.market.market_status).toBe("partial");
  });
  ```

- [ ] **Step 7: Verify backend and frontend focused tests**

  ```bash
  uv run pytest tests/test_asset_flow_service.py tests/test_api_http.py -q
  npm test -- --run web/src/lib/tokenRadar.test.ts web/src/components/TokenRadarRow.test.tsx web/src/App.test.tsx
  ```
  Expected: selected tests pass.

- [ ] **Step 8: Commit**

  ```bash
  git add src/parallax/domains/token_intel/read_models/asset_flow_service.py src/parallax/app/surfaces/api/http.py src/parallax/app/surfaces/cli/main.py src/parallax/app/runtime/app.py web/src/api/types.ts web/src/lib/tokenRadar.ts web/src/components/TokenRadarRow.tsx tests/test_asset_flow_service.py tests/test_api_http.py web/src/lib/tokenRadar.test.ts web/src/components/TokenRadarRow.test.tsx web/src/App.test.tsx
  git commit -m "feat: hard cut token radar api to current market"
  ```

## Task 6: Share OKX DEX Provider Budget

**Files:**

- Modify: `src/parallax/app/runtime/providers_wiring.py`
- Test: `tests/test_api_health.py`
- Test: `tests/test_asset_market_sync.py`

- [ ] **Step 1: Add wiring regression**

  Add a unit test that builds providers with OKX DEX configured and asserts sync/message/discovery share the same DEX provider object:
  ```python
  def test_okx_dex_provider_is_shared_across_asset_market_workers():
      settings = Settings(
          ws_token="test-token",
          okx_dex_api_key="key",
          okx_dex_secret_key="secret",
          okx_dex_passphrase="pass",
      )
      providers = wire_providers(settings, start_collector=True)

      assert providers.asset_market.sync_dex_market is providers.asset_market.message_dex_market
      assert providers.asset_market.sync_dex_market is providers.asset_market.discovery_dex_market
  ```
  Import `Settings` from `parallax.platform.config.settings` and `wire_providers` from `parallax.app.runtime.providers_wiring` in `tests/test_api_health.py`.

- [ ] **Step 2: Implement serialized provider wrapper**

  In `providers_wiring.py`, add:
  ```python
  from collections.abc import Sequence
  import threading


  class _SerializedDexMarketProvider:
      def __init__(self, provider: DexMarketProvider):
          self.provider = provider
          self._lock = threading.Lock()

      def search_tokens(self, *, query: str, chain_ids: Sequence[str]) -> list[Any]:
          with self._lock:
              return self.provider.search_tokens(query=query, chain_ids=chain_ids)

      def token_prices(self, tokens: list[Any]) -> list[Any]:
          with self._lock:
              return self.provider.token_prices(tokens)

      def close(self) -> None:
          close = getattr(self.provider, "close", None)
          if close:
              close()
  ```
  In `_wire_asset_market`, create one shared provider:
  ```python
  dex_market = _SerializedDexMarketProvider(_okx_dex_market(settings)) if settings.okx_dex_configured else None
  ```
  Return:
  ```python
  sync_dex_market=dex_market,
  message_dex_market=dex_market,
  discovery_dex_market=dex_market,
  ```
  Remove `projection_dex_market`; it is unused and violates projection purity by implying projection provider access.

- [ ] **Step 3: Verify wiring and health tests**

  ```bash
  uv run pytest tests/test_api_health.py tests/test_asset_market_sync.py -q
  ```
  Expected: selected tests pass.

- [ ] **Step 4: Commit**

  ```bash
  git add src/parallax/app/runtime/providers_wiring.py tests/test_api_health.py tests/test_asset_market_sync.py
  git commit -m "fix: share serialized okx dex provider across market workers"
  ```

## Task 7: Ops Audit and Docs

**Files:**

- Modify: `src/parallax/app/surfaces/cli/main.py`
- Modify: `src/parallax/domains/token_intel/ARCHITECTURE.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CONTRACTS.md`
- Test: `tests/test_cli.py`
- Test: `tests/test_token_radar_audit_cli.py`

- [ ] **Step 1: Extend CLI audit output**

  Add a current-market section to the existing token radar audit command or a new `current-market` ops command. The output shape:
  ```json
  {
    "target_type": "Asset",
    "target_id": "asset:solana:token:TROLL",
    "market_status": "partial",
    "fields": {
      "price_usd": {"value": 0.104, "status": "fresh", "age_ms": 30000, "provider": "okx_dex_price"},
      "market_cap_usd": {"value": 51000000, "status": "stale", "age_ms": 86400000, "provider": "okx_dex_search"}
    }
  }
  ```

- [ ] **Step 2: Add CLI test**

  In `tests/test_cli.py`, assert the command is registered and can print `market_status` and `fields.price_usd.status` for a seeded observation pair.

- [ ] **Step 3: Update architecture docs**

  In `src/parallax/domains/token_intel/ARCHITECTURE.md`, replace the Radar projection market observation sentence with:
  ```text
  Projection consumes `asset_market` current-market snapshots for scoring context. It does not read latest price-observation rows as a live market contract and does not call providers.
  ```
  In `docs/ARCHITECTURE.md`, extend the `asset_market` row:
  ```text
  Owns price observations and field-aware current market read models.
  ```
  In `docs/CONTRACTS.md`, document `/api/current-market` and `AssetFlowRow.current_market`.

- [ ] **Step 4: Verify docs/CLI focused tests**

  ```bash
  uv run pytest tests/test_cli.py tests/test_token_radar_audit_cli.py tests/test_docs_generated.py -q
  ```
  Expected: selected tests pass or `tests/test_docs_generated.py` skips only for its existing documented Postgres availability reason.

- [ ] **Step 5: Commit**

  ```bash
  git add src/parallax/app/surfaces/cli/main.py src/parallax/domains/token_intel/ARCHITECTURE.md docs/ARCHITECTURE.md docs/CONTRACTS.md tests/test_cli.py tests/test_token_radar_audit_cli.py
  git commit -m "docs: document current market boundary and audit path"
  ```

## PR Breakdown

1. **PR 1 — No-copy-forward hotfix**: Task 1 only. Mergeable alone; immediately stops new polluted observations.
2. **PR 2 — Current market read model**: Task 2. Mergeable alone; adds field-aware snapshots without changing product surfaces.
3. **PR 3 — Resolver and Radar scoring boundary**: Tasks 3 and 4. Depends on PR 2; moves resolver/Radar off latest-row semantics.
4. **PR 4 — API/frontend hard cut**: Task 5. Depends on PR 3; removes factor snapshot as live price source.
5. **PR 5 — Provider budget and ops docs**: Tasks 6 and 7. Can land after PR 1; best after PR 4 so audit matches final API contract.

## Rollout Order

1. Land PR 1 first to stop new `okx_dex_price` copy-forward pollution.
2. Land PR 2; run the GMGN-payload market-data prune migration so old payload prices do not remain in current-market facts or timing baselines.
3. Land PR 3; projection version bump creates fresh `token-radar-v10-current-market` rows.
4. Land PR 4; frontend/API hard cut to `current_market`.
5. Land PR 5; provider budget sharing and ops docs.
6. Restart service workers so `providers_wiring.py` uses the shared serialized DEX provider.
7. Run a production audit for `$TROLL`:
   ```bash
   uv run parallax current-market --target-type Asset --target-id 'asset:solana:token:5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2'
   ```
   Expected: price field can be fresh while market cap field shows stale until a full metadata source refreshes it.

## Rollback

- PR 1 rollback is safe but discouraged; reverting would reintroduce polluted observations.
- PR 2 rollback is safe before PR 3/4 because it only adds read code.
- PR 3 rollback requires resetting `TOKEN_RADAR_PROJECTION_VERSION` consumers to the previous version. Do not mix v10 projection rows with v9-only frontend code.
- PR 4 rollback requires rolling back frontend and backend API together because `price`/`market` aliases are intentionally removed.
- PR 5 rollback is safe for docs and provider sharing; if shared provider causes unexpected thread-safety issues, revert provider sharing while keeping no-copy-forward and current-market contracts.

Compensating action for polluted historical rows: no destructive SQL is required because current-market queries exclude `okx_dex_price` from market cap/liquidity/holders. Historical rows remain for audit.

## Acceptance Test Commands

- AC1:
  ```bash
  uv run pytest tests/test_asset_market_sync.py::test_sync_dex_prices_refreshes_active_dex_venues_in_batches tests/test_message_market_observation.py::test_message_market_observation_writes_dex_message_quote_per_message -q
  ```
  Expected: `okx_dex_price` observations have price only; market cap/liquidity/holders are `None`.

- AC2 and AC6:
  ```bash
  uv run pytest tests/test_current_market_repository.py::test_current_market_keeps_price_fresh_while_market_cap_stale tests/test_current_market_repository.py::test_current_market_updates_market_cap_from_full_metadata_provider -q
  ```
  Expected: current market distinguishes fresh price from stale market cap, then updates market cap only from full metadata.

- AC3 and AC7:
  ```bash
  uv run pytest tests/test_token_radar_projection.py -q
  ```
  Expected: projection consumes `repos.current_market`, keeps provider-free behavior, and writes field statuses into factor snapshot provenance.

- AC4 and AC8:
  ```bash
  npm test -- --run web/src/lib/tokenRadar.test.ts web/src/components/TokenRadarRow.test.tsx
  ```
  Expected: frontend reads live market from `current_market`, not factor snapshot market facts.

- AC5:
  ```bash
  uv run pytest tests/test_api_health.py -q
  ```
  Expected: provider errors/rate-limit-like worker failures appear in readiness provider state; current-market stale/missing status prevents high-alert freshness from being treated as fresh.

- AC9:
  ```bash
  uv run pytest tests/test_asset_ingest_flow.py tests/golden/test_token_radar_corpus.py -q
  ```
  Expected: tweet ingest/extraction/resolution works without provider calls in the synchronous path.

- AC10:
  ```bash
  uv run pytest tests/test_registry_repository.py::test_symbol_lookup_ignores_okx_price_only_market_metadata_for_dominance tests/test_deterministic_token_resolver.py::test_symbol_dominance_requires_field_freshness -q
  ```
  Expected: symbol dominance ignores price-only market metadata.

## Full Verification

Before declaring implementation complete:

```bash
uv run ruff check src tests
uv run pytest -q
uv run python -m compileall src tests
npm test -- --run
npm run build
```

Manual verification after Docker/service restart:

```bash
curl -s -H "Authorization: Bearer $WS_TOKEN" "http://localhost:8000/api/token-radar?window=5m&scope=all&limit=20" | jq '.data.targets[] | select(.target.symbol=="TROLL") | {target, current_market}'
curl -s -H "Authorization: Bearer $WS_TOKEN" "http://localhost:8000/api/current-market?target_type=Asset&target_id=asset:solana:token:5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2" | jq '.data'
curl -s "http://localhost:8000/readyz" | jq '.asset_market_sync.providers, .message_market_observation, .token_discovery'
```

Expected manual evidence:

- `current_market.fields.price_usd.status` can be `fresh`.
- `current_market.fields.market_cap_usd.status` is independently `fresh`, `stale`, or `missing`.
- Factor snapshot market facts do not act as frontend live price.
- Provider worker status is visible in `/readyz`.
