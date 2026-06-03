# News Intel Hard Cut Residual Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Completed
**Date:** 2026-06-03
**Owning spec:** `docs/superpowers/specs/active/2026-06-03-news-intel-hard-cut-residual-root-fix-cn.md`
**Worktree:** `.worktrees/news-intel-hard-cut-residual-root-fix/`
**Branch:** `codex/news-intel-hard-cut-residual-root-fix`

**Goal:** Root-fix News Intel residual identity, projection, context, and cleanup bugs without changing business scoring, brief semantics, UI ranking, or the Kappa/CQRS worker model.

**Architecture:** Keep the current provider fetch -> canonical facts -> processing -> rebuildable read model spine. Hard-cut ambiguous identity and dormant context paths, clear polluted News Intel input/fact/read-model data instead of preserving old shapes, then let current providers repopulate under one policy.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic, psycopg3 repositories, existing News Intel workers, FastAPI, pytest, ruff, CLI ops commands.

---

## Hard-Cut Decisions

- Keep business behavior stable: do not change score thresholds, agent prompt semantics, event scoring, UI ranking, worker ownership, or provider source configuration meaning except for deleting context policy.
- Provider-global article identity is allowlisted to `opennews` in this plan through one shared helper. RSS/Atom/JSON Feed/CryptoPanic source-local ids do not become `provider_article_key` unless a later spec proves provider-global guarantees.
- `content_hash` becomes content-only for storage and comparison: title fingerprint + cleaned summary + cleaned body. It no longer includes canonical URL, but it must not be treated as an unconditional strong canonical key.
- Canonical identity order is: hard public URL -> allowlisted provider-global article id -> qualified content identity -> weak source/window fallback. Qualified content identity requires enough title/body signal; generic titles, empty summaries/bodies, homepage/live/aggregator URLs, and low-entropy content must not merge globally.
- Invalid URLs fail one item, not one run. `canonicalize_url()` returns `""` for invalid ports or malformed split failures, and feed normalization drops that item.
- Context is removed as an active News Intel capability: provider result types, fetch worker persistence, repository hydration, brief input, source quality tags, settings, and schema all lose the context path. This is a forward hard cut, not a legacy-preserving migration.
- Historical News data can be cleared. The cleanup command deletes News Intel ingest/canonical/derived/read-model data, news-originated notifications, and stale source health/runtime state while preserving `news_sources` configuration rows.

## Pre-Flight

- [ ] Confirm the spec is approved.
  ```bash
  rg -n "^Status: Approved$" docs/superpowers/specs/active/2026-06-03-news-intel-hard-cut-residual-root-fix-cn.md
  ```
  Expected: one match.

- [ ] Create an isolated worktree for implementation.
  ```bash
  git worktree add .worktrees/news-intel-hard-cut-residual-root-fix -b codex/news-intel-hard-cut-residual-root-fix main
  cd .worktrees/news-intel-hard-cut-residual-root-fix
  git status --short
  git branch --show-current
  ```
  Expected: clean worktree on `codex/news-intel-hard-cut-residual-root-fix`.

- [ ] Confirm runtime config paths before touching live data.
  ```bash
  uv run parallax config
  ```
  Expected: `config_path` and `workers_config_path` point at `~/.parallax/`. Do not print secret values.

- [ ] Check whether the operator config still contains News `context_policy`.
  ```bash
  uv run python - <<'PY'
  from pathlib import Path
  import yaml

  path = Path.home() / ".parallax" / "config.yaml"
  payload = yaml.safe_load(path.read_text()) or {}
  sources = ((payload.get("news_intel") or {}).get("sources") or [])
  count = sum(1 for source in sources if isinstance(source, dict) and "context_policy" in source)
  print({"config_path": str(path), "news_sources_with_context_policy": count})
  PY
  ```
  Expected before hard cut rollout: `0`. If nonzero, remove those keys from `~/.parallax/config.yaml` before deploying the context hard cut. Use raw YAML scanning because post-hard-cut settings validation will reject the key.

- [ ] Confirm `config.example.yaml` does not keep removed News context config after implementation.
  ```bash
  rg -n "context_policy" config.example.yaml
  ```
  Expected after Task 4: no matches.

- [ ] Capture a DB backup/snapshot before any destructive cleanup rehearsal or rollout.
  ```bash
  # Use the operator-owned PostgreSQL backup path/process for this environment.
  # Record the backup id/path in the verification artefact before running --execute.
  ```
  Expected: backup id/path recorded. Cleanup rollback after `--execute` depends on this snapshot.

- [ ] Capture baseline test state.
  ```bash
  uv run ruff check .
  uv run pytest tests/unit/domains/news_intel tests/integration/domains/news_intel -q
  ```
  Expected: pass, or record exact pre-existing failures in the implementation notes before editing.

## File-Level Edits

### Identity And Normalization

- Modify `src/parallax/domains/news_intel/services/text_normalization.py`.
  - `canonicalize_url(url: object) -> str` catches `ValueError` from invalid ports and returns `""`.
  - Query normalization strips `utm_*`, `fbclid`, `gclid`, `gbraid`, `wbraid`, `mc_cid`, `mc_eid`, `igshid`, `ref`, and `ref_src`.
  - `content_hash` signature becomes content-only:
    ```python
    def content_hash(title: object, summary: object, *, body_text: object = "") -> str:
        payload = "\x1f".join(
            (
                title_fingerprint(title),
                clean_news_text(summary),
                clean_news_text(body_text),
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    ```
  - Hash payload is `title_fingerprint(title)`, `clean_news_text(summary)`, and `clean_news_text(body_text)` only.
  - Add a small qualified-content helper used by canonical identity, for example `qualified_content_hash(title, summary, body_text) -> str`. It returns `""` unless the content is high enough signal: nonempty non-generic title fingerprint, at least 160 cleaned summary/body characters, and at least 12 unique alphanumeric tokens across title/summary/body.
  - Generic or low-entropy examples such as `Market Update`, `Breaking News`, empty body/summary, homepage/live pages, or feed index pages must not return a qualified content key.

- Modify `src/parallax/domains/news_intel/services/feed_item_normalizer.py`.
  - Keep using `canonicalize_url(link)`.
  - Entries with invalid URL normalize to `None`, so caller list comprehensions continue without raising.

- Modify `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`.
  - Update the `content_hash` call to stop passing `observation.canonical_url`.
  - Remove all context observation persistence calls from fetch processing.

- Modify `src/parallax/domains/news_intel/services/news_canonical_identity.py`.
  - Keep hard URL identity first, but only for `hard_public_url_identity_key()`.
  - Move allowlisted provider-global identity before content identity, so OpenNews article ids remain stable even when fetched body/summary changes.
  - Use content identity only when `qualified_content_hash(...)` returns nonempty. Do not treat every nonempty stored `content_hash` as `dedup_key_confidence="strong"`.
  - Add or reuse one shared provider-global allowlist helper:
    ```python
    PROVIDER_GLOBAL_ARTICLE_ID_TYPES = frozenset({"opennews"})
    ```
    Repository and canonical identity code must call the same helper, not duplicate allowlist logic.

- Modify `src/parallax/domains/news_intel/repositories/news_repository.py`.
  - `_provider_article_id` returns provider article ids only when `provider_type` is in `PROVIDER_GLOBAL_ARTICLE_ID_TYPES`.
  - Non-global providers return `""` even if payload contains `id`, `guid`, `source_item_key`, or an explicit `provider_article_key` argument.
  - `upsert_provider_item` no longer preserves old non-global `provider_article_id` or `provider_article_key`; conflict SQL must overwrite old RSS/non-global keys to `""`.
  - `upsert_canonical_news_item` keeps global `provider_article_key` reuse only for nonempty allowlisted keys.

### Projection And Filters

- Modify `src/parallax/domains/news_intel/repositories/news_repository.py`.
  - `load_items_for_page_projection` must build the projected `item` payload from the enabled representative edge payload, not from disabled `news_items` representative columns.
  - The enabled representative payload must override at least: `provider_item_id`, `source_id`, `source_domain`, `canonical_url`, `title`, `summary`, `body_text`, `language`, `published_at_ms`, `fetched_at_ms`, `content_hash`, `title_fingerprint`, `provider_signal_json`, `provider_token_impacts_json`, and source metadata.
  - `delete_page_rows_for_sources` remains a delete helper for no-enabled-edge cases. Reprojection of enabled alternatives is handled by dirty targets.
  - Add a serving-path stale guard in `list_news_page_rows`: if the projected `source_json ->> 'source_id'` is nonempty, the row is returned only when that source is still enabled. Do not rely only on "any enabled edge exists" for already-projected rows.
  - Add the same stale guard in `list_news_high_signal_notification_candidates`, so notification generation cannot use a stale disabled-source projection during the dirty-target lag window.
  - Derived token lanes, fact lanes, and agent brief are canonical item-level data by design. This plan does not reprocess or source-scope those fields on source disable; the hard-cut cleanup plus stricter identity policy are the root fix for old cross-story pollution. Document this policy in the projection test so it is not confused with representative source fields.
  - `list_news_page_rows` accepts only public read contract filters: `status`, `signal`, `min_score`, and `q`.
  - `_news_page_row_filter_sql` removes unreachable `direction`, `provider_type`, `source_role`, `trust_tier`, `coverage_tag`, `content_class`, `content_tag`, and `decision_class` branches.

- Modify `src/parallax/domains/news_intel/queries/news_page_query.py`.
  - Keep the query signature aligned with `/api/news`: `limit`, `cursor`, `status`, `signal`, `min_score`, `q`.

- Modify `src/parallax/app/surfaces/api/routes_news.py`.
  - No new filters. Keep the current public API filter set.

### Context Hard Cut

- Modify `src/parallax/domains/news_intel/types/source_provider.py`.
  - Delete `NewsProviderContextObservation`.
  - Delete `NewsProviderFetchResult.context_observations`.

- Modify `src/parallax/app/runtime/provider_wiring/news.py`.
  - Return `NewsProviderFetchResult` with observations only; no context fields.

- Modify `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`.
  - Delete `_persist_context_observations`.
  - Delete context-parent tracking and `news_context_written` reprojection/reprocess logic.

- Modify `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`.
  - Call `news_item_agent_brief_eligibility` and `news_item_agent_brief_priority` without `context_items`.

- Modify `src/parallax/domains/news_intel/services/news_item_agent_policy.py`.
  - Remove `context_items` parameters.
  - `_has_processed_market_context` checks token mentions and fact candidates only.

- Modify `src/parallax/domains/news_intel/services/news_item_brief_input.py` and `src/parallax/domains/news_intel/types/news_item_brief.py`.
  - Remove context item model fields and packet hydration.
  - Remove context evidence refs from brief input payloads.

- Modify `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`.
  - Stop reading `candidate["context_items"]`.
  - Build brief inputs from item, token mentions, fact candidates, and provider/agent state only.

- Modify `src/parallax/app/runtime/projection_dirty_targets.py`.
  - Remove `news_context_items` joins and context payload plumbing.

- Modify `src/parallax/domains/news_intel/repositories/news_repository.py`.
  - Delete `upsert_news_context_item`.
  - Delete `list_context_items_for_news_item`.
  - Remove context joins from `load_items_for_brief_targets`, `get_news_item_detail`, source status, and source quality diagnostics.
  - Remove `context_policy` from `_source_payload`, `upsert_source`, source material comparison, and source capability tags.
  - Remove source-status fields `context_item_count` and `latest_context_seen_at_ms`.
  - Remove `_public_context_item_payload`, `_context_policy_enabled`, and `context_items` capability tag handling.

- Modify `src/parallax/domains/news_intel/services/source_quality_projection.py`.
  - Replace context-aware formula ids/metrics such as `useful_fact_or_context10`, `context_item_count`, and `useful_fact_or_context_rate` with fact-only names such as `useful_fact10`, `fact_candidate_count`, and `useful_fact_rate`.
  - Bump the source quality formula id/version so old diagnostics are not confused with post-hard-cut fact-only diagnostics.
  - Do not read or emit `context_item_count`, `latest_context_seen_at_ms`, or context capability tags.

- Modify `src/parallax/platform/config/settings.py`, `src/parallax/domains/news_intel/types/__init__.py`, and `config.example.yaml`.
  - Remove `context_policy` from News source config models.
  - Remove `context_policy` from the example config and repository/config fixtures. After this change, `extra="forbid"` should reject operator configs that still contain the key.

### Storage / Migrations

- Create `src/parallax/platform/db/alembic/versions/20260603_0142_news_context_and_filter_hard_cut.py`.
  - Forward hard cut only:
    ```sql
    DROP INDEX IF EXISTS ix_news_context_items_source_effective_time;
    DROP INDEX IF EXISTS idx_news_context_items_source_effective_time;
    DROP INDEX IF EXISTS news_context_items_source_published_idx;
    DROP INDEX IF EXISTS news_context_items_parent_published_idx;
    DROP TABLE IF EXISTS news_context_items;
    ALTER TABLE news_sources DROP COLUMN IF EXISTS context_policy_json;
    DROP INDEX IF EXISTS idx_news_page_rows_provider_type_time;
    DROP INDEX IF EXISTS idx_news_page_rows_source_role_time;
    DROP INDEX IF EXISTS idx_news_page_rows_trust_tier_time;
    DROP INDEX IF EXISTS idx_news_page_rows_content_class_time;
    DROP INDEX IF EXISTS idx_news_page_rows_decision_class_time;
    DROP INDEX IF EXISTS idx_news_page_rows_coverage_tags_gin;
    DROP INDEX IF EXISTS idx_news_page_rows_content_tags_gin;
    ANALYZE news_sources;
    ```
  - Downgrade may recreate empty schema if repo convention requires a downgrade body, but it must not attempt to restore old data.
  - The new revision number must not reuse the existing `20260601_0141` sequence label.

- Do not edit historical Alembic files such as `20260529_0123_news_public_url_hard_identity.py`. Current code, tests, cleanup, and the new forward hard cut define head behavior.

### Hard-Cut Cleanup Command

- Create `src/parallax/domains/news_intel/services/news_intel_hard_cut_cleanup.py`.
  - Public entry:
    ```python
    def cleanup_news_intel_hard_cut(repos: Any, *, execute: bool, now_ms: int) -> dict[str, Any]:
        table_counts = _news_table_counts(repos.conn)
        notification_counts = _news_notification_counts(repos.conn)
        active_state = _active_news_runtime_state(repos.conn, now_ms=now_ms)
        source_count = _news_source_count(repos.conn)
        if execute:
            _raise_if_active_news_runtime(active_state)
            _delete_news_notifications(repos.conn)
            _delete_news_tables(repos.conn, now_ms=now_ms)
            repos.conn.commit()
        return {
            "mode": "execute" if execute else "dry_run",
            "execute": bool(execute),
            "tables": table_counts,
            "notifications": notification_counts,
            "active_state": active_state,
            "source_sync_reset_count": source_count if execute else 0,
        }
    ```
  - Dry run returns row counts for every table and notification surface it would clear.
  - Execute fails closed if News fetch/process/projection workers still have active leases, running fetch runs, or leased dirty targets. Rollout still stops workers first; the command is the last guardrail.
  - Execute deletes News-originated notifications before page rows:
    ```sql
    DELETE FROM notifications
     WHERE rule_id = 'news_high_signal'
       AND (source_table = 'news_page_rows' OR entity_type = 'news_item');
    ```
    `notification_reads` and `notification_deliveries` cascade through the existing notification FKs.
  - Execute deletes News Intel data in dependency order and resets source fetch/health state:
    ```sql
    DELETE FROM news_projection_dirty_targets;
    DELETE FROM news_page_rows;
    DELETE FROM news_item_agent_briefs;
    DELETE FROM news_item_agent_runs;
    DELETE FROM news_fact_candidates;
    DELETE FROM news_token_mentions;
    DELETE FROM news_item_entities;
    DELETE FROM news_item_observation_edges;
    DELETE FROM news_items;
    DELETE FROM news_provider_items;
    DELETE FROM news_fetch_runs;
    DELETE FROM news_source_quality_rows;
    UPDATE news_sources
       SET etag = NULL,
           last_modified = NULL,
           last_fetch_at_ms = NULL,
           last_success_at_ms = NULL,
           consecutive_failures = 0,
           last_error = NULL,
           source_quality_status = 'unknown',
           next_fetch_after_ms = 0,
           sync_cursor_json = '{}'::jsonb,
           sync_high_watermark_ms = 0,
           sync_diagnostics_json = '{}'::jsonb,
           updated_at_ms = %(now_ms)s;
    ```
  - Table inventory may include optional pre-head legacy tables such as `news_story_members` and `news_story_groups` only when they exist; do not issue direct SQL against tables absent from current Alembic head.
  - Preserve `news_sources` rows and source configuration fields other than dropped context policy.

- Modify `src/parallax/app/surfaces/cli/parser.py`.
  - Add:
    ```python
    cleanup_news_intel = ops_subcommands.add_parser(
        "cleanup-news-intel-hard-cut",
        help="clear News Intel ingest, facts, derived rows, notifications, and source runtime state for the current hard cut",
    )
    cleanup_news_intel.add_argument("--execute", action="store_true")
    ```

- Modify `src/parallax/app/surfaces/cli/commands/ops.py`.
  - Wire `cleanup-news-intel-hard-cut` to `cleanup_news_intel_hard_cut`.
  - Return `{"ok": True, "data": result}`.

### Docs

- Modify `src/parallax/domains/news_intel/ARCHITECTURE.md`.
  - State the current identity policy.
  - Remove legacy “all public URLs are hard identity” wording.
  - Remove context item table/runtime claims.

- Modify `docs/WORKERS.md`.
  - News fetch/process/projection worker descriptions must not mention context observations.

- Modify `docs/CONTRACTS.md`.
  - Add `ops cleanup-news-intel-hard-cut`.
  - Keep `/api/news` filter contract limited to `status`, `signal`, `min_score`, and `q`.

- Regenerate or update `docs/generated/db-schema.md` only through the repo’s existing schema generation path if that file is expected to track Alembic head.

## Tests To Add Or Rewrite

### Unit Tests

- Modify `tests/unit/domains/news_intel/test_text_normalization.py`.
  - Add `test_canonicalize_url_returns_empty_for_invalid_ports`.
  - Add `test_canonicalize_url_strips_common_tracking_params`.
  - Rewrite `test_content_hash_is_stable_over_html_tracking_urls_and_case_noise` so different canonical URLs with identical title/summary/body produce the same hash.
  - Add negative qualified-content tests proving generic titles, empty summary/body, and low-entropy content return no qualified content identity.

- Modify `tests/unit/domains/news_intel/test_feed_item_normalizer.py`.
  - Add `test_normalize_feed_entry_rejects_invalid_port_without_raising`.

- Modify `tests/unit/domains/news_intel/test_news_canonical_identity.py`.
  - Add `test_homepage_live_and_aggregator_urls_do_not_create_hard_url_identity`.
  - Keep OpenNews provider id tests and update them for the new order: hard URL first, then OpenNews provider-global id, then qualified content.
  - Add `test_rss_provider_article_id_is_not_global_identity`.
  - Add `test_generic_content_hash_does_not_create_strong_identity`.

- Modify `tests/unit/domains/news_intel/test_news_workers.py`.
  - Delete context-observation persistence tests.
  - Add fetch-worker coverage that a bad normalized item does not fail the whole run when other observations are valid.

- Modify `tests/unit/domains/news_intel/test_news_item_agent_policy.py`.
  - Remove `context_items=[]` from all calls.
  - Add an assertion that token mentions or accepted fact candidates are required for processed market context.

- Modify `tests/unit/domains/news_intel/test_news_item_brief_input.py`.
  - Delete context packet tests.
  - Assert the packet has no `context_items` field or context evidence refs.

- Modify `tests/unit/test_settings.py`.
  - Delete `context_policy` parsing assertions.
  - Add a rejection assertion that source configs containing `context_policy` fail after the hard cut.
  - Keep `test_config_example_matches_settings_schema` passing by removing `context_policy` from `config.example.yaml`.

- Modify `tests/unit/test_postgres_schema.py`.
  - Remove assertions requiring `news_context_items` indexes.
  - Add assertions that head schema does not contain `news_context_items` or `news_sources.context_policy_json`.

- Modify `tests/unit/test_api_news_contract.py`.
  - Keep only public filters in fake repository assertions: `status`, `signal`, `min_score`, `q`.
  - Remove source-status assertions for `context_item_count` and `latest_context_seen_at_ms`.

- Modify `tests/unit/test_ops_projection_dirty_targets.py` and `tests/unit/domains/news_intel/test_news_projection_dirty_targets.py`.
  - Remove `context_items_json`, `context_policy_json`, and `news_context_items` join expectations.
  - Assert projection dirty-target hydration uses item/token/fact/provider payloads only.

- Modify `tests/unit/domains/news_intel/test_source_quality_projection.py`.
  - Rename context-aware metrics to fact-only metrics.
  - Assert `source_quality_projection.py` emits no `context_item_count`, `latest_context_seen_at_ms`, `useful_fact_or_context_rate`, or `context_items` capability tag.

- Modify `tests/unit/domains/news_intel/test_news_source_quality_dirty_targets.py`.
  - Remove `context_item_count` expectations from dirty-target payloads and keep fact/fetch/provider diagnostics only.

### Integration Tests

- Modify `tests/integration/domains/news_intel/test_news_repository.py`.
  - Add `test_source_local_item_keys_do_not_merge_across_feed_sources`.
  - Add a regression that passes an explicit RSS `provider_article_key` and still stores no provider-global key.
  - Add a regression that seeds an old `rss:<guid>` provider row, upserts it after the hard cut, and asserts provider item plus canonical edge keys are reset to `""`.
  - Rewrite `test_provider_item_upsert_keeps_identity_status_monotonic_in_conflict_sql` so only allowlisted providers preserve provider article identity.
  - Rewrite RSS provider key expectations from `["rss:<key>"]` to `[]` where the key is source-local.
  - Keep OpenNews provider key expectations such as `["opennews:2367422"]`.
  - Add an OpenNews canonical-path integration test: same OpenNews article id, non-hard URL, and different content hash still resolve to the same canonical identity.
  - Delete or rewrite `test_canonical_dedup_migration_promotes_public_urls_to_hard_identity`.
  - Extend `test_page_projection_loader_uses_enabled_edge_source_metadata_for_disabled_representative` to assert enabled-edge `title`, `summary`, `body_text`, `canonical_url`, `provider_signal_json`, and `provider_token_impacts_json`, not just source metadata.
  - Add `test_list_news_page_rows_hides_stale_disabled_projected_source_before_reprojection`.
  - Add `test_news_high_signal_candidates_hide_stale_disabled_projected_source_before_reprojection`.
  - Delete repository filter tests for `provider_type`, `source_role`, `trust_tier`, `coverage_tag`, `content_class`, `content_tag`, and `decision_class`.
  - Rename or rewrite the existing ambiguous signal/direction filter test so it clearly covers public `signal`, not retired `direction`.

- Delete `tests/integration/domains/news_intel/test_news_context_items_repository.py`.

- Modify `tests/integration/domains/news_intel/test_news_source_quality_repository.py`.
  - Remove context item setup and expectations.
  - Keep source quality fetch-run and provider item diagnostics.
  - Assert source status no longer exposes context counters/timestamps or `context_items` capability tags.

- Modify `tests/integration/domains/news_intel/test_news_source_classification_repository.py`.
  - Remove `context_policy` fixture input and `context_policy_json` storage assertions.

- Create `tests/integration/domains/news_intel/test_news_intel_hard_cut_cleanup.py`.
  - Seed sources with old health/runtime state, fetch runs, provider items, canonical items, observation edges, page rows, notifications, agent rows, fact/token/entity rows, and source quality rows.
  - Dry run asserts counts and no deletion.
  - Execute asserts all cleared tables have count `0`, news-originated notifications are gone, `news_sources` remains, and source cursor/cache/health fields are reset.
  - Execute with active dirty-target lease or running News runtime state fails without deleting.

- Modify `tests/integration/test_cli.py`.
  - Add parser/command coverage for `ops cleanup-news-intel-hard-cut` dry run and `--execute`.

## Task Breakdown

### Task 1: Identity And URL Normalization

- [ ] Write failing unit tests for invalid URL, tracking params, content-only hash, qualified-content rejection, homepage/live URL identity, and RSS non-global article identity.
- [ ] Update `text_normalization.py`, `feed_item_normalizer.py`, and `news_canonical_identity.py`.
- [ ] Update `news_fetch_worker.py` content hash call.
- [ ] Enforce canonical identity order: hard public URL -> allowlisted provider-global article id -> qualified content identity -> weak source/window fallback.
- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_text_normalization.py \
    tests/unit/domains/news_intel/test_feed_item_normalizer.py \
    tests/unit/domains/news_intel/test_news_canonical_identity.py -q
  ```
  Expected: pass.

### Task 2: Provider Article Key Hard Cut

- [ ] Write failing integration tests for two RSS sources sharing the same `source_item_key`, explicit RSS `provider_article_key`, and an existing old `rss:<guid>` row.
- [ ] Modify `_provider_article_id` and provider item upsert behavior so RSS/Atom/JSON Feed ids do not become global provider keys and old non-global provider keys are overwritten to `""`.
- [ ] Rewrite RSS `provider_article_keys_json` expectations to empty arrays.
- [ ] Keep OpenNews provider id tests passing, including canonical-path coverage where content hash changes but OpenNews article id is stable.
- [ ] Run:
  ```bash
  uv run pytest \
    tests/integration/domains/news_intel/test_news_repository.py::test_source_local_item_keys_do_not_merge_across_feed_sources \
    tests/integration/domains/news_intel/test_news_repository.py::test_explicit_rss_provider_article_key_is_not_global_identity \
    tests/integration/domains/news_intel/test_news_repository.py::test_old_rss_provider_article_key_is_cleared_on_upsert \
    tests/integration/domains/news_intel/test_news_repository.py::test_opennews_provider_article_key_survives_source_item_key_drift -q
  ```
  Expected: pass.

### Task 3: Projection Representative Hard Cut

- [ ] Extend disabled representative integration test to assert enabled payload fields.
- [ ] Modify `load_items_for_page_projection` SQL to overlay enabled representative edge payload onto the item JSON.
- [ ] Add serving stale guards to `list_news_page_rows` and `list_news_high_signal_notification_candidates`.
- [ ] Keep `replace_page_rows_for_items` duplicate summaries enabled-edge scoped.
- [ ] Run:
  ```bash
  uv run pytest \
    tests/integration/domains/news_intel/test_news_repository.py::test_page_projection_loader_uses_enabled_edge_source_metadata_for_disabled_representative \
    tests/integration/domains/news_intel/test_news_repository.py::test_list_news_page_rows_hides_stale_disabled_projected_source_before_reprojection \
    tests/integration/domains/news_intel/test_news_repository.py::test_news_high_signal_candidates_hide_stale_disabled_projected_source_before_reprojection \
    tests/integration/domains/news_intel/test_news_repository.py::test_replace_page_rows_summary_counts_enabled_edges_only \
    tests/integration/domains/news_intel/test_news_repository.py::test_list_news_page_rows_requires_enabled_observation_edge -q
  ```
  Expected: pass.

### Task 4: Context Runtime And Schema Removal

- [ ] Remove context provider types, fetch worker persistence, repository context methods, brief input context fields, source quality context metrics/tags, status payload context fields, settings `context_policy`, and `config.example.yaml` context keys.
- [ ] Add forward hard-cut migration `20260603_0142_news_context_and_filter_hard_cut.py`.
- [ ] Delete context repository tests and rewrite unit tests that currently pass `context_items`.
- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_agent_policy.py \
    tests/unit/domains/news_intel/test_news_item_brief_input.py \
    tests/unit/domains/news_intel/test_news_workers.py \
    tests/unit/test_ops_projection_dirty_targets.py \
    tests/unit/domains/news_intel/test_news_projection_dirty_targets.py \
    tests/unit/domains/news_intel/test_source_quality_projection.py \
    tests/unit/domains/news_intel/test_news_source_quality_dirty_targets.py \
    tests/unit/test_api_news_contract.py \
    tests/unit/test_settings.py \
    tests/unit/test_postgres_schema.py \
    tests/integration/domains/news_intel/test_news_source_classification_repository.py \
    tests/integration/domains/news_intel/test_news_source_quality_repository.py -q
  ```
  Expected: pass.

- [ ] Confirm runtime code has no active context path:
  ```bash
  rg -n "NewsProviderContextObservation|context_observations|news_context_items|context_policy|NewsItemBriefContextItem|context_items|context_item_count|latest_context_seen_at_ms|useful_fact_or_context|_public_context_item_payload|news_context_written" \
    src/parallax/domains/news_intel src/parallax/app/runtime src/parallax/platform/config/settings.py
  ```
  Expected: no matches outside removed historical docs/migrations not included in this search.

### Task 5: Public Filter Cleanup

- [ ] Remove unreachable repository filters from `list_news_page_rows` and `_news_page_row_filter_sql`.
- [ ] Drop obsolete filter indexes in the new hard-cut migration.
- [ ] Delete integration tests for non-public News page filters.
- [ ] Add `test_list_news_page_rows_filters_by_query_text` so the remaining `q` filter stays covered after deleting non-public filter tests.
- [ ] Keep `/api/news` contract unchanged.
- [ ] Verify retired filter names no longer appear in repository read-path signatures or `_news_page_row_filter_sql`.
  ```bash
  uv run python - <<'PY'
  from pathlib import Path

  text = Path("src/parallax/domains/news_intel/repositories/news_repository.py").read_text()
  names = ("list_news_page_rows", "_news_page_row_filter_sql")
  retired = ("provider_type", "source_role", "trust_tier", "coverage_tag", "content_class", "content_tag", "decision_class", "direction")
  found = []
  for name in names:
      start = text.index(f"def {name}")
      end = text.find("\n    def ", start + 1)
      body = text[start:] if end == -1 else text[start:end]
      found.extend(f"{name}:{term}" for term in retired if term in body)
  if found:
      raise SystemExit("\n".join(found))
  print("ok")
  PY
  ```
  Expected: `ok`.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_api_news_contract.py \
    tests/integration/domains/news_intel/test_news_repository.py::test_list_news_page_rows_filters_by_signal \
    tests/integration/domains/news_intel/test_news_repository.py::test_list_news_page_rows_filters_by_query_text -q
  ```
  Expected: pass.

### Task 6: Hard-Cut Cleanup Command

- [ ] Add `news_intel_hard_cut_cleanup.py` service with dry-run and execute modes.
- [ ] Add execute prechecks for active News runtime state/leases before deleting.
- [ ] Clear news-originated notifications and reset source cursor/cache/health state.
- [ ] Wire `ops cleanup-news-intel-hard-cut --execute`.
- [ ] Add integration tests for dry-run, execute, active-runtime rejection, notification cleanup, and source health reset.
- [ ] Run:
  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_intel_hard_cut_cleanup.py -q
  uv run pytest tests/integration/test_cli.py -q
  uv run parallax ops cleanup-news-intel-hard-cut
  ```
  Expected: tests pass; CLI returns `execute: false` and table counts without deleting.

### Task 7: Legacy Tests And Docs

- [ ] Delete or rewrite tests that assert legacy public URL hard identity.
- [ ] Update `src/parallax/domains/news_intel/ARCHITECTURE.md`, `docs/WORKERS.md`, and `docs/CONTRACTS.md`.
- [ ] Update generated schema docs if the project’s generator is available in this worktree.
- [ ] Run:
  ```bash
  rg -n "all public URL|public URL hard identity|context observations|context_policy|news_context_items" \
    src/parallax/domains/news_intel/ARCHITECTURE.md docs/WORKERS.md docs/CONTRACTS.md
  ```
  Expected: no stale claims. Historical specs and old migrations may still mention old behavior.

### Task 8: Full Verification

- [ ] Run focused News Intel suite:
  ```bash
  uv run pytest tests/unit/domains/news_intel tests/integration/domains/news_intel -q
  ```
  Expected: pass.

- [ ] Run API/CLI/schema tests touched by this plan:
  ```bash
  uv run pytest tests/unit/test_api_news_contract.py tests/unit/test_settings.py tests/unit/test_postgres_schema.py tests/integration/test_cli.py -q
  ```
  Expected: pass.

- [ ] Run lint:
  ```bash
  uv run ruff check .
  ```
  Expected: pass.

- [ ] Run the hard-cut cleanup against a dev database only:
  ```bash
  # Confirm a dev DB backup/snapshot id is recorded before --execute.
  uv run parallax ops cleanup-news-intel-hard-cut
  uv run parallax ops cleanup-news-intel-hard-cut --execute
  uv run parallax ops worker-status
  ```
  Expected: dry run reports counts, execute clears News Intel data/news notifications and resets source fetch/health state, worker status remains healthy.

## PR Breakdown

1. **PR 1 — Identity and normalization hard cut:** edits text normalization, feed normalization, canonical identity, fetch content hash call, and identity tests.
2. **PR 2 — Provider key and projection correctness:** edits repository provider key handling, page projection loader, RSS/OpenNews expectations, and disabled representative tests.
3. **PR 3 — Context removal:** removes context runtime/schema/settings/brief paths and updates affected tests.
4. **PR 4 — Filter cleanup and ops cleanup:** removes non-public filters, adds `cleanup-news-intel-hard-cut`, and adds cleanup tests.
5. **PR 5 — Docs and verification:** updates architecture/contracts/workers docs and records final verification.

If implemented in one branch, keep commits aligned to the PR slices above.

## Rollout Order

1. Stop News Intel workers or deploy during a maintenance window.
2. Capture and record a PostgreSQL backup/snapshot id/path. Do not proceed to cleanup without this artefact.
3. Remove `context_policy` keys from `~/.parallax/config.yaml` if the pre-flight check finds any.
4. Deploy code and apply Alembic head, including `20260603_0142_news_context_and_filter_hard_cut.py`.
5. Validate config after deployment:
   ```bash
   uv run parallax config
   ```
   Expected: config loads, paths point at `~/.parallax/`, no secret values printed.
6. Confirm no active News runtime state before destructive cleanup:
   ```bash
   uv run parallax ops worker-status
   ```
   Expected: workers stopped/idle.
7. Run dry-run cleanup:
   ```bash
   uv run parallax ops cleanup-news-intel-hard-cut
   ```
8. Run execute cleanup only after confirming table counts are expected:
   ```bash
   uv run parallax ops cleanup-news-intel-hard-cut --execute
   ```
9. Restart News workers. The reset source cursors and `next_fetch_after_ms = 0` force fresh ingestion under the current policy.
10. Watch `uv run parallax ops worker-status` and `/api/news/sources/status` until enabled sources have fresh fetch runs and page rows.

## Rollback

- Code rollback before cleanup: revert the branch and do not run cleanup.
- Code rollback after context migration: old code that references `news_context_items` or `context_policy_json` is not compatible. Restore from DB backup or roll forward with the hard-cut code.
- Cleanup rollback: data deletion is intentionally not reversible. Recovery is fresh provider ingestion from configured sources or restoring the recorded pre-cleanup PostgreSQL snapshot.
- If fresh ingestion fails, keep the hard-cut code deployed and fix provider/runtime issues; do not reintroduce legacy identity or context compatibility paths.

## Acceptance Test Commands

- AC1 source-local ids do not merge globally:
  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_repository.py::test_source_local_item_keys_do_not_merge_across_feed_sources -q
  ```

- AC2 OpenNews provider-global id still dedups:
  ```bash
  uv run pytest \
    tests/integration/domains/news_intel/test_news_repository.py::test_opennews_provider_article_key_survives_source_item_key_drift \
    tests/integration/domains/news_intel/test_news_repository.py::test_opennews_provider_article_key_wins_before_content_identity -q
  ```

- AC3 aggregator/live/homepage URLs are not hard canonical URL identity:
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_canonical_identity.py::test_homepage_live_and_aggregator_urls_do_not_create_hard_url_identity -q
  ```

- AC4 invalid URL does not fail a fetch run:
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_text_normalization.py::test_canonicalize_url_returns_empty_for_invalid_ports \
    tests/unit/domains/news_intel/test_feed_item_normalizer.py::test_normalize_feed_entry_rejects_invalid_port_without_raising -q
  ```

- AC5 disabled source does not leak representative content:
  ```bash
  uv run pytest \
    tests/integration/domains/news_intel/test_news_repository.py::test_page_projection_loader_uses_enabled_edge_source_metadata_for_disabled_representative \
    tests/integration/domains/news_intel/test_news_repository.py::test_list_news_page_rows_hides_stale_disabled_projected_source_before_reprojection \
    tests/integration/domains/news_intel/test_news_repository.py::test_news_high_signal_candidates_hide_stale_disabled_projected_source_before_reprojection -q
  ```

- AC6 context path is gone:
  ```bash
  rg -n "NewsProviderContextObservation|context_observations|news_context_items|context_policy|NewsItemBriefContextItem|context_items|context_item_count|latest_context_seen_at_ms|useful_fact_or_context|_public_context_item_payload|news_context_written" \
    src/parallax/domains/news_intel src/parallax/app/runtime src/parallax/platform/config/settings.py
  ```

- AC7 content hash semantics match inputs:
  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_text_normalization.py::test_content_hash_is_stable_over_html_tracking_urls_and_case_noise \
    tests/unit/domains/news_intel/test_text_normalization.py::test_qualified_content_hash_rejects_generic_low_entropy_content \
    tests/unit/domains/news_intel/test_news_canonical_identity.py::test_generic_content_hash_does_not_create_strong_identity -q
  ```

- AC8 only public `/api/news` filters remain:
  ```bash
  uv run pytest tests/unit/test_api_news_contract.py -q
  uv run python - <<'PY'
  from pathlib import Path

  text = Path("src/parallax/domains/news_intel/repositories/news_repository.py").read_text()
  names = ("list_news_page_rows", "_news_page_row_filter_sql")
  retired = ("provider_type", "source_role", "trust_tier", "coverage_tag", "content_class", "content_tag", "decision_class", "direction")
  found = []
  for name in names:
      start = text.index(f"def {name}")
      end = text.find("\n    def ", start + 1)
      body = text[start:] if end == -1 else text[start:end]
      found.extend(f"{name}:{term}" for term in retired if term in body)
  if found:
      raise SystemExit("\n".join(found))
  print("ok")
  PY
  ```
  Expected: pytest passes and the script prints `ok`.

- AC9 hard-cut cleanup works:
  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_intel_hard_cut_cleanup.py -q
  uv run parallax ops cleanup-news-intel-hard-cut
  ```
  Expected: dry run includes News table counts, news notification counts, and safe active runtime state.

## Verification Artefact

Create `docs/superpowers/plans/active/2026-06-03-news-intel-hard-cut-residual-root-fix-verification-cn.md` before marking this plan complete. It must include:

- Git branch and commit hash.
- Whether `uv run parallax config` reported `~/.parallax/` paths, with secrets omitted.
- Pre-cleanup DB backup/snapshot id/path.
- Focused pytest commands and pass/fail output summaries.
- `uv run ruff check .` result.
- Dev DB cleanup dry-run and execute summaries, including News notification counts, active runtime precheck result, and source health reset counts.
- Any intentionally deleted tests and the current tests that replace their coverage.
