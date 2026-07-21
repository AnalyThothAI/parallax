# News Intel Architecture

News Intel ingests configured sources, preserves provider observations,
canonicalizes news items, derives deterministic evidence, produces one current
story brief, and projects the News page. PostgreSQL facts are the business
truth; provider frames are inputs and workers catch up on bounded intervals.

## Material facts and read models

Material facts and durable control state:

- `news_sources`, `news_fetch_runs`, and `news_provider_items` preserve source,
  fetch, and provider-observation history.
- `news_items` is canonical item truth.
- `news_item_observation_edges`, `news_item_entities`,
  `news_token_mentions`, and `news_fact_candidates` preserve deterministic
  evidence.
- Story identity, market scope, and admission are deterministic item state.

Rebuildable CQRS state:

- `news_story_agent_runs` is the append-only story execution ledger.
- `news_story_agent_briefs` is the one current story-brief projection, keyed by
  stable `story_brief_key`.
- `news_page_rows` is the serving projection.
- `news_projection_dirty_targets` is bounded operational work state.

Run ids, attempts, timestamps, and generations never identify current state.

## Repository ownership

News has four business repositories, each bound explicitly by
`RepositorySession`:

| Binding | Repository | Ownership |
|---|---|---|
| `news_sources` | `NewsSourceRepository` | source config, fetch lifecycle, provider observations, sync cursor, compact health |
| `news_items` | `NewsItemRepository` | canonical items, observation remap, deterministic evidence, scope, story identity, admission |
| `news_story_agents` | `NewsStoryAgentRepository` | story run ledger and one current story brief |
| `news_pages` | `NewsPageRepository` | page projection writes and News read queries |

There is no aggregate News repository. Callers select the owner directly.

Runtime single writers are:

| State | Writer |
|---|---|
| source, fetch, provider observation, canonical item | `NewsFetchWorker` |
| deterministic item evidence and identity | `NewsItemProcessWorker` |
| story run ledger and current brief | `NewsStoryBriefWorker` |
| page rows | `NewsPageProjectionWorker` |

All News workers use `parallax.platform.runtime` worker primitives.

## Kappa/CQRS flow

```text
configured source
  -> provider observation
  -> canonical item
  -> deterministic item processing
  -> story_brief dirty target -> story run/current
  -> page dirty target        -> news_page_rows
  -> API / WebSocket / CLI
```

Workers always perform bounded interval catch-up from PostgreSQL. Every serving
row can be rebuilt from material facts.

## Dirty-target contract

Only two projection names are valid:

- `page`: `target_kind = 'news_item'`, stable canonical item id, empty window.
- `story_brief`: `target_kind = 'story'`, stable story key, empty window.

Both require a positive producer-supplied `source_watermark_ms`. Claim
completion uses lease owner, attempt count, and payload hash as a CAS token.
Enqueue, claim, completion, retry, and terminalization use PostgreSQL rowcount
evidence.

Page projection expands bounded story membership, builds the complete serving
row, and writes only when its stable payload hash changes. An unchanged
projection writes zero rows. Story current identity is derived from story
identity version plus `story_key`; a reusable run must match the persisted
input and artifact identity exactly.

## Transactions and restart recovery

Application services and workers own transactions with
`RepositorySession.transaction()`. Repository public writes neither commit nor
open an implicit transaction. Multi-step state transitions therefore share one
caller-owned transaction, including dirty-target terminalization.

Configured source payloads are canonicalized into `config_payload_hash`. A
deterministic terminal provider refusal disables the source and records the same
hash in `terminal_config_payload_hash`. Restart reconciliation keeps that source
disabled while the hashes match. A real config change clears the terminal
marker and reapplies configured enabled state, so restart is idempotent and an
operator correction resumes ingestion.

## Read and provider boundaries

The News API reads `news_page_rows`. Item detail first requires a current page
row, then hydrates provider observations and deterministic evidence. Public
story, signal, admission, and brief fields come from the projected row. Market
scope has one public location, `signal.alert_eligibility.market_scope`; the
physical `market_scope_json` column is derived from that nested value at the
single writer boundary and is not a second public field. Admission status and
reason remain top-level row fields and have no alert-eligibility aliases.
Signal, token/fact lane arrays with explicit lane/status values, and brief
status are required current sections; readers fail closed on malformed rows.

Runtime source types are `rss`, `atom`, `json_feed`, `cryptopanic`, and
`opennews`. Provider capability is a static application/schema contract. The
story model client delegates execution to the process-wide agent gateway; the
domain owns packet construction, validation, persistence, and publication.

News workers do not write Token Radar or market facts, and read handlers do not
fetch providers, run workers, or execute models.
