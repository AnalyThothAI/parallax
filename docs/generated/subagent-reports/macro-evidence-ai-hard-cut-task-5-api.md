# Subagent Report - 2026-07-23 Macro Evidence / Product-AI Hard Cut, Task 5 API

Mode: write-allowed

## Findings

- The Macro HTTP surface now contains exactly seven reads: six explicit persisted page routes plus the bounded series route. Each page handler calls only `repos.macro_intel.snapshot_page()` with its exact stable page key (`overview`, `cross_asset`, `rates_inflation`, `growth_labor`, `liquidity_funding`, or `credit`). Missing persisted pages fail closed with HTTP 503; no route rebuilds a page inline.
- The retired aggregate `/api/macro`, correlation route, module wildcard, currentness adapter, and all legacy regime/scenario/scorecard/module response models were deleted. Retired paths now return ordinary 404 responses.
- Every Macro page and every knowable nested evidence, conclusion, freshness, derivation, rule, metric, correlation, funding, curve, and credit shape uses `extra="forbid"` Pydantic models. Macro page shapes contain no `JsonObject`. The strict series point contract preserves source name, series key, unit, frequency, data quality, and whitelisted event metadata.
- News list/detail contracts expose only persisted source, story, classification, market-scope, token-lane, and fact-lane data. Signal query handling and all admission, agent brief/status, token-impact, macro-event-flow, eligibility, and compatibility response fields are gone.
- Search inspect and Token Case expose no brief or narrative-admission compatibility field. Their API composition no longer injects the now-unused Token Radar repository.
- Notifications expose their native persisted JSONB payload without a `news_high_signal` product-AI adapter. API integration coverage now uses only watched-account activity and watched-account token-alert rules.
- Status and Ops schemas no longer publish `agent_execution`; Ops config no longer publishes `llm_configured`.
- Frontend mounting now registers exactly `/macro`, `/macro/cross-asset`, `/macro/rates-inflation`, `/macro/growth-labor`, `/macro/liquidity-funding`, and `/macro/credit`. There is no Macro wildcard fallback, so retired and unknown Macro browser paths return 404.

## Changed Files

- `src/parallax/app/surfaces/api/app.py`
- `src/parallax/app/surfaces/api/routes_macro.py`
- `src/parallax/app/surfaces/api/routes_news.py`
- `src/parallax/app/surfaces/api/routes_notifications.py`
- `src/parallax/app/surfaces/api/routes_search.py`
- `src/parallax/app/surfaces/api/schemas.py`
- `tests/unit/test_api_macro_contract.py`
- `tests/unit/test_api_news_contract.py`
- `tests/unit/test_api_notifications_contract.py`
- `tests/unit/test_api_openapi_exact_contracts.py`
- `tests/unit/test_api_ops_contract.py`
- `tests/unit/domains/macro_intel/test_macro_currentness_payloads.py` (deleted)
- `tests/integration/test_api_http.py`
- `tests/integration/test_api_static.py`
- `tests/contract/test_openapi_drift.py`

## Verification

- `uv run pytest -q tests/unit/test_api_*.py -x`
  - `51 passed in 1.62s`
- After removing the final unused Search/Token repository injection:
  - `uv run pytest -q tests/unit/test_api_*.py tests/integration/test_api_http.py::test_api_exposes_recent_search_and_token_read_models tests/integration/test_api_http.py::test_api_token_case_returns_dossier_for_resolved_asset -x`
  - `53 passed in 22.57s`
- `uv run pytest -q tests/integration/test_api_http.py -x`
  - `42 passed in 283.87s`
- `uv run pytest -q tests/integration/test_api_static.py`
  - `2 passed in 9.39s`
- Fresh runtime OpenAPI inspection passed:
  - exact paths are `/api/macro/credit`, `/api/macro/cross-asset`, `/api/macro/growth-labor`, `/api/macro/liquidity-funding`, `/api/macro/overview`, `/api/macro/rates-inflation`, and `/api/macro/series`;
  - `AgentExecutionStatusData`, `NewsSignalEnvelope`, `NarrativeAdmissionData`, and `OpsAgentExecutionData` are absent.
- Scoped Ruff passed: `All checks passed!`
- Scoped `git diff --check` passed.

## Remaining Contract Step

`tests/contract/test_openapi_drift.py` currently reports `2 failed, 2 passed` for one expected ownership-bound reason: the committed `docs/generated/openapi.json` and `web/src/lib/types/openapi.ts` have not yet been regenerated from the now-stable runtime schema. The failing checks are the JSON byte-drift check and the negative retired-product-AI check against those stale committed artifacts. Runtime OpenAPI itself is clean. Task 6/root must run the canonical contract generator after the frontend consumes the final schema; this API subtask intentionally did not edit generated docs or `web/`.

## Scope Adherence

All production edits are under the assigned API surface. Test edits are limited to the assigned API/static/contract boundaries. No Macro service, repository, migration, config, CLI, frontend, or canonical documentation file was edited by this subtask. This report is the only generated documentation addition.
