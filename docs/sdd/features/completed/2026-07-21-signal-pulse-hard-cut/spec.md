# Spec — Signal Pulse Hard Cut And Architecture Simplification

**Status**: Superseded
**Superseded by**: `docs/reviews/backend-kiss-architecture-audit-zh-2026-07-21.md`
**Date**: 2026-07-21
**Owner**: Codex `/root`
**Approved by**: delegated goal
**Approved at**: 2026-07-21
**Related**: `docs/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/RELIABILITY.md`, `docs/WORKERS.md`, `docs/WORKER_FLOW.md`, `docs/references/POSTGRES_PERFORMANCE.md`

## Background

Signal Pulse began as a derived decision surface on top of Token Radar. Before this hard cut it spanned a dedicated domain, an agent worker and lane, control queues, audit ledgers, public HTTP and CLI contracts, notification evaluation, Token Case overlays, and a Live-page frontend panel. The operator-owned runtime disabled its consumers, but upstream Token Radar still enqueued dirty targets and the frontend still polled its endpoints (`docs/reviews/signal-pulse-hard-cut-architecture-audit-zh-2026-07-21.md:5`, `docs/reviews/signal-pulse-hard-cut-architecture-audit-zh-2026-07-21.md:25`, `docs/reviews/signal-pulse-hard-cut-architecture-audit-zh-2026-07-21.md:28`).

The 2026-07-21 inventory found 51 dedicated Python files with 13,298 lines, 42 Pulse-named test files with 19,206 lines, and eight dedicated frontend files with 1,055 lines before counting shared wiring, generated contracts, docs, fixtures, and cross-cut tests (`docs/reviews/signal-pulse-hard-cut-architecture-audit-zh-2026-07-21.md:22`, `docs/reviews/signal-pulse-hard-cut-architecture-audit-zh-2026-07-21.md:23`, `docs/reviews/signal-pulse-hard-cut-architecture-audit-zh-2026-07-21.md:24`). The live local PostgreSQL instance at revision `0182` contained 14 Pulse relations, 52 Pulse indexes, and 35,561,472 bytes of Pulse relations (`docs/reviews/signal-pulse-hard-cut-architecture-audit-zh-2026-07-21.md:25`). Its disabled consumer left 21,172 due dirty targets (`docs/reviews/signal-pulse-hard-cut-architecture-audit-zh-2026-07-21.md:26`); in the observed stats window, producer upserts executed 570 times, touched 2,703 rows, and generated 6,193,803 WAL bytes (`docs/reviews/signal-pulse-hard-cut-architecture-audit-zh-2026-07-21.md:27`).

## Problem

Signal Pulse no longer provides active business value, yet every producer, contract, schema object, poller, configuration branch, compatibility path, and test remains a maintenance and performance obligation. Disabling the consumer does not stop producer writes, public requests, schema churn, or cognitive load. Keeping the feature as dormant code violates KISS and leaves a second decision pipeline beside the canonical material-fact to derived-read-model flow.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| Is this a deprecation or compatibility exercise? | No. Delete Signal Pulse end to end; do not keep aliases, feature flags, disabled worker blocks, placeholder responses, redirect routes, or schema compatibility. | delegated goal | 2026-07-21 |
| Are material Kappa facts deleted? | No. Preserve `events`, `token_intents`, `token_intent_resolutions`, identity facts, `market_ticks`, `enriched_events`, Token Radar current rows, and News/Macro facts. | delegated goal | 2026-07-21 |
| Are Pulse tables business truth? | No. They are rebuildable read models, control-plane queues/budgets, or feature-specific audit ledgers and may be dropped. | delegated goal | 2026-07-21 |
| Is shared agent infrastructure removed? | Only if unused after the cut. The shared execution gateway and News lanes remain because News still consumes them; the `pulse.decision` lane and Pulse client/provider are deleted. | delegated goal | 2026-07-21 |
| Are historical migrations rewritten? | No. Add one irreversible forward migration after current head; historical migrations remain immutable chain evidence. | delegated goal | 2026-07-21 |
| May the frontend keep a hidden Lab panel or compatibility selection state? | No. Remove the panel, polling, global Pulse selection, fixtures, generated types, and route/task compatibility. Simplify remaining Live selection to its real route-local needs. | delegated goal | 2026-07-21 |
| Does this deploy to the operator-owned live database/config automatically? | No. Code, migration, contracts, and rollout instructions are delivered; destructive migration and operator config cleanup require an explicit deployment action. | delegated goal | 2026-07-21 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| Material facts remain intact. | Migration and architecture tests enumerate Pulse-only drops and assert canonical fact/read-model tables remain. |
| Producer work stops at the source. | Token Radar no longer writes Pulse dirty targets or emits any Pulse-specific wake/fan-out. |
| There is no dormant runtime. | Worker manifest, factory, settings, repository session, queue health, diagnostics, provider wiring, and agent lane contain no Pulse runtime contract. |
| There is no public compatibility surface. | Pulse HTTP/CLI/schema/notification/Token Case overlay contracts are absent; stale URLs return normal not-found behavior. |
| There is no frontend polling or hidden UI. | Live renders only supported panels and no Signal Lab query key, request, overlay, task, fixture, or selection union remains. |
| Database state is actually retired. | Head migration drops all current Pulse tables and purges feature-specific rows from shared notification/terminal ledgers before dropping source tables. |
| Shared business capabilities survive. | Token Radar, Token Case without overlay, News agent briefs, generic notifications, and the shared agent gateway pass targeted tests. |
| KISS improvements are evidence-backed. | The architecture audit records keep/remove decisions, before/after inventory, current database cost, Kappa/CQRS ownership, and deferred non-Pulse risks. |
| No compatibility glue is added. | Static guard rejects Pulse runtime/public/frontend markers outside immutable history and the hard-cut record. |

## First principles

- A disabled consumer is not a deletion boundary when producers still create durable work.
- Material facts are retained; feature-specific projections, queues, and audit ledgers exist only while a product consumer exists.
- Kappa/CQRS needs one fact stream and rebuildable read models, not a second dormant decision truth.
- Public contracts should represent supported behavior. A fake empty response, disabled configuration block, or redirect is still code and still a contract.
- Shared infrastructure is kept only for verified remaining consumers; names and settings of the removed lane are not retained.
- A hard cut is forward-only. Recovery uses a pre-migration backup and code rollback, not schema resurrection shims.

## Goals

- G1. Delete the entire Signal Pulse domain and all current runtime, provider, public, notification, Token Radar, and frontend consumers/producers.
- G2. Drop every current Pulse database object and purge Pulse-owned rows in shared ledgers through one explicit irreversible migration.
- G3. Preserve canonical Kappa facts and the remaining single-writer CQRS read models without adding fallback paths.
- G4. Simplify the Live frontend state and request graph after the Lab panel disappears.
- G5. Produce a Chinese architecture audit with measured complexity/performance impact and explicit keep/remove/defer decisions.
- G6. Leave generated OpenAPI, database schema, CLI help, worker inventory, docs, examples, and tests aligned with the supported product.

## Non-goals

- N1. This does not redesign Token Radar ranking, News briefs, Macro models, or material fact schemas.
- N2. This does not delete generic market/news uses of the word “pulse” that are unrelated to Signal Pulse.
- N3. This does not deploy migrations or rewrite `~/.parallax/` operator-owned files automatically.
- N4. This does not rewrite or delete historical Alembic revisions, completed SDD records, or immutable audit history documents.
- N5. This does not retain Pulse data for a future feature; a future product must start with a new approved contract and projection.

## Target architecture

```text
provider inputs
    -> material PostgreSQL facts
    -> single-writer Token Radar / News / Macro read models
    -> supported HTTP, WebSocket, CLI, notification and React consumers

removed completely:
Token Radar -> Pulse dirty targets -> Pulse agent jobs/runs -> Pulse candidates/playbooks
            -> Signal Pulse API/CLI/notifications -> Signal Lab frontend
```

Token Radar remains the supported market-attention read model. News keeps its own agent lanes through the shared `AgentExecutionGateway`. Notifications continue to evaluate supported watchlist and News rules. The Live route owns only its remaining Radar/Tape selection and mobile task state; the application shell no longer carries Pulse selection compatibility.

## Core models

- Material facts retained: social/news/macro/provider evidence, token intents and resolutions, asset identity, market ticks, enriched events.
- Current read models retained: Token Radar current/publication rows, News page rows, Macro series/views, token profiles, notifications.
- Pulse read models removed: candidates and playbook snapshots.
- Pulse control plane removed: dirty targets, agent jobs, candidate/target budgets, edge state, runtime/eval control rows.
- Pulse audit ledgers removed: runs, run steps, evidence packets, eval cases/results/runtime versions.

## Interface contracts

- No `/api/signal-lab/pulse` list or detail endpoint.
- No Pulse replay CLI command or Pulse queue-specific operator action.
- No `pulse_overlay` in Token Case or Token Radar-facing schemas.
- No `signal_pulse_candidate` notification rule.
- No `pulse_candidate` worker, status entry, queue health adapter, or `pulse.decision` lane.
- No Signal Lab panel or Pulse query from the Live page.
- Existing operator configs containing removed keys fail as unknown configuration until the operator removes them; there is no ignored-key compatibility.

## Acceptance criteria

- AC1. WHEN source and test architecture guards scan current runtime code THEN the `pulse_lab` domain, Pulse decision client/provider, Pulse worker/factory, and Pulse-specific repository/session wiring SHALL be absent.
- AC2. WHEN worker and configuration contracts are generated THEN `pulse_candidate`, `pulse.decision`, Pulse queue health, Pulse diagnostics, and Pulse notification-rule settings SHALL be absent while News agent lanes and supported workers SHALL remain.
- AC3. WHEN Token Radar publishes or catches up from dirty targets THEN it SHALL NOT enqueue Pulse work, call a Pulse repository, or emit a Pulse-specific output while its own stable current-row and Narrative wake contracts SHALL remain valid.
- AC4. WHEN public contracts are inspected or exercised THEN Signal Pulse routes, CLI commands, schemas, `pulse_overlay`, notification candidates, and compatibility responses SHALL be absent and stale Pulse URLs SHALL return normal not-found behavior.
- AC5. WHEN the React application renders `/` on desktop and mobile THEN it SHALL show only supported Live panels and SHALL issue no Signal Pulse request, retain no Signal Lab query key/fixture/generated type, and carry no global Pulse selection state.
- AC6. WHEN the Alembic chain upgrades from `20260713_0183` to the new head THEN every current `pulse_%` table SHALL be absent, Pulse-owned shared notification and terminal-ledger rows SHALL be purged, and canonical material-fact and supported read-model tables SHALL remain.
- AC7. WHEN schema downgrade is attempted after the destructive cut THEN it SHALL fail explicitly with backup-restore guidance rather than recreate empty compatibility tables.
- AC8. WHEN generated artifacts and canonical docs are checked THEN OpenAPI, frontend types, database schema, CLI help, worker inventory, architecture, contracts, frontend, reliability, worker, and agent-execution docs SHALL describe only supported behavior.
- AC9. WHEN the architecture audit is reviewed THEN it SHALL quantify before/after code, runtime request, table/index/WAL cost, classify Kappa facts versus derived/control/audit state, and record each high-confidence KISS removal or explicit deferral.
- AC10. WHEN targeted, architecture, frontend, migration, and full repository gates run THEN they SHALL pass without a Pulse compatibility allowlist except immutable historical migrations/SDDs and this hard-cut evidence record.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Operator config still contains removed keys. | High | Document required pre-deploy deletion; keep strict unknown-key failure rather than silently ignoring stale config. |
| Migration drops audit data that might be wanted later. | High | Declare migration irreversible; require pre-migration backup for recovery; verify only Pulse-owned relations/rows are targeted. |
| Shared News agent execution is accidentally removed. | High | Targeted gateway/provider/settings tests prove News lanes remain. |
| Token Radar fan-out removal damages Narrative catch-up. | High | Preserve and test existing Narrative dirty-target/wake behavior independently. |
| Frontend shell simplification breaks Radar/Tape selection or mobile navigation. | High | Route/component tests plus desktop/mobile browser verification. |
| Historical references make a zero-string scan misleading. | Medium | Hard-delete guard scopes current runtime/public/frontend/config surfaces and explicitly excludes immutable history. |
| Existing active Kappa/CQRS SDD overlaps the same files. | High | This feature owns Signal Pulse deletion from current `main`; conflict sets explicitly coordinate with the older feature and preserve its non-Pulse changes. |

## Evolution path

A future decision-agent product must begin with a new SDD, a verified product consumer, a single-writer read-model identity, a bounded control plane, and measured demand. It must not revive these schemas or names through compatibility code.

## Alternatives considered

- Leave Pulse disabled — rejected because producers, frontend polling, schema objects, config, and maintenance cost remain.
- Keep empty endpoints and UI placeholders — rejected because they preserve public and frontend compatibility complexity with no product value.
- Stop only Token Radar enqueue — rejected because dead code, database objects, public contracts, and client polling would remain.
- Reuse Pulse audit tables for News — rejected because that creates cross-domain ownership and a second truth; News already owns its ledgers.
- Rewrite historical migrations — rejected because landed migrations are immutable operational history.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Delete current Pulse code/contracts/data structures, retain Kappa facts, keep remaining consumers explicit, and verify behavior. |
| Ask first | Deploy the destructive migration or mutate operator-owned live config. |
| Never | Add aliases, disabled placeholders, ignored config keys, dual writers, compatibility tables, or provider reads in request paths. |
