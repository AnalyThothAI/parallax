from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.macro_intel.services.macro_module_shared import diagnostic_rows


def build_risk_module_read(
    *,
    module_id: str,
    concept_keys: Sequence[str],
    features: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows = diagnostic_rows(concept_keys, features)
    if not rows:
        return {}
    key = "volatility_diagnostics" if module_id == "volatility/vix" else "credit_diagnostics"
    label = "波动率" if module_id == "volatility/vix" else "信用压力"
    return {
        key: {
            "label": label,
            "regime": "observed",
            "regime_label": "持久化观测",
            "summary": f"{len(rows)} 个{label}序列可用。",
            "rows": rows,
            "implications": [f"以{label}的广度和方向确认尾部风险。"],
            "invalidations": ["关键风险序列缺失或反转。"],
        }
    }


__all__ = ["build_risk_module_read"]
