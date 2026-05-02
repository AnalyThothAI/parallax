# Evidence, Entity, Signal Hardening Design

## Purpose

Build a durable trader-facing intelligence core instead of a search demo. The system must answer, with low latency and auditable evidence:

- What did the public GMGN Twitter stream just say?
- Which watched accounts mentioned a token, CA, cashtag, keyword, hashtag, URL, or narrative term?
- Is a token or keyword gaining mindshare now, compared with its recent baseline?
- What exact tweet proves the signal?

The design deliberately excludes LLM summarization, semantic search, vector storage, and broad AI enrichment from the current product. They are not kept as dormant dependencies, adapters, or placeholder modules.

## First Principles

### 1. Evidence Is The Source Of Truth

Evidence is immutable enough to audit and replay. It includes raw upstream frames, normalized tweet events, canonical event identity, author metadata, text projections, and timing. Evidence must not depend on token resolution, embeddings, LLMs, external APIs, or downstream query workloads.

If evidence cannot be written quickly and deterministically, every higher-level signal is suspect.

### 2. Entity Extraction Is Deterministic

Entities are facts extracted from evidence:

- EVM CA
- Solana CA
- cashtag
- hashtag
- mention
- URL/domain
- configured keyword

Entity extraction must be cheap, local, replayable, and testable. The first version does not infer hidden tickers through LLMs. A token symbol without a CA remains unresolved until deterministic evidence or an explicit registry resolves it.

### 3. Signals Are Materialized Windows

Signals are derived records built from evidence plus entities:

- account token alerts
- account keyword alerts
- token mindshare windows
- keyword mindshare windows

Signals are not summaries. They are compact, queryable, time-windowed metrics with links back to event IDs.

### 4. Search Is Not The Source Of Truth

The runtime store must optimize correctness and hot writes first. Search indexes are projections. Full-text search belongs close to the operational store. Semantic/vector search is outside this design and must not leave dead code in the product.

## Core Architectural Decision

Use SQLite WAL as the operational source of truth. Use SQLite FTS5 for keyword/full-text retrieval. Remove LanceDB from the product, not only from the hot path.

Rationale:

- SQLite WAL provides one local durable database file, transactional writes, concurrent readers, and simple backup.
- SQLite FTS5 provides real full-text search, BM25 ranking, prefix queries, and transactional consistency with the event store.
- The current LanceDB design has shown operational friction for hot writes, file locks, heavy snapshots, and concurrent reads in Docker.
- The trader-critical queries are exact token/entity/window queries and full-text keyword queries, not semantic vector recall.

If semantic search later becomes a proven trader requirement, it needs a new design decision and a fresh implementation. This hardening project does not preserve LanceDB code, dependencies, environment variables, data paths, CLI flags, or projection jobs.

## Non-Goals

- No backward-compatible LanceDB runtime adapter.
- No LanceDB sidecar, dormant projection, or retained dependency.
- No LLM in the ingest path.
- No semantic vector search in the first hardened version.
- No Kafka, Redis, ClickHouse, or multi-service pipeline.
- No attempt to guarantee full Twitter firehose coverage. Coverage remains GMGN anonymous public stream.
- No complex token resolver in the hot path. Deterministic CA extraction is resolved; cashtags remain unresolved unless a CA co-occurs or a local registry entry exists.

## Runtime Shape

Single process:

```text
GMGN Direct WS
  -> CollectorService
  -> IngestService
  -> SQLite WAL
       raw_frames
       events
       event_fts
       event_entities
       account_token_alerts
       account_keyword_alerts
       token_windows
       keyword_windows
  -> PublicWebSocketHub
  -> CLI/API reads
```

One process is intentional. The upstream collector and API currently share an in-memory live push hub. Splitting ingest and API would require a broker or polling layer. That is unnecessary until the operational store and signals are proven.

## Storage Design

### SQLite Pragmas

Every writable connection sets:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
PRAGMA temp_store=MEMORY;
```

Read connections use:

```sql
PRAGMA query_only=ON;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
```

### `schema_migrations`

Tracks applied schema versions.

```sql
CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at_ms INTEGER NOT NULL
);
```

### `raw_frames`

Stores raw upstream frames for audit and replay.

```sql
CREATE TABLE raw_frames (
  frame_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  channel TEXT NOT NULL,
  received_at_ms INTEGER NOT NULL,
  payload_hash TEXT NOT NULL UNIQUE,
  raw_payload_json TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL
);

CREATE INDEX idx_raw_frames_received ON raw_frames(received_at_ms);
CREATE INDEX idx_raw_frames_channel_received ON raw_frames(channel, received_at_ms);
```

### `events`

One normalized Twitter event per logical event.

```sql
CREATE TABLE events (
  event_id TEXT PRIMARY KEY,
  logical_dedup_key TEXT NOT NULL UNIQUE,
  canonical_url TEXT,
  source_provider TEXT NOT NULL,
  source_transport TEXT NOT NULL,
  coverage TEXT NOT NULL,
  channel TEXT NOT NULL,
  action TEXT NOT NULL,
  original_action TEXT,
  tweet_id TEXT,
  internal_id TEXT,
  timestamp_ms INTEGER NOT NULL,
  received_at_ms INTEGER NOT NULL,
  author_handle TEXT,
  author_name TEXT,
  author_avatar TEXT,
  author_followers INTEGER,
  author_tags_json TEXT NOT NULL DEFAULT '[]',
  text TEXT,
  text_raw TEXT,
  text_clean TEXT,
  search_text TEXT,
  urls_json TEXT NOT NULL DEFAULT '[]',
  cashtags_json TEXT NOT NULL DEFAULT '[]',
  hashtags_json TEXT NOT NULL DEFAULT '[]',
  mentions_json TEXT NOT NULL DEFAULT '[]',
  media_json TEXT NOT NULL DEFAULT '[]',
  reference_json TEXT,
  matched_handles_json TEXT NOT NULL DEFAULT '[]',
  is_watched INTEGER NOT NULL DEFAULT 0,
  matched_at_ms INTEGER NOT NULL DEFAULT 0,
  raw_json TEXT NOT NULL,
  event_json TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE INDEX idx_events_received ON events(received_at_ms);
CREATE INDEX idx_events_author_received ON events(author_handle, received_at_ms);
CREATE INDEX idx_events_watched_received ON events(is_watched, received_at_ms);
CREATE INDEX idx_events_tweet_id ON events(tweet_id);
```

### `event_fts`

SQLite FTS5 index for practical keyword search.

```sql
CREATE VIRTUAL TABLE event_fts USING fts5(
  event_id UNINDEXED,
  author_handle,
  text_clean,
  search_text,
  cashtags,
  hashtags,
  mentions,
  tokenize = 'unicode61 remove_diacritics 2'
);
```

The repository inserts or replaces `event_fts` rows in the same transaction as `events`. This gives transactional keyword search without a separate indexing service.

### `event_entities`

Deterministic entities extracted from an event.

```sql
CREATE TABLE event_entities (
  entity_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  entity_type TEXT NOT NULL,
  raw_value TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  chain TEXT,
  token_resolution_status TEXT NOT NULL,
  confidence REAL NOT NULL,
  source TEXT NOT NULL,
  received_at_ms INTEGER NOT NULL,
  author_handle TEXT,
  is_watched INTEGER NOT NULL DEFAULT 0,
  created_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX ux_event_entities_event_type_value_chain
  ON event_entities(event_id, entity_type, normalized_value, COALESCE(chain, ''));
CREATE INDEX idx_event_entities_type_value ON event_entities(entity_type, normalized_value);
CREATE INDEX idx_event_entities_token_window ON event_entities(entity_type, token_resolution_status, received_at_ms);
CREATE INDEX idx_event_entities_watched_window ON event_entities(is_watched, received_at_ms);
```

Allowed `entity_type` values:

- `ca`
- `symbol`
- `hashtag`
- `mention`
- `url`
- `domain`
- `keyword`

### `account_token_alerts`

Materialized low-latency alert when a watched account mentions a token entity.

```sql
CREATE TABLE account_token_alerts (
  alert_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE REFERENCES events(event_id) ON DELETE CASCADE,
  author_handle TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  raw_value TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  chain TEXT,
  token_resolution_status TEXT NOT NULL,
  first_seen_global INTEGER NOT NULL,
  first_seen_by_author INTEGER NOT NULL,
  received_at_ms INTEGER NOT NULL,
  score REAL NOT NULL,
  evidence_json TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL
);

CREATE INDEX idx_account_token_alerts_received ON account_token_alerts(received_at_ms);
CREATE INDEX idx_account_token_alerts_author_received ON account_token_alerts(author_handle, received_at_ms);
CREATE INDEX idx_account_token_alerts_token_received ON account_token_alerts(normalized_value, received_at_ms);
```

### `account_keyword_alerts`

Materialized alert when a watched account mentions a configured keyword, hashtag, domain, or narrative term.

```sql
CREATE TABLE account_keyword_alerts (
  alert_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  author_handle TEXT NOT NULL,
  keyword TEXT NOT NULL,
  source TEXT NOT NULL,
  first_seen_global INTEGER NOT NULL,
  first_seen_by_author INTEGER NOT NULL,
  received_at_ms INTEGER NOT NULL,
  score REAL NOT NULL,
  evidence_json TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX ux_account_keyword_alerts_event_keyword
  ON account_keyword_alerts(event_id, keyword);
CREATE INDEX idx_account_keyword_alerts_received ON account_keyword_alerts(received_at_ms);
CREATE INDEX idx_account_keyword_alerts_keyword_received ON account_keyword_alerts(keyword, received_at_ms);
```

### `token_windows`

Materialized token mindshare windows.

```sql
CREATE TABLE token_windows (
  window_id TEXT PRIMARY KEY,
  window TEXT NOT NULL,
  window_start_ms INTEGER NOT NULL,
  window_end_ms INTEGER NOT NULL,
  entity_type TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  chain TEXT,
  symbol TEXT,
  mention_count INTEGER NOT NULL,
  unique_authors INTEGER NOT NULL,
  watched_mention_count INTEGER NOT NULL,
  weighted_reach REAL NOT NULL,
  market_mindshare REAL NOT NULL,
  watched_mindshare REAL NOT NULL,
  velocity REAL,
  top_authors_json TEXT NOT NULL,
  top_events_json TEXT NOT NULL,
  quality_flags_json TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE INDEX idx_token_windows_window_end ON token_windows(window, window_end_ms);
CREATE INDEX idx_token_windows_entity_window ON token_windows(normalized_value, window, window_end_ms);
```

### `keyword_windows`

Materialized keyword mindshare windows.

```sql
CREATE TABLE keyword_windows (
  window_id TEXT PRIMARY KEY,
  window TEXT NOT NULL,
  window_start_ms INTEGER NOT NULL,
  window_end_ms INTEGER NOT NULL,
  keyword TEXT NOT NULL,
  mention_count INTEGER NOT NULL,
  unique_authors INTEGER NOT NULL,
  watched_mention_count INTEGER NOT NULL,
  weighted_reach REAL NOT NULL,
  market_mindshare REAL NOT NULL,
  watched_mindshare REAL NOT NULL,
  velocity REAL,
  top_authors_json TEXT NOT NULL,
  top_events_json TEXT NOT NULL,
  quality_flags_json TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE INDEX idx_keyword_windows_window_end ON keyword_windows(window, window_end_ms);
CREATE INDEX idx_keyword_windows_keyword_window ON keyword_windows(keyword, window, window_end_ms);
```

## Entity Extraction

The extractor keeps existing CA and cashtag behavior, and adds deterministic non-token entities:

- hashtags from tweet and reference text
- mentions from tweet and reference text
- URLs and domains
- configured keywords from `WATCH_KEYWORDS`

`WATCH_KEYWORDS` is a comma-separated env var. Matching is case-insensitive and word-boundary based for ASCII terms. Non-ASCII terms use normalized substring matching.

No inferred token symbol resolution is performed in the hot path. If a cashtag appears without a CA, it is a `symbol` entity with `token_resolution_status = 'unresolved'`.

## Signal Rules

### Account Token Alert

Create an alert when:

- event is watched (`is_watched = 1`)
- event has at least one `ca` or `symbol` entity

Fields:

- `first_seen_global`: no earlier event entity has same `entity_type`, `normalized_value`, and `chain`
- `first_seen_by_author`: no earlier event entity has same identity and same `author_handle`
- `score`: deterministic priority score

Initial score:

```text
score =
  50
  + 25 if first_seen_by_author
  + 15 if first_seen_global
  + min(20, log10(author_followers + 1) * 3)
  + 10 if entity_type == 'ca'
```

### Account Keyword Alert

Create an alert when:

- event is watched
- event contains a configured keyword, hashtag, or domain entity

Initial score:

```text
score =
  40
  + 20 if first_seen_by_author
  + 10 if first_seen_global
  + min(20, log10(author_followers + 1) * 3)
```

### Token Windows

Windows are computed for:

- `1m`
- `5m`
- `1h`
- `24h`

Metrics:

- `mention_count`
- `unique_authors`
- `watched_mention_count`
- `weighted_reach = sum(log10(author_followers + 1))`
- `market_mindshare = token mentions / all token entity mentions in window`
- `watched_mindshare = watched token mentions / all watched token entity mentions in window`
- `velocity = (current mention_count - previous mention_count) / max(previous mention_count, 1)`
- `top_authors`
- `top_events`

### Keyword Windows

Same structure as token windows, with denominator based on keyword/domain/hashtag entities.

## WebSocket Output

The public `/ws` event payload should include deterministic signal fields for live consumers:

```json
{
  "type": "event",
  "event": {},
  "entities": {
    "tokens": [],
    "keywords": [],
    "hashtags": [],
    "mentions": [],
    "domains": []
  },
  "alerts": {
    "account_token_alerts": [],
    "account_keyword_alerts": []
  }
}
```

This allows a downstream trading workflow to immediately react without re-querying the database.

## CLI Output

Add or preserve these trader-oriented commands:

```bash
gmgn-twitter-intel recent --limit 20
gmgn-twitter-intel search "base stablecoin" --limit 20
gmgn-twitter-intel token-flow --window 5m --limit 20
gmgn-twitter-intel account-alerts --window 24h --limit 50
gmgn-twitter-intel keyword-flow --window 1h --limit 20
```

`mindshare` should be replaced or reworked into `token-flow`. The name `mindshare` can remain as an alias only if it calls the same implementation; no separate compatibility path.

## Readiness And Health

`/readyz` must include:

- DB open and migration status
- collector task status
- last upstream frame age
- last normalized event age
- write error count
- signal builder error count

It returns HTTP 503 if:

- migrations are incomplete
- collector task stopped
- no upstream frames after stale timeout
- no normalized event after stale timeout while frames are arriving
- SQLite write probe fails

## Operational Model

Docker Compose stores SQLite in `/data/twitter_intel.sqlite3` on a named volume.

Backups use SQLite online backup, not file copying:

```bash
sqlite3 /data/twitter_intel.sqlite3 ".backup '/data/backups/twitter_intel-YYYYMMDD-HHMMSS.sqlite3'"
```

No raw `cp -a` snapshot of a hot store is part of normal operations.

## Cutover Strategy

This is a breaking cutover. LanceDB compatibility is removed from runtime and repository code.

Acceptable options:

1. Clean start with SQLite WAL.
2. One-time offline export/import outside the application runtime.

The application should not carry a LanceDB adapter, projection job, dual-write mode, retained dependency, environment variable, or automatic migration path.

## Testing Strategy

Required test coverage:

- SQLite schema bootstraps on empty database.
- SQLite FTS5 is available and can match inserted event text.
- Evidence insert is idempotent by `event_id` and `logical_dedup_key`.
- Raw frame insert is idempotent by payload hash.
- Entity extraction covers CA, Solana CA, cashtag, hashtag, mention, URL/domain, configured keyword.
- Account token alerts detect first seen globally and by author.
- Account keyword alerts detect first seen globally and by author.
- Token windows compute count, unique authors, weighted reach, market mindshare, watched mindshare, and velocity.
- WebSocket replay includes entities and alerts.
- `/readyz` fails when DB probe fails or collector is stale.

## Success Criteria

The hardened system is acceptable when:

- Ingest can run for 12 hours without LanceDB file lock/query contention.
- `recent`, `search`, `token-flow`, and `account-alerts` work while ingest is active.
- A watched account mentioning a CA or cashtag produces an account token alert in the same event payload.
- A watched account mentioning a configured keyword produces an account keyword alert in the same event payload.
- Token window metrics are reproducible from stored evidence and entities.
- Restarting the service does not require rebuilding indexes manually.
- Removing LanceDB from runtime does not remove full-text search capability because SQLite FTS5 covers it.
- The repository contains no LanceDB runtime module, dependency, config surface, or future-use placeholder.
