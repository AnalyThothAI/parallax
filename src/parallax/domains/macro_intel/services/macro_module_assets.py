from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.macro_intel.services.macro_module_shared import diagnostic_rows


def build_asset_module_read(
    *,
    module_id: str,
    concept_keys: Sequence[str],
    features: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows = diagnostic_rows(concept_keys, features)
    if not rows:
        return {}
    positive = sum(1 for row in rows if isinstance(row.get("change"), int | float) and row["change"] > 0)
    negative = sum(1 for row in rows if isinstance(row.get("change"), int | float) and row["change"] < 0)
    if positive > negative:
        regime, label = "risk_on", "风险偏好占优"
    elif negative > positive:
        regime, label = "defensive", "防守占优"
    else:
        regime, label = "mixed", "资产表现分化"
    key = "asset_diagnostics" if module_id == "assets" else "asset_class_diagnostics"
    return {
        key: {
            "label": "跨资产诊断" if module_id == "assets" else "资产类别诊断",
            "regime": regime,
            "regime_label": label,
            "summary": f"{len(rows)} 个持久化资产序列参与判断。",
            "rows": rows,
            "implications": [label],
            "invalidations": ["后续观测方向反转时重评。"],
        }
    }


__all__ = ["build_asset_module_read"]
