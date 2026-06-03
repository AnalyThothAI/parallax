from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from parallax.domains.news_intel.services.news_item_research_executor import (
    NEWS_RESEARCH_EXECUTOR_HARD_TOTAL_CHARS,
    NEWS_RESEARCH_EXECUTOR_MAX_TOOL_CALLS,
    NEWS_RESEARCH_EXECUTOR_TARGET_TOTAL_CHARS,
)
from parallax.domains.news_intel.services.news_item_research_tools import build_news_research_tool_registry
from parallax.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_RESEARCH_POLICY_VERSION,
    NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION,
    NewsContextTargetRef,
    NewsItemBriefBasePacket,
    NewsItemResearchBudget,
    NewsItemResearchPlan,
    NewsItemResearchTodo,
    NewsItemResearchToolCall,
)

ARCHIVE_WINDOW_HOURS = 168
ARCHIVE_LIMIT = 8
TARGET_CONTEXT_WINDOW_HOURS = 72
TARGET_CONTEXT_LIMIT = 12
FACT_CONTEXT_LIMIT = 20
OBSERVATION_HISTORY_LIMIT = 12
SOURCE_QUALITY_CLASSES = frozenset({"regulation", "security", "etf", "exchange_listing", "protocol_governance"})
ARCHIVE_WORTHY_CLASSES = SOURCE_QUALITY_CLASSES | frozenset(
    {
        "listing",
        "token_listing",
        "protocol",
        "macro",
        "stablecoin",
        "hack",
        "funding",
        "partnership",
    }
)


class NewsItemResearchDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    needs_research: bool
    research_plan: NewsItemResearchPlan
    reasons: list[str] = Field(default_factory=list, max_length=20)


def classify_news_item_research_policy(base_packet: NewsItemBriefBasePacket) -> NewsItemResearchDecision:
    reasons: list[str] = []
    calls: list[NewsItemResearchToolCall] = []
    todos: list[NewsItemResearchTodo] = []
    registry = build_news_research_tool_registry()

    has_facts = bool(base_packet.fact_lanes)
    fact_truncated = (
        base_packet.base_budget_report.original_fact_count > base_packet.base_budget_report.kept_fact_count
        or "fact_lanes_budget" in base_packet.base_budget_report.truncation_reasons
    )
    has_targets = bool(base_packet.allowed_context_targets)
    content_class = (base_packet.content_class or "").strip().lower()
    has_provider_signal = base_packet.provider_signal_evidence is not None

    if has_facts:
        reasons.append("fact_lanes_present")
    if fact_truncated:
        reasons.append("fact_lanes_truncated")
    if has_targets:
        reasons.append("resolved_allowed_targets")
    if has_provider_signal:
        reasons.append("provider_signal_present")
    if content_class and content_class != "low_signal":
        reasons.append(f"content_class:{content_class}")

    context_worthy = has_facts or fact_truncated or has_targets or _archive_worthy(content_class)
    if content_class == "low_signal" and not has_facts and not fact_truncated and not has_targets:
        context_worthy = False

    if not context_worthy and not has_provider_signal:
        return _skip_decision(reasons=reasons, skip_reason_zh="缺少事实、供应商信号和已解析标的，跳过本地补充检索。")
    if not context_worthy:
        return _skip_decision(reasons=reasons, skip_reason_zh="该条目为低信息增量新闻，暂无可用本地上下文工具。")

    if has_facts or fact_truncated:
        _append_call(
            calls,
            tool_name="get_fact_context",
            input_payload={"include_rejected": fact_truncated, "limit": FACT_CONTEXT_LIMIT},
            purpose_zh="补充当前新闻条目的事实候选和验证状态，避免把注意力事实误写为已证实事实。",
            expected_evidence=["fact_candidate", "validation_status"],
            registry=registry,
        )
        todos.append(_todo("todo-facts", "核对事实候选、验证状态和被截断事实是否改变结论。"))

    if has_targets:
        target_refs = _target_refs(base_packet.allowed_context_targets)
        symbol_fallbacks = _symbol_fallbacks(base_packet)
        _append_call(
            calls,
            tool_name="get_target_news_context",
            input_payload={
                "target_refs": target_refs,
                "symbol_fallbacks": symbol_fallbacks,
                "window_hours": TARGET_CONTEXT_WINDOW_HOURS,
                "limit": TARGET_CONTEXT_LIMIT,
            },
            purpose_zh="只围绕输入允许的已解析标的拉取近期相关新闻上下文。",
            expected_evidence=["exact_target", "known_symbol"],
            registry=registry,
        )
        todos.append(_todo("todo-targets", "检查已解析标的近期是否已有重复、更新或确认新闻。"))

    if has_facts or fact_truncated or has_targets or _archive_worthy(content_class):
        _append_call(
            calls,
            tool_name="search_news_archive",
            input_payload={
                "query_terms": _query_terms(base_packet),
                "symbols": _symbol_fallbacks(base_packet, max_items=5),
                "match_modes": ["title", "token", "fact", "source_title"],
                "window_hours": ARCHIVE_WINDOW_HOURS,
                "limit": ARCHIVE_LIMIT,
            },
            purpose_zh="在 168 小时窗口内检索同类新闻，判断新发、重复、更新或单源状态。",
            expected_evidence=["similar_news", "term_match", "symbol_match"],
            registry=registry,
        )
        todos.append(_todo("todo-archive", "对比本地历史新闻，确认新颖性和重复风险。"))

    _append_call(
        calls,
        tool_name="get_observation_history",
        input_payload={"limit": OBSERVATION_HISTORY_LIMIT},
        purpose_zh="查看当前新闻条目的观测历史和来源聚合线索。",
        expected_evidence=["observation_history", "same_source"],
        registry=registry,
    )
    todos.append(_todo("todo-observations", "检查观测历史、来源聚合和同域重复线索。"))

    if (
        has_provider_signal or content_class in SOURCE_QUALITY_CLASSES
    ) and len(calls) < NEWS_RESEARCH_EXECUTOR_MAX_TOOL_CALLS:
        _append_call(
            calls,
            tool_name="get_source_quality",
            input_payload={},
            purpose_zh="补充来源质量和健康状态，仅作为来源可靠性辅助信号。",
            expected_evidence=["source_quality", "trust_tier"],
            registry=registry,
        )
        todos.append(_todo("todo-source", "把来源质量作为辅助信号，不把同域聚合误判为独立确认。"))

    plan = NewsItemResearchPlan(
        status="ready" if calls else "skip",
        research_todos=todos[:12],
        tool_calls=_with_stable_ids(calls[:NEWS_RESEARCH_EXECUTOR_MAX_TOOL_CALLS]),
        budget=NewsItemResearchBudget(
            max_tool_calls=NEWS_RESEARCH_EXECUTOR_MAX_TOOL_CALLS,
            max_total_chars=NEWS_RESEARCH_EXECUTOR_TARGET_TOTAL_CHARS,
            hard_max_total_chars=NEWS_RESEARCH_EXECUTOR_HARD_TOTAL_CHARS,
            max_rows_per_tool=25,
        ),
        policy_notes_zh="; ".join(_policy_notes(reasons))[:1000],
        skip_reason_zh="" if calls else "没有选择本地研究工具。",
        evidence_refs=list(base_packet.evidence_refs[:40]),
        policy_version=NEWS_ITEM_RESEARCH_POLICY_VERSION,
        tool_catalog_version=NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION,
    )
    return NewsItemResearchDecision(needs_research=bool(plan.tool_calls), research_plan=plan, reasons=reasons)


def _skip_decision(*, reasons: list[str], skip_reason_zh: str) -> NewsItemResearchDecision:
    plan = NewsItemResearchPlan(
        status="skip",
        research_todos=[],
        tool_calls=[],
        budget=NewsItemResearchBudget(
            max_tool_calls=0,
            max_total_chars=0,
            hard_max_total_chars=0,
            max_rows_per_tool=0,
        ),
        policy_notes_zh="; ".join(_policy_notes(reasons))[:1000],
        skip_reason_zh=skip_reason_zh,
        evidence_refs=[],
        policy_version=NEWS_ITEM_RESEARCH_POLICY_VERSION,
        tool_catalog_version=NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION,
    )
    return NewsItemResearchDecision(needs_research=False, research_plan=plan, reasons=reasons)


def _append_call(
    calls: list[NewsItemResearchToolCall],
    *,
    tool_name: str,
    input_payload: dict[str, Any],
    purpose_zh: str,
    expected_evidence: list[str],
    registry: Mapping[str, Any] | dict[str, Any],
) -> None:
    if len(calls) >= NEWS_RESEARCH_EXECUTOR_MAX_TOOL_CALLS or tool_name not in registry:
        return
    calls.append(
        NewsItemResearchToolCall(
            tool_call_id=f"call-{len(calls) + 1:03d}",
            tool_name=tool_name,
            input=input_payload,
            purpose_zh=purpose_zh,
            expected_evidence=expected_evidence,
        )
    )


def _with_stable_ids(calls: list[NewsItemResearchToolCall]) -> list[NewsItemResearchToolCall]:
    return [call.model_copy(update={"tool_call_id": f"call-{index:03d}"}) for index, call in enumerate(calls, 1)]


def _todo(todo_id: str, content_zh: str) -> NewsItemResearchTodo:
    return NewsItemResearchTodo(todo_id=todo_id, content_zh=content_zh, status="pending")


def _target_refs(targets: list[NewsContextTargetRef]) -> list[dict[str, str]]:
    return [{"target_type": target.target_type, "target_id": target.target_id} for target in targets[:5]]


def _symbol_fallbacks(base_packet: NewsItemBriefBasePacket, *, max_items: int = 3) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for lane in base_packet.token_lanes:
        symbol = (lane.display_symbol or lane.observed_symbol or "").strip().upper()[:32]
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
        if len(symbols) >= max_items:
            break
    return symbols


def _query_terms(base_packet: NewsItemBriefBasePacket) -> list[str]:
    terms: list[str] = []
    if base_packet.content_class:
        terms.append(base_packet.content_class.replace("_", " "))
    title_terms = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,24}", base_packet.news_item.title or "")
    terms.extend(title_terms[:3])
    for fact in base_packet.fact_lanes[:2]:
        terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,24}", fact.claim or "")[:2])
    return _stable_unique([term[:64] for term in terms if term])[:5]


def _archive_worthy(content_class: str) -> bool:
    if not content_class:
        return False
    return any(marker in content_class for marker in ARCHIVE_WORTHY_CLASSES)


def _policy_notes(reasons: list[str]) -> list[str]:
    if not reasons:
        return ["未命中特定研究触发原因"]
    return [f"研究触发：{reason}" for reason in reasons]


def _stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


__all__ = ["NewsItemResearchDecision", "classify_news_item_research_policy"]
