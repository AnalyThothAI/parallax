# Token Radar Narrative 1h Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-cut Narrative Intelligence to one realtime `1h/all` compute lane, let non-`1h` Token Radar surfaces reuse only explicit same-target `1h` overlays, and verify the live lane through focused tests plus realtime data-flow checks.

**Architecture:** Token Radar remains the scanner for `5m/1h/4h/24h`; Narrative becomes one bounded CQRS read-model lane keyed by `analysis_window = "1h"`. Runtime workers write only true `1h` admissions, semantics, and digests; API hydration may fan out a ready same-target `1h` digest to `5m/4h/24h` rows with explicit overlay metadata. No old-window compatibility path, no hidden repository fallback, and no HTTP-time LLM calls.

**Tech Stack:** Python 3.13, PostgreSQL, psycopg, FastAPI, Pydantic v2, pytest, OpenAI AgentExecutionGateway-backed narrative providers, React/Vite, TypeScript, Vitest.

---

**Status:** Draft
**Date:** 2026-05-22
**Owning spec:** `docs/superpowers/specs/active/2026-05-22-token-radar-narrative-1h-throughput-root-fix-cn.md`
**Worktree:** `.worktrees/token-radar-narrative-1h-throughput-root-fix/`
**Branch:** `codex/token-radar-narrative-1h-throughput-root-fix`

## Hard-Cut Rules

- Runtime Narrative lanes are exactly `("1h", "all")`.
- Operator configs that still set `narrative_admission.windows` or `token_discussion_digest.windows` to `5m`, `4h`, or `24h` fail validation.
- Operator configs that set `narrative_admission.scopes` or `token_discussion_digest.scopes` to anything except `all` fail validation.
- `token_radar_projection.windows` remains `("5m", "1h", "4h", "24h")`.
- `NarrativeRepository.current_narrative_snapshots_for_targets()` keeps exact `(target, window, scope)` semantics.
- Token Radar hydration owns the only cross-window read-model fanout: non-`1h` surfaces may request `1h` snapshots and decorate them as overlays.
- Non-`1h` surfaces without a ready compatible `1h` digest return `reason = "no_reusable_1h_digest"` and never surface `semantic_labeling_pending`.
- Ops cleanup suppresses non-`1h/all` current admissions and stales non-`1h/all` current digests; old state is not kept live.

## Pre-Flight

- [ ] Verify the spec is approved in this thread.
- [ ] Create an isolated worktree:
  ```bash
  git worktree add .worktrees/token-radar-narrative-1h-throughput-root-fix -b codex/token-radar-narrative-1h-throughput-root-fix main
  cd .worktrees/token-radar-narrative-1h-throughput-root-fix
  git branch --show-current
  git status --short
  ```
  Expected branch: `codex/token-radar-narrative-1h-throughput-root-fix`.
- [ ] Confirm real runtime config paths before any live-data command:
  ```bash
  uv run gmgn-twitter-intel config
  ```
  Expected: `config_path` and `workers_config_path` point under `~/.gmgn-twitter-intel/`. Do not print secrets.
- [ ] Run baseline focused tests:
  ```bash
  uv run pytest tests/unit/test_worker_settings.py -q
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py -q
  uv run pytest tests/unit/domains/narrative_intel/test_discussion_digest_service.py -q
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_epoch_policy.py -q
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_read_model.py -q
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_backlog_health.py -q
  npm --prefix web run test -- --run web/tests/unit/shared/model/narrativeDataGaps.test.ts web/tests/unit/shared/model/tokenRadarCompactCase.test.ts
  ```
  Expected baseline: existing tests pass before edits, except tests added in this plan fail before implementation.

## File Map

- Modify `src/gmgn_twitter_intel/platform/config/settings.py`: hard-cut default Narrative windows to `1h`, reject obsolete Narrative windows, add one digest partial-tail knob.
- Modify `src/gmgn_twitter_intel/domains/narrative_intel/services/narrative_epoch_policy.py`: make `1h` the only digest epoch window and delegate semantic pending decisions to `DiscussionDigestService`.
- Modify `src/gmgn_twitter_intel/domains/narrative_intel/runtime/narrative_admission_worker.py`: default to `1h` and rely on validated runtime windows.
- Modify `src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py`: enqueue missing admitted `1h` source rows every cycle even when due rows already exist.
- Modify `src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py`: request due digest targets only for validated realtime windows and pass partial-tail policy into the service.
- Modify `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`: filter due semantics/digest queries to `1h`, hard-clean non-`1h` realtime state, keep exact snapshot lookup.
- Modify `src/gmgn_twitter_intel/domains/narrative_intel/read_models/narrative_read_model.py`: add explicit Token Radar surface overlay hydration.
- Modify `src/gmgn_twitter_intel/domains/narrative_intel/services/narrative_currentness.py`: keep exact currentness semantics; only add missing-overlay sentinel support if the read model needs a shared constructor.
- Modify `src/gmgn_twitter_intel/domains/narrative_intel/services/discussion_digest_service.py`: allow ready digest when coverage passes and pending semantic tail is within one bounded knob.
- Modify `src/gmgn_twitter_intel/domains/narrative_intel/queries/narrative_backlog_health_query.py`: make health `1h`-lane scoped and add drain estimates.
- Modify `src/gmgn_twitter_intel/app/surfaces/api/routes_status.py` and `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`: pass worker settings to health and expose new fields.
- Modify `src/gmgn_twitter_intel/app/surfaces/cli/parser.py` and `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`: make `rebuild-narrative-intel` default to hard-cut `1h` and report cleanup counts.
- Modify `web/src/lib/types/frontend-contracts.ts`: add optional overlay metadata fields to `TokenDiscussionDigest`.
- Modify `web/src/shared/model/narrativeDataGaps.ts` and `web/src/shared/model/tokenRadarCompactCase.ts`: render overlay and no-reusable states distinctly.
- Add or modify tests listed in each task.

## Task 1: Hard-Cut Narrative Config and Epoch Windows

**Files:**
- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`
- Modify: `src/gmgn_twitter_intel/domains/narrative_intel/services/narrative_epoch_policy.py`
- Test: `tests/unit/test_worker_settings.py`
- Test: `tests/unit/domains/narrative_intel/test_narrative_epoch_policy.py`

- [ ] **Step 1: Write failing settings tests**

  Add these tests to `tests/unit/test_worker_settings.py`:

  ```python
  def test_narrative_runtime_defaults_are_1h_only() -> None:
      settings = WorkersSettings(**yaml.safe_load(default_workers_yaml()))

      assert settings.token_radar_projection.windows == ("5m", "1h", "4h", "24h")
      assert settings.narrative_admission.windows == ("1h",)
      assert settings.token_discussion_digest.windows == ("1h",)
      assert settings.token_discussion_digest.digest_ttl_by_window_seconds == {"1h": 900}
      assert settings.token_discussion_digest.max_pending_semantic_rows_for_digest == 5


  def test_narrative_runtime_rejects_non_1h_windows() -> None:
      payload = yaml.safe_load(default_workers_yaml())
      payload["narrative_admission"]["windows"] = ["1h", "4h"]

      with pytest.raises(ValidationError, match="narrative_admission.windows"):
          WorkersSettings(**payload)

      payload = yaml.safe_load(default_workers_yaml())
      payload["token_discussion_digest"]["windows"] = ["24h"]

      with pytest.raises(ValidationError, match="token_discussion_digest.windows"):
          WorkersSettings(**payload)


  def test_token_discussion_digest_rejects_non_1h_ttl_keys() -> None:
      payload = yaml.safe_load(default_workers_yaml())
      payload["token_discussion_digest"]["digest_ttl_by_window_seconds"] = {"1h": 900, "4h": 1800}

      with pytest.raises(ValidationError, match="digest_ttl_by_window_seconds"):
          WorkersSettings(**payload)
  ```

- [ ] **Step 2: Write failing epoch tests**

  Add this assertion to `tests/unit/domains/narrative_intel/test_narrative_epoch_policy.py`:

  ```python
  def test_epoch_policy_hard_cuts_digest_windows_to_1h() -> None:
      from gmgn_twitter_intel.domains.narrative_intel.services.narrative_epoch_policy import (
          DEFAULT_THRESHOLDS,
          DIGEST_WINDOWS,
          NarrativeEpochPolicy,
      )

      assert DIGEST_WINDOWS == frozenset({"1h"})
      assert set(DEFAULT_THRESHOLDS) == {"1h"}

      decision = NarrativeEpochPolicy().evaluate(
          admission={"window": "4h", "source_event_count": 10, "independent_author_count": 4},
          last_ready_digest=None,
          semantic_coverage={"source_event_count": 10, "missing_semantic_count": 0},
          market_context={},
          now_ms=10_000,
      )

      assert decision.reason == "unsupported_window"
      assert decision.should_refresh is False
      assert decision.should_write_status_digest is False
  ```

- [ ] **Step 3: Run tests to verify they fail**

  ```bash
  uv run pytest tests/unit/test_worker_settings.py::test_narrative_runtime_defaults_are_1h_only tests/unit/test_worker_settings.py::test_narrative_runtime_rejects_non_1h_windows tests/unit/test_worker_settings.py::test_token_discussion_digest_rejects_non_1h_ttl_keys tests/unit/domains/narrative_intel/test_narrative_epoch_policy.py::test_epoch_policy_hard_cuts_digest_windows_to_1h -q
  ```
  Expected: FAIL because defaults still include `5m/4h/24h`, the new digest knob is absent, and `DIGEST_WINDOWS` still includes `4h/24h`.

- [ ] **Step 4: Implement config hard cut**

  In `src/gmgn_twitter_intel/platform/config/settings.py`, add constants near the other worker window constants:

  ```python
  NARRATIVE_REALTIME_WINDOWS = ("1h",)
  NARRATIVE_REALTIME_WINDOW_SET = frozenset(NARRATIVE_REALTIME_WINDOWS)
  ```

  Change `NarrativeAdmissionWorkerSettings` defaults and validators:

  ```python
  class NarrativeAdmissionWorkerSettings(PerWorkerSettings):
      interval_seconds: float = Field(default=60.0, ge=0)
      soft_timeout_seconds: float = Field(default=180.0, ge=0)
      hard_timeout_seconds: float = Field(default=300.0, ge=0)
      advisory_lock_key: int = 2026051901
      wakes_on: tuple[str, ...] = ("token_radar_updated", "resolution_updated")
      windows: tuple[str, ...] = NARRATIVE_REALTIME_WINDOWS
      scopes: tuple[str, ...] = ("all",)
      admission_limit: int = Field(default=200, ge=1)
      source_limit: int = Field(default=2000, ge=1)
      min_rank_score: int = Field(default=30, ge=0)
      hot_rank_limit: int = Field(default=50, ge=1)

      @field_validator("wakes_on", "windows", "scopes", mode="before")
      @classmethod
      def parse_tuple(cls, value: Any) -> tuple[str, ...]:
          return tuple(_split_values(value))

      @field_validator("windows", mode="after")
      @classmethod
      def validate_windows(cls, value: tuple[str, ...]) -> tuple[str, ...]:
          return _validate_narrative_realtime_windows("narrative_admission.windows", value)
  ```

  Change `TokenDiscussionDigestWorkerSettings` defaults and validators:

  ```python
  class TokenDiscussionDigestWorkerSettings(PerWorkerSettings):
      interval_seconds: float = Field(default=120.0, ge=0)
      soft_timeout_seconds: float = Field(default=570.0, ge=0)
      hard_timeout_seconds: float = Field(default=660.0, ge=0)
      batch_size: int = Field(default=25, ge=1)
      max_attempts: int = Field(default=3, ge=1)
      advisory_lock_key: int = 2026051802
      wakes_on: tuple[str, ...] = ("token_radar_updated", "narrative_semantics_updated", "market_tick_written")
      windows: tuple[str, ...] = NARRATIVE_REALTIME_WINDOWS
      scopes: tuple[str, ...] = ("all",)
      min_source_mentions: int = Field(default=3, ge=1)
      min_independent_authors: int = Field(default=2, ge=1)
      min_semantic_coverage: float = Field(default=0.35, ge=0, le=1)
      max_pending_semantic_rows_for_digest: int = Field(default=5, ge=0)
      max_mentions_per_digest: int = Field(default=24, ge=1)
      max_llm_calls_per_cycle: int = Field(default=3, ge=0)
      max_llm_failures_per_cycle: int = Field(default=2, ge=0)
      provider_failure_backoff_seconds: int = Field(default=600, ge=1)
      stance_mix_change_threshold: float = Field(default=0.20, ge=0, le=1)
      attention_mix_change_threshold: float = Field(default=0.20, ge=0, le=1)
      price_move_refresh_pct: float = Field(default=12.0, ge=0)
      digest_ttl_by_window_seconds: dict[str, int] = Field(default_factory=lambda: {"1h": 900})

      @field_validator("wakes_on", "windows", "scopes", mode="before")
      @classmethod
      def parse_tuple(cls, value: Any) -> tuple[str, ...]:
          return tuple(_split_values(value))

      @field_validator("windows", mode="after")
      @classmethod
      def validate_windows(cls, value: tuple[str, ...]) -> tuple[str, ...]:
          return _validate_narrative_realtime_windows("token_discussion_digest.windows", value)

      @field_validator("digest_ttl_by_window_seconds")
      @classmethod
      def validate_digest_ttl_windows(cls, value: dict[str, int]) -> dict[str, int]:
          unsupported_windows = tuple(window for window in value if window not in NARRATIVE_REALTIME_WINDOW_SET)
          if unsupported_windows:
              rejected = ", ".join(unsupported_windows)
              raise ValueError(f"token_discussion_digest.digest_ttl_by_window_seconds supports only 1h; got: {rejected}")
          return value
  ```

  Add the shared validator below the worker setting classes:

  ```python
  def _validate_narrative_realtime_windows(field_name: str, value: tuple[str, ...]) -> tuple[str, ...]:
      if not value:
          raise ValueError(f"{field_name} must be exactly 1h")
      invalid = tuple(window for window in value if window not in NARRATIVE_REALTIME_WINDOW_SET)
      if invalid:
          rejected = ", ".join(invalid)
          raise ValueError(f"{field_name} must contain only 1h; got: {rejected}")
      if tuple(value) != NARRATIVE_REALTIME_WINDOWS:
          raise ValueError(f"{field_name} must be exactly ['1h']")
      return value
  ```

  Update `default_workers_yaml()` narrative blocks:

  ```yaml
  narrative_admission:
    windows: ["1h"]
    scopes: ["all"]
  token_discussion_digest:
    windows: ["1h"]
    scopes: ["all"]
    max_pending_semantic_rows_for_digest: 5
    digest_ttl_by_window_seconds:
      1h: 900
  ```

- [ ] **Step 5: Implement epoch hard cut**

  In `src/gmgn_twitter_intel/domains/narrative_intel/services/narrative_epoch_policy.py`, replace the constants:

  ```python
  DIGEST_WINDOWS = frozenset({"1h"})

  DEFAULT_THRESHOLDS = {
      "1h": NarrativeEpochThreshold(min_new_sources=3, min_new_authors=2, max_epoch_age_ms=15 * 60 * 1000),
  }
  ```

  Remove the initial `pending > 0` block from `NarrativeEpochPolicy.evaluate()` so semantic readiness is decided only by `DiscussionDigestService`:

  ```python
  if last_ready_digest is None:
      if source_count <= 0 or authors <= 0:
          return NarrativeEpochDecision(
              reason="insufficient",
              should_refresh=False,
              should_write_status_digest=True,
              next_due_at_ms=next_due,
          )
      return NarrativeEpochDecision(
          reason="no_ready_digest",
          should_refresh=True,
          should_write_status_digest=False,
          next_due_at_ms=next_due,
          refresh_reason="initial_ready",
      )
  ```

- [ ] **Step 6: Run focused tests**

  ```bash
  uv run pytest tests/unit/test_worker_settings.py tests/unit/domains/narrative_intel/test_narrative_epoch_policy.py -q
  ```
  Expected: PASS.

- [ ] **Step 7: Commit**

  ```bash
  git add src/gmgn_twitter_intel/platform/config/settings.py src/gmgn_twitter_intel/domains/narrative_intel/services/narrative_epoch_policy.py tests/unit/test_worker_settings.py tests/unit/domains/narrative_intel/test_narrative_epoch_policy.py
  git commit -m "fix: hard cut narrative runtime windows to 1h"
  ```

## Task 2: Filter Worker Work Queues to the `1h` Lane

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/narrative_intel/runtime/narrative_admission_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`
- Test: `tests/unit/domains/narrative_intel/test_narrative_workers.py`
- Test: `tests/integration/test_narrative_repository.py`

- [ ] **Step 1: Write failing worker tests**

  Add tests to `tests/unit/domains/narrative_intel/test_narrative_workers.py`:

  ```python
  def test_mention_semantics_enqueues_missing_rows_even_when_due_rows_exist():
      async def scenario():
          repo = FakeNarrativeRepository(
              due_mentions=[
                  {
                      "semantic_id": "semantic-ready",
                      "event_id": "event-ready",
                      "target_type": "chain_token",
                      "target_id": "solana:So111",
                      "text_clean": "ready row",
                      "text_fingerprint": "fp-ready",
                  }
              ],
              due_admissions=[
                  {
                      "admission_id": "admission-1h",
                      "target_type": "chain_token",
                      "target_id": "solana:So111",
                      "window": "1h",
                      "scope": "all",
                      "source_event_ids_json": ["event-new"],
                  }
              ],
              source_rows=[
                  {
                      "event_id": "event-new",
                      "target_type": "chain_token",
                      "target_id": "solana:So111",
                      "text_clean": "new row",
                      "text_fingerprint": "fp-new",
                      "source_received_at_ms": 9_900,
                  }
              ],
          )
          db = FakeDB(repo)
          worker = MentionSemanticsWorker(
              name="mention_semantics",
              settings=fake_settings(windows=("1h",), scopes=("all",)),
              db=db,
              telemetry=SimpleNamespace(),
              provider=BarrierNarrativeProvider(db),
          )

          result = await worker.run_once(now_ms=10_000)

          assert result.notes["enqueue_semantic_inserted"] == 1
          assert repo.enqueued_source_event_ids == ["event-new"]
          assert result.notes["claimed"] == 1
          assert result.processed == 1

      asyncio.run(scenario())


  def test_digest_worker_requests_only_realtime_windows_from_repository():
      repo = FakeDigestRepository()
      worker = TokenDiscussionDigestWorker(
          name="token_discussion_digest",
          settings=fake_digest_settings(windows=("1h",)),
          db=FakeDB(repo),
          telemetry=SimpleNamespace(),
          provider=BarrierNarrativeProvider(FakeDB(repo)),
      )

      worker._due_targets_sync(now_ms=10_000, limit=10)

      assert repo.due_digest_target_calls == [{"now_ms": 10_000, "limit": 10, "windows": ("1h",)}]
  ```

  Extend `FakeNarrativeRepository.due_admissions_for_semantics()` and `FakeDigestRepository.due_digest_targets()` in the same test file to accept and record `windows`.

- [ ] **Step 2: Run tests to verify they fail**

  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py::test_mention_semantics_enqueues_missing_rows_even_when_due_rows_exist tests/unit/domains/narrative_intel/test_narrative_workers.py::test_digest_worker_requests_only_realtime_windows_from_repository -q
  ```
  Expected: FAIL because enqueue currently runs only when no due rows were claimed, and `due_digest_targets()` currently has no `windows` argument.

- [ ] **Step 3: Implement worker-side realtime window helper**

  In `narrative_admission_worker.py`, change the default windows line:

  ```python
  windows = tuple(getattr(self.settings, "windows", ("1h",)) or ("1h",))
  ```

  In `mention_semantics_worker.py`, add:

  ```python
  def _realtime_windows(settings: Any) -> tuple[str, ...]:
      windows = tuple(str(window) for window in (getattr(settings, "windows", ("1h",)) or ("1h",)))
      return windows or ("1h",)
  ```

  In `token_discussion_digest_worker.py`, add the same helper near the bottom of the file.

- [ ] **Step 4: Enqueue missing semantics every cycle**

  Replace the beginning of `MentionSemanticsWorker.run_once_async()` after `max_attempts` is computed:

  ```python
  rows = await asyncio.to_thread(self._claim_due_rows_sync, now_ms=resolved_now_ms, limit=batch_size)
  enqueue_stats = await asyncio.to_thread(self._enqueue_missing_from_admissions_sync, now_ms=resolved_now_ms)
  if not rows:
      rows = await asyncio.to_thread(self._claim_due_rows_sync, now_ms=resolved_now_ms, limit=batch_size)
  if not rows:
      return WorkerResult(
          skipped=1,
          notes={
              "reason": "no_due_mentions",
              "claimed": 0,
              **_prefixed(enqueue_stats, "enqueue_"),
          },
      )
  ```

  In `_enqueue_missing_from_admissions_sync()`, call the repository with the `1h` lane:

  ```python
  due_admissions = repos.narratives.due_admissions_for_semantics(
      now_ms=now_ms,
      limit=admission_limit,
      windows=_realtime_windows(self.settings),
  )
  ```

- [ ] **Step 5: Filter repository due queries**

  In `narrative_repository.py`, change `due_admissions_for_semantics()`:

  ```python
  def due_admissions_for_semantics(
      self,
      *,
      now_ms: int,
      limit: int,
      windows: tuple[str, ...] = ("1h",),
  ) -> list[dict[str, Any]]:
      rows = self.conn.execute(
          """
          SELECT *
          FROM narrative_admissions
          WHERE status = 'admitted'
            AND "window" = ANY(%s)
            AND next_semantics_due_at_ms <= %s
          ORDER BY priority DESC, last_seen_at_ms DESC
          LIMIT %s
          """,
          (list(windows), int(now_ms), int(limit)),
      ).fetchall()
      return [_row(row) for row in rows]
  ```

  Change `due_digest_targets()`:

  ```python
  def due_digest_targets(
      self,
      *,
      now_ms: int,
      limit: int,
      windows: tuple[str, ...] = ("1h",),
  ) -> list[dict[str, Any]]:
      rows = self.conn.execute(
          """
          SELECT *
          FROM narrative_admissions
          WHERE status = 'admitted'
            AND "window" = ANY(%s)
            AND next_digest_due_at_ms <= %s
          ORDER BY priority DESC, last_seen_at_ms DESC
          LIMIT %s
          """,
          (list(windows), int(now_ms), int(limit)),
      ).fetchall()
      return [_row(row) for row in rows]
  ```

  Update `TokenDiscussionDigestWorker._due_targets_sync()`:

  ```python
  return list(
      repos.narratives.due_digest_targets(
          now_ms=now_ms,
          limit=limit,
          windows=_realtime_windows(self.settings),
      )
  )
  ```

- [ ] **Step 6: Add integration assertion for SQL filters**

  In `tests/integration/test_narrative_repository.py`, add a test that inserts one admitted `1h` row and one admitted `24h` row, calls `due_admissions_for_semantics(..., windows=("1h",))` and `due_digest_targets(..., windows=("1h",))`, and asserts only the `1h` `admission_id` is returned.

  Use this assertion shape:

  ```python
  assert [row["admission_id"] for row in semantic_rows] == ["admission-1h"]
  assert [row["admission_id"] for row in digest_rows] == ["admission-1h"]
  ```

- [ ] **Step 7: Run focused tests**

  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py tests/integration/test_narrative_repository.py -q
  ```
  Expected: PASS.

- [ ] **Step 8: Commit**

  ```bash
  git add src/gmgn_twitter_intel/domains/narrative_intel/runtime/narrative_admission_worker.py src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py tests/unit/domains/narrative_intel/test_narrative_workers.py tests/integration/test_narrative_repository.py
  git commit -m "fix: constrain narrative workers to the 1h lane"
  ```

## Task 3: Digest Partial-Complete Policy Without Hiding Backlog

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/narrative_intel/services/discussion_digest_service.py`
- Modify: `src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`
- Test: `tests/unit/domains/narrative_intel/test_discussion_digest_service.py`
- Test: `tests/unit/domains/narrative_intel/test_narrative_workers.py`

- [ ] **Step 1: Write failing service tests**

  Add to `tests/unit/domains/narrative_intel/test_discussion_digest_service.py`:

  ```python
  def test_refresh_decision_allows_bounded_pending_tail_when_coverage_passes() -> None:
      service = DiscussionDigestService(
          min_source_mentions=3,
          min_independent_authors=2,
          min_semantic_coverage=0.35,
          max_pending_semantic_rows_for_digest=5,
      )

      decision = service.refresh_decision(
          {
              "source_event_count": 20,
              "independent_author_count": 8,
              "semantic_row_count": 16,
              "missing_semantic_count": 4,
              "pending_semantic_count": 0,
              "retryable_semantic_count": 0,
              "terminal_unavailable_count": 0,
              "labeled_event_count": 8,
          }
      )

      assert decision.should_refresh is True
      assert decision.reason == "thresholds_met_partial_semantic_tail"


  def test_refresh_decision_blocks_pending_tail_above_tolerance() -> None:
      service = DiscussionDigestService(
          min_source_mentions=3,
          min_independent_authors=2,
          min_semantic_coverage=0.35,
          max_pending_semantic_rows_for_digest=5,
      )

      decision = service.refresh_decision(
          {
              "source_event_count": 20,
              "independent_author_count": 8,
              "semantic_row_count": 14,
              "missing_semantic_count": 6,
              "pending_semantic_count": 0,
              "retryable_semantic_count": 0,
              "terminal_unavailable_count": 0,
              "labeled_event_count": 8,
          }
      )

      assert decision.should_refresh is False
      assert decision.reason == "semantic_labeling_pending"
      assert decision.status_if_not_refresh == "pending"
  ```

- [ ] **Step 2: Run tests to verify they fail**

  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_discussion_digest_service.py::test_refresh_decision_allows_bounded_pending_tail_when_coverage_passes tests/unit/domains/narrative_intel/test_discussion_digest_service.py::test_refresh_decision_blocks_pending_tail_above_tolerance -q
  ```
  Expected: FAIL because `DiscussionDigestService` does not accept `max_pending_semantic_rows_for_digest` and still blocks on any pending semantic row.

- [ ] **Step 3: Implement one bounded-tail knob**

  Update `DiscussionDigestService.__init__()`:

  ```python
  def __init__(
      self,
      *,
      min_source_mentions: int = 3,
      min_independent_authors: int = 2,
      min_semantic_coverage: float = 0.35,
      max_mentions_per_digest: int = DEFAULT_MAX_MENTIONS_PER_DIGEST,
      max_pending_semantic_rows_for_digest: int = 5,
  ) -> None:
      self.min_source_mentions = max(1, int(min_source_mentions))
      self.min_independent_authors = max(1, int(min_independent_authors))
      self.min_semantic_coverage = max(0.0, min(1.0, float(min_semantic_coverage)))
      self.max_mentions_per_digest = max(1, int(max_mentions_per_digest))
      self.max_pending_semantic_rows_for_digest = max(0, int(max_pending_semantic_rows_for_digest))
  ```

  Replace the strict pending block in `refresh_decision()`:

  ```python
  pending_total = missing_semantic_count + pending_semantic_count + retryable_semantic_count
  if pending_total > self.max_pending_semantic_rows_for_digest:
      return DigestRefreshDecision(
          should_refresh=False,
          reason="semantic_labeling_pending",
          status_if_not_refresh="pending",
      )
  if coverage < self.min_semantic_coverage:
      if (
          pending_total == 0
          and source_count > 0
          and semantic_row_count == source_count
          and terminal_unavailable_count > 0
          and labeled + terminal_unavailable_count == semantic_row_count
      ):
          return DigestRefreshDecision(
              should_refresh=False,
              reason="semantic_provider_unavailable",
              status_if_not_refresh="semantic_unavailable",
          )
      return DigestRefreshDecision(
          should_refresh=False,
          reason="low_semantic_coverage",
          status_if_not_refresh="insufficient",
      )
  if pending_total > 0:
      return DigestRefreshDecision(
          should_refresh=True,
          reason="thresholds_met_partial_semantic_tail",
          status_if_not_refresh="pending",
      )
  return DigestRefreshDecision(should_refresh=True, reason="thresholds_met", status_if_not_refresh="pending")
  ```

- [ ] **Step 4: Pass the setting from the digest worker**

  In `TokenDiscussionDigestWorker.__init__()`, add the argument:

  ```python
  max_pending_semantic_rows_for_digest=int(
      getattr(settings, "max_pending_semantic_rows_for_digest", 5) or 5
  ),
  ```

- [ ] **Step 5: Add worker regression test**

  Add to `tests/unit/domains/narrative_intel/test_narrative_workers.py`:

  ```python
  def test_digest_worker_allows_ready_digest_with_bounded_pending_tail():
      async def scenario():
          repo = FakeDigestRepository(
              context={
                  "target_type": "chain_token",
                  "target_id": "solana:So111",
                  "window": "1h",
                  "scope": "all",
                  "mentions": [
                      {"event_id": "event-1", "author_handle": "a", "status": "labeled"},
                      {"event_id": "event-2", "author_handle": "b", "status": "labeled"},
                      {"event_id": "event-3", "author_handle": "c", "status": "labeled"},
                  ],
                  "semantic_rows": [
                      {"event_id": "event-1", "author_handle": "a", "status": "labeled"},
                      {"event_id": "event-2", "author_handle": "b", "status": "labeled"},
                      {"event_id": "event-3", "author_handle": "c", "status": "labeled"},
                  ],
                  "allowed_refs": [{"ref_id": "event:event-1", "kind": "event"}],
                  "source_event_ids_json": ["event-1", "event-2", "event-3", "event-4"],
                  "source_event_count": 4,
                  "semantic_row_count": 3,
                  "missing_semantic_count": 1,
                  "pending_semantic_count": 0,
                  "retryable_semantic_count": 0,
                  "terminal_unavailable_count": 0,
                  "labeled_event_count": 3,
                  "independent_author_count": 3,
                  "source_fingerprint": "fp-current",
              }
          )
          db = FakeDB(repo)
          worker = TokenDiscussionDigestWorker(
              name="token_discussion_digest",
              settings=fake_digest_settings(
                  windows=("1h",),
                  max_pending_semantic_rows_for_digest=1,
              ),
              db=db,
              telemetry=SimpleNamespace(),
              provider=SummarizingNarrativeProvider(),
          )

          result = await worker.run_once(now_ms=10_000)

          assert result.notes["ready"] == 1
          assert repo.replaced_digests[0]["status"] == "ready"
          assert repo.replaced_digests[0]["source_fingerprint"] == "fp-current"

      asyncio.run(scenario())
  ```

- [ ] **Step 6: Run focused tests**

  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_discussion_digest_service.py tests/unit/domains/narrative_intel/test_narrative_workers.py -q
  ```
  Expected: PASS.

- [ ] **Step 7: Commit**

  ```bash
  git add src/gmgn_twitter_intel/domains/narrative_intel/services/discussion_digest_service.py src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py src/gmgn_twitter_intel/platform/config/settings.py tests/unit/domains/narrative_intel/test_discussion_digest_service.py tests/unit/domains/narrative_intel/test_narrative_workers.py
  git commit -m "fix: allow bounded-tail 1h narrative digests"
  ```

## Task 4: Explicit `1h` Overlay for Non-`1h` Token Radar Surfaces

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/narrative_intel/read_models/narrative_read_model.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- Test: `tests/unit/domains/narrative_intel/test_narrative_read_model.py`
- Test: `tests/unit/test_api_narrative_contract.py`

- [ ] **Step 1: Write failing read-model tests**

  Add to `tests/unit/domains/narrative_intel/test_narrative_read_model.py`:

  ```python
  def test_non_1h_token_radar_reuses_ready_1h_digest_as_explicit_overlay():
      repo = FakeNarrativeRepository(
          {
              ("Asset", "asset:solana:token:So111"): {
                  "digest_id": "digest-1h",
                  "target_type": "Asset",
                  "target_id": "asset:solana:token:So111",
                  "window": "1h",
                  "scope": "all",
                  "status": "ready",
                  "headline_zh": "SOL 讨论升温",
                  "dominant_narratives_json": [{"label_zh": "SOL 轮动", "summary_zh": "1h 资金轮动。"}],
                  "data_gaps_json": [],
                  "semantic_coverage": 0.8,
                  "source_event_count": 10,
                  "labeled_event_count": 8,
                  "independent_author_count": 4,
                  "evidence_refs_json": [],
                  "currentness": {"display_status": "current", "reason": "fingerprint_match"},
              }
          }
      )

      result = NarrativeReadModel(repo).hydrate_token_radar(
          {"targets": [{"target_type": "Asset", "target_id": "asset:solana:token:So111"}]},
          window="4h",
          scope="all",
          now_ms=1_000,
      )

      digest = result["targets"][0]["discussion_digest"]
      assert repo.calls == [{"window": "1h", "scope": "all"}]
      assert digest["window"] == "1h"
      assert digest["analysis_window"] == "1h"
      assert digest["source_window"] == "1h"
      assert digest["surface_window"] == "4h"
      assert digest["reuse_reason"] == "target_current_1h_narrative"
      assert digest["currentness"]["display_status"] == "current"
      assert digest["currentness"]["reason"] == "fingerprint_match"


  def test_non_1h_token_radar_without_ready_1h_digest_returns_no_reusable_reason():
      repo = FakeNarrativeRepository(
          {
              ("Asset", "asset:solana:token:So111"): {
                  "target_type": "Asset",
                  "target_id": "asset:solana:token:So111",
                  "window": "1h",
                  "scope": "all",
                  "status": "pending",
                  "data_gaps_json": [{"reason": "semantic_labeling_pending"}],
                  "semantic_coverage": 0.2,
                  "source_event_count": 5,
                  "labeled_event_count": 1,
                  "independent_author_count": 3,
                  "evidence_refs_json": [],
                  "currentness": {"display_status": "not_ready", "reason": "semantic_labeling_pending"},
              }
          }
      )

      result = NarrativeReadModel(repo).hydrate_token_radar(
          {"targets": [{"target_type": "Asset", "target_id": "asset:solana:token:So111"}]},
          window="24h",
          scope="all",
          now_ms=1_000,
      )

      digest = result["targets"][0]["discussion_digest"]
      assert digest["status"] == "pending"
      assert digest["analysis_window"] == "1h"
      assert digest["surface_window"] == "24h"
      assert digest["currentness"]["display_status"] == "not_ready"
      assert digest["currentness"]["reason"] == "no_reusable_1h_digest"
      assert digest["data_gaps"] == [{"reason": "no_reusable_1h_digest"}]
  ```

  Update `FakeNarrativeRepository` in that file:

  ```python
  class FakeNarrativeRepository:
      def __init__(self, digests):
          self.digests = digests
          self.calls = []

      def current_narrative_snapshots_for_targets(self, targets, *, window, scope, schema_version, now_ms):
          self.calls.append({"window": window, "scope": scope})
          return self.digests
  ```

- [ ] **Step 2: Run tests to verify they fail**

  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_read_model.py::test_non_1h_token_radar_reuses_ready_1h_digest_as_explicit_overlay tests/unit/domains/narrative_intel/test_narrative_read_model.py::test_non_1h_token_radar_without_ready_1h_digest_returns_no_reusable_reason -q
  ```
  Expected: FAIL because `hydrate_token_radar()` currently queries the requested surface window and does not add overlay metadata.

- [ ] **Step 3: Implement surface-aware Token Radar hydration**

  In `narrative_read_model.py`, add constants:

  ```python
  TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW = "1h"
  TOKEN_RADAR_NARRATIVE_SURFACE_WINDOWS = frozenset({"5m", "4h", "24h"})
  OVERLAY_READY_STATUSES = frozenset({"current", "updating", "stale"})
  ```

  Replace `hydrate_token_radar()` with:

  ```python
  def hydrate_token_radar(self, data: dict[str, Any], *, window: str, scope: str, now_ms: int) -> dict[str, Any]:
      targets = _extract_targets(data)
      normalized_scope = _normalize_scope(scope)
      analysis_window = TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW if window in TOKEN_RADAR_NARRATIVE_SURFACE_WINDOWS else window
      digests = self.repository.current_narrative_snapshots_for_targets(
          targets,
          window=analysis_window,
          scope=normalized_scope,
          schema_version=NARRATIVE_SCHEMA_VERSION,
          now_ms=now_ms,
      )
      if window in TOKEN_RADAR_NARRATIVE_SURFACE_WINDOWS:
          digests = _surface_overlay_digests(
              targets,
              digests,
              surface_window=window,
              scope=normalized_scope,
              now_ms=now_ms,
          )
      hydrated = dict(data)
      for key in ("targets", "attention", "items"):
          if isinstance(hydrated.get(key), list):
              hydrated[key] = [self._hydrate_row(row, digests, now_ms=now_ms) for row in hydrated[key]]
      return hydrated
  ```

  Add helpers below `_missing_digest()`:

  ```python
  def _surface_overlay_digests(
      targets: list[dict[str, str]],
      digests: dict[tuple[str, str], dict[str, Any]],
      *,
      surface_window: str,
      scope: str,
      now_ms: int,
  ) -> dict[tuple[str, str], dict[str, Any]]:
      result: dict[tuple[str, str], dict[str, Any]] = {}
      for target in targets:
          target_type = str(target.get("target_type") or "")
          target_id = str(target.get("target_id") or "")
          key = (target_type, target_id)
          row = digests.get(key)
          if _is_reusable_1h_overlay(row):
              result[key] = {
                  **dict(row or {}),
                  "analysis_window": TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW,
                  "source_window": TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW,
                  "surface_window": surface_window,
                  "reuse_reason": "target_current_1h_narrative",
              }
              continue
          result[key] = _missing_surface_overlay_digest(
              target_type=target_type,
              target_id=target_id,
              scope=scope,
              surface_window=surface_window,
              now_ms=now_ms,
          )
      return result


  def _is_reusable_1h_overlay(row: dict[str, Any] | None) -> bool:
      if not row or str(row.get("status") or "") != "ready":
          return False
      currentness = row.get("currentness") if isinstance(row.get("currentness"), dict) else {}
      return str(currentness.get("display_status") or "") in OVERLAY_READY_STATUSES


  def _missing_surface_overlay_digest(
      *,
      target_type: str,
      target_id: str,
      scope: str,
      surface_window: str,
      now_ms: int,
  ) -> dict[str, Any]:
      return {
          "target_type": target_type,
          "target_id": target_id,
          "window": TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW,
          "scope": scope,
          "schema_version": NARRATIVE_SCHEMA_VERSION,
          "status": "pending",
          "is_current": False,
          "analysis_window": TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW,
          "source_window": TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW,
          "surface_window": surface_window,
          "reuse_reason": "no_reusable_1h_digest",
          "data_gaps_json": [{"reason": "no_reusable_1h_digest"}],
          "semantic_coverage": 0.0,
          "source_event_count": 0,
          "labeled_event_count": 0,
          "independent_author_count": 0,
          "evidence_refs_json": [],
          "currentness": public_currentness(
              digest=None,
              admission=None,
              window=TOKEN_RADAR_NARRATIVE_ANALYSIS_WINDOW,
              now_ms=now_ms,
              reason="no_reusable_1h_digest",
          ),
      }
  ```

- [ ] **Step 4: Add schema fields**

  In `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`, add optional fields to `TokenDiscussionDigestData`:

  ```python
  analysis_window: str | None = None
  source_window: str | None = None
  surface_window: str | None = None
  reuse_reason: str | None = None
  ```

- [ ] **Step 5: Run focused backend tests**

  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_read_model.py tests/unit/test_api_narrative_contract.py -q
  ```
  Expected: PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add src/gmgn_twitter_intel/domains/narrative_intel/read_models/narrative_read_model.py src/gmgn_twitter_intel/app/surfaces/api/schemas.py tests/unit/domains/narrative_intel/test_narrative_read_model.py tests/unit/test_api_narrative_contract.py
  git commit -m "feat: expose 1h narrative overlays on radar surfaces"
  ```

## Task 5: Hard-Cut Ops Cleanup and `1h` Health Drain Math

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/narrative_intel/queries/narrative_backlog_health_query.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/routes_status.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/parser.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
- Test: `tests/unit/domains/narrative_intel/test_narrative_backlog_health.py`
- Test: `tests/integration/test_narrative_repository.py`

- [ ] **Step 1: Write failing cleanup test**

  In `tests/integration/test_narrative_repository.py`, add a test that seeds:

  - admitted `1h` admission with current source `event-1`;
  - admitted `24h` admission for the same target;
  - current ready `24h` digest;
  - queued semantic row for a source outside the current admitted `1h` source set.

  Assert:

  ```python
  cleanup = repo.cleanup_narrative_current_hard_cut(
      schema_version="narrative_intel_v1",
      now_ms=10_000,
      realtime_windows=("1h",),
  )

  assert cleanup["suppressed_non_realtime_admissions"] == 1
  assert cleanup["stale_non_realtime_digests"] == 1
  assert cleanup["deleted_obsolete_pending_semantics"] == 1
  ```

- [ ] **Step 2: Write failing health test updates**

  Update `tests/unit/domains/narrative_intel/test_narrative_backlog_health.py` expected payload:

  ```python
  assert health["realtime_windows"] == ["1h"]
  assert health["semantic_backlog"]["estimated_semantic_drain_seconds"] == 120
  assert health["pending_digest_count"] == 7
  assert health["estimated_digest_drain_seconds"] == 360
  ```

  Update `FakeConn.execute()` to assert the semantic backlog SQL filters current admissions:

  ```python
  if "current_sources" in sql:
      assert 'admissions."window" = ANY' in sql
      return FakeCursor(
          [
              {
                  "current_source_rows": 12,
                  "semantic_rows_for_current_sources": 8,
                  "missing_semantic_rows": 4,
                  "admissions_with_missing_semantics": 2,
                  "queued": 3,
                  "retryable": 2,
                  "stale": 0,
                  "unavailable": 1,
                  "suppressed_current_digest_count": 1,
                  "stale_fingerprint_current_digest_count": 3,
                  "oldest_due_at_ms": 6_000,
              }
          ]
      )
  ```

- [ ] **Step 3: Run tests to verify they fail**

  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_backlog_health.py tests/integration/test_narrative_repository.py -q
  ```
  Expected: FAIL because cleanup does not suppress non-`1h` admissions/digests and health has no realtime window or drain estimate fields.

- [ ] **Step 4: Extend cleanup hard cut**

  Change `cleanup_narrative_current_hard_cut()` signature:

  ```python
  def cleanup_narrative_current_hard_cut(
      self,
      *,
      schema_version: str,
      now_ms: int,
      realtime_windows: tuple[str, ...] = ("1h",),
  ) -> dict[str, int]:
  ```

  At the start of the method, suppress non-realtime admissions:

  ```python
  non_realtime_admissions = self.conn.execute(
      """
      UPDATE narrative_admissions
      SET status = 'suppressed',
          reason = 'non_realtime_narrative_window',
          suppressed_at_ms = %s,
          updated_at_ms = %s
      WHERE schema_version = %s
        AND status = 'admitted'
        AND NOT ("window" = ANY(%s))
      """,
      (int(now_ms), int(now_ms), schema_version, list(realtime_windows)),
  )
  ```

  Stale non-realtime current digests:

  ```python
  non_realtime_digests = self.conn.execute(
      """
      UPDATE token_discussion_digests
      SET status = 'stale',
          is_current = false,
          superseded_at_ms = %s
      WHERE schema_version = %s
        AND is_current = true
        AND NOT ("window" = ANY(%s))
      """,
      (int(now_ms), schema_version, list(realtime_windows)),
  )
  ```

  Filter the existing `current_sources` CTE to `AND admissions."window" = ANY(%s)` and return:

  ```python
  return {
      "suppressed_non_realtime_admissions": int(getattr(non_realtime_admissions, "rowcount", 0) or 0),
      "stale_non_realtime_digests": int(getattr(non_realtime_digests, "rowcount", 0) or 0),
      "deleted_obsolete_pending_semantics": int(getattr(obsolete, "rowcount", 0) or 0),
      "stale_suppressed_digests": int(getattr(stale_suppressed, "rowcount", 0) or 0),
      "fingerprint_mismatch_digests_preserved": int(mismatch_preserved["count"] if mismatch_preserved else 0),
  }
  ```

- [ ] **Step 5: Make health `1h` scoped with estimates**

  Change `NarrativeBacklogHealthQuery.__init__()`:

  ```python
  class NarrativeBacklogHealthQuery:
      def __init__(
          self,
          conn: Any,
          *,
          realtime_windows: tuple[str, ...] = ("1h",),
          semantics_rows_per_cycle: int = 10,
          semantics_interval_seconds: int = 60,
          digest_calls_per_cycle: int = 3,
          digest_interval_seconds: int = 120,
      ) -> None:
          self.conn = conn
          self.realtime_windows = tuple(realtime_windows)
          self.semantics_rows_per_cycle = max(1, int(semantics_rows_per_cycle))
          self.semantics_interval_seconds = max(1, int(semantics_interval_seconds))
          self.digest_calls_per_cycle = max(1, int(digest_calls_per_cycle))
          self.digest_interval_seconds = max(1, int(digest_interval_seconds))
  ```

  Include `realtime_windows` in `health()` and compute estimates:

  ```python
  pending_digest_count = self._pending_digest_count(schema_version=schema_version)
  return {
      "schema_version": schema_version,
      "now_ms": int(now_ms),
      "since_hours": since_hours,
      "realtime_windows": list(self.realtime_windows),
      "admissions": self._admission_health(schema_version=schema_version),
      "semantic_backlog": {
          **backlog,
          "estimated_semantic_drain_seconds": _estimate_drain_seconds(
              backlog["total_pending"],
              per_cycle=self.semantics_rows_per_cycle,
              interval_seconds=self.semantics_interval_seconds,
          ),
      },
      "recent_runs": self._recent_runs(since_ms=since_ms, schema_version=schema_version),
      "digest_status_counts": self._digest_status_counts(schema_version=schema_version),
      "digest_reason_counts": self._digest_reason_counts(schema_version=schema_version),
      "pending_digest_count": pending_digest_count,
      "estimated_digest_drain_seconds": _estimate_drain_seconds(
          pending_digest_count,
          per_cycle=self.digest_calls_per_cycle,
          interval_seconds=self.digest_interval_seconds,
      ),
      "epoch": self._epoch_health(now_ms=int(now_ms), schema_version=schema_version),
  }
  ```

  Add helper:

  ```python
  def _estimate_drain_seconds(total: int, *, per_cycle: int, interval_seconds: int) -> int:
      if total <= 0:
          return 0
      cycles = (int(total) + int(per_cycle) - 1) // int(per_cycle)
      return cycles * int(interval_seconds)
  ```

  Add `AND "window" = ANY(%s)` filters to admission, semantic backlog, digest count, reason count, pending digest, and epoch queries.

- [ ] **Step 6: Pass real worker settings from API and ops**

  In `routes_status.py`, construct the health query with runtime settings:

  ```python
  workers = runtime.settings.workers
  health = NarrativeBacklogHealthQuery(
      repos.conn,
      realtime_windows=workers.token_discussion_digest.windows,
      semantics_rows_per_cycle=min(
          int(workers.mention_semantics.batch_size),
          int(workers.mention_semantics.provider_batch_size),
      ),
      semantics_interval_seconds=int(workers.mention_semantics.interval_seconds),
      digest_calls_per_cycle=max(1, int(workers.token_discussion_digest.max_llm_calls_per_cycle)),
      digest_interval_seconds=int(workers.token_discussion_digest.interval_seconds),
  ).health(
      now_ms=_now_ms(),
      since_hours=since_hours,
  )
  ```

  Add schema fields:

  ```python
  class NarrativeSemanticBacklog(ApiSchema):
      estimated_semantic_drain_seconds: int = 0


  class NarrativeBacklogHealthData(ApiSchema):
      realtime_windows: list[str] = Field(default_factory=list)
      estimated_digest_drain_seconds: int = 0
  ```

- [ ] **Step 7: Hard-cut CLI rebuild to `1h`**

  In `parser.py`, change the command defaults:

  ```python
  rebuild_narrative_intel.add_argument("--window", choices=("1h",), default="1h")
  rebuild_narrative_intel.add_argument("--scope", choices=("all",), default="all")
  ```

  In `ops.py`, pass realtime windows into cleanup:

  ```python
  cleanup = _cleanup_narrative_backlog(
      db,
      now_ms=cycle_now_ms,
      realtime_windows=settings.workers.token_discussion_digest.windows,
  )
  ```

  Change `_cleanup_narrative_backlog()`:

  ```python
  def _cleanup_narrative_backlog(db: object, *, now_ms: int, realtime_windows: tuple[str, ...]) -> dict[str, int]:
      with db.worker_session("rebuild_narrative_intel_cleanup") as repos:
          return dict(
              repos.narratives.cleanup_narrative_current_hard_cut(
                  schema_version=NARRATIVE_SCHEMA_VERSION,
                  now_ms=now_ms,
                  realtime_windows=realtime_windows,
              )
          )
  ```

- [ ] **Step 8: Run focused tests**

  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_backlog_health.py tests/integration/test_narrative_repository.py -q
  uv run pytest tests/unit/test_worker_settings.py -q
  ```
  Expected: PASS.

- [ ] **Step 9: Commit**

  ```bash
  git add src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py src/gmgn_twitter_intel/domains/narrative_intel/queries/narrative_backlog_health_query.py src/gmgn_twitter_intel/app/surfaces/api/routes_status.py src/gmgn_twitter_intel/app/surfaces/api/schemas.py src/gmgn_twitter_intel/app/surfaces/cli/parser.py src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py tests/unit/domains/narrative_intel/test_narrative_backlog_health.py tests/integration/test_narrative_repository.py tests/unit/test_worker_settings.py
  git commit -m "fix: hard cut narrative cleanup and health to 1h"
  ```

## Task 6: Frontend Labels for Overlay and No-Reusable States

**Files:**
- Modify: `web/src/lib/types/frontend-contracts.ts`
- Modify: `web/src/shared/model/narrativeDataGaps.ts`
- Modify: `web/src/shared/model/tokenRadarCompactCase.ts`
- Test: `web/tests/unit/shared/model/narrativeDataGaps.test.ts`
- Test: `web/tests/unit/shared/model/tokenRadarCompactCase.test.ts`

- [ ] **Step 1: Write failing frontend tests**

  Add to `web/tests/unit/shared/model/narrativeDataGaps.test.ts`:

  ```typescript
  it("labels 1h overlay reasons without saying generic analysis is running", () => {
    expect(narrativeGapLabel({ reason: "no_reusable_1h_digest" })).toBe("1h 叙事待生成");
    expect(narrativeGapLabel({ reason: "target_current_1h_narrative" })).toBe("1h 叙事已读");
  });
  ```

  Add to `web/tests/unit/shared/model/tokenRadarCompactCase.test.ts`:

  ```typescript
  it("marks reused 1h narrative overlays distinctly on non-1h radar rows", () => {
    const view = buildTokenRadarCompactCase({
      ...tokenFlowFixture(),
      flow: { ...tokenFlowFixture().flow, window: "4h" },
      discussion_digest: {
        ...tokenFlowFixture().discussion_digest!,
        analysis_window: "1h",
        source_window: "1h",
        surface_window: "4h",
        reuse_reason: "target_current_1h_narrative",
      },
    });

    expect(view.narrative.value).toBe("Expansion chase · 1h叙事 · bullish 62%");
    expect(view.narrative.detail).toContain("1h context");
  });

  it("does not render non-trigger rows without a 1h digest as generic analysis running", () => {
    const view = buildTokenRadarCompactCase({
      ...tokenFlowFixture(),
      flow: { ...tokenFlowFixture().flow, window: "24h" },
      discussion_digest: {
        status: "pending",
        analysis_window: "1h",
        source_window: "1h",
        surface_window: "24h",
        reuse_reason: "no_reusable_1h_digest",
        currentness: {
          display_status: "not_ready",
          reason: "no_reusable_1h_digest",
        },
        data_gaps: [{ reason: "no_reusable_1h_digest" }],
      },
    });

    expect(view.narrative.value).toBe("1h 叙事待生成");
    expect(view.narrative.detail).toBe("1h 叙事待生成");
  });
  ```

- [ ] **Step 2: Run tests to verify they fail**

  ```bash
  npm --prefix web run test -- --run web/tests/unit/shared/model/narrativeDataGaps.test.ts web/tests/unit/shared/model/tokenRadarCompactCase.test.ts
  ```
  Expected: FAIL because labels and TypeScript contract fields are missing.

- [ ] **Step 3: Add frontend contract fields**

  In `web/src/lib/types/frontend-contracts.ts`, add optional fields to `TokenDiscussionDigest`:

  ```typescript
  analysis_window?: string | null;
  source_window?: string | null;
  surface_window?: string | null;
  reuse_reason?: string | null;
  ```

- [ ] **Step 4: Add reason labels**

  In `web/src/shared/model/narrativeDataGaps.ts`, extend `REASON_LABELS`:

  ```typescript
  no_reusable_1h_digest: "1h 叙事待生成",
  target_current_1h_narrative: "1h 叙事已读",
  thresholds_met_partial_semantic_tail: "1h 叙事已读",
  ```

- [ ] **Step 5: Render overlays distinctly**

  In `tokenRadarCompactCase.ts`, add helper:

  ```typescript
  function isReused1hOverlay(digest: TokenDiscussionDigest | null | undefined): boolean {
    return digest?.reuse_reason === "target_current_1h_narrative";
  }
  ```

  In `compactWhyNowTitle()`, change the ready-title branch:

  ```typescript
  const title = cleanText(digest.dominant_narrative?.title) ?? "叙事已读取";
  const overlaySuffix = isReused1hOverlay(digest) ? " · 1h叙事" : "";
  if (displayStatus === "updating") {
    return `${title}${overlaySuffix} · 更新中 +${compactNumber(currentness.delta_source_event_count ?? 0)}`;
  }
  if (displayStatus === "stale") {
    return `${title}${overlaySuffix} · 上一版`;
  }
  const stance = topMixLabel(digest.stance_mix);
  return stance ? `${title}${overlaySuffix} · ${stance}` : `${title}${overlaySuffix}`;
  ```

  In `compactWhyNowDetail()`, prefix reused overlay detail:

  ```typescript
  const details = [summary, coverageLabel(digest), pulseOverlayLabel(item)].filter(Boolean);
  if (isReused1hOverlay(digest)) {
    details.unshift("1h context");
  }
  return details.join(" · ");
  ```

- [ ] **Step 6: Run focused frontend tests**

  ```bash
  npm --prefix web run test -- --run web/tests/unit/shared/model/narrativeDataGaps.test.ts web/tests/unit/shared/model/tokenRadarCompactCase.test.ts
  ```
  Expected: PASS.

- [ ] **Step 7: Commit**

  ```bash
  git add web/src/lib/types/frontend-contracts.ts web/src/shared/model/narrativeDataGaps.ts web/src/shared/model/tokenRadarCompactCase.ts web/tests/unit/shared/model/narrativeDataGaps.test.ts web/tests/unit/shared/model/tokenRadarCompactCase.test.ts
  git commit -m "fix: label reused 1h narrative overlays"
  ```

## Task 7: Operator Handoff

**Files:**
- Modify: `docs/superpowers/plans/active/2026-05-22-token-radar-narrative-1h-throughput-root-fix-plan-cn.md`
- Modify: `docs/CONTRACTS.md` only if API response examples currently claim non-`1h` narrative windows are independently analyzed.
- Modify: `docs/WORKERS.md` only if the worker inventory still says narrative admission tracks all Radar windows.
- Modify: `docs/TECH_DEBT.md` only for non-trivial follow-ups discovered during verification.

- [ ] **Step 1: Run backend focused unit/contract suite**

  ```bash
  uv run pytest tests/unit/domains/narrative_intel tests/unit/test_api_narrative_contract.py tests/unit/test_cli_ops_contract.py -q
  uv run pytest tests/unit/test_worker_settings.py::test_narrative_runtime_defaults_are_1h_only tests/unit/test_worker_settings.py::test_narrative_runtime_rejects_non_1h_windows tests/unit/test_worker_settings.py::test_narrative_realtime_workers_reject_matched_scope -q
  ```
  Expected: PASS.

- [ ] **Step 2: Run frontend focused suite**

  ```bash
  npm --prefix web run test -- --run web/tests/unit/shared/model/narrativeDataGaps.test.ts web/tests/unit/shared/model/tokenRadarCompactCase.test.ts web/tests/unit/lib/tokenRadar.test.ts
  ```
  Expected: PASS.

- [ ] **Step 3: Build image**

  ```bash
  docker compose build app
  ```
  Expected: image builds successfully. Do not run integration performance stress tests for this release.

- [ ] **Step 4: Validate local config hard failure**

  Create a temporary workers payload from `default_workers_yaml()`, set `token_discussion_digest.windows = ["4h"]`, and verify `WorkersSettings(**payload)` raises `ValidationError`. Do this in a Python one-liner without reading or printing real secrets:

  ```bash
  uv run python - <<'PY'
  import yaml
  from pydantic import ValidationError
  from gmgn_twitter_intel.platform.config.settings import WorkersSettings, default_workers_yaml

  payload = yaml.safe_load(default_workers_yaml())
  payload["token_discussion_digest"]["windows"] = ["4h"]
  try:
      WorkersSettings(**payload)
  except ValidationError:
      print("ok: rejected non-1h narrative window")
  else:
      raise SystemExit("expected validation failure")
  PY
  ```
  Expected output: `ok: rejected non-1h narrative window`.

- [ ] **Step 5: Run live-safe config/path check**

  ```bash
  uv run gmgn-twitter-intel config
  ```
  Expected: paths under `~/.gmgn-twitter-intel/`. Report only paths and redacted booleans.

- [ ] **Step 6: Operator rollout note**

  Add this exact note to the PR description or verification artifact:

  ```markdown
  Rollout gate: update `~/.gmgn-twitter-intel/workers.yaml` so `narrative_admission.windows` and `token_discussion_digest.windows` are `["1h"]`, with `scopes: ["all"]`, before restarting workers. Old configs with `5m`, `4h`, or `24h` now fail validation by design. After restart, run `uv run gmgn-twitter-intel ops rebuild-narrative-intel --window 1h --scope all --drain --cycles 8` to suppress non-1h narrative admissions/digests and drain the 1h lane.
  ```

- [ ] **Step 7: Commit docs updates**

  ```bash
  git add docs/CONTRACTS.md docs/WORKERS.md docs/TECH_DEBT.md docs/superpowers/plans/active/2026-05-22-token-radar-narrative-1h-throughput-root-fix-plan-cn.md
  git commit -m "docs: record narrative 1h hard-cut verification"
  ```

## Self-Review

- **Spec coverage:** G1 is Task 1 and Task 2; G2 is Task 1 and Task 5; G3 is Task 4 and Task 6; G4 is preserved by the admission limits and health counters; G5 is Task 2; G6 is Task 3; G7 is Task 5 and Task 7; G8 is Task 5; G9 is Task 5; G10 is Task 6.
- **KISS check:** one realtime analysis window, one overlay policy, one pending-tail knob, one cleanup path. No feature flag, no dual writer, no repository-level cross-window lookup.
- **Semantic safety:** `1h` digest may be displayed on `5m/4h/24h` only as `analysis_window/source_window = "1h"` and `surface_window = requested window`; non-`1h` source sets are never claimed as analyzed.
- **Compatibility removal:** old non-`1h/all` Narrative configs fail validation; old non-`1h/all` admissions/digests are suppressed/staled by ops cleanup; worker queries filter to `1h/all`.
- **Verification:** focused unit/contract/Vitest suites, image build, and live data-flow checks; live commands must redact secrets and confirm config paths only.
