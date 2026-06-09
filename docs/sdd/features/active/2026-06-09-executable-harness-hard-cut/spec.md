# Spec — Executable Harness Hard Cut

**Status**: In Progress
**Date**: 2026-06-09
**Owner**: Codex
**Approved by**: qinghuan
**Approved at**: 2026-06-09
**Related**: `docs/WORKFLOW.md`, `docs/sdd/README.md`, `scripts/regen_sdd_work_index.py`

## Background

Parallax already routes non-trivial coding-agent work through the SDD lane in `docs/WORKFLOW.md:7`.
The lane requires `spec.md`, `plan.md`, `tasks.md`, and `verification.md`, and says production work follows
`spec -> clarify -> checklist -> plan -> tasks -> analyze -> implement -> verify` in `docs/WORKFLOW.md:22`.
Completion requires `make check-all` evidence in `docs/WORKFLOW.md:57`. The current generated index is produced
by `scripts/regen_sdd_work_index.py:1` and currently reports only lifecycle/status hygiene.

Latest external SDD and agent-loop references reinforce the same direction: GitHub Spec Kit documents specify, plan, tasks, and implement commands plus clarify/checklist/analyze gates (https://github.com/github/spec-kit), OpenAI's agent evaluation docs emphasize reproducible evals and trace grading (https://platform.openai.com/docs/guides/agent-evals), Claude Code docs separate deterministic hooks and bounded subagents (https://code.claude.com/docs/en/agent-sdk/hooks, https://code.claude.com/docs/en/sub-agents), and GitHub Copilot task guidance emphasizes scoped task prompts for coding agents (https://docs.github.com/en/enterprise-cloud@latest/copilot/using-github-copilot/coding-agent/best-practices-for-using-copilot-to-work-on-tasks).

## Problem

The harness proves that SDD files exist and have lane-valid status strings, but it does not prove that the
records are truthful, coordinated, or useful for multi-agent execution. A completed record can say `Verified`
while its verification text admits that `make check-all` did not produce final evidence. Test architecture also
contains useful hard-cut tripwires mixed with brittle wording, source-shape, and exact SQL checks, so the harness
can both miss real process drift and block healthy refactors.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| Should old SDD compatibility lanes or retired planning trees remain supported? | No. The current `docs/sdd/` lane is the only planning lane. | qinghuan | 2026-06-09 |
| Should `Verified` ever allow partial `make check-all` evidence? | No. Use `Review`, `Blocked`, or `Superseded` until final evidence exists. | qinghuan | 2026-06-09 |
| Should brittle tests be deleted without replacement? | No. Hard-cut tripwires stay when they defend retired runtime surfaces, but behavior contracts replace accidental shape locks. | qinghuan | 2026-06-09 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| SDD truth must be executable. | A script fails false `Verified` records, missing gate sections, missing approval metadata, and incomplete task coordination fields. |
| Active work must be coordinatable. | The generated SDD index includes owner, worktree, branch, factory lanes, touch set, conflict set, blocked state, and verification status. |
| Test harness intent must be explicit. | Architecture tests classify permanent invariants, migration tripwires, behavior contracts, and generated hygiene. |
| SQL tests must avoid accidental alias/order coupling. | A query-contract helper checks tables, predicates, locks, params, and forbidden surfaces without pinning formatting. |
| Completion gates must be deterministic. | `make check-all` runs the SDD validator and stale generated index check. |
| Multi-agent development loops must be bounded. | Task records declare factory lane, deterministic constraints, on-demand context, kill/defer criteria, and eval/repair signal. |
| Task dependencies must be executable. | Task dependency references are parsed, unresolved references fail validation, and unmet dependencies block dry-run dispatch. |
| Subagent return evidence must be executable. | Subagent reports are validated against the owning SDD task for scope adherence, changed-file claims, expected verification command, exit status, and secret hygiene before parent integration. |
| Parent review outcome must be visible. | Task records expose subagent report and review result fields, and the generated Task Board surfaces review state including `needs-repair`. |
| Referenced report artifacts must be real. | Delegated task report paths are checked for existence and validated against the task-bound report contract by the SDD validator. |
| Completed task status must be evidenced. | A `[x]` task requires matching `verification.md` command evidence with exit code 0. |
| Machine fields must be exact tokens. | `Subagent handoff` accepts only the exact `not delegated` token or a repo path, not prose suffixes. |
| Delegated handoff artifacts must be real. | Delegated task handoff paths are checked for existence before dispatch or review. |
| Verified spec-compliance rows must be evidenced. | A `Verified` record cannot mark a compliance row complete unless command-shaped evidence in that row has exit code 0 in canonical evidence sections. |
| Worktree and branch metadata must be machine-valid. | `plan.md`, `tasks.md`, and `verification.md` must agree on either `codex/<slug>` with `.worktrees/<slug>` or exact `main`/`main` metadata. |
| Spec background must be source-backed. | Each `spec.md` Background claim block must cite an existing repo `path:line` or an external `https://` source. |

## First principles

- Material facts and runtime behavior remain the source of product truth; SDD files are execution records, as stated in `docs/sdd/README.md:13`.
- Development-agent orchestration must stay separate from product LLM agents; `docs/AGENT_EXECUTION.md:3` owns the product runtime boundary.
- Hard cuts should delete compatibility surfaces, not wrap them; `docs/WORKFLOW.md:49` already requires isolated worktrees for non-trivial coding work.

## Goals

- G1. A `Verified` SDD artifact set with missing or contradicted `make check-all` evidence fails `uv run python scripts/validate_sdd_artifacts.py --check`.
- G2. A filled `tasks.md` without owner, touch set, conflict set, verification command, review owner, or task status fails the same validator.
- G3. `docs/generated/sdd-work-index.md` renders a coordination board with owner, worktree, branch, touch set, conflict set, blocked state, and verification status.
- G4. Tests that rely on SQL shape can use a query-contract helper to assert semantic SQL contracts without exact alias or whitespace coupling.
- G5. `make check-all` includes SDD artifact validation and generated index freshness so harness drift blocks completion.
- G6. Development-agent work follows an explicit factory/eval loop that separates deterministic constraints from on-demand context, keeps product LLM agents outside development lanes, and records repair signals.
- G7. Parent agents can generate a bounded subagent context packet from a validated active SDD task without hand-copying template prose.
- G8. Parent agents can generate a dry-run subagent handoff from a dispatchable active SDD task and the harness refuses completed tasks.
- G9. Task coordination fields are semantically validated, not accepted by mere presence.
- G10. `Verified` evidence is parsed from the canonical verification command block, not from old success snippets elsewhere in the file.
- G11. The generated SDD work index exposes task-level dispatch state, not only feature-level coordination.
- G12. Task dependencies are parsed as task references/ranges, unresolved references fail validation, and dispatch/index state blocks tasks whose dependencies are incomplete.
- G13. Subagent handoffs include a task-bound report contract, and returned reports are machine-validated against the owning SDD task before parent integration.
- G14. Parent review outcome is a structured task field and a generated Task Board state, not prose hidden in a handoff note.
- G15. SDD validation follows delegated `Subagent report` paths and fails missing or invalid report artifacts.
- G16. SDD validation fails any `[x]` task whose `Verification` command is not recorded in `verification.md` with exit code 0.
- G17. SDD validation treats machine-readable task tokens as exact values and rejects prose appended to `not delegated`.
- G18. SDD validation follows delegated `Subagent handoff` paths and fails missing handoff artifacts.

## Non-goals

- N1. This does not add a product LLM agent runtime, background agent task queue, or shared tool loop.
- N2. This does not preserve legacy planning-lane compatibility.
- N3. This does not rewrite every existing SQL test; it establishes the harness and converts the currently blocking obsolete macro contract.

## Target architecture

The SDD lane becomes an executable control plane for development work. A validator parses feature records,
emits explicit issue codes, and exits non-zero when active/completed records violate gate semantics. The generated
work index becomes a compact coordination board for parent agents and subagents, including bounded factory lanes.
Test taxonomy is documented and enforced so string tripwires are deliberate, expiring safeguards rather than
accidental design locks.

## Conceptual data flow

```text
SDD records -> validate_sdd_artifacts -> regen_sdd_work_index -> make check-all
      |                    |                       |
      |                    v                       v
      +------------> issue codes ------------> coordination board
```

The new arrows are harness-only and do not affect runtime product data flow.

## Core models

- `SddFeature`: feature slug, lane, artifact paths, status values, owner, branch, worktree, approval metadata,
  touch set, conflict set, factory lanes, verification status, blocked reason, and issue codes.
- `SddIssue`: code, severity, path, and message for deterministic gate failures.
- `SqlContract`: required tables, forbidden tables, required predicates, forbidden fragments, required locks, and
  expected params.

## Interface contracts

- CLI: `uv run python scripts/validate_sdd_artifacts.py --check` exits 0 when all SDD records satisfy the executable harness and exits 1 with issue lines otherwise.
- CLI: `uv run python scripts/regen_sdd_work_index.py --check` fails when `docs/generated/sdd-work-index.md` is stale.
- CLI: `uv run python scripts/build_agent_context_packet.py --feature <slug> --task <number> --mode <mode>` prints a bounded subagent context packet from active SDD task metadata.
- CLI: `uv run python scripts/dispatch_sdd_task.py --feature <slug> --task <number> --mode <mode>` prints a dry-run handoff prompt and refuses completed, non-dispatchable, or dependency-blocked tasks.
- CLI: `uv run python scripts/validate_subagent_report.py --feature <slug> --task <number> --mode <mode> --report <report.md>` validates a returned subagent report against the owning SDD task before parent integration.
- Test helper: `tests.support.query_contract.assert_query_contract(sql, ...)` raises `AssertionError` with contract-specific messages.

## Acceptance criteria

- AC1. WHEN a completed feature is marked `Verified` without full successful `make check-all` evidence THEN the validator SHALL exit non-zero and report a `verified-missing-check-all` or `verified-contradicts-evidence` issue.
- AC2. WHEN a feature task omits owner/touch/conflict/verification/review/status fields THEN the validator SHALL exit non-zero and report a task coordination issue.
- AC3. WHEN the SDD index is regenerated THEN it SHALL include a coordination board with owner, worktree, branch, factory lanes, touch set, conflict set, blocked state, verification status, and flags.
- AC4. WHEN a SQL unit test uses the query-contract helper THEN it SHALL be able to assert required/forbidden tables and predicates without depending on alias names or whitespace.
- AC5. WHEN `make check-all` runs THEN SDD artifact validation and generated index freshness SHALL be part of the deterministic gate.
- AC6. WHEN task records are created or updated THEN each task SHALL declare factory lane, deterministic constraints, on-demand context, kill/defer criteria, and eval/repair signal; missing fields SHALL report `task-missing-agent-loop-fields`.
- AC7. WHEN a parent agent prepares a subagent handoff THEN the context packet CLI SHALL read a validated active SDD task and output mode, factory lane, owned scope, conflict scope, deterministic constraints, on-demand context, kill/defer criteria, eval/repair signal, verification evidence, redactions, and the product-agent boundary.
- AC8. WHEN a parent agent dispatches a task dry-run THEN the dispatcher SHALL output a handoff prompt containing the generated context packet, and SHALL refuse `[x]` completed tasks.
- AC9. WHEN task records contain non-path file/touch fields, malformed conflict rules, non-test failing-test-first values, non-command verification values, or invalid task statuses THEN the validator SHALL report `task-invalid-coordination-fields`.
- AC10. WHEN a completed SDD record is marked `Verified` THEN the validator SHALL require the `## Verification commands` fenced block to contain the single successful `make check-all` evidence and SHALL reject stale success blocks or unexplained skipped tests.
- AC11. WHEN `docs/generated/sdd-work-index.md` is regenerated THEN it SHALL include a `Task Board` with one row per SDD task showing task status, dispatch state, factory lane, owner, dependency, touch set, conflict set, and verification command.
- AC12. WHEN a task references missing dependency task numbers or a dispatchable task depends on incomplete tasks THEN the validator SHALL report `task-invalid-dependencies` for unresolved references, the dispatcher SHALL refuse the task, and the generated `Task Board` SHALL show `blocked-by-dependencies`.
- AC13. WHEN a subagent report lacks required report sections, lists changed files outside the task touch set, overlaps the conflict set, runs a verification command different from the task command, or records a non-zero exit code THEN the report validator SHALL fail, and generated handoffs SHALL instruct the parent to run that task-bound validator before integration.
- AC14. WHEN a task is delegated or reviewed THEN `tasks.md` SHALL contain `Subagent report` and `Review result`, the validator SHALL reject missing or inconsistent review fields, and the generated `Task Board` SHALL expose review result and `needs-repair` dispatch state.
- AC15. WHEN a delegated task references a `Subagent report` path THEN the SDD validator SHALL require that file to exist and pass the same task-bound subagent report validator.
- AC16. WHEN a task is marked `[x]` THEN its `Verification` command SHALL appear in `verification.md` with exit code 0, otherwise the validator SHALL report `task-complete-missing-verification-evidence`.
- AC17. WHEN `Subagent handoff` starts with `not delegated` but includes extra prose THEN the validator SHALL reject it as `task-invalid-review-fields`; rationale belongs in deterministic constraints, implementation, or verification evidence.
- AC18. WHEN a delegated task references a `Subagent handoff` path THEN the SDD validator SHALL require that file to exist and report `task-missing-subagent-handoff-artifact` when it does not.
- AC19. WHEN one SDD feature has mixed `Status` values across `spec.md`, `plan.md`, `tasks.md`, and `verification.md` THEN the validator SHALL report `artifact-status-mismatch` before any lifecycle transition is trusted.
- AC20. WHEN a `Superseded` artifact only mentions a successor in prose, omits `**Superseded by**`, names a non-path value, or names a missing path THEN the validator SHALL report `superseded-missing-successor`.
- AC21. WHEN an SDD feature directory contains any file or subdirectory besides `spec.md`, `plan.md`, `tasks.md`, and `verification.md` THEN the validator SHALL report `unexpected-artifact`; historical screenshots, mockups, logs, and notes SHALL be removed from feature directories.
- AC22. WHEN a task is marked `[x]` while any declared dependency task is missing or not `[x]` THEN the validator SHALL report `task-invalid-dependencies`; completion order is evidence, not prose.
- AC23. WHEN a completed task's `Verification` command appears only outside `## Verification commands` and `## Other commands run` fenced blocks THEN the validator SHALL report `task-complete-missing-verification-evidence`.
- AC24. WHEN an artifact is `Superseded` but lacks required approval/execution metadata THEN the validator SHALL still report `missing-approval-metadata`; superseded status only skips content-section gates, not metadata truth.
- AC25. WHEN a `Superseded` feature has a legacy checkbox-only `tasks.md` with no structured `### Task` sections THEN the validator SHALL report `task-missing-coordination-fields`.
- AC26. WHEN artifacts in the same `Superseded` feature declare different `Superseded by` paths THEN the validator SHALL report `superseded-successor-mismatch`.
- AC27. WHEN a task is marked `[x]` but `Review result` is not `parent-reviewed` or `accepted` THEN the validator SHALL report `task-complete-missing-review-evidence`; completion requires a review outcome, not just non-delegation.
- AC28. WHEN structured task headings skip, duplicate, or omit machine-readable task numbers THEN the validator SHALL report `task-invalid-numbering`; dispatch dependency graphs require a unique contiguous `Task 1..N` sequence.
- AC29. WHEN `plan.md`, `tasks.md`, or `verification.md` owning links point outside the same feature's canonical `spec.md` or `plan.md` THEN the validator SHALL report `artifact-owning-link-mismatch`; old feature links cannot satisfy current Spec→Plan→Tasks→Verification lineage.
- AC30. WHEN `spec.md` declares an acceptance criterion without a matching `plan.md` `Acceptance test commands` entry, or `plan.md` declares an AC command not present in `spec.md`, THEN the validator SHALL report `acceptance-command-mismatch`; spec criteria and plan commands must have exact machine coverage.
- AC31. WHEN `spec.md` acceptance criteria or `plan.md` acceptance command entries skip, duplicate, or reorder AC numbers THEN the validator SHALL report `acceptance-numbering-invalid`; acceptance criteria must form one unique contiguous `AC1..N` sequence.
- AC32. WHEN `plan.md` acceptance test command entries are prose or otherwise not command-shaped THEN the validator SHALL report `acceptance-command-invalid`; acceptance coverage requires runnable command-shaped evidence, not backticked narration.
- AC33. WHEN `plan.md` acceptance test command bullets contain trailing prose, ranges, or non-AC command labels THEN the validator SHALL report `acceptance-command-invalid`; acceptance test commands must be exact AC-numbered command-only machine lines.
- AC34. WHEN an SDD feature directory uses a freeform slug or an artifact `Date` does not match the slug date THEN the validator SHALL report `feature-slug-invalid`; executable SDD records must use `YYYY-MM-DD-kebab-slug` identity.
- AC35. WHEN required clarify, checklist, analyze, or gate-compliance sections contain only empty template rows or placeholders THEN the validator SHALL report `gate-evidence-missing`; SDD gates require structured evidence, not headings alone.
- AC36. WHEN a `spec.md` acceptance criterion omits the executable `WHEN ... THEN ... SHALL ...` structure THEN the validator SHALL report `acceptance-criterion-format-invalid`; vague acceptance prose cannot satisfy plan-command coverage.
- AC37. WHEN a `Verified` `verification.md` Spec compliance row marks an acceptance criterion complete and references a command-shaped backticked command THEN the validator SHALL require matching exit code 0 evidence for that command in canonical evidence sections and report `verified-missing-spec-compliance-evidence` otherwise.
- AC38. WHEN `plan.md`, `tasks.md`, or `verification.md` declares malformed, template-placeholder, prose, mismatched, or cross-artifact inconsistent Worktree/Branch metadata THEN the validator SHALL report `worktree-metadata-invalid`; execution location metadata must be machine-readable.
- AC39. WHEN a non-superseded `spec.md` Background claim block lacks an existing repo `path:line` citation or external `https://` source THEN the validator SHALL report `spec-background-uncited`; specs must audit current docs/code or external references before planning.
- AC40. WHEN a checked `plan.md` Pre-flight row claims a Worktree/Branch verification that disagrees with the artifact's Worktree/Branch metadata THEN the validator SHALL report `plan-preflight-metadata-mismatch`; checked setup evidence cannot preserve stale worktree names.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Validator becomes another wording-only scanner. | High | Parse stable metadata and issue codes; reserve phrase scans for forbidden contradiction language. |
| Coordination board grows into canonical runtime truth. | Medium | Index states that code/docs/runtime contracts remain canonical truth. |
| SQL helper over-promises parsing. | Medium | Keep it a lightweight contract normalizer for test assertions, not a SQL parser. |
| `make check-all` becomes too slow. | Low | Validator and index checks are pure filesystem scans. |

## Evolution path

The next expansion is a richer active-work dispatch CLI that can split context packets across multiple lanes and
optionally write reviewed packets to generated artifacts. This work should not foreclose that path, but it must avoid
adding durable runtime agent queues.

## Alternatives considered

- Keep prose-only SDD checks — rejected because prose allowed false `Verified` records.
- Add a second planning tree — rejected because `docs/sdd/` is the current hard-cut lane and old lanes should not remain as compatibility paths.
- Fully parse PostgreSQL SQL grammar in tests — rejected because the immediate need is stable contract assertions, not query rewriting.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Validate SDD truth, render coordination fields, classify harness tests, and include the new checks in `make check-all`. |
| Ask first | Large-scale conversion of every SQL test family. |
| Never | Recreate legacy planning folders, accept partial `Verified` evidence, or add compatibility shims for old harness surfaces. |
