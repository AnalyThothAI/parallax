# News Intel Architecture

News Intel owns configured news source ingestion, raw news item facts,
deterministic entity and token mention observations, fact candidates,
market-wide item-scoped agent briefs, and the independent News page read model.

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
  Its `market_scope_json` records deterministic market-scope metadata. Its
  `agent_admission_status` records the market-wide item brief decision after
  deterministic duplicate/similar checks.
  Its `signal_json` is an explicit envelope:
  `display_signal` is the product display choice, `agent_signal` preserves
  compact current-brief state, and `alert_eligibility` is an object whose
  `in_app_eligible` field can
  be true for high-signal candidates only after market-wide agent admission and
  current brief readiness pass.
  External phone pushes require `external_push_ready` plus a ready, publishable
  current brief; `external_push_block_reason` records why a row is not
  publishable.
- `news_sources` carries source classification (`provider_type`,
  `source_role`, `trust_tier`, `coverage_tags`) and source policy JSON. The
  page read model copies the compact classification fields into `source_json`
  so `/api/news` can filter without calling providers.
- `news_items` carries item content classification (`content_class`,
  `content_tags_json`, and `content_classification_json`), deterministic
  `market_scope_json`, market-wide agent admission (`agent_admission_*`), and
  deterministic story identity (`story_key`, `story_identity_json`). These
  describe what happened, what market transmission may matter, whether an item
  is a fresh representative agent target versus duplicate/similar covered, and
  how it groups for the current serving projection.
  OpenNews `provider_rating` is an LLM budget gate: only rows with a ready
  provider rating score of at least 80 can become fresh item-brief targets.
  The rating remains evidence for admission and display; it is not a
  publishable agent brief and notification delivery must not use it directly.
  Provider signal or provider impact changes invalidate item-scoped derived
  facts and return processed items to `raw` so `NewsItemProcessWorker` recomputes
  admission before any new brief work is enqueued.
  Current-state writes for market scope, story identity, and agent admission
  accept only the formal `NewsMarketScope`, `NewsStoryIdentity`, and
  `NewsItemAgentAdmission` domain results. Dict payloads, alias fields, and
  write-side default reconstruction are not runtime write contracts; row
  normalization is limited to public/projection reads.
  Deterministic entity, token mention, and fact candidate writes accept only
  formal `NewsEntity`, `NewsTokenMention`, and `NewsFactCandidate` results;
  object reflection is not a write-side compatibility surface. Those result
  types live in `news_intel.types`; repositories and queries must not import
  deterministic extraction/building services, runtime modules, or read models.
  Story identity is rebuildable state over facts, not a separate material truth
  table.
- Provider-native article ids, including OpenNews ids, are evidence only. They
  may appear in story/member evidence for auditability, but must not become a
  `story_key`. Stable story identity is derived from product facts such as
  exchange-listing venue, asset, quote market, and time bucket, then from
  normalized material title buckets, and finally from item-level keys for weak
  low-information items.
- Public `http://` and `https://` URLs admitted by
  `public_url_identity_policy` are the hard identity for `news_items`.
  Homepage, aggregator, live page, feed, preview, and generic announcement URLs
  are provider/raw evidence only and must not become serving canonical URLs.
  `url_identity_kind` is diagnostic context, not a storage dedup gate. OpenNews
  missing-link observations may attach to an existing canonical item only
  through bounded deterministic material identity.
  Canonical item identity values and provider-global article-key policy live in
  `news_intel.types.news_canonical_identity`; repositories and workers import
  that leaf type module directly instead of reaching upward into deterministic
  services.
- `news_item_agent_runs` is the append-only audit ledger for single-item
  agent brief attempts. `news_item_agent_briefs` is the current item-scoped
  brief read model. `NewsItemBriefWorker` is the only runtime writer for both.
  Agent-run inserts and current-brief upserts require rowcount=1 with a
  returned row before the worker reports audit/current brief writes, page dirty
  fan-out, or publication eligibility state.
- `news_source_quality_rows` is a rebuildable source-quality read model
  written only by `NewsSourceQualityProjectionWorker`; `news_sources`
  stores only the compact latest `source_quality_status`.
- `news_fact_candidates` references only `news_items`.

## Stage Map

Required core:

```text
news_fetch -> news_item_process(market scope + story identity + agent admission)
  -> news_page_projection(story rows)
```

Optional enhancement:

```text
news_item_process(market-wide agent admission) -> news_item_brief -> news_page_projection
```

Operational projection:

```text
news_fetch/source refresh -> news_source_quality_projection
  -> page dirty only when compact source status changes
```

| Stage | Responsibility |
|-------|----------------|
| Fetch | Reconcile configured sources into `news_sources`, fetch due feeds, persist provider items and normalized news items, then enqueue semantic page dirty work only from canonical repository `affected_news_item_ids` plus source-refresh work. Source configuration, due-source batch, source-claim lease, feed fetch limit, session timeout, provider requirement, and item/page dirty wake emission come from the formal `settings.workers.news_fetch` and `settings.news_intel` contracts. Configured-source `INSERT INTO news_sources ... ON CONFLICT ... RETURNING *` upserts require rowcount=1 with a returned source row before inserted/updated source rows are reported. Provider-item `INSERT INTO news_provider_items ... ON CONFLICT ... RETURNING *` upserts require rowcount=1 with a returned provider-item row before inserted/updated provider observations are reported. Canonical item `INSERT INTO news_items ... ON CONFLICT ... RETURNING *` upserts require rowcount=1 with a returned `news_items` row before observation edges, remap cleanup, or affected-item accounting use the canonical `news_item_id`. Observation-edge `INSERT INTO news_item_observation_edges ... ON CONFLICT` upserts require rowcount=1 before provider-article remap, material duplicate remap, summary refresh, representative reselection, or affected-item accounting treats the provider observation as linked. Due-source `UPDATE news_sources ... RETURNING sources.*` claims require PostgreSQL rowcount to match returned claim rows before provider work starts. Fetch-run start requires rowcount=1 for the `news_fetch_runs` running-row insert and matching `news_sources.last_fetch_at_ms` update before a run id is returned. Fetch-run `UPDATE news_fetch_runs ... RETURNING *` finalization requires rowcount=1 with a returned run row before `news_sources` status updates or finalized run rows are returned. Missing affected-set evidence for inserted/updated items fails the fetch run instead of synthesizing current-item dirty targets. It does not create agent brief work. |
| Item processing | Read raw `news_items`, extract entities and token mentions deterministically, classify item content, write attention-safe observations and fact candidates, compute deterministic `market_scope_json`, compute deterministic story identity, read the just-written admission context back through the repository, compute market-wide `agent_admission`, and enqueue optional item-brief work only for provider-rating-gated eligible/refresh representative targets. Entity, token mention, fact candidate, current market scope, story identity, and agent admission writes consume formal domain result objects only; dict/alias/default payloads and object reflection are not a write-side compatibility surface. Claim batch, lease, max attempts, retry delay, session timeout, and processed-item wake emission come from the formal `settings.workers.news_item_process` contract. Claiming `news_items` through `UPDATE news_items ... RETURNING items.*` must prove cursor rowcount matches returned claim rows before `NewsItemProcessWorker` treats items as leased. Claimed item rows must carry positive `processing_attempts` and non-empty `processing_lease_owner` before deterministic writes, retry/terminal failure, or projection dirty enqueue; malformed claims fail before state-machine branching. Missing repository admission context fails closed; worker-memory fallback context is not a compatibility surface. |
| Item brief | Build bounded item/entity/fact packets, reserve `news.item_brief`, execute through the shared `AgentExecutionGateway`, shape-validate the standard market-wide brief output, write the run ledger, upsert the current brief, and dirty page rows. Claim batch, lease, retry cadence, backpressure cooldown, session timeout, provider requirement, and brief-updated wake emission come from the formal `settings.workers.news_item_brief` contract. `news_item_agent_runs` `INSERT ... RETURNING *` and `news_item_agent_briefs` `INSERT ... ON CONFLICT ... RETURNING *` paths require rowcount=1 with a returned row before agent audit/current brief state or page dirty accounting is reported. Schema-version cleanup of current `news_item_agent_briefs` rows through `DELETE ... RETURNING news_item_id` requires cursor rowcount to match returned ids before stale-brief cleanup accounting is reported. Reusing completed/failed `news_item_agent_runs` for current brief restore requires a non-empty persisted `run_id`; malformed run identity fails the dirty target instead of triggering a second model call or writing an empty `agent_run_id`. Evidence refs and sparse source context are audit/quality metadata, not publication gates. |
| Page projection | Claim item-scoped dirty targets inside `RepositorySession.transaction`, expand them to bounded story groups, and rebuild story-shaped News page rows from news facts, market scope, agent admission, story identity, provider-native signal, and the current item brief. SQL timeout, claim batch, lease, and retry cadence come from formal `settings.workers.news_page_projection` fields, and the worker has no wake emitter because it emits no downstream wake. Page-row JSON sections (`token_lanes`, `fact_lanes`, `story`, `token_impacts`, `content_tags`, `content_classification`, `source`, `signal`, `provider_rating`, `agent_brief`, `market_scope`, and `agent_admission`) are required writer output before payload hash or SQL; the repository fails malformed rows instead of restoring missing sections to `[]`, `{}`, or pending agent state. `news_page_rows` `INSERT ... ON CONFLICT ... RETURNING (xmax = 0)` writes validate PostgreSQL rowcount against returned-row presence before inserted/updated/unchanged accounting: rowcount=0/no row is the only unchanged result, and rowcount=1/row is the only changed serving-row result. Page and item-brief dirty enqueue must first pass item ids through the repository `servable_news_item_ids` filter; missing filter contract fails closed rather than enqueueing raw ids. Missing session transaction support fails before claim/write and must not fall back to `nullcontext` or raw connection transactions. Terminalizing claimed dirty targets deletes the queue row and writes `worker_queue_terminal_events` inside a connection transaction; missing connection transaction support fails before delete/ledger SQL. Ordinary dirty-target repository enqueue/claim/done/error mutations also require the connection transaction when the repository owns the commit; missing transaction support fails before queue SQL. Dirty-target done/error/delete/terminalization completion keys require the claimed row `attempt_count`; malformed completion tokens fail before SQL instead of using synthesized zero attempts. |
| Source quality projection | Own source-quality windows inside `RepositorySession.transaction`, expand source refresh intents into configured source/window work, rebuild source quality rows, and dirty page rows only when compact source quality status changes. SQL timeout, claim batch, lease, retry cadence, and windows come from formal `settings.workers.news_source_quality_projection` fields. It is an operational projection, not item hot-path fanout. Missing session transaction support fails before claim/write and must not fall back to `nullcontext` or raw connection transactions. Terminal dirty-target delete/ledger writes require the same connection transaction contract, and dirty-target completion keys must carry the claimed row `attempt_count` instead of a synthesized zero attempt. |
| API/UI | Read-only surfaces over projected `news_page_rows`, with explicit source/content/decision filters and source status diagnostics. News page list rows, high-signal notification candidates, and item detail all preserve the current page-row contract before public shaping. Item detail requires a current page row before hydrating provider observations, facts, current brief, or run summaries as evidence. Once the page row exists, story, market-scope, signal, provider-rating, content, token/fact lane, and agent-admission fields come from that projected row only; malformed projected fields fail visibly instead of being repaired from raw `news_items`, empty JSON defaults, pending `agent_brief`, or `projection_missing` signal fallback. Raw `news_items` are worker inputs, not public fallback rows. |

News projection dirty-target completion keys preserve both claimed-row CAS
fields: `attempt_count` must be valid and `lease_owner` must be non-empty before
done/error/delete/terminalization SQL; `payload_hash` must also come from the
claimed row before completion SQL. Missing claim fields are malformed queue
state, not zero-attempt, empty-owner, or empty-payload compatibility tokens.
Claim rows returned by `claim_due` over `UPDATE news_projection_dirty_targets ...
RETURNING news_projection_dirty_targets.*` also require PostgreSQL
`cursor.rowcount` to match returned rows before Page/Source Quality workers treat
targets as leased work.
News projection dirty-target enqueue and done/error changed-row counts require
PostgreSQL `cursor.rowcount` evidence; missing, boolean, negative, or otherwise
invalid rowcount is malformed repository/driver state, not default zero changed
work or candidate `len(records)` enqueue accounting.
Terminal delete paths over `news_projection_dirty_targets` require the same
rowcount evidence, and cursor rowcount must match the returned deleted rows
before `worker_queue_terminal_events` are written.
Ops projection dirty repair is an explicit keyset enqueue path. Page and brief
repair read only item id, source watermark, and persisted agent-admission
status; source-quality-only repair skips `news_items` entirely. Repair code must
not rebuild the wide News page/brief projection input with source joins,
mentions/facts LATERAL aggregates, provider signal payloads, or admission JSON
just to enqueue dirty targets.

Agent admission duplicate/provider-article lookup uses normalized
`news_item_observation_edges.provider_article_key` edges, not
`jsonb_array_elements_text(...)` over `provider_article_keys_json`. The JSONB
field remains compact payload evidence for rows and prompts; indexed edge rows
are the SQL lookup contract.

`NewsFetchWorker`, `NewsItemProcessWorker`, and `NewsItemBriefWorker` write
News facts, agent admission/current brief state, run ledgers, projection dirty
targets, and worker claim/failure state inside `RepositorySession.transaction`.
Missing session transaction support is a worker/session contract failure before
reconcile, claim, or write; runtime code must not fall back to raw
`conn.transaction()`.
The item-brief repository writes also require single-row PostgreSQL
`RETURNING` evidence: `news_item_agent_runs` insert and
`news_item_agent_briefs` current upsert must both return exactly one row with
matching cursor rowcount before downstream page dirty or publication state is
reported.
`NewsItemBriefWorker` also treats `news_item_agent_runs.run_id` as the required
ledger/current-brief identity when restoring a completed or failed run. Missing
or blank run identity is malformed persisted state and must fail the dirty
target before model execution or current-brief upsert.
Completed-run validation is the formal `NewsItemBriefValidationResult` contract,
provider failure audit is the formal
`AgentExecutionRequestAudit | AgentExecutionResultAudit` contract, and market-wide
agent admission is the formal `NewsItemAgentAdmission` contract. The worker must
not restore these runtime values through arbitrary `getattr(...)`,
`model_dump`, `__slots__`, or object-reflection fallbacks.
Item-brief source-backed entity/domain support consumes formal
`NewsItemBriefEntityLane` entries from `NewsItemBriefInputPacket.entity_lanes`
directly. Missing lane fields or loose mapping/entity objects are malformed
packet state, not compatibility inputs that can be defaulted with
`getattr(..., fallback)`.
When `NewsRepository` owns a commit outside those worker sessions, source/fetch
run/provider item/canonical item writes, deterministic item facts, agent run and
current brief writes, source-quality rows, and page rows must enter a callable
connection transaction before SQL. Worker paths keep those writes caller-owned
with `commit=False` inside the outer `RepositorySession.transaction`; repository
default paths must not use naked `self.conn.commit()` or optional transaction
fallbacks. Repository methods that return item lifecycle, source-quality status,
source disable, or page-row changed counts require PostgreSQL `cursor.rowcount`
evidence; missing, boolean, negative, or otherwise invalid rowcount is malformed
repository/driver state, not default zero changed News work. Configured-source
`INSERT INTO news_sources ... ON CONFLICT ... RETURNING *` upserts must prove
rowcount=1 with a returned source row before inserted/updated source rows are
reported. Provider item
`INSERT INTO news_provider_items ... ON CONFLICT ... RETURNING *` upserts must
prove rowcount=1 with a returned provider-item row before inserted/updated
provider observations are reported. Canonical item
`INSERT INTO news_items ... ON CONFLICT ... RETURNING *` upserts must prove
rowcount=1 with a returned `news_items` row before observation edges, canonical
remap cleanup, or affected-item accounting use the canonical `news_item_id`.
Observation edge `INSERT INTO news_item_observation_edges ... ON CONFLICT`
upserts must prove rowcount=1 before provider-article remap, material duplicate
remap, summary refresh, or affected-item accounting treats the provider
observation as linked to the canonical item.
Provider-article and material duplicate edge-remap CTEs over
`news_item_observation_edges` must prove cursor rowcount matches returned old
item-id rows before old-item summary cleanup, dirty-target remap, or
affected-item accounting uses those ids.
Observation summary `UPDATE news_items ... RETURNING items.*` refreshes must
prove rowcount=1 with a returned current item row before affected-item accounting
uses refreshed source/provider-article aggregates; old zero-edge cleanup paths
may observe rowcount=0/no row only as explicit optional cleanup state, never by
fallback `SELECT` readback.
Old-item representative reselection `UPDATE news_items ... RETURNING items.*`
must also validate optional single-row rowcount evidence: rowcount=0/no row is
only an explicit no-representative-edge cleanup result, and rowcount=1/row is
the only valid representative fact refresh before derived item-scoped facts are
cleared or affected-item accounting continues.
Source claim and source disable
`UPDATE news_sources ... RETURNING` paths must also match cursor rowcount to
returned source rows before due-source claim rows, source reconcile rows, or
disable counts are reported. Fetch-run
start must prove rowcount=1 for both the `news_fetch_runs` running-row insert
and matching `news_sources.last_fetch_at_ms` update before a run id is returned;
fetch-run `UPDATE news_fetch_runs ... RETURNING *` finalization must prove
rowcount=1 with a returned run row before `news_sources` status is updated or a
finalized fetch-run row is returned.
Canonical edge-remap cleanup uses the same `RETURNING` rowcount contract:
zero-edge old `news_items` deletes must prove cursor rowcount matches returned
deleted rows before cleanup booleans are returned.
Page-row upserts use the same optional single-row `RETURNING` contract:
rowcount=0 with no row is the only valid unchanged projection result, and
rowcount=1 with a returned `(xmax = 0)` row is the only valid inserted/updated
serving-row result.

## Provider Waves

The runtime-supported News provider types are `rss`, `atom`, `json_feed`,
`cryptopanic`, and `opennews`. `/api/news/sources/status`, `news_fetch`
provider-contract validation, and `/api/status` `news_provider_contract` all
read this static runtime provider-type contract rather than probing the live
provider object or its registry. Provider objects fetch observations; they do
not own capability discovery. Schema provider-type evidence comes from the
`news_sources` database constraint, not from the Python source-classification
enum.

- Wave 1: enable `cryptopanic` where credentials exist; keep it as an
  aggregator or specialist source, not an authority source.
- Wave 2: enable OpenNews only as a provider-fact source. OpenNews is
  REST-only in `news_fetch`: `/open/news_search` is the canonical path for
  `aiRating` and `coins[]` impact facts. The injected REST poster is an
  async-only HTTP contract and is awaited directly. Short-lived OpenNews
  WebSocket subscribe cycles, hybrid fetch mode, and synchronous poster
  compatibility are not runtime surfaces. The synchronous `news_fetch` bridge
  owns only the concrete REST coroutine and closes it directly on active-loop
  misuse; arbitrary awaitable close probing is not part of the provider
  contract. REST scan budgets are source/worker policy, not integration-client
  defaults: `rest_limit` or the worker fetch limit sets page size,
  `max_rest_pages` sets the bounded scan, and `rest_overlap_ms` or durable
  cursor `overlap_ms` sets the replay overlap.
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
- Provider token impacts and provider ratings are evidence, not product truth by
  themselves. A ready provider rating score below 80, or a missing provider
  rating score, blocks LLM item-brief admission to protect budget and freshness.
  `market_scope` is metadata, not a rejection state. Notification eligibility is
  still market-wide and requires a ready, publishable agent brief; provider
  rating alone never makes an external push publishable. A bare ticker/common
  word must not create a market impact without deterministic source-backed
  identity or provider evidence.
- Retired News research tools are not runtime surfaces. Cleanup may keep their
  names only as purge markers for deleting old agent artifacts.
