from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from gmgn_twitter_intel.domains.macro_intel._constants import MACRO_CONCEPT_METADATA


def build_macro_data_gaps(raw_codes: Sequence[str]) -> list[dict[str, Any]]:
    return [_gap_payload(code) for code in _unique(raw_codes)]


def _gap_payload(raw_code: str) -> dict[str, Any]:
    concept_key = _gap_concept_key(raw_code)
    metadata = MACRO_CONCEPT_METADATA.get(concept_key or "", {})
    public_code = _public_gap_code(raw_code)
    return {
        "code": public_code,
        "label": _gap_label(raw_code, concept_label=_concept_label(metadata)),
        "severity": _gap_severity(raw_code),
        "score_participation": False,
        "remediation_hint": _remediation_hint(public_code),
    }


def _gap_concept_key(raw_code: str) -> str | None:
    if raw_code.startswith("missing:"):
        return raw_code.split(":", 1)[1].split("|", 1)[0]
    return None


def _concept_label(metadata: Mapping[str, Any]) -> str:
    return str(metadata.get("short_label") or metadata.get("label") or "")


def _public_gap_code(raw_code: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in raw_code).strip("_")


def _gap_label(raw_code: str, *, concept_label: str) -> str:
    if raw_code.startswith("missing:"):
        return f"缺少当前数据：{concept_label or '未命名指标'}"
    if suffix := _suffix(raw_code, colon_prefix="insufficient_history:", underscore_prefix="insufficient_history_"):
        if suffix.endswith("d"):
            return f"历史样本不足：无法计算 {suffix[:-1]} 日变化"
        if suffix == "zscore":
            return "历史样本不足：无法计算 z-score"
        if suffix == "percentile":
            return "历史样本不足：无法计算分位数"
    if count := _suffix(raw_code, colon_prefix="non_numeric_values:", underscore_prefix="non_numeric_values_"):
        return f"存在非数值观测：{count} 个点已排除"
    if quality := _suffix(raw_code, colon_prefix="data_quality:", underscore_prefix="data_quality_"):
        return f"数据质量异常：{quality}"
    if days := _suffix(raw_code, colon_prefix="stale_latest:", underscore_prefix="stale_latest_"):
        return f"最新观测已过期：{days.removesuffix('d')} 天未更新"
    if raw_code == "positioning_data_gap":
        return "缺少持仓数据：无法确认仓位拥挤度"
    if raw_code == "missing_numeric_history":
        return "缺少可用数值历史"
    if raw_code == "missing_latest_observed_at":
        return "缺少最新观测日期"
    if label := _CATALOG_GAP_LABELS.get(_public_gap_code(raw_code)):
        return label
    return "数据缺口：待补齐数据源"


def _remediation_hint(public_code: str) -> str:
    if public_code.startswith("insufficient_history"):
        return "回填历史后重新生成宏观投影。"
    if public_code.startswith("missing"):
        return "检查对应 provider 导入与最新观测。"
    if public_code.startswith("cex_board"):
        return "启用或修复 cex_oi_radar_board worker。"
    return _CATALOG_GAP_REMEDIATION.get(public_code, "补齐数据源后重新投影。")


def _suffix(raw_code: str, *, colon_prefix: str, underscore_prefix: str) -> str:
    if raw_code.startswith(colon_prefix):
        return raw_code.removeprefix(colon_prefix)
    if raw_code.startswith(underscore_prefix):
        return raw_code.removeprefix(underscore_prefix)
    return ""


def _gap_severity(raw_code: str) -> str:
    if raw_code.startswith("missing:") or raw_code.startswith("stale_latest"):
        return "error"
    if raw_code == "missing_numeric_history":
        return "error"
    return "warning"


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


_CATALOG_GAP_LABELS = {
    "basis_missing": "缺少基差信号：无法确认期现结构",
    "cex_board_empty": "CEX 合约板为空：暂无可用杠杆排行",
    "cex_board_missing": "缺少 CEX 合约板：无法确认杠杆状态",
    "crypto_options_missing": "缺少加密期权数据：无法确认波动率定价",
    "equity_breadth_missing": "缺少美股广度：无法确认上涨参与度",
    "equity_options_gex_missing": "缺少美股期权 GEX：无法确认经销商仓位压力",
    "etf_flows_missing": "缺少 ETF 资金流：无法确认现货资金需求",
    "fed_calendar_missing": "缺少美联储日历：无法确认政策事件窗口",
    "fed_speeches_missing": "缺少美联储讲话：无法确认政策沟通风险",
    "fed_statement_text_missing": "缺少 FOMC 文本：无法解析政策措辞变化",
    "move_index_missing": "缺少 MOVE 指数：无法确认债券波动率压力",
    "options_iv_rv_missing": "缺少 IV/RV：无法确认波动率风险溢价",
    "vix_term_structure_missing": "缺少 VIX 期限结构：无法确认波动率曲线压力",
}

_CATALOG_GAP_REMEDIATION = {
    "basis_missing": "接入期现基差数据后重建衍生品页面。",
    "crypto_options_missing": "接入加密期权 IV、偏度或期限结构后重建页面。",
    "equity_breadth_missing": "接入美股广度数据后重建资产页面。",
    "equity_options_gex_missing": "接入美股期权 GEX 数据后重建页面。",
    "etf_flows_missing": "接入 ETF flow 数据后重建加密衍生品页面。",
    "fed_calendar_missing": "接入 FOMC 日历后重建美联储页面。",
    "fed_speeches_missing": "接入美联储讲话数据后重建美联储页面。",
    "fed_statement_text_missing": "接入 FOMC 声明文本后重建美联储页面。",
    "move_index_missing": "接入 MOVE 指数后重建债券或利率页面。",
    "options_iv_rv_missing": "接入 IV/RV 数据后重建波动率页面。",
    "vix_term_structure_missing": "接入 VIX 期限结构后重建波动率页面。",
}


__all__ = ["build_macro_data_gaps"]
