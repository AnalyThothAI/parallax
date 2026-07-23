# GMGN Anonymous Public WebSocket — Protocol Notes

**Source of truth:** `src/parallax/collector/`
**Cited by:** `docs/OPERATIONS.md` (provider reliability boundary), `docs/SECURITY.md` (privacy boundary).

## Scope

This file is a router into the collector code. It exists so specs can cite a stable relative path instead of pinning line numbers in `collector/`. Detailed frame schemas, channel lists, and chain identifiers live as constants and docstrings inside the source files below.

## Source files

| Concern | File |
|---------|------|
| Connection lifecycle, reconnect | `src/parallax/collector/direct_ws.py` |
| Frame parsing / envelope | `src/parallax/collector/gmgn_token_payload.py` |
| `cp=0` / `cp=1` snapshot gate | `src/parallax/collector/normalizer.py` |
| Handle filter | `src/parallax/collector/service.py` (filter logic inlined in service orchestration) |
| Subscription bookkeeping | `src/parallax/collector/subscriptions.py` |

## Privacy boundary (load-bearing)

The chain identifiers, channel names, app-version handshake fields, and frame envelope keys observed by `collector/` are GMGN's internal protocol. Per `docs/SECURITY.md` and `docs/CONTRACTS.md` they MUST NOT appear in any user-facing payload (HTTP, WebSocket, CLI). Tests under `tests/test_*payload*.py` enforce this.
