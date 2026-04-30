# AGENTS.md

Guidance for coding agents working in this repository.

## Development Commands

```bash
uv sync
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

Run the CLI service:

```bash
uv run gmgn-twitter-intel serve
```

Equivalent module entrypoint:

```bash
uv run python -m gmgn_twitter_intel serve
```

Query stored events:

```bash
uv run gmgn-twitter-intel recent --limit 20
uv run gmgn-twitter-intel search --symbol PEPE --limit 20
```

## Architecture

This is a standard `uv` project using `src/gmgn_twitter_intel`.

The CLI service consumes GMGN anonymous public Twitter WebSocket channels, normalizes events into the LanceDB `twitter_events` fact table, marks handle-filtered rows for replay, and exposes an authenticated FastAPI WebSocket API at `/ws`.

The public configuration surface is intentionally small:

- `MONITOR_HANDLES`: comma-separated Twitter handles.
- `WS_TOKEN`: public WebSocket API token.
- `API_HOST` / `API_PORT`: FastAPI bind address.
- `LANCEDB_PATH` / `EMBEDDING_DIM`: LanceDB runtime store settings.

GMGN chains, channels, app versions, and protocol frames are internal collector strategy, not user-facing subscription concepts.

## Module Responsibilities

- `src/gmgn_twitter_intel/settings.py`: pydantic-settings environment loader.
- `src/gmgn_twitter_intel/api/app.py`: FastAPI app, health probes, WebSocket route, lifespan tasks.
- `src/gmgn_twitter_intel/api/ws.py`: authenticated WebSocket subscribe/replay/live push hub.
- `src/gmgn_twitter_intel/collector/direct_ws.py`: GMGN upstream WebSocket adapter.
- `src/gmgn_twitter_intel/collector/normalizer.py`: raw frame parsing and stable event normalization.
- `src/gmgn_twitter_intel/collector/service.py`: collector pipeline, `cp=0/cp=1` snapshot gate, handle matching, store-first publish.
- `src/gmgn_twitter_intel/pipeline/tweet_text.py`: tweet text projection, URL/cashtag/hashtag/mention extraction.
- `src/gmgn_twitter_intel/pipeline/token_extractor.py`: cheap EVM/Solana CA and cashtag entity extraction.
- `src/gmgn_twitter_intel/pipeline/processing_policy.py`: local gating status for embeddings and token processing.
- `src/gmgn_twitter_intel/pipeline/embedding.py`: hash and HTTP embedding backends plus pending embedding processing.
- `src/gmgn_twitter_intel/pipeline/social_windows.py`: social window parsing and bounds.
- `src/gmgn_twitter_intel/pipeline/llm_enrichment.py`: evidence-bound LiteLLM JSON enrichment with quote validation.
- `src/gmgn_twitter_intel/retrieval/search_service.py`: exact CA/symbol/handle and hybrid text retrieval.
- `src/gmgn_twitter_intel/retrieval/mindshare_service.py`: token social metrics over resolved entities.
- `src/gmgn_twitter_intel/storage/lancedb_client.py`: LanceDB table client and query/index helpers.
- `src/gmgn_twitter_intel/storage/lancedb_schema.py`: LanceDB `raw_frames` and `twitter_events` schemas.
- `src/gmgn_twitter_intel/storage/tweet_repository.py`: Twitter event repository over LanceDB.
- `src/gmgn_twitter_intel/storage/social_repository.py`: token social window persistence.
- `src/gmgn_twitter_intel/storage/llm_repository.py`: LLM run and extraction audit persistence.
- `src/gmgn_twitter_intel/cli.py`: `serve`, query, enrichment, and ops commands.

## Runtime Notes

- Public clients authenticate with `{"type":"auth","token":"..."}`.
- Public clients subscribe with `{"type":"subscribe","handles":["toly"],"replay":20}`.
- `coverage=public_stream` means events are filtered from GMGN's anonymous public stream; it is not a full Twitter firehose guarantee.
- Run one ASGI worker unless the collector and API are split into separate processes.
- There is no macOS LaunchAgent, systemd unit, or `service` subcommand. Use foreground CLI or Docker Compose.
- Docker Compose mounts `${GMGN_TWITTER_HOME:-$HOME/.gmgn-twitter-intel}` to `/data`; container LanceDB is `/data/twitter_intel.lancedb`.
- Local foreground default LanceDB is `~/.gmgn-twitter-intel/twitter_intel.lancedb`.

## MCP

Do not use MCP as the live event stream. FastMCP can be added later as an optional query/control plane, but `/ws` remains the production push API.
