from __future__ import annotations

import math
from typing import Any


def score_oi_radar_row(
    *,
    open_interest_usd: Any,
    open_interest_change_pct_1h: Any,
    volume_24h_usd: Any,
    funding_rate: Any,
) -> dict[str, Any]:
    oi_value = max(0.0, _float(open_interest_usd))
    change_pct = _float(open_interest_change_pct_1h)
    volume = max(0.0, _float(volume_24h_usd))
    funding = abs(_float(funding_rate))

    oi_score = min(45.0, math.log10(max(1.0, oi_value)) * 4.5)
    change_score = min(30.0, abs(change_pct) * 1.5)
    volume_score = min(20.0, math.log10(max(1.0, volume)) * 2.0)
    funding_penalty = min(12.0, funding * 10_000.0)
    total = max(0.0, min(100.0, oi_score + change_score + volume_score - funding_penalty))
    return {
        "score": round(total, 4),
        "components": {
            "oi_score": round(oi_score, 4),
            "change_score": round(change_score, 4),
            "volume_score": round(volume_score, 4),
            "funding_penalty": round(funding_penalty, 4),
        },
    }


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
