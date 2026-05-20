# News Intel Architecture

News Intel owns configured news source ingestion, raw news item facts,
deterministic entity and token mention observations, deterministic story
grouping, fact candidates, item-scoped agent briefs, and the independent News
page read model.

The bounded context does not own Token Radar, Pulse, or market facts. News
workers never write `token_radar_rows`, Signal Pulse tables, or price tick
tables. Token identity is read only through domain interfaces; unresolved,
unknown, or ambiguous mentions remain in attention state instead of being
forced into a resolved asset.

## Truth And Read Models

- `news_sources`, `news_fetch_runs`, `news_provider_items`, `news_items`,
  `news_item_entities`, `news_token_mentions`, and `news_fact_candidates` are
  material facts or control-plane state owned by News Intel.
- Provider raw feed entries are inputs. The persisted fact path is
  `news_provider_items` plus normalized `news_items`.
- `news_story_groups`, `news_story_members`, and `news_page_rows` are
  rebuildable read models.
- `news_item_agent_runs` is the append-only audit ledger for single-item
  agent brief attempts. `news_item_agent_briefs` is the current item-scoped
  brief read model. `NewsItemBriefWorker` is the only runtime writer for both.
- `news_fact_candidates` references only `news_items`; story association is
  derived through read-model queries.

## Stage Map

| Stage | Responsibility |
|-------|----------------|
| Fetch | Reconcile configured sources into `news_sources`, fetch due feeds, persist provider items and normalized news items. |
| Item processing | Read raw `news_items`, extract entities and token mentions deterministically, and write attention-safe observations and fact candidates. |
| Story projection | Rebuild deterministic story groups and memberships from news item facts and observations. |
| Item brief | Build bounded item/story/token/fact packets, reserve `news.item_brief`, execute through the shared `AgentExecutionGateway`, validate the output, write the run ledger, and upsert the current brief. |
| Page projection | Rebuild the News page rows from news facts, story state, item lifecycle, and the current item brief. |
| API/UI | Read-only surfaces over `news_page_rows` or raw visible `news_items` during early rollout. |

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
