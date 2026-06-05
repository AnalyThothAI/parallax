# News Realtime Postgres Hotpath Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 根治 News 模块 OpenNews “短连 WS + REST 混跑”导致的实时链路不稳定，并清理历史 backpressure 膨胀数据与 PostgreSQL 热点。

**Architecture:** Hard cut：OpenNews runtime 只保留 REST `/open/news_search` catch-up，删除 `news_fetch` 内的 WebSocket connect/subscribe/receive/unsubscribe 路径、配置项和测试兼容分支。PostgreSQL 热点通过最小化存储改动解决：新增 claim/query 索引、收窄 source-quality 聚合 SQL、清理旧 no-start agent run 与无效 `brief_input` dirty targets，不引入新的双写/双读/legacy fallback。

**Tech Stack:** Python 3.12, PostgreSQL 18, Alembic, psycopg, FastAPI, pytest, ruff, existing News Intel worker/runtime manifests.

---

**Status:** Completed in feature branch; project-wide `make check-all` remains blocked by unrelated non-News format drift.
**Date:** 2026-05-28
**Owning spec:** Current operator request plus predecessor `docs/superpowers/plans/active/2026-05-28-news-intel-dedup-root-fix-plan-cn.md`
**Worktree:** `.worktrees/news-realtime-postgres-hotpath-hard-cut/`
**Branch:** `codex/news-realtime-postgres-hotpath-hard-cut`

## Completion Record

- OpenNews runtime hard-cut completed: active `news_fetch` no longer has WebSocket connect/subscribe/receive/unsubscribe, hybrid mode, or WS fallback.
- Operator config cutover completed in `~/.parallax/config.yaml`; backup: `~/.parallax/config.yaml.bak-20260528-news-hard-cut`.
- Historical cleanup completed in DB migration `20260528_0118`; live checks show no-start backpressure rows = 0 and OpenNews provider-signal `brief_input` dirty targets = 0.
- Source-status API timeout found during live verification and fixed with KISS pre-aggregation plus migration `20260528_0119`.
- Docker image rebuilt and app restarted; live DB health reports `migration_version=20260528_0119`, `expected_migration_version=20260528_0119`.
- Full News target suite passed after source-status fix: `529 passed`.
- `make check-all` was attempted twice; after formatting only this branch's files, it still fails at `ruff format --check .` on 24 unrelated non-News files.

## Hard-Cut Constraints

- No OpenNews WebSocket code remains in the active runtime path.
- No `fetch_mode=hybrid`, `fetch_mode=websocket`, `wss_url`, `connect_timeout_seconds`, `stream_timeout_seconds`, or `max_messages` compatibility parser remains.
- No runtime fallback from failed WS to REST remains, because WS is removed from this slice.
- No frontend-only or API-only dedup workaround is allowed.
- No historical no-start backpressure rows remain in `news_item_agent_runs` after migration.
- No `brief_input` dirty target remains for OpenNews items that already have provider-owned ready signal facts.
- No migration rewrites already-landed revisions. Create a new revision after `20260528_0117`.
- No broad production `EXPLAIN (ANALYZE)` may mutate rows outside an explicit `BEGIN ... ROLLBACK`.

## KISS Decisions

- Keep `news_item_process` as a fact-lifecycle claim over `news_items`; do not introduce a new `news_item_process_targets` table in this cut. The current lifecycle fields are already the durable work state; the actual PostgreSQL problem is the missing partial claim index.
- Do not add a new long-lived OpenNews WS worker now. If sub-10s latency is later required, add a separate `opennews_ws_ingest` worker that writes the same `news_provider_items` facts, never inside `news_fetch`.
- Keep existing `news_projection_dirty_targets` table. Add a projection-first due index and clean obsolete backlog instead of splitting the table prematurely.
- Do not drop News page filter indexes in this cut; they support existing `/api/news` filters. Revisit with a longer `pg_stat_user_indexes` window after this fix.

## Pre-flight

- [ ] Create isolated worktree:

  ```bash
  git worktree add .worktrees/news-realtime-postgres-hotpath-hard-cut -b codex/news-realtime-postgres-hotpath-hard-cut main
  cd .worktrees/news-realtime-postgres-hotpath-hard-cut
  git status --short
  git branch --show-current
  ```

  Expected: clean worktree and branch `codex/news-realtime-postgres-hotpath-hard-cut`.

- [ ] Confirm runtime config paths without printing secrets:

  ```bash
  uv run parallax config
  ```

  Expected: `config_path` and `workers_config_path` point at `~/.parallax/`; report only paths and redacted credential booleans.

- [ ] Record baseline runtime symptoms:

  ```bash
  docker compose ps
  docker compose exec -T app parallax db health
  python - <<'PY'
  import httpx, json
  data = httpx.get("http://127.0.0.1:8765/readyz", timeout=10, trust_env=False).json()
  for name in (
      "news_fetch",
      "news_item_process",
      "news_item_brief",
      "news_page_projection",
      "news_source_quality_projection",
  ):
      worker = data["workers"][name]
      print(name, json.dumps({
          "last_result": worker.get("last_result"),
          "queue_depth": worker.get("queue_depth"),
          "iteration_duration_p99_ms": worker.get("iteration_duration_p99_ms"),
          "last_error": worker.get("last_error"),
      }, ensure_ascii=False))
  PY
  ```

- [ ] Record baseline PostgreSQL evidence:

  ```bash
  docker compose exec -T postgres psql -U parallax_app -d parallax -P pager=off -c "
  SELECT queryid, calls, round(total_exec_time::numeric,1) AS total_ms,
         round(mean_exec_time::numeric,2) AS mean_ms,
         shared_blks_read, temp_blks_written,
         left(regexp_replace(query,'\s+',' ','g'),220) AS q
  FROM pg_stat_statements
  WHERE query ILIKE '%news_%'
  ORDER BY total_exec_time DESC
  LIMIT 15;"
  ```

- [ ] Record cleanup target counts:

  ```bash
  docker compose exec -T postgres psql -U parallax_app -d parallax -P pager=off -c "
  SELECT count(*) AS total,
         count(*) FILTER (WHERE execution_started=false) AS no_start,
         count(*) FILTER (
           WHERE execution_started=false
             AND outcome IN ('backpressure_circuit_open','backpressure_capacity_denied')
         ) AS no_start_backpressure
  FROM news_item_agent_runs;

  SELECT count(*) AS opennews_provider_signal_brief_targets
  FROM news_projection_dirty_targets AS targets
  JOIN news_items AS items ON items.news_item_id = targets.target_id
  JOIN news_sources AS sources ON sources.source_id = items.source_id
  WHERE targets.projection_name = 'brief_input'
    AND targets.target_kind = 'news_item'
    AND sources.provider_type = 'opennews'
    AND items.provider_signal_json ->> 'source' = 'provider';"
  ```

## File-Level Edits

### `src/parallax/integrations/news_feeds/opennews_client.py`

- Replace `OpenNewsFeedClient` with a REST-only client.
- Delete imports and constructor args used only by WS:
  - `asyncio` remains only if `_default_post_json` is async; remove WS event-loop branch if no longer needed.
  - delete `time`, `DEFAULT_OPENNEWS_WSS_URL`, `DEFAULT_CONNECT_TIMEOUT_SECONDS`, `DEFAULT_STREAM_TIMEOUT_SECONDS`, `DEFAULT_MAX_MESSAGES`, `_PUSH_METHODS`.
  - delete `wss_url`, `connect_timeout_seconds`, `connect`, `_request_id`.
- Keep official REST base URL and `/open/news_search`.

Target shape:

```python
class OpenNewsFeedClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        api_base_url: str = DEFAULT_OPENNEWS_API_BASE_URL,
        post_json: Callable[..., Any] | None = None,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self._token = _optional_text(token)
        self._api_base_url = (
            str(api_base_url or DEFAULT_OPENNEWS_API_BASE_URL).strip().rstrip("/")
            or DEFAULT_OPENNEWS_API_BASE_URL
        )
        self._post_json = post_json or _default_post_json
        self._now_ms = now_ms or _now_ms

    def fetch(
        self,
        url: str,
        *,
        source: dict[str, Any] | None = None,
        cursor: Mapping[str, Any] | None = None,
        limit: int | None = None,
    ) -> FeedFetchResult:
        if not self._token:
            raise ValueError("OpenNews token is not configured")
        policy = _source_fetch_policy(source or {})
        _reject_removed_websocket_policy(policy)
        subscription = _subscription_params(url, policy)
        entries, next_cursor = _run_rest_fetch(
            self._fetch_rest_entries(
                subscription=subscription,
                policy=policy,
                cursor=cursor or {},
                limit=limit,
            )
        )
        return FeedFetchResult(
            status_code=200,
            entries=[entry for entry in entries if _entry_is_visible(entry)],
            not_modified=False,
            feed={
                "provider": "opennews",
                "transport": "rest",
                "subscription": subscription,
                "rest_received": int(next_cursor.get("rest_received") or len(entries)),
                "received": len(entries),
            },
            next_cursor=next_cursor,
        )
```

Add hard-cut policy rejection:

```python
_REMOVED_WEBSOCKET_POLICY_KEYS = {
    "fetch_mode",
    "wss_url",
    "stream_timeout_seconds",
    "streamTimeoutSeconds",
    "max_messages",
    "maxMessages",
    "connect_timeout_seconds",
    "connectTimeoutSeconds",
}


def _reject_removed_websocket_policy(policy: Mapping[str, Any]) -> None:
    removed = sorted(key for key in _REMOVED_WEBSOCKET_POLICY_KEYS if key in policy)
    if removed:
        raise ValueError(f"removed OpenNews websocket policy keys: {', '.join(removed)}")
```

Delete these functions entirely:

- `_fetch_mode`
- `_max_messages`
- `_stream_timeout_seconds`
- `_default_connect`
- `_send_json`
- `_recv_json`
- `_validate_subscribe_ack`
- `_entry_from_message`

Keep `_entry_from_params` and `_merge_entry` because REST and historical tests still use the same provider payload normalization semantics.

### `src/parallax/platform/config/settings.py`

- Remove OpenNews default policy keys `fetch_mode`, `stream_timeout_seconds`, and `max_messages` from the three built-in OpenNews source definitions.
- Keep only:

```python
"fetch_policy": {
    "engineTypes": {"news": []},
    "hasCoin": True,
    "rest_limit": 100,
    "max_rest_pages": 5,
    "rest_overlap_ms": 900_000,
}
```

- Apply the same shape for `opennews-listing` and `opennews-onchain`.
- Set `opennews-onchain` default `enabled` to `False` and keep it false; the live operator config must also disable it because current diagnostics show `rest_received=0`.
- Remove `OpenNewsSettings.wss_url` and `OpenNewsSettings.connect_timeout_seconds`.
- Config validation must reject old keys instead of silently accepting them:

```python
@field_validator("sources", mode="after")
@classmethod
def reject_removed_opennews_websocket_policy(cls, sources: tuple[NewsSourceConfig, ...]) -> tuple[NewsSourceConfig, ...]:
    removed = {
        "fetch_mode",
        "wss_url",
        "stream_timeout_seconds",
        "streamTimeoutSeconds",
        "max_messages",
        "maxMessages",
        "connect_timeout_seconds",
        "connectTimeoutSeconds",
    }
    for source in sources:
        if source.provider_type != "opennews":
            continue
        bad = sorted(removed.intersection(source.fetch_policy))
        if bad:
            raise ValueError(f"{source.source_id} uses removed OpenNews websocket policy keys: {', '.join(bad)}")
    return sources
```

If the existing model structure cannot host this validator exactly, implement the same validation at the `NewsIntelConfig` level.

### `src/parallax/app/runtime/provider_wiring/news.py`

- Remove the `wss_url` and `connect_timeout_seconds` arguments when constructing `OpenNewsFeedClient`.
- Final call shape:

```python
opennews_client=OpenNewsFeedClient(
    token=opennews_settings.api_token,
    api_base_url=opennews_settings.api_base_url,
)
```

### `src/parallax/integrations/news_feeds/provider_registry.py`

- Rename test/doc wording from “websocket client shape” to “opennews client shape”; no runtime behavior should assume WS.
- `OpenNewsNewsFeedProvider.fetch()` remains a thin wrapper over `OpenNewsFeedClient.fetch()` with `cursor` and `limit`.

### `src/parallax/domains/news_intel/ARCHITECTURE.md`

- Replace Wave 2 text:

```markdown
- Wave 2: enable OpenNews only as a provider-fact REST source. REST
  `/open/news_search` is the catch-up path for delayed `aiRating` and `coins[]`
  impact facts. WebSocket ingestion is intentionally not part of `news_fetch`;
  if it is reintroduced, it must be a separate long-lived ingest worker writing
  the same raw provider facts.
```

### `docs/CONTRACTS.md`, `docs/WORKERS.md`, `docs/RELIABILITY.md`

- Update public config docs to remove `news_intel.opennews.wss_url` and `connect_timeout_seconds`.
- Update worker docs so `news_fetch` says OpenNews REST catch-up, not hybrid WS/REST.
- Add a reliability invariant:

```markdown
OpenNews REST and any future OpenNews WS ingest are separate provider inputs.
`news_fetch` must not open a short-lived websocket as part of a poll cycle.
```

### Runtime Operator Config: `~/.parallax/config.yaml`

This is an operational edit, not a repository fixture. Before starting the new image, update enabled OpenNews sources:

```yaml
news_intel:
  sources:
    - source_id: opennews-news
      provider_type: opennews
      enabled: true
      refresh_interval_seconds: 10
      fetch_policy:
        engineTypes:
          news: []
        hasCoin: true
        rest_limit: 100
        max_rest_pages: 5
        rest_overlap_ms: 900000
    - source_id: opennews-listing
      provider_type: opennews
      enabled: true
      refresh_interval_seconds: 10
      fetch_policy:
        engineTypes:
          listing: []
        hasCoin: true
        rest_limit: 100
        max_rest_pages: 5
        rest_overlap_ms: 900000
    - source_id: opennews-onchain
      provider_type: opennews
      enabled: false
      refresh_interval_seconds: 300
      fetch_policy:
        engineTypes:
          onchain: []
        hasCoin: true
        rest_limit: 100
        max_rest_pages: 2
        rest_overlap_ms: 900000
```

Do not print token values. Verify with:

```bash
uv run parallax config
```

Expected: OpenNews token configured boolean is true; removed WS keys are absent.

## Storage / Migration

Create:

- `src/parallax/platform/db/alembic/versions/20260528_0118_news_realtime_postgres_hotpath_hard_cut.py`

Revision metadata:

```python
revision = "20260528_0118"
down_revision = "20260528_0117"
branch_labels = None
depends_on = None
```

Upgrade body:

```python
from alembic import op


def upgrade() -> None:
    op.execute("SET lock_timeout = '5s'")
    op.execute("SET statement_timeout = '120s'")
    _clean_historical_no_start_news_agent_runs()
    _clean_opennews_provider_signal_brief_targets()
    _analyze_cleaned_news_tables()
    with op.get_context().autocommit_block():
        _create_hotpath_indexes()


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_context_items_source_effective_time")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_projection_dirty_projection_due")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_page_rows_news_item")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_items_unprocessed_claim")
```

Cleanup SQL:

```python
def _clean_historical_no_start_news_agent_runs() -> None:
    op.execute(
        """
        DELETE FROM news_item_agent_runs AS runs
         WHERE runs.execution_started = false
           AND runs.outcome IN ('backpressure_circuit_open', 'backpressure_capacity_denied')
        """
    )


def _clean_opennews_provider_signal_brief_targets() -> None:
    op.execute(
        """
        DELETE FROM news_projection_dirty_targets AS targets
        USING news_items AS items,
              news_sources AS sources
         WHERE targets.projection_name = 'brief_input'
           AND targets.target_kind = 'news_item'
           AND targets.target_id = items.news_item_id
           AND sources.source_id = items.source_id
           AND sources.provider_type = 'opennews'
           AND items.provider_signal_json ->> 'source' = 'provider'
        """
    )
```

Index SQL:

```python
def _create_hotpath_indexes() -> None:
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_items_unprocessed_claim
          ON news_items(published_at_ms ASC, news_item_id ASC)
          WHERE lifecycle_status IN ('raw', 'process_failed')
             OR (
               lifecycle_status = 'processed'
               AND content_classification_json = '{}'::jsonb
             )
        """
    )
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_page_rows_news_item
          ON news_page_rows(news_item_id)
        """
    )
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_projection_dirty_projection_due
          ON news_projection_dirty_targets(
            projection_name,
            due_at_ms,
            leased_until_ms,
            priority,
            updated_at_ms,
            target_kind,
            target_id,
            "window"
          )
        """
    )
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_context_items_source_effective_time
          ON news_context_items(
            source_id,
            (COALESCE(published_at_ms, created_at_ms)),
            parent_news_item_id
          )
        """
    )
```

Analyze SQL:

```python
def _analyze_cleaned_news_tables() -> None:
    op.execute("ANALYZE news_item_agent_runs")
    op.execute("ANALYZE news_projection_dirty_targets")
    op.execute("ANALYZE news_items")
    op.execute("ANALYZE news_page_rows")
    op.execute("ANALYZE news_context_items")
```

Do not run `VACUUM FULL` in migration. Normal `VACUUM (ANALYZE)` for disk reuse is an operator step after deploy if table bloat remains material.

## Repository SQL Changes

### `src/parallax/domains/news_intel/repositories/news_repository.py`

#### `list_unprocessed_items`

- Keep behavior and claim semantics unchanged.
- The new partial index must serve this existing predicate:

```sql
WHERE lifecycle_status IN ('raw', 'process_failed')
   OR (
     lifecycle_status = 'processed'
     AND content_classification_json = '{}'::jsonb
   )
ORDER BY published_at_ms ASC, news_item_id ASC
LIMIT %s
FOR UPDATE SKIP LOCKED
```

- Add a repository unit test that asserts the predicate text still matches the partial index predicate, so future edits do not silently bypass the index.

#### `list_source_quality_inputs_for_targets`

- Replace `window_items AS SELECT items.*` with a narrow CTE:

```sql
window_items AS (
  SELECT
    items.news_item_id,
    items.source_id,
    items.published_at_ms,
    items.fetched_at_ms,
    items.lifecycle_status
  FROM source_rows AS sources
  JOIN news_items AS items ON items.source_id = sources.source_id
  WHERE items.published_at_ms >= %s
    AND items.published_at_ms <= %s
)
```

- Keep all existing aggregate outputs unchanged:
  - `fetch_run_count`
  - `fetch_success_count`
  - `items_fetched`
  - `items_inserted`
  - `items_duplicate`
  - `item_count`
  - `processed_item_count`
  - `latest_item_published_at_ms`
  - `median_lag_ms`
  - `mention_count`
  - `resolved_mention_count`
  - `fact_count`
  - `attention_fact_count`
  - `accepted_fact_count`
  - `ready_brief_count`
  - `context_item_count`
  - `context_parent_item_count`
  - `useful_item_count`

- Keep `source_quality_projection` service API unchanged.

#### `replace_page_rows_for_items`

- Keep behavior unchanged.
- The new `ix_news_page_rows_news_item` index must support:

```sql
DELETE FROM news_page_rows
 WHERE news_item_id = ANY(%s::text[])
   AND NOT (row_id = ANY(%s::text[]))
```

No batch upsert rewrite in this cut; the current top issue is delete path and table/index bloat, not per-row insert CPU.

## Worker Manifest / Runtime Contract

### `src/parallax/app/runtime/worker_manifest.py`

- Fix `news_page_projection` read-model identity from non-existent `page_id` to actual stable key `row_id`:

```python
current_read_model_identities=(("news_page_rows", ("row_id",)),),
```

- Keep `news_item_process` without `dirty_target_tables`; it is a lifecycle-state claimer over `news_items`, and the hot path is made bounded by `ix_news_items_unprocessed_claim`.

### `tests/architecture/test_worker_runtime_contracts.py`

- Update expected `news_page_rows` identity to `row_id`.
- Add a hard-cut assertion:

```python
def test_news_manifest_does_not_reference_nonexistent_page_id() -> None:
    manifest = require_worker_manifest("news_page_projection")
    assert manifest.current_read_model_identities == (("news_page_rows", ("row_id",)),)
```

## Tests

### OpenNews REST-only client

Modify:

- `tests/unit/integrations/news_feeds/test_opennews_client.py`

Add failing tests first:

```python
def test_opennews_client_uses_rest_only_and_never_connects_websocket() -> None:
    calls: list[dict[str, object]] = []

    async def post_json(url: str, *, token: str, body: dict[str, object]) -> dict[str, object]:
        calls.append({"url": url, "token": token, "body": body})
        return {
            "data": [
                {
                    "id": "article-1",
                    "text": "BTC ETF approval",
                    "newsType": "Bloomberg",
                    "engineType": "news",
                    "link": "https://example.com/btc-etf",
                    "coins": [{"symbol": "BTC", "signal": "long", "score": 88}],
                    "aiRating": {"status": "done", "score": 88, "signal": "long"},
                    "ts": 1_700_000_000_000,
                }
            ]
        }

    client = OpenNewsFeedClient(token="token", post_json=post_json, now_ms=lambda: 1_700_000_100_000)
    result = client.fetch(
        "opennews://subscribe",
        source={"fetch_policy_json": {"engineTypes": {"news": []}, "hasCoin": True, "rest_limit": 100}},
        cursor={},
        limit=100,
    )

    assert result.status_code == 200
    assert result.feed["transport"] == "rest"
    assert calls == [
        {
            "url": "https://ai.6551.io/open/news_search",
            "token": "token",
            "body": {"limit": 100, "page": 1, "engineTypes": {"news": []}, "hasCoin": True},
        }
    ]
```

```python
def test_opennews_client_rejects_removed_websocket_policy_keys() -> None:
    client = OpenNewsFeedClient(token="token", post_json=lambda **_: {"data": []})

    with pytest.raises(ValueError, match="removed OpenNews websocket policy keys"):
        client.fetch(
            "opennews://subscribe",
            source={"fetch_policy_json": {"fetch_mode": "hybrid", "max_messages": 20}},
            cursor={},
        )
```

Remove or rewrite tests that assert WebSocket subscription, ack, push receive, or hybrid merge. They are obsolete, not compatibility contracts.

### Provider wiring

Modify:

- `tests/unit/test_bootstrap_worker_runtime_wiring.py`
- `tests/unit/integrations/news_feeds/test_provider_registry.py`

Assertions:

```python
def test_news_provider_wiring_constructs_opennews_without_websocket_settings() -> None:
    settings = Settings(news_intel={"opennews": {"api_token": "token", "api_base_url": "https://ai.6551.io"}})
    provider = news_feed_client(settings)
    assert "opennews" in provider.supported_provider_types()
```

`test_provider_registry.py` should assert cursor/limit/source pass-through, not WS shape.

### Settings hard cut

Modify:

- `tests/unit/test_settings.py`

Replace expectations:

```python
assert "fetch_mode" not in opennews_sources["opennews-news"].fetch_policy
assert "stream_timeout_seconds" not in opennews_sources["opennews-news"].fetch_policy
assert "max_messages" not in opennews_sources["opennews-news"].fetch_policy
assert settings.news_intel.opennews.api_base_url == "https://ai.6551.io"
assert not hasattr(settings.news_intel.opennews, "wss_url")
```

Add rejection test:

```python
def test_opennews_rejects_removed_websocket_policy_keys() -> None:
    with pytest.raises(ValidationError, match="removed OpenNews websocket policy keys"):
        Settings.model_validate(
            {
                "news_intel": {
                    "sources": [
                        {
                            "source_id": "opennews-news",
                            "provider_type": "opennews",
                            "feed_url": "opennews://subscribe",
                            "source_domain": "6551.io",
                            "source_name": "OpenNews News",
                            "enabled": True,
                            "fetch_policy": {"fetch_mode": "hybrid"},
                        }
                    ]
                }
            }
        )
```

### Migration/schema tests

Modify:

- `tests/unit/test_postgres_schema.py`

Add tests:

```python
def test_news_hotpath_migration_cleans_no_start_backpressure_runs() -> None:
    migration = _read_migration("20260528_0118_news_realtime_postgres_hotpath_hard_cut.py")
    assert "DELETE FROM news_item_agent_runs" in migration
    assert "execution_started = false" in migration
    assert "backpressure_circuit_open" in migration
    assert "backpressure_capacity_denied" in migration
```

```python
def test_news_hotpath_migration_adds_claim_and_projection_indexes() -> None:
    migration = _read_migration("20260528_0118_news_realtime_postgres_hotpath_hard_cut.py")
    assert "ix_news_items_unprocessed_claim" in migration
    assert "ix_news_page_rows_news_item" in migration
    assert "ix_news_projection_dirty_projection_due" in migration
    assert "ix_news_context_items_source_effective_time" in migration
```

```python
def test_news_hotpath_migration_cleans_opennews_provider_signal_brief_targets() -> None:
    migration = _read_migration("20260528_0118_news_realtime_postgres_hotpath_hard_cut.py")
    assert "DELETE FROM news_projection_dirty_targets" in migration
    assert "projection_name = 'brief_input'" in migration
    assert "sources.provider_type = 'opennews'" in migration
    assert "provider_signal_json ->> 'source' = 'provider'" in migration
```

### Repository query tests

Modify:

- `tests/unit/domains/news_intel/test_news_repository_queries.py`

Add:

```python
def test_list_source_quality_inputs_uses_narrow_window_items_cte() -> None:
    conn = RecordingConnection()
    repo = NewsRepository(conn)
    repo.list_source_quality_inputs_for_targets(source_windows=[("opennews-news", "24h")], now_ms=1_700_000_000_000)
    sql = conn.sql
    assert "SELECT items.*" not in sql
    assert "items.news_item_id" in sql
    assert "items.source_id" in sql
    assert "items.published_at_ms" in sql
    assert "items.fetched_at_ms" in sql
    assert "items.lifecycle_status" in sql
```

```python
def test_list_unprocessed_items_predicate_matches_partial_index_contract() -> None:
    conn = RecordingConnection()
    repo = NewsRepository(conn)
    repo.list_unprocessed_items(limit=10, now_ms=1_700_000_000_000)
    sql = conn.sql
    assert "lifecycle_status IN ('raw', 'process_failed')" in sql
    assert "content_classification_json = '{}'::jsonb" in sql
    assert "ORDER BY published_at_ms ASC, news_item_id ASC" in sql
```

### Architecture tests

Modify or add:

- `tests/architecture/test_news_intel_boundaries.py`
- `tests/architecture/test_runtime_performance_architecture_hard_cut.py`

Add hard-cut assertions:

```python
def test_opennews_runtime_has_no_websocket_short_poll_path() -> None:
    client = _read("src/parallax/integrations/news_feeds/opennews_client.py")
    assert "websockets.connect" not in client
    assert "news.subscribe" not in client
    assert "news.unsubscribe" not in client
    assert "fetch_mode" not in client
```

```python
def test_news_fetch_docs_do_not_describe_hybrid_opennews() -> None:
    docs = _read("docs/WORKERS.md") + _read("src/parallax/domains/news_intel/ARCHITECTURE.md")
    assert "hybrid" not in docs.lower()
    assert "short-lived websocket" not in docs.lower()
```

## Execution Tasks

### Task 1: Branch And Baseline

**Files:** no repository edits.

- [ ] Create worktree and confirm branch.
- [ ] Run config path check.
- [ ] Capture readyz worker state.
- [ ] Capture `pg_stat_statements` top News SQL.
- [ ] Capture cleanup target counts.

Verification:

```bash
git status --short
uv run parallax config
docker compose exec -T app parallax db health
```

### Task 2: OpenNews REST-Only Tests

**Files:**

- Modify: `tests/unit/integrations/news_feeds/test_opennews_client.py`
- Modify: `tests/unit/integrations/news_feeds/test_provider_registry.py`

- [ ] Add REST-only test.
- [ ] Add removed-WS-policy rejection test.
- [ ] Rewrite provider registry wording away from WS.
- [ ] Run:

  ```bash
  uv run pytest tests/unit/integrations/news_feeds/test_opennews_client.py tests/unit/integrations/news_feeds/test_provider_registry.py -q
  ```

  Expected before implementation: failures referencing current WS/hybrid behavior.

### Task 3: Remove OpenNews WS Runtime

**Files:**

- Modify: `src/parallax/integrations/news_feeds/opennews_client.py`
- Modify: `src/parallax/integrations/news_feeds/provider_registry.py`

- [ ] Delete WS constants, constructor args, connect helpers, subscribe/unsubscribe handling.
- [ ] Implement REST-only `fetch()`.
- [ ] Reject removed WS policy keys.
- [ ] Run:

  ```bash
  uv run pytest tests/unit/integrations/news_feeds/test_opennews_client.py tests/unit/integrations/news_feeds/test_provider_registry.py -q
  ```

  Expected: pass.

### Task 4: Hard-Cut OpenNews Config Surface

**Files:**

- Modify: `src/parallax/platform/config/settings.py`
- Modify: `src/parallax/app/runtime/provider_wiring/news.py`
- Modify: `tests/unit/test_settings.py`
- Modify: `tests/unit/test_bootstrap_worker_runtime_wiring.py`

- [ ] Remove `wss_url` and `connect_timeout_seconds` from `OpenNewsSettings`.
- [ ] Remove WS keys from built-in OpenNews source policies.
- [ ] Add validator rejecting removed WS policy keys.
- [ ] Update provider wiring to pass only token and REST base URL.
- [ ] Run:

  ```bash
  uv run pytest tests/unit/test_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py -q
  ```

  Expected: pass.

### Task 5: PostgreSQL Hotpath Migration Tests

**Files:**

- Modify: `tests/unit/test_postgres_schema.py`

- [ ] Add tests for cleanup SQL.
- [ ] Add tests for new indexes.
- [ ] Add tests for OpenNews provider-signal brief target cleanup.
- [ ] Run:

  ```bash
  uv run pytest tests/unit/test_postgres_schema.py -q
  ```

  Expected before migration: failure because `20260528_0118` does not exist.

### Task 6: PostgreSQL Hotpath Migration

**Files:**

- Create: `src/parallax/platform/db/alembic/versions/20260528_0118_news_realtime_postgres_hotpath_hard_cut.py`

- [ ] Add migration metadata.
- [ ] Add no-start run cleanup.
- [ ] Add OpenNews provider-signal brief target cleanup.
- [ ] Add claim/page/projection/context indexes in `autocommit_block`.
- [ ] Add `ANALYZE`.
- [ ] Run:

  ```bash
  uv run pytest tests/unit/test_postgres_schema.py -q
  ```

  Expected: pass.

### Task 7: Source Quality Query Narrowing

**Files:**

- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `tests/unit/domains/news_intel/test_news_repository_queries.py`
- Verify existing integration: `tests/integration/domains/news_intel/test_news_source_quality_repository.py`

- [ ] Add repository SQL tests.
- [ ] Replace `SELECT items.*` in source-quality `window_items`.
- [ ] Keep aggregate output names unchanged.
- [ ] Run:

  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/integration/domains/news_intel/test_news_source_quality_repository.py -q
  ```

  Expected: pass.

### Task 8: Worker Manifest Identity Fix

**Files:**

- Modify: `src/parallax/app/runtime/worker_manifest.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`

- [ ] Change `news_page_rows` current identity from `page_id` to `row_id`.
- [ ] Add architecture assertion.
- [ ] Run:

  ```bash
  uv run pytest tests/architecture/test_worker_runtime_contracts.py -q
  ```

  Expected: pass.

### Task 9: Docs Hard Cut

**Files:**

- Modify: `src/parallax/domains/news_intel/ARCHITECTURE.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/RELIABILITY.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `tests/architecture/test_news_intel_boundaries.py`
- Modify: `tests/architecture/test_runtime_performance_architecture_hard_cut.py`

- [ ] Update docs to REST-only OpenNews fetch.
- [ ] Add invariant forbidding short-lived WS inside `news_fetch`.
- [ ] Add architecture tests.
- [ ] Run:

  ```bash
  uv run pytest tests/architecture/test_news_intel_boundaries.py tests/architecture/test_runtime_performance_architecture_hard_cut.py -q
  ```

  Expected: pass.

### Task 10: Runtime Config Cutover

**Files:** operator-owned `~/.parallax/config.yaml`; do not commit.

- [ ] Remove old OpenNews WS keys from operator config.
- [ ] Disable `opennews-onchain` unless operator confirms live data.
- [ ] Validate config without printing secrets:

  ```bash
  uv run parallax config
  ```

  Expected: no validation error; paths point at `~/.parallax/`.

### Task 11: Full Test Gate

**Files:** no edits.

- [ ] Run targeted suite:

  ```bash
  uv run pytest \
    tests/unit/integrations/news_feeds/test_opennews_client.py \
    tests/unit/integrations/news_feeds/test_provider_registry.py \
    tests/unit/domains/news_intel \
    tests/integration/domains/news_intel \
    tests/unit/test_settings.py \
    tests/unit/test_bootstrap_worker_runtime_wiring.py \
    tests/unit/test_postgres_schema.py \
    tests/architecture/test_news_intel_boundaries.py \
    tests/architecture/test_worker_runtime_contracts.py \
    tests/architecture/test_runtime_performance_architecture_hard_cut.py -q
  ```

- [ ] Run project gate:

  ```bash
  make check-all
  ```

  Expected: exit code 0.

### Task 12: Docker Rebuild And Live Verification

**Files:** no edits.

- [ ] Rebuild and start:

  ```bash
  docker compose build app
  docker compose up -d
  docker compose ps
  ```

- [ ] Confirm migration:

  ```bash
  docker compose exec -T app parallax db health
  ```

  Expected: `migration_version=20260528_0119`, `migration_status=ready`.

- [ ] Confirm OpenNews fetch no longer fails on WS handshake:

  ```bash
  docker compose exec -T postgres psql -U parallax_app -d parallax -P pager=off -c "
  SELECT source_id, status, http_status, fetched_count, inserted_count, updated_count,
         duplicate_count, left(coalesce(error,''),180) AS error
  FROM news_fetch_runs
  ORDER BY started_at_ms DESC
  LIMIT 12;"
  ```

  Expected: no `timed out during opening handshake`; OpenNews REST rows use `http_status=200`.

- [ ] Confirm cleanup:

  ```bash
  docker compose exec -T postgres psql -U parallax_app -d parallax -P pager=off -c "
  SELECT count(*) AS no_start_backpressure
  FROM news_item_agent_runs
  WHERE execution_started=false
    AND outcome IN ('backpressure_circuit_open','backpressure_capacity_denied');

  SELECT projection_name, count(*) AS total,
         count(*) FILTER (
           WHERE due_at_ms <= (extract(epoch from now())*1000)::bigint
             AND (leased_until_ms IS NULL OR leased_until_ms <= (extract(epoch from now())*1000)::bigint)
         ) AS due
  FROM news_projection_dirty_targets
  GROUP BY projection_name
  ORDER BY total DESC;"
  ```

  Expected: `no_start_backpressure=0`; `brief_input` due count materially lower.

- [ ] Confirm query plans:

  ```bash
  docker compose exec -T postgres psql -U parallax_app -d parallax -P pager=off -c "
  BEGIN;
  EXPLAIN (ANALYZE, BUFFERS)
  WITH picked AS (
    SELECT news_item_id
    FROM news_items
    WHERE lifecycle_status IN ('raw','process_failed')
       OR (lifecycle_status='processed' AND content_classification_json='{}'::jsonb)
    ORDER BY published_at_ms ASC, news_item_id ASC
    LIMIT 10
    FOR UPDATE SKIP LOCKED
  )
  SELECT count(*) FROM picked;
  ROLLBACK;"
  ```

  Expected: uses `ix_news_items_unprocessed_claim` or has near-zero execution time when no work exists; no seq scan over all `news_items`.

- [ ] Confirm API and live stream:

  ```bash
  python - <<'PY'
  import httpx, json
  ready = httpx.get("http://127.0.0.1:8765/readyz", timeout=10, trust_env=False).json()
  print(json.dumps({
      "ok": ready["ok"],
      "news_fetch": ready["workers"]["news_fetch"]["last_result"],
      "news_item_brief": ready["workers"]["news_item_brief"]["queue_depth"],
      "news_page_projection": ready["workers"]["news_page_projection"]["queue_depth"],
  }, ensure_ascii=False))
  PY
  ```

  Then run the existing authenticated `/api/news` and `/ws/live` smoke commands used in the previous verification. Do not print token values.

## Rollout Order

1. Implement and merge code/migration/docs in the feature branch.
2. Before deploying the new image, update `~/.parallax/config.yaml` to remove removed WS keys.
3. Build image.
4. Run migrations.
5. Start app.
6. Verify `news_fetch` succeeds via REST and no WS handshake errors appear.
7. Verify cleanup and query plans.
8. Record verification in `docs/superpowers/plans/active/2026-05-28-news-realtime-postgres-hotpath-hard-cut-verification-cn.md`.

## Rollback

- Code rollback requires restoring the previous image and restoring operator config with old OpenNews WS keys. This is not the preferred path because the change is a hard cut.
- Database migration downgrade drops only new indexes. Deleted no-start backpressure rows and deleted provider-signal `brief_input` dirty targets are intentionally not restored.
- If REST OpenNews fails after deploy, keep WS disabled and diagnose `/open/news_search` auth/rate-limit behavior. Do not reintroduce short-lived WS in `news_fetch`.
- If query performance regresses, keep the migration and add missing indexes in a follow-up revision; do not remove cleanup.

## Acceptance Criteria

- AC1: WHEN `news_fetch` processes OpenNews THEN it SHALL call REST `/open/news_search` only and SHALL NOT open a WebSocket.
- AC2: WHEN OpenNews config contains removed WS keys THEN config validation SHALL fail fast before runtime starts.
- AC3: WHEN a WS handshake would have failed previously THEN News fetch SHALL still complete through REST because WS is not in the code path.
- AC4: WHEN migration `20260528_0118` completes THEN historical no-start backpressure rows SHALL be deleted from `news_item_agent_runs`.
- AC5: WHEN migration completes THEN OpenNews provider-signal items SHALL not retain obsolete `brief_input` dirty targets.
- AC6: WHEN `news_item_process` is idle THEN its claim query SHALL avoid a full seq scan over `news_items`.
- AC7: WHEN source-quality projection runs THEN its aggregate SQL SHALL avoid wide `SELECT items.*` materialization.
- AC8: WHEN page projection replaces rows THEN deletes by `news_item_id` SHALL have a supporting index.
- AC9: WHEN worker manifests are checked THEN `news_page_rows` SHALL use `row_id`, not non-existent `page_id`.
- AC10: WHEN Docker is rebuilt and started THEN `/readyz`, `/api/news`, and authenticated `/ws/live` smoke checks SHALL pass with no OpenNews WS handshake errors in recent fetch runs.

## Final Verification Commands

```bash
uv run ruff check .
uv run pytest \
  tests/unit/integrations/news_feeds/test_opennews_client.py \
  tests/unit/integrations/news_feeds/test_provider_registry.py \
  tests/unit/domains/news_intel \
  tests/integration/domains/news_intel \
  tests/unit/test_settings.py \
  tests/unit/test_bootstrap_worker_runtime_wiring.py \
  tests/unit/test_postgres_schema.py \
  tests/architecture/test_news_intel_boundaries.py \
  tests/architecture/test_worker_runtime_contracts.py \
  tests/architecture/test_runtime_performance_architecture_hard_cut.py -q
make check-all
docker compose build app
docker compose up -d
docker compose exec -T app parallax db health
```

Post-deploy SQL checks:

```sql
SELECT count(*) AS no_start_backpressure
FROM news_item_agent_runs
WHERE execution_started=false
  AND outcome IN ('backpressure_circuit_open','backpressure_capacity_denied');

SELECT source_id, status, http_status, fetched_count, inserted_count, updated_count,
       duplicate_count, left(coalesce(error,''),180) AS error
FROM news_fetch_runs
ORDER BY started_at_ms DESC
LIMIT 12;

SELECT queryid, calls, round(total_exec_time::numeric,1) AS total_ms,
       round(mean_exec_time::numeric,2) AS mean_ms,
       shared_blks_read, temp_blks_written,
       left(regexp_replace(query,'\s+',' ','g'),220) AS q
FROM pg_stat_statements
WHERE query ILIKE '%news_%'
ORDER BY total_exec_time DESC
LIMIT 15;
```

## Self-Review

- Spec coverage: OpenNews short-lived WS removal, config hard cut, cleanup, PostgreSQL hot indexes, source-quality SQL narrowing, manifest identity, docs, Docker verification are all covered by tasks.
- Placeholder scan: no `TBD`, `TODO`, or unspecified “add tests” remains; every task names files and commands.
- Type consistency: `OpenNewsFeedClient.fetch()` remains the provider contract used by `OpenNewsNewsFeedProvider`; removed settings are also removed from provider wiring and tests.
- Compatibility scan: plan intentionally rejects old WS policy keys and does not retain hybrid/websocket fetch mode.
