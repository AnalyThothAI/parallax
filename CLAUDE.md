# CLAUDE.md

Guidance for coding agents working in this repository.

## Commands

```bash
uv sync
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

Run:

```bash
uv run gmgn-twitter-intel init
uv run gmgn-twitter-intel serve
```

Trader queries:

```bash
uv run gmgn-twitter-intel recent --limit 20
uv run gmgn-twitter-intel search --symbol PEPE --limit 20
uv run gmgn-twitter-intel token-flow --window 5m --limit 20
uv run gmgn-twitter-intel account-alerts --window 24h --limit 50
uv run gmgn-twitter-intel narrative-flow --window 1h --limit 20
uv run gmgn-twitter-intel account-narratives --window 24h --limit 50
```

## Architecture

This repository is a standard `uv + src/` Python service backed by PostgreSQL:

- `src/gmgn_twitter_intel/settings.py`: YAML config loader and typed runtime settings.
- `src/gmgn_twitter_intel/api/app.py`: FastAPI app, `/healthz`, `/readyz`, `/ws`, lifespan background tasks.
- `src/gmgn_twitter_intel/api/ws.py`: authenticated public WebSocket hub.
- `src/gmgn_twitter_intel/collector/direct_ws.py`: GMGN anonymous upstream WebSocket client.
- `src/gmgn_twitter_intel/collector/normalizer.py`: GMGN frame parsing and event normalization.
- `src/gmgn_twitter_intel/collector/service.py`: snapshot gate, handle filtering, store-first publish.
- `src/gmgn_twitter_intel/pipeline/entity_extractor.py`: deterministic entity extraction.
- `src/gmgn_twitter_intel/pipeline/ingest_service.py`: evidence/entity/signal ingest orchestration.
- `src/gmgn_twitter_intel/pipeline/signal_builder.py`: account token alerts and token windows.
- `src/gmgn_twitter_intel/pipeline/social_event_extraction.py`: strict social-event extraction parsing.
- `src/gmgn_twitter_intel/pipeline/enrichment_worker.py`: async watched-account enrichment jobs.
- `src/gmgn_twitter_intel/retrieval/*`: PostgreSQL-backed search, token-flow, account-alert, and harness services.
- `src/gmgn_twitter_intel/storage/*`: PostgreSQL client, Alembic migrations, and repositories.
- `src/gmgn_twitter_intel/cli.py`: `serve`, query, signal, and ops commands.

External users pass handles, symbols, or CAs to this service. GMGN chains/channels are internal collector strategy.

## Operational Notes

- Public WebSocket endpoint: `/ws`.
- Auth message: `{"type":"auth","token":"..."}`.
- Subscribe message: `{"type":"subscribe","handles":["toly"],"replay":20}`.
- Payloads include `event`, `entities`, `alerts`, and `enrichment`.
- Run one ASGI worker; multiple workers duplicate the upstream collector.
- There is no macOS LaunchAgent, systemd unit, or `service` subcommand. Use foreground CLI or Docker Compose.
- The only application config source is `~/.gmgn-twitter-intel/config.yaml`.
- Docker Compose bind-mounts host `~/.gmgn-twitter-intel` to container `/root/.gmgn-twitter-intel`.
- Local foreground and Docker use the same host config. Docker Compose runs PostgreSQL with the `gmgn-twitter-intel-postgres` named volume.
- MCP/FastMCP is optional control/query infrastructure only, not the live event push mechanism.
