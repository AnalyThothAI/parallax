# 闭环 Harness Cockpit 具体页面设计

日期：2026-05-04

静态原型：`docs/prototypes/closed-loop-harness-cockpit.html`

## 页面定位

这不是一个新的 dashboard，也不是一个“叙事分析页”。它是当前 `intel.cockpit` 的 Harness 模式首屏。

页面要让交易员在 30 秒内回答：

```text
1. 高价值账号刚制造了什么 attention seed？
2. 这个 seed 有没有被 token/social flow 接住？
3. harness 是否冻结了 snapshot？
4. shadow decision 是什么，为什么不是 live decision？
5. outcome/credit 是否已经回写？
6. score bucket 是否证明这类信号有 edge？
```

核心设计取向：

```text
工业交易终端
高密度
证据优先
不解释成因果
不鼓励冲动下单
```

页面记忆点应该是右侧的纵向闭环 trace：

```text
Extracted -> Seed -> Snapshot -> Outcome -> Credit
```

用户一眼能看到：LLM 只抽取，Harness 才负责闭环。

## 首屏结构

### 1440px Desktop

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Topbar: brand | health | search | counters                         refresh │
├──────────────┬───────────────────────────────────────────────┬──────────────┤
│ SideRail     │ Center                                        │ RightDrawer  │
│ 184px        │ flexible                                      │ 360px        │
│              │                                               │              │
│ nav          │ Token Radar                                   │ selected     │
│ filters      │ 52% height                                    │ snapshot     │
│ harness mini │                                               │ trace        │
│              ├───────────────────────────────────────────────┤ ledger       │
│              │ Bottom Deck                                   │ outcome      │
│              │ Live Tape | Harness Panel | Evaluation Mini   │ credit       │
└──────────────┴───────────────────────────────────────────────┴──────────────┘
```

建议 CSS grid：

```css
.cockpit-grid {
  grid-template-columns: 184px minmax(660px, 1fr) 360px;
}

.center-column {
  grid-template-rows: minmax(420px, 1fr) 310px;
}

.bottom-deck {
  grid-template-columns: minmax(250px, 0.9fr) minmax(320px, 1.1fr) minmax(250px, 0.85fr);
}
```

### 1280px Desktop

右侧 drawer 保持 340px，左侧 rail 缩到 168px。底部第三列从 `Evaluation Mini` 变成 `Search/Score` tab。

### 1024px Narrow Desktop

不做移动端重排。交易工具优先保证桌面可用：

```text
SideRail 152px
RightDrawer 320px
Center min 540px
BottomDeck 仍然三列，但 Live Tape 行数减少
```

如果宽度不足，优先牺牲：

```text
topbar counters detail
live tape body 第二行
evaluation mini
```

不能牺牲：

```text
Token Radar
HarnessPanel
Right trace
```

## Topbar

### 内容

```text
intel.cockpit
public_stream · shadow_only
search: / symbol, CA, handle, snapshot
MATCHED 6
SEEDS 12
SNAP 42
SETTLED 73%
schema 96%
refresh
```

### 设计

- `intel.cockpit` 继续保留当前品牌；
- 新增 `shadow_only` 状态，避免用户误以为有实盘；
- `enrich` counter 不再作为主状态，改成 `schema` 和 `SETTLED`；
- counter 只放 4 个，避免 topbar 变监控面板。

### 图标

React 实现时使用 lucide：

```text
Search
RefreshCw
Activity
Radio
Gauge
ShieldCheck
```

## SideRail

### 导航

```text
1 Live
2 Tokens
3 Harness
4 Outcomes
5 Ops
```

`Harness` 默认 active。`Narratives` 不再出现。

### 过滤器

```text
window: 5m / 1h / 24h
horizon: 6h / 24h
scope: watched / all stream
handles:
  cz_binance
  elonmusk
  heyibinance
```

### Mini Health

SideRail 底部放一个紧凑状态块：

```text
schema 96%
pending 18
snapshots 42
coverage 73%
```

这不是详细监控，只是告诉用户当前页面可信度。

## Center: Token Radar

Token Radar 仍然是主工作区，不被 Harness 抢走。

### 列设计

```text
Token
Heat
Quality
Propagation
Market
Timing
Harness
Decision
```

新增 `Harness` 列：

```text
seed 3
snap 1
credit +.21
```

如果 token 只有 social heat，没有 harness link：

```text
seed -
snap -
```

### Row 示例

```text
$BNB
heat 84 · +18
quality 71 · 5 acct
prop expansion · 7 author
market +3.8% fresh
timing social leads
harness seed 2 · snap 1 · pending
decision watch
```

点击 row 仍然进入右侧 token drawer，默认 tab 是 `Timeline`。如果该 token 有 harness link，drawer header 右上角显示：

```text
harness linked 3
```

## Bottom Deck

Bottom deck 是具体页面的关键，因为它把旧叙事面板替换为闭环入口。

### Left: Live Signal Tape

标题：

```text
Live Tape
```

Row 类型：

```text
EVENT
TOKEN
SEED
SNAP
```

Row 示例：

```text
SEED @cz_binance · meme_phrase_seed
build on BNB · conf .86 · 2m
```

Live Tape 不解释完整原因，只做脉冲入口。

### Middle: Harness Panel

标题：

```text
Harness
social-event-v1 · shadow loop
```

顶部 health strip：

```text
schema 96% | snap 42 | pending 18 | settled 73%
```

Segmented control：

```text
Events | Seeds | Snapshots
```

#### Events tab

Row：

```text
@elonmusk · product_or_ai_update · 2m
Grok product progress
[Grok] [xAI]  impact .72 novelty .68 conf .86
```

#### Seeds tab

Row：

```text
@heyibinance · exchange_or_listing_hint · linked
Binance Alpha
links BNB, CAKE · unresolved_symbol
```

#### Snapshots tab

Row：

```text
BNB · 6h · score .42
shadow LONG_SMALL · outcome pending
cz_meme_seed + heyi_exchange_hint
```

### Right: Evaluation Mini

MVP 右下不是完整 report，只放判断系统是否值得继续看的小面板。

标题：

```text
Score Buckets · 6h
```

表格：

```text
bucket      n    avg y    hit
<=-.8      12   -.31     33%
-.8~-.4    31   -.12     42%
-.4~.4     90   +.01     51%
.4~.8      28   +.14     61%
>=.8       10   +.29     70%
```

不引入图表库，用 CSS bar 表示 `avg y`。

## Right Drawer

右侧 drawer 是具体页面的第二个核心。

### 当选中 token

Header：

```text
selected token
$BNB
bsc · 0x... · resolved_ca
opportunity 79
harness linked 3
```

Tabs：

```text
Timeline | Posts | Score | Harness | Accounts
```

Harness tab 顺序：

```text
Linked Seeds
Active Snapshots
Latest Outcome
Credit Rows
```

### 当选中 social event / seed / snapshot

Header：

```text
selected harness object
@cz_binance · meme_phrase_seed
social-event-v1 · conf .86
```

Tabs：

```text
Trace | Snapshot | Outcome | Credit
```

### Trace 具体设计

纵向 timeline：

```text
1 Extracted
  @cz_binance · meme_phrase_seed
  anchor: "build on BNB"
  impact .72 · novelty .68 · conf .86

2 Seed
  linked · token uptake 2
  BNB, CAKE

3 Snapshot
  BNB · 6h · score .42
  shadow LONG_SMALL · policy NO_TRADE

4 Outcome
  pending · horizon not reached

5 Credit
  credit not assigned
```

注意文案：

```text
Predictive credit, not causal proof.
```

不要出现：

```text
caused
why price moved
driver proof
```

## 视觉系统

### 设计风格

```text
industrial command desk
dark evidence grid
amber attention
cyan info
green/red outcome
compact ledger
```

### 颜色

```text
bg:        #070909
panel:     #0d1111
panel-2:   #101515
line:      #252b2b
text:      #d9dfdc
ink:       #f5f1e8
muted:     #777f7b
amber:     #f2a51f
cyan:      #63c7dd
green:     #55d887
red:       #ff5f66
```

不要引入紫色渐变、蓝紫渐变、奶油色大面积背景、装饰性光球。

### 字体

当前应用使用 `Inter + JetBrains Mono`。为了页面更有交易终端感，建议生产实现调整为：

```text
body: IBM Plex Sans Condensed / PingFang SC / system-ui
numbers: JetBrains Mono
brand/counters: JetBrains Mono
```

如果不想动全局字体，至少 Harness 区域用 `JetBrains Mono` 强化证据感。

### 尺寸

```text
topbar height: 46px
side rail width: 184px
right drawer width: 360px
panel radius: 5px
row radius: 4px
compact row height: 56-76px
chip height: 20px
```

卡片圆角不超过 8px。不要做卡片套卡片。

### 动效

只做非常克制的动效：

```text
new live row: 160ms border flash
selected row: 120ms background transition
health warning: no pulsing, only color change
drawer tab switch: no slide animation
```

交易工具不需要戏剧性动效。

## 页面状态

### Empty

```text
当前窗口暂无 social event
当前窗口暂无 attention seed
当前窗口暂无 harness snapshot
```

### Loading

```text
loading harness state
```

### LLM off

```text
LLM extractor disabled
```

### Schema unhealthy

```text
social-event-v1 schema failure high
```

### Outcome pending

```text
outcome pending · horizon not reached
```

### Missing market

```text
missing market data · cannot settle
```

## 不做什么

这一页明确不做：

```text
下单按钮
仓位建议
live PnL hero number
叙事长文总结
大图表
Sankey / graph
多 agent trace
外部新闻源入口
旧 narrative label fallback
```

## 验收

页面设计合格标准：

```text
1. 首屏仍是交易 cockpit，不像 landing page
2. Narratives 不再是一级对象
3. HarnessPanel 能在一屏内显示 Events / Seeds / Snapshots
4. 右侧 Trace 能完整表达 Extracted -> Seed -> Snapshot -> Outcome -> Credit
5. 用户能区分 seed-only、snapshot-ready、outcome-pending、settled
6. 页面不暗示 LLM 做交易决策
7. 不出现旧 narrative_label fallback
8. 1440px 下三栏不重叠
9. 1024px 下文本不撑破 row 或按钮
10. Score bucket 被放在评估区，不抢实时工作区
```

