# Reliability

> **Scope.** Owns operational invariants that must hold in any deployment of this service. Setup commands live in `SETUP.md`; security policy in `SECURITY.md`.

## Single ASGI worker

One ASGI worker. Multiple workers duplicate the upstream collector. If collector and API must scale separately, split them into distinct processes.

## Foreground-only run model

`~/.gmgn-twitter-intel/config.yaml` is the only application config source. There is no macOS LaunchAgent, systemd unit, or `service` subcommand — run via foreground CLI or Docker Compose.

## Docker Compose state

Docker Compose bind-mounts the host config directory into the container and pins PostgreSQL data to the `gmgn-twitter-intel-postgres` named volume. Local foreground and Docker share the same config; query Docker data via `/api/*`, `/ws`, or `docker compose exec app gmgn-twitter-intel ...`.

## Coverage semantics

`coverage=public_stream` flags events as filtered from GMGN's anonymous public stream — not a full Twitter firehose guarantee. Do not advertise broader coverage in payloads or docs.

## MCP boundary

MCP / FastMCP is optional control / query infrastructure only. `/ws` is the production live push channel; do not route real-time events through MCP.
