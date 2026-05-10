"""One-shot before/after diff for the Phase 2.0 social factor changes.

Reads two JSON dumps of token_radar_rows and reports:
  - score distribution shift (mean, p50, p95)
  - rank correlation (Spearman rho on common subset)
  - top movers (by absolute opportunity score change)
  - Phase 1 hit rate (how many score_json carry account_profiles-derived
    quality signal)
  - cross-section rank coverage

Run:
    uv run python tools/factor_baseline_diff.py /tmp/factor-baseline/before.json \\
                                                /tmp/factor-baseline/after.json
"""

from __future__ import annotations

import json
import statistics
import sys


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
    """Phase 1 quality signal flows through when score_version is the new v3+
    OR when score_json shows a v4 opportunity (composite of upgraded subscores).
    """
    score_json = row.get("score_json") or {}
    heat_v = (score_json.get("heat") or {}).get("score_version", "")
    opp_v = (score_json.get("opportunity") or {}).get("score_version", "")
    return heat_v == "social_heat_v3" or opp_v == "social_opportunity_v4"


def _summarize(scores: list[float]) -> dict:
    if not scores:
        return {"n": 0}
    sorted_scores = sorted(scores)
    return {
        "n": len(scores),
        "mean": round(statistics.mean(scores), 2),
        "p50": round(statistics.median(scores), 2),
        "p95": round(sorted_scores[int(0.95 * (len(sorted_scores) - 1))], 2),
        "max": round(max(scores), 2),
    }


def main(before_path: str, after_path: str) -> int:
    before = _load(before_path)
    after = _load(after_path)
    common_ids = set(before) & set(after)
    print("== Token coverage ==")
    print(f"  before: {len(before)}, after: {len(after)}, common: {len(common_ids)}")
    print(f"  added in after: {len(set(after) - set(before))}")
    print(f"  dropped in after: {len(set(before) - set(after))}")

    before_scores = [s for s in (_opportunity(before[i]) for i in common_ids) if s is not None]
    after_scores = [s for s in (_opportunity(after[i]) for i in common_ids) if s is not None]
    print("\n== Opportunity score distribution ==")
    print(f"  before: {_summarize(before_scores)}")
    print(f"  after:  {_summarize(after_scores)}")

    print("\n== Phase 1 quality signal coverage ==")
    after_phase1 = sum(1 for i in common_ids if _has_phase1_quality(after[i]))
    pct = 100 * after_phase1 / max(1, len(common_ids))
    print(f"  after:  {after_phase1}/{len(common_ids)} ({pct:.1f}%)")
    print(f"  acceptance threshold: ≥ 80%  →  {'PASS' if pct >= 80 else 'FAIL'}")

    print("\n== Cross-section rank coverage ==")
    after_cs = sum(1 for i in common_ids if _has_cross_section(after[i]))
    cs_pct = 100 * after_cs / max(1, len(common_ids))
    print(f"  after:  {after_cs}/{len(common_ids)} ({cs_pct:.1f}%)")
    print(f"  acceptance threshold: 100%  →  {'PASS' if cs_pct >= 99.5 else 'FAIL'}")

    print("\n== Top 20 score changes (after - before) ==")
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

    print("\n== Rank correlation (Spearman, common subset) ==")
    common_with_scores = [(t, _opportunity(before[t]), _opportunity(after[t])) for t in common_ids]
    common_with_scores = [(t, b, a) for t, b, a in common_with_scores if b is not None and a is not None]
    if len(common_with_scores) >= 5:
        before_ranks = {t: r for r, (t, _, _) in enumerate(sorted(common_with_scores, key=lambda x: x[1]))}
        after_ranks = {t: r for r, (t, _, _) in enumerate(sorted(common_with_scores, key=lambda x: x[2]))}
        n = len(common_with_scores)
        sum_d2 = sum((before_ranks[t] - after_ranks[t]) ** 2 for t, _, _ in common_with_scores)
        rho = 1 - (6 * sum_d2) / (n * (n * n - 1))
        print(f"  n={n}, Spearman rho={rho:.3f}")
        in_range = 0.5 <= rho <= 0.95
        print(f"  acceptance threshold: ∈ [0.5, 0.95]  →  {'PASS' if in_range else 'FAIL'}")
    else:
        print(f"  Sample too small ({len(common_with_scores)} < 5)")

    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: factor_baseline_diff.py <before.json> <after.json>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
