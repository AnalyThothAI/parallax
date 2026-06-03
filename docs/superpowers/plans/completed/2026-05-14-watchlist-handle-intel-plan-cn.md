# Watchlist Handle Intel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `/watchlist?handle=...` 从内存 buffer 里的 8 条英文 evidence，升级成可分页的账号时间线、可过滤的 signal/all scope、以及由 watched-event extraction 派生的中文主题汇总。

**Architecture:** 新增 `domains/watchlist_intel` 拥有 handle timeline 查询、summary job 队列、summary worker、summary provider contract 和结果读模型。`social_enrichment` 仍只负责单条 watched event extraction；`EnrichmentWorker` 在 extraction 成功持久化的同一个事务里触发 watchlist summary job 入队，避免“extraction 已 done 但 summary job 丢失”。HTTP 仍留在 `app/surfaces/api/http.py`，只调用 domain service，不把 domain-owned routes 放到 domain 目录。

**Tech Stack:** Python 3, FastAPI, psycopg, Alembic, OpenAI Agents SDK provider adapter, pytest, React 19, TypeScript, TanStack Query, Vite, Vitest/RTL, MSW, Playwright.

**Owning spec:** `docs/superpowers/specs/active/2026-05-14-watchlist-handle-intel-cn.md`

**UI mockup:** `docs/generated/watchlist-handle-intel-ui-mockup.html`

---

## Current-State Analysis

### Watchlist 页面现状

- `web/src/routes/AppRoutes.tsx:86-102` 从 `statusHandles/bootstrapHandles + liveItems` 生成 `watchlistRows` 和 `watchlistAccountCases`，没有独立 server state。
- `web/src/features/watchlist/model/watchlistCase.ts:43-85` 只从 `LivePayload[]` 聚合，每个 handle `slice(0, 8)`，没有 cursor、没有后端历史查询。
- `web/src/features/watchlist/ui/WatchlistPage.tsx:33-65` 页面结构是 Hero、SignalStrip、左侧 Recent evidence、右侧 extracted clusters。
- `web/src/features/watchlist/ui/WatchlistPage.tsx:155-183` EvidenceStream 只渲染 `item.body` 原文，没有读 `payload.harness.summary_zh`。
- `/api/recent` 在 `src/parallax/app/surfaces/api/http.py:90-120` 支持 `handles` CSV 和 `limit`，但没有 per-handle cursor，也没有 `scope=signal|all`。

### Watched event enrichment 现状

- `IngestService.ingest_event` 在 `src/parallax/domains/evidence/services/ingest_service.py:128-140` 对 watched event 调 `watched_social_event_priority(...)`，命中后插入 `enrichment_jobs`。
- `watched_social_event_priority` 不是纯英文词表 gate：`src/parallax/domains/social_enrichment/services/watched_event_gate.py:70-96` 对 CA、resolved target、有高信号词、symbol+topic term、双 topic term 分级给 priority。
- 但纯中文文本如果没有 CA 或 resolved target，仍会被 `watched_event_gate` 跳过，因为高信号词和 topic term 仍是英文词表。这一点和 spec 的 R1 方向一致，但 spec 对 gate 的描述应从“只有英文词表 + len”修正为“优先级 gate 有实体/解析分支，但中文非实体文本仍漏”。
- `EnrichmentWorker.process_one` 在 `src/parallax/domains/social_enrichment/runtime/enrichment_worker.py:58-139` claim job、调用 LLM、完成 `complete_social_event_job`、materialize harness、发布 `harness_update`。
- `_complete_job_sync` 在 `src/parallax/domains/social_enrichment/runtime/enrichment_worker.py:185-214` 已经用 `repos.unit_of_work()` 包住 enrichment completion 和 harness materialization。Watchlist summary 入队应挂在这里同一事务，不能挂成 process 末尾的 best-effort side effect。

### Signal Pulse worker 对本方案的启发

- `PulseCandidateWorker.run` 在 `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:147-170` 使用 poll + wake queue，可以作为新的 `HandleSummaryWorker` 生命周期模板。
- `run_once_async` 在 `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:216-226` 明确拆成 scan 和 process，并维护 `last_result/last_error`，适合复用到 readiness/doctor 输出。
- `process_due_jobs_once_async` 在 `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:262-293` 使用批量 claim、失败计数、missing context 处理，适合复用到 summary job worker。
- `PulseCandidateWorker._enqueue_if_due` 在 `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:364-433` 的关键价值不是可复制的业务逻辑，而是闭环模式：独立 state table、dedup、budget、edge events、enqueue 后写 processed state。Watchlist summary 不需要 `pulse_candidate_edge_state`，但需要同等级别的独立 job table、lease、attempt、runs audit 和 summary watermark。

### 闭环判断

可落地性：高。当前代码已经具备 watched event ingestion、LLM extraction、`summary_zh/is_signal_event` 持久化、runtime worker wiring、React Query、MSW 测试基础。

闭环完整性：有一个必须修正点。Spec 说在 `EnrichmentWorker.process_one()` 末尾加 outbound 钩子；如果这个钩子在 enrichment job done 之后失败，就会永久丢 summary recompute。实现时必须改成：

```python
with self.repository_session() as repos, repos.unit_of_work():
    run = repos.enrichment.complete_social_event_job(..., commit=False)
    materialized = HarnessSnapshotBuilder(...).materialize(..., commit=False)
    if bool(result.is_signal_event) and bool(event.get("is_watched")):
        repos.watchlist_intel.enqueue_handle_summary_if_due(
            handle=str(event.get("author_handle") or ""),
            now_ms=finished_at_ms,
            commit=False,
        )
```

这样 extraction、harness、summary job 处于同一 commit。后续再补一个 `reconcile_missing_summary_jobs(limit)` CLI/doctor 命令，覆盖历史数据和极端迁移窗口。

---

## Design Corrections To Apply Before Coding

1. **HTTP surface 位置修正**  
   Spec 里的 `domains/watchlist_intel/http/routes.py` 不符合当前架构文档。HTTP endpoints 应加在 `app/surfaces/api/http.py`，domain 提供 `WatchlistIntelReadService` / `WatchlistIntelService`。

2. **配置形态修正**  
   当前项目以 `Settings.llm` 的 pydantic YAML config 为主，不是直接读 `WATCHLIST_HANDLE_SUMMARY_*` 环境变量。新增字段放入 `LlmConfig`，暴露 `settings.watchlist_handle_summary_*` properties；文档里再说明 YAML key。

3. **入队闭环修正**  
   入队必须在 `EnrichmentWorker._complete_job_sync` 的 UOW 内执行，并且通过 `repos.watchlist_intel` 写入。不要在 publish 之后 best-effort 调用。

4. **索引命名修正**  
   当前已有 `idx_events_author_received ON events(author_handle, received_at_ms)`，但缺少 `event_id` 作为 keyset tie-breaker。新增索引用 `idx_events_author_received_event_desc`，而不是复用容易误解的旧名。

5. **Gate 风险表述修正**  
   R1 保留，但描述为“中文非实体/非已解析 target 文本会漏 enrichment”，不是“所有纯中文都必漏”。含 CA 或 resolved target 的中文文本可能仍会 enqueue。

6. **Frontend 分层修正**  
   根据 `docs/FRONTEND.md`，server hooks 放 `web/src/features/watchlist/api/`，不要新增 `data/` 目录。

---

## File Structure

### Backend

- Create: `src/parallax/domains/watchlist_intel/__init__.py`
- Create: `src/parallax/domains/watchlist_intel/interfaces.py`
- Create: `src/parallax/domains/watchlist_intel/providers.py`
- Create: `src/parallax/domains/watchlist_intel/types.py`
- Create: `src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py`
- Create: `src/parallax/domains/watchlist_intel/services/handle_summary_service.py`
- Create: `src/parallax/domains/watchlist_intel/read_models/watchlist_intel_service.py`
- Create: `src/parallax/domains/watchlist_intel/runtime/handle_summary_worker.py`
- Create: `src/parallax/integrations/openai_agents/watchlist_handle_summary_client.py`
- Modify: `src/parallax/app/runtime/repository_session.py`
- Modify: `src/parallax/app/runtime/providers_wiring.py`
- Modify: `src/parallax/app/runtime/app.py`
- Modify: `src/parallax/app/surfaces/api/http.py`
- Modify: `src/parallax/app/surfaces/api/schemas.py`
- Modify: `src/parallax/platform/config/settings.py`
- Create: `src/parallax/platform/db/alembic/versions/20260514_0043_watchlist_handle_intel.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/TECH_DEBT.md`

### Frontend

- Create: `web/src/features/watchlist/api/useHandleSummaryQuery.ts`
- Create: `web/src/features/watchlist/api/useHandleTimelineQuery.ts`
- Create: `web/src/features/watchlist/model/handleIntelTypes.ts`
- Create: `web/src/features/watchlist/model/handleTimeline.ts`
- Create: `web/src/features/watchlist/state/watchlistRouteState.ts`
- Create: `web/src/features/watchlist/ui/HandleTopicSummary.tsx`
- Create: `web/src/features/watchlist/ui/HandleTimeline.tsx`
- Create: `web/src/features/watchlist/ui/HandleTimelineItem.tsx`
- Create: `web/src/features/watchlist/ui/handleIntel.css`
- Modify: `web/src/features/watchlist/ui/WatchlistPage.tsx`
- Modify: `web/src/features/watchlist/index.ts`
- Modify: `web/src/lib/types/frontend-contracts.ts`
- Modify: `web/tests/msw/fixtures.ts`
- Modify: `web/tests/e2e/support/mockApi.ts`
- Create: `web/tests/unit/features/watchlist/state/watchlistRouteState.test.ts`
- Create: `web/tests/component/features/watchlist/api/useHandleTimelineQuery.test.tsx`
- Create: `web/tests/component/features/watchlist/ui/HandleTopicSummary.test.tsx`
- Create: `web/tests/component/features/watchlist/ui/HandleTimeline.test.tsx`
- Modify: `web/tests/routes/watchlist.route.test.tsx`

### Tests

- Create: `tests/domains/watchlist_intel/test_cursor.py`
- Create: `tests/domains/watchlist_intel/test_enqueue.py`
- Create: `tests/domains/watchlist_intel/test_handle_summary_prompt.py`
- Create: `tests/integration/watchlist/test_watchlist_intel_repository.py`
- Create: `tests/integration/watchlist/test_watchlist_intel_api.py`
- Create: `tests/integration/watchlist/test_watchlist_intel_worker.py`
- Modify: `tests/unit/test_settings.py`
- Modify: `tests/unit/test_enrichment_worker_runtime.py`
- Modify: `tests/integration/test_enrichment_worker.py`
- Modify: architecture tests only if they enumerate known domains.

---

## Task 1: Schema, Cursor, Repository

**Files:**
- Create migration: `src/parallax/platform/db/alembic/versions/20260514_0043_watchlist_handle_intel.py`
- Create repository: `src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py`
- Create types: `src/parallax/domains/watchlist_intel/types.py`
- Tests: `tests/domains/watchlist_intel/test_cursor.py`, `tests/integration/watchlist/test_watchlist_intel_repository.py`

- [ ] Add tables `watchlist_handle_summary_jobs`, `watchlist_handle_summaries`, `watchlist_handle_summary_runs`.
- [ ] Add `idx_events_author_received_event_desc ON events(author_handle, received_at_ms DESC, event_id DESC)` using `op.get_context().autocommit_block()` and `CREATE INDEX CONCURRENTLY IF NOT EXISTS`.
- [ ] Add repository methods:
  - `enqueue_handle_summary_job(handle, next_run_at_ms, pending_signal_count, trigger_reason, commit=True)`
  - `claim_next_summary_job(now_ms, lease_ms)`
  - `mark_summary_job_failed(job, error, now_ms)`
  - `delete_summary_job(handle, commit=True)`
  - `upsert_handle_summary(...)`
  - `insert_summary_run(...)`
  - `get_handle_summary(handle)`
  - `pending_summary_job(handle)`
  - `count_signal_events_total(handle)`
  - `signal_events_for_summary(handle, since_ms, limit)`
  - `timeline(handle, scope, cursor, limit)`
- [ ] Implement cursor as base64url JSON with `received_at_ms` and `event_id`; invalid cursor raises `WatchlistTimelineCursorError`.
- [ ] Repository integration tests must prove:
  - one handle has at most one pending/running summary job;
  - stale running lease can be reclaimed;
  - max attempts moves job to `dead`;
  - `signal_count_at_gen` is stored and used;
  - timeline cursor returns stable pages under same-millisecond events;
  - `scope=signal` excludes non-signal / missing extraction rows;
  - `scope=all` returns raw events with nullable extraction fields.

## Task 2: Domain Service And Summary Provider Contract

**Files:**
- Create: `src/parallax/domains/watchlist_intel/providers.py`
- Create: `src/parallax/domains/watchlist_intel/services/handle_summary_service.py`
- Create: `src/parallax/domains/watchlist_intel/read_models/watchlist_intel_service.py`
- Tests: `tests/domains/watchlist_intel/test_enqueue.py`, `tests/domains/watchlist_intel/test_handle_summary_prompt.py`

- [ ] Define `HandleTopicSummaryProvider` protocol with `provider`, `model`, `timeout_seconds`, `request_audit(...)`, and `summarize_handle(...)`.
- [ ] Implement `enqueue_handle_summary_if_due` with cold start, `signal_threshold`, `time_threshold_ms`, and `min_interval_ms`.
- [ ] Implement `summarize_handle(job, now_ms)`:
  - load at most `input_limit` signal events from last `window_days`;
  - skip events with empty `summary_zh`;
  - return a deterministic `not_enough_input` summary if no usable events exist, without calling LLM;
  - otherwise call provider, upsert summary, insert run audit, delete job.
- [ ] Implement read service methods:
  - `summary(handle, configured_handles, now_ms)` returning `ready/not_ready/404`;
  - `timeline(handle, configured_handles, scope, cursor, limit)`.
- [ ] Unit tests cover cold start, threshold events, threshold time, min interval, pending count, empty input, prompt input limit, and `is_stale/pending_recompute`.

## Task 3: Worker, Runtime Wiring, And Enrichment Hook

**Files:**
- Create: `src/parallax/domains/watchlist_intel/runtime/handle_summary_worker.py`
- Create: `src/parallax/integrations/openai_agents/watchlist_handle_summary_client.py`
- Modify: `src/parallax/app/runtime/repository_session.py`
- Modify: `src/parallax/app/runtime/providers_wiring.py`
- Modify: `src/parallax/app/runtime/app.py`
- Modify: `src/parallax/domains/social_enrichment/runtime/enrichment_worker.py`
- Tests: `tests/unit/test_enrichment_worker_runtime.py`, `tests/integration/test_enrichment_worker.py`, `tests/integration/watchlist/test_watchlist_intel_worker.py`

- [ ] Add `WatchlistIntelRepository` to `RepositorySession` so all writes use the existing UOW.
- [ ] Add provider wiring for `OpenAIAgentsWatchlistHandleSummaryClient`, using `settings.watchlist_handle_summary_model` or `settings.llm_model`.
- [ ] Add `HandleSummaryWorker` fields to `CliRuntime`, start/stop lifecycle, and readiness diagnostics.
- [ ] Implement worker loop using the Pulse worker pattern: bounded batch, claim, process, `last_result`, `last_error`, graceful stop.
- [ ] Change `EnrichmentWorker._complete_job_sync` to enqueue summary job in the same transaction after `complete_social_event_job` and `HarnessSnapshotBuilder.materialize`.
- [ ] The enrichment hook must only run when:
  - `result.is_signal_event` is true;
  - event has `is_watched=true`;
  - normalized `author_handle` is non-empty;
  - watchlist summary feature is enabled.
- [ ] Add a backfill operation, either CLI or repository method exposed through doctor, that scans existing `social_event_extractions` where `is_signal_event=true` and no summary exists/pending for that handle.

## Task 4: HTTP API

**Files:**
- Modify: `src/parallax/app/surfaces/api/http.py`
- Modify: `src/parallax/app/surfaces/api/schemas.py`
- Modify: `docs/CONTRACTS.md`
- Tests: `tests/integration/watchlist/test_watchlist_intel_api.py`

- [ ] Add `WatchlistHandleSummaryData` and `WatchlistHandleTimelineData` schemas with permissive `JsonObject` payloads matching current API style.
- [ ] Add `GET /api/watchlist/handle/{handle}/summary`.
- [ ] Add `GET /api/watchlist/handle/{handle}/timeline?scope=signal|all&cursor=&limit=`.
- [ ] Validate handle with normalized ASCII-ish X handle characters: `^[A-Za-z0-9_\\.\\-]{1,64}$`.
- [ ] Validate configured handle membership against `runtime.settings.handles`; return 404 for unknown handles.
- [ ] Return 400 for invalid cursor, 422 for invalid limit/scope via FastAPI or explicit `ApiBadRequest`.
- [ ] Integration tests cover ready summary, not_ready summary, unknown handle, signal/all timeline, cursor page 2, and URL encoded handles.

## Task 5: Frontend Query Layer And Route State

**Files:**
- Create: `web/src/features/watchlist/model/handleIntelTypes.ts`
- Create: `web/src/features/watchlist/state/watchlistRouteState.ts`
- Create: `web/src/features/watchlist/api/useHandleSummaryQuery.ts`
- Create: `web/src/features/watchlist/api/useHandleTimelineQuery.ts`
- Modify: `web/src/features/watchlist/index.ts`
- Tests: `web/tests/unit/features/watchlist/state/watchlistRouteState.test.ts`, `web/tests/component/features/watchlist/api/useHandleTimelineQuery.test.tsx`

- [ ] Define `WatchlistScope = "signal" | "all"`.
- [ ] Parse `/watchlist?handle=<handle>&scope=<scope>` with default `scope="signal"`, preserving current handle normalization.
- [ ] Add `useHandleSummaryQuery({ handle, token })` with `staleTime=60_000` and `refetchInterval=60_000`.
- [ ] Add `useHandleTimelineQuery({ handle, scope, token })` with `useInfiniteQuery`, `getNextPageParam`, `staleTime=15_000`.
- [ ] Query hooks live in `features/watchlist/api` and use `getApi` only there.
- [ ] Tests assert params include handle/scope/cursor/limit and that switching scope changes query key.

## Task 6: Frontend UI Replacement

**Files:**
- Create: `web/src/features/watchlist/ui/HandleTopicSummary.tsx`
- Create: `web/src/features/watchlist/ui/HandleTimeline.tsx`
- Create: `web/src/features/watchlist/ui/HandleTimelineItem.tsx`
- Create: `web/src/features/watchlist/ui/handleIntel.css`
- Modify: `web/src/features/watchlist/ui/WatchlistPage.tsx`
- Tests: `web/tests/component/features/watchlist/ui/HandleTopicSummary.test.tsx`, `web/tests/component/features/watchlist/ui/HandleTimeline.test.tsx`, `web/tests/routes/watchlist.route.test.tsx`

- [ ] Insert `HandleTopicSummary` between `SignalStrip` and `watchlist-monitor-grid`.
- [ ] Replace `EvidenceStream` with `HandleTimeline`, leaving `ClusterPanel` and `RiskPanel` temporarily props-based.
- [ ] Render each timeline item with:
  - relative time;
  - `summary_zh` as primary copy when present;
  - signal/non-signal pill;
  - event type, subject, anchor terms;
  - cashtags/hashtags;
  - collapsed original text via `<details>`.
- [ ] Add segmented scope tabs that write URL search params and trigger infinite-query refresh.
- [ ] Empty signal state shows a compact action to switch to all scope.
- [ ] Load-more button uses `fetchNextPage`; IntersectionObserver can be added after button path passes tests.
- [ ] CSS follows existing Obsidian Desk tokens, class prefix `watchlist-handle-*`, no global selectors outside this feature import.

## Task 7: Docs, Tech Debt, And Verification

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/TECH_DEBT.md`
- Modify: `docs/generated/db-schema.md` through `make docs-generated`

- [ ] Add `domains/watchlist_intel` to architecture domain table.
- [ ] Add API contracts for summary and timeline endpoints.
- [ ] Add tech debt entries:
  - `watched_event_gate-zh-bias`: Chinese non-entity watched tweets can miss enrichment.
  - `watchlist-page-data-source-split`: Watchlist page temporarily uses React Query for timeline/summary and props for aside clusters.
- [ ] Regenerate DB schema docs.
- [ ] Run backend tests:
  - `uv run pytest tests/domains/watchlist_intel/ -v`
  - `uv run pytest tests/integration/watchlist/ -v`
  - `uv run pytest tests/unit/test_enrichment_worker_runtime.py tests/integration/test_enrichment_worker.py -v`
- [ ] Run frontend tests:
  - `cd web && npm test -- --run tests/unit/features/watchlist tests/component/features/watchlist tests/routes/watchlist.route.test.tsx`
  - `cd web && npm run typecheck`
  - `cd web && npm run lint`
- [ ] Run full gate when the branch is ready: `make check-all`.
- [ ] Manual browser verification:
  - open `/watchlist?handle=<configured>&scope=signal`;
  - verify summary card, timeline signal scope, all scope, load more;
  - verify no failing `/api/watchlist/*` requests;
  - verify mobile width has no overlap.

---

## Acceptance Criteria

- Timeline can page through a configured handle's historical events with stable `(received_at_ms, event_id)` cursor.
- `scope=signal` uses `social_event_extractions.is_signal_event=true`; `scope=all` shows raw events even without extraction.
- Chinese `summary_zh` is visible before original English text.
- Summary worker produces 1-5 Chinese topics and persists the watermark `signal_count_at_gen`.
- Enrichment completion and watchlist summary job enqueue are atomic.
- Summary worker failure is retryable and visible through runs audit / worker diagnostics.
- The page still works when summary is not ready or LLM is disabled.
- Existing Signal Pulse, token radar, notification, and harness tests are unaffected except for intentional worker diagnostics additions.

## Residual Risks

- The summary depends on enrichment coverage. Without fixing `watched_event_gate`, some Chinese non-entity tweets remain raw-only.
- `scope=all` can become dense for very active accounts; this plan caps page size at 100 and uses keyset pagination, but no full-text filter inside the handle timeline yet.
- If many handles burst simultaneously, LLM cost is controlled by per-handle dedup and min interval, but total hourly spend still needs runs audit monitoring after deployment.
- Existing `idx_events_author_received` may be good enough for small DBs, but production cursor correctness and performance require the new event-id tie-breaker index before rollout.
