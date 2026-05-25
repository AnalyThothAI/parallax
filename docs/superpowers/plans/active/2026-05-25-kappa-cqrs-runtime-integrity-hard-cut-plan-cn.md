# Kappa/CQRS Runtime Integrity Hard Cut Plan

Date: 2026-05-25

## Tasks

- [x] Add transaction primitives and repository transaction guards for worker
  fact/control-plane writes.
- [x] Make market tick persistence atomic and enqueue
  `market_tick_current_dirty_targets`.
- [x] Make `market_tick_current` a single-owner projection and route Token Radar
  wakeups through `market_tick_current_updated`.
- [x] Add explicit ops repair/rebuild commands for market current and Token
  Radar dirty target enqueue.
- [x] Remove Token Radar runtime idle catch-up scans.
- [x] Convert resolution refresh to `token_discovery_dirty_lookup_keys`.
- [x] Remove Token Radar legacy numeric confidence fallback.
- [x] Hard-cut provider-backed API/read paths for market candles and stock
  quotes.
- [x] Bound WebSocket fan-out against slow subscribers.
- [x] Move wake `LISTEN` waits off the event loop default executor and close
  them through worker lifecycle.
- [x] Add architecture tests for provider-free read paths, dirty control-plane
  ownership, and broad runtime catch-up bans.
- [x] Update architecture, reliability, worker inventory, generated CLI help,
  and this spec/plan.
- [x] Run final targeted and broader verification.

## Verification Plan

- Targeted unit/integration suites for Token Radar projection, resolution
  refresh, market tick current, API read paths, WebSocket fan-out, wake waiter,
  and worker lifecycle.
- Architecture suites:
  `tests/architecture/test_worker_runtime_contracts.py`,
  `tests/architecture/test_api_read_paths_provider_free.py`, and projection
  idle-cost contracts.
- `ruff check` on changed source, tests, and docs-adjacent generated Python
  files.
- A broader pytest slice covering the touched worker/read-path contracts before
  handoff.

## Verification Results

- `uv run ruff check src/gmgn_twitter_intel tests` -> passed.
- Market tick/current/transaction suite -> `80 passed`.
- Resolution refresh, Token Radar, API/WebSocket, wake, and worker lifecycle
  suite -> `84 passed`.
- Architecture, CLI, and worker wiring suite -> `168 passed`.
