# Spec — Evidence-first Macro Intel And Product-AI Hard Cut

**Status**: Review
**Superseded by**: N/A
**Date**: 2026-07-23
**Owner**: Codex `/root`
**Approved by**: delegated goal and GitHub Issue #4
**Approved at**: 2026-07-23
**Related**: `https://github.com/AnalyThothAI/parallax/issues/4`, `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/FRONTEND.md`, `docs/RELIABILITY.md`, `docs/WORKERS.md`, `docs/WORKER_FLOW.md`, `docs/AGENT_EXECUTION.md`

## Background

The current macro writer already has the correct durable recovery shape: it claims PostgreSQL dirty targets, refreshes compact observation-series rows, builds one current snapshot, and acknowledges the claimed work after projection (`src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py:50`, `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py:115`, `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py:154`, `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py:158`). The repository prevents unchanged snapshot writes with a payload hash (`src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1703`). Its persisted row is a wide legacy contract containing global regime, score, scenario, and generic module JSON (`src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1680`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1682`). A separate repository method extracts an arbitrary module by JSON key (`src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1755`).

The public macro surface began with one legacy snapshot route and separately declared an asset-correlation route (`src/parallax/app/surfaces/api/routes_macro.py:44`, `src/parallax/app/surfaces/api/routes_macro.py:58`). The pre-cut frontend mirrored the generic model: the route type started a sixteen-member module union, route descriptors were flattened from a navigation tree, and the route sent every resolved module through one renderer. Those deleted inputs remain auditable at the fixed pre-change commit: [routes](https://github.com/AnalyThothAI/parallax/blob/11a7fab52d9febc00259290ddab46b1f0e7fa070/web/src/features/macro/model/macroRoutes.ts#L9), [registry](https://github.com/AnalyThothAI/parallax/blob/11a7fab52d9febc00259290ddab46b1f0e7fa070/web/src/features/macro/model/macroPageRegistry.ts#L15), and [renderer](https://github.com/AnalyThothAI/parallax/blob/11a7fab52d9febc00259290ddab46b1f0e7fa070/web/src/features/macro/MacroWorkbenchRoute.tsx#L69).

News story brief is a real production LLM lane. It is declared as a worker (`src/parallax/app/runtime/worker_manifest.py:93`) and current read-model writer (`src/parallax/app/runtime/worker_manifest.py:96`). Bootstrap constructs model execution when News agent execution is enabled (`src/parallax/app/runtime/bootstrap.py:97`). The lane owns a run table (`src/parallax/platform/db/alembic/versions/20260618_0181_news_story_agent_hard_cut.py:16`) and a current brief table (`src/parallax/platform/db/alembic/versions/20260618_0181_news_story_agent_hard_cut.py:56`). Token and Search also expose deterministic AI-labelled surfaces and dead model-derived storage even though they do not execute a model. These derived surfaces are not material facts.

## Problem

The product cannot reliably answer what macro shock is dominant, which evidence confirms or contradicts it, or what would invalidate it. Generic cross-frequency transformations, a global regime/score/scenario, loose module dictionaries, mixed units, and duplicated route logic create contradictory conclusions and silent backend/frontend drift. Meanwhile, real and pseudo AI product chains add database, worker, notification, API, and UI state without a trustworthy evidence contract. Disabling or hiding those paths would retain the same complexity; the supported product needs one hard-cut contract.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| Is this an incremental redesign? | No. Replace the current macro semantic layer and delete old routes, fields, builders, renderers, aliases, and compatibility code. | delegated goal | 2026-07-23 |
| What remains authoritative? | PostgreSQL Macro, News, Token, event, entity, market, and dedupe facts; macro sync audit/control rows; compact series; stable single-writer current projections. | delegated goal | 2026-07-23 |
| What product AI is deleted? | News story brief end to end, Macro scenario/regime/trade narrative, SearchAgentBrief, Token narrative admission, semantic catalyst, `llm_*` fields, and all consumers. | delegated goal | 2026-07-23 |
| Is AI replaced by deterministic prose? | No. News/Search/Token return source facts only; macro judgments use explicit evidence rules without pretending to be AI. | delegated goal | 2026-07-23 |
| What LLM code remains? | Only dormant provider-neutral structured-JSON execution primitives, capabilities, hashing/usage/schema helpers, dependencies, and isolated tests. Production bootstrap has no model consumer. | delegated goal | 2026-07-23 |
| Are old migrations rewritten? | No. Add one irreversible forward migration after the current head; backup is the only recovery boundary. | delegated goal | 2026-07-23 |
| Is missing market data proxied? | No. TRACE, ETF premium/discount, dealer inventory, FedWatch, consensus, and surprise remain unavailable, not assessed, and not scored. | delegated goal | 2026-07-23 |
| What is the authoritative horizon? | Overview judgments cover 1–4 weeks. Each evidence concept uses its own frequency-aware change and freshness policy. | delegated goal | 2026-07-23 |
| Is macro real time? | No. It is a completed-snapshot product aligned to the latest completed US regular session. | delegated goal | 2026-07-23 |
| May local evidence degradation fail readiness? | No. Claim readiness and process readiness are separate; critical gaps fail the claim closed, not the HTTP process. | delegated goal | 2026-07-23 |
| Does this goal authorize the full SDD loop? | Yes. The user delegated the complete implementation and asked the agent to continue until completion. | delegated goal | 2026-07-23 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| Six fixed macro pages and seven typed endpoints replace sixteen modules. | Exact route/schema tests; old routes and endpoints return ordinary not-found. |
| One atomic snapshot carries six typed documents. | PostgreSQL projection integration test proves one version/watermark and unchanged zero-write. |
| Claims use one judgment interface and fail closed. | Golden rule matrices cover critical gaps, optional degradation, confirmations, contradictions, and invalidation. |
| Evidence metadata is complete and unit-safe. | Schema/golden/browser assertions cover value, unit, window, timestamps, frequency, source, series, freshness, sample range/count, and derived formula inputs. |
| Domain skeletons match the approved product. | Page-specific contract tests cover Cross-asset, Rates & Inflation, Growth & Labor, Liquidity & Funding, and six-layer Credit. |
| Product AI and pseudo AI are absent. | Runtime/schema/API/frontend negative guard plus positive News/Token fact-path tests. |
| Shared LLM library is dormant. | Import/unit test passes while bootstrap/worker/status composition has no model consumer. |
| Destructive state is really removed. | Non-empty predecessor migration proves exact drops, raw-fact preservation, bounded timeouts, and explicit irreversible downgrade. |
| Frontend is explicit and responsive. | Lint/typecheck/build/component/browser checks at 1920/1366/834/390. |
| Canonical/generated contracts match. | OpenAPI, generated frontend types, DB schema, CLI help, docs, SDD index, and full gate are clean. |

## First principles

- Material PostgreSQL facts are the only business truth; current page documents are rebuildable read models. The current worker already claims durable targets and acknowledges after projection (`src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py:47-179`).
- A current read model has one writer, stable product identity, atomic replacement, and zero serving writes when content is unchanged. The current repository already implements payload-hash guarded replacement (`src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1674-1727`).
- The deep module interface is the test surface: one macro snapshot builder accepts persisted observations and returns six page documents. Page-specific complexity remains in its implementation; public callers never learn a generic module catalog.
- Unsupported evidence is explicit absence, never zero, proxy, fallback prose, a global score, or readiness failure.

## Goals

- G1. Replace the macro product with exactly six fixed pages and seven strict public endpoints.
- G2. Produce all six page documents from one atomic, versioned, stable-key snapshot with unchanged zero-write behavior.
- G3. Implement a shared judgment contract and versioned domain rules without global score, confidence percentage, trade instruction, scenario probability, or generic percentile engine.
- G4. Organize existing facts into the approved five domain skeletons with complete evidence/freshness/sample metadata.
- G5. Delete every current real and pseudo AI product producer, runtime, durable derived state, public contract, notification dependency, and UI consumer while retaining raw facts.
- G6. Leave shared LLM execution code dormant and provider-neutral with no production instantiation or business status.
- G7. Replace the macro frontend with six explicit pages, one flat navigation, feature-owned CSS, and readable 1920/1366/834/390 layouts.
- G8. Prove the hard cut on a non-empty predecessor database, real projection replay, generated contracts, Docker runtime, browser flows, and the full repository gate with zero skips.

## Non-goals

- N1. No new provider, TRACE, ETF premium/discount, dealer inventory, FedWatch, consensus, forecast, or surprise data.
- N2. No ALFRED, historical vintages, point-in-time reconstruction, revision surprise, or backtesting.
- N3. No trade advice, sizing, target price, execution, or personalized portfolio recommendation.
- N4. No replacement LLM/agent feature and no deterministic fake brief for News, Search, or Token.
- N5. No customizable dashboard, saved view, arbitrary formula, arbitrary date range, or new UI library.
- N6. No macro WebSocket or intraday judgment; real-time infrastructure for unrelated domains remains.
- N7. No rewrite of landed Alembic history and no archive/dual-read/compatibility schema for deleted derived state.

## Target architecture

```text
existing macro providers
  -> macro sync audit/control
  -> macro_observations facts
  -> macro dirty targets
  -> compact observation series
  -> bounded clock recheck when freshness date or completed-session cutoff advances
  -> one deep evidence-snapshot module
  -> one stable macro snapshot row containing six typed page documents
  -> six page endpoints + one series endpoint
  -> six explicit React pages

existing News / Token / event facts
  -> fact-only public projections and views

dormant provider-neutral LLM library
  -> no runtime consumer, worker, queue, table, status, or UI
```

## Conceptual data flow

```text
provider input -> persisted facts -> compact series -> atomic evidence snapshot -> typed HTTP -> explicit pages
                                   \-> independent typed series HTTP -----/
```

The changed arrow is compact series to evidence snapshot: the generic score/regime/module chain is replaced by frequency-aware concept metadata and domain rules. News and Token fact projections continue without the deleted AI-derived branch.

## Core models

- **Macro snapshot identity**: exactly one `snapshot_key = current` row; projection version and lifecycle timestamps are payload metadata, never identity.
- **Page document**: `conclusion`, `horizon`, `drivers`, `confirmations`, `contradictions`, `upgrade_invalidation`, `evidence_refs`, `freshness`, shared snapshot metadata, and page-specific evidence sections.
- **Evidence item**: value, unit, change, change window, observed time, frequency, source, series key, freshness status, sample start/end/count, criticality, and optional derivation formula/inputs/references.
- **Dominant shock**: candidate, status, primary trigger, cross-domain confirmations, critical contradictions, affected exposures, rule version, and hit evidence. Candidate is absent when rules cannot establish one.
- **Credit state**: stage and direction kept separate; stage is one of contained, tail_stress, broadening, systemic_tightening, repairing, insufficient_evidence.
- **Concept manifest entry**: page, evidence role, unit, frequency, freshness policy, legal change window, criticality, and claim effect.
- **Unavailable evidence**: named capability plus `not_assessed` and reason; it carries no numeric value and never enters a score.

## Interface contracts

- UI pages: `/macro`, `/macro/cross-asset`, `/macro/rates-inflation`, `/macro/growth-labor`, `/macro/liquidity-funding`, `/macro/credit`.
- HTTP read interfaces: `/api/macro/overview`, `/api/macro/cross-asset`, `/api/macro/rates-inflation`, `/api/macro/growth-labor`, `/api/macro/liquidity-funding`, `/api/macro/credit`, `/api/macro/series`.
- Each page interface is independently typed, forbids undocumented fields, and reads the same persisted projection version/fact watermark/market cutoff/computed time.
- Critical missing or stale evidence returns a valid page document whose conclusion status is `insufficient_evidence`; optional gaps return `degraded` with explicit impact.
- Old `/api/macro`, generic module, correlation, and old page interfaces do not redirect or return placeholders.
- News returns source facts only; Token/Search return surviving fact/rank fields only. Removed AI fields are absent rather than nullable.
- Macro read interfaces never call a provider, worker, repair command, or WebSocket path.

## Acceptance criteria

- AC1. WHEN macro public routes are enumerated THEN the system SHALL expose exactly six fixed UI pages and seven typed HTTP reads, and old macro routes/endpoints SHALL return ordinary not-found.
- AC2. WHEN persisted macro facts are projected THEN the system SHALL atomically publish six page documents with one projection version, fact watermark, market cutoff, computed time, and stable identity.
- AC3. WHEN unchanged facts are projected twice THEN the system SHALL write zero serving rows on the second run and SHALL preserve atomic dirty-target acknowledgement.
- AC4. WHEN a page conclusion is returned THEN the system SHALL include horizon, drivers, confirmations, contradictions, upgrade/invalidation, evidence references, freshness, rule version, and actual rule hits without a global score or percentage confidence.
- AC5. WHEN critical evidence is missing, stale, or lacks required metadata THEN the affected claim SHALL be `insufficient_evidence`; WHEN only optional evidence is unavailable THEN the claim SHALL be `degraded` without making the service unready.
- AC6. WHEN Cross-asset evidence is read THEN the system SHALL use cutoff-aligned returns, actual common sample ranges/counts, 20/60-session return correlations, confirmations, divergences, and explicit gaps without mixed raw-point comparisons.
- AC7. WHEN Rates & Inflation evidence is read THEN the system SHALL separate nominal curve/slopes, real yields, breakevens, true term premium, policy/funding corridor, release-aware inflation, and curve-shape classification with correct units and tenor axes.
- AC8. WHEN Growth & Labor or Liquidity & Funding evidence is read THEN the system SHALL keep the approved sublayers and leading/lagging or secured/unsecured distinctions without a combined score or net-liquidity causal label.
- AC9. WHEN Credit evidence is read THEN the system SHALL expose aggregate spreads, rating tail, effective yields, credit supply, realized damage, and financial-conditions/liquidity layers plus Treasury-yield × spread quadrant and the approved stage/direction state.
- AC10. WHEN unavailable TRACE, ETF premium/discount, dealer inventory, FedWatch, or similar evidence is represented THEN the system SHALL mark it not assessed and not scored without placeholder, proxy, zero value, or readiness impact.
- AC11. WHEN current runtime, database head, public contracts, generated types, and frontend are inspected THEN News story brief, Macro scenario/regime/trade narrative, SearchAgentBrief, narrative admission, semantic catalyst, `llm_*` derived fields, and `news_high_signal` SHALL be absent while raw facts and watched-account notification SHALL remain functional.
- AC12. WHEN production bootstrap and worker/status composition start THEN the system SHALL instantiate no LLM business consumer; WHEN the dormant provider-neutral library is imported and unit tested THEN it SHALL remain usable independently.
- AC13. WHEN a non-empty predecessor database upgrades to the new head THEN the system SHALL drop the exact retired AI-derived and legacy macro schema in dependency-safe order, preserve material facts, use bounded timeouts, and reject downgrade with backup-restore guidance.
- AC14. WHEN the React product renders at 1920, 1366, 834, and 390 pixels THEN the system SHALL show flat six-page navigation, complete visible evidence metadata, no whole-page overflow, responsive lists/small multiples, and no generic renderer or AI narrative.
- AC15. WHEN official catalysts are displayed THEN the system SHALL limit them to the next seven days and show official time, timezone, source, and release status without consensus, forecast, surprise, or event score.
- AC16. WHEN completion is claimed THEN the system SHALL have synchronized canonical docs/OpenAPI/generated types/schema/CLI, passed non-empty migration and Docker/browser checks, passed `make check-all` with zero skips, and passed independent spec review.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Destructive migration removes material facts. | Critical | Exact relation/column inventory, child-first drops, no CASCADE/IF EXISTS, non-empty predecessor test, before-count assertions, backup recovery boundary. |
| News fact page still depends implicitly on an agent brief. | High | Write a positive fact-only projection/API test before deleting the lane; inspect every downstream notification and UI consumer. |
| Six page documents drift or recompute independently. | High | One deep snapshot builder, one writer transaction, shared metadata, strict page response models. |
| Frequency-aware rules accidentally reuse observation offsets. | High | Concept manifest plus table-driven daily/weekly/monthly/quarterly tests and actual sample metadata. |
| Token ranking changes unpredictably after semantic catalyst deletion. | High | Remove zero-input family, bump surviving factor/projection version, assert transparent factor decomposition and representative ranking behavior. |
| Dormant LLM code remains wired through config/status. | High | Runtime composition guard and bootstrap test; retain only library imports and isolated tests. |
| Frontend redesign hides critical evidence on small screens. | High | Explicit pages, no hover-only information, component/browser tests at all four required widths. |
| Broad string deletion damages historical evidence or unrelated agent terminology. | Medium | Guard supported runtime/contracts by ownership and behavior; do not rewrite immutable migrations/completed SDD history. |

## Evolution path

New data providers, point-in-time vintages, backtests, or model-assisted research require new specs and new evidence contracts. The fixed six-page interface may add evidence rows inside an existing page, but must not reintroduce generic modules, arbitrary dashboards, global scores, or a product LLM consumer without explicit approval.

## Alternatives considered

- Patch the existing module renderer — rejected because loose backend dictionaries and sixteen generic routes are the source of semantic drift; another adapter would preserve the shallow interface.
- Keep the global regime but improve labels — rejected because independent domain divergence is valid and must not be overwritten.
- Disable News LLM and leave tables/workers — rejected because dormant producers, schema, status, and compatibility remain an operational product contract.
- Rename pseudo AI fields — rejected because SearchAgentBrief, narrative admission, and semantic catalyst do not earn a distinct product interface.
- Add proxies for missing credit liquidity — rejected because absence is materially different from evidence and must stay not assessed.
- Split deployment into old/new compatibility phases — rejected because the user explicitly requires a one-time hard cut and mixed contracts are less safe than an atomic schema/application switch backed by a database backup.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Preserve material facts; hard-delete old product contracts; publish one six-document snapshot; expose evidence metadata and gaps honestly; verify non-empty state and real UI/runtime. |
| Ask first | Mutate operator-owned config, execute the destructive migration against the operator database, or restore from backup. |
| Never | Add compatibility routes/fields/tables, hidden fallbacks, dual writers, request-time providers, placeholder evidence, product AI replacements, trade advice, or fake readiness. |
