# Token Factor Engineering Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current presence-heavy token factor snapshot with an evaluable, cross-section-aware factor contract where identity, market freshness, duplicate risk, and data availability are gates or data-health facts rather than fake alpha.

**Architecture:** Keep the existing Token Radar projection, Signal Labs pulse, PostgreSQL, CLI, and React app surfaces. Hard-cut the runtime contract from `token_factor_snapshot_v1` to one current v2 shape, then update every producer, reader, audit, and frontend adapter that consumes it. No new providers, queues, LLM labels, training loop, or recreated legacy signal snapshot tables.

**Tech Stack:** Python 3.13, psycopg/PostgreSQL, Alembic, argparse CLI, pytest with `tests/unit` / `tests/integration` / `tests/architecture` / `tests/contract` markers, React/TypeScript/Vitest under `web/`.

---

## Current Main Resync

This plan was refreshed against local `main` on 2026-05-11 after the tests-and-lint/frontend refactor landed. Important deltas from the earlier plan:

- Local `main` is ahead of `origin/main` by three commits and is the base for this work.
- Coding happens in `.worktrees/token-factor-engineering-hard-cut` on branch `codex/token-factor-engineering-hard-cut`.
- Backend tests are now split. Most old `tests/test_*.py` paths moved to `tests/unit/` or `tests/integration/`. The root exceptions still present are `tests/unit/test_factor_snapshot.py` and `tests/architecture/test_no_factor_snapshot_fallback.py`.
- Frontend commands must run from `web/`: `cd web && npm run test`, `cd web && npm run typecheck`, `cd web && npm run build`, `cd web && npm run lint`.
- Completion evidence is `make check-all`; it wraps lint, typecheck, unit/architecture/contract, integration/e2e, and coverage.
- `web/src/lib/tokenRadar.ts` is the frontend Token Radar adapter and is more important than `ScoreLedger.tsx` for the v2 hard cut.
- `src/parallax/domains/token_intel/read_models/asset_flow_service.py` currently fabricates `current_market` from factor snapshot `market_quality`; v2 must instead use the existing current-market read model data.
- `src/parallax/domains/pulse_lab/repositories/pulse_repository.py` has SQL JSON paths into `families.market_quality`; it must be updated too.
- During merge to current `main`, Alembic `20260511_0025` is owned by token-radar production read models, so the factor diagnostics migration is `20260511_0026` with `down_revision = "20260511_0025"`.

## Source Spec

- Spec: `docs/superpowers/specs/active/2026-05-11-token-factor-engineering-hard-cut-cn.md`
- Branch: `codex/token-factor-engineering-hard-cut`
- Worktree: `.worktrees/token-factor-engineering-hard-cut`

## Scope

In:
- New current factor snapshot version only: `token_factor_snapshot_v2_alpha_gated`.
- Existing data only: `events`, `account_profiles`, `social_event_extractions`, `price_observations`, `token_radar_rows`, `token_score_evaluations`, and current-market read models already backed by `price_observations`.
- Token Radar projection and `/api/token-radar` latest runtime rows.
- Signal Labs pulse candidates, recommendation context, notification severity/body, and pulse repository health SQL.
- Frontend Token Radar and Signal Lab adapters and tests.
- Historical `token_radar_rows` retention for forward-return settlement.
- Bucket summaries and diagnostics in existing `token_score_evaluations`.

Out:
- New market/social providers.
- New LLM calls or model training.
- Recreating `token_signal_snapshots` or `token_signal_outcomes`.
- Runtime fallback that accepts v1 `hard_gates`, `families.identity`, `families.market_quality`, `families.social_attention`, `families.social_quality`, or `families.timing`.

## Target Snapshot Contract

Runtime rows must persist this shape under `token_radar_rows.factor_snapshot_json`:

```json
{
  "schema_version": "token_factor_snapshot_v2_alpha_gated",
  "subject": {
    "target_type": "Asset",
    "target_id": "asset:...",
    "symbol": "BUTTCOIN",
    "target_market_type": "dex",
    "chain": "solana",
    "address": "...",
    "pricefeed_id": "..."
  },
  "gates": {
    "eligible_for_high_alert": false,
    "max_decision": "watch",
    "blocked_reasons": ["insufficient_independent_social_sources"],
    "risk_reasons": ["thin_author_set"]
  },
  "data_health": {
    "identity": "ready",
    "market": "ready",
    "social": "ready",
    "alpha": "ready"
  },
  "families": {
    "attention_heat": {
      "raw_score": 42,
      "score": 73,
      "weight": 0.35,
      "data_health": "ready",
      "facts": {},
      "factors": {}
    },
    "diffusion_quality": {
      "raw_score": 31,
      "score": 58,
      "weight": 0.30,
      "data_health": "ready",
      "facts": {},
      "factors": {}
    },
    "semantic_quality": {
      "raw_score": 0,
      "score": 0,
      "weight": 0.25,
      "data_health": "missing",
      "facts": {},
      "factors": {}
    },
    "timing_response": {
      "raw_score": 0,
      "score": 0,
      "weight": 0.10,
      "data_health": "partial",
      "facts": {
        "social_signal_start_ms": 1778490000000
      },
      "factors": {}
    }
  },
  "normalization": {
    "status": "ready",
    "cohort": {
      "in_cohort": true,
      "size": 12,
      "definition_version": "factor_cohort_v2",
      "normalizer_version": "cross_section_v2_factor_ranks"
    },
    "factor_ranks": {
      "attention_heat": 0.73,
      "diffusion_quality": 0.58,
      "semantic_quality": null,
      "timing_response": null
    },
    "alpha_rank": 0.67
  },
  "composite": {
    "raw_alpha_score": 42,
    "rank_score": 67,
    "family_scores": {
      "attention_heat": 73,
      "diffusion_quality": 58,
      "semantic_quality": 0,
      "timing_response": 0
    },
    "recommended_decision": "watch"
  },
  "provenance": {
    "source_event_ids": ["event-1"],
    "computed_at_ms": 1778490000000
  }
}
```

## Factor Rules

- Identity facts never score. Missing identity gates high alert and caps the decision surface.
- Market freshness, DEX holder/liquidity/market-cap floors, and CEX native market identity never score. They are gates and data-health facts.
- `social_signal_start_ms` is provenance/timing context only. Its presence must never create points.
- Duplicate text and top-author concentration are negative risk controls. A clean duplicate score may avoid a penalty, but must not create a standalone 100-point alpha family.
- Alpha families are social-first and sparse: `attention_heat`, `diffusion_quality`, `semantic_quality`, `timing_response`.
- Final `rank_score` uses cross-sectional factor ranks when the cohort is usable; otherwise it falls back to raw alpha with `normalization.status = "insufficient_cohort"`.
- High alert requires both alpha and gates. A high alpha score with blocked gates becomes `watch` or `discard`, never `high_alert`.

## Exact Files

Producer and scoring:
- Modify `src/parallax/domains/token_intel/_constants.py`.
- Modify `src/parallax/domains/token_intel/scoring/factor_snapshot.py`.
- Modify `src/parallax/domains/token_intel/scoring/token_radar_feature_builder.py`.
- Modify `src/parallax/domains/token_intel/scoring/diffusion_health.py` only for narrow input normalization if needed.
- Modify `src/parallax/domains/token_intel/scoring/cross_section_normalizer.py`.
- Modify `src/parallax/domains/token_intel/scoring/factor_cohort.py`.
- Modify `src/parallax/domains/token_intel/services/token_radar_projection.py`.

Read models and repositories:
- Modify `src/parallax/domains/token_intel/repositories/token_radar_repository.py`.
- Modify `src/parallax/domains/token_intel/read_models/asset_flow_service.py`.
- Modify `src/parallax/app/runtime/app.py`.
- Modify `src/parallax/app/surfaces/api/http.py`.
- Modify `src/parallax/app/surfaces/cli/main.py`.
- Modify `src/parallax/app/runtime/repository_session.py`.
- Modify `src/parallax/domains/asset_market/repositories/price_observation_repository.py`.
- Create `src/parallax/domains/token_intel/scoring/factor_diagnostics.py`.
- Create `src/parallax/domains/token_intel/repositories/token_factor_evaluation_repository.py`.
- Create `src/parallax/domains/token_intel/services/token_factor_evaluation.py`.
- Create `src/parallax/platform/db/alembic/versions/20260511_0026_token_factor_eval_diagnostics.py`.

Pulse and notifications:
- Modify `src/parallax/domains/pulse_lab/services/pulse_candidate_gate.py`.
- Modify `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`.
- Modify `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py`.
- Modify `src/parallax/domains/pulse_lab/repositories/pulse_repository.py`.
- Modify `src/parallax/domains/notifications/services/notification_rules.py`.
- Modify `src/parallax/domains/pulse_lab/types/pulse_recommendation.py` only if factor-key collection assumes v1 names.
- Modify `src/parallax/integrations/openai_agents/pulse_recommendation_agent_client.py` only if prompt/audit labels assume v1 names.

Frontend:
- Modify `web/src/api/types.ts`.
- Modify `web/src/lib/tokenRadar.ts`.
- Modify `web/src/lib/tokenRadar.test.ts`.
- Modify `web/src/lib/venue.ts`.
- Modify `web/src/lib/venue.test.ts`.
- Modify `web/src/components/SignalLabPulse.tsx`.
- Modify `web/src/components/SignalLabPulse.test.tsx`.
- Modify `web/src/components/SignalLabInspector.tsx`.
- Modify `web/src/components/SignalLabInspector.test.tsx`.
- Modify `web/src/components/TokenRadarRow.test.tsx`.
- Modify `web/src/components/__tests__/PulseDetailPage.routing.test.tsx`.
- Modify `web/src/App.test.tsx`.
- Create `web/src/components/ScoreLedger.test.tsx` if ledger-specific gate/alpha rendering is not covered elsewhere.

Tests:
- Modify `tests/unit/test_factor_snapshot.py`.
- Modify `tests/architecture/test_no_factor_snapshot_fallback.py`.
- Modify `tests/unit/test_cross_section_normalizer.py`.
- Modify `tests/unit/test_factor_cohort.py`.
- Modify `tests/unit/test_token_radar_feature_builder.py`.
- Modify `tests/unit/test_diffusion_health.py`.
- Modify `tests/unit/test_token_radar_projection.py`.
- Modify `tests/unit/test_token_radar_apply_cross_section.py`.
- Modify `tests/unit/test_token_radar_repository.py`.
- Modify `tests/unit/test_token_radar_audit_cli.py`.
- Modify `tests/unit/test_pulse_candidate_gate.py`.
- Modify `tests/unit/test_pulse_candidate_worker.py`.
- Modify `tests/unit/test_signal_pulse_service.py`.
- Modify `tests/unit/test_notification_rules.py`.
- Modify `tests/unit/test_postgres_schema.py`.
- Modify `tests/integration/test_api_http.py`.
- Modify `tests/integration/test_cli.py`.
- Modify `tests/integration/test_postgres_schema_runtime.py`.
- Modify `tests/integration/test_postgres_audit.py`.
- Modify `tests/integration/test_pulse_repository.py`.
- Create `tests/unit/test_factor_diagnostics.py`.
- Create `tests/unit/test_token_factor_evaluation.py`.
- Create `tests/integration/test_token_factor_evaluation_repository.py` if unit fakes cannot cover SQL upsert behavior.

Docs/generated:
- Modify `docs/CONTRACTS.md`.
- Modify `docs/ARCHITECTURE.md`.
- Modify `docs/TECH_DEBT.md`.
- Regenerate `docs/generated/cli-help.md` with `make docs-cli-help`.
- Regenerate OpenAPI and TS bindings with `make regen-contract` if HTTP schema changes.

## Task 0: Worktree And Baseline

**Files:** read-only check of repo policy and worktree state.

- [x] **Step 0.1: Create worktree**

Run:

```bash
git worktree add .worktrees/token-factor-engineering-hard-cut -b codex/token-factor-engineering-hard-cut main
```

Expected: branch `codex/token-factor-engineering-hard-cut` exists at `.worktrees/token-factor-engineering-hard-cut`.

- [x] **Step 0.2: Confirm clean branch**

Run:

```bash
git status --short --branch
git branch --show-current
```

Expected: `## codex/token-factor-engineering-hard-cut`; no source changes before implementation.

- [ ] **Step 0.3: Capture current baseline**

Run:

```bash
uv run ruff check .
uv run python -m pytest tests/unit/test_factor_snapshot.py tests/architecture/test_no_factor_snapshot_fallback.py tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_repository.py tests/unit/test_pulse_candidate_gate.py -q
cd web && npm run typecheck && npm run test -- --run
```

Expected: record pass/fail state before changing code. If baseline fails for unrelated reasons, write the failure in the verification notes and keep implementation tests focused.

## Task 1: Contract Tests And V2 Snapshot Builder

**Files:**
- Modify `src/parallax/domains/token_intel/_constants.py`.
- Modify `src/parallax/domains/token_intel/scoring/factor_snapshot.py`.
- Modify `tests/unit/test_factor_snapshot.py`.
- Modify `tests/architecture/test_no_factor_snapshot_fallback.py`.

- [x] **Step 1.1: Add failing snapshot contract tests**

In `tests/unit/test_factor_snapshot.py`, assert:

```python
snapshot = build_token_factor_snapshot(
    target={
        "target_type": "Asset",
        "target_id": "asset:buttcoin",
        "symbol": "BUTTCOIN",
        "chain": "solana",
        "address": "So11111111111111111111111111111111111111112",
        "pricefeed_id": "pricefeed:buttcoin",
    },
    attention={"mentions_window": 5, "weighted_mentions": 5.0, "unique_authors": 4, "robust_z": 0.5},
    social_quality={
        "duplicate_text_share": 0.0,
        "independent_authors": 4,
        "effective_authors": 4,
        "top_author_share": 0.25,
    },
    social_semantics={},
    market={"market_status": "fresh", "holders": 500, "liquidity_usd": 100000, "market_cap_usd": 500000},
    timing={"social_signal_start_ms": 1778490000000},
    source_event_ids=["e1", "e2"],
    computed_at_ms=1778490000000,
)
assert snapshot["schema_version"] == "token_factor_snapshot_v2_alpha_gated"
assert set(snapshot["families"]) == {"attention_heat", "diffusion_quality", "semantic_quality", "timing_response"}
assert "identity" not in snapshot["families"]
assert "market_quality" not in snapshot["families"]
assert "timing" not in snapshot["families"]
assert "hard_gates" not in snapshot
assert snapshot["subject"]["target_id"] == "asset:buttcoin"
assert snapshot["data_health"]["identity"] == "ready"
assert snapshot["data_health"]["market"] == "ready"
assert snapshot["gates"]["eligible_for_high_alert"] is True
assert "social_signal_start_ms" not in snapshot["families"]["timing_response"]["factors"]
```

- [x] **Step 1.2: Add duplicate-risk regression**

Assert clean duplication is not a fake 100-point alpha source:

```python
clean = _snapshot_with_social_quality(duplicate_text_share=0.0, independent_authors=4, effective_authors=4)
repeated = _snapshot_with_social_quality(duplicate_text_share=0.75, independent_authors=4, effective_authors=1)
assert clean["families"]["diffusion_quality"]["score"] < 100
assert repeated["families"]["diffusion_quality"]["score"] < clean["families"]["diffusion_quality"]["score"]
assert "repeated_text_cluster" in repeated["gates"]["risk_reasons"]
assert "duplicate_text_share_high" in repeated["gates"]["blocked_reasons"]
```

- [x] **Step 1.3: Add producer no-fallback scan**

In `tests/architecture/test_no_factor_snapshot_fallback.py`, add a focused producer scan for the files owned by Tasks 1 and 2. The full runtime/frontend scan belongs to Task 7 after all consumers are converted.

```python
source_files = [
    "src/parallax/domains/token_intel/scoring/factor_snapshot.py",
    "src/parallax/domains/token_intel/scoring/cross_section_normalizer.py",
    "src/parallax/domains/token_intel/scoring/factor_cohort.py",
    "src/parallax/domains/token_intel/services/token_radar_projection.py",
]
```

Forbidden strings for these producer files:

```python
"token_factor_snapshot_v1"
"hard_gates"
"families\", \"identity\""
"families\", \"market_quality\""
```

Do not scan Pulse, notification, or frontend files in this step; they intentionally still fail until Tasks 5 and 6.

- [x] **Step 1.4: Implement constants and v2 builder**

Set:

```python
TOKEN_RADAR_PROJECTION_VERSION = "token-radar-v11-factor-alpha-gated"
TOKEN_FACTOR_SNAPSHOT_VERSION = "token_factor_snapshot_v2_alpha_gated"
TOKEN_RADAR_FACTOR_FAMILIES = (
    "attention_heat",
    "diffusion_quality",
    "semantic_quality",
    "timing_response",
)
```

In `factor_snapshot.py`, implement:

```python
FAMILY_WEIGHTS = {
    "attention_heat": 0.35,
    "diffusion_quality": 0.30,
    "semantic_quality": 0.25,
    "timing_response": 0.10,
}
```

Required gate reasons:

```python
identity_unresolved
market_freshness_missing
market_freshness_stale
holders_below_high_alert_floor
liquidity_below_high_alert_floor
market_cap_below_high_alert_floor
insufficient_independent_social_sources
duplicate_text_share_high
alpha_data_missing
```

Decision caps:
- identity or freshness block: `max_decision = "discard"`;
- DEX floor, duplicate, or social-source block: `max_decision = "watch"`;
- no block: `max_decision = "high_alert"`.

Thresholds:
- `high_alert`: score `>= 70` and `gates.max_decision == "high_alert"`;
- `watch`: score `>= 35` and cap allows watch;
- `discard`: otherwise.

- [x] **Step 1.5: Run contract tests**

Run:

```bash
uv run python -m pytest tests/unit/test_factor_snapshot.py tests/architecture/test_no_factor_snapshot_fallback.py -q
```

Expected: v2 snapshot tests pass; no producer-owned v1 fallback remains in files touched so far.

## Task 2: Diffusion, Cohort, Normalization, And Projection

**Files:**
- Modify `src/parallax/domains/token_intel/scoring/token_radar_feature_builder.py`.
- Modify `src/parallax/domains/token_intel/scoring/diffusion_health.py` only if needed.
- Modify `src/parallax/domains/token_intel/scoring/cross_section_normalizer.py`.
- Modify `src/parallax/domains/token_intel/scoring/factor_cohort.py`.
- Modify `src/parallax/domains/token_intel/services/token_radar_projection.py`.
- Modify `tests/unit/test_token_radar_feature_builder.py`.
- Modify `tests/unit/test_diffusion_health.py`.
- Modify `tests/unit/test_cross_section_normalizer.py`.
- Modify `tests/unit/test_factor_cohort.py`.
- Modify `tests/unit/test_token_radar_projection.py`.
- Modify `tests/unit/test_token_radar_apply_cross_section.py`.

- [x] **Step 2.1: Wire diffusion health once**

Call `diffusion_health` from the feature builder. Store:
- `diffusion_status`, `diffusion_score`, `diffusion_risks` in `features.quality`.
- `effective_authors`, `top_author_share`, `duplicate_text_share`, `top_authors` in `features.propagation`.

Do not recompute duplicate share separately for v2 factor scoring.

- [x] **Step 2.2: Add factor-rank normalizer**

In `cross_section_normalizer.py`, set:

```python
NORMALIZER_VERSION = "cross_section_v2_factor_ranks"
```

Add:

```python
def rank_factors_within_cohort(
    *,
    factor_scores: dict[str, dict[str, float | None]],
    cohort: set[str],
) -> dict[str, dict[str, float | None]]:
    ...

def weighted_rank_score(
    *,
    factor_ranks: dict[str, float | None],
    weights: dict[str, float],
) -> float | None:
    ...
```

Rules:
- rank each factor independently;
- ignore `None` values for that factor;
- ties use average percentile rank;
- weighted rank renormalizes over available factors;
- no ranked factors returns `None`.

- [x] **Step 2.3: Update cohort signature**

Set:

```python
COHORT_DEFINITION_VERSION = "factor_cohort_v2"
```

Change `is_active_cohort_member` to accept `target_id: str | None`. Require a non-empty `target_id`, exclude major stablecoin symbols, and include if any of these is true:
- at least two high-confidence mentions;
- at least one KOL/watched mention;
- first seen globally in 24h.

Update `TokenRadarProjection._apply_cross_section` call sites to pass `target_id`.

- [x] **Step 2.4: Apply cross-section in projection**

`_project_group` emits raw snapshots. `_apply_cross_section` must:
- collect `raw_score` for each family;
- compute factor ranks;
- compute weighted `alpha_rank`;
- update each family `score`;
- update `normalization`;
- update `composite.family_scores`;
- update `composite.rank_score`;
- recompute `composite.recommended_decision`;
- synchronize `row["decision"]` with the final normalized composite.

- [x] **Step 2.5: Remove v1 tie-breaks and validation**

Update:
- `_rank_key` to use `families.attention_heat.facts` and `families.diffusion_quality.facts`, not `families.social_attention`.
- `_factor_snapshot_or_raise` to require `subject`, `families`, `gates`, `data_health`, `normalization`, and `composite`.
- `_factor_snapshot_or_raise` to reject `hard_gates`.
- `data_health_json` to read `factor_snapshot["data_health"]`.

- [x] **Step 2.6: Run producer tests**

Run:

```bash
uv run python -m pytest tests/unit/test_token_radar_feature_builder.py tests/unit/test_diffusion_health.py tests/unit/test_cross_section_normalizer.py tests/unit/test_factor_cohort.py tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_apply_cross_section.py -q
```

Expected: projection persists v2 snapshots, writes final normalized decisions, and no longer ranks using presence-only families.

## Task 3: Radar Repository Retention, Current Market Read Model, And Evaluation

**Files:**
- Modify `src/parallax/domains/token_intel/repositories/token_radar_repository.py`.
- Modify `src/parallax/domains/token_intel/read_models/asset_flow_service.py`.
- Modify `src/parallax/app/runtime/app.py`.
- Modify `src/parallax/app/surfaces/api/http.py`.
- Modify `src/parallax/app/surfaces/cli/main.py`.
- Modify `src/parallax/app/runtime/repository_session.py`.
- Modify `src/parallax/domains/asset_market/repositories/price_observation_repository.py`.
- Create `src/parallax/domains/token_intel/repositories/token_factor_evaluation_repository.py`.
- Create `src/parallax/domains/token_intel/services/token_factor_evaluation.py`.
- Modify `tests/unit/test_token_radar_repository.py`.
- Modify `tests/unit/test_asset_flow_service.py`.
- Modify `tests/unit/test_token_factor_evaluation.py` or create it.
- Modify/create `tests/integration/test_token_factor_evaluation_repository.py` for SQL upsert if needed.

- [x] **Step 3.1: Retain historical radar runs**

In `TokenRadarRepository.replace_rows`, replace broad delete:

```sql
DELETE FROM token_radar_rows
WHERE projection_version = %s AND "window" = %s AND scope = %s
```

with run-idempotent delete:

```sql
DELETE FROM token_radar_rows
WHERE projection_version = %s
  AND "window" = %s
  AND scope = %s
  AND computed_at_ms = %s
```

Keep the existing stale-write guard that rejects writes older than latest `computed_at_ms`.

- [x] **Step 3.2: Validate v2 contract in repository**

Require:

```python
for key in ("subject", "families", "gates", "data_health", "normalization", "composite"):
    ...
```

Reject:
- mismatched `schema_version`;
- missing `TOKEN_RADAR_FACTOR_FAMILIES`;
- `hard_gates` key.

- [x] **Step 3.3: Stop deriving API current_market from factor snapshot**

Update `AssetFlowService` to accept `current_market` repository:

```python
class AssetFlowService:
    def __init__(self, *, token_radar, current_market):
        self.token_radar = token_radar
        self.current_market = current_market
```

When building asset-flow rows:
- collect `(target_type, target_id)` from radar rows;
- call `current_market.current_for_subjects(subjects, now_ms=now_ms)`;
- pass the returned current-market snapshot into `_public_row`;
- remove `_current_market_from_snapshot` dependency on `families.market_quality`.

Update `http.py`, `app.py`, and CLI `asset-flow` construction to pass `repos.current_market`.

- [x] **Step 3.4: Add price exit lookup for settlement**

In `PriceObservationRepository`, add:

```python
def first_for_subject_at_or_after(
    self,
    *,
    subject_type: str,
    subject_id: str,
    at_or_after_ms: int,
) -> dict[str, Any] | None:
    row = self.conn.execute(
        """
        SELECT *
        FROM price_observations
        WHERE subject_type = %s
          AND subject_id = %s
          AND observed_at_ms >= %s
          AND price_usd IS NOT NULL
        ORDER BY observed_at_ms ASC, observation_id ASC
        LIMIT 1
        """,
        (subject_type, subject_id, int(at_or_after_ms)),
    ).fetchone()
    return dict(row) if row else None
```

Also update `latest_for_subject_at_or_before` settlement use to filter `price_usd IS NOT NULL` in the evaluation repository/service, not necessarily globally for every caller.

- [x] **Step 3.5: Add evaluation repository and service**

Create a focused repository with:
- `historical_radar_rows(factor_version, window, scope, horizon_ms, generated_at_ms, limit)`.
- `upsert_score_evaluation(summary)`.
- `latest_score_evaluations(horizon, window, scope, score_version)`.

Create service:

```python
def settle_token_factor_scores(
    *,
    repos,
    horizon: str,
    window: str,
    scope: str,
    generated_at_ms: int,
    limit: int,
) -> dict[str, Any]:
    ...
```

Horizon map:

```python
HORIZON_MS = {
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "6h": 6 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
}
```

Settlement rules:
- entry price: latest non-null `price_usd` at or before `computed_at_ms`;
- exit price: first non-null `price_usd` at or after `computed_at_ms + horizon_ms`;
- unsettled if entry or exit is missing;
- actual return: `(exit_price - entry_price) / entry_price`;
- buckets: `0-19`, `20-39`, `40-59`, `60-79`, `80-100`;
- directional hit: return `> 0`;
- Spearman IC: correlation of `rank_score` versus actual return when at least three settled rows exist;
- ICIR: daily IC mean divided by daily IC standard deviation when at least two daily IC values exist, otherwise `None`.

- [x] **Step 3.6: Run repository/read-model/evaluation tests**

Run:

```bash
uv run python -m pytest tests/unit/test_token_radar_repository.py tests/unit/test_asset_flow_service.py tests/unit/test_token_factor_evaluation.py -q
```

If SQL behavior is covered:

```bash
uv run python -m pytest tests/integration/test_token_factor_evaluation_repository.py -q
```

Expected: historical rows are retained, latest rows remain latest-only, current-market response comes from the market read model, and settlement buckets are deterministic.

## Task 4: Migration, Diagnostics, And CLI

**Files:**
- Create `src/parallax/platform/db/alembic/versions/20260511_0026_token_factor_eval_diagnostics.py`.
- Create `src/parallax/domains/token_intel/scoring/factor_diagnostics.py`.
- Modify `src/parallax/app/surfaces/cli/main.py`.
- Modify `src/parallax/platform/db/postgres_audit.py`.
- Modify `tests/unit/test_factor_diagnostics.py`.
- Modify `tests/unit/test_token_radar_audit_cli.py`.
- Modify `tests/unit/test_postgres_schema.py`.
- Modify `tests/integration/test_cli.py`.
- Modify `tests/integration/test_postgres_schema_runtime.py`.
- Modify `tests/integration/test_postgres_audit.py`.

- [x] **Step 4.1: Add migration**

Use:

```python
revision = "20260511_0026"
down_revision = "20260511_0025"
```

Upgrade:

```sql
ALTER TABLE token_score_evaluations
  ADD COLUMN IF NOT EXISTS sample_start_ms BIGINT,
  ADD COLUMN IF NOT EXISTS sample_end_ms BIGINT,
  ADD COLUMN IF NOT EXISTS spearman_ic DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS icir DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS score_stddev DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_token_score_evaluations_generated
  ON token_score_evaluations(horizon, "window", scope, score_version, generated_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_token_radar_rows_settlement
  ON token_radar_rows(factor_version, "window", scope, computed_at_ms, target_type, target_id);

CREATE INDEX IF NOT EXISTS idx_price_observations_subject_price_after
  ON price_observations(subject_type, subject_id, observed_at_ms ASC, observation_id ASC)
  WHERE price_usd IS NOT NULL;
```

Downgrade drops those indexes and columns in reverse order.

- [x] **Step 4.2: Add factor distribution diagnostics**

Create `factor_distribution_report(rows)` returning:
- `row_count`;
- `rank_score_unique_count`;
- `rank_score_stddev`;
- `rank_score_saturation_100_share`;
- `family_saturation_100_share`;
- `gate_block_counts`;
- `data_health_counts`;
- `ok`;
- `violations`.

Violation rules:
- `row_count > 20` and `rank_score_unique_count <= 3`;
- saturation at 100 exceeds 25% for any alpha family with at least 20 non-null scores;
- old family keys appear;
- `hard_gates` appears.

- [x] **Step 4.3: Add CLI commands**

Under `ops` add:

```bash
parallax ops factor-diagnostics --window 1h --scope all --limit 200
parallax ops settle-token-factors --window 1h --scope all --horizon 1h --limit 1000
```

Arguments:
- `factor-diagnostics`: `--window`, `--scope`, `--limit`.
- `settle-token-factors`: `--window`, `--scope`, `--horizon`, `--limit`, hidden `--now-ms`.

- [x] **Step 4.4: Update audit-token-radar**

Audit now requires:
- `schema_version == TOKEN_FACTOR_SNAPSHOT_VERSION`;
- families exactly contain `TOKEN_RADAR_FACTOR_FAMILIES`;
- `gates`, `data_health`, `normalization`, `composite` exist;
- `hard_gates` absent;
- high alert only when `gates.eligible_for_high_alert` is true;
- no old runtime payload resurrection.

- [x] **Step 4.5: Run diagnostics and CLI tests**

Run:

```bash
uv run python -m pytest tests/unit/test_factor_diagnostics.py tests/unit/test_token_radar_audit_cli.py tests/unit/test_postgres_schema.py -q
uv run python -m pytest tests/integration/test_cli.py tests/integration/test_postgres_schema_runtime.py tests/integration/test_postgres_audit.py -q
```

Expected: CLI help includes new commands, audit rejects v1 shape, migration schema includes diagnostics columns and settlement indexes.

## Task 5: Pulse, Notifications, And Agent Context Hard Cut

**Files:**
- Modify `src/parallax/domains/pulse_lab/services/pulse_candidate_gate.py`.
- Modify `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`.
- Modify `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py`.
- Modify `src/parallax/domains/pulse_lab/repositories/pulse_repository.py`.
- Modify `src/parallax/domains/notifications/services/notification_rules.py`.
- Modify `src/parallax/domains/pulse_lab/types/pulse_recommendation.py` if needed.
- Modify `src/parallax/integrations/openai_agents/pulse_recommendation_agent_client.py` if prompt/audit names are v1-specific.
- Modify `tests/unit/test_pulse_candidate_gate.py`.
- Modify `tests/unit/test_pulse_candidate_worker.py`.
- Modify `tests/unit/test_signal_pulse_service.py`.
- Modify `tests/unit/test_notification_rules.py`.
- Modify `tests/integration/test_pulse_repository.py`.
- Modify `tests/integration/test_api_http.py`.

- [x] **Step 5.1: Gate service hard cut**

`gate_pulse_candidate_from_factor_snapshot` and `_valid_snapshot` must require:
- `subject`;
- `gates`;
- `data_health`;
- `families`;
- `composite`.

They must reject `hard_gates`.

High alert eligibility:

```python
eligible = bool(snapshot["gates"]["eligible_for_high_alert"])
score = int(snapshot["composite"]["rank_score"] or 0)
```

Market/identity reasons appear as gate/data-health explanation, not alpha reasons.

- [x] **Step 5.2: Worker trigger metrics v2 paths**

`pulse_candidate_worker.py` trigger metrics read only:
- `composite.rank_score`;
- `composite.recommended_decision`;
- `gates.blocked_reasons`;
- `gates.eligible_for_high_alert`;
- `families.attention_heat.facts`;
- `families.diffusion_quality.facts`;
- `families.semantic_quality.facts`;
- `families.timing_response.facts`.

Update `_source_seed_factor_snapshot` to produce v2 shape with `identity_unresolved` gate instead of v1 `hard_gates`.

- [x] **Step 5.3: Signal pulse read model v2 fact card**

`signal_pulse_service.py` fact card should expose:
- rank score and recommended decision;
- gate block reasons;
- data health;
- alpha family scores;
- market facts from `subject`, `data_health`, or current row fields, not `families.market_quality`.

`_valid_factor_snapshot` requires v2 keys and rejects v1.

- [x] **Step 5.4: Pulse repository SQL v2 JSON paths**

Replace direct SQL checks on:

```sql
factor_snapshot_json #>> '{families,market_quality,facts,market_status}'
```

with v2 data-health/gate paths such as:

```sql
factor_snapshot_json #>> '{data_health,market}'
factor_snapshot_json #>> '{gates,eligible_for_high_alert}'
```

Choose the path that matches the summary field semantics. For market-ready rate, use `data_health.market IN ('ready', 'partial')` only if partial is intentionally counted; otherwise use `= 'ready'`.

- [x] **Step 5.5: Notifications v2 severity/body**

Notification severity uses `gates + composite`, not market/identity alpha:
- `_signal_pulse_severity`;
- `_valid_factor_snapshot`;
- `_market_fact_line`;
- `_social_fact_line`;
- payload fingerprints and body fields.

Copy should mention strongest alpha families and gate blocks separately.

- [x] **Step 5.6: Run backend consumer tests**

Run:

```bash
uv run python -m pytest tests/unit/test_pulse_candidate_gate.py tests/unit/test_pulse_candidate_worker.py tests/unit/test_signal_pulse_service.py tests/unit/test_notification_rules.py tests/integration/test_pulse_repository.py tests/integration/test_api_http.py -q
```

Expected: Signal Labs and notifications accept v2 only and do not treat market/identity gates as alpha.

## Task 6: Frontend V2 Adapter And Components

**Files:**
- Modify `web/src/api/types.ts`.
- Modify `web/src/lib/tokenRadar.ts`.
- Modify `web/src/lib/tokenRadar.test.ts`.
- Modify `web/src/lib/venue.ts`.
- Modify `web/src/lib/venue.test.ts`.
- Modify `web/src/components/SignalLabPulse.tsx`.
- Modify `web/src/components/SignalLabPulse.test.tsx`.
- Modify `web/src/components/SignalLabInspector.tsx`.
- Modify `web/src/components/SignalLabInspector.test.tsx`.
- Modify `web/src/components/TokenRadarRow.test.tsx`.
- Modify `web/src/components/__tests__/PulseDetailPage.routing.test.tsx`.
- Modify `web/src/App.test.tsx`.
- Create `web/src/components/ScoreLedger.test.tsx` if coverage is otherwise missing.

- [x] **Step 6.1: Type hard cut**

Update `TokenFactorSnapshot` in `web/src/api/types.ts`:
- `schema_version: "token_factor_snapshot_v2_alpha_gated" | string`;
- `gates` replaces `hard_gates`;
- `data_health` required;
- families are v2 alpha families;
- `normalization` present.

Do not keep `hard_gates` as an optional field.

- [x] **Step 6.2: Adapter hard cut**

`requiredFactorSnapshot` in `web/src/lib/tokenRadar.ts` accepts only v2.

Map current UI concepts:
- `social_heat` from `families.attention_heat`;
- `propagation` from `families.diffusion_quality`;
- `discussion_quality` from `families.semantic_quality` plus diffusion facts where existing UI needs author/duplicate fields;
- `timing` from `families.timing_response`;
- `tradeability` from `gates` and `data_health.market`, not a scoring family;
- `opportunity.hard_risks` from `gates.blocked_reasons`;
- `opportunity.components` from `composite.family_scores`.

Keep price/market display from `row.current_market.fields`; do not read price from factor families.

- [x] **Step 6.3: Component labels**

`ScoreLedger` and Signal Lab inspectors should show:
- alpha family rows only;
- gate block panel separately;
- cross-section rank/cohort size;
- data-health warnings.

They must not render identity or market as alpha cards.

- [x] **Step 6.4: Update frontend fixtures**

Replace v1 fixtures in:
- `web/src/lib/tokenRadar.test.ts`;
- `web/src/lib/venue.test.ts`;
- `web/src/components/SignalLabPulse.test.tsx`;
- `web/src/components/SignalLabInspector.test.tsx`;
- `web/src/components/TokenRadarRow.test.tsx`;
- `web/src/components/__tests__/PulseDetailPage.routing.test.tsx`;
- `web/src/App.test.tsx`.

Add one explicit test that v1 throws a contract error.

- [x] **Step 6.5: Run frontend checks**

Run:

```bash
cd web && npm run typecheck && npm run lint && npm run test -- --run && npm run build
```

Expected: frontend accepts v2 snapshots only and current market remains independent of factor families.

## Task 7: Docs, Generated Contracts, And Verification

**Files:**
- Modify `docs/CONTRACTS.md`.
- Modify `docs/ARCHITECTURE.md`.
- Modify `src/parallax/domains/token_intel/ARCHITECTURE.md`.
- Modify `docs/TECH_DEBT.md`.
- Regenerate `docs/generated/cli-help.md`.
- Regenerate `docs/generated/openapi.json` and `web/src/api/openapi.ts` if API schema changes.

- [x] **Step 7.1: Document v2 contract**

Document:
- gate/data-health/alpha split;
- no v1 runtime compatibility;
- `current_market` comes from market read model, not factor snapshot;
- diagnostic/settlement commands;
- retained historical `token_radar_rows`.

- [x] **Step 7.2: Regenerate generated docs**

Run:

```bash
make docs-cli-help
make regen-contract
```

Run `make docs-generated` only if db schema or score-version generated docs are expected to change and the local database is available.

- [x] **Step 7.3: Final hard-cut scan**

Run:

```bash
rg -n "token_factor_snapshot_v1|hard_gates|families\\]\\[\\\"identity\\\"|families\\]\\[\\\"market_quality\\\"|families\\]\\[\\\"social_attention\\\"|social_signal_start_ms.*score" src tests web
```

Expected: no runtime v1 compatibility paths remain. Mentions in migration history, docs, and explicit negative tests are acceptable.

- [ ] **Step 7.4: Full completion gate**

Run:

```bash
make check-all
```

Expected: exit 0 before claiming completion.

Current status after the 2026-05-11 resync and Godel review fixes:
- `make check` passes: ruff, ruff format, mypy, frontend typecheck/lint/format, unit, architecture, contract, and compileall; latest run was `459 passed, 6 skipped`.
- `make test-integration` has no business-code failures: `168 passed, 14 skipped`; the only failure is `tests/integration/test_docs_generated.py::test_make_docs_generated_clean_diff`.
- `make test-e2e` passes: `4 passed`.
- `make coverage` reaches the configured threshold: `696 passed, 19 skipped`, total coverage `82.74%`; the only failure is again `test_make_docs_generated_clean_diff`.
- Subagent Godel re-review after the P1/P2 fixes is `APPROVED`.

`test_make_docs_generated_clean_diff` reruns `make docs-generated` and then
requires `git diff docs/generated/` to be empty. The generated files are updated
in the worktree, but they are intentionally not staged here because staging was
not requested. `make check-all` will remain blocked by this git-index cleanliness
rule until the generated docs are staged or committed with the rest of the
change.

- [ ] **Step 7.5: Operational smoke**

Run when a local DB/config is available:

```bash
uv run parallax db health
uv run parallax ops rebuild-token-radar --window 1h --scope all --limit 100
uv run parallax ops audit-token-radar --window 1h --scope all --limit 100
uv run parallax ops factor-diagnostics --window 1h --scope all --limit 200
uv run parallax ops settle-token-factors --window 1h --scope all --horizon 1h --limit 1000
uv run parallax asset-flow --window 1h --scope all --limit 20
```

Expected:
- latest rows use `token-radar-v11-factor-alpha-gated`;
- audit passes;
- diagnostics show score dispersion rather than presence-based saturation;
- settlement writes or reports insufficient forward-price coverage honestly;
- `/asset-flow` and frontend render current market from `current_market.fields`, not factor market facts.

## Subagent Execution Order

Execute sequentially with fresh workers and review after each task:

1. Task 1 worker: constants + v2 builder + contract tests.
2. Task 2 worker: diffusion + normalization + projection.
3. Task 3 worker: repository retention + asset flow current-market + evaluation service.
4. Task 4 worker: migration + diagnostics + CLI audit/ops.
5. Task 5 worker: Pulse + notifications.
6. Task 6 worker: frontend adapter + components.
7. Task 7 worker: docs/generated + final verification.

Workers are not alone in the codebase. Each worker must avoid reverting edits from other workers and must adapt to previous task changes. Use disjoint write scopes where possible; if a task needs to touch a file owned by an earlier task, inspect the current file first and preserve existing edits.

## Final Review Checklist

- [x] Identity, market freshness, DEX floors, CEX native-market identity, duplicate clean state, and `social_signal_start_ms` are never positive alpha.
- [x] Runtime producers persist only v2 snapshot shape.
- [x] Runtime readers reject v1 shape rather than falling back.
- [x] `token_radar_rows` retains historical runs while `latest_rows` remains latest-only.
- [x] Asset-flow `current_market` is from the current-market read model, not factor snapshot.
- [x] `token_score_evaluations` receives real bucket/IC diagnostics keyed by v2 score version.
- [x] Signal Labs and notifications explain gates separately from alpha families.
- [x] Frontend adapters render v2 and fail loudly on v1.
- [ ] `make check-all` passes.
