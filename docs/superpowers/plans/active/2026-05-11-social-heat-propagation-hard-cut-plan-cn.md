# Social Heat Propagation Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-cut Token Radar factor scoring to a professional, auditable social heat and propagation model built from existing GMGN/Twitter/account/enrichment data, with no runtime compatibility for old factor families or old snapshot versions.

**Architecture:** Keep the existing Token Radar projection pipeline and PostgreSQL storage, but replace the current factor contract with `token_factor_snapshot_v3_social_attention`. The chain becomes source rows -> per-mention social atoms -> window aggregates -> social factor families -> cross-section rank -> Pulse/notifications/frontend/evaluation, with identity and market remaining gates rather than alpha.

**Tech Stack:** Python 3.13, pytest, psycopg/PostgreSQL, Alembic, React/TypeScript/Vitest under `web/`, existing `token_radar_rows.factor_snapshot_json`, existing `token_score_evaluations`.

---

## Source Scope

This plan implements the approved social heat / propagation hard-cut scope from 2026-05-11:

- Existing data only: `events`, `token_intents`, `token_intent_resolutions`, `account_profiles`, `social_event_extractions`, `asset_identity_current`, anchor/current market snapshots, price observations, and `token_radar_rows`.
- No bot detector. The monitored accounts and GMGN directory followers/tags are treated as the curated human network.
- No Twitter engagement ingestion. Likes, replies, retweets, quote counts, views, and full cascade graph are out of scope because they are not in the current data path.
- No compatibility layer. Runtime accepts one current snapshot schema only.
- Primary scientific target: make social heat and propagation rank abnormal, credible, independent human attention instead of raw popularity.

## Target Data Flow

```text
GMGN public stream
  -> events + token_intents + token_intent_resolutions
  -> TokenRadarSourceQuery
       joins events, account_profiles, social_event_extractions,
       asset_identity_current, CEX/feed metadata, anchor price baselines
  -> token_radar_feature_builder
       per-mention source_weight, confidence, text fingerprint,
       semantic hints, author timing, watched/public role
  -> window features
       social_heat inputs, social_propagation inputs,
       semantic_catalyst inputs, timing_risk facts
  -> build_token_factor_snapshot
       schema_version = token_factor_snapshot_v3_social_attention
       families = social_heat, social_propagation, semantic_catalyst, timing_risk
       gates = identity, market, social health, duplicate/concentration, timing caps
  -> TokenRadarProjection._apply_cross_section
       factor ranks inside active cohort, composite.rank_score
  -> token_radar_rows.factor_snapshot_json
  -> Pulse gate / notification rules / API read models / React UI
  -> TokenFactorEvaluationService
       composite, family, and selected factor IC/bucket diagnostics
```

## Hard-Cut Runtime Contract

The only accepted snapshot version is:

```python
TOKEN_FACTOR_SNAPSHOT_VERSION = "token_factor_snapshot_v3_social_attention"
TOKEN_RADAR_PROJECTION_VERSION = "token-radar-v13-social-attention"
TOKEN_RADAR_FACTOR_FAMILIES = (
    "social_heat",
    "social_propagation",
    "semantic_catalyst",
    "timing_risk",
)
```

Runtime readers must reject these old contracts:

- `token_factor_snapshot_v1`
- `token_factor_snapshot_v2_alpha_gated`
- `hard_gates`
- `families.attention_heat`
- `families.diffusion_quality`
- `families.semantic_quality`
- `families.timing_response`
- `families.identity`
- `families.market_quality`
- old `score_json` fallback scores
- stale validator names `require_token_factor_snapshot_v2` and `requireTokenFactorSnapshotV2`

## Factor Definitions

### `social_heat`

Meaning: abnormal attention surprise from credible human accounts.

Composite factors:

- `attention_surprise`: maps `robust_z`, fallback `z_ewma`, fallback `new_burst_score` into 0-100.
- `source_weighted_mentions`: uses `weighted_mentions` from GMGN followers/tags and resolver confidence.
- `attention_acceleration`: uses `mention_delta` and `mention_delta_pct`; repeated long-window count stacking is removed.
- `watched_seed_strength`: watched mention contribution, capped so one watched author cannot create high alert alone.

Facts:

- `mentions_5m`, `mentions_1h`, `mentions_window`
- `previous_mentions`, `mention_delta`, `mention_delta_pct`
- `weighted_mentions`, `stream_share`
- `z_score`, `z_ewma`, `robust_z`, `new_burst_score`
- `baseline_status`, `baseline_sample_count`, `baseline_nonzero_sample_count`
- `watched_mentions`, `latest_seen_ms`

### `social_propagation`

Meaning: independent human diffusion instead of one account broadcasting or repeated text.

Composite factors:

- `independent_authors`: count of independent authors.
- `source_weighted_effective_authors`: author concentration-adjusted credible author mass.
- `propagation_speed`: second and third independent credible author arrival speed inside the scoring window.
- `watched_to_public_followup`: watched seed followed by non-watched independent authors.
- `duplicate_text_share_penalty`: negative only.
- `top_author_concentration_penalty`: negative only.

Facts:

- `independent_authors`, `effective_authors`, `source_weighted_effective_authors`
- `new_authors`
- `top_author_share`, `duplicate_text_share`, `author_entropy`
- `time_to_second_author_ms`, `time_to_third_author_ms`
- `watched_author_count`, `public_followup_author_count`
- `reproduction_rate`, `top_authors`

### `semantic_catalyst`

Meaning: LLM-enriched context helps explain why attention exists, but cannot override weak heat/propagation.

Composite factors:

- `semantic_impact`: weighted by LLM confidence and coverage.
- `semantic_novelty`: weighted by LLM confidence and coverage.
- `semantic_coverage`: share of source events with usable LLM hints.
- `direction_mix`: explanation fact; bullish/neutral/bearish distribution does not automatically mean high score.

Facts:

- `direction_counts`
- `impact_mean`, `novelty_mean`, `confidence_mean`
- `llm_covered_mentions`, `llm_coverage`

### `timing_risk`

Meaning: timing caps promotion when social signal is late or price has already repriced.

Composite weight: `0.0`.

Factors:

- `pre_social_chase_risk`: negative/cap flag when pre-social price move is already large.
- `post_social_late_risk`: negative/cap flag when post-social move is already too extended.

Facts:

- `price_change_before_social_pct`
- `price_change_since_social_pct`
- `social_signal_start_ms`
- `price_change_status`

### Composite

```text
raw_alpha_score =
  0.45 * social_heat
+ 0.40 * social_propagation
+ 0.15 * semantic_catalyst
+ 0.00 * timing_risk

rank_score = weighted percentile rank of family scores inside active cohort
decision = gate_cap(rank_score, identity/market/social/timing gates)
```

High alert requires:

- identity ready;
- market fresh/ready and DEX floors pass for DEX targets;
- `social_heat >= 55`;
- `social_propagation >= 50`;
- no blocking duplicate text cluster;
- no insufficient independent social source gate;
- rank score high enough after cross-section.

## Exact Files

Source query and feature construction:

- Modify `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py`.
- Modify `src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py`.
- Modify `src/gmgn_twitter_intel/domains/token_intel/scoring/diffusion_health.py`.
- Create `src/gmgn_twitter_intel/domains/token_intel/scoring/social_signal_features.py`.
- Modify `src/gmgn_twitter_intel/domains/token_intel/services/atomic_mention.py` only for naming exports or narrowly tested helper reuse.

Factor contract and projection:

- Modify `src/gmgn_twitter_intel/domains/token_intel/_constants.py`.
- Modify `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py`.
- Modify `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot_contract.py`.
- Modify `src/gmgn_twitter_intel/domains/token_intel/scoring/cross_section_normalizer.py`.
- Modify `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_cohort.py`.
- Modify `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`.
- Modify `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_diagnostics.py`.

Evaluation:

- Modify `src/gmgn_twitter_intel/domains/token_intel/services/token_factor_evaluation.py`.
- Modify `src/gmgn_twitter_intel/domains/token_intel/repositories/token_factor_evaluation_repository.py`.

Backend consumers:

- Modify `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py`.
- Modify `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`.
- Modify `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py`.
- Modify `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_repository.py`.
- Modify `src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_recommendation.py`.
- Modify `src/gmgn_twitter_intel/integrations/openai_agents/pulse_recommendation_agent_client.py`.
- Modify `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py`.
- Modify `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`.
- Modify `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py`.

Frontend consumers:

- Modify `web/src/api/types.ts`.
- Modify `web/src/lib/tokenFactorSnapshot.ts`.
- Modify `web/src/lib/tokenRadar.ts`.
- Modify `web/src/lib/tokenRadar.test.ts`.
- Modify `web/src/components/SignalLabPulse.tsx`.
- Modify `web/src/components/SignalLabPulse.test.tsx`.
- Modify `web/src/components/SignalLabInspector.tsx`.
- Modify `web/src/components/SignalLabInspector.test.tsx`.
- Modify `web/src/App.test.tsx`.

Tests:

- Modify `tests/unit/test_factor_snapshot.py`.
- Modify `tests/architecture/test_no_factor_snapshot_fallback.py`.
- Modify `tests/unit/test_token_radar_feature_builder.py`.
- Modify `tests/unit/test_diffusion_health.py`.
- Create `tests/unit/test_social_signal_features.py`.
- Modify `tests/unit/test_token_radar_apply_cross_section.py`.
- Modify `tests/unit/test_token_radar_projection.py`.
- Modify `tests/unit/test_factor_diagnostics.py`.
- Modify `tests/unit/test_token_factor_evaluation.py`.
- Modify `tests/unit/test_pulse_candidate_gate.py`.
- Modify `tests/unit/test_pulse_candidate_worker.py`.
- Modify `tests/unit/test_signal_pulse_service.py`.
- Modify `tests/unit/test_notification_rules.py`.
- Modify `tests/unit/test_token_radar_repository.py`.
- Modify `tests/unit/test_token_radar_audit_cli.py`.

Docs and generated artifacts:

- Modify `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`.
- Modify `docs/ARCHITECTURE.md`.
- Modify `docs/CONTRACTS.md`.
- Modify `docs/generated/score-versions.md`.
- Modify `docs/TECH_DEBT.md` only if a verification gap remains.

## Task 0: Worktree And Baseline

**Files:**

- Read: `AGENTS.md`
- Read: `docs/WORKFLOW.md`
- Read: `docs/DESIGN_DISCIPLINE.md`

- [ ] **Step 0.1: Create an isolated worktree**

Run:

```bash
git worktree add .worktrees/social-heat-propagation-hard-cut -b codex/social-heat-propagation-hard-cut main
```

Expected: the command exits 0 and creates `.worktrees/social-heat-propagation-hard-cut`.

- [ ] **Step 0.2: Confirm branch and cleanliness**

Run:

```bash
cd .worktrees/social-heat-propagation-hard-cut
git branch --show-current
git status --short --branch
```

Expected:

```text
codex/social-heat-propagation-hard-cut
## codex/social-heat-propagation-hard-cut
```

- [ ] **Step 0.3: Capture current focused baseline**

Run:

```bash
uv run python -m pytest tests/unit/test_factor_snapshot.py tests/unit/test_token_radar_feature_builder.py tests/unit/test_diffusion_health.py tests/unit/test_token_radar_apply_cross_section.py tests/unit/test_token_factor_evaluation.py -q
```

Expected: the current mainline focused tests pass before changes begin.

## Task 1: Hard-Cut Contract Version And Family Names

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/token_intel/_constants.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot_contract.py`
- Modify: `web/src/lib/tokenFactorSnapshot.ts`
- Modify: `tests/unit/test_factor_snapshot.py`
- Modify: `tests/architecture/test_no_factor_snapshot_fallback.py`
- Modify: `web/src/lib/tokenRadar.test.ts`

- [ ] **Step 1.1: Write failing backend contract tests**

In `tests/unit/test_factor_snapshot.py`, change the exported contract assertion to:

```python
def test_scoring_package_exports_factor_snapshot_contract() -> None:
    from gmgn_twitter_intel.domains.token_intel import scoring

    assert TOKEN_FACTOR_SNAPSHOT_VERSION == "token_factor_snapshot_v3_social_attention"
    assert FACTOR_FAMILIES == (
        "social_heat",
        "social_propagation",
        "semantic_catalyst",
        "timing_risk",
    )
    assert scoring.TOKEN_FACTOR_SNAPSHOT_VERSION == TOKEN_FACTOR_SNAPSHOT_VERSION
    assert scoring.FACTOR_FAMILIES == FACTOR_FAMILIES
    assert scoring.DEX_HIGH_ALERT_FLOORS == DEX_HIGH_ALERT_FLOORS
    assert scoring.build_token_factor_snapshot is build_token_factor_snapshot
```

Add this old-family rejection guard to `tests/architecture/test_no_factor_snapshot_fallback.py`:

```python
LEGACY_FACTOR_FAMILY_PATTERNS = (
    '"attention_heat"',
    '"diffusion_quality"',
    '"semantic_quality"',
    '"timing_response"',
    '"social_attention"',
    '"social_quality"',
    '"market_quality"',
    '"identity"',
)

LEGACY_FACTOR_CONTRACT_FUNCTION_PATTERNS = (
    "require_token_factor_snapshot_v2",
    "is_token_factor_snapshot_v2",
    "requireTokenFactorSnapshotV2",
)


def test_runtime_has_no_previous_factor_family_literals() -> None:
    offenders = _matches(
        _python_runtime_files(),
        patterns=LEGACY_FACTOR_FAMILY_PATTERNS,
    )

    assert offenders == []


def test_runtime_has_no_stale_v2_factor_contract_function_names() -> None:
    offenders = _matches(
        _python_runtime_files(),
        patterns=LEGACY_FACTOR_CONTRACT_FUNCTION_PATTERNS,
    )

    assert offenders == []
```

- [ ] **Step 1.2: Run failing backend tests**

Run:

```bash
uv run python -m pytest tests/unit/test_factor_snapshot.py::test_scoring_package_exports_factor_snapshot_contract tests/architecture/test_no_factor_snapshot_fallback.py::test_runtime_has_no_previous_factor_family_literals tests/architecture/test_no_factor_snapshot_fallback.py::test_runtime_has_no_stale_v2_factor_contract_function_names -q
```

Expected: fails because constants and runtime readers still mention v2 family names.

- [ ] **Step 1.3: Update Python constants**

In `src/gmgn_twitter_intel/domains/token_intel/_constants.py`, set:

```python
TOKEN_RADAR_PROJECTION_VERSION = "token-radar-v13-social-attention"
TOKEN_FACTOR_SNAPSHOT_VERSION = "token_factor_snapshot_v3_social_attention"
TOKEN_RADAR_FACTOR_FAMILIES = (
    "social_heat",
    "social_propagation",
    "semantic_catalyst",
    "timing_risk",
)
```

- [ ] **Step 1.4: Rename and update backend snapshot validator with no old acceptance**

In `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot_contract.py`, rename:

```python
def require_token_factor_snapshot_v2(...)
def is_token_factor_snapshot_v2(...)
```

to:

```python
def require_token_factor_snapshot(...)
def is_token_factor_snapshot(...)
```

Do not keep aliases under the old names. Preserve the current mainline top-level `market` section introduced by `token-radar-v12-anchor-live-hard-cut`; the v3 contract still requires it:

```python
TOKEN_FACTOR_SNAPSHOT_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "subject",
        "market",
        "gates",
        "data_health",
        "families",
        "normalization",
        "composite",
        "provenance",
    }
)
```

Keep exact top-level validation, but ensure the family allow-list comes only from `TOKEN_RADAR_FACTOR_FAMILIES`. Add explicit old-key rejection before missing-family checks:

```python
FORBIDDEN_FACTOR_FAMILY_KEYS = frozenset(
    {
        "attention_heat",
        "diffusion_quality",
        "semantic_quality",
        "timing_response",
        "social_attention",
        "social_quality",
        "market_quality",
        "identity",
    }
)
```

Inside `require_token_factor_snapshot`, after `family_keys = set(str(key) for key in families)`, add:

```python
old_families = sorted(FORBIDDEN_FACTOR_FAMILY_KEYS & family_keys)
if old_families:
    raise ValueError(f"{field_name}.families.{old_families[0]} is not allowed")
```

Update imports in these files to the renamed validator in the same task so runtime does not carry stale v2 API names:

- `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py`
- `src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_recommendation.py`

- [ ] **Step 1.5: Update frontend contract validator**

In `web/src/lib/tokenFactorSnapshot.ts`, rename `requireTokenFactorSnapshotV2` to `requireTokenFactorSnapshot`, then set:

```ts
export const TOKEN_FACTOR_SNAPSHOT_SCHEMA = "token_factor_snapshot_v3_social_attention";
const ALPHA_FAMILIES: TokenFactorFamilyKey[] = [
  "social_heat",
  "social_propagation",
  "semantic_catalyst",
  "timing_risk",
];
```

Add a forbidden-family check before `missingFamily`:

```ts
const FORBIDDEN_FACTOR_FAMILIES = new Set([
  "attention_heat",
  "diffusion_quality",
  "semantic_quality",
  "timing_response",
  "social_attention",
  "social_quality",
  "market_quality",
  "identity",
]);
const oldFamily = familyKeys.find((family) => FORBIDDEN_FACTOR_FAMILIES.has(family));
if (oldFamily) {
  throw new Error(`token_factor_snapshot_contract:${fieldName}.families.${oldFamily}`);
}
```

- [ ] **Step 1.6: Run focused contract tests**

Run:

```bash
uv run python -m pytest tests/unit/test_factor_snapshot.py::test_scoring_package_exports_factor_snapshot_contract tests/architecture/test_no_factor_snapshot_fallback.py -q
cd web && npm run test -- tokenRadar.test.ts
```

Expected: Python tests still fail until snapshot producer is updated; frontend validator tests fail until fixtures use v3.

- [ ] **Step 1.7: Commit contract skeleton**

Run:

```bash
git add src/gmgn_twitter_intel/domains/token_intel/_constants.py src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot_contract.py src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_recommendation.py web/src/lib/tokenFactorSnapshot.ts tests/unit/test_factor_snapshot.py tests/architecture/test_no_factor_snapshot_fallback.py web/src/lib/tokenRadar.test.ts
git commit -m "feat: hard cut token factor snapshot contract"
```

Expected: commit succeeds after tests for this task are either passing or documented as expected failing until Task 4.

## Task 2: Add Pure Social Signal Feature Helpers

**Files:**

- Create: `src/gmgn_twitter_intel/domains/token_intel/scoring/social_signal_features.py`
- Create: `tests/unit/test_social_signal_features.py`

- [ ] **Step 2.1: Write failing tests for source-weighted attention and propagation timing**

Create `tests/unit/test_social_signal_features.py`:

```python
from __future__ import annotations

import pytest

from gmgn_twitter_intel.domains.token_intel.scoring.social_signal_features import (
    author_entropy,
    public_followup_author_count,
    source_weighted_effective_authors,
    time_to_nth_independent_author_ms,
)


def row(event_id: str, *, author: str, received_at_ms: int, weight: float, watched: bool = False) -> dict:
    return {
        "event_id": event_id,
        "author_handle": author,
        "received_at_ms": received_at_ms,
        "is_watched": watched,
        "_source_weight": weight,
    }


def test_source_weighted_effective_authors_penalizes_single_author_repeat_cluster() -> None:
    repeated = [
        row("a1", author="alice", received_at_ms=1_000, weight=1.0),
        row("a2", author="alice", received_at_ms=2_000, weight=1.0),
        row("a3", author="alice", received_at_ms=3_000, weight=1.0),
    ]
    independent = [
        row("a1", author="alice", received_at_ms=1_000, weight=0.8),
        row("b1", author="bob", received_at_ms=2_000, weight=0.7),
        row("c1", author="carol", received_at_ms=3_000, weight=0.6),
    ]

    assert source_weighted_effective_authors(independent) > source_weighted_effective_authors(repeated)
    assert source_weighted_effective_authors(repeated) == pytest.approx(1.0)


def test_time_to_nth_independent_author_uses_first_distinct_author_arrivals() -> None:
    rows = [
        row("a1", author="alice", received_at_ms=10_000, weight=1.0),
        row("a2", author="alice", received_at_ms=12_000, weight=1.0),
        row("b1", author="bob", received_at_ms=25_000, weight=1.0),
        row("c1", author="carol", received_at_ms=45_000, weight=1.0),
    ]

    assert time_to_nth_independent_author_ms(rows, 2) == 15_000
    assert time_to_nth_independent_author_ms(rows, 3) == 35_000
    assert time_to_nth_independent_author_ms(rows, 4) is None


def test_public_followup_count_requires_watched_seed_then_non_watched_authors() -> None:
    rows = [
        row("seed", author="alice", received_at_ms=10_000, weight=1.0, watched=True),
        row("repeat", author="alice", received_at_ms=11_000, weight=1.0, watched=False),
        row("public-1", author="bob", received_at_ms=15_000, weight=1.0, watched=False),
        row("public-2", author="carol", received_at_ms=20_000, weight=1.0, watched=False),
    ]

    assert public_followup_author_count(rows) == 2


def test_author_entropy_increases_with_independent_distribution() -> None:
    concentrated = [
        row("a1", author="alice", received_at_ms=1, weight=1.0),
        row("a2", author="alice", received_at_ms=2, weight=1.0),
        row("b1", author="bob", received_at_ms=3, weight=1.0),
    ]
    balanced = [
        row("a1", author="alice", received_at_ms=1, weight=1.0),
        row("b1", author="bob", received_at_ms=2, weight=1.0),
        row("c1", author="carol", received_at_ms=3, weight=1.0),
    ]

    assert author_entropy(balanced) > author_entropy(concentrated)
```

- [ ] **Step 2.2: Run tests and verify failure**

Run:

```bash
uv run python -m pytest tests/unit/test_social_signal_features.py -q
```

Expected: fails with `ModuleNotFoundError` for `social_signal_features`.

- [ ] **Step 2.3: Implement pure helper module**

Create `src/gmgn_twitter_intel/domains/token_intel/scoring/social_signal_features.py`:

```python
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any


def source_weighted_effective_authors(rows: list[dict[str, Any]]) -> float:
    weights_by_author: dict[str, float] = defaultdict(float)
    for row in rows:
        handle = _handle(row)
        if not handle:
            continue
        weights_by_author[handle] += max(0.0, _float(row.get("_source_weight"), default=0.0))
    if not weights_by_author:
        return 0.0
    total = sum(weights_by_author.values())
    if total <= 0.0:
        return 0.0
    hhi = sum((weight / total) ** 2 for weight in weights_by_author.values())
    return round(1.0 / max(hhi, 1e-9), 6)


def time_to_nth_independent_author_ms(rows: list[dict[str, Any]], n: int) -> int | None:
    if n <= 0:
        return None
    arrivals: dict[str, int] = {}
    for row in rows:
        handle = _handle(row)
        if not handle:
            continue
        received = _int(row.get("received_at_ms"))
        if received is None:
            continue
        arrivals[handle] = min(arrivals.get(handle, received), received)
    if len(arrivals) < n:
        return None
    ordered = sorted(arrivals.values())
    return ordered[n - 1] - ordered[0]


def public_followup_author_count(rows: list[dict[str, Any]]) -> int:
    watched_seed_authors = {
        _handle(row)
        for row in rows
        if row.get("is_watched") and _handle(row) and _int(row.get("received_at_ms")) is not None
    }
    if not watched_seed_authors:
        return 0
    first_watched_ms = min(
        _int(row.get("received_at_ms")) or 0
        for row in rows
        if row.get("is_watched") and _handle(row)
    )
    public_authors = {
        _handle(row)
        for row in rows
        if not row.get("is_watched")
        and _handle(row)
        and _handle(row) not in watched_seed_authors
        and (_int(row.get("received_at_ms")) or 0) >= first_watched_ms
    }
    return len(public_authors)


def author_entropy(rows: list[dict[str, Any]]) -> float:
    counts = Counter(_handle(row) for row in rows if _handle(row))
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    value = -sum((count / total) * math.log(count / total) for count in counts.values())
    return round(value, 6)


def _handle(row: dict[str, Any]) -> str:
    return str(row.get("author_handle") or "").strip().lstrip("@").lower()


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed
```

- [ ] **Step 2.4: Run helper tests**

Run:

```bash
uv run python -m pytest tests/unit/test_social_signal_features.py -q
```

Expected: all tests pass.

- [ ] **Step 2.5: Commit helper module**

Run:

```bash
git add src/gmgn_twitter_intel/domains/token_intel/scoring/social_signal_features.py tests/unit/test_social_signal_features.py
git commit -m "feat: add social signal feature primitives"
```

Expected: commit succeeds.

## Task 3: Materialize Social Heat And Propagation Inputs In Feature Builder

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/diffusion_health.py`
- Modify: `tests/unit/test_token_radar_feature_builder.py`
- Modify: `tests/unit/test_diffusion_health.py`

- [ ] **Step 3.1: Write failing feature-builder tests for new fields**

Add to `tests/unit/test_token_radar_feature_builder.py`:

```python
def test_feature_builder_exposes_social_heat_and_propagation_inputs():
    now_ms = 1_700_000_000_000
    rows = [
        row("event-1", received_at_ms=now_ms - 240_000, author="alice", gmgn_platform_followers=20_000, gmgn_user_tags=["kol"]),
        row("event-2", received_at_ms=now_ms - 180_000, author="bob", gmgn_platform_followers=10_000, gmgn_user_tags=["trader"], is_watched=False),
        row("event-3", received_at_ms=now_ms - 60_000, author="carol", gmgn_platform_followers=5_000, gmgn_user_tags=["other"], is_watched=False),
    ]

    features = build_radar_features(
        window_rows=rows,
        context_rows=rows,
        previous_rows=[],
        now_ms=now_ms,
        window_ms=5 * 60_000,
        total_window_events=3,
    )

    assert features.attention["mentions_window"] == 3
    assert features.attention["weighted_mentions"] > 1.0
    assert features.attention["attention_acceleration"] is not None
    assert features.propagation["source_weighted_effective_authors"] > 2.0
    assert features.propagation["time_to_second_author_ms"] == 60_000
    assert features.propagation["time_to_third_author_ms"] == 180_000
    assert features.propagation["public_followup_author_count"] == 2
    assert features.propagation["author_entropy"] > 1.0
```

- [ ] **Step 3.2: Write failing diffusion health entropy test**

Add to `tests/unit/test_diffusion_health.py`:

```python
def test_diffusion_health_reports_author_entropy():
    rows = [
        {"event_id": "a", "author_handle": "alice", "received_at_ms": 1_000, "text_clean": "$ABC one"},
        {"event_id": "b", "author_handle": "bob", "received_at_ms": 2_000, "text_clean": "$ABC two"},
        {"event_id": "c", "author_handle": "carol", "received_at_ms": 3_000, "text_clean": "$ABC three"},
    ]

    health = diffusion_health(rows, watched_author_handles=set())

    assert health["author_entropy"] > 1.0
```

- [ ] **Step 3.3: Run failing tests**

Run:

```bash
uv run python -m pytest tests/unit/test_token_radar_feature_builder.py::test_feature_builder_exposes_social_heat_and_propagation_inputs tests/unit/test_diffusion_health.py::test_diffusion_health_reports_author_entropy -q
```

Expected: fails because fields are missing.

- [ ] **Step 3.4: Annotate window rows with source weight**

In `src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py`, import:

```python
from gmgn_twitter_intel.domains.token_intel.scoring.social_signal_features import (
    author_entropy,
    public_followup_author_count,
    source_weighted_effective_authors,
    time_to_nth_independent_author_ms,
)
```

At the start of `build_radar_features`, replace:

```python
window = list(window_rows)
```

with:

```python
window = [_with_source_weight(row) for row in window_rows]
```

Add near `_atomic_quality`:

```python
def _with_source_weight(row: dict[str, Any]) -> dict[str, Any]:
    confidence = _confidence(row)
    return {**row, "_source_weight": _atomic_quality(row) * confidence}
```

- [ ] **Step 3.5: Extend heat features**

In `_heat_features`, after `mention_delta_pct`, add:

```python
attention_acceleration = mention_delta / max(1, previous_mentions)
```

Return these keys:

```python
"attention_acceleration": attention_acceleration,
"weighted_mentions": weighted_mentions,
```

In the `attention = {**attention, ...}` merge, include:

```python
"weighted_mentions": heat["weighted_mentions"],
"attention_acceleration": heat["attention_acceleration"],
```

- [ ] **Step 3.6: Extend propagation features**

In `_propagation_features`, add return keys:

```python
"source_weighted_effective_authors": source_weighted_effective_authors(window),
"time_to_second_author_ms": time_to_nth_independent_author_ms(window, 2),
"time_to_third_author_ms": time_to_nth_independent_author_ms(window, 3),
"public_followup_author_count": public_followup_author_count(window),
"author_entropy": author_entropy(window),
```

- [ ] **Step 3.7: Extend diffusion health**

In `src/gmgn_twitter_intel/domains/token_intel/scoring/diffusion_health.py`, import the helper:

```python
from gmgn_twitter_intel.domains.token_intel.scoring.social_signal_features import author_entropy
```

Add to the returned dict:

```python
"author_entropy": author_entropy(mentions),
```

- [ ] **Step 3.8: Run focused feature tests**

Run:

```bash
uv run python -m pytest tests/unit/test_token_radar_feature_builder.py tests/unit/test_diffusion_health.py tests/unit/test_social_signal_features.py -q
```

Expected: tests pass.

- [ ] **Step 3.9: Commit feature materialization**

Run:

```bash
git add src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py src/gmgn_twitter_intel/domains/token_intel/scoring/diffusion_health.py tests/unit/test_token_radar_feature_builder.py tests/unit/test_diffusion_health.py
git commit -m "feat: materialize social heat propagation inputs"
```

Expected: commit succeeds.

## Task 4: Rewrite Factor Snapshot Families

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py`
- Modify: `tests/unit/test_factor_snapshot.py`

- [ ] **Step 4.1: Write failing snapshot shape and formula tests**

Update `tests/unit/test_factor_snapshot.py` shape assertions:

```python
assert set(snapshot) == {
    "schema_version",
    "subject",
    "market",
    "gates",
    "data_health",
    "families",
    "normalization",
    "composite",
    "provenance",
}
assert set(snapshot["families"]) == {
    "social_heat",
    "social_propagation",
    "semantic_catalyst",
    "timing_risk",
}
assert snapshot["schema_version"] == "token_factor_snapshot_v3_social_attention"
assert "attention_heat" not in snapshot["families"]
assert "diffusion_quality" not in snapshot["families"]
```

Add tests:

```python
def test_social_heat_uses_surprise_and_weighted_mentions_not_overlapping_long_counts() -> None:
    snapshot = _strong_dex_snapshot(
        attention={
            "mentions_1h": 20,
            "mentions_4h": 200,
            "mentions_24h": 500,
            "mentions_window": 3,
            "weighted_mentions": 2.4,
            "robust_z": 3.0,
            "z_ewma": 2.0,
            "new_burst_score": 0.0,
            "mention_delta": 3,
            "mention_delta_pct": 3.0,
            "attention_acceleration": 3.0,
            "watched_mentions": 1,
        }
    )

    factors = snapshot["families"]["social_heat"]["factors"]
    assert set(factors) >= {
        "attention_surprise",
        "source_weighted_mentions",
        "attention_acceleration",
        "watched_seed_strength",
    }
    assert "mentions_4h" not in factors
    assert "mentions_24h" not in factors
    assert snapshot["families"]["social_heat"]["score"] > 60


def test_social_propagation_penalizes_single_author_copy_pasta_below_independent_authors() -> None:
    independent = _strong_dex_snapshot(
        social_quality={
            "independent_authors": 3,
            "effective_authors": 3.0,
            "source_weighted_effective_authors": 2.8,
            "duplicate_text_share": 0.0,
            "top_author_share": 0.34,
            "time_to_second_author_ms": 120_000,
            "time_to_third_author_ms": 240_000,
            "public_followup_author_count": 2,
            "author_entropy": 1.09,
        }
    )
    repeated = _strong_dex_snapshot(
        social_quality={
            "independent_authors": 1,
            "effective_authors": 1.0,
            "source_weighted_effective_authors": 1.0,
            "duplicate_text_share": 1.0,
            "top_author_share": 1.0,
            "time_to_second_author_ms": None,
            "time_to_third_author_ms": None,
            "public_followup_author_count": 0,
            "author_entropy": 0.0,
        }
    )

    assert independent["families"]["social_propagation"]["score"] > repeated["families"]["social_propagation"]["score"]
    assert "duplicate_text_share_high" in repeated["gates"]["blocked_reasons"]
    assert repeated["composite"]["recommended_decision"] != "high_alert"


def test_timing_risk_has_zero_weight_and_never_adds_positive_alpha() -> None:
    snapshot = _strong_dex_snapshot(
        timing={
            "price_change_before_social_pct": 0.25,
            "price_change_since_social_pct": 0.35,
            "social_signal_start_ms": 1_778_000_001_000,
        }
    )

    family = snapshot["families"]["timing_risk"]
    assert family["weight"] == 0.0
    assert family["score"] <= 0
    assert "social_signal_start_ms" not in family["factors"]
    assert "timing_chase_risk" in snapshot["gates"]["risk_reasons"]
```

- [ ] **Step 4.2: Run failing snapshot tests**

Run:

```bash
uv run python -m pytest tests/unit/test_factor_snapshot.py -q
```

Expected: fails because producer still emits old families.

- [ ] **Step 4.3: Replace family weights**

In `factor_snapshot.py`, set:

```python
_FAMILY_WEIGHTS = {
    "social_heat": 0.45,
    "social_propagation": 0.40,
    "semantic_catalyst": 0.15,
    "timing_risk": 0.0,
}
```

- [ ] **Step 4.4: Replace family construction**

In `build_token_factor_snapshot`, replace the `families = { ... }` block with:

```python
families = {
    "social_heat": _social_heat_family(attention=attention),
    "social_propagation": _social_propagation_family(social_quality=social_quality),
    "semantic_catalyst": _semantic_catalyst_family(social_semantics=social_semantics, social_quality=social_quality),
    "timing_risk": _timing_risk_family(timing=timing, market=market),
}
```

Delete `_attention_heat_family`, `_diffusion_quality_family`, `_semantic_quality_family`, and `_timing_response_family` after their replacements exist. Do not leave wrapper functions under old names.

- [ ] **Step 4.5: Implement `social_heat` factors**

Add:

```python
def _social_heat_family(*, attention: dict[str, Any]) -> dict[str, Any]:
    mentions_window = _optional_int(attention.get("mentions_window"))
    weighted_mentions = _optional_float(attention.get("weighted_mentions"))
    robust_z = _optional_float(attention.get("robust_z"))
    z_ewma = _optional_float(attention.get("z_ewma"))
    z_score = _optional_float(attention.get("z_score"))
    new_burst_score = _optional_float(attention.get("new_burst_score"))
    acceleration = _optional_float(attention.get("attention_acceleration"))
    watched_mentions = _optional_int(attention.get("watched_mentions"))
    facts = {
        "mentions_5m": _optional_int(attention.get("mentions_5m")),
        "mentions_1h": _count_int(attention.get("mentions_1h")),
        "mentions_window": _count_int(mentions_window),
        "previous_mentions": _count_int(attention.get("previous_mentions")),
        "mention_delta": _optional_int(attention.get("mention_delta")),
        "mention_delta_pct": _optional_float(attention.get("mention_delta_pct")),
        "attention_acceleration": acceleration,
        "weighted_mentions": weighted_mentions,
        "stream_share": _optional_float(attention.get("stream_share")),
        "z_score": z_score,
        "z_ewma": z_ewma,
        "robust_z": robust_z,
        "new_burst_score": new_burst_score,
        "baseline_status": _optional_str(attention.get("baseline_status")),
        "baseline_sample_count": _optional_int(attention.get("baseline_sample_count")),
        "baseline_nonzero_sample_count": _optional_int(attention.get("baseline_nonzero_sample_count")),
        "watched_mentions": _count_int(watched_mentions),
        "latest_seen_ms": _optional_int(attention.get("latest_seen_ms")),
    }
    return _family(
        "social_heat",
        facts=facts,
        factors=[
            _z_or_new_burst_factor(robust_z=robust_z, z_ewma=z_ewma, z_score=z_score, new_burst_score=new_burst_score),
            _count_factor("social_heat", "source_weighted_mentions", weighted_mentions, scale=3),
            _acceleration_factor(acceleration),
            _count_factor("social_heat", "watched_seed_strength", watched_mentions, scale=2),
        ],
    )
```

Add helpers:

```python
def _z_or_new_burst_factor(*, robust_z: float | None, z_ewma: float | None, z_score: float | None, new_burst_score: float | None) -> dict[str, Any]:
    value = robust_z if robust_z is not None else z_ewma if z_ewma is not None else z_score
    if value is not None:
        score = max(0.0, min(100.0, 25.0 + value * 22.5))
        raw_value: Any = value
    else:
        raw_value = new_burst_score
        score = log_points(safe_float(new_burst_score), scale=2.0, max_points=80.0)
    return _factor_point("social_heat", "attention_surprise", raw_value=raw_value, score=score, confidence=0.95 if raw_value is not None else 0.0)


def _acceleration_factor(value: float | None) -> dict[str, Any]:
    score = 0.0 if value is None else log_points(max(0.0, value), scale=2.0, max_points=100.0)
    return _factor_point("social_heat", "attention_acceleration", raw_value=value, score=score, confidence=0.9 if value is not None else 0.0)
```

- [ ] **Step 4.6: Implement `social_propagation` factors**

Add:

```python
def _social_propagation_family(*, social_quality: dict[str, Any]) -> dict[str, Any]:
    duplicate_text_share = _optional_float(social_quality.get("duplicate_text_share"))
    top_author_share = _optional_float(social_quality.get("top_author_share"))
    independent_authors = _optional_int(social_quality.get("independent_authors"))
    source_weighted_effective = _optional_float(social_quality.get("source_weighted_effective_authors"))
    facts = {
        "duplicate_text_share": duplicate_text_share,
        "top_author_share": top_author_share,
        "author_entropy": _optional_float(social_quality.get("author_entropy")),
        "informative_post_count": _optional_int(social_quality.get("informative_post_count")),
        "mentions": _count_int(social_quality.get("mentions")),
        "independent_authors": _count_int(independent_authors),
        "effective_authors": _optional_float(social_quality.get("effective_authors")),
        "source_weighted_effective_authors": source_weighted_effective,
        "new_authors": _optional_int(social_quality.get("new_authors")),
        "time_to_second_author_ms": _optional_int(social_quality.get("time_to_second_author_ms")),
        "time_to_third_author_ms": _optional_int(social_quality.get("time_to_third_author_ms")),
        "public_followup_author_count": _optional_int(social_quality.get("public_followup_author_count")),
        "watched_author_count": _optional_int(social_quality.get("watched_author_count")),
        "reproduction_rate": _optional_float(social_quality.get("reproduction_rate")),
    }
    return _family(
        "social_propagation",
        facts=facts,
        factors=[
            _count_factor("social_propagation", "independent_authors", independent_authors, scale=4),
            _ratio_factor("social_propagation", "source_weighted_effective_authors", source_weighted_effective, max_ratio=5.0),
            _propagation_speed_factor(facts["time_to_second_author_ms"], facts["time_to_third_author_ms"]),
            _count_factor("social_propagation", "watched_to_public_followup", facts["public_followup_author_count"], scale=2),
            _penalty_factor("social_propagation", "duplicate_text_share_penalty", raw_value=duplicate_text_share, threshold=DEX_HIGH_ALERT_FLOORS["duplicate_text_share"], risk_flag="duplicate_text_share_high"),
            _penalty_factor("social_propagation", "top_author_concentration_penalty", raw_value=top_author_share, threshold=DEX_HIGH_ALERT_FLOORS["top_author_share"], risk_flag="author_concentration_high"),
        ],
    )
```

Add:

```python
def _propagation_speed_factor(second_ms: int | None, third_ms: int | None) -> dict[str, Any]:
    if second_ms is None:
        return _factor_point("social_propagation", "propagation_speed", raw_value=None, score=0.0, confidence=0.0)
    second_score = max(0.0, 100.0 - min(float(second_ms), 60 * 60_000.0) / (60 * 60_000.0) * 60.0)
    third_score = 0.0 if third_ms is None else max(0.0, 100.0 - min(float(third_ms), 60 * 60_000.0) / (60 * 60_000.0) * 40.0)
    score = second_score * 0.65 + third_score * 0.35
    return _factor_point(
        "social_propagation",
        "propagation_speed",
        raw_value={"time_to_second_author_ms": second_ms, "time_to_third_author_ms": third_ms},
        score=score,
        confidence=0.9,
    )
```

- [ ] **Step 4.7: Implement `semantic_catalyst` and `timing_risk`**

Replace semantic and timing family builders with:

```python
def _semantic_catalyst_family(*, social_semantics: dict[str, Any], social_quality: dict[str, Any]) -> dict[str, Any]:
    direction_counts = _count_map(social_semantics.get("direction_counts"))
    impact_mean = _optional_float(social_semantics.get("impact_mean"))
    novelty_mean = _optional_float(social_semantics.get("novelty_mean"))
    confidence_mean = _optional_float(social_semantics.get("confidence_mean"))
    mentions = max(1, _count_int(social_quality.get("mentions")))
    llm_covered_mentions = sum(direction_counts.values())
    llm_coverage = min(1.0, llm_covered_mentions / mentions)
    facts = {
        "direction_counts": direction_counts,
        "impact_mean": impact_mean,
        "novelty_mean": novelty_mean,
        "confidence_mean": confidence_mean,
        "llm_covered_mentions": llm_covered_mentions,
        "llm_coverage": round(llm_coverage, 6),
    }
    return _family(
        "semantic_catalyst",
        facts=facts,
        factors=[
            _coverage_weighted_ratio_factor("semantic_impact", impact_mean, confidence_mean, llm_coverage),
            _coverage_weighted_ratio_factor("semantic_novelty", novelty_mean, confidence_mean, llm_coverage),
            _ratio_factor("semantic_catalyst", "semantic_coverage", llm_coverage),
            _direction_factor(direction_counts, family="semantic_catalyst"),
        ],
    )


def _timing_risk_family(*, timing: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    social_signal_start_ms = timing.get("social_signal_start_ms") or market.get("social_signal_start_ms")
    before = _optional_float(timing.get("price_change_before_social_pct"))
    since = _optional_float(timing.get("price_change_since_social_pct"))
    facts = {
        "price_change_before_social_pct": before,
        "price_change_since_social_pct": since,
        "social_signal_start_ms": _optional_int(social_signal_start_ms),
        "price_change_status": _optional_str(market.get("price_change_status")),
    }
    return _family(
        "timing_risk",
        facts=facts,
        factors=[
            _timing_risk_factor("pre_social_chase_risk", before, threshold=0.10),
            _timing_risk_factor("post_social_late_risk", since, threshold=0.20),
        ],
    )
```

Add:

```python
def _coverage_weighted_ratio_factor(key: str, value: float | None, confidence: float | None, coverage: float) -> dict[str, Any]:
    score = ratio_points(safe_float(value), max_ratio=1.0, max_points=100.0) * safe_float(confidence) * safe_float(coverage)
    return _factor_point("semantic_catalyst", key, raw_value=value, score=score, confidence=safe_float(confidence) * safe_float(coverage) if value is not None else 0.0)


def _timing_risk_factor(key: str, value: float | None, *, threshold: float) -> dict[str, Any]:
    risk_flags = ["timing_chase_risk"] if value is not None and value >= threshold else []
    penalty = 0.0 if value is None else -min(100.0, max(0.0, value - threshold) / threshold * 50.0)
    return _factor_point("timing_risk", key, raw_value=value, score=penalty, confidence=0.8 if value is not None else 0.0, risk_flags=risk_flags)
```

Update `_direction_factor` signature to accept `family: str`, and call `_factor_point(family, "direction_mix", ...)`.

- [ ] **Step 4.8: Update gates for social hard requirements and timing caps**

In `_gates`, change independent source computation to use propagation fields:

```python
independent_sources = max(
    _count_int(attention.get("unique_authors")),
    _count_int(social_quality.get("independent_authors")),
)
source_weighted_effective = _optional_float(social_quality.get("source_weighted_effective_authors"))
```

Add:

```python
if independent_sources < 2 and watched_mentions <= 0:
    blocked_reasons.append("insufficient_independent_social_sources")
    risk_reasons.append("thin_author_set")
if source_weighted_effective is not None and source_weighted_effective < 1.5 and watched_mentions <= 0:
    blocked_reasons.append("insufficient_credible_social_sources")
    risk_reasons.append("thin_credible_author_set")
```

For timing risk:

```python
before = _optional_float(market.get("price_change_before_social_pct"))
since = _optional_float(market.get("price_change_since_social_pct"))
if before is not None and before >= 0.10:
    risk_reasons.append("timing_chase_risk")
if since is not None and since >= 0.20:
    risk_reasons.append("timing_late_risk")
```

Do not append timing risks to `discard_cap_reasons`; they cap confidence through Pulse/decision, but do not erase a social signal.

- [ ] **Step 4.9: Run snapshot tests**

Run:

```bash
uv run python -m pytest tests/unit/test_factor_snapshot.py -q
```

Expected: all factor snapshot tests pass after fixture updates.

- [ ] **Step 4.10: Commit snapshot rewrite**

Run:

```bash
git add src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py tests/unit/test_factor_snapshot.py
git commit -m "feat: rewrite token radar social factor families"
```

Expected: commit succeeds.

## Task 5: Update Cross-Section Ranking And Projection

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/cross_section_normalizer.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_cohort.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- Modify: `tests/unit/test_token_radar_apply_cross_section.py`
- Modify: `tests/unit/test_token_radar_projection.py`

- [ ] **Step 5.1: Write failing cross-section tests for new family keys and zero timing weight**

In `tests/unit/test_token_radar_apply_cross_section.py`, update `_family` fixture to new family keys. Add:

```python
def test_cross_section_ignores_zero_weight_timing_risk_for_alpha_rank():
    rows = [
        _row(target_id="asset:slow", symbol="SLOW", rank_score=30.0),
        _row(target_id="asset:fast", symbol="FAST", rank_score=70.0),
    ]
    rows[0]["factor_snapshot_json"]["families"]["timing_risk"]["raw_score"] = 100
    rows[0]["factor_snapshot_json"]["families"]["timing_risk"]["score"] = 100
    rows[1]["factor_snapshot_json"]["families"]["timing_risk"]["raw_score"] = 0
    rows[1]["factor_snapshot_json"]["families"]["timing_risk"]["score"] = 0

    result = TokenRadarProjection._apply_cross_section(rows)

    by_id = {r["target_id"]: r["factor_snapshot_json"]["normalization"] for r in result}
    assert by_id["asset:fast"]["alpha_rank"] == 1.0
    assert by_id["asset:slow"]["alpha_rank"] == 0.5
```

- [ ] **Step 5.2: Run failing projection tests**

Run:

```bash
uv run python -m pytest tests/unit/test_token_radar_apply_cross_section.py tests/unit/test_token_radar_projection.py -q
```

Expected: fails because fixtures/projection still expect v2 family names.

- [ ] **Step 5.3: Update projection family references**

In `TokenRadarProjection._apply_cross_section`, keep this pattern but ensure it loops through the new `TOKEN_RADAR_FACTOR_FAMILIES`:

```python
factor_scores[target_id] = {
    family: _family_raw_score(families.get(family)) for family in TOKEN_RADAR_FACTOR_FAMILIES
}
factor_weights[target_id] = {
    family: _family_weight(families.get(family)) for family in TOKEN_RADAR_FACTOR_FAMILIES
}
```

No old family lookup branches are allowed.

- [ ] **Step 5.4: Update cohort metadata semantics**

In `_project_group`, leave current high-confidence and KOL counts, and add public follow-up metadata after `features` exists:

```python
cohort_public_followup_count = int(features.propagation.get("public_followup_author_count") or 0)
```

Add to the returned internal fields:

```python
"_cohort_public_followup_count": cohort_public_followup_count,
```

In `_apply_cross_section`, add to `cohort_metadata[target_id]`:

```python
"public_followup_authors": _count_public_followup(row),
```

Add helper:

```python
def _count_public_followup(row: dict[str, Any]) -> int:
    return int(row.get("_cohort_public_followup_count") or 0)
```

Update `factor_cohort.is_active_cohort_member` only if accepting public follow-up as an entry condition:

```python
if high_confidence_mention_count >= 2 or kol_mention_count > 0 or was_first_seen_global_24h:
    return True
return False
```

Do not add public follow-up to the cohort entry condition in this task; it is metadata only.

- [ ] **Step 5.5: Ensure zero-weight timing is ignored**

`weighted_rank_score` already filters factors with `weights.get(factor) <= 0`. Add a unit assertion in `tests/unit/test_cross_section_normalizer.py`:

```python
def test_weighted_rank_score_ignores_zero_weight_factors() -> None:
    assert weighted_rank_score(
        {"social_heat": 0.5, "social_propagation": 1.0, "timing_risk": 0.0},
        {"social_heat": 0.5, "social_propagation": 0.5, "timing_risk": 0.0},
    ) == 0.75
```

- [ ] **Step 5.6: Run projection tests**

Run:

```bash
uv run python -m pytest tests/unit/test_cross_section_normalizer.py tests/unit/test_token_radar_apply_cross_section.py tests/unit/test_token_radar_projection.py -q
```

Expected: all pass.

- [ ] **Step 5.7: Commit projection update**

Run:

```bash
git add src/gmgn_twitter_intel/domains/token_intel/scoring/cross_section_normalizer.py src/gmgn_twitter_intel/domains/token_intel/scoring/factor_cohort.py src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py tests/unit/test_cross_section_normalizer.py tests/unit/test_token_radar_apply_cross_section.py tests/unit/test_token_radar_projection.py
git commit -m "feat: rank social factor families in cohort"
```

Expected: commit succeeds.

## Task 6: Add Family-Level Evaluation Diagnostics

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_factor_evaluation.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_factor_evaluation_repository.py`
- Modify: `tests/unit/test_token_factor_evaluation.py`

- [ ] **Step 6.1: Write failing evaluation test for family IC diagnostics**

Add to `tests/unit/test_token_factor_evaluation.py`:

```python
def test_settle_token_factor_scores_records_family_rank_ic_diagnostics():
    base_ms = 1_700_000_000_000
    rows = [
        radar_row("a", score=20, computed_at_ms=base_ms, family_scores={"social_heat": 20, "social_propagation": 80, "semantic_catalyst": 50, "timing_risk": 0}),
        radar_row("b", score=60, computed_at_ms=base_ms, family_scores={"social_heat": 60, "social_propagation": 60, "semantic_catalyst": 50, "timing_risk": 0}),
        radar_row("c", score=90, computed_at_ms=base_ms, family_scores={"social_heat": 90, "social_propagation": 20, "semantic_catalyst": 50, "timing_risk": 0}),
    ]
    repos = FakeRepos(
        rows=rows,
        prices={
            ("Asset", "asset:a"): (100.0, 90.0),
            ("Asset", "asset:b"): (100.0, 110.0),
            ("Asset", "asset:c"): (100.0, 140.0),
        },
    )

    settle_token_factor_scores(
        repos=repos,
        horizon="1h",
        window="1h",
        scope="all",
        generated_at_ms=base_ms + 3_600_001,
        limit=100,
    )

    diagnostics = repos.token_factor_evaluations.upserts[0]["diagnostics_json"]
    assert diagnostics["family_rank_ic"]["social_heat"] == pytest.approx(1.0)
    assert diagnostics["family_rank_ic"]["social_propagation"] == pytest.approx(-1.0)
    assert diagnostics["family_rank_ic"]["timing_risk"] is None
    assert diagnostics["family_coverage"]["social_heat"] == 1.0
```

Update the local `radar_row` helper signature to accept `family_scores: dict[str, float] | None = None`, and write those into `factor_snapshot_json.composite.family_scores`.

- [ ] **Step 6.2: Run failing evaluation test**

Run:

```bash
uv run python -m pytest tests/unit/test_token_factor_evaluation.py::test_settle_token_factor_scores_records_family_rank_ic_diagnostics -q
```

Expected: fails because diagnostics do not include `family_rank_ic`.

- [ ] **Step 6.3: Add family score extraction**

In `token_factor_evaluation.py`, add:

```python
def _family_scores(snapshot: dict[str, Any]) -> dict[str, float | None]:
    composite = _mapping(snapshot.get("composite"))
    scores = _mapping(composite.get("family_scores"))
    out: dict[str, float | None] = {}
    for family in ("social_heat", "social_propagation", "semantic_catalyst", "timing_risk"):
        value = scores.get(family)
        try:
            out[family] = None if value is None else max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            out[family] = None
    return out
```

In `_settle_row`, add to settled and unsettled rows:

```python
"family_scores": _family_scores(snapshot),
```

- [ ] **Step 6.4: Add diagnostics functions**

Add:

```python
def _family_rank_ics(settled: list[dict[str, Any]]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for family in ("social_heat", "social_propagation", "semantic_catalyst", "timing_risk"):
        xs: list[float] = []
        ys: list[float] = []
        for item in settled:
            value = _mapping(item.get("family_scores")).get(family)
            if value is None:
                continue
            xs.append(float(value))
            ys.append(float(item["actual_return"]))
        out[family] = _spearman(xs, ys)
    return out


def _family_coverage(settlements: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for family in ("social_heat", "social_propagation", "semantic_catalyst", "timing_risk"):
        covered = sum(1 for item in settlements if _mapping(item.get("family_scores")).get(family) is not None)
        out[family] = covered / len(settlements) if settlements else 0.0
    return out
```

In `global_diagnostics`, add:

```python
"family_rank_ic": _family_rank_ics(settled),
"family_coverage": _family_coverage(settlements),
```

- [ ] **Step 6.5: Run evaluation tests**

Run:

```bash
uv run python -m pytest tests/unit/test_token_factor_evaluation.py -q
```

Expected: all evaluation tests pass.

- [ ] **Step 6.6: Commit evaluation diagnostics**

Run:

```bash
git add src/gmgn_twitter_intel/domains/token_intel/services/token_factor_evaluation.py src/gmgn_twitter_intel/domains/token_intel/repositories/token_factor_evaluation_repository.py tests/unit/test_token_factor_evaluation.py
git commit -m "feat: evaluate social factor family diagnostics"
```

Expected: commit succeeds.

## Task 7: Update Backend Consumers With No Fallbacks

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_recommendation.py`
- Modify: `src/gmgn_twitter_intel/integrations/openai_agents/pulse_recommendation_agent_client.py`
- Modify: `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py`
- Modify: `tests/unit/test_pulse_candidate_gate.py`
- Modify: `tests/unit/test_pulse_candidate_worker.py`
- Modify: `tests/unit/test_signal_pulse_service.py`
- Modify: `tests/unit/test_notification_rules.py`
- Modify: `tests/unit/test_token_radar_repository.py`

- [ ] **Step 7.1: Search for old family literals**

Run:

```bash
rg -n '"attention_heat"|"diffusion_quality"|"semantic_quality"|"timing_response"|token_factor_snapshot_v2_alpha_gated' src tests web
```

Expected: many hits before this task.

- [ ] **Step 7.2: Update Pulse gate tests first**

In `tests/unit/test_pulse_candidate_gate.py` and `tests/unit/test_pulse_candidate_worker.py`, replace snapshot fixtures with:

```python
"schema_version": "token_factor_snapshot_v3_social_attention",
"families": {
    "social_heat": _family(82, 0.45, {"mentions_1h": 7, "weighted_mentions": 3.2}, {}),
    "social_propagation": _family(76, 0.40, {"independent_authors": 4, "duplicate_text_share": 0.0}, {}),
    "semantic_catalyst": _family(60, 0.15, {"impact_mean": 0.7, "llm_coverage": 0.5}, {}),
    "timing_risk": _family(0, 0.0, {"price_change_status": "ready"}, {}),
},
"composite": {
    "raw_alpha_score": 76,
    "rank_score": rank_score,
    "recommended_decision": "high_alert",
    "family_scores": {
        "social_heat": 82,
        "social_propagation": 76,
        "semantic_catalyst": 60,
        "timing_risk": 0,
    },
},
```

- [ ] **Step 7.3: Run failing backend consumer tests**

Run:

```bash
uv run python -m pytest tests/unit/test_pulse_candidate_gate.py tests/unit/test_pulse_candidate_worker.py tests/unit/test_signal_pulse_service.py tests/unit/test_notification_rules.py tests/unit/test_token_radar_repository.py -q
```

Expected: fails where production code still reads old family names.

- [ ] **Step 7.4: Replace Pulse family reads**

In `pulse_candidate_worker.py`, replace:

```python
families.attention_heat.facts.watched_mentions
families.diffusion_quality.facts.independent_authors
families.semantic_quality.facts
families.timing_response.facts
```

with:

```python
families.social_heat.facts.watched_mentions
families.social_propagation.facts.independent_authors
families.semantic_catalyst.facts
families.timing_risk.facts
```

Delete old fallback helper branches if any function tries multiple family names.

- [ ] **Step 7.5: Replace Signal Pulse read-model labels**

In `signal_pulse_service.py`, set:

```python
ALPHA_FAMILIES = ("social_heat", "social_propagation", "semantic_catalyst", "timing_risk")
```

Change `attention_facts` to `heat_facts`, and `diffusion_facts` to `propagation_facts`. Keep outward API names user-facing, but source only from v3 families.

- [ ] **Step 7.6: Replace notification rules**

In `notification_rules.py`, set:

```python
ALPHA_FAMILIES = ("social_heat", "social_propagation", "semantic_catalyst", "timing_risk")
```

Replace score reads:

```python
_family_score(snapshot, "social_heat")
_family_score(snapshot, "semantic_catalyst")
_family_facts(snapshot, "social_heat")
_family_facts(snapshot, "social_propagation")
```

Notification copy may still say "heat" and "propagation"; it must not mention old internal keys.

- [ ] **Step 7.7: Update repository validator tests**

In `tests/unit/test_token_radar_repository.py`, ensure a snapshot containing old `families.attention_heat` raises:

```python
with pytest.raises(ValueError, match=r"factor_snapshot_json\.families\.attention_heat is not allowed"):
    TokenRadarRepository(conn).replace_rows([row])
```

The valid fixture must use v3 family names only.

- [ ] **Step 7.8: Run backend consumer tests**

Run:

```bash
uv run python -m pytest tests/unit/test_pulse_candidate_gate.py tests/unit/test_pulse_candidate_worker.py tests/unit/test_signal_pulse_service.py tests/unit/test_notification_rules.py tests/unit/test_token_radar_repository.py tests/test_pulse_recommendation.py tests/test_pulse_recommendation_agent_client.py -q
```

Expected: all pass.

- [ ] **Step 7.9: Verify old runtime literals are gone from src**

Run:

```bash
rg -n '"attention_heat"|"diffusion_quality"|"semantic_quality"|"timing_response"|token_factor_snapshot_v2_alpha_gated' src/gmgn_twitter_intel
```

Expected: no output from runtime `src/`. Test fixtures may still contain old strings only inside explicit rejection tests.

- [ ] **Step 7.10: Commit backend consumer update**

Run:

```bash
git add src/gmgn_twitter_intel/domains/pulse_lab src/gmgn_twitter_intel/integrations/openai_agents/pulse_recommendation_agent_client.py src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py tests/unit/test_pulse_candidate_gate.py tests/unit/test_pulse_candidate_worker.py tests/unit/test_signal_pulse_service.py tests/unit/test_notification_rules.py tests/unit/test_token_radar_repository.py tests/test_pulse_recommendation.py tests/test_pulse_recommendation_agent_client.py
git commit -m "feat: update backend consumers for social factor contract"
```

Expected: commit succeeds.

## Task 8: Update Frontend Contract And Display

**Files:**

- Modify: `web/src/api/types.ts`
- Modify: `web/src/lib/tokenFactorSnapshot.ts`
- Modify: `web/src/lib/tokenRadar.ts`
- Modify: `web/src/lib/tokenRadar.test.ts`
- Modify: `web/src/components/SignalLabPulse.tsx`
- Modify: `web/src/components/SignalLabPulse.test.tsx`
- Modify: `web/src/components/SignalLabInspector.tsx`
- Modify: `web/src/components/SignalLabInspector.test.tsx`
- Modify: `web/src/App.test.tsx`

- [ ] **Step 8.1: Update TypeScript family type**

In `web/src/api/types.ts`, set:

```ts
export type TokenFactorFamilyKey =
  | "social_heat"
  | "social_propagation"
  | "semantic_catalyst"
  | "timing_risk";
```

Ensure any `Record<TokenFactorFamilyKey, ...>` fixtures use all four new keys.

- [ ] **Step 8.2: Update frontend tests to fail on old fixtures**

In `web/src/lib/tokenRadar.test.ts`, add:

```ts
it("rejects v2 alpha gated family snapshots", () => {
  const snapshot = validFactorSnapshot();
  snapshot.schema_version = "token_factor_snapshot_v2_alpha_gated";
  snapshot.families = {
    attention_heat: snapshot.families.social_heat,
    diffusion_quality: snapshot.families.social_propagation,
    semantic_quality: snapshot.families.semantic_catalyst,
    timing_response: snapshot.families.timing_risk,
  } as never;

  expect(() => requireTokenFactorSnapshot(snapshot)).toThrow(/schema_version/);
});
```

- [ ] **Step 8.3: Run failing frontend tests**

Run:

```bash
cd web && npm run test -- tokenRadar.test.ts SignalLabPulse.test.tsx SignalLabInspector.test.tsx App.test.tsx
```

Expected: fails where fixtures and display code still use old family names.

- [ ] **Step 8.4: Replace family label maps**

Where frontend label maps exist, set labels:

```ts
const FACTOR_FAMILY_LABELS: Record<TokenFactorFamilyKey, string> = {
  social_heat: "Social heat",
  social_propagation: "Propagation",
  semantic_catalyst: "Catalyst",
  timing_risk: "Timing risk",
};
```

If Chinese labels are used:

```ts
const FACTOR_FAMILY_LABELS_ZH: Record<TokenFactorFamilyKey, string> = {
  social_heat: "社交热度",
  social_propagation: "传播质量",
  semantic_catalyst: "语义催化",
  timing_risk: "时机风险",
};
```

- [ ] **Step 8.5: Update frontend fixtures**

Replace fixture family blocks with:

```ts
families: {
  social_heat: factorFamily(82, 0.45, { mentions_1h: 7, weighted_mentions: 3.2 }),
  social_propagation: factorFamily(76, 0.4, { independent_authors: 4, duplicate_text_share: 0.0 }),
  semantic_catalyst: factorFamily(60, 0.15, { impact_mean: 0.7, llm_coverage: 0.5 }),
  timing_risk: factorFamily(0, 0.0, { price_change_status: "ready" }),
},
composite: {
  raw_alpha_score: 76,
  rank_score: 82,
  family_scores: {
    social_heat: 82,
    social_propagation: 76,
    semantic_catalyst: 60,
    timing_risk: 0,
  },
  recommended_decision: "high_alert",
},
```

- [ ] **Step 8.6: Run frontend tests**

Run:

```bash
cd web && npm run test -- tokenRadar.test.ts SignalLabPulse.test.tsx SignalLabInspector.test.tsx App.test.tsx
cd web && npm run typecheck
```

Expected: tests and typecheck pass.

- [ ] **Step 8.7: Commit frontend update**

Run:

```bash
git add web/src/api/types.ts web/src/lib/tokenFactorSnapshot.ts web/src/lib/tokenRadar.ts web/src/lib/tokenRadar.test.ts web/src/components/SignalLabPulse.tsx web/src/components/SignalLabPulse.test.tsx web/src/components/SignalLabInspector.tsx web/src/components/SignalLabInspector.test.tsx web/src/App.test.tsx
git commit -m "feat: update frontend social factor snapshot contract"
```

Expected: commit succeeds.

## Task 9: Diagnostics, Docs, And Generated Score Versions

**Files:**

- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_diagnostics.py`
- Modify: `tests/unit/test_factor_diagnostics.py`
- Modify: `docs/generated/score-versions.md`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CONTRACTS.md`

- [ ] **Step 9.1: Update diagnostics test for saturation and old-family rejection**

In `tests/unit/test_factor_diagnostics.py`, add:

```python
def test_factor_distribution_report_accepts_current_social_families_without_old_family_violation():
    snapshot = _snapshot(
        families={
            "social_heat": _family(70),
            "social_propagation": _family(60),
            "semantic_catalyst": _family(40),
            "timing_risk": _family(0),
        }
    )

    report = factor_distribution_report([{"factor_snapshot_json": snapshot}])

    assert all(item.get("code") != "old_factor_family_keys" for item in report["violations"])
```

- [ ] **Step 9.2: Run failing diagnostics tests**

Run:

```bash
uv run python -m pytest tests/unit/test_factor_diagnostics.py -q
```

Expected: fails if diagnostics still know only old family names or current fixtures use v2.

- [ ] **Step 9.3: Update diagnostics**

In `factor_diagnostics.py`, set allowed/current families from `TOKEN_RADAR_FACTOR_FAMILIES`. Add old family detection only for:

```python
OLD_FACTOR_FAMILIES = frozenset(
    {
        "attention_heat",
        "diffusion_quality",
        "semantic_quality",
        "timing_response",
        "identity",
        "market_quality",
        "social_attention",
        "social_quality",
        "social_semantics",
    }
)
```

Do not include `social_heat`, `social_propagation`, `semantic_catalyst`, or `timing_risk` in `OLD_FACTOR_FAMILIES`.

- [ ] **Step 9.4: Regenerate score version docs**

Run:

```bash
make docs-generated
```

Expected: `docs/generated/score-versions.md` lists `token_factor_snapshot_v3_social_attention` and does not list `token_factor_snapshot_v2_alpha_gated` as runtime current.

- [ ] **Step 9.5: Update architecture docs**

In `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`, update Factor Snapshot Contract section:

```markdown
- `schema_version = "token_factor_snapshot_v3_social_attention"` — the only runtime snapshot version accepted by readers.
- `market` — anchor/live current-market facts carried as first-class context for gates and display; market is not an alpha family.
- `families` — social alpha families only: `social_heat`, `social_propagation`, `semantic_catalyst`, and `timing_risk`.
- `timing_risk.weight = 0.0`; timing risk can cap/caution decisions but does not create positive alpha.
```

In `docs/ARCHITECTURE.md`, update the token_intel domain row to reference `token_factor_snapshot_v3_social_attention`.

In `docs/CONTRACTS.md`, update any factor snapshot example or family list to the v3 names.

- [ ] **Step 9.6: Run docs and diagnostics tests**

Run:

```bash
uv run python -m pytest tests/unit/test_factor_diagnostics.py tests/unit/test_token_radar_audit_cli.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

- [ ] **Step 9.7: Commit docs and diagnostics**

Run:

```bash
git add src/gmgn_twitter_intel/domains/token_intel/scoring/factor_diagnostics.py tests/unit/test_factor_diagnostics.py docs/generated/score-versions.md src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md docs/ARCHITECTURE.md docs/CONTRACTS.md
git commit -m "docs: document social attention factor contract"
```

Expected: commit succeeds.

## Task 10: Whole-Chain Verification And No-Compatibility Audit

**Files:**

- Read: all modified files.
- Modify: `docs/superpowers/plans/active/2026-05-11-social-heat-propagation-hard-cut-verification.md`

- [ ] **Step 10.1: Run old-literal audit**

Run:

```bash
rg -n '"attention_heat"|"diffusion_quality"|"semantic_quality"|"timing_response"|token_factor_snapshot_v2_alpha_gated|token_factor_snapshot_v1|hard_gates|require_token_factor_snapshot_v2|requireTokenFactorSnapshotV2' src/gmgn_twitter_intel web/src docs/generated docs/ARCHITECTURE.md docs/CONTRACTS.md
```

Expected: no output except explicit rejection tests are outside this command scope. If docs intentionally mention historical versions, remove that prose from runtime contract docs.

- [ ] **Step 10.2: Run focused backend verification**

Run:

```bash
uv run python -m pytest tests/unit/test_factor_snapshot.py tests/architecture/test_no_factor_snapshot_fallback.py tests/unit/test_social_signal_features.py tests/unit/test_token_radar_feature_builder.py tests/unit/test_diffusion_health.py tests/unit/test_token_radar_apply_cross_section.py tests/unit/test_token_radar_projection.py tests/unit/test_factor_diagnostics.py tests/unit/test_token_factor_evaluation.py tests/unit/test_pulse_candidate_gate.py tests/unit/test_pulse_candidate_worker.py tests/unit/test_signal_pulse_service.py tests/unit/test_notification_rules.py tests/unit/test_token_radar_repository.py tests/test_pulse_recommendation.py tests/test_pulse_recommendation_agent_client.py -q
```

Expected: all selected tests pass.

- [ ] **Step 10.3: Run focused lint**

Run:

```bash
uv run ruff check src/gmgn_twitter_intel/domains/token_intel src/gmgn_twitter_intel/domains/pulse_lab src/gmgn_twitter_intel/domains/notifications tests/unit/test_factor_snapshot.py tests/architecture/test_no_factor_snapshot_fallback.py tests/unit/test_social_signal_features.py
```

Expected: exits 0.

- [ ] **Step 10.4: Run frontend verification**

Run:

```bash
cd web && npm run lint
cd web && npm run typecheck
cd web && npm run test
```

Expected: all frontend checks pass.

- [ ] **Step 10.5: Run full completion gate**

Run:

```bash
make check-all
```

Expected: exits 0. If a pre-existing unrelated integration failure appears, capture the exact failure and run the focused successful checks above; do not mark the implementation complete until the user accepts the gap.

- [ ] **Step 10.6: Write verification artifact**

Create `docs/superpowers/plans/active/2026-05-11-social-heat-propagation-hard-cut-verification.md` with:

```markdown
# Social Heat Propagation Hard Cut Verification

## Summary

- Snapshot version: `token_factor_snapshot_v3_social_attention`
- Projection version: `token-radar-v13-social-attention`
- Old runtime compatibility audit: record the exact `rg` command from Step 10.1 and its zero-output result.

## Commands

### Focused Backend

```text
Record the exact focused backend command from Step 10.2 and its full stdout/stderr.
```

### Ruff

```text
Record the exact Ruff command from Step 10.3 and its full stdout/stderr.
```

### Frontend

```text
Record the exact frontend commands from Step 10.4 and their full stdout/stderr.
```

### Full Gate

```text
Record the exact `make check-all` command from Step 10.5 and its full stdout/stderr.
```

## Coverage

- Social heat: covered by `tests/unit/test_factor_snapshot.py`, `tests/unit/test_token_radar_feature_builder.py`, and frontend factor snapshot tests.
- Social propagation: covered by `tests/unit/test_factor_snapshot.py`, `tests/unit/test_social_signal_features.py`, `tests/unit/test_diffusion_health.py`, and projection tests.
- Semantic catalyst: covered by `tests/unit/test_factor_snapshot.py`, Pulse recommendation factor-key tests, and Signal Lab frontend tests.
- Timing risk: covered by `tests/unit/test_factor_snapshot.py` and cross-section zero-weight tests.
- Pulse: covered by `tests/unit/test_pulse_candidate_gate.py`, `tests/unit/test_pulse_candidate_worker.py`, `tests/unit/test_signal_pulse_service.py`, `tests/test_pulse_recommendation.py`, and `tests/test_pulse_recommendation_agent_client.py`.
- Notifications: covered by `tests/unit/test_notification_rules.py`.
- Frontend: covered by `web` lint, typecheck, and Vitest.
- Evaluation: covered by `tests/unit/test_token_factor_evaluation.py`.

## Skipped Tests

- Write `- None.` when no tests were skipped by command selection. If any command reports skipped tests, list each skipped test id and the skip reason printed by pytest/Vitest.

## E2E Golden Path

- Projection writes v3 snapshot.
- Cross-section ranks v3 families.
- Pulse consumes v3 snapshot.
- Frontend renders v3 family labels.

## Remaining Risks

- Write `- None.` when no risk remains. If a risk remains, list the exact behavior, affected surface, and accepted follow-up owner.
```

- [ ] **Step 10.7: Commit verification**

Run:

```bash
git add docs/superpowers/plans/active/2026-05-11-social-heat-propagation-hard-cut-verification.md
git commit -m "test: verify social factor hard cut"
```

Expected: commit succeeds.

## Task 11: Final Diff Review

**Files:** all modified files.

- [ ] **Step 11.1: Review diff by concern**

Run:

```bash
git diff main...HEAD --stat
git diff main...HEAD -- src/gmgn_twitter_intel/domains/token_intel/_constants.py
git diff main...HEAD -- src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py
git diff main...HEAD -- src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py
git diff main...HEAD -- src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py
git diff main...HEAD -- web/src/lib/tokenFactorSnapshot.ts
```

Expected: diff shows one coherent hard-cut contract and no compatibility shim.

- [ ] **Step 11.2: Run final old-code scan including tests**

Run:

```bash
rg -n '"attention_heat"|"diffusion_quality"|"semantic_quality"|"timing_response"|token_factor_snapshot_v2_alpha_gated|token_factor_snapshot_v1|hard_gates|require_token_factor_snapshot_v2|requireTokenFactorSnapshotV2' .
```

Expected: only explicit rejection tests and migration/history comments remain. Runtime `src/`, frontend `web/src`, and generated runtime docs must not depend on old names.

- [ ] **Step 11.3: Prepare branch handoff**

Run:

```bash
git status --short --branch
git log --oneline --decorate -8
```

Expected: branch is clean and contains the task commits above.

## Plan Self-Review

- Spec coverage: the plan covers current data usage, social heat, propagation, semantic catalyst, timing risk, hard-cut contract, Pulse/notification/frontend consumers, evaluation diagnostics, and verification.
- No compatibility path: the plan explicitly rejects v1, v2, old families, `hard_gates`, and old `score_json` runtime fallback.
- File specificity: each task lists concrete files and commands.
- TDD: each implementation task begins with a failing test, then code, then verification.
- Scope control: no new providers, no new LLM calls, no new tables, no bot detector, no chain-onchain expansion.
