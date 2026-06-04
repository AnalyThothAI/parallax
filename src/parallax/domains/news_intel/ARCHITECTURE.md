# News Intel Architecture

News Intel owns configured news source ingestion, raw news item facts,
deterministic entity and token mention observations, fact candidates,
item-scoped agent briefs, and the independent News page read model.

The bounded context does not own Token Radar, Pulse, or market facts. News
workers never write Token Radar current/history/audit read models, Signal Pulse tables, or price tick
tables. Token identity is read only through domain interfaces; unresolved,
unknown, or ambiguous mentions remain in attention state instead of being
forced into a resolved asset.

## Truth And Read Models

- `news_sources`, `news_fetch_runs`, `news_provider_items`, `news_items`,
  `news_item_entities`, `news_token_mentions`, and `news_fact_candidates` are
  material facts or control-plane state owned by News Intel.
- Provider raw feed entries are inputs. The persisted fact path is
  `news_provider_items` plus normalized `news_items`.
- `news_page_rows` is the rebuildable News page read model. Its `signal_json`
  is an explicit envelope: `display_signal` is the product display choice,
  `provider_signal` preserves provider-native evidence, `agent_signal`
  preserves compact current-brief state, and `alert_eligibility` separates
  provider/in-app candidate visibility (`in_app_eligible`) from external
  notification readiness (`external_push_ready`,
  `external_push_block_reason`). Provider high-score rows may be visible before
  an agent brief is publishable; external phone pushes require the explicit
  ready state.
- `news_sources` carries source classification (`provider_type`,
  `source_role`, `trust_tier`, `coverage_tags`) and source policy JSON. The
  page read model copies the compact classification fields into `source_json`
  so `/api/news` can filter without calling providers.
- `news_items` carries item content classification (`content_class`,
  `content_tags_json`, and `content_classification_json`). This describes what
  happened in the item and is independent of who published it.
- Public `http://` and `https://` URLs admitted by
  `public_url_identity_policy` are the hard identity for `news_items`.
  Homepage, aggregator, live page, feed, preview, and generic announcement URLs
  are provider/raw evidence only and must not become serving canonical URLs.
  `url_identity_kind` is diagnostic context, not a storage dedup gate. OpenNews
  missing-link observations may attach to an existing canonical item only
  through bounded deterministic material identity.
- `news_item_agent_runs` is the append-only audit ledger for single-item
  agent brief attempts. `news_item_agent_briefs` is the current item-scoped
  brief read model. `NewsItemBriefWorker` is the only runtime writer for both.
- `news_source_quality_rows` is a rebuildable source-quality read model
  written only by `NewsSourceQualityProjectionWorker`; `news_sources`
  stores only the compact latest `source_quality_status`.
- `news_fact_candidates` references only `news_items`.

## News Item Brief Research Harness

News item brief generation is adaptive. Eligible stale targets either follow
empty-plan synthesis when the base packet is self-contained, or run:

```text
deterministic research policy -> local read-only tool executor -> synthesis
```

The deterministic policy is host code in News Intel. It chooses bounded
News-owned tools from the base packet, content class, resolved target refs,
fact lanes, observation summary, and dirty reason. The local executor validates
tool names and inputs, enforces row and character clamps, runs SELECT-only
repository methods, redacts raw provider payload fields, and hashes compact
results before synthesis. The model receives only the synthesis packet and
returns strict structured JSON.

There is no shared runtime tool loop. `AgentExecutionGateway` still runs one
structured JSON model call for the `news_item_brief_synthesis` stage; it does
not receive native tools and does not execute database reads. `AgentStageSpec`
continues to carry an `input_payload` without `tools=`.

Tools are input evidence, not business facts. Their compact outputs may support
novelty, duplicate/update, source-consensus, and retrieval-note claims, but
PostgreSQL facts and rebuildable read models remain the product truth. Provider
raw frames and tool results are never promoted directly into facts. The
publication gate remains News validation plus the worker-owned run ledger and
current brief write.

`NewsItemBriefWorker` remains the only runtime writer for
`news_item_agent_runs` and `news_item_agent_briefs`. Host deterministic policy
and read-only tool executor are News-local harness components, not a lower
level application workflow kernel and not a cross-domain agent runtime.

## Stage Map

Required core:

```text
news_fetch -> news_item_process -> news_page_projection
```

Optional enhancement:

```text
news_item_process -> news_item_brief -> news_page_projection
```

Operational projection:

```text
news_fetch/source refresh -> news_source_quality_projection
  -> page dirty only when compact source status changes
```

| Stage | Responsibility |
|-------|----------------|
| Fetch | Reconcile configured sources into `news_sources`, fetch due feeds, persist provider items and normalized news items, then enqueue semantic page/source-refresh work. It does not create agent brief work. |
| Item processing | Read raw `news_items`, extract entities and token mentions deterministically, classify item content, write attention-safe observations and fact candidates, and admit optional item-brief work only after processed-state policy passes. |
| Item brief | Build a bounded base packet, reserve `news.item_brief`, run empty-plan synthesis or deterministic research policy plus the local read-only tool executor, call the shared `AgentExecutionGateway` only for structured JSON synthesis, validate the v2 brief, write the run ledger, upsert the current brief, and dirty page rows. Tool evidence is run input context, not a fact or publication gate by itself. |
| Page projection | Rebuild the News page rows from news facts, item lifecycle, provider-native signal, and the current item brief. |
| Source quality projection | Own source-quality windows, expand source refresh intents into configured source/window work, rebuild source quality rows, and dirty page rows only when compact source quality status changes. It is an operational projection, not item hot-path fanout. |
| API/UI | Read-only surfaces over projected `news_page_rows`, with explicit source/content/decision filters and source status diagnostics. Raw `news_items` are worker inputs, not public fallback rows. |

## Provider Waves

The runtime-supported News provider types are `rss`, `atom`, `json_feed`,
`cryptopanic`, and `opennews`. `/api/news/sources/status` reports these
alongside configured provider types and source hygiene warnings.

- Wave 1: enable `cryptopanic` where credentials exist; keep it as an
  aggregator or specialist source, not an authority source.
- Wave 2: enable OpenNews only as a provider-fact source. OpenNews is
  REST-only in `news_fetch`: `/open/news_search` is the canonical path for
  `aiRating` and `coins[]` impact facts. Short-lived OpenNews WebSocket
  subscribe cycles and hybrid fetch mode are not runtime surfaces.
- Wave 3: add official RSS/manual API feeds for exchanges, regulators,
  protocols, and issuers. These are the feeds eligible for accepted fact
  candidates after authority-scope validation.
- Wave 4: add OpenBB/macro source adapters only where they do not cross
  ownership with `macro_intel`.
- Wave 5: add social/community/developer primary-item sources only after a
  fresh spec. Replies, comments, and threads are not a current News runtime
  storage surface.

## Boundaries

- News workers never write Token Radar rows, Pulse candidate state, or market
  tick facts.
- API handlers are read-only. They do not fetch feeds, run entity extraction,
  resolve token identity, execute projection workers, or run agents.
- The News agent adapter is behind the `NewsItemBriefProvider` contract and
  delegates SDK execution to the process-wide `AgentExecutionGateway`. News
  domain code owns validation and persistence, not runner construction.
- Unknown and ambiguous token mentions stay attention-visible until a later
  deterministic pass can resolve them.
