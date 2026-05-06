# Harness Abnormal Return Baseline 升级（设计规格）

文档日期：2026-05-06
状态：待评审

## 1. 背景

Signal Lab Harness 是 gmgn-twitter-intel 的闭环度量子系统：把 watched accounts 发出的社交事件抽取为结构化信号、锁定决策时刻的市场快照、在指定 horizon 后结算价格变动、把结果反向归因到原始事件与来源。Pulse 是这条闭环对外的展示面：哪类事件、哪些来源在 horizon 后被市场验证有预测力。

整套产品价值的核心断言是：「系统能用真实价格变动证伪或证实社交信号的预测力。」

这一断言成立的前提是 outcome metric 必须有能力把"信号有预测力"和"市场普遍上涨/下跌"区分开。当前实现的 outcome 不具备这个区分能力，本规格定义升级路径。

## 2. 现状审计

证据均出自当前 main 分支代码，作为问题诊断的事实依据，不作为执行指令（执行细节由后续 plan 给出）。

**规格层（设计正确）**：`docs/superpowers/specs/2026-05-04-closed-loop-social-event-harness-design.md` 第 836-870 行明确写入 `expected_return = 0.6 × BTC_or_ETH_benchmark + 0.4 × asset_recent_momentum`、`abnormal_return = actual_return − expected_return`。

**函数层（实现正确）**：`pipeline/harness_settlement.py:10` 的 `expected_return()` 接受 benchmark returns 与 weights 字典，按线性组合返回期望收益；`:20` 的 `abnormal_return()` 计算 actual − expected。函数本身没有缺陷。

**调用层（被绕过）**：
- `pipeline/harness_ops.py:14`：`BASELINE_VERSION = "benchmark-zero-v1"`
- `pipeline/harness_ops.py:68-69`：`expected = 0.0; abnormal = abnormal_return(actual, expected)`
- `pipeline/token_signal_settlement.py:53` 内部还有一份独立的 `abnormal_return()` 副本，调用点 `:142-143` 同样写死 `benchmark = 0.0`
- `pipeline/harness_snapshot_builder.py:18,224`：snapshot 构造时把 `baseline_version = "benchmark-zero-v1"` 写入 versions_json

设计者把"零基线"刻入版本字符串，等于在代码里登记了"我们当前没有 benchmark"，但这一登记没有被任何下游消费者使用。

**评估层（不切片）**：`retrieval/harness_service.py:177` 的 `score_buckets(*, horizon)` 签名只接受 horizon，不接受 scoring_version 与 baseline_version。任何对 score 公式或 baseline 公式的更新会让新旧 population 在同一查询下被合并统计。

**scoring 形态（背景信息）**：`pipeline/harness_scoring.py:4` 的 `base_event_score = sign(direction) × impact × confidence × novelty × (1 − pricedness)`；`:29` 的 `combined_score = sum(event_scores)`；`pipeline/harness_credit.py:11` 的 credit responsibility 按 |event_score| 比例分配。这些是 outcome 的下游消费者，本规格不修改这些公式，但会替换它们消费的 outcome 输入。

## 3. 问题诊断

把 expected_return 在调用层硬编码为零，等价于在事件研究中省略 benchmark return 项。后果是 abnormal_return 退化为 actual_return，整条闭环的 outcome 度量从"相对超额收益"退化为"绝对涨跌幅"。

退化沿下游传播，污染所有依赖 outcome 的决策：

- credit 按 normalized outcome 在事件之间分配责任。outcome 是 raw return，则 credit 衡量的是 token 涨跌方向，不是 token 跑赢/跑输 sector 的方向。
- weight update（source_weight, event_type_weight）以 credit 为输入。系统因此学到的是「在涨潮期发推的来源」，不是「事后被市场验证有 alpha 的来源」。
- bucket 评估展示的 hit rate 在大盘单边行情下接近大盘涨跌占比。在 SOL 单日涨 5% 的日子里，所有 positive 信号都会"命中"，看似 65% hit rate 实则毫无预测力。
- 用户在 Pulse 上看到的「高 score → 高 hit rate」曲线，本质是 raw return 对 score 的拟合，不是 alpha 对 score 的拟合。

并发问题：bucket 评估不按 (scoring_version, baseline_version) 切片，意味着任何度量公式迭代都会让新旧 population 在同一聚合下混合。CLAUDE.md "Scoring and ranking design" 节明文禁止「A/B 比较静默混合不同版本的 population」——这件事在当前代码里从未被防住。

## 4. 第一性原理与文献依据

- **事件研究方法论**（MacKinlay 1997, *Journal of Economic Literature* 35(1)）：研究单一事件对资产价格影响时，必须把实际收益分解为 expected component（在没有该事件下的预期）与 abnormal component（事件归因部分）。abnormal_return = actual_return − expected_return 是事件归因的标准定义。
- **因子分解**（Sharpe 1964 *Journal of Finance*；Fama & French 1992 *Journal of Finance*）：资产收益由 systematic 部分（β × 市场收益）与 idiosyncratic 部分组成。一条社交信号是否「预测了独立于大盘的事情」，关心的是 idiosyncratic 部分。
- **Crypto sector benchmark**：在 alt/meme coin 领域，单一使用 BTC 会显著低估 sector beta，因为 alt 与 BTC 的相关性弱、与同链主币（SOL/ETH/BNB）的相关性强。务实做法是按链选择 sector proxy。本仓库 watched handles 的发言对象主要在 Solana 链，首期采用 SOL 作为 sector benchmark。
- **版本契约**：每次度量公式变化构成一次 measurement regime change。混合不同 regime 的样本计算 hit rate 是统计错误。任何评估接口必须以 (scoring_version, baseline_version) 为必填筛选键。这是 ML 实验工程的基本要求，CLAUDE.md 已作为强约束写入。

## 5. 目标与可证伪指标

主目标：把 Harness settlement 的 outcome metric 从 raw return 升级为 abnormal return（相对 sector benchmark 的超额收益），让 credit / weight update / hit rate 三个下游度量从测量市场 beta 升级为测量信号 alpha。

可证伪指标 M1-M5——部署后必须达成，否则视为本规格未达成：

**M1（数值一致性）**：对 Solana 链上某 token，当 SOL 在 horizon 内涨 X%、token 同步涨 X% 时，新 baseline 下该 snapshot 的 abnormal_return 落在 [−0.5%, +0.5%]；同一 snapshot 的 actual_return 仍记录为 X%；两者之差的绝对值与 X% 之差不超过 0.5 个百分点。该指标用单元测试 + 一段真实数据回放验证。

**M2（区分性）**：选取连续 30 天历史数据回放，按新 baseline 切两组——SOL 单日涨幅 > 5% 的日子 vs 单日跌幅 > 5% 的日子。两组中 positive 信号的 abnormal_return 均值的双样本 t 检验 p > 0.05。该指标证明 outcome 已脱离大盘相关性。

**M3（版本隔离）**：bucket 接口在不传 (scoring_version, baseline_version) 完整元组时返回 HTTP 400。传入 (`harness-score-v1`, `benchmark-zero-v1`) 与 (`harness-score-v1`, `benchmark-sol-v1`) 必须返回完全不重叠的样本集合，N 之和等于截至查询时刻的全部 settled snapshot 总数。

**M4（cold start 显式化）**：新 baseline 下样本量 N < 200 时，bucket 接口必须返回 `insufficient_samples = true` 与 N，前端 Pulse 不展示具体 hit_rate 数字而展示 warmup 提示。该阈值依据：在 effect size 0.1（hit rate 60% vs 50%）、α=0.05、power=0.8 的标准 power analysis 下，单 bucket 至少需要约 200 样本才能开始有可解释的统计推断；低于此值的展示对用户构成误导。

**M5（健康可观测）**：harness-health 探针返回字段必须包含 current_baseline_version 与 baseline_stale_rate_24h（24h 内 abnormal_return = NULL 的 outcome 比例）。运维不读代码即可判断 baseline 当前是否失效。

## 6. 目标架构

引入两个一阶概念：

**Benchmark Reference**：系统持续维护若干 benchmark 资产（首期：SOL）的市场快照序列，时间网格密度与 watched token 一致。Benchmark 资产由系统主动注册到 market_observation_worker，与 watched accounts 是否提及 SOL 完全无关——它是基础设施，不是观测对象。

**Baseline Composition**：从 token 到 benchmark 的映射规则。首期采用 chain-based 简单映射：

- chain == solana → benchmark = SOL，baseline_version = `benchmark-sol-v1`
- 其他链 → benchmark = unavailable，baseline_version = `benchmark-unavailable-v1`，abnormal_return = NULL

settlement 流程的语义改写：

- T 时刻 freeze：snapshot 同时锁定 token entry price 与 benchmark entry price
- T+H 时刻 settle：读取 token 与 benchmark 在 T+H 时刻的快照
- 计算：actual_return（token 涨跌幅）、expected_return（benchmark 涨跌幅）、abnormal_return = actual − expected
- 落库：outcome 同时记录三个量，附 baseline_version、benchmark_asset、baseline_stale 标志

bucket 评估的语义改写：

- 接口必填 (scoring_version, baseline_version)
- hit_rate 定义为 sign(score) == sign(abnormal_return) 的样本占比
- avg_outcome 字段语义改为 abnormal_return 均值；额外保留 avg_actual_return 作为参考
- baseline_unavailable 与 baseline_stale 的 snapshot 不计入 bucket，但仍出现在 chain 详情中

credit 的语义改写：credit_i = responsibility_i × sign(score_i) × normalized(abnormal_return)。responsibility 与 normalization 函数保持原状，仅替换其中的 outcome 输入。

## 7. 概念数据流

```
T 时刻（freeze）
  LLM extraction → builder
  snapshot 锁定:
    token_entry_price     = at_or_before(token, T)
    benchmark_entry_price = at_or_before(SOL, T)        [当 token 在 Solana]
    versions = {
      scoring_version  = harness-score-v1
      baseline_version = benchmark-sol-v1                [否则 benchmark-unavailable-v1]
    }

T+H 时刻（settle）
  token_exit_price     = at_or_after(token, T+H, tol ≤ Δ)
  benchmark_exit_price = at_or_after(SOL,   T+H, tol ≤ Δ)

  if benchmark missing or |t_actual − (T+H)| > Δ:
      outcome ← {actual_return, abnormal_return = NULL, baseline_stale = true}
  else:
      actual    = (token_exit − token_entry) / token_entry
      expected  = (bench_exit − bench_entry) / bench_entry
      abnormal  = actual − expected
      outcome ← {actual_return = actual, expected_return = expected,
                 abnormal_return = abnormal, baseline_stale = false}

evaluation
  GET /api/signal-lab/harness-buckets?scoring_version=…&baseline_version=…
    仅聚合 (scoring_version, baseline_version) 命中且 baseline_stale = false 的 snapshots
    N < 200 时附 insufficient_samples = true
```

时间容差 Δ 取 60 秒：market_observation_worker 写入间隔与 settlement 触发延迟之和的经验上界。超过 60 秒视为 baseline 失效，避免用过期 benchmark 价格污染 abnormal_return。

## 8. 核心模型

新增字段（语义层面，DDL 由 plan 决定）：

- harness_outcomes 增 `expected_return`、`abnormal_return`、`benchmark_asset`、`baseline_version`、`baseline_stale`
- harness_snapshots 的 versions_json 已存在，需保证 freeze 时为 `baseline_version` 与 `benchmark_asset` 赋值

新增常量：

- `BASELINE_VERSION = "benchmark-sol-v1"`（Solana 链 token 默认 baseline）
- `BASELINE_UNAVAILABLE = "benchmark-unavailable-v1"`（无 sector benchmark 的 token）

不变字段：

- actual_return 保留作为 raw return 参考，不删除——用户在 Pulse 上需要同时看到「token 涨跌」和「相对 SOL 的超额涨跌」
- scoring_version 保留为 `harness-score-v1`，本规格不动 score 公式

## 9. 接口契约

**settlement 内部不变量**：
- baseline_stale = true 时 abnormal_return 必为 NULL
- baseline_stale = false 时 actual_return / expected_return / abnormal_return 三字段必同时非 NULL
- baseline_version = `benchmark-unavailable-v1` 时 baseline_stale 不参与判定，abnormal_return 始终为 NULL

**API：GET /api/signal-lab/harness-buckets**：
- 必填 query：scoring_version、baseline_version
- 缺任一参数 → HTTP 400，body `{"error": "version_required"}`
- 不存在的版本组合 → HTTP 200，body `{"buckets": [], "insufficient_samples": true, "n": 0}`
- 正常响应：每个 bucket 含 `(score_min, score_max, n, hit_rate, hit_rate_lower_wilson, hit_rate_upper_wilson, avg_abnormal_return, avg_actual_return)`
- N < 200 时附 `insufficient_samples = true`，前端必须显示 warmup 提示

**API：GET /api/signal-lab/chains**：
- response 中每条 chain 增 `outcome.benchmark_asset` 与 `outcome.abnormal_return` 两字段
- outcome.actual_return 保留
- baseline_stale = true 时 abnormal_return 字段为 null，前端展示「baseline pending」徽标

**API：GET /api/signal-lab/harness-health**：
- 返回字段补：`current_baseline_version`、`baseline_stale_rate_24h`、`benchmark_asset_coverage`（被 settle 的 snapshot 中 baseline 不为 unavailable 的占比）

## 10. 不在范围

每项均为有意义但与本规格解耦的工作，须独立 spec：

- **LLM confidence 校准**：当前 confidence/impact/novelty 三个 LLM 输出量纲不统一、未经 calibration（Kadavath et al. 2022 *Language Models (Mostly) Know What They Know*；Tian et al. 2023 *Just Ask for Calibration* 表明 LLM 自评 confidence 系统性 over-confident）。本规格只让 outcome 度量正确，不修 score 输入端。
- **bot 鲁棒性**：当前 `combined_score = Σ event_scores` 对单作者复制粘贴线性敏感（CLAUDE.md "Scoring and ranking design" 节明文要求的 copy-pasta 单测缺失）。本规格不引入去重 / 冷却 / 同源惩罚。
- **Shapley credit attribution**：当前 credit = proportional by |score| 是广告 multi-touch attribution 中 linear-touch 的对称版（Shao & Li 2011 KDD）。本规格仅替换该公式中的 outcome 输入，不改 attribution 模型。
- **跨链 benchmark**：本规格首期只支持 Solana → SOL；其他链 token 标记 `baseline_unavailable`。
- **复合 benchmark**：原规格 2026-05-04 提到的 `0.6 × BTC + 0.4 × momentum` 复合形式不在本期实现。首期采用最简的 `1.0 × SOL`。在没有跑通最简形式之前引入复合是 over-engineering。
- **历史数据回填**：所有 `benchmark-zero-v1` 数据保留为历史快照，不计算 abnormal_return。明确不做 backfill 是因为 backfill 时使用 SOL 历史快照存在 lookahead 风险（在历史 T 时刻读取 SOL 价格，需要 SOL 在 T 时刻已写入，而历史 SOL 数据可能并不存在或时间分辨率不匹配）。新 baseline 从启用时刻起前向计算。

## 11. 风险与缓解

**R1 benchmark 数据缺失**：market_observation_worker 故障导致 SOL 快照延迟。缓解：baseline_stale 比例进入 health 探针，超过阈值（如 24h > 5%）触发告警。

**R2 benchmark 时间错位**：T 与 T+H 时刻读到的 SOL 快照与目标时刻偏差 Δ 超 60 秒。缓解：标记 baseline_stale，outcome 仍写入但 abnormal_return = NULL，bucket 评估自动剔除。

**R3 benchmark 自身被操纵**：极端事件下 SOL 价格本身被操纵（虽然概率低但确实存在）。本期不解决，记录为已知限制。如未来观察到显著影响，启动复合 benchmark 后续 spec（多 benchmark 加权能稀释单一 benchmark 操纵的影响）。

**R4 cold start**：新 baseline 启用后短期无足够样本。缓解：bucket 接口对 N < 200 显式返回 insufficient_samples，前端展示 warmup 提示。在样本积累期间 Pulse 仍展示 chain 全貌（extraction、seed、freeze、settle 状态）但隐藏 hit rate 数字。

**R5 非 Solana token 占比上升**：watched accounts 越来越多提到其他链 token 时 baseline_unavailable 比例上升。缓解：health 探针暴露 `benchmark_asset_coverage`，运维可监控并触发跨链 benchmark 后续 spec。当 coverage 低于 70% 视为达到触发阈值。

**R6 版本字符串组合爆炸**：未来 baseline 公式调整频繁会产生大量版本组合。本期版本仅两个，无需引入 version compatibility 表。当组合数超过 5 时（即 baseline 已迭代到第 5 版）启动 version compatibility 设计。

**R7 用户面误解**：用户看到 abnormal_return 为负但 token 实际上涨可能困惑。缓解：API 同时返回 actual_return 与 abnormal_return，前端在 detail panel 中清晰区分；列表层主显 actual_return 作为直观值，但 hit rate 与 bucket 统计基于 abnormal。

**R8 bot 仍可放大 combined_score**：本规格不解决，预期效果为：高 bucket 在新 baseline 下 hit rate 不会显著高于低 bucket，从而暴露 bot 影响力问题，作为下一个 spec（bot 鲁棒性）的依据。这是有意保留的"自暴露"机制——闭环健康前提下，本身就能暴露上游污染。

**R9 双路 settlement 的不一致**：当前 `harness_ops.py` 与 `token_signal_settlement.py` 各自有一份 abnormal_return 实现且都写死 benchmark = 0。本规格要求两条 settlement 路径同时升级。如只升级一条，会出现「同一 snapshot 在 harness_outcomes 表得到 SOL-baseline 的 abnormal_return，而在 token_signal_snapshots 表得到 zero-baseline 的 abnormal_return」的不一致状态，后续比较与诊断会被严重误导。两条路径的代码副本统一为单一 settlement 库由 plan 决定，但本规格强制要求"两条路径同 baseline"作为不变量。

## 12. 演进路径

下一阶段的独立 spec，按依赖顺序：

1. **跨链 benchmark**：添加 ETH（Ethereum 链）、BNB（BSC 链）的 benchmark 注册与 chain → benchmark 映射，让 baseline_unavailable 比例下降到接近零。前置条件：本规格落地、benchmark_asset_coverage < 70%。
2. **复合 benchmark**：在 sector benchmark 之上加入 `asset_recent_momentum` 项；baseline_version 升级为 `benchmark-composite-v1`。前置条件：sector benchmark 已稳定运行 ≥ 30 天且 M2 区分性指标持续达标。
3. **bot 鲁棒性**：通过同源/同语义事件的去重压缩 combined_score。前置条件：本规格落地后观察到 R8 预期的「高 bucket hit rate 不显著高于低 bucket」现象成立，作为 bot 污染的实证依据。
4. **LLM confidence 校准**：用 conformal prediction 或 Platt scaling 把 LLM 自评 confidence 映射到经验概率。前置条件：bot 鲁棒性已落地（避免用 bot 污染样本校准）、累积 settled snapshot N ≥ 1500。
5. **Shapley credit attribution**：在 N ≥ 5000 的样本规模下用 Shapley value 替代 proportional-by-score credit。前置条件：前四步全部完成、用户开始基于 credit 做策略选择。

每一步都需要可证伪指标，照本规格 §5 的格式给出。
