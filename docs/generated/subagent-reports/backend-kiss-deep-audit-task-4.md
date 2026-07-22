# Provider adapter and PostgreSQL execution-plane KISS audit

Mode: read-only

## Findings

- CUT: remove the fake `active` branch from terminal-history queries; the CLI already routes active requests to queue health.
- CUT: remove the unused PostgreSQL-audit `token_factor_version` binding; none of the current hot queries consumes it.
- CUT: remove the provider Candle protocol/wiring/adapter surface. The call graph has no worker, service, HTTP, WebSocket, CLI, or CQRS writer consumer; the separately retained `MarketCandlesService` currently returns an explicit unsupported status and does not call providers.
- CUT: remove the Binance USD-M `premium_index`, `open_interest_hist`, and simple `ticker` endpoints. Current production uses `exchange_info`, `ticker_24hr`, and candles are removed with the provider Candle surface.
- CUT: remove OpenNews URL-query policy fallback after a redacted structural check confirmed the current operator config uses typed `fetch_policy_json` and no `engine.*`, `coins`, or `hasCoin` URL query.
- CUT: use the generic RSS-like provider for CryptoPanic; delete its duplicate wrapper, the unused registry enumeration method, and unused `FeedClient` context-manager methods.
- KEEP: PostgreSQL write/CAS/JSON-safety/client/migration boundaries, the terminal ledger, and distinct provider-unavailable semantics.
- KEEP: current terminal-reason classifiers. Deleting a small open classifier does not reduce a state machine and could degrade future operator triage; historical migrations remain immutable either way.
- DEFER: OKX external-payload aliases and provider-local retry policy until sealed live frames and retry/idempotency evidence are available.
- DEFER: PostgreSQL indexes, tables, and hot-query shapes until current relation/index/query-plan evidence is collected.

## Scope Adherence

Owned scope: pass

Conflict set: pass

The audit was read-only and did not edit migrations `0185`-`0187`, `.agents/skills/**`, or `web/**`.

## Changed Files

None.

## Required Reading Evidence

Task classification: provider adapter and PostgreSQL execution-plane risk radar.

Read `AGENTS.md`, `docs/agent-playbook/task-reading-matrix.md`, `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/SECURITY.md`, `docs/RELIABILITY.md`, `docs/references/POSTGRES_PERFORMANCE.md`, the active feature records, and the existing implementation audit.

## Verification Evidence

```text
$ uv run pytest -q tests/architecture/test_kiss_runtime_invariants.py
............                                                             [100%]
12 passed in 2.37s
exit code: 0

$ uv run pytest -q tests/unit/test_queue_terminal.py tests/integration/test_postgres_audit.py tests/unit/test_binance_usdm_futures_client.py tests/unit/test_okx_clients.py tests/unit/integrations/news_feeds/test_opennews_client.py
.....................................................................    [100%]
69 passed in 22.08s
exit code: 0
```

## Remaining Risks

- Candle removal must be atomic across protocol, wiring, capabilities, adapters, and tests.
- External provider payload normalization is not presumed to be compatibility glue.
- Real PostgreSQL and provider E2E remain separate evidence lanes.
