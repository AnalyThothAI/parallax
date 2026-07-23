# Plan — News Story Agent Hard Cut

**Status**: Superseded
**Superseded by**: `docs/ARCHITECTURE.md`
**Date**: 2026-06-18
**Owning spec**: `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut/spec.md`
**Worktree**: `.worktrees/news-trading-agent-architecture-research/`
**Branch**: `codex/news-trading-agent-architecture-research`
**Approved by**: delegated goal
**Approved at**: 2026-06-18

## Pre-flight

- [x] Worktree exists at `.worktrees/news-trading-agent-architecture-research/` and `git branch --show-current` matches `codex/news-trading-agent-architecture-research`.
- [x] Current change scope is backend News story-current implementation plus architecture/SDD documentation.
- [x] Research has been corrected to avoid new cross-domain price/return subsystems.
- [x] Backend touch sets were narrowed to News storage, dirty targets, worker wiring, page projection, provider/client contracts, docs, and tests.

Known-failing baseline tests:

- None accepted for implementation.

## Architecture decision

Do not add cross-domain price, return-window, eval, or backtest objects in this phase. The production problem is inside News Intel: page rows are story-shaped, but LLM current state is item-scoped. The plan hard-cuts product-facing agent state to story scope.

The desired serving contract is:

```text
canonical item facts remain strict
story identity groups related canonical items
story agent owns one current brief per story key/material input hash
page projection serves story rows from story current state
API/UI never repair missing current state from old item briefs
```

The source-level redundancy audit keeps only two categories of duplication: evidence repetition in observation edges and rebuildable projection/cache fields in `news_page_rows`. It explicitly rejects reintroducing retired `news_story_groups`, `news_story_members`, or the old dirty-target `projection_name = 'story'`.

## File-level edits

### Current implementation branch

- `docs/references/news-agent-trading-research-2026-06-18.md`
- `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut/spec.md`
- `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut/plan.md`
- `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut/tasks.md`
- `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut/verification.md`
- `src/parallax/domains/news_intel/types/news_story_brief.py`
- `src/parallax/domains/news_intel/services/news_story_brief_input.py`
- `src/parallax/domains/news_intel/services/news_story_brief_stage.py`
- `src/parallax/domains/news_intel/runtime/news_story_brief_worker.py`
- `src/parallax/domains/news_intel/runtime/news_projection_work.py`
- `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- `src/parallax/domains/news_intel/repositories/news_repository.py`
- `src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py`
- `src/parallax/platform/db/alembic/versions/20260618_0181_news_story_agent_hard_cut.py`
- `src/parallax/app/runtime/provider_wiring/__init__.py`
- `src/parallax/app/runtime/queue_health.py`
- `src/parallax/app/runtime/wake_bus.py`
- `src/parallax/app/runtime/worker_factories/news_intel.py`
- `src/parallax/app/runtime/worker_manifest.py`
- `src/parallax/platform/config/settings.py`
- `src/parallax/integrations/model_execution/news_item_brief_agent_client.py`
- `tests/unit/domains/news_intel/test_news_story_brief_input.py`
- `tests/unit/domains/news_intel/test_news_story_brief_worker.py`
- `tests/unit/domains/news_intel/test_news_story_agent_admission.py`
- `tests/integration/domains/news_intel/test_news_story_agent_repository.py`
- Existing focused worker, projection, schema, API, and architecture tests.

### Deferred final gates

Per explicit user instruction on 2026-06-18, continue completion without running integration tests for this closeout. These remain the full `Verified` gate:

- Full `make check-all`.
- Runtime `/readyz`, `/api/recent`, and WebSocket golden path.
- Frontend lint only if frontend files change.

## Five-step work method

1. **Clarify**: document the current source chain and dedupe semantics before implementation.
2. **Cut**: define story current state as the product-facing agent output and forbid item-brief fallback.
3. **Refactor**: add story-scoped packet, run ledger, current read model, dirty target, and worker.
4. **Accelerate**: make packet hashes, dirty-target coalescing, worker reuse, and projection unchanged writes testable.
5. **Automate**: enable story brief enqueueing and notification ranking only after story current state is stable.

## Proposed data model

Draft shape for future migration:

```sql
CREATE TABLE news_story_agent_runs (
  run_id text PRIMARY KEY,
  story_brief_key text NOT NULL,
  story_key text NOT NULL,
  story_identity_version text NOT NULL,
  representative_news_item_id text NOT NULL REFERENCES news_items(news_item_id),
  member_news_item_ids_json jsonb NOT NULL,
  provider text NOT NULL,
  model text NOT NULL,
  backend text NOT NULL,
  execution_trace_id text,
  workflow_name text NOT NULL,
  agent_name text NOT NULL,
  lane text NOT NULL,
  artifact_version_hash text NOT NULL,
  prompt_version text NOT NULL,
  schema_version text NOT NULL,
  validator_version text NOT NULL,
  guardrail_version text NOT NULL,
  input_hash text NOT NULL,
  output_hash text,
  execution_started boolean NOT NULL,
  status text NOT NULL,
  outcome text NOT NULL,
  error_class text,
  error text,
  request_json jsonb NOT NULL,
  response_json jsonb,
  validation_errors_json jsonb NOT NULL,
  trace_metadata_json jsonb NOT NULL,
  usage_json jsonb NOT NULL,
  latency_ms integer NOT NULL,
  started_at_ms bigint NOT NULL,
  finished_at_ms bigint NOT NULL,
  created_at_ms bigint NOT NULL
);

CREATE TABLE news_story_agent_briefs (
  story_brief_key text PRIMARY KEY,
  story_key text NOT NULL,
  story_identity_version text NOT NULL,
  representative_news_item_id text NOT NULL REFERENCES news_items(news_item_id),
  member_news_item_ids_json jsonb NOT NULL,
  agent_run_id text NOT NULL REFERENCES news_story_agent_runs(run_id) ON DELETE CASCADE,
  status text NOT NULL,
  direction text NOT NULL,
  decision_class text NOT NULL,
  brief_json jsonb NOT NULL,
  input_hash text NOT NULL,
  artifact_version_hash text NOT NULL,
  prompt_version text NOT NULL,
  schema_version text NOT NULL,
  validator_version text NOT NULL,
  computed_at_ms bigint NOT NULL,
  created_at_ms bigint NOT NULL,
  updated_at_ms bigint NOT NULL
);
```

Stable current identity is `story_brief_key`, not `run_id`.

No separate `news_story_brief_members`, `news_story_groups`, or source-quality snapshot table is part of this plan. Member ids stay as compact current/run JSON and packet evidence until a measured query requires a normalized member table.

## Data-structure simplification map

| Structure | Decision | Implementation rule |
|-----------|----------|---------------------|
| `news_provider_items` | Keep | Source-adapter input and raw payload audit only. |
| `news_items` | Keep | Strict canonical item facts; do not loosen into story identity. |
| `news_item_observation_edges` | Keep | Provenance truth for duplicate/source/provider evidence. |
| Duplicate summaries on `news_items` | Cache | Rebuild from observation edges; do not treat as separate truth. |
| `news_page_rows.story_json` | Keep | Public story envelope and rebuildable read model. |
| Page top-level duplicate/source/provider fields | Cache/index | Denormalized serving fields only. |
| `news_item_agent_runs` | Audit | Historical item run evidence after hard cut. |
| `news_item_agent_briefs` | Cut from public current | No page/API/UI fallback after story current is enabled. |
| `news_story_agent_runs` | Add | Story-scoped audit ledger. |
| `news_story_agent_briefs` | Add | Single authoritative current story agent state. |
| `news_story_groups` / `news_story_members` | Do not add | Retired tables; story identity and packet loading replace membership materialization. |
| `projection_name = 'story'` | Do not add | Retired queue name; use `story_brief`. |
| `provider_rating_json` / `provider_signal_json` | Evidence | Admission/explanation input only, not agent signal truth. |
| `signal_json` / `agent_status` | Cache/envelope | Derived from story current state after the hard cut. |
| `market_scope_json` | Existing metadata | Keep as News-owned scope metadata; do not expand into price/return reads. |

## Story packet builder

Add a deterministic packet builder that uses:

- Representative item and bounded member evidence.
- Observation edge source timeline and duplicate/source/provider-key evidence.
- Entities, token mentions, and fact lanes from story members.
- Source role/trust/source-quality fields.
- Admission, similarity, and material-delta basis.
- Existing deterministic scope metadata only as metadata.

Rules:

- Cap representative text, member snippets, entities, and facts.
- Sort all merged lanes deterministically.
- Evidence refs point only to packet material.
- Packet hash excludes run id, worker time, attempts, leases, and public projection payloads.

## Worker flow

`NewsStoryBriefWorker.run_once` should:

1. Read due story dirty depth.
2. Reserve `news.story_brief` capacity before claiming work.
3. Claim story dirty targets with lease owner and limit.
4. Load story packet candidates through repository.
5. Decide skip/eligible state.
6. Build packet and compute input hash.
7. Skip if current story brief is fresh for hash and version tuple.
8. Restore from matching completed run if valid.
9. Restore terminal failed current from matching failed run if appropriate.
10. Execute model only after deterministic reuse gates fail.
11. Validate output.
12. Insert run ledger.
13. Upsert current story brief.
14. Enqueue page reprojection for member ids.
15. Mark dirty target done/error with claimed CAS fields.

No DB session should remain open during model execution.

## Analyze Gate

| Check | Result |
|-------|--------|
| Spec goals map to file-level edits. | Pass: goals map to story packet/domain types, repository/migration, dirty target, worker, projection/API/UI, and docs cleanup. |
| Plan preserves architecture boundaries. | Pass: all new objects are News Intel-owned and no cross-domain price/return reads are introduced. |
| Same-type news behavior is explicit. | Pass: deterministic per-item processing is preserved while model current output becomes story-scoped. |
| Compatibility code or old files are not retained as serving state. | Pass: old item briefs may remain audit-only but cannot be public/runtime fallback after hard cut. |
| Parallel touch/conflict sets are explicit. | Pass: current branch uses narrowed backend/doc touch sets, and final verification remains isolated from frontend unless frontend files change. |
| Redundant structures are classified. | Pass: data model keeps evidence and projection caches, cuts retired story membership, and forbids old `story` dirty targets. |

## PR breakdown

1. **Backend story-current slice**: implemented story packet/domain types, migration/repository methods, story dirty target, worker/runtime wiring, provider/client contracts, page projection hard cut, and architecture docs.
2. **Final verification slice**: run the full repository gate and runtime golden path before moving the SDD record to `Verified`.

## Rollout order

1. Land story packet builder behind unit tests.
2. Add database tables before runtime enqueueing.
3. Add story dirty target support with `news_story_brief` as the product-facing agent worker.
4. Keep `news_item_brief` disabled by default and explicit/manual for audit-only reprocessing.
5. Switch page projection to story current state.
6. Remove public item-brief fallback in the same PR as projection hard cut.
7. Archive or retire item brief worker once historical audit reprocessing no longer needs it.

## Rollback

Rollback is operational, not a compatibility shim:

- Disable `news.story_brief` lane capacity.
- Stop story worker.
- Keep fetch, item processing, and page projection serving explicit pending/failed states.
- Re-enable item brief only through an intentional rollback PR, not a silent runtime fallback.

## Acceptance test commands

- AC1: `uv run pytest tests/integration/domains/news_intel/test_news_story_agent_repository.py::test_same_canonical_item_enqueues_one_story_brief_target -q`
- AC2: `uv run pytest tests/unit/domains/news_intel/test_news_story_agent_admission.py::test_similar_story_without_material_delta_skips_model -q`
- AC3: `uv run pytest tests/unit/domains/news_intel/test_news_story_agent_admission.py::test_material_delta_refreshes_one_story_current_brief -q`
- AC4: `uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_restores_completed_story_run_without_second_model_call -q`
- AC5: `uv run pytest tests/integration/domains/news_intel/test_news_page_rows_read_path.py::test_page_rows_read_story_brief_without_item_brief_fallback -q`
- AC6: `uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_old_item_outputs_are_audit_only_after_story_agent_hard_cut -q`
- AC7: `uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_dirty_target_repository_rejects_retired_story_projection_name tests/unit/domains/news_intel/test_news_repository_queries.py -q`

## Verification

Scoped backend verification evidence lives in `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut/verification.md`. This active record is not `Verified` until the final repository and runtime gates are recorded there.
