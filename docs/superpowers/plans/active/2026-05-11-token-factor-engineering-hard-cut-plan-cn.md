# Token Factor Engineering Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current presence-heavy token factor snapshot with an evaluable, cross-section-aware factor contract where identity, market freshness, duplicate risk, and data availability are gates or data-health facts rather than fake alpha.

**Architecture:** Keep the existing token radar projection path and PostgreSQL store. Rewrite only the factor contract, projection normalization, retention, diagnostics, evaluation, and consumers that read the snapshot. Do not add providers, queues, LLM calls, new scoring tables, or backward-compatible runtime branches for `token_factor_snapshot_v1`.

**Tech Stack:** Python 3, psycopg/PostgreSQL, Alembic, pytest, argparse CLI, existing React/TypeScript frontend.

---

## Source Spec

- Spec: `docs/superpowers/specs/active/2026-05-11-token-factor-engineering-hard-cut-cn.md`
- Implementation branch: `codex/token-factor-engineering-hard-cut`
- Implementation worktree: `.worktrees/token-factor-engineering-hard-cut`

## Scope

In:
- New current factor version only.
- Existing data only: `events`, `account_profiles`, `social_event_extractions`, `price_observations`, `token_radar_rows`, `token_score_evaluations`.
- Keep Token Radar, Signal Labs pulse, notifications, API, CLI, and frontend aligned with the new snapshot shape.
- Retain historical `token_radar_rows` snapshots for forward-return settlement.
- Persist bucket evaluation summaries into existing `token_score_evaluations`.

Out:
- No new external market/social providers.
- No new LLM labels or model training.
- No recreated `token_signal_snapshots` / `token_signal_outcomes`.
- No runtime fallback for old `families.identity`, `families.market_quality`, or `hard_gates`.

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
      "raw_score": 0,
      "score": 0,
      "weight": 0.35,
      "data_health": "ready",
      "facts": {},
      "factors": {}
    },
    "diffusion_quality": {
      "raw_score": 0,
      "score": 0,
      "weight": 0.30,
      "data_health": "ready",
      "facts": {},
      "factors": {}
    },
    "semantic_quality": {
      "raw_score": 0,
      "score": 0,
      "weight": 0.25,
      "data_health": "partial",
      "facts": {},
      "factors": {}
    },
    "timing_response": {
      "raw_score": 0,
      "score": 0,
      "weight": 0.10,
      "data_health": "partial",
      "facts": {},
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
    "source_event_ids": [],
    "computed_at_ms": 1778490000000
  }
}
```

## Scoring Rules

- Identity facts are never alpha. Missing target identity gates high alert and caps the decision surface.
- Market freshness, DEX holder/liquidity/market-cap floors, and CEX native market identity are never alpha. They are gates and data-health facts.
- `social_signal_start_ms` is provenance only. Its presence must never produce points.
- Duplicate text and top-author concentration are negative risk controls. A clean duplicate score may remove a penalty but must not create a standalone 100-point alpha family.
- Raw alpha is social-first and sparse: `attention_heat`, `diffusion_quality`, `semantic_quality`, `timing_response`.
- Final `rank_score` is cross-sectional when the active cohort is usable; otherwise it falls back to raw alpha with `normalization.status = "insufficient_cohort"`.
- High alert requires both alpha and gates. A high raw score with blocked gates becomes `watch` or `discard`, never `high_alert`.

## File Structure

Modify:
- `src/gmgn_twitter_intel/domains/token_intel/_constants.py`: bump projection/factor/normalizer/cohort-facing constants and alpha family tuple.
- `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py`: rewrite current snapshot builder and gate/composite semantics.
- `src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py`: wire `diffusion_health`, expose weighted/social facts needed by v2.
- `src/gmgn_twitter_intel/domains/token_intel/scoring/cross_section_normalizer.py`: add factor-level percentile ranks and Spearman helpers.
- `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_cohort.py`: update active cohort definition version and keep the cohort simple.
- `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`: build raw snapshots first, apply factor-level normalization second, and persist new decision fields.
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`: retain historical runs and validate the new factor contract.
- `src/gmgn_twitter_intel/domains/asset_market/repositories/price_observation_repository.py`: add first-at-or-after lookup for settlement.
- `src/gmgn_twitter_intel/app/runtime/repository_session.py`: expose the factor evaluation repository if a new focused repository is created.
- `src/gmgn_twitter_intel/app/surfaces/cli/main.py`: add factor diagnostics and settlement commands; update `audit-token-radar`.
- `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py`: read `gates`, `data_health`, and new `composite`.
- `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`: emit trigger metadata from v2 paths only.
- `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py`: expose v2 score ledger and fact cards.
- `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py`: prevent high-alert notification copy from treating gates as alpha.
- `src/gmgn_twitter_intel/platform/db/postgres_audit.py`: update schema audit expectations for retained token radar rows and v2 snapshots.
- `docs/CONTRACTS.md`, `docs/ARCHITECTURE.md`, `docs/TECH_DEBT.md`, `docs/generated/cli-help.md`: document the new hard-cut contract and commands.
- Frontend files that render score ledgers or pulse detail pages, likely `web/src/api/types.ts`, `web/src/components/SignalLabPulse.tsx`, `web/src/components/PulseDetailPage.tsx`, `web/src/components/SignalLabInspector.tsx`, and `web/src/components/ScoreLedger.tsx`.

Create:
- `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_diagnostics.py`: distribution, saturation, uniqueness, and family-health report logic.
- `src/gmgn_twitter_intel/domains/token_intel/services/token_factor_evaluation.py`: settlement and bucket evaluation orchestration.
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_factor_evaluation_repository.py`: SQL for historical radar rows and evaluation upserts.
- `src/gmgn_twitter_intel/platform/db/alembic/versions/20260511_0025_token_factor_eval_diagnostics.py`: add diagnostics columns/indexes to existing evaluation table.
- `tests/test_token_factor_evaluation.py`: settlement, bucket, and IC coverage.
- `tests/test_factor_diagnostics.py`: saturation and distribution diagnostics.

## Task 0: Worktree, Baseline, And Safety Check

**Files:**
- Read: `AGENTS.md`
- Read: `CLAUDE.md`
- Read: `docs/WORKFLOW.md`

- [ ] **Step 0.1: Create the isolated implementation worktree**

Run:

```bash
git worktree add .worktrees/token-factor-engineering-hard-cut -b codex/token-factor-engineering-hard-cut
cd .worktrees/token-factor-engineering-hard-cut
```

Expected: new branch `codex/token-factor-engineering-hard-cut` is checked out in `.worktrees/token-factor-engineering-hard-cut`.

- [ ] **Step 0.2: Confirm unrelated work is not part of the branch**

Run:

```bash
git status --short
```

Expected: clean worktree before edits.

- [ ] **Step 0.3: Capture baseline test state**

Run:

```bash
uv run ruff check .
uv run pytest tests/test_factor_snapshot.py tests/test_token_radar_projection.py tests/test_token_radar_repository.py tests/test_pulse_candidate_gate.py -q
```

Expected: record pass/fail state in the implementation notes before changing code.

## Task 1: Lock The V2 Contract In Tests First

**Files:**
- Modify: `tests/test_factor_snapshot.py`
- Modify: `tests/test_no_factor_snapshot_fallback.py`
- Modify: `tests/test_token_radar_audit_cli.py`
- Modify: `tests/test_cross_section_normalizer.py`
- Create: `tests/test_factor_diagnostics.py`

- [ ] **Step 1.1: Add a factor snapshot test that proves presence facts do not score**

Add assertions covering this behavior:

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
    social_quality={"duplicate_text_share": 0.0, "independent_authors": 4, "effective_authors": 4, "top_author_share": 0.25},
    social_semantics={},
    market={"market_status": "fresh", "holders": 500, "liquidity_usd": 100000, "market_cap_usd": 500000},
    timing={"social_signal_start_ms": 1778490000000},
    source_event_ids=["e1", "e2"],
    computed_at_ms=1778490000000,
)
assert "identity" not in snapshot["families"]
assert "market_quality" not in snapshot["families"]
assert "timing" not in snapshot["families"]
assert "hard_gates" not in snapshot
assert snapshot["subject"]["target_id"] == "asset:buttcoin"
assert snapshot["gates"]["eligible_for_high_alert"] is True
assert "social_signal_start_ms" not in snapshot["families"]["timing_response"]["factors"]
```

- [ ] **Step 1.2: Add a duplicate-risk test that penalizes but never rewards clean duplicates**

Add assertions:

```python
clean = _snapshot_with_social_quality(duplicate_text_share=0.0, independent_authors=4, effective_authors=4)
repeated = _snapshot_with_social_quality(duplicate_text_share=0.75, independent_authors=4, effective_authors=1)
assert clean["families"]["diffusion_quality"]["score"] < 100
assert repeated["families"]["diffusion_quality"]["score"] < clean["families"]["diffusion_quality"]["score"]
assert "repeated_text_cluster" in repeated["gates"]["risk_reasons"]
assert "duplicate_text_share_high" in repeated["gates"]["blocked_reasons"]
```

- [ ] **Step 1.3: Add a no-fallback test for v1 paths**

Add assertions that source no longer reads runtime keys:

```python
source_files = [
    "src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py",
    "src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py",
    "src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py",
]
for path in source_files:
    text = Path(path).read_text()
    assert "token_factor_snapshot_v1" not in text
    assert "[\"hard_gates\"]" not in text
    assert ".get(\"hard_gates\"" not in text
```

- [ ] **Step 1.4: Add cross-section tests for factor ranks and tie handling**

Add assertions:

```python
ranks = rank_factors_within_cohort(
    factor_scores={
        "a": {"attention_heat": 10, "diffusion_quality": 20},
        "b": {"attention_heat": 40, "diffusion_quality": 20},
        "c": {"attention_heat": 90, "diffusion_quality": None},
    },
    cohort={"a", "b", "c"},
)
assert ranks["a"]["attention_heat"] < ranks["b"]["attention_heat"] < ranks["c"]["attention_heat"]
assert ranks["a"]["diffusion_quality"] == ranks["b"]["diffusion_quality"]
assert ranks["c"]["diffusion_quality"] is None
```

- [ ] **Step 1.5: Run the new tests and verify they fail for the current implementation**

Run:

```bash
uv run pytest tests/test_factor_snapshot.py tests/test_no_factor_snapshot_fallback.py tests/test_cross_section_normalizer.py tests/test_factor_diagnostics.py -q
```

Expected: failures mention old `hard_gates`, old family names, or missing diagnostic/rank functions.

## Task 2: Rewrite Constants And Snapshot Builder

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/_constants.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py`
- Modify: `tests/test_factor_snapshot.py`

- [ ] **Step 2.1: Bump versions and family constants**

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

- [ ] **Step 2.2: Replace old family builders with v2 alpha families**

In `factor_snapshot.py`, keep `DEX_HIGH_ALERT_FLOORS` but move it into gate logic. Implement four family builders:

```python
FAMILY_WEIGHTS = {
    "attention_heat": 0.35,
    "diffusion_quality": 0.30,
    "semantic_quality": 0.25,
    "timing_response": 0.10,
}
```

Use these rules:
- `attention_heat`: score weighted mentions, unique authors, robust z/new burst, and stream share.
- `diffusion_quality`: score effective authors and penalize top-author concentration and duplicate share.
- `semantic_quality`: score direction/impact/novelty/confidence only when semantic facts are present.
- `timing_response`: score price-change context only when price-change fields are present; store `social_signal_start_ms` only under facts.

- [ ] **Step 2.3: Implement v2 gates**

Gate reasons:

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
- Any identity or market freshness block: `max_decision = "discard"`.
- DEX floor or duplicate/social-source block: `max_decision = "watch"`.
- No block: `max_decision = "high_alert"`.

- [ ] **Step 2.4: Implement v2 composite before normalization**

Before cross-section normalization:

```python
raw_alpha_score = weighted_average(ready_or_partial_family_scores)
rank_score = raw_alpha_score
recommended_decision = capped_decision(raw_alpha_score, gates)
```

Thresholds:
- `high_alert`: raw/ranked score `>= 70` and `gates.max_decision == "high_alert"`.
- `watch`: score `>= 35` and `gates.max_decision in {"watch", "high_alert"}`.
- `discard`: all other cases.

- [ ] **Step 2.5: Run snapshot tests**

Run:

```bash
uv run pytest tests/test_factor_snapshot.py -q
```

Expected: v2 snapshot tests pass; old v1 expectations are removed rather than dual-supported.

## Task 3: Wire Real Diffusion Health Into Existing Feature Building

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/diffusion_health.py` only if the existing function needs a narrow input compatibility fix.
- Modify: `tests/test_token_radar_feature_builder.py`
- Modify: `tests/test_diffusion_health.py`

- [ ] **Step 3.1: Add failing feature-builder assertions**

Assert that `build_radar_features(...).quality` or `.propagation` includes:

```python
{
    "diffusion_status": "healthy",
    "effective_authors": 3,
    "top_author_share": 0.5,
    "duplicate_text_share": 0.0,
    "diffusion_risks": [],
}
```

Also assert repeated text creates:

```python
assert "repeated_text_cluster" in features.quality["diffusion_risks"]
assert features.quality["effective_authors"] < features.quality["independent_authors"]
```

- [ ] **Step 3.2: Call `diffusion_health` from the feature builder**

Use existing row fields:
- `author_handle`
- `text_clean` or `text`
- `author_followers`
- `received_at_ms`
- `is_watched`

Merge results into existing quality/propagation dictionaries with explicit names:

```python
quality["diffusion_status"] = health["status"]
quality["diffusion_score"] = health["score"]
quality["diffusion_risks"] = health["risks"]
propagation["effective_authors"] = health["effective_authors"]
propagation["top_author_share"] = health["top_author_share"]
propagation["duplicate_text_share"] = health["duplicate_text_share"]
propagation["top_authors"] = health["top_authors"][:3]
```

- [ ] **Step 3.3: Keep duplicate facts single-source**

Ensure `factor_snapshot.py` reads duplicate/top-author/effective-author values from the merged diffusion output, not from a second ad hoc duplicate computation.

- [ ] **Step 3.4: Run feature tests**

Run:

```bash
uv run pytest tests/test_token_radar_feature_builder.py tests/test_diffusion_health.py -q
```

Expected: diffusion behavior is deterministic and repeated text lowers diffusion health.

## Task 4: Add Factor-Level Cross-Section Normalization

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/cross_section_normalizer.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_cohort.py`
- Modify: `tests/test_cross_section_normalizer.py`
- Modify: `tests/test_factor_cohort.py`

- [ ] **Step 4.1: Add rank helpers**

Implement:

```python
NORMALIZER_VERSION = "cross_section_v2_factor_ranks"

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
- Rank each factor independently.
- Ignore `None` values per factor.
- Ties receive average percentile rank.
- If no ranked factors exist, return `None`.
- Weighted rank is renormalized over available factors.

- [ ] **Step 4.2: Update cohort definition**

Set `COHORT_DEFINITION_VERSION = "factor_cohort_v2"`.

Keep cohort membership simple:
- target has `target_id`;
- not a major stablecoin symbol;
- at least two high-confidence mentions, or at least one KOL/watched mention, or first-seen global in 24h.

- [ ] **Step 4.3: Run normalization tests**

Run:

```bash
uv run pytest tests/test_cross_section_normalizer.py tests/test_factor_cohort.py -q
```

Expected: factor ranks, ties, missing factors, and cohort exclusion behavior pass.

## Task 5: Apply Normalization In Token Radar Projection

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- Modify: `tests/test_token_radar_projection.py`
- Modify: `tests/test_token_radar_apply_cross_section.py`

- [ ] **Step 5.1: Make `_project_group` emit raw v2 snapshots**

Keep `_project_group` responsible for:
- grouping facts;
- building raw v2 snapshot;
- setting the provisional row decision from raw composite;
- writing `data_health_json` from `factor_snapshot_json["data_health"]`.

Remove old data-health paths:

```python
"identity": factor_snapshot["families"]["identity"]["data_health"]
"market": factor_snapshot["families"]["market_quality"]["data_health"]
```

Replace with:

```python
"identity": factor_snapshot["data_health"]["identity"]
"market": factor_snapshot["data_health"]["market"]
"social": factor_snapshot["data_health"]["social"]
"alpha": factor_snapshot["data_health"]["alpha"]
```

- [ ] **Step 5.2: Make `_apply_cross_section` normalize families before sorting**

Collect per-target family scores:

```python
factor_scores[target_id] = {
    family: snapshot["families"][family]["raw_score"]
    for family in TOKEN_RADAR_FACTOR_FAMILIES
}
```

Apply `rank_factors_within_cohort` and `weighted_rank_score`. Then update each snapshot:
- `normalization.factor_ranks`
- `normalization.alpha_rank`
- normalized `families[family]["score"]`
- `composite.family_scores`
- `composite.rank_score`
- `composite.recommended_decision`

- [ ] **Step 5.3: Keep sorting aligned with normalized decisions**

Sort key must use:

```python
factor_snapshot_json["composite"]["rank_score"]
```

Use final `decision` from the normalized composite after `_apply_cross_section`, not the provisional decision from `_project_group`.

- [ ] **Step 5.4: Add projection regression tests**

Add tests proving:
- two tokens with identical identity and market freshness do not both get 100 from presence facts;
- a token with stronger diffusion ranks above a single-author token;
- blocked gates cap decision to `watch` or `discard` even when rank score is high.

- [ ] **Step 5.5: Run projection tests**

Run:

```bash
uv run pytest tests/test_token_radar_projection.py tests/test_token_radar_apply_cross_section.py -q
```

Expected: projection persists v2 snapshots and ranking uses normalized alpha.

## Task 6: Retain Historical Radar Rows For Evaluation

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `tests/test_token_radar_repository.py`
- Modify: `src/gmgn_twitter_intel/platform/db/postgres_audit.py`

- [ ] **Step 6.1: Change `replace_rows` from full-window delete to run-idempotent delete**

Replace the broad delete:

```sql
DELETE FROM token_radar_rows
WHERE projection_version = %s AND "window" = %s AND scope = %s
```

with:

```sql
DELETE FROM token_radar_rows
WHERE projection_version = %s
  AND "window" = %s
  AND scope = %s
  AND computed_at_ms = %s
```

Reason: `latest_rows` already selects `MAX(computed_at_ms)`, so old rows can remain without changing read-model behavior.

- [ ] **Step 6.2: Update stale-run protection**

Keep the existing check that rejects writes older than the current max `computed_at_ms`. It prevents out-of-order historical writes from becoming latest.

- [ ] **Step 6.3: Update factor contract validation**

Require:

```python
for key in ("families", "gates", "data_health", "composite", "normalization"):
    payload = factor_snapshot.get(key)
    if not isinstance(payload, dict) or not payload:
        raise ValueError(...)
```

Reject:
- mismatched `schema_version`;
- old `hard_gates`;
- missing v2 family keys.

- [ ] **Step 6.4: Add retention tests**

Add tests:
- inserting `computed_at_ms=1000` then `computed_at_ms=2000` leaves both runs in the table;
- `latest_rows` returns only the `2000` run;
- inserting `computed_at_ms=1500` after `2000` returns `False`;
- inserting the same `computed_at_ms=2000` replaces only that run.

- [ ] **Step 6.5: Run repository tests**

Run:

```bash
uv run pytest tests/test_token_radar_repository.py -q
```

Expected: historical rows are retained and latest reads stay stable.

## Task 7: Add Evaluation Settlement On Existing Tables

**Files:**
- Create: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_factor_evaluation_repository.py`
- Create: `src/gmgn_twitter_intel/domains/token_intel/services/token_factor_evaluation.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/price_observation_repository.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/repository_session.py`
- Create: `tests/test_token_factor_evaluation.py`

- [ ] **Step 7.1: Add price exit lookup**

Add:

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
        WHERE subject_type = %s AND subject_id = %s AND observed_at_ms >= %s
        ORDER BY observed_at_ms ASC, observation_id ASC
        LIMIT 1
        """,
        (subject_type, subject_id, int(at_or_after_ms)),
    ).fetchone()
    return dict(row) if row else None
```

- [ ] **Step 7.2: Create focused evaluation repository**

Responsibilities:
- `historical_radar_rows(factor_version, window, scope, horizon_ms, generated_at_ms, limit)`
- `upsert_score_evaluation(summary)`
- `latest_score_evaluations(horizon, window, scope, score_version)`

Use `score_version = TOKEN_FACTOR_SNAPSHOT_VERSION`.

- [ ] **Step 7.3: Implement settlement service**

Add:

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
- entry price: latest `price_observations` at or before `computed_at_ms`, with non-null `price_usd`;
- exit price: first `price_observations` at or after `computed_at_ms + horizon_ms`, with non-null `price_usd`;
- unsettled if entry or exit is missing;
- actual return: `(exit_price - entry_price) / entry_price`;
- bucket by final `composite.rank_score`: `0-19`, `20-39`, `40-59`, `60-79`, `80-100`;
- directional hit: return `> 0`;
- Spearman IC: correlation of `rank_score` versus actual return across settled rows;
- ICIR: daily IC mean divided by daily IC standard deviation when at least two daily IC values exist, otherwise `null`.

- [ ] **Step 7.4: Add tests**

Test cases:
- unsettled rows increase `snapshot_count` but not `settled_count`;
- bucket summaries upsert into `token_score_evaluations`;
- Spearman IC is positive when higher scores have higher returns;
- IC is `None` when fewer than three settled rows exist.

- [ ] **Step 7.5: Run evaluation tests**

Run:

```bash
uv run pytest tests/test_token_factor_evaluation.py -q
```

Expected: bucket rows and IC diagnostics are deterministic.

## Task 8: Add Minimal Migration For Diagnostics Columns And Indexes

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260511_0025_token_factor_eval_diagnostics.py`
- Modify: `tests/test_migrations.py` or the existing migration test file if present.

- [ ] **Step 8.1: Add migration**

Migration body:

```python
from __future__ import annotations

from alembic import op

revision = "20260511_0025"
down_revision = "20260511_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE token_score_evaluations
          ADD COLUMN IF NOT EXISTS sample_start_ms BIGINT,
          ADD COLUMN IF NOT EXISTS sample_end_ms BIGINT,
          ADD COLUMN IF NOT EXISTS spearman_ic DOUBLE PRECISION,
          ADD COLUMN IF NOT EXISTS icir DOUBLE PRECISION,
          ADD COLUMN IF NOT EXISTS score_stddev DOUBLE PRECISION NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_score_evaluations_generated
          ON token_score_evaluations(horizon, "window", scope, score_version, generated_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_rows_settlement
          ON token_radar_rows(factor_version, "window", scope, computed_at_ms, target_type, target_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_radar_rows_settlement")
    op.execute("DROP INDEX IF EXISTS idx_token_score_evaluations_generated")
    op.execute("ALTER TABLE token_score_evaluations DROP COLUMN IF EXISTS diagnostics_json")
    op.execute("ALTER TABLE token_score_evaluations DROP COLUMN IF EXISTS score_stddev")
    op.execute("ALTER TABLE token_score_evaluations DROP COLUMN IF EXISTS icir")
    op.execute("ALTER TABLE token_score_evaluations DROP COLUMN IF EXISTS spearman_ic")
    op.execute("ALTER TABLE token_score_evaluations DROP COLUMN IF EXISTS sample_end_ms")
    op.execute("ALTER TABLE token_score_evaluations DROP COLUMN IF EXISTS sample_start_ms")
```

- [ ] **Step 8.2: Run migration checks**

Run:

```bash
uv run gmgn-twitter-intel db migrate
uv run gmgn-twitter-intel db health
```

Expected: database migrates to `20260511_0025` and health reports ready.

## Task 9: Add Factor Diagnostics CLI And Tighten Radar Audit

**Files:**
- Create: `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_diagnostics.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/main.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_token_radar_audit_cli.py`
- Create: `tests/test_factor_diagnostics.py`

- [ ] **Step 9.1: Implement diagnostics**

Add:

```python
def factor_distribution_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ...
```

Output fields:
- `row_count`
- `rank_score_unique_count`
- `rank_score_stddev`
- `rank_score_saturation_100_share`
- `family_saturation_100_share`
- `gate_block_counts`
- `data_health_counts`
- `ok`
- `violations`

Violation rules:
- `row_count > 20` and `rank_score_unique_count <= 3`;
- saturation at 100 exceeds 25% for any alpha family with at least 20 non-null scores;
- old family keys appear;
- `hard_gates` appears.

- [ ] **Step 9.2: Add CLI commands**

Under `ops` add:

```bash
gmgn-twitter-intel ops factor-diagnostics --window 1h --scope all --limit 200
gmgn-twitter-intel ops settle-token-factors --window 1h --scope all --horizon 1h --limit 1000
```

Parser args:
- `factor-diagnostics`: `--window`, `--scope`, `--limit`
- `settle-token-factors`: `--window`, `--scope`, `--horizon`, `--limit`, hidden `--now-ms`

- [ ] **Step 9.3: Update `audit-token-radar`**

Audit must now require:
- `schema_version == TOKEN_FACTOR_SNAPSHOT_VERSION`;
- `families` exactly contain `TOKEN_RADAR_FACTOR_FAMILIES`;
- `gates`, `data_health`, `normalization`, and `composite` exist;
- no old runtime payloads;
- high alert only when `gates.eligible_for_high_alert` is true.

- [ ] **Step 9.4: Run CLI tests**

Run:

```bash
uv run pytest tests/test_cli.py tests/test_token_radar_audit_cli.py tests/test_factor_diagnostics.py -q
```

Expected: help includes new commands, audit rejects old shape, diagnostics detect saturation.

## Task 10: Update Pulse, Notifications, API, And Frontend Consumers

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py`
- Modify: `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/http.py` only if response shaping assumes old paths.
- Modify: `web/src/api/types.ts`
- Modify: `web/src/components/SignalLabPulse.tsx`
- Modify: `web/src/components/PulseDetailPage.tsx`
- Modify: `web/src/components/SignalLabInspector.tsx`
- Modify: `web/src/components/ScoreLedger.tsx`
- Modify: relevant frontend tests under `web/src`.

- [ ] **Step 10.1: Hard-cut backend readers to v2 keys**

Replace old reads:

```python
snapshot["hard_gates"]
snapshot["families"]["identity"]
snapshot["families"]["market_quality"]
snapshot["families"]["timing"]
```

with:

```python
snapshot["gates"]
snapshot["data_health"]["identity"]
snapshot["data_health"]["market"]
snapshot["families"]["attention_heat"]
snapshot["families"]["diffusion_quality"]
snapshot["normalization"]
snapshot["composite"]
```

- [ ] **Step 10.2: Update pulse gate semantics**

Pulse candidate high-alert eligibility:
- requires `snapshot["gates"]["eligible_for_high_alert"]`;
- uses `snapshot["composite"]["rank_score"]`;
- includes `blocked_reasons` in the rejection explanation;
- never treats market cap, holders, native market id, symbol, or social signal start as positive reasons.

- [ ] **Step 10.3: Update notifications**

Notification body should mention:
- `rank_score`;
- strongest alpha families by normalized score;
- gate blocks if downgraded;
- data-health warnings if market or semantic data is missing.

- [ ] **Step 10.4: Update frontend type and ledger rendering**

TypeScript snapshot model must expose:
- `gates`
- `data_health`
- `families`
- `normalization`
- `composite`

Score ledger should render:
- Alpha family rows only.
- Gate block panel separately from score rows.
- Cross-section rank and cohort size near rank score.

- [ ] **Step 10.5: Run backend and frontend consumer tests**

Run:

```bash
uv run pytest tests/test_pulse_candidate_gate.py tests/test_pulse_candidate_worker.py tests/test_signal_pulse_service.py tests/test_notification_rules.py -q
npm test -- --run
```

Expected: backend consumers no longer rely on old snapshot keys and frontend renders v2 score ledger.

## Task 11: Documentation And Generated Surfaces

**Files:**
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/TECH_DEBT.md`
- Modify: `docs/generated/cli-help.md`

- [ ] **Step 11.1: Document factor engineering contract**

In `docs/CONTRACTS.md`, document:
- v2 snapshot shape;
- gate/data-health/alpha split;
- no compatibility for old runtime shape;
- evaluation command outputs.

- [ ] **Step 11.2: Document data flow**

In `docs/ARCHITECTURE.md`, update Token Radar flow:

```text
source rows -> raw factor snapshot -> cross-section normalization -> retained radar row -> pulse/notification/API -> settlement diagnostics
```

- [ ] **Step 11.3: Update tech debt**

Remove or close any entry claiming token factor snapshot is unevaluable or placeholder-heavy. Add a remaining debt item only if it is real after implementation, such as longer-horizon evaluation sample size.

- [ ] **Step 11.4: Regenerate CLI help**

Run:

```bash
uv run gmgn-twitter-intel --help > /tmp/gmgn-cli-help.txt
uv run gmgn-twitter-intel ops --help > /tmp/gmgn-ops-help.txt
```

Then update `docs/generated/cli-help.md` using the existing generated-doc format in that file.

## Task 12: End-To-End Verification

**Files:**
- No new source files beyond previous tasks.

- [ ] **Step 12.1: Run full Python verification**

Run:

```bash
uv run ruff check .
uv run python -m compileall src tests
uv run pytest
```

Expected: all pass.

- [ ] **Step 12.2: Run frontend verification**

Run:

```bash
npm test -- --run
npm run build
```

Expected: all pass.

- [ ] **Step 12.3: Run local operational smoke**

Run:

```bash
uv run gmgn-twitter-intel db health
uv run gmgn-twitter-intel ops rebuild-token-radar --window 1h --scope all --limit 100
uv run gmgn-twitter-intel ops audit-token-radar --window 1h --scope all --limit 100
uv run gmgn-twitter-intel ops factor-diagnostics --window 1h --scope all --limit 200
uv run gmgn-twitter-intel ops settle-token-factors --window 1h --scope all --horizon 1h --limit 1000
```

Expected:
- health ready;
- rebuild writes rows under `token-radar-v11-factor-alpha-gated`;
- audit passes;
- diagnostics no longer show all dominant families at 100;
- settlement writes or reports coverage honestly if insufficient forward price data exists.

- [ ] **Step 12.4: Inspect real 1h output**

Run:

```bash
uv run gmgn-twitter-intel asset-flow --window 1h --scope all --limit 20
```

Expected:
- rank score has visible dispersion;
- factor ledger separates gates from alpha;
- a token like BUTTCOIN can be explained by actual social diffusion/heat rather than symbol, market id, or signal-start presence.

- [ ] **Step 12.5: Final no-compatibility scan**

Run:

```bash
rg -n "token_factor_snapshot_v1|hard_gates|families\\]\\[\\\"identity\\\"|families\\]\\[\\\"market_quality\\\"|social_signal_start_ms.*score" src tests web
```

Expected: no runtime compatibility paths remain. Mentions in migration history or docs explaining the hard cut are acceptable only outside runtime code.

## Review Checklist

- [ ] Every old score source that was a presence fact is either `subject`, `gates`, `data_health`, or `provenance`.
- [ ] Every alpha family is based on variation in social evidence, semantics, timing response, or cross-section.
- [ ] `token_radar_rows` retains historical runs for settlement.
- [ ] `latest_rows` still returns only the newest run.
- [ ] `token_score_evaluations` has real bucket rows keyed by v2 score version.
- [ ] CLI diagnostics make saturation and low dispersion visible.
- [ ] Signal Labs pulse and notifications explain gate blocks separately from alpha score.
- [ ] No runtime code accepts old snapshot shape.

