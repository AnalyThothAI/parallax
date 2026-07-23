# Spec — Docs and Ops KISS Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Date**: 2026-07-23
**Owner**: Codex `/root`
**Approved by**: user
**Approved at**: 2026-07-23
**Related**: `README.md`, `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`

## Background

The current repository mixes canonical documentation with obsolete audits,
mockups, prototypes, screenshots, temporary HTML, and subagent receipts. The
`docs/generated/` README says the directory is reproducible, while most of its
118 files are not produced by `make docs-generated`
([pre-cut generated tree](https://github.com/AnalyThothAI/parallax/tree/416f8be8bc113dd53ef266a7be1bc80ccd511762/docs/generated)).

The operator interface is also duplicated. The browser owns a large `/ops`
feature and two authenticated diagnostics reads, while `/api/status`,
health/readiness, and the JSON CLI already expose the durable operational
interfaces
([pre-cut Ops route](https://github.com/AnalyThothAI/parallax/blob/416f8be8bc113dd53ef266a7be1bc80ccd511762/src/parallax/app/surfaces/api/routes_ops.py),
[pre-cut README](https://github.com/AnalyThothAI/parallax/blob/416f8be8bc113dd53ef266a7be1bc80ccd511762/README.md)).

## Problem

Readers must decide which of many overlapping files is current. Agents load
navigation documents that point to more navigation documents. Operators have a
browser diagnostics product that duplicates status data and manually mirrors a
large backend payload. This increases drift, contract surface, test cost, and
maintenance without adding material facts or recovery capability.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| Are completed SDD records deleted? | No. They remain the implementation-history boundary. | user | 2026-07-23 |
| Are stale reviews, mockups, prototypes, screenshots, temporary HTML, and generated subagent receipts retained? | No. Delete them rather than archive them in another repository folder. | user | 2026-07-23 |
| Is the operator CLI removed? | No. Keep direct JSON CLI inspection, repair, sync, and rebuild commands. | user | 2026-07-23 |
| Is the browser Ops product retained? | No. Remove `/ops`, its feature bundle, and the dedicated `/api/ops/*` reads without redirect or alias. | user | 2026-07-23 |
| What remains for health and status? | `/healthz`, `/readyz`, authenticated `/api/status`, and direct CLI commands. | user | 2026-07-23 |
| Is the agent packet/dispatch/report harness retained? | No. Delete it; SDD tasks and native agent collaboration already own the handoff. | user | 2026-07-23 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| Current docs have explicit ownership and no obsolete artifact buckets. | Docs surface contract and residual reference scan pass. |
| README is a concise entry point rather than a duplicate architecture manual. | README links to each canonical owner and contains only setup/navigation essentials. |
| Browser/API Ops duplication is absent. | Retired endpoints return 404; frontend route/navigation/feature files are absent. |
| Direct operational capability remains. | Status/readiness contracts and CLI Ops tests pass. |
| SDD workflow has no local subagent factory wrapper. | Validator tests pass without packet/dispatch/report scripts; work index contains active work only. |

## First principles

- Canonical docs explain current contracts; completed SDDs explain history.
- Generated means reproducible from a checked-in generator.
- One operational fact should have one public owner.
- Native collaboration does not need a second text-file dispatch protocol.
- Deletion is preferred to aliases, redirects, archives, or tombstone folders.

## Goals

- G1. Reduce the current documentation map to a small set of authoritative
  product, development, and operations documents.
- G2. Delete obsolete visual/review/generated artifacts and stale internal
  research notes.
- G3. Remove the browser Ops feature and dedicated Ops HTTP reads while
  retaining status/readiness and direct CLI operations.
- G4. Delete the local subagent context/dispatch/report harness and simplify the
  SDD index to active coordination only.
- G5. Close already-finished active SDDs and regenerate current contracts.

## Non-goals

- N1. Do not change material facts, read-model ownership, workers, migrations,
  providers, or domain product behavior.
- N2. Do not remove CLI repair/sync/rebuild commands or queue health queries.
- N3. Do not delete completed SDD history or external provider protocol notes
  that still describe current adapters.
- N4. Do not add redirects, compatibility routes, archive folders, or a new
  documentation generator framework.

## Target architecture

The documentation interface is:

```text
README
  -> architecture / contracts / setup / frontend
  -> development / operations / security
  -> domain ARCHITECTURE files
  -> active SDD work or completed SDD history
```

The operational interface is:

```text
healthz / readyz
authenticated api/status
direct JSON CLI commands
```

There is no browser Ops route, dedicated Ops HTTP payload, or manual frontend
mirror of operational diagnostics.

## Interface contracts

- `README.md` is the short entry point.
- `docs/generated/` contains only reproducible source-derived artifacts plus
  its README.
- `/ops`, `/api/ops/diagnostics`, and `/api/ops/queues/{queue_name}` are
  ordinary not-found.
- `/api/status`, `/healthz`, `/readyz`, and `parallax ops ...` retain their
  current roles.
- SDD verification still requires complete tasks and successful command
  evidence for every acceptance criterion.

## Acceptance criteria

- AC1. WHEN the documentation tree is inspected THEN the system SHALL contain no legacy review, mockup, prototype, visual-verification, temporary-HTML, or generated subagent-receipt bucket, and every remaining generated artifact SHALL have a checked-in generator.
- AC2. WHEN a reader opens README THEN the system SHALL provide a concise product description, quick start, direct verification command, and links to canonical owners without duplicating their detailed contracts.
- AC3. WHEN browser and HTTP routes are enumerated THEN the system SHALL expose no `/ops` product or `/api/ops/*` read while `/api/status`, `/healthz`, `/readyz`, and direct CLI Ops commands remain available.
- AC4. WHEN the SDD workflow is inspected THEN the system SHALL contain no context-packet, dispatch, subagent-report validator, or generated handoff/report interface, and the generated work index SHALL describe active coordination only.
- AC5. WHEN completion is claimed THEN the system SHALL have archived all finished active SDDs, regenerated OpenAPI/frontend/generated docs, passed focused backend/frontend/documentation checks, and recorded omitted lanes honestly.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| A useful current contract is deleted as “old.” | High | Trace every candidate's live references and replacement owner before deletion. |
| Operators lose repair capability with the browser Ops deletion. | High | Preserve direct CLI operations and queue-health modules; test status and CLI paths. |
| Generated contracts drift after route removal. | High | Regenerate OpenAPI and frontend types, then run contract and frontend checks. |
| Historical evidence becomes ambiguous. | Medium | Keep completed SDDs; delete only secondary receipts and explicitly noncanonical artifacts. |

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Prefer one current owner, direct commands, and ordinary 404 for retired routes. |
| Ask first | Remove a material fact, worker, CLI repair capability, or completed SDD. |
| Never | Add compatibility aliases, archive directories, or a replacement browser Ops payload. |
