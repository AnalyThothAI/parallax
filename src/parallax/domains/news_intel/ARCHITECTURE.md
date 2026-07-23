# News Intel Architecture

News Intel ingests configured sources, preserves provider observations,
canonicalizes items, derives deterministic entity/fact/story evidence, and
projects a fact-only News page. PostgreSQL facts are the business truth;
provider frames are inputs and workers recover by bounded interval catch-up.

The domain has no model-backed producer, generated prose, inferred thesis, or
notification rule.

## Material facts and current state

Material facts and durable control/audit state:

- `news_sources`, `news_fetch_runs`, and `news_provider_items` preserve source
  configuration, fetch history, and provider observations.
- `news_items` is canonical item truth.
- `news_item_observation_edges`, `news_item_entities`,
  `news_token_mentions`, and `news_fact_candidates` preserve deterministic
  evidence.
- Story identity/membership and market scope are deterministic item facts.

Rebuildable CQRS state:

- `news_page_rows` is the fact-only serving projection.
- `news_projection_dirty_targets` is bounded operational work state and admits
  only page work.

Run ids, attempts, timestamps, and generations never identify current state.

## Repository and writer ownership

| Binding | Repository | Ownership |
|---|---|---|
| `news_sources` | `NewsSourceRepository` | source config, fetch lifecycle, provider observations, sync cursor, compact health |
| `news_items` | `NewsItemRepository` | canonical items, observation remap, entities, token mentions, fact candidates, story identity/membership, market scope |
| `news_pages` | `NewsPageRepository` | page projection writes and News read queries |

There is no aggregate News repository. Callers select the owner directly.

| State | Single runtime writer |
|---|---|
| source, fetch, provider observation, canonical item | `NewsFetchWorker` |
| deterministic item evidence and identity | `NewsItemProcessWorker` |
| page current rows | `NewsPageProjectionWorker` |

All News workers use `parallax.platform.runtime` primitives.

## Kappa/CQRS flow

```text
configured source
  -> fetch attempt + provider observation
  -> canonical item
  -> deterministic item/entity/token/fact/story processing
  -> page dirty target
  -> news_page_rows
  -> fact-only API and frontend
```

Every serving row is rebuildable from material facts. Workers always re-read
PostgreSQL on a bounded interval; there is no wake-message dependency.

## Dirty-target contract

Every target has:

```text
projection_name = "page"
target_kind = "news_item"
target_id = <canonical news item id>
window = ""
```

The producer supplies a positive `source_watermark_ms`. Claim completion uses
projection name, target kind/id/window, lease owner, attempt count, and payload
hash as the exact CAS token. Enqueue, claim, completion, retry, and
terminalization use PostgreSQL rowcount evidence.

Page projection expands bounded story membership, builds one complete serving
row, and writes only when its stable payload hash changes. An unchanged
projection writes zero rows.

## Fact-only page contract

`news_page_rows_v6_facts_only` contains:

- stable row/item/story identity and deterministic story membership;
- published time, lifecycle, headline, summary, canonical URL, and dedupe
  counts;
- token-resolution lanes and fact-candidate lanes with explicit statuses;
- provider-supplied rating fields;
- content class/tags/classification;
- source role/trust/coverage/quality;
- deterministic market scope;
- computation time and projection version.

The projection does not create a direction, alert eligibility, generated
summary, thesis, confidence, or prose interpretation. Provider rating fields
remain attributed provider observations rather than Parallax conclusions.
Readers validate required structures and fail closed on malformed current
rows.

`/api/news` reads current page rows. Item detail first requires a current row,
then hydrates persisted provider observations, entities, token mentions, and
fact candidates. Fact detail reads the selected persisted candidate. Source
status combines `news_sources` with fetch history. Read handlers do not fetch a
provider, execute projection code, or synthesize missing rows.

## Transactions and restart recovery

Workers own transactions through `RepositorySession.transaction()`.
Repository public writes neither commit nor open an implicit transaction.
Multi-step queue/read-model/terminal transitions therefore share one
caller-owned transaction.

Configured source payloads are canonicalized into `config_payload_hash`. A
deterministic terminal provider refusal disables the source and records the
same hash in `terminal_config_payload_hash`. Restart reconciliation keeps the
source disabled while the hashes match. A real operator config change clears
the terminal marker and reapplies configured enabled state.

Runtime provider types are `rss`, `atom`, `json_feed`, `cryptopanic`, and
`opennews`. Provider capability is a static application/schema contract.
Provider I/O remains outside database transactions. News workers do not write
Token Radar or market facts.
