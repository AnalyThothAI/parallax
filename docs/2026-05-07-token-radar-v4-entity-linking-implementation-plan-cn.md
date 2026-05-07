# Token Radar V4 Entity Linking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade Token Radar identity pipeline where Twitter/GMGN token mentions become event-level intents, intents resolve through auditable entity linking, venues map to precise market observations, and unresolved/ambiguous rows are explainable instead of silently leaking as `UNKNOWN`, address-only symbols, or wrong `driver` decisions.

**Architecture:** Keep the V3 intent-first spine, but split entity linking into explicit bounded modules: chain parsers, mention facts, intent linker, candidate generator/ranker, resolver, provider observations, venue market snapshots, and backend-owned Radar projection. Hard-cut all mention-level attribution and frontend decision compatibility paths from Token Radar runtime.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic/psycopg, pytest, ruff, eth-utils, solders, tonsdk, FastAPI, TypeScript, React, Vite, Vitest, Docker Compose.

---

## Implementation Stance

This plan implements the V4 spec:

- `docs/2026-05-07-token-radar-v4-entity-linking-production-spec-cn.md`

The plan is deliberately hard-cut:

- no fallback to `asset_mentions` or `asset_attributions`;
- no fake unresolved/ambiguous assets;
- no symbol resolution from observed/social aliases;
- no frontend Radar decision calculation;
- no crypto resolution for stock-only cashtags;
- no regex-only TON address parsing;
- no market status collapse into one generic missing state.

## Current Code Map

Keep and extend:

- `src/gmgn_twitter_intel/pipeline/entity_extractor.py`: already span-aware for EVM/Solana/cashtags; needs TON, segment grouping, stock/crypto class hints, URL address extraction.
- `src/gmgn_twitter_intel/pipeline/token_evidence_builder.py`: already builds token evidence; needs mention class fields and stock separation.
- `src/gmgn_twitter_intel/pipeline/token_intent_builder.py`: keep as orchestration shell, move linking to a new linker module.
- `src/gmgn_twitter_intel/pipeline/token_intent_resolver.py`: keep public resolver facade, replace direct alias lookup with candidate resolver.
- `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`: keep materialized read model, upgrade version/status/candidate audit.
- `src/gmgn_twitter_intel/storage/asset_repository.py`: keep registry/venue writes; enforce alias scope.
- `src/gmgn_twitter_intel/storage/token_radar_repository.py`: keep read/write table repository.
- `src/gmgn_twitter_intel/market/gmgn_openapi_client.py`: keep exact token info lookup.
- `src/gmgn_twitter_intel/market/okx_dex_client.py`: keep DEX search/price adapter.
- `web/src/App.tsx`: keep UI view model, ensure it renders backend state only.

Create:

- `src/gmgn_twitter_intel/pipeline/chain_address_parser.py`
- `src/gmgn_twitter_intel/pipeline/token_mention.py`
- `src/gmgn_twitter_intel/pipeline/token_intent_linker.py`
- `src/gmgn_twitter_intel/pipeline/identity_candidate_resolver.py`
- `src/gmgn_twitter_intel/pipeline/identity_resolution_worker.py`
- `src/gmgn_twitter_intel/pipeline/stock_instrument_resolver.py`
- `src/gmgn_twitter_intel/storage/provider_observation_repository.py`
- `src/gmgn_twitter_intel/storage/stock_instrument_repository.py`
- `src/gmgn_twitter_intel/storage/alembic/versions/20260507_0008_token_radar_v4_entity_linking.py`
- `tests/factories_token_radar_v4.py`
- `tests/golden/test_token_radar_v4_entity_linking.py`
- `tests/test_chain_address_parser.py`
- `tests/test_token_intent_linker.py`
- `tests/test_identity_candidate_resolver.py`
- `tests/test_provider_observation_repository.py`
- `tests/test_stock_instrument_resolver.py`

## Task 1: Add V4 Golden Corpus

**Files:**

- Create: `tests/factories_token_radar_v4.py`
- Create: `tests/golden/test_token_radar_v4_entity_linking.py`
- Modify: `tests/test_token_radar_projection.py`

- [ ] **Step 1: Create V4 test factory**

Add `tests/factories_token_radar_v4.py`:

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
ADDRESS_SUFFIX_MUSK = "8561484D1111111111111111111111111111117F7musk"
TON_FRIENDLY_CA = "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c"


def make_event(
    event_id: str,
    *,
    text: str,
    received_at_ms: int = 1_777_800_000_000,
    author_handle: str = "alpha",
    is_watched: bool = True,
) -> TwitterEvent:
    return TwitterEvent(
        event_id=event_id,
        source=Source(provider="gmgn", transport="direct_ws", coverage="public_stream", channel="twitter_monitor_basic"),
        action="tweet",
        original_action=None,
        tweet_id=event_id,
        internal_id=event_id,
        timestamp=received_at_ms // 1000,
        received_at_ms=received_at_ms,
        author=Author(handle=author_handle, name=author_handle, avatar=None, followers=10_000, tags=[]),
        content=Content(text=text, media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=[author_handle] if is_watched else [],
        raw={"id": event_id},
    )


def make_payload_event(
    event_id: str,
    *,
    symbol: str,
    chain: str,
    address: str,
    price: str = "0.00001234",
    market_cap: str = "123456.78",
    received_at_ms: int = 1_777_800_000_000,
) -> TwitterEvent:
    snapshot = parse_gmgn_token_payload(
        {
            "tt": "ca",
            "t": {
                "a": address,
                "c": chain,
                "mc": market_cap,
                "p": price,
                "s": symbol,
                "liquidity": "45678.9",
                "holder_count": 3210,
            },
        }
    )
    return replace(
        make_event(event_id, text=f"${symbol} payload", received_at_ms=received_at_ms),
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

- [ ] **Step 2: Add failing golden tests**

Add `tests/golden/test_token_radar_v4_entity_linking.py`:

```python
from __future__ import annotations

from gmgn_twitter_intel.pipeline.token_radar_projection import TokenRadarProjection
from tests.factories_token_radar_v4 import (
    ADDRESS_SUFFIX_MUSK,
    MOONCLUB_SOL_CA,
    PEPE_ETH_CA,
    TON_FRIENDLY_CA,
    VERSA_BASE_CA,
    make_event,
    make_payload_event,
    open_v4_runtime,
)


def test_versa_symbol_and_base_ca_resolve_to_one_intent(tmp_path):
    _, repos, ingest = open_v4_runtime(tmp_path)
    repos.assets.upsert_dex_asset(
        chain="base",
        address=VERSA_BASE_CA,
        symbol="VERSA",
        event_id=None,
        observed_at_ms=1_777_799_000_000,
        provider="fixture",
        commit=True,
    )

    result = ingest.ingest_event(
        make_event("event-versa", text=f"很不错的一个项目，挺有格局的dev， $VERSA {VERSA_BASE_CA}"),
        is_watched=True,
    )

    intents = repos.token_intents.intents_for_event("event-versa")
    resolutions = repos.intent_resolutions.resolutions_for_event("event-versa")
    assert len(intents) == 1
    assert intents[0]["display_symbol"] == "VERSA"
    assert intents[0]["address_hint"].lower() == VERSA_BASE_CA
    assert len(resolutions) == 1
    assert resolutions[0]["identity_status"] == "resolved"
    assert result.token_resolutions[0]["primary_venue_id"] == f"venue:dex:base:{VERSA_BASE_CA}"


def test_decimal_heavy_text_pairs_single_symbol_with_single_solana_ca(tmp_path):
    _, repos, ingest = open_v4_runtime(tmp_path)
    event = make_event(
        "event-moonclub",
        text=f"$MOONCLUB result: 4.1xX 90K -> 371K Time: 3h {MOONCLUB_SOL_CA} Source: SOLANA",
    )

    ingest.ingest_event(event, is_watched=True)
    intents = repos.token_intents.intents_for_event("event-moonclub")

    assert len(intents) == 1
    assert intents[0]["display_symbol"] == "MOONCLUB"
    assert intents[0]["chain_hint"] == "solana"
    assert intents[0]["address_hint"] == MOONCLUB_SOL_CA


def test_symbol_only_mask_with_stock_collision_is_not_crypto_resolved(tmp_path):
    _, repos, ingest = open_v4_runtime(tmp_path)
    repos.stock_instruments.upsert_instrument(
        symbol="MASK",
        exchange="nasdaq",
        name="Mask Network Stock Fixture",
        source="exchange_symbol_directory",
        observed_at_ms=1_777_799_000_000,
        commit=True,
    )

    ingest.ingest_event(make_event("event-mask", text="$MASK ripping"), is_watched=True)
    resolution = repos.intent_resolutions.resolutions_for_event("event-mask")[0]

    assert resolution["identity_status"] in {"ambiguous", "unresolved"}
    assert "stock_crypto_symbol_collision" in resolution["risks_json"] or "stock_ticker_candidate" in resolution["reasons_json"]
    assert resolution["asset_id"] is None


def test_ton_friendly_address_becomes_ton_ca_mention(tmp_path):
    _, repos, ingest = open_v4_runtime(tmp_path)

    ingest.ingest_event(make_event("event-ton", text=f"$TONALPHA {TON_FRIENDLY_CA}"), is_watched=True)
    evidence = repos.token_evidence.evidence_for_event("event-ton")

    ton_ca = next(item for item in evidence if item["evidence_type"] == "ca")
    assert ton_ca["chain_hint"] == "ton"
    assert ton_ca["address_hint"]


def test_solana_address_suffix_is_not_used_as_symbol(tmp_path):
    _, repos, ingest = open_v4_runtime(tmp_path)

    ingest.ingest_event(make_payload_event("event-musk-address", symbol=ADDRESS_SUFFIX_MUSK, chain="sol", address=ADDRESS_SUFFIX_MUSK), is_watched=True)
    TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=1_777_800_060_000)
    row = repos.token_radar.latest_rows(window="5m", scope="all", limit=10)[0]

    assert row["asset_json"]["symbol"] is None
    assert row["primary_venue_json"]["address"] == ADDRESS_SUFFIX_MUSK


def test_no_chain_evm_ca_with_multiple_chain_matches_is_ambiguous(tmp_path):
    _, repos, ingest = open_v4_runtime(tmp_path)
    for chain in ("eth", "base"):
        repos.assets.upsert_dex_asset(
            chain=chain,
            address=PEPE_ETH_CA,
            symbol="PEPE",
            event_id=None,
            observed_at_ms=1_777_799_000_000,
            provider="fixture",
            commit=True,
        )

    ingest.ingest_event(make_event("event-pepe-no-chain", text=f"watch this {PEPE_ETH_CA}"), is_watched=True)
    resolution = repos.intent_resolutions.resolutions_for_event("event-pepe-no-chain")[0]

    assert resolution["identity_status"] == "ambiguous"
    assert "chain_required_for_exact_ca" in resolution["risks_json"]


def test_micro_price_is_projected_without_zero_rounding(tmp_path):
    _, repos, ingest = open_v4_runtime(tmp_path)

    ingest.ingest_event(
        make_payload_event("event-micro", symbol="MICRO", chain="eth", address=PEPE_ETH_CA, price="0.00001234"),
        is_watched=True,
    )
    TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=1_777_800_060_000)
    row = repos.token_radar.latest_rows(window="5m", scope="all", limit=10)[0]

    assert row["market_json"]["price_usd"] == 0.00001234
    assert row["decision"] in {"driver", "watch"}
```

- [ ] **Step 3: Run golden tests and confirm failures**

Run:

```bash
uv run pytest tests/golden/test_token_radar_v4_entity_linking.py -q
```

Expected now:

```text
FAILED ... stock_instruments
FAILED ... TON
FAILED ... alias/candidate resolution
```

The failures prove the test suite is hitting missing V4 capabilities, not fixture wiring.

- [ ] **Step 4: Commit golden corpus**

```bash
git add tests/factories_token_radar_v4.py tests/golden/test_token_radar_v4_entity_linking.py
git commit -m "test: add token radar v4 entity linking corpus"
```

## Task 2: Chain Address Parser And Token Mention Model

**Files:**

- Create: `src/gmgn_twitter_intel/pipeline/chain_address_parser.py`
- Create: `src/gmgn_twitter_intel/pipeline/token_mention.py`
- Modify: `src/gmgn_twitter_intel/pipeline/entity_extractor.py`
- Modify: `src/gmgn_twitter_intel/pipeline/token_evidence_builder.py`
- Modify: `pyproject.toml`
- Test: `tests/test_chain_address_parser.py`
- Test: `tests/test_entity_extractor.py`
- Test: `tests/test_token_evidence_builder.py`

- [ ] **Step 1: Add maintained TON parser dependency**

Run:

```bash
uv add tonsdk
```

Expected:

```text
Resolved ...
Updated pyproject.toml
Updated uv.lock
```

- [ ] **Step 2: Write parser tests**

Add `tests/test_chain_address_parser.py`:

```python
from __future__ import annotations

import pytest

from gmgn_twitter_intel.pipeline.chain_address_parser import parse_chain_address


def test_parse_evm_checksum_address_without_defaulting_chain():
    parsed = parse_chain_address("0x2cc0db4f8977accadb5b7da59c5923e14328eba3")

    assert parsed.chain == "evm_unknown"
    assert parsed.address == "0x2Cc0dB4f8977AccaDB5b7da59C5923e14328EbA3"
    assert parsed.address_family == "evm"


def test_parse_solana_pubkey_keeps_pump_suffix_as_address_chars():
    parsed = parse_chain_address("69PzM2hDa3MCo7cvKPgiPxhr1FdGdMV3S7h6wpRkpump")

    assert parsed.chain == "solana"
    assert parsed.address == "69PzM2hDa3MCo7cvKPgiPxhr1FdGdMV3S7h6wpRkpump"
    assert parsed.display_symbol is None


def test_parse_ton_friendly_address():
    parsed = parse_chain_address("EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c")

    assert parsed.chain == "ton"
    assert parsed.address
    assert parsed.address_family == "ton"


def test_reject_plain_symbol_as_address():
    with pytest.raises(ValueError):
        parse_chain_address("MASK")
```

- [ ] **Step 3: Create parser implementation**

Add `src/gmgn_twitter_intel/pipeline/chain_address_parser.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from eth_utils import is_address, to_checksum_address
from solders.pubkey import Pubkey
from tonsdk.utils import Address


@dataclass(frozen=True, slots=True)
class ParsedChainAddress:
    address_family: str
    chain: str
    address: str
    display_symbol: str | None = None


def parse_chain_address(value: str, *, chain_hint: str | None = None) -> ParsedChainAddress:
    text = value.strip()
    chain = _normalize_chain(chain_hint)
    if is_address(text):
        return ParsedChainAddress(address_family="evm", chain=chain or "evm_unknown", address=to_checksum_address(text))

    try:
        pubkey = Pubkey.from_string(text)
    except ValueError:
        pubkey = None
    if pubkey is not None:
        return ParsedChainAddress(address_family="solana", chain="solana", address=str(pubkey))

    try:
        ton = Address(text)
    except Exception as exc:
        raise ValueError(f"invalid chain address: {value}") from exc
    return ParsedChainAddress(address_family="ton", chain="ton", address=ton.to_string(is_user_friendly=True))


def _normalize_chain(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"", "unknown", "evm"}:
        return None
    if normalized in {"ethereum", "erc20"}:
        return "eth"
    if normalized in {"sol", "solana"}:
        return "solana"
    if normalized in {"ton", "toncoin"}:
        return "ton"
    return normalized
```

- [ ] **Step 4: Create mention dataclass**

Add `src/gmgn_twitter_intel/pipeline/token_mention.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TokenMentionInput:
    mention_id: str
    event_id: str
    surface: str
    mention_type: str
    raw_value: str
    normalized_symbol: str | None
    normalized_address: str | None
    chain_hint: str | None
    asset_class_hint: str
    span_start: int
    span_end: int
    sentence_id: int
    segment_id: int
    source_kind: str
    source_id: str
    confidence: float
    created_at_ms: int
```

- [ ] **Step 5: Refactor extractor to call parser**

Modify `src/gmgn_twitter_intel/pipeline/entity_extractor.py`:

```python
from .chain_address_parser import parse_chain_address
```

Replace `_evm_ca_entity()` and `_solana_ca_entity()` usage inside `_extract_surface_entities()` with:

```python
parsed = parse_chain_address(raw, chain_hint=_chain_for_evm_ca(text, raw=raw, start=match.start(), end=match.end()))
_append_unique(
    entities,
    seen,
    _with_span(
        ExtractedEntity(
            "ca",
            raw,
            parsed.address,
            parsed.chain,
            "resolved_ca" if parsed.chain != "evm_unknown" else "unresolved_chain_ca",
            1.0,
            "chain_address_parser",
        ),
        surface=surface.surface,
        text=text,
        start=match.start(),
        end=match.end(),
    ),
)
```

Add TON detection with a bounded regex candidate followed by parser validation:

```python
TON_CA_RE = re.compile(r"(?<![A-Za-z0-9_-])(?:EQ|UQ)[A-Za-z0-9_-]{46,60}(?![A-Za-z0-9_-])")
```

For each match:

```python
raw = match.group(0)
try:
    parsed = parse_chain_address(raw, chain_hint="ton")
except ValueError:
    continue
_append_unique(
    entities,
    seen,
    _with_span(
        ExtractedEntity("ca", raw, parsed.address, "ton", "resolved_ca", 1.0, "chain_address_parser"),
        surface=surface.surface,
        text=text,
        start=match.start(),
        end=match.end(),
    ),
)
```

- [ ] **Step 6: Replace sentence-only locality with segment id**

Modify `_sentence_id()` into segment logic that does not split decimal numbers:

```python
def _sentence_id(text: str, offset: int) -> int:
    segment = 0
    for index, char in enumerate(text[: max(0, offset)]):
        if char == "\n":
            segment += 1
            continue
        if char in {"。", "！", "？"}:
            segment += 1
            continue
        if char in {"!", "?"}:
            segment += 1
            continue
        if char == "." and not _between_digits(text, index):
            segment += 1
    return segment


def _between_digits(text: str, index: int) -> bool:
    before = text[index - 1] if index > 0 else ""
    after = text[index + 1] if index + 1 < len(text) else ""
    return before.isdigit() and after.isdigit()
```

- [ ] **Step 7: Run parser/extractor tests**

Run:

```bash
uv run pytest tests/test_chain_address_parser.py tests/test_entity_extractor.py tests/test_token_evidence_builder.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit parser and mention model**

```bash
git add pyproject.toml uv.lock src/gmgn_twitter_intel/pipeline/chain_address_parser.py src/gmgn_twitter_intel/pipeline/token_mention.py src/gmgn_twitter_intel/pipeline/entity_extractor.py src/gmgn_twitter_intel/pipeline/token_evidence_builder.py tests/test_chain_address_parser.py tests/test_entity_extractor.py tests/test_token_evidence_builder.py
git commit -m "feat: add token radar v4 chain parsers"
```

## Task 3: V4 Schema And Registry Hard Cut

**Files:**

- Create: `src/gmgn_twitter_intel/storage/alembic/versions/20260507_0008_token_radar_v4_entity_linking.py`
- Create: `src/gmgn_twitter_intel/storage/provider_observation_repository.py`
- Create: `src/gmgn_twitter_intel/storage/stock_instrument_repository.py`
- Modify: `src/gmgn_twitter_intel/storage/repository_session.py`
- Modify: `tests/test_postgres_schema.py`
- Modify: `tests/test_postgres_schema_runtime.py`
- Test: `tests/test_provider_observation_repository.py`
- Test: `tests/test_stock_instrument_resolver.py`

- [ ] **Step 1: Write schema assertions**

Add to `tests/test_postgres_schema.py`:

```python
def test_v4_entity_linking_schema_present():
    text = _migration_text("20260507_0008_token_radar_v4_entity_linking.py")
    assert "ALTER TABLE asset_aliases ADD COLUMN IF NOT EXISTS alias_scope" in text
    assert "provider_identity_observations" in text
    assert "stock_instruments" in text
    assert "financial_instrument_mentions" in text
    assert "score_components_json" in text
    assert "asset_class" in text
    assert "DELETE FROM assets" in text
```

Add to `tests/test_postgres_schema_runtime.py`:

```python
def test_v4_runtime_tables_and_columns(conn):
    names = {row["table_name"] for row in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    assert "provider_identity_observations" in names
    assert "stock_instruments" in names
    assert "financial_instrument_mentions" in names

    alias_columns = {
        row["column_name"]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'asset_aliases'"
        )
    }
    assert "alias_scope" in alias_columns
```

- [ ] **Step 2: Add migration**

Add `src/gmgn_twitter_intel/storage/alembic/versions/20260507_0008_token_radar_v4_entity_linking.py`:

```python
"""Add Token Radar V4 entity linking schema."""

from __future__ import annotations

from alembic import op

revision = "20260507_0008"
down_revision = "20260507_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE asset_aliases ADD COLUMN IF NOT EXISTS alias_scope TEXT NOT NULL DEFAULT 'provider'")
    op.execute("ALTER TABLE token_evidence ADD COLUMN IF NOT EXISTS asset_class_hint TEXT NOT NULL DEFAULT 'crypto'")
    op.execute("ALTER TABLE token_intents ADD COLUMN IF NOT EXISTS asset_class_hint TEXT NOT NULL DEFAULT 'crypto'")
    op.execute("ALTER TABLE token_intents ADD COLUMN IF NOT EXISTS linking_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE token_intents ADD COLUMN IF NOT EXISTS linking_risks_json JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE token_intent_resolution_candidates ADD COLUMN IF NOT EXISTS asset_class TEXT")
    op.execute("ALTER TABLE token_intent_resolution_candidates ADD COLUMN IF NOT EXISTS candidate_source TEXT")
    op.execute("ALTER TABLE token_intent_resolution_candidates ADD COLUMN IF NOT EXISTS score_components_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute(
        """
        UPDATE asset_aliases
        SET alias_scope = CASE
          WHEN alias_type = 'ca' THEN 'provider'
          WHEN source IN ('gmgn', 'okx', 'okx_cex', 'okx_dex', 'fixture') THEN 'provider'
          WHEN source IN ('curated', 'canonical') THEN 'canonical'
          ELSE 'observed'
        END
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_asset_aliases_symbol_scope ON asset_aliases(alias_type, normalized_alias, alias_scope)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_identity_observations (
          observation_id TEXT PRIMARY KEY,
          provider TEXT NOT NULL,
          request_kind TEXT NOT NULL,
          request_key TEXT NOT NULL,
          chain_hint TEXT,
          address_hint TEXT,
          symbol_hint TEXT,
          status TEXT NOT NULL,
          candidate_count BIGINT NOT NULL DEFAULT 0,
          raw_payload_hash TEXT,
          raw_payload_json JSONB,
          error_code TEXT,
          error_message TEXT,
          observed_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_provider_identity_observations_lookup
          ON provider_identity_observations(provider, request_kind, request_key, observed_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_instruments (
          instrument_id TEXT PRIMARY KEY,
          symbol TEXT NOT NULL,
          exchange TEXT NOT NULL,
          name TEXT,
          source TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          observed_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_stock_instruments_exchange_symbol ON stock_instruments(exchange, symbol)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stock_instruments_symbol ON stock_instruments(symbol)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS financial_instrument_mentions (
          mention_id TEXT PRIMARY KEY,
          event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
          instrument_id TEXT REFERENCES stock_instruments(instrument_id) ON DELETE SET NULL,
          symbol TEXT NOT NULL,
          exchange TEXT,
          status TEXT NOT NULL,
          reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_financial_instrument_mentions_event ON financial_instrument_mentions(event_id)")
    op.execute(
        """
        DELETE FROM asset_aliases
        WHERE asset_id IN (
          SELECT asset_id FROM assets
          WHERE identity_status IN ('unresolved', 'ambiguous')
             OR asset_id LIKE 'asset:unresolved:%'
             OR asset_id LIKE 'asset:ambiguous:%'
        )
        """
    )
    op.execute(
        """
        DELETE FROM assets
        WHERE identity_status IN ('unresolved', 'ambiguous')
           OR asset_id LIKE 'asset:unresolved:%'
           OR asset_id LIKE 'asset:ambiguous:%'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_financial_instrument_mentions_event")
    op.execute("DROP TABLE IF EXISTS financial_instrument_mentions")
    op.execute("DROP INDEX IF EXISTS idx_stock_instruments_symbol")
    op.execute("DROP INDEX IF EXISTS ux_stock_instruments_exchange_symbol")
    op.execute("DROP TABLE IF EXISTS stock_instruments")
    op.execute("DROP INDEX IF EXISTS idx_provider_identity_observations_lookup")
    op.execute("DROP TABLE IF EXISTS provider_identity_observations")
    op.execute("DROP INDEX IF EXISTS idx_asset_aliases_symbol_scope")
    op.execute("ALTER TABLE token_intent_resolution_candidates DROP COLUMN IF EXISTS score_components_json")
    op.execute("ALTER TABLE token_intent_resolution_candidates DROP COLUMN IF EXISTS candidate_source")
    op.execute("ALTER TABLE token_intent_resolution_candidates DROP COLUMN IF EXISTS asset_class")
    op.execute("ALTER TABLE token_intents DROP COLUMN IF EXISTS linking_risks_json")
    op.execute("ALTER TABLE token_intents DROP COLUMN IF EXISTS linking_reasons_json")
    op.execute("ALTER TABLE token_intents DROP COLUMN IF EXISTS asset_class_hint")
    op.execute("ALTER TABLE token_evidence DROP COLUMN IF EXISTS asset_class_hint")
    op.execute("ALTER TABLE asset_aliases DROP COLUMN IF EXISTS alias_scope")
```

- [ ] **Step 3: Add provider observation repository**

Add `src/gmgn_twitter_intel/storage/provider_observation_repository.py`:

```python
from __future__ import annotations

import hashlib
import json
from typing import Any


class ProviderObservationRepository:
    def __init__(self, conn):
        self.conn = conn

    def insert_identity_observation(
        self,
        *,
        provider: str,
        request_kind: str,
        request_key: str,
        status: str,
        observed_at_ms: int,
        chain_hint: str | None = None,
        address_hint: str | None = None,
        symbol_hint: str | None = None,
        candidate_count: int = 0,
        raw_payload: dict[str, Any] | list[Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        raw_payload_hash = _payload_hash(raw_payload) if raw_payload is not None else None
        observation_id = _stable_id("provider-identity-observation", provider, request_kind, request_key, str(observed_at_ms))
        row = self.conn.execute(
            """
            INSERT INTO provider_identity_observations(
              observation_id, provider, request_kind, request_key, chain_hint, address_hint, symbol_hint,
              status, candidate_count, raw_payload_hash, raw_payload_json, error_code, error_message,
              observed_at_ms, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
            ON CONFLICT (observation_id) DO UPDATE SET
              status = excluded.status,
              candidate_count = excluded.candidate_count,
              raw_payload_hash = excluded.raw_payload_hash,
              raw_payload_json = excluded.raw_payload_json,
              error_code = excluded.error_code,
              error_message = excluded.error_message
            RETURNING *
            """,
            (
                observation_id,
                provider,
                request_kind,
                request_key,
                chain_hint,
                address_hint,
                symbol_hint,
                status,
                int(candidate_count),
                raw_payload_hash,
                json.dumps(raw_payload, ensure_ascii=False, sort_keys=True) if raw_payload is not None else None,
                error_code,
                error_message,
                observed_at_ms,
                observed_at_ms,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row)


def _payload_hash(payload: dict[str, Any] | list[Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Add stock instrument repository**

Add `src/gmgn_twitter_intel/storage/stock_instrument_repository.py`:

```python
from __future__ import annotations

import hashlib
from typing import Any


class StockInstrumentRepository:
    def __init__(self, conn):
        self.conn = conn

    def upsert_instrument(
        self,
        *,
        symbol: str,
        exchange: str,
        name: str | None,
        source: str,
        observed_at_ms: int,
        commit: bool = False,
    ) -> dict[str, Any]:
        normalized_symbol = symbol.strip().upper()
        normalized_exchange = exchange.strip().lower()
        instrument_id = _stable_id("stock-instrument", normalized_exchange, normalized_symbol)
        row = self.conn.execute(
            """
            INSERT INTO stock_instruments(
              instrument_id, symbol, exchange, name, source, status,
              observed_at_ms, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, 'active', %s, %s, %s)
            ON CONFLICT (exchange, symbol) DO UPDATE SET
              name = COALESCE(excluded.name, stock_instruments.name),
              source = excluded.source,
              status = 'active',
              observed_at_ms = excluded.observed_at_ms,
              updated_at_ms = excluded.updated_at_ms
            RETURNING *
            """,
            (
                instrument_id,
                normalized_symbol,
                normalized_exchange,
                name,
                source,
                observed_at_ms,
                observed_at_ms,
                observed_at_ms,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row)

    def candidates_for_symbol(self, symbol: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM stock_instruments
            WHERE symbol = %s AND status = 'active'
            ORDER BY exchange ASC
            """,
            (symbol.strip().upper(),),
        ).fetchall()
        return [dict(row) for row in rows]


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
```

- [ ] **Step 5: Wire repositories**

Modify `src/gmgn_twitter_intel/storage/repository_session.py`:

```python
from .provider_observation_repository import ProviderObservationRepository
from .stock_instrument_repository import StockInstrumentRepository
```

Add to repository container construction:

```python
provider_observations=ProviderObservationRepository(conn),
stock_instruments=StockInstrumentRepository(conn),
```

- [ ] **Step 6: Run schema/repository tests**

Run:

```bash
uv run pytest tests/test_postgres_schema.py tests/test_postgres_schema_runtime.py tests/test_provider_observation_repository.py tests/test_stock_instrument_resolver.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit schema**

```bash
git add src/gmgn_twitter_intel/storage/alembic/versions/20260507_0008_token_radar_v4_entity_linking.py src/gmgn_twitter_intel/storage/provider_observation_repository.py src/gmgn_twitter_intel/storage/stock_instrument_repository.py src/gmgn_twitter_intel/storage/repository_session.py tests/test_postgres_schema.py tests/test_postgres_schema_runtime.py tests/test_provider_observation_repository.py tests/test_stock_instrument_resolver.py
git commit -m "feat: add token radar v4 entity linking schema"
```

## Task 4: Intent Linker Extraction From Builder

**Files:**

- Create: `src/gmgn_twitter_intel/pipeline/token_intent_linker.py`
- Modify: `src/gmgn_twitter_intel/pipeline/token_intent_builder.py`
- Test: `tests/test_token_intent_linker.py`
- Test: `tests/test_token_intent_builder.py`

- [ ] **Step 1: Write linker tests**

Add `tests/test_token_intent_linker.py`:

```python
from __future__ import annotations

from gmgn_twitter_intel.pipeline.entity_extractor import TextSurface, extract_entities_from_surfaces
from gmgn_twitter_intel.pipeline.token_evidence_builder import build_token_evidence
from gmgn_twitter_intel.pipeline.token_intent_linker import link_token_evidence
from tests.factories_token_radar_v4 import MOONCLUB_SOL_CA, VERSA_BASE_CA


def _evidence(text: str):
    return build_token_evidence(
        event_id="event-link",
        entities=extract_entities_from_surfaces([TextSurface("primary", text)]),
        token_snapshot=None,
        created_at_ms=1_777_800_000_000,
    )


def test_single_symbol_single_ca_same_surface_link_even_with_decimal_punctuation():
    groups = link_token_evidence(_evidence(f"$MOONCLUB result: 4.1x 90K -> 371K {MOONCLUB_SOL_CA}"))

    assert len(groups) == 1
    assert groups[0].display_symbol == "MOONCLUB"
    assert groups[0].primary.address_hint == MOONCLUB_SOL_CA
    assert "single_symbol_single_ca_same_surface" in groups[0].reasons


def test_multiple_symbols_and_multiple_cas_do_not_force_merge():
    groups = link_token_evidence(_evidence(f"$AAA {VERSA_BASE_CA} and $BBB {MOONCLUB_SOL_CA}"))

    assert len(groups) == 2
    assert all(group.display_symbol in {"AAA", "BBB"} for group in groups)
    assert all("reciprocal_nearest_pair" in group.reasons for group in groups)


def test_multiple_symbols_one_ca_is_ambiguous_mentions():
    groups = link_token_evidence(_evidence(f"$AAA and $BBB both watching {VERSA_BASE_CA}"))

    assert len(groups) == 3
    assert any("ambiguous_symbol_ca_pairing" in group.risks for group in groups)
```

- [ ] **Step 2: Create linker module**

Add `src/gmgn_twitter_intel/pipeline/token_intent_linker.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from .token_evidence_builder import TokenEvidenceInput

MAX_PAIR_DISTANCE = 180


@dataclass(frozen=True, slots=True)
class LinkedTokenEvidenceGroup:
    primary: TokenEvidenceInput
    display_symbol: str | None
    links: list[tuple[TokenEvidenceInput, str]]
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


def link_token_evidence(evidence: list[TokenEvidenceInput]) -> list[LinkedTokenEvidenceGroup]:
    identities = [item for item in evidence if item.address_hint]
    cashtags = [item for item in evidence if item.evidence_type == "cashtag" and item.normalized_symbol]
    groups: list[LinkedTokenEvidenceGroup] = []
    consumed: set[str] = set()

    for identity, cashtag, reason in _identity_cashtag_pairs(identities, cashtags):
        consumed.add(identity.evidence_id)
        consumed.add(cashtag.evidence_id)
        groups.append(
            LinkedTokenEvidenceGroup(
                primary=identity,
                display_symbol=cashtag.normalized_symbol,
                links=[(identity, "primary_identity"), (cashtag, "display_alias")],
                reasons=[reason],
            )
        )

    for identity in identities:
        if identity.evidence_id in consumed:
            continue
        groups.append(
            LinkedTokenEvidenceGroup(
                primary=identity,
                display_symbol=None,
                links=[(identity, "primary_identity")],
                risks=["missing_display_alias"],
            )
        )

    for cashtag in cashtags:
        if cashtag.evidence_id in consumed:
            continue
        groups.append(
            LinkedTokenEvidenceGroup(
                primary=cashtag,
                display_symbol=cashtag.normalized_symbol,
                links=[(cashtag, "primary_identity")],
                risks=["symbol_only_intent"],
            )
        )

    if len(identities) == 1 and len(cashtags) > 1:
        return [
            group
            if group.primary.evidence_id != identities[0].evidence_id
            else LinkedTokenEvidenceGroup(
                primary=group.primary,
                display_symbol=group.display_symbol,
                links=group.links,
                reasons=group.reasons,
                risks=[*group.risks, "ambiguous_symbol_ca_pairing"],
            )
            for group in groups
        ]
    return groups


def _identity_cashtag_pairs(
    identities: list[TokenEvidenceInput],
    cashtags: list[TokenEvidenceInput],
) -> list[tuple[TokenEvidenceInput, TokenEvidenceInput, str]]:
    local_pairs = []
    for identity in identities:
        local = [
            cashtag
            for cashtag in cashtags
            if cashtag.text_surface == identity.text_surface and cashtag.local_group_key == identity.local_group_key
        ]
        if len(local) == 1:
            local_pairs.append((identity, local[0], "same_local_group"))
    if local_pairs:
        return _dedupe_pairs(local_pairs)

    by_surface = {(item.text_surface) for item in [*identities, *cashtags]}
    surface_pairs = []
    for surface in by_surface:
        surface_identities = [item for item in identities if item.text_surface == surface]
        surface_cashtags = [item for item in cashtags if item.text_surface == surface]
        if len(surface_identities) == 1 and len(surface_cashtags) == 1:
            distance = _span_distance(surface_identities[0], surface_cashtags[0])
            if distance <= MAX_PAIR_DISTANCE:
                surface_pairs.append((surface_identities[0], surface_cashtags[0], "single_symbol_single_ca_same_surface"))
    if surface_pairs:
        return surface_pairs

    return _reciprocal_nearest_pairs(identities, cashtags)


def _reciprocal_nearest_pairs(
    identities: list[TokenEvidenceInput],
    cashtags: list[TokenEvidenceInput],
) -> list[tuple[TokenEvidenceInput, TokenEvidenceInput, str]]:
    pairs = []
    for identity in identities:
        same_surface = [item for item in cashtags if item.text_surface == identity.text_surface]
        nearest = _nearest(identity, same_surface)
        if nearest is None:
            continue
        reverse = _nearest(nearest, [item for item in identities if item.text_surface == nearest.text_surface])
        if reverse and reverse.evidence_id == identity.evidence_id and _span_distance(identity, nearest) <= MAX_PAIR_DISTANCE:
            pairs.append((identity, nearest, "reciprocal_nearest_pair"))
    return _dedupe_pairs(pairs)


def _nearest(item: TokenEvidenceInput, candidates: list[TokenEvidenceInput]) -> TokenEvidenceInput | None:
    return min(candidates, key=lambda candidate: _span_distance(item, candidate), default=None)


def _span_distance(left: TokenEvidenceInput, right: TokenEvidenceInput) -> int:
    if left.span_end < right.span_start:
        return int(right.span_start - left.span_end)
    if right.span_end < left.span_start:
        return int(left.span_start - right.span_end)
    return 0


def _dedupe_pairs(
    pairs: list[tuple[TokenEvidenceInput, TokenEvidenceInput, str]],
) -> list[tuple[TokenEvidenceInput, TokenEvidenceInput, str]]:
    out = []
    seen: set[tuple[str, str]] = set()
    for identity, cashtag, reason in pairs:
        key = (identity.evidence_id, cashtag.evidence_id)
        if key in seen:
            continue
        seen.add(key)
        out.append((identity, cashtag, reason))
    return out
```

- [ ] **Step 3: Modify builder to consume linker output**

Modify `src/gmgn_twitter_intel/pipeline/token_intent_builder.py`:

```python
from .token_intent_linker import link_token_evidence
```

Replace the current body of `build_token_intents()` with:

```python
def build_token_intents(
    *,
    event_id: str,
    evidence: list[TokenEvidenceInput],
    created_at_ms: int,
) -> list[TokenIntentInput]:
    intents: list[TokenIntentInput] = []
    for group in link_token_evidence(evidence):
        intents.append(
            _intent(
                event_id=event_id,
                primary=group.primary,
                display_symbol=group.display_symbol,
                links=[TokenIntentEvidenceLink(item.evidence_id, role) for item, role in group.links],
                created_at_ms=created_at_ms,
            )
        )
    return _unique_intents(intents)
```

- [ ] **Step 4: Run linker/builder tests**

Run:

```bash
uv run pytest tests/test_token_intent_linker.py tests/test_token_intent_builder.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit linker**

```bash
git add src/gmgn_twitter_intel/pipeline/token_intent_linker.py src/gmgn_twitter_intel/pipeline/token_intent_builder.py tests/test_token_intent_linker.py tests/test_token_intent_builder.py
git commit -m "feat: split token intent entity linker"
```

## Task 5: Alias Scope And Stock Resolver

**Files:**

- Modify: `src/gmgn_twitter_intel/storage/asset_repository.py`
- Create: `src/gmgn_twitter_intel/pipeline/stock_instrument_resolver.py`
- Modify: `src/gmgn_twitter_intel/pipeline/token_evidence_builder.py`
- Test: `tests/test_asset_repository.py`
- Test: `tests/test_stock_instrument_resolver.py`

- [ ] **Step 1: Add asset repository tests for alias scope**

Add to `tests/test_asset_repository.py`:

```python
def test_candidates_for_symbol_ignores_observed_aliases(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    reset_postgres_schema(conn)
    repo = AssetRepository(conn)
    result = repo.upsert_dex_asset(
        chain="eth",
        address="0x6982508145454ce325ddbe47a25d4ec3d2311933",
        symbol="MASK",
        event_id=None,
        observed_at_ms=1_777_800_000_000,
        provider="observed_social",
        commit=True,
    )
    conn.execute("UPDATE asset_aliases SET alias_scope = 'observed' WHERE asset_id = %s", (result.asset["asset_id"],))
    conn.commit()

    assert repo.candidates_for_symbol("MASK") == []
```

- [ ] **Step 2: Enforce alias scope in symbol candidates**

Modify `src/gmgn_twitter_intel/storage/asset_repository.py` inside `candidates_for_symbol()`:

```sql
WHERE asset_aliases.alias_type = 'symbol'
  AND asset_aliases.normalized_alias = %s
  AND asset_aliases.alias_scope IN ('canonical', 'provider')
  AND assets.identity_status = 'resolved'
  AND assets.asset_id NOT LIKE 'asset:unresolved:%'
  AND assets.asset_id NOT LIKE 'asset:ambiguous:%'
```

Add `asset_aliases.alias_scope` to the SELECT list:

```sql
asset_aliases.alias_scope,
```

- [ ] **Step 3: Add stock resolver**

Add `src/gmgn_twitter_intel/pipeline/stock_instrument_resolver.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StockTickerDecision:
    symbol: str
    status: str
    instrument_ids: list[str]
    reasons: list[str]
    risks: list[str]


class StockInstrumentResolver:
    def __init__(self, *, stock_instruments):
        self.stock_instruments = stock_instruments

    def resolve_symbol(self, symbol: str) -> StockTickerDecision:
        normalized = symbol.strip().upper().lstrip("$")
        candidates = self.stock_instruments.candidates_for_symbol(normalized)
        if not candidates:
            return StockTickerDecision(normalized, "not_stock", [], [], [])
        return StockTickerDecision(
            normalized,
            "stock_candidate",
            [str(row["instrument_id"]) for row in candidates],
            ["stock_ticker_candidate"],
            ["stock_crypto_symbol_collision"],
        )
```

- [ ] **Step 4: Mark stock collisions in token evidence**

Modify `src/gmgn_twitter_intel/pipeline/token_evidence_builder.py` to accept an optional stock resolver:

```python
def build_token_evidence(
    *,
    event_id: str,
    entities: list[ExtractedEntity],
    token_snapshot: TokenSnapshot | None,
    created_at_ms: int,
    stock_resolver=None,
) -> list[TokenEvidenceInput]:
```

Inside symbol conversion:

```python
asset_class_hint = "crypto"
if stock_resolver is not None and entity.entity_type == "symbol":
    stock_decision = stock_resolver.resolve_symbol(entity.normalized_value)
    if stock_decision.status == "stock_candidate":
        asset_class_hint = "unknown"
```

Persist `asset_class_hint` on `TokenEvidenceInput`.

- [ ] **Step 5: Run alias/stock tests**

Run:

```bash
uv run pytest tests/test_asset_repository.py tests/test_stock_instrument_resolver.py tests/test_token_evidence_builder.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit alias and stock resolver**

```bash
git add src/gmgn_twitter_intel/storage/asset_repository.py src/gmgn_twitter_intel/pipeline/stock_instrument_resolver.py src/gmgn_twitter_intel/pipeline/token_evidence_builder.py tests/test_asset_repository.py tests/test_stock_instrument_resolver.py tests/test_token_evidence_builder.py
git commit -m "feat: enforce canonical token alias resolution"
```

## Task 6: Identity Candidate Resolver

**Files:**

- Create: `src/gmgn_twitter_intel/pipeline/identity_candidate_resolver.py`
- Modify: `src/gmgn_twitter_intel/pipeline/token_intent_resolver.py`
- Modify: `src/gmgn_twitter_intel/storage/intent_resolution_repository.py`
- Test: `tests/test_identity_candidate_resolver.py`
- Test: `tests/test_token_intent_resolver.py`

- [ ] **Step 1: Write candidate resolver tests**

Add `tests/test_identity_candidate_resolver.py`:

```python
from __future__ import annotations

from gmgn_twitter_intel.pipeline.identity_candidate_resolver import IdentityCandidateResolver


def test_exact_ca_with_chain_selects_direct_candidate(fake_asset_registry):
    resolver = IdentityCandidateResolver(assets=fake_asset_registry, stock_instruments=None, provider_observations=None)

    decision = resolver.resolve_intent(
        {
            "intent_id": "intent-1",
            "event_id": "event-1",
            "display_symbol": "VERSA",
            "chain_hint": "base",
            "address_hint": "0x2cc0db4f8977accadb5b7da59c5923e14328eba3",
            "asset_class_hint": "crypto",
        },
        evidence=[],
        now_ms=1_777_800_000_000,
    )

    assert decision.identity_status == "resolved"
    assert decision.reasons == ["exact_ca_with_chain_hint"]
    assert decision.candidates[0].decision == "selected"


def test_symbol_only_multiple_candidates_returns_ambiguous(fake_asset_registry):
    fake_asset_registry.symbol_candidates = [
        {"asset_id": "asset:crypto:one", "venue_id": "venue:one", "asset_confidence": 0.9, "alias_confidence": 0.9, "alias_scope": "provider"},
        {"asset_id": "asset:crypto:two", "venue_id": "venue:two", "asset_confidence": 0.9, "alias_confidence": 0.9, "alias_scope": "provider"},
    ]
    resolver = IdentityCandidateResolver(assets=fake_asset_registry, stock_instruments=None, provider_observations=None)

    decision = resolver.resolve_intent(
        {"intent_id": "intent-1", "event_id": "event-1", "display_symbol": "MASK", "chain_hint": None, "address_hint": None, "asset_class_hint": "crypto"},
        evidence=[],
        now_ms=1_777_800_000_000,
    )

    assert decision.identity_status == "ambiguous"
    assert "multiple_symbol_candidates" in decision.reasons
```

- [ ] **Step 2: Implement candidate resolver**

Add `src/gmgn_twitter_intel/pipeline/identity_candidate_resolver.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

MIN_SYMBOL_SCORE = 0.85
MIN_SYMBOL_MARGIN = 0.20


@dataclass(frozen=True, slots=True)
class IdentityCandidate:
    candidate_id: str
    intent_id: str
    asset_id: str | None
    venue_id: str | None
    asset_class: str
    candidate_kind: str
    candidate_source: str
    score: float
    score_components: dict[str, float]
    decision: str
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    raw_observation_id: str | None = None


@dataclass(frozen=True, slots=True)
class IdentityResolution:
    intent_id: str
    event_id: str
    asset_id: str | None
    venue_id: str | None
    resolution_status: str
    identity_status: str
    confidence: float
    reasons: list[str]
    risks: list[str]
    candidates: list[IdentityCandidate]


class IdentityCandidateResolver:
    def __init__(self, *, assets, stock_instruments, provider_observations):
        self.assets = assets
        self.stock_instruments = stock_instruments
        self.provider_observations = provider_observations

    def resolve_intent(self, intent: dict[str, Any], evidence: list[Any], *, now_ms: int) -> IdentityResolution:
        address = _text(intent.get("address_hint"))
        chain = _text(intent.get("chain_hint"))
        symbol = _text(intent.get("display_symbol"))
        if address:
            return self._resolve_address(intent, address=address, chain=chain)
        if symbol:
            return self._resolve_symbol(intent, symbol=symbol)
        return self._nil(intent, reasons=["no_identity_evidence"], risks=["provider_resolution_pending"])

    def _resolve_address(self, intent: dict[str, Any], *, address: str, chain: str | None) -> IdentityResolution:
        if chain:
            result = self.assets.upsert_dex_asset(
                chain=chain,
                address=address,
                symbol=_text(intent.get("display_symbol")),
                event_id=str(intent["event_id"]),
                observed_at_ms=int(intent.get("created_at_ms") or 0),
                provider="deterministic",
                commit=False,
            )
            venue_id = str((result.venue or {}).get("venue_id"))
            return self._selected(intent, asset_id=str(result.asset["asset_id"]), venue_id=venue_id, reason="exact_ca_with_chain_hint", score=1.0)

        candidates = [row for row in self.assets.candidates_for_ca(chain=None, address=address) if _real_candidate(row)]
        if len(candidates) == 1:
            row = candidates[0]
            return self._selected(intent, asset_id=str(row["asset_id"]), venue_id=str(row["venue_id"]), reason="local_exact_ca_match", score=0.95)
        if len(candidates) > 1:
            retained = [_candidate_from_row(intent, row, "exact_ca", 0.75, "retained", ["multiple_local_ca_matches"], ["chain_required_for_exact_ca"]) for row in candidates]
            return IdentityResolution(str(intent["intent_id"]), str(intent["event_id"]), None, None, "ambiguous", "ambiguous", 0.55, ["multiple_local_ca_matches"], ["chain_required_for_exact_ca"], retained)
        return self._nil(intent, reasons=["ca_requires_provider_resolution"], risks=["provider_resolution_pending"])

    def _resolve_symbol(self, intent: dict[str, Any], *, symbol: str) -> IdentityResolution:
        rows = [row for row in self.assets.candidates_for_symbol(symbol) if _real_candidate(row)]
        candidates = [_candidate_from_row(intent, row, "canonical_symbol", _symbol_score(row), "retained", ["symbol_candidate"], []) for row in rows]
        candidates.sort(key=lambda item: item.score, reverse=True)
        if not candidates:
            return self._nil(intent, reasons=["no_local_identity_match"], risks=["provider_resolution_pending"])
        top = candidates[0]
        second_score = candidates[1].score if len(candidates) > 1 else 0.0
        if top.score >= MIN_SYMBOL_SCORE and top.score - second_score >= MIN_SYMBOL_MARGIN:
            selected = IdentityCandidate(**{**top.__dict__, "decision": "selected", "reasons": ["single_canonical_symbol_candidate"]})
            return IdentityResolution(str(intent["intent_id"]), str(intent["event_id"]), selected.asset_id, selected.venue_id, "selected", "resolved", selected.score, ["single_canonical_symbol_candidate"], [], [selected, *candidates[1:]])
        return IdentityResolution(str(intent["intent_id"]), str(intent["event_id"]), None, None, "ambiguous", "ambiguous", top.score, ["multiple_symbol_candidates"], ["candidate_selection_requires_provider_resolution"], candidates)

    def _selected(self, intent: dict[str, Any], *, asset_id: str, venue_id: str, reason: str, score: float) -> IdentityResolution:
        candidate = IdentityCandidate(_stable_id("identity-candidate", str(intent["intent_id"]), asset_id, venue_id), str(intent["intent_id"]), asset_id, venue_id, "crypto", "exact_ca", "local_registry", score, {"address_specificity": score}, "selected", [reason], [])
        return IdentityResolution(str(intent["intent_id"]), str(intent["event_id"]), asset_id, venue_id, "direct", "resolved", score, [reason], [], [candidate])

    def _nil(self, intent: dict[str, Any], *, reasons: list[str], risks: list[str]) -> IdentityResolution:
        return IdentityResolution(str(intent["intent_id"]), str(intent["event_id"]), None, None, "unresolved", "unresolved", 0.25, reasons, risks, [])


def _candidate_from_row(intent: dict[str, Any], row: dict[str, Any], kind: str, score: float, decision: str, reasons: list[str], risks: list[str]) -> IdentityCandidate:
    asset_id = str(row.get("asset_id") or "")
    venue_id = str(row.get("venue_id") or "")
    return IdentityCandidate(
        _stable_id("identity-candidate", str(intent["intent_id"]), asset_id, venue_id, kind),
        str(intent["intent_id"]),
        asset_id,
        venue_id,
        "crypto",
        kind,
        str(row.get("primary_source") or row.get("alias_source") or "local_registry"),
        score,
        {"alias_confidence": float(row.get("alias_confidence") or 0), "asset_confidence": float(row.get("asset_confidence") or 0)},
        decision,
        reasons,
        risks,
    )


def _symbol_score(row: dict[str, Any]) -> float:
    alias = float(row.get("alias_confidence") or 0)
    asset = float(row.get("asset_confidence") or 0)
    return min(1.0, alias * 0.55 + asset * 0.35 + 0.10)


def _real_candidate(row: dict[str, Any]) -> bool:
    asset_id = str(row.get("asset_id") or "")
    return bool(asset_id and row.get("venue_id") and not asset_id.startswith(("asset:unresolved:", "asset:ambiguous:")))


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
```

- [ ] **Step 3: Persist candidates**

Modify `src/gmgn_twitter_intel/storage/intent_resolution_repository.py` to add:

```python
def insert_candidates(self, candidates, *, commit: bool = False) -> None:
    for candidate in candidates:
        self.conn.execute(
            """
            INSERT INTO token_intent_resolution_candidates(
              candidate_id, intent_id, asset_id, venue_id, provider, candidate_kind, score, decision,
              reasons_json, risks_json, raw_observation_id, created_at_ms,
              asset_class, candidate_source, score_components_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (candidate_id) DO UPDATE SET
              score = excluded.score,
              decision = excluded.decision,
              reasons_json = excluded.reasons_json,
              risks_json = excluded.risks_json,
              score_components_json = excluded.score_components_json
            """,
            (
                candidate.candidate_id,
                candidate.intent_id,
                candidate.asset_id,
                candidate.venue_id,
                candidate.candidate_source,
                candidate.candidate_kind,
                candidate.score,
                candidate.decision,
                json.dumps(candidate.reasons, ensure_ascii=False),
                json.dumps(candidate.risks, ensure_ascii=False),
                candidate.raw_observation_id,
                int(time.time() * 1000),
                candidate.asset_class,
                candidate.candidate_source,
                json.dumps(candidate.score_components, ensure_ascii=False, sort_keys=True),
            ),
        )
    if commit:
        self.conn.commit()
```

- [ ] **Step 4: Replace resolver internals**

Modify `src/gmgn_twitter_intel/pipeline/token_intent_resolver.py`:

```python
from .identity_candidate_resolver import IdentityCandidateResolver

RESOLVER_POLICY_VERSION = "token_intent_resolver_v4"
```

Inside `_decision()`:

```python
candidate_resolver = IdentityCandidateResolver(
    assets=self.assets,
    stock_instruments=getattr(self.resolutions, "stock_instruments", None),
    provider_observations=getattr(self.resolutions, "provider_observations", None),
)
resolution = candidate_resolver.resolve_intent(_intent_dict(intent), evidence, now_ms=now_ms)
self.resolutions.insert_candidates(resolution.candidates, commit=False)
return _decision(
    intent,
    asset_id=resolution.asset_id,
    primary_venue_id=resolution.venue_id,
    resolution_status=resolution.resolution_status,
    identity_status=resolution.identity_status,
    confidence=resolution.confidence,
    reasons=resolution.reasons,
    risks=resolution.risks,
    now_ms=now_ms,
)
```

Add:

```python
def _intent_dict(intent: TokenIntentInput | dict[str, Any]) -> dict[str, Any]:
    if isinstance(intent, dict):
        return dict(intent)
    return {
        "intent_id": intent.intent_id,
        "event_id": intent.event_id,
        "display_symbol": intent.display_symbol,
        "chain_hint": intent.chain_hint,
        "address_hint": intent.address_hint,
        "asset_class_hint": getattr(intent, "asset_class_hint", "crypto"),
        "created_at_ms": intent.created_at_ms,
    }
```

- [ ] **Step 5: Run resolver tests**

Run:

```bash
uv run pytest tests/test_identity_candidate_resolver.py tests/test_token_intent_resolver.py tests/golden/test_token_radar_v4_entity_linking.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit resolver**

```bash
git add src/gmgn_twitter_intel/pipeline/identity_candidate_resolver.py src/gmgn_twitter_intel/pipeline/token_intent_resolver.py src/gmgn_twitter_intel/storage/intent_resolution_repository.py tests/test_identity_candidate_resolver.py tests/test_token_intent_resolver.py tests/golden/test_token_radar_v4_entity_linking.py
git commit -m "feat: resolve token intents through candidates"
```

## Task 7: Provider Identity Observations And Market Status Closure

**Files:**

- Create: `src/gmgn_twitter_intel/pipeline/identity_resolution_worker.py`
- Modify: `src/gmgn_twitter_intel/market/gmgn_openapi_client.py`
- Modify: `src/gmgn_twitter_intel/market/okx_dex_client.py`
- Modify: `src/gmgn_twitter_intel/pipeline/asset_market_sync.py`
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- Test: `tests/test_provider_observation_repository.py`
- Test: `tests/test_token_radar_projection.py`

- [ ] **Step 1: Add projection tests for exact market states**

Add to `tests/test_token_radar_projection.py`:

```python
def test_resolved_venue_without_provider_result_is_pending_refresh(tmp_path):
    _, repos, ingest = open_v4_runtime(tmp_path)
    ingest.ingest_event(make_payload_event("event-pending", symbol="PEND", chain="eth", address=PEPE_ETH_CA, price=""), is_watched=True)

    TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=1_777_800_060_000)
    row = repos.token_radar.latest_rows(window="5m", scope="all", limit=10)[0]

    assert row["market_json"]["market_observation_status"] == "pending_refresh"
    assert row["decision"] != "driver"


def test_provider_not_found_market_state_is_not_driver(tmp_path):
    _, repos, ingest = open_v4_runtime(tmp_path)
    ingest.ingest_event(make_payload_event("event-found-miss", symbol="MISS", chain="eth", address=PEPE_ETH_CA, price=""), is_watched=True)
    repos.provider_observations.insert_identity_observation(
        provider="gmgn",
        request_kind="exact_ca",
        request_key=f"eth:{PEPE_ETH_CA.lower()}",
        status="provider_not_found",
        chain_hint="eth",
        address_hint=PEPE_ETH_CA,
        observed_at_ms=1_777_800_030_000,
        commit=True,
    )

    TokenRadarProjection(repos=repos).rebuild(window="5m", scope="all", now_ms=1_777_800_060_000)
    row = repos.token_radar.latest_rows(window="5m", scope="all", limit=10)[0]

    assert row["market_json"]["market_observation_status"] == "provider_not_found"
    assert row["decision"] != "driver"
```

- [ ] **Step 2: Add identity worker**

Add `src/gmgn_twitter_intel/pipeline/identity_resolution_worker.py`:

```python
from __future__ import annotations

import time
from typing import Any

from ..market.gmgn_openapi_client import GmgnOpenApiError
from ..storage.postgres_client import transaction
from .token_intent_resolver import TokenIntentResolver


class IdentityResolutionWorker:
    def __init__(self, *, repos, gmgn_client=None, okx_dex_client=None):
        self.repos = repos
        self.gmgn_client = gmgn_client
        self.okx_dex_client = okx_dex_client

    def resolve_pending_intent(self, intent_id: str, *, now_ms: int | None = None) -> dict[str, Any]:
        resolved_now = int(now_ms or time.time() * 1000)
        intent = self.repos.token_intents.get_intent(intent_id)
        evidence = self.repos.token_evidence.evidence_for_event(str(intent["event_id"]))
        self._write_provider_observations(intent, now_ms=resolved_now)
        with transaction(self.repos.conn):
            decision = TokenIntentResolver(assets=self.repos.assets, resolutions=self.repos.intent_resolutions).resolve(
                intent,
                evidence,
                decision_time_ms=resolved_now,
                persist=True,
                commit=False,
            )
        return {"intent_id": intent_id, "identity_status": decision.identity_status, "reasons": decision.reasons}

    def _write_provider_observations(self, intent: dict[str, Any], *, now_ms: int) -> None:
        address = intent.get("address_hint")
        chain = intent.get("chain_hint")
        symbol = intent.get("display_symbol")
        if address and chain and self.gmgn_client is not None:
            request_key = f"{chain}:{str(address).lower()}"
            try:
                lookup = self.gmgn_client.lookup_token_info(chain=str(chain), address=str(address))
            except GmgnOpenApiError as exc:
                self.repos.provider_observations.insert_identity_observation(
                    provider="gmgn",
                    request_kind="exact_ca",
                    request_key=request_key,
                    status="provider_error",
                    chain_hint=str(chain),
                    address_hint=str(address),
                    error_code="gmgn_error",
                    error_message=str(exc),
                    observed_at_ms=now_ms,
                    commit=False,
                )
                return
            status = "ready" if lookup.info is not None else "provider_not_found"
            self.repos.provider_observations.insert_identity_observation(
                provider="gmgn",
                request_kind="exact_ca",
                request_key=request_key,
                status=status,
                chain_hint=str(chain),
                address_hint=str(address),
                candidate_count=1 if lookup.info is not None else 0,
                raw_payload=lookup.info.raw if lookup.info is not None else None,
                observed_at_ms=now_ms,
                commit=False,
            )
        elif symbol and self.okx_dex_client is not None:
            candidates = self.okx_dex_client.search_tokens(query=str(symbol), chain_indexes=[])
            self.repos.provider_observations.insert_identity_observation(
                provider="okx_dex",
                request_kind="symbol_search",
                request_key=str(symbol).upper(),
                status="ready" if candidates else "provider_not_found",
                symbol_hint=str(symbol).upper(),
                candidate_count=len(candidates),
                raw_payload=[candidate.raw for candidate in candidates],
                observed_at_ms=now_ms,
                commit=False,
            )
```

- [ ] **Step 3: Join provider observations in projection market state**

Modify `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`:

- Add a `latest_identity_observation` lateral join keyed by `chain:address` for resolved venues.
- Add `provider_identity_status`, `provider_identity_observed_at_ms`, `provider_identity_error_code` to selected columns.
- Update `_market()` missing-snapshot branch:

```python
provider_status = str(row.get("provider_identity_status") or "")
if provider_status in {"provider_not_found", "provider_error", "rate_limited", "provider_not_configured"}:
    return {
        "market_status": "missing",
        "market_observation_status": provider_status,
        "price_change_status": provider_status,
        "provider": row.get("provider_identity_provider"),
        "price_usd": None,
        "market_cap_usd": None,
        "liquidity_usd": None,
        "volume_24h_usd": None,
        "open_interest_usd": None,
        "holders": None,
        "snapshot_age_ms": None,
        "snapshot_observed_at_ms": row.get("provider_identity_observed_at_ms"),
        "price_change_since_social_pct": None,
        "price_change_before_social_pct": None,
    }
```

- [ ] **Step 4: Run provider/market tests**

Run:

```bash
uv run pytest tests/test_provider_observation_repository.py tests/test_token_radar_projection.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit provider closure**

```bash
git add src/gmgn_twitter_intel/pipeline/identity_resolution_worker.py src/gmgn_twitter_intel/market/gmgn_openapi_client.py src/gmgn_twitter_intel/market/okx_dex_client.py src/gmgn_twitter_intel/pipeline/asset_market_sync.py src/gmgn_twitter_intel/pipeline/token_radar_projection.py tests/test_provider_observation_repository.py tests/test_token_radar_projection.py
git commit -m "feat: close token identity provider observations"
```

## Task 8: Radar Projection/API/Frontend Hard Cut To V4

**Files:**

- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/retrieval/asset_flow_service.py`
- Modify: `src/gmgn_twitter_intel/api/app.py`
- Modify: `src/gmgn_twitter_intel/api/ws.py`
- Modify: `src/gmgn_twitter_intel/pipeline/notification_rules.py`
- Modify: `web/src/App.tsx`
- Modify: `web/src/api/types.ts`
- Test: `tests/test_asset_flow_service.py`
- Test: `tests/test_notification_rules.py`
- Test: `web/src/App.test.tsx`

- [ ] **Step 1: Add hard-cut import guard test**

Add to `tests/test_asset_flow_service.py`:

```python
def test_asset_flow_projection_declares_v4_source():
    service = AssetFlowService(token_radar=FakeTokenRadarRepository(rows=[]))
    result = service.asset_flow(window="5m", limit=20, scope="all", now_ms=1_777_800_000_000)

    assert result["projection"]["source"] == "token_radar_rows"
    assert result["projection"]["version"] == "token-radar-v4"
```

- [ ] **Step 2: Update projection version and data health**

Modify `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`:

```python
PROJECTION_VERSION = "token-radar-v4"
```

Ensure `resolution_json` includes candidate audit summary:

```python
"candidate_summary": {
    "selected_asset_id": latest.get("resolved_asset_id"),
    "selected_venue_id": latest.get("primary_venue_id"),
    "resolver_policy_version": latest.get("resolver_policy_version"),
},
```

Ensure `data_health_json` has:

```python
"identity": identity_status,
"market": market["market_observation_status"],
"coverage": "public_stream",
"projection_version": PROJECTION_VERSION,
```

- [ ] **Step 3: Update API projection version**

Modify `src/gmgn_twitter_intel/retrieval/asset_flow_service.py`:

```python
"version": "token-radar-v4",
```

- [ ] **Step 4: Remove frontend scoring decisions**

Modify `web/src/App.tsx`:

- keep `tokenRadarRowToTokenItem()` as a render adapter only;
- keep `normalizeDecision(row.decision)`;
- remove any branch that recomputes `decision` from heat/quality/tradeability;
- keep `decision_priority` as display sorting metadata only.

The decision section should remain:

```ts
const decision = normalizeDecision(row.decision);
```

No code in `web/src/App.tsx` should contain:

```ts
opportunityScore >=
decision = "driver"
```

- [ ] **Step 5: Add frontend regression**

Add to `web/src/App.test.tsx`:

```tsx
it("keeps backend investigate decision for unresolved high heat radar rows", () => {
  const item = tokenRadarRowToTokenItem(
    makeAssetFlowRow({
      decision: "investigate",
      resolution: { status: "unresolved", confidence: 0.3, reasons: ["no_local_identity_match"], risks: [] },
      score: { opportunity: { score: 100, score_version: "token-radar-v4", reasons: [], risks: [] } }
    }),
    "5m",
    "all"
  );

  expect(item.opportunity.decision).toBe("investigate");
});
```

- [ ] **Step 6: Run API/UI tests**

Run:

```bash
uv run pytest tests/test_asset_flow_service.py tests/test_notification_rules.py -q
npm --prefix web test -- --run
npm --prefix web run build
```

Expected:

```text
passed
✓ built
```

- [ ] **Step 7: Commit projection/UI hard cut**

```bash
git add src/gmgn_twitter_intel/pipeline/token_radar_projection.py src/gmgn_twitter_intel/retrieval/asset_flow_service.py src/gmgn_twitter_intel/api/app.py src/gmgn_twitter_intel/api/ws.py src/gmgn_twitter_intel/pipeline/notification_rules.py web/src/App.tsx web/src/api/types.ts tests/test_asset_flow_service.py tests/test_notification_rules.py web/src/App.test.tsx
git commit -m "feat: hard cut token radar api to v4"
```

## Task 9: Ops Commands And Live 5m Diagnostic Pull

**Files:**

- Modify: `src/gmgn_twitter_intel/cli.py`
- Modify: `src/gmgn_twitter_intel/storage/postgres_audit.py`
- Create: `tests/test_token_radar_v4_ops.py`

- [ ] **Step 1: Add ops test**

Add `tests/test_token_radar_v4_ops.py`:

```python
from __future__ import annotations

from gmgn_twitter_intel.storage.postgres_audit import PostgresAudit


def test_v4_audit_reports_identity_and_market_breakdowns(tmp_path):
    conn, repos, ingest = open_v4_runtime(tmp_path)
    ingest.ingest_event(make_event("event-unknown", text="$SPACEXAI"), is_watched=True)

    payload = PostgresAudit(conn).token_radar_v4_health()

    assert "identity_status_counts" in payload
    assert "resolution_reason_counts" in payload
    assert "market_status_counts" in payload
    assert "address_display_without_symbol_count" in payload
```

- [ ] **Step 2: Add CLI audit command**

Modify `src/gmgn_twitter_intel/cli.py`:

```python
def _cmd_token_radar_v4_health(args) -> int:
    settings = load_settings(args.config)
    with connect_postgres(settings.storage.postgres) as conn:
        payload = PostgresAudit(conn).token_radar_v4_health(window=args.window)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0
```

Register:

```python
health = ops_subparsers.add_parser("token-radar-v4-health")
health.add_argument("--window", default="5m", choices=("5m", "1h", "4h", "24h"))
health.set_defaults(func=_cmd_token_radar_v4_health)
```

- [ ] **Step 3: Add audit query**

Modify `src/gmgn_twitter_intel/storage/postgres_audit.py`:

```python
def token_radar_v4_health(self, *, window: str = "5m") -> dict[str, Any]:
    return {
        "projection_version": "token-radar-v4",
        "identity_status_counts": self._json_counts(
            "SELECT resolution_json->>'status' AS key, count(*) AS count FROM token_radar_rows WHERE projection_version = 'token-radar-v4' AND window = %s GROUP BY 1",
            (window,),
        ),
        "resolution_reason_counts": self._jsonb_array_counts("token_radar_rows", "resolution_json", "reasons", window),
        "market_status_counts": self._json_counts(
            "SELECT market_json->>'market_observation_status' AS key, count(*) AS count FROM token_radar_rows WHERE projection_version = 'token-radar-v4' AND window = %s GROUP BY 1",
            (window,),
        ),
        "address_display_without_symbol_count": self._scalar(
            """
            SELECT count(*)
            FROM token_radar_rows
            WHERE projection_version = 'token-radar-v4'
              AND window = %s
              AND asset_json->>'symbol' IS NULL
              AND primary_venue_json->>'address' IS NOT NULL
            """,
            (window,),
        ),
    }
```

- [ ] **Step 4: Run ops tests**

Run:

```bash
uv run pytest tests/test_token_radar_v4_ops.py tests/test_postgres_audit.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit ops diagnostics**

```bash
git add src/gmgn_twitter_intel/cli.py src/gmgn_twitter_intel/storage/postgres_audit.py tests/test_token_radar_v4_ops.py
git commit -m "feat: add token radar v4 diagnostics"
```

## Task 10: Full Verification And Docker Runtime Check

**Files:**

- Modify only files changed by previous tasks when verification finds a concrete failure.

- [ ] **Step 1: Run backend verification**

Run:

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

- [ ] **Step 2: Run frontend verification**

Run:

```bash
npm --prefix web test -- --run
npm --prefix web run build
```

Expected:

```text
passed
✓ built
```

- [ ] **Step 3: Rebuild Docker image**

Run:

```bash
docker compose build app
docker compose up -d app
```

Expected:

```text
app  Built
Container ... Started
```

- [ ] **Step 4: Check runtime readiness**

Run:

```bash
curl -fsS http://127.0.0.1:8000/readyz | jq .
```

Expected:

```json
{
  "status": "ok"
}
```

- [ ] **Step 5: Rebuild Token Radar V4 projection**

Run:

```bash
docker compose exec app gmgn-twitter-intel ops rebuild-token-radar --window 5m --scope all --limit 100
```

Expected:

```text
token-radar-v4
rows_written
```

- [ ] **Step 6: Pull live 5m API sample**

Run:

```bash
curl -fsS "http://127.0.0.1:8000/api/asset-flow?window=5m&scope=all&limit=80" | jq '.projection, [.resolved_assets[], .attention_candidates[]] | length'
```

Expected:

```text
"source": "token_radar_rows"
"version": "token-radar-v4"
```

- [ ] **Step 7: Run root-cause diagnostic**

Run:

```bash
docker compose exec app gmgn-twitter-intel ops token-radar-v4-health --window 5m
```

Expected output must include non-empty objects:

```json
{
  "projection_version": "token-radar-v4",
  "identity_status_counts": {},
  "resolution_reason_counts": {},
  "market_status_counts": {}
}
```

- [ ] **Step 8: Verify exit gates manually from API sample**

Run:

```bash
curl -fsS "http://127.0.0.1:8000/api/asset-flow?window=5m&scope=all&limit=120" \
  | jq '[.resolved_assets[], .attention_candidates[]] | map({symbol: .asset.symbol, intent: .intent.display_symbol, venue: .primary_venue, resolution: .resolution, market: .market.market_observation_status, decision})'
```

Check:

- unresolved/ambiguous rows have `decision="investigate"`;
- resolved rows with `market_observation_status="pending_refresh"` are not `driver`;
- address-only resolved rows have `asset.symbol=null` and a real venue address;
- `UNKNOWN ETH` does not appear as a synthetic symbol;
- stock-only rows are absent from crypto resolved lane;
- no row has source `asset_attributions`.

- [ ] **Step 9: Commit verification fixes**

If any verification fix was required:

```bash
git add <changed-files>
git commit -m "fix: close token radar v4 verification gaps"
```

If no verification fix was required, skip this commit.

## Self-Review Checklist

- [ ] V4 spec exit gates are covered by golden tests.
- [ ] Every new schema table has a repository or audit read path.
- [ ] `asset_aliases.alias_scope='observed'` cannot resolve symbol-only crypto intents.
- [ ] `token_intent_resolver.py` writes candidate audit rows for selected and retained candidates.
- [ ] Provider true miss, provider error, rate limit, no venue, pending refresh, and stale snapshot are distinct statuses.
- [ ] Frontend preserves backend `decision`.
- [ ] Docker runtime reports `token-radar-v4`.
- [ ] Live 5m diagnostic can explain every unknown/address-only row by reason code.
