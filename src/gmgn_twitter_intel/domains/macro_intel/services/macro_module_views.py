from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from gmgn_twitter_intel.domains.macro_intel._constants import MACRO_MODULE_VIEW_VERSION
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
        return _missing_view(config=config, latest_import_run=latest_import_run)

    feature_map = _mapping(snapshot.get("features_json"))
    concept_keys = _module_concept_keys(config)
    tiles = [_tile(concept_key, feature_map[concept_key]) for concept_key in concept_keys if concept_key in feature_map]
    charts = [_chart(spec, feature_map) for spec in config.chart_specs]
    if config.module_id == "assets/crypto-derivatives":
        tables = [_table(spec, feature_map) for spec in config.table_specs if spec.table_id != "cex_perp_board"]
        tables = [*tables, _cex_board_table(cex_board)]
    else:
        tables = [_table(spec, feature_map) for spec in config.table_specs]

    gaps = _data_gaps(config=config, snapshot=snapshot)
    import_run = _latest_import_run(latest_import_run)
    provenance = {
        "latest_import_run": import_run,
        "source_coverage": _mapping(snapshot.get("source_coverage_json")),
        "observation_sources": _observation_sources(observations),
        "degradation": {
            "status": str(snapshot.get("status") or "unknown"),
            "reason_codes": list(import_run["reason_codes"]),
        },
    }
    if config.module_id == "assets/crypto-derivatives":
        provenance["cex_board"] = _cex_board_source(cex_board)

    return _ordered_payload(
        snapshot=_snapshot_header(config=config, snapshot=snapshot),
        tiles=tiles,
        charts=charts,
        tables=tables,
        current_read=_current_read(config=config, snapshot=snapshot),
        signals=_signals(snapshot),
        provenance=provenance,
        data_gaps=gaps,
        related_routes=list(config.related_routes),
    )


def _missing_view(config: MacroModuleConfig, latest_import_run: Mapping[str, Any] | None) -> dict[str, Any]:
    reason_codes = ["macro_view_snapshot_missing"]
    gaps = _unique([*reason_codes, *config.gap_codes])
    import_run = _latest_import_run(latest_import_run)
    return _ordered_payload(
        snapshot={
            "module_id": config.module_id,
            "route_path": config.route_path,
            "title": config.title,
            "section": config.section,
            "projection_version": MACRO_MODULE_VIEW_VERSION,
            "status": "missing",
            "asof_date": None,
            "source_snapshot_id": None,
            "source_projection_version": None,
            "computed_at_ms": None,
        },
        tiles=[],
        charts=[_missing_chart(spec) for spec in config.chart_specs],
        tables=[_missing_table(spec) for spec in config.table_specs],
        current_read={"regime": "data_gap", "current_regime": "data_gap", "summary": None, "trade_map": {}},
        signals=[],
        provenance={
            "latest_import_run": import_run,
            "source_coverage": {},
            "observation_sources": [],
            "degradation": {"status": "missing", "reason_codes": reason_codes},
        },
        data_gaps=gaps,
        related_routes=list(config.related_routes),
    )


def _ordered_payload(
    *,
    snapshot: dict[str, Any],
    tiles: list[dict[str, Any]],
    charts: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    current_read: dict[str, Any],
    signals: list[dict[str, Any]],
    provenance: dict[str, Any],
    data_gaps: list[str],
    related_routes: list[str],
) -> dict[str, Any]:
    return {
        "snapshot": snapshot,
        "tiles": tiles,
        "charts": charts,
        "tables": tables,
        "current_read": current_read,
        "signals": signals,
        "provenance": provenance,
        "data_gaps": data_gaps,
        "related_routes": related_routes,
    }


def _snapshot_header(config: MacroModuleConfig, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "module_id": config.module_id,
        "route_path": config.route_path,
        "title": config.title,
        "section": config.section,
        "projection_version": MACRO_MODULE_VIEW_VERSION,
        "status": snapshot.get("status"),
        "asof_date": snapshot.get("asof_date"),
        "source_snapshot_id": snapshot.get("snapshot_id"),
        "source_projection_version": snapshot.get("projection_version"),
        "computed_at_ms": snapshot.get("computed_at_ms"),
    }


def _current_read(config: MacroModuleConfig, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    scenario = _mapping(snapshot.get("scenario_json"))
    chain = _mapping(snapshot.get("chain_json"))
    chain_node = _mapping(chain.get(config.section))
    return {
        "regime": chain_node.get("regime") or snapshot.get("regime"),
        "current_regime": scenario.get("current_regime"),
        "summary": scenario.get("summary"),
        "trade_map": _mapping(scenario.get("trade_map")),
    }


def _signals(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    scenario = _mapping(snapshot.get("scenario_json"))
    signals = scenario.get("watch_triggers") or []
    if not isinstance(signals, list):
        return []
    return [dict(signal) for signal in signals if isinstance(signal, Mapping)]


def _module_concept_keys(config: MacroModuleConfig) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*config.required_concepts, *config.optional_concepts)))


def _tile(concept_key: str, feature: Mapping[str, Any]) -> dict[str, Any]:
    latest = _mapping(feature.get("latest"))
    return {
        "concept_key": concept_key,
        "label": concept_key,
        "latest": latest.get("value"),
        "unit": latest.get("unit"),
        "freshness_days": feature.get("freshness_days"),
    }


def _chart(spec: MacroChartSpec, feature_map: Mapping[str, Any]) -> dict[str, Any]:
    concept_keys = _concept_keys_from_spec(spec)
    missing_concept_keys = [concept_key for concept_key in concept_keys if concept_key not in feature_map]
    series = [
        _series_summary(concept_key, feature_map[concept_key])
        for concept_key in concept_keys
        if concept_key in feature_map
    ]
    return {
        "chart_id": spec.chart_id,
        "status": _spec_status(concept_keys=concept_keys, missing_concept_keys=missing_concept_keys),
        "missing_concept_keys": missing_concept_keys,
        "series": series,
    }


def _table(spec: MacroTableSpec, feature_map: Mapping[str, Any]) -> dict[str, Any]:
    concept_keys = _concept_keys_from_spec(spec)
    missing_concept_keys = [concept_key for concept_key in concept_keys if concept_key not in feature_map]
    rows = [
        _table_row(concept_key, feature_map[concept_key]) for concept_key in concept_keys if concept_key in feature_map
    ]
    return {
        "table_id": spec.table_id,
        "status": _spec_status(concept_keys=concept_keys, missing_concept_keys=missing_concept_keys),
        "missing_concept_keys": missing_concept_keys,
        "rows": rows,
    }


def _series_summary(concept_key: str, feature: Mapping[str, Any]) -> dict[str, Any]:
    latest = _mapping(feature.get("latest"))
    return {
        "concept_key": concept_key,
        "label": concept_key,
        "latest": latest.get("value"),
        "unit": latest.get("unit"),
        "freshness_days": feature.get("freshness_days"),
        "data_gaps": list(feature.get("data_gaps") or []),
    }


def _table_row(concept_key: str, feature: Mapping[str, Any]) -> dict[str, Any]:
    latest = _mapping(feature.get("latest"))
    return {
        "concept_key": concept_key,
        "latest": latest.get("value"),
        "unit": latest.get("unit"),
        "observed_at": latest.get("observed_at"),
        "freshness_days": feature.get("freshness_days"),
        "data_gaps": list(feature.get("data_gaps") or []),
    }


def _missing_chart(spec: MacroChartSpec) -> dict[str, Any]:
    return {
        "chart_id": spec.chart_id,
        "status": "missing",
        "missing_concept_keys": list(spec.concept_keys),
        "series": [],
    }


def _missing_table(spec: MacroTableSpec) -> dict[str, Any]:
    return {
        "table_id": spec.table_id,
        "status": "missing",
        "missing_concept_keys": list(spec.concept_keys),
        "rows": [],
    }


def _cex_board_table(cex_board: Mapping[str, Any] | None) -> dict[str, Any]:
    source = _cex_board_source(cex_board)
    rows = []
    if cex_board is not None:
        rows = [
            _compact_cex_board_row(row, source=source)
            for row in cex_board.get("rows", [])
            if isinstance(row, Mapping)
        ]
    if not rows:
        source = {**source, "degraded_reasons": _unique([*source["degraded_reasons"], "cex_board_empty"])}
    return {
        "table_id": "cex_perp_board",
        "status": "ok" if rows else "missing",
        "missing_concept_keys": [],
        "source": source,
        "rows": rows,
    }


def _cex_board_source(cex_board: Mapping[str, Any] | None) -> dict[str, Any]:
    if cex_board is None:
        return {
            "name": "cex_market_intel",
            "status": "missing",
            "degraded_reasons": ["cex_board_missing"],
            "observed_at_ms": None,
        }
    return {
        "name": "cex_market_intel",
        "status": cex_board.get("status") or "unknown",
        "degraded_reasons": list(cex_board.get("degraded_reasons") or []),
        "observed_at_ms": cex_board.get("observed_at_ms"),
    }


def _compact_cex_board_row(row: Mapping[str, Any], *, source: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for public_key, aliases in _CEX_BOARD_ROW_ALIASES:
        value = _first_present(row, aliases)
        if value is not None:
            payload[public_key] = value
    if "symbol" not in payload:
        symbol = _first_present(row, ("base_symbol", "native_market_id"))
        if symbol is not None:
            payload["symbol"] = symbol
    degraded_reasons = _string_list(
        _first_present(row, ("degraded_reasons", "degraded_reasons_json"))
        or source.get("degraded_reasons")
    )
    if degraded_reasons:
        payload["degraded_reasons"] = degraded_reasons
    if "observed_at_ms" not in payload and source.get("observed_at_ms") is not None:
        payload["observed_at_ms"] = source.get("observed_at_ms")
    return payload


_CEX_BOARD_ROW_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rank", ("rank",)),
    ("symbol", ("symbol", "base_symbol")),
    ("native_market_id", ("native_market_id",)),
    ("quote_symbol", ("quote_symbol",)),
    ("open_interest_usd", ("open_interest_usd", "oi_usd")),
    (
        "open_interest_change_pct_1h",
        ("open_interest_change_pct_1h", "open_interest_delta_1h_pct", "oi_delta_1h_pct"),
    ),
    (
        "open_interest_change_pct_4h",
        ("open_interest_change_pct_4h", "open_interest_delta_4h_pct", "oi_delta_4h_pct"),
    ),
    (
        "open_interest_change_pct_24h",
        ("open_interest_change_pct_24h", "open_interest_delta_24h_pct", "oi_delta_24h_pct"),
    ),
    ("funding_rate", ("funding_rate", "funding_rate_pct")),
    ("volume_24h_usd", ("volume_24h_usd", "volume_usd")),
    ("mark_price", ("mark_price", "price")),
    ("score", ("score",)),
    ("cvd", ("cvd", "cvd_usd")),
    ("long_short_ratio", ("long_short_ratio",)),
    ("top_trader_long_short_ratio", ("top_trader_long_short_ratio",)),
    ("liquidation_bands", ("liquidation_bands", "liquidation_bands_json", "liquidation_levels_json")),
    ("coinglass_status", ("coinglass_status",)),
    ("observed_at_ms", ("observed_at_ms",)),
    ("computed_at_ms", ("computed_at_ms",)),
)


def _data_gaps(config: MacroModuleConfig, snapshot: Mapping[str, Any]) -> list[str]:
    return _unique([*list(snapshot.get("data_gaps_json") or []), *config.gap_codes])


def _latest_import_run(latest_import_run: Mapping[str, Any] | None) -> dict[str, Any]:
    if latest_import_run is None:
        return {"run_id": None, "status": None, "reason_codes": []}
    reason_codes = latest_import_run.get("reason_codes")
    if reason_codes is None:
        reason_codes = latest_import_run.get("reason_codes_json")
    return {
        "run_id": latest_import_run.get("run_id"),
        "status": latest_import_run.get("status"),
        "reason_codes": list(reason_codes or []),
    }


def _observation_sources(observations: Sequence[Mapping[str, Any]]) -> list[str]:
    sources = [str(observation.get("source_name") or "").strip() for observation in observations]
    return sorted({source for source in sources if source})


def _concept_keys_from_spec(spec: MacroChartSpec | MacroTableSpec) -> tuple[str, ...]:
    return spec.concept_keys


def _spec_status(*, concept_keys: tuple[str, ...], missing_concept_keys: list[str]) -> str:
    if not concept_keys:
        return "static"
    if len(missing_concept_keys) == len(concept_keys):
        return "missing"
    if missing_concept_keys:
        return "partial"
    return "ok"


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_present(row: Mapping[str, Any], aliases: Sequence[str]) -> Any | None:
    for alias in aliases:
        value = row.get(alias)
        if value is not None:
            return value
    return None


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


__all__ = ["build_macro_module_view"]
