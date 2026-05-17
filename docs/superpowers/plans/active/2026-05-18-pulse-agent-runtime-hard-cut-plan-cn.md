# Pulse Agent Runtime Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft
**Date:** 2026-05-18
**Owning spec:** `docs/superpowers/specs/active/2026-05-18-pulse-agent-runtime-hard-cut-cn.md`
**Worktree:** `.worktrees/pulse-agent-runtime-hard-cut/`
**Branch:** `codex/pulse-agent-runtime-hard-cut`

**Goal:** 一次性删除 `closed_loop_harness` 半成品 runtime，把 SocialEvent extraction 迁回 `social_enrichment`，统一三个 OpenAI agent client 的执行层，并把 Pulse 改成 EvidencePack + verifier + write gate + outcome loop 的生产闭环。

**Architecture:** 这是单次 hard-cut release，不做旧 harness API/worker/config/WS/CLI 兼容。共享代码只放 OpenAI SDK 执行机械层；prompt、输入构造、schema、业务验证、Pulse 证据包和写入门都留在 domain 层。`closed_loop_harness` 删除后，真正的闭环只围绕 Pulse decision outcome 建立。

**Tech Stack:** Python 3.13, Pydantic v2, openai-agents, psycopg, Alembic, FastAPI, pytest, ruff, PostgreSQL.

---

## Pre-flight

- [ ] Spec `docs/superpowers/specs/active/2026-05-18-pulse-agent-runtime-hard-cut-cn.md` approved.
- [ ] Create isolated worktree:
  ```bash
  git worktree add .worktrees/pulse-agent-runtime-hard-cut -b codex/pulse-agent-runtime-hard-cut main
  ```
- [ ] Verify worktree:
  ```bash
  cd .worktrees/pulse-agent-runtime-hard-cut
  git branch --show-current
  git status --short
  ```
  Expected branch: `codex/pulse-agent-runtime-hard-cut`; expected status: clean.
- [ ] Confirm runtime config path before live-data verification:
  ```bash
  uv run gmgn-twitter-intel config
  ```
  Expected: `config_path` and `workers_config_path` point at `~/.gmgn-twitter-intel/`; do not print secrets.
- [ ] Baseline checks:
  ```bash
  uv run ruff check .
  uv run pytest tests/architecture -q
  ```
- [ ] Take production DB backup before applying destructive harness-table migration. This migration drops report-only shadow harness tables and is not meant to be reversed by app code.

Known-failing baseline tests: none expected. If PostgreSQL-dependent integration tests cannot run locally, record the environment gap in verification and run them where Postgres is available before merge.

---

## Release Shape

Implement as one hard-cut release branch. Internally, use the commit groups below, but do not deploy or merge a partial state:

1. Architecture guardrails and tests.
2. SocialEvent extraction ownership migration.
3. `closed_loop_harness` runtime deletion and storage migration.
4. Pulse agent runtime vocabulary cleanup.
5. Shared OpenAI runtime extraction and prompt relocation.
6. Pulse EvidencePack / verifier / clipper / write gate / outcome loop.
7. API, CLI, docs, generated help, and verification.

Reason: deleting `harness_ops` while leaving API payloads, or adding EvidencePack while leaving old harness terminology, produces a worse mixed architecture. The branch can be reviewed in commits, but production should receive one coherent cut.

---

## File Structure

### Delete

- `src/gmgn_twitter_intel/domains/closed_loop_harness/`
- `src/gmgn_twitter_intel/app/runtime/worker_factories/harness.py`
- `src/gmgn_twitter_intel/app/surfaces/api/routes_harness.py`

### Create

- `src/gmgn_twitter_intel/domains/social_enrichment/repositories/social_event_extraction_repository.py`
- `src/gmgn_twitter_intel/domains/social_enrichment/prompts/social_event_extraction.md`
- `src/gmgn_twitter_intel/domains/social_enrichment/services/social_event_runtime.py`
- `src/gmgn_twitter_intel/domains/watchlist_intel/prompts/handle_summary.md`
- `src/gmgn_twitter_intel/domains/watchlist_intel/types/handle_summary.py`
- `src/gmgn_twitter_intel/domains/watchlist_intel/services/handle_summary_runtime.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/agent_output_schema.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/agent_model_settings.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/agent_stage_runner.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/agent_run_audit.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/types/evidence_pack.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/types/claim_verification.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/evidence_pack_builder.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/evidence_completeness_gate.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/claim_evidence_verifier.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/recommendation_clipper.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/write_gate.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_decision_outcome_service.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_agent_eval_repository.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_outcome_repository.py`
- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260518_0060_pulse_agent_runtime_hard_cut.py`
- `tests/architecture/test_agent_runtime_boundaries.py`
- `tests/integration/test_social_event_extraction_repository.py`
- `tests/unit/pulse_lab/test_evidence_pack_builder.py`
- `tests/unit/pulse_lab/test_claim_evidence_verifier.py`
- `tests/unit/pulse_lab/test_recommendation_clipper.py`
- `tests/unit/pulse_lab/test_write_gate.py`
- `tests/integration/test_pulse_decision_outcomes.py`

### Modify

- `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- `src/gmgn_twitter_intel/app/runtime/bootstrap.py`
- `src/gmgn_twitter_intel/app/runtime/worker_registry.py`
- `src/gmgn_twitter_intel/app/runtime/worker_factories/__init__.py`
- `src/gmgn_twitter_intel/app/runtime/worker_factories/notifications.py`
- `src/gmgn_twitter_intel/app/surfaces/api/http.py`
- `src/gmgn_twitter_intel/app/surfaces/api/routes_events.py`
- `src/gmgn_twitter_intel/app/surfaces/api/routes_pulse.py`
- `src/gmgn_twitter_intel/app/surfaces/api/ws.py`
- `src/gmgn_twitter_intel/app/surfaces/cli/parser.py`
- `src/gmgn_twitter_intel/app/surfaces/cli/commands/read_models.py`
- `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
- `src/gmgn_twitter_intel/platform/config/settings.py`
- `src/gmgn_twitter_intel/domains/social_enrichment/interfaces.py`
- `src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py`
- `src/gmgn_twitter_intel/domains/social_enrichment/types/social_event_extraction.py`
- `src/gmgn_twitter_intel/domains/watchlist_intel/interfaces.py`
- `src/gmgn_twitter_intel/domains/watchlist_intel/runtime/handle_summary_worker.py`
- `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/interfaces.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/providers.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/types/agent_decision.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_runtime.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_eval.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_job_service.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_decision_runtime.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/__init__.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_agent_eval_repository.py` (rename/delete)
- `src/gmgn_twitter_intel/integrations/openai_agents/pulse_decision_agent_client.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/social_event_agent_client.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/watchlist_summary_agent_client.py`
- `src/gmgn_twitter_intel/integrations/openai_agents/tools/*.py` (only if retained as optional helpers)
- `src/gmgn_twitter_intel/app/runtime/provider_wiring/openai.py`
- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/CONTRACTS.md`
- `docs/FRONTEND.md`
- `docs/TECH_DEBT.md`
- `docs/generated/cli-help.md`

---

## File-Level Edits

### Architecture tests first

#### `tests/architecture/test_agent_runtime_boundaries.py`

Create tests that initially fail:

- `test_closed_loop_harness_domain_removed`
  - Assert `src/gmgn_twitter_intel/domains/closed_loop_harness` does not exist.
- `test_no_closed_loop_harness_imports`
  - Scan `src/` and `tests/` Python files for `closed_loop_harness`, `HarnessRepository`, `HarnessService`, `HarnessSnapshotBuilder`, and `HarnessOpsWorker`.
  - Allow only Alembic migration string literals in the destructive migration file if necessary.
- `test_openai_integrations_do_not_own_business_prompts`
  - Assert `integrations/openai_agents` contains no large prompt functions such as `_instructions()` and no domain-specific prompt text blocks.
- `test_domains_do_not_import_openai_agents_sdk`
  - Assert domain packages do not import `agents`, `OpenAIChatCompletionsModel`, `Runner`, or `RunConfig`.
- `test_pulse_public_write_gate_exists`
  - Assert `pulse_lab/services/write_gate.py` exists and `PulseCandidateJobService` imports/uses it.

#### `tests/architecture/test_worker_runtime_contracts.py`

- Remove `harness_ops` from canonical worker expectations.
- Keep the test strict: any reintroduction of `harness_ops` fails.

#### `tests/architecture/test_project_structure.py` and `tests/architecture/test_src_domain_architecture.py`

- Remove `closed_loop_harness` from allowed domain list.
- Add `social_event_extractions` repository to `social_enrichment` expectations if those tests enumerate repositories.

### SocialEvent extraction ownership

#### `src/gmgn_twitter_intel/domains/social_enrichment/repositories/social_event_extraction_repository.py`

Create a repository that owns the existing `social_event_extractions` table:

- `upsert_extraction` as a keyword-only method covering the existing `social_event_extractions` columns and returning `dict[str, Any]`
  - Inserts/updates the existing columns currently written by `HarnessRepository.upsert_social_event_extraction`.
  - Uses the same `extraction_id = sha256("social_event_extraction"|event_id)` convention to avoid unnecessary ID churn.
- `by_event_id(event_id: str) -> dict[str, Any] | None`
- `by_event_ids(event_ids: Sequence[str]) -> dict[str, dict[str, Any] | None]`
- `recent(window: str, limit: int, handles: set[str], event_types: set[str]) -> dict[str, Any]`
  - Only if `/social-events` stays as a non-harness enrichment route. If the public route is deleted, do not add this method.

Do not move `social_event_extractions` into `EnrichmentRepository`; it already owns jobs and model runs. Extraction facts deserve a focused repository.

#### `src/gmgn_twitter_intel/domains/social_enrichment/interfaces.py`

- Export `SocialEventExtractionRepository`.
- Keep existing provider and type exports.

#### `src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py`

Replace current harness materialization:

- Delete import at line 14:
  ```python
  from gmgn_twitter_intel.domains.closed_loop_harness.interfaces import HarnessSnapshotBuilder
  ```
- In `_complete_job_sync`, keep the existing call to `repos.enrichment.complete_social_event_job`.
- Add a call to `repos.social_event_extractions.upsert_extraction` after model run completion.
- Delete the `HarnessSnapshotBuilder` materialization call.
- Return payload shaped as:
  ```python
  {
      "social_event": social_event_row,
      "watchlist_summary_enqueued": bool_value,
  }
  ```
- Change publisher message type from `harness_update` to `social_event_enrichment_update`, or remove publisher emission if no frontend surface consumes it after route cleanup.
- Error note should become `"enrichment_persistence_error"` instead of `"materialization_error"`.

#### Tests

- Update `tests/integration/test_enrichment_worker.py`:
  - Replace `test_enrichment_worker_materializes_closed_loop_harness_and_publishes_update`.
  - New assertion: model run is recorded, social event extraction is persisted, no harness tables are touched, publisher emits no `harness_update`.
- Add `tests/integration/test_social_event_extraction_repository.py`.
- Update watchlist repository tests that use `HarnessRepository` as a fixture; insert `social_event_extractions` via the new repository instead.

### Remove `closed_loop_harness` runtime and public surfaces

#### Delete domain

- Delete every file under `src/gmgn_twitter_intel/domains/closed_loop_harness/`.
- Do not leave a compatibility `interfaces.py`.

#### `src/gmgn_twitter_intel/app/runtime/repository_session.py`

- Remove `HarnessRepository` import and `harness: HarnessRepository` field.
- Add:
  ```python
  from gmgn_twitter_intel.domains.social_enrichment.repositories.social_event_extraction_repository import (
      SocialEventExtractionRepository,
  )
  ```
- Add field:
  ```python
  social_event_extractions: SocialEventExtractionRepository
  ```
- Construct it in `repositories_for_connection`.

#### `src/gmgn_twitter_intel/app/runtime/bootstrap.py`

- Remove `HarnessRepository` import.
- Remove `harness` and `read_harness` fields from `Runtime`.
- Remove pooled harness construction.
- Remove `harness` and `read_harness` assignments from the `Runtime` constructor call.

#### `src/gmgn_twitter_intel/app/runtime/worker_registry.py`

- Remove `"harness_ops"` from `CANONICAL_WORKER_CLASSES`.
- Remove `"harness_ops"` from `WORKER_START_PRIORITY`.

#### `src/gmgn_twitter_intel/app/runtime/worker_factories/__init__.py`

- Remove `harness.py` factory import and the `WorkerFactorySpec` entry for `harness.py`.
- Ensure worker factory key coverage tests still pass.

#### `src/gmgn_twitter_intel/platform/config/settings.py`

- Delete `HarnessOpsWorkerSettings`.
- Delete `WorkersSettings.harness_ops`.
- Delete default YAML block for `harness_ops` near the generated/example config section.
- Because `WorkersSettings.model_config = ConfigDict(extra="forbid")`, stale operator `workers.yaml` with `harness_ops` will fail. This is intended; rollout notes must tell operator to remove it.

#### `src/gmgn_twitter_intel/app/surfaces/api/http.py`

- Remove `routes_harness` import and `router.include_router(routes_harness.router)`.

#### `src/gmgn_twitter_intel/app/surfaces/api/routes_harness.py`

- Delete the file.

#### `src/gmgn_twitter_intel/app/surfaces/api/routes_events.py`

- Remove `"harness": repos.harness.harness_for_event(event_id)`.
- Remove batch `harness_for_events` lookup.
- Event payloads should remain otherwise unchanged.

#### `src/gmgn_twitter_intel/app/surfaces/api/ws.py`

- Remove `"harness": repos.harness.harness_for_event(event_id)`.
- Remove routing for `harness_update`.

#### `src/gmgn_twitter_intel/app/surfaces/api/routes_pulse.py`

- Stop passing `harness=repos.harness` to `SignalPulseService`.

#### `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py`

- Remove constructor `harness` parameter.
- Remove `settlement_coverage` from health payload.
- Delete `_settlement_coverage`.
- If frontend currently expects the key, update frontend contract and tests in the same commit; no fallback key.

#### CLI files

- `src/gmgn_twitter_intel/app/surfaces/cli/parser.py`
  - Delete `harness-snapshots`, `harness-outcomes`, `harness-credits`, `harness-weights`, `attribute-harness-credits`, and `update-harness-weights`.
- `src/gmgn_twitter_intel/app/surfaces/cli/commands/read_models.py`
  - Remove harness command branches and `HarnessService` import.
- `src/gmgn_twitter_intel/app/surfaces/cli/commands/ops.py`
  - Remove harness ops imports and branches.

#### Notifications

- `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py`
  - Remove `harness` constructor parameter and `self.harness`.
  - Remove the call that extends candidates with `_harness_snapshots`.
  - Delete `_harness_snapshots`.
  - Remove rule id `harness_snapshot_high_score` from default rule config if present.
- `src/gmgn_twitter_intel/app/runtime/worker_factories/notifications.py`
  - Remove `HarnessService` import.
  - Stop passing `harness=HarnessService(repos.harness)`.
- Update `tests/unit/test_notification_rules.py`:
  - Remove harness fake and `test_harness_snapshot_candidate_uses_combined_score_threshold`.
  - Add assertion that configured rule ids do not include `harness_snapshot_high_score`.

### Storage / migrations

#### `src/gmgn_twitter_intel/platform/db/alembic/versions/20260518_0060_pulse_agent_runtime_hard_cut.py`

Create one hard-cut migration. Use the actual current head as `down_revision`; at time of planning, the latest visible revision is `20260517_0059`.

Upgrade DDL:

```sql
DROP INDEX IF EXISTS idx_event_clusters_event_seen;
DROP INDEX IF EXISTS idx_attention_seeds_event;
DROP TABLE IF EXISTS harness_weights CASCADE;
DROP TABLE IF EXISTS harness_credits CASCADE;
DROP TABLE IF EXISTS harness_outcomes CASCADE;
DROP TABLE IF EXISTS harness_decisions CASCADE;
DROP TABLE IF EXISTS harness_snapshots CASCADE;
DROP TABLE IF EXISTS event_clusters CASCADE;
DROP TABLE IF EXISTS attention_seeds CASCADE;
```

Keep `social_event_extractions`.

Rename Pulse agent runtime tables and columns away from harness vocabulary:

```sql
ALTER TABLE pulse_agent_runtime_versions RENAME TO pulse_agent_runtime_versions;
ALTER TABLE pulse_agent_runtime_versions RENAME COLUMN runtime_hash TO runtime_hash;
ALTER TABLE pulse_agent_runtime_versions RENAME COLUMN runtime_version TO runtime_version;

ALTER TABLE pulse_agent_runs RENAME COLUMN runtime_version TO runtime_version;
ALTER TABLE pulse_agent_runs RENAME COLUMN runtime_hash TO runtime_hash;

ALTER TABLE pulse_agent_eval_cases RENAME COLUMN runtime_hash TO runtime_hash;
ALTER TABLE pulse_agent_eval_results RENAME COLUMN runtime_hash TO runtime_hash;
```

Create Pulse production outcome tables:

```sql
CREATE TABLE IF NOT EXISTS pulse_evidence_packs (
  evidence_pack_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES pulse_agent_runs(run_id) ON DELETE CASCADE,
  candidate_id TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  window TEXT NOT NULL,
  scope TEXT NOT NULL,
  evidence_pack_hash TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  pack_json JSONB NOT NULL,
  quality_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at_ms BIGINT NOT NULL,
  UNIQUE(run_id)
);

CREATE TABLE IF NOT EXISTS pulse_claim_matrices (
  claim_matrix_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES pulse_agent_runs(run_id) ON DELETE CASCADE,
  evidence_pack_id TEXT NOT NULL REFERENCES pulse_evidence_packs(evidence_pack_id) ON DELETE CASCADE,
  matrix_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pass','fail','downgraded')),
  claims_json JSONB NOT NULL,
  verifier_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at_ms BIGINT NOT NULL,
  UNIQUE(run_id)
);

CREATE TABLE IF NOT EXISTS pulse_decision_outcomes (
  outcome_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL,
  run_id TEXT NOT NULL REFERENCES pulse_agent_runs(run_id) ON DELETE CASCADE,
  evidence_pack_hash TEXT NOT NULL,
  runtime_hash TEXT NOT NULL,
  horizon TEXT NOT NULL,
  decision_time_ms BIGINT NOT NULL,
  entry_tick_id TEXT,
  exit_tick_id TEXT,
  entry_price DOUBLE PRECISION,
  exit_price DOUBLE PRECISION,
  realized_return DOUBLE PRECISION,
  max_drawdown_proxy DOUBLE PRECISION,
  liquidity_decay DOUBLE PRECISION,
  outcome_status TEXT NOT NULL CHECK (
    outcome_status IN ('pending','settled','missing_entry','missing_exit','insufficient_market_data')
  ),
  created_at_ms BIGINT NOT NULL,
  settled_at_ms BIGINT,
  UNIQUE(run_id, horizon)
);
```

Indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_pulse_evidence_packs_candidate
  ON pulse_evidence_packs(candidate_id, created_at_ms DESC);
CREATE INDEX IF NOT EXISTS idx_pulse_claim_matrices_run
  ON pulse_claim_matrices(run_id, created_at_ms DESC);
CREATE INDEX IF NOT EXISTS idx_pulse_decision_outcomes_candidate
  ON pulse_decision_outcomes(candidate_id, horizon, decision_time_ms DESC);
CREATE INDEX IF NOT EXISTS idx_pulse_decision_outcomes_status
  ON pulse_decision_outcomes(outcome_status, horizon, decision_time_ms);
```

Downgrade can recreate table names only if cheap, but does not need to preserve dropped shadow data. Mark destructive downgrade clearly. Operational rollback is DB restore from backup.

### Pulse agent runtime vocabulary cleanup

#### Rename repository

- Rename `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_agent_eval_repository.py` to `pulse_agent_eval_repository.py`.
- Rename class `PulseAgentEvalRepository` to `PulseAgentEvalRepository`.
- Rename methods:
  - `upsert_agent_runtime_version` -> `upsert_agent_runtime_version`
  - `agent_runtime_version` -> `agent_runtime_version`
- Rename parameters and row keys from `runtime_hash`/`runtime_version` to `runtime_hash`/`runtime_version`.

#### `src/gmgn_twitter_intel/domains/pulse_lab/services/agent_runtime.py`

- Rename file to `agent_runtime_manifest.py`.
- Rename exported constants:
  - `PULSE_AGENT_RUNTIME_VERSION` -> `PULSE_AGENT_RUNTIME_VERSION`
  - `PULSE_AGENT_STRATEGY` can remain if meaningful, otherwise `PULSE_AGENT_RUNTIME_STRATEGY`.
- Rename functions:
  - `build_pulse_runtime_manifest` -> `build_pulse_agent_runtime_manifest`
  - `pulse_runtime_hash` -> `pulse_runtime_hash`

#### Call sites

Update imports and variable names in:

- `pulse_candidate_job_service.py`
- `pulse_decision_runtime.py`
- `pulse_agent_eval_repository.py`
- `pulse_runs_repository.py`
- `routes_pulse.py` if response includes runtime metadata.
- Tests under `tests/integration/test_pulse_*` and `tests/unit/test_signal_pulse_service.py`.

No compatibility aliases. If a test imports old names, update the test.

### Unified OpenAI runtime

#### `src/gmgn_twitter_intel/integrations/openai_agents/agent_output_schema.py`

Move the strict schema wrapper from Pulse into this file:

- `StrictJsonOutputSchema(output_type: type[Any])`
- `_coerce_dict_additional_properties_to_false`
- `_strip_defs`
- `_force_strict_object_shape`

All three clients use this wrapper.

#### `src/gmgn_twitter_intel/integrations/openai_agents/agent_model_settings.py`

Create:

Create `default_model_settings` returning the current retry policy, qwen `enable_thinking=false` extra body, and `include_usage=True`. Create `api_base` with the same base-url normalization currently copied in multiple clients.

Use current retry policy and `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`.

#### `src/gmgn_twitter_intel/integrations/openai_agents/agent_run_audit.py`

Create focused helpers:

- `stable_sha256(value: Any) -> str`
- `trace_id(seed: str) -> str`
- `extract_usage(result: Any) -> dict[str, Any]`
- `build_trace_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]`

Do not include domain-specific candidate, handle, or event logic here. Domain runtimes pass metadata fields in.

#### `src/gmgn_twitter_intel/integrations/openai_agents/agent_stage_runner.py`

Create `OpenAIAgentStageRunner` that owns:

- model construction from LLMGateway
- `RunConfig`
- safety-net vs direct Runner path
- usage extraction
- latency/status/error audit

It accepts a domain-provided stage spec and returns a typed output plus a neutral stage audit. Pulse can adapt this audit into `StageRunAudit`; Social/Watchlist can adapt into their existing model-run audit.

#### Pulse client

Modify `pulse_decision_agent_client.py`:

- Remove local `_JsonOutputSchema`, `_model_settings`, `_api_base`, `_extract_usage`, and related copied helpers.
- Use `StrictJsonOutputSchema`.
- Use shared model settings and stage runner.
- Keep Pulse-specific tool registrations only until EvidencePack refactor removes required tools. After EvidencePack, tool registration should be optional or deleted.

#### SocialEvent client

Modify `social_event_agent_client.py`:

- Replace direct `output_type=SocialEventPayload` with `StrictJsonOutputSchema(SocialEventPayload)`.
- Use shared model settings and audit helpers.
- Stop calling `social_event_agent_instructions` after prompt relocation; call `SocialEventRuntimeService.stage_spec`.

#### Watchlist client

Modify `watchlist_summary_agent_client.py`:

- Delete `_WatchlistOutputSchema`.
- Move `WatchlistTopicPayload` and `WatchlistHandleSummaryPayload` to `domains/watchlist_intel/types/handle_summary.py`.
- Move `_instructions()` to `domains/watchlist_intel/prompts/handle_summary.md` and load through `HandleSummaryRuntimeService`.
- Use shared stage runner.

### Domain prompt relocation

#### SocialEvent

- Create `domains/social_enrichment/prompts/social_event_extraction.md` from the current `social_event_agent_instructions()` text.
- Keep allowed enum values and schema injection controlled by `SocialEventRuntimeService`, not by string concatenation in integration client.
- Modify `social_event_extraction.py`:
  - Keep Pydantic payloads and domain dataclasses.
  - Remove large prompt function.
  - Keep `social_event_agent_input` only if runtime service uses it; otherwise move input construction into `social_event_runtime.py`.

#### Watchlist

- Create `domains/watchlist_intel/prompts/handle_summary.md`.
- Move payload models into domain type file.
- Runtime service builds input payload and audit metadata.

### Pulse EvidencePack, verifier, clipper, write gate

#### `domains/pulse_lab/types/evidence_pack.py`

Define Pydantic/dataclass models:

- `EvidenceRef`
- `MetricRef`
- `EvidencePackV3`
- `EvidenceQualityMetrics`
- `EvidenceRiskFlag`

Invariants:

- All selected post event IDs are in `source_event_ids`.
- `direct_target_evidence=false` posts cannot support direct catalyst claims alone.
- 1h claims cannot cite 24h-only context without label.

#### `domains/pulse_lab/services/evidence_pack_builder.py`

Build from existing runtime inputs:

- `PulseCandidateContext.factor_snapshot`
- `PulseCandidateContext.selected_posts`
- `PulseCandidateContext.source_event_ids`
- `token_targets.timeline_rows`
- existing `pulse_timeline_context` cluster summaries
- market/profile repositories already in `RepositorySession`

No LLM and no external HTTP. Reuse the SQL behind current agent tools as direct query functions if helpful.

#### `domains/pulse_lab/services/evidence_completeness_gate.py`

Route-specific minimums:

- `research_only`: always no public trading candidate.
- `meme`: requires direct target evidence, independent authors, and market readiness for `trade_candidate` or higher.
- `cex`: requires market/profile completeness and catalyst/text evidence for `trade_candidate` or higher.

Produces max recommendation ceiling and data gaps.

#### `domains/pulse_lab/types/claim_verification.py`

Define:

- `MaterialClaim`
- `ClaimEvidenceMatrix`
- `ClaimSupportStatus`
- `VerifierDecision`

#### `domains/pulse_lab/services/claim_evidence_verifier.py`

Implement deterministic checks:

- Event refs must exist in EvidencePack.
- Claim text must not cite unsupported external facts.
- KOL relay claims count independent authors after duplicate and same-author grouping.
- Catalyst/listing/partnership claims require explicit source text or profile/market fact.
- Market confirmation claims require metric refs with matching direction.

#### `domains/pulse_lab/services/recommendation_clipper.py`

Input:

- gate result
- evidence completeness ceiling
- verifier result
- LLM FinalDecision draft

Output:

- clipped FinalDecision
- downgrade reasons
- public displayability flag

Rules:

- `risk_rejected_high_info` -> `ignore` or `abstain`; no playbook.
- eval/verifier fail -> not displayable.
- high conviction requires route-specific eligibility, not just event count.

#### `domains/pulse_lab/services/write_gate.py`

Input:

- run metadata
- eval result
- verifier result
- clipper result

Output:

- `allow_public_candidate: bool`
- `candidate_payload` or `blocked_reason`

`PulseCandidateJobService` must call this before `repos.pulse_candidates.upsert_candidate`.

#### `domains/pulse_lab/services/pulse_decision_outcome_service.py`

Records or settles Pulse outcomes using `market_ticks` and `registry`:

- `materialize_pending_outcomes`
- `settle_due_outcomes`

No new worker in this release. Call this opportunistically from `pulse_candidate` after successful public write and expose an ops command only if needed.

### Pulse job service integration

#### `pulse_candidate_job_service.py`

Change lifecycle:

1. Build `EvidencePackV3`.
2. Insert `evidence_pack` run step before LLM.
3. Run evidence completeness gate.
4. If blocked, produce abstain/ignore and write non-displayable result.
5. Run LLM narrative/claim stages through shared runtime.
6. Run claim verifier.
7. Run recommendation clipper.
8. Build deterministic eval case using EvidencePack and ClaimEvidenceMatrix.
9. Run eval.
10. Call WriteGate.
11. Only if allowed, upsert `pulse_candidates` and playbook snapshot.
12. Record/queue `pulse_decision_outcomes`.

Delete logic where eval is inserted and then candidate is unconditionally upserted.

### Tests

#### Architecture

- `uv run pytest tests/architecture/test_agent_runtime_boundaries.py -v`
- `uv run pytest tests/architecture/test_worker_runtime_contracts.py -v`
- `uv run pytest tests/architecture/test_project_structure.py -v`

#### Social enrichment

- `tests/integration/test_enrichment_worker.py::test_enrichment_worker_persists_social_event_extraction_without_harness`
- `tests/integration/test_social_event_extraction_repository.py::test_upsert_and_lookup_by_event_id`
- `tests/integration/watchlist/test_watchlist_intel_repository.py` updated to use social extraction repository fixtures.

#### API / CLI / websocket

- Update `tests/integration/test_api_http.py`:
  - harness endpoints return 404 or are no longer registered, depending on router test style.
  - event payloads do not include `harness`.
- Update `tests/integration/test_api_websocket.py`:
  - replay event payloads do not include `harness`.
  - no `harness_update` route.
- Update `tests/integration/test_cli.py`:
  - removed harness commands are not in parser/help.

#### Pulse

- `tests/unit/pulse_lab/test_evidence_pack_builder.py`
  - Empty/stale/generic evidence produces non-displayable ceiling.
  - Generic basket tweet cannot support direct target catalyst.
  - Same-author duplicate cluster lowers independent author count.
- `tests/unit/pulse_lab/test_claim_evidence_verifier.py`
  - Unsupported listing/catalyst claim fails.
  - Market confirmation without metric ref fails.
  - Supported direct-target social diffusion claim passes.
- `tests/unit/pulse_lab/test_recommendation_clipper.py`
  - `risk_rejected_high_info` clips to non-playbook ignore/abstain.
  - high conviction downgrades if route eligibility missing.
- `tests/unit/pulse_lab/test_write_gate.py`
  - eval fail blocks candidate write.
  - verifier fail blocks displayable write.
  - pass allows write payload.
- Update `tests/integration/test_pulse_desk_e2e.py`:
  - EvidencePack and write gate steps exist.
  - Candidate is not upserted displayable when eval fails.
- Add `tests/integration/test_pulse_decision_outcomes.py`.

---

## PR Breakdown

Recommended: one hard-cut PR with the following commit groups. If review size forces splitting, use stacked PRs and do not deploy until the full stack is merged.

1. **Commit 1 — Architecture guardrails:** Add failing tests for closed-loop removal, no harness imports, no business prompts in integrations, and no OpenAI SDK imports in domains.
2. **Commit 2 — SocialEvent ownership:** Add `SocialEventExtractionRepository`, update `EnrichmentWorker`, update repository session, and migrate tests off `HarnessRepository`.
3. **Commit 3 — Delete closed_loop_harness:** Remove domain, worker, config, routes, CLI commands, websocket payloads, notification rule, bootstrap/runtime fields, and storage tables.
4. **Commit 4 — Rename Pulse runtime vocabulary:** Rename Pulse harness repository/tables/columns/functions to agent runtime/eval vocabulary.
5. **Commit 5 — Unified OpenAI runtime:** Extract shared schema/settings/stage/audit utilities; refactor Pulse, SocialEvent, and Watchlist clients; move prompts into domains.
6. **Commit 6 — Pulse production loop:** Add EvidencePack, verifier, recommendation clipper, write gate, outcome tables/services, and job-service integration.
7. **Commit 7 — Contracts and docs:** Update `docs/ARCHITECTURE.md`, `docs/WORKERS.md`, `docs/CONTRACTS.md`, `docs/FRONTEND.md`, `docs/generated/cli-help.md`, and `docs/TECH_DEBT.md`.
8. **Commit 8 — Verification:** Run full checks, record outputs in verification artifact, and move spec/plan to completed only when implementation ships.

---

## Rollout Order

1. Remove `harness_ops` from operator-owned `~/.gmgn-twitter-intel/workers.yaml`.
2. Confirm runtime config paths:
   ```bash
   uv run gmgn-twitter-intel config
   ```
3. Take DB backup.
4. Apply migration:
   ```bash
   uv run alembic upgrade head
   ```
5. Start workers without `harness_ops`.
6. Run smoke checks:
   ```bash
   uv run gmgn-twitter-intel --help | rg "harness"
   curl -s http://127.0.0.1:<port>/api/harness-health
   curl -s http://127.0.0.1:<port>/api/signal-lab/pulse?window=1h\&scope=all\&limit=5
   ```
   Expected: help grep returns no harness commands; harness endpoint is not registered; Pulse endpoint returns valid non-harness payload.
7. Watch worker health for `collector`, `enrichment`, `handle_summary`, `token_radar_projection`, `pulse_candidate`, notifications, and market workers.
8. Compare first 20 Pulse decisions manually through run steps: evidence pack present, verifier present, write gate present, unsupported claims blocked.

---

## Rollback

This is a destructive hard cut. Safe rollback is backup restore plus previous app version, not an in-app compatibility path.

- Before migration: rollback by reverting code branch; no data action needed.
- After migration but before deploy: restore DB backup or run a manually reviewed downgrade that recreates empty harness tables; historical shadow data is not recoverable without backup.
- After deploy: stop workers, restore DB backup, redeploy previous app, restore `harness_ops` worker config only if reverting to old app.
- Do not attempt to reintroduce `closed_loop_harness` compatibility shims in the new app.

---

## Acceptance Test Commands

Map to spec acceptance criteria.

- AC1:
  ```bash
  rg "closed_loop_harness|HarnessRepository|HarnessService|HarnessSnapshotBuilder|HarnessOpsWorker" src tests
  ```
  Expected: no live code references.

- AC2:
  ```bash
  uv run gmgn-twitter-intel --help | rg "harness"
  ```
  Expected: no output.

- AC3:
  ```bash
  uv run pytest tests/integration/test_api_http.py -k "harness or routes" -v
  ```
  Expected: tests prove `/harness-*` routes are absent.

- AC4:
  ```bash
  uv run pytest tests/integration/test_api_websocket.py tests/integration/test_api_http.py -k "event_payload or websocket_replay" -v
  ```
  Expected: event payloads contain no `harness` key.

- AC5:
  ```bash
  uv run pytest tests/integration/test_enrichment_worker.py::test_enrichment_worker_persists_social_event_extraction_without_harness -v
  ```
  Expected: `model_runs` and `social_event_extractions` persisted; no harness writes.

- AC6-AC9:
  ```bash
  uv run pytest tests/unit/pulse_lab/test_evidence_pack_builder.py \
    tests/unit/pulse_lab/test_claim_evidence_verifier.py \
    tests/unit/pulse_lab/test_recommendation_clipper.py \
    tests/unit/pulse_lab/test_write_gate.py -v
  ```
  Expected: EvidencePack, verifier, clipper, and write gate rules pass.

- AC10:
  ```bash
  uv run pytest tests/unit/test_pulse_decision_agent_client.py \
    tests/unit/test_social_event_agent_client.py \
    tests/unit/test_watchlist_summary_agent_client.py \
    tests/architecture/test_agent_runtime_boundaries.py -v
  ```
  Expected: all clients use shared OpenAI runtime mechanics.

- Full gate:
  ```bash
  uv run ruff check .
  uv run pytest tests -q
  make check-all
  ```

---

## Verification

Create `docs/superpowers/plans/active/2026-05-18-pulse-agent-runtime-hard-cut-verification.md` before claiming completion. It must include:

- Full `make check-all` output.
- Alembic upgrade output.
- `rg` output proving no `closed_loop_harness` live references.
- CLI help regeneration diff summary.
- API/websocket payload samples proving `harness` is gone.
- Pulse run sample proving EvidencePack, claim verifier, recommendation clipper, write gate, and outcome logging are present.
- Remaining risks and follow-ups appended to `docs/TECH_DEBT.md` if non-trivial.
