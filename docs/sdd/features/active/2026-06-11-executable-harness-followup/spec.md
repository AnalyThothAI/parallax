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

## Acceptance criteria

- AC1. WHEN an active SDD feature grows beyond 40 structured tasks THEN `scripts/validate_sdd_artifacts.py` SHALL report `active-feature-too-large` before omnibus active ledgers can satisfy the executable harness.
- AC2. WHEN the workflow, SDD README, or task template describes active records THEN they SHALL name the 40 structured tasks bound, `active-feature-too-large`, and the split or supersede action before operators can create oversized active ledgers from stale guidance.
- AC3. WHEN the verification template describes E2E golden path evidence THEN it SHALL reference the current feature spec instead of a fixed historical section anchor before agents can copy stale completion instructions.
- AC4. WHEN final verification status cells use symbolic pass/fail tokens such as checkmarks THEN `scripts/validate_sdd_artifacts.py` SHALL reject them, and the verification template SHALL teach machine-readable `Pass`/`Fail` examples instead.
- AC5. WHEN any SDD `verification.md` Spec compliance or Coverage table uses symbolic or prose-mixed status cells THEN `scripts/validate_sdd_artifacts.py` SHALL report `verification-status-token-invalid` before active or historical records can satisfy the harness.
- AC6. WHEN an active SDD record advertises `--check` on `scripts/validate_sdd_artifacts.py` or `scripts/check_sdd_gate.py` THEN `scripts/validate_sdd_artifacts.py` SHALL report `active-sdd-lifecycle-check-flag-invalid` before obsolete lifecycle compatibility flags can guide current work.
- AC7. WHEN an active `verification.md` contains placeholder final transcript text such as `Pending final run` or `exit code: pending` THEN `scripts/validate_sdd_artifacts.py` SHALL report `active-placeholder-final-evidence` before placeholder command output can masquerade as executable evidence.

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
