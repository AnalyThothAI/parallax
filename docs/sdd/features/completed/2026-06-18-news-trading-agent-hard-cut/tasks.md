# Tasks — News Story Agent Hard Cut

**Status**: Superseded
**Superseded by**: `docs/reviews/backend-kiss-architecture-audit-zh-2026-07-21.md`
**Owning plan**: `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut/plan.md`
**Worktree**: `.worktrees/news-trading-agent-architecture-research/`
**Branch**: `codex/news-trading-agent-architecture-research`
**Approved by**: delegated goal
**Approved at**: 2026-06-18

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` includes `## Clarifications` and the research document describes the current News source chain. |
| Checklist | `spec.md` includes `## Requirement Checklist` with News-only and hard-cut gates. |
| Analyze | `plan.md` includes `## Analyze Gate` and source-chain architecture decisions. |
| Implement | Tasks below are ordered so future code work starts with failing tests and narrowed touch sets. |
| Verify | `verification.md` captures non-integration closeout evidence plus deferred integration/runtime gates. |

## Tasks

### Task 1 — Correct News source-chain research and SDD record

- **File(s)**: `docs/references/news-agent-trading-research-2026-06-18.md`, `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut/*`
- **Owner**: parent
- **Depends on**: none
- **Touch set**: `docs/references/news-agent-trading-research-2026-06-18.md`, `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut`
- **Conflict set**: coordinate with docs/sdd/features/active for active SDD edits; coordinate with 2026-07-21-signal-pulse-hard-cut for shared contracts, generated artifacts and shell files.
- **Failing test first**: `tests/architecture/test_projection_worker_idle_cost_contract.py::test_agent_brief_workers_claim_dirty_targets_instead_of_scanning_candidates` — anchors the current worker/dirty-target pattern reviewed by this planning task.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Spec/plan
- **Deterministic constraints**: Research must remain over 10,000 characters, must not propose new cross-domain price/return subsystems for this phase, and must classify current/proposed News data structures as keep, cut, cache, or do-not-add.
- **On-demand context**: `src/parallax/domains/news_intel/ARCHITECTURE.md`, `src/parallax/domains/news_intel/repositories/news_repository.py`, `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`, `src/parallax/domains/news_intel/services/news_page_projection.py`.
- **Kill/defer criteria**: Stop if the plan requires price/return data or public fallback to old item brief rows.
- **Eval/repair signal**: SDD validator failure, residual old object names, revived retired story tables/projection names, or source-review gaps around dedupe/admission/projection.
- **Implementation**: Rewrote the research, spec, plan, tasks, and verification artifacts around a News-only story agent hard cut.
- **Verification**: `uv run pytest tests/architecture/test_projection_worker_idle_cost_contract.py::test_agent_brief_workers_claim_dirty_targets_instead_of_scanning_candidates -q`
- **Review owner**: parent
- **Status**: [x]

### Task 2 — Story packet domain contract

- **File(s)**: `docs/references/news-agent-trading-research-2026-06-18.md`, `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut`
- **Owner**: current implementation branch
- **Depends on**: Task 1
- **Touch set**: `docs/references/news-agent-trading-research-2026-06-18.md`, `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut`
- **Conflict set**: coordinate with docs/sdd/features/active for active SDD edits.
- **Failing test first**: `tests/unit/domains/news_intel/test_news_story_brief_input.py::test_story_packet_hash_stable_for_equivalent_member_order` — asserts stable story packet hashing.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Packet hash excludes run id, timestamps, attempts, leases, worker time, and public projection payloads.
- **On-demand context**: `news_item_brief_input.py`, `news_story_identity.py`, `news_story_similarity.py`, `news_material_delta.py`, and the research document.
- **Kill/defer criteria**: Stop if packet construction needs data outside News-owned facts/control state.
- **Eval/repair signal**: unstable hash tests, oversized packet fixtures, unsupported evidence refs, or source-review defects.
- **Implementation**: Added story brief types and deterministic packet construction from representative/member evidence, entities, facts, token mentions, explicit story identity, story market scope, and story admission context. Packet construction now rejects missing or malformed representative/member source timeline (`published_at_ms`) values, including bool/string/float pseudo-timestamps, missing member rows, malformed member item identity, representative-item context fallback, legacy `market_scope` / `market_scope_primary` aliases, bare list/string `market_scope_json` payloads, legacy story context aliases (`story_identity`, `agent_admission`, `similarity`, `material_delta`), and admission-basis restoration of story packet material/similarity context; the packet hash excludes runtime projection fields.
- **Verification**: `uv run pytest tests/unit/domains/news_intel/test_news_story_brief_input.py -q`
- **Review owner**: parent
- **Status**: [x]

### Task 3 — Story agent storage and repository

- **File(s)**: `docs/references/news-agent-trading-research-2026-06-18.md`, `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut`
- **Owner**: current implementation branch
- **Depends on**: Task 2
- **Touch set**: `docs/references/news-agent-trading-research-2026-06-18.md`, `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut`
- **Conflict set**: coordinate with docs/sdd/features/active for active SDD edits.
- **Failing test first**: `tests/integration/domains/news_intel/test_news_story_agent_repository.py::test_story_current_brief_key_is_stable_story_identity` — asserts stable story current identity.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Current rows are keyed by story identity version plus story key; run id is audit identity only; no separate story membership table is added without measured query evidence.
- **On-demand context**: current `news_item_agent_runs`/`news_item_agent_briefs` repository methods, Alembic item-brief migrations, and read-model review rules.
- **Kill/defer criteria**: Stop if schema design uses run/generation/timestamp/UUID as current serving identity or recreates retired `news_story_groups` / `news_story_members`.
- **Eval/repair signal**: rowcount evidence failure, uniqueness conflict, old item-brief fallback, or migration-review defect.
- **Implementation**: Added the Alembic hard cut for `news_story_agent_runs`, `news_story_agent_briefs`, and `story_brief` dirty targets; added repository run/current writes, story target loading, current lookup, rowcount evidence, explicit JSON/scalar audit payload validation for story agent run/current writes, and required story target context fields for `story_identity_version`, `market_scope_json`, and `agent_admission_json`.
- **Verification**: `uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py -q`; integration repository verification remains deferred by explicit user instruction.
- **Review owner**: parent
- **Status**: [~]

### Task 4 — Story dirty target and worker

- **File(s)**: `docs/references/news-agent-trading-research-2026-06-18.md`, `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut`
- **Owner**: current implementation branch
- **Depends on**: Tasks 2-3
- **Touch set**: `docs/references/news-agent-trading-research-2026-06-18.md`, `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut`
- **Conflict set**: coordinate with docs/sdd/features/active for active SDD edits.
- **Failing test first**: `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_restores_completed_story_run_without_second_model_call` — asserts completed-run restore without model execution.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Reserve capacity before claim, no DB session during model execution, CAS completion with claimed payload hash/lease owner/attempt count, and use `story_brief` rather than retired `story` as the projection name.
- **On-demand context**: `news_item_brief_worker.py`, `news_projection_work.py`, dirty target repository tests, and AgentExecutionGateway contracts.
- **Kill/defer criteria**: Stop if worker needs API-triggered execution, an ad hoc queue outside `news_projection_dirty_targets`, or the retired `story` dirty projection name.
- **Eval/repair signal**: repeated model call, backpressure leak, dirty-target CAS failure, or worker single-writer architecture failure.
- **Implementation**: Added story dirty target support, item-process story enqueueing, `NewsStoryBriefWorker`, provider stage/client support, formal `news.story_brief` agent-runtime lane settings, runtime factory/manifest/wake wiring, and focused worker tests for ready writes, completed-run restore, started failed-run current restore, missing persisted failed-run identity rejection before model execution, no-start backpressure retry without attempt burn, provider-started failed-run ledger writes, and malformed story candidates failing without model execution or silent target completion. Current story brief reuse now requires explicit current identity, run identity, status, input hash, and version fields before skipping; malformed current rows fail the dirty target instead of causing a second model call. Completed/failed latest-run reuse now requires explicit run status, story brief key, input hash, and version fields before the reuse gate can classify the run as matching or stale. Completed-run restore now requires explicit response JSON, response status matching the persisted outcome, and ready payload publishable `summary_zh` before reuse; it rejects market-read-only restored payloads instead of using `market_read_zh` as a publishable-summary fallback. Fresh ready payload validation also requires explicit non-empty `summary_zh`; `market_read_zh` alone no longer satisfies publishable text for story or retained item-brief execution. Fresh story result audit now requires explicit non-negative `latency_ms`, `usage`, and `trace_metadata` instead of defaulting missing audit fields to zero or empty objects; provider-started generic failures attach a measured latency before ledger insert. Story and item worker ledger writes now persist only the explicit `output_hash` argument from validated payload handling and do not restore a missing run output hash from provider/audit payload fields. Completed/failed run restore now requires explicit persisted `outcome` before reuse, explicit positive `finished_at_ms`, completed-run status accounting reads explicit persisted `outcome`, failed-run restore/error reporting requires explicit non-empty `error_class` and `error`, failed-run reuse requires explicit boolean `execution_started` before deciding whether a failed run is restorable, and item processing now enqueues page and story-brief current work only; it no longer auto-enqueues item-brief dirty work, and `news_item_brief` is interval-only rather than woken by `news_item_processed`. Story worker optional object handling also removed the unreachable generic `_dict` empty-object fallback so malformed present objects cannot later be repaired to `{}` by helper reuse. Item/story packet context fields now fail closed when a formal context key is present but malformed rather than collapsing it to `{}`, while absent optional context remains absent. The retained item-brief audit lane also fails closed on malformed loaded candidate item identity, malformed repository admission-context evidence/current state, item packet context restored from admission basis or legacy item aliases, malformed present packet context objects, malformed current-brief status/hash/version identity before skipping, malformed no-start backpressure error contracts, malformed failed latest-run status/outcome/execution-start/hash/version/error identity before restore, missing publishable validation payload, missing completed-run `outcome` / `finished_at_ms`, missing invalid-completed source run `provider` / `model`, missing result `agent_run_audit`, missing result audit `latency_ms` / `usage` / `trace_metadata`, and missing audit identity scalar fields (`provider`, `model`, `backend`, `workflow_name`, `agent_name`, `lane`, `prompt_version`, `schema_version`, `input_hash`) rather than completing malformed candidate targets as missing, repairing malformed admission context from candidate sidecars, restoring packet market scope/similarity/material-delta/admission from admission basis or legacy aliases, injecting admission-basis similarity/material-delta back into worker packet fields, treating malformed current or failed-run rows as stale and calling the model again, writing `{}` for missing publishable validation payloads, repairing completed-run `outcome` to `ready`, using current time as a completed-run finish fallback, defaulting invalid source audit identity or failed-run error details, falling back from result audit to request audit, defaulting audit values to `0` / `{}`, or using provider/config/packet defaults. Repository item-run writes now also require explicit `backend` and non-negative `latency_ms`, and dirty-target completion keys require formal non-empty text identity plus explicit window shape from claimed rows instead of stringifying malformed `projection_name`, `target_kind`, `target_id`, or `window`.
- **Verification**: `uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py -q`
- **Review owner**: parent
- **Status**: [~]

### Task 5 — Projection, API, and UI hard cut

- **File(s)**: `docs/references/news-agent-trading-research-2026-06-18.md`, `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut`
- **Owner**: current implementation branch
- **Depends on**: Tasks 3-4
- **Touch set**: `docs/references/news-agent-trading-research-2026-06-18.md`, `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut`
- **Conflict set**: coordinate with docs/sdd/features/active for active SDD edits.
- **Failing test first**: `tests/integration/domains/news_intel/test_news_page_rows_read_path.py::test_page_rows_read_story_brief_without_item_brief_fallback` — asserts projected story current state is the read path.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Public rows come from projected current story state; no raw-item or old item-brief reconstruction.
- **On-demand context**: `docs/FRONTEND.md` before frontend edits, current News page projection tests, API contract tests, and source architecture doc.
- **Kill/defer criteria**: Stop if UI/API requires runtime fallback to old item brief rows to stay functional.
- **Eval/repair signal**: public fallback detected, malformed projected row silently repaired, frontend lint failure, or route-shell architecture failure.
- **Implementation**: Updated the backend page projection, item-detail load paths, read-only agent context registry, notification public shaping, and admission representative context to consume projected `news_story_agent_briefs` current state without item-brief or item-run fallback. Page projection now requires an explicit story envelope, explicit item `market_scope_json` / `agent_admission_json` context, explicit item content projection fields, explicit story projection member/source/timing/story-identity fields, explicit agent-signal status after the intentional missing-current pending path, and projection payload sections instead of rebuilding story rows from item fallback data, page-row writes require explicit serving identity, display strings, cache/index summary fields, agent status/brief consistency, and admission fields instead of repairing missing representative/story/agent representative/status/reason identity from `news_item_id`, admission payloads, or repository defaults, public agent-brief shaping strips retired/audit fields without downgrading projected story-current payloads through the old item-brief schema gate and now requires projected public status instead of defaulting it to pending, page projection wake-in listens to `news_story_brief_updated` rather than audit-only `news_item_brief_updated`, admission duplicate/same-story representative current-state joins read story-current rows and require explicit story identity version rather than defaulting it, and item-brief current writes no longer enqueue page reprojection. Page projection current-brief compaction now treats malformed present `market_impacts`, `bull_view`, `bear_view`, and `data_gaps` as projection damage instead of silently dropping impacts or repairing optional sections to empty values; it also rejects present malformed story evidence lists (`source_ids`, `provider_article_keys`) and admission basis match objects (`similar_story`, `exact_duplicate`) before emitting page rows. External push readiness now requires an explicit non-empty current `summary_zh`; ready story-current rows with only legacy `market_read_zh` remain in-app eligible but are blocked from external push as `agent_brief_missing_summary`. Public agent-brief shaping now reads only projected top-level public fields and no longer inspects nested `brief_json` to repair missing summary/list fields; present public text, mapping, list, non-negative integer, and affected-entity member fields fail when malformed as projected row damage. News high-signal notification shaping rejects malformed present `agent_brief`, `affected_entities`, and `token_impacts` payload sections instead of publishing sanitized empty sections, requires explicit projected `news_item_id` plus `representative_news_item_id` instead of deriving one identity from the other, requires candidate `alert_eligibility.in_app_eligible` to be explicitly true, and now requires typed public `agent_brief` text fields, typed public affected-entity text/evidence fields, formal `affected_entities[].symbol` only for notification asset identity, public allowlisted top-level affected-entity payloads, typed public token-impact fields, typed display-title source text, typed optional `canonical_url` in payload/body generation, typed optional external-push readiness booleans, ready external-push basis `agent_brief`, and typed present external-push block reasons even on ready push paths, typed API sanitizer fields for stored notification payloads including top-level text/mapping/bool/non-negative count fields, required present `agent_brief.status`, and allowlisted nested story/market-scope/agent-admission member fields without `**payload` passthrough, removes the dead `_NEWS_HIGH_SIGNAL_PAYLOAD_KEYS` copy-list after sanitizer construction became fully field-driven, and removes the unused notification-rule `_optional_news_list` helper so list acceptance is expressed only by active typed helper calls, typed `agent_brief.status`, typed ready-summary text when `summary_zh` is present, and typed pending-path projected `alert_eligibility.decision_class` / signal direction instead of treating malformed values as pending or stringified text. Page search text is derived only from current projected `*_json` fields and no longer restores source/token/fact terms from legacy alias fields when current fields are empty. Page/story target repository loaders now require explicit evidence arrays for projected member `entities`, `token_mentions`, and `fact_candidates` instead of converting malformed member evidence into empty arrays before page projection or story-brief packet construction. Page projection input, item-brief target, agent-admission context, and item-detail repository read paths now reject malformed evidence/candidate arrays instead of converting them to empty arrays through `_json_list`. Page projection worker member expansion now fails malformed `member_items` identities instead of silently dropping bad members and publishing a partial story row, shared projection claim helpers now fail malformed claimed rows instead of filtering them out before worker load, source-quality future target rescheduling requires explicit aggregate `source_id`, `window`, and integer `item_count` instead of silently skipping malformed rows, and ops dirty-target repair plus item/story dirty priority read material delta, status, and market scope from formal admission/current fields rather than sidecar `material_delta_json`, scalar `agent_admission_status`, top-level `market_scope`, or nested market-scope alias keys. No frontend files were changed in this slice.
- **Verification**: `uv run pytest tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_worker_runtime_contracts.py tests/unit/platform/test_agent_read_tools.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_api_news_contract.py -q`
- **Review owner**: parent
- **Status**: [~]

### Task 6 — Cleanup, architecture docs, and final gates

- **File(s)**: `docs/references/news-agent-trading-research-2026-06-18.md`, `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut`
- **Owner**: current implementation branch
- **Depends on**: Tasks 1-5
- **Touch set**: `docs/references/news-agent-trading-research-2026-06-18.md`, `docs/sdd/features/completed/2026-06-18-news-trading-agent-hard-cut`
- **Conflict set**: coordinate with docs/sdd/features/active for active SDD edits.
- **Failing test first**: `tests/architecture/test_news_intel_kiss_simplification.py::test_old_item_outputs_are_audit_only_after_story_agent_hard_cut` — asserts no legacy item-brief fallback remains.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Final integration
- **Deterministic constraints**: Architecture docs must name story current writer ownership, stable story key identity, no compatibility read path, and page-row denormalized fields as cache/index data only.
- **On-demand context**: `docs/ARCHITECTURE.md`, `docs/AGENT_EXECUTION.md`, `src/parallax/domains/news_intel/ARCHITECTURE.md`, and read-model review checklist.
- **Kill/defer criteria**: Stop if cleanup would remove non-agent News page behavior without a replacement contract.
- **Eval/repair signal**: architecture harness failure, stale generated docs, active SDD validation failure, or review defect on old/current compatibility.
- **Implementation**: Updated worker and architecture docs for story-current ownership, stable story keys, no compatibility read path, retired story tables/projection names, and the formal `news.story_brief` lane inventory. Removed the unused runtime row-level item-brief contract helper so the retained item-brief contract module only exposes constants and the SQL predicate still needed by audit/source-quality query lanes. Full integration/runtime gates are deferred by explicit user instruction on 2026-06-18; the non-integration repository gate is complete.
- **Verification**: `make check`
- **Review owner**: parent
- **Status**: [~]
