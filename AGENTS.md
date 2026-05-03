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
uv run gmgn-twitter-intel init
uv run gmgn-twitter-intel serve
```

Query stored events and signals:

```bash
uv run gmgn-twitter-intel recent --limit 20
uv run gmgn-twitter-intel search --symbol PEPE --limit 20
uv run gmgn-twitter-intel token-flow --window 5m --limit 20
uv run gmgn-twitter-intel account-alerts --window 24h --limit 50
uv run gmgn-twitter-intel narrative-flow --window 1h --limit 20
uv run gmgn-twitter-intel account-narratives --window 24h --limit 50
uv run gmgn-twitter-intel enrichment-jobs --limit 50
```

## Architecture

This is a standard `uv` project using `src/gmgn_twitter_intel`.

The service consumes GMGN anonymous public Twitter WebSocket channels, normalizes events into a SQLite WAL evidence store, extracts deterministic entities, materializes token signals, enqueues watched-account LLM enrichment jobs, materializes narrative signals, and exposes an authenticated FastAPI WebSocket API at `/ws`.

The public configuration surface is intentionally small:

- `~/.gmgn-twitter-intel/config.yaml`: the only application configuration source.
- `handles`: watched Twitter handles.
- `ws_token`: public WebSocket API token.
- `api`: FastAPI bind address and replay settings.
- `storage.sqlite_path`: SQLite runtime database path, relative to `~/.gmgn-twitter-intel` by default.
- `llm.openai_api_key` / `llm.openai_model`: optional watched-account enrichment worker credentials.

GMGN chains, channels, app versions, and protocol frames are internal collector strategy, not user-facing subscription concepts.

## Module Responsibilities

- `src/gmgn_twitter_intel/settings.py`: YAML config loader and typed runtime settings.
- `src/gmgn_twitter_intel/api/app.py`: FastAPI app, health probes, WebSocket route, lifespan tasks.
- `src/gmgn_twitter_intel/api/ws.py`: authenticated WebSocket subscribe/replay/live push hub.
- `src/gmgn_twitter_intel/collector/direct_ws.py`: GMGN upstream WebSocket adapter.
- `src/gmgn_twitter_intel/collector/normalizer.py`: raw frame parsing and stable event normalization.
- `src/gmgn_twitter_intel/collector/service.py`: collector pipeline, `cp=0/cp=1` snapshot gate, handle matching, store-first publish.
- `src/gmgn_twitter_intel/pipeline/tweet_text.py`: tweet text projection, URL/cashtag/hashtag/mention extraction.
- `src/gmgn_twitter_intel/pipeline/entity_extractor.py`: deterministic CA, cashtag, hashtag, mention, and URL/domain extraction.
- `src/gmgn_twitter_intel/pipeline/ingest_service.py`: transactional evidence/entity/signal ingest orchestration.
- `src/gmgn_twitter_intel/pipeline/signal_builder.py`: account token alerts and token window updates.
- `src/gmgn_twitter_intel/pipeline/llm_enrichment.py`: evidence-bound LLM enrichment parsing.
- `src/gmgn_twitter_intel/pipeline/enrichment_worker.py`: async enrichment job processor.
- `src/gmgn_twitter_intel/retrieval/search_service.py`: exact CA/symbol/handle and SQLite FTS5 retrieval.
- `src/gmgn_twitter_intel/retrieval/token_flow_service.py`: token social window reads.
- `src/gmgn_twitter_intel/retrieval/account_alert_service.py`: watched-account alert reads.
- `src/gmgn_twitter_intel/retrieval/narrative_service.py`: narrative signal reads.
- `src/gmgn_twitter_intel/storage/sqlite_client.py`: SQLite connection helpers and WAL pragmas.
- `src/gmgn_twitter_intel/storage/sqlite_schema.py`: schema and migrations.
- `src/gmgn_twitter_intel/storage/evidence_repository.py`: raw frame, normalized event, and FTS persistence.
- `src/gmgn_twitter_intel/storage/entity_repository.py`: deterministic entity persistence and lookups.
- `src/gmgn_twitter_intel/storage/signal_repository.py`: alert and window persistence.
- `src/gmgn_twitter_intel/storage/enrichment_repository.py`: enrichment job, model run, token candidate, and narrative signal persistence.
- `src/gmgn_twitter_intel/cli.py`: `serve`, query, signal, and ops commands.

## Runtime Notes

- Public clients authenticate with `{"type":"auth","token":"..."}`.
- Public clients subscribe with `{"type":"subscribe","handles":["toly"],"replay":20}`.
- Live and replay payloads include `event`, `entities`, `alerts`, and `enrichment`.
- `coverage=public_stream` means events are filtered from GMGN's anonymous public stream; it is not a full Twitter firehose guarantee.
- Run one ASGI worker unless the collector and API are split into separate processes.
- There is no macOS LaunchAgent, systemd unit, or `service` subcommand. Use foreground CLI or Docker Compose.
- Docker Compose bind-mounts host `~/.gmgn-twitter-intel` to container `/root/.gmgn-twitter-intel`.
- Local foreground and Docker use the same host config and SQLite file under `~/.gmgn-twitter-intel`.

## MCP

Do not use MCP as the live event stream. FastMCP can be added later as an optional query/control plane, but `/ws` remains the production push API.
