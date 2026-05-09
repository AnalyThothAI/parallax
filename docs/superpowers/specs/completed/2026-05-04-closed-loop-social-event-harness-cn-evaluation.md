# 闭环 Social Event Harness 中文总结与评估

日期：2026-05-04

## 一句话结论

这个方向是对的，但必须严格控制复杂度。

推荐做法不是一次性做一个完整“AI 交易系统”，而是先做一个最小闭环：

```text
高价值 watched account 动态
  -> LLM 严格抽取 social event
  -> harness 生成 attention seed / snapshot / shadow decision
  -> 到期结算 abnormal return
  -> 分配 credit
  -> 生成 score bucket 报告
```

只要这条链路能跑通，系统就从“看起来聪明的叙事流”变成“可验证、可复盘、可迭代的信号工厂”。如果一开始就同时引入外部新闻源、复杂聚类、实时交易、LangGraph、MLflow、复杂 baseline 和 UI 大改，就会偏离 KISS，并且很容易变成不可验证的大工程。

## 核心判断

### 是否遵循 KISS

当前设计在原则上遵循 KISS，因为它把 LLM 的职责压缩成一个单点：

```text
raw watched event -> structured social event extraction
```

其他所有事情交给确定性 harness：

```text
状态
评分
快照
结算
归因
权重
版本
评估
```

这比“LLM 判断利好利空、LLM 给交易建议、LLM 解释盈亏”简单得多，也更可靠。

但当前 spec 和 plan 里的完整形态偏大。它描述的是最终闭环，而不是第一刀 MVP。如果按全文一次性实现，会有复杂度风险。

### 是否引入不成熟方案

当前方案没有强制引入 LangGraph、MLflow、embedding 聚类、外部新闻源、自动交易、模型微调，所以没有把不成熟或重型方案塞进核心路径。

真正有风险的不是某个技术名词，而是这些工程动作：

```text
一次性做完整事件聚类
一次性做多资产 settlement baseline
一次性做权重学习和配置晋级
一次性改 UI
一次性重写全部 narrative/token-link 接口
```

这些如果同时上，会让闭环还没验证就先复杂化。

### 是否能够实现闭环

能，但必须承认闭环不是“写完表结构就闭上”。

真正闭环至少要满足六个条件：

```text
1. 每个信号只使用事前信息
2. 每个 snapshot 冻结且可回放
3. 每个 shadow decision 有明确 horizon
4. horizon 到期后能算 abnormal return
5. 多事件能分配 credit
6. credit 能进入慢速权重或评估报告
```

如果只做到 extraction、seed、score，而没有 settlement/outcome/credit，那仍然只是一个更好的信号生成器，不是闭环 harness。

## 现有问题的本质

现在的叙事流看不懂、没有交易价值，不是因为中文写得不好，也不是因为 UI 不够漂亮。

根因是对象错了。

当前对象更像：

```text
watched event -> narrative label -> narrative window
```

这会产生几个问题：

- label 太抽象，不能直接交易；
- label 没有明确 horizon；
- label 没有 frozen snapshot；
- label 后续是否带来 abnormal return 不可结算；
- label 之间同时出现时无法归因；
- 系统无法知道自己长期是否变好。

新闻/社交交易真正需要的是：

```text
watched event -> attention seed -> tradable expression -> snapshot -> outcome -> credit
```

这个变化才是根本性的。

## 第一性总结

### CZ、Musk、何一这类账号的价值是什么

他们的价值不是“预测价格”，而是制造注意力坐标。

一个高价值账号动态可能创造：

- 新短语；
- 新 meme 对象；
- 新产品关联；
- 新生态暗示；
- 新交易所/listing 预期；
- 新风险叙事；
- 对某个项目/人物/资产的放大。

这些东西本身不一定可交易。它们只有在后续出现确定性 token 证据时，才可能变成交易候选。

所以系统应该分清：

```text
attention seed: 值得观察
token uptake: 开始可交易化
market state: 是否已经 price in
snapshot outcome: 这个信号历史上是否有效
```

### LLM 应该解决的问题

LLM 只解决语言理解：

```text
这条动态到底在制造什么注意力？
原文中的 anchor term 是什么？
它属于哪类 social event？
有什么语义风险？
有没有显式 token candidate？
```

LLM 不解决：

```text
是否买入
买多少
是否 driver
是否归因成功
source weight 怎么更新
历史上是否有效
```

### Harness 应该解决的问题

Harness 解决生产纪律：

```text
状态机
版本
证据
打分
快照
风控
结算
归因
权重
评估
晋级
```

这就是 `Model + Harness` 里 harness 的价值。

## KISS 评估

### 符合 KISS 的地方

#### 1. 单一 LLM 节点

设计中只有一个 LLM 节点：

```text
watched account text -> social-event-v1 JSON
```

这很 KISS。它避免了多 agent 协调、反思、辩论、工具递归等不必要复杂度。

#### 2. 不接外部新闻源

V1 不接 RSS、新闻 API、SEC、交易所公告，这是正确的。

原因：

- 当前系统已经有 GMGN/X 证据库；
- watched account 是最接近 meme/crypto social edge 的源；
- 外部源会引入新的去重、时间戳、版权、延迟和语义分类问题；
- 没有必要在闭环未验证前扩大输入面。

#### 3. 不引入 LangGraph/MLflow 为必需依赖

当前 repo 已经有 SQLite evidence store、CLI、FastAPI、worker。

V1 用 SQLite 状态表实现 durable state 就够了。LangGraph 的 durable execution、MLflow 的 registry 都是后续可选项，不应该成为第一版依赖。

#### 4. LLM 输出强 schema

严格 JSON schema 是 KISS。

宽松 JSON + parser 容错看似灵活，实际上会把复杂度扩散到下游。

强 schema 的好处：

- 字段固定；
- enum 固定；
- 测试明确；
- 无效输出直接失败；
- 不需要兼容各种模型废话。

#### 5. 不保留旧 narrative 兼容层

这也符合 KISS。

双系统兼容会导致：

```text
旧 narrative label
新 social event
旧 API fallback
新 harness report
旧 UI display
新 snapshot outcome
```

同时存在，最终谁都说不清哪一个是产品真相。

破坏式替换短期痛，但长期简单。

### 不够 KISS 的风险点

#### 1. 一次性实现全部表和循环

完整闭环包括：

```text
extractions
clusters
snapshots
decisions
outcomes
credits
weights
score buckets
config evaluation
```

这些都合理，但不应该一刀全做成生产级。

建议拆成三层：

```text
MVP 必做:
  extraction, snapshot, shadow decision, outcome, credit report

第二阶段:
  weights, score bucket, config candidate

第三阶段:
  paper/canary/live promotion, UI full integration
```

#### 2. event_clusters 可能过早复杂化

新闻交易里 cluster 很重要，但当前 source 是 watched social events，不是全量新闻 API。

V1 可以先：

```text
one extraction = one cluster
```

等有数据后再做：

```text
same asset + event_type + anchor_terms + time window 合并
```

不要一开始做 embedding clustering。

#### 3. expected_return baseline 可能过早复杂化

异常收益必须做，但 baseline 可以先简单。

不建议 V1 直接做 rolling beta、多因子、宏观资产。

V1 可以先用：

```text
BTC/ETH benchmark + asset momentum
```

并明确写入：

```text
baseline_version = simple_crypto_baseline_v1
```

后续再替换。

#### 4. weight update 不应过早影响实时信号

权重更新是闭环的一部分，但早期样本少。

建议：

```text
先生成 weight report
不自动改变 live scoring
样本数达到阈值后再启用 candidate config
```

否则会变成小样本自激反馈。

#### 5. UI 不应和 backend 闭环同步大改

UI 最容易把系统带偏。

第一阶段应该以 CLI/API report 为主：

```text
social-events
harness-snapshots
harness-outcomes
harness-credits
score-buckets
```

当这些报告能证明信号有用，再改 cockpit。

## 是否引入不成熟方案

### 没有强行引入的不成熟方案

当前设计没有把这些放进核心路径，这是正确的：

- 多 agent 自主决策；
- LLM 自我反思打分；
- LLM 交易决策；
- LLM 归因盈亏；
- 全量 Twitter LLM 扫描；
- 外部新闻源大杂烩；
- embedding 聚类；
- LangGraph 必选；
- MLflow 必选；
- 自动下单；
- 模型微调。

这些都不是第一阶段该做的。

### 潜在不成熟点

#### 1. Strict Structured Outputs 的提供方兼容性

如果当前使用的是 OpenAI 官方 API，严格 schema 是成熟方案。

如果使用 OpenAI-compatible endpoint，可能不完全支持 `json_schema strict`。

建议策略：

```text
V1 默认要求 strict schema
不支持 strict 的 provider 直接 fail job
不要 fallback 到 old json_object
```

这是破坏式策略，但符合系统目标。

#### 2. Credit assignment 是近似，不是因果推断

当前 credit 公式：

```text
rho_i = abs(event_score_i) / sum(abs(event_score_j))
credit_i = rho_i * sign(event_score_i) * normalized_outcome
```

这是合理 MVP，但不是严格因果归因。

必须在 UI/文档里叫：

```text
predictive credit
```

不要叫：

```text
cause
causal attribution
```

#### 3. 权重学习可能被小样本污染

虽然 shrinkage 能缓解，但早期样本仍然少。

建议强制：

```text
n < 50: 只展示，不参与 scoring
50 <= n < 200: candidate config
n >= 200: 才允许 promotion review
```

具体阈值可以后续调，但必须有样本门槛。

#### 4. Price data 不足会让 settlement 不稳定

如果 token 市场快照稀疏，很多 seed 无法结算。

这不是 LLM 问题，是市场数据问题。

MVP 应该允许：

```text
outcome_status = missing_market
```

但不能把 missing outcome 当失败或成功。

## 是否真正能够实现闭环

### 闭环定义

一个真正闭环必须从输入回到系统参数或配置评估。

最小闭环是：

```text
event -> extraction -> snapshot -> decision -> outcome -> credit -> report
```

完整闭环是：

```text
event -> extraction -> snapshot -> decision -> outcome -> credit -> weights -> config candidate -> shadow/paper promotion
```

### 当前设计能闭环的地方

它已经覆盖闭环关键对象：

- `social_event_extractions`: 模型理解结果；
- `event_clusters`: 同一事件/注意力坐标；
- `harness_snapshots`: 事前冻结；
- `harness_decisions`: shadow/paper 决策；
- `harness_outcomes`: 到期结果；
- `harness_credits`: 多事件信用；
- `harness_weights`: 慢速学习；
- `score bucket reports`: 配置评估。

对象齐全，所以从数据模型上可以闭环。

### 还需要补齐的关键执行条件

闭环能不能跑，不取决于表够不够，而取决于下面这些条件能不能满足。

#### 1. Snapshot 必须不可变

一旦写入：

```text
snapshot_id
event_clusters_json
market_state_json
config_version
prompt_version
schema_version
scoring_version
```

就不能事后被更新。

可以新增修正版 snapshot，但不能修改历史 snapshot。

#### 2. 所有时间必须使用 received_at / decision_time

不能用未来数据。

结算时只能找：

```text
decision_time 之后的 forward price
```

评分时只能用：

```text
decision_time 之前已经存在的信息
```

#### 3. Outcome 必须有状态

不是所有 snapshot 都能结算。

需要状态：

```text
pending
settled
missing_entry_price
missing_exit_price
missing_baseline
insufficient_market_data
```

没有这些状态，闭环会把数据缺失误当成信号错误。

#### 4. Credit 必须和 snapshot 绑定

Credit 不能直接绑定 raw event。

必须绑定：

```text
snapshot_id + cluster_id + horizon + scoring_version
```

否则没法复盘“当时系统为什么这么判断”。

#### 5. Weight update 不能直接改历史

权重更新只影响未来 config candidate。

历史 snapshot 保持原版本。

这点是闭环可信度的核心。

### 结论：能闭环，但要先做“影子闭环”

不要第一阶段追求 live。

第一阶段目标应该是：

```text
shadow-only closed loop
```

也就是：

```text
不下单
但每个信号都生成 snapshot
每个 snapshot 都到期结算
每个 outcome 都分配 credit
每天看 score bucket
```

这已经是真闭环。

## 推荐的 KISS MVP

### MVP 范围

建议第一版只做这些：

```text
1. social-event-v1 strict extraction
2. social_event_extractions table
3. harness_snapshots table
4. harness_decisions table
5. harness_outcomes table
6. harness_credits table
7. 简单 scoring
8. 简单 baseline
9. settle-harness CLI
10. score-bucket CLI/API report
```

先不做：

```text
复杂 event_clusters merge
自动权重影响实时分数
config promotion 自动化
UI 大改
外部新闻源
paper/live execution
embedding clustering
```

### MVP 数据流

```text
watched event
  -> LLM social-event-v1
  -> if signal: snapshot
  -> shadow decision
  -> after horizon: outcome
  -> credit
  -> score bucket report
```

### MVP 成功标准

只看五个指标：

```text
schema_success_rate
snapshot_count
settlement_coverage
score_bucket_monotonicity
avg_normalized_abnormal_return_by_bucket
```

不要一开始看太多指标。

## 影响评估

### 产品影响

短期产品会变得更“冷”：

- narrative label 少了；
- 自动解释少了；
- 一些看起来有趣的动态不会被展示成交易机会；
- 历史 narrative 不能直接延续。

长期产品会更有交易价值：

- 每个信号都有证据链；
- 每个信号都有 horizon；
- 每个信号都有 outcome；
- 每个信号可以被归因；
- 每个配置可以和旧配置比较。

### 交易影响

正面：

- 减少 LLM 幻觉 ticker；
- 减少价格已动后的追高；
- 减少单条新闻过度归因；
- 可以知道哪些账号/事件类型/horizon 真有效。

负面：

- 早期 signal 数量会下降；
- 很多 meme seed 会停留在 watch 状态；
- settlement 覆盖率受市场数据影响；
- bucket 单调性可能一开始很差。

这里 bucket 单调性差不是坏事。它说明旧叙事系统没有 edge，或者 scoring 需要改。至少系统终于能诚实地告诉你。

### 工程影响

正面：

- 语义边界清晰；
- parser 更简单；
- 旧 narrative 双系统被删除；
- 后续 debug 可以定位到 extraction/scoring/settlement/credit。

负面：

- schema 表增加；
- 测试需要大改；
- CLI/API 新增；
- 文档和操作流程更重。

这是一笔合理交易。因为复杂度换来的是可验证闭环，而不是 UI 花活。

### 运营影响

新增人工/自动任务：

```text
定期 settle due snapshots
生成 score bucket 报告
检查 settlement coverage
检查 schema failure
检查 weight drift
决定 candidate config 是否进入 paper
```

这意味着系统从“实时看板”变成“研究/生产一体化 harness”。

### 数据影响

旧数据：

- 不应该伪迁移；
- 不应该直接映射成新 social event；
- 只能作为历史 raw evidence；
- 如果要进入新系统，必须 replay 原始事件并重新跑新 extractor。

新数据：

- 从 social-event-v1 开始记录；
- 每条 extraction 有 schema/prompt/model 版本；
- 每条 snapshot 有 config/scoring/baseline 版本；
- 每条 outcome 有 settlement 版本。

## 关键风险

### 风险 1：闭环过度设计

表现：

```text
表很多，报告很多，但没有先证明 score bucket 有用
```

缓解：

```text
先做 shadow-only MVP
第一阶段只看 score bucket
不做 UI 大改
不做权重自动生效
```

### 风险 2：LLM strict schema 失败率高

表现：

```text
高价值账号动态来了，但 job 经常失败
```

缓解：

```text
记录 schema failure
人工审查失败样本
改 prompt/schema
不 fallback 到旧 narrative
```

### 风险 3：token uptake 证据不足

表现：

```text
Musk/CZ 产生了 attention seed，但没有确定 CA/token 映射
```

缓解：

```text
保留 attention seed
不升级成 tradable candidate
等 public stream/token mention 验证
```

### 风险 4：settlement 市场数据不足

表现：

```text
snapshot 很多，但 outcome 很少
```

缓解：

```text
先聚焦 BTC/ETH/BNB/SOL/高流动 token
missing_market 单独统计
不要把缺失结算当信号失败
```

### 风险 5：权重学习过早自激

表现：

```text
少数几次 credit 改变权重，权重又影响未来 score
```

缓解：

```text
权重先 report-only
样本数阈值前不进入 scoring
candidate config 必须 shadow 对比
```

## 最终评估

### KISS 评分

如果按推荐 MVP 做：

```text
8/10
```

原因：

- 单 LLM 节点；
- 单数据源；
- SQLite 状态机；
- strict schema；
- shadow-only；
- 无兼容双系统。

扣分点：

- 表和状态比当前系统多；
- settlement/credit/weights 是新运营负担。

如果按完整 spec 一次性全做：

```text
5/10
```

原因：

- event clustering、weights、config promotion、UI、API、settlement 全一起上，会太重；
- 闭环还没验证，复杂度已经堆满。

### 成熟度评分

核心方案成熟度：

```text
7.5/10
```

成熟部分：

- strict schema extraction；
- SQLite durable state；
- shadow decisions；
- abnormal return settlement；
- score bucket evaluation。

需要谨慎部分：

- credit assignment 是近似；
- weight learning 要慢；
- market baseline 先简单；
- clustering 后置。

### 闭环可实现性评分

如果先做 shadow-only MVP：

```text
8/10
```

如果要求第一版就 paper/live/canary：

```text
4/10
```

闭环能实现，但路径必须是：

```text
先证明预测性
再谈交易化
```

## 建议的最终执行顺序

### 第一刀

```text
social-event-v1 contract
social_event_extractions
harness_snapshots
harness_decisions(shadow)
```

目标：

```text
每个高价值 watched event 都能变成可回放的结构化 signal hypothesis
```

### 第二刀

```text
harness_outcomes
harness_credits
settle-harness CLI
score-bucket report
```

目标：

```text
知道信号有没有预测性
```

### 第三刀

```text
weights report-only
candidate config
paper-only evaluation
```

目标：

```text
让系统学习，但不让小样本污染实时信号
```

### 第四刀

```text
UI 重构
attention seed / snapshot / outcome / credit 视图
```

目标：

```text
把已验证的闭环展示给交易员
```

## 最后结论

这个方案从方向上是正确的，因为它把系统从：

```text
LLM 叙事解释器
```

升级为：

```text
可验证的社交新闻交易 harness
```

但它必须以 KISS 的方式落地：

```text
单 LLM 节点
单输入源
严格 schema
shadow-only
简单 baseline
report-only learning
无兼容双系统
无外部源
无 live trading
```

这样它能真正闭环。

如果背离这些约束，它会变成另一个复杂但不可验证的“智能叙事系统”。
