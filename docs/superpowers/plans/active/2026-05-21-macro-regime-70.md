# Macro Regime 70 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing macro scaffold into a 70+ macro regime system with public data bundles, importable observations, historical features, deterministic state-machine output, and an operator/agent surface.

**Architecture:** Keep public provider access in `macrodata-cli`; import normalized envelopes into `parallax` as facts; compute feature and regime snapshots in `macro_intel`; expose only deterministic JSON through `/api/macro` and `/macro`. This plan intentionally avoids paid institutional feeds and treats optional proxy gaps as explicit state.

**Tech Stack:** Python 3.13, Typer, FastAPI, psycopg/JSONB, Alembic, WorkerBase, Pydantic, React + React Query + TypeScript, Playwright/Vitest.

---

**Status**: Draft
**Date**: 2026-05-21
**Owning spec**: `docs/superpowers/specs/active/2026-05-21-macro-regime-70.md`
**Repos**:
- `/Users/qinghuan/Documents/code/macrodata-cli`
- `/Users/qinghuan/Documents/code/parallax`

## Pre-flight

- [ ] Create or select an isolated worktree for `parallax`:

  ```bash
  cd /Users/qinghuan/Documents/code/parallax
  git worktree add .worktrees/macro-regime-70 -b codex/macro-regime-70 main
  cd .worktrees/macro-regime-70
  git status --short --branch
  ```

  Expected: branch is `codex/macro-regime-70` and worktree is clean.

- [ ] Create or select an isolated worktree for `macrodata-cli`:

  ```bash
  cd /Users/qinghuan/Documents/code/macrodata-cli
  git worktree add .worktrees/macro-core-bundle -b codex/macro-core-bundle main
  cd .worktrees/macro-core-bundle
  git status --short --branch
  ```

  Expected: branch is `codex/macro-core-bundle` and worktree is clean.

- [ ] Confirm runtime config paths before any real-data operation:

  ```bash
  cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-regime-70
  uv run parallax config
  ```

  Expected: `config_path` and `workers_config_path` point at
  `~/.parallax/`. Do not print credential values.

## File-level Design

### `macrodata-cli`

- Modify `src/macrodata/catalog/entries.py`.
  - Add catalog entries for the expanded `macro-core` bundle:
    `fred:DGS5`, `fred:T10Y3M`, `fred:DFII10`, `fred:T5YIFR`,
    `fred:EFFR`, `fred:SP500`, `fred:DCOILWTICO`, and broad-dollar proxy
    `fred:DTWEXBGS`.
  - Add Stooq catalog entries for ETF proxies:
    `stooq:spy.us`, `stooq:qqq.us`, `stooq:iwm.us`, `stooq:tlt.us`,
    `stooq:hyg.us`, `stooq:lqd.us`, `stooq:gld.us`, `stooq:uso.us`.
  - Add a CFTC positioning proxy catalog entry:
    `cftc:financial_futures:sp500_net_noncommercial`.

- Create `src/macrodata/providers/stooq.py`.
  - Fetch daily historical CSV from Stooq for one symbol.
  - Normalize close price into `MacroObservation`.
  - Preserve provider provenance and parse errors.

- Create `src/macrodata/providers/cftc.py`.
  - Fetch or load one public CFTC COT financial-futures proxy.
  - Normalize one weekly net-position observation into `MacroObservation`.
  - If the exact public source is unavailable, return structured
    `MacrodataError(code="provider_unavailable", provider="cftc")`.

- Modify `src/macrodata/app/runtime.py`.
  - Register `StooqProvider` and `CftcProvider`.

- Modify `src/macrodata/app/services.py`.
  - Add `MACRO_CORE`.
  - Add `bundle("macro-core", asof=...)`.
  - Add `bundle_history("macro-core", start=..., end=...)`.

- Modify `src/macrodata/surfaces/cli.py`.
  - Add `macrodata bundle macro-core --asof`.
  - Add `macrodata bundle history macro-core --start --end`.

- Modify `src/macrodata/surfaces/mcp_server.py`.
  - Add `bundle_macro_core`.
  - Add `bundle_macro_core_history`.

- Tests:
  - `tests/provider/test_stooq_provider.py`
  - `tests/provider/test_cftc_provider.py`
  - `tests/unit/test_bundles.py`
  - `tests/cli/test_bundle_commands.py`
  - `tests/mcp/test_mcp_server.py`

### `parallax`

- Create migration `src/parallax/platform/db/alembic/versions/20260521_0077_macro_regime_70.py`.
  - Add `macro_import_runs`.
  - Add optional JSONB columns to `macro_view_snapshots`:
    `features_json`, `chain_json`, `scenario_json`, `scorecard_json`.

- Modify `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`.
  - Add `insert_import_run`.
  - Add `latest_import_run`.
  - Add `observations_for_series`.
  - Update `insert_snapshot` and `latest_snapshot` for new JSONB columns.

- Create `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py`.
  - Parse `macrodata-cli` result envelopes.
  - Convert each observation into repository shape.
  - Upsert observations idempotently.
  - Record import diagnostics.

- Create `src/parallax/domains/macro_intel/services/macro_feature_engine.py`.
  - Build latest, freshness, delta, z-score, percentile, and spread features
    from observation history.

- Modify `src/parallax/domains/macro_intel/services/macro_regime_engine.py`.
  - Keep `build_macro_view_snapshot` as public entrypoint.
  - Internally call feature engine and emit:
    `features_json`, `chain_json`, `scenario_json`, `scorecard_json`.
  - Add version bump in `_constants.py`, for example
    `MACRO_VIEW_PROJECTION_VERSION = "macro_regime_v2"`.

- Create `src/parallax/domains/macro_intel/services/macro_scenario_engine.py`.
  - Convert panel and chain state into deterministic scenario/trade-map JSON.

- Modify `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py`.
  - Read bounded history instead of latest-only rows.

- Add CLI:
  - Modify `src/parallax/app/surfaces/cli/parser.py`.
  - Create `src/parallax/app/surfaces/cli/commands/macro.py`.
  - Wire in `src/parallax/app/surfaces/cli/main.py`.

- Modify API and frontend:
  - `src/parallax/app/surfaces/api/routes_macro.py`
  - `web/src/lib/types/frontend-contracts.ts`
  - `web/src/features/macro/MacroPage.tsx`
  - `web/src/features/macro/macro.css`
  - `web/tests/component/features/macro/MacroPage.test.tsx`

- Docs:
  - `docs/CONTRACTS.md`
  - `docs/WORKERS.md`
  - `docs/ARCHITECTURE.md`
  - `src/parallax/domains/macro_intel/ARCHITECTURE.md`
  - `docs/superpowers/plans/active/2026-05-21-macro-regime-70-verification.md`

## Task 1: Expand `macrodata-cli` Catalog and Bundle Contracts

**Files:**
- Modify: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/catalog/entries.py`
- Modify: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`
- Modify: `/Users/qinghuan/Documents/code/macrodata-cli/docs/reference/catalog.md`
- Test: `/Users/qinghuan/Documents/code/macrodata-cli/tests/unit/test_catalog.py`
- Test: `/Users/qinghuan/Documents/code/macrodata-cli/tests/unit/test_bundles.py`

- [ ] **Step 1: Write catalog tests for new core series**

  Add a test that asserts the catalog contains representative series from all
  target categories:

  ```python
  def test_catalog_contains_macro_core_series() -> None:
      catalog = default_catalog()
      keys = {entry.series_key for entry in catalog.list_entries()}

      assert {
          "fred:DGS5",
          "fred:T10Y3M",
          "fred:DFII10",
          "fred:T5YIFR",
          "fred:EFFR",
          "fred:SP500",
          "fred:DCOILWTICO",
          "fred:DTWEXBGS",
          "stooq:spy.us",
          "stooq:hyg.us",
          "cftc:financial_futures:sp500_net_noncommercial",
      }.issubset(keys)
  ```

- [ ] **Step 2: Run test and confirm failure**

  ```bash
  cd /Users/qinghuan/Documents/code/macrodata-cli/.worktrees/macro-core-bundle
  uv run pytest tests/unit/test_catalog.py::test_catalog_contains_macro_core_series -q
  ```

  Expected: FAIL because the new entries do not exist yet.

- [ ] **Step 3: Add catalog entries**

  Add helper functions in `entries.py`:

  ```python
  def _stooq(symbol: str, name: str, description: str) -> SourceCatalogEntry:
      return SourceCatalogEntry(
          series_key=f"stooq:{symbol}",
          name=name,
          provider="stooq",
          dataset=symbol,
          description=description,
          unit="price",
          frequency="daily",
          latency_class="eod",
          requires_api_key=False,
          source_url=f"https://stooq.com/q/d/l/?s={symbol}&i=d",
          license_note="Stooq public data terms apply.",
      )

  def _cftc(dataset: str, name: str, description: str) -> SourceCatalogEntry:
      return SourceCatalogEntry(
          series_key=f"cftc:{dataset}",
          name=name,
          provider="cftc",
          dataset=dataset,
          description=description,
          unit="contracts",
          frequency="weekly",
          latency_class="weekly",
          requires_api_key=False,
          source_url="https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm",
          license_note="CFTC public data terms apply.",
      )
  ```

  Add the concrete FRED, Stooq, and CFTC entries listed in the file-level design.

- [ ] **Step 4: Add `MACRO_CORE` tests**

  In `tests/unit/test_bundles.py`, add:

  ```python
  def test_macro_core_bundle_contains_70_point_categories() -> None:
      assert "fred:WALCL" in MACRO_CORE
      assert "fred:DGS10" in MACRO_CORE
      assert "fred:IORB" in MACRO_CORE
      assert "nyfed:SOFR" in MACRO_CORE
      assert "fred:VIXCLS" in MACRO_CORE
      assert "fred:BAMLH0A0HYM2" in MACRO_CORE
      assert "stooq:spy.us" in MACRO_CORE
      assert "stooq:hyg.us" in MACRO_CORE
      assert "cftc:financial_futures:sp500_net_noncommercial" in MACRO_CORE
      assert len(MACRO_CORE) >= 20
  ```

- [ ] **Step 5: Implement `MACRO_CORE`**

  In `services.py`, define:

  ```python
  MACRO_CORE = [
      *LIQUIDITY_CORE,
      "fred:DGS2",
      "fred:DGS5",
      "fred:DGS10",
      "fred:DGS30",
      "fred:T10Y2Y",
      "fred:T10Y3M",
      "fred:DFII10",
      "fred:T10YIE",
      "fred:T5YIFR",
      "fred:DFEDTARU",
      "fred:DFEDTARL",
      "fred:EFFR",
      "fred:BAMLC0A0CM",
      "fred:BAMLH0A0HYM2",
      "fred:VIXCLS",
      "fred:SP500",
      "fred:DCOILWTICO",
      "fred:DTWEXBGS",
      "stooq:spy.us",
      "stooq:qqq.us",
      "stooq:iwm.us",
      "stooq:tlt.us",
      "stooq:hyg.us",
      "stooq:lqd.us",
      "stooq:gld.us",
      "stooq:uso.us",
      "cftc:financial_futures:sp500_net_noncommercial",
  ]
  ```

  Update `_bundle_series` so `bundle == "macro-core"` returns `MACRO_CORE`.

- [ ] **Step 6: Verify Task 1**

  ```bash
  uv run pytest tests/unit/test_catalog.py tests/unit/test_bundles.py -q
  uv run ruff check src/macrodata tests
  ```

- [ ] **Step 7: Commit Task 1**

  ```bash
  git add src/macrodata/catalog/entries.py src/macrodata/app/services.py docs/reference/catalog.md tests/unit/test_catalog.py tests/unit/test_bundles.py
  git commit -m "feat: define macro core data bundle"
  ```

## Task 2: Add Stooq and CFTC Public Proxy Providers

**Files:**
- Create: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/stooq.py`
- Create: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/cftc.py`
- Modify: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/runtime.py`
- Test: `/Users/qinghuan/Documents/code/macrodata-cli/tests/provider/test_stooq_provider.py`
- Test: `/Users/qinghuan/Documents/code/macrodata-cli/tests/provider/test_cftc_provider.py`

- [ ] **Step 1: Test Stooq provider parsing**

  Mock a CSV response:

  ```csv
  Date,Open,High,Low,Close,Volume
  2026-05-20,600.0,605.0,598.0,604.25,1000
  ```

  Assert `series_key == "stooq:spy.us"`, `value == 604.25`, `unit == "price"`,
  and `observed_at == "2026-05-20"`.

- [ ] **Step 2: Implement `StooqProvider`**

  The provider must support `get_range(dataset, start, end)` and
  `get_latest(dataset)`. Convert ISO dates to `YYYYMMDD` for Stooq params:

  ```python
  params = {"s": dataset, "i": "d", "d1": start.replace("-", ""), "d2": end.replace("-", "")}
  ```

  Parse the `Close` column as the observation value.

- [ ] **Step 3: Test CFTC provider degraded behavior**

  Add a test that a missing/unparseable CFTC response raises:

  ```python
  MacrodataError(code="provider_unavailable", provider="cftc", retryable=True)
  ```

  This makes positioning an explicit gap instead of fake neutrality.

- [ ] **Step 4: Implement CFTC-lite provider**

  Implement only `financial_futures:sp500_net_noncommercial` for the 70+
  milestone. If the public CSV schema changes, raise `provider_parse_error`.
  If the endpoint is unavailable, raise `provider_unavailable`.

- [ ] **Step 5: Register providers**

  In `runtime.py`, add provider instances:

  ```python
  providers={
      "fred": FredSeriesProvider(...),
      "nyfed": NyFedMarketsProvider(...),
      "treasury_fiscal": TreasuryFiscalProvider(...),
      "stooq": StooqProvider(http_client=http_client),
      "cftc": CftcProvider(http_client=http_client),
  }
  ```

- [ ] **Step 6: Verify Task 2**

  ```bash
  uv run pytest tests/provider/test_stooq_provider.py tests/provider/test_cftc_provider.py tests/unit/test_runtime.py -q
  uv run ruff check src/macrodata tests
  uv run mypy src tests
  ```

- [ ] **Step 7: Commit Task 2**

  ```bash
  git add src/macrodata/providers/stooq.py src/macrodata/providers/cftc.py src/macrodata/app/runtime.py tests/provider/test_stooq_provider.py tests/provider/test_cftc_provider.py tests/unit/test_runtime.py
  git commit -m "feat: add macro proxy data providers"
  ```

## Task 3: Add Macro Bundle CLI, History, and MCP Tools

**Files:**
- Modify: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`
- Modify: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/surfaces/cli.py`
- Modify: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/surfaces/mcp_server.py`
- Modify: `/Users/qinghuan/Documents/code/macrodata-cli/docs/reference/mcp-tools.md`
- Test: `/Users/qinghuan/Documents/code/macrodata-cli/tests/cli/test_bundle_commands.py`
- Test: `/Users/qinghuan/Documents/code/macrodata-cli/tests/mcp/test_mcp_server.py`

- [ ] **Step 1: Test `macrodata bundle macro-core`**

  Add a CLI test asserting:

  ```python
  result = CliRunner().invoke(app, ["bundle", "macro-core", "--asof", "2026-05-21", "--fred-api-key", "test-key"])
  payload = json.loads(result.stdout)
  snapshot = payload["data"]["snapshot"]
  assert snapshot["bundle"] == "macro-core"
  assert snapshot["coverage"]["requested"] >= 20
  assert "series_errors" in snapshot
  ```

- [ ] **Step 2: Test history bundle command**

  Add a CLI test for:

  ```bash
  macrodata bundle history macro-core --start 2026-05-01 --end 2026-05-21
  ```

  Expected payload shape:

  ```json
  {
    "snapshot": {
      "bundle": "macro-core",
      "observations": [],
      "coverage": {"requested": 0, "available": 0},
      "missing_series": [],
      "series_errors": []
    }
  }
  ```

  The exact counts depend on mocked providers; tests should assert shape and
  requested series coverage.

- [ ] **Step 3: Implement `bundle_history`**

  Add a `MacrodataService.bundle_history(bundle, start, end)` method that loops
  through `_bundle_series(bundle)` and calls `fetch_series` for each key. Reuse
  the same partial diagnostics logic as `bundle`.

- [ ] **Step 4: Wire CLI**

  Extend the existing `bundle` command parser so:

  ```bash
  uv run macrodata bundle macro-core --asof 2026-05-21
  uv run macrodata bundle history macro-core --start 2026-05-01 --end 2026-05-21
  ```

  both emit one JSON result envelope.

- [ ] **Step 5: Wire MCP**

  Add tools:

  ```python
  def bundle_macro_core(asof: str) -> dict[str, Any]:
      return _bundle_tool(bundle_name="macro-core", command="bundle.macro-core", asof=asof)

  def bundle_macro_core_history(start: str, end: str) -> dict[str, Any]:
      ...
  ```

- [ ] **Step 6: Verify Task 3**

  ```bash
  uv run pytest tests/cli/test_bundle_commands.py tests/mcp/test_mcp_server.py -q
  uv run macrodata doctor
  uv run macrodata bundle macro-core --asof 2026-05-21
  ```

  Expected without `FRED_API_KEY`: command exits 0 with partial diagnostics and
  no secret values.

- [ ] **Step 7: Commit Task 3**

  ```bash
  git add src/macrodata/app/services.py src/macrodata/surfaces/cli.py src/macrodata/surfaces/mcp_server.py docs/reference/mcp-tools.md tests/cli/test_bundle_commands.py tests/mcp/test_mcp_server.py
  git commit -m "feat: expose macro core bundles"
  ```

## Task 4: Add GMGN Macro Import Storage and CLI

**Files:**
- Create: `src/parallax/platform/db/alembic/versions/20260521_0077_macro_regime_70.py`
- Modify: `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
- Create: `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py`
- Create: `src/parallax/app/surfaces/cli/commands/macro.py`
- Modify: `src/parallax/app/surfaces/cli/parser.py`
- Modify: `src/parallax/app/surfaces/cli/main.py`
- Test: `tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py`
- Test: `tests/unit/test_cli_macro_commands.py`

- [ ] **Step 1: Write importer unit test**

  Use a representative `macrodata-cli` envelope:

  ```python
  ENVELOPE = {
      "ok": True,
      "command": "bundle.macro-core",
      "data": {
          "snapshot": {
              "bundle": "macro-core",
              "asof": "2026-05-21",
              "observations": [
                  {
                      "series_key": "nyfed:SOFR",
                      "provider": "nyfed",
                      "dataset": "SOFR",
                      "observed_at": "2026-05-19",
                      "value": 3.51,
                      "unit": "percent",
                      "frequency": "daily",
                      "source_ts": "2026-05-19",
                      "data_quality": "ok",
                      "provenance": [{"provider": "nyfed", "source_url": "https://markets.newyorkfed.org"}],
                  }
              ],
              "coverage": {"requested": 20, "available": 1},
              "missing_series": ["fred:WALCL"],
              "series_errors": [{"series_key": "fred:WALCL", "provider": "fred", "code": "missing_api_key"}],
              "source_chain": ["nyfed"],
              "data_quality": "partial",
              "reason_codes": ["missing_series", "missing_api_key"],
          }
      },
  }
  ```

  Assert the importer upserts one observation and records one import run.

- [ ] **Step 2: Add migration**

  Create `macro_import_runs`:

  ```sql
  CREATE TABLE IF NOT EXISTS macro_import_runs (
    run_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    bundle_name TEXT NOT NULL,
    asof_date DATE,
    status TEXT NOT NULL,
    observations_count INTEGER NOT NULL DEFAULT 0,
    coverage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    missing_series_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    series_errors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at_ms BIGINT NOT NULL,
    completed_at_ms BIGINT NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_macro_import_runs_latest
    ON macro_import_runs(completed_at_ms DESC);
  ```

  Add JSONB columns:

  ```sql
  ALTER TABLE macro_view_snapshots ADD COLUMN IF NOT EXISTS features_json JSONB NOT NULL DEFAULT '{}'::jsonb;
  ALTER TABLE macro_view_snapshots ADD COLUMN IF NOT EXISTS chain_json JSONB NOT NULL DEFAULT '{}'::jsonb;
  ALTER TABLE macro_view_snapshots ADD COLUMN IF NOT EXISTS scenario_json JSONB NOT NULL DEFAULT '{}'::jsonb;
  ALTER TABLE macro_view_snapshots ADD COLUMN IF NOT EXISTS scorecard_json JSONB NOT NULL DEFAULT '{}'::jsonb;
  ```

- [ ] **Step 3: Implement importer service**

  Public function:

  ```python
  def import_macrodata_bundle(envelope: Mapping[str, Any], *, repos: RepositorySession, now_ms: int) -> dict[str, Any]:
      ...
  ```

  Map `MacroObservation.value` to `value_numeric` only when it is numeric. Store
  the original observation under `raw_payload_json`.

- [ ] **Step 4: Implement CLI commands**

  Add parser commands:

  ```text
  parallax macro import-bundle --file PATH
  parallax macro import-bundle --stdin
  parallax macro project-once
  parallax macro status
  ```

  `status` returns:

  ```json
  {
    "migration_ready": true,
    "observations_count": 0,
    "series_count": 0,
    "latest_import_run": null,
    "latest_snapshot": null
  }
  ```

- [ ] **Step 5: Verify Task 4**

  ```bash
  uv run python -m pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/test_cli_macro_commands.py -q
  uv run ruff check src/parallax/domains/macro_intel src/parallax/app/surfaces/cli
  ```

- [ ] **Step 6: Commit Task 4**

  ```bash
  git add src/parallax/platform/db/alembic/versions/20260521_0077_macro_regime_70.py src/parallax/domains/macro_intel/repositories/macro_intel_repository.py src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py src/parallax/app/surfaces/cli/commands/macro.py src/parallax/app/surfaces/cli/parser.py src/parallax/app/surfaces/cli/main.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/test_cli_macro_commands.py
  git commit -m "feat: import macrodata bundles"
  ```

## Task 5: Build Historical Feature Layer

**Files:**
- Create: `src/parallax/domains/macro_intel/services/macro_feature_engine.py`
- Modify: `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
- Test: `tests/unit/domains/macro_intel/test_macro_feature_engine.py`

- [ ] **Step 1: Write feature engine tests**

  Add tests for:

  ```python
  def test_feature_engine_computes_latest_delta_zscore_and_percentile() -> None:
      ...
  ```

  Input: 30 daily observations for `fred:DGS10`. Expected:
  latest value, `delta_5d`, `delta_20d`, finite `zscore`, finite `percentile`,
  and no freshness gap.

- [ ] **Step 2: Add history repository method**

  Implement:

  ```python
  def observations_for_series(self, *, series_keys: Sequence[str], lookback_days: int, limit_per_series: int) -> list[dict[str, Any]]:
      ...
  ```

  SQL should filter by `series_key = ANY(%s)` and order by
  `series_key ASC, observed_at DESC, ingested_at_ms DESC`.

- [ ] **Step 3: Implement feature engine**

  Output shape:

  ```json
  {
    "fred:DGS10": {
      "latest": {"value": 4.7, "observed_at": "2026-05-20", "unit": "percent"},
      "freshness_days": 1,
      "delta": {"5d": 0.12, "20d": 0.34, "60d": null},
      "zscore": {"lookback": 252, "value": 1.2},
      "percentile": {"lookback": 252, "value": 0.83},
      "data_gaps": ["insufficient_history:60d"]
    }
  }
  ```

- [ ] **Step 4: Verify Task 5**

  ```bash
  uv run python -m pytest tests/unit/domains/macro_intel/test_macro_feature_engine.py -q
  uv run mypy src/parallax/domains/macro_intel
  ```

- [ ] **Step 5: Commit Task 5**

  ```bash
  git add src/parallax/domains/macro_intel/services/macro_feature_engine.py src/parallax/domains/macro_intel/repositories/macro_intel_repository.py tests/unit/domains/macro_intel/test_macro_feature_engine.py
  git commit -m "feat: compute macro historical features"
  ```

## Task 6: Upgrade Regime and Scenario Engine

**Files:**
- Modify: `src/parallax/domains/macro_intel/_constants.py`
- Modify: `src/parallax/domains/macro_intel/services/macro_regime_engine.py`
- Create: `src/parallax/domains/macro_intel/services/macro_scenario_engine.py`
- Modify: `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py`
- Test: `tests/unit/domains/macro_intel/test_macro_regime_engine.py`
- Test: `tests/unit/domains/macro_intel/test_macro_scenario_engine.py`

- [ ] **Step 1: Write regime v2 tests**

  Add test cases:

  ```python
  def test_regime_v2_emits_chain_and_scenario_for_funding_stress() -> None:
      snapshot = build_macro_view_snapshot(observations, computed_at_ms=NOW_MS)
      assert snapshot["projection_version"] == "macro_regime_v2"
      assert snapshot["chain_json"]["liquidity"]["regime"] in {"tightening", "funding_stress"}
      assert snapshot["scenario_json"]["current_regime"] in {"funding_stress", "tightening"}
      assert snapshot["scenario_json"]["confirmations"]
      assert snapshot["scenario_json"]["watch_triggers"]
      assert "trade_map" in snapshot["scenario_json"]
  ```

- [ ] **Step 2: Bump projection version**

  Change `_constants.py`:

  ```python
  MACRO_VIEW_PROJECTION_VERSION = "macro_regime_v2"
  ```

- [ ] **Step 3: Implement chain scoring**

  Use deterministic chain keys:

  ```text
  liquidity
  rates
  fed_corridor
  volatility
  credit
  positioning
  cross_asset
  ```

  Each chain node must emit:

  ```json
  {"score": 0.0, "regime": "neutral", "evidence": [], "data_gaps": []}
  ```

- [ ] **Step 4: Implement scenario assembly**

  `macro_scenario_engine.py` should expose:

  ```python
  def build_macro_scenario(*, chain: Mapping[str, Any], panels: Mapping[str, Any], features: Mapping[str, Any], triggers: Sequence[Mapping[str, Any]], data_gaps: Sequence[str]) -> dict[str, Any]:
      ...
  ```

  It should produce deterministic confirmations and contradictions. Example:

  ```json
  {
    "current_regime": "funding_stress",
    "confidence": 0.72,
    "time_window": "1w",
    "confirmations": [{"code": "sofr_above_iorb", "indicator_keys": ["sofr_iorb_spread_bps"]}],
    "contradictions": [],
    "watch_triggers": [{"code": "hy_oas_widening_5d"}],
    "invalidations": [{"code": "sofr_iorb_normalizes"}],
    "trade_map": [{"expression": "risk_down_credit_sensitive", "invalidates_on": ["hy_oas_tightens"]}]
  }
  ```

- [ ] **Step 5: Update worker to read history**

  Replace latest-only read with:

  ```python
  observations = repos.macro_intel.observations_for_series(
      series_keys=MACRO_CORE_SERIES,
      lookback_days=self._lookback_days(),
      limit_per_series=self._limit_per_series(),
  )
  ```

  Add worker setting defaults only if needed:
  `lookback_days=1095`, `limit_per_series=800`.

- [ ] **Step 6: Verify Task 6**

  ```bash
  uv run python -m pytest tests/unit/domains/macro_intel/test_macro_regime_engine.py tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_view_projection_worker.py -q
  uv run mypy src/parallax/domains/macro_intel
  ```

- [ ] **Step 7: Commit Task 6**

  ```bash
  git add src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services/macro_regime_engine.py src/parallax/domains/macro_intel/services/macro_scenario_engine.py src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py tests/unit/domains/macro_intel/test_macro_regime_engine.py tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_view_projection_worker.py
  git commit -m "feat: add macro regime state machine"
  ```

## Task 7: Extend API and `/macro` Product Surface

**Files:**
- Modify: `src/parallax/app/surfaces/api/routes_macro.py`
- Modify: `tests/unit/test_api_macro_contract.py`
- Modify: `web/src/lib/types/frontend-contracts.ts`
- Modify: `web/src/features/macro/MacroPage.tsx`
- Modify: `web/src/features/macro/macro.css`
- Modify: `web/tests/component/features/macro/MacroPage.test.tsx`

- [ ] **Step 1: Test API includes new fields**

  Extend the API contract test to assert:

  ```python
  assert "features" in payload["data"]
  assert "chain" in payload["data"]
  assert "scenario" in payload["data"]
  assert "scorecard" in payload["data"]
  ```

- [ ] **Step 2: Update API serializer**

  Add fields in `_public_macro`:

  ```python
  "features": snapshot.get("features_json") or {},
  "chain": snapshot.get("chain_json") or {},
  "scenario": snapshot.get("scenario_json") or {},
  "scorecard": snapshot.get("scorecard_json") or {},
  ```

- [ ] **Step 3: Extend frontend types**

  Add `MacroScenario`, `MacroChainNode`, and `MacroFeatureSnapshot` types.
  Keep fields permissive enough for partial data gaps but explicit enough for
  render tests.

- [ ] **Step 4: Render scenario/trade map**

  Add page sections:

  ```text
  Transmission Chain
  Scenario Path
  Confirmations / Contradictions
  Trade Map
  Data Gaps
  ```

  The page should still render when `scenario` is empty.

- [ ] **Step 5: Verify Task 7**

  ```bash
  uv run python -m pytest tests/unit/test_api_macro_contract.py -q
  cd web && npm test -- --run tests/component/features/macro/MacroPage.test.tsx
  cd web && npm run typecheck
  cd web && npm run lint
  ```

- [ ] **Step 6: Commit Task 7**

  ```bash
  git add src/parallax/app/surfaces/api/routes_macro.py tests/unit/test_api_macro_contract.py web/src/lib/types/frontend-contracts.ts web/src/features/macro/MacroPage.tsx web/src/features/macro/macro.css web/tests/component/features/macro/MacroPage.test.tsx
  git commit -m "feat: surface macro scenario state"
  ```

## Task 8: Real Runtime Smoke and 70+ Verification

**Files:**
- Create: `docs/superpowers/plans/active/2026-05-21-macro-regime-70-verification.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `src/parallax/domains/macro_intel/ARCHITECTURE.md`

- [ ] **Step 1: Apply DB migration in real runtime**

  ```bash
  cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-regime-70
  uv run parallax db migrate
  uv run parallax db health
  ```

  Expected: `migration_status` is `ready`. If the operator does not want to
  migrate immediately, record the blocker in verification and stop real-data
  smoke.

- [ ] **Step 2: Generate macrodata bundle**

  ```bash
  cd /Users/qinghuan/Documents/code/macrodata-cli/.worktrees/macro-core-bundle
  uv run macrodata bundle macro-core --asof 2026-05-21 > /tmp/macro-core.json
  ```

  Expected: exit 0. If `FRED_API_KEY` is missing, output is `data_quality=partial`
  with `missing_api_key` diagnostics.

- [ ] **Step 3: Import bundle**

  ```bash
  cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-regime-70
  uv run parallax macro import-bundle --file /tmp/macro-core.json
  uv run parallax macro status
  ```

  Expected: observation counts increase and import diagnostics are visible.

- [ ] **Step 4: Run projection once**

  ```bash
  uv run parallax macro project-once
  uv run parallax macro status
  ```

  Expected: latest snapshot has `projection_version=macro_regime_v2`,
  non-empty `chain`, and `scenario.current_regime`.

- [ ] **Step 5: Verify API and UI**

  ```bash
  uv run python -m pytest tests/unit/domains/macro_intel tests/unit/test_api_macro_contract.py -q
  cd web && npm test -- --run tests/component/features/macro/MacroPage.test.tsx tests/routes/macro.route.test.tsx
  cd web && npm run typecheck && npm run lint && npm run build
  ```

  Start the app and capture `/macro` with Playwright. Expected visible sections:
  `Macro`, `Transmission Chain`, `Scenario Path`, `Triggers`, `Data Gaps`, and
  `Trade Map`.

- [ ] **Step 6: Run scorecard**

  Record this table in the verification file:

  ```markdown
  | Area | Max | Score | Evidence |
  |------|-----|-------|----------|
  | Data source coverage | 20 |  |  |
  | Import chain | 15 |  |  |
  | Historical feature layer | 15 |  |  |
  | Regime state machine | 20 |  |  |
  | Product surface | 10 |  |  |
  | Ops and verification | 20 |  |  |
  | Total | 100 |  |  |
  ```

  Minimum target: total >= 72.

- [ ] **Step 7: Update docs**

  Document:

  - `/api/macro` new fields in `docs/CONTRACTS.md`;
  - macro importer and worker ownership in `docs/WORKERS.md`;
  - data-layer flow in `docs/ARCHITECTURE.md`;
  - domain-specific import/feature/regime flow in
    `src/parallax/domains/macro_intel/ARCHITECTURE.md`.

- [ ] **Step 8: Commit Task 8**

  ```bash
  git add docs/CONTRACTS.md docs/WORKERS.md docs/ARCHITECTURE.md src/parallax/domains/macro_intel/ARCHITECTURE.md docs/superpowers/plans/active/2026-05-21-macro-regime-70-verification.md
  git commit -m "docs: verify macro regime 70"
  ```

## Final Verification Commands

Run in `macrodata-cli`:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src tests
uv run macrodata doctor
uv run macrodata bundle macro-core --asof 2026-05-21
```

Run in `parallax`:

```bash
uv run ruff check .
uv run mypy src/parallax/domains/macro_intel src/parallax/app/surfaces/api/routes_macro.py src/parallax/app/surfaces/cli/commands/macro.py
uv run python -m pytest tests/unit/domains/macro_intel tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py -q
cd web && npm test -- --run tests/component/features/macro/MacroPage.test.tsx tests/routes/macro.route.test.tsx
cd web && npm run typecheck && npm run lint && npm run build
uv run parallax db health
uv run parallax macro status
```

If `make check-all` still fails because of unrelated baseline architecture
checks, record the exact failures in the verification artifact and confirm no
macro-related failure was introduced.

## PR / Commit Breakdown

1. `macrodata-cli`: `feat: define macro core data bundle`
2. `macrodata-cli`: `feat: add macro proxy data providers`
3. `macrodata-cli`: `feat: expose macro core bundles`
4. `parallax`: `feat: import macrodata bundles`
5. `parallax`: `feat: compute macro historical features`
6. `parallax`: `feat: add macro regime state machine`
7. `parallax`: `feat: surface macro scenario state`
8. `parallax`: `docs: verify macro regime 70`

## Rollback

- Disable `workers.macro_view_projection.enabled` if projection misbehaves.
- Stop importing bundles by not running `parallax macro import-bundle`.
- Revert code commits if needed.
- DB rollback of `20260521_0077` drops `macro_import_runs` and removes the
  added JSONB snapshot columns. Export `macro_observations` and
  `macro_view_snapshots` before downgrade if production data exists.

## Self-review

- Spec coverage: Tasks 1-3 cover `macrodata-cli`; Task 4 covers import chain;
  Task 5 covers feature layer; Task 6 covers regime/scenario; Task 7 covers
  API/UI; Task 8 covers real runtime verification and scorecard.
- Placeholder scan: No task uses placeholder markers or undefined future
  behavior as an implementation substitute.
- Type consistency: New snapshot fields are consistently named
  `features_json`, `chain_json`, `scenario_json`, and `scorecard_json` in DB,
  repository, API, and frontend contracts.
