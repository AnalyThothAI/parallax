from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from parallax.domains.macro_intel._constants import MACRO_CONCEPT_METADATA, MACRO_MIN_CHART_POINTS
from parallax.domains.macro_intel.services.macro_module_catalog import (
    MacroChartSpec,
    MacroModuleConfig,
    MacroTableSpec,
)

_MODULE_CHART_POINT_LIMIT = 260


def required_mapping(value: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if field_name not in value or value[field_name] is None:
        raise ValueError(f"macro_view_snapshot_section_required:{field_name}")
    field = value[field_name]
    if not isinstance(field, Mapping):
        raise ValueError(f"macro_view_snapshot_section_invalid:{field_name}")
    return dict(field)


def required_list(value: Mapping[str, Any], field_name: str) -> list[Any]:
    if field_name not in value or value[field_name] is None:
        raise ValueError(f"macro_view_snapshot_section_required:{field_name}")
    field = value[field_name]
    if isinstance(field, Mapping | str | bytes | bytearray) or not isinstance(field, Sequence):
        raise ValueError(f"macro_view_snapshot_section_invalid:{field_name}")
    return list(field)


def module_concepts(config: MacroModuleConfig) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*config.required_concepts, *config.optional_concepts)))


def build_feature_map(
    snapshot_features: Mapping[str, Any],
    *,
    observations: Sequence[Mapping[str, Any]],
    concept_keys: Sequence[str],
) -> dict[str, dict[str, Any]]:
    wanted = set(concept_keys)
    features = {
        str(concept_key): dict(feature)
        for concept_key, feature in snapshot_features.items()
        if concept_key in wanted and isinstance(feature, Mapping)
    }
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for observation in observations:
        concept_key = str(observation.get("concept_key") or "")
        if concept_key in wanted:
            grouped.setdefault(concept_key, []).append(observation)
    for concept_key, rows in grouped.items():
        observation_feature = _feature_from_observations(concept_key, rows)
        if observation_feature is None:
            continue
        current = features.get(concept_key)
        if current is None:
            features[concept_key] = observation_feature
            continue
        current_latest = mapping(current.get("latest"))
        projected_latest = mapping(observation_feature["latest"])
        current_date = date_string(current_latest.get("observed_at")) or ""
        projected_date = date_string(projected_latest.get("observed_at")) or ""
        current_points = int_value(current.get("history_points")) or 0
        projected_points = int_value(observation_feature.get("history_points")) or 0
        if projected_date >= current_date or projected_points > current_points:
            merged = dict(current)
            merged.update(observation_feature)
            features[concept_key] = merged
    return features


def build_tiles(concept_keys: Sequence[str], features: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [build_tile(key, features[key]) for key in concept_keys if key in features]


def diagnostic_rows(
    concept_keys: Sequence[str],
    features: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for concept_key in concept_keys:
        feature = features.get(concept_key)
        if feature is None:
            continue
        latest = mapping(feature.get("latest"))
        current = number(latest.get("value"))
        if current is None:
            continue
        history = _chart_history(feature)
        previous = number(history[-2].get("value")) if len(history) > 1 else None
        change = current - previous if previous is not None else None
        rows.append(
            {
                "key": concept_key,
                "label": concept_label(concept_key),
                "current": current,
                "display_value": display_number(current),
                "change": change,
                "change_label": "--" if change is None else f"{change:+.2f}",
                "observed_at": date_string(latest.get("observed_at")),
                "status": "ready",
                "status_label": status_label("ready"),
            }
        )
    return rows


def build_tile(concept_key: str, feature: Mapping[str, Any]) -> dict[str, Any]:
    metadata = concept_metadata(concept_key)
    latest = mapping(feature.get("latest"))
    value = number(latest.get("value"))
    observed_at = date_string(latest.get("observed_at"))
    unit = text(latest.get("unit"))
    quality = text(feature.get("data_quality")) or "unknown"
    source = mapping(feature.get("source"))
    source_label = text(source.get("name")) or text(source.get("source_name")) or "unknown"
    return {
        "concept_key": concept_key,
        "label": metadata["label"],
        "short_label": metadata["short_label"],
        "description": metadata["description"],
        "value": value,
        "display_value": display_number(value),
        "unit": unit,
        "unit_label": metadata["unit_label"],
        "delta_label": delta_label(feature),
        "source_label": source_label,
        "observed_at": observed_at,
        "observed_at_label": f"观测于 {observed_at}" if observed_at else "观测时间缺失",
        "quality": quality,
        "quality_label": quality_label(quality),
        "score_participation": bool(feature.get("score_participation")),
        "history_points": int_value(feature.get("history_points")) or 0,
    }


def build_primary_chart(
    spec: MacroChartSpec,
    features: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    series = [series_payload(key, features[key]) for key in spec.concept_keys if key in features]
    missing = [key for key in spec.concept_keys if key not in features]
    ready_series = [item for item in series if len(item["points"]) >= MACRO_MIN_CHART_POINTS]
    status = "ready" if ready_series else "partial" if series else "missing"
    return {
        "id": spec.chart_id,
        "kind": "time_series",
        "title": chart_title(spec.chart_id),
        "subtitle": "持久化宏观观测的有界历史",
        "status": status,
        "status_label": status_label(status),
        "min_points": MACRO_MIN_CHART_POINTS,
        "missing_concept_keys": missing,
        "series": series,
    }


def series_payload(concept_key: str, feature: Mapping[str, Any]) -> dict[str, Any]:
    metadata = concept_metadata(concept_key)
    points = [
        {
            "observed_at": date_string(point.get("observed_at")),
            "value": number(point.get("value")),
        }
        for point in mapping_list(feature.get("history"))
        if date_string(point.get("observed_at")) is not None and number(point.get("value")) is not None
    ][-_MODULE_CHART_POINT_LIMIT:]
    return {
        "concept_key": concept_key,
        "label": metadata["short_label"],
        "unit_label": metadata["unit_label"],
        "points": points,
    }


def build_tables(
    specs: Sequence[MacroTableSpec],
    *,
    config: MacroModuleConfig,
    features: Mapping[str, Mapping[str, Any]],
    data_gaps: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    tables = [_table(spec, features) for spec in specs]
    tables.append(_availability_table(config, features, data_gaps))
    return tables


def build_data_health(
    *,
    config: MacroModuleConfig,
    snapshot_status: str,
    snapshot_gaps: Sequence[Any],
    features: Mapping[str, Mapping[str, Any]],
    primary_chart: Mapping[str, Any],
) -> dict[str, Any]:
    global_gaps = [normalise_gap(gap, scope="global_reference") for gap in snapshot_gaps]
    missing_required = [key for key in config.required_concepts if key not in features]
    missing_optional = [key for key in config.optional_concepts if key not in features]
    module_gaps = [missing_concept_gap(key, required=True) for key in missing_required]
    module_gaps.extend(missing_concept_gap(key, required=False) for key in missing_optional)
    chart_gaps = [
        missing_concept_gap(key, required=key in config.required_concepts, scope="chart_blocker")
        for key in primary_chart.get("missing_concept_keys", [])
    ]
    if snapshot_status in {"missing", "stale"}:
        summary = snapshot_status
    elif missing_required or primary_chart.get("status") != "ready":
        summary = "partial"
    else:
        summary = "ready"
    return {
        "summary_status": summary,
        "summary_label": status_label(summary),
        "module_gaps": unique_gaps(module_gaps),
        "chart_gaps": unique_gaps(chart_gaps),
        "global_gaps": unique_gaps(global_gaps),
    }


def build_evidence(scenario: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        key: [evidence_item(item) for item in mapping_list(scenario.get(key))]
        for key in ("confirmations", "contradictions", "watch_triggers", "invalidations")
    }


def build_transmission(
    *,
    config: MacroModuleConfig,
    chain: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, value in chain.items():
        if not isinstance(value, Mapping):
            continue
        regime = text(value.get("regime")) or "data_gap"
        rows.append(
            {
                "key": str(key),
                "label": concept_label(str(key)),
                "kind": "chain",
                "status": regime,
                "status_label": status_label(regime),
                "value": number(value.get("score")),
                "active": str(key) in config.section or config.section == "overview",
            }
        )
    return rows


def build_provenance(
    *,
    snapshot: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    facts_max_observed_at: object,
    projection_lag_days: int | None,
    projection_behind_facts: bool,
) -> dict[str, Any]:
    sources: dict[str, dict[str, Any]] = {}
    for observation in observations:
        source = text(observation.get("source_name")) or "unknown"
        row = sources.setdefault(source, {"concepts": set(), "latest_observed_at": None, "quality": "ok"})
        row["concepts"].add(str(observation.get("concept_key") or ""))
        observed_at = date_string(observation.get("observed_at"))
        if observed_at and (row["latest_observed_at"] is None or observed_at > row["latest_observed_at"]):
            row["latest_observed_at"] = observed_at
        quality = text(observation.get("data_quality")) or "unknown"
        if quality not in {"ok", "ready"}:
            row["quality"] = quality
    return {
        "projection_version": snapshot.get("projection_version"),
        "currentness": {
            "facts_max_observed_at": date_string(facts_max_observed_at),
            "projection_lag_days": projection_lag_days,
            "projection_behind_facts": bool(projection_behind_facts),
        },
        "rows": [
            {
                "row_id": f"source:{source}",
                "source_label": source,
                "status": row["quality"],
                "status_label": quality_label(row["quality"]),
                "latest_observed_at": row["latest_observed_at"],
                "concept_count": len(row["concepts"]),
                "notes": "",
            }
            for source, row in sorted(sources.items())
        ],
    }


def official_event_flow(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    rows: list[dict[str, Any]] = []
    for observation in observations:
        concept_key = str(observation.get("concept_key") or "")
        if not concept_key.startswith("event:"):
            continue
        metadata = mapping(observation.get("event_metadata_json"))
        code = text(metadata.get("event_code")) or text(observation.get("series_key"))
        observed_at = date_string(observation.get("observed_at"))
        if not code or not observed_at:
            continue
        label = text(metadata.get("text_value")) or concept_label(concept_key)
        row = {
            "key": f"event:{code}:{observed_at}",
            "label": label,
            "detail": label,
            "source": text(observation.get("source_name")) or "unknown",
            "kind": event_kind(code),
            "observed_at": observed_at,
            "value": number(observation.get("value_numeric")),
        }
        source_url = text(metadata.get("source_url"))
        if source_url:
            row["source_url"] = source_url
        rows.append(row)
    if not rows:
        return None
    rows.sort(key=lambda item: (str(item["observed_at"]), str(item["key"])))
    return {"key": "market_event_flow", "label": "市场事件流", "rows": rows[:12]}


def mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def mapping_list(value: object) -> list[dict[str, Any]]:
    if isinstance(value, Mapping | str | bytes | bytearray) or not isinstance(value, Sequence):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal | int | float):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def int_value(value: object) -> int | None:
    numeric = number(value)
    return int(numeric) if numeric is not None else None


def text(value: object) -> str | None:
    result = str(value or "").strip()
    return result or None


def date_string(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return text(value)


def concept_metadata(concept_key: str) -> dict[str, str]:
    metadata = MACRO_CONCEPT_METADATA.get(concept_key, {})
    label = text(metadata.get("label")) or concept_key
    return {
        "label": label,
        "short_label": text(metadata.get("short_label")) or label,
        "description": text(metadata.get("description")) or "持久化宏观观测",
        "unit_label": text(metadata.get("unit_label")) or "",
    }


def concept_label(concept_key: str) -> str:
    return concept_metadata(concept_key)["label"]


def display_number(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def status_label(status: object) -> str:
    key = str(status or "unknown").lower()
    return {
        "ready": "就绪",
        "ok": "正常",
        "partial": "部分可用",
        "missing": "缺失",
        "stale": "过期",
        "data_gap": "数据缺口",
        "tightening": "收紧",
        "easing": "宽松",
        "neutral": "中性",
    }.get(key, str(status or "未知"))


def quality_label(quality: str) -> str:
    return status_label(quality)


def related_routes(config: MacroModuleConfig) -> list[dict[str, str]]:
    return [{"href": route, "label": route.rsplit("/", 1)[-1].replace("-", " ")} for route in config.related_routes]


def _feature_from_observations(
    concept_key: str,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    ordered = sorted(rows, key=lambda row: date_string(row.get("observed_at")) or "", reverse=True)
    numeric_rows = [row for row in ordered if number(row.get("value_numeric")) is not None]
    if not numeric_rows:
        return None
    latest = numeric_rows[0]
    history = [
        {"observed_at": date_string(row.get("observed_at")), "value": number(row.get("value_numeric"))}
        for row in reversed(numeric_rows)
    ]
    return {
        "concept_key": concept_key,
        "latest": {
            "value": number(latest.get("value_numeric")),
            "observed_at": date_string(latest.get("observed_at")),
            "unit": text(latest.get("unit")) or "unknown",
        },
        "history": history,
        "history_points": len(history),
        "data_quality": text(latest.get("data_quality")) or "unknown",
        "source": {"name": text(latest.get("source_name")) or "unknown"},
        "score_participation": False,
    }


def _table(spec: MacroTableSpec, features: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    rows = [build_tile(key, features[key]) for key in spec.concept_keys if key in features]
    missing = [key for key in spec.concept_keys if key not in features]
    status = "ready" if rows and not missing else "partial" if rows else "missing"
    return {
        "id": spec.table_id,
        "title": spec.table_id.replace("_", " "),
        "status": status,
        "missing_concept_keys": missing,
        "columns": [
            {"key": "label", "label": "指标"},
            {"key": "display_value", "label": "最新值"},
            {"key": "observed_at", "label": "观测日"},
            {"key": "source_label", "label": "来源"},
        ],
        "rows": rows,
    }


def _availability_table(
    config: MacroModuleConfig,
    features: Mapping[str, Mapping[str, Any]],
    data_gaps: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    gaps_by_concept = {str(gap.get("concept_key") or ""): gap for gap in data_gaps}
    rows = []
    for key in module_concepts(config):
        feature = features.get(key)
        rows.append(
            {
                "concept_key": key,
                "label": concept_label(key),
                "required": key in config.required_concepts,
                "available": feature is not None,
                "source_label": text(mapping(mapping(feature or {}).get("source")).get("name")) if feature else None,
                "gap": gaps_by_concept.get(key),
            }
        )
    return {
        "id": "availability_proxy_notes",
        "title": "数据可用性 / 代理说明",
        "status": "ready" if all(row["available"] for row in rows if row["required"]) else "partial",
        "rows": rows,
    }


def _chart_history(feature: Mapping[str, Any]) -> list[dict[str, Any]]:
    return mapping_list(feature.get("history"))


def delta_label(feature: Mapping[str, Any]) -> str:
    delta = mapping(feature.get("delta"))
    value = number(delta.get("20d"))
    return "--" if value is None else f"20d {value:+.2f}"


def normalise_gap(value: object, *, scope: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        gap = dict(value)
        code = text(gap.get("code")) or "macro_data_gap"
        gap["code"] = code
        gap.setdefault("label", code.replace("_", " "))
        gap.setdefault("severity", "warning")
        gap["scope"] = scope
        return gap
    code = text(value) or "macro_data_gap"
    return {"code": code, "label": code.replace("_", " "), "severity": "warning", "scope": scope}


def missing_concept_gap(concept_key: str, *, required: bool, scope: str = "module_gap") -> dict[str, Any]:
    return {
        "code": f"missing_concept:{concept_key}",
        "concept_key": concept_key,
        "label": f"缺少 {concept_label(concept_key)}",
        "severity": "critical" if required else "info",
        "scope": scope,
        "remediation_hint": "等待 Macro 投影从持久化观测重建。",
    }


def unique_gaps(gaps: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for gap in gaps:
        key = (str(gap.get("code") or ""), str(gap.get("scope") or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(gap))
    return result


def evidence_item(item: Mapping[str, Any]) -> dict[str, Any]:
    code = text(item.get("code")) or text(item.get("key")) or "macro_signal"
    label = text(item.get("label")) or code.replace("_", " ")
    return {"code": code, "label": label, "evidence_label": text(item.get("evidence_label"))}


def event_kind(code: str) -> str:
    if code.startswith("official_fed_text:"):
        return "fed_text"
    if "auction" in code:
        return "auction_calendar"
    return "calendar"


def chart_title(chart_id: str) -> str:
    return chart_id.replace("_", " ")


__all__ = [
    "build_data_health",
    "build_evidence",
    "build_feature_map",
    "build_primary_chart",
    "build_provenance",
    "build_tables",
    "build_tiles",
    "build_transmission",
    "concept_label",
    "date_string",
    "diagnostic_rows",
    "display_number",
    "mapping",
    "mapping_list",
    "module_concepts",
    "number",
    "official_event_flow",
    "related_routes",
    "required_list",
    "required_mapping",
    "status_label",
    "text",
]
