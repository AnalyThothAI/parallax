# Architecture

> **Scope.** Owns the Python-service layer boundaries and conceptual data flow for `gmgn-twitter-intel`. Frontend (`web/`) architecture lives in `FRONTEND.md`. Public interface contracts live in `CONTRACTS.md`.

A single Python service organised as a five-stage pipeline writing to one PostgreSQL store.

```
GMGN public WS  →  collector/  →  pipeline/  →  storage/  ←  retrieval/  →  api/  →  WS / HTTP / CLI consumers
```

## Layers

| Layer | Directory | Responsibility |
|------|-----------|---------------|
| Collector | `src/gmgn_twitter_intel/collector/` | GMGN anonymous-WebSocket adapter, frame parsing, `cp=0/cp=1` snapshot gate, handle filter, store-first publish, subscription bookkeeping. |
| Pipeline  | `src/gmgn_twitter_intel/pipeline/`  | Deterministic entity extraction, token-intent resolution, async LLM enrichment for watched accounts, closed-loop harness materialisation (snapshot → settlement → credit → scoring), token-radar feature build & projection, notification rules / delivery, pulse candidate evaluation & thesis agent, asset-market & message-market sync workers. |
| Storage   | `src/gmgn_twitter_intel/storage/`   | Single PostgreSQL store. One repository per aggregate (evidence, entity, signal, asset, harness, notification, pulse, projection, registry, token-radar, token-target, intent-resolution, account-quality, market, price-observation, enrichment, discovery). Alembic migrations + `repository_session` helper. |
| Retrieval | `src/gmgn_twitter_intel/retrieval/` | Read services for HTTP / WebSocket / CLI: search, asset-flow, asset-search, account-alert, account-quality, harness, signal-pulse, token-target (posts, social timeline, stage builder, message price payload), plus the scoring components (heat, propagation, opportunity, catalyst, baseline, tradeability, timing, post-text quality, discussion quality, diffusion health, timeline features). |
| API       | `src/gmgn_twitter_intel/api/`       | FastAPI HTTP routes (`/healthz`, `/readyz`, `/api/...`) and the authenticated public WebSocket hub at `/ws`. |
| CLI       | `src/gmgn_twitter_intel/cli.py`     | Argparse front-end exposing the same data as the API plus operator subcommands (`db`, `ops`). |

## Cross-cutting

- `src/gmgn_twitter_intel/market/` — OKX CEX/DEX clients and the GMGN OpenAPI client used by the asset and price-observation pipelines.
- `src/gmgn_twitter_intel/settings.py` — single config loader (`~/.gmgn-twitter-intel/config.yaml`).
- `src/gmgn_twitter_intel/runtime_paths.py`, `models.py`, `logging_setup.py` — shared runtime utilities.
- `tests/` mirrors the package layout. Schema and Docker assets are pinned by `tests/test_postgres_schema*.py` and `tests/test_compose_*.py`.

To find code, prefer `ls src/gmgn_twitter_intel/<layer>/` over a memorised file list. This file pins the layer boundaries; per-file responsibilities live in the code and its tests.
