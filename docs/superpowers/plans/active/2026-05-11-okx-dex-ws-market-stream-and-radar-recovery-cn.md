# OKX DEX WS Market Stream and Token Radar Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore reliable Token Radar data for all public windows and add OKX DEX WebSocket `price-info` as a clean metadata-capable realtime market provider.

**Architecture:** First fix local read-model performance and explicit projection coverage so `/api/token-radar` is bounded and honest. Coverage is a status row, not a `token_radar_rows` row-count inference: a computed empty window is ready; absent/running/failed coverage is pending. Then add OKX DEX WS behind `asset_market` provider contracts, write `okx_dex_ws_price_info` observations, and push backend `/ws market_update` deltas to the frontend.

**Tech Stack:** Python 3.13, FastAPI, PostgreSQL/Alembic, psycopg, websockets, React/Vite, pytest, ruff.

---

## Pre-flight

- [ ] Spec is approved: `docs/superpowers/specs/active/2026-05-11-okx-dex-ws-market-stream-and-radar-recovery-cn.md`.
- [ ] Create worktree: `git worktree add .worktrees/okx-dex-ws-market-stream -b codex/okx-dex-ws-market-stream main`.
- [ ] In worktree, verify `git branch --show-current` prints `codex/okx-dex-ws-market-stream`.
- [ ] Run baseline: `uv run ruff check .`.
- [ ] Run baseline: `uv run pytest tests/test_current_market_repository.py tests/test_token_radar_projection_worker.py tests/test_asset_market_sync.py tests/test_api_websocket.py -q`.

Known production finding before implementation:

- `price_observations` had about 1.75m rows; stale statistics and field-filtered lateral queries caused `current_market` hydrate to take tens of seconds.
- `token-radar-v10-current-market` initially had only `5m` rows; after diagnostic `ANALYZE`, `1h:all` backfilled, proving worker/query performance is the immediate zero-data root.
- Hard rule for this implementation: no fallback to old projection versions, no factor-snapshot market alias compatibility, and no browser-direct OKX WebSocket. Current-version coverage and `current_market.fields` are the only public path.

Live implementation amendment after 2026-05-11 verification:

- `/api/token-radar` must not hydrate `current_market` during the request path. HTTP returns the projection row's persisted market facts; live changes arrive through backend WebSocket `market_update` deltas.
- `TokenRadarSourceQuery` must not read historical `price_observations` through per-row LATERAL joins. Projection market context comes from `current_market` hydration only; historical event-price deltas are intentionally absent instead of being a slow compatibility layer.
- The source query materializes the bounded `events.received_at_ms` window with the event columns needed by scoring, then resolves intents through the current resolver row. Do not rejoin the full `events` table after materialization.
- `24h/all` analysis lookback is capped at 48h. This preserves the current and previous 24h windows while avoiding 7-day source scans that can starve hot `5m` refreshes.
- Coverage readiness and projection-run completion are committed atomically. Rows without `ready` coverage are not considered public-ready, even if `token_radar_rows` contains partial output.

## Required Amendments From Engineering Review

- Add a persistent `token_radar_projection_coverage` read-model table keyed by `(projection_version, window, scope)`. It stores `status`, `reason`, `source_rows`, `row_count`, `computed_at_ms`, `started_at_ms`, `finished_at_ms`, and `error`.
- Do not infer missing coverage from `COUNT(*) FROM token_radar_rows`. Zero rows can mean a correctly computed empty window.
- `/api/token-radar` must read coverage before deciding `projection.status`. `ready + row_count=0` returns `fresh` with empty rows. Missing/running/failed coverage returns `pending` with a reason.
- `TokenRadarProjectionWorker` must prioritize coverage gaps and open a fresh repository session per window/scope. A slow or failed background window must not hide already completed windows.
- Migration indexes on `price_observations` must use `CREATE INDEX CONCURRENTLY` in an Alembic autocommit block. Run `ANALYZE` as rollout ops after migration, not as a long transaction side effect.
- Do not hardcode `token-radar-v10-current-market` outside token-intel constants/interfaces. Stream target queries take the current projection version as a parameter.
- Sweep all current-market-like provider filters, including search/registry reads, so `okx_dex_ws_price_info` is metadata-capable everywhere `current_market` semantics apply.
- The frontend must send visible/resolved `market_targets` in the backend `/ws` subscribe payload; handling `market_update` without subscribing is not enough.

## File-Level Edits

### Storage / Migrations

- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260511_0024_price_observation_field_indexes.py`.

```python
from __future__ import annotations

from alembic import op

revision = "20260511_0024"
down_revision = "20260510_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_price
        ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
        WHERE provider IN ('gmgn_payload', 'okx_dex_search', 'okx_dex_price', 'okx_dex_ws_price_info', 'okx_cex')
          AND (price_usd IS NOT NULL OR price_quote IS NOT NULL)
        """
    )
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_market_cap
        ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
        WHERE provider IN ('gmgn_payload', 'okx_dex_search', 'okx_dex_ws_price_info')
          AND market_cap_usd IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_liquidity
        ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
        WHERE provider IN ('gmgn_payload', 'okx_dex_search', 'okx_dex_ws_price_info')
          AND liquidity_usd IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_holders
        ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
        WHERE provider IN ('gmgn_payload', 'okx_dex_search', 'okx_dex_ws_price_info')
          AND holders IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_volume_24h
        ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
        WHERE provider IN ('okx_cex', 'gmgn_payload', 'okx_dex_search', 'okx_dex_ws_price_info')
          AND volume_24h_usd IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_open_interest
        ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
        WHERE provider = 'okx_cex'
          AND open_interest_usd IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_subject_first
        ON price_observations(subject_type, subject_id, observed_at_ms ASC, observation_id ASC)
        """
    )
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_message_resolution_latest
        ON price_observations(source_resolution_id, subject_type, subject_id, observation_kind, observed_at_ms DESC, observation_id DESC)
        WHERE observation_kind IN ('message_payload', 'message_quote')
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_projection_coverage (
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          status TEXT NOT NULL,
          reason TEXT,
          source_rows BIGINT NOT NULL DEFAULT 0,
          row_count BIGINT NOT NULL DEFAULT 0,
          computed_at_ms BIGINT,
          started_at_ms BIGINT,
          finished_at_ms BIGINT,
          error TEXT,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(projection_version, "window", scope)
        )
        """
    )


def downgrade() -> None:
    for name in (
        "idx_price_observations_message_resolution_latest",
        "idx_price_observations_subject_first",
        "idx_price_observations_current_open_interest",
        "idx_price_observations_current_volume_24h",
        "idx_price_observations_current_holders",
        "idx_price_observations_current_liquidity",
        "idx_price_observations_current_market_cap",
        "idx_price_observations_current_price",
    ):
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
    op.execute("DROP TABLE IF EXISTS token_radar_projection_coverage")
```

- Modify: `tests/test_postgres_schema.py`.
  - Add assertions that migration text contains each `idx_price_observations_current_*` index.
  - Add assertion that metadata indexes include `okx_dex_ws_price_info`.
  - Add assertion that `token_radar_projection_coverage` exists.
  - Add assertion that indexes are created/dropped concurrently.

### `src/gmgn_twitter_intel/domains/asset_market/market_field_facts.py`

- Add constants:

```python
PROVIDER_OKX_DEX_WS_PRICE_INFO = "okx_dex_ws_price_info"
```

- Update provider sets:

```python
PRICE_CAPABLE_PROVIDERS = frozenset({
    "gmgn_payload",
    "okx_dex_search",
    "okx_dex_price",
    "okx_dex_ws_price_info",
    "okx_cex",
})
DEX_METADATA_CAPABLE_PROVIDERS = frozenset({
    "gmgn_payload",
    "okx_dex_search",
    "okx_dex_ws_price_info",
})
CEX_MARKET_CAPABLE_PROVIDERS = frozenset({"okx_cex"})
```

### `src/gmgn_twitter_intel/domains/asset_market/repositories/current_market_repository.py`

- Replace literal provider lists with imported provider-set constants when building SQL.
- Keep one query shape and field-aware lateral reads, but ensure SQL includes `okx_dex_ws_price_info` only for price/DEX metadata/volume fields, not open interest.
- Add helper:

```python
def _sql_list(values: frozenset[str]) -> str:
    return ", ".join("'" + value + "'" for value in sorted(values))
```

### `tests/test_current_market_repository.py`

- Add test:

```python
def test_current_market_reads_okx_dex_ws_price_info_as_metadata_provider(tmp_path):
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
            provider="okx_dex_ws_price_info",
            pricefeed_id="feed-ws",
            observed_at_ms=1_700_086_420_000,
            subject_type=SUBJECT_TYPE,
            subject_id=SUBJECT_ID,
            price_usd=0.111,
            price_basis="usd",
            market_cap_usd=110_900_000,
            liquidity_usd=4_820_000,
            volume_24h_usd=27_400_000,
            holders=57_141,
        )
        snapshot = CurrentMarketRepository(conn).current_for_subjects(
            [{"target_type": SUBJECT_TYPE, "target_id": SUBJECT_ID}],
            now_ms=1_700_086_430_000,
        )[(SUBJECT_TYPE, SUBJECT_ID)]
    finally:
        conn.close()

    assert snapshot["fields"]["price_usd"]["value"] == 0.111
    assert snapshot["fields"]["market_cap_usd"]["value"] == 110_900_000
    assert snapshot["fields"]["liquidity_usd"]["value"] == 4_820_000
    assert snapshot["fields"]["holders"]["value"] == 57_141
    assert snapshot["fields"]["market_cap_usd"]["provider"] == "okx_dex_ws_price_info"
```

### `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`

- Add coverage method:

```python
def latest_coverage(self, *, projection_version: str, windows: tuple[str, ...], scopes: tuple[str, ...]) -> dict[tuple[str, str], dict[str, Any]]:
    rows = self.conn.execute(
        """
        SELECT "window", scope, status, reason, source_rows, row_count, computed_at_ms, error
        FROM token_radar_projection_coverage
        WHERE projection_version = %s
          AND "window" = ANY(%s)
          AND scope = ANY(%s)
        """,
        (projection_version, list(windows), list(scopes)),
    ).fetchall()
    return {
        (str(row["window"]), str(row["scope"])): {
            "row_count": int(row["row_count"] or 0),
            "source_rows": int(row["source_rows"] or 0),
            "status": str(row["status"]),
            "reason": row.get("reason"),
            "computed_at_ms": int(row["computed_at_ms"]) if row["computed_at_ms"] is not None else None,
            "error": row.get("error"),
        }
        for row in rows
    }
```

- Add `mark_coverage(...)` with an upsert into `token_radar_projection_coverage`.
- `TokenRadarProjection.rebuild(...)` must mark `running` before the source query and `ready` only after `token_radar_rows` replacement commits. On failure, the worker marks `failed` in a separate session.

### `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py`

- Change `rebuild_once(...)` so each window/scope is isolated:
  - Determine missing current-version windows from `repos.token_radar.latest_coverage(...)`.
  - Prioritize missing windows before normal round-robin background work.
  - Open a repository session per window/scope so one slow background query does not hide completed hot windows.
  - Update `last_result` after each window, not only after the whole batch.

- Add helper:

```python
def _missing_work_items(self, coverage: dict[tuple[str, str], dict[str, Any]]) -> list[tuple[str, str]]:
    return [
        (window, scope)
        for window in self.windows
        for scope in self.scopes
        if str((coverage.get((window, scope)) or {}).get("status") or "") != "ready"
    ]
```

### `tests/test_token_radar_projection_worker.py`

- Replace `test_token_radar_projection_worker_rebuilds_all_windows_and_scopes` with two tests:
  - `test_projection_worker_prioritizes_missing_current_version_windows`
  - `test_projection_worker_records_partial_window_results_before_background_failure`
  - `test_projection_worker_does_not_rebuild_ready_empty_windows`

Minimum fake repository shape:

```python
class FakeTokenRadar:
    def __init__(self, coverage):
        self.coverage = coverage

    def latest_coverage(self, *, projection_version, windows, scopes):
        return dict(self.coverage)


class FakeRepos:
    def __init__(self, coverage):
        self.token_radar = FakeTokenRadar(coverage)
```

Expected first-call order when only `5m:all` exists:

```python
assert calls[:3] == [
    {"window": "5m", "scope": "matched", "now_ms": 1_777_800_000_000, "limit": 7},
    {"window": "1h", "scope": "all", "now_ms": 1_777_800_000_000, "limit": 7},
    {"window": "1h", "scope": "matched", "now_ms": 1_777_800_000_000, "limit": 7},
]
```

### `src/gmgn_twitter_intel/domains/asset_market/providers.py`

- Add streaming value types:
- Add `from collections.abc import AsyncIterator`; keep the existing `typing` imports for `Any` and `Protocol`.

```python
@dataclass(frozen=True, slots=True)
class DexMarketStreamTarget:
    chain_id: str
    address: str
    subject_type: str
    subject_id: str
    pricefeed_id: str | None = None


@dataclass(frozen=True, slots=True)
class DexMarketFactUpdate:
    chain_id: str
    address: str
    observed_at_ms: int
    price_usd: float | None
    market_cap_usd: float | None
    liquidity_usd: float | None
    volume_24h_usd: float | None
    holders: int | None
    raw: dict[str, Any]


class DexMarketStreamProvider(Protocol):
    async def stream_price_info(self, targets: list[DexMarketStreamTarget]) -> AsyncIterator[DexMarketFactUpdate]:
        raise NotImplementedError
```

### `src/gmgn_twitter_intel/integrations/okx/dex_ws_client.py`

- Create async client with:
  - `connect -> login -> subscribe -> ping loop -> yield price-info updates`.
  - HMAC signature: `timestamp + "GET" + "/users/self/verify"`.
  - Plain text `"ping"` every 25 seconds and expect `"pong"`.
  - Reconnect on close, timeout, `notice`, or non-zero login/subscribe error.

### `tests/test_okx_dex_ws_client.py`

- Add unit tests with fake websocket:
  - `test_okx_dex_ws_login_uses_expected_signature_prehash`
  - `test_okx_dex_ws_price_info_normalizes_market_fields`
  - `test_okx_dex_ws_unauthenticated_error_is_surfaceable`

### `src/gmgn_twitter_intel/domains/asset_market/runtime/dex_market_stream_worker.py`

- Create worker:
  - Reads hot resolved DEX targets from a new registry method.
  - Enforces `subscription_limit`.
  - Calls stream provider.
  - Upserts `dex_token` pricefeed with provider `okx_dex_ws_price_info`.
  - Inserts `price_observations` with field-capable values.
  - Calls optional `on_market_update` after commit.

### `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py`

- Read `token_radar.latest_coverage(...)` before `latest_rows(...)`.
- If coverage is absent/running/failed, return `targets=[]`, `attention=[]`, `projection.status="pending"`, and a specific `projection.reason`.
- If coverage is `ready`, return rows normally. `ready + zero rows` is a valid fresh empty projection.
- Keep the hard cut: do not read older projection versions and do not derive public market fields from factor snapshots.

### `src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py`

- Add query method:

```python
def active_dex_market_stream_targets(self, *, projection_version: str, since_ms: int, limit: int) -> list[dict[str, Any]]:
    rows = self.conn.execute(
        """
        WITH latest_rows AS (
          SELECT DISTINCT ON (token_radar_rows.target_id)
            token_radar_rows.target_id AS asset_id,
            token_radar_rows."window",
            token_radar_rows.scope,
            token_radar_rows.lane,
            token_radar_rows.rank,
            token_radar_rows.computed_at_ms,
            token_radar_rows.source_max_received_at_ms
          FROM token_radar_rows
          WHERE token_radar_rows.projection_version = %s
            AND token_radar_rows.target_type = 'Asset'
            AND token_radar_rows.computed_at_ms >= %s
          ORDER BY
            token_radar_rows.target_id,
            CASE token_radar_rows."window" WHEN '5m' THEN 0 WHEN '1h' THEN 1 WHEN '4h' THEN 2 ELSE 3 END,
            CASE token_radar_rows.lane WHEN 'resolved' THEN 0 ELSE 1 END,
            token_radar_rows.rank ASC,
            token_radar_rows.computed_at_ms DESC
        )
        SELECT
          registry_assets.asset_id,
          registry_assets.chain_id,
          registry_assets.address,
          latest_rows."window",
          latest_rows.scope,
          latest_rows.lane,
          latest_rows.rank,
          latest_rows.computed_at_ms,
          latest_rows.source_max_received_at_ms
        FROM latest_rows
        JOIN registry_assets ON registry_assets.asset_id = latest_rows.asset_id
        WHERE registry_assets.address IS NOT NULL
          AND registry_assets.status IN ('candidate', 'canonical')
        ORDER BY
          CASE latest_rows."window" WHEN '5m' THEN 0 WHEN '1h' THEN 1 WHEN '4h' THEN 2 ELSE 3 END,
          CASE latest_rows.lane WHEN 'resolved' THEN 0 ELSE 1 END,
          latest_rows.rank ASC,
          latest_rows.computed_at_ms DESC
        LIMIT %s
        """,
        (projection_version, int(since_ms), max(0, int(limit))),
    ).fetchall()
    return [dict(row) for row in rows]
```

Use current `TOKEN_RADAR_PROJECTION_VERSION` rows, resolved `Asset` targets, and registry chain/address fields. Order by latest rank window priority: `5m` before `1h`, resolved lane before attention, rank ascending, latest computed time descending.

- Update existing registry/search market lateral provider filters to include `okx_dex_ws_price_info` for DEX metadata fields and price, while keeping `okx_dex_price` price-only.

### `src/gmgn_twitter_intel/app/runtime/providers_wiring.py`

- Wire `OkxDexWebSocketMarketProvider` separately from REST `OkxDexMarketProvider`.
- Do not put WS methods on the REST provider.
- Reuse OKX DEX credentials from settings.

### `src/gmgn_twitter_intel/platform/config/settings.py`

- Add fields to `OkxProviderConfig`:

```python
dex_ws_enabled: bool = False
dex_ws_url: str = "wss://wsdex.okx.com/ws/v6/dex"
dex_ws_subscription_limit: int = Field(default=100, gt=0)
dex_ws_hot_target_ttl_seconds: float = Field(default=300.0, gt=0)
dex_ws_reconnect_delay_seconds: float = Field(default=3.0, gt=0)
```

- Add property:

```python
@property
def okx_dex_ws_configured(self) -> bool:
    return bool(
        self.providers.okx.dex_ws_enabled
        and self.okx_dex_api_key
        and self.okx_dex_secret_key
        and self.okx_dex_passphrase
    )
```

### `src/gmgn_twitter_intel/app/surfaces/api/ws.py`

- Extend `ClientSubscription`:

```python
market_targets: set[tuple[str, str]] = field(default_factory=set)
```

- Parse optional `market_targets` in subscribe messages.
- Match `market_update` payloads by explicit `market_targets`, subscribed CA, or subscribed symbol.

### `web/src/api/useIntelSocket.ts`

- Extend live payload handling:

```ts
if (payload.type === "market_update") {
  setMarketUpdates((current) => [payload as MarketUpdatePayload, ...current].slice(0, 200));
  return;
}
```

- Extend hook options with `marketTargets`.
- Include `market_targets` in subscribe payloads.

### `web/src/App.tsx`

- Build visible `marketTargets` from current Token Radar rows.
- Pass them into `useIntelSocket(...)`.
- On market update, patch React Query cache entries for visible `["token-radar", windowKey, scope]` rows where `target.target_type + target.target_id` matches.
- Keep 10 second HTTP refetch as baseline reconciliation.

## PR Breakdown

1. **PR 1 — projection and current-market recovery**
   - Migration indexes.
   - Current market provider set update.
   - Token Radar worker coverage priority.
   - API pending semantics if rows are missing.
   - Tests: current market, migration schema, projection worker, API HTTP.

2. **PR 2 — OKX DEX WS provider**
   - Integration client.
   - Domain stream provider types.
   - Stream worker.
   - Settings and wiring.
   - Tests: WS client, stream worker, settings, providers wiring.

3. **PR 3 — backend/frontend live market updates**
   - `/ws market_update` contract.
   - Runtime publisher callback.
   - Frontend socket handling and query-cache patch.
   - Tests: API websocket, frontend token radar live patch.

## Rollout Order

1. Apply PR 1 migration.
2. Run `ANALYZE price_observations; ANALYZE token_intent_resolutions; ANALYZE token_intents; ANALYZE events;` once after migration.
3. Rebuild current projection windows: `uv run gmgn-twitter-intel ops rebuild-token-radar --window 5m --scope all`, repeat for all public windows/scopes if the CLI supports one pair at a time.
4. Deploy PR 1 and verify `/api/token-radar` for all windows.
5. Deploy PR 2 with `providers.okx.dex_ws_enabled: false`.
6. Enable DEX WS on one environment with `dex_ws_subscription_limit: 20`.
7. Verify TROLL and other hot targets receive `okx_dex_ws_price_info`.
8. Deploy PR 3 frontend live patch.
9. Increase subscription limit gradually.

## Rollback

- PR 1 indexes can remain in place safely; if needed, run downgrade to drop them. Do not roll back to old projection version in public API.
- PR 2 can be disabled by setting `providers.okx.dex_ws_enabled: false`.
- PR 3 frontend can keep HTTP polling; if market-update payloads fail, backend can stop publishing `market_update` while clients continue polling.

## Acceptance Test Commands

- AC1:
  ```bash
  uv run pytest tests/test_okx_dex_ws_client.py::test_okx_dex_ws_price_info_normalizes_market_fields tests/test_asset_market_stream_worker.py::test_stream_worker_writes_okx_dex_ws_price_info_observation -q
  ```

- AC2:
  ```bash
  uv run pytest tests/test_current_market_repository.py::test_current_market_keeps_price_fresh_while_market_cap_stale tests/test_current_market_repository.py::test_current_market_reads_okx_dex_ws_price_info_as_metadata_provider -q
  ```

- AC3:
  ```bash
  uv run pytest tests/test_token_radar_projection_worker.py -q
  ```

- AC4:
  ```bash
  uv run gmgn-twitter-intel ops audit-token-radar --window 1h --scope all
  curl -s 'http://127.0.0.1:8765/api/token-radar?window=1h&scope=all&limit=48' -H "Authorization: Bearer $TOKEN" | jq '.data.projection.status,.data.targets|length'
  ```
  Expected: status is `fresh` or `pending`; request completes below the configured timeout; after backfill target length is non-zero when source rows exist.

- AC5:
  ```bash
  npm --prefix web test -- TokenRadar
  uv run pytest tests/test_api_websocket.py::test_websocket_routes_market_update_when_subscribed -q
  ```

- AC6:
  ```bash
  uv run pytest tests/test_okx_dex_ws_client.py::test_okx_dex_ws_reconnects_and_resubscribes_after_notice -q
  ```

## Verification

- Before completion, create `docs/superpowers/plans/active/2026-05-11-okx-dex-ws-market-stream-and-radar-recovery-verification.md`.
- Required commands:
  - `uv run ruff check .`
  - `uv run pytest`
  - `uv run python -m compileall src tests`
  - `npm --prefix web test`
  - Docker smoke: `/api/status`, `/api/token-radar` for `5m/1h/4h/24h` x `all/matched`.
  - Live OKX WS smoke with credentials, printing no secrets.
