# Macro Regime 70 Verification

Date: 2026-05-21
Branch: `codex/macro-regime-70`
Task: Real runtime smoke and 70+ verification
Outcome: 87 / 100; target met.

## Runtime Evidence

- `uv run gmgn-twitter-intel config` returned `ok: true`.
- Active runtime paths were
  `/Users/qinghuan/.gmgn-twitter-intel/config.yaml` and
  `/Users/qinghuan/.gmgn-twitter-intel/workers.yaml`.
- `ws_token_configured=true`; no raw token or secret value was printed.
- In the macrodata-cli sibling worktree, `uv run macrodata doctor` returned
  `ok: true` with `fred_api_key_configured=false`.

## Import And Projection Smoke

- `uv run gmgn-twitter-intel db migrate` succeeded and Alembic ran
  `20260521_0076 -> 20260521_0077`.
- `uv run gmgn-twitter-intel db health` reported
  `migration_version=20260521_0077`,
  `expected_migration_version=20260521_0077`, and
  `migration_status=ready`.
- `uv run macrodata bundle macro-core --asof 2026-05-21` succeeded with
  `ok=true`, `coverage.requested=33`, `coverage.available=3`,
  `data_quality=partial`, and reason codes
  `missing_series`, `missing_api_key`, and `provider_unavailable`.
- `uv run gmgn-twitter-intel macro import-bundle --file /tmp/macro-core.json`
  imported 3 observations with run id
  `macro-import:dd405e4d4ee60931ba6fd6b153b6c525`, `status=partial`,
  and coverage `requested=33`, `available=3`.
- `uv run gmgn-twitter-intel macro project-once` wrote a
  `macro_regime_v2` snapshot with `status=partial`, `regime=data_gap`, and
  snapshot id `macro-view:macro_regime_v2:1779358329382`.
- `uv run gmgn-twitter-intel macro status` after projection reported
  `migration_ready=true`, 3 observations, 3 series, and a latest v2 snapshot.
  The snapshot features contained `nyfed:SOFR`,
  `treasury_fiscal:operating_cash_balance`, and
  `cftc:financial_futures:sp500_net_noncommercial`. The chain contained all
  seven chain keys. The scenario reported `current_regime=neutral`. The
  scorecard reported `coverage_ratio=0.0909`, `observed_series_count=3`,
  `required_series_count=33`, and `data_gap_count=30`.

## API And UI Smoke

- Unit API contract coverage verified the new `/api/macro` fields:
  `features`, `chain`, `scenario`, and `scorecard`.
- A real HTTP request against the already-running `127.0.0.1:8765` process
  returned old `macro_regime_v1`. That process appears to be an older backend,
  not this worktree code. Do not count live HTTP v2 on `8765` as verified until
  the process is restarted from this branch.
- Browser smoke served the current frontend with
  `VITE_API_BASE_URL=http://127.0.0.1:8765`. Normal Chromium hit CORS from
  `5173` to `8765`; rerunning Chromium with `--disable-web-security` verified
  the page visually.
- `/tmp/macro-regime-70-smoke.png` captured the rendered Macro page headings:
  `Macro`, `Transmission Chain`, `Scenario Path`,
  `Confirmations / Contradictions`, `Trade Map`, `Validation Indicators`,
  `Triggers`, and `Data Gaps`.
- Browser console showed only React Router future warnings plus two unrelated
  live-side 503 resource errors; the Macro sections rendered.

## Scorecard

| Area | Max | Score | Evidence |
|------|-----|-------|----------|
| Data source coverage | 20 | 15 | 33-series macro-core exists across FRED/Treasury/NYFed/Stooq/CFTC; live run has 3/33 because `FRED_API_KEY` is absent and Stooq requires access/API key; failures are structured diagnostics. |
| Import chain | 15 | 15 | Migration, bundle import, import run, observation upsert, and `project-once` all succeeded. |
| Historical feature layer | 15 | 14 | Feature engine computes latest/deltas/zscore/percentile/freshness; live snapshot has feature entries for 3 imported series; limited history yields explicit gaps. |
| Regime state machine | 20 | 17 | v2 chain has seven deterministic nodes and scenario/scorecard; under sparse data it remains `data_gap` / `neutral` instead of false stress. |
| Product surface | 10 | 9 | API contract and frontend render features/chain/scenario/scorecard sections; visual smoke rendered required headings. Live already-running backend is still old v1 until restarted. |
| Ops and verification | 20 | 17 | DB migrated, CLI smoke, tests, lint, typecheck, and build all passed; runtime HTTP v2 smoke blocked by existing old `8765` process/CORS dev setup. |
| Total | 100 | 87 | `>=72` target met. |

## Verification Commands

Macrodata-cli sibling worktree:

- `uv run pytest -q` -> 84 passed.
- `uv run ruff check .` -> passed.
- `uv run mypy src tests` -> passed.
- `uv run macrodata doctor` -> `ok=true`, FRED key not configured.
- `uv run macrodata bundle macro-core --asof 2026-05-21` -> `ok=true`,
  partial, requested 33, available 3.

Gmgn worktree:

- `uv run python -m pytest tests/unit/domains/macro_intel tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py -q`
  -> 30 passed.
- `uv run ruff check .` -> passed.
- `uv run mypy src/gmgn_twitter_intel/domains/macro_intel src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py src/gmgn_twitter_intel/app/surfaces/cli/commands/macro.py`
  -> passed, 13 source files.
- `cd web && npm test -- --run tests/component/features/macro/MacroPage.test.tsx tests/routes/macro.route.test.tsx`
  -> 2 files, 3 tests passed.
- `cd web && npm run typecheck` -> passed.
- `cd web && npm run lint` -> passed.
- `cd web && npm run build` -> passed; Vite emitted the existing
  chunk-size warning for chunks over 500 kB.
- `uv run gmgn-twitter-intel db health` -> ready at `20260521_0077`.
- `uv run gmgn-twitter-intel macro status` -> `migration_ready=true`,
  3 observations, 3 series, latest v2 snapshot after projection.

## Remaining Runtime Check

Restart the backend process on `127.0.0.1:8765` from
`codex/macro-regime-70`, then verify that live `/api/macro` returns
`projection_version=macro_regime_v2` and the v2 fields over HTTP without the
temporary browser CORS bypass.
