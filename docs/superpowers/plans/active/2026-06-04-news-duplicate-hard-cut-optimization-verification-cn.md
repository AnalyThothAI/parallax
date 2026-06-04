# News Duplicate Hard-Cut Optimization Verification

**Date:** 2026-06-04
**Scope:** Tasks 1-9 implementation verification for the News duplicate hard-cut plan.

## Completed Gates

- Runtime config path check:

```bash
uv run parallax config
```

Result: command exited 0. `config_path` is `/Users/qinghuan/.parallax/config.yaml`; `workers_config_path` is `/Users/qinghuan/.parallax/workers.yaml`. LLM runtime is configured. Secret values were not copied into this artefact. The command emitted LiteLLM optional Bedrock/SageMaker `botocore` preload warnings.

- Target News test suite:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_url_identity.py tests/unit/domains/news_intel/test_feed_item_normalizer.py tests/unit/domains/news_intel/test_news_material_identity.py tests/unit/domains/news_intel/test_news_canonical_identity.py tests/unit/domains/news_intel/test_news_projection_work.py tests/integration/domains/news_intel/test_news_repository.py tests/integration/domains/news_intel/test_news_duplicate_hard_cut_repair.py tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py tests/integration/domains/news_intel/test_news_page_rows_read_path.py -q
```

Result: `160 passed in 546.14s`.

- Focused Task 6-8 regression suite after formatting:

```bash
uv run pytest tests/unit/domains/news_intel/test_news_duplicate_hard_cut_repair_unit.py tests/integration/domains/news_intel/test_news_duplicate_hard_cut_repair.py tests/unit/test_cli.py tests/unit/domains/news_intel/test_news_projection_work.py tests/integration/domains/news_intel/test_news_repository.py tests/integration/domains/news_intel/test_news_item_agent_brief_repository.py tests/integration/domains/news_intel/test_news_page_rows_read_path.py -q -k 'repair_news_duplicates or news_duplicate_hard_cut_repair or news_dedup or material_duplicate or duplicate_observation or enqueue_news_item_work_filters_non_servable_duplicate_ids'
```

Result: `22 passed, 83 deselected in 111.38s`.

- Targeted lint and format:

```bash
uv run ruff check <touched Python files>
uv run ruff format --check <touched Python files>
```

Result: `All checks passed!`; `24 files already formatted`.

- Generated CLI help:

```bash
uv run python scripts/regen_cli_help.py
rg -n "repair-news-duplicates-hard-cut|news-dedup-diagnostics" docs/generated/cli-help.md
```

Result: generated help includes `repair-news-duplicates-hard-cut` and `news-dedup-diagnostics`. The regen command emitted LiteLLM optional Bedrock/SageMaker `botocore` preload warnings.

- Whitespace:

```bash
git diff --check
```

Result: exited 0.

## Partial / Deferred Gates

- `make check` was attempted and failed at the repo-wide `ruff format --check .` stage. The formatter reported 48 files across the repository that would be reformatted, including many files outside this task's edit scope. To avoid unrelated churn, only task-touched Python files were formatted and verified.
- `make check-all` was not run. It includes full integration, e2e, golden, and coverage gates and should be run as the final pre-merge/rollout gate.
- Docker rebuild, local migration, dry-run repair, execute repair, app restart, and production diagnostics were not run in this pass.

## Subagent Reviews

- Task 6/7 repair and diagnostics review: PASS after fixing material candidate limit after hard-provider exclusion.
- Task 8 projection/brief guardrail review: PASS. Residual notes: disabled-source filtering and fake-repo fallback branch are not directly covered by integration tests; physical stale `news_page_rows` cleanup remains a separate operational cleanup concern.
