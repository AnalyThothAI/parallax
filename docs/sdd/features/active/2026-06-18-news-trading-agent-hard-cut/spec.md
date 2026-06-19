# Spec — News Story Agent Hard Cut

**Status**: In Progress
**Date**: 2026-06-18
**Owner**: Codex
**Approved by**: delegated goal
**Approved at**: 2026-06-18
**Related**: `docs/references/news-agent-trading-research-2026-06-18.md`

## Background

News Intel owns configured news ingestion, provider observations, canonical news items, deterministic entity/fact extraction, item-scoped agent briefs, and the story-shaped News page read model (`src/parallax/domains/news_intel/ARCHITECTURE.md:1`). Canonical identity already distinguishes hard public article URL, provider-global article id, qualified content hash, and weak title/source/hour identity (`src/parallax/domains/news_intel/types/news_canonical_identity.py:44`). The page projection already builds one row from story identity or item identity and includes story, source, admission, and compact agent state (`src/parallax/domains/news_intel/services/news_page_projection.py:20`). The current agent worker already performs admission checks, input-hash reuse, completed-run restore, failed-run reuse, validation, run-ledger writes, and current-brief upserts (`src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:108`).

The architecture review concludes that the product-facing mismatch is inside News Intel: page rows are story-shaped, but current agent output is item-scoped (`docs/references/news-agent-trading-research-2026-06-18.md:180`). This feature keeps the scope News-only and hard-cuts public/runtime current state to a story-level agent brief.

## Problem

The existing chain can correctly store multiple observations, dedupe canonical items, group related items into stories, skip exact duplicates, and avoid repeated model calls for identical item packets. However, because current agent state lives in `news_item_agent_briefs`, a same-story sequence can still leave multiple item-scoped agent outputs. After remap cleanup, old item outputs may remain valid audit records, but they must not be exposed as current story intelligence.

The system needs a story-scoped current read model and worker contract before any broader product automation. The plan must not add cross-domain price, stock, crypto, return-window, or eval objects in this phase.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| Should this phase introduce cross-domain price or return-window data? | No. This phase is News-only and fixes story current-state semantics first. | delegated goal | 2026-06-18 |
| Should canonical item identity be loosened to collapse similar headlines? | No. Keep strict item identity and move model current state to story scope. | delegated goal | 2026-06-18 |
| Should old item agent outputs remain public fallback state? | No. They may remain audit-only during migration, but public/runtime reads must not use them as current story state. | delegated goal | 2026-06-18 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| Source-chain review is code-grounded. | Research doc names provider item, canonical identity, observation edge, material duplicate, story identity, admission, worker reuse, dirty target, and projection layers. |
| Same-type news semantics are explicit. | Spec and plan distinguish desired deterministic per-item processing from undesired repeated story model current output. |
| Story current state has stable identity. | Planned current row key uses story identity version plus story key, never run id or timestamp. |
| Hard cut avoids compatibility shims. | API/UI and page projection must not read old item briefs as fallback after story current state is enabled. |
| News-only boundary is preserved. | Planned implementation uses News facts/control state only and does not add cross-domain price or return-window reads. |
| Redundant structures are explicitly classified. | Research and plan classify current/proposed tables, JSON fields, and dirty targets as keep, cut, cache, or do-not-add. |

## First principles

- Provider observations are evidence; canonical `news_items` remain the strict item-level fact boundary.
- Story identity groups related items for serving and model budgeting; it must not mutate canonical item truth.
- Deterministic item processing may repeat for distinct canonical items because new facts, entities, sources, or authority can matter.
- Product-facing model output should be current per story/material input, not current per individual item.
- Raw facts and audit ledgers can persist old state, but public surfaces should read current projected read models only.

## Goals

- G1. Define a News-only story agent architecture that uses existing News facts, observation edges, story identity, source evidence, facts/entities, source quality, and admission context.
- G2. Replace product-facing item brief current state with `news_story_agent_runs` and `news_story_agent_briefs`.
- G3. Make same-type news behavior explicit: deterministic processing may repeat per canonical item; model current output is one current story brief per material story version.
- G4. Keep public API/UI reads projected and current-state only, with no fallback to old item brief rows or raw `news_items`.
- G5. Reuse existing AgentExecutionGateway, run-ledger, validation, dirty-target, and worker backpressure patterns.
- G6. Preserve auditability for old item outputs without exposing them as current story intelligence.
- G7. Classify current and proposed News data structures so implementation avoids retired story tables, duplicate membership state, and ambiguous projection caches.

## Non-goals

- N1. Do not add cross-domain price, stock, crypto, return-window, eval, or backtest tables.
- N2. Do not build automated order execution, trading advice, position sizing, leverage, stop-loss, take-profit, or portfolio guidance.
- N3. Do not loosen canonical item identity to collapse all similar headlines into one item.
- N4. Do not keep runtime compatibility code that reconstructs story current state from old item-brief schemas.
- N5. Do not trigger provider fetches, source reads, or model execution from API/UI request paths.
- N6. Do not recreate retired `news_story_groups`, `news_story_members`, or dirty-target `projection_name = 'story'`.

## Target architecture

```text
news_fetch
  -> news_provider_items
  -> news_items + news_item_observation_edges
  -> news_item_process
     -> entities, token mentions, facts, content/scope metadata, story identity, admission
  -> news_story_brief
     -> story packet, story run ledger, current story brief
  -> news_page_projection
     -> story rows that consume current story brief state
  -> API/UI
     -> read projected rows only
```

Existing `market_scope_json` may remain as deterministic scope metadata because it already exists in the News item contract. It must not imply new cross-domain data reads.

## Core models

- `NewsStoryPacket`: deterministic host-built packet keyed by `story_identity_version` and `story_key`, with bounded representative/member evidence, source timeline, observation-edge summaries, entities, fact lanes, source quality, admission basis, and evidence refs.
- `news_story_agent_runs`: append-only audit ledger for story agent attempts.
- `news_story_agent_briefs`: current story read model keyed by stable `story_brief_key = sha256("news-story-brief|<story_identity_version>|<story_key>")`.
- Story dirty target: semantic queue work for story brief current state, coalesced by stable story identity and positive source watermark. Use a new `story_brief` projection name; the old `story` projection name remains retired.

## Interface contracts

- Worker: `NewsStoryBriefWorker` is the only runtime writer for story agent runs/current rows.
- Repository: story packet loading, run insert, current upsert, current lookup, and page projection payloads must validate returned rowcount evidence.
- Page projection: story row signal reads current story brief state after the hard cut.
- API/UI: list/detail routes read projected rows and never call providers, source fetches, or product LLMs inline.

## Acceptance criteria

- AC1. WHEN two provider observations resolve to the same canonical item THEN the system SHALL update deterministic item state once for the canonical item and enqueue story brief work at most once for the story key and source watermark.
- AC2. WHEN a new canonical item belongs to an existing story and has no material delta THEN the system SHALL update story/page evidence without calling the model.
- AC3. WHEN a story member adds material source, entity, fact, or content delta THEN the system SHALL produce at most one refreshed current story brief for the stable story identity.
- AC4. WHEN a matching current story brief or completed story run exists for the packet hash and version tuple THEN the system SHALL skip a second model call.
- AC5. WHEN page rows are served THEN story signal fields SHALL come from the current story brief read model or an explicit pending/failed state, never from old item brief fallback reconstruction.
- AC6. WHEN old item outputs exist after canonical remap THEN the system SHALL keep them audit-only and SHALL NOT expose them as current story intelligence.
- AC7. WHEN story-agent storage, dirty targets, or projection changes are implemented THEN the system SHALL NOT recreate retired story membership tables or the retired `story` dirty projection, and SHALL document remaining page-row denormalization as cache/index data only.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Story identity groups unrelated items. | High | Keep canonical item identity strict and add focused story identity tests for templates, title buckets, and weak fallbacks. |
| Story packet grows too large. | Medium | Cap member snippets, entities, and fact lanes; sort deterministically; expose truncation metadata. |
| Hard cut breaks UI fields. | Medium | Update projection and API contract together; fail visibly or show explicit pending state instead of fallback reconstruction. |
| Model cost rises during migration. | Medium | Reuse current/completed/failed story hash gates before model execution. |
| Old item outputs confuse operators. | High | Remove public reads of item current briefs after story current is enabled. |
| Redundant story structures return under new names. | High | Keep the data-structure audit in the plan and add architecture tests for retired tables/projection names. |

## Alternatives considered

- Extend item briefs in place: rejected because item-scoped current state is the mismatch.
- Collapse all similar stories into canonical items: rejected because it would damage source/fact auditability.
- Add cross-domain price/return objects now: rejected because News current-state semantics are not production-grade yet.
- UI-only grouping over existing rows: rejected because UI cannot enforce single writer, current-state keys, or model-run reuse.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Keep this phase News-only, story-scoped, stable-keyed, and projected-read-model driven. |
| Ask first | Add cross-domain price/return inputs, public schema rename, or migration of historical item runs into publishable story runs. |
| Never | Expose old item brief rows as current story intelligence or execute model/provider work from API/UI. |
