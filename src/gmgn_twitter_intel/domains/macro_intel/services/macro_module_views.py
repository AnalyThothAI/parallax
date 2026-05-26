from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from gmgn_twitter_intel.domains.macro_intel._constants import (
    MACRO_CONCEPT_METADATA,
    MACRO_MIN_CHART_POINTS,
    MACRO_MODULE_VIEW_VERSION,
)
from gmgn_twitter_intel.domains.macro_intel.services.macro_gap_payloads import build_macro_data_gaps
from gmgn_twitter_intel.domains.macro_intel.services.macro_module_catalog import (
    MacroChartSpec,
    MacroModuleConfig,
    MacroTableSpec,
    get_macro_module_config,
)


def build_macro_module_view(
    module_id: str,
    snapshot: Mapping[str, Any] | None,
    observations: Sequence[Mapping[str, Any]],
    latest_import_run: Mapping[str, Any] | None,
    cex_board: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    config = get_macro_module_config(module_id)
    if snapshot is None:
        return _missing_view(config=config, latest_import_run=latest_import_run, cex_board=cex_board)

    feature_map = _mapping(snapshot.get("features_json"))
    concept_keys = _module_concept_keys(config)
    cex_source = _cex_source(cex_board) if config.module_id == "assets/crypto-derivatives" else None
    primary_chart = _primary_chart(config.chart_specs[0], feature_map) if config.chart_specs else _empty_chart()
    data_health = _data_health(
        config=config,
        snapshot=snapshot,
        feature_map=feature_map,
        concept_keys=concept_keys,
        primary_chart=primary_chart,
        cex_source=cex_source,
    )

    tables = [_table(spec, feature_map) for spec in config.table_specs if spec.table_id != "cex_perp_board"]
    if config.module_id == "assets/crypto-derivatives":
        tables.append(_cex_table(cex_board))
    tables.append(
        _availability_table(
            config=config,
            feature_map=feature_map,
            concept_keys=concept_keys,
            data_gaps=_availability_gaps(data_health),
        )
    )

    tiles = [_tile(concept_key, feature_map[concept_key]) for concept_key in concept_keys if concept_key in feature_map]
    return _ordered_payload(
        snapshot=_snapshot_header(config=config, snapshot=snapshot),
        tiles=tiles,
        primary_chart=primary_chart,
        tables=tables,
        module_read=_module_read(
            config=config,
            feature_map=feature_map,
            primary_chart=primary_chart,
            data_health=data_health,
            snapshot=snapshot,
        ),
        module_evidence=_module_evidence(
            config=config,
            feature_map=feature_map,
            primary_chart=primary_chart,
            data_health={**data_health, "_scenario": snapshot.get("scenario_json")},
            cex_source=cex_source,
        ),
        transmission=_transmission(config=config, snapshot=snapshot, feature_map=feature_map, data_health=data_health),
        data_health=data_health,
        provenance=_provenance(
            snapshot=snapshot,
            observations=observations,
            latest_import_run=latest_import_run,
            cex_source=cex_source,
        ),
        related_routes=_related_routes(config.related_routes),
        section_boards=_section_boards(config, feature_map),
    )


def _missing_view(
    config: MacroModuleConfig,
    latest_import_run: Mapping[str, Any] | None,
    cex_board: Mapping[str, Any] | None,
) -> dict[str, Any]:
    cex_source = _cex_source(cex_board) if config.module_id == "assets/crypto-derivatives" else None
    primary_chart = _missing_chart(config.chart_specs[0]) if config.chart_specs else _empty_chart()
    data_health = _data_health(
        config=config,
        snapshot={"data_gaps_json": build_macro_data_gaps(["macro_view_snapshot_missing"])},
        feature_map={},
        concept_keys=(),
        primary_chart=primary_chart,
        cex_source=cex_source,
    )
    return _ordered_payload(
        snapshot={
            "module_id": config.module_id,
            "route_path": config.route_path,
            "title": config.title,
            "subtitle": config.subtitle,
            "question": config.question,
            "section": config.section,
            "projection_version": MACRO_MODULE_VIEW_VERSION,
            "status": "missing",
            "status_label": _status_label("missing"),
            "asof_date": None,
            "asof_label": "截至 --",
            "computed_at_ms": None,
            "computed_at_label": "计算于 --",
            "source_snapshot_id": None,
            "source_projection_version": None,
        },
        tiles=[],
        primary_chart=primary_chart,
        tables=[
            _cex_table(cex_board) if spec.table_id == "cex_perp_board" else _missing_table(spec)
            for spec in config.table_specs
        ]
        + [
            _availability_table(
                config=config,
                feature_map={},
                concept_keys=_module_concept_keys(config),
                data_gaps=_availability_gaps(data_health),
            )
        ],
        module_read={
            "headline": f"{config.title}：缺少快照",
            "regime_label": "数据缺口",
            "confidence_label": "低置信度 0%",
            "data_note": "宏观快照缺失，页面只展示可用性和缺口。",
            "methodology_note": "运行 macro sync 回填历史并重新投影后恢复图表。",
        },
        module_evidence={"confirmations": [], "contradictions": [], "watch_triggers": [], "invalidations": []},
        transmission=_transmission(config=config, snapshot={}, feature_map={}, data_health=data_health),
        data_health=data_health,
        provenance=_provenance(
            snapshot={},
            observations=[],
            latest_import_run=latest_import_run,
            cex_source=cex_source,
        ),
        related_routes=_related_routes(config.related_routes),
        section_boards=[],
    )


def _ordered_payload(
    *,
    snapshot: dict[str, Any],
    tiles: list[dict[str, Any]],
    primary_chart: dict[str, Any],
    tables: list[dict[str, Any]],
    module_read: dict[str, Any],
    module_evidence: dict[str, Any],
    transmission: dict[str, Any],
    data_health: dict[str, Any],
    provenance: dict[str, Any],
    related_routes: list[dict[str, str]],
    section_boards: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "snapshot": snapshot,
        "tiles": tiles,
        "primary_chart": primary_chart,
        "tables": tables,
        "module_read": module_read,
        "module_evidence": module_evidence,
        "transmission": transmission,
        "data_health": data_health,
        "provenance": provenance,
        "related_routes": related_routes,
        "section_boards": section_boards,
    }


def _snapshot_header(config: MacroModuleConfig, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    status = str(snapshot.get("status") or "unknown")
    asof_date = snapshot.get("asof_date")
    computed_at_ms = snapshot.get("computed_at_ms")
    return {
        "module_id": config.module_id,
        "route_path": config.route_path,
        "title": config.title,
        "subtitle": config.subtitle,
        "question": config.question,
        "section": config.section,
        "projection_version": MACRO_MODULE_VIEW_VERSION,
        "status": status,
        "status_label": _status_label(status),
        "asof_date": asof_date,
        "asof_label": f"截至 {asof_date}" if asof_date else "截至 --",
        "computed_at_ms": computed_at_ms,
        "computed_at_label": _computed_at_label(computed_at_ms),
        "source_snapshot_id": snapshot.get("snapshot_id"),
        "source_projection_version": snapshot.get("projection_version"),
    }


def _tile(concept_key: str, feature: Mapping[str, Any]) -> dict[str, Any]:
    latest = _mapping(feature.get("latest"))
    source = _mapping(feature.get("source"))
    value = _number(latest.get("value"))
    delta_20d = _number(_mapping(feature.get("delta")).get("20d"))
    quality = str(feature.get("data_quality") or "unknown")
    return {
        "concept_key": concept_key,
        "label": _feature_label(concept_key, feature),
        "short_label": _feature_short_label(concept_key, feature),
        "description": _feature_description(concept_key, feature),
        "value": latest.get("value"),
        "display_value": _display_number(value),
        "unit": latest.get("unit"),
        "unit_label": _feature_unit_label(concept_key, feature, latest),
        "delta_label": _delta_label(delta_20d),
        "source_label": _source_label(source),
        "observed_at": latest.get("observed_at"),
        "observed_at_label": _observed_label(latest.get("observed_at")),
        "quality": quality,
        "quality_label": _quality_label(quality),
        "score_participation": bool(feature.get("score_participation")),
        "history_points": _int_or_none(feature.get("history_points")),
    }


def _primary_chart(spec: MacroChartSpec, feature_map: Mapping[str, Any]) -> dict[str, Any]:
    concept_keys = spec.concept_keys
    missing = [concept_key for concept_key in concept_keys if concept_key not in feature_map]
    series = [
        _chart_series(concept_key, feature_map[concept_key])
        for concept_key in concept_keys
        if concept_key in feature_map
    ]
    status = _chart_status(concept_keys=concept_keys, missing_concept_keys=missing, series=series)
    return {
        "id": spec.chart_id,
        "title": _chart_title(spec.chart_id),
        "subtitle": _chart_subtitle(status),
        "kind": "line",
        "status": status,
        "status_label": _status_label(status),
        "min_points": MACRO_MIN_CHART_POINTS,
        "missing_concept_keys": missing,
        "series": series,
    }


def _chart_series(concept_key: str, feature: Mapping[str, Any]) -> dict[str, Any]:
    history = _sequence(feature.get("history"))
    points = [
        {"observed_at": point.get("observed_at"), "value": point.get("value")}
        for point in history
        if isinstance(point, Mapping)
    ]
    latest = _mapping(feature.get("latest"))
    if not points and latest.get("value") is not None:
        points = [{"observed_at": latest.get("observed_at"), "value": latest.get("value")}]
    return {
        "concept_key": concept_key,
        "label": _feature_label(concept_key, feature),
        "short_label": _feature_short_label(concept_key, feature),
        "unit_label": _feature_unit_label(concept_key, feature, latest),
        "point_count": len(points),
        "status": "ok" if len(points) >= MACRO_MIN_CHART_POINTS else "insufficient_history",
        "points": points,
    }


def _table(spec: MacroTableSpec, feature_map: Mapping[str, Any]) -> dict[str, Any]:
    concept_keys = spec.concept_keys
    missing = [concept_key for concept_key in concept_keys if concept_key not in feature_map]
    rows = [
        _table_row(concept_key, feature_map[concept_key]) for concept_key in concept_keys if concept_key in feature_map
    ]
    return {
        "id": spec.table_id,
        "title": _table_title(spec.table_id),
        "status": _spec_status(concept_keys=concept_keys, missing_concept_keys=missing),
        "status_label": _status_label(_spec_status(concept_keys=concept_keys, missing_concept_keys=missing)),
        "columns": _STANDARD_COLUMNS,
        "missing_concept_keys": missing,
        "rows": rows,
    }


def _table_row(concept_key: str, feature: Mapping[str, Any]) -> dict[str, Any]:
    latest = _mapping(feature.get("latest"))
    source = _mapping(feature.get("source"))
    value = _number(latest.get("value"))
    delta_20d = _number(_mapping(feature.get("delta")).get("20d"))
    quality = str(feature.get("data_quality") or "unknown")
    return {
        "row_id": concept_key,
        "row_quality": quality,
        "source_state": {"label": _source_label(source), "status": quality},
        "cells": {
            "indicator": {
                "display_value": _feature_label(concept_key, feature),
                "sort_value": _feature_short_label(concept_key, feature),
            },
            "latest": {"display_value": _display_number(value), "sort_value": value},
            "delta_20d": {"display_value": _delta_label(delta_20d), "sort_value": delta_20d},
            "quality": {"display_value": _quality_label(quality), "sort_value": quality},
            "source": {"display_value": _source_label(source), "sort_value": _source_label(source)},
        },
    }


def _availability_table(
    *,
    config: MacroModuleConfig,
    feature_map: Mapping[str, Any],
    concept_keys: Sequence[str],
    data_gaps: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for concept_key in concept_keys:
        metadata = MACRO_CONCEPT_METADATA.get(concept_key, {})
        feature = _mapping(feature_map.get(concept_key))
        status = "ok" if feature else "missing"
        latest = _mapping(feature.get("latest"))
        source = _mapping(feature.get("source"))
        history_points = _int_or_none(feature.get("history_points"))
        required_points = _int_or_none(feature.get("required_history_points"))
        rows.append(
            {
                "row_id": f"concept:{concept_key}",
                "row_quality": status,
                "source_state": {"label": _source_label(source), "status": status},
                "cells": {
                    "item": {
                        "display_value": metadata.get("label") or concept_key,
                        "sort_value": metadata.get("short_label") or concept_key,
                    },
                    "status": {
                        "display_value": "已入库" if feature else "缺少观测",
                        "sort_value": status,
                    },
                    "latest": {
                        "display_value": _observed_label(latest.get("observed_at")) if feature else "观测于 --",
                        "sort_value": latest.get("observed_at"),
                    },
                    "coverage": {
                        "display_value": _history_coverage_label(history_points, required_points),
                        "sort_value": history_points,
                    },
                    "notes": {
                        "display_value": _availability_note(concept_key, feature),
                        "sort_value": concept_key,
                    },
                },
            }
        )
    for gap in data_gaps:
        code = str(gap.get("code") or "")
        if not code:
            continue
        rows.append(
            {
                "row_id": f"gap:{code}",
                "row_quality": str(gap.get("severity") or "warning"),
                "source_state": {"label": "数据可用性", "status": gap.get("severity")},
                "cells": {
                    "item": {"display_value": gap.get("label") or code, "sort_value": code},
                    "status": {"display_value": gap.get("severity") or "warning", "sort_value": gap.get("severity")},
                    "latest": {"display_value": "n/a", "sort_value": None},
                    "coverage": {"display_value": "计分排除", "sort_value": 0},
                    "notes": {
                        "display_value": gap.get("remediation_hint") or "补齐数据源后重新投影。",
                        "sort_value": gap.get("remediation_hint"),
                    },
                },
            }
        )
    if not rows:
        rows.append(
            {
                "row_id": f"{config.module_id}:available",
                "row_quality": "ok",
                "source_state": {"label": "数据可用性", "status": "ok"},
                "cells": {
                    "item": {"display_value": config.title, "sort_value": config.module_id},
                    "status": {"display_value": "无显式缺口", "sort_value": "ok"},
                    "latest": {"display_value": "n/a", "sort_value": None},
                    "coverage": {"display_value": "可用", "sort_value": 1},
                    "notes": {"display_value": "当前模块没有配置级缺口。", "sort_value": "ok"},
                },
            }
        )
    return {
        "id": "availability_proxy_notes",
        "title": "数据可用性 / 代理说明",
        "status": "ok" if not data_gaps else "partial",
        "status_label": "可用" if not data_gaps else "部分可用",
        "columns": [
            {"key": "item", "label": "项目"},
            {"key": "status", "label": "状态"},
            {"key": "latest", "label": "最新观测"},
            {"key": "coverage", "label": "历史覆盖"},
            {"key": "notes", "label": "说明"},
        ],
        "rows": rows,
    }


def _module_read(
    *,
    config: MacroModuleConfig,
    feature_map: Mapping[str, Any],
    primary_chart: Mapping[str, Any],
    data_health: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    if config.module_id == "overview":
        scenario = _mapping(snapshot.get("scenario_json"))
        regime = str(scenario.get("current_regime") or snapshot.get("regime") or "data_gap")
        confidence = _number(scenario.get("confidence")) or 0.0
        headline_label = _regime_label(regime)
        confidence_label = _confidence_label(confidence)
    else:
        status = str(data_health.get("summary_status") or primary_chart.get("status") or "unknown")
        headline_label = _status_label(status)
        present = len([concept_key for concept_key in _module_concept_keys(config) if concept_key in feature_map])
        total = len(_module_concept_keys(config))
        confidence_label = f"模块覆盖 {present}/{total}" if total else "模块覆盖 0/0"
    return {
        "headline": f"{config.title}：{headline_label}",
        "regime_label": headline_label,
        "confidence_label": confidence_label,
        "data_note": "本页只展示已入库的真实观测、规则状态和可用性说明。",
        "methodology_note": f"{config.title} 使用模块配置中的 required/optional 概念生成图表和表格。",
    }


def _module_evidence(
    *,
    config: MacroModuleConfig,
    feature_map: Mapping[str, Any],
    primary_chart: Mapping[str, Any],
    data_health: Mapping[str, Any],
    cex_source: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if config.module_id == "overview":
        scenario = _mapping(data_health.get("_scenario"))
        return {
            "confirmations": [_evidence_item(item) for item in _mapping_list(scenario.get("confirmations"))],
            "contradictions": [_evidence_item(item) for item in _mapping_list(scenario.get("contradictions"))],
            "watch_triggers": [_evidence_item(item) for item in _mapping_list(scenario.get("watch_triggers"))],
            "invalidations": [_evidence_item(item) for item in _mapping_list(scenario.get("invalidations"))],
        }

    confirmations = [
        {
            "code": f"module_concept_available:{concept_key}",
            "label": _feature_label(concept_key, _mapping(feature_map.get(concept_key))),
            "description": _availability_note(concept_key, _mapping(feature_map.get(concept_key))),
        }
        for concept_key in _module_concept_keys(config)
        if concept_key in feature_map
    ]
    missing_concepts = _string_list(primary_chart.get("missing_concept_keys"))
    contradictions = [
        {
            "code": f"module_concept_missing:{concept_key}",
            "label": MACRO_CONCEPT_METADATA.get(concept_key, {}).get("label") or concept_key,
            "description": "模块配置概念未在最新宏观投影中出现。",
        }
        for concept_key in missing_concepts
    ]
    watch_triggers = [
        {
            "code": f"module_gap:{gap.get('code')}",
            "label": str(gap.get("label") or gap.get("code") or "数据缺口"),
            "description": str(gap.get("remediation_hint") or "补齐数据源后重新投影。"),
        }
        for gap in _mapping_list(data_health.get("future_integration_gaps"))
    ]
    if cex_source is not None and cex_source.get("status") != "ok":
        watch_triggers.append(
            {
                "code": f"module_source:{cex_source.get('status')}",
                "label": "CEX OI Radar",
                "description": "CEX 合约杠杆板当前不可完整使用。",
            }
        )
    return {
        "confirmations": confirmations,
        "contradictions": contradictions,
        "watch_triggers": watch_triggers,
        "invalidations": [
            {
                "code": "module_chart_missing",
                "label": "主图缺失",
                "description": "主图核心序列全部缺失时，模块信号不可用。",
            }
        ]
        if primary_chart.get("status") == "missing"
        else [],
    }


def _evidence_item(item: Mapping[str, Any]) -> dict[str, Any]:
    code = str(item.get("code") or "")
    return {
        "code": code,
        "label": _code_label(code),
        "description": item.get("description") or "",
    }


def _provenance(
    *,
    snapshot: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    latest_import_run: Mapping[str, Any] | None,
    cex_source: Mapping[str, Any] | None,
) -> dict[str, Any]:
    rows = _observation_source_rows(observations)
    import_run = _latest_import_run(latest_import_run)
    import_status = _status_key(import_run["status"])
    rows.append(
        {
            "source": "宏观导入",
            "status": import_status,
            "status_label": _status_label(import_status),
            "latest_observed_at": None,
            "concept_count": None,
            "notes": "，".join(_localized_reason(reason) for reason in import_run["reason_codes"]),
        }
    )
    if cex_source is not None:
        cex_status = _status_key(cex_source["status"])
        rows.append(
            {
                "source": "CEX OI Radar",
                "status": cex_status,
                "status_label": _status_label(cex_status),
                "latest_observed_at": None,
                "concept_count": cex_source.get("row_count"),
                "notes": "，".join(_localized_reason(reason) for reason in cex_source["degraded_reasons"]),
            }
        )
    return {
        "projection_version": snapshot.get("projection_version"),
        "source_snapshot_id": snapshot.get("snapshot_id"),
        "rows": rows,
    }


def _observation_source_rows(observations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_source: dict[str, dict[str, Any]] = {}
    for observation in observations:
        source = str(observation.get("source_name") or "").strip()
        if not source:
            continue
        row = by_source.setdefault(
            source,
            {"source": source, "status": "ok", "latest_observed_at": None, "concepts": set[str](), "notes": ""},
        )
        row["concepts"].add(str(observation.get("concept_key") or ""))
        observed_at = observation.get("observed_at")
        if observed_at and (row["latest_observed_at"] is None or str(observed_at) > str(row["latest_observed_at"])):
            row["latest_observed_at"] = observed_at
        quality = _status_key(observation.get("data_quality") or "ok")
        if quality != "ok":
            row["status"] = quality
    return [
        {
            "source": _provider_label(source),
            "status": row["status"],
            "status_label": _status_label(row["status"]),
            "latest_observed_at": row["latest_observed_at"],
            "concept_count": len(row["concepts"]),
            "notes": row["notes"],
        }
        for source, row in sorted(by_source.items())
    ]


def _cex_table(cex_board: Mapping[str, Any] | None) -> dict[str, Any]:
    source = _cex_source(cex_board)
    rows = [_cex_row(row, source=source) for row in _mapping_list(_mapping(cex_board).get("rows"))]
    if not rows:
        rows = [_missing_cex_row(source["degraded_reasons"][0])]
    status = "missing" if rows[0]["row_quality"] == "missing" else source["status"]
    return {
        "id": "cex_perp_board",
        "title": "CEX 合约杠杆板",
        "status": status,
        "status_label": _status_label(status),
        "columns": [
            {"key": "symbol", "label": "合约"},
            {"key": "open_interest", "label": "未平仓"},
            {"key": "funding", "label": "资金费率"},
            {"key": "volume_24h", "label": "24h 成交"},
            {"key": "score", "label": "分数"},
        ],
        "rows": rows,
    }


def _cex_source(cex_board: Mapping[str, Any] | None) -> dict[str, Any]:
    if cex_board is None:
        return {"status": "missing", "degraded_reasons": ["cex_board_missing"], "row_count": 0}
    rows = _mapping_list(cex_board.get("rows"))
    reasons = _string_list(cex_board.get("degraded_reasons"))
    if not rows:
        reasons = _unique([*reasons, "cex_board_empty"])
    return {
        "status": _normalize_cex_status(cex_board.get("status"), has_rows=bool(rows)),
        "degraded_reasons": reasons,
        "row_count": len(rows),
    }


def _cex_row(row: Mapping[str, Any], *, source: Mapping[str, Any]) -> dict[str, Any]:
    symbol = _first_non_none(row, ("symbol", "base_symbol", "native_market_id")) or "--"
    row_id = str(_first_non_none(row, ("native_market_id", "symbol", "base_symbol")) or symbol)
    oi = _number(_first_non_none(row, ("open_interest_usd", "oi_usd")))
    funding = _number(_first_non_none(row, ("funding_rate", "funding_rate_pct")))
    volume = _number(_first_non_none(row, ("volume_24h_usd", "volume_usd")))
    score = _number(row.get("score"))
    quality = str(source.get("status") or "unknown")
    return {
        "row_id": row_id,
        "row_quality": quality,
        "source_state": {"label": "CEX OI Radar", "status": source.get("status")},
        "cells": {
            "symbol": {"display_value": str(symbol), "sort_value": str(symbol)},
            "open_interest": {"display_value": _compact_usd(oi), "sort_value": oi},
            "funding": {"display_value": _pct_value(funding), "sort_value": funding},
            "volume_24h": {"display_value": _compact_usd(volume), "sort_value": volume},
            "score": {"display_value": _display_number(score), "sort_value": score},
        },
    }


def _missing_cex_row(reason: str) -> dict[str, Any]:
    return {
        "row_id": reason,
        "row_quality": "missing",
        "source_state": {"label": "CEX OI Radar", "status": "missing"},
        "cells": {
            "symbol": {"display_value": "CEX 数据不可用", "sort_value": None},
            "open_interest": {"display_value": "缺失", "sort_value": None},
            "funding": {"display_value": "缺失", "sort_value": None},
            "volume_24h": {"display_value": "缺失", "sort_value": None},
            "score": {"display_value": "缺失", "sort_value": None},
        },
    }


def _data_health(
    *,
    config: MacroModuleConfig,
    snapshot: Mapping[str, Any],
    feature_map: Mapping[str, Any],
    concept_keys: Sequence[str],
    primary_chart: Mapping[str, Any],
    cex_source: Mapping[str, Any] | None,
) -> dict[str, Any]:
    global_gaps = [_gap_payload(gap) for gap in _sequence(snapshot.get("data_gaps_json"))]
    global_scope = "global_blocker" if config.module_id == "overview" else "global_reference"
    global_gaps = [_with_scope(gap, global_scope) for gap in global_gaps]

    module_gaps: list[dict[str, Any]] = []
    if any(gap.get("code") == "macro_view_snapshot_missing" for gap in global_gaps):
        module_gaps.extend(_with_scope(gap, "module_blocker") for gap in global_gaps)
    for concept_key in concept_keys:
        feature = feature_map.get(concept_key)
        if isinstance(feature, Mapping):
            module_gaps.extend(
                _with_scope(_gap_payload(gap), "module_blocker") for gap in _sequence(feature.get("data_gaps"))
            )
    config_gaps = [_gap_payload(gap) for gap in build_macro_data_gaps(config.gap_codes)]
    if any(gap.get("code") == "macro_view_snapshot_missing" for gap in global_gaps):
        module_gaps.extend(_with_scope(gap, "module_blocker") for gap in config_gaps)
        future_integration_gaps = []
    else:
        future_integration_gaps = [_with_scope(gap, "future_integration") for gap in config_gaps]
    if cex_source is not None:
        module_gaps.extend(
            _with_scope(_gap_payload(gap), "module_blocker")
            for gap in build_macro_data_gaps(cex_source["degraded_reasons"])
        )

    chart_gaps = [
        _with_scope(
            _gap_payload(
                {
                    "code": f"chart_missing:{concept_key}",
                    "label": f"主图缺少序列：{_concept_short_label(concept_key)}",
                    "severity": "warning",
                    "concept_key": concept_key,
                }
            ),
            "chart_blocker",
        )
        for concept_key in _string_list(primary_chart.get("missing_concept_keys"))
    ]
    status = _data_health_status(
        module_gaps=module_gaps,
        chart_gaps=chart_gaps,
        primary_chart=primary_chart,
        feature_map=feature_map,
        concept_keys=concept_keys,
    )
    return {
        "summary_status": status,
        "module_gaps": _unique_gaps(module_gaps),
        "chart_gaps": _unique_gaps(chart_gaps),
        "global_gaps": _unique_gaps(global_gaps),
        "future_integration_gaps": _unique_gaps(future_integration_gaps),
    }


def _availability_gaps(data_health: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        *_mapping_list(data_health.get("module_gaps")),
        *_mapping_list(data_health.get("chart_gaps")),
        *_mapping_list(data_health.get("future_integration_gaps")),
    ]


def _unique_gaps(gaps: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for gap in gaps:
        code = str(gap.get("code") or "")
        if code and code not in unique:
            unique[code] = dict(gap)
    return list(unique.values())


def _with_scope(gap: Mapping[str, Any], scope: str) -> dict[str, Any]:
    payload = dict(gap)
    payload["scope"] = scope
    return payload


def _data_health_status(
    *,
    module_gaps: Sequence[Mapping[str, Any]],
    chart_gaps: Sequence[Mapping[str, Any]],
    primary_chart: Mapping[str, Any],
    feature_map: Mapping[str, Any],
    concept_keys: Sequence[str],
) -> str:
    if any(gap.get("severity") == "error" for gap in module_gaps):
        return "missing"
    chart_status = str(primary_chart.get("status") or "unknown")
    if chart_status == "missing" or (
        concept_keys and not any(concept_key in feature_map for concept_key in concept_keys)
    ):
        return "missing"
    if module_gaps or chart_gaps or chart_status in {"partial", "insufficient_history"}:
        return "partial"
    return "ok"


def _transmission(
    *,
    config: MacroModuleConfig,
    snapshot: Mapping[str, Any],
    feature_map: Mapping[str, Any],
    data_health: Mapping[str, Any],
) -> dict[str, Any]:
    if config.module_id == "overview":
        chain = _mapping(snapshot.get("chain_json"))
        nodes = [
            {
                "id": f"global:{key}",
                "label": _section_label(key),
                "value": _regime_label(str(_mapping(value).get("regime") or "data_gap")),
                "kind": "signal",
                "status": "ok" if _mapping(value).get("regime") not in {None, "data_gap"} else "missing",
            }
            for key, value in chain.items()
            if isinstance(value, Mapping)
        ]
        if not nodes:
            nodes = [
                {
                    "id": "global:data_health",
                    "label": "全局数据健康",
                    "value": _status_label(data_health.get("summary_status")),
                    "kind": "risk",
                    "status": str(data_health.get("summary_status") or "unknown"),
                }
            ]
        return {"nodes": nodes}

    first_concept = next(
        (concept_key for concept_key in _module_concept_keys(config) if concept_key in feature_map), None
    )
    source_status = "ok" if first_concept else "missing"
    source_value = (
        _feature_short_label(first_concept, _mapping(feature_map.get(first_concept))) if first_concept else "缺少观测"
    )
    return {
        "nodes": [
            {
                "id": f"{config.module_id}:source",
                "label": "模块观测",
                "value": source_value,
                "kind": "source",
                "status": source_status,
            },
            {
                "id": f"{config.module_id}:signal",
                "label": config.title,
                "value": _status_label(data_health.get("summary_status")),
                "kind": "signal",
                "status": str(data_health.get("summary_status") or "unknown"),
            },
            {
                "id": f"{config.module_id}:implication",
                "label": "宏观含义",
                "value": config.question,
                "kind": "implication",
                "status": str(data_health.get("summary_status") or "unknown"),
            },
        ]
    }


def _section_boards(config: MacroModuleConfig, feature_map: Mapping[str, Any]) -> list[dict[str, Any]]:
    boards: list[dict[str, Any]] = []
    for spec in config.section_board_specs:
        rows = []
        for concept_key in spec.concept_keys:
            feature = _mapping(feature_map.get(concept_key))
            row = _section_board_row(concept_key, feature)
            rows.append(row)
        boards.append(
            {
                "board_id": spec.board_id,
                "title": spec.title,
                "route_path": spec.route_path,
                "concept_keys": list(spec.concept_keys),
                "status": "ok" if all(row["status"] == "ok" for row in rows) else "partial" if rows else "missing",
                "rows": rows,
            }
        )
    return boards


def _section_board_row(concept_key: str, feature: Mapping[str, Any]) -> dict[str, Any]:
    latest = _mapping(feature.get("latest"))
    source = _mapping(feature.get("source"))
    value = _number(latest.get("value"))
    delta_20d = _number(_mapping(feature.get("delta")).get("20d"))
    return {
        "concept_key": concept_key,
        "label": _feature_label(concept_key, feature),
        "short_label": _feature_short_label(concept_key, feature),
        "status": "ok" if feature else "missing",
        "display_value": _display_number(value),
        "delta_label": _delta_label(delta_20d),
        "observed_at_label": _observed_label(latest.get("observed_at")),
        "source_label": _source_label(source),
    }


def _section_label(section: str) -> str:
    return {
        "assets": "资产联动",
        "credit": "信用压力",
        "economy": "经济数据",
        "fed": "美联储",
        "liquidity": "美元流动性",
        "rates": "利率定价",
        "volatility": "波动率",
    }.get(section, section)


def _concept_short_label(concept_key: str) -> str:
    return str(MACRO_CONCEPT_METADATA.get(concept_key, {}).get("short_label") or concept_key)


def _gap_payload(value: object) -> dict[str, Any]:
    payload = dict(value) if isinstance(value, Mapping) else build_macro_data_gaps([str(value)])[0]
    payload.setdefault("severity", "warning")
    payload.setdefault("score_participation", False)
    payload.setdefault("owner", "macro_intel")
    payload.setdefault("score_impact", "excluded")
    payload.setdefault("remediation_hint", _remediation_hint(str(payload.get("code") or "")))
    return payload


def _missing_chart(spec: MacroChartSpec) -> dict[str, Any]:
    return {
        "id": spec.chart_id,
        "title": _chart_title(spec.chart_id),
        "subtitle": "缺少宏观快照",
        "kind": "line",
        "status": "missing",
        "status_label": _status_label("missing"),
        "min_points": MACRO_MIN_CHART_POINTS,
        "missing_concept_keys": list(spec.concept_keys),
        "series": [],
    }


def _empty_chart() -> dict[str, Any]:
    return {
        "id": None,
        "title": "",
        "subtitle": "",
        "kind": "line",
        "status": "missing",
        "status_label": _status_label("missing"),
        "min_points": MACRO_MIN_CHART_POINTS,
        "missing_concept_keys": [],
        "series": [],
    }


def _missing_table(spec: MacroTableSpec) -> dict[str, Any]:
    return {
        "id": spec.table_id,
        "title": _table_title(spec.table_id),
        "status": "missing",
        "status_label": _status_label("missing"),
        "columns": _STANDARD_COLUMNS,
        "missing_concept_keys": list(spec.concept_keys),
        "rows": [],
    }


def _module_concept_keys(config: MacroModuleConfig) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*config.required_concepts, *config.optional_concepts)))


def _chart_status(
    *,
    concept_keys: tuple[str, ...],
    missing_concept_keys: list[str],
    series: Sequence[Mapping[str, Any]],
) -> str:
    if not concept_keys or len(missing_concept_keys) == len(concept_keys):
        return "missing"
    if missing_concept_keys:
        return "partial"
    if any((_int_or_none(item.get("point_count")) or 0) < MACRO_MIN_CHART_POINTS for item in series):
        return "insufficient_history"
    return "ok"


def _spec_status(*, concept_keys: tuple[str, ...], missing_concept_keys: list[str]) -> str:
    if not concept_keys:
        return "static"
    if len(missing_concept_keys) == len(concept_keys):
        return "missing"
    if missing_concept_keys:
        return "partial"
    return "ok"


def _feature_label(concept_key: str, feature: Mapping[str, Any]) -> str:
    metadata = MACRO_CONCEPT_METADATA.get(concept_key, {})
    return str(feature.get("label") or metadata.get("label") or feature.get("short_label") or "未命名指标")


def _feature_short_label(concept_key: str, feature: Mapping[str, Any]) -> str:
    metadata = MACRO_CONCEPT_METADATA.get(concept_key, {})
    return str(feature.get("short_label") or metadata.get("short_label") or _feature_label(concept_key, feature))


def _feature_description(concept_key: str, feature: Mapping[str, Any]) -> str:
    metadata = MACRO_CONCEPT_METADATA.get(concept_key, {})
    return str(feature.get("description") or metadata.get("description") or "")


def _feature_unit_label(concept_key: str, feature: Mapping[str, Any], latest: Mapping[str, Any]) -> str:
    metadata = MACRO_CONCEPT_METADATA.get(concept_key, {})
    return str(feature.get("unit_label") or metadata.get("unit_label") or "单位未标注")


def _source_label(source: Mapping[str, Any]) -> str:
    return _provider_label(str(source.get("name") or ""))


def _provider_label(value: str) -> str:
    return {
        "coinglass": "Coinglass",
        "cftc": "CFTC",
        "fred": "FRED",
        "macro_import": "宏观导入",
        "nyfed": "NY Fed",
        "treasury_fiscal": "US Treasury",
        "yahoo": "Yahoo",
    }.get(value.strip().lower(), "未知来源")


_STATUS_LABELS = {
    "ok": "可用",
    "ready": "可用",
    "partial": "部分可用",
    "missing": "缺失",
    "stale": "过期",
    "degraded": "降级",
    "insufficient_history": "历史不足",
    "static": "静态",
    "unknown": "未知",
}


def _status_label(status: object) -> str:
    return _STATUS_LABELS.get(_status_key(status), "未知")


def _status_key(status: object) -> str:
    status_key = str(status or "unknown")
    return status_key if status_key in _STATUS_LABELS else "unknown"


def _quality_label(quality: str) -> str:
    return {"ok": "可用", "missing": "缺失", "degraded": "降级", "partial": "部分可用"}.get(quality, "未知")


def _regime_label(regime: str) -> str:
    return {
        "data_gap": "数据缺口",
        "funding_stress": "融资压力",
        "credit_stress": "信用压力",
        "term_premium_pressure": "期限溢价压力",
        "tightening": "紧缩压力",
        "risk_on_liquidity": "流动性 risk-on",
        "reflation": "再通胀",
        "neutral": "中性",
    }.get(regime, "未知宏观状态")


def _confidence_label(confidence: float) -> str:
    bucket = "高置信度" if confidence >= 0.75 else "中等置信度" if confidence >= 0.45 else "低置信度"
    return f"{bucket} {confidence:.0%}"


def _crypto_read(regime: str) -> str:
    if regime in {"funding_stress", "credit_stress", "tightening", "term_premium_pressure"}:
        return "宏观链条偏紧，加密 beta 需要等待流动性或信用确认。"
    if regime == "risk_on_liquidity":
        return "流动性链条支持风险资产，BTC/ETH 可作为宏观 beta 确认。"
    return "宏观读数中性，优先观察 BTC/ETH 是否自行突破。"


def _token_impact(regime: str) -> str:
    if regime in {"funding_stress", "credit_stress", "tightening", "term_premium_pressure"}:
        return "优先降低高 beta 山寨暴露，等待 BTC/ETH 与信用压力背离修复。"
    if regime == "risk_on_liquidity":
        return "可提高流动性敏感 token 观察权重，但需用衍生品杠杆确认。"
    return "维持选择性暴露，避免把单币种叙事误读成宏观确认。"


def _code_label(code: str) -> str:
    return {
        "breakevens_accelerate": "通胀补偿加速",
        "credit_spreads_benign": "信用利差温和",
        "credit_spreads_normalize": "信用利差正常化",
        "credit_stress": "信用压力",
        "cross_asset_risk_off": "跨资产 risk-off 确认",
        "deep_curve_inversion": "曲线深度倒挂",
        "fed_corridor_pressure": "政策走廊压力",
        "hyg_underperforms_lqd": "HYG 跑输 LQD",
        "hy_oas_distress": "高收益债利差进入困境区",
        "hy_oas_stress": "高收益债利差压力",
        "term_premium_pressure": "期限溢价压力",
        "higher_real_rates": "实际利率上行",
        "liquidity_easing": "流动性宽松",
        "liquidity_impulse_fades": "流动性脉冲减弱",
        "liquidity_impulse_persists": "流动性脉冲延续",
        "liquidity_tightening": "流动性收紧",
        "liquidity_tightens": "流动性转紧",
        "macro_core_coverage_recovers": "宏观核心覆盖恢复",
        "macro_regime_breakout": "宏观状态突破",
        "positioning_extreme": "仓位极端",
        "rates_pressure": "利率压力",
        "real_yield_breakout": "实际利率突破",
        "real_yield_recedes": "实际利率回落",
        "repo_pressure_persists_3d": "回购压力持续三日",
        "repo_corridor_pressure": "回购走廊压力",
        "risk_asset_confirmation_missing": "风险资产确认缺失",
        "risk_assets_confirm_risk_on": "风险资产确认 risk-on",
        "rrp_buffer_low": "RRP 缓冲偏低",
        "sofr_above_iorb": "SOFR 高于 IORB",
        "sofr_iorb_normalizes": "SOFR/IORB 回归正常",
        "ten_year_yield_reverses": "10年期收益率回落",
        "tga_high": "TGA 偏高",
        "vix_breaks_30": "VIX 突破 30",
        "vix_elevated": "VIX 偏高",
        "vix_reprices_higher": "VIX 重新上行定价",
        "vix_returns_to_carry": "VIX 回到 carry 区间",
        "volatility_carry": "波动率 carry",
        "volatility_panic": "波动率恐慌",
        "volatility_stress": "波动率压力",
        "volatility_unconcerned": "波动率未确认压力",
    }.get(code, "待确认信号")


def _related_routes(routes: Sequence[str]) -> list[dict[str, str]]:
    return [{"href": route, "label": _ROUTE_LABELS.get(route, route)} for route in routes]


def _localized_reason(reason: str) -> str:
    return {
        "cex_board_empty": "CEX 合约板为空",
        "cex_board_missing": "CEX 合约板缺失",
        "coinglass_partial": "Coinglass 数据不完整",
        "fred_key_missing": "FRED 凭证缺失",
        "missing_api_key": "导入配置缺失",
    }.get(reason, "数据源降级")


def _computed_at_label(value: object) -> str:
    timestamp_ms = _int_or_none(value)
    if timestamp_ms is None:
        return "计算于 --"
    return "计算于 " + datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")


def _observed_label(value: object) -> str:
    return f"观测于 {value}" if value else "观测于 --"


def _delta_label(value: float | None) -> str:
    return "20日变化不可用" if value is None else f"{value:+.2f}"


def _display_number(value: float | None) -> str:
    return "缺失" if value is None else f"{value:.2f}"


def _history_coverage_label(points: int | None, required_points: int | None) -> str:
    if points is None:
        return "历史缺失"
    if required_points is None:
        return f"{points} 点"
    return f"{points}/{required_points} 点"


def _availability_note(concept_key: str, feature: Mapping[str, Any]) -> str:
    if not feature:
        return "未在最新宏观投影中出现；检查 macrodata bundle 和 importer 映射。"
    source = _mapping(feature.get("source"))
    source_name = _source_label(source)
    metadata = MACRO_CONCEPT_METADATA.get(concept_key, {})
    description = str(metadata.get("description") or "").strip()
    return f"{source_name}；{description}" if description else source_name


def _pct_value(value: float | None) -> str:
    return "缺失" if value is None else f"{value:.4%}"


def _compact_usd(value: float | None) -> str:
    if value is None:
        return "缺失"
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    return f"{value:.2f}"


def _remediation_hint(code: str) -> str:
    if code.startswith("insufficient_history"):
        return "回填历史后重新生成宏观投影。"
    if code.startswith("missing"):
        return "检查对应 provider 导入与最新观测。"
    if code.startswith("cex_board"):
        return "启用或修复 cex_oi_radar_board worker。"
    return "补齐数据源后重新投影。"


def _latest_import_run(latest_import_run: Mapping[str, Any] | None) -> dict[str, Any]:
    if latest_import_run is None:
        return {"run_id": None, "status": None, "reason_codes": []}
    reason_codes = latest_import_run.get("reason_codes")
    if reason_codes is None:
        reason_codes = latest_import_run.get("reason_codes_json")
    return {
        "run_id": latest_import_run.get("run_id"),
        "status": latest_import_run.get("status"),
        "reason_codes": _string_list(reason_codes),
    }


def _chart_title(chart_id: str) -> str:
    return _CHART_TITLES.get(chart_id, "宏观图表")


def _chart_subtitle(status: str) -> str:
    if status == "insufficient_history":
        return "历史样本不足，暂不渲染趋势判断"
    if status == "partial":
        return "部分序列缺失，仅展示可用指标"
    return "核心序列走势"


def _table_title(table_id: str) -> str:
    return _TABLE_TITLES.get(table_id, "宏观表格")


def _normalize_cex_status(status: object, *, has_rows: bool) -> str:
    status_key = str(status or "").strip().lower()
    if not has_rows:
        return "missing"
    if status_key in {"ok", "ready", "success"}:
        return "ok"
    if status_key in {"partial", "degraded"}:
        return status_key
    if status_key in {"missing", "empty"}:
        return "missing"
    return "unknown"


def _first_non_none(row: Mapping[str, Any], aliases: Sequence[str]) -> Any | None:
    for alias in aliases:
        value = row.get(alias)
        if value is not None:
            return value
    return None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return list(value)
    return []


def _mapping_list(value: object) -> list[Mapping[str, Any]]:
    return [item for item in _sequence(value) if isinstance(item, Mapping)]


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Sequence):
        return [str(item) for item in value if item]
    return [str(value)]


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, int | float | str | Decimal):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, int | float | str | Decimal):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_STANDARD_COLUMNS = [
    {"key": "indicator", "label": "指标"},
    {"key": "latest", "label": "最新值"},
    {"key": "delta_20d", "label": "20日变化"},
    {"key": "quality", "label": "质量"},
    {"key": "source", "label": "来源"},
]

_ROUTE_LABELS = {
    "/macro/assets": "资产联动",
    "/macro/assets/equities": "美股风险",
    "/macro/assets/bonds": "债券资产",
    "/macro/assets/commodities": "商品冲击",
    "/macro/assets/fx": "美元压力",
    "/macro/assets/crypto": "加密资产",
    "/macro/assets/crypto-derivatives": "加密衍生品",
    "/macro/rates": "利率定价",
    "/macro/rates/fed-funds": "联邦基金",
    "/macro/rates/yield-curve": "收益率曲线",
    "/macro/rates/auctions": "国债拍卖",
    "/macro/rates/real-rates": "实际利率",
    "/macro/rates/expectations": "政策预期",
    "/macro/fed": "美联储走廊",
    "/macro/fed/statements": "FOMC 声明",
    "/macro/fed/speeches": "美联储讲话",
    "/macro/liquidity": "美元流动性",
    "/macro/liquidity/transmission-chain": "流动性传导链",
    "/macro/liquidity/fed-balance-sheet": "资产负债表",
    "/macro/liquidity/operations": "公开市场操作",
    "/macro/liquidity/rrp-tga": "RRP / TGA",
    "/macro/liquidity/reserves": "银行准备金",
    "/macro/liquidity/global-dollar": "全球美元",
    "/macro/liquidity/subsurface": "资金面暗流",
    "/macro/economy": "经济数据",
    "/macro/economy/gdp": "GDP",
    "/macro/economy/employment": "就业",
    "/macro/economy/inflation": "通胀",
    "/macro/economy/consumer": "消费",
    "/macro/volatility": "波动率压力",
    "/macro/volatility/dashboard": "波动率 Dashboard",
    "/macro/volatility/vix": "VIX 结构",
    "/macro/credit": "信用压力",
    "/macro/credit/cds": "CDS 代理",
    "/macro/credit/stress": "信用压力分解",
}

_CHART_TITLES = {
    "rates_curve": "收益率曲线",
    "asset_proxy_performance": "资产代理走势",
    "macro_regime": "宏观链条走势",
    "bond_proxy_performance": "债券代理走势",
    "commodity_proxy_performance": "商品代理走势",
    "credit_spreads": "信用利差走势",
    "credit_stress_stack": "信用压力堆栈",
    "cds_public_proxy": "CDS 公共代理走势",
    "auction_curve_proxy": "拍卖供给曲线代理",
    "consumer_dashboard": "消费与信心走势",
    "crypto_derivative_context": "加密衍生品背景",
    "crypto_proxy_performance": "加密资产走势",
    "economy_four_pillar": "经济四象限走势",
    "equity_proxy_performance": "美股代理走势",
    "employment_dashboard": "就业市场走势",
    "fed_corridor": "美联储政策走廊",
    "fed_funds_corridor": "联邦基金走廊",
    "fed_statement_policy_proxy": "FOMC 文本政策代理",
    "fed_speeches_market_proxy": "讲话市场代理",
    "fed_balance_sheet": "美联储资产负债表",
    "fx_proxy_performance": "美元代理走势",
    "global_dollar_pressure": "全球美元压力",
    "inflation_dashboard": "通胀数据走势",
    "liquidity_stack": "美元流动性堆栈",
    "nyfed_operations": "NY Fed 操作量",
    "policy_expectations_proxy": "政策预期代理",
    "real_gdp_history": "实际 GDP 历史",
    "real_rates": "实际利率走势",
    "reserve_balances": "银行准备金走势",
    "rrp_tga_stack": "RRP / TGA 堆栈",
    "subsurface_funding": "资金面暗流",
    "transmission_chain": "流动性传导链",
    "volatility_context": "波动率背景",
    "volatility_risk_matrix": "波动率风险矩阵",
    "vix_term_proxy": "VIX 期限代理",
    "yield_curve": "收益率曲线",
}

_TABLE_TITLES = {
    "rates_snapshot": "利率快照",
    "asset_proxy_snapshot": "资产快照",
    "panel_scorecard": "面板记分卡",
    "bond_proxy_snapshot": "债券资产快照",
    "cex_perp_board": "CEX 合约杠杆板",
    "commodity_proxy_snapshot": "商品资产快照",
    "credit_snapshot": "信用压力快照",
    "credit_oas_ladder": "OAS 分层表",
    "credit_stress_table": "信用压力表",
    "cds_proxy_table": "CDS 公共代理表",
    "auction_rate_proxy_table": "拍卖曲线代理表",
    "availability_proxy_notes": "数据可用性 / 代理说明",
    "consumer_table": "消费数据表",
    "crypto_proxy_snapshot": "加密资产快照",
    "curve_spreads": "曲线利差快照",
    "economy_four_pillar_table": "经济四象限表",
    "equity_proxy_snapshot": "美股资产快照",
    "employment_table": "就业数据表",
    "fed_corridor_snapshot": "政策走廊快照",
    "fed_funds_snapshot": "联邦基金快照",
    "fed_statement_proxy_table": "FOMC 文本代理表",
    "fed_speeches_proxy_table": "美联储讲话代理表",
    "fed_balance_sheet_table": "资产负债表",
    "fx_proxy_snapshot": "美元压力快照",
    "global_dollar_table": "全球美元表",
    "inflation_table": "通胀数据表",
    "liquidity_snapshot": "流动性快照",
    "nyfed_operations_table": "公开市场操作表",
    "policy_expectations_table": "政策预期表",
    "real_gdp_table": "GDP 数据表",
    "real_rates_snapshot": "实际利率快照",
    "reserve_balances_table": "准备金表",
    "rrp_tga_table": "RRP / TGA 表",
    "subsurface_funding_table": "资金面暗流表",
    "transmission_nodes": "传导节点快照",
    "volatility_risk_table": "波动率风险表",
    "volatility_snapshot": "波动率快照",
    "vix_term_proxy_table": "VIX 期限代理表",
}


__all__ = ["build_macro_module_view"]
