# Spec - Earnings Hard Delete

**Status**: Approved
**Date**: 2026-05-29
**Owner**: qinghuan / Codex
**Related**: `docs/superpowers/specs/active/2026-05-22-equity-event-intel-cn.md`, `docs/superpowers/specs/active/2026-05-26-earnings-product-hard-cut-root-fix-cn.md`

## Background

当前仓库已经把 earnings 产品做成完整 `equity_event_intel` 域，而不是一个可忽略的前端入口。域文档定义它负责美国股票公司事件、earnings/calendar read models 和 cited agent briefs，且不写 News Intel、Token Radar、Pulse 或 market tick facts（`src/gmgn_twitter_intel/domains/equity_event_intel/ARCHITECTURE.md:3`）。它拥有 PostgreSQL facts/control/read-model 表，包括 `equity_event_sources`、`equity_expected_events`、`equity_event_documents`、`equity_event_evidence_jobs`、`equity_company_events`、`equity_event_agent_briefs` 和页面 read models（`src/gmgn_twitter_intel/domains/equity_event_intel/ARCHITECTURE.md:13`）。

后端 API 已注册 `/api/equity-events*` route，`routes_equity_events` 被导入并 include 到主 API router（`src/gmgn_twitter_intel/app/surfaces/api/http.py:8`, `src/gmgn_twitter_intel/app/surfaces/api/http.py:34`）。SPA fallback 也显式注册 `/earnings` 和 `/earnings/{path:path}`（`src/gmgn_twitter_intel/app/runtime/app.py:134`）。前端 router 把 `earnings/*` lazy-load 到 `equity-events.route`（`web/src/routes/router.tsx:44`），左侧导航显示 `Earnings` 并指向 `/earnings`（`web/src/features/cockpit/ui/appNavigation.ts:77`）。

运行时已经有 7 个 equity-event worker manifest：source reconcile、fetch、evidence hydration、process、story projection、brief、page projection（`src/gmgn_twitter_intel/app/runtime/worker_manifest.py:515`）。这些 worker 写入 facts、control plane、read models，并通过 `equity_event_*` wake channels 串联（`src/gmgn_twitter_intel/app/runtime/worker_manifest.py:528`, `src/gmgn_twitter_intel/app/runtime/worker_manifest.py:545`, `src/gmgn_twitter_intel/app/runtime/worker_manifest.py:666`）。worker factory registry 也显式注册 `equity_event_intel.py`（`src/gmgn_twitter_intel/app/runtime/worker_factories/__init__.py:197`）。

配置 schema 已包含 `equity_event_intel`、expected events、agent lane，以及独立 worker settings（`src/gmgn_twitter_intel/platform/config/settings.py:748`, `src/gmgn_twitter_intel/platform/config/settings.py:821`, `src/gmgn_twitter_intel/platform/config/settings.py:1452`）。默认配置生成器会把 `equity_event_intel` 写入 `config.yaml`，并把所有 `equity_event_*` worker 写入 `workers.yaml`（`src/gmgn_twitter_intel/platform/config/settings.py:1992`, `src/gmgn_twitter_intel/platform/config/settings.py:2331`）。`load_settings` 对 config 和 workers 都用 pydantic `extra="forbid"` schema 加载，删除 schema 后运行配置中的残留字段会导致启动失败（`src/gmgn_twitter_intel/platform/config/settings.py:1888`）。

数据库迁移 `20260523_0083` 创建了第一批 equity-event 表，例如 `equity_event_sources` 和 `equity_event_fetch_runs`（`src/gmgn_twitter_intel/platform/db/alembic/versions/20260523_0083_equity_event_intel.py:1`, `src/gmgn_twitter_intel/platform/db/alembic/versions/20260523_0083_equity_event_intel.py:16`）。后续迁移继续添加 runtime indexes、fact shape、evidence hard-cut、payload hashes、fetch reaper 和 process jobs。架构测试当前还把 `equity_event_intel` 当成必须存在的 domain 和 provider domain（`tests/architecture/test_src_domain_architecture.py:13`, `tests/architecture/test_src_domain_architecture.py:32`），并有专门测试要求该 domain 存在（`tests/architecture/test_equity_event_intel_boundaries.py:48`）。

## Problem

现阶段 earnings 产品链路没有被想清楚，继续保留会让后端 worker、DB 表、config、前端入口、API contract 和测试维护成本持续存在。半禁用会隐藏复杂度但不会消除维护面，后续任何 worker/runtime/config/schema 改动都还需要照顾一条不打算继续推进的链路。

## First Principles

1. **不保留半产品。** 如果用户不可用且产品语义未定，代码、runtime、API、前端、测试和配置都应从主线移除，避免它继续参与架构约束和运行时启动路径。
2. **PostgreSQL business truth 必须清晰。** 既然 `equity_event_*` 和 `equity_expected_events` 不再代表当前产品事实，它们应该通过显式 destructive migration 从运行库 drop 掉，而不是留下可被误读的旧事实表。
3. **配置必须可启动。** 因为配置 schema 禁止额外字段，代码删除必须配套清理 repo 默认 config、example config 和 operator-owned `~/.gmgn-twitter-intel/config.yaml` / `workers.yaml` 中的 earnings 段。

## Goals

- G1. `/earnings` 和 `/api/equity-events*` 从产品 surface 消失；前端导航、SPA fallback、API router、OpenAPI/generated client 中没有 earnings/equity-event route。
- G2. `equity_event_intel` runtime 消失；没有 equity-event worker manifest、worker factory、wake channel、queue health adapter、provider wiring 或 OpenAI equity brief lane。
- G3. 现有运行库中的 earnings/equity-event 表被显式 drop；迁移可重复执行在目标库上完成，不保留 read model、job、audit、brief 或 calendar 表数据。
- G4. repo 默认配置、example 配置、operator runtime config 都不再包含 `equity_event_intel` 或 `equity_event_*` worker 配置；清理 operator config 时不打印 secret 值。
- G5. 测试和架构约束反映删除后的世界：不再要求 `equity_event_intel` 存在，同时能防止 `/earnings` 或 `equity_event_intel` runtime 被意外重新挂回。

## Non-Goals

- N1. 不重新设计 earnings 产品，也不保留 dormant feature flag。
- N2. 不删除普通新闻、宏观或股票语义里自然出现的 `earnings` 文本，例如 news classification 中的 earnings 关键词或 macro average hourly earnings。
- N3. 不删除共享的 US equity symbol universe 或 stocks/token-equity 基础设施，除非实现阶段证明某个对象只服务于被删除链路。
- N4. 不迁移、导出或备份 equity-event 产品数据作为业务 artefact；这次是删除现有数据。仅对 operator config 文件做安全备份。
- N5. 不修改 GMGN/Twitter ingest、Token Radar、News Intel、Macro、Watchlist、Pulse 等当前核心产品行为。

## Target Architecture

删除后，`gmgn-twitter-intel` 不再有独立 earnings/equity-event 产品域。当前核心产品仍由 ingestion、asset_market、token_intel、cex_market_intel、macro_intel、narrative_intel、news_intel、pulse_lab、watchlist_intel、notifications 等域组成。股票相关能力只保留已被其他产品使用的共享基础设施和 `/stocks` 相关 surface；`/earnings` 不再作为导航项、路由、API 或 worker chain 存在。

运行时 worker registry 中没有 `equity_event_*` worker，也没有 `equity_event_intel.py` factory。provider wiring 不再构造 equity-event SEC/IR/calendar provider，也不再构造 `equity_event.brief` OpenAI provider。agent runtime lane defaults 不再包含 `equity_event.brief`。

数据库层通过新的 Alembic revision 做一次 destructive cleanup。该 migration drop 所有 earnings/equity-event owned tables、indexes 和 queue/read-model tables；若表不存在也应安全完成。历史 migration 文件可以作为 Alembic history 保留，但当前 head 之后的 schema 不应包含这些表。

配置层只保留仍在当前产品中使用的 settings。`Settings` 删除 `equity_event_intel` 字段和相关 computed property；`WorkersSettings` 删除全部 `equity_event_*` worker fields。默认 YAML、example YAML 和 operator config 都要同步移除这些段。

## Conceptual Data Flow

删除前：

```text
equity config/calendar
  -> equity_event_source_reconcile
  -> equity_event_fetch
  -> equity_event_evidence_hydration
  -> equity_event_process
  -> equity_event_story_projection
  -> equity_event_brief
  -> equity_event_page_projection
  -> /api/equity-events*
  -> web /earnings
```

删除后：

```text
GMGN/Twitter ingest -> token/news/macro/watchlist/pulse surfaces
news fetch/process/projection -> /api/news* -> web /news
macro sync/projection -> /api/macro* -> web /macro
```

`equity config/calendar -> /earnings` 这条链路整体不存在；没有替代流，也没有空 read model。

## Core Models

删除对象包括但不限于以下 semantic groups：

- Product facts/control: `equity_event_sources`, `equity_event_universe_members`, `equity_expected_events`, `equity_event_fetch_runs`, `equity_provider_documents`, `equity_event_documents`, `equity_event_evidence_jobs`, `equity_event_process_jobs`.
- Event facts/evidence: `equity_company_events`, `equity_event_source_spans`, `equity_event_fact_candidates`, `equity_event_evidence_artifacts`.
- Agent/read models: `equity_event_agent_runs`, `equity_event_agent_briefs`, `equity_event_brief_states`, `equity_event_story_groups`, `equity_event_story_members`, `equity_event_page_rows`, `equity_event_calendar_rows`, `equity_event_alert_candidates`, `equity_company_timeline_rows`, `equity_event_projection_dirty_targets`.
- Runtime/config models: `EquityEventIntelSettings`, `EquityExpectedEventSettings`, all `EquityEvent*WorkerSettings`, `equity_event.brief` lane defaults, `EquityEventIntelProviders`, equity-event worker factory specs.

Preserved models:

- `us_equity_symbol_universe` and related shared equity symbol fixtures/tests if they are used outside `/earnings`.
- News/macro text categories that contain the English word "earnings" but are not the deleted product domain.

## Interface Contracts

- HTTP: `/api/equity-events`, `/api/equity-events/calendar`, `/api/equity-events/summary`, `/api/equity-events/sources/status`, `/api/equity-events/{event_id}`, `/api/equity-events/stories/{story_id}`, and `/api/equity-events/companies/{ticker}/timeline` are removed from the API router and generated OpenAPI contract.
- Frontend routes: `/earnings`, `/earnings/calendar`, `/earnings/events/:eventId`, `/earnings/stories/:storyId`, and `/earnings/companies/:ticker` are removed from the React router and backend SPA fallback list.
- CLI/config: `gmgn-twitter-intel config` should still report the active config paths, but generated config content should not include earnings/equity-event sections.
- Runtime config cleanup: implementation may edit `~/.gmgn-twitter-intel/config.yaml` and `~/.gmgn-twitter-intel/workers.yaml` to remove only the deleted keys. It must create timestamped backups and must report only paths and redacted booleans, never secret values.
- DB migration: applying current Alembic head deletes existing equity-event tables/data. Downgrade may be empty or explicitly non-restorative, because this work intentionally drops data and no business restore path is promised.

## Acceptance Criteria

- AC1. WHEN the app starts after the change THEN no `equity_event_*` worker is constructed, scheduled, listed in worker manifest output, or included in queue health.
- AC2. WHEN `/api/equity-events` or any former equity-event API route is requested THEN the route is not served by an equity-event handler and is absent from generated OpenAPI.
- AC3. WHEN the frontend is built THEN navigation contains no `Earnings` item and the React router contains no `earnings/*` route.
- AC4. WHEN Alembic migrations are applied to a database that contains the existing equity-event schema THEN all owned equity-event tables and their data are removed.
- AC5. WHEN `uv run gmgn-twitter-intel config` is run after operator config cleanup THEN it succeeds and reports `~/.gmgn-twitter-intel/config.yaml` plus `~/.gmgn-twitter-intel/workers.yaml` paths without rejected `equity_event_intel` or `equity_event_*` keys.
- AC6. WHEN `rg -n "equity_event_intel|equity-events|/earnings|equity_event\\.brief|equity_event_" src web tests docs config.example.yaml` is reviewed THEN remaining hits are either historical Alembic migration identifiers, this hard-delete spec/plan artefact, or deliberate non-product text documented in the implementation summary.
- AC7. WHEN backend and frontend test suites run at the selected verification level THEN no tests fail because they still expect `equity_event_intel`, `/earnings`, or `/api/equity-events*` to exist.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Dropping a shared table used by stocks/token-equity code. | High | Treat only `equity_event_*`, `equity_expected_events`, and directly owned dependent tables as drop candidates; verify `rg` references before writing migration. |
| Operator config fails to load after schema deletion because old keys remain. | High | Clean `~/.gmgn-twitter-intel/config.yaml` and `workers.yaml` with backups before final runtime verification. |
| OpenAPI/client generated artefacts keep stale routes. | Medium | Regenerate or update generated API/types as part of implementation and include route absence in acceptance checks. |
| Architecture tests encode old domain requirements. | Medium | Replace existence tests with absence/guard tests that prevent accidental reintroduction of the deleted runtime. |
| False-positive `earnings` text cleanup deletes valid news/macro semantics. | Medium | Delete by ownership boundary, not by raw keyword. Preserve non-product "earnings" references. |

## Evolution Path

If earnings/company-event intelligence becomes important again, it should return through a new spec with a narrower product question, explicit provider evidence model, and a fresh schema. Future work should not reuse dropped runtime names or silently resurrect `/earnings`; a new product should justify its surfaces, data ownership, and operational burden from scratch.

## Alternatives Considered

- **Disable-only feature flag.** Rejected because worker/config/API/frontend/test surfaces would remain in the repo and continue consuming maintenance attention.
- **Archive code in-place.** Rejected because dormant product code still pollutes search, architecture constraints, generated types, and runtime mental model.
- **Keep DB tables for possible future analysis.** Rejected by product decision: existing data is not current business truth and should be removed with the product chain.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Delete the earnings/equity-event product surface, runtime, config schema, tests, docs references, and DB tables/data. |
| Ask first | Delete any table or module that is not named/owned by `equity_event_intel` but appears related to U.S. equities. |
| Never | Print secrets from operator config; delete news/macro uses of the word `earnings`; leave a disabled worker/API/frontend shell behind. |
