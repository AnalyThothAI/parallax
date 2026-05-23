# Narrative Intelligence Throughput CQRS Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft
**Date:** 2026-05-19
**Owning spec:** `docs/superpowers/specs/active/2026-05-19-narrative-intel-throughput-cqrs-hard-cut-cn.md`
**Worktree:** `.worktrees/narrative-intel-throughput-cqrs-hard-cut/`
**Branch:** `codex/narrative-intel-throughput-cqrs-hard-cut`

**Goal:** 根治 Token Radar 大范围显示"叙事不足"的问题：把 Narrative Intelligence 的 admission/source-set、semantic labeling、discussion digest 三段 CQRS 写边界切开，清掉历史错误积压，并让 digest 状态从 source facts 而不是 semantics backlog 推导。

**Architecture:** `TokenRadarProjectionWorker` 继续拥有 Radar projection；新增 `NarrativeAdmissionWorker` 独占写 `narrative_admissions`；`MentionSemanticsWorker` 只写 `token_mention_semantics`；`TokenDiscussionDigestWorker` 只写 `token_discussion_digests`。API 和 frontend 只消费 read models，不做 provider calls、不写 read models、不补兼容路径。

**Tech Stack:** Python 3.13, psycopg, Alembic, FastAPI, Pydantic v2, PostgreSQL, pytest, ruff, React, TypeScript, Vitest.

---

## Pre-flight

- [ ] Read owning spec fully.
- [ ] Create worktree:
  ```bash
  git worktree add .worktrees/narrative-intel-throughput-cqrs-hard-cut -b codex/narrative-intel-throughput-cqrs-hard-cut main
  ```
- [ ] Verify clean branch:
  ```bash
  cd .worktrees/narrative-intel-throughput-cqrs-hard-cut
  git branch --show-current
  git status --short
  ```
- [ ] Confirm real runtime config paths before any live-data diagnosis:
  ```bash
  uv run gmgn-twitter-intel config
  ```
  Expected: `config_path` and `workers_config_path` point at `~/.gmgn-twitter-intel/`. Do not print secrets.
- [ ] Capture baseline without changing data:
  - authenticated `/api/status/narrative-health?since_hours=4`;
  - authenticated `/api/status`;
  - authenticated `/api/token-radar?window=1h&scope=all`;
  - authenticated `/api/token-radar?window=4h&scope=all`;
  - authenticated `/api/token-radar?window=24h&scope=all`.
- [ ] Run baseline tests:
  ```bash
  uv run ruff check .
  uv run pytest tests/unit/domains/narrative_intel -q
  uv run pytest tests/integration/test_narrative_repository.py -q
  uv run pytest tests/unit/test_api_narrative_contract.py -q
  ```

If integration tests require local PostgreSQL and it is unavailable, record that explicitly and run them before merge in an environment with Postgres.

---

## Implementation Order

Do this as one hard-cut branch. Do not ship a partial state where web expects the new status contract but backend still computes source count from semantics, or where backend writes new statuses but frontend maps them to old "叙事不足" text.

1. Add failing tests for architecture and state rules.
2. Add migration for admission source-set metadata.
3. Add latest-frontier/source-set query.
4. Add `NarrativeAdmissionWorker`.
5. Refactor `MentionSemanticsWorker` to claim-first and admission-source-only.
6. Refactor digest context/status rules.
7. Add formal drain/rebuild ops command.
8. Update health/API/frontend contract.
9. Update docs and generated contract artefacts.
10. Run local and live verification.

---

## Step 1 — Guardrail Tests First

- [ ] Add/update unit tests proving `DiscussionDigestService.refresh_decision` uses source-set count:
  - source set count 10, labeled count 0, pending/unseen semantics -> `pending`, reason `semantic_labeling_pending`;
  - source set count 2 below threshold -> `insufficient`, reason `low_source_volume`;
  - source set count enough, all terminal unavailable -> `semantic_unavailable` or pending reason according to implemented state contract;
  - labeled coverage above threshold -> refresh provider.

- [ ] Add integration test for latest Radar frontier:
  - seed `token_radar_projection_coverage` with latest ready `computed_at_ms=2000`;
  - seed current Radar rows for `computed_at_ms=2000`;
  - seed latest rows with fewer/lower ranks;
  - query admission frontier;
  - assert only `computed_at_ms=2000` rows are returned.

- [ ] Add worker boundary tests:
  - `NarrativeAdmissionWorker.SINGLE_WRITER_KEY` exists and writes `narrative_admissions`;
  - `MentionSemanticsWorker` source no longer references `upsert_admissions_from_radar_rows`, `admitted_radar_rows`, or `source_mentions_for_admission`;
  - API route modules do not import `NarrativeIntelProvider` or write repositories.

- [ ] Add regression test for digest context:
  - seed admission source ids and events;
  - seed no semantics;
  - assert `digest_context.source_event_count == len(source_event_ids)` and `semantic_rows` left join is empty/pending, not source count zero.

Target files:

- `tests/unit/domains/narrative_intel/test_discussion_digest_service.py`
- `tests/integration/test_narrative_repository.py`
- `tests/unit/domains/narrative_intel/test_narrative_workers.py`
- `tests/architecture/test_worker_runtime_contracts.py`
- `tests/architecture/test_src_domain_architecture.py`

Run expected failing subset:

```bash
uv run pytest tests/unit/domains/narrative_intel/test_discussion_digest_service.py -q
uv run pytest tests/integration/test_narrative_repository.py -q
uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py -q
```

---

## Step 2 — Migration 0064 For Source-Set Admission

- [ ] Create Alembic revision after `20260518_0063`:
  - `src/gmgn_twitter_intel/platform/db/alembic/versions/20260519_0064_narrative_admission_source_sets.py`

- [ ] Add source-set metadata to `narrative_admissions`:
  ```sql
  ALTER TABLE narrative_admissions
    ADD COLUMN IF NOT EXISTS projection_computed_at_ms BIGINT,
    ADD COLUMN IF NOT EXISTS source_window_start_ms BIGINT,
    ADD COLUMN IF NOT EXISTS source_window_end_ms BIGINT,
    ADD COLUMN IF NOT EXISTS source_event_count BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS independent_author_count BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS admission_generation TEXT;
  ```

- [ ] Add indexes:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_narrative_admissions_projection_frontier
    ON narrative_admissions("window", scope, schema_version, projection_computed_at_ms DESC, status);

  CREATE INDEX IF NOT EXISTS idx_narrative_admissions_source_fingerprint
    ON narrative_admissions(target_type, target_id, "window", scope, schema_version, source_fingerprint);
  ```

- [ ] Do not create a compatibility migration that backfills source counts from `token_mention_semantics`. Existing rows will be rebuilt by the formal drain/rebuild command.

- [ ] Add schema integration checks in:
  - `tests/integration/test_postgres_schema_runtime.py`
  - `tests/integration/test_narrative_repository.py`

Run:

```bash
uv run pytest tests/integration/test_postgres_schema_runtime.py tests/integration/test_narrative_repository.py -q
```

---

## Step 3 — Latest Frontier And Source-Set Query

- [ ] Refactor `NarrativeSourceQuery.admitted_radar_rows` to read through `token_radar_projection_coverage`.

Required behavior:

```sql
WITH latest AS (
  SELECT computed_at_ms
  FROM token_radar_projection_coverage
  WHERE projection_version = %(projection_version)s
    AND "window" = %(window)s
    AND scope = %(scope)s
    AND status = 'ready'
    AND computed_at_ms IS NOT NULL
)
SELECT rows.*
FROM token_radar_current_rows rows
JOIN latest ON latest.computed_at_ms = rows.computed_at_ms
WHERE rows.projection_version = %(projection_version)s
  AND rows."window" = %(window)s
  AND rows.scope = %(scope)s
ORDER BY rows.rank ASC
LIMIT %(limit)s
```

- [ ] Add a source-set query that builds source facts for one current admission target:
  - reads `events` + `token_intent_resolutions`;
  - bounds by `window`;
  - applies `events.is_watched = true` for `matched`;
  - returns event ids, max received time, source count, independent author count;
  - has a hard `source_limit`.

- [ ] Keep `token_radar_current_rows.source_event_ids_json` as an optional seed/diagnostic only. Source count must be computed from source facts/source set.

Target files:

- `src/gmgn_twitter_intel/domains/narrative_intel/queries/narrative_source_query.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`
- `tests/integration/test_narrative_repository.py`

Run:

```bash
uv run pytest tests/integration/test_narrative_repository.py -q
```

---

## Step 4 — Add NarrativeAdmissionWorker

- [ ] Create `src/gmgn_twitter_intel/domains/narrative_intel/runtime/narrative_admission_worker.py`.

Responsibilities:

- iterate configured windows/scopes;
- read latest ready Radar frontier;
- build source sets;
- upsert `narrative_admissions` with source-set metadata;
- suppress admissions no longer in current frontier;
- emit wake hint for narrative semantics/digest;
- report notes:
  - `frontier_rows`;
  - `source_events`;
  - `admissions_upserted`;
  - `admissions_suppressed`;
  - `coverage_missing`;
  - `source_query_ms`.

- [ ] Move admission reconciliation ownership out of `MentionSemanticsWorker`.

- [ ] Wire worker settings and factory:
  - `src/gmgn_twitter_intel/app/runtime/worker_factories/narrative_intel.py`
  - `src/gmgn_twitter_intel/app/runtime/worker_registry.py`
  - `src/gmgn_twitter_intel/platform/config/settings.py`
  - `tests/unit/test_worker_settings.py`
  - `tests/unit/test_bootstrap_worker_runtime_wiring.py`

- [ ] Update `docs/WORKERS.md` inventory.

Run:

```bash
uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py -q
```

---

## Step 5 — Refactor MentionSemanticsWorker

- [ ] Change `run_once_async` order:
  1. claim due semantic rows;
  2. if rows exist, call provider and complete batch;
  3. if no rows or backlog below low-water mark, enqueue missing semantics from current admissions source sets;
  4. never scan source facts here.

- [ ] Replace `_reconcile_admissions_and_enqueue_sync` with a smaller method:
  - reads due/current admissions;
  - expands `source_event_ids_json`;
  - inserts missing `token_mention_semantics` rows;
  - respects global `max_semantic_rows_enqueued_per_cycle`;
  - respects per-target pending cap;
  - updates `next_semantics_due_at_ms`.

- [ ] Add `FOR UPDATE SKIP LOCKED` when claiming due rows if current DB abstraction allows it.

- [ ] Remove imports:
  - `NarrativeAdmissionService`;
  - `TOKEN_RADAR_PROJECTION_VERSION`.

- [ ] Remove worker notes that imply admission scanning from semantics:
  - `admission_radar_rows`;
  - `admission_source_mentions`;
  - `admission_due_admissions` from source scanning path.

New notes should separate:

- `claimed`;
- `labeled`;
- `semantic_unavailable`;
- `failed`;
- `enqueued_missing`;
- `enqueue_budget_remaining`;
- `pending_backlog_before`;
- `backpressure_skipped_enqueue`.

Run:

```bash
uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py -q
uv run pytest tests/unit/domains/narrative_intel/test_mention_semantics_service.py -q
```

---

## Step 6 — Fix Digest Context And Status Rules

- [ ] Rewrite repository `digest_context`:
  - find current admission by target/window/scope/schema;
  - expand `narrative_admissions.source_event_ids_json`;
  - join `events` for text/author/tweet refs;
  - left join current `token_mention_semantics`;
  - compute `source_event_count` from source set;
  - compute `labeled_event_count` from semantics status;
  - compute pending/unseen/terminal unavailable counts explicitly.

- [ ] Update `DiscussionDigestService.refresh_decision`:
  - `low_source_volume` only uses source-set count;
  - source sufficient + pending/unseen semantics -> `pending/semantic_labeling_pending`;
  - source sufficient + provider backpressure -> `pending/semantic_provider_backpressure`;
  - all terminal unavailable -> `semantic_unavailable/semantic_provider_unavailable`;
  - low coverage with no pending/unseen -> `insufficient/low_semantic_coverage`.

- [ ] Ensure pending digest replaces stale current digest when source fingerprint changes. Do not reuse old ready digest as current for a new source set.

- [ ] Keep provider call gated behind source volume and semantic coverage thresholds.

Target files:

- `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/services/discussion_digest_service.py`
- `src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
- `tests/unit/domains/narrative_intel/test_discussion_digest_service.py`
- `tests/integration/test_narrative_repository.py`

Run:

```bash
uv run pytest tests/unit/domains/narrative_intel/test_discussion_digest_service.py tests/integration/test_narrative_repository.py -q
```

---

## Step 7 — Formal Backlog Drain/Rebuild

- [ ] Add an ops command under the existing CLI style. Suggested public surface:
  ```bash
  uv run gmgn-twitter-intel narrative rebuild --windows 1h,4h,24h --scopes all,matched
  ```

If the project prefers `ops` grouping, use:

```bash
uv run gmgn-twitter-intel ops narrative-rebuild --windows 1h,4h,24h --scopes all,matched
```

Pick the shape that matches current CLI conventions; do not create both.

- [ ] Command behavior:
  1. acquire narrative worker advisory locks or require workers paused;
  2. rebuild current admissions from latest ready Radar coverage;
  3. suppress/delete obsolete admissions outside current frontier;
  4. delete queued/retryable/stale semantics not referenced by current admissions;
  5. reset retryable semantics referenced by current admissions to `next_retry_at_ms=0`;
  6. mark digests stale or replace with pending when source fingerprint differs;
  7. print redacted counts only.

- [ ] Command must refuse to delete material facts.

- [ ] Add dry-run mode if current CLI conventions support it. Dry-run can print counts but must not be the only path; production needs an actual rebuild/drain action.

Target files:

- `src/gmgn_twitter_intel/app/surfaces/cli.py` or existing CLI module
- `src/gmgn_twitter_intel/domains/narrative_intel/services/`
- `tests/unit/test_cli_search_query.py` or a new CLI ops test
- `tests/integration/test_narrative_repository.py`

Run:

```bash
uv run pytest tests/unit/test_cli_search_query.py tests/integration/test_narrative_repository.py -q
```

---

## Step 8 — Health/API/Frontend Contract

- [ ] Extend narrative health:
  - current admissions;
  - current source events;
  - queued/retryable/stale/unavailable semantics;
  - pending waterline hits;
  - provider timeout/error counts;
  - label throughput;
  - digest status counts by window/scope;
  - top reasons: `semantic_labeling_pending`, `low_source_volume`, `low_independent_author_count`, `low_semantic_coverage`, `semantic_provider_unavailable`.

- [ ] Update API schemas to expose digest status/reasons/counts with no compatibility alias.

- [ ] Update frontend model text:
  - `insufficient + low_source_volume` -> "叙事样本不足";
  - `pending + semantic_labeling_pending` -> "叙事分析中";
  - `semantic_unavailable` -> "叙事分析暂不可用";
  - `stale` -> "叙事待刷新".

- [ ] Ensure `buildTokenRadarCompactCase` no longer collapses pending semantic work into "叙事不足".

Target files:

- `src/gmgn_twitter_intel/domains/narrative_intel/queries/narrative_backlog_health_query.py`
- `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- `src/gmgn_twitter_intel/app/surfaces/api/routes_status.py`
- `src/gmgn_twitter_intel/app/surfaces/api/routes_radar.py`
- `web/src/shared/model/tokenRadarCompactCase.ts`
- `web/tests/unit/shared/model/tokenRadarCompactCaseNarrative.test.ts`
- `docs/CONTRACTS.md`
- `docs/FRONTEND.md`

Run:

```bash
uv run pytest tests/unit/test_api_narrative_contract.py tests/integration/test_api_http.py -q
cd web && npm test -- --run web/tests/unit/shared/model/tokenRadarCompactCaseNarrative.test.ts
```

---

## Step 9 — Documentation And Generated Artefacts

- [ ] Add `src/gmgn_twitter_intel/domains/narrative_intel/ARCHITECTURE.md` if still missing.
- [ ] Update:
  - `docs/ARCHITECTURE.md`
  - `docs/WORKERS.md`
  - `docs/WORKER_FLOW.md`
  - `docs/CONTRACTS.md`
  - `docs/FRONTEND.md`
  - `docs/generated/cli-help.md` if CLI changes
  - `docs/generated/openapi.json` if API schema changes
  - `web/src/lib/types/openapi.ts` if generated types are checked in

- [ ] Document one-writer ownership explicitly:
  - `narrative_admissions`: `NarrativeAdmissionWorker`
  - `token_mention_semantics`: `MentionSemanticsWorker`
  - `token_discussion_digests`: `TokenDiscussionDigestWorker`

Run:

```bash
uv run pytest tests/integration/test_docs_generated.py tests/contract/test_openapi_drift.py -q
```

---

## Step 10 — Full Verification

Run backend:

```bash
uv run ruff check src/gmgn_twitter_intel/domains/narrative_intel tests/unit/domains/narrative_intel tests/integration/test_narrative_repository.py
uv run pytest tests/unit/domains/narrative_intel -q
uv run pytest tests/integration/test_narrative_repository.py -q
uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_src_domain_architecture.py -q
uv run pytest tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py -q
uv run pytest tests/unit/test_api_narrative_contract.py tests/integration/test_api_http.py -q
```

Run frontend if contract/model changed:

```bash
cd web && npm test -- --run web/tests/unit/shared/model/tokenRadarCompactCaseNarrative.test.ts
```

Run live-data verification:

```bash
uv run gmgn-twitter-intel config
```

Then, without printing secrets:

- apply migration;
- pause/acquire narrative workers;
- run narrative rebuild/drain command;
- resume `NarrativeAdmissionWorker`;
- resume `MentionSemanticsWorker`;
- resume `TokenDiscussionDigestWorker`;
- inspect `/api/status/narrative-health?since_hours=4`;
- inspect `/api/status`;
- sample `/api/token-radar?window=1h&scope=all`;
- sample `/api/token-radar?window=4h&scope=all`;
- sample `/api/token-radar?window=24h&scope=all`.

Expected after at least one full cycle:

- `mention_semantics` notes no longer show thousands of source mentions scanned before labeling a tiny batch;
- obsolete queued/retryable backlog is gone or bounded by current frontier waterline;
- top Radar rows with enough source set show `pending` while semantics catch up, then `ready`;
- `insufficient` only appears for true low source/author or final low semantic coverage;
- health endpoint separates source insufficiency from semantic backlog/provider failure.

---

## Completion Gate

- [ ] All required tests pass or skipped tests have documented environment reason.
- [ ] Live config paths were confirmed from `~/.gmgn-twitter-intel/`.
- [ ] Formal rebuild/drain was run or a dry-run report was attached for review before production execution.
- [ ] No runtime compatibility branch remains for old admission/digest behavior.
- [ ] No API request path writes narrative read models or calls provider.
- [ ] Docs and generated contracts match shipped behavior.
