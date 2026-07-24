# Architecture

Tracefold is one Python service, one CLI, one React console, and one PostgreSQL
database. The architecture remains Kappa/CQRS: append-oriented material facts
are the only business truth; deterministic current views and immutable research
publications are derived state.

## Data flow

```text
providers / public streams
  -> integrations
  -> PostgreSQL material facts
  -> durable dirty targets or bounded catch-up
  -> single-writer read models or immutable publications
  -> HTTP / WebSocket / CLI / React
```

Workers recover exclusively by re-reading PostgreSQL on bounded
`interval_seconds` loops. There is no database wake plane or in-memory
correctness dependency. Provider raw frames remain inputs until normalized and
persisted as material facts.

## Truth, control state, and derived state

Material facts include:

- evidence: `raw_frames`, `events`, `event_entities`;
- identity: `token_evidence`, `token_intents`,
  `token_intent_lookup_keys`, `token_intent_resolutions`,
  `registry_assets`, `asset_identity_evidence`, `asset_identity_current`;
- market: `market_ticks`, `enriched_events`;
- news: `news_provider_items`, `news_items`, and persisted story/entity/fact
  edges;
- macro: `macro_observations`;
- notifications: `notifications` and the external delivery facts in
  `notification_deliveries`. `account_token_alerts` remains a Market fact that
  Notifications consumes through an explicit input.

Current read models are `token_radar_current_rows`,
`token_profile_current`, `market_tick_current`, and `news_page_rows`. Each uses
stable product/window/target identity, has exactly one runtime writer, is
rebuildable from facts, and writes zero serving rows when its business payload
is unchanged.

Queues, leases, retries, fetch attempts, sync runs, terminal events, and agent
checkpoints are control or audit state. They are not alternate business truth.
`macro_research_publications` is immutable derived research keyed by completed
U.S. session; it is not a material Macro fact.

## Package map

```text
tracefold.market
  capture/       provider-neutral evidence ingestion
  identity/      token and asset identity resolution
  pricing/       append-only market facts and current prices
  profiles/      source-backed token profiles and image state
  radar/         transparent factor projection
  views/         persisted market read queries

tracefold.news
  ingest/        provider facts and source health
  projection/    deterministic item and page projection
  views/         persisted News reads

tracefold.macro
  observations/  provider fact import and live evidence reads
  research/      completed-session immutable research lifecycle

tracefold.notifications
  durable notification creation, rules, and delivery state

tracefold.integrations
  provider and external-system adapters, including DeepAgents

tracefold.platform
  config, PostgreSQL/Alembic, telemetry, paths, and generic worker mechanics

tracefold.app
  composition, repositories/providers, worker registry, HTTP/WS, and CLI
```

The four business package roots are their public Python interfaces:
`tracefold.market`, `tracefold.news`, `tracefold.macro`, and
`tracefold.notifications`. Consumers outside an owning package import from the
root only. Internal subpackages may change without creating a repository-wide
import graph.

The dependency direction is:

```text
app -> integrations + business packages + platform
integrations -> business package interfaces + platform
news -> market + platform
macro -> market + news + platform
market -> platform
notifications -> platform
platform -> Python / third-party libraries only
```

Business packages never import `tracefold.app` or provider integrations.
Transport adapters do not own business rules. Generic worker mechanics live in
`tracefold.platform.workers`; queue state machines and read-model behavior stay
with their business owner. These rules are executable in
`tests/architecture/test_backend_boundaries.py`.

SQL ownership follows the same boundary: Market owns the event, token, asset,
profile, price, Radar, and collector tables; News owns `news_*`; Macro owns
`macro_*`; Notifications owns `notification*`. Platform owns Alembic,
checkpoint, and generic terminal-evidence tables. Cross-business reads go
through the owner package interface—for example, completed-session Macro
research uses the News-owned bounded research-evidence reader rather than
querying `news_items` itself. The architecture gate checks SQL table references
against the generated current schema.

## Transaction ownership

Application services and workers own transaction scope. Repository writes use
the supplied connection and never expose commit switches or open hidden
transactions.

Important atomic units are:

- fact persistence, identity resolution, market capture, and downstream dirty
  target creation;
- current read-model write plus acknowledgement of the exact claim;
- immutable Macro publication plus transition of its run to `published`;
- notification creation plus activation of delivery rows;
- retry or terminal transition plus mutation of its source queue row.

Provider, model, subprocess, filesystem, and network I/O occurs outside
database transactions. External delivery follows claim, commit, I/O, then a
compare-and-set completion or retry.

## Product flows

### Market and Token Radar

`market_tick_current` is transactionally maintained from append-only
`market_ticks`; it has no projection worker or dirty queue. Explicit bounded
fact replay rebuilds it.

```text
events + intents + resolutions + market facts
  -> token_radar_dirty_targets
  -> source edges + target features
  -> token_radar_current_rows + publication state
  -> Radar, Search, Token Case, notifications
```

The public Radar row is a transparent `factor_snapshot` built only from
persisted identity, social, and market facts.

### News

```text
configured sources
  -> fetch ledger + provider items + canonical news facts
  -> deterministic item processing
  -> page dirty targets
  -> news_page_rows
```

`page` is the only News projection target. Rows contain persisted source,
membership, entity-resolution, fact-candidate, content, and market-scope fields;
there is no generated thesis or prose product layer.

### Macro

```text
macro_sync_windows
  -> provider bundles
  -> macro_observations
  -> persisted-only live evidence reads

completed-session macro_research_runs
  -> one frozen-scope DeepAgents graph
  -> one immutable macro_research_publications row
  -> persisted-only research read
```

Live Macro evidence reads bounded `macro_observations` directly through six
descriptive lenses. It has no projection table or semantic readiness gate.
Completed-session research freezes session, cutoff, and evidence visibility
before model work. PostgreSQL checkpoints are resumable execution state, not
facts or a second publication source. Read requests never invoke the graph.

## Safety boundary

`events.raw_json` and `events.event_json` remain because historical events do
not yet have a proven one-to-one `raw_frames` source edge and locator. They may
be removed only after new writes persist the edge, historical coverage is
verified at 100%, and ambiguous payloads are exported as immutable evidence.
No runtime fallback path should be introduced meanwhile.

See [Public Contracts](CONTRACTS.md), [Operations](OPERATIONS.md), and
[Frontend Architecture](FRONTEND.md) for the other current authority surfaces.
