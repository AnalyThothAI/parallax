from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from parallax.domains.macro_intel.services.macro_module_shared import mapping_list, text


def build_overview_module_read(
    *,
    scenario: Mapping[str, Any],
    market_event_flow: Mapping[str, Any] | None,
) -> dict[str, Any]:
    confirmations = mapping_list(scenario.get("confirmations"))
    contradictions = mapping_list(scenario.get("contradictions"))
    watch_triggers = mapping_list(scenario.get("watch_triggers"))
    invalidations = mapping_list(scenario.get("invalidations"))
    scenario_cases = mapping_list(scenario.get("scenario_cases"))
    trade_map = mapping_list(scenario.get("trade_map"))
    rows = [
        {
            "key": "regime",
            "label": "当前宏观状态",
            "value": text(scenario.get("current_regime")) or "data_gap",
            "evidence": [text(item.get("label")) for item in confirmations if text(item.get("label"))],
        }
    ]
    payload: dict[str, Any] = {
        "structured_analysis": {"key": "macro_regime", "label": "宏观结构", "rows": rows},
        "decision_console": {
            "top_changes": confirmations[:3],
            "quality_blockers": contradictions[:3],
            "scenario_cases": scenario_cases[:3],
            "trade_map": trade_map[:2],
            "watchlist_alerts": {"rules": watch_triggers[:6], "invalidations": invalidations[:6]},
        },
    }
    if market_event_flow is not None:
        payload["market_event_flow"] = dict(market_event_flow)
    return payload


__all__ = ["build_overview_module_read"]
