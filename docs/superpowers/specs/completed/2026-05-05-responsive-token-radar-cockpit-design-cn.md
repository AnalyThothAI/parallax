# Token Radar 响应式 Cockpit 重构设计

日期：2026-05-05

状态：设计已确认，待实施计划

范围：重构 `web/` 前端响应式布局。手机端首屏默认优先 `Token Radar`。不保留旧布局兼容代码。

## 一句话结论

当前页面的问题不是颜色、字号或单个断点，而是桌面三栏交易台被直接压缩到窄屏。屏幕变小时，布局没有重新定义任务优先级，导致 `Token Radar`、`Live Tape`、`Signal Lab`、右侧详情互相抢空间，最终信息丢失。

重构目标是建立一个生产级响应式 cockpit：

```text
desktop:  left rail + Token Radar center + detail drawer
tablet:   compact controls + Token Radar first + detail below
mobile:   single-task flow, Token Radar first, Tape/Lab/Detail through task nav
```

手机端不是缩小版桌面，而是以交易员最先需要扫描的对象为首屏：`Token Radar`。

## 当前问题

### 结构问题

当前布局核心仍是固定三栏：

```text
.cockpit-grid {
  grid-template-columns: 184px minmax(0, 1fr) minmax(356px, 388px);
}
```

这在桌面端成立，但在平板和手机端会出现三个问题：

- 左 rail 在窄屏仍占据大量垂直内容，主信息被推后；
- 右 drawer 在窄屏堆叠后太长，选中 token 的详情会吞掉主扫描流；
- 中心列内部仍按桌面信息密度组织，无法保证首屏可用。

### Token Radar 问题

`TokenRadarTable` 在 CSS 中保留桌面表格心智：

```text
radar row min-width: 920px
columns: Token / Heat / Quality / Propagation / Market / Timing / Decision / GMGN
```

窄屏上继续使用横向表格，会让用户只能看到部分列，或者被迫横向滚动。对交易 cockpit 来说，这相当于丢失信号，因为用户无法同时看到 token、score、decision 和 timing。

### CSS 问题

`web/src/styles.css` 已经出现重复定义和后置覆盖：

- `@media (max-width: 1180px)` 出现多次；
- `@media (max-width: 760px)` 出现多次；
- `.cockpit-grid`、`.detail-drawer`、`.radar-row` 在文件后半段再次覆盖；
- 断点是补丁式堆叠，不是明确布局系统。

这次重构需要删除旧响应式补丁，建立单一布局规则。不要增加兼容层。

## 产品原则

### 1. Token Radar 是手机首屏

手机端默认显示：

```text
topbar compact
global search
status/counters strip
Token Radar list
bottom task nav
```

首屏必须能看到前几条 token 信号，而不是先看到 watchlist、window 控制、空白详情或 Signal Lab。

### 2. 不丢信息，只改变承载方式

桌面表格的列在手机端不能被删除，应压缩成扫描行：

```text
row line 1: token identity | opportunity score | decision
row line 2: heat | quality | propagation | timing
row line 3: market | source/freshness | GMGN action
```

低优先级文本可以截断，但核心判断信息必须同屏可见。

核心判断信息：

- token label / chain / short address；
- opportunity score；
- decision；
- heat score and mention delta；
- quality label；
- propagation authors；
- timing status；
- market cap / price change；
- GMGN action；
- selected state。

### 3. 控制区不抢主区

手机端不展示常驻 SideRail。`views`、`window`、`scope`、`watchlist` 改成紧凑控制：

- window/scope 放在 Token Radar 上方的 control strip；
- views 由底部 task nav 承载；
- watched handles 作为可展开 filter sheet 或 compact input，不常驻占屏；
- decision counts 和 watchlist 后置到 Tape/Lab 或过滤区域，不在首屏挤压 radar。

### 4. Detail 是任务，不是常驻列

桌面端右侧 drawer 常驻是对的。手机端右侧 drawer 应成为 `Detail` task：

```text
Radar -> select token -> switch/show Detail task
```

选中 token 后，底部 task nav 的 `Detail` 出现 active/available 状态。用户可以返回 Radar，不会被详情页困住。

### 5. Signal Lab 不消失

`Signal Lab Pulse` 在手机端不与 Token Radar 抢首屏。它是同级任务：

```text
Radar | Tape | Lab | Detail
```

`Open Lab` 在手机端切换到 Lab task；桌面端继续切换到 Signal Lab workbench。

### 6. 不做兼容性代码

本次重构不做以下事情：

- 不保留旧 `@media` 补丁作为 fallback；
- 不为旧三栏手机布局写兼容分支；
- 不用 JS 监听 window width 再手动同步布局；
- 不复制两套业务组件；
- 不引入新的 UI 框架；
- 不为了兼容旧 CSS 命名继续追加覆盖。

实现完成后，旧响应式规则应被删除或改写，而不是继续叠加。

## 响应式断点

使用三个明确断点。

### Desktop：`>= 1280px`

目标：高密度交易台。

```text
Topbar
CockpitGrid:
  SideRail        184px
  CenterColumn    minmax(0, 1fr)
  DetailDrawer    356-388px
```

布局要求：

- `SideRail` sticky；
- `DetailDrawer` sticky；
- `TokenRadarTable` 使用桌面 grid table；
- `BottomDeck` 显示 Live Tape + Signal Lab Pulse；
- Signal Lab view 使用完整 workbench + inspector。

### Tablet：`768px - 1279px`

目标：保留扫描连续性，详情下沉。

```text
Topbar wraps into two rows
ControlRail becomes horizontal control panel
CenterColumn first
DetailDrawer below CenterColumn
```

布局要求：

- 不显示常驻左 rail 列；
- view/window/scope/watchlist 合并为 `responsive-control-panel`；
- Token Radar 仍是页面第一主区；
- Token Radar 可以继续使用 table grid，但列间距收紧，允许内部横向滚动；
- Detail drawer 作为中心内容下方的 section，而不是右侧列；
- BottomDeck 保持两块堆叠或双列，不能压缩主 radar 高度到不可读。

### Mobile：`< 768px`

目标：单任务工作流，Token Radar 首屏。

```text
Topbar compact
Search
Counters strip
TaskSurface:
  Radar
  Tape
  Lab
  Detail
BottomTaskNav
```

布局要求：

- `body` 和 root 不出现页面级横向滚动；
- `TokenRadarTable` 切换为 card/list 表达；
- `.radar-head` 在 mobile 隐藏；
- `.radar-row` 不再依赖 `min-width`；
- `.radar-row-select` 变为 1 列卡片布局；
- metrics 使用 2x2 或自适应 grid；
- GMGN action 独立成右上或底部小按钮；
- `SideRail` 不渲染为长块首屏内容；
- `DetailDrawer` 只在 Detail task 中展示；
- Tape/Lab task 各自滚动，不挤占 Radar 首屏。

## 信息架构

### Desktop IA

```text
topbar:
  brand | status | search | counters | refresh

side rail:
  views
  window
  scope
  handles
  decisions
  watchlist

center:
  radar controls
  Token Radar
  bottom deck: Live Tape + Signal Lab Pulse

right:
  selected detail
```

### Mobile IA

```text
topbar compact:
  brand + connection
  refresh
  search
  counters strip

radar task:
  window/scope controls
  sort control
  Token Radar mobile list

tape task:
  Live Signal Tape

lab task:
  Signal Lab Pulse or Workbench summary

detail task:
  selected token / evidence / signal chain detail

bottom task nav:
  Radar
  Tape
  Lab
  Detail
```

`Radar` 是默认 task。

## Component Design

### App Shell

`web/src/App.tsx` 需要把布局从“三栏永远存在”改成响应式 shell。

新增概念：

```ts
type MobileTask = "radar" | "tape" | "lab" | "detail";
```

状态原则：

- `activeView` 继续表达产品视图：`live` / `signal_lab`；
- `mobileTask` 只表达小屏当前任务；
- 选择 token、event、signal chain 后，桌面保持右 drawer 更新；
- 手机端选择对象后，切到 `detail` task；
- 从 `detail` 返回时，保持 selection，不清空。

不使用 JS viewport detection。通过 CSS 控制哪些区域在不同断点显示。`mobileTask` 是用户任务状态，不是断点兼容状态。

### TokenRadarTable

保持单一组件，输出同一组 row DOM，通过 CSS 在不同断点改变表达。

Desktop:

```text
header grid
row grid
```

Mobile:

```text
header hidden
row card
metric grid
action strip
```

不要拆成 `DesktopTokenRadarTable` 和 `MobileTokenRadarCards` 两套业务组件，避免排序、selected、loading、error 分叉。

### TokenRadarRow

当前 row 已经有比较好的语义分组：

```text
token-cell
metric heat
metric quality
phase propagation
metric market
phase timing
decision-cell
gmgn-cell
```

需要调整为更适合响应式的 DOM：

- 给每个 metric 增加稳定 class 或 `data-metric`；
- mobile 下 `.radar-row-select` 变成卡片主体；
- `.gmgn-cell` 在 mobile 放到卡片 action 区；
- long text 使用 `overflow-wrap: anywhere` 或稳定截断；
- 行高从 fixed/min table 思维改成 content-based，但有最小触控高度。

### SideRail / Control Panel

当前 `side-rail` 在 mobile 不应该作为首屏长列表出现。

建议抽出：

```text
CockpitControls
  ViewButtons
  WindowControl
  ScopeControl
  HandleFilter
  DecisionCounts
  Watchlist
```

桌面端由 `SideRail` 承载这些控制。平板端和手机端用 compact control strip 或 filter sheet 承载同一控制组件。

第一版可以先不做 modal sheet，使用 mobile radar 顶部的 compact filter strip：

```text
5m | 1h | 24h
watched | all
sort
handles input collapsed/inline
```

### Detail Surfaces

桌面：

```text
right column detail drawer
```

平板：

```text
detail section below main content
```

手机：

```text
Detail task
```

`TokenDetailDrawer`、`EvidenceDetailDrawer`、`SignalLabInspector` 不需要复制。外层 shell 控制其所在区域即可。

### MobileTaskNav

新增小组件：

```text
Radar
Tape
Lab
Detail
```

要求：

- fixed bottom；
- 高度稳定；
- 使用 lucide icons；
- `Detail` 在没有 selection 时 disabled 或显示空态；
- 点击 `Radar` 回到 Token Radar；
- 不遮挡内容，主内容底部预留 safe area padding。

## Visual System

保留当前工业交易终端视觉语言：

- dark cockpit；
- amber accent；
- mono-heavy data typography；
- sharp 4-7px radius；
- dense borders；
- restrained state color。

但需要修正两个问题：

- 不让页面继续读成单色暗块：状态色保留 green/blue/red，用于 health、watch、risk；
- 手机端卡片不能过度装饰，优先扫描效率。

禁止：

- hero；
- marketing section；
- 大卡片堆叠 dashboard；
- 渐变装饰背景；
- 解释性说明文字占据首屏。

## CSS Architecture

重构 `web/src/styles.css` 为清晰分区：

```text
1. imports / variables / base
2. shell: topbar, grid, responsive surfaces
3. controls: buttons, segmented, search, status
4. radar: table desktop + mobile card rules
5. tape / pulse / signal lab
6. drawers and detail panels
7. responsive breakpoints
```

断点只保留一组：

```css
@media (max-width: 1279px) { ...tablet... }
@media (max-width: 767px) { ...mobile... }
```

桌面规则作为默认。不要在文件前半段写一套断点、后半段再覆盖一套。

页面级规则：

```css
html,
body,
#root {
  min-width: 0;
  min-height: 100%;
}

body {
  overflow-x: clip;
}
```

组件级规则：

- 所有 grid child 设置 `min-width: 0`；
- 长 token/name/address 使用稳定截断；
- tweet/body 文本使用 line clamp；
- buttons 有稳定高度；
- bottom nav 预留 `env(safe-area-inset-bottom)`；
- 不使用 `font-size: vw`。

## Interaction Rules

### Search

保持现有行为：

- token-like query 优先选择当前唯一 radar token；
- Signal Lab view 下搜索进入 Signal Lab filter；
- 其他情况走 evidence search。

手机端 search 提交后：

- 如果命中 token，切回 `Radar` 并选中该 token；
- 如果是 evidence query，切到 `Detail` task 展示结果；
- 如果 Signal Lab active，切到 `Lab` task。

### Selection

Desktop:

```text
select row -> update right drawer
```

Mobile:

```text
select row -> update selected object -> switch to Detail task
```

用户返回 Radar 时 selected state 保留。

### Signal Lab

Desktop:

```text
Open Lab -> activeView signal_lab -> full workbench
```

Mobile:

```text
Open Lab -> mobileTask lab
```

如果用户在 Lab task 中点 chain：

```text
select signal chain -> mobileTask detail
```

## Accessibility

最低要求：

- bottom task nav 使用 `aria-label`；
- active task 使用 `aria-current="page"` 或明确 active state；
- detail tabs 保持现有 `role="tablist"` / `role="tab"` / `aria-selected`；
- icon-only buttons 必须有 `aria-label`；
- mobile token row button 触控高度不小于 44px；
- focus states 不被移除；
- 不依赖颜色表达唯一状态。

## Empty / Loading / Error States

手机端空态不能占满首屏。

Radar:

```text
loading: compact skeleton rows
empty: 当前窗口暂无可交易 token 热度
error: Token Radar 暂不可用 + message
```

Tape:

```text
loading replay
waiting replay/live event
ws disconnected
```

Lab:

```text
No Signal Chains in this window
```

Detail:

```text
Select a token from Token Radar
```

## Implementation Boundaries

Files expected to change:

```text
web/src/App.tsx
web/src/styles.css
web/src/components/TokenRadarTable.tsx
web/src/components/TokenRadarRow.tsx
```

Optional new file:

```text
web/src/components/MobileTaskNav.tsx
```

Files that should not need backend changes:

```text
src/parallax/api/*
src/parallax/retrieval/*
src/parallax/storage/*
```

This is a frontend layout and interaction refactor. API contracts stay unchanged.

## Verification Matrix

Run:

```bash
cd web
npm run build
npm test -- --run
```

Then browser QA:

```text
1440x900:
  desktop three-column cockpit visible
  Token Radar table readable
  right drawer sticky

1280x800:
  desktop compact still readable
  no clipped topbar controls

1024x768:
  no permanent side rail column
  Token Radar remains first
  detail appears below main content

768x1024:
  tablet layout has no page horizontal scroll
  controls do not crowd radar

430x932:
  Token Radar is first task
  first token rows visible above fold
  no page horizontal scroll
  bottom task nav visible
  selecting token opens Detail

390x844:
  search, counters, radar list fit
  metric text does not overlap
  GMGN action remains tappable
```

Automated checks:

- page-level `document.documentElement.scrollWidth <= window.innerWidth` for mobile widths；
- selected token detail renders after mobile row click；
- switching `Radar -> Tape -> Lab -> Detail` does not reset filters；
- no console errors during resize。

## Non-Goals

- 不重做 backend；
- 不重做 Signal Lab 数据模型；
- 不新增 auth/login；
- 不新增 trading/wallet 功能；
- 不做 SSR 或 Next.js；
- 不做旧布局兼容层；
- 不为了移动端复制一套业务数据组件。

## Acceptance Criteria

这次重构完成后必须满足：

- 手机端默认首屏是 `Token Radar`；
- 手机端没有页面级横向滚动；
- Token row 在手机端显示核心交易判断信息；
- Live Tape、Signal Lab、Detail 没有消失，而是通过 task nav 进入；
- 桌面端仍保持高密度三栏交易台；
- CSS 只有一套明确响应式断点；
- 删除重复旧断点覆盖；
- `npm run build` 通过；
- 浏览器截图验证 1440、1024、768、430、390 宽度。
