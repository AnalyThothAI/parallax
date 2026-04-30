# GMGN Twitter CLI

Production-oriented collector for GMGN anonymous public Twitter signals.

Users configure only a Twitter handle list. The service consumes GMGN public WebSocket channels, normalizes public events into SQLite, derives matched events for the configured handles, and exposes replay plus live delivery through an authenticated WebSocket API.

## Architecture

```text
GMGN anonymous WebSocket
        |
        v
collector/direct_ws.py
        |
        v
collector/service.py
  - frame parsing
  - cp=0/cp=1 snapshot gate
  - handle matching
        |
        +--> store/sqlite.py
        |
        +--> api/ws.py
```

FastAPI owns the production process:

- `src/gmgn_twitter_cli/api/app.py`: ASGI app, `/healthz`, `/readyz`, `/ws`, lifespan background tasks.
- `src/gmgn_twitter_cli/collector/direct_ws.py`: GMGN upstream WebSocket protocol adapter.
- `src/gmgn_twitter_cli/collector/normalizer.py`: raw GMGN payload to stable `TwitterEvent`.
- `src/gmgn_twitter_cli/collector/service.py`: collector pipeline and `cp=0/cp=1` deduplication.
- `src/gmgn_twitter_cli/store/sqlite.py`: SQLite WAL `observed_events` and `matched_events` journals.
- `src/gmgn_twitter_cli/settings.py`: pydantic-settings based environment loader.
- `src/gmgn_twitter_cli/cli.py`: `serve` and `recent` commands.

Legacy Playwright login, Telegram formatting, browser state, and root script entrypoints are intentionally removed.

## Setup

```bash
uv sync
cp .env.example .env
```

Required setting:

```env
WS_TOKEN=replace-with-a-strong-token
MONITOR_HANDLES=toly,elonmusk,cz_binance
```

Run the CLI service:

```bash
uv run gmgn-twitter-cli serve
```

Equivalent module entrypoint:

```bash
uv run python -m gmgn_twitter_cli serve
```

## Configuration

Public configuration:

| Variable | Purpose |
|---|---|
| `WS_TOKEN` | Required token for `/ws` clients |
| `API_HOST` | FastAPI bind host, default `0.0.0.0` |
| `API_PORT` | FastAPI bind port, default `8765` |
| `MONITOR_HANDLES` | Comma-separated Twitter handles to publish |
| `EVENT_DB_PATH` | SQLite event journal path, default `data/events.sqlite3` |
| `REPLAY_LIMIT` | Default replay count per subscription |
| `OBSERVED_RETENTION_DAYS` | Retention for all parsed public-stream events, default `7` |
| `MATCHED_RETENTION_DAYS` | Retention for matched replay events, default `180` |
| `LOG_FILE` | Loguru rotating file path |

Internal collector strategy:

| Variable | Purpose |
|---|---|
| `UPSTREAM_CHAINS` | GMGN coverage hint, default `sol,eth,base,bsc` |
| `UPSTREAM_CHANNELS` | GMGN channels, default `twitter_monitor_basic,twitter_monitor_token` |
| `GMGN_WS_APP_VERSION` | GMGN web client version string |
| `GMGN_WS_PROXY` | Optional upstream proxy |
| `UPSTREAM_RECONNECT_DELAY` | Upstream reconnect delay seconds |
| `UPSTREAM_HEARTBEAT_INTERVAL` | Upstream heartbeat interval seconds |

`UPSTREAM_CHAINS` is not a user subscription concept. External users pass handles only.

## WebSocket API

Connect to:

```text
ws://127.0.0.1:8765/ws
```

Authenticate first:

```json
{"type":"auth","token":"replace-with-a-strong-token"}
```

Then subscribe:

```json
{"type":"subscribe","handles":["toly","elonmusk"],"replay":20}
```

The server replies with:

```json
{"type":"ready"}
```

Events are sent as:

```json
{"type":"event","event":{"event_id":"gmgn:twitter_monitor_basic:...","source":{"coverage":"public_stream"},"author":{"handle":"toly"},"content":{"text":"..."}}}
```

`coverage=public_stream` means events are filtered from GMGN's anonymous public stream. It is not a full Twitter firehose guarantee.

## SQLite Replay

The store uses WAL mode and has two tables:

- `observed_events`: every GMGN public event that can be parsed and normalized, before handle filtering.
- `matched_events`: events that match `MONITOR_HANDLES`; this is the table used by `/ws` replay and `recent`.

When the service starts, it backfills `matched_events` from retained `observed_events` for the current handle list. That means adding a new handle can recover recent history as long as the event is still inside `OBSERVED_RETENTION_DAYS`.

Query recent matched events:

```bash
uv run gmgn-twitter-cli recent --limit 20
uv run gmgn-twitter-cli recent --handles toly,elonmusk --limit 20
```

## Health

FastAPI exposes probes on the same port:

```bash
curl http://127.0.0.1:8765/healthz
curl http://127.0.0.1:8765/readyz
```

`/readyz` includes collector counters, `store_counts.observed_events`, and `store_counts.matched_events`.

## Production

Install and start with systemd:

```bash
uv sync --frozen
sudo ln -sf "$(pwd)/deploy/systemd/gmgn-twitter-cli.service" /etc/systemd/system/gmgn-twitter-cli.service
sudo systemctl daemon-reload
sudo systemctl enable gmgn-twitter-cli
sudo systemctl start gmgn-twitter-cli
```

Inspect:

```bash
sudo systemctl status gmgn-twitter-cli --no-pager -l
sudo journalctl -u gmgn-twitter-cli -f
```

Run one ASGI worker. Multiple workers would start duplicate collectors unless the collector and public API are split into separate processes.

For public TLS, put Nginx or Caddy in front of `http://127.0.0.1:8765`; a sample Nginx config is in `deploy/nginx/gmgn-twitter-cli.conf`.

## macOS LaunchAgent

Recommended lifecycle commands:

```bash
uv run gmgn-twitter-cli service install --start
uv run gmgn-twitter-cli service status
uv run gmgn-twitter-cli service logs --lines 80
uv run gmgn-twitter-cli service restart
uv run gmgn-twitter-cli service stop
```

The legacy shell entrypoint is now only a thin wrapper around the CLI:

```bash
./deploy/macos/install_launchd.sh
```

The installer copies the app to `~/.local/share/gmgn-twitter-cli/app` and runs launchd from there. This avoids macOS privacy restrictions that can block background agents from reading projects under `~/Documents`. Existing `.env` in the install directory is preserved; on first install, the CLI copies the current repo `.env` when present.

Inspect:

```bash
launchctl print gui/$(id -u)/com.local.gmgn-twitter-cli
tail -f logs/launchd.stderr.log
curl http://127.0.0.1:8765/healthz
```

Stop the LaunchAgent:

```bash
uv run gmgn-twitter-cli service stop
```

## MCP

MCP is not the event push path. FastMCP is useful as an optional control/query plane for tools like `get_recent_events`, `get_status`, or `update_handles`, but MCP is client-session oriented and should not be used as a reliable real-time WebSocket subscription or out-of-band wakeup mechanism. Keep `/ws` for live market signals.

## Development

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```
