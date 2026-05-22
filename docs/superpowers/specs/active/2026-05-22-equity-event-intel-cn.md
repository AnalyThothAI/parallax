# Spec - Equity Event Intel

**Status**: Draft, ready for implementation planning
**Date**: 2026-05-22
**Owner**: Qinghuan / Codex
**Related**:
- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/FRONTEND.md`
- `docs/CONTRACTS.md`
- `docs/WORKERS.md`
- `docs/TESTING.md`
- `src/gmgn_twitter_intel/domains/news_intel/ARCHITECTURE.md`
- `docs/superpowers/specs/active/2026-05-19-news-intel-kappa-cqrs-cn.md`
- Reference-only old repo: `/Users/qinghuan/Documents/code/filing-event-research`

## 一句话

在当前 `gmgn-twitter-intel` 仓库内新增独立 `equity_event_intel` 域和 `/earnings` 前端入口，把 Nasdaq/US 科技股的财报、SEC filing、业绩电话会、指引变更和重大公司更新做成事件新闻流：事件先出现，证据随后补全，分析可审计地增量更新；旧 `filing-event-research` 只作为经验参考，不迁移它的前端和 ticker-first 产品形态。

## 结论

可行，而且应该在当前仓库做。

原因是当前项目已经具备这类产品需要的基础设施：PostgreSQL facts + rebuildable read models、worker registry、provider wiring、HTTP API、WebSocket/notification wake 语义、React route/feature 结构、News Intel 的事件流范式和严格的架构测试。新增模块的主要工作不是“能不能接数据”，而是把公司事件建模成一等事实和读模，避免落回旧项目那种以股票页和 digest 为中心的形态。

不建议在旧仓库继续做。旧仓库的问题不是缺一个前端页面，而是产品入口、数据组织和运行时心智都是 ticker-first：用户先选股票，再看 digest。目标产品需要的是 event-first：用户先看到“发生了什么、哪个公司、什么证据、是否影响交易、下一步缺什么”，再进入公司维度。

也不建议把它塞进现有 `news_intel`。`news_intel` 是通用新闻/crypto/token story 语义；财报和公司更新有强结构化来源、预期日历、官方文档、表格指标、电话会 transcript、filing revision、事件后价格反应等专有生命周期。可以复用 News Intel 的 Kappa/CQRS 模式和页面语法，但事实表、worker、API、frontend feature 都应独立。

## Background

当前项目的根架构是 Kappa/CQRS：

- PostgreSQL material facts 是业务真相。
- Derived read models 可重建。
- 每个 read model 只有一个 runtime writer。
- `NOTIFY` 只是 wake hint，listener 必须重读 DB 并保留 bounded `interval_seconds` catch-up。
- Provider raw frames 是输入，不是事实。

这正好适合财报/公司事件流，因为这类产品天然存在多个时间层：

1. **预期事件**: 财报日期、电话会时间、filing due window、investor day。
2. **原始发生**: SEC filing 出现、press release 发布、8-K 披露、transcript 到达。
3. **结构化解析**: revenue/EPS/guidance/segment/capex/buyback/management change 等事实候选。
4. **证据定位**: 文档、exhibit、paragraph/table/span、revision/diff。
5. **分析产物**: agent brief、风险点、交易相关变化、下一步 watch items。
6. **事件后状态**: 价格反应、量能、同业扩散、后续 conference call 或 analyst revision。

旧 `filing-event-research` 已经证明 SEC/document/filing 方向值得做，但它把用户入口放在股票维度，前端围绕 issuer digest 和 review page 组织；这与“第一事件更新流”目标冲突。当前仓库的 News Intel 则已经证明了正确的 runtime 形态：raw item 可见、process worker 增量处理、story/page projection 独立写 read model、API/Frontend 只读。

## Problem

目标用户是跟踪和交易 Nasdaq/US 科技股的人。他们不想每天挨个打开公司页，也不想等一个完整 digest 生成后才知道发生了什么。真正的工作流是：

- 开盘前和盘后快速看到哪些公司发生了 P0 事件。
- 财报一出先看到原始来源、公司、事件类型和重要性。
- 结构化指标和官方证据逐步补齐。
- LLM 分析必须能回指原文，不能凭空总结。
- 事件之间要有 continuity：同一家公司同一财报周期的 press release、10-Q、8-K、call transcript、presentation、guidance update 应聚成同一个 story。
- 用户能从 feed 进入 detail，判断“现在能不能交易、还缺什么确认、下一条 watch 是什么”。

当前项目没有 `equity_event_intel` 域、没有公司事件事实表、没有 earnings/calendar read model、没有 event-first 前端 route。已有 `/stocks-radar` 偏社交/市场注意力，不适合承载财报事实。已有 `news_intel` 能作为架构参考，但不应承担财报专属语义。

## First Principles

**事件先于股票页。** 用户的第一屏应是 event tape，而不是 ticker list。Ticker detail 是 drill-down，不是产品入口。

**预期事件和实际事件都要物化。** 财报日历不是 UI 辅助信息，它是用户预期和 missed-event 检测的基础事实。实际 filing/press release 到达后，应能与预期事件关联。

**原始证据先出现，分析后补全。** 事件流必须允许 raw document/event 先展示，解析、fact candidates、brief、diff、price reaction 后续增量更新。

**LLM 不是事实源。** Agent 可以写 brief、提取候选、总结变化，但 accepted fact 必须来自可追溯 source document/span/table 和 deterministic validation。

**公司事件不是普通新闻。** 官方 SEC/IR/press release 的 source role、event slot、filing form、period、fiscal quarter、exhibit、table extraction、transcript section 都是产品核心，不应压平成 title/summary/news item。

**读模服务页面，事实服务审计。** `/earnings` 页面应主要读 `equity_event_page_rows`、calendar rows 和 detail read models；不能在前端或 API request path 里做 provider calls、LLM、dedup、document parsing。

**交易视角不是自动交易。** 产品可以标注 surprise、guidance direction、source authority、missing confirmation、post-event reaction，但不执行交易、不生成自动下单、不把结果写入交易决策闭环。

## Goals

- **G1 Event-first product.** 新增 `/earnings` 页面，第一屏展示公司事件流，支持 Nasdaq/US tech universe、事件类型、优先级、session、状态、source role 过滤。
- **G2 Earnings calendar.** 物化预期事件，至少支持 upcoming/recent earnings calendar，并能显示 expected vs actual arrival。
- **G3 Raw document visibility.** SEC filing、press release、IR release、transcript 等原始事件到达后，即使还没有完整解析，也必须能进入 feed。
- **G4 Structured facts.** 财报核心字段、guidance、segment、buyback、management change、material contract、risk/update 等进入 fact candidate/accepted flow，带 evidence span/table 引用。
- **G5 Story continuity.** 同一公司同一财报周期或重大更新链路应聚成 story，保留每个 document/member 的 source role 和时间线。
- **G6 Agent analysis with citations.** Agent brief 可以生成完整解析、风险点和交易相关变化，但每个 claim 必须能回指 source span 或 accepted fact。
- **G7 Rebuildable read models.** Event feed、calendar rows、story rows、alert candidates 都是可重建读模，各自有唯一 runtime writer。
- **G8 Missed wake safe.** 丢失 `NOTIFY` 或 worker 重启后，所有处理链路仍能通过 bounded interval catch-up 补齐。
- **G9 Current repo integration.** 模块必须遵守当前仓库 architecture tests、worker registry、provider wiring、frontend CSS harness 和 docs contract。

## Non-goals

- 不在 `/Users/qinghuan/Documents/code/filing-event-research` 继续实现。
- 不迁移旧项目前端，不复刻 issuer digest 页面，不把旧 review page 搬进当前仓库。
- 不把财报事件塞入现有 `news_intel` 表。
- 不把股票 ticker 字符串当作唯一 identity；至少需要 canonical equity symbol/company identity。
- 不让 LLM summary 成为 material fact。
- 不在 HTTP request handler 或 React frontend 做 SEC/IR provider calls、document parsing、LLM 调用、fact validation。
- 不做自动交易、订单执行、回测平台或交易建议合规包装。
- 不要求 V1 覆盖所有美股。默认 universe 是 Nasdaq/US tech，可通过配置扩展。
- 不要求 V1 做完整 valuation model、DCF、analyst estimate consensus、options flow 或 full transcript NLP。

## Domain Name And Product Surface

后端 bounded context 使用 `equity_event_intel`。

用户可见 route 使用 `/earnings`，因为用户的核心任务是财报和公司重大更新跟踪；页面标题可以是 `Earnings & Events`。API 使用 `/api/equity-events`，避免把产品语义限制成 earnings-only。

建议结构：

```text
src/gmgn_twitter_intel/domains/equity_event_intel/
  ARCHITECTURE.md
  models/
  services/
  workers/
  repositories/
  projections/
  providers/

web/src/features/equity-events/
  api/
  model/
  state/
  ui/
  equityEvents.css

web/src/routes/equity-events.route.tsx
```

Frontend CSS namespace 使用 `equity-event-`，并在 frontend architecture harness 中登记。全局 cockpit nav label 使用 `Earnings` 或 `Events`，但 feature folder 保持 `equity-events`，避免和已有 `news`、`stocks`、`token` 语义混淆。

## Event Taxonomy

事件优先级按交易/跟踪重要性分层。优先级是产品读模字段，不是 provider 原始字段。

| Priority | Event types | Source examples | User meaning |
|----------|-------------|-----------------|--------------|
| P0 | earnings release, 10-Q, 10-K, 8-K material disclosure, guidance raise/cut, preliminary results, restatement, merger/acquisition, CEO/CFO change, buyback/dividend, major contract, regulatory/legal material update | SEC filing, official IR release, company press release | 需要立即进入 feed 和 alert candidates |
| P1 | earnings call transcript, presentation, investor day, shareholder letter, exhibit update, segment detail, conference remarks | transcript provider, SEC exhibit, IR deck | 用于补全分析和 story timeline |
| P2 | analyst/news report about company update, exchange notice, non-official rumor, media summary | trusted media/API/news source | attention lane，不直接成为 accepted fact |
| P3 | calendar schedule, expected report date, call schedule, reminder, late/missing expected event | calendar provider, company IR schedule | 预期管理和 missed-event detection |

每个 event 至少应包含：

- `event_id`
- `company_id`
- `ticker`
- `event_type`
- `priority`
- `source_role`
- `event_time`
- `discovered_at`
- `lifecycle_status`
- `story_id` when projected
- `evidence_status`
- `brief_status`

## Target Product Experience

### `/earnings` first viewport

第一屏是事件流，不是股票列表。默认排序按 `latest_event_at DESC`，P0 事件在盘后/盘前窗口中优先浮出。

每一行/卡片展示：

- 公司 ticker/name。
- 事件类型和优先级。
- source role，例如 SEC filing、IR release、transcript、calendar。
- event time、discovered time、processing state。
- 一句话 deterministic headline。
- 关键 facts 状态，例如 `raw only`、`facts extracted`、`brief ready`、`needs confirmation`。
- story continuity，例如 `FY2026 Q1 earnings story`。
- evidence availability，例如 document/table/span count。

### Event detail

Event detail 是“交易前核查面”：

- Timeline: expected event -> raw document -> parsed facts -> brief -> transcript -> follow-up.
- Source documents: SEC filing、press release、exhibits、transcript、presentation。
- Fact table: metric/claim、period、value、unit、direction、evidence、validation status。
- Agent brief: summary、surprise、guidance direction、risks、watch items、citations。
- Diff: revised filing or repeated document changes。
- Reaction snapshot: price/volume context only when persisted facts exist; V1 可先显示 unavailable。

### Calendar

Calendar 是 event feed 的另一个视图，不是独立 ticker board。它回答：

- 未来哪些 Nasdaq/US tech 公司预计发布财报。
- 哪些 expected events 已经被 actual event 匹配。
- 哪些 expected events 超时未出现。
- 哪些公司在同一 session/after-hours 形成事件簇。

## Target Architecture

新增 `equity_event_intel` bounded context。它读取外部 company/filing/calendar sources，并通过现有 stock/company identity 接口解析公司；它不写 `news_intel` facts，不写 Token Radar，不写 Pulse，不写 market tick facts。

```text
equity event sources + configured universe
  -> equity_event_source_reconcile
  -> equity_event_fetch
  -> equity_provider_documents + equity_event_documents + equity_expected_events
  -> equity_event_process
  -> equity_company_events + equity_event_fact_candidates + equity_event_source_spans
  -> equity_event_story_projection
  -> equity_event_story_groups + equity_event_story_members
  -> equity_event_brief
  -> equity_event_agent_runs + equity_event_agent_briefs
  -> equity_event_page_projection
  -> equity_event_page_rows + equity_event_calendar_rows + equity_event_alert_candidates
  -> /api/equity-events + /api/equity-events/calendar + /api/equity-events/{event_id}
  -> web /earnings
```

### Layer Ownership

| Layer | Owns | Does not own |
|-------|------|--------------|
| `equity_event_intel` | event source config, expected events, provider documents, company events, facts/candidates, source spans, story projection, page/calendar/alert read models | Generic news story scoring, token radar, pulse decisions, market tick truth |
| Stock/company identity | canonical US equity/company identity, Nasdaq/US tech universe membership where already available | Event parsing, SEC document lifecycle, agent brief |
| Agent runtime | brief generation, cited analysis, model run audit | Accepted fact authority |
| API surfaces | read-only translation from read services to `/api/equity-events*` | Provider IO, LLM, parsing, validation mutation |
| Frontend | rendering event feed, calendar, detail, filters, processing states | Event inference, scoring, source fetching |

## Core Tables

Names are proposed contract names for implementation planning. Exact column names can be refined, but ownership and truth boundaries should hold.

### Facts And Audit

| Table | Kind | Writer | Purpose |
|-------|------|--------|---------|
| `equity_event_sources` | control/fact | source reconcile/fetch worker | Configured SEC/IR/calendar/transcript sources, trust tier, enabled state, fetch cursor/cache |
| `equity_event_fetch_runs` | audit | `equity_event_fetch` | One provider fetch attempt, status, diagnostics, item counts |
| `equity_event_universe_members` | fact/control | reconcile/import worker | Nasdaq/US tech company universe membership and source |
| `equity_expected_events` | fact | calendar fetch/process | Expected earnings/call/filing events, due windows, provider/source |
| `equity_provider_documents` | provider observation | `equity_event_fetch` | Raw SEC/IR/calendar/transcript provider payload and payload hash |
| `equity_event_documents` | normalized fact | `equity_event_fetch` / process handoff | Normalized document/event source, canonical URL, company, form/type, period, discovered time |
| `equity_document_revisions` | fact | `equity_event_process` | Revision/hash lineage for updated filings or rolling releases |
| `equity_section_diffs` | fact/candidate | `equity_event_process` | Section/table-level diff between revisions |
| `equity_company_events` | fact | `equity_event_process` | Canonical company event row: type, priority, company, source role, event time, lifecycle |
| `equity_event_source_spans` | evidence fact | `equity_event_process` | Document/table/paragraph/span references for claims |
| `equity_event_fact_candidates` | candidate fact | `equity_event_process` and validator | Extracted claims, required slots, evidence refs, validation status |

### Read Models

| Table | Writer | Purpose |
|-------|--------|---------|
| `equity_event_story_groups` | `equity_event_story_projection` | Rebuildable story continuity object by company/event cycle/update chain |
| `equity_event_story_members` | `equity_event_story_projection` | Event/document membership and match reasons |
| `equity_event_agent_runs` | `equity_event_brief` | Agent run audit, model, prompt policy, input refs |
| `equity_event_agent_briefs` | `equity_event_brief` | Cited analysis artifact for story/event detail |
| `equity_event_page_rows` | `equity_event_page_projection` | Denormalized event feed rows for `/earnings` |
| `equity_event_calendar_rows` | `equity_event_page_projection` | Denormalized expected vs actual calendar rows |
| `equity_event_alert_candidates` | `equity_event_page_projection` | P0/P1 rows eligible for UI attention/notification |
| `equity_company_timeline_rows` | `equity_event_page_projection` | Company drill-down timeline rows |

`equity_event_agent_briefs` are read-model/product artifacts, not material facts. Any claim inside a brief must cite `equity_event_fact_candidates`, `equity_event_source_spans`, or source document references.

## Workers

| Worker | Runtime role | Writes | Wake-in | Wake-out |
|--------|--------------|--------|---------|----------|
| `equity_event_source_reconcile` | Reconcile operator config/universe into DB control rows | `equity_event_sources`, `equity_event_universe_members` | poll | `equity_event_sources_reconciled` |
| `equity_event_fetch` | Fetch SEC/IR/calendar/transcript providers with backoff/cursors | `equity_event_fetch_runs`, `equity_provider_documents`, `equity_event_documents`, `equity_expected_events` | poll, `equity_event_sources_reconciled` | `equity_event_document_written` |
| `equity_event_process` | Parse normalized documents, classify events, extract facts/spans/diffs | `equity_company_events`, `equity_event_fact_candidates`, `equity_event_source_spans`, `equity_document_revisions`, `equity_section_diffs` | `equity_event_document_written`, poll | `equity_event_processed` |
| `equity_event_story_projection` | Group related events/documents into continuity stories | `equity_event_story_groups`, `equity_event_story_members` | `equity_event_processed`, poll | `equity_event_story_updated` |
| `equity_event_brief` | Generate/update cited event/story analysis | `equity_event_agent_runs`, `equity_event_agent_briefs` | `equity_event_story_updated`, poll | `equity_event_brief_updated` |
| `equity_event_page_projection` | Build feed/calendar/alert/company timeline read models | `equity_event_page_rows`, `equity_event_calendar_rows`, `equity_event_alert_candidates`, `equity_company_timeline_rows` | document/process/story/brief wakes, poll | `equity_event_page_updated` |

Provider IO must not hold pinned DB sessions. Workers should claim/snapshot due work, release DB session, call provider, then persist in a fresh worker session.

Every worker must support missed wake recovery through `interval_seconds` catch-up. `NOTIFY` channels accelerate processing but are never required for correctness.

## Provider Strategy

Phase 1 sources should prefer structured or official endpoints:

- SEC EDGAR/company submissions and filing documents for actual filings.
- Company IR RSS/press release feeds where configured.
- Earnings calendar provider through configured source rows.
- Transcript source as optional Phase 2/3 provider.

The implementation should not build a general web crawler. Each provider adapter must normalize into `equity_provider_documents` first, then downstream workers decide event type and product meaning.

Provider raw payloads are inputs. Normalized `equity_event_documents`, `equity_expected_events`, `equity_company_events`, source spans and fact candidates are the product truth.

## Company Identity

Ticker display is not enough. The domain should use a canonical company/equity identity:

- Reuse existing US equity symbol registry/read interface when available.
- Store `ticker`, `exchange`, `company_name`, `cik` when available, and a canonical internal `company_id`.
- Nasdaq/US tech universe membership should be explicit and configurable.
- Ambiguous or missing company identity keeps a document in attention/raw lane; it must not become an accepted company event.

`stocks-radar` can remain a separate social/market attention product. `equity_event_intel` may link to stock pages by ticker, but it should not depend on request-time quote snapshots as business truth.

## Fact Candidate Contract

Each `equity_event_fact_candidate` should preserve:

- `candidate_id`
- `company_event_id`
- `company_id`
- `ticker`
- `event_type`
- `fact_type`
- `period`
- `metric_name`
- `value`
- `unit`
- `direction`
- `claim_text`
- `source_document_id`
- `source_span_id`
- `source_role`
- `required_slots`
- `validation_status`
- `rejection_reasons`
- `policy_version`
- `created_at`

Examples of fact types:

- `revenue_actual`
- `eps_actual`
- `revenue_guidance`
- `eps_guidance`
- `segment_revenue`
- `gross_margin`
- `operating_margin`
- `capex`
- `free_cash_flow`
- `share_buyback`
- `dividend_change`
- `headcount_change`
- `management_change`
- `material_contract`
- `risk_factor_update`
- `restatement`

Accepted fact rules:

- Required slots must be present.
- Company identity must be production eligible.
- Evidence must reference a source document/span/table.
- Source role must be strong enough for the fact type.
- LLM extracted values require deterministic validation against evidence.
- Media-only reports remain attention/reported lane unless supported by official source.

## Story Grouping

Story grouping should be deterministic first:

1. Same company + same fiscal period + same official event type.
2. Same SEC accession/document family.
3. Same canonical URL/content hash/provider document lineage.
4. Expected event matched to actual event within due window.
5. Press release + 8-K + 10-Q/K + call transcript within configured event window.
6. Fuzzy title/source/time overlap only as fallback, and must record match reason.

Story groups are read models. Material fact/candidate tables must not depend on story IDs for correctness. If story projection is rebuilt, feed and detail semantics should be recoverable from facts.

## Agent Briefs

Agent briefs are useful only after enough evidence exists. They should be scheduled by `equity_event_brief` when:

- P0/P1 company event exists.
- At least one official source document or accepted fact candidate exists.
- The event/story has not already been briefed under the current policy/input hash.

Brief output should include:

- executive summary
- what changed vs expectation or prior document
- core financial metrics
- guidance read
- risk/uncertainty
- trading-relevant watch items
- source citations
- missing evidence

The brief must degrade gracefully:

- `raw_only`: no analysis yet.
- `facts_partial`: deterministic facts exist, brief pending.
- `brief_ready`: cited analysis exists.
- `brief_stale`: new source/facts arrived after the brief.
- `brief_failed`: run failed with redacted diagnostic.

## API Contracts

### `GET /api/equity-events`

Returns paginated `equity_event_page_rows`.

Filters:

- `window`
- `universe`
- `ticker`
- `event_type`
- `priority`
- `source_role`
- `lifecycle_status`
- `brief_status`
- `q`
- `cursor`
- `limit`

Cursor pagination must be stable by `(latest_event_at_ms, event_id)`.

### `GET /api/equity-events/{event_id}`

Returns event detail:

- company identity
- event row
- source documents
- source spans
- fact candidates and accepted facts
- story membership
- brief status/content
- processing lifecycle

### `GET /api/equity-events/stories/{story_id}`

Returns story continuity:

- story summary
- member events/documents
- match reasons
- timeline
- facts rollup
- briefs
- missing expected sources

### `GET /api/equity-events/calendar`

Returns expected/actual calendar rows.

Filters:

- `from`
- `to`
- `universe`
- `ticker`
- `status`
- `session`

### `GET /api/equity-events/companies/{ticker}/timeline`

Returns company timeline rows for drill-down. This is a read endpoint, not a ticker-first primary product.

### `GET /api/equity-events/sources/status`

Returns source health:

- source id/type/role
- enabled state
- last fetch
- next due
- consecutive failures
- last redacted error type
- item/document counts

V1 can use HTTP polling plus existing frontend query invalidation. If WebSocket notification is added, it should emit invalidation hints after `equity_event_page_updated`; clients still refetch API read models.

## Frontend Contract

Add a new feature folder:

```text
web/src/features/equity-events/
  api/
  model/
  state/
  ui/
  equityEvents.css
```

Add route:

```text
/earnings
/earnings/calendar
/earnings/events/:eventId
/earnings/stories/:storyId
/earnings/companies/:ticker
```

Add route module:

```text
web/src/routes/equity-events.route.tsx
```

Add cockpit nav entry through the existing app navigation model. Static SPA fallback in backend app runtime must include the `/earnings` path family.

Frontend rules:

- API hooks live under feature `api/`.
- View model formatting lives under feature `model/`.
- CSS owner namespace uses `equity-event-`.
- No restyling shared UI internals or Obsidian `.ods-*` selectors.
- The page must render explicit empty/loading/stale/error states.
- The frontend must not compute fact acceptance, surprise score, source trust, event priority, or brief status.
- Badge/count data should come from a compact endpoint or read model field; avoid making `AppRoutes` prefetch the whole event feed just for nav state.

## Config

Runtime config follows current project rule: real data runs use operator-owned files in `~/.gmgn-twitter-intel/`, not repository fixtures.

Proposed config surface:

```yaml
equity_event_intel:
  enabled: true
  default_universe: nasdaq_tech
  source_reconcile:
    enabled: true
  sources:
    sec_edgar:
      enabled: true
    company_ir:
      enabled: false
    earnings_calendar:
      enabled: true
    transcripts:
      enabled: false
  agent:
    enabled: true
    lane: equity_event.brief
```

Worker settings belong in `workers.yaml`, following existing worker docs/inventory style:

```yaml
workers:
  equity_event_source_reconcile:
    enabled: true
    interval_seconds: 300
  equity_event_fetch:
    enabled: true
    interval_seconds: 60
  equity_event_process:
    enabled: true
    interval_seconds: 30
  equity_event_story_projection:
    enabled: true
    interval_seconds: 30
  equity_event_brief:
    enabled: true
    interval_seconds: 60
  equity_event_page_projection:
    enabled: true
    interval_seconds: 15
```

Implementation must redact secrets and report only paths/booleans/diagnostics, matching `AGENTS.md`.

## Integration Points In Current Repo

Implementation planning must account for these extension points:

- API router registration in `src/gmgn_twitter_intel/app/surfaces/api/http.py`.
- Worker registry in `src/gmgn_twitter_intel/app/runtime/worker_registry.py`.
- Worker factories under `src/gmgn_twitter_intel/app/runtime/worker_factories/`.
- Provider wiring under `src/gmgn_twitter_intel/app/runtime/provider_wiring/`.
- Settings in `src/gmgn_twitter_intel/platform/config/settings.py`.
- Repository session/runtime lifecycle in `src/gmgn_twitter_intel/app/runtime/repository_session.py`.
- Alembic migrations under `src/gmgn_twitter_intel/platform/db/alembic/versions/`.
- Frontend route registration in `web/src/routes/AppRoutes.tsx`.
- Navigation model in `web/src/features/cockpit/ui/appNavigation.ts`.
- SPA static mount routing in `src/gmgn_twitter_intel/app/runtime/app.py`.
- Frontend architecture harness in `web/tests/architecture/cssArchitectureHarness.test.ts`.

Architecture tests currently hard-code known domains, workers, provider domains, read model writers and CSS namespaces. Adding this module must update those tests and docs intentionally; failing tests are expected until the allowlists and docs are aligned.

## Testing And Acceptance Criteria

- **AC1.** When `equity_event_intel` is disabled, no equity event workers run and no `/earnings` data fetch loop is started.
- **AC2.** When a configured SEC/calendar source is enabled, source reconcile creates or updates `equity_event_sources` without relying on repository fixture files.
- **AC3.** When a provider returns a valid official filing/release, `equity_provider_documents` and `equity_event_documents` are persisted, and `/api/equity-events` can show a raw event row after projection.
- **AC4.** When an expected earnings event is matched by an actual filing/release within the configured window, `equity_event_calendar_rows` shows matched status.
- **AC5.** When a document contains a supported metric with evidence, `equity_event_fact_candidates` records value/unit/period/source span and validation status.
- **AC6.** When company identity is missing or ambiguous, the event remains raw/attention and cannot become an accepted company event.
- **AC7.** When `equity_event_page_rows` is truncated and page projection catch-up runs, `/api/equity-events` returns semantically equivalent rows rebuilt from facts.
- **AC8.** When `NOTIFY` is not delivered, all workers still process backlog through bounded interval catch-up.
- **AC9.** When a new official document arrives after a brief, the existing brief is marked stale or a new brief is scheduled by input hash/policy version.
- **AC10.** When V1 ships, repository search finds no runtime writes from `equity_event_intel` to `news_intel` facts, Token Radar rows, Pulse candidates or market tick facts.
- **AC11.** Frontend lint/architecture tests pass after adding the `equity-event-` CSS namespace and route-owned CSS.
- **AC12.** API contract tests verify list/detail/calendar/source-status responses and stable cursor pagination.
- **AC13.** Worker runtime contract tests list all new workers, factory files and single-writer read models.
- **AC14.** Docs are updated: `docs/ARCHITECTURE.md`, `docs/WORKERS.md`, `docs/CONTRACTS.md`, `docs/FRONTEND.md`, and new `src/gmgn_twitter_intel/domains/equity_event_intel/ARCHITECTURE.md`.

## Phase Shape

### Phase 0 - Spec and plan

Create this spec, then write an implementation plan that maps migrations, domain package, worker registration, API routes, frontend route and tests into small verifiable steps.

### Phase 1 - Backend event facts and feed read model

Implement domain package, migrations, source reconcile, fetch/process/page projection skeleton, API list/detail/source status, and minimal SEC/calendar provider path. No LLM required for this phase.

### Phase 2 - Frontend `/earnings`

Add route, nav entry, API hooks, event feed, event detail skeleton, calendar view, loading/error/empty states and architecture harness updates. The page should be useful with raw/fact status even before agent briefs exist.

### Phase 3 - Agent briefs and evidence UX

Add `equity_event_brief`, agent run audit, cited brief payload, stale detection and event detail evidence navigation.

### Phase 4 - Richer event lifecycle

Add transcript provider, document revisions/diffs, post-event reaction facts, peer/sector rollups, alert candidates and company timeline hardening.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Recreating the old ticker-first product | High | `/earnings` first screen is event feed; company timeline is drill-down only. |
| Overloading `news_intel` | High | Separate domain, tables, workers, API and frontend feature; reuse only architecture patterns. |
| LLM summaries becoming trusted truth | High | Briefs cite facts/spans and stay product artifacts; accepted facts require deterministic validation. |
| SEC/IR source latency or rate limits | High | Per-source cursors/cache/backoff, fetch audit, official endpoints first, no request-time provider calls. |
| Architecture tests blocking progress | Medium | Update allowlists, worker inventory, docs and CSS namespace as part of implementation plan. |
| Calendar quality varies by provider | Medium | Store provider/source role and confidence; distinguish expected from actual events. |
| Company identity drift | Medium | Use canonical company identity and CIK when available; ambiguous identity stays attention/raw. |
| Frontend route becomes heavy | Medium | Page consumes read models; nav badges use compact read state rather than whole-feed prefetch. |
| Event feed lacks enough context without price reaction | Low | V1 prioritizes official event/fact visibility; reaction facts are Phase 4. |

## Locked Decisions

- Build in current `gmgn-twitter-intel` repo.
- New backend bounded context name: `equity_event_intel`.
- New user-facing route family: `/earnings`.
- New API route family: `/api/equity-events`.
- Old repo is reference-only.
- Existing News Intel is architecture reference-only, not storage/runtime target.
- V1 truth boundary is PostgreSQL facts/read models, not frontend state, request-time provider calls or LLM output.

## Deferred Decisions

- Exact first earnings calendar provider.
- Exact SEC parsing depth in Phase 1 versus Phase 3.
- Whether transcripts enter Phase 2 or Phase 4.
- Whether post-event price reaction uses existing stock quote provider or a new persisted equity market facts table.
- Whether alerts remain page read model candidates or integrate with a broader notification domain later.

