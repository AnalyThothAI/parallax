# Token Radar V4 KISS Deterministic Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Token Radar's symbol/asset guessing path with a deterministic Project/Asset/CexToken/PriceFeed resolver, automatic discovery queue, registry update, reprocess loop, and price observations that preserve current token/CEX prices without requiring DEX pool identity.

**Architecture:** Keep the existing ingest spine (`events -> event_entities -> token_evidence -> token_intents -> token_radar_rows`) and hard-cut the old asset/venue/snapshot path (`assets + asset_venues + asset_market_snapshots`) out of Token Radar runtime. Implement a KISS resolver as a fixed priority table returning `EXACT / UNIQUE_BY_CONTEXT / PROJECT_ONLY / AMBIGUOUS / NIL / INVALID`; unresolved states enqueue discovery tasks and registry updates trigger deterministic reprocess. GMGN token payloads, OKX DEX token-price responses, GMGN/OpenAPI token-info responses, and CEX tickers all write `price_observations`. Current-stage V4 does not create DEX pool/AMM Market models and does not expose execution targets. This is a single unreleased hard-cut branch, not a compatibility migration.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic/psycopg, pytest, ruff, eth-utils, solders, pytoniq-core or tonsdk after package-health gate, FastAPI, TypeScript, React, Vite, Vitest, Docker Compose.

---

## Execution Rules

- Do not add ML entity linking.
- Do not add manual labeling.
- Do not choose identity by one raw metric or hidden confidence score; chain Asset selection may use the explicit V4 market-dominance formula.
- Do not keep `asset_attributions` or request-time `asset_flow_rows` in Token Radar runtime.
- Do not let frontend compute `decision`.
- Do not implement CEX as chain Asset.
- Do not use `asset_venues` as the V4 price source identity table.
- Do not dual-write V3 and V4 identity paths.
- Do not keep request-time fallback to `asset_id + primary_venue_id`.
- Do not overload `resolution_status` with lifecycle values such as `superseded`.
- Do not use `float` for V4 price-like provider data.
- Do not create DEX Market/pool identity in current-stage Token Radar.
- Do not require exact FX conversion for CEX `USD/USDT/USDC` quote markets; mark them as `usd_like`.
- Do not treat non-stable quote markets such as `PEPE-BTC` as USD without a provider USD basis.
- Do not let Token Radar frontend call Asset-only drilldown APIs for non-Asset targets.
- Do not release any intermediate task branch; release only after the hard-cut audit is clean.
- Make every task end with tests and a commit.

## File Ownership Map

Create:

- `src/gmgn_twitter_intel/pipeline/mention_key_extractor.py`: extracts address, pricefeed, chain, venue, and intent keys from span-aware text facts.
- `src/gmgn_twitter_intel/pipeline/deterministic_token_resolver.py`: fixed priority resolver table.
- `src/gmgn_twitter_intel/pipeline/discovery_worker.py`: claims discovery tasks and writes registry facts.
- `src/gmgn_twitter_intel/pipeline/reprocess_worker.py`: reruns resolver for intents touched by registry updates.
- `src/gmgn_twitter_intel/storage/registry_repository.py`: Project/Asset/CexToken/PriceFeed/Alias reads and writes.
- `src/gmgn_twitter_intel/storage/discovery_repository.py`: discovery task queue.
- `src/gmgn_twitter_intel/storage/price_observation_repository.py`: token/CexToken/pricefeed-level provider price observations.
- `src/gmgn_twitter_intel/storage/token_intent_lookup_repository.py`: indexed resolver lookup keys for deterministic reprocess.
- `src/gmgn_twitter_intel/retrieval/token_radar_service.py`: V4 `/api/token-radar` read service.
- `src/gmgn_twitter_intel/retrieval/token_target_posts_service.py`: target-aware Radar posts drilldown.
- `src/gmgn_twitter_intel/retrieval/token_target_timeline_service.py`: target-aware Radar timeline drilldown.
- `src/gmgn_twitter_intel/storage/alembic/versions/20260507_0008_token_radar_v4_deterministic_registry.py`
- `tests/factories_token_radar_v4.py`
- `tests/golden/test_token_radar_v4_deterministic_resolver.py`
- `tests/test_mention_key_extractor.py`
- `tests/test_deterministic_token_resolver.py`
- `tests/test_registry_repository.py`
- `tests/test_discovery_repository.py`
- `tests/test_reprocess_worker.py`
- `tests/test_price_observation_repository.py`
- `tests/test_token_intent_lookup_repository.py`
- `tests/test_token_target_posts_service.py`
- `tests/test_token_target_timeline_service.py`

Modify:

- `src/gmgn_twitter_intel/pipeline/entity_extractor.py`
- `src/gmgn_twitter_intel/pipeline/token_evidence_builder.py`
- `src/gmgn_twitter_intel/pipeline/token_intent_builder.py`
- `src/gmgn_twitter_intel/pipeline/token_intent_resolver.py`
- `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- `src/gmgn_twitter_intel/pipeline/asset_market_sync.py`
- `src/gmgn_twitter_intel/pipeline/asset_market_sync_worker.py`
- `src/gmgn_twitter_intel/retrieval/tradeability_scoring.py`
- `src/gmgn_twitter_intel/retrieval/trading_attention_service.py`
- `src/gmgn_twitter_intel/storage/repository_session.py`
- `src/gmgn_twitter_intel/storage/postgres_audit.py`
- `src/gmgn_twitter_intel/models.py`
- `src/gmgn_twitter_intel/collector/gmgn_token_payload.py`
- `src/gmgn_twitter_intel/market/okx_models.py`
- `src/gmgn_twitter_intel/market/gmgn_openapi_client.py`
- `src/gmgn_twitter_intel/api/app.py`
- `src/gmgn_twitter_intel/api/http.py`
- `src/gmgn_twitter_intel/api/ws.py`
- `src/gmgn_twitter_intel/cli.py`
- `web/src/App.tsx`
- `web/src/api/types.ts`
- `web/src/components/ScoreLedger.tsx`

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
        registry=repos.registry,
        discovery=repos.discovery,
        price_observations=repos.price_observations,
        token_intent_lookup=repos.token_intent_lookup,
        intent_resolutions=repos.intent_resolutions,
    )
    return conn, repos, ingest
```

- [ ] **Step 2: Add state-gate tests**

Create `tests/golden/test_token_radar_v4_deterministic_resolver.py` with tests named:

```python
def test_symbol_only_pepe_prefers_confirmed_cex_token(tmp_path): ...
def test_symbol_only_upeg_selects_market_dominant_eth_asset(tmp_path): ...
def test_symbol_only_lfi_selects_market_dominant_base_asset(tmp_path): ...
def test_symbol_only_mask_stock_crypto_collision_is_ambiguous(tmp_path): ...
def test_base_ca_versa_is_exact_asset(tmp_path): ...
def test_no_chain_evm_address_multiple_chains_is_ambiguous(tmp_path): ...
def test_no_chain_evm_address_single_chain_is_unique_by_context(tmp_path): ...
def test_binance_pepe_without_quote_is_cex_token(tmp_path): ...
def test_bybit_pepeusdt_perp_is_exact_pricefeed(tmp_path): ...
def test_dex_token_url_is_exact_asset_with_price_observation(tmp_path): ...
def test_moonclub_symbol_and_solana_mint_create_one_exact_asset_intent(tmp_path): ...
def test_solana_suffix_musk_is_not_symbol(tmp_path): ...
def test_ton_friendly_address_is_validated_or_queued_for_discovery(tmp_path): ...
def test_micro_price_remains_nonzero_in_price_observation(tmp_path): ...
def test_gmgn_payload_price_does_not_create_synthetic_market(tmp_path): ...
def test_okx_cex_usdt_quote_is_usd_like_price_observation(tmp_path): ...
def test_okx_cex_btc_quote_is_not_usd_without_provider_basis(tmp_path): ...
def test_okx_dex_token_price_is_price_observation_without_pool_identity(tmp_path): ...
def test_nil_symbol_enqueues_discovery_task(tmp_path): ...
def test_registry_update_reprocesses_nil_intent(tmp_path): ...
```

Each test must assert:

```python
resolution["resolution_status"] in {"EXACT", "UNIQUE_BY_CONTEXT", "PROJECT_ONLY", "AMBIGUOUS", "NIL", "INVALID"}
resolution["target_type"] in {"Project", "Asset", "CexToken", "PriceFeed", None}
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
cex_tokens
price_feeds
registry_aliases
price_observations
discovery_tasks
registry_versions
token_intent_resolutions.target_type
token_intent_resolutions.target_id
token_intent_resolutions.resolution_status
token_intent_resolutions.reason_codes_json
token_intent_resolutions.record_status
token_intent_resolutions.is_current
token_intent_lookup_keys
token_radar_rows.target_type
token_radar_rows.target_id
token_radar_rows.pricefeed_id
token_radar_rows.target_json
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

CREATE TABLE IF NOT EXISTS cex_tokens (
  cex_token_id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
  base_symbol TEXT NOT NULL,
  status TEXT NOT NULL,
  evidence_level TEXT NOT NULL,
  first_seen_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS price_feeds (
  pricefeed_id TEXT PRIMARY KEY,
  feed_type TEXT NOT NULL,
  provider TEXT NOT NULL,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  chain_id TEXT,
  address TEXT,
  native_market_id TEXT,
  base_asset_id TEXT REFERENCES registry_assets(asset_id) ON DELETE SET NULL,
  base_cex_token_id TEXT REFERENCES cex_tokens(cex_token_id) ON DELETE SET NULL,
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

CREATE TABLE IF NOT EXISTS price_observations (
  observation_id TEXT PRIMARY KEY,
  pricefeed_id TEXT REFERENCES price_feeds(pricefeed_id) ON DELETE SET NULL,
  provider TEXT NOT NULL,
  observed_at_ms BIGINT NOT NULL,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  price_usd NUMERIC,
  price_quote NUMERIC,
  quote_symbol TEXT,
  price_basis TEXT NOT NULL DEFAULT 'unavailable',
  market_cap_usd NUMERIC,
  liquidity_usd NUMERIC,
  volume_24h_usd NUMERIC,
  open_interest_usd NUMERIC,
  holders BIGINT,
  raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
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
  affected_lookup_keys_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  changed_at_ms BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS token_intent_lookup_keys (
  lookup_key TEXT NOT NULL,
  intent_id TEXT NOT NULL REFERENCES token_intents(intent_id) ON DELETE CASCADE,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  source_evidence_id TEXT REFERENCES token_evidence(evidence_id) ON DELETE SET NULL,
  created_at_ms BIGINT NOT NULL,
  PRIMARY KEY(lookup_key, intent_id)
);
```

Add columns:

```sql
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS target_type TEXT;
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS target_id TEXT;
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS candidate_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS lookup_keys_json JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS registry_version TEXT;
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS pricefeed_id TEXT REFERENCES price_feeds(pricefeed_id) ON DELETE SET NULL;
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS record_status TEXT NOT NULL DEFAULT 'current';
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS superseded_at_ms BIGINT;
ALTER TABLE token_radar_rows ADD COLUMN IF NOT EXISTS target_type TEXT;
ALTER TABLE token_radar_rows ADD COLUMN IF NOT EXISTS target_id TEXT;
ALTER TABLE token_radar_rows ADD COLUMN IF NOT EXISTS pricefeed_id TEXT REFERENCES price_feeds(pricefeed_id) ON DELETE SET NULL;
ALTER TABLE token_radar_rows ADD COLUMN IF NOT EXISTS target_json JSONB NOT NULL DEFAULT '{}'::jsonb;
```

Required constraints and indexes:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_registry_assets_identity
  ON registry_assets(chain_id, lower(address));
CREATE UNIQUE INDEX IF NOT EXISTS ux_cex_tokens_identity
  ON cex_tokens(base_symbol);
CREATE UNIQUE INDEX IF NOT EXISTS ux_price_feeds_native_identity
  ON price_feeds(provider, feed_type, native_market_id)
  WHERE native_market_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_price_feeds_token_identity
  ON price_feeds(provider, feed_type, chain_id, lower(address))
  WHERE address IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_registry_aliases_identity
  ON registry_aliases(alias_norm, target_type, target_id, source);
CREATE UNIQUE INDEX IF NOT EXISTS ux_token_intent_current_resolution
  ON token_intent_resolutions(intent_id)
  WHERE is_current = true;
CREATE INDEX IF NOT EXISTS idx_token_intent_lookup_keys_lookup
  ON token_intent_lookup_keys(lookup_key);
CREATE INDEX IF NOT EXISTS idx_token_intent_resolutions_target_current
  ON token_intent_resolutions(target_type, target_id, decision_time_ms DESC)
  WHERE is_current = true;
CREATE INDEX IF NOT EXISTS idx_price_observations_feed_latest
  ON price_observations(pricefeed_id, observed_at_ms DESC)
  WHERE pricefeed_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_price_observations_subject_latest
  ON price_observations(subject_type, subject_id, observed_at_ms DESC);
```

Backfill from old tables once:

- DEX `assets + asset_venues` rows become `registry_assets`;
- CEX `asset_venues` rows become `cex_tokens + price_feeds`;
- old `asset_market_snapshots` rows become `price_observations`;
- provider token prices become `price_observations`, not synthetic Markets or pools;
- no V4 runtime code may read old tables after the hard-cut branch is complete;
- Task 2 itself only creates the replacement schema, and the branch must not be released before Tasks 5-11 remove all old runtime reads/writes.

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

## Task 3: Registry, Discovery, And Price Observation Repositories

**Files:**

- Create: `src/gmgn_twitter_intel/storage/registry_repository.py`
- Create: `src/gmgn_twitter_intel/storage/discovery_repository.py`
- Create: `src/gmgn_twitter_intel/storage/price_observation_repository.py`
- Create: `src/gmgn_twitter_intel/storage/token_intent_lookup_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/repository_session.py`
- Test: `tests/test_registry_repository.py`
- Test: `tests/test_discovery_repository.py`
- Test: `tests/test_price_observation_repository.py`
- Test: `tests/test_token_intent_lookup_repository.py`

- [ ] **Step 1: Implement `RegistryRepository`**

Required methods:

```python
upsert_project(...)
upsert_chain_asset(...)
upsert_cex_token(...)
upsert_pricefeed(...)
upsert_alias(...)
find_projects_by_symbol(symbol)
find_assets_by_address(address, chain_id=None)
find_assets_by_chain_symbol(chain_id, symbol)
find_assets_by_symbol_with_latest_observation(symbol)
find_cex_token(base_symbol)
find_cex_pricefeed(exchange, native_market_id)
find_dex_token_pricefeed(provider, chain_id, address)
active_assets(rows)
write_registry_version(source, target_type, target_id, changed_at_ms)
```

The `active_assets()` filter returns only `status IN ('candidate', 'canonical')` and requires evidence:

```text
evidence_level IN ('trusted_registry', 'price_observation', 'sustained_activity', 'canonical')
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

- [ ] **Step 3: Implement `PriceObservationRepository`**

Required methods:

```python
insert_observation(provider, pricefeed_id, observed_at_ms, subject_type, subject_id, price_usd, price_quote, quote_symbol, price_basis, market_cap_usd, liquidity_usd, volume_24h_usd, open_interest_usd, holders, raw_payload)
latest_for_subject(subject_type, subject_id, at_or_before_ms)
latest_for_pricefeed(pricefeed_id, at_or_before_ms)
assets_needing_price_refresh(stale_before_ms, limit)
cex_tokens_needing_price_refresh(stale_before_ms, limit)
```

Use this repository for all current-stage provider prices. It must not create Market or pool identity. `price_basis='usd_like'` is valid for CEX `USD/USDT/USDC` quote markets; `price_basis='quote'` means `price_usd` is null and `price_quote` carries the native quote value.

- [ ] **Step 4: Implement `TokenIntentLookupRepository`**

Required methods:

```python
replace_lookup_keys(intent_id, event_id, keys, source_evidence_id, created_at_ms)
keys_for_intent(intent_id)
intents_for_lookup_keys(keys, limit)
```

Lookup keys are deterministic strings:

```text
symbol:<SYMBOL>
address:<family>:<chain_id_or_unknown>:<canonical_address>
cex_pricefeed:<exchange>:<native_market_id>
cex_token:<base_symbol>
dex_token:<provider>:<chain_id>:<canonical_address>
project_symbol:<SYMBOL>
```

- [ ] **Step 5: Wire repositories**

Modify `RepositorySession`:

```python
registry: RegistryRepository
discovery: DiscoveryRepository
price_observations: PriceObservationRepository
token_intent_lookup: TokenIntentLookupRepository
```

- [ ] **Step 6: Run repository tests**

```bash
uv run pytest tests/test_registry_repository.py tests/test_discovery_repository.py tests/test_price_observation_repository.py tests/test_token_intent_lookup_repository.py -q
```

Expected: passed.

- [ ] **Step 7: Commit repositories**

```bash
git add src/gmgn_twitter_intel/storage/registry_repository.py src/gmgn_twitter_intel/storage/discovery_repository.py src/gmgn_twitter_intel/storage/price_observation_repository.py src/gmgn_twitter_intel/storage/token_intent_lookup_repository.py src/gmgn_twitter_intel/storage/repository_session.py tests/test_registry_repository.py tests/test_discovery_repository.py tests/test_price_observation_repository.py tests/test_token_intent_lookup_repository.py
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
    cex_pricefeeds: list[CexPriceFeedKey]
    dex_tokens: list[DexTokenKey]
    chain_hints: list[str]
    venue_hints: list[str]
    intent_hints: list[str]
```

The extractor also exposes intent-level bundles:

```python
@dataclass(frozen=True, slots=True)
class MentionIntentKeys:
    parse_state: Literal[
        "EXACT_PRICEFEED_KEY",
        "EXACT_ADDRESS_KEY",
        "CONTEXTUAL_SYMBOL_KEY",
        "SYMBOL_ONLY",
        "NO_KEYS",
        "INVALID_KEYS",
    ]
    symbols: list[str]
    addresses: list[AddressKey]
    cex_pricefeeds: list[CexPriceFeedKey]
    dex_tokens: list[DexTokenKey]
    chain_hints: list[str]
    venue_hints: list[str]
    lookup_keys: list[str]
```

Grouping rules are intent-level:

```text
DEX/provider token URL + nearby symbol -> one asset intent plus price observation
CEX native instrument text + exchange hint -> one PriceFeed intent
valid CA/mint + chain hint + nearby cashtag -> one asset intent
valid CA/mint without chain + nearby cashtag -> one cross-chain address intent
exchange + base symbol without quote -> one CEX token intent
official project handle/domain + plain known alias -> one project intent
symbol-only -> one symbol intent
GMGN token payload chain + address -> one asset intent plus price observation
```

Invalid-shaped keys stay scoped to their own intent. A malformed address in the same tweet as `$PEPE` returns one `INVALID` intent plus one independent symbol-only intent.

Every extracted key must preserve `source_surface`: `primary`, `reference`, `quoted`, or provider payload. Tests must include a primary tweet containing `$FLOCK` with a quoted/reference surface containing `$VVV`; V4 must create two intents and the `$VVV` intent must be visibly marked as reference-surface evidence.

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
- CEX instrument forms: `PEPEUSDT`, `PEPE/USDT`, `TON-USDT-SWAP`, `1000PEPEUSDT`;
- chain hints;
- venue hints;
- DEX/provider token URLs when they expose chain + token address;
- author handle, mentioned handle, URL domain, and reference surface context keys.

Plain aliases without `$`, such as `uPeg` or `vvv`, are supported only when an official handle/domain or provider URL maps the surface to a known Project or CexToken. Do not enable broad lowercase ticker extraction.

- [ ] **Step 4: Persist lookup keys for reprocess**

Update `token_evidence_builder.py` and `token_intent_builder.py` so every intent has deterministic lookup keys derived from `MentionKeys`.

Rules:

```text
symbol-only -> symbol:<SYMBOL> and project_symbol:<SYMBOL>
official handle/domain alias -> project_handle:<handle> or project_domain:<domain>
chain + address -> address:<family>:<chain_id>:<canonical_address>
address without chain -> address:<family>:unknown:<canonical_address>
exchange + base symbol -> cex_token:<base_symbol>
native CEX instrument -> cex_pricefeed:<exchange>:<native_market_id>
DEX token URL -> dex_token:<provider>:<chain_id>:<canonical_address>
```

Write keys through `repos.token_intent_lookup.replace_lookup_keys(...)` during ingest. These keys are the only production mechanism for registry-update reprocess fanout.

- [ ] **Step 5: Run extraction tests**

```bash
uv run pytest tests/test_mention_key_extractor.py tests/test_entity_extractor.py tests/test_token_evidence_builder.py tests/test_token_intent_builder.py tests/test_token_intent_lookup_repository.py -q
```

Expected: passed.

- [ ] **Step 6: Commit extraction**

```bash
git add pyproject.toml uv.lock src/gmgn_twitter_intel/pipeline/mention_key_extractor.py src/gmgn_twitter_intel/pipeline/entity_extractor.py src/gmgn_twitter_intel/pipeline/token_evidence_builder.py src/gmgn_twitter_intel/pipeline/token_intent_builder.py src/gmgn_twitter_intel/storage/token_intent_lookup_repository.py tests/test_mention_key_extractor.py tests/test_entity_extractor.py tests/test_token_evidence_builder.py tests/test_token_intent_builder.py tests/test_token_intent_lookup_repository.py
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
CEX native price feed beats symbol
CEX token beats DEX symbol candidates
chain+address beats symbol
no-chain address never defaults to eth
symbol-only can resolve to market-dominant chain Asset
multiple active candidates without dominance returns AMBIGUOUS
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
    pricefeed_id: str | None
    reason_codes: list[str]
    candidate_ids: list[str]
    lookup_keys: list[str]
    discovery_tasks: list[DiscoveryTaskInput]
```

- [ ] **Step 3: Implement fixed priority table**

Implement resolver branches in this exact order:

```python
if keys.cex_pricefeed:
    resolve_cex_pricefeed()
elif keys.address and keys.chain:
    resolve_chain_address()
elif keys.address:
    resolve_address_across_tracked_chains()
elif keys.dex_token:
    resolve_dex_token_url()
elif keys.cex_token:
    resolve_cex_token()
elif keys.dex and keys.chain and keys.symbol:
    resolve_dex_chain_symbol()
elif keys.chain and keys.symbol:
    resolve_chain_symbol()
elif keys.symbol:
    resolve_symbol_by_cex_then_market_dominance()
else:
    nil("NO_RESOLVABLE_MENTION")
```

Each branch returns immediately.

Invalid address-shaped or pricefeed-shaped input returns `INVALID` from the matching branch and never falls through to symbol-only resolution.

`resolve_symbol_by_cex_then_market_dominance()` must use this KISS order:

```text
1. confirmed CEX token exists -> CexToken UNIQUE_BY_CONTEXT
2. no CEX token and one active chain Asset -> Asset UNIQUE_BY_CONTEXT
3. no CEX token and multiple active chain Assets -> apply Market Dominance Selector
4. dominance passes -> Asset UNIQUE_BY_CONTEXT with reason MARKET_DOMINANT_CHAIN_ASSET
5. dominance fails -> PROJECT_ONLY or AMBIGUOUS with visible candidates
```

Market Dominance Selector:

```python
def dominance_score(market_cap_usd, holders, liquidity_usd):
    return (
        Decimal("0.55") * log10_decimal((market_cap_usd or 0) + 1)
        + Decimal("0.30") * log10_decimal((holders or 0) + 1)
        + Decimal("0.15") * log10_decimal((liquidity_usd or 0) + 1)
    )
```

Eligibility gates:

```text
fresh provider observation
at least two of market_cap_usd / holders / liquidity_usd are present
top score - second score >= 1.0
top market_cap_usd >= 250000 OR top holders >= 1000 OR top liquidity_usd >= 100000
```

The selector writes `resolution_candidates` with the raw inputs and score. It must not hide the decision behind a generic confidence field.

- [ ] **Step 4: Enqueue discovery from resolver result**

`token_intent_resolver.py` persists resolution and then calls `repos.discovery.enqueue()` for every `DiscoveryTaskInput` when status is `AMBIGUOUS`, `NIL`, or `INVALID`.

- [ ] **Step 5: Persist V4 resolution fields**

`IntentResolutionRepository.insert_resolution()` writes:

```text
resolution_status
target_type
target_id
pricefeed_id
reason_codes_json
candidate_ids_json
lookup_keys_json
registry_version
record_status
is_current
superseded_at_ms
```

`resolution_status` contains only the six V4 enum values. `insert_resolution()` supersedes previous rows by setting `record_status='superseded'`, `is_current=false`, and `superseded_at_ms`, then inserts the new row with `is_current=true`.

The old `identity_status/confidence/asset_id/primary_venue_id` fields are not read or written by V4 projection.

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

## Task 6: Ingest Hard Cut And Precision

**Files:**

- Modify: `src/gmgn_twitter_intel/pipeline/ingest_service.py`
- Modify: `src/gmgn_twitter_intel/models.py`
- Modify: `src/gmgn_twitter_intel/collector/gmgn_token_payload.py`
- Modify: `src/gmgn_twitter_intel/market/okx_models.py`
- Modify: `src/gmgn_twitter_intel/market/okx_cex_client.py`
- Modify: `src/gmgn_twitter_intel/market/okx_dex_client.py`
- Modify: `src/gmgn_twitter_intel/market/gmgn_openapi_client.py`
- Test: `tests/test_ingest_service.py`
- Test: `tests/test_token_radar_v4_ingest_flow.py`
- Test: `tests/test_okx_clients.py`

- [ ] **Step 1: Remove `AssetRepository` from Token Radar ingest**

`IngestService` must depend on:

```python
registry: RegistryRepository
discovery: DiscoveryRepository
price_observations: PriceObservationRepository
token_intent_lookup: TokenIntentLookupRepository
intent_resolutions: IntentResolutionRepository
```

It must not instantiate `AssetRepository` and must not call:

```text
upsert_dex_asset
upsert_cex_instrument
insert_market_snapshot(asset_id, venue_id, ...)
candidates_for_symbol
candidates_for_ca
```

- [ ] **Step 2: Write GMGN payload into V4 registry and price observations**

GMGN `token_snapshot` with `chain + address` becomes:

```text
registry_assets asset:<chain>:<standard>:<address>
price_observations subject_type='Asset', subject_id=<asset_id>, provider='gmgn_ws_token_payload'
token_intent_resolutions target_type='Asset', target_id=<asset_id>, pricefeed_id=<pricefeed_id or null>
```

No code writes `asset_market_snapshots`. No code creates `market:dex:<chain>:gmgn_payload:<address>` from token payload alone.

- [ ] **Step 3: Convert provider price fields to Decimal/string**

Change model types and parser outputs:

```text
TokenSnapshot.price: Decimal | None
TokenSnapshot.previous_price: Decimal | None
TokenSnapshot.market_cap: Decimal | None
OKX/GMGN provider price-like fields: Decimal | None or string until repository insert
```

Tests assert exact round-trip for:

```python
Decimal("0.000000000123")
Decimal("0.00001234")
```

- [ ] **Step 4: Update watched-account alerts**

Account token alerts use `target_type + target_id`, not old `asset_id`. Alerts for `PROJECT_ONLY / AMBIGUOUS / NIL / INVALID` can be emitted as investigation alerts but must not claim a resolved Asset.

- [ ] **Step 5: Run ingest precision tests**

```bash
uv run pytest tests/test_ingest_service.py tests/test_token_radar_v4_ingest_flow.py tests/test_okx_clients.py tests/golden/test_token_radar_v4_deterministic_resolver.py::test_micro_price_remains_nonzero_in_price_observation tests/golden/test_token_radar_v4_deterministic_resolver.py::test_gmgn_payload_price_does_not_create_synthetic_market -q
```

Expected: passed.

- [ ] **Step 6: Commit ingest hard cut**

```bash
git add src/gmgn_twitter_intel/pipeline/ingest_service.py src/gmgn_twitter_intel/models.py src/gmgn_twitter_intel/collector/gmgn_token_payload.py src/gmgn_twitter_intel/market/okx_models.py src/gmgn_twitter_intel/market/okx_cex_client.py src/gmgn_twitter_intel/market/okx_dex_client.py src/gmgn_twitter_intel/market/gmgn_openapi_client.py tests/test_ingest_service.py tests/test_token_radar_v4_ingest_flow.py tests/test_okx_clients.py tests/golden/test_token_radar_v4_deterministic_resolver.py
git commit -m "feat: hard cut token radar ingest to v4 registry"
```

## Task 7: Discovery Worker And Reprocess Loop

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
cex_pricefeed_lookup
cex_token_lookup
dex_token_lookup
dex_price_lookup
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
load affected_lookup_keys_json from registry_versions
find intents through token_intent_lookup_keys
load event token evidence and lookup keys
rerun deterministic resolver
write new current token_intent_resolutions row
mark prior row record_status=superseded and is_current=false
enqueue projection rebuild dirty range
```

Forbidden:

```text
scan all unresolved intents for every registry update
match by raw tweet text
match by symbol substring
use old asset_id or primary_venue_id to find affected rows
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

## Task 8: Price Sync To Explicit PriceFeeds

**Files:**

- Modify: `src/gmgn_twitter_intel/pipeline/asset_market_sync.py`
- Modify: `src/gmgn_twitter_intel/pipeline/asset_market_sync_worker.py`
- Modify: `src/gmgn_twitter_intel/market/okx_cex_client.py`
- Modify: `src/gmgn_twitter_intel/market/okx_dex_client.py`
- Modify: `src/gmgn_twitter_intel/market/gmgn_openapi_client.py`
- Test: `tests/test_asset_market_sync.py`
- Test: `tests/test_price_observation_repository.py`

- [ ] **Step 1: Rewrite CEX sync**

Implement KISS CEX token registry sync:

```python
sync_cex_tokens_from_okx(...)
sync_cex_tokens_from_configured_source(...)
```

Do not introduce a provider abstraction layer before the second real provider needs it. The repository API is stable enough:

```python
upsert_cex_token(base_symbol, project_id, source, observed_at_ms)
upsert_cex_pricefeed(exchange, native_market_id, base_symbol, quote_symbol, inst_type, multiplier, observed_at_ms)
insert_price_observation(...)
```

Each sync writes:

```text
CexToken for base_symbol, e.g. cex_token:PEPE
PriceFeed for exchange + native_market_id
PriceObservation for pricefeed_id and CexToken subject
```

It must not create `asset:cex:*`.

Provider health gate:

```text
OKX public ticker/instrument sync must pass.
Binance or alternate CEX token source should be configured if Binance official tweets are important.
If Binance public API is unavailable in the runtime region, use a configured alternate trusted CEX token source; do not silently create a chain Asset before CEX token lookup.
```

Price basis rules:

```text
quote in USD/USDT/USDC -> price_usd = last_price, price_quote = last_price, price_basis = 'usd_like'
quote not in USD/USDT/USDC -> price_usd = null unless provider supplies USD, price_quote = last_price, price_basis = 'quote' or 'provider_usd'
1000/10000-style instruments -> normalize by pricefeed.multiplier before writing per-base display price
```

This intentionally does not do exact stablecoin FX conversion. Radar only needs a clearly marked `usd_like` display basis for USDT/USDC/USD quote markets such as `PEPE-USDT`.

- [ ] **Step 2: Rewrite DEX Asset price sync**

DEX Asset price sync reads recently-mentioned `registry_assets` that need refresh. It does not read `markets` or require DEX pool identity. The input shape is:

```text
registry_assets.chain_id
registry_assets.address
recent attention through current token_intent_resolutions.target_type='Asset'
latest price_observations(subject_type='Asset') older than stale threshold or missing
```

OKX DEX token-price responses keyed by `chainIndex + tokenContractAddress` write `price_observations(subject_type='Asset')`. They must not create or refresh a DEX pool Market in current-stage V4.

This is required because most live GMGN/X token mentions contain token address or symbol context, not pool identity. V4 current stage intentionally ignores DEX pool identity and preserves token-level prices through `price.observation`.

- [ ] **Step 3: Preserve numeric precision**

Provider adapters should keep price-like fields as string or Decimal until repository insert. Tests assert:

```python
Decimal("0.00001234")
```

round-trips through API as nonzero. Add tests for:

```text
PEPE-USDT CEX ticker -> price observation with price_basis='usd_like'
PEPE-BTC CEX ticker -> no fake USD price
DEX token price by token address -> price observation, no pool required
Binance official CAKE context -> CexToken when CEX token registry exists; otherwise market-dominant BSC Asset plus CEX discovery task
UPEG symbol-only with current candidates -> Ethereum Asset through MARKET_DOMINANT_CHAIN_ASSET
VVV symbol-only with current candidates -> Base Asset through MARKET_DOMINANT_CHAIN_ASSET unless confirmed CEX token exists
LFI symbol-only with current candidates -> Base Asset through MARKET_DOMINANT_CHAIN_ASSET when dominance gates pass
```

- [ ] **Step 4: Run price sync tests**

```bash
uv run pytest tests/test_asset_market_sync.py tests/test_price_observation_repository.py -q
```

Expected: passed.

- [ ] **Step 5: Commit price sync**

```bash
git add src/gmgn_twitter_intel/pipeline/asset_market_sync.py src/gmgn_twitter_intel/pipeline/asset_market_sync_worker.py src/gmgn_twitter_intel/market/okx_cex_client.py src/gmgn_twitter_intel/market/okx_dex_client.py src/gmgn_twitter_intel/market/gmgn_openapi_client.py tests/test_asset_market_sync.py tests/test_price_observation_repository.py
git commit -m "feat: sync token radar prices by pricefeed"
```

## Task 9: Token Radar Projection V4

**Files:**

- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/retrieval/opportunity_scoring.py`
- Modify/Delete: `src/gmgn_twitter_intel/retrieval/tradeability_scoring.py`
- Modify: `src/gmgn_twitter_intel/storage/token_radar_repository.py`
- Create: `src/gmgn_twitter_intel/retrieval/token_radar_service.py`
- Modify: `src/gmgn_twitter_intel/api/http.py`
- Test: `tests/test_token_radar_projection.py`
- Test: `tests/test_token_radar_service.py`
- Test: `tests/test_api_http.py`
- Test: `tests/test_opportunity_scoring.py`
- Delete/Replace: `tests/test_tradeability_scoring.py`

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
pricefeed_id
resolution_status
reason_codes_json
candidate_ids_json
lookup_keys_json
registry_version
```

It does not read:

```text
asset_id
primary_venue_id
asset_venues
asset_market_snapshots
```

Projection writes V4 fields:

```text
target_type
target_id
pricefeed_id
target_json
price_json.observation from latest price_observations
resolution_json.status
resolution_json.reason_codes
resolution_json.candidate_ids
resolution_json.lookup_keys
```

If old physical columns still exist in `token_radar_rows`, V4 writes them as `NULL` and no V4 reader consumes them.

- [ ] **Step 3: Join price observations**

Use `price_observations` and `price_feeds`.

Price status rules:

```text
PROJECT_ONLY -> no_price
AMBIGUOUS -> no_price
NIL -> no_price
INVALID -> invalid_identity
EXACT/UNIQUE_BY_CONTEXT with no observation -> pending_refresh
EXACT/UNIQUE_BY_CONTEXT with fresh observation -> ready
EXACT/UNIQUE_BY_CONTEXT with old observation -> stale
```

Projection includes the latest `price_observations` payload under `price_json.observation`:

```json
{
  "subject_type": "Asset",
  "subject_id": "asset:solana:token:...",
  "provider": "okx_dex_price",
  "observed_at_ms": 1778142883365,
  "price_usd": "0.00013157275348985763",
  "price_basis": "provider_usd"
}
```

This keeps token-level prices visible while preventing token-level prices from becoming pool or execution identity.

Observation usability:

```text
ready/stale is computed from venue-specific freshness thresholds
price_basis in ('exact_usd', 'provider_usd', 'usd_like') is usable for Radar display and decision timing
price_basis='quote' is display-only unless the quote itself is shown; it does not become USD timing
USDT/USDC/USD quote markets such as PEPE-USDT are usable as usd_like without exact FX conversion
```

- [ ] **Step 4: Replace tradeability score contract**

Current V3 projection computes a `tradeability` score and calls `_market_usable_for_driver(market)`. V4 must remove that runtime concept from Token Radar.

V4 score components are:

```text
heat
quality
propagation
price_health
timing
attention
```

Forbidden score inputs:

```text
tradeability
pool_status
pool_present
missing_pool
_market_usable_for_driver
tradeability_score(...)
```

`price_health` is display/readiness context only. It can lower attention when price is missing or stale, but it must not convert an Asset, CexToken, or PriceFeed into an execution target.

- [ ] **Step 5: Decision caps**

Implement:

```text
PROJECT_ONLY -> investigate
AMBIGUOUS -> investigate
NIL -> investigate
INVALID -> discard or investigate
price pending/missing -> max investigate
usable price can support watch/attention ranking, but does not create an execution target
```

- [ ] **Step 6: Add `/api/token-radar` service**

`TokenRadarService` reads `token_radar_rows` and returns:

```json
{
  "rows": [],
  "projection": {
    "source": "token_radar_rows",
    "version": "token-radar-v4"
  }
}
```

The response does not use old V3 names such as `resolved_assets`, `attention_candidates`, `asset`, or `primary_venue`.

`/api/asset-flow` is removed from Token Radar V4 runtime. If the route remains for unrelated historical tooling, V4 frontend and tests must not call it.

- [ ] **Step 7: Run projection/API tests**

```bash
uv run pytest tests/test_token_radar_projection.py tests/test_token_radar_service.py tests/test_api_http.py tests/test_opportunity_scoring.py tests/golden/test_token_radar_v4_deterministic_resolver.py -q
```

Expected: passed.

- [ ] **Step 8: Commit projection**

```bash
git add src/gmgn_twitter_intel/pipeline/token_radar_projection.py src/gmgn_twitter_intel/storage/token_radar_repository.py src/gmgn_twitter_intel/retrieval/token_radar_service.py src/gmgn_twitter_intel/retrieval/opportunity_scoring.py src/gmgn_twitter_intel/retrieval/tradeability_scoring.py src/gmgn_twitter_intel/api/http.py tests/test_token_radar_projection.py tests/test_token_radar_service.py tests/test_api_http.py tests/test_opportunity_scoring.py tests/test_tradeability_scoring.py tests/golden/test_token_radar_v4_deterministic_resolver.py
git commit -m "feat: project token radar from deterministic resolutions"
```

## Task 10: Target-Aware API And Frontend Render-Only Contract

**Files:**

- Create: `src/gmgn_twitter_intel/retrieval/token_target_posts_service.py`
- Create: `src/gmgn_twitter_intel/retrieval/token_target_timeline_service.py`
- Modify: `src/gmgn_twitter_intel/api/http.py`
- Modify: `web/src/App.tsx`
- Modify: `web/src/api/types.ts`
- Modify: `web/src/components/ScoreLedger.tsx`
- Test: `tests/test_token_target_posts_service.py`
- Test: `tests/test_token_target_timeline_service.py`
- Test: `tests/test_api_http.py`
- Test: `web/src/App.test.tsx`

- [ ] **Step 1: Add target-aware backend contract**

Add APIs:

```bash
GET /api/token-radar?window=5m&scope=all&limit=120
GET /api/token-radar-target-posts?target_type=Asset&target_id=...&window=5m&scope=all
GET /api/token-radar-target-timeline?target_type=Project&target_id=...&window=1h&scope=all
```

Rules:

```text
Project target -> evidence and posts linked by project/CexToken/asset candidates
Asset target -> asset-specific posts and price observations when available
CexToken target -> CEX token posts and CEX price observations when available
PriceFeed target -> provider feed observations and linked subject posts
AMBIGUOUS/NIL/INVALID -> evidence/discovery state only
```

V4 frontend must not call `/api/asset-posts` or `/api/asset-social-timeline`.

- [ ] **Step 2: Add API types**

Types include:

```ts
type ResolutionStatus = "EXACT" | "UNIQUE_BY_CONTEXT" | "PROJECT_ONLY" | "AMBIGUOUS" | "NIL" | "INVALID";
type TargetType = "Project" | "Asset" | "CexToken" | "PriceFeed" | null;
type ScoreComponent = "heat" | "quality" | "propagation" | "price_health" | "timing" | "attention";
```

Remove Token Radar V3 fields from frontend types: `tradeability`, `pool_status`, `primary_venue`, `asset_id` as row identity.

- [ ] **Step 3: Remove decision synthesis**

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
- reconstructing `pool_status` from DEX address presence.
- rendering Token Radar score blocks labeled `Tradeability`.
- treating `driver` as an execution affordance.

- [ ] **Step 4: Add UI regressions**

Tests:

```text
PROJECT_ONLY row remains investigate
AMBIGUOUS high heat row remains investigate
pending price row remains investigate/watch according to backend decision
price observation does not create execution panel
score ledger shows price_health/attention, not Tradeability
USDT/USDC/USD CEX quote row shows usd_like price basis
non-stable quote CEX row does not show quote price as USD
nonzero micro price does not render $0
address ending musk does not show MUSK as symbol
PROJECT_ONLY drawer does not call asset detail APIs
AMBIGUOUS drawer shows candidate/discovery state
```

- [ ] **Step 5: Run backend and frontend tests**

```bash
uv run pytest tests/test_token_target_posts_service.py tests/test_token_target_timeline_service.py tests/test_api_http.py -q
npm --prefix web test -- --run
npm --prefix web run build
```

Expected: passed and built.

- [ ] **Step 6: Commit target-aware UI**

```bash
git add src/gmgn_twitter_intel/retrieval/token_target_posts_service.py src/gmgn_twitter_intel/retrieval/token_target_timeline_service.py src/gmgn_twitter_intel/api/http.py web/src/App.tsx web/src/api/types.ts web/src/App.test.tsx tests/test_token_target_posts_service.py tests/test_token_target_timeline_service.py tests/test_api_http.py
git commit -m "feat: render deterministic token radar states"
```

## Task 11: Remove Old Runtime Paths

**Files:**

- Modify: `src/gmgn_twitter_intel/api/app.py`
- Modify: `src/gmgn_twitter_intel/api/ws.py`
- Modify: `src/gmgn_twitter_intel/api/http.py`
- Modify: `src/gmgn_twitter_intel/pipeline/ingest_service.py`
- Modify: `src/gmgn_twitter_intel/pipeline/token_intent_resolver.py`
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/pipeline/asset_market_sync.py`
- Modify: `src/gmgn_twitter_intel/retrieval/token_radar_service.py`
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
AssetRepository.upsert_dex_asset
AssetRepository.upsert_cex_instrument
AssetRepository.insert_market_snapshot
market:dex:* synthetic Market IDs in current-stage Token Radar
tradeability_scoring.py from Token Radar runtime
TradingAttentionService from Token Radar runtime
pool_status in Token Radar API/UI types
Tradeability score labels in Token Radar UI
/api/asset-posts from Token Radar UI
/api/asset-social-timeline from Token Radar UI
/api/asset-flow from Token Radar UI
resolution_status <> 'superseded'
```

Migration files may mention old names; runtime files may not.

- [ ] **Step 2: Update notifications**

Notifications read `token_radar_rows.decision`, `resolution.target_type`, `price.price_status`.

They do not recompute identity, price state, or decision.

They use `target_type + target_id` as the notification identity key. `PROJECT_ONLY`, `AMBIGUOUS`, `NIL`, and `INVALID` can notify as investigation states but cannot be promoted by notification code.

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
price_status_counts
reprocess_success_rate
old_runtime_path_import_count
old_runtime_sql_reference_count
old_frontend_asset_drilldown_call_count
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

## Task 12: Full Verification And Docker Runtime

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
curl -fsS "http://127.0.0.1:8000/api/token-radar?window=5m&scope=all&limit=120" | jq '.projection'
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
  "price_status_counts": {},
  "old_runtime_path_import_count": 0,
  "old_runtime_sql_reference_count": 0,
  "old_frontend_asset_drilldown_call_count": 0
}
```

- [ ] **Step 7: Manual exit-gate scan**

Run:

```bash
curl -fsS "http://127.0.0.1:8000/api/token-radar?window=5m&scope=all&limit=120" \
  | jq '.rows | map({symbol: .target.symbol, target_type: .target.target_type, status: .resolution.status, reasons: .resolution.reason_codes, price: .price.price_status, decision})'
```

Check:

- `$SYMBOL` only rows can be `CexToken UNIQUE_BY_CONTEXT`, market-dominant `Asset UNIQUE_BY_CONTEXT`, `PROJECT_ONLY`, `AMBIGUOUS`, or `NIL`;
- no symbol-only row is `Asset EXACT`;
- CEX native instrument rows have `target_type="PriceFeed"`;
- CEX token rows have `target_type="CexToken"`;
- unresolved hot rows are `investigate`;
- no pending/no-price row is promoted by UI;
- no Token Radar row exposes `pool_status`, `Tradeability`, or execution affordances;
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
- [ ] `/api/token-radar` reports `token-radar-v4`.
- [ ] `old_runtime_path_import_count` is zero.
- [ ] `old_runtime_sql_reference_count` is zero for Token Radar runtime files.
- [ ] Token Radar frontend has zero calls to Asset-only drilldown APIs.
- [ ] `resolution_status` has only V4 enum values; lifecycle uses `record_status/is_current`.
- [ ] V4 ingest and price sync write provider prices to `price_observations`; current-stage V4 does not write `market_snapshots` or DEX pool Markets; never writes `asset_market_snapshots`.
- [ ] Token Radar V4 runtime has no `tradeability_score`, `pool_status`, `Tradeability` label, or pool-based ranking component.
- [ ] CEX `USD/USDT/USDC` quote prices are marked `usd_like`; non-stable quote prices are not treated as USD without provider basis.
- [ ] Provider price-like fields preserve Decimal/string precision end to end.
- [ ] Reprocess fanout is proven through `token_intent_lookup_keys`, not unresolved-intent scans.
- [ ] Live 5m rows explain unknowns through enum status and reason codes.
- [ ] `Discovery -> Registry Update -> Reprocess` is proven by test and runtime audit.
