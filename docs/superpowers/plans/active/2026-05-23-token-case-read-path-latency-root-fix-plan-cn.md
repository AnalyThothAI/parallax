# Token Case Read Path Latency Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/token/:targetType/:targetId` and `/api/token-case` reliably fast by removing request-time provider calls, reducing duplicated read work, and bounding the background DB load that currently creates multi-second tail latency.

**Architecture:** Token Case must be a CQRS read path: HTTP reads only PostgreSQL facts/read models and never synchronously call GMGN, OKX, Binance, OpenAI, or any provider. Market candles become local derived presentation data from persisted `market_ticks` first; provider-backed OHLC can be added later as a worker-owned read model. Background Token Radar projections and maintenance must stay bounded so rebuildable read models do not starve user-facing API reads.

**Tech Stack:** Python 3.13, FastAPI, psycopg/PostgreSQL 18, pytest, React/Vite/TypeScript, React Query, Playwright Browser verification.

---

## Context And Root Cause

### User-visible symptom

The page below opens slowly and sometimes stalls for multiple seconds:

```text
http://localhost:8765/token/Asset/asset%3Aeip155%3A8453%3Aerc20%3A0xaef8bde6a49ccd5ebcb8cd7b458ac5bf3eaf0857
```

The frontend shell and static route are not the primary bottleneck:

- Static HTML route response was about `85ms`.
- Browser page had about `1094` DOM nodes, `27` article cards, and no console errors.
- Token logo `/api/token-images/...` was about `88ms` and about `3.8KB`.

The slow path is the data request behind the route:

- `/api/token-case?window=24h&scope=all&posts_limit=24` returned about `100KB`.
- Common latency was `1.3s` to `1.9s`; a later run hit about `7.8s`.
- `/api/target-posts` for the same target was often tens of milliseconds, so the posts query alone is not the main culprit.

### Root cause 1: request-time provider call in Token Case

`/api/token-case` constructs `TokenCaseService` with a provider-backed `MarketCandlesService`:

```python
# src/parallax/app/surfaces/api/routes_search.py
data = TokenCaseService(
    targets=repos.token_targets,
    profiles=TokenProfileReadModel(token_profiles=repos.token_profiles),
    live_price_gateway=_worker_object(runtime, "live_price_gateway"),
    market_candles=_market_candles_service(runtime),
    cex_detail_snapshots=repos.cex_detail_snapshots,
).dossier(...)
```

The service then builds timeline data:

```python
# src/parallax/domains/token_intel/read_models/token_case_service.py
timeline = TokenTargetSocialTimelineService(
    targets=self.targets,
    market_candles=self.market_candles,
).timeline(...)
```

Timeline generation then enriches candles synchronously:

```python
# src/parallax/domains/token_intel/read_models/token_target_social_timeline_service.py
market_candles = _market_candles(page_rows)
if self.market_candles is not None:
    market_candles = self.market_candles.enrich_market_candles(market_candles, window=window)
```

For `Asset` targets, `MarketCandlesService` calls the GMGN DEX candle provider in the HTTP request path:

```python
# src/parallax/domains/asset_market/read_models/market_candles_service.py
rows = self.dex_candle_market.token_candles(
    chain_id=chain_id,
    address=address,
    bar=bar,
    limit=limit,
)
```

Direct measurement inside the running container showed the same service with candles disabled completed in about `28ms` to `109ms`; with candles enabled it took about `390ms` to `1119ms` even when candles were empty. This makes every Token Case open depend on external provider latency and retry/error behavior.

### Root cause 2: duplicated read work in Token Case

`TokenCaseService.dossier()` currently asks for timeline rows and posts rows separately:

```python
timeline = TokenTargetSocialTimelineService(...).timeline(...)
posts = TokenTargetPostsService(...).target_posts(...)
```

For the default route both use the same target, window, scope, and recent ordering. The duplicated DB work is not the biggest latency source on this sampled token, but it adds avoidable cost and makes future wide windows more fragile.

### Root cause 3: semantic hydrate N+1 query

`NarrativeReadModel.hydrate_target_posts()` calls `NarrativeRepository.semantics_for_posts()`. That repository currently loops over posts and executes one query per post:

```python
for post in posts:
    row = self.conn.execute(
        """
        SELECT *
        FROM token_mention_semantics
        WHERE event_id = %s
          AND target_type = %s
          AND target_id = %s
          AND schema_version = %s
        ORDER BY computed_at_ms DESC NULLS LAST, queued_at_ms DESC NULLS LAST
        LIMIT 1
        """,
        (...),
    ).fetchone()
```

At `24` posts this is tolerable; at larger limits or under API concurrency it creates unnecessary query count and connection time.

### Root cause 4: DB is not actually small

The phrase "now data volume is not large" is misleading for the active runtime database. Snapshot observed from `pg_stat_user_tables` and relation size:

```text
token_radar_rows         total about 120GB, live rows about 1.18M
market_ticks             total about 19GB, live rows about 9.4M
events                   total about 9GB, live rows about 1.64M
token_intent_resolutions total about 2.2GB, live rows about 1.86M
```

The especially surprising part is `token_radar_rows`: it is a rebuildable read model, but it has grown to about `120GB` total. The heap was about `28GB`, indexes about `22GB`, and the remaining size is very likely TOAST payload from large JSON columns. `pg_stat_user_tables` also showed no recorded vacuum/autovacuum for `token_radar_rows` in this runtime.

During investigation, Postgres CPU exceeded `200%`, and `pg_stat_activity` showed long-running `worker:token_radar_projection` queries with parallel workers. App logs also showed:

```text
wake waiter reconnecting after LISTEN failure: couldn't get a connection after 30.00 sec
notification_summary ... QueryCanceled: canceling statement due to statement timeout
```

So the page is affected by shared DB/CPU/IO pressure even when its own detail SQL is quick. This is why one Token Case request can be under `2s` and another can spike near `8s`.

### Non-root causes ruled down

- The detail page's core `timeline_rows` SQL for this target was about `21ms` with `EXPLAIN (ANALYZE, BUFFERS)`.
- It used existing indexes such as `idx_token_intent_resolutions_target_current`, `events_pkey`, `enriched_events_pkey`, and `market_ticks_pkey`.
- Therefore this is not primarily "missing one index on the Token Case query".

---

## Implementation Strategy

Make the first fix narrow and reversible:

1. Remove synchronous provider candle enrichment from `/api/token-case`.
2. Replace it with a local DB-only candle summary derived from persisted `market_ticks`.
3. Reuse fetched post rows where possible.
4. Batch narrative semantic hydration.
5. Add diagnostics/tests proving Token Case does not call external candle providers.
6. Separately bound Token Radar read-model growth and projection load.

Do not introduce a frontend-only workaround that hides loading while the backend still blocks on provider IO. The product should become fast because the read path is structurally fast.

---

## File Structure

### Backend read path

- Modify: `src/parallax/app/surfaces/api/routes_search.py`
  - Stop injecting provider-backed `MarketCandlesService` into Token Case.
  - Use a DB-only local candle service if/when it is ready.

- Modify: `src/parallax/domains/token_intel/read_models/token_case_service.py`
  - Let `TokenCaseService` accept a local candle read model dependency, not a provider-backed market adapter.
  - Reuse one set of rows for timeline/posts when possible.

- Modify: `src/parallax/domains/token_intel/read_models/token_target_social_timeline_service.py`
  - Keep timeline construction pure over rows.
  - Avoid calling provider-backed enrichers from API reads.

- Create: `src/parallax/domains/asset_market/read_models/local_market_candles.py`
  - Query persisted `market_ticks`.
  - Bucket rows into the same public candle shape used by existing frontend models.
  - Return explicit statuses: `ready`, `empty`, `missing_identity`, `missing_target`, `unsupported`.

- Modify: `src/parallax/domains/narrative_intel/repositories/narrative_repository.py`
  - Replace per-post semantic lookups with one batched query.

### Backend tests

- Modify: `tests/unit/test_token_case_service.py`
  - Assert Token Case can build dossier without any provider candle dependency.
  - Assert timeline candle block is local/empty and does not throw.

- Add or modify: `tests/unit/domains/asset_market/test_local_market_candles.py`
  - Unit-test bucket mapping, empty state, and price aggregation behavior.

- Modify: `tests/integration/test_api_http.py`
  - Add regression that `/api/token-case` does not call provider-backed candles.
  - Keep existing contract shape intact.

- Modify: `tests/unit/domains/narrative_intel/test_narrative_repository.py` or closest existing repository test file
  - Assert `semantics_for_posts()` performs a batched latest-row selection.

### DB load and operations

- Inspect/modify: `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py`
  - Ensure projection schedules are bounded and not wake-amplified.

- Inspect/modify: `src/parallax/domains/token_intel/queries/token_radar_source_query.py`
  - Reduce repeated lateral `market_ticks` latest/first lookups where possible.

- Inspect/modify: `src/parallax/app/runtime/wake_waiter.py`
  - Keep LISTEN connections from starving each other.

- Inspect/modify: `src/parallax/app/runtime/db_pool_bundle.py`
  - Size `wake_pool` based on enabled listeners or replace many listeners with shared fanout.

- Inspect existing CLI: `src/parallax/app/surfaces/cli/commands/ops.py`
  - Confirm hard-cut PostgreSQL reset and partition helpers exist; legacy Token Radar prune/backfill commands must stay removed.

### Documentation

- Modify: `docs/ARCHITECTURE.md`
  - State Token Case read path must not perform provider calls.

- Modify: `docs/CONTRACTS.md`
  - Document `/api/token-case.timeline.market_candles` statuses and local-read semantics.

- Modify: `docs/RELIABILITY.md`
  - Add operational guidance for Token Radar pruning and wake pool sizing.

- Modify: `docs/TECH_DEBT.md`
  - Add any deferred OHLC provider projection work if not completed in this plan.

---

## Task 0: Unblock The Workspace

**Files:**
- Existing conflict files shown by `git status --short`
- No code changes from this task unless the implementing agent explicitly owns resolving the existing conflicts

- [ ] **Step 0.1: Confirm current conflict state**

Run:

```bash
git status --short
```

Expected current problem:

```text
UU docs/WORKERS.md
UU src/parallax/app/runtime/worker_registry.py
UU src/parallax/platform/config/settings.py
UU tests/architecture/test_worker_runtime_contracts.py
```

- [ ] **Step 0.2: Confirm CLI config command is blocked before conflict resolution**

Run:

```bash
uv run parallax config
```

Expected before resolving conflicts:

```text
SyntaxError: invalid syntax
```

The failure is expected while `settings.py` contains conflict markers.

- [ ] **Step 0.3: Resolve or isolate unrelated conflicts before code implementation**

Use one of these safe paths:

```bash
# Preferred: resolve the existing conflicts if they are part of the active branch.
git status --short
```

or:

```bash
# Alternative: create a clean worktree from the intended base branch.
git worktree add .worktrees/token-case-read-path-latency-root-fix -b codex/token-case-read-path-latency-root-fix main
cd .worktrees/token-case-read-path-latency-root-fix
```

Expected:

```text
No conflict markers in Python files that must be imported by tests.
```

- [ ] **Step 0.4: Verify real runtime config paths**

Run after conflicts are gone:

```bash
uv run parallax config
```

Expected:

```text
config_path: .../.parallax/config.yaml
workers_config_path: .../.parallax/workers.yaml
```

Do not print secret values. Only report paths and redacted booleans.

---

## Task 1: Add A Failing Regression For Token Case Provider Isolation

**Files:**
- Modify: `tests/unit/test_token_case_service.py`
- Modify if needed: `tests/integration/test_api_http.py`

- [ ] **Step 1.1: Add a provider sentinel test to `tests/unit/test_token_case_service.py`**

Add a fake candle provider that fails if called:

```python
class ExplodingMarketCandles:
    def enrich_market_candles(self, payload, *, window: str):
        raise AssertionError("Token Case must not call provider-backed candle enrichment")
```

Add a test that constructs `TokenCaseService` with this dependency and verifies the service no longer calls it after Task 2:

```python
def test_token_case_dossier_does_not_call_provider_candles(token_case_targets, token_profiles):
    service = TokenCaseService(
        targets=token_case_targets,
        profiles=TokenProfileReadModel(token_profiles=token_profiles),
        live_price_gateway=None,
        market_candles=ExplodingMarketCandles(),
    )

    dossier = service.dossier(
        target_type="Asset",
        target_id="asset:eip155:8453:erc20:0xaef8bde6a49ccd5ebcb8cd7b458ac5bf3eaf0857",
        window="24h",
        scope="all",
        posts_limit=24,
        now_ms=1_779_500_000_000,
    )

    assert dossier["target"]["target_type"] == "Asset"
    assert dossier["timeline"]["query"]["window"] == "24h"
```

If existing fixtures use different names, adapt only fixture names, not the assertion intent.

- [ ] **Step 1.2: Run the failing unit test**

Run:

```bash
uv run pytest tests/unit/test_token_case_service.py::test_token_case_dossier_does_not_call_provider_candles -q
```

Expected before implementation:

```text
FAILED ... AssertionError: Token Case must not call provider-backed candle enrichment
```

- [ ] **Step 1.3: Add an API-level regression if existing test harness supports runtime provider injection**

In `tests/integration/test_api_http.py`, add a route-level test that installs a fake provider whose candle method raises. The test should call:

```python
response = client.get(
    "/api/token-case",
    params={
        "target_type": "Asset",
        "target_id": "asset:eip155:8453:erc20:0xaef8bde6a49ccd5ebcb8cd7b458ac5bf3eaf0857",
        "window": "24h",
        "scope": "all",
        "posts_limit": 24,
    },
    headers=auth_headers(),
)
assert response.status_code == 200
```

Expected before implementation if the fake provider is wired correctly:

```text
FAILED because the provider sentinel is called
```

---

## Task 2: Remove Provider Candles From `/api/token-case`

**Files:**
- Modify: `src/parallax/app/surfaces/api/routes_search.py`
- Modify: `src/parallax/domains/token_intel/read_models/token_case_service.py`
- Modify: `src/parallax/domains/token_intel/read_models/token_target_social_timeline_service.py`

- [ ] **Step 2.1: Make Token Case pass no provider candle dependency**

Change the `/api/token-case` construction in `routes_search.py` from:

```python
market_candles=_market_candles_service(runtime),
```

to:

```python
market_candles=None,
```

This is the smallest safe root fix. It removes request-time provider IO immediately.

- [ ] **Step 2.2: Preserve the response shape**

In `TokenTargetSocialTimelineService.timeline()`, keep this behavior:

```python
market_candles = _market_candles(page_rows)
if self.market_candles is not None:
    market_candles = self.market_candles.enrich_market_candles(market_candles, window=window)
```

For Task 2, do not delete the hook yet because search inspect may still use it. The route-level change is enough to stop Token Case from provider calls.

- [ ] **Step 2.3: Run the regression**

Run:

```bash
uv run pytest tests/unit/test_token_case_service.py::test_token_case_dossier_does_not_call_provider_candles -q
```

Expected:

```text
1 passed
```

- [ ] **Step 2.4: Run Token Case backend tests**

Run:

```bash
uv run pytest tests/unit/test_token_case_service.py tests/integration/test_api_http.py -q
```

Expected:

```text
All selected tests pass, or unrelated pre-existing failures are documented with exact names.
```

- [ ] **Step 2.5: Measure real endpoint again**

Use the running service and authenticated token:

```bash
python - <<'PY'
import json
import time
import urllib.request

base = "http://localhost:8765"
boot = json.loads(urllib.request.urlopen(base + "/api/bootstrap", timeout=5).read())
token = boot["data"]["ws_token"]
target = "asset:eip155:8453:erc20:0xaef8bde6a49ccd5ebcb8cd7b458ac5bf3eaf0857"
url = (
    base
    + "/api/token-case?target_type=Asset&target_id="
    + urllib.parse.quote(target, safe="")
    + "&window=24h&scope=all&posts_limit=24"
)
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
for i in range(5):
    started = time.perf_counter()
    body = urllib.request.urlopen(req, timeout=10).read()
    print(i + 1, round((time.perf_counter() - started) * 1000), len(body))
PY
```

Expected:

```text
Most runs should be near local DB timings, not 400ms-1100ms provider timings.
```

---

## Task 3: Add Local DB-Only Candle Read Model

**Files:**
- Create: `src/parallax/domains/asset_market/read_models/local_market_candles.py`
- Test: `tests/unit/domains/asset_market/test_local_market_candles.py`

- [ ] **Step 3.1: Write unit tests for bucket policy**

Create `tests/unit/domains/asset_market/test_local_market_candles.py`:

```python
from parallax.domains.asset_market.read_models.local_market_candles import (
    candle_query_for_window,
)


def test_candle_query_for_window_maps_public_windows():
    assert candle_query_for_window("5m") == ("1m", 10)
    assert candle_query_for_window("1h") == ("5m", 24)
    assert candle_query_for_window("4h") == ("15m", 32)
    assert candle_query_for_window("24h") == ("1H", 48)
```

- [ ] **Step 3.2: Write unit tests for empty and ready payloads**

Add tests using a fake repository/connection that returns no ticks and several ticks:

```python
def test_local_market_candles_returns_empty_when_no_ticks(fake_conn):
    service = LocalMarketCandlesReadModel(fake_conn)

    payload = service.asset_candles(
        target_type="Asset",
        target_id="asset:eip155:8453:erc20:0xaef8bde6a49ccd5ebcb8cd7b458ac5bf3eaf0857",
        chain_id="eip155:8453",
        address="0xaef8bde6a49ccd5ebcb8cd7b458ac5bf3eaf0857",
        window="24h",
        now_ms=1_779_500_000_000,
    )

    assert payload["candle_status"] == "empty"
    assert payload["candle_source"] == "local_market_ticks"
    assert payload["candles"] == []
```

Use existing fake connection helpers if the repository tests already provide them.

- [ ] **Step 3.3: Implement `local_market_candles.py`**

Implement a focused service:

```python
from __future__ import annotations

from typing import Any

WINDOW_MS = {
    "5m": 5 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
}


def candle_query_for_window(window: str) -> tuple[str, int]:
    if window == "5m":
        return "1m", 10
    if window == "1h":
        return "5m", 24
    if window == "4h":
        return "15m", 32
    return "1H", 48
```

Add `LocalMarketCandlesReadModel` with one public method:

```python
class LocalMarketCandlesReadModel:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def asset_candles(
        self,
        *,
        target_type: str,
        target_id: str,
        chain_id: str | None,
        address: str | None,
        window: str,
        now_ms: int,
    ) -> dict[str, Any]:
        if target_type != "Asset":
            return _anchor(status="unsupported", target_type=target_type, target_id=target_id, window=window)
        if not chain_id or not address:
            return _anchor(status="missing_identity", target_type=target_type, target_id=target_id, window=window)
        bar, limit = candle_query_for_window(window)
        bucket_ms = _bucket_ms(bar)
        since_ms = int(now_ms) - WINDOW_MS.get(window, WINDOW_MS["24h"])
        rows = self._ticks(
            market_target_id=f"{chain_id}:{address.lower()}",
            since_ms=since_ms,
            now_ms=now_ms,
        )
        candles = _bucket_ticks(rows, bucket_ms=bucket_ms, limit=limit)
        return {
            "target_type": target_type,
            "target_id": target_id,
            "chain_id": chain_id,
            "address": address.lower(),
            "price_series_type": "ohlc" if candles else "anchor_line",
            "candle_status": "ready" if candles else "empty",
            "candle_source": "local_market_ticks",
            "candle_bar": bar,
            "candles": candles,
        }
```

The SQL should use the existing index `idx_market_ticks_target_observed`:

```sql
SELECT observed_at_ms, price_usd, volume_24h_usd, market_cap_usd, liquidity_usd
FROM market_ticks
WHERE target_type = 'chain_token'
  AND target_id = %s
  AND observed_at_ms >= %s
  AND observed_at_ms <= %s
  AND price_usd IS NOT NULL
ORDER BY observed_at_ms ASC, tick_id ASC
```

- [ ] **Step 3.4: Run unit tests**

Run:

```bash
uv run pytest tests/unit/domains/asset_market/test_local_market_candles.py -q
```

Expected:

```text
All tests pass.
```

---

## Task 4: Wire Local Candles Into Token Case

**Files:**
- Modify: `src/parallax/app/surfaces/api/routes_search.py`
- Modify: `src/parallax/domains/token_intel/read_models/token_case_service.py`
- Modify: `src/parallax/domains/token_intel/read_models/token_target_social_timeline_service.py`
- Test: `tests/integration/test_api_http.py`

- [ ] **Step 4.1: Add a local candle dependency name**

In `TokenCaseService.__init__`, keep the argument name compatible for now:

```python
market_candles: Any | None = None
```

But document in code by type/comment that for Token Case this must be DB-only. Do not pass provider-backed `MarketCandlesService` from `/api/token-case`.

- [ ] **Step 4.2: Build local candles from the API repository connection**

In `routes_search.py`, import:

```python
from parallax.domains.asset_market.read_models.local_market_candles import (
    LocalMarketCandlesReadModel,
)
```

Change `/api/token-case` construction to:

```python
market_candles=LocalMarketCandlesReadModel(repos.conn),
```

- [ ] **Step 4.3: Make `LocalMarketCandlesReadModel` compatible with timeline enrichment**

Add an `enrich_market_candles(payload, *, window)` method:

```python
def enrich_market_candles(self, payload: dict[str, Any] | None, *, window: str) -> dict[str, Any]:
    base = dict(payload) if isinstance(payload, dict) else {"status": "missing"}
    return self.asset_candles(
        target_type=str(base.get("target_type") or ""),
        target_id=str(base.get("target_id") or ""),
        chain_id=_text(base.get("chain_id")),
        address=_text(base.get("address")),
        window=window,
        now_ms=_now_ms(),
    )
```

If exact `now_ms` consistency is needed, pass `now_ms` from `TokenCaseService` into `TokenTargetSocialTimelineService.timeline()` and then into `enrich_market_candles`. Prefer explicit `now_ms` over calling time twice.

- [ ] **Step 4.4: Add API assertion for candle status**

Add to `tests/integration/test_api_http.py`:

```python
body = response.json()
market_candles = body["data"]["timeline"]["market_candles"]
assert market_candles["candle_source"] == "local_market_ticks"
assert market_candles["candle_status"] in {"ready", "empty"}
```

- [ ] **Step 4.5: Run route tests**

Run:

```bash
uv run pytest tests/integration/test_api_http.py -k "token_case or target_posts" -q
```

Expected:

```text
All selected tests pass.
```

---

## Task 5: Reuse Token Case Rows Instead Of Querying Twice

**Files:**
- Modify: `src/parallax/domains/token_intel/read_models/token_case_service.py`
- Modify: `src/parallax/domains/token_intel/read_models/token_target_social_timeline_service.py`
- Modify: `src/parallax/domains/token_intel/read_models/token_target_posts_service.py`
- Test: `tests/unit/test_token_case_service.py`

- [ ] **Step 5.1: Add test that rows are fetched once**

Use a fake target repository that counts `timeline_rows()` calls:

```python
def test_token_case_reuses_timeline_rows_for_posts(fake_token_case_repository, token_profiles):
    service = TokenCaseService(
        targets=fake_token_case_repository,
        profiles=TokenProfileReadModel(token_profiles=token_profiles),
        live_price_gateway=None,
        market_candles=None,
    )

    service.dossier(
        target_type="Asset",
        target_id=fake_token_case_repository.target_id,
        window="24h",
        scope="all",
        posts_limit=24,
        now_ms=1_779_500_000_000,
    )

    assert fake_token_case_repository.timeline_rows_calls == 1
```

- [ ] **Step 5.2: Extract row-to-timeline builder**

In `TokenTargetSocialTimelineService`, add a method that accepts pre-fetched rows:

```python
def timeline_from_rows(
    self,
    *,
    rows: list[dict[str, Any]],
    target_type: str,
    target_id: str,
    window: str,
    scope: str,
    limit: int,
    now_ms: int,
) -> dict[str, Any]:
    page_rows = rows[: max(0, int(limit))]
    ...
```

Keep `timeline()` as a wrapper that fetches rows and calls `timeline_from_rows()`.

- [ ] **Step 5.3: Extract row-to-posts builder**

In `TokenTargetPostsService`, add:

```python
def target_posts_from_rows(
    self,
    *,
    rows: list[dict[str, Any]],
    target_type: str,
    target_id: str,
    window: str,
    scope: str,
    post_range: str,
    sort: str,
    limit: int,
) -> dict[str, Any]:
    page_rows = rows[: max(0, int(limit))]
    ...
```

Keep `target_posts()` as the pagination-aware wrapper for `/api/target-posts`.

- [ ] **Step 5.4: Use one fetch in `TokenCaseService.dossier()`**

In `TokenCaseService.dossier()`, fetch rows once:

```python
rows = self.targets.timeline_rows(
    target_type=target_type,
    target_id=target_id,
    since_ms=resolved_now_ms - WINDOW_MS.get(window, WINDOW_MS["1h"]),
    watched_only=service_scope == "matched",
    limit=max(posts_limit, 24) + 1,
    cursor=None,
)
```

Then pass `rows` into the timeline and posts builders.

- [ ] **Step 5.5: Run tests**

Run:

```bash
uv run pytest tests/unit/test_token_case_service.py tests/integration/test_api_http.py -k "token_case or target_posts" -q
```

Expected:

```text
All selected tests pass.
```

---

## Task 6: Batch Narrative Semantics Hydration

**Files:**
- Modify: `src/parallax/domains/narrative_intel/repositories/narrative_repository.py`
- Test: closest narrative repository unit/integration test

- [ ] **Step 6.1: Add test for latest semantic selection**

Create a test that seeds two semantics rows for one `(event_id,target_type,target_id,schema_version)` and one for another post. Assert the method returns both posts and picks newest by `computed_at_ms DESC NULLS LAST, queued_at_ms DESC NULLS LAST`.

Expected assertion shape:

```python
result = repository.semantics_for_posts(posts, schema_version="narrative_v1")

assert result[("event-1", "Asset", "asset:x")]["semantic_id"] == "semantic-new"
assert result[("event-2", "Asset", "asset:x")]["semantic_id"] == "semantic-2"
```

- [ ] **Step 6.2: Replace loop with batched SQL**

Use a `VALUES` CTE:

```sql
WITH requested(event_id, target_type, target_id) AS (
  SELECT * FROM (VALUES %s) AS values(event_id, target_type, target_id)
),
ranked AS (
  SELECT semantics.*,
         row_number() OVER (
           PARTITION BY semantics.event_id, semantics.target_type, semantics.target_id
           ORDER BY semantics.computed_at_ms DESC NULLS LAST,
                    semantics.queued_at_ms DESC NULLS LAST
         ) AS rn
  FROM requested
  JOIN token_mention_semantics AS semantics
    ON semantics.event_id = requested.event_id
   AND semantics.target_type = requested.target_type
   AND semantics.target_id = requested.target_id
  WHERE semantics.schema_version = %s
)
SELECT *
FROM ranked
WHERE rn = 1
```

Use psycopg-safe parameterization. If `VALUES %s` is awkward in this codebase, use parallel arrays with `unnest()`:

```sql
WITH requested AS (
  SELECT *
  FROM unnest(%s::text[], %s::text[], %s::text[])
       AS requested(event_id, target_type, target_id)
)
...
```

- [ ] **Step 6.3: Preserve missing semantic behavior**

`NarrativeReadModel.hydrate_target_posts()` should still use `_missing_semantic()` for posts absent from the result map. No API behavior change except fewer SQL queries.

- [ ] **Step 6.4: Run narrative and token case tests**

Run:

```bash
uv run pytest tests/unit tests/integration/test_api_http.py -k "semantic or token_case or target_posts" -q
```

Expected:

```text
All selected tests pass.
```

---

## Task 7: Bound Token Radar Read Model Growth

**Files:**
- Inspect/modify: `src/parallax/app/surfaces/cli/commands/ops.py`
- Inspect/modify: `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `docs/RELIABILITY.md`
- Modify: `docs/TECH_DEBT.md`

- [ ] **Step 7.1: Confirm hard-cut maintenance commands**

Run:

```bash
uv run parallax ops --help | rg "reset-token-radar-postgres-hard-cut|ensure-postgres-partitions|drop-expired-postgres-partitions"
```

Expected:

```text
reset-token-radar-postgres-hard-cut
ensure-postgres-partitions
drop-expired-postgres-partitions
```

- [ ] **Step 7.2: Dry-run derived-storage reset impact**

Run against real config only after `uv run parallax config` confirms paths:

```bash
uv run parallax ops reset-token-radar-postgres-hard-cut --dry-run
```

Expected:

```text
Dry-run reports derived tables, attached partition scope, projection-control filters, preserved facts, and does not delete data.
```

- [ ] **Step 7.3: Execute hard-cut derived reset once**

Run:

```bash
uv run parallax ops reset-token-radar-postgres-hard-cut --execute
```

Run only after confirming the service can rebuild from current material facts. Do not run legacy bounded prune commands.

- [ ] **Step 7.4: Ensure history/audit partitions**

Run:

```bash
uv run parallax ops ensure-postgres-partitions --execute
```

Expected:

```text
Current and next month `token_radar_rank_history_*` and `token_radar_snapshot_audit_*` partitions exist.
```

- [ ] **Step 7.5: Add reliability doc note**

In `docs/RELIABILITY.md`, update the Token Radar maintenance section with:

```markdown
Token Radar rows are rebuildable read-model output. Production uses
`ops reset-token-radar-postgres-hard-cut` for one-shot derived-storage resets
and `ops ensure-postgres-partitions` for rank-history/audit partition readiness.
Legacy `prune-token-radar` and first-seen backfill commands are removed.
```

---

## Task 8: Fix Wake Pool Starvation

**Files:**
- Modify: `src/parallax/app/runtime/db_pool_bundle.py`
- Modify or create tests near worker runtime architecture tests
- Modify: `docs/RELIABILITY.md`

- [ ] **Step 8.1: Add a test for wake pool sizing**

Add an architecture/runtime test asserting `wake_pool` max size is not a hard-coded value lower than enabled LISTEN users. If direct runtime settings are hard to instantiate, test a helper function:

```python
def test_wake_pool_size_accounts_for_enabled_listeners():
    assert wake_pool_max_size(enabled_listener_count=12) >= 12
```

- [ ] **Step 8.2: Extract wake pool size calculation**

In `db_pool_bundle.py`, add:

```python
def wake_pool_max_size(*, enabled_listener_count: int) -> int:
    return max(3, int(enabled_listener_count) + 1)
```

If enabled listener count is not available in `DBPoolBundle.create()`, add it to settings-derived runtime construction rather than guessing.

- [ ] **Step 8.3: Use the helper when creating `wake_pool`**

Replace:

```python
max_size=3,
```

with:

```python
max_size=wake_pool_max_size(enabled_listener_count=_enabled_wake_listener_count(settings)),
```

Implement `_enabled_wake_listener_count(settings)` by counting enabled workers with non-empty `wakes_on` tuples.

- [ ] **Step 8.4: Verify the original warning disappears**

After deploying locally, watch logs:

```bash
docker logs --tail 300 parallax-app-1 | rg "wake waiter reconnecting|couldn't get a connection"
```

Expected:

```text
No repeated wake waiter connection starvation warnings under normal worker load.
```

---

## Task 9: Reduce Token Radar Projection Load

**Files:**
- Modify: `src/parallax/domains/token_intel/queries/token_radar_source_query.py`
- Modify: `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py`
- Test: existing token radar projection tests

- [ ] **Step 9.1: Capture the current query plan**

Run an `EXPLAIN (ANALYZE, BUFFERS)` for the active projection query for the hottest window/scope. Save the summary in the implementation notes:

```sql
EXPLAIN (ANALYZE, BUFFERS)
WITH source_intents AS MATERIALIZED (...)
SELECT ...
```

Expected:

```text
Plan shows whether cost is source_intents materialization, market_ticks laterals, or token_radar_rows writes.
```

- [ ] **Step 9.2: Remove unnecessary `MATERIALIZED` if planner can do better**

Test a variant:

```sql
WITH source_intents AS (
  ...
)
```

Compare:

```text
Execution Time
shared hit/read buffers
parallel worker behavior
```

Keep `MATERIALIZED` only if it measurably wins.

- [ ] **Step 9.3: Avoid per-row first/latest market tick lookups**

If EXPLAIN shows repeated `market_ticks` lateral scans dominate, precompute latest ticks for distinct market targets in the window:

```sql
WITH distinct_market_targets AS (...),
latest_ticks AS (
  SELECT DISTINCT ON (target_type, target_id)
         target_type, target_id, tick_id, observed_at_ms, price_usd, ...
  FROM market_ticks
  JOIN distinct_market_targets USING (target_type, target_id)
  WHERE observed_at_ms <= %s
  ORDER BY target_type, target_id, observed_at_ms DESC, tick_id DESC
)
```

Then join by `(target_type, target_id)` instead of running one latest lookup per source row.

- [ ] **Step 9.4: Throttle redundant projection wake work**

In `TokenRadarProjectionWorker`, confirm wake bursts are deduped by `(window, scope)` and that active projection cycles are not stacked. If missing, add a small coalescing guard:

```python
def _dedupe_work_items(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
```

This helper already exists; ensure all wake-derived work paths use it.

- [ ] **Step 9.5: Run projection tests**

Run:

```bash
uv run pytest tests/integration/test_token_radar_idempotency.py tests/unit/test_worker_settings.py -q
```

Expected:

```text
Projection remains deterministic and worker settings still validate.
```

---

## Task 10: Frontend Behavior And Browser Verification

**Files:**
- Inspect/modify only if needed: `web/src/features/token-case/ui/TokenCaseRoute.tsx`
- Inspect/modify only if needed: `web/src/features/token-case/model/buildTokenCaseViewModel.ts`
- Inspect/modify only if needed: `web/src/shared/query/patchMarketUpdate.ts`

- [ ] **Step 10.1: Keep frontend contract stable**

Do not change route params:

```text
/token/:targetType/:targetId?window=24h&scope=all&postSort=recent
```

Do not make frontend call provider URLs. Token images must still be same-origin `/api/token-images/{image_id}`.

- [ ] **Step 10.2: Verify no extra `/api/target-posts` first-page fetch**

The route should still seed posts from dossier:

```typescript
const initialPosts = dossierQuery.isPending ? undefined : (dossier?.posts ?? null);
```

Expected first load:

```text
/api/token-case is required.
/api/target-posts is not required unless first-page seed is missing or user loads more.
```

- [ ] **Step 10.3: Browser hard reload exact route**

Open:

```text
http://localhost:8765/token/Asset/asset%3Aeip155%3A8453%3Aerc20%3A0xaef8bde6a49ccd5ebcb8cd7b458ac5bf3eaf0857
```

Expected:

```text
Page reaches usable Token Case state without waiting on external candle provider.
No failing /api/* requests.
No provider image URLs.
No console errors.
```

- [ ] **Step 10.4: Capture timing evidence**

In Browser performance/resource entries or API timing script, record:

```text
/api/token-case p50
/api/token-case worst of 5 local runs
response bytes
console errors
```

Expected target after Task 2/4:

```text
Typical local `/api/token-case` under 300ms when DB is not saturated.
No provider-call-sized 400ms-1100ms baseline penalty.
Tail latency documented separately if Token Radar projection is actively saturating DB.
```

---

## Task 11: Documentation Updates

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/RELIABILITY.md`
- Modify: `docs/TECH_DEBT.md`

- [ ] **Step 11.1: Update architecture invariant**

In `docs/ARCHITECTURE.md`, add to the read-model/public read path section:

```markdown
Token Case is a local read path. `/api/token-case` may read persisted facts,
derived read models, local image assets, and in-process live market snapshots,
but it must not synchronously call external market, profile, candle, or LLM
providers. Provider-backed enrichment belongs in workers or explicit refresh
commands.
```

- [ ] **Step 11.2: Update contract docs**

In `docs/CONTRACTS.md`, document:

```markdown
`timeline.market_candles.candle_source` is either `local_market_ticks` or absent.
`candle_status=empty` means no persisted ticks were available for the requested
window; it is not an HTTP/provider failure.
```

- [ ] **Step 11.3: Update reliability docs**

In `docs/RELIABILITY.md`, add:

```markdown
When Token Case p95 regresses, check request-time provider calls first, then
`pg_stat_activity` for Token Radar projection pressure, then
`pg_total_relation_size('token_radar_rows')`.
```

- [ ] **Step 11.4: Update tech debt only for deferred worker OHLC**

If this implementation does not add provider-backed OHLC projection, add:

```markdown
| Provider OHLC for Token Case should be worker-owned instead of API-time provider IO | 2026-05-23 token-case latency root fix | asset_market/token_intel | medium | Add a rebuildable local candle read model if local `market_ticks` fidelity is not enough for product use | unowned |
```

---

## Task 12: Final Verification Gate

**Files:**
- No direct source edits unless failures reveal missing coverage

- [ ] **Step 12.1: Run targeted backend tests**

Run:

```bash
uv run pytest \
  tests/unit/test_token_case_service.py \
  tests/unit/domains/asset_market/test_local_market_candles.py \
  tests/integration/test_api_http.py \
  -k "token_case or target_posts or local_market_candles" \
  -q
```

Expected:

```text
All selected tests pass.
```

- [ ] **Step 12.2: Run architecture tests touched by docs/runtime changes**

Run:

```bash
uv run pytest tests/architecture/test_src_domain_architecture.py tests/architecture/test_project_structure.py -q
```

Expected:

```text
All selected tests pass.
```

- [ ] **Step 12.3: Run frontend checks if any web files changed**

Run:

```bash
cd web && npm run lint
cd web && npm run typecheck
```

Expected:

```text
No lint or type errors.
```

- [ ] **Step 12.4: Verify exact URL in Browser**

Use the in-app Browser to hard reload:

```text
http://localhost:8765/token/Asset/asset%3Aeip155%3A8453%3Aerc20%3A0xaef8bde6a49ccd5ebcb8cd7b458ac5bf3eaf0857
```

Expected:

```text
Token Case appears quickly.
No failing `/api/*`.
No console errors.
No provider image URL requests.
```

- [ ] **Step 12.5: Record before/after timings**

Record:

```text
Before:
- /api/token-case common: 1.3s-1.9s
- /api/token-case observed tail: about 7.8s
- provider candle direct call: 390ms-1119ms

After:
- /api/token-case p50:
- /api/token-case max of 5:
- active DB load:
- token_radar_rows total size:
```

Expected:

```text
The fixed endpoint no longer carries provider-call latency. Any remaining tail is attributable to shared DB load and should reduce after Tasks 7-9.
```

---

## Rollout Notes

1. Ship Task 2 first if the page is painful now. It is the smallest risk reduction: remove provider candles from `/api/token-case`.
2. Ship Tasks 3-6 next to restore local candle data and reduce DB query count.
3. Ship Tasks 7-9 as operations/performance hardening. These are related to latency tails, but they are broader than the Token Case endpoint.
4. Do not run large prune/delete commands without dry-run and small batches.
5. Do not claim success from one fast page reload; use at least five authenticated `/api/token-case` runs plus Browser verification.

---

## Self-Review

- Spec coverage: The plan covers request-time provider IO, duplicate Token Case rows, semantic hydrate N+1, Token Radar read-model bloat, wake pool starvation, documentation, and verification.
- Placeholder scan: No step depends on "TBD" behavior. Deferred provider-backed OHLC is explicitly recorded as tech debt if not implemented.
- Type consistency: The plan keeps the existing `market_candles` dependency shape until the local read model can implement `enrich_market_candles(...)`, minimizing public contract churn.
