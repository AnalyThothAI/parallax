# Signal Pulse Agent Harness v3 硬切 Spec

**Status**: Draft
**Date**: 2026-05-17
**Owner**: Codex with Qinghuan
**Related**:

- Supersedes `docs/superpowers/specs/active/2026-05-16-pulse-agent-desk-redesign-cn.md` for Agent Harness, decision contract, grader, and public stage surface.
- Composes with `docs/superpowers/specs/active/2026-05-17-pulse-control-plane-architecture-cn.md` for admission, budget, failure circuit, and notification control. If the two specs conflict, this v3 spec owns agent correctness and public write semantics; the control-plane spec owns enqueue and external-push throttling.
- Retires the agent-runtime assumptions in `docs/superpowers/specs/active/2026-05-14-pulse-decision-context-narrative-cn.md`.

## Background

`gmgn-twitter-intel` 的全局架构已经选对了方向：PostgreSQL material facts 是业务真相，Signal Pulse 只是一个 rebuildable read model；架构文档明确要求没有 runtime compatibility layer，hard cut 后 public API 和 frontend 不允许 fallback 到旧字段，见 `docs/ARCHITECTURE.md:70`。同一份文档还要求每个 Signal Pulse 决策必须能从 `pulse_agent_runs` 和 `pulse_agent_run_steps` replay，数据不足时必须 abstain，而不是发明 confidence 或 display status，见 `docs/ARCHITECTURE.md:84`。

当前 Pulse runtime 已经集中在 `pulse_lab`：`docs/ARCHITECTURE.md:211` 描述了 deterministic route policy、pre-LLM hard block、Pulse worker 调用 `PulseDecisionProvider`；`docs/ARCHITECTURE.md:220` 把 OpenAI-specific stage execution 限定在 `integrations/openai_agents/`；`docs/ARCHITECTURE.md:227` 把 `pulse_candidates.decision_*` 和 `decision_json` 定义为 public decision source。

`pulse_lab` 局部架构目前是 v2 两阶段：`investigator -> decision_maker` 加 `research_only_gate`，见 `src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md:17`。同一文档要求 Investigator 使用三个工具，并由 deterministic eval R2 `tool_calls_present` 断言非 hard-blocked run 至少调用一次工具，见 `src/gmgn_twitter_intel/domains/pulse_lab/ARCHITECTURE.md:32`。这与生产观测冲突：最近数小时的 run step 审计显示大量 `investigator` 和 `decision_maker` 成功落库，但 `tool_calls_count_delta = 0`，`input_json.tool_calls` 为空；R2 能标失败，但 worker 仍会把最终 decision 写入 `pulse_candidates`。

类型层当前只允许三类 stage：`investigator`、`decision_maker`、`research_only_gate`，见 `src/gmgn_twitter_intel/domains/pulse_lab/types/agent_decision.py:8`。`FinalDecision` 只要求 non-abstain 有 `evidence_event_ids` 或 `residual_risks`，high conviction 只要求 bull/bear strength、证据数量、archetype，见 `src/gmgn_twitter_intel/domains/pulse_lab/types/agent_decision.py:127` 和 `src/gmgn_twitter_intel/domains/pulse_lab/types/agent_decision.py:191`。这个约束能防止空 JSON，但不能证明“多空理由被证据支持”。

当前 OpenAI Agents client 的类注释假设 Investigator 会以 multi-turn 工具方式运行，并且每次工具调用会累加 `PulseToolContext.tool_calls_count`，见 `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py:139`。它确实注册了 `get_target_recent_tweets`、`get_target_price_action`、`get_official_token_profile` 三个工具，见 `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py:341`，DecisionMaker 也可选注册 fallback tweets tool，见 `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py:377`。但是工具调用摘要只是在 `_with_tool_calls` 能从 SDK result 提取到时才附加，否则原样返回输入，见 `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py:889`。因此 prompt 里的“必调”不是 runtime guarantee。

当前证据 guard 只校验 event_id 是否属于工具贡献或 worker 注入的 `evidence_event_ids/source_event_ids`，见 `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py:548` 和 `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py:852`。这能防止模型编造不存在的 event_id，但不能证明“这条 event 的文本支持了这句话”。生产样例里出现的“14 个 KOL 接力”“Binance listing 猜测”“结构健康”等，就是 citation truth 通过、claim truth 失败。

当前 worker 在 LLM 返回后会先持久化 run、step 和 eval case，然后调用 `grade_pulse_deterministic_eval_case`，但无论 eval result 是 pass 还是 fail，下一步都会 `upsert_candidate`，见 `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:572` 和 `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:593`。因此 deterministic eval 现在是 telemetry，不是 write gate。

当前 gate 已经计算 `max_recommendation`，`trade_candidate -> trade_candidate`、`token_watch -> watch`、`risk_rejected_high_info -> research`，见 `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py:123`。但 `candidate_fields_from_decision` 直接把 LLM recommendation 映射到 public `score_band`，见 `src/gmgn_twitter_intel/domains/pulse_lab/services/decision_mapping.py:16`，worker 写入时没有 deterministic clipper，见 `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:526`。这就是 `max_recommendation=research/watch` 被升级成 `watchlist/trade_candidate/high_conviction` 的根。

当前 timeline context 已经有可复用的证据包雏形：它构造 `selected_posts`、`post_clusters`、window summaries、duplicate/concentration risk flags，并给每个 selected post 附 `event_id`、author、text、role、cluster_id，见 `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_timeline_context.py:25`、`src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_timeline_context.py:201` 和 `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_timeline_context.py:429`。问题不是没有事实，而是事实没有被封装成不可绕过的 EvidencePack，也没有 claim-level verifier。

当前 public read model 默认只显示 `DISPLAY_STATUSES = {"trade_candidate", "token_watch", "risk_rejected_high_info"}`，并隐藏 `decision_recommendation = "abstain"`，见 `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py:7` 和 `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py:137`。detail stage 只返回 `investigator`、`decision_maker`、`research_only_gate`，见 `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py:82`；API schema 也固定这三个 stage，见 `src/gmgn_twitter_intel/app/surfaces/api/schemas.py:180`。

TradingAgents 的可借鉴点不是“多 agent 越多越好”。它把复杂交易流程拆成 analyst、bull/bear researcher、trader、risk、portfolio manager，见 `/Users/qinghuan/Documents/code/TradingAgents/README.md:58` 和 `/Users/qinghuan/Documents/code/TradingAgents/tradingagents/graph/setup.py:81`。更重要的是，它自己也修过同类错误：旧 social prompt 要求社交分析，但只有 Yahoo Finance news 工具，导致 LLM 编造 Reddit/X/StockTwits；新版本改成 LLM 前预取 news、StockTwits、Reddit 三类结构化数据，且不再 tool-call，见 `/Users/qinghuan/Documents/code/TradingAgents/tradingagents/agents/analysts/sentiment_analyst.py:1`、`/Users/qinghuan/Documents/code/TradingAgents/tradingagents/agents/analysts/sentiment_analyst.py:8` 和 `/Users/qinghuan/Documents/code/TradingAgents/tradingagents/agents/analysts/sentiment_analyst.py:86`。

OpenAI cookbook 的 relevant lesson 也一致：如果工具必须被调用，应该用 runtime 的 required tool choice，而不是 prompt 祈祷，见 `/Users/qinghuan/Documents/code/openai-cookbook/examples/Using_tool_required_for_customer_service.ipynb:10` 和 `/Users/qinghuan/Documents/code/openai-cookbook/examples/Using_tool_required_for_customer_service.ipynb:158`。hallucination guardrail 应逐句检查 claim，并要求 factual reference，见 `/Users/qinghuan/Documents/code/openai-cookbook/examples/Developing_hallucination_guardrails.ipynb:612` 和 `/Users/qinghuan/Documents/code/openai-cookbook/examples/Developing_hallucination_guardrails.ipynb:654`。eval flywheel 要从失败 trace 标注、量化、再改 prompt/组件，见 `/Users/qinghuan/Documents/code/openai-cookbook/examples/evaluation/Building_resilient_prompts_using_an_evaluation_flywheel.md:18`。

## Problem

Signal Pulse 现在不是“方向错”，而是 Agent Harness 的信任边界错：系统把 LLM 生成的解释当成准事实，只做 schema、event_id subset、run ledger 和事后 eval，却没有在 public write 前证明证据包存在、工具或预取事实真实发生、每个关键 claim 被原文/市场事实支持、gate max recommendation 被执行。因此 agent 会在少量或弱相关 tweet 上强行组织 bull/bear 理由，并把 research/watch 级别的候选升级成交易候选。这种失败不靠继续润色 prompt 解决，必须把事实获取、claim verification、recommendation clipping、eval write gate 变成 deterministic control path。

## First Principles

1. Facts before narrative. LLM 不产生事实，只能解释 worker 封存的 EvidencePack。EvidencePack 来自 PostgreSQL material facts 和 derived read model，不来自 agent 自己声称已查看的工具调用。这个原则延续 `docs/ARCHITECTURE.md:84` 的 audit-ledger truth 和 `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_timeline_context.py:25` 已有 timeline context。

2. Citation truth is not claim truth. `event_id` 属于白名单只说明模型没有编造 ID，不说明这条 tweet 支持“Binance listing”“14 KOL relay”“market confirmation”。每个 material claim 必须有 `ClaimEvidenceMatrix`，并被 deterministic verifier 判为 `supported` 或 `weak_supported` 后才能进入 final public decision。当前 subset guard 只覆盖 ID 级别，见 `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py:548`。

3. Public write gate beats eval telemetry. 只要 deterministic eval 或 verifier 失败，非 abstain 决策不得写入 `pulse_candidates` 的 public recommendation。当前 worker 先 grade 再无条件 `upsert_candidate`，见 `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:587` 和 `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:593`，v3 必须反转这个语义。

4. Recommendation ceiling is a hard upper bound. `pulse_candidate_gate.py` 计算出的 `max_recommendation` 是 deterministic risk policy，不是给 LLM 参考的 advisory。任何 route/gate/evidence/verifier 的 ceiling 都只能降低 public recommendation，不能被 DecisionMaker 升级。

5. Hard cut means one live contract. v3 runtime、public API、frontend、grader 只支持 v3 schema 和 v3 stage enum。历史 DB 行可以留在数据库供离线审计，但 live read path 不写 compatibility branch，不做 `legacy_skipped`，不渲染旧 stage placeholder，不保留 rollback dual-write。

## Goals

- G1. WHEN a non-hard-blocked candidate enters Pulse v3 THEN worker SHALL construct and persist an EvidencePack stage before any LLM stage; no non-abstain public decision can exist without an `evidence_pack_id` and `evidence_pack_hash`.
- G2. WHEN EvidencePack is empty, stale, target-mismatched, or below route-specific minimum quality THEN system SHALL finish the run as `abstain` or `ignore`, with no playbook and no public trading candidate.
- G3. WHEN a final decision contains material social, market, catalyst, or risk claims THEN every material claim SHALL appear in ClaimEvidenceMatrix with supporting evidence refs or metric refs; unsupported or contradicted claims SHALL be removed or force downgrade before write.
- G4. WHEN deterministic eval result is `fail` THEN `pulse_candidates` SHALL not expose the run as `watchlist`, `trade_candidate`, or `high_conviction`.
- G5. WHEN `gate.max_recommendation` is lower than LLM recommendation THEN deterministic RecommendationClipper SHALL lower the public recommendation and record the downgrade reason in the write gate audit.
- G6. WHEN `pulse_status = risk_rejected_high_info` THEN public recommendation SHALL be `ignore` or `abstain`; it SHALL NOT produce `watchlist`, `trade_candidate`, `high_conviction`, or `playbook.has_playbook=true`.
- G7. WHEN the API returns Signal Pulse detail THEN `stages` SHALL expose only v3 stage names and their v3 payloads; no `analyst`, `critic`, `judge`, legacy placeholder, or v2-only `legacy_skipped` concept appears in public runtime.
- G8. WHEN a model tries to cite evidence outside EvidencePack allowed refs THEN the run SHALL fail verifier or write gate before candidate upsert.
- G9. WHEN high conviction is emitted THEN the verifier SHALL prove route-specific high-conviction eligibility, not only count `evidence_event_ids >= 3`.
- G10. WHEN a v3 harness change lands THEN eval dataset SHALL include at least the failure modes observed in recent Signal Pulse: zero evidence/tool-equivalent context, same-author concentration, generic basket tweet cited as target proof, gate max escalation, 24h evidence used as 1h primary claim, and unsupported listing/catalyst claim.

## Non-Goals

- N1. No order execution, portfolio sizing, leverage, price targets, stop loss, take profit, or broker/exchange integration.
- N2. No full TradingAgents clone, no LangGraph migration, no 11-role debate system, no multi-model quick/deep split in v3.
- N3. No vector database or embedding memory dependency for public write correctness.
- N4. No new background worker solely for v3. The existing `pulse_candidate` worker remains the runtime owner unless a later approved plan proves it cannot hold the lifecycle.
- N5. No compatibility mode for v1/v2 public decision shapes, old stage names, old UI cards, or old grader cases.
- N6. No attempt to predict PnL in this spec. Outcome settlement hooks are included only to label future eval examples, not to claim strategy profitability.
- N7. No external HTTP calls inside agent stages. All required facts come from local PostgreSQL facts/projections or already configured domain repositories.

## Target Architecture

v3 keeps the good Kappa/CQRS spine and replaces only the unsafe Agent Harness center:

```text
Token Radar row
  -> PulseAdmissionPolicy and target/candidate budgets
  -> EvidencePackBuilder             deterministic, DB/read-model facts
  -> EvidenceCompletenessGate         deterministic, route/window quality
  -> Investigator / ClaimExtractor    LLM, reads sealed EvidencePack only
  -> ClaimEvidenceVerifier            deterministic first, optional LLM judge only for non-upgrade review
  -> SkepticRiskReviewer              bounded LLM or deterministic stage, can only downgrade
  -> DecisionMaker                    LLM, emits FinalDecisionV3 from verified claims
  -> RecommendationClipper            deterministic ceiling and high-conviction eligibility
  -> WriteGate                        deterministic eval pass required
  -> pulse_agent_runs / steps
  -> pulse_candidates public read model
  -> API / frontend / notifications
  -> eval dataset labels and future outcome loop
```

The major design move is to delete “required evidence via agent tool calls” as a correctness dependency. Pulse v3 does not require the model to call tools. It requires the worker to build `EvidencePackV3` before the model runs. Existing SQL tool implementation logic may be reused internally by `EvidencePackBuilder` as ordinary Python/query functions, but required evidence is no longer obtained through OpenAI Agents tool-calling. If a future plan reintroduces model tools, those tools are optional enrichment and cannot satisfy G1-G4 unless the runtime enforces required tool use at API level and the returned facts are folded into EvidencePack before verification.

### Component Responsibilities

| Component | Owner | Responsibility | Must not do |
|-----------|-------|----------------|-------------|
| `PulseAdmissionPolicy` | `pulse_lab/services` | Decide whether a material edge deserves a run and bound target/candidate budgets. | Read LLM output or public API state. |
| `EvidencePackBuilder` | `pulse_lab/services` | Build sealed target/window/scope evidence from `factor_snapshot`, timeline rows, selected posts, clusters, market snapshot, and profile facts. | Call LLM or external HTTP. |
| `EvidenceCompletenessGate` | `pulse_lab/services` | Fail closed when pack quality is insufficient for any non-abstain decision. | Upgrade a candidate. |
| `OpenAIAgentsPulseDecisionClient` v3 | `integrations/openai_agents` | Run LLM stages over sealed inputs and return typed domain values. | Own routing, SQL, product thresholds, or final public clipping. |
| `ClaimEvidenceVerifier` | `pulse_lab/services` | Verify material claims against pack text/metrics and mark support status. | Trust LLM citation text without checking pack refs. |
| `SkepticRiskReviewer` | `integrations/openai_agents` or deterministic service | Review only verified matrix and risk metrics; can request downgrade or abstain. | Add new bullish claims or upgrade recommendation. |
| `DecisionMaker` | `integrations/openai_agents` | Produce `FinalDecisionV3` from verified claims, route, gate, and reviewer output. | Invent new evidence or exceed max recommendation. |
| `RecommendationClipper` | `pulse_lab/services` | Enforce gate max, verifier max, route high-conviction rules, and no-playbook rules. | Ask the model for permission to downgrade. |
| `WriteGate` | `pulse_lab/runtime` | Persist public candidate only if deterministic eval and verifier pass. | Treat eval fail as telemetry-only. |
| Signal Pulse API/read model | `pulse_lab/read_models`, `app/surfaces/api` | Expose v3 decision and v3 stages only. | Synthesize old fields or render legacy stages. |

### Stage Enum v3

`pulse_agent_run_steps.stage` becomes a v3 enum:

```text
evidence_pack
evidence_completeness_gate
investigator
claim_verifier
skeptic_review
decision_maker
recommendation_clipper
write_gate
research_only_gate
```

`research_only_gate` remains only for deterministic short-circuit before LLM. It is not a compatibility stage. `investigator` remains as a name, but its semantics change: it is no longer “tool user”; it is a ClaimExtractor over an EvidencePack.

Historical rows with `analyst`, `critic`, `judge`, or v2-only `investigator/decision_maker` stage shape may remain in PostgreSQL. The v3 public runtime filters them out by harness/schema version. It does not contain code paths to grade, render, or adapt those shapes.

### Recommendation Lattice

`abstain` is not a trading recommendation; it means the system refuses judgment. For clipping, define an ordered lattice only for displayable recommendation levels:

```text
ignore < watchlist < trade_candidate < high_conviction
```

`research` is deleted as a `max_recommendation` value. If deterministic gate wants to preserve a high-information but risk-rejected observation, it uses `pulse_status = risk_rejected_high_info` plus a non-trading `public_note`, while `decision.recommendation` is clipped to `ignore` or `abstain`.

High conviction requires all of:

- `gate.max_recommendation >= high_conviction`.
- EvidencePack quality says `eligible_for_high_conviction = true`.
- Claim verifier marks all required bull claims supported and all material risk/data-gap claims represented.
- Independent author count, direct-target evidence count, market confirmation, concentration, and duplicate-text metrics meet route-specific thresholds.
- SkepticRiskReviewer does not set `max_after_review < high_conviction`.

## Conceptual Data Flow

```text
token_radar_rows
  -> scan_triggers_once
  -> PulseAdmissionPolicy
  -> pulse_agent_jobs
  -> _run_job
  -> EvidencePackBuilder
  -> evidence_pack step
  -> EvidenceCompletenessGate
  -> investigator LLM
  -> claim_verifier
  -> skeptic_review
  -> decision_maker LLM
  -> recommendation_clipper
  -> deterministic eval
  -> write_gate
  -> pulse_candidates
  -> /api/signal-lab/pulse
```

Changed arrows:

- `_run_job -> EvidencePackBuilder` is new and replaces `agent_context.selected_posts + required tool prompt` as the source of evidence.
- `investigator -> claim_verifier` is new and makes “多空理由是否成立” a first-class artifact.
- `deterministic eval -> write_gate -> pulse_candidates` changes eval from after-the-fact telemetry into a public write precondition.
- `recommendation_clipper -> pulse_candidates` enforces `gate.max_recommendation` and high-conviction eligibility after LLM output.

No new service worker is introduced because the existing `pulse_candidate` worker already owns the job lifecycle, run ledger, eval case, and `pulse_candidates` write. A new worker would add coordination risk without improving correctness.

## Core Models

### EvidencePackV3

Sealed deterministic input to all LLM stages.

Fields:

- `evidence_pack_id`: stable ID from candidate, run, window, scope, target, and source fingerprints.
- `evidence_pack_hash`: sha256 of canonical JSON.
- `schema_version`: `pulse_evidence_pack_v3`.
- `candidate_id`, `target_type`, `target_id`, `symbol`, `window`, `scope`.
- `snapshot_at_ms`, `active_window_ms`, `source_lookback_ms`.
- `source_event_ids`: all source IDs considered.
- `allowed_evidence_refs`: event refs and metric refs that LLM may cite.
- `selected_posts`: selected tweet/event items with `event_id`, `author_handle`, `author_followers`, `received_at_ms`, `age_ms`, `text`, `roles`, `cluster_id`, `direct_target_evidence`, `is_watched`, `resolution_status`, `attribution_weight`.
- `post_clusters`: cluster summaries with duplicate share, authors, representative IDs, and cluster type.
- `window_metrics`: 5m/1h/4h/24h mentions, authors, watched_mentions, top_author_share, duplicate_text_share, price_change_since_social_pct.
- `market_metrics`: latest price/liquidity/volume/holders/market cap/readiness, with `metric_ref` IDs.
- `profile_facts`: official name/symbol/twitter/website/telegram/logo/description availability; missing fields are explicit data gaps, not hidden nulls.
- `risk_flags`: author concentration, duplicate text, watched-amplified duplicate, market missing, cohort insufficient, stale market, target mismatch.
- `quality_metrics`: `direct_target_text_count`, `independent_author_count`, `watched_author_count`, `same_author_repeat_count`, `generic_basket_post_count`, `primary_window_event_count`, `primary_window_author_count`, `market_snapshot_status`, `eligible_for_high_conviction`.
- `data_gaps`: deterministic gaps.
- `excluded_posts`: posts rejected from selected evidence with reason.

Invariants:

- Every `selected_posts[*].event_id` must be in `source_event_ids`.
- Every post with `direct_target_evidence=false` may support context/risk claims, but may not support a target-specific catalyst or KOL relay claim alone.
- 1h primary claims must use events inside the 1h active window unless explicitly labeled `24h_context`.
- Generic basket tweets cannot count as independent target confirmation unless text contains direct target evidence.

### MaterialClaimV3

Atomic claim extracted from Investigator output or DecisionMaker draft.

Fields:

- `claim_id`.
- `claim_type`: `social_diffusion | kol_relay | catalyst | market_confirmation | market_divergence | profile_quality | risk_concentration | data_gap | thesis_summary`.
- `polarity`: `bull | bear | neutral`.
- `text_zh`.
- `scope_window`: `primary_window | lookback_24h | cross_window`.
- `supporting_event_ids`.
- `supporting_metric_refs`.
- `contradicting_event_ids`.
- `required_support_rule`.
- `support_status`: `supported | weak_supported | unsupported | contradicted`.
- `verifier_reason`.

Invariants:

- Every material non-summary claim must have at least one event ref or metric ref.
- Claims of `kol_relay` require independent author count after same-author and duplicate clustering.
- Claims of catalyst/listing/partnership require explicit text evidence or profile/market facts; conjecture must be labeled as conjecture and cannot support `trade_candidate` or above.
- `thesis_summary` can summarize only already supported/weak-supported claims.

### ClaimEvidenceMatrixV3

Verifier artifact connecting claims to evidence.

Fields:

- `matrix_id`, `matrix_hash`.
- `evidence_pack_id`, `run_id`.
- `claims`.
- `unsupported_claim_ids`.
- `contradicted_claim_ids`.
- `max_recommendation_from_claims`.
- `verification_status`: `pass | downgrade | fail`.

### InvestigationReportV3

LLM output from `investigator`.

Fields:

- `narrative_archetype_candidate`.
- `observation_zh`.
- `claims`: list of draft `MaterialClaimV3` without final support status.
- `bull_claim_ids`.
- `bear_claim_ids`.
- `data_gap_claim_ids`.
- `notes_for_reviewer`.

It no longer cites raw `supporting_event_ids` directly in bull/bear prose. It cites claim IDs, and claims cite evidence refs.

### SkepticReviewV3

Downgrade-only review artifact.

Fields:

- `review_status`: `pass | downgrade | abstain`.
- `unsupported_or_overstated_claim_ids`.
- `missing_risk_claims`.
- `max_recommendation_after_review`.
- `review_notes_zh`.

Invariant: SkepticReview may not add bullish claims or increase max recommendation.

### FinalDecisionV3

Public decision payload.

Fields:

- `schema_version`: `pulse_final_decision_v3`.
- `route`.
- `recommendation`: `high_conviction | trade_candidate | watchlist | ignore | abstain`.
- `confidence`.
- `abstain_reason`.
- `summary_zh`.
- `narrative_archetype`.
- `narrative_thesis_zh`.
- `bull_view`: references `claim_ids`, not raw event IDs.
- `bear_view`: references `claim_ids`, not raw event IDs.
- `playbook`: monitoring-only playbook.
- `evidence_event_urls`: worker-populated links for referenced event IDs.
- `invalidation_conditions`.
- `residual_risks`.
- `evidence_event_ids`: flattened event IDs from supported claims only.
- `claim_matrix`: compact public claim matrix.
- `gate_clip`: final clipping metadata.
- `write_gate`: pass/fail metadata for public write.

Invariants:

- Non-abstain requires `claim_matrix.verification_status in {"pass", "downgrade"}` and no unsupported material claims in displayed thesis.
- `ignore` and `abstain` require `playbook.has_playbook=false`.
- `risk_rejected_high_info` cannot produce a playbook.
- Final prose cannot mention facts that are absent from supported or weak-supported claims.

## Interface Contracts

### HTTP `GET /api/signal-lab/pulse`

The list endpoint continues to return Signal Pulse items, but v3 list rows expose only v3 decisions. Rows whose latest run has non-v3 `schema_version` are excluded from default live listings.

Semantics:

- Default list includes `watchlist`, `trade_candidate`, `high_conviction` only when write gate passed.
- `ignore` rows are hidden by default unless an explicit future operator/debug filter is approved.
- `abstain` rows remain hidden by default but count in health/eval diagnostics.
- `risk_rejected_high_info` is not a trading candidate. It can appear only as an explicit non-trading diagnostic surface in a later approved UI/API change.

### HTTP `GET /api/signal-lab/pulse/{candidate_id}`

Detail endpoint returns v3 `stages`:

- `evidence_pack`.
- `evidence_completeness_gate`.
- `investigator`.
- `claim_verifier`.
- `skeptic_review`.
- `decision_maker`.
- `recommendation_clipper`.
- `write_gate`.
- `research_only_gate` when applicable.

It does not return `analyst`, `critic`, `judge`, v2-only stage payloads, or placeholder cards for missing legacy stages.

### Eval Cases and Results

`pulse_agent_eval_cases` stays as the eval dataset table, but v3 cases use a new grader version and v3 schema. The v3 grader does not grade v1/v2 shapes and does not return `legacy_skipped`; live queries select by v3 harness hash/schema version before grading.

Required deterministic rules:

- `evidence_pack_present`.
- `evidence_pack_quality`.
- `claim_evidence_matrix_present`.
- `no_unsupported_material_claims`.
- `recommendation_clipped_to_gate_max`.
- `risk_rejected_no_playbook`.
- `high_conviction_eligibility`.
- `public_write_gate_passed`.
- `primary_window_claims_use_primary_window_evidence`.
- `no_execution_language`.

### Notifications

Signal Pulse notifications may consume only rows that passed v3 write gate. External push eligibility remains governed by the control-plane spec, but notification body must not render clipped-away LLM recommendation or unsupported claims.

## Acceptance Criteria

- AC1. WHEN a non-hard-blocked v3 job starts THEN `pulse_agent_run_steps` SHALL contain an `evidence_pack` step before any LLM step.
- AC2. WHEN EvidencePack has zero direct target evidence and zero supported market/profile facts THEN system SHALL write `abstain` or `ignore`, not `watchlist`.
- AC3. WHEN Investigator or DecisionMaker says “KOL relay” THEN ClaimEvidenceVerifier SHALL count independent authors after clustering and same-author repeats; if the count is below threshold, claim SHALL be `unsupported` or `weak_supported`.
- AC4. WHEN a tweet mentions a basket or generic market view without direct target text THEN it SHALL NOT by itself support a target-specific bull claim.
- AC5. WHEN a claim references listing, partnership, migration, airdrop, official catalyst, or Binance/CEX action THEN verifier SHALL require explicit text/profile/market evidence; otherwise final decision SHALL remove the claim or downgrade to `ignore/abstain`.
- AC6. WHEN `gate.max_recommendation = watchlist` THEN public decision SHALL NOT exceed `watchlist`.
- AC7. WHEN `gate.max_recommendation = ignore` or risk-rejected equivalent THEN public decision SHALL NOT exceed `ignore`, and `playbook.has_playbook` SHALL be false.
- AC8. WHEN deterministic eval returns any required-rule violation THEN worker SHALL finish the run audit but SHALL NOT upsert a displayable public candidate from that run.
- AC9. WHEN final decision is `high_conviction` THEN write gate SHALL verify high-conviction eligibility from EvidencePack quality metrics and claim matrix, not only evidence count.
- AC10. WHEN a non-abstain final decision references event IDs THEN every ID SHALL be reachable from supported or weak-supported claims in the matrix.
- AC11. WHEN final narrative uses 1h wording THEN all primary supporting claims SHALL reference 1h active-window evidence unless explicitly marked as 24h context.
- AC12. WHEN public detail is requested for a candidate whose latest run is pre-v3 THEN API SHALL return not found or no live v3 detail, not adapted legacy content.
- AC13. WHEN v3 grader sees old stage names THEN they SHALL be outside the selected v3 dataset; grader code SHALL NOT contain a runtime `legacy_skipped` compatibility branch.
- AC14. WHEN no `evidence_pack_hash`, `matrix_hash`, or `write_gate.status=pass` exists THEN no notification SHALL be sent.
- AC15. WHEN operator reviews audit ledger THEN every public decision SHALL be replayable from EvidencePack, claim matrix, reviewer output, clipper output, and write gate step.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| EvidencePack becomes too large and increases latency/cost. | Medium | Deterministic selected-post cap, cluster compaction, metric refs, and route-specific maximum pack size. |
| Verifier is too strict and suppresses useful early signals. | Medium | Use `weak_supported` and `watchlist` as intermediate, but never allow unsupported claims into `trade_candidate` or `high_conviction`. |
| Removing tool-calling loses flexible follow-up. | Low | Required evidence becomes reliable through prefetch; optional tool enrichment can be revisited after runtime required-tool support is proven. |
| Hard cut hides historical rows that users expect to see. | Medium | Historical rows remain in DB and can be queried by explicit operator SQL/CLI later; live trading-intel surface stays v3-only. |
| More deterministic stages make UI detail verbose. | Low | List view stays compact; detail view can group deterministic stages under audit sections without compatibility cards. |
| Claim verifier misses semantic support subtleties. | Medium | Start with deterministic rules for known failure modes, then add v3 eval labels and optional downgrade-only LLM judge for ambiguous non-upgrade review. |
| High-conviction becomes rare. | Low | That is acceptable. Signal Pulse should prefer fewer real candidates over frequent fabricated conviction. |
| No compatibility code makes rollback harder. | Medium | Rollback is process-level: deploy previous version and filter by harness/schema. v3 runtime does not carry dual contracts. |

## Evolution Path

After v3 public correctness is stable for several days of live data, the next spec can add an outcome loop:

- Store post-decision settlement windows for `1h/4h/24h`.
- Label claims as confirmed, neutral, or invalidated by later facts.
- Feed failure labels into the eval dataset and prompt/component improvement loop.
- Add per-author/cohort historical reliability only after enough settlement data exists.

Do not foreclose future execution research, but keep this project as trading-intel until public Signal Pulse can prove claim truth and recommendation discipline. Execution requires a separate risk, compliance, exchange, and portfolio spec.

## Alternatives Considered

- Keep v2 two-stage and only make eval fail block writes. Rejected because it would stop zero-tool failures, but still would not prove claim support. Event ID subset is too weak for “多空理由是否成立”.

- Use OpenAI required tool choice for Investigator. Rejected for this runtime because current adapter is OpenAI Agents over an OpenAI-compatible Qwen/llama.cpp endpoint, and live audit shows prompt-level mandatory tools produced zero tool calls. Required facts should not depend on provider-specific tool behavior until it is proven and enforced at runtime.

- Copy TradingAgents multi-role graph. Rejected because gmgn is high-throughput crypto social intelligence, not simulated order execution. The useful pieces are pre-fetched structured data, bull/bear/risk separation, and final risk control, not the whole 11-role graph.

- Keep `research` as a max recommendation value. Rejected because `research` is a note/status, not a recommendation in the ordered public lattice. Keeping it created the ambiguity that allowed research-only rows to be upgraded to watchlist/trade_candidate.

- Keep old public stage compatibility for historical rows. Rejected because project architecture explicitly requires no runtime compatibility layer, and the user requested no compatibility code. Historical audit access can be solved outside live public runtime.

- Add a new `pulse_evidence_packs` table immediately. Rejected for this spec because `pulse_agent_run_steps.response_json` can hold sealed deterministic artifacts first. A later storage optimization can add a table if pack size/query patterns justify it.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Build EvidencePack before LLM; verify claims before final public write; clip recommendation after LLM; persist replayable audit steps; hide failed/non-v3 public decisions from live Signal Pulse. |
| Ask first | Adding new tables, new workers, external data providers, execution-related fields, outcome settlement tables, or a separate research-only public surface. |
| Never | Trust prompt-only tool requirements; publish unsupported material claims; let LLM exceed gate max; render legacy stages; preserve old public decision fallback branches; put trading execution instructions in playbook. |
