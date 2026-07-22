from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

from parallax.domains.macro_intel._constants import MACRO_MODULE_VIEW_VERSION
from parallax.domains.macro_intel.services.macro_assets_brief import build_macro_assets_brief
from parallax.domains.macro_intel.services.macro_module_assets import build_asset_module_read
from parallax.domains.macro_intel.services.macro_module_catalog import (
    MACRO_MODULE_IDS,
    MacroModuleConfig,
    get_macro_module_config,
)
from parallax.domains.macro_intel.services.macro_module_economy import build_economy_module_read
from parallax.domains.macro_intel.services.macro_module_liquidity import build_liquidity_module_read
from parallax.domains.macro_intel.services.macro_module_overview import build_overview_module_read
from parallax.domains.macro_intel.services.macro_module_rates import build_rates_module_read
from parallax.domains.macro_intel.services.macro_module_risk import build_risk_module_read
from parallax.domains.macro_intel.services.macro_module_shared import (
    build_data_health,
    build_evidence,
    build_feature_map,
    build_primary_chart,
    build_provenance,
    build_tables,
    build_tiles,
    build_transmission,
    module_concepts,
    official_event_flow,
    related_routes,
    required_list,
    required_mapping,
    status_label,
    text,
)


def build_macro_module_view(
    module_id: str,
    *,
    snapshot: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    daily_brief: Mapping[str, Any] | None = None,
    facts_max_observed_at: object = None,
    projection_lag_days: int | None = None,
    projection_behind_facts: bool = False,
) -> dict[str, Any]:
    config = get_macro_module_config(module_id)
    snapshot_sections = _snapshot_sections(snapshot)
    concept_keys = module_concepts(config)
    feature_map = build_feature_map(
        snapshot_sections["features_json"],
        observations=observations,
        concept_keys=concept_keys,
    )
    primary_chart = build_primary_chart(config.chart_specs[0], feature_map)
    data_health = build_data_health(
        config=config,
        snapshot_status=_required_text(snapshot, "status"),
        snapshot_gaps=snapshot_sections["data_gaps_json"],
        features=feature_map,
        primary_chart=primary_chart,
    )
    module_read = _base_module_read(config=config, snapshot=snapshot, data_health=data_health)
    module_read.update(
        _domain_module_read(
            config=config,
            features=feature_map,
            scenario=snapshot_sections["scenario_json"],
            observations=observations,
        )
    )
    payload: dict[str, Any] = {
        "snapshot": _snapshot_header(config=config, snapshot=snapshot),
        "tiles": build_tiles(concept_keys, feature_map),
        "primary_chart": primary_chart,
        "tables": build_tables(
            config.table_specs,
            config=config,
            features=feature_map,
            data_gaps=data_health["module_gaps"],
        ),
        "module_read": module_read,
        "module_evidence": build_evidence(snapshot_sections["scenario_json"]),
        "transmission": build_transmission(config=config, chain=snapshot_sections["chain_json"]),
        "data_health": data_health,
        "provenance": build_provenance(
            snapshot=snapshot,
            observations=observations,
            facts_max_observed_at=facts_max_observed_at,
            projection_lag_days=projection_lag_days,
            projection_behind_facts=projection_behind_facts,
        ),
        "related_routes": related_routes(config),
    }
    if module_id == "assets":
        payload["daily_brief"] = dict(daily_brief) if isinstance(daily_brief, Mapping) else None
    return payload


def build_macro_module_views(
    *,
    snapshot: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    facts_max_observed_at, projection_lag_days, projection_behind_facts = _projection_currentness(snapshot)
    assets_brief = build_macro_assets_brief(snapshot=snapshot)
    observations_by_concept: dict[str, list[Mapping[str, Any]]] = {}
    for observation in observations:
        concept_key = str(observation.get("concept_key") or "")
        if concept_key:
            observations_by_concept.setdefault(concept_key, []).append(observation)
    views: dict[str, dict[str, Any]] = {}
    for module_id in MACRO_MODULE_IDS:
        config = get_macro_module_config(module_id)
        module_observations = [
            observation
            for concept_key in module_concepts(config)
            for observation in observations_by_concept.get(concept_key, ())
        ]
        views[module_id] = build_macro_module_view(
            module_id,
            snapshot=snapshot,
            observations=module_observations,
            daily_brief=assets_brief if module_id == "assets" else None,
            facts_max_observed_at=facts_max_observed_at,
            projection_lag_days=projection_lag_days,
            projection_behind_facts=projection_behind_facts,
        )
    return views


def _snapshot_sections(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "panels_json": required_mapping(snapshot, "panels_json"),
        "indicators_json": required_mapping(snapshot, "indicators_json"),
        "triggers_json": required_list(snapshot, "triggers_json"),
        "data_gaps_json": required_list(snapshot, "data_gaps_json"),
        "source_coverage_json": required_mapping(snapshot, "source_coverage_json"),
        "features_json": required_mapping(snapshot, "features_json"),
        "chain_json": required_mapping(snapshot, "chain_json"),
        "scenario_json": required_mapping(snapshot, "scenario_json"),
        "scorecard_json": required_mapping(snapshot, "scorecard_json"),
    }


def _snapshot_header(*, config: MacroModuleConfig, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    status = _required_text(snapshot, "status")
    asof_date = _required_date(snapshot, "asof_date")
    computed_at_ms = _required_int(snapshot, "computed_at_ms")
    return {
        "module_id": config.module_id,
        "route_path": config.route_path,
        "title": config.title,
        "subtitle": config.subtitle,
        "question": config.question,
        "section": config.section,
        "projection_version": MACRO_MODULE_VIEW_VERSION,
        "status": status,
        "status_label": status_label(status),
        "asof_date": asof_date,
        "asof_label": f"截至 {asof_date}",
        "computed_at_ms": computed_at_ms,
        "computed_at_label": (
            f"计算于 {datetime.fromtimestamp(computed_at_ms / 1000, tz=UTC).isoformat(timespec='minutes')}"
        ),
        "source_projection_version": _required_text(snapshot, "projection_version"),
    }


def _base_module_read(
    *,
    config: MacroModuleConfig,
    snapshot: Mapping[str, Any],
    data_health: Mapping[str, Any],
) -> dict[str, Any]:
    regime = _required_text(snapshot, "regime")
    scenario = required_mapping(snapshot, "scenario_json")
    confidence = scenario.get("confidence")
    confidence_label = f"置信度 {float(confidence):.0%}" if isinstance(confidence, int | float) else "置信度待补"
    return {
        "headline": f"{config.title}：{status_label(regime)}",
        "regime_label": status_label(regime),
        "confidence_label": confidence_label,
        "data_note": str(data_health.get("summary_label") or "数据状态未知"),
        "methodology_note": "仅使用 PostgreSQL 持久化观测与单写者 current projection。",
    }


def _domain_module_read(
    *,
    config: MacroModuleConfig,
    features: Mapping[str, Mapping[str, Any]],
    scenario: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    concept_keys = module_concepts(config)
    module_id = config.module_id
    if module_id == "overview":
        return build_overview_module_read(
            scenario=scenario,
            market_event_flow=official_event_flow(observations),
        )
    if module_id == "assets" or module_id.startswith("assets/"):
        return build_asset_module_read(module_id=module_id, concept_keys=concept_keys, features=features)
    if module_id.startswith("rates/"):
        return build_rates_module_read(module_id=module_id, concept_keys=concept_keys, features=features)
    if module_id.startswith("liquidity/"):
        return build_liquidity_module_read(concept_keys=concept_keys, features=features)
    if module_id.startswith("economy/"):
        return build_economy_module_read(module_id=module_id, concept_keys=concept_keys, features=features)
    return build_risk_module_read(module_id=module_id, concept_keys=concept_keys, features=features)


def _projection_currentness(snapshot: Mapping[str, Any]) -> tuple[object, int | None, bool]:
    source_coverage = required_mapping(snapshot, "source_coverage_json")
    facts_max_observed_at = source_coverage.get("latest_observed_at") or snapshot.get("asof_date")
    facts_date = _date_value(facts_max_observed_at)
    snapshot_date = _date_value(snapshot.get("asof_date"))
    if facts_date is None or snapshot_date is None:
        return facts_max_observed_at, None, facts_date is not None
    lag_days = max(0, (facts_date - snapshot_date).days)
    return facts_max_observed_at, lag_days, facts_date > snapshot_date


def _required_text(value: Mapping[str, Any], field_name: str) -> str:
    result = text(value.get(field_name))
    if result is None:
        raise ValueError(f"macro_view_snapshot_section_required:{field_name}")
    return result


def _required_date(value: Mapping[str, Any], field_name: str) -> str:
    resolved = _date_value(value.get(field_name))
    if resolved is None:
        raise ValueError(f"macro_view_snapshot_section_required:{field_name}")
    return resolved.isoformat()


def _required_int(value: Mapping[str, Any], field_name: str) -> int:
    field = value.get(field_name)
    if isinstance(field, bool) or not isinstance(field, int) or field < 0:
        raise ValueError(f"macro_view_snapshot_section_required:{field_name}")
    return field


def _date_value(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = text(value)
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


__all__ = ["build_macro_module_view", "build_macro_module_views"]
