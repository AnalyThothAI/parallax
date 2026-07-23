# Spec — Verification Harness Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Date**: 2026-07-23
**Owner**: Codex `/root`
**Approved by**: user
**Approved at**: 2026-07-23
**Related**: `docs/WORKFLOW.md`, `docs/TESTING.md`, `docs/sdd/README.md`

## Background

Before this hard cut, the repository exposed `make check-all`,
`make coverage`, and `make check-sdd-completion` as a mandatory completion
chain, with a dedicated development dependency, global threshold
configuration, fixed coverage/skip/E2E sections, and a second completion
transcript. The deleted implementation remains auditable at the fixed
[pre-cut Makefile](https://github.com/AnalyThothAI/parallax/blob/54d3d11a270ce1d9d93240d8593fa0a007b02a50/Makefile#L58-L77),
[dependency configuration](https://github.com/AnalyThothAI/parallax/blob/54d3d11a270ce1d9d93240d8593fa0a007b02a50/pyproject.toml#L31-L38),
and [verification template](https://github.com/AnalyThothAI/parallax/blob/54d3d11a270ce1d9d93240d8593fa0a007b02a50/docs/sdd/_templates/verification-template.md#L32-L91).

The underlying test lanes already have direct interfaces: `make check`,
`make test-integration`, `make test-e2e`, `make test-golden`,
`make test-architecture`, and `make test-contract`. The aggregate completion
layer did not add test capability; it prescribed one repository-wide
combination and duplicated evidence rules across Make, Python, templates,
generated docs, and prose
([pre-cut direct lanes](https://github.com/AnalyThothAI/parallax/blob/54d3d11a270ce1d9d93240d8593fa0a007b02a50/Makefile#L21-L56)).

## Problem

Every change is forced through a repository-wide completion ritual even when
its risk is narrow. This makes verification slow, creates false pressure to run
unrelated lanes, and expands the agent harness with coverage-specific code and
fixed evidence sections that do not improve the observable behavior of the
product.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| Are tests being removed? | No. Existing unit, architecture, contract, integration, E2E, golden, lint, typecheck, and build commands remain directly runnable. | user | 2026-07-23 |
| Is code coverage still mandatory? | No. Remove the dependency, configuration, Make target, validator rules, and documentation. | user | 2026-07-23 |
| Is one aggregate completion command retained? | No. Delete `make check-all` and `make check-sdd-completion` without aliases. | user | 2026-07-23 |
| What proves a feature? | The plan selects commands proportional to risk; verification records their output and maps successful commands to acceptance criteria. | user | 2026-07-23 |
| Are historical records rewritten? | No. Completed SDDs and audit reports remain historical evidence. | user | 2026-07-23 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| Aggregate and coverage interfaces are absent. | Make help, dependency lock, configuration, and residual scans show no live interface. |
| SDD verification accepts relevant commands. | Validator interface tests cover multiple successful targeted commands. |
| Failed or missing evidence cannot pass. | Validator interface tests retain non-zero and missing-command rejection. |
| Current governance describes risk-based verification. | Router, workflow, testing, playbook, SDD, README, and templates agree. |
| The accepted Macro hard cut is no longer blocked by the retired wrapper. | Its 16 acceptance criteria cite successful direct evidence and its verify gate passes. |

## First principles

- The test lane is the interface; an aggregate pass-through target is not a
  separate test capability.
- Verification must match the changed seam and risk, not repository size.
- Evidence stays honest: omitted lanes are reported, not silently promoted.

## Goals

- G1. Remove `check-all`, `check-sdd-completion`, and coverage tooling from the
  live build and dependency interfaces.
- G2. Reduce SDD verification to acceptance-criterion mapping plus successful
  command evidence.
- G3. Remove fixed coverage, zero-skip, E2E, and completion-transcript
  requirements from current templates, validators, generated summaries, and
  canonical governance.
- G4. Close the accepted Macro hard-cut SDD from its recorded direct evidence
  without fabricating aggregate-gate success.

## Non-goals

- N1. Do not delete test suites or their direct Make targets.
- N2. Do not weaken product architecture, schema, or public-contract tests.
- N3. Do not rewrite completed SDDs, immutable audits, or historical command
  transcripts.
- N4. Do not create a replacement aggregate command, wrapper, alias, or CI
  compatibility path.

## Target architecture

Verification has one small policy seam: each plan names the commands needed for
its acceptance criteria, and the verification record captures successful
outputs. Direct test/lint/build commands remain independent. SDD validation
checks evidence integrity, not a universal command list or metric threshold.

## Conceptual data flow

```text
spec acceptance criteria
  -> plan-selected direct commands
  -> command output and exit status
  -> verification criterion mapping
  -> SDD verify gate
```

The retired path is the repository-wide aggregate command plus coverage and
completion meta-transcript.

## Core models

- **Verification command**: any relevant direct command recorded with output
  and exit status.
- **Spec compliance row**: one acceptance criterion, a terminal status, and one
  or more recorded successful commands.
- **Omitted lane**: a risk or command not run, stated under risks without being
  represented as passing evidence.

## Interface contracts

- `make check` remains the fast static/unit interface.
- `make test-*` targets remain explicit opt-in lane interfaces.
- `scripts/check_sdd_gate.py --feature <slug> --gate verify` validates complete
  tasks and successful acceptance evidence.
- `verification.md` has no global coverage, skip-count, fixed E2E, or completion
  transcript contract.

## Acceptance criteria

- AC1. WHEN build and dependency interfaces are inspected THEN the system SHALL expose no `check-all`, `check-sdd-completion`, coverage target, coverage configuration, or coverage dependency.
- AC2. WHEN a verified SDD records relevant successful direct commands for every acceptance criterion THEN the system SHALL pass the verify evidence check without requiring a repository-wide command.
- AC3. WHEN a verified SDD omits command evidence or records a non-zero exit for cited evidence THEN the system SHALL fail closed.
- AC4. WHEN current governance and templates are searched THEN the system SHALL describe risk-based lane selection without mandatory coverage, zero-skip, fixed E2E, or completion meta-gates.
- AC5. WHEN the accepted Macro hard-cut SDD is evaluated under the direct-evidence contract THEN the system SHALL pass its verify gate and be archived as completed.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Agents run too little verification. | Medium | Plans must map every acceptance criterion to a direct command; verification must cite successful command evidence. |
| Removal accidentally deletes useful test lanes. | High | Keep every direct test target and run focused harness tests plus `make check`. |
| Historical evidence is destroyed. | Medium | Exclude completed SDDs and audit/review records from cleanup. |
| Old aggregate names survive as compatibility aliases. | Medium | Residual scan covers live Make, config, scripts, templates, routers, and canonical docs. |

## Evolution path

If repeated risk patterns emerge, document small recommended command sets in
`docs/TESTING.md`. Do not recreate a mandatory universal wrapper.

## Alternatives considered

- Keep `make check-all` as optional — rejected because the name and existing
  validator coupling preserve the same central interface and invite policy
  drift back into a requirement.
- Keep coverage but remove its threshold — rejected because the dependency,
  configuration, command, and evidence sections would remain unused machinery.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Preserve direct test lanes and honest recorded evidence. |
| Ask first | Add a new mandatory repository-wide verification policy. |
| Never | Restore aggregate aliases, global coverage thresholds, or fabricated completion evidence. |
