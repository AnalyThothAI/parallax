# Token Radar V4 KISS Deterministic Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Token Radar's symbol/asset guessing path with a deterministic Project/Asset/Listing/Market resolver, automatic discovery queue, registry update, reprocess loop, and market snapshots keyed by explicit Market identity.

**Architecture:** Keep the existing ingest spine (`events -> event_entities -> token_evidence -> token_intents -> token_radar_rows`) and hard-cut the coupled registry/market path (`assets + asset_venues + asset_market_snapshots`) out of Token Radar runtime. Implement a KISS resolver as a fixed priority table returning `EXACT / UNIQUE_BY_CONTEXT / PROJECT_ONLY / AMBIGUOUS / NIL / INVALID`; unresolved states enqueue discovery tasks and registry updates trigger deterministic reprocess.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic/psycopg, pytest, ruff, eth-utils, solders, pytoniq-core or tonsdk after package-health gate, FastAPI, TypeScript, React, Vite, Vitest, Docker Compose.

---

## Execution Rules

- Do not add ML entity linking.
- Do not add manual labeling.
- Do not choose identity by liquidity or market cap.
- Do not keep `asset_attributions` or request-time `asset_flow_rows` in Token Radar runtime.
- Do not let frontend compute `decision`.
- Do not implement CEX as chain Asset.
- Do not use `asset_venues` as the V4 market identity table.
- Make every task end with tests and a commit.

## File Ownership Map

Create:

- `src/gmgn_twitter_intel/pipeline/mention_key_extractor.py`: extracts address, market, chain, venue, and intent keys from span-aware text facts.
- `src/gmgn_twitter_intel/pipeline/deterministic_token_resolver.py`: fixed priority resolver table.
- `src/gmgn_twitter_intel/pipeline/discovery_worker.py`: claims discovery tasks and writes registry facts.
- `src/gmgn_twitter_intel/pipeline/reprocess_worker.py`: reruns resolver for intents touched by registry updates.
- `src/gmgn_twitter_intel/storage/registry_repository.py`: Project/Asset/Listing/Market/Alias reads and writes.
- `src/gmgn_twitter_intel/storage/discovery_repository.py`: discovery task queue.
- `src/gmgn_twitter_intel/storage/market_snapshot_repository.py`: market snapshots keyed by `market_id`.
- `src/gmgn_twitter_intel/storage/alembic/versions/20260507_0008_token_radar_v4_deterministic_registry.py`
- `tests/factories_token_radar_v4.py`
- `tests/golden/test_token_radar_v4_deterministic_resolver.py`
- `tests/test_mention_key_extractor.py`
- `tests/test_deterministic_token_resolver.py`
- `tests/test_registry_repository.py`
- `tests/test_discovery_repository.py`
- `tests/test_reprocess_worker.py`
- `tests/test_market_snapshot_repository.py`

Modify:

- `src/gmgn_twitter_intel/pipeline/entity_extractor.py`
- `src/gmgn_twitter_intel/pipeline/token_evidence_builder.py`
- `src/gmgn_twitter_intel/pipeline/token_intent_builder.py`
- `src/gmgn_twitter_intel/pipeline/token_intent_resolver.py`
- `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- `src/gmgn_twitter_intel/pipeline/asset_market_sync.py`
- `src/gmgn_twitter_intel/pipeline/asset_market_sync_worker.py`
- `src/gmgn_twitter_intel/storage/repository_session.py`
- `src/gmgn_twitter_intel/storage/postgres_audit.py`
- `src/gmgn_twitter_intel/retrieval/asset_flow_service.py`
- `src/gmgn_twitter_intel/api/app.py`
- `src/gmgn_twitter_intel/cli.py`
- `web/src/App.tsx`
- `web/src/api/types.ts`

## Task 1: Golden Corpus For V4 States

**Files:**

- Create: `tests/factories_token_radar_v4.py`
- Create: `tests/golden/test_token_radar_v4_deterministic_resolver.py`
- Modify: `tests/test_token_radar_projection.py`

- [ ] **Step 1: Add fixture factory**

Create `tests/factories_token_radar_v4.py` with:

```python
from __future__ import annotations

from dataclasses import replace

from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.storage.repository_session import repositories_for_connection
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

VERSA_BASE_CA = "0x2cc0db4f8977accadb5b7da59c5923e14328eba3"
PEPE_ETH_CA = "0x6982508145454ce325ddbe47a25d4ec3d2311933"
MOONCLUB_SOL_CA = "69PzM2hDa3MCo7cvKPgiPxhr1FdGdMV3S7h6wpRkpump"
SOLANA_SUFFIX_MUSK = "8561484D1111111111111111111111111111117F7musk"
TON_FRIENDLY_CA = "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c"


def make_event(event_id: str, *, text: str, received_at_ms: int = 1_777_800_000_000) -> TwitterEvent:
    return TwitterEvent(
        event_id=event_id,
        source=Source(provider="gmgn", transport="direct_ws", coverage="public_stream", channel="twitter_monitor_basic"),
        action="tweet",
        original_action=None,
        tweet_id=event_id,
        internal_id=event_id,
        timestamp=received_at_ms // 1000,
        received_at_ms=received_at_ms,
        author=Author(handle="alpha", name="alpha", avatar=None, followers=10_000, tags=[]),
        content=Content(text=text, media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=["alpha"],
        raw={"id": event_id},
    )


def make_payload_event(event_id: str, *, symbol: str, chain: str, address: str, price: str = "0.00001234") -> TwitterEvent:
    snapshot = parse_gmgn_token_payload({"tt": "ca", "t": {"a": address, "c": chain, "p": price, "s": symbol, "mc": "123456.78"}})
    return replace(
        make_event(event_id, text=f"${symbol} payload"),
        source=Source(provider="gmgn", transport="direct_ws", coverage="public_stream", channel="twitter_monitor_token"),
        token_snapshot=snapshot,
    )


def open_v4_runtime(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    repos = repositories_for_connection(conn)
    ingest = IngestService(
        evidence=repos.evidence,
        entities=repos.entities,
        signals=repos.signals,
        enrichment=repos.enrichment,
        assets=repos.assets,
    )
    return conn, repos, ingest
```

- [ ] **Step 2: Add state-gate tests**

Create `tests/golden/test_token_radar_v4_deterministic_resolver.py` with tests named:

```python
def test_symbol_only_pepe_is_project_only_not_asset(tmp_path): ...
def test_symbol_only_mask_stock_crypto_collision_is_ambiguous(tmp_path): ...
def test_base_ca_versa_is_exact_asset(tmp_path): ...
def test_no_chain_evm_address_multiple_chains_is_ambiguous(tmp_path): ...
def test_no_chain_evm_address_single_chain_is_unique_by_context(tmp_path): ...
def test_binance_pepe_without_quote_is_listing(tmp_path): ...
def test_bybit_pepeusdt_perp_is_exact_market(tmp_path): ...
def test_dex_pool_url_is_exact_market(tmp_path): ...
def test_moonclub_symbol_and_solana_mint_create_one_exact_asset_intent(tmp_path): ...
def test_solana_suffix_musk_is_not_symbol(tmp_path): ...
def test_ton_friendly_address_is_validated_or_queued_for_discovery(tmp_path): ...
def test_micro_price_remains_nonzero_in_market_snapshot(tmp_path): ...
def test_nil_symbol_enqueues_discovery_task(tmp_path): ...
def test_registry_update_reprocesses_nil_intent(tmp_path): ...
```

Each test must assert:

```python
resolution["resolution_status"] in {"EXACT", "UNIQUE_BY_CONTEXT", "PROJECT_ONLY", "AMBIGUOUS", "NIL", "INVALID"}
resolution["target_type"] in {"Project", "Asset", "Listing", "Market", None}
resolution["reason_codes_json"]
```

- [ ] **Step 3: Run corpus and confirm it fails before implementation**

Run:

```bash
uv run pytest tests/golden/test_token_radar_v4_deterministic_resolver.py -q
```

Expected: failures for missing V4 schema/repositories/resolver.

- [ ] **Step 4: Commit corpus**

```bash
git add tests/factories_token_radar_v4.py tests/golden/test_token_radar_v4_deterministic_resolver.py
git commit -m "test: add token radar v4 deterministic corpus"
```

## Task 2: V4 Registry And Resolution Schema

**Files:**

- Create: `src/gmgn_twitter_intel/storage/alembic/versions/20260507_0008_token_radar_v4_deterministic_registry.py`
- Modify: `tests/test_postgres_schema.py`
- Modify: `tests/test_postgres_schema_runtime.py`

- [ ] **Step 1: Add schema tests**

Update schema tests to assert the migration contains and runtime creates:

```text
projects
registry_assets
listings
markets
registry_aliases
market_snapshots
discovery_tasks
registry_versions
token_intent_resolutions.target_type
token_intent_resolutions.target_id
token_intent_resolutions.resolution_status
token_intent_resolutions.reason_codes_json
```

- [ ] **Step 2: Add migration**

Create migration `20260507_0008_token_radar_v4_deterministic_registry.py`.

Required DDL:

```sql
CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY,
  canonical_symbol TEXT NOT NULL,
  display_name TEXT,
  status TEXT NOT NULL,
  evidence_level TEXT NOT NULL,
  primary_source TEXT NOT NULL,
  first_seen_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS registry_assets (
  asset_id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
  chain_id TEXT NOT NULL,
  token_standard TEXT NOT NULL,
  address TEXT NOT NULL,
  symbol TEXT,
  name TEXT,
  decimals BIGINT,
  status TEXT NOT NULL,
  evidence_level TEXT NOT NULL,
  primary_source TEXT NOT NULL,
  first_seen_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS listings (
  listing_id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
  exchange TEXT NOT NULL,
  base_symbol TEXT NOT NULL,
  status TEXT NOT NULL,
  evidence_level TEXT NOT NULL,
  first_seen_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS markets (
  market_id TEXT PRIMARY KEY,
  market_type TEXT NOT NULL,
  venue_type TEXT NOT NULL,
  venue TEXT NOT NULL,
  chain_id TEXT,
  pool_address TEXT,
  native_market_id TEXT,
  base_asset_id TEXT REFERENCES registry_assets(asset_id) ON DELETE SET NULL,
  quote_asset_id TEXT REFERENCES registry_assets(asset_id) ON DELETE SET NULL,
  base_listing_id TEXT REFERENCES listings(listing_id) ON DELETE SET NULL,
  base_project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
  base_symbol TEXT,
  quote_symbol TEXT,
  multiplier NUMERIC,
  status TEXT NOT NULL,
  evidence_level TEXT NOT NULL,
  first_seen_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS registry_aliases (
  alias_id TEXT PRIMARY KEY,
  alias_norm TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  source TEXT NOT NULL,
  priority BIGINT NOT NULL,
  status TEXT NOT NULL,
  valid_from_ms BIGINT NOT NULL,
  valid_to_ms BIGINT
);

CREATE TABLE IF NOT EXISTS market_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  market_id TEXT NOT NULL REFERENCES markets(market_id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  observed_at_ms BIGINT NOT NULL,
  price_usd NUMERIC,
  market_cap_usd NUMERIC,
  liquidity_usd NUMERIC,
  volume_24h_usd NUMERIC,
  open_interest_usd NUMERIC,
  holders BIGINT,
  raw_observation_id TEXT,
  created_at_ms BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS discovery_tasks (
  task_id TEXT PRIMARY KEY,
  task_type TEXT NOT NULL,
  query_key TEXT NOT NULL,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL,
  attempt_count BIGINT NOT NULL DEFAULT 0,
  last_error TEXT,
  next_run_at_ms BIGINT NOT NULL,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  UNIQUE(task_type, query_key)
);

CREATE TABLE IF NOT EXISTS registry_versions (
  registry_version TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  changed_target_type TEXT NOT NULL,
  changed_target_id TEXT NOT NULL,
  changed_at_ms BIGINT NOT NULL
);
```

Add columns:

```sql
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS target_type TEXT;
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS target_id TEXT;
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS candidate_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS registry_version TEXT;
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS market_id TEXT REFERENCES markets(market_id) ON DELETE SET NULL;
```

Backfill from old tables once:

- DEX `assets + asset_venues` rows become `registry_assets`;
- CEX `asset_venues` rows become `listings + markets`;
- `asset_market_snapshots` rows become `market_snapshots`;
- no runtime code may read old tables after this task.

- [ ] **Step 3: Run schema tests**

```bash
uv run pytest tests/test_postgres_schema.py tests/test_postgres_schema_runtime.py -q
```

Expected: passed.

- [ ] **Step 4: Commit schema**

```bash
git add src/gmgn_twitter_intel/storage/alembic/versions/20260507_0008_token_radar_v4_deterministic_registry.py tests/test_postgres_schema.py tests/test_postgres_schema_runtime.py
git commit -m "feat: add deterministic token registry schema"
```

## Task 3: Registry, Discovery, And Market Snapshot Repositories

**Files:**

- Create: `src/gmgn_twitter_intel/storage/registry_repository.py`
- Create: `src/gmgn_twitter_intel/storage/discovery_repository.py`
- Create: `src/gmgn_twitter_intel/storage/market_snapshot_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/repository_session.py`
- Test: `tests/test_registry_repository.py`
- Test: `tests/test_discovery_repository.py`
- Test: `tests/test_market_snapshot_repository.py`

- [ ] **Step 1: Implement `RegistryRepository`**

Required methods:

```python
upsert_project(...)
upsert_chain_asset(...)
upsert_listing(...)
upsert_market(...)
upsert_alias(...)
find_projects_by_symbol(symbol)
find_assets_by_address(address, chain_id=None)
find_assets_by_chain_symbol(chain_id, symbol)
find_listings(exchange, base_symbol)
find_cex_market(exchange, native_market_id)
find_dex_market(venue, chain_id, pool_address)
active_assets(rows)
write_registry_version(source, target_type, target_id, changed_at_ms)
```

The `active_assets()` filter returns only `status IN ('candidate', 'canonical')` and requires evidence:

```text
evidence_level IN ('trusted_registry', 'market_evidence', 'sustained_activity', 'canonical')
```

- [ ] **Step 2: Implement `DiscoveryRepository`**

Required methods:

```python
enqueue(task_type, query_key, payload, next_run_at_ms)
claim(limit, now_ms)
mark_ready(task_id)
mark_failed(task_id, error, next_run_at_ms)
tasks_for_query(task_type, query_key)
```

`enqueue()` must be idempotent on `(task_type, query_key)`.

- [ ] **Step 3: Implement `MarketSnapshotRepository`**

Required methods:

```python
insert_snapshot(market_id, provider, observed_at_ms, price_usd, market_cap_usd, liquidity_usd, volume_24h_usd, open_interest_usd, holders, raw_observation_id)
latest_snapshot(market_id, at_or_before_ms)
markets_needing_refresh(stale_before_ms, limit)
```

Use `Decimal` or string input at the repository boundary and write to PostgreSQL `NUMERIC`.

- [ ] **Step 4: Wire repositories**

Modify `RepositorySession`:

```python
registry: RegistryRepository
discovery: DiscoveryRepository
market_snapshots: MarketSnapshotRepository
```

- [ ] **Step 5: Run repository tests**

```bash
uv run pytest tests/test_registry_repository.py tests/test_discovery_repository.py tests/test_market_snapshot_repository.py -q
```

Expected: passed.

- [ ] **Step 6: Commit repositories**

```bash
git add src/gmgn_twitter_intel/storage/registry_repository.py src/gmgn_twitter_intel/storage/discovery_repository.py src/gmgn_twitter_intel/storage/market_snapshot_repository.py src/gmgn_twitter_intel/storage/repository_session.py tests/test_registry_repository.py tests/test_discovery_repository.py tests/test_market_snapshot_repository.py
git commit -m "feat: add deterministic registry repositories"
```

## Task 4: KISS Mention Key Extraction

**Files:**

- Create: `src/gmgn_twitter_intel/pipeline/mention_key_extractor.py`
- Modify: `src/gmgn_twitter_intel/pipeline/entity_extractor.py`
- Modify: `src/gmgn_twitter_intel/pipeline/token_evidence_builder.py`
- Test: `tests/test_mention_key_extractor.py`
- Test: `tests/test_entity_extractor.py`
- Test: `tests/test_token_evidence_builder.py`

- [ ] **Step 1: Choose TON parser package**

Use a package-health gate before adding a TON dependency:

```bash
uv add pytoniq-core
uv run python - <<'PY'
from pytoniq_core import Address
print(Address)
PY
```

If the import fails, remove it and use:

```bash
uv remove pytoniq-core
uv add tonsdk
uv run python - <<'PY'
from tonsdk.utils import Address
print(Address)
PY
```

Commit whichever package imports and validates a friendly TON address in tests.

- [ ] **Step 2: Implement extracted key dataclass**

`mention_key_extractor.py` must expose:

```python
@dataclass(frozen=True, slots=True)
class MentionKeys:
    symbols: list[str]
    addresses: list[AddressKey]
    cex_markets: list[CexMarketKey]
    dex_markets: list[DexMarketKey]
    chain_hints: list[str]
    venue_hints: list[str]
    intent_hints: list[str]
```

Address keys include:

```python
family: "evm" | "solana" | "ton"
chain_id: str | None
address: str
valid: bool
invalid_reason: str | None
```

- [ ] **Step 3: Extract only supported keys**

Extractor must support:

- EVM address;
- Solana mint candidate validated by `solders.Pubkey`;
- TON friendly/raw address validated by selected TON parser;
- cashtag;
- CEX market forms: `PEPEUSDT`, `PEPE/USDT`, `TON-USDT-SWAP`, `1000PEPEUSDT`;
- chain hints;
- venue hints;
- DEX/provider URLs.

- [ ] **Step 4: Run extraction tests**

```bash
uv run pytest tests/test_mention_key_extractor.py tests/test_entity_extractor.py tests/test_token_evidence_builder.py -q
```

Expected: passed.

- [ ] **Step 5: Commit extraction**

```bash
git add pyproject.toml uv.lock src/gmgn_twitter_intel/pipeline/mention_key_extractor.py src/gmgn_twitter_intel/pipeline/entity_extractor.py src/gmgn_twitter_intel/pipeline/token_evidence_builder.py tests/test_mention_key_extractor.py tests/test_entity_extractor.py tests/test_token_evidence_builder.py
git commit -m "feat: extract deterministic token mention keys"
```

## Task 5: Deterministic Resolver

**Files:**

- Create: `src/gmgn_twitter_intel/pipeline/deterministic_token_resolver.py`
- Modify: `src/gmgn_twitter_intel/pipeline/token_intent_resolver.py`
- Modify: `src/gmgn_twitter_intel/storage/intent_resolution_repository.py`
- Test: `tests/test_deterministic_token_resolver.py`
- Test: `tests/test_token_intent_resolver.py`

- [ ] **Step 1: Add resolver enum tests**

Test each status:

```text
EXACT
UNIQUE_BY_CONTEXT
PROJECT_ONLY
AMBIGUOUS
NIL
INVALID
```

Test priority ordering:

```text
DEX pool beats symbol
CEX native market beats symbol
chain+address beats symbol
no-chain address never defaults to eth
symbol-only never resolves to Asset
multiple active candidates returns AMBIGUOUS
```

- [ ] **Step 2: Implement resolver output**

`deterministic_token_resolver.py` must expose:

```python
@dataclass(frozen=True, slots=True)
class DeterministicResolution:
    intent_id: str
    event_id: str
    resolution_status: str
    target_type: str | None
    target_id: str | None
    market_id: str | None
    reason_codes: list[str]
    candidate_ids: list[str]
    discovery_tasks: list[DiscoveryTaskInput]
```

- [ ] **Step 3: Implement fixed priority table**

Implement resolver branches in this exact order:

```python
if keys.dex_market:
    resolve_dex_market()
elif keys.cex_market:
    resolve_cex_market()
elif keys.address and keys.chain:
    resolve_chain_address()
elif keys.address:
    resolve_address_across_tracked_chains()
elif keys.exchange and keys.symbol:
    resolve_listing()
elif keys.chain and keys.symbol:
    resolve_chain_symbol()
elif keys.dex and keys.chain and keys.symbol:
    resolve_dex_chain_symbol()
elif keys.symbol:
    resolve_project_only()
else:
    nil("NO_RESOLVABLE_MENTION")
```

Each branch returns immediately.

- [ ] **Step 4: Enqueue discovery from resolver result**

`token_intent_resolver.py` persists resolution and then calls `repos.discovery.enqueue()` for every `DiscoveryTaskInput` when status is `AMBIGUOUS`, `NIL`, or `INVALID`.

- [ ] **Step 5: Persist V4 resolution fields**

`IntentResolutionRepository.insert_resolution()` writes:

```text
resolution_status
target_type
target_id
market_id
reason_codes_json
candidate_ids_json
registry_version
```

The old `identity_status/confidence/asset_id/primary_venue_id` fields are not used by V4 projection.

- [ ] **Step 6: Run resolver tests**

```bash
uv run pytest tests/test_deterministic_token_resolver.py tests/test_token_intent_resolver.py tests/golden/test_token_radar_v4_deterministic_resolver.py -q
```

Expected: passed.

- [ ] **Step 7: Commit resolver**

```bash
git add src/gmgn_twitter_intel/pipeline/deterministic_token_resolver.py src/gmgn_twitter_intel/pipeline/token_intent_resolver.py src/gmgn_twitter_intel/storage/intent_resolution_repository.py tests/test_deterministic_token_resolver.py tests/test_token_intent_resolver.py tests/golden/test_token_radar_v4_deterministic_resolver.py
git commit -m "feat: resolve token intents deterministically"
```

## Task 6: Discovery Worker And Reprocess Loop

**Files:**

- Create: `src/gmgn_twitter_intel/pipeline/discovery_worker.py`
- Create: `src/gmgn_twitter_intel/pipeline/reprocess_worker.py`
- Modify: `src/gmgn_twitter_intel/cli.py`
- Test: `tests/test_discovery_repository.py`
- Test: `tests/test_reprocess_worker.py`

- [ ] **Step 1: Implement discovery worker**

Worker handles:

```text
address_lookup
solana_mint_lookup
ton_jetton_lookup
cex_market_lookup
cex_listing_lookup
dex_pool_lookup
dex_symbol_lookup
project_symbol_lookup
```

For the first implementation, provider adapters can write deterministic fixture-backed registry facts in tests and production provider calls behind existing clients. The worker must always:

```text
claim task
validate query shape
write raw/candidate/canonical registry rows
write registry_versions
mark task ready or failed
```

- [ ] **Step 2: Implement reprocess worker**

Worker input is `registry_version`.

Algorithm:

```text
find intents whose unresolved/ambiguous reason could be affected by changed target/query
load event token evidence
rerun deterministic resolver
write superseding token_intent_resolutions row
enqueue projection rebuild dirty range
```

- [ ] **Step 3: Add CLI ops**

Add:

```bash
gmgn-twitter-intel ops discovery-run --limit 100
gmgn-twitter-intel ops reprocess-registry-updates --limit 1000
```

- [ ] **Step 4: Run worker tests**

```bash
uv run pytest tests/test_discovery_repository.py tests/test_reprocess_worker.py tests/golden/test_token_radar_v4_deterministic_resolver.py::test_registry_update_reprocesses_nil_intent -q
```

Expected: passed.

- [ ] **Step 5: Commit discovery loop**

```bash
git add src/gmgn_twitter_intel/pipeline/discovery_worker.py src/gmgn_twitter_intel/pipeline/reprocess_worker.py src/gmgn_twitter_intel/cli.py tests/test_discovery_repository.py tests/test_reprocess_worker.py tests/golden/test_token_radar_v4_deterministic_resolver.py
git commit -m "feat: add token discovery and reprocess loop"
```

## Task 7: Market Sync To Explicit Markets

**Files:**

- Modify: `src/gmgn_twitter_intel/pipeline/asset_market_sync.py`
- Modify: `src/gmgn_twitter_intel/pipeline/asset_market_sync_worker.py`
- Modify: `src/gmgn_twitter_intel/market/okx_cex_client.py`
- Modify: `src/gmgn_twitter_intel/market/okx_dex_client.py`
- Modify: `src/gmgn_twitter_intel/market/gmgn_openapi_client.py`
- Test: `tests/test_asset_market_sync.py`
- Test: `tests/test_market_snapshot_repository.py`

- [ ] **Step 1: Rewrite CEX sync**

`sync_okx_cex_universe()` writes:

```text
Project when safe from listing metadata
Listing for exchange + base_symbol
Market for exchange + native_market_id
MarketSnapshot for market_id
```

It must not create `asset:cex:*`.

- [ ] **Step 2: Rewrite DEX price sync**

DEX sync reads `markets WHERE venue_type='dex' AND status IN ('candidate','canonical')`, not `asset_venues`.

It writes `market_snapshots`.

- [ ] **Step 3: Preserve numeric precision**

Provider adapters should keep price-like fields as string or Decimal until repository insert. Tests assert:

```python
Decimal("0.00001234")
```

round-trips through API as nonzero.

- [ ] **Step 4: Run market tests**

```bash
uv run pytest tests/test_asset_market_sync.py tests/test_market_snapshot_repository.py -q
```

Expected: passed.

- [ ] **Step 5: Commit market sync**

```bash
git add src/gmgn_twitter_intel/pipeline/asset_market_sync.py src/gmgn_twitter_intel/pipeline/asset_market_sync_worker.py src/gmgn_twitter_intel/market/okx_cex_client.py src/gmgn_twitter_intel/market/okx_dex_client.py src/gmgn_twitter_intel/market/gmgn_openapi_client.py tests/test_asset_market_sync.py tests/test_market_snapshot_repository.py
git commit -m "feat: sync market data by market identity"
```

## Task 8: Token Radar Projection V4

**Files:**

- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/storage/token_radar_repository.py`
- Modify: `src/gmgn_twitter_intel/retrieval/asset_flow_service.py`
- Test: `tests/test_token_radar_projection.py`
- Test: `tests/test_asset_flow_service.py`

- [ ] **Step 1: Change projection version**

Set:

```python
PROJECTION_VERSION = "token-radar-v4"
```

- [ ] **Step 2: Read V4 resolution fields**

Projection reads:

```text
target_type
target_id
market_id
resolution_status
reason_codes_json
candidate_ids_json
registry_version
```

It does not read:

```text
asset_id
primary_venue_id
asset_venues
asset_market_snapshots
```

- [ ] **Step 3: Join market snapshots by market_id**

Use `market_snapshots` and `markets`.

Market status rules:

```text
PROJECT_ONLY -> no_market
AMBIGUOUS -> no_market
NIL -> no_market
INVALID -> invalid_identity
EXACT/UNIQUE_BY_CONTEXT with market_id and snapshot -> ready/stale
EXACT/UNIQUE_BY_CONTEXT with market_id and no snapshot -> pending_refresh
```

- [ ] **Step 4: Decision caps**

Implement:

```text
PROJECT_ONLY -> investigate
AMBIGUOUS -> investigate
NIL -> investigate
INVALID -> discard or investigate, never driver
market pending/missing -> max watch
driver only if exact/unique target has usable market
```

- [ ] **Step 5: Run projection/API tests**

```bash
uv run pytest tests/test_token_radar_projection.py tests/test_asset_flow_service.py tests/golden/test_token_radar_v4_deterministic_resolver.py -q
```

Expected: passed.

- [ ] **Step 6: Commit projection**

```bash
git add src/gmgn_twitter_intel/pipeline/token_radar_projection.py src/gmgn_twitter_intel/storage/token_radar_repository.py src/gmgn_twitter_intel/retrieval/asset_flow_service.py tests/test_token_radar_projection.py tests/test_asset_flow_service.py tests/golden/test_token_radar_v4_deterministic_resolver.py
git commit -m "feat: project token radar from deterministic resolutions"
```

## Task 9: Frontend Render-Only Contract

**Files:**

- Modify: `web/src/App.tsx`
- Modify: `web/src/api/types.ts`
- Test: `web/src/App.test.tsx`

- [ ] **Step 1: Add API types**

Types include:

```ts
type ResolutionStatus = "EXACT" | "UNIQUE_BY_CONTEXT" | "PROJECT_ONLY" | "AMBIGUOUS" | "NIL" | "INVALID";
type TargetType = "Project" | "Asset" | "Listing" | "Market" | null;
```

- [ ] **Step 2: Remove decision synthesis**

Search:

```bash
rg -n "opportunityScore|decision =|driver" web/src/App.tsx
```

Allowed:

- display labels;
- `normalizeDecision(row.decision)`;
- sorting metadata based on backend decision.

Forbidden:

- computing backend decision from UI score blocks.

- [ ] **Step 3: Add UI regressions**

Tests:

```text
PROJECT_ONLY row remains investigate
AMBIGUOUS high heat row remains investigate
pending market row does not render driver
nonzero micro price does not render $0
address ending musk does not show MUSK as symbol
```

- [ ] **Step 4: Run frontend tests**

```bash
npm --prefix web test -- --run
npm --prefix web run build
```

Expected: passed and built.

- [ ] **Step 5: Commit frontend**

```bash
git add web/src/App.tsx web/src/api/types.ts web/src/App.test.tsx
git commit -m "feat: render deterministic token radar states"
```

## Task 10: Remove Old Runtime Paths

**Files:**

- Modify: `src/gmgn_twitter_intel/api/app.py`
- Modify: `src/gmgn_twitter_intel/api/ws.py`
- Modify: `src/gmgn_twitter_intel/pipeline/notification_rules.py`
- Modify: `src/gmgn_twitter_intel/storage/postgres_audit.py`
- Test: `tests/test_postgres_audit.py`
- Test: `tests/test_notification_rules.py`

- [ ] **Step 1: Add import guard audit**

Audit fails if Token Radar runtime imports:

```text
asset_mentions
asset_attributions
asset_venues
asset_market_snapshots
AssetRepository.candidates_for_symbol
AssetRepository.asset_flow_rows
```

Migration files may mention old names; runtime files may not.

- [ ] **Step 2: Update notifications**

Notifications read `token_radar_rows.decision`, `resolution.target_type`, `market.market_status`.

They do not recompute tradeability.

- [ ] **Step 3: Add health command**

Add:

```bash
gmgn-twitter-intel ops token-radar-v4-health --window 5m
```

Output includes:

```text
resolution_status_counts
target_type_counts
reason_code_counts
discovery_task_counts
market_status_counts
reprocess_success_rate
old_runtime_path_import_count
```

- [ ] **Step 4: Run audit tests**

```bash
uv run pytest tests/test_postgres_audit.py tests/test_notification_rules.py -q
```

Expected: passed.

- [ ] **Step 5: Commit runtime hard cut**

```bash
git add src/gmgn_twitter_intel/api/app.py src/gmgn_twitter_intel/api/ws.py src/gmgn_twitter_intel/pipeline/notification_rules.py src/gmgn_twitter_intel/storage/postgres_audit.py tests/test_postgres_audit.py tests/test_notification_rules.py
git commit -m "feat: remove old token radar runtime paths"
```

## Task 11: Full Verification And Docker Runtime

**Files:**

- Modify only files with failing tests or runtime checks.

- [ ] **Step 1: Backend verification**

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

Expected:

```text
passed
All checks passed!
```

- [ ] **Step 2: Frontend verification**

```bash
npm --prefix web test -- --run
npm --prefix web run build
```

Expected: passed and built.

- [ ] **Step 3: Docker rebuild**

```bash
docker compose build app
docker compose up -d app
curl -fsS http://127.0.0.1:8000/readyz
```

Expected:

```json
{"status":"ok"}
```

- [ ] **Step 4: Rebuild V4 projection**

```bash
docker compose exec app gmgn-twitter-intel ops rebuild-token-radar --window 5m --scope all --limit 120
```

Expected output includes:

```text
token-radar-v4
rows_written
```

- [ ] **Step 5: Pull live 5m data**

```bash
curl -fsS "http://127.0.0.1:8000/api/asset-flow?window=5m&scope=all&limit=120" | jq '.projection'
```

Expected:

```json
{
  "source": "token_radar_rows",
  "version": "token-radar-v4"
}
```

- [ ] **Step 6: Run health audit**

```bash
docker compose exec app gmgn-twitter-intel ops token-radar-v4-health --window 5m
```

Expected:

```json
{
  "resolution_status_counts": {},
  "target_type_counts": {},
  "reason_code_counts": {},
  "discovery_task_counts": {},
  "market_status_counts": {},
  "old_runtime_path_import_count": 0
}
```

- [ ] **Step 7: Manual exit-gate scan**

Run:

```bash
curl -fsS "http://127.0.0.1:8000/api/asset-flow?window=5m&scope=all&limit=120" \
  | jq '[.resolved_assets[], .attention_candidates[]] | map({symbol: .target.symbol, target_type: .target.target_type, status: .resolution.status, reasons: .resolution.reason_codes, market: .market.market_observation_status, decision})'
```

Check:

- `$SYMBOL` only rows are `PROJECT_ONLY`, `AMBIGUOUS`, or `NIL`;
- no symbol-only row is `Asset EXACT`;
- CEX market rows have `target_type="Market"`;
- CEX listing rows have `target_type="Listing"`;
- unresolved hot rows are `investigate`;
- no pending/no-market row is `driver`;
- address-only rows show real address fallback, not fake symbol;
- micro prices are nonzero when raw provider price is nonzero.

- [ ] **Step 8: Commit verification fixes**

If verification changed files:

```bash
git add <changed-files>
git commit -m "fix: close token radar v4 verification gaps"
```

## Done Criteria

- [ ] All V4 golden tests pass.
- [ ] `uv run pytest` passes.
- [ ] `uv run ruff check .` passes.
- [ ] `uv run python -m compileall src tests` passes.
- [ ] Frontend tests and build pass.
- [ ] Docker app is healthy.
- [ ] `/api/asset-flow` reports `token-radar-v4`.
- [ ] `old_runtime_path_import_count` is zero.
- [ ] Live 5m rows explain unknowns through enum status and reason codes.
- [ ] `Discovery -> Registry Update -> Reprocess` is proven by test and runtime audit.
