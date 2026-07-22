# Provider and PostgreSQL private-surface hard cut

Mode: write-allowed

## Findings

- Removed the unused Candle protocol/capability/wiring and provider client branches as one atomic surface.
- Removed three unused Binance endpoints, OpenNews URL-query policy fallback, duplicate CryptoPanic wrapper, and unused feed/registry helpers.
- Restricted terminal inspection to unresolved terminal evidence and removed an unused PostgreSQL-audit binding.
- Preserved external payload aliases, provider retries/unavailable semantics, terminal classification, and historical migrations.

## Scope Adherence

Owned scope: pass

Conflict set: pass

## Changed Files

- `src/parallax/app/runtime/provider_wiring/asset_market.py`
- `src/parallax/app/runtime/provider_wiring/binance.py`
- `src/parallax/app/runtime/provider_wiring/gmgn.py`
- `src/parallax/app/runtime/provider_wiring/types.py`
- `src/parallax/app/surfaces/cli/commands/db.py`
- `src/parallax/app/surfaces/cli/commands/queue_ops.py`
- `src/parallax/domains/asset_market/providers.py`
- `src/parallax/integrations/binance/usdm_futures_client.py`
- `src/parallax/integrations/gmgn/openapi_client.py`
- `src/parallax/integrations/gmgn/openapi_gateway.py`
- `src/parallax/integrations/news_feeds/feed_client.py`
- `src/parallax/integrations/news_feeds/opennews_client.py`
- `src/parallax/integrations/news_feeds/provider_registry.py`
- `src/parallax/integrations/okx/dex_client.py`
- `src/parallax/integrations/okx/models.py`
- `src/parallax/platform/db/postgres_audit.py`
- `src/parallax/platform/db/queue_terminal.py`
- `tests/integration/test_postgres_audit.py`
- `tests/unit/integrations/news_feeds/test_opennews_client.py`
- `tests/unit/integrations/news_feeds/test_provider_registry.py`
- `tests/unit/test_binance_usdm_futures_client.py`
- `tests/unit/test_gmgn_openapi_client.py`
- `tests/unit/test_okx_clients.py`
- `tests/unit/test_provider_capabilities.py`
- `tests/unit/test_providers_wiring.py`
- `tests/unit/test_queue_terminal.py`

## Required Reading Evidence

Task classification: provider-adapter and PostgreSQL-private implementation.

Read `AGENTS.md`, `docs/agent-playbook/task-reading-matrix.md`, the provider/DB audit report, and current consumer searches.

## Verification Evidence

```text
$ uv run pytest -q tests/unit/test_provider_capabilities.py tests/unit/test_providers_wiring.py tests/unit/test_binance_usdm_futures_client.py tests/unit/test_okx_clients.py tests/unit/integrations/news_feeds tests/unit/test_queue_terminal.py tests/integration/test_postgres_audit.py
........................................................................ [ 71%]
.............................                                            [100%]
101 passed in 26.69s
exit code: 0
```

## Remaining Risks

- Live-provider behavior remains a separate E2E evidence lane; no live compatibility claim is made from unit fixtures.
