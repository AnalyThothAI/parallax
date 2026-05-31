# Search Intel Page Verification

**Date:** 2026-05-12  
**Owning spec:** `docs/superpowers/specs/completed/2026-05-12-search-intel-page-kiss-cn.md`  
**Owning plan:** `docs/superpowers/plans/completed/2026-05-12-search-intel-page-plan-cn.md`  
**Worktree:** `.worktrees/search-intel-page/`  
**Branch:** `codex/search-intel-page`

## Spec Compliance

| Acceptance point | Status | Evidence |
|---|---:|---|
| Search is a manual route-backed second-level page, not a left-rail view. | Pass | `web/src/features/live/useLiveSelection.ts` routes submit to `/search?q=...&window=...&scope=...`; `/search` uses `search-focus-mode`. |
| Old search drawer/local token matching is hard-cut. | Pass | Removed `SearchQueryDrawer`, `searchIntent`, `submittedSearch`, and the old `/api/search` infinite query from live data. |
| Token result shows resolver, 24h timeline, 24h Twitter rows, market anchor overlay, and Agent Brief. | Pass | `SearchInspectService` composes search, timeline, posts, radar, and deterministic brief; `SearchIntelPage` renders timeline/table/brief. |
| Keyword result shows 24h Twitter rows and Agent summary without forcing token selection. | Pass | `SearchInspectService` returns `topic_result`; App and page tests cover text query route. |
| Agent design includes 项目总结, 传播, 多空观点. | Pass | `SearchAgentBrief` renders 项目总结, 传播, 多头观点, 空头观点; unit tests assert these sections. |
| Market data is honest about current capability. | Pass | `market_overlay.price_series_type` is `anchor_line`; no fake OHLC/K-line endpoint or chart library added. |

## Red/Green Evidence

- `uv run pytest tests/unit/test_search_service.py -q`
  - Red before implementation: failed on missing `window` / `since_ms` behavior.
  - Green after implementation: `10 passed`.
- `uv run pytest tests/unit/test_search_agent_brief.py -q`
  - Red before implementation: import error.
  - Green after implementation: `2 passed`.
- `uv run pytest tests/unit/test_search_inspect_service.py -q`
  - Red before implementation: import error.
  - Green after implementation: `4 passed`.
- `npm run test -- searchRouteState`
  - Red before implementation: missing module.
  - Green after implementation: `3 passed`.
- `npm run test -- SearchAgentBrief`
  - Red before implementation: missing component.
  - Green after implementation: `1 passed`.
- `npm run test -- SearchIntelPage.routing`
  - Red before implementation: missing route/component.
  - Green after implementation: passed.

## Commands

```text
$ uv run ruff check src/parallax/domains/token_intel/read_models/search_agent_brief.py src/parallax/domains/token_intel/read_models/search_inspect_service.py src/parallax/domains/token_intel/read_models/search_service.py src/parallax/domains/token_intel/queries/search_events_query.py src/parallax/app/surfaces/api/http.py tests/unit/test_search_service.py tests/unit/test_search_agent_brief.py tests/unit/test_search_inspect_service.py tests/integration/test_api_http.py
All checks passed!
```

```text
$ uv run pytest tests/unit/test_search_service.py tests/unit/test_search_agent_brief.py tests/unit/test_search_inspect_service.py -q
16 passed in 0.34s
```

```text
$ uv run pytest tests/integration/test_api_http.py::test_api_exposes_recent_search_and_signal_read_models -q
1 passed in 24.00s
```

```text
$ npm run test -- searchRouteState SearchAgentBrief SearchIntelPage.routing TokenTargetPage.routing App.test
Test Files  5 passed (5)
Tests  62 passed (62)
```

```text
$ make contract-check
tests/contract/test_openapi_drift.py .. [100%]
2 passed in 3.54s
```

```text
$ npm run build
vite v8.0.10 building client environment for production...
dist/index.html                   0.45 kB
dist/assets/index-f471wIdQ.css   69.46 kB
dist/assets/index-BQP_KmFc.js   428.23 kB
✓ built in 1.10s
```

```text
$ make check
Python ruff, ruff format, mypy: passed.
Web typecheck, lint, format: passed.
Unit/architecture/contract pytest: 472 passed, 6 skipped.
compileall: passed.
```

```text
$ make check-all
make check: passed.
test-integration: 173 passed, 9 skipped in 1492.70s.
test-e2e: 4 passed in 44.40s.
coverage: 727 passed, 14 skipped in 1218.19s.
Total coverage: 81.81% (required 80.0%).
```

Note: the first `make check-all` attempt stopped at `test_make_docs_generated_clean_diff` because `docs/generated/openapi.json` was correctly regenerated but not staged; after staging the generated OpenAPI artifact, the targeted docs-generated test passed and the full `make check-all` run exited 0.

## Manual UI Verification

Opened a local built `web/dist` smoke server with mocked `/api/bootstrap` and `/api/search/inspect`, then navigated with Playwright to:

```text
http://127.0.0.1:5174/search?q=%24RKC&window=24h&scope=all
```

Desktop viewport `1440x1100`:

- Page rendered `Search Intel`, `24h Social x Market Timeline`, `24h Twitter Results`, and `Agent Brief`.
- Agent sections rendered: `项目总结`, `传播`, `多头观点`, `空头观点`.
- Twitter table rendered 3 rows.
- `.desktop-side-rail`, `.detail-task-panel`, and `.responsive-control-panel` were `display: none`.
- No horizontal overflow.

Mobile viewport `390x900`:

- Search page, Twitter results, and all Agent sections rendered.
- `.search-main-grid` collapsed to one column.
- No horizontal overflow.

## Diff Summary

- Backend: added `/api/search/inspect`, window-scoped `/api/search`, deterministic `search_agent_brief_v1`, and `SearchInspectService`.
- Frontend: added `/search` route, route-state parsing, inspect query hook, dense timeline/table/Agent components, and search focus mode.
- Hard cut: removed old query drawer, local search-token matching, old submitted-search store state, and the old live-data `/api/search` query.
- Docs/contracts: updated `CONTRACTS.md`, `FRONTEND.md`, OpenAPI generated files, and moved spec/plan to completed.

## Risks And Follow-Ups

- Market overlay remains anchor-only, not OHLC/K-line. Real K-line requires a separate market-series endpoint.
- Agent Brief is deterministic and evidence-grounded; LLM synthesis can be added later behind a typed schema and fallback path.
- The existing local Docker service on `127.0.0.1:8765` was running an older API during browser smoke, so UI smoke used a built static server plus mocked inspect payload instead of the live service.
