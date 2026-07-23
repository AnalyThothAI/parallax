# Development

This document owns design, SDD, worktree, test-selection, and completion rules.

## Design before implementation

Audit the existing seam before adding a service, table, worker, score, or
contract:

1. trace provider input to PostgreSQL fact, durable target, current row, and
   concrete consumer;
2. read the existing owning service and domain architecture map;
3. identify persisted fields that are not yet consumed;
4. extend the existing owner unless lifecycle or responsibility genuinely
   differs.

New tables, workers, model-backed product consumers, probabilistic outputs, and
evaluation control planes require an explicit current need and an approved
design. Prefer deterministic, explainable factors with component breakdowns.
Every ranking formula change bumps `score_version`.

Specs describe intent and semantic contracts. Plans own file edits, SQL,
migrations, tests, rollout, and rollback. Neither is a change diary.

## SDD workflow

Trivial low-risk edits may go direct. Non-trivial changes use one directory:

```text
docs/sdd/features/active/YYYY-MM-DD-<slug>/
  spec.md
  plan.md
  tasks.md
  verification.md
```

The sequence is:

```text
spec -> clarify -> checklist -> plan -> tasks -> analyze -> implement -> verify
```

Keep active boards at or below 40 tasks. Tasks record owner, dependency, touch
set, conflict set, failing contract where applicable, implementation, and one
verification command. Native agent collaboration stays outside the repository;
do not create handoff, dispatch, context-packet, or agent-report artifacts.

Validation:

```bash
uv run python scripts/validate_sdd_artifacts.py
uv run python scripts/regen_sdd_work_index.py --check
uv run python scripts/check_sdd_gate.py --feature <slug> --gate verify
```

After every acceptance criterion has successful evidence and every task is
complete, move the whole feature directory to `features/completed/`.

## Worktrees

Coding changes use an isolated `.worktrees/<branch-slug>/` worktree from
`main`, unless the user names another base. Inspect worktree, branch, and dirty
state before editing. Existing worktrees belong to their current task.

## Tests

| Lane | Location | Proves |
|---|---|---|
| Unit | `tests/unit/` | deterministic in-process behavior |
| Architecture | `tests/architecture/` | durable ownership/import invariants |
| Contract | `tests/contract/` | public and generated schemas |
| Integration | `tests/integration/` | real PostgreSQL and composed service behavior |
| Golden | `tests/golden/` | curated end-to-end data expectations |
| E2E | `tests/e2e/` | running process boundaries |
| Frontend | `web/tests/` | UI, route, model, and architecture behavior |

Select commands by risk:

- schema/repository changes: focused PostgreSQL integration tests;
- HTTP changes: API behavior, OpenAPI drift, regenerated frontend types;
- UI changes: scoped tests, lint, typecheck, and browser checks for layout or
  interaction;
- generated files: their generator and clean-diff contract;
- documentation: surface/link validators and `git diff --check`;
- workers: bounded claim, lease, retry/terminal, restart catch-up, idempotency,
  single writer, and external-I/O transaction boundaries.

`make check` is a convenient fast bundle, not a universal completion mandate.
There is no mandatory repository-wide command or coverage threshold. The plan
chooses commands proportional to the changed seam.

## Generated contracts

`docs/generated/` contains only reproducible outputs. Run:

```bash
make docs-generated
make regen-contract
```

when their sources change. Generated OpenAPI and frontend types change in the
same commit as their API owner.

## Completion evidence

A change is complete only when:

- observable behavior and durable invariants have direct successful evidence;
- generated outputs are current;
- omitted lanes and remaining risks are stated honestly;
- the SDD validator and selected verify gate pass for SDD work;
- old names, routes, files, and compatibility paths are removed.

Do not manufacture green results with skip flags, compatibility mocks, or
private source-text assertions.
