# Spec — Pulse 1h/4h Research Committee Hard Cut

**Status**: Draft, awaiting review
**Date**: 2026-05-20
**Owner**: Qinghuan / Codex
**Related**:
- `docs/ARCHITECTURE.md`
- `docs/CONTRACTS.md`
- `docs/WORKERS.md`
- `docs/WORKFLOW.md`
- `src/parallax/domains/pulse_lab/ARCHITECTURE.md`
- `docs/superpowers/specs/completed/2026-05-14-pulse-detail-redesign-cn.md`
- `/Users/qinghuan/Documents/code/TradingAgents`

## Background

Pulse Agent 当前是一个从 Token Radar read model 取最新 rows、生成 sealed evidence packet、
再让 agent 做有限判断的单服务链路。`PulseCandidateWorker.run_once_async` 每轮先 scan
再 process，scan 时按配置的 `windows` 和 `scopes` 遍历，并对每个
`(window, scope)` 调 `repos.token_radar.latest_rows(..., limit=self.batch_size)`：
`src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:128-173`。
默认配置仍包含 `5m, 1h, 4h, 24h`，且每轮 `batch_size=10`、
`max_enqueues_per_cycle=25`：
`src/parallax/platform/config/settings.py:720-731` 和
`src/parallax/platform/config/settings.py:1508-1522`。

HTTP 和前端也默认把 Signal Lab Pulse 放在 5m。后端
`/api/signal-lab/pulse` 默认 `window="5m"`、`scope="all"`：
`src/parallax/app/surfaces/api/routes_pulse.py:21-35`。前端 compact query
写死 `SIGNAL_LAB_COMPACT_WINDOW = "5m"`：
`web/src/features/signal-lab/api/useSignalLabCompactQuery.ts:7-23`。Signal Lab route
state 也默认 `window: "5m"`：
`web/src/features/signal-lab/state/signalLabRouteState.ts:12-18`。

当前触发门槛会让单个 watched author 进入 Pulse。`_is_asset_trigger` 只要
`watched_mentions > 0` 就返回 true：
`src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:427-437`。
Token Radar factor gate 对独立来源不足的阻断也有 watched author 例外：
`independent_sources < 2 and watched_mentions <= 0` 才 block，
`credible_sources < 1.5 and watched_mentions <= 0` 才 block：
`src/parallax/domains/token_intel/scoring/factor_snapshot.py:348-361`。
这意味着 1 个 watched author 可以绕过“独立作者不足”的公共信号限制。

Pulse 的 public surface 还把 `risk_rejected_high_info` 作为默认公共状态之一。
`SignalPulseService` 的 summary/status 集合包含 `risk_rejected_high_info`，displayable
状态包含 `display_risk_rejected_high_info`：
`src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py:9-18`。
读库查询也把 `display_risk_rejected_high_info` 纳入 public display SQL：
`src/parallax/domains/pulse_lab/repositories/pulse_read_repository.py:13-18`。
因此单作者 watched row 即使被 agent 判为 ignore，也可能以“高信息但被拒绝”的形式
占据默认候选列表。

另一处结构性 stale 问题在 Pulse edge diff。`build_pulse_edge_state` 已经把
`trigger_signature` 和 `timeline_signature` 放入 observed state：
`src/parallax/domains/pulse_lab/services/pulse_edge_events.py:35-60`。
但 `diff_pulse_edge_events` 只比较版本、状态、score band、hard risks、
recommended decision 和 watched confirmation，并不比较 timeline/trigger signature：
`src/parallax/domains/pulse_lab/services/pulse_edge_events.py:63-84`。
如果新帖子、新作者或新 selected evidence 进入，但 score/status bucket 没变，
admission policy 会收到空 edge events 并 suppress 为 `unchanged`：
`src/parallax/domains/pulse_lab/services/pulse_admission_policy.py:28-48`。

Agent runtime 目前是两段 tool-free pipeline：`evidence_debate` 和 `decision_maker`。
`runtime_contract` 明确 stage names 为这两段，并且每段 `tool_names_by_stage=()`：
`src/parallax/integrations/openai_agents/pulse_decision_agent_client.py:99-113`。
run pipeline 先跑 evidence debate，再校验 refs，然后跑 decision maker：
`src/parallax/integrations/openai_agents/pulse_decision_agent_client.py:147-219`。
这个设计是安全的，但它更接近 sealed-packet summarizer，而不是 TradingAgents 那种
多源、多角色、带反方和风险管理的研究流程。

TradingAgents 的核心差异是 graph-level committee。它在 setup 中创建 market/social/news/
fundamentals analysts、Bull/Bear researchers、Research Manager、Trader、Aggressive/
Neutral/Conservative risk analysts 和 Portfolio Manager：
`/Users/qinghuan/Documents/code/TradingAgents/tradingagents/graph/setup.py:49-112`。
它把 analysts 串行连接到 Bull/Bear debate，再到 trader 和 risk debate：
`/Users/qinghuan/Documents/code/TradingAgents/tradingagents/graph/setup.py:114-184`。
debate/risk loops 有明确 round cap：
`/Users/qinghuan/Documents/code/TradingAgents/tradingagents/graph/conditional_logic.py:46-67`。
它还在 sentiment analyst 中预取 news、StockTwits、Reddit 三类数据后再调用 LLM，避免
prompt 要求社交分析但没有社交事实时模型编造：
`/Users/qinghuan/Documents/code/TradingAgents/tradingagents/agents/analysts/sentiment_analyst.py:1-18`
和
`/Users/qinghuan/Documents/code/TradingAgents/tradingagents/agents/analysts/sentiment_analyst.py:52-90`。
TradingAgents 还在每次 run 前解析历史 pending outcome、生成 reflection 并注入后续状态：
`/Users/qinghuan/Documents/code/TradingAgents/tradingagents/graph/trading_graph.py:254-304`
和
`/Users/qinghuan/Documents/code/TradingAgents/tradingagents/graph/trading_graph.py:332-339`。

2026-05-20 真实运行配置已确认来自 operator-owned path：
`/Users/qinghuan/.parallax/config.yaml` 和
`/Users/qinghuan/.parallax/workers.yaml`。以下诊断基于真实 DB，不使用 repo
fixture。当前 Token Radar projection version 为 `token-radar-v13-social-attention`。

最新 projection 中 `rank <= 50` row 集合显示，5m 明显比 1h/4h 更单作者、更高集中度：

| Window / scope | Rows | p50 authors | Single-author rows | >=3-author rows | High-concentration rows | Watched rows | Avg mentions |
|---|---:|---:|---:|---:|---:|---:|---:|
| 5m / all | 24 | 1.0 | 22 | 1 | 22 | 1 | 1.2 |
| 5m / matched | 1 | 1.0 | 1 | 0 | 1 | 1 | 3.0 |
| 1h / all | 70 | 2.0 | 20 | 34 | 23 | 10 | 3.6 |
| 1h / matched | 10 | 1.0 | 9 | 0 | 9 | 10 | 1.5 |
| 4h / all | 100 | 2.0 | 50 | 50 | 51 | 8 | 6.6 |
| 4h / matched | 17 | 1.0 | 15 | 0 | 16 | 17 | 1.6 |

过去 4 小时 Pulse candidates 和 runs 也显示 5m/all 产出更像噪音队列：

- `5m/all`: 31 个 `display_risk_rejected_high_info`，17 个 `hidden_invalid_output`，
  8 个 `hidden_insufficient_evidence`，只有 1 个 `display_trade_candidate`。
- `1h/all`: 10 个 `display_trade_candidate`，6 个 `display_token_watch`，
  6 个 `display_risk_rejected_high_info`。
- `4h/all`: displayable 数量偏少，但这是 edge diff stale 和 backpressure 共同造成的，
  不是 4h/all 没有多作者数据。
- 最近 4 小时 `5m/all` runs 有 35 个 `display_risk_rejected_high_info`、27 个
  `unexpected_exception`、22 个 `backpressure_circuit_open`，只有 1 个
  `display_trade_candidate`。

## Problem

Pulse 当前默认面向 5m 和 matched/watched 触发，用户看到的是高 churn、单作者、高热账号
或被拒绝候选；真正更有参考价值的 1h/4h 多作者扩散信号没有成为默认研究对象，并且会被
edge diff 的 `unchanged` suppress 变 stale。结果是 Signal Lab Pulse 像短线热度噪音流，
不是一个能帮助研究员判断“是否值得继续研究/交易”的中周期研究队列。

## First Principles

1. **Pulse Agent 是研究队列，不是 tick feed。** 5m 对 GMGN/Twitter 原始观察有价值，
   但不足以作为 agent 默认判断周期。Pulse 的公共候选必须建立在 1h/4h 这类有扩散时间、
   有作者去重空间、有市场确认窗口的 horizon 上。
2. **Public candidate 必须要求独立扩散。** Watched author 是线索来源，不是独立确认。
   单 watched author 可以触发 watchlist alert，但不能绕过 independent authors /
   credible authors gate 成为默认 public trade/watch candidate。
3. **LLM 只能解释 sealed facts，不能补事实。** TradingAgents 的启发不是让 Pulse 在运行时
   任意调用外部工具，而是在 sealed packet 已经包含的 DB facts 上做角色拆分、反方约束和
   风险裁决。
4. **Kappa/CQRS 和 one-writer invariant 不变。** `PulseCandidateWorker` 仍是
   `pulse_agent_jobs`、`pulse_agent_runs`、`pulse_candidates` 等 Pulse read models 的
   runtime writer。新增 committee 行为不得引入第二个 writer 或 API 写入业务事实。

## Goals

- **G1 — Hard cut 5m from Pulse Agent admission.** Pulse Agent 不再扫描、enqueue、process
  或公开展示 `5m` horizon candidates。`5m` 可以继续作为 Token Radar/原始观察窗口存在，
  但不再是 Signal Lab Pulse agent 的 admission window。
- **G2 — Make 1h/4h the only primary Pulse horizons.** Pulse public API、frontend defaults、
  worker config 和 health 均以 `1h`、`4h` 为合法 primary windows。默认 discovery view 为
  `4h/all`，`1h/all` 作为 early-confirmation view。
- **G3 — Remove standalone 24h Pulse jobs.** `24h` 不再单独触发 Pulse Agent jobs。24h
  只作为 context feature 出现在 packet 中，例如 baseline、prior mentions、staleness 或
  outcome evaluation，不作为 public Pulse horizon。
- **G4 — Separate discovery from matched/watchlist alerts.** `scope=all` 是 discovery
  lane。`scope=matched` 是 watchlist/context lane；matched-only 单作者 row 不得进入默认
  public trade/watch list。需要展示时用明确的 `watchlist_alert`/alert rail，而不是混在
  discovery candidates 中。
- **G5 — Enforce independent diffusion for public trade/watch.** `display_trade_candidate`
  和 `display_token_watch` 必须满足至少 2 个 independent authors，或一个更严格的
  “watched seed + public corroboration”规则。`watched_mentions > 0` 不再绕过 social source
  gate。
- **G6 — Stop publishing single-author risk rejects by default.** 单作者、high-concentration
  或 matched-only 的 `risk_rejected_high_info` 不再进入默认 candidate list。风险拒绝仍可在
  audit/debug filter 中查看，但不能占据默认研究队列。
- **G7 — Treat material evidence changes as admission edges.** `timeline_signature` 和
  `trigger_signature` 变化必须能产生 material edge event，但要由 horizon-specific debounce
  约束，避免 1h/4h 因每条小变化无限重跑。
- **G8 — Replace two-stage Pulse with a bounded research committee.** 参考 TradingAgents，
  Pulse Agent 改为 packet-only committee：Signal Analyst -> Bear Case -> Risk/Portfolio
  Judge。每段最多 1 turn，无工具调用，所有 claim 必须引用 sealed packet refs。
- **G9 — Add historical evaluation before shipping threshold changes.** 实现前必须产出
  evaluation report，对比 current vs proposed policy 在最近真实数据上的候选量、作者分散度、
  churn、失败率、market freshness 和 outcome proxy。
- **G10 — Preserve operational boundedness.** 1h/4h 各自有 scan/enqueue/run budget 和
  health counters。移除 5m 后释放的 capacity 必须优先补给 1h/4h，而不是被 matched-only
  alerts 吃掉。

## Non-goals

- 不删除 Token Radar 的 5m projection，也不删除其他页面使用的 5m 观察窗口。
- 不把 Pulse Agent 改成可自由联网、可调用任意外部工具的 TradingAgents clone。
- 不承诺输出交易指令；Pulse 仍输出 research decision / candidate status / risk notes。
- 不在本 spec 内重做 Token Radar scoring、identity resolver、market tick ingestion 或
  narrative digest pipeline。
- 不新增前端大改版；本 spec 只要求 Signal Lab Pulse 的默认窗口、filter、badge 和列表语义
  对齐新 policy。
- 不保留 5m Pulse runtime compatibility path。已有 5m 历史 candidates 可以作为历史记录存在，
  但新 run 不再生成 5m Pulse candidates。

## Target Architecture

目标架构保留 `PulseCandidateWorker` 单 writer，但把它分成三个清晰 policy 层：

```text
Token Radar rows
  -> PulseHorizonPolicy
  -> PulseDiscoveryAdmission
  -> PulseResearchPacketBuilder
  -> Packet-only Research Committee
  -> ClaimEvidenceVerifier / RecommendationClipper / WriteGate
  -> pulse_candidates
```

**PulseHorizonPolicy**

- Primary windows: `1h`, `4h`.
- Context-only windows: `24h` where available.
- Excluded from Pulse Agent: `5m`.
- Discovery scope: `all`.
- Alert/context scope: `matched`.

**PulseDiscoveryAdmission**

Admission 只为 `1h/all` 和 `4h/all` 生成 public candidate jobs。
`matched` rows 可以作为 packet context 和 watchlist alerts，但不能单独成为 default public
candidate，除非同一 target 在 `all` scope 内也满足 independent diffusion gate。

**PulseResearchPacketBuilder**

Packet 仍是 sealed facts。它必须包含：

- 1h social diffusion facts；
- 4h social diffusion facts；
- matched/watched context；
- 24h baseline context；
- market freshness and liquidity context；
- source concentration facts；
- prior Pulse candidate/run summary when available；
- all evidence refs required by committee stages。

**Packet-only Research Committee**

Committee 不新增外部 tools。它只把当前两段 agent 拆成更像 TradingAgents 的职责：

1. `signal_analyst`: 只回答“bull case / why surfaced / what changed”，必须引用
   social、market、identity、timeline refs。
2. `bear_case`: 专门找作者集中、重复文本、market stale、liquidity、timing chase、
   single-source dependency 和 missing facts。
3. `risk_portfolio_judge`: 合并 analyst 与 bear case，输出 final recommendation、
   confidence ceiling、public display eligibility 和 invalidation conditions。

后续 `claim_verifier`、`recommendation_clipper`、`deterministic_eval`、`write_gate` 继续保留。
LLM committee 不得越过 deterministic gate；deterministic gate 可以继续 downgrade 或 hide。

## Conceptual Data Flow

```text
token_radar_rows(1h/all, 4h/all)
  + token_radar_rows(1h/matched, 4h/matched as context)
  + 24h factor context
    -> horizon admission
    -> diffusion/public-quality gate
    -> sealed research packet
    -> signal_analyst
    -> bear_case
    -> risk_portfolio_judge
    -> verifier / clipper / write gate
    -> Signal Lab Pulse public read model
```

Changed arrows:

- `token_radar_rows(5m/*) -> Pulse Agent` is removed.
- `matched -> public candidate` becomes `matched -> context/watchlist alert`.
- `timeline_signature -> unchanged suppress` becomes `timeline_signature -> material evidence edge`
  when horizon-specific thresholds are met.
- `two-stage agent -> final decision` becomes `committee stages -> final decision`, still packet-only.

No API route writes facts. No new runtime service owns `pulse_candidates`.

## Core Models

**PulseHorizonPolicy**

Semantic config that defines allowed Pulse agent horizons and context horizons:

- `primary_windows = ("1h", "4h")`
- `context_windows = ("24h",)`
- `excluded_windows = ("5m",)`
- `default_public_window = "4h"`
- `early_confirmation_window = "1h"`

**PulseSourceQuality**

Derived quality facts used before public display:

- `independent_author_count`
- `source_weighted_effective_authors`
- `top_author_share`
- `duplicate_text_share`
- `watched_mentions`
- `matched_only`
- `public_corroboration_seen`
- `single_author_dependency`

Invariant: watched mentions can improve priority or context, but cannot reduce the independent source
requirement for default public trade/watch display.

**PulseMaterialEvidenceEdge**

Edge event emitted when evidence changed enough to justify a new agent run:

- `timeline_evidence_changed`
- `trigger_evidence_changed`
- `independent_author_added`
- `source_quality_regressed`
- `market_freshness_changed`

The plan must define exact debounce thresholds, but the semantic rule is: source facts changing inside
1h/4h can no longer be suppressed solely because score band and status stayed in the same bucket.

**PulseCommitteeRun**

Agent run with ordered stages:

- `signal_analyst`
- `bear_case`
- `risk_portfolio_judge`
- existing deterministic stages after the LLM stages

Each LLM stage has:

- `stage_name`
- `input_hash`
- `output_hash`
- `allowed_ref_ids`
- `cited_ref_ids`
- `confidence`
- `data_gaps`
- `latency_ms`
- `status`

**WatchlistAlert**

Non-default public surface for matched-only or watched-only triggers. It can share the same underlying
candidate/audit storage if the plan can keep contracts clean, but semantically it is not a discovery
trade/watch candidate.

**PulseEvaluationReport**

Generated artefact under `docs/generated/` before implementation verification. It compares current and
proposed policies against real DB data and records:

- horizon distribution;
- author concentration;
- public candidate mix;
- hidden/invalid/failure rates;
- candidate churn;
- market freshness;
- outcome proxy by horizon where market data permits.

## Interface Contracts

**Worker config**

- `pulse_candidate.windows` accepts only `["1h", "4h"]` for agent admission.
- `pulse_candidate.scopes` may remain `["all", "matched"]`, but `matched` is context/alert only.
- `stale_job_ttl_by_window_seconds` must not contain a `5m`-only special case after the hard cut.
- Runtime config docs/examples must not advertise 5m Pulse Agent admission.

**HTTP `/api/signal-lab/pulse`**

- Default query becomes `window=4h&scope=all`.
- Valid Pulse windows become `1h | 4h`.
- `window=5m` and `window=24h` return `invalid_window` for this endpoint after the hard cut.
- `scope=matched` is allowed only as an alert/context view and must expose that semantic in response
  metadata, for example `lane: "watchlist_alert"` or equivalent.
- Default `status=all` excludes single-author `display_risk_rejected_high_info`. A specific
  risk/debug filter may include them.

**Signal Lab frontend**

- Signal Lab default route becomes `window=4h&scope=all`.
- Compact overview uses `4h/all` for primary count and may show `1h/all` as early confirmation.
- Pulse window controls show only `1h` and `4h`.
- Matched/watchlist rows are visually separated from discovery candidates.
- Candidate cards expose independent author count, top author share, and watched-only/matched-only badge.

**Agent stage contract**

- Public detail response exposes new committee stages by name.
- Old `evidence_debate` / `decision_maker` names are removed from new runs after the version bump.
- Stage outputs must be ref-checked. Unknown evidence refs produce deterministic abstain/hide, not
  public display.

**Health**

Pulse health must report at least:

- per-window scan/enqueue/run counts for `1h` and `4h`;
- rejected 5m request count, if tracked;
- matched-only alert count;
- public candidate count by window;
- single-author suppressed count;
- material evidence suppress/enqueue counts;
- committee stage failure counts.

## Evaluation Plan

The implementation plan must start with an offline evaluator before changing production defaults.
The evaluator can run read-only SQL and pure Python against the live DB using the confirmed
operator-owned config path. It must not print secrets.

### Baseline Metrics

For current policy and proposed policy, compute:

- rows admitted by `window/scope`;
- author distribution: p50/p75 independent authors, single-author ratio, top-author-share buckets;
- watched-only ratio;
- public display mix: trade/watch/risk-rejected/hidden/invalid;
- agent failure mix: timeout, unexpected_exception, unknown evidence ref, backpressure;
- median age of public candidates;
- churn: candidates entering/leaving top N over 15m, 30m, 60m, 4h;
- market freshness: fresh/stale/missing by route;
- outcome proxy where available: price return and max adverse excursion at +15m, +1h, +4h, +24h.

### Success Thresholds

- 5m creates zero new Pulse Agent jobs after rollout.
- Default Signal Lab Pulse list contains zero single-author trade/watch candidates.
- Default Signal Lab Pulse list excludes matched-only risk rejects.
- At least 80% of displayed trade/watch candidates in `1h/all` and `4h/all` have
  `independent_author_count >= 2`.
- `4h/all` fresh multi-author rows are not suppressed as `unchanged` when timeline/source facts
  materially change.
- Agent invalid-output rate is lower than the current 5m/all baseline.
- Backpressure is lower than current baseline or explicitly explained by committee-stage capacity.

### Report Output

The evaluator must write a report under:

```text
docs/generated/pulse-1h-4h-research-committee-evaluation-YYYY-MM-DD.md
```

The report must include the exact SQL/Python command used, redacted config path confirmation, summary
tables, and a short recommendation: ship, revise thresholds, or stop.

## Acceptance Criteria

- **AC1.** WHEN `pulse_candidate` starts after the hard cut THEN it SHALL not scan, enqueue, process,
  or create agent jobs for `window='5m'` or `window='24h'`.
- **AC2.** WHEN a client calls `/api/signal-lab/pulse?window=5m` THEN the API SHALL reject it with
  `invalid_window` for the Pulse endpoint.
- **AC3.** WHEN Signal Lab loads without URL params THEN the UI SHALL request `4h/all`, not `5m/all`.
- **AC4.** WHEN a row has `watched_mentions > 0` but fewer than 2 independent authors and no public
  corroboration THEN it SHALL not be displayed as `display_trade_candidate` or `display_token_watch`.
- **AC5.** WHEN a matched-only single-author row is processed THEN it SHALL be classified as
  watchlist/context/audit state, not default discovery candidate.
- **AC6.** WHEN a `1h/all` or `4h/all` target receives material new source evidence while score band
  is unchanged THEN Pulse admission SHALL emit a material edge or record an explicit debounce reason;
  it SHALL not silently suppress as generic `unchanged`.
- **AC7.** WHEN a new Pulse Agent run completes THEN its stage audit SHALL include
  `signal_analyst`, `bear_case`, and `risk_portfolio_judge` outputs, with ref validation.
- **AC8.** WHEN committee output cites an unknown evidence ref THEN write gate SHALL hide/abstain the
  candidate and record the failure reason.
- **AC9.** WHEN historical evaluation is run THEN it SHALL produce the `docs/generated/...evaluation`
  report before production defaults are changed.
- **AC10.** WHEN the rollout is verified against live DB THEN there SHALL be zero new 5m Pulse jobs
  created after the deployment timestamp.

## Risks

| Risk | Severity | Mitigation |
|---|---:|---|
| Removing 5m misses very early moves | Medium | Keep 1h/all as early-confirmation lane; 5m remains available in Token Radar/raw observation, but not public Pulse Agent. |
| 1h/4h default feels slower | Medium | Surface candidate freshness, material evidence changes, and 1h early lane beside 4h conviction lane. |
| Committee adds latency/cost | High | Three stages, one turn each, no tools; per-window budgets and health counters required. |
| Timeline signature edge causes rerun churn | Medium | Horizon-specific material thresholds and debounce reasons required in plan/tests. |
| Matched users lose a useful feed | Medium | Preserve matched as watchlist alert/context lane, visually separate from discovery candidates. |
| Historical 5m links break | Low | Existing candidate detail by id can remain readable; list/query endpoint rejects new 5m window. |
| Public list becomes too sparse | Medium | Evaluation report must quantify candidate count before rollout; thresholds can be revised before implementation approval. |
| Full TradingAgents clone overfits equities workflow | Medium | Copy only the role pattern: analyst, skeptic, risk judge. Do not copy external tool graph or portfolio trading semantics. |

## Evolution Path

After this hard cut, Pulse can evolve in three directions without reopening the 5m default:

1. Add outcome memory similar to TradingAgents reflection, using existing Pulse playbook/outcome storage
   where possible.
2. Add external source collectors only as upstream facts/read models, never as free-form agent tools.
3. Add a separate real-time watchlist alert rail for 5m/matched operator attention, clearly labeled as
   alerts rather than research candidates.

The design should not foreclose a future 24h context summary, but 24h should remain context/evaluation
until it proves useful as a primary public horizon.

## Alternatives Considered

- **Tune 5m thresholds only.** Rejected because live DB shows 5m is structurally single-author and
  high-concentration. Raising thresholds may reduce volume but does not create independent diffusion.
- **Only change the frontend default to 4h.** Rejected because worker capacity, API defaults,
  admission edge suppressions and watched-author bypass would continue generating noisy 5m/matched
  candidates behind the scenes.
- **Adopt full TradingAgents graph.** Rejected because Pulse must stay sealed-packet, DB-facts-first,
  and operationally bounded. The useful part is committee structure, not open-ended tool use.
- **Use 24h as primary horizon.** Rejected for now because 24h is better as baseline/context; primary
  Pulse research should stay close enough to current market/social flow to be actionable.
- **Keep matched as public candidate lane.** Rejected because current data shows matched is mostly
  watched-only single-author flow. It should be an alert/context lane until corroborated by all-scope
  diffusion.

## Boundaries

| Class | Behaviour |
|---|---|
| Always | Pulse Agent primary admission uses `1h/all` and `4h/all`; default Signal Lab Pulse uses `4h/all`; public trade/watch requires independent diffusion; committee stages are packet-only and ref-checked. |
| Ask first | Adding external data providers, creating new DB tables, exposing 5m as a separate alert product, changing Token Radar scoring weights, or changing trading/outcome semantics. |
| Never | Generate new 5m Pulse Agent jobs, let watched_mentions bypass independent-source public display, publish single-author matched-only rows as default trade/watch candidates, allow agent claims without packet refs, or add a second writer for Pulse read models. |
