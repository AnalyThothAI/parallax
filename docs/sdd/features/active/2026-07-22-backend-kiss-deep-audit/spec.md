# Spec — Backend KISS whole-chain simplification

**Status**: Review
**Date**: 2026-07-22
**Owner**: Codex
**Approved by**: delegated `/goal` for whole-architecture KISS review and implementation
**Approved at**: 2026-07-22
**Related**: `docs/reviews/backend-kiss-hard-cut-implementation-audit-zh-2026-07-22.md`; `docs/sdd/features/active/2026-07-22-backend-kiss-deep-audit/plan.md`

## Background

The current backend already has a static 17-worker inventory with queue and current-row ownership declared in one manifest (`src/parallax/app/runtime/worker_manifest.py:14`). Composition constructs the formal worker set and fails when names are missing, duplicated, or unknown (`src/parallax/app/runtime/worker_factories/__init__.py:37`). The composition root creates PostgreSQL pools, validates startup state, wires providers, constructs workers, and exposes the pooled ingest transaction adapter (`src/parallax/app/runtime/bootstrap.py:77`; `src/parallax/app/runtime/bootstrap.py:130`; `src/parallax/app/runtime/bootstrap.py:226`).

The generic worker kernel keeps interval recovery, sequential execution, status, backoff, and telemetry, but its maintenance iteration and long-running loop currently carry two lifecycle execution paths (`src/parallax/platform/runtime/worker_base.py:74`; `src/parallax/platform/runtime/worker_base.py:109`). Permanent architecture checks protect one-way imports, transaction ownership, stable read-model identities, static worker composition, zero-SQL status, and the single agent policy (`tests/architecture/test_kiss_runtime_invariants.py:81`; `tests/architecture/test_kiss_runtime_invariants.py:120`; `tests/architecture/test_kiss_runtime_invariants.py:160`; `tests/architecture/test_kiss_runtime_invariants.py:198`).

After the preceding hard cut, maintenance concentration remains visible in very large repository/service and test modules, including News canonical persistence (`src/parallax/domains/news_intel/repositories/news_item_repository.py:1`), Macro persistence (`src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1`), Token Radar projection (`src/parallax/domains/token_intel/services/token_radar_projector.py:1`), and repository-query tests (`tests/unit/domains/news_intel/test_news_repository_queries.py:1`). Size alone is not a defect; this feature audits whether those modules encode one cohesive state machine or retain duplicated adapters, transaction emulators, compatibility tripwires, and indirection that no current business contract needs.

## Problem

The previous implementation audit established a simpler target architecture, but it did not prove that every remaining abstraction, directory layer, helper, and test still pays for itself in the current code. Unnecessary factories, duplicate lifecycle paths, legacy-rejection tests, fake-database emulators, or split modules can increase change cost while all architectural gates remain green. The system needs a fresh whole-chain review that distinguishes essential Kappa/CQRS complexity from accidental implementation and test complexity, then removes only the latter.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| Is implementation authorized after the audit? | Yes; implement evidence-backed hard cuts autonomously and do not retain compatibility wrappers. | delegated `/goal` | 2026-07-22 |
| May business truth, current-row identity, recovery, or side-effect ledgers be removed to reduce LOC? | No; simplification must preserve the canonical Kappa/CQRS invariants. | delegated `/goal` plus canonical architecture | 2026-07-22 |
| Are published Alembic revisions runtime compatibility code? | No; preserve migration history and audit it separately from runtime shims. | `docs/RELIABILITY.md` | 2026-07-22 |
| Is the `events.raw_json` / `events.event_json` safety hold in scope? | No; do not remove it without verified provenance coverage. | canonical architecture safety boundary | 2026-07-22 |
| May this feature absorb the active Docker/frontend or News FK-index records? | No; their touch sets and current main changes remain separate. | parent coordination review | 2026-07-22 |
| Must the final `make check-all` complete before merge? | No. After the second attempt reached a missing frontend dependency/toolchain mismatch, the user explicitly stopped the full gate and requested merge to `main`, Docker build/start, real-chain checks, and an exact omission report. | user | 2026-07-22 |
| May a new migration be added after the static hard cut? | Only when the merged real stack exposes a persisted derived-cache contract defect. Revision `0188` is authorized as an irreversible hard cut of the private Token Radar factor cache plus bounded dirty-target requeue; it does not rewrite `0185`-`0187`, backfill malformed JSON, or alter material facts/current-row identity. | real-chain validation under the delegated goal | 2026-07-22 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| Review the whole backend and end-to-end data flow from provider input to public read. | A source-backed audit classifies facts, read models, control/audit state, cache/fan-out state, provider inputs, and generated artefacts for every domain. |
| Identify accidental complexity without deleting necessary correctness. | Every proposed cut names the current consumer, truth owner, failure/recovery boundary, replacement behavior, and verification evidence. |
| Simplify runtime code and tests with no compatibility glue. | The final diff is net-negative in the targeted production/test scope and introduces no alias, fallback, duplicate writer, table, worker, or generic framework. |
| Keep tests focused on behavior and durable architecture. | Removed private/source-shape tripwires are either redundant or replaced by the smallest positive behavior/AST invariant. |
| Preserve concurrent work. | The feature does not edit `.agents/skills/**`, `web/**`, revisions `0185`–`0187`, or absorb either active feature. The existing News-index record receives only reciprocal coordination metadata for the two shared schema-head tests; the new `0188` revision is owned by this feature. |

## First principles

- PostgreSQL material facts are the sole business truth; derived current rows have stable product/window keys, one writer, zero unchanged writes, and bounded fact/queue recovery (`src/parallax/app/runtime/worker_manifest.py:14`; `tests/architecture/test_kiss_runtime_invariants.py:160`).
- Application services and workers own transactions; repositories do not commit, and provider/model/network/file I/O stays outside write transactions (`tests/architecture/test_kiss_runtime_invariants.py:120`).
- KISS means one direct current contract and the fewest responsibilities needed by observed behavior; it does not mean collapsing distinct business truth, failure budgets, refresh cadences, or external side effects.

## Goals

- G1. Produce a current, source-backed whole-chain ownership map and a prioritized keep/cut/defer decision for every confirmed complexity hotspot.
- G2. Remove confirmed redundant production paths and low-value test machinery with a net decrease in targeted production plus test LOC, without introducing a new runtime layer or compatibility surface.
- G3. Preserve all compact root architecture invariants and add only the minimum positive behavior coverage needed for changed boundaries.
- G4. Complete the user-authorized verification boundary with zero hidden skips: targeted/static backend gates plus post-merge Docker build/start and real-chain checks; report the incomplete `make check-all` lanes exactly.

## Non-goals

- N1. No new product feature, ranking formula, provider, table, worker, service process, or public response field.
- N2. No deletion of historical migrations, material facts, unresolved terminal evidence, model/delivery audit ledgers, or the event raw-payload safety hold.
- N3. No frontend refactor, Docker implementation change, or modification to the active News FK-index work; Docker is used only for post-merge validation.
- N4. No blanket refactor of every McCabe warning or large file; cohesive business algorithms may remain complex when splitting would only move branches between helpers.
- N5. No live performance claim without current operator PostgreSQL evidence.

## Target architecture

The target remains one Python service, one PostgreSQL store, one static worker manifest, domain-owned business policies, one composition root, and exact HTTP/WebSocket/CLI reads over facts and stable current models. This feature removes redundant implementation paths inside that architecture. A retained abstraction must own at least one distinct business responsibility, failure/recovery boundary, external dependency, or reusable invariant. Tests retain observable behavior and durable AST/ownership checks; they do not emulate PostgreSQL or freeze retired private shapes when integration or contract coverage already proves the replacement.

## Conceptual data flow

```text
provider raw input
  -> bounded adapter/worker
  -> PostgreSQL material fact
  -> stable dirty target or same-transaction current index
  -> single-writer current read model
  -> exact HTTP / WebSocket / CLI contract
  -> React consumer
```

No new arrow is introduced. Candidate removals are accepted only when this flow still has one explicit owner at every arrow and remains rebuildable from PostgreSQL.

## Core models

- Material fact: durable domain evidence that is never reconstructed from a serving projection.
- Current read model: bounded derived state identified by stable product/window keys and written by exactly one runtime owner.
- Durable target/control row: recoverable work identity, lease, retry, or publication frontier; not business truth.
- External side-effect ledger: durable idempotency and audit state around model or notification I/O.
- Runtime snapshot: in-memory operational state only; never an alternate fact or read model.

## Interface contracts

No new public contract is planned. If an unused private/runtime surface is removed, all callers are cut in the same change and retired input is rejected rather than aliased. Existing public HTTP, WebSocket, and CLI success payloads remain exact. Any public hard cut discovered during audit requires the plan to name its consumers and contract tests before implementation.

## Acceptance criteria

- AC1. WHEN the audit is complete THEN the system SHALL have a source-backed map separating provider inputs, PostgreSQL facts, control/audit state, current read models, cache/fan-out state, and public consumers for all backend domains.
- AC2. WHEN a production path is removed or consolidated THEN the system SHALL retain exactly one current owner, one transaction boundary, and one bounded recovery path, proven by targeted behavior or architecture tests.
- AC3. WHEN tests are simplified THEN the remaining suite SHALL prove observable behavior or durable architecture and SHALL not retain redundant source-string, signature, fake-commit, or retired-private-shape tripwires.
- AC4. WHEN verification runs THEN targeted tests, root architecture checks, Ruff, mypy, SDD/generated-document checks, Docker build/start, and real-chain probes SHALL report exact outcomes, while the interrupted `make check-all` lanes remain explicitly unverified.
- AC5. WHEN the final diff is reviewed THEN it SHALL not modify the explicit conflict set and SHALL show a net LOC reduction in the targeted production/test files.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Deleting a queue/ledger that encodes real recovery or side-effect identity. | Critical | Require a truth/writer/recovery/consumer map and integration evidence before any such cut. |
| Treating versioned domain policy as compatibility code. | High | Classify policy versions and identity aliases separately from runtime fallback/shims. |
| Replacing a large cohesive algorithm with many tiny indirection helpers. | Medium | Use net cognitive-path reduction, not function size alone, as the decision rule. |
| Deleting fast unit coverage while PostgreSQL integration is unavailable. | High | Remove fake SQL tests only where equivalent integration/contract behavior is fresh and executable. |
| Colliding with active work or user deletions. | High | Keep the conflict set explicit and review `git diff main...HEAD` before every implementation batch. |

## Evolution path

Physical PostgreSQL governance remains a separate evidence-driven phase: provenance coverage for event payload cleanup, live index usage, relation size/dead tuples, and real query plans. Future product domains should reuse the same fact/current/target/side-effect classification and must justify any new worker, table, or framework with a distinct present lifecycle.

## Alternatives considered

- A blanket module-size or cyclomatic-complexity rewrite was rejected because it can increase indirection without changing the number of business decisions.
- A compatibility-preserving cleanup was rejected because dual paths prolong the maintenance burden this goal is intended to remove.
- A documentation-only audit was rejected because the delegated goal explicitly includes evidence-backed code and test simplification.
- A microservice split was rejected because it adds deployment, consistency, and observability control planes without a current independent scaling or ownership boundary.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Trace current source, preserve truth/recovery/side-effect invariants, and prefer deletion/consolidation over wrappers. |
| Ask first | Any change requiring a new public product contract, new durable entity, or access to secrets/external coordination. |
| Never | Edit user-owned unrelated changes, expose operator secrets, weaken gates, or claim live/physical evidence from unit tests. |
