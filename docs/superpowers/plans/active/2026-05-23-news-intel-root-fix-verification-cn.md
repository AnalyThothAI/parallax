# News Intel Root Fix Verification

**Date:** 2026-05-23 08:46:54 UTC  
**Branch:** `codex/news-intel-root-fix`  
**Worktree:** `/Users/qinghuan/Documents/code/gmgn-twitter-intel/.worktrees/news-intel-root-fix`

## Result

News root-fix implementation is built and running in Docker from the current worktree image. The News read model is migrated to `20260523_0086`, indexed for the canonical page filters, and `/news` renders live projected rows.

## Docker Rebuild Finding

`docker compose up -d --build` first produced an image that did not contain `20260523_0086_news_page_filter_indexes.py`; the container still had an older migration file from another branch. A forced `docker compose build --no-cache migrate app` exposed the reproducible root cause: the Python dependency stage could not build `quickjs==1.19.4` because `gcc` was missing.

Fix applied:

- `Dockerfile` now installs `build-essential git` in the `python-deps` stage.
- Final runtime image still copies only `/app` from the dependency stage; build tools are not installed by the final stage.
- `docker compose build --no-cache migrate app` passed after the fix.

## Runtime Configuration

`uv run gmgn-twitter-intel config` confirmed:

- `config_path`: `/Users/qinghuan/.gmgn-twitter-intel/config.yaml`
- `workers_config_path`: `/Users/qinghuan/.gmgn-twitter-intel/workers.yaml`
- `api.ws_token_configured`: `true`

No secret values were printed or copied.

## Database And Migration

`docker compose logs migrate`:

- `{"ok":true,"data":{"migration":"head"}}`

`alembic_version`:

- `20260523_0086`

`news_page_rows` filter indexes present:

- `idx_news_page_rows_content_tags_gin`
- `idx_news_page_rows_coverage_tags_gin`
- `idx_news_page_rows_decision_class_time`
- `idx_news_page_rows_direction_time`
- `idx_news_page_rows_provider_type_time`
- `idx_news_page_rows_source_role_time`
- `idx_news_page_rows_trust_tier_time`

## Live News Data

Relation counts after restart:

- `news_sources`: 10
- `news_fetch_runs`: 7664
- `news_provider_items`: 4667
- `news_items`: 4667
- `news_page_rows`: 4667
- `news_source_quality_rows`: 20

Newest projection:

- newest `news_page_rows.computed_at_ms`: `2026-05-23 08:46:04.76+00`
- newest item timestamp: `2026-05-23 06:55:08+00`

Content classes in `news_page_rows`:

- `low_signal`: 4377
- `crypto_market`: 117
- `regulation`: 39
- `equity_earnings`: 27
- `rates_fed`: 19
- `energy_geopolitics`: 16
- `etf_fund_flow`: 15
- `ai_semiconductors`: 12
- `exchange_listing`: 12
- `security_hack`: 12
- `market_structure`: 7
- `protocol_development`: 6
- `analyst_rating`: 5
- `macro_policy`: 3

Source classification in `news_page_rows`:

- `rss / aggregator / standard / degraded`: 3883
- `rss / specialist_media / standard / watch`: 467
- `rss / specialist_media / high / watch`: 228
- `rss / specialist_media / standard / degraded`: 69
- `rss / specialist_media / high / degraded`: 20

Latest fetch runs show live RSS polling is active. Examples:

- `yahoo-finance`: success, 43 fetched, 1 inserted, 42 duplicate
- `cnbc-economy`: success, 30 fetched, 30 duplicate
- `coindesk`: success, 25 fetched, 25 duplicate
- `decrypt`: success, 37 fetched, 37 duplicate

## HTTP And Frontend

Docker status:

- `gmgn-twitter-intel-app-1`: running, healthy
- `gmgn-twitter-intel-postgres-1`: running, healthy

Final `/healthz` sample after startup:

- 5/5 returned `200`
- observed times: `0.293s`, `0.025s`, `3.778s`, `0.019s`, `0.027s`

Unauthenticated `/api/news/sources/status`:

- returned `401`, expected because API token is required.
- The shell did not have `GMGN_API_TOKEN`; no token was read from config.

Playwright smoke test:

- Opened `http://127.0.0.1:8765/news`.
- Page title: `GMGN Twitter Intel`.
- News page rendered live feed summary and `100/100` loaded rows.
- Rows showed projected agent states such as `ready`, `failed`, `insufficient`; directions such as `bullish`, `bearish`, `neutral`; and decisions such as `driver`, `watch`, `context`, `discard`.

## Residual Non-News Runtime Risk

During app startup and early worker load, `/healthz` can still be slow or briefly time out before the service settles. After startup it stabilized and Docker health became healthy.

`readyz` can still time out under full runtime load, and app logs include unrelated token radar errors:

- `relation "token_radar_rows" does not exist`

This is outside the News chain and should be handled by a separate Token Radar storage/migration plan. It does not block the News read model verification above.
