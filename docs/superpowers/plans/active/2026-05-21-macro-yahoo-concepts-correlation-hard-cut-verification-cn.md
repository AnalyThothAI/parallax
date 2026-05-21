# Macro Yahoo Concepts Correlation Verification

**Date:** 2026-05-21

**Scope:** `macrodata-cli` Yahoo hard cut, `gmgn-twitter-intel` concept-key projection, `marketlane-cli` removal, and `/macro/assets/correlation` route/page.

## Dependency And Source Cut

- `macrodata-cli` main released and pushed:
  - `v0.1.3`: Yahoo provider and macro-core source-chain switch.
  - `v0.1.5`: dependency upgrade release used by this repo.
- `gmgn-twitter-intel` now pins `macrodata-cli` tag `v0.1.5`.
- `marketlane-cli` is removed from `pyproject.toml` and `uv.lock`.
- Runtime provider wiring uses `providers.macrodata.stock_quote_provider`.
- `config.example.yaml` now uses `providers.macrodata` and is covered by `tests/unit/test_settings.py`.

## Automated Verification

`macrodata-cli`:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
```

Result:

```text
89 passed
All checks passed
Success: no issues found
```

`gmgn-twitter-intel` backend target suite:

```bash
uv run pytest tests/unit/test_settings.py tests/unit/domains/macro_intel tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py tests/unit/test_macrodata_quote_provider.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_gmgn_openapi_client.py tests/unit/test_direct_ws.py tests/integration/test_api_health.py tests/architecture/test_project_structure.py
```

Result:

```text
134 passed in 40.80s
```

`gmgn-twitter-intel` lint/type checks:

```bash
uv run ruff check src/gmgn_twitter_intel/domains/macro_intel src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py src/gmgn_twitter_intel/app/runtime/provider_wiring src/gmgn_twitter_intel/app/runtime/providers_wiring.py src/gmgn_twitter_intel/integrations/macrodata src/gmgn_twitter_intel/platform/config/settings.py tests/unit/domains/macro_intel tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py tests/unit/test_macrodata_quote_provider.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_settings.py tests/integration/test_api_health.py tests/architecture/test_project_structure.py
uv run mypy src/gmgn_twitter_intel/domains/macro_intel src/gmgn_twitter_intel/integrations/macrodata
```

Result:

```text
All checks passed
Success: no issues found in 14 source files
```

Frontend target tests:

```bash
cd web
npm test -- --run tests/component/features/macro/MacroPage.test.tsx tests/routes/macro.route.test.tsx tests/component/features/macro/MacroAssetCorrelationPage.test.tsx
npm run typecheck
npm run lint
npm run build
```

Result:

```text
Test Files 3 passed
Tests 6 passed
typecheck passed
lint passed
build passed
```

## Real Data Smoke

Operator config was checked with:

```bash
uv run gmgn-twitter-intel config
```

Confirmed runtime paths point at:

```text
/Users/qinghuan/.gmgn-twitter-intel/config.yaml
/Users/qinghuan/.gmgn-twitter-intel/workers.yaml
```

Secrets were not printed.

Generated Yahoo-backed macro-core history:

```bash
uv run macrodata bundle history macro-core --start 2026-05-01 --end 2026-05-21
```

Result summary:

```text
ok=True
bundle=macro-core
observations=489
missing_count=0
errors_count=0
source_chain=['fred', 'nyfed', 'treasury_fiscal', 'yahoo', 'cftc']
```

Imported and projected into the local Postgres smoke target:

```bash
HOME=/tmp/gmgn-macro-smoke uv run gmgn-twitter-intel db migrate
HOME=/tmp/gmgn-macro-smoke uv run gmgn-twitter-intel macro import-bundle --file /tmp/macro-core-history.json
HOME=/tmp/gmgn-macro-smoke uv run gmgn-twitter-intel macro project-once
HOME=/tmp/gmgn-macro-smoke uv run gmgn-twitter-intel macro status
```

Result summary:

```text
projection_version=macro_regime_v3
observed_concept_count=36
required_concept_count=36
coverage_ratio=1.0
```

Correlation API smoke against the current branch server:

```bash
curl -fsS 'http://127.0.0.1:8766/api/macro/assets/correlation?window=20d&token=macro-smoke-token'
```

Result summary:

```text
ok=True
window=20d
asset_count=12
pair_count=66
available_pairs=66
gap_count=0
asof_date=2026-05-20
sample_pair=asset:spy/asset:qqq correlation=0.9298 sample_size=13
```

Browser smoke against the current branch server:

```text
http://127.0.0.1:8766/macro/assets/correlation
```

Result summary:

```text
route rendered
60d showed explicit insufficient-history gaps for the 2026-05-01 to 2026-05-21 smoke dataset
20d rendered matrix, strongest positive pairs, strongest negative pairs, and coverage complete
```

## Post-main Integration

After merging local `main` commit `0225df7f` into the feature branch, the target verification was rerun:

```text
backend target pytest: 134 passed in 36.09s
backend ruff: All checks passed
backend mypy: Success, no issues found in 14 source files
frontend macro tests: 3 files passed, 6 tests passed
frontend typecheck: passed
frontend lint: passed
frontend build: passed
```

## Known Non-goals

- Full architecture suite has pre-existing domain-boundary findings outside this macro hard-cut scope. Targeted architecture structure tests passed.
- The running Docker app on port `8765` is an older image. The new `/api/macro/assets/correlation` route was smoke-tested on the current branch server on port `8766`; production use requires rebuilding/restarting the app from this branch after merge.
