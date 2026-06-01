# Spec — News Intel KISS Simplification

**Status**: Draft  
**Date**: 2026-06-01  
**Owner**: Qinghuan / Codex  
**Related**:

- `docs/superpowers/specs/active/2026-05-19-news-intel-kappa-cqrs-cn.md`
- `docs/superpowers/specs/active/2026-05-28-news-intel-dedup-root-fix-cn.md`
- `docs/superpowers/specs/active/2026-05-30-news-item-brief-llm-cost-root-fix-cn.md`
- `docs/superpowers/specs/active/2026-05-31-news-brief-opennews-dedup-cost-hard-cut-cn.md`

## Background

News Intel currently owns configured news source ingestion, canonical news item facts, deterministic entity/token/fact extraction, item-scoped agent briefs, the News page read model, and source quality projection. The domain architecture already states that provider entries are inputs, `news_provider_items` plus normalized `news_items` are the persisted fact path, `news_page_rows` is the public rebuildable read model, `NewsItemBriefWorker` is the only runtime writer for item agent runs/current briefs, and `NewsSourceQualityProjectionWorker` is the only writer for source quality rows (`src/parallax/domains/news_intel/ARCHITECTURE.md:15`, `src/parallax/domains/news_intel/ARCHITECTURE.md:20`, `src/parallax/domains/news_intel/ARCHITECTURE.md:40`, `src/parallax/domains/news_intel/ARCHITECTURE.md:43`).

The runtime factory constructs five News workers when enabled: `news_fetch`, `news_item_process`, `news_item_brief`, `news_page_projection`, and `news_source_quality_projection` (`src/parallax/app/runtime/worker_factories/news_intel.py:26`). The factory also passes `source_quality_windows` into upstream fetch/process/brief workers, which couples core item flow to source quality projection policy (`src/parallax/app/runtime/worker_factories/news_intel.py:43`, `src/parallax/app/runtime/worker_factories/news_intel.py:58`, `src/parallax/app/runtime/worker_factories/news_intel.py:72`).

`news_fetch` reconciles configured sources, claims due source rows, fetches provider documents, persists provider items and canonical news items, and enqueues projection dirty targets (`src/parallax/domains/news_intel/runtime/news_fetch_worker.py:42`, `src/parallax/domains/news_intel/runtime/news_fetch_worker.py:93`, `src/parallax/domains/news_intel/runtime/news_fetch_worker.py:194`). It can enqueue `brief_input` directly from provider observations before deterministic item processing has completed (`src/parallax/domains/news_intel/runtime/news_fetch_worker.py:247`).

`news_item_process` is deterministic. It loads unprocessed items, extracts entities, resolves token mentions through a narrow identity interface, builds fact candidates, classifies content, marks the item processed, and enqueues `page`, `brief_input`, and `source_quality` dirty targets (`src/parallax/domains/news_intel/runtime/news_item_process_worker.py:42`, `src/parallax/domains/news_intel/runtime/news_item_process_worker.py:66`, `src/parallax/domains/news_intel/runtime/news_item_process_worker.py:73`, `src/parallax/domains/news_intel/runtime/news_item_process_worker.py:79`, `src/parallax/domains/news_intel/runtime/news_item_process_worker.py:90`, `src/parallax/domains/news_intel/runtime/news_item_process_worker.py:112`).

`news_item_brief` is the only LLM-backed News worker. It checks queue depth, reserves the shared `news.item_brief` lane before claiming dirty targets, loads bounded candidates, skips ineligible or fresh current briefs, executes one typed stage through the provider, validates output, writes the run ledger/current brief, and dirties page/source quality (`src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:52`, `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:62`, `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:66`, `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:92`, `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:141`, `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:147`). The actual LLM adapter builds an `AgentStageSpec` and delegates to the process-wide `AgentExecutionGateway` (`src/parallax/integrations/model_execution/news_item_brief_agent_client.py:22`, `src/parallax/integrations/model_execution/news_item_brief_agent_client.py:55`).

`news_page_projection` claims `projection_name='page'`, loads item facts plus current brief, builds a public page row, and replaces `news_page_rows` (`src/parallax/domains/news_intel/runtime/news_page_projection_worker.py:30`, `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py:38`, `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py:52`, `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py:57`, `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py:82`). API routes are read-only over `NewsPageQuery` and source status diagnostics (`src/parallax/app/surfaces/api/routes_news.py:14`, `src/parallax/app/surfaces/api/routes_news.py:30`, `src/parallax/app/surfaces/api/routes_news.py:59`, `src/parallax/domains/news_intel/queries/news_page_query.py:9`).

The dirty target repository is a single physical queue for three logical intents: `brief_input`, `page`, and `source_quality` (`src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:11`). Workers currently pass those string projection names directly.

## Problem

The current News Intel flow is directionally correct but cognitively too large for the product problem. It exposes internal scheduling strings as business concepts, couples core item processing to source quality window policy, lets provider fetch enqueue agent work before deterministic processing is the single admission point, and gives source quality the feel of a hot-path dependency even though it is an operational read model. This makes the chain hard to reason about and increases the chance that future fixes add another worker, queue state, or agent stage instead of simplifying the existing flow.

## First Principles

1. News Intel answers one product question: what happened, who said it, which assets are affected, and whether it is worth surfacing. The minimum correct flow is provider observation → canonical item fact → deterministic understanding → optional item brief → public read model.
2. PostgreSQL facts remain product truth. Provider payloads, wake hints, dirty rows, leases, agent lane counters, and source quality windows are control or input state, not public truth. Existing docs and code already enforce this by making API routes read only and by projecting `news_page_rows` from stored facts (`src/parallax/domains/news_intel/ARCHITECTURE.md:18`, `src/parallax/domains/news_intel/ARCHITECTURE.md:57`, `src/parallax/app/surfaces/api/routes_news.py:14`).
3. Optional enhancement stages must be isolated. Agent brief and source quality may enrich the product, but neither may be required for the canonical item to exist or for the page projection to expose an honest pending/degraded state.

## Goals

- G1. News core flow is explainable as exactly three required stages: fetch, deterministic item processing, and page projection. Brief and source quality are explicitly optional enhancement/ops stages.
- G2. Agent admission has a single semantic owner after deterministic processing. Provider fetch must not be a second path that creates `brief_input` work from raw provider observations.
- G3. Source quality no longer appears in upstream worker constructors or item-level admission logic. Source quality owns its own windows and cadence.
- G4. Runtime code and docs no longer use raw `projection_name` strings as the reader-facing concept for page, brief, and source quality work. The physical dirty target table may remain, but business language must become typed/semantic.
- G5. The public News row separates provider-native signal, agent brief signal, and display/alert eligibility so that UI/API consumers can see which layer made the judgment.
- G6. No new worker, new table, new LLM lane, or new story/projection layer is introduced for this simplification.
- G7. Provider ingestion freshness and LLM brief eligibility are separate policies. Fetch windows must not depend on agent brief age constants or admission policy.
- G8. Obsolete read-model fields introduced for prior projection lifecycle designs are removed or explicitly justified as serving-contract fields.

## Non-goals

- N1. This spec does not replace Kappa/CQRS, single-writer read models, durable dirty targets, advisory locks, or the shared `AgentExecutionGateway`.
- N2. This spec does not remove canonical URL dedup, provider observation edges, item agent run audit rows, or current item brief rows.
- N3. This spec does not redesign the React News UI.
- N4. This spec does not add story clustering, multi-agent news analysis, cross-source consensus scoring, or a new `news_story_projection`.
- N5. This spec does not change provider credentials, runtime config file locations, or source onboarding waves.

## Target Architecture

News Intel should be described and implemented as a two-layer pipeline:

Required core:

```text
news_fetch
  -> news_items + observation facts
  -> item needs deterministic processing

news_item_process
  -> entities + token mentions + fact candidates + content class
  -> page dirty
  -> optional brief dirty only after deterministic admission

news_page_projection
  -> news_page_rows
  -> API/UI
```

Optional enhancement and ops:

```text
news_item_brief
  -> news_item_agent_runs + news_item_agent_briefs
  -> page dirty

news_source_quality_projection
  -> news_source_quality_rows + compact news_sources.source_quality_status
  -> page dirty only when compact status changes
```

The physical dirty target mechanism can stay consolidated, but runtime code should treat it as a private scheduling implementation. The domain language should be semantic: page reproject intent, item brief intent, and source quality refresh intent.

## Simplification Decisions

### Remove: Fetch-to-Brief Admission

`news_fetch` should persist provider facts and enqueue page processing/projection work only. It should not decide whether an item deserves LLM brief work, because that decision needs deterministic item state: content class, token mentions, fact candidates, canonical representative status, and context availability. This removes one admission path and makes `news_item_process` the single semantic owner for creating item brief work.

Context updates are not an exception. If new context should reconsider an item brief, the flow must enqueue a semantic "processed item needs brief reconsideration" intent owned by the same admission policy, not a fetch-owned `brief_input` shortcut.

### Remove: Fetch Horizon Coupled To Agent Policy

Provider fetch windows decide what input facts the system should observe. Agent brief eligibility decides whether an already observed and processed item deserves a model call. These are different policies. Fetch code should not import, reference, or derive its provider catch-up horizon from item brief age constants.

### Remove: Source Quality Window Coupling From Upstream Workers

Fetch, process, and brief workers should not receive or reason about `source_quality_windows`. Source quality windows belong to `NewsSourceQualityProjectionWorker` settings. Upstream events may mark a source as potentially changed through a semantic source refresh intent, but they should not construct per-window targets. This makes source quality an ops projection rather than part of the item lifecycle.

### Remove: Item-Level Source Quality Fanout As Hot Path

Source quality does not need to recompute synchronously for every item write, process, or brief update. It can be eventual and source/window-scoped. A source quality status change may still dirty page rows because the page row copies compact source status, but ordinary item freshness must not wait for source quality projection.

### Hide: Stringly Typed Dirty Target Names

The physical queue can remain `news_projection_dirty_targets`, but worker and service code should not expose `projection_name='brief_input'`, `projection_name='page'`, or `projection_name='source_quality'` as ordinary domain language. A typed scheduling facade should own those strings, validation, and target construction. Raw projection strings should be limited to the dirty-target repository, the scheduling facade, migrations, queue-health adapters, and tests that explicitly verify the adapter. This is a readability simplification, not a storage rewrite.

### Rename: Agent Stage Builder Is Not Runtime

The module that builds the News item brief agent stage is a stage/prompt adapter, not a runtime owner. It should be named and documented as such. Runtime ownership remains with `NewsItemBriefWorker` and shared execution ownership remains with `AgentExecutionGateway`.

### Simplify: Public Signal Envelope

`news_page_rows` should preserve the distinction between:

- provider-native signal: upstream structured signal such as OpenNews score/coin impact;
- agent brief signal: the validated item brief output;
- display signal: the compact row-level product signal shown in the News surface;
- alert eligibility: deterministic product decision for in-app visibility and external push readiness.

The page projection may compute a display signal, but it must not hide whether the signal came from provider facts or the agent brief.

### Remove: Unused Read-Model Lifecycle Fields

Read-model fields that are no longer written by the current projection path should be removed from serving tables or explicitly documented as part of the public serving contract. In particular, projection lifecycle fields inherited from older generation/watermark designs should not remain as inert schema weight on `news_page_rows` or `news_source_quality_rows`.

### Preserve: Separate Agent Worker

The item brief worker should remain separate from deterministic processing. LLM execution has different cost, timeout, retry, audit, and backpressure semantics. Collapsing brief into `news_item_process` would make the required core flow depend on optional agent health.

### Preserve: Observation Edges

Observation edges are necessary because multiple providers/sources can observe the same canonical item. They are not over-complexity; they are the data structure that lets canonical dedup preserve source provenance.

### Preserve: Current Brief + Run Ledger Split

`news_item_agent_runs` and `news_item_agent_briefs` should remain separate. The append-only run ledger is audit/control evidence; the current brief is the compact read model used by projection.

## Conceptual Data Flow

```text
configured sources
  -> provider fetch
  -> provider observation facts
  -> canonical news item
  -> deterministic item processing
  -> page projection
  -> /news API and UI

deterministic item processing
  -> optional item brief admission
  -> item brief agent
  -> current item brief
  -> page projection

source/fetch/item aggregates
  -> eventual source quality projection
  -> compact source status
  -> page projection only when status changes
```

The changed arrows are:

- provider fetch no longer creates brief work directly;
- source quality refresh is source/window-owned and eventual, not an item hot-path fanout;
- page projection reads provider signal and agent brief as separate inputs.

## Core Models

- `NewsItem`: canonical material news item. It owns identity, title/body/summary, published/fetched timestamps, lifecycle status, content class, provider-native signal, and provider-native token impacts.
- `NewsObservation`: provider/source observation of a canonical item. It owns source provenance, provider item identity, raw payload, provider article key, and dedup evidence.
- `NewsUnderstanding`: deterministic item-derived facts: entities, token mentions, fact candidates, and content classification.
- `NewsItemBrief`: optional current LLM item brief keyed by `news_item_id` and material input identity.
- `NewsBriefRun`: append-only audit of provider-started and terminal brief attempts.
- `NewsPageRow`: public rebuildable read model. It must be reconstructable from canonical item, observation summary, deterministic understanding, provider signal, and current brief.
- `NewsSourceQuality`: eventual source/window quality read model for operations and compact source status, not item truth.

## Interface Contracts

HTTP routes remain read-only:

- `/news` returns projected page rows and pagination.
- `/news/items/{news_item_id}` returns item detail and audit/detail context.
- `/news/facts/{fact_candidate_id}` returns fact candidate detail.
- `/news/sources/status` returns provider capability and source hygiene diagnostics.

The semantic response contract should make pending optional stages explicit:

- item exists even when deterministic processing is pending;
- page row can show agent brief status `pending`, `insufficient`, `ready`, or `failed`;
- source quality can be `unknown` or stale without hiding the item;
- provider signal and agent signal are distinguishable.

No public route may call providers, run item processing, execute the agent, repair data, or mutate dirty targets.

## Acceptance Criteria

- AC1. WHEN `news_fetch` persists or updates a canonical item THEN the system SHALL NOT create item brief work until deterministic item processing has evaluated the processed item.
- AC2. WHEN `news_fetch` handles provider items or context observations THEN it SHALL NOT import, call, or depend on item brief admission policy.
- AC3. WHEN item processing completes THEN item brief admission SHALL be the only normal runtime path that can create item brief work, and the decision SHALL be based on processed item state rather than raw provider score alone.
- AC4. WHEN provider ingestion catch-up windows are configured or computed THEN they SHALL NOT reference agent brief age constants or LLM admission policy.
- AC5. WHEN a processed item is not brief-eligible THEN the system SHALL expose the page row with deterministic/provider state and no agent provider execution.
- AC6. WHEN source quality windows change in worker settings THEN fetch/process/brief construction SHALL NOT need code or constructor changes.
- AC7. WHEN fetch/process/brief complete item-level work THEN they SHALL NOT construct per-window source quality targets; source quality window expansion SHALL be owned by source quality scheduling/runtime policy.
- AC8. WHEN source quality needs refresh THEN the refresh intent SHALL be bounded and durable without broad fact-table scans when the dirty queue is empty.
- AC9. WHEN source quality is delayed or failing THEN `/news` SHALL still serve canonical item rows with an explicit source status of unknown/degraded/stale rather than blocking item visibility.
- AC10. WHEN an item has both provider-native signal and agent brief signal THEN the projected row SHALL expose provider signal, agent/current-brief signal, display signal, and alert eligibility as distinguishable concepts.
- AC11. WHEN a worker enqueues page, brief, or source quality work THEN reviewers SHALL see semantic scheduling language rather than raw dirty-target projection strings outside the scheduling adapter, dirty-target repository, migrations, queue-health adapter, and adapter-focused tests.
- AC12. WHEN the News item brief stage is referenced THEN docs/code SHALL identify it as a stage or prompt adapter, while `NewsItemBriefWorker` and `AgentExecutionGateway` remain the runtime owners.
- AC13. WHEN this simplification is complete THEN the worker inventory SHALL remain the same or smaller; no new News worker, LLM lane, or story projection table SHALL be introduced.
- AC14. WHEN canonical item provenance is inspected THEN provider observations and source edges SHALL still explain which providers/sources saw the item.
- AC15. WHEN existing News read-model columns are not written by current projection code and are not public contract fields THEN they SHALL be removed or explicitly justified before the simplification is considered complete.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Briefs appear later because fetch no longer enqueues brief work directly. | Medium | Item processing already wakes from `news_item_written`; brief remains optional and page rows expose pending state. |
| Source quality becomes less real-time. | Low | Source quality is operational metadata; compact status changes still trigger page reprojection. |
| Hiding dirty-target strings creates a thin wrapper that does not remove real complexity. | Medium | The wrapper must replace call-site concepts, not merely rename functions. Acceptance is based on raw projection strings disappearing from domain worker code. |
| Public signal contract changes surprise frontend consumers. | Medium | Preserve existing display fields while adding explicit provider/agent source fields until frontend migration is verified. |
| Over-correction collapses agent work into deterministic processing. | High | Non-goals and acceptance criteria preserve a separate LLM worker and shared execution gateway. |
| Removing fetch-owned brief admission loses context-triggered re-briefs. | Medium | Route context changes through the same processed-item brief reconsideration policy. |
| Fetch horizon narrowing drops provider facts. | High | Keep ingestion freshness independent from LLM eligibility; brief policy may reject old items after facts are persisted. |

## Evolution Path

After this simplification, future News improvements should follow the same ladder:

1. Improve canonical item identity and observation edges before adding story objects.
2. Improve deterministic item understanding before adding more agent stages.
3. Improve page projection semantics before adding new API fallbacks.
4. Promote source quality to product ranking only after measured evidence shows it improves operator outcomes.

If the product later needs event-level clustering across sources, it should be introduced as a separate approved spec with evidence that canonical URL/item identity is insufficient.

## Alternatives Considered

- Merge all News work into one worker — rejected because provider IO, deterministic processing, LLM execution, and read model projection have different failure modes, budgets, and retry semantics.
- Split `news_projection_dirty_targets` into three physical tables immediately — rejected for this spec because the current table can remain a private scheduling implementation; semantic wrappers deliver most of the KISS benefit with less migration risk.
- Remove `news_source_quality_projection` entirely — rejected because source health and hygiene are useful operational diagnostics. The simplification is to demote it from hot-path thinking, not to delete the diagnostics.
- Remove `news_item_brief` entirely — rejected because item-level brief is useful for external push readiness and trader-facing interpretation. The simplification is stricter admission and one typed stage, not no agent.
- Add a new `news_story_projection` to make item flow clearer — rejected because it adds a new product identity and worker before proving canonical item plus observation edges are insufficient.
- Keep fetch-time high-score brief admission as a fast path — rejected because it creates a second semantic owner for model work and makes raw provider score compete with processed item understanding.
