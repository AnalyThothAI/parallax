# Architecture

Parallax is one Python service, one CLI, one React console, and one PostgreSQL
database. It follows Kappa/CQRS: material facts are written once, while
rebuildable read models and immutable research publications remain derived
state with explicit single-writer ownership.

## Data flow

```text
providers / public streams
  -> ingestion adapters
  -> PostgreSQL material facts
  -> durable dirty targets or bounded catch-up
  -> single-writer read models or immutable publications
  -> HTTP / WebSocket / CLI
```

Workers recover exclusively from PostgreSQL state through bounded `interval_seconds` catch-up. There is no database wake plane or in-memory correctness dependency.

## Truth and derived state

Material business truth includes:

- Evidence: `raw_frames`, `events`, `event_entities`.
- Identity: `token_evidence`, `token_intents`, `token_intent_lookup_keys`, `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence`, `asset_identity_current`.
- Market: `market_ticks`, `enriched_events`.
- News: `news_provider_items`, `news_items`, story membership/entity/fact edges.
- Macro: `macro_observations`.
- Notification input/output facts: `account_token_alerts`, `notifications`; external delivery state remains in `notification_deliveries`.

Current read models include `token_radar_current_rows`,
`token_profile_current`, `market_tick_current`, and `news_page_rows`. They have
stable product keys, exactly one runtime writer, and zero writes when their
business payload is unchanged.

`macro_research_publications` is immutable derived research keyed by completed
U.S. session. `macro_research_runs` owns only the durable session lifecycle,
lease, retry, frozen cutoff, and sanitized failure state. Neither table is
material Macro truth, and the public read never reconstructs a publication from
facts.

Queues, leases, publication state, sync attempts, provider fetch attempts, and terminal-event rows are control or audit state. They are not alternate business truth.

## Package boundaries

```text
domains/*       business facts, policies, repositories, read models, workers
integrations/*  provider and external-system adapters
platform/*      configuration, PostgreSQL, telemetry, generic worker kernel
app/runtime/*   composition, factories, scheduler, provider wiring
app/operations  authenticated operator application queries/commands
app/surfaces/*  HTTP, WebSocket, and CLI transport adapters
```

Dependency rules:

- Domains do not import `parallax.app`.
- Runtime composition does not import transport surfaces.
- Surfaces may call application/runtime services but do not become business-rule owners.
- Provider objects enter domains through declared protocols or bundles.
- `platform/runtime/worker_base.py` owns the generic loop; domain workers own their queue and state machine.

These rules are enforced by `tests/architecture/test_kiss_runtime_invariants.py`.

## Transaction ownership

Application services and workers own transaction scope. Repository write methods execute SQL on the supplied connection; they do not expose `commit` switches or open implicit transactions.

Important atomic units are:

- event fact, identity resolution, market capture, enriched event, and downstream dirty target;
- Token Radar private edges/features, current rows, publication state, and queue acknowledgement;
- a read-model replacement/current upsert and its queue acknowledgement;
- one immutable Macro publication insertion and its run completion;
- notification creation and delivery-row activation;
- terminalization or retry transition plus its source queue mutation.

Provider, subprocess, filesystem, and network I/O stays outside database
transactions. External delivery follows load/claim -> close transaction -> I/O
-> compare-and-set complete/fail.

## Product read models and publications

### Market Current

`market_tick_current` is a transactionally maintained index over append-only
`market_ticks`: a newly inserted fact, monotonic current advance, and downstream
Radar dirty enqueue share one transaction. It has no projection worker or dirty
queue. Recovery remains CQRS-rebuildable through the explicit bounded
`ops rebuild-market-current` application operation, which scans stable target
keys in the fact tape and uses the same current-write service.

### Token Radar

```text
events + intents + resolutions + market facts
  -> token_radar_dirty_targets
  -> rank source edges + compact target features
  -> token_radar_current_rows + token_radar_publication_state
  -> Radar, search, token case, notifications
```

There is one target queue. Generic projection run/offset ledgers and the
source-event dirty queue are retired. The public row is a transparent
`factor_snapshot` built only from persisted identity, social, and market facts.

### News

```text
configured sources
  -> fetch ledger + provider items + canonical news facts
  -> deterministic item processing
  -> page dirty targets
  -> fact-only page current rows
```

`page` is the only News dirty-target kind. The page projection contains source,
story-membership, entity-resolution, fact-candidate, provider-rating, content,
and market-scope fields already present in PostgreSQL. Source health is current
state on `news_sources`; deterministic terminal failures are tied to
`config_payload_hash` and resume only after the source configuration changes.

### Macro

```text
macro_sync_windows
  -> provider bundle
  -> macro_observations + macro_sync_runs
  -> GET /api/macro/evidence/{view_id} -> /macro + six live detail routes
  -> completed-session macro_research_runs
  -> one DeepAgents research graph over a frozen evidence scope
  -> one immutable macro_research_publications row
  -> GET /api/macro/research -> /macro/research
```

`macro_observations` remains the only Macro evidence truth. Each research run
freezes one completed-session identity, market-close cutoff, and seal time.
Pageable tools expose only observations and eligible persisted News that were
available inside that scope, plus prior immutable Macro publications. The
DeepAgent owns its todo plan, evidence selection, virtual-filesystem notes,
specialist delegation, counterevidence, section structure, gaps, review, and
Chinese narrative. Parallax does not prescribe a risk taxonomy, forecast
horizon, readiness state, direction, confidence, or conclusion.

The live evidence read is a separate request-time projection over bounded
persisted history. The original 108 concepts and six categories are
presentation metadata, not an Agent allowlist or stored read model.
Uncatalogued facts remain visible on the dashboard. Transparent differences,
returns, spreads, accounting identities, and correlations may be computed with
formula/window/sample provenance; they never become semantic labels or gates.
Observation/source time, ingestion time, request read time, and read health
remain separate.

Search tools return compact, offset-pageable evidence identities. Exact reads
retain the complete evidence record; native DeepAgents filesystem middleware
offloads large tool results into checkpoint-backed `/large_tool_results/` for
progressive `read_file` access. The application does not discard raw evidence
or fail the graph at an arbitrary payload threshold. Search pages have a
bounded per-call size but no application-owned total-depth cap.

The production DeepAgents backend is a native `CompositeBackend`: ordinary
virtual files and large-result artifacts use `StateBackend` and therefore the
PostgreSQL checkpoint, while `/workspace/` and `execute` share a per-scope
calculation directory under the operator app home. Parallax registers no
permissions, approval middleware, tool exclusion, or semantic safety gate.
Calculations can transform disclosed evidence but do not create a second
market-fact source.

Application code owns only calendar and cutoff mechanics, scheduling, leases,
retries, evidence visibility, the structured storage envelope, citation
referential integrity, and atomic persistence. Model and tool I/O occurs
outside database write transactions. A publication and the transition of its
run to `published` share one transaction. The session key and database trigger
make publication immutable; replaying a published session performs no model
call and no serving write.

DeepAgents receives a production PostgreSQL checkpointer. The frozen scope ID
is the stable graph `thread_id`, so retries resume durable agent state after a
process restart instead of depending on memory. Checkpoint storage is execution
state, not business evidence and not a second publication source.

### Model-execution boundary

The only production product-model consumer is the `macro_research` worker
factory and its Macro-owned DeepAgents adapter. There is no generic Parallax
model gateway, workflow DSL, semantic gate layer, or alternate model execution
path. News, Token, other workers, status, HTTP reads, and the frontend
instantiate no model consumer. The frontend reads persisted facts or immutable
research; an HTTP request never invokes the graph.

### Evidence watchlist and account alerts

Watchlist timeline/cluster queries are Evidence read models. The unsupported `signal` scope and fixed-zero signal metrics are removed. `account_token_alerts` remains a real ingest output consumed by notifications; the stale Account Quality scoring/profile control plane is removed.

## Deliberate safety boundary

`events.raw_json` and `events.event_json` are still present because historical events do not yet have a proven one-to-one `raw_frames` source edge and locator. They must not be deleted until new writes persist that edge, historical coverage is verified at 100%, and ambiguous payloads are exported to immutable evidence. No runtime fallback layer should be added in the meantime.

## Authoritative references

- Worker ownership, reliability, and diagnosis: `docs/OPERATIONS.md`
- Public surfaces: `docs/CONTRACTS.md`
- PostgreSQL diagnostics: `docs/references/POSTGRES_PERFORMANCE.md`
- Frontend boundaries: `docs/FRONTEND.md`
