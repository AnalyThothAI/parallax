# Subagent Report - 2026-07-23-macro-evidence-ai-hard-cut / Task 7 Canonical Docs

Mode: write-allowed

## Findings

- The previous current documentation described a generic Macro module product
  and a production model-backed News path that no longer exist in the approved
  contract.
- Canonical architecture, public-contract, frontend, worker, reliability,
  setup, design-discipline, README, router, and agent-playbook documents now
  describe one stable `macro_evidence_v1` current snapshot containing exactly
  six typed page documents, six page APIs plus one persisted-series API, the
  latest completed US-session cutoff, strict evidence/freshness/rule-hit
  judgments, and ordinary `404` handling for unmatched Macro paths.
- The Macro domain map now documents page-specific Cross-asset, Rates &
  Inflation, Growth & Labor, Liquidity & Funding, and six-layer Credit
  contracts; critical gaps fail the claim closed, optional gaps degrade it,
  and unsupported capabilities remain named `not_assessed`.
- News, Search, Token Radar, Token Case, and Notifications documentation now
  describes source facts and transparent deterministic factors only. News has
  one page dirty-target kind and one fact-only page writer. Notifications
  consume only watched-account activity and watched-account token-alert facts.
- `docs/AGENT_EXECUTION.md` now owns only the dormant provider-neutral
  structured-JSON/capability/hash/schema/usage library. It explicitly records
  that production composition, workers, status, Ops, domains, API, CLI, and UI
  have no model consumer, prompt catalog, product queue, or derived business
  state.
- `AGENTS.md` and `CLAUDE.md` retain byte-identical shared router blocks and
  route model-library questions to the dormant-library document.
- Current canonical Markdown outside historical references, reviews, generated
  evidence, and completed/active SDD records has zero matches for the retired
  Macro/product-model contract vocabulary used by the scoped residual guard.

## Scope Adherence

Owned scope: pass

Conflict set: pass

The parent explicitly expanded the owned documentation scope to include
`README.md`, both mirrored routers, the task-reading matrix, and the two
current development-agent workflow documents found by the residual scan. No
Python/TypeScript source, test, migration, active/completed SDD record,
historical review/reference, generated OpenAPI/type/index, or operator config
was edited. This report is the only generated artifact added by this lane.

## Changed Files

- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/AGENT_EXECUTION.md`
- `docs/ARCHITECTURE.md`
- `docs/CONTRACTS.md`
- `docs/DESIGN_DISCIPLINE.md`
- `docs/FRONTEND.md`
- `docs/RELIABILITY.md`
- `docs/SETUP.md`
- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/agent-playbook/task-reading-matrix.md`
- `docs/agent-playbook/eval-repair-loop.md`
- `docs/agent-playbook/factory-operating-model.md`
- `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- `src/parallax/domains/news_intel/ARCHITECTURE.md`
- `src/parallax/domains/notifications/ARCHITECTURE.md`
- `src/parallax/domains/token_intel/ARCHITECTURE.md`
- `docs/generated/subagent-reports/macro-evidence-ai-hard-cut-task-7-docs.md`

## Required Reading Evidence

Task classification: Agent Workflow Or Documentation Harness; Read Model
Change Review; Macro Evidence Snapshot Or Freshness.

- `AGENTS.md`: material-fact truth, stable current identities, one writer,
  zero-write unchanged projections, real operator config, and frontend CSS
  ownership.
- `docs/agent-playbook/task-reading-matrix.md`: documentation, read-model,
  worker, frontend, and Macro context routing.
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/spec.md`:
  approved G1-G8 and AC1-AC16 contract.
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/plan.md`:
  exact hard-cut architecture, storage/API/frontend/docs scope, rollout, and
  rollback boundary.
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/tasks.md`:
  Task 7 touch/conflict sets and canonical/generated contract gate.
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/verification.md`:
  current in-progress evidence and final completion boundary.
- Existing canonical docs and all four changed domain maps were read end to
  end before editing.
- Current `worker_manifest.py`, Macro/News/Search API routes and strict schemas,
  Macro concept/evidence/rule/snapshot modules, projection repository and
  irreversible migration, News fact-only projection/dirty-target code,
  notification rules/repository/worker, Token factor schema, dormant
  model-execution primitives, settings, and tests were inspected to keep
  documentation source-backed.

## Verification Evidence

Current replacement contract and product-model absence:

```text
$ uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/unit/test_api_macro_contract.py tests/unit/test_api_news_contract.py -q
..........................                                               [100%]
26 passed in 3.93s
exit code: 0
```

Root architecture invariants:

```text
$ uv run pytest tests/architecture/test_kiss_runtime_invariants.py -q
...........                                                              [100%]
11 passed in 1.03s
exit code: 0
```

Mirrored shared router:

```text
$ diff -u <(sed -n '/<!-- BEGIN SHARED AGENT ROUTER -->/,/<!-- END SHARED AGENT ROUTER -->/p' AGENTS.md) <(sed -n '/<!-- BEGIN SHARED AGENT ROUTER -->/,/<!-- END SHARED AGENT ROUTER -->/p' CLAUDE.md)
router_status=0
exit code: 0
```

Scoped current-document residual guard:

```text
$ rg ... README.md AGENTS.md CLAUDE.md docs src/parallax/domains/*/ARCHITECTURE.md
residual_count=0
exit code: 0
```

Owned-file whitespace check:

```text
$ git diff --check -- <owned canonical docs and architecture maps>
diff_check_exit=0
exit code: 0
```

Subagent report validator:

```text
$ uv run python scripts/validate_subagent_report.py --feature 2026-07-23-macro-evidence-ai-hard-cut --task 7 --mode write-allowed --report docs/generated/subagent-reports/macro-evidence-ai-hard-cut-task-7-docs.md
error: changed files must stay within task touch set
error: verification command must match task verification
exit code: 1
```

This lane was explicitly expanded by the parent to `README.md` and current
agent-playbook documents that are not listed in the active Task 7 touch set,
while the task's registered verification command performs parent-owned
generation. The lane was also explicitly forbidden from editing the active SDD
or generated contracts. Parent integration must reconcile that coordination
metadata and run the registered full Task 7 command.

## Remaining Risks

- Generated OpenAPI, frontend types, database schema, CLI help, and SDD index
  remain parent-owned and were deliberately not regenerated by this lane.
- The generated report is not validator-accepted until the parent reconciles
  the expanded touch set and records/runs the registered Task 7 verification.
- Frontend implementation and final API integration were still changing while
  this report was written. Parent review must compare their final names and
  payloads with these canonical docs before regeneration.
- This lane did not run Docker, browser viewports, the irreversible migration,
  or `make check-all`; those are Task 8 completion evidence and cannot be
  inferred from documentation checks.
