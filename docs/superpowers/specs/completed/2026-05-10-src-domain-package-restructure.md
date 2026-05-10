# Spec — Src Domain Package Restructure

**Status**: Approved
**Date**: 2026-05-10
**Owner**: Qinghuan / Codex
**Related**: `docs/ARCHITECTURE.md`, `docs/DESIGN_DISCIPLINE.md`, `docs/WORKFLOW.md`, `docs/references/walkinglabs-harness-engineering.md`, https://openai.com/index/harness-engineering/, https://walkinglabs.github.io/learn-harness-engineering/zh/resources/openai-advanced/

## Background

The repository already has a good documentation harness: root routers point into governance files, active and completed lane directories exist, generated artefacts live under `docs/generated/`, and external references live under `docs/references/`. The Python source tree is still organised mostly by technical layer, not product domain. `docs/ARCHITECTURE.md:5-20` describes the current flow as `collector/ -> pipeline/ -> storage/ <- retrieval/ -> api/`, with cross-cutting `market/`, `settings.py`, `runtime_paths.py`, `models.py`, and `logging_setup.py` at `docs/ARCHITECTURE.md:22-27`.

The current source confirms that layer structure:

- The collector owns GMGN frame parsing, snapshot gating, watched-handle matching, store-first ingestion, and publish after insert in `src/gmgn_twitter_intel/collector/service.py:48-171`. It imports the ingest result from `pipeline` at `src/gmgn_twitter_intel/collector/service.py:10-13`, so a lower input adapter already depends on downstream pipeline code.
- The ingest service is a large orchestration point. It imports storage repositories and domain functions from several concerns at `src/gmgn_twitter_intel/pipeline/ingest_service.py:9-24`, then handles event insertion, entity extraction, token evidence, token intent resolution, registry writes, price observations, alerting, and enrichment enqueueing in one transaction at `src/gmgn_twitter_intel/pipeline/ingest_service.py:61-148`.
- Repository construction is centralised in a flat storage session at `src/gmgn_twitter_intel/storage/repository_session.py:8-27` and exposes every aggregate from one dataclass at `src/gmgn_twitter_intel/storage/repository_session.py:29-50`. This is useful for app wiring but does not reveal domain ownership.
- Several boundaries are already inverted in practice. Token-radar projection imports scoring from `retrieval` at `src/gmgn_twitter_intel/pipeline/token_radar_projection.py:8-14`, while asset-flow retrieval imports a projection constant from `pipeline` at `src/gmgn_twitter_intel/retrieval/asset_flow_service.py:5-6`. `query_parser` imports normalisation from `pipeline` at `src/gmgn_twitter_intel/retrieval/query_parser.py:5`.
- Some storage modules import pipeline logic directly. `EvidenceRepository` imports entity extraction constants, tweet identity helpers, and text projection helpers from `pipeline` at `src/gmgn_twitter_intel/storage/evidence_repository.py:12-16`, so storage cannot be understood as a pure persistence boundary.
- Harness is functionally present but not domain-isolated. Enrichment materialises harness snapshots inside `EnrichmentWorker` at `src/gmgn_twitter_intel/pipeline/enrichment_worker.py:124-143`. Harness ops query SQL directly through `harness.conn` at `src/gmgn_twitter_intel/pipeline/harness_ops.py:19-65`, `src/gmgn_twitter_intel/pipeline/harness_ops.py:68-145`, `src/gmgn_twitter_intel/pipeline/harness_ops.py:165-210`, and `src/gmgn_twitter_intel/pipeline/harness_ops.py:273-333`. Harness retrieval also queries `harness.conn` directly for score buckets at `src/gmgn_twitter_intel/retrieval/harness_service.py:76-125`.
- API routes are surface code but import read services and repositories from the flat technical packages at `src/gmgn_twitter_intel/api/http.py:11-25`. The harness HTTP endpoints call `HarnessService` directly inside route handlers at `src/gmgn_twitter_intel/api/http.py:350-507`.
- The project has structural tests, but they pin the current technical-layer paths instead of a domain-package architecture. `tests/test_project_structure.py:18-60` asserts the existence of `collector/`, `pipeline/`, `retrieval/`, and `storage/` modules, while `tests/test_harness_structure.py` mechanically protects the docs harness rather than `src` import direction.

The design discipline file already requires audit-before-design and actual file citations for data-flow claims at `docs/DESIGN_DISCIPLINE.md:15-24`. Workflow also requires this spec to be approved before plan work begins at `docs/WORKFLOW.md:5-20`, and any `src` / `tests` implementation to use an isolated worktree at `docs/WORKFLOW.md:22-30`.

## Problem

The codebase has grown enough product domains that technical-layer packages no longer tell an agent where a change belongs. Business concerns such as token-radar scoring, asset-market observation, enrichment, harness settlement, notification delivery, and pulse candidate evaluation are spread across `pipeline/`, `storage/`, `retrieval/`, `market/`, `api/`, and `cli.py`. That makes the current architecture legible only after reading many cross-layer imports, and it leaves important rules such as "repositories own SQL", "retrieval does not reach into pipeline internals", and "domain scoring lives with its domain" as conventions rather than executable structure.

## First principles

1. **Repository-local structure is the operating manual.** The router / governance harness already encodes project knowledge into repo-local files, and the source tree should follow the same pattern. `AGENTS.md:9-27` points agents into the docs harness; `docs/references/walkinglabs-harness-engineering.md` records the "short entry, deep links" and "mechanical structure beats verbal convention" principles.
2. **Domain ownership must be visible from paths.** A new agent should infer that harness settlement belongs to a harness package, token-radar projection belongs to a token-intel package, and OKX clients are integration adapters rather than unrelated market business logic.
3. **Mechanical boundaries outrank prose.** OpenAI's harness article and the walkinglabs SOP both favour strict dependency direction and structural checks over long instructions. This repo already applies that idea to documentation with `tests/test_harness_structure.py`; the source tree needs equivalent structural tests.
4. **Public behaviour is not part of this refactor.** Public config, HTTP, WebSocket, CLI, score-version, and privacy contracts live in `docs/CONTRACTS.md` and must remain stable during the package move.

## Goals

- **G1.** A coding agent can answer "where does this source change belong?" by reading `docs/ARCHITECTURE.md` plus the target domain package root, without scanning flat `pipeline/` or `storage/` directories.
- **G2.** Business logic, repositories, read services, and runtime workers are grouped by domain package, with no business modules remaining in the old flat `collector/`, `pipeline/`, `retrieval/`, `storage/`, or `market/` packages after the final migration.
- **G3.** Import direction is mechanically enforced. Structural tests fail if a domain imports another domain's internal modules, if repository code imports service/runtime code, if retrieval/read models execute raw SQL outside repository/query modules, or if platform modules import product domains.
- **G4.** HTTP, WebSocket, CLI, settings, generated docs, score-version strings, and database schema semantics are preserved. Existing contract tests should pass after import updates, except where they are intentionally rewritten to assert the new paths.
- **G5.** `docs/ARCHITECTURE.md` is updated from a technical-layer map to a domain-package map, and generated or structural tests pin the new map.
- **G6.** The migration is reviewable in domain-sized slices while ending in one coherent architecture; temporary compatibility shims are allowed only as migration scaffolding and are removed or explicitly documented before completion.

## Non-goals

- **N1.** No new PostgreSQL tables, columns, materialised views, migrations, or backfills.
- **N2.** No scoring formula changes, score-version bumps, or ranking behaviour changes.
- **N3.** No new HTTP routes, WebSocket message types, CLI verbs, background workers, or OpenAI / OKX / GMGN API behaviours.
- **N4.** No frontend redesign or `web/` package restructuring.
- **N5.** No attempt to make every file smaller or prettier unless the move requires a split to preserve domain boundaries. Style cleanup that does not protect the package architecture belongs in later work.

## Target architecture

The final `src/gmgn_twitter_intel/` tree is organised around domains and explicit composition roots:

```
src/gmgn_twitter_intel/
  app/
    runtime/
    surfaces/
      api/
      cli/
  domains/
    ingestion/
    evidence/
    asset_market/
    token_intel/
    social_enrichment/
    closed_loop_harness/
    notifications/
    pulse_lab/
    account_quality/
  integrations/
    gmgn/
    okx/
    openai_agents/
  platform/
    config/
    db/
    logging/
    paths/
  __main__.py
  cli.py
```

`__main__.py` and `cli.py` may remain as tiny public entry shims because `pyproject.toml` points the installed command at `gmgn_twitter_intel.cli:main`. API modules remain surface code under `app/surfaces/api/`, with any old import path retained only if it is needed as a temporary compatibility bridge during migration. The business logic moves under `domains/`.

Each domain uses the same conceptual layer sequence:

```
types/config -> repositories/queries -> services/scoring -> runtime/workers -> app surfaces
```

The allowed import rules are:

- `platform` may import standard libraries and third-party infrastructure packages, but never product domains.
- `integrations` adapt external systems and may depend on `platform`; they do not own product decisions.
- `domains/<domain>/types` and `domains/<domain>/config` are importable by that domain and by explicit cross-domain interfaces.
- `domains/<domain>/repositories` and `domains/<domain>/queries` own SQL and persistence shape for that domain.
- `domains/<domain>/services` own deterministic business behaviour and may depend on that domain's repositories plus explicit public interfaces from other domains.
- `domains/<domain>/runtime` owns async loops, workers, polling, and provider orchestration for that domain.
- `app/runtime` is the composition root. It may import every domain runtime and repository to wire the process.
- `app/surfaces/api` and `app/surfaces/cli` translate public inputs into domain calls and public outputs. They do not contain domain scoring, settlement, SQL, token resolution, or notification rules.
- Cross-domain imports go through public domain interface modules, not through another domain's private repository, query, scoring, or worker modules.

### Domain ownership

| Domain package | Owns |
|----------------|------|
| `domains/ingestion` | GMGN public-stream frame handling, snapshot gate, handle filtering, raw public-stream normalisation, collector status. |
| `domains/evidence` | Canonical Twitter event model, event identity, text projection, entity extraction surfaces, evidence and entity persistence. |
| `domains/asset_market` | Asset registry, chain/address identity, price observations, OKX / GMGN market adapters through `integrations`, discovery, market hydration, asset-market sync. |
| `domains/token_intel` | Token evidence, token intents, intent resolution, token target views, token-radar features, scoring, projection, token-radar read models. |
| `domains/social_enrichment` | Watched-event gate, social-event extraction schema, OpenAI Agents request/response audit, enrichment job lifecycle, enrichment worker. |
| `domains/closed_loop_harness` | Social-event harness extraction read model, attention seeds, event clusters, snapshots, decisions, outcomes, credits, report-only weights, harness ops worker, harness health and read models. |
| `domains/notifications` | Notification rules, repository, delivery adapters, workers, notification read/write services. |
| `domains/pulse_lab` | Signal pulse read model, pulse candidate gate, pulse candidate worker, thesis model, thesis agent client, pulse repository. |
| `domains/account_quality` | Account quality snapshots, account quality scoring/read service, account alert read service. |

Root-level `models.py` is not a long-term dumping ground. Shared data types either move into the domain that owns them or into a deliberately named public interface module when multiple domains must use them.

## Conceptual data flow

The public event path remains semantically the same:

```
GMGN public stream
  -> domains/ingestion
  -> domains/evidence
  -> domains/token_intel
  -> domains/social_enrichment
  -> domains/closed_loop_harness
  -> domains/notifications and domains/pulse_lab
  -> app/surfaces/api + app/surfaces/cli + WebSocket hub
```

The arrows that change are ownership arrows, not product behaviour arrows. `collector -> pipeline -> storage <- retrieval -> api` becomes domain-local repositories and services called from a composition root. The current `IngestService` transaction remains one conceptual event-ingestion transaction, but its responsibilities are separated into domain interfaces so evidence insertion, token-intel derivation, market observation, alerts, and enrichment enqueueing each have an obvious owner.

The read path also remains semantically stable:

```
HTTP / CLI / WS request
  -> app surface validation/auth
  -> domain read service
  -> domain repository/query module
  -> public payload
```

Raw SQL is not removed from the codebase; it is moved to domain repository/query modules where ownership is explicit. Retrieval services such as harness score buckets and token-radar asset flow should not talk to `.conn` directly after the migration.

## Core models

- **Domain package.** A product-owned package under `domains/` with one bounded responsibility, one public import surface, and internal modules that are not imported by other domains.
- **Domain public interface.** The only cross-domain import surface. It exposes semantic operations or stable value types and hides internal repository/query/runtime structure.
- **Repository/query module.** The persistence boundary for a domain. It owns SQL, row decoding, JSON conversion, idempotent writes, and read-model query shape.
- **Service/scoring module.** Deterministic domain behaviour independent of app surfaces. Scoring modules live with the domain that owns the score.
- **Runtime/worker module.** Async loops, polling cadence, provider calls, and process lifecycle for one domain. Runtime modules may depend on services and repositories, but service modules do not depend on runtime modules.
- **Integration adapter.** External API or SDK wrapper under `integrations/`. It translates third-party shape into a provider interface consumed by a domain runtime/service.
- **App surface.** HTTP, WebSocket, and CLI translation. It validates request parameters, calls domain public interfaces, and returns public payloads. It does not own domain decisions.
- **Composition root.** App runtime wiring that creates repositories, services, integrations, workers, and tasks. It is allowed to import broadly because it is the explicit dependency assembly point.
- **Compatibility shim.** A temporary or permanent thin module that preserves a public import/entrypoint while delegating to the new implementation. It contains no business logic.

## Interface contracts

Public user-facing contracts are preserved:

- Config remains `~/.gmgn-twitter-intel/config.yaml`.
- FastAPI still exposes `/healthz`, `/readyz`, and existing `/api/*` routes.
- The authenticated WebSocket hub still accepts the current auth/subscribe messages and includes event, entity, alert, token-intent, token-resolution, and harness payloads after store commit.
- CLI command semantics remain defined by `uv run gmgn-twitter-intel --help`.
- Score payloads continue to expose component breakdowns and existing score-version strings unless a separate scoring spec changes them.
- Privacy boundaries around GMGN channels/protocol details remain internal.

Internal Python import paths are not public contracts except for installed entrypoints and app factory imports that the local tests explicitly exercise. Where an import path is retained for compatibility, it must be a thin shim and must not become a second source of truth.

## Acceptance criteria

- **AC1.** WHEN a coding agent opens `docs/ARCHITECTURE.md` after the migration THEN it SHALL see a domain-package map, allowed dependency directions, and the cross-domain interface rule instead of only the old technical-layer table.
- **AC2.** WHEN structural architecture tests inspect imports under `src/gmgn_twitter_intel/` THEN they SHALL report zero forbidden domain-internal imports, zero repository-to-service/runtime imports, zero platform-to-domain imports, and zero raw `.conn.execute` calls outside approved repository/query/composition modules.
- **AC3.** WHEN the source tree is inspected after completion THEN old flat technical-layer packages SHALL contain no business logic modules. Any remaining root modules SHALL be documented compatibility shims or public app entrypoints.
- **AC4.** WHEN API, WebSocket, CLI, repository, scoring, and worker tests run after import updates THEN public behaviour SHALL remain unchanged except for expected module-path assertions being rewritten to the new architecture.
- **AC5.** WHEN generated docs are regenerated THEN `docs/generated/cli-help.md`, `docs/generated/ws-protocol.md`, and `docs/generated/score-versions.md` SHALL remain semantically stable unless a separate approved spec changes those contracts.
- **AC6.** WHEN a new feature is added after this refactor THEN its target domain package and allowed import direction SHALL be mechanically obvious from failing or passing architecture tests.
- **AC7.** WHEN implementation verification is recorded THEN it SHALL include the full completion gate from `docs/WORKFLOW.md`: ruff, pytest, compileall, diff review against plan, and explicit notes for any live WebSocket / Docker Compose flows not exercised.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Large rename-only diff hides behaviour changes. | High | Execute in domain-sized slices; keep each slice behaviour-preserving; use tests before and after each slice; review moved files separately from edited files. |
| Temporary compatibility shims become permanent duplicate architecture. | High | Define shim expiry in the plan; final acceptance requires no business logic in shims. |
| Import cycles appear when domain interfaces are extracted. | High | Move shared value types to the owning domain or a public interface module before moving services; enforce acyclic imports with structural tests. |
| App wiring becomes a new god module. | Medium | Keep app runtime as a composition root only; domain workers and services remain in domain packages. |
| Tests become noisy because many imports change at once. | Medium | Rewrite tests domain-by-domain; preserve behavioural assertions; avoid weakening tests just to pass after moves. |
| Agents overfit to the old `pipeline` / `storage` examples still present in docs or tests. | Medium | Update `docs/ARCHITECTURE.md`, `tests/test_project_structure.py`, and any generated/internal references in the same migration. |
| PostgreSQL query ownership becomes unclear during the move. | Medium | Raw SQL is allowed only in repository/query modules and composition health checks; structural tests catch drift. |
| Score-version or public payload drift during relocation. | Medium | Run existing score, API, CLI, WebSocket, and generated-doc checks; no formula edits in this spec. |

## Evolution path

Once the domain packages are stable, the next useful expansion is source harness automation: a generated domain map, import graph report, stale shim detector, and doc-gardening check that compares `docs/ARCHITECTURE.md` to the actual package tree. The design should leave room for more domains if product boundaries become clearer, but it should not reintroduce broad technical catch-all packages.

This refactor also creates a natural place for narrower future specs: improving token-intel scoring, making harness settlement baselines richer, or tightening pulse candidate evaluation can each happen inside one domain package without rediscovering the whole source tree.

## Alternatives considered

- **Keep the current technical layers and add stricter tests** — rejected because it improves enforcement but not discoverability. A structural test can block `retrieval -> pipeline`, but it does not tell an agent whether a token-radar scoring change belongs in `pipeline`, `retrieval`, or `storage`.
- **Move only harness into a domain package** — rejected for this request because harness is only the most visible symptom. Token-radar, enrichment, asset-market, notifications, and pulse have the same cross-layer scattering.
- **Create one `core/` or `services/` package** — rejected because it would become another broad technical bucket. The target architecture needs domain names, not a renamed pipeline.
- **Big-bang move without compatibility shims** — rejected because API/CLI/runtime imports and tests would all change simultaneously, making review and rollback too risky. Shims are acceptable as scaffolding, but not as a final resting place for business logic.
- **Adopt a fully hexagonal architecture with ports/adapters for every dependency immediately** — rejected because it would add abstraction without measured need. The domain-package layout and import guardrails address the current pain while preserving room to introduce explicit ports where provider churn or testing pain justifies it.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Move business logic into domain packages; update architecture docs; add structural import / SQL ownership guardrails; preserve public HTTP / WebSocket / CLI / config semantics; run the completion gates in an implementation worktree. |
| Ask first | Removing compatibility shims that might affect external Python import users; renaming installed entrypoints; splitting any large service beyond what the package move requires; changing generated-doc commands or CI wiring. |
| Never | Change scoring formulas or score versions as part of the package move; add database schema changes; add new production dependencies solely for architecture enforcement; weaken existing behavioural tests to make moves easier; hide follow-up debt outside `docs/TECH_DEBT.md`. |
