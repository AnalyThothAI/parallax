# Evidence Entity Signal Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove LanceDB from the current product and replace the runtime with a SQLite WAL + FTS5 operational core that makes evidence, entity extraction, and trading signals durable, queryable, and low-latency.

**Architecture:** SQLite WAL becomes the source of truth for raw frames, normalized events, deterministic entities, full-text search, alerts, and signal windows. LanceDB, embedding, and LLM enrichment are removed from code, dependencies, configuration, and Docker surfaces rather than preserved for compatibility or future use. The service stays single-process and KISS: GMGN WS collector, transactional ingest, SQLite-backed queries, and WebSocket live push.

**Tech Stack:** Python 3.13, stdlib `sqlite3`, SQLite WAL, SQLite FTS5, FastAPI, websockets, pydantic-settings, pytest, ruff.

---

## Spec Reference

Implement this plan against:

`docs/superpowers/specs/2026-05-02-evidence-entity-signal-hardening-design.md`

## File Map

### Create

- `src/gmgn_twitter_intel/storage/sqlite_schema.py`
  Owns schema SQL, migrations, and FTS5 capability check.

- `src/gmgn_twitter_intel/storage/sqlite_client.py`
  Owns connection creation, WAL pragmas, transaction context manager, read/write connection helpers, and row decoding.

- `src/gmgn_twitter_intel/storage/evidence_repository.py`
  Owns raw frame and normalized event persistence, FTS row writes, recent/search/count queries.

- `src/gmgn_twitter_intel/storage/entity_repository.py`
  Owns event entity persistence and entity lookups for tokens, keywords, authors, and windows.

- `src/gmgn_twitter_intel/storage/signal_repository.py`
  Owns account alerts and window upserts/queries.

- `src/gmgn_twitter_intel/pipeline/entity_extractor.py`
  Replaces token-only extraction with deterministic extraction for CA, symbol, hashtag, mention, URL/domain, and configured keywords.

- `src/gmgn_twitter_intel/pipeline/signal_builder.py`
  Builds account token alerts, account keyword alerts, token windows, and keyword windows.

- `src/gmgn_twitter_intel/retrieval/token_flow_service.py`
  Query service for token flow windows and ranked token activity.

- `src/gmgn_twitter_intel/retrieval/account_alert_service.py`
  Query service for watched-account token/keyword alerts.

- `tests/test_sqlite_schema.py`
- `tests/test_evidence_repository.py`
- `tests/test_entity_extractor.py`
- `tests/test_signal_builder.py`
- `tests/test_token_flow_service.py`
- `tests/test_account_alert_service.py`

### Modify

- `src/gmgn_twitter_intel/settings.py`
  Replace LanceDB settings with SQLite path and keyword watchlist.

- `src/gmgn_twitter_intel/runtime_paths.py`
  Default DB path becomes `~/.gmgn-twitter-intel/twitter_intel.sqlite3`.

- `src/gmgn_twitter_intel/collector/service.py`
  Use the new ingest repository flow and return entities/alerts for live publish.

- `src/gmgn_twitter_intel/api/app.py`
  Build SQLite repositories, readiness DB probe, and WebSocket hub.

- `src/gmgn_twitter_intel/api/ws.py`
  Replay and live payloads include entities and alerts.

- `src/gmgn_twitter_intel/cli.py`
  Replace LanceDB commands with SQLite-backed `recent`, `search`, `token-flow`, `account-alerts`, and `keyword-flow`.

- `src/gmgn_twitter_intel/retrieval/search_service.py`
  Use SQLite exact lookups and FTS5 BM25 instead of hash embeddings/ranking over all rows.

- `src/gmgn_twitter_intel/retrieval/mindshare_service.py`
  Replace or delete in favor of `token_flow_service.py`. Keep no separate compatibility implementation.

- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `compose.yaml`
- `Dockerfile`
- `Makefile`
- `pyproject.toml`
- `tests/test_project_structure.py`
- `tests/test_cli.py`
- `tests/test_api_health.py`
- `tests/test_api_websocket.py`

### Delete

- `src/gmgn_twitter_intel/storage/lancedb_client.py`
- `src/gmgn_twitter_intel/storage/lancedb_schema.py`
- `src/gmgn_twitter_intel/storage/runtime_bootstrap.py`
- `src/gmgn_twitter_intel/storage/tweet_repository.py`
- `src/gmgn_twitter_intel/storage/social_repository.py`
- `src/gmgn_twitter_intel/storage/llm_repository.py`
- `src/gmgn_twitter_intel/pipeline/embedding.py`
- `src/gmgn_twitter_intel/pipeline/llm_enrichment.py`
- `src/gmgn_twitter_intel/retrieval/ranking.py`

Remove dependencies from `pyproject.toml` if no remaining code imports them:

- `lancedb`
- `pyarrow`
- `litellm`
- `openai` if only pulled by LiteLLM

---

## Task 1: Add SQLite Schema And Connection Core

**Files:**

- Create: `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- Create: `src/gmgn_twitter_intel/storage/sqlite_client.py`
- Test: `tests/test_sqlite_schema.py`

- [ ] **Step 1: Write failing schema bootstrap test**

Create `tests/test_sqlite_schema.py` with tests that bootstrap an empty DB and assert core tables plus FTS5 exist.

Expected test shape:

```python
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate


def test_sqlite_schema_bootstraps_core_tables(tmp_path):
    db_path = tmp_path / "twitter_intel.sqlite3"
    conn = connect_sqlite(db_path, read_only=False)
    try:
        migrate(conn)
        names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "schema_migrations" in names
    assert "raw_frames" in names
    assert "events" in names
    assert "event_entities" in names
    assert "account_token_alerts" in names
    assert "account_keyword_alerts" in names
    assert "token_windows" in names
    assert "keyword_windows" in names


def test_sqlite_fts5_matches_inserted_text(tmp_path):
    db_path = tmp_path / "twitter_intel.sqlite3"
    conn = connect_sqlite(db_path, read_only=False)
    try:
        migrate(conn)
        conn.execute(
            "INSERT INTO event_fts(event_id, author_handle, text_clean, search_text, cashtags, hashtags, mentions) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("event-1", "toly", "stablecoin on base", "stablecoin on base", "", "", ""),
        )
        rows = conn.execute(
            "SELECT event_id FROM event_fts WHERE event_fts MATCH ?",
            ("stablecoin",),
        ).fetchall()
    finally:
        conn.close()

    assert [row["event_id"] for row in rows] == ["event-1"]
```

- [ ] **Step 2: Run failing test**

Run:

```bash
uv run python -m pytest tests/test_sqlite_schema.py -q
```

Expected: fails because `sqlite_client` and `sqlite_schema` do not exist.

- [ ] **Step 3: Implement SQLite client**

Create `src/gmgn_twitter_intel/storage/sqlite_client.py` with:

- `connect_sqlite(path: Path, read_only: bool = False) -> sqlite3.Connection`
- WAL pragmas for writable connections
- query-only pragmas for read-only connections
- `row_factory = sqlite3.Row`
- `transaction(conn)` context manager that commits or rolls back

- [ ] **Step 4: Implement schema migrations**

Create `src/gmgn_twitter_intel/storage/sqlite_schema.py` with:

- `SCHEMA_VERSION = 1`
- `migrate(conn)`
- `ensure_fts5_available(conn)`
- table SQL from the design spec
- indexes from the design spec
- insert into `schema_migrations`

Use `CREATE TABLE IF NOT EXISTS` and `CREATE VIRTUAL TABLE IF NOT EXISTS`.

- [ ] **Step 5: Verify schema tests pass**

Run:

```bash
uv run python -m pytest tests/test_sqlite_schema.py -q
```

Expected: pass.

---

## Task 2: Replace LanceDB Runtime Settings With SQLite Settings

**Files:**

- Modify: `src/gmgn_twitter_intel/settings.py`
- Modify: `src/gmgn_twitter_intel/runtime_paths.py`
- Modify: `tests/test_settings.py`
- Modify: `tests/test_project_structure.py`

- [ ] **Step 1: Write failing settings tests**

Update tests to expect:

- default DB path `twitter_intel.sqlite3`
- `SQLITE_PATH` override
- `WATCH_KEYWORDS` parsing
- no public `LANCEDB_PATH`

Expected assertions:

```python
assert settings.sqlite_path == app_home / "twitter_intel.sqlite3"
assert settings.watch_keywords == ("listing", "airdrop", "mainnet")
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
uv run python -m pytest tests/test_settings.py tests/test_project_structure.py -q
```

Expected: fail because current settings still expose LanceDB path.

- [ ] **Step 3: Implement settings changes**

In `settings.py`:

- Add `sqlite_path_override: Path | None = Field(default=None, validation_alias="SQLITE_PATH")`
- Add `watch_keywords: tuple[str, ...] = Field(default_factory=tuple, validation_alias="WATCH_KEYWORDS")`
- Add `sqlite_path` property.
- Remove `lancedb_path_override`, `embedding_dim`, `llm_model`, and LanceDB-specific settings.

In `runtime_paths.py`:

- Add `sqlite_path(app_home_override: Path | None = None) -> Path`
- Return `app_home(...) / "twitter_intel.sqlite3"`.

- [ ] **Step 4: Verify settings tests pass**

Run:

```bash
uv run python -m pytest tests/test_settings.py tests/test_project_structure.py -q
```

Expected: pass.

---

## Task 3: Build Deterministic Entity Extractor

**Files:**

- Create: `src/gmgn_twitter_intel/pipeline/entity_extractor.py`
- Modify or remove: `src/gmgn_twitter_intel/pipeline/token_extractor.py`
- Test: `tests/test_entity_extractor.py`

- [ ] **Step 1: Write failing extractor tests**

Test cases:

- EVM CA becomes `entity_type="ca"`, `chain="eth"`, resolved.
- Solana CA becomes `entity_type="ca"`, `chain="solana"`, resolved.
- `$PEPE` becomes `entity_type="symbol"`, unresolved.
- `#Base` becomes `hashtag`.
- `@toly` becomes `mention`.
- URL becomes both `url` and `domain`.
- `WATCH_KEYWORDS=listing,airdrop` matches text case-insensitively.

- [ ] **Step 2: Run failing extractor tests**

Run:

```bash
uv run python -m pytest tests/test_entity_extractor.py -q
```

Expected: fail until the new extractor exists.

- [ ] **Step 3: Implement entity extractor**

Create:

- `Entity` dataclass with fields from `event_entities`.
- `extract_entities(text: str | None, reference_text: str | None, watch_keywords: tuple[str, ...]) -> list[Entity]`
- `normalize_entity_key(entity)`

Reuse proven CA regex logic from `token_extractor.py`, then remove duplicated old token-only extraction after repositories migrate.

- [ ] **Step 4: Verify extractor tests pass**

Run:

```bash
uv run python -m pytest tests/test_entity_extractor.py -q
```

Expected: pass.

---

## Task 4: Implement Evidence Repository

**Files:**

- Create: `src/gmgn_twitter_intel/storage/evidence_repository.py`
- Test: `tests/test_evidence_repository.py`

- [ ] **Step 1: Write failing evidence repository tests**

Test:

- `insert_raw_frame` is idempotent by payload hash.
- `insert_event` is idempotent by `event_id`.
- different event IDs with same logical dedup key do not duplicate evidence.
- insert writes `event_fts`.
- `recent_events(limit=...)` returns newest first.
- `search_text("stablecoin")` uses FTS and returns expected event.

- [ ] **Step 2: Run failing tests**

Run:

```bash
uv run python -m pytest tests/test_evidence_repository.py -q
```

Expected: fail.

- [ ] **Step 3: Implement repository**

Create `EvidenceRepository`:

- `insert_raw_frame(source, channel, received_at_ms, raw_payload_json) -> bool`
- `insert_event(event, is_watched, matched_handles, entities) -> bool`
- `recent_events(limit, handles=None, matched_only=False) -> list[dict]`
- `search_events(query, limit, matched_only=False) -> list[dict]`
- `event_counts() -> dict`
- `health_probe() -> bool`

All event and FTS writes occur in one SQLite transaction.

- [ ] **Step 4: Verify evidence tests pass**

Run:

```bash
uv run python -m pytest tests/test_evidence_repository.py -q
```

Expected: pass.

---

## Task 5: Implement Entity Repository

**Files:**

- Create: `src/gmgn_twitter_intel/storage/entity_repository.py`
- Test: `tests/test_evidence_repository.py`
- Test: `tests/test_entity_extractor.py`

- [ ] **Step 1: Add failing entity persistence tests**

Add tests for:

- inserting multiple entity types for one event
- uniqueness by event/type/value/chain
- querying token entities by CA
- querying symbol entities by symbol
- querying keyword entities by keyword

- [ ] **Step 2: Implement entity repository**

Create `EntityRepository`:

- `insert_entities(event_id, entities, received_at_ms, author_handle, is_watched)`
- `entities_for_event(event_id)`
- `events_for_entity(entity_type, normalized_value, chain=None, start_ms=None, end_ms=None)`
- `symbol_ca_candidates(symbol)`

- [ ] **Step 3: Verify entity persistence tests**

Run:

```bash
uv run python -m pytest tests/test_evidence_repository.py tests/test_entity_extractor.py -q
```

Expected: pass.

---

## Task 6: Implement Signal Builder And Signal Repository

**Files:**

- Create: `src/gmgn_twitter_intel/pipeline/signal_builder.py`
- Create: `src/gmgn_twitter_intel/storage/signal_repository.py`
- Test: `tests/test_signal_builder.py`

- [ ] **Step 1: Write failing signal tests**

Test:

- watched account plus CA creates account token alert.
- watched account plus cashtag creates account token alert.
- watched account plus keyword creates account keyword alert.
- first seen global is true only for the first mention of an entity.
- first seen by author is true only for that author's first mention.
- token window computes mention count, unique authors, watched mentions, weighted reach, market mindshare, watched mindshare, and velocity.

- [ ] **Step 2: Implement signal repository**

Create:

- `insert_account_token_alert(...)`
- `insert_account_keyword_alert(...)`
- `upsert_token_window(...)`
- `upsert_keyword_window(...)`
- `recent_account_alerts(window_ms, limit)`
- `token_flow(window, limit)`
- `keyword_flow(window, limit)`

- [ ] **Step 3: Implement signal builder**

Create `SignalBuilder`:

- `build_event_alerts(event_row, entities) -> dict`
- `refresh_token_windows(windows=("1m", "5m", "1h", "24h"), now_ms=None)`
- `refresh_keyword_windows(windows=("1m", "5m", "1h", "24h"), now_ms=None)`

Keep window refresh simple: recompute complete current and previous windows from SQLite queries. Do not create incremental state yet.

- [ ] **Step 4: Verify signal tests pass**

Run:

```bash
uv run python -m pytest tests/test_signal_builder.py -q
```

Expected: pass.

---

## Task 7: Rewire Collector To Store Evidence, Entities, And Signals

**Files:**

- Modify: `src/gmgn_twitter_intel/collector/service.py`
- Modify: `src/gmgn_twitter_intel/api/app.py`
- Test: `tests/test_collector_service.py`
- Test: `tests/test_api_health.py`

- [ ] **Step 1: Write failing collector test**

Add a test that feeds a watched account tweet containing `$PEPE listing` and asserts:

- event inserted
- symbol entity inserted
- keyword entity inserted
- account token alert inserted
- account keyword alert inserted
- publisher receives event payload with entities and alerts

- [ ] **Step 2: Replace repository dependency**

Replace old `TweetRepository` usage with a new `IngestService` or direct repositories:

- evidence repository
- entity repository
- signal builder/repository

Store-first remains mandatory:

```text
parse -> raw frame -> normalized event -> entities -> alerts -> publish
```

- [ ] **Step 3: Update readiness DB probe**

`/readyz` must call a SQLite health probe and return 503 if it fails.

- [ ] **Step 4: Verify collector and health tests**

Run:

```bash
uv run python -m pytest tests/test_collector_service.py tests/test_api_health.py -q
```

Expected: pass.

---

## Task 8: Rewire WebSocket Replay And Live Payloads

**Files:**

- Modify: `src/gmgn_twitter_intel/api/ws.py`
- Test: `tests/test_api_websocket.py`

- [ ] **Step 1: Write failing WebSocket tests**

Test:

- subscribe by handle replays events with `entities` and `alerts`.
- subscribe by symbol replays matching token events.
- live publish includes account token alerts for watched account token mention.
- invalid symbol ambiguity returns an error.

- [ ] **Step 2: Implement enriched payload**

The live/replay message shape is:

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

- [ ] **Step 3: Verify WebSocket tests**

Run:

```bash
uv run python -m pytest tests/test_api_websocket.py -q
```

Expected: pass.

---

## Task 9: Replace Search With SQLite Exact + FTS5

**Files:**

- Modify: `src/gmgn_twitter_intel/retrieval/search_service.py`
- Delete: `src/gmgn_twitter_intel/retrieval/ranking.py`
- Test: `tests/test_search_service.py`

- [ ] **Step 1: Write failing search tests**

Test:

- CA query uses entity exact lookup.
- symbol query uses entity exact lookup.
- handle query uses events index.
- text query uses FTS5.
- matched scope limits results to watched events.

- [ ] **Step 2: Implement SQLite-backed search**

Remove hash embedding search. FTS query uses:

```sql
SELECT e.*, bm25(event_fts) AS score
FROM event_fts
JOIN events e ON e.event_id = event_fts.event_id
WHERE event_fts MATCH ?
ORDER BY score
LIMIT ?
```

- [ ] **Step 3: Verify search tests**

Run:

```bash
uv run python -m pytest tests/test_search_service.py -q
```

Expected: pass.

---

## Task 10: Add Token Flow And Account Alert Services

**Files:**

- Create: `src/gmgn_twitter_intel/retrieval/token_flow_service.py`
- Create: `src/gmgn_twitter_intel/retrieval/account_alert_service.py`
- Test: `tests/test_token_flow_service.py`
- Test: `tests/test_account_alert_service.py`

- [ ] **Step 1: Write failing service tests**

Token flow test:

- insert token windows
- query `window="5m"`
- results sorted by watched mentions, velocity, then mention count

Account alert test:

- insert token and keyword alerts
- query `window="24h"`
- filter by author
- filter by alert type

- [ ] **Step 2: Implement query services**

`TokenFlowService.token_flow(window, limit)` returns:

- token identity
- mention count
- watched mention count
- velocity
- market mindshare
- watched mindshare
- top authors
- top events

`AccountAlertService.account_alerts(window, limit, handles=None, alert_type=None)` returns:

- alert metadata
- event evidence
- entity details
- first seen flags

- [ ] **Step 3: Verify service tests**

Run:

```bash
uv run python -m pytest tests/test_token_flow_service.py tests/test_account_alert_service.py -q
```

Expected: pass.

---

## Task 11: Rebuild CLI Around Trader Workflows

**Files:**

- Modify: `src/gmgn_twitter_intel/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Expected commands:

```bash
gmgn-twitter-intel recent --limit 20
gmgn-twitter-intel search "base stablecoin" --limit 20
gmgn-twitter-intel token-flow --window 5m --limit 20
gmgn-twitter-intel account-alerts --window 24h --limit 50
gmgn-twitter-intel keyword-flow --window 1h --limit 20
gmgn-twitter-intel ops rebuild-windows --window 5m
```

- [ ] **Step 2: Remove obsolete CLI commands**

Remove:

- `embed`
- `enrich`
- `resolve-token` if it depends on external token registry runtime
- LanceDB-specific `ops rebuild-indexes`
- LanceDB store path options

- [ ] **Step 3: Implement SQLite CLI**

Use `SQLITE_PATH` or default runtime path. Emit compact JSON with `ok`, `data`, and `error`.

- [ ] **Step 4: Verify CLI tests**

Run:

```bash
uv run python -m pytest tests/test_cli.py -q
```

Expected: pass.

---

## Task 12: Remove LanceDB, Embedding, And LLM Runtime Code

**Files:**

- Delete LanceDB/embedding/LLM files listed in the File Map.
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `tests/test_project_structure.py`

- [ ] **Step 1: Delete obsolete modules**

Remove files:

```text
src/gmgn_twitter_intel/storage/lancedb_client.py
src/gmgn_twitter_intel/storage/lancedb_schema.py
src/gmgn_twitter_intel/storage/runtime_bootstrap.py
src/gmgn_twitter_intel/storage/tweet_repository.py
src/gmgn_twitter_intel/storage/social_repository.py
src/gmgn_twitter_intel/storage/llm_repository.py
src/gmgn_twitter_intel/pipeline/embedding.py
src/gmgn_twitter_intel/pipeline/llm_enrichment.py
src/gmgn_twitter_intel/retrieval/ranking.py
```

- [ ] **Step 2: Remove dependencies**

Update `pyproject.toml` dependencies:

- remove `lancedb`
- remove `pyarrow`
- remove `litellm`
- remove `openai` if no longer pulled by another dependency

Run:

```bash
uv sync
```

- [ ] **Step 3: Verify no stale imports**

Run:

```bash
rg -n "lancedb|LanceDB|pyarrow|litellm|llm_enrichment|embedding|HashEmbedding|TweetRepository|SocialRepository|LlmRepository" src tests README.md AGENTS.md CLAUDE.md pyproject.toml compose.yaml Dockerfile Makefile
```

Expected: no matches. Do not keep LanceDB references in docs as future-use placeholders.

- [ ] **Step 4: Verify no LanceDB data/config surface remains**

Run:

```bash
rg -n "LANCEDB_PATH|EMBEDDING_DIM|LANCE_|RAYON_|twitter_intel\\.lancedb|rebuild-indexes|vector|semantic projection" src tests README.md AGENTS.md CLAUDE.md pyproject.toml compose.yaml Dockerfile Makefile
```

Expected: no matches.

- [ ] **Step 5: Verify project structure tests**

Run:

```bash
uv run python -m pytest tests/test_project_structure.py -q
```

Expected: pass.

---

## Task 13: Update Docker, Docs, And Ops

**Files:**

- Modify: `compose.yaml`
- Modify: `Dockerfile`
- Modify: `Makefile`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update compose**

Set:

- `GMGN_TWITTER_HOME=/data`
- no LanceDB env vars
- no Lance thread env vars
- named volume `/data`
- healthcheck calls `/readyz`

- [ ] **Step 2: Update docs**

Document:

- SQLite WAL is source of truth.
- FTS5 powers search.
- no legacy vector-store env vars, paths, CLI flags, or future-use notes.
- `WATCH_KEYWORDS`.
- CLI trader workflows.
- Docker volume and SQLite backup command.

- [ ] **Step 3: Verify docs commands**

Run:

```bash
uv run gmgn-twitter-intel config
uv run python -m compileall src tests
```

Expected: both pass.

---

## Task 14: Full Verification And Docker Smoke Test

**Files:**

- No new files unless tests reveal missed imports.

- [ ] **Step 1: Run full local verification**

Run:

```bash
uv run python -m pytest -q
uv run ruff check .
uv run python -m compileall src tests
```

Expected:

- all tests pass
- ruff passes
- compileall passes

- [ ] **Step 2: Run Docker build**

Run:

```bash
docker compose up -d --build app
```

Expected: container starts and becomes healthy.

- [ ] **Step 3: Verify live readiness**

Run:

```bash
curl -fsS http://127.0.0.1:8765/readyz
```

Expected:

```json
{
  "ok": true,
  "reasons": []
}
```

- [ ] **Step 4: Verify trader commands**

Run:

```bash
docker compose exec -T app gmgn-twitter-intel recent --limit 5
docker compose exec -T app gmgn-twitter-intel token-flow --window 5m --limit 10
docker compose exec -T app gmgn-twitter-intel account-alerts --window 24h --limit 10
docker compose exec -T app gmgn-twitter-intel search stablecoin --limit 5
```

Expected:

- each returns valid JSON
- no SQLite lock errors
- no LanceDB references

- [ ] **Step 5: Observe 10 minutes of ingest**

Run:

```bash
sleep 600
curl -fsS http://127.0.0.1:8765/readyz
docker compose logs --tail=100 app
```

Expected:

- collector frame count increases
- event count increases when GMGN emits Twitter frames
- no watchdog restart loop caused by DB writes
- `/readyz` stays healthy unless upstream truly goes stale

---

## Risk Notes

- SQLite FTS5 must be available in the Python runtime. The schema test proves this before implementation continues.
- SQLite WAL supports concurrent readers with one writer. Keep writes in one process and avoid multi-writer containers.
- The existing LanceDB dataset is not automatically migrated. This is intentional. If historical data matters, export/import should be a one-time external operation before deleting LanceDB dependencies.
- FTS5 solves exact/full-text search. It does not solve semantic similarity. Semantic search is not part of this architecture. If it later proves necessary, it requires a new spec and a fresh dependency decision, not preserved LanceDB code.
- Token symbol resolution remains conservative. A cashtag without CA stays unresolved unless a deterministic local registry maps it.

## Completion Definition

The work is complete when:

- LanceDB is absent from runtime dependencies and code.
- LanceDB is absent from product docs, Docker, env vars, config settings, CLI surfaces, and future-use placeholders.
- SQLite WAL stores evidence, entities, alerts, and windows.
- FTS search works from SQLite.
- watched-account token/keyword alerts are emitted live.
- token-flow and account-alerts CLI commands work.
- tests and Docker smoke checks pass.
