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
- `news_page_rows` is the rebuildable News page read model.
  `signal.alert_eligibility` separates provider/in-app candidate visibility
  (`in_app_eligible`) from external notification readiness
  (`external_push_ready`, `external_push_block_reason`). Provider high-score
  rows may be visible before an agent brief is publishable; external phone
  pushes require the explicit ready state.
- `news_sources` carries source classification (`provider_type`,
  `source_role`, `trust_tier`, `coverage_tags`) and source policy JSON. The
  page read model copies the compact classification fields into `source_json`
  so `/api/news` can filter without calling providers.
- `news_items` carries item content classification (`content_class`,
  `content_tags_json`, and `content_classification_json`). This describes what
  happened in the item and is independent of who published it.
- Public `http://` and `https://` canonical URLs are the global hard identity
  for `news_items`, regardless of provider, source role, category, or
  `url_identity_kind`. Provider observations with the same public canonical URL
  collapse into one `news_items` row and remain visible through
  `news_item_observation_edges`; `url_identity_kind` is diagnostic context, not
  a storage dedup gate. Content hash and provider article id are fallbacks only
  when no public canonical URL is available.
- `news_item_agent_runs` is the append-only audit ledger for single-item
  agent brief attempts. `news_item_agent_briefs` is the current item-scoped
  brief read model. `NewsItemBriefWorker` is the only runtime writer for both.
- `news_source_quality_rows` is a rebuildable source-quality read model
  written only by `NewsSourceQualityProjectionWorker`; `news_sources`
  stores only the compact latest `source_quality_status`.
- `news_fact_candidates` references only `news_items`.

## Stage Map

| Stage | Responsibility |
|-------|----------------|
| Fetch | Reconcile configured sources into `news_sources`, fetch due feeds, persist provider items and normalized news items. |
| Item processing | Read raw `news_items`, extract entities and token mentions deterministically, classify item content, and write attention-safe observations and fact candidates. |
| Item brief | Build bounded item/token/fact packets, reserve `news.item_brief`, execute through the shared `AgentExecutionGateway`, validate the output, write the run ledger, and upsert the current brief. |
| Page projection | Rebuild the News page rows from news facts, item lifecycle, and the current item brief. |
| Source quality projection | Rebuild per-source quality windows from source/fetch/item/token/fact/brief/context rows and update compact source quality status. |
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
- Wave 5: add social/community/developer context sources. Replies, comments,
  and threads belong in `news_context_items`, not in `news_items.body_text`.

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
