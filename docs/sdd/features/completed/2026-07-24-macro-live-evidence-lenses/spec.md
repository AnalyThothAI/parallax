# Spec — Macro Live Evidence Lenses and DeepAgents Research Separation

**Status**: Verified
**Date**: 2026-07-24
**Owner**: Codex `/root`
**Approved by**: user and GitHub Issue #8
**Approved at**: 2026-07-24
**Related**: https://github.com/AnalyThothAI/parallax/issues/8

## Background

The DeepAgents Macro hard cut correctly removed deterministic judgment,
readiness, direction, risk-lane, and `no_call` systems, but it also removed the
six data views operators used to inspect live material facts. Issue #8 records
the approved product correction: keep the DeepAgents completed-session
research chain and restore six descriptive, source-native data lenses.
https://github.com/AnalyThothAI/parallax/issues/8

The fixed six-category taxonomy is presentation metadata, not an Agent output
schema or evidence allowlist. Live facts and frozen research intentionally use
different clocks and different routes.
https://github.com/AnalyThothAI/parallax/issues/8

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| What returns? | A live dashboard, six category detail routes, transparent charts/tables, and the original 108 concepts as presentation metadata. | user and Issue #8 | 2026-07-24 |
| What remains removed? | Deterministic direction, confidence, risk lanes, stages, quadrants, readiness, sufficiency, `no_call`, page gates, projection workers, and judgment tables. | user and Issue #8 | 2026-07-24 |
| Is the DeepAgent constrained to six sections? | No. Its tools, planning, specialists, dynamic sections, frozen evidence scope, and immutable publication remain unchanged. | user and Issue #8 | 2026-07-24 |
| What is current? | Live pages show the latest persisted fact at each source's native cadence; research remains frozen to its completed-session cutoff. | user and Issue #8 | 2026-07-24 |
| Where do live pages read? | Directly from PostgreSQL `macro_observations` through one parameterized persisted-only API. | user and Issue #8 | 2026-07-24 |
| How is missing data handled? | Row-local missing state with source/timing context; no page-level sufficiency gate. | user and Issue #8 | 2026-07-24 |
| Is implementation authorized? | Yes, including merge to `main`, image rebuild, and runtime verification. | user | 2026-07-24 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| `/macro` is a six-category live dashboard with compact latest-research context. | Frontend route and browser tests. |
| `/macro/research` owns the complete immutable DeepAgent document and history selection. | API and route tests. |
| Six child routes expose curated summaries, history, and complete searchable rows. | API, route, and browser tests. |
| One persisted-only API reads `macro_observations` and never invokes a model/provider or writes. | HTTP contract and spy tests. |
| Original 108 concepts are display metadata while uncatalogued facts remain visible. | Catalog and unclassified-fact tests. |
| Observation time, received time, exact content age, read health, and last successful read remain distinct. | API and frontend currentness tests. |
| Transparent arithmetic exposes formula/window/sample without semantic labels. | Unit and contract tests. |
| DeepAgents topology and immutable publication remain unchanged. | Existing topology/publication tests. |
| No old projection writer, judgment storage, compatibility API, or deterministic semantic fields return. | Architecture and migration tests. |
| Generated contracts, canonical docs, SDD, Docker image, and production runtime agree. | Generators, docs, build, migration, and smoke tests. |

## Product contract

- `/macro` is the live dashboard.
- `/macro/research` is the complete frozen research document.
- `/macro/overview`, `/macro/rates-inflation`, `/macro/growth-labor`,
  `/macro/liquidity-funding`, `/macro/credit`, and `/macro/cross-asset` are
  live detail routes.
- `GET /api/macro/evidence/{view_id}` accepts `dashboard` and the six canonical
  view IDs plus a bounded history window.
- The API returns descriptive material facts, row-local missing states, and
  named transparent calculations only.
- The dashboard includes six compact previews and bounded uncatalogued facts.
- Detail pages contain no Agent prose; they show only the latest research
  session/cutoff link.

## Acceptance criteria

- AC1. WHEN `/macro` loads THEN it SHALL render six live category summaries, a bounded uncatalogued-facts surface, and a compact latest-research card.
- AC2. WHEN a category route loads THEN it SHALL render curated summary metrics, bounded history, and a complete searchable table for that category.
- AC3. WHEN `/macro/research` loads with or without `session_date` THEN it SHALL render the existing persisted immutable DeepAgent publication and historical state without starting work.
- AC4. WHEN the live evidence API reads THEN it SHALL query only persisted `macro_observations`, perform zero model/provider calls and writes, and return an explicit read timestamp.
- AC5. WHEN catalogued and uncatalogued facts coexist THEN the original 108 concepts SHALL retain stable presentation metadata while uncatalogued facts remain discoverable without becoming Agent allowlists.
- AC6. WHEN a fact is current, delayed, revised, late-ingested, date-only, future-dated, or missing THEN the response and UI SHALL preserve observation/source time, received time, row-local availability, and separate HTTP read health without fabricating freshness.
- AC7. WHEN descriptive calculations are returned THEN they SHALL expose formula identity, operands, window, and sample size without direction, confidence, risk, stage, quadrant, readiness, sufficiency, or `no_call` semantics.
- AC8. WHEN the feature is inspected structurally THEN it SHALL contain no restored Macro snapshot/projection writer, dirty-target queue, judgment table, or compatibility endpoint.
- AC9. WHEN DeepAgents regression tests run THEN native planning, filesystem, execute, specialists, dynamic sections, frozen evidence, checkpoints, citation closure, and immutable publication SHALL remain intact.
- AC10. WHEN the frontend is exercised at 1920px, 1366px, 834px, and 390px THEN all eight Macro routes SHALL hard-load without shell overflow and preserve refresh, search, URL window, keyboard, and last-good-data behavior.
- AC11. WHEN public contracts and canonical docs are generated THEN OpenAPI, TypeScript, schema documentation, architecture, contracts, frontend, operations, setup, and SDD records SHALL describe the same split live/frozen product.
- AC12. WHEN the branch is delivered THEN it SHALL be committed, merged into `main`, built into the production Docker image, migrated idempotently, and verified through readiness, authenticated API, browser, worker, and log checks.

## Out of scope

- New providers, browser-to-provider calls, or ordinary News feeds.
- Historical as-of snapshots for live pages.
- A six-section Agent schema or six independent Agent runs.
- Trade instructions, position sizing, entries, exits, targets, or allocation.
- Reintroduction of any retired deterministic judgment system.
