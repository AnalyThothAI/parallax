from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from parallax.domains.macro_intel._constants import (
    MACRO_CONCEPT_METADATA,
    MACRO_MIN_CHART_POINTS,
    MACRO_MODULE_VIEW_VERSION,
)
from parallax.domains.macro_intel.services.macro_gap_payloads import build_macro_data_gaps
from parallax.domains.macro_intel.services.macro_module_catalog import (
    MacroChartSpec,
    MacroModuleConfig,
    MacroTableSpec,
    get_macro_module_config,
)

TRADE_MAP_RELIABILITY_CONCEPTS = ("asset:ndx", "crypto:btc", "asset:gld", "asset:spx", "asset:tlt")
TRADE_MAP_RELIABILITY_WINDOW_DAYS = 60
TRADE_MAP_PAPER_NOTIONAL_USD = 10_000

_TRADE_MAP_HOLDING_PERIODS = (("1d", "1D", 1), ("5d", "5D", 5), ("20d", "20D", 20))
_ReferenceGapGroup = tuple[str, str, tuple[str, ...], str]

_ASSET_CHANGE_WINDOWS = (
    ("1w", "change_1w_pct", 7),
    ("1m", "change_1m_pct", 30),
)

_ASSET_PRICE_ROWS = (
    {"key": "spx", "label": "SPX", "concept_key": "asset:spx", "kind": "risk"},
    {"key": "tlt", "label": "TLT", "concept_key": "asset:tlt", "kind": "duration"},
    {"key": "dxy", "label": "DXY", "concept_key": "fx:dxy", "kind": "dollar"},
    {"key": "wti", "label": "WTI", "concept_key": "commodity:wti_futures", "kind": "energy"},
    {"key": "btc", "label": "BTC", "concept_key": "crypto:btc", "kind": "crypto"},
)

_DATA_CREDIBILITY_CONCEPTS = (
    "asset:spx",
    "fx:dxy",
    "crypto:btc",
    "commodity:wti_futures",
    "rates:dgs10",
    "vol:vix",
    "credit:hy_oas",
    "liquidity:on_rrp",
)
_DATA_CREDIBILITY_MIN_ROWS = 6
_DATA_CREDIBILITY_OK_QUALITIES = {"ok", "ready"}

_NEWS_MARKET_SCOPE_LABELS = {
    "assets": "大类资产",
    "commodities": "商品",
    "credit": "信用市场",
    "crypto": "加密货币",
    "economy": "经济数据",
    "employment": "就业",
    "equities": "美股",
    "fx": "外汇",
    "inflation": "通胀",
    "liquidity": "流动性",
    "macro_policy": "美联储",
    "macro_rates": "利率",
    "rates": "利率",
    "volatility": "波动率",
}

_EQUITY_DIAGNOSTIC_PRICE_ROWS = (
    {"key": "spx", "label": "SPX", "concept_key": "asset:spx", "kind": "risk"},
    {"key": "ndx", "label": "NDX", "concept_key": "asset:ndx", "kind": "risk"},
    {"key": "rut", "label": "RUT", "concept_key": "asset:rut", "kind": "risk"},
    {"key": "qqq", "label": "QQQ", "concept_key": "asset:qqq", "kind": "risk"},
    {"key": "iwm", "label": "IWM", "concept_key": "asset:iwm", "kind": "risk"},
)

_BOND_DIAGNOSTIC_PRICE_ROWS = (
    {"key": "tlt", "label": "TLT", "concept_key": "asset:tlt", "kind": "duration"},
    {"key": "ief", "label": "IEF", "concept_key": "asset:ief", "kind": "duration"},
    {"key": "lqd", "label": "LQD", "concept_key": "asset:lqd", "kind": "credit"},
    {"key": "hyg", "label": "HYG", "concept_key": "asset:hyg", "kind": "credit"},
)

_BOND_DIAGNOSTIC_OAS_ROWS = (
    {"key": "hy_oas", "label": "HY OAS", "concept_key": "credit:hy_oas"},
    {"key": "ig_oas", "label": "IG OAS", "concept_key": "credit:ig_oas"},
)

_COMMODITY_DIAGNOSTIC_PRICE_ROWS = (
    {"key": "wti", "label": "WTI", "concept_key": "commodity:wti_futures", "kind": "energy"},
    {"key": "brent", "label": "Brent", "concept_key": "commodity:brent", "kind": "energy"},
    {"key": "natgas", "label": "NatGas", "concept_key": "commodity:natgas_futures", "kind": "energy"},
    {"key": "gold", "label": "Gold", "concept_key": "commodity:gold_futures", "kind": "precious"},
    {"key": "copper", "label": "Copper", "concept_key": "commodity:copper_futures", "kind": "industrial"},
)

_FX_DIAGNOSTIC_ROWS = (
    {"key": "dxy", "label": "DXY", "concept_key": "fx:dxy", "kind": "dollar"},
    {"key": "broad_dollar", "label": "Broad USD", "concept_key": "fx:broad_dollar", "kind": "dollar"},
    {"key": "eurusd", "label": "EURUSD", "concept_key": "fx:eurusd", "usd_direction": "inverse"},
    {"key": "usdjpy", "label": "USDJPY", "concept_key": "fx:usdjpy", "usd_direction": "direct"},
    {"key": "usdcny", "label": "USDCNY", "concept_key": "fx:usdcny", "usd_direction": "direct"},
    {"key": "uup", "label": "UUP", "concept_key": "asset:uup", "kind": "dollar"},
)

_CRYPTO_DIAGNOSTIC_PRICE_ROWS = (
    {"key": "btc", "label": "BTC", "concept_key": "crypto:btc", "kind": "crypto"},
    {"key": "eth", "label": "ETH", "concept_key": "crypto:eth", "kind": "crypto"},
)

_CRYPTO_DERIVATIVE_OI_ROWS = (
    {
        "key": "btc_perp_oi",
        "label": "BTC 永续 OI",
        "concept_keys": (
            "crypto_derivatives:okx_btc_oi_usd",
            "crypto_derivatives:deribit_btc_oi_usd",
        ),
    },
    {
        "key": "eth_perp_oi",
        "label": "ETH 永续 OI",
        "concept_keys": (
            "crypto_derivatives:okx_eth_oi_usd",
            "crypto_derivatives:deribit_eth_oi_usd",
        ),
    },
)

_CRYPTO_DERIVATIVE_AVERAGE_BP_ROWS = (
    {
        "key": "btc_funding",
        "label": "BTC 资金费率",
        "concept_keys": (
            "crypto_derivatives:okx_btc_funding",
            "crypto_derivatives:deribit_btc_funding_8h",
        ),
        "scale_to_bp": 10_000.0,
        "status_kind": "funding",
    },
    {
        "key": "eth_funding",
        "label": "ETH 资金费率",
        "concept_keys": (
            "crypto_derivatives:okx_eth_funding",
            "crypto_derivatives:deribit_eth_funding_8h",
        ),
        "scale_to_bp": 10_000.0,
        "status_kind": "funding",
    },
    {
        "key": "btc_basis",
        "label": "BTC 基差",
        "concept_keys": (
            "crypto_derivatives:okx_btc_basis",
            "crypto_derivatives:deribit_btc_basis",
        ),
        "scale_to_bp": 100.0,
        "status_kind": "basis",
    },
    {
        "key": "eth_basis",
        "label": "ETH 基差",
        "concept_keys": (
            "crypto_derivatives:okx_eth_basis",
            "crypto_derivatives:deribit_eth_basis",
        ),
        "scale_to_bp": 100.0,
        "status_kind": "basis",
    },
)

_CRYPTO_DERIVATIVE_VOL_ROWS = (
    {
        "key": "btc_dvol",
        "label": "BTC DVOL",
        "concept_key": "crypto_derivatives:deribit_btc_vol_index",
    },
    {
        "key": "eth_dvol",
        "label": "ETH DVOL",
        "concept_key": "crypto_derivatives:deribit_eth_vol_index",
    },
)

_YIELD_CURVE_CHANGE_WINDOWS = (
    ("1w", "change_1w_bp", 7),
    ("1m", "change_1m_bp", 30),
    ("3m", "change_3m_bp", 90),
)
_YIELD_CURVE_HISTORY_POINT_LIMIT = 64

_CREDIT_CHANGE_WINDOWS = (
    ("1w", "change_1w_bp", 7),
    ("1m", "change_1m_bp", 30),
    ("3m", "change_3m_bp", 90),
)

_CREDIT_CONDITIONS_CHANGE_WINDOWS = (
    ("1w", "change_1w_index", 7),
    ("1m", "change_1m_index", 30),
    ("3m", "change_3m_index", 90),
)

_CREDIT_OAS_ROWS = (
    {"key": "hy_oas", "label": "HY OAS", "concept_key": "credit:hy_oas"},
    {"key": "ig_oas", "label": "IG OAS", "concept_key": "credit:ig_oas"},
)

_VOLATILITY_CHANGE_WINDOWS = (
    ("1w", "change_1w_index", 7),
    ("1m", "change_1m_index", 30),
)

_LIQUIDITY_CHANGE_WINDOWS = (
    ("1w", 7),
    ("1m", 30),
)

_LIQUIDITY_PRESSURE_DRIVER_PRIORITY = (
    "sofr_iorb",
    "net_liquidity",
    "tga",
    "on_rrp",
    "sofr_tgcr",
    "sofr_volume",
)

_YIELD_CURVE_SPREADS = (
    {"key": "2s10s", "label": "2s10s", "front": "rates:dgs2", "back": "rates:dgs10"},
    {"key": "3m10y", "label": "3m10y", "front": "rates:dgs3mo", "back": "rates:dgs10"},
    {"key": "5s30s", "label": "5s30s", "front": "rates:dgs5", "back": "rates:dgs30"},
)

_YIELD_CURVE_TENORS = (
    {
        "key": "5y",
        "label": "5Y",
        "nominal": "rates:dgs5",
        "real": "rates:real_5y",
        "breakeven": "inflation:5y_breakeven",
    },
    {
        "key": "10y",
        "label": "10Y",
        "nominal": "rates:dgs10",
        "real": "rates:real_10y",
        "breakeven": "inflation:10y_breakeven",
    },
)

_REAL_RATE_REAL_ROWS = (
    {"key": "real_5y", "label": "5Y Real", "concept_key": "rates:real_5y"},
    {"key": "real_10y", "label": "10Y Real", "concept_key": "rates:real_10y"},
    {"key": "real_30y", "label": "30Y Real", "concept_key": "rates:real_30y"},
)

_REAL_RATE_INFLATION_ROWS = (
    {"key": "breakeven_5y", "label": "5Y Breakeven", "concept_key": "inflation:5y_breakeven"},
    {"key": "breakeven_10y", "label": "10Y Breakeven", "concept_key": "inflation:10y_breakeven"},
    {"key": "forward_5y5y", "label": "5Y5Y Forward", "concept_key": "inflation:5y5y_forward"},
)

_TRADE_MAP_RELIABILITY_ASSETS = (
    {"asset": "NDX", "label": "纳斯达克", "concept_key": "asset:ndx"},
    {"asset": "BTC", "label": "比特币", "concept_key": "crypto:btc"},
    {"asset": "GOLD", "label": "黄金", "concept_key": "asset:gld"},
    {"asset": "SPX", "label": "标普500", "concept_key": "asset:spx"},
    {"asset": "TLT", "label": "长债", "concept_key": "asset:tlt"},
)

_TRADE_MAP_EXPECTATIONS = {
    "risk_down_credit_sensitive": {
        "NDX": ("down", "回避"),
        "BTC": ("down", "回避"),
        "GOLD": ("up", "防守"),
        "SPX": ("down", "回避"),
        "TLT": ("up", "防守"),
    },
    "duration_pressure_quality_over_growth": {
        "NDX": ("down", "回避"),
        "BTC": ("down", "回避"),
        "GOLD": ("down", "低配"),
        "SPX": ("down", "回避"),
        "TLT": ("down", "低配"),
    },
    "credit_beta_underweight": {
        "NDX": ("down", "低配"),
        "BTC": ("down", "低配"),
        "GOLD": ("up", "防守"),
        "SPX": ("down", "低配"),
        "TLT": ("up", "防守"),
    },
    "risk_on_liquidity_beta": {
        "NDX": ("up", "做多"),
        "BTC": ("up", "做多"),
        "GOLD": ("up", "顺势"),
        "SPX": ("up", "做多"),
        "TLT": ("down", "低配"),
    },
}

_TRADE_MAP_EXPRESSION_LABELS = {
    "credit_beta_underweight": "低配信用 beta",
    "duration_pressure_quality_over_growth": "久期承压 / 质量优于成长",
    "risk_down_credit_sensitive": "风险降档 / 信用敏感",
    "risk_on_liquidity_beta": "流动性 risk-on beta",
}


def build_macro_module_view(
    module_id: str,
    snapshot: Mapping[str, Any] | None,
    observations: Sequence[Mapping[str, Any]],
    daily_brief: Mapping[str, Any] | None = None,
    news_rows: Sequence[Mapping[str, Any]] = (),
    facts_max_observed_at: object = None,
    projection_lag_days: int | None = None,
    projection_behind_facts: bool = False,
) -> dict[str, Any]:
    config = get_macro_module_config(module_id)
    if snapshot is None:
        return _missing_view(
            config=config,
            facts_max_observed_at=facts_max_observed_at,
            projection_lag_days=projection_lag_days,
            projection_behind_facts=projection_behind_facts,
        )

    snapshot_sections = _macro_module_view_snapshot_sections(snapshot)
    concept_keys = _module_concept_keys(config)
    feature_map = _module_feature_map(
        snapshot_sections["features_json"],
        observations=observations,
        concept_keys=concept_keys,
        include_observation_supplements=config.module_id != "overview",
    )
    primary_chart = _primary_chart(config.chart_specs[0], feature_map)
    data_health = _data_health(
        config=config,
        data_gaps=snapshot_sections["data_gaps_json"],
        feature_map=feature_map,
        concept_keys=concept_keys,
        primary_chart=primary_chart,
        snapshot_status=str(snapshot.get("status") or ""),
    )

    tables = [_table(spec, feature_map) for spec in config.table_specs]
    tables.append(
        _availability_table(
            config=config,
            feature_map=feature_map,
            concept_keys=concept_keys,
            data_gaps=_availability_gaps(data_health),
        )
    )

    tiles = [_tile(concept_key, feature_map[concept_key]) for concept_key in concept_keys if concept_key in feature_map]
    payload = _ordered_payload(
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
            scenario=snapshot_sections["scenario_json"],
            observations=observations,
            news_rows=news_rows,
        ),
        module_evidence=_module_evidence(
            config=config,
            feature_map=feature_map,
            primary_chart=primary_chart,
            data_health=data_health,
            scenario=snapshot_sections["scenario_json"],
        ),
        transmission=_transmission(
            config=config,
            chain=snapshot_sections["chain_json"],
            feature_map=feature_map,
            data_health=data_health,
        ),
        data_health=data_health,
        provenance=_provenance(
            snapshot=snapshot,
            observations=observations,
            facts_max_observed_at=facts_max_observed_at,
            projection_lag_days=projection_lag_days,
            projection_behind_facts=projection_behind_facts,
        ),
        related_routes=_related_routes(config.related_routes),
    )
    if config.module_id == "assets" and daily_brief is not None:
        payload["daily_brief"] = dict(daily_brief)
    return payload


def _macro_module_view_snapshot_sections(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "panels_json": _required_snapshot_mapping(snapshot, "panels_json"),
        "indicators_json": _required_snapshot_mapping(snapshot, "indicators_json"),
        "triggers_json": _required_snapshot_list(snapshot, "triggers_json"),
        "data_gaps_json": _required_snapshot_list(snapshot, "data_gaps_json"),
        "source_coverage_json": _required_snapshot_mapping(snapshot, "source_coverage_json"),
        "features_json": _required_snapshot_mapping(snapshot, "features_json"),
        "chain_json": _required_snapshot_mapping(snapshot, "chain_json"),
        "scenario_json": _required_snapshot_mapping(snapshot, "scenario_json"),
        "scorecard_json": _required_snapshot_mapping(snapshot, "scorecard_json"),
    }


def _module_feature_map(
    snapshot_feature_map: Mapping[str, Any],
    *,
    observations: Sequence[Mapping[str, Any]],
    concept_keys: Sequence[str],
    include_observation_supplements: bool,
) -> dict[str, Any]:
    merged = {str(concept_key): feature for concept_key, feature in snapshot_feature_map.items()}
    if not include_observation_supplements:
        return merged
    wanted = {str(concept_key) for concept_key in concept_keys}
    for concept_key, concept_observations in _module_observations_by_concept(observations, concept_keys=wanted).items():
        feature = _feature_from_observations(concept_key, concept_observations)
        if feature is not None:
            existing = _mapping(merged.get(concept_key))
            if existing:
                if _observation_feature_is_newer_or_deeper(existing, feature):
                    merged[concept_key] = _merge_observation_feature(existing, feature)
            else:
                merged[concept_key] = feature
    return merged


def _module_observations_by_concept(
    observations: Sequence[Mapping[str, Any]],
    *,
    concept_keys: set[str],
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for observation in observations:
        concept_key = str(observation.get("concept_key") or "").strip()
        if concept_key not in concept_keys:
            continue
        observed_date = _parse_date(str(observation.get("observed_at") or ""))
        if observed_date is None:
            continue
        grouped.setdefault(concept_key, []).append(observation)
    for concept_observations in grouped.values():
        concept_observations.sort(key=lambda item: _parse_date(str(item.get("observed_at") or "")) or date.min)
    return grouped


def _feature_from_observations(
    concept_key: str,
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    history = [
        {"observed_at": str(observation.get("observed_at") or ""), "value": value}
        for observation in observations
        if (value := _observation_value(observation)) is not None and str(observation.get("observed_at") or "").strip()
    ]
    if not history:
        return None
    latest_observation = observations[-1]
    latest = history[-1]
    unit = latest_observation.get("unit")
    quality = str(latest_observation.get("data_quality") or "ok")
    series_key = str(latest_observation.get("series_key") or "").strip()
    source_name = str(
        latest_observation.get("source_name") or latest_observation.get("provider") or _provider_from_series(series_key)
    )
    history_points = len(history)
    history_ready = history_points >= MACRO_MIN_CHART_POINTS
    return {
        "concept_key": concept_key,
        "label": _concept_required_text(concept_key, "label"),
        "short_label": _concept_required_text(concept_key, "short_label"),
        "description": _concept_optional_text(concept_key, "description") or "",
        "unit_label": _concept_required_text(concept_key, "unit_label", error_field="unit"),
        "latest": {"value": latest["value"], "observed_at": latest["observed_at"], "unit": unit},
        "freshness_days": None,
        "delta": {"20d": None},
        "history": history,
        "history_points": history_points,
        "history_windows": {
            "20d": {"points": history_points, "required_points": MACRO_MIN_CHART_POINTS, "ready": history_ready}
        },
        "score_participation": False,
        "data_quality": quality,
        "source": {"name": source_name, "series_key": series_key},
        "data_gaps": []
        if history_ready
        else [
            {
                "code": "insufficient_history_20d",
                "label": "历史样本不足：无法计算 20 日变化",
                "severity": "warning",
                "score_participation": False,
                "remediation_hint": "回填历史后重新生成宏观投影。",
            }
        ],
    }


def _observation_value(observation: Mapping[str, Any]) -> float | None:
    value = _number(observation.get("value_numeric"))
    return value if value is not None else _number(observation.get("value"))


def _observation_feature_is_newer_or_deeper(
    existing: Mapping[str, Any],
    observation_feature: Mapping[str, Any],
) -> bool:
    existing_points = _int_or_none(existing.get("history_points")) or len(_mapping_list(existing.get("history")))
    observation_points = _int_or_none(observation_feature.get("history_points")) or len(
        _mapping_list(observation_feature.get("history"))
    )
    if observation_points > existing_points:
        return True
    existing_latest = _parse_date(str(_mapping(existing.get("latest")).get("observed_at") or ""))
    observation_latest = _parse_date(str(_mapping(observation_feature.get("latest")).get("observed_at") or ""))
    return observation_latest is not None and (existing_latest is None or observation_latest > existing_latest)


def _merge_observation_feature(existing: Mapping[str, Any], observation_feature: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for field_name in (
        "latest",
        "freshness_days",
        "delta",
        "history",
        "history_points",
        "history_windows",
        "data_quality",
        "source",
        "data_gaps",
    ):
        merged[field_name] = observation_feature.get(field_name)
    return merged


def _provider_from_series(series_key: str) -> str:
    if ":" not in series_key:
        return ""
    return series_key.split(":", 1)[0]


def _required_snapshot_mapping(snapshot: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if field_name not in snapshot or snapshot.get(field_name) is None:
        raise ValueError(f"macro_module_view_snapshot_section_required:{field_name}")
    value = snapshot.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"macro_module_view_snapshot_section_invalid:{field_name}")
    return dict(value)


def _required_snapshot_list(snapshot: Mapping[str, Any], field_name: str) -> list[Any]:
    if field_name not in snapshot or snapshot.get(field_name) is None:
        raise ValueError(f"macro_module_view_snapshot_section_required:{field_name}")
    value = snapshot.get(field_name)
    if isinstance(value, Mapping | str | bytes | bytearray):
        raise ValueError(f"macro_module_view_snapshot_section_invalid:{field_name}")
    if not isinstance(value, Sequence):
        raise ValueError(f"macro_module_view_snapshot_section_invalid:{field_name}")
    return list(value)


def _missing_view(
    config: MacroModuleConfig,
    facts_max_observed_at: object = None,
    projection_lag_days: int | None = None,
    projection_behind_facts: bool = False,
) -> dict[str, Any]:
    primary_chart = _missing_chart(config.chart_specs[0])
    data_health = _data_health(
        config=config,
        data_gaps=build_macro_data_gaps(["macro_view_snapshot_missing"]),
        feature_map={},
        concept_keys=(),
        primary_chart=primary_chart,
        snapshot_status="missing",
    )
    payload = _ordered_payload(
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
        tables=[_missing_table(spec) for spec in config.table_specs]
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
        transmission=_transmission(config=config, chain={}, feature_map={}, data_health=data_health),
        data_health=data_health,
        provenance=_provenance(
            snapshot={},
            observations=[],
            facts_max_observed_at=facts_max_observed_at,
            projection_lag_days=projection_lag_days,
            projection_behind_facts=projection_behind_facts,
        ),
        related_routes=_related_routes(config.related_routes),
    )
    if config.module_id == "assets":
        payload["daily_brief"] = None
    return payload


def _ordered_payload(
    *,
    snapshot: dict[str, Any],
    tiles: list[dict[str, Any]],
    primary_chart: dict[str, Any],
    tables: list[dict[str, Any]],
    module_read: dict[str, Any],
    module_evidence: dict[str, Any],
    transmission: list[dict[str, Any]],
    data_health: dict[str, Any],
    provenance: dict[str, Any],
    related_routes: list[dict[str, str]],
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
                        "display_value": _concept_required_text(concept_key, "label"),
                        "sort_value": _concept_short_label(concept_key),
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
        code = _required_data_gap_field(gap, "code")
        label = _required_data_gap_field(gap, "label")
        severity = _required_data_gap_field(gap, "severity")
        remediation_hint = _required_data_gap_field(gap, "remediation_hint")
        rows.append(
            {
                "row_id": f"gap:{code}",
                "row_quality": severity,
                "source_state": {"label": "数据可用性", "status": severity},
                "cells": {
                    "item": {"display_value": label, "sort_value": code},
                    "status": {"display_value": severity, "sort_value": severity},
                    "latest": {"display_value": "n/a", "sort_value": None},
                    "coverage": {"display_value": "计分排除", "sort_value": 0},
                    "notes": {
                        "display_value": remediation_hint,
                        "sort_value": remediation_hint,
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
    scenario: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    news_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if config.module_id == "overview":
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
    read: dict[str, Any] = {
        "headline": f"{config.title}：{headline_label}",
        "regime_label": headline_label,
        "confidence_label": confidence_label,
        "data_note": "本页只展示已入库的真实观测、规则状态和可用性说明。",
        "methodology_note": f"{config.title} 使用模块配置中的 required/optional 概念生成图表和表格。",
    }
    if config.module_id == "overview":
        read["decision_console"] = _decision_console(
            scenario=scenario,
            data_health=data_health,
            feature_map=feature_map,
            observations=observations,
        )
        structured_analysis = _structured_analysis(
            feature_map,
            scenario=scenario,
            observations=observations,
        )
        if structured_analysis is not None:
            read["structured_analysis"] = structured_analysis
        market_event_flow = _market_event_flow(_event_catalyst_candidates(observations), news_rows=news_rows)
        if market_event_flow is not None:
            read["market_event_flow"] = market_event_flow
    if config.module_id == "assets":
        asset_diagnostics = _asset_diagnostics(feature_map)
        if asset_diagnostics is not None:
            read["asset_diagnostics"] = asset_diagnostics
    if config.module_id.startswith("assets/"):
        asset_class_diagnostics = _asset_class_diagnostics(config.module_id, feature_map)
        if asset_class_diagnostics is not None:
            read["asset_class_diagnostics"] = asset_class_diagnostics
    if config.module_id == "rates/fed-funds":
        policy_diagnostics = _policy_diagnostics(feature_map)
        if policy_diagnostics is not None:
            read["policy_diagnostics"] = policy_diagnostics
    if config.module_id == "rates/yield-curve":
        curve_diagnostics = _yield_curve_diagnostics(feature_map)
        if curve_diagnostics is not None:
            read["curve_diagnostics"] = curve_diagnostics
    if config.module_id == "rates/real-rates":
        real_rate_diagnostics = _real_rate_diagnostics(feature_map)
        if real_rate_diagnostics is not None:
            read["real_rate_diagnostics"] = real_rate_diagnostics
    if config.module_id == "credit/stress":
        credit_diagnostics = _credit_diagnostics(feature_map)
        if credit_diagnostics is not None:
            read["credit_diagnostics"] = credit_diagnostics
    if config.module_id == "volatility/vix":
        volatility_diagnostics = _volatility_diagnostics(feature_map)
        if volatility_diagnostics is not None:
            read["volatility_diagnostics"] = volatility_diagnostics
    if config.module_id == "liquidity/rrp-tga":
        liquidity_diagnostics = _liquidity_diagnostics(feature_map)
        if liquidity_diagnostics is not None:
            read["liquidity_diagnostics"] = liquidity_diagnostics
    if config.module_id == "economy/gdp":
        growth_diagnostics = _growth_diagnostics(feature_map)
        if growth_diagnostics is not None:
            read["growth_diagnostics"] = growth_diagnostics
    if config.module_id == "economy/employment":
        employment_diagnostics = _employment_diagnostics(feature_map)
        if employment_diagnostics is not None:
            read["employment_diagnostics"] = employment_diagnostics
    if config.module_id == "economy/inflation":
        inflation_diagnostics = _inflation_diagnostics(feature_map)
        if inflation_diagnostics is not None:
            read["inflation_diagnostics"] = inflation_diagnostics
    return read


def _structured_analysis(
    feature_map: Mapping[str, Any],
    *,
    scenario: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    rows = [
        row
        for row in (
            _structured_market_thesis_row(scenario),
            _structured_fed_communication_row(observations),
            _structured_analysis_row(
                key="assets",
                label="大类资产",
                diagnostics=_asset_diagnostics(feature_map),
            ),
            _structured_analysis_row(
                key="rates",
                label="利率曲线",
                diagnostics=_yield_curve_diagnostics(feature_map),
            ),
            _structured_analysis_row(
                key="policy",
                label="美联储",
                diagnostics=_policy_diagnostics(feature_map),
            ),
            _structured_analysis_row(
                key="liquidity",
                label="流动性",
                diagnostics=_liquidity_diagnostics(feature_map),
            ),
            _structured_analysis_row(
                key="growth",
                label="经济增长",
                diagnostics=_growth_diagnostics(feature_map),
            ),
            _structured_analysis_row(
                key="employment",
                label="就业",
                diagnostics=_employment_diagnostics(feature_map),
            ),
            _structured_analysis_row(
                key="inflation",
                label="通胀",
                diagnostics=_inflation_diagnostics(feature_map),
            ),
            _structured_analysis_row(
                key="volatility",
                label="波动率",
                diagnostics=_volatility_diagnostics(feature_map),
            ),
            _structured_analysis_row(
                key="credit",
                label="信用市场",
                diagnostics=_credit_diagnostics(feature_map),
            ),
        )
        if row is not None
    ]
    if not rows:
        return None
    return {
        "key": "structured_analysis",
        "label": "跨域判断链",
        "rows": rows,
    }


def _structured_market_thesis_row(scenario: Mapping[str, Any]) -> dict[str, Any] | None:
    regime = str(scenario.get("current_regime") or "").strip()
    regime_label = _regime_label(regime) if regime else None
    base_case = _structured_base_case(scenario)
    thesis = str(base_case.get("thesis") or "").strip()
    if thesis:
        fact = f"市场主线：{thesis}"
    elif regime_label:
        fact = f"市场主线：{regime_label}。"
    else:
        return None
    evidence = _structured_market_evidence(scenario)
    trade = str(base_case.get("trade") or "").strip()
    if not trade:
        trade = _structured_market_trade(scenario)
    invalidation = str(base_case.get("invalidation") or "").strip()
    if not invalidation:
        invalidation = _structured_market_invalidation(scenario)
    if not fact or not evidence or not trade or not invalidation:
        return None
    return {
        "key": "market_thesis",
        "label": "市场主线",
        "regime_label": regime_label,
        "fact": fact,
        "evidence": evidence[:3],
        "trade": trade,
        "invalidation": invalidation,
    }


def _structured_base_case(scenario: Mapping[str, Any]) -> Mapping[str, Any]:
    scenario_cases = _mapping_list(scenario.get("scenario_cases"))
    return next(
        (case for case in scenario_cases if str(case.get("case") or "") == "base"),
        scenario_cases[0] if scenario_cases else {},
    )


def _structured_market_evidence(scenario: Mapping[str, Any]) -> list[str]:
    evidence: list[str] = []
    for item in _mapping_list(scenario.get("top_changes")):
        line = _structured_signal_line(item)
        if line:
            evidence.append(line)
        if len(evidence) >= 2:
            break
    for item in _mapping_list(scenario.get("confirmations")):
        if len(evidence) >= 2:
            break
        line = _structured_signal_line(item)
        if line:
            evidence.append(line)
    trade = _structured_market_trade(scenario)
    if trade:
        evidence.append(f"Trade Map · {trade.removeprefix('当前表达：')}")
    return evidence


def _structured_signal_line(item: Mapping[str, Any]) -> str | None:
    code = str(item.get("code") or "").strip()
    label = str(item.get("label") or _code_label(code) or "").strip()
    if not label:
        return None
    detail = str(
        item.get("evidence_label")
        or item.get("description")
        or item.get("change_label")
        or item.get("value_label")
        or ""
    ).strip()
    return f"{label} · {detail}" if detail else label


def _structured_market_trade(scenario: Mapping[str, Any]) -> str:
    labels = [
        str(item.get("label") or _trade_map_expression_label(str(item.get("expression") or "")) or "").strip()
        for item in _mapping_list(scenario.get("trade_map"))
        if str(item.get("expression") or "").strip()
    ]
    labels = [label for label in labels if label]
    if not labels:
        return ""
    return f"当前表达：{' / '.join(labels[:2])}"


def _structured_market_invalidation(scenario: Mapping[str, Any]) -> str:
    first = next(iter(_mapping_list(scenario.get("invalidations"))), None)
    if first is None:
        return ""
    code = str(first.get("code") or "").strip()
    label = str(first.get("label") or _code_label(code) or "").strip()
    description = str(first.get("description") or "").strip()
    if label and description:
        return f"{label}：{description}"
    return label or description


def _structured_fed_communication_row(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    catalyst = next(
        (item for item in _event_catalyst_candidates(observations) if str(item.get("kind") or "") == "fed_text"),
        None,
    )
    if catalyst is None:
        return None
    detail = str(catalyst.get("description") or "").strip()
    if not detail:
        return None
    document_type = str(catalyst.get("document_type") or "").strip()
    document_label = _fed_document_type_label(document_type)
    evidence = _structured_fed_communication_evidence(catalyst)
    if not evidence:
        return None
    return {
        "key": "fed_communication",
        "label": "美联储沟通",
        "regime_label": document_label,
        "fact": f"Fed 沟通：{detail}",
        "evidence": evidence,
        "trade": "利率路径和流动性定价需跟随 Fed 沟通重新校准。",
        "invalidation": "若后续 FOMC 声明、纪要或讲话与当前政策路径反向，Fed 沟通读法降级。",
    }


def _structured_fed_communication_evidence(catalyst: Mapping[str, Any]) -> list[str]:
    source = str(catalyst.get("source") or "").strip()
    speaker = str(catalyst.get("speaker") or "").strip()
    label = str(catalyst.get("label") or "Fed 文档").strip()
    primary_parts = [label, source, speaker]
    evidence = [" · ".join(part for part in primary_parts if part)]
    _category, _category_label, _impact, impact_label, watch = _event_flow_classification(catalyst)
    secondary = " · ".join(part for part in (impact_label, watch) if part)
    if secondary:
        evidence.append(secondary)
    return [line for line in evidence if line][:3]


def _fed_document_type_label(document_type: str) -> str:
    return {
        "minutes": "会议纪要",
        "press_release": "新闻稿",
        "speech": "讲话",
        "statement": "声明",
    }.get(document_type, "Fed 文档")


def _structured_analysis_row(
    *,
    key: str,
    label: str,
    diagnostics: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if diagnostics is None:
        return None
    fact = str(diagnostics.get("summary") or "").strip()
    evidence = _structured_analysis_evidence(diagnostics)
    trade = _first_string(diagnostics.get("implications"))
    invalidation = _first_string(diagnostics.get("invalidations"))
    if not fact or not evidence or not trade or not invalidation:
        return None
    return {
        "key": key,
        "label": label,
        "regime_label": _structured_regime_label(diagnostics),
        "fact": fact,
        "evidence": evidence[:3],
        "trade": trade,
        "invalidation": invalidation,
    }


def _structured_regime_label(diagnostics: Mapping[str, Any]) -> str:
    return str(
        diagnostics.get("regime_label") or diagnostics.get("shape_label") or diagnostics.get("label") or "样本不足"
    )


def _structured_analysis_evidence(diagnostics: Mapping[str, Any]) -> list[str]:
    rows = _mapping_list(diagnostics.get("rows"))
    if not rows:
        rows = _mapping_list(diagnostics.get("real_yield_rows"))
    if not rows:
        rows = _mapping_list(diagnostics.get("inflation_rows"))
    return [line for line in (_structured_evidence_line(row) for row in rows) if line]


def _structured_evidence_line(row: Mapping[str, Any]) -> str | None:
    label = str(row.get("label") or "").strip()
    if not label:
        return None
    parts = [
        label,
        _structured_evidence_value_label(row),
        str(row.get("status_label") or "").strip(),
    ]
    return " · ".join(part for part in parts if part)


def _structured_evidence_value_label(row: Mapping[str, Any]) -> str:
    for field_name, suffix in (
        ("current_bp", "bp"),
        ("current_pct", "%"),
        ("current_yoy_pct", "% y/y"),
        ("current_k", "k"),
        ("current_m", "M"),
        ("current_bn", "B"),
        ("current_trillion", "T"),
        ("current_index", ""),
        ("current_points", "pts"),
        ("current_ratio", "x"),
    ):
        value = _number(row.get(field_name))
        if value is None:
            continue
        body = _structured_number_label(value)
        if suffix == "B":
            return f"${body}B"
        if suffix == "T":
            return f"${body}T"
        return f"{body}{suffix}"
    pct_parts = _structured_change_parts(row, (("1w", "change_1w_pct"), ("1m", "change_1m_pct")), "%")
    if pct_parts:
        return " · ".join(pct_parts)
    bp_parts = _structured_change_parts(row, (("1w", "change_1w_bp"), ("1m", "change_1m_bp")), "bp")
    if bp_parts:
        return " · ".join(bp_parts)
    return ""


def _structured_change_parts(
    row: Mapping[str, Any],
    fields: Sequence[tuple[str, str]],
    suffix: str,
) -> list[str]:
    parts: list[str] = []
    for label, field_name in fields:
        value = _number(row.get(field_name))
        if value is None:
            continue
        parts.append(f"{label} {_structured_signed_number_label(value)}{suffix}")
    return parts


def _structured_number_label(value: float) -> str:
    rounded = round(float(value), 1)
    if rounded == 0:
        rounded = 0.0
    return str(int(rounded)) if rounded.is_integer() else f"{rounded:.1f}"


def _structured_signed_number_label(value: float) -> str:
    label = _structured_number_label(value)
    return label if label.startswith("-") or label == "0" else f"+{label}"


def _first_string(value: object) -> str:
    items = _string_list(value)
    return items[0] if items else ""


def _asset_diagnostics(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = [row for spec in _ASSET_PRICE_ROWS if (row := _asset_price_row(spec, feature_map)) is not None]
    vix_row = _asset_vix_row(feature_map)
    if vix_row is not None:
        rows.append(vix_row)
    hy_oas_row = _asset_hy_oas_row(feature_map)
    if hy_oas_row is not None:
        rows.append(hy_oas_row)
    if not rows or not any(_asset_row_has_change(row) for row in rows):
        return None
    regime, regime_label, summary = _asset_regime(rows)
    return {
        "label": "跨资产诊断",
        "regime": regime,
        "regime_label": regime_label,
        "summary": summary,
        "rows": rows,
        "implications": _asset_implications(regime),
        "invalidations": _asset_invalidations(regime),
    }


def _asset_class_diagnostics(module_id: str, feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    if module_id == "assets/equities":
        return _equity_diagnostics(feature_map)
    if module_id == "assets/bonds":
        return _bond_diagnostics(feature_map)
    if module_id == "assets/commodities":
        return _commodity_diagnostics(feature_map)
    if module_id == "assets/fx":
        return _fx_diagnostics(feature_map)
    if module_id == "assets/crypto":
        return _crypto_diagnostics(feature_map)
    return None


def _equity_diagnostics(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = [row for spec in _EQUITY_DIAGNOSTIC_PRICE_ROWS if (row := _asset_price_row(spec, feature_map)) is not None]
    positioning_row = _equity_positioning_row(feature_map)
    if positioning_row is not None:
        rows.append(positioning_row)
    if not rows or not any(_asset_row_has_change(row) for row in rows):
        return None
    regime, regime_label, summary = _equity_regime(rows)
    return {
        "label": "美股风险诊断",
        "regime": regime,
        "regime_label": regime_label,
        "summary": summary,
        "rows": rows,
        "implications": _equity_implications(regime),
        "invalidations": _equity_invalidations(regime),
    }


def _bond_diagnostics(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = [row for spec in _BOND_DIAGNOSTIC_PRICE_ROWS if (row := _asset_price_row(spec, feature_map)) is not None]
    rows.extend(
        row for spec in _BOND_DIAGNOSTIC_OAS_ROWS if (row := _asset_credit_oas_row(spec, feature_map)) is not None
    )
    if not rows or not any(_asset_row_has_change(row) for row in rows):
        return None
    regime, regime_label, summary = _bond_regime(rows)
    return {
        "label": "债券风险诊断",
        "regime": regime,
        "regime_label": regime_label,
        "summary": summary,
        "rows": rows,
        "implications": _bond_implications(regime),
        "invalidations": _bond_invalidations(regime),
    }


def _commodity_diagnostics(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = [
        row for spec in _COMMODITY_DIAGNOSTIC_PRICE_ROWS if (row := _asset_price_row(spec, feature_map)) is not None
    ]
    if not rows or not any(_asset_row_has_change(row) for row in rows):
        return None
    regime, regime_label, summary = _commodity_regime(rows)
    return {
        "label": "商品冲击诊断",
        "regime": regime,
        "regime_label": regime_label,
        "summary": summary,
        "rows": rows,
        "implications": _commodity_implications(regime),
        "invalidations": _commodity_invalidations(regime),
    }


def _fx_diagnostics(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = [row for spec in _FX_DIAGNOSTIC_ROWS if (row := _fx_diagnostic_row(spec, feature_map)) is not None]
    if not rows or not any(_asset_row_has_change(row) for row in rows):
        return None
    regime, regime_label, summary = _fx_regime(rows)
    return {
        "label": "美元压力诊断",
        "regime": regime,
        "regime_label": regime_label,
        "summary": summary,
        "rows": rows,
        "implications": _fx_implications(regime),
        "invalidations": _fx_invalidations(regime),
    }


def _crypto_diagnostics(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = [row for spec in _CRYPTO_DIAGNOSTIC_PRICE_ROWS if (row := _asset_price_row(spec, feature_map)) is not None]
    rows.extend(_crypto_derivative_rows(feature_map))
    if not rows or not any(_asset_row_has_change(row) for row in rows):
        return None
    regime, regime_label, summary = _crypto_regime(rows)
    return {
        "label": "加密 beta 诊断",
        "regime": regime,
        "regime_label": regime_label,
        "summary": summary,
        "rows": rows,
        "implications": _crypto_implications(regime),
        "invalidations": _crypto_invalidations(regime),
    }


def _crypto_derivative_rows(feature_map: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(row for spec in _CRYPTO_DERIVATIVE_OI_ROWS if (row := _crypto_oi_row(spec, feature_map)) is not None)
    rows.extend(
        row
        for spec in _CRYPTO_DERIVATIVE_AVERAGE_BP_ROWS
        if (row := _crypto_average_bp_row(spec, feature_map)) is not None
    )
    rows.extend(row for spec in _CRYPTO_DERIVATIVE_VOL_ROWS if (row := _crypto_vol_row(spec, feature_map)) is not None)
    return rows


def _crypto_oi_row(spec: Mapping[str, Any], feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    series_points = [
        points
        for concept_key in _string_list(spec.get("concept_keys"))
        if (points := _feature_points(_mapping(feature_map.get(concept_key))))
    ]
    if not series_points:
        return None
    current_date = max(points[-1][0] for points in series_points)
    current_value = _sum_points_at_or_before(series_points, current_date)
    if current_value is None:
        return None
    prior_value = _sum_points_at_or_before(series_points, current_date - timedelta(days=7))
    change_1w_pct = (
        _round_pct((current_value / prior_value - 1.0) * 100.0) if prior_value is not None and prior_value else None
    )
    status, status_label = _crypto_oi_status(change_1w_pct)
    return {
        "key": str(spec["key"]),
        "label": str(spec["label"]),
        "current_bn": _round_index(current_value / 1_000_000_000.0),
        "change_1w_pct": change_1w_pct,
        "status": status,
        "status_label": status_label,
    }


def _crypto_average_bp_row(spec: Mapping[str, Any], feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    values = [
        value
        for concept_key in _string_list(spec.get("concept_keys"))
        if (value := _latest_feature_map_value(feature_map, concept_key)) is not None
    ]
    if not values:
        return None
    current_bp = _round_bp((sum(values) / len(values)) * float(spec["scale_to_bp"]))
    status_kind = str(spec["status_kind"])
    if status_kind == "funding":
        status, status_label = _crypto_funding_status(current_bp)
    else:
        status, status_label = _crypto_basis_status(current_bp)
    return {
        "key": str(spec["key"]),
        "label": str(spec["label"]),
        "current_bp": current_bp,
        "status": status,
        "status_label": status_label,
    }


def _crypto_vol_row(spec: Mapping[str, Any], feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get(str(spec["concept_key"]))))
    if not points:
        return None
    current_date, current_value = points[-1]
    prior_value = _point_value_at_or_before(points, current_date - timedelta(days=7))
    change_1w_index = _round_index(current_value - prior_value) if prior_value is not None else None
    current_index = _round_index(current_value)
    status, status_label = _crypto_vol_status(current_index=current_index, change_1w_index=change_1w_index)
    return {
        "key": str(spec["key"]),
        "label": str(spec["label"]),
        "current_index": current_index,
        "change_1w_index": change_1w_index,
        "status": status,
        "status_label": status_label,
    }


def _sum_points_at_or_before(series_points: Sequence[Sequence[tuple[date, float]]], target_date: date) -> float | None:
    values = [
        value for points in series_points if (value := _point_value_at_or_before(points, target_date)) is not None
    ]
    return sum(values) if values else None


def _latest_feature_map_value(feature_map: Mapping[str, Any], concept_key: str) -> float | None:
    points = _feature_points(_mapping(feature_map.get(concept_key)))
    return points[-1][1] if points else None


def _crypto_oi_status(change_1w_pct: float | None) -> tuple[str, str]:
    if change_1w_pct is not None and change_1w_pct >= 8.0:
        return "leverage_expanding", "杠杆扩张"
    if change_1w_pct is not None and change_1w_pct <= -8.0:
        return "leverage_flush", "杠杆出清"
    return "leverage_stable", "杠杆平稳"


def _crypto_funding_status(current_bp: float) -> tuple[str, str]:
    if current_bp >= 5.0:
        return "funding_hot", "多头拥挤"
    if current_bp <= -2.0:
        return "funding_negative", "空头付费"
    return "funding_neutral", "资金费率中性"


def _crypto_basis_status(current_bp: float) -> tuple[str, str]:
    if current_bp >= 75.0:
        return "basis_rich", "正基差"
    if current_bp <= -25.0:
        return "basis_backwardation", "贴水"
    return "basis_neutral", "基差中性"


def _crypto_vol_status(*, current_index: float, change_1w_index: float | None) -> tuple[str, str]:
    if current_index >= 65.0 or (change_1w_index is not None and change_1w_index >= 8.0):
        return "vol_hot", "波动升温"
    if current_index <= 45.0 and (change_1w_index is None or change_1w_index <= -5.0):
        return "vol_relief", "波动回落"
    return "vol_neutral", "波动中性"


def _equity_positioning_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("positioning:sp500_net_noncommercial")))
    if not points:
        return None
    current_date, current_value = points[-1]
    prior_week_value = _point_value_at_or_before(points, current_date - timedelta(days=7))
    prior_month_value = _point_value_at_or_before(points, current_date - timedelta(days=30))
    current_k = _round_k(current_value / 1_000.0)
    change_1w_k = _round_k((current_value - prior_week_value) / 1_000.0) if prior_week_value is not None else None
    change_1m_k = _round_k((current_value - prior_month_value) / 1_000.0) if prior_month_value is not None else None
    status, status_label = _equity_positioning_status(current_k=current_k, change_1w_k=change_1w_k)
    return {
        "key": "sp500_positioning",
        "label": "CFTC S&P 净投机",
        "current_k": current_k,
        "change_1w_k": change_1w_k,
        "change_1m_k": change_1m_k,
        "status": status,
        "status_label": status_label,
    }


def _asset_price_row(spec: Mapping[str, str], feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get(spec["concept_key"])))
    if not points:
        return None
    current_date, _current_value = points[-1]
    row: dict[str, Any] = {
        "key": spec["key"],
        "label": spec["label"],
    }
    for _window_label, field_name, days in _ASSET_CHANGE_WINDOWS:
        change_pct = _price_return_pct(points, current_date=current_date, days=days)
        row[field_name] = _round_pct(change_pct) if change_pct is not None else None
    status, status_label = _asset_price_status(
        kind=spec["kind"],
        change_1w_pct=_number(row.get("change_1w_pct")),
        change_1m_pct=_number(row.get("change_1m_pct")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _fx_diagnostic_row(spec: Mapping[str, str], feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    if spec.get("kind"):
        return _asset_price_row(spec, feature_map)

    points = _feature_points(_mapping(feature_map.get(spec["concept_key"])))
    if not points:
        return None
    current_date, _current_value = points[-1]
    row: dict[str, Any] = {
        "key": spec["key"],
        "label": spec["label"],
    }
    for _window_label, field_name, days in _ASSET_CHANGE_WINDOWS:
        change_pct = _price_return_pct(points, current_date=current_date, days=days)
        row[field_name] = _round_pct(change_pct) if change_pct is not None else None
    status, status_label = _fx_pair_status(
        usd_direction=spec["usd_direction"],
        change_1w_pct=_number(row.get("change_1w_pct")),
        change_1m_pct=_number(row.get("change_1m_pct")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _asset_credit_oas_row(spec: Mapping[str, str], feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get(spec["concept_key"])))
    if not points:
        return None
    current_date, current_value = points[-1]
    row: dict[str, Any] = {
        "key": spec["key"],
        "label": spec["label"],
        "current_bp": _round_bp(current_value * 100.0),
    }
    for _window_label, field_name, days in _CREDIT_CHANGE_WINDOWS[:2]:
        prior_value = _point_value_at_or_before(points, current_date - timedelta(days=days))
        row[field_name] = _round_bp((current_value - prior_value) * 100.0) if prior_value is not None else None
    status, status_label = _asset_hy_oas_status(_number(row.get("change_1w_bp")))
    row["status"] = status
    row["status_label"] = status_label
    return row


def _asset_vix_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("vol:vix")))
    if not points:
        return None
    current_date, current_value = points[-1]
    row: dict[str, Any] = {
        "key": "vix",
        "label": "VIX",
        "current_index": _round_index(current_value),
    }
    for _window_label, field_name, days in _VOLATILITY_CHANGE_WINDOWS:
        prior_value = _point_value_at_or_before(points, current_date - timedelta(days=days))
        row[field_name] = _round_index(current_value - prior_value) if prior_value is not None else None
    status, status_label = _asset_vix_status(
        current_index=_number(row.get("current_index")) or 0.0,
        change_1w_index=_number(row.get("change_1w_index")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _asset_hy_oas_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("credit:hy_oas")))
    if not points:
        return None
    current_date, current_value = points[-1]
    row: dict[str, Any] = {
        "key": "hy_oas",
        "label": "HY OAS",
        "current_bp": _round_bp(current_value * 100.0),
    }
    for _window_label, field_name, days in _CREDIT_CHANGE_WINDOWS[:2]:
        prior_value = _point_value_at_or_before(points, current_date - timedelta(days=days))
        row[field_name] = _round_bp((current_value - prior_value) * 100.0) if prior_value is not None else None
    status, status_label = _asset_hy_oas_status(_number(row.get("change_1w_bp")))
    row["status"] = status
    row["status_label"] = status_label
    return row


def _asset_row_has_change(row: Mapping[str, Any]) -> bool:
    return any(
        _number(row.get(field_name)) is not None
        for field_name in (
            "change_1w_pct",
            "change_1m_pct",
            "change_1w_index",
            "change_1m_index",
            "change_1w_bp",
            "change_1m_bp",
            "change_1w_k",
            "change_1m_k",
        )
    )


def _equity_positioning_status(*, current_k: float, change_1w_k: float | None) -> tuple[str, str]:
    if current_k <= -100.0 or (change_1w_k is not None and change_1w_k <= -50.0):
        return "positioning_defensive", "仓位防守"
    if current_k >= 100.0 or (change_1w_k is not None and change_1w_k >= 50.0):
        return "positioning_chase", "仓位追多"
    return "positioning_neutral", "仓位中性"


def _asset_price_status(*, kind: str, change_1w_pct: float | None, change_1m_pct: float | None) -> tuple[str, str]:
    change = change_1w_pct if change_1w_pct is not None else change_1m_pct
    if change is None:
        return "insufficient_history", "样本不足"
    if kind == "risk":
        if change <= -1.0:
            return "risk_off", "风险降温"
        if change >= 1.0:
            return "risk_on", "风险回暖"
        return "risk_neutral", "风险震荡"
    if kind == "duration":
        if change <= -1.0:
            return "duration_pressure", "久期承压"
        if change >= 1.0:
            return "duration_bid", "久期修复"
        return "duration_neutral", "久期中性"
    if kind == "dollar":
        if change >= 0.5:
            return "dollar_up", "美元走强"
        if change <= -0.5:
            return "dollar_down", "美元走弱"
        return "dollar_neutral", "美元震荡"
    if kind == "energy":
        if change >= 2.0:
            return "energy_up", "能源上行"
        if change <= -2.0:
            return "energy_down", "能源下行"
        return "energy_neutral", "能源震荡"
    if kind == "crypto":
        if change <= -3.0:
            return "crypto_beta_down", "加密降温"
        if change >= 3.0:
            return "crypto_beta_up", "加密升温"
        return "crypto_beta_neutral", "加密震荡"
    if kind == "credit":
        if change <= -0.5:
            return "credit_beta_down", "信用承压"
        if change >= 0.5:
            return "credit_beta_up", "信用修复"
        return "credit_beta_neutral", "信用震荡"
    if kind == "precious":
        if change <= -1.0:
            return "precious_down", "贵金属回落"
        if change >= 1.0:
            return "precious_bid", "贵金属走强"
        return "precious_neutral", "贵金属震荡"
    if kind == "industrial":
        if change <= -1.0:
            return "industrial_down", "工业金属走弱"
        if change >= 1.0:
            return "industrial_bid", "工业金属走强"
        return "industrial_neutral", "工业金属震荡"
    return "neutral", "中性"


def _fx_pair_status(*, usd_direction: str, change_1w_pct: float | None, change_1m_pct: float | None) -> tuple[str, str]:
    change = change_1w_pct if change_1w_pct is not None else change_1m_pct
    if change is None:
        return "insufficient_history", "样本不足"
    usd_pressure = -change if usd_direction == "inverse" else change
    if usd_pressure >= 0.5:
        return "usd_up", "美元走强"
    if usd_pressure <= -0.5:
        return "usd_down", "美元走弱"
    return "fx_neutral", "汇率震荡"


def _asset_vix_status(*, current_index: float, change_1w_index: float | None) -> tuple[str, str]:
    change = change_1w_index if change_1w_index is not None else 0.0
    if current_index >= 30.0 or change >= 5.0:
        return "vol_stress", "波动压力"
    if current_index >= 20.0 or change >= 2.0:
        return "vol_up", "波动升温"
    if change <= -2.0 and current_index < 20.0:
        return "vol_down", "波动回落"
    return "vol_neutral", "波动中性"


def _asset_hy_oas_status(change_1w_bp: float | None) -> tuple[str, str]:
    if change_1w_bp is None:
        return "credit_stable", "信用稳定"
    if change_1w_bp >= 10.0:
        return "credit_widening", "信用走阔"
    if change_1w_bp <= -10.0:
        return "credit_tightening", "信用收窄"
    return "credit_stable", "信用稳定"


def _asset_regime(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    spx = _asset_row(rows, "spx")
    tlt = _asset_row(rows, "tlt")
    dxy = _asset_row(rows, "dxy")
    wti = _asset_row(rows, "wti")
    btc = _asset_row(rows, "btc")
    vix = _asset_row(rows, "vix")
    hy_oas = _asset_row(rows, "hy_oas")
    spx_1w = _number(spx.get("change_1w_pct")) or 0.0
    tlt_1w = _number(tlt.get("change_1w_pct")) or 0.0
    dxy_1w = _number(dxy.get("change_1w_pct")) or 0.0
    wti_1w = _number(wti.get("change_1w_pct")) or 0.0
    btc_1w = _number(btc.get("change_1w_pct")) or 0.0
    vix_change_1w = _number(vix.get("change_1w_index")) or 0.0
    hy_change_1w = _number(hy_oas.get("change_1w_bp")) or 0.0
    if spx_1w <= -1.0 and tlt_1w <= -1.0 and dxy_1w >= 0.5 and wti_1w >= 2.0:
        return (
            "stagflation_shock",
            "滞胀冲击",
            "跨资产主线偏滞胀冲击：股债双杀、美元与能源走强，风险资产需要降档。",
        )
    if spx_1w <= -1.0 and (vix_change_1w >= 2.0 or hy_change_1w >= 10.0 or btc_1w <= -3.0):
        return (
            "risk_off",
            "Risk-off",
            "跨资产主线偏 risk-off：权益走弱并伴随波动、信用或加密 beta 降温。",
        )
    if spx_1w >= 1.0 and btc_1w >= 2.0 and hy_change_1w < 10.0 and dxy_1w < 0.5:
        return (
            "risk_on",
            "Risk-on",
            "跨资产主线偏 risk-on：权益和加密同步修复，美元与信用没有显著背离。",
        )
    return (
        "mixed",
        "分化",
        "跨资产信号分化：权益、久期、美元、能源、信用和波动率尚未形成同向主线。",
    )


def _equity_regime(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    spx = _asset_row(rows, "spx")
    ndx = _asset_row(rows, "ndx")
    rut = _asset_row(rows, "rut")
    qqq = _asset_row(rows, "qqq")
    iwm = _asset_row(rows, "iwm")
    positioning = _asset_row(rows, "sp500_positioning")
    spx_1w = _number(spx.get("change_1w_pct")) or 0.0
    ndx_1w = _number(ndx.get("change_1w_pct")) or 0.0
    rut_1w = _number(rut.get("change_1w_pct")) or 0.0
    qqq_1w = _number(qqq.get("change_1w_pct")) or 0.0
    iwm_1w = _number(iwm.get("change_1w_pct")) or 0.0
    positioning_1w = _number(positioning.get("change_1w_k")) or 0.0
    if spx_1w <= -2.0 and (ndx_1w <= -2.0 or qqq_1w <= -2.0) and (rut_1w <= -3.0 or iwm_1w <= -3.0):
        return (
            "equity_risk_off",
            "美股降温",
            "美股风险偏好走弱：大盘和成长承压，小盘/高 beta 未确认，风险资产需要降档。",
        )
    if spx_1w >= 2.0 and (ndx_1w >= 2.0 or qqq_1w >= 2.0) and (rut_1w >= 2.0 or iwm_1w >= 2.0):
        return (
            "equity_broad_risk_on",
            "广谱 risk-on",
            "美股风险偏好广谱修复：大盘、成长和小盘同步上行，风险资产 beta 获得确认。",
        )
    if spx_1w >= 1.0 and (ndx_1w >= 1.0 or qqq_1w >= 1.0) and (rut_1w <= -1.0 or iwm_1w <= -1.0):
        return (
            "mega_cap_narrowing",
            "龙头收窄",
            "美股上涨集中在大盘/成长龙头，小盘未确认，risk-on 质量需要打折。",
        )
    if positioning_1w <= -50.0:
        return (
            "positioning_defensive",
            "仓位防守",
            "CFTC S&P 净投机仓位转防守，美股价格确认不足时不宜放大 beta。",
        )
    return (
        "equity_mixed",
        "美股分化",
        "美股内部信号分化：等待 SPX、NDX、RUT 与 ETF 代理给出同向确认。",
    )


def _bond_regime(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    tlt = _asset_row(rows, "tlt")
    ief = _asset_row(rows, "ief")
    lqd = _asset_row(rows, "lqd")
    hyg = _asset_row(rows, "hyg")
    hy_oas = _asset_row(rows, "hy_oas")
    ig_oas = _asset_row(rows, "ig_oas")
    tlt_1w = _number(tlt.get("change_1w_pct")) or 0.0
    ief_1w = _number(ief.get("change_1w_pct")) or 0.0
    lqd_1w = _number(lqd.get("change_1w_pct")) or 0.0
    hyg_1w = _number(hyg.get("change_1w_pct")) or 0.0
    hy_change_1w = _number(hy_oas.get("change_1w_bp")) or 0.0
    ig_change_1w = _number(ig_oas.get("change_1w_bp")) or 0.0
    hyg_underperforms_lqd = hyg_1w <= lqd_1w - 1.0
    if tlt_1w <= -2.0 and (hyg_underperforms_lqd or hy_change_1w >= 10.0) and ig_change_1w >= 5.0:
        return (
            "bond_credit_pressure",
            "信用久期双压",
            "债券横截面偏防守：长久期回撤且 HYG 跑输 LQD，信用利差同步走阔。",
        )
    if tlt_1w >= 1.0 and ief_1w >= 0.5 and hy_change_1w < 10.0:
        return (
            "duration_bid",
            "久期修复",
            "债券横截面偏久期修复：TLT/IEF 同步走强，信用利差未明显背离。",
        )
    if hyg_1w >= 1.0 and lqd_1w >= 0.5 and hy_change_1w <= -10.0:
        return (
            "credit_relief",
            "信用修复",
            "债券横截面偏信用修复：HYG/LQD 同步走强，HY OAS 收窄确认风险偏好。",
        )
    if tlt_1w <= -2.0 and ief_1w <= -1.0:
        return (
            "duration_pressure",
            "久期承压",
            "债券横截面偏久期承压：长端和中端债券 ETF 同步回撤，利率压力仍在。",
        )
    return (
        "bond_mixed",
        "债券分化",
        "债券横截面分化：等待 TLT/IEF、LQD/HYG 与 HY/IG OAS 给出同向确认。",
    )


def _commodity_regime(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    wti = _asset_row(rows, "wti")
    brent = _asset_row(rows, "brent")
    natgas = _asset_row(rows, "natgas")
    gold = _asset_row(rows, "gold")
    copper = _asset_row(rows, "copper")
    wti_1w = _number(wti.get("change_1w_pct")) or 0.0
    brent_1w = _number(brent.get("change_1w_pct")) or 0.0
    natgas_1w = _number(natgas.get("change_1w_pct")) or 0.0
    gold_1w = _number(gold.get("change_1w_pct")) or 0.0
    copper_1w = _number(copper.get("change_1w_pct")) or 0.0
    if wti_1w >= 5.0 and brent_1w >= 5.0 and natgas_1w >= 10.0:
        return (
            "energy_inflation_shock",
            "能源通胀冲击",
            "商品主线偏能源通胀冲击：原油和天然气同步上行，铜确认需求，贵金属未给防守确认。",
        )
    if wti_1w <= -5.0 and brent_1w <= -5.0 and natgas_1w <= -10.0:
        return (
            "energy_deflation_relief",
            "能源通胀缓和",
            "商品主线偏能源通胀缓和：原油和天然气同步回落，通胀压力边际降温。",
        )
    if gold_1w >= 2.0 and copper_1w <= -2.0:
        return (
            "defensive_metal_bid",
            "防守金属",
            "商品主线偏防守：黄金走强但铜走弱，市场更像避险而非需求扩张。",
        )
    if copper_1w >= 3.0 and wti_1w >= 0.0:
        return (
            "cyclical_commodity_bid",
            "周期商品走强",
            "商品主线偏周期走强：铜与能源获得需求确认，但需观察美元和实际利率压制。",
        )
    return (
        "commodity_mixed",
        "商品分化",
        "商品信号分化：能源、贵金属和工业金属尚未形成一致的通胀或增长主线。",
    )


def _fx_regime(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    dxy = _asset_row(rows, "dxy")
    broad_dollar = _asset_row(rows, "broad_dollar")
    eurusd = _asset_row(rows, "eurusd")
    usdjpy = _asset_row(rows, "usdjpy")
    usdcny = _asset_row(rows, "usdcny")
    uup = _asset_row(rows, "uup")
    dxy_1w = _number(dxy.get("change_1w_pct")) or 0.0
    broad_1w = _number(broad_dollar.get("change_1w_pct")) or 0.0
    eurusd_1w = _number(eurusd.get("change_1w_pct")) or 0.0
    usdjpy_1w = _number(usdjpy.get("change_1w_pct")) or 0.0
    usdcny_1w = _number(usdcny.get("change_1w_pct")) or 0.0
    uup_1w = _number(uup.get("change_1w_pct")) or 0.0
    if dxy_1w >= 1.0 and broad_1w >= 0.5 and eurusd_1w <= -1.0 and (usdjpy_1w >= 1.0 or usdcny_1w >= 0.5):
        return (
            "dollar_squeeze",
            "美元挤压",
            "美元压力偏紧：DXY 和广义美元走强，欧元、日元与人民币同步确认离岸美元需求。",
        )
    if dxy_1w <= -1.0 and broad_1w <= -0.5 and eurusd_1w >= 1.0 and (uup_1w <= -0.5 or usdcny_1w <= -0.5):
        return (
            "dollar_relief",
            "美元回落",
            "美元压力缓和：DXY 和广义美元走弱，非美货币与美元 ETF 同步确认风险资产获得缓冲。",
        )
    if dxy_1w >= 1.0 and (eurusd_1w >= 0.0 or usdjpy_1w <= 0.0):
        return (
            "dollar_index_divergence",
            "美元指数背离",
            "DXY 走强但主要货币对未同步确认，避免把单点美元指数当成离岸美元挤压。",
        )
    if dxy_1w <= -1.0 and (broad_1w >= 0.0 or usdcny_1w >= 0.5):
        return (
            "dollar_relief_divergence",
            "美元回落背离",
            "DXY 回落但广义美元或人民币未同步放松，风险资产不能只按美元指数回落交易。",
        )
    return (
        "fx_mixed",
        "外汇分化",
        "美元与主要货币对分化：等待 DXY、广义美元、EURUSD、USDJPY 与 USDCNY 同向确认。",
    )


def _crypto_regime(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    btc = _asset_row(rows, "btc")
    eth = _asset_row(rows, "eth")
    btc_1w = _number(btc.get("change_1w_pct")) or 0.0
    eth_1w = _number(eth.get("change_1w_pct")) or 0.0
    eth_underperforms = eth_1w <= btc_1w - 2.0
    spot_up = btc_1w >= 3.0 and eth_1w >= 3.0
    spot_down = btc_1w <= -3.0 and eth_1w <= -3.0
    oi_expanding = _has_row_status(rows, "leverage_expanding")
    oi_flush = _has_row_status(rows, "leverage_flush")
    funding_hot = _has_row_status(rows, "funding_hot")
    funding_negative = _has_row_status(rows, "funding_negative")
    basis_rich = _has_row_status(rows, "basis_rich")
    basis_backwardation = _has_row_status(rows, "basis_backwardation")
    vol_hot = _has_row_status(rows, "vol_hot")
    if spot_up and oi_expanding and (funding_hot or basis_rich):
        return (
            "crypto_leverage_chase",
            "加密杠杆追涨",
            "加密价格、OI、资金费率和基差同步走热，DVOL 升温，当前更像杠杆追涨而不是干净 beta。",
        )
    if spot_down and (oi_flush or funding_negative or basis_backwardation):
        return (
            "crypto_leverage_flush",
            "加密杠杆出清",
            "加密价格回撤并伴随 OI 收缩、负 funding 或贴水，杠杆正在出清，不能急着抄 beta。",
        )
    if vol_hot and (spot_down or funding_negative or basis_backwardation):
        return (
            "crypto_vol_stress",
            "加密波动压力",
            "DVOL 升温且衍生品定价转弱，加密 beta 的风险补偿正在恶化。",
        )
    if btc_1w <= -3.0 and eth_1w <= -3.0:
        return (
            "crypto_beta_unwind",
            "加密 beta 降温",
            "加密资产同步降温：BTC 和 ETH 单周回撤，ETH 跑输 BTC，宏观 risk-on 需要降档。",
        )
    if btc_1w >= 3.0 and eth_1w >= 3.0:
        return (
            "crypto_beta_risk_on",
            "加密 beta 升温",
            "加密资产同步升温：BTC 和 ETH 同步上行，风险偏好获得高 beta 确认。",
        )
    if btc_1w >= 3.0 and eth_underperforms:
        return (
            "btc_defensive_bid",
            "BTC 单边修复",
            "BTC 修复但 ETH 明显跑输，市场更像质量/流动性回补而非广谱加密 risk-on。",
        )
    if eth_1w >= 5.0 and btc_1w >= 0.0:
        return (
            "eth_high_beta_chase",
            "ETH 高 beta 追涨",
            "ETH 相对 BTC 加速，风险偏好更激进，但需要波动率和美元不背离。",
        )
    return (
        "crypto_mixed",
        "加密分化",
        "BTC 与 ETH 信号分化：等待双币种同向确认后再把加密当作宏观 beta 放大器。",
    )


def _has_row_status(rows: Sequence[Mapping[str, Any]], status: str) -> bool:
    return any(row.get("status") == status for row in rows)


def _asset_row(rows: Sequence[Mapping[str, Any]], key: str) -> Mapping[str, Any]:
    return next((row for row in rows if row.get("key") == key), {})


def _asset_implications(regime: str) -> list[str]:
    if regime == "stagflation_shock":
        return ["滞胀冲击：降低权益/加密 beta，保留美元、能源或现金防守表达。"]
    if regime == "risk_off":
        return ["Risk-off：降低权益、加密和信用 beta，等待波动率与信用压力回落。"]
    if regime == "risk_on":
        return ["Risk-on：可保留风险资产 beta，但需要信用不走阔、美元不重新走强确认。"]
    return ["跨资产分化：避免单点叙事，等待 SPX/TLT/DXY/WTI/BTC 与信用、波动率同向确认。"]


def _equity_implications(regime: str) -> list[str]:
    if regime == "equity_risk_off":
        return ["美股降温：降低股票、加密 beta 和高收益信用暴露，等待小盘和成长股修复。"]
    if regime == "equity_broad_risk_on":
        return ["广谱 risk-on：可以提高权益和加密 beta 权重，但仍需信用和波动率不背离。"]
    if regime == "mega_cap_narrowing":
        return ["龙头收窄：优先质量/大盘，降低小盘、高 beta 和拥挤成长追涨。"]
    if regime == "positioning_defensive":
        return ["仓位防守：价格没有广谱确认前，避免把单日反弹当成新趋势。"]
    return ["美股分化：保留核心风险暴露，等待 SPX、NDX、RUT 和 ETF 代理同向确认。"]


def _bond_implications(regime: str) -> list[str]:
    if regime == "bond_credit_pressure":
        return ["信用久期双压：降低 HYG/JNK 和长久期暴露，优先现金、短债或高质量信用。"]
    if regime == "duration_bid":
        return ["久期修复：可保留 TLT/IEF，但需要信用利差稳定确认不是衰退式买债。"]
    if regime == "credit_relief":
        return ["信用修复：可回补 HYG/LQD beta，但需要 HY OAS 持续收窄和 VIX 不背离。"]
    if regime == "duration_pressure":
        return ["久期承压：降低长久期债券暴露，优先短债或等待 10Y/30Y 利率压力回落。"]
    return ["债券分化：不要只看单个 ETF，等待久期、信用 ETF 和现金利差同向确认。"]


def _commodity_implications(regime: str) -> list[str]:
    if regime == "energy_inflation_shock":
        return ["能源通胀冲击：保留能源/美元受益表达，降低长久期和高估值风险资产。"]
    if regime == "energy_deflation_relief":
        return ["能源通胀缓和：长久期和消费风险可获得边际缓冲，但仍需需求数据确认。"]
    if regime == "defensive_metal_bid":
        return ["防守金属：优先黄金防守表达，降低周期和高 beta 商品追涨。"]
    if regime == "cyclical_commodity_bid":
        return ["周期商品走强：可保留铜/能源 beta，但需要美元不重新走强。"]
    return ["商品分化：等待能源、贵金属、铜和美元给出同向确认后再放大表达。"]


def _fx_implications(regime: str) -> list[str]:
    if regime == "dollar_squeeze":
        return ["美元挤压：降低新兴市场、商品进口国和高 beta 风险资产，保留美元现金或 UUP 防守。"]
    if regime == "dollar_relief":
        return ["美元回落：可给风险资产、商品和非美货币边际加分，但需要信用和波动率不背离。"]
    if regime == "dollar_index_divergence":
        return ["美元指数背离：避免只按 DXY 加仓美元，等待 EURUSD、USDJPY 和 USDCNY 方向确认。"]
    if regime == "dollar_relief_divergence":
        return ["美元回落背离：风险资产修复需要打折，优先观察广义美元和人民币是否跟随放松。"]
    return ["外汇分化：不放大单一美元叙事，等待 DXY、广义美元、主要货币对和 UUP 同向确认。"]


def _crypto_implications(regime: str) -> list[str]:
    if regime == "crypto_leverage_chase":
        return ["杠杆追涨：保留 BTC/ETH beta 要降低杠杆和追价，优先等待 funding、basis 或 DVOL 降温后再加仓。"]
    if regime == "crypto_leverage_flush":
        return ["杠杆出清：降低加密 beta，等待 OI 停止收缩、资金费率企稳和 BTC/ETH 价格重新确认。"]
    if regime == "crypto_vol_stress":
        return ["波动压力：减少短 gamma/高杠杆表达，等待 DVOL 回落或 basis 修复后再提高风险。"]
    if regime == "crypto_beta_unwind":
        return ["加密 beta 降温：降低 BTC/ETH 和高 beta 风险资产暴露，等待 BTC 稳定与 ETH 不再跑输。"]
    if regime == "crypto_beta_risk_on":
        return ["加密 beta 升温：可保留 BTC/ETH beta，但需要美元、波动率和信用不背离。"]
    if regime == "btc_defensive_bid":
        return ["BTC 单边修复：优先 BTC 或降低山寨 beta，等待 ETH 确认广谱风险偏好。"]
    if regime == "eth_high_beta_chase":
        return ["ETH 高 beta 追涨：控制仓位和止损，等待 BTC 跟随与美元压力不反扑。"]
    return ["加密分化：不把单币种波动当成宏观 risk-on，等待 BTC 与 ETH 同向确认。"]


def _asset_invalidations(regime: str) -> list[str]:
    if regime == "stagflation_shock":
        return ["若 SPX/BTC 修复且 DXY、WTI、VIX 同步回落，滞胀冲击读法降级。"]
    if regime == "risk_off":
        return ["若 SPX 修复、VIX 回落且 HY OAS 不再走阔，risk-off 读法降级。"]
    if regime == "risk_on":
        return ["若 DXY 重新走强、VIX 上行或 HY OAS 走阔，risk-on 读法失效。"]
    return ["若任一主链信号单周变化突破阈值，重新评估跨资产 regime。"]


def _equity_invalidations(regime: str) -> list[str]:
    if regime == "equity_risk_off":
        return ["若 SPX/NDX 1w 转正且 RUT/IWM 不再跑输，美股降温读法降级。"]
    if regime == "equity_broad_risk_on":
        return ["若 RUT/IWM 跑输超过 3% 或 CFTC 仓位单周转负，广谱 risk-on 读法降级。"]
    if regime == "mega_cap_narrowing":
        return ["若 RUT/IWM 1w 转正并追上 SPX/NDX，龙头收窄读法失效。"]
    if regime == "positioning_defensive":
        return ["若 CFTC S&P 净投机仓位转正且 SPX/NDX 同步上行，仓位防守读法降级。"]
    return ["若 SPX、NDX 或 RUT 单周变化超过 3%，重新评估美股内部主线。"]


def _bond_invalidations(regime: str) -> list[str]:
    if regime == "bond_credit_pressure":
        return ["若 TLT/IEF 1w 转正且 HYG 不再跑输 LQD，信用久期双压读法降级。"]
    if regime == "duration_bid":
        return ["若 TLT 重新单周转负或 HY OAS 走阔超过 10bp，久期修复读法降级。"]
    if regime == "credit_relief":
        return ["若 HYG 跑输 LQD 或 HY OAS 重新走阔，信用修复读法失效。"]
    if regime == "duration_pressure":
        return ["若 TLT/IEF 1w 转正且 10Y/30Y 收益率回落，久期承压读法降级。"]
    return ["若 TLT、HYG 或 HY OAS 单周突破阈值，重新评估债券横截面。"]


def _commodity_invalidations(regime: str) -> list[str]:
    if regime == "energy_inflation_shock":
        return ["若 WTI/Brent 1w 转负且 NatGas 回落，能源通胀冲击读法降级。"]
    if regime == "energy_deflation_relief":
        return ["若 WTI/Brent 重新单周上涨超过 5%，能源通胀缓和读法失效。"]
    if regime == "defensive_metal_bid":
        return ["若铜转强且黄金回落，防守金属读法降级。"]
    if regime == "cyclical_commodity_bid":
        return ["若铜单周转负或美元重新走强，周期商品走强读法降级。"]
    return ["若 WTI、Gold 或 Copper 单周突破阈值，重新评估商品主线。"]


def _fx_invalidations(regime: str) -> list[str]:
    if regime == "dollar_squeeze":
        return ["若 DXY/Broad USD 1w 转负且 EURUSD 修复，美元挤压读法降级。"]
    if regime == "dollar_relief":
        return ["若 DXY 或 Broad USD 重新走强且 USDJPY/USDCNY 上行，美元回落读法失效。"]
    if regime == "dollar_index_divergence":
        return ["若 EURUSD 转弱且 USDJPY/USDCNY 同步上行，美元指数背离读法失效。"]
    if regime == "dollar_relief_divergence":
        return ["若 Broad USD 与 USDCNY 同步回落，美元回落背离读法降级。"]
    return ["若 DXY、Broad USD 或 EURUSD 单周突破阈值，重新评估美元压力。"]


def _crypto_invalidations(regime: str) -> list[str]:
    if regime == "crypto_leverage_chase":
        return ["若 OI 收缩且 funding/basis 回落，加密杠杆追涨读法降级。"]
    if regime == "crypto_leverage_flush":
        return ["若 OI 止跌、funding 转正且 BTC/ETH 同步修复，加密杠杆出清读法降级。"]
    if regime == "crypto_vol_stress":
        return ["若 DVOL 回落且 basis/funding 修复，加密波动压力读法降级。"]
    if regime == "crypto_beta_unwind":
        return ["若 BTC/ETH 1w 转正且 ETH 不再跑输 BTC，加密降温读法降级。"]
    if regime == "crypto_beta_risk_on":
        return ["若 BTC 或 ETH 单周转负，或美元/波动率重新走强，加密升温读法降级。"]
    if regime == "btc_defensive_bid":
        return ["若 ETH 1w 追上 BTC 或 BTC 单周转负，BTC 单边修复读法失效。"]
    if regime == "eth_high_beta_chase":
        return ["若 ETH 单周转负或 BTC 不跟随，ETH 高 beta 追涨读法降级。"]
    return ["若 BTC 或 ETH 单周突破 5%，重新评估加密 beta。"]


def _policy_diagnostics(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    target_row = _policy_target_range_row(feature_map)
    effr_row = _policy_effr_position_row(feature_map)
    spread_rows = [
        row
        for row in (
            _policy_spread_row(
                key="effr_iorb_spread",
                label="EFFR-IORB",
                left_concept_key="fed:effr",
                right_concept_key="fed:iorb",
                feature_map=feature_map,
                status_fn=_policy_effr_iorb_status,
            ),
            _policy_spread_row(
                key="sofr_effr_spread",
                label="SOFR-EFFR",
                left_concept_key="liquidity:sofr",
                right_concept_key="fed:effr",
                feature_map=feature_map,
                status_fn=_policy_funding_status,
            ),
            _policy_spread_row(
                key="sofr_30d_effr_spread",
                label="SOFR 30D-EFFR",
                left_concept_key="fed:sofr_30d",
                right_concept_key="fed:effr",
                feature_map=feature_map,
                status_fn=_policy_funding_status,
            ),
            _policy_spread_row(
                key="dff_effr_spread",
                label="DFF-EFFR",
                left_concept_key="fed:dff",
                right_concept_key="fed:effr",
                feature_map=feature_map,
                status_fn=_policy_admin_spread_status,
            ),
            _policy_spread_row(
                key="obfr_effr_spread",
                label="OBFR-EFFR",
                left_concept_key="fed:obfr",
                right_concept_key="fed:effr",
                feature_map=feature_map,
                status_fn=_policy_unsecured_spread_status,
            ),
        )
        if row is not None
    ]
    volume_rows = [
        row
        for row in (
            _policy_volume_row(
                key="effr_volume",
                label="EFFR 成交量",
                concept_key="fed:effr_volume",
                feature_map=feature_map,
            ),
            _policy_volume_row(
                key="obfr_volume",
                label="OBFR 成交量",
                concept_key="fed:obfr_volume",
                feature_map=feature_map,
            ),
        )
        if row is not None
    ]
    if target_row is None or effr_row is None or not spread_rows:
        return None
    rows = [target_row, effr_row, *spread_rows, *volume_rows]
    regime, regime_label, summary = _policy_regime(rows)
    return {
        "label": "政策走廊诊断",
        "regime": regime,
        "regime_label": regime_label,
        "summary": summary,
        "rows": rows,
        "implications": _policy_implications(regime),
        "invalidations": _policy_invalidations(regime),
    }


def _yield_curve_diagnostics(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = [row for spread in _YIELD_CURVE_SPREADS if (row := _yield_curve_spread_row(spread, feature_map)) is not None]
    if not rows or not any(
        row.get(key) is not None for row in rows for _label, key, _days in _YIELD_CURVE_CHANGE_WINDOWS
    ):
        return None
    shape, shape_label, summary = _yield_curve_shape(rows, feature_map)
    diagnostics: dict[str, Any] = {
        "label": "曲线诊断",
        "shape": shape,
        "shape_label": shape_label,
        "summary": summary,
        "rows": rows,
        "implications": _yield_curve_implications(shape),
        "invalidations": _yield_curve_invalidations(shape),
    }
    spread_history = [
        history
        for spread in _YIELD_CURVE_SPREADS
        if (history := _yield_curve_spread_history(spread, feature_map)) is not None
    ]
    if spread_history:
        diagnostics["spread_history"] = spread_history
    tenor_comparison = [
        row for tenor in _YIELD_CURVE_TENORS if (row := _yield_curve_tenor_row(tenor, feature_map)) is not None
    ]
    if tenor_comparison:
        diagnostics["tenor_comparison"] = tenor_comparison
    return diagnostics


def _real_rate_diagnostics(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    real_yield_rows = [
        row
        for spec in _REAL_RATE_REAL_ROWS
        if (row := _real_rate_row(spec, feature_map, status_fn=_real_rate_real_status)) is not None
    ]
    inflation_rows = [
        row
        for spec in _REAL_RATE_INFLATION_ROWS
        if (row := _real_rate_row(spec, feature_map, status_fn=_real_rate_inflation_status)) is not None
    ]
    if not real_yield_rows or not any(_real_rate_row_has_change(row) for row in (*real_yield_rows, *inflation_rows)):
        return None
    regime, regime_label, summary = _real_rate_regime(real_yield_rows, inflation_rows)
    return {
        "label": "实际利率诊断",
        "regime": regime,
        "regime_label": regime_label,
        "summary": summary,
        "real_yield_rows": real_yield_rows,
        "inflation_rows": inflation_rows,
        "implications": _real_rate_implications(regime),
        "invalidations": _real_rate_invalidations(regime),
    }


def _credit_diagnostics(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = [row for spec in _CREDIT_OAS_ROWS if (row := _credit_oas_row(spec, feature_map)) is not None]
    tail_row = _credit_tail_row(feature_map)
    if tail_row is not None:
        rows.append(tail_row)
    etf_row = _credit_etf_relative_row(feature_map)
    if etf_row is not None:
        rows.append(etf_row)
    conditions_row = _credit_financial_conditions_row(feature_map)
    if conditions_row is not None:
        rows.append(conditions_row)
    sloos_row = _credit_sloos_row(feature_map)
    if sloos_row is not None:
        rows.append(sloos_row)
    if not rows or not any(_credit_row_has_change(row) for row in rows):
        return None
    regime, regime_label, summary = _credit_regime(rows)
    return {
        "label": "信用压力诊断",
        "regime": regime,
        "regime_label": regime_label,
        "summary": summary,
        "rows": rows,
        "implications": _credit_implications(regime),
        "invalidations": _credit_invalidations(regime),
    }


def _volatility_diagnostics(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = [
        row
        for row in (
            _volatility_index_row(
                key="vix_spot",
                label="VIX 现货",
                concept_key="vol:vix",
                feature_map=feature_map,
            ),
            _volatility_front_premium_row(
                feature_map,
                concept_key="vol:vix1d",
                key="vix1d_vix",
                label="VIX1D-VIX 当日溢价",
            ),
            _volatility_front_premium_row(
                feature_map,
                concept_key="vol:vix9d",
                key="vix9d_vix",
                label="VIX9D-VIX 近端溢价",
            ),
            _volatility_term_row(feature_map),
            _volatility_index_row(
                key="vvix",
                label="VVIX 波动率凸性",
                concept_key="vol:vvix",
                feature_map=feature_map,
                status_fn=_volatility_vvix_status,
            ),
            _volatility_index_row(
                key="skew",
                label="SKEW 尾部风险",
                concept_key="vol:skew",
                feature_map=feature_map,
                status_fn=_volatility_skew_status,
            ),
            _volatility_rates_vol_row(feature_map),
            _volatility_etf_relative_row(feature_map),
            _volatility_index_row(
                key="vxn",
                label="VXN 纳指波动率",
                concept_key="vol:vxn",
                feature_map=feature_map,
            ),
        )
        if row is not None
    ]
    if not rows or not any(_volatility_row_has_change(row) for row in rows):
        return None
    regime, regime_label, summary = _volatility_regime(rows)
    return {
        "label": "波动率诊断",
        "regime": regime,
        "regime_label": regime_label,
        "summary": summary,
        "rows": rows,
        "implications": _volatility_implications(regime),
        "invalidations": _volatility_invalidations(regime),
    }


def _liquidity_diagnostics(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = [
        row
        for row in (
            _liquidity_corridor_row(feature_map),
            _liquidity_repo_depth_row(feature_map),
            _liquidity_volume_row(feature_map),
            _liquidity_balance_row(
                key="on_rrp",
                label="RRP 缓冲",
                concept_key="liquidity:on_rrp",
                feature_map=feature_map,
                status_fn=_liquidity_rrp_status,
            ),
            _liquidity_balance_row(
                key="tga",
                label="TGA 财政现金",
                concept_key="liquidity:tga",
                feature_map=feature_map,
                status_fn=_liquidity_tga_status,
            ),
            _liquidity_net_row(feature_map),
        )
        if row is not None
    ]
    if not rows or not any(_liquidity_row_has_change(row) for row in rows):
        return None
    regime, regime_label, summary = _liquidity_regime(rows)
    return {
        "label": "流动性诊断",
        "regime": regime,
        "regime_label": regime_label,
        "summary": summary,
        "rows": rows,
        "implications": _liquidity_implications(regime),
        "invalidations": _liquidity_invalidations(regime),
    }


def _inflation_diagnostics(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = [
        row
        for row in (
            _inflation_yoy_row(
                key="cpi_yoy",
                label="CPI 同比",
                concept_key="inflation:cpi",
                feature_map=feature_map,
                pipeline=False,
            ),
            _inflation_yoy_row(
                key="core_cpi_yoy",
                label="核心 CPI 同比",
                concept_key="inflation:core_cpi",
                feature_map=feature_map,
                pipeline=False,
            ),
            _inflation_yoy_row(
                key="ppi_yoy",
                label="PPI 同比",
                concept_key="inflation:ppi",
                feature_map=feature_map,
                pipeline=True,
            ),
            _inflation_breakeven_row(feature_map),
        )
        if row is not None
    ]
    if not rows or not any(_inflation_row_has_change(row) for row in rows):
        return None
    regime, regime_label, summary = _inflation_regime(rows)
    return {
        "label": "通胀诊断",
        "regime": regime,
        "regime_label": regime_label,
        "summary": summary,
        "rows": rows,
        "implications": _inflation_implications(regime),
        "invalidations": _inflation_invalidations(regime),
    }


def _employment_diagnostics(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = [
        row
        for row in (
            _employment_unemployment_row(feature_map),
            _employment_payroll_row(feature_map),
            _employment_claims_row(feature_map),
            _employment_openings_row(feature_map),
            _employment_wage_row(feature_map),
        )
        if row is not None
    ]
    if not rows or not any(_employment_row_has_change(row) for row in rows):
        return None
    regime, regime_label, summary = _employment_regime(rows)
    return {
        "label": "就业诊断",
        "regime": regime,
        "regime_label": regime_label,
        "summary": summary,
        "rows": rows,
        "implications": _employment_implications(regime),
        "invalidations": _employment_invalidations(regime),
    }


def _growth_diagnostics(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = [
        row
        for row in (
            _growth_gdp_row(feature_map),
            _growth_gdpnow_row(feature_map),
            _growth_industrial_row(feature_map),
            _growth_housing_row(feature_map),
            _growth_consumption_row(
                key="real_pce_yoy",
                label="实际 PCE 同比",
                concept_key="consumer:pce_real",
                feature_map=feature_map,
                retail=False,
            ),
            _growth_consumption_row(
                key="retail_sales_yoy",
                label="零售销售同比",
                concept_key="consumer:retail_sales",
                feature_map=feature_map,
                retail=True,
            ),
        )
        if row is not None
    ]
    if not rows or not any(_growth_row_has_change(row) for row in rows):
        return None
    regime, regime_label, summary = _growth_regime(rows)
    return {
        "label": "增长诊断",
        "regime": regime,
        "regime_label": regime_label,
        "summary": summary,
        "rows": rows,
        "implications": _growth_implications(regime),
        "invalidations": _growth_invalidations(regime),
    }


def _growth_gdp_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("economy:gdp_real")))
    if not points:
        return None
    current_date = points[-1][0]
    current_yoy = _inflation_yoy_at_or_before(points, current_date)
    if current_yoy is None:
        return None
    prior_yoy = _inflation_yoy_at_or_before(points, current_date - timedelta(days=90))
    change_1q = _round_pct(current_yoy - prior_yoy) if prior_yoy is not None else None
    status, status_label = _growth_gdp_status(current_yoy_pct=current_yoy, change_1q_pct=change_1q)
    return {
        "key": "real_gdp_yoy",
        "label": "实际 GDP 同比",
        "current_yoy_pct": current_yoy,
        "change_1q_pct": change_1q,
        "status": status,
        "status_label": status_label,
    }


def _growth_gdpnow_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("economy:gdp_nowcast")))
    if not points:
        return None
    current_date, current_value = points[-1]
    prior_value = _point_value_at_or_before(points, current_date - timedelta(days=30))
    change_1m = _round_pct(current_value - prior_value) if prior_value is not None else None
    status, status_label = _growth_gdpnow_status(current_pct=current_value, change_1m_pct=change_1m)
    return {
        "key": "gdpnow_saar",
        "label": "GDPNow",
        "current_pct": _round_pct(current_value),
        "change_1m_pct": change_1m,
        "status": status,
        "status_label": status_label,
    }


def _growth_industrial_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    row = _growth_yoy_row(
        key="industrial_production_yoy",
        label="工业生产同比",
        concept_key="economy:industrial_production",
        feature_map=feature_map,
    )
    if row is None:
        return None
    status, status_label = _growth_industrial_status(
        current_yoy_pct=_number(row.get("current_yoy_pct")) or 0.0,
        change_1m_pct=_number(row.get("change_1m_pct")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _growth_consumption_row(
    *,
    key: str,
    label: str,
    concept_key: str,
    feature_map: Mapping[str, Any],
    retail: bool,
) -> dict[str, Any] | None:
    row = _growth_yoy_row(
        key=key,
        label=label,
        concept_key=concept_key,
        feature_map=feature_map,
    )
    if row is None:
        return None
    status, status_label = _growth_consumption_status(
        current_yoy_pct=_number(row.get("current_yoy_pct")) or 0.0,
        change_1m_pct=_number(row.get("change_1m_pct")),
        retail=retail,
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _growth_yoy_row(
    *,
    key: str,
    label: str,
    concept_key: str,
    feature_map: Mapping[str, Any],
    status_fn: Callable[[float, float | None], tuple[str, str]] | None = None,
) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get(concept_key)))
    if not points:
        return None
    current_date = points[-1][0]
    current_yoy = _inflation_yoy_at_or_before(points, current_date)
    if current_yoy is None:
        return None
    prior_yoy = _inflation_yoy_at_or_before(points, current_date - timedelta(days=30))
    change_1m = _round_pct(current_yoy - prior_yoy) if prior_yoy is not None else None
    return {
        "key": key,
        "label": label,
        "current_yoy_pct": current_yoy,
        "change_1m_pct": change_1m,
        "status": "stable",
        "status_label": "稳定",
    }


def _growth_housing_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("economy:housing_starts")))
    if not points:
        return None
    current_date, current_value = points[-1]
    prior_value = _point_value_at_or_before(points, current_date - timedelta(days=30))
    current_k = _housing_thousands(current_value)
    change_1m = _round_k(current_k - _housing_thousands(prior_value)) if prior_value is not None else None
    status, status_label = _growth_housing_status(current_m=_round_m(current_k / 1_000.0), change_1m_k=change_1m)
    return {
        "key": "housing_starts",
        "label": "住房开工",
        "current_m": _round_m(current_k / 1_000.0),
        "change_1m_k": change_1m,
        "status": status,
        "status_label": status_label,
    }


def _growth_row_has_change(row: Mapping[str, Any]) -> bool:
    return any(
        _number(row.get(field_name)) is not None for field_name in ("change_1q_pct", "change_1m_pct", "change_1m_k")
    )


def _growth_gdp_status(*, current_yoy_pct: float, change_1q_pct: float | None) -> tuple[str, str]:
    if current_yoy_pct <= 0.0:
        return "contracting", "收缩"
    if current_yoy_pct <= 2.0 or (change_1q_pct is not None and change_1q_pct <= -0.5):
        return "slowing", "放缓"
    if current_yoy_pct >= 2.5 and (change_1q_pct is None or change_1q_pct >= 0.0):
        return "resilient", "韧性"
    return "stable", "稳定"


def _growth_gdpnow_status(*, current_pct: float, change_1m_pct: float | None) -> tuple[str, str]:
    if current_pct <= 0.0:
        return "nowcast_contraction", "Nowcast 收缩"
    if change_1m_pct is not None and change_1m_pct <= -0.5:
        return "nowcast_cooling", "Nowcast 降温"
    if current_pct >= 2.5 and (change_1m_pct is None or change_1m_pct >= 0.0):
        return "nowcast_resilient", "Nowcast 韧性"
    return "nowcast_stable", "Nowcast 稳定"


def _growth_industrial_status(*, current_yoy_pct: float, change_1m_pct: float | None) -> tuple[str, str]:
    if current_yoy_pct < 0.0:
        return "contracting", "收缩"
    if change_1m_pct is not None and change_1m_pct <= -1.0:
        return "slowing", "放缓"
    if current_yoy_pct >= 2.0:
        return "expanding", "扩张"
    return "stable", "稳定"


def _growth_consumption_status(
    *,
    current_yoy_pct: float,
    change_1m_pct: float | None,
    retail: bool,
) -> tuple[str, str]:
    if current_yoy_pct <= 1.5 or (change_1m_pct is not None and change_1m_pct <= -0.8):
        return ("demand_cooling", "需求降温") if retail else ("consumption_cooling", "消费降温")
    if current_yoy_pct >= 3.0:
        return ("demand_resilient", "需求韧性") if retail else ("consumption_resilient", "消费韧性")
    return "stable", "稳定"


def _growth_housing_status(*, current_m: float, change_1m_k: float | None) -> tuple[str, str]:
    if current_m <= 1.2 or (change_1m_k is not None and change_1m_k <= -100.0):
        return "housing_drag", "地产拖累"
    if change_1m_k is not None and change_1m_k >= 100.0:
        return "housing_rebound", "地产修复"
    return "stable", "稳定"


def _growth_regime(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    gdp = next((row for row in rows if row.get("key") == "real_gdp_yoy"), {})
    industrial = next((row for row in rows if row.get("key") == "industrial_production_yoy"), {})
    housing = next((row for row in rows if row.get("key") == "housing_starts"), {})
    pce = next((row for row in rows if row.get("key") == "real_pce_yoy"), {})
    gdp_current = _number(gdp.get("current_yoy_pct")) or 0.0
    gdp_change_1q = _number(gdp.get("change_1q_pct")) or 0.0
    industrial_current = _number(industrial.get("current_yoy_pct")) or 0.0
    housing_change_1m = _number(housing.get("change_1m_k")) or 0.0
    pce_current = _number(pce.get("current_yoy_pct")) or 0.0
    pce_change_1m = _number(pce.get("change_1m_pct")) or 0.0
    if gdp_current <= 0.0 or (industrial_current <= -2.0 and pce_current <= 0.5):
        return (
            "recession_risk",
            "衰退风险",
            "增长进入衰退风险区：实际 GDP 或生产消费同步转弱，风险资产需要盈利下修折价。",
        )
    if gdp_change_1q <= -0.5 and (industrial_current < 0.0 or pce_change_1m <= -0.5 or housing_change_1m <= -100.0):
        return (
            "growth_cooling",
            "增长降温",
            "增长降温：实际 GDP、工业生产和消费动能同步放缓，风险资产盈利预期需要降级。",
        )
    if housing_change_1m <= -100.0:
        return (
            "housing_drag",
            "地产拖累",
            "地产拖累增长：住房开工快速下行，需观察消费和就业是否跟随走弱。",
        )
    if gdp_current >= 2.0 and pce_current >= 2.0 and industrial_current >= 0.0:
        return (
            "resilient",
            "增长韧性",
            "增长仍有韧性：实际 GDP 和消费维持扩张，风险资产盈利预期暂获支撑。",
        )
    return (
        "neutral",
        "中性",
        "增长信号中性：等待 GDP、工业生产、消费和地产同向确认。",
    )


def _growth_implications(regime: str) -> list[str]:
    if regime == "recession_risk":
        return ["衰退风险：降低周期、信用和高 beta 暴露，优先检查信用利差是否确认。"]
    if regime == "growth_cooling":
        return ["增长降温：降低盈利周期和高 beta 暴露，等待就业或消费重新确认。"]
    if regime == "housing_drag":
        return ["地产拖累：降低地产链、银行和小盘周期风险，等待住房开工或消费修复。"]
    if regime == "resilient":
        return ["增长韧性：风险资产盈利端仍有支撑，但若通胀粘性同步存在，降息预期需降级。"]
    return ["增长暂未给强方向：等待 GDP、工业生产、消费和地产同向确认。"]


def _growth_invalidations(regime: str) -> list[str]:
    if regime == "recession_risk":
        return ["若工业生产和实际 PCE 同比重新转正，衰退风险读法降级。"]
    if regime == "growth_cooling":
        return ["若实际 PCE 与工业生产同比回升且住房开工 1m 转正，增长降温读法降级。"]
    if regime == "housing_drag":
        return ["若住房开工 1m 转正且消费同比维持 2% 以上，地产拖累读法降级。"]
    if regime == "resilient":
        return ["若实际 GDP 同比跌破 2% 且工业生产转负，增长韧性读法失效。"]
    return ["若 GDP、工业生产或实际 PCE 出现单期明显反向变化，重新评估增长读法。"]


def _housing_thousands(value: float) -> float:
    absolute = abs(float(value))
    return float(value) / 1_000.0 if absolute >= 100_000.0 else float(value)


def _employment_unemployment_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("labor:unemployment")))
    if not points:
        return None
    current_date, current_value = points[-1]
    prior_value = _point_value_at_or_before(points, current_date - timedelta(days=30))
    change_1m = _round_pct(current_value - prior_value) if prior_value is not None else None
    status, status_label = _employment_unemployment_status(
        current_pct=current_value,
        change_1m_pct=change_1m,
    )
    return {
        "key": "unemployment_rate",
        "label": "失业率",
        "current_pct": _round_pct(current_value),
        "change_1m_pct": change_1m,
        "status": status,
        "status_label": status_label,
    }


def _employment_payroll_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("labor:payrolls")))
    if len(points) < 2:
        return None
    current_gain = _labor_thousands(points[-1][1] - points[-2][1])
    prior_gain = _labor_thousands(points[-2][1] - points[-3][1]) if len(points) >= 3 else None
    change_1m = _round_k(current_gain - prior_gain) if prior_gain is not None else None
    status, status_label = _employment_payroll_status(current_k=current_gain, change_1m_k=change_1m)
    return {
        "key": "payroll_gain",
        "label": "非农新增",
        "current_k": _round_k(current_gain),
        "change_1m_k": change_1m,
        "status": status,
        "status_label": status_label,
    }


def _employment_claims_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("labor:initial_claims")))
    if not points:
        return None
    current_date, current_value = points[-1]
    row: dict[str, Any] = {
        "key": "initial_claims",
        "label": "初请失业金",
        "current_k": _round_k(_labor_thousands(current_value)),
    }
    for suffix, days in _LIQUIDITY_CHANGE_WINDOWS:
        prior_value = _point_value_at_or_before(points, current_date - timedelta(days=days))
        row[f"change_{suffix}_k"] = (
            _round_k(_labor_thousands(current_value) - _labor_thousands(prior_value))
            if prior_value is not None
            else None
        )
    status, status_label = _employment_claims_status(
        current_k=_number(row.get("current_k")) or 0.0,
        change_1m_k=_number(row.get("change_1m_k")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _employment_openings_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("labor:job_openings")))
    if not points:
        return None
    current_date, current_value = points[-1]
    prior_value = _point_value_at_or_before(points, current_date - timedelta(days=30))
    current_m = _labor_millions(current_value)
    change_1m = _round_m(current_m - _labor_millions(prior_value)) if prior_value is not None else None
    status, status_label = _employment_openings_status(current_m=current_m, change_1m_m=change_1m)
    return {
        "key": "job_openings",
        "label": "职位空缺",
        "current_m": _round_m(current_m),
        "change_1m_m": change_1m,
        "status": status,
        "status_label": status_label,
    }


def _employment_wage_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("labor:avg_hourly_earnings")))
    if not points:
        return None
    current_date = points[-1][0]
    current_yoy = _inflation_yoy_at_or_before(points, current_date)
    if current_yoy is None:
        return None
    prior_yoy = _inflation_yoy_at_or_before(points, current_date - timedelta(days=30))
    change_1m = _round_pct(current_yoy - prior_yoy) if prior_yoy is not None else None
    status, status_label = _employment_wage_status(
        current_yoy_pct=current_yoy,
        change_1m_pct=change_1m,
    )
    return {
        "key": "wage_yoy",
        "label": "平均时薪同比",
        "current_yoy_pct": current_yoy,
        "change_1m_pct": change_1m,
        "status": status,
        "status_label": status_label,
    }


def _employment_row_has_change(row: Mapping[str, Any]) -> bool:
    return any(
        _number(row.get(field_name)) is not None
        for field_name in ("change_1m_pct", "change_1m_k", "change_1w_k", "change_1m_m")
    )


def _employment_unemployment_status(*, current_pct: float, change_1m_pct: float | None) -> tuple[str, str]:
    if current_pct >= 4.5 or (change_1m_pct is not None and change_1m_pct >= 0.2):
        return "deteriorating", "走弱"
    if change_1m_pct is not None and change_1m_pct <= -0.2:
        return "improving", "改善"
    if current_pct <= 4.0:
        return "tight", "偏紧"
    return "stable", "稳定"


def _employment_payroll_status(*, current_k: float, change_1m_k: float | None) -> tuple[str, str]:
    if current_k <= 100.0 or (change_1m_k is not None and change_1m_k <= -100.0):
        return "slowing", "放缓"
    if current_k >= 180.0:
        return "strong", "强劲"
    return "steady", "稳定"


def _employment_claims_status(*, current_k: float, change_1m_k: float | None) -> tuple[str, str]:
    if current_k >= 300.0 or (change_1m_k is not None and change_1m_k >= 20.0):
        return "claims_rising", "初请上行"
    if change_1m_k is not None and change_1m_k <= -20.0:
        return "claims_falling", "初请回落"
    return "stable", "稳定"


def _employment_openings_status(*, current_m: float, change_1m_m: float | None) -> tuple[str, str]:
    if current_m <= 7.0 or (change_1m_m is not None and change_1m_m <= -0.3):
        return "demand_cooling", "需求降温"
    if current_m >= 9.0:
        return "demand_tight", "需求偏紧"
    return "stable", "稳定"


def _employment_wage_status(*, current_yoy_pct: float, change_1m_pct: float | None) -> tuple[str, str]:
    if current_yoy_pct >= 4.5 and (change_1m_pct is None or change_1m_pct >= 0.0):
        return "wage_pressure", "工资压力"
    if change_1m_pct is not None and change_1m_pct <= -0.3:
        return "wage_cooling", "工资降温"
    return "stable", "稳定"


def _employment_regime(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    unemployment = next((row for row in rows if row.get("key") == "unemployment_rate"), {})
    payroll = next((row for row in rows if row.get("key") == "payroll_gain"), {})
    claims = next((row for row in rows if row.get("key") == "initial_claims"), {})
    wage = next((row for row in rows if row.get("key") == "wage_yoy"), {})
    unemployment_current = _number(unemployment.get("current_pct")) or 0.0
    unemployment_change_1m = _number(unemployment.get("change_1m_pct")) or 0.0
    payroll_current = _number(payroll.get("current_k")) or 0.0
    claims_current = _number(claims.get("current_k")) or 0.0
    claims_change_1m = _number(claims.get("change_1m_k")) or 0.0
    wage_current = _number(wage.get("current_yoy_pct")) or 0.0
    if unemployment_current >= 4.8 and claims_current >= 300.0:
        return (
            "labor_stress",
            "就业压力",
            "就业压力上升：失业率和初请同时处于压力区，风险资产需要增长风险折价。",
        )
    if unemployment_change_1m >= 0.2 and (payroll_current <= 100.0 or claims_change_1m >= 20.0):
        return (
            "labor_cooling",
            "就业降温",
            "就业降温：失业率与初请上行、非农动能放缓，增长风险开始压过软着陆叙事。",
        )
    if unemployment_current <= 4.0 and payroll_current >= 180.0 and wage_current >= 4.0:
        return (
            "labor_tight",
            "就业偏紧",
            "就业仍偏紧：非农和工资压力支撑更高更久的政策利率假设。",
        )
    if payroll_current >= 180.0 and claims_change_1m <= 0.0:
        return (
            "resilient",
            "就业韧性",
            "就业仍有韧性：增长尚未明显失速，风险资产需要继续观察工资和通胀确认。",
        )
    return (
        "neutral",
        "中性",
        "就业信号中性：等待非农、失业率、初请和工资同向确认。",
    )


def _employment_implications(regime: str) -> list[str]:
    if regime == "labor_stress":
        return ["就业压力：降低盈利敏感和信用 beta，优先检查信用利差是否跟随走阔。"]
    if regime == "labor_cooling":
        return ["就业降温：降低盈利周期和高 beta 置信度，降息交易需等待通胀同步配合。"]
    if regime == "labor_tight":
        return ["就业偏紧：降低抢跑降息交易，等待工资或失业率转弱确认。"]
    if regime == "resilient":
        return ["就业韧性：增长仍支撑风险资产，但若通胀粘性同步存在，降息预期需降级。"]
    return ["就业暂未给强方向：等待非农、初请、失业率和工资同向确认。"]


def _employment_invalidations(regime: str) -> list[str]:
    if regime == "labor_stress":
        return ["若初请回落至 240k 以下且失业率 1m 不再上行，就业压力读法降级。"]
    if regime == "labor_cooling":
        return ["若非农新增重新高于 180k 且初请 1m 回落超过 20k，就业降温读法降级。"]
    if regime == "labor_tight":
        return ["若非农新增低于 100k 或失业率 1m 上行超过 0.2pp，就业偏紧读法失效。"]
    if regime == "resilient":
        return ["若初请 1m 上行超过 20k 且非农低于 100k，就业韧性读法降级。"]
    return ["若非农、失业率或初请出现单月明显反向变化，重新评估就业读法。"]


def _labor_thousands(value: float) -> float:
    absolute = abs(float(value))
    return float(value) / 1_000.0 if absolute >= 10_000.0 else float(value)


def _labor_millions(value: float) -> float:
    absolute = abs(float(value))
    return float(value) / 1_000_000.0 if absolute >= 100_000.0 else float(value) / 1_000.0


def _round_k(value: float) -> float:
    rounded = round(float(value), 1)
    return 0.0 if rounded == 0 else rounded


def _round_m(value: float) -> float:
    rounded = round(float(value), 2)
    return 0.0 if rounded == 0 else rounded


def _inflation_yoy_row(
    *,
    key: str,
    label: str,
    concept_key: str,
    feature_map: Mapping[str, Any],
    pipeline: bool,
) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get(concept_key)))
    if not points:
        return None
    current_date = points[-1][0]
    current_yoy = _inflation_yoy_at_or_before(points, current_date)
    if current_yoy is None:
        return None
    prior_yoy = _inflation_yoy_at_or_before(points, current_date - timedelta(days=30))
    change_1m = _round_pct(current_yoy - prior_yoy) if prior_yoy is not None else None
    status, status_label = _inflation_yoy_status(
        current_yoy_pct=current_yoy,
        change_1m_pct=change_1m,
        pipeline=pipeline,
    )
    return {
        "key": key,
        "label": label,
        "current_yoy_pct": current_yoy,
        "change_1m_pct": change_1m,
        "status": status,
        "status_label": status_label,
    }


def _inflation_breakeven_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("inflation:10y_breakeven")))
    if not points:
        return None
    current_date, current_value = points[-1]
    row: dict[str, Any] = {
        "key": "breakeven_10y",
        "label": "10Y 通胀补偿",
        "current_pct": _round_pct(current_value),
    }
    for suffix, days in _LIQUIDITY_CHANGE_WINDOWS:
        prior_value = _point_value_at_or_before(points, current_date - timedelta(days=days))
        row[f"change_{suffix}_bp"] = (
            _round_bp((current_value - prior_value) * 100.0) if prior_value is not None else None
        )
    status, status_label = _inflation_breakeven_status(
        current_pct=_number(row.get("current_pct")) or 0.0,
        change_1m_bp=_number(row.get("change_1m_bp")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _inflation_yoy_at_or_before(points: Sequence[tuple[date, float]], target_date: date) -> float | None:
    current_value = _point_value_at_or_before(points, target_date)
    prior_value = _point_value_at_or_before(points, target_date - timedelta(days=365))
    if current_value is None or prior_value is None or prior_value == 0:
        return None
    return _round_pct((current_value / prior_value - 1.0) * 100.0)


def _inflation_row_has_change(row: Mapping[str, Any]) -> bool:
    return any(
        _number(row.get(field_name)) is not None for field_name in ("change_1m_pct", "change_1w_bp", "change_1m_bp")
    )


def _inflation_yoy_status(
    *,
    current_yoy_pct: float,
    change_1m_pct: float | None,
    pipeline: bool,
) -> tuple[str, str]:
    if pipeline and (current_yoy_pct >= 5.0 or (change_1m_pct is not None and change_1m_pct >= 0.5)):
        return "pipeline_pressure", "上游压力"
    if change_1m_pct is not None and change_1m_pct >= 0.3:
        return "accelerating", "加速"
    if change_1m_pct is not None and change_1m_pct <= -0.3:
        return "cooling", "降温"
    if current_yoy_pct >= 4.0:
        return "sticky", "粘性"
    return "contained", "温和"


def _inflation_breakeven_status(*, current_pct: float, change_1m_bp: float | None) -> tuple[str, str]:
    if current_pct >= 2.5 or (change_1m_bp is not None and change_1m_bp >= 10.0):
        return "expectation_pressure", "预期升温"
    if change_1m_bp is not None and change_1m_bp <= -10.0:
        return "expectation_relief", "预期降温"
    return "stable", "稳定"


def _inflation_regime(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    cpi = next((row for row in rows if row.get("key") == "cpi_yoy"), {})
    core_cpi = next((row for row in rows if row.get("key") == "core_cpi_yoy"), {})
    breakeven = next((row for row in rows if row.get("key") == "breakeven_10y"), {})
    cpi_change_1m = _number(cpi.get("change_1m_pct")) or 0.0
    core_current = _number(core_cpi.get("current_yoy_pct")) or 0.0
    core_change_1m = _number(core_cpi.get("change_1m_pct")) or 0.0
    breakeven_current = _number(breakeven.get("current_pct")) or 0.0
    breakeven_change_1m = _number(breakeven.get("change_1m_bp")) or 0.0
    if cpi_change_1m >= 0.3 and core_change_1m >= 0.3 and breakeven_change_1m >= 10.0:
        return (
            "reaccelerating",
            "通胀再加速",
            "通胀再加速：CPI/Core CPI 同比重新上行且通胀补偿走阔，降息交易需要降级。",
        )
    if core_current <= 3.0 and cpi_change_1m <= -0.3 and core_change_1m <= -0.3:
        return (
            "disinflation",
            "通胀降温",
            "通胀继续降温：核心通胀回落，降息交易可获得经济数据确认。",
        )
    if breakeven_current >= 2.5 or breakeven_change_1m >= 10.0:
        return (
            "expectation_pressure",
            "预期升温",
            "通胀预期升温：市场补偿走阔，实际利率与久期资产需要重新评估。",
        )
    if core_current >= 4.0:
        return (
            "sticky",
            "粘性通胀",
            "核心通胀仍有粘性：降息交易缺少通胀确认，高 beta 需要等待数据回落。",
        )
    return (
        "neutral",
        "中性",
        "通胀信号中性：等待 CPI、PCE 与通胀补偿同向确认。",
    )


def _inflation_implications(regime: str) -> list[str]:
    if regime == "reaccelerating":
        return ["通胀再加速：降低降息受益、长久期成长和高 beta 反弹置信度。"]
    if regime == "disinflation":
        return ["通胀降温：降息受益和长久期资产可获得经济数据确认。"]
    if regime == "expectation_pressure":
        return ["预期升温：降低长久期和估值敏感资产暴露，等待 breakeven 回落。"]
    if regime == "sticky":
        return ["粘性通胀：维持政策利率更高更久假设，降低抢跑降息交易。"]
    return ["通胀暂未给强方向：等待 CPI/Core PCE 与 breakeven 同向确认。"]


def _inflation_invalidations(regime: str) -> list[str]:
    if regime == "reaccelerating":
        return ["若核心 CPI 同比回落且 10Y 通胀补偿 1m 收窄超过 10bp，再加速读法降级。"]
    if regime == "disinflation":
        return ["若核心 CPI 同比重新上行或 breakeven 1m 走阔超过 10bp，降温读法失效。"]
    if regime == "expectation_pressure":
        return ["若 10Y 通胀补偿 1m 收窄超过 10bp，预期升温读法降级。"]
    if regime == "sticky":
        return ["若核心通胀跌破 3% 且 PCE 同步回落，粘性通胀读法降级。"]
    return ["若核心通胀或 breakeven 1m 明显上行，重新评估通胀压力。"]


def _liquidity_corridor_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    sofr_points = _feature_points(_mapping(feature_map.get("liquidity:sofr")))
    iorb_points = _feature_points(_mapping(feature_map.get("fed:iorb")))
    if not sofr_points or not iorb_points:
        return None
    current_date = min(sofr_points[-1][0], iorb_points[-1][0])
    current_spread = _spread_at_or_before(iorb_points, sofr_points, current_date)
    if current_spread is None:
        return None
    row: dict[str, Any] = {
        "key": "sofr_iorb",
        "label": "SOFR-IORB 走廊压力",
        "current_bp": _round_bp(current_spread * 100.0),
    }
    for suffix, days in _LIQUIDITY_CHANGE_WINDOWS:
        prior_spread = _spread_at_or_before(iorb_points, sofr_points, current_date - timedelta(days=days))
        row[f"change_{suffix}_bp"] = (
            _round_bp((current_spread - prior_spread) * 100.0) if prior_spread is not None else None
        )
    status, status_label = _liquidity_corridor_status(
        current_bp=_number(row.get("current_bp")) or 0.0,
        change_1w_bp=_number(row.get("change_1w_bp")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _liquidity_repo_depth_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    sofr_points = _feature_points(_mapping(feature_map.get("liquidity:sofr")))
    tgcr_points = _feature_points(_mapping(feature_map.get("liquidity:tgcr")))
    if not sofr_points or not tgcr_points:
        return None
    current_date = min(sofr_points[-1][0], tgcr_points[-1][0])
    current_spread = _spread_at_or_before(tgcr_points, sofr_points, current_date)
    if current_spread is None:
        return None
    row: dict[str, Any] = {
        "key": "sofr_tgcr",
        "label": "SOFR-TGCR 深度压力",
        "current_bp": _round_bp(current_spread * 100.0),
    }
    for suffix, days in _LIQUIDITY_CHANGE_WINDOWS:
        prior_spread = _spread_at_or_before(tgcr_points, sofr_points, current_date - timedelta(days=days))
        row[f"change_{suffix}_bp"] = (
            _round_bp((current_spread - prior_spread) * 100.0) if prior_spread is not None else None
        )
    status, status_label = _liquidity_repo_depth_status(
        current_bp=_number(row.get("current_bp")) or 0.0,
        change_1w_bp=_number(row.get("change_1w_bp")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _liquidity_volume_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("liquidity:sofr_volume")))
    if not points:
        return None
    current_date, current_value = points[-1]
    row: dict[str, Any] = {
        "key": "sofr_volume",
        "label": "SOFR 成交量",
        "current_bn": _round_bn(current_value),
    }
    for suffix, days in _LIQUIDITY_CHANGE_WINDOWS:
        prior_value = _point_value_at_or_before(points, current_date - timedelta(days=days))
        row[f"change_{suffix}_bn"] = _round_bn(current_value - prior_value) if prior_value is not None else None
    status, status_label = _liquidity_volume_status(
        change_1w_bn=_number(row.get("change_1w_bn")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _liquidity_balance_row(
    *,
    key: str,
    label: str,
    concept_key: str,
    feature_map: Mapping[str, Any],
    status_fn: Any,
) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get(concept_key)))
    if not points:
        return None
    current_date, current_value = points[-1]
    row: dict[str, Any] = {
        "key": key,
        "label": label,
        "current_bn": _round_bn(current_value),
    }
    for suffix, days in _LIQUIDITY_CHANGE_WINDOWS:
        prior_value = _point_value_at_or_before(points, current_date - timedelta(days=days))
        row[f"change_{suffix}_bn"] = _round_bn(current_value - prior_value) if prior_value is not None else None
    status, status_label = status_fn(
        current_bn=_number(row.get("current_bn")) or 0.0,
        change_1w_bn=_number(row.get("change_1w_bn")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _liquidity_net_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    fed_assets_points = _feature_points(_mapping(feature_map.get("liquidity:fed_assets")))
    rrp_points = _feature_points(_mapping(feature_map.get("liquidity:on_rrp")))
    tga_points = _feature_points(_mapping(feature_map.get("liquidity:tga")))
    if not fed_assets_points or not rrp_points or not tga_points:
        return None
    current_date = min(fed_assets_points[-1][0], rrp_points[-1][0], tga_points[-1][0])
    current_value = _net_liquidity_at_or_before(fed_assets_points, rrp_points, tga_points, current_date)
    if current_value is None:
        return None
    row: dict[str, Any] = {
        "key": "net_liquidity",
        "label": "净流动性",
        "current_trillion": _round_trillion(current_value),
    }
    for suffix, days in _LIQUIDITY_CHANGE_WINDOWS:
        prior_value = _net_liquidity_at_or_before(
            fed_assets_points,
            rrp_points,
            tga_points,
            current_date - timedelta(days=days),
        )
        row[f"change_{suffix}_bn"] = _round_bn(current_value - prior_value) if prior_value is not None else None
    status, status_label = _liquidity_net_status(_number(row.get("change_1w_bn")))
    row["status"] = status
    row["status_label"] = status_label
    return row


def _net_liquidity_at_or_before(
    fed_assets_points: Sequence[tuple[date, float]],
    rrp_points: Sequence[tuple[date, float]],
    tga_points: Sequence[tuple[date, float]],
    target_date: date,
) -> float | None:
    fed_assets = _point_value_at_or_before(fed_assets_points, target_date)
    rrp = _point_value_at_or_before(rrp_points, target_date)
    tga = _point_value_at_or_before(tga_points, target_date)
    if fed_assets is None or rrp is None or tga is None:
        return None
    return fed_assets - rrp - tga


def _liquidity_row_has_change(row: Mapping[str, Any]) -> bool:
    return any(
        _number(row.get(field_name)) is not None
        for field_name in ("change_1w_bp", "change_1m_bp", "change_1w_bn", "change_1m_bn")
    )


def _liquidity_corridor_status(*, current_bp: float, change_1w_bp: float | None) -> tuple[str, str]:
    if current_bp >= 5.0 or (change_1w_bp is not None and current_bp > 0.0 and change_1w_bp >= 5.0):
        return "corridor_pressure", "走廊压力"
    if current_bp <= 0.0:
        return "ample", "充裕"
    return "watch", "观察"


def _liquidity_repo_depth_status(*, current_bp: float, change_1w_bp: float | None) -> tuple[str, str]:
    if current_bp >= 5.0 or (change_1w_bp is not None and change_1w_bp >= 5.0):
        return "repo_depth_pressure", "Repo 深度压力"
    if current_bp <= 1.0:
        return "repo_depth_normal", "深度正常"
    return "repo_depth_watch", "观察"


def _liquidity_volume_status(*, change_1w_bn: float | None) -> tuple[str, str]:
    if change_1w_bn is None:
        return "insufficient_history", "样本不足"
    if change_1w_bn >= 100.0:
        return "volume_expansion", "成交放大"
    if change_1w_bn <= -100.0:
        return "volume_contraction", "成交收缩"
    return "stable", "稳定"


def _liquidity_rrp_status(*, current_bn: float, change_1w_bn: float | None) -> tuple[str, str]:
    if current_bn < 300.0:
        return "buffer_low", "缓冲偏低"
    if change_1w_bn is not None and change_1w_bn <= -50.0:
        return "buffer_drawdown", "缓冲消耗"
    return "buffer_ample", "缓冲充足"


def _liquidity_tga_status(*, current_bn: float, change_1w_bn: float | None) -> tuple[str, str]:
    if change_1w_bn is not None and change_1w_bn >= 50.0:
        return "treasury_drain", "财政抽水"
    if change_1w_bn is not None and change_1w_bn <= -50.0:
        return "treasury_injection", "财政注入"
    if current_bn >= 900.0:
        return "treasury_high", "TGA 偏高"
    return "stable", "稳定"


def _liquidity_net_status(change_1w_bn: float | None) -> tuple[str, str]:
    if change_1w_bn is None:
        return "insufficient_history", "样本不足"
    if change_1w_bn <= -50.0:
        return "net_drain", "净抽水"
    if change_1w_bn >= 50.0:
        return "net_injection", "净注入"
    return "stable", "稳定"


def _liquidity_regime(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    corridor = next((row for row in rows if row.get("key") == "sofr_iorb"), {})
    rrp = next((row for row in rows if row.get("key") == "on_rrp"), {})
    tga = next((row for row in rows if row.get("key") == "tga"), {})
    net = next((row for row in rows if row.get("key") == "net_liquidity"), {})
    corridor_current = _number(corridor.get("current_bp")) or 0.0
    net_change_1w = _number(net.get("change_1w_bn")) or 0.0
    tga_change_1w = _number(tga.get("change_1w_bn")) or 0.0
    rrp_current = _number(rrp.get("current_bn")) or 0.0
    if corridor_current >= 5.0 and net_change_1w <= -50.0:
        return (
            "corridor_drain",
            "走廊抽水",
            "流动性走廊抽水：SOFR 高于 IORB 且净流动性回落，高 beta 需要降杠杆。",
        )
    if rrp_current < 300.0 and net_change_1w <= 0.0:
        return (
            "buffer_low",
            "缓冲偏低",
            "RRP 缓冲偏低：财政或 QT 抽水更容易传导到准备金和融资市场。",
        )
    if tga_change_1w >= 100.0 or net_change_1w <= -100.0:
        return (
            "treasury_drain",
            "财政抽水",
            "财政现金或 QT 正在抽走净流动性，风险资产需要等待资金面确认。",
        )
    if net_change_1w >= 50.0:
        return (
            "liquidity_injection",
            "净注入",
            "净流动性回升：资金面给风险资产提供边际支持，但仍需信用和波动率确认。",
        )
    return (
        "neutral",
        "中性",
        "流动性信号中性：等待 SOFR-IORB、RRP、TGA 和净流动性同向确认。",
    )


def _liquidity_implications(regime: str) -> list[str]:
    if regime == "corridor_drain":
        return ["流动性抽水：降低高 beta、杠杆多头和融资敏感资产暴露。"]
    if regime == "buffer_low":
        return ["RRP 缓冲偏低：资金面冲击容错下降，优先控制融资敏感风险。"]
    if regime == "treasury_drain":
        return ["财政抽水：等待 TGA/RRP 或准备金改善前，降低追涨风险资产的置信度。"]
    if regime == "liquidity_injection":
        return ["净注入：risk-on 可以获得资金面确认，但需要波动率和信用不背离。"]
    return ["流动性暂未给强方向：等待 SOFR-IORB、RRP/TGA 和净流动性同向确认。"]


def _liquidity_invalidations(regime: str) -> list[str]:
    if regime == "corridor_drain":
        return ["若 SOFR-IORB 回落至 0bp 附近且净流动性 1w 转正，抽水读法降级。"]
    if regime == "buffer_low":
        return ["若 RRP 回升至 300B 以上且 SOFR-IORB 稳定，缓冲偏低读法降级。"]
    if regime == "treasury_drain":
        return ["若 TGA 回落且净流动性 1w 转正，财政抽水读法降级。"]
    if regime == "liquidity_injection":
        return ["若净流动性重新转负或 SOFR-IORB 走阔，净注入读法失效。"]
    return ["若 SOFR-IORB 上行超过 5bp 或净流动性 1w 下降超过 50B，重新评估流动性压力。"]


def _volatility_index_row(
    *,
    key: str,
    label: str,
    concept_key: str,
    feature_map: Mapping[str, Any],
    status_fn: Callable[..., tuple[str, str]] | None = None,
) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get(concept_key)))
    if not points:
        return None
    current_date, current_value = points[-1]
    row: dict[str, Any] = {
        "key": key,
        "label": label,
        "current_index": _round_index(current_value),
    }
    for _window_label, field_name, days in _VOLATILITY_CHANGE_WINDOWS:
        prior_value = _point_value_at_or_before(points, current_date - timedelta(days=days))
        row[field_name] = _round_index(current_value - prior_value) if prior_value is not None else None
    row_status_fn = status_fn or _volatility_index_status
    status, status_label = row_status_fn(
        current_index=_number(row.get("current_index")) or 0.0,
        change_1w_index=_number(row.get("change_1w_index")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _volatility_term_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    vix_points = _feature_points(_mapping(feature_map.get("vol:vix")))
    vix3m_points = _feature_points(_mapping(feature_map.get("vol:vix3m")))
    if not vix_points or not vix3m_points:
        return None
    current_date = min(vix_points[-1][0], vix3m_points[-1][0])
    current_spread = _spread_at_or_before(vix_points, vix3m_points, current_date)
    if current_spread is None:
        return None
    row: dict[str, Any] = {
        "key": "vix3m_vix",
        "label": "VIX3M-VIX 期限溢价",
        "current_points": _round_index(current_spread),
    }
    for _window_label, _index_field_name, days in _VOLATILITY_CHANGE_WINDOWS:
        prior_spread = _spread_at_or_before(vix_points, vix3m_points, current_date - timedelta(days=days))
        suffix = "1w" if days == 7 else "1m"
        row[f"change_{suffix}_points"] = (
            _round_index(current_spread - prior_spread) if prior_spread is not None else None
        )
    status, status_label = _volatility_term_status(_number(row.get("current_points")))
    row["status"] = status
    row["status_label"] = status_label
    return row


def _volatility_front_premium_row(
    feature_map: Mapping[str, Any],
    *,
    concept_key: str,
    key: str,
    label: str,
) -> dict[str, Any] | None:
    vix_points = _feature_points(_mapping(feature_map.get("vol:vix")))
    front_points = _feature_points(_mapping(feature_map.get(concept_key)))
    if not vix_points or not front_points:
        return None
    current_date = min(vix_points[-1][0], front_points[-1][0])
    current_spread = _spread_at_or_before(vix_points, front_points, current_date)
    if current_spread is None:
        return None
    row: dict[str, Any] = {
        "key": key,
        "label": label,
        "current_points": _round_index(current_spread),
    }
    for _window_label, _index_field_name, days in _VOLATILITY_CHANGE_WINDOWS:
        prior_spread = _spread_at_or_before(vix_points, front_points, current_date - timedelta(days=days))
        suffix = "1w" if days == 7 else "1m"
        row[f"change_{suffix}_points"] = (
            _round_index(current_spread - prior_spread) if prior_spread is not None else None
        )
    status, status_label = _volatility_front_premium_status(
        current_points=_number(row.get("current_points")),
        change_1w_points=_number(row.get("change_1w_points")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _volatility_etf_relative_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    vixy_points = _feature_points(_mapping(feature_map.get("asset:vixy")))
    vixm_points = _feature_points(_mapping(feature_map.get("asset:vixm")))
    if not vixy_points or not vixm_points:
        return None
    current_date = min(vixy_points[-1][0], vixm_points[-1][0])
    current_ratio = _ratio_at_or_before(vixy_points, vixm_points, current_date)
    if current_ratio is None:
        return None
    row: dict[str, Any] = {
        "key": "vixy_vixm",
        "label": "VIXY/VIXM 前端压力",
        "current_ratio": _round_ratio(current_ratio),
    }
    for _window_label, _index_field_name, days in _VOLATILITY_CHANGE_WINDOWS:
        suffix = "1w" if days == 7 else "1m"
        row[f"change_{suffix}_pct"] = _volatility_relative_return(vixy_points, vixm_points, current_date, days=days)
    status, status_label = _volatility_etf_status(_number(row.get("change_1w_pct")))
    row["status"] = status
    row["status_label"] = status_label
    return row


def _volatility_rates_vol_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("vol:move")))
    if not points:
        return None
    current_date, current_value = points[-1]
    row: dict[str, Any] = {
        "key": "move",
        "label": "MOVE 美债波动率",
        "current_index": _round_index(current_value),
    }
    for _window_label, field_name, days in _VOLATILITY_CHANGE_WINDOWS:
        prior_value = _point_value_at_or_before(points, current_date - timedelta(days=days))
        row[field_name] = _round_index(current_value - prior_value) if prior_value is not None else None
    status, status_label = _volatility_move_status(
        current_index=_number(row.get("current_index")) or 0.0,
        change_1w_index=_number(row.get("change_1w_index")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _volatility_relative_return(
    front_points: Sequence[tuple[date, float]],
    mid_points: Sequence[tuple[date, float]],
    current_date: date,
    *,
    days: int,
) -> float | None:
    front_current = _point_value_at_or_before(front_points, current_date)
    mid_current = _point_value_at_or_before(mid_points, current_date)
    front_prior = _point_value_at_or_before(front_points, current_date - timedelta(days=days))
    mid_prior = _point_value_at_or_before(mid_points, current_date - timedelta(days=days))
    if (
        front_current is None
        or mid_current is None
        or front_prior is None
        or mid_prior is None
        or front_prior == 0
        or mid_prior == 0
    ):
        return None
    front_return = (float(front_current) / float(front_prior) - 1.0) * 100.0
    mid_return = (float(mid_current) / float(mid_prior) - 1.0) * 100.0
    return _round_pct(front_return - mid_return)


def _ratio_at_or_before(
    front_points: Sequence[tuple[date, float]],
    back_points: Sequence[tuple[date, float]],
    target_date: date,
) -> float | None:
    front_value = _point_value_at_or_before(front_points, target_date)
    back_value = _point_value_at_or_before(back_points, target_date)
    if front_value is None or back_value is None or back_value == 0:
        return None
    return front_value / back_value


def _volatility_row_has_change(row: Mapping[str, Any]) -> bool:
    return any(
        _number(row.get(field_name)) is not None
        for field_name in (
            "change_1w_index",
            "change_1m_index",
            "change_1w_points",
            "change_1m_points",
            "change_1w_pct",
            "change_1m_pct",
        )
    )


def _volatility_index_status(
    *,
    current_index: float,
    change_1w_index: float | None,
) -> tuple[str, str]:
    if current_index >= 30.0:
        return "panic", "恐慌"
    if current_index >= 20.0:
        return "elevated", "偏高"
    if change_1w_index is not None and change_1w_index >= 5.0:
        return "repricing", "重新定价"
    return "normal", "正常"


def _volatility_term_status(current_points: float | None) -> tuple[str, str]:
    if current_points is None:
        return "insufficient_history", "样本不足"
    if current_points < 0.0:
        return "backwardation", "Backwardation"
    if current_points >= 3.0:
        return "contango", "Contango"
    return "flat", "期限平坦"


def _volatility_front_premium_status(
    *,
    current_points: float | None,
    change_1w_points: float | None,
) -> tuple[str, str]:
    if current_points is None:
        return "insufficient_history", "样本不足"
    if current_points >= 5.0 or (change_1w_points is not None and change_1w_points >= 4.0):
        return "front_event_stress", "事件压力"
    if current_points >= 2.0 or (change_1w_points is not None and change_1w_points >= 2.0):
        return "front_event_premium", "近端升温"
    if current_points <= -2.0:
        return "front_relief", "近端回落"
    return "normal", "正常"


def _volatility_etf_status(change_1w_pct: float | None) -> tuple[str, str]:
    if change_1w_pct is None:
        return "insufficient_history", "样本不足"
    if change_1w_pct >= 3.0:
        return "front_repricing", "前端升温"
    if change_1w_pct <= -3.0:
        return "front_relief", "前端回落"
    return "stable", "稳定"


def _volatility_move_status(
    *,
    current_index: float,
    change_1w_index: float | None,
) -> tuple[str, str]:
    if current_index >= 150.0:
        return "rates_vol_stress", "利率波动压力"
    if current_index >= 120.0 or (change_1w_index is not None and change_1w_index >= 15.0):
        return "rates_repricing", "利率重新定价"
    if current_index <= 80.0 and (change_1w_index is None or change_1w_index <= 0.0):
        return "normal", "正常"
    return "elevated", "偏高"


def _volatility_vvix_status(
    *,
    current_index: float,
    change_1w_index: float | None,
) -> tuple[str, str]:
    if current_index >= 120.0:
        return "convexity_stress", "凸性压力"
    if current_index >= 100.0 or (change_1w_index is not None and change_1w_index >= 10.0):
        return "convexity_repricing", "凸性升温"
    return "normal", "正常"


def _volatility_skew_status(
    *,
    current_index: float,
    change_1w_index: float | None,
) -> tuple[str, str]:
    if current_index >= 150.0:
        return "tail_hedging", "尾部对冲"
    if current_index >= 140.0 or (change_1w_index is not None and change_1w_index >= 5.0):
        return "tail_premium", "尾部溢价"
    return "normal", "正常"


def _volatility_regime(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    vix = next((row for row in rows if row.get("key") == "vix_spot"), {})
    front_rows = [row for row in rows if row.get("key") in {"vix1d_vix", "vix9d_vix"}]
    term = next((row for row in rows if row.get("key") == "vix3m_vix"), {})
    etf = next((row for row in rows if row.get("key") == "vixy_vixm"), {})
    move = next((row for row in rows if row.get("key") == "move"), {})
    vix_current = _number(vix.get("current_index")) or 0.0
    vix_change_1w = _number(vix.get("change_1w_index")) or 0.0
    front_current = max((_number(row.get("current_points")) or 0.0 for row in front_rows), default=0.0)
    front_change_1w = max((_number(row.get("change_1w_points")) or 0.0 for row in front_rows), default=0.0)
    term_current = _number(term.get("current_points")) or 0.0
    etf_change_1w = _number(etf.get("change_1w_pct")) or 0.0
    move_current = _number(move.get("current_index")) or 0.0
    move_change_1w = _number(move.get("change_1w_index")) or 0.0
    if vix_current >= 30.0 or term_current < 0.0:
        return (
            "backwardation_stress",
            "倒挂压力",
            "波动率进入倒挂压力：VIX 或期限结构提示去杠杆风险，优先降低风险暴露。",
        )
    if move_current >= 150.0:
        return (
            "rates_vol_stress",
            "利率波动升温",
            "MOVE 指示美债波动率压力：久期、信用和高估值资产需要同步降敏感度。",
        )
    if (
        front_current >= 2.0
        or front_change_1w >= 2.0
        or vix_change_1w >= 5.0
        or etf_change_1w >= 5.0
        or move_change_1w >= 15.0
    ):
        return (
            "front_repricing",
            "前端升温",
            "波动率前端重新定价：短端避险需求升温，高 beta 需要降杠杆。",
        )
    if term_current >= 3.0 and vix_current < 20.0:
        return (
            "carry_contango",
            "期限 Contango",
            "波动率处于 Contango：VIX 回落且远期仍有溢价，短期风险偏 carry。",
        )
    if vix_current >= 20.0:
        return (
            "elevated",
            "波动偏高",
            "波动率偏高但未倒挂：风险资产可以观察，但仓位需要保守。",
        )
    return (
        "neutral",
        "中性",
        "波动率信号中性：等待 VIX、MOVE、期限结构和期货代理同向确认。",
    )


def _volatility_implications(regime: str) -> list[str]:
    if regime == "carry_contango":
        return ["波动率 carry：风险资产可维持暴露，但不追杠杆，等待 VIX3M-VIX 收窄确认。"]
    if regime == "backwardation_stress":
        return ["波动率倒挂：优先降低高 beta 和杠杆多头，保留防守/对冲表达。"]
    if regime == "front_repricing":
        return ["前端升温：降低追涨风险资产，观察 VIX1D/VIX9D-VIX、VIXY/VIXM 与信用是否共振。"]
    if regime == "rates_vol_stress":
        return ["利率波动升温：降低长久期和高杠杆资产敏感度，观察信用利差是否跟随走阔。"]
    if regime == "elevated":
        return ["波动偏高：控制仓位和止损距离，等待 VIX 回到 carry 区间。"]
    return ["波动率暂未给强方向：等待 VIX、MOVE、VIX3M-VIX 与 VIXY/VIXM 同向确认。"]


def _volatility_invalidations(regime: str) -> list[str]:
    if regime == "carry_contango":
        return ["若 VIX3M-VIX 转负或 VIX 单周上行超过 5 点，carry 读法失效。"]
    if regime == "backwardation_stress":
        return ["若 VIX 回落至 20 以下且期限结构回到 Contango，倒挂压力降级。"]
    if regime == "front_repricing":
        return ["若 VIX1D/VIX9D-VIX 回落、VIXY/VIXM 相对表现回落且 VIX3M-VIX 走阔，前端升温读法降级。"]
    if regime == "rates_vol_stress":
        return ["若 MOVE 回落至 120 以下且信用未走阔，利率波动压力读法降级。"]
    if regime == "elevated":
        return ["若 VIX 回落至 18 以下且期限结构维持 Contango，波动偏高读法降级。"]
    return ["若 VIX 单周上行超过 5 点或期限结构转负，重新评估波动率压力。"]


def _credit_oas_row(spec: Mapping[str, str], feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get(spec["concept_key"])))
    if not points:
        return None
    current_date, current_value = points[-1]
    row: dict[str, Any] = {
        "key": spec["key"],
        "label": spec["label"],
        "current_bp": _round_bp(current_value * 100.0),
    }
    for _window_label, field_name, days in _CREDIT_CHANGE_WINDOWS:
        prior_value = _point_value_at_or_before(points, current_date - timedelta(days=days))
        row[field_name] = _round_bp((current_value - prior_value) * 100.0) if prior_value is not None else None
    status, status_label = _credit_oas_status(_number(row.get("change_1w_bp")))
    row["status"] = status
    row["status_label"] = status_label
    return row


def _credit_tail_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    ccc_points = _feature_points(_mapping(feature_map.get("credit:hy_ccc_oas")))
    hy_points = _feature_points(_mapping(feature_map.get("credit:hy_oas")))
    if not ccc_points or not hy_points:
        return None
    current_date = min(ccc_points[-1][0], hy_points[-1][0])
    current_tail = _spread_at_or_before(hy_points, ccc_points, current_date)
    if current_tail is None:
        return None
    row: dict[str, Any] = {
        "key": "ccc_hy_tail",
        "label": "CCC-HY 尾部",
        "current_bp": _round_bp(current_tail * 100.0),
    }
    for _window_label, field_name, days in _CREDIT_CHANGE_WINDOWS:
        prior_tail = _spread_at_or_before(hy_points, ccc_points, current_date - timedelta(days=days))
        row[field_name] = _round_bp((current_tail - prior_tail) * 100.0) if prior_tail is not None else None
    status, status_label = _credit_tail_status(_number(row.get("change_1w_bp")))
    row["status"] = status
    row["status_label"] = status_label
    return row


def _credit_sloos_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("credit:sloos_ci_large_tightening")))
    if not points:
        return None
    current_date, current_value = points[-1]
    prior_value = _point_value_at_or_before(points, current_date - timedelta(days=90))
    change_1q = _round_pct(current_value - prior_value) if prior_value is not None else None
    status, status_label = _credit_sloos_status(current_value=current_value, change_1q_pct=change_1q)
    return {
        "key": "sloos_ci_large_tightening",
        "label": "SLOOS 大中型收紧",
        "current_pct": _round_pct(current_value),
        "change_1q_pct": change_1q,
        "status": status,
        "status_label": status_label,
    }


def _credit_financial_conditions_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get("credit:nfci")))
    if not points:
        return None
    current_date, current_value = points[-1]
    row: dict[str, Any] = {
        "key": "nfci",
        "label": "NFCI 金融条件",
        "current_index": _round_index(current_value),
    }
    for _window_label, field_name, days in _CREDIT_CONDITIONS_CHANGE_WINDOWS:
        prior_value = _point_value_at_or_before(points, current_date - timedelta(days=days))
        row[field_name] = _round_index(current_value - prior_value) if prior_value is not None else None
    adjusted_points = _feature_points(_mapping(feature_map.get("credit:anfci")))
    adjusted_value = _point_value_at_or_before(adjusted_points, current_date) if adjusted_points else None
    if adjusted_value is not None:
        row["adjusted_index"] = _round_index(adjusted_value)
    status, status_label = _credit_financial_conditions_status(
        current_index=_number(row.get("current_index")) or 0.0,
        change_1w_index=_number(row.get("change_1w_index")),
        change_1m_index=_number(row.get("change_1m_index")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _credit_etf_relative_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    hyg_points = _feature_points(_mapping(feature_map.get("asset:hyg")))
    lqd_points = _feature_points(_mapping(feature_map.get("asset:lqd")))
    if not hyg_points or not lqd_points:
        return None
    current_date = min(hyg_points[-1][0], lqd_points[-1][0])
    hyg_current = _point_value_at_or_before(hyg_points, current_date)
    lqd_current = _point_value_at_or_before(lqd_points, current_date)
    if hyg_current is None or lqd_current is None:
        return None
    hyg_1w = _price_return_pct(hyg_points, current_date=current_date, days=7)
    lqd_1w = _price_return_pct(lqd_points, current_date=current_date, days=7)
    hyg_1m = _price_return_pct(hyg_points, current_date=current_date, days=30)
    lqd_1m = _price_return_pct(lqd_points, current_date=current_date, days=30)
    relative_1w = _round_pct(hyg_1w - lqd_1w) if hyg_1w is not None and lqd_1w is not None else None
    relative_1m = _round_pct(hyg_1m - lqd_1m) if hyg_1m is not None and lqd_1m is not None else None
    if relative_1w is None and relative_1m is None:
        return None
    status, status_label = _credit_etf_relative_status(
        hyg_1w_pct=hyg_1w,
        relative_1w_pct=relative_1w,
    )
    return {
        "key": "hyg_lqd_relative",
        "label": "HYG/LQD 信用 ETF",
        "hyg_1w_pct": _round_pct(hyg_1w) if hyg_1w is not None else None,
        "lqd_1w_pct": _round_pct(lqd_1w) if lqd_1w is not None else None,
        "relative_1w_pct": relative_1w,
        "hyg_1m_pct": _round_pct(hyg_1m) if hyg_1m is not None else None,
        "lqd_1m_pct": _round_pct(lqd_1m) if lqd_1m is not None else None,
        "relative_1m_pct": relative_1m,
        "status": status,
        "status_label": status_label,
    }


def _price_return_pct(points: Sequence[tuple[date, float]], *, current_date: date, days: int) -> float | None:
    current_value = _point_value_at_or_before(points, current_date)
    prior_value = _point_value_at_or_before(points, current_date - timedelta(days=days))
    if current_value is None or prior_value is None or prior_value == 0.0:
        return None
    return (current_value / prior_value - 1.0) * 100.0


def _credit_row_has_change(row: Mapping[str, Any]) -> bool:
    return any(
        _number(row.get(field_name)) is not None
        for field_name in (
            "change_1w_bp",
            "change_1m_bp",
            "change_3m_bp",
            "change_1w_index",
            "change_1m_index",
            "change_3m_index",
            "relative_1w_pct",
            "relative_1m_pct",
            "change_1q_pct",
        )
    )


def _credit_oas_status(change_1w_bp: float | None) -> tuple[str, str]:
    if change_1w_bp is None:
        return "stable", "稳定"
    if change_1w_bp >= 5.0:
        return "widening", "走阔"
    if change_1w_bp <= -5.0:
        return "tightening", "收窄"
    return "stable", "稳定"


def _credit_tail_status(change_1w_bp: float | None) -> tuple[str, str]:
    if change_1w_bp is None:
        return "stable", "稳定"
    if change_1w_bp >= 25.0:
        return "tail_widening", "尾部恶化"
    if change_1w_bp <= -25.0:
        return "tail_relief", "尾部缓和"
    return "stable", "稳定"


def _credit_sloos_status(*, current_value: float, change_1q_pct: float | None) -> tuple[str, str]:
    if current_value >= 25.0 or (change_1q_pct is not None and change_1q_pct >= 5.0):
        return "tightening", "银行收紧"
    if current_value <= 0.0 and change_1q_pct is not None and change_1q_pct <= -5.0:
        return "easing", "银行放松"
    return "neutral", "中性"


def _credit_financial_conditions_status(
    *, current_index: float, change_1w_index: float | None, change_1m_index: float | None
) -> tuple[str, str]:
    change_1w = change_1w_index if change_1w_index is not None else 0.0
    change_1m = change_1m_index if change_1m_index is not None else 0.0
    if current_index >= 0.5 or change_1w >= 0.2 or change_1m >= 0.4:
        return "conditions_tightening", "金融条件收紧"
    if current_index <= -0.75 and change_1w <= -0.2:
        return "conditions_easing", "金融条件宽松"
    return "conditions_stable", "条件稳定"


def _credit_etf_relative_status(*, hyg_1w_pct: float | None, relative_1w_pct: float | None) -> tuple[str, str]:
    hyg_1w = hyg_1w_pct if hyg_1w_pct is not None else 0.0
    relative_1w = relative_1w_pct if relative_1w_pct is not None else 0.0
    if relative_1w <= -1.0 and hyg_1w <= 0.0:
        return "etf_pressure", "HYG跑输"
    if relative_1w >= 1.0 and hyg_1w >= 0.0:
        return "etf_relief", "HYG企稳"
    return "etf_neutral", "ETF中性"


def _credit_regime(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    hy = next((row for row in rows if row.get("key") == "hy_oas"), {})
    tail = next((row for row in rows if row.get("key") == "ccc_hy_tail"), {})
    etf = next((row for row in rows if row.get("key") == "hyg_lqd_relative"), {})
    conditions = next((row for row in rows if row.get("key") == "nfci"), {})
    sloos = next((row for row in rows if row.get("key") == "sloos_ci_large_tightening"), {})
    hy_current = _number(hy.get("current_bp")) or 0.0
    hy_change_1w = _number(hy.get("change_1w_bp")) or 0.0
    hy_change_1m = _number(hy.get("change_1m_bp")) or 0.0
    tail_current = _number(tail.get("current_bp")) or 0.0
    tail_change_1w = _number(tail.get("change_1w_bp")) or 0.0
    tail_change_1m = _number(tail.get("change_1m_bp")) or 0.0
    etf_status = str(etf.get("status") or "")
    conditions_status = str(conditions.get("status") or "")
    sloos_status = str(sloos.get("status") or "")
    if hy_current >= 600.0 or tail_current >= 700.0:
        return (
            "credit_stress",
            "信用压力",
            "信用压力升温：高收益或 CCC 尾部进入压力区，风险资产需要防守。",
        )
    if hy_change_1w > 0.0 and tail_change_1w >= 25.0:
        return (
            "tail_widening",
            "尾部走阔",
            "信用尾部走阔：HY OAS 与 CCC-HY 尾部同时上行，高 beta 需要降级。",
        )
    if etf_status == "etf_pressure":
        return (
            "credit_etf_pressure",
            "ETF 压力",
            "信用 ETF 压力：HYG 跑输 LQD，现金信用尚未完全确认，先降低高收益 beta。",
        )
    if conditions_status == "conditions_tightening":
        return (
            "financial_conditions_tightening",
            "金融条件收紧",
            "金融条件收紧：NFCI 已经升温，但信用利差尚未完全扩散，警惕滞后确认。",
        )
    if hy_change_1m <= -20.0 and tail_change_1m <= 0.0:
        return (
            "credit_relief",
            "信用缓和",
            "信用利差缓和：HY OAS 收窄且尾部未扩散，风险偏好可获得信用确认。",
        )
    if sloos_status == "tightening":
        return (
            "bank_tightening",
            "银行收紧",
            "银行信贷收紧：信用风险尚未全面扩散，但融资条件正在压制 beta。",
        )
    return (
        "contained",
        "压力可控",
        "信用压力可控：利差和银行信贷暂未给出强方向，等待尾部确认。",
    )


def _credit_implications(regime: str) -> list[str]:
    if regime == "tail_widening":
        return ["信用尾部恶化：降低高 beta、盈利下修和融资敏感资产暴露。"]
    if regime == "credit_stress":
        return ["信用压力升温：优先防守现金流脆弱、杠杆高和再融资敏感资产。"]
    if regime == "credit_etf_pressure":
        return ["信用 ETF 走弱：低配高收益信用，优先 LQD/BIL 防守。"]
    if regime == "financial_conditions_tightening":
        return ["金融条件收紧：降低对利差尚未反应的信用 beta 和长久期风险资产暴露。"]
    if regime == "credit_relief":
        return ["信用缓和：风险资产可获得二次确认，但仍需流动性和波动率配合。"]
    if regime == "bank_tightening":
        return ["银行收紧：降低依赖融资扩张和信用 beta 的表达，等待 SLOOS 回落。"]
    return ["信用暂未给强方向：等待 HY OAS、CCC-HY 尾部、NFCI 和 SLOOS 同向确认。"]


def _credit_invalidations(regime: str) -> list[str]:
    if regime == "tail_widening":
        return ["若 HY OAS 1m 收窄且 CCC-HY 尾部回落，信用压力降级。"]
    if regime == "credit_stress":
        return ["若 HY OAS 回落至压力区下方且 CCC-HY 尾部收窄，压力读法降级。"]
    if regime == "credit_etf_pressure":
        return ["若 HYG 相对 LQD 重新走强且 HY OAS 未走阔，ETF 压力读法降级。"]
    if regime == "financial_conditions_tightening":
        return ["若 NFCI 回落且 HY/IG OAS 未继续走阔，金融条件收紧读法降级。"]
    if regime == "credit_relief":
        return ["若 HY OAS 重新 1w 走阔且 CCC-HY 尾部扩散，信用缓和失效。"]
    if regime == "bank_tightening":
        return ["若 SLOOS 收紧比例回落且利差稳定，银行收紧读法降级。"]
    return ["若 HY OAS 或 CCC-HY 尾部单周走阔超过 25bp，重新评估信用压力。"]


def _policy_target_range_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    lower_points = _feature_points(_mapping(feature_map.get("fed:target_lower")))
    upper_points = _feature_points(_mapping(feature_map.get("fed:target_upper")))
    if not lower_points or not upper_points:
        return None
    current_date = min(lower_points[-1][0], upper_points[-1][0])
    lower_value = _point_value_at_or_before(lower_points, current_date)
    upper_value = _point_value_at_or_before(upper_points, current_date)
    if lower_value is None or upper_value is None:
        return None
    return {
        "key": "target_range",
        "label": "目标区间",
        "lower_pct": _round_pct(lower_value),
        "upper_pct": _round_pct(upper_value),
        "width_bp": _round_bp((upper_value - lower_value) * 100.0),
        "status": "range_defined",
        "status_label": "区间明确",
    }


def _policy_effr_position_row(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    effr_points = _feature_points(_mapping(feature_map.get("fed:effr")))
    upper_points = _feature_points(_mapping(feature_map.get("fed:target_upper")))
    lower_points = _feature_points(_mapping(feature_map.get("fed:target_lower")))
    if not effr_points or not upper_points or not lower_points:
        return None
    current_date = min(effr_points[-1][0], upper_points[-1][0], lower_points[-1][0])
    current_effr = _point_value_at_or_before(effr_points, current_date)
    current_upper = _point_value_at_or_before(upper_points, current_date)
    current_lower = _point_value_at_or_before(lower_points, current_date)
    if current_effr is None or current_upper is None or current_lower is None:
        return None
    current_distance = current_effr - current_upper
    prior_date = current_date - timedelta(days=7)
    prior_effr = _point_value_at_or_before(effr_points, prior_date)
    prior_upper = _point_value_at_or_before(upper_points, prior_date)
    prior_distance = prior_effr - prior_upper if prior_effr is not None and prior_upper is not None else None
    distance_bp = _round_bp(current_distance * 100.0)
    status, status_label = _policy_effr_position_status(
        current_effr=current_effr,
        current_lower=current_lower,
        distance_to_upper_bp=distance_bp,
    )
    return {
        "key": "effr_vs_range",
        "label": "EFFR 位置",
        "current_pct": _round_pct(current_effr),
        "distance_to_upper_bp": distance_bp,
        "change_1w_bp": _round_bp((current_distance - prior_distance) * 100.0) if prior_distance is not None else None,
        "status": status,
        "status_label": status_label,
    }


def _policy_spread_row(
    *,
    key: str,
    label: str,
    left_concept_key: str,
    right_concept_key: str,
    feature_map: Mapping[str, Any],
    status_fn: Any,
) -> dict[str, Any] | None:
    left_points = _feature_points(_mapping(feature_map.get(left_concept_key)))
    right_points = _feature_points(_mapping(feature_map.get(right_concept_key)))
    if not left_points or not right_points:
        return None
    current_date = min(left_points[-1][0], right_points[-1][0])
    current_spread = _policy_spread_at_or_before(left_points, right_points, current_date)
    if current_spread is None:
        return None
    prior_spread = _policy_spread_at_or_before(left_points, right_points, current_date - timedelta(days=7))
    current_bp = _round_bp(current_spread * 100.0)
    change_1w_bp = _round_bp((current_spread - prior_spread) * 100.0) if prior_spread is not None else None
    status, status_label = status_fn(current_bp=current_bp, change_1w_bp=change_1w_bp)
    return {
        "key": key,
        "label": label,
        "current_bp": current_bp,
        "change_1w_bp": change_1w_bp,
        "status": status,
        "status_label": status_label,
    }


def _policy_spread_at_or_before(
    left_points: Sequence[tuple[date, float]],
    right_points: Sequence[tuple[date, float]],
    target_date: date,
) -> float | None:
    left_value = _point_value_at_or_before(left_points, target_date)
    right_value = _point_value_at_or_before(right_points, target_date)
    if left_value is None or right_value is None:
        return None
    return left_value - right_value


def _policy_volume_row(
    *,
    key: str,
    label: str,
    concept_key: str,
    feature_map: Mapping[str, Any],
) -> dict[str, Any] | None:
    points = _feature_points(_mapping(feature_map.get(concept_key)))
    if not points:
        return None
    current_date, current_value = points[-1]
    prior_value = _point_value_at_or_before(points, current_date - timedelta(days=7))
    row: dict[str, Any] = {
        "key": key,
        "label": label,
        "current_bn": _round_bn(current_value),
        "change_1w_bn": _round_bn(current_value - prior_value) if prior_value is not None else None,
    }
    status, status_label = _policy_volume_status(
        current_bn=_number(row.get("current_bn")) or 0.0,
        change_1w_bn=_number(row.get("change_1w_bn")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _policy_effr_position_status(
    *,
    current_effr: float,
    current_lower: float,
    distance_to_upper_bp: float,
) -> tuple[str, str]:
    if distance_to_upper_bp > 0.0:
        return "above_upper", "高于上限"
    if current_effr < current_lower:
        return "below_lower", "低于下限"
    if distance_to_upper_bp >= -5.0:
        return "near_upper", "贴近上限"
    return "in_range", "区间内"


def _policy_effr_iorb_status(*, current_bp: float, change_1w_bp: float | None) -> tuple[str, str]:
    if current_bp >= 10.0 or (change_1w_bp is not None and change_1w_bp >= 10.0):
        return "corridor_pressure", "走廊压力"
    if current_bp <= -10.0:
        return "below_iorb", "低于 IORB"
    return "stable", "稳定"


def _policy_funding_status(*, current_bp: float, change_1w_bp: float | None) -> tuple[str, str]:
    if current_bp >= 5.0 or (change_1w_bp is not None and change_1w_bp >= 5.0):
        return "funding_pressure", "融资压力"
    if current_bp <= -5.0:
        return "funding_relief", "融资缓和"
    return "stable", "稳定"


def _policy_admin_spread_status(*, current_bp: float, change_1w_bp: float | None) -> tuple[str, str]:
    if abs(current_bp) >= 5.0 or (change_1w_bp is not None and abs(change_1w_bp) >= 5.0):
        return "diverging", "偏离"
    return "stable", "稳定"


def _policy_unsecured_spread_status(*, current_bp: float, change_1w_bp: float | None) -> tuple[str, str]:
    if current_bp >= 5.0 or (change_1w_bp is not None and change_1w_bp >= 5.0):
        return "broader_unsecured_pressure", "广义无担保压力"
    if current_bp <= -5.0:
        return "fed_funds_premium", "联邦基金溢价"
    return "stable", "稳定"


def _policy_volume_status(*, current_bn: float, change_1w_bn: float | None) -> tuple[str, str]:
    if current_bn < 125.0 or (change_1w_bn is not None and change_1w_bn <= -25.0):
        return "thin_depth", "成交变薄"
    if change_1w_bn is not None and change_1w_bn >= 25.0:
        return "depth_improving", "深度改善"
    return "depth_ok", "深度稳定"


def _policy_regime(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    effr = next((row for row in rows if row.get("key") == "effr_vs_range"), {})
    effr_iorb = next((row for row in rows if row.get("key") == "effr_iorb_spread"), {})
    sofr_effr = next((row for row in rows if row.get("key") == "sofr_effr_spread"), {})
    effr_status = str(effr.get("status") or "")
    effr_iorb_bp = _number(effr_iorb.get("current_bp")) or 0.0
    sofr_effr_bp = _number(sofr_effr.get("current_bp")) or 0.0
    if effr_status == "above_upper" and (effr_iorb_bp >= 10.0 or sofr_effr_bp >= 5.0):
        return (
            "corridor_pressure",
            "走廊压力",
            "政策走廊承压：EFFR 高于目标上限且 SOFR 相对 EFFR 走阔，隔夜融资压力需要降杠杆。",
        )
    if sofr_effr_bp >= 10.0 or effr_iorb_bp >= 10.0:
        return (
            "funding_pressure",
            "融资压力",
            "隔夜融资压力上升：SOFR 或 EFFR 相对政策锚走阔，高 beta 需要等待资金面确认。",
        )
    if effr_status == "near_upper":
        return (
            "near_upper",
            "贴近上限",
            "EFFR 贴近政策区间上沿：走廊仍有效，但资金面容错空间下降。",
        )
    if effr_status == "below_lower":
        return (
            "below_lower",
            "低于下限",
            "EFFR 低于目标区间：政策传导偏松或数据口径需复核，等待官方利率确认。",
        )
    return (
        "stable",
        "走廊稳定",
        "政策走廊稳定：EFFR 位于目标区间内，SOFR 相对政策锚未显示明显压力。",
    )


def _policy_implications(regime: str) -> list[str]:
    if regime == "corridor_pressure":
        return ["走廊压力：降低融资敏感资产和杠杆多头，等待 EFFR 回到目标区间内。"]
    if regime == "funding_pressure":
        return ["融资压力：risk-on 需要降级，等待 SOFR-EFFR 或 EFFR-IORB 收窄确认。"]
    if regime == "near_upper":
        return ["贴近上限：保留防守仓位，避免把短端稳定误读为宽松。"]
    if regime == "below_lower":
        return ["低于下限：先复核数据和政策设定，再判断是否存在政策传导异常。"]
    return ["走廊稳定：政策利率传导未给风险资产额外压力，继续观察流动性和信用确认。"]


def _policy_invalidations(regime: str) -> list[str]:
    if regime == "corridor_pressure":
        return ["若 EFFR 回落至目标上限下方且 SOFR-EFFR 收窄至 0bp 附近，走廊压力读法降级。"]
    if regime == "funding_pressure":
        return ["若 SOFR-EFFR 与 EFFR-IORB 同时回到 0bp 附近，融资压力读法降级。"]
    if regime == "near_upper":
        return ["若 EFFR 重新回到区间中部且 SOFR-EFFR 不再走阔，贴上沿读法降级。"]
    if regime == "below_lower":
        return ["若 EFFR 回到目标区间内，低于下限读法失效。"]
    return ["若 EFFR 越过目标区间或 SOFR-EFFR 单周走阔超过 5bp，重新评估政策走廊。"]


def _yield_curve_spread_row(
    spread: Mapping[str, str],
    feature_map: Mapping[str, Any],
) -> dict[str, Any] | None:
    front_points = _feature_points(_mapping(feature_map.get(spread["front"])))
    back_points = _feature_points(_mapping(feature_map.get(spread["back"])))
    if not front_points or not back_points:
        return None
    current_date = min(front_points[-1][0], back_points[-1][0])
    current_spread = _spread_at_or_before(front_points, back_points, current_date)
    if current_spread is None:
        return None
    current_bp = _round_bp(current_spread * 100.0)
    row: dict[str, Any] = {
        "key": spread["key"],
        "label": spread["label"],
        "current_bp": current_bp,
    }
    for _window_label, field_name, days in _YIELD_CURVE_CHANGE_WINDOWS:
        prior_spread = _spread_at_or_before(
            front_points,
            back_points,
            current_date - timedelta(days=days),
        )
        row[field_name] = _round_bp((current_spread - prior_spread) * 100.0) if prior_spread is not None else None
    status, status_label = _yield_curve_spread_status(
        current_bp=current_bp,
        change_1w_bp=_number(row.get("change_1w_bp")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _yield_curve_spread_history(
    spread: Mapping[str, str],
    feature_map: Mapping[str, Any],
) -> dict[str, Any] | None:
    front_points = _feature_points(_mapping(feature_map.get(spread["front"])))
    back_points = _feature_points(_mapping(feature_map.get(spread["back"])))
    if not front_points or not back_points:
        return None
    observed_dates = sorted({observed_date for observed_date, _value in (*front_points, *back_points)})
    points: list[dict[str, Any]] = []
    for observed_date in observed_dates:
        spread_value = _spread_at_or_before(front_points, back_points, observed_date)
        if spread_value is None:
            continue
        points.append({"observed_at": observed_date.isoformat(), "value_bp": _round_bp(spread_value * 100.0)})
    if len(points) < 2:
        return None
    bounded_points = points[-_YIELD_CURVE_HISTORY_POINT_LIMIT:]
    values = [_number(point.get("value_bp")) for point in bounded_points]
    numeric_values = [value for value in values if value is not None]
    if not numeric_values:
        return None
    return {
        "key": spread["key"],
        "label": spread["label"],
        "unit": "bp",
        "points": bounded_points,
        "min_bp": _round_bp(min(numeric_values)),
        "max_bp": _round_bp(max(numeric_values)),
        "latest_bp": _round_bp(numeric_values[-1]),
    }


def _yield_curve_tenor_row(
    tenor: Mapping[str, str],
    feature_map: Mapping[str, Any],
) -> dict[str, Any] | None:
    nominal_feature = _mapping(feature_map.get(tenor["nominal"]))
    real_feature = _mapping(feature_map.get(tenor["real"]))
    breakeven_feature = _mapping(feature_map.get(tenor["breakeven"]))
    nominal = _latest_feature_value(nominal_feature)
    real = _latest_feature_value(real_feature)
    breakeven = _latest_feature_value(breakeven_feature)
    if nominal is None or real is None or breakeven is None:
        return None
    nominal_change_1w_bp = _yield_curve_feature_change_bp(nominal_feature, days=7)
    real_change_1w_bp = _yield_curve_feature_change_bp(real_feature, days=7)
    breakeven_change_1w_bp = _yield_curve_feature_change_bp(breakeven_feature, days=7)
    driver, driver_label = _yield_curve_tenor_driver(
        real_change_1w_bp=real_change_1w_bp,
        breakeven_change_1w_bp=breakeven_change_1w_bp,
    )
    return {
        "key": tenor["key"],
        "label": tenor["label"],
        "nominal_pct": _round_pct(nominal),
        "real_pct": _round_pct(real),
        "breakeven_pct": _round_pct(breakeven),
        "nominal_change_1w_bp": nominal_change_1w_bp,
        "real_change_1w_bp": real_change_1w_bp,
        "breakeven_change_1w_bp": breakeven_change_1w_bp,
        "residual_bp": _round_bp((nominal - real - breakeven) * 100.0),
        "driver": driver,
        "driver_label": driver_label,
    }


def _latest_feature_value(feature: Mapping[str, Any]) -> float | None:
    points = _feature_points(feature)
    if not points:
        return None
    return points[-1][1]


def _feature_points(feature: Mapping[str, Any]) -> list[tuple[date, float]]:
    points: dict[date, float] = {}
    for point in _mapping_list(feature.get("history")):
        observed_date = _parse_date(str(point.get("observed_at") or ""))
        value = _number(point.get("value"))
        if observed_date is not None and value is not None:
            points[observed_date] = value
    latest = _mapping(feature.get("latest"))
    latest_date = _parse_date(str(latest.get("observed_at") or ""))
    latest_value = _number(latest.get("value"))
    if latest_date is not None and latest_value is not None:
        points[latest_date] = latest_value
    return sorted(points.items(), key=lambda item: item[0])


def _spread_at_or_before(
    front_points: Sequence[tuple[date, float]],
    back_points: Sequence[tuple[date, float]],
    target_date: date,
) -> float | None:
    front_value = _point_value_at_or_before(front_points, target_date)
    back_value = _point_value_at_or_before(back_points, target_date)
    if front_value is None or back_value is None:
        return None
    return back_value - front_value


def _point_value_at_or_before(points: Sequence[tuple[date, float]], target_date: date) -> float | None:
    value = None
    for observed_date, observed_value in points:
        if observed_date > target_date:
            break
        value = observed_value
    return value


def _yield_curve_spread_status(
    *,
    current_bp: float,
    change_1w_bp: float | None,
) -> tuple[str, str]:
    if change_1w_bp is None:
        return ("inverted", "倒挂") if current_bp < 0 else ("stable", "稳定")
    if current_bp < 0 and change_1w_bp >= 5.0:
        return "less_inverted", "倒挂缓和"
    if change_1w_bp >= 5.0:
        return "steepening", "走陡"
    if change_1w_bp <= -5.0:
        return "flattening", "走平"
    if current_bp < 0:
        return "inverted", "倒挂"
    return "stable", "稳定"


def _yield_curve_shape(rows: Sequence[Mapping[str, Any]], feature_map: Mapping[str, Any]) -> tuple[str, str, str]:
    two_ten = next((row for row in rows if row.get("key") == "2s10s"), {})
    two_ten_current = _number(two_ten.get("current_bp")) or 0.0
    two_ten_change = _number(two_ten.get("change_1w_bp")) or 0.0
    ten_year_change = _yield_curve_feature_change_bp(_mapping(feature_map.get("rates:dgs10")), days=7) or 0.0
    if ten_year_change > 0 and two_ten_change > 0:
        return (
            "bear_steepening",
            "熊陡",
            "曲线熊陡：10Y 上行且 2s10s 走陡，期限溢价压力压制久期资产。",
        )
    if ten_year_change < 0 and two_ten_change > 0:
        return (
            "bull_steepening",
            "牛陡",
            "曲线牛陡：10Y 下行且 2s10s 走陡，增长下行压力高于期限溢价。",
        )
    if two_ten_change < 0:
        return (
            "flattening",
            "走平",
            "曲线走平：前端政策压力相对后端更强，风险资产仍需等待政策预期确认。",
        )
    if two_ten_current < 0:
        return (
            "inverted",
            "倒挂",
            "曲线倒挂：衰退定价仍在，风险偏好需要信用和流动性二次确认。",
        )
    return (
        "neutral",
        "中性",
        "曲线形态中性：期限结构暂未给出强方向，等待利率、信用和流动性共振。",
    )


def _yield_curve_feature_change_bp(feature: Mapping[str, Any], *, days: int) -> float | None:
    points = _feature_points(feature)
    if len(points) < 2:
        return None
    current_date, current_value = points[-1]
    prior_value = _point_value_at_or_before(points, current_date - timedelta(days=days))
    if prior_value is None:
        return None
    return _round_bp((current_value - prior_value) * 100.0)


def _yield_curve_tenor_driver(
    *,
    real_change_1w_bp: float | None,
    breakeven_change_1w_bp: float | None,
) -> tuple[str, str]:
    if real_change_1w_bp is None or breakeven_change_1w_bp is None:
        return "insufficient_history", "历史不足"
    real_abs = abs(real_change_1w_bp)
    breakeven_abs = abs(breakeven_change_1w_bp)
    if real_abs >= breakeven_abs + 5.0:
        return "real_rate", "实际利率驱动"
    if breakeven_abs >= real_abs + 5.0:
        return "breakeven", "通胀补偿驱动"
    return "mixed", "混合驱动"


def _real_rate_row(
    spec: Mapping[str, str],
    feature_map: Mapping[str, Any],
    *,
    status_fn: Any,
) -> dict[str, Any] | None:
    feature = _mapping(feature_map.get(spec["concept_key"]))
    current = _latest_feature_value(feature)
    if current is None:
        return None
    row: dict[str, Any] = {
        "key": spec["key"],
        "label": spec["label"],
        "current_pct": _round_pct(current),
    }
    for _window_label, field_name, days in _YIELD_CURVE_CHANGE_WINDOWS:
        row[field_name] = _yield_curve_feature_change_bp(feature, days=days)
    status, status_label = status_fn(
        current_pct=_number(row.get("current_pct")) or 0.0,
        change_1w_bp=_number(row.get("change_1w_bp")),
    )
    row["status"] = status
    row["status_label"] = status_label
    return row


def _real_rate_row_has_change(row: Mapping[str, Any]) -> bool:
    return any(row.get(field_name) is not None for _label, field_name, _days in _YIELD_CURVE_CHANGE_WINDOWS)


def _real_rate_real_status(*, current_pct: float, change_1w_bp: float | None) -> tuple[str, str]:
    if current_pct >= 2.0 or (change_1w_bp is not None and change_1w_bp >= 15.0):
        return "valuation_pressure", "估值压力"
    if change_1w_bp is not None and change_1w_bp <= -15.0:
        return "valuation_relief", "估值缓和"
    return "stable", "稳定"


def _real_rate_inflation_status(*, current_pct: float, change_1w_bp: float | None) -> tuple[str, str]:
    if change_1w_bp is None:
        return "stable", "稳定"
    if change_1w_bp >= 5.0:
        return "rising", "补偿走阔"
    if change_1w_bp <= -5.0:
        return "falling", "补偿回落"
    return "stable", "稳定"


def _real_rate_regime(
    real_yield_rows: Sequence[Mapping[str, Any]],
    inflation_rows: Sequence[Mapping[str, Any]],
) -> tuple[str, str, str]:
    ten_year_real = next((row for row in real_yield_rows if row.get("key") == "real_10y"), {})
    ten_year_breakeven = next((row for row in inflation_rows if row.get("key") == "breakeven_10y"), {})
    real_current = _number(ten_year_real.get("current_pct")) or 0.0
    real_change = _number(ten_year_real.get("change_1w_bp")) or 0.0
    breakeven_change = _number(ten_year_breakeven.get("change_1w_bp")) or 0.0
    if (real_current >= 2.0 or real_change >= 15.0) and breakeven_change <= 5.0:
        return (
            "real_rate_pressure",
            "实际利率压力",
            "实际利率上行且通胀补偿未同步走阔：估值压力偏实际利率驱动，长久期与高 beta 需要降级。",
        )
    if breakeven_change >= 10.0 and real_change < 10.0:
        return (
            "inflation_compensation",
            "通胀补偿走阔",
            "通胀补偿走阔而实际利率未同步上行：名义利率压力偏通胀预期驱动。",
        )
    if real_change <= -15.0:
        return (
            "real_rate_relief",
            "实际利率缓和",
            "实际利率回落：久期与高 beta 估值压力缓和，但仍需信用和流动性确认。",
        )
    return (
        "stable",
        "实际利率稳定",
        "实际利率与通胀补偿未出现强方向：等待 10Y real、breakeven 和风险资产同步确认。",
    )


def _real_rate_implications(regime: str) -> list[str]:
    if regime == "real_rate_pressure":
        return ["实际利率压力：降低长久期成长、长债和高 beta 反弹置信度。"]
    if regime == "inflation_compensation":
        return ["通胀补偿走阔：区分名义利率上行是否由通胀预期而非实际贴现率驱动。"]
    if regime == "real_rate_relief":
        return ["实际利率缓和：可上调久期和成长估值容忍度，但需要信用/流动性确认。"]
    return ["实际利率稳定：暂不把估值压力作为主导变量，等待 10Y real 或 5Y5Y 给方向。"]


def _real_rate_invalidations(regime: str) -> list[str]:
    if regime == "real_rate_pressure":
        return ["若 10Y 实际利率单周回落超过 15bp，且 breakeven 不再回落，实际利率压力读法降级。"]
    if regime == "inflation_compensation":
        return ["若 breakeven 回落且 10Y real 转为上行，通胀补偿驱动读法失效。"]
    if regime == "real_rate_relief":
        return ["若 10Y real 重新上行超过 15bp，实际利率缓和读法失效。"]
    return ["若 10Y real 或 5Y5Y 单周变化超过 15bp，重新评估实际利率读法。"]


def _yield_curve_implications(shape: str) -> list[str]:
    if shape == "bear_steepening":
        return ["期限溢价压力：优先防守长久期成长、长债和高 beta。"]
    if shape == "bull_steepening":
        return ["增长压力：优先检查信用利差、盈利预期和防守资产确认。"]
    if shape == "flattening":
        return ["政策压力：优先降低对降息交易和高 beta 反弹的置信度。"]
    if shape == "inverted":
        return ["衰退定价：风险资产需要信用不再恶化和流动性改善才能升级。"]
    return ["曲线暂未给强方向：等待 2s10s、3m10y 与信用/流动性同步确认。"]


def _yield_curve_invalidations(shape: str) -> list[str]:
    if shape == "bear_steepening":
        return ["若 10Y 回落且 2s10s 重新走平，曲线压力降级。"]
    if shape == "bull_steepening":
        return ["若 10Y 重新上行且信用未恶化，增长压力读法降级。"]
    if shape == "flattening":
        return ["若 2s10s 重新走陡且短端回落，政策压力读法降级。"]
    if shape == "inverted":
        return ["若 3m10y 回到正值且信用稳定，倒挂压力降级。"]
    return ["若关键利差单周变化超过 10bp，重新评估曲线形态。"]


def _round_bp(value: float) -> float:
    rounded = round(float(value), 1)
    return 0.0 if rounded == 0 else rounded


def _round_pct(value: float) -> float:
    rounded = round(float(value), 2)
    return 0.0 if rounded == 0 else rounded


def _round_index(value: float) -> float:
    rounded = round(float(value), 1)
    return 0.0 if rounded == 0 else rounded


def _round_ratio(value: float) -> float:
    rounded = round(float(value), 2)
    return 0.0 if rounded == 0 else rounded


def _round_bn(value_million_usd: float) -> float:
    rounded = round(float(value_million_usd) / 1_000.0, 1)
    return 0.0 if rounded == 0 else rounded


def _round_trillion(value_million_usd: float) -> float:
    rounded = round(float(value_million_usd) / 1_000_000.0, 2)
    return 0.0 if rounded == 0 else rounded


def _module_evidence(
    *,
    config: MacroModuleConfig,
    feature_map: Mapping[str, Any],
    primary_chart: Mapping[str, Any],
    data_health: Mapping[str, Any],
    scenario: Mapping[str, Any],
) -> dict[str, Any]:
    if config.module_id == "overview":
        return {
            "confirmations": [
                item
                for item in (_evidence_item(item) for item in _mapping_list(scenario.get("confirmations")))
                if item is not None
            ],
            "contradictions": [
                item
                for item in (_evidence_item(item) for item in _mapping_list(scenario.get("contradictions")))
                if item is not None
            ],
            "watch_triggers": [
                item
                for item in (_evidence_item(item) for item in _mapping_list(scenario.get("watch_triggers")))
                if item is not None
            ],
            "invalidations": [
                item
                for item in (_evidence_item(item) for item in _mapping_list(scenario.get("invalidations")))
                if item is not None
            ],
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
            "label": _concept_required_text(concept_key, "label"),
            "description": "模块配置概念未在最新宏观投影中出现。",
        }
        for concept_key in missing_concepts
    ]
    return {
        "confirmations": confirmations,
        "contradictions": contradictions,
        "watch_triggers": [],
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


def _decision_console(
    *,
    scenario: Mapping[str, Any],
    data_health: Mapping[str, Any],
    feature_map: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    quality_blockers = _mapping_list(scenario.get("quality_blockers"))
    if not quality_blockers:
        quality_blockers = [
            {
                "code": gap.get("code"),
                "label": gap.get("label"),
                "description": gap.get("remediation_hint") or gap.get("label") or "",
                "severity": gap.get("severity"),
            }
            for gap in _mapping_list(data_health.get("global_gaps"))
        ]
    trade_map = [
        item
        for item in (_trade_map_item(item, observations) for item in _mapping_list(scenario.get("trade_map")))
        if item is not None
    ]
    payload: dict[str, Any] = {
        "top_changes": [
            item
            for item in (_compact_signal(item) for item in _mapping_list(scenario.get("top_changes")))
            if item is not None
        ],
        "quality_blockers": [_compact_quality_blocker(item) for item in quality_blockers],
        "trade_map": trade_map,
    }
    watchlist_alerts = _watchlist_alerts(
        scenario=scenario,
        trade_map=trade_map,
        quality_blockers=quality_blockers,
    )
    if watchlist_alerts:
        payload["watchlist_alerts"] = watchlist_alerts
    judgement_review = _judgement_review(trade_map)
    if judgement_review:
        payload["judgement_review"] = judgement_review
    scenario_cases = _mapping_list(scenario.get("scenario_cases"))
    if scenario_cases:
        payload["scenario_cases"] = [dict(item) for item in scenario_cases]
    liquidity_pressure = _liquidity_pressure(feature_map)
    if liquidity_pressure:
        payload["liquidity_pressure"] = liquidity_pressure
    event_candidates = _event_catalyst_candidates(observations)
    future_catalysts = _future_catalysts(scenario, event_candidates)
    if future_catalysts:
        payload["future_catalysts"] = future_catalysts
    data_credibility = _data_credibility(feature_map)
    if data_credibility:
        payload["data_credibility"] = data_credibility
    return payload


def _future_catalysts(
    scenario: Mapping[str, Any],
    event_candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    rows = [
        row
        for row in (_future_watch_catalyst(item) for item in _mapping_list(scenario.get("watch_triggers")))
        if row is not None
    ]
    rows.extend(row for row in (_future_event_catalyst(catalyst) for catalyst in event_candidates) if row is not None)
    if not rows:
        return None
    return {
        "label": "未来 24/72h 催化剂",
        "rows": sorted(rows, key=_future_catalyst_sort_key)[:6],
    }


def _future_watch_catalyst(item: Mapping[str, Any]) -> dict[str, Any] | None:
    code = str(item.get("code") or "").strip()
    label = str(item.get("label") or _code_label(code) or "").strip()
    window = _future_catalyst_window(item.get("time_window"))
    if not label or window is None:
        return None
    severity = _required_macro_severity(item.get("severity"))
    return {
        "key": f"watch:{code or label}",
        "label": label,
        "description": str(item.get("description") or ""),
        "window": window,
        "window_label": window,
        "severity": severity,
        "severity_label": _future_catalyst_severity_label(severity),
        "source": "情景触发",
        "kind": "watch_trigger",
    }


def _future_event_catalyst(catalyst: Mapping[str, Any]) -> dict[str, Any] | None:
    kind = str(catalyst.get("kind") or "")
    days_until = _number(catalyst.get("value"))
    if kind not in {"auction_calendar", "calendar"} or days_until is None:
        return None
    if days_until < 0 or days_until > 3:
        return None
    window = "24h" if days_until <= 1 else "72h"
    severity = "high" if window == "24h" else "medium"
    row = {
        "key": f"event:{catalyst.get('code') or catalyst.get('label') or ''}",
        "label": str(catalyst.get("label") or ""),
        "description": str(catalyst.get("description") or ""),
        "window": window,
        "window_label": window,
        "severity": severity,
        "severity_label": _future_catalyst_severity_label(severity),
        "source": str(catalyst.get("source") or ""),
        "kind": kind,
    }
    source_url = catalyst.get("source_url")
    if source_url:
        row["source_url"] = source_url
    return row


def _future_catalyst_window(value: object) -> str | None:
    window = str(value or "").strip().lower()
    if window in {"24h", "24hr", "1d", "today"}:
        return "24h"
    if window in {"72h", "3d"}:
        return "72h"
    return None


def _future_catalyst_severity_label(severity: str) -> str:
    return _required_macro_severity_label(severity, allowed={"high", "medium", "low"})


def _future_catalyst_sort_key(item: Mapping[str, Any]) -> tuple[int, int, int, str]:
    window_rank = {"24h": 0, "72h": 1}.get(str(item.get("window") or ""), 2)
    severity_rank = {"high": 0, "medium": 1, "low": 2}.get(str(item.get("severity") or ""), 3)
    kind_rank = {"watch_trigger": 0, "calendar": 1, "auction_calendar": 1}.get(
        str(item.get("kind") or ""),
        2,
    )
    return (window_rank, severity_rank, kind_rank, str(item.get("label") or ""))


def _market_event_flow(
    catalysts: Sequence[Mapping[str, Any]],
    *,
    news_rows: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any] | None:
    rows = [row for row in (_market_news_event_flow_row(news_row) for news_row in news_rows) if row is not None]
    rows.extend(row for row in (_market_event_flow_row(catalyst) for catalyst in catalysts) if row is not None)
    if not rows:
        return None
    return {
        "key": "market_event_flow",
        "label": "市场事件流",
        "rows": rows,
    }


def _market_event_flow_row(catalyst: Mapping[str, Any]) -> dict[str, Any] | None:
    label = str(catalyst.get("label") or "").strip()
    detail = str(catalyst.get("description") or "").strip()
    date = str(catalyst.get("observed_at") or "").strip()
    if not label or not detail or not date:
        return None
    window, severity, severity_label = _event_flow_window(catalyst)
    category, category_label, impact, impact_label, watch = _event_flow_classification(catalyst)
    return {
        "key": str(catalyst.get("code") or label),
        "label": label,
        "date": date,
        "detail": detail,
        "source": str(catalyst.get("source") or ""),
        "source_url": catalyst.get("source_url"),
        "kind": str(catalyst.get("kind") or ""),
        "window": window,
        "severity": severity,
        "severity_label": severity_label,
        "category": category,
        "category_label": category_label,
        "impact": impact,
        "impact_label": impact_label,
        "watch": watch,
    }


def _market_news_event_flow_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    label = str(row.get("headline") or "").strip()
    detail = str(row.get("summary") or "").strip()
    date_label = _news_row_date(row)
    source = str(row.get("source_domain") or "").strip()
    if not label or not detail or not date_label or not source:
        return None
    market_scope = _mapping(row.get("market_scope"))
    category = str(market_scope.get("primary") or "").strip() or "market_event"
    category_label = _news_scope_label(category)
    impact, impact_label, severity, severity_label = _news_mainline_impact(row)
    watch_parts = _news_watch_parts(row, category_label=category_label)
    return {
        "key": f"news:{row.get('row_id') or row.get('news_item_id') or label}",
        "label": label,
        "date": date_label,
        "detail": detail,
        "source": source,
        "source_url": row.get("canonical_url"),
        "kind": "news",
        "window": "recent",
        "severity": severity,
        "severity_label": severity_label,
        "category": category,
        "category_label": category_label,
        "impact": impact,
        "impact_label": impact_label,
        "watch": " · ".join(watch_parts),
    }


def _news_row_date(row: Mapping[str, Any]) -> str | None:
    latest_at_ms = _number(row.get("latest_at_ms"))
    if latest_at_ms is None:
        return _date_string(row.get("published_at") or row.get("observed_at"))
    return datetime.fromtimestamp(latest_at_ms / 1000, tz=UTC).date().isoformat()


def _news_scope_label(scope: str) -> str:
    return _NEWS_MARKET_SCOPE_LABELS.get(scope, "市场事件")


def _news_mainline_impact(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    signal = _mapping(row.get("signal"))
    agent_signal = _mapping(signal.get("agent_signal"))
    alert_eligibility = _mapping(signal.get("alert_eligibility"))
    decision_class = str(agent_signal.get("decision_class") or alert_eligibility.get("decision_class") or "").strip()
    if decision_class == "driver":
        return "mainline_driver", "改变主线", "high", "高"
    if decision_class == "watch":
        return "mainline_watch", "观察主线", "medium", "中"
    return "mainline_context", "不改主线", "low", "低"


def _news_watch_parts(row: Mapping[str, Any], *, category_label: str) -> list[str]:
    token_lanes = _mapping_list(row.get("token_lanes"))
    symbols = _unique(str(item.get("symbol") or "").strip() for item in token_lanes)
    if symbols:
        return [*symbols[:4], category_label]
    return [category_label]


def _event_flow_window(catalyst: Mapping[str, Any]) -> tuple[str, str, str]:
    kind = str(catalyst.get("kind") or "")
    if kind == "fed_text":
        return _event_flow_fed_text_window(catalyst)
    if kind == "auction_result":
        return "recent", "medium", "中"
    days_until = _number(catalyst.get("value"))
    if kind in {"auction_calendar", "calendar"} and days_until is not None:
        return _event_flow_calendar_window(days_until)
    return "recent", "medium", "中"


def _event_flow_calendar_window(days_until: float) -> tuple[str, str, str]:
    if days_until <= 3:
        return "0-3d", "high", "高"
    if days_until <= 7:
        return "4-7d", "medium", "中"
    if days_until <= 14:
        return "8-14d", "low", "低"
    if days_until <= 30:
        return "15-30d", "low", "低"
    return "30d+", "low", "低"


def _event_flow_fed_text_window(catalyst: Mapping[str, Any]) -> tuple[str, str, str]:
    document_type = str(catalyst.get("document_type") or "").strip()
    if document_type in {"minutes", "press_release", "statement"}:
        return "recent", "high", "高"
    return "recent", "medium", "中"


def _watchlist_alerts(
    *,
    scenario: Mapping[str, Any],
    trade_map: Sequence[Mapping[str, Any]],
    quality_blockers: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    assets = _watchlist_assets(trade_map)
    rules = _watchlist_rules(scenario, quality_blockers)
    if not assets and not rules:
        return None
    return {
        "key": "watchlist_alerts",
        "label": "Watchlist 与触发提醒",
        "assets": assets[:8],
        "rules": rules[:8],
    }


def _watchlist_assets(trade_map: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for trade in trade_map:
        for leg in _mapping_list(trade.get("legs")):
            symbol = str(leg.get("symbol") or "").strip()
            label = str(leg.get("label") or symbol).strip()
            action = str(leg.get("action") or "").strip()
            key = symbol or label
            if not key or not label:
                continue
            normalized_key = key.lower()
            if normalized_key in seen:
                continue
            seen.add(normalized_key)
            assets.append(
                {
                    "key": key,
                    "symbol": symbol,
                    "label": label,
                    "action": action,
                }
            )
    return assets


def _watchlist_rules(
    scenario: Mapping[str, Any],
    quality_blockers: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(
        row
        for row in (
            _watchlist_rule(item, kind="watch", kind_label="触发")
            for item in _mapping_list(scenario.get("watch_triggers"))
        )
        if row is not None
    )
    rows.extend(
        row
        for row in (
            _watchlist_rule(item, kind="invalidation", kind_label="失效")
            for item in _mapping_list(scenario.get("invalidations"))
        )
        if row is not None
    )
    rows.extend(
        row
        for row in (_watchlist_rule(item, kind="quality", kind_label="质量") for item in quality_blockers)
        if row is not None
    )
    return rows


def _watchlist_rule(
    item: Mapping[str, Any],
    *,
    kind: str,
    kind_label: str,
) -> dict[str, Any] | None:
    code = str(item.get("code") or "").strip()
    label = str(item.get("label") or _code_label(code) or "").strip()
    if not label:
        return None
    payload = {
        "key": f"{kind}:{code or label}",
        "label": label,
        "description": str(item.get("description") or item.get("remediation_hint") or ""),
        "kind": kind,
        "kind_label": kind_label,
    }
    window = str(item.get("time_window") or "").strip()
    if window:
        payload["window"] = window
    severity = str(item.get("severity") or "").strip()
    if severity:
        payload["severity"] = severity
        payload["severity_label"] = _watchlist_severity_label(severity)
    return payload


def _watchlist_severity_label(severity: str) -> str:
    return _required_macro_severity_label(severity)


def _liquidity_pressure(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    diagnostics = _liquidity_diagnostics(feature_map)
    if diagnostics is None:
        return None
    regime = str(diagnostics.get("regime") or "").strip()
    score = _liquidity_pressure_score(regime)
    payload: dict[str, Any] = {
        "key": "liquidity_pressure",
        "label": "流动性压力",
        "score": score,
        "score_label": f"{score:.1f}/10",
        "regime": regime,
        "regime_label": _liquidity_pressure_regime_label(regime, diagnostics.get("regime_label")),
        "summary": str(diagnostics.get("summary") or ""),
        "drivers": _liquidity_pressure_drivers(_mapping_list(diagnostics.get("rows"))),
    }
    implications = _string_list(diagnostics.get("implications"))
    invalidations = _string_list(diagnostics.get("invalidations"))
    if implications:
        payload["implication"] = implications[0]
    if invalidations:
        payload["invalidation"] = invalidations[0]
    return payload


def _liquidity_pressure_score(regime: str) -> float:
    score = {
        "corridor_drain": 7.0,
        "treasury_drain": 6.5,
        "buffer_low": 6.0,
        "neutral": 5.0,
        "liquidity_injection": 3.5,
    }.get(regime)
    if score is not None:
        return score
    raise ValueError(f"Missing macro liquidity pressure regime metadata: {regime or '<missing>'}")


def _liquidity_pressure_regime_label(regime: str, label: object) -> str:
    normalized_label = str(label or "").strip()
    if normalized_label:
        return normalized_label
    raise ValueError(f"Missing macro liquidity pressure regime label metadata: {regime or '<missing>'}")


def _liquidity_pressure_drivers(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows_by_key = {str(row.get("key") or ""): dict(row) for row in rows}
    drivers = [rows_by_key[key] for key in _LIQUIDITY_PRESSURE_DRIVER_PRIORITY if key in rows_by_key]
    return drivers[:3]


def _data_credibility(feature_map: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = [
        _data_credibility_row(concept_key, _mapping(feature_map.get(concept_key)))
        for concept_key in _DATA_CREDIBILITY_CONCEPTS
        if isinstance(feature_map.get(concept_key), Mapping)
    ]
    if len(rows) < _DATA_CREDIBILITY_MIN_ROWS:
        return None
    issue_count = sum(1 for row in rows if row["quality"] not in _DATA_CREDIBILITY_OK_QUALITIES)
    return {
        "label": "数据可信度层",
        "issue_count": issue_count,
        "issue_label": f"{issue_count} issue(s)",
        "rows": rows,
    }


def _data_credibility_row(concept_key: str, feature: Mapping[str, Any]) -> dict[str, Any]:
    tile = _tile(concept_key, feature)
    return {
        "concept_key": concept_key,
        "label": tile["short_label"],
        "display_value": tile["display_value"],
        "unit_label": tile["unit_label"],
        "observed_at": tile["observed_at"],
        "observed_at_label": tile["observed_at_label"],
        "source_label": tile["source_label"],
        "quality": tile["quality"],
        "quality_label": tile["quality_label"],
    }


def _judgement_review(trade_map: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    rows = [row for row in (_judgement_review_row(item) for item in trade_map) if row is not None]
    if not rows:
        return None
    return {
        "label": "昨日判断复盘",
        "item_count": len(rows),
        "item_count_label": f"{len(rows)} 条",
        "rows": rows[:4],
    }


def _judgement_review_row(item: Mapping[str, Any]) -> dict[str, Any] | None:
    expression = str(item.get("expression") or "")
    if not expression:
        return None
    label = str(item.get("label") or _trade_map_expression_label(expression) or "").strip()
    if not label:
        return None
    holding_rows = _mapping_list(_mapping(item.get("holding_period_review")).get("rows"))
    windows = [row for row in (_judgement_review_window(row) for row in holding_rows) if row is not None]
    if not windows:
        return None
    trust_summary = str(_mapping(item.get("historical_trust")).get("summary") or "")
    return {
        "key": f"{expression}:holding_periods",
        "expression": expression,
        "label": label,
        "reliability_summary": trust_summary,
        "windows": windows,
    }


def _judgement_review_window(row: Mapping[str, Any]) -> dict[str, Any] | None:
    horizon = str(row.get("horizon") or "").strip()
    label = str(row.get("label") or "").strip()
    if not horizon or not label:
        return None
    status = str(row.get("status") or "insufficient_history")
    return {
        "horizon": horizon,
        "label": label,
        "status": status,
        "status_label": str(row.get("status_label") or _judgement_review_status_label(status)),
        "sample_count": _int_or_none(row.get("sample_count")) or 0,
        "hit_count": _int_or_none(row.get("hit_count")) or 0,
        "win_rate_label": str(row.get("win_rate_label") or "0/0"),
        "pnl_usd": _number(row.get("pnl_usd")) or 0.0,
        "average_signed_return_pct": _number(row.get("average_signed_return_pct")) or 0.0,
    }


def _judgement_review_status_label(status: str) -> str:
    return {
        "complete": "已完成",
        "completed": "已完成",
        "in_progress": "观察中",
        "pending": "观察中",
        "observing": "观察中",
        "insufficient_history": "样本不足",
    }.get(status, "样本不足")


def _trade_map_expression_label(expression: str) -> str | None:
    return _TRADE_MAP_EXPRESSION_LABELS.get(expression)


def _trade_map_item(item: Mapping[str, Any], observations: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    payload = dict(item)
    expression = str(payload.get("expression") or "").strip()
    if expression and not str(payload.get("label") or "").strip() and _trade_map_expression_label(expression) is None:
        return None
    historical_review = _trade_map_historical_review(expression, observations)
    if historical_review:
        payload["historical_review"] = historical_review
        portfolio_review = _trade_map_portfolio_review(historical_review)
        payload["portfolio_review"] = portfolio_review
        payload["action_checklist"] = _trade_map_action_checklist(payload, portfolio_review)
        holding_review = _trade_map_holding_period_review(expression, observations)
        if holding_review:
            payload["holding_period_review"] = holding_review
            payload["historical_trust"] = _trade_map_historical_trust(holding_review)
    return payload


def _trade_map_historical_review(
    expression: str,
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    expectations = _TRADE_MAP_EXPECTATIONS.get(expression)
    if not expectations:
        return None
    observations_by_concept = _trade_map_observations_by_concept(observations)
    rows: list[dict[str, Any]] = []
    for asset in _TRADE_MAP_RELIABILITY_ASSETS:
        asset_key = str(asset["asset"])
        expected = expectations.get(asset_key)
        if expected is None:
            continue
        points = observations_by_concept.get(str(asset["concept_key"])) or []
        row = _trade_map_historical_row(asset, points, expected_direction=expected[0], action=expected[1])
        if row is not None:
            rows.append(row)
    if not rows:
        return None
    hit_count = len([row for row in rows if row["outcome"] == "hit"])
    average_return = sum(float(row["return_pct"]) for row in rows) / len(rows)
    max_adverse = min(float(row["mae_pct"]) for row in rows)
    return {
        "label": f"五资产 {TRADE_MAP_RELIABILITY_WINDOW_DAYS}日验证",
        "window": f"{TRADE_MAP_RELIABILITY_WINDOW_DAYS}d",
        "sample_count": len(rows),
        "hit_count": hit_count,
        "win_rate": round(hit_count / len(rows), 2),
        "win_rate_label": f"{hit_count}/{len(rows)}",
        "average_return_pct": _round_pct(average_return),
        "max_adverse_excursion_pct": _round_pct(max_adverse),
        "rows": rows,
    }


def _trade_map_observations_by_concept(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, list[tuple[str, float]]]:
    supported = set(TRADE_MAP_RELIABILITY_CONCEPTS)
    grouped: dict[str, dict[str, float]] = {}
    for observation in observations:
        concept_key = str(observation.get("concept_key") or "")
        if concept_key not in supported:
            continue
        value = _number(observation.get("value_numeric"))
        observed_at = _date_string(observation.get("observed_at"))
        if value is None or observed_at is None:
            continue
        grouped.setdefault(concept_key, {})[observed_at] = value
    return {
        concept_key: sorted(points.items(), key=lambda item: item[0])
        for concept_key, points in grouped.items()
        if len(points) >= 2
    }


def _trade_map_historical_row(
    asset: Mapping[str, str],
    points: Sequence[tuple[str, float]],
    *,
    expected_direction: str,
    action: str,
) -> dict[str, Any] | None:
    if len(points) < 2:
        return None
    start_value = points[0][1]
    if start_value == 0:
        return None
    returns = [((value / start_value) - 1.0) * 100.0 for _observed_at, value in points]
    return_pct = returns[-1]
    outcome = "hit" if _trade_map_outcome_hit(return_pct, expected_direction) else "miss"
    mfe_pct, mae_pct = _trade_map_excursions(returns, expected_direction)
    return {
        "asset": str(asset["asset"]),
        "label": str(asset["label"]),
        "concept_key": str(asset["concept_key"]),
        "expected_direction": expected_direction,
        "action": action,
        "return_pct": _round_pct(return_pct),
        "mfe_pct": _round_pct(mfe_pct),
        "mae_pct": _round_pct(mae_pct),
        "outcome": outcome,
    }


def _trade_map_excursions(returns: Sequence[float], expected_direction: str) -> tuple[float, float]:
    if expected_direction == "down":
        return -min(returns), -max(returns)
    return max(returns), min(returns)


def _trade_map_outcome_hit(return_pct: float, expected_direction: str) -> bool:
    if expected_direction == "up":
        return return_pct > 0
    if expected_direction == "down":
        return return_pct < 0
    return abs(return_pct) < 0.5


def _trade_map_portfolio_review(review: Mapping[str, Any]) -> dict[str, Any]:
    rows = _mapping_list(review.get("rows"))
    notional = float(TRADE_MAP_PAPER_NOTIONAL_USD)
    per_asset = notional / len(rows) if rows else 0.0
    pnl = 0.0
    max_adverse = 0.0
    for row in rows:
        return_pct = _number(row.get("return_pct")) or 0.0
        direction = str(row.get("expected_direction") or "")
        signed_return_pct = return_pct if direction == "up" else -return_pct if direction == "down" else 0.0
        pnl += per_asset * signed_return_pct / 100.0
        max_adverse += per_asset * (_number(row.get("mae_pct")) or 0.0) / 100.0
    hit_count = _int_or_none(review.get("hit_count")) or 0
    sample_count = _int_or_none(review.get("sample_count")) or len(rows)
    risk_temperature = _trade_map_risk_temperature(hit_count, sample_count, max_adverse / notional if notional else 0.0)
    pnl_pct = pnl / notional * 100.0 if notional else 0.0
    win_rate_label = str(review.get("win_rate_label") or f"{hit_count}/{sample_count}")
    return {
        "label": "$10K 纸面映射",
        "notional_usd": TRADE_MAP_PAPER_NOTIONAL_USD,
        "deployed_usd": TRADE_MAP_PAPER_NOTIONAL_USD if rows else 0,
        "pnl_usd": round(pnl, 2),
        "pnl_pct": _round_pct(pnl_pct),
        "max_adverse_usd": round(max_adverse, 2),
        "risk_temperature": risk_temperature,
        "summary": f"{_format_usd(notional)} · P&L {_format_usd(pnl, signed=True)} · 胜率 {win_rate_label}",
    }


def _trade_map_risk_temperature(hit_count: int, sample_count: int, adverse_ratio: float) -> str:
    win_rate = hit_count / sample_count if sample_count else 0.0
    if win_rate >= 0.6 and adverse_ratio > -0.05:
        return "低"
    if win_rate >= 0.4 and adverse_ratio > -0.12:
        return "中"
    return "高"


def _trade_map_action_checklist(
    item: Mapping[str, Any],
    portfolio_review: Mapping[str, Any],
) -> list[dict[str, str]]:
    checklist: list[dict[str, str]] = []
    for code in _string_list(item.get("confirms_on"))[:2]:
        label = _code_label(code)
        if not label:
            continue
        checklist.append(
            {
                "kind": "confirm",
                "label": label,
                "description": f"观察 {label} 是否继续确认。",
            }
        )
    for code in _string_list(item.get("invalidates_on"))[:2]:
        label = _code_label(code)
        if not label:
            continue
        checklist.append(
            {
                "kind": "invalidate",
                "label": label,
                "description": f"若 {label}，则撤销该映射。",
            }
        )
    summary = str(portfolio_review.get("summary") or "")
    if summary:
        checklist.append(
            {
                "kind": "position_review",
                "label": "纸面仓位复盘",
                "description": summary,
            }
        )
    return checklist


def _trade_map_holding_period_review(
    expression: str,
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    expectations = _TRADE_MAP_EXPECTATIONS.get(expression)
    if not expectations:
        return None
    observations_by_concept = _trade_map_observations_by_concept(observations)
    rows: list[dict[str, Any]] = []
    for horizon, label, days in _TRADE_MAP_HOLDING_PERIODS:
        horizon_rows: list[dict[str, Any]] = []
        for asset in _TRADE_MAP_RELIABILITY_ASSETS:
            expected = expectations.get(str(asset["asset"]))
            if expected is None:
                continue
            points = observations_by_concept.get(str(asset["concept_key"])) or []
            holding_row = _trade_map_holding_asset_row(points, expected_direction=expected[0], days=days)
            if holding_row is not None:
                horizon_rows.append(holding_row)
        rows.append(_trade_map_holding_period_row(horizon, label, horizon_rows))
    return {"label": "持有期复盘", "rows": rows} if rows else None


def _trade_map_holding_asset_row(
    points: Sequence[tuple[str, float]],
    *,
    expected_direction: str,
    days: int,
) -> dict[str, float | str] | None:
    if len(points) < 2:
        return None
    start_date = _parse_date(points[0][0])
    start_value = points[0][1]
    if start_date is None or start_value == 0:
        return None
    target_date = start_date + timedelta(days=days)
    target_value = None
    for observed_at, value in points[1:]:
        observed_date = _parse_date(observed_at)
        if observed_date is not None and observed_date >= target_date:
            target_value = value
            break
    if target_value is None:
        return None
    return_pct = ((target_value / start_value) - 1.0) * 100.0
    signed_return_pct = _trade_map_signed_return(return_pct, expected_direction)
    return {
        "signed_return_pct": _round_pct(signed_return_pct),
        "outcome": "hit" if signed_return_pct > 0 else "miss",
    }


def _trade_map_holding_period_row(
    horizon: str,
    label: str,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    sample_count = len(rows)
    hit_count = len([row for row in rows if row.get("outcome") == "hit"])
    win_rate = round(hit_count / sample_count, 2) if sample_count else 0.0
    per_asset = float(TRADE_MAP_PAPER_NOTIONAL_USD) / len(_TRADE_MAP_RELIABILITY_ASSETS)
    signed_returns = [_number(row.get("signed_return_pct")) or 0.0 for row in rows]
    pnl = sum(per_asset * value / 100.0 for value in signed_returns)
    average_signed_return = sum(signed_returns) / sample_count if sample_count else 0.0
    return {
        "horizon": horizon,
        "label": label,
        "status": _trade_map_holding_status(sample_count),
        "status_label": _trade_map_holding_status_label(sample_count),
        "sample_count": sample_count,
        "hit_count": hit_count,
        "win_rate": win_rate,
        "win_rate_label": f"{hit_count}/{sample_count}",
        "pnl_usd": round(pnl, 2),
        "average_signed_return_pct": _round_pct(average_signed_return),
    }


def _trade_map_holding_status(sample_count: int) -> str:
    if sample_count >= len(_TRADE_MAP_RELIABILITY_ASSETS):
        return "complete"
    return "partial" if sample_count else "observing"


def _trade_map_holding_status_label(sample_count: int) -> str:
    return {"complete": "已完成", "partial": "部分样本", "observing": "观察中"}[_trade_map_holding_status(sample_count)]


def _trade_map_historical_trust(review: Mapping[str, Any]) -> dict[str, Any]:
    rows = _mapping_list(review.get("rows"))
    sample_count = sum(_int_or_none(row.get("sample_count")) or 0 for row in rows)
    hit_count = sum(_int_or_none(row.get("hit_count")) or 0 for row in rows)
    score_pct = round(hit_count / sample_count * 100.0, 1) if sample_count else 0.0
    quality = _trade_map_trust_quality(score_pct)
    return {
        "label": "历史可信度",
        "score_pct": score_pct,
        "quality": quality,
        "sample_count": sample_count,
        "hit_count": hit_count,
        "summary": f"历史可信度 {score_pct:.1f}% · {quality} · {sample_count} 个样本",
    }


def _trade_map_trust_quality(score_pct: float) -> str:
    if score_pct >= 70.0:
        return "高"
    if score_pct >= 50.0:
        return "中"
    return "低"


def _trade_map_signed_return(return_pct: float, expected_direction: str) -> float:
    if expected_direction == "up":
        return return_pct
    if expected_direction == "down":
        return -return_pct
    return 0.0


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _format_usd(value: float, *, signed: bool = False) -> str:
    rounded = round(float(value))
    sign = "+" if signed and rounded > 0 else "-" if signed and rounded < 0 else ""
    return f"{sign}${abs(rounded):,}"


def _event_catalyst_candidates(observations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    candidate_catalysts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for observation in observations:
        concept_key = str(observation.get("concept_key") or "")
        if not concept_key.startswith("event:"):
            continue
        catalyst = _event_catalyst(observation)
        if catalyst is None:
            continue
        candidate_catalysts.append(catalyst)
    catalysts: list[dict[str, Any]] = []
    for catalyst in sorted(candidate_catalysts, key=_event_catalyst_sort_key):
        if catalyst["code"] in seen:
            continue
        seen.add(catalyst["code"])
        catalysts.append(catalyst)
    return catalysts


def _event_flow_classification(catalyst: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    kind = str(catalyst.get("kind") or "")
    code = str(catalyst.get("code") or "")
    if kind == "fed_text" or code.startswith("official_fed_text:"):
        return ("policy", "政策", "fed_communication", "Fed 沟通", "跟踪措辞、投票分歧和政策路径信号。")
    if kind == "auction_calendar":
        return (
            "treasury_supply",
            "国债供给",
            "settlement_watch",
            "拍卖/交割",
            "关注拍卖需求、公告规模和交割日资金占用。",
        )
    if kind == "auction_result":
        return (
            "treasury_supply",
            "国债供给",
            "auction_result",
            "拍卖结果",
            "拍卖结果作为国债需求和期限溢价压力证据。",
        )
    if code.startswith("official_calendar:fomc"):
        return ("policy", "政策", "policy_path", "政策路径", "利率路径和流动性定价。")
    if code.startswith("official_calendar:bls") or code.startswith("official_calendar:bea"):
        return (
            "economic_data",
            "经济数据",
            "release_revision",
            "实际/修正",
            "跟踪官方实际值、前值修正和数据口径变化。",
        )
    return ("official_event", "官方事件", "calendar_watch", "日历", "事件窗口内重新评估宏观读法。")


def _event_catalyst_sort_key(catalyst: Mapping[str, Any]) -> tuple[int, float, int, str]:
    kind = str(catalyst.get("kind") or "")
    value = _number(catalyst.get("value"))
    code = str(catalyst.get("code") or "")
    observed_at = str(catalyst.get("observed_at") or "")
    observed_date = _parse_date(observed_at)
    observed_ordinal = observed_date.toordinal() if observed_date is not None else 0
    if kind in {"calendar", "auction_calendar"} and value is not None and value >= 0:
        return (0, value, observed_ordinal, code)
    return (1, 0.0, -observed_ordinal, code)


def _event_catalyst(observation: Mapping[str, Any]) -> dict[str, Any] | None:
    raw_payload = _event_raw_payload(observation)
    series_key = str(raw_payload.get("series_key") or observation.get("series_key") or "").strip()
    concept_key = str(observation.get("concept_key") or "").strip()
    if not series_key or not concept_key:
        return None
    value = _number(observation.get("value_numeric"))
    if value is None:
        value = _number(raw_payload.get("value"))
    observed_at = _date_string(observation.get("observed_at") or raw_payload.get("observed_at"))
    provenance = _mapping_list(raw_payload.get("provenance"))
    first_provenance = provenance[0] if provenance else {}
    provider = str(observation.get("source_name") or raw_payload.get("provider") or "").strip()
    kind = _event_kind(series_key)
    text_value = _event_text_value(raw_payload=raw_payload, provenance=first_provenance)
    source_url = _event_source_url(raw_payload=raw_payload, provenance=first_provenance)
    document_type = _event_document_type(
        kind=kind,
        raw_payload=raw_payload,
        provenance=first_provenance,
    )
    speaker = _event_speaker(
        kind=kind,
        document_type=document_type,
        raw_payload=raw_payload,
        provenance=first_provenance,
        text_value=text_value,
    )
    catalyst = {
        "code": series_key,
        "label": _event_label(concept_key),
        "description": _event_description(
            kind=kind,
            observed_at=observed_at,
            value=value,
            provenance=first_provenance,
            text_value=text_value,
        ),
        "source": _provider_label(provider),
        "kind": kind,
        "observed_at": observed_at,
        "value": value,
    }
    if source_url:
        catalyst["source_url"] = source_url
    if document_type:
        catalyst["document_type"] = document_type
    if speaker:
        catalyst["speaker"] = speaker
    return catalyst


def _event_raw_payload(observation: Mapping[str, Any]) -> Mapping[str, Any]:
    raw_payload = observation.get("raw_payload_json")
    if isinstance(raw_payload, Mapping):
        return raw_payload
    raw_payload = observation.get("raw_payload")
    if isinstance(raw_payload, Mapping):
        return raw_payload
    return {}


def _event_kind(series_key: str) -> str:
    if series_key.startswith("official_calendar:"):
        return "calendar"
    if series_key.startswith("official_fed_text:"):
        return "fed_text"
    if series_key.startswith("treasury_auction:") and series_key.endswith("_next_auction_days"):
        return "auction_calendar"
    if series_key.startswith("treasury_auction:"):
        return "auction_result"
    return "event"


def _event_label(concept_key: str) -> str:
    return _concept_required_text(concept_key, "label")


def _event_description(
    *,
    kind: str,
    observed_at: str | None,
    value: float | None,
    provenance: Mapping[str, Any],
    text_value: str | None = None,
) -> str:
    date_label = observed_at or "--"
    if kind == "calendar":
        days_label = _event_days_label(value)
        event_time = str(provenance.get("event_time") or provenance.get("event_time_et") or "").strip()
        reference_period = str(provenance.get("reference_period") or "").strip()
        parts = [date_label, days_label, event_time, reference_period]
        return " · ".join(part for part in parts if part)
    if kind == "auction_result":
        value_label = _event_number_label(value)
        cusip = str(provenance.get("cusip") or "").strip()
        parts = [date_label, value_label, f"CUSIP {cusip}" if cusip else ""]
        return " · ".join(part for part in parts if part)
    if kind == "auction_calendar":
        days_label = _event_days_label(value)
        announcement_date = str(provenance.get("announcement_date") or "").strip()
        settlement_date = str(provenance.get("settlement_date") or "").strip()
        reopening_label = "Reopen" if bool(provenance.get("reopening")) else ""
        parts = [
            date_label,
            days_label,
            f"{announcement_date} 公告" if announcement_date else "",
            f"{settlement_date} 交割" if settlement_date else "",
            reopening_label,
        ]
        return " · ".join(part for part in parts if part)
    if kind == "fed_text":
        return " · ".join(part for part in (date_label, text_value or "") if part)
    value_label = _event_number_label(value)
    return " · ".join(part for part in (date_label, value_label) if part)


def _event_text_value(*, raw_payload: Mapping[str, Any], provenance: Mapping[str, Any]) -> str | None:
    candidates = (
        raw_payload.get("value"),
        provenance.get("document_title"),
        provenance.get("description"),
    )
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text
    return None


def _event_source_url(*, raw_payload: Mapping[str, Any], provenance: Mapping[str, Any]) -> str | None:
    candidates = (
        provenance.get("source_url"),
        raw_payload.get("source_url"),
        raw_payload.get("url"),
    )
    for candidate in candidates:
        source_url = str(candidate or "").strip()
        if source_url.startswith(("https://", "http://")):
            return source_url
    return None


def _event_document_type(
    *,
    kind: str,
    raw_payload: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> str | None:
    if kind != "fed_text":
        return None
    for candidate in (provenance.get("document_type"), raw_payload.get("document_type")):
        document_type = str(candidate or "").strip()
        if document_type:
            return document_type
    return None


def _event_speaker(
    *,
    kind: str,
    document_type: str | None,
    raw_payload: Mapping[str, Any],
    provenance: Mapping[str, Any],
    text_value: str | None,
) -> str | None:
    if kind != "fed_text" or document_type != "speech":
        return None
    for candidate in (provenance.get("speaker"), raw_payload.get("speaker")):
        speaker = str(candidate or "").strip()
        if speaker:
            return speaker
    title = text_value or _event_text_value(raw_payload=raw_payload, provenance=provenance)
    if not title or "," not in title:
        return None
    speaker = title.split(",", 1)[0].strip()
    return speaker or None


def _event_days_label(value: float | None) -> str:
    if value is None:
        return ""
    return f"还有 {_event_number_label(value)} 天"


def _event_number_label(value: float | None) -> str:
    if value is None:
        return ""
    return str(int(value)) if value.is_integer() else f"{value:.2f}"


def _compact_signal(item: Mapping[str, Any]) -> dict[str, Any] | None:
    node = str(item.get("node") or "").strip()
    label = str(item.get("label") or _code_label(str(item.get("code") or "")) or "").strip()
    if not label:
        return None
    payload = {
        "code": str(item.get("code") or ""),
        "label": label,
        "description": str(item.get("description") or ""),
        "node": _section_label(node),
        "kind": str(item.get("kind") or "signal"),
    }
    for key in (
        "change_label",
        "value_label",
        "observed_at",
        "source_label",
        "severity",
        "severity_label",
        "evidence_label",
    ):
        value = item.get(key)
        if value:
            payload[key] = value
    return payload


def _compact_quality_blocker(item: Mapping[str, Any]) -> dict[str, Any]:
    code = str(item.get("code") or "").strip()
    label = str(item.get("label") or "").strip()
    if not label:
        raise ValueError("Missing macro quality blocker label metadata")
    severity = _quality_blocker_severity(item, code=code)
    return {
        "code": code,
        "label": label,
        "description": str(item.get("description") or item.get("remediation_hint") or label),
        "severity": severity,
    }


def _quality_blocker_severity(item: Mapping[str, Any], *, code: str) -> str:
    severity = str(item.get("severity") or "").strip().lower()
    if not severity:
        raise ValueError(f"Missing macro quality blocker severity metadata: {code or '<missing>'}")
    return _required_macro_severity(severity)


def _evidence_item(item: Mapping[str, Any]) -> dict[str, Any] | None:
    code = str(item.get("code") or "")
    label = str(item.get("label") or _code_label(code) or "").strip()
    if not label:
        return None
    payload = {
        "code": code,
        "label": label,
        "description": item.get("description") or "",
    }
    if item.get("time_window"):
        payload["time_window"] = item.get("time_window")
    if item.get("severity"):
        payload["severity"] = item.get("severity")
    return payload


def _provenance(
    *,
    snapshot: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    facts_max_observed_at: object,
    projection_lag_days: int | None,
    projection_behind_facts: bool,
) -> dict[str, Any]:
    rows = _observation_source_rows(observations)
    return {
        "projection_version": snapshot.get("projection_version"),
        "source_snapshot_id": snapshot.get("snapshot_id"),
        "currentness": {
            "facts_max_observed_at": _date_string(facts_max_observed_at),
            "projection_lag_days": projection_lag_days,
            "projection_behind_facts": bool(projection_behind_facts),
        },
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
            "row_id": _source_row_id(_provider_label(source)),
            "source_label": _provider_label(source),
            "status": row["status"],
            "status_label": _status_label(row["status"]),
            "latest_observed_at": row["latest_observed_at"],
            "concept_count": len(row["concepts"]),
            "notes": row["notes"],
        }
        for source, row in sorted(by_source.items())
    ]


def _source_row_id(source_label: str) -> str:
    key = "_".join(part for part in source_label.replace("/", " ").split() if part)
    return f"source:{key}"


def _data_health(
    *,
    config: MacroModuleConfig,
    data_gaps: Sequence[Any],
    feature_map: Mapping[str, Any],
    concept_keys: Sequence[str],
    primary_chart: Mapping[str, Any],
    snapshot_status: str,
) -> dict[str, Any]:
    global_gaps = [_gap_payload(gap) for gap in data_gaps]
    global_scope = _global_gap_scope(config, snapshot_status=snapshot_status)
    global_gaps = [_with_scope(gap, global_scope) for gap in global_gaps]

    module_gaps: list[dict[str, Any]] = []
    snapshot_missing = any(gap.get("code") == "macro_view_snapshot_missing" for gap in global_gaps)
    if snapshot_missing:
        module_gaps.extend(_with_scope(gap, "module_blocker") for gap in global_gaps)
    required_concepts = set(config.required_concepts)
    for concept_key in concept_keys:
        feature = feature_map.get(concept_key)
        if isinstance(feature, Mapping):
            module_gaps.extend(
                _with_concept_gap_scope(_gap_payload(gap), concept_key, required=concept_key in required_concepts)
                for gap in _sequence(feature.get("data_gaps"))
            )
    if not snapshot_missing:
        module_gaps.extend(_asset_depth_reference_gaps(config.module_id, feature_map))
        module_gaps.extend(_crypto_derivative_reference_gaps(config.module_id, feature_map))
        module_gaps.extend(_credit_depth_reference_gaps(config.module_id, feature_map))
        module_gaps.extend(_economy_depth_reference_gaps(config.module_id, feature_map))
        module_gaps.extend(_liquidity_depth_reference_gaps(config.module_id, feature_map))
        module_gaps.extend(_policy_corridor_reference_gaps(config.module_id, feature_map))
        module_gaps.extend(_rates_depth_reference_gaps(config.module_id, feature_map))
        module_gaps.extend(_volatility_depth_reference_gaps(config.module_id, feature_map))
    chart_gaps = [
        _with_scope(
            _gap_payload(
                {
                    "code": f"chart_missing:{concept_key}",
                    "label": f"主图缺少序列：{_concept_short_label(concept_key)}",
                    "severity": "warning",
                    "concept_key": concept_key,
                    "remediation_hint": "补齐该图表序列后重新生成宏观投影。",
                }
            ),
            "chart_blocker",
        )
        for concept_key in _string_list(primary_chart.get("missing_concept_keys"))
    ]
    status = _data_health_status(
        module_gaps=module_gaps,
        chart_gaps=chart_gaps,
        global_gaps=global_gaps,
        primary_chart=primary_chart,
        feature_map=feature_map,
        concept_keys=concept_keys,
        global_reference_gaps_affect_status=config.module_id == "overview" and global_scope == "global_reference",
    )
    return {
        "summary_status": status,
        "module_gaps": _unique_gaps(module_gaps),
        "chart_gaps": _unique_gaps(chart_gaps),
        "global_gaps": _unique_gaps(global_gaps),
    }


def _asset_depth_reference_gaps(module_id: str, feature_map: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups: tuple[_ReferenceGapGroup, ...]
    if module_id == "assets":
        groups = (
            (
                "asset_risk_breadth_missing",
                "缺少 NDX/RUT：无法判断风险资产广度",
                ("asset:ndx", "asset:rut"),
                "all",
            ),
            (
                "asset_duration_proxy_missing",
                "缺少 TLT：无法判断久期资产确认",
                ("asset:tlt",),
                "any",
            ),
            (
                "asset_credit_stress_missing",
                "缺少 HYG/LQD/HY OAS：无法判断信用 beta 压力",
                ("asset:hyg", "asset:lqd", "credit:hy_oas"),
                "any",
            ),
            (
                "asset_volatility_missing",
                "缺少 VIX：无法判断波动率确认",
                ("vol:vix",),
                "any",
            ),
            (
                "asset_commodity_depth_missing",
                "缺少黄金/天然气/铜：无法判断商品冲击广度",
                ("commodity:gold_futures", "commodity:natgas_futures", "commodity:copper_futures"),
                "any",
            ),
        )
        remediation = "同步 macro-core 大类资产深度源后重新投影 retained assets。"
    elif module_id == "assets/equities":
        groups = (
            (
                "equity_growth_leadership_missing",
                "缺少 NDX/QQQ：无法判断成长股领导力",
                ("asset:ndx", "asset:qqq"),
                "all",
            ),
            (
                "equity_small_caps_missing",
                "缺少 RUT/IWM：无法判断小盘风险广度",
                ("asset:rut", "asset:iwm"),
                "all",
            ),
            (
                "equity_global_sector_missing",
                "缺少 EFA/EEM/SMH/SOXX：无法判断全球与半导体确认",
                ("asset:efa", "asset:eem", "asset:smh", "asset:soxx"),
                "any",
            ),
            (
                "equity_positioning_missing",
                "缺少 CFTC S&P 仓位：无法判断投机拥挤或防守",
                ("positioning:sp500_net_noncommercial",),
                "any",
            ),
        )
        remediation = "同步 macro-core 美股/仓位深度源后重新投影 retained assets/equities。"
    elif module_id == "assets/bonds":
        groups = (
            (
                "bond_intermediate_duration_missing",
                "缺少 SHY/IEF：无法判断短中久期确认",
                ("asset:shy", "asset:ief"),
                "any",
            ),
            (
                "bond_inflation_protection_missing",
                "缺少 TIP：无法判断通胀保护债确认",
                ("asset:tip",),
                "any",
            ),
            (
                "bond_credit_beta_missing",
                "缺少 HYG/JNK/LQD：无法判断信用 ETF beta",
                ("asset:hyg", "asset:jnk", "asset:lqd"),
                "any",
            ),
            (
                "bond_credit_spreads_missing",
                "缺少 HY/IG OAS：无法判断信用利差确认",
                ("credit:hy_oas", "credit:ig_oas"),
                "any",
            ),
            (
                "bond_aggregate_missing",
                "缺少 BND：无法判断综合债券确认",
                ("asset:bnd",),
                "any",
            ),
        )
        remediation = "同步 macro-core 债券深度源后重新投影 retained assets/bonds。"
    elif module_id == "assets/commodities":
        groups = (
            ("commodity_brent_missing", "缺少 Brent：无法交叉验证原油冲击", ("commodity:brent",), "any"),
            (
                "commodity_natural_gas_missing",
                "缺少 NatGas：无法判断能源冲击广度",
                ("commodity:natgas", "commodity:natgas_futures", "asset:ung"),
                "any",
            ),
            (
                "commodity_precious_metals_missing",
                "缺少黄金/白银：无法判断贵金属防守确认",
                ("commodity:gold_futures", "commodity:silver_futures", "asset:gld", "asset:slv"),
                "any",
            ),
            (
                "commodity_copper_missing",
                "缺少铜：无法判断工业需求确认",
                ("commodity:copper_futures", "asset:cper"),
                "any",
            ),
            (
                "commodity_etf_proxy_missing",
                "缺少商品 ETF 代理：无法交叉验证期货信号",
                ("asset:uso", "asset:ung", "asset:gld", "asset:slv", "asset:cper"),
                "any",
            ),
        )
        remediation = "同步 macro-core 商品深度源后重新投影 retained assets/commodities。"
    elif module_id == "assets/fx":
        groups = (
            ("fx_broad_dollar_missing", "缺少广义美元：无法验证 DXY 之外的美元压力", ("fx:broad_dollar",), "any"),
            (
                "fx_g10_pairs_missing",
                "缺少 EUR/GBP 交叉验证：无法判断 G10 美元广度",
                ("fx:eurusd", "fx:gbpusd", "fx:fred_eurusd", "fx:fred_gbpusd"),
                "any",
            ),
            (
                "fx_asia_pairs_missing",
                "缺少 JPY/CNY/KRW：无法判断亚洲美元压力",
                ("fx:usdjpy", "fx:usdcny", "fx:usdkrw", "fx:fred_usdjpy", "fx:fred_usdcny"),
                "any",
            ),
            (
                "fx_etf_proxy_missing",
                "缺少 UUP/FXE/FXY：无法用 ETF 代理交叉验证美元压力",
                ("asset:uup", "asset:fxe", "asset:fxy"),
                "any",
            ),
        )
        remediation = "同步 macro-core 外汇深度源后重新投影 retained assets/fx。"
    else:
        return []

    gaps: list[dict[str, Any]] = []
    for code, label, concept_keys, coverage_rule in groups:
        if coverage_rule == "all":
            is_covered = all(concept_key in feature_map for concept_key in concept_keys)
        else:
            is_covered = any(concept_key in feature_map for concept_key in concept_keys)
        if is_covered:
            continue
        gaps.append(
            {
                "code": code,
                "label": label,
                "severity": "warning",
                "score_participation": False,
                "scope": "module_reference",
                "concept_required": False,
                "remediation_hint": remediation,
            }
        )
    return gaps


def _crypto_derivative_reference_gaps(module_id: str, feature_map: Mapping[str, Any]) -> list[dict[str, Any]]:
    if module_id != "assets/crypto":
        return []
    groups = (
        (
            "crypto_derivatives_oi_missing",
            "缺少加密衍生品 OI：无法判断杠杆扩张或出清",
            (
                "crypto_derivatives:okx_btc_oi_usd",
                "crypto_derivatives:deribit_btc_oi_usd",
                "crypto_derivatives:okx_eth_oi_usd",
                "crypto_derivatives:deribit_eth_oi_usd",
            ),
        ),
        (
            "crypto_derivatives_funding_missing",
            "缺少加密衍生品 funding：无法判断多空拥挤",
            (
                "crypto_derivatives:okx_btc_funding",
                "crypto_derivatives:deribit_btc_funding_8h",
                "crypto_derivatives:okx_eth_funding",
                "crypto_derivatives:deribit_eth_funding_8h",
            ),
        ),
        (
            "crypto_derivatives_basis_missing",
            "缺少加密衍生品 basis：无法判断正基差或贴水",
            (
                "crypto_derivatives:okx_btc_basis",
                "crypto_derivatives:deribit_btc_basis",
                "crypto_derivatives:okx_eth_basis",
                "crypto_derivatives:deribit_eth_basis",
            ),
        ),
        (
            "crypto_derivatives_dvol_missing",
            "缺少加密 DVOL：无法判断期权波动压力",
            (
                "crypto_derivatives:deribit_btc_vol_index",
                "crypto_derivatives:deribit_eth_vol_index",
            ),
        ),
    )
    gaps: list[dict[str, Any]] = []
    for code, label, concept_keys in groups:
        if any(concept_key in feature_map for concept_key in concept_keys):
            continue
        gaps.append(
            {
                "code": code,
                "label": label,
                "severity": "warning",
                "score_participation": False,
                "scope": "module_reference",
                "concept_required": False,
                "remediation_hint": "同步 crypto-derivatives-core 后重新投影 retained assets/crypto。",
            }
        )
    return gaps


def _credit_depth_reference_gaps(module_id: str, feature_map: Mapping[str, Any]) -> list[dict[str, Any]]:
    if module_id != "credit/stress":
        return []
    groups = (
        (
            "credit_etf_pressure_missing",
            "缺少 HYG/LQD 信用 ETF：无法判断 ETF 流动性确认",
            ("asset:hyg", "asset:lqd"),
            "all",
        ),
        (
            "credit_financial_conditions_missing",
            "缺少 NFCI 金融条件：无法判断信用压力是否扩散到广义融资条件",
            ("credit:nfci",),
            "all",
        ),
        (
            "credit_bank_lending_missing",
            "缺少 SLOOS 银行信贷：无法判断贷款标准和需求变化",
            (
                "credit:sloos_ci_large_tightening",
                "credit:sloos_ci_small_tightening",
                "credit:sloos_ci_large_demand",
                "credit:sloos_ci_small_demand",
            ),
            "any",
        ),
        (
            "credit_loan_quality_missing",
            "缺少贷款质量：无法判断违约和核销压力",
            (
                "credit:business_delinquency",
                "credit:consumer_delinquency",
                "credit:business_charge_off",
                "credit:consumer_charge_off",
            ),
            "any",
        ),
    )
    gaps: list[dict[str, Any]] = []
    for code, label, concept_keys, coverage_rule in groups:
        if coverage_rule == "all":
            is_covered = all(concept_key in feature_map for concept_key in concept_keys)
        else:
            is_covered = any(concept_key in feature_map for concept_key in concept_keys)
        if is_covered:
            continue
        gaps.append(
            {
                "code": code,
                "label": label,
                "severity": "warning",
                "score_participation": False,
                "scope": "module_reference",
                "concept_required": False,
                "remediation_hint": "同步 macro-core 信用深度源后重新投影 retained credit/stress。",
            }
        )
    return gaps


def _economy_depth_reference_gaps(module_id: str, feature_map: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups: tuple[_ReferenceGapGroup, ...]
    if module_id == "economy/gdp":
        groups = (
            (
                "growth_nominal_gdp_missing",
                "缺少名义 GDP：无法拆分实际增长与价格贡献",
                ("economy:gdp_nominal",),
                "any",
            ),
            (
                "growth_nowcast_missing",
                "缺少 GDPNow：无法判断季度内增长动能",
                ("economy:gdp_nowcast",),
                "any",
            ),
            (
                "growth_production_housing_missing",
                "缺少工业生产/住房开工：无法确认实体活动广度",
                ("economy:industrial_production", "economy:housing_starts"),
                "all",
            ),
            (
                "growth_consumption_missing",
                "缺少实际 PCE/零售销售：无法确认消费需求动能",
                ("consumer:pce_real", "consumer:retail_sales"),
                "all",
            ),
            (
                "growth_consumer_depth_missing",
                "缺少名义 PCE/储蓄率/消费者信心：无法判断消费缓冲",
                ("consumer:pce_nominal", "consumer:saving_rate", "consumer:umich_sentiment"),
                "any",
            ),
        )
        remediation = "同步 macro-core 增长/消费深度源后重新投影 retained economy/gdp。"
    elif module_id == "economy/employment":
        groups = (
            (
                "employment_job_openings_missing",
                "缺少 JOLTS 职位空缺：无法判断劳动力需求降温",
                ("labor:job_openings",),
                "any",
            ),
            (
                "employment_wage_missing",
                "缺少平均时薪：无法判断工资通胀压力",
                ("labor:avg_hourly_earnings",),
                "any",
            ),
            (
                "employment_participation_missing",
                "缺少劳动参与率：无法判断劳动力供给缓冲",
                ("labor:participation",),
                "any",
            ),
        )
        remediation = "同步 macro-core 就业深度源后重新投影 retained economy/employment。"
    elif module_id == "economy/inflation":
        groups = (
            (
                "inflation_pce_missing",
                "缺少 PCE/Core PCE：无法判断 Fed 偏好的通胀口径",
                ("inflation:pce", "inflation:core_pce"),
                "all",
            ),
            (
                "inflation_deflator_missing",
                "缺少 GDP 平减指数：无法判断增长价格分解",
                ("inflation:gdp_deflator",),
                "any",
            ),
            (
                "inflation_market_expectations_missing",
                "缺少市场通胀预期曲线：无法判断 breakeven/forward 确认",
                ("inflation:5y_breakeven", "inflation:10y_breakeven", "inflation:5y5y_forward"),
                "all",
            ),
            (
                "inflation_consumer_expectations_missing",
                "缺少消费者通胀预期：无法判断密歇根预期压力",
                ("inflation:mich_1y_expectation",),
                "any",
            ),
        )
        remediation = "同步 macro-core 通胀深度源后重新投影 retained economy/inflation。"
    else:
        return []

    gaps: list[dict[str, Any]] = []
    for code, label, concept_keys, coverage_rule in groups:
        if coverage_rule == "all":
            is_covered = all(concept_key in feature_map for concept_key in concept_keys)
        else:
            is_covered = any(concept_key in feature_map for concept_key in concept_keys)
        if is_covered:
            continue
        gaps.append(
            {
                "code": code,
                "label": label,
                "severity": "warning",
                "score_participation": False,
                "scope": "module_reference",
                "concept_required": False,
                "remediation_hint": remediation,
            }
        )
    return gaps


def _liquidity_depth_reference_gaps(module_id: str, feature_map: Mapping[str, Any]) -> list[dict[str, Any]]:
    if module_id != "liquidity/rrp-tga":
        return []
    groups = (
        (
            "liquidity_balance_sheet_missing",
            "缺少 Fed 资产/准备金余额：无法判断净流动性和准备金缓冲",
            ("liquidity:fed_assets", "liquidity:reserve_balances"),
            "all",
        ),
        (
            "liquidity_secured_corridor_missing",
            "缺少 SOFR/IORB：无法判断有担保融资走廊压力",
            ("liquidity:sofr", "fed:iorb"),
            "all",
        ),
        (
            "liquidity_repo_depth_missing",
            "缺少 BGCR/TGCR：无法判断 repo 深度压力",
            ("liquidity:bgcr", "liquidity:tgcr"),
            "all",
        ),
        (
            "liquidity_volume_depth_missing",
            "缺少 SOFR/BGCR/TGCR 成交量：无法判断 repo 交易深度",
            ("liquidity:sofr_volume", "liquidity:bgcr_volume", "liquidity:tgcr_volume"),
            "all",
        ),
        (
            "liquidity_nyfed_operations_missing",
            "缺少 NY Fed RRP/SRF：无法判断官方工具使用压力",
            ("liquidity:nyfed_rrp", "liquidity:srf"),
            "all",
        ),
    )
    gaps: list[dict[str, Any]] = []
    for code, label, concept_keys, coverage_rule in groups:
        if coverage_rule == "all":
            is_covered = all(concept_key in feature_map for concept_key in concept_keys)
        else:
            is_covered = any(concept_key in feature_map for concept_key in concept_keys)
        if is_covered:
            continue
        gaps.append(
            {
                "code": code,
                "label": label,
                "severity": "warning",
                "score_participation": False,
                "scope": "module_reference",
                "concept_required": False,
                "remediation_hint": "同步 macro-core 流动性深度源后重新投影 retained liquidity/rrp-tga。",
            }
        )
    return gaps


def _policy_corridor_reference_gaps(module_id: str, feature_map: Mapping[str, Any]) -> list[dict[str, Any]]:
    if module_id != "rates/fed-funds":
        return []
    groups = (
        (
            "policy_daily_fed_funds_missing",
            "缺少 DFF：无法复核每日有效联邦基金利率与 EFFR 偏差",
            ("fed:dff",),
            "any",
        ),
        (
            "policy_sofr_30d_missing",
            "缺少 SOFR 30D：无法判断有担保融资压力是否持续",
            ("fed:sofr_30d",),
            "any",
        ),
        (
            "policy_unsecured_funding_missing",
            "缺少 OBFR：无法判断广义无担保融资压力",
            ("fed:obfr",),
            "any",
        ),
        (
            "policy_volume_depth_missing",
            "缺少 EFFR/OBFR 成交量：无法判断政策走廊交易深度",
            ("fed:effr_volume", "fed:obfr_volume"),
            "all",
        ),
    )
    gaps: list[dict[str, Any]] = []
    for code, label, concept_keys, coverage_rule in groups:
        if coverage_rule == "all":
            is_covered = all(concept_key in feature_map for concept_key in concept_keys)
        else:
            is_covered = any(concept_key in feature_map for concept_key in concept_keys)
        if is_covered:
            continue
        gaps.append(
            {
                "code": code,
                "label": label,
                "severity": "warning",
                "score_participation": False,
                "scope": "module_reference",
                "concept_required": False,
                "remediation_hint": "同步 macro-core 政策走廊深度源后重新投影 retained rates/fed-funds。",
            }
        )
    return gaps


def _rates_depth_reference_gaps(module_id: str, feature_map: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups: tuple[_ReferenceGapGroup, ...]
    if module_id == "rates/yield-curve":
        groups = (
            (
                "yield_curve_front_end_missing",
                "缺少 3M 国债收益率：无法判断 3m10y 前端倒挂",
                ("rates:dgs3mo",),
                "any",
            ),
            (
                "yield_curve_belly_missing",
                "缺少 5Y 国债收益率：无法判断曲线腹部压力",
                ("rates:dgs5",),
                "any",
            ),
            (
                "yield_curve_long_end_missing",
                "缺少 30Y 国债收益率：无法判断 5s30s 长端斜率",
                ("rates:dgs30",),
                "any",
            ),
            (
                "yield_curve_real_rate_decomposition_missing",
                "缺少 5Y/10Y TIPS：无法拆分名义利率与实际利率贡献",
                ("rates:real_5y", "rates:real_10y"),
                "all",
            ),
            (
                "yield_curve_breakeven_decomposition_missing",
                "缺少 5Y/10Y breakeven：无法拆分通胀补偿贡献",
                ("inflation:5y_breakeven", "inflation:10y_breakeven"),
                "all",
            ),
        )
        remediation = "同步 macro-core 曲线和 TIPS/breakeven 深度源后重新投影 retained rates/yield-curve。"
    elif module_id == "rates/real-rates":
        groups = (
            (
                "real_rates_tips_curve_missing",
                "缺少 5Y/10Y/30Y TIPS 曲线：无法判断实际利率期限结构",
                ("rates:real_5y", "rates:real_10y", "rates:real_30y"),
                "all",
            ),
            (
                "real_rates_breakeven_curve_missing",
                "缺少 5Y/10Y breakeven：无法判断通胀补偿曲线",
                ("inflation:5y_breakeven", "inflation:10y_breakeven"),
                "all",
            ),
            (
                "real_rates_forward_inflation_missing",
                "缺少 5Y5Y forward：无法判断长期通胀预期锚定",
                ("inflation:5y5y_forward",),
                "any",
            ),
        )
        remediation = "同步 macro-core TIPS 和 breakeven 深度源后重新投影 retained rates/real-rates。"
    else:
        return []

    gaps: list[dict[str, Any]] = []
    for code, label, concept_keys, coverage_rule in groups:
        if coverage_rule == "all":
            is_covered = all(concept_key in feature_map for concept_key in concept_keys)
        else:
            is_covered = any(concept_key in feature_map for concept_key in concept_keys)
        if is_covered:
            continue
        gaps.append(
            {
                "code": code,
                "label": label,
                "severity": "warning",
                "score_participation": False,
                "scope": "module_reference",
                "concept_required": False,
                "remediation_hint": remediation,
            }
        )
    return gaps


def _volatility_depth_reference_gaps(module_id: str, feature_map: Mapping[str, Any]) -> list[dict[str, Any]]:
    if module_id != "volatility/vix":
        return []
    groups = (
        (
            "vol_event_premium_missing",
            "缺少短端事件波动率：无法判断 VIX1D/VIX9D 前端溢价",
            ("vol:vix1d", "vol:vix9d"),
        ),
        (
            "vol_tail_depth_missing",
            "缺少波动率凸性/尾部风险：无法判断 VVIX/SKEW",
            ("vol:vvix", "vol:skew"),
        ),
        (
            "vol_rates_vol_missing",
            "缺少 MOVE：无法判断利率波动率压力",
            ("vol:move",),
        ),
        (
            "vol_futures_proxy_missing",
            "缺少 VIXY/VIXM：无法判断 VIX 期货代理压力",
            ("asset:vixy", "asset:vixm"),
        ),
    )
    gaps: list[dict[str, Any]] = []
    for code, label, concept_keys in groups:
        if any(concept_key in feature_map for concept_key in concept_keys):
            continue
        gaps.append(
            {
                "code": code,
                "label": label,
                "severity": "warning",
                "score_participation": False,
                "scope": "module_reference",
                "concept_required": False,
                "remediation_hint": "同步 macro-core 波动率深度源后重新投影 retained volatility/vix。",
            }
        )
    return gaps


def _availability_gaps(data_health: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        *[dict(gap) for gap in _mapping_list(data_health.get("module_gaps"))],
        *[dict(gap) for gap in _mapping_list(data_health.get("chart_gaps"))],
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


def _with_concept_gap_scope(gap: Mapping[str, Any], concept_key: str, *, required: bool) -> dict[str, Any]:
    payload = _with_scope(gap, "module_blocker" if required else "module_reference")
    payload["concept_key"] = concept_key
    payload["concept_required"] = required
    return payload


def _global_gap_scope(config: MacroModuleConfig, *, snapshot_status: str) -> str:
    if config.module_id != "overview":
        return "global_reference"
    return "global_reference" if snapshot_status == "ready" else "global_blocker"


def _data_health_status(
    *,
    module_gaps: Sequence[Mapping[str, Any]],
    chart_gaps: Sequence[Mapping[str, Any]],
    global_gaps: Sequence[Mapping[str, Any]],
    primary_chart: Mapping[str, Any],
    feature_map: Mapping[str, Any],
    concept_keys: Sequence[str],
    global_reference_gaps_affect_status: bool = False,
) -> str:
    global_blockers = [gap for gap in global_gaps if gap.get("scope") == "global_blocker"]
    module_blockers = [gap for gap in module_gaps if gap.get("scope") == "module_blocker"]
    if any(gap.get("severity") == "error" for gap in global_blockers):
        return "missing"
    if any(gap.get("severity") == "error" for gap in module_blockers):
        return "missing"
    chart_status = _status_key(primary_chart.get("status"))
    if chart_status == "missing" or (
        concept_keys and not any(concept_key in feature_map for concept_key in concept_keys)
    ):
        return "missing"
    if (
        global_blockers
        or (global_reference_gaps_affect_status and global_gaps)
        or module_gaps
        or chart_gaps
        or chart_status in {"partial", "insufficient_history"}
    ):
        return "partial"
    return "ok"


def _transmission(
    *,
    config: MacroModuleConfig,
    chain: Mapping[str, Any],
    feature_map: Mapping[str, Any],
    data_health: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if config.module_id == "overview":
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
        return nodes

    first_concept = next(
        (concept_key for concept_key in _module_concept_keys(config) if concept_key in feature_map), None
    )
    source_status = "ok" if first_concept else "missing"
    source_value = (
        _feature_short_label(first_concept, _mapping(feature_map.get(first_concept))) if first_concept else "缺少观测"
    )
    return [
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


def _section_label(section: str) -> str:
    section_key = str(section or "").strip()
    label = {
        "assets": "资产联动",
        "credit": "信用压力",
        "cross_asset": "跨资产确认",
        "economy": "经济数据",
        "fed": "美联储",
        "fed_corridor": "政策走廊",
        "funding": "资金面",
        "liquidity": "美元流动性",
        "macro": "宏观",
        "positioning": "仓位拥挤度",
        "rates": "利率定价",
        "volatility": "波动率",
    }.get(section_key)
    if label:
        return label
    raise ValueError(f"Missing macro section label metadata: {section_key or '<missing>'}")


def _required_macro_severity(value: object) -> str:
    severity = str(value or "").strip().lower()
    _required_macro_severity_label(severity)
    return severity


def _required_macro_severity_label(
    value: object,
    *,
    allowed: set[str] | None = None,
) -> str:
    severity = str(value or "").strip().lower()
    labels = {
        "high": "高",
        "medium": "中",
        "low": "低",
        "error": "阻断",
        "warning": "关注",
        "info": "提示",
    }
    label = labels.get(severity)
    if label and (allowed is None or severity in allowed):
        return label
    raise ValueError(f"Missing macro severity label metadata: {severity or '<missing>'}")


def _concept_short_label(concept_key: str) -> str:
    return _concept_required_text(concept_key, "short_label")


def _concept_metadata(concept_key: str) -> Mapping[str, Any]:
    metadata = MACRO_CONCEPT_METADATA.get(concept_key)
    if isinstance(metadata, Mapping) and metadata:
        return metadata
    raise ValueError(f"Missing macro concept metadata: {concept_key}")


def _concept_required_text(concept_key: str, field: str, *, error_field: str | None = None) -> str:
    value = _public_text(_concept_metadata(concept_key).get(field))
    if value:
        return value
    raise ValueError(f"Missing macro concept {error_field or field} metadata: {concept_key}")


def _concept_optional_text(concept_key: str, field: str) -> str | None:
    return _public_text(_concept_metadata(concept_key).get(field))


def _gap_payload(value: object) -> dict[str, Any]:
    require_remediation_hint = False
    if isinstance(value, Mapping):
        payload: dict[str, Any] = {str(key): item for key, item in value.items()}
        require_remediation_hint = True
    else:
        payload = dict(build_macro_data_gaps([str(value)])[0])
    payload["code"] = _required_data_gap_field(payload, "code")
    payload["label"] = _required_data_gap_field(payload, "label")
    payload["severity"] = _required_data_gap_field(payload, "severity")
    if require_remediation_hint:
        payload["remediation_hint"] = _required_data_gap_field(payload, "remediation_hint")
    payload.setdefault("score_participation", False)
    payload.setdefault("owner", "macro_intel")
    payload.setdefault("score_impact", "excluded")
    return payload


def _required_data_gap_field(gap: Mapping[str, Any], field: str) -> str:
    code = str(gap.get("code") or "").strip()
    value = str(gap.get(field) or "").strip()
    if value:
        return value
    raise ValueError(f"Missing macro data gap {field} metadata: {code or '<missing>'}")


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
    label = _public_text(feature.get("label")) or _concept_required_text(concept_key, "label")
    if label:
        return label
    raise ValueError(f"Missing macro concept label metadata: {concept_key}")


def _feature_short_label(concept_key: str, feature: Mapping[str, Any]) -> str:
    return _public_text(feature.get("short_label")) or _concept_short_label(concept_key)


def _feature_description(concept_key: str, feature: Mapping[str, Any]) -> str:
    return _public_text(feature.get("description")) or _concept_optional_text(concept_key, "description") or ""


def _feature_unit_label(concept_key: str, feature: Mapping[str, Any], latest: Mapping[str, Any]) -> str:
    unit_label = _public_text(feature.get("unit_label")) or _concept_required_text(
        concept_key,
        "unit_label",
        error_field="unit",
    )
    if unit_label:
        return unit_label
    raise ValueError(f"Missing macro concept unit metadata: {concept_key}")


def _public_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _source_label(source: Mapping[str, Any]) -> str | None:
    name = _public_text(source.get("name"))
    return _provider_label(name) if name else None


def _provider_label(value: str) -> str:
    key = value.strip().lower()
    label = {
        "cboe": "Cboe",
        "coinglass": "Coinglass",
        "cftc": "CFTC",
        "deribit": "Deribit",
        "fred": "FRED",
        "official_fed_text": "Federal Reserve",
        "macro_import": "宏观导入",
        "ny_fed": "NY Fed",
        "nyfed": "NY Fed",
        "okx": "OKX",
        "official_calendar": "官方日历",
        "treasury": "US Treasury",
        "treasury_auction": "US Treasury",
        "treasury_fiscal": "US Treasury",
        "yahoo": "Yahoo",
    }.get(key)
    if label:
        return label
    raise ValueError(f"Missing macro provider label metadata: {value}")


_STATUS_LABELS = {
    "ok": "可用",
    "ready": "可用",
    "partial": "部分可用",
    "missing": "缺失",
    "stale": "过期",
    "degraded": "降级",
    "insufficient_history": "历史不足",
    "static": "静态",
}


def _status_label(status: object) -> str:
    return _STATUS_LABELS[_status_key(status)]


def _status_key(status: object) -> str:
    status_key = str(status or "").strip()
    if status_key in _STATUS_LABELS:
        return status_key
    raise ValueError(f"Missing macro status label metadata: {status_key or '<missing>'}")


def _quality_label(quality: str) -> str:
    quality_key = str(quality or "").strip()
    labels = {
        "ready": "可用",
        "ok": "可用",
        "missing": "缺失",
        "degraded": "降级",
        "partial": "部分可用",
        "stale": "过期",
    }
    label = labels.get(quality_key)
    if label:
        return label
    raise ValueError(f"Missing macro quality label metadata: {quality_key or '<missing>'}")


def _regime_label(regime: str) -> str:
    regime_key = str(regime or "").strip()
    label = {
        "carry": "波动率 carry",
        "confirmed_risk_on": "风险偏好确认",
        "corridor_drain": "走廊抽水",
        "corridor_pressure": "走廊压力",
        "crowded_risk_long": "风险多头拥挤",
        "data_gap": "数据缺口",
        "defensive_short": "防守仓位偏空",
        "easing": "宽松",
        "equity_context_available": "风险资产参考可用",
        "front_end_tightening": "短端收紧",
        "credit_stress": "信用压力",
        "funding_stress": "融资压力",
        "low_quality_stress": "低质量信用压力",
        "near_term_stress": "短期压力",
        "orderly": "秩序正常",
        "panic": "波动率恐慌",
        "policy_tight_growth_scare": "紧政策 / 增长担忧",
        "risk_on": "风险偏好上行",
        "risk_on_confirmation": "risk-on 确认",
        "risk_off_confirmation": "risk-off 确认",
        "supportive": "流动性支持",
        "term_premium_pressure": "期限溢价压力",
        "tightening": "紧缩压力",
        "risk_on_liquidity": "流动性 risk-on",
        "reflation": "再通胀",
        "neutral": "中性",
        "watch": "观察区",
    }.get(regime_key)
    if label:
        return label
    raise ValueError(f"Missing macro regime label metadata: {regime_key or '<missing>'}")


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


def _contains_cjk(value: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in value)


def _code_label(code: str) -> str | None:
    if not code:
        return None
    if _contains_cjk(code):
        return code
    return {
        "breakevens_accelerate": "通胀补偿加速",
        "credit_spreads_benign": "信用利差温和",
        "credit_spreads_normalize": "信用利差正常化",
        "credit_stress": "信用压力",
        "cross_asset_risk_off": "跨资产 risk-off 确认",
        "deep_curve_inversion": "曲线深度倒挂",
        "fed_corridor_pressure": "政策走廊压力",
        "global_term_premium": "期限溢价压力",
        "hyg_underperforms_lqd": "HYG 跑输 LQD",
        "hy_oas_distress": "高收益债利差进入困境区",
        "hy_oas_stress": "高收益债利差压力",
        "hy_oas_tightens": "HY OAS 收窄",
        "hy_oas_widening": "HY OAS 走阔",
        "hy_oas_widening_5d": "HY OAS 5日走阔",
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
    }.get(code)


def _related_routes(routes: Sequence[str]) -> list[dict[str, str]]:
    return [{"href": route, "label": _ROUTE_LABELS.get(route, route)} for route in routes]


def _localized_reason(reason: str) -> str:
    return {
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
    source_name = _source_label(source) or "未标注来源"
    description = _concept_optional_text(concept_key, "description") or ""
    return f"{source_name}；{description}" if description else source_name


def _date_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, date | datetime):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value)


def _chart_title(chart_id: str) -> str:
    title = _CHART_TITLES.get(chart_id)
    if title:
        return title
    raise ValueError(f"Missing macro chart title metadata: {chart_id}")


def _chart_subtitle(status: str) -> str:
    if status == "insufficient_history":
        return "历史样本不足，暂不渲染趋势判断"
    if status == "partial":
        return "部分序列缺失，仅展示可用指标"
    return "核心序列走势"


def _table_title(table_id: str) -> str:
    title = _TABLE_TITLES.get(table_id)
    if title:
        return title
    raise ValueError(f"Missing macro table title metadata: {table_id}")


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


def _unique(values: Iterable[str]) -> list[str]:
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
    "/macro/assets/equities": "美股风险",
    "/macro/assets/bonds": "债券资产",
    "/macro/assets/commodities": "商品冲击",
    "/macro/assets/fx": "美元压力",
    "/macro/assets/crypto": "加密资产",
    "/macro/rates/fed-funds": "联邦基金",
    "/macro/rates/yield-curve": "收益率曲线",
    "/macro/rates/real-rates": "实际利率",
    "/macro/liquidity/rrp-tga": "RRP / TGA",
    "/macro/economy/gdp": "GDP",
    "/macro/economy/employment": "就业",
    "/macro/economy/inflation": "通胀",
    "/macro/volatility/vix": "VIX 结构",
    "/macro/credit/stress": "信用压力分解",
}

_CHART_TITLES = {
    "asset_cross_market_snapshot": "大类资产走势",
    "rates_curve": "收益率曲线",
    "asset_proxy_performance": "资产代理走势",
    "macro_regime": "宏观链条走势",
    "bond_proxy_performance": "债券代理走势",
    "commodity_proxy_performance": "商品代理走势",
    "credit_spreads": "信用利差走势",
    "credit_stress_stack": "信用压力堆栈",
    "crypto_proxy_performance": "加密资产走势",
    "economy_four_pillar": "经济四象限走势",
    "equity_proxy_performance": "美股代理走势",
    "employment_dashboard": "就业市场走势",
    "fed_corridor": "美联储政策走廊",
    "fed_funds_corridor": "联邦基金走廊",
    "fx_proxy_performance": "美元代理走势",
    "inflation_dashboard": "通胀数据走势",
    "liquidity_stack": "美元流动性堆栈",
    "real_gdp_history": "实际 GDP 历史",
    "real_rates": "实际利率走势",
    "rrp_tga_stack": "RRP / TGA 堆栈",
    "volatility_context": "波动率背景",
    "vix_term_proxy": "VIX 期限代理",
    "yield_curve": "收益率曲线",
}

_TABLE_TITLES = {
    "asset_group_snapshot": "大类资产快照",
    "rates_snapshot": "利率快照",
    "asset_proxy_snapshot": "资产快照",
    "panel_scorecard": "面板记分卡",
    "bond_proxy_snapshot": "债券资产快照",
    "commodity_proxy_snapshot": "商品资产快照",
    "credit_snapshot": "信用压力快照",
    "credit_oas_ladder": "OAS 分层表",
    "credit_stress_table": "信用压力表",
    "availability_proxy_notes": "数据可用性 / 代理说明",
    "crypto_proxy_snapshot": "加密资产快照",
    "curve_spreads": "曲线利差快照",
    "economy_four_pillar_table": "经济四象限表",
    "equity_proxy_snapshot": "美股资产快照",
    "employment_table": "就业数据表",
    "fed_corridor_snapshot": "政策走廊快照",
    "fed_funds_snapshot": "联邦基金快照",
    "fx_proxy_snapshot": "美元压力快照",
    "inflation_table": "通胀数据表",
    "liquidity_snapshot": "流动性快照",
    "real_gdp_table": "GDP 数据表",
    "real_rates_snapshot": "实际利率快照",
    "rrp_tga_table": "RRP / TGA 表",
    "volatility_snapshot": "波动率快照",
    "vix_term_proxy_table": "VIX 期限代理表",
}


__all__ = ["TRADE_MAP_RELIABILITY_CONCEPTS", "TRADE_MAP_RELIABILITY_WINDOW_DAYS", "build_macro_module_view"]
