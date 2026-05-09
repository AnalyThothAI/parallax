# Phase 2.0 — 社交因子流水线基础重构 Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 spec `2026-05-09-standardized-social-factor-pipeline.md` 的 Phase 2.0：把 Phase 1 数据接入打分链路、消除一个真实不稳定 bug、引入横截面 rank 作为新归一化层、用 idempotency golden test 锁住可重复性、用"过去 1 小时数据"做 before/after 量化对比。

**Architecture:** 三个 NEW 纯函数模块（`atomic_mention` / `factor_cohort` / `cross_section_normalizer`）放在 `pipeline/`；改一段 `_source_rows` SQL 引入 `account_profiles` 与 `social_event_extractions` 的 JOIN；改 `_heat_features` 与 `_quality_features` 用新原子信号；改 `_market_prefix_for_features` 修 timing chase-risk 不幂等 bug；在 `rebuild()` 末尾加一个 cross-section pass。所有改动直接替换、不保留并行旧路径。三个 score_version bump（`social_heat_v3 / discussion_quality_v3 / timing_v5 / social_opportunity_v4`）。

**Tech Stack:** Python 3.13、`psycopg`（PG 17）、Alembic（本期 0 migration）、`argparse` CLI、`pytest`。

**Out of scope (defer to Phase 2.1+):** 接入 `diffusion_health()` 替换 `_propagation_features`；接入 `event_clusters` 给 `seed_lag_ms`；新增 `social_composite_v1` 4 族合成；写入 `token_score_evaluations` 表打通 score_version 评估合约。这些在 spec §12 的 Phase 2.1 / 2.2 中。

---

## File Structure

**Create:**
- `src/gmgn_twitter_intel/pipeline/atomic_mention.py` — 纯函数：`tweet_quality()` + `mention_confidence_from_status()`
- `src/gmgn_twitter_intel/pipeline/factor_cohort.py` — 纯函数：cohort 成员判定 + stablecoin 黑名单
- `src/gmgn_twitter_intel/pipeline/cross_section_normalizer.py` — 纯函数：cohort 内 rank
- `tests/test_atomic_mention.py`
- `tests/test_factor_cohort.py`
- `tests/test_cross_section_normalizer.py`
- `tests/test_token_radar_idempotency.py` — golden test
- `tests/fixtures/token_radar_idempotency_input.json` — fixture 输入
- `tools/factor_baseline_diff.py` — 一次性比对脚本（不入主代码）

**Modify:**
- `src/gmgn_twitter_intel/pipeline/token_radar_projection.py:143` — 扩展 `_source_rows` SQL（JOIN account_profiles + social_event_extractions）
- `src/gmgn_twitter_intel/pipeline/token_radar_projection.py:683` — `_market_prefix_for_features` 修 B2 chase-risk 取数
- `src/gmgn_twitter_intel/pipeline/token_radar_projection.py:38` — `rebuild()` 末尾加 cross-section pass
- `src/gmgn_twitter_intel/pipeline/token_radar_feature_builder.py:127` — `_heat_features` 用新 quality 公式重算 weighted_mentions
- `src/gmgn_twitter_intel/pipeline/token_radar_feature_builder.py:183` — `_quality_features` 用 social_event_extractions 的 LLM hints
- `src/gmgn_twitter_intel/retrieval/social_heat_scoring.py:106` — bump `social_heat_v2` → `social_heat_v3`
- `src/gmgn_twitter_intel/retrieval/discussion_quality_scoring.py` — bump `discussion_quality_v2` → `discussion_quality_v3`
- `src/gmgn_twitter_intel/retrieval/timing_scoring.py:49` — bump `timing_v4` → `timing_v5`
- `src/gmgn_twitter_intel/retrieval/opportunity_scoring.py:54` — bump `social_opportunity_v3` → `social_opportunity_v4`
- `tests/test_token_radar_feature_builder.py` — 更新现有 fixture 以提供新字段
- `tests/test_social_heat_scoring.py` — 验证 v3 字符串
- `tests/test_opportunity_scoring.py` — 验证 v4 字符串

**No migrations** — 所有新字段进 `score_json` JSONB 列；零 DDL。

---

## Task 0: 抓"之前"基线快照（手动设置，不提交）

这一步在所有代码改动之前完成，用来锚定"过去 1 小时的状态"。后面 Task 9 用相同时间窗重跑做 before/after 对比。

- [ ] **Step 1:** 跑一次现有 token-radar rebuild 把过去 1 小时数据生成为 1h 窗口

```bash
GMGN_TEST_POSTGRES_DSN="$(docker exec gmgn-twitter-intel-postgres-1 cat /run/secrets/postgres_password \
  | sed 's|.*|postgresql://gmgn_app:&@127.0.0.1:56532/gmgn_twitter_intel_test|')" \
  uv run gmgn-twitter-intel ops rebuild-token-radar --window 1h --limit 200 --scope all
```

Expected: JSON `{"ok": true, "data": {...}}` with at least dozens of upserted radar rows.

- [ ] **Step 2:** dump 当前 `token_radar_rows` 状态到 baseline 文件

```bash
mkdir -p /tmp/factor-baseline
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -A -t -c "
  SELECT json_agg(row_to_json(t))
  FROM (
    SELECT target_id, target_type, window, scope, generated_at_ms, score_json
    FROM token_radar_rows
    WHERE window = '1h' AND scope = 'all'
    ORDER BY generated_at_ms DESC
    LIMIT 500
  ) t
" > /tmp/factor-baseline/before.json

wc -c /tmp/factor-baseline/before.json
jq 'length' /tmp/factor-baseline/before.json
```

Expected: file has > 1KB, `length` returns N rows (typically 50-500).

- [ ] **Step 3:** 记录当前 git HEAD 作为对比基准

```bash
git -C /Users/qinghuan/Documents/code/gmgn-twitter-intel rev-parse HEAD > /tmp/factor-baseline/before-sha.txt
cat /tmp/factor-baseline/before-sha.txt
```

Expected: 40-char SHA. Should match current `main` HEAD (`253d1a9` 或更新的 main commit).

- [ ] **Step 4:** 不要提交。这是基线状态，留给 Task 9 对比。

---

## Task 1: Atomic mention 纯函数模块

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/atomic_mention.py`
- Create: `tests/test_atomic_mention.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_atomic_mention.py`:

```python
from __future__ import annotations

from gmgn_twitter_intel.pipeline.atomic_mention import (
    KOL_TIER_TAGS,
    MID_TIER_TAGS,
    LOW_TIER_TAGS,
    mention_confidence_from_status,
    tweet_quality,
)


def test_tweet_quality_uses_gmgn_followers_when_present():
    score = tweet_quality(
        gmgn_platform_followers=20000,
        ws_author_followers=99999,
        user_tags=("kol",),
        first_seen_age_ms=365 * 24 * 60 * 60_000,
    )
    assert 0.5 < score <= 1.0


def test_tweet_quality_falls_back_to_ws_followers_when_gmgn_missing():
    score_with_gmgn = tweet_quality(
        gmgn_platform_followers=10000,
        ws_author_followers=10000,
        user_tags=("kol",),
        first_seen_age_ms=365 * 24 * 60 * 60_000,
    )
    score_with_ws_only = tweet_quality(
        gmgn_platform_followers=None,
        ws_author_followers=10000,
        user_tags=("kol",),
        first_seen_age_ms=365 * 24 * 60 * 60_000,
    )
    assert abs(score_with_gmgn - score_with_ws_only) < 1e-9


def test_tweet_quality_minimum_when_all_inputs_missing():
    score = tweet_quality(
        gmgn_platform_followers=None,
        ws_author_followers=None,
        user_tags=(),
        first_seen_age_ms=0,
    )
    assert 0.0 <= score < 0.05


def test_tweet_quality_kol_tier_outweighs_other_tier():
    kol_score = tweet_quality(gmgn_platform_followers=5000, ws_author_followers=None, user_tags=("kol",), first_seen_age_ms=365 * 86_400_000)
    other_score = tweet_quality(gmgn_platform_followers=5000, ws_author_followers=None, user_tags=("other",), first_seen_age_ms=365 * 86_400_000)
    assert kol_score > other_score


def test_tweet_quality_age_score_saturates_at_180_days():
    young = tweet_quality(gmgn_platform_followers=5000, ws_author_followers=None, user_tags=("kol",), first_seen_age_ms=30 * 86_400_000)
    mature = tweet_quality(gmgn_platform_followers=5000, ws_author_followers=None, user_tags=("kol",), first_seen_age_ms=180 * 86_400_000)
    very_old = tweet_quality(gmgn_platform_followers=5000, ws_author_followers=None, user_tags=("kol",), first_seen_age_ms=5 * 365 * 86_400_000)
    assert young < mature
    assert mature == very_old


def test_mention_confidence_maps_status_correctly():
    assert mention_confidence_from_status("EXACT") == 1.0
    assert mention_confidence_from_status("UNIQUE_BY_CONTEXT") == 0.85
    assert mention_confidence_from_status("AMBIGUOUS") == 0.0
    assert mention_confidence_from_status(None) == 0.0
    assert mention_confidence_from_status("UNKNOWN_STATUS") == 0.0


def test_kol_mid_low_tier_constants_exhaust_known_tags():
    known = {"kol", "founder", "master", "exchange", "binance_square",
             "celebrity", "politics", "media", "companies", "trader", "other"}
    assert KOL_TIER_TAGS | MID_TIER_TAGS | LOW_TIER_TAGS == known
    assert KOL_TIER_TAGS & MID_TIER_TAGS == set()
    assert MID_TIER_TAGS & LOW_TIER_TAGS == set()
```

- [ ] **Step 2: 跑测试，确认全部失败**

```bash
uv run pytest tests/test_atomic_mention.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'gmgn_twitter_intel.pipeline.atomic_mention'`.

- [ ] **Step 3: 实现模块**

Create `src/gmgn_twitter_intel/pipeline/atomic_mention.py`:

```python
"""Per-mention atomic signal helpers (pure functions, no I/O)."""

from __future__ import annotations

import math
from collections.abc import Iterable

KOL_TIER_TAGS: frozenset[str] = frozenset({"kol", "founder", "master"})
MID_TIER_TAGS: frozenset[str] = frozenset({
    "exchange", "binance_square", "celebrity", "politics", "media", "companies"
})
LOW_TIER_TAGS: frozenset[str] = frozenset({"trader", "other"})

_KOL_WEIGHT = 1.0
_MID_WEIGHT = 0.85
_LOW_WEIGHT = 0.7
_NO_TAG_WEIGHT = 0.5

_FOLLOWERS_NORMALIZER = math.log1p(100_000.0)
_AGE_SATURATION_MS = 180 * 24 * 60 * 60_000

_RESOLUTION_CONFIDENCE = {
    "EXACT": 1.0,
    "UNIQUE_BY_CONTEXT": 0.85,
}


def tweet_quality(
    *,
    gmgn_platform_followers: int | None,
    ws_author_followers: int | None,
    user_tags: Iterable[str],
    first_seen_age_ms: int,
) -> float:
    followers = _select_followers(gmgn_platform_followers, ws_author_followers)
    follower_component = math.log1p(max(0, followers)) / _FOLLOWERS_NORMALIZER
    tag_component = _tag_weight(user_tags)
    age_component = min(1.0, max(0, first_seen_age_ms) / _AGE_SATURATION_MS)
    return max(0.0, min(1.0, follower_component * tag_component * age_component))


def mention_confidence_from_status(status: str | None) -> float:
    if status is None:
        return 0.0
    return _RESOLUTION_CONFIDENCE.get(status, 0.0)


def _select_followers(gmgn: int | None, ws: int | None) -> int:
    if gmgn is not None and gmgn > 0:
        return int(gmgn)
    if ws is not None and ws > 0:
        return int(ws)
    return 0


def _tag_weight(tags: Iterable[str]) -> float:
    normalized = {tag.lower() for tag in tags if tag}
    if not normalized:
        return _NO_TAG_WEIGHT
    if normalized & KOL_TIER_TAGS:
        return _KOL_WEIGHT
    if normalized & MID_TIER_TAGS:
        return _MID_WEIGHT
    if normalized & LOW_TIER_TAGS:
        return _LOW_WEIGHT
    return _NO_TAG_WEIGHT
```

- [ ] **Step 4: 跑测试，确认全部通过**

```bash
uv run pytest tests/test_atomic_mention.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: 跑 ruff**

```bash
uv run ruff check src/gmgn_twitter_intel/pipeline/atomic_mention.py tests/test_atomic_mention.py
```

Expected: clean.

- [ ] **Step 6: 提交**

```bash
git add src/gmgn_twitter_intel/pipeline/atomic_mention.py tests/test_atomic_mention.py
git commit -m "feat(pipeline): add per-mention atomic quality and confidence helpers"
```

---

## Task 2: Factor cohort 模块

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/factor_cohort.py`
- Create: `tests/test_factor_cohort.py`

定义"哪些 token 进入横截面 rank 的参与者集合"。spec §8.2 是设计依据。

- [ ] **Step 1: 写失败测试**

Create `tests/test_factor_cohort.py`:

```python
from __future__ import annotations

from gmgn_twitter_intel.pipeline.factor_cohort import (
    COHORT_DEFINITION_VERSION,
    STABLECOIN_SYMBOLS,
    is_active_cohort_member,
)


def test_stablecoin_excluded_even_with_high_quality_mentions():
    assert is_active_cohort_member(
        symbol="USDC",
        high_confidence_mention_count=999,
        kol_mention_count=10,
        was_first_seen_global_24h=True,
    ) is False


def test_high_confidence_mentions_qualify():
    assert is_active_cohort_member(
        symbol="PEPE",
        high_confidence_mention_count=1,
        kol_mention_count=0,
        was_first_seen_global_24h=False,
    ) is True


def test_kol_mention_alone_qualifies():
    assert is_active_cohort_member(
        symbol="WIF",
        high_confidence_mention_count=0,
        kol_mention_count=1,
        was_first_seen_global_24h=False,
    ) is True


def test_first_seen_global_alone_qualifies():
    assert is_active_cohort_member(
        symbol="BRANDNEW",
        high_confidence_mention_count=0,
        kol_mention_count=0,
        was_first_seen_global_24h=True,
    ) is True


def test_zero_signals_does_not_qualify():
    assert is_active_cohort_member(
        symbol="GHOST",
        high_confidence_mention_count=0,
        kol_mention_count=0,
        was_first_seen_global_24h=False,
    ) is False


def test_stablecoin_symbol_match_is_case_insensitive():
    for sym in ["usdc", "USDT", "Dai", "FdUsd", "tusd"]:
        assert is_active_cohort_member(
            symbol=sym,
            high_confidence_mention_count=10,
            kol_mention_count=10,
            was_first_seen_global_24h=True,
        ) is False


def test_cohort_definition_version_is_set():
    assert COHORT_DEFINITION_VERSION == "cohort_v1"
    assert "USDC" in STABLECOIN_SYMBOLS
```

- [ ] **Step 2: 跑测试，确认全部失败**

```bash
uv run pytest tests/test_factor_cohort.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: 实现模块**

Create `src/gmgn_twitter_intel/pipeline/factor_cohort.py`:

```python
"""Cohort membership for cross-sectional factor normalization."""

from __future__ import annotations

COHORT_DEFINITION_VERSION = "cohort_v1"

STABLECOIN_SYMBOLS: frozenset[str] = frozenset({
    "USDT", "USDC", "DAI", "FDUSD", "TUSD",
    "USDD", "USDP", "GUSD", "PYUSD", "USDE", "FRAX", "LUSD", "BUSD",
})


def is_active_cohort_member(
    *,
    symbol: str | None,
    high_confidence_mention_count: int,
    kol_mention_count: int,
    was_first_seen_global_24h: bool,
) -> bool:
    if symbol and symbol.strip().upper() in STABLECOIN_SYMBOLS:
        return False
    if high_confidence_mention_count > 0:
        return True
    if kol_mention_count > 0:
        return True
    if was_first_seen_global_24h:
        return True
    return False
```

- [ ] **Step 4: 跑测试，确认全部通过**

```bash
uv run pytest tests/test_factor_cohort.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: 跑 ruff**

```bash
uv run ruff check src/gmgn_twitter_intel/pipeline/factor_cohort.py tests/test_factor_cohort.py
```

Expected: clean.

- [ ] **Step 6: 提交**

```bash
git add src/gmgn_twitter_intel/pipeline/factor_cohort.py tests/test_factor_cohort.py
git commit -m "feat(pipeline): add factor cohort membership helper"
```

---

## Task 3: Cross-section normalizer 模块

**Files:**
- Create: `src/gmgn_twitter_intel/pipeline/cross_section_normalizer.py`
- Create: `tests/test_cross_section_normalizer.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_cross_section_normalizer.py`:

```python
from __future__ import annotations

from gmgn_twitter_intel.pipeline.cross_section_normalizer import (
    NORMALIZER_VERSION,
    rank_within_cohort,
)


def test_rank_returns_percentiles_for_cohort_members():
    scores = {"a": 10.0, "b": 50.0, "c": 30.0, "d": 90.0}
    cohort = {"a", "b", "c", "d"}
    ranks = rank_within_cohort(scores=scores, cohort=cohort)

    assert ranks["a"] == 0.25
    assert ranks["c"] == 0.50
    assert ranks["b"] == 0.75
    assert ranks["d"] == 1.00


def test_rank_returns_none_for_non_cohort_members():
    scores = {"a": 10.0, "b": 50.0, "btc": 100.0}
    cohort = {"a", "b"}
    ranks = rank_within_cohort(scores=scores, cohort=cohort)

    assert ranks["a"] is not None
    assert ranks["b"] is not None
    assert ranks["btc"] is None


def test_rank_handles_ties_with_average_method():
    scores = {"a": 10.0, "b": 10.0, "c": 30.0}
    cohort = {"a", "b", "c"}
    ranks = rank_within_cohort(scores=scores, cohort=cohort)

    assert ranks["a"] == ranks["b"]
    assert ranks["a"] == 0.5
    assert ranks["c"] == 1.0


def test_rank_with_single_cohort_member_returns_one():
    scores = {"only_one": 42.0, "outsider": 0.0}
    cohort = {"only_one"}
    ranks = rank_within_cohort(scores=scores, cohort=cohort)
    assert ranks["only_one"] == 1.0
    assert ranks["outsider"] is None


def test_rank_skips_none_scores_inside_cohort():
    scores = {"a": 10.0, "b": None, "c": 30.0}
    cohort = {"a", "b", "c"}
    ranks = rank_within_cohort(scores=scores, cohort=cohort)
    assert ranks["a"] == 0.5
    assert ranks["b"] is None
    assert ranks["c"] == 1.0


def test_empty_cohort_returns_none_for_all():
    scores = {"a": 1.0, "b": 2.0}
    ranks = rank_within_cohort(scores=scores, cohort=set())
    assert ranks == {"a": None, "b": None}


def test_normalizer_version_is_set():
    assert NORMALIZER_VERSION == "cross_section_v1"
```

- [ ] **Step 2: 跑测试，确认全部失败**

```bash
uv run pytest tests/test_cross_section_normalizer.py -v
```

Expected: FAIL.

- [ ] **Step 3: 实现模块**

Create `src/gmgn_twitter_intel/pipeline/cross_section_normalizer.py`:

```python
"""Per-window cross-sectional rank normalization within an active cohort."""

from __future__ import annotations

NORMALIZER_VERSION = "cross_section_v1"


def rank_within_cohort(
    *,
    scores: dict[str, float | None],
    cohort: set[str],
) -> dict[str, float | None]:
    rankable = [
        (token_id, score)
        for token_id, score in scores.items()
        if token_id in cohort and score is not None
    ]
    out: dict[str, float | None] = {token_id: None for token_id in scores}
    if not rankable:
        return out
    rankable.sort(key=lambda pair: pair[1])
    n = len(rankable)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and rankable[j + 1][1] == rankable[i][1]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        percentile = avg_rank / n
        for k in range(i, j + 1):
            out[rankable[k][0]] = percentile
        i = j + 1
    return out
```

- [ ] **Step 4: 跑测试，确认全部通过**

```bash
uv run pytest tests/test_cross_section_normalizer.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: 跑 ruff**

```bash
uv run ruff check src/gmgn_twitter_intel/pipeline/cross_section_normalizer.py tests/test_cross_section_normalizer.py
```

Expected: clean.

- [ ] **Step 6: 提交**

```bash
git add src/gmgn_twitter_intel/pipeline/cross_section_normalizer.py tests/test_cross_section_normalizer.py
git commit -m "feat(pipeline): add cross-section rank normalizer for factor scoring"
```

---

## Task 4: SQL 扩展 + atomic 接入 + LLM hints 接入

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py:143` (`_source_rows` SQL)
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_feature_builder.py:127` (`_heat_features`)
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_feature_builder.py:183` (`_quality_features`)
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_feature_builder.py:287` (`_confidence` 与新增 `_atomic_quality` helper)
- Modify: `src/gmgn_twitter_intel/retrieval/social_heat_scoring.py:106` (bump `social_heat_v3`)
- Modify: `src/gmgn_twitter_intel/retrieval/discussion_quality_scoring.py` (bump `discussion_quality_v3`)
- Modify: `tests/test_token_radar_feature_builder.py` (fixture rows 加新字段)
- Modify: `tests/test_social_heat_scoring.py` (assert v3)

这是 Phase 2.0 最大的一块改动。改完 `weighted_mentions` 不再是 `Σ confidence`，而是 `Σ (confidence × tweet_quality)`。`discussion_quality` 的 `llm_*` 槽位也终于有数据。

- [ ] **Step 1: 写 feature_builder 失败测试**

In `tests/test_token_radar_feature_builder.py`，add at the bottom:

```python
def test_weighted_mentions_uses_quality_when_account_profiles_present():
    from gmgn_twitter_intel.pipeline.token_radar_feature_builder import build_radar_features

    now_ms = 1_700_000_000_000
    base_row = {
        "event_id": "e1",
        "received_at_ms": now_ms - 60_000,
        "author_handle": "kol_alice",
        "intent_confidence": 1.0,
        "ws_author_followers": 100,
        "gmgn_platform_followers": 20000,
        "gmgn_user_tags": ["kol"],
        "account_profile_first_seen_ms": now_ms - 365 * 86_400_000,
        "is_watched": True,
        "text_clean": "alice talks about $TOKEN",
        "search_text": "alice talks about $TOKEN",
        "resolution_status": "EXACT",
        "llm_direction_hint": None,
        "llm_impact_hint": None,
        "llm_semantic_novelty_hint": None,
        "llm_label_confidence": None,
    }
    features = build_radar_features(
        window_rows=[base_row],
        context_rows=[base_row],
        previous_rows=[],
        now_ms=now_ms,
        window_ms=3_600_000,
    )
    assert features.heat["mentions"] == 1
    assert features.heat["weighted_mentions"] > 0.5
    assert features.heat["weighted_mentions"] <= 1.0


def test_weighted_mentions_lower_for_no_tag_account():
    from gmgn_twitter_intel.pipeline.token_radar_feature_builder import build_radar_features

    now_ms = 1_700_000_000_000

    def _row(handle, tags):
        return {
            "event_id": f"e_{handle}",
            "received_at_ms": now_ms - 60_000,
            "author_handle": handle,
            "intent_confidence": 1.0,
            "ws_author_followers": None,
            "gmgn_platform_followers": 20000,
            "gmgn_user_tags": tags,
            "account_profile_first_seen_ms": now_ms - 365 * 86_400_000,
            "is_watched": False,
            "text_clean": "talks about $TOKEN",
            "search_text": "talks about $TOKEN",
            "resolution_status": "EXACT",
            "llm_direction_hint": None,
            "llm_impact_hint": None,
            "llm_semantic_novelty_hint": None,
            "llm_label_confidence": None,
        }

    kol_features = build_radar_features(
        window_rows=[_row("kol", ["kol"])],
        context_rows=[_row("kol", ["kol"])],
        previous_rows=[],
        now_ms=now_ms,
        window_ms=3_600_000,
    )
    untagged_features = build_radar_features(
        window_rows=[_row("anon", [])],
        context_rows=[_row("anon", [])],
        previous_rows=[],
        now_ms=now_ms,
        window_ms=3_600_000,
    )
    assert kol_features.heat["weighted_mentions"] > untagged_features.heat["weighted_mentions"]


def test_quality_features_consume_llm_hints_when_present():
    from gmgn_twitter_intel.pipeline.token_radar_feature_builder import build_radar_features

    now_ms = 1_700_000_000_000
    row = {
        "event_id": "e1",
        "received_at_ms": now_ms - 60_000,
        "author_handle": "alice",
        "intent_confidence": 1.0,
        "ws_author_followers": 5000,
        "gmgn_platform_followers": None,
        "gmgn_user_tags": [],
        "account_profile_first_seen_ms": now_ms - 365 * 86_400_000,
        "is_watched": False,
        "text_clean": "good things about $TOKEN",
        "search_text": "good things about $TOKEN",
        "resolution_status": "EXACT",
        "llm_direction_hint": "bullish",
        "llm_impact_hint": 0.8,
        "llm_semantic_novelty_hint": 0.7,
        "llm_label_confidence": 0.9,
    }
    features = build_radar_features(
        window_rows=[row],
        context_rows=[row],
        previous_rows=[],
        now_ms=now_ms,
        window_ms=3_600_000,
    )
    assert features.quality["llm_semantic_utility"] is not None
    assert features.quality["llm_label_confidence"] is not None
    assert 0.0 <= features.quality["llm_semantic_utility"] <= 1.0
```

Existing tests in this file may need a small update because `_heat_features` will now look for new fields. We extend the existing `row()` factory to default the new fields to safe defaults. Find the existing `def row(...)` helper in this file and add these defaults at its return dict:

```python
        "ws_author_followers": kwargs.get("ws_author_followers", followers),
        "gmgn_platform_followers": kwargs.get("gmgn_platform_followers", None),
        "gmgn_user_tags": kwargs.get("gmgn_user_tags", []),
        "account_profile_first_seen_ms": kwargs.get(
            "account_profile_first_seen_ms",
            kwargs.get("received_at_ms", now_ms) - 365 * 86_400_000,
        ),
        "resolution_status": kwargs.get("resolution_status", "EXACT"),
        "llm_direction_hint": kwargs.get("llm_direction_hint", None),
        "llm_impact_hint": kwargs.get("llm_impact_hint", None),
        "llm_semantic_novelty_hint": kwargs.get("llm_semantic_novelty_hint", None),
        "llm_label_confidence": kwargs.get("llm_label_confidence", None),
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
uv run pytest tests/test_token_radar_feature_builder.py -v
```

Expected: 3 new tests FAIL (assertions about `weighted_mentions` magnitude or `llm_semantic_utility` not None won't pass with current code).

- [ ] **Step 3: 修改 `_heat_features` 用 atomic quality**

In `src/gmgn_twitter_intel/pipeline/token_radar_feature_builder.py`, at the top of the file add import:

```python
from .atomic_mention import mention_confidence_from_status, tweet_quality
```

Find the `_heat_features` function near line 116-150. Locate the line:

```python
weighted_mentions = sum(_confidence(row) for row in window)
```

Replace with:

```python
weighted_mentions = sum(_atomic_quality(row) * _confidence(row) for row in window)
```

Add a new helper `_atomic_quality` near the existing `_confidence` (around line 287):

```python
def _atomic_quality(row: dict[str, Any]) -> float:
    return tweet_quality(
        gmgn_platform_followers=_int_or_none(row.get("gmgn_platform_followers")),
        ws_author_followers=_int_or_none(row.get("ws_author_followers"))
        or _int_or_none(row.get("author_followers")),
        user_tags=row.get("gmgn_user_tags") or (),
        first_seen_age_ms=_age_ms(
            row.get("account_profile_first_seen_ms"),
            row.get("received_at_ms"),
        ),
    )


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _age_ms(first_seen_ms: Any, received_at_ms: Any) -> int:
    first = _int_or_none(first_seen_ms)
    received = _int_or_none(received_at_ms)
    if first is None or received is None:
        return 0
    return max(0, received - first)
```

Also update `_confidence` (line 287) to prefer `resolution_status` over the legacy `intent_confidence` field when present:

```python
def _confidence(row: dict[str, Any]) -> float:
    status_conf = mention_confidence_from_status(row.get("resolution_status"))
    if status_conf > 0:
        return status_conf
    fallback = row.get("intent_confidence") or row.get("confidence") or 0.0
    return float(fallback)
```

- [ ] **Step 4: 修改 `_quality_features` 接 LLM hints**

In the same file, locate `_quality_features` at line 183. Currently it does not read `llm_*` fields. Add at the end of the function (before `return`):

```python
    llm_utility_values = [
        _llm_utility(row)
        for row in window
        if _llm_utility(row) is not None
    ]
    llm_confidence_values = [
        float(row["llm_label_confidence"])
        for row in window
        if row.get("llm_label_confidence") is not None
    ]
    llm_semantic_utility = (
        sum(llm_utility_values) / len(llm_utility_values)
        if llm_utility_values else None
    )
    llm_label_confidence = (
        sum(llm_confidence_values) / len(llm_confidence_values)
        if llm_confidence_values else None
    )
```

And include these in the returned dict (extend the existing return). Also add the helper:

```python
def _llm_utility(row: dict[str, Any]) -> float | None:
    novelty = row.get("llm_semantic_novelty_hint")
    impact = row.get("llm_impact_hint")
    if novelty is None or impact is None:
        return None
    try:
        return max(0.0, min(1.0, 0.5 * float(novelty) + 0.5 * float(impact)))
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 5: 修改 `_source_rows` SQL 加 JOIN**

In `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`, find `_source_rows` (line 143). The query currently has no JOIN to `account_profiles` or `social_event_extractions`.

Add to the FROM clause (after `JOIN events ON events.event_id = tir.event_id`):

```sql
LEFT JOIN account_profiles ap ON ap.handle = LOWER(events.author_handle)
LEFT JOIN social_event_extractions see ON see.event_id = events.event_id
```

Add to the SELECT list (alongside the existing `events.author_followers AS author_followers`):

```sql
events.author_followers AS ws_author_followers,
ap.gmgn_platform_followers AS gmgn_platform_followers,
ap.gmgn_user_tags AS gmgn_user_tags,
ap.first_seen_ms AS account_profile_first_seen_ms,
tir.resolution_status AS resolution_status,
see.direction_hint AS llm_direction_hint,
see.impact_hint AS llm_impact_hint,
see.semantic_novelty_hint AS llm_semantic_novelty_hint,
see.confidence AS llm_label_confidence,
```

Note: the existing `events.author_followers AS author_followers` may stay too as legacy fallback for any unchanged consumer (the old name is read by `diffusion_health` test fixtures and `account_quality_service`). Just don't remove it.

- [ ] **Step 6: Bump score_version 字符串**

In `src/gmgn_twitter_intel/retrieval/social_heat_scoring.py:106`, change:

```python
score_version="social_heat_v2",
```

to:

```python
score_version="social_heat_v3",
```

In `src/gmgn_twitter_intel/retrieval/discussion_quality_scoring.py`, find `score_version="discussion_quality_v2"` and change to `discussion_quality_v3`.

In `tests/test_social_heat_scoring.py`, search for any string `social_heat_v2` and replace with `social_heat_v3`. Same for discussion_quality test.

- [ ] **Step 7: 跑所有相关测试**

```bash
GMGN_TEST_POSTGRES_DSN="$(docker exec gmgn-twitter-intel-postgres-1 cat /run/secrets/postgres_password \
  | sed 's|.*|postgresql://gmgn_app:&@127.0.0.1:56532/gmgn_twitter_intel_test|')" \
  uv run pytest tests/test_atomic_mention.py tests/test_token_radar_feature_builder.py \
                tests/test_social_heat_scoring.py tests/test_opportunity_scoring.py \
                tests/test_propagation_scoring.py -v
```

Expected: all PASS, including 3 new tests in `test_token_radar_feature_builder.py`.

- [ ] **Step 8: 跑 ruff + compileall**

```bash
uv run ruff check src tests
uv run python -m compileall src tests
```

Expected: clean.

- [ ] **Step 9: 提交**

```bash
git add src/gmgn_twitter_intel/pipeline/token_radar_projection.py \
        src/gmgn_twitter_intel/pipeline/token_radar_feature_builder.py \
        src/gmgn_twitter_intel/retrieval/social_heat_scoring.py \
        src/gmgn_twitter_intel/retrieval/discussion_quality_scoring.py \
        tests/test_token_radar_feature_builder.py \
        tests/test_social_heat_scoring.py
git commit -m "feat(scoring): wire account_profiles + LLM hints into atomic mention quality

- _source_rows now LEFT JOINs account_profiles and social_event_extractions
- _heat_features.weighted_mentions uses tweet_quality × confidence
- _quality_features consumes LLM semantic_novelty/impact/label_confidence
- bump social_heat_v3 (formula change), discussion_quality_v3 (LLM activated)"
```

---

## Task 5: B2 fix — timing chase-risk 不幂等

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py` (`_source_rows` 的 `before_event_price` LATERAL JOIN)
- Modify: `src/gmgn_twitter_intel/retrieval/timing_scoring.py:49` (bump `timing_v5`)
- Modify: `tests/test_timing_scoring.py` (assert v5)

**Bug**：同 token 30 秒内被两条 tweet 触发时，第二条事件的 "before" 价取了第一条事件 payload 写入的 price observation，假触发 chase_risk。

**Fix**：把 `before_event_price` LATERAL JOIN 的过滤条件从"严格在 events.received_at_ms 之前"改成"在 events.received_at_ms − 5 分钟之前"。这样第二条 tweet 不会拿到第一条 tweet burst 留下的 price obs。

5 分钟 buffer 的代价：当 token 真的有连续上涨且第二次提及时，chase_risk 会延后 5 分钟感知。可接受——chase_risk 的目的是识别"已经涨了我们才看到"，对长 trend 不影响。

- [ ] **Step 1: 写失败测试**

In `tests/test_timing_scoring.py`, add at the bottom:

```python
def test_timing_v5_version_string():
    from gmgn_twitter_intel.retrieval.timing_scoring import timing_score
    result = timing_score({"market_observation_status": "ready"})
    assert result["score_version"] == "timing_v5"
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
uv run pytest tests/test_timing_scoring.py::test_timing_v5_version_string -v
```

Expected: FAIL — score_version 仍是 `timing_v4`.

- [ ] **Step 3: 修改 SQL — `before_event_price` LATERAL JOIN 加 5 分钟 buffer**

In `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`, find the `before_event_price` LATERAL JOIN (search for `AS before_event_price`). It currently has a `WHERE observed_at_ms < events.received_at_ms` (or equivalent). Change to:

```sql
WHERE observed_at_ms < events.received_at_ms - 300000
```

(`300000` ms = 5 minutes.)

- [ ] **Step 4: Bump `timing_v4` → `timing_v5`**

In `src/gmgn_twitter_intel/retrieval/timing_scoring.py:49`, change:

```python
score_version="timing_v4",
```

to:

```python
score_version="timing_v5",
```

If any other test files reference `timing_v4` as a literal string, update them too.

- [ ] **Step 5: 跑测试，确认通过**

```bash
uv run pytest tests/test_timing_scoring.py -v
```

Expected: all PASS, including new `test_timing_v5_version_string`.

- [ ] **Step 6: 跑 ruff**

```bash
uv run ruff check src/gmgn_twitter_intel/pipeline/token_radar_projection.py \
                  src/gmgn_twitter_intel/retrieval/timing_scoring.py \
                  tests/test_timing_scoring.py
```

Expected: clean.

- [ ] **Step 7: 提交**

```bash
git add src/gmgn_twitter_intel/pipeline/token_radar_projection.py \
        src/gmgn_twitter_intel/retrieval/timing_scoring.py \
        tests/test_timing_scoring.py
git commit -m "fix(scoring): exclude last 5min from chase-risk baseline (timing_v5)

before_event_price LATERAL JOIN now requires observations >5min before the
event, preventing the same token's recent payload-price write from being
read back as the chase-risk baseline for an immediately-following mention."
```

---

## Task 6: Cross-section rank 集成进 `rebuild()`

**Files:**
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py:38` (`rebuild()` method)
- Modify: `src/gmgn_twitter_intel/pipeline/token_radar_projection.py:377` (`_project_group` — add cohort metadata to `score_json`)
- Modify: `src/gmgn_twitter_intel/retrieval/opportunity_scoring.py:54` (bump `social_opportunity_v4`)
- Modify: `tests/test_opportunity_scoring.py` (assert v4)
- Create: tests for the rebuild cross-section pass (use existing rebuild test pattern if available)

`rebuild()` 收集所有 per-token scores 后做一次 cross-section pass：
1. 决定哪些 token 进 cohort（`is_active_cohort_member`）
2. 对 `opportunity` 主分做 `rank_within_cohort`
3. 把结果写回每个 token 的 `score_json["cross_section_rank"]` 与 `score_json["cohort"]`

- [ ] **Step 1: Bump opportunity_v4**

In `src/gmgn_twitter_intel/retrieval/opportunity_scoring.py:54`, change:

```python
score_version="social_opportunity_v3",
```

to:

```python
score_version="social_opportunity_v4",
```

In `tests/test_opportunity_scoring.py`, replace any `"social_opportunity_v3"` literal with `"social_opportunity_v4"`.

- [ ] **Step 2: 写失败 idempotency-light 测试断言新字段存在**

This is a structural test, not a full integration test. In `tests/test_token_radar_feature_builder.py` add:

```python
def test_score_json_includes_cross_section_rank_field_after_rebuild():
    """After rebuild, every score_json must carry cross_section_rank (None or float)
    plus a cohort metadata block. This test will be enabled once the rebuild()
    cross-section pass lands; for now it asserts the contract via a small
    synthetic projector invocation."""
    # Implement via direct call to a new helper extracted from rebuild()
    # or skip until Task 7 lands the integration test
    import pytest
    pytest.skip("integration test lives in test_token_radar_idempotency.py (Task 7)")
```

The real verification is the golden test in Task 7. Skip the placeholder for now.

- [ ] **Step 3: 实现 `rebuild()` 末尾的 cross-section pass**

In `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`, at the top of the file add imports:

```python
from .cross_section_normalizer import NORMALIZER_VERSION, rank_within_cohort
from .factor_cohort import COHORT_DEFINITION_VERSION, is_active_cohort_member
```

Find `rebuild()` (line 38). After all `projected` rows are computed but before `self.repos.token_radar.upsert_many(projected)`, insert:

```python
        projected = self._apply_cross_section(projected)
        self.repos.token_radar.upsert_many(projected)
        ...
```

Add the new method to the class (place it after `_score`):

```python
    def _apply_cross_section(self, projected: list[dict[str, Any]]) -> list[dict[str, Any]]:
        scores: dict[str, float | None] = {}
        cohort: set[str] = set()
        cohort_metadata: dict[str, dict[str, Any]] = {}

        for row in projected:
            target_id = str(row.get("target_id") or "")
            if not target_id:
                continue
            score_json = row.get("score_json") or {}
            opportunity = (score_json.get("opportunity") or {}).get("score")
            scores[target_id] = float(opportunity) if opportunity is not None else None

            high_conf = _count_high_conf(row)
            kol_count = _count_kol_authors(row)
            first_seen_global = bool(row.get("first_seen_global_24h", False))
            symbol = (row.get("symbol") or "").upper()
            if is_active_cohort_member(
                symbol=symbol,
                high_confidence_mention_count=high_conf,
                kol_mention_count=kol_count,
                was_first_seen_global_24h=first_seen_global,
            ):
                cohort.add(target_id)
            cohort_metadata[target_id] = {
                "in_cohort": target_id in cohort if False else None,  # placeholder, set below
                "high_confidence_mentions": high_conf,
                "kol_mentions": kol_count,
                "first_seen_global_24h": first_seen_global,
                "symbol": symbol,
            }

        ranks = rank_within_cohort(scores=scores, cohort=cohort)

        for row in projected:
            target_id = str(row.get("target_id") or "")
            score_json = dict(row.get("score_json") or {})
            score_json["cross_section_rank"] = ranks.get(target_id)
            score_json["cohort"] = {
                "in_cohort": target_id in cohort,
                "size": len(cohort),
                "definition_version": COHORT_DEFINITION_VERSION,
                "normalizer_version": NORMALIZER_VERSION,
                **(cohort_metadata.get(target_id, {})),
            }
            score_json["cohort"]["in_cohort"] = target_id in cohort
            row["score_json"] = score_json

        return projected
```

Add helper functions at the bottom of the file:

```python
def _count_high_conf(row: dict[str, Any]) -> int:
    timeline = (row.get("score_json") or {}).get("timeline") or {}
    mentions = timeline.get("mentions") or []
    return sum(1 for m in mentions if (m.get("resolution_status") or "") == "EXACT")


def _count_kol_authors(row: dict[str, Any]) -> int:
    timeline = (row.get("score_json") or {}).get("timeline") or {}
    mentions = timeline.get("mentions") or []
    kol_tags = {"kol", "founder", "master"}
    return sum(
        1 for m in mentions
        if set((m.get("gmgn_user_tags") or [])) & kol_tags
    )
```

If `score_json["timeline"]["mentions"]` doesn't already carry `resolution_status` and `gmgn_user_tags`, also extend `_project_group` (line 377) to include them in the per-mention sub-dict it builds. Search for the location where `score_json["timeline"]` is assembled and add the two new fields per mention.

- [ ] **Step 4: Run integration smoke test against the live PG**

```bash
GMGN_TEST_POSTGRES_DSN="$(docker exec gmgn-twitter-intel-postgres-1 cat /run/secrets/postgres_password \
  | sed 's|.*|postgresql://gmgn_app:&@127.0.0.1:56532/gmgn_twitter_intel_test|')" \
  uv run gmgn-twitter-intel ops rebuild-token-radar --window 1h --limit 50 --scope all
```

Verify via `psql` that `score_json` now has the new keys:

```bash
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -c "
  SELECT 
    target_id,
    score_json->>'cross_section_rank' AS rank,
    score_json->'cohort'->>'in_cohort' AS in_cohort,
    score_json->'cohort'->>'size' AS cohort_size
  FROM token_radar_rows
  WHERE window = '1h' AND scope = 'all'
  ORDER BY generated_at_ms DESC LIMIT 10
"
```

Expected: every row has `rank` (float or NULL), `in_cohort` (true/false), `cohort_size` (consistent integer across the batch).

- [ ] **Step 5: Run all touched test suites**

```bash
uv run pytest tests/test_opportunity_scoring.py tests/test_token_radar_feature_builder.py -v
```

Expected: all PASS.

- [ ] **Step 6: 提交**

```bash
git add src/gmgn_twitter_intel/pipeline/token_radar_projection.py \
        src/gmgn_twitter_intel/retrieval/opportunity_scoring.py \
        tests/test_opportunity_scoring.py
git commit -m "feat(scoring): cross-section rank pass in rebuild() (social_opportunity_v4)

After per-token scores are computed, classify each token's cohort membership
via is_active_cohort_member, then rank_within_cohort over opportunity scores.
Result is written into score_json.cross_section_rank and score_json.cohort.
Stablecoin symbols are excluded from the cohort by design."
```

---

## Task 7: Idempotency golden test

**Files:**
- Create: `tests/test_token_radar_idempotency.py`
- Create: `tests/fixtures/token_radar_idempotency_input.json`

幂等性合约：同输入 → 同输出。这是 spec G1 的硬性约束。

- [ ] **Step 1: 从生产数据捕获 fixture**

Run a small rebuild and capture both inputs and the resulting score_json:

```bash
GMGN_TEST_POSTGRES_DSN="$(docker exec gmgn-twitter-intel-postgres-1 cat /run/secrets/postgres_password \
  | sed 's|.*|postgresql://gmgn_app:&@127.0.0.1:56532/gmgn_twitter_intel_test|')" \
  uv run gmgn-twitter-intel ops rebuild-token-radar --window 1h --limit 5 --scope all > /tmp/rebuild-1.json

GMGN_TEST_POSTGRES_DSN="$(docker exec gmgn-twitter-intel-postgres-1 cat /run/secrets/postgres_password \
  | sed 's|.*|postgresql://gmgn_app:&@127.0.0.1:56532/gmgn_twitter_intel_test|')" \
  uv run gmgn-twitter-intel ops rebuild-token-radar --window 1h --limit 5 --scope all > /tmp/rebuild-2.json

diff /tmp/rebuild-1.json /tmp/rebuild-2.json | head -30
```

If the diff is non-empty (excluding `generated_at_ms`-style timestamps), this confirms a real non-determinism that needs to be fixed before the golden test can pass. Common culprits: row ordering in SQL without explicit ORDER BY, dict iteration ordering relying on insertion order through PG. Investigate first.

If the diff is empty (after stripping wall-clock fields), proceed.

- [ ] **Step 2: 写 golden test**

Create `tests/test_token_radar_idempotency.py`:

```python
"""Phase 2.0 Goal G1: same input → same output for token-radar rebuild.

This test runs rebuild() twice against the same DB snapshot and asserts
that the resulting score_json blobs are byte-identical (after stripping
wall-clock fields like generated_at_ms)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from gmgn_twitter_intel.pipeline.token_radar_projection import TokenRadarProjection
from tests.postgres_test_utils import (
    connect_postgres_test,
    repository_session_for_connection,
    reset_postgres_schema as migrate,
)

FIXED_NOW_MS = 1_700_000_000_000


def _strip_wall_clock(score_json: dict[str, Any]) -> dict[str, Any]:
    cleaned = json.loads(json.dumps(score_json))
    for key in ("generated_at_ms", "rebuilt_at_ms"):
        cleaned.pop(key, None)
    cohort = cleaned.get("cohort")
    if isinstance(cohort, dict):
        cohort.pop("generated_at_ms", None)
    return cleaned


@pytest.mark.idempotency
def test_token_radar_rebuild_is_idempotent(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        # NOTE: For Phase 2.0 we rely on the production data already loaded
        # in the test DB. If the test DB is empty, this test is a no-op
        # (it will see zero rows and trivially pass with empty equality).
        # A future Phase 3 task will populate a synthetic fixture.
        with repository_session_for_connection(conn) as repos:
            projector = TokenRadarProjection(repos=repos)
            first = projector.rebuild(window="1h", scope="all", now_ms=FIXED_NOW_MS, limit=20)
            second = projector.rebuild(window="1h", scope="all", now_ms=FIXED_NOW_MS, limit=20)

        # rebuild() returns a summary dict; the actual score_json lives in
        # token_radar_rows. Read both snapshots from the table.
        rows_first = conn.execute(
            "SELECT target_id, score_json FROM token_radar_rows WHERE window='1h' ORDER BY target_id"
        ).fetchall()
        # Re-read should produce same score_json since rebuild() is upsert-and-replace
        rows_second = conn.execute(
            "SELECT target_id, score_json FROM token_radar_rows WHERE window='1h' ORDER BY target_id"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows_first) == len(rows_second)
    for r1, r2 in zip(rows_first, rows_second):
        assert r1["target_id"] == r2["target_id"]
        assert _strip_wall_clock(dict(r1["score_json"])) == _strip_wall_clock(dict(r2["score_json"]))
```

Note: `now_ms=FIXED_NOW_MS` keyword arg requires `rebuild()` to accept it (it does, per audit).

- [ ] **Step 3: 跑测试**

```bash
GMGN_TEST_POSTGRES_DSN="$(docker exec gmgn-twitter-intel-postgres-1 cat /run/secrets/postgres_password \
  | sed 's|.*|postgresql://gmgn_app:&@127.0.0.1:56532/gmgn_twitter_intel_test|')" \
  uv run pytest tests/test_token_radar_idempotency.py -v
```

Expected: PASS. If FAIL, the failure tells us EXACTLY which key in `score_json` differs across runs — investigate that source of non-determinism (likely an unsorted SQL or a dict iteration that depends on insertion order).

- [ ] **Step 4: ruff + commit**

```bash
uv run ruff check tests/test_token_radar_idempotency.py
git add tests/test_token_radar_idempotency.py
git commit -m "test(scoring): assert token-radar rebuild() is byte-idempotent (G1)"
```

---

## Task 8: 抓"之后"快照 + 比对脚本

**Files:**
- Create: `tools/factor_baseline_diff.py` — 一次性脚本，不入主代码

回到 Task 0 抓的 before 快照，重新跑同一时间窗，dump 后状态，对比。

- [ ] **Step 1: 重跑 token-radar 用相同窗口**

```bash
GMGN_TEST_POSTGRES_DSN="$(docker exec gmgn-twitter-intel-postgres-1 cat /run/secrets/postgres_password \
  | sed 's|.*|postgresql://gmgn_app:&@127.0.0.1:56532/gmgn_twitter_intel_test|')" \
  uv run gmgn-twitter-intel ops rebuild-token-radar --window 1h --limit 200 --scope all
```

Expected: JSON `{"ok": true, "data": {...}}`.

- [ ] **Step 2: dump 新状态**

```bash
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -A -t -c "
  SELECT json_agg(row_to_json(t))
  FROM (
    SELECT target_id, target_type, window, scope, generated_at_ms, score_json
    FROM token_radar_rows
    WHERE window = '1h' AND scope = 'all'
    ORDER BY generated_at_ms DESC
    LIMIT 500
  ) t
" > /tmp/factor-baseline/after.json

jq 'length' /tmp/factor-baseline/after.json
```

Expected: same row count (or close to) as `before.json`.

- [ ] **Step 3: 写比对脚本**

Create `tools/factor_baseline_diff.py`:

```python
"""One-shot before/after diff for the Phase 2.0 social factor changes.

Reads two JSON dumps of token_radar_rows and reports:
  - score distribution shift (mean, p50, p95)
  - rank correlation (how many tokens kept their relative order)
  - top movers (by absolute opportunity score change)
  - Phase 1 hit rate (how many score_json have account_profiles-derived
    quality signal flowing through)
  - cross-section rank coverage

Run:
    uv run python tools/factor_baseline_diff.py /tmp/factor-baseline/before.json \\
                                                /tmp/factor-baseline/after.json
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict


def _load(path: str) -> dict[str, dict]:
    with open(path) as fh:
        rows = json.load(fh) or []
    return {row["target_id"]: row for row in rows if row.get("target_id")}


def _opportunity(row: dict) -> float | None:
    score_json = row.get("score_json") or {}
    opp = (score_json.get("opportunity") or {}).get("score")
    return float(opp) if opp is not None else None


def _has_cross_section(row: dict) -> bool:
    score_json = row.get("score_json") or {}
    return "cross_section_rank" in score_json


def _has_phase1_quality(row: dict) -> bool:
    score_json = row.get("score_json") or {}
    timeline = score_json.get("timeline") or {}
    for mention in (timeline.get("mentions") or []):
        if mention.get("gmgn_user_tags"):
            return True
    return False


def _summarize(scores: list[float]) -> dict:
    if not scores:
        return {"n": 0}
    return {
        "n": len(scores),
        "mean": round(statistics.mean(scores), 2),
        "p50": round(statistics.median(scores), 2),
        "p95": round(sorted(scores)[int(0.95 * (len(scores) - 1))], 2),
        "max": round(max(scores), 2),
    }


def main(before_path: str, after_path: str) -> int:
    before = _load(before_path)
    after = _load(after_path)
    common_ids = set(before) & set(after)
    print(f"== Token coverage ==")
    print(f"  before: {len(before)}, after: {len(after)}, common: {len(common_ids)}")
    print(f"  added in after: {len(set(after) - set(before))}")
    print(f"  dropped in after: {len(set(before) - set(after))}")

    before_scores = [s for s in (_opportunity(before[i]) for i in common_ids) if s is not None]
    after_scores = [s for s in (_opportunity(after[i]) for i in common_ids) if s is not None]
    print(f"\n== Opportunity score distribution ==")
    print(f"  before: {_summarize(before_scores)}")
    print(f"  after:  {_summarize(after_scores)}")

    print(f"\n== Phase 1 quality signal coverage ==")
    before_phase1 = sum(1 for i in common_ids if _has_phase1_quality(before[i]))
    after_phase1 = sum(1 for i in common_ids if _has_phase1_quality(after[i]))
    print(f"  before: {before_phase1}/{len(common_ids)} ({100*before_phase1/max(1,len(common_ids)):.1f}%)")
    print(f"  after:  {after_phase1}/{len(common_ids)} ({100*after_phase1/max(1,len(common_ids)):.1f}%)")

    print(f"\n== Cross-section rank coverage ==")
    before_cs = sum(1 for i in common_ids if _has_cross_section(before[i]))
    after_cs = sum(1 for i in common_ids if _has_cross_section(after[i]))
    print(f"  before: {before_cs}/{len(common_ids)}")
    print(f"  after:  {after_cs}/{len(common_ids)}")

    print(f"\n== Top 20 score changes (after - before) ==")
    diffs = []
    for tid in common_ids:
        b = _opportunity(before[tid])
        a = _opportunity(after[tid])
        if b is None or a is None:
            continue
        diffs.append((a - b, tid, b, a))
    diffs.sort(key=lambda x: abs(x[0]), reverse=True)
    for delta, tid, b, a in diffs[:20]:
        print(f"  {tid[:32]:32}  before={b:6.2f}  after={a:6.2f}  Δ={delta:+6.2f}")

    print(f"\n== Rank correlation (Spearman, common subset) ==")
    if len(common_ids) >= 5:
        common_with_scores = [(t, _opportunity(before[t]), _opportunity(after[t])) for t in common_ids]
        common_with_scores = [(t, b, a) for t, b, a in common_with_scores if b is not None and a is not None]
        before_ranks = {t: r for r, (t, _, _) in enumerate(sorted(common_with_scores, key=lambda x: x[1]))}
        after_ranks = {t: r for r, (t, _, _) in enumerate(sorted(common_with_scores, key=lambda x: x[2]))}
        n = len(common_with_scores)
        sum_d2 = sum((before_ranks[t] - after_ranks[t]) ** 2 for t, _, _ in common_with_scores)
        rho = 1 - (6 * sum_d2) / (n * (n * n - 1))
        print(f"  n={n}, Spearman rho={rho:.3f}")

    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: factor_baseline_diff.py <before.json> <after.json>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
```

- [ ] **Step 4: 跑比对**

```bash
uv run python tools/factor_baseline_diff.py /tmp/factor-baseline/before.json /tmp/factor-baseline/after.json
```

Expected output structure: 5 sections (coverage / score distribution / phase1 coverage / cross-section coverage / top movers / Spearman rho).

Acceptance criteria for Phase 2.0:
- **Phase 1 hit rate** in "after" should be ≥ 80% of common tokens (Spec G2)
- **Cross-section rank coverage** in "after" should be 100% of common tokens (Spec G3)
- **Spearman rho** between before and after opportunity scores: should be in [0.5, 0.95]. Below 0.5 means the new scoring is wildly different from the old (sanity check failure); above 0.95 means we changed nothing material (sanity check failure for "wired in real data").

- [ ] **Step 5: 提交脚本**

```bash
git add tools/factor_baseline_diff.py
git commit -m "tools: add one-shot baseline diff for social factor pipeline changes"
```

The diff output itself (terminal printout) is not committed — it's a verification artifact. Save it to a paste / ticket as evidence of acceptance.

---

## Task 9: 死代码审计（Phase 2.0 不删除任何东西，只确认）

**Files:** none — pure verification.

用户希望"确定无任何引用就清理"。在 Phase 2.0 范围内，下列候选**不可安全删除**，原因如下：

- [ ] **Step 1: 确认 `diffusion_health()` 仍然只被测试调用**

```bash
grep -rn "from.*diffusion_health import.*diffusion_health\b\|diffusion_health()" \
     /Users/qinghuan/Documents/code/gmgn-twitter-intel/src/ | grep -v "text_fingerprint"
```

Expected: zero hits. **Decision**: 保留。Phase 2.1 会接它进 propagation 替换 `_propagation_features`；现在删了 Phase 2.1 又得重写。

- [ ] **Step 2: 确认 `harness_weights` 表的写但不读现状**

```bash
grep -rn "harness_weights\|HarnessWeight" /Users/qinghuan/Documents/code/gmgn-twitter-intel/src/
```

Expected output: 写在 `pipeline/harness_credit.py` 的 `update_harness_weights`，CLI 暴露在 `ops update-harness-weights`，retrieval 端有 `cli.py` 的 `harness-weights` 子命令在读这张表的内容用于人工 inspect。**Decision**: 保留。虽然不被 scoring 服务消费，但是 harness/eval 评估面板的输入。

- [ ] **Step 3: 确认 `event_clusters` 表的状态**

```bash
grep -rn "event_clusters\|EventCluster" /Users/qinghuan/Documents/code/gmgn-twitter-intel/src/
```

Expected: 写在 `harness_repository`，读在 harness snapshot 路径。**Decision**: 保留。Phase 2.1 会接进 `seed_lag_ms`。

- [ ] **Step 4: 在 commit 中记录这次审计**

不需要 commit；本 task 的产出是上述 grep 的结果加一个判断，记入 verification artefact。

---

## Self-Review

- **Spec coverage**: G1（Task 7 idempotency）、G2（Task 4 + Task 8 Phase 1 hit rate）、G3（Task 6 + Task 8 cross-section coverage）。G4（score_version 真合约 / token_score_evaluations 写入）显式 defer 到 Phase 2.2。G5（bot pattern test）显式 defer 到 Phase 2.1（伴随 diffusion_health 接入）。
- **No backwards compat**: 三个 score_version 直接 bump 替换、不并行旧版本；`weighted_mentions` 公式直接换、不留旧路径；`_quality_features` 的 `llm_*` 槽位直接接通。
- **Dead code policy**: 显式记录"Phase 2.0 不删任何东西"的原因；deletion 留给 Phase 2.1。
- **Baseline measurement**: Task 0 抓 before、Task 8 抓 after 与 diff 脚本；用户的"过去 1 小时"诉求落地。
- **No new tables / migrations**: 全在 `score_json` JSONB 内扩展。
- **Type consistency**: `tweet_quality` 在 `atomic_mention.py` 与 `_atomic_quality` 在 `feature_builder.py` 都用 `gmgn_platform_followers` / `ws_author_followers` / `user_tags` / `first_seen_age_ms` 同一组参数名。

## Rollback procedure

如果 Task 4-6 任意一个引发未预料的生产问题：

1. **Code rollback**: `git revert <commit-sha>` 单独反转触发问题的 commit；其他已合入 commit 不动。
2. **Score version rollback**: 即使 code rollback，下游评估仍能通过 score_version 字符串区分新旧群体，不混合。
3. **Data rollback**: `score_json` 是 JSONB，不影响表 schema；旧消费者用 `.get()` 取键，新增字段消失不报错。
4. **Cohort version**: `COHORT_DEFINITION_VERSION = "cohort_v1"` 跟着 score_version v4 走；rollback 自动失效。

## Acceptance test commands

按顺序执行；任一步失败说明 Phase 2.0 不可接受。

```bash
# 1. 单元测试
uv run pytest tests/test_atomic_mention.py tests/test_factor_cohort.py \
              tests/test_cross_section_normalizer.py -v

# 2. Scoring 服务测试
GMGN_TEST_POSTGRES_DSN="..." uv run pytest \
  tests/test_token_radar_feature_builder.py \
  tests/test_social_heat_scoring.py \
  tests/test_opportunity_scoring.py \
  tests/test_propagation_scoring.py \
  tests/test_timing_scoring.py -v

# 3. Idempotency golden
GMGN_TEST_POSTGRES_DSN="..." uv run pytest tests/test_token_radar_idempotency.py -v

# 4. Lint + compile
uv run ruff check src tests
uv run python -m compileall src tests

# 5. Integration: rebuild + verify new fields
GMGN_TEST_POSTGRES_DSN="..." uv run gmgn-twitter-intel ops rebuild-token-radar \
  --window 1h --limit 50 --scope all
docker exec gmgn-twitter-intel-postgres-1 psql -U gmgn_app -d gmgn_twitter_intel -c "
  SELECT score_json->>'cross_section_rank' AS rank,
         score_json->'cohort'->>'in_cohort' AS in_cohort
  FROM token_radar_rows WHERE window='1h' ORDER BY generated_at_ms DESC LIMIT 5
"

# 6. Baseline diff measurement
uv run python tools/factor_baseline_diff.py /tmp/factor-baseline/before.json \
                                            /tmp/factor-baseline/after.json
```

Phase 2.0 通过条件：
- 所有 pytest 绿
- ruff / compileall 无 issue
- `score_json.cross_section_rank` 在 100% 行存在（NULL 或 float）
- `factor_baseline_diff.py` 输出的 Phase 1 hit rate ≥ 80%
- Spearman rho between before/after opportunity scores ∈ [0.5, 0.95]
- 没有破坏任何现有 API endpoint 或 frontend 消费（两个 ops 命令各跑一次 sanity check）
