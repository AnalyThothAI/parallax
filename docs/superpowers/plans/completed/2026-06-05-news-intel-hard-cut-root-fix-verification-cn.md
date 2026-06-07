> Superseded on 2026-06-07 by `docs/superpowers/specs/active/2026-06-07-news-market-wide-notification-hard-cut-cn.md` and `docs/superpowers/plans/active/2026-06-07-news-market-wide-notification-hard-cut-plan-cn.md`. Do not use this file for current News agent, projection, notification, API, or storage behavior.

# News Intel hard-cut root fix verification

Date: 2026-06-05

Scope:
- Remove retired News research-tool compatibility from runtime/public contracts.
- Preserve material news facts; purge only retired agent/read-model/notification/dirty-target artifacts.
- Gate News analysis, page rows, and notifications through semantic admission plus story identity.
- Keep current read models stable and rebuildable with current projection/brief contracts only.

Known runtime config check:
- `uv run parallax config` was run before implementation.
- Reported runtime config paths were operator-owned `~/.parallax/config.yaml` and `~/.parallax/workers.yaml`.
- Secret values were not printed.

Completed targeted verification:
- Task 1-2 contract/cleanup target: passed.
- Task 3-5 admission, process integration, story identity target: passed.
- Task 6 story-shaped page projection target: `114 passed in 208.81s`.
- Task 7 notifications/API target: `74 passed in 103.76s`.
- Task 8 architecture/guardrails:
  - `uv run pytest tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_worker_runtime_contracts.py -q`
  - Result before reviewer fixes: `103 passed, 1 skipped in 5.77s`.
  - Result after reviewer fixes: `104 passed, 1 skipped in 5.43s`.
  - `uv run ruff check tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_worker_runtime_contracts.py`
  - Result: `All checks passed!`.
- Task 8 reviewer findings addressed:
  - `signal.alert_eligibility` docs now describe object fields
    `in_app_eligible`, `external_push_ready`, and `external_push_block_reason`.
  - Retired research-tool token guard now scans all `src/parallax/**/*.py`;
    only hard-cut cleanup may contain purge markers.
  - Cleanup architecture guard now requires delete-only writes against the
    exact retired artifact tables.
  - Cleanup dry-run output now separates `preserved_material_facts` from
    `preserved_current_read_models`.
- Broad final News chain target after formatting:
  - `uv run pytest ... tests/integration/test_cli.py::test_cli_ops_cleanup_news_intel_hard_cut_dispatches_to_service ... -q`
  - Result: `422 passed, 1 skipped in 273.60s`.
- Changed-file lint/format:
  - `uv run ruff check .`
  - Result: `All checks passed!`.
  - `uv run ruff format --check $(changed Python files)`
  - Result: `33 files already formatted`.
- Affected formatter rerun:
  - `uv run pytest tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_news_item_agent_policy.py tests/architecture/test_news_intel_kiss_simplification.py -q`
  - Result: `39 passed in 0.82s`.

Runtime DB / cleanup verification:
- `uv run parallax db health` before migration reported stale:
  `migration_version=20260604_0148`, `expected_migration_version=20260605_0149`.
- `uv run parallax db migrate` applied
  `20260605_0149_news_analysis_story_hard_cut`.
- `uv run parallax db health` after migration reported
  `migration_status=ready`.
- `uv run parallax ops cleanup-news-intel-hard-cut --dry-run` after migration:
  - Retired page rows: `15546`.
  - Retired notifications: `711` notifications, `2` reads, `482` deliveries.
  - Legacy briefs/runs still present by old contracts.
  - Preserved material facts included `15989` `news_items` and `19474`
    `news_provider_items` / observation edges.
  - Preserved current read models included `4` `news_source_quality_rows`.
  - Active blockers: `4` running fetch runs and one active `brief_input` dirty
    lease.
- `uv run parallax ops cleanup-news-intel-hard-cut --execute` was attempted
  after migration and correctly failed without deleting because News runtime
  advisory locks were unavailable / fetch runs were active.
- Recent 4h audit:
  - `uv run parallax ops news-dedup-diagnostics --window-hours 4 --score-threshold 85`
  - Fact layer material duplicate excess: `0`.
  - Serving read-model still has old duplicate/retired projection rows until the
    guarded cleanup can execute in a quiet maintenance window.

Project-level gate:
- `make check-all` currently fails before tests at `ruff format --check .`.
- After formatting all changed Python files, the remaining failures are 36
  unrelated pre-existing formatter-debt files outside this News hard-cut diff.
