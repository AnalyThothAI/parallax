# Plan — DeepAgents Macro Research Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Date**: 2026-07-24
**Owning spec**: `docs/sdd/features/completed/2026-07-24-deepagents-macro-research-hard-cut/spec.md`
**Worktree**: `.worktrees/deepagents-macro-hard-cut/`
**Branch**: `codex/deepagents-macro-hard-cut`
**Approved by**: user
**Approved at**: 2026-07-24

## Analyze Gate

| Check | Result |
|-------|--------|
| Material fact owner | Pass: `macro_observations` plus sync windows/runs remain the sole evidence and attempt truth. |
| Current derived owners | Pass: `MacroViewProjectionWorker` owns compact series and six `macro_decision_v2` documents; `DailyMacroJudgmentWorker` owns frozen-pack SPY judgments/outcomes. Both retire. |
| Model topology | Pass: installed `deepagents==0.6.12` is the current stable release, but custom middleware forces read/submit/task order and excludes native planning/filesystem capability. |
| Public consumers | Pass: six backend page reads, a series read, a Daily read, six React routes, and deterministic rendering all depend on retired schemas. |
| Dormant platform | Pass: a generic execution gateway/schema/usage/capability stack remains importable but has no production owner; Macro bypasses it. |
| Target seam | Pass: one `CompletedSessionMacro.run/read` deep module gives callers a small interface while hiding session selection, agent, tool, subagent, and persistence complexity. |
| Data migration | Pass: new session-keyed run/publication tables replace all Macro derived judgment/projection tables; facts and sync ledgers remain. |
| Verification boundary | Pass: code topology, PostgreSQL behavior, real provider publication, and blind semantic quality are separate evidence lanes. |

## Design alternatives

### A — Worker-owned orchestration

The worker claims a run, opens evidence repositories, constructs tools and
subagents, invokes DeepAgents, validates citations, and publishes. This is
initially direct but exposes too many decisions to a scheduling adapter and
makes every future caller duplicate orchestration.

### B — Generic research-program runtime

`ResearchRuntime.conduct(program, request)` loads versioned programs and tool
registries. This is flexible but creates a Parallax workflow DSL and generic
agent platform before there is a second concrete product.

### C — Completed-session deep module (selected)

`CompletedSessionMacro.run(session_date=None)` hides completed-session catch-up,
frozen scope, tools, DeepAgents graph, specialist definitions, mechanical
validation, and publication assembly; `read(session_date=None)` returns only
persisted state. The worker calls zero-argument `run()`. Explicit dates exist
only for backfill. This has the deepest useful interface, maximum locality, and
no speculative platform.

## Current seams and target ownership

- Keep `MacroSyncWorker`, `MacroSyncService`, provider runner, concept/source
  identity, and fact repository writes.
- Replace deterministic snapshot/series/evidence-pack/Daily services with
  agent-facing frozen evidence query/read tools.
- Replace the two derived workers with one `macro_research` worker.
- Replace the generic and Daily-specific model adapters with one
  Macro-owned DeepAgents runtime.
- Replace all derived Macro tables with `macro_research_runs` and immutable
  `macro_research_publications`.
- Replace six page APIs plus series/Daily APIs with one persisted research read.
- Replace six React pages with one Macro research document route.

## DeepAgents composition

- Parent agent: owns plan, research strategy, section structure, final Chinese
  artifact, and whether more evidence is needed.
- Native middleware/backend: todo planning, checkpoint virtual filesystem,
  shared `/workspace/`, real `execute`, context management, structured output,
  and dynamic `task`.
- Declarative specialists: evidence analyst, cross-asset challenger, and
  skeptical editor. They receive scoped read tools and return context to the
  parent; Parallax does not force an invocation sequence.
- Evidence tools: catalog, search observations, read observation details,
  search eligible News, read prior Macro publications.
- Large-result contract: compact search hits expose `next_offset` without a
  total paging cap; exact reads
  retain full evidence and use native DeepAgents `/large_tool_results/` VFS
  offload plus `read_file`, without an application-owned truncation gate.
- Scope: every tool call is bound to one completed-session cutoff and run seal
  time; ingestion timestamps never make later evidence available retroactively.
- Output: one typed artifact; only identity and reference integrity are checked
  mechanically.

## Storage and migration

- Add Alembic revision `20260724_0194`.
- Drop triggers/functions and tables owned by old projection and judgment
  lanes: dirty targets, compact series/state, six-page snapshots, judgment jobs,
  publications, and outcomes.
- Create `macro_research_runs` keyed by `session_date`, with cutoff, lifecycle,
  lease/retry, seal, and safe error/audit fields.
- Create `macro_research_publications` keyed by `session_date`, with artifact
  JSON, Markdown, citation/audit hashes, model/prompt/workflow versions, and
  immutable triggers.
- Remove fact-write dirty-target enqueue behavior because no projection queue
  remains.
- Regenerate the PostgreSQL schema from the new Alembic head.

## API and frontend

- Add one `MacroResearchData` API schema and `/api/macro/research`.
- Remove page, series, and Daily Macro response schemas and routes.
- Keep only the `/macro` frontend index route.
- Build one feature-owned research query, model types, page, and colocated CSS.
- Present the agent’s Markdown safely using existing frontend primitives or a
  minimal feature-owned renderer; show gaps and citation details explicitly.
- Regenerate OpenAPI and TypeScript together.

## Test strategy

- Unit: artifact envelope/reference closure, frozen evidence tools, DeepAgents
  topology, runtime result handling, worker transaction boundary.
- Integration: non-empty migration hard cut, run claim/retry/publication,
  immutable/replay behavior, persisted-only API.
- Architecture: only the Macro deep module imports model runtime; retired names,
  modules, tables, routes, and direct LiteLLM dependency are absent.
- Frontend: single route states, artifact rendering, gaps/citations, responsive
  behavior, and retired child routes.
- Runtime: redacted configured provider run for one completed session and one
  independent blind semantic review.

## Implementation sequence

1. Establish active SDD and external hard-cut contracts.
2. Add the new artifact, evidence scope/tools, repository, and migration.
3. Implement the DeepAgents runtime and bounded worker/factory/settings.
4. Add the persisted-only API and one Macro research page.
5. Delete all replaced deterministic, Daily, and dormant LLM paths.
6. Regenerate contracts/schema and align canonical docs/config examples.
7. Run focused/full selected gates, non-empty migration, real provider,
   independent semantic review, browser inspection, residual audit, and SDD
   verification.

## Rollout and recovery

This is an owner-approved irreversible hard cut with no compatibility mode,
backup prerequisite, or downgrade path. Deployment order is migration,
application image, enabled worker configuration, explicit first run, and
API/browser inspection. Operational recovery is forward-fix only: material
facts remain authoritative, the new research/checkpoint state is repairable,
and retired derived tables are not reconstructed.

## Acceptance test commands

- AC1: `uv run pytest tests/integration/test_deepagents_macro_research_migration.py -q`
- AC2: `uv run pytest tests/unit/domains/macro_intel/test_completed_session_macro.py tests/unit/domains/macro_intel/test_macro_research_worker.py -q`
- AC3: `uv run pytest tests/unit/integrations/model_execution/test_macro_research_deepagent.py -q`
- AC4: `uv run pytest tests/unit/domains/macro_intel/test_macro_research_repository.py -q`
- AC5: `uv run pytest tests/unit/domains/macro_intel/test_macro_research.py -q`
- AC6: `uv run pytest tests/integration/test_macro_research_publication.py -q`
- AC7: `uv run pytest tests/unit/test_api_macro_contract.py -q`
- AC8: `cd web && npm test -- --run tests/routes/macro.route.test.tsx`
- AC9: `uv run pytest tests/architecture/test_kiss_runtime_invariants.py -q`
- AC10: `uv run pytest tests/architecture/test_product_ai_hard_delete.py -q`
- AC11: `uv run python scripts/check_macro_research_publication.py --session-date 2026-07-23`
- AC12: `uv run python scripts/check_sdd_gate.py --feature 2026-07-24-deepagents-macro-research-hard-cut --gate verify`

## Verification commands

```text
uv run pytest tests/unit/domains/macro_intel tests/unit/integrations/model_execution tests/architecture/test_product_ai_hard_delete.py tests/architecture/test_kiss_runtime_invariants.py -q
uv run pytest tests/integration/test_deepagents_macro_research_migration.py tests/integration/test_macro_research_publication.py -q
make regen-contract
uv run pytest tests/unit/test_api_macro_contract.py tests/contract/test_openapi_drift.py -q
cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/architecture/macroResearchHardCut.test.ts
cd web && npm run typecheck && npm run lint && npm run format:check && npm run build
uv run python scripts/validate_sdd_artifacts.py
uv run python scripts/regen_sdd_work_index.py --check
uv run python scripts/check_sdd_gate.py --feature 2026-07-24-deepagents-macro-research-hard-cut --gate verify
git diff --check
```
