# Architecture

> **Scope.** Owns Python-service package boundaries, dependency direction, and conceptual data flow for `gmgn-twitter-intel`. Frontend (`web/`) architecture lives in `FRONTEND.md`. Public interface contracts live in `CONTRACTS.md`.

The service is organised around domain packages, explicit integration adapters, platform infrastructure, and app surfaces. Boundaries are mechanically enforced by `tests/test_src_domain_architecture.py` and `tests/test_project_structure.py::test_project_uses_domain_package_src_layout`.

```
GMGN public stream
  → domains/ingestion
  → domains/evidence
  → domains/token_intel
  → domains/social_enrichment
  → domains/closed_loop_harness
  → domains/notifications and domains/pulse_lab
  → app/surfaces/api + app/surfaces/cli
```

This repository is the system of record for agent work: if a production
decision changes, update the nearest architecture / contract / reliability
document in the same change. A fresh agent must not need chat history to know
where token identity is extracted, resolved, refreshed, scored, and served.

## Package Roots

| Root | Responsibility |
|------|----------------|
| `app/` | Composition root plus HTTP, WebSocket, and CLI surfaces. `app/runtime/` wires domains; `app/surfaces/{api,cli}/` translate public inputs and outputs. |
| `domains/` | Product domains. Each domain owns its repositories, queries, services / scoring, read models, and runtime workers. |
| `integrations/` | External adapters for GMGN, OKX, and OpenAI Agents. They translate third-party API shapes but do not own product decisions. |
| `platform/` | Config, PostgreSQL infrastructure (client, migrations, audit, Alembic), logging, and runtime paths. Platform never imports product domains. |

Top-level entry shims `cli.py` and `__main__.py` exist only because `pyproject.toml` points the installed command at `gmgn_twitter_intel.cli:main`. They contain no logic.

## Domains

| Domain | Owns |
|--------|------|
| `domains/ingestion/` | GMGN public-stream frame handling, snapshot gate, handle filtering, raw public-stream normalisation, collector status. |
| `domains/evidence/` | Canonical Twitter event model, event identity, text projection, entity extraction, evidence and entity persistence, ingest orchestration. |
| `domains/asset_market/` | Asset registry, chain/address identity, asset identity evidence/current identity selection, price observations, field-aware current market read models, discovery, asset-market sync, message-market observation. |
| `domains/token_intel/` | Token evidence, token intents, deterministic resolution, token-target views, Token Radar feature aggregation, `token_factor_snapshot_v1` construction, factor-snapshot projection, audit queries, signal alerts. |
| `domains/social_enrichment/` | Watched-event gate, social-event extraction schema, OpenAI Agents enrichment lifecycle, enrichment worker. |
| `domains/closed_loop_harness/` | Social-event harness extraction, attention seeds, snapshots, settlement, outcomes, credits, weights, harness health, ops worker, score-bucket read models. |
| `domains/notifications/` | Notification rules, repository, delivery, workers, candidate types. |
| `domains/pulse_lab/` | Signal pulse read model, factor-snapshot candidate gate / worker, bounded pulse recommendation agent, pulse persistence. |
| `domains/account_quality/` | Account-quality snapshots, account-quality read service, account-alert read service. |

## Module Architecture Documents

Global architecture stays intentionally small. Important subsystems keep their
own maps next to the code they describe, and this file links to them.

| Module | File | Covers |
|--------|------|--------|
| Token Radar and token identity | [`src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`](../src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md) | GMGN frame to token evidence, intents, deterministic resolution, discovery / reprocess, market observations, radar projection, and hard identity boundaries. |

When a subsystem needs more than a short row here, add
`src/gmgn_twitter_intel/domains/<domain>/ARCHITECTURE.md` and link it from this
table. Keep local docs minimal, current, and tied to code changes.

## Dependency Direction

Within a domain, the allowed sequence is:

```
types/config → repositories/queries → services/scoring → read_models/runtime → app surfaces
```

| Layer | May import from |
|-------|-----------------|
| `domains/<d>/types`, `domains/<d>/config` | stdlib, third-party, same-domain `types`. |
| `domains/<d>/providers.py` | stdlib, third-party typing primitives, and same-domain or interface value types. Pure provider contracts only; no `integrations/*`, `platform/db`, or `platform/paths`. |
| `domains/<d>/repositories`, `domains/<d>/queries` | own domain's `types`, `platform/db`, stdlib, third-party. **Never** imports `services/`, `runtime/`, `read_models/`. Owns SQL. |
| `domains/<d>/services`, `domains/<d>/scoring` | own domain's `types`, `providers.py`, `repositories`, `queries`, plus other domains' `interfaces.py` only. **No `integrations/*`, `platform/db`, or `platform/paths`.** |
| `domains/<d>/read_models` | own domain's `types`, `repositories`, `queries`, plus other domains' `interfaces.py`. **No raw SQL** — query modules live in `repositories/` or `queries/`. |
| `domains/<d>/runtime` | own domain's `services`, `providers.py`, `repositories`, `queries`, `scoring`, plus other domains' `interfaces.py`. **No `integrations/*`, `platform/db`, or `platform/paths`.** |
| `app/runtime/providers_wiring.py` | Service-process composition module. The only service-runtime file that joins concrete `integrations/*` clients with domain Provider contracts. It may translate supplier shapes such as OKX chain indexes into domain values. |
| `app/runtime/app.py` | Runtime orchestration: builds repositories, workers, surfaces, readiness, and lifecycle. Imports `wire_providers(...)` / `WiredProviders`; does not import concrete integrations or domain provider modules directly. |
| `app/runtime` | composition root: may import any domain runtime, repository, or interface to wire the process, subject to the dedicated Provider wiring rule above. |
| `app/surfaces/api`, `app/surfaces/cli` | domain `interfaces.py` and read services. **No domain SQL, scoring, settlement, token resolution, or notification rules** — surfaces translate public inputs into domain calls. |
| `platform/*` | stdlib, third-party. **Never** imports `domains/`, `integrations/`, or `app/`. |
| `integrations/*` | stdlib, third-party, `platform/*`. They wrap external APIs; they do not import `domains/` or `app/`. |

Cross-domain imports MUST go through the target domain's `interfaces.py` (or `_constants.py` for leaf data). `tests/test_src_domain_architecture.py::test_cross_domain_imports_use_interfaces` enforces this.

Raw SQL (`conn.execute(...)`) lives ONLY in `repositories/`, `queries/`, `platform/db/`, or `app/runtime/` health checks. `tests/test_src_domain_architecture.py::test_raw_sql_is_owned_by_repositories_queries_or_app_runtime` enforces this.

Transaction ownership follows the same rule: domain services and runtime workers use repository/session Unit of Work methods, not `platform.db.postgres_client.transaction` directly. Repositories and `app/runtime/repository_session.py` own the concrete PostgreSQL transaction context.

Provider modules are intentionally sparse. Only domains with real inbound cross-cutting dependencies have `providers.py` today: `ingestion`, `asset_market`, `social_enrichment`, and `pulse_lab`. Do not add empty provider files.

CLI ops remain a separate operational surface exception: they may construct external clients for explicit operator commands, while service runtime construction stays centralized in `app/runtime/providers_wiring.py`.

## Generated and reference material

- `docs/generated/{cli-help,ws-protocol,score-versions,db-schema}.md` — regenerated by `make docs-generated`. Score-version paths reflect `domains/token_intel/scoring/`.
- `docs/CONTRACTS.md` — public HTTP / WebSocket / CLI surface contracts.
- `docs/references/` — papers and external API references underpinning algorithm choices.

To find code, prefer `ls src/gmgn_twitter_intel/domains/<domain>/` over a memorised file list. This file pins the package map; per-file responsibilities live in the code and its tests.
