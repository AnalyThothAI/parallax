# Closed Loop Social Event Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an evidence-bound, closed-loop social-event harness on top of the existing GMGN/X watched-account pipeline, without adding external news sources.

**Architecture:** The LLM becomes a strict JSON-schema social-event extractor. The harness persists each stage in SQLite, computes deterministic scores, freezes shadow snapshots, settles abnormal returns, assigns multi-event credit, and updates explainable weights slowly. This is a breaking replacement of the narrative-first LLM contract; do not build compatibility bridges.

**Tech Stack:** Python 3.13, SQLite WAL/FTS5, FastAPI, existing OpenAI SDK dependency, pytest, ruff, existing CLI/API patterns.

**Related spec:** `docs/superpowers/specs/2026-05-04-closed-loop-social-event-harness-design.md`

**Chinese evaluation:** `docs/superpowers/specs/2026-05-04-closed-loop-social-event-harness-cn-evaluation.md`

**Backend production architecture:** `docs/superpowers/specs/2026-05-04-closed-loop-harness-backend-production-cn.md`

**MVP UI design:** `docs/superpowers/specs/2026-05-04-closed-loop-harness-mvp-ui-component-design-cn.md`

**MVP UI implementation plan:** `docs/superpowers/plans/2026-05-04-closed-loop-harness-mvp-ui.md`

---

## Implementation Status On 2026-05-05

Completed backend slices:

```text
P0 data support:
  schema tables
  HarnessRepository
  HarnessService
  /api/social-events
  /api/attention-seeds
  /api/harness-snapshots
  /api/harness-outcomes
  /api/harness-credits
  /api/harness-weights
  /api/harness-health
  /api/harness-score-buckets
  CLI read commands

P1 strict social-event-v1 extraction:
  OpenAI chat client now uses strict JSON schema response_format
  parser contract is evidence-bound social event extraction

P2 shadow snapshot loop:
  watched LLM job -> model_run -> social_event_extraction
  -> attention_seed -> event_cluster -> immutable 6h/24h snapshots
  -> shadow harness_decisions

P3 settlement and credit:
  ops settle-harness
  ops attribute-harness-credits
  score bucket read model

P4 report-only learning:
  ops update-harness-weights
  harness_weights status remains report_only
```

Still intentionally out of scope:

```text
external news sources
embedding clustering
automatic config promotion
paper/live execution
LangGraph/MLflow dependencies
automatic weight influence on live scoring
```

Verification completed:

```bash
uv run pytest -q
uv run ruff check .
uv run python -m compileall src tests
cd web && npm run typecheck
cd web && npm test -- --run
cd web && npm run build
```

---

## Implementation Principles

1. Keep GMGN/X as the only input source in this phase.
2. Keep full-stream ingest deterministic and independent of LLM availability.
3. Replace the LLM output contract before adding scoring loops.
4. Do not preserve compatibility code for old narrative/enrichment response shapes.
5. Build backend/CLI reports before cockpit UI.
6. Record shadow decisions before any paper/live execution.
7. Use TDD for every behavior change.

## KISS Scope Gate

Before implementation, read the Chinese evaluation doc and enforce this MVP boundary:

```text
Stage 1:
  social-event-v1 contract
  social_event_extractions
  harness_snapshots
  shadow decisions

Stage 2:
  outcomes
  credits
  settle-harness CLI
  score bucket report

Stage 3:
  report-only weights
  candidate config evaluation

Stage 4:
  UI after backend reports show value
```

Do not pull these into the first implementation slice:

```text
external news sources
embedding clustering
automatic config promotion
paper/live execution
LangGraph/MLflow dependencies
large cockpit redesign
automatic weight influence on live scoring
```

## Current Backend Gap After MVP UI

The MVP cockpit now calls the Harness read models, but the backend does not yet expose them. Current live behavior is:

```text
GET /api/social-events       -> missing
GET /api/attention-seeds     -> missing
GET /api/harness-snapshots   -> missing
GET /api/harness-outcomes    -> missing
GET /api/harness-credits     -> missing
GET /api/harness-health      -> missing
```

Therefore the first backend slice is not "better scoring". It is durable data support:

```text
1. migrate SQLite to include harness tables
2. add HarnessRepository
3. add HarnessService read models
4. add the six MVP API endpoints above
5. return empty items from real tables when there is no harness data
6. do not derive fake rows from old narrative tables
```

The UI is allowed to show empty Harness state. The backend is not allowed to return 404 for the MVP Harness surface.

## Production Closed Loop Backend Architecture

Read the dedicated backend spec before implementation:

```text
docs/superpowers/specs/2026-05-04-closed-loop-harness-backend-production-cn.md
```

The production backend has four contexts:

```text
Evidence Context:
  raw_frames / events / entities / token mentions / token attributions / market snapshots

Social Extraction Context:
  watched job / strict social-event-v1 schema / social_event_extractions / model_runs

Harness Context:
  attention_seeds / event_clusters / harness_snapshots / decisions / outcomes / credits / weights

Retrieval Context:
  harness_service.py / harness_evaluation_service.py / /api/harness-* / CLI reports
```

The write path is:

```text
GMGN/X public stream
  -> deterministic ingest
  -> watched_social_event_extraction job
  -> strict LLM social-event-v1 extraction
  -> social_event_extractions
  -> attention_seeds
  -> event_clusters
  -> harness_snapshots
  -> harness_decisions with execution_mode=shadow
```

The settlement path is:

```text
due harness_snapshots
  -> price lookup from existing token market facts
  -> actual_return
  -> expected_return
  -> abnormal_return
  -> normalized_outcome
  -> harness_outcomes
  -> harness_credits
  -> report-only harness_weights
```

Key architecture constraints:

```text
Repository stores and reads. It does not score.
Scoring, settlement, and credit are pure pipeline modules.
Snapshot rows are immutable once created.
Outcome and credit writes are idempotent.
Weights are report_only until config evaluation exists.
Baseline v0 can be expected_return=0 if no reliable benchmark feed exists.
```

## Revised Delivery Order

The previous stage list remains valid, but implementation should be executed in this practical production order:

```text
P0: Data support for MVP UI
  - schema tables
  - HarnessRepository
  - HarnessService
  - /api/social-events
  - /api/attention-seeds
  - /api/harness-snapshots
  - /api/harness-outcomes
  - /api/harness-credits
  - /api/harness-health
  - CLI list commands

P1: Strict social-event-v1 extraction
  - replace old LLM narrative output contract
  - persist social_event_extractions
  - preserve model_runs audit

P2: Shadow snapshot loop
  - extraction -> seed -> cluster -> immutable snapshot
  - record shadow decisions
  - publish websocket update after store commit

P3: Settlement and credit
  - ops settle-harness
  - ops attribute-harness-credits
  - score bucket report

P4: Report-only learning loop
  - harness_weights
  - evaluation report
  - candidate config comparison

P5: Paper/canary/live
  - out of scope
  - requires separate risk spec and explicit approval
```

P0 is considered complete only when the cockpit no longer sees 404 from the Harness endpoints.

## Breaking-Change Policy

This implementation intentionally breaks the old narrative product contract.

Do not implement:

- old `narratives` JSON parser fallback;
- compatibility derivation from `SocialEventExtraction` back into `NarrativeItem`;
- dual writes to old and new semantic tables just to keep old endpoints alive;
- UI fallback from harness fields to old narrative labels;
- historical narrative-row reinterpretation as new social-event output;
- old API response compatibility for narrative/enrichment surfaces.

Allowed reuse:

- `events`, raw evidence, entity extraction, token mentions, token attributions, token identities, token market snapshots;
- watched enrichment job scheduling;
- model run audit records;
- token-linking facts if rewritten around attention seeds.

The difference is important: factual infrastructure can stay; old product semantics cannot.

## Stage 0: Baseline And Documentation

**Purpose:** Make sure the branch starts clean and the design is reviewed before implementation.

**Files:**

- Create: `docs/superpowers/specs/2026-05-04-closed-loop-social-event-harness-design.md`
- Create/modify: `docs/superpowers/plans/2026-05-04-closed-loop-social-event-harness.md`

- [ ] Run baseline tests:

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

- [ ] Review current enrichment and narrative linking files:

```text
src/gmgn_twitter_intel/pipeline/llm_enrichment.py
src/gmgn_twitter_intel/pipeline/llm_client.py
src/gmgn_twitter_intel/pipeline/enrichment_worker.py
src/gmgn_twitter_intel/pipeline/narrative_seed_builder.py
src/gmgn_twitter_intel/pipeline/narrative_token_linker.py
src/gmgn_twitter_intel/storage/enrichment_repository.py
src/gmgn_twitter_intel/storage/sqlite_schema.py
```

- [ ] Confirm no implementation begins until the spec/plan is accepted.

## Stage 1: Strict Social Event Extraction Contract

**Purpose:** Replace narrative-first LLM output with evidence-bound social-event extraction.

**Files:**

- Create: `src/gmgn_twitter_intel/pipeline/social_event_extraction.py`
- Modify: `src/gmgn_twitter_intel/pipeline/llm_client.py`
- Modify or replace: `src/gmgn_twitter_intel/pipeline/llm_enrichment.py`
- Test: `tests/test_social_event_extraction.py`
- Test: `tests/test_llm_client.py`
- Test: `tests/test_llm_enrichment.py`

### Required Behaviors

- [ ] Define dataclasses:

```text
AnchorTerm
SocialTokenCandidate
SocialEventExtraction
```

- [ ] Define enum sets:

```text
EVENT_TYPES
ATTENTION_MECHANISMS
DIRECTION_HINTS
ANCHOR_ROLES
SEMANTIC_RISKS
SOURCE_ACTIONS
```

- [ ] Implement `build_social_event_prompt(event, entities)`.

- [ ] Implement `social_event_response_format()` returning strict OpenAI JSON schema.

- [ ] Implement `parse_social_event_response(raw_response, event_text, min_confidence=0.55)`.

- [ ] Parser must:

```text
clamp numeric hints to [0, 1]
reject invalid enum values
require evidence substring for anchors and token candidates
dedupe anchor terms by normalized term + role
dedupe token candidates by address or symbol/project/evidence
downgrade signal to non_signal when no valid anchor exists
preserve raw_response for audit
```

### TDD Steps

- [ ] Write parser tests first:

```bash
uv run pytest tests/test_social_event_extraction.py -v
```

Expected before code: `ModuleNotFoundError`.

- [ ] Implement the minimal module.

- [ ] Update LLM client tests to assert:

```text
response_format.type == "json_schema"
json_schema.name == "social_event_extraction"
json_schema.strict is True
result.event_type is parsed from the fake response
```

- [ ] Run:

```bash
uv run pytest tests/test_social_event_extraction.py tests/test_llm_client.py tests/test_llm_enrichment.py -v
```

### Breaking Contract Decision

Remove acceptance of old narrative-only payloads. Existing tests that assert old JSON mode narrative payloads are accepted should be deleted or rewritten around `social-event-v1`.

New runtime consumers must read `SocialEventExtraction` directly. Do not create fake `NarrativeItem` rows from anchor terms to keep old retrieval/UI code working.

## Stage 2: Harness Schema And Repository

**Purpose:** Persist the closed-loop state machine while keeping only factual ingest stable.

**Files:**

- Modify: `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- Create: `src/gmgn_twitter_intel/storage/harness_repository.py`
- Test: `tests/test_harness_repository.py`
- Modify: `tests/test_sqlite_schema.py`
- Modify: `tests/test_project_structure.py`

### Tables

- [ ] Add `social_event_extractions`.
- [ ] Add `event_clusters`.
- [ ] Add `harness_snapshots`.
- [ ] Add `harness_decisions`.
- [ ] Add `harness_outcomes`.
- [ ] Add `harness_credits`.
- [ ] Add `harness_weights`.

### Repository Methods

- [ ] `upsert_social_event_extraction(event, run_id, extraction, provider, model)`.
- [ ] `social_event_for_event(event_id)`.
- [ ] `list_social_events(window_ms, limit, handles=None, event_types=None)`.
- [ ] `upsert_event_cluster(...)`.
- [ ] `create_snapshot(...)`.
- [ ] `record_decision(...)`.
- [ ] `record_outcome(...)`.
- [ ] `record_credits(...)`.
- [ ] `upsert_weight(...)`.
- [ ] `list_snapshots(...)`, `list_outcomes(...)`, `list_credits(...)`, `list_weights(...)`.

### Legacy Removal

- [ ] Remove old narrative product tables from active read paths when equivalent harness read paths exist.
- [ ] Remove old parser tests and API tests that depend on `narrative_label` as trader-facing truth.
- [ ] If schema mismatch rebuild logic is used, allow old app tables to be cleared rather than migrated into the new harness shape.

### TDD Steps

- [ ] Write failing repository tests for:

```text
tables exist after migrate
extraction upsert is idempotent by event_id
JSON fields decode correctly
snapshot is immutable or replace-protected
decision records shadow mode
outcome records normalized_outcome
credit rows store responsibility and credit
weight update changes n/mean_credit/weight
```

- [ ] Run:

```bash
uv run pytest tests/test_harness_repository.py tests/test_sqlite_schema.py -v
```

Expected before code: missing repository/tables.

- [ ] Implement schema version bump and repository.

- [ ] Run focused tests until green.

### Design Constraint

Do not put all harness behavior into `enrichment_repository.py`. That file is already large. Use a focused repository so harness state remains understandable.

## Stage 3: Deterministic Scoring And Policy

**Purpose:** Move all decision-like logic into pure, testable harness math.

**Files:**

- Create: `src/gmgn_twitter_intel/pipeline/harness_scoring.py`
- Test: `tests/test_harness_scoring.py`

### Functions

- [ ] `base_event_score(direction, impact, confidence, novelty, pricedness)`.
- [ ] `price_move_penalty(pre_move, recent_vol)`.
- [ ] `event_score(base_score, source_weight, event_type_weight, horizon_weight, time_decay, price_move_penalty)`.
- [ ] `combined_score(event_scores)`.
- [ ] `policy_signal(combined_score, long_threshold, short_threshold)`.
- [ ] `shadow_signal(combined_score, long_threshold, short_threshold)`.
- [ ] `apply_risk_caps(score, risks)`.

### TDD Cases

- [ ] Positive event with high novelty scores positive.
- [ ] Negative event scores negative.
- [ ] High pricedness reduces score.
- [ ] Large pre-move caps penalty.
- [ ] Missing market data adds risk and prevents driver/paper decisions.
- [ ] Shadow threshold is lower than paper threshold.

Run:

```bash
uv run pytest tests/test_harness_scoring.py -v
```

## Stage 4: Snapshot Builder

**Purpose:** Freeze decision-time state using only pre-decision information.

**Files:**

- Create: `src/gmgn_twitter_intel/pipeline/harness_snapshot_builder.py`
- Modify: `src/gmgn_twitter_intel/pipeline/enrichment_worker.py`
- Modify: `src/gmgn_twitter_intel/api/app.py`
- Test: `tests/test_harness_snapshot_builder.py`
- Test: `tests/test_enrichment_worker.py`

### Behavior

- [ ] Build one initial cluster per valid social event extraction.
- [ ] Use deterministic token evidence or major asset hints for asset expression.
- [ ] Skip paper decision when asset is unknown.
- [ ] Always record shadow decision when there is a valid signal event.
- [ ] Store config versions:

```text
config_version
prompt_version
schema_version
scoring_version
weight_version
policy_version
risk_version
baseline_version
```

- [ ] Make snapshot creation idempotent for `(event_id, asset, horizon, config_version)`.

### TDD Cases

- [ ] Watched event with social extraction creates extraction, cluster, snapshot, and shadow decision.
- [ ] Non-signal extraction stores extraction but no snapshot.
- [ ] Unknown asset creates attention seed but no paper decision.
- [ ] Token-flow factual tests still pass, while old narrative publish payload expectations are removed or rewritten.

Run:

```bash
uv run pytest tests/test_harness_snapshot_builder.py tests/test_enrichment_worker.py -v
```

## Stage 5: Settlement And Credit

**Purpose:** Close the loop by converting predictions into settled abnormal-return outcomes and event credits.

**Files:**

- Create: `src/gmgn_twitter_intel/pipeline/harness_settlement.py`
- Create: `src/gmgn_twitter_intel/pipeline/harness_credit.py`
- Test: `tests/test_harness_settlement.py`
- Test: `tests/test_harness_credit.py`

### Functions

- [ ] `actual_return(entry_price, exit_price)`.
- [ ] `expected_return(benchmark_returns, momentum_return, weights)`.
- [ ] `abnormal_return(actual_return, expected_return)`.
- [ ] `normalized_outcome(abnormal_return, realized_vol)`.
- [ ] `assign_cluster_credits(snapshot_clusters, normalized_outcome)`.
- [ ] `update_weight_stat(existing, credit, n0=50, lambda_=0.5)`.

### TDD Cases

- [ ] Abnormal return subtracts baseline.
- [ ] Normalized outcome clips to `[-1, 1]`.
- [ ] Multi-event snapshot splits responsibility by absolute event score.
- [ ] Negative event receives negative credit when abnormal return is positive.
- [ ] Weight update is slow when sample size is small.
- [ ] Weight is clipped to `[0.5, 1.5]`.

Run:

```bash
uv run pytest tests/test_harness_settlement.py tests/test_harness_credit.py -v
```

## Stage 6: Settlement CLI Ops

**Purpose:** Let operators run the closed loop manually before scheduling jobs.

**Files:**

- Modify: `src/gmgn_twitter_intel/cli.py`
- Test: `tests/test_cli.py`

### Commands

- [ ] `gmgn-twitter-intel ops settle-harness --horizon 6h`.
- [ ] `gmgn-twitter-intel ops attribute-harness-credits --horizon 6h`.
- [ ] `gmgn-twitter-intel ops update-harness-weights`.

### Behavior

- [ ] Commands output JSON counts:

```text
snapshots_scanned
outcomes_written
credits_written
weights_updated
skipped_missing_market
errors
```

- [ ] Re-running commands does not duplicate outcomes or credits.

Run:

```bash
uv run pytest tests/test_cli.py -v
```

## Stage 7: Read Models, API, And CLI Reports

**Purpose:** Make the harness inspectable.

**Files:**

- Create: `src/gmgn_twitter_intel/retrieval/harness_service.py`
- Modify: `src/gmgn_twitter_intel/api/http.py`
- Modify: `src/gmgn_twitter_intel/cli.py`
- Test: `tests/test_api_http.py`
- Test: `tests/test_cli.py`

### New Read APIs

- [ ] `/api/social-events`.
- [ ] `/api/harness-snapshots`.
- [ ] `/api/harness-outcomes`.
- [ ] `/api/harness-credits`.
- [ ] `/api/harness-weights`.
- [ ] `/api/harness-score-buckets`.

### New CLI Commands

- [ ] `social-events`.
- [ ] `harness-snapshots`.
- [ ] `harness-outcomes`.
- [ ] `harness-credits`.
- [ ] `harness-weights`.
- [ ] `harness-score-buckets`.

### Output Requirements

Every row should expose:

```text
event evidence
source account
anchor terms
asset expression
score components
decision mode
outcome status
credit status
config versions
risks
```

Run:

```bash
uv run pytest tests/test_api_http.py tests/test_cli.py -v
```

## Stage 8: Narrative Token Link Reconciliation

**Purpose:** Reuse deterministic token-link evidence as the tradability bridge, without preserving old narrative semantics.

**Files:**

- Modify: `src/gmgn_twitter_intel/pipeline/narrative_seed_builder.py`
- Modify: `src/gmgn_twitter_intel/pipeline/narrative_token_linker.py`
- Modify: `src/gmgn_twitter_intel/retrieval/narrative_link_service.py`
- Test: `tests/test_narrative_seed_builder.py`
- Test: `tests/test_narrative_token_linker.py`

### Behavior

- [ ] Create attention seeds from social event anchors.
- [ ] Link tokens only through deterministic post-seed evidence.
- [ ] Preserve risk concepts as new harness/link risks:

```text
coverage_public_stream
unresolved_symbol
market_missing
author_concentration_high
repeat_seed
```

- [ ] Feed token-link results into snapshot asset expression when a seed has no direct token at extraction time.

Run:

```bash
uv run pytest tests/test_narrative_seed_builder.py tests/test_narrative_token_linker.py -v
```

## Stage 9: Evaluation Reports

**Purpose:** Prove whether the harness has predictive value.

**Files:**

- Create: `src/gmgn_twitter_intel/retrieval/harness_evaluation_service.py`
- Test: `tests/test_harness_evaluation_service.py`

### Reports

- [ ] Score buckets:

```text
<= -0.8
-0.8 to -0.4
-0.4 to 0.4
0.4 to 0.8
>= 0.8
```

- [ ] Average normalized abnormal return by bucket.
- [ ] Hit rate by bucket.
- [ ] Average credit by source.
- [ ] Average credit by event type.
- [ ] Average credit by horizon.
- [ ] Sample size per bucket.
- [ ] Weight drift top gainers/losers.

Run:

```bash
uv run pytest tests/test_harness_evaluation_service.py -v
```

## Stage 10: Documentation Update And Breaking Change Notes

**Files:**

- Modify: `README.md`
- Optional modify: `AGENTS.md`

- [ ] Document the new harness loop.
- [ ] Document that LLM only extracts social events.
- [ ] Document that no external news sources are added in V1.
- [ ] Document that old narrative/enrichment compatibility is intentionally removed.
- [ ] Document which endpoints are removed, renamed, or semantically rewritten.
- [ ] Document that old narrative rows are not migrated unless replayed through the new extractor.
- [ ] Document CLI/API examples.
- [ ] Document settlement and credit commands.
- [ ] Document caveats:

```text
public_stream coverage only
shadow first
no live trading
unresolved symbols are high risk
abnormal return is baseline-dependent
credit is not causal proof
```

## Stage 11: Optional Cockpit UI

Do this only after CLI/API reports show useful data.

Use the dedicated UI implementation plan for task-level execution:

```text
docs/superpowers/plans/2026-05-04-closed-loop-harness-mvp-ui.md
```

**Files:**

- Modify: `web/src/api/types.ts`
- Modify: `web/src/App.tsx`
- Add focused components listed in `docs/superpowers/specs/2026-05-04-closed-loop-harness-mvp-ui-component-design-cn.md`.

### Views

- [ ] Replace `NarrativePanel` with `HarnessPanel`.
- [ ] Add `SocialEventFeed`, `AttentionSeedList`, and `HarnessHealthStrip`.
- [ ] Replace token drawer `Narratives` tab with `HarnessTokenTab`.
- [ ] Add `SnapshotLedger`, `OutcomeCard`, and `CreditLedger`.
- [ ] Add `ScoreBucketPanel` and `SettlementCoveragePanel` only after outcome reports exist.
- [ ] Keep `WeightDriftPanel` report-only until candidate config evaluation is implemented.

### UI Principle

The cockpit must not imply the LLM is making trade decisions. Labels should say:

```text
Extracted Event
Harness Score
Shadow Decision
Outcome Pending
Credit Assigned
```

## Stage 12: Full Verification

Run:

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

If web UI was changed:

```bash
cd web
npm run typecheck
npm test -- --run
npm run build
```

## Rollout Plan

### Phase A: Shadow Only

- Store extractions, snapshots, decisions.
- No settlement yet required for product display.
- Validate latency, schema success, invalid output rate.

### Phase B: Settled Shadow

- Run settlement for 6h and 24h horizons.
- Produce score bucket reports.
- No paper/live trading.

### Phase C: Paper Candidate

- Enable paper decisions only for configs with bucket monotonicity.
- Track cost-adjusted paper PnL.

### Phase D: Canary Live

Out of scope for this implementation plan. Requires separate approval and risk spec.

## Success Criteria

Implementation is successful when:

- every watched LLM event has a durable extraction state;
- signal events create auditable snapshots;
- shadow decisions can be listed and replayed;
- settled outcomes use abnormal return;
- credits are assigned across all snapshot clusters;
- weights update slowly with shrinkage;
- score bucket report can show whether the system has edge;
- full-stream ingest and token-flow still pass existing tests.

## Expected Effect

Expected positive effect:

- narrative flow stops being the primary product surface;
- high-value account posts become structured attention seeds;
- system can distinguish "interesting story" from "tradable uptake";
- stale/news-after-price-move risk becomes explicit;
- iteration becomes measurable through abnormal return and credit.

Expected cost:

- more backend complexity;
- more operational jobs;
- more storage tables;
- more time before UI payoff.

Expected risk reduction:

- fewer LLM hallucination-driven signals;
- less single-event overfitting;
- lower chance of shipping unmeasurable narrative heuristics;
- cleaner path from shadow to paper to live.

## Detailed Impact Summary

### Breaking Areas

- `llm_enrichment.py` no longer accepts the old `summary + narratives + stance + intent` contract as product truth.
- `tests/test_llm_enrichment.py` and `tests/test_llm_client.py` must be rewritten for `social-event-v1`.
- Old narrative API and WebSocket response shapes should be removed or rebuilt over new harness read models.
- Cockpit narrative UI should be replaced with social event, attention seed, snapshot, and credit views.
- Historical narrative rows do not appear in new harness reports without explicit replay.

### Stable Areas

- raw GMGN/X event ingestion;
- deterministic entity extraction;
- token identity resolution;
- token mention and attribution facts;
- token market snapshots;
- full-stream token-flow factual base;
- watched-account-only LLM scheduling.

### Expected Product Effect

- Fewer but higher-quality surfaced signals.
- Clearer separation between "attention seed" and "tradable token uptake".
- Easier post-mortems because every signal has snapshot/outcome/credit state.
- Initial UI may feel less full because old narrative labels are not carried over.

### Expected Trading Effect

- Reduced stale-news chasing through explicit pre-move/pricedness penalty.
- Reduced LLM hallucination risk because unresolved semantic ideas cannot become driver decisions.
- Score bucket monotonicity becomes the main proof of edge.
- Some event types may be proven useless and down-weighted or removed.

### Expected Engineering Effect

- Short-term test churn is high because old contract tests should fail and be replaced.
- Long-term complexity is lower than dual-running two semantic systems.
- Storage grows, but every table has a closed-loop purpose.
- Debugging becomes cleaner because failures can be assigned to extraction, scoring, settlement, credit, or weight update.

### Expected Operational Effect

- Operators must run or schedule settlement/credit/weight jobs.
- Config promotion requires report review, not ad hoc prompt changes.
- Schema migrations may require app-table rebuilds.
- Shadow/paper/live promotion becomes a separate operational discipline.
