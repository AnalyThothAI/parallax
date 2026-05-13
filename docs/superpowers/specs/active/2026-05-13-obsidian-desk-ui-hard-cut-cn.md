# Spec — Obsidian Desk UI Hard Cut

**Status**: In Progress  
**Date**: 2026-05-13  
**Owner**: Codex  
**Related**: `docs/superpowers/plans/active/2026-05-13-obsidian-desk-ui-hard-cut-plan-cn.md`, `docs/prototypes/obsidian-desk-v2-static.html`, `docs/FRONTEND.md`, `docs/ARCHITECTURE.md`, `docs/WORKFLOW.md`

## Background

当前前端已经进入 feature-layer 架构：`web/src/app/CockpitApp.tsx` 从 `@features/cockpit`、`@features/live`、`@features/search`、`@features/signal-lab`、`@features/stocks`、`@features/token-target` 组合页面，并通过 `IntelSocketProvider` 包住业务路由（`web/src/app/CockpitApp.tsx:1-27`, `web/src/app/CockpitApp.tsx:32-50`）。`docs/FRONTEND.md` 也定义了 `app/`、`features/<name>/api`、`features/<name>/model`、`features/<name>/ui`、`shared/ui`、`styles/` 等边界（`docs/FRONTEND.md:5-25`），并要求 feature UI 不直接拥有 server fetching、公共组件不做 server fetching、Score display 必须带 API 的 component breakdown（`docs/FRONTEND.md:29-36`）。

页面组合仍然高度集中在 Cockpit 容器内。`CockpitAppRoutes` 在同一个文件里拆出 live data、socket snapshot、selection、token detail、notifications 和 watchlist rows（`web/src/app/CockpitApp.tsx:53-134`），再根据当前 selection 在右侧 detail panel 中切换 `SignalLabInspector`、`EvidenceDetailDrawer`、`TokenDetailDrawer`（`web/src/app/CockpitApp.tsx:153-189`）。路由也仍在这里直接挂载 `/`、`/token/:targetType/:targetId`、`/stocks`、`/signal-lab`、`/search`（`web/src/app/CockpitApp.tsx:292-334`）。`web/src/app/AppRoutes.tsx` 目前只是返回 `CockpitApp`（`web/src/app/AppRoutes.tsx:1-4`），`web/src/routes/*.route.tsx` 只是 re-export，尚未成为真正的 route orchestration（`web/src/routes/live.route.tsx:1`, `web/src/routes/search.route.tsx:1`, `web/src/routes/signal-lab.route.tsx:1`）。

Token Radar 当前是 metric table。`TokenRadarTable` 表头是 `Token / Heat / Quality / Propagation / Market / Timing / Decision / Action`（`web/src/features/live/ui/TokenRadarTable.tsx:61-71`），排序标签也暴露为 `Opportunity / Heat / Quality / Propagation / Timing`（`web/src/features/live/ui/TokenRadarTable.tsx:7-13`）。`TokenRadarRow` 对每行分别展示 heat、quality、propagation、market、timing、decision、venue/action（`web/src/features/live/ui/TokenRadarRow.tsx:56-109`），大量展示逻辑与 JSX 绑定在同一个组件内（`web/src/features/live/ui/TokenRadarRow.tsx:114-316`）。这解释了用户反馈的“看不懂”：用户看到的是评分因子，而不是一个可执行的 token 案卷。

Selected Token 当前是 tab-first drawer。未选择时显示 `selected token / Select Token`（`web/src/features/live/ui/TokenDetailDrawer.tsx:106-119`）；选择后 header 展示 heat、quality、spread、timing 四个指标（`web/src/features/live/ui/TokenDetailDrawer.tsx:150-193`），再放 `TokenProfileCard` 和 `Timeline / Posts / Score / Lab / Accounts` tabs（`web/src/features/live/ui/TokenDetailDrawer.tsx:194-273`）。这让 official、community、narrative、market、decision 分散在不同位置；用户需要自己把资料拼成判断。

Search Intel 已经是独立 route page，会解析 URL state、调用 `useSearchInspectQuery`、订阅 market target，并渲染 topbar/sidebar/body（`web/src/features/search/ui/SearchIntelPage.tsx:40-71`）。但它的 sidebar 仍偏工程控制台：query、window、scope、resolver、candidates、sections 分散展示（`web/src/features/search/ui/SearchIntelPage.tsx:106-211`）；token result body 虽然已有 `token case`、metric strip、agent brief、timeline 等结构（`web/src/features/search/ui/SearchIntelPage.tsx:227-260`），但视觉语法没有和 Radar item、Selected Token、Signal Pulse 统一。

Watchlist 目前不是二级页面，而是 side rail 中的一组账号链接。`CockpitSideRail` 的 views 只有 Token、Stocks、Signal Labs（`web/src/features/cockpit/ui/CockpitSideRail.tsx:47-73`）；watchlist rows 点击后进入 `signalLabPath({ handle })`（`web/src/features/cockpit/ui/CockpitSideRail.tsx:111-130`）。其数据模型也只有 `handle`、`unreadCount`、`lastSeenAtMs`（`web/src/lib/watchlist.ts:3-7`），由 live events 推最近时间并排序（`web/src/lib/watchlist.ts:15-43`）。这无法承载“账号档案页、该账号推动了哪些 token、哪些叙事、哪些证据链”的产品语义。

Signal Pulse 当前像内部 inspector。Workbench 有 status grid、filter bar、list（`web/src/features/signal-lab/ui/SignalLabWorkbench.tsx:97-208`），但 selected item detail 直接展示 `Agent Recommendation`、`Fact Card`、`Eligibility Gates`、`Data Health`、`Alpha Families`、`Source Events`、raw `factor_snapshot/gate/playbooks` JSON 和 versions（`web/src/features/signal-lab/ui/SignalLabInspector.tsx:35-247`）。这些信息有价值，但首屏更像调试面板，不像交易/研究工作台的可读 memo。

当前全局 design token 只有 dark panels、accent、green、red、blue 等基础变量（`web/src/styles/tokens.css:1-23`）。Obsidian Desk v2 静态稿已经提出新的产品语言：`--void`、`--obsidian`、`--slab`、`--bone`、`--ash`、`--opportunity`、`--health`、`--info`、`--risk`、`--violet` 等语义色（`docs/prototypes/obsidian-desk-v2-static.html:8-37`），并把 Token Radar、Search Intel、Watchlist、Signal Pulse 统一成同一种 case-file 交互语法（`docs/prototypes/obsidian-desk-v2-static.html:1225-1261`）。静态稿中的 Radar 行已经把 item 改成案卷：Identity、Community、Narrative、Decision（`docs/prototypes/obsidian-desk-v2-static.html:1335-1385`）；Watchlist 和 Signal Pulse 也分别展示 account file 与 agent memo/fact ledger 方向（`docs/prototypes/obsidian-desk-v2-static.html:1461-1485`, `docs/prototypes/obsidian-desk-v2-static.html:1495-1517`）。

后端架构已经明确官方资料归属：resolved DEX asset profile facts 通过 `TokenProfileReadModel` 进入 `/api/token-radar`、`/api/search/inspect` 和 frontend，official links/descriptions 必须不依赖 narrative agent 可见（`docs/ARCHITECTURE.md:114-134`）。因此这次 UI hard cut 应优先重组现有 read model，不引入新后端事实来源。

## Problem

用户现在必须在多个页面语言之间来回翻译：Token Radar 用评分因子表格，Selected Token 用 tab drawer，Watchlist 被藏在 side rail 并跳去 Signal Lab，Signal Pulse 像 raw inspector，Search Intel 又是另一套 case inspect。产品特性本身是“从社交事件提取 token/叙事/账号证据并形成判断”，但 UI 没有把 official、community、narrative、market、decision 放进同一个 item 和同一个 selected case，导致用户无法快速回答“这个 token 是谁、谁在推、叙事是什么、市场确认了吗、下一步做什么”。

## First Principles

1. **Case-file grammar is the product grammar.** 所有一级/二级页面都使用同一套读法：Identity / Official / Community / Narrative / Market / Decision / Evidence / Next action。当前 `docs/FRONTEND.md` 已要求 Token Radar 是 scan surface，主行点击进入 Search Intel，而不是把所有 audit 逻辑塞在 radar 行（`docs/FRONTEND.md:32-33`）。
2. **Facts before narrative.** Official profile facts 来自 persisted profile read model，不由 narrative agent 临场生成；这与 `TokenProfileReadModel` 的架构边界一致（`docs/ARCHITECTURE.md:114-134`）。UI 可以展示 agent brief，但必须标记为 agent memo，而不是官方事实。
3. **Hard cut, no compatibility UI.** 本次实现不保留旧 Radar table、旧 selected-token tab-first drawer、旧 Watchlist-to-Signal-Lab account detail、旧 JSON-first Signal Pulse inspector 的并行渲染路径；不加 feature flag；不留下 “new/legacy” 双组件。保留的只能是必要 API enum、query 参数和稳定 public contract。
4. **Frontend boundaries stay clean.** 新 UI 的业务归纳放在 `features/<name>/model/`，不是 JSX 内临时拼字符串；shared primitives 只负责 presentation；route/state/API 仍遵循 `docs/FRONTEND.md` 的 layer map（`docs/FRONTEND.md:5-25`）。

## Goals

- **G1 Design language unified.** `web/src/styles/tokens.css` SHALL expose Obsidian Desk semantic tokens and the visible pages `/`, `/search`, `/watchlist`, `/signal-lab`, `/signal-lab/pulse/:candidateId`, `/token/:targetType/:targetId` SHALL use the same palette, spacing, typography, borders, badges, and case-file primitives.
- **G2 Token Radar item readable in one pass.** Radar rows SHALL display Identity, Community, Narrative, Decision, and venue/Search actions in a stable row layout; user-facing headers SHALL NOT be Heat / Quality / Propagation / Timing.
- **G3 Selected Token becomes Selected Case.** The detail panel SHALL show official profile, community proof, narrative thesis, market confirmation, decision rationale, and Search Intel action above secondary evidence sections.
- **G4 Watchlist becomes a first-class page.** The side rail SHALL include Watchlist as its own view, route to `/watchlist`, and expose an account detail page for selected handle with recent evidence, token mentions, narrative clusters, unread state, and Search Intel links.
- **G5 Search Intel aligns with case-file grammar.** Search result pages SHALL keep existing resolver/query behavior but present token/topic/ambiguous results as a dossier with shared section primitives and visible source/agent boundaries.
- **G6 Signal Pulse becomes memo-first.** Signal Pulse queue SHALL show candidate stage, gate, agent verdict, key facts, and next action; selected pulse SHALL prioritize agent memo + fact ledger + source events, with raw JSON hidden behind explicit debug disclosure or removed from primary route.
- **G7 No compatibility code remains.** Old user-facing strings/classes/components for the previous UI SHALL be removed or renamed; `legacy-ui.ts` SHALL be renamed or decomposed so type exports no longer advertise a legacy UI surface.
- **G8 Verification is reviewable.** Unit/integration tests, e2e golden paths, browser screenshots, and `make check-all` SHALL prove the hard cut before completion.

## Non-Goals

- **N1 No backend schema or scoring changes.** This work does not add DB tables, migrations, new workers, new APIs, or new agent prompts.
- **N2 No new market-data provider.** Market confirmation uses existing `TokenFlowItem`, Search Inspect, Signal Pulse, and live market subscription data.
- **N3 No new narrative generation.** UI may summarize deterministic existing fields and existing agent recommendation fields; it must not invent a narrative beyond available facts.
- **N4 No Stocks Radar product redesign beyond shell language.** `/stocks` should inherit palette/shell primitives where cheap, but this spec does not redesign stock-specific workflows.
- **N5 No mobile-native redesign.** Responsive behavior must remain usable and non-overlapping, but this is not a separate native mobile product pass.

## Target Architecture

The frontend will keep the existing feature-layer architecture and add a case-file design layer:

- `shared/ui/case-file` owns reusable presentational primitives: case shell, row, metric, section, field, badge, evidence list, empty/loading affordances. It has no data fetching and no token-specific business logic.
- `features/live/model/tokenCase.ts` converts `TokenFlowItem` into `TokenCaseView`. It owns labels for identity, official profile availability, community proof, narrative phase, market confirmation, decision, and next action. `TokenRadarRow`, `TokenRadarTable`, and `TokenDetailDrawer` render this view model instead of recomputing copy in JSX.
- `features/search/model/searchCase.ts` converts `SearchInspectData` result branches into shared `SearchCaseView` sections while preserving existing route state and query hook.
- `features/watchlist/` becomes a real feature with model/state/ui. It derives account cases from configured handles, live events, unread counts, and available token/social entities. It owns `/watchlist` UI and selected handle URL state.
- `features/signal-lab/model/pulseCase.ts` converts `SignalPulseItem` into `PulseCaseView`. Workbench and inspector render a memo-first queue/detail instead of raw-factor-first cards.
- `app/CockpitApp.tsx` stays the composition root for now but delegates Watchlist route UI to `features/watchlist`; future route decomposition can move route objects into `web/src/routes/*` without changing product behavior.

No new backend data owner is introduced. The UI hard cut is a presentation/modeling reframe of existing HTTP/WebSocket read models.

## Conceptual Data Flow

```text
existing HTTP + WebSocket read models
  -> feature api/socket hooks
  -> feature model adapters
  -> shared case-file primitives
  -> route/page UI
```

Changed arrows:

- `TokenFlowItem -> TokenCaseView` is new and replaces row-local label construction in `TokenRadarRow`.
- `LivePayload[] + notification summary + handles -> WatchlistAccountCase[]` expands the current `WatchlistRow` model.
- `SignalPulseItem -> PulseCaseView` is new and replaces JSON-first `SignalLabInspector` composition.
- `SearchInspectData -> SearchCaseView` is new but does not alter `/api/search/inspect`.

No new arrow appears between frontend and backend. If implementation discovers missing fields for official/community/narrative sections, the UI SHALL show explicit unavailable states rather than adding hidden backend calls.

## Core Models

`CaseTone`

- Values: `opportunity`, `health`, `info`, `risk`, `agent`, `neutral`.
- Invariant: tones describe semantic meaning, not raw color names.

`CaseFact`

- Fields: `label`, `value`, optional `detail`, optional `tone`, optional `source`.
- Invariant: any agent-derived source must be labelled `agent`; official/profile facts must not be merged with agent text.

`TokenCaseView`

- Fields: `key`, `identity`, `official`, `community`, `narrative`, `market`, `decision`, `actions`, `evidence`.
- Invariant: Radar row and Selected Case consume the same model; detail may show more fields, but cannot use a different vocabulary.

`WatchlistAccountCase`

- Fields: `handle`, `unreadCount`, `lastSeenAtMs`, `recentEvents`, `tokenMentions`, `narrativeClusters`, `riskNotes`, `searchLinks`.
- Invariant: account case is derived from configured watchlist + live/read-model evidence; it is not a user-managed portfolio list.

`PulseCaseView`

- Fields: `candidateId`, `subject`, `stage`, `gate`, `agentMemo`, `factLedger`, `sourceEvents`, `actions`, `debugFacts`.
- Invariant: `debugFacts` are not part of the primary visual hierarchy.

`SearchCaseView`

- Fields: `query`, `resolver`, `resultKind`, `selectedTarget`, `official`, `community`, `narrative`, `market`, `timeline`, `evidence`.
- Invariant: ambiguous/topic/token branches share shell and section primitives but keep branch-specific facts.

## Interface Contracts

Public HTTP/WebSocket/CLI contracts are unchanged.

Frontend route contract changes:

- `/watchlist` renders all configured accounts with Obsidian Desk case-list styling.
- `/watchlist?handle=<handle>` selects an account file. The handle is normalized without `@`, lowercased, and must preserve other live filters where meaningful.
- Existing `/signal-lab?handle=<handle>` remains a Signal Pulse filter, not the canonical account detail view.
- Topbar search remains `/search?q=<query>&window=<window>&scope=<scope>`.
- Token Radar row primary click continues to open Search Intel, consistent with `docs/FRONTEND.md:32-33`; selection still controls the side detail panel where needed.

Internal contracts:

- `TokenCaseView`, `WatchlistAccountCase`, `PulseCaseView`, `SearchCaseView` are frontend view models only.
- Shared case-file primitives accept already formatted labels/values and do not import feature models.

## Acceptance Criteria

- **AC1.** WHEN `/` renders Token Radar THEN each row SHALL show Identity, Community, Narrative, Decision, and actions, and SHALL NOT show user-facing headers `Heat`, `Quality`, `Propagation`, or `Timing`.
- **AC2.** WHEN a token row is selected THEN the detail panel SHALL be labelled as a selected case and show official profile, community proof, narrative thesis, market confirmation, decision rationale, and Search Intel as the primary action.
- **AC3.** WHEN the selected token has profile links/description from `TokenProfileReadModel` THEN those official facts SHALL be visible without depending on Signal Pulse or agent recommendation data.
- **AC4.** WHEN `/search?q=<token>` renders a token result THEN Search Intel SHALL use the same case-file section primitives as Radar detail and SHALL keep resolver confidence/candidates available without dominating the page.
- **AC5.** WHEN the user clicks Watchlist in the side rail THEN the app SHALL navigate to `/watchlist`, not `/signal-lab`, and show account cases derived from watchlist handles.
- **AC6.** WHEN `/watchlist?handle=<handle>` renders THEN the selected account file SHALL show recent evidence, token mentions, narrative clusters or empty states, unread count, and links into Search Intel.
- **AC7.** WHEN `/signal-lab` renders THEN Signal Pulse SHALL read like a candidate queue with stage/gate/agent verdict/facts/next action, not a raw status/filter list only.
- **AC8.** WHEN a Signal Pulse item is selected or `/signal-lab/pulse/:candidateId` renders THEN the primary panel SHALL show agent memo, fact ledger, source events, venue/Search actions, and only secondary/debug access to raw JSON.
- **AC9.** WHEN the frontend CSS is scanned THEN old compatibility selectors and old user-facing copy from the previous hard-cut surface SHALL be absent or intentionally renamed.
- **AC10.** WHEN frontend verification runs THEN `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`, relevant Playwright golden paths, browser visual checks, and final `make check-all` SHALL pass or record explicit baseline failures.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| UI invents official/narrative facts not present in read models. | High | Model adapters must label source and render unavailable states; official fields come from profile only, agent fields from `agent_recommendation` only. |
| Hard cut touches many CSS modules and causes visual regressions. | High | Build shared primitives first, then migrate feature-by-feature; use screenshots for `/`, `/search`, `/watchlist`, `/signal-lab`, `/signal-lab/pulse/:candidateId`. |
| Watchlist page overpromises account analytics without backend support. | Medium | Initial account cases derive only from current handles, live events, unread counts, entities, and token mentions; missing clusters show clear empty states. |
| Removing compatibility UI breaks existing tests that assert old labels. | Medium | Update tests to product vocabulary; keep API enum values internal where needed. |
| `legacy-ui.ts` rename becomes large mechanical churn. | Medium | Rename only the local re-export file and import path if generated schemas cannot replace it; do not mix type cleanup with business behavior. |
| Signal Pulse raw JSON removal hides useful debug info. | Low | Keep explicit debug disclosure or route-local development detail, but not primary UI. |

## Evolution Path

After this hard cut, a backend-backed Watchlist account summary can be added as a read model without changing the page grammar: it would hydrate the existing `WatchlistAccountCase` fields instead of replacing the UI. A future narrative agent can write candidate narrative summaries, but official facts should remain profile-owned and source-labelled. A later route decomposition can move `CockpitAppRoutes` into `web/src/routes/*` once the UI language is stable.

## Alternatives Considered

- **Keep metric table and add tooltips** — rejected because it preserves the current cognitive burden; users still need to translate scoring factors into product meaning.
- **Add a theme switcher with old/new UI behind a flag** — rejected because the user explicitly requested no compatibility code, and dual UI paths would double tests/CSS and slow convergence.
- **Build a new backend Watchlist aggregate first** — rejected for this pass because existing handles/live events/notifications can support a useful account file, while backend work would delay the UI language decision.
- **Make Signal Pulse the universal detail page** — rejected because account-level watchlist detail and agent candidate review are different jobs; routing Watchlist into Signal Lab is part of the current confusion.
- **Use generated OpenAPI types only and delete all local UI view types immediately** — rejected because `docs/FRONTEND.md` still identifies frontend-specific compatibility payloads (`docs/FRONTEND.md:21-22`), and some local view contracts are richer than generated schemas. The hard cut should rename/decompose local view contracts, not pretend the API already owns every UI shape.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Reuse existing HTTP/WebSocket data; render official/community/narrative/decision in one case grammar; remove old parallel UI; keep source labels visible. |
| Ask first | Add backend fields, agent prompts, DB migrations, or a true user-editable watchlist management workflow. |
| Never | Add feature flags for old vs new UI; keep old Radar table as fallback; make agent copy look like official fact; route account detail primarily through Signal Lab. |

## Progress Log

| Time | Milestone | Status | Validation |
|------|-----------|--------|------------|
| 2026-05-13 | Kickoff | In progress | Read `AGENTS.md`, `docs/WORKFLOW.md`, `docs/TESTING.md`, `docs/FRONTEND.md`, and this spec. Created isolated worktree `codex/obsidian-desk-ui-hard-cut`. Baseline validation pending. |
| 2026-05-13 | Baseline frontend validation | Complete | `npm --prefix web run lint` exit 0; `npm --prefix web run typecheck` exit 0; `npm --prefix web run test` exit 0 with 31 files / 151 tests passed; `npm --prefix web run build` exit 0. |

## Decision Log

| Time | Decision | Reason |
|------|----------|--------|
| 2026-05-13 | Use this spec as implementation source of truth. | User explicitly requested this spec as source of truth and instructed not to expand scope beyond it. |
| 2026-05-13 | Do not implement full route decomposition as a prerequisite. | This spec allows `CockpitApp` to remain composition root for now and treats future route decomposition as an evolution path; implementation will only change routing required by `/watchlist` and the case-file hard cut. |
