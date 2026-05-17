# Spec — Pulse Agent Runtime Hard Cut

**Status**: Draft
**Date**: 2026-05-18
**Owner**: Codex with Qinghuan
**Related**:

- Supersedes the runtime-shape portions of `docs/superpowers/specs/active/2026-05-17-pulse-agent-harness-v3-hard-cut-cn.md`.
- Supersedes `docs/superpowers/specs/active/2026-05-16-unified-agent-worker-runtime-cn.md` where that spec preserves the existing three-client split.
- Pairs with `docs/superpowers/plans/active/2026-05-18-pulse-agent-runtime-hard-cut-plan-cn.md`.

## Background

`closed_loop_harness` is currently a full domain module, not a small optional helper. It owns repository, read-model, runtime worker, scoring, settlement, credit, and snapshot-building code under `src/gmgn_twitter_intel/domains/closed_loop_harness/`. The live `EnrichmentWorker` imports `HarnessSnapshotBuilder` from that domain at `src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py:14`, calls it after the SocialEvent LLM run at `src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py:192`, and publishes a `harness_update` websocket payload at `src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py:117`.

The harness dependency is wired through the global runtime. `RepositorySession` imports `HarnessRepository` at `src/gmgn_twitter_intel/app/runtime/repository_session.py:19`, exposes it as `repos.harness` at `src/gmgn_twitter_intel/app/runtime/repository_session.py:71`, and constructs it at `src/gmgn_twitter_intel/app/runtime/repository_session.py:110`. Runtime bootstrap imports `HarnessRepository` at `src/gmgn_twitter_intel/app/runtime/bootstrap.py:24`, creates a pooled harness repository at `src/gmgn_twitter_intel/app/runtime/bootstrap.py:146`, and places it on both `runtime.harness` and `runtime.read_harness` at `src/gmgn_twitter_intel/app/runtime/bootstrap.py:191` and `src/gmgn_twitter_intel/app/runtime/bootstrap.py:197`.

The harness also has public and worker surfaces. `worker_registry.py` registers `harness_ops` at `src/gmgn_twitter_intel/app/runtime/worker_registry.py:31` and schedules it after handle summaries at `src/gmgn_twitter_intel/app/runtime/worker_registry.py:54`. `worker_factories/harness.py` imports `HarnessOpsWorker` at `src/gmgn_twitter_intel/app/runtime/worker_factories/harness.py:5` and constructs it at `src/gmgn_twitter_intel/app/runtime/worker_factories/harness.py:15`. The HTTP harness route imports `HarnessService` at `src/gmgn_twitter_intel/app/surfaces/api/routes_harness.py:13` and exposes `/social-events`, `/attention-seeds`, `/harness-snapshots`, `/harness-outcomes`, `/harness-credits`, `/harness-weights`, `/harness-health`, and `/harness-score-buckets` between `src/gmgn_twitter_intel/app/surfaces/api/routes_harness.py:18` and `src/gmgn_twitter_intel/app/surfaces/api/routes_harness.py:191`.

The event replay surface includes harness state inside normal event payloads. The recent-event API attaches `repos.harness.harness_for_event(event_id)` at `src/gmgn_twitter_intel/app/surfaces/api/routes_events.py:64` and batch attaches `harness_for_events` at `src/gmgn_twitter_intel/app/surfaces/api/routes_events.py:74`. WebSocket replay attaches the same field at `src/gmgn_twitter_intel/app/surfaces/api/ws.py:177`. Signal Pulse read-model health also reaches back into harness by passing a `harness` argument to `SignalPulseService` in `src/gmgn_twitter_intel/app/surfaces/api/routes_pulse.py:69` and `src/gmgn_twitter_intel/app/surfaces/api/routes_pulse.py:97`, then reports `settlement_coverage` from that dependency at `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py:55`.

Notification rules depend on harness snapshots as an alert source. `NotificationRuleEngine` accepts a `harness` dependency at `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py:44`, evaluates `_harness_snapshots` at `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py:66`, reads harness snapshots at `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py:322`, and emits notifications sourced from `harness_snapshots` at `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py:349`. The worker factory wires this with `HarnessService(repos.harness)` at `src/gmgn_twitter_intel/app/runtime/worker_factories/notifications.py:66`.

The storage model shows why this is a half-built closed loop rather than the production Pulse loop. The initial migration creates `social_event_extractions`, `attention_seeds`, `event_clusters`, `harness_snapshots`, `harness_decisions`, `harness_outcomes`, `harness_credits`, and `harness_weights` at `src/gmgn_twitter_intel/platform/db/alembic/versions/20260506_0001_initial_postgresql.py:340` through `src/gmgn_twitter_intel/platform/db/alembic/versions/20260506_0001_initial_postgresql.py:511`. `HarnessSnapshotBuilder` converts a SocialEventExtraction into shadow snapshots and decisions, not Pulse decisions, in `src/gmgn_twitter_intel/domains/closed_loop_harness/services/harness_snapshot_builder.py:36`. It records decisions with `execution_mode="shadow"` and `size=0.0` in `src/gmgn_twitter_intel/domains/closed_loop_harness/services/harness_snapshot_builder.py:239`, so this is not an executable or Pulse-gated decision loop.

Signal Pulse has its own agent ledger and eval path, but the naming also uses "harness". `PulseCandidateJobService` builds a pulse harness manifest at `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py:110`, stores it through `repos.pulse_agent_eval.upsert_agent_runtime_version` at `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py:127`, inserts eval cases at `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py:270`, grades them at `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py:276`, and then still upserts the public candidate at `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py:282`. That means eval is currently telemetry, not a public write gate.

Pulse v2 still relies on agent tool behavior as part of correctness. `PulseAgentRuntimeContract` says the default stages are `investigator` and `decision_maker` at `src/gmgn_twitter_intel/domains/pulse_lab/providers.py:42`, says investigator tools are `get_target_recent_tweets`, `get_target_price_action`, and `get_official_token_profile` at `src/gmgn_twitter_intel/domains/pulse_lab/providers.py:44`, and enables validators including `runtime_evidence_id_subset` at `src/gmgn_twitter_intel/domains/pulse_lab/providers.py:53`. `PulseDecisionRuntimeService` validates only whether supporting ids are in context or tool-contributed ids at `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_decision_runtime.py:81` and `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_decision_runtime.py:103`; it does not verify that the quoted event actually supports the claim.

The three LLM clients are not a unified runtime. Pulse has a strict flattened `_JsonOutputSchema` in `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py:62`, Watchlist has a similar inline schema wrapper whose comment says it is waiting for a shared helper at `src/gmgn_twitter_intel/integrations/openai_agents/watchlist_summary_agent_client.py:41`, and SocialEvent directly passes `SocialEventPayload` as output type at `src/gmgn_twitter_intel/integrations/openai_agents/social_event_agent_client.py:73`. `provider_wiring/openai.py` constructs three separate OpenAI clients at `src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py:91`, `src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py:110`, and `src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py:141`.

TradingAgents is useful as a contrast, not as a blueprint. Its graph uses explicit state fields and role transitions, and its sentiment analyst prefetches structured text rather than relying on tool calls. The important lesson for this project is not "add more agents"; it is "facts must be collected before LLM synthesis, state must be explicit, risk must be separated, and reflection belongs after outcome is known."

## Problem

The current architecture mixes two unrelated ideas under the word "harness": a SocialEvent shadow settlement subsystem and a Pulse agent eval ledger. The SocialEvent `closed_loop_harness` is not mature enough to keep: it adds worker, API, WebSocket, CLI, notification, config, repository-session, migration, and test surface area without serving as the production Pulse trading loop. At the same time, the actual Pulse agent runtime remains split across independent OpenAI clients and still trusts prompt/tool behavior and after-the-fact eval too much. The system needs one hard cut: remove the half-built closed-loop harness, move the useful SocialEvent extraction facts into their proper domain, unify the agent execution layer, and make Pulse's production loop deterministic around EvidencePack, claim verification, write gate, and outcome logging.

## First Principles

1. **Business truth stays in material facts, not agent prose.** The project already treats PostgreSQL facts and rebuildable read models as the core architecture. Agent output can explain and summarize; it cannot become a trusted fact source without deterministic verification.
2. **A component name must match its operational role.** `closed_loop_harness` sounds like the production trading feedback loop, but it is currently a SocialEvent shadow harness. Keeping it creates false confidence and makes the real Pulse loop harder to reason about.
3. **LLM stages consume bounded evidence; they do not own fact acquisition.** Required facts must be prebuilt from local DB/read-model state. Optional LLM tool calls may exist later, but they cannot satisfy correctness requirements unless their outputs are sealed into the same evidence artifact before verification.
4. **Eval failures must block public writes.** If a deterministic verifier or eval says a Pulse decision is invalid, `pulse_candidates` must not expose that run as displayable.
5. **KISS means one production loop.** The target system should have one Pulse decision lifecycle and one shared OpenAI execution runtime, not separate partial loops that each know a little about trading, evidence, and scoring.

## Goals

- G1. Remove the `closed_loop_harness` domain from live runtime code: no `gmgn_twitter_intel.domains.closed_loop_harness` imports remain in `src/` after the cut.
- G2. Remove `harness_ops` from worker registry, worker factories, worker settings, generated worker docs, readiness surfaces, and tests.
- G3. Remove public harness API and payload surfaces: `/harness-*` endpoints, event payload `harness` fields, websocket `harness_update`, and harness snapshot notifications no longer exist.
- G4. Preserve useful SocialEvent extraction output by moving ownership of `social_event_extractions` into `social_enrichment`; enrichment completion still persists model run audit and extracted social-event facts.
- G5. Drop SocialEvent shadow harness storage: `attention_seeds`, `event_clusters`, `harness_snapshots`, `harness_decisions`, `harness_outcomes`, `harness_credits`, and `harness_weights` are removed by migration.
- G6. Replace Pulse "harness" vocabulary with "agent runtime" and "agent eval" vocabulary in code and DB where those concepts are live Pulse concerns.
- G7. Create one shared OpenAI agent runtime for Pulse, SocialEvent, and Watchlist: strict output schema, model settings, trace config, usage extraction, safety-net integration, and run audit are not duplicated across clients.
- G8. Move business prompts out of OpenAI integration clients. Domain packages own prompt text, input construction, output schema semantics, and business validators.
- G9. Change Pulse correctness from tool-call/prompt enforcement to sealed EvidencePack, ClaimEvidenceMatrix, deterministic verifier, recommendation clipper, and write gate.
- G10. Add a production Pulse outcome loop that logs realized outcomes by horizon for Pulse decisions, without automatic live tuning until enough verified samples exist.

## Non-Goals

- N1. No exchange execution, order routing, leverage, position sizing, target prices, stop loss, or take profit.
- N2. No LangGraph migration and no TradingAgents-style multi-role debate clone.
- N3. No compatibility layer for deleted `closed_loop_harness` APIs, workers, websocket payloads, CLI commands, notification rules, or tables.
- N4. No new background worker for agent execution. The existing `pulse_candidate`, `enrichment`, and `handle_summary` workers keep ownership of their job lifecycles.
- N5. No online learning, bandits, or automatic production weight tuning from the first outcome samples.
- N6. No external HTTP calls inside Pulse LLM stages. Required evidence comes from local PostgreSQL facts and read models.

## Target Architecture

The target architecture has three clean lanes.

**Social enrichment lane.** `EnrichmentWorker` claims watched social-event jobs, calls `SocialEventEnrichmentProvider`, records the model run, and persists `social_event_extractions` through a social-enrichment-owned repository. It can trigger watchlist summary jobs. It does not materialize attention seeds, event clusters, harness snapshots, harness decisions, credits, weights, or harness websocket updates.

**Unified agent runtime lane.** `integrations/openai_agents` exposes a small execution infrastructure: strict JSON output schema, model settings, run config builder, usage extractor, safety-net runner, and stage audit builder. Domain-specific clients become thin adapters that provide stage specs and output types. They do not contain prompt text or SQL. `app/runtime/provider_wiring/openai.py` remains the composition root that wires settings, LLMGateway, DB-backed domain services, and OpenAI client adapters.

**Pulse production loop.** `pulse_lab` owns the trading-analysis lifecycle:

```text
token_radar_rows
  -> PulseAdmissionPolicy
  -> pulse_agent_jobs
  -> EvidencePackBuilder
  -> EvidenceCompletenessGate
  -> LLM Narrative / Claim Extraction
  -> ClaimEvidenceVerifier
  -> SkepticRiskReview
  -> DecisionMaker
  -> RecommendationClipper
  -> deterministic eval
  -> WriteGate
  -> pulse_candidates / pulse_playbooks
  -> pulse_decision_outcomes
  -> agent eval / reflection report
```

The replacement for `closed_loop_harness` is not another generic harness. It is a Pulse-specific outcome loop. It records versioned decision facts, entry/exit ticks, realized return, drawdown proxy, liquidity decay, invalidation observations, and verifier failures against the exact EvidencePack and decision version that produced the public candidate.

## Conceptual Data Flow

```text
collector
  -> ingest
  -> token_intel / asset_market material facts
  -> token_radar_rows
  -> pulse_candidate worker
  -> EvidencePackBuilder
  -> unified OpenAI runtime stages
  -> ClaimEvidenceVerifier + WriteGate
  -> pulse_candidates / pulse_playbooks
  -> pulse_decision_outcomes
  -> api / web / notification
```

Changed arrows:

- `enrichment -> closed_loop_harness` is deleted.
- `events/ws -> harness payload` is deleted.
- `notification_rule -> harness snapshots` is deleted.
- `pulse_candidate -> OpenAI tool-dependent investigator` becomes `pulse_candidate -> EvidencePackBuilder -> OpenAI narrative stages`.
- `deterministic eval -> telemetry only` becomes `deterministic eval -> WriteGate`.
- `pulse_candidates -> future eval` becomes `pulse_candidates -> pulse_decision_outcomes -> versioned eval/reflection`.

## Core Models

### SocialEventExtraction

Owned by `social_enrichment`. It preserves the existing semantic output of the SocialEvent LLM: signal flag, event type, source action, subject, direction hint, attention mechanism, impact/novelty/confidence, anchor terms, token candidates, semantic risks, summary, raw response, model audit. It no longer implies seed/snapshot/decision materialization.

### AgentStageSpec

Domain-produced immutable description of one LLM stage: stage name, prompt text, input payload, output type, max turns, optional tool set, and audit tags. The OpenAI integration executes it; it does not create business inputs itself.

### AgentRunAudit

Shared run metadata: provider, model, backend, workflow name, agent name, prompt version, schema version, runtime version, input hash, output hash, trace metadata, usage, safety-net metadata, parse mode, latency, status, and error.

### EvidencePack

Pulse-owned sealed evidence artifact. It contains selected posts, source event ids, event refs, metric refs, market facts, profile facts, quality metrics, duplicate/concentration metrics, risk flags, data gaps, and a canonical hash. It is built before LLM execution and is the only evidence source for non-abstain Pulse decisions.

### ClaimEvidenceMatrix

Pulse-owned verifier artifact. It maps every material bull, bear, catalyst, market, profile, and risk claim to event refs or metric refs, support strength, contradictions, and verifier reason. It separates "model cited a real event" from "the event supports the claim."

### PulseDecisionOutcome

Pulse-owned post-decision outcome artifact. It records decision id/run id/candidate id, EvidencePack hash, decision version, horizon, entry tick, exit tick, realized return, max drawdown proxy, liquidity decay, outcome status, and created/settled timestamps.

## Interface Contracts

- HTTP event/recent payloads no longer include `harness`.
- WebSocket event replay no longer includes `harness`; enrichment completion publishes an enrichment/social-event update only if the existing frontend needs one.
- `/harness-snapshots`, `/harness-outcomes`, `/harness-credits`, `/harness-weights`, `/harness-health`, and `/harness-score-buckets` are deleted.
- CLI `harness-*` and `ops attribute/update harness` commands are deleted.
- Signal Pulse public list/detail keeps `/signal-lab/pulse` semantics but exposes v3 stage names and v3 decision artifacts only.
- Notification rules no longer include `harness_snapshot_high_score`; Pulse notifications must be driven from `pulse_candidates`, `pulse_playbooks`, or later `pulse_decision_outcomes`.
- Worker config no longer accepts `harness_ops`. Because this is a hard cut, stale `harness_ops` config should fail config validation until operator-owned `workers.yaml` is updated.

## Acceptance Criteria

- AC1. WHEN `rg "closed_loop_harness|HarnessRepository|HarnessService|HarnessSnapshotBuilder|HarnessOpsWorker" src tests` is run THEN system SHALL return no live code imports or references, except migration downgrade comments if unavoidable.
- AC2. WHEN `uv run gmgn-twitter-intel --help` is regenerated THEN CLI SHALL not list `harness-snapshots`, `harness-outcomes`, `harness-credits`, `harness-weights`, `attribute-harness-credits`, or `update-harness-weights`.
- AC3. WHEN HTTP routes are listed THEN `/harness-*` routes SHALL not exist.
- AC4. WHEN recent event API or websocket replay returns an event payload THEN the payload SHALL not contain a `harness` key.
- AC5. WHEN `enrichment` processes a watched social event THEN it SHALL persist `model_runs` and `social_event_extractions`, SHALL optionally enqueue watchlist summary, and SHALL NOT write attention seeds, event clusters, harness snapshots, or harness decisions.
- AC6. WHEN `pulse_candidate` runs a non-hard-blocked job THEN it SHALL create an EvidencePack before any LLM stage.
- AC7. WHEN a Pulse decision has unsupported material claims THEN WriteGate SHALL prevent a displayable candidate write.
- AC8. WHEN deterministic eval result is `fail` THEN public `pulse_candidates` SHALL not expose `watchlist`, `trade_candidate`, or `high_conviction` for that run.
- AC9. WHEN `risk_rejected_high_info` is produced by deterministic gate THEN public decision SHALL have no playbook and SHALL be clipped to `ignore` or `abstain`.
- AC10. WHEN agent clients run in tests THEN Pulse, SocialEvent, and Watchlist SHALL use the same shared OpenAI runtime schema/settings/audit utilities.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Removing harness breaks recent event UI assumptions. | High | Contract tests assert event payload shape; frontend/API tests must be updated in the same PR that deletes route payloads. |
| Dropping harness tables deletes historical shadow data that might be useful later. | Medium | This data is report-only and not trusted for Pulse. If preservation is needed, export before migration outside app runtime; do not keep live compatibility code. |
| `social_event_extractions` is accidentally dropped with harness tables. | High | Keep the table and move repository ownership to `social_enrichment`; add integration test for enrichment persistence. |
| Notification coverage decreases after deleting harness snapshot alerts. | Medium | Pulse candidate/playbook notification rules remain; add explicit test that no harness rule id is registered. |
| Unified runtime becomes a generic helper dumping ground. | Medium | Keep shared code limited to OpenAI SDK execution mechanics; prompts, input builders, validators, and business schemas stay in domains. |
| Outcome loop is mistaken for profitable strategy proof. | High | Outcome loop is eval labeling only; no automatic tuning or trading claim until enough verified samples and a separate spec. |

## Evolution Path

After this hard cut, the next expansion is a Pulse outcome analytics surface: per-version precision/false-positive rate, unsupported-claim taxonomy, route-level downgrade reasons, and outcome distributions by horizon. The design should not foreclose future provider support, but the first version should stay OpenAI-runtime-specific at the integration layer and domain-contract-specific at the Pulse layer.

## Alternatives Considered

- **Keep `closed_loop_harness` but disable `harness_ops`.** Rejected because the domain would still pollute repository sessions, API payloads, notifications, config, and mental model while not serving the production Pulse loop.
- **Rename `closed_loop_harness` to `social_event_harness`.** Rejected because the shadow snapshot/credit/weight system is not mature enough to justify its runtime surface. Moving useful extraction facts into `social_enrichment` is simpler.
- **Create a new generic `domains/agent_runtime`.** Rejected for this cut because domain semantics remain different across Pulse, SocialEvent, and Watchlist. Shared code should live at the OpenAI integration boundary until a second provider forces a domain-level abstraction.
- **Clone TradingAgents' multi-agent graph.** Rejected because this product is a near-real-time Twitter crypto signal system. It needs deterministic evidence and write gates more than debate depth.
- **Keep LLM tools as required evidence acquisition.** Rejected because prompt-based tool requirements already failed in production. Required facts must be prebuilt and sealed before model stages.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Delete `closed_loop_harness` live runtime, routes, worker, config, and notifications. |
| Always | Keep SocialEvent extraction facts by moving them into `social_enrichment`. |
| Always | Use one shared OpenAI execution runtime for strict schema/settings/audit mechanics. |
| Always | Make Pulse public writes pass EvidencePack, claim verifier, recommendation clipper, deterministic eval, and WriteGate. |
| Ask first | Export historical harness shadow tables before destructive migration in a live production DB. |
| Ask first | Add an LLM skeptic stage if deterministic verifier coverage is sufficient but qualitative risk review still needs model help. |
| Never | Preserve compatibility code for deleted harness APIs, worker config, websocket payloads, CLI commands, or route handlers. |
| Never | Let LLM output upgrade deterministic gate ceilings or bypass unsupported-claim failures. |
