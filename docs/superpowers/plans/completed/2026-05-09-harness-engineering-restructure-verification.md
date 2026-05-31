# Verification — Harness Engineering Restructure

**Date:** 2026-05-09
**Plan:** `docs/superpowers/plans/active/2026-05-09-harness-engineering-restructure.md` (will be moved to `completed/` in the same commit as this artefact)
**Spec:** `docs/superpowers/specs/active/2026-05-09-harness-engineering-restructure.md` (will be moved to `completed/` in the same commit as this artefact)

## Commands run

```
$ uv run ruff check .
All checks passed!

$ uv run python -m compileall -q src tests scripts
(no output — zero errors)

$ uv run pytest -v --tb=line tests/test_harness_structure.py tests/test_docs_generated.py
============================= test session starts ==============================
platform darwin -- Python 3.13.11, pytest-9.0.3, pluggy-1.6.0
cachedir: .pytest_cache
rootdir: /Users/qinghuan/Documents/code/parallax/.claude/worktrees/harness-restructure
configfile: pyproject.toml
plugins: anyio-4.13.0
collecting ... collected 11 items

tests/test_harness_structure.py::test_routers_within_line_budget PASSED  [  9%]
tests/test_harness_structure.py::test_lane_roots_have_no_loose_files PASSED [ 18%]
tests/test_harness_structure.py::test_specs_lane_has_templates_dir_only_under_superpowers PASSED [ 27%]
tests/test_harness_structure.py::test_docs_root_governance_files PASSED  [ 36%]
tests/test_harness_structure.py::test_no_legacy_files_at_docs_root PASSED [ 45%]
tests/test_harness_structure.py::test_rule_uniqueness PASSED             [ 54%]
tests/test_harness_structure.py::test_references_papers_present PASSED   [ 63%]
tests/test_docs_generated.py::test_generated_directory_present PASSED    [ 72%]
tests/test_docs_generated.py::test_expected_generated_files PASSED       [ 81%]
tests/test_docs_generated.py::test_generated_files_have_header_marker PASSED [ 90%]
tests/test_docs_generated.py::test_make_docs_generated_clean_diff PASSED [100%]

============================== 11 passed in 6.33s ==============================

$ uv run pytest --tb=line 2>&1 | tail -3
====================== 349 passed, 133 skipped in 13.12s =======================
```

## Acceptance criteria evidence

| AC | Description | Evidence |
|----|-------------|----------|
| AC1 | routers ≤ 60 lines | `tests/test_harness_structure.py::test_routers_within_line_budget` PASS (AGENTS.md 27 lines, CLAUDE.md 40 lines) |
| AC2 | no rule duplication | `tests/test_harness_structure.py::test_rule_uniqueness` PASS (6 representative phrases each appear in exactly one governance file and in no router) |
| AC3 | lane roots clean | `tests/test_harness_structure.py::test_lane_roots_have_no_loose_files` PASS |
| AC4 | docs root = 10 governance files | `tests/test_harness_structure.py::test_docs_root_governance_files` PASS plus `tests/test_harness_structure.py::test_no_legacy_files_at_docs_root` PASS |
| AC5 | `make docs-generated` clean | `tests/test_docs_generated.py::test_make_docs_generated_clean_diff` PASS (Postgres reachable, diff clean) |
| AC6 | papers present | `tests/test_harness_structure.py::test_references_papers_present` PASS |
| AC7 | TECH_DEBT registry | manual check: `grep -q '^| Description |' docs/TECH_DEBT.md` exits 0 — schema present |

## Files counted

| Category | Count |
|----------|-------|
| Routers | 2 (AGENTS.md 27 lines, CLAUDE.md 40 lines) |
| Governance | 10 (`ARCHITECTURE`, `CONTRACTS`, `SETUP`, `WORKFLOW`, `DESIGN_DISCIPLINE`, `TESTING`, `SECURITY`, `RELIABILITY`, `FRONTEND`, `TECH_DEBT`) |
| Active specs | 5 (after archiving harness-restructure) |
| Completed specs | 22 (after archiving harness-restructure: 21 existing + 1 harness-restructure) |
| Active plans | 5 (after archiving harness-restructure) |
| Completed plans | 14 (after archiving: 12 existing + 1 harness-restructure plan + 1 harness-restructure verification) |
| references/papers | 6 |
| references/* (other) | 4 (README + walkinglabs + 2 protocol stubs) |
| generated/* | 5 (README + 4 generated artefacts) |
| New scripts | 4 |

## Manual routing-table verification

Three concerns from the AGENTS.md routing table were spot-checked:

1. **"Testing & completion gates" → `docs/TESTING.md`**: File exists; contains the word "completion" and documents the `ruff check` / `pytest` / `compileall` gate commands. Link resolves correctly.

2. **"Operational invariants" → `docs/RELIABILITY.md`**: File exists; contains the word "invariant" and opens with "Owns operational invariants that must hold in any deployment." Link resolves correctly.

3. **"External references & papers" → `docs/references/`**: Directory exists; contains `papers/` subdirectory with 6 paper summaries (kleinberg-2002-burst, goel-2016-structural-virality, cheng-2014-cascades, crane-sornette-2008-endogenous-exogenous, bakshy-2011-influencer-refutation, centola-2010-complex-contagion), plus README, walkinglabs-harness-engineering.md, gmgn-public-protocol.md, okx-api.md. Link resolves correctly.

## Risks observed

- `test_current_projection_docs_are_postgres_only` was failing transiently because Chunk 2 moved two files referenced by hardcoded paths in `tests/test_project_structure.py`. Fixed in commit `994cbd3` (Chunk 4 cleanup) by adding the `completed/` segment to those paths.
- `regen_db_schema.py` requires Postgres connectivity; the test gates this via skip-on-failure logic. CI must provision Postgres or the AC5 evidence will be SKIP rather than PASS. In this run Postgres was reachable and the test passed.
- The plan called for `from parallax.storage.session import build_engine`; that import did not exist. The script was adapted to use `local_docker_host_dsn` + `with_password_from_file` from `parallax.storage.postgres_client`, following the same pattern as `storage/alembic/env.py`. Adaptation is documented in the script's import comments.

## Follow-ups (appended to docs/TECH_DEBT.md)

- Chunk 1 code review noted that `test_rule_uniqueness` could be split into two functions (one for ownership, one for router non-leakage) and that the `path.exists()` guard deserves an inline comment. Both are non-blocking readability improvements.
- Chunk 5 noted `regen_ws_protocol.py` produces a sparse table because `src/parallax/api/ws.py` uses JSON dicts on the wire rather than typed message classes. If the WS surface gets typed message classes in the future, the script will pick them up automatically; until then the table only lists `ClientSubscription` and `PublicWebSocketHub`.
- The pre-Chunk-3 `RULE_PHRASES` test scaffold guessed phrases that did not match verbatim governance content; commit `816ecc4` (Chunk 3 cleanup) corrected them. If governance files are reworded in future, RULE_PHRASES likely needs another sweep.
