# Production Social Intelligence Algorithm Spec

日期：2026-05-05

## 背景

当前系统已经具备 GMGN public stream 采集、确定性 entity extraction、token rolling window、watched-account LLM social event extraction、harness shadow decision 和闭环 settlement。需要把 `heat` / `quality` 从展示型指标升级为生产级可冻结、可结算、可校准的 deterministic signal，并明确 LLM 的边界。

本 spec 不保留旧 scoring 兼容层：旧 `token_baseline.py`、旧 `*_v1` score version、固定 pricedness 和不可结算的半成品入口都应被替换。

## 设计原则

1. Evidence first：所有分数必须能追溯到 event、entity、token attribution、timeline bucket、market snapshot。
2. No lookahead：打分只能读取 decision time 之前或当时的 market snapshot；未来价格只允许 settlement 使用。
3. Snapshot immutable：进入评估闭环的 signal 必须冻结 component payload、market snapshot id、timeline 和 event ids。
4. LLM bounded：LLM 只用于 watched-account `social-event-v2` 结构化抽取，不参与全量 token-flow scoring、不做交易决策、不写入价格/收益判断。
5. Calibration ready：分数必须有 outcome、bucket evaluation、coverage 和置信区间，权重先 report-only。
6. Operationally simple：API/CLI 暴露查询、冻结、结算、评估；SQLite WAL 仍是唯一运行存储。

## 数据流

```text
GMGN public WS
  -> normalized_events
  -> token attributions
  -> token rolling flow
  -> baseline_scoring.token_baseline_v2
  -> timeline_features.build_timeline_features
  -> social_heat_v2 / discussion_quality_v2 / propagation_v2
  -> tradeability_v2 / timing_v3
  -> social_opportunity_v2
  -> token_signal_snapshots
  -> token_signal_outcomes
  -> token_score_evaluations
```

Watched-account harness 是独立边界：

```text
watched event
  -> enrichment job
  -> social_event_v2 strict JSON schema
  -> attention seed / event cluster / harness snapshot
  -> shadow decision
  -> benchmark-zero-v1 settlement
  -> report-only credit and weight
```

## 算法方案

### Baseline v2

文件：`src/parallax/retrieval/baseline_scoring.py`

- 输入：rolling token window、token历史窗口、当前窗口统计。
- 输出：`score_version=token_baseline_v2`、`baseline_avg_mentions`、`robust_z_mentions`、`ewma_mentions`、`new_burst_score`、`data_health`。
- 原理：
  - 使用 median + MAD 而不是简单均值，降低异常刷屏窗口对基线的污染。
  - 使用 EWMA 表示短期惯性。
  - 稀疏 token 通过 `new_burst_score` 进入可解释早期发现路径，而不是假装有稳定基线。
  - `data_health` 标记 sample count、coverage、sparse/ok 状态，供下游降权。

### Timeline Features

文件：`src/parallax/retrieval/timeline_features.py`

- 5m 使用 30s bucket；1h 使用 5m bucket；4h 使用 15m bucket；24h 使用 1h bucket。
- 计算：
  - bucket mentions/posts/authors；
  - effective authors entropy；
  - true new authors by first-seen bucket；
  - reproduction rate；
  - phase: `ignition` / `expansion` / `saturation` / `fade`。
- 返回 `event_ids`，供 snapshot 冻结 evidence 集合。

### Component Scores

文件：

- `src/parallax/retrieval/social_heat_scoring.py`
- `src/parallax/retrieval/discussion_quality_scoring.py`
- `src/parallax/retrieval/propagation_scoring.py`
- `src/parallax/retrieval/tradeability_scoring.py`
- `src/parallax/retrieval/timing_scoring.py`
- `src/parallax/retrieval/opportunity_scoring.py`
- `src/parallax/retrieval/scoring_common.py`

版本：

- `social_heat_v2`
- `discussion_quality_v2`
- `propagation_v2`
- `tradeability_v2`
- `timing_v3`
- `social_opportunity_v2`

原理：

- Heat 衡量相对历史异常、绝对规模、短期速度和 sparse burst。
- Quality 衡量独立作者、去重、源质量、非重复讨论密度。
- Propagation 衡量扩散阶段、新作者、reproduction、entropy 和跨 bucket 延续。
- Tradeability 衡量 liquidity、market snapshot freshness、价格可用性、lookahead risk。
- Timing 衡量 phase、chase risk、early expansion 和 stale/fade 惩罚。
- Opportunity 使用固定生产权重：heat .26、quality .22、propagation .22、tradeability .18、timing .12。

硬门槛：

- driver 条件：opportunity >= 72、heat >= 68、quality >= 62、propagation >= 62、tradeability >= 70、timing >= 55、phase in expansion/ignition、无 hard risk。
- hard risk cap 40；chase cap 55；repeated/duplicate cap 50；public-only unconfirmed cap 68。

### Token Signal Snapshot / Settlement / Evaluation

文件：

- `src/parallax/storage/token_signal_repository.py`
- `src/parallax/retrieval/token_signal_snapshot_service.py`
- `src/parallax/pipeline/token_signal_settlement.py`
- `src/parallax/retrieval/token_signal_evaluation_service.py`
- `src/parallax/storage/sqlite_schema.py`

表：

- `token_signal_snapshots`
- `token_signal_outcomes`
- `token_score_evaluations`
- `llm_enrichment_labels`

结算：

- entry snapshot：decision time at-or-after。
- exit snapshot：decision time + horizon at-or-after。
- abnormal return：token return - benchmark return。
- normalized outcome：abnormal_return / max(realized_vol, .03)，并 clamp 到 [-1, 1]。
- 缺 entry/exit/price 必须写显式 outcome status，不静默跳过。

评估：

- bucket：0-39、40-54、55-69、70-84、85-100。
- 输出 snapshot_count、settled_count、settlement_coverage、average returns/outcome、directional_hit_rate、Wilson interval。

### Harness Upgrade

文件：

- `src/parallax/pipeline/social_event_extraction.py`
- `src/parallax/pipeline/harness_snapshot_builder.py`
- `src/parallax/pipeline/harness_settlement.py`
- `src/parallax/pipeline/harness_ops.py`
- `src/parallax/pipeline/enrichment_worker.py`

变更：

- LLM response format name 改为 `social_event_v2`。
- harness schema version 改为 `social-event-v2`，prompt version 改为 `social-event-extractor-v2`。
- fixed `pricedness=0.35` 删除，改为 token 30m pre-move pricedness。
- policy threshold 降到 .55，shadow threshold 降到 .20，避免 shadow harness 永远不触发。
- benchmark version 改为 `benchmark-zero-v1`，vol floor 统一 .03。

## API / CLI

HTTP：

- `GET /api/token-signal-snapshots`
- `GET /api/token-signal-outcomes`
- `GET /api/token-signal-evaluations`

CLI：

- `token-signal-snapshots`
- `token-signal-outcomes`
- `token-signal-evaluations`
- `ops freeze-token-signals`
- `ops settle-token-signals`

## 验收标准

1. `uv run pytest` 全量通过。
2. `uv run ruff check .` 通过。
3. `uv run python -m compileall src tests` 通过。
4. 生产代码和测试中不得保留旧 token scoring 入口：
   - `token_baseline.py`
   - `social_heat_v1`
   - `discussion_quality_v1`
   - `propagation_v1`
   - `tradeability_v1`
   - `timing_v2`
   - `social_opportunity_v1`
5. 不得保留固定 pricedness 或旧 harness benchmark：
   - `pricedness=0.35`
   - `baseline-zero-v0`
6. Token signal freeze 不调用 LLM。
7. Token flow market block 必须包含 freeze/settlement 所需 snapshot id，并避免 lookahead。
8. README 必须描述 v2 LLM 边界、token signal snapshot、settlement/evaluation CLI/API。
