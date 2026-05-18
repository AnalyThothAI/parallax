# Unified Agent Runtime Phase 0b Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 owning spec 把 Signal Pulse 从单 recommendation agent hard cut 升级为统一 Agent Runtime Core 的第一个落地策略：token_target 走 CEX/Meme route 的 Analyst → Critic → Judge 三阶段；source_seed 未解析 target 时 deterministic research-only / abstain；完整 stage replay 入库；public Signal Pulse item 改为 `decision` block。

**Architecture:** `pulse_lab` 继续拥有领域决策、gate、worker、repository、read model；`integrations/openai_agents` 只实现 OpenAI Agents SDK stage adapter；`app/runtime/providers_wiring.py` 负责把 adapter 注入 domain provider protocol。Route policy、completeness gate、decision mapping 属于 domain service，不放进 integrations。PostgreSQL 继续是唯一持久化 ledger。

**Tech Stack:** Python 3.12, PostgreSQL, Alembic, Pydantic, OpenAI Agents SDK, pytest, ruff, React/Vitest 仅在 public contract/UI 受影响时触达。

---

## Status

**Status**: Implemented pending final full-suite verification
**Date**: 2026-05-14
**Owning spec**: `docs/superpowers/specs/active/2026-05-13-target-agent-architecture-design-cn.md`
**Worktree**: `.worktrees/unified-agent-runtime-phase-0b/`
**Branch**: `codex/unified-agent-runtime-phase-0b`

## Current Code Anchors

| Area | Current anchor | Plan stance |
|---|---|---|
| Provider protocol | `src/gmgn_twitter_intel/domains/pulse_lab/providers.py` | Add decision-oriented provider result/protocol; retire direct single recommendation semantics from worker |
| Existing recommendation schema | `src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_recommendation.py` | Delete/retire old schema and replace callers with decision schema |
| Single OpenAI agent | `src/gmgn_twitter_intel/integrations/openai_agents/pulse_recommendation_agent_client.py` | Delete old client and replace with stage runner client |
| Worker orchestration | `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py` | Preserve job queue/poll/wake/retry shape; replace `_run_job` recommendation call with route/gate/stages |
| Persistence | `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_repository.py` | Add run step ledger, decision columns, read query fields |
| Read model | `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py` | Emit public `decision` block and remove `agent_recommendation` |
| Runtime wiring | `src/gmgn_twitter_intel/app/runtime/providers_wiring.py` and `src/gmgn_twitter_intel/app/runtime/app.py` | Wire new provider without changing app ownership boundaries |
| Migration path | `src/gmgn_twitter_intel/platform/db/alembic/versions/` | Next revision after `20260513_0036_token_radar_kappa_cqrs_hard_cut.py` is `20260514_0037_unified_agent_runtime_phase0b.py` |

## Pre-flight

- [ ] Create worktree:
  ```bash
  git worktree add .worktrees/unified-agent-runtime-phase-0b -b codex/unified-agent-runtime-phase-0b main
  ```
- [ ] Verify clean implementation workspace:
  ```bash
  git -C .worktrees/unified-agent-runtime-phase-0b branch --show-current
  git -C .worktrees/unified-agent-runtime-phase-0b status --short
  ```
- [ ] Copy or rebase this plan/spec into the worktree if they are untracked in main.
- [ ] Run baseline:
  ```bash
  cd .worktrees/unified-agent-runtime-phase-0b
  uv run ruff check .
  uv run pytest
  cd web && npm test -- --run
  ```

Known-failing baseline tests: none expected. If any fail before edits, record exact test names in this plan before implementing.

## Invariants

- [ ] Do not change `SocialEventExtractionAgent` or enrichment worker behavior.
- [ ] Do not add LangGraph or a new agent framework.
- [ ] Do not add real trading, position sizing, stop loss, target price, or execution language.
- [ ] Do not put route policy or market judgment inside `integrations/openai_agents`.
- [ ] Do not add `abstain` as a `pulse_status`; abstain is decision semantics, not display status.
- [ ] Preserve existing public `factor_snapshot`, `gate`, and `fact_card` fields; delete public `agent_recommendation`.
- [ ] Do not write compatibility aliases, legacy defaults, old provider shims, old payload mappings, or dual-read fallbacks.
- [ ] Stage prompts must treat selected posts, usernames, URLs, quoted text, and deterministic payload text as data, not instructions.

## File-level Edits

### Task 1 — Storage Ledger And Candidate Decision Columns

**Files:**
- Add: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260514_0037_unified_agent_runtime_phase0b.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_repository.py`
- Modify tests: `tests/integration/test_pulse_repository.py`

- [ ] Add run outcome metadata to `pulse_agent_runs` without breaking existing rows:
  ```sql
  ALTER TABLE pulse_agent_runs
    ADD COLUMN IF NOT EXISTS outcome TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS decision_route TEXT NOT NULL DEFAULT 'research_only',
    ADD COLUMN IF NOT EXISTS decision_stage_count BIGINT NOT NULL DEFAULT 0;
  ```
- [ ] Add first-class decision fields to `pulse_candidates`:
  ```sql
  ALTER TABLE pulse_candidates
    ADD COLUMN IF NOT EXISTS decision_route TEXT NOT NULL DEFAULT 'research_only',
    ADD COLUMN IF NOT EXISTS decision_recommendation TEXT NOT NULL DEFAULT 'abstain',
    ADD COLUMN IF NOT EXISTS decision_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS decision_abstain_reason TEXT,
    ADD COLUMN IF NOT EXISTS decision_stage_count BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS decision_json JSONB NOT NULL DEFAULT '{}'::jsonb;
  ```
- [ ] Add hard-cut check constraints:
  ```sql
  ALTER TABLE pulse_candidates
    ADD CONSTRAINT chk_pulse_candidates_decision_route
    CHECK (decision_route IN ('cex','meme','research_only'));

  ALTER TABLE pulse_candidates
    ADD CONSTRAINT chk_pulse_candidates_decision_recommendation
    CHECK (decision_recommendation IN (
      'high_conviction','trade_candidate','watchlist','ignore','abstain'
    ));

  ALTER TABLE pulse_candidates
    ADD CONSTRAINT chk_pulse_candidates_decision_confidence
    CHECK (decision_confidence IS NULL OR (decision_confidence >= 0 AND decision_confidence <= 1));
  ```
- [ ] Add stage replay table:
  ```sql
  CREATE TABLE IF NOT EXISTS pulse_agent_run_steps (
    step_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES pulse_agent_runs(run_id) ON DELETE CASCADE,
    stage TEXT NOT NULL CHECK (stage IN ('analyst','critic','judge','research_only_gate')),
    route TEXT NOT NULL CHECK (route IN ('cex','meme','research_only')),
    attempt_index BIGINT NOT NULL DEFAULT 0,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    prompt_text TEXT NOT NULL DEFAULT '',
    response_json JSONB,
    trace_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    usage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    latency_ms BIGINT NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('ok','failed','timeout','skipped')),
    error TEXT,
    started_at_ms BIGINT NOT NULL,
    finished_at_ms BIGINT NOT NULL,
    created_at_ms BIGINT NOT NULL,
    UNIQUE(run_id, stage, attempt_index)
  );
  CREATE INDEX IF NOT EXISTS idx_pulse_agent_run_steps_run_stage
    ON pulse_agent_run_steps(run_id, stage, attempt_index);
  CREATE INDEX IF NOT EXISTS idx_pulse_candidates_decision_latest
    ON pulse_candidates(pulse_version, "window", scope, decision_route, decision_recommendation, updated_at_ms DESC);
  ```
- [ ] Drop old recommendation storage after decision fields exist:
  ```sql
  ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS agent_recommendation_json;
  ```
- [ ] Extend repository methods:
  - `insert_agent_run_step(step_id: str, run_id: str, stage: str, route: str, attempt_index: int, provider: str, model: str, prompt_version: str, schema_version: str, input_json: dict[str, Any], prompt_text: str, response_json: dict[str, Any] | None, trace_metadata_json: dict[str, Any], usage_json: dict[str, Any], latency_ms: int, status: str, error: str | None) -> dict[str, Any]`
  - `list_agent_run_steps(run_id: str) -> list[dict[str, Any]]`
  - add `outcome: str`, `decision_route: str`, `decision_stage_count: int` to `insert_agent_run(...)` / `finish_agent_run(...)`
  - add `decision_route: str`, `decision_recommendation: str`, `decision_confidence: float | None`, `decision_abstain_reason: str | None`, `decision_stage_count: int`, `decision_json: dict[str, Any]` to `upsert_candidate(...)`
  - select decision fields in candidate list/detail queries
- [ ] Tests:
  - `tests/integration/test_pulse_repository.py::test_agent_run_steps_round_trip`
  - `tests/integration/test_pulse_repository.py::test_candidate_decision_columns_round_trip`
  - `tests/integration/test_pulse_repository.py::test_candidate_upsert_rejects_missing_decision_fields`
- [ ] Run:
  ```bash
  uv run pytest tests/integration/test_pulse_repository.py -q
  ```

### Task 2 — Decision Schemas And Hard-Cut Mapping

**Files:**
- Add: `src/gmgn_twitter_intel/domains/pulse_lab/types/agent_decision.py`
- Delete: `src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_recommendation.py`
- Add: `src/gmgn_twitter_intel/domains/pulse_lab/services/decision_mapping.py`
- Add tests: `tests/unit/test_pulse_agent_decision.py`

- [ ] Define strict Pydantic schemas with `extra="forbid"`:
  ```python
  DecisionRoute = Literal["cex", "meme", "research_only"]
  DecisionRecommendation = Literal[
      "high_conviction", "trade_candidate", "watchlist", "ignore", "abstain"
  ]

  class AnalystOpinion(BaseModel):
      route: DecisionRoute
      recommendation: Literal["trade_candidate", "watchlist", "ignore"]
      confidence: float = Field(ge=0, le=1)
      summary_zh: str
      evidence: list[str]

  class CritiqueReport(BaseModel):
      route: DecisionRoute
      weaknesses: list[str]
      missing_fact_impacts: list[str]
      confidence_ceiling: float = Field(ge=0, le=1)
      should_abstain: bool

  class FinalDecision(BaseModel):
      route: DecisionRoute
      recommendation: DecisionRecommendation
      confidence: float = Field(ge=0, le=1)
      abstain_reason: str | None
      summary_zh: str
      invalidation_conditions: list[str]
      residual_risks: list[str]
      evidence_event_ids: list[str]

  class StageRunAudit(BaseModel):
      stage: Literal["analyst", "critic", "judge", "research_only_gate"]
      route: DecisionRoute
      attempt_index: int
      input_json: dict[str, Any]
      prompt_text: str
      response_json: dict[str, Any] | None
      usage_json: dict[str, Any]
      latency_ms: int
      status: Literal["ok", "failed", "timeout", "skipped"]
      error: str | None

  class PulseDecisionPayload(BaseModel):
      final_decision: FinalDecision
      stage_audits: tuple[StageRunAudit, ...]
  ```
- [ ] Validators:
  - confidence and confidence ceiling must be `0 <= value <= 1`
  - `recommendation="abstain"` requires non-empty `abstain_reason`
  - non-abstain decisions must have at least one evidence or residual risk
  - reject trading execution language using the existing forbidden-language pattern
- [ ] Hard-cut mapping:
  - map `FinalDecision` directly to candidate `decision_*` columns
  - map final recommendation to `score_band` only for existing list/filter semantics
  - do not create `PulseRecommendationPayload`
  - do not write `agent_recommendation_json`
- [ ] Tests:
  - `test_final_decision_requires_abstain_reason`
  - `test_final_decision_rejects_execution_language`
  - `test_high_conviction_maps_to_candidate_decision_fields`
  - `test_watchlist_maps_to_candidate_decision_fields`
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_pulse_agent_decision.py -q
  ```

### Task 3 — Domain Route Policy And Completeness Gate

**Files:**
- Add: `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_routing.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py` only if existing gate result needs an extra reason exposed to routing
- Add tests: `tests/unit/test_pulse_agent_routing.py`

- [ ] Implement route policy as pure functions that accept the existing `PulseCandidateContext` / factor snapshot dict:
  - token_target with CEX venue/perp-like context -> `cex`
  - token_target with DEX/new-pair/meme-like context -> `meme`
  - no resolved target -> `research_only`
- [ ] Implement completeness result:
  ```python
  @dataclass(frozen=True, slots=True)
  class CompletenessResult:
      route: DecisionRoute
      score: float
      hard_blocked: bool
      missing_fields: tuple[str, ...]
      stale_fields: tuple[str, ...]
      blockers: tuple[str, ...]
  ```
- [ ] Hard-block rules:
  - `research_only` hard-blocks LLM asset stages
  - missing `market.decision_latest` hard-blocks CEX/Meme
  - `market.readiness.blockers` with DEX floor facts hard-blocks Meme unless route policy explicitly marks research-only
  - cohort statuses `cohort_insufficient`, `cohort_all_tied`, `cohort_no_signal` hard-block high conviction and should normally abstain before LLM
- [ ] Thresholds:
  - Meme hard gate target: `score < 0.60`
  - CEX hard gate target: `score < 0.80`
  - soft warning fields flow to Critic but do not block
- [ ] Tests:
  - `test_source_seed_routes_research_only_without_llm`
  - `test_missing_decision_latest_hard_blocks_token_target`
  - `test_meme_dex_floor_unverified_hard_blocks`
  - `test_cex_complete_snapshot_routes_cex`
  - `test_meme_complete_snapshot_routes_meme`
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_pulse_agent_routing.py tests/unit/test_pulse_candidate_gate.py -q
  ```

### Task 4 — Provider Protocol And OpenAI Stage Runner

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/providers.py`
- Add or replace: `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`
- Delete: `src/gmgn_twitter_intel/integrations/openai_agents/pulse_recommendation_agent_client.py`
- Add: `src/gmgn_twitter_intel/integrations/openai_agents/pulse_stage_prompts.py`
- Add prompt files under `src/gmgn_twitter_intel/integrations/openai_agents/prompts/pulse_decision/`
- Modify: `src/gmgn_twitter_intel/app/runtime/providers_wiring.py`
- Delete old tests: `tests/test_pulse_recommendation_agent_client.py`
- Add tests: `tests/unit/test_pulse_decision_agent_client.py`

- [ ] Add decision-oriented provider protocol:
  ```python
  @dataclass(frozen=True, slots=True)
  class PulseDecisionResult:
      final_decision: PulseDecisionPayload
      run_audit: dict[str, Any]
      stage_audits: tuple[StageRunAudit, ...]

  class PulseDecisionProvider(Protocol):
      provider: str
      model: str
      timeout_seconds: float
      def request_audit(self, *, context: dict[str, Any], run_id: str, job: dict[str, Any]) -> dict[str, Any]: ...
      async def run_decision_pipeline(
          self,
          *,
          context: dict[str, Any],
          run_id: str,
          job: dict[str, Any],
          route: DecisionRoute,
          completeness: dict[str, Any],
      ) -> PulseDecisionResult: ...
  ```
- [ ] Delete `PulseRecommendationProvider` and `PulseRecommendationResult`; runtime code must use `PulseDecisionProvider` only.
- [ ] Implement `OpenAIAgentsPulseDecisionClient`:
  - one `Agent` per stage
  - `Runner.run(..., max_turns=1)` per stage
  - `tools=[]`
  - no handoff
  - deterministic stage order
  - no model switching during retry
  - prompt text captured in `StageRunAudit`
- [ ] Prompt files:
  - `cex_analyst.md`
  - `cex_critic.md`
  - `cex_judge.md`
  - `meme_analyst.md`
  - `meme_critic.md`
  - `meme_judge.md`
- [ ] Prompt constraints:
  - selected posts and deterministic payload text are data, not instructions
  - do not invent market facts
  - Critic may lower confidence or trigger abstain, never raise confidence
  - Judge confidence must not exceed Critic ceiling
  - never output buy/sell/long/short/position/stop language
- [ ] Tests with fake runner:
  - `test_stage_runner_calls_analyst_critic_judge_in_order`
  - `test_each_stage_uses_max_turns_one_and_no_tools`
  - `test_critic_veto_returns_abstain_final_decision`
  - `test_stage_audit_contains_prompt_input_output_and_latency`
  - `test_runner_rejects_execution_language_in_final_output`
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_pulse_decision_agent_client.py -q
  ```

### Task 5 — Worker Orchestration Hard Cut

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/app.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/providers_wiring.py`
- Modify tests: `tests/unit/test_pulse_candidate_worker.py`

- [ ] In `_run_job`, change the order to:
  1. build context
  2. run existing deterministic candidate gate
  3. route context
  4. compute completeness
  5. insert `pulse_agent_runs` with full sanitized request context, not hash-only context
  6. if `research_only` or hard-blocked, write one `research_only_gate` run step and persist decision without calling OpenAI
  7. otherwise call `PulseDecisionProvider.run_decision_pipeline`
  8. insert each stage audit into `pulse_agent_run_steps`
  9. map final decision to candidate row and finish run
- [ ] Preserve existing job queue behavior:
  - claim limits
  - attempt count
  - cooldown
  - wake listener as hint
  - poll catch-up
  - timeout protection
- [ ] Error semantics:
  - stage timeout -> run outcome `error`, job retry if attempts remain
  - validation error -> run outcome `error`, job retry if attempts remain
  - hard-block/research-only -> run status `completed`, outcome `abstain_insufficient_data` or `research_only`
  - Critic veto -> run status `completed`, outcome `abstain_critic_veto`
- [ ] Candidate persistence:
  - do not add `pulse_status="abstain"`
  - keep existing gate-derived `pulse_status`
  - set `decision_recommendation="abstain"` and `decision_abstain_reason` for abstain
  - write `decision_json` as the complete final decision payload
  - do not write `agent_recommendation_json`
- [ ] Tests:
  - `test_source_seed_without_target_short_circuits_before_provider`
  - `test_missing_decision_latest_short_circuits_before_provider`
  - `test_successful_token_target_persists_three_stage_steps`
  - `test_critic_veto_persists_abstain_decision_without_judge_upgrade`
  - `test_stage_failure_marks_run_error_and_does_not_upsert_success_decision`
  - update existing tests that assert request hash only
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_pulse_candidate_worker.py tests/unit/test_pulse_candidate_gate.py -q
  ```

### Task 6 — Signal Pulse Read Model And Public Contract

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/http.py` only if response schema helpers require explicit docs
- Modify: `docs/CONTRACTS.md`
- Modify generated docs if contract tests require it
- Modify tests: `tests/unit/test_signal_pulse_service.py`, `tests/integration/test_cli.py` if CLI prints pulse fields
- Frontend only if TypeScript contract tests fail: `web/src/api/types.ts`, relevant Signal Lab components/tests

- [ ] Add `decision` block to each Signal Pulse item:
  ```json
  {
    "route": "meme",
    "recommendation": "trade_candidate",
    "confidence": 0.68,
    "abstain_reason": null,
    "stage_count": 3,
    "summary_zh": "社交热度有效，但 DEX floor 仍需继续确认。",
    "invalidation_conditions": ["decision_latest 失效或 liquidity 跌破 floor"],
    "residual_risks": ["单一 KOL 驱动，缺少多源确认"]
  }
  ```
- [ ] Keep existing `gate`, `factor_snapshot`, and `fact_card`; remove `agent_recommendation`.
- [ ] Default display should hide `decision.recommendation="abstain"` unless the caller explicitly requests diagnostic/all rows.
- [ ] Add summary counters:
  - `decision_route_counts`
  - `decision_recommendation_counts`
  - `decision_abstain_reason_counts`
  - `decision_error_count` if available from run rows
- [ ] Tests:
  - `test_pulse_item_includes_decision_block`
  - `test_default_listing_hides_abstain_decisions`
  - `test_agent_recommendation_is_removed_from_public_payload`
  - `test_summary_counts_decision_routes_and_abstain_reasons`
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_signal_pulse_service.py tests/integration/test_cli.py -q
  cd web && npm test -- --run
  ```

### Task 7 — Architecture And Safety Guards

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/RELIABILITY.md`
- Add or modify: architecture tests under `tests/architecture/`
- Modify: `docs/generated/cli-help.md` or `docs/generated/ws-protocol.md` only if regeneration detects public changes

- [ ] Document `Agent Runtime Core` under Pulse Lab architecture:
  - route policy in domain
  - OpenAI stage runner in integrations
  - provider wiring in app runtime
  - replay ledger in repository
- [ ] Document that `pulse_agent_run_steps.prompt_text` is operational audit data and must not include secrets, cookies, auth headers, or raw `.env`.
- [ ] Add architecture guard:
  - `domains/pulse_lab/services/agent_routing.py` must not import `agents` or OpenAI integration packages
  - `integrations/openai_agents` must not import repositories
  - stage prompt files must not contain execution words banned by the existing recommendation validator
- [ ] Run:
  ```bash
  uv run pytest tests/architecture/test_src_domain_architecture.py -q
  uv run ruff check .
  ```

### Task 8 — Soft Launch Verification Artefact

**Files:**
- Add: `docs/superpowers/plans/active/2026-05-14-unified-agent-runtime-phase-0b-verification-cn.md`
- Optional operational helper if already present patterns allow it: CLI/read-only report command under `app/surfaces/cli/`

- [ ] Add verification doc template with:
  - migration status
  - test outputs
  - sample run id with three steps
  - sample source_seed run id with research-only gate step
  - high_conviction rate
  - abstain rate
  - error rate
  - example public payload shape
- [ ] Add read-only SQL snippets for operators:
  ```sql
  SELECT decision_recommendation, count(*)
  FROM pulse_candidates
  WHERE updated_at_ms > (EXTRACT(EPOCH FROM NOW()) * 1000 - 7 * 24 * 3600 * 1000)
  GROUP BY decision_recommendation
  ORDER BY count(*) DESC;
  ```
  ```sql
  SELECT run_id, stage, route, status, latency_ms
  FROM pulse_agent_run_steps
  WHERE run_id = 'run_sample_id'
  ORDER BY started_at_ms, attempt_index;
  ```
- [ ] Capture at least one real or fixture-backed replay example before declaring completion.

## PR Breakdown

1. **PR 1 — Storage And Domain Types**: Tasks 1 and 2. Mergeable once repository and schema tests pass.
2. **PR 2 — Routing And Stage Adapter**: Tasks 3 and 4. Depends on PR 1; no worker behavior change yet if adapter is unused.
3. **PR 3 — Worker Hard Cut**: Task 5. Depends on PR 2; flips Pulse runtime to decision pipeline.
4. **PR 4 — Public Contract And Docs**: Tasks 6 and 7. Depends on PR 3; updates read model, frontend, docs, and architecture guards.
5. **PR 5 — Soft Launch Evidence**: Task 8. Can be the landing PR or a post-merge verification artefact after running on local/prod-like data.

## Rollout Order

1. Merge and apply migration:
   ```bash
   uv run alembic upgrade head
   ```
2. Deploy code with Pulse agent enabled only after migration is confirmed.
3. Run one local fixture-backed worker cycle with fake provider.
4. Run one configured OpenAI stage-run smoke on a known low-risk fixture if credentials are available.
5. Keep Signal Lab default display hiding abstain decisions during soft launch.
6. Observe 7-day distribution:
   - high_conviction `< 15%`
   - agent run error `< 5%`
   - abstain has non-empty reason distribution

## Rollback

- Code rollback before migration is safe because new columns/tables are additive.
- If the new worker produces bad decisions, set `pulse_agent_enabled=false` or disable the app runtime Pulse worker and keep rows for audit.
- If migration must be reversed in local/dev, Alembic downgrade drops `pulse_agent_run_steps` and decision columns. In production, prefer code rollback plus leaving additive columns in place to preserve audit.
- Do not delete run step ledger during incident response unless explicitly approved; it is the only replay source.

## Acceptance Test Commands

- AC1 storage ledger:
  ```bash
  uv run pytest tests/integration/test_pulse_repository.py::test_agent_run_steps_round_trip -q
  ```
- AC2 route gate:
  ```bash
  uv run pytest tests/unit/test_pulse_agent_routing.py::test_source_seed_routes_research_only_without_llm -q
  ```
- AC3 stage runner:
  ```bash
  uv run pytest tests/unit/test_pulse_decision_agent_client.py::test_stage_runner_calls_analyst_critic_judge_in_order -q
  ```
- AC4 worker hard cut:
  ```bash
  uv run pytest tests/unit/test_pulse_candidate_worker.py::test_successful_token_target_persists_three_stage_steps -q
  ```
- AC5 public contract:
  ```bash
  uv run pytest tests/unit/test_signal_pulse_service.py::test_pulse_item_includes_decision_block -q
  ```
- AC6 architecture boundary:
  ```bash
  uv run pytest tests/architecture/test_src_domain_architecture.py -q
  ```
- Final gate:
  ```bash
  make check-all
  ```

## Definition Of Done

- [ ] All tasks checked off with test evidence.
- [ ] Migration applied in target environment.
- [ ] Every successful token_target LLM run has exactly three successful stage records.
- [ ] Every source_seed/no-target run has no CEX/Meme stage records.
- [ ] Public payload includes `decision` and no `agent_recommendation`.
- [ ] `make check-all` passes.
- [ ] Verification artefact exists and includes at least one replayable run id.
