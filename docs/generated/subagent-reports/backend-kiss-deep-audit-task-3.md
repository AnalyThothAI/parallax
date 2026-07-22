# News, Macro, and test-architecture KISS audit

Mode: read-only

## Findings

- CUT: remove confirmed-unused fake connection/settings/provider helpers in News and Macro tests; they have no call sites.
- CUT: move the real PostgreSQL low-score News page inclusion assertion into the existing page-repository integration test and delete the private signature/SQL-negative unit test.
- CUT: delete redundant Macro repository/source-shape tests already covered by current-generation behavior, root repository AST checks, or real PostgreSQL integration; keep fake SQL tests where PostgreSQL behavior has no executable replacement.
- CUT: call `servable_news_item_ids` directly rather than catch all `AttributeError` from inside the repository method and relabel it as a missing-method error.
- KEEP: News canonical upsert, story/model ledgers, Macro fact/sync/current state machines, and the large cohesive repository modules. Splitting them by file size would add indirection without removing decisions.
- DEFER: `news_story_brief_worker.py` records the model run after external I/O, leaving a crash window for a duplicate paid call. Fixing it needs a durable pre-call/CAS design and belongs in a correctness feature.

## Scope Adherence

Owned scope: pass

Conflict set: pass

The audit was read-only and did not touch the active News FK-index feature or schema tests.

## Changed Files

None.

## Required Reading Evidence

Task classification: News/Macro data-flow and test-maintenance audit.

Read `AGENTS.md`, `docs/agent-playbook/task-reading-matrix.md`, canonical root documents, News and Macro architecture maps, current repositories/services/tests, and the existing implementation audit.

## Verification Evidence

```text
$ uv run pytest -q tests/architecture/test_kiss_runtime_invariants.py
............                                                             [100%]
12 passed in 2.25s
exit code: 0
```

## Remaining Risks

- Bulk fake-SQL deletion remains deferred until equivalent real PostgreSQL coverage exists.
- The model-run crash window is a correctness risk and must not be disguised as a KISS-only refactor.
