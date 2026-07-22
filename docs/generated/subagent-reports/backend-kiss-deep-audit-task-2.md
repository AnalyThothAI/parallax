# Fact and projection domain KISS audit

Mode: read-only

## Findings

- CUT: `CollectorService` queries event token resolutions after `IngestedEvent` already carries the committed resolutions. Publish the returned payload and delete the extra store protocol/query.
- CUT: resolution refresh and token-intent rebuild return fake `anchor`/deferred projection results even though the Radar worker owns projection. Remove the placeholders and the unused `projection_limit` echo.
- CUT: `_missing_work_items()` is a subset of the existing hot-work selector and is deduplicated immediately afterward; delete it and its private-method tests.
- KEEP: material evidence, identity decisions, market facts, dirty targets, Radar publication state, notification/delivery ledgers, and the raw-event provenance hold all encode current truth or recovery.
- DEFER: token-image completion is split across transactions; discovery also has a crash-sensitive in-flight state, and notification stale CAS outcomes can be misreported. These are correctness hardening tasks, not safe deletion-only edits.
- DEFER: unifying the two ingest entry contexts would mix the production market-capture boundary with the deterministic test/E2E ingest path; remove only the demonstrated redundant post-commit query in this slice.

## Scope Adherence

Owned scope: pass

Conflict set: pass

The audit stayed within evidence, ingestion, asset-market, Token Intel, and notification source/tests and made no edits.

## Changed Files

None.

## Required Reading Evidence

Task classification: Kappa/CQRS fact, identity, projection, and side-effect audit.

Read `AGENTS.md`, `docs/agent-playbook/task-reading-matrix.md`, the canonical root architecture/reliability documents, the read-model checklist, and the Asset Market, Token Intel, and Notifications architecture maps. Evidence and Ingestion currently have no domain architecture map; source and tests were traced directly.

## Verification Evidence

```text
$ uv run pytest -q tests/architecture/test_kiss_runtime_invariants.py
............                                                             [100%]
12 passed in 2.31s
exit code: 0
```

## Remaining Risks

- The deferred transaction/crash-window findings need separate specs with failure injection and real PostgreSQL coverage.
- No material fact, retry ledger, terminal evidence, or safety-held raw payload should be removed under this feature.
