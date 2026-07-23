# Token test contract hard-cut report

## Findings

- The six assigned Token test surfaces still encoded the retired product-AI contract through `semantic_catalyst`, `narrative_admission`, and old Token Radar projection versions.
- Repository fixtures now use only the surviving transparent factor families: `social_heat`, `social_propagation`, and `timing_risk`.
- Every assigned projection fixture and assertion now targets `token-radar-v14-transparent-factors`; factor snapshots continue to use the production-exported `TOKEN_FACTOR_SNAPSHOT_VERSION`, currently `token_factor_snapshot_v4_transparent_factors`.
- Asset Flow assertions no longer require the retired narrative-admission read-model output.
- Factor distribution and cross-section tests exercise the transparent family set and its available-rank renormalization without a semantic placeholder.
- The two inherited golden failures were transaction-contract failures, not projection behavior failures. The dirty-target enqueue now runs inside an explicit `repos.transaction()`; the publisher retains its own transaction boundary.

## Scope

Changed exactly:

- `tests/unit/test_token_radar_repository.py`
- `tests/unit/test_asset_flow_service.py`
- `tests/unit/test_factor_diagnostics.py`
- `tests/unit/test_cross_section_normalizer.py`
- `tests/integration/test_token_radar_repository.py`
- `tests/golden/test_token_radar_corpus.py`
- this generated report

No production source, API, frontend, migration, or other test file was edited.

## Verification

Fresh combined assigned gate:

```text
$ uv run pytest -q tests/unit/test_token_radar_repository.py tests/unit/test_asset_flow_service.py tests/unit/test_factor_diagnostics.py tests/unit/test_cross_section_normalizer.py tests/integration/test_token_radar_repository.py tests/golden/test_token_radar_corpus.py
........................................................................ [ 54%]
...................................................                      [100%]
131 passed in 54.49s
```

Static verification:

```text
$ uv run ruff check <the six assigned test files>
All checks passed!

$ git diff --check -- <the six assigned test files>
exit code: 0

$ rg -n "semantic_catalyst|llm_|narrative_admission|token-radar-v(9|11|13)|token_factor_snapshot_v[123]" <the six assigned test files>
no matches
```

## Production mismatch

None found in the exercised Token contracts. The current production repository, factor-snapshot validator, Asset Flow service, projection version, and PostgreSQL migration schema agree with the rewritten tests.
