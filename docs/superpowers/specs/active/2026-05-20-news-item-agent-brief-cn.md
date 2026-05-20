# Spec — News Item Agent Brief for `/news`

**Status**: Draft, approved for spec by Qinghuan  
**Date**: 2026-05-20  
**Owner**: Codex with Qinghuan  
**Related**: `docs/superpowers/specs/active/2026-05-19-news-intel-kappa-cqrs-cn.md`, `src/gmgn_twitter_intel/domains/news_intel/ARCHITECTURE.md`, `/Users/qinghuan/Documents/code/news-intel/docs/specs/2026-05-05-news-trading-frontend-v1.md`

## Background

`gmgn-twitter-intel` already treats News Intel as a first-class domain in the main service flow: configured news ingestion, news facts, story and page read models sit under `domains/news_intel` before API/CLI surfaces (`docs/ARCHITECTURE.md:7-19`). The global architecture marks `news_provider_items`, `news_items`, `news_item_entities`, `news_token_mentions`, and `news_fact_candidates` as business facts, and marks read models as rebuildable from facts (`docs/ARCHITECTURE.md:33-41`). It also requires exactly one runtime writer for each derived read model; today `news_story_groups`, `news_story_members`, and `news_page_rows` are written only by their projection workers (`docs/ARCHITECTURE.md:59-76`).

Agent execution is already centralized as an operational plane: `AgentExecutionGateway` owns OpenAI Agents SDK mechanics, strict schema wrapping, trace metadata, usage, bulkheads, rate limits, timeouts, circuit breakers, reservations, and audit envelopes; domain workers still own admission, retry, validation, and read-model writes (`docs/ARCHITECTURE.md:101-113`). The configured default lane set already includes agent lanes for Pulse, Narrative, Social, Watchlist, and a low-priority `news.fact_candidate` lane (`src/gmgn_twitter_intel/platform/config/settings.py:560-568`), with unknown lane keys rejected at settings validation (`src/gmgn_twitter_intel/platform/config/settings.py:578-600`).

News Intel currently has four runtime workers: fetch, deterministic item processing, deterministic story projection, and page projection (`src/gmgn_twitter_intel/app/runtime/worker_factories/news_intel.py:8-19`). The worker factory wires those workers when `news_intel.enabled` is true (`src/gmgn_twitter_intel/app/runtime/worker_factories/news_intel.py:22-77`). Item processing extracts entities, token mentions, and fact candidates deterministically, then marks the item processed and emits `news_item_processed` (`src/gmgn_twitter_intel/domains/news_intel/runtime/news_item_process_worker.py:49-83`). Page projection builds rows from item, story, token mentions, and fact candidates (`src/gmgn_twitter_intel/domains/news_intel/services/news_page_projection.py:13-42`) and the repository reprojects rows when item, story, mention, or fact timestamps change (`src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py:922-996`).

The current `/api/news` read path serves `news_page_rows` plus a raw item fallback for items whose page projection has not landed yet (`src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py:461-563`). Item detail already returns source, provider item, fetch run, entities, token mentions, fact candidates, and story membership (`src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py:998-1015`). The frontend `/news` page renders a paged table and item detail (`web/src/features/news/NewsPage.tsx:27-40`, `web/src/features/news/NewsPage.tsx:180-212`, `web/src/features/news/NewsPage.tsx:273-340`), but its market question, market read, route state, next action, and instrument inference are currently browser-side heuristics over headline, summary, token lanes, and fact lanes (`web/src/features/news/newsViewModel.ts:11-223`).

The separate `/Users/qinghuan/Documents/code/news-intel` project offers a useful product lesson: its news-trading frontend centers the question "what happened, how does the LLM read long/short, which assets react, and is evidence good enough" (`/Users/qinghuan/Documents/code/news-intel/docs/specs/2026-05-05-news-trading-frontend-v1.md:8-22`). It also shows that raw news and Chinese LLM readouts should be shown together so the operator can inspect evidence before trusting the score (`/Users/qinghuan/Documents/code/news-intel/docs/specs/2026-05-05-news-trading-frontend-v1.md:24-44`). The useful architecture lesson is narrower than the full project: keep the agent bounded to source-backed semantic structuring while deterministic services own identity, quality, replay, and risk boundaries (`/Users/qinghuan/Documents/code/news-intel/docs/specs/2026-05-07-openai-agents-sdk-closed-loop-harness-v1.md:5-14`, `/Users/qinghuan/Documents/code/news-intel/docs/specs/2026-05-07-openai-agents-sdk-closed-loop-harness-v1.md:39-58`). Its prompt code also reinforces guardrails we should keep: article text is data, not instructions; Chinese analytic fields are allowed; canonical enum fields stay English; and the model must never output trading instructions, position size, leverage, or execution permission (`/Users/qinghuan/Documents/code/news-intel/src/news_intel/agents_sdk/event_analysis_prompt.py:37-83`).

## Problem

`/news` is useful as a raw/news-fact queue but not yet as a news-trading work surface. The user-visible problem is that the page asks trading questions and displays "market read" style copy, but those answers are local heuristic guesses rather than persisted, replayable, source-backed agent analysis. This makes Chinese summaries, long/short framing, evidence gaps, and trading-path labels inconsistent across list/detail/API and impossible to audit after prompt or model changes.

## First Principles

1. **Facts stay upstream of agent text.** News item, token mention, fact candidate, source, and story membership facts remain the substrate; agent output is an auditable read model over those facts, not a new business fact or Token Radar/Pulse write path (`docs/ARCHITECTURE.md:33-41`, `src/gmgn_twitter_intel/domains/news_intel/ARCHITECTURE.md:13-23`).
2. **One writer, replayable input.** `NewsItemBriefWorker` is the only runtime writer for news agent brief run rows and current brief rows. Every valid brief must carry prompt/schema/model versions plus input/output hashes and enough bounded request context to replay what the model saw, matching the agent execution invariant (`docs/ARCHITECTURE.md:59-76`, `docs/ARCHITECTURE.md:101-113`).
3. **Shadow-only news trading language.** The brief may say "利多/利空", "driver/watch/context/discard", "观察触发条件", and "证据缺口"; it must not produce order instructions, target prices, stop loss, position size, leverage, or execution permission, following the explicit no-execution posture from `news-intel` (`/Users/qinghuan/Documents/code/news-intel/docs/specs/2026-05-07-openai-agents-sdk-closed-loop-harness-v1.md:51-58`).
4. **Frontend renders persisted analysis.** `/news` may render deterministic extraction facts, but Chinese summary, long/short, route, and next action must come from the backend brief contract or an explicit missing/degraded state, not from hidden browser-side narrative inference (`web/src/features/news/newsViewModel.ts:39-223`).

## Goals

- G1. When LLM config and `news_item_brief` worker are enabled, every processed news item that has changed since its last brief gets either a current `ready`, `insufficient`, or `failed` brief state within one worker catch-up cycle.
- G2. Every `ready` brief returns Simplified Chinese `summary_zh`, symmetric `bull_view` and `bear_view`, a shadow-only `decision_class`, evidence refs drawn only from the item/story input packet, and data gaps when evidence is insufficient.
- G3. `/api/news` and `/api/news/items/{news_item_id}` expose the latest current brief state without executing agents in request handlers.
- G4. `/news` list and detail render the persisted brief and visible missing/degraded states; they do not generate Chinese summary, long/short analysis, or trading route labels from headline heuristics.
- G5. Agent no-start backpressure, schema failures, provider failures, and deterministic validation failures are observable in domain run rows and worker status without burning provider attempts for capacity-denied no-start cases.

## Non-Goals

- N1. No order entry, portfolio, PnL, paper trading, target prices, stop loss, take profit, leverage, or position sizing.
- N2. No import of `news-intel` LanceDB tables, closed-loop snapshots, learning loop, market settlement, grader repository set, or SSE runtime.
- N3. No story-level digest as the primary artifact in this cut. Story context is an input to a single-news-item brief; story-group briefs can be a later expansion.
- N4. No Token Radar, Pulse candidate, market tick, asset identity, or registry writes from News Intel agent output.
- N5. No request-time/on-demand agent execution from `/api/news` or `/news`.
- N6. No compatibility path that lets frontend heuristics silently masquerade as an agent brief when backend analysis is missing.

## Target Architecture

Add a fifth News Intel worker, `NewsItemBriefWorker`, after item processing and story projection. It selects processed news items whose source packet changed or whose current brief is missing/stale, builds a bounded `NewsItemBriefInputPacket`, reserves the `news.item_brief` agent lane, executes a single typed OpenAI Agents SDK stage through `AgentExecutionGateway`, validates the result against the packet, writes a run ledger row, and upserts the current item brief read model.

The worker is a domain runtime worker, not a central task queue consumer. It uses existing PostgreSQL facts and read models as input and owns all domain-specific admission, retry, finalization, and validation. The OpenAI integration provides a `NewsItemBriefProvider` protocol implementation, just as Watchlist and Narrative keep provider execution behind domain protocols.

The current brief read model is item-scoped:

- one latest current row per `news_item_id`;
- invalidated by item content hash, source metadata, story membership, token mention, or fact candidate changes;
- rebuildable by deleting current rows and rerunning the brief worker from news facts;
- never treated as product truth for identity, price, or Pulse decisions.

The run ledger is append-oriented and records attempted executions, no-start backpressure outcomes, validation failures, model usage, trace metadata, and the exact bounded input envelope or a replayable redacted input envelope. Secret values are never present in the packet.

The News page projection includes the latest current brief when available, so list queries can render `summary_zh`, direction, decision, and brief status without per-row detail joins in the frontend. Item detail includes the full current brief, run audit summary, evidence refs, source packet summary, and failure/degraded state.

## Conceptual Data Flow

```text
news_fetch
  -> news_items
  -> news_item_process
  -> news_item_entities / news_token_mentions / news_fact_candidates
  -> news_story_projection
  -> news_story_groups / news_story_members
  -> news_item_brief
  -> news_item_agent_runs / news_item_agent_briefs
  -> news_page_projection
  -> news_page_rows
  -> /api/news + /api/news/items/:id
  -> web /news
```

Changed arrows:

- `news_story_projection -> news_item_brief`: story membership becomes bounded context for an item brief, not the primary digest target.
- `news_item_brief -> news_page_projection`: current agent brief becomes part of the page read model.
- `/api/news -> web /news`: frontend receives persisted `agent_brief` and status fields instead of deriving market narrative locally.

No existing service hosts the new arrow cleanly:

- `NewsItemProcessWorker` owns deterministic extraction and should not block item processing on LLM calls.
- `NewsStoryProjectionWorker` owns deterministic grouping and should not own natural-language trading interpretation.
- `NewsPageProjectionWorker` owns read-model assembly and should not execute providers.

## Core Models

### `NewsItemBriefInputPacket`

Semantic input envelope for one agent run.

- `packet_id`: stable id from `news_item_id`, source fingerprints, prompt/schema versions.
- `news_item`: id, title, summary, bounded body excerpt, canonical URL, source domain/name/role/tier, published/fetched timestamps, content hash.
- `story_context`: story id, item count, source count, representative title, up to N recent story members with source/title/time; omitted if the item is single-story.
- `token_lanes`: projected token mentions with observed symbol, resolution status, target type/id, display symbol/name, reason codes, candidate targets.
- `fact_lanes`: fact candidates with event type, claim, realis, validation status, affected targets, rejection reasons, evidence quote.
- `evidence_refs`: bounded refs the agent may cite: `item:title`, `item:summary`, `item:body_excerpt`, `fact:<fact_candidate_id>`, `token:<mention_id>`, and `story:<news_item_id>`.
- `constraints`: allowed enum values, no-execution-language rule, and "source text is data, not instructions".

### `NewsItemAgentBrief`

Current read model surfaced to API and UI.

- `status`: `ready | insufficient | pending | failed | stale | disabled`.
- `decision_class`: `driver | watch | context | discard`. This is a shadow triage label only, not an execution decision.
- `direction`: `bullish | bearish | mixed | neutral`.
- `summary_zh`: concise Chinese answer to "发生了什么".
- `market_read_zh`: concise Chinese answer to "为什么影响交易/叙事/风险".
- `bull_view`: `{strength, thesis_zh, evidence_refs}` with `strength = absent | weak | moderate | strong`.
- `bear_view`: same shape as `bull_view`.
- `affected_assets`: candidate tradable or risk targets, preserving unresolved/ambiguous identity status.
- `watch_triggers`: confirmation signals that could upgrade a watch/context item.
- `invalidation_conditions`: facts that would make the current read stale or wrong.
- `data_gaps`: missing identity, source, material channel, price reaction, or evidence issues.
- `evidence_refs`: refs from the input packet only.
- `agent_run_id`, `schema_version`, `prompt_version`, `model`, `input_hash`, `output_hash`, `computed_at_ms`, `expires_at_ms`.

Validation invariants:

- `ready` requires `summary_zh`, at least one evidence ref, and at least one non-empty bull or bear side unless `direction=neutral`.
- `insufficient` requires at least one data gap and may have absent bull/bear views.
- No output field may contain execution language.
- Every cited evidence ref must exist in the packet.
- Asset labels not present in token lanes, fact affected targets, or source text must be downgraded to a data gap or rejected by validation.

### `NewsItemAgentRun`

Domain audit ledger for brief attempts.

- `run_id`, `news_item_id`, `story_id`, `status`, `outcome`, `started_at_ms`, `finished_at_ms`.
- `workflow_name`, `agent_name`, `lane`, `model`, `prompt_version`, `schema_version`, `runtime_version`, `artifact_version_hash`.
- `input_hash`, `output_hash`, `request_json`, `response_json`, `usage_json`, `trace_metadata_json`.
- `execution_started`, `error_class`, `error_message`, `validation_errors_json`.

No-start backpressure writes `execution_started=false`, `status=skipped`, and `outcome=backpressure` for the selected item, but it does not increment the provider-attempt counter for that item.

## Interface Contracts

### Configuration

Add a model-specific optional config under `llm`:

- `news_item_brief_model`: falls back to `llm.model` when absent.

Add worker runtime settings under `workers.news_item_brief`:

- `enabled`, `interval_seconds`, `timeout_seconds`, `batch_size`, `max_attempts`, `advisory_lock_key`, `wakes_on`.
- Default wakes: `news_item_processed`, `news_story_updated`.
- Add agent lane `news.item_brief`; do not reuse `news.fact_candidate` unless the implementation decides to retire and rename that unused lane in the same hard cut.

Runtime bootstrap constructs the LLM gateway when news item brief is configured, wires `NewsItemBriefProvider`, and constructs `NewsItemBriefWorker` only when News Intel, the worker, and LLM config are enabled.

### HTTP

`GET /api/news` remains read-only and paginated. Each row may include:

- `agent_brief`: compact current brief projection with status, decision, direction, summary_zh, market_read_zh, bull/bear strengths, data_gap count, computed time.
- `agent_brief_status`: duplicate scalar for cheap filtering/display.
- `agent_brief_computed_at_ms`.

`GET /api/news/items/{news_item_id}` includes:

- full `agent_brief`;
- latest `agent_run` audit summary excluding sensitive raw provider data;
- source packet summary with allowed evidence refs;
- deterministic facts already returned today.

Error modes:

- Missing item remains `404 news_item_not_found`.
- Missing agent brief is a successful item response with `agent_brief.status = pending | disabled | failed | stale`, never a 5xx by itself.
- API handlers never execute the agent.

Optional filters in `/api/news`:

- `brief_status=ready|insufficient|pending|failed|stale|disabled`
- `direction=bullish|bearish|mixed|neutral`
- `decision_class=driver|watch|context|discard`

The implementation may defer filters if the first plan needs a smaller first PR, but returned fields must be shaped so filters can be added without a breaking response change.

### Frontend

`web/src/shared/model/newsIntel.ts` adds `NewsAgentBrief` and run-audit summary types.

`web/src/features/news/NewsPage.tsx` changes:

- List table: replace "Event / Question", "Route", and "Next" generated analysis with persisted agent brief columns: `Brief`, `Direction`, `Decision`, `Evidence/Gaps`.
- Detail page: add an agent brief panel above extracted facts with Chinese summary, market read, bull/bear columns, watch triggers, invalidation conditions, evidence refs, and data gaps.
- Missing/degraded states: render `pending`, `disabled`, `failed`, `stale`, and `insufficient` visibly and tersely.

`web/src/features/news/newsViewModel.ts` keeps only mechanical formatting helpers. It must not generate `summary_zh`, `market_read_zh`, bull/bear theses, decision class, or next action from headline keywords.

## Acceptance Criteria

- AC1. WHEN a processed news item has changed facts and `news_item_brief` is enabled THEN `NewsItemBriefWorker` SHALL write one `NewsItemAgentRun` row and either upsert a current `NewsItemAgentBrief` or record a validation/failure outcome.
- AC2. WHEN `AgentExecutionGateway` denies capacity before provider execution THEN the selected news item SHALL surface a no-start backpressure outcome without consuming a provider attempt.
- AC3. WHEN an agent output cites an evidence ref not present in the input packet THEN validation SHALL fail the run and no `ready` current brief SHALL be published.
- AC4. WHEN an agent output includes order/execution language THEN validation SHALL fail the run and preserve the error in the run ledger.
- AC5. WHEN `/api/news` returns a row with a ready brief THEN the row SHALL include `summary_zh`, `direction`, `decision_class`, bull/bear strengths, brief status, and computed timestamp.
- AC6. WHEN `/api/news/items/{news_item_id}` returns a detail row THEN it SHALL include deterministic extraction facts plus the full current brief or a visible missing/degraded brief state.
- AC7. WHEN LLM config is absent or the brief worker is disabled THEN `/news` SHALL continue to render deterministic news facts and SHALL show `agent_brief.status=disabled` or equivalent unavailable state, not heuristic analysis.
- AC8. WHEN a frontend test fixture includes a ready brief THEN `/news` SHALL render Chinese summary and bull/bear text from the fixture payload, and changing the headline alone SHALL NOT change those rendered analysis fields.
- AC9. WHEN an item's content hash, token lanes, fact lanes, or story membership changes THEN the previous current brief SHALL become stale or be replaced by a new brief whose `input_hash` reflects the changed packet.
- AC10. WHEN implementation completes THEN `src/gmgn_twitter_intel/domains/news_intel/ARCHITECTURE.md`, `docs/ARCHITECTURE.md`, `docs/WORKERS.md`, and public contract docs SHALL name the new worker/read model ownership.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Agent overstates tradeability for unresolved token mentions. | High | Preserve identity status in packet; schema requires affected assets to carry resolution status; validation rejects unsupported asset refs and UI shows identity/data gaps. |
| Frontend keeps old headline heuristics and conflicts with backend brief. | High | Remove narrative-generating helpers from `newsViewModel`; add tests where headline changes but brief text remains stable. |
| New agent lane starves Pulse/Narrative lanes. | Medium | Use low/normal priority, max concurrency 1, RPM cap, and no-start backpressure semantics through `AgentExecutionGateway`. |
| Brief table becomes perceived as business truth. | Medium | Document as read model, expose deterministic facts beside it, and keep News worker boundaries from writing Token Radar/Pulse/market facts. |
| Prompt injection from article body. | Medium | Packet/instructions state source text is data; no tools are exposed; validation rejects execution/mutation language. |
| Audit payload stores excessive raw body text. | Medium | Bound body excerpts; hash full input; store replayable but redacted/size-limited request JSON; never include secrets. |
| Too much schema on first cut delays value. | Medium | Keep one single-stage item brief, no story-level digest, no closed-loop learning, no market settlement. |

## Evolution Path

The next natural expansion is a story-group brief that summarizes multi-source continuity and suppresses duplicate rows. This spec deliberately keeps the item brief packet story-aware so a later story digest can reuse the same evidence-ref vocabulary. Another expansion is market reaction overlay, but it should read existing `market_ticks` or a dedicated read-side quote surface and must remain an overlay, not an agent-owned price fact.

Later offline eval can freeze real item packets and replay prompt/schema candidates. This should reuse the run ledger and artifact hashes introduced here, but it should not block the first production item-brief path.

## Alternatives Considered

- **Story-group brief first** — rejected for this cut because the user wants `/news` improved now, and current `/news` navigation is item-first. Story grouping is deterministic and useful context, but making it the primary agent target would make grouping quality a release blocker.
- **On-demand brief generation from item detail** — rejected because API handlers must stay read-only and because request-time LLM calls would create latency, retry, and audit ambiguity.
- **Reuse the old frontend heuristic view model with Chinese copy** — rejected because it preserves the core problem: browser code would still be inventing market analysis without audit, model version, evidence refs, or replay.
- **Import `news-intel` closed-loop/harness wholesale** — rejected because this repository already has PostgreSQL Kappa/CQRS, `AgentExecutionGateway`, worker registry, and domain boundaries. LanceDB snapshots, settlement, learning, and SSE would be a different product cut.
- **Attach brief JSON directly to `news_items`** — rejected because agent output is a derived, versioned read model. Keeping it separate preserves fact/read-model boundaries and allows rebuilding without mutating raw item facts.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Build one item-scoped, source-backed, Chinese agent brief from persisted News Intel facts; persist run audit; expose current brief through read APIs; render persisted brief in `/news`. |
| Ask first | Add story-level briefs, market reaction scoring, offline eval activation gates, new notification rules from news briefs, or broader route redesign beyond the existing `/news` page. |
| Never | Produce execution instructions, mutate Token Radar/Pulse/market facts, execute agents in API handlers, hide failed/pending agent state behind heuristic copy, or copy `news-intel` LanceDB/closed-loop runtime into this service. |

## Spec Self-Review

- Placeholder scan: no placeholder sections remain.
- Internal consistency: the design keeps News facts, agent run ledger, current brief read model, API, and frontend responsibilities separate.
- Scope check: single item brief is a single implementation plan; story-level digest and closed-loop eval remain future work.
- Ambiguity check: disabled, pending, failed, insufficient, stale, and ready states are explicit public states, and execution-language output is forbidden.
