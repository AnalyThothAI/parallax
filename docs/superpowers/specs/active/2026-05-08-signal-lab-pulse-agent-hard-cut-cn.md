# Signal Lab Pulse Agent Hard Cut Spec

日期：2026-05-08

取代：

- `docs/superpowers/specs/2026-05-06-watched-account-trading-attention-cn.md`
- `docs/superpowers/plans/2026-05-06-watched-account-trading-attention.md`
- 当前 `TradingAttentionService` on-demand Pulse 读模型

## 1. 目标

Signal Lab Pulse 必须从“watched-account attention feed”升级为“可验证的交易语境候选系统”。

新系统保留 watched-account 逐推文 agent 的核心能力：Musk、CZ、HeYi、toly 等高权重账号即使不提具体 token，也能产生主题、关键词、生态、意图和潜在资金流注意力种子。与此同时，token radar 已经有确定性社交评分；当某个 token 的 social heat / propagation / opportunity 达到阈值时，系统需要一个 bounded agent 总结交易语境，但不能让 agent 改写评分或直接给交易执行指令。

## 2. Hard Cut 原则

本次不保留兼容性代码。

必须删除：

- `src/parallax/retrieval/trading_attention_service.py`
- `tests/test_trading_attention_service.py`
- 所有 `TradingAttention*` TypeScript 类型
- `SignalLabPulse` / `SignalLabWorkbench` / `SignalLabInspector` 对 `TradingAttentionData` 的依赖
- `/api/signal-lab/pulse` 当前从 events/social_event_extractions/token_intent_resolutions 临时拼装的实现

禁止新增：

- `LegacyTradingAttentionService`
- `TradingAttentionData` 到 `SignalPulseData` 的 alias
- 旧字段兼容映射，例如 `kind -> pulse_status`
- 同时支持旧 `kind=direct_token|topic_heat` 和新 `status=trade_candidate|theme_watch` 的 API 分支
- 回退读取旧 on-demand attention rows

允许保留：

- `/api/signal-lab/pulse` 路径名，但响应 contract 必须硬切为 `SignalPulseData`
- watched-account `social_event_extractions` agent 链路
- harness/lab audit endpoints
- token radar v6 scoring

## 3. 交易第一性

Pulse 不回答“谁在发推”，而回答“这个信息是否可能改变未来订单流，以及它是否仍然可交易”。

交易员第一性问题：

1. 信息是否领先价格，而不是价格先涨后社交追认。
2. 注意力是否独立扩散，而不是单账号反复喊话或复制粘贴。
3. 是否有 deterministic token identity 和可交易市场。
4. 如果没有 token，是否能形成可观察主题篮子或后续 token 映射。
5. 当前阶段是 seed、ignition、expansion、concentration 还是 chase。
6. 有哪些确认条件和失效条件。
7. 历史上相似 source / event type / phase / score bucket 是否有正向 abnormal return。

所以 agent 只做语义和交易语境解释；score、gate、排序、结算和 credit 必须确定性。

## 4. 两条产品链路

### 4.1 Source-led Attention

触发源：高权重 watched account 发推。

典型例子：

- Musk 提到 Grok、xAI、payments、robotaxi。
- CZ 提到 BNB Chain、listing culture、ecosystem support。
- HeYi 提到 listing 标准、交易所风控、生态项目。
- toly 提到 Solana tech、DePIN、手机、生态 builder。

这条链路经常没有直接 token。它的输出不是交易候选，而是 `AttentionSeed`：

```text
source event -> SocialEventExtractionAgent -> AttentionSeed -> optional ThemePulseCandidate
```

Source-led 可以进入 Pulse，但只能是：

- `theme_watch`
- `risk_rejected_high_info`
- `blocked_low_information`，仅计入 health，不展示为普通 row

Source-led 不能产生 `trade_candidate`，除非后续被 deterministic token resolver 或 token radar 绑定到具体 target。

### 4.2 Asset-led Token Thesis

触发源：token radar 已经发现某个 token 社交分数达阈值。

触发条件：

```text
radar.decision in {"driver", "watch"}
or score.heat.score >= 80
or score.propagation.score >= 70
or watched_confirmation present
```

这条链路必须读取：

- token radar v6 score JSON
- target social timeline
- stage builder 输出
- source event IDs
- market snapshot
- price before/after social
- harness historical credit

它的输出是 `PulseThesis`，再由 deterministic `PulseCandidateGate` 写入 `pulse_candidates`。

## 5. Agent 边界

### 5.1 保留的上游 agent

`SocialEventExtractionAgent` 继续逐推文处理 watched accounts。

职责：

- 抽取 source-backed social event。
- 抽取 anchor terms。
- 抽取 token candidates，但不强行映射 token identity。
- 输出中文摘要。
- 标注 semantic risks。

禁止：

- 输出买卖建议。
- 输出仓位、杠杆、目标价、止损。
- 改写 deterministic token identity。

### 5.2 新增 PulseThesisAgent

`PulseThesisAgent` 只处理已触发的 source-led 或 asset-led 候选，不参与实时 ranking 主路径。

输入：

```text
candidate context:
  candidate_type
  source event IDs
  watched social extraction
  radar score blocks
  target social timeline
  token target posts
  market context
  harness history
```

### 5.3 Token Timeline 总结

`PulseThesisAgent` 不应该只看触发它的单条推文。对 asset-led token candidate，它必须读取一个确定性压缩后的 token 时间线，然后做“阶段总结和交易语境提炼”。

窗口设计：

```text
trigger_window = 5m
primary_context_window = 1h
extended_context_window = 4h
baseline_window = 24h
```

Agent 输入不是整段无限 raw timeline，而是 `PulseTimelineContextBuilder` 生成的 bounded context：

```json
{
  "target": {},
  "windows": {
    "5m": {
      "mentions": 12,
      "authors": 5,
      "watched_mentions": 1,
      "phase": "ignition",
      "top_author_share": 0.25,
      "duplicate_text_share": 0.08,
      "price_change_since_social_pct": 0.04
    },
    "1h": {},
    "4h": {},
    "24h": {}
  },
  "stage_segments": [
    {
      "phase": "seed",
      "start_ms": 1778240000000,
      "end_ms": 1778240060000,
      "representative_event_ids": ["event-1"],
      "summary_facts": ["watched source first mentioned PEPE"]
    }
  ],
  "post_clusters": [
    {
      "cluster_id": "text:sha256:...",
      "cluster_type": "unique_information",
      "representative_event_id": "event-1",
      "event_ids": ["event-1", "event-3"],
      "authors": ["cz_binance", "trader_a"],
      "watched_author_present": true,
      "text_excerpt": "$PEPE ignition ...",
      "first_seen_ms": 1778240000000,
      "latest_seen_ms": 1778240100000
    }
  ],
  "selected_posts": [
    {
      "event_id": "event-1",
      "author_handle": "cz_binance",
      "text": "$PEPE ignition ...",
      "role": "watched_seed"
    }
  ],
  "market_overlay": {},
  "radar_score": {}
}
```

Post selection budget：

```text
max_selected_posts = 24
max_post_clusters = 16
max_raw_text_chars_per_post = 280
```

必须包含：

- first seed post
- latest post
- watched-author posts
- 每个 stage 的 representative posts
- direct CA/ticker evidence posts
- price inflection 附近 posts
- 新独立作者 posts
- high-risk duplicate/concentration representative post

必须先做确定性去重：

- `normalized_text_hash`: lowercase、去 URL、去多空白、去常见 emoji/punctuation 后 hash。
- `semantic_cluster_key`: normalized text + primary URL domain + cashtags + target_id。
- 同 author 同文本只保留 first/latest。
- 多 author 同文本聚合为 cluster，并把 `duplicate_text_share` 暴露给 agent。

Agent 输出要回答：

```text
what_changed_in_5m
what_changed_in_1h
which_stage_changed
whether_new_information_or_repetition
whether_social_is_before_price
confirmation/invalidation
```

这让 agent 做“时间线摘要”，不是“单推文解释”。

输出：

```python
class PulseThesisPayload(BaseModel):
    schema_version: Literal["pulse_thesis_v1"]
    candidate_type: Literal["source_seed", "token_target"]
    subject_key: str
    target_type: Literal["Asset", "CexToken"] | None
    target_id: str | None
    symbol: str | None

    verdict: Literal[
        "trade_candidate",
        "token_watch",
        "theme_watch",
        "risk_rejected_high_info",
        "blocked_low_information",
    ]
    social_phase: Literal[
        "seed",
        "ignition",
        "expansion",
        "concentration",
        "chase",
        "unknown",
    ]
    narrative_type: Literal[
        "direct_token",
        "ecosystem_spillover",
        "listing_or_exchange",
        "product_catalyst",
        "meme_phrase",
        "risk_event",
        "market_structure",
        "unknown",
    ]

    summary_zh: str
    why_now_zh: str
    bull_case_zh: list[str]
    bear_case_zh: list[str]
    confirmation_triggers_zh: list[str]
    invalidation_triggers_zh: list[str]
    top_risks: list[str]

    evidence_event_ids: list[str]
    source_event_ids: list[str]
    confidence: float
```

约束：

- `evidence_event_ids` 必须是输入 `source_event_ids` 子集。
- `trade_candidate` 必须有 `target_type` 和 `target_id`。
- `theme_watch` 必须没有强制 token target。
- `blocked_low_information` 不进入普通 Pulse row。
- 输出文本不能包含买入、卖出、开仓、做多、做空、仓位、杠杆、目标价、止损价等执行指令。

## 6. OpenAI Agents SDK 使用方式

使用 `openai-agents-python` 的 `Agent`、`Runner.run`、`RunConfig`、`output_type` 和 tracing。

Agent 形态：

```text
PulseThesisAgent
  output_type = PulseThesisPayload
  tools = [
    fetch_pulse_candidate_context,
    fetch_target_social_timeline,
    fetch_radar_score,
    fetch_market_context,
    fetch_harness_history
  ]
  max_turns = 3
```

不使用多 agent 辩论。原因：

- 交易解释需要一致口径，不需要角色扮演式争论。
- 工具读取是 deterministic；最终语义归纳由一个 agent 完成。
- 输出必须可审计，trace 中能看到 input hash、tool input/output hash、output hash。

Trace metadata：

```json
{
  "workflow_name": "parallax.pulse_thesis",
  "agent_name": "PulseThesisAgent",
  "prompt_version": "pulse-thesis-agents-sdk-v1",
  "schema_version": "pulse_thesis_v1",
  "candidate_id": "...",
  "candidate_type": "token_target",
  "subject_key": "...",
  "input_hash": "...",
  "artifact_version_hash": "..."
}
```

## 7. Deterministic Gate

`PulseCandidateGate` 是唯一能决定生产 Pulse 状态的模块。

### 7.1 Status

```text
trade_candidate
token_watch
theme_watch
risk_rejected_high_info
blocked_low_information
```

Pulse 普通列表只展示：

```text
trade_candidate
token_watch
theme_watch
risk_rejected_high_info
```

`blocked_low_information` 只进入 health 和 Lab diagnostics。

### 7.2 Trade Candidate Gate

`trade_candidate` 必须满足：

```text
candidate_type == token_target
target_type in {"Asset", "CexToken"}
target_id present
radar.decision == "driver"
heat >= 75
quality >= 62
propagation >= 62
tradeability >= 70
timing >= 50
phase in {"ignition", "expansion"}
market_status == "fresh"
no hard_risks
not chase_risk
agent confidence >= 0.65
```

任何一条失败，则降级为：

- `token_watch`：信息有效，但 trade gate 不完整。
- `risk_rejected_high_info`：信息强，但有硬风险，例如 chase、market stale、identity ambiguity、liquidity missing。
- `blocked_low_information`：证据弱、文本低信息、重复 cluster、public-only unconfirmed。

### 7.3 Heat >= 80 规则

`heat >= 80` 只代表“异常注意力”，不是交易许可。

```text
heat >= 80 + identity unresolved
  -> blocked_low_information or risk_rejected_high_info

heat >= 80 + price_change_before_social >= 15%
  -> risk_rejected_high_info with chase_risk

heat >= 80 + thin_mentions/public_only_unconfirmed
  -> token_watch or blocked_low_information

heat >= 80 + quality/propagation/tradeability/timing all pass
  -> eligible for trade_candidate
```

## 8. 数据模型

### 8.1 pulse_agent_jobs

用途：异步触发 PulseThesisAgent。

```sql
CREATE TABLE pulse_agent_jobs (
  job_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL,
  candidate_type TEXT NOT NULL,
  subject_key TEXT NOT NULL,
  target_type TEXT,
  target_id TEXT,
  "window" TEXT NOT NULL,
  scope TEXT NOT NULL,
  trigger_signature TEXT NOT NULL,
  timeline_signature TEXT NOT NULL,
  priority BIGINT NOT NULL,
  status TEXT NOT NULL,
  attempt_count BIGINT NOT NULL DEFAULT 0,
  max_attempts BIGINT NOT NULL DEFAULT 3,
  next_run_at_ms BIGINT NOT NULL,
  cooldown_until_ms BIGINT NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  UNIQUE(candidate_id)
);
```

`trigger_signature` 和 `timeline_signature` 是防重复触发的核心。

### 8.1.1 Trigger Signature

Asset-led signature：

```text
sha256(
  pulse_version,
  candidate_type,
  target_type,
  target_id,
  window,
  scope,
  latest_source_event_id,
  latest_seen_bucket,
  heat_bucket,
  opportunity_decision,
  social_phase,
  watched_confirmation_flag,
  chase_risk_flag
)
```

Source-led signature：

```text
sha256(
  pulse_version,
  candidate_type,
  source_event_id,
  subject_key,
  event_type,
  direction_hint,
  impact_bucket,
  novelty_bucket
)
```

`latest_seen_bucket` 不用精确毫秒，而用窗口 bucket：

```text
5m window -> 60s bucket
1h window -> 5m bucket
4h window -> 15m bucket
24h window -> 1h bucket
```

### 8.1.2 Timeline Signature

`timeline_signature` 来自 `PulseTimelineContextBuilder`：

```text
sha256(
  target_id,
  window,
  phase,
  selected_event_ids,
  cluster_ids,
  author_count_bucket,
  duplicate_share_bucket,
  price_change_bucket,
  risk_flags
)
```

只有 timeline materially changed 才重新跑 agent。

### 8.2 pulse_agent_runs

用途：记录 agent 审计，与 `model_runs` 平行但针对 candidate，不绑定单个 event。

```sql
CREATE TABLE pulse_agent_runs (
  run_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES pulse_agent_jobs(job_id) ON DELETE CASCADE,
  candidate_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  backend TEXT NOT NULL DEFAULT 'openai_agents_sdk',
  sdk_trace_id TEXT,
  workflow_name TEXT NOT NULL,
  agent_name TEXT NOT NULL,
  artifact_version_hash TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  output_hash TEXT,
  trace_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  usage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  latency_ms BIGINT NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  request_json JSONB NOT NULL,
  response_json JSONB,
  error TEXT,
  started_at_ms BIGINT NOT NULL,
  finished_at_ms BIGINT NOT NULL
);
```

### 8.3 pulse_candidates

用途：Signal Lab Pulse 的唯一生产读模型。

```sql
CREATE TABLE pulse_candidates (
  candidate_id TEXT PRIMARY KEY,
  candidate_type TEXT NOT NULL,
  subject_key TEXT NOT NULL,
  target_type TEXT,
  target_id TEXT,
  symbol TEXT,
  window TEXT NOT NULL,
  scope TEXT NOT NULL,
  pulse_status TEXT NOT NULL,
  verdict TEXT NOT NULL,
  social_phase TEXT NOT NULL,
  narrative_type TEXT NOT NULL,
  candidate_score DOUBLE PRECISION NOT NULL,
  score_band TEXT NOT NULL,
  trigger_signature TEXT NOT NULL,
  timeline_signature TEXT NOT NULL,
  thesis_json JSONB NOT NULL,
  radar_score_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  market_context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  gate_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  risk_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  evidence_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  agent_run_id TEXT REFERENCES pulse_agent_runs(run_id) ON DELETE SET NULL,
  pulse_version TEXT NOT NULL,
  gate_version TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL
);
```

索引：

```sql
CREATE INDEX idx_pulse_candidates_latest
  ON pulse_candidates(pulse_version, window, scope, pulse_status, updated_at_ms DESC);

CREATE INDEX idx_pulse_candidates_target
  ON pulse_candidates(target_type, target_id, updated_at_ms DESC);

CREATE INDEX idx_pulse_candidates_subject
  ON pulse_candidates(subject_key, updated_at_ms DESC);
```

### 8.6 去重和冷却

系统有三层去重。

第一层：trigger enqueue 去重。

```text
same candidate_id + same trigger_signature + same timeline_signature
  -> skip
same candidate_id + material timeline change
  -> enqueue/update pending job
same candidate_id + no material change + cooldown active
  -> skip
```

默认 agent cooldown：

```text
trade_candidate eligible token target: 5m
token_watch: 15m
theme_watch source seed: 60m
risk_rejected_high_info: 30m
blocked_low_information: 120m
```

允许绕过 cooldown 的 material changes：

- status 可能升级，例如 `token_watch -> trade_candidate`
- social phase 变化，例如 `seed -> ignition -> expansion`
- heat score 跨 bucket，例如 `70s -> 80s -> 90s`
- 新 watched-author confirmation 出现
- independent author count 增加至少 2
- chase risk 从 false 变 true
- market 从 pending/stale 变 fresh
- 新 hard risk 出现

第二层：candidate upsert 去重。

`pulse_candidates.candidate_id` 稳定，重复更新同一个候选，不制造多条 Pulse row。

第三层：notification dedup。

通知不直接由 trigger 产生，只由已经物化的 `pulse_candidates` 产生。最终靠 `notifications.dedup_key` 的唯一约束兜底。

## 8.7 Notification Signature

通知 signature 与 agent signature 分开，因为 agent 可能更新摘要，但并非每次都值得推送。

```text
notification_signature = sha256(
  pulse_version,
  candidate_id,
  pulse_status,
  score_band,
  social_phase,
  top_risk_keys,
  confirmation_trigger_keys,
  latest_evidence_event_id_bucket
)
```

通知 cooldown：

```text
trade_candidate: 15m
token_watch: 30m
theme_watch: 2h
risk_rejected_high_info: 1h
blocked_low_information: never push
```

允许突破通知 cooldown：

- `token_watch -> trade_candidate`
- `theme_watch -> token_watch`
- `token_watch -> risk_rejected_high_info` 且 risk 是 `chase_risk` / `market_stale` / `identity_ambiguous`
- 新 watched source 加入同一 candidate
- score_band 升级到 `high_conviction`

### 8.4 pulse_playbook_snapshots

用途：shadow-only 交易方案观察，不执行订单。

```sql
CREATE TABLE pulse_playbook_snapshots (
  playbook_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES pulse_candidates(candidate_id) ON DELETE CASCADE,
  target_type TEXT,
  target_id TEXT,
  horizon TEXT NOT NULL,
  decision_time_ms BIGINT NOT NULL,
  playbook_status TEXT NOT NULL,
  side TEXT NOT NULL,
  setup_json JSONB NOT NULL,
  confirmation_json JSONB NOT NULL,
  invalidation_json JSONB NOT NULL,
  risk_json JSONB NOT NULL,
  entry_market_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  playbook_version TEXT NOT NULL,
  outcome_status TEXT NOT NULL DEFAULT 'pending',
  created_at_ms BIGINT NOT NULL,
  UNIQUE(candidate_id, horizon, playbook_version)
);
```

`side` 只允许：

```text
LONG_BIAS
RISK_OFF
OBSERVE_ONLY
FLAT
```

### 8.5 pulse_playbook_outcomes

```sql
CREATE TABLE pulse_playbook_outcomes (
  playbook_id TEXT PRIMARY KEY REFERENCES pulse_playbook_snapshots(playbook_id) ON DELETE CASCADE,
  settled_at_ms BIGINT NOT NULL,
  actual_return DOUBLE PRECISION,
  benchmark_return DOUBLE PRECISION,
  abnormal_return DOUBLE PRECISION,
  max_favorable_excursion DOUBLE PRECISION,
  max_adverse_excursion DOUBLE PRECISION,
  confirmation_hit BOOLEAN NOT NULL DEFAULT false,
  invalidation_hit BOOLEAN NOT NULL DEFAULT false,
  outcome_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at_ms BIGINT NOT NULL
);
```

## 9. Candidate Score

`candidate_score` 不是概率，不显示 `%`。

组成：

```text
social_strength
discussion_quality
propagation_quality
tradeability
timing
agent_confidence
historical_credit
freshness_decay
risk_penalty
```

score band：

```text
high_conviction
watch
speculative
blocked
```

UI 显示 band，不把分数包装成 hit rate。

## 10. Pulse API

路径保留：

```text
GET /api/signal-lab/pulse
```

请求参数：

```text
window=5m|1h|4h|24h
scope=all|matched
status=trade_candidate|token_watch|theme_watch|risk_rejected_high_info
handle=cz_binance,heyi
q=grok,bnb
limit=50
cursor=...
```

响应：

```json
{
  "ok": true,
  "data": {
    "query": {
      "window": "1h",
      "scope": "all",
      "status": null,
      "handle": null,
      "q": null
    },
    "health": {
      "pulse_ready": true,
      "agent_worker_running": true,
      "candidate_count": 8,
      "blocked_low_information_count": 12,
      "dead_job_count": 0,
      "market_ready_rate": 0.91,
      "settlement_coverage": 0.74
    },
    "summary": {
      "trade_candidate": 2,
      "token_watch": 4,
      "theme_watch": 1,
      "risk_rejected_high_info": 1,
      "blocked_low_information": 12
    },
    "items": [
      {
        "candidate_id": "pulse:...",
        "candidate_type": "token_target",
        "pulse_status": "token_watch",
        "score_band": "watch",
        "symbol": "PEPE",
        "subject_key": "target:CexToken:cex-token:PEPE",
        "title": "PEPE ignition after watched-source confirmation",
        "summary_zh": "PEPE 社交热度显著上升，但当前仍需确认独立作者扩散是否持续。",
        "why_now_zh": "5m heat 突破阈值，且 watched source 出现直接证据。",
        "social_phase": "ignition",
        "narrative_type": "direct_token",
        "confirmation_triggers_zh": ["新增独立作者继续扩散", "价格未先于社交大幅拉升"],
        "invalidation_triggers_zh": ["后续只剩重复文案", "价格已进入 chase"],
        "top_risks": ["public_stream_coverage"],
        "source_event_ids": ["event-1"],
        "evidence_event_ids": ["event-1"],
        "updated_at_ms": 1778240000000
      }
    ],
    "returned_count": 1,
    "has_more": false,
    "next_cursor": null
  }
}
```

## 11. Frontend 信息预算

Pulse row 只显示：

- status
- symbol 或 subject
- why now
- social phase
- score band
- top risks
- confirmation / invalidation 摘要
- updated time

Inspector 显示：

- thesis JSON 中的 bull/bear case
- source event IDs
- raw tweet text
- radar score blocks
- market context
- playbook/horizon/outcome

不展示：

- old kind labels
- low_signal
- raw lifecycle chains
- NO_TRADE
- missing_market rows as ordinary candidates

## 12. 运行时

`PulseCandidateWorker` 周期：

```text
1. scan token_radar_rows for asset-led triggers
2. scan social_event_extractions for source-led triggers
3. build PulseTimelineContext for each trigger
4. compute trigger_signature and timeline_signature
5. apply enqueue dedupe and cooldown
6. claim and run PulseThesisAgent
7. validate output and guardrail text
8. run PulseCandidateGate
9. upsert pulse_candidates
10. build pulse_playbook_snapshots for watch/trade/risk rows
11. settle due playbooks
12. update pulse health
```

`PulseCandidateWorker` 可以与当前 `EnrichmentWorker` 共用 OpenAI API key/model，但必须有独立 job table、run table、prompt version 和 schema version。

## 12.1 Notification Runtime

新增通知规则：

```text
signal_pulse_candidate
```

它读取 `pulse_candidates`，而不是读取 trigger jobs 或 raw radar rows。

通知生成顺序：

```text
pulse_candidates
  -> SignalPulseNotificationRule
  -> NotificationCandidate
  -> notifications(dedup_key unique)
  -> notification_deliveries
  -> in_app / apprise / pushdeer
  -> websocket notification event
```

通知 severity：

```text
trade_candidate -> critical
token_watch -> high
theme_watch -> warning
risk_rejected_high_info -> high
blocked_low_information -> no notification
```

通知 body 必须包含：

- status
- symbol/subject
- why now
- social phase
- top risks
- confirmation triggers
- invalidation triggers
- evidence event ids
- link target metadata

通知 dedup key：

```text
signal_pulse_candidate:{candidate_id}:{notification_signature_bucket}
```

`notification_signature_bucket` 根据 status cooldown 生成：

```text
bucket = updated_at_ms // cooldown_ms_for_status
```

如果 status 升级，dedup key 必须变化，允许立即推送。

## 13. 版本

```text
PULSE_VERSION = signal-pulse-v2-agent-thesis
THESIS_SCHEMA_VERSION = pulse_thesis_v1
PROMPT_VERSION = pulse-thesis-agents-sdk-v1
GATE_VERSION = pulse-candidate-gate-v1
PLAYBOOK_VERSION = shadow-playbook-v1
```

旧版本不参与生产 Pulse 查询。

## 14. 验收

Backend:

- `TradingAttentionService` 文件不存在。
- `tests/test_trading_attention_service.py` 文件不存在。
- `/api/signal-lab/pulse` 不导入 `TradingAttentionService`。
- `/api/signal-lab/pulse` 只读取 `pulse_candidates`。
- `pulse_candidates` 没有 row 时返回生产空态和 health，不从旧 tables 拼装。
- `blocked_low_information` 不进入普通 `items`。
- `theme_watch` 可以来自 Musk/CZ/HeYi 无 token 推文。
- `trade_candidate` 必须来自 resolved token target。

Frontend:

- `TradingAttention*` 类型不存在。
- `SignalLabPulse` 使用 `SignalPulseData`。
- `SignalLabWorkbench` 使用 status filters，不使用 kind filters。
- `SignalLabInspector` 使用 `SignalPulseItem`。
- UI 不显示 Direct token / Topic heat / Ecosystem / Structure / Risk 作为旧 category grid。

Tests:

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
npm test -- --run src/components/SignalLabPulse.test.tsx src/App.test.tsx
```
