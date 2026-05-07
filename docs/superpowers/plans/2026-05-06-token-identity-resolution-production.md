# Token Identity Resolution Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the token-only DEX identity pipeline with a production asset identity pipeline that preserves every tweet mention, resolves assets across CEX and DEX venues, and exposes resolved assets plus unresolved attention candidates without legacy fallback paths.

**Architecture:** Keep `events` and `event_entities` as immutable source facts, introduce asset-domain tables for mentions, identities, venues, candidate audit, attributions, snapshots, jobs, and projections, then cut ingest/search/radar/timeline APIs over to the new model. Provider code stays behind explicit adapters: GMGN remains chain/address enrichment, OKX CEX syncs bounded instruments, and OKX DEX resolves symbol/address candidates on demand.

**Tech Stack:** Python 3.13, uv, psycopg, Alembic, FastAPI, pytest, ruff, PostgreSQL, existing repository/service patterns in `src/gmgn_twitter_intel`.

---

## Implementation Boundary

The implementation runs in:

```text
/Users/qinghuan/Documents/code/gmgn-twitter-intel/.worktrees/token-identity-resolution-production
```

Branch:

```text
codex/token-identity-resolution-production
```

Baseline before changes:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

Observed baseline:

```text
pytest: 104 passed, 183 skipped
ruff: All checks passed
compileall: pass
```

## File Structure

Create:

- `src/gmgn_twitter_intel/storage/asset_repository.py`
  Owns asset schema writes/reads: mentions, assets, aliases, venues, candidates, attributions, snapshots, jobs, projection rows.

- `src/gmgn_twitter_intel/pipeline/asset_mention_builder.py`
  Converts `event_entities` and GMGN payload facts into `AssetMentionInput` rows. No provider calls.

- `src/gmgn_twitter_intel/pipeline/asset_resolver.py`
  Deterministic local resolver policy for CA, GMGN payload, local aliases, CEX instruments, DEX candidates, unresolved and ambiguous buckets.

- `src/gmgn_twitter_intel/pipeline/asset_attribution.py`
  Converts resolver decisions into `asset_attributions` rows and projection-ready payloads.

- `src/gmgn_twitter_intel/market/okx_cex_client.py`
  Small HTTP adapter for OKX public instruments/tickers. No trading/private endpoints.

- `src/gmgn_twitter_intel/market/okx_dex_client.py`
  Small HTTP adapter for OKX DEX token search and price info.

- `src/gmgn_twitter_intel/market/okx_models.py`
  Normalized provider records for CEX instruments, DEX token candidates, and market snapshots.

- `src/gmgn_twitter_intel/retrieval/asset_search_service.py`
  New `$SYMBOL`/CA/handle/text search semantics. Symbol search returns evidence even when unresolved.

- `src/gmgn_twitter_intel/retrieval/asset_flow_service.py`
  Serves `resolved_assets` and `attention_candidates`.

- `src/gmgn_twitter_intel/retrieval/asset_social_timeline_service.py`
  Timeline by `asset_id`, works for unresolved and resolved assets.

- `src/gmgn_twitter_intel/storage/alembic/versions/20260506_0005_asset_identity_resolution.py`
  Adds asset-domain schema and indexes.

- `tests/test_asset_repository.py`
- `tests/test_asset_mention_builder.py`
- `tests/test_asset_resolver.py`
- `tests/test_asset_ingest_flow.py`
- `tests/test_asset_search_service.py`
- `tests/test_asset_flow_service.py`
- `tests/test_asset_social_timeline_service.py`
- `tests/test_okx_clients.py`

Modify:

- `src/gmgn_twitter_intel/pipeline/ingest_service.py`
  Cut event ingest over to asset mentions/resolution/attributions.

- `src/gmgn_twitter_intel/storage/repository_session.py`
  Expose `AssetRepository`.

- `src/gmgn_twitter_intel/api/http.py`
  Replace token-flow/search/timeline routes with asset-domain services.

- `src/gmgn_twitter_intel/cli.py`
  Add ops commands for OKX universe sync, symbol resolution, attribution audit, backfill, and asset-flow rebuild.

- `src/gmgn_twitter_intel/settings.py` and `config.example.yaml`
  Add OKX public/provider settings and remove unused `gmgn_evm_candidate_chains`.

- `tests/test_query_parser.py`
  Keep parser behavior, but downstream symbol semantics change.

- `tests/test_token_attribution_flow.py`, `tests/test_postgres_retrieval_services.py`, `tests/test_token_rolling_flow.py`, `tests/test_token_posts_service.py`, `tests/test_token_social_timeline_service.py`
  Delete or rewrite old expectations that unresolved symbols/unknown-chain CAs vanish.

Retire from runtime:

- `src/gmgn_twitter_intel/pipeline/token_identity_resolver.py`
- token-only symbol search behavior in `src/gmgn_twitter_intel/retrieval/search_service.py`
- token-only flow API route semantics in `src/gmgn_twitter_intel/retrieval/token_flow_service.py`
- token-only timeline route semantics in `src/gmgn_twitter_intel/retrieval/token_social_timeline_service.py`
- token-only market observation enqueue assumptions where all rows have `chain/address`

The files may remain briefly during implementation to keep intermediate tests running, but final runtime imports and routes must not depend on them.

---

## Task 1: Asset Schema Migration

**Files:**
- Create: `src/gmgn_twitter_intel/storage/alembic/versions/20260506_0005_asset_identity_resolution.py`
- Modify: `tests/test_postgres_schema.py`
- Modify: `tests/test_postgres_schema_runtime.py`

- [ ] **Step 1: Write failing schema tests**

Add tests asserting these tables exist:

```python
ASSET_TABLES = {
    "asset_mentions",
    "assets",
    "asset_aliases",
    "asset_venues",
    "asset_resolution_candidates",
    "asset_attributions",
    "asset_market_snapshots",
    "asset_resolution_jobs",
    "asset_attention_buckets",
    "asset_attention_bucket_authors",
    "asset_flow_window_snapshots",
}
```

Also assert:

```python
def test_asset_schema_supports_cex_assets(conn):
    columns = table_columns(conn, "asset_venues")
    assert {"venue_type", "exchange", "inst_id", "base_symbol", "quote_symbol", "inst_type"}.issubset(columns)
    assert {"chain", "address"}.issubset(columns)


def test_asset_attributions_allow_unresolved_rows(conn):
    columns = table_columns(conn, "asset_attributions")
    assert columns["venue_id"]["nullable"] is True
    assert columns["attribution_status"]["nullable"] is False
```

- [ ] **Step 2: Run schema tests and verify failure**

Run:

```bash
uv run pytest tests/test_postgres_schema.py tests/test_postgres_schema_runtime.py -q
```

Expected: failures showing missing asset tables.

- [ ] **Step 3: Add Alembic migration**

Create `20260506_0005_asset_identity_resolution.py` with:

```python
revision = "20260506_0005"
down_revision = "20260506_0004"
```

Create tables:

```text
assets(asset_id PK, asset_type, canonical_symbol, display_name, identity_status, confidence, primary_source, first_seen_event_id, first_seen_at_ms, updated_at_ms)
asset_aliases(alias_id PK, asset_id FK, alias_type, alias_value, normalized_alias, source, confidence, created_at_ms)
asset_venues(venue_id PK, asset_id FK, venue_type, provider, exchange, chain, address, inst_id, base_symbol, quote_symbol, inst_type, is_active, confidence, source_payload_hash, created_at_ms, updated_at_ms)
asset_mentions(mention_id PK, event_id FK, mention_type, raw_value, normalized_symbol, chain_hint, address_hint, source_entity_id, source, mention_confidence, created_at_ms)
asset_resolution_candidates(candidate_id PK, mention_id FK, asset_id FK nullable, venue_id FK nullable, provider, candidate_kind, score, decision, reasons_json, risks_json, raw_observation_id, created_at_ms)
asset_attributions(attribution_id PK, event_id FK, mention_id FK, asset_id FK, venue_id FK nullable, attribution_status, attribution_weight, confidence, identity_status, reasons_json, risks_json, decision_time_ms, created_at_ms)
asset_market_snapshots(snapshot_id PK, asset_id FK, venue_id FK, provider, observed_at_ms, price_usd, market_cap_usd, liquidity_usd, volume_24h_usd, open_interest_usd, holders, price_change_5m_pct, price_change_1h_pct, price_change_24h_pct, source_payload_hash, raw_observation_id, created_at_ms)
asset_resolution_jobs(job_id PK, job_type, normalized_symbol, chain_hint, address_hint, status, attempt_count, next_run_at_ms, last_error, created_at_ms, updated_at_ms)
asset_attention_buckets(...)
asset_attention_bucket_authors(...)
asset_flow_window_snapshots(...)
```

Use indexes:

```text
asset_mentions(event_id)
asset_mentions(normalized_symbol, mention_type)
asset_aliases(normalized_alias, alias_type)
asset_venues(venue_type, exchange, inst_id)
asset_venues(chain, address)
asset_attributions(event_id)
asset_attributions(asset_id, created_at_ms)
asset_attributions(attribution_status, identity_status)
asset_resolution_jobs(status, next_run_at_ms)
asset_attention_buckets(window, bucket_start_ms, asset_id)
asset_flow_window_snapshots(window, rank)
```

- [ ] **Step 4: Run migration tests**

Run:

```bash
uv run pytest tests/test_postgres_schema.py tests/test_postgres_schema_runtime.py -q
```

Expected: pass or skip consistently with existing PostgreSQL fixture behavior.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/storage/alembic/versions/20260506_0005_asset_identity_resolution.py tests/test_postgres_schema.py tests/test_postgres_schema_runtime.py
git commit -m "feat: add asset identity schema"
```

---

## Task 2: Asset Repository

**Files:**
- Create: `src/gmgn_twitter_intel/storage/asset_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/repository_session.py`
- Create: `tests/test_asset_repository.py`

- [ ] **Step 1: Write repository tests first**

Test cases:

```python
def test_upsert_unresolved_symbol_asset_round_trips(asset_repo):
    asset = asset_repo.upsert_unresolved_symbol("MIRROR", event_id="event-1", observed_at_ms=1000)
    assert asset["asset_type"] == "unresolved_symbol"
    assert asset["canonical_symbol"] == "MIRROR"
    assert asset["identity_status"] == "unresolved"


def test_upsert_cex_instrument_creates_asset_alias_and_venue(asset_repo):
    result = asset_repo.upsert_cex_instrument(
        exchange="okx",
        inst_type="SPOT",
        inst_id="BTC-USDT",
        base_symbol="BTC",
        quote_symbol="USDT",
        observed_at_ms=1000,
        source_payload_hash="hash",
    )
    assert result.asset["asset_type"] == "cex_asset"
    assert result.venue["venue_type"] == "cex"
    assert asset_repo.candidates_for_symbol("BTC")


def test_record_unresolved_attribution(asset_repo):
    mention = asset_repo.insert_mention(...)
    asset = asset_repo.upsert_unresolved_symbol("MIRROR", event_id=mention.event_id, observed_at_ms=1000)
    attribution = asset_repo.insert_attribution(...)
    assert attribution["attribution_status"] == "unresolved"
    assert attribution["venue_id"] is None
```

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest tests/test_asset_repository.py -q
```

Expected: import/table/method failures.

- [ ] **Step 3: Implement focused repository methods**

Implement dataclasses:

```python
@dataclass(frozen=True, slots=True)
class AssetResolutionResult:
    asset: dict[str, Any]
    venue: dict[str, Any] | None = None
    aliases: list[dict[str, Any]] = field(default_factory=list)
```

Implement methods:

```python
insert_mention(...)
upsert_unresolved_symbol(...)
upsert_ambiguous_symbol(...)
upsert_dex_asset(...)
upsert_cex_instrument(...)
candidates_for_symbol(symbol: str) -> list[dict[str, Any]]
insert_resolution_candidate(...)
insert_attribution(...)
insert_market_snapshot(...)
queue_resolution_job(...)
events_for_symbol_mentions(...)
asset_attributions_for_asset(...)
```

Use early returns and small private helpers:

```python
def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()
```

- [ ] **Step 4: Wire repository session**

Add:

```python
from .asset_repository import AssetRepository
```

Expose:

```python
@cached_property
def assets(self) -> AssetRepository:
    return AssetRepository(self.conn)
```

- [ ] **Step 5: Run focused tests**

```bash
uv run pytest tests/test_asset_repository.py -q
```

Expected: pass/skip according to DB fixture.

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/storage/asset_repository.py src/gmgn_twitter_intel/storage/repository_session.py tests/test_asset_repository.py
git commit -m "feat: add asset repository"
```

---

## Task 3: Provider Adapters For OKX

**Files:**
- Create: `src/gmgn_twitter_intel/market/okx_models.py`
- Create: `src/gmgn_twitter_intel/market/okx_cex_client.py`
- Create: `src/gmgn_twitter_intel/market/okx_dex_client.py`
- Modify: `src/gmgn_twitter_intel/settings.py`
- Modify: `config.example.yaml`
- Create: `tests/test_okx_clients.py`

- [ ] **Step 1: Write adapter tests with mocked HTTP transport**

Tests:

```python
def test_okx_cex_client_normalizes_instruments():
    client = OkxCexClient(base_url="https://www.okx.com", transport=mock_transport({...}))
    instruments = client.instruments(inst_type="SPOT")
    assert instruments[0].inst_id == "BTC-USDT"
    assert instruments[0].base_symbol == "BTC"


def test_okx_dex_client_normalizes_token_search_candidates():
    client = OkxDexClient(base_url="https://web3.okx.com", transport=mock_transport({...}))
    candidates = client.search_tokens(query="MIRROR", chain_indexes=["501"])
    assert candidates[0].symbol == "MIRROR"
    assert candidates[0].chain_index == "501"
```

- [ ] **Step 2: Implement provider models**

Create frozen dataclasses:

```python
@dataclass(frozen=True, slots=True)
class OkxCexInstrument:
    inst_id: str
    inst_type: str
    base_symbol: str
    quote_symbol: str
    state: str
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class OkxDexTokenCandidate:
    chain_index: str
    chain: str | None
    address: str
    symbol: str
    name: str | None
    market_cap_usd: float | None
    liquidity_usd: float | None
    holders: int | None
    community_recognized: bool | None
    raw: dict[str, Any]
```

- [ ] **Step 3: Implement clients**

`OkxCexClient`:

```python
def instruments(self, *, inst_type: str) -> list[OkxCexInstrument]:
    return self._get("/api/v5/public/instruments", params={"instType": inst_type})
```

`OkxDexClient`:

```python
def search_tokens(self, *, query: str, chain_indexes: list[str]) -> list[OkxDexTokenCandidate]:
    return self._get("/api/v6/dex/market/token/search", params={"keyword": query, "chainIndex": ",".join(chain_indexes)})
```

Use resilient payload parsing like `onchain_os`: accept `data` as list or nested list, ignore malformed rows, never raise for a single bad row.

- [ ] **Step 4: Add settings**

Add:

```yaml
providers:
  okx:
    cex_base_url: "https://www.okx.com"
    dex_base_url: "https://web3.okx.com"
    dex_chain_indexes: ["501", "1", "56", "8453"]
    timeout_seconds: 15
```

Remove unused `gmgn_evm_candidate_chains`.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_okx_clients.py tests/test_settings.py -q
uv run ruff check src/gmgn_twitter_intel/market src/gmgn_twitter_intel/settings.py tests/test_okx_clients.py
```

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/market/okx_models.py src/gmgn_twitter_intel/market/okx_cex_client.py src/gmgn_twitter_intel/market/okx_dex_client.py src/gmgn_twitter_intel/settings.py config.example.yaml tests/test_okx_clients.py tests/test_settings.py
git commit -m "feat: add OKX asset provider adapters"
```

---

## Task 4: Asset Mention Builder

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/asset_mention_builder.py`
- Create: `tests/test_asset_mention_builder.py`

- [ ] **Step 1: Write tests**

Cases:

```python
def test_cashtag_creates_asset_mention():
    entity = ExtractedEntity(entity_type="symbol", raw_value="$mirror", normalized_value="MIRROR", ...)
    mentions = build_asset_mentions(event_id="event-1", entities=[entity], token_snapshot=None, created_at_ms=1000)
    assert mentions[0].mention_type == "cashtag"
    assert mentions[0].normalized_symbol == "MIRROR"


def test_plain_word_is_not_asset_mention():
    mentions = build_asset_mentions(event_id="event-1", entities=[], token_snapshot=None, created_at_ms=1000)
    assert mentions == []


def test_gmgn_payload_creates_direct_payload_mention():
    mentions = build_asset_mentions(event_id="event-1", entities=[], token_snapshot=snapshot, created_at_ms=1000)
    assert mentions[0].mention_type == "gmgn_payload"
    assert mentions[0].chain_hint == snapshot.chain
```

- [ ] **Step 2: Implement dataclass and builder**

```python
@dataclass(frozen=True, slots=True)
class AssetMentionInput:
    event_id: str
    mention_type: str
    raw_value: str
    normalized_symbol: str | None
    chain_hint: str | None
    address_hint: str | None
    source_entity_id: str | None
    source: str
    mention_confidence: float
    created_at_ms: int
```

Builder rules:

- symbol entity -> `cashtag`;
- CA entity -> `ca`;
- GMGN token snapshot -> `gmgn_payload`;
- no provider calls;
- de-dupe exact duplicate `(mention_type, normalized_symbol, chain_hint, address_hint, raw_value)`.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_asset_mention_builder.py tests/test_entity_extractor.py -q
```

- [ ] **Step 4: Commit**

```bash
git add src/gmgn_twitter_intel/pipeline/asset_mention_builder.py tests/test_asset_mention_builder.py
git commit -m "feat: build asset mentions from tweet facts"
```

---

## Task 5: Deterministic Asset Resolver

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/asset_resolver.py`
- Create: `src/gmgn_twitter_intel/pipeline/asset_attribution.py`
- Create: `tests/test_asset_resolver.py`

- [ ] **Step 1: Write resolver policy tests**

Cases:

```python
def test_unresolved_symbol_creates_attention_asset(fake_asset_repo):
    decision = resolver.resolve(mention("$MIRROR"))
    assert decision.attribution_status == "unresolved"
    assert decision.asset["asset_type"] == "unresolved_symbol"


def test_btc_prefers_cex_asset_when_local_cex_instrument_exists(fake_asset_repo):
    fake_asset_repo.seed_cex("BTC", "BTC-USDT")
    decision = resolver.resolve(mention("$BTC"))
    assert decision.asset["asset_type"] == "cex_asset"
    assert decision.attribution_status == "selected"


def test_multiple_close_candidates_remain_ambiguous(fake_asset_repo):
    fake_asset_repo.seed_candidates("MIRROR", scores=[74, 68])
    decision = resolver.resolve(mention("$MIRROR"))
    assert decision.attribution_status == "ambiguous"
```

- [ ] **Step 2: Implement resolver result types**

```python
@dataclass(frozen=True, slots=True)
class AssetResolutionDecision:
    mention_id: str
    asset_id: str
    venue_id: str | None
    attribution_status: str
    identity_status: str
    confidence: float
    attribution_weight: float
    reasons: list[str]
    risks: list[str]
```

- [ ] **Step 3: Implement decision order**

Implement exactly:

1. GMGN payload with chain/address -> direct DEX asset.
2. CA with chain hint -> direct DEX asset.
3. CA without chain hint -> local CA alias; else unresolved CA asset.
4. Symbol with single high-confidence local alias -> selected.
5. Symbol with local CEX instrument -> selected CEX asset.
6. Multiple close candidates -> ambiguous.
7. No candidate -> unresolved symbol asset.

No external provider calls in this synchronous resolver.

- [ ] **Step 4: Implement attribution writer**

`asset_attribution.py` should map decisions to repository calls:

```python
def persist_asset_decision(repo: AssetRepository, decision: AssetResolutionDecision, *, event_id: str, decision_time_ms: int) -> dict[str, Any]:
    return repo.insert_attribution(...)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_asset_resolver.py -q
```

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/pipeline/asset_resolver.py src/gmgn_twitter_intel/pipeline/asset_attribution.py tests/test_asset_resolver.py
git commit -m "feat: resolve asset mentions deterministically"
```

---

## Task 6: Ingest V2 Cutover

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/ingest_service.py`
- Modify: `tests/test_asset_ingest_flow.py`
- Modify: existing ingest/token attribution tests that assert old behavior

- [ ] **Step 1: Write end-to-end ingest tests**

Cases:

```python
def test_ingest_mirror_writes_unresolved_asset_attribution(repo_session):
    event = twitter_event(text="$mirror is moving")
    ingest.ingest_event(event)
    rows = repo_session.assets.events_for_symbol_mentions("MIRROR", limit=10)
    assert rows
    assert rows[0]["attribution_status"] == "unresolved"


def test_ingest_gmgn_payload_writes_direct_dex_asset(repo_session):
    event = twitter_event(token_snapshot=gmgn_snapshot(chain="solana", address="So111...", symbol="SOL"))
    ingest.ingest_event(event)
    attrs = repo_session.assets.asset_attributions_for_symbol("SOL")
    assert attrs[0]["attribution_status"] == "direct"
    assert attrs[0]["venue_type"] == "dex"
```

- [ ] **Step 2: Run tests and verify old path fails**

```bash
uv run pytest tests/test_asset_ingest_flow.py -q
```

- [ ] **Step 3: Modify ingest orchestration**

Replace token-only block:

```python
token_mentions = self.token_identity.resolve_event_mentions(...)
self.signals.insert_event_token_mentions(...)
attributions = build_token_attributions(...)
self.signals.insert_event_token_attributions(...)
```

with asset-domain block:

```python
mention_inputs = build_asset_mentions(...)
asset_mentions = self.assets.insert_mentions(mention_inputs, commit=False)
asset_decisions = self.asset_resolver.resolve_many(asset_mentions, event=event)
self.assets.insert_attributions_from_decisions(asset_decisions, commit=False)
```

Keep existing evidence/entity writes before asset writes.

- [ ] **Step 4: Remove runtime dependency on `TokenIdentityResolver`**

`IngestService.__init__` should accept/use:

```python
assets: AssetRepository
asset_resolver: AssetResolver
```

No new ingest code should instantiate `TokenIdentityResolver`.

- [ ] **Step 5: Run focused tests**

```bash
uv run pytest tests/test_asset_ingest_flow.py tests/test_collector_service.py tests/test_api_websocket.py -q
```

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/pipeline/ingest_service.py tests/test_asset_ingest_flow.py tests/test_collector_service.py tests/test_api_websocket.py
git commit -m "feat: cut ingest over to asset attributions"
```

---

## Task 7: Asset Search Service

**Files:**
- Create: `src/gmgn_twitter_intel/retrieval/asset_search_service.py`
- Modify: `src/gmgn_twitter_intel/api/http.py`
- Create: `tests/test_asset_search_service.py`
- Modify: `tests/test_api_http.py`

- [ ] **Step 1: Write search semantics tests**

Cases:

```python
def test_symbol_search_returns_unresolved_mentions(asset_search):
    result = asset_search.search("$MIRROR", limit=20)
    assert result.ok is True
    assert result.resolution["status"] == "unresolved"
    assert result.items[0]["match_type"] == "asset_mention"


def test_symbol_search_returns_ambiguous_candidates_and_events(asset_search):
    result = asset_search.search("$DOG", limit=20)
    assert result.ok is True
    assert result.resolution["status"] == "ambiguous"
    assert result.candidates
    assert result.items


def test_text_search_still_uses_fts(asset_search):
    result = asset_search.search("mirror", limit=20)
    assert result.ok is True
    assert result.items[0]["match_type"] == "fts"
```

- [ ] **Step 2: Implement service contract**

Return dataclass:

```python
@dataclass(frozen=True, slots=True)
class AssetSearchResults:
    ok: bool
    items: list[dict[str, Any]]
    query: dict[str, Any]
    resolution: dict[str, Any]
    candidates: list[dict[str, Any]]
    total_count: int
    returned_count: int
    has_more: bool
    error: str | None = None
```

Symbol path:

1. fetch candidates from `assets.candidates_for_symbol(symbol)`;
2. fetch mention evidence from `assets.events_for_symbol_mentions(symbol)`;
3. if selected asset exists, prepend attribution events;
4. never return empty solely because no candidate exists.

- [ ] **Step 3: Replace HTTP search dependency**

`/api/search` should instantiate/use `AssetSearchService`, not old `SearchService`.

- [ ] **Step 4: Delete old unresolved symbol behavior tests**

Replace tests expecting:

```text
ok=false, error=unresolved_token_symbol
```

with:

```text
ok=true, resolution.status=unresolved, items non-empty
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_asset_search_service.py tests/test_api_http.py tests/test_query_parser.py -q
```

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/retrieval/asset_search_service.py src/gmgn_twitter_intel/api/http.py tests/test_asset_search_service.py tests/test_api_http.py tests/test_query_parser.py
git commit -m "feat: return symbol evidence for unresolved asset search"
```

---

## Task 8: Asset Flow Radar

**Files:**
- Create: `src/gmgn_twitter_intel/retrieval/asset_flow_service.py`
- Modify: `src/gmgn_twitter_intel/api/http.py`
- Create: `tests/test_asset_flow_service.py`
- Modify or delete: token-flow tests that assume all rows have `chain/address`

- [ ] **Step 1: Write flow contract tests**

Cases:

```python
def test_asset_flow_has_resolved_and_attention_lanes(asset_flow):
    result = asset_flow.list_assets(window="1h", limit=20)
    assert "resolved_assets" in result["data"]
    assert "attention_candidates" in result["data"]


def test_unresolved_mirror_appears_in_attention_lane(asset_flow):
    result = asset_flow.list_assets(window="1h", limit=20)
    mirror = find_symbol(result["data"]["attention_candidates"], "MIRROR")
    assert mirror["asset"]["identity_status"] == "unresolved"


def test_btc_cex_asset_does_not_require_chain_address(asset_flow):
    btc = find_symbol(result["data"]["resolved_assets"], "BTC")
    assert btc["asset"]["asset_type"] == "cex_asset"
    assert btc["primary_venue"]["venue_type"] == "cex"
```

- [ ] **Step 2: Implement aggregation**

Read from `asset_attributions`:

- resolved lane: `attribution_status IN ('direct', 'selected')` and asset has active venue;
- attention lane: `attribution_status IN ('unresolved', 'ambiguous')`;
- group by `asset_id`;
- compute `mentions_5m`, `mentions_1h`, `unique_authors`, `watched_mentions`, `latest_seen_ms`.

No `chain/address` global filter.

- [ ] **Step 3: Add `/api/asset-flow`**

Route:

```text
GET /api/asset-flow?window=1h&limit=50&scope=all
```

Response:

```json
{
  "ok": true,
  "data": {
    "resolved_assets": [],
    "attention_candidates": [],
    "projection": {"status": "fresh", "version": "asset-flow-v1"}
  }
}
```

- [ ] **Step 4: Remove `/api/token-flow` runtime route**

Delete route registration or return explicit 410 only if API framework requires preserving route. Final frontend must not call it.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_asset_flow_service.py tests/test_api_http.py -q
```

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/retrieval/asset_flow_service.py src/gmgn_twitter_intel/api/http.py tests/test_asset_flow_service.py tests/test_api_http.py
git commit -m "feat: expose asset flow radar lanes"
```

---

## Task 9: Asset Social Timeline

**Files:**
- Create: `src/gmgn_twitter_intel/retrieval/asset_social_timeline_service.py`
- Modify: `src/gmgn_twitter_intel/api/http.py`
- Create: `tests/test_asset_social_timeline_service.py`

- [ ] **Step 1: Write timeline tests**

Cases:

```python
def test_unresolved_asset_timeline_returns_posts_without_market_overlay(service):
    result = service.timeline(asset_id="asset:unresolved:MIRROR", window="1h", limit=50)
    assert result["summary"]["posts"] > 0
    assert result["market_overlay"] is None


def test_cex_asset_timeline_uses_cex_market_overlay(service):
    result = service.timeline(asset_id="asset:cex:BTC", window="1h", limit=50)
    assert result["market_overlay"]["venue_type"] == "cex"
```

- [ ] **Step 2: Implement service**

Inputs:

```text
asset_id
window
scope
limit
cursor
```

Reads:

- `asset_attributions`;
- `events`;
- latest `asset_market_snapshots` by venue;
- group posts into buckets.

- [ ] **Step 3: Add API route**

```text
GET /api/asset-social-timeline?asset_id=...&window=1h&scope=all&limit=200&cursor=...
```

- [ ] **Step 4: Remove token-only timeline route usage**

Frontend and tests should stop relying on:

```text
/api/token-social-timeline?token_id=...
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_asset_social_timeline_service.py tests/test_api_http.py -q
```

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/retrieval/asset_social_timeline_service.py src/gmgn_twitter_intel/api/http.py tests/test_asset_social_timeline_service.py tests/test_api_http.py
git commit -m "feat: add asset social timeline"
```

---

## Task 10: Ops Commands And Backfill

**Files:**
- Modify: `src/gmgn_twitter_intel/cli.py`
- Create: tests in `tests/test_cli.py` or focused `tests/test_asset_ops_cli.py`

- [ ] **Step 1: Write CLI tests**

Commands:

```bash
gmgn-twitter-intel ops sync-okx-cex-universe --inst-type SPOT --inst-type SWAP
gmgn-twitter-intel ops resolve-asset-symbol --symbol MIRROR
gmgn-twitter-intel ops asset-resolution-health --window 24h
gmgn-twitter-intel ops audit-asset-attribution --event-id event-1
gmgn-twitter-intel ops backfill-asset-mentions --since-ms 0
gmgn-twitter-intel ops rebuild-asset-flow --window 1h
```

Tests assert command registration and JSON shape, with provider calls mocked.

- [ ] **Step 2: Implement commands**

Each command must:

- open settings/session using existing CLI patterns;
- return JSON or rich table consistently with existing ops commands;
- never require private OKX credentials;
- expose provider errors explicitly.

- [ ] **Step 3: Implement backfill**

Backfill source:

```text
events
event_entities
GMGN token payload facts if present in normalized event payload
```

Writes:

```text
asset_mentions
asset_attributions
asset_resolution_jobs
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_cli.py tests/test_asset_ops_cli.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/cli.py tests/test_cli.py tests/test_asset_ops_cli.py
git commit -m "feat: add asset resolution ops commands"
```

---

## Task 11: Frontend Contract Cutover

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/TokenDetailDrawer.tsx`
- Modify: `web/src/store/useTraderStore.ts`
- Modify/add relevant frontend tests

- [ ] **Step 1: Replace token-flow API types**

Create:

```ts
export interface AssetFlowResponse {
  ok: boolean;
  data: {
    resolved_assets: AssetFlowItem[];
    attention_candidates: AssetAttentionCandidate[];
    projection: ProjectionStatus;
  };
}
```

Remove runtime dependency on old `TokenFlowResponse`.

- [ ] **Step 2: Update store API calls**

Replace:

```text
/api/token-flow
```

with:

```text
/api/asset-flow
```

- [ ] **Step 3: Render two lanes**

UI must show:

- resolved assets;
- attention candidates;
- unresolved/ambiguous badges;
- CEX venue rows without chain/address;
- DEX venue rows with chain/address.

- [ ] **Step 4: Update detail drawer**

Use:

```text
/api/asset-social-timeline?asset_id=...
```

Do not require `token_id`, `chain`, or `address`.

- [ ] **Step 5: Run frontend tests**

```bash
cd web
npm test -- --run
```

If the repo uses a different test script, run the existing configured script from `package.json`.

- [ ] **Step 6: Commit**

```bash
git add web/src/api/types.ts web/src/App.tsx web/src/components/TokenDetailDrawer.tsx web/src/store/useTraderStore.ts web/src/**/*.test.tsx
git commit -m "feat: cut frontend over to asset flow"
```

---

## Task 12: Legacy Runtime Deletion

**Files:**
- Delete or remove runtime imports from token-only modules listed in the spec.
- Modify: `tests/test_project_structure.py`

- [ ] **Step 1: Add structure guard tests**

Assertions:

```python
def test_legacy_token_identity_runtime_removed():
    forbidden = [
        "TokenIdentityResolver",
        "unresolved_token_symbol",
        "gmgn_evm_candidate_chains",
    ]
    for term in forbidden:
        assert term not in runtime_source_text()
```

Allow these terms only in docs/migration notes.

- [ ] **Step 2: Remove runtime imports**

Use `rg`:

```bash
rg "TokenIdentityResolver|event_token_attributions|token_aliases|unresolved_token_symbol|gmgn_evm_candidate_chains" src tests web
```

Delete or rewrite runtime references.

- [ ] **Step 3: Remove old route contracts**

Verify:

```bash
rg "/api/token-flow|token-social-timeline\\?|token_id=.*chain=.*address" src web tests
```

Expected: no runtime references.

- [ ] **Step 4: Run full checks**

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove legacy token identity runtime"
```

---

## Task 13: Production Verification And Documentation

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md` if command list changes
- Modify: `docs/2026-05-06-token-identity-resolution-production-spec-cn.md` if implementation details changed

- [ ] **Step 1: Document new commands**

Add:

```bash
uv run gmgn-twitter-intel ops sync-okx-cex-universe --inst-type SPOT --inst-type SWAP
uv run gmgn-twitter-intel ops resolve-asset-symbol --symbol MIRROR
uv run gmgn-twitter-intel ops asset-resolution-health --window 24h
uv run gmgn-twitter-intel asset-flow --window 1h --limit 50
```

- [ ] **Step 2: Document runtime semantics**

Must state:

- `$SYMBOL` search returns mention evidence even if unresolved;
- unresolved/ambiguous assets appear in attention candidates;
- CEX assets do not require chain/address;
- resolved DEX assets still include chain/address.

- [ ] **Step 3: Final verification**

Run:

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

If frontend changed:

```bash
cd web
npm test -- --run
npm run build
```

- [ ] **Step 4: Manual CLI smoke**

With test or local config:

```bash
uv run gmgn-twitter-intel search '$MIRROR' --limit 5
uv run gmgn-twitter-intel search mirror --limit 5
uv run gmgn-twitter-intel ops resolve-asset-symbol --symbol MIRROR
uv run gmgn-twitter-intel asset-flow --window 1h --limit 10
```

Expected:

- `$MIRROR` does not return `unresolved_token_symbol`;
- unresolved symbol has evidence or explicit no-evidence status;
- asset-flow returns `resolved_assets` and `attention_candidates`.

- [ ] **Step 5: Commit**

```bash
git add README.md AGENTS.md docs/2026-05-06-token-identity-resolution-production-spec-cn.md
git commit -m "docs: document asset identity resolution pipeline"
```

---

## Self-Review Checklist

- [ ] `$MIRROR` is covered by Task 4, Task 5, Task 6, Task 7, Task 8, and Task 13.
- [ ] BTC/TAO CEX-first assets are covered by Task 3, Task 5, Task 8, and Task 11.
- [ ] Unknown-chain CA is covered by Task 4, Task 5, Task 6, Task 8, and Task 12.
- [ ] OKX is only a provider adapter; no trading/private endpoint enters ingest.
- [ ] GMGN no longer acts as the sole symbol resolver.
- [ ] Old empty unresolved symbol search behavior is deleted, not hidden.
- [ ] `/api/token-flow` runtime route is removed and `/api/asset-flow` is the new contract.
- [ ] Projection freshness remains explicit.
- [ ] Every task has focused tests before implementation.
- [ ] Final checks use the repository commands from AGENTS.md.
