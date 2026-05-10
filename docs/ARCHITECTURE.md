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
| `domains/asset_market/` | Asset registry, chain/address identity, price observations, discovery, market hydration, asset-market sync, message-market observation. |
| `domains/token_intel/` | Token evidence, token intents, intent resolution, token-target views, token-radar features, scoring (heat / quality / propagation / tradeability / timing / opportunity), projection, audit queries, signal alerts. |
| `domains/social_enrichment/` | Watched-event gate, social-event extraction schema, OpenAI Agents enrichment lifecycle, enrichment worker. |
| `domains/closed_loop_harness/` | Social-event harness extraction, attention seeds, snapshots, settlement, outcomes, credits, weights, harness health, ops worker, score-bucket read models. |
| `domains/notifications/` | Notification rules, repository, delivery, workers, candidate types. |
| `domains/pulse_lab/` | Signal pulse read model, pulse candidate gate / worker, pulse thesis, pulse persistence. |
| `domains/account_quality/` | Account-quality snapshots, account-quality read service, account-alert read service. |

## Dependency Direction

Within a domain, the allowed sequence is:

```
types/config → repositories/queries → services/scoring → read_models/runtime → app surfaces
```

| Layer | May import from |
|-------|-----------------|
| `domains/<d>/types`, `domains/<d>/config` | stdlib, third-party, same-domain `types`. |
| `domains/<d>/repositories`, `domains/<d>/queries` | own domain's `types`, `platform/db`, stdlib, third-party. **Never** imports `services/`, `runtime/`, `read_models/`. Owns SQL. |
| `domains/<d>/services`, `domains/<d>/scoring` | own domain's `types`, `repositories`, `queries`, plus other domains' `interfaces.py` only. |
| `domains/<d>/read_models` | own domain's `types`, `repositories`, `queries`, plus other domains' `interfaces.py`. **No raw SQL** — query modules live in `repositories/` or `queries/`. |
| `domains/<d>/runtime` | own domain's `services`, `repositories`, `queries`, `scoring`, plus other domains' `interfaces.py`. |
| `app/runtime` | composition root: may import any domain runtime, repository, or interface to wire the process. |
| `app/surfaces/api`, `app/surfaces/cli` | domain `interfaces.py` and read services. **No domain SQL, scoring, settlement, token resolution, or notification rules** — surfaces translate public inputs into domain calls. |
| `platform/*` | stdlib, third-party. **Never** imports `domains/`, `integrations/`, or `app/`. |
| `integrations/*` | stdlib, third-party, `platform/*`. They wrap external APIs; they do not import `domains/` or `app/`. |

Cross-domain imports MUST go through the target domain's `interfaces.py` (or `_constants.py` for leaf data). `tests/test_src_domain_architecture.py::test_cross_domain_imports_use_interfaces` enforces this.

Raw SQL (`conn.execute(...)`) lives ONLY in `repositories/`, `queries/`, `platform/db/`, or `app/runtime/` health checks. `tests/test_src_domain_architecture.py::test_raw_sql_is_owned_by_repositories_queries_or_app_runtime` enforces this.

## Generated and reference material

- `docs/generated/{cli-help,ws-protocol,score-versions,db-schema}.md` — regenerated by `make docs-generated`. Score-version paths reflect `domains/token_intel/scoring/`.
- `docs/CONTRACTS.md` — public HTTP / WebSocket / CLI surface contracts.
- `docs/references/` — papers and external API references underpinning algorithm choices.

To find code, prefer `ls src/gmgn_twitter_intel/domains/<domain>/` over a memorised file list. This file pins the package map; per-file responsibilities live in the code and its tests.
