# Radar Candidate Market Hydration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make radar price freshness owned by the current radar candidate set, hard-cut the projection contract, and keep the mature token extraction/resolver state machine unchanged.

**Architecture:** Reuse existing tables and workers. Add a candidate-scoped DEX refresh selector to the registry repository, make the DEX sync worker consume that selector instead of the global active-registry queue, prioritize recent message/start quotes, and bump the radar projection version/read model to explicit market readiness semantics. No new worker, no new table, no resolver policy change.

**Tech Stack:** Python 3, PostgreSQL, existing OKX market clients, existing `price_observations`, `price_feeds`, `token_radar_rows`, pytest, ruff.

---

## File Structure

- Modify `src/gmgn_twitter_intel/pipeline/token_radar_contract.py`
  - Bump `TOKEN_RADAR_PROJECTION_VERSION` to the candidate-hydration hard-cut version.
  - Update `TOKEN_RADAR_SOURCE_TABLE` to include candidate-scoped hydration semantics.

- Modify `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
  - Keep resolver consumption unchanged.
  - Add explicit market readiness / event price readiness fields into `market_json`, `price_json`, and `data_health_json`.
  - Preserve no-driver behavior for stale/missing provider state.

- Modify `src/gmgn_twitter_intel/storage/registry_repository.py`
  - Add a repository selector for radar candidate assets needing price refresh.
  - Join current token intent resolutions and events so current social candidates outrank registry history.
  - Keep `chain_assets_needing_price_refresh` available for non-radar cold stewardship, but do not use it from the radar-critical DEX sync path.

- Modify `src/gmgn_twitter_intel/pipeline/asset_market_sync.py`
  - Replace the DEX price sync input universe with the new candidate-scoped selector.
  - Keep current address-search and token_prices write behavior.
  - Report candidate-scoped counters in the sync result.

- Modify `src/gmgn_twitter_intel/pipeline/message_market_observation.py`
  - Prioritize pending message/start quote rows by recent candidate windows before old backlog.
  - Keep source event/intent/resolution linkage unchanged.

- Modify tests:
  - `tests/test_token_radar_projection.py`
  - `tests/test_asset_market_sync.py`
  - `tests/test_message_market_observation.py`
  - `tests/test_registry_repository.py`
  - Contract assertions that reference the projection version.

- Add verification artifact:
  - `docs/superpowers/plans/2026-05-09-radar-candidate-market-hydration-verification.md`

---

### Task 1: Hard-Cut Projection Contract and Readiness Fields

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_contract.py`
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- Test: `tests/test_token_radar_projection.py`

- [x] **Step 1: Write failing tests for the hard-cut version and readiness fields**

Add assertions that:

```python
def test_token_radar_projection_uses_v7_candidate_hydration_contract():
    assert TOKEN_RADAR_PROJECTION_NAME == "token-radar"
    assert TOKEN_RADAR_PROJECTION_VERSION == "token-radar-v7-candidate-hydration"
    assert TOKEN_RADAR_SOURCE_TABLE == "token_intent_resolutions+candidate_market_hydration+price_observations"
    assert PROJECTION_VERSION == TOKEN_RADAR_PROJECTION_VERSION
```

Add a market readiness assertion to the existing market tests:

```python
assert market["market_readiness"]["status"] == "fresh"
assert market["market_readiness"]["observation_status"] == "ready"
assert market["event_price_readiness"]["status"] == "ready"
assert market["event_price_readiness"]["source"] == "message_or_history"
```

Add a stale/missing no-driver assertion:

```python
assert row["data_health_json"]["market"] == "pending_refresh"
assert row["data_health_json"]["market_readiness"]["status"] == "missing"
assert row["data_health_json"]["event_price_readiness"]["status"] == "missing"
```

- [x] **Step 2: Run the focused projection tests and verify they fail**

Run:

```bash
uv run pytest tests/test_token_radar_projection.py -q
```

Expected failure:

- version assertion still reports `token-radar-v6-auditable`;
- readiness keys are missing.

- [x] **Step 3: Implement the minimal projection contract change**

Change constants to:

```python
TOKEN_RADAR_PROJECTION_VERSION = "token-radar-v7-candidate-hydration"
TOKEN_RADAR_SOURCE_TABLE = "token_intent_resolutions+candidate_market_hydration+price_observations"
```

Add readiness helpers in `token_radar_projection.py`:

```python
def _market_readiness(market: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": market.get("market_status") or "missing",
        "observation_status": market.get("market_observation_status") or "missing",
        "provider": market.get("provider"),
        "snapshot_age_ms": market.get("snapshot_age_ms"),
        "snapshot_observed_at_ms": market.get("snapshot_observed_at_ms"),
    }


def _event_price_readiness(market: dict[str, Any]) -> dict[str, Any]:
    value = market.get("price_at_social_start")
    status = "ready" if value is not None else "missing"
    return {
        "status": status,
        "source": "message_or_history" if status == "ready" else market.get("price_change_status"),
        "social_signal_start_ms": market.get("social_signal_start_ms"),
        "price_at_social_start": value,
        "price_change_status": market.get("price_change_status"),
    }
```

Attach these blocks when returning `_market`, and mirror them into `data_health_json`.

- [x] **Step 4: Run projection tests and verify green**

Run:

```bash
uv run pytest tests/test_token_radar_projection.py -q
```

Expected: all tests in the file pass.

---

### Task 2: Candidate-Scoped DEX Refresh Universe

**Files:**
- Modify: `src/gmgn_twitter_intel/storage/registry_repository.py`
- Modify: `src/gmgn_twitter_intel/pipeline/asset_market_sync.py`
- Test: `tests/test_registry_repository.py`
- Test: `tests/test_asset_market_sync.py`

- [x] **Step 1: Write failing repository test**

Add an integration test that creates:

- one hot asset with current resolution in the last hour and stale/missing price;
- one old active registry asset with no current resolution;
- one demoted search asset with a current-looking symbol but no eligible status.

Expected:

```python
rows = registry.chain_assets_needing_radar_price_refresh(
    stale_before_ms=1_778_145_300_000,
    radar_since_ms=1_778_141_400_000,
    hot_since_ms=1_778_141_400_000,
    limit=10,
)
assert [row["asset_id"] for row in rows] == [hot_asset["asset_id"]]
```

- [x] **Step 2: Write failing sync test**

Update the fake registry in `tests/test_asset_market_sync.py` with both old and new selectors. Assert `sync_okx_dex_prices` calls the candidate-scoped selector:

```python
assert registry.radar_refresh_calls == [
    {
        "stale_before_ms": 1_778_084_800_000,
        "radar_since_ms": 1_777_998_700_000,
        "hot_since_ms": 1_778_081_500_000,
        "limit": 100,
    }
]
assert registry.global_refresh_calls == []
```

- [x] **Step 3: Run focused tests and verify red**

Run:

```bash
uv run pytest tests/test_registry_repository.py::test_radar_price_refresh_selects_current_candidates_not_cold_registry_assets tests/test_asset_market_sync.py::test_sync_okx_dex_prices_refreshes_active_dex_venues_in_batches -q
```

Expected: missing method / wrong selector failures.

- [x] **Step 4: Implement repository selector**

Add `RegistryRepository.chain_assets_needing_radar_price_refresh(...)` with this behavior:

- Select `registry_assets` joined to current `token_intent_resolutions` where `target_type = 'Asset'`.
- Join `events` and keep rows with `events.received_at_ms >= radar_since_ms`.
- Keep only `registry_assets.status IN ('candidate', 'canonical')`.
- Include assets whose latest price observation is missing or older than `stale_before_ms`.
- Group by asset and latest price fields.
- Order hot candidates first using `MAX(events.received_at_ms) >= hot_since_ms`, then newest mention first, then oldest/missing price.
- Return the same row shape currently consumed by `sync_okx_dex_prices`.

- [x] **Step 5: Implement candidate-scoped sync input**

In `sync_okx_dex_prices`, derive:

```python
radar_since_ms = int(observed_at_ms) - 24 * 60 * 60 * 1000
hot_since_ms = int(observed_at_ms) - 60 * 60 * 1000
```

Fetch rows from:

```python
registry.chain_assets_needing_radar_price_refresh(
    stale_before_ms=int(observed_at_ms) - int(stale_after_ms),
    radar_since_ms=radar_since_ms,
    hot_since_ms=hot_since_ms,
    limit=max(0, int(limit)),
)
```

Keep address-search, pricefeed writing, and price observation writing unchanged.

- [x] **Step 6: Run focused tests and verify green**

Run:

```bash
uv run pytest tests/test_registry_repository.py tests/test_asset_market_sync.py -q
```

Expected: both files pass.

---

### Task 3: Recent-First Message/Start Price Hydration

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/message_market_observation.py`
- Test: `tests/test_message_market_observation.py`

- [x] **Step 1: Write failing test for recent pending rows before old backlog**

Add a fake rows test that inspects SQL and params:

```python
result = observe_message_market(
    repos=repos,
    cex_client=None,
    dex_client=FakeDexClient([...]),
    now_ms=1_700_000_001_000,
    limit=10,
)
assert "events.received_at_ms >= %s" in repos.conn.sql
assert "ORDER BY" in repos.conn.sql
assert "DESC" in repos.conn.sql
assert repos.conn.params[-2] == 1_700_000_001_000 - 60 * 60 * 1000
assert repos.conn.params[-1] == 10
```

- [x] **Step 2: Run focused message tests and verify red**

Run:

```bash
uv run pytest tests/test_message_market_observation.py -q
```

Expected: SQL/params assertion fails because current selector is oldest-first.

- [x] **Step 3: Implement recent-first selector**

Change `_select_pending_rows` to receive `now_ms`, compute `hot_since_ms = now_ms - 60 * 60 * 1000`, and order by:

```sql
CASE WHEN events.received_at_ms >= %s THEN 0 ELSE 1 END,
events.received_at_ms DESC,
tir.resolution_id ASC
```

Keep the existing `NOT EXISTS` source-resolution dedupe and resolver policy filter.

- [x] **Step 4: Run message tests and verify green**

Run:

```bash
uv run pytest tests/test_message_market_observation.py -q
```

Expected: all message market observation tests pass.

---

### Task 4: Contract Cascade and Verification

**Files:**
- Modify tests that assert the projection contract.
- Add: `docs/superpowers/plans/2026-05-09-radar-candidate-market-hydration-verification.md`

- [x] **Step 1: Run targeted suite**

Run:

```bash
uv run pytest tests/test_token_radar_projection.py tests/test_asset_market_sync.py tests/test_message_market_observation.py tests/test_registry_repository.py tests/test_asset_flow_service.py tests/test_token_radar_audit_cli.py tests/golden/test_token_radar_corpus.py -q
```

Expected: pass after contract updates.

- [x] **Step 2: Run project verification**

Run:

```bash
uv run ruff check .
uv run pytest
uv run python -m compileall src tests
```

Expected: all pass.

- [x] **Step 3: Write verification artifact**

Create `docs/superpowers/plans/2026-05-09-radar-candidate-market-hydration-verification.md` with:

- commands run and results;
- diff summary;
- explicit note that resolver policy was not bumped;
- residual risks and follow-ups.

- [x] **Step 4: Review diff against spec**

Run:

```bash
git diff --stat
git diff -- docs/superpowers/specs/2026-05-09-radar-candidate-market-hydration.md docs/superpowers/plans/2026-05-09-radar-candidate-market-hydration.md src/gmgn_twitter_intel tests
```

Expected: implementation matches spec boundaries, with no extraction/resolver state machine rewrite and no legacy projection compatibility path.
