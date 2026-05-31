# Event Anchor Capture Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-cut the old `price_observations(event_anchor/decision_latest)` runtime and replace it with append-only `market_ticks`, same-transaction `enriched_events`, token capture tiers, and explicit three-tier market capture.

**Architecture:** Provider frames and REST quotes become `market_ticks` facts. Event-time market state is no longer a later join worker: ingest resolves the target, finds or captures a tick outside any DB session, then commits `events` and `enriched_events` in one transaction. Token Radar and secondary read models consume `enriched_events JOIN market_ticks`; `LivePriceGateway` remains only as in-process publish/cache fanout and no longer writes market facts.

**Tech Stack:** Python, psycopg repository layer, Alembic/PostgreSQL, existing OKX CEX REST, existing OKX DEX WS, new OKX DEX REST quote adapter over `OkxDexClient.token_prices`, existing unified worker runtime.

---

## Status

**Status**: Draft  
**Date**: 2026-05-15  
**Owning spec**: `docs/superpowers/specs/active/2026-05-15-event-anchor-capture-redesign-cn.md`  
**Worktree**: `.worktrees/event-anchor-capture-redesign/`  
**Branch**: `codex/event-anchor-capture-redesign`

## Pre-flight

- [ ] Read `docs/superpowers/specs/active/2026-05-15-event-anchor-capture-redesign-cn.md`.
- [ ] Create worktree from current `main`.

```bash
git fetch origin
git worktree add .worktrees/event-anchor-capture-redesign -b codex/event-anchor-capture-redesign origin/main
cd .worktrees/event-anchor-capture-redesign
git branch --show-current
```

Expected branch output:

```text
codex/event-anchor-capture-redesign
```

- [ ] Capture baseline state.

```bash
uv run ruff check .
uv run pytest
uv run parallax --help > docs/generated/cli-help.md
```

Expected: baseline either passes, or failures are copied into the verification notes before implementation starts.

## Spec And Main Branch Analysis

### What the spec changes

- `price_observations(event_anchor)` is not a fact. It is a later join result written by `AnchorPriceWorker`, so it cannot prove event-time price capture.
- `price_observations(decision_latest)` is also not the new durable market history. Market state should be represented by raw-ish provider ticks in `market_ticks`.
- `AnchorPriceWorker`, `anchor_price` settings, `pending_anchor_price_query`, `anchor_price_observation`, and the `PriceObservationRepository` runtime must be removed, not wrapped.
- Event ingest must produce `enriched_events` for resolved token events in the same transaction as `events`.
- Market capture has exactly three acquisition paths:
  - Tier 1: OKX DEX WS frames written by `MarketTickStreamWorker`.
  - Tier 2: batch polling written by `MarketTickPollWorker`.
  - Tier 3: ingest inline quote pull after deterministic resolution when no recent tick exists.
- Provider IO must stay outside DB sessions.
- New wake channel is `market_tick_written`; old `market_observation_written` disappears.
- Frontend is out of scope. Public HTTP/WS payloads may keep the existing `market.event_anchor` / `market.decision_latest` JSON keys as an API shape adapter, but those keys must be generated from `enriched_events` and `market_ticks`; there is no old-table fallback.

### Current main branch conflicts

- Worker registry still registers old workers:
  - `src/parallax/app/runtime/worker_registry.py:3-24` includes `anchor_price` and `live_price_gateway`.
  - `src/parallax/app/runtime/worker_registry.py:28-41` assigns old priorities.
- Runtime bootstrap wires old provider paths:
  - `src/parallax/app/runtime/bootstrap.py:25-27` imports `AnchorPriceWorker` and `LivePriceGateway`.
  - `src/parallax/app/runtime/bootstrap.py:321-330` constructs `anchor_price`.
  - `src/parallax/app/runtime/bootstrap.py:350-361` constructs `live_price_gateway` with persistence knobs.
  - `src/parallax/app/runtime/bootstrap.py:405-424` runs the entire ingest flow inside one `worker_session("collector")`.
- Settings still expose old runtime config:
  - `src/parallax/platform/config/settings.py:369-372` defines `AnchorPriceWorkerSettings`.
  - `src/parallax/platform/config/settings.py:375-385` defines persistence-oriented `LivePriceGatewayWorkerSettings`.
  - `src/parallax/platform/config/settings.py:498-517` adds `anchor_price` and old `live_price_gateway` under `WorkersSettings`.
  - `src/parallax/platform/config/settings.py:929-970` emits old YAML keys.
- Old anchor code is present:
  - `src/parallax/domains/asset_market/runtime/anchor_price_worker.py`.
  - `src/parallax/domains/asset_market/services/anchor_price_observation.py`.
  - `src/parallax/domains/asset_market/queries/pending_anchor_price_query.py`.
- Old repository is mutable and table-centered:
  - `src/parallax/domains/asset_market/repositories/price_observation_repository.py:76-133` accepts old enum values.
  - `src/parallax/domains/asset_market/repositories/price_observation_repository.py:398-450` updates an old row, which violates the append-only requirement.
- `LivePriceGateway` persists material observations:
  - `src/parallax/domains/asset_market/runtime/live_price_gateway.py:362-422` writes `price_observations` and notifies `market_observation_written`.
- Radar and secondary read models still read `price_observations`:
  - `src/parallax/domains/token_intel/queries/token_radar_source_query.py:80-153`.
  - `src/parallax/domains/token_intel/repositories/token_target_repository.py:217-226`.
  - `src/parallax/domains/token_intel/services/token_factor_evaluation.py:124-132`.
  - `src/parallax/domains/account_quality/repositories/account_quality_repository.py:289-310`.
- There is literal drift already:
  - `pending_anchor_price_query.py` and `token_target_repository.py` still mention `message_anchor` while the table now uses `event_anchor`.

### Existing useful pieces

- `DBPoolBundle.worker_session(name)`, `wake_emitter()`, and `wake_listener()` already exist and should be reused.
- `TokenIntentResolver.resolve(evidence_inputs, persist=False)` already exists and supports a split ingest flow.
- `OkxDexClient.token_prices(chain_index, token_contract_addresses)` exists and can back a real OKX DEX REST quote provider.
- `providers.py` already has market quote types (`DexQuote`, `CexTicker`, capabilities) that can be extended without introducing a new external provider.
- `AssetMarketProviders.stream_dex_market` already exposes OKX DEX WS, but its subscription limit is currently tied to `live_price_gateway`; that setting moves to `market_tick_stream`.

## Hard-Cut Rules

- [ ] Do not keep runtime fallback reads from `price_observations`.
- [ ] Do not double-write to `price_observations`.
- [ ] Do not keep `AnchorPriceWorker`, `AnchorPriceWorkerSettings`, or `anchor_price` YAML keys.
- [ ] Do not keep `market_observation_written`.
- [ ] Do not keep `event_anchor` or `decision_latest` as DB enum literals or table concepts.
- [ ] Do not migrate old `price_observations` rows into `market_ticks`; the spec classifies those rows as flawed join output.
- [ ] Keep only historical Alembic migrations, specs, plans, and verification docs as places where old names may appear.

Allowed public adapter:

- Existing API JSON may continue to expose `market.event_anchor` and `market.decision_latest` keys for frontend stability during this backend-only change.
- That adapter must be implemented by `enriched_events` and `market_ticks` reads only.
- The adapter is not compatibility code because it does not read old tables, start old workers, or preserve old DB semantics.

## Target File Map

### Create

- `src/parallax/platform/db/alembic/versions/20260515_0046_event_anchor_capture_redesign.py` — hard-cut DB migration.
- `src/parallax/domains/asset_market/types/market_tick.py` — typed tick/capture records and validators.
- `src/parallax/domains/asset_market/repositories/market_tick_repository.py` — append-only tick writes and tick lookups.
- `src/parallax/domains/asset_market/repositories/enriched_event_repository.py` — append-only enriched event writes and reads.
- `src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py` — capture tier projection.
- `src/parallax/domains/asset_market/services/event_market_capture.py` — pure orchestration for Tier 1/2 lookup and Tier 3 inline pull.
- `src/parallax/domains/asset_market/providers/okx_dex_quote_provider.py` — OKX DEX REST adapter around `OkxDexClient.token_prices`.
- `src/parallax/domains/asset_market/runtime/market_tick_stream_worker.py` — Tier 1 stream writer.
- `src/parallax/domains/asset_market/runtime/market_tick_poll_worker.py` — Tier 2 batch poll writer.
- `src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py` — capture tier projection writer.
- `tests/unit/test_market_tick_repository.py`.
- `tests/unit/test_enriched_event_repository.py`.
- `tests/unit/test_event_market_capture.py`.
- `tests/unit/test_market_tick_stream_worker.py`.
- `tests/unit/test_market_tick_poll_worker.py`.
- `tests/unit/test_token_capture_tier_worker.py`.
- `tests/architecture/test_event_anchor_capture_redesign_contracts.py`.

### Modify

- `src/parallax/domains/asset_market/interfaces.py` — replace `price_observations` repo with new repositories.
- `src/parallax/app/runtime/bootstrap.py` — split ingest session boundaries, wire new services/workers/providers.
- `src/parallax/app/runtime/worker_registry.py` — replace old worker list.
- `src/parallax/platform/config/settings.py` — remove old settings and add `market_tick_stream`, `market_tick_poll`, `token_capture_tier`.
- `src/parallax/app/providers_wiring.py` — wire OKX DEX quote provider and move stream settings.
- `src/parallax/domains/evidence/services/ingest_service.py` — split prepare/commit stages so provider IO is outside DB sessions.
- `src/parallax/domains/asset_market/runtime/live_price_gateway.py` — remove persistence and make it cache/publish only.
- `src/parallax/domains/token_intel/queries/token_radar_source_query.py` — read `enriched_events` and `market_ticks`.
- `src/parallax/domains/token_intel/services/token_radar_projection.py` — build market context from new rows.
- `src/parallax/domains/token_intel/scoring/factor_snapshot.py` — keep API shape but source fields from new market context.
- `src/parallax/domains/token_intel/repositories/token_target_repository.py` — remove old observation joins.
- `src/parallax/domains/token_intel/services/token_factor_evaluation.py` — use tick repository for before/between reads.
- `src/parallax/domains/account_quality/repositories/account_quality_repository.py` — use ticks.
- `src/parallax/app/surfaces/cli/main.py` — rename audit source max field to tick-based source.
- `docs/ARCHITECTURE.md`, `docs/RELIABILITY.md`, `docs/WORKERS.md`, `docs/CONTRACTS.md`, `docs/generated/cli-help.md`, and domain architecture docs.

### Delete

- `src/parallax/domains/asset_market/runtime/anchor_price_worker.py`.
- `src/parallax/domains/asset_market/services/anchor_price_observation.py`.
- `src/parallax/domains/asset_market/queries/pending_anchor_price_query.py`.
- `src/parallax/domains/asset_market/repositories/price_observation_repository.py`.
- `src/parallax/domains/asset_market/services/live_observation_policy.py`.
- `tests/unit/test_anchor_price_observation.py`.
- `tests/unit/test_price_observation_repository.py`.
- `tests/unit/test_price_observation_repository_policy.py`.
- `tests/unit/test_price_observation_read_models.py` if still present under that path.
- `tests/unit/test_live_observation_policy.py`.
- `tests/benchmark/test_live_observation_write_budget.py`.

## Storage Contract

Create revision `20260515_0046_event_anchor_capture_redesign.py` with `down_revision = "20260514_0045"`.

```sql
CREATE TABLE IF NOT EXISTS market_ticks (
  tick_id TEXT PRIMARY KEY,
  target_type TEXT NOT NULL CHECK (target_type IN ('chain_token', 'cex_symbol')),
  target_id TEXT NOT NULL,
  chain TEXT,
  token_address TEXT,
  exchange TEXT,
  instrument TEXT,
  pricefeed_id TEXT REFERENCES price_feeds(pricefeed_id) ON DELETE SET NULL,
  source_tier TEXT NOT NULL CHECK (source_tier IN ('tier1_ws', 'tier2_poll', 'tier3_inline')),
  source_provider TEXT NOT NULL CHECK (source_provider IN ('okx_dex_ws', 'okx_dex_rest', 'okx_cex_rest')),
  observed_at_ms BIGINT NOT NULL,
  received_at_ms BIGINT NOT NULL,
  price_usd NUMERIC NOT NULL CHECK (price_usd > 0),
  liquidity_usd NUMERIC,
  volume_24h_usd NUMERIC,
  market_cap_usd NUMERIC,
  raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at_ms BIGINT NOT NULL,
  CHECK (
    (
      target_type = 'chain_token'
      AND chain IS NOT NULL
      AND token_address IS NOT NULL
      AND exchange IS NULL
      AND instrument IS NULL
    )
    OR (
      target_type = 'cex_symbol'
      AND exchange IS NOT NULL
      AND instrument IS NOT NULL
      AND chain IS NULL
      AND token_address IS NULL
    )
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_ticks_dedupe
  ON market_ticks(target_type, target_id, source_provider, observed_at_ms);

CREATE INDEX IF NOT EXISTS idx_market_ticks_target_observed
  ON market_ticks(target_type, target_id, observed_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_market_ticks_received
  ON market_ticks(received_at_ms DESC);

CREATE TABLE IF NOT EXISTS token_capture_tier (
  target_type TEXT NOT NULL CHECK (target_type IN ('chain_token', 'cex_symbol')),
  target_id TEXT NOT NULL,
  tier INTEGER NOT NULL CHECK (tier IN (1, 2, 3)),
  reason TEXT NOT NULL CHECK (reason IN ('ws_subscribed', 'batch_poll', 'inline_only')),
  score NUMERIC NOT NULL DEFAULT 0,
  updated_at_ms BIGINT NOT NULL,
  PRIMARY KEY(target_type, target_id)
);

CREATE TABLE IF NOT EXISTS enriched_events (
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  intent_id TEXT NOT NULL REFERENCES token_intents(intent_id) ON DELETE CASCADE,
  resolution_id TEXT NOT NULL REFERENCES token_intent_resolutions(resolution_id) ON DELETE CASCADE,
  target_type TEXT NOT NULL CHECK (target_type IN ('chain_token', 'cex_symbol')),
  target_id TEXT NOT NULL,
  t_event_ms BIGINT NOT NULL,
  tick_id TEXT REFERENCES market_ticks(tick_id) ON DELETE RESTRICT,
  tick_lag_ms BIGINT,
  capture_method TEXT NOT NULL CHECK (capture_method IN ('tier1_ws', 'tier2_poll', 'tier3_inline', 'unavailable')),
  capture_reason TEXT NOT NULL,
  created_at_ms BIGINT NOT NULL,
  CHECK (
    (
      capture_method = 'unavailable'
      AND tick_id IS NULL
      AND tick_lag_ms IS NULL
    )
    OR (
      capture_method <> 'unavailable'
      AND tick_id IS NOT NULL
      AND tick_lag_ms IS NOT NULL
      AND tick_lag_ms >= 0
    )
  ),
  PRIMARY KEY(event_id, intent_id)
);

CREATE INDEX IF NOT EXISTS idx_enriched_events_event
  ON enriched_events(event_id);

CREATE INDEX IF NOT EXISTS idx_enriched_events_target_time
  ON enriched_events(target_type, target_id, t_event_ms DESC);

CREATE INDEX IF NOT EXISTS idx_enriched_events_tick
  ON enriched_events(tick_id);
```

Append-only trigger:

```sql
CREATE OR REPLACE FUNCTION forbid_market_fact_update()
RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_market_ticks_no_update
  BEFORE UPDATE ON market_ticks
  FOR EACH ROW EXECUTE FUNCTION forbid_market_fact_update();

CREATE TRIGGER trg_enriched_events_no_update
  BEFORE UPDATE ON enriched_events
  FOR EACH ROW EXECUTE FUNCTION forbid_market_fact_update();
```

Hard-cut removal:

```sql
DROP TABLE IF EXISTS price_observations CASCADE;
```

The downgrade may recreate empty table shells for local developer rollback, but it must not be described as production rollback and must not restore runtime code paths.

## Implementation Tasks

### Task 1: Add architecture contract tests first

**Files:**
- Create: `tests/architecture/test_event_anchor_capture_redesign_contracts.py`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`

- [ ] Add a failing architecture test that bans old runtime names outside historical docs and migrations.

```python
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ALLOWED_OLD_NAME_PATH_PARTS = (
    "platform/db/alembic/versions/20260513_0036_token_radar_kappa_cqrs_hard_cut.py",
    "docs/superpowers/specs/active/2026-05-15-event-anchor-capture-redesign-cn.md",
    "docs/superpowers/plans/active/2026-05-15-event-anchor-capture-redesign-plan-cn.md",
)


def _project_text_files() -> list[Path]:
    paths: list[Path] = []
    for path in ROOT.rglob("*"):
        if path.is_dir():
            continue
        if any(part in {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache"} for part in path.parts):
            continue
        if path.suffix in {".py", ".md", ".yaml", ".yml", ".toml", ".sql"}:
            paths.append(path)
    return paths


def _is_allowed_old_reference(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return any(part in rel for part in ALLOWED_OLD_NAME_PATH_PARTS)


def test_old_price_observation_runtime_is_removed() -> None:
    banned = (
        "AnchorPriceWorker",
        "anchor_price",
        "price_observations",
        "market_observation_written",
        "message_anchor",
        "decision_latest",
        "should_persist_live_observation",
    )
    offenders: list[str] = []
    for path in _project_text_files():
        if _is_allowed_old_reference(path):
            continue
        text = path.read_text(encoding="utf-8")
        for needle in banned:
            if needle in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {needle}")
    assert offenders == []
```

- [ ] Add append-only SQL guard tests for the new migration file.

```python
def test_market_tick_tables_are_append_only_in_latest_migration() -> None:
    migration = ROOT / "src/parallax/platform/db/alembic/versions/20260515_0046_event_anchor_capture_redesign.py"
    text = migration.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS market_ticks" in text
    assert "CREATE TABLE IF NOT EXISTS enriched_events" in text
    assert "BEFORE UPDATE ON market_ticks" in text
    assert "BEFORE UPDATE ON enriched_events" in text
    assert "DROP TABLE IF EXISTS price_observations CASCADE" in text
    assert "UPDATE market_ticks" not in text
    assert "UPDATE enriched_events" not in text
```

- [ ] Update `tests/architecture/test_worker_runtime_contracts.py` expected worker names.

Expected canonical set:

```python
{
    "collector",
    "market_tick_stream",
    "market_tick_poll",
    "token_capture_tier",
    "live_price_gateway",
    "resolution_refresh",
    "asset_profile_refresh",
    "token_radar_projection",
    "pulse_candidate",
    "enrichment",
    "handle_summary",
    "harness_ops",
    "notification_rule",
    "notification_delivery",
}
```

- [ ] Run the architecture tests and confirm failure on current main.

```bash
uv run pytest tests/architecture/test_event_anchor_capture_redesign_contracts.py tests/architecture/test_worker_runtime_contracts.py -q
```

Expected: failures cite old names and missing migration.

- [ ] Commit the failing tests.

```bash
git add tests/architecture/test_event_anchor_capture_redesign_contracts.py tests/architecture/test_worker_runtime_contracts.py
git commit -m "test: lock event anchor capture hard cut contracts"
```

### Task 2: Create migration and new market fact types

**Files:**
- Create: `src/parallax/platform/db/alembic/versions/20260515_0046_event_anchor_capture_redesign.py`
- Create: `src/parallax/domains/asset_market/types/market_tick.py`
- Modify: `tests/unit/test_postgres_schema.py`
- Modify: `tests/integration/test_postgres_schema_runtime.py`

- [ ] Add schema tests asserting new tables and absence of `price_observations`.

```python
def test_market_tick_capture_schema(sql_text: str) -> None:
    assert "CREATE TABLE IF NOT EXISTS market_ticks" in sql_text
    assert "CREATE TABLE IF NOT EXISTS enriched_events" in sql_text
    assert "CREATE TABLE IF NOT EXISTS token_capture_tier" in sql_text
    assert "DROP TABLE IF EXISTS price_observations CASCADE" in sql_text
    assert "BEFORE UPDATE ON market_ticks" in sql_text
    assert "BEFORE UPDATE ON enriched_events" in sql_text
```

Runtime integration assertion:

```python
assert {"market_ticks", "enriched_events", "token_capture_tier"}.issubset(table_names)
assert "price_observations" not in table_names
```

- [ ] Create the Alembic revision with the SQL from the Storage Contract section.

Required header:

```python
"""event anchor capture redesign

Revision ID: 20260515_0046
Revises: 20260514_0045
Create Date: 2026-05-15
"""

from __future__ import annotations

from alembic import op

revision = "20260515_0046"
down_revision = "20260514_0045"
branch_labels = None
depends_on = None
```

Upgrade must execute the complete SQL shown in the Storage Contract section in this order:

```python
def upgrade() -> None:
    op.execute(MARKET_TICKS_SQL)
    op.execute(MARKET_TICKS_DEDUPE_INDEX_SQL)
    op.execute(MARKET_TICKS_TARGET_INDEX_SQL)
    op.execute(MARKET_TICKS_RECEIVED_INDEX_SQL)
    op.execute(TOKEN_CAPTURE_TIER_SQL)
    op.execute(ENRICHED_EVENTS_SQL)
    op.execute(ENRICHED_EVENTS_EVENT_INDEX_SQL)
    op.execute(ENRICHED_EVENTS_TARGET_INDEX_SQL)
    op.execute(ENRICHED_EVENTS_TICK_INDEX_SQL)
    op.execute(FORBID_MARKET_FACT_UPDATE_FUNCTION_SQL)
    op.execute(MARKET_TICKS_NO_UPDATE_TRIGGER_SQL)
    op.execute(ENRICHED_EVENTS_NO_UPDATE_TRIGGER_SQL)
    op.execute("DROP TABLE IF EXISTS price_observations CASCADE")
```

Downgrade must drop new objects and recreate only an empty developer rollback shell if required by local test harness:

```python
def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS enriched_events")
    op.execute("DROP TABLE IF EXISTS token_capture_tier")
    op.execute("DROP TABLE IF EXISTS market_ticks")
    op.execute("DROP FUNCTION IF EXISTS forbid_market_fact_update()")
```

- [ ] Create `market_tick.py` with closed literals.

```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

MarketTickTargetType = Literal["chain_token", "cex_symbol"]
MarketTickSourceTier = Literal["tier1_ws", "tier2_poll", "tier3_inline"]
MarketTickSourceProvider = Literal["okx_dex_ws", "okx_dex_rest", "okx_cex_rest"]
EventCaptureMethod = Literal["tier1_ws", "tier2_poll", "tier3_inline", "unavailable"]


@dataclass(frozen=True, slots=True)
class MarketTick:
    tick_id: str
    target_type: MarketTickTargetType
    target_id: str
    chain: str | None
    token_address: str | None
    exchange: str | None
    instrument: str | None
    pricefeed_id: str | None
    source_tier: MarketTickSourceTier
    source_provider: MarketTickSourceProvider
    observed_at_ms: int
    received_at_ms: int
    price_usd: Decimal
    liquidity_usd: Decimal | None
    volume_24h_usd: Decimal | None
    market_cap_usd: Decimal | None
    raw_payload_json: dict[str, Any]
    created_at_ms: int


@dataclass(frozen=True, slots=True)
class EnrichedEventCapture:
    event_id: str
    intent_id: str
    resolution_id: str
    target_type: MarketTickTargetType
    target_id: str
    t_event_ms: int
    tick_id: str | None
    tick_lag_ms: int | None
    capture_method: EventCaptureMethod
    capture_reason: str
    created_at_ms: int
```

- [ ] Run schema tests.

```bash
uv run pytest tests/unit/test_postgres_schema.py tests/integration/test_postgres_schema_runtime.py -q
```

Expected: pass after migration code exists.

- [ ] Commit.

```bash
git add src/parallax/platform/db/alembic/versions/20260515_0046_event_anchor_capture_redesign.py src/parallax/domains/asset_market/types/market_tick.py tests/unit/test_postgres_schema.py tests/integration/test_postgres_schema_runtime.py
git commit -m "feat: add market tick capture schema"
```

### Task 3: Replace price observation repository with append-only repositories

**Files:**
- Delete: `src/parallax/domains/asset_market/repositories/price_observation_repository.py`
- Create: `src/parallax/domains/asset_market/repositories/market_tick_repository.py`
- Create: `src/parallax/domains/asset_market/repositories/enriched_event_repository.py`
- Create: `src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py`
- Modify: `src/parallax/domains/asset_market/interfaces.py`
- Test: `tests/unit/test_market_tick_repository.py`
- Test: `tests/unit/test_enriched_event_repository.py`

- [ ] Write repository tests for idempotent insert without update.

```python
def test_insert_market_tick_is_idempotent_without_update(fake_conn) -> None:
    repo = MarketTickRepository(fake_conn)
    tick = _tick(tick_id="tick-1", observed_at_ms=1_778_000_000_000, price_usd=Decimal("1.23"))

    repo.insert_tick(tick)
    repo.insert_tick(tick)

    assert "ON CONFLICT(target_type, target_id, source_provider, observed_at_ms) DO NOTHING" in fake_conn.sql
    assert "UPDATE market_ticks" not in fake_conn.sql
```

```python
def test_insert_enriched_event_is_append_only(fake_conn) -> None:
    repo = EnrichedEventRepository(fake_conn)
    repo.insert_capture(_capture(event_id="event-1", tick_id="tick-1", capture_method="tier3_inline"))

    assert "INSERT INTO enriched_events" in fake_conn.sql
    assert "ON CONFLICT(event_id, intent_id) DO NOTHING" in fake_conn.sql
    assert "UPDATE enriched_events" not in fake_conn.sql
```

- [ ] Implement `MarketTickRepository`.

Required methods:

```python
class MarketTickRepository:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def insert_tick(self, tick: MarketTick) -> str:
        """Insert one append-only tick. Return tick.tick_id even when deduped."""
        self._conn.execute(INSERT_MARKET_TICK_SQL, _tick_params(tick))
        return tick.tick_id

    def insert_ticks(self, ticks: Iterable[MarketTick]) -> int:
        """Insert many ticks and return attempted insert count."""
        attempted = 0
        for tick in ticks:
            self.insert_tick(tick)
            attempted += 1
        return attempted

    def latest_at_or_before(
        self,
        *,
        target_type: str,
        target_id: str,
        at_ms: int,
        max_lag_ms: int,
    ) -> dict[str, Any] | None:
        return self._fetch_one(LATEST_AT_OR_BEFORE_SQL, {
            "target_type": target_type,
            "target_id": target_id,
            "at_ms": at_ms,
            "min_observed_at_ms": at_ms - max_lag_ms,
        })

    def latest_for_target(
        self,
        *,
        target_type: str,
        target_id: str,
        max_age_ms: int,
        now_ms: int,
    ) -> dict[str, Any] | None:
        return self._fetch_one(LATEST_FOR_TARGET_SQL, {
            "target_type": target_type,
            "target_id": target_id,
            "min_received_at_ms": now_ms - max_age_ms,
        })

    def first_between(
        self,
        *,
        target_type: str,
        target_id: str,
        start_ms: int,
        end_ms: int,
    ) -> dict[str, Any] | None:
        return self._fetch_one(FIRST_BETWEEN_SQL, {
            "target_type": target_type,
            "target_id": target_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
        })
```

Insert SQL:

```sql
INSERT INTO market_ticks(
  tick_id, target_type, target_id, chain, token_address, exchange, instrument,
  pricefeed_id, source_tier, source_provider, observed_at_ms, received_at_ms,
  price_usd, liquidity_usd, volume_24h_usd, market_cap_usd, raw_payload_json,
  created_at_ms
) VALUES (
  %(tick_id)s, %(target_type)s, %(target_id)s, %(chain)s, %(token_address)s,
  %(exchange)s, %(instrument)s, %(pricefeed_id)s, %(source_tier)s,
  %(source_provider)s, %(observed_at_ms)s, %(received_at_ms)s, %(price_usd)s,
  %(liquidity_usd)s, %(volume_24h_usd)s, %(market_cap_usd)s,
  %(raw_payload_json)s, %(created_at_ms)s
)
ON CONFLICT(target_type, target_id, source_provider, observed_at_ms) DO NOTHING
```

- [ ] Implement `EnrichedEventRepository`.

Required methods:

```python
class EnrichedEventRepository:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def insert_capture(self, capture: EnrichedEventCapture) -> None:
        self._conn.execute(INSERT_ENRICHED_EVENT_SQL, _capture_params(capture))

    def list_by_event_id(self, event_id: str) -> list[dict[str, Any]]:
        return self._fetch_all(LIST_BY_EVENT_ID_SQL, {"event_id": event_id})

    def by_event_intent(self, *, event_id: str, intent_id: str) -> dict[str, Any] | None:
        return self._fetch_one(BY_EVENT_INTENT_SQL, {"event_id": event_id, "intent_id": intent_id})

    def latest_for_target(self, *, target_type: str, target_id: str, limit: int) -> list[dict[str, Any]]:
        return self._fetch_all(LATEST_FOR_TARGET_SQL, {
            "target_type": target_type,
            "target_id": target_id,
            "limit": limit,
        })
```

- [ ] Implement `TokenCaptureTierRepository`.

Required methods:

```python
class TokenCaptureTierRepository:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def upsert_tier(
        self,
        *,
        target_type: str,
        target_id: str,
        tier: int,
        reason: str,
        score: Decimal,
        updated_at_ms: int,
    ) -> None:
        self._conn.execute(UPSERT_TOKEN_CAPTURE_TIER_SQL, {
            "target_type": target_type,
            "target_id": target_id,
            "tier": tier,
            "reason": reason,
            "score": score,
            "updated_at_ms": updated_at_ms,
        })

    def list_by_tier(self, *, tier: int, limit: int) -> list[dict[str, Any]]:
        return self._fetch_all(LIST_BY_TIER_SQL, {"tier": tier, "limit": limit})

    def get(self, *, target_type: str, target_id: str) -> dict[str, Any] | None:
        return self._fetch_one(GET_TIER_SQL, {"target_type": target_type, "target_id": target_id})
```

`token_capture_tier` is a projection, so this exact upsert shape is allowed here:

```sql
ON CONFLICT(target_type, target_id) DO UPDATE SET
  tier = excluded.tier,
  reason = excluded.reason,
  score = excluded.score,
  updated_at_ms = excluded.updated_at_ms
```

- [ ] Modify `RepositorySession` in `interfaces.py`.

Replace:

```python
price_observations: PriceObservationRepository
```

With:

```python
market_ticks: MarketTickRepository
enriched_events: EnrichedEventRepository
token_capture_tiers: TokenCaptureTierRepository
```

- [ ] Run repository tests.

```bash
uv run pytest tests/unit/test_market_tick_repository.py tests/unit/test_enriched_event_repository.py -q
```

- [ ] Commit.

```bash
git add src/parallax/domains/asset_market/repositories src/parallax/domains/asset_market/interfaces.py tests/unit/test_market_tick_repository.py tests/unit/test_enriched_event_repository.py
git rm src/parallax/domains/asset_market/repositories/price_observation_repository.py
git commit -m "feat: replace price observation repository with market tick facts"
```

### Task 4: Add OKX DEX REST quote provider and provider wiring

**Files:**
- Create: `src/parallax/domains/asset_market/providers/okx_dex_quote_provider.py`
- Modify: `src/parallax/app/providers_wiring.py`
- Modify: `src/parallax/domains/asset_market/providers.py`
- Test: `tests/unit/test_okx_dex_quote_provider.py`

- [ ] Write provider adapter tests.

```python
def test_okx_dex_quote_provider_maps_token_prices_to_dex_quote() -> None:
    client = FakeOkxDexClient(
        token_prices=[
            OkxDexTokenPrice(
                chain_index="501",
                token_contract_address="So11111111111111111111111111111111111111112",
                price="142.12",
                time="1778000000000",
                market_cap="1000000000",
            )
        ]
    )
    provider = OkxDexQuoteProvider(client)

    quote = provider.quote_token(chain="solana", token_address="So11111111111111111111111111111111111111112")

    assert quote is not None
    assert quote.price_usd == Decimal("142.12")
    assert quote.provider == "okx_dex_rest"
    assert quote.observed_at_ms == 1_778_000_000_000
```

- [ ] Implement `OkxDexQuoteProvider`.

Required shape:

```python
class OkxDexQuoteProvider:
    provider = "okx_dex_rest"

    def __init__(self, client: OkxDexClient) -> None:
        self._client = client

    def quote_token(self, *, chain: str, token_address: str) -> DexQuote | None:
        chain_index = okx_chain_index(chain)
        prices = self._client.token_prices(chain_index=chain_index, token_contract_addresses=[token_address])
        if not prices:
            return None
        row = prices[0]
        return DexQuote(
            provider=self.provider,
            chain=chain,
            token_address=token_address,
            price_usd=Decimal(row.price),
            liquidity_usd=None,
            volume_24h_usd=None,
            market_cap_usd=Decimal(row.market_cap) if row.market_cap else None,
            observed_at_ms=int(row.time),
            raw_payload=row.raw_payload,
        )
```

- [ ] Wire provider bundle so `AssetMarketProviders.dex_quote_market` is OKX-backed for capture.

`providers_wiring.py` changes:

```python
providers = AssetMarketProviders(
    sync_cex_market=okx_sync_cex_market,
    message_cex_market=okx_message_cex_market,
    dex_discovery_market=okx_dex_discovery_market,
    dex_quote_market=okx_dex_quote_provider,
    dex_candle_market=gmgn_dex_candle_market,
    dex_profile_market=gmgn_dex_profile_market,
    stream_dex_market=okx_dex_ws_market,
    discovery_chain_ids=settings.providers.okx.dex_discovery_chain_ids,
    provider_health=tuple(provider_health),
)
```

- [ ] Move OKX DEX WS subscription limit from `settings.workers.live_price_gateway.subscription_limit` to `settings.workers.market_tick_stream.subscription_limit`.

- [ ] Run provider tests.

```bash
uv run pytest tests/unit/test_okx_dex_quote_provider.py -q
```

- [ ] Commit.

```bash
git add src/parallax/domains/asset_market/providers.py src/parallax/domains/asset_market/providers/okx_dex_quote_provider.py src/parallax/app/providers_wiring.py tests/unit/test_okx_dex_quote_provider.py
git commit -m "feat: add okx dex quote provider for tick capture"
```

### Task 5: Implement event market capture service with DB-free provider IO

**Files:**
- Create: `src/parallax/domains/asset_market/services/event_market_capture.py`
- Test: `tests/unit/test_event_market_capture.py`

- [ ] Write tests for lookup hit, inline pull success, and unavailable capture.

```python
def test_capture_uses_existing_recent_tick_without_provider_io() -> None:
    ticks = FakeTickLookup(latest={"tick_id": "tick-1", "observed_at_ms": 1_778_000_000_000})
    providers = FailingProviders()
    capture = EventMarketCaptureService(providers=providers, now_ms=lambda: 1_778_000_000_500)

    result = capture.capture_for_event(
        resolution=_resolution(target_type="chain_token", target_id="solana:abc"),
        event_ms=1_778_000_000_100,
        tick_lookup=ticks,
    )

    assert result.tick.tick_id == "tick-1"
    assert result.capture.capture_method == "tier1_ws"
    assert providers.calls == []
```

```python
def test_capture_inline_pull_writes_tick_when_lookup_misses() -> None:
    ticks = FakeTickLookup(latest=None)
    providers = ProvidersReturningDexQuote(price=Decimal("0.42"))
    capture = EventMarketCaptureService(providers=providers, now_ms=lambda: 1_778_000_001_000)

    result = capture.capture_for_event(
        resolution=_resolution(target_type="chain_token", target_id="solana:abc"),
        event_ms=1_778_000_000_000,
        tick_lookup=ticks,
    )

    assert result.tick is not None
    assert result.tick.source_tier == "tier3_inline"
    assert result.tick.source_provider == "okx_dex_rest"
    assert result.capture.capture_method == "tier3_inline"
```

```python
def test_capture_unavailable_has_reason_and_no_tick() -> None:
    ticks = FakeTickLookup(latest=None)
    providers = ProvidersReturningNone()
    capture = EventMarketCaptureService(providers=providers, now_ms=lambda: 1_778_000_001_000)

    result = capture.capture_for_event(
        resolution=_resolution(target_type="cex_symbol", target_id="okx:PEPE-USDT"),
        event_ms=1_778_000_000_000,
        tick_lookup=ticks,
    )

    assert result.tick is None
    assert result.capture.capture_method == "unavailable"
    assert result.capture.capture_reason == "provider_no_quote"
```

- [ ] Implement service as a pure orchestrator.

Required dataclasses and signatures:

```python
@dataclass(frozen=True, slots=True)
class TickLookup:
    latest_at_or_before: Callable[[str, str, int, int], dict[str, Any] | None]


@dataclass(frozen=True, slots=True)
class CaptureResult:
    tick: MarketTick | None
    capture: EnrichedEventCapture


class EventMarketCaptureService:
    def __init__(
        self,
        *,
        providers: AssetMarketProviders,
        now_ms: Callable[[], int],
        max_existing_tick_lag_ms: int = 60_000,
    ) -> None:
        self._providers = providers
        self._now_ms = now_ms
        self._max_existing_tick_lag_ms = max_existing_tick_lag_ms

    def capture_for_event(
        self,
        *,
        event_id: str,
        intent_id: str,
        resolution_id: str,
        resolution: Mapping[str, Any],
        event_ms: int,
        tick_lookup: TickLookup,
    ) -> CaptureResult:
        target_type = str(resolution["target_type"])
        target_id = str(resolution["target_id"])
        existing = tick_lookup.latest_at_or_before(
            target_type,
            target_id,
            event_ms,
            self._max_existing_tick_lag_ms,
        )
        if existing:
            return _capture_from_existing_tick(existing, event_ms)
        return self._capture_inline(
            event_id=event_id,
            intent_id=intent_id,
            resolution_id=resolution_id,
            resolution=resolution,
            event_ms=event_ms,
        )
```

Rules inside `capture_for_event`:

- Query `tick_lookup.latest_at_or_before(target_type, target_id, event_ms, max_existing_tick_lag_ms)`.
- If hit, return `capture_method` equal to the hit row `source_tier` and no new tick.
- If miss and target is `chain_token`, call `providers.dex_quote_market.token_quotes([DexTokenQuoteRequest(chain_id=chain_id, address=token_address)])` outside DB session.
- If miss and target is `cex_symbol`, call `providers.message_cex_market.ticker(inst_id=instrument)` outside DB session.
- Convert provider quote to `MarketTick(source_tier="tier3_inline")`.
- If provider returns no quote or raises a recoverable provider error, return `capture_method="unavailable"` with a short reason.
- Do not import repository classes into this service.
- Do not open DB connections in this service.

- [ ] Run service tests.

```bash
uv run pytest tests/unit/test_event_market_capture.py -q
```

- [ ] Commit.

```bash
git add src/parallax/domains/asset_market/services/event_market_capture.py tests/unit/test_event_market_capture.py
git commit -m "feat: add DB-free event market capture service"
```

### Task 6: Split ingest into prepare, outside-DB capture, and same-transaction commit

**Files:**
- Modify: `src/parallax/domains/evidence/services/ingest_service.py`
- Modify: `src/parallax/app/runtime/bootstrap.py`
- Test: `tests/unit/test_ingest_event_market_capture.py`
- Test: `tests/integration/test_ingest_enriched_events.py`

- [ ] Write an ingest unit test proving provider IO is outside `worker_session`.

Test approach: use a fake pool bundle whose session object toggles `in_session=True`, and a fake provider that asserts `in_session` is false when called.

```python
def test_inline_market_capture_runs_outside_worker_session() -> None:
    state = SessionState()
    pool_bundle = FakeDBPoolBundle(state)
    provider = AssertingProvider(lambda: state.in_session is False)
    store = _PooledIngestStore(pool_bundle=pool_bundle, providers=provider, settings=_settings())

    store.ingest_event(_raw_event())

    assert provider.called is True
    assert pool_bundle.committed_enriched_event is True
```

- [ ] Add integration test proving `events` and `enriched_events` commit together.

```python
def test_ingest_writes_event_and_enriched_event_in_same_transaction(db_pool_bundle, okx_quote_provider) -> None:
    store = _PooledIngestStore(pool_bundle=db_pool_bundle, providers=okx_quote_provider, settings=_settings())

    result = store.ingest_event(_raw_event_with_token_address())

    with db_pool_bundle.worker_session("assert") as repos:
        event = repos.evidence.events.by_id(result.event_id)
        enriched_rows = repos.enriched_events.list_by_event_id(result.event_id)

    assert event is not None
    assert len(enriched_rows) == 1
    assert enriched_rows[0]["capture_method"] == "tier3_inline"
```

- [ ] Refactor `IngestService` into explicit stages.

Required new shapes:

```python
@dataclass(frozen=True, slots=True)
class PreparedIngest:
    raw_event: RawEvent
    event_id: str
    event_ms: int
    event_row: dict[str, Any]
    entities: list[dict[str, Any]]
    evidence_inputs: list[TokenEvidenceInput]
    intents: list[dict[str, Any]]
    registry_inputs: list[dict[str, Any]]


class IngestService:
    def prepare_event(self, raw: RawEvent) -> PreparedIngest:
        return PreparedIngest.from_raw(raw, extractor=self._extractor, clock=self._clock)

    def prepare_registry_for_resolution(self, prepared: PreparedIngest) -> None:
        """Runs inside a short worker_session and upserts only registry rows needed by resolver reads."""

    def resolve_prepared(self, prepared: PreparedIngest, *, persist: bool = False) -> list[TokenResolutionResult]:
        return self._resolver.resolve(prepared.evidence_inputs, persist=persist)

    def commit_prepared_event(
        self,
        prepared: PreparedIngest,
        *,
        resolutions: list[TokenResolutionResult],
        captures: list[CaptureResult],
    ) -> IngestedEvent:
        return self._commit_event_graph(prepared, resolutions=resolutions, captures=captures)
```

Implementation sequence in `_PooledIngestStore.ingest_event`:

```python
prepare_service = IngestService(
    repos=None,
    extractor=extractor,
    resolver=resolver,
    clock=clock,
)
prepared = prepare_service.prepare_event(raw)

with pool_bundle.worker_session("collector") as repos:
    service = IngestService(
        repos=repos,
        extractor=extractor,
        resolver=resolver,
        clock=clock,
    )
    service.prepare_registry_for_resolution(prepared)
    resolutions = service.resolve_prepared(prepared, persist=False)
    tick_lookup_rows = _build_tick_lookup_rows(repos.market_ticks, resolutions, prepared.event_ms)

captures = []
for resolution in resolutions:
    captures.append(
        event_market_capture.capture_for_event(
            event_id=prepared.event_id,
            intent_id=resolution.intent_id,
            resolution_id=resolution.resolution_id,
            resolution=resolution.payload,
            event_ms=prepared.event_ms,
            tick_lookup=TickLookup.from_prefetched_rows(tick_lookup_rows),
        )
    )

with pool_bundle.worker_session("collector") as repos:
    service = IngestService(
        repos=repos,
        extractor=extractor,
        resolver=resolver,
        clock=clock,
    )
    return service.commit_prepared_event(
        prepared,
        resolutions=resolutions,
        captures=captures,
    )
```

Commit stage must:

- Insert `events`.
- Insert entities, evidence rows, token intents, and persisted token intent resolutions.
- Insert newly captured `market_ticks` before `enriched_events`.
- Insert one `enriched_events` row for each resolved token intent, keyed by `(event_id, intent_id)`.
- Insert token lookup rows, alerts, and enrichment jobs exactly once.

- [ ] Run ingest tests.

```bash
uv run pytest tests/unit/test_ingest_event_market_capture.py tests/integration/test_ingest_enriched_events.py -q
```

- [ ] Commit.

```bash
git add src/parallax/domains/evidence/services/ingest_service.py src/parallax/app/runtime/bootstrap.py tests/unit/test_ingest_event_market_capture.py tests/integration/test_ingest_enriched_events.py
git commit -m "feat: capture event market ticks during ingest commit"
```

### Task 7: Add token capture tier projection worker

**Files:**
- Create: `src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py`
- Modify: `src/parallax/app/runtime/worker_registry.py`
- Test: `tests/unit/test_token_capture_tier_worker.py`

- [ ] Write worker test for deterministic tiers.

```python
def test_token_capture_tier_worker_promotes_hot_tokens_to_ws() -> None:
    repos = FakeRepos(active_targets=[_target(target_id="solana:hot", score=95)])
    worker = TokenCaptureTierWorker(interval_seconds=30, batch_size=100, ws_limit=50)

    count = worker.run_once(repos=repos, now_ms=1_778_000_000_000)

    assert count == 1
    assert repos.capture_tiers[("chain_token", "solana:hot")]["tier"] == 1
    assert repos.capture_tiers[("chain_token", "solana:hot")]["reason"] == "ws_subscribed"
```

- [ ] Implement `TokenCaptureTierWorker`.

Required constructor:

```python
class TokenCaptureTierWorker:
    worker_name = "token_capture_tier"

    def __init__(
        self,
        *,
        pool_bundle: DBPoolBundle,
        interval_seconds: float,
        batch_size: int,
        ws_limit: int,
        poll_limit: int,
        clock: Callable[[], int],
    ) -> None:
        self._pool_bundle = pool_bundle
        self._interval_seconds = interval_seconds
        self._batch_size = batch_size
        self._ws_limit = ws_limit
        self._poll_limit = poll_limit
        self._clock = clock
```

Runtime behavior:

- Reads active target candidates from existing Token Radar / registry query surfaces.
- Writes `tier=1, reason='ws_subscribed'` for hottest `ws_limit`.
- Writes `tier=2, reason='batch_poll'` for next `poll_limit`.
- Writes `tier=3, reason='inline_only'` for resolved but less active targets.
- Uses `RepositorySession.token_capture_tiers.upsert_tier`.
- Does not call providers.

- [ ] Run tests.

```bash
uv run pytest tests/unit/test_token_capture_tier_worker.py -q
```

- [ ] Commit.

```bash
git add src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py src/parallax/app/runtime/worker_registry.py tests/unit/test_token_capture_tier_worker.py
git commit -m "feat: project token market capture tiers"
```

### Task 8: Add Tier 1 MarketTickStreamWorker

**Files:**
- Create: `src/parallax/domains/asset_market/runtime/market_tick_stream_worker.py`
- Modify: `src/parallax/app/providers_wiring.py`
- Test: `tests/unit/test_market_tick_stream_worker.py`

- [ ] Write stream worker test.

```python
def test_market_tick_stream_worker_writes_ws_ticks_and_notifies() -> None:
    stream = FakeDexStream(frames=[_dex_frame(token_address="0xabc", price="0.10", observed_at_ms=1_778_000_000_000)])
    repos = FakeRepos(capture_tiers=[_tier(target_type="chain_token", target_id="eip155:1:0xabc", tier=1)])
    wake = FakeWakeEmitter()
    worker = MarketTickStreamWorker(stream_dex_market=stream, pool_bundle=FakePool(repos), wake_emitter=wake, subscription_limit=10)

    count = worker.run_once()

    assert count == 1
    assert repos.market_ticks[0].source_tier == "tier1_ws"
    assert repos.market_ticks[0].source_provider == "okx_dex_ws"
    assert wake.channels == ["market_tick_written"]
```

- [ ] Implement worker.

Required behavior:

- Reads Tier 1 targets from `token_capture_tier`.
- Subscribes/refreshes OKX DEX WS targets.
- Normalizes each frame to `MarketTick`.
- Inserts ticks via `repos.market_ticks.insert_ticks`.
- Emits `market_tick_written` after at least one attempted insert.
- Uses DB only for reading target tiers and writing ticks; provider stream handling must not hold a DB session while blocking on network reads.

Constructor shape:

```python
class MarketTickStreamWorker:
    worker_name = "market_tick_stream"

    def __init__(
        self,
        *,
        pool_bundle: DBPoolBundle,
        stream_dex_market: DexMarketStreamProvider,
        wake_emitter: WakeEmitter,
        subscription_limit: int,
        interval_seconds: float,
        clock: Callable[[], int],
    ) -> None:
        self._pool_bundle = pool_bundle
        self._stream_dex_market = stream_dex_market
        self._wake_emitter = wake_emitter
        self._subscription_limit = subscription_limit
        self._interval_seconds = interval_seconds
        self._clock = clock
```

- [ ] Run tests.

```bash
uv run pytest tests/unit/test_market_tick_stream_worker.py -q
```

- [ ] Commit.

```bash
git add src/parallax/domains/asset_market/runtime/market_tick_stream_worker.py tests/unit/test_market_tick_stream_worker.py src/parallax/app/providers_wiring.py
git commit -m "feat: persist tier one market ticks from okx dex stream"
```

### Task 9: Add Tier 2 MarketTickPollWorker

**Files:**
- Create: `src/parallax/domains/asset_market/runtime/market_tick_poll_worker.py`
- Test: `tests/unit/test_market_tick_poll_worker.py`

- [ ] Write poll worker tests for CEX and DEX targets.

```python
def test_market_tick_poll_worker_polls_tier_two_targets() -> None:
    repos = FakeRepos(capture_tiers=[
        _tier(target_type="chain_token", target_id="solana:abc", tier=2),
        _tier(target_type="cex_symbol", target_id="okx:PEPE-USDT", tier=2),
    ])
    providers = ProvidersReturningQuotes()
    wake = FakeWakeEmitter()
    worker = MarketTickPollWorker(pool_bundle=FakePool(repos), providers=providers, wake_emitter=wake, batch_size=100)

    count = worker.run_once()

    assert count == 2
    assert {tick.source_provider for tick in repos.market_ticks} == {"okx_dex_rest", "okx_cex_rest"}
    assert wake.channels == ["market_tick_written"]
```

- [ ] Implement worker.

Required behavior:

- Short DB session A: read Tier 2 targets.
- No DB session: call OKX DEX REST for chain tokens and OKX CEX REST for CEX symbols.
- Short DB session B: insert ticks and notify `market_tick_written`.
- Skip failed provider quote with a structured log; do not insert unavailable rows into `market_ticks`.

Constructor shape:

```python
class MarketTickPollWorker:
    worker_name = "market_tick_poll"

    def __init__(
        self,
        *,
        pool_bundle: DBPoolBundle,
        providers: AssetMarketProviders,
        wake_emitter: WakeEmitter,
        interval_seconds: float,
        batch_size: int,
        clock: Callable[[], int],
    ) -> None:
        self._pool_bundle = pool_bundle
        self._providers = providers
        self._wake_emitter = wake_emitter
        self._interval_seconds = interval_seconds
        self._batch_size = batch_size
        self._clock = clock
```

- [ ] Run tests.

```bash
uv run pytest tests/unit/test_market_tick_poll_worker.py -q
```

- [ ] Commit.

```bash
git add src/parallax/domains/asset_market/runtime/market_tick_poll_worker.py tests/unit/test_market_tick_poll_worker.py
git commit -m "feat: poll tier two market ticks"
```

### Task 10: Convert LivePriceGateway to cache/publish only

**Files:**
- Modify: `src/parallax/domains/asset_market/runtime/live_price_gateway.py`
- Delete: `src/parallax/domains/asset_market/services/live_observation_policy.py`
- Modify: `tests/test_live_price_gateway.py`
- Modify: `tests/unit/test_live_price_gateway.py`
- Delete: `tests/unit/test_live_observation_policy.py`
- Delete: `tests/benchmark/test_live_observation_write_budget.py`

- [ ] Update gateway tests to assert no DB writes.

```python
def test_live_price_gateway_does_not_persist_market_facts() -> None:
    repos = ReposThatFailOnMarketTickWrite()
    gateway = LivePriceGateway(pool_bundle=FakePool(repos), providers=ProvidersReturningQuotes(), publisher=FakePublisher())

    gateway.run_once()

    assert gateway.cache_snapshot()
    assert repos.market_tick_write_attempts == 0
    assert repos.enriched_event_write_attempts == 0
```

- [ ] Remove these methods from `live_price_gateway.py`:

```python
_persist_material_observation
_observation_from_snapshot
_material_observation_reason
```

- [ ] Remove constructor settings:

```python
live_observation_min_interval_ms
live_observation_min_pct_move
live_observation_max_rows_per_cycle
```

- [ ] Keep only:

- active target discovery,
- provider fetch/stream fanout,
- in-memory cache update,
- downstream publish messages if those are still used by HTTP/WS live clients.

- [ ] Run tests.

```bash
uv run pytest tests/test_live_price_gateway.py tests/unit/test_live_price_gateway.py -q
```

- [ ] Commit.

```bash
git add src/parallax/domains/asset_market/runtime/live_price_gateway.py tests/test_live_price_gateway.py tests/unit/test_live_price_gateway.py
git rm src/parallax/domains/asset_market/services/live_observation_policy.py tests/unit/test_live_observation_policy.py tests/benchmark/test_live_observation_write_budget.py
git commit -m "refactor: make live price gateway cache only"
```

### Task 11: Hard-cut worker settings, registry, bootstrap, and wake channel

**Files:**
- Modify: `src/parallax/platform/config/settings.py`
- Modify: `src/parallax/app/runtime/worker_registry.py`
- Modify: `src/parallax/app/runtime/bootstrap.py`
- Modify: `docs/generated/cli-help.md`
- Test: `tests/architecture/test_worker_runtime_contracts.py`
- Test: `tests/unit/test_settings_workers.py`

- [ ] Update settings tests.

```python
def test_default_workers_yaml_uses_market_tick_workers() -> None:
    yaml_text = default_workers_yaml()
    assert "market_tick_stream:" in yaml_text
    assert "market_tick_poll:" in yaml_text
    assert "token_capture_tier:" in yaml_text
    assert "anchor_price:" not in yaml_text
    assert "live_observation_min_interval_ms" not in yaml_text
    assert "market_observation_written" not in yaml_text
```

- [ ] Replace settings classes.

New settings:

```python
class MarketTickStreamWorkerSettings(BaseModel):
    enabled: bool = True
    interval_seconds: float = 5.0
    subscription_limit: int = 100


class MarketTickPollWorkerSettings(BaseModel):
    enabled: bool = True
    interval_seconds: float = 15.0
    batch_size: int = 100


class TokenCaptureTierWorkerSettings(BaseModel):
    enabled: bool = True
    interval_seconds: float = 30.0
    batch_size: int = 500
    ws_limit: int = 100
    poll_limit: int = 500


class LivePriceGatewayWorkerSettings(BaseModel):
    enabled: bool = True
    interval_seconds: float = 2.0
```

`WorkersSettings` must contain:

```python
market_tick_stream: MarketTickStreamWorkerSettings = Field(default_factory=MarketTickStreamWorkerSettings)
market_tick_poll: MarketTickPollWorkerSettings = Field(default_factory=MarketTickPollWorkerSettings)
token_capture_tier: TokenCaptureTierWorkerSettings = Field(default_factory=TokenCaptureTierWorkerSettings)
live_price_gateway: LivePriceGatewayWorkerSettings = Field(default_factory=LivePriceGatewayWorkerSettings)
```

- [ ] Update canonical worker classes:

```python
CANONICAL_WORKER_CLASSES = {
    "collector": CollectorWorker,
    "market_tick_stream": MarketTickStreamWorker,
    "market_tick_poll": MarketTickPollWorker,
    "token_capture_tier": TokenCaptureTierWorker,
    "live_price_gateway": LivePriceGateway,
    "resolution_refresh": ResolutionRefreshWorker,
    "asset_profile_refresh": AssetProfileRefreshWorker,
    "token_radar_projection": TokenRadarProjectionWorker,
    "pulse_candidate": PulseCandidateWorker,
    "enrichment": EnrichmentWorker,
    "handle_summary": HandleSummaryWorker,
    "harness_ops": HarnessOpsWorker,
    "notification_rule": NotificationRuleWorker,
    "notification_delivery": NotificationDeliveryWorker,
}
```

Priority order:

```python
WORKER_START_PRIORITY = {
    "collector": 10,
    "token_capture_tier": 20,
    "market_tick_stream": 30,
    "market_tick_poll": 40,
    "live_price_gateway": 50,
    "resolution_refresh": 60,
    "asset_profile_refresh": 70,
    "token_radar_projection": 80,
    "pulse_candidate": 90,
    "enrichment": 100,
    "handle_summary": 110,
    "harness_ops": 120,
    "notification_rule": 130,
    "notification_delivery": 140,
}
```

- [ ] Update bootstrap construction.

Bootstrap must construct:

```python
TokenCaptureTierWorker(pool_bundle=pool_bundle, interval_seconds=settings.workers.token_capture_tier.interval_seconds, batch_size=settings.workers.token_capture_tier.batch_size, ws_limit=settings.workers.token_capture_tier.ws_limit, poll_limit=settings.workers.token_capture_tier.poll_limit, clock=clock)
MarketTickStreamWorker(pool_bundle=pool_bundle, stream_dex_market=providers.asset_market.stream_dex_market, wake_emitter=pool_bundle.wake_emitter(), subscription_limit=settings.workers.market_tick_stream.subscription_limit, interval_seconds=settings.workers.market_tick_stream.interval_seconds, clock=clock)
MarketTickPollWorker(pool_bundle=pool_bundle, providers=providers.asset_market, wake_emitter=pool_bundle.wake_emitter(), interval_seconds=settings.workers.market_tick_poll.interval_seconds, batch_size=settings.workers.market_tick_poll.batch_size, clock=clock)
LivePriceGateway(pool_bundle=pool_bundle, providers=providers.asset_market, interval_seconds=settings.workers.live_price_gateway.interval_seconds, clock=clock)
```

Bootstrap must not import:

```python
AnchorPriceWorker
```

Bootstrap must not emit or listen to:

```python
market_observation_written
```

- [ ] Regenerate CLI help after settings change.

```bash
uv run parallax --help > docs/generated/cli-help.md
```

- [ ] Run tests.

```bash
uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/unit/test_settings_workers.py -q
```

- [ ] Commit.

```bash
git add src/parallax/platform/config/settings.py src/parallax/app/runtime/worker_registry.py src/parallax/app/runtime/bootstrap.py docs/generated/cli-help.md tests/architecture/test_worker_runtime_contracts.py tests/unit/test_settings_workers.py
git commit -m "feat: wire market tick worker runtime"
```

### Task 12: Delete AnchorPrice runtime and old observation services

**Files:**
- Delete: `src/parallax/domains/asset_market/runtime/anchor_price_worker.py`
- Delete: `src/parallax/domains/asset_market/services/anchor_price_observation.py`
- Delete: `src/parallax/domains/asset_market/queries/pending_anchor_price_query.py`
- Delete: `tests/unit/test_anchor_price_observation.py`

- [ ] Delete the old files.

```bash
git rm src/parallax/domains/asset_market/runtime/anchor_price_worker.py
git rm src/parallax/domains/asset_market/services/anchor_price_observation.py
git rm src/parallax/domains/asset_market/queries/pending_anchor_price_query.py
git rm tests/unit/test_anchor_price_observation.py
```

- [ ] Verify imports are gone.

```bash
rg -n "AnchorPriceWorker|anchor_price_observation|pending_anchor_price_query|AnchorPriceWorkerSettings|anchor_price:" src tests docs --glob '!docs/superpowers/specs/active/2026-05-15-event-anchor-capture-redesign-cn.md' --glob '!docs/superpowers/plans/active/2026-05-15-event-anchor-capture-redesign-plan-cn.md'
```

Expected: no matches except historical migration/doc paths explicitly allowed by architecture tests.

- [ ] Commit.

```bash
git add -u
git commit -m "refactor: delete anchor price observation runtime"
```

### Task 13: Move Token Radar source query to enriched events and market ticks

**Files:**
- Modify: `src/parallax/domains/token_intel/queries/token_radar_source_query.py`
- Modify: `src/parallax/domains/token_intel/services/token_radar_projection.py`
- Modify: `src/parallax/domains/token_intel/scoring/factor_snapshot.py`
- Modify: `tests/unit/test_token_radar_source_query.py`
- Modify: `tests/unit/test_token_radar_projection.py`
- Modify: `tests/unit/test_factor_snapshot.py`
- Modify: `tests/golden/test_token_radar_corpus.py`

- [ ] Update query tests to require new joins.

```python
def test_token_radar_source_query_uses_enriched_events_and_market_ticks() -> None:
    sql = build_token_radar_source_query(limit=100)
    assert "enriched_events" in sql
    assert "market_ticks" in sql
    assert "price_observations" not in sql
    assert "event_anchor" not in sql
    assert "decision_latest" not in sql
```

- [ ] Replace old lateral observation joins with:

```sql
LEFT JOIN enriched_events event_market
  ON event_market.event_id = events.event_id
LEFT JOIN market_ticks event_tick
  ON event_tick.tick_id = event_market.tick_id
LEFT JOIN LATERAL (
  SELECT *
  FROM market_ticks latest_tick
  WHERE latest_tick.target_type = token_intent_resolutions.target_type
    AND latest_tick.target_id = token_intent_resolutions.target_id
    AND latest_tick.observed_at_ms <= %(now_ms)s
  ORDER BY latest_tick.observed_at_ms DESC
  LIMIT 1
) decision_tick ON true
LEFT JOIN LATERAL (
  SELECT *
  FROM market_ticks first_tick
  WHERE first_tick.target_type = token_intent_resolutions.target_type
    AND first_tick.target_id = token_intent_resolutions.target_id
  ORDER BY first_tick.observed_at_ms ASC
  LIMIT 1
) first_tick ON true
```

Column aliases should keep existing projection input names when that avoids frontend changes:

```sql
event_tick.price_usd AS event_price_usd,
event_tick.observed_at_ms AS event_price_observed_at_ms,
event_tick.source_provider AS event_price_provider,
event_tick.pricefeed_id AS event_price_pricefeed_id,
event_market.capture_method AS event_price_capture_method,
event_market.capture_reason AS event_price_capture_reason,
decision_tick.price_usd AS latest_price_usd,
decision_tick.observed_at_ms AS latest_price_observed_at_ms,
decision_tick.source_provider AS latest_price_provider,
decision_tick.pricefeed_id AS latest_price_pricefeed_id
```

- [ ] Update `token_radar_projection.py` market context.

Rules:

- `factor_snapshot.market.event_anchor` JSON key may remain.
- Its `source` field becomes `capture_method`, not DB `observation_kind`.
- `factor_snapshot.market.decision_latest` JSON key may remain.
- Its data comes from latest `market_ticks`, not persisted live observation policy.
- `market_context["pricefeed_id"]` still uses target resolution `pricefeed_id` or tick `pricefeed_id`.

- [ ] Update factor snapshot tests to keep public shape but remove old semantics.

Assertion:

```python
assert snapshot["market"]["event_anchor"]["source"] == "tier3_inline"
assert snapshot["market"]["event_anchor"]["price_usd"] == 0.42
assert "observation_kind" not in snapshot["market"]["event_anchor"]
```

- [ ] Run radar tests.

```bash
uv run pytest tests/unit/test_token_radar_source_query.py tests/unit/test_token_radar_projection.py tests/unit/test_factor_snapshot.py tests/golden/test_token_radar_corpus.py -q
```

- [ ] Commit.

```bash
git add src/parallax/domains/token_intel/queries/token_radar_source_query.py src/parallax/domains/token_intel/services/token_radar_projection.py src/parallax/domains/token_intel/scoring/factor_snapshot.py tests/unit/test_token_radar_source_query.py tests/unit/test_token_radar_projection.py tests/unit/test_factor_snapshot.py tests/golden/test_token_radar_corpus.py
git commit -m "refactor: source token radar market context from market ticks"
```

### Task 14: Update secondary consumers of historical market data

**Files:**
- Modify: `src/parallax/domains/token_intel/repositories/token_target_repository.py`
- Modify: `src/parallax/domains/token_intel/services/token_factor_evaluation.py`
- Modify: `src/parallax/domains/account_quality/repositories/account_quality_repository.py`
- Modify: `src/parallax/app/surfaces/cli/main.py`
- Modify: related tests under `tests/unit/`, `tests/integration/`, and `tests/e2e/`

- [ ] Update `token_target_repository.py` tests.

Required assertion:

```python
assert "market_ticks" in conn.sql
assert "enriched_events" in conn.sql
assert "price_observations" not in conn.sql
assert "message_anchor" not in conn.sql
```

- [ ] Replace token target post price join.

Old intent:

```sql
LEFT JOIN price_observations
  ON price_observations.source_event_id = events.event_id
```

New intent:

```sql
LEFT JOIN enriched_events
  ON enriched_events.event_id = events.event_id
LEFT JOIN market_ticks event_tick
  ON event_tick.tick_id = enriched_events.tick_id
```

- [ ] Update `token_factor_evaluation.py`.

Replace calls:

```python
repos.price_observations.latest_price_for_subject_at_or_before(
    subject_type=target_type,
    subject_id=target_id,
    at_ms=event_ms,
)
repos.price_observations.first_price_for_subject_between(
    subject_type=target_type,
    subject_id=target_id,
    start_ms=start_ms,
    end_ms=end_ms,
)
```

With:

```python
repos.market_ticks.latest_at_or_before(
    target_type=target_type,
    target_id=target_id,
    at_ms=event_ms,
    max_lag_ms=max_lag_ms,
)
repos.market_ticks.first_between(
    target_type=target_type,
    target_id=target_id,
    start_ms=start_ms,
    end_ms=end_ms,
)
```

- [ ] Update account quality price history query.

Required SQL source:

```sql
FROM market_ticks
WHERE target_type = %(target_type)s
  AND target_id = %(target_id)s
ORDER BY observed_at_ms ASC
```

- [ ] Update CLI audit field names.

Use:

```python
source_max_market_tick_observed_at_ms
```

Instead of:

```python
source_max_price_observed_at_ms
```

- [ ] Run targeted consumer tests.

```bash
uv run pytest tests/unit/test_token_target_posts_service.py tests/unit/test_token_radar_audit_cli.py tests/unit/test_account_quality_repository.py tests/unit/test_token_factor_evaluation.py tests/integration/test_api_http.py tests/e2e/test_pulse_agent_runtime_flow.py -q
```

- [ ] Commit.

```bash
git add src/parallax/domains/token_intel/repositories/token_target_repository.py src/parallax/domains/token_intel/services/token_factor_evaluation.py src/parallax/domains/account_quality/repositories/account_quality_repository.py src/parallax/app/surfaces/cli/main.py tests
git commit -m "refactor: move market history consumers to ticks"
```

### Task 15: Update docs and domain architecture maps

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/RELIABILITY.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/FRONTEND.md`
- Modify: `src/parallax/domains/asset_market/ARCHITECTURE.md`
- Modify: `src/parallax/domains/token_intel/ARCHITECTURE.md`

- [ ] Replace old architecture language.

Required new statements:

- `market_ticks` are append-only provider tick facts.
- `enriched_events` are event projection rows committed with `events`.
- `token_capture_tier` is a rebuildable projection with one runtime writer.
- `MarketTickStreamWorker` writes Tier 1 WS ticks.
- `MarketTickPollWorker` writes Tier 2 REST ticks.
- Ingest inline capture writes Tier 3 ticks and enriched event rows.
- `LivePriceGateway` is cache/publish only.
- `market_tick_written` is a wake hint; listeners re-read DB and catch up by interval.

- [ ] Remove or rewrite old statements:

```text
price_observations are business truth
event_anchor
decision_latest
AnchorPriceWorker
market_observation_written
live observation write budget
```

- [ ] Run doc grep.

```bash
rg -n "price_observations|event_anchor|decision_latest|AnchorPriceWorker|market_observation_written|live observation" docs src/parallax/domains/*/ARCHITECTURE.md --glob '!docs/superpowers/specs/active/2026-05-15-event-anchor-capture-redesign-cn.md' --glob '!docs/superpowers/plans/active/2026-05-15-event-anchor-capture-redesign-plan-cn.md'
```

Expected: no runtime docs still teach old semantics. If `event_anchor` appears only as public API JSON adapter wording, the paragraph must explicitly say it is a compatibility-shaped response generated from `enriched_events` and `market_ticks`, not an internal market concept.

- [ ] Commit.

```bash
git add docs/ARCHITECTURE.md docs/RELIABILITY.md docs/WORKERS.md docs/CONTRACTS.md docs/FRONTEND.md src/parallax/domains/asset_market/ARCHITECTURE.md src/parallax/domains/token_intel/ARCHITECTURE.md
git commit -m "docs: describe market tick capture architecture"
```

### Task 16: Full hard-cut cleanup and verification

**Files:**
- Entire repo

- [ ] Remove old tests if any remain.

```bash
git rm tests/test_price_observation_read_models.py || true
git rm tests/unit/test_price_observation_repository.py || true
git rm tests/unit/test_price_observation_repository_policy.py || true
git rm tests/unit/test_live_observation_policy.py || true
git rm tests/benchmark/test_live_observation_write_budget.py || true
```

- [ ] Run hard-cut grep.

```bash
rg -n "price_observations|message_anchor|market_observation_written|AnchorPriceWorker|anchor_price:|AnchorPriceWorkerSettings|should_persist_live_observation" src tests docs \
  --glob '!src/parallax/platform/db/alembic/versions/20260513_0036_token_radar_kappa_cqrs_hard_cut.py' \
  --glob '!docs/superpowers/specs/active/2026-05-15-event-anchor-capture-redesign-cn.md' \
  --glob '!docs/superpowers/plans/active/2026-05-15-event-anchor-capture-redesign-plan-cn.md'
```

Expected: no matches.

- [ ] Run enum drift grep.

```bash
rg -n "\"event_anchor\"|'event_anchor'|\"decision_latest\"|'decision_latest'|\"message_anchor\"|'message_anchor'" src tests \
  --glob '!tests/unit/test_factor_snapshot.py' \
  --glob '!src/parallax/domains/token_intel/scoring/factor_snapshot.py'
```

Expected: no matches in internal DB/runtime code. Any remaining frontend-facing response key test must assert it is sourced from `capture_method`, not DB observation kind.

- [ ] Run full verification.

```bash
uv run ruff check .
uv run pytest
uv run alembic upgrade head
uv run parallax workers list
uv run parallax --help > docs/generated/cli-help.md
```

Expected:

- Ruff passes.
- Pytest passes.
- Alembic upgrade creates `market_ticks`, `enriched_events`, and `token_capture_tier`; `price_observations` is absent.
- Worker list contains `market_tick_stream`, `market_tick_poll`, and `token_capture_tier`; it does not contain `anchor_price`.

- [ ] Commit final cleanup.

```bash
git add -A
git commit -m "chore: complete event anchor capture hard cut"
```

## PR Breakdown

Use one hard-cut PR. Intermediate commits should follow the task boundaries above, but the branch should not be deployed partially because old settings, old table removal, and new read models must land together.

1. **PR 1 — event anchor capture redesign hard cut**:
   - Migration: create `market_ticks`, `enriched_events`, `token_capture_tier`; drop `price_observations`.
   - Runtime: delete `AnchorPriceWorker`, add capture tier / stream / poll workers, change ingest to inline capture.
   - Repositories: replace price observation repo with market tick/enriched event repos.
   - Read models: move Token Radar and secondary consumers to new tables.
   - Docs/tests: update architecture and hard-cut guards.

## Rollout Order

1. Stop old workers.
2. Deploy code and migration together.
3. Run:

```bash
uv run alembic upgrade head
```

4. Start unified worker runtime.
5. Confirm workers:

```bash
uv run parallax workers list
```

Expected live workers:

```text
collector
token_capture_tier
market_tick_stream
market_tick_poll
live_price_gateway
token_radar_projection
pulse_candidate
enrichment
handle_summary
harness_ops
notification_rule
notification_delivery
```

6. Rebuild projections that depend on market context:

```bash
uv run parallax ops rebuild-token-radar
```

7. Watch logs for:

```text
market_tick_written
capture_method=tier1_ws
capture_method=tier2_poll
capture_method=tier3_inline
capture_method=unavailable
```

## Rollback

This is a hard cut. Production rollback is code rollback plus database restore from pre-migration backup.

Safe compensating actions:

- Pause `market_tick_stream`, `market_tick_poll`, and `collector` if provider behavior is unhealthy.
- Keep HTTP read-only if projections are stale.
- Restore DB backup if `DROP TABLE price_observations` must be undone.

Unsafe actions:

- Re-enabling `AnchorPriceWorker`.
- Recreating runtime writes to `price_observations`.
- Reading both old and new market tables in production code.

## Acceptance Criteria Mapping

- AC1, AC2, AC3, AC4: `uv run pytest tests/unit/test_event_market_capture.py tests/integration/test_ingest_enriched_events.py -q`
- AC5: `uv run pytest tests/unit/test_market_tick_stream_worker.py tests/unit/test_market_tick_poll_worker.py -q`
- AC6: `uv run pytest tests/unit/test_token_capture_tier_worker.py -q`
- AC7: `uv run pytest tests/test_live_price_gateway.py tests/unit/test_live_price_gateway.py -q`
- AC8: `uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/unit/test_settings_workers.py -q`
- AC9: `uv run pytest tests/unit/test_token_radar_source_query.py tests/unit/test_token_radar_projection.py tests/golden/test_token_radar_corpus.py -q`
- AC10: `uv run pytest tests/architecture/test_event_anchor_capture_redesign_contracts.py -q`
- AC11: `uv run pytest tests/unit/test_okx_dex_quote_provider.py -q`
- AC12: `uv run pytest tests/unit/test_ingest_event_market_capture.py tests/integration/test_ingest_enriched_events.py -q`
- AC13: hard-cut grep:

```bash
rg -n "price_observations|message_anchor|market_observation_written|AnchorPriceWorker|anchor_price:|should_persist_live_observation" src tests docs \
  --glob '!src/parallax/platform/db/alembic/versions/20260513_0036_token_radar_kappa_cqrs_hard_cut.py' \
  --glob '!docs/superpowers/specs/active/2026-05-15-event-anchor-capture-redesign-cn.md' \
  --glob '!docs/superpowers/plans/active/2026-05-15-event-anchor-capture-redesign-plan-cn.md'
```

Expected: no matches.

## Verification

Before declaring implementation complete, create:

`docs/superpowers/plans/active/2026-05-15-event-anchor-capture-redesign-verification-cn.md`

Include:

- Branch and commit SHA.
- Baseline test status.
- Every command from Acceptance Criteria Mapping with pass/fail output.
- Alembic upgrade output.
- Hard-cut grep output.
- A sample `enriched_events JOIN market_ticks` row from local or test DB:

```sql
SELECT
  enriched_events.event_id,
  enriched_events.capture_method,
  enriched_events.capture_reason,
  market_ticks.source_tier,
  market_ticks.source_provider,
  market_ticks.price_usd,
  market_ticks.observed_at_ms
FROM enriched_events
LEFT JOIN market_ticks ON market_ticks.tick_id = enriched_events.tick_id
ORDER BY enriched_events.created_at_ms DESC
LIMIT 5;
```

Expected sample properties:

- At least one captured row has `capture_method IN ('tier1_ws', 'tier2_poll', 'tier3_inline')`.
- Unavailable rows have `tick_id IS NULL`.
- Captured rows have `tick_lag_ms >= 0`.

## Self-Review Checklist

- [ ] Spec coverage: every old price observation writer is deleted or converted to new tick capture.
- [ ] Spec coverage: ingest provider IO happens outside DB sessions.
- [ ] Spec coverage: `events` and `enriched_events` are committed together.
- [ ] Spec coverage: `market_ticks` and `enriched_events` are append-only.
- [ ] Spec coverage: Token Radar reads the new source of truth.
- [ ] Spec coverage: settings and worker inventory contain no old worker names.
- [ ] No placeholder language remains in this plan.
- [ ] Type names are consistent: `MarketTick`, `EnrichedEventCapture`, `MarketTickRepository`, `EnrichedEventRepository`, `TokenCaptureTierRepository`.
- [ ] Literal names are consistent: `tier1_ws`, `tier2_poll`, `tier3_inline`, `unavailable`, `market_tick_written`.
