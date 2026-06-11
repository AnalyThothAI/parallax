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

## Acceptance criteria

- AC1. WHEN an active SDD feature grows beyond 40 structured tasks THEN `scripts/validate_sdd_artifacts.py` SHALL report `active-feature-too-large` before omnibus active ledgers can satisfy the executable harness.
- AC2. WHEN the workflow, SDD README, or task template describes active records THEN they SHALL name the 40 structured tasks bound, `active-feature-too-large`, and the split or supersede action before operators can create oversized active ledgers from stale guidance.

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
