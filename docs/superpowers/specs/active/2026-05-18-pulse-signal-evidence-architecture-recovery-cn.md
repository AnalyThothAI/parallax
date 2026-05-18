# Spec — Pulse Signal Evidence-First Architecture Recovery

**Status**: Draft, recalibrated after subagent review
**Date**: 2026-05-18
**Owner**: Codex with Qinghuan
**Scope**: Architecture-level recovery for Signal Pulse after recent Pulse Signal / Pulse Agent refactors caused live worker activity to stop producing fresh displayable signals.

## Decision

The bottleneck is the Pulse agent boundary.

It is not that we need more agents. It is that the agent receives evidence that is not sealed, not typed enough, and not deterministically admissible. The system can already reach facts through PostgreSQL facts, read models, and provider-derived market/profile data. The missing layer is an explicit `PulseEvidencePacket` that decides which facts are admissible for this run and gives the LLM a closed citation set.

Correct design:

```text
worker builds sealed PulseEvidencePacket
  -> LLM synthesizes bull/bear/rebuttal only inside packet
  -> deterministic verifier checks every cited ref
  -> decision/write gate decides public eligibility
```

Incorrect design:

```text
LLM must call tools to acquire critical facts
  -> eval checks after the fact whether tools happened
  -> public write path tries to infer validity from agent output
```

The architecture borrows the useful idea from `/Users/qinghuan/Documents/code/TradingAgents`: first build evidence reports, then ask dedicated roles to synthesize and challenge the case, then let a manager-like stage adjudicate. We do not borrow its broad multi-agent/tool graph. Pulse needs a compact evidence debate, not more autonomous data-fetching agents.

## References

OpenAI cookbook references used for design principles:

- `/Users/qinghuan/Documents/code/openai-cookbook/examples/Structured_Outputs_Intro.ipynb`
- `/Users/qinghuan/Documents/code/openai-cookbook/examples/Using_tool_required_for_customer_service.ipynb`
- `/Users/qinghuan/Documents/code/openai-cookbook/examples/reasoning_function_calls.ipynb`
- `/Users/qinghuan/Documents/code/openai-cookbook/examples/evaluation/use-cases/tools-evaluation.ipynb`
- `/Users/qinghuan/Documents/code/openai-cookbook/examples/evaluation/use-cases/structured-outputs-evaluation.ipynb`
- `/Users/qinghuan/Documents/code/openai-cookbook/examples/evaluation/Building_resilient_prompts_using_an_evaluation_flywheel.md`
- `/Users/qinghuan/Documents/code/openai-cookbook/examples/agents_sdk/evaluate_agents.ipynb`
- `/Users/qinghuan/Documents/code/openai-cookbook/examples/agents_sdk/agent_improvement_loop.ipynb`
- `/Users/qinghuan/Documents/code/openai-cookbook/articles/techniques_to_improve_reliability.md`

TradingAgents references used for architectural comparison:

- `/Users/qinghuan/Documents/code/TradingAgents/tradingagents/graph/setup.py`
- `/Users/qinghuan/Documents/code/TradingAgents/tradingagents/agents/researchers/bull_researcher.py`
- `/Users/qinghuan/Documents/code/TradingAgents/tradingagents/agents/researchers/bear_researcher.py`
- `/Users/qinghuan/Documents/code/TradingAgents/tradingagents/agents/managers/research_manager.py`
- `/Users/qinghuan/Documents/code/TradingAgents/tradingagents/agents/schemas.py`

## Production Evidence

Read-only production diagnostics used the operator-owned runtime config:

- `config_path`: `/Users/qinghuan/.gmgn-twitter-intel/config.yaml`
- `workers_config_path`: `/Users/qinghuan/.gmgn-twitter-intel/workers.yaml`

Window: approximately `2026-05-18 13:06:48` to `2026-05-18 17:06:48` Asia/Shanghai.

Observed facts:

- Runtime is alive. `pulse_candidate` is running; a recent live status sample had `claimed=10`, `processed=3`, `failed=7`, `skipped=95`.
- Price/backfill is not the primary root cause. `event_anchor_backfill` had no selected pending work in live status. Four-hour terminal backfill jobs were `1168`, with `96` failed (`8.22%`), mostly `provider_no_quote` and `no_market_data`.
- Pulse agent health is degraded. Four-hour `pulse_agent_runs` were `678`, with `130` failed (`19.17%`).
- Failed agent reasons were `schema_validation_failed=96`, `unknown_evidence_id=32`, and `timeout=2`.
- Deterministic eval flagged `tool_calls_present` failures in `320 / 679` recent eval results.
- Default Signal Pulse `1h/all` had newer rows, but the newest rows were hidden `abstain` decisions. Latest any-row was BNB at `2026-05-18 14:39:24`, with `decision_recommendation=abstain` and `decision_abstain_reason=data_completeness_below_hard_gate`.
- Latest displayable `1h/all` row was still LFI at `2026-05-18 07:42:56`, because the public list hides `decision_recommendation=abstain`.
- A sampled CEX candidate had `data_health.market=ready`, `price_usd`, `source_provider=okx_cex_rest`, and `pricefeed_id`, but no `venue_id`; current completeness requires CEX `price_usd + venue_id`, causing a false `score=0.5` hard block.

## Problem

The current chain confuses three questions:

1. Are enough admissible facts present for a decision?
2. Did the LLM produce valid structured reasoning?
3. Should the UI show a fresh public signal?

Facts are reachable, but not sealed. Current Pulse passes a large `factor_snapshot` and relies on LLM tool behavior and post-hoc eval to validate the run. That creates several failure modes:

- A provider/read-model shape mismatch (`venue_id` absent, `pricefeed_id` present) becomes a generic hard block.
- A prompt-level instruction to call tools is treated as a correctness boundary, but the runtime does not enforce a complete evidence acquisition contract.
- Agent output can cite unknown evidence ids because the allowed set is not the primary artifact.
- Fresh hidden abstains update the database while the default public list looks stale.

The root problem is the trust boundary. Required evidence acquisition must move out of LLM tool-calling and into deterministic worker-owned packet construction.

## Definitions

**Facts available** means the system can reach facts from PostgreSQL material facts, read models, and provider-derived snapshots.

**Facts admissible** means the facts have been normalized, freshness-checked, assigned stable refs, hashed, persisted, and included in the current run's `PulseEvidencePacket`.

Signal Pulse decisions may only use admissible facts.

## Principles

1. **Facts before narrative.** LLM stages consume sealed facts. They do not own required fact discovery.
2. **Structured output controls shape, not truth.** Pydantic/JSON schema is necessary but not sufficient.
3. **Tool calling is not the critical evidence boundary.** `tool_choice='required'` proves a tool call happened; it does not prove the right facts were acquired.
4. **Producer/consumer contracts must be domain types.** Pulse consumes `MarketEvidence`, `SocialEvidence`, and `IdentityEvidence`, not raw provider-shaped keys.
5. **Ref-based claims are mandatory.** Every non-abstain claim must cite `allowed_evidence_refs.ref_id`, including event, metric, cluster, and profile refs.
6. **Debate is bounded by evidence.** Bull/bear/rebuttal synthesis is valuable only after the packet is sealed.
7. **Invalid agent runs are product states.** Schema failures, unsupported refs, insufficient evidence, and degraded publish state must be visible in health/display status.
8. **No live compatibility path.** Historical rows remain audit-only; live runtime and public API use the recovered evidence-first contract.
9. **Replay beats intuition.** Future Pulse changes must pass replay/eval over fixed production failures and seed cases.

## Goals

- G1. Build and persist a sealed `PulseEvidencePacket` before any LLM stage.
- G2. Build packet facts primarily from PostgreSQL material facts and canonical repositories, not from raw `factor_snapshot` alone.
- G3. Replace tool-required Investigator semantics with packet-only evidence debate semantics.
- G4. Introduce `EvidenceDebateMemo` with bull case, bear case, rebuttals, data gaps, and cited refs.
- G5. Require `FinalDecision` and `EvidenceDebateMemo` to cite complete packet refs, not event ids only.
- G6. Enforce route-specific evidence gates and recommendation ceilings before public write.
- G7. Add typed `AgentRunOutcome`, `EvidenceStatus`, `DecisionStatus`, and `DisplayStatus`.
- G8. Expose freshness and failure SLOs in API/status/CLI/frontend.
- G9. Keep the existing `pulse_candidate` worker as the lifecycle owner; do not introduce a new worker.

## Non-Goals

- N1. Do not fix this by only adding `tool_choice='required'`.
- N2. Do not fix this by only changing CEX `venue_id` to another field.
- N3. Do not add a broad TradingAgents-style graph with many autonomous agents.
- N4. Do not let LLM judges replace deterministic packet/ref/completeness checks.
- N5. Do not add exchange execution, position sizing, target price, stop loss, or take profit.
- N6. Do not preserve live v1/v2 Pulse stage adapters. Historical audit rows may remain queryable.

## Target Data Flow

```text
token_radar_rows
  -> PulseAdmissionPolicy
  -> pulse_agent_jobs
  -> PulseEvidenceBuilder
       reads events / enriched_events
       reads asset_identity_current / token_profile_current / cex_token_profiles
       reads market_ticks / pricefeed current facts
       may include factor_snapshot as source fingerprint and admission context
  -> pulse_evidence_packets
  -> EvidenceCompletenessGate
  -> EvidenceDebateSynthesizer
       packet-only bull/bear/rebuttal memo
  -> ClaimEvidenceVerifier
       memo refs subset packet refs
  -> DecisionMaker
       packet + debate memo + evidence gate only
  -> RecommendationClipper
       pulse gate ceiling + evidence gate ceiling
  -> DeterministicEval
  -> PulseWriteGate / PulsePublishPolicy
  -> pulse_candidates(display_status, evidence_status, evidence_packet_hash)
  -> Signal Pulse read model / health
  -> API / frontend / notifications
  -> ReplayEvalHarness
```

The LLM stages are two roles, not three autonomous data agents:

1. `evidence_debate`: synthesize bull/bear/rebuttal from the sealed packet.
2. `decision_maker`: adjudicate from the packet, debate memo, gates, and constraints.

This mirrors TradingAgents at the architectural level:

```text
TradingAgents: analyst reports -> bull/bear debate -> research manager
Pulse: sealed evidence packet -> bull/bear evidence memo -> decision maker
```

The difference is that Pulse keeps evidence acquisition deterministic and typed before LLM reasoning.

## Core Contracts

### PulseEvidencePacket

Sealed deterministic input to all LLM stages.

Required fields:

- `evidence_packet_id`
- `evidence_packet_hash`
- `schema_version`
- `candidate_id`
- `target_type`
- `target_id`
- `symbol`
- `window`
- `scope`
- `snapshot_at_ms`
- `source_event_ids`
- `allowed_evidence_refs`
- `social_evidence`
- `market_evidence`
- `identity_evidence`
- `quality_metrics`
- `data_gaps`
- `risk_flags`
- `source_fingerprints`
- `admission_context`

Invariants:

- Packet construction happens before the first LLM stage.
- Packet hash is persisted on `pulse_agent_runs` and `pulse_candidates`.
- All non-abstain LLM claims cite refs from `allowed_evidence_refs`.
- The packet may be valid for an abstain or hidden result while invalid for public non-abstain recommendations.
- `factor_snapshot` is not the packet's source of truth. It may be included as `admission_context` and fingerprinted for replay.

### EvidenceRef

Stable citation unit.

Required fields:

- `ref_id`
- `ref_type`: `event | metric | profile | cluster | market | identity | gate`
- `source_table`
- `source_id`
- `observed_at_ms`
- `summary_zh`
- `quality`

Examples:

```text
event:event-123
metric:market:price_usd
metric:market:volume_24h_usd
profile:official_links
cluster:social:direct_target
gate:pulse:low_information
```

### MarketEvidence

Route-specific normalized market contract.

CEX required shape:

```text
route = cex
target_market_type = cex | spot | perp | perpetual
price_usd
venue_ref
instrument_ref
observed_at_ms
freshness_status
source_provider
pricefeed_id
volume_24h_usd optional but scored
open_interest_usd optional
funding_rate optional
```

DEX/meme required shape:

```text
route = meme
target_market_type = dex | meme | new_pair | pumpfun
price_usd
liquidity_usd
market_cap_usd
volume_24h_usd
holders
observed_at_ms
freshness_status
chain
token_address
source_provider
```

`venue_ref` may be derived from `pricefeed_id`, `source_provider`, `instrument_ref`, or provider metadata. Downstream Pulse code consumes `venue_ref`, never raw `venue_id`.

### SocialEvidence

Normalized social proof contract.

Required shape:

```text
selected_posts
post_clusters
independent_author_count
watched_author_count
direct_target_text_count
generic_basket_post_count
duplicate_text_share
top_author_share
primary_window_event_count
source_lookback_event_count
```

Invariant:

- Generic basket posts may support context/risk claims, but may not be the sole support for a direct target catalyst.

### IdentityEvidence

Normalized target identity contract.

Required shape:

```text
resolution_status
target_id
symbol
canonical_name optional
chain optional
token_address optional
profile_status
official_links
profile_description optional
logo_status
```

Invariant:

- `research_only` is used when identity is unresolved or target is not decisionable.

### EvidenceDebateMemo

Structured LLM output from sealed packet only.

Required fields:

- `route`
- `bull_case`
- `bear_case`
- `bull_rebuttal`
- `bear_rebuttal`
- `data_gaps`
- `narrative_archetype_candidate`
- `overall_evidence_balance`

Each case/rebuttal has:

- `thesis_zh`
- `strength`: `absent | weak | moderate | strong`
- `supporting_evidence_refs`

Invariants:

- Every `supporting_evidence_refs` item must exist in `PulseEvidencePacket.allowed_evidence_refs`.
- `strength != absent` requires at least one supporting ref.
- No new evidence may be introduced by the memo.

### FinalDecision

DecisionMaker output from packet + debate memo + gates only.

Required fields:

- Existing decision fields: `route`, `recommendation`, `confidence`, `abstain_reason`, `summary_zh`, `narrative_archetype`, `narrative_thesis_zh`, `bull_view`, `bear_view`, `playbook`, `invalidation_conditions`, `residual_risks`
- New ref fields:
  - `supporting_evidence_refs`
  - `risk_evidence_refs`
  - `data_gap_refs`

Invariants:

- Non-abstain requires `supporting_evidence_refs`.
- `high_conviction` requires evidence-ready status, moderate/strong bull and bear analysis, and at least three supporting refs across event/market/social/profile categories.
- No final decision may cite refs outside the packet.
- `evidence_event_ids` may remain as a derived API convenience, but it is not the verifier's primary contract.

### AgentRunOutcome

Typed outcome for every run, separate from queue status.

Values:

```text
running
completed
abstain_insufficient_evidence
blocked_market_contract
blocked_social_contract
blocked_identity_contract
invalid_schema
invalid_unknown_evidence_ref
invalid_unsupported_claim
timeout
provider_rate_limited
provider_unavailable
unexpected_exception
```

Queue status answers scheduling. `AgentRunOutcome` answers product validity.

### DisplayStatus

Public display state derived after write gate.

Values:

```text
display_trade_candidate
display_token_watch
display_risk_rejected_high_info
hidden_abstain
hidden_insufficient_evidence
hidden_blocked_low_information
hidden_invalid_output
hidden_hold_publish
```

Default Signal Pulse lists may hide abstains, but health/read-model APIs must expose freshness across all statuses.

## State Model

The recovered chain uses separate state layers:

| Layer | Question | Owner | Examples |
|-------|----------|-------|----------|
| `admission_status` | Should this radar edge create work? | `PulseAdmissionPolicy` | `suppressed`, `enqueued`, `budget_blocked` |
| `evidence_status` | What level of decision can facts support? | `EvidenceCompletenessGate` | `complete`, `partial`, `insufficient`, `stale`, `invalid` |
| `agent_status` | Did LLM stages complete valid structured synthesis? | agent runtime | `completed`, `invalid_schema`, `timeout` |
| `decision_status` | What decision class survived verifier/eval/write gate? | verifier / write gate | `trade_candidate`, `token_watch`, `risk_rejected_high_info`, `abstain`, `invalid` |
| `display_status` | Should UI show it by default? | read model | `display_trade_candidate`, `hidden_abstain`, `hidden_hold_publish` |

No layer may infer another layer's answer implicitly from one enum.

## SLOs And Health

Add Pulse health to Signal Pulse summary and `/api/status`.

Required metrics:

- `latest_any_at_ms`
- `latest_evidence_ready_at_ms`
- `latest_valid_agent_at_ms`
- `latest_displayable_at_ms`
- `latest_actionable_at_ms`
- `agent_run_failure_rate_15m`
- `agent_run_failure_rate_4h`
- `schema_failure_rate_4h`
- `unknown_evidence_ref_rate_4h`
- `unsupported_claim_rate_4h`
- `market_contract_block_rate_4h`
- `display_hidden_abstain_rate_4h`
- `dead_job_count`
- `due_job_backlog`

Derived status:

```text
healthy
degraded_agent
degraded_evidence
degraded_display
hold_publish
```

Initial thresholds:

- `agent_run_failure_rate_15m >= 15%` -> `degraded_agent`
- `schema_failure_rate_4h >= 10%` -> `degraded_agent`
- `unknown_evidence_ref_rate_4h >= 5%` -> `degraded_agent`
- `unsupported_claim_rate_4h >= 5%` -> `degraded_agent`
- `market_contract_block_rate_4h >= 40%` -> `degraded_evidence`
- `latest_displayable_at_ms` older than 2 hours while `latest_any_at_ms` is fresh -> `degraded_display`
- `agent_run_failure_rate_15m >= 30%` or repeated verifier failures -> `hold_publish`

`hold_publish` does not stop audit rows or hidden rows. It stops new public display writes such as `display_trade_candidate` until the chain is back inside SLO.

## Eval And Replay

### Dataset Sources

- Recent production failures from `pulse_agent_runs`.
- Eval failures from `pulse_agent_eval_results`.
- Current display-stale cases from `pulse_candidates`.
- Fixed seed cases for CEX, DEX/meme, research-only, abstain, risk-rejected, high-conviction eligibility.
- A captured 2026-05-18 failure set covering CEX market contract mismatch, schema validation failures, unknown evidence refs, and hidden abstain freshness.

### Required Deterministic Graders

- `evidence_packet_exists`
- `market_evidence_contract`
- `social_evidence_contract`
- `identity_evidence_contract`
- `debate_refs_subset_packet_refs`
- `decision_refs_subset_packet_refs`
- `non_abstain_requires_evidence_ready`
- `recommendation_ceiling_respected`
- `display_freshness_contract`
- `agent_run_outcome_typed`
- `hold_publish_blocks_actionable`

### Required Semantic Graders

Use LLM graders only after deterministic checks pass.

- `summary_zh_grounded_in_packet`
- `bull_bear_rebuttals_supported`
- `risk_summary_represents_data_gaps`
- `no_trading_execution_language`

LLM grader outputs must use strict structured output and be compared against a small human-reviewed gold set before becoming a release gate.

## Migration Strategy

### Phase 0 — Freeze And Baseline

- Freeze Pulse prompt/tool/schema refactors except emergency fixes.
- Export recent failed runs, eval failures, hidden abstains, and last good displayable rows.
- Add read-only diagnostics if needed, without changing public behavior.

### Phase 1 — DB And Type Foundations

- Add packet ledger table.
- Add `evidence_packet_hash`, `evidence_status`, `decision_status`, and `display_status` to `pulse_candidates`.
- Add `evidence_packet_id`, `evidence_packet_hash`, `evidence_status`, and `display_status` to `pulse_agent_runs`.
- Hard-cut `pulse_agent_run_steps.stage` CHECK to include evidence-first stage names with `NOT VALID`.
- Hard-cut `pulse_agent_runs.outcome` CHECK to include new `AgentRunOutcome` values with `NOT VALID`.
- Existing `pulse_candidates` rows without packet hash are historical audit rows. Explicitly set them to hidden evidence-first statuses and require `evidence_packet_hash` for default public reads. Do not translate old rows into displayable evidence-first candidates.

### Phase 2 — Evidence Packet Builder

- Build packet from repositories/material facts:
  - social facts: `events`, `enriched_events`, `social_event_extractions`, selected timeline rows
  - market facts: `market_ticks`, event anchors, pricefeed-derived current facts
  - identity facts: asset identity/current profile repositories
- Include `factor_snapshot` only as admission context and replay fingerprint.
- Persist the packet before any LLM stage.

### Phase 3 — Packet-Only LLM Runtime

- Remove required evidence tools from public Pulse runtime.
- Runtime manifest declares no required tools.
- Replace `investigator` with `evidence_debate`.
- Keep `decision_maker` as adjudicator from packet + debate memo.

### Phase 4 — Verifier, Eval, Publish Gate

- Verify debate refs and decision refs against packet refs.
- Replace `tool_calls_present` grader with evidence-first graders.
- Combine evidence gate, deterministic eval, claim verifier, and health status inside `PulseWriteGate` or `PulsePublishPolicy`.

### Phase 5 — Read Model, API, Frontend, Replay

- Expose freshness clocks and failure rates in Signal Pulse health.
- Update API schema and frontend contracts.
- Add replay eval command following existing CLI command patterns.
- Update architecture and contracts docs.

## Acceptance Criteria

- AC1. Every new Pulse run persists a `PulseEvidencePacket` before any LLM stage audit row.
- AC2. A CEX market fact with `price_usd + pricefeed_id/source_provider/instrument` but no raw `venue_id` derives `venue_ref` or emits `blocked_market_contract`; it does not become generic `data_completeness_below_hard_gate`.
- AC3. LLM stages cannot access required evidence tools in public Pulse runtime.
- AC4. `EvidenceDebateMemo` and `FinalDecision` cite only `allowed_evidence_refs.ref_id`.
- AC5. Unknown refs and unsupported claims produce typed outcomes and no displayable candidate.
- AC6. `hold_publish` blocks new actionable public rows but keeps packet/run audit rows.
- AC7. Default Signal Pulse health distinguishes `latest_any_at_ms` from `latest_displayable_at_ms`.
- AC8. Existing rows without `evidence_packet_hash` are explicitly hidden as audit-only, and health/status surfaces this hard cut during rollout.
- AC9. Replay eval classifies the 2026-05-18 failure modes before rollout.
- AC10. Architecture docs state: required facts come from `PulseEvidencePacket`, not LLM tools.

## Explicit Trade-Offs

**Why not add more agents?** More agents amplify an unclear evidence boundary. The production failure was not lack of reasoning roles; it was absence of a sealed admissible evidence artifact.

**Why keep two LLM stages?** One stage builds a bounded bull/bear/rebuttal memo. One stage adjudicates. This captures the useful TradingAgents pattern without adding a broad graph.

**Why remove required tools from public Pulse runtime?** Required evidence is business-critical. It must be deterministic, replayable, and typed before reasoning. Tools can return later only as upstream packet enrichment.

**Why keep historical audit compatibility?** Historical rows are operational evidence. They should remain queryable for replay and incident analysis, but live runtime and public API must not branch into old behavior.

**Why allow `factor_snapshot` at all?** It remains useful as admission context, edge signature input, and replay fingerprint. It is not sufficient as the source of truth for market/social/identity evidence.

## Anti-Patterns Rejected

- Prompt-only repair.
- `tool_choice='required'` as the whole repair.
- LLM judge before deterministic packet/ref/completeness checks.
- Treating worker `running=true` as Pulse health.
- Treating `candidate_count` as fresh displayable signal count.
- Reading provider-specific `decision_latest` fields directly in agent routing, job service, read model, or LLM prompts.
- Letting hidden abstains make summary look fresh while the default list is stale.
- Calling the design “TradingAgents-inspired” while leaving the LLM responsible for critical fact discovery.
