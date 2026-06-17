from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.macro_intel._constants import MACRO_CONCEPT_METADATA


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
        if concept_label:
            return f"缺少当前数据：{concept_label}"
        return f"数据质量缺口：{_public_gap_code(raw_code)}"
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
    public_code = _public_gap_code(raw_code)
    if label := _NAMED_GAP_LABELS.get(public_code):
        return label
    if subject := _missing_subject(public_code):
        return _missing_label(subject)
    return f"数据质量缺口：{public_code}"


def _remediation_hint(public_code: str) -> str:
    if public_code.startswith("insufficient_history"):
        return "回填历史后重新生成宏观投影。"
    if public_code.startswith("missing"):
        return "检查对应 provider 导入与最新观测。"
    return "补齐数据源后重新投影。"


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


def _missing_subject(public_code: str) -> str:
    if not public_code.endswith("_missing"):
        return ""
    body = public_code.removesuffix("_missing")
    return _NAMED_GAP_SUBJECTS.get(body, _humanize_gap_code(body))


def _missing_label(subject: str) -> str:
    separator = " " if subject and subject[-1].isascii() and subject[-1].isalnum() else ""
    return f"{subject}{separator}缺失"


def _humanize_gap_code(value: str) -> str:
    return " ".join(part.upper() if len(part) <= 4 else part for part in value.split("_") if part)


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


_NAMED_GAP_LABELS: dict[str, str] = {
    "basis_missing": "基差缺失",
    "move_index_missing": "MOVE 指数缺失",
    "options_iv_rv_missing": "期权 IV/RV 缺失",
    "vix_term_structure_missing": "VIX 期限结构缺失",
}

_NAMED_GAP_SUBJECTS: dict[str, str] = {
    "average_hourly_earnings": "平均时薪",
    "crypto_options": "加密期权",
    "equity_breadth": "股票广度",
    "equity_options_gex": "股票期权 GEX",
    "etf_flows": "ETF 资金流",
    "fed_calendar": "Fed 日历",
    "fed_speeches": "Fed 讲话",
    "fed_statement_text": "Fed 声明文本",
    "jolts": "JOLTS",
    "loan_quality": "贷款质量",
    "personal_spending": "个人消费支出",
    "sloos": "SLOOS",
}


__all__ = ["build_macro_data_gaps"]
