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
- `news_page_rows` is the rebuildable, story-shaped News page read model. A
  row represents a stable `story_key` when deterministic story identity is
  available, or the single item when no story key exists. Its `story_json`
  carries compact member ids/counts and source/provider article key evidence.
  Its `analysis_admission_status` separates broad page visibility from crypto
  analysis eligibility. Its `signal_json` is an explicit envelope:
  `display_signal` is the product display choice, `provider_signal` preserves
  provider-native evidence, `agent_signal` preserves compact current-brief
  state, `agent_requirement` copies the persisted item-level agent gate, and
  `alert_eligibility` is an object whose `in_app_eligible` field can be true
  for high-signal candidates only after the item/story is `admitted`. External
  phone pushes require `external_push_ready` plus a ready, publishable current
  brief; `external_push_block_reason` records why a row is not publishable.
- `news_sources` carries source classification (`provider_type`,
  `source_role`, `trust_tier`, `coverage_tags`) and source policy JSON. The
  page read model copies the compact classification fields into `source_json`
  so `/api/news` can filter without calling providers.
- `news_items` carries item content classification (`content_class`,
  `content_tags_json`, and `content_classification_json`), analysis admission
  (`analysis_admission_*`), persisted single-item agent requirement
  (`agent_requirement_status`, `agent_requirement_reason`,
  `agent_requirement_priority`, `agent_requirement_json`,
  `agent_requirement_version`), and deterministic story identity (`story_key`,
  `story_identity_json`). These describe what happened, whether it is eligible
  for crypto analysis, whether a single-item brief agent is required, and how
  it groups for the current serving projection. Story identity is rebuildable
  state over facts, not a separate material truth table.
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

## Stage Map

Required core:

```text
news_fetch -> news_item_process(admission + story identity)
  -> news_page_projection(story rows)
```

Optional enhancement:

```text
news_item_process(agent_requirement_status=required) -> news_item_brief -> news_page_projection
```

Operational projection:

```text
news_fetch/source refresh -> news_source_quality_projection
  -> page dirty only when compact source status changes
```

| Stage | Responsibility |
|-------|----------------|
| Fetch | Reconcile configured sources into `news_sources`, fetch due feeds, persist provider items and normalized news items, then enqueue semantic page/source-refresh work. It does not create agent brief work. |
| Item processing | Read raw `news_items`, extract entities and token mentions deterministically, classify item content, write attention-safe observations and fact candidates, compute analysis admission, compute deterministic story identity, compute and persist `agent_requirement_*`, and enqueue optional item-brief work only when `agent_requirement_status = required`. |
| Item brief | Read persisted `agent_requirement_*`; only required items may execute. Build bounded item/token/fact packets, reserve `news.item_brief`, execute through the shared `AgentExecutionGateway`, shape-validate the standard brief output, write the run ledger, upsert the current brief, and dirty page rows. Evidence refs and sparse source context are audit/quality metadata, not publication gates. |
| Page projection | Claim item-scoped dirty targets, expand them to bounded story groups, and rebuild story-shaped News page rows from news facts, admission, story identity, provider-native signal, persisted agent requirement, and the current item brief. It does not recompute agent requirement policy. |
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
- Provider token impacts and provider scores are evidence, not crypto identity
  and not analysis admission by themselves. A bare ticker/common word must not
  create a crypto driver/watch row without admitted crypto-native evidence.
- `NewsItemProcessWorker` is the only runtime writer for item-level
  `agent_requirement_*`. Brief input repair, page projection, API, and UI must
  read this persisted requirement and must not rerun an equivalent score,
  admission, or freshness policy.
- Retired News research tools are not runtime surfaces. Cleanup may keep their
  names only as purge markers for deleting old agent artifacts.
