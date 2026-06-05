# News Intel Hard-Cut Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-cut retired News agent artifacts, add crypto analysis admission, project semantic story rows, and stop stock/macro/ticker-collision noise from becoming crypto high-signal output.

**Architecture:** Keep material News facts as truth and rebuild derived rows from durable dirty targets. The first slice prevents old current briefs from being served and changes cleanup from full News data wipe to retired artifact purge. The later slices add deterministic admission and story identity in `news_item_process`, then make `news_page_rows` and notifications story/admission aware.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic, pytest, Parallax worker runtime, `uv`, existing News Intel repository/projection/CLI patterns.

---

**Status**: Draft
**Date**: 2026-06-05
**Owning spec**: `docs/superpowers/specs/active/2026-06-05-news-intel-hard-cut-root-fix-cn.md`
**Worktree**: `.worktrees/news-intel-hard-cut-root-fix/`
**Branch**: `codex/news-intel-hard-cut-root-fix`

## Pre-flight

- [ ] Spec is approved. User approved by asking to write this plan after the draft spec.
- [ ] Create or enter the implementation worktree:
  ```bash
  git worktree add .worktrees/news-intel-hard-cut-root-fix -b codex/news-intel-hard-cut-root-fix codex/news-intel-hard-cut-residual-root-fix
  cd .worktrees/news-intel-hard-cut-root-fix
  git branch --show-current
  ```
  Expected branch: `codex/news-intel-hard-cut-root-fix`.
- [ ] Confirm real runtime config is operator-owned and secrets are not printed:
  ```bash
  uv run parallax config
  ```
  Expected evidence: `config_path` and `workers_config_path` point to `/Users/qinghuan/.parallax/`; report only redacted booleans/paths.
- [ ] Baseline lint:
  ```bash
  uv run ruff check .
  ```
  Expected: exit 0.
- [ ] Baseline targeted News tests:
  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_agent_policy.py \
    tests/unit/domains/news_intel/test_news_page_projection.py \
    tests/unit/domains/news_intel/test_news_workers.py \
    tests/unit/test_notification_rules.py \
    tests/integration/domains/news_intel/test_news_intel_hard_cut_cleanup.py \
    tests/integration/domains/news_intel/test_news_repository.py \
    tests/integration/domains/news_intel/test_news_page_rows_read_path.py
  ```
  Expected: exit 0 or list exact pre-existing failures before editing.
- [ ] Baseline full gate before final completion:
  ```bash
  make check-all
  ```
  Expected: exit 0 before declaring the implementation complete.

Known-failing baseline tests:

- None expected. If a baseline fails, record exact command, failure name, and whether it is unrelated before modifying source.

## File-Level Edits

### Contract Constants And Brief Guard

#### Modify `src/parallax/domains/news_intel/_constants.py`

- Keep the existing current brief constants:
  - `NEWS_ITEM_BRIEF_PROMPT_VERSION = "news-item-brief-v3"`
  - `NEWS_ITEM_BRIEF_SCHEMA_VERSION = "news_item_brief_v1"`
  - `NEWS_ITEM_BRIEF_VALIDATOR_VERSION = "news_item_brief_validator_v3"`
- Add new admission/story constants and update the existing page projection version:
  ```python
  NEWS_ANALYSIS_ADMISSION_VERSION = "news_analysis_admission_v1"
  NEWS_STORY_IDENTITY_VERSION = "news_story_identity_v1"
  NEWS_PAGE_PROJECTION_VERSION = "news_page_rows_v4"
  ```
- The page projection version bump hard-cuts old `news_page_rows_v3` serving rows; cleanup removes the old rows instead of retaining them.

#### Create `src/parallax/domains/news_intel/services/news_item_brief_contract.py`

Responsibility: one small module that defines the static current News brief contract for public/read-model guards.

- Export:
  ```python
  CURRENT_NEWS_ITEM_BRIEF_PROMPT_VERSION: str
  CURRENT_NEWS_ITEM_BRIEF_SCHEMA_VERSION: str
  CURRENT_NEWS_ITEM_BRIEF_VALIDATOR_VERSION: str
  CURRENT_NEWS_ITEM_BRIEF_CONTRACT: dict[str, str]
  is_current_news_item_brief_contract(row: Mapping[str, Any] | None) -> bool
  current_news_item_brief_sql_predicate(alias: str = "current_brief") -> str
  ```
- `is_current_news_item_brief_contract` returns true only when prompt/schema/validator match current constants. It does not compare `artifact_version_hash`; that value is runtime-provider-specific and remains enforced by `NewsItemBriefWorker` freshness plus cleanup artifact grouping.
- `current_news_item_brief_sql_predicate("current_brief")` returns a SQL fragment equivalent to:
  ```sql
  current_brief.prompt_version = 'news-item-brief-v3'
  AND current_brief.schema_version = 'news_item_brief_v1'
  AND current_brief.validator_version = 'news_item_brief_validator_v3'
  ```

#### Modify `src/parallax/domains/news_intel/repositories/news_repository.py`

- Import current contract helpers.
- Add a private helper:
  ```python
  def _current_brief_join_condition(alias: str = "current_brief") -> str
  ```
- Update all current brief joins to include the current contract predicate:
  - `load_items_for_page_projection` around lines 2438-2545.
  - `load_items_for_brief_targets` around lines 2572-2635.
  - `get_news_item_detail` around lines 2691-2728.
  - Source-quality ready brief aggregate around the `ready_brief_count` query.
- Update `_remap_item_scoped_agent_outputs_to_news_item` around lines 1612-1685 so remap ignores non-current current briefs and never migrates retired v1/v2/v4 rows to the canonical item.
- Update `_public_agent_brief_payload` around lines 4717-4744:
  - Return `{"status": "pending", "brief_json": {}}` if row is missing or non-current.
  - Allow only current `NewsItemBriefPayload` public fields: `status`, `direction`, `decision_class`, `title_zh`, `summary_zh`, `market_read_zh`, `bull_view`, `bear_view`, `affected_assets`, `watch_triggers`, `invalidation_conditions`, `data_gaps`, `evidence_refs`, `prompt_version`, `schema_version`, `validator_version`, `computed_at_ms`.
  - Do not pass through retired fields: `retrieval_notes_zh`, `source_consensus_zh`, `confirmation_state`, `novelty_status`, `used_tool_call_ids`, `impact_zh`, `watch_items_zh`, `confidence`.
- Add repository methods for cleanup:
  ```python
  news_legacy_agent_artifact_counts() -> dict[str, Any]
  delete_legacy_news_agent_artifacts(*, now_ms: int, current_artifact_version_hash: str | None = None) -> dict[str, int]
  delete_retired_news_page_rows(*, now_ms: int) -> dict[str, int]
  delete_retired_news_notifications() -> dict[str, int]
  ```
  These methods delete only retired agent/read-model/notification artifacts, not material facts.

### Artifact Cleanup And Ops Command

#### Modify `src/parallax/domains/news_intel/services/news_intel_hard_cut_cleanup.py`

- Replace current full-data wipe semantics. Today this service deletes `news_items`, provider observations, entities, mentions, and fact candidates. New semantics delete only:
  - Retired `news_item_agent_briefs` where prompt/schema/validator are not current, or `brief_json` contains retired research-tool fields.
  - Retired `news_item_agent_runs` where prompt/schema/validator are not current, or `request_json` / `response_json` contains `research_packet`, `tool_results`, `get_target_news_context`, `search_news_archive`, or `get_observation_history`.
  - Retired `news_page_rows` where `projection_version <> NEWS_PAGE_PROJECTION_VERSION`, `agent_brief_json.prompt_version` is non-current, or `agent_brief_json.brief_json` has retired fields.
  - Stale `news_projection_dirty_targets` for `projection_name='brief_input'` whose target already has a non-current brief cleanup decision.
  - `news_high_signal` notifications whose source row is retired or whose payload contains retired brief fields.
- Preserve:
  - `news_sources`
  - `news_fetch_runs`
  - `news_provider_items`
  - `news_item_observation_edges`
  - `news_items`
  - `news_item_entities`
  - `news_token_mentions`
  - `news_fact_candidates`
  - `news_source_quality_rows`
- Return dry-run/execute payload with:
  ```json
  {
    "mode": "dry_run|execute",
    "current_contract": {
      "prompt_version": "<current prompt version>",
      "schema_version": "<current schema version>",
      "validator_version": "<current validator version>",
      "artifact_version_hash": "optional"
    },
    "legacy_briefs_by_contract": [],
    "legacy_runs_by_contract": [],
    "retired_page_rows": 0,
    "retired_notifications": 0,
    "deleted": {},
    "preserved_material_facts": {}
  }
  ```
- Keep advisory lock/running worker guards. Execute mode aborts when News workers are active, a dirty target lease is active, or the optional runtime artifact hash check proves the running process still writes a retired contract.
- Keep the existing exception `NewsIntelHardCutCleanupAbort`.

#### Modify `src/parallax/app/surfaces/cli/parser.py`

- Keep existing command name `cleanup-news-intel-hard-cut`.
- Add explicit `--dry-run` while preserving default dry-run behavior when neither flag is supplied.
- Add optional `--current-artifact-version-hash` for operator-supplied exact artifact cleanup.
- Update help text to say it purges retired News agent/read-model artifacts, not all News facts.

#### Modify `src/parallax/app/surfaces/cli/commands/ops.py`

- Pass `dry_run`, `execute`, and optional artifact hash into `cleanup_news_intel_hard_cut`.
- On abort, keep returning `{"ok": false, "error": "<abort reason>"}` with exit 1.
- Add no secret output.

#### Modify `tests/integration/domains/news_intel/test_news_intel_hard_cut_cleanup.py`

- Rewrite the existing execute test. It currently expects material News tables to be emptied. New expectations:
  - Old current brief/run/page row/notification are deleted.
  - `news_items`, provider items, observation edges, entities, mentions, facts, fetch runs, and sources remain.
  - Dry-run reports old contracts but deletes nothing.
  - Execute aborts with active fetch run or active dirty lease.
- Add SpaceX-style old v2 seed:
  - current brief prompt `news-item-brief-synthesizer-v1`
  - schema `news_item_brief_v2`
  - `brief_json.retrieval_notes_zh`
  - run `request_json.tool_results.get_target_news_context`
  Expected after execute: zero old rows and material facts still present.

### Analysis Admission

#### Create `src/parallax/domains/news_intel/services/news_analysis_admission.py`

Responsibility: deterministic gate that separates broad News visibility from crypto analysis eligibility.

- Export dataclasses or frozen pydantic models:
  ```python
  NewsAnalysisAdmissionStatus = Literal["admitted", "page_only", "research_context", "suppressed", "needs_review"]

  @dataclass(frozen=True, slots=True)
  class NewsAnalysisAdmission:
      status: NewsAnalysisAdmissionStatus
      reason: str
      basis: dict[str, Any]
      version: str

  def decide_news_analysis_admission(
      *,
      item: Mapping[str, Any],
      token_mentions: Sequence[Mapping[str, Any]],
      fact_candidates: Sequence[Mapping[str, Any]],
  ) -> NewsAnalysisAdmission
  ```
- Admission rules:
  - `admitted` requires crypto-native evidence: allowed content class plus resolved crypto target or accepted crypto fact or source/title/body crypto subject evidence.
  - `page_only` for stock/private-company/commodity/common-word rows with no crypto-native evidence.
  - `research_context` for macro/geopolitical/energy rows that may affect broad crypto but lack specific crypto facts.
  - `needs_review` only for conflicting strong signals where deterministic rules cannot decide.
  - `suppressed` for disabled/source-policy rows if any are passed in.
- Treat provider score and provider token impacts as evidence, never sufficient alone.
- Treat `market_type` values outside crypto as non-crypto evidence.
- Treat common-word/equity/private-company collisions as negative evidence even when a token mention was resolved by context.

#### Modify `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`

- After classification/fact/mention generation, call `decide_news_analysis_admission`.
- Persist admission onto `news_items` with a new repository method before marking processed.
- Enqueue item brief work only when admission status is `admitted` and `news_item_agent_brief_eligibility` passes.
- Always enqueue page reprojection for processed rows so broad News still appears.

#### Modify `src/parallax/domains/news_intel/services/news_item_agent_policy.py`

- Add `analysis_admission_status` gate:
  - If item status is not `admitted`, return `eligible=False` with reason `analysis_not_admitted`.
  - Keep freshness and provider-source checks, but do not make provider score the only path.
  - Allow admitted crypto-native rows with provider score 65-79 when admission basis contains explicit crypto subject evidence.
- Keep `news_item_agent_brief_priority`; for admitted score 65-79 rows, priority is lower than score >=80 but still enqueueable.

#### Add `tests/unit/domains/news_intel/test_news_analysis_admission.py`

Test matrix:

- `test_spacex_private_company_is_page_only_even_with_spcx_provider_impacts`
- `test_samsung_equity_share_headline_is_page_only`
- `test_dram_hard_drive_story_does_not_admit_fil_from_symbol_collision`
- `test_hormuz_oil_geopolitics_is_research_context_not_crypto_driver`
- `test_zcash_orchard_bug_is_admitted_security_event`
- `test_jpm_citi_tokenized_deposit_story_is_admitted_crypto_market`
- `test_coinbase_btc_mortgage_score_70_is_admitted_with_crypto_subject`
- `test_common_word_symbols_do_not_create_crypto_admission`

#### Modify `tests/unit/domains/news_intel/test_news_item_agent_policy.py`

- Add tests:
  - `test_policy_rejects_provider_score_without_analysis_admission`
  - `test_policy_accepts_admitted_crypto_native_low_provider_score`
  - `test_policy_keeps_age_and_processed_guards`

#### Modify `tests/unit/domains/news_intel/test_news_workers.py`

- Add worker tests proving:
  - SpaceX/Samsung-like processed rows enqueue page work but not brief work.
  - Zcash/Coinbase-like processed rows enqueue both page work and brief work.
  - Process worker writes `analysis_admission_status`, `analysis_admission_reason`, and `analysis_admission_json`.

### Storage Migration For Admission And Story Identity

#### Create `src/parallax/platform/db/alembic/versions/20260605_0149_news_analysis_story_hard_cut.py`

Down revision: `20260604_0148`.

Upgrade DDL:

```sql
ALTER TABLE news_items
  ADD COLUMN IF NOT EXISTS analysis_admission_status TEXT NOT NULL DEFAULT 'needs_review',
  ADD COLUMN IF NOT EXISTS analysis_admission_reason TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS analysis_admission_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS analysis_admission_version TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS story_key TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS story_identity_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS story_identity_version TEXT NOT NULL DEFAULT '';

ALTER TABLE news_page_rows
  ADD COLUMN IF NOT EXISTS representative_news_item_id TEXT,
  ADD COLUMN IF NOT EXISTS story_key TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS story_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS analysis_admission_status TEXT NOT NULL DEFAULT 'needs_review',
  ADD COLUMN IF NOT EXISTS analysis_admission_reason TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS analysis_admission_json JSONB NOT NULL DEFAULT '{}'::jsonb;
```

Indexes:

```sql
CREATE INDEX IF NOT EXISTS ix_news_items_story_key_published
  ON news_items(story_key, published_at_ms DESC, news_item_id)
  WHERE story_key <> '';

CREATE INDEX IF NOT EXISTS ix_news_items_analysis_admission_published
  ON news_items(analysis_admission_status, published_at_ms DESC, news_item_id);

CREATE INDEX IF NOT EXISTS ix_news_page_rows_story_key
  ON news_page_rows(story_key, latest_at_ms DESC, row_id DESC)
  WHERE story_key <> '';

CREATE INDEX IF NOT EXISTS ix_news_page_rows_analysis_admission
  ON news_page_rows(analysis_admission_status, latest_at_ms DESC, row_id DESC);
```

Backfill:

- Initialize existing processed rows as `needs_review` with empty story key.
- Do not generate broad story groups in migration; use ops dirty-target enqueue and item processing/rebuild path.
- Analyze `news_items` and `news_page_rows`.

Downgrade:

- Raise `RuntimeError` because this hard-cut changes current row identity and cleanup may delete retired artifacts.

#### Modify `tests/unit/test_postgres_schema.py`

- Add migration checks for new columns and indexes.
- Assert no `news_story_groups` / `news_story_members` resurrection in this migration.

### Story Identity And Story-Shaped Page Projection

#### Create `src/parallax/domains/news_intel/services/news_story_identity.py`

Responsibility: deterministic story key and compact story metadata.

- Export:
  ```python
  @dataclass(frozen=True, slots=True)
  class NewsStoryIdentity:
      story_key: str
      confidence: str
      basis: dict[str, Any]
      version: str

  def build_news_story_identity(
      *,
      item: Mapping[str, Any],
      token_mentions: Sequence[Mapping[str, Any]],
      fact_candidates: Sequence[Mapping[str, Any]],
      admission: NewsAnalysisAdmission,
  ) -> NewsStoryIdentity
  ```
- Key rules:
  - Prefer provider article key groups when OpenNews article keys match.
  - Otherwise use normalized material title/subject fingerprint plus a bounded published-time bucket.
  - Include strong subjects such as `spacex`, `jpmorgan+citi+tokenized-deposit`, `zcash+orchard`, `trump+iran`, `ukraine+russia+sanctions`.
  - Drop weak stopwords and source prefixes (`WSJ:`, `NEW:`, bullet prefixes) before fingerprinting.
  - Keep story confidence in `strong`, `medium`, `weak`; weak story keys can still produce one row per item if grouping confidence is insufficient.

#### Modify `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`

- After admission, call `build_news_story_identity`.
- Persist `story_key`, `story_identity_json`, and `story_identity_version` on `news_items`.
- Use story key in page enqueue watermarks if available.

#### Modify `src/parallax/domains/news_intel/repositories/news_repository.py`

- Add:
  ```python
  update_item_analysis_and_story_identity(
      *,
      news_item_id: str,
      admission: Mapping[str, Any],
      story_identity: Mapping[str, Any],
      now_ms: int,
      commit: bool = True,
  ) -> None
  ```
- Add:
  ```python
  load_story_projection_payloads_for_items(*, news_item_ids: Sequence[str]) -> list[dict[str, Any]]
  replace_page_rows_for_story_targets(
      *,
      news_item_ids: Sequence[str],
      story_keys: Sequence[str],
      rows: Sequence[Mapping[str, Any]],
      commit: bool = True,
  ) -> dict[str, int]
  ```
- `load_story_projection_payloads_for_items` expands claimed item ids to their story keys, loads all current story members within a bounded recent window, and returns one payload per story key with:
  - representative item
  - member items
  - token/fact lanes by representative
  - source domain set
  - provider article key set
  - current-contract brief for representative only
- `replace_page_rows_for_story_targets` deletes stale v4 rows whose `story_key` is in scope or whose `news_item_id` is one of the scoped member ids but whose incoming row id is absent.
- Keep `payload_hash IS DISTINCT FROM` unchanged-write behavior.

#### Modify `src/parallax/domains/news_intel/services/news_page_projection.py`

- Update `build_news_page_row` signature:
  ```python
  def build_news_page_row(
      *,
      item: dict[str, Any],
      token_mentions: list[dict[str, Any]],
      fact_candidates: list[dict[str, Any]],
      agent_brief: dict[str, Any] | None = None,
      story: dict[str, Any] | None = None,
      computed_at_ms: int,
  ) -> dict[str, Any]:
  ```
- Use `story_key` for `row_id` when present:
  ```python
  row_id = _stable_id("news-page-row", NEWS_PAGE_PROJECTION_VERSION, story_key or news_item_id)
  ```
- Add row fields:
  - `representative_news_item_id`
  - `story_key`
  - `story`
  - `analysis_admission_status`
  - `analysis_admission_reason`
  - `analysis_admission`
- `_page_signal` must only set `alert_eligibility.in_app_eligible=True` when `analysis_admission_status == "admitted"` and either a ready driver/watch agent brief exists or provider evidence is crypto-admitted.
- Non-admitted rows still carry provider signal under `provider_signal`, but display as context/page-only rather than high-signal.

#### Modify `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py`

- Replace item-only projection path:
  - Claim `page` dirty targets as before.
  - Expand claimed ids through `load_story_projection_payloads_for_items`.
  - Build one row per story key or one row per item when no story key exists.
  - Call `replace_page_rows_for_story_targets`.
- Worker notes should include `story_groups_projected`, `story_member_items`, `projected`, `deleted`.

#### Modify `tests/unit/domains/news_intel/test_news_page_projection.py`

- Add tests:
  - `test_story_row_id_uses_story_key`
  - `test_non_admitted_provider_score_does_not_set_in_app_eligible`
  - `test_admitted_ready_brief_sets_external_push_ready`
  - `test_story_payload_includes_member_count_and_domains`

#### Modify `tests/unit/domains/news_intel/test_news_workers.py`

- Add page projection worker tests:
  - Same story claimed twice writes one row.
  - Old item-level row for a story member is deleted.
  - Unchanged story projection returns `unchanged` count.

#### Modify `tests/integration/domains/news_intel/test_news_repository.py`

- Add integration tests:
  - `test_story_projection_groups_jpm_citi_variants_into_one_page_row`
  - `test_story_projection_groups_spacex_variants_but_marks_page_only`
  - `test_replace_page_rows_for_story_targets_deletes_old_member_rows`
  - `test_page_row_payload_hash_skips_unchanged_story_row`

### Notifications And Public API Read Path

#### Modify `src/parallax/domains/news_intel/repositories/news_repository.py`

- Update `_list_projected_news_page_rows` and `_page_row_payload` to expose story/admission fields.
- Update `list_news_high_signal_notification_candidates` around lines 1995-2058:
  - Filter `analysis_admission_status = 'admitted'`.
  - Filter `projection_version = NEWS_PAGE_PROJECTION_VERSION`.
  - Keep enabled observation edge requirement.
  - Return `story_key`, `story_json`, and admission fields.
- Update `get_news_item_detail` around lines 2691-2861:
  - Include `story_key`, `story_identity`, and `analysis_admission` from item/page row.
  - Use current-contract brief only.

#### Modify `src/parallax/domains/notifications/services/notification_rules.py`

- `_news_high_signal_candidates`:
  - Skip any row where `analysis_admission_status != "admitted"`.
  - Use `story_key` in semantic signature and external push signature.
  - Entity key should prefer `news_story:{story_key}`; fallback to `news_item:{news_item_id}` only when no story key exists.
- `_news_semantic_signature`:
  - Include `story_key`, `decision_class`, `direction`, and affected assets.
  - Do not derive uniqueness from only headline/token symbols.

#### Modify `tests/unit/test_notification_rules.py`

- Add tests:
  - `test_news_high_signal_skips_page_only_provider_score`
  - `test_news_high_signal_uses_story_key_for_dedup`
  - `test_news_external_push_still_requires_ready_brief`
  - `test_jpm_citi_story_variants_emit_one_candidate`

#### Modify `tests/unit/test_api_news_contract.py`

- Add API contract tests:
  - `/api/news` rows include `story_key`, `story`, and `analysis_admission_status`.
  - `/api/news/items/{id}` excludes retired brief fields even when DB has old brief rows.
  - Missing/non-current brief renders pending/stale/absent state, not old JSON.

### Runtime Tool Removal Guardrails

#### Modify `tests/architecture/test_news_intel_kiss_simplification.py`

- Add assertions:
  - No files matching `src/parallax/domains/news_intel/services/news_item_research_*.py`.
  - No imports or references to `get_target_news_context`, `search_news_archive`, or `get_observation_history` under `src/parallax/domains/news_intel`.
  - `news_item_brief.md` still contains the no-tool/no-external-data rule.

#### Modify `tests/architecture/test_worker_runtime_contracts.py`

- Update News page projection identity expectation if row identity is now story-aware. It remains `("news_page_rows", ("row_id",))`, but add assertion that worker manifest ordering keys do not include run/generation/timestamp identity.
- Add `analysis_admission_status` as a required field for `news_page_rows` contract if this test enumerates fields.

### Ops Projection Dirty Target Repair

#### Modify `src/parallax/app/runtime/projection_dirty_targets.py`

- `_fetch_news_item_rows` must include `analysis_admission_status`, admission JSON, story key, story identity, token mentions, and fact candidates.
- `_row_brief_eligible` must use the updated `news_item_agent_brief_eligibility`, which rejects non-admitted rows.
- `--projection page` can enqueue all recent page rows without requiring `--since-hours`; `--projection brief_input` remains bounded.

#### Modify `tests/unit/test_ops_projection_dirty_targets.py`

- Add tests:
  - `test_news_projection_repair_enqueues_page_for_page_only_rows`
  - `test_news_projection_repair_does_not_enqueue_brief_for_page_only_rows`
  - `test_news_projection_repair_enqueues_brief_for_admitted_crypto_rows`

### Documentation

#### Modify `src/parallax/domains/news_intel/ARCHITECTURE.md`

- Update Stage Map:
  ```text
  news_fetch -> news_item_process(admission + story identity) -> news_page_projection(story rows)
  news_item_process(admitted only) -> news_item_brief -> news_page_projection
  ```
- State that provider token impacts are evidence, not crypto identity.
- State that story identity is rebuildable projection state stored on facts/read rows for current serving, not a separate material truth table.

#### Modify `docs/CONTRACTS.md`

- Update News Intel contract:
  - `/api/news` rows are story-shaped.
  - `analysis_admission_status` separates page visibility from crypto analysis.
  - `/api/news/items/{id}` never exposes retired agent fields.
  - Notifications read admitted story-level rows only.

#### Modify `docs/RELIABILITY.md`

- Add a short News-specific note under current read models:
  - Story row id is stable by `NEWS_PAGE_PROJECTION_VERSION + story_key`.
  - Dirty target wake remains item-scoped but worker expands to bounded story group.
  - No broad idle scan is introduced.

## PR Breakdown

1. **PR 1 — Retired artifact hard cut**: brief contract helper, repository current-brief guards, sanitized public brief payload, artifact-only cleanup semantics, CLI option updates, cleanup tests. Mergeable on its own and immediately stops old brief leakage.
2. **PR 2 — Analysis admission**: migration columns, admission service, process worker persistence, brief policy gate, admission unit/worker tests. Depends on PR 1 for current-brief safety.
3. **PR 3 — Story-shaped page projection**: story identity service, story projection repository methods, projection worker update, `news_page_rows_v4`, story row tests. Depends on PR 2 because story rows need admission fields.
4. **PR 4 — Notification/API hardening**: high-signal notification filters/dedup, public API story/admission fields, API and notification tests. Depends on PR 3.
5. **PR 5 — Architecture/docs/ops verification**: architecture guardrails, docs updates, real-data dry-run audit instructions, verification artefact. Depends on PR 1-4.

## Task Checklist

### Task 1: Current Brief Contract Guard

**Files:**
- Create: `src/parallax/domains/news_intel/services/news_item_brief_contract.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `tests/integration/domains/news_intel/test_news_repository.py`
- Modify: `tests/unit/test_api_news_contract.py`

- [ ] Write failing integration test where an old v2 current brief exists for an item and `load_items_for_page_projection` returns `current_brief is None`.
- [ ] Write failing detail/API test where old `brief_json.retrieval_notes_zh` exists and public payload returns pending/absent without retired fields.
- [ ] Add the contract helper module with static prompt/schema/validator checks.
- [ ] Apply current-contract join predicates to page projection, brief targets, item detail, source quality, and duplicate remap current-brief selection.
- [ ] Sanitize `_public_agent_brief_payload`.
- [ ] Run:
  ```bash
  uv run pytest \
    tests/integration/domains/news_intel/test_news_repository.py::test_load_items_for_page_projection_ignores_non_current_brief \
    tests/unit/test_api_news_contract.py::test_news_item_detail_hides_retired_brief_fields
  ```

### Task 2: Artifact-Only Cleanup

**Files:**
- Modify: `src/parallax/domains/news_intel/services/news_intel_hard_cut_cleanup.py`
- Modify: `src/parallax/app/surfaces/cli/parser.py`
- Modify: `src/parallax/app/surfaces/cli/commands/ops.py`
- Modify: `tests/integration/domains/news_intel/test_news_intel_hard_cut_cleanup.py`

- [ ] Rewrite cleanup tests so execute preserves `news_items`, provider items, observation edges, entities, mentions, facts, fetch runs, and sources.
- [ ] Add dry-run assertions for old prompt/schema/validator grouped counts.
- [ ] Change cleanup service to delete retired brief/run/page/notification artifacts only.
- [ ] Keep active worker/advisory lock abort behavior.
- [ ] Add explicit `--dry-run` and optional `--current-artifact-version-hash` parser fields.
- [ ] Run:
  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_intel_hard_cut_cleanup.py
  ```

### Task 3: Admission Storage And Decision Service

**Files:**
- Create: `src/parallax/platform/db/alembic/versions/20260605_0149_news_analysis_story_hard_cut.py`
- Create: `src/parallax/domains/news_intel/services/news_analysis_admission.py`
- Modify: `src/parallax/domains/news_intel/_constants.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `tests/unit/test_postgres_schema.py`
- Create: `tests/unit/domains/news_intel/test_news_analysis_admission.py`

- [ ] Add failing schema test for admission/story columns and indexes.
- [ ] Add admission unit tests for SpaceX, Samsung, DRAM, Hormuz, Zcash, JPM/Citi, Coinbase/BTC mortgage, and common-word symbols.
- [ ] Add migration DDL and indexes.
- [ ] Implement deterministic admission service.
- [ ] Add repository persistence method.
- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/test_postgres_schema.py \
    tests/unit/domains/news_intel/test_news_analysis_admission.py
  ```

### Task 4: Process Worker And Brief Policy Gate

**Files:**
- Modify: `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- Modify: `src/parallax/domains/news_intel/services/news_item_agent_policy.py`
- Modify: `src/parallax/app/runtime/projection_dirty_targets.py`
- Modify: `tests/unit/domains/news_intel/test_news_item_agent_policy.py`
- Modify: `tests/unit/domains/news_intel/test_news_workers.py`
- Modify: `tests/unit/test_ops_projection_dirty_targets.py`

- [ ] Write failing policy tests for non-admitted provider score rejection and admitted low-score crypto acceptance.
- [ ] Write failing process worker tests for page-only rows not enqueuing brief work.
- [ ] Persist admission in process worker before brief enqueue.
- [ ] Make policy require `analysis_admission_status='admitted'`.
- [ ] Make ops dirty target repair use the same policy.
- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_agent_policy.py \
    tests/unit/domains/news_intel/test_news_workers.py \
    tests/unit/test_ops_projection_dirty_targets.py
  ```

### Task 5: Story Identity

**Files:**
- Create: `src/parallax/domains/news_intel/services/news_story_identity.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Create: `tests/unit/domains/news_intel/test_news_story_identity.py`
- Modify: `tests/unit/domains/news_intel/test_news_workers.py`

- [ ] Add story identity tests for SpaceX variants, JPM/Citi variants, Zcash follow-ups, Trump/Iran fragments, and weak unrelated titles.
- [ ] Implement story key builder with normalized subject/title/time/source evidence.
- [ ] Persist story identity in `news_item_process`.
- [ ] Add repository write method if not already done in Task 3.
- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_story_identity.py \
    tests/unit/domains/news_intel/test_news_workers.py
  ```

### Task 6: Story-Shaped Page Projection

**Files:**
- Modify: `src/parallax/domains/news_intel/services/news_page_projection.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `tests/unit/domains/news_intel/test_news_page_projection.py`
- Modify: `tests/unit/domains/news_intel/test_news_workers.py`
- Modify: `tests/integration/domains/news_intel/test_news_repository.py`
- Modify: `tests/integration/domains/news_intel/test_news_page_rows_read_path.py`

- [ ] Write failing projection unit tests for story row id, admission alert eligibility, and member count.
- [ ] Write failing integration test proving JPM/Citi variants collapse to one row.
- [ ] Add story payload to page row builder and bump page projection version to v4.
- [ ] Add story projection loading/replacement repository methods.
- [ ] Update page projection worker to expand claimed item ids to story payloads.
- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_page_projection.py \
    tests/unit/domains/news_intel/test_news_workers.py \
    tests/integration/domains/news_intel/test_news_repository.py \
    tests/integration/domains/news_intel/test_news_page_rows_read_path.py
  ```

### Task 7: Notifications And API

**Files:**
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `src/parallax/domains/notifications/services/notification_rules.py`
- Modify: `tests/unit/test_notification_rules.py`
- Modify: `tests/unit/test_api_news_contract.py`
- Modify: `tests/integration/test_notification_repository.py`
- Modify: `tests/integration/test_notification_worker.py`

- [ ] Write failing notification tests for page-only provider score skip and story-key dedup.
- [ ] Write failing API contract tests for story/admission fields and retired-field absence.
- [ ] Filter high-signal candidates to admitted story rows.
- [ ] Add story key into notification dedup signatures and entity keys.
- [ ] Expose story/admission fields through public read payloads.
- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/test_notification_rules.py \
    tests/unit/test_api_news_contract.py \
    tests/integration/test_notification_repository.py \
    tests/integration/test_notification_worker.py
  ```

### Task 8: Architecture Guardrails And Docs

**Files:**
- Modify: `tests/architecture/test_news_intel_kiss_simplification.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`
- Modify: `src/parallax/domains/news_intel/ARCHITECTURE.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/RELIABILITY.md`

- [ ] Add architecture tests proving old runtime research tools are absent.
- [ ] Add worker contract assertions for story/admission projection identity.
- [ ] Update News Intel architecture docs.
- [ ] Update public contracts.
- [ ] Update reliability notes.
- [ ] Run:
  ```bash
  uv run pytest \
    tests/architecture/test_news_intel_kiss_simplification.py \
    tests/architecture/test_worker_runtime_contracts.py
  ```

## Rollout Order

1. Merge/deploy PR 1 first to stop serving old current brief contracts.
2. Apply migration `20260605_0149_news_analysis_story_hard_cut.py`.
3. Deploy PR 2-4 code so current runtime writes admission/story/page v4 rows and cannot write old research-tool brief artifacts.
4. Confirm runtime contract:
   ```bash
   uv run parallax config
   ```
   Expected: config path under `/Users/qinghuan/.parallax/`, News workers enabled, no old prompt/schema in local constants.
5. Dry-run cleanup:
   ```bash
   uv run parallax ops cleanup-news-intel-hard-cut --dry-run
   ```
   Expected: reports old v1/v2/v4 artifact counts, retired page rows, retired notifications, and preserved material facts.
6. Execute cleanup only after dry-run looks correct and News workers are stopped or advisory locks are available:
   ```bash
   uv run parallax ops cleanup-news-intel-hard-cut --execute
   ```
   Expected: old artifacts deleted; material facts preserved.
7. Enqueue page rebuild for recent News:
   ```bash
   uv run parallax ops enqueue-projection-dirty-targets --domain news --projection page --since-hours 12 --execute
   ```
   Expected: page dirty targets enqueued for recent rows.
8. Enqueue admitted brief backlog for bounded recent window:
   ```bash
   uv run parallax ops enqueue-projection-dirty-targets --domain news --projection brief_input --since-hours 8 --execute
   ```
   Expected: brief targets only for admitted crypto rows.
9. Let workers drain or run worker once via the existing runtime path.
10. Run live read-only audit queries:
    - No `news-item-brief-synthesizer-v1`.
    - No `news_item_brief_v2`.
    - No page rows with retired brief fields.
    - Recent SpaceX/Samsung/DRAM/Hormuz rows are page-only/context.
    - Recent Zcash/JPM/Coinbase crypto rows are admitted or queued.

## Rollback

- Migration rollback is not safe after cleanup because retired artifacts may be deleted. Recovery is restore from DB backup or rebuild current read models from material facts.
- If PR 2 admission is too strict, adjust admission rules and reprocess recent `news_items`; do not re-enable provider-score-only brief admission.
- If PR 3 story grouping over-merges, lower story confidence thresholds and re-enqueue page projection. Material facts remain intact.
- If cleanup execute deletes an artifact class unexpectedly, stop News workers, restore from backup if required, and rerun dry-run with narrower predicates. Material facts should not require restore if cleanup obeyed this plan.
- If notification volume drops too far, tune admission rules; do not remove story/admission filters from notification candidate discovery.

## Acceptance Test Commands

- AC1:
  ```bash
  uv run parallax ops cleanup-news-intel-hard-cut --dry-run
  ```
  Expected: JSON contains `legacy_briefs_by_contract`, `legacy_runs_by_contract`, `retired_page_rows`, `preserved_material_facts`, and no deletes occur.
- AC2:
  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_intel_hard_cut_cleanup.py
  ```
  Expected: old artifact rows deleted in execute test; material facts preserved.
- AC3:
  ```bash
  uv run pytest tests/unit/test_api_news_contract.py::test_news_item_detail_hides_retired_brief_fields
  ```
  Expected: retired fields absent.
- AC4:
  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_repository.py::test_load_items_for_page_projection_ignores_non_current_brief
  ```
  Expected: old current brief treated as absent.
- AC5:
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_analysis_admission.py::test_spacex_private_company_is_page_only_even_with_spcx_provider_impacts
  ```
  Expected: not admitted.
- AC6:
  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_repository.py::test_story_projection_groups_jpm_citi_variants_into_one_page_row
  ```
  Expected: one story row and member count > 1.
- AC7:
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_analysis_admission.py::test_hormuz_oil_geopolitics_is_research_context_not_crypto_driver
  ```
  Expected: not admitted.
- AC8:
  ```bash
  uv run pytest tests/unit/domains/news_intel/test_news_analysis_admission.py::test_coinbase_btc_mortgage_score_70_is_admitted_with_crypto_subject
  ```
  Expected: admitted.
- AC9:
  ```bash
  uv run pytest tests/architecture/test_news_intel_kiss_simplification.py
  ```
  Expected: no runtime research tools; if a future context packet is added, tests must assert `matched_count`, `returned_count`, and `emitted_count` semantics before merging.
- AC10:
  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_repository.py::test_page_row_payload_hash_skips_unchanged_story_row
  ```
  Expected: unchanged projection writes zero serving rows.

## Verification

Create `docs/superpowers/plans/active/2026-06-05-news-intel-hard-cut-root-fix-verification-cn.md` before declaring completion.

Required verification contents:

- Full `make check-all` output.
- Targeted pytest command outputs listed above.
- Dry-run cleanup JSON with secrets redacted.
- Execute cleanup JSON from local/staging DB after operator approval.
- Read-only DB audit:
  ```sql
  SELECT prompt_version, schema_version, validator_version, status, COUNT(*)
  FROM news_item_agent_briefs
  GROUP BY 1, 2, 3, 4
  ORDER BY COUNT(*) DESC;
  ```
  Expected: no retired prompt/schema rows.
- Recent 4-6h audit table:
  - total rows
  - admitted rows
  - page-only rows
  - research-context rows
  - high-score provider rows not admitted
  - crypto-native admitted rows below provider score 80
- Manual item checks:
  - SpaceX target item
  - Samsung shares
  - DRAM/hard drives
  - Hormuz/oil
  - Zcash Orchard
  - JPM/Citi tokenized deposit
  - Coinbase/BTC mortgage if present

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/active/2026-06-05-news-intel-hard-cut-root-fix-cn.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, faster iteration with bounded write scopes.
2. **Inline Execution** - execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.
