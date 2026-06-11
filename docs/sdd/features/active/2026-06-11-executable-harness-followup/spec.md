# Spec - Executable Harness Followup

**Status**: In Progress
**Date**: 2026-06-11
**Owner**: Codex
**Approved by**: qinghuan
**Approved at**: 2026-06-11

## Background

The prior executable harness record was an omnibus active ledger with more than 250 tasks. The current workflow points agents to docs/sdd/ as the canonical Spec -> Plan -> Tasks -> verification lane in docs/WORKFLOW.md:1, and the validator source is scripts/validate_sdd_artifacts.py:1.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| How should ongoing harness work continue after the omnibus record? | Supersede the oversized record and continue in small active records with executable gates. | qinghuan | 2026-06-11 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| Active SDD records stay bounded. | Validator rejects active features with more than 40 tasks. |
| SDD docs teach the same bound. | Architecture harness rejects workflow, README, or template drift from the validator limit. |
| Verification templates stay current. | Architecture harness rejects stale fixed spec-section anchors in completion evidence templates. |
| Completion status tokens are machine-readable. | Validator rejects symbolic final-evidence status cells, and templates teach `Pass`/`Fail` examples. |
| Verification status tokens are lifecycle-wide. | Validator rejects symbolic status cells in active, superseded, and verified `verification.md` tables. |
| Active records use current SDD lifecycle commands. | Validator rejects active records that advertise obsolete lifecycle `--check` flags. |
| Active records do not fake final transcripts. | Validator rejects placeholder final command transcripts in active `verification.md` records. |
| Active skipped-test accounting is final-run-bound. | Validator rejects numeric skipped-test counts in active `verification.md` records without successful final `make check-all` evidence. |
| Verification templates fail closed. | Templates do not embed fake final `exit code: 0` transcripts, and validator rejects copied template transcript placeholders in active records. |
| Subagent context packets are dispatch-bound. | Context packet generation rejects completed or dependency-blocked tasks before a subagent can receive stale context. |
| Subagent mode constraints are deterministic. | Context packet and handoff generation emit mode-specific edit boundaries for read-only, write-allowed, and review-only lanes. |
| Subagent handoff artifacts enforce mode constraints. | Validator rejects delegated handoff artifacts that omit the mode-specific edit boundary emitted by the generator. |

## Acceptance criteria

- AC1. WHEN an active SDD feature grows beyond 40 structured tasks THEN `scripts/validate_sdd_artifacts.py` SHALL report `active-feature-too-large` before omnibus active ledgers can satisfy the executable harness.
- AC2. WHEN the workflow, SDD README, or task template describes active records THEN they SHALL name the 40 structured tasks bound, `active-feature-too-large`, and the split or supersede action before operators can create oversized active ledgers from stale guidance.
- AC3. WHEN the verification template describes E2E golden path evidence THEN it SHALL reference the current feature spec instead of a fixed historical section anchor before agents can copy stale completion instructions.
- AC4. WHEN final verification status cells use symbolic pass/fail tokens such as checkmarks THEN `scripts/validate_sdd_artifacts.py` SHALL reject them, and the verification template SHALL teach machine-readable `Pass`/`Fail` examples instead.
- AC5. WHEN any SDD `verification.md` Spec compliance or Coverage table uses symbolic or prose-mixed status cells THEN `scripts/validate_sdd_artifacts.py` SHALL report `verification-status-token-invalid` before active or historical records can satisfy the harness.
- AC6. WHEN an active SDD record advertises `--check` on `scripts/validate_sdd_artifacts.py` or `scripts/check_sdd_gate.py` THEN `scripts/validate_sdd_artifacts.py` SHALL report `active-sdd-lifecycle-check-flag-invalid` before obsolete lifecycle compatibility flags can guide current work.
- AC7. WHEN an active `verification.md` contains placeholder final transcript text such as `Pending final run` or `exit code: pending` THEN `scripts/validate_sdd_artifacts.py` SHALL report `active-placeholder-final-evidence` before placeholder command output can masquerade as executable evidence.
- AC8. WHEN an active `verification.md` lacks successful final `make check-all` evidence THEN `scripts/validate_sdd_artifacts.py` SHALL report `active-skipped-count-without-final-evidence` for numeric `Skipped tests` run-above counts before zero-skip claims can masquerade as executable evidence.
- AC9. WHEN `docs/sdd/_templates/verification-template.md` teaches final command evidence THEN it SHALL fail closed with a non-success exit placeholder, and `scripts/validate_sdd_artifacts.py` SHALL report `active-placeholder-final-evidence` if that transcript placeholder is copied into an active record.
- AC10. WHEN `scripts/build_agent_context_packet.py` is asked to build context for a completed task or a task with incomplete dependencies THEN it SHALL fail with the same dispatchability reason as `scripts/dispatch_sdd_task.py` before subagents can receive stale or blocked task context.
- AC11. WHEN `scripts/build_agent_context_packet.py` or `scripts/dispatch_sdd_task.py` emits subagent context THEN it SHALL include mode-specific edit constraints before read-only, write-allowed, or review-only lanes can rely on implicit prompt convention.
- AC12. WHEN a delegated task references a `Subagent handoff` artifact THEN `scripts/validate_sdd_artifacts.py` SHALL reject it as `task-invalid-subagent-handoff-artifact` unless the artifact contains `Mode constraints:` and the constraint line matching its `Mode:`.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| A hard size limit blocks legitimate large programs. | Medium | Split large programs into successor SDD records instead of allowing one active ledger to absorb every task. |

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Keep active feature records small enough for a reviewable agent loop. |
| Ask first | Raising the task-count threshold. |
| Never | Add compatibility exemptions for specific oversized active records. |
