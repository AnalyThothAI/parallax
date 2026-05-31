# Token Radar Factor Snapshot Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-cut Token Radar, Signal Lab Pulse, notifications, and frontend reads from score/thesis-centered runtime contracts to a professional `TokenFactorSnapshot` contract with no legacy fallback.

**Architecture:** Keep `TokenRadarProjection` as the production projection entrypoint, but change its output contract to `factor_snapshot_json`. Build deterministic factor families from existing raw source rows, derive score/gate/rank from the snapshot, then pass that same snapshot to Pulse, notifications, and UI. Migration `20260510_0023` drops legacy Signal Pulse `thesis_json`, `radar_score_json`, and `market_context_json` columns; current runtime paths must not read them as fallback.

**Tech Stack:** Python 3.13, PostgreSQL JSONB, Alembic, pytest, Pydantic, OpenAI Agents SDK, React/TypeScript, Vitest.

---

**Status**: Implemented and verified in `codex/token-radar-factor-snapshot-hard-cut`
**Date**: 2026-05-10
**Owning spec**: `docs/superpowers/specs/active/2026-05-10-token-radar-factor-snapshot-architecture-cn.md`
**Worktree**: `.worktrees/token-radar-factor-snapshot-hard-cut/`
**Branch**: `codex/token-radar-factor-snapshot-hard-cut`

## Pre-flight

- [ ] Create the worktree from the repository root:
  ```bash
  git worktree add .worktrees/token-radar-factor-snapshot-hard-cut -b codex/token-radar-factor-snapshot-hard-cut main
  ```
- [ ] Copy this plan and the owning spec into the worktree if they were authored in the main checkout.
- [ ] In the worktree, verify location and branch:
  ```bash
  git worktree list
  git status --short
  git branch --show-current
  ```
  Expected branch: `codex/token-radar-factor-snapshot-hard-cut`.
- [ ] Confirm the active DB migration head is after `20260510_0021_asset_identity_evidence_hard_cut.py`.
- [ ] Record baseline:
  ```bash
  uv run ruff check src tests
  uv run pytest -q
  uv run python -m compileall src tests
  npm test -- --run
  npm run build
  ```
- [ ] Do not edit `.worktrees/token-identity-freshness-hard-cut/`; that worktree belongs to another task.

Known baseline expectation: no known failing tests are accepted for this plan. If the baseline fails, record exact failing tests in this plan before implementation.

## File Structure

### New Python files

- `src/parallax/domains/token_intel/scoring/factor_snapshot.py`
  - Owns `TOKEN_FACTOR_SNAPSHOT_VERSION`, factor point helpers, social factor assembly, market/on-chain-lite factor assembly, hard gates, and composite score derivation.
  - Pure functions only; no DB, no HTTP, no agent calls.
- `src/parallax/domains/asset_market/services/market_freshness_demand.py`
  - Owns Token Radar product freshness classes and refresh priority scoring for market observation.
  - Pure domain selection helpers; provider calls remain in `asset_market_sync.py`.
- `src/parallax/domains/pulse_lab/types/pulse_recommendation.py`
  - Replaces thesis-first agent output for current Pulse runs.
  - Validates factor-key-backed reasons and forbids unsupported execution language.
- `src/parallax/platform/db/alembic/versions/20260510_0022_token_radar_factor_snapshot_hard_cut.py`
  - Adds current factor snapshot storage columns and current Pulse recommendation storage columns.

### Modified Python files

- `src/parallax/domains/token_intel/_constants.py`
  - Bump `TOKEN_RADAR_PROJECTION_VERSION` to `token-radar-v9-factor-snapshot`.
  - Replace score component constant with factor family constant.
- `src/parallax/domains/token_intel/services/token_radar_projection.py`
  - Build `factor_snapshot_json`.
  - Rank from factor snapshot composite score.
  - Stop using old score JSON as runtime source.
- `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
  - Insert/read `factor_snapshot_json` and `factor_version`.
  - Stop requiring current callers to pass `attention_json`, `market_json`, `price_json`, `score_json` as the runtime contract.
- `src/parallax/domains/token_intel/read_models/asset_flow_service.py`
  - Read current Token Radar facts from `factor_snapshot_json`.
- `src/parallax/domains/asset_market/services/asset_market_sync.py`
  - Use explicit market freshness demand when selecting DEX radar refresh candidates.
- `src/parallax/domains/asset_market/runtime/asset_market_sync_worker.py`
  - Accept configurable DEX refresh interval, stale thresholds, and limits instead of sharing only the CEX sync interval.
- `src/parallax/domains/asset_market/repositories/registry_repository.py`
  - Return enough active target metadata for deterministic freshness priority ordering.
- `src/parallax/platform/config/settings.py`
  - Add OKX/market freshness knobs for DEX refresh cadence and hot/warm SLOs.
- `src/parallax/domains/pulse_lab/interfaces.py`
  - Bump Pulse version constants from thesis v1 to factor recommendation v1.
- `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
  - Pass factor snapshot through candidate context.
  - Gate before agent.
  - Persist factor snapshot and agent recommendation.
  - Stop passing `radar_score_json` and `market_context_json`.
- `src/parallax/domains/pulse_lab/services/pulse_candidate_gate.py`
  - Consume factor snapshot rather than thesis + radar/market/timeline context.
- `src/parallax/domains/pulse_lab/repositories/pulse_repository.py`
  - Replace candidate upsert contract with `factor_snapshot_json`, `agent_recommendation_json`, and `gate_json`.
  - Update summary `market_fresh_count` to read factor snapshot.
- `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py`
  - Expose factor facts and recommendation; remove current read-model dependency on `radar_score_json` and `market_context_json`.
- `src/parallax/integrations/openai_agents/pulse_thesis_agent_client.py`
  - Rename or replace thesis client behavior with recommendation output schema. The file may keep its name only if imports make renaming too noisy; runtime semantics must be recommendation-first.
- `src/parallax/domains/notifications/services/notification_rules.py`
  - Gate severity from factor snapshot.
  - Render fact-first Signal Pulse body.

### Modified frontend files

- `web/src/api/types.ts`
  - Replace `SignalPulseItem.radar_score_json` / `market_context_json` with typed `factor_snapshot` and `agent_recommendation`.
  - Add factor fact card types.
- `web/src/components/SignalLabPulse.tsx`
  - Render high-signal market/social fact chips before agent summary.
- `web/src/components/PulseDetailPage.tsx`
  - Render factor families, hard gates, and agent recommendation.
- `web/src/components/SignalLabInspector.tsx` and `web/src/components/SignalLabWorkbench.tsx`
  - Remove old thesis/score assumptions where present.
- `web/src/lib/venue.ts`
  - Read venue links from factor snapshot subject when old market context is removed.

### Tests to add or rewrite

- `tests/unit/test_factor_snapshot.py`
- `tests/test_token_radar_projection.py`
- `tests/test_token_radar_repository.py`
- `tests/test_market_freshness_demand.py`
- `tests/test_asset_market_sync.py`
- `tests/test_settings.py`
- `tests/test_pulse_candidate_gate.py`
- `tests/test_pulse_candidate_worker.py`
- `tests/test_pulse_repository.py`
- `tests/test_signal_pulse_service.py`
- `tests/test_notification_rules.py`
- `tests/test_pulse_recommendation.py`
- `web/src/components/SignalLabPulse.test.tsx`
- `web/src/components/__tests__/PulseDetailPage.routing.test.tsx`
- `web/src/api/__tests__/useSignalPulseQueries.test.tsx`

## Task 1: Add Hard-Cut Schema Columns

**Files:**

- Create: `src/parallax/platform/db/alembic/versions/20260510_0022_token_radar_factor_snapshot_hard_cut.py`
- Modify: `src/parallax/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `src/parallax/domains/pulse_lab/repositories/pulse_repository.py`
- Test: `tests/test_token_radar_repository.py`
- Test: `tests/test_pulse_repository.py`

- [ ] **Step 1: Write failing repository tests for new columns**

  Add a test in `tests/test_token_radar_repository.py` that inserts a row with:
  ```python
  row = {
      "row_id": "row-factor-1",
      "source_max_received_at_ms": 1_778_000_000_000,
      "lane": "resolved",
      "rank": 1,
      "intent_id": "intent-1",
      "event_id": "event-1",
      "target_type": "Asset",
      "target_id": "asset-1",
      "pricefeed_id": "feed-1",
      "intent_json": {"display_symbol": "BOV"},
      "asset_json": {},
      "primary_venue_json": None,
      "target_json": {"symbol": "BOV"},
      "factor_snapshot_json": {
          "schema_version": "token_factor_snapshot_v1",
          "subject": {"target_type": "Asset", "target_id": "asset-1", "symbol": "BOV"},
          "families": {},
          "hard_gates": {"eligible_for_high_alert": False, "blocked_reasons": ["liquidity_below_high_alert_floor"]},
          "composite": {"rank_score": 12, "recommended_decision": "discard"},
      },
      "factor_version": "token_factor_snapshot_v1",
      "decision": "discard",
      "data_health_json": {"factor_snapshot": "ready"},
      "source_event_ids_json": ["event-1"],
      "created_at_ms": 1_778_000_000_000,
  }
  ```

  Assert `repository.latest_rows(window="1h", scope="all", limit=10, projection_version="token-radar-v9-factor-snapshot")[0]["factor_snapshot_json"]["schema_version"] == "token_factor_snapshot_v1"` and that no assertion reads `score_json`.

- [ ] **Step 2: Write failing Pulse repository test**

  Add a test in `tests/test_pulse_repository.py` that calls `upsert_candidate()` with:
  ```python
  factor_snapshot_json={"schema_version": "token_factor_snapshot_v1", "hard_gates": {"eligible_for_high_alert": False}},
  agent_recommendation_json={"schema_version": "pulse_recommendation_v1", "recommendation": "ignore"},
  gate_json={"pulse_status": "blocked_low_information", "candidate_score": 12},
  ```
  Assert the returned row contains these three JSON blobs and that the call signature does not accept `radar_score_json` or `market_context_json`.

- [ ] **Step 3: Add Alembic migration**

  Migration SQL:
  ```sql
  ALTER TABLE token_radar_rows
    ADD COLUMN IF NOT EXISTS factor_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb;
  ALTER TABLE token_radar_rows
    ADD COLUMN IF NOT EXISTS factor_version TEXT NOT NULL DEFAULT 'token_factor_snapshot_v1';

  ALTER TABLE pulse_candidates
    ADD COLUMN IF NOT EXISTS factor_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb;
  ALTER TABLE pulse_candidates
    ADD COLUMN IF NOT EXISTS agent_recommendation_json JSONB NOT NULL DEFAULT '{}'::jsonb;
  ALTER TABLE pulse_candidates
    ADD COLUMN IF NOT EXISTS gate_json JSONB NOT NULL DEFAULT '{}'::jsonb;

  CREATE INDEX IF NOT EXISTS idx_token_radar_rows_factor_version
    ON token_radar_rows(projection_version, factor_version, "window", scope, computed_at_ms DESC);
  CREATE INDEX IF NOT EXISTS idx_pulse_candidates_factor_snapshot_gate
    ON pulse_candidates(pulse_version, "window", scope, updated_at_ms DESC)
    WHERE factor_snapshot_json <> '{}'::jsonb;
  ```

  Downgrade SQL:
  ```sql
  DROP INDEX IF EXISTS idx_pulse_candidates_factor_snapshot_gate;
  DROP INDEX IF EXISTS idx_token_radar_rows_factor_version;
  ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS gate_json;
  ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS agent_recommendation_json;
  ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS factor_snapshot_json;
  ALTER TABLE token_radar_rows DROP COLUMN IF EXISTS factor_version;
  ALTER TABLE token_radar_rows DROP COLUMN IF EXISTS factor_snapshot_json;
  ```

- [ ] **Step 4: Update repositories**

  `TokenRadarRepository.replace_rows()` insert list includes `factor_snapshot_json` and `factor_version`. Keep old physical columns omitted from the insert so their defaults are not a runtime contract.

  `TokenRadarRepository._json_payload()` JSON keys include:
  ```python
  "factor_snapshot_json",
  "intent_json",
  "asset_json",
  "primary_venue_json",
  "target_json",
  "data_health_json",
  "source_event_ids_json",
  ```

  `PulseRepository.upsert_candidate()` signature changes to:
  ```python
  def upsert_candidate(
      self,
      *,
      candidate_id: str,
      candidate_type: str,
      subject_key: str,
      window: str,
      scope: str,
      pulse_status: str,
      verdict: str,
      social_phase: str,
      narrative_type: str,
      candidate_score: float,
      score_band: str,
      trigger_signature: str,
      timeline_signature: str,
      pulse_version: str,
      gate_version: str,
      prompt_version: str,
      schema_version: str,
      factor_snapshot_json: dict[str, Any],
      gate_json: dict[str, Any],
      agent_recommendation_json: dict[str, Any] | None = None,
      target_type: str | None = None,
      target_id: str | None = None,
      symbol: str | None = None,
      gate_reasons_json: list[Any] | None = None,
      risk_reasons_json: list[Any] | None = None,
      evidence_event_ids_json: list[Any] | None = None,
      source_event_ids_json: list[Any] | None = None,
      agent_run_id: str | None = None,
      created_at_ms: int | None = None,
      updated_at_ms: int | None = None,
      commit: bool = True,
  ) -> dict[str, Any]:
  ```

- [ ] **Step 5: Run focused tests**

  ```bash
  uv run pytest tests/test_token_radar_repository.py tests/test_pulse_repository.py -q
  ```
  Expected after implementation: PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add src/parallax/platform/db/alembic/versions/20260510_0022_token_radar_factor_snapshot_hard_cut.py \
          src/parallax/domains/token_intel/repositories/token_radar_repository.py \
          src/parallax/domains/pulse_lab/repositories/pulse_repository.py \
          tests/test_token_radar_repository.py tests/test_pulse_repository.py
  git commit -m "feat: add factor snapshot hard cut storage"
  ```

## Task 2: Build TokenFactorSnapshot Pure Domain Layer

**Files:**

- Create: `src/parallax/domains/token_intel/scoring/factor_snapshot.py`
- Modify: `src/parallax/domains/token_intel/scoring/__init__.py`
- Test: `tests/unit/test_factor_snapshot.py`

- [ ] **Step 1: Write tests for DEX floors, CEX separation, and social quality**

  Add tests:

  ```python
  def test_dex_asset_below_market_floors_blocks_high_alert():
      snapshot = build_token_factor_snapshot(
          target={"target_type": "Asset", "target_id": "asset:bsc:0x1", "symbol": "BOV", "chain": "56", "address": "0x1"},
          attention={"mentions_1h": 3, "mentions_4h": 3, "mentions_24h": 3, "unique_authors": 2, "watched_mentions": 0},
          social_quality={"duplicate_text_share": 0.0, "informative_post_count": 1, "mentions": 3, "independent_authors": 2},
          social_semantics={"direction_counts": {"bullish": 1}, "impact_mean": 0.2, "novelty_mean": 0.1, "confidence_mean": 0.6},
          market={
              "market_status": "fresh",
              "market_cap_usd": 12087.0,
              "liquidity_usd": 6553.0,
              "holders": 46,
              "price_change_since_social_pct": -0.1338,
              "price_change_before_social_pct": None,
          },
          timing={"price_change_before_social_pct": None, "price_change_since_social_pct": -0.1338},
          source_event_ids=["event-1", "event-2", "event-3"],
          computed_at_ms=1_778_000_000_000,
      )

      assert snapshot["hard_gates"]["eligible_for_high_alert"] is False
      assert set(snapshot["hard_gates"]["blocked_reasons"]) >= {
          "holders_below_high_alert_floor",
          "liquidity_below_high_alert_floor",
          "market_cap_below_high_alert_floor",
          "insufficient_independent_social_sources",
      }
      assert snapshot["families"]["market_quality"]["factors"]["holders"]["raw_value"] == 46
  ```

  ```python
  def test_cex_token_does_not_apply_dex_holder_liquidity_floors():
      snapshot = build_token_factor_snapshot(
          target={"target_type": "CexToken", "target_id": "cex_token:BLEND", "symbol": "BLEND"},
          attention={"mentions_1h": 7, "mentions_4h": 7, "mentions_24h": 9, "unique_authors": 5, "watched_mentions": 1},
          social_quality={"duplicate_text_share": 0.0, "informative_post_count": 5, "mentions": 7, "independent_authors": 5},
          social_semantics={"direction_counts": {"bullish": 3, "neutral": 2}, "impact_mean": 0.5, "novelty_mean": 0.3, "confidence_mean": 0.8},
          market={"market_status": "fresh", "volume_24h_usd": 45_000_000.0, "open_interest_usd": None, "native_market_id": "OKX:BLEND-USDT"},
          timing={"price_change_before_social_pct": 0.02, "price_change_since_social_pct": 0.01},
          source_event_ids=["event-1"],
          computed_at_ms=1_778_000_000_000,
      )

      assert "holders_below_high_alert_floor" not in snapshot["hard_gates"]["blocked_reasons"]
      assert "liquidity_below_high_alert_floor" not in snapshot["hard_gates"]["blocked_reasons"]
      assert snapshot["families"]["market_quality"]["target_market_type"] == "cex"
  ```

  ```python
  def test_duplicate_social_text_blocks_high_alert():
      snapshot = build_token_factor_snapshot(
          target={"target_type": "Asset", "target_id": "asset:solana:token:X", "symbol": "X", "chain": "solana", "address": "X"},
          attention={"mentions_1h": 5, "mentions_4h": 5, "mentions_24h": 5, "unique_authors": 5, "watched_mentions": 0},
          social_quality={"duplicate_text_share": 0.75, "informative_post_count": 1, "mentions": 5, "independent_authors": 5},
          social_semantics={"direction_counts": {}, "impact_mean": None, "novelty_mean": None, "confidence_mean": None},
          market={"market_status": "fresh", "market_cap_usd": 200_000.0, "liquidity_usd": 80_000.0, "holders": 500},
          timing={"price_change_before_social_pct": 0.0, "price_change_since_social_pct": 0.0},
          source_event_ids=["event-1", "event-2"],
          computed_at_ms=1_778_000_000_000,
      )

      assert "duplicate_text_share_high" in snapshot["hard_gates"]["blocked_reasons"]
  ```

- [ ] **Step 2: Implement factor snapshot builder**

  Public constants and functions:

  ```python
  TOKEN_FACTOR_SNAPSHOT_VERSION = "token_factor_snapshot_v1"
  FACTOR_FAMILIES = (
      "identity",
      "social_attention",
      "social_quality",
      "social_semantics",
      "market_quality",
      "timing",
  )

  DEX_HIGH_ALERT_FLOORS = {
      "holders": 100,
      "liquidity_usd": 25_000.0,
      "market_cap_usd": 50_000.0,
      "unique_authors": 3,
      "duplicate_text_share": 0.50,
  }

  def build_token_factor_snapshot(
      *,
      target: dict[str, Any],
      attention: dict[str, Any],
      social_quality: dict[str, Any],
      social_semantics: dict[str, Any],
      market: dict[str, Any],
      timing: dict[str, Any],
      source_event_ids: list[str],
      computed_at_ms: int,
  ) -> dict[str, Any]:
      families = {
          "identity": _identity_family(target=target),
          "social_attention": _social_attention_family(attention=attention),
          "social_quality": _social_quality_family(social_quality=social_quality),
          "social_semantics": _social_semantics_family(social_semantics=social_semantics),
          "market_quality": _market_quality_family(target=target, market=market),
          "timing": _timing_family(timing=timing),
      }
      hard_gates = _hard_gates(target=target, families=families)
      composite = _composite(families=families, hard_gates=hard_gates)
      return {
          "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
          "subject": _subject(target),
          "families": families,
          "hard_gates": hard_gates,
          "composite": composite,
          "provenance": {
              "source_event_ids": list(dict.fromkeys(str(event_id) for event_id in source_event_ids if str(event_id))),
              "computed_at_ms": int(computed_at_ms),
          },
      }
  ```

  Factor point shape:

  ```python
  {
      "family": "market_quality",
      "key": "liquidity_usd",
      "raw_value": 6553.0,
      "score": 5,
      "confidence": 0.95,
      "data_health": "ready",
      "freshness_ms": 11000,
      "source_refs": [],
      "risk_flags": ["liquidity_below_high_alert_floor"],
      "hard_gate": "block_high_alert",
  }
  ```

  Composite shape:

  ```python
  {
      "family_scores": {
          "identity": 100,
          "social_attention": 24,
          "social_quality": 18,
          "social_semantics": 10,
          "market_quality": 4,
          "timing": 45,
      },
      "rank_score": 22,
      "recommended_decision": "discard",
  }
  ```

- [ ] **Step 3: Run focused tests**

  ```bash
  uv run pytest tests/unit/test_factor_snapshot.py -q
  ```
  Expected: PASS.

- [ ] **Step 4: Commit**

  ```bash
  git add src/parallax/domains/token_intel/scoring/factor_snapshot.py \
          src/parallax/domains/token_intel/scoring/__init__.py \
          tests/unit/test_factor_snapshot.py
  git commit -m "feat: build token factor snapshots"
  ```

## Task 3: Hard-Cut Token Radar Projection To Factor Snapshot

**Files:**

- Modify: `src/parallax/domains/token_intel/_constants.py`
- Modify: `src/parallax/domains/token_intel/services/token_radar_projection.py`
- Modify: `src/parallax/domains/token_intel/read_models/asset_flow_service.py`
- Test: `tests/test_token_radar_projection.py`
- Test: `tests/test_token_radar_apply_cross_section.py`
- Test: `tests/test_token_radar_idempotency.py`
- Test: `tests/test_token_radar_audit_cli.py`

- [ ] **Step 1: Write failing projection hard-cut tests**

  Update `tests/test_token_radar_projection.py`:

  ```python
  def test_token_radar_projection_uses_factor_snapshot_contract():
      assert TOKEN_RADAR_PROJECTION_VERSION == "token-radar-v9-factor-snapshot"
      assert PROJECTION_VERSION == TOKEN_RADAR_PROJECTION_VERSION
  ```

  Add:

  ```python
  def test_project_group_outputs_factor_snapshot_not_score_contract():
      row = source_row("event-bov", received_at_ms=1_777_800_000_000)
      row["target_type"] = "Asset"
      row["target_id"] = "asset:bsc:0x1"
      row["asset_symbol"] = "BOV"
      row["asset_chain_id"] = "56"
      row["asset_address"] = "0x1"
      row["market_status"] = "fresh"
      row["market_market_cap_usd"] = 12087.0
      row["market_liquidity_usd"] = 6553.0
      row["market_holders"] = 46

      projected = _project_group([row], now_ms=1_777_800_060_000, window="1h", scope="all")

      assert projected is not None
      assert projected["factor_snapshot_json"]["schema_version"] == "token_factor_snapshot_v1"
      assert projected["factor_snapshot_json"]["hard_gates"]["eligible_for_high_alert"] is False
      assert projected["score_json"] == {}
      assert projected["attention_json"] == {}
      assert projected["market_json"] == {}
      assert projected["price_json"] == {}
  ```

  The empty old JSON asserts are intentional: physical DB columns can exist, but current projection must not write old runtime payloads.

- [ ] **Step 2: Update constants**

  In `_constants.py`:

  ```python
  TOKEN_RADAR_PROJECTION_VERSION = "token-radar-v9-factor-snapshot"
  TOKEN_RADAR_FACTOR_FAMILIES = (
      "identity",
      "social_attention",
      "social_quality",
      "social_semantics",
      "market_quality",
      "timing",
  )
  ```

  Remove exports that imply current runtime depends on `TOKEN_RADAR_SCORE_COMPONENTS`.

- [ ] **Step 3: Update projection row assembly**

  In `_project_group()`:

  - Build `features = build_radar_features(window_rows=window_rows, context_rows=rows, previous_rows=previous_rows, now_ms=now_ms, window_ms=window_ms, total_window_events=total_window_events)` as now.
  - Build existing market dict using `_market(window_rows, now_ms=now_ms)` as now.
  - Build `factor_snapshot = build_token_factor_snapshot(target=target, attention=features.attention, social_quality={**features.quality, **features.propagation}, social_semantics=_social_semantics(window_rows), market=market, timing=features.timing, source_event_ids=event_ids, computed_at_ms=now_ms)`.
  - Set:

    ```python
    row["factor_snapshot_json"] = factor_snapshot
    row["factor_version"] = factor_snapshot["schema_version"]
    row["decision"] = factor_snapshot["composite"]["recommended_decision"]
    row["data_health_json"] = {
        "factor_snapshot": "ready",
        "identity": factor_snapshot["families"]["identity"]["data_health"],
        "market": factor_snapshot["families"]["market_quality"]["data_health"],
    }
    row["attention_json"] = {}
    row["market_json"] = {}
    row["price_json"] = {}
    row["score_json"] = {}
    ```

- [ ] **Step 4: Update cross-section ranking**

  `_apply_cross_section()` reads rank score from:

  ```python
  factor_snapshot = row.get("factor_snapshot_json") or {}
  rank_score = ((factor_snapshot.get("composite") or {}).get("rank_score"))
  ```

  It writes cross-section output back into:

  ```python
  row["factor_snapshot_json"]["normalization"] = {
      "cross_section_rank": ranks.get(target_id),
      "cohort": {
          "in_cohort": target_id in cohort,
          "size": len(cohort),
          "definition_version": COHORT_DEFINITION_VERSION,
          "normalizer_version": NORMALIZER_VERSION,
          **cohort_metadata.get(target_id, {}),
      },
  }
  ```

- [ ] **Step 5: Update rank key**

  `_rank_key()` uses:

  ```python
  snapshot = row.get("factor_snapshot_json") if isinstance(row.get("factor_snapshot_json"), dict) else {}
  composite = snapshot.get("composite") if isinstance(snapshot.get("composite"), dict) else {}
  attention = ((snapshot.get("families") or {}).get("social_attention") or {}).get("facts") or {}
  ```

  Sort by decision priority, `rank_score`, and latest seen timestamp from factor snapshot.

- [ ] **Step 6: Update asset flow read model**

  `AssetFlowService` returns `factor_snapshot` and derived minimal `attention/target/market` from it. It must not read `score_json` as fallback.

- [ ] **Step 7: Run focused tests**

  ```bash
  uv run pytest tests/test_token_radar_projection.py tests/test_token_radar_apply_cross_section.py tests/test_token_radar_idempotency.py tests/test_token_radar_audit_cli.py -q
  ```
  Expected: PASS.

- [ ] **Step 8: Commit**

  ```bash
  git add src/parallax/domains/token_intel/_constants.py \
          src/parallax/domains/token_intel/services/token_radar_projection.py \
          src/parallax/domains/token_intel/read_models/asset_flow_service.py \
          tests/test_token_radar_projection.py tests/test_token_radar_apply_cross_section.py \
          tests/test_token_radar_idempotency.py tests/test_token_radar_audit_cli.py
  git commit -m "feat: hard cut token radar to factor snapshots"
  ```

## Task 3A: Add Market Freshness Demand To Stop Hot-Target Starvation

**Files:**

- Create: `src/parallax/domains/asset_market/services/market_freshness_demand.py`
- Modify: `src/parallax/domains/asset_market/services/asset_market_sync.py`
- Modify: `src/parallax/domains/asset_market/runtime/asset_market_sync_worker.py`
- Modify: `src/parallax/domains/asset_market/repositories/registry_repository.py`
- Modify: `src/parallax/platform/config/settings.py`
- Test: `tests/test_market_freshness_demand.py`
- Test: `tests/test_asset_market_sync.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write failing pure freshness-demand tests**

  Create `tests/test_market_freshness_demand.py`:

  ```python
  from parallax.domains.asset_market.services.market_freshness_demand import (
      classify_market_refresh_candidate,
      prioritize_market_refresh_candidates,
  )


  def test_hot_target_without_price_is_top_priority():
      rows = [
          {
              "asset_id": "warm-old",
              "latest_candidate_received_at_ms": 1_777_999_000_000,
              "candidate_event_count": 1,
              "latest_price_observed_at_ms": 1_777_990_000_000,
          },
          {
              "asset_id": "hot-missing",
              "latest_candidate_received_at_ms": 1_778_000_000_000,
              "candidate_event_count": 3,
              "latest_price_observed_at_ms": None,
          },
      ]

      ordered = prioritize_market_refresh_candidates(
          rows,
          now_ms=1_778_000_060_000,
          hot_since_ms=1_778_000_000_000 - 60 * 60 * 1000,
          hot_stale_after_ms=90_000,
          warm_stale_after_ms=300_000,
      )

      assert ordered[0]["asset_id"] == "hot-missing"
      assert ordered[0]["market_freshness_class"] == "hot"
      assert ordered[0]["market_freshness_status"] == "missing"
  ```

  Add:

  ```python
  def test_hot_target_over_alert_slo_beats_older_warm_target():
      rows = [
          {
              "asset_id": "warm-older",
              "latest_candidate_received_at_ms": 1_777_990_000_000,
              "candidate_event_count": 9,
              "latest_price_observed_at_ms": 1_777_990_000_000,
          },
          {
              "asset_id": "hot-stale",
              "latest_candidate_received_at_ms": 1_778_000_050_000,
              "candidate_event_count": 2,
              "latest_price_observed_at_ms": 1_777_999_900_000,
          },
      ]

      ordered = prioritize_market_refresh_candidates(
          rows,
          now_ms=1_778_000_060_000,
          hot_since_ms=1_778_000_000_000,
          hot_stale_after_ms=90_000,
          warm_stale_after_ms=300_000,
      )

      assert ordered[0]["asset_id"] == "hot-stale"
      assert ordered[0]["market_freshness_status"] == "stale"
      assert ordered[0]["market_freshness_lag_ms"] == 160_000
  ```

  Add:

  ```python
  def test_fresh_hot_target_is_not_selected_when_budget_is_needed_elsewhere():
      candidate = classify_market_refresh_candidate(
          {
              "asset_id": "fresh-hot",
              "latest_candidate_received_at_ms": 1_778_000_050_000,
              "candidate_event_count": 3,
              "latest_price_observed_at_ms": 1_778_000_040_000,
          },
          now_ms=1_778_000_060_000,
          hot_since_ms=1_778_000_000_000,
          hot_stale_after_ms=90_000,
          warm_stale_after_ms=300_000,
      )

      assert candidate["market_freshness_class"] == "hot"
      assert candidate["market_freshness_status"] == "fresh"
      assert candidate["market_refresh_required"] is False
  ```

- [ ] **Step 2: Implement pure demand helpers**

  Create `market_freshness_demand.py` with:

  ```python
  from __future__ import annotations

  from typing import Any

  HOT_MISSING_PRIORITY = 0
  HOT_STALE_PRIORITY = 1
  WARM_MISSING_PRIORITY = 2
  WARM_STALE_PRIORITY = 3
  FRESH_PRIORITY = 9


  def classify_market_refresh_candidate(
      row: dict[str, Any],
      *,
      now_ms: int,
      hot_since_ms: int,
      hot_stale_after_ms: int,
      warm_stale_after_ms: int,
  ) -> dict[str, Any]:
      latest_candidate_ms = _int_or_zero(row.get("latest_candidate_received_at_ms"))
      latest_price_ms = _int_or_none(row.get("latest_price_observed_at_ms"))
      is_hot = latest_candidate_ms >= int(hot_since_ms)
      stale_after_ms = int(hot_stale_after_ms if is_hot else warm_stale_after_ms)
      lag_ms = None if latest_price_ms is None else max(0, int(now_ms) - latest_price_ms)
      if latest_price_ms is None:
          status = "missing"
          required = True
      elif lag_ms is not None and lag_ms > stale_after_ms:
          status = "stale"
          required = True
      else:
          status = "fresh"
          required = False
      target_class = "hot" if is_hot else "warm"
      priority = _priority(target_class=target_class, status=status)
      return {
          **row,
          "market_freshness_class": target_class,
          "market_freshness_status": status,
          "market_freshness_lag_ms": lag_ms,
          "market_freshness_slo_ms": stale_after_ms,
          "market_refresh_required": required,
          "market_refresh_priority": priority,
      }


  def prioritize_market_refresh_candidates(
      rows: list[dict[str, Any]],
      *,
      now_ms: int,
      hot_since_ms: int,
      hot_stale_after_ms: int,
      warm_stale_after_ms: int,
  ) -> list[dict[str, Any]]:
      classified = [
          classify_market_refresh_candidate(
              row,
              now_ms=now_ms,
              hot_since_ms=hot_since_ms,
              hot_stale_after_ms=hot_stale_after_ms,
              warm_stale_after_ms=warm_stale_after_ms,
          )
          for row in rows
      ]
      required = [row for row in classified if row["market_refresh_required"]]
      required.sort(
          key=lambda row: (
              int(row["market_refresh_priority"]),
              -_int_or_zero(row.get("candidate_event_count")),
              -_int_or_zero(row.get("latest_candidate_received_at_ms")),
              _int_or_zero(row.get("latest_price_observed_at_ms")),
              str(row.get("asset_id") or ""),
          )
      )
      return required


  def _priority(*, target_class: str, status: str) -> int:
      if target_class == "hot" and status == "missing":
          return HOT_MISSING_PRIORITY
      if target_class == "hot" and status == "stale":
          return HOT_STALE_PRIORITY
      if status == "missing":
          return WARM_MISSING_PRIORITY
      if status == "stale":
          return WARM_STALE_PRIORITY
      return FRESH_PRIORITY


  def _int_or_none(value: Any) -> int | None:
      if value is None:
          return None
      try:
          return int(value)
      except (TypeError, ValueError):
          return None


  def _int_or_zero(value: Any) -> int:
      parsed = _int_or_none(value)
      return parsed if parsed is not None else 0
  ```

- [ ] **Step 3: Write failing integration test for DEX refresh selection**

  In `tests/test_asset_market_sync.py`, add a fake registry row set where a hot stale SHIT/SATO-like target would previously rank behind many warm stale rows. Assert `sync_dex_prices()` requests the hot row first when `limit=1`.

  Test shape:

  ```python
  def test_sync_dex_prices_prioritizes_hot_stale_radar_candidate():
      registry = FakeRegistry(
          rows=[
              {
                  "asset_id": "warm-old",
                  "chain_id": "56",
                  "address": "0xwarm",
                  "identity_confidence": "provider_exact",
                  "latest_candidate_received_at_ms": 1_777_990_000_000,
                  "candidate_event_count": 10,
                  "latest_price_observed_at_ms": 1_777_990_000_000,
              },
              {
                  "asset_id": "hot-stale",
                  "chain_id": "56",
                  "address": "0xhot",
                  "identity_confidence": "provider_exact",
                  "latest_candidate_received_at_ms": 1_778_000_050_000,
                  "candidate_event_count": 2,
                  "latest_price_observed_at_ms": 1_777_999_900_000,
              },
          ]
      )

      result = sync_dex_prices(
          registry=registry,
          identity_evidence=FakeIdentityEvidence(),
          price_observations=FakePriceObservations(),
          dex_market=FakeDexMarket(),
          observed_at_ms=1_778_000_060_000,
          stale_after_ms=300_000,
          hot_stale_after_ms=90_000,
          warm_stale_after_ms=300_000,
          limit=1,
          radar_since_ms=1_777_900_000_000,
          hot_since_ms=1_778_000_000_000,
      )

      assert result["price_observations_written"] == 1
      assert registry.pricefeed_upserts[0]["address"] == "0xhot"
  ```

- [ ] **Step 4: Integrate demand ordering into asset market sync**

  Update `sync_dex_prices()` signature:

  ```python
  def sync_dex_prices(
      *,
      registry,
      identity_evidence,
      price_observations,
      dex_market,
      observed_at_ms: int,
      stale_after_ms: int,
      limit: int,
      radar_since_ms: int | None = None,
      hot_since_ms: int | None = None,
      hot_stale_after_ms: int | None = None,
      warm_stale_after_ms: int | None = None,
      refresh_universe: str = "radar_candidates",
  ) -> dict[str, Any]:
  ```

  After loading rows from `chain_assets_needing_radar_price_refresh()`, apply:

  ```python
  rows = prioritize_market_refresh_candidates(
      rows,
      now_ms=observed_at_ms,
      hot_since_ms=resolved_hot_since_ms,
      hot_stale_after_ms=hot_stale_after_ms or stale_after_ms,
      warm_stale_after_ms=warm_stale_after_ms or stale_after_ms,
  )[: max(0, int(limit))]
  ```

  Return counters:

  ```python
  "refresh_candidates_selected": len(rows),
  "refresh_candidates_hot": sum(1 for row in rows if row.get("market_freshness_class") == "hot"),
  "refresh_candidates_stale": sum(1 for row in rows if row.get("market_freshness_status") == "stale"),
  "refresh_candidates_missing": sum(1 for row in rows if row.get("market_freshness_status") == "missing"),
  ```

- [ ] **Step 5: Add settings for DEX freshness**

  Extend `OkxProviderConfig`:

  ```python
  dex_sync_interval_seconds: float = 30.0
  dex_price_hot_stale_seconds: float = 90.0
  dex_price_warm_stale_seconds: float = 300.0
  dex_price_refresh_limit: int = 160
  ```

  Add `tests/test_settings.py` assertions that these defaults parse and reject unknown keys because `extra="forbid"` remains active.

- [ ] **Step 6: Wire worker settings without coupling to CEX interval**

  Update `AssetMarketSyncWorker` constructor to accept:

  ```python
  dex_stale_after_ms: int = DEX_PRICE_STALE_MS
  dex_hot_stale_after_ms: int = 90 * 1000
  dex_warm_stale_after_ms: int = DEX_PRICE_STALE_MS
  dex_refresh_limit: int = DEX_PRICE_REFRESH_LIMIT
  ```

  `_sync_dex_with_refresh()` passes those values into `sync_dex_prices()`. App wiring should use `settings.providers.okx.dex_sync_interval_seconds` for DEX cadence if the worker is split, or the lower of CEX/DEX intervals if the worker remains single-loop. The plan preference is a single worker with separate provider-specific due checks to avoid adding a new worker.

- [ ] **Step 7: Run focused tests**

  ```bash
  uv run pytest tests/test_market_freshness_demand.py tests/test_asset_market_sync.py tests/test_settings.py -q
  ```
  Expected: PASS.

- [ ] **Step 8: Commit**

  ```bash
  git add src/parallax/domains/asset_market/services/market_freshness_demand.py \
          src/parallax/domains/asset_market/services/asset_market_sync.py \
          src/parallax/domains/asset_market/runtime/asset_market_sync_worker.py \
          src/parallax/domains/asset_market/repositories/registry_repository.py \
          src/parallax/platform/config/settings.py \
          tests/test_market_freshness_demand.py tests/test_asset_market_sync.py tests/test_settings.py
  git commit -m "feat: prioritize hot token market freshness"
  ```

## Task 4: Replace Pulse Thesis With Factor-Backed Recommendation

**Files:**

- Modify: `src/parallax/domains/pulse_lab/interfaces.py`
- Create: `src/parallax/domains/pulse_lab/types/pulse_recommendation.py`
- Modify: `src/parallax/integrations/openai_agents/pulse_thesis_agent_client.py`
- Test: `tests/test_pulse_recommendation.py`
- Test: `tests/test_pulse_thesis_agent_client.py`

- [ ] **Step 1: Write recommendation schema tests**

  Add:

  ```python
  def test_recommendation_requires_factor_backed_reasons():
      payload = {
          "schema_version": "pulse_recommendation_v1",
          "recommendation": "ignore",
          "summary_zh": "链上质量不足，不应高优先级推送。",
          "primary_reasons": [
              {
                  "factor_key": "market_quality.liquidity_usd",
                  "explanation_zh": "流动性低于高优先级地板。",
              }
          ],
          "upgrade_conditions": [
              {"factor_key": "market_quality.liquidity_usd", "operator": ">=", "value": 25000, "description_zh": "流动性恢复到最低观察地板。"}
          ],
          "invalidation_conditions": [
              {"factor_key": "social_quality.duplicate_text_share", "operator": ">=", "value": 0.5, "description_zh": "重复文本继续升高。"}
          ],
          "residual_risks": [
              {"factor_key": "market_quality.security_data", "description_zh": "安全字段未知。"}
          ],
          "evidence_event_ids": ["event-1"],
          "confidence": 0.82,
      }

      model = validate_pulse_recommendation_payload(payload, available_factor_keys={"market_quality.liquidity_usd", "social_quality.duplicate_text_share", "market_quality.security_data"}, input_source_event_ids={"event-1"})

      assert model.recommendation == "ignore"
  ```

  Add a failure test where `factor_key="made_up.factor"` raises `ValueError`.

- [ ] **Step 2: Update constants**

  In `interfaces.py`:

  ```python
  PULSE_VERSION = "signal-pulse-v3-factor-snapshot"
  PULSE_RECOMMENDATION_SCHEMA_VERSION = "pulse_recommendation_v1"
  PULSE_RECOMMENDATION_PROMPT_VERSION = "pulse-recommendation-agents-sdk-v1"
  PULSE_GATE_VERSION = "pulse-factor-gate-v1"
  ```

  Keep old constants only if tests/imports need historical references; current runtime must import recommendation constants.

- [ ] **Step 3: Implement recommendation model**

  `PulseRecommendationPayload` fields:

  ```python
  class PulseReason(BaseModel):
      factor_key: str
      explanation_zh: str

  class PulseCondition(BaseModel):
      factor_key: str
      operator: Literal[">=", ">", "<=", "<", "=="]
      value: float | int | str | bool
      description_zh: str

  class PulseResidualRisk(BaseModel):
      factor_key: str
      description_zh: str

  class PulseRecommendationPayload(BaseModel):
      model_config = ConfigDict(extra="forbid")

      schema_version: Literal["pulse_recommendation_v1"]
      recommendation: Literal["ignore", "watch", "research", "alert", "trade_candidate"]
      summary_zh: str
      primary_reasons: list[PulseReason]
      upgrade_conditions: list[PulseCondition]
      invalidation_conditions: list[PulseCondition]
      residual_risks: list[PulseResidualRisk]
      evidence_event_ids: list[str]
      confidence: float = Field(ge=0, le=1)
  ```

- [ ] **Step 4: Update Agents SDK client**

  The agent instructions must say:

  ```text
  You receive deterministic TokenFactorSnapshot and gate_result. Do not invent facts.
  Every primary reason, upgrade condition, invalidation condition, and residual risk must cite a factor_key present in available_factor_keys.
  Recommendation cannot upgrade beyond gate_result.max_recommendation.
  ```

  The input payload contains:

  ```python
  {
      "task": "write_pulse_recommendation_v1",
      "factor_snapshot": context["factor_snapshot"],
      "gate_result": context["gate_result"],
      "available_factor_keys": sorted(collect_factor_keys(context["factor_snapshot"])),
      "selected_posts": context.get("selected_posts", []),
  }
  ```

- [ ] **Step 5: Run focused tests**

  ```bash
  uv run pytest tests/test_pulse_recommendation.py tests/test_pulse_thesis_agent_client.py -q
  ```
  Expected: PASS after test updates.

- [ ] **Step 6: Commit**

  ```bash
  git add src/parallax/domains/pulse_lab/interfaces.py \
          src/parallax/domains/pulse_lab/types/pulse_recommendation.py \
          src/parallax/integrations/openai_agents/pulse_thesis_agent_client.py \
          tests/test_pulse_recommendation.py tests/test_pulse_thesis_agent_client.py
  git commit -m "feat: replace pulse thesis with factor recommendations"
  ```

## Task 5: Hard-Cut Pulse Worker And Gate To Factor Snapshot

**Files:**

- Modify: `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `src/parallax/domains/pulse_lab/services/pulse_candidate_gate.py`
- Modify: `src/parallax/domains/pulse_lab/services/pulse_timeline_context.py`
- Test: `tests/test_pulse_candidate_gate.py`
- Test: `tests/test_pulse_candidate_worker.py`
- Test: `tests/test_pulse_timeline_context.py`

- [ ] **Step 1: Write gate tests**

  Add:

  ```python
  def test_factor_gate_blocks_low_liquidity_high_alert():
      result = gate_pulse_candidate_from_factor_snapshot(
          factor_snapshot={
              "schema_version": "token_factor_snapshot_v1",
              "subject": {"target_type": "Asset", "target_id": "asset:bsc:0x1", "symbol": "BOV"},
              "hard_gates": {
                  "eligible_for_high_alert": False,
                  "blocked_reasons": ["liquidity_below_high_alert_floor", "holders_below_high_alert_floor"],
              },
              "composite": {"rank_score": 19, "recommended_decision": "discard"},
              "families": {},
          }
      )

      assert result.pulse_status in {"blocked_low_information", "risk_rejected_high_info"}
      assert result.candidate_score <= 40
      assert "liquidity_below_high_alert_floor" in result.risk_reasons
  ```

  Add:

  ```python
  def test_source_seed_without_factor_snapshot_is_not_displayable_high_alert():
      assert gate_source_seed_without_target().pulse_status == "blocked_low_information"
  ```

- [ ] **Step 2: Change gate function signature**

  Replace current thesis/radar/market/timeline gate entry with:

  ```python
  def gate_pulse_candidate_from_factor_snapshot(
      *,
      factor_snapshot: dict[str, Any],
      thresholds: PulseGateThresholds | None = None,
  ) -> PulseGateResult:
      composite = factor_snapshot.get("composite") if isinstance(factor_snapshot.get("composite"), dict) else {}
      hard_gates = factor_snapshot.get("hard_gates") if isinstance(factor_snapshot.get("hard_gates"), dict) else {}
      blocked_reasons = [str(item) for item in hard_gates.get("blocked_reasons", []) if str(item)]
      rank_score = safe_float(composite.get("rank_score"))
      eligible_for_high_alert = bool(hard_gates.get("eligible_for_high_alert"))
      candidate_score = clamp_score(rank_score)
      if blocked_reasons:
          pulse_status = "risk_rejected_high_info" if candidate_score >= 30 else "blocked_low_information"
      elif eligible_for_high_alert and candidate_score >= 72:
          pulse_status = "trade_candidate"
      elif eligible_for_high_alert and candidate_score >= 45:
          pulse_status = "token_watch"
      else:
          pulse_status = "blocked_low_information"
      return PulseGateResult(
          pulse_status=pulse_status,
          verdict=pulse_status,
          candidate_score=float(candidate_score),
          score_band=_score_band_from_candidate_score(candidate_score, pulse_status),
          gate_reasons=blocked_reasons if blocked_reasons else ["factor_snapshot_passed_high_alert_gate"],
          risk_reasons=blocked_reasons,
          hard_risks=blocked_reasons,
      )
  ```

  `PulseGateResult` remains the deterministic persistence object, but `gate_reasons` and `risk_reasons` come from factor hard gates and factor risk flags.

- [ ] **Step 3: Update worker context**

  `PulseCandidateContext` fields:

  ```python
  factor_snapshot: dict[str, Any]
  selected_posts: list[dict[str, Any]]
  gate_result: dict[str, Any] | None
  ```

  Remove current runtime fields:

  ```python
  radar_score: dict[str, Any]
  market_context: dict[str, Any]
  timeline_context: dict[str, Any]
  ```

  `_asset_context()` reads `row["factor_snapshot_json"]`; if missing or empty, returns `None` and increments skipped. This is the no-fallback enforcement point.

- [ ] **Step 4: Gate before agent**

  In `_run_job()`:

  ```python
  gate = self.gate_func(factor_snapshot=context.factor_snapshot, thresholds=self.gate_thresholds)
  agent_context = {
      "factor_snapshot": context.factor_snapshot,
      "gate_result": gate.to_json(),
      "selected_posts": context.selected_posts,
  }
  result = await self.thesis_client.write_thesis(context=agent_context, run_id=run_id, job=job)
  recommendation = result.payload
  ```

  The recommendation may explain but cannot change `gate.pulse_status`, `gate.candidate_score`, or `gate.score_band`.

- [ ] **Step 5: Persist new Pulse candidate contract**

  `upsert_candidate()` call passes:

  ```python
  factor_snapshot_json=context.factor_snapshot,
  gate_json=gate.to_json(),
  agent_recommendation_json=_payload_dict(recommendation),
  ```

  It does not pass `radar_score_json` or `market_context_json`.

- [ ] **Step 6: Run focused tests**

  ```bash
  uv run pytest tests/test_pulse_candidate_gate.py tests/test_pulse_candidate_worker.py tests/test_pulse_timeline_context.py -q
  ```
  Expected: PASS after test updates.

- [ ] **Step 7: Commit**

  ```bash
  git add src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py \
          src/parallax/domains/pulse_lab/services/pulse_candidate_gate.py \
          src/parallax/domains/pulse_lab/services/pulse_timeline_context.py \
          tests/test_pulse_candidate_gate.py tests/test_pulse_candidate_worker.py tests/test_pulse_timeline_context.py
  git commit -m "feat: gate pulse candidates from factor snapshots"
  ```

## Task 6: Hard-Cut Signal Pulse Read Model And Notifications

**Files:**

- Modify: `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py`
- Modify: `src/parallax/domains/notifications/services/notification_rules.py`
- Test: `tests/test_signal_pulse_service.py`
- Test: `tests/test_notification_rules.py`

- [ ] **Step 1: Write read-model no-fallback tests**

  In `tests/test_signal_pulse_service.py`, create a pulse row with empty `factor_snapshot_json` and non-empty old `radar_score_json`. Assert the service excludes it or marks it invalid; it must not expose old radar facts.

  Expected assertion:

  ```python
  assert "radar_score_json" not in item
  assert "market_context_json" not in item
  assert item["factor_snapshot"]["schema_version"] == "token_factor_snapshot_v1"
  ```

- [ ] **Step 2: Write notification severity tests**

  In `tests/test_notification_rules.py`, add:

  ```python
  def test_signal_pulse_low_liquidity_factor_snapshot_cannot_emit_high_notification():
      row = pulse_candidate_row(
          pulse_status="token_watch",
          factor_snapshot_json={
              "schema_version": "token_factor_snapshot_v1",
              "subject": {"symbol": "BOV", "target_type": "Asset"},
              "hard_gates": {
                  "eligible_for_high_alert": False,
                  "blocked_reasons": ["liquidity_below_high_alert_floor"],
              },
              "families": {
                  "market_quality": {"facts": {"liquidity_usd": 6553, "holders": 46, "market_cap_usd": 12087}},
                  "social_attention": {"facts": {"mentions_1h": 3, "unique_authors": 2}},
              },
          },
      )

      candidates = engine_candidates_for(row)

      assert candidates == []
  ```

  Add a positive test where `eligible_for_high_alert=True` and status `token_watch` can emit `high`.

- [ ] **Step 3: Update SignalPulseService output**

  Output item fields:

  ```python
  {
      "candidate_id": row.get("candidate_id"),
      "subject": factor_snapshot["subject"],
      "pulse_status": row.get("pulse_status"),
      "candidate_score": row.get("candidate_score"),
      "score_band": row.get("score_band"),
      "factor_snapshot": factor_snapshot,
      "agent_recommendation": agent_recommendation_json,
      "gate": gate_json,
      "fact_card": {
          "market_cap_usd": _factor_raw(factor_snapshot, "market_quality", "market_cap_usd"),
          "liquidity_usd": _factor_raw(factor_snapshot, "market_quality", "liquidity_usd"),
          "holders": _factor_raw(factor_snapshot, "market_quality", "holders"),
          "volume_24h_usd": _factor_raw(factor_snapshot, "market_quality", "volume_24h_usd"),
          "market_status": _factor_raw(factor_snapshot, "market_quality", "market_status"),
          "mentions_1h": _factor_raw(factor_snapshot, "social_attention", "mentions_1h"),
          "unique_authors": _factor_raw(factor_snapshot, "social_quality", "independent_authors"),
          "watched_mentions": _factor_raw(factor_snapshot, "social_attention", "watched_mentions"),
          "eligible_for_high_alert": gate_json.get("eligible_for_high_alert"),
          "blocked_reasons": gate_json.get("blocked_reasons") or [],
      },
  }
  ```

  Remove current output keys `radar_score_json` and `market_context_json`.

- [ ] **Step 4: Update notification rules**

  Signal Pulse candidate selection:

  - Requires non-empty `factor_snapshot_json`.
  - Drops source seed candidates without resolved target from high/critical channels.
  - Maps severity from `gate_json` and `factor_snapshot["hard_gates"]["eligible_for_high_alert"]`.
  - Does not map `token_watch` to high unless the factor snapshot allows high alert.

  Fact-first body format:

  ```markdown
  ## $BOV Signal Pulse

  - **Status:** blocked
  - **Gate:** liquidity below high-alert floor, holders below high-alert floor
  - **Market:** mcap $12.1k · liq $6.6k · holders 46 · fresh
  - **Social:** 3 mentions · 2 authors · watched 0

  链上质量不足，不应高优先级推送。
  ```

- [ ] **Step 5: Run focused tests**

  ```bash
  uv run pytest tests/test_signal_pulse_service.py tests/test_notification_rules.py -q
  ```
  Expected: PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py \
          src/parallax/domains/notifications/services/notification_rules.py \
          tests/test_signal_pulse_service.py tests/test_notification_rules.py
  git commit -m "feat: render signal pulse from factor snapshots"
  ```

## Task 7: Hard-Cut Frontend Types And Views

**Files:**

- Modify: `web/src/api/types.ts`
- Modify: `web/src/components/SignalLabPulse.tsx`
- Modify: `web/src/components/PulseDetailPage.tsx`
- Modify: `web/src/components/SignalLabInspector.tsx`
- Modify: `web/src/components/SignalLabWorkbench.tsx`
- Modify: `web/src/lib/venue.ts`
- Test: `web/src/components/SignalLabPulse.test.tsx`
- Test: `web/src/components/__tests__/PulseDetailPage.routing.test.tsx`
- Test: `web/src/api/__tests__/useSignalPulseQueries.test.tsx`

- [ ] **Step 1: Update TypeScript types**

  Add:

  ```ts
  export type FactorPoint = {
    family: string;
    key: string;
    raw_value?: unknown;
    score?: number | null;
    confidence?: number | null;
    data_health?: string | null;
    freshness_ms?: number | null;
    source_refs?: string[];
    risk_flags?: string[];
    hard_gate?: string | null;
  };

  export type TokenFactorSnapshot = {
    schema_version: "token_factor_snapshot_v1" | string;
    subject: {
      target_type?: string | null;
      target_id?: string | null;
      symbol?: string | null;
      chain?: string | null;
      address?: string | null;
    };
    families: Record<string, {
      score?: number | null;
      facts?: Record<string, unknown>;
      factors?: Record<string, FactorPoint>;
      data_health?: string | null;
    }>;
    hard_gates: {
      eligible_for_high_alert: boolean;
      blocked_reasons: string[];
    };
    composite: {
      rank_score?: number | null;
      recommended_decision?: string | null;
    };
  };

  export type PulseAgentRecommendation = {
    schema_version: "pulse_recommendation_v1" | string;
    recommendation: "ignore" | "watch" | "research" | "alert" | "trade_candidate" | string;
    summary_zh?: string | null;
    primary_reasons: Array<{ factor_key: string; explanation_zh: string }>;
    upgrade_conditions: Array<{ factor_key: string; operator: string; value: unknown; description_zh: string }>;
    invalidation_conditions: Array<{ factor_key: string; operator: string; value: unknown; description_zh: string }>;
    residual_risks: Array<{ factor_key: string; description_zh: string }>;
  };
  ```

  `SignalPulseItem` removes `radar_score_json`, `market_context_json`, `thesis_json`, `confirmation_triggers_zh`, `top_risks` as required display fields and adds:

  ```ts
  factor_snapshot: TokenFactorSnapshot;
  agent_recommendation: PulseAgentRecommendation;
  gate: Record<string, unknown>;
  fact_card: Record<string, unknown>;
  ```

- [ ] **Step 2: Update list row rendering**

  `SignalLabPulse.tsx` row order:

  1. status badge.
  2. title.
  3. fact meta: market cap/liquidity/holders or volume, mentions/authors, gate.
  4. recommendation summary.
  5. gate score/band.

  It must not read `item.radar_score_json` or `item.market_context_json`.

- [ ] **Step 3: Update detail page**

  `PulseDetailPage.tsx` sections:

  - Fact Card
  - Hard Gates
  - Factor Families
  - Agent Recommendation
  - Source Events

- [ ] **Step 4: Update venue links**

  `signalPulseVenueActions()` reads:

  ```ts
  const subject = item.factor_snapshot?.subject;
  const chain = subject?.chain;
  const address = subject?.address;
  const symbol = subject?.symbol ?? item.symbol;
  ```

- [ ] **Step 5: Run frontend tests**

  ```bash
  npm test -- --run web/src/components/SignalLabPulse.test.tsx web/src/components/__tests__/PulseDetailPage.routing.test.tsx web/src/api/__tests__/useSignalPulseQueries.test.tsx
  npm run build
  ```
  Expected: PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add web/src/api/types.ts web/src/components/SignalLabPulse.tsx web/src/components/PulseDetailPage.tsx \
          web/src/components/SignalLabInspector.tsx web/src/components/SignalLabWorkbench.tsx web/src/lib/venue.ts \
          web/src/components/SignalLabPulse.test.tsx web/src/components/__tests__/PulseDetailPage.routing.test.tsx \
          web/src/api/__tests__/useSignalPulseQueries.test.tsx
  git commit -m "feat: show signal pulse factor facts"
  ```

## Task 8: Delete Old Runtime Paths And Add No-Fallback Guards

**Files:**

- Modify: all files touched by Tasks 3-7
- Test: `tests/architecture/test_no_factor_snapshot_fallback.py`

- [ ] **Step 1: Add grep-based no-fallback regression test**

  Create `tests/architecture/test_no_factor_snapshot_fallback.py`:

  ```python
  from pathlib import Path

  ROOT = Path(__file__).resolve().parents[1]

  RUNTIME_FILES = [
      ROOT / "src/parallax/domains/token_intel/services/token_radar_projection.py",
      ROOT / "src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py",
      ROOT / "src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py",
      ROOT / "src/parallax/domains/notifications/services/notification_rules.py",
  ]

  FORBIDDEN_PATTERNS = [
      "factor_snapshot_json\") or _mapping(row.get(\"score_json",
      "factor_snapshot_json') or",
      "radar_score_json=context",
      "market_context_json=context",
      "radar_score_json\": _dict",
      "market_context_json\": _dict",
  ]

  def test_current_runtime_has_no_factor_snapshot_fallbacks():
      combined = "\n".join(path.read_text() for path in RUNTIME_FILES)
      for pattern in FORBIDDEN_PATTERNS:
          assert pattern not in combined
  ```

- [ ] **Step 2: Remove obsolete imports and helpers**

  Remove or stop using:

  - `_radar_score(row)` in `pulse_candidate_worker.py`
  - `_market_context(row)` as Pulse agent/gate input
  - thesis field formatting in Signal Pulse notification body
  - Signal Pulse read model output keys `radar_score_json` and `market_context_json`

- [ ] **Step 3: Update docs generated by implementation**

  Update:

  - `src/parallax/domains/token_intel/ARCHITECTURE.md`
  - `docs/ARCHITECTURE.md`
  - `docs/CONTRACTS.md`

  Required statement:

  ```markdown
  Token Radar current runtime explanation source is `factor_snapshot_json`.
  Legacy score-centered JSON fields may exist historically but are not runtime fallback sources.
  Signal Lab Pulse recommendations consume factor snapshots and deterministic gates.
  ```

- [ ] **Step 4: Run grep**

  ```bash
  rg -n "radar_score_json|market_context_json|confirmation_triggers_zh|top_risks|thesis_json|score_json.*fallback|factor_snapshot.*or.*score_json" src web tests
  ```

  Expected: remaining hits are historical migrations, old test fixture names intentionally changed in this plan, or non-runtime documentation explaining the hard cut. No current runtime path may use old fields as fallback.

- [ ] **Step 5: Run focused test**

  ```bash
  uv run pytest tests/architecture/test_no_factor_snapshot_fallback.py -q
  ```
  Expected: PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add src/parallax/domains/token_intel/ARCHITECTURE.md docs/ARCHITECTURE.md docs/CONTRACTS.md \
          tests/architecture/test_no_factor_snapshot_fallback.py
  git commit -m "chore: remove factor snapshot fallback paths"
  ```

## Task 9: Live DB Verification And Noise-Reduction Measurement

**Files:**

- Create: `docs/superpowers/plans/active/2026-05-10-token-radar-factor-snapshot-hard-cut-verification.md`
- No source changes unless verification finds a bug.

- [ ] **Step 1: Apply migration in local Docker DB**

  ```bash
  uv run alembic upgrade head
  ```
  Expected: revision `20260510_0022_token_radar_factor_snapshot_hard_cut` applied.

- [ ] **Step 2: Rebuild Token Radar projection**

  Use the project CLI command already used for Token Radar rebuilds. If command spelling differs, inspect `uv run parallax --help` and record the exact command in verification.

  Expected DB check:

  ```sql
  SELECT projection_version, COUNT(*)
  FROM token_radar_rows
  WHERE projection_version = 'token-radar-v9-factor-snapshot'
  GROUP BY projection_version;
  ```

  Count must be greater than 0.

- [ ] **Step 3: Verify no current row lacks factor snapshot**

  ```sql
  WITH latest AS (
    SELECT MAX(computed_at_ms) AS computed_at_ms
    FROM token_radar_rows
    WHERE projection_version = 'token-radar-v9-factor-snapshot'
      AND "window" = '1h'
      AND scope = 'all'
  )
  SELECT COUNT(*) AS missing_factor_snapshot
  FROM token_radar_rows, latest
  WHERE projection_version = 'token-radar-v9-factor-snapshot'
    AND "window" = '1h'
    AND scope = 'all'
    AND token_radar_rows.computed_at_ms = latest.computed_at_ms
    AND factor_snapshot_json = '{}'::jsonb;
  ```

  Expected: `0`.

- [ ] **Step 4: Verify BOV-style weak DEX rows are blocked**

  Query latest rows for any DEX Asset where holders `< 100` or liquidity `< 25000`:

  ```sql
  SELECT
    target_id,
    factor_snapshot_json #>> '{subject,symbol}' AS symbol,
    factor_snapshot_json #>> '{hard_gates,eligible_for_high_alert}' AS eligible_for_high_alert,
    factor_snapshot_json #> '{hard_gates,blocked_reasons}' AS blocked_reasons
  FROM token_radar_rows
  WHERE projection_version = 'token-radar-v9-factor-snapshot'
    AND "window" = '1h'
    AND scope = 'all'
    AND target_type = 'Asset'
    AND (
      ((factor_snapshot_json #>> '{families,market_quality,facts,holders}')::numeric < 100)
      OR ((factor_snapshot_json #>> '{families,market_quality,facts,liquidity_usd}')::numeric < 25000)
    )
  LIMIT 20;
  ```

  Expected: every returned row has `eligible_for_high_alert = false`.

- [ ] **Step 5: Run Pulse worker once**

  Run the existing app/worker command or call the focused runtime function from `uv run python` in a controlled transaction-free local environment. Record:

  - jobs scanned
  - jobs enqueued
  - jobs processed
  - candidates written
  - candidates skipped for missing factor snapshot

- [ ] **Step 6: Measure before/after Signal Pulse notification volume**

  Before/after comparison query:

  ```sql
  SELECT
    rule_id,
    severity,
    COUNT(*)
  FROM notifications
  WHERE updated_at_ms >= (extract(epoch from now()) * 1000)::bigint - 3600000
  GROUP BY 1, 2
  ORDER BY 1, 2;
  ```

  Record the previous baseline from the spec discussion: recent sample had 5 high and 4 warning Signal Pulse notifications in one hour. After hard cut, high-severity weak DEX cases should be lower. The verification artifact must report actual counts.

- [ ] **Step 7: Write verification artifact**

  Include:

  - migration revision observed
  - commands run
  - SQL outputs
  - noisy sample outcome for BOV-style conditions
  - notification count comparison
  - any skipped flows and why

- [ ] **Step 8: Commit verification**

  ```bash
  git add docs/superpowers/plans/active/2026-05-10-token-radar-factor-snapshot-hard-cut-verification.md
  git commit -m "docs: verify factor snapshot hard cut"
  ```

## Rollout Order

1. Merge storage migration and pure factor snapshot builder.
2. Merge market freshness demand ordering so hot targets stop starving behind warm/cold refreshes.
3. Merge Token Radar projection hard cut and bump projection version.
4. Merge Pulse gate/agent/repository hard cut and bump Pulse version.
5. Merge Signal Pulse notification/read model hard cut.
6. Merge frontend contract changes.
7. Apply Alembic migration.
8. Rebuild Token Radar projection.
9. Run Pulse worker once locally and verify factor snapshot candidates.
10. Run full backend/frontend verification.

## Rollback

This is intentionally a hard cut, so runtime rollback is branch-level or deploy-level rollback, not field-level fallback.

- If migration was applied but code has not deployed: keeping new columns is safe; they are additive storage columns.
- If code deployed and projection fails: roll back the deploy to the previous commit and keep DB columns in place. Do not add fallback adapters.
- If Pulse notifications regress: pause the `signal_pulse_candidate` notification rule in config, fix factor snapshot/gate logic, and redeploy.
- If frontend breaks on the new contract: roll back frontend with backend together. Do not reintroduce old `radar_score_json` or `market_context_json` reads.

## Acceptance Test Commands

- AC1, AC2:
  ```bash
  uv run pytest tests/unit/test_factor_snapshot.py -q
  ```
- AC3, AC4:
  ```bash
  uv run pytest tests/test_market_freshness_demand.py tests/test_asset_market_sync.py tests/test_pulse_candidate_gate.py tests/test_pulse_candidate_worker.py -q
  ```
- AC5:
  ```bash
  uv run pytest tests/test_signal_pulse_service.py tests/test_notification_rules.py -q
  npm test -- --run web/src/components/SignalLabPulse.test.tsx
  ```
- AC6:
  ```bash
  uv run pytest tests/test_pulse_recommendation.py tests/test_pulse_thesis_agent_client.py -q
  ```
- AC7, AC8:
  ```bash
  uv run pytest tests/test_token_radar_projection.py tests/test_token_radar_apply_cross_section.py tests/test_token_radar_idempotency.py -q
  ```
- AC9:
  ```bash
  uv run pytest tests/architecture/test_no_factor_snapshot_fallback.py -q
  rg -n "factor_snapshot.*or.*score_json|radar_score_json=context|market_context_json=context" src web tests
  ```
  Expected grep output: no current runtime hits.

## Final Verification Gate

Before declaring complete:

```bash
uv run ruff check src tests
uv run pytest -q
uv run python -m compileall src tests
npm test -- --run
npm run build
```

Also run the live DB verification in Task 9 and write the verification artifact.

## Spec Coverage Self-Review

- G1 covered by Tasks 1-3.
- G2 covered by Tasks 2, 3A, and Task 9 SQL checks.
- G3 covered by Task 3A and Task 9 SQL checks.
- G4 covered by Tasks 4-5.
- G5 covered by Tasks 6-7.
- G6 covered by Tasks 1, 3, 5, 6, 8.
- Hard-cut no-fallback requirement covered by Task 8 and AC9.
- Expected optimization effect measurement covered by Task 9.
