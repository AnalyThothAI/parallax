from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"
WEB_SRC = ROOT / "web" / "src"
ALEMBIC_VERSIONS = SRC / "platform" / "db" / "alembic" / "versions"

FORBIDDEN_MACRO_COMPATIBILITY_TOKENS = (
    "macro_regime_v3",
    "macro_module_view_v1",
    "macro_module_view_v2",
    "macro_observation_series_active_generation",
    "macro_observation_series_generations",
    "macro_view_snapshots_compact",
    "macro_view_snapshot_generations",
    "macro_regime_snapshots",
)

RETIRED_CEX_RUN_SERVING_DOC_TOKENS = (
    "CREATE TABLE IF NOT EXISTS cex_oi_radar_runs",
    "Write `cex_oi_radar_runs`",
    "写 `cex_oi_radar_runs`",
    "Replace rows for a `run_id`",
    "按 `run_id` 重建",
)

HARD_DELETED_MACRO_MODULE_IDS = (
    "assets/correlation",
    "assets/crypto-derivatives",
    "rates/auctions",
    "rates/expectations",
    "fed/statements",
    "fed/speeches",
    "liquidity/global-dollar",
    "liquidity/reserves",
    "liquidity/subsurface",
    "liquidity/transmission-chain",
    "liquidity/operations",
    "liquidity/fed-balance-sheet",
    "economy/consumer",
    "volatility/dashboard",
    "credit/cds",
)

MACRO_RUNTIME_SCAN_ROOTS = (
    SRC / "domains/macro_intel",
    SRC / "app/surfaces/api/routes_macro.py",
    SRC / "app/surfaces/cli/commands/macro.py",
    WEB_SRC / "features/macro",
    WEB_SRC / "routes/macro.route.tsx",
    WEB_SRC / "features/cockpit/ui/appNavigation.ts",
)

MACRO_SOURCE_BACKLOG_PLACEHOLDER_TOKENS = (
    "来源待接入",
    "future-source",
    "future source",
    "static backlog",
    "CME FedWatch",
    "FedWatch",
    "fake FedWatch",
    "OPRA",
    "TRACE",
    "CDS",
    "CDX",
    "DataShop",
    "LiveVol",
    "auction-tail",
    "when-issued",
    "STFM",
)

MACRO_PRODUCT_PLACEHOLDER_TOKENS = (
    "未命名指标",
    "单位未标注",
    "宏观图表",
    "宏观表格",
    "未知",
    "未知来源",
    "未知状态",
    "未知宏观状态",
    "unknown_chart",
    "unknown_table",
)

MACRO_EMPTY_RUNTIME_FACTORY_TOKENS = ("_empty_chart",)

MACRO_RAW_CONCEPT_METADATA_FALLBACK_TOKENS = (
    'MACRO_CONCEPT_METADATA.get(concept_key, {}).get("label") or concept_key',
    'MACRO_CONCEPT_METADATA.get(concept_key, {}).get("short_label") or concept_key',
    'MACRO_CONCEPT_METADATA.get(concept_key, {}).get("unit_label") or str(unit or "")',
    'metadata.get("label") or concept_key',
    'metadata.get("short_label") or concept_key',
    'metadata.get("unit_label") or str(unit or "")',
    'metadata.get("short_label") or _feature_label(concept_key, feature)',
)

MACRO_FEATURE_ENGINE_METADATA_FALLBACK_TOKENS = (
    "metadata = MACRO_CONCEPT_METADATA.get(concept_key, {})",
    '"label": str(metadata.get("label") or concept_key)',
    '"short_label": str(metadata.get("short_label") or metadata.get("label") or concept_key)',
    '"description": str(metadata.get("description") or "")',
    '"unit_label": str(metadata.get("unit_label") or unit)',
)

MACRO_FEATURE_ENGINE_CONCEPT_KEY_DROP_TOKENS = (
    'str(observation.get("concept_key") or "").strip()',
    "if not concept_key:\n            continue",
)

MACRO_FEATURE_ENGINE_SOURCE_FALLBACK_TOKENS = (
    '"name": str(latest_observation.get("source_name") or "")',
    '"series_key": str(latest_observation.get("series_key") or "")',
)

MACRO_FEATURE_ENGINE_NUMERIC_VALUE_FALLBACK_TOKENS = ('for field_name in ("value_numeric", "value"):',)

MACRO_ASSET_CORRELATION_NUMERIC_VALUE_FALLBACK_TOKENS = ('observation.get("value_numeric", observation.get("value"))',)

MACRO_ASSET_CORRELATION_OBSERVED_AT_DROP_TOKENS = ("if observed_at is None or value is None or value <= 0:",)

MACRO_ASSET_CORRELATION_SOURCE_FALLBACK_TOKENS = (
    '"source_name": str(observation.get("source_name") or "").strip()',
    'str(point.get("source_name") or "")',
)

MACRO_ASSET_CORRELATION_RANKING_FALLBACK_TOKENS = (
    '_int_value(observation.get("source_priority"))',
    '_int_value(observation.get("ingested_at_ms"))',
    "def _int_value",
)

MACRO_ASSET_CORRELATION_TITLE_FALLBACK_TOKENS = ("ASSET_CORRELATION_TITLES.get(concept_key, concept_key)",)

MACRO_GAP_PAYLOAD_CONCEPT_METADATA_FALLBACK_TOKENS = (
    'MACRO_CONCEPT_METADATA.get(concept_key or "", {})',
    'return f"数据质量缺口：{_public_gap_code(raw_code)}"',
)

MACRO_GAP_PAYLOAD_HUMANIZED_MISSING_FALLBACK_TOKENS = (
    "_NAMED_GAP_SUBJECTS.get(body, _humanize_gap_code(body))",
    "def _humanize_gap_code",
)

MACRO_FEATURE_ENGINE_UNIT_FALLBACK_TOKENS = (
    '"unit": latest_observation.get("unit")',
    '"unit": observation.get("unit")',
    '"unit": latest["unit"]',
)

MACRO_FEATURE_ENGINE_OBSERVED_AT_FALLBACK_TOKENS = (
    "latest_observation = ordered_observations[0] if ordered_observations else {}",
)

MACRO_FEATURE_ENGINE_OBSERVED_AT_DROP_TOKENS = ("if observed_at is None:\n            continue",)

MACRO_FEATURE_ENGINE_FREQUENCY_FALLBACK_TOKENS = (
    'return str(observation.get("frequency") or "").strip().lower()',
    'STALE_FRESHNESS_DAYS_BY_FREQUENCY.get(frequency, STALE_FRESHNESS_DAYS_BY_FREQUENCY["daily"])',
)

MACRO_FEATURE_ENGINE_DATA_QUALITY_FALLBACK_TOKENS = (
    'str(observation.get("data_quality") or "").strip().lower()',
    'if data_quality and data_quality != "ok":',
)

MACRO_JUDGEMENT_REVIEW_STAT_FALLBACK_TOKENS = (
    'row.get("status") or "insufficient_history"',
    'row.get("win_rate_label") or "0/0"',
    '_number(row.get("pnl_usd")) or 0.0',
    '_number(row.get("average_signed_return_pct")) or 0.0',
)

MACRO_SCENARIO_QUALITY_FALLBACK_TOKENS = (
    'gap.get("severity") or "warning"',
    '"description": _text(gap.get("remediation_hint"))',
)

MACRO_SCENARIO_CONFIDENCE_SCORE_FALLBACK_TOKENS = ('_number(node.get("score")) or 0.0',)

MACRO_SCENARIO_TRIGGER_DISPLAY_FALLBACK_TOKENS = (
    "or _code_label(code)",
    'or _code_label(code) or ""',
    "_trigger_node(code)",
    "SOURCE_LABELS.get(source_name, source_name)",
    '{"high": "高", "medium": "中", "low": "低"}.get(severity, "中")',
)

MACRO_SCENARIO_SOURCE_LABEL_FALLBACK_TOKENS = (
    'if not source_name:\n        return ""',
    'return SOURCE_LABELS.get(source_name, "")',
)

MACRO_SCENARIO_FEATURE_LATEST_FALLBACK_TOKENS = (
    'unit=_text(latest.get("unit"))',
    'if value is None:\n        return ""',
    'if observed_at:\n        parts.append(f"as-of {observed_at}")',
    'f"as-of={observed_at}" if observed_at else ""',
)

MACRO_SCENARIO_TRADE_MAP_LEGACY_CODE_LIST_TOKENS = (
    '"confirms_on"',
    '"invalidates_on"',
)

MACRO_MODULE_OBSERVATION_SOURCE_FALLBACK_TOKENS = (
    'latest_observation.get("provider")',
    "_provider_from_series(series_key)",
    "def _provider_from_series",
)

MACRO_MODULE_PROVENANCE_SOURCE_DROP_TOKENS = ("if not source:\n            continue",)

MACRO_REGIME_PANEL_SCORE_FALLBACK_TOKENS = (
    "_panel_score(panel, default=4.0)",
    "_panel_score(panel, default=0.0)",
    '_panel_regime(panel, default="macro_confirmation_pending")',
)

MACRO_REGIME_COVERAGE_FALLBACK_TOKENS = (
    'coverage.get("observed_concept_count") or 0',
    'coverage.get("required_concept_count") or len(CORE_REQUIRED_CONCEPTS)',
    'coverage.get("latest_coverage_ratio") or 0.0',
    'coverage.get("history_coverage_ratio") or 0.0',
)

MACRO_REGIME_FEATURE_FALLBACK_TOKENS = (
    '_int_or_none(feature.get("stale_after_days")) or 7',
    '_int_or_none(feature.get("history_points")) or 0',
)

MACRO_MODULE_SCENARIO_CONFIDENCE_FALLBACK_TOKENS = ('_number(scenario.get("confidence")) or 0.0',)

MACRO_MODULE_SCENARIO_REGIME_FALLBACK_TOKENS = (
    'scenario.get("current_regime") or snapshot.get("regime") or "data_gap"',
)

MACRO_MODULE_SCENARIO_CASES_FALLBACK_TOKENS = (
    '_mapping_list(scenario.get("scenario_cases"))',
    "scenario_cases[0]",
)

MACRO_MODULE_BASE_CASE_FIELD_FALLBACK_TOKENS = (
    'elif regime_label:\n        fact = f"市场主线：{regime_label}。"',
    "if not trade:\n        trade = _structured_market_trade(scenario)",
    "if not invalidation:\n        invalidation = _structured_market_invalidation(scenario)",
)

MACRO_MODULE_STRUCTURED_REGIME_LABEL_FALLBACK_TOKENS = (
    'diagnostics.get("label")',
    '"样本不足"',
)

MACRO_MODULE_SCENARIO_QUALITY_FALLBACK_TOKENS = (
    "if not quality_blockers:\n        quality_blockers = [",
    'for gap in _mapping_list(data_health.get("global_gaps"))',
)

MACRO_MODULE_SCENARIO_LIST_FALLBACK_TOKENS = (
    '_mapping_list(scenario.get("top_changes"))',
    '_mapping_list(scenario.get("trade_map"))',
    '_mapping_list(scenario.get("watch_triggers"))',
    '_mapping_list(scenario.get("invalidations"))',
    '_mapping_list(scenario.get("confirmations"))',
    '_mapping_list(scenario.get("contradictions"))',
)

MACRO_MODULE_SCENARIO_SIGNAL_DISPLAY_FALLBACK_TOKENS = (
    'item.get("label") or _code_label',
    'first.get("label") or _code_label',
    'item.get("kind") or "signal"',
    'item.get("evidence_label")\n        or item.get("description")',
    'or item.get("change_label")',
    'or item.get("value_label")',
    'return f"{label} · {detail}" if detail else label',
    'detail = str(item.get("description") or "").strip()',
    'value = item.get("detail") or item.get("description")',
    '"description": item.get("description") or "",',
    '"description": str(item.get("description") or ""),\n        "window": window,',
    '"description": str(catalyst.get("description") or ""),\n        "window": window,',
    '"description": str(item.get("description") or item.get("remediation_hint") or ""),\n        "kind": kind,',
    '"description": str(item.get("description") or ""),\n        "node": node,',
)

MACRO_MODULE_SCENARIO_SEVERITY_LABEL_FALLBACK_TOKENS = (
    'str(item.get("severity_label") or "").strip() or _required_macro_severity_label',
)

MACRO_MODULE_WATCHLIST_SEVERITY_LABEL_FALLBACK_TOKENS = (
    'payload["severity_label"] = _watchlist_severity_label(severity)',
    "def _watchlist_severity_label",
)

MACRO_MODULE_WATCHLIST_WINDOW_LABEL_FALLBACK_TOKENS = ('payload["window_label"] = window\n',)

MACRO_MODULE_FUTURE_WATCH_CATALYST_WINDOW_LABEL_FALLBACK_TOKENS = ('"window_label": window,\n',)

MACRO_MODULE_FUTURE_WATCH_CATALYST_SEVERITY_LABEL_FALLBACK_TOKENS = (
    '"severity_label": _future_catalyst_severity_label(severity),\n',
)

MACRO_MODULE_FUTURE_EVENT_CATALYST_DISPLAY_FALLBACK_TOKENS = (
    '"window_label": window,\n',
    '"severity_label": _future_catalyst_severity_label(severity),\n',
)

MACRO_MODULE_MARKET_EVENT_FLOW_DISPLAY_FALLBACK_TOKENS = (
    "window, severity, severity_label = _event_flow_window(catalyst)",
    '"window_label": _event_flow_window_label(window),\n',
)

MACRO_MODULE_MARKET_EVENT_FLOW_CLASSIFICATION_FALLBACK_TOKENS = (
    "category, category_label, impact, impact_label, watch = _event_flow_classification(catalyst)",
)

MACRO_STRUCTURED_FED_COMMUNICATION_EVENT_FLOW_FALLBACK_TOKENS = (
    "_category, _category_label, _impact, impact_label, watch = _event_flow_classification(catalyst)",
)

MACRO_MODULE_EVIDENCE_ITEM_SEVERITY_LABEL_FALLBACK_TOKENS = (
    'payload["severity_label"] = _required_macro_severity_label(severity)\n',
)

MACRO_MODULE_EVIDENCE_ITEM_WINDOW_LABEL_FALLBACK_TOKENS = (
    'if item.get("time_window_label"):\n        payload["time_window_label"] = item.get("time_window_label")',
)

MACRO_MODULE_QUALITY_BLOCKER_SEVERITY_LABEL_FALLBACK_TOKENS = (
    '"severity_label": _required_macro_severity_label(severity),\n',
)

MACRO_MODULE_EVIDENCE_ITEM_DROP_TOKENS = (
    "if not label or not evidence_label:\n        return None",
    'if item is not None\n            ],\n            "contradictions"',
    'if item is not None\n            ],\n            "watch_triggers"',
    'if item is not None\n            ],\n            "invalidations"',
)

MACRO_MODULE_COMPACT_SIGNAL_DROP_TOKENS = (
    "if not label or not kind or not evidence_label:\n        return None",
    'if item is not None\n        ],\n        "quality_blockers"',
)

MACRO_MODULE_STRUCTURED_SIGNAL_LINE_DROP_TOKENS = (
    "if not label:\n        return None",
    "if not detail:\n        return None",
    "if line:\n            evidence.append(line)",
)

MACRO_MODULE_STRUCTURED_MARKET_THESIS_DROP_TOKENS = (
    "if not fact or not evidence or not trade or not invalidation:\n        return None",
)

MACRO_MODULE_STRUCTURED_MARKET_INVALIDATION_DEAD_TOKENS = ("def _structured_market_invalidation",)

MACRO_MODULE_STRUCTURED_MARKET_TRADE_DROP_TOKENS = (
    'if str(item.get("expression") or "").strip()',
    "labels = [label for label in labels if label]",
)

MACRO_MODULE_STRUCTURED_FED_COMMUNICATION_LABEL_FALLBACK_TOKENS = (
    'catalyst.get("label") or "Fed 文档"',
    '"Fed 文档"',
)

MACRO_MODULE_STRUCTURED_FED_COMMUNICATION_DROP_TOKENS = (
    "if not detail:\n        return None",
    "if not evidence:\n        return None",
)

MACRO_MODULE_STRUCTURED_FED_COMMUNICATION_SOURCE_DROP_TOKENS = ('source = str(catalyst.get("source") or "").strip()',)

MACRO_MODULE_FED_SPEAKER_TITLE_FALLBACK_TOKENS = (
    "title = text_value or _event_text_value(raw_payload=raw_payload, provenance=provenance)",
    'title.split(",", 1)',
)

MACRO_MODULE_STRUCTURED_FED_COMMUNICATION_DOCUMENT_TYPE_FALLBACK_TOKENS = (
    '}.get(document_type, "Fed 文档")',
    '"Fed 文档"',
)

MACRO_MODULE_EVENT_CATALYST_DESCRIPTION_FALLBACK_TOKENS = (
    'description = str(first.get("description") or "").strip()',
    'detail = str(catalyst.get("description") or "").strip()',
    '"description": _event_description(',
)

MACRO_MODULE_EVENT_TEXT_DESCRIPTION_FALLBACK_TOKENS = ('provenance.get("description")',)

MACRO_MODULE_QUALITY_BLOCKER_DESCRIPTION_FALLBACK_TOKENS = (
    '"description": gap.get("remediation_hint") or gap.get("label") or "",',
    '"description": str(item.get("description") or item.get("remediation_hint") or label)',
    'or item.get("description")\n        )',
)

MACRO_MODULE_QUALITY_BLOCKER_DISPLAY_DROP_TOKENS = (
    'evidence_label = str(item.get("evidence_label") or item.get("remediation_hint") or "").strip()',
    'evidence_label = str(item.get("evidence_label") or item.get("remediation_hint") or "").strip()\n'
    "    if not evidence_label:\n"
    "        return None",
    'or item.get("remediation_hint")',
    "if not detail:\n"
    '        if kind != "quality":\n'
    '            raise ValueError("macro_watchlist_rule_detail_required")\n'
    "        return None",
)

MACRO_MODULE_AVAILABILITY_PLACEHOLDER_TOKENS = (
    '"display_value": "n/a"',
    '"display_value": "计分排除"',
    '"display_value": "无显式缺口"',
    '"display_value": "当前模块没有配置级缺口。"',
)

MACRO_MODULE_AVAILABILITY_OPTIONAL_SOURCE_TOKENS = ("source_name = _source_label(source)",)

MACRO_MODULE_FEATURE_SOURCE_OPTIONAL_TOKENS = (
    '"source_label": _source_label(source)',
    '"source_state": {"label": _source_label(source)',
    '"source": {"display_value": _source_label(source), "sort_value": _source_label(source)}',
)

MACRO_MODULE_FEATURE_LATEST_PLACEHOLDER_TOKENS = (
    '"display_value": _display_number(value)',
    '"observed_at_label": _observed_label(latest.get("observed_at"))',
    '"latest": {"display_value": _display_number(value), "sort_value": value}',
)

MACRO_MODULE_FEATURE_LATEST_UNIT_PLACEHOLDER_TOKENS = ('"unit": latest.get("unit")',)

MACRO_MODULE_FEATURE_DISPLAY_METADATA_FALLBACK_TOKENS = (
    '_public_text(feature.get("label")) or _concept_required_text(concept_key, "label")',
    '_public_text(feature.get("short_label")) or _concept_short_label(concept_key)',
    '_public_text(feature.get("description")) or _concept_optional_text(concept_key, "description") or ""',
    'unit_label = _public_text(feature.get("unit_label")) or _concept_required_text(',
)

MACRO_MODULE_CHART_HISTORY_COMPATIBILITY_TOKENS = (
    "if isinstance(point, Mapping)",
    'if not points and latest.get("value") is not None:',
    '"observed_at": latest.get("observed_at"), "value": latest.get("value")',
)

MACRO_MODULE_FEATURE_HISTORY_OPTIONAL_SURFACE_TOKENS = (
    '"history_points": _int_or_none(feature.get("history_points"))',
    'history_points = _int_or_none(feature.get("history_points"))',
)

MACRO_MODULE_AVAILABILITY_LATEST_PLACEHOLDER_TOKENS = (
    'latest = _mapping(feature.get("latest"))',
    '_observed_label(latest.get("observed_at")) if feature else "观测于 --"',
    '"sort_value": latest.get("observed_at")',
)

MACRO_MODULE_SNAPSHOT_HEADER_TIME_PLACEHOLDER_TOKENS = (
    'asof_date = snapshot.get("asof_date")',
    'computed_at_ms = snapshot.get("computed_at_ms")',
    '"asof_label": f"截至 {asof_date}" if asof_date else "截至 --"',
)

MACRO_MODULE_TRADE_MAP_ACTION_CHECKLIST_FALLBACK_TOKENS = (
    'item.get("confirms_on")',
    'item.get("invalidates_on")',
    "label = _code_label(code)",
)

MACRO_MODULE_TRADE_MAP_ACTION_CHECKLIST_DROP_TOKENS = (
    "if not kind or not kind_label or not label or not description:\n            continue",
)

MACRO_MODULE_TRADE_MAP_ACTION_CHECKLIST_SHAPE_DROP_TOKENS = ('_mapping_list(item.get("action_checklist"))',)

MACRO_MODULE_TRADE_MAP_EXPRESSION_LABEL_FALLBACK_TOKENS = (
    "_TRADE_MAP_EXPRESSION_LABELS",
    "_trade_map_expression_label(",
    'item.get("label") or _trade_map_expression_label',
)

MACRO_MODULE_TRADE_MAP_ITEM_DROP_TOKENS = (
    'if not expression or not str(payload.get("label") or "").strip():\n        return None',
    "if item is not None",
)

MACRO_MODULE_WATCHLIST_ASSET_FALLBACK_TOKENS = (
    'label = str(leg.get("label") or symbol).strip()',
    "key = symbol or label",
    'action = str(leg.get("action") or "").strip()',
)

MACRO_MODULE_SCENARIO_RULE_KEY_FALLBACK_TOKENS = (
    '"key": f"watch:{code or label}"',
    '"key": f"{kind}:{code or label}"',
)

MACRO_MODULE_SCENARIO_RULE_DISPLAY_DROP_TOKENS = (
    "if not label or not detail or window is None:\n        return None",
    "if not label or not detail:\n        return None\n    if not code:",
)

MACRO_MODULE_EVENT_KEY_FALLBACK_TOKENS = (
    "\"key\": f\"event:{catalyst.get('code') or catalyst.get('label') or ''}\"",
    '"key": str(catalyst.get("code") or label)',
)

MACRO_MODULE_EVENT_SOURCE_FALLBACK_TOKENS = ('"source": str(catalyst.get("source") or ""),',)

MACRO_MODULE_EVENT_CATALYST_SOURCE_PROVIDER_FALLBACK_TOKENS = (
    'observation.get("source_name") or raw_payload.get("provider")',
)

MACRO_MODULE_EVENT_KIND_FALLBACK_TOKENS = ('"kind": str(catalyst.get("kind") or ""),',)

MACRO_MODULE_EVENT_DISPLAY_FIELD_DROP_TOKENS = (
    'label = str(catalyst.get("label") or "").strip()\n'
    '    detail = str(catalyst.get("detail") or "").strip()\n'
    "    if not label or not detail:\n"
    "        return None",
    'date = str(catalyst.get("observed_at") or "").strip()\n'
    "    if not label or not detail or not date:\n"
    "        return None",
)

MACRO_MODULE_EVENT_DETAIL_DATE_PLACEHOLDER_TOKENS = ('date_label = observed_at or "--"',)

MACRO_MODULE_NEWS_EVENT_IDENTITY_FALLBACK_TOKENS = (
    "\"key\": f\"news:{row.get('row_id') or row.get('news_item_id') or label}\"",
)

MACRO_MODULE_NEWS_EVENT_SCOPE_FALLBACK_TOKENS = (
    'category = str(market_scope.get("primary") or "").strip() or "market_event"',
    'return _NEWS_MARKET_SCOPE_LABELS.get(scope, "市场事件")',
)

MACRO_MODULE_NEWS_EVENT_IMPACT_FALLBACK_TOKENS = (
    'alert_eligibility.get("decision_class")',
    'return "mainline_context", "不改主线", "low", "低"',
)

MACRO_MODULE_NEWS_EVENT_DATE_FALLBACK_TOKENS = (
    'return _date_string(row.get("published_at") or row.get("observed_at"))',
)

MACRO_MODULE_NEWS_EVENT_DISPLAY_FIELD_DROP_TOKENS = (
    "if not label or not detail or not date_label or not source:\n        return None",
)

MACRO_MODULE_NEWS_EVENT_FLOW_DERIVATION_TOKENS = (
    "category, category_label = _required_market_news_scope(market_scope)",
    "impact, impact_label, severity, severity_label = _news_mainline_impact(row)",
    "watch_parts = _news_watch_parts(row, category_label=category_label)",
    '"window_label": _event_flow_window_label("recent"),\n',
)

MACRO_MODULE_HISTORY_POINTS_FALLBACK_TOKENS = (
    '_int_or_none(existing.get("history_points")) or len(_mapping_list(existing.get("history")))',
    '_int_or_none(observation_feature.get("history_points")) or len(',
)

MACRO_MODULE_TRADE_REVIEW_FALLBACK_TOKENS = (
    '_number(row.get("return_pct")) or 0.0',
    '_number(row.get("mae_pct")) or 0.0',
    '_int_or_none(review.get("hit_count")) or 0',
    '_int_or_none(review.get("sample_count")) or len(rows)',
    'review.get("win_rate_label") or f"{hit_count}/{sample_count}"',
)

MACRO_MODULE_HOLDING_REVIEW_FALLBACK_TOKENS = (
    '_number(row.get("signed_return_pct")) or 0.0',
    '_int_or_none(row.get("sample_count")) or 0',
    '_int_or_none(row.get("hit_count")) or 0',
    "win_rate = round(hit_count / sample_count, 2) if sample_count else 0.0",
    "average_signed_return = sum(signed_returns) / sample_count if sample_count else 0.0",
)

MACRO_MODULE_JUDGEMENT_REVIEW_WINDOW_DROP_TOKENS = (
    "if row is not None",
    "return None",
)

MACRO_MODULE_STATUS_CHANGE_FALLBACK_TOKENS = (
    "change = change_1w_index if change_1w_index is not None else 0.0",
    "change_1w = change_1w_index if change_1w_index is not None else 0.0",
    "change_1m = change_1m_index if change_1m_index is not None else 0.0",
    "hyg_1w = hyg_1w_pct if hyg_1w_pct is not None else 0.0",
    "relative_1w = relative_1w_pct if relative_1w_pct is not None else 0.0",
)

MACRO_MODULE_CRYPTO_DERIVATIVE_STATUS_FALLBACK_TOKENS = (
    "def _crypto_oi_status(change_1w_pct: float | None) -> tuple[str, str]:\n"
    "    if change_1w_pct is not None and change_1w_pct >= 8.0:\n"
    '        return "leverage_expanding", "杠杆扩张"\n'
    "    if change_1w_pct is not None and change_1w_pct <= -8.0:\n"
    '        return "leverage_flush", "杠杆出清"\n'
    '    return "leverage_stable", "杠杆平稳"',
    "if current_index <= 45.0 and (change_1w_index is None or change_1w_index <= -5.0):\n"
    '        return "vol_relief", "波动回落"',
)

MACRO_MODULE_CREDIT_SPREAD_STATUS_FALLBACK_TOKENS = (
    "def _asset_hy_oas_status(change_1w_bp: float | None) -> tuple[str, str]:\n"
    "    if change_1w_bp is None:\n"
    '        return "credit_stable", "信用稳定"',
    "def _credit_oas_status(change_1w_bp: float | None) -> tuple[str, str]:\n"
    "    if change_1w_bp is None:\n"
    '        return "stable", "稳定"',
    "def _credit_tail_status(change_1w_bp: float | None) -> tuple[str, str]:\n"
    "    if change_1w_bp is None:\n"
    '        return "stable", "稳定"',
)

MACRO_MODULE_GROWTH_REGIME_FALLBACK_TOKENS = (
    '_number(gdp.get("current_yoy_pct")) or 0.0',
    '_number(gdp.get("change_1q_pct")) or 0.0',
    '_number(industrial.get("current_yoy_pct")) or 0.0',
    '_number(housing.get("change_1m_k")) or 0.0',
    '_number(pce.get("current_yoy_pct")) or 0.0',
    '_number(pce.get("change_1m_pct")) or 0.0',
)

MACRO_MODULE_GROWTH_STATUS_FALLBACK_TOKENS = (
    "def _growth_gdp_status(*, current_yoy_pct: float, change_1q_pct: float | None) -> tuple[str, str]:\n"
    "    if current_yoy_pct <= 0.0:\n"
    '        return "contracting", "收缩"\n'
    "    if current_yoy_pct <= 2.0 or (change_1q_pct is not None and change_1q_pct <= -0.5):\n"
    '        return "slowing", "放缓"\n'
    "    if current_yoy_pct >= 2.5 and (change_1q_pct is None or change_1q_pct >= 0.0):\n"
    '        return "resilient", "韧性"\n'
    '    return "stable", "稳定"',
    "def _growth_gdpnow_status(*, current_pct: float, change_1m_pct: float | None) -> tuple[str, str]:\n"
    "    if current_pct <= 0.0:\n"
    '        return "nowcast_contraction", "Nowcast 收缩"\n'
    "    if change_1m_pct is not None and change_1m_pct <= -0.5:\n"
    '        return "nowcast_cooling", "Nowcast 降温"\n'
    "    if current_pct >= 2.5 and (change_1m_pct is None or change_1m_pct >= 0.0):\n"
    '        return "nowcast_resilient", "Nowcast 韧性"\n'
    '    return "nowcast_stable", "Nowcast 稳定"',
    "def _growth_industrial_status(*, current_yoy_pct: float, change_1m_pct: float | None) -> tuple[str, str]:\n"
    "    if current_yoy_pct < 0.0:\n"
    '        return "contracting", "收缩"\n'
    "    if change_1m_pct is not None and change_1m_pct <= -1.0:\n"
    '        return "slowing", "放缓"\n'
    "    if current_yoy_pct >= 2.0:\n"
    '        return "expanding", "扩张"\n'
    '    return "stable", "稳定"',
    "def _growth_consumption_status(\n"
    "    *,\n"
    "    current_yoy_pct: float,\n"
    "    change_1m_pct: float | None,\n"
    "    retail: bool,\n"
    ") -> tuple[str, str]:\n"
    "    if current_yoy_pct <= 1.5 or (change_1m_pct is not None and change_1m_pct <= -0.8):\n"
    '        return ("demand_cooling", "需求降温") if retail else ("consumption_cooling", "消费降温")\n'
    "    if current_yoy_pct >= 3.0:\n"
    '        return ("demand_resilient", "需求韧性") if retail else ("consumption_resilient", "消费韧性")\n'
    '    return "stable", "稳定"',
    "def _growth_housing_status(*, current_m: float, change_1m_k: float | None) -> tuple[str, str]:\n"
    "    if current_m <= 1.2 or (change_1m_k is not None and change_1m_k <= -100.0):\n"
    '        return "housing_drag", "地产拖累"\n'
    "    if change_1m_k is not None and change_1m_k >= 100.0:\n"
    '        return "housing_rebound", "地产修复"\n'
    '    return "stable", "稳定"',
)

MACRO_MODULE_EMPLOYMENT_REGIME_FALLBACK_TOKENS = (
    '_number(unemployment.get("current_pct")) or 0.0',
    '_number(unemployment.get("change_1m_pct")) or 0.0',
    '_number(payroll.get("current_k")) or 0.0',
    '_number(claims.get("current_k")) or 0.0',
    '_number(claims.get("change_1m_k")) or 0.0',
    '_number(wage.get("current_yoy_pct")) or 0.0',
)

MACRO_MODULE_EMPLOYMENT_STATUS_FALLBACK_TOKENS = (
    "def _employment_unemployment_status(*, current_pct: float, change_1m_pct: float | None) -> tuple[str, str]:\n"
    "    if current_pct >= 4.5 or (change_1m_pct is not None and change_1m_pct >= 0.2):\n"
    '        return "deteriorating", "走弱"\n'
    "    if change_1m_pct is not None and change_1m_pct <= -0.2:\n"
    '        return "improving", "改善"\n'
    "    if current_pct <= 4.0:\n"
    '        return "tight", "偏紧"\n'
    '    return "stable", "稳定"',
    "def _employment_payroll_status(*, current_k: float, change_1m_k: float | None) -> tuple[str, str]:\n"
    "    if current_k <= 100.0 or (change_1m_k is not None and change_1m_k <= -100.0):\n"
    '        return "slowing", "放缓"\n'
    "    if current_k >= 180.0:\n"
    '        return "strong", "强劲"\n'
    '    return "steady", "稳定"',
    "def _employment_claims_status(*, current_k: float, change_1m_k: float | None) -> tuple[str, str]:\n"
    "    if current_k >= 300.0 or (change_1m_k is not None and change_1m_k >= 20.0):\n"
    '        return "claims_rising", "初请上行"\n'
    "    if change_1m_k is not None and change_1m_k <= -20.0:\n"
    '        return "claims_falling", "初请回落"\n'
    '    return "stable", "稳定"',
    "def _employment_openings_status(*, current_m: float, change_1m_m: float | None) -> tuple[str, str]:\n"
    "    if current_m <= 7.0 or (change_1m_m is not None and change_1m_m <= -0.3):\n"
    '        return "demand_cooling", "需求降温"\n'
    "    if current_m >= 9.0:\n"
    '        return "demand_tight", "需求偏紧"\n'
    '    return "stable", "稳定"',
    "def _employment_wage_status(*, current_yoy_pct: float, change_1m_pct: float | None) -> tuple[str, str]:\n"
    "    if current_yoy_pct >= 4.5 and (change_1m_pct is None or change_1m_pct >= 0.0):\n"
    '        return "wage_pressure", "工资压力"\n'
    "    if change_1m_pct is not None and change_1m_pct <= -0.3:\n"
    '        return "wage_cooling", "工资降温"\n'
    '    return "stable", "稳定"',
)

MACRO_MODULE_INFLATION_REGIME_FALLBACK_TOKENS = (
    '_number(cpi.get("change_1m_pct")) or 0.0',
    '_number(core_cpi.get("current_yoy_pct")) or 0.0',
    '_number(core_cpi.get("change_1m_pct")) or 0.0',
    '_number(breakeven.get("current_pct")) or 0.0',
    '_number(breakeven.get("change_1m_bp")) or 0.0',
)

MACRO_MODULE_INFLATION_BREAKEVEN_STATUS_FALLBACK_TOKENS = (
    "def _inflation_breakeven_status(*, current_pct: float, change_1m_bp: float | None) -> tuple[str, str]:\n"
    "    if current_pct >= 2.5 or (change_1m_bp is not None and change_1m_bp >= 10.0):\n"
    '        return "expectation_pressure", "预期升温"\n'
    "    if change_1m_bp is not None and change_1m_bp <= -10.0:\n"
    '        return "expectation_relief", "预期降温"\n'
    '    return "stable", "稳定"',
)

MACRO_MODULE_VOLATILITY_REGIME_FALLBACK_TOKENS = (
    '_number(vix.get("current_index")) or 0.0',
    '_number(vix.get("change_1w_index")) or 0.0',
    '_number(row.get("current_points")) or 0.0 for row in front_rows',
    '_number(row.get("change_1w_points")) or 0.0 for row in front_rows',
    '_number(term.get("current_points")) or 0.0',
    '_number(etf.get("change_1w_pct")) or 0.0',
    '_number(move.get("current_index")) or 0.0',
    '_number(move.get("change_1w_index")) or 0.0',
)

MACRO_MODULE_ASSET_REGIME_FALLBACK_TOKENS = (
    '_number(spx.get("change_1w_pct")) or 0.0',
    '_number(tlt.get("change_1w_pct")) or 0.0',
    '_number(dxy.get("change_1w_pct")) or 0.0',
    '_number(wti.get("change_1w_pct")) or 0.0',
    '_number(btc.get("change_1w_pct")) or 0.0',
    '_number(vix.get("change_1w_index")) or 0.0',
    '_number(hy_oas.get("change_1w_bp")) or 0.0',
)

MACRO_MODULE_EQUITY_REGIME_FALLBACK_TOKENS = (
    '_number(spx.get("change_1w_pct")) or 0.0',
    '_number(ndx.get("change_1w_pct")) or 0.0',
    '_number(rut.get("change_1w_pct")) or 0.0',
    '_number(qqq.get("change_1w_pct")) or 0.0',
    '_number(iwm.get("change_1w_pct")) or 0.0',
    '_number(positioning.get("change_1w_k")) or 0.0',
)

MACRO_MODULE_BOND_REGIME_FALLBACK_TOKENS = (
    '_number(tlt.get("change_1w_pct")) or 0.0',
    '_number(ief.get("change_1w_pct")) or 0.0',
    '_number(lqd.get("change_1w_pct")) or 0.0',
    '_number(hyg.get("change_1w_pct")) or 0.0',
    '_number(hy_oas.get("change_1w_bp")) or 0.0',
    '_number(ig_oas.get("change_1w_bp")) or 0.0',
)

MACRO_MODULE_COMMODITY_REGIME_FALLBACK_TOKENS = (
    '_number(wti.get("change_1w_pct")) or 0.0',
    '_number(brent.get("change_1w_pct")) or 0.0',
    '_number(natgas.get("change_1w_pct")) or 0.0',
    '_number(gold.get("change_1w_pct")) or 0.0',
    '_number(copper.get("change_1w_pct")) or 0.0',
)

MACRO_MODULE_FX_REGIME_FALLBACK_TOKENS = (
    '_number(dxy.get("change_1w_pct")) or 0.0',
    '_number(broad_dollar.get("change_1w_pct")) or 0.0',
    '_number(eurusd.get("change_1w_pct")) or 0.0',
    '_number(usdjpy.get("change_1w_pct")) or 0.0',
    '_number(usdcny.get("change_1w_pct")) or 0.0',
    '_number(uup.get("change_1w_pct")) or 0.0',
)

MACRO_MODULE_CRYPTO_REGIME_FALLBACK_TOKENS = (
    '_number(btc.get("change_1w_pct")) or 0.0',
    '_number(eth.get("change_1w_pct")) or 0.0',
)

MACRO_MODULE_LIQUIDITY_REGIME_FALLBACK_TOKENS = (
    '_number(corridor.get("current_bp")) or 0.0',
    '_number(net.get("change_1w_bn")) or 0.0',
    '_number(tga.get("change_1w_bn")) or 0.0',
    '_number(rrp.get("current_bn")) or 0.0',
)

MACRO_MODULE_LIQUIDITY_TGA_STATUS_FALLBACK_TOKENS = (
    "def _liquidity_tga_status(*, current_bn: float, change_1w_bn: float | None) -> tuple[str, str]:\n"
    "    if change_1w_bn is not None and change_1w_bn >= 50.0:\n"
    '        return "treasury_drain", "财政抽水"\n'
    "    if change_1w_bn is not None and change_1w_bn <= -50.0:\n"
    '        return "treasury_injection", "财政注入"\n'
    "    if current_bn >= 900.0:\n"
    '        return "treasury_high", "TGA 偏高"\n'
    '    return "stable", "稳定"',
)

MACRO_MODULE_CREDIT_REGIME_FALLBACK_TOKENS = (
    '_number(hy.get("current_bp")) or 0.0',
    '_number(hy.get("change_1w_bp")) or 0.0',
    '_number(hy.get("change_1m_bp")) or 0.0',
    '_number(tail.get("current_bp")) or 0.0',
    '_number(tail.get("change_1w_bp")) or 0.0',
    '_number(tail.get("change_1m_bp")) or 0.0',
)

MACRO_MODULE_POLICY_REGIME_FALLBACK_TOKENS = (
    '_number(effr_iorb.get("current_bp")) or 0.0',
    '_number(sofr_effr.get("current_bp")) or 0.0',
)

MACRO_MODULE_YIELD_CURVE_REGIME_FALLBACK_TOKENS = (
    '_number(two_ten.get("current_bp")) or 0.0',
    '_number(two_ten.get("change_1w_bp")) or 0.0',
    '_yield_curve_feature_change_bp(_mapping(feature_map.get("rates:dgs10")), days=7) or 0.0',
)

MACRO_MODULE_YIELD_CURVE_SPREAD_STATUS_FALLBACK_TOKENS = (
    "def _yield_curve_spread_status(\n"
    "    *,\n"
    "    current_bp: float,\n"
    "    change_1w_bp: float | None,\n"
    ") -> tuple[str, str]:\n"
    "    if change_1w_bp is None:\n"
    '        return ("inverted", "倒挂") if current_bp < 0 else ("stable", "稳定")',
)

MACRO_MODULE_REAL_RATE_REGIME_FALLBACK_TOKENS = (
    '_number(ten_year_real.get("current_pct")) or 0.0',
    '_number(ten_year_real.get("change_1w_bp")) or 0.0',
    '_number(ten_year_breakeven.get("change_1w_bp")) or 0.0',
)

MACRO_MODULE_REAL_RATE_STATUS_FALLBACK_TOKENS = (
    "def _real_rate_real_status(*, current_pct: float, change_1w_bp: float | None) -> tuple[str, str]:\n"
    "    if current_pct >= 2.0 or (change_1w_bp is not None and change_1w_bp >= 15.0):\n"
    '        return "valuation_pressure", "估值压力"\n'
    "    if change_1w_bp is not None and change_1w_bp <= -15.0:\n"
    '        return "valuation_relief", "估值缓和"\n'
    '    return "stable", "稳定"',
    "def _real_rate_inflation_status(*, current_pct: float, change_1w_bp: float | None) -> tuple[str, str]:\n"
    "    if change_1w_bp is None:\n"
    '        return "stable", "稳定"',
)

MACRO_MODULE_DISPLAY_FALLBACK_TOKENS = (
    '_mapping(value).get("regime") or "data_gap"',
    '_int_or_none(item.get("point_count")) or 0',
)

ALLOWED_DELETED_MACRO_ROUTE_REFERENCES = {
    "src/parallax/app/surfaces/api/routes_macro.py": {"/macro/assets/correlation"},
    "web/src/features/macro/api/useMacroAssetCorrelationQuery.ts": {"/macro/assets/correlation"},
}


def _iter_macro_runtime_source_paths() -> list[Path]:
    suffixes = {".py", ".ts", ".tsx"}
    paths: list[Path] = []
    for root in MACRO_RUNTIME_SCAN_ROOTS:
        if root.is_file():
            paths.append(root)
            continue
        paths.extend(path for path in root.rglob("*") if path.suffix in suffixes)
    return sorted(paths)


def test_runtime_source_does_not_reference_retired_macro_serving_contracts() -> None:
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if ALEMBIC_VERSIONS in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(ROOT)} contains {token}"
            for token in FORBIDDEN_MACRO_COMPATIBILITY_TOKENS
            if token in text
        )

    assert offenders == []


def test_macro_routes_do_not_expose_query_token_auth_compatibility() -> None:
    source = (SRC / "app/surfaces/api/routes_macro.py").read_text(encoding="utf-8")
    forbidden_tokens = (
        'Query(alias="token")',
        '"token", "window"',
        '"assets", "token"',
        '"concept_keys", "token"',
    )

    assert [token for token in forbidden_tokens if token in source] == []


def test_macro_contract_docs_do_not_publish_query_token_auth_compatibility() -> None:
    contracts = (ROOT / "docs/CONTRACTS.md").read_text(encoding="utf-8")
    macro_series_contract = contracts.split("- `/api/macro/series`", 1)[1].split(
        "\n\nWatchlist handle intel contract:",
        1,
    )[0]
    forbidden_tokens = (
        "Query-token auth uses the shared `token` parameter.",
        "shared `token` parameter",
    )

    assert [token for token in forbidden_tokens if token in macro_series_contract] == []


def test_deleted_macro_product_routes_do_not_reappear_in_runtime_source() -> None:
    forbidden_route_tokens = tuple(f"/macro/{module_id}" for module_id in HARD_DELETED_MACRO_MODULE_IDS)
    offenders: list[str] = []

    for path in _iter_macro_runtime_source_paths():
        relative_path = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        allowed_tokens = ALLOWED_DELETED_MACRO_ROUTE_REFERENCES.get(relative_path, set())
        offenders.extend(
            f"{relative_path} contains deleted macro route {token}"
            for token in forbidden_route_tokens
            if token in text and token not in allowed_tokens
        )

    assert offenders == []


def test_deleted_macro_frontend_page_components_are_removed() -> None:
    removed_paths = [
        WEB_SRC / "features/macro/ui/pages/MacroMatrixPage.tsx",
        WEB_SRC / "features/macro/ui/correlation/CorrelationRead.tsx",
    ]

    assert [path.relative_to(ROOT).as_posix() for path in removed_paths if path.exists()] == []


def test_macro_runtime_source_has_no_future_source_backlog_placeholders() -> None:
    offenders: list[str] = []
    for path in _iter_macro_runtime_source_paths():
        relative_path = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{relative_path} contains source-backlog placeholder {token!r}"
            for token in MACRO_SOURCE_BACKLOG_PLACEHOLDER_TOKENS
            if token in text
        )

    assert offenders == []


def test_macro_runtime_source_does_not_manufacture_unnamed_indicator_labels() -> None:
    offenders: list[str] = []
    for path in _iter_macro_runtime_source_paths():
        relative_path = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{relative_path} contains product placeholder {token!r}"
            for token in MACRO_PRODUCT_PLACEHOLDER_TOKENS
            if token in text
        )

    assert offenders == []


def test_macro_module_views_do_not_repair_observation_source_from_provider_or_series() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    feature_source = source.split("def _feature_from_observations", 1)[1].split("def _observation_value", 1)[0]
    offenders = [token for token in MACRO_MODULE_OBSERVATION_SOURCE_FALLBACK_TOKENS[:2] if token in feature_source]
    offenders.extend(token for token in MACRO_MODULE_OBSERVATION_SOURCE_FALLBACK_TOKENS[2:] if token in source)

    assert offenders == []


def test_macro_module_views_do_not_silently_drop_provenance_rows_with_missing_source() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    provenance_source = source.split("def _observation_source_rows", 1)[1].split("def _source_row_id", 1)[0]

    assert [token for token in MACRO_MODULE_PROVENANCE_SOURCE_DROP_TOKENS if token in provenance_source] == []


def test_macro_runtime_source_has_no_empty_chart_compatibility_factory() -> None:
    offenders: list[str] = []
    for path in _iter_macro_runtime_source_paths():
        relative_path = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{relative_path} contains empty runtime factory {token!r}"
            for token in MACRO_EMPTY_RUNTIME_FACTORY_TOKENS
            if token in text
        )

    assert offenders == []


def test_macro_module_views_do_not_use_raw_concept_key_or_unit_metadata_fallbacks() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_RAW_CONCEPT_METADATA_FALLBACK_TOKENS if token in source] == []


def test_macro_feature_engine_does_not_write_raw_key_or_unit_metadata_fallbacks() -> None:
    source = (SRC / "domains/macro_intel/services/macro_feature_engine.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_FEATURE_ENGINE_METADATA_FALLBACK_TOKENS if token in source] == []


def test_macro_feature_engine_does_not_silently_drop_missing_concept_key_observations() -> None:
    source = (SRC / "domains/macro_intel/services/macro_feature_engine.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_FEATURE_ENGINE_CONCEPT_KEY_DROP_TOKENS if token in source] == []


def test_macro_feature_engine_does_not_write_empty_source_metadata_fallbacks() -> None:
    source = (SRC / "domains/macro_intel/services/macro_feature_engine.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_FEATURE_ENGINE_SOURCE_FALLBACK_TOKENS if token in source] == []


def test_macro_feature_engine_does_not_use_raw_value_as_numeric_fallback() -> None:
    source = (SRC / "domains/macro_intel/services/macro_feature_engine.py").read_text(encoding="utf-8")
    numeric_value_source = source.split("def _numeric_value", 1)[1].split("def _to_float", 1)[0]

    offenders = [token for token in MACRO_FEATURE_ENGINE_NUMERIC_VALUE_FALLBACK_TOKENS if token in numeric_value_source]

    assert offenders == []


def test_macro_asset_correlation_does_not_use_raw_value_as_numeric_fallback() -> None:
    source = (SRC / "domains/macro_intel/services/macro_asset_correlation.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_ASSET_CORRELATION_NUMERIC_VALUE_FALLBACK_TOKENS if token in source] == []


def test_macro_asset_correlation_does_not_silently_drop_malformed_observed_at_rows() -> None:
    source = (SRC / "domains/macro_intel/services/macro_asset_correlation.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_ASSET_CORRELATION_OBSERVED_AT_DROP_TOKENS if token in source] == []


def test_macro_asset_correlation_does_not_write_empty_source_metadata_fallbacks() -> None:
    source = (SRC / "domains/macro_intel/services/macro_asset_correlation.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_ASSET_CORRELATION_SOURCE_FALLBACK_TOKENS if token in source] == []


def test_macro_asset_correlation_does_not_default_ranking_metadata_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_asset_correlation.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_ASSET_CORRELATION_RANKING_FALLBACK_TOKENS if token in source] == []


def test_macro_asset_correlation_does_not_use_concept_key_as_title_fallback() -> None:
    source = (SRC / "domains/macro_intel/services/macro_asset_correlation.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_ASSET_CORRELATION_TITLE_FALLBACK_TOKENS if token in source] == []


def test_macro_gap_payloads_require_concept_metadata_without_code_label_fallback() -> None:
    source = (SRC / "domains/macro_intel/services/macro_gap_payloads.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_GAP_PAYLOAD_CONCEPT_METADATA_FALLBACK_TOKENS if token in source] == []


def test_macro_gap_payloads_do_not_humanize_missing_codes_without_named_subjects() -> None:
    source = (SRC / "domains/macro_intel/services/macro_gap_payloads.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_GAP_PAYLOAD_HUMANIZED_MISSING_FALLBACK_TOKENS if token in source] == []


def test_macro_feature_engine_does_not_write_optional_latest_unit_fallbacks() -> None:
    source = (SRC / "domains/macro_intel/services/macro_feature_engine.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_FEATURE_ENGINE_UNIT_FALLBACK_TOKENS if token in source] == []


def test_macro_feature_engine_does_not_write_features_from_missing_observed_at() -> None:
    source = (SRC / "domains/macro_intel/services/macro_feature_engine.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_FEATURE_ENGINE_OBSERVED_AT_FALLBACK_TOKENS if token in source] == []


def test_macro_feature_engine_does_not_silently_drop_malformed_observed_at_rows() -> None:
    source = (SRC / "domains/macro_intel/services/macro_feature_engine.py").read_text(encoding="utf-8")
    dedupe_source = source.split("def _deduped_observations", 1)[1].split("def _sort_key", 1)[0]

    assert [token for token in MACRO_FEATURE_ENGINE_OBSERVED_AT_DROP_TOKENS if token in dedupe_source] == []


def test_macro_feature_engine_does_not_default_unknown_frequency_to_daily_freshness() -> None:
    source = (SRC / "domains/macro_intel/services/macro_feature_engine.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_FEATURE_ENGINE_FREQUENCY_FALLBACK_TOKENS if token in source] == []


def test_macro_feature_engine_does_not_default_missing_data_quality_to_ok() -> None:
    source = (SRC / "domains/macro_intel/services/macro_feature_engine.py").read_text(encoding="utf-8")
    data_quality_source = source.split("def _series_data_quality", 1)[1].split("__all__", 1)[0]

    assert [token for token in MACRO_FEATURE_ENGINE_DATA_QUALITY_FALLBACK_TOKENS if token in data_quality_source] == []


def test_macro_module_views_do_not_manufacture_judgement_review_stats() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_JUDGEMENT_REVIEW_STAT_FALLBACK_TOKENS if token in source] == []


def test_macro_scenario_engine_does_not_default_quality_blocker_severity() -> None:
    source = (SRC / "domains/macro_intel/services/macro_scenario_engine.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_SCENARIO_QUALITY_FALLBACK_TOKENS if token in source] == []


def test_macro_scenario_engine_does_not_default_missing_node_scores_into_confidence() -> None:
    source = (SRC / "domains/macro_intel/services/macro_scenario_engine.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_SCENARIO_CONFIDENCE_SCORE_FALLBACK_TOKENS if token in source] == []


def test_macro_scenario_engine_does_not_infer_trigger_display_metadata_from_codes() -> None:
    source = (SRC / "domains/macro_intel/services/macro_scenario_engine.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_SCENARIO_TRIGGER_DISPLAY_FALLBACK_TOKENS if token in source] == []


def test_macro_scenario_engine_does_not_default_feature_change_source_labels() -> None:
    source = (SRC / "domains/macro_intel/services/macro_scenario_engine.py").read_text(encoding="utf-8")
    source_label_source = source.split("def _source_label", 1)[1].split("def _quality_blockers", 1)[0]

    assert [token for token in MACRO_SCENARIO_SOURCE_LABEL_FALLBACK_TOKENS if token in source_label_source] == []


def test_macro_scenario_engine_requires_complete_feature_change_latest_metadata() -> None:
    source = (SRC / "domains/macro_intel/services/macro_scenario_engine.py").read_text(encoding="utf-8")
    feature_change_source = source.split("def _feature_top_changes", 1)[1].split("def _source_label", 1)[0]

    assert [token for token in MACRO_SCENARIO_FEATURE_LATEST_FALLBACK_TOKENS if token in feature_change_source] == []


def test_macro_scenario_engine_does_not_emit_legacy_trade_map_code_lists() -> None:
    source = (SRC / "domains/macro_intel/services/macro_scenario_engine.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_SCENARIO_TRADE_MAP_LEGACY_CODE_LIST_TOKENS if token in source] == []


def test_macro_regime_engine_does_not_default_missing_panel_scores_into_chain_scores() -> None:
    source = (SRC / "domains/macro_intel/services/macro_regime_engine.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_REGIME_PANEL_SCORE_FALLBACK_TOKENS if token in source] == []


def test_macro_regime_engine_does_not_default_missing_coverage_metadata() -> None:
    source = (SRC / "domains/macro_intel/services/macro_regime_engine.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_REGIME_COVERAGE_FALLBACK_TOKENS if token in source] == []


def test_macro_regime_engine_does_not_default_missing_feature_metadata() -> None:
    source = (SRC / "domains/macro_intel/services/macro_regime_engine.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_REGIME_FEATURE_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_missing_scenario_confidence_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_SCENARIO_CONFIDENCE_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_missing_scenario_regime_from_snapshot() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_SCENARIO_REGIME_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_missing_scenario_cases_to_empty() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_SCENARIO_CASES_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_repair_base_case_fields_from_other_scenario_fields() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_BASE_CASE_FIELD_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_rebuild_missing_scenario_quality_blockers_from_data_health() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_SCENARIO_QUALITY_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_missing_scenario_signal_lists_to_empty() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_SCENARIO_LIST_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_use_section_labels_as_structured_regime_fallbacks() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    regime_label_source = source.split("def _structured_regime_label", 1)[1].split(
        "def _structured_analysis_evidence", 1
    )[0]

    assert [
        token for token in MACRO_MODULE_STRUCTURED_REGIME_LABEL_FALLBACK_TOKENS if token in regime_label_source
    ] == []


def test_macro_module_views_do_not_infer_scenario_signal_display_metadata_from_codes() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_SCENARIO_SIGNAL_DISPLAY_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_derive_scenario_severity_labels() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    compact_source = source.split("def _compact_signal", 1)[1].split("def _quality_blocker_item", 1)[0]

    assert [token for token in MACRO_MODULE_SCENARIO_SEVERITY_LABEL_FALLBACK_TOKENS if token in compact_source] == []


def test_macro_module_views_do_not_derive_watchlist_severity_labels() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_WATCHLIST_SEVERITY_LABEL_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_copy_watchlist_window_as_display_label() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    watchlist_source = source.split("def _watchlist_rule", 1)[1].split("def _required_scenario_rule_text", 1)[0]

    assert [token for token in MACRO_MODULE_WATCHLIST_WINDOW_LABEL_FALLBACK_TOKENS if token in watchlist_source] == []


def test_macro_module_views_do_not_copy_future_watch_catalyst_window_as_display_label() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    future_watch_source = source.split("def _future_watch_catalyst", 1)[1].split(
        "def _future_event_catalyst",
        1,
    )[0]

    assert [
        token
        for token in MACRO_MODULE_FUTURE_WATCH_CATALYST_WINDOW_LABEL_FALLBACK_TOKENS
        if token in future_watch_source
    ] == []


def test_macro_module_views_do_not_derive_future_watch_catalyst_severity_labels() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    future_watch_source = source.split("def _future_watch_catalyst", 1)[1].split(
        "def _future_event_catalyst",
        1,
    )[0]

    assert [
        token
        for token in MACRO_MODULE_FUTURE_WATCH_CATALYST_SEVERITY_LABEL_FALLBACK_TOKENS
        if token in future_watch_source
    ] == []


def test_macro_module_views_do_not_repair_future_event_catalyst_display_labels() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    future_event_source = source.split("def _future_event_catalyst", 1)[1].split(
        "def _future_catalyst_window",
        1,
    )[0]

    assert [
        token for token in MACRO_MODULE_FUTURE_EVENT_CATALYST_DISPLAY_FALLBACK_TOKENS if token in future_event_source
    ] == []


def test_macro_module_views_do_not_derive_market_event_flow_display_labels() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    market_event_source = source.split("def _market_event_flow_row", 1)[1].split(
        "def _required_event_catalyst_text",
        1,
    )[0]

    assert [
        token for token in MACRO_MODULE_MARKET_EVENT_FLOW_DISPLAY_FALLBACK_TOKENS if token in market_event_source
    ] == []


def test_macro_module_views_do_not_derive_market_event_flow_classification_labels() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    market_event_source = source.split("def _market_event_flow_row", 1)[1].split(
        "def _required_event_catalyst_text",
        1,
    )[0]

    assert [
        token for token in MACRO_MODULE_MARKET_EVENT_FLOW_CLASSIFICATION_FALLBACK_TOKENS if token in market_event_source
    ] == []


def test_macro_module_views_do_not_derive_structured_fed_event_flow_evidence() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    structured_fed_source = source.split("def _structured_fed_communication_evidence", 1)[1].split(
        "def _required_structured_fed_communication_source",
        1,
    )[0]

    assert [
        token
        for token in MACRO_STRUCTURED_FED_COMMUNICATION_EVENT_FLOW_FALLBACK_TOKENS
        if token in structured_fed_source
    ] == []


def test_macro_module_views_do_not_derive_evidence_item_severity_labels() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    evidence_item_source = source.split("def _evidence_item", 1)[1].split("def _provenance", 1)[0]

    assert [
        token for token in MACRO_MODULE_EVIDENCE_ITEM_SEVERITY_LABEL_FALLBACK_TOKENS if token in evidence_item_source
    ] == []


def test_macro_module_views_do_not_allow_optional_evidence_item_window_labels() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    evidence_item_source = source.split("def _evidence_item", 1)[1].split("def _provenance", 1)[0]

    assert [
        token for token in MACRO_MODULE_EVIDENCE_ITEM_WINDOW_LABEL_FALLBACK_TOKENS if token in evidence_item_source
    ] == []


def test_macro_module_views_do_not_derive_quality_blocker_severity_labels() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    quality_blocker_source = source.split("def _compact_quality_blocker", 1)[1].split(
        "def _quality_blocker_severity",
        1,
    )[0]

    assert [
        token
        for token in MACRO_MODULE_QUALITY_BLOCKER_SEVERITY_LABEL_FALLBACK_TOKENS
        if token in quality_blocker_source
    ] == []


def test_macro_module_views_do_not_silently_drop_module_evidence_items() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_EVIDENCE_ITEM_DROP_TOKENS if token in source] == []


def test_macro_module_views_do_not_silently_drop_top_change_signals() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_COMPACT_SIGNAL_DROP_TOKENS if token in source] == []


def test_macro_module_views_do_not_silently_drop_structured_signal_lines() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    structured_source = source.split("def _structured_market_evidence", 1)[1].split("def _structured_market_trade", 1)[
        0
    ]

    assert [token for token in MACRO_MODULE_STRUCTURED_SIGNAL_LINE_DROP_TOKENS if token in structured_source] == []


def test_macro_module_views_do_not_silently_drop_market_thesis_missing_evidence() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    thesis_source = source.split("def _structured_market_thesis_row", 1)[1].split("def _structured_base_case", 1)[0]

    assert [token for token in MACRO_MODULE_STRUCTURED_MARKET_THESIS_DROP_TOKENS if token in thesis_source] == []


def test_macro_module_views_do_not_keep_dead_market_invalidation_helper() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_STRUCTURED_MARKET_INVALIDATION_DEAD_TOKENS if token in source] == []


def test_macro_module_views_do_not_silently_drop_structured_market_trade_rows() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    trade_source = source.split("def _structured_market_trade", 1)[1].split("def _structured_fed_communication_row", 1)[
        0
    ]

    assert [token for token in MACRO_MODULE_STRUCTURED_MARKET_TRADE_DROP_TOKENS if token in trade_source] == []


def test_macro_module_views_do_not_use_generic_fed_doc_as_structured_evidence_label() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    fed_evidence_source = source.split("def _structured_fed_communication_evidence", 1)[1].split(
        "def _fed_document_type_label", 1
    )[0]

    assert [
        token
        for token in MACRO_MODULE_STRUCTURED_FED_COMMUNICATION_LABEL_FALLBACK_TOKENS
        if token in fed_evidence_source
    ] == []


def test_macro_module_views_do_not_silently_drop_structured_fed_communication_rows() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    fed_row_source = source.split("def _structured_fed_communication_row", 1)[1].split(
        "def _structured_fed_communication_evidence", 1
    )[0]

    assert [token for token in MACRO_MODULE_STRUCTURED_FED_COMMUNICATION_DROP_TOKENS if token in fed_row_source] == []


def test_macro_module_views_do_not_omit_structured_fed_communication_source() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    fed_evidence_source = source.split("def _structured_fed_communication_evidence", 1)[1].split(
        "def _required_structured_fed_communication_label", 1
    )[0]

    assert [
        token for token in MACRO_MODULE_STRUCTURED_FED_COMMUNICATION_SOURCE_DROP_TOKENS if token in fed_evidence_source
    ] == []


def test_macro_module_views_do_not_infer_fed_speech_speaker_from_title() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    fed_speaker_source = source.split("def _event_speaker", 1)[1].split("def _event_days_label", 1)[0]

    assert [token for token in MACRO_MODULE_FED_SPEAKER_TITLE_FALLBACK_TOKENS if token in fed_speaker_source] == []


def test_macro_module_views_do_not_use_generic_fed_doc_as_structured_regime_label() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    fed_document_label_source = source.split("def _fed_document_type_label", 1)[1].split(
        "def _structured_analysis_row", 1
    )[0]

    assert [
        token
        for token in MACRO_MODULE_STRUCTURED_FED_COMMUNICATION_DOCUMENT_TYPE_FALLBACK_TOKENS
        if token in fed_document_label_source
    ] == []


def test_macro_module_views_do_not_use_event_description_as_display_detail() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_EVENT_CATALYST_DESCRIPTION_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_use_event_description_as_text_value() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    event_text_source = source.split("def _event_text_value", 1)[1].split("def _event_source_url", 1)[0]

    assert [token for token in MACRO_MODULE_EVENT_TEXT_DESCRIPTION_FALLBACK_TOKENS if token in event_text_source] == []


def test_macro_module_views_do_not_use_quality_blocker_description_as_display_detail() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_QUALITY_BLOCKER_DESCRIPTION_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_silently_drop_quality_blockers_with_missing_display_evidence() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_QUALITY_BLOCKER_DISPLAY_DROP_TOKENS if token in source] == []


def test_macro_module_views_do_not_silently_drop_compact_quality_blockers() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    compact_source = source.split("compact_quality_blockers = [", 1)[1].split("payload = {", 1)[0]

    assert "if item is not None" not in compact_source


def test_macro_module_views_do_not_silently_drop_watchlist_rules() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    rules_source = source.split("def _watchlist_rules", 1)[1].split("def _watchlist_rule", 1)[0]

    assert "if row is not None" not in rules_source


def test_macro_module_views_do_not_silently_drop_future_watch_catalysts() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    watch_source = source.split("def _future_catalysts", 1)[1].split("rows.extend", 1)[0]

    assert "if row is not None" not in watch_source


def test_macro_module_views_do_not_emit_availability_placeholder_cells() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_AVAILABILITY_PLACEHOLDER_TOKENS if token in source] == []


def test_macro_module_views_do_not_allow_optional_availability_source_labels() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    availability_source = source.split("def _availability_note", 1)[1].split(
        "def _required_availability_source_label", 1
    )[0]

    assert [token for token in MACRO_MODULE_AVAILABILITY_OPTIONAL_SOURCE_TOKENS if token in availability_source] == []


def test_macro_module_views_do_not_allow_optional_feature_surface_source_labels() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    feature_surface_source = (
        source.split("def _tile", 1)[1].split("def _primary_chart", 1)[0]
        + source.split("def _table_row", 1)[1].split("def _availability_table", 1)[0]
    )

    assert [token for token in MACRO_MODULE_FEATURE_SOURCE_OPTIONAL_TOKENS if token in feature_surface_source] == []


def test_macro_module_views_do_not_use_feature_latest_placeholders_for_present_surfaces() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    feature_surface_source = (
        source.split("def _tile", 1)[1].split("def _primary_chart", 1)[0]
        + source.split("def _table_row", 1)[1].split("def _availability_table", 1)[0]
    )

    assert [token for token in MACRO_MODULE_FEATURE_LATEST_PLACEHOLDER_TOKENS if token in feature_surface_source] == []


def test_macro_module_views_do_not_use_feature_latest_unit_placeholders_for_present_surfaces() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    feature_surface_source = (
        source.split("def _tile", 1)[1].split("def _primary_chart", 1)[0]
        + source.split("def _table_row", 1)[1].split("def _availability_table", 1)[0]
        + source.split("def _availability_table", 1)[1].split("def _module_read", 1)[0]
    )

    assert [
        token for token in MACRO_MODULE_FEATURE_LATEST_UNIT_PLACEHOLDER_TOKENS if token in feature_surface_source
    ] == []


def test_macro_module_views_do_not_catalog_fill_present_feature_display_metadata() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    feature_metadata_source = source.split("def _feature_label", 1)[1].split("def _public_text", 1)[0]

    assert [
        token for token in MACRO_MODULE_FEATURE_DISPLAY_METADATA_FALLBACK_TOKENS if token in feature_metadata_source
    ] == []


def test_macro_module_views_do_not_repair_chart_history_from_latest_or_drop_bad_points() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    chart_source = source.split("def _chart_series", 1)[1].split("def _table", 1)[0]

    assert [token for token in MACRO_MODULE_CHART_HISTORY_COMPATIBILITY_TOKENS if token in chart_source] == []


def test_macro_module_views_do_not_treat_present_feature_history_points_as_optional_surface_data() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    feature_history_surface_source = (
        source.split("def _tile", 1)[1].split("def _primary_chart", 1)[0]
        + source.split("def _table_row", 1)[1].split("def _availability_table", 1)[0]
        + source.split("def _availability_table", 1)[1].split("def _module_read", 1)[0]
    )

    assert [
        token
        for token in MACRO_MODULE_FEATURE_HISTORY_OPTIONAL_SURFACE_TOKENS
        if token in feature_history_surface_source
    ] == []


def test_macro_module_views_do_not_use_availability_latest_placeholders_for_present_features() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    availability_source = source.split("def _availability_table", 1)[1].split("def _module_read", 1)[0]

    assert [
        token for token in MACRO_MODULE_AVAILABILITY_LATEST_PLACEHOLDER_TOKENS if token in availability_source
    ] == []


def test_macro_module_views_do_not_use_snapshot_header_time_placeholders_for_real_snapshots() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    header_source = source.split("def _snapshot_header", 1)[1].split("def _tile", 1)[0]

    assert [token for token in MACRO_MODULE_SNAPSHOT_HEADER_TIME_PLACEHOLDER_TOKENS if token in header_source] == []


def test_macro_module_views_do_not_build_trade_map_checklist_from_legacy_code_lists() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_TRADE_MAP_ACTION_CHECKLIST_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_silently_drop_trade_map_action_checklist_rows() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    checklist_source = source.split("def _trade_map_action_checklist", 1)[1].split(
        "def _trade_map_holding_period_review", 1
    )[0]

    assert [token for token in MACRO_MODULE_TRADE_MAP_ACTION_CHECKLIST_DROP_TOKENS if token in checklist_source] == []


def test_macro_module_views_do_not_silently_drop_trade_map_action_checklist_shape() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    checklist_source = source.split("def _trade_map_action_checklist", 1)[1].split(
        "def _trade_map_holding_period_review", 1
    )[0]

    assert [
        token for token in MACRO_MODULE_TRADE_MAP_ACTION_CHECKLIST_SHAPE_DROP_TOKENS if token in checklist_source
    ] == []


def test_macro_module_views_do_not_infer_trade_map_labels_from_expressions() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_TRADE_MAP_EXPRESSION_LABEL_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_silently_drop_trade_map_items() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    decision_source = source.split("def _decision_console", 1)[1].split("def _future_catalysts", 1)[0]
    item_source = source.split("def _trade_map_item", 1)[1].split("def _trade_map_historical_review", 1)[0]

    assert "if item is not None" not in decision_source.split("compact_quality_blockers", 1)[0]
    assert [token for token in MACRO_MODULE_TRADE_MAP_ITEM_DROP_TOKENS if token in item_source] == []


def test_macro_module_views_do_not_repair_watchlist_asset_fields_from_other_leg_fields() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_WATCHLIST_ASSET_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_use_labels_as_scenario_rule_identity_fallbacks() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_SCENARIO_RULE_KEY_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_silently_drop_scenario_rules_with_missing_display_fields() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_SCENARIO_RULE_DISPLAY_DROP_TOKENS if token in source] == []


def test_macro_module_views_do_not_use_event_labels_as_identity_fallbacks() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_EVENT_KEY_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_render_events_with_empty_source_fallbacks() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_EVENT_SOURCE_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_repair_event_source_from_raw_provider() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    event_catalyst_source = source.split("def _event_catalyst", 1)[1].split("def _event_raw_payload", 1)[0]

    assert [
        token for token in MACRO_MODULE_EVENT_CATALYST_SOURCE_PROVIDER_FALLBACK_TOKENS if token in event_catalyst_source
    ] == []


def test_macro_module_views_do_not_render_events_with_empty_kind_fallbacks() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_EVENT_KIND_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_silently_drop_events_with_missing_display_fields() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_EVENT_DISPLAY_FIELD_DROP_TOKENS if token in source] == []


def test_macro_module_views_do_not_use_placeholder_event_dates() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    event_detail_source = source.split("def _event_detail", 1)[1].split("def _event_text_value", 1)[0]

    assert [token for token in MACRO_MODULE_EVENT_DETAIL_DATE_PLACEHOLDER_TOKENS if token in event_detail_source] == []


def test_macro_module_views_do_not_repair_news_event_identity_from_news_item_or_headline() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_NEWS_EVENT_IDENTITY_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_news_event_scope_to_generic_market_event() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_NEWS_EVENT_SCOPE_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_news_event_impact_to_context() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_NEWS_EVENT_IMPACT_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_repair_news_event_date_from_raw_timestamps() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_NEWS_EVENT_DATE_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_silently_drop_news_events_with_missing_display_fields() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_NEWS_EVENT_DISPLAY_FIELD_DROP_TOKENS if token in source] == []


def test_macro_module_views_do_not_derive_news_event_flow_from_page_row_fields() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    news_event_source = source.split("def _market_news_event_flow_row", 1)[1].split(
        "def _required_market_news_event_text",
        1,
    )[0]

    assert [token for token in MACRO_MODULE_NEWS_EVENT_FLOW_DERIVATION_TOKENS if token in news_event_source] == []


def test_macro_module_views_do_not_default_missing_feature_history_points() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_HISTORY_POINTS_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_trade_review_metrics() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_TRADE_REVIEW_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_holding_review_metrics() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_HOLDING_REVIEW_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_silently_drop_judgement_review_windows() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    row_source = source.split("def _judgement_review_row", 1)[1].split("def _judgement_review_window", 1)[0]
    window_source = source.split("def _judgement_review_window", 1)[1].split("def _trade_map_item", 1)[0]

    assert "if row is not None" not in row_source
    assert [token for token in MACRO_MODULE_JUDGEMENT_REVIEW_WINDOW_DROP_TOKENS if token in window_source] == []


def test_macro_module_views_do_not_silently_drop_judgement_review_items() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    review_source = source.split("def _judgement_review", 1)[1].split("def _judgement_review_row", 1)[0]
    row_source = source.split("def _judgement_review_row", 1)[1].split("def _judgement_review_window", 1)[0]

    assert "if row is not None" not in review_source
    assert "return None" not in row_source


def test_macro_module_views_do_not_default_missing_status_changes_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_STATUS_CHANGE_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_missing_crypto_derivative_changes_to_stable_or_relief() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_CRYPTO_DERIVATIVE_STATUS_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_missing_credit_spread_changes_to_stable() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_CREDIT_SPREAD_STATUS_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_growth_regime_metrics_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_GROWTH_REGIME_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_missing_growth_changes_to_stable() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_GROWTH_STATUS_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_employment_regime_metrics_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_EMPLOYMENT_REGIME_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_missing_employment_changes_to_stable() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_EMPLOYMENT_STATUS_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_inflation_regime_metrics_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_INFLATION_REGIME_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_missing_inflation_breakeven_changes_to_stable() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_INFLATION_BREAKEVEN_STATUS_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_volatility_regime_metrics_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_VOLATILITY_REGIME_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_asset_regime_metrics_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    start = source.index("def _asset_regime(")
    end = source.index("def _equity_regime(", start)
    asset_regime_source = source[start:end]

    assert [token for token in MACRO_MODULE_ASSET_REGIME_FALLBACK_TOKENS if token in asset_regime_source] == []


def test_macro_module_views_do_not_default_equity_regime_metrics_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    start = source.index("def _equity_regime(")
    end = source.index("def _bond_regime(", start)
    equity_regime_source = source[start:end]

    assert [token for token in MACRO_MODULE_EQUITY_REGIME_FALLBACK_TOKENS if token in equity_regime_source] == []


def test_macro_module_views_do_not_default_bond_regime_metrics_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    start = source.index("def _bond_regime(")
    end = source.index("def _commodity_regime(", start)
    bond_regime_source = source[start:end]

    assert [token for token in MACRO_MODULE_BOND_REGIME_FALLBACK_TOKENS if token in bond_regime_source] == []


def test_macro_module_views_do_not_default_commodity_regime_metrics_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    start = source.index("def _commodity_regime(")
    end = source.index("def _fx_regime(", start)
    commodity_regime_source = source[start:end]

    assert [token for token in MACRO_MODULE_COMMODITY_REGIME_FALLBACK_TOKENS if token in commodity_regime_source] == []


def test_macro_module_views_do_not_default_fx_regime_metrics_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    start = source.index("def _fx_regime(")
    end = source.index("def _crypto_regime(", start)
    fx_regime_source = source[start:end]

    assert [token for token in MACRO_MODULE_FX_REGIME_FALLBACK_TOKENS if token in fx_regime_source] == []


def test_macro_module_views_do_not_default_crypto_regime_metrics_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    start = source.index("def _crypto_regime(")
    end = source.index("def _has_row_status(", start)
    crypto_regime_source = source[start:end]

    assert [token for token in MACRO_MODULE_CRYPTO_REGIME_FALLBACK_TOKENS if token in crypto_regime_source] == []


def test_macro_module_views_do_not_default_liquidity_regime_metrics_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    start = source.index("def _liquidity_regime(")
    end = source.index("def _liquidity_implications(", start)
    liquidity_regime_source = source[start:end]

    assert [token for token in MACRO_MODULE_LIQUIDITY_REGIME_FALLBACK_TOKENS if token in liquidity_regime_source] == []


def test_macro_module_views_do_not_default_missing_tga_change_to_stable() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_LIQUIDITY_TGA_STATUS_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_credit_regime_metrics_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    start = source.index("def _credit_regime(")
    end = source.index("def _credit_implications(", start)
    credit_regime_source = source[start:end]

    assert [token for token in MACRO_MODULE_CREDIT_REGIME_FALLBACK_TOKENS if token in credit_regime_source] == []


def test_macro_module_views_do_not_default_policy_regime_metrics_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    start = source.index("def _policy_regime(")
    end = source.index("def _policy_implications(", start)
    policy_regime_source = source[start:end]

    assert [token for token in MACRO_MODULE_POLICY_REGIME_FALLBACK_TOKENS if token in policy_regime_source] == []


def test_macro_module_views_do_not_default_yield_curve_regime_metrics_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    start = source.index("def _yield_curve_shape(")
    end = source.index("def _yield_curve_feature_change_bp(", start)
    yield_curve_regime_source = source[start:end]

    assert [
        token for token in MACRO_MODULE_YIELD_CURVE_REGIME_FALLBACK_TOKENS if token in yield_curve_regime_source
    ] == []


def test_macro_module_views_do_not_default_missing_yield_curve_spread_changes_to_stable() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_YIELD_CURVE_SPREAD_STATUS_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_real_rate_regime_metrics_to_zero() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")
    start = source.index("def _real_rate_regime(")
    end = source.index("def _real_rate_implications(", start)
    real_rate_regime_source = source[start:end]

    assert [token for token in MACRO_MODULE_REAL_RATE_REGIME_FALLBACK_TOKENS if token in real_rate_regime_source] == []


def test_macro_module_views_do_not_default_missing_real_rate_changes_to_stable() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_REAL_RATE_STATUS_FALLBACK_TOKENS if token in source] == []


def test_macro_module_views_do_not_default_display_contract_fields() -> None:
    source = (SRC / "domains/macro_intel/services/macro_module_views.py").read_text(encoding="utf-8")

    assert [token for token in MACRO_MODULE_DISPLAY_FALLBACK_TOKENS if token in source] == []


def test_canonical_docs_do_not_republish_retired_cex_run_serving_instructions() -> None:
    docs = (
        ROOT / "docs" / "ARCHITECTURE.md",
        ROOT / "docs" / "WORKERS.md",
        ROOT / "docs" / "CONTRACTS.md",
        ROOT / "docs" / "references" / "POSTGRES_PERFORMANCE.md",
    )
    offenders: list[str] = []
    for path in docs:
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(ROOT)} contains retired CEX run-serving instruction {token!r}"
            for token in RETIRED_CEX_RUN_SERVING_DOC_TOKENS
            if token in text
        )

    assert offenders == []


def test_cex_binance_hard_cut_cleanup_runtime_surface_is_removed() -> None:
    removed_paths = [
        SRC / "domains/asset_market/services/cex_binance_hard_cut_cleanup.py",
        SRC / "domains/asset_market/repositories/cex_binance_hard_cut_cleanup_repository.py",
        ROOT / "tests/unit/test_cex_binance_hard_cut_cleanup.py",
    ]
    assert [path.relative_to(ROOT).as_posix() for path in removed_paths if path.exists()] == []

    forbidden_runtime_tokens = {
        "cex-binance-hard-cut-cleanup",
        "cleanup_cex_binance_hard_cut",
        "CexBinanceHardCutAbort",
        "cex_binance_hard_cut_cleanup_repository",
    }
    scanned_paths = [
        SRC / "app/surfaces/cli/parser.py",
        SRC / "app/surfaces/cli/commands/ops.py",
        ROOT / "Makefile",
        ROOT / "tests/architecture/test_token_radar_sql_surface_inventory_contract.py",
    ]
    offenders = [
        f"{path.relative_to(ROOT)} contains {token}"
        for path in scanned_paths
        for token in forbidden_runtime_tokens
        if token in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_macrodata_quote_runtime_lane_is_removed() -> None:
    removed_paths = [
        SRC / "integrations/macrodata/quote_provider.py",
        SRC / "app/runtime/provider_wiring/macrodata.py",
        ROOT / "tests/unit/test_macrodata_quote_provider.py",
    ]
    assert [path.relative_to(ROOT).as_posix() for path in removed_paths if path.exists()] == []

    scanned_paths = [
        SRC / "integrations/macrodata/__init__.py",
        SRC / "app/runtime/provider_wiring/__init__.py",
        SRC / "app/runtime/provider_wiring/types.py",
        SRC / "app/runtime/providers_wiring.py",
        SRC / "app/runtime/bootstrap.py",
        SRC / "platform/config/settings.py",
        SRC / "app/surfaces/cli/commands/config.py",
        ROOT / "config.example.yaml",
    ]
    forbidden_tokens = (
        "MacrodataQuoteProvider",
        "stock_quote_provider",
        "macrodata_quote_timeout_seconds",
        "macrodata_quote_cache_ttl_seconds",
        "quote_timeout_seconds",
        "quote_cache_ttl_seconds",
    )
    offenders = [
        f"{path.relative_to(ROOT)} contains {token}"
        for path in scanned_paths
        for token in forbidden_tokens
        if token in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_macro_assets_daily_brief_requires_repository_contract_without_optional_loader() -> None:
    route_source = (SRC / "app/surfaces/api/routes_macro.py").read_text()

    forbidden_tokens = (
        'getattr(repos.macro_intel, "latest_macro_daily_brief", None)',
        "if loader is None:",
    )

    assert [token for token in forbidden_tokens if token in route_source] == []
    assert "repos.macro_intel.latest_macro_daily_brief" in route_source


def test_macrodata_bundle_import_requires_session_unit_of_work_without_conn_transaction_fallback() -> None:
    source = (SRC / "domains/macro_intel/services/macrodata_bundle_importer.py").read_text()

    forbidden_tokens = (
        "_unit_of_work",
        "_require_transaction",
        'getattr(repos, "unit_of_work", None)',
        'getattr(getattr(repos, "conn", None), "transaction", None)',
        'getattr(repos, "require_transaction", None)',
        "repository session does not expose a transaction",
    )

    assert "repos.unit_of_work()" in source
    assert "repos.require_transaction(" in source
    assert [token for token in forbidden_tokens if token in source] == []


def test_macro_sync_queue_summary_requires_repository_contract_without_optional_probe() -> None:
    source = (SRC / "domains/macro_intel/services/macro_sync_service.py").read_text()
    enqueue_source = source.split("def enqueue_due_windows", 1)[1].split("def run_claimed_window_once", 1)[0]
    forbidden_tokens = (
        "def _call_queue_summary",
        'getattr(repos.macro_intel, "macro_sync_queue_summary", None)',
        "if not callable(queue_summary):",
        "return {}",
    )

    assert "repos.macro_intel.macro_sync_queue_summary" in enqueue_source
    assert [token for token in forbidden_tokens if token in source] == []


def test_macrodata_runner_and_sync_service_use_formal_fred_and_timeout_settings_without_provider_shape_fallback() -> (
    None
):
    runner_source = (SRC / "integrations/macrodata/runner.py").read_text()
    sync_service_source = (SRC / "domains/macro_intel/services/macro_sync_service.py").read_text()
    combined = f"{runner_source}\n{sync_service_source}"
    forbidden_tokens = (
        'getattr(settings, "macrodata_fred_api_key_env", None)',
        'getattr(settings, "macrodata_fred_api_key", None)',
        'getattr(settings, "providers", None)',
        'getattr(providers, "macrodata", None)',
        'getattr(macrodata, "fred_api_key_env", None)',
        'getattr(macrodata, "fred_api_key", None)',
        'getattr(settings, "macrodata_timeout_seconds", None)',
        'getattr(macro_sync, "macrodata_timeout_seconds", None)',
        "value if value is not None else 240.0",
        "DEFAULT_FRED_API_KEY_ENV",
        "_DEFAULT_FRED_API_KEY_ENV",
    )
    violations = [token for token in forbidden_tokens if token in combined]

    assert violations == []
    assert "env_name = settings.macrodata_fred_api_key_env" in runner_source
    assert "value = settings.macrodata_fred_api_key" in runner_source
    assert "value = settings.workers.macro_sync.macrodata_timeout_seconds" in runner_source
    assert "macrodata_fred_api_key_env_settings_required" in runner_source
    assert "macrodata_fred_api_key_settings_required" in runner_source
    assert "macrodata_timeout_settings_required" in runner_source
    assert "env_name = settings.macrodata_fred_api_key_env" in sync_service_source
    assert "macrodata_fred_api_key_env_settings_required" in sync_service_source


def test_macro_observation_series_refresh_requires_connection_transaction_without_nullcontext() -> None:
    source = (SRC / "domains/macro_intel/repositories/macro_intel_repository.py").read_text()

    forbidden_tokens = (
        "nullcontext",
        'getattr(conn, "transaction", None)',
        'hasattr(conn, "transaction")',
        "conn.transaction()",
    )

    assert "with _transaction_context(self.conn):" in source
    assert "macro_observation_series_refresh_transaction_required" in source
    assert [token for token in forbidden_tokens if token in source] == []


def test_macro_projection_dirty_target_writes_require_connection_transaction_without_manual_commit() -> None:
    source = (SRC / "domains/macro_intel/repositories/macro_intel_repository.py").read_text()
    dirty_target_source = source.split("def claim_macro_projection_dirty_targets", 1)[1].split(
        "def latest_observations", 1
    )[0]

    forbidden_tokens = (
        "nullcontext",
        'getattr(conn, "transaction", None)',
        'hasattr(conn, "transaction")',
        "conn.transaction()",
        "self.conn.commit()",
    )

    assert "_macro_projection_dirty_target_transaction_context" in source
    assert "macro_projection_dirty_target_transaction_required" in source
    assert "with _macro_projection_dirty_target_transaction_context(self.conn):" in dirty_target_source
    assert [token for token in forbidden_tokens if token in dirty_target_source] == []


def test_macro_repository_write_counts_require_real_cursor_rowcount_without_defaults() -> None:
    source = (SRC / "domains/macro_intel/repositories/macro_intel_repository.py").read_text()
    forbidden_tokens = (
        'getattr(cursor, "rowcount", 0)',
        'int(getattr(cursor, "rowcount", 0) or 0)',
        'getattr(cursor, "rowcount", None)',
        "if rowcount is None",
        "return len(targets)",
        "return len(rows)",
        'return bool(dict(row or {}).get("changed", False))',
    )
    required_tokens = (
        "def _cursor_rowcount(cursor: Any) -> int:",
        "def _single_rowcount(cursor: Any) -> int:",
        "def _single_returning_changed(cursor: Any, row: Any | None) -> bool:",
        "macro_intel_repository_rowcount_required",
        "macro_intel_repository_rowcount_invalid",
        "return _single_rowcount(cursor) > 0",
        "return _cursor_rowcount(cursor)",
        "return _single_returning_changed(cursor, row)",
        "if count != (1 if row is not None else 0):",
    )

    assert [token for token in forbidden_tokens if token in source] == []
    for token in required_tokens:
        assert token in source
    assert source.count("return _single_returning_changed(cursor, row)") >= 2


def test_macro_sync_window_returning_writes_require_cursor_rowcount_match() -> None:
    source = (SRC / "domains/macro_intel/repositories/macro_intel_repository.py").read_text()
    enqueue_source = source.split("def enqueue_macro_sync_window", 1)[1].split(
        "def claim_macro_sync_window",
        1,
    )[0]
    claim_source = source.split("def claim_macro_sync_window", 1)[1].split(
        "def record_macro_sync_run",
        1,
    )[0]
    sync_window_source = enqueue_source + claim_source
    forbidden_tokens = (
        'return str(dict(row or {})["sync_window_id"])',
        "return dict(row) if row is not None else None",
        'getattr(cursor, "rowcount"',
        'getattr(cursor, "rowcount", 0)',
        "cursor.rowcount or 0",
    )

    assert [token for token in forbidden_tokens if token in sync_window_source] == []
    assert "def _required_returning_row(" in source
    assert "def _optional_returning_row(" in source
    assert "_required_returning_row(cursor, row)" in enqueue_source
    assert "_optional_returning_row(cursor, row)" in claim_source


def test_macro_view_projection_worker_uses_session_transaction_without_worker_commits() -> None:
    source = (SRC / "domains/macro_intel/runtime/macro_view_projection_worker.py").read_text()
    claimed_source = source.split("def _run_claimed_once", 1)[1].split("def _repository_session", 1)[0]

    forbidden_tokens = (
        "commit=True",
        "repos.conn.commit()",
        "conn.commit()",
        "nullcontext",
        'getattr(repos, "transaction", None)',
        "conn.transaction()",
    )

    assert "repos.transaction()" in source
    assert 'repos.require_transaction(operation="macro_view_projection")' in source
    assert "wake_payload" in source
    assert source.index("repos.transaction()") < source.index("claim_macro_projection_dirty_targets")
    assert "notify_macro_view_snapshot_updated" not in claimed_source
    assert [token for token in forbidden_tokens if token in source] == []
