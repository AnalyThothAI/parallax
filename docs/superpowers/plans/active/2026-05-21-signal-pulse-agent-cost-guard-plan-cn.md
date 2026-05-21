# Signal Pulse Agent Cost Guard And Hybrid Model Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft
**Date:** 2026-05-21
**Owning spec:** `docs/superpowers/specs/active/2026-05-21-signal-pulse-agent-cost-guard-cn.md`
**Worktree:** `.worktrees/signal-pulse-agent-cost-guard/`
**Branch:** `codex/signal-pulse-agent-cost-guard`

**Goal:** Add a Pulse-owned cost guard so Signal Pulse uses Qwen3.6 for free research, reserves DeepSeek for public-eligible final judgment, suppresses duplicate/no-start retry loops, and proves public product output is preserved.

**Architecture:** Keep Pulse job state, run audit, eval, and read-model writes in the Pulse domain. Insert a deterministic `PulseCostGuardDecision` between evidence packet construction and LLM execution. The guard classifies each job into no-LLM finalization, cached fingerprint reuse, Qwen-only research, or Qwen research plus DeepSeek judge. Provider/circuit pressure becomes cooldown/backpressure, not rapid skipped-run churn.

**Tech Stack:** Python 3.13, Pydantic v2, psycopg, PostgreSQL, OpenAI-compatible Agents gateway, pytest, ruff, FastAPI ops diagnostics, markdown generated reports.

---

## Scope

- In:
  - Pulse cost guard, fingerprint reuse, Qwen/DeepSeek stage routing, backpressure cooldown, dry-run report, and focused tests.
  - Repository default agent lane config and documentation for operator-owned config changes.
  - Ops/reporting counters for calls saved and public candidate deltas.
- Out:
  - Frontend redesign.
  - Token Radar scoring changes.
  - Central durable agent queue.
  - Automatic mutation of `~/.gmgn-twitter-intel/workers.yaml`.
  - Relaxing deterministic eval, claim verifier, source quality, or public write gate.

## Pre-flight

- [ ] Read the owning spec:
  ```bash
  sed -n '1,260p' docs/superpowers/specs/active/2026-05-21-signal-pulse-agent-cost-guard-cn.md
  ```

- [ ] Create an isolated worktree:
  ```bash
  git worktree add .worktrees/signal-pulse-agent-cost-guard -b codex/signal-pulse-agent-cost-guard main
  cd .worktrees/signal-pulse-agent-cost-guard
  ```

- [ ] Verify branch and clean status:
  ```bash
  git branch --show-current
  git status --short
  ```
  Expected branch: `codex/signal-pulse-agent-cost-guard`; expected status: clean.

- [ ] Confirm real runtime config paths before any live-data diagnostics:
  ```bash
  uv run gmgn-twitter-intel config
  ```
  Expected: `config_path` and `workers_config_path` point to `/Users/qinghuan/.gmgn-twitter-intel/`. Do not print secrets.

- [ ] Run focused baseline tests:
  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_agent_eval_v2.py tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/unit/test_pulse_decision_agent_client.py tests/unit/test_pulse_candidate_worker.py -q
  uv run pytest tests/unit/integrations/openai_agents/test_agent_execution_gateway.py -q
  ```

Known-failing baseline tests:

- None expected. If baseline tests fail, record exact failures in the eventual verification artifact before implementation.

## File Structure

### New Pulse Services

- Create `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_agent_cost_guard.py`
  - Owns `PulseCostGuardDecision`, `PulseStagePlan`, fingerprint construction, and deterministic action classification.
  - Pure logic only; no DB access.
  - Public API:
    ```python
    @dataclass(frozen=True, slots=True)
    class PulseRunFingerprint:
        candidate_id: str
        trigger_signature: str
        timeline_signature: str
        evidence_packet_hash: str
        runtime_hash: str
        stage_plan_hash: str
        route: str

    @dataclass(frozen=True, slots=True)
    class PulseStagePlan:
        run_signal_analyst: bool
        run_bear_case: bool
        run_risk_portfolio_judge: bool
        signal_model: str
        bear_model: str
        judge_model: str | None

    @dataclass(frozen=True, slots=True)
    class PulseCostGuardDecision:
        action: Literal[
            "no_llm_finalize",
            "reuse_terminal_run",
            "qwen_research_only",
            "qwen_research_deepseek_judge",
            "provider_cooldown",
        ]
        reason: str
        public_eligible: bool
        qwen_allowed: bool
        deepseek_allowed: bool
        fingerprint: PulseRunFingerprint
        stage_plan: PulseStagePlan
        cooldown_until_ms: int | None = None
        audit_json: Mapping[str, Any] = field(default_factory=dict)
    ```

- Create `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_agent_cost_report.py`
  - Owns read-only aggregation for recent Pulse runs, stage calls, token use, duplicate fingerprints, and public candidate deltas.
  - Public API:
    ```python
    def build_signal_pulse_agent_cost_report(
        conn: Any,
        *,
        now_ms: int,
        lookback_hours: int,
        dry_run_policy: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError("Task 1 implements the read-only report query.")
    ```

### Pulse Repositories

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_runs_repository.py`
  - Add a terminal fingerprint lookup using existing run fields and request JSON.
  - Suggested signature:
    ```python
    def terminal_run_for_fingerprint(
        self,
        *,
        candidate_id: str,
        fingerprint_json: dict[str, Any],
        since_ms: int,
    ) -> dict[str, Any] | None:
        raise NotImplementedError("Task 3 implements the PostgreSQL lookup.")
    ```

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_jobs_repository.py`
  - Add a cooldown-aware no-start release method that does not create 30s retry churn.
  - Suggested signature:
    ```python
    def release_running_job_for_provider_cooldown(
        self,
        job: dict[str, Any],
        *,
        reason: str,
        now_ms: int,
        cooldown_until_ms: int,
        decrement_attempt: bool = True,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        raise NotImplementedError("Task 6 implements the cooldown release.")
    ```
  - Keep `release_running_job_for_backpressure` for generic short backpressure, but Pulse child-lane circuit/provider outage must use the cooldown-aware method.

### Pulse Runtime And Agent Client

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py`
  - Evaluate source quality before LLM stages.
  - Build cost guard input after evidence packet and evidence gate.
  - Reuse terminal fingerprints before model calls.
  - Finalize deterministic no-LLM runs without external stage audits.
  - Pass a stage plan into the decision client.
  - Convert provider cooldown/no-start failures into delayed job release with bounded audit noise.

- Modify `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`
  - Accept `stage_plan` in `run_decision_pipeline`.
  - Skip `risk_portfolio_judge` when `stage_plan.run_risk_portfolio_judge` is false.
  - Never fallback from Qwen to DeepSeek for non-public paths.
  - Preserve model names in stage audit from the gateway lane that executed the stage.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/providers.py`
  - Extend `PulseDecisionProvider.run_decision_pipeline` protocol with optional `stage_plan`.

- Modify `src/gmgn_twitter_intel/platform/config/settings.py`
  - Update default workers YAML so:
    - `pulse.pipeline` uses `qwen3.6` or the default model label.
    - `pulse.signal_analyst` uses `qwen3.6`.
    - `pulse.bear_case` uses `qwen3.6`.
    - `pulse.risk_portfolio_judge` uses `deepseek-v4-flash`.
  - Do not mutate operator-owned config automatically.

### Admission And Backpressure

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_admission_policy.py`
  - Treat plain `timeline_evidence_changed` as debounce/coalesce unless paired with escalation/hard-risk/score-band change.
  - Preserve immediate admission for `pulse_status_changed`, `recommended_decision_changed`, and `hard_risk_added`.

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
  - Track result counters for `agent_cost_guard_suppressed`, `agent_fingerprint_reused`, and `agent_provider_cooldown`.

### Ops / Report / Docs

- Add `scripts/evaluate_signal_pulse_agent_cost_guard.py`
  - Read-only report against live DB.
  - Writes markdown under `docs/generated/`.
  - Command:
    ```bash
    uv run python scripts/evaluate_signal_pulse_agent_cost_guard.py --lookback-hours 24 --dry-run
    ```

- Optionally modify `src/gmgn_twitter_intel/app/runtime/ops_diagnostics.py`
  - Add aggregate Pulse agent cost/cooldown counters if available without heavy queries.

- Modify docs:
  - `docs/WORKERS.md`
  - `docs/RELIABILITY.md`
  - `docs/superpowers/specs/active/2026-05-21-signal-pulse-agent-cost-guard-cn.md`
  - This plan if implementation decisions change.

### Tests

- Add `tests/unit/domains/pulse_lab/test_pulse_agent_cost_guard.py`
- Modify `tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py`
- Modify `tests/unit/test_pulse_decision_agent_client.py`
- Modify `tests/unit/test_pulse_candidate_worker.py`
- Modify `tests/integration/test_pulse_repositories.py`
- Add `tests/unit/domains/pulse_lab/test_pulse_agent_cost_report.py`

## PR Breakdown

1. **PR 1 - Read-only Cost Report And Baseline**
   - Adds report service/script.
   - Produces dry-run metrics from existing behavior.
   - No runtime behavior change.

2. **PR 2 - Pure Cost Guard And Fingerprint Lookup**
   - Adds cost guard models/classifier.
   - Adds terminal fingerprint lookup.
   - Adds unit tests proving public eligibility classification.

3. **PR 3 - Job Service Guard Enforcement**
   - Threads cost guard into `PulseCandidateJobService`.
   - Adds deterministic no-LLM finalization and fingerprint reuse.
   - Adds tests proving no external steps for blocked paths.

4. **PR 4 - Hybrid Qwen/DeepSeek Stage Routing**
   - Adds stage plan to Pulse decision client/provider protocol.
   - Updates default lane models.
   - Adds tests proving Qwen research and DeepSeek-only public judge.

5. **PR 5 - Backpressure Cooldown And Admission Debounce**
   - Adds cooldown-aware job release.
   - Debounces non-escalation timeline churn.
   - Adds tests proving no 30s skipped-run loop.

6. **PR 6 - Ops Docs And Live Verification**
   - Updates docs and report output.
   - Runs live read-only report after implementation.
   - Captures public candidate delta and savings evidence.

## Task 1 - Read-only Cost Report

**Files:**

- Create: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_agent_cost_report.py`
- Create: `scripts/evaluate_signal_pulse_agent_cost_guard.py`
- Test: `tests/unit/domains/pulse_lab/test_pulse_agent_cost_report.py`

- [ ] **Step 1: Write tests for report aggregation**

  Add tests that feed small synthetic run/step rows into pure aggregation helpers and assert:

  ```python
  assert report["deepseek"]["total_tokens"] == 1_000
  assert report["hidden_invalid_output"]["total_tokens"] == 800
  assert report["public_display"]["display_token_watch"] == 1
  assert report["backpressure"]["circuit_open_runs"] == 2
  ```

  Run:
  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_pulse_agent_cost_report.py -q
  ```
  Expected before implementation: FAIL because the module does not exist.

- [ ] **Step 2: Implement read-only report service**

  Implement `build_signal_pulse_agent_cost_report` with SQL that reads:

  - `pulse_agent_runs`
  - `pulse_agent_run_steps`
  - `pulse_agent_jobs`
  - `pulse_agent_eval_cases`
  - `pulse_agent_eval_results`

  Required output keys:

  ```python
  {
      "window": {"lookback_hours": 24, "since_ms": 0, "now_ms": 0},
      "runs": {"total": 0, "backpressure_circuit_open": 0, "hidden_invalid_output": 0},
      "steps_by_stage_model_status": [],
      "tokens_by_display_status": [],
      "duplicate_fingerprints": {
          "duplicate_success_fingerprint_groups": 0,
          "extra_success_runs_same_fingerprint": 0,
      },
      "public_candidate_delta": {
          "display_trade_candidate": 0,
          "display_token_watch": 0,
      },
      "predicted_savings": {
          "deepseek_tokens_before": 0,
          "deepseek_tokens_after": 0,
          "deepseek_token_reduction_ratio": 0.0,
      },
  }
  ```

- [ ] **Step 3: Add CLI script**

  The script must load settings with `require_ws_token=False`, apply
  `with_password_from_file`, set `default_transaction_read_only=on`, and write
  `docs/generated/signal-pulse-agent-cost-guard-YYYY-MM-DD.md`.

  Run:
  ```bash
  uv run python scripts/evaluate_signal_pulse_agent_cost_guard.py --lookback-hours 24 --dry-run
  ```
  Expected: a markdown report path printed with redacted config paths only.

## Task 2 - Pure Cost Guard

**Files:**

- Create: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_agent_cost_guard.py`
- Test: `tests/unit/domains/pulse_lab/test_pulse_agent_cost_guard.py`

- [ ] **Step 1: Add tests for public eligibility**

  Required test cases:

  - evidence hard-blocked -> `action == "no_llm_finalize"`, `deepseek_allowed is False`
  - source quality not public -> `action == "qwen_research_only"` or `no_llm_finalize`, `deepseek_allowed is False`
  - public trade candidate with complete evidence -> `action == "qwen_research_deepseek_judge"`
  - duplicate fingerprint present -> `action == "reuse_terminal_run"`
  - provider cooldown active -> `action == "provider_cooldown"`

  Run:
  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_pulse_agent_cost_guard.py -q
  ```
  Expected before implementation: FAIL.

- [ ] **Step 2: Implement guard models and classifier**

  Implement:

  ```python
  def decide_pulse_agent_cost(
      *,
      context: PulseCandidateContext,
      evidence_gate: EvidenceCompletenessGateResult,
      gate: PulseGateResult,
      source_quality: PulseSourceQualityDecision,
      runtime_hash: str,
      evidence_packet_hash: str,
      lane_models: Mapping[str, str],
      terminal_fingerprint_found: bool,
      provider_cooldown_until_ms: int | None,
      now_ms: int,
  ) -> PulseCostGuardDecision:
      raise NotImplementedError("Task 2 implements deterministic cost classification.")
  ```

  Public eligibility rule:

  ```python
  public_eligible = (
      evidence_gate.public_allowed
      and source_quality.public_allowed
      and gate.pulse_status in {"trade_candidate", "token_watch"}
      and gate.max_recommendation in {"trade_candidate", "watch"}
  )
  ```

- [ ] **Step 3: Run focused tests**

  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_pulse_agent_cost_guard.py -q
  ```
  Expected: PASS.

## Task 3 - Fingerprint Lookup

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_runs_repository.py`
- Test: `tests/integration/test_pulse_repositories.py`

- [ ] **Step 1: Add repository test**

  Insert two `pulse_agent_runs` rows with the same and different fingerprint JSON in `request_json->'cost_guard'->'fingerprint'`. Assert lookup returns only terminal runs with matching fingerprint and ignores running/failed no-output rows.

  Run:
  ```bash
  uv run pytest tests/integration/test_pulse_repositories.py::test_pulse_runs_terminal_run_for_fingerprint_returns_latest_matching_terminal_run -q
  ```
  Expected before implementation: FAIL.

- [ ] **Step 2: Implement lookup**

  Query shape:

  ```sql
  SELECT *
  FROM pulse_agent_runs
  WHERE candidate_id = %(candidate_id)s
    AND status = 'done'
    AND finished_at_ms >= %(since_ms)s
    AND request_json->'cost_guard'->'fingerprint' = %(fingerprint_json)s::jsonb
  ORDER BY finished_at_ms DESC, run_id DESC
  LIMIT 1
  ```

- [ ] **Step 3: Run repository tests**

  ```bash
  uv run pytest tests/integration/test_pulse_repositories.py::test_pulse_runs_terminal_run_for_fingerprint_returns_latest_matching_terminal_run -q
  ```
  Expected: PASS.

## Task 4 - Job Service Cost Guard Enforcement

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/types/agent_decision.py` only if a helper constructor is cleaner
- Test: `tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py`

- [ ] **Step 1: Add no-LLM finalization test**

  Construct a job/context whose evidence gate is hard-blocked. Assert:

  ```python
  assert decision_client.run_decision_pipeline_calls == 0
  assert stored_run["status"] == "done"
  assert stored_run["request_json"]["cost_guard"]["decision"]["action"] == "no_llm_finalize"
  assert not any(step["stage"] == "signal_analyst" for step in stored_steps)
  ```

  Run:
  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_run_job_cost_guard_hard_block_does_not_call_agent_pipeline -q
  ```

- [ ] **Step 2: Add duplicate fingerprint reuse test**

  Seed the fake repository with a terminal matching fingerprint. Assert the job succeeds without calling the decision client and records `reuse_terminal_run`.

  Run:
  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_run_job_reuses_terminal_fingerprint_without_model_call -q
  ```

- [ ] **Step 3: Implement cost guard in `run_job`**

  After evidence packet, evidence gate, source quality, and runtime hash are available:

  ```python
  cost_guard = decide_pulse_agent_cost(
      context=context,
      evidence_gate=evidence_gate,
      gate=gate,
      source_quality=source_quality,
      runtime_hash=runtime_hash,
      evidence_packet_hash=evidence_packet.evidence_packet_hash,
      lane_models=decision_client_lane_models,
      terminal_fingerprint_found=terminal_fingerprint is not None,
      provider_cooldown_until_ms=provider_cooldown_until_ms,
      now_ms=now_ms,
  )
  agent_context = {
      **agent_context,
      "cost_guard": cost_guard.to_json(),
  }
  ```

  Branch before `decision_client.run_decision_pipeline`:

  - `no_llm_finalize`: build deterministic abstain/ignore, insert deterministic stages, finish run.
  - `reuse_terminal_run`: finish run with reused metadata, no external stages.
  - `provider_cooldown`: release job through cooldown path and do not create additional model stages.
  - `qwen_research_only` / `qwen_research_deepseek_judge`: call decision client with `stage_plan`.

- [ ] **Step 4: Run job service tests**

  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py -q
  ```

## Task 5 - Hybrid Stage Routing

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/providers.py`
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`
- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`
- Test: `tests/unit/test_pulse_decision_agent_client.py`
- Test: `tests/unit/test_settings.py`

- [ ] **Step 1: Add decision client tests**

  Required assertions:

  ```python
  assert gateway.calls == ["pulse.signal_analyst", "pulse.bear_case"]
  assert "pulse.risk_portfolio_judge" not in gateway.calls
  ```

  for `qwen_research_only`, and:

  ```python
  assert gateway.calls == [
      "pulse.signal_analyst",
      "pulse.bear_case",
      "pulse.risk_portfolio_judge",
  ]
  ```

  for `qwen_research_deepseek_judge`.

- [ ] **Step 2: Extend provider protocol**

  Add optional `stage_plan: PulseStagePlan | None = None` to
  `run_decision_pipeline`.

- [ ] **Step 3: Implement stage skipping**

  In `OpenAIAgentsPulseDecisionClient.run_decision_pipeline`, skip judge when:

  ```python
  if stage_plan is not None and not stage_plan.run_risk_portfolio_judge:
      final = _stage_failure_abstain_decision(
          route=route,
          reason="deepseek_judge_not_required",
          evidence_packet=evidence_packet,
          abstain_reason="cost_guard_research_only",
      )
      audit = self._decision_runtime.with_output_hash(audit, final=final)
      return PulseDecisionAgentResult(
          final_decision=final,
          agent_run_audit=audit,
          stage_audits=tuple(stage_audits),
      )
  ```

  Keep signal/bear validation intact. Non-public Qwen failures must return
  abstain and must not call judge.

- [ ] **Step 4: Update default worker YAML**

  Update defaults so repository-generated config uses:

  ```yaml
  pulse.pipeline:
    model: qwen3.6
  pulse.signal_analyst:
    model: qwen3.6
  pulse.bear_case:
    model: qwen3.6
  pulse.risk_portfolio_judge:
    model: deepseek-v4-flash
  ```

  Add tests in `tests/unit/test_settings.py` proving generated defaults and
  lane model resolution.

- [ ] **Step 5: Run tests**

  ```bash
  uv run pytest tests/unit/test_pulse_decision_agent_client.py tests/unit/test_settings.py -q
  ```

## Task 6 - Provider Cooldown And Backpressure Hardening

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_jobs_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py`
- Test: `tests/integration/test_pulse_repositories.py`
- Test: `tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py`

- [ ] **Step 1: Add cooldown release repository test**

  Claim a pending job so `attempt_count` increments. Release it with
  `cooldown_until_ms=now+300_000`. Assert:

  ```python
  assert row["status"] == "pending"
  assert row["next_run_at_ms"] == now + 300_000
  assert row["attempt_count"] == 0
  assert "provider_cooldown" in row["last_error"]
  ```

- [ ] **Step 2: Implement cooldown release**

  Add `release_running_job_for_provider_cooldown` with the SQL shape:

  ```sql
  UPDATE pulse_agent_jobs
  SET status = 'pending',
      next_run_at_ms = %(cooldown_until_ms)s,
      last_error = %(reason)s,
      attempt_count = CASE
          WHEN %(decrement_attempt)s THEN GREATEST(0, attempt_count - 1)
          ELSE attempt_count
      END,
      updated_at_ms = %(now_ms)s
  WHERE job_id = %(job_id)s
    AND status = 'running'
    AND attempt_count = %(attempt_count)s
  RETURNING *
  ```

- [ ] **Step 3: Map circuit/provider no-start to cooldown**

  In job service failure handling, when the exception is no-start circuit,
  capacity, rate limit, auth unavailable, or insufficient balance:

  - compute cooldown from lane policy/circuit metadata when available;
  - otherwise use 5 minutes for provider config/balance outage and 2 minutes
    for circuit open;
  - avoid repeated 30-second release.

- [ ] **Step 4: Run tests**

  ```bash
  uv run pytest tests/integration/test_pulse_repositories.py::test_release_running_job_for_provider_cooldown_delays_without_burning_attempt -q
  uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_no_start_circuit_open_releases_job_to_cooldown -q
  ```

## Task 7 - Admission Debounce For Non-Escalation Timeline Churn

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_admission_policy.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Test: `tests/unit/test_pulse_candidate_worker.py`

- [ ] **Step 1: Add policy tests**

  Cases:

  - only `timeline_evidence_changed` within debounce window -> suppress `timeline_debounce`
  - `timeline_evidence_changed + pulse_status_changed` -> enqueue escalation
  - `hard_risk_added` -> enqueue immediately
  - repeated score-band-only change still requires confirmation

- [ ] **Step 2: Implement debounce inputs**

  Extend `PulseAdmissionPolicy.classify` with:

  ```python
  last_processed_at_ms: int | None = None
  now_ms: int | None = None
  timeline_debounce_seconds: int = 600
  ```

  If only material timeline/trigger evidence changed and no escalation exists,
  suppress until debounce expires.

- [ ] **Step 3: Thread edge timestamps from worker**

  Pass `existing_edge.get("last_processed_at_ms")` and `now_ms` from
  `_enqueue_if_due`.

- [ ] **Step 4: Run worker tests**

  ```bash
  uv run pytest tests/unit/test_pulse_candidate_worker.py -q
  ```

## Task 8 - Docs, Ops, And Live Verification

**Files:**

- Modify: `docs/WORKERS.md`
- Modify: `docs/RELIABILITY.md`
- Modify: `docs/superpowers/specs/active/2026-05-21-signal-pulse-agent-cost-guard-cn.md` if implementation changes scope
- Modify: `docs/superpowers/plans/active/2026-05-21-signal-pulse-agent-cost-guard-plan-cn.md`

- [ ] **Step 1: Run full focused verification**

  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_pulse_agent_cost_guard.py tests/unit/domains/pulse_lab/test_pulse_agent_cost_report.py tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py tests/unit/test_pulse_decision_agent_client.py tests/unit/test_pulse_candidate_worker.py tests/integration/test_pulse_repositories.py -q
  uv run ruff check src/gmgn_twitter_intel/domains/pulse_lab src/gmgn_twitter_intel/integrations/openai_agents tests/unit/domains/pulse_lab tests/unit/test_pulse_decision_agent_client.py tests/unit/test_pulse_candidate_worker.py tests/integration/test_pulse_repositories.py
  ```

- [ ] **Step 2: Run read-only live report**

  ```bash
  uv run gmgn-twitter-intel config
  uv run python scripts/evaluate_signal_pulse_agent_cost_guard.py --lookback-hours 24 --dry-run
  ```

  Expected:

  - config paths point to `/Users/qinghuan/.gmgn-twitter-intel/`;
  - no secrets printed;
  - predicted DeepSeek token reduction >= 70%;
  - predicted public trade/watch delta >= 0;
  - predicted backpressure skipped-run reduction >= 90% for circuit-open scenario.

- [ ] **Step 3: Update docs**

  Document:

  - Qwen3.6 research lane and DeepSeek judge lane;
  - cost guard actions;
  - provider cooldown behavior;
  - how to run the dry-run report;
  - operator config snippet for `~/.gmgn-twitter-intel/workers.yaml`.

- [ ] **Step 4: Capture final verification artifact**

  Create or update:

  ```text
  docs/superpowers/plans/active/2026-05-21-signal-pulse-agent-cost-guard-verification-cn.md
  ```

  Include command output summaries, generated report path, public candidate delta, and any residual risk.

## Rollout Order

1. Merge read-only report first and run it against live data.
2. Merge pure cost guard and fingerprint lookup with tests; no enforcement yet.
3. Enable job-service guard in dry-run mode if a config flag is needed.
4. Switch repository defaults to Qwen research / DeepSeek judge.
5. Enable enforcement only after dry-run public candidate delta is acceptable.
6. Run live report after one full 1h and 4h cycle.

## Rollback

- If public candidates drop unexpectedly, disable cost guard enforcement and keep report-only mode.
- If Qwen p95 latency creates backlog, set `pulse.signal_analyst` and `pulse.bear_case` temporarily back to DeepSeek while keeping non-public DeepSeek suppression.
- If cooldown delays recovery too much, reduce cooldown TTL in config and keep fingerprint reuse active.
- If fingerprint reuse suppresses valid new evidence, disable reuse TTL or include additional evidence fields in the fingerprint.

## Acceptance Test Commands

- AC1:
  ```bash
  uv run python scripts/evaluate_signal_pulse_agent_cost_guard.py --lookback-hours 24 --dry-run
  ```
  Expected: report shows DeepSeek token reduction >= 70% and public trade/watch delta >= 0.

- AC2/AC3:
  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_run_job_cost_guard_hard_block_does_not_call_agent_pipeline tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_source_quality_hidden_path_does_not_call_deepseek -q
  ```

- AC4:
  ```bash
  uv run pytest tests/integration/test_pulse_repositories.py::test_pulse_runs_terminal_run_for_fingerprint_returns_latest_matching_terminal_run tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_run_job_reuses_terminal_fingerprint_without_model_call -q
  ```

- AC5/AC8:
  ```bash
  uv run pytest tests/integration/test_pulse_repositories.py::test_release_running_job_for_provider_cooldown_delays_without_burning_attempt tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py::test_no_start_circuit_open_releases_job_to_cooldown -q
  ```

- AC6/AC7:
  ```bash
  uv run pytest tests/unit/test_pulse_decision_agent_client.py tests/unit/test_settings.py -q
  ```

## Verification

Verification will be recorded in
`docs/superpowers/plans/active/2026-05-21-signal-pulse-agent-cost-guard-verification-cn.md`
before this plan is marked complete.
