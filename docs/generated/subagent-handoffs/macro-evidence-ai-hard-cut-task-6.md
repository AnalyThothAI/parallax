# Subagent Handoff - 2026-07-23-macro-evidence-ai-hard-cut / Task 6

Mode: write-allowed
Mode constraints:
- Write-allowed mode: changed files must stay inside Owned scope and avoid Do not touch.

Goal:
- Hard-cut the frontend to six explicit Macro evidence pages and remove every
  News, Search, Token, Ops, Cockpit, Notification, and Live Radar consumer of
  the retired product-AI contracts.

Owned scope:
- `web/`

Do not touch:
- `src/`
- `docs/`

Must read:
- `AGENTS.md`
- `docs/agent-playbook/task-reading-matrix.md`
- `docs/FRONTEND.md`
- active Spec, Plan, Tasks, and Verification artifacts
- generated frontend OpenAPI types
- current route shell, shared models, fixtures, and frontend architecture tests

Context packet:

```md
# Context Packet - 2026-07-23-macro-evidence-ai-hard-cut / Task 6

Mode: write-allowed
Mode constraints:
- Write-allowed mode: changed files must stay inside Owned scope and avoid Do not touch.
Factory lane: Domain implementation

Current objective:
- Replace the generic Macro workbench with six explicit pages and hard-delete
  every frontend consumer of the retired real or pseudo AI product contract.

Truth boundary:
- Facts: frontend reads only persisted Macro page/series, News, Search, Token,
  event, market, and notification facts.
- Read models: six independently typed Macro page contracts share one persisted
  snapshot metadata tuple.
- Control plane: no model execution, agent worker, or repair state is rendered.
- Cache/fan-out: no semantic catalyst, narrative admission, or agent brief.
- Provider raw inputs: never read directly by the frontend.

Known symptoms:
- The pre-cut UI owns a sixteen-module registry, universal renderer, duplicate
  Macro navigation, and AI-labelled News/Search/Token surfaces.

Canonical docs/code already checked:
- `AGENTS.md` - Kappa/CQRS, hard-cut, and frontend guardrails.
- `docs/agent-playbook/task-reading-matrix.md` - frontend route/CSS and Macro
  evidence reading set.
- `docs/FRONTEND.md` - lazy route ownership, feature CSS, responsive, and
  architecture harness contracts.
- Generated frontend types - the sole response-schema source.

Relevant active planning artefacts:
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/spec.md`
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/plan.md`
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/tasks.md`

Unknowns:
- Any stale generated backend type must be reported to the parent; do not add a
  handwritten compatibility type.

Redactions:
- Credentials and private runtime values are omitted.

Suggested verification:
- `cd web && npm run lint && npm run typecheck && npm run test -- --run tests/component/features/macro tests/routes/macro.route.test.tsx`
```

Report contract:
- Use headings: `## Findings`, `## Scope Adherence`, `## Changed Files`,
  `## Required Reading Evidence`, `## Verification Evidence`, and
  `## Remaining Risks`.
- Include `Owned scope: pass`, `Conflict set: pass`, and command output with
  `exit code:`.
- Parent validates the report with `uv run python scripts/validate_subagent_report.py --feature 2026-07-23-macro-evidence-ai-hard-cut --task 6 --mode write-allowed --report <report.md>`.

Expected output:
- Findings first with source evidence.
- Changed files inside `web/**` only.
- Exact route, contract, responsive, and residual-deletion evidence.

Verification evidence:
- `cd web && npm run lint && npm run typecheck && npm run test -- --run tests/component/features/macro tests/routes/macro.route.test.tsx`

Constraints:
- Work with existing changes; never revert unrelated edits.
- Never print credentials or private runtime values.
- Treat subagent output as evidence, not authority.
