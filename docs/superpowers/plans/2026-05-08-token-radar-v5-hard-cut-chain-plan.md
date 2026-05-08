# Token Radar V5 Hard-Cut Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Token Radar from the current partially-auditable v4 projection into a v5 auditable trading radar with no v4 projection fallback, no `price_health` compatibility path, and no frontend inference that hides missing backend data.

**Architecture:** Keep the current deterministic identity resolver as the identity policy, but hard-cut the read model contract. The ingest/resolution/registry chain remains the source of truth; `price_observations` becomes the single market ledger for refresh prices and message-linked prices; `TokenRadarProjection` becomes the only scorer and calls the mature scoring modules directly; API and frontend consume only `token-radar-v5-auditable`.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic, FastAPI, React/TypeScript, existing repository/session pattern, `uv run pytest`, `uv run ruff check .`, `uv run python -m compileall src tests`, `cd web && npm test -- --runInBand`.

---

## Current Chain Audit

### Ingest And Identity

Current path:

1. `collector/normalizer.py` attaches `TwitterEvent.token_snapshot` when GMGN payload contains token `t`.
2. `pipeline/ingest_service.py` writes `events`, deterministic entities, token evidence, token intents.
3. `TokenIntentResolver` calls `DeterministicTokenResolver`.
4. Current resolver policy is `token_radar_v4_deterministic_resolver`.
5. Resolution rows write `target_type`, `target_id`, and optional `pricefeed_id`.

Decision: keep resolver policy as-is. This is not compatibility code; it is the current identity policy. The hard cut is the radar projection/read contract, not identity migration.

### Price Ledger

Current path:

1. `IngestService._insert_gmgn_payload_price_observation()` writes GMGN payload price only when event has token snapshot and resolution matches the payload asset.
2. `asset_market_sync.py` writes periodic OKX CEX/DEX refresh observations.
3. `token_discovery_worker.py` writes discovery/search observations.
4. `price_observations` lacks message attribution columns.

Problem: target latest price exists, but message-level price does not. The current table cannot answer “this tweet resolved to this token, what price did we observe for that message, and with what lag?”

### Projection

Current path:

1. `TokenRadarProjectionWorker` rebuilds all windows/scopes through `TokenRadarProjection`.
2. discovery/reprocess also calls `rebuild_token_radar_windows()`, which uses the same projection class.
3. `TokenRadarProjection.PROJECTION_VERSION` is `token-radar-v4`.
4. `_score()` is a local heuristic and returns `price_health`.
5. mature scoring modules are not used by production projection.
6. `_market()` is called with the latest row only, so simply adding social-start fields to source SQL would still use the wrong row for social start.

Decision: hard-cut `TokenRadarProjection` itself. Once this class is v5, worker, discovery reprocess, CLI rebuild, and API all move together.

### Read API

Current path:

1. `/api/token-radar` calls `AssetFlowService`.
2. `AssetFlowService` calls `TokenRadarRepository.latest_rows()` without version.
3. `TokenRadarRepository.latest_rows()` defaults to `token-radar-v4`.
4. `ProjectionRepository.KNOWN_PROJECTIONS` and `PostgresQueryAudit` also reference v4.

Problem: these are hidden compatibility/default paths. v5 must require explicit projection version and audit v5 only.

### Timeline And Posts

Current path:

1. `/api/target-social-timeline` calls `TokenTargetSocialTimelineService`.
2. It reads `TokenTargetRepository.timeline_rows()`.
3. Buckets set `price = None`.
4. Posts use simple `45 + confidence * 35` quality.
5. `/api/target-posts` uses the same rows but also has simple quality and no price.

Decision: both timeline and posts must expose message price and use `post_quality_score`. Updating only timeline would leave the drawer/posts tab half-finished.

### Frontend

Current path:

1. `web/src/api/types.ts` still includes `price_health`.
2. `web/src/App.tsx::tokenRadarRowToTokenItem()` maps `row.score.price_health` into `tradeability`.
3. Default score versions are `token_radar_v4`.
4. opportunity components read `components.price_health`.
5. market status treats stale as usable.

Decision: remove these paths. Frontend should require v5 `score.tradeability`; it must not translate legacy `price_health`.

## No Compatibility Rules

- Do not keep `token-radar-v4` as a query default anywhere in active runtime code.
- Do not keep `score.price_health` in backend JSON, frontend types, test fixtures, notification payload fixtures, or mapper code.
- Do not keep `_score_block()`, old `_score()`, `_decision()`, or `_market_usable_for_driver()` in `token_radar_projection.py`.
- Do not add a “try v5, fallback v4” read path.
- Do not add frontend fallback from `price_health` to `tradeability`.
- Do not mark stale/missing market as driver-eligible.
- Do not compute social-start market fields from the latest row in a group.
- Do not update `web/dist`; it is a build artifact and should not be part of this source change.

Allowed v4 string:

- `token_radar_v4_deterministic_resolver` remains in resolver-related code/tests because it names the deterministic identity policy. This is not the projection/scoring compatibility path.

## Data-Flow Invariants

These invariants prevent the v5 cutover from becoming another partially-auditable read model.

1. `events`, `token_intents`, `token_intent_resolutions`, and `price_observations` are facts. `token_radar_rows` is disposable projection state.
2. A message price belongs to the current `source_resolution_id + target_type + target_id + pricefeed_id`, not just `source_intent_id`. If an intent is re-resolved, the new current resolution needs its own message price.
3. Projection freshness has two source clocks: social/identity facts from `token_intent_resolutions` and market facts from `price_observations`. A projection can be socially fresh but market-stale; health must expose both.
4. Price deltas are valid only when price basis is comparable. Do not compare `price_quote` values across different quote symbols or compare unavailable basis to USD basis.
5. `social_signal_start_ms` is the earliest event in the projected window for that target. It is not the latest row and not the first observation ever stored.
6. External provider calls must not run inside a long database transaction. Select work, release transaction, call provider, then upsert idempotent observations.
7. CEX and DEX remain separate targets. A shared project layer can be added later, but v5 rows do not aggregate across `CexToken` and `Asset`.

## Task 1: Centralize V5 Contract Constants And Remove V4 Defaults

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/token_radar_contract.py`
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/storage/token_radar_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/projection_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/postgres_audit.py`
- Modify: `src/gmgn_twitter_intel/retrieval/asset_flow_service.py`
- Modify: `src/gmgn_twitter_intel/cli.py`
- Modify tests that assert v4 projection names.

- [ ] **Step 1: Add contract constants**

Create:

```python
from __future__ import annotations

TOKEN_RADAR_PROJECTION_NAME = "token-radar"
TOKEN_RADAR_PROJECTION_VERSION = "token-radar-v5-auditable"
TOKEN_RADAR_SOURCE_TABLE = "token_intent_resolutions+price_observations"
TOKEN_RADAR_SCORE_COMPONENTS = ("heat", "quality", "propagation", "tradeability", "timing", "opportunity")
```

- [ ] **Step 2: Update projection to import constants**

Replace local `PROJECTION_VERSION = "token-radar-v4"` with:

```python
from .token_radar_contract import TOKEN_RADAR_PROJECTION_NAME, TOKEN_RADAR_PROJECTION_VERSION, TOKEN_RADAR_SOURCE_TABLE

PROJECTION_VERSION = TOKEN_RADAR_PROJECTION_VERSION
```

Use `TOKEN_RADAR_PROJECTION_NAME` and `TOKEN_RADAR_SOURCE_TABLE` in projection run/offset writes. `source_table` is intentionally composite because v5 projection depends on both social identity and market facts.

- [ ] **Step 3: Remove repository default projection version**

Change:

```python
def latest_rows(..., projection_version: str = "token-radar-v4") -> list[dict[str, Any]]:
```

to:

```python
def latest_rows(self, *, window: str, scope: str, limit: int, projection_version: str) -> list[dict[str, Any]]:
```

This intentionally breaks any caller that does not choose the v5 contract.

- [ ] **Step 4: Update all active callers**

Update:

```python
rows = self.token_radar.latest_rows(
    window=window,
    scope=scope,
    limit=row_limit,
    projection_version=TOKEN_RADAR_PROJECTION_VERSION,
)
```

Update `tests/test_token_discovery_worker.py` and golden corpus tests that call `latest_rows()` directly. These tests must pass v5 explicitly or be renamed/deleted if they only validate old v3/v4 projection behavior.

- [ ] **Step 5: Update operational audit strings**

Change:

- `ProjectionRepository.KNOWN_PROJECTIONS`
- `PostgresQueryAudit` `token_radar_latest`
- CLI `ops rebuild-token-radar` help text
- `AssetFlowService` projection metadata

All must report `token-radar-v5-auditable`.

- [ ] **Step 6: Verify no active v4 projection default remains**

Run:

```bash
rg -n "token-radar-v4|price_health|token_radar_v4" src/gmgn_twitter_intel web/src tests -S
```

Expected allowed matches only:

- `token_radar_v4_deterministic_resolver`
- migration filenames or resolver tests that explicitly validate identity policy.

- [ ] **Step 7: Commit**

```bash
git add src/gmgn_twitter_intel tests web/src
git commit -m "feat: hard cut token radar projection contract to v5"
```

## Task 2: Extend Price Observations Into Message Price Ledger

**Files:**
- Create: `src/gmgn_twitter_intel/storage/alembic/versions/20260508_0011_event_price_observations.py`
- Modify: `src/gmgn_twitter_intel/storage/price_observation_repository.py`
- Modify: `tests/test_postgres_schema.py`
- Create: `tests/test_price_observation_repository.py`

- [ ] **Step 1: Write schema test**

Assert migration text contains:

```python
assert "source_event_id" in text
assert "source_intent_id" in text
assert "source_resolution_id" in text
assert "observation_kind" in text
assert "event_received_at_ms" in text
assert "observation_lag_ms" in text
assert "idx_price_observations_source_event" in text
assert "idx_price_observations_subject_time_kind" in text
```

- [ ] **Step 2: Add migration**

Add columns:

```sql
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS source_event_id TEXT REFERENCES events(event_id) ON DELETE SET NULL;
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS source_intent_id TEXT REFERENCES token_intents(intent_id) ON DELETE SET NULL;
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS source_resolution_id TEXT REFERENCES token_intent_resolutions(resolution_id) ON DELETE SET NULL;
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS observation_kind TEXT NOT NULL DEFAULT 'refresh';
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS event_received_at_ms BIGINT;
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS observation_lag_ms BIGINT;
CREATE INDEX IF NOT EXISTS idx_price_observations_source_event ON price_observations(source_event_id);
CREATE INDEX IF NOT EXISTS idx_price_observations_source_intent ON price_observations(source_intent_id);
CREATE INDEX IF NOT EXISTS idx_price_observations_subject_time_kind ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_kind);
```

- [ ] **Step 3: Update insert API**

Add arguments:

```python
source_event_id: str | None = None,
source_intent_id: str | None = None,
source_resolution_id: str | None = None,
observation_kind: str = "refresh",
event_received_at_ms: int | None = None,
```

Compute:

```python
observation_lag_ms = (
    max(0, int(observed_at_ms) - int(event_received_at_ms))
    if event_received_at_ms is not None
    else None
)
```

Add these fields to `INSERT` and conflict update.

- [ ] **Step 4: Change observation id inputs**

Current id only keys by provider/feed/subject/time. Change stable id to include:

```python
observation_kind,
source_event_id or "",
source_intent_id or "",
source_resolution_id or "",
provider,
pricefeed_id or "",
subject_type,
subject_id,
str(observed_at_ms),
```

This avoids message quote colliding with refresh quote at the same timestamp.

- [ ] **Step 5: Add baseline read methods**

Add:

```python
def first_for_subject(self, *, subject_type: str, subject_id: str) -> dict[str, Any] | None: ...
def latest_for_subject_at_or_before(self, *, subject_type: str, subject_id: str, at_or_before_ms: int) -> dict[str, Any] | None: ...
def latest_message_for_event(self, *, event_id: str, subject_type: str, subject_id: str) -> dict[str, Any] | None: ...
```

Do not delete `latest_for_subject`; callers can migrate later or use the new name. This is not v4 compatibility because it is generic repository API.

- [ ] **Step 6: Verify**

Run:

```bash
uv run pytest tests/test_postgres_schema.py tests/test_price_observation_repository.py -q
```

Expected: pass.

## Task 3: Store GMGN Payload As Message Payload Price

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/ingest_service.py`
- Modify: `tests/test_asset_ingest_flow.py` or existing GMGN payload ingest tests.

- [ ] **Step 1: Write failing ingest test**

Seed a GMGN token payload event using `tests.factories.make_token_event()`. After `IngestService.ingest_event()`, assert the matching observation has:

```python
assert observation["observation_kind"] == "message_payload"
assert observation["source_event_id"] == event.event_id
assert observation["source_intent_id"] in {row["intent_id"] for row in result.token_intents}
assert observation["source_resolution_id"] in {row["resolution_id"] for row in result.token_resolutions}
assert observation["event_received_at_ms"] == event.received_at_ms
assert observation["observation_lag_ms"] == 0
```

- [ ] **Step 2: Change ingest call shape**

Replace:

```python
self._insert_gmgn_payload_price_observation(event, decisions)
```

with:

```python
self._insert_gmgn_payload_price_observation(event, token_resolutions)
```

Update `_insert_gmgn_payload_price_observation()` to iterate persisted resolution rows, not `DeterministicResolution` decisions, because decisions do not carry `resolution_id`.

- [ ] **Step 3: Insert message attribution**

Call:

```python
self.price_observations.insert_observation(
    provider="gmgn_payload",
    pricefeed_id=str(pricefeed["pricefeed_id"]),
    observed_at_ms=event.received_at_ms,
    subject_type="Asset",
    subject_id=str(asset["asset_id"]),
    price_usd=snapshot.price,
    price_basis="usd" if snapshot.price is not None else "unavailable",
    market_cap_usd=snapshot.market_cap,
    liquidity_usd=_raw_number(snapshot.raw, "liquidity", "liq", "pool_liquidity"),
    volume_24h_usd=_raw_number(snapshot.raw, "volume_24h", "v24h", ("stat", "volume_24h")),
    holders=_raw_int(snapshot.raw, "holder_count", "holders"),
    source_event_id=event.event_id,
    source_intent_id=str(resolution["intent_id"]),
    source_resolution_id=str(resolution["resolution_id"]),
    observation_kind="message_payload",
    event_received_at_ms=event.received_at_ms,
    raw_payload={**snapshot.raw, "payload_hash": _payload_hash(snapshot.raw)},
    commit=False,
)
```

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest tests/test_asset_ingest_flow.py -q
```

Expected: pass.

## Task 4: Add Missing Message Quote Worker

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/message_market_observation.py`
- Create: `src/gmgn_twitter_intel/pipeline/message_market_observation_worker.py`
- Modify: `src/gmgn_twitter_intel/market/okx_cex_client.py`
- Modify: `src/gmgn_twitter_intel/api/app.py`
- Create: `tests/test_message_market_observation.py`
- Modify: `tests/test_api_health.py`

- [ ] **Step 1: Add OKX CEX single ticker method**

Add:

```python
def ticker(self, *, inst_id: str) -> OkxCexTicker | None:
    rows = self._get("/api/v5/market/ticker", params={"instId": inst_id.strip().upper()})
    for row in rows:
        ticker = _ticker_from_row(row)
        if ticker is not None:
            return ticker
    return None
```

- [ ] **Step 2: Write observer tests**

Use a fake repository object with `conn.execute()` rows or a real PostgreSQL test DB. Required assertions:

```python
assert result["rows_selected"] == 1
assert result["observations_written"] == 1
assert observation["observation_kind"] == "message_quote"
assert observation["source_event_id"] == "event-1"
assert observation["source_intent_id"] == "intent-1"
assert observation["source_resolution_id"] == "resolution-1"
assert observation["observation_lag_ms"] == 1_000
```

Write one CEX case and one DEX Asset case.

- [ ] **Step 3: Implement selection query**

Select current resolved rows with no existing message observation for the current resolution and target:

```sql
SELECT ...
FROM token_intent_resolutions tir
JOIN events ON events.event_id = tir.event_id
LEFT JOIN registry_assets ...
LEFT JOIN cex_tokens ...
LEFT JOIN price_feeds ...
WHERE tir.is_current = true
  AND tir.target_type IN ('Asset', 'CexToken')
  AND tir.target_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM price_observations po
    WHERE po.source_resolution_id = tir.resolution_id
      AND po.subject_type = tir.target_type
      AND po.subject_id = tir.target_id
      AND COALESCE(po.pricefeed_id, '') = COALESCE(tir.pricefeed_id, '')
      AND po.observation_kind IN ('message_payload', 'message_quote')
  )
ORDER BY events.received_at_ms ASC, tir.resolution_id ASC
LIMIT %s
```

Do not filter only by `source_intent_id`; an intent can be re-resolved from `NIL` or one target to another target.

- [ ] **Step 4: Implement CEX write**

For `CexToken`, require `native_market_id`. If missing, increment `skipped_missing_pricefeed`; do not invent a feed. Dedupe quote fetches by `pricefeed_id` within one worker batch, then insert one observation per message so every message has its own `source_event_id/source_resolution_id`. Insert `message_quote` with provider `okx_cex`, quote/usd fields, and lag.

- [ ] **Step 5: Implement DEX write**

For `Asset`, require chain/address. Batch calls to `dex_client.token_prices()`. Dedupe provider calls by chain/address, then insert one observation per message. Insert `message_quote` with provider `okx_dex_price` and lag.

- [ ] **Step 6: Add worker lifecycle**

Add runtime fields in `CliRuntime` for worker/task/client, start it when CEX sync or DEX is configured, stop/close it in `_stop_runtime()`, and expose:

```json
"message_market_observation": {
  "worker_running": true,
  "last_run_at_ms": 1700000000000,
  "last_result": {"observations_written": 12},
  "last_error": null
}
```

- [ ] **Step 7: Verify**

Run:

```bash
uv run pytest tests/test_message_market_observation.py tests/test_api_health.py -q
```

Expected: pass.

## Task 5: Build Group-Aware V5 Radar Features

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/token_radar_feature_builder.py`
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- Create: `tests/test_token_radar_feature_builder.py`

- [ ] **Step 1: Define data model**

Create:

```python
@dataclass(frozen=True, slots=True)
class RadarFeatureSet:
    window_rows: list[dict[str, Any]]
    context_rows: list[dict[str, Any]]
    previous_rows: list[dict[str, Any]]
    attention: dict[str, Any]
    heat: dict[str, Any]
    quality: dict[str, Any]
    propagation: dict[str, Any]
    tradeability: dict[str, Any]
    timing: dict[str, Any]
```

- [ ] **Step 2: Change projection source scope**

In `rebuild()` compute:

```python
window_ms = WINDOW_MS.get(window, WINDOW_MS["1h"])
score_since_ms = computed_at_ms - window_ms
analysis_since_ms = min(computed_at_ms - WINDOW_MS["24h"], score_since_ms - window_ms)
```

Pass both to `_source_rows()`. Source rows include enough data to compute current window, previous same-length window, and 24h context. Only groups with at least one `window_row` are projected.

- [ ] **Step 3: Extend `_source_rows()` selected fields**

Add selected columns:

- `events.text`
- `events.text_clean`
- `events.reference_json`
- `token_intents.intent_confidence`
- `token_intents.primary_evidence_id`
- message price fields from `price_observations` if available
- `latest_price` for reference market
- `first_price` for first snapshot
- per-row `event_price` at or before event time
- per-row `before_event_price` before event time

- [ ] **Step 4: Build window/context/previous rows**

For each group:

```python
window_rows = [row for row in rows if int(row["received_at_ms"]) >= score_since_ms]
previous_rows = [
    row for row in rows
    if score_since_ms - window_ms <= int(row["received_at_ms"]) < score_since_ms
]
context_rows = rows
```

If `window_rows` is empty, skip the group.

- [ ] **Step 5: Compute attention correctly**

`mentions_5m`, `mentions_1h`, `mentions_4h`, `mentions_24h` must count unique event ids from `context_rows` within each interval, not reuse `len(event_ids)` for every label. Also compute `stream_share` using the total distinct token-intent event count for the same window/scope before grouping; do not leave it at `0`.

- [ ] **Step 6: Use existing text quality functions**

Use `post_quality_score()` and `post_text_features()` for quality features. Do not keep the temporary `45 + confidence * 35` formula in radar feature builder.

- [ ] **Step 7: Compute social baseline**

Set:

```python
previous_mentions = len({row["event_id"] for row in previous_rows})
mention_delta = mentions - previous_mentions
new_burst_score = mentions if previous_mentions == 0 and mentions > 0 else 0
```

No EWMA is added in this phase. Missing EWMA stays auditable through `insufficient_baseline` in `social_heat_score`.

- [ ] **Step 8: Verify feature tests**

Run:

```bash
uv run pytest tests/test_token_radar_feature_builder.py -q
```

Expected: pass.

## Task 6: Replace Projection Scoring With Mature Score Modules

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/retrieval/tradeability_scoring.py`
- Modify: `tests/test_token_radar_projection.py`
- Modify: `tests/test_tradeability_scoring.py`

- [ ] **Step 1: Update tradeability for CEX and DEX**

Branch by `target_type`:

- `Asset`: requires `resolved_ca`, `token_id`, `chain`, `address`.
- `CexToken`: requires `resolved_cex`, `token_id`, `pricefeed_id`, `native_market_id`.

CEX scoring must not require chain/address/pool/market cap. Asset scoring must not require CEX venue.

- [ ] **Step 2: Delete old projection scoring functions**

Delete active use and definitions of:

- `_score_block`
- old `_score`
- `_decision`
- `_market_usable_for_driver`
- `_market_risk`

Do not keep them renamed or unused.

- [ ] **Step 3: Import mature modules**

```python
from ..retrieval.discussion_quality_scoring import discussion_quality_score
from ..retrieval.opportunity_scoring import opportunity_score
from ..retrieval.propagation_scoring import propagation_score
from ..retrieval.social_heat_scoring import social_heat_score
from ..retrieval.timing_scoring import timing_score
from ..retrieval.tradeability_scoring import tradeability_score
```

- [ ] **Step 4: Build score set**

```python
components = {
    "heat": social_heat_score(features.heat),
    "quality": discussion_quality_score(features.quality),
    "propagation": propagation_score(features.propagation),
    "tradeability": tradeability_score(features.tradeability),
    "timing": timing_score(features.timing),
}
score = {**components, "opportunity": opportunity_score(components)}
decision = score["opportunity"]["decision"]
```

- [ ] **Step 5: Assert no legacy score key**

Add tests:

```python
assert set(row["score_json"]) == {"heat", "quality", "propagation", "tradeability", "timing", "opportunity"}
assert "price_health" not in row["score_json"]
for block in row["score_json"].values():
    assert block["score_version"]
    assert block["contributions"]
```

- [ ] **Step 6: Verify**

Run:

```bash
uv run pytest tests/test_token_radar_projection.py tests/test_tradeability_scoring.py tests/test_social_heat_scoring.py tests/test_discussion_quality_scoring.py tests/test_propagation_scoring.py tests/test_timing_scoring.py tests/test_opportunity_scoring.py -q
```

Expected: pass.

## Task 7: Compute Market Baselines From The Correct Rows

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- Modify: `tests/test_token_radar_projection.py`

- [ ] **Step 1: Change `_market()` signature**

Change from:

```python
def _market(row: dict[str, Any], *, resolved: bool, now_ms: int) -> dict[str, Any]:
```

to:

```python
def _market(window_rows: list[dict[str, Any]], *, resolved: bool, now_ms: int) -> dict[str, Any]:
```

This prevents using latest row as social start.

- [ ] **Step 2: Select row roles**

Inside `_market()`:

```python
latest = max(window_rows, key=lambda row: int(row.get("received_at_ms") or 0))
social_start = min(window_rows, key=lambda row: int(row.get("received_at_ms") or 0))
```

Use `latest.latest_price` fields for reference, `social_start.event_price` for social start, `social_start.before_event_price` for before-social, and `latest.first_price` for first snapshot.

- [ ] **Step 3: Compute pct changes**

Use one helper:

```python
def _pct_change(current: Any, base: Any) -> float | None:
    current_value = _float_or_none(current)
    base_value = _float_or_none(base)
    if current_value is None or base_value is None or base_value == 0:
        return None
    return round(current_value / base_value - 1.0, 6)
```

- [ ] **Step 4: Status contract**

Set:

- `market_observation_status = "ready"` only when latest reference price is fresh.
- `market_observation_status = "stale"` when latest exists but age exceeds SLA.
- `price_change_status = "ready"` only when reference and social-start prices exist.
- `price_change_status = "insufficient_history"` when latest exists but social-start baseline is missing.
- `price_change_status = "missing_market"` when no latest price exists.

Stale remains visible in market but `tradeability_score` caps it; no driver eligibility workaround.

- [ ] **Step 5: Enforce comparable price basis**

Add:

```python
def _comparable_price(current: dict[str, Any], base: dict[str, Any]) -> tuple[Any, Any, str]:
    if current.get("price_usd") is not None and base.get("price_usd") is not None:
        return current["price_usd"], base["price_usd"], "usd"
    current_quote = current.get("quote_symbol")
    base_quote = base.get("quote_symbol")
    if current_quote and base_quote and current_quote == base_quote:
        return current.get("price_quote"), base.get("price_quote"), f"quote:{current_quote}"
    return None, None, "basis_mismatch"
```

If basis mismatches, set the pct change to `None` and `price_change_status = "basis_mismatch"`.

- [ ] **Step 6: Test multi-row social start**

Create a projection test with two rows in the same group:

- earliest event price = `1.00`
- latest event price = `1.40`
- latest reference price = `1.50`

Assert:

```python
assert market["price_at_social_start"] == 1.00
assert market["price_at_reference"] == 1.50
assert market["price_change_since_social_pct"] == 0.5
```

- [ ] **Step 7: Verify**

Run:

```bash
uv run pytest tests/test_token_radar_projection.py -q
```

Expected: pass.

## Task 8: Update Timeline And Posts To Use Message Prices

**Files:**
- Modify: `src/gmgn_twitter_intel/storage/token_target_repository.py`
- Modify: `src/gmgn_twitter_intel/retrieval/token_target_social_timeline_service.py`
- Modify: `src/gmgn_twitter_intel/retrieval/token_target_posts_service.py`
- Create: `src/gmgn_twitter_intel/retrieval/token_message_price_payload.py`
- Modify: `tests/test_token_target_social_timeline_service.py`
- Modify tests for `TokenTargetPostsService`.

- [ ] **Step 1: Add shared price payload builder**

Create:

```python
MESSAGE_PRICE_FRESH_MS = 5 * 60 * 1000

def message_price_payload(row: dict[str, Any]) -> dict[str, Any]:
    observation_id = row.get("price_observation_id")
    if not observation_id:
        return {
            "status": "pending_observation",
            "provider": None,
            "pricefeed_id": row.get("pricefeed_id"),
            "price_usd": None,
            "price_quote": None,
            "quote_symbol": row.get("quote_symbol"),
            "observed_at_ms": None,
            "observation_lag_ms": None,
            "observation_id": None,
        }
    lag = row.get("price_observation_lag_ms")
    status = "stale" if lag is not None and int(lag) > MESSAGE_PRICE_FRESH_MS else "ready"
    return {
        "status": status,
        "provider": row.get("price_provider"),
        "pricefeed_id": row.get("pricefeed_id"),
        "price_usd": row.get("price_usd"),
        "price_quote": row.get("price_quote"),
        "quote_symbol": row.get("price_quote_symbol") or row.get("quote_symbol"),
        "observed_at_ms": row.get("price_observed_at_ms"),
        "observation_lag_ms": lag,
        "observation_id": observation_id,
    }
```

- [ ] **Step 2: Extend timeline rows SQL**

Add LATERAL `message_price` join on `source_event_id`, `subject_type`, and `subject_id`, preferring `message_payload` over `message_quote`.

- [ ] **Step 3: Add price to timeline posts**

`TokenTargetSocialTimelineService._post()` returns:

```python
"price": message_price_payload(row)
```

- [ ] **Step 4: Add price to target posts**

`TokenTargetPostsService._post()` also returns:

```python
"price": message_price_payload(row)
```

Use `post_quality_score()` instead of the temporary quality formula.

- [ ] **Step 5: Add bucket price overlay**

`_buckets()` sets bucket `price` from the last post price in the bucket and computes `price_change_from_start_pct` from the first bucket with price.

- [ ] **Step 6: Verify**

Run:

```bash
uv run pytest tests/test_token_target_social_timeline_service.py -q
```

Expected: pass.

## Task 9: Remove Frontend Legacy Mapping

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/ScoreLedger.tsx`
- Modify: `web/src/components/TokenRadarRow.tsx`
- Modify: `web/src/components/TokenTimeline.tsx`
- Modify: `web/src/components/TokenPostsTab.tsx`
- Modify: `web/src/App.test.tsx`
- Modify: `web/src/components/TokenRadarRow.test.tsx`

- [ ] **Step 1: Remove legacy score types**

Delete:

```ts
price_health?: TokenRadarScoreBlock;
price_health?: number | null;
```

Require:

```ts
tradeability?: TokenRadarScoreBlock;
tradeability?: number | null;
```

- [ ] **Step 2: Remove v4 mapper fallbacks**

Replace:

```ts
normalizedScoreBlock(row.score?.price_health, "token_radar_v4")
```

with:

```ts
normalizedScoreBlock(row.score?.tradeability, "tradeability_v2")
```

Then remove all references to `priceHealth`.

- [ ] **Step 3: Stop deriving backend features**

`tokenRadarRowToTokenItem()` should copy backend score extras, not reconstruct quality/propagation/tradeability from attention counts. For each component, prefer fields already present in the score payload:

```ts
const heat = normalizedScoreBlock(row.score?.heat, "social_heat_v2") as SocialHeatBlock;
const quality = normalizedScoreBlock(row.score?.quality, "discussion_quality_v2") as DiscussionQualityBlock;
const propagation = normalizedScoreBlock(row.score?.propagation, "propagation_v2") as PropagationBlock;
const tradeability = normalizedScoreBlock(row.score?.tradeability, "tradeability_v2") as TradeabilityBlock;
```

Do not read `opportunity.components.price_health`.

- [ ] **Step 4: Add first snapshot fields**

Add to market types and mapper:

```ts
price_at_first_snapshot?: number | null;
first_snapshot_observed_at_ms?: number | null;
price_change_since_first_snapshot_pct?: number | null;
```

- [ ] **Step 5: Add message price fields**

Add `price` to `TokenTimelinePost` and `TokenPostItem` using the backend contract.

- [ ] **Step 6: Update UI**

`TokenRadarRow` displays:

1. social-start delta if present.
2. first-snapshot delta if social delta is absent.
3. market status otherwise.

`ScoreLedger` shows `tradeability`, never `price_health`.

`TokenTimeline` and `TokenPostsTab` show message price status. If price is absent, display `pending_observation`; do not display “price snapshot missing” as if the feature is not implemented.

- [ ] **Step 7: Verify no legacy frontend strings**

Run:

```bash
rg -n "price_health|token_radar_v4|token-radar-v4" web/src -S
```

Expected: no matches.

- [ ] **Step 8: Verify frontend tests**

Run:

```bash
cd web && npm test -- --runInBand
```

Expected: pass.

## Task 10: Add Token Secondary Page Without Replacing Drawer

**Files:**
- Create: `web/src/components/TokenTargetPage.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`
- Modify: `web/src/App.test.tsx`

- [ ] **Step 1: Add page component**

Component props:

```ts
type TokenTargetPageProps = {
  token: TokenFlowItem;
  timeline: TokenSocialTimelineData | null;
  posts: TokenPostsData | null;
  onBack: () => void;
};
```

Sections:

- target header with identity, venue, latest price.
- market ledger with first snapshot, social start, latest reference.
- timeline with bucket prices.
- posts with tweet, post quality, message price, observation lag.
- score ledger with all score components.

- [ ] **Step 2: Wire app state**

Add:

```ts
const [selectedTokenPageKey, setSelectedTokenPageKey] = useState<string | null>(null);
```

Use existing selected token queries. Do not add a router dependency in this task.

- [ ] **Step 3: Add row action**

Add a compact “open page” action on radar row. Drawer remains quick inspect; secondary page is full audit view.

- [ ] **Step 4: Verify responsive behavior**

Use existing frontend tests first, then browser QA if server is running.

## Task 11: Update Notifications And CLI Audit To V5

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/notification_rules.py`
- Modify: `tests/test_notification_rules.py`
- Modify: `src/gmgn_twitter_intel/cli.py`
- Create: `tests/test_token_radar_audit_cli.py`

- [ ] **Step 1: Update notification fixtures**

`radar_score()` test fixture uses:

```python
"score_version": "social_opportunity_v3"
```

and components:

```python
"tradeability": 80
```

No fixture contains `price_health`.

- [ ] **Step 2: Add audit command**

Add:

```bash
gmgn-twitter-intel ops audit-token-radar --window 5m --scope all --limit 100
```

It fails nonzero when:

- any row has `score_json.price_health`
- any required component missing
- any score block has empty `contributions`
- any driver has stale/missing market
- projection version is not `token-radar-v5-auditable`
- projection social source is fresh but market source has no observation within market SLA

Audit output must include separate source freshness:

```json
{
  "source_max_resolution_ms": 1700000000000,
  "source_max_price_observed_at_ms": 1700000005000,
  "social_lag_ms": 1200,
  "market_lag_ms": 700
}
```

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest tests/test_notification_rules.py tests/test_token_radar_audit_cli.py -q
```

Expected: pass.

## Task 12: Hard-Cut Regression Sweep

**Files:**
- Modify only files needed to remove legacy references found by the sweep.

- [ ] **Step 1: Search active source**

Run:

```bash
rg -n "price_health|token-radar-v4|token_radar_v4" src/gmgn_twitter_intel web/src tests -S
```

Allowed matches:

- `token_radar_v4_deterministic_resolver`
- resolver policy tests
- migration filenames/schema tests that refer to historical migration files

No active projection, API, frontend, notification, or audit code may match `price_health` or `token-radar-v4`.

- [ ] **Step 2: Run backend targeted tests**

Run:

```bash
uv run pytest tests/test_token_radar_projection.py tests/test_token_radar_feature_builder.py tests/test_tradeability_scoring.py tests/test_price_observation_repository.py tests/test_message_market_observation.py tests/test_token_target_social_timeline_service.py tests/test_notification_rules.py -q
```

Expected: pass.

- [ ] **Step 3: Run full backend tests**

Run:

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

Expected: pass.

- [ ] **Step 4: Run frontend tests**

Run:

```bash
cd web && npm test -- --runInBand
```

Expected: pass.

- [ ] **Step 5: Rebuild and audit local radar**

Run:

```bash
uv run gmgn-twitter-intel ops rebuild-token-radar --window 5m --scope all --limit 100
uv run gmgn-twitter-intel asset-flow --window 5m --scope all --limit 20
uv run gmgn-twitter-intel ops audit-token-radar --window 5m --scope all --limit 100
```

Expected:

- projection version is `token-radar-v5-auditable`
- `score_json` has `tradeability`, not `price_health`
- every score block has contributions
- market fields expose social-start and first-snapshot deltas when observations exist
- stale/missing market cannot be driver
- timeline posts include message price status

## Execution Notes

- Implement tasks in order. Task 1 intentionally breaks callers so hidden v4 defaults surface immediately.
- Do not keep old branches “temporarily”; tests should be updated in the same task that changes the contract.
- Do not update old docs except this plan/spec unless a test reads them.
- Do not edit `web/dist`.
- If a test currently exists only to validate v3/v4 projection behavior, delete or rewrite it for v5 rather than preserving a compatibility adapter.

## Self-Review

- Spec coverage: mature scoring, message price ledger, social/first snapshot deltas, CEX/DEX separation, token timeline/page, market page delta, and audit command are all covered.
- Current chain coverage: ingest, resolver, price observations, market sync/discovery, projection worker, repository defaults, API, notification rules, timeline/posts, and frontend mapper are all explicitly addressed.
- No compatibility code: the plan removes v4 projection defaults, removes `price_health`, forbids frontend fallback, and requires a grep gate.
- Known exception: `token_radar_v4_deterministic_resolver` remains only as the identity resolver policy name.
