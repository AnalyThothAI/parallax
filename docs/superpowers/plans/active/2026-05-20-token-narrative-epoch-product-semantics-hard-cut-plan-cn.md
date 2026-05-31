# Token Narrative Epoch Product Semantics Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-cut Token Radar / Token Case narrative from exact source-fingerprint readiness into stable narrative epochs, last-ready snapshots, and explicit current delta/currentness.

**Architecture:** Keep the existing Kappa/CQRS three-writer narrative lane, but change the digest contract: admissions remain the current source frontier, digest rows become sealed epochs, and public read models compose `last_ready_digest + current_admission_delta + currentness`. `TokenDiscussionDigestWorker` no longer refreshes for every fingerprint change; it uses a deterministic `NarrativeEpochPolicy`, never writes 5m digest rows, and never replaces a usable ready digest with a worse pending/status row when current delta is still being processed.

**Tech Stack:** Python 3.13, PostgreSQL, Alembic, psycopg, FastAPI, Pydantic v2, OpenAI Agents through `AgentExecutionGateway`, pytest, ruff, React 19, TanStack Query, Vite/Vitest, OpenAPI-generated frontend types.

---

**Status:** Draft
**Date:** 2026-05-20
**Owning spec:** `docs/superpowers/specs/active/2026-05-20-token-narrative-epoch-product-semantics-hard-cut-cn.md`
**Worktree:** `.worktrees/token-narrative-epoch-product-semantics-hard-cut/`
**Branch:** `codex/token-narrative-epoch-product-semantics-hard-cut`

## Non-Compatibility Rule

This is a hard cut. Do not keep aliases, fallbacks, dual public shapes, old reason labels, exact-fingerprint-only hydration paths, or runtime branches that preserve the previous “digest current only when source fingerprint matches exactly” behavior.

Allowed:

- Historical ready digest rows remain readable as last-ready snapshots.
- Token Radar continues to compute 5m rows.
- `NarrativeAdmissionWorker` may continue admitting 5m frontier rows so health/read models can return `unsupported_window`.
- Existing status digest rows can remain in history, but they must not hide a newer or older usable ready epoch.

Forbidden:

- Writing `token_discussion_digests` for `window='5m'`.
- Replacing a ready digest with `pending`, `insufficient`, or `semantic_unavailable` while last-ready should remain visible as `updating`.
- Marking a digest stale solely because current admission `source_fingerprint` changed.
- Public API responses without `discussion_digest.currentness`.
- Frontend synthesis of narrative prose from factor snapshots or raw post text.
- Runtime names such as `legacy_`, `compat_`, `fallback_`, or `v1` for removed behavior.

## Pre-Flight

- [ ] Confirm spec approval in this thread. The approved product semantics are: no compatibility code, no minute target chasing, 5m scanner only, and Token Case as the canonical narrative dossier.
- [ ] Create the implementation worktree:
  ```bash
  git worktree add .worktrees/token-narrative-epoch-product-semantics-hard-cut -b codex/token-narrative-epoch-product-semantics-hard-cut main
  cd .worktrees/token-narrative-epoch-product-semantics-hard-cut
  git worktree list
  git branch --show-current
  git status --short
  ```
  Expected branch: `codex/token-narrative-epoch-product-semantics-hard-cut`.
- [ ] Confirm live config paths before any real-data check:
  ```bash
  uv run parallax config
  ```
  Expected: `config_path` and `workers_config_path` point at `/Users/qinghuan/.parallax/`. Do not print secret values.
- [ ] Run focused backend baseline:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_discussion_digest_service.py tests/unit/domains/narrative_intel/test_narrative_workers.py tests/unit/domains/narrative_intel/test_narrative_read_model.py tests/unit/domains/narrative_intel/test_narrative_backlog_health.py tests/integration/test_narrative_repository.py tests/unit/test_api_narrative_contract.py -q
  ```
- [ ] Run focused frontend baseline:
  ```bash
  cd web
  npm run test -- --run web/tests/unit/shared/model/tokenRadarCompactCase.test.ts web/tests/unit/features/token-case/model/buildTokenCaseViewModel.test.ts web/tests/unit/shared/model/narrativeDataGaps.test.ts
  ```

Known baseline risks:

- Existing worktree may have unrelated user changes. Do not revert them.
- Integration tests may require a PostgreSQL test database. If unavailable locally, record the exact error and run them in the normal DB-backed check environment before merge.

## File-Level Map

### Create

- `src/parallax/domains/narrative_intel/services/narrative_epoch_policy.py`
  - Pure deterministic policy for `unsupported_window`, `no_ready_digest`, `no_material_delta`, `material_delta_due`, `ttl_refresh_due`, `semantic_pending`, and `insufficient`.
- `src/parallax/domains/narrative_intel/services/narrative_currentness.py`
  - Pure composer for public `discussion_digest.currentness`, delta counts, unsupported sentinels, and stale/updating labels.
- `src/parallax/platform/db/alembic/versions/20260520_0070_token_narrative_epochs.py`
  - Adds epoch metadata to `token_discussion_digests`.
- `tests/unit/domains/narrative_intel/test_narrative_epoch_policy.py`
  - Policy unit tests.
- `tests/unit/domains/narrative_intel/test_narrative_currentness.py`
  - Public currentness composer unit tests.

### Modify

- `src/parallax/domains/narrative_intel/types/discussion_digest.py`
  - Add epoch metadata fields to `TokenDiscussionDigest`.
- `src/parallax/domains/narrative_intel/repositories/narrative_repository.py`
  - Persist/read epoch metadata.
  - Add last-ready lookup and public snapshot lookup.
  - Stop demoting current ready digests on source-fingerprint mismatch.
- `src/parallax/domains/narrative_intel/runtime/token_discussion_digest_worker.py`
  - Replace direct `refresh_decision` flow with `NarrativeEpochPolicy`.
  - Skip 5m without writes.
  - Keep last-ready display when semantics/source thresholds fail.
- `src/parallax/domains/narrative_intel/services/discussion_digest_service.py`
  - Preserve threshold/status helpers, but publish ready/status digests with epoch metadata.
- `src/parallax/domains/narrative_intel/read_models/narrative_read_model.py`
  - Hydrate Token Radar and Token Case with public currentness and `narrative_delta`.
- `src/parallax/domains/narrative_intel/interfaces.py`
  - Rename/add `current_narrative_snapshots_for_targets`.
- `src/parallax/domains/narrative_intel/queries/narrative_backlog_health_query.py`
  - Add epoch/currentness health.
- `src/parallax/app/surfaces/api/schemas.py`
  - Add structured public digest/currentness schemas so OpenAPI requires `currentness`.
- `src/parallax/domains/pulse_lab/repositories/pulse_evidence_source_repository.py`
  - Include digest currentness metadata in Pulse context; do not allow stale/updating prose as sole evidence.
- `src/parallax/domains/pulse_lab/services/evidence_packet_builder.py`
  - Compact digest context with currentness and data-gap boundaries.
- `src/parallax/platform/config/settings.py`
  - Hard-cut digest TTL defaults and remove 5m digest TTL from worker YAML.
- `docs/CONTRACTS.md`, `docs/WORKERS.md`, `docs/ARCHITECTURE.md`, `src/parallax/domains/narrative_intel/ARCHITECTURE.md`
  - Document epoch/currentness semantics.
- `web/src/lib/types/openapi.ts`, `web/src/lib/types/frontend-contracts.ts`, `web/src/lib/types/index.ts`
  - Regenerate/sync public types.
- `web/src/shared/model/narrativeDataGaps.ts`
  - Replace old digest labels with new hard-cut reason set.
- `web/src/shared/model/tokenRadarCompactCase.ts`
  - Show `current/updating/stale/not_ready/unsupported_window`.
- `web/src/features/token-case/model/buildTokenCaseViewModel.ts`
  - Surface last-ready computed time, delta counts, semantic coverage, and non-blank updating state.

## Task 1 — Schema And Domain Type Epoch Metadata

- [ ] Add failing migration/schema tests in `tests/unit/test_postgres_schema.py`:
  ```python
  TOKEN_NARRATIVE_EPOCHS_MIGRATION = MIGRATIONS / "20260520_0070_token_narrative_epochs.py"

  def test_token_narrative_epochs_migration_adds_digest_epoch_metadata() -> None:
      text = TOKEN_NARRATIVE_EPOCHS_MIGRATION.read_text()
      for statement in (
          'revision = "20260520_0070"',
          'down_revision = "20260520_0069"',
          "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS epoch_id TEXT",
          "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS epoch_policy_version TEXT",
          "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS source_event_ids_json JSONB",
          "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS source_window_start_ms BIGINT",
          "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS source_window_end_ms BIGINT",
          "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS epoch_closed_at_ms BIGINT",
          "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS display_current_until_ms BIGINT",
          "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS refresh_reason TEXT",
          "idx_token_discussion_digests_epoch_currentness",
          "hard-cut migration is not safely reversible",
      ):
          assert statement in text
  ```
- [ ] Run the new test and verify it fails because the migration does not exist:
  ```bash
  uv run pytest tests/unit/test_postgres_schema.py::test_token_narrative_epochs_migration_adds_digest_epoch_metadata -q
  ```
- [ ] Create `src/parallax/platform/db/alembic/versions/20260520_0070_token_narrative_epochs.py` with:
  ```python
  """Add token narrative epoch metadata."""

  from __future__ import annotations

  from alembic import op

  revision = "20260520_0070"
  down_revision = "20260520_0069"
  branch_labels = None
  depends_on = None

  def upgrade() -> None:
      op.execute("ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS epoch_id TEXT")
      op.execute("ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS epoch_policy_version TEXT")
      op.execute(
          "ALTER TABLE token_discussion_digests "
          "ADD COLUMN IF NOT EXISTS source_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb"
      )
      op.execute("ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS source_window_start_ms BIGINT")
      op.execute("ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS source_window_end_ms BIGINT")
      op.execute("ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS epoch_closed_at_ms BIGINT")
      op.execute("ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS display_current_until_ms BIGINT")
      op.execute("ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS refresh_reason TEXT")
      op.execute(
          """
          CREATE INDEX IF NOT EXISTS idx_token_discussion_digests_epoch_currentness
            ON token_discussion_digests(
              target_type, target_id, "window", scope, schema_version,
              status, computed_at_ms DESC
            )
          """
      )

  def downgrade() -> None:
      raise RuntimeError(
          "token narrative epoch hard-cut migration is not safely reversible; "
          "restore a pre-migration backup instead"
      )
  ```
- [ ] Modify `src/parallax/domains/narrative_intel/types/discussion_digest.py`:
  ```python
  epoch_id: str | None = None
  epoch_policy_version: str | None = None
  source_event_ids: list[str] = Field(default_factory=list)
  source_window_start_ms: int | None = None
  source_window_end_ms: int | None = None
  epoch_closed_at_ms: int | None = None
  display_current_until_ms: int | None = None
  refresh_reason: str | None = None
  ```
- [ ] Modify `_digest_payload()` and `replace_current_digest()` in `narrative_repository.py` to persist/select the new columns. Map persisted `source_event_ids_json` to public/domain `source_event_ids`.
- [ ] Add `tests/unit/domains/narrative_intel/test_types_and_validation.py` coverage proving `TokenDiscussionDigest` accepts epoch metadata and keeps ready validation unchanged.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_postgres_schema.py::test_token_narrative_epochs_migration_adds_digest_epoch_metadata tests/unit/domains/narrative_intel/test_types_and_validation.py -q
  ```
- [ ] Commit:
  ```bash
  git add src/parallax/platform/db/alembic/versions/20260520_0070_token_narrative_epochs.py src/parallax/domains/narrative_intel/types/discussion_digest.py src/parallax/domains/narrative_intel/repositories/narrative_repository.py tests/unit/test_postgres_schema.py tests/unit/domains/narrative_intel/test_types_and_validation.py
  git commit -m "feat: add token narrative epoch metadata"
  ```

## Task 2 — Deterministic Narrative Epoch Policy

- [ ] Create failing tests in `tests/unit/domains/narrative_intel/test_narrative_epoch_policy.py` for:
  - `5m` returns `unsupported_window`.
  - Ready digest plus one new source below threshold returns `no_material_delta`.
  - No ready digest and sufficient source/semantic coverage returns `no_ready_digest`.
  - New source/author delta above window threshold returns `material_delta_due`.
  - Expired `display_current_until_ms` returns `ttl_refresh_due`.
  - Missing/pending semantics returns `semantic_pending` when no ready digest exists.
  - Missing/pending semantics returns `no_material_delta` or `material_delta_due` without writing status when ready digest exists, depending on source delta materiality.
  - Price move over threshold returns `material_delta_due`.
- [ ] Create `src/parallax/domains/narrative_intel/services/narrative_epoch_policy.py`:
  ```python
  from __future__ import annotations

  from dataclasses import dataclass
  from typing import Any, Literal

  EPOCH_POLICY_VERSION = "token-narrative-epoch-v1"
  DIGEST_WINDOWS = frozenset({"1h", "4h", "24h"})

  EpochDecisionReason = Literal[
      "unsupported_window",
      "no_ready_digest",
      "no_material_delta",
      "material_delta_due",
      "ttl_refresh_due",
      "semantic_pending",
      "insufficient",
  ]

  @dataclass(frozen=True, slots=True)
  class NarrativeEpochDecision:
      reason: EpochDecisionReason
      should_refresh: bool
      should_write_status_digest: bool
      next_due_at_ms: int
      epoch_policy_version: str = EPOCH_POLICY_VERSION
      refresh_reason: str | None = None

  @dataclass(frozen=True, slots=True)
  class NarrativeEpochThreshold:
      min_new_sources: int
      min_new_authors: int
      max_epoch_age_ms: int

  DEFAULT_THRESHOLDS = {
      "1h": NarrativeEpochThreshold(min_new_sources=3, min_new_authors=2, max_epoch_age_ms=15 * 60 * 1000),
      "4h": NarrativeEpochThreshold(min_new_sources=5, min_new_authors=2, max_epoch_age_ms=30 * 60 * 1000),
      "24h": NarrativeEpochThreshold(min_new_sources=8, min_new_authors=3, max_epoch_age_ms=2 * 60 * 60 * 1000),
  }
  ```
- [ ] Implement `NarrativeEpochPolicy.evaluate` with early returns:
  ```python
  class NarrativeEpochPolicy:
      def __init__(
          self,
          *,
          thresholds: dict[str, NarrativeEpochThreshold] | None = None,
          stance_mix_change_threshold: float = 0.20,
          attention_mix_change_threshold: float = 0.20,
          price_move_refresh_pct: float = 12.0,
      ) -> None:
          self.thresholds = thresholds or DEFAULT_THRESHOLDS
          self.stance_mix_change_threshold = float(stance_mix_change_threshold)
          self.attention_mix_change_threshold = float(attention_mix_change_threshold)
          self.price_move_refresh_pct = float(price_move_refresh_pct)

      def evaluate(
          self,
          *,
          admission: dict[str, Any],
          last_ready_digest: dict[str, Any] | None,
          semantic_coverage: dict[str, int],
          market_context: dict[str, Any] | None,
          now_ms: int,
      ) -> NarrativeEpochDecision:
          window = str(admission.get("window") or "")
          if window not in DIGEST_WINDOWS:
              return NarrativeEpochDecision(
                  reason="unsupported_window",
                  should_refresh=False,
                  should_write_status_digest=False,
                  next_due_at_ms=int(now_ms) + 24 * 60 * 60 * 1000,
              )
          threshold = self.thresholds[window]
          next_due = int(now_ms) + threshold.max_epoch_age_ms
          source_count = int(semantic_coverage.get("source_event_count") or admission.get("source_event_count") or 0)
          authors = int(admission.get("independent_author_count") or 0)
          pending = (
              int(semantic_coverage.get("missing_semantic_count") or 0)
              + int(semantic_coverage.get("pending_semantic_count") or 0)
              + int(semantic_coverage.get("retryable_semantic_count") or 0)
          )
          if last_ready_digest is None:
              if source_count <= 0 or authors <= 0:
                  return NarrativeEpochDecision("insufficient", False, True, next_due)
              if pending > 0:
                  return NarrativeEpochDecision("semantic_pending", False, True, min(next_due, int(now_ms) + 60_000))
              return NarrativeEpochDecision("no_ready_digest", True, False, next_due, refresh_reason="initial_ready")
          if _ttl_expired(last_ready_digest, now_ms=now_ms):
              return NarrativeEpochDecision("ttl_refresh_due", True, False, next_due, refresh_reason="ttl_refresh_due")
          delta = _source_delta(admission, last_ready_digest)
          if _is_material_delta(delta, threshold=threshold, market_context=market_context):
              return NarrativeEpochDecision("material_delta_due", True, False, next_due, refresh_reason="material_delta_due")
          return NarrativeEpochDecision("no_material_delta", False, False, next_due)
  ```
  Keep helpers pure and covered by tests. The implementation may refine helper internals, but it must preserve the test-visible reasons above.
- [ ] Wire settings thresholds from `TokenDiscussionDigestWorkerSettings`. Hard-cut defaults:
  - `digest_ttl_by_window_seconds`: `{"1h": 900, "4h": 1800, "24h": 7200}`
  - No `5m` key.
  - Remove `min_new_labeled_mentions` and `min_new_authors` from worker settings/default YAML unless they are replaced by new policy-threshold field names in the same edit. Do not accept old field names.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_epoch_policy.py tests/unit/test_worker_settings.py -q
  ```
- [ ] Commit:
  ```bash
  git add src/parallax/domains/narrative_intel/services/narrative_epoch_policy.py src/parallax/platform/config/settings.py tests/unit/domains/narrative_intel/test_narrative_epoch_policy.py tests/unit/test_worker_settings.py
  git commit -m "feat: add deterministic narrative epoch policy"
  ```

## Task 3 — Repository Last-Ready Snapshots And Delta Context

- [ ] Add failing integration tests in `tests/integration/test_narrative_repository.py`:
  - `current_narrative_snapshots_for_targets` returns a ready digest with `currentness.display_status="updating"` when admission fingerprint changes and one new event is added.
  - `current_narrative_snapshots_for_targets` returns `unsupported_window` for `window="5m"` without inserting a digest.
  - `latest_ready_digest_for_target` finds newest `status='ready'` digest even if an older status digest exists.
  - `cleanup_narrative_current_hard_cut` does not mark ready digests stale solely for source fingerprint mismatch.
  - Digest rows persist `epoch_id`, `epoch_policy_version`, `source_event_ids_json`, and `refresh_reason`.
- [ ] Add repository methods:
  ```python
  def latest_ready_digest_for_target(
      self,
      *,
      target_type: str,
      target_id: str,
      window: str,
      scope: str,
      schema_version: str,
  ) -> dict[str, Any] | None:
      """Return newest ready digest for target/window/scope, regardless of source fingerprint."""

  def current_admission_for_target(
      self,
      *,
      target_type: str,
      target_id: str,
      window: str,
      scope: str,
      schema_version: str,
  ) -> dict[str, Any] | None:
      """Return current admitted or suppressed frontier row for public currentness composition."""

  def market_context_for_admission(
      self,
      admission: dict[str, Any],
      *,
      last_ready_digest: dict[str, Any] | None,
  ) -> dict[str, Any]:
      return {"price_move_pct_since_ready": value_or_none}
  ```
- [ ] Implement `current_narrative_snapshots_for_targets` as the new public repository entry point. It should return one row per requested target:
  - `5m` -> unsupported sentinel, no DB digest lookup required.
  - current admission + fingerprint-matched ready digest -> ready row with current admission metadata.
  - current admission + last ready digest with different source set -> last-ready row with admission metadata.
  - current admission + no ready digest -> not-ready sentinel based on semantic coverage.
  - no current admission + last ready digest -> stale/out-of-frontier snapshot.
  - no current admission + no ready digest -> not-ready sentinel.
- [ ] Keep `current_digests_for_targets` only as a thin caller to the new method if still required by interfaces during the same PR. It must not contain exact-fingerprint-only SQL.
- [ ] Change `cleanup_narrative_current_hard_cut`:
  - Keep deletion of obsolete queued/retryable/stale semantics outside current source sets.
  - Keep staling of suppressed digests only when the target leaves the frontier and no Token Case stale display needs `is_current=true`.
  - Remove `stale_fingerprint_mismatch_digests` update behavior. Return `fingerprint_mismatch_digests_preserved` instead of demoting them.
- [ ] Run:
  ```bash
  uv run pytest tests/integration/test_narrative_repository.py -q
  ```
- [ ] Commit:
  ```bash
  git add src/parallax/domains/narrative_intel/repositories/narrative_repository.py tests/integration/test_narrative_repository.py
  git commit -m "feat: expose last-ready narrative snapshots"
  ```

## Task 4 — Digest Worker Epoch Refresh Flow

- [ ] Add failing worker tests in `tests/unit/domains/narrative_intel/test_narrative_workers.py`:
  - Due 5m admission is scanned/deferred and does not call provider or `replace_current_digest`.
  - Due admission with last-ready digest and one below-threshold new event marks admission scanned and does not call provider.
  - Due admission with last-ready digest and pending semantics keeps the ready digest; it does not write a pending status digest.
  - Due admission with no ready digest and pending semantics writes a status digest with `currentness`-compatible data gap.
  - Material delta calls provider and writes ready digest with epoch metadata.
  - LLM budget exhaustion still defers without writing status over a ready digest.
- [ ] Modify `TokenDiscussionDigestWorker.__init__` to instantiate `NarrativeEpochPolicy` from settings:
  ```python
  self.epoch_policy = NarrativeEpochPolicy(
      thresholds=_thresholds_from_settings(settings),
      stance_mix_change_threshold=float(getattr(settings, "stance_mix_change_threshold", 0.20) or 0.20),
      attention_mix_change_threshold=float(getattr(settings, "attention_mix_change_threshold", 0.20) or 0.20),
      price_move_refresh_pct=float(getattr(settings, "price_move_refresh_pct", 12.0) or 12.0),
  )
  ```
- [ ] Rewrite the run loop for each due target:
  ```python
  admission = dict(target)
  context = await asyncio.to_thread(self._digest_context_sync, target=target)
  last_ready = await asyncio.to_thread(self._latest_ready_digest_sync, target=target)
  market_context = await asyncio.to_thread(self._market_context_sync, admission=admission, last_ready=last_ready)
  decision = self.epoch_policy.evaluate(
      admission=admission,
      last_ready_digest=last_ready,
      semantic_coverage=context,
      market_context=market_context,
      now_ms=resolved_now_ms,
  )
  ```
- [ ] Implement decision handling:
  - `unsupported_window`: mark scanned/deferred; no provider call; no digest write.
  - `no_material_delta`: mark scanned using `decision.next_due_at_ms`; no provider call; no digest write.
  - `semantic_pending` / `insufficient` with `last_ready is not None`: mark scanned; no digest write.
  - `semantic_pending` / `insufficient` with no ready digest: write deterministic status digest.
  - `no_ready_digest`, `material_delta_due`, `ttl_refresh_due`: call provider under existing LLM caps.
- [ ] Ensure `build_digest_request` receives sealed epoch context with:
  ```python
  context["epoch_policy_version"] = decision.epoch_policy_version
  context["refresh_reason"] = decision.refresh_reason
  context["epoch_closed_at_ms"] = resolved_now_ms
  context["display_current_until_ms"] = decision.next_due_at_ms
  ```
- [ ] Ensure ready digests write:
  - `epoch_id`: deterministic hash of target/window/scope/schema/source_fingerprint/epoch_closed_at_ms.
  - `epoch_policy_version`: `token-narrative-epoch-v1`.
  - `source_event_ids`: current admission source ids.
  - `source_window_start_ms`, `source_window_end_ms`.
  - `epoch_closed_at_ms`, `display_current_until_ms`, `refresh_reason`.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_workers.py tests/unit/domains/narrative_intel/test_discussion_digest_service.py -q
  ```
- [ ] Commit:
  ```bash
  git add src/parallax/domains/narrative_intel/runtime/token_discussion_digest_worker.py src/parallax/domains/narrative_intel/services/discussion_digest_service.py tests/unit/domains/narrative_intel/test_narrative_workers.py tests/unit/domains/narrative_intel/test_discussion_digest_service.py
  git commit -m "feat: gate narrative digest refresh by epoch policy"
  ```

## Task 5 — Public Currentness Composer And Read Model

- [ ] Add tests in `tests/unit/domains/narrative_intel/test_narrative_currentness.py`:
  - `test_currentness_exact_ready_digest_is_current` asserts fingerprint match returns `display_status="current"` and zero delta.
  - `test_currentness_last_ready_with_delta_is_updating` asserts ready source ids `["a", "b"]` plus current source ids `["a", "b", "c"]` returns `display_status="updating"` and `delta_source_event_count=1`.
  - `test_currentness_last_ready_past_display_until_is_stale` asserts expired `display_current_until_ms` returns `display_status="stale"`.
  - `test_currentness_no_ready_with_admission_is_not_ready` asserts no digest plus current admission returns `display_status="not_ready"` and reason `no_ready_digest`.
  - `test_currentness_unsupported_5m_is_unsupported_window` asserts 5m returns `display_status="unsupported_window"` and reason `unsupported_window`.
  - `test_currentness_out_of_frontier_is_not_current` asserts no current admission plus last-ready digest returns `display_status="out_of_frontier"` for Radar hydration.
- [ ] Create `narrative_currentness.py` with public helpers:
  ```python
  CURRENTNESS_STATUSES = ("current", "updating", "stale", "not_ready", "out_of_frontier", "unsupported_window")

  def public_currentness(
      *,
      digest: dict[str, Any] | None,
      admission: dict[str, Any] | None,
      window: str,
      now_ms: int,
      reason: str | None = None,
  ) -> dict[str, Any]:
      """Return the public currentness object required by API contracts."""

  def narrative_delta_from_currentness(currentness: dict[str, Any]) -> dict[str, Any]:
      """Return Token Case top-level delta metadata derived from currentness."""

  def unsupported_digest_sentinel(*, target_type: str, target_id: str, window: str, scope: str, schema_version: str) -> dict[str, Any]:
      """Return non-persisted 5m unsupported digest payload."""
  ```
- [ ] Modify `_public_digest()` in `narrative_read_model.py` so every public digest includes:
  - `currentness`
  - `coverage`
  - normalized `data_gaps`
  - `dominant_narrative`
  - `bull_bear`
  - `processing` when backlog exists
- [ ] Modify `hydrate_token_case()` to add:
  ```python
  hydrated["narrative_delta"] = narrative_delta_from_currentness(
      hydrated["discussion_digest"]["currentness"]
  )
  ```
- [ ] Modify `hydrate_token_radar()` to keep Radar rows usable even when digest status is `unsupported_window` or `updating`.
- [ ] Update `tests/unit/domains/narrative_intel/test_narrative_read_model.py`:
  - Existing `digest_stale` expectations become `currentness.display_status="updating"` when an admitted source frontier exists.
  - `not_in_current_frontier` expectations become `display_status="out_of_frontier"` for Radar and `stale` for Token Case if a last-ready digest exists.
  - 5m returns `unsupported_window`.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_currentness.py tests/unit/domains/narrative_intel/test_narrative_read_model.py tests/integration/test_api_http.py::test_token_case_discussion_digest -q
  ```
- [ ] Commit:
  ```bash
  git add src/parallax/domains/narrative_intel/services/narrative_currentness.py src/parallax/domains/narrative_intel/read_models/narrative_read_model.py tests/unit/domains/narrative_intel/test_narrative_currentness.py tests/unit/domains/narrative_intel/test_narrative_read_model.py tests/integration/test_api_http.py
  git commit -m "feat: publish narrative currentness snapshots"
  ```

## Task 6 — API Schemas, Contracts, And Generated Frontend Types

- [ ] Add schema tests in `tests/unit/test_api_narrative_contract.py`:
  - Token Case response requires `discussion_digest.currentness`.
  - Token Case response includes `narrative_delta`.
  - Token Radar row examples include `discussion_digest.currentness`.
  - 5m Token Radar row returns `unsupported_window`, not `digest_stale`.
- [ ] Modify `src/parallax/app/surfaces/api/schemas.py` with structured schemas:
  ```python
  class NarrativeCurrentnessData(ApiSchema):
      display_status: Literal["current", "updating", "stale", "not_ready", "out_of_frontier", "unsupported_window"]
      epoch_id: str | None = None
      epoch_policy_version: str | None = None
      ready_source_fingerprint: str | None = None
      current_source_fingerprint: str | None = None
      ready_source_event_count: int = 0
      current_source_event_count: int = 0
      delta_source_event_count: int = 0
      delta_independent_author_count: int = 0
      delta_since_ms: int | None = None
      last_ready_computed_at_ms: int | None = None
      next_refresh_due_at_ms: int | None = None
      reason: str

  class TokenDiscussionDigestData(ApiSchema):
      status: Literal["ready", "pending", "insufficient", "semantic_unavailable", "stale"]
      currentness: NarrativeCurrentnessData
      data_gaps: list[JsonObject] = Field(default_factory=list)
      coverage: JsonObject = Field(default_factory=dict)

  class NarrativeDeltaData(ApiSchema):
      display_status: str
      delta_source_event_count: int = 0
      delta_independent_author_count: int = 0
      label: str | None = None
  ```
- [ ] Change `TokenCaseData.discussion_digest` to `TokenDiscussionDigestData` and add `narrative_delta: NarrativeDeltaData`.
- [ ] Introduce a permissive `TokenRadarRowData(ApiSchema)` with `discussion_digest: TokenDiscussionDigestData | None = None`, then use it for `TokenRadarData.targets` and `TokenRadarData.attention`. Keep `extra="allow"` so existing row fields survive.
- [ ] Regenerate OpenAPI and frontend types using the project’s existing command. If the repo command is not obvious, use:
  ```bash
  uv run parallax openapi > docs/generated/openapi.json
  cd web
  npm run generate:types
  ```
  If either command name differs, inspect `pyproject.toml`, `package.json`, or existing docs and record the exact command used in verification.
- [ ] Update `docs/CONTRACTS.md` with the `currentness` object and 5m unsupported shape from the spec.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/test_api_narrative_contract.py tests/integration/test_api_http.py -q
  cd web && npm run typecheck
  ```
- [ ] Commit:
  ```bash
  git add src/parallax/app/surfaces/api/schemas.py docs/CONTRACTS.md docs/generated/openapi.json web/src/lib/types/openapi.ts web/src/lib/types/frontend-contracts.ts web/src/lib/types/index.ts tests/unit/test_api_narrative_contract.py tests/integration/test_api_http.py
  git commit -m "feat: require narrative currentness in public contracts"
  ```

## Task 7 — Narrative Health Epoch Diagnostics

- [ ] Add tests in `tests/unit/domains/narrative_intel/test_narrative_backlog_health.py` for:
  - `epoch_policy_version`.
  - `unsupported_window_admissions`.
  - `last_ready_digest_count`.
  - `updating_snapshot_count`.
  - `material_delta_due_count`.
  - `no_material_delta_deferred_count`.
  - `last_ready_p50_age_ms`.
  - `last_ready_p95_age_ms`.
  - `delta_source_rows`.
  - `delta_independent_authors`.
  - `digest_refresh_due_by_window`.
  - `digest_refresh_deferred_by_epoch_policy`.
- [ ] Modify `NarrativeBacklogHealthQuery.health()` to include an `epoch` object:
  ```python
  "epoch": {
      "epoch_policy_version": EPOCH_POLICY_VERSION,
      "unsupported_window_admissions": int(unsupported_window_admissions),
      "last_ready_digest_count": int(last_ready_digest_count),
      "updating_snapshot_count": int(updating_snapshot_count),
      "material_delta_due_count": int(material_delta_due_count),
      "no_material_delta_deferred_count": int(no_material_delta_deferred_count),
      "last_ready_p50_age_ms": last_ready_p50_age_ms,
      "last_ready_p95_age_ms": last_ready_p95_age_ms,
      "delta_source_rows": int(delta_source_rows),
      "delta_independent_authors": int(delta_independent_authors),
      "digest_refresh_due_by_window": dict(digest_refresh_due_by_window),
      "digest_refresh_deferred_by_epoch_policy": dict(digest_refresh_deferred_by_epoch_policy),
  }
  ```
- [ ] Keep existing missing semantics fields unchanged. Epoch policy must not hide `missing_semantic_rows`.
- [ ] Update `src/parallax/app/surfaces/api/schemas.py` health models to expose the epoch object.
- [ ] Update ops diagnostics frontend only if it already renders narrative health fields; otherwise leave UI unchanged and rely on API contract.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/domains/narrative_intel/test_narrative_backlog_health.py tests/unit/test_api_status_contract.py -q
  ```
- [ ] Commit:
  ```bash
  git add src/parallax/domains/narrative_intel/queries/narrative_backlog_health_query.py src/parallax/app/surfaces/api/schemas.py tests/unit/domains/narrative_intel/test_narrative_backlog_health.py
  git commit -m "feat: add narrative epoch health diagnostics"
  ```

## Task 8 — Pulse Evidence Packet Boundary

- [ ] Add tests in `tests/unit/domains/pulse_lab/test_evidence_packet_builder.py` or the existing Pulse evidence packet test file:
  - Updating digest is included only as context with `currentness`.
  - Non-abstain packet decisions still require current evidence refs.
  - Stale digest prose is not the sole supporting evidence.
- [ ] Modify `pulse_evidence_source_repository.get_current_discussion_digest()`:
  - Use the narrative snapshot/currentness repository path or include equivalent currentness fields in the selected row.
  - Do not filter solely on exact fingerprint.
  - Still require `status='ready'` for prose included as digest context.
- [ ] Modify `_compact_discussion_digest()` in `evidence_packet_builder.py` to include:
  ```python
  "currentness": payload.get("currentness") or {},
  "data_gaps": payload.get("data_gaps_json") or payload.get("data_gaps") or [],
  ```
- [ ] Add a guard in packet construction: if digest `currentness.display_status` is `updating` or `stale`, the packet may include the digest summary but must not count it as a primary evidence ref.
- [ ] Run:
  ```bash
  uv run pytest tests/unit/domains/pulse_lab/test_evidence_packet_builder.py tests/integration/test_pulse_evidence_repository.py -q
  ```
- [ ] Commit:
  ```bash
  git add src/parallax/domains/pulse_lab/repositories/pulse_evidence_source_repository.py src/parallax/domains/pulse_lab/services/evidence_packet_builder.py tests/unit/domains/pulse_lab/test_evidence_packet_builder.py tests/integration/test_pulse_evidence_repository.py
  git commit -m "feat: pass narrative currentness into pulse evidence"
  ```

## Task 9 — Frontend Token Radar And Token Case Semantics

- [ ] Update `web/src/shared/model/narrativeDataGaps.ts` to the hard-cut reason set:
  ```ts
  const LABELS: Record<string, string> = {
    semantic_labeling_pending: "叙事分析中",
    low_source_volume: "叙事样本不足",
    low_independent_author_count: "独立作者不足",
    low_semantic_coverage: "语义覆盖不足",
    no_ready_digest: "叙事待生成",
    digest_updating: "叙事更新中",
    material_delta_due: "叙事刷新排队中",
    unsupported_window: "5m 实时信号",
    narrative_not_supported_for_window: "5m 实时信号",
    out_of_frontier: "不在当前雷达前沿",
    not_in_current_frontier: "不在当前雷达前沿",
  };
  ```
  Do not keep `digest_stale` as a primary new label. If a test fixture still has it, convert the fixture to `stale` currentness.
- [ ] Update `tokenRadarCompactCase.ts`:
  - `current`: show ready digest title/detail.
  - `updating`: show ready digest title plus `更新中 +N`.
  - `stale`: show ready digest title plus `上一版`.
  - `not_ready`: show data gap label.
  - `unsupported_window`: show `5m 实时信号`.
- [ ] Update `buildTokenCaseViewModel.ts`:
  - Add currentness badges to digest pills.
  - Surface `last_ready_computed_at_ms`.
  - Surface `delta_source_event_count` and `delta_independent_author_count`.
  - Keep the narrative section visible when digest is ready but currentness is `updating`.
- [ ] Update fixtures:
  - `web/tests/fixtures/tokenCaseFixture.ts`
  - `web/tests/unit/lib/tokenRadar.test.ts`
  - route/component fixtures that construct `discussion_digest`.
  Every fixture must include `currentness`.
- [ ] Add/modify tests:
  ```bash
  cd web
  npm run test -- --run web/tests/unit/shared/model/narrativeDataGaps.test.ts web/tests/unit/shared/model/tokenRadarCompactCase.test.ts web/tests/unit/features/token-case/model/buildTokenCaseViewModel.test.ts web/tests/component/features/live/ui/TokenRadarTable.test.tsx web/tests/component/features/token-case/ui/TokenCaseRoute.routing.test.tsx
  npm run typecheck
  ```
- [ ] Commit:
  ```bash
  git add web/src/shared/model/narrativeDataGaps.ts web/src/shared/model/tokenRadarCompactCase.ts web/src/features/token-case/model/buildTokenCaseViewModel.ts web/tests web/src/lib/types
  git commit -m "feat: render narrative currentness in token surfaces"
  ```

## Task 10 — Architecture Guards And Docs

- [ ] Add architecture tests in `tests/architecture/test_worker_runtime_contracts.py`:
  - `TokenDiscussionDigestWorker` imports `NarrativeEpochPolicy`.
  - No SQL path in `current_narrative_snapshots_for_targets` requires source fingerprint equality to return a ready digest.
  - `cleanup_narrative_current_hard_cut` does not demote fingerprint mismatch.
  - No code writes `token_discussion_digests` for 5m.
  - API routes do not import narrative providers or write repositories.
- [ ] Add grep-style tests in a new or existing architecture test:
  ```python
  def test_no_exact_fingerprint_only_public_hydration() -> None:
      text = Path("src/parallax/domains/narrative_intel/repositories/narrative_repository.py").read_text()
      method = text.split("def current_narrative_snapshots_for_targets", 1)[1]
      assert "COALESCE(admissions.source_fingerprint, '') = COALESCE(digest.source_fingerprint, '')" not in method
  ```
- [ ] Update docs:
  - `docs/ARCHITECTURE.md`: narrative epochs are sealed read-model facts, not minute-moving projections.
  - `docs/WORKERS.md`: digest worker uses epoch policy and does not process 5m.
  - `docs/WORKER_FLOW.md`: last-ready + delta public path.
  - `src/parallax/domains/narrative_intel/ARCHITECTURE.md`: writer ownership and currentness read-model composition.
  - `docs/CONTRACTS.md`: public API examples.
- [ ] Run:
  ```bash
  uv run pytest tests/architecture/test_worker_runtime_contracts.py -q
  uv run ruff check .
  ```
- [ ] Commit:
  ```bash
  git add tests/architecture/test_worker_runtime_contracts.py docs/ARCHITECTURE.md docs/WORKERS.md docs/WORKER_FLOW.md docs/CONTRACTS.md src/parallax/domains/narrative_intel/ARCHITECTURE.md
  git commit -m "docs: document narrative epoch hard cut"
  ```

## Task 11 — Rebuild, Verification, And Release Gate

- [ ] Run full backend checks:
  ```bash
  uv run ruff check .
  uv run pytest -q
  ```
- [ ] Run frontend checks:
  ```bash
  cd web
  npm run typecheck
  npm run test -- --run
  npm run build
  ```
- [ ] Run full project gate if available:
  ```bash
  make check-all
  ```
- [ ] Run migration smoke test against a disposable database:
  ```bash
  uv run parallax db upgrade
  ```
  Expected: revision reaches `20260520_0070`.
- [ ] If using live data for smoke verification, first confirm config paths:
  ```bash
  uv run parallax config
  ```
  Then check narrative health without printing secrets:
  ```bash
  curl -fsS "http://127.0.0.1:8765/api/status/narrative-health?token=$GMGN_WS_TOKEN&since_hours=4" | python -m json.tool
  ```
- [ ] Verify public behavior with seeded or live rows:
  - Token Radar 5m row has `discussion_digest.currentness.display_status="unsupported_window"`.
  - Token Radar 1h/4h/24h row with last-ready plus new delta shows `updating`.
  - Token Case 24h remains readable when current delta exists.
  - Health distinguishes missing semantics, LLM capacity defer, epoch-policy defer, unsupported 5m, no ready digest, and stale/out-of-frontier.
- [ ] Create verification artifact:
  `docs/superpowers/plans/active/2026-05-20-token-narrative-epoch-product-semantics-hard-cut-verification-cn.md`
  Include:
  - Commands run with full output for `make check-all`.
  - Coverage.
  - Skipped tests.
  - E2E golden path.
  - Other commands run.
  - Remaining risks.
- [ ] Final commit:
  ```bash
  git add docs/superpowers/plans/active/2026-05-20-token-narrative-epoch-product-semantics-hard-cut-verification-cn.md
  git commit -m "test: verify narrative epoch hard cut"
  ```

## Acceptance Mapping

| Spec AC | Implemented By |
|---|---|
| AC1 last-ready 24h remains visible with one new source | Tasks 3, 5, 6, 9 |
| AC2 below-threshold delta does not call LLM | Tasks 2, 4, 7 |
| AC3 material delta seals new epoch | Tasks 1, 2, 4 |
| AC4 5m unsupported and no LLM work | Tasks 2, 3, 4, 5, 9 |
| AC5 no ready digest returns specific not-ready reason | Tasks 4, 5, 6 |
| AC6 out-of-frontier/stale semantics | Tasks 3, 5, 9 |
| AC7 Pulse treats updating digest as context only | Task 8 |
| AC8 generated schemas require currentness | Task 6 |
| AC9 narrative health explains freshness | Task 7 |
| AC10 architecture scan forbids old paths | Task 10 |

## Review Checklist

- [ ] Search plan and code for forbidden names:
  ```bash
  rg -n "compat_|fallback_|legacy_|digest_stale|exact-fingerprint|exact fingerprint|max_pending_source_age_seconds" src tests web docs/CONTRACTS.md docs/WORKERS.md docs/WORKER_FLOW.md
  ```
  Expected: no runtime compatibility path; `digest_stale` only appears in removed-history docs or migrated old tests that are being deleted in the same PR.
- [ ] Search for 5m digest writes:
  ```bash
  rg -n "\"5m\"|window.*5m|5m:" src/parallax/domains/narrative_intel src/parallax/platform/config/settings.py tests/unit/domains/narrative_intel
  ```
  Expected: 5m appears in Radar/admission/currentness unsupported tests, not in digest TTL defaults or provider-call paths.
- [ ] Confirm `TokenDiscussionDigestWorker` has one runtime write path for `token_discussion_digests`.
- [ ] Confirm API routes still do not write narrative tables.
- [ ] Confirm frontend never builds narrative prose from factor snapshots when digest is missing.

## Rollout Notes

- Deploy schema and code together. This hard cut changes API shape and frontend expectations in one branch.
- Before restarting live workers, remove 5m digest TTL from operator-owned `/Users/qinghuan/.parallax/workers.yaml`; do not add runtime compatibility parsing for the old key.
- Run the narrative rebuild/drain after deploy so current admissions and semantics are aligned under the new epoch policy.
- Existing ready digest rows without epoch metadata remain historical rows. Runtime code must compute public currentness from source ids/fingerprints/counts and must not branch on a migration label.
- Threshold tuning after live observation is allowed through worker config, but adding minute-chasing refresh behavior requires a new spec.
