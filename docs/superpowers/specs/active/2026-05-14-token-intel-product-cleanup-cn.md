# Spec — Token Intel Product Cleanup

**Status**: In Progress  
**Date**: 2026-05-14  
**Branch**: `main`  
**Related**: `docs/superpowers/specs/active/2026-05-14-obsidian-desk-production-cleanup-cn.md`, `docs/FRONTEND.md`, `docs/ARCHITECTURE.md`

## 一句话

把 Obsidian Desk 从“雷达列表 + 搜索调试页”重构成交易员可用的 token intelligence 工作流：Radar 只展示有行动价值的 token case，Search Intel 默认进入已确定合约/target 的情报页，不再把 resolver candidate 当成主产品。

## 背景

上一刀已经删除右侧 selected sidecar 和旧 drawer 组件，并把 token item 变成独立页面。但产品层仍有两个根问题：

1. **Radar item 信息结构仍像迁移产物。** 现在的 row 把 Identity / Official / Community / Narrative / Market / Decision 横向摊开，还保留 `Attention / Proof / Reach / Entry` 这类内部评分维度排序。交易员看到的是很多“模型解释词”，不是能快速判断能否继续看的事实。
2. **Search Intel 仍像 resolver/debug 页面。** token 已经由确定合约地址或 target 打开时，页面仍展示 resolver confidence、candidate list、sections sidebar、metric strip 等调试语言。用户已经在看一个确定 token，此时 candidate 选项没有增量信息，反而降低信任。

## 第一性原则

每个 UI 字段必须回答一个交易问题，否则删掉。

| 交易问题 | UI 应给的信息 | 不应暴露的信息 |
|---|---|---|
| 这是什么？ | icon、symbol/name、chain、CA/target、venue | resolver candidate list |
| 能不能点？ | Website、X、GMGN、GeckoTerminal、venue action | “profile provider ready” 作为主字段 |
| 谁在推？ | posts、authors、watched、top author concentration | generic proof score |
| 为什么现在？ | phase、one-line narrative、lead evidence/stage | propagation score family name |
| 能不能交易？ | market cap/price、since-social change、market data health、risk flag | timing/entry component score |
| 下一步？ | open item、open Search Intel、open venue | tab navigation/debug sections |

## Goals

- **G1 Radar 顶部减法。** 删除大块 `Token Radar` 标题/解释文案，把 window/scope 放进同一行紧凑工具栏。用户可见排序只保留默认 `Desk pick` 语义；不再展示 `Attention / Proof / Reach / Entry`。
- **G2 Radar item 产品化。** 每行必须以 token profile 为入口，展示 icon、symbol/name、CA/chain、official links、social proof、narrative、market、decision/action。字段少，但每个字段都有交易增量。
- **G3 Search Intel 默认确定 target。** 从 Radar 打开 Search Intel 时使用确定的 target/CA，而不是 symbol guess；token_result 页面不展示 candidate 选项。只有 ambiguous_result 才展示 candidate compare。
- **G4 Search Intel 变成 token intelligence 页。** token_result 的首屏是 token case header + profile links + decision/market/social/narrative summary；timeline/evidence 是主内容，agent brief 是辅助，不再让 resolver/sidebar 主导页面。
- **G5 静态组件先行。** 先建立清晰的静态组件边界和 props，再接现有数据，避免继续在大页面里手写临时 JSX。
- **G6 清掉无价值旧词。** 用户可见层移除 `Attention`、`Proof`、`Reach`、`Entry`、`candidates`（token_result）、`resolver confidence`（token_result 主视觉）。

## Non-Goals

- 不改后端 resolver、score、timeline、posts API。
- 不删除内部 `RadarSortMode` 类型或评分 families；可以保留为内部排序/兼容层，但不作为用户可见产品控件。
- 不重做 Signal Pulse、Watchlist、Stocks。
- 不做大型图表库替换；现有 Search timeline/chart 可以保留，只调整其在页面中的优先级。

## Product Design

### Radar Header

现状：左边大标题 + 解释文案，右边 sort tabs，window/scope 在更上层。

目标：一条紧凑 scan bar。

字段：

- 左：`Token Radar` 小标题 + 当前结果计数，例如 `48 live cases`
- 中：window segmented control：`5m / 1h / 4h / 24h`
- 右：scope segmented control：`watched / all`

删除：

- 解释文案 `快速扫...`
- `Attention / Proof / Reach / Entry`
- 多余 `token radar toolbar` 层级

### Radar Item

每行分三段，而不是七列表格：

1. **Token identity**
   - icon/logo 或 fallback mark
   - `$SYMBOL` / official name
   - chain + short CA 或 CEX market id
   - official status only when it changes trust: `profile` / `links` / `unverified`

2. **Why now**
   - social: `posts · authors · watched`
   - narrative: phase + one-line reason
   - market: market cap/price + since-social delta

3. **Action**
   - decision pill + score
   - compact risk flag
   - venue button
   - Search Intel button

删除/降级：

- `Official` 独立列。官网/X 应作为 token identity 的 link strip，不是一个文本列。
- `Community` 独立列。保留为 social fact line。
- `Narrative` 独立列。保留为 why-now line。
- `Decision` 大数字卡。保留 score + pill，但不让它压过 identity。

### Search Intel Token Page

token_result 页面分三层：

1. **Token Intel Header**
   - icon、symbol/name、chain/CA
   - Website/X/GMGN/GeckoTerminal/venue actions
   - window/scope controls
   - decision + score/risk

2. **Decision Strip**
   - social proof：posts/authors/watched/top share
   - market：market cap/price/provider/data health
   - narrative：agent one-liner or deterministic phase
   - evidence：returned/total events and selected stage

3. **Evidence Workspace**
   - primary column: timeline + evidence stream
   - side column: trader brief + profile details + score/data health, but not resolver candidates

token_result 删除：

- `SearchIntelSidebar`
- candidate list
- resolver confidence panel
- metric strip with eight tiny cards

ambiguous_result 保留但降级为单独状态：

- 展示 `Ambiguous query`
- 展示 candidate compare
- 不自动伪装成 token intelligence

topic_result 保留为 topic research：

- 不显示 token profile/market actions
- 保留 topic timeline/evidence/agent brief

## Component Boundaries

### Shared token intelligence primitives

Create or reshape around:

- `web/src/shared/model/tokenCase.ts`
  - Continue as single source for token identity/community/narrative/market/decision facts.
  - Add link/profile helpers only if used by both Radar and Search.

- `web/src/shared/ui/TokenIdentityBlock.tsx`
  - Presentation-only.
  - Props: `label`, `subtitle`, `profile`, `tone`, `links`, `compact`.
  - Renders icon/logo, symbol/name, CA/venue subtitle, official links.

- `web/src/shared/ui/TokenDecisionStrip.tsx`
  - Presentation-only.
  - Props: `fields: ObsidianStringField[]`, `decision`, `score`, `risk`.
  - Used by Radar row and Search Intel header.

### Radar feature components

- `web/src/features/live/ui/TokenRadarScanBar.tsx`
  - Owns title/count/window/scope controls.
  - No sort tabs.

- `web/src/features/live/ui/TokenRadarRow.tsx`
  - Uses shared token primitives.
  - No separate Official/Community/Narrative table cells.

- `web/src/features/live/ui/TokenRadarTable.tsx`
  - Becomes a list shell, not a table grammar.
  - `sortMode` can remain in props for compatibility but is not rendered as tabs.

### Search feature components

- `web/src/features/search/ui/SearchTokenIntelPage.tsx`
  - token_result only.
  - Receives `SearchInspectData` and `SearchTokenResult`.
  - Uses shared token primitives and existing Search timeline/evidence components.

- `web/src/features/search/ui/SearchIntelControls.tsx`
  - window/scope controls for Search token page.
  - No resolver/candidate UI.

- `web/src/features/search/ui/SearchAmbiguousCase.tsx`
  - owns candidate compare for ambiguous_result only.

- `web/src/features/search/ui/SearchTopicCase.tsx`
  - owns topic_result only.

## Data Flow

### Radar to item

Clicking a Radar row opens `/token/:targetType/:targetId` when target is resolved. Unresolved symbol-only rows fall back to Search Intel.

### Radar to Search Intel

Clicking Search Intel from a resolved Radar row SHALL prefer a deterministic query:

1. DEX asset with address: `q=<address>`
2. CEX token with inst id/native market: `q=<inst_id>`
3. resolved target id when no address/inst id
4. symbol fallback only when no deterministic target exists

This avoids candidate ambiguity when the row already carries a resolved contract/target.

### Search token_result

Search API may still return resolver metadata, but UI treats `data.token_result.target` as source of truth. `data.resolver.target_candidates` is ignored in token_result rendering.

## Acceptance Criteria

- **AC1 Radar header**: at desktop width, Token Radar has one scan bar with window/scope controls; no large description block.
- **AC2 Radar sorting copy**: user-visible UI contains no `Attention`, `Proof`, `Reach`, or `Entry` sort buttons.
- **AC3 Radar row**: each token row renders token icon/logo fallback, symbol/name, chain/CA or venue subtitle, social fact, narrative fact, market fact, decision/score, venue action, and Search Intel action.
- **AC4 Search deterministic query**: resolved DEX token Search Intel action navigates with address/target-specific query, not just `$SYMBOL`.
- **AC5 Search token_result**: token_result renders no candidate list and no resolver confidence card.
- **AC6 Search ambiguous_result**: ambiguous_result still renders candidate compare and clearly says it is ambiguous.
- **AC7 Search token page**: token_result first viewport includes token profile links, decision, market, social proof, narrative, timeline/evidence entry points.
- **AC8 Component boundaries**: `SearchIntelPage.tsx` no longer owns token_result body JSX directly; it delegates to token/topic/ambiguous case components.
- **AC9 Visual QA**: `http://localhost:8765/` shows no right selected sidecar, Radar content uses full main width, and Search Intel token page is not a resolver/debug layout.
- **AC10 Verification**: lint, typecheck, full Vitest, build, Docker rebuild, and browser console check pass.

## Test Plan

- `web/src/features/live/ui/TokenRadarRow.test.tsx`
  - assert icon/profile/link affordances
  - assert no candidate text for resolved rows
  - assert Search action uses deterministic query

- `web/src/features/live/__tests__/CockpitApp.integration.test.tsx`
  - assert Radar has no old sort labels
  - assert Radar controls live in scan bar

- `web/src/features/search/ui/__tests__/SearchIntelPage.routing.test.tsx`
  - token_result: no candidate/sidebar/resolver confidence
  - token_result: renders token intel header + profile links + evidence
  - ambiguous_result: candidate compare remains

- `web/src/test/obsidianArchitectureCleanout.test.ts`
  - user-visible old sort labels absent from Radar table
  - token_result does not render `search-sidebar-candidates`

## Risks

| Risk | Mitigation |
|---|---|
| Removing sort tabs hides useful power-user control. | Keep internal `sort=opportunity` default and URL compatibility; revisit only if a real trader asks for alternate scan modes with clear labels. |
| Address-based Search query may expose long CA in topbar. | Header should show symbol/name; route query can remain technical. |
| Shared token primitives become too generic. | Keep only token intelligence primitives; no generic dashboard atoms. |
| Search page split touches many tests. | Do component tests first, then integration tests. |

## Implementation Notes

Use TDD where practical:

1. Add failing tests for removed old labels/candidates.
2. Add static shared token identity/decision primitives.
3. Rebuild Radar row/header around the primitives.
4. Split Search token_result into `SearchTokenIntelPage`.
5. Keep ambiguous/topic paths explicit.
6. Run full verification and browser QA.

