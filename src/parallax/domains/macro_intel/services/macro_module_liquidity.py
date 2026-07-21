from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.macro_intel.services.macro_module_shared import diagnostic_rows


def build_liquidity_module_read(
    *,
    concept_keys: Sequence[str],
    features: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows = diagnostic_rows(concept_keys, features)
    if not rows:
        return {}
    return {
        "liquidity_diagnostics": {
            "label": "美元流动性",
            "regime": "observed",
            "regime_label": "持久化观测",
            "summary": f"{len(rows)} 个流动性序列可用。",
            "rows": rows,
            "implications": ["RRP、TGA 与银行准备金共同决定净流动性方向。"],
            "invalidations": ["关键余额序列未更新。"],
        }
    }


__all__ = ["build_liquidity_module_read"]
