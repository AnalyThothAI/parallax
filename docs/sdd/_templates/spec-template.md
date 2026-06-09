# Spec — `<feature title>`

**Status**: Draft | Approved | In Progress | Review | Blocked | Verified | Superseded
**Date**: YYYY-MM-DD
**Owner**: <user / agent name>
**Approved by**: <user / delegated goal / pending>
**Approved at**: <YYYY-MM-DD / pending>
**Related**: <link to plan, predecessor specs, ADRs>

## Background

State what exists today. **Cite real files** — `src/parallax/<area>/<file>.py:<line>` — for every claim about current behaviour. A spec whose background is uncited is ungrounded; rewrite before continuing.

## Problem

One paragraph describing the user-visible or system-visible problem. Avoid solution language.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
|          |        |             |             |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
|             |              |

## First principles

The two or three invariants this design must respect (e.g. "snapshot gate must precede entity extraction", "score versions are immutable contracts"). Cite the code that already enforces them.

## Goals

Each goal is a falsifiable claim with a metric or pass/fail criterion. Bad: "improve relevance". Good: "p95 token-flow query under 200 ms with 50k events in window".

- G1.
- G2.
- G3.

## Non-goals

What this work explicitly does not do. Required — protects scope.

- N1.
- N2.

## Target architecture

Describe the system after this change. Components, data ownership, lifecycle. No file:line edits, no function signatures, no SQL DDL — those live in the plan.

## Conceptual data flow

```
collector → ingest → enrichment → retrieval → api → web
```

Annotate the arrows that change. If a new arrow appears, justify why an existing service cannot host it.

## Core models

Semantic model definitions only — names, fields, invariants. No CREATE TABLE.

## Interface contracts

Public HTTP / WebSocket / CLI surfaces this change touches. Describe semantics: input shape, output shape, error modes, idempotency. No JSON schemas — those live in the plan.

## Acceptance criteria

Phrased as `WHEN <condition> THEN system SHALL <observable behaviour>` so they can be checked at review and re-checked at verification time.

- AC1. WHEN ... THEN system SHALL ...
- AC2. WHEN ... THEN system SHALL ...
- AC3. WHEN ... THEN system SHALL ...

## Risks

Specific failure modes and the test or design choice that addresses each.

| Risk | Severity | Mitigation |
|------|----------|------------|
|      |          |            |

## Evolution path

What is the next plausible expansion of this design, and what should we be careful not to foreclose?

## Alternatives considered

For each alternative: a one-paragraph description and the specific reason it was rejected. Required when a new service, table, or background worker is being introduced.

- Alternative A — rejected because ...
- Alternative B — rejected because ...

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Things this feature unconditionally does. |
| Ask first | Ambiguous behaviours that require user confirmation. |
| Never | Things this feature unconditionally does not do. |
