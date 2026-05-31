# Token Radar Hot Resolution and Market Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix Token Radar missing at the root by separating targetless identity diagnostics from tradable rows, prioritizing hot unresolved resolution refresh, and overlaying live market cache for resolved targets.

**Architecture:** Ingest remains local and deterministic. One resolution refresh worker handles symbol/address discovery, then synchronously runs the minimal downstream repair for hot windows: reprocess affected intents, observe anchor prices, and rebuild 5m/1h projections. The public read model filters targetless rows from main lists and overlays `LivePriceGateway` cache without provider calls.

**Tech Stack:** Python 3, FastAPI, PostgreSQL, pytest integration tests, React/TypeScript token-radar contract tests.

**Execution status:** Implemented on 2026-05-12. The final implementation also fixes the production-only US equity symbol collision root cause: symbol-only resolution now checks confirmed CEX first, confirmed US equity second, and DEX symbol registry third. No compatibility alias remains for the old token-discovery worker or CLI command.

**Production proof:** Docker was rebuilt, targeted `reprocess-token-intents` resolved 5 of 6 real US-equity sample intents, and `run-resolution-refresh --limit 120 --reprocess-limit 500` wrote 16 assets and reprocessed 57 intents with 53 resolved. Latest hot-window DB metrics after explicit rebuild: `5m/all identity_missing=2 nil=2 ambiguous=0 resolved=24`; `1h/all identity_missing=29 nil=28 ambiguous=1 resolved=250`. HTTP public payload has `public_targetless=0` for both 5m and 1h.

---

## File Structure

- Modify `src/parallax/domains/asset_market/repositories/discovery_repository.py`
  - Add hot-window lookup selection inputs and deterministic ordering.
- Modify `src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py`
  - Refactor existing worker behavior into the single ResolutionRefreshWorker concept.
  - Keep one worker, no hot/background split.
  - Add hot retry TTL and immediate downstream repair.
- Modify `src/parallax/domains/token_intel/runtime/token_resolution_refresh.py`
  - Expose a small hot-window rebuild helper for `5m/1h` only.
- Modify `src/parallax/domains/token_intel/read_models/asset_flow_service.py`
  - Filter public targetless rows and add unresolved diagnostics.
  - Overlay optional live market snapshots.
- Modify `src/parallax/app/surfaces/api/http.py`
  - Pass `runtime.live_price_gateway` into `AssetFlowService`.
- Modify `src/parallax/app/runtime/app.py`
  - Wire the refactored single worker if the class name changes.
- Test `tests/integration/test_resolution_refresh_worker.py`
  - Add hot retry and downstream repair coverage.
- Test `tests/integration/test_api_http.py`
  - Add public targetless filtering and live overlay coverage.
- Test `web/src/lib/tokenRadar.test.ts` only if backend payload contract changes require frontend derivation updates.

---

### Task 1: Lock Public API Semantics For Targetless Rows

**Files:**
- Modify: `src/parallax/domains/token_intel/read_models/asset_flow_service.py`
- Test: `tests/integration/test_api_http.py`

- [ ] **Step 1: Write failing API test for unresolved diagnostics**

Add an integration test that creates one resolved token and one unresolved symbol-only token, rebuilds radar, and asserts the unresolved row is absent from `targets` and `attention` but present in `projection.unresolved`.

```python
def test_token_radar_public_payload_keeps_targetless_rows_in_diagnostics(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)
    now_ms = 1_778_562_000_000

    with TestClient(app) as client:
        runtime = client.app.state.service
        runtime.ingest.ingest_event(
            make_token_event("event-pepe", symbol="PEPE", address=PEPE, text=f"$PEPE {PEPE}", received_at_ms=now_ms),
            is_watched=True,
        )
        runtime.ingest.ingest_event(
            make_event("event-unknown", text="$NEWTOKEN soon", received_at_ms=now_ms + 1_000, is_watched=True),
            is_watched=True,
        )
        rebuild_token_radar(client, now_ms=now_ms + 2_000)

        response = client.get(
            "/api/token-radar",
            params={"window": "5m", "scope": "all", "limit": 20},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    public_rows = [*data["targets"], *data["attention"]]
    assert public_rows
    assert all(row["target"]["target_id"] for row in public_rows)
    assert "NEWTOKEN" not in {row["target"]["symbol"] for row in public_rows}
    assert data["projection"]["unresolved"]["identity_missing_count"] >= 1
    assert "NEWTOKEN" in data["projection"]["unresolved"]["sample_symbols"]
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
uv run pytest tests/integration/test_api_http.py::test_token_radar_public_payload_keeps_targetless_rows_in_diagnostics -q
```

Expected before implementation: FAIL because targetless attention rows are returned publicly and `projection.unresolved` is missing.

- [ ] **Step 3: Implement public filtering and diagnostics**

In `AssetFlowService.asset_flow(...)`:

- Build `public_rows = [_public_row(row) for row in rows]`.
- Split `unresolved_rows = [row for row in public_rows if not row["target"].get("target_id")]`.
- Only include targetful rows in `targets` and `attention`.
- Add `projection.unresolved`.

Implementation shape:

```python
targetful_rows = [row for row in public_rows if row.get("target", {}).get("target_id")]
unresolved_rows = [row for row in public_rows if not row.get("target", {}).get("target_id")]
targets = [row for row in targetful_rows if row.get("_lane") == "resolved"]
attention = [row for row in targetful_rows if row.get("_lane") == "attention"]
```

Add helper:

```python
def _unresolved_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = [
        str(_mapping(row.get("target")).get("status") or _mapping(row.get("resolution")).get("status") or "")
        for row in rows
    ]
    symbols = []
    for row in rows:
        symbol = _mapping(row.get("target")).get("symbol") or _mapping(row.get("intent")).get("display_symbol")
        if symbol and symbol not in symbols:
            symbols.append(str(symbol))
    return {
        "identity_missing_count": len(rows),
        "nil_count": sum(1 for status in statuses if status == "NIL"),
        "ambiguous_count": sum(1 for status in statuses if status == "AMBIGUOUS"),
        "sample_symbols": symbols[:10],
    }
```

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest tests/integration/test_api_http.py::test_token_radar_public_payload_keeps_targetless_rows_in_diagnostics -q
```

Expected: PASS.

---

### Task 2: Overlay Live Market Cache In `/api/token-radar`

**Files:**
- Modify: `src/parallax/domains/token_intel/read_models/asset_flow_service.py`
- Modify: `src/parallax/app/surfaces/api/http.py`
- Test: `tests/integration/test_api_http.py`

- [ ] **Step 1: Write failing API test for live overlay**

Add a fake gateway object in the test and attach it to runtime before calling `/api/token-radar`.

```python
class FakeLiveGateway:
    def snapshot(self, *, target_type: str, target_id: str, now_ms: int | None = None):
        return {
            "target_type": target_type,
            "target_id": target_id,
            "status": "live",
            "price_usd": 0.123,
            "price_quote": None,
            "quote_symbol": "USD",
            "price_basis": "usd",
            "market_cap_usd": 123_000,
            "liquidity_usd": 45_000,
            "holders": 321,
            "volume_24h_usd": 9_000,
            "observed_at_ms": now_ms,
            "received_at_ms": now_ms,
            "age_ms": 0,
            "provider": "test_live",
        }
```

Test assertion:

```python
row = response.json()["data"]["targets"][0]
assert row["live_market"]["status"] == "live"
assert row["live_market"]["price_usd"] == 0.123
assert row["live_market"]["market_cap_usd"] == 123_000
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
uv run pytest tests/integration/test_api_http.py::test_token_radar_overlays_live_gateway_snapshot -q
```

Expected before implementation: FAIL because `AssetFlowService` always emits missing live market.

- [ ] **Step 3: Add optional live overlay**

Change constructor:

```python
class AssetFlowService:
    def __init__(self, *, token_radar: Any, live_market_gateway: Any | None = None) -> None:
        self.token_radar = token_radar
        self.live_market_gateway = live_market_gateway
```

After `_public_row(row)`, overlay only when target exists:

```python
def _overlay_live_market(row: dict[str, Any], *, gateway: Any | None, now_ms: int | None) -> dict[str, Any]:
    target = _mapping(row.get("target"))
    target_type = str(target.get("target_type") or "").strip()
    target_id = str(target.get("target_id") or "").strip()
    if gateway is None or not target_type or not target_id:
        return row
    snapshot = gateway.snapshot(target_type=target_type, target_id=target_id, now_ms=now_ms)
    return {**row, "live_market": {"target_type": target_type, "target_id": target_id, **_mapping(snapshot)}}
```

Wire in `http.py`:

```python
AssetFlowService(
    token_radar=repos.token_radar,
    live_market_gateway=runtime.live_price_gateway,
).asset_flow(...)
```

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest tests/integration/test_api_http.py::test_token_radar_overlays_live_gateway_snapshot -q
```

Expected: PASS.

---

### Task 3: Hot Lookup Selection And Retry TTL

**Files:**
- Modify: `src/parallax/domains/asset_market/repositories/discovery_repository.py`
- Modify: `src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py`
- Test: `tests/integration/test_resolution_refresh_worker.py`

- [ ] **Step 1: Write failing test for launch-race retry**

Test shape:

1. Ingest `$FLAPPYFARM`.
2. First refresh returns 0 candidates and writes `not_found`.
3. Advance 60 seconds, fake provider returns one candidate.
4. Run refresh again and assert lookup is retried despite previous `not_found`.
5. Assert intent resolves.

```python
def test_hot_symbol_not_found_retries_quickly_and_resolves_launch_race(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    now_ms = 1_778_561_100_000
    address = "0xfcb54d2b664f00f88587377e73c423bff2bf7777"
    try:
        migrate(conn)
        ingest = IngestService(
            evidence=EvidenceRepository(conn),
            entities=EntityRepository(conn),
            signals=SignalRepository(conn),
            enrichment=FakeEnrichment(),
        )
        ingested = ingest.ingest_event(
            make_event("event-flappyfarm", text="$FLAPPYFARM launch soon", received_at_ms=now_ms, is_watched=True),
            is_watched=True,
        )

        market = FakeDexMarket(candidates=[])
        worker = ResolutionRefreshWorker(
            repository_session=lambda: repository_session_for_connection(conn),
            dex_market=market,
            chain_ids=("eip155:56",),
            interval_seconds=60,
        )
        first = worker.run_once(now_ms=now_ms + 10_000)
        assert first["lookups_done"] == 1

        market.candidates = [
            DexTokenCandidate(
                chain_id="eip155:56",
                address=address,
                symbol="FLAPPYFARM",
                name="FlappyFarm",
                price_usd=0.00001,
                market_cap_usd=10_000,
                liquidity_usd=5_000,
                holders=50,
                community_recognized=False,
                raw={"tokenSymbol": "FLAPPYFARM"},
            )
        ]
        second = worker.run_once(now_ms=now_ms + 70_000)

        repos = repositories_for_connection(conn)
        resolution = repos.intent_resolutions.active_resolution_for_intent(
            ingested.token_intents[0]["intent_id"]
        )
    finally:
        conn.close()

    assert second["lookups_done"] == 1
    assert second["search_hits"] == 1
    assert second["reprocessed_intents"] == 1
    assert resolution["target_type"] == "Asset"
    assert resolution["target_id"] == f"asset:eip155:56:erc20:{address}"
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
uv run pytest tests/integration/test_resolution_refresh_worker.py::test_hot_symbol_not_found_retries_quickly_and_resolves_launch_race -q
```

Expected before implementation: FAIL because `not_found` refresh TTL is 5 minutes.

- [ ] **Step 3: Add hot selection inputs**

Update `DiscoveryRepository.due_lookup_keys(...)` signature:

```python
def due_lookup_keys(
    self,
    *,
    since_ms: int,
    now_ms: int,
    limit: int,
    hot_since_ms: int | None = None,
    hot_not_found_retry_ms: int | None = None,
) -> list[dict[str, Any]]:
```

In SQL, compute `is_hot`:

```sql
CASE WHEN recent_refresh_candidates.latest_seen_ms >= %s THEN 0 ELSE 1 END AS hot_priority
```

Allow hot not_found rows to be due earlier:

```sql
OR (
  %s IS NOT NULL
  AND recent_refresh_candidates.latest_seen_ms >= %s
  AND token_discovery_results.status = 'not_found'
  AND token_discovery_results.last_lookup_at_ms <= %s - %s
)
```

Order:

```sql
ORDER BY
  hot_priority ASC,
  recent_refresh_candidates.refresh_priority ASC,
  recent_refresh_candidates.latest_seen_ms DESC,
  ...
```

- [ ] **Step 4: Wire hot retry in worker**

In `run_resolution_refresh_once(...)`, pass:

```python
hot_since_ms = int(now_ms) - WINDOW_MS["1h"]
lookups = repos.discovery.due_lookup_keys(
    since_ms=since_ms,
    now_ms=now_ms,
    limit=lookup_limit,
    hot_since_ms=hot_since_ms,
    hot_not_found_retry_ms=60_000,
)
```

- [ ] **Step 5: Verify**

Run:

```bash
uv run pytest tests/integration/test_resolution_refresh_worker.py::test_hot_symbol_not_found_retries_quickly_and_resolves_launch_race -q
```

Expected: PASS.

---

### Task 4: Immediate Anchor And Hot Projection After Successful Refresh

**Files:**
- Modify: `src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py`
- Modify: `src/parallax/domains/token_intel/runtime/token_resolution_refresh.py`
- Test: `tests/integration/test_resolution_refresh_worker.py`

- [ ] **Step 1: Write failing test for downstream repair**

Extend the launch-race test or add a focused one that asserts after successful refresh:

```python
assert second["anchor"]["anchor_observations_written"] >= 1
assert second["projection"]["windows"]["5m:all"]["rows_written"] >= 1
```

Then query latest `token_radar_rows` and assert the target appears in resolved lane:

```python
rows = repos.token_radar.latest_rows(
    window="5m",
    scope="all",
    limit=20,
    projection_version=TOKEN_RADAR_PROJECTION_VERSION,
)
assert any(row["target_id"] == f"asset:eip155:56:erc20:{address}" for row in rows)
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
uv run pytest tests/integration/test_resolution_refresh_worker.py::test_hot_resolution_refresh_repairs_anchor_and_projection -q
```

Expected before implementation: FAIL because worker defers projection and does not call anchor observation.

- [ ] **Step 3: Add hot rebuild helper**

In `token_resolution_refresh.py`:

```python
def rebuild_hot_token_radar_windows(
    *,
    repos: Any,
    now_ms: int,
    limit: int = 100,
) -> dict[str, Any]:
    return rebuild_token_radar_windows(
        repos=repos,
        now_ms=now_ms,
        windows=("5m", "1h"),
        scopes=("all", "matched"),
        limit=limit,
    )
```

- [ ] **Step 4: Call anchor and hot projection after reprocess**

In `run_resolution_refresh_once(...)`, after `reprocess_recent_token_intents(...)`:

```python
if reprocess_result["resolved_intents"]:
    from parallax.domains.asset_market.services.anchor_price_observation import observe_anchor_prices
    from parallax.domains.token_intel.runtime.token_resolution_refresh import (
        rebuild_hot_token_radar_windows,
    )

    result["anchor"] = observe_anchor_prices(
        repos=repos,
        cex_market=None,
        dex_market=dex_market,
        now_ms=now_ms,
        limit=max(20, reprocess_result["resolved_intents"] * 2),
    )
    result["projection"] = rebuild_hot_token_radar_windows(
        repos=repos,
        now_ms=now_ms,
        limit=100,
    )
else:
    result["projection"] = deferred_token_radar_projection()
```

Keep this inside the existing single worker. Do not create another worker.

- [ ] **Step 5: Verify**

Run:

```bash
uv run pytest tests/integration/test_resolution_refresh_worker.py::test_hot_resolution_refresh_repairs_anchor_and_projection -q
```

Expected: PASS.

---

### Task 5: Rename Mental Model Without Compatibility Code

**Files:**
- Modify: `src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py`
- Modify: `src/parallax/app/runtime/app.py`
- Modify: `src/parallax/app/surfaces/cli/main.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 1: Rename class if it stays readable**

Preferred hard cut:

```python
class ResolutionRefreshWorker:
    ...
```

Do not keep a compatibility alias named `TokenDiscoveryWorker`.

Rename the CLI command to `run-resolution-refresh`; do not keep the old command as an alias. Internally, call `run_resolution_refresh_once(...)`.

- [ ] **Step 2: Update runtime wiring**

In `app.py`, instantiate `ResolutionRefreshWorker` for `runtime.resolution_refresh_worker`.

- [ ] **Step 3: Update tests imports**

Replace imports in tests:

```python
from parallax.domains.asset_market.runtime.resolution_refresh_worker import (
    ResolutionRefreshWorker,
)
```

- [ ] **Step 4: Verify CLI registration still works**

Run:

```bash
uv run pytest tests/integration/test_cli.py::TestCliParser::test_audit_and_token_radar_projection_commands_are_registered -q
```

Expected: PASS.

---

### Task 6: End-to-End Verification

**Files:**
- No new source files unless tests expose a narrow bug.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
uv run pytest \
  tests/integration/test_resolution_refresh_worker.py \
  tests/integration/test_api_http.py::test_token_radar_public_payload_keeps_targetless_rows_in_diagnostics \
  tests/integration/test_api_http.py::test_token_radar_overlays_live_gateway_snapshot \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend contract tests if payload changed**

Run:

```bash
cd web && npm test -- tokenRadar liveMarketUpdatePatch --runInBand
```

Expected: PASS.

- [ ] **Step 3: Rebuild Docker**

Run:

```bash
docker compose build app
docker compose up -d
```

Expected: app container healthy.

- [ ] **Step 4: Run one explicit refresh on real data**

Run:

```bash
docker compose exec -T app uv run parallax ops run-resolution-refresh --limit 120 --reprocess-limit 500
docker compose exec -T app uv run parallax ops rebuild-token-radar --window 5m --scope all --limit 300
docker compose exec -T app uv run parallax ops rebuild-token-radar --window 1h --scope all --limit 300
```

Expected:

- Hot lookup result includes reprocess/projection details.
- `FLAPPYFARM` remains resolved if still in window.
- Public `/api/token-radar` rows have target ids.

- [ ] **Step 5: Record production metrics**

Run:

```sql
WITH latest AS (
  SELECT "window", scope, MAX(computed_at_ms) AS computed_at_ms
  FROM token_radar_rows
  WHERE projection_version = 'token-radar-v13-social-attention'
    AND scope = 'all'
    AND "window" IN ('5m','1h')
  GROUP BY "window", scope
),
rows AS (
  SELECT r.*
  FROM token_radar_rows r
  JOIN latest l
    ON l."window" = r."window"
   AND l.scope = r.scope
   AND l.computed_at_ms = r.computed_at_ms
)
SELECT
  "window",
  COUNT(*) AS persisted_rows,
  COUNT(*) FILTER (WHERE target_type IS NULL) AS persisted_identity_missing,
  COUNT(*) FILTER (WHERE target_type IS NOT NULL AND data_health_json->>'market'='missing') AS resolved_market_missing
FROM rows
GROUP BY "window"
ORDER BY "window";
```

Expected:

- Persisted diagnostics may remain non-zero.
- API public rows should have zero targetless rows.
- Resolved market missing should decrease when live overlay/anchor is available.

---

## Self-Review

- Spec coverage: covers identity missing, market missing, hot retry, post-resolution anchor, hot projection, public targetless filtering, and live cache overlay.
- KISS check: one worker concept, no frontend/provider search, no ingest network calls, no compatibility alias required.
- Risk: class rename creates churn; mitigate by updating imports, runtime field, CLI help, and focused tests in the same commit.
