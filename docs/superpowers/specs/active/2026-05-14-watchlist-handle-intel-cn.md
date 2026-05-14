# Spec — Watchlist Handle Intel（按账号的时间线 + 主题汇总）

**Status**: Draft
**Date**: 2026-05-14
**Owner**: Claude / aaurix
**Related**: `web/src/features/watchlist/ui/WatchlistPage.tsx`, `src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py`, `src/gmgn_twitter_intel/domains/evidence/services/ingest_service.py`, `src/gmgn_twitter_intel/domains/social_enrichment/services/watched_event_gate.py`, `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/TESTING.md`, `docs/TECH_DEBT.md`

## Background

`/watchlist?handle=...` 当前是一个轻量视图：`WatchlistPage` 只接收上层 `accountCases` prop，硬上限 8 条 evidence、无分页、无滚动加载，主区域三栏（Hero / SignalStrip / Evidence + Extraction aside）信息密度尚可但承载力有限（`web/src/features/watchlist/ui/WatchlistPage.tsx:33-66`, `web/src/features/watchlist/ui/WatchlistPage.tsx:155-184`）。数据全部从 `AppRoutes.tsx` 上层的内存事件 buffer 派生：`buildWatchlistAccountCases` 在前端聚合 `liveItems`（`web/src/routes/AppRoutes.tsx:86-103`）。后端没有 per-handle 的 paginated 端点，`/api/recent` 是通用 endpoint，只能按 `handles` CSV 过滤、不带 cursor。

每条进入 ingest 的 watchlist event 会走 `IngestService.ingest_event`，若 `is_watched=True` 且过 `watched_event_gate` 则插一行 `enrichment_jobs`（`src/gmgn_twitter_intel/domains/evidence/services/ingest_service.py:129-140`），由 `EnrichmentWorker`（轮询 `enrichment_jobs`，2s + `FOR UPDATE SKIP LOCKED`）调用 `SocialEventExtractionAgent`，写入 `social_event_extractions`，其中 `summary_zh`（一句中文摘要）+ `is_signal_event`（信号事件标记）+ `subject` + `anchor_terms` + `token_candidates` 已经持久化。`summary_zh` 通过 `/api/recent` 的 harness 字段也可被前端取到，**但目前 `/watchlist` 完全没有渲染**——用户在该页面只能看见英文原文，看不见已经算出来的中文摘要。

`watched_event_gate.should_enqueue_watched_social_event_text` 用 `HIGH_SIGNAL_TERMS | TOPIC_TERMS` 两组**硬编码英文词表** + `len >= 24` 字符做门槛（`src/gmgn_twitter_intel/domains/social_enrichment/services/watched_event_gate.py:6-36`, `src/gmgn_twitter_intel/domains/social_enrichment/services/watched_event_gate.py:99-105`）。后果：**纯中文推文如果不含英文金融词，会被静默跳过 LLM**，既没有 `summary_zh` 也没有 `is_signal_event`。这是已知缺口，本 spec 不修，但在 `Risks & Known Gaps · R1` 明确，并挂到 `docs/TECH_DEBT.md`。

主分支后台 worker 共 10 个，与 LLM 相关的只有两个：`EnrichmentWorker`（单条 tweet 维度）、`PulseCandidateWorker`（token/source 维度）。Handle 维度的"近期主题汇总"在现有任何 worker 都不存在。

## Problem

用户切到某个 watchlist handle 时希望快速回答："这个账号近期在说什么？主题是什么？我能不能拉到他全部历史推文？" 当前实现的缺口：

1. **看不见 summary_zh** — 数据库里已经按条算了中文摘要，前端不渲染，英文原文淹没用户视线。
2. **看不见 handle 级主题** — 单条摘要不会被自动聚合成"近 7 天他主要在谈 X / Y / Z 三个话题"，用户每次切 handle 都要从前端聚合的少量 evidence 推断。
3. **拉不到全部历史** — 8 条硬上限 + 无分页 + 无后端端点支撑，用户只能看到内存 buffer 里恰好留着的几条。
4. **噪声没分级** — 实际推文中大量是英文 thread 闲聊、表情、转发，没办法只看"信号"。这层过滤数据库里靠 `is_signal_event` 已经标好，但前端没有切换。

## First Principles

1. **数据已经算出来就别再算第二遍** — `summary_zh` / `is_signal_event` / `subject` / `anchor_terms` 在 `social_event_extractions` 已经持久化，前端要做的是渲染，不是重算。Handle 级主题汇总是真正新增的计算。
2. **Handle 维度的智能跟单 event 维度不同** — 输入是 N 条 event 输出粒度是 handle，跟 `enrichment_jobs.event_id NOT NULL` 的语义承诺冲突。**新增的工作放新表 + 新 worker + 新 domain**，不污染单 event 链路。
3. **事件触发 + 防抖**（用户决策）— 主题汇总在新推文进 enrichment 完成后异步触发，PK=handle 的 jobs 表天然 dedup，避免重复入队。
4. **Cursor 分页是 timeline 的最小契约** — `(received_at_ms DESC, event_id DESC)` 复合 cursor + 复合索引，offset 不可用（高频写入下 offset 会跳）。
5. **本期不动 gate** — `watched_event_gate` 的英文词表缺口范围更大，独立 spec 处理。本 spec 把缺口写明、挂 tech_debt，但 timeline 在 `scope=all` 下仍能展示所有原文，让用户至少能感知到漏掉了什么。

## Goals

- **G1 Handle 时间线 API 落地** — 新增 `GET /api/watchlist/handle/{handle}/timeline?cursor=&limit=&scope=signal|all`，返回 event + extraction 的合并视图，支持 cursor 翻页。
- **G2 Handle 主题汇总持久化** — 新增 `watchlist_handle_summaries`（结果表）+ `watchlist_handle_summary_jobs`（防抖队列），事件触发异步入队，独立 worker 跑 LLM 产 `topics_json`。
- **G3 Handle 主题汇总 API 落地** — 新增 `GET /api/watchlist/handle/{handle}/summary`，handle 未生成时返回 `status="not_ready"`，handle 不在 watchlist 时返回 404。
- **G4 前端渲染** — `WatchlistPage` 顶部新增 `HandleTopicSummary` 卡片，中间用 `HandleTimeline`（React Query `useInfiniteQuery`）替换原 `EvidenceStream`，每条显示 `summary_zh` + 标签 + 折叠原文，scope tab 在 `signal` / `all` 之间切换。
- **G5 新 domain** — `src/gmgn_twitter_intel/domains/watchlist_intel/` 作为新的子域，独立 worker、repo、agent、service，不复用 `enrichment_jobs` / `EnrichmentWorker`。
- **G6 索引就位** — `events` 表新增 `(author_handle, received_at_ms DESC, event_id DESC)` 复合索引，通过独立 alembic step 用 `CREATE INDEX CONCURRENTLY` 部署。
- **G7 验证可复核** — 单元 + 集成测试覆盖入队 / claim / lease / cursor / scope / 冷启动 / 阈值，LLM 部分用 stub provider；前端 Vitest 覆盖渲染、scope 切换、分页追加。
- **G8 不动现有链路核心** — `enrichment_jobs` schema 零修改，`EnrichmentWorker` 的 LLM 抽取主流程零修改（仅增加一个 outbound 钩子在 `process_one` 末尾通知 `watchlist_intel`），pulse / harness / notification / token_radar 链路零修改。

## Non-Goals

- ❌ **修复 `watched_event_gate` 的英文词表偏置** — 留给独立 spec（见 `Risks & Known Gaps · R1` + tech_debt `watched_event_gate-zh-bias`）。
- ❌ **events.language 列 / 语言识别** — 本期不引入 `langdetect` / `lingua` 等依赖。
- ❌ **"无意义"过滤**（emoji-only / 链接-only / 表情包） — 用户明确推迟。
- ❌ **WS 推流直接灌进 timeline 状态** — 本期靠 React Query 轮询，未来再加（见 `Risks & Known Gaps · R4`）。
- ❌ **跨 handle 主题 diff / 历史 timeline-summary 趋势** — 不在本期范围。
- ❌ **右侧 `Extraction aside`（Token mentions / Narrative clusters / Risk notes）改造** — 继续从 `accountCases` 内存聚合取，本期不动（接受短期 props/hooks 数据源分裂，见 `Risks & Known Gaps · R5`）。
- ❌ **修改 `EnrichmentWorker` 的核心 LLM 抽取逻辑 / `enrichment_jobs` schema** — 仅在 `EnrichmentWorker.process_one()` 写完 `social_event_extractions` 后增加一个 outbound 钩子（向 `watchlist_intel` 域发起入队判断），不改主流程，不动 schema。

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  ingest_service.ingest_event(event, is_watched=True)           │
│   └─ 现有: enqueue enrichment_jobs                              │
│       (event_id, job_type='watched_social_event')              │
└────────────────────────────────────────────────────────────────┘
            │
            ▼
  EnrichmentWorker (现有，核心不动)
  poll enrichment_jobs (2s, FOR UPDATE SKIP LOCKED)
  → SocialEventExtractionAgent
  → write social_event_extractions  ← 含 summary_zh / is_signal_event
  └─ ★ 新增 outbound 钩子（process_one 末尾）:
      if extraction.is_signal_event:
        watchlist_intel.enqueue_handle_summary_if_due(handle)
          └─ upsert watchlist_handle_summary_jobs (PK=handle)
                                       │
                                       ▼
                            HandleSummaryWorker (新)
                            poll watchlist_handle_summary_jobs (2s)
                            → HandleTopicSummaryAgent
                              (input: 近 7 天 signal events 的 summary_zh)
                            → upsert watchlist_handle_summaries

                                          │
                                          ▼
┌────────────────────────────────────────────────────────────────┐
│  HTTP                                                           │
│   GET /api/watchlist/handle/{handle}/summary                   │
│   GET /api/watchlist/handle/{handle}/timeline                  │
│        ?cursor=&limit=&scope=signal|all                        │
└────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌────────────────────────────────────────────────────────────────┐
│  Frontend /watchlist?handle=X                                   │
│   ├─ Hero / SignalStrip       (不动)                            │
│   ├─ HandleTopicSummary       (新 · useHandleSummaryQuery)     │
│   ├─ watchlist-monitor-grid                                     │
│   │   ├─ HandleTimeline       (新 · useHandleTimelineQuery)    │
│   │   │   scope tab + useInfiniteQuery + 每条中文摘要 + 折叠原文│
│   │   └─ Extraction aside     (不动)                            │
└────────────────────────────────────────────────────────────────┘
```

新 domain 在 `src/gmgn_twitter_intel/domains/watchlist_intel/`：

```
watchlist_intel/
├─ __init__.py
├─ runtime/
│   └─ handle_summary_worker.py        # HandleSummaryWorker 类 + run()
├─ services/
│   └─ handle_summary_service.py       # enqueue_handle_summary_if_due + summarize_handle 编排
├─ providers/
│   └─ handle_topic_summary_agent.py   # OpenAI Agents SDK / HandleTopicSummaryAgent
├─ repos/
│   └─ watchlist_intel.py              # claim/upsert/enqueue/get
├─ http/
│   └─ routes.py                       # /api/watchlist/handle/{handle}/...
└─ tests/
    └─ ...
```

## Data Model

### `watchlist_handle_summary_jobs` — 防抖队列（PK=handle，天然 dedup）

```sql
CREATE TABLE watchlist_handle_summary_jobs (
  handle                 TEXT PRIMARY KEY,
  status                 TEXT NOT NULL DEFAULT 'pending',  -- pending | running
  next_run_at_ms         BIGINT NOT NULL,
  pending_signal_count   INT NOT NULL DEFAULT 0,
  trigger_reason         TEXT,                              -- cold_start | threshold_events | threshold_time
  lease_expires_at_ms    BIGINT,                            -- claim 后写入 (避免崩溃永锁)
  attempt_count          INT NOT NULL DEFAULT 0,
  last_error             TEXT,
  created_at_ms          BIGINT NOT NULL,
  updated_at_ms          BIGINT NOT NULL
);

CREATE INDEX wh_summary_jobs_run_at_idx
  ON watchlist_handle_summary_jobs (status, next_run_at_ms)
  WHERE status = 'pending';
```

### `watchlist_handle_summaries` — 结果（PK=handle，upsert，不堆历史）

```sql
CREATE TABLE watchlist_handle_summaries (
  handle                  TEXT PRIMARY KEY,
  generated_at_ms         BIGINT NOT NULL,
  input_window_start_ms   BIGINT NOT NULL,
  input_window_end_ms     BIGINT NOT NULL,
  input_event_count       INT NOT NULL,
  topics_json             JSONB NOT NULL,
  -- [{title: str, description: str, event_count: int, top_event_ids: [str, ...]}]
  model                   TEXT NOT NULL,
  raw_response_json       JSONB,                  -- 审计/重放，可 nullable
  signal_count_at_gen     INT NOT NULL,           -- watermark
  updated_at_ms           BIGINT NOT NULL
);
```

### `watchlist_handle_summary_runs` — 审计 / 成本追踪（可选但推荐）

```sql
CREATE TABLE watchlist_handle_summary_runs (
  run_id              UUID PRIMARY KEY,
  handle              TEXT NOT NULL,
  started_at_ms       BIGINT NOT NULL,
  finished_at_ms      BIGINT,
  status              TEXT NOT NULL,           -- running | succeeded | failed
  model               TEXT NOT NULL,
  prompt_tokens       INT,
  completion_tokens   INT,
  cost_usd_estimate   NUMERIC(10, 6),
  error_message       TEXT
);

CREATE INDEX wh_summary_runs_handle_started_idx
  ON watchlist_handle_summary_runs (handle, started_at_ms DESC);
```

### `events` 表索引补强（独立 migration step）

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS events_handle_received_at_idx
  ON events (author_handle, received_at_ms DESC, event_id DESC);
```

> CONCURRENTLY 必须 out-of-transaction，alembic migration 里用 `op.execute()` 并配 `with op.get_context().autocommit_block(): ...`。这是项目里处理 FK 缺索引时已经走过的模式，照搬即可（参考最近添加 FK 索引时的 migration 写法）。

## Worker — 防抖与执行

### 入队时机（关键）

**入队入口在 `EnrichmentWorker.process_one()` 末尾**，而不是 `IngestService.ingest_event`。原因：

- `is_signal_event` / `summary_zh` 是 LLM 跑完才知道的，ingest 阶段无法判断。
- 在 ingest 阶段入队会把"非 signal event 也算账"，导致 worker 拉到 0 条新 signal 但白跑一次 LLM。
- `EnrichmentWorker` 主流程零侵入，只在 `process_one` 末尾追加一行 outbound 钩子。

钩子伪代码（要点：仅当 `extraction.is_signal_event=True` 才调用）：

```python
# EnrichmentWorker.process_one() — 现有逻辑写完 social_event_extractions 后
if extraction.is_signal_event and event.is_watched:
    self.watchlist_intel_service.enqueue_handle_summary_if_due(
        handle=event.author_handle, now_ms=now_ms
    )
```

### 入队判断 (`enqueue_handle_summary_if_due`)

```python
def enqueue_handle_summary_if_due(
    handle: str,
    *,
    now_ms: int,
    repo: WatchlistIntelRepo,
    settings: WatchlistIntelSettings,
) -> None:
    summary = repo.get_summary(handle)
    # 注意：count_signal_events_total 返回 events × social_event_extractions JOIN 中
    # author_handle=$handle AND is_signal_event=TRUE 的总条数（全历史）
    signal_count_total = repo.count_signal_events_total(handle)

    if summary is None:
        # 冷启动：handle 第一次出现 signal event → 立即入队
        reason, next_run_at_ms, pending = "cold_start", now_ms, 1
    else:
        pending = signal_count_total - summary.signal_count_at_gen
        age_ms = now_ms - summary.generated_at_ms

        # 全局速率底线：5 分钟内不重跑同 handle（即便阈值触发）
        if age_ms < settings.min_interval_ms:
            return

        if pending >= settings.signal_threshold:
            reason, next_run_at_ms = "threshold_events", now_ms
        elif age_ms >= settings.time_threshold_ms and pending > 0:
            # age 超时但确实有新 signal 才入队；纯 age 满但 pending=0 不刷
            reason, next_run_at_ms = "threshold_time", now_ms
        else:
            return  # 不入队

    repo.upsert_job(
        handle=handle,
        next_run_at_ms=next_run_at_ms,
        pending_signal_count=pending,
        trigger_reason=reason,
    )
```

### Worker 主循环

`HandleSummaryWorker.run()` — 独立 asyncio task 启动于 `app/runtime/app.py`，2s poll：

```python
while running:
    job = await repo.claim_next_job(now_ms, lease_ms=settings.lease_ms)
    if job is None:
        await asyncio.sleep(settings.poll_interval); continue

    try:
        await self._process(job, now_ms)
    except Exception as e:
        await repo.fail_job(handle=job.handle, error=str(e),
                            retry_in_ms=backoff(job.attempt_count))
```

`_process` 流程：

1. 拉 `social_event_extractions` × `events` JOIN：`author_handle=$handle AND is_signal_event=TRUE AND received_at_ms >= now - 7d`，按 `received_at_ms DESC` LIMIT 80。
2. 构造 prompt：含 `summary_zh` / `subject` / `anchor_terms` / 时间戳。
3. 调 `HandleTopicSummaryAgent` → 返回 `{topics: [{title, description, event_count, top_event_ids}], confidence}`。
4. `upsert_summary(handle, topics_json, signal_count_at_gen=当前 total, ...)`。
5. `delete_job(handle)`。
6. 写 `watchlist_handle_summary_runs`（成本审计）。

### 配置项

写入 `src/gmgn_twitter_intel/platform/config/settings.py`，全部 `WATCHLIST_HANDLE_SUMMARY_*` 前缀：

| 配置 | 默认 | 含义 |
|---|---|---|
| `WATCHLIST_HANDLE_SUMMARY_ENABLED` | `True` | 总开关 |
| `WATCHLIST_HANDLE_SUMMARY_SIGNAL_THRESHOLD` | `10` | N：累计多少条新 signal 触发 |
| `WATCHLIST_HANDLE_SUMMARY_TIME_THRESHOLD_MS` | `30 * 60_000` | T：多久未刷触发 |
| `WATCHLIST_HANDLE_SUMMARY_MIN_INTERVAL_MS` | `5 * 60_000` | 同 handle 最小重跑间隔（硬底） |
| `WATCHLIST_HANDLE_SUMMARY_POLL_INTERVAL_SECONDS` | `2` | worker poll |
| `WATCHLIST_HANDLE_SUMMARY_CONCURRENCY` | `1` | 启几个 worker loop |
| `WATCHLIST_HANDLE_SUMMARY_INPUT_LIMIT` | `80` | LLM 输入最多 80 条 signal event |
| `WATCHLIST_HANDLE_SUMMARY_WINDOW_DAYS` | `7` | 时间窗 |
| `WATCHLIST_HANDLE_SUMMARY_LEASE_MS` | `120_000` | claim 后 lease |
| `WATCHLIST_HANDLE_SUMMARY_MAX_ATTEMPTS` | `3` | 失败重试上限 |

### Agent 实例

`HandleTopicSummaryAgent` 沿用项目已选定的 agent harness：openai-agents-python（OpenAI Agents SDK），单 stage 直接 `Runner.run`，不引入 handoff、不迁 LangGraph。复用 `SocialEventExtractionAgent` 的 client 初始化与重试封装。

Prompt 框架（伪代码）：

```
SYSTEM: 你是中文加密分析助手。给出一个 X 账号在近 7 天的主要议题。
INPUT:
  - handle: @{handle}
  - events: [{time: ISO8601, summary_zh, subject, anchor_terms}] (≤ 80)
OUTPUT (JSON):
  - topics: 3-5 个，title (≤ 12 字) / description (≤ 40 字) / event_count / top_event_ids (≤ 3)
  - confidence: 0-1
约束：
  - 主题用中文
  - description 必须基于 summary_zh + subject 的事实，不臆测
  - 若 events 少于 5 条，仍要给出至少 1 个主题
```

## HTTP API

### `GET /api/watchlist/handle/{handle}/summary`

**Request**: `handle` 走 URL path（FastAPI 自动 URL-decode），需校验 ASCII + 长度 ≤ 64。

**Response 200**（已生成）:

```jsonc
{
  "handle": "marionawfal",
  "generated_at_ms": 1747843200000,
  "input_window_start_ms": 1747238400000,
  "input_window_end_ms": 1747843200000,
  "input_event_count": 78,
  "topics": [
    {
      "title": "BTC ETF 风险预警",
      "description": "持续提示 BTC ETF 净流出可能触发回调。",
      "event_count": 12,
      "top_event_ids": ["evt_xxx", "evt_yyy"]
    }
  ],
  "model": "gpt-4o-mini",
  "is_stale": false,
  "pending_recompute": false
}
```

**Response 200**（未生成，handle 在 watchlist 但 summary 表无记录）:

```jsonc
{ "handle": "marionawfal", "status": "not_ready", "pending_recompute": true }
```

**Response 404**（handle 不在 watchlist）。

`is_stale = generated_at_ms < now - 2 * T_THRESHOLD`（服务端时钟）。
`pending_recompute = jobs 表存在该 handle 的 pending/running 行`。

### `GET /api/watchlist/handle/{handle}/timeline?cursor=&limit=&scope=signal|all`

**Params**:
- `cursor`: 不透明字符串。后端实际是 `base64(json({"received_at_ms": ..., "event_id": "..."}))`。
- `limit`: 默认 30，最大 100，参数校验失败返回 422。
- `scope`: `signal`（默认）| `all`。

**Response 200**:

```jsonc
{
  "handle": "marionawfal",
  "scope": "signal",
  "items": [
    {
      "event_id": "evt_xxx",
      "received_at_ms": 1747843200000,
      "text": "BTC ETF outflows are flashing red...",
      "text_url": "https://x.com/marionawfal/status/...",
      "summary_zh": "警告 BTC ETF 净流出或导致回调。",
      "is_signal_event": true,
      "subject": "BTC ETF risk",
      "event_type": "warning",
      "anchor_terms": ["BTC", "ETF", "outflow"],
      "cashtags": ["$BTC"],
      "hashtags": [],
      "token_resolutions": [/* 与 /api/recent 一致的结构 */]
    }
  ],
  "next_cursor": "eyJyZWNlaXZlZF9hdF9tcyI6MTc0Nzg0Mywg..."
}
```

`next_cursor` 为 `null` 表示已到末尾。

**SQL 核心**（实践中按 `scope` 拼两条 SQL，避免 LEFT JOIN + WHERE 的 planner 歧义）:

```sql
-- scope=signal: INNER JOIN，walking index 的同时硬过滤 is_signal_event
SELECT e.event_id, e.received_at_ms, e.text, e.cashtags_json, e.hashtags_json,
       x.summary_zh, x.is_signal_event, x.subject, x.event_type, x.anchor_terms_json
FROM events e
INNER JOIN social_event_extractions x USING (event_id)
WHERE e.author_handle = $1
  AND x.is_signal_event = TRUE
  AND ($2::bigint IS NULL OR (e.received_at_ms, e.event_id) < ($2, $3))
ORDER BY e.received_at_ms DESC, e.event_id DESC
LIMIT $4;

-- scope=all: LEFT JOIN，无 extraction 的 event 也返回（summary_zh 为 NULL）
SELECT e.event_id, e.received_at_ms, e.text, e.cashtags_json, e.hashtags_json,
       x.summary_zh, x.is_signal_event, x.subject, x.event_type, x.anchor_terms_json
FROM events e
LEFT JOIN social_event_extractions x USING (event_id)
WHERE e.author_handle = $1
  AND ($2::bigint IS NULL OR (e.received_at_ms, e.event_id) < ($2, $3))
ORDER BY e.received_at_ms DESC, e.event_id DESC
LIMIT $4;
```

依赖索引：`events_handle_received_at_idx`（见 `Data Model · events 表索引补强`）。`scope=signal` 还涉及 extraction 表的 `is_signal_event` 过滤，可在后续 spec 评估是否额外加 partial index `WHERE x.is_signal_event = TRUE`；本期不加，留 EXPLAIN ANALYZE 出数据后再决策。

**Cursor 防御**:
- base64 解码失败 → 400。
- 字段缺失 / 类型不符 → 400。
- `received_at_ms` 不是正整数 → 400。
- 参数全部走 prepared statement，不拼字符串。

## Frontend

### 路由 / 状态

URL 形态：`/watchlist?handle=<handle>&scope=signal|all`。`handle` 沿用现有 URL param，`scope` 是新参数（默认 `signal`）。`scope` 切换走 `useSearchParams`，不重新挂载组件。

### 改造范围

```
WatchlistPage (web/src/features/watchlist/ui/WatchlistPage.tsx)
├─ Hero                          (不动)
├─ SignalStrip                   (不动)
├─ HandleTopicSummary  ← 新       (useHandleSummaryQuery)
├─ watchlist-monitor-grid
│   ├─ HandleTimeline  ← 新替换     (useHandleTimelineQuery + useInfiniteQuery)
│   │   - 顶部 Tab: signal | all
│   │   - 列表项: 时间 + summary_zh + 标签(signal/token) + 折叠原文
│   │   - 底部"加载更多"按钮 + IntersectionObserver
│   └─ Extraction aside           (不动: ClusterPanel × 2 + RiskPanel)
```

### 新增文件

```
web/src/features/watchlist/
├─ api/
│   ├─ fetchHandleSummary.ts             # HTTP fetch
│   └─ fetchHandleTimeline.ts            # HTTP fetch (with cursor)
├─ data/
│   ├─ useHandleSummaryQuery.ts          # React Query useQuery
│   └─ useHandleTimelineQuery.ts         # React Query useInfiniteQuery
├─ ui/
│   ├─ HandleTopicSummary.tsx
│   ├─ HandleTimeline.tsx
│   ├─ HandleTimelineItem.tsx
│   └─ handleTimeline.css                # 局部样式
└─ model/
    └─ handleSummaryTypes.ts             # API 响应类型
```

### React Query 用法

```ts
// useHandleTimelineQuery.ts
useInfiniteQuery({
  queryKey: ["watchlist", "handle", handle, "timeline", scope],
  queryFn: ({ pageParam }) => fetchTimeline({ handle, scope, cursor: pageParam }),
  getNextPageParam: (last) => last.next_cursor ?? undefined,
  staleTime: 30_000,
  refetchInterval: 15_000,  // 仅第一页：React Query 在 enabled+visible 时轮询
});

// useHandleSummaryQuery.ts
useQuery({
  queryKey: ["watchlist", "handle", handle, "summary"],
  queryFn: () => fetchSummary({ handle }),
  staleTime: 60_000,
  refetchInterval: 60_000,
});
```

### Live 更新策略

- summary：60s 轮询 + 切换 handle 立即 refetch。
- timeline：第一页 15s 轮询；后续页通过用户操作（"加载更多" / scroll）触发，**不轮询**。
- WS 推流**不**直接灌进 timeline 状态（避免乱序、避免 cursor 失效），本期靠轮询。

### scope tab 行为

- Tab 切换写 URL `scope` param + 触发新 infinite query（query key 包含 scope，自动重新拉）。
- `scope=signal` 默认；空数据时显示"近期无信号事件 · 切到全部"按钮。

### 视觉

沿用 `web/src/features/watchlist/ui/watchlist.css` 已有 design token + Obsidian Desk 配色（见 `docs/superpowers/specs/active/2026-05-13-obsidian-desk-ui-hard-cut-cn.md`）。新组件不引入新色板，新增 class 用 `watchlist-handle-summary-*` / `watchlist-handle-timeline-*` 前缀。

## Testing

按 `docs/TESTING.md` 分层。

### Unit (pytest)

| 测试 | 文件 | 覆盖 |
|---|---|---|
| `test_enqueue_handle_summary_if_due` | `tests/domains/watchlist_intel/test_enqueue.py` | 冷启动 / 阈值-条数 / 阈值-时间 / min_interval 兜底 / 未到阈值不入队 |
| `test_repo_claim_next_job` | `tests/domains/watchlist_intel/test_repo.py` | claim 走 FOR UPDATE SKIP LOCKED，lease 写入，`next_run_at_ms <= now` 过滤，并发 claim 不重 |
| `test_repo_upsert_summary` | `tests/domains/watchlist_intel/test_repo.py` | `signal_count_at_gen` 写对，重复 upsert by handle |
| `test_handle_summary_prompt_build` | `tests/domains/watchlist_intel/test_prompt.py` | 80 条 input limit、时间窗截断、缺 summary_zh 的 event 不参与 |
| `test_timeline_cursor_codec` | `tests/domains/watchlist_intel/test_cursor.py` | 合法/非法/边界 cursor、SQL injection 防御 |

### Integration (真 PG，遵循 `docs/TESTING.md` — 不 mock 数据库)

| 测试 | 覆盖 |
|---|---|
| `test_handle_summary_pipeline_end_to_end` | ingest N 条 signal event → 触发入队 → worker claim → 写 summary（LLM 用 stub provider） |
| `test_handle_summary_dedup_under_burst` | 同 handle 短时间 50 条 event，jobs 表 PK=handle 保证只 1 行 |
| `test_handle_summary_worker_lease_recovery` | worker 拿了 lease 后崩溃，lease 过期后另一 loop 能 reclaim |
| `test_api_timeline_pagination` | cursor 翻 3 页 ≡ 一次拿 3*limit 条；scope=signal 与 scope=all 边界 |
| `test_api_timeline_index_used` | `EXPLAIN ANALYZE` 走新索引 |
| `test_api_summary_not_ready` | summary 表无记录时返回 200+`status="not_ready"` |
| `test_api_handle_not_in_watchlist` | 返回 404 |
| `test_api_handle_url_encoding` | handle 含 `.` `_` `-` 等合法字符正确解析 |

### LLM stub

集成测试不调真 OpenAI。在 `tests/_stubs/handle_summary_provider.py` 写一个固定输出 stub，按输入 event_id 数量返回确定 topics。

```python
class StubHandleTopicSummaryAgent:
    async def summarize(self, *, handle, events, ...):
        return HandleTopicSummaryResult(
            topics=[Topic(title="主题 A", description="...", event_count=len(events),
                          top_event_ids=[e.event_id for e in events[:3]])],
            confidence=0.8,
            model="stub-handle-topic-summary",
        )
```

`pytest` fixture 切换：`WATCHLIST_HANDLE_SUMMARY_PROVIDER=stub` 时注入 stub。

### Frontend (Vitest + RTL)

| 测试 | 覆盖 |
|---|---|
| `HandleTopicSummary.test.tsx` | `not_ready` 显示骨架；`is_stale` 显示"X 分钟前更新"；正常显示 topics |
| `HandleTimeline.test.tsx` | 切换 scope 触发 refetch；点"加载更多"追加下一页；空数据显示 empty state |
| `useHandleTimelineQuery.test.ts` | mock fetch，验证 cursor 透传、`getNextPageParam` |

### 验证清单（完成前必须跑过）

- `uv run pytest tests/domains/watchlist_intel/ -v`
- `uv run pytest tests/integration/watchlist/ -v`
- `cd web && pnpm test features/watchlist`
- `uv run gmgn-twitter-intel watchlist-intel doctor` (新增 CLI 子命令做端到端 smoke，可选)
- 手动：本地起 server，watchlist 切 3 个 handle，验证主题汇总 / scope tab / 分页加载

## Risks & Known Gaps

### R1 · 纯中文推文被 gate 拦在 LLM 外（已知缺口，本期不修）

`watched_event_gate.should_enqueue_watched_social_event_text` 用 `HIGH_SIGNAL_TERMS | TOPIC_TERMS` 英文词表筛选（`src/gmgn_twitter_intel/domains/social_enrichment/services/watched_event_gate.py:99-105`）。后果：纯中文推文如果不含英文金融词，**没 `summary_zh` 也没 `is_signal_event`**，watchlist `scope=signal` 看不到，主题汇总也漏掉。

**处置**：
- 本期不修，spec 明确写入。
- 同步在 `docs/TECH_DEBT.md` 新增条目 `watched_event_gate-zh-bias`，标"中等优先级 / 下一期"。
- `scope=all` 视图仍能展示纯中文原文（只是没有摘要 + 不打 signal 标），用户至少能感知。

### R2 · LLM 调用成本失控

极端情况：100 个 watchlist handle × 高频推文 → 每个 handle 每 30 min 触发 → 每小时 200 次 LLM 调用。

**缓解**：
- jobs 表 PK=handle 天然 dedup（同一 handle 不会并发排队）。
- `WATCHLIST_HANDLE_SUMMARY_INPUT_LIMIT=80` 单次 prompt 上限。
- `WATCHLIST_HANDLE_SUMMARY_MIN_INTERVAL_MS=5*60_000` 硬底（即便阈值触发，5 分钟内不重跑同 handle）。
- `watchlist_handle_summary_runs` 审计表 → 运维能 `SELECT date_trunc('hour', ...) GROUP BY` 拉成本曲线。
- 失败 backoff（attempt_count → exponential）+ `MAX_ATTEMPTS=3` 之后停止重试。

### R3 · 索引未到位前 timeline 慢查

`events` 当前没有 `(author_handle, received_at_ms DESC, event_id DESC)` 复合索引，cursor 翻页可能走 seq scan。

**处置**：
- 部署前必须先跑 `CREATE INDEX CONCURRENTLY`（独立 alembic step，按项目已有 FK 索引补强 migration 的模式）。
- 集成测试 `test_api_timeline_index_used` 用 EXPLAIN ANALYZE 验证。
- 不带索引的环境（CI 起新库）通过 migration 自动创建。

### R4 · 不接 WS 实时推流的可感知延迟

最新 1 条推文要等 15s 轮询才出现在 timeline 顶部。

**处置**：
- 本期接受，spec 标记下一期"接 WS 灌入 timeline 第一页"。
- 用户感知：SignalStrip 的 Evidence 计数仍是 WS 实时更新（继续从 `accountCases` 取），可以作为"有新事件，请刷新"的视觉提示。

### R5 · WatchlistPage 短期数据源分裂

改造期间：右 aside 走 props（`accountCases`），新组件走 React Query。同一页面两个数据源。

**处置**：
- 接受这个分裂作为最 minimal 改造代价。
- `docs/TECH_DEBT.md` 新增条目 `watchlist-page-data-source-split`，下一期完整迁移到 hooks。

### R6 · `is_stale` 客户端钟漂

`is_stale` 完全在服务端用 `generated_at_ms < now - 2 * T_THRESHOLD` 算，避开客户端钟漂。客户端只用 `formatRelativeTime`（已有）显示"X 分钟前"。

### R7 · Handle 列表来源

新 API 不维护"哪些 handle 在 watchlist"，依赖现有 `/api/bootstrap.handles` + `/api/cockpit-status.handles`。当 handle 从 watchlist 移除：jobs 表残留 + summary 表残留是 OK 的（不会自动跑），定期清理留给下一期。404 判定走"`handle NOT IN bootstrap.handles`"。

## Verification

完成本 spec 后，下列证据必须存在并附在 PR 描述：

1. **测试结果** — `uv run pytest tests/domains/watchlist_intel/ tests/integration/watchlist/ -v` 全绿，输出贴 PR。
2. **前端测试** — `cd web && pnpm test features/watchlist` 全绿。
3. **EXPLAIN ANALYZE** — timeline SQL 走 `events_handle_received_at_idx`，运行时长 < 50ms（100k 行测试库）。
4. **截图** — 本地 dev server 三张：summary 卡 / timeline signal scope / timeline all scope（"加载更多"分页前后各一）。
5. **make check-all** — 全绿（lint + type + test）。
6. **手动 smoke** — 起服务，在三个不同 handle 上切换 + scope tab + 至少一次"加载更多"；观察 worker 日志看到 claim + write + run 审计行；DB 看到 summary + run 记录。

## Open Questions

无（设计阶段已收敛）。落 plan 时若发现 ingest_service 入队点细节有出入，回到本 spec 修订。

---

**变更记录**

- 2026-05-14 草案首版。
