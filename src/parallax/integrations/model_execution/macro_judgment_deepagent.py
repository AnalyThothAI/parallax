from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

import deepagents
from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
    wrap_model_call,
)
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool, tool

from parallax.domains.macro_intel.services.daily_macro_judgment import (
    DAILY_MACRO_JUDGMENT_SCHEMA_VERSION,
    DailyMacroJudgment,
    MacroAgentAnalysis,
    MacroEvidencePack,
    ReviewerResult,
    canonical_json_hash,
)

MACRO_ANALYST_PROMPT_VERSION = "macro_analyst_v1"
MACRO_REVIEWER_PROMPT_VERSION = "macro_reviewer_v1"
MACRO_DEEPAGENTS_WORKFLOW_VERSION = "deepagents_analyst_reviewer_v1"
MACRO_AGENT_PACK_VIEW_VERSION = "macro_agent_pack_view_v1"
MACRO_AGENT_PACK_VIEW_MAX_CHARS = 60_000
_WORKFLOW_MODEL_CALL_LIMIT = 16
_REVIEWER_MODEL_CALL_LIMIT = 5
_REVIEWER_PACK_READ_LIMIT = 1
_WORKFLOW_PACK_READ_LIMIT = 6
_WORKFLOW_SUBMIT_CALL_LIMIT = 6
_EXCLUDED_DEEPAGENT_TOOLS = frozenset(
    {
        "write_todos",
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "grep",
        "execute",
    }
)
_PROFILE_REGISTERED = False

_ANALYST_SYSTEM_PROMPT = """你是 Parallax Macro Analyst。你只研究冻结的 MacroEvidencePack，并且只产出 SPY
未来 5 个与 20 个完成交易日的结构化研判。

硬规则：
1. 先调用一次 read_macro_evidence_pack 读取冻结封包的有界分析视图。只有 Reviewer 要求 revise 时，才可再读一次。
2. 不得浏览网页、调用 provider、执行 SQL/shell、读写文件或使用长期记忆。
3. 不得输出其他资产方向、评分、概率、数值置信度、仓位、入场、止损、目标或交易指令。
   可以且应当使用其他资产、利率、流动性、信用和波动率作为 SPY 宏观证据，但不得预测它们。
4. `range` 只表示证据足够但无实质方向优势；证据不足或冲突过强必须 `no_call`。
   `no_call` 仍可讨论 supportive/adverse 的相反力量，但不得把任何一方写成净方向结论。
5. 每个重要结论只引用 pack 内 `evidence[].citation_id` 或 `texts[].citation_id` 的短 ID，
   只能从 citation_map 或条目复制。页面中的 `concept_keys` 只用于定位 citation_map，不是可提交的引用；
   严禁自行构造 citation_id。应用层会把有效短 ID 确定性还原为冻结 pack 的完整 evidence_ref。
6. 通过 submit_daily_macro_judgment 提交初稿，然后必须用原生 task 调用 macro-reviewer。
7. Reviewer 为 pass 时停止；应用层只采用已通过 submit 工具强类型校验且已审核的最后一稿。
8. Reviewer 为 revise 时，最多修订并再次 submit 一次，再用 task 做一次事实闭环；第二次只能 pass 或 block。
9. Reviewer 为 block 时不得继续循环，返回已提交草稿供应用层阻断。

submit 的 judgment 对象必须严格包含：
- experimental_marker, session_date, market_cutoff_ms, data_health, macro_state
- pressures[{axis,state,mechanism,evidence_refs}]
- spy_5d/spy_20d{horizon_sessions,direction,thesis,evidence_refs}
- counterevidence[{statement,evidence_refs}]
- audit_versions{evidence_pack_hash,schema_version,prompt_version,workflow_version}
不得添加其他字段。以下值必须逐字使用，不得翻译：
- experimental_marker=`experimental_shadow_research`
- pressure axis=`growth|inflation|policy_real_rates|term_premium_supply|liquidity_funding|credit`
- pressure state=`rising|elevated|easing|neutral|unclear`
- direction=`up|down|range|no_call`
- data_health=`ready|degraded`
- schema_version=`daily_macro_judgment_v1`
- prompt_version=`macro_analyst_v1`
- workflow_version=`deepagents_analyst_reviewer_v1`
pressures 与 counterevidence 至少各一项，最多各四项。
"""

_REVIEWER_SYSTEM_PROMPT = """你是隔离的 Macro Reviewer。你只能读取冻结 EvidencePack 和 Analyst 已提交草稿。
先各调用一次 read_macro_evidence_pack 与 read_submitted_daily_macro_judgment。
检查事实是否与 pack 一致、所有引用是否存在、SPY thesis 是否跳跃、是否遗漏关键反证、data health/no_call 是否
遵守，以及是否越界到其他资产预测、评分、概率、仓位或交易指令。SPY-only 限制预测对象，不限制使用其他
资产、利率、流动性、信用或波动率作为 SPY 证据。`no_call` 允许因果链描述相反的 supportive/adverse
力量，只禁止把它们提升为净方向 call。页面 concept key 不是有效引用；有效引用只能是 evidence/texts
条目中的 citation_id。引用、反证或措辞等可修问题应返回 `revise`；只有不可修的事实捏造、范围越界或
健康规则违例才返回 `block`。read_submitted_daily_macro_judgment 返回 submission_number、
closure_required 与 judgment；closure_required=true 时只能返回 pass 或 block，不能再次 revise。你不能静默
改写方向，只能返回严格结构化 `pass`、`revise` 或 `block` 及问题。
"""


MacroAgentRunResult = MacroAgentAnalysis


class DeepAgentGraph(Protocol):
    async def ainvoke(self, input: Mapping[str, Any]) -> Mapping[str, Any]: ...


class MacroJudgmentDeepAgent:
    def __init__(
        self,
        *,
        model: BaseChatModel,
        model_name: str,
        reviewer_model: BaseChatModel,
        reviewer_model_name: str,
        timeout_seconds: float,
        agent_factory: Callable[..., DeepAgentGraph] = create_deep_agent,
    ) -> None:
        self._model = model
        self._model_name = str(model_name)
        self._reviewer_model = reviewer_model
        self._reviewer_model_name = str(reviewer_model_name)
        self._timeout_seconds = float(timeout_seconds)
        self._agent_factory = agent_factory
        _register_least_capability_profile()

    async def analyze(self, evidence_pack: MacroEvidencePack) -> MacroAgentRunResult:
        submissions: list[dict[str, Any]] = []
        submission_validation_errors: list[list[dict[str, str]]] = []
        analyst_pack_reads: list[str] = []
        reviewer_pack_reads: list[str] = []
        citation_aliases = _agent_citation_aliases(evidence_pack)
        read_pack = _read_pack_tool(
            evidence_pack,
            pack_reads=analyst_pack_reads,
            max_reads=4,
            compact_repeats=True,
        )
        reviewer_read_pack = _read_pack_tool(
            evidence_pack,
            pack_reads=reviewer_pack_reads,
            max_reads=2,
            compact_repeats=False,
        )
        submit = _submit_draft_tool(
            submissions,
            evidence_pack=evidence_pack,
            citation_aliases=citation_aliases,
            validation_errors=submission_validation_errors,
        )
        read_draft = _read_submitted_draft_tool(
            submissions,
            citation_aliases=citation_aliases,
        )
        enforce_workflow = _workflow_contract_middleware(
            submissions=submissions,
            analyst_pack_reads=analyst_pack_reads,
        )
        enforce_reviewer_inputs = _reviewer_input_contract_middleware()
        reviewer = {
            "name": "macro-reviewer",
            "description": "Review the submitted SPY-only macro judgment against the frozen EvidencePack.",
            "system_prompt": _REVIEWER_SYSTEM_PROMPT,
            "tools": (reviewer_read_pack, read_draft),
            "model": self._reviewer_model,
            "middleware": (
                enforce_reviewer_inputs,
                ModelCallLimitMiddleware(
                    run_limit=_REVIEWER_MODEL_CALL_LIMIT,
                    exit_behavior="error",
                ),
                ToolCallLimitMiddleware(
                    tool_name="read_macro_evidence_pack",
                    run_limit=_REVIEWER_PACK_READ_LIMIT,
                    exit_behavior="error",
                ),
                ToolCallLimitMiddleware(
                    tool_name="read_submitted_daily_macro_judgment",
                    run_limit=1,
                    exit_behavior="error",
                ),
            ),
            "response_format": ToolStrategy(ReviewerResult),
        }
        graph = self._agent_factory(
            model=self._model,
            tools=(read_pack, submit),
            system_prompt=_ANALYST_SYSTEM_PROMPT,
            subagents=(reviewer,),
            middleware=(
                enforce_workflow,
                ModelCallLimitMiddleware(
                    # Parent middleware observes model calls made by both
                    # isolated Reviewer runs. Bound the whole one-revision
                    # workflow, while each Reviewer keeps its own tighter cap.
                    run_limit=_WORKFLOW_MODEL_CALL_LIMIT,
                    exit_behavior="error",
                ),
                ToolCallLimitMiddleware(
                    tool_name="read_macro_evidence_pack",
                    # Parent middleware also observes Reviewer tool calls:
                    # initial Analyst read, optional revision read, and at most
                    # two one-read Reviewer runs. Two compact Analyst repeats
                    # are the bounded correction budget.
                    run_limit=_WORKFLOW_PACK_READ_LIMIT,
                    exit_behavior="error",
                ),
                ToolCallLimitMiddleware(
                    tool_name="submit_daily_macro_judgment",
                    # Invalid payloads are not accepted submissions or
                    # revisions. Give the model a bounded schema-correction
                    # budget while the tool still accepts at most two drafts.
                    run_limit=_WORKFLOW_SUBMIT_CALL_LIMIT,
                    exit_behavior="error",
                ),
                ToolCallLimitMiddleware(
                    tool_name="task",
                    run_limit=2,
                    exit_behavior="error",
                ),
            ),
            name="macro-analyst",
        )
        try:
            result = await asyncio.wait_for(
                graph.ainvoke(
                    {
                        "messages": [
                            {
                                "role": "user",
                                "content": (
                                    f"研判 session={evidence_pack.session_date.isoformat()}，"
                                    f"cutoff_ms={evidence_pack.market_cutoff_ms}，"
                                    f"pack_hash={evidence_pack.pack_hash}。"
                                ),
                            }
                        ]
                    }
                ),
                timeout=self._timeout_seconds,
            )
        except Exception as exc:
            diagnostics = {
                "error_type": type(exc).__name__,
                "error": str(exc).replace("\n", " ")[:1_000],
                "analyst_pack_reads": analyst_pack_reads,
                "reviewer_pack_reads": reviewer_pack_reads,
                "submission_validation_errors": submission_validation_errors,
            }
            raise RuntimeError(
                "daily_macro_judgment_deepagent_failed:"
                + json.dumps(diagnostics, sort_keys=True, separators=(",", ":"))
            ) from exc
        if not submissions:
            raise RuntimeError(
                "daily_macro_judgment_submission_missing:"
                + json.dumps(submission_validation_errors, sort_keys=True, separators=(",", ":"))
            )
        reviewers, task_calls = _reviewer_results(result.get("messages"))
        _validate_bounded_workflow(
            submissions=submissions,
            reviewers=reviewers,
            task_calls=task_calls,
        )
        _require_exact_pack_reads(
            analyst_pack_reads=analyst_pack_reads,
            reviewer_pack_reads=reviewer_pack_reads,
            reviewer_runs=len(submissions),
        )
        final_reviewer = reviewers[-1]
        structured = DailyMacroJudgment.model_validate(submissions[-1])
        audit = {
            "runtime": f"deepagents=={deepagents.__version__}",
            "workflow_version": MACRO_DEEPAGENTS_WORKFLOW_VERSION,
            "analyst_prompt_version": MACRO_ANALYST_PROMPT_VERSION,
            "reviewer_prompt_version": MACRO_REVIEWER_PROMPT_VERSION,
            "schema_version": DAILY_MACRO_JUDGMENT_SCHEMA_VERSION,
            "analyst_model_name": self._model_name,
            "reviewer_model_name": self._reviewer_model_name,
            "evidence_pack_hash": evidence_pack.pack_hash,
            "analyst_submissions": len(submissions),
            "native_task_calls": task_calls,
            "reviewer_dispositions": [item.disposition for item in reviewers],
            "workflow_model_call_limit": _WORKFLOW_MODEL_CALL_LIMIT,
            "reviewer_model_call_limit": _REVIEWER_MODEL_CALL_LIMIT,
            "reviewer_pack_read_limit": _REVIEWER_PACK_READ_LIMIT,
            "workflow_pack_read_limit": _WORKFLOW_PACK_READ_LIMIT,
            "workflow_submit_call_limit": _WORKFLOW_SUBMIT_CALL_LIMIT,
            "submission_validation_failures": len(submission_validation_errors),
            "agent_pack_view_version": MACRO_AGENT_PACK_VIEW_VERSION,
            "agent_pack_view_hash": canonical_json_hash(_agent_pack_view(evidence_pack)),
            "analyst_pack_sections_read": list(analyst_pack_reads),
            "reviewer_pack_sections_read": list(reviewer_pack_reads),
            "allowed_main_tools": ["read_macro_evidence_pack", "submit_daily_macro_judgment", "task"],
            "excluded_tools": sorted(_EXCLUDED_DEEPAGENT_TOOLS),
        }
        return MacroAgentAnalysis(
            judgment=structured,
            reviewer=final_reviewer,
            audit=audit,
            model_name=self._model_name,
            prompt_version=MACRO_ANALYST_PROMPT_VERSION,
            workflow_version=MACRO_DEEPAGENTS_WORKFLOW_VERSION,
        )


def _read_pack_tool(
    evidence_pack: MacroEvidencePack,
    *,
    pack_reads: list[str],
    max_reads: int,
    compact_repeats: bool,
) -> BaseTool:
    @tool("read_macro_evidence_pack")
    def read_macro_evidence_pack() -> str:
        """Read the frozen pack's bounded page-referenced analysis view and deterministic hashes."""
        if len(pack_reads) >= max_reads:
            raise ValueError("macro_evidence_pack_read_limit_exceeded")
        if compact_repeats and pack_reads:
            pack_reads.append("repeat")
            return json.dumps(
                {
                    "already_read": True,
                    "evidence_pack_hash": evidence_pack.pack_hash,
                    "instruction": "Use the frozen pack analysis view returned by the first call.",
                },
                separators=(",", ":"),
            )
        pack_reads.append("full")
        payload = _agent_pack_view(evidence_pack)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    return read_macro_evidence_pack


def _agent_pack_view(evidence_pack: MacroEvidencePack) -> dict[str, Any]:
    payload = evidence_pack.model_dump(mode="json")
    pages = _agent_page_views(payload["pages"])
    selected_evidence = _selected_agent_evidence(payload, pages=pages)
    citation_aliases = _citation_aliases(
        [
            *(str(item["evidence_ref"]) for item in selected_evidence),
            *(str(item["evidence_ref"]) for item in payload["texts"]),
        ]
    )
    ref_to_alias = {evidence_ref: citation_id for citation_id, evidence_ref in citation_aliases.items()}
    evidence = [
        _compact_evidence_item(
            item,
            citation_id=ref_to_alias[str(item["evidence_ref"])],
        )
        for item in selected_evidence
    ]
    texts = [
        {
            "citation_id": ref_to_alias[str(item["evidence_ref"])],
            **{
                key: item[key]
                for key in (
                    "source_id",
                    "source_name",
                    "trust_tier",
                    "source_quality",
                    "published_at_ms",
                    "title",
                    "summary",
                    "canonical_url",
                )
            },
        }
        | {"body_text": item["body_text"][:1_000]}
        for item in payload["texts"]
    ]
    view: dict[str, Any] = {
        "agent_view_version": MACRO_AGENT_PACK_VIEW_VERSION,
        "evidence_pack_hash": evidence_pack.pack_hash,
        "schema_version": payload["schema_version"],
        "selection_policy_version": payload["selection_policy_version"],
        "session_date": payload["session_date"],
        "market_cutoff_ms": payload["market_cutoff_ms"],
        "sealed_at_ms": payload["sealed_at_ms"],
        "projection_version": payload["projection_version"],
        "health": payload["health"],
        "evidence_policy": "latest_for_page_referenced_concepts_v1",
        "full_pack_evidence_count": len(payload["evidence"]),
        "agent_view_evidence_count": len(evidence),
        "pages": pages,
        "citation_map": {item["concept_key"]: item["citation_id"] for item in evidence},
        "evidence": evidence,
        "texts": texts,
        "exclusion_summary": _exclusion_summary(payload["exclusions"]),
    }
    view["agent_view_hash"] = canonical_json_hash(view)
    view_chars = len(json.dumps(view, ensure_ascii=False, separators=(",", ":")))
    if view_chars > MACRO_AGENT_PACK_VIEW_MAX_CHARS:
        raise RuntimeError(f"macro_agent_pack_view_too_large:{view_chars}")
    return view


def _agent_citation_aliases(evidence_pack: MacroEvidencePack) -> dict[str, str]:
    payload = evidence_pack.model_dump(mode="json")
    pages = _agent_page_views(payload["pages"])
    evidence = _selected_agent_evidence(payload, pages=pages)
    return _citation_aliases(
        [
            *(str(item["evidence_ref"]) for item in evidence),
            *(str(item["evidence_ref"]) for item in payload["texts"]),
        ]
    )


def _selected_agent_evidence(
    payload: Mapping[str, Any],
    *,
    pages: Mapping[str, Any],
) -> list[dict[str, Any]]:
    page_concept_keys = _concept_keys_referenced_by_pages(
        pages,
        known_concepts={str(item["concept_key"]) for item in payload["evidence"]},
    )
    return [
        item
        for item in _latest_evidence_per_concept(payload["evidence"])
        if str(item["concept_key"]) in page_concept_keys
    ]


def _citation_aliases(evidence_refs: Sequence[str]) -> dict[str, str]:
    unique_refs = list(dict.fromkeys(evidence_refs))
    return {f"E{index:03d}": evidence_ref for index, evidence_ref in enumerate(unique_refs, start=1)}


def _agent_page_views(pages: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    compact = {
        page_id: {
            key: page[key]
            for key in (
                "freshness",
                "conclusion",
                "drivers",
                "confirmations",
                "contradictions",
                "unavailable_evidence",
                "upgrade_invalidation",
            )
            if key in page
        }
        for page_id, page in pages.items()
    }
    overview = pages["overview"]
    compact["overview"].update(
        {key: overview[key] for key in ("key_changes", "nearest_catalyst", "core_invalidation") if key in overview}
    )
    if "shock_summary" in overview:
        compact["overview"]["shock_summary"] = _only_keys(
            overview["shock_summary"],
            (
                "state",
                "candidate",
                "summary",
                "trend",
                "drivers",
                "confirmations",
                "contradictions",
                "evidence_refs",
            ),
        )
    compact["overview"]["risk_lanes"] = [
        _only_keys(
            lane,
            (
                "lane_id",
                "direction",
                "trend",
                "summary",
                "evidence_refs",
                "degradation_reason",
                "current_session",
                "comparison_session",
            ),
        )
        for lane in overview.get("risk_lanes", ())
    ]

    cross_asset = pages["cross_asset"]
    compact["cross_asset"]["correlations_20"] = _compact_correlations(cross_asset.get("correlations_20", ()))
    compact["cross_asset"]["correlations_60"] = _compact_correlations(cross_asset.get("correlations_60", ()))
    compact["cross_asset"]["divergences"] = cross_asset.get("divergences", ())
    compact["cross_asset"]["volatility"] = [
        _only_keys(
            item,
            (
                "concept_key",
                "role",
                "status",
                "reason",
                "value",
                "unit",
                "change",
                "change_window",
                "observed_at",
                "source_name",
                "series_key",
                "data_quality",
            ),
        )
        for item in cross_asset.get("volatility", ())
    ]
    for page_id, keys in {
        "rates_inflation": ("curve_shape", "term_premium"),
        "credit": ("credit_state", "treasury_spread_quadrant"),
    }.items():
        page = pages[page_id]
        compact[page_id].update({key: page[key] for key in keys if key in page})
    return _rename_page_reference_keys(compact)


def _compact_correlations(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        _only_keys(item, ("left", "right", "window", "status", "correlation"))
        | {"sample_count": item.get("sample", {}).get("count")}
        for item in items
        if "asset:spy" in {item.get("left"), item.get("right")}
    ]


def _only_keys(value: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    return {key: value[key] for key in keys if key in value}


def _rename_page_reference_keys(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            ("concept_keys" if key == "evidence_refs" else key): _rename_page_reference_keys(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_rename_page_reference_keys(item) for item in value]
    return value


def _compact_evidence_item(
    item: Mapping[str, Any],
    *,
    citation_id: str,
) -> dict[str, Any]:
    content = item.get("content", {})
    event_metadata = content.get("event_metadata", {})
    compact = {
        "citation_id": citation_id,
        "concept_key": item["concept_key"],
        "source_name": item["source_name"],
        "observed_at": item["observed_at"],
        "value_numeric": content.get("value_numeric"),
        "unit": content.get("unit"),
    }
    selected_metadata = {
        key: event_metadata[key]
        for key in ("text_value", "document_type", "speaker", "event_time", "reference_period")
        if key in event_metadata
    }
    if selected_metadata:
        compact["event_metadata"] = selected_metadata
    return compact


def _latest_evidence_per_concept(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        concept_key = str(item["concept_key"])
        if concept_key in seen:
            continue
        seen.add(concept_key)
        selected.append(item)
    return selected


def _concept_keys_referenced_by_pages(
    pages: Mapping[str, Any],
    *,
    known_concepts: set[str],
) -> set[str]:
    references: set[str] = set()
    pending: list[Any] = [pages]
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            if value in known_concepts:
                references.add(value)
        elif isinstance(value, Mapping):
            pending.extend(nested for key, nested in value.items() if key not in {"freshness", "unavailable_evidence"})
        elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            pending.extend(value)
    return references


def _exclusion_summary(exclusions: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for exclusion in exclusions:
        reason = str(exclusion.get("reason") or "unknown")
        summary[reason] = summary.get(reason, 0) + 1
    return dict(sorted(summary.items()))


def _submit_draft_tool(
    submissions: list[dict[str, Any]],
    *,
    evidence_pack: MacroEvidencePack,
    citation_aliases: Mapping[str, str],
    validation_errors: list[list[dict[str, str]]],
) -> BaseTool:
    @tool("submit_daily_macro_judgment")
    def submit_daily_macro_judgment(judgment: dict[str, Any]) -> str:
        """Submit one JSON object; the tool strongly validates DailyMacroJudgment before accepting it."""
        if len(submissions) >= 2:
            raise ValueError("daily_macro_judgment_revision_limit_exceeded")
        expanded_judgment, unknown_citation_ids = _translate_citation_fields(
            judgment,
            citations=citation_aliases,
        )
        if unknown_citation_ids:
            error_summary = [
                {
                    "location": "evidence_refs",
                    "type": "unknown_citation_ids",
                    "expected": ",".join(citation_aliases),
                }
            ]
            validation_errors.append(error_summary)
            return json.dumps(
                {
                    "accepted": False,
                    "validation_errors": error_summary,
                    "unknown_citation_ids": sorted(unknown_citation_ids),
                    "instruction": "Use only citation_id values present in the frozen pack view.",
                },
                separators=(",", ":"),
            )
        try:
            validated = DailyMacroJudgment.model_validate(expanded_judgment)
        except Exception as exc:
            error_summary = _validation_error_summary(exc)
            validation_errors.append(error_summary)
            return json.dumps(
                {
                    "accepted": False,
                    "validation_errors": error_summary,
                    "instruction": "Correct the exact fields and submit again.",
                },
                separators=(",", ":"),
            )
        contract_errors = _draft_contract_error_summary(
            validated,
            evidence_pack=evidence_pack,
        )
        if contract_errors:
            validation_errors.append(contract_errors)
            return json.dumps(
                {
                    "accepted": False,
                    "validation_errors": contract_errors,
                    "instruction": "Correct the exact fields and submit again.",
                },
                separators=(",", ":"),
            )
        submissions.append(validated.model_dump(mode="json"))
        return json.dumps(
            {
                "accepted": True,
                "submission_number": len(submissions),
                "instruction": "Call task with subagent_type=macro-reviewer now.",
            },
            separators=(",", ":"),
        )

    return submit_daily_macro_judgment


def _translate_citation_fields(
    value: Any,
    *,
    citations: Mapping[str, str],
) -> tuple[Any, set[str]]:
    unknown: set[str] = set()

    def translate(item: Any, *, inside_evidence_refs: bool = False) -> Any:
        if isinstance(item, Mapping):
            return {key: translate(nested, inside_evidence_refs=key == "evidence_refs") for key, nested in item.items()}
        if isinstance(item, Sequence) and not isinstance(item, str | bytes | bytearray):
            return [translate(nested, inside_evidence_refs=inside_evidence_refs) for nested in item]
        if inside_evidence_refs and isinstance(item, str):
            translated = citations.get(item)
            if translated is None:
                unknown.add(item)
                return item
            return translated
        return item

    return translate(value), unknown


def _draft_contract_error_summary(
    judgment: DailyMacroJudgment,
    *,
    evidence_pack: MacroEvidencePack,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    unknown_refs = sorted(judgment.all_evidence_refs - evidence_pack.evidence_refs)
    if unknown_refs:
        errors.append(
            {
                "location": "evidence_refs",
                "type": "unknown_evidence_refs",
                "expected": ",".join(unknown_refs[:20]),
            }
        )
    if judgment.session_date != evidence_pack.session_date:
        errors.append(
            {
                "location": "session_date",
                "type": "literal_error",
                "expected": evidence_pack.session_date.isoformat(),
            }
        )
    if judgment.market_cutoff_ms != evidence_pack.market_cutoff_ms:
        errors.append(
            {
                "location": "market_cutoff_ms",
                "type": "literal_error",
                "expected": str(evidence_pack.market_cutoff_ms),
            }
        )
    if judgment.audit_versions.evidence_pack_hash != evidence_pack.pack_hash:
        errors.append(
            {
                "location": "audit_versions.evidence_pack_hash",
                "type": "literal_error",
                "expected": evidence_pack.pack_hash,
            }
        )
    expected_health = "degraded" if evidence_pack.health.status.value == "degraded" else "ready"
    if judgment.data_health != expected_health:
        errors.append(
            {
                "location": "data_health",
                "type": "literal_error",
                "expected": expected_health,
            }
        )
    for horizon in evidence_pack.health.no_call_horizons:
        call = judgment.spy_5d if horizon == 5 else judgment.spy_20d
        if call.direction.value != "no_call":
            errors.append(
                {
                    "location": f"spy_{horizon}d.direction",
                    "type": "data_health_requires_no_call",
                    "expected": "no_call",
                }
            )
    return errors


def _validation_error_summary(exc: Exception) -> list[dict[str, str]]:
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return [{"location": "judgment", "type": type(exc).__name__}]
    summary: list[dict[str, str]] = []
    for error in errors(include_url=False, include_input=False)[:20]:
        item = {
            "location": ".".join(str(part) for part in error.get("loc", ("judgment",))),
            "type": str(error.get("type") or "validation_error"),
        }
        expected = error.get("ctx", {}).get("expected")
        if expected is not None:
            item["expected"] = str(expected)
        summary.append(item)
    return summary


def _read_submitted_draft_tool(
    submissions: list[dict[str, Any]],
    *,
    citation_aliases: Mapping[str, str],
) -> BaseTool:
    @tool("read_submitted_daily_macro_judgment")
    def read_submitted_daily_macro_judgment() -> str:
        """Read the latest Analyst draft submitted for this isolated review."""
        if not submissions:
            raise ValueError("daily_macro_judgment_submission_missing")
        reviewer_judgment, unknown_refs = _translate_citation_fields(
            submissions[-1],
            citations={evidence_ref: citation_id for citation_id, evidence_ref in citation_aliases.items()},
        )
        if unknown_refs:
            raise RuntimeError("daily_macro_judgment_internal_citation_translation_failed")
        return json.dumps(
            {
                "submission_number": len(submissions),
                "closure_required": len(submissions) == 2,
                "judgment": reviewer_judgment,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    return read_submitted_daily_macro_judgment


def _workflow_contract_middleware(
    *,
    submissions: Sequence[Mapping[str, Any]],
    analyst_pack_reads: Sequence[str],
) -> Any:
    @wrap_model_call
    async def enforce_macro_workflow(request: Any, handler: Callable[[Any], Any]) -> Any:
        reviewers, _ = _reviewer_results(request.messages)
        if not analyst_pack_reads:
            tool_name = "read_macro_evidence_pack"
        elif not submissions:
            tool_name = "submit_daily_macro_judgment"
        elif len(reviewers) < len(submissions):
            tool_name = "task"
        elif reviewers[-1].disposition == "revise" and len(submissions) == 1:
            tool_name = "submit_daily_macro_judgment"
        else:
            return await handler(request.override(tool_choice="none"))
        return await handler(request.override(tool_choice=_named_tool_choice(tool_name)))

    return enforce_macro_workflow


def _reviewer_input_contract_middleware() -> Any:
    @wrap_model_call
    async def enforce_reviewer_inputs(request: Any, handler: Callable[[Any], Any]) -> Any:
        tool_names = _completed_tool_names(request.messages)
        if "read_macro_evidence_pack" not in tool_names:
            tool_name = "read_macro_evidence_pack"
        elif "read_submitted_daily_macro_judgment" not in tool_names:
            tool_name = "read_submitted_daily_macro_judgment"
        else:
            return await handler(request)
        return await handler(request.override(tool_choice=_named_tool_choice(tool_name)))

    return enforce_reviewer_inputs


def _completed_tool_names(messages: Any) -> set[str]:
    if not isinstance(messages, Sequence) or isinstance(messages, str | bytes | bytearray):
        return set()
    return {str(message.name or "") for message in messages if isinstance(message, ToolMessage) and message.name}


def _named_tool_choice(tool_name: str) -> dict[str, Any]:
    return {"type": "function", "function": {"name": tool_name}}


def _reviewer_results(messages: Any) -> tuple[list[ReviewerResult], int]:
    if not isinstance(messages, Sequence) or isinstance(messages, str | bytes | bytearray):
        raise RuntimeError("daily_macro_judgment_messages_missing")
    task_call_ids: list[str] = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        task_call_ids.extend(
            str(call.get("id") or "") for call in message.tool_calls if str(call.get("name") or "") == "task"
        )
    task_ids = {value for value in task_call_ids if value}
    reviewers: list[ReviewerResult] = []
    for message in messages:
        if not isinstance(message, ToolMessage) or str(message.tool_call_id or "") not in task_ids:
            continue
        content = message.content
        if not isinstance(content, str):
            continue
        try:
            payload = json.loads(content)
            reviewers.append(ReviewerResult.model_validate(payload))
        except (json.JSONDecodeError, ValueError):
            continue
    return reviewers, len(task_call_ids)


def _validate_bounded_workflow(
    *,
    submissions: Sequence[Mapping[str, Any]],
    reviewers: Sequence[ReviewerResult],
    task_calls: int,
) -> None:
    if len(submissions) not in {1, 2}:
        raise RuntimeError(f"daily_macro_judgment_submission_count_invalid:{len(submissions)}")
    if task_calls != len(submissions) or len(reviewers) != len(submissions):
        raise RuntimeError(
            "daily_macro_judgment_native_review_count_invalid:"
            f"submissions={len(submissions)}:task_calls={task_calls}:reviews={len(reviewers)}"
        )
    first = reviewers[0].disposition
    if len(submissions) == 1 and first not in {"pass", "block"}:
        raise RuntimeError("daily_macro_judgment_revision_not_closed")
    if len(submissions) == 2:
        if first != "revise":
            raise RuntimeError("daily_macro_judgment_unrequested_second_submission")
        if reviewers[1].disposition not in {"pass", "block"}:
            raise RuntimeError("daily_macro_judgment_second_review_must_close")


def _require_exact_pack_reads(
    *,
    analyst_pack_reads: Sequence[str],
    reviewer_pack_reads: Sequence[str],
    reviewer_runs: int,
) -> None:
    if not 1 <= len(analyst_pack_reads) <= 4 or analyst_pack_reads[0] != "full":
        raise RuntimeError(
            "daily_macro_judgment_analyst_pack_reads_invalid:"
            + json.dumps(list(analyst_pack_reads), separators=(",", ":"))
        )
    if any(item != "repeat" for item in analyst_pack_reads[1:]):
        raise RuntimeError(
            "daily_macro_judgment_analyst_pack_reads_invalid:"
            + json.dumps(list(analyst_pack_reads), separators=(",", ":"))
        )
    if reviewer_pack_reads != ["full"] * reviewer_runs:
        raise RuntimeError(
            "daily_macro_judgment_reviewer_pack_reads_invalid:"
            + json.dumps(list(reviewer_pack_reads), separators=(",", ":"))
        )


def _register_least_capability_profile() -> None:
    global _PROFILE_REGISTERED  # noqa: PLW0603
    if _PROFILE_REGISTERED:
        return
    register_harness_profile(
        "litellm",
        HarnessProfile(
            excluded_tools=_EXCLUDED_DEEPAGENT_TOOLS,
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        ),
    )
    _PROFILE_REGISTERED = True


__all__ = [
    "MACRO_AGENT_PACK_VIEW_MAX_CHARS",
    "MACRO_AGENT_PACK_VIEW_VERSION",
    "MACRO_ANALYST_PROMPT_VERSION",
    "MACRO_DEEPAGENTS_WORKFLOW_VERSION",
    "MACRO_REVIEWER_PROMPT_VERSION",
    "MacroAgentRunResult",
    "MacroJudgmentDeepAgent",
]
