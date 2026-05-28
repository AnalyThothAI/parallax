# News Intel Dedup Hard Cut Verification

**Date:** 2026-05-28
**Branch:** `codex/news-intel-dedup-root-fix`
**Scope:** canonical item hard cut, OpenNews bounded catch-up cursor, provider ready/partial monotonic merge, observation edge remap, page-row enabled-edge guard, source disable catch-up, public read-path identity cleanup, ops diagnostics.

## Final Verification Rerun

```bash
uv run pytest tests/unit/domains/news_intel tests/unit/integrations/news_feeds tests/integration/domains/news_intel tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_boundaries.py tests/architecture/test_projection_worker_idle_cost_contract.py -q
```

Result: `270 passed in 440.35s (0:07:20)`.

```bash
uv run pytest tests/unit/domains/news_intel/test_news_story_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_workers.py tests/architecture/test_projection_worker_idle_cost_contract.py tests/unit/integrations/news_feeds/test_provider_registry.py tests/unit/domains/news_intel/test_opennews_provider_signal.py -q
```

Result: `32 passed in 0.46s`.

```bash
uv run pytest tests/integration/domains/news_intel/test_news_repository.py::test_story_and_fact_detail_sanitize_internal_urls tests/integration/domains/news_intel/test_news_repository.py::test_news_dedup_diagnostics_reports_disabled_rows_and_visible_duplicate_excess -q
```

Result: `2 passed in 12.99s`.

```bash
uv run ruff check .
```

Result: `All checks passed!`.

```bash
uv run ruff format --check src/gmgn_twitter_intel/domains/news_intel/services/news_canonical_identity.py src/gmgn_twitter_intel/domains/news_intel/services/news_url_identity.py src/gmgn_twitter_intel/platform/db/alembic/versions/20260528_0116_news_intel_canonical_dedup_hard_cut.py tests/unit/domains/news_intel/test_news_canonical_identity.py tests/unit/domains/news_intel/test_news_url_identity.py $(git diff --name-only -- '*.py')
```

Result: `36 files already formatted`.

```bash
git diff --check
```

Result: no output.

```bash
uv run mypy src/gmgn_twitter_intel/app/runtime/provider_wiring/news.py src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py src/gmgn_twitter_intel/app/surfaces/cli/parser.py src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py src/gmgn_twitter_intel/domains/news_intel/runtime/news_story_projection_worker.py src/gmgn_twitter_intel/domains/news_intel/services/feed_item_normalizer.py src/gmgn_twitter_intel/domains/news_intel/services/news_canonical_identity.py src/gmgn_twitter_intel/domains/news_intel/services/news_page_projection.py src/gmgn_twitter_intel/domains/news_intel/services/news_story_grouping.py src/gmgn_twitter_intel/domains/news_intel/services/news_url_identity.py src/gmgn_twitter_intel/domains/news_intel/services/opennews_provider_signal.py src/gmgn_twitter_intel/integrations/news_feeds/feed_client.py src/gmgn_twitter_intel/integrations/news_feeds/opennews_client.py src/gmgn_twitter_intel/integrations/news_feeds/provider_registry.py
```

Result: `Success: no issues found in 15 source files`.

Final subagent review result: `96/100`, with no P0/P1/P2 findings in the reviewed scope. Earlier P1 findings around OpenNews partial-first provider locking and public agent/run identity exposure were fixed and re-reviewed.

```bash
uv run ruff format --check .
```

Result: blocked by existing repository-wide format debt outside this News slice plus the migration/new identity files before they were formatted. After formatting this slice, remaining global blockers are 22 unrelated files in `macro`, `asset_market`, `token_intel`, `equity_event`, `narrative`, and unrelated tests. This branch avoids touching those files.

## Verified Commands

```bash
uv run pytest tests/integration/domains/news_intel/test_news_repository.py -q
```

Result: `42 passed in 88.17s`.

```bash
uv run pytest tests/unit/integrations/news_feeds/test_opennews_client.py tests/unit/integrations/news_feeds/test_provider_registry.py tests/unit/domains/news_intel/test_feed_item_normalizer.py -q
```

Result: `21 passed in 0.15s`.

```bash
uv run pytest tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py -q
```

Result: `24 passed in 0.22s`.

```bash
uv run pytest tests/unit/domains/news_intel/test_news_url_identity.py tests/unit/domains/news_intel/test_news_canonical_identity.py -q
```

Result: `10 passed in 0.02s`.

```bash
uv run pytest tests/unit/domains/news_intel tests/unit/integrations/news_feeds tests/integration/domains/news_intel tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_boundaries.py -q
```

Result: `253 passed in 218.29s` after formatting/type cleanup. Earlier pre-format run also passed: `253 passed in 355.91s`.

```bash
uv run pytest tests/unit/domains/news_intel/test_news_story_grouping.py::test_story_grouping_rejects_same_container_url_without_content_or_event_evidence tests/unit/test_cli.py::test_ops_news_dedup_commands_are_registered_without_compatibility_flags tests/integration/domains/news_intel/test_news_repository.py::test_list_news_item_ids_for_sources_uses_observation_edges_not_representative_source tests/integration/domains/news_intel/test_news_repository.py::test_page_projection_loader_uses_enabled_edge_source_metadata_for_disabled_representative tests/integration/domains/news_intel/test_news_repository.py::test_get_news_item_detail_exposes_canonical_observation_evidence tests/integration/domains/news_intel/test_news_repository.py::test_source_status_exposes_news_dedup_and_sync_diagnostics tests/integration/domains/news_intel/test_news_repository.py::test_news_dedup_diagnostics_reports_disabled_rows_and_visible_duplicate_excess -q
```

Result: `7 passed in 27.21s`.

```bash
uv run ruff check .
```

Result: `All checks passed!`.

```bash
uv run ruff format --check $(git diff --name-only -- '*.py')
```

Result: `26 files already formatted`.

```bash
git diff --check
```

Result: no output.

```bash
uv run mypy src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py src/gmgn_twitter_intel/domains/news_intel/runtime/news_story_projection_worker.py src/gmgn_twitter_intel/domains/news_intel/services/news_canonical_identity.py src/gmgn_twitter_intel/domains/news_intel/services/news_page_projection.py src/gmgn_twitter_intel/domains/news_intel/services/news_story_grouping.py src/gmgn_twitter_intel/integrations/news_feeds/opennews_client.py src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py src/gmgn_twitter_intel/app/surfaces/cli/parser.py
```

Result: `Success: no issues found in 9 source files`.

## Static Gates

- `NewsRepository` has no `upsert_news_item` writer surface.
- `news_items` is no longer written with `ON CONFLICT(provider_item_id)`.
- News story projection no longer calls fuzzy candidate search; story id is derived from deterministic `story_key_for_item`, and membership uses `replace_story_member_for_item`.
- Story assignment and story key selection are `content_hash` first; article URL is only a deterministic fallback.
- Migration clears old `news_story_members/news_story_groups`, clears page story context, and enqueues story/page/brief rebuild targets for processed canonical items.
- Exact `content_hash` is the canonical root before OpenNews provider article id and article URL in runtime and migration backfill.
- OpenNews `sourceItemKey` is observation identity only; official `provider_article_id/article_id/id` is required for provider article identity.
- OpenNews `incoming_provider_payload_status` is passed from provider item upsert into canonical upsert, so ready exact content can promote partial-first provider edges without partial-later downgrading ready rows.
- Same-fetch OpenNews ready payloads keep title/body/raw/provider token impacts when a later partial patch arrives.
- Same-fetch OpenNews ready payloads keep canonical `link` when a later partial patch arrives.
- `news_item_observation_edges` is the only `provider_item_id` conflict target introduced in this slice.
- RSS/CryptoPanic receive empty sync cursor; OpenNews receives source high watermark/overlap cursor.
- Page row duplicate/source summaries are derived from enabled observation edges only.
- `choose_story_assignment` only uses exact URL story merge when both sides are `url_identity_kind="article"`.
- `choose_story_assignment` no longer uses `title_token_time_overlap`; fuzzy title/time grouping is not a runtime story identity path.
- Source reconcile returns disabled rows and `news_fetch` enqueues affected canonical items through edge lookup.
- Public `/api/news` list rows no longer expose provider article keys or canonical dedup keys.
- Public item/story/fact detail sanitizes non-http URLs and omits raw/provider/internal identities such as `source_item_key`, `provider_item_id`, `raw_payload_json`, canonical keys and dedup key fields.
- Public page/detail agent payloads omit internal run/hash/trace identities such as `agent_run_id`, `run_id`, `sdk_trace_id`, `input_hash`, `artifact_version_hash`, and `trace_metadata_json`.
- OpenNews fetch policy has a single `fetch_mode` surface: `rest`, `websocket`, or `hybrid`.
- Ops CLI now exposes `ops news-dedup-diagnostics` and `ops rebuild-news-canonical-items`.

## Blocked / Not Run

- `make check-all` was not rerun after final story/detail fixes because `uv run ruff format --check .` still fails on existing repository-wide format debt outside this News slice. The final direct global format check reported 24 files before formatting this slice; after formatting this slice, remaining blockers are unrelated files. To avoid unrelated churn, only this branch's touched Python files were formatted and checked.
- `uv run mypy src` was attempted. It still reports pre-existing type errors outside this slice in `news_item_brief_worker.py`, `equity_event_*`, `macro_intel`, and `narrative_intel`; this branch's touched source files pass scoped mypy.
- Live `uv run gmgn-twitter-intel ops news-dedup-diagnostics` has not been run yet against operator config in this slice.
- Production-like OpenNews credentialed fetch was not run; tests use local fakes and no secrets.

## Residual Risks

- Real OpenNews high-churn windows may need tuning of `max_rest_pages` and overlap after observing production lag diagnostics.
