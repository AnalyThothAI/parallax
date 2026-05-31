# Signal Pulse KISS Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the core Signal Pulse noise/control failures with the smallest production-safe changes: external push policy, atomic target admission, failure-loop control, and removal of public legacy stage compatibility.

**Architecture:** Keep the existing workers and Kappa/CQRS ownership. Add deterministic policy services inside the current Pulse and notification domains; do not add a new runtime worker, a notification intent table, frontend throttling, or parallel specialist agents.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic, Pydantic v2, pytest, React/TypeScript, Vitest, OpenAPI generation.

---

## File Map

- Create: `src/parallax/domains/pulse_lab/services/pulse_admission_policy.py`
  - Pure policy for edge materiality, active-job suppression, score-band confirmation, and failure-circuit decisions.
- Modify: `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
  - Route `_enqueue_if_due` through policy and atomic repository admission. Move processed-state update to successful terminal run.
- Modify: `src/parallax/domains/pulse_lab/repositories/pulse_repository.py`
  - Add `claim_pulse_admission`, target budget helpers, suppression fields, failure query, and processed-state update on success.
- Create: `src/parallax/platform/db/alembic/versions/20260517_0059_pulse_control_plane_kiss.py`
  - Add `pulse_target_run_budget` and minimal edge-state suppression/pending-band columns.
- Modify: `src/parallax/domains/notifications/services/notification_rules.py`
  - Add Signal Pulse in-app/external signatures, cooldown bucket, external eligibility, and channel split.
- Modify: `src/parallax/domains/notifications/repositories/notification_repository.py`
  - Change Signal Pulse semantic duplicate lookup to use `in_app_signature` and `external_push_signature`.
- Modify: `src/parallax/domains/notifications/runtime/notification_worker.py`
  - Keep delivery enqueueing based on candidate channels; no frontend throttling.
- Modify: `src/parallax/platform/config/settings.py`
  - Reject unsupported Signal Pulse statuses after operator config cleanup.
- Modify: `src/parallax/domains/pulse_lab/services/agent_runtime.py`
  - Include actual tool/validator/failure-taxonomy contract fields in the harness manifest.
- Modify: `src/parallax/domains/pulse_lab/services/agent_eval.py`
  - Grade failed-run eval cases and align evidence subset checks with runtime validation.
- Modify: `src/parallax/app/surfaces/api/schemas.py`
  - Remove public `analyst`, `critic`, `judge` stage fields.
- Modify: `web/src/lib/types/frontend-contracts.ts`
  - Remove public legacy stage fields until generated types fully replace this file.
- Modify: `web/src/features/signal-lab/model/pulseDetail.ts`
  - Remove legacy stage view model and placeholder logic.
- Modify: `web/src/features/signal-lab/ui/PulseDetail/PulseAgentRail.tsx`
  - Remove legacy placeholder cards/copy.
- Modify: `docs/ARCHITECTURE.md`
  - Replace stale Analyst/Critic/Judge text with Investigator/DecisionMaker.
- Modify: `docs/WORKERS.md`
  - List actual Pulse worker writes: jobs, edge state, budgets, runs, steps, harness versions, eval cases/results, candidates, playbook snapshots.

---

## Task 1: Quiet External PushDeer Without New Tables

**Intent:** Keep in-app Signal Pulse history, but make external push target/cooldown/escalation gated. This is the fastest way to reduce operator-visible spam.

**Files:**
- Modify: `src/parallax/domains/notifications/services/notification_rules.py`
- Modify: `src/parallax/domains/notifications/repositories/notification_repository.py`
- Test: `tests/unit/test_notification_rules.py`
- Test: `tests/unit/test_notification_worker_runtime.py`

- [ ] **Step 1: Add failing tests for Signal Pulse external push policy**

  Add tests to `tests/unit/test_notification_rules.py`:

  ```python
  def test_signal_pulse_pushdeer_uses_target_cooldown_signature() -> None:
      row = pulse_candidate(
          "pulse-all",
          status="trade_candidate",
          symbol="PEPE",
          eligible_for_high_alert=True,
      )
      matched = dict(row)
      matched["candidate_id"] = "pulse-matched"
      matched["scope"] = "matched"
      notifications = NotificationsConfig(
          rules={
              "signal_pulse_candidate": {
                  "enabled": True,
                  "channels": ["in_app", "pushdeer"],
                  "window": "1h",
                  "scopes": ["all", "matched"],
                  "statuses": ["trade_candidate"],
                  "cooldown_seconds": 900,
              }
          }
      )

      candidates = [
          item
          for item in engine(pulse=FakePulse([row, matched]), notifications=notifications).evaluate(now_ms=NOW_MS)
          if item.rule_id == "signal_pulse_candidate"
      ]

      assert len(candidates) == 1
      assert candidates[0].channels == ("in_app", "pushdeer")
      assert candidates[0].payload["external_push_eligible"] is True
      assert candidates[0].payload["external_push_signature"]
  ```

  Add another test:

  ```python
  def test_signal_pulse_score_band_only_change_is_in_app_only() -> None:
      row = pulse_candidate("pulse-score-band", status="token_watch", eligible_for_high_alert=True)
      row["last_edge_events_json"] = ["score_band_crossed"]

      candidate = _only_pulse_notification(row)

      assert candidate.channels == ("in_app",)
      assert candidate.payload["external_push_eligible"] is False
      assert candidate.payload["external_push_suppression_reason"] == "not_escalation"
  ```

- [ ] **Step 2: Run tests to verify current behavior fails**

  Run:

  ```bash
  uv run pytest tests/unit/test_notification_rules.py::test_signal_pulse_pushdeer_uses_target_cooldown_signature tests/unit/test_notification_rules.py::test_signal_pulse_score_band_only_change_is_in_app_only -q
  ```

  Expected: both tests fail because current code passes `rule.channels` unchanged and has no external push metadata.

- [ ] **Step 3: Implement minimal signature helpers**

  In `notification_rules.py`, add helpers near `_pulse_notification_signature`:

  ```python
  def _pulse_in_app_signature(row: dict[str, Any]) -> str:
      decision = _pulse_decision(row)
      factor_snapshot = _dict(row.get("factor_snapshot_json"))
      playbook = decision.get("playbook") or {}
      payload = {
          "candidate_id": row.get("candidate_id"),
          "pulse_status": row.get("pulse_status"),
          "score_band": row.get("score_band"),
          "decision_route": decision.get("route"),
          "decision_recommendation": decision.get("recommendation"),
          "playbook_has_playbook": bool(playbook.get("has_playbook")) if isinstance(playbook, dict) else False,
          "playbook_monitoring_horizon": playbook.get("monitoring_horizon") if isinstance(playbook, dict) else None,
          "gate_max_decision": _dict(factor_snapshot.get("gates")).get("max_decision"),
      }
      return _stable_hash(payload)


  def _pulse_external_push_signature(
      row: dict[str, Any],
      *,
      cooldown_seconds: int,
      occurrence_at_ms: int,
      alert_class: str,
      status_level: int,
      recommendation_level: int,
  ) -> str:
      payload = {
          "target_type": row.get("target_type"),
          "target_id": row.get("target_id"),
          "alert_class": alert_class,
          "status_level": status_level,
          "recommendation_level": recommendation_level,
          "cooldown_bucket": _cooldown_bucket(occurrence_at_ms, cooldown_seconds),
          "pulse_version": row.get("pulse_version"),
          "gate_version": row.get("gate_version"),
      }
      return _stable_hash(payload)
  ```

- [ ] **Step 4: Add external eligibility and channel split**

  In `notification_rules.py`, import `dataclass` and add the policy helper:

  ```python
  from dataclasses import dataclass
  ```

  ```python
  @dataclass(frozen=True, slots=True)
  class _PulseExternalPushPolicy:
      eligible: bool
      external_push_signature: str | None
      row_signature: str | None
      suppression_reason: str | None


  def _pulse_external_push_policy(
      row: dict[str, Any],
      *,
      severity: str,
      factor_snapshot: dict[str, Any],
      occurrence_at_ms: int,
      cooldown_seconds: int,
  ) -> _PulseExternalPushPolicy:
      edge_events = set(_list(row.get("last_edge_events_json")))
      status = str(row.get("pulse_status") or "")
      escalation = bool(edge_events & {"pulse_status_changed", "recommended_decision_changed"})
      resolved = _has_resolved_pulse_target(row, factor_snapshot)
      if severity not in {"high", "critical"}:
          return _PulseExternalPushPolicy(False, None, None, "severity_below_high")
      if status == "risk_rejected_high_info":
          return _PulseExternalPushPolicy(False, None, None, "risk_rejected_in_app_only")
      if not resolved:
          return _PulseExternalPushPolicy(False, None, None, "unresolved_target")
      if not escalation:
          return _PulseExternalPushPolicy(False, None, None, "not_escalation")
      signature = _pulse_external_push_signature(
          row,
          cooldown_seconds=cooldown_seconds,
          occurrence_at_ms=occurrence_at_ms,
          alert_class=status,
          status_level=_pulse_status_escalation_level(status),
          recommendation_level=_pulse_recommendation_escalation_level(_pulse_decision(row).get("recommendation")),
      )
      return _PulseExternalPushPolicy(True, signature, signature, None)
  ```

  Add these two tiny ranking helpers:

  ```python
  def _pulse_status_escalation_level(status: str) -> int:
      return {"risk_rejected_high_info": 0, "token_watch": 1, "trade_candidate": 2}.get(status, 0)


  def _pulse_recommendation_escalation_level(value: Any) -> int:
      recommendation = str(value or "")
      return {"ignore": 0, "abstain": 0, "watchlist": 1, "trade_candidate": 2, "high_conviction": 3}.get(
          recommendation,
          0,
      )
  ```

  Then in `_signal_pulse_candidates`, replace the single signature/payload/channels block with:

  ```python
  in_app_signature = _pulse_in_app_signature(row)
  push_policy = _pulse_external_push_policy(
      row,
      severity=severity,
      factor_snapshot=factor_snapshot,
      occurrence_at_ms=occurrence_at_ms,
      cooldown_seconds=rule.cooldown_seconds,
  )
  payload = _pulse_payload(
      row,
      notification_signature=push_policy.row_signature or in_app_signature,
      in_app_signature=in_app_signature,
      external_push_signature=push_policy.external_push_signature,
      external_push_eligible=push_policy.eligible,
      external_push_suppression_reason=push_policy.suppression_reason,
  )
  channels = rule.channels if push_policy.eligible else tuple(channel for channel in rule.channels if channel == "in_app")
  ```

- [ ] **Step 5: Update repository semantic duplicate lookup**

  In `NotificationRepository._pulse_signature_duplicate`, replace the lookup by only `notification_signature` with lookup by `in_app_signature` and `external_push_signature`:

  ```sql
  WHERE rule_id = %s
    AND payload_json->>'in_app_signature' = %s
    AND COALESCE(payload_json->>'external_push_signature', 'in_app') = %s
  ```

  Use `"in_app"` when the incoming payload has no external push signature.

- [ ] **Step 6: Run targeted tests**

  Run:

  ```bash
  uv run pytest tests/unit/test_notification_rules.py tests/unit/test_notification_worker_runtime.py -q
  ```

  Expected: notification rule and worker tests pass.

---

## Task 2: Add Atomic Target Admission

**Intent:** Prevent cross-window/scope amplification and prevent budget consumption without a job.

**Files:**
- Create: `src/parallax/domains/pulse_lab/services/pulse_admission_policy.py`
- Modify: `src/parallax/domains/pulse_lab/repositories/pulse_repository.py`
- Modify: `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Create: `src/parallax/platform/db/alembic/versions/20260517_0059_pulse_control_plane_kiss.py`
- Test: `tests/unit/test_pulse_admission_policy.py`
- Test: `tests/unit/test_pulse_candidate_worker.py`
- Test: `tests/integration/test_pulse_repository.py`

- [ ] **Step 1: Add failing policy unit tests**

  Create `tests/unit/test_pulse_admission_policy.py`:

  ```python
  from parallax.domains.pulse_lab.services.pulse_admission_policy import (
      PulseAdmissionPolicy,
  )


  def test_policy_suppresses_unchanged_state() -> None:
      state = {"pulse_status": "token_watch", "score_band": "70-79"}
      decision = PulseAdmissionPolicy().classify(
          previous_state=state,
          current_state=state,
          existing_job=None,
          edge_events=[],
          pending_score_band=None,
          pending_score_band_count=0,
      )
      assert decision.action == "suppress"
      assert decision.reason == "unchanged"


  def test_policy_requires_two_score_band_observations() -> None:
      decision = PulseAdmissionPolicy().classify(
          previous_state={"score_band": "60-69", "pulse_status": "token_watch"},
          current_state={"score_band": "70-79", "pulse_status": "token_watch"},
          existing_job=None,
          edge_events=["score_band_crossed"],
          pending_score_band="70-79",
          pending_score_band_count=1,
      )
      assert decision.action == "enqueue_agent"
      assert decision.reason == "score_band_confirmed"
  ```

- [ ] **Step 2: Add migration**

  Create `20260517_0059_pulse_control_plane_kiss.py` with:

  ```python
  from __future__ import annotations

  from alembic import op

  revision = "20260517_0059"
  down_revision = "20260517_0058"
  branch_labels = None
  depends_on = None


  def upgrade() -> None:
      op.execute(
          """
          CREATE TABLE IF NOT EXISTS pulse_target_run_budget (
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            hour_bucket_ms BIGINT NOT NULL,
            enqueue_count BIGINT NOT NULL DEFAULT 0,
            created_at_ms BIGINT NOT NULL,
            updated_at_ms BIGINT NOT NULL,
            PRIMARY KEY(target_type, target_id, hour_bucket_ms)
          )
          """
      )
      op.execute(
          """
          ALTER TABLE pulse_candidate_edge_state
            ADD COLUMN IF NOT EXISTS last_suppressed_reason TEXT,
            ADD COLUMN IF NOT EXISTS last_suppressed_at_ms BIGINT,
            ADD COLUMN IF NOT EXISTS pending_score_band TEXT,
            ADD COLUMN IF NOT EXISTS pending_score_band_count BIGINT NOT NULL DEFAULT 0
          """
      )
      op.execute(
          """
          CREATE INDEX IF NOT EXISTS idx_pulse_target_run_budget_hour
            ON pulse_target_run_budget(hour_bucket_ms DESC, updated_at_ms DESC)
          """
      )


  def downgrade() -> None:
      op.execute("DROP INDEX IF EXISTS idx_pulse_target_run_budget_hour")
      op.execute("DROP TABLE IF EXISTS pulse_target_run_budget")
      op.execute("ALTER TABLE pulse_candidate_edge_state DROP COLUMN IF EXISTS pending_score_band_count")
      op.execute("ALTER TABLE pulse_candidate_edge_state DROP COLUMN IF EXISTS pending_score_band")
      op.execute("ALTER TABLE pulse_candidate_edge_state DROP COLUMN IF EXISTS last_suppressed_at_ms")
      op.execute("ALTER TABLE pulse_candidate_edge_state DROP COLUMN IF EXISTS last_suppressed_reason")
  ```

- [ ] **Step 3: Add atomic repository integration tests**

  Add to `tests/integration/test_pulse_repository.py`:

  ```python
  def _job_payload(candidate_id: str) -> dict[str, Any]:
      return {
          "candidate_id": candidate_id,
          "candidate_type": "token_target",
          "subject_key": "Asset:asset-1",
          "window": "1h",
          "scope": "all",
          "trigger_signature": "trigger",
          "timeline_signature": "timeline",
          "priority": 10,
          "target_type": "Asset",
          "target_id": "asset-1",
          "context_json": {"candidate_id": candidate_id, "factor_snapshot": {"schema_version": "test"}},
          "max_attempts": 3,
          "next_run_at_ms": 3_600_001,
      }


  def test_claim_pulse_admission_rejects_target_without_candidate_budget_consumption(tmp_path) -> None:
      with connect_postgres_test(tmp_path / "db", read_only=False) as conn:
          reset_postgres_schema(conn)
          repo = PulseRepository(conn)
          first = repo.claim_pulse_admission(
              candidate_id="cand-1",
              target_type="Asset",
              target_id="asset-1",
              hour_bucket_ms=3_600_000,
              now_ms=3_600_001,
              target_limit=0,
              candidate_limit=3,
              job_payload=_job_payload("cand-1"),
              edge_state={"score_band": "70-79"},
              edge_events=["pulse_status_changed"],
          )

          assert first.accepted is False
          assert first.reason == "target_budget_exhausted"
          assert repo.job_for_candidate("cand-1") is None
  ```

- [ ] **Step 4: Implement `PulseAdmissionPolicy`**

  Add a frozen result type and a small classifier:

  ```python
  from dataclasses import dataclass
  from typing import Literal


  @dataclass(frozen=True, slots=True)
  class PulseAdmissionDecision:
      action: Literal["suppress", "enqueue_agent"]
      reason: str
      edge_events: tuple[str, ...]
  ```

  Keep the implementation pure and under 80 lines.

- [ ] **Step 5: Implement `claim_pulse_admission` in one transaction**

  In `PulseRepository`, implement one method that uses `with transaction(self.conn):` or the repository-session transaction helper used elsewhere. It must call lower-level SQL with `commit=False` semantics and return:

  ```python
  @dataclass(frozen=True, slots=True)
  class PulseAdmissionClaim:
      accepted: bool
      reason: str
      job: dict[str, Any] | None = None
  ```

- [ ] **Step 6: Wire worker admission**

  In `_enqueue_if_due`:

  - build edge state,
  - record/classify using `PulseAdmissionPolicy`,
  - call `claim_pulse_admission`,
  - return `claim.accepted`.

  Remove the direct `claim_edge_budget -> enqueue_job -> mark_edge_job_enqueued` chain from `_enqueue_if_due`.

- [ ] **Step 7: Move processed-state update to success**

  Change `mark_edge_run_finished` to accept `processed_state_json` and `edge_events_json`, then update `last_processed_state_json` only in the success transaction in `_run_job`.

- [ ] **Step 8: Run targeted tests**

  Run:

  ```bash
  uv run pytest tests/unit/test_pulse_admission_policy.py tests/unit/test_pulse_candidate_worker.py tests/integration/test_pulse_repository.py -q
  ```

  Expected: all targeted Pulse admission tests pass.

---

## Task 3: Bound Failure Loops And Add Failed-Run Eval Cases

**Intent:** Stop repeated schema/evidence failures from creating noisy work while preserving audit and eval data.

**Files:**
- Modify: `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `src/parallax/domains/pulse_lab/repositories/pulse_repository.py`
- Modify: `src/parallax/domains/pulse_lab/services/agent_runtime.py`
- Modify: `src/parallax/domains/pulse_lab/services/agent_eval.py`
- Test: `tests/unit/test_pulse_candidate_worker.py`
- Test: `tests/unit/domains/pulse_lab/test_agent_eval_v2.py`

- [ ] **Step 1: Add failure taxonomy helper tests**

  Add to `tests/unit/test_pulse_candidate_worker.py`:

  ```python
  def test_normalized_failure_reason_maps_unknown_evidence() -> None:
      assert _normalized_failure_reason(ValueError("unknown evidence ids: event-x")) == "unknown_evidence_id"


  def test_normalized_failure_reason_maps_schema_validation() -> None:
      assert _normalized_failure_reason(ValueError("model_validate failed")) == "schema_validation_failed"
  ```

- [ ] **Step 2: Implement `_normalized_failure_reason`**

  In `pulse_candidate_worker.py`, add:

  ```python
  def _normalized_failure_reason(exc: Exception) -> str:
      text = str(exc).lower()
      if "unknown evidence" in text or "unknown final evidence" in text:
          return "unknown_evidence_id"
      if "model_validate" in text or "validation" in text or "schema" in text:
          return "schema_validation_failed"
      if "budget exceeded" in text:
          return "tool_budget_exceeded"
      if isinstance(exc, TimeoutError) or "timed out" in text:
          return "timeout"
      if "rate limit" in text or "429" in text:
          return "provider_rate_limited"
      if "provider unavailable" in text or "503" in text:
          return "provider_unavailable"
      if "stale_running_timeout" in text:
          return "stale_running_timeout"
      return "unexpected_exception"
  ```

- [ ] **Step 3: Persist normalized reason on failures**

  In the `_run_job` exception branch:

  - compute `failure_reason = _normalized_failure_reason(exc)`;
  - extend `PulseRepository.finish_agent_run` so callers can pass `trace_metadata_json_patch`;
  - write `{"failure_reason": failure_reason}` into `pulse_agent_runs.trace_metadata_json`;
  - pass `failure_reason` to `mark_job_failed` so retry/circuit-breaker queries read a stable code;
  - keep `_compact_error(exc)` in `pulse_agent_runs.error` for human debugging.

- [ ] **Step 4: Add failed-run eval case builder**

  Extend `agent_eval.py` with:

  ```python
  def build_pulse_failed_eval_case(
      *,
      run_id: str,
      runtime_hash: str,
      context: dict[str, Any],
      route: DecisionRoute,
      completeness: dict[str, Any],
      stage_audits: tuple[StageRunAudit, ...],
      failure_reason: str,
  ) -> dict[str, Any]:
      return {
          "eval_case_id": _stable_id("pulse-failed-eval-case", run_id, failure_reason, PULSE_DETERMINISTIC_GRADER_VERSION),
          "source_run_id": run_id,
          "runtime_hash": runtime_hash,
          "eval_type": "deterministic",
          "route": route,
          "recommendation": "abstain",
          "input_json": {
              "context": context,
              "completeness": completeness,
              "stage_audits": [stage.model_dump(mode="json") for stage in stage_audits],
              "failure_reason": failure_reason,
          },
          "expected_json": {"status": "fail", "failure_reason": failure_reason},
          "rubric_json": {
              "grader_version": PULSE_DETERMINISTIC_GRADER_VERSION,
              "checks": ["failed_run_recorded"],
          },
      }
  ```

- [ ] **Step 5: Add failure circuit breaker query**

  In `PulseRepository`, add `recent_target_failure_count(target_type, target_id, since_ms, reasons)` by joining `pulse_agent_runs` to `pulse_agent_jobs` on `job_id`, reading `trace_metadata_json->>'failure_reason'`.

- [ ] **Step 6: Wire circuit breaker into admission policy**

  Before calling `claim_pulse_admission`, if the edge is not an escalation and `recent_target_failure_count >= 3`, suppress with `failure_circuit_open`.

- [ ] **Step 7: Run tests**

  Run:

  ```bash
  uv run pytest tests/unit/test_pulse_candidate_worker.py tests/unit/domains/pulse_lab/test_agent_eval_v2.py -q
  ```

---

## Task 4: Remove Public Legacy Stage Compatibility

**Intent:** Historical DB rows may remain, but `analyst`, `critic`, and `judge` must not be first-class runtime/API/frontend fields.

**Files:**
- Modify: `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py`
- Modify: `src/parallax/app/surfaces/api/schemas.py`
- Modify: `web/src/lib/types/frontend-contracts.ts`
- Modify: `web/src/features/signal-lab/model/pulseDetail.ts`
- Modify: `web/src/features/signal-lab/ui/PulseDetail/PulseAgentRail.tsx`
- Modify: `web/tests/unit/features/signal-lab/pulseDetail.test.ts`
- Modify: `web/tests/component/features/signal-lab/ui/PulseAgentRail.test.tsx`
- Modify: `tests/unit/test_signal_pulse_service.py`
- Modify: `tests/contract/test_openapi_drift.py`

- [ ] **Step 1: Update backend tests to expect only v2 stage keys**

  Replace legacy-stage assertions in `tests/unit/test_signal_pulse_service.py` with:

  ```python
  def test_candidate_stages_only_expose_v2_public_contract() -> None:
      pulse = FakePulseRepository()
      pulse.candidate_rows["pulse-1"] = _candidate_row("pulse-1", pulse_status="token_watch", verdict="token_watch")
      pulse.agent_run_steps["run-1"] = [
          {"stage": "analyst", "status": "ok", "response_json": {"summary_zh": "legacy"}},
          {"stage": "investigator", "status": "ok", "response_json": {"summary_zh": "v2"}},
      ]

      item = SignalPulseService(pulse=pulse).candidate(candidate_id="pulse-1")

      assert item is not None
      assert set(item["stages"]) == {"investigator", "decision_maker", "research_only_gate"}
      assert item["stages"]["investigator"]["response"]["summary_zh"] == "v2"
  ```

- [ ] **Step 2: Remove legacy stage keys from read model and schema**

  In `SignalPulseService._stages_for`, change the `empty` dict to:

  ```python
  empty: dict[str, dict[str, Any] | None] = {
      "investigator": None,
      "decision_maker": None,
      "research_only_gate": None,
  }
  ```

  In `SignalPulseStages`, remove `analyst`, `critic`, and `judge`.

- [ ] **Step 3: Remove frontend legacy model and UI**

  In `pulseDetail.ts`, remove:

  - `LegacyStageView`
  - `kind: "legacy"` from `StageRailItem`
  - `isLegacy`
  - `hasLegacyStages`
  - legacy stage collection from `buildAgent`

  In `PulseAgentRail.tsx`, remove legacy notice and `LegacyBody`.

- [ ] **Step 4: Regenerate contracts**

  Run:

  ```bash
  make regen-contract
  uv run pytest tests/contract -m contract -q
  ```

- [ ] **Step 5: Run frontend tests**

  Run:

  ```bash
  cd web
  npm test -- --run web/tests/unit/features/signal-lab/pulseDetail.test.ts web/tests/component/features/signal-lab/ui/PulseAgentRail.test.tsx
  npm run build
  cd ..
  ```

---

## Task 5: Validate Config And Update Architecture Docs

**Intent:** Remove silent config drift and make docs match the real writer/stage model.

**Files:**
- Modify: `src/parallax/platform/config/settings.py`
- Modify: `tests/unit/test_settings.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/superpowers/specs/active/2026-05-17-pulse-control-plane-architecture-cn.md`

- [ ] **Step 1: Add settings validation tests**

  Add to `tests/unit/test_settings.py`:

  ```python
  def test_signal_pulse_rule_rejects_theme_watch_status(tmp_path, monkeypatch):
      monkeypatch.setenv("HOME", str(tmp_path))
      write_config(
          tmp_path,
          {
              "ws_token": "secret",
              "handles": ["toly"],
              "notifications": {
                  "rules": {
                      "signal_pulse_candidate": {
                          "statuses": ["trade_candidate", "theme_watch"],
                      }
                  }
              },
          },
      )

      with pytest.raises(ValidationError, match="unsupported Signal Pulse statuses"):
          load_settings()
  ```

- [ ] **Step 2: Implement validation in `NotificationsConfig.parse_rules`**

  In the `signal_pulse_candidate` branch, add:

  ```python
  allowed_statuses = {"trade_candidate", "token_watch", "risk_rejected_high_info"}
  raw_statuses = payload.get("statuses")
  if raw_statuses is not None:
      parsed_statuses = set(_split_values(raw_statuses))
      unsupported = sorted(parsed_statuses - allowed_statuses)
      if unsupported:
          raise ValueError(f"unsupported Signal Pulse statuses: {unsupported}")
  ```

- [ ] **Step 3: Update architecture docs**

  In `docs/ARCHITECTURE.md`, replace the stale Analyst/Critic/Judge description with:

  ```markdown
  Signal Pulse uses the two-stage `Investigator -> DecisionMaker` harness, with `research_only_gate` for deterministic hard-blocks.
  ```

  In `docs/WORKERS.md`, update `pulse_candidate` writes to include:

  ```text
  pulse_agent_jobs, pulse_candidate_edge_state, pulse_candidate_run_budget,
  pulse_target_run_budget, pulse_agent_runs, pulse_agent_run_steps,
  pulse_agent_runtime_versions, pulse_agent_eval_cases,
  pulse_agent_eval_results, pulse_candidates, pulse_playbook_snapshots
  ```

- [ ] **Step 4: Run docs/settings checks**

  Run:

  ```bash
  uv run pytest tests/unit/test_settings.py tests/architecture/test_worker_runtime_contracts.py -q
  ```

---

## Final Verification

- [ ] Run backend targeted suite:

  ```bash
  uv run pytest tests/unit/test_notification_rules.py tests/unit/test_notification_worker_runtime.py tests/unit/test_pulse_admission_policy.py tests/unit/test_pulse_candidate_worker.py tests/integration/test_pulse_repository.py tests/unit/test_settings.py -q
  ```

- [ ] Run contract and docs checks:

  ```bash
  make regen-contract
  make docs-generated
  uv run pytest tests/contract -m contract tests/integration/test_docs_generated.py -q
  ```

- [ ] Run frontend focused suite:

  ```bash
  cd web
  npm test -- --run web/tests/unit/features/signal-lab/pulseDetail.test.ts web/tests/component/features/signal-lab/ui/PulseAgentRail.test.tsx
  npm run build
  cd ..
  ```

- [ ] Run migration smoke:

  ```bash
  uv run alembic upgrade head
  uv run alembic downgrade -1
  uv run alembic upgrade head
  ```

- [ ] Run 48h post-deploy SQL diagnostics against operator config and compare to the spec acceptance metrics.
