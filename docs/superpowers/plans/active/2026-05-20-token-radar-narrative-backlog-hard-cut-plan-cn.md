# Token Radar Narrative Backlog Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the hidden narrative backlog that keeps Token Radar discussion analysis pending/stale by hard-cutting source-set semantics, digest completeness, health diagnostics, and rebuild/drain behavior into one consistent CQRS contract.

**Architecture:** Keep the existing three-writer model, but make `narrative_admissions.source_event_ids_json` the only source-set truth. `MentionSemanticsWorker` materializes missing semantics without source-age prune and claims due rows fairly across targets; `TokenDiscussionDigestWorker` judges completeness from full-source aggregate counts, writes admission `source_fingerprint` through every digest, and sends only a bounded prompt sample to the LLM. Public read models return either a fingerprint-matched current digest or a truthful non-persisted missing-state reason.

**Tech Stack:** Python 3.13, PostgreSQL, psycopg, Alembic, FastAPI, Pydantic v2, OpenAI Agents SDK through `AgentExecutionGateway`, pytest, ruff, React/Vite contract consumers.

---

**Status:** Draft
**Date:** 2026-05-20
**Owning spec:** `docs/superpowers/specs/active/2026-05-20-token-radar-narrative-backlog-hard-cut-cn.md`
**Worktree:** `.worktrees/token-radar-narrative-backlog-hard-cut/`
**Branch:** `codex/token-radar-narrative-backlog-hard-cut`

## Pre-flight

- [ ] Spec is approved.
- [ ] Create the implementation worktree:
  ```bash
  git worktree add .worktrees/token-radar-narrative-backlog-hard-cut -b codex/token-radar-narrative-backlog-hard-cut main
  cd .worktrees/token-radar-narrative-backlog-hard-cut
  git branch --show-current
  git status --short
  ```
  Expected branch: `codex/token-radar-narrative-backlog-hard-cut`.
- [ ] Confirm live config paths before any real-data command:
  ```bash
  uv run gmgn-twitter-intel config
  ```
  Expected: `config_path` and `workers_config_path` are under `~/.gmgn-twitter-intel/`. Do not print secrets.
- [ ] Capture baseline health without mutation:
  ```bash
  curl -fsS "http://127.0.0.1:8765/api/status/narrative-health?token=$GMGN_WS_TOKEN&since_hours=4" | python -m json.tool
  curl -fsS "http://127.0.0.1:8765/readyz" | python -m json.tool
  ```
- [ ] Run baseline tests:
  ```bash
  uv run ruff check .
  uv run pytest tests/unit/domains/narrative_intel -q
  uv run pytest tests/integration/test_narrative_repository.py -q
  uv run pytest tests/unit/test_api_narrative_contract.py -q
  uv run pytest tests/unit/test_worker_settings.py -q
  ```

Known-failing baseline tests: none expected. If Postgres integration tests cannot run locally, record the exact failure and run them before merge in the Docker-backed environment.

## File-Level Edits

### `src/gmgn_twitter_intel/platform/config/settings.py`

- Remove `MentionSemanticsWorkerSettings.max_pending_source_age_seconds`.
- Remove `max_pending_source_age_seconds: 43200` from `default_workers_yaml()`.
- Add hard-cut knobs:
  ```python
  max_semantic_rows_enqueued_per_cycle: int = Field(default=120, ge=1)
  max_semantic_rows_enqueued_per_admission: int = Field(default=20, ge=1)
  max_semantics_claimed_per_target_per_cycle: int = Field(default=3, ge=1)
  partial_enqueue_retry_seconds: int = Field(default=5, ge=1)
  ```
- Add digest caps:
  ```python
  max_llm_calls_per_cycle: int = Field(default=3, ge=0)
  max_llm_failures_per_cycle: int = Field(default=2, ge=0)
  provider_failure_backoff_seconds: int = Field(default=600, ge=1)
  ```

### `src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py`

- Delete `_prune_pending_backlog_sync` and every call to it.
- Keep run loop order as claim-first, then enqueue-if-needed:
  ```python
  rows = await asyncio.to_thread(self._claim_due_rows_sync, now_ms=resolved_now_ms, limit=batch_size)
  if rows:
      return await self._label_rows(rows, now_ms=resolved_now_ms, max_attempts=max_attempts)
  enqueue_stats = await asyncio.to_thread(self._enqueue_missing_from_admissions_sync, now_ms=resolved_now_ms)
  rows = await asyncio.to_thread(self._claim_due_rows_sync, now_ms=resolved_now_ms, limit=batch_size)
  if not rows:
      return WorkerResult(skipped=1, notes={"reason": "no_due_mentions", **_prefixed(enqueue_stats, "enqueue_")})
  return await self._label_rows(rows, now_ms=resolved_now_ms, max_attempts=max_attempts)
  ```
- In `_enqueue_missing_from_admissions_sync`, do not mark an admission fully scanned when `missing_after_enqueue > 0`.
- Add per-admission cap using `max_semantic_rows_enqueued_per_admission`.
- Use `partial_enqueue_retry_seconds` for partially materialized admissions.

### `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`

- Add full source-set aggregate query used by digest and health:
  ```python
  def semantic_coverage_for_admission(self, admission: dict[str, Any]) -> dict[str, int]:
      source_event_ids = _json_list(admission.get("source_event_ids_json"))
      if not source_event_ids:
          return {
              "source_event_count": 0,
              "semantic_row_count": 0,
              "missing_semantic_count": 0,
              "pending_semantic_count": 0,
              "retryable_semantic_count": 0,
              "labeled_event_count": 0,
              "terminal_unavailable_count": 0,
          }
      # SQL expands source_event_ids and left joins token_mention_semantics on
      # event_id + target_type + target_id + schema_version. Return counts over
      # the full source set, not the prompt-limited mention sample and not
      # events.received_at_ms >= now-window.
  ```
  It must expand `admission.source_event_ids_json` and left join
  `token_mention_semantics` with the current schema.
- Rewrite `digest_context` so aggregate counts are computed before `LIMIT max_mentions`.
  Remove `since_ms` from the completeness path; the digest worker must not re-window an
  admission source set by `now - window`.
- Add SQL-count metadata, not Python materialization:
  ```python
  def missing_semantic_count_for_admission(self, admission: dict[str, Any], *, schema_version: str) -> int:
      # SELECT COUNT(*) from expanded source ids where no semantics row exists.
  ```
- Change `current_digests_for_targets` to join admitted current admissions and matching `source_fingerprint`.
  It returns either:
  - a DB digest row when fingerprint matches an admitted admission;
  - a non-persisted sentinel row with `data_gaps_json=[{"reason": "digest_stale"}]` when an
    admitted admission exists but only stale/fingerprint-mismatched digest rows exist;
  - a sentinel row with `not_in_current_frontier` when only suppressed admission exists;
  - a sentinel row with `digest_not_ready` when no usable admission/digest exists.
- Add cleanup method:
  ```python
  def cleanup_narrative_current_hard_cut(self, *, schema_version: str, now_ms: int) -> dict[str, int]:
      # Deletes queued/retryable/stale semantics outside current admitted source
      # sets and marks current digests stale when their admission is suppressed
      # or their source_fingerprint no longer matches. Returns exact rowcounts:
      # deleted_obsolete_pending_semantics, stale_suppressed_digests,
      # stale_fingerprint_mismatch_digests.
  ```
  It marks stale/fingerprint-mismatched current digests through the ops-maintenance path, and deletes queued/retryable/stale semantics outside current admitted source sets. This path is allowed only while `ops rebuild-narrative-intel` holds the narrative worker advisory locks; it is not a runtime writer and is not callable from HTTP routes.

### `src/gmgn_twitter_intel/domains/narrative_intel/services/discussion_digest_service.py`

- Replace prompt-sample-derived unseen logic with explicit aggregate fields:
  ```python
  missing = int(context.get("missing_semantic_count") or 0)
  pending = int(context.get("pending_semantic_count") or 0)
  retryable = int(context.get("retryable_semantic_count") or 0)
  unavailable = int(context.get("terminal_unavailable_count") or 0)
  semantic_rows = int(context.get("semantic_row_count") or 0)
  ```
- `semantic_labeling_pending` only when `missing + pending + retryable > 0`.
- `semantic_provider_unavailable` only when `source_count > 0`, `semantic_rows == source_count`, and every row is terminal unavailable or labeled coverage is below threshold with no pending/missing.
- Keep `build_digest_request` capped to `max_mentions_per_digest`; add context fields `prompt_mention_count` and `prompt_mention_limit`.
- `build_status_digest` and `publish_ready_digest` must copy `context["source_fingerprint"]`
  into the returned `TokenDiscussionDigest`. New status/ready digest rows must pass the public
  fingerprint join immediately.

### `src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py`

- Add counters:
  ```python
  llm_calls = 0
  llm_failures = 0
  deferred = 0
  ```
- Before provider call:
  ```python
  if llm_calls >= self._max_llm_calls_per_cycle():
      await self._mark_digest_scanned_sync(
          target=target,
          now_ms=resolved_now_ms,
          next_due_at_ms=self._backpressure_next_due_at_ms(now_ms=resolved_now_ms),
      )
      counts["pending"] += 1
      deferred += 1
      refresh_reasons["llm_cycle_budget_exhausted"] = refresh_reasons.get("llm_cycle_budget_exhausted", 0) + 1
      continue
  ```
- On provider exception, use `provider_failure_backoff_seconds`; stop LLM attempts once `max_llm_failures_per_cycle` is hit.
- Include `llm_calls`, `llm_failures`, and `deferred_llm_budget` in worker notes.
- Change `_digest_context_sync` to stop computing `since_ms`; call repository `digest_context`
  with target identity/window/scope and `max_mentions` only. `_window_ms` can be deleted unless
  another path still uses it.

### `src/gmgn_twitter_intel/domains/narrative_intel/queries/narrative_backlog_health_query.py`

- Add missing source-set metrics:
  - `current_source_rows`
  - `semantic_rows_for_current_sources`
  - `missing_semantic_rows`
  - `admissions_with_missing_semantics`
  - `pending_existing_rows`
  - `suppressed_current_digest_count`
  - `stale_fingerprint_current_digest_count`
- Redefine `semantic_backlog.total_pending` as `missing_semantic_rows + queued + retryable + stale`.
- Define SQL count semantics explicitly:
  - expand admitted `source_event_ids_json` into `current_sources(admission_id,target_type,target_id,window,scope,event_id)`;
  - count per admission-source row, so the same event can count once per current window/scope admission;
  - count a source row as having semantics with `EXISTS` over `(event_id,target_type,target_id,schema_version)`;
  - do not count duplicate text fingerprints multiple times for one admission-source row.

### `src/gmgn_twitter_intel/app/runtime/worker_factories/narrative_intel.py`

- Wire `wake_waiter=ctx.db.wake_listener(worker_name, workers.<worker>.wakes_on)` for
  `mention_semantics` and `token_discussion_digest`, matching token/news/pulse worker factory
  patterns.

### `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`

- Extend `rebuild-narrative-intel` with hard-cut cleanup output.
- Add `--dry-run` if the existing parser can support it without delaying the fix; otherwise expose cleanup counts in normal command output.
- The command must run:
  1. admission rebuild;
  2. current hard-cut cleanup;
  3. semantics drain cycles;
  4. digest drain cycles;
  5. final health summary.
- Before starting the rebuilt image, the operator-owned
  `~/.gmgn-twitter-intel/workers.yaml` must be edited to remove `max_pending_source_age_seconds`.
  This is a hard-cut deployment gate, not a runtime compatibility alias.

### Tests

- `tests/unit/domains/narrative_intel/test_discussion_digest_service.py`
- `tests/unit/domains/narrative_intel/test_narrative_workers.py`
- `tests/unit/domains/narrative_intel/test_narrative_backlog_health.py`
- `tests/unit/domains/narrative_intel/test_narrative_read_model.py`
- `tests/integration/test_narrative_repository.py`
- `tests/unit/test_worker_settings.py`
- `tests/unit/test_api_narrative_contract.py`
- `tests/unit/test_bootstrap_worker_runtime_wiring.py`
- `tests/architecture/test_worker_runtime_contracts.py`
- `web/tests/unit/shared/model/narrativeDataGaps.test.ts`

### Docs

- Update `docs/WORKERS.md`.
- Create `src/gmgn_twitter_intel/domains/narrative_intel/ARCHITECTURE.md` because global `docs/ARCHITECTURE.md` links it but the file is currently missing.
- Update `docs/CONTRACTS.md` for narrative health fields and public digest currentness.

## Task 1 — Tests For Config Hard Cut

- [ ] Add failing test in `tests/unit/test_worker_settings.py`:
  ```python
  def test_mention_semantics_hard_cuts_source_age_prune_setting() -> None:
      text = default_workers_yaml()
      assert "max_pending_source_age_seconds" not in text
      settings = WorkersSettings(**yaml.safe_load(text))
      assert not hasattr(settings.mention_semantics, "max_pending_source_age_seconds")
      assert settings.mention_semantics.max_semantic_rows_enqueued_per_cycle == 120
      assert settings.mention_semantics.max_semantic_rows_enqueued_per_admission == 20
      assert settings.mention_semantics.max_semantics_claimed_per_target_per_cycle == 3
      assert settings.mention_semantics.partial_enqueue_retry_seconds == 5
  ```
- [ ] Add digest cap assertions:
  ```python
  def test_token_discussion_digest_has_llm_cycle_caps() -> None:
      settings = WorkersSettings(**yaml.safe_load(default_workers_yaml()))
      assert settings.token_discussion_digest.max_llm_calls_per_cycle == 3
      assert settings.token_discussion_digest.max_llm_failures_per_cycle == 2
      assert settings.token_discussion_digest.provider_failure_backoff_seconds == 600
  ```
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_worker_settings.py -q
  ```
  Expected before implementation: FAIL on missing settings/defaults.

## Task 2 — Implement Config Hard Cut

- [ ] Modify `settings.py` exactly as described in File-Level Edits.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_worker_settings.py -q
  ```
  Expected: PASS.
- [ ] Commit:
  ```bash
  git add src/gmgn_twitter_intel/platform/config/settings.py tests/unit/test_worker_settings.py
  git commit -m "fix: hard cut narrative backlog worker settings"
  ```

## Task 3 — Tests For Digest Completeness From Full Source Set

- [ ] Add unit tests in `test_discussion_digest_service.py`:
  ```python
  def test_refresh_decision_pending_uses_explicit_missing_count_not_prompt_sample_size() -> None:
      service = DiscussionDigestService(min_source_mentions=3, min_independent_authors=2, min_semantic_coverage=0.35)
      decision = service.refresh_decision({
          "source_event_count": 82,
          "independent_author_count": 12,
          "semantic_row_count": 82,
          "missing_semantic_count": 0,
          "pending_semantic_count": 0,
          "retryable_semantic_count": 0,
          "terminal_unavailable_count": 25,
          "labeled_event_count": 57,
          "mentions": [{"status": "labeled"} for _ in range(24)],
          "semantic_rows": [{"status": "labeled"} for _ in range(24)],
      })
      assert decision.should_refresh is True
      assert decision.reason == "thresholds_met"
  ```
- [ ] Add missing semantics test:
  ```python
  def test_refresh_decision_reports_semantic_pending_when_source_rows_are_missing_semantics() -> None:
      service = DiscussionDigestService(min_source_mentions=3, min_independent_authors=2, min_semantic_coverage=0.35)
      decision = service.refresh_decision({
          "source_event_count": 10,
          "independent_author_count": 4,
          "semantic_row_count": 4,
          "missing_semantic_count": 6,
          "pending_semantic_count": 0,
          "retryable_semantic_count": 0,
          "terminal_unavailable_count": 0,
          "labeled_event_count": 4,
          "mentions": [{"status": "labeled"} for _ in range(4)],
          "semantic_rows": [{"status": "labeled"} for _ in range(4)],
      })
      assert decision.should_refresh is False
      assert decision.reason == "semantic_labeling_pending"
      assert decision.status_if_not_refresh == "pending"
  ```
- [ ] Add source fingerprint write-through tests:
  ```python
  def test_status_digest_carries_source_fingerprint_from_context() -> None:
      service = DiscussionDigestService()
      digest = service.build_status_digest(
          target_type="chain_token",
          target_id="solana:So111",
          window="24h",
          scope="all",
          context={
              "source_event_count": 3,
              "labeled_event_count": 0,
              "independent_author_count": 2,
              "source_fingerprint": "source-current",
          },
          reason="semantic_labeling_pending",
          now_ms=1000,
          status="pending",
      )
      assert digest.source_fingerprint == "source-current"

  def test_ready_digest_carries_source_fingerprint_from_context() -> None:
      service = DiscussionDigestService()
      digest = service.publish_ready_digest(
          {
              "target_type": "chain_token",
              "target_id": "solana:So111",
              "window": "24h",
              "scope": "all",
              "schema_version": "narrative_intel_v1",
              "model_version": "gpt-test",
              "status": "ready",
              "dominant_narratives": [
                  {"cluster_key": "main", "summary_zh": "主线", "evidence_refs": [{"ref_id": "event:e1"}]}
              ],
              "bull_view": {"summary_zh": "多头", "evidence_refs": [{"ref_id": "event:e1"}]},
              "bear_view": {"summary_zh": "空头", "evidence_refs": [{"ref_id": "event:e2"}]},
              "evidence_refs": [{"ref_id": "event:e1"}],
          },
          context={
              "source_event_count": 3,
              "labeled_event_count": 3,
              "independent_author_count": 2,
              "source_fingerprint": "source-current",
              "mentions": [{"event_id": "e1"}, {"event_id": "e2"}, {"event_id": "e3"}],
              "semantic_rows": [{"status": "labeled"}, {"status": "labeled"}, {"status": "labeled"}],
          },
          now_ms=1000,
      )
      assert digest.source_fingerprint == "source-current"
  ```
- [ ] Run:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_discussion_digest_service.py -q
  ```
  Expected before implementation: FAIL where prompt sample length forces pending.

## Task 4 — Implement Digest Decision Aggregate Fields

- [ ] Update `DiscussionDigestService.refresh_decision` to use explicit aggregate fields.
- [ ] Update `build_status_digest` and `publish_ready_digest` to set:
  ```python
  "source_fingerprint": context.get("source_fingerprint")
  ```
  when the context value is present.
- [ ] Update `_compact_context` to include:
  ```python
  "semantic_row_count": int(context.get("semantic_row_count") or 0),
  "missing_semantic_count": int(context.get("missing_semantic_count") or 0),
  "pending_semantic_count": int(context.get("pending_semantic_count") or 0),
  "retryable_semantic_count": int(context.get("retryable_semantic_count") or 0),
  "terminal_unavailable_count": int(context.get("terminal_unavailable_count") or 0),
  "prompt_mention_count": int(mention_count_sent),
  "prompt_mention_limit": int(mention_limit),
  ```
- [ ] Run:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_discussion_digest_service.py -q
  ```
  Expected: PASS.
- [ ] Commit:
  ```bash
  git add src/gmgn_twitter_intel/domains/narrative_intel/services/discussion_digest_service.py tests/unit/domains/narrative_intel/test_discussion_digest_service.py
  git commit -m "fix: judge narrative digest coverage from full source set"
  ```

## Task 5 — Repository Tests For Full Source Aggregates And Public Currentness

- [ ] Add integration test `test_digest_context_counts_missing_semantics_outside_prompt_limit`:
  - seed one admitted target with 30 source event ids;
  - seed semantics rows for 24 of them;
  - request `digest_context(..., max_mentions=10)`;
  - assert `source_event_count == 30`;
  - assert `semantic_row_count == 24`;
  - assert `missing_semantic_count == 6`;
  - assert `len(context["mentions"]) == 10`.
- [ ] Add integration test `test_digest_context_full_source_counts_ignore_digest_now_window_filter`:
  - seed an admitted `24h` target whose `source_event_ids_json` includes one event older than
    `now_ms - 24h` but still in the current admission source set;
  - seed a semantics row for every source id;
  - call `digest_context(..., max_mentions=10)` after the digest worker would previously have
    computed `since_ms`;
  - assert the older source id is included in `source_event_count` and `semantic_row_count`.
- [ ] Add integration test `test_current_digests_returns_matching_fingerprint_digest`:
  - seed admitted source fingerprint `current`;
  - seed current ready digest with source fingerprint `current`;
  - call `current_digests_for_targets`;
  - assert the ready digest is returned.
- [ ] Add integration test `test_current_digests_excludes_suppressed_admission_digest`:
  - seed current digest for target;
  - seed matching admission as `suppressed`;
  - call `current_digests_for_targets`;
  - assert result contains a non-persisted pending sentinel with data gap reason
    `not_in_current_frontier`.
- [ ] Add integration test `test_current_digests_excludes_fingerprint_mismatch`:
  - seed admitted source fingerprint `new`;
  - seed current digest source fingerprint `old`;
  - assert result contains a non-persisted pending sentinel with data gap reason `digest_stale`.
- [ ] Run:
  ```bash
  uv run pytest tests/integration/test_narrative_repository.py -q
  ```
  Expected before implementation: FAIL.

## Task 6 — Implement Repository Aggregates And Current Digest Filter

- [ ] Rewrite `digest_context` using a CTE that never filters completeness by `since_ms`:
  ```sql
  WITH source_ids AS (
    SELECT jsonb_array_elements_text(%(source_event_ids_json)s::jsonb) AS event_id
  ),
  joined AS (
    SELECT
      events.event_id,
      events.text_clean,
      events.author_handle,
      events.tweet_id,
      events.raw_json AS reference_json,
      events.received_at_ms AS source_received_at_ms,
      semantics.semantic_id,
      semantics.status,
      semantics.trade_stance,
      semantics.attention_valence,
      semantics.narrative_cluster_key,
      semantics.claim_type,
      semantics.evidence_type,
      semantics.semantic_confidence,
      semantics.co_mentioned_targets_json,
      semantics.evidence_refs_json,
      semantics.raw_label_json,
      semantics.model_run_id,
      semantics.computed_at_ms,
      semantics.retry_count,
      semantics.next_retry_at_ms,
      semantics.error
    FROM source_ids
    JOIN events ON events.event_id = source_ids.event_id
    LEFT JOIN token_mention_semantics AS semantics
      ON semantics.event_id = events.event_id
     AND semantics.target_type = %(target_type)s
     AND semantics.target_id = %(target_id)s
     AND semantics.schema_version = %(schema_version)s
  )
  SELECT * FROM joined
  ORDER BY source_received_at_ms DESC, event_id DESC
  LIMIT %(max_mentions)s
  ```
- [ ] Add a second aggregate query over the same `joined` CTE without `LIMIT`.
- [ ] Return aggregate count keys used by Task 4, plus `source_fingerprint` from the admission row.
- [ ] Remove `since_ms` from the repository `digest_context` signature and from
  `TokenDiscussionDigestWorker._digest_context_sync`.
- [ ] Change `current_digests_for_targets` SQL to join admitted admissions:
  ```sql
  JOIN narrative_admissions AS admissions
    ON admissions.target_type = digest.target_type
   AND admissions.target_id = digest.target_id
   AND admissions."window" = digest."window"
   AND admissions.scope = digest.scope
   AND admissions.schema_version = digest.schema_version
   AND admissions.status = 'admitted'
   AND COALESCE(admissions.source_fingerprint, '') = COALESCE(digest.source_fingerprint, '')
  ```
- [ ] Add sentinel helper in `narrative_repository.py`:
  ```python
  def _missing_digest_row(
      *,
      target_type: str,
      target_id: str,
      window: str,
      scope: str,
      schema_version: str,
      reason: str,
  ) -> dict[str, Any]:
      return {
          "target_type": target_type,
          "target_id": target_id,
          "window": window,
          "scope": scope,
          "schema_version": schema_version,
          "status": "pending",
          "is_current": False,
          "data_gaps_json": [{"reason": reason}],
          "semantic_coverage": 0.0,
          "source_event_count": 0,
          "labeled_event_count": 0,
          "independent_author_count": 0,
          "evidence_refs_json": [],
      }
  ```
  Do not persist sentinel rows.
- [ ] Run:
  ```bash
  uv run pytest tests/integration/test_narrative_repository.py -q
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_read_model.py -q
  ```
  Expected: PASS.
- [ ] Commit:
  ```bash
  git add src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py tests/integration/test_narrative_repository.py tests/unit/domains/narrative_intel/test_narrative_read_model.py
  git commit -m "fix: filter narrative digests by current source sets"
  ```

## Task 7 — Tests For Mention Semantics Enqueue Visibility

- [ ] Add worker test `test_semantics_enqueue_budget_keeps_partially_missing_admission_due`:
  - fake repository returns one admission with 30 missing source rows;
  - settings budget is 10 and per-admission cap is 10;
  - after `_enqueue_missing_from_admissions_sync`, assert:
    - inserted count is 10;
    - `semantic_suppressed_budget` is 20;
    - `mark_admissions_semantics_scanned` receives `next_due_at_ms <= now_ms + 5_000`.
- [ ] Add source-code architecture test:
  ```python
  def test_mention_semantics_worker_no_source_age_prune_runtime_path() -> None:
      source = inspect.getsource(MentionSemanticsWorker)
      assert "max_pending_source_age_seconds" not in source
      assert "_prune_pending_backlog_sync" not in source
      assert "prune_pending_mention_semantics_backlog" not in source
  ```
- [ ] Add worker/repository test `test_due_mentions_for_labeling_limits_rows_per_target`:
  - seed queued semantics for one hot target and one cold target;
  - call `due_mentions_for_labeling(now_ms=..., limit=6, max_per_target=3)`;
  - assert no target contributes more than three rows and both targets can be claimed.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py -q
  ```
  Expected before implementation: FAIL.

## Task 8 — Implement MentionSemanticsWorker Hard Cut

- [ ] Delete source-age prune code and notes.
- [ ] Pass `max_semantics_claimed_per_target_per_cycle` from
  `MentionSemanticsWorker._claim_due_rows_sync` into repository `due_mentions_for_labeling`.
- [ ] Change `NarrativeRepository.due_mentions_for_labeling` signature:
  ```python
  def due_mentions_for_labeling(
      self,
      *,
      now_ms: int,
      limit: int,
      max_per_target: int | None = None,
  ) -> list[dict[str, Any]]:
  ```
  Use a `row_number() OVER (PARTITION BY target_type, target_id ORDER BY source_received_at_ms DESC, semantic_id ASC)` CTE when `max_per_target` is set, so one hot target cannot monopolize the claim batch.
- [ ] Add helper:
  ```python
  def _next_semantics_due_for_enqueue(
      *,
      now_ms: int,
      missing_after_enqueue: int,
      interval_ms: int,
      partial_retry_ms: int,
  ) -> int:
      return int(now_ms) + (partial_retry_ms if missing_after_enqueue > 0 else interval_ms)
  ```
- [ ] In `_enqueue_missing_from_admissions_sync`, compute `missing_after_enqueue` per admission and mark due accordingly.
- [ ] Preserve single writer: this worker may update only due timestamp fields on `narrative_admissions`, not admission source metadata or status.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py -q
  uv run pytest tests/unit/domains/narrative_intel/test_discussion_digest_service.py -q
  ```
  Expected: PASS.
- [ ] Commit:
  ```bash
  git add src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py tests/unit/domains/narrative_intel/test_narrative_workers.py
  git commit -m "fix: keep missing narrative semantics visible"
  ```

## Task 9 — Tests For Digest Worker LLM Caps

- [ ] Add worker test with 5 threshold-met targets and fake provider:
  - settings `max_llm_calls_per_cycle=2`;
  - assert provider called exactly 2 times;
  - assert remaining targets marked pending/deferred, not failed;
  - assert worker notes include `llm_calls=2` and `deferred_llm_budget=3`.
- [ ] Add provider failure cap test:
  - settings `max_llm_failures_per_cycle=1`;
  - fake provider raises for first call;
  - assert later threshold-met targets are deferred, not attempted.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py -q
  ```
  Expected before implementation: FAIL.

## Task 10 — Implement Digest Worker LLM Caps And Backoff

- [ ] Add private settings helpers:
  ```python
  def _max_llm_calls_per_cycle(self) -> int:
      return max(0, int(getattr(self.settings, "max_llm_calls_per_cycle", 3) or 0))

  def _max_llm_failures_per_cycle(self) -> int:
      return max(0, int(getattr(self.settings, "max_llm_failures_per_cycle", 2) or 0))

  def _provider_failure_backoff_ms(self) -> int:
      seconds = max(1, int(getattr(self.settings, "provider_failure_backoff_seconds", 600) or 600))
      return seconds * 1000
  ```
- [ ] Gate provider calls as shown in File-Level Edits.
- [ ] On provider failure, mark that target next due at `finished_at_ms + _provider_failure_backoff_ms()`.
- [ ] Stop attempting LLM calls after failure cap; remaining threshold-met targets get `llm_failure_budget_exhausted`.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py -q
  ```
  Expected: PASS.
- [ ] Commit:
  ```bash
  git add src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py tests/unit/domains/narrative_intel/test_narrative_workers.py
  git commit -m "fix: bound narrative digest llm amplification"
  ```

## Task 11 — Health Query Tests And Implementation

- [ ] Add unit or integration test for `NarrativeBacklogHealthQuery`:
  - admitted source ids count 5;
  - semantics rows count 2;
  - existing queued rows count 1;
  - assert `missing_semantic_rows == 3`;
  - assert `semantic_backlog.total_pending == missing + queued + retryable + stale`.
- [ ] Add duplicate semantic row test:
  - one admitted source id has two semantic rows with different `text_fingerprint`;
  - assert `semantic_rows_for_current_sources == 1`, not 2, for that admission-source row.
- [ ] Add contract assertion that counts are admission-source rows:
  - the same event included in two current windows counts once per admission/window;
  - document this explicitly in `docs/CONTRACTS.md`.
- [ ] Add suppressed current digest count test.
- [ ] Implement health fields in `narrative_backlog_health_query.py`.
- [ ] Update API schema in `src/gmgn_twitter_intel/app/surfaces/api/schemas.py` if typed fields are explicit.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_backlog_health.py tests/unit/test_api_narrative_contract.py -q
  ```
  Expected: PASS.
- [ ] Commit:
  ```bash
  git add src/gmgn_twitter_intel/domains/narrative_intel/queries/narrative_backlog_health_query.py src/gmgn_twitter_intel/app/surfaces/api/schemas.py tests/unit/domains/narrative_intel/test_narrative_backlog_health.py tests/unit/test_api_narrative_contract.py
  git commit -m "fix: expose real narrative semantic backlog"
  ```

## Task 12 — Ops Rebuild/Drain Hard-Cut Cleanup

- [ ] Add tests for ops cleanup using repository-level methods:
  - delete queued/retryable/stale semantics outside admitted source sets;
  - keep labeled/semantic_unavailable historical rows;
  - mark current digests stale when admission suppressed or fingerprint mismatched.
- [ ] Add CLI contract test that `rebuild-narrative-intel` acquires all three narrative worker
  advisory locks before cleanup. The cleanup method is a maintenance writer exception only inside
  that locked command.
- [ ] Implement `cleanup_narrative_current_hard_cut`.
- [ ] Extend `rebuild-narrative-intel` output with:
  ```json
  {
    "cleanup": {
      "deleted_obsolete_pending_semantics": 0,
      "stale_suppressed_digests": 0,
      "stale_fingerprint_mismatch_digests": 0
    },
    "final_health": {
      "missing_semantic_rows": 0,
      "pending_digest_count": 0
    }
  }
  ```
- [ ] Run:
  ```bash
  uv run pytest tests/integration/test_narrative_repository.py tests/unit/test_cli_ops_contract.py -q
  ```
  Expected: PASS.
- [ ] Commit:
  ```bash
  git add src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py tests/integration/test_narrative_repository.py tests/unit/test_cli_ops_contract.py
  git commit -m "fix: add narrative hard-cut rebuild cleanup"
  ```

## Task 13 — Narrative Wake Wiring

- [ ] Add failing wiring test in `tests/unit/test_bootstrap_worker_runtime_wiring.py`:
  ```python
  def test_narrative_workers_use_configured_wake_waiters() -> None:
      db = FakeDB()
      providers = FakeProviders()
      providers.narrative_intel = SimpleNamespace(narrative_provider=object())
      settings = _settings()
      settings.llm.api_key = "secret"
      settings.llm.model = "gpt-test"
      settings.workers.mention_semantics.enabled = True
      settings.workers.token_discussion_digest.enabled = True

      workers = construct_workers(
          settings=settings,
          db=db,
          telemetry=object(),
          providers=providers,
          hub=SimpleNamespace(publish=lambda payload: None),
          collector=FakeCollector(name="collector", settings=SimpleNamespace(enabled=False), db=db, telemetry=object()),
          collector_enabled=False,
          wake_bus=db.wake,
      )

      assert workers["mention_semantics"].wake_waiter.channels == (
          "token_radar_updated",
          "resolution_updated",
      )
      assert workers["token_discussion_digest"].wake_waiter.channels == (
          "token_radar_updated",
          "narrative_semantics_updated",
          "market_tick_written",
      )
  ```
  Use the existing `FakeDB.wake_listener` helper in that test file; do not create a new runtime harness.
- [ ] Update `src/gmgn_twitter_intel/app/runtime/worker_factories/narrative_intel.py`:
  ```python
  worker_name = "mention_semantics"
  constructed[worker_name] = MentionSemanticsWorker(
      name=worker_name,
      settings=workers.mention_semantics,
      db=ctx.db,
      telemetry=ctx.telemetry,
      provider=provider,
      wake_bus=ctx.wake_bus,
      wake_waiter=ctx.db.wake_listener(worker_name, workers.mention_semantics.wakes_on),
  )
  ```
  Repeat the same pattern for `token_discussion_digest`.
- [ ] Update `MentionSemanticsWorker.__init__` and `TokenDiscussionDigestWorker.__init__` to accept
  `wake_waiter: Any | None = None` and pass it to `WorkerBase`.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/domains/narrative_intel/test_narrative_workers.py -q
  ```
  Expected: PASS.
- [ ] Commit:
  ```bash
  git add src/gmgn_twitter_intel/app/runtime/worker_factories/narrative_intel.py src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py tests/unit/test_bootstrap_worker_runtime_wiring.py
  git commit -m "fix: wire narrative workers to wake hints"
  ```

## Task 14 — Architecture Docs And Contract Docs

- [ ] Create `src/gmgn_twitter_intel/domains/narrative_intel/ARCHITECTURE.md` with:
  - source-set truth;
  - writer ownership table;
  - digest status contract;
  - no runtime compatibility;
  - update triggers.
- [ ] Update `docs/WORKERS.md` narrative worker inventory.
- [ ] Update `docs/CONTRACTS.md` for `/api/status/narrative-health` fields and digest currentness.
- [ ] Update frontend reason labels in `web/src/shared/model/narrativeDataGaps.ts`:
  ```ts
  digest_stale: "叙事待刷新",
  not_in_current_frontier: "不在当前雷达前沿",
  llm_cycle_budget_exhausted: "叙事排队中",
  llm_failure_budget_exhausted: "叙事排队中",
  ```
- [ ] Add architecture test if one does not exist:
  ```python
  def test_narrative_architecture_doc_exists() -> None:
      assert Path("src/gmgn_twitter_intel/domains/narrative_intel/ARCHITECTURE.md").exists()
  ```
- [ ] Run:
  ```bash
  uv run pytest tests/architecture -q
  npm --prefix web test -- --run web/tests/unit/shared/model/narrativeDataGaps.test.ts
  ```
  Expected: PASS.
- [ ] Commit:
  ```bash
  git add src/gmgn_twitter_intel/domains/narrative_intel/ARCHITECTURE.md docs/WORKERS.md docs/CONTRACTS.md web/src/shared/model/narrativeDataGaps.ts tests/architecture
  git commit -m "docs: document narrative source-set contract"
  ```

## Task 15 — Full Verification

- [ ] Run focused regression:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel tests/integration/test_narrative_repository.py tests/unit/test_api_narrative_contract.py tests/unit/test_worker_settings.py tests/unit/test_cli_ops_contract.py tests/architecture -q
  ```
- [ ] Run broader worker/API regression:
  ```bash
  uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_cli_worker_status_contract.py tests/unit/test_ops_diagnostics.py -q
  ```
- [ ] Run lint:
  ```bash
  uv run ruff check .
  ```
- [ ] If time permits before merge, run project gate:
  ```bash
  make check-all
  ```
- [ ] Rebuild Docker:
  ```bash
  uv run gmgn-twitter-intel config
  docker compose build app
  docker compose up -d app
  docker compose ps app
  curl -fsS http://127.0.0.1:8765/readyz | python -m json.tool
  ```
  Expected before build/start: `workers_config_path` points under `~/.gmgn-twitter-intel/`
  and live `workers.yaml` has no `max_pending_source_age_seconds`.
- [ ] Live drain command after deploy:
  ```bash
  uv run gmgn-twitter-intel ops rebuild-narrative-intel --window 1h --scope all --drain --cycles 10
  uv run gmgn-twitter-intel ops rebuild-narrative-intel --window 4h --scope all --drain --cycles 10
  uv run gmgn-twitter-intel ops rebuild-narrative-intel --window 24h --scope all --drain --cycles 10
  ```
- [ ] Verify live health:
  ```bash
  curl -fsS "http://127.0.0.1:8765/api/status/narrative-health?token=$GMGN_WS_TOKEN&since_hours=4" | python -m json.tool
  ```
  Expected: `semantic_backlog.missing_semantic_rows` is visible and trending down after drain; `suppressed_current_digest_count` is 0 or explained; stale `semantic_labeling_pending` with zero actual pending semantics is gone.

## PR Breakdown

1. **PR 1 — Config and digest decision hard cut**: Tasks 1-4. Mergeable once unit tests pass.
2. **PR 2 — Repository aggregate/currentness hard cut**: Tasks 5-6. Depends on PR 1.
3. **PR 3 — Worker state-machine hard cut**: Tasks 7-10. Depends on PR 2.
4. **PR 4 — Health, ops, wake wiring, docs, live drain**: Tasks 11-15. Depends on PR 3.

For this repo/session, these can land as one branch if the user wants a single hard-cut deployment. Do not merge only PR 1 or PR 2 to production without PR 3/4, because API state would become more honest but backlog would not drain.

## Rollout Order

1. Merge code and docs to `main`.
2. Edit operator-owned `~/.gmgn-twitter-intel/workers.yaml` to remove `max_pending_source_age_seconds`.
3. Run `uv run gmgn-twitter-intel config`; treat any config validation failure as a deployment blocker.
4. Build and start Docker image.
5. Confirm `/readyz` is OK.
6. Run narrative rebuild/drain command for hot windows first: `5m`, `1h`, then `4h`, then `24h`.
7. Watch `/api/status/narrative-health` for missing/pending trend.
8. Verify `/api/token-radar` top rows show ready or honest not-ready reasons.
9. Keep old active spec/plan drafts untouched unless a separate cleanup PR moves superseded docs to completed/archived.

## Rollback

This is a hard cut, not a dual runtime.

- Code rollback: revert the merge commit and rebuild Docker.
- Data rollback: no destructive migration is required by the plan. Stale digest markers and deleted queued/retryable obsolete semantics are operational cleanup effects; labeled and terminal historical semantics remain.
- Config rollback: restore previous `workers.yaml` from operator backup only if code is reverted too. Do not run new code with old `max_pending_source_age_seconds`.
- If live drain causes high LLM load, reduce `token_discussion_digest.max_llm_calls_per_cycle` and rerun; do not re-enable old source-age prune.

## Acceptance Test Commands

- AC1:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_backlog_health.py::test_health_reports_missing_semantics_not_only_existing_queue_rows -q
  ```
- AC2 and AC8:
  ```bash
  uv run pytest tests/unit/test_worker_settings.py::test_mention_semantics_hard_cuts_source_age_prune_setting tests/unit/domains/narrative_intel/test_narrative_workers.py::test_mention_semantics_worker_no_source_age_prune_runtime_path -q
  ```
- AC3:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py::test_semantics_enqueue_budget_keeps_partially_missing_admission_due -q
  ```
- AC4:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_discussion_digest_service.py::test_refresh_decision_pending_uses_explicit_missing_count_not_prompt_sample_size -q
  ```
- AC5:
  ```bash
  uv run pytest tests/integration/test_narrative_repository.py::test_current_digests_excludes_suppressed_admission_digest tests/integration/test_narrative_repository.py::test_current_digests_excludes_fingerprint_mismatch -q
  ```
- AC6:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py::test_digest_worker_caps_llm_calls_per_cycle -q
  ```
- AC7:
  ```bash
  uv run gmgn-twitter-intel ops rebuild-narrative-intel --window 1h --scope all --drain --cycles 10
  curl -fsS "http://127.0.0.1:8765/api/status/narrative-health?token=$GMGN_WS_TOKEN&since_hours=4" | python -m json.tool
  ```
- AC9:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_discussion_digest_service.py::test_status_digest_carries_source_fingerprint_from_context tests/unit/domains/narrative_intel/test_discussion_digest_service.py::test_ready_digest_carries_source_fingerprint_from_context tests/integration/test_narrative_repository.py::test_current_digests_returns_matching_fingerprint_digest -q
  ```
- AC10:
  ```bash
  uv run pytest tests/integration/test_narrative_repository.py::test_digest_context_full_source_counts_ignore_digest_now_window_filter -q
  ```
- AC11:
  ```bash
  uv run pytest tests/integration/test_narrative_repository.py::test_current_digests_excludes_suppressed_admission_digest tests/integration/test_narrative_repository.py::test_current_digests_excludes_fingerprint_mismatch -q
  ```
- AC12:
  ```bash
  uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py::test_narrative_workers_use_configured_wake_waiters -q
  ```

## Impact Assessment

**Product impact:** Token Radar narrative panels will become more honest immediately. Some rows that previously showed stale/pending digest may temporarily show `digest_not_ready` until drain catches up. This is preferable to displaying wrong current narratives.

**Operational impact:** The first drain after deployment will surface a large missing-semantics backlog. This is expected. Digest LLM calls are capped, so ready digest recovery may take multiple cycles rather than one huge timeout-prone burst.

**Cost/performance impact:** Removing source-age prune can increase semantic queue size for 24h windows, but current source-set membership, per-cycle budget, per-admission cap, and digest LLM caps bound the load. Health now makes the backlog visible.

**Database impact:** No new table is required. Additional aggregate queries expand `source_event_ids_json`; integration tests and live verification must capture query latency under statement timeout. Existing unique indexes already cover the main semantic equality lookup prefix; add a migration only after `EXPLAIN` proves a missing access path.

**API/frontend impact:** `/api/status/narrative-health` changes `total_pending` semantics and adds fields. Public digest currentness becomes stricter and exposes `digest_stale` / `not_in_current_frontier` reasons; frontend labels must be updated in the same hard cut.

**Compatibility impact:** Intentional breaking hard cut. Runtime will not read `max_pending_source_age_seconds`, will not fallback to suppressed digests, and will not keep old hidden-backlog health semantics.

## Verification

Create `docs/superpowers/plans/active/2026-05-20-token-radar-narrative-backlog-hard-cut-verification-cn.md` during implementation. It must include:

- exact test command outputs;
- Docker build/restart output summary;
- before/after narrative-health snapshots with secrets redacted;
- live drain command output summary;
- remaining risks and any follow-up appended to `docs/TECH_DEBT.md`.
