# Subagent Handoff - 2026-07-23-macro-evidence-ai-hard-cut / Task 8

Mode: review-only
Mode constraints:
- Review-only mode: do not edit files; review existing scope and report issues only.

Goal:
- Independently review the final Macro evidence and product-AI hard cut against
  the approved Spec, repository standards, migration safety, frontend public
  behavior, and completion claims. Return PASS, WARN, or FAIL with P0/P1/P2
  findings; do not repair findings.

Context packet:

```md
# Context Packet - 2026-07-23-macro-evidence-ai-hard-cut / Task 8

Mode: review-only
Mode constraints:
- Review-only mode: do not edit files; review existing scope and report issues only.
Factory lane: Final integration

Required review:
- Read `AGENTS.md` and `docs/agent-playbook/task-reading-matrix.md`.
- Read the active Spec, Plan, Tasks, and Verification artifacts.
- Inspect the complete feature diff from fixed base `11a7fab52d9`.
- Review revision `20260723_0191`, its non-empty migration/contract tests, the
  current Macro projection, strict HTTP contracts, product-AI deletion guard,
  Token/Watchlist public behavior, and the explicit six-page frontend.
- Cross-check Docker/API/browser receipts and the final `make check-all`
  transcript when it is available.
- Do not edit files, stage, commit, connect to or mutate PostgreSQL, operate
  Docker, expose secrets, or infer a passing full gate from focused tests.
```

Report contract:
- Use headings: `## Findings`, `## Scope Adherence`, `## Changed Files`,
  `## Required Reading Evidence`, `## Verification Evidence`, and
  `## Remaining Risks`.
- Include `Owned scope: pass`, `Conflict set: pass`, exact commands with
  `exit code:`, and an overall PASS, WARN, or FAIL verdict.
- Parent validates the report with `uv run python scripts/validate_subagent_report.py --feature 2026-07-23-macro-evidence-ai-hard-cut --task 8 --mode review-only --report <report.md>`.

Expected output:
- Findings first, ordered P0/P1/P2, with exact source evidence.
- No changed files.
- Separate Standards and Spec verdicts.
- Explicitly distinguish focused read-only checks from the root-owned migration,
  Docker, browser, and full-gate evidence.

Verification evidence:
- `make check-all`

Constraints:
- Treat generated reports and prior agent findings as evidence, not authority.
- Do not weaken the approved no-compatibility or fail-closed boundaries.
- Keep the feature in Review until the root-owned completion evidence is final.
