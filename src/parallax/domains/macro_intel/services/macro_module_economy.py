from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.macro_intel.services.macro_module_shared import diagnostic_rows


def build_economy_module_read(
    *,
    module_id: str,
    concept_keys: Sequence[str],
    features: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows = diagnostic_rows(concept_keys, features)
    if not rows:
        return {}
    key, label = {
        "economy/gdp": ("growth_diagnostics", "增长"),
        "economy/employment": ("employment_diagnostics", "就业"),
        "economy/inflation": ("inflation_diagnostics", "通胀"),
    }[module_id]
    return {
        key: {
            "label": label,
            "regime": "observed",
            "regime_label": "持久化观测",
            "summary": f"{len(rows)} 个{label}序列可用。",
            "rows": rows,
            "implications": [f"以{label}趋势和修正方向确认宏观状态。"],
            "invalidations": ["关键官方序列缺失或修正。"],
        }
    }


__all__ = ["build_economy_module_read"]
