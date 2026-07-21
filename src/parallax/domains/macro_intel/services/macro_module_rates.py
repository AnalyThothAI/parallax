from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.macro_intel.services.macro_module_shared import diagnostic_rows


def build_rates_module_read(
    *,
    module_id: str,
    concept_keys: Sequence[str],
    features: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows = diagnostic_rows(concept_keys, features)
    if not rows:
        return {}
    if module_id == "rates/fed-funds":
        return {"policy_diagnostics": _diagnostics("政策利率走廊", rows)}
    if module_id == "rates/yield-curve":
        return {"curve_diagnostics": _diagnostics("收益率曲线", rows)}
    return {"real_rate_diagnostics": _diagnostics("实际利率", rows)}


def _diagnostics(label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "label": label,
        "regime": "observed",
        "regime_label": "持久化观测",
        "summary": f"{len(rows)} 个利率序列可用。",
        "rows": rows,
        "real_yield_rows": rows,
        "inflation_rows": [],
        "spread_history": [],
        "tenor_comparison": [],
        "implications": ["以曲线和实际利率的共同方向确认宏观压力。"],
        "invalidations": ["关键期限观测缺失或方向反转。"],
    }


__all__ = ["build_rates_module_read"]
