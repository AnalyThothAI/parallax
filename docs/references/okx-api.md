# OKX & GMGN OpenAPI — Endpoint Notes

**Source of truth:** `src/gmgn_twitter_intel/market/`
**Cited by:** `docs/ARCHITECTURE.md` (cross-cutting `market/` module), `docs/CONTRACTS.md` (optional config groups).

## Scope

This file is a router into the market clients. Detailed endpoint paths, query parameters, and response shapes live in the client modules below; this reference file gives specs a stable citable path.

## Source files

| Client | File |
|--------|------|
| OKX CEX REST client | `src/gmgn_twitter_intel/market/okx_cex_client.py` |
| OKX DEX REST client | `src/gmgn_twitter_intel/market/okx_dex_client.py` |
| GMGN OpenAPI REST client | `src/gmgn_twitter_intel/market/gmgn_openapi_client.py` |

## Operational notes

- Rate-limit handling and retry policy live in each client's `_request` / `_call` helper.
- Authentication credentials come from the optional config groups in `docs/CONTRACTS.md`; absence of credentials disables the corresponding pipeline cleanly (no crash).
