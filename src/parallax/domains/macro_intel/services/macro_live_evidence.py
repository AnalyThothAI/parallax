from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from parallax.domains.macro_intel.services.macro_live_catalog import (
    MACRO_LIVE_CATALOG,
    MACRO_LIVE_SECTION_LABELS,
    MACRO_LIVE_VIEW_IDS,
    MACRO_LIVE_VIEW_META,
    MacroLiveConceptSpec,
    MacroLiveViewId,
)

MACRO_LIVE_SCHEMA_VERSION: Literal["macro_live_evidence_v1"] = "macro_live_evidence_v1"
MacroLiveWindow = Literal["30d", "90d", "1y", "5y"]

MACRO_LIVE_WINDOWS: dict[MacroLiveWindow, int] = {
    "30d": 30,
    "90d": 90,
    "1y": 366,
    "5y": 1_826,
}
_MAX_HISTORY_POINTS = 160
_DASHBOARD_SUMMARY_LIMIT = 8
_UNCLASSIFIED_LIMIT = 50


def build_macro_live_evidence(
    *,
    view_id: Literal["dashboard"] | MacroLiveViewId,
    window: MacroLiveWindow,
    read_at_ms: int,
    observations: Sequence[Mapping[str, Any]],
    research: Mapping[str, Any] | None,
) -> dict[str, Any]:
    grouped = _group_by_concept(observations)
    material = {
        concept_key: _material_metric(spec, grouped.get(concept_key, ()), window=window)
        for concept_key, spec in MACRO_LIVE_CATALOG.items()
    }
    requested_views = MACRO_LIVE_VIEW_IDS if view_id == "dashboard" else (view_id,)
    views = [
        _view_payload(
            requested_view,
            material=material,
            grouped=grouped,
            window=window,
            dashboard=view_id == "dashboard",
        )
        for requested_view in requested_views
    ]
    return {
        "schema_version": MACRO_LIVE_SCHEMA_VERSION,
        "view_id": view_id,
        "window": window,
        "read_at_ms": int(read_at_ms),
        "views": views,
        "unclassified": _unclassified_metrics(grouped),
        "research": dict(research) if research is not None else None,
    }


def _view_payload(
    view_id: MacroLiveViewId,
    *,
    material: Mapping[str, dict[str, Any]],
    grouped: Mapping[str, Sequence[Mapping[str, Any]]],
    window: MacroLiveWindow,
    dashboard: bool,
) -> dict[str, Any]:
    metrics = [material[concept_key] for concept_key, spec in MACRO_LIVE_CATALOG.items() if spec.view_id == view_id]
    metrics.extend(_derived_metrics(view_id, material=material, grouped=grouped, window=window))
    available_count = sum(metric["availability"] == "available" for metric in metrics)
    latest_dates = [
        metric["observed_at"]
        for metric in metrics
        if metric["availability"] == "available" and metric["observed_at"] is not None
    ]
    received_times = [
        metric["received_at_ms"]
        for metric in metrics
        if metric["availability"] == "available" and metric["received_at_ms"] is not None
    ]
    title, description = MACRO_LIVE_VIEW_META[view_id]
    returned_metrics = metrics
    if dashboard:
        returned_metrics = [metric for metric in metrics if metric["summary"]][:_DASHBOARD_SUMMARY_LIMIT]
    return {
        "view_id": view_id,
        "title": title,
        "description": description,
        "metrics": returned_metrics,
        "total_metric_count": len(metrics),
        "available_count": available_count,
        "latest_observed_at": max(latest_dates) if latest_dates else None,
        "max_received_at_ms": max(received_times) if received_times else None,
    }


def _material_metric(
    spec: MacroLiveConceptSpec,
    rows: Sequence[Mapping[str, Any]],
    *,
    window: MacroLiveWindow,
) -> dict[str, Any]:
    history_rows = _preferred_history(spec, rows)
    history = [_history_point(spec, row) for row in history_rows]
    history = _downsample(history, limit=_MAX_HISTORY_POINTS)
    latest = history[-1] if history else None
    return {
        "concept_key": spec.concept_key,
        "page_id": spec.view_id,
        "section_id": spec.section_id,
        "section_label": spec.section_label,
        "display_label": spec.display_label,
        "display_order": spec.display_order,
        "summary": spec.summary,
        "kind": "material",
        "availability": "available" if latest is not None else "missing",
        "value_numeric": latest["value_numeric"] if latest else None,
        "unit": spec.unit,
        "frequency": latest["frequency"] if latest and latest["frequency"] else spec.frequency,
        "observed_at": latest["observed_at"] if latest else None,
        "source_timestamp": latest["source_timestamp"] if latest else None,
        "received_at_ms": latest["received_at_ms"] if latest else None,
        "source_name": latest["source_name"] if latest else None,
        "series_key": latest["series_key"] if latest else spec.preferred_series_key,
        "source_priority": latest["source_priority"] if latest else None,
        "data_quality": latest["data_quality"] if latest else None,
        "source_url": latest["source_url"] if latest else None,
        "history": history,
        "calculation": _window_change(spec, history, window=window),
    }


def _preferred_history(
    spec: MacroLiveConceptSpec,
    rows: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if not rows:
        return []
    preferred = [row for row in rows if str(row.get("series_key") or "") == spec.preferred_series_key]
    candidates = preferred or _best_series_rows(rows)
    selected: dict[date, Mapping[str, Any]] = {}
    for row in candidates:
        observed_at = _as_date(row.get("observed_at"))
        existing = selected.get(observed_at)
        if existing is None or _row_rank(row) > _row_rank(existing):
            selected[observed_at] = row
    return [selected[key] for key in sorted(selected)]


def _best_series_rows(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("source_name") or ""), str(row.get("series_key") or ""))].append(row)
    best_key = max(
        grouped,
        key=lambda key: (
            max(int(row.get("source_priority") or 0) for row in grouped[key]),
            key[1],
            key[0],
        ),
    )
    return grouped[best_key]


def _row_rank(row: Mapping[str, Any]) -> tuple[int, str, int, str]:
    return (
        int(row.get("source_priority") or 0),
        str(row.get("source_ts") or ""),
        int(row.get("ingested_at_ms") or 0),
        str(row.get("observation_id") or ""),
    )


def _history_point(spec: MacroLiveConceptSpec, row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "observed_at": _as_date(row.get("observed_at")),
        "value_numeric": _display_value(
            row.get("value_numeric"),
            source_unit=str(row.get("unit") or ""),
            display_unit=spec.unit,
        ),
        "source_timestamp": _optional_text(row.get("source_ts")),
        "received_at_ms": int(row["ingested_at_ms"]) if row.get("ingested_at_ms") is not None else None,
        "source_name": _optional_text(row.get("source_name")),
        "series_key": _optional_text(row.get("series_key")),
        "source_priority": int(row["source_priority"]) if row.get("source_priority") is not None else None,
        "frequency": _optional_text(row.get("frequency")),
        "data_quality": _optional_text(row.get("data_quality")),
        "source_url": _source_url(row.get("raw_payload_json")),
    }


def _window_change(
    spec: MacroLiveConceptSpec,
    history: Sequence[Mapping[str, Any]],
    *,
    window: MacroLiveWindow,
) -> dict[str, Any] | None:
    numeric = [point for point in history if _finite(point.get("value_numeric")) is not None]
    if spec.change_kind == "none" or len(numeric) < 2:
        return None
    first = float(numeric[0]["value_numeric"])
    last = float(numeric[-1]["value_numeric"])
    if spec.change_kind == "return_pct":
        if first == 0:
            return None
        result = ((last / first) - 1) * 100
        formula_id = "window_return_pct_v1"
        formula = "(latest / first - 1) × 100"
        unit = "percent"
    else:
        result = last - first
        formula_id = "window_difference_v1"
        formula = "latest - first"
        unit = spec.unit
    return _calculation(
        formula_id=formula_id,
        formula=formula,
        operands=[spec.concept_key],
        window=window,
        sample_size=len(numeric),
        result=result,
        unit=unit,
    )


def _derived_metrics(
    view_id: MacroLiveViewId,
    *,
    material: Mapping[str, dict[str, Any]],
    grouped: Mapping[str, Sequence[Mapping[str, Any]]],
    window: MacroLiveWindow,
) -> list[dict[str, Any]]:
    if view_id == "liquidity-funding":
        return [
            _net_liquidity_metric(material, window=window),
            *[
                _spread_metric(
                    left,
                    "fed:iorb",
                    derived_key,
                    label,
                    material=material,
                    window=window,
                )
                for left, derived_key, label in (
                    ("liquidity:sofr", "derived:sofr_minus_iorb_bps", "SOFR–IORB 利差"),
                    ("liquidity:bgcr", "derived:bgcr_minus_iorb_bps", "BGCR–IORB 利差"),
                    ("liquidity:tgcr", "derived:tgcr_minus_iorb_bps", "TGCR–IORB 利差"),
                    ("fed:obfr", "derived:obfr_minus_iorb_bps", "OBFR–IORB 利差"),
                    ("fed:effr", "derived:effr_minus_iorb_bps", "EFFR–IORB 利差"),
                )
            ],
        ]
    if view_id == "credit":
        return [
            _difference_metric(
                "credit:hy_ccc_oas",
                "credit:hy_bb_oas",
                "derived:credit_ccc_minus_bb_oas",
                "CCC–BB 信用利差",
                unit="basis_points",
                formula_id="credit_ccc_minus_bb_oas_v1",
                material=material,
                window=window,
            )
        ]
    if view_id == "cross-asset":
        return [
            _correlation_metric(
                "asset:spy",
                right,
                label,
                material=material,
                grouped=grouped,
                window=window,
            )
            for right, label in (
                ("asset:tlt", "SPY × TLT 收益相关性"),
                ("asset:hyg", "SPY × HYG 收益相关性"),
                ("asset:gld", "SPY × GLD 收益相关性"),
                ("asset:uso", "SPY × USO 收益相关性"),
                ("fx:dxy", "SPY × DXY 收益相关性"),
                ("crypto:btc", "SPY × BTC 收益相关性"),
            )
        ]
    return []


def _net_liquidity_metric(
    material: Mapping[str, dict[str, Any]],
    *,
    window: MacroLiveWindow,
) -> dict[str, Any]:
    keys = ("liquidity:fed_assets", "liquidity:tga", "liquidity:on_rrp")
    values = [_metric_value(material[key]) for key in keys]
    available = all(value is not None for value in values)
    result = None
    if available:
        fed_assets, tga, on_rrp_billions = (float(value) for value in values if value is not None)
        result = fed_assets - tga - (on_rrp_billions * 1_000)
    calculation = _calculation(
        formula_id="fed_assets_minus_tga_minus_on_rrp_v1",
        formula="Fed assets (USD millions) - TGA (USD millions) - ON RRP (USD billions × 1,000)",
        operands=list(keys),
        window=window,
        sample_size=sum(value is not None for value in values),
        result=result,
        unit="millions_usd",
    )
    return _derived_metric(
        concept_key="derived:net_liquidity_accounting_proxy",
        label="净流动性会计代理",
        value=result,
        unit="millions_usd",
        calculation=calculation,
        inputs=[material[key] for key in keys],
        summary=True,
    )


def _spread_metric(
    left: str,
    right: str,
    concept_key: str,
    label: str,
    *,
    material: Mapping[str, dict[str, Any]],
    window: MacroLiveWindow,
) -> dict[str, Any]:
    left_value = _metric_value(material[left])
    right_value = _metric_value(material[right])
    result = None if left_value is None or right_value is None else (left_value - right_value) * 100
    calculation = _calculation(
        formula_id=f"{concept_key.removeprefix('derived:')}_v1",
        formula=f"({left} - {right}) × 100",
        operands=[left, right],
        window=window,
        sample_size=sum(value is not None for value in (left_value, right_value)),
        result=result,
        unit="basis_points",
    )
    return _derived_metric(
        concept_key=concept_key,
        label=label,
        value=result,
        unit="basis_points",
        calculation=calculation,
        inputs=[material[left], material[right]],
        summary=left == "liquidity:sofr",
    )


def _difference_metric(
    left: str,
    right: str,
    concept_key: str,
    label: str,
    *,
    unit: str,
    formula_id: str,
    material: Mapping[str, dict[str, Any]],
    window: MacroLiveWindow,
) -> dict[str, Any]:
    left_value = _metric_value(material[left])
    right_value = _metric_value(material[right])
    result = None if left_value is None or right_value is None else left_value - right_value
    calculation = _calculation(
        formula_id=formula_id,
        formula=f"{left} - {right}",
        operands=[left, right],
        window=window,
        sample_size=sum(value is not None for value in (left_value, right_value)),
        result=result,
        unit=unit,
    )
    return _derived_metric(
        concept_key=concept_key,
        label=label,
        value=result,
        unit=unit,
        calculation=calculation,
        inputs=[material[left], material[right]],
        summary=True,
    )


def _correlation_metric(
    left: str,
    right: str,
    label: str,
    *,
    material: Mapping[str, dict[str, Any]],
    grouped: Mapping[str, Sequence[Mapping[str, Any]]],
    window: MacroLiveWindow,
) -> dict[str, Any]:
    left_history = _preferred_history(MACRO_LIVE_CATALOG[left], grouped.get(left, ()))
    right_history = _preferred_history(MACRO_LIVE_CATALOG[right], grouped.get(right, ()))
    left_returns = _returns_by_date(left_history)
    right_returns = _returns_by_date(right_history)
    overlap = sorted(set(left_returns).intersection(right_returns))
    result = _pearson(
        [left_returns[day] for day in overlap],
        [right_returns[day] for day in overlap],
    )
    concept_key = f"derived:correlation:{left}:{right}"
    calculation = _calculation(
        formula_id="pearson_return_correlation_v1",
        formula="Pearson correlation of aligned one-period returns",
        operands=[left, right],
        window=window,
        sample_size=len(overlap),
        result=result,
        unit="correlation",
    )
    return _derived_metric(
        concept_key=concept_key,
        label=label,
        value=result,
        unit="correlation",
        calculation=calculation,
        inputs=[material[left], material[right]],
        summary=right in {"asset:tlt", "asset:hyg"},
    )


def _returns_by_date(rows: Sequence[Mapping[str, Any]]) -> dict[date, float]:
    points = [(_as_date(row.get("observed_at")), _finite(row.get("value_numeric"))) for row in rows]
    returns: dict[date, float] = {}
    previous: float | None = None
    for observed_at, value in points:
        if value is None or previous is None or previous == 0:
            previous = value
            continue
        returns[observed_at] = (value / previous) - 1
        previous = value
    return returns


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_denominator = sum((x - left_mean) ** 2 for x in left)
    right_denominator = sum((y - right_mean) ** 2 for y in right)
    denominator = math.sqrt(left_denominator * right_denominator)
    return None if denominator == 0 else numerator / denominator


def _derived_metric(
    *,
    concept_key: str,
    label: str,
    value: float | None,
    unit: str,
    calculation: Mapping[str, Any],
    inputs: Sequence[Mapping[str, Any]],
    summary: bool,
) -> dict[str, Any]:
    available_inputs = [item for item in inputs if item["availability"] == "available"]
    observed_dates = [item["observed_at"] for item in available_inputs if item["observed_at"] is not None]
    received_times = [item["received_at_ms"] for item in available_inputs if item["received_at_ms"] is not None]
    return {
        "concept_key": concept_key,
        "page_id": _derived_page_id(concept_key),
        "section_id": "derived",
        "section_label": MACRO_LIVE_SECTION_LABELS["derived"],
        "display_label": label,
        "display_order": 10_000,
        "summary": summary,
        "kind": "derived",
        "availability": "available" if value is not None else "missing",
        "value_numeric": _rounded(value),
        "unit": unit,
        "frequency": "derived",
        "observed_at": min(observed_dates) if value is not None and observed_dates else None,
        "source_timestamp": None,
        "received_at_ms": max(received_times) if value is not None and received_times else None,
        "source_name": None,
        "series_key": None,
        "source_priority": None,
        "data_quality": None,
        "source_url": None,
        "history": [],
        "calculation": dict(calculation),
    }


def _derived_page_id(concept_key: str) -> MacroLiveViewId:
    if "liquidity" in concept_key or "iorb" in concept_key:
        return "liquidity-funding"
    if "credit" in concept_key:
        return "credit"
    return "cross-asset"


def _calculation(
    *,
    formula_id: str,
    formula: str,
    operands: list[str],
    window: MacroLiveWindow,
    sample_size: int,
    result: float | None,
    unit: str,
) -> dict[str, Any]:
    return {
        "formula_id": formula_id,
        "formula": formula,
        "operands": operands,
        "window": window,
        "sample_size": int(sample_size),
        "result": _rounded(result),
        "unit": unit,
    }


def _metric_value(metric: Mapping[str, Any]) -> float | None:
    return _finite(metric.get("value_numeric")) if metric.get("availability") == "available" else None


def _unclassified_metrics(
    grouped: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for concept_key in sorted(set(grouped) - set(MACRO_LIVE_CATALOG)):
        by_series: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
        for row in grouped[concept_key]:
            by_series[(str(row.get("source_name") or ""), str(row.get("series_key") or ""))].append(row)
        for (source_name, series_key), series_rows in sorted(by_series.items()):
            latest = max(series_rows, key=lambda row: (_as_date(row.get("observed_at")), _row_rank(row)))
            value = _finite(latest.get("value_numeric"))
            rows.append(
                {
                    "concept_key": concept_key,
                    "page_id": None,
                    "section_id": "unclassified",
                    "section_label": MACRO_LIVE_SECTION_LABELS["unclassified"],
                    "display_label": concept_key,
                    "display_order": 0,
                    "summary": False,
                    "kind": "material",
                    "availability": "available" if value is not None else "missing",
                    "value_numeric": value,
                    "unit": _optional_text(latest.get("unit")),
                    "frequency": _optional_text(latest.get("frequency")),
                    "observed_at": _as_date(latest.get("observed_at")),
                    "source_timestamp": _optional_text(latest.get("source_ts")),
                    "received_at_ms": (
                        int(latest["ingested_at_ms"]) if latest.get("ingested_at_ms") is not None else None
                    ),
                    "source_name": source_name or None,
                    "series_key": series_key or None,
                    "source_priority": (
                        int(latest["source_priority"]) if latest.get("source_priority") is not None else None
                    ),
                    "data_quality": _optional_text(latest.get("data_quality")),
                    "source_url": _source_url(latest.get("raw_payload_json")),
                    "history": [],
                    "calculation": None,
                }
            )
    rows.sort(
        key=lambda row: (
            -(int(row["received_at_ms"]) if row["received_at_ms"] is not None else -1),
            str(row["concept_key"]),
            str(row["series_key"]),
        )
    )
    return rows[:_UNCLASSIFIED_LIMIT]


def _group_by_concept(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in observations:
        concept_key = str(row.get("concept_key") or "").strip()
        if concept_key:
            grouped[concept_key].append(row)
    return grouped


def _display_value(value: object, *, source_unit: str, display_unit: str) -> float | None:
    numeric = _finite(value)
    if numeric is None:
        return None
    if source_unit == display_unit or not source_unit:
        return numeric
    if source_unit == "percent" and display_unit == "basis_points":
        return numeric * 100
    if source_unit == "billions_usd" and display_unit == "millions_usd":
        return numeric * 1_000
    if source_unit == "millions_usd" and display_unit == "billions_usd":
        return numeric / 1_000
    return numeric


def _finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        resolved = float(value)
        return resolved if math.isfinite(resolved) else None
    return None


def _rounded(value: float | None) -> float | None:
    if value is None:
        return None
    rounded = round(float(value), 8)
    return 0.0 if rounded == -0.0 else rounded


def _source_url(raw_payload: object) -> str | None:
    if not isinstance(raw_payload, Mapping):
        return None
    provenance = raw_payload.get("provenance")
    if isinstance(provenance, Sequence) and not isinstance(provenance, (str, bytes)) and provenance:
        first = provenance[0]
        if isinstance(first, Mapping):
            return _optional_text(first.get("source_url"))
    return _optional_text(raw_payload.get("source_url"))


def _downsample(
    points: Sequence[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if len(points) <= limit:
        return list(points)
    indexes = {round(index * (len(points) - 1) / (limit - 1)) for index in range(limit)}
    return [point for index, point in enumerate(points) if index in indexes]


def _as_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "MACRO_LIVE_SCHEMA_VERSION",
    "MACRO_LIVE_WINDOWS",
    "MacroLiveWindow",
    "build_macro_live_evidence",
]
