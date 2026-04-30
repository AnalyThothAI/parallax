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
uv run gmgn-twitter-cli serve
```

Recent events:

```bash
uv run gmgn-twitter-cli recent --limit 20
```

## Architecture

This repository is a standard `uv + src/` Python service:

- `src/gmgn_twitter_cli/settings.py`: pydantic-settings config.
- `src/gmgn_twitter_cli/api/app.py`: FastAPI app, `/healthz`, `/readyz`, `/ws`, lifespan background tasks.
- `src/gmgn_twitter_cli/api/ws.py`: authenticated public WebSocket hub.
- `src/gmgn_twitter_cli/collector/direct_ws.py`: GMGN anonymous upstream WebSocket client.
- `src/gmgn_twitter_cli/collector/normalizer.py`: GMGN frame parsing and event normalization.
- `src/gmgn_twitter_cli/collector/service.py`: snapshot gate, handle filtering, store-first publish.
- `src/gmgn_twitter_cli/store/sqlite.py`: SQLite WAL `observed_events` and `matched_events` store.
- `src/gmgn_twitter_cli/cli.py`: `serve` and `recent`.

External users pass only a handle list. GMGN chains/channels are internal collector strategy.

## Operational Notes

- Public WebSocket endpoint: `/ws`.
- Auth message: `{"type":"auth","token":"..."}`.
- Subscribe message: `{"type":"subscribe","handles":["toly"],"replay":20}`.
- Run one ASGI worker; multiple workers duplicate the upstream collector.
- Systemd unit: `deploy/systemd/gmgn-twitter-cli.service`.
- macOS lifecycle: `gmgn-twitter-cli service install/start/stop/status/logs/uninstall`.
- `deploy/macos/install_launchd.sh` is only a thin wrapper around `gmgn-twitter-cli service install --start`.
- macOS LaunchAgent runs from `~/.local/share/gmgn-twitter-cli/app` to avoid `~/Documents` privacy restrictions.
- MCP/FastMCP is optional control/query infrastructure only, not the live event push mechanism.
