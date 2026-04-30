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
uv run gmgn-twitter-intel serve
```

Recent events:

```bash
uv run gmgn-twitter-intel recent --limit 20
uv run gmgn-twitter-intel search --symbol PEPE --limit 20
```

## Architecture

This repository is a standard `uv + src/` Python service backed by LanceDB:

- `src/gmgn_twitter_intel/settings.py`: pydantic-settings config.
- `src/gmgn_twitter_intel/api/app.py`: FastAPI app, `/healthz`, `/readyz`, `/ws`, lifespan background tasks.
- `src/gmgn_twitter_intel/api/ws.py`: authenticated public WebSocket hub.
- `src/gmgn_twitter_intel/collector/direct_ws.py`: GMGN anonymous upstream WebSocket client.
- `src/gmgn_twitter_intel/collector/normalizer.py`: GMGN frame parsing and event normalization.
- `src/gmgn_twitter_intel/collector/service.py`: snapshot gate, handle filtering, store-first publish.
- `src/gmgn_twitter_intel/pipeline/*`: text cleanup, entity extraction, embeddings, mindshare, and LLM enrichment helpers.
- `src/gmgn_twitter_intel/retrieval/*`: token search and mindshare services.
- `src/gmgn_twitter_intel/storage/*`: LanceDB client, schemas, and repositories.
- `src/gmgn_twitter_intel/cli.py`: `serve`, query, enrichment, and ops commands.

External users pass only handles, symbols, or CAs to this service. GMGN chains/channels are internal collector strategy.

## Operational Notes

- Public WebSocket endpoint: `/ws`.
- Auth message: `{"type":"auth","token":"..."}`.
- Subscribe message: `{"type":"subscribe","handles":["toly"],"replay":20}`.
- Run one ASGI worker; multiple workers duplicate the upstream collector.
- There is no macOS LaunchAgent, systemd unit, or `service` subcommand. Use foreground CLI or Docker Compose.
- Docker Compose mounts `${GMGN_TWITTER_HOME:-$HOME/.gmgn-twitter-intel}` to `/data`; container LanceDB is `/data/twitter_intel.lancedb`.
- Local foreground default LanceDB is `~/.gmgn-twitter-intel/twitter_intel.lancedb`.
- MCP/FastMCP is optional control/query infrastructure only, not the live event push mechanism.
