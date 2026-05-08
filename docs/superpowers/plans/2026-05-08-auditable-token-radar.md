# Auditable Token Trading Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-cut Token Radar into an auditable trading radar by wiring mature scoring functions into production projection, recording message-linked prices, and exposing token-level timeline/market ledgers.

**Architecture:** Keep `events`, `token_intents`, `token_intent_resolutions`, and `price_observations` as facts. Rebuild `token_radar_rows` as a deterministic v5 projection that calls the existing scoring modules and writes complete score ledgers. Extend `price_observations` with event attribution so the same ledger supports per-message prices, latest market, social-start baselines, first-snapshot deltas, timeline overlays, and market page deltas.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic, FastAPI, React/TypeScript, existing repository pattern, `uv run pytest`, `uv run ruff check .`, `uv run python -m compileall src tests`.

---

## File Structure

- Modify: `src/gmgn_twitter_intel/retrieval/tradeability_scoring.py`
  - Support `Asset` and `CexToken` as separate tradeability identities.
- Create: `src/gmgn_twitter_intel/pipeline/token_radar_feature_builder.py`
  - Convert grouped projection rows into scoring features.
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
  - Bump projection to `token-radar-v5-auditable`, remove old `_score()`/`_decision()`, call mature scoring functions.
- Create: `src/gmgn_twitter_intel/storage/alembic/versions/20260508_0011_event_price_observations.py`
  - Add message price attribution columns and indexes.
- Modify: `src/gmgn_twitter_intel/storage/price_observation_repository.py`
  - Insert/read message-linked observations and target baselines.
- Modify: `src/gmgn_twitter_intel/pipeline/ingest_service.py`
  - Store GMGN payload prices as `message_payload` observations with event/intent/resolution links.
- Create: `src/gmgn_twitter_intel/pipeline/message_market_observation.py`
  - Batch missing message price quotes for current CEX/DEX resolutions.
- Create: `src/gmgn_twitter_intel/pipeline/message_market_observation_worker.py`
  - Periodic worker wrapper for app lifespan.
- Modify: `src/gmgn_twitter_intel/market/okx_cex_client.py`
  - Add single-instrument ticker fetch used by message quote worker.
- Modify: `src/gmgn_twitter_intel/api/app.py`
  - Start/stop message market observation worker and expose health.
- Modify: `src/gmgn_twitter_intel/storage/token_target_repository.py`
  - Include message price fields in target timeline rows.
- Modify: `src/gmgn_twitter_intel/retrieval/token_target_social_timeline_service.py`
  - Return post price blocks and bucket price overlays.
- Modify: `src/gmgn_twitter_intel/retrieval/asset_flow_service.py`
  - Report v5 projection metadata.
- Modify: `src/gmgn_twitter_intel/cli.py`
  - Add token radar audit command.
- Modify: `web/src/api/types.ts`
  - Replace `price_health` contract with `tradeability`; add first-snapshot and post-price fields.
- Modify: `web/src/App.tsx`
  - Map v5 score/market fields and add token secondary page route state.
- Modify: `web/src/components/TokenRadarRow.tsx`
  - Show first-snapshot delta and v5 tradeability/timing status.
- Modify: `web/src/components/TokenTimeline.tsx`
  - Show bucket/post prices and observation status.
- Create: `web/src/components/TokenTargetPage.tsx`
  - Full token secondary page with timeline, posts, score ledger, and market ledger.
- Tests:
  - Modify: `tests/test_tradeability_scoring.py`
  - Create: `tests/test_token_radar_feature_builder.py`
  - Modify: `tests/test_token_radar_projection.py`
  - Create: `tests/test_event_price_observations.py`
  - Create: `tests/test_message_market_observation.py`
  - Modify: `tests/test_token_target_social_timeline_service.py`
  - Modify: `web/src/App.test.tsx`
  - Modify: `web/src/components/TokenRadarRow.test.tsx`

## Task 1: Tradeability Supports CEX And DEX Separately

**Files:**
- Modify: `src/gmgn_twitter_intel/retrieval/tradeability_scoring.py`
- Modify: `tests/test_tradeability_scoring.py`

- [ ] **Step 1: Write failing CEX tradeability test**

Add:

```python
def test_tradeability_scores_cex_token_without_chain_address_or_pool():
    payload = tradeability_score(
        {
            "target_type": "CexToken",
            "identity_status": "resolved_cex",
            "token_id": "cex_token:BTC",
            "pricefeed_id": "pricefeed:okx:BTC-USDT",
            "native_market_id": "BTC-USDT",
            "quote_symbol": "USDT",
            "market_status": "fresh",
            "volume_24h": 1_000_000_000,
            "open_interest": 500_000_000,
        }
    )

    assert payload["score"] >= 70
    assert "resolved_cex" in payload["reasons"]
    assert "fresh_market" in payload["reasons"]
    assert "missing_market_cap" not in payload["risks"]
    assert "missing_pool" not in payload["risks"]
    assert payload["identity_tradeable"] is True
```

- [ ] **Step 2: Write failing stale CEX cap test**

Add:

```python
def test_tradeability_caps_stale_cex_market():
    payload = tradeability_score(
        {
            "target_type": "CexToken",
            "identity_status": "resolved_cex",
            "token_id": "cex_token:ETH",
            "pricefeed_id": "pricefeed:okx:ETH-USDT",
            "native_market_id": "ETH-USDT",
            "quote_symbol": "USDT",
            "market_status": "stale",
            "volume_24h": 900_000_000,
        }
    )

    assert payload["score"] <= 70
    assert "stale_market" in payload["risks"]
    assert {"risk": "stale_market", "cap": 70} in payload["risk_caps"]
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
uv run pytest tests/test_tradeability_scoring.py -q
```

Expected: the new CEX tests fail because current tradeability requires `chain` and `address`.

- [ ] **Step 4: Replace tradeability identity logic**

Update `tradeability_score()` so identity and market requirements branch by `target_type`:

```python
target_type = str(features.get("target_type") or "")
identity_status = str(features.get("identity_status") or "")
is_asset = target_type == "Asset"
is_cex = target_type == "CexToken"

asset_identity_tradeable = (
    is_asset
    and identity_status == "resolved_ca"
    and bool(features.get("token_id"))
    and bool(features.get("chain"))
    and bool(features.get("address"))
)
cex_identity_tradeable = (
    is_cex
    and identity_status == "resolved_cex"
    and bool(features.get("token_id"))
    and bool(features.get("pricefeed_id"))
    and bool(features.get("native_market_id"))
)
identity_tradeable = asset_identity_tradeable or cex_identity_tradeable
```

Use these scoring rules:

- Identity: +30 for `resolved_ca` or `resolved_cex`; hard cap 20 when missing.
- Fresh market: +25 for `market_status == "fresh"`; cap 70 for stale; hard cap 35 for missing.
- Asset-only: +20 market cap, +15 liquidity, +10 pool.
- CEX-only: +15 volume when `volume_24h` exists, +10 open interest when `open_interest` exists, +10 quote sanity when quote is `USD/USDT/USDC`.

- [ ] **Step 5: Verify**

Run:

```bash
uv run pytest tests/test_tradeability_scoring.py -q
```

Expected: all tradeability tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/retrieval/tradeability_scoring.py tests/test_tradeability_scoring.py
git commit -m "feat: score cex and dex tradeability separately"
```

## Task 2: Build Production Radar Scoring Features

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/token_radar_feature_builder.py`
- Create: `tests/test_token_radar_feature_builder.py`

- [ ] **Step 1: Write feature builder tests**

Create `tests/test_token_radar_feature_builder.py`:

```python
from __future__ import annotations

from gmgn_twitter_intel.pipeline.token_radar_feature_builder import build_score_inputs


def test_feature_builder_outputs_auditable_social_features():
    rows = [
        row("event-1", "alice", 1_700_000_000_000, True, "BUY $PEPE liquidity up", "EXACT", 1.0),
        row("event-2", "bob", 1_700_000_030_000, False, "$PEPE market cap breakout", "EXACT", 1.0),
        row("event-3", "bob", 1_700_000_040_000, False, "$PEPE market cap breakout", "EXACT", 1.0),
    ]

    result = build_score_inputs(
        rows,
        market={
            "market_status": "fresh",
            "market_observation_status": "ready",
            "price_change_since_social_pct": 0.08,
            "price_change_before_social_pct": 0.02,
            "market_cap_usd": 10_000_000,
            "liquidity_usd": 1_000_000,
        },
        window="5m",
        scope="all",
        now_ms=1_700_000_060_000,
    )

    assert result.attention["mentions_window"] == 3
    assert result.attention["mentions_5m"] == 3
    assert result.attention["unique_authors"] == 2
    assert result.heat["mentions"] == 3
    assert result.quality["direct_mentions"] == 3
    assert result.quality["informative_post_count"] == 3
    assert result.quality["duplicate_text_share"] > 0
    assert result.propagation["independent_authors"] == 2
    assert result.timing["price_change_since_social_pct"] == 0.08


def row(event_id, author, received_at_ms, watched, text, resolution_status, confidence):
    return {
        "event_id": event_id,
        "intent_id": f"intent-{event_id}",
        "resolution_id": f"resolution-{event_id}",
        "received_at_ms": received_at_ms,
        "author_handle": author,
        "is_watched": watched,
        "text_clean": text,
        "text": text,
        "resolution_status": resolution_status,
        "target_type": "Asset",
        "target_id": "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
        "asset_chain_id": "eip155:1",
        "asset_address": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
        "asset_symbol": "PEPE",
        "pricefeed_id": "pricefeed:dex-token:gmgn:eip155:1:0x6982508145454ce325ddbe47a25d4ec3d2311933",
        "attribution_confidence": confidence,
    }
```

- [ ] **Step 2: Run failing test**

Run:

```bash
uv run pytest tests/test_token_radar_feature_builder.py -q
```

Expected: fails because `token_radar_feature_builder.py` does not exist.

- [ ] **Step 3: Implement feature builder**

Create `src/gmgn_twitter_intel/pipeline/token_radar_feature_builder.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..retrieval.discussion_quality_scoring import post_quality_score
from ..retrieval.post_text_quality import post_text_features


@dataclass(frozen=True, slots=True)
class RadarScoreInputs:
    attention: dict[str, Any]
    heat: dict[str, Any]
    quality: dict[str, Any]
    propagation: dict[str, Any]
    tradeability: dict[str, Any]
    timing: dict[str, Any]


def build_score_inputs(
    rows: list[dict[str, Any]],
    *,
    market: dict[str, Any],
    window: str,
    scope: str,
    now_ms: int,
) -> RadarScoreInputs:
    event_ids = sorted({str(row["event_id"]) for row in rows})
    authors = [str(row.get("author_handle") or "") for row in rows if row.get("author_handle")]
    author_counts = {author: authors.count(author) for author in set(authors)}
    watched_mentions = sum(1 for row in rows if row.get("is_watched"))
    received_times = [int(row.get("received_at_ms") or 0) for row in rows]
    social_start_ms = min(received_times) if received_times else None
    latest_seen_ms = max(received_times) if received_times else None
    mentions = len(event_ids)
    unique_authors = len(set(authors))
    top_author_share = max(author_counts.values()) / mentions if author_counts and mentions else 0.0
    texts = [str(row.get("text_clean") or row.get("text") or "") for row in rows]
    duplicate_share = _duplicate_text_share(texts)
    post_scores = [
        post_quality_score(
            {
                "text": text,
                "attribution_status": _post_attribution_status(row),
                "attribution_confidence": _confidence(row),
                "attribution_weight": _confidence(row),
                "is_watched": bool(row.get("is_watched")),
            }
        )
        for row, text in zip(rows, texts, strict=False)
    ]
    informative_count = sum(1 for text in texts if post_text_features(text)["informative"])
    market_context_count = sum(1 for text in texts if post_text_features(text)["has_market_context"])
    direct_mentions = sum(1 for row in rows if str(row.get("resolution_status") or "") == "EXACT")
    avg_confidence = sum(_confidence(row) for row in rows) / mentions if mentions else 0.0
    latest = max(rows, key=lambda row: int(row.get("received_at_ms") or 0)) if rows else {}
    attention = {
        "mentions_5m": mentions if window == "5m" else 0,
        "mentions_1h": mentions if window in {"5m", "1h"} else 0,
        "mentions_4h": mentions if window in {"5m", "1h", "4h"} else 0,
        "mentions_24h": mentions,
        "mentions_window": mentions,
        "unique_authors": unique_authors,
        "watched_mentions": watched_mentions,
        "social_signal_start_ms": social_start_ms,
        "latest_seen_ms": latest_seen_ms,
    }
    return RadarScoreInputs(
        attention=attention,
        heat={
            "mentions": mentions,
            **attention,
            "weighted_mentions": sum(_confidence(row) for row in rows),
            "previous_mentions": 0,
            "mention_delta": mentions,
            "stream_share": 0.0,
            "watched_share": watched_mentions / mentions if mentions else 0.0,
            "is_new_local_evidence": True,
            "is_first_seen_by_watched": watched_mentions > 0,
            "new_burst_score": mentions if mentions else 0,
        },
        quality={
            "mentions": mentions,
            "direct_mentions": direct_mentions,
            "avg_attribution_confidence": avg_confidence,
            "duplicate_text_share": duplicate_share,
            "informative_post_count": informative_count,
            "watched_source_count": watched_mentions,
            "market_context_count": market_context_count,
            "avg_post_quality": round(sum(int(item["score"]) for item in post_scores) / mentions) if mentions else 0,
        },
        propagation={
            "mentions": mentions,
            "independent_authors": unique_authors,
            "effective_authors": _effective_authors(author_counts),
            "new_authors": unique_authors,
            "top_author_share": top_author_share,
            "duplicate_text_share": duplicate_share,
            "watched_author_count": len({str(row.get("author_handle")) for row in rows if row.get("is_watched") and row.get("author_handle")}),
            "seed_lag_ms": 0 if watched_mentions else None,
            "reproduction_rate": 1.0 if unique_authors >= 2 and mentions >= 3 else 0.0,
            "phase_hint": None,
        },
        tradeability=_tradeability_features(latest, market),
        timing={
            "social_signal_start_ms": social_start_ms,
            "price_change_since_social_pct": market.get("price_change_since_social_pct"),
            "price_change_before_social_pct": market.get("price_change_before_social_pct"),
            "market_observation_status": market.get("market_observation_status"),
        },
    )
```

Also add private helpers `_confidence`, `_post_attribution_status`, `_duplicate_text_share`, `_effective_authors`, and `_tradeability_features` in the same file. `_tradeability_features` must emit `target_type = "Asset"` with `resolved_ca` and `target_type = "CexToken"` with `resolved_cex`.

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest tests/test_token_radar_feature_builder.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/pipeline/token_radar_feature_builder.py tests/test_token_radar_feature_builder.py
git commit -m "feat: build auditable token radar score features"
```

## Task 3: Wire Mature Scores Into Production Projection

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- Modify: `tests/test_token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/retrieval/asset_flow_service.py`

- [ ] **Step 1: Write projection scoring contract test**

Add:

```python
def test_projection_uses_mature_auditable_score_blocks():
    rows = [
        {
            "event_id": "event-1",
            "intent_id": "intent-1",
            "resolution_id": "resolution-1",
            "received_at_ms": 1_777_800_000_000,
            "author_handle": "alice",
            "text": "PEPE liquidity breakout",
            "text_clean": "PEPE liquidity breakout",
            "is_watched": True,
            "resolution_status": "EXACT",
            "target_type": "Asset",
            "target_id": "asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
            "pricefeed_id": "pricefeed:dex-token:gmgn:eip155:1:0x6982508145454ce325ddbe47a25d4ec3d2311933",
            "display_symbol": "PEPE",
            "asset_symbol": "PEPE",
            "asset_chain_id": "eip155:1",
            "asset_address": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
            "market_provider": "gmgn_payload",
            "market_observed_at_ms": 1_777_800_000_000,
            "market_price_usd": 0.01,
            "market_market_cap_usd": 1_000_000,
            "market_liquidity_usd": 250_000,
            "reason_codes_json": [],
            "candidate_ids_json": [],
            "lookup_keys_json": [],
        }
    ]

    row = _project_group(rows, now_ms=1_777_800_030_000, window="5m", scope="all")

    score = row["score_json"]
    assert set(score) == {"heat", "quality", "propagation", "tradeability", "timing", "opportunity"}
    assert score["heat"]["score_version"] == "social_heat_v2"
    assert score["quality"]["score_version"] == "discussion_quality_v2"
    assert score["propagation"]["score_version"] == "propagation_v2"
    assert score["tradeability"]["score_version"] == "tradeability_v2"
    assert score["timing"]["score_version"] == "timing_v4"
    assert score["opportunity"]["score_version"] == "social_opportunity_v3"
    assert score["heat"]["contributions"]
    assert score["quality"]["contributions"]
    assert "price_health" not in score
```

- [ ] **Step 2: Run failing projection test**

Run:

```bash
uv run pytest tests/test_token_radar_projection.py::test_projection_uses_mature_auditable_score_blocks -q
```

Expected: fails because projection still returns `price_health` and `token_radar_v4`.

- [ ] **Step 3: Replace projection version and scoring imports**

In `token_radar_projection.py`:

```python
from ..retrieval.discussion_quality_scoring import discussion_quality_score
from ..retrieval.opportunity_scoring import opportunity_score
from ..retrieval.propagation_scoring import propagation_score
from ..retrieval.social_heat_scoring import social_heat_score
from ..retrieval.timing_scoring import timing_score
from ..retrieval.tradeability_scoring import tradeability_score
from .token_radar_feature_builder import build_score_inputs

PROJECTION_VERSION = "token-radar-v5-auditable"
```

Remove `_score()`, `_score_block()`, and `_decision()` from production use. They can be deleted in the same task because v5 is a hard cut.

- [ ] **Step 4: Replace score construction**

Inside `_project_group()`:

```python
score_inputs = build_score_inputs(rows, market=market, window=window, scope=scope, now_ms=now_ms)
score = _score(score_inputs)
decision = str(score["opportunity"]["decision"])
```

Add:

```python
def _score(score_inputs) -> dict[str, Any]:
    components = {
        "heat": social_heat_score(score_inputs.heat),
        "quality": discussion_quality_score(score_inputs.quality),
        "propagation": propagation_score(score_inputs.propagation),
        "tradeability": tradeability_score(score_inputs.tradeability),
        "timing": timing_score(score_inputs.timing),
    }
    return {**components, "opportunity": opportunity_score(components)}
```

Use `score_inputs.attention` as `attention_json`.

- [ ] **Step 5: Rank by trading decision and opportunity**

Replace `_rank_key()` with:

```python
def _rank_key(row: dict[str, Any]) -> tuple[int, int, int, int]:
    score = row.get("score_json") or {}
    opportunity = score.get("opportunity") or {}
    attention = row["attention_json"]
    decision_priority = int(opportunity.get("decision_priority") or 0)
    opportunity_score_value = int(opportunity.get("score") or 0)
    return (
        -decision_priority,
        -opportunity_score_value,
        -int(attention["mentions_window"]),
        -int(attention["latest_seen_ms"] or 0),
    )
```

- [ ] **Step 6: Update projection metadata**

In `asset_flow_service.py`, set projection version to `token-radar-v5-auditable`.

- [ ] **Step 7: Verify projection tests**

Run:

```bash
uv run pytest tests/test_token_radar_projection.py tests/test_social_heat_scoring.py tests/test_discussion_quality_scoring.py tests/test_propagation_scoring.py tests/test_timing_scoring.py tests/test_tradeability_scoring.py -q
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add src/gmgn_twitter_intel/pipeline/token_radar_projection.py src/gmgn_twitter_intel/retrieval/asset_flow_service.py tests/test_token_radar_projection.py
git commit -m "feat: project token radar with auditable scoring"
```

## Task 4: Add Event Attribution To Price Observations

**Files:**
- Create: `src/gmgn_twitter_intel/storage/alembic/versions/20260508_0011_event_price_observations.py`
- Modify: `src/gmgn_twitter_intel/storage/price_observation_repository.py`
- Create: `tests/test_event_price_observations.py`

- [ ] **Step 1: Write repository test**

Create:

```python
from __future__ import annotations

from gmgn_twitter_intel.pipeline.deterministic_token_resolver import DeterministicResolution
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.intent_resolution_repository import IntentResolutionRepository
from gmgn_twitter_intel.storage.price_observation_repository import PriceObservationRepository
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_price_observation_insert_accepts_message_attribution(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        EvidenceRepository(conn).insert_event(
            make_event(event_id="event-1", received_at_ms=1_700_000_000_000),
            is_watched=True,
        )
        conn.execute(
            """
            INSERT INTO token_intents(
              intent_id, event_id, intent_key, construction_policy, primary_evidence_id,
              display_symbol, display_name, chain_hint, address_hint, intent_status,
              intent_confidence, created_at_ms, updated_at_ms
            )
            VALUES (
              'intent-1', 'event-1', 'symbol:PEPE', 'test', NULL,
              'PEPE', NULL, NULL, NULL, 'pending', 1.0, 1700000000000, 1700000000000
            )
            """
        )
        resolution = IntentResolutionRepository(conn).insert_resolution(
            DeterministicResolution(
                intent_id="intent-1",
                event_id="event-1",
                resolution_status="EXACT",
                target_type="Asset",
                target_id="asset-1",
                pricefeed_id=None,
                resolver_policy_version="token_radar_v4_deterministic_resolver",
                reason_codes=[],
                candidate_ids=["asset-1"],
                lookup_keys=["symbol:PEPE"],
                decision_time_ms=1_700_000_000_000,
                created_at_ms=1_700_000_000_000,
            ),
            commit=False,
        )
        row = PriceObservationRepository(conn).insert_observation(
            provider="gmgn_payload",
            pricefeed_id=None,
            observed_at_ms=1_700_000_000_000,
            subject_type="Asset",
            subject_id="asset-1",
            price_usd=0.01,
            price_basis="usd",
            source_event_id="event-1",
            source_intent_id="intent-1",
            source_resolution_id=resolution["resolution_id"],
            observation_kind="message_payload",
            event_received_at_ms=1_700_000_000_000,
            commit=False,
        )
    finally:
        conn.close()

    assert row["source_event_id"] == "event-1"
    assert row["source_intent_id"] == "intent-1"
    assert row["source_resolution_id"] == resolution["resolution_id"]
    assert row["observation_kind"] == "message_payload"
    assert row["observation_lag_ms"] == 0
```

Add a second repository test for id separation:

```python
def test_message_and_refresh_price_observations_do_not_collide(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        observations = PriceObservationRepository(conn)
        refresh = observations.insert_observation(
            provider="okx_cex",
            pricefeed_id=None,
            observed_at_ms=1_700_000_000_000,
            subject_type="CexToken",
            subject_id="cex_token:BTC",
            price_quote=70_000,
            quote_symbol="USDT",
            price_basis="quote_as_usd",
            observation_kind="refresh",
            commit=False,
        )
        message = observations.insert_observation(
            provider="okx_cex",
            pricefeed_id=None,
            observed_at_ms=1_700_000_000_000,
            subject_type="CexToken",
            subject_id="cex_token:BTC",
            price_quote=70_000,
            quote_symbol="USDT",
            price_basis="quote_as_usd",
            source_event_id=None,
            source_intent_id=None,
            observation_kind="message_quote",
            event_received_at_ms=1_699_999_999_000,
            commit=False,
        )
    finally:
        conn.close()

    assert refresh["observation_id"] != message["observation_id"]
    assert message["observation_lag_ms"] == 1_000
```

- [ ] **Step 2: Run failing test**

Run:

```bash
uv run pytest tests/test_event_price_observations.py -q
```

Expected: fails because schema/repository fields do not exist.

- [ ] **Step 3: Add Alembic migration**

Create `20260508_0011_event_price_observations.py`:

```python
"""Add event-linked price observation fields."""

from __future__ import annotations

from alembic import op

revision = "20260508_0011"
down_revision = "20260507_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS source_event_id TEXT REFERENCES events(event_id) ON DELETE SET NULL")
    op.execute("ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS source_intent_id TEXT REFERENCES token_intents(intent_id) ON DELETE SET NULL")
    op.execute("ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS source_resolution_id TEXT REFERENCES token_intent_resolutions(resolution_id) ON DELETE SET NULL")
    op.execute("ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS observation_kind TEXT NOT NULL DEFAULT 'refresh'")
    op.execute("ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS event_received_at_ms BIGINT")
    op.execute("ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS observation_lag_ms BIGINT")
    op.execute("CREATE INDEX IF NOT EXISTS idx_price_observations_source_event ON price_observations(source_event_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_price_observations_source_intent ON price_observations(source_intent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_price_observations_subject_time_kind ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_kind)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_price_observations_subject_time_kind")
    op.execute("DROP INDEX IF EXISTS idx_price_observations_source_intent")
    op.execute("DROP INDEX IF EXISTS idx_price_observations_source_event")
    op.execute("ALTER TABLE price_observations DROP COLUMN IF EXISTS observation_lag_ms")
    op.execute("ALTER TABLE price_observations DROP COLUMN IF EXISTS event_received_at_ms")
    op.execute("ALTER TABLE price_observations DROP COLUMN IF EXISTS observation_kind")
    op.execute("ALTER TABLE price_observations DROP COLUMN IF EXISTS source_resolution_id")
    op.execute("ALTER TABLE price_observations DROP COLUMN IF EXISTS source_intent_id")
    op.execute("ALTER TABLE price_observations DROP COLUMN IF EXISTS source_event_id")
```

- [ ] **Step 4: Update repository insert**

Add keyword arguments:

```python
source_event_id: str | None = None
source_intent_id: str | None = None
source_resolution_id: str | None = None
observation_kind: str = "refresh"
event_received_at_ms: int | None = None
```

Compute:

```python
observation_lag_ms = (
    max(0, int(observed_at_ms) - int(event_received_at_ms))
    if event_received_at_ms is not None
    else None
)
```

Include the new fields in `INSERT`, `ON CONFLICT DO UPDATE`, and return payload. Change `_stable_id()` inputs to include `observation_kind`, `source_event_id`, `source_intent_id`, and `observed_at_ms` so message observations do not collide with refresh observations.

- [ ] **Step 5: Add baseline read methods**

Add methods:

```python
def first_for_subject(self, *, subject_type: str, subject_id: str) -> dict[str, Any] | None: ...
def latest_message_for_event(self, *, event_id: str, subject_type: str, subject_id: str) -> dict[str, Any] | None: ...
def latest_for_subject_at_or_before(self, *, subject_type: str, subject_id: str, at_or_before_ms: int) -> dict[str, Any] | None: ...
```

The SQL for the last method is the same ordering as `latest_for_subject()`, with `observed_at_ms <= %s`.

- [ ] **Step 6: Verify**

Run:

```bash
uv run pytest tests/test_event_price_observations.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add src/gmgn_twitter_intel/storage/alembic/versions/20260508_0011_event_price_observations.py src/gmgn_twitter_intel/storage/price_observation_repository.py tests/test_event_price_observations.py
git commit -m "feat: link price observations to token messages"
```

## Task 5: Store GMGN Payload Prices As Message Prices

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/ingest_service.py`
- Modify: tests covering ingest payload price observations

- [ ] **Step 1: Write failing ingest assertion**

In the ingest test that already verifies GMGN payload price insertion, assert the inserted observation includes:

```python
assert observation["source_event_id"] == event.event_id
assert observation["source_intent_id"] in {intent["intent_id"] for intent in result.token_intents}
assert observation["source_resolution_id"] in {resolution["resolution_id"] for resolution in result.token_resolutions}
assert observation["observation_kind"] == "message_payload"
assert observation["event_received_at_ms"] == event.received_at_ms
assert observation["observation_lag_ms"] == 0
```

- [ ] **Step 2: Run failing ingest test**

Run the specific ingest test file:

```bash
uv run pytest tests -q -k gmgn_payload
```

Expected: fails on the new message attribution fields.

- [ ] **Step 3: Pass current resolution rows into price insert**

Change the ingest flow from:

```python
self._insert_gmgn_payload_price_observation(event, decisions)
```

to:

```python
self._insert_gmgn_payload_price_observation(event, token_resolutions)
```

Change `_insert_gmgn_payload_price_observation()` to iterate current resolution rows. Pass:

```python
source_event_id=event.event_id,
source_intent_id=str(resolution["intent_id"]),
source_resolution_id=str(resolution["resolution_id"]),
observation_kind="message_payload",
event_received_at_ms=event.received_at_ms,
```

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest tests -q -k gmgn_payload
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/pipeline/ingest_service.py tests
git commit -m "feat: record gmgn payload prices per message"
```

## Task 6: Add Message Market Observation Worker

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/message_market_observation.py`
- Create: `src/gmgn_twitter_intel/pipeline/message_market_observation_worker.py`
- Modify: `src/gmgn_twitter_intel/market/okx_cex_client.py`
- Modify: `src/gmgn_twitter_intel/api/app.py`
- Create: `tests/test_message_market_observation.py`

- [ ] **Step 1: Write worker unit tests**

Create tests for CEX and DEX:

```python
def test_message_observer_writes_cex_message_quote(fake_repos):
    fake_repos.seed_current_resolution(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        target_type="CexToken",
        target_id="cex_token:BTC",
        pricefeed_id="pricefeed:okx:BTC-USDT",
        received_at_ms=1_700_000_000_000,
        native_market_id="BTC-USDT",
    )
    result = observe_message_prices_once(
        repos=fake_repos,
        cex_client=FakeCexClient(last_price=70_000, observed_at_ms=1_700_000_001_000),
        dex_client=None,
        now_ms=1_700_000_001_000,
        limit=50,
    )

    assert result["observations_written"] == 1
    observation = fake_repos.price_observations.latest_message_for_event(
        event_id="event-1",
        subject_type="CexToken",
        subject_id="cex_token:BTC",
    )
    assert observation["observation_kind"] == "message_quote"
    assert observation["source_event_id"] == "event-1"
    assert observation["price_quote"] == 70_000
    assert observation["observation_lag_ms"] == 1_000


def test_message_observer_writes_dex_message_quote(fake_repos):
    fake_repos.seed_current_resolution(
        event_id="event-2",
        intent_id="intent-2",
        resolution_id="resolution-2",
        target_type="Asset",
        target_id="asset:eip155:1:erc20:0x6982508145454ce325ddbe47a25d4ec3d2311933",
        pricefeed_id="pricefeed:dex:pepe",
        received_at_ms=1_700_000_000_000,
        chain_id="eip155:1",
        address="0x6982508145454ce325ddbe47a25d4ec3d2311933",
    )
    result = observe_message_prices_once(
        repos=fake_repos,
        cex_client=None,
        dex_client=FakeDexClient(price_usd=0.01, observed_at_ms=1_700_000_002_000),
        now_ms=1_700_000_002_000,
        limit=50,
    )

    assert result["observations_written"] == 1
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
uv run pytest tests/test_message_market_observation.py -q
```

Expected: fails because observer module does not exist.

- [ ] **Step 3: Add OKX CEX single ticker method**

In `OkxCexClient`, add:

```python
def ticker(self, *, inst_id: str) -> OkxCexTicker | None:
    rows = self._get("/api/v5/market/ticker", params={"instId": inst_id.strip().upper()})
    for row in rows:
        ticker = _ticker_from_row(row)
        if ticker is not None:
            return ticker
    return None
```

- [ ] **Step 4: Implement observer selection query**

Create `observe_message_prices_once()` that selects current resolved intents with no existing `message_payload` or `message_quote` observation for the same `source_intent_id`.

The SQL must include:

```sql
WHERE tir.is_current = true
  AND tir.target_type IN ('Asset', 'CexToken')
  AND NOT EXISTS (
    SELECT 1
    FROM price_observations po
    WHERE po.source_intent_id = tir.intent_id
      AND po.observation_kind IN ('message_payload', 'message_quote')
  )
ORDER BY events.received_at_ms ASC
LIMIT %s
```

- [ ] **Step 5: Implement CEX quote write**

For `CexToken`, use `price_feeds.native_market_id` and `cex_client.ticker(inst_id=...)`. Insert:

```python
observation_kind="message_quote",
source_event_id=row["event_id"],
source_intent_id=row["intent_id"],
source_resolution_id=row["resolution_id"],
event_received_at_ms=row["received_at_ms"],
provider="okx_cex",
price_quote=ticker.last_price,
price_usd=ticker.last_price if quote_symbol in {"USD", "USDT", "USDC"} else None,
quote_symbol=quote_symbol,
price_basis="quote_as_usd" if quote_symbol in {"USD", "USDT", "USDC"} else "quote",
```

- [ ] **Step 6: Implement DEX quote write**

For `Asset`, batch rows by chain/address and call `dex_client.token_prices()`. Insert:

```python
observation_kind="message_quote",
source_event_id=row["event_id"],
source_intent_id=row["intent_id"],
source_resolution_id=row["resolution_id"],
event_received_at_ms=row["received_at_ms"],
provider="okx_dex_price",
price_usd=price.price_usd,
price_basis="usd",
```

- [ ] **Step 7: Add worker wrapper**

Create `MessageMarketObservationWorker` with the same lifecycle shape as `TokenDiscoveryWorker`: `run()`, `run_once()`, `stop()`, `close()`, `last_started_at_ms`, `last_run_at_ms`, `last_result`, `last_error`.

- [ ] **Step 8: Start worker in FastAPI lifespan**

In `api/app.py`, instantiate the worker when at least one market client is configured. Include health:

```json
"message_market_observation": {
  "enabled": true,
  "worker_running": true,
  "last_run_at_ms": 1777800000000,
  "last_result": {}
}
```

- [ ] **Step 9: Verify**

Run:

```bash
uv run pytest tests/test_message_market_observation.py -q
```

Expected: pass.

- [ ] **Step 10: Commit**

```bash
git add src/gmgn_twitter_intel/pipeline/message_market_observation.py src/gmgn_twitter_intel/pipeline/message_market_observation_worker.py src/gmgn_twitter_intel/market/okx_cex_client.py src/gmgn_twitter_intel/api/app.py tests/test_message_market_observation.py
git commit -m "feat: observe market prices for resolved token messages"
```

## Task 7: Compute Market Baselines In Radar Projection

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- Modify: `tests/test_token_radar_projection.py`

- [ ] **Step 1: Write baseline projection test**

Add:

```python
def test_projection_market_includes_social_and_first_snapshot_deltas():
    market = _market(
        {
            "target_type": "Asset",
            "target_id": "asset-1",
            "market_provider": "gmgn_payload",
            "market_observed_at_ms": 1_700_000_060_000,
            "market_price_usd": 1.20,
            "market_price_quote": None,
            "market_quote_symbol": None,
            "market_price_basis": "usd",
            "market_market_cap_usd": 1_000_000,
            "market_liquidity_usd": 200_000,
            "social_price_usd": 1.00,
            "social_price_observed_at_ms": 1_700_000_000_000,
            "first_price_usd": 0.80,
            "first_price_observed_at_ms": 1_699_999_000_000,
            "before_social_price_usd": 0.95,
            "before_social_price_observed_at_ms": 1_699_999_900_000,
        },
        resolved=True,
        now_ms=1_700_000_060_000,
    )

    assert market["price_at_social_start"] == 1.00
    assert market["price_change_since_social_pct"] == 0.2
    assert market["price_at_first_snapshot"] == 0.80
    assert market["price_change_since_first_snapshot_pct"] == 0.5
    assert market["price_change_before_social_pct"] == 0.052632
```

- [ ] **Step 2: Run failing test**

Run:

```bash
uv run pytest tests/test_token_radar_projection.py::test_projection_market_includes_social_and_first_snapshot_deltas -q
```

Expected: fails because market baselines are currently null.

- [ ] **Step 3: Add price baseline lateral joins**

In `_source_rows()`, add three LATERAL joins:

- `event_price`: latest observation for target/feed at or before `events.received_at_ms`.
- `before_event_price`: latest observation before `events.received_at_ms - 5 * 60 * 1000`.
- `first_price`: earliest observation for target/feed.

Select aliased fields:

```sql
event_price.price_usd AS social_price_usd,
event_price.price_quote AS social_price_quote,
event_price.observed_at_ms AS social_price_observed_at_ms,
before_event_price.price_usd AS before_social_price_usd,
before_event_price.price_quote AS before_social_price_quote,
before_event_price.observed_at_ms AS before_social_price_observed_at_ms,
first_price.price_usd AS first_price_usd,
first_price.price_quote AS first_price_quote,
first_price.observed_at_ms AS first_price_observed_at_ms
```

Use the same target/feed matching predicate as `latest_price`.

- [ ] **Step 4: Compute baseline fields in `_market()`**

Add helper:

```python
def _pct_change(current: Any, base: Any) -> float | None:
    current_value = _float_or_none(current)
    base_value = _float_or_none(base)
    if current_value is None or base_value in (None, 0.0):
        return None
    return round(current_value / base_value - 1.0, 6)
```

Use USD first, quote second:

```python
reference_price = row.get("market_price_usd") or row.get("market_price_quote")
social_price = row.get("social_price_usd") or row.get("social_price_quote")
first_price = row.get("first_price_usd") or row.get("first_price_quote")
before_social_price = row.get("before_social_price_usd") or row.get("before_social_price_quote")
```

Set `price_change_status = "ready"` when reference and social prices both exist. Set `price_change_status = "insufficient_history"` when latest price exists but social baseline is missing.

- [ ] **Step 5: Verify**

Run:

```bash
uv run pytest tests/test_token_radar_projection.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/gmgn_twitter_intel/pipeline/token_radar_projection.py tests/test_token_radar_projection.py
git commit -m "feat: project token radar market baselines"
```

## Task 8: Return Message Prices In Target Timeline

**Files:**
- Modify: `src/gmgn_twitter_intel/storage/token_target_repository.py`
- Modify: `src/gmgn_twitter_intel/retrieval/token_target_social_timeline_service.py`
- Modify: `tests/test_token_target_social_timeline_service.py`

- [ ] **Step 1: Write timeline post price test**

Add:

```python
def test_token_target_timeline_includes_post_price_and_bucket_price():
    service = TokenTargetSocialTimelineService(
        targets=FakeTargets(
            rows=[
                timeline_row(
                    target_type="Asset",
                    target_id="asset-1",
                    symbol="PEPE",
                    chain_id="eip155:1",
                    address="0x6982508145454ce325ddbe47a25d4ec3d2311933",
                    price_usd=0.01,
                    price_observed_at_ms=1_700_000_000_500,
                    observation_lag_ms=500,
                    price_observation_status="ready",
                )
            ]
        )
    )

    result = service.timeline(
        target_type="Asset",
        target_id="asset-1",
        window="1h",
        scope="all",
        limit=50,
        now_ms=1_700_000_060_000,
    )

    assert result["posts"][0]["price"]["status"] == "ready"
    assert result["posts"][0]["price"]["price_usd"] == 0.01
    assert result["posts"][0]["price"]["observation_lag_ms"] == 500
    assert result["buckets"][0]["price"] == 0.01
```

- [ ] **Step 2: Run failing test**

Run:

```bash
uv run pytest tests/test_token_target_social_timeline_service.py -q
```

Expected: fails because posts do not expose price.

- [ ] **Step 3: Add message price lateral join**

In `TokenTargetRepository.timeline_rows()`, add a LATERAL join selecting the best message-linked observation:

```sql
LEFT JOIN LATERAL (
  SELECT *
  FROM price_observations
  WHERE price_observations.source_event_id = events.event_id
    AND price_observations.subject_type = tir.target_type
    AND price_observations.subject_id = tir.target_id
    AND price_observations.observation_kind IN ('message_payload', 'message_quote')
  ORDER BY
    CASE WHEN price_observations.observation_kind = 'message_payload' THEN 0 ELSE 1 END,
    price_observations.observed_at_ms DESC
  LIMIT 1
) message_price ON true
```

Select `message_price.observation_id`, `provider`, `price_usd`, `price_quote`, `quote_symbol`, `price_basis`, `observed_at_ms`, `observation_lag_ms`.

- [ ] **Step 4: Build post price block**

In `_post()`, add:

```python
"price": _post_price(row)
```

Implement:

```python
def _post_price(row: dict[str, Any]) -> dict[str, Any]:
    observation_id = row.get("price_observation_id")
    if not observation_id:
        return {
            "status": "pending_observation",
            "provider": None,
            "pricefeed_id": row.get("pricefeed_id"),
            "price_usd": None,
            "price_quote": None,
            "quote_symbol": row.get("quote_symbol"),
            "observed_at_ms": None,
            "observation_lag_ms": None,
            "observation_id": None,
        }
    lag = row.get("price_observation_lag_ms")
    status = "stale" if lag is not None and int(lag) > 5 * 60 * 1000 else "ready"
    return {
        "status": status,
        "provider": row.get("price_provider"),
        "pricefeed_id": row.get("pricefeed_id"),
        "price_usd": row.get("price_usd"),
        "price_quote": row.get("price_quote"),
        "quote_symbol": row.get("price_quote_symbol") or row.get("quote_symbol"),
        "observed_at_ms": row.get("price_observed_at_ms"),
        "observation_lag_ms": lag,
        "observation_id": observation_id,
    }
```

- [ ] **Step 5: Build bucket price overlay**

In `_buckets()`, when a row has `price_usd` or `price_quote`, set bucket `price` to the last row price in that bucket and compute `price_change_from_start_pct` from the first bucket with price.

- [ ] **Step 6: Verify**

Run:

```bash
uv run pytest tests/test_token_target_social_timeline_service.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add src/gmgn_twitter_intel/storage/token_target_repository.py src/gmgn_twitter_intel/retrieval/token_target_social_timeline_service.py tests/test_token_target_social_timeline_service.py
git commit -m "feat: expose message prices in token timelines"
```

## Task 9: Update Frontend To V5 Radar Contract

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/TokenRadarRow.tsx`
- Modify: `web/src/components/TokenTimeline.tsx`
- Create: `web/src/components/TokenTargetPage.tsx`
- Modify: `web/src/App.test.tsx`
- Modify: `web/src/components/TokenRadarRow.test.tsx`

- [ ] **Step 1: Update type tests/fixtures**

Change test fixtures so `score` uses:

```ts
score: {
  heat: scoreBlock({ score_version: "social_heat_v2", score: 68 }),
  quality: scoreBlock({ score_version: "discussion_quality_v2", score: 63 }),
  propagation: scoreBlock({ score_version: "propagation_v2", score: 61 }),
  tradeability: scoreBlock({ score_version: "tradeability_v2", score: 78 }),
  timing: scoreBlock({ score_version: "timing_v4", score: 50 }),
  opportunity: scoreBlock({
    score_version: "social_opportunity_v3",
    score: 72,
    decision: "driver",
    decision_priority: 3,
    components: { heat: 68, quality: 63, propagation: 61, tradeability: 78, timing: 50 },
  }),
}
```

Remove all fixture references to `price_health`.

- [ ] **Step 2: Run failing frontend tests**

Run:

```bash
cd web && npm test -- --runInBand
```

Expected: fails on old `price_health` assumptions and missing token page component.

- [ ] **Step 3: Update API types**

In `AssetFlowRow["score"]`, replace `price_health` with `tradeability`. Add market fields:

```ts
price_at_first_snapshot?: number | null;
first_snapshot_observed_at_ms?: number | null;
price_change_since_first_snapshot_pct?: number | null;
```

In timeline post type, add:

```ts
price: {
  status: string;
  provider?: string | null;
  pricefeed_id?: string | null;
  price_usd?: number | null;
  price_quote?: number | null;
  quote_symbol?: string | null;
  observed_at_ms?: number | null;
  observation_lag_ms?: number | null;
  observation_id?: string | null;
};
```

- [ ] **Step 4: Update `tokenRadarRowToTokenItem()`**

Map:

```ts
tradeability: score.tradeability ?? emptyScoreBlock("tradeability_v2")
```

Remove `price_health` mapping. Use backend `opportunity.decision` as the displayed decision. Map first-snapshot fields into `item.market`.

- [ ] **Step 5: Add token secondary page**

Create `TokenTargetPage.tsx` with props:

```ts
type TokenTargetPageProps = {
  token: TokenFlowItem;
  timeline: TokenSocialTimelineData | null;
  onBack: () => void;
};
```

Render unframed sections:

- Header with symbol, target type, venue, latest price, social delta, first snapshot delta.
- Timeline using existing `TokenTimeline`.
- Posts list with post quality and price status.
- Score ledger using existing `ScoreLedger`.
- Market ledger with first snapshot, social start, latest observation.

- [ ] **Step 6: Add route state in `App.tsx`**

Use simple state, not a new router dependency:

```ts
const [selectedPageTokenId, setSelectedPageTokenId] = useState<string | null>(null);
```

When a radar row secondary action is clicked, set the token id. Render `TokenTargetPage` instead of the main cockpit when selected. Keep the existing drawer for quick inspection.

- [ ] **Step 7: Update row display**

In `TokenRadarRow.tsx`, show market delta priority:

1. `price_change_since_social_pct`
2. `price_change_since_first_snapshot_pct`
3. market status

Add a compact label for first snapshot delta when social delta is missing:

```ts
`${formatSignedPercent(item.market.price_change_since_first_snapshot_pct)} since first`
```

- [ ] **Step 8: Verify frontend**

Run:

```bash
cd web && npm test -- --runInBand
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add web/src/api/types.ts web/src/App.tsx web/src/components/TokenRadarRow.tsx web/src/components/TokenTimeline.tsx web/src/components/TokenTargetPage.tsx web/src/App.test.tsx web/src/components/TokenRadarRow.test.tsx
git commit -m "feat: show auditable token radar contract in web"
```

## Task 10: Add Token Radar Audit Command

**Files:**
- Modify: `src/gmgn_twitter_intel/cli.py`
- Create: `tests/test_token_radar_audit_cli.py`

- [ ] **Step 1: Define audit output contract**

Add CLI command:

```bash
uv run gmgn-twitter-intel ops audit-token-radar --window 1h --scope all --limit 200
```

Output JSON keys:

```json
{
  "projection_version": "token-radar-v5-auditable",
  "rows": 200,
  "score_blocks_missing_contributions": 0,
  "rows_with_price_health_legacy_key": 0,
  "rows_with_tradeability": 200,
  "driver_rows_with_stale_or_missing_market": 0,
  "resolved_rows_missing_message_price_coverage": 0,
  "heat_100_count": 0,
  "quality_100_count": 0
}
```

- [ ] **Step 2: Write failing CLI test**

Add a `tests/test_cli.py` method next to `test_db_audit_query_audit_and_token_radar_projection_ops_use_postgres_only`:

```python
def test_token_radar_audit_rejects_legacy_score_contract(self):
    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir)
        db_path = home / ".gmgn-twitter-intel" / "postgres_test_db"
        write_runtime_config(home, db_path=db_path)
        conn = connect_postgres_test(db_path, read_only=False)
        try:
            migrate(conn)
            conn.execute(
                """
                INSERT INTO token_radar_rows(
                  row_id, projection_version, window, scope, computed_at_ms, lane, rank,
                  intent_id, event_id, target_type, target_id, pricefeed_id,
                  intent_json, asset_json, target_json, primary_venue_json,
                  attention_json, resolution_json, market_json, price_json,
                  score_json, decision, data_health_json, source_event_ids_json,
                  source_max_received_at_ms, created_at_ms
                )
                VALUES (
                  'row-legacy', 'token-radar-v5-auditable', '5m', 'all', 1700000000000, 'resolved', 1,
                  'intent-1', 'event-1', 'Asset', 'asset-1', NULL,
                  '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, NULL,
                  '{"mentions_window": 1, "latest_seen_ms": 1700000000000}'::jsonb,
                  '{}'::jsonb, '{"market_status": "fresh"}'::jsonb, '{"market_status": "fresh"}'::jsonb,
                  '{"price_health": {"score": 80}, "heat": {"score": 100, "contributions": []}}'::jsonb,
                  'driver', '{}'::jsonb, '["event-1"]'::jsonb,
                  1700000000000, 1700000000000
                )
                """
            )
            conn.commit()
        finally:
            conn.close()
        stdout = io.StringIO()
        with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
            exit_code = main(["ops", "audit-token-radar", "--window", "5m", "--scope", "all"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    self.assertEqual(exit_code, 1)
    self.assertEqual(payload["data"]["rows_with_price_health_legacy_key"], 1)
    self.assertEqual(payload["data"]["score_blocks_missing_contributions"], 1)
```

- [ ] **Step 3: Implement audit query**

Read latest rows from `token_radar_rows` for window/scope. Count:

- missing `score_json.tradeability`
- present `score_json.price_health`
- any component with empty `contributions`
- driver rows where `market_json.market_status != "fresh"`
- resolved rows whose `source_event_ids_json` has no matching message price observations
- exact 100 counts for heat and quality

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest tests/test_token_radar_audit_cli.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/gmgn_twitter_intel/cli.py tests/test_token_radar_audit_cli.py
git commit -m "feat: audit token radar scoring and price coverage"
```

## Task 11: End-To-End Verification

**Files:**
- No new files.
- Touch only failing tests or implementation files if verification exposes a real defect.

- [ ] **Step 1: Run backend targeted tests**

Run:

```bash
uv run pytest tests/test_token_radar_projection.py tests/test_token_radar_feature_builder.py tests/test_tradeability_scoring.py tests/test_event_price_observations.py tests/test_message_market_observation.py tests/test_token_target_social_timeline_service.py -q
```

Expected: pass.

- [ ] **Step 2: Run full backend tests**

Run:

```bash
uv run pytest
```

Expected: pass.

- [ ] **Step 3: Run lint and compile**

Run:

```bash
uv run ruff check .
uv run python -m compileall src tests
```

Expected: both pass.

- [ ] **Step 4: Run frontend tests**

Run:

```bash
cd web && npm test -- --runInBand
```

Expected: pass.

- [ ] **Step 5: Rebuild local projection and inspect audit**

Run:

```bash
uv run gmgn-twitter-intel asset-flow --window 5m --limit 20
uv run gmgn-twitter-intel ops audit-token-radar --window 5m --scope all --limit 100
```

Expected:

- `projection.version` is `token-radar-v5-auditable`.
- rows contain `tradeability`, not `price_health`.
- score blocks have contributions.
- social and first-snapshot price fields are populated when observations exist.
- stale or missing market rows are not `driver`.

- [ ] **Step 6: Commit verification fixes**

If previous steps required fixes:

```bash
git add src tests web
git commit -m "fix: complete auditable token radar verification"
```

If no fixes were needed, skip this commit.

## Self-Review

- Spec coverage: scoring hard cut, event price attribution, message quote worker, market baselines, timeline prices, token secondary page, market first-snapshot delta, and audit command are all mapped to tasks.
- Placeholder scan: this plan avoids deferred requirements and gives exact target files, test snippets, commands, and expected outputs.
- Type consistency: production score key is `tradeability` everywhere; `price_health` is removed from backend and frontend contract.
- Scope check: this is one cohesive production cutover because scoring, price ledger, projection, timeline, and frontend all depend on the same v5 row contract.
