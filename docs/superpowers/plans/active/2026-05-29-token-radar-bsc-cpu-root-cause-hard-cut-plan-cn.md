# Token Radar BSC / CPU Root Cause Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从根上修掉 Token Radar 长窗口 BSC 榜单为空、PostgreSQL source populate 过宽导致 CPU/IO spike、以及 Equity hard-delete 残留导致 `/readyz` 反复红的问题。

**Architecture:** PostgreSQL material facts 仍是唯一业务真相；Token Radar 的在线榜单必须由稳定 product key 驱动。`venue/chain` 是服务端榜单维度，不是前端在全局 top-N 上做的展示过滤；source edge 是 windowless narrow event-target edge，只回答“这个 event 当前属于哪个 target”，不承担 profile/social/identity/event-price/latest-market/feature hydrate；window/scope/venue 只在 feature/rank/current 层出现；已删除的 Equity/Earnings runtime contract 不保留 disabled placeholder、shadow queue、fallback reader 或兼容表。

**Tech Stack:** Python 3.13, FastAPI, psycopg, PostgreSQL 18, Alembic, pytest, React/Vite/TypeScript, TanStack Query, Docker Compose, pg_stat_statements.

**Status:** Revised after subagent SQL/KISS audit. 不实现 News；不做兼容壳；允许 destructive rebuild 派生 read model。

**Implementation checkpoint (2026-05-29 12:15 CST):** core hard cut landed in code. Token Radar now has server-side
`venue` product keys, narrow windowless source event edges, a separate source dirty event queue, target-only market/repair
dirty queue, API/frontend server-side venue selection, cross-domain readers pinned to `venue='all'`, and worker manifest /
queue health coverage for the new queue. The leftover frontend `tokenRadarVenueMatches` compatibility helper was removed
and guarded against reintroduction. Verification so far: 252 backend focused tests passed with 1 expected skip; frontend
component tests, typecheck, and lint passed; the final venue architecture guard, ruff, and diff check also passed.

**Remaining operational checkpoint:** runtime migration/rebuild/restart and live post-rollout checks are not executed by
this code-level checkpoint. The next operator step is Task 8 Step 2-6: apply migration/image rollout, rebuild Token Radar
derived rows, verify BSC `5m/1h/4h/24h`, `/readyz`, and `pg_stat_statements` temp-block deltas, then write the verification
artefact.

---

## Current Evidence

- `4h/all` 有 BSC eligible candidates 22 个，但第一个 BSC 实际 rank 是 33；`24h/all` 有 BSC eligible candidates 142 个，但第一个 BSC 实际 rank 是 22。当前后端只发布全局 top20，所以前端本地筛 BSC 后为空。
- `/api/token-radar` 只有 `window/scope/limit`，没有 `venue/chain` 参数；`TokenRadarTable` 在前端用 `tokenRadarVenueMatches(...)` 过滤已经返回的全局结果。
- 旧 target-wide runtime populate 已经消失；当前 spike 是 event-id-bounded source populate，但 SQL 仍 JOIN identity/profile/social/enriched/event-market/latest-market，并做两次 `row_number()`、整行 `to_jsonb + sha256`、108 列 insert、约 100 列 update、stale delete，采样等待为 `IO / BuffileWrite`。
- 只读审计确认这不是历史残留：45 秒采样里新 `source_event_ids_json` populate 仍跑 4 次，写 temp 18,011 blocks，约 141MB；累计 pg_stat 两个 source-populate fingerprint 已写约 8GB temp blocks。
- `token_radar_rank_source_events` 当前约 108 列，约 40k-50k rows 就达到约 156MB；这是“热路径行太宽 + 重复搬运宽行”，不是单纯数据量过大。
- `/readyz` 反复红的直接原因是 `WorkerManifest` 仍声明 `equity_event_page_projection` 和 `equity_event_projection_dirty_targets`，但运行库里该表缺失。disabled worker 不能豁免 manifest/schema health contract。

## P0 / P1 / P2 Root-Cause Coverage

| Priority | Work | Root cause solved? | Why |
| --- | --- | --- | --- |
| P0-A | Token Radar 服务端 per-venue/per-chain 榜单 product key | Yes for BSC empty long windows | 让 `venue` 进入 publication/current-row identity，BSC 请求排名 BSC universe，而不是过滤全局 top20。 |
| P0-B | Equity/Earnings runtime contract hard-delete | Yes for `/readyz queue_table_unavailable` | 从 manifest、queue health、factory、settings、docs/tests 删除 runtime contract；不再检查不存在的 queue table。 |
| P0-C | 重建 Token Radar source-edge 边界 | Yes for current CPU/IO spike shape | source edge 改为 windowless narrow event-target edge；source populate 禁止 profile/social/identity/enriched/market/latest hydrate、宽窗口排序、整行 JSON hash、宽 upsert。 |
| P0-D | 拆分 source dirty event-edge queue 与 target feature/current queue | Yes for source-id union / window-scope amplification recurrence | source dirty 只表示 event-target membership/hash 变化；target dirty 表示 market/event-payload/repair 触发的 feature/current 刷新，不再在 target row 里 union 一坨 `source_event_ids_json`。 |
| P1 | Feature projection hydrate isolation and selected-row IO budget | Yes for residual bounded cost | profile/social/identity/event-anchor/latest-market 在 feature projection 里按 selected source ids/target ids 读取，不能回到 source populate。 |
| P2 | PostgreSQL maintenance, observability, rebuild/runbook | Partially, not root by itself | `ANALYZE`、局部 `work_mem`、indexes、pg_stat gates 只能控制风险；不能替代 product key、source-edge 边界和 queue 边界 hard cut。 |

## PostgreSQL Best Practice For The Wide-Query Problem

本质原因不是“Postgres 不够快”，也不是 `work_mem` 太小，而是热路径把不同生命周期的工作混成一条宽 SQL：source event 归属、profile/social/identity hydrate、event anchor hydrate、latest market overlay、window/scope 复制、排序去重、整行 hash、宽 upsert 和 stale cleanup。只要宽 JOIN 的中间行参与 `row_number()`、hash、upsert 或 delete，即使入口是 event-id bounded，也会产生 temp spill、CPU、WAL、shared buffer 和 autovacuum 压力。

最佳实践在本项目里应落成这些硬规则：

- 热路径先选窄 key：`event_id`, `intent_id`, `resolution_id`, `target_type`, `target_id`, `received_at_ms`；不要在排序/去重阶段携带 JSONB、text payload、market 数字块。
- 两阶段 hydrate：先写 windowless source-edge scalar facts，再对被选中的 target/window/scope/venue 做 feature projection 和 selected-row hydrate。
- 避免宽行窗口函数：`row_number()` 的 partition/order 输入必须是窄列；需要 explain 证明不再写 temp blocks。
- JSONB/TOAST 不参与 hot sort/hash：JSON 只在最终 row payload 或少量 selected rows 阶段生成。
- source populate 禁止 `market_tick_current`, `latest_price_`, `latest_market_`, `event_price_`, `account_profiles`, `social_event_extractions`, `asset_identity_current`, `registry_assets`, `cex_tokens`, `price_feeds`, `enriched_events`, `market_ticks`, `row_number() OVER`, `to_jsonb(ranked_source)`, whole-row JSON hash；这些属于 feature projection 或 selected hydrate。
- partial index 必须精确匹配 runtime predicate；例如 `is_current = true`、target type、provider/status 等条件要和 SQL 谓词一致。
- CTE 不作为“整理代码”的默认工具；需要 materialization 时显式证明。宽 CTE 不是边界，派生表/read model 才是边界。
- worker idle path 不能通过 broad scan 证明无事可做；只 claim durable dirty targets 或 explicit ops repair enqueue。
- `work_mem` 只可作为短期 per-transaction guardrail，例如 `SET LOCAL work_mem = '64MB'` 包裹已确认的小批量投影；不能用全局调大掩盖宽 SQL。
- 每个 hard cut 必须用 `pg_stat_statements` delta、`EXPLAIN (ANALYZE, BUFFERS, WAL)`、temp block gate 和 `/readyz` 验证，而不是只看 API 有数据。

---

## File Structure

### Create

- `tests/architecture/test_token_radar_venue_leaderboard_contract.py`
- `tests/architecture/test_token_radar_source_width_contract.py`
- `tests/architecture/test_token_radar_sql_surface_inventory_contract.py`
- `tests/architecture/test_equity_runtime_hard_delete_contract.py`
- `tests/unit/domains/token_intel/test_token_radar_venue.py`
- `tests/unit/domains/token_intel/test_token_radar_source_event_edges.py`
- `tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py`
- `tests/unit/test_asset_flow_service_venue.py`
- `web/src/features/live/api/useTokenRadarQuery.test.ts`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py`
- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260529_0125_token_radar_venue_source_width_hard_cut.py`
- `docs/superpowers/plans/active/2026-05-29-token-radar-bsc-cpu-root-cause-verification-cn.md`

### Modify

- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260527_0111_token_radar_publication_state.py` tests only; do not rewrite historical migration unless test fixture requires string updates.
- `src/gmgn_twitter_intel/app/surfaces/api/routes_radar.py`
- `src/gmgn_twitter_intel/app/surfaces/api/validators.py`
- `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- `src/gmgn_twitter_intel/domains/token_intel/_constants.py`
- `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_dirty_target_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_rank_source_repository.py`
- `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_rank_source_query.py`
- `src/gmgn_twitter_intel/domains/token_intel/queries/event_token_projection_query.py` if reused for selected source hydrate
- `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/event_anchor_backfill_worker.py`
- `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
- `src/gmgn_twitter_intel/app/runtime/worker_manifest.py`
- `src/gmgn_twitter_intel/app/runtime/worker_factories/__init__.py`
- `src/gmgn_twitter_intel/app/runtime/worker_factories/equity_event_intel.py`
- `src/gmgn_twitter_intel/app/runtime/queue_health.py`
- `src/gmgn_twitter_intel/platform/config/settings.py`
- `web/src/features/live/api/useLiveRadarRouteData.ts`
- `web/src/features/live/api/useTokenRadarQuery.ts`
- `web/src/features/live/ui/TokenRadarTable.tsx`
- `web/src/shared/query/queryKeys.ts`
- `web/src/lib/venue.ts`
- `web/src/lib/types.ts` or generated OpenAPI types after contract regen
- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/RELIABILITY.md`
- `docs/CONTRACTS.md`
- `docs/references/POSTGRES_PERFORMANCE.md`
- `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`

### Delete When Equity/Earnings Is Fully Hard-Deleted

Follow and merge the existing scope in `docs/superpowers/plans/active/2026-05-29-earnings-hard-delete-plan-cn.md`; do not keep a local compatibility variant here. At minimum this plan must remove every runtime reference that causes queue health to inspect `equity_event_projection_dirty_targets`.

---

## Task 0: Baseline And Scope Lock

**Files:**
- Read: `AGENTS.md`
- Read: `docs/WORKERS.md`
- Read: `docs/WORKER_FLOW.md`
- Read: `docs/references/POSTGRES_PERFORMANCE.md`

- [ ] **Step 1: Confirm active config paths without printing secrets**

Run:

```bash
uv run gmgn-twitter-intel config
```

Expected:

```text
config_path=/Users/qinghuan/.gmgn-twitter-intel/config.yaml
workers_config_path=/Users/qinghuan/.gmgn-twitter-intel/workers.yaml
```

Do not copy tokens, proxy URLs, cookies, or DSNs.

- [ ] **Step 2: Capture pre-change runtime evidence**

Run:

```bash
curl -sS http://127.0.0.1:8765/readyz | jq '{ok,reasons,projection:.worker_lanes.projection}'
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -X -q -P pager=off -c "
SELECT to_regclass('public.equity_event_projection_dirty_targets') AS equity_queue_table;
SELECT \"window\", scope, venue, count(*) AS rows
FROM token_radar_current_rows
GROUP BY 1,2,3
ORDER BY 1,2,3;
"
```

Expected: command exits `0`. Save output into the verification file created in Task 8.

- [ ] **Step 3: Capture Token Radar SQL baseline**

Run a 60 second delta without resetting stats:

```bash
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -X -q -P pager=off -c "
SELECT now() AS captured_at,
       calls,
       round(total_exec_time::numeric, 2) AS total_ms,
       temp_blks_written,
       left(regexp_replace(query, '\s+', ' ', 'g'), 180) AS query
FROM pg_stat_statements
WHERE query ILIKE '%token_radar_rank_source_events%'
ORDER BY total_exec_time DESC
LIMIT 10;
"
sleep 60
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -X -q -P pager=off -c "
SELECT now() AS captured_at,
       calls,
       round(total_exec_time::numeric, 2) AS total_ms,
       temp_blks_written,
       left(regexp_replace(query, '\s+', ' ', 'g'), 180) AS query
FROM pg_stat_statements
WHERE query ILIKE '%token_radar_rank_source_events%'
ORDER BY total_exec_time DESC
LIMIT 10;
"
```

Expected: old target-wide SQL fingerprints do not increase; current source populate temp blocks provide the before number.

---

## Task 1: Add Failing Hard-Cut Guards First

**Files:**
- Create: `tests/architecture/test_token_radar_venue_leaderboard_contract.py`
- Create: `tests/architecture/test_token_radar_source_width_contract.py`
- Create: `tests/architecture/test_equity_runtime_hard_delete_contract.py`

- [ ] **Step 1: Add venue leaderboard architecture guard**

Create `tests/architecture/test_token_radar_venue_leaderboard_contract.py`:

```python
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_token_radar_api_accepts_server_side_venue() -> None:
    route = _text("src/gmgn_twitter_intel/app/surfaces/api/routes_radar.py")
    service = _text("src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py")
    repo = _text("src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py")

    assert "venue:" in route
    assert "_venue(" in route
    assert "venue=parsed_venue" in route
    assert "venue: str" in service
    assert "venue=venue" in service
    assert 'current_rows.venue = %s' in repo


def test_token_radar_current_identity_includes_venue() -> None:
    manifest = _text("src/gmgn_twitter_intel/app/runtime/worker_manifest.py")
    migration = _text(
        "src/gmgn_twitter_intel/platform/db/alembic/versions/"
        "20260529_0125_token_radar_venue_source_width_hard_cut.py"
    )

    assert '"token_radar_current_rows"' in manifest
    assert '"venue"' in manifest
    assert 'ADD COLUMN IF NOT EXISTS venue TEXT' in migration
    assert 'PRIMARY KEY(projection_version, "window", scope, venue)' in migration


def test_frontend_does_not_treat_client_filter_as_leaderboard_truth() -> None:
    hook = _text("web/src/features/live/api/useTokenRadarQuery.ts")
    query_keys = _text("web/src/shared/query/queryKeys.ts")
    table = _text("web/src/features/live/ui/TokenRadarTable.tsx")
    live_feature = _text("web/src/features/live/ui/LiveRadar.tsx")

    assert "venue" in hook
    assert "params: { window, limit, scope, venue }" in hook
    assert "tokenRadar: (window: WindowKey, scope: ScopeKey, venue:" in query_keys
    assert "items.filter((item) => tokenRadarVenueMatches(item, venueFilter))" not in table
    assert "tokenRadarVenueMatches(" not in table
    assert "tokenRadarVenueMatches(" not in live_feature
```

- [ ] **Step 2: Add source-width architecture guard**

Create `tests/architecture/test_token_radar_source_width_contract.py`:

```python
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_source_edge_populate_is_windowless_narrow_event_edge() -> None:
    query = _text(
        "src/gmgn_twitter_intel/domains/token_intel/queries/"
        "token_radar_rank_source_query.py"
    )
    populate = query.split("_POPULATE_RANK_SOURCE_EDGES_FOR_EVENT_IDS_SQL", 1)[1].split(
        "def ", 1
    )[0]

    assert "requested_event_ids" in populate
    forbidden = (
        "market_tick_current",
        "latest_price_",
        "latest_market_",
        "event_price_",
        "account_profiles",
        "social_event_extractions",
        "asset_identity_current",
        "registry_assets",
        "cex_tokens",
        "price_feeds",
        "enriched_events",
        "market_ticks",
        "row_number() OVER",
        "to_jsonb(ranked_source)",
        "sha256(",
    )
    offenders = [token for token in forbidden if token in populate]
    assert offenders == []


def test_rank_source_table_is_not_window_or_payload_coupled() -> None:
    migration = _text(
        "src/gmgn_twitter_intel/platform/db/alembic/versions/"
        "20260529_0125_token_radar_venue_source_width_hard_cut.py"
    )
    create_table = migration.split("CREATE TABLE token_radar_rank_source_events", 1)[1].split(
        ");", 1
    )[0]

    assert "source_kind" in create_table
    assert "source_id" in create_table
    assert '"window"' not in create_table
    assert "scope" not in create_table
    assert "source_payload_json" not in create_table
    assert "factor_snapshot_json" not in create_table
    assert len([line for line in create_table.splitlines() if line.strip() and "--" not in line]) <= 32


def test_source_dirty_is_event_edge_queue_not_target_union() -> None:
    projection = _text(
        "src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py"
    )
    source_dirty_repo = _text(
        "src/gmgn_twitter_intel/domains/token_intel/repositories/"
        "token_radar_source_dirty_event_repository.py"
    )
    target_dirty_repo = _text(
        "src/gmgn_twitter_intel/domains/token_intel/repositories/"
        "token_radar_dirty_target_repository.py"
    )

    assert "token_radar_source_dirty_events" in source_dirty_repo
    assert "source_event_id" in source_dirty_repo
    assert "source_event_ids_json = (" not in target_dirty_repo
    assert "jsonb_agg" not in target_dirty_repo
    assert "populate_edges_for_requests(" not in projection
    assert "populate_edges_for_event_ids(" in projection
```

- [ ] **Step 3: Add full Token Radar SQL surface inventory guard**

Create `tests/architecture/test_token_radar_sql_surface_inventory_contract.py`:

```python
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TOKEN_RADAR_SQL_SURFACES = (
    "src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_rank_source_query.py",
    "src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py",
    "src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_dirty_target_repository.py",
    "src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py",
    "src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py",
    "src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py",
    "src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py",
    "src/gmgn_twitter_intel/app/surfaces/api/routes_radar.py",
)


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_token_radar_sql_surface_inventory_is_explicit() -> None:
    offenders: list[str] = []
    for path in ROOT.rglob("*.py"):
        relpath = path.relative_to(ROOT).as_posix()
        if "alembic/versions/" in relpath or relpath.startswith("tests/"):
            continue
        text = path.read_text(encoding="utf-8")
        if "token_radar_" in text and any(sql in text for sql in ("SELECT ", "INSERT ", "UPDATE ", "DELETE ")):
            if relpath not in TOKEN_RADAR_SQL_SURFACES:
                offenders.append(relpath)
    assert sorted(offenders) == []


def test_token_radar_product_sql_has_no_venue_compatibility_fallback() -> None:
    forbidden = (
        "venue IS NULL",
        "COALESCE(current_rows.venue",
        "COALESCE(state.venue",
        "DEFAULT 'all' /* compatibility",
        "if venue is None",
    )
    offenders: list[str] = []
    for relpath in TOKEN_RADAR_SQL_SURFACES:
        text = _text(relpath)
        for token in forbidden:
            if token in text:
                offenders.append(f"{relpath} contains {token}")
    assert offenders == []


def test_all_current_publication_and_first_seen_sql_is_venue_scoped() -> None:
    repo = _text("src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py")

    assert 'AND current_rows.venue = %s' in repo
    assert 'AND state.venue = current_rows.venue' in repo
    assert 'ON CONFLICT(projection_version, "window", scope, venue)' in repo
    assert 'ON CONFLICT(projection_version, "window", scope, venue, target_type_key, identity_id)' in repo
    assert "stable_generation_id(" in repo
    assert '"venue": venue' in repo
```

Expected: implementation must update every Token Radar SQL surface deliberately. If another file touches `token_radar_*` SQL, add it to the inventory and justify it in the plan before coding.

- [ ] **Step 4: Add equity runtime hard-delete guard**

Create `tests/architecture/test_equity_runtime_hard_delete_contract.py`:

```python
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RUNTIME_FILES = (
    "src/gmgn_twitter_intel/app/runtime/worker_manifest.py",
    "src/gmgn_twitter_intel/app/runtime/queue_health.py",
    "src/gmgn_twitter_intel/app/runtime/worker_factories/__init__.py",
    "src/gmgn_twitter_intel/platform/config/settings.py",
    "docs/WORKERS.md",
)

FORBIDDEN = (
    "equity_event_page_projection",
    "equity_event_story_projection",
    "equity_event_brief",
    "equity_event_projection_dirty_targets",
)


def test_deleted_equity_runtime_contract_is_not_in_manifest_or_health() -> None:
    offenders: list[str] = []
    for relpath in RUNTIME_FILES:
        text = (ROOT / relpath).read_text(encoding="utf-8")
        for token in FORBIDDEN:
            if token in text:
                offenders.append(f"{relpath} contains {token}")
    assert offenders == []
```

- [ ] **Step 5: Run guards and verify they fail before implementation**

Run:

```bash
uv run pytest \
  tests/architecture/test_token_radar_venue_leaderboard_contract.py \
  tests/architecture/test_token_radar_source_width_contract.py \
  tests/architecture/test_token_radar_sql_surface_inventory_contract.py \
  tests/architecture/test_equity_runtime_hard_delete_contract.py \
  -q
```

Expected before implementation: FAIL. If any guard passes before code changes, tighten it until it proves the intended hard cut.

---

## Task 2: P0-A Add Server-Side Venue As Token Radar Product Key

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260529_0125_token_radar_venue_source_width_hard_cut.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/_constants.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py`
- Test: `tests/unit/domains/token_intel/test_token_radar_venue.py`

- [ ] **Step 1: Define canonical venue keys**

Add constants:

```python
TOKEN_RADAR_VENUES = ("all", "sol", "eth", "base", "bsc", "cex")
TOKEN_RADAR_DEFAULT_VENUE = "all"
```

Add a pure helper in `token_radar_projection.py` or a focused module under `domains/token_intel/services/`:

```python
def token_radar_venue_for_rank_input(row: dict[str, object]) -> str:
    target_type = str(row.get("target_type") or "")
    if target_type == "CexToken":
        return "cex"
    snapshot = row.get("factor_snapshot_json")
    subject = snapshot.get("subject") if isinstance(snapshot, dict) else {}
    chain = str((subject or {}).get("chain") or row.get("asset_chain_id") or "").lower()
    if chain in {"sol", "solana"}:
        return "sol"
    if chain in {"eth", "ethereum", "eip155:1"}:
        return "eth"
    if chain in {"base", "eip155:8453"}:
        return "base"
    if chain in {"bsc", "bnb", "bnb_chain", "eip155:56"}:
        return "bsc"
    return "all"
```

Expected: helper returns `bsc` for `eip155:56` and never relies on frontend display labels.

- [ ] **Step 2: Add migration for current rows and publication state venue identity**

Create `20260529_0125_token_radar_venue_source_width_hard_cut.py` with `down_revision = "20260529_0124"`.

Required SQL shape:

```sql
DELETE FROM token_radar_current_rows;
DELETE FROM token_radar_target_first_seen;
DROP TABLE IF EXISTS token_radar_publication_state CASCADE;

ALTER TABLE token_radar_current_rows ADD COLUMN IF NOT EXISTS venue TEXT NOT NULL DEFAULT 'all';
ALTER TABLE token_radar_current_rows DROP CONSTRAINT IF EXISTS token_radar_current_rows_projection_version_window_scope_lane_rank_key;
ALTER TABLE token_radar_current_rows DROP CONSTRAINT IF EXISTS token_radar_current_rows_projection_version_window_scope_lane_target_type_key_identity_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_token_radar_current_rows_venue_rank
  ON token_radar_current_rows(projection_version, "window", scope, venue, lane, rank);

CREATE UNIQUE INDEX IF NOT EXISTS idx_token_radar_current_rows_venue_target
  ON token_radar_current_rows(projection_version, "window", scope, venue, lane, target_type_key, identity_id);

DROP INDEX IF EXISTS idx_token_radar_current_rows_generation;
CREATE INDEX IF NOT EXISTS idx_token_radar_current_rows_generation
  ON token_radar_current_rows(projection_version, "window", scope, venue, generation_id, lane, rank);

CREATE TABLE token_radar_publication_state (
  projection_version TEXT NOT NULL,
  "window" TEXT NOT NULL,
  scope TEXT NOT NULL,
  venue TEXT NOT NULL DEFAULT 'all',
  current_generation_id TEXT,
  current_published_at_ms BIGINT,
  current_source_frontier_ms BIGINT,
  current_row_count BIGINT NOT NULL DEFAULT 0,
  current_source_rows BIGINT NOT NULL DEFAULT 0,
  latest_attempt_generation_id TEXT,
  latest_attempt_status TEXT NOT NULL CHECK (latest_attempt_status IN ('ready', 'failed')),
  latest_attempt_started_at_ms BIGINT,
  latest_attempt_finished_at_ms BIGINT,
  latest_attempt_error TEXT,
  updated_at_ms BIGINT NOT NULL,
  PRIMARY KEY(projection_version, "window", scope, venue),
  CHECK (latest_attempt_status = 'failed' OR current_generation_id = latest_attempt_generation_id)
);

ALTER TABLE token_radar_target_first_seen ADD COLUMN IF NOT EXISTS venue TEXT NOT NULL DEFAULT 'all';
ALTER TABLE token_radar_target_first_seen DROP CONSTRAINT IF EXISTS token_radar_target_first_seen_pkey;
ALTER TABLE token_radar_target_first_seen
  ADD PRIMARY KEY(projection_version, "window", scope, venue, target_type_key, identity_id);
```

Expected: old current rows and first-seen rows are rebuildable and can be deleted; no compatibility `venue IS NULL` path is introduced.

- [ ] **Step 3: Thread venue through repository reads and publication**

Modify repository methods so signatures require `venue: str`:

```python
latest_publication_state(projection_version=..., windows=..., scopes=..., venues=...)
current_rows_for_generation(window=..., scope=..., venue=..., generation_id=...)
latest_current_rows(window=..., scope=..., venue=...)
publish_current_generation(window=..., scope=..., venue=..., rows=...)
mark_publication_failed(window=..., scope=..., venue=...)
first_seen_by_identity(window=..., scope=..., venue=..., rows=...)
upsert_first_seen_batch(window=..., scope=..., venue=..., rows=...)
stable_generation_id(projection_version=..., window=..., scope=..., venue=..., rows=...)
```

Expected SQL predicates include:

```sql
AND current_rows.venue = %s
AND state.venue = current_rows.venue
```

No method should silently default missing venue except public API validator defaulting request input to `"all"`.

- [ ] **Step 4: Publish rank sets for all required venues without multiplying source population**

Modify `TokenRadarProjectionWorker` due work items to include venue:

```text
(window, scope, venue)
```

Modify `_rank_current_rows(...)`:

```python
rank_inputs = list_rank_inputs_for_rank_set(...)
if venue != "all":
    rank_inputs = [
        row for row in rank_inputs
        if token_radar_venue_for_rank_input(row) == venue
    ]
ranked = rank_compact_inputs(rank_inputs)
```

Expected: source-edge populate still runs once per source dirty event set; venue only affects ranking/publication from `token_radar_target_features`.

- [ ] **Step 5: Include venue in stable row id and manifest identity**

Update `_row_from_target_feature(...)` / row patching so `row_id` includes `venue`:

```python
_stable_id("token-radar-row", projection_version, window, scope, venue, lane, target_type_key, identity_id)
```

Update `WorkerManifest.current_read_model_identities`:

```python
("token_radar_rank_source_events", ("projection_version", "target_type_key", "identity_id", "source_kind", "source_id"))
("token_radar_current_rows", ("projection_version", "window", "scope", "venue", "lane", "target_type_key", "identity_id"))
("token_radar_publication_state", ("projection_version", "window", "scope", "venue"))
("token_radar_target_first_seen", ("projection_version", "window", "scope", "venue", "target_type_key", "identity_id"))
```

Expected: no generation/run/timestamp identity is introduced.

---

## Task 3: P0-A Add API And Frontend Server-Side Venue Contract

**Files:**
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/validators.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/routes_radar.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py`
- Modify: `web/src/features/live/api/useTokenRadarQuery.ts`
- Modify: `web/src/features/live/api/useLiveRadarRouteData.ts`
- Modify: `web/src/features/live/ui/TokenRadarTable.tsx`
- Modify: `web/src/shared/query/queryKeys.ts`
- Test: `tests/unit/test_asset_flow_service_venue.py`
- Test: `web/src/features/live/api/useTokenRadarQuery.test.ts`

- [ ] **Step 1: Add strict backend validator**

Add `_venue(value: str) -> str`:

```python
def _venue(value: str) -> str:
    parsed = str(value or "all").strip().lower()
    allowed = {"all", "sol", "eth", "base", "bsc", "cex"}
    if parsed not in allowed:
        raise ApiBadRequest("invalid_venue", field="venue")
    return parsed
```

Expected: unknown venue returns bad request; no fallback to `"all"` after invalid input.

- [ ] **Step 2: Thread venue through `/api/token-radar`**

Change route signature:

```python
venue: Annotated[str, Query()] = "all",
```

Return payload includes `venue`:

```python
return _json({"ok": True, "data": {"window": parsed_window, "scope": parsed_scope, "venue": parsed_venue, **data}})
```

Expected: `/api/token-radar?window=24h&scope=all&venue=bsc` reads BSC publication state, not global state.

- [ ] **Step 3: Remove frontend local filter as leaderboard truth**

Change `TokenRadarTable` props:

```ts
venue: TokenRadarVenueFilter;
onVenueChange: (venue: TokenRadarVenueFilter) => void;
```

Remove:

```ts
items.filter((item) => tokenRadarVenueMatches(item, venueFilter))
```

Use `items` directly as server-ranked rows. Delete `tokenRadarVenueMatches` if it exists solely for Token Radar filtering; otherwise guarantee zero imports/calls from `web/src/features/live/**`.

Expected: BSC tab changes the query key and HTTP params; it does not hide global rows after the backend already truncated them.

- [ ] **Step 4: Include venue in query cache keys**

Change:

```ts
tokenRadar: (window: WindowKey, scope: ScopeKey, venue: TokenRadarVenueFilter, limit: number) =>
  ["token-radar", window, scope, venue, limit] as const
```

Change hook params:

```ts
params: { window, limit, scope, venue }
```

Expected: switching BSC/SOL/ALL does not reuse stale global cache.

---

## Task 4: P0-B Hard-Delete Equity/Earnings Runtime Contract

**Files:**
- Modify/Delete per `docs/superpowers/plans/active/2026-05-29-earnings-hard-delete-plan-cn.md`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_manifest.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/queue_health.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/worker_factories/__init__.py`
- Modify/Delete: `src/gmgn_twitter_intel/app/runtime/worker_factories/equity_event_intel.py`
- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`
- Modify: `docs/WORKERS.md`
- Test: `tests/architecture/test_equity_runtime_hard_delete_contract.py`

- [ ] **Step 1: Choose hard delete, not queue-table compatibility**

Do not recreate `equity_event_projection_dirty_targets` only to make readiness green. Remove the worker contracts that reference it.

Expected forbidden runtime tokens after this task:

```text
equity_event_page_projection
equity_event_story_projection
equity_event_brief
equity_event_projection_dirty_targets
```

Allowed only in historical Alembic migrations and completed plan/verification artefacts.

- [ ] **Step 2: Remove Equity workers from manifest and factories**

Delete manifest entries for Equity/Earnings workers and remove the `equity_event_intel.py` factory from `EXPECTED_WORKER_FACTORY_FILES` / factory construction.

Expected: `all_worker_manifests()` no longer returns any worker name beginning with `equity_event_`.

- [ ] **Step 3: Remove queue health adapter and worker-specific filters**

Delete `QueueHealthAdapterSpec` for `equity_event_projection_dirty_targets` and filter rows:

```python
("equity_event_projection_dirty_targets", "equity_event_story_projection")
("equity_event_projection_dirty_targets", "equity_event_brief")
("equity_event_projection_dirty_targets", "equity_event_page_projection")
```

Expected: `/readyz` no longer queries the missing table.

- [ ] **Step 4: Remove settings/docs/tests compatibility references**

Remove worker settings keys from `Settings`, `config.example.yaml`, `docs/WORKERS.md`, and architecture tests. If the full Earnings product is deleted, run the existing earnings hard-delete plan completely in the same branch.

Expected: architecture guard passes; no disabled placeholder remains to preserve an old status shape.

---

## Task 5: P0-C Rebuild Windowless Narrow Source Edge

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_rank_source_query.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_rank_source_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- Test: `tests/unit/domains/token_intel/test_token_radar_source_event_edges.py`

- [ ] **Step 1: Recreate source-edge table as a narrow event-target read model**

Destructively rebuild `token_radar_rank_source_events`. It is rebuildable and must no longer preserve old wide-column compatibility.

Required shape:

```sql
DROP TABLE IF EXISTS token_radar_rank_source_events;

CREATE TABLE token_radar_rank_source_events (
  projection_version TEXT NOT NULL,
  target_type_key TEXT NOT NULL,
  identity_id TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_id TEXT NOT NULL,
  event_received_at_ms BIGINT NOT NULL,
  projected_at_ms BIGINT NOT NULL,
  source_payload_hash TEXT NOT NULL,
  intent_id TEXT,
  event_id TEXT,
  resolution_id TEXT,
  target_type TEXT,
  target_id TEXT,
  pricefeed_id TEXT,
  resolution_status TEXT,
  is_watched BOOLEAN NOT NULL DEFAULT false,
  PRIMARY KEY(projection_version, target_type_key, identity_id, source_kind, source_id)
);

CREATE INDEX idx_token_radar_rank_source_events_target_time
  ON token_radar_rank_source_events(
    projection_version,
    target_type_key,
    identity_id,
    event_received_at_ms DESC,
    source_id
  );

CREATE INDEX idx_token_radar_rank_source_events_watched
  ON token_radar_rank_source_events(projection_version, event_received_at_ms DESC)
  WHERE is_watched = true;
```

Expected: table has no `"window"`, `scope`, `generation_id`, JSON payload, profile/social columns, event-price columns, or latest-market columns. Column count stays <= 32.

- [ ] **Step 2: Split source-edge request type from feature/rank request type**

Remove `window`, `scope`, `analysis_since_ms`, `score_since_ms`, and `now_ms` from the request object passed to `populate_edges_for_event_ids(...)`.

Required shape:

```python
@dataclass(frozen=True)
class TokenRadarSourceEdgeRequest:
    source_event_id: str


@dataclass(frozen=True)
class TokenRadarFeatureSourceRequest:
    request_key: str
    target_type_key: str
    identity_id: str
    window: str
    scope: str
    venue: str
    analysis_since_ms: int
    now_ms: int
```

Expected: source-edge populate cannot accidentally fan out by window/scope/venue because those fields are not in its input contract.

- [ ] **Step 3: Make source populate answer only event current target**

`_POPULATE_RANK_SOURCE_EDGES_FOR_EVENT_IDS_SQL` must start from exact requested event ids and join only material facts needed to answer target ownership:

```sql
WITH requested_event_ids AS (
  SELECT DISTINCT source_event_id
  FROM jsonb_array_elements_text(%s::jsonb) AS ids(source_event_id)
),
source_edges AS (
  SELECT
    %s AS projection_version,
    resolution.target_type AS target_type_key,
    resolution.identity_id,
    'event' AS source_kind,
    events.event_id AS source_id,
    events.received_at_ms AS event_received_at_ms,
    %s AS projected_at_ms,
    digest(concat_ws('|', ...explicit scalar fields...), 'sha256') AS source_payload_hash,
    intents.intent_id,
    events.event_id,
    resolution.resolution_id,
    resolution.target_type,
    resolution.target_id,
    resolution.pricefeed_id,
    resolution.resolution_status,
    resolution.is_watched
  FROM requested_event_ids
  JOIN events ON events.event_id = requested_event_ids.source_event_id
  JOIN token_intents intents ON intents.event_id = events.event_id
  JOIN token_intent_resolutions resolution ON resolution.intent_id = intents.intent_id
  WHERE resolution.identity_id IS NOT NULL
)
INSERT INTO token_radar_rank_source_events (...)
SELECT ...
ON CONFLICT (...) DO UPDATE
SET ...
WHERE token_radar_rank_source_events.source_payload_hash IS DISTINCT FROM EXCLUDED.source_payload_hash;
```

Forbidden in this query:

```text
market_tick_current
latest_price_
latest_market_
event_price_
account_profiles
social_event_extractions
asset_identity_current
registry_assets
cex_tokens
price_feeds
enriched_events
market_ticks
row_number() OVER
to_jsonb(ranked_source)
sha256(to_jsonb
```

Expected: no window/scope fanout, no rank calculation, no broad fallback, no whole-row JSON hash. The write changes only rows whose explicit scalar hash changes.

- [ ] **Step 4: Move all hydrate and ranking decisions to selected-row feature projection**

Feature projection may query richer tables only after it has selected a bounded target/window/scope/venue work item and a bounded source-id list from the narrow edge table.

Allowed only outside source populate:

```python
source_edges = repos.token_radar_rank_sources.list_edges_for_targets(
    projection_version=...,
    targets=target_keys,
    since_ms=window_since_ms,
    limit_per_target=...
)
event_payloads = repos.token_radar_rank_sources.load_selected_event_payloads(
    source_ids=[edge.source_id for edge in source_edges]
)
latest_context = repos.token_radar_rank_sources.load_latest_market_context_for_targets(
    targets=target_keys
)
```

Expected: `account_profiles`, `social_event_extractions`, `asset_identity_current`, `registry_assets`, `cex_tokens`, `price_feeds`, `enriched_events`, `market_ticks`, and `market_tick_current` can appear in selected hydrate SQL, but not in source-edge populate SQL.

- [ ] **Step 5: Compute source rank after filtering, not during source-edge write**

If ranking needs source order, compute it from the narrow edge rows after applying the target/window/scope/venue request:

```sql
SELECT *,
       row_number() OVER (
         PARTITION BY projection_version, target_type_key, identity_id
         ORDER BY event_received_at_ms DESC, source_id DESC
       ) AS source_rank
FROM token_radar_rank_source_events
WHERE projection_version = %s
  AND event_received_at_ms >= %s
  AND (target_type_key, identity_id) = ANY(%s);
```

Expected: any window function input is narrow edge rows only. It must not carry hydrated event/profile/social/market payload columns.

- [ ] **Step 6: Rewrite source-edge prune and stale delete for windowless identity**

`prune_edges(...)` must no longer accept `window` or `scope`:

```sql
DELETE FROM token_radar_rank_source_events
WHERE projection_version = %s
  AND event_received_at_ms < %s;
```

Stale delete on resolution target movement must match only `(projection_version, source_kind, source_id)` and the current event-target edge; no window/scope/lane predicate remains.

Expected: source-edge retention is event-time based; product/window retention stays on `token_radar_target_features`, `token_radar_current_rows`, `token_radar_publication_state`, and `token_radar_target_first_seen`.

- [ ] **Step 7: Delete obsolete wide-column readers and writers**

Remove runtime references to dropped columns instead of leaving compatibility fallbacks:

```sql
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'token_radar_rank_source_events'
ORDER BY ordinal_position;
```

Expected: no production code reads `event_price_*`, `latest_price_*`, `source_payload_json`, profile/social/identity display columns, or window/scope from `token_radar_rank_source_events`.

- [ ] **Step 8: Prove the new source query avoids temp spill**

Run in a transaction on a representative request payload:

```sql
BEGIN;
EXPLAIN (ANALYZE, BUFFERS, WAL)
/* source-edge populate statement with a small event-id payload */;
ROLLBACK;
```

Expected: `temp read/write` is zero for normal batches. If temp appears, do not raise `work_mem` as the fix; reduce columns, batch shape, or ordering until source populate is truly narrow.

---

## Task 6: P0-D Split Source Dirty Event Queue From Target Feature Queue

**Files:**
- Create: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_dirty_target_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_rank_source_query.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/event_anchor_backfill_worker.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
- Test: `tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py`

- [ ] **Step 1: Create source dirty event-edge queue**

Add `token_radar_source_dirty_events` in the same migration:

```sql
CREATE TABLE token_radar_source_dirty_events (
  projection_version TEXT NOT NULL,
  target_type_key TEXT NOT NULL,
  identity_id TEXT NOT NULL,
  source_event_id TEXT NOT NULL,
  dirty_reason TEXT NOT NULL,
  payload_hash TEXT,
  due_at_ms BIGINT NOT NULL,
  claimed_by TEXT,
  claimed_until_ms BIGINT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  PRIMARY KEY(projection_version, target_type_key, identity_id, source_event_id)
);

CREATE INDEX idx_token_radar_source_dirty_events_claim
  ON token_radar_source_dirty_events(due_at_ms, claimed_until_ms, attempt_count);
```

Expected: source-dirty identity is the event-target edge. It is not embedded as an array inside `token_radar_dirty_targets`.

- [ ] **Step 2: Keep target dirty market-only**

`token_radar_dirty_targets` remains a target feature/current refresh queue. It may represent `market_dirty`, selected event-payload dirty, publication repair, or explicit target rebuild, but it must not store or aggregate source event ids.

Delete patterns:

```sql
source_event_ids_json = (
jsonb_agg(...)
jsonb_array_elements_text(source_event_ids_json)
```

Expected: no target-row union of source ids. Market-only dirty reuses existing source edges and refreshes target features/current rows.

- [ ] **Step 3: Update worker manifest and queue health for two queues**

Update `WorkerManifest`:

```python
input_contract=("token_radar_source_dirty_events", "token_radar_dirty_targets")
writes_control_plane=("token_radar_source_dirty_events", "token_radar_dirty_targets", ...)
dirty_target_tables=("token_radar_source_dirty_events", "token_radar_dirty_targets")
ordering_keys=("source_event_id", "target_type", "target_id", "window", "scope", "venue")
```

Expected: `/readyz` checks both queues that actually exist; no shadow/disabled compatibility queue is introduced.

- [ ] **Step 4: Enqueue exact source event edges from fact changes**

When these inputs change, materialize exact source event-edge rows into `token_radar_source_dirty_events`:

```text
new token intent
token intent resolution changed target
ops source repair for explicit events
backfill that changes token intent/resolution membership semantics
```

Expected: source repair without event ids is impossible at the repository API boundary. The repository method accepts `Iterable[SourceDirtyEvent]`, not a target plus optional JSON array.

- [ ] **Step 5: Claim source events and market targets as separate worker loops**

Worker flow:

```text
claim source dirty events
  -> populate windowless source edges by source_event_id
  -> delete stale edge for old target if resolution moved
  -> enqueue affected target feature/current refresh

claim target feature/current dirty rows
  -> refresh selected target features/current rows
  -> publish affected venue/window/scope rows
```

Expected: source population happens once per changed event edge. Window/scope/venue fanout happens only after the narrow edge write.

- [ ] **Step 6: Delete old target source edge on resolution target change**

When an event currently resolves to a different target than an existing `token_radar_rank_source_events` row, delete stale rows by exact source event id:

```sql
DELETE FROM token_radar_rank_source_events existing
WHERE existing.projection_version = %s
  AND existing.source_kind = 'event'
  AND existing.source_id = ANY(%s)
  AND NOT EXISTS (
    SELECT 1
    FROM requested_event_ids requested
    WHERE requested.source_event_id = existing.source_id
      AND requested.target_type_key = existing.target_type_key
      AND requested.identity_id = existing.identity_id
  );
```

Expected: an event moving from target A to target B cannot keep polluting target A until prune.

- [ ] **Step 7: Enqueue target feature dirty from event anchor backfill**

If `event_anchor_backfill` updates `enriched_events` fields consumed by selected hydrate/feature projection, look up affected narrow source edges by exact `event_id` and enqueue target feature/current dirty for those targets. Do not repopulate source edges.

Expected: anchor backfill does not rely on market-only dirty and does not widen source populate. It only refreshes target features/current rows for targets actually touched by the event.

- [ ] **Step 8: Fix ops repair to choose source-events or market-targets explicitly**

`ops_market_current_repair` must enqueue pure market target dirty only. A source repair command must query/materialize exact event ids before writing `token_radar_source_dirty_events`.

Expected: no `repair_dirty=true` target rows with empty source ids; no source_dirty state exists without a source event id.

---

## Task 7: P2 PostgreSQL Guardrails And Maintenance

**Files:**
- Modify: `docs/references/POSTGRES_PERFORMANCE.md`
- Modify: `scripts/runtime_performance_root_fix_check.sh` if current gates do not cover venue/source temp blocks
- Test: `tests/unit/test_postgres_observability_scripts.py`

- [ ] **Step 1: Add explicit performance gates**

Add gates:

```text
Token Radar source populate temp_blks_written delta over validation window == 0 for normal event batches.
No `market_tick_current`, `latest_price_`, `event_price_`, profile/social/identity, enriched/event-market, or latest-market string in source-edge populate SQL.
No `row_number() OVER`, `to_jsonb(ranked_source)`, or whole-row JSON hash in source-edge populate SQL.
`token_radar_rank_source_events` column count <= 32 and has no `window`/`scope` columns.
`token_radar_dirty_targets` has no `source_event_ids_json` union/aggregation path.
`/api/token-radar?venue=bsc&window=24h&scope=all` returns rows when eligible BSC features exist.
No worker queue health check references deleted equity queue tables.
```

- [ ] **Step 2: Refresh planner stats after migration and rebuild**

Run:

```sql
ANALYZE token_radar_rank_source_events;
ANALYZE token_radar_target_features;
ANALYZE token_radar_current_rows;
ANALYZE token_radar_publication_state;
ANALYZE token_radar_dirty_targets;
ANALYZE token_radar_source_dirty_events;
```

Expected: statistics match the new schema and planner stops estimating hot tables as tiny when they are not.

- [ ] **Step 3: Use `SET LOCAL work_mem` only as bounded guardrail**

If a remaining rank publication sort needs memory, wrap only that transaction:

```sql
SET LOCAL work_mem = '64MB';
```

Expected: this appears only around bounded rank-set publication, not as a global DB setting and not around source-edge populate as a substitute for splitting the query.

---

## Task 8: Rebuild, Verify, And Document

**Files:**
- Create: `docs/superpowers/plans/active/2026-05-29-token-radar-bsc-cpu-root-cause-verification-cn.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/WORKER_FLOW.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/references/POSTGRES_PERFORMANCE.md`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`

- [ ] **Step 1: Run backend and frontend tests**

Run:

```bash
uv run pytest \
  tests/architecture/test_token_radar_venue_leaderboard_contract.py \
  tests/architecture/test_token_radar_source_width_contract.py \
  tests/architecture/test_token_radar_sql_surface_inventory_contract.py \
  tests/architecture/test_equity_runtime_hard_delete_contract.py \
  tests/unit/domains/token_intel/test_token_radar_venue.py \
  tests/unit/domains/token_intel/test_token_radar_source_event_edges.py \
  tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py \
  tests/unit/test_asset_flow_service_venue.py \
  -q

cd web && npm run lint && npm test -- --run
```

Expected: all pass.

- [ ] **Step 2: Run migration and rebuild derived Token Radar rows**

With app workers stopped or paused:

```bash
uv run gmgn-twitter-intel db upgrade
uv run gmgn-twitter-intel ops rebuild-token-radar
```

Expected: rebuild writes current rows for `(window, scope, venue)` including `venue=bsc`.

- [ ] **Step 3: Validate BSC long-window behavior**

Run authenticated API checks without printing token:

```bash
curl -sS -H "Authorization: Bearer $GMGN_API_TOKEN" \
  "http://127.0.0.1:8765/api/token-radar?window=4h&scope=all&venue=bsc&limit=20" \
  | jq '{ok, venue:.data.venue, targets:(.data.targets|length), attention:(.data.attention|length), projection:.data.projection.status}'

curl -sS -H "Authorization: Bearer $GMGN_API_TOKEN" \
  "http://127.0.0.1:8765/api/token-radar?window=24h&scope=all&venue=bsc&limit=20" \
  | jq '{ok, venue:.data.venue, targets:(.data.targets|length), attention:(.data.attention|length), projection:.data.projection.status}'
```

Expected: if BSC eligible candidates exist, BSC endpoints return BSC-ranked rows even when global top20 has no BSC.

- [ ] **Step 4: Validate readiness root fix**

Run:

```bash
curl -sS http://127.0.0.1:8765/readyz | jq '{ok,reasons,workers:(.workers|keys|map(select(startswith("equity_event_"))))}'
```

Expected:

```json
{"ok":true,"reasons":[],"workers":[]}
```

or `ok=true` with unrelated non-equity reasons explicitly explained. There must be no `queue_health_table_unavailable` from deleted equity queues.

- [ ] **Step 5: Validate source populate width and temp blocks**

Run the same 60 second `pg_stat_statements` delta from Task 0.

Expected:

- old target-wide Token Radar SQL calls do not increase;
- source-edge populate temp blocks stay at zero over normal event batches;
- source-edge populate query text has no forbidden wide hydrate tokens;
- `token_radar_rank_source_events` column count is <= 32;
- no active `worker:token_radar_projection` query waits on `IO / BuffileWrite` during normal batches.

- [ ] **Step 6: Write verification artefact**

Create `docs/superpowers/plans/active/2026-05-29-token-radar-bsc-cpu-root-cause-verification-cn.md` with:

```markdown
# Token Radar BSC / CPU Root Cause Hard Cut Verification

- Branch:
- Migration head:
- Config paths confirmed:
- Tests:
- API checks:
- `/readyz`:
- pg_stat_statements before/after:
- Docker stats after 10 min:
- Known residual risks:
```

Expected: verification file contains command names, exit codes, and summarized counts only; no secrets.

---

## Acceptance Criteria

- `/api/token-radar` accepts `venue=all|sol|eth|base|bsc|cex` and returns server-ranked rows for that venue.
- Frontend venue selection changes the API query and query key; it does not filter a truncated global leaderboard as product truth.
- No `web/src/features/live/**` product surface calls `tokenRadarVenueMatches`; server-ranked rows are displayed directly.
- `token_radar_current_rows`, `token_radar_publication_state`, and `token_radar_target_first_seen` identities include `venue`; `stable_generation_id` also includes `venue`.
- BSC `4h/all` and `24h/all` can show rows when BSC eligible features exist even if BSC is outside global top20.
- `token_radar_rank_source_events` is windowless and narrow: no `window`, no `scope`, no generation identity, no JSON payload, no profile/social/identity/market columns, and <= 32 columns.
- Source-edge populate SQL contains no `market_tick_current`, `latest_price_`, `event_price_`, `account_profiles`, `social_event_extractions`, `asset_identity_current`, `registry_assets`, `cex_tokens`, `price_feeds`, `enriched_events`, `market_ticks`, `row_number() OVER`, `to_jsonb(ranked_source)`, or whole-row JSON hash.
- All non-migration Token Radar SQL surfaces are covered by `test_token_radar_sql_surface_inventory_contract.py`; adding another `token_radar_*` SQL file requires updating the inventory.
- Source dirty lives in `token_radar_source_dirty_events` at event-target granularity; `token_radar_dirty_targets` no longer stores or unions `source_event_ids_json`.
- Resolution target changes remove stale source edges for the old target by exact event id.
- Event anchor backfill uses exact event ids to enqueue target feature/current dirty for affected targets; ops source repair enqueues source dirty only with exact event ids; market repair only enqueues target market dirty.
- No runtime manifest, queue health, worker factory, or settings path references deleted Equity/Earnings workers or `equity_event_projection_dirty_targets`.
- `/readyz` is not red because of a missing deleted equity queue table.
- Performance verification shows zero normal Token Radar source populate temp-block growth and no sustained `BuffileWrite` waits from source populate.
