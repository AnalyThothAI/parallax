# Token Radar Anchor / Live Hard Cut Verification

- `uv run ruff check .` - pass.
- `uv run pytest -q` - pass: 650 passed, 14 skipped.
- `npm --prefix web test -- --run` - pass: 20 files / 116 tests.
- `npm --prefix web run build` - pass.
- `uv run parallax db migrate` - pass after 0029 switched to destructive hard cut; local DB reached `20260511_0029`.
- `uv run pytest tests/contract/test_openapi_drift.py tests/integration/test_docs_generated.py::test_make_docs_generated_clean_diff -q` - pass: 3 passed.
