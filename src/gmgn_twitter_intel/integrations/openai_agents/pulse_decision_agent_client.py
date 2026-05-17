from __future__ import annotations

import inspect
import json
import time
from dataclasses import dataclass
from types import GetSetDescriptorType, MemberDescriptorType
from typing import Any, cast

from agents import (
    Agent,
    RunConfig,
    Runner,
    ToolCallItem,
)
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel

from gmgn_twitter_intel.domains.pulse_lab.providers import (
    DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT,
    PulseAgentRuntimeContract,
    PulseAgentToolRuntimeFactory,
    PulseDecisionRuntime,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    DecisionRoute,
    FinalDecision,
    InvestigationReport,
    PulseDecisionPayload,
    PulseStageFailure,
    StageName,
    StageRunAudit,
    StageStatus,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_model_settings import (
    default_agent_model_settings,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_output_schema import StrictJsonOutputSchema
from gmgn_twitter_intel.integrations.openai_agents.instructor_safety_net import (
    InstructorSafetyNet,
    SafetyNetExhausted,
)
from gmgn_twitter_intel.integrations.openai_agents.tools import (
    PulseToolContext,
    get_official_token_profile,
    get_target_price_action,
    get_target_recent_tweets,
)

WORKFLOW_NAME = "gmgn-twitter-intel.pulse_decision"
AGENT_NAME = "PulseDecisionDesk"


@dataclass(frozen=True)
class PulseDecisionAgentResult:
    final_decision: FinalDecision
    run_audit: dict[str, Any]
    stage_audits: tuple[StageRunAudit, ...]


class OpenAIAgentsPulseDecisionClient:
    """Two-stage Investigator → DecisionMaker pulse decision client.

    Stage 1 (Investigator): multi-turn Agent run with 3 investigator tools
    (`get_target_recent_tweets`, `get_target_price_action`,
    `get_official_token_profile`); produces an :class:`InvestigationReport`.
    Each tool call increments ``PulseToolContext.tool_calls_count`` and the
    SDK raises :class:`ToolBudgetExceeded` once
    ``investigator_max_tool_calls`` (per-route) is hit; the worker treats that
    as a stage failure.

    Stage 2 (DecisionMaker): single-turn Agent run, optionally exposing the
    tweets tool as a fallback when ``decision_maker_enable_fallback_tool`` is
    True (OQ-2); produces a :class:`FinalDecision`.

    The provider Protocol contract (``run_decision_pipeline`` / ``request_audit``
    signatures) is unchanged from the previous Analyst/Critic/Judge pipeline so
    wiring + read-models keep compiling. The runtime manifest carries
    ``stages: ["investigator", "decision_maker"]`` which bumps
    ``runtime_hash`` and isolates v2 eval cases from v1.
    """

    provider = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        llm_gateway: Any,
        tool_runtime_factory: PulseAgentToolRuntimeFactory,
        decision_runtime: PulseDecisionRuntime,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 20.0,
        runner: Any | None = None,
        safety_net: InstructorSafetyNet | None = None,
        trace_enabled: bool = True,
        trace_include_sensitive_data: bool = False,
        workflow_name: str = WORKFLOW_NAME,
        investigator_max_tool_calls_by_route: dict[str, int] | None = None,
        decision_maker_enable_fallback_tool: bool = True,
        decision_maker_max_turns: int = 3,
        investigator_max_turns: int = 5,
    ) -> None:
        self.api_key = api_key
        self.model = str(model or "").strip()
        if not self.model:
            raise ValueError("llm.pulse_agent_model or llm.model is required")
        if llm_gateway is None:
            raise ValueError("llm_gateway is required")
        if tool_runtime_factory is None:
            raise ValueError("tool_runtime_factory is required for Investigator tools")
        if decision_runtime is None:
            raise ValueError("decision_runtime is required")
        self._llm_gateway = llm_gateway
        self._tool_runtime_factory = tool_runtime_factory
        self._decision_runtime = decision_runtime
        self.base_url = _api_base(base_url)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.workflow_name = str(workflow_name or "").strip() or WORKFLOW_NAME
        self.trace_enabled = bool(trace_enabled and getattr(self._llm_gateway, "trace_export_enabled", False))
        self.trace_include_sensitive_data = bool(trace_include_sensitive_data)
        self._runner = runner or Runner
        self._safety_net = safety_net
        self._model = None if runner is not None else self._build_model()
        self._investigator_max_tool_calls_by_route = dict(investigator_max_tool_calls_by_route or {})
        self._decision_maker_enable_fallback_tool = bool(decision_maker_enable_fallback_tool)
        self._decision_maker_max_turns = max(1, int(decision_maker_max_turns))
        self._investigator_max_turns = max(1, int(investigator_max_turns))

    @property
    def artifact_version_hash(self) -> str:
        return f"artifact:{self.model}"

    @property
    def runtime_contract(self) -> PulseAgentRuntimeContract:
        decision_tools = ("get_target_recent_tweets",) if self._decision_maker_enable_fallback_tool else ()
        route_budgets = (
            dict(self._investigator_max_tool_calls_by_route)
            or dict(DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT.route_tool_budgets)
        )
        return PulseAgentRuntimeContract(
            stage_names=("investigator", "decision_maker"),
            max_turns_per_stage={
                "investigator": self._investigator_max_turns,
                "decision_maker": self._decision_maker_max_turns,
            },
            tool_names_by_stage={
                "investigator": (
                    "get_target_recent_tweets",
                    "get_target_price_action",
                    "get_official_token_profile",
                ),
                "decision_maker": decision_tools,
            },
            route_tool_budgets=route_budgets,
            decision_maker_fallback_tool_enabled=self._decision_maker_enable_fallback_tool,
            safety_net_enabled=self._safety_net is not None,
        )

    def request_audit(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        return self._decision_runtime.request_audit(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=completeness,
            runtime_manifest=runtime_manifest,
            model=self.model,
            artifact_version_hash=self.artifact_version_hash,
            workflow_name=self.workflow_name,
            agent_name=AGENT_NAME,
        )

    async def run_decision_pipeline(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
    ) -> PulseDecisionAgentResult:
        audit = self._decision_runtime.request_audit(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=completeness,
            runtime_manifest=runtime_manifest,
            model=self.model,
            artifact_version_hash=self.artifact_version_hash,
            workflow_name=self.workflow_name,
            agent_name=AGENT_NAME,
        )
        tool_budget = self._decision_runtime.tool_budget_for_route(
            route=route,
            budgets=self._investigator_max_tool_calls_by_route,
        )
        tool_runtime = self._tool_runtime_factory(investigator_max_tool_calls=tool_budget)
        tool_ctx = PulseToolContext(
            tool_runtime=tool_runtime,
        )

        # Stage 1: Investigator (multi-turn, with tools).
        investigator_step = await self._run_investigator(
            route=route,
            context=context,
            completeness=completeness,
            run_id=run_id,
            audit=audit,
            tool_ctx=tool_ctx,
        )
        stage_audits: list[StageRunAudit] = [investigator_step]
        if investigator_step.status != "ok":
            raise PulseStageFailure(
                f"investigator stage {investigator_step.status}: {investigator_step.error}",
                audits=tuple(stage_audits),
            )
        investigation = InvestigationReport.model_validate(investigator_step.response_json)

        # Hallucination guard: bull/bear supporting_event_ids must come from
        # tool contributions or upstream context evidence.
        try:
            self._decision_runtime.validate_supporting_ids(
                investigation,
                tool_runtime=tool_runtime,
                context=context,
            )
        except ValueError as exc:
            failed_step = self._decision_runtime.mark_step_failed(investigator_step, error=str(exc))
            stage_audits[-1] = failed_step
            raise PulseStageFailure(
                f"investigator stage failed: {exc}",
                audits=tuple(stage_audits),
            ) from exc

        # Stage 2: DecisionMaker (single/few turn, optional fallback tool).
        decision_step = await self._run_decision_maker(
            route=route,
            context=context,
            completeness=completeness,
            investigation=investigation,
            run_id=run_id,
            audit=audit,
            tool_ctx=tool_ctx,
        )
        stage_audits.append(decision_step)
        if decision_step.status != "ok":
            raise PulseStageFailure(
                f"decision_maker stage {decision_step.status}: {decision_step.error}",
                audits=tuple(stage_audits),
            )
        final = FinalDecision.model_validate(decision_step.response_json)
        try:
            self._decision_runtime.validate_final_evidence_ids(
                final,
                investigation=investigation,
                tool_runtime=tool_runtime,
                context=context,
            )
        except ValueError as exc:
            failed_step = self._decision_runtime.mark_step_failed(decision_step, error=str(exc))
            stage_audits[-1] = failed_step
            raise PulseStageFailure(
                f"decision_maker stage failed: {exc}",
                audits=tuple(stage_audits),
            ) from exc

        # Evidence URL enrichment (best-effort JOIN against events).
        final = self._decision_runtime.enrich_evidence_urls(final)

        PulseDecisionPayload(final_decision=final, stage_audits=tuple(stage_audits))
        audit = self._decision_runtime.with_output_hash(audit, final=final)
        return PulseDecisionAgentResult(
            final_decision=final,
            run_audit=audit,
            stage_audits=tuple(stage_audits),
        )

    async def _run_investigator(
        self,
        *,
        route: DecisionRoute,
        context: dict[str, Any],
        completeness: dict[str, Any],
        run_id: str,
        audit: dict[str, Any],
        tool_ctx: PulseToolContext,
    ) -> StageRunAudit:
        spec = self._decision_runtime.investigator_stage_spec(
            route=route,
            context=context,
            completeness=completeness,
        )
        agent = Agent[PulseToolContext](
            name=f"PulseInvestigator{_route_label(route)}",
            instructions=spec.prompt_text,
            output_type=StrictJsonOutputSchema(InvestigationReport),
            tools=[
                get_target_recent_tweets,
                get_target_price_action,
                get_official_token_profile,
            ],
            model=self._model,
            model_settings=default_agent_model_settings(),
        )
        return await self._run_stage(
            stage="investigator",
            route=route,
            agent=agent,
            output_type=InvestigationReport,
            input_payload=spec.input_payload,
            prompt=spec.prompt_text,
            audit=audit,
            tool_ctx=tool_ctx,
            max_turns=self._investigator_max_turns,
        )

    async def _run_decision_maker(
        self,
        *,
        route: DecisionRoute,
        context: dict[str, Any],
        completeness: dict[str, Any],
        investigation: InvestigationReport,
        run_id: str,
        audit: dict[str, Any],
        tool_ctx: PulseToolContext,
    ) -> StageRunAudit:
        spec = self._decision_runtime.decision_maker_stage_spec(
            route=route,
            context=context,
            completeness=completeness,
            investigation=investigation,
        )
        tools = [get_target_recent_tweets] if self._decision_maker_enable_fallback_tool else []
        agent = Agent[PulseToolContext](
            name=f"PulseDecisionMaker{_route_label(route)}",
            instructions=spec.prompt_text,
            output_type=StrictJsonOutputSchema(FinalDecision),
            tools=tools,
            model=self._model,
            model_settings=default_agent_model_settings(),
        )
        return await self._run_stage(
            stage="decision_maker",
            route=route,
            agent=agent,
            output_type=FinalDecision,
            input_payload=spec.input_payload,
            prompt=spec.prompt_text,
            audit=audit,
            tool_ctx=tool_ctx,
            max_turns=self._decision_maker_max_turns,
        )

    async def _run_stage(
        self,
        *,
        stage: StageName,
        route: DecisionRoute,
        agent: Agent[PulseToolContext],
        output_type: type[Any],
        input_payload: dict[str, Any],
        prompt: str,
        audit: dict[str, Any],
        tool_ctx: PulseToolContext,
        max_turns: int,
    ) -> StageRunAudit:
        stage_input = json.dumps(input_payload, ensure_ascii=False, sort_keys=True)
        base_trace_metadata = {**audit["trace_metadata"], "stage": stage, "route": route}
        run_config = RunConfig(
            workflow_name=self.workflow_name,
            trace_id=audit["sdk_trace_id"],
            group_id=_group_id(input_payload.get("context")),
            trace_include_sensitive_data=self.trace_include_sensitive_data,
            tracing_disabled=not self.trace_enabled,
            trace_metadata=base_trace_metadata,
        )
        started = int(time.time() * 1000)
        raw_output: Any = None
        result_obj: Any = None
        tool_calls_count_before = int(getattr(tool_ctx, "tool_calls_count", 0) or 0)
        audit_extra: dict[str, Any] = {
            "safety_net_used": False,
            "safety_net_retries": 0,
            "parse_mode": "strict",
            "usage": {},
        }
        try:
            if self._safety_net is not None:
                final_output, audit_extra, result_obj = await self._llm_gateway.run_with_limits(
                    "pulse_candidate",
                    stage,
                    self.timeout_seconds,
                    lambda: self._safety_net.run_with_safety_net(
                        agent=agent,
                        input_payload=stage_input,
                        run_config=run_config,
                        pydantic_output_type=output_type,
                        context=tool_ctx,
                        max_turns=max_turns,
                        return_result=True,
                    ),
                )
                raw_output = final_output
            else:
                result_obj = await self._llm_gateway.run_with_limits(
                    "pulse_candidate",
                    stage,
                    self.timeout_seconds,
                    lambda: self._runner.run(
                        agent,
                        stage_input,
                        max_turns=max_turns,
                        run_config=run_config,
                        context=tool_ctx,
                    ),
                )
                raw_output = getattr(result_obj, "final_output", None)
                audit_extra = {**audit_extra, "usage": _extract_usage(result_obj)}
            output = raw_output if isinstance(raw_output, output_type) else output_type.model_validate(raw_output)
        except SafetyNetExhausted as exhausted:
            finished = int(time.time() * 1000)
            audit_extra = exhausted.audit_extra
            trace_metadata_failed = {
                **base_trace_metadata,
                **audit_extra,
                **_tool_count_metadata(tool_calls_count_before, tool_ctx),
            }
            return StageRunAudit(
                stage=stage,
                route=route,
                attempt_index=0,
                input_json=_with_tool_calls(input_payload, result_obj),
                prompt_text=prompt,
                response_json=None,
                trace_metadata_json=trace_metadata_failed,
                usage_json=audit_extra.get("usage") or {},
                latency_ms=max(0, finished - started),
                started_at_ms=started,
                finished_at_ms=finished,
                status="failed",
                error=f"{type(exhausted.original).__name__}: {exhausted.original}"[:1000],
                safety_net_used=True,
                safety_net_retries=int(audit_extra.get("safety_net_retries") or 0),
                parse_mode=str(audit_extra.get("parse_mode") or "instructor_failed"),
            )
        except Exception as exc:
            finished = int(time.time() * 1000)
            status: StageStatus = "timeout" if isinstance(exc, TimeoutError) else "failed"
            trace_metadata_failed = {
                **base_trace_metadata,
                **audit_extra,
                **_tool_count_metadata(tool_calls_count_before, tool_ctx),
            }
            return StageRunAudit(
                stage=stage,
                route=route,
                attempt_index=0,
                input_json=_with_tool_calls(input_payload, result_obj),
                prompt_text=prompt,
                response_json={"raw_output": _truncate(raw_output)} if raw_output is not None else None,
                trace_metadata_json=trace_metadata_failed,
                usage_json=audit_extra.get("usage") or {},
                latency_ms=max(0, finished - started),
                started_at_ms=started,
                finished_at_ms=finished,
                status=status,
                error=f"{type(exc).__name__}: {exc}"[:1000],
                safety_net_used=bool(audit_extra.get("safety_net_used")),
                safety_net_retries=int(audit_extra.get("safety_net_retries") or 0),
                parse_mode=str(audit_extra.get("parse_mode") or "strict"),
            )
        finished = int(time.time() * 1000)
        trace_metadata_ok = {
            **base_trace_metadata,
            **audit_extra,
            **_tool_count_metadata(tool_calls_count_before, tool_ctx),
        }
        return StageRunAudit(
            stage=stage,
            route=route,
            attempt_index=0,
            input_json=_with_tool_calls(input_payload, result_obj),
            prompt_text=prompt,
            response_json=output.model_dump(mode="json"),
            trace_metadata_json=trace_metadata_ok,
            usage_json=audit_extra.get("usage") or {},
            latency_ms=max(0, finished - started),
            started_at_ms=started,
            finished_at_ms=finished,
            status="ok",
            error=None,
            safety_net_used=bool(audit_extra.get("safety_net_used")),
            safety_net_retries=int(audit_extra.get("safety_net_retries") or 0),
            parse_mode=str(audit_extra.get("parse_mode") or "strict"),
        )

    def _build_model(self):
        return OpenAIChatCompletionsModel(
            model=self.model,
            openai_client=self._llm_gateway.openai_client(
                model=self.model,
                base_url=self.base_url,
                timeout_s=self.timeout_seconds,
            ),
        )

    async def aclose(self) -> None:
        return None


def _route_label(route: DecisionRoute) -> str:
    return {"cex": "Cex", "meme": "Meme", "research_only": "ResearchOnly"}.get(str(route), "Cex")


def _api_base(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    if not value:
        return "https://api.openai.com/v1"
    return value if value.endswith("/v1") else f"{value}/v1"


def _group_id(context: Any) -> str | None:
    if not isinstance(context, dict):
        return None
    candidate_id = _context_string(context, "candidate_id")
    if candidate_id:
        return candidate_id
    return _context_string(context, "subject_key")


def _context_string(context: dict[str, Any], key: str) -> str | None:
    value = context.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truncate(value: Any, *, limit: int = 4000) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text[:limit]


def _tool_count_metadata(before: int, tool_ctx: PulseToolContext) -> dict[str, int]:
    after = int(getattr(tool_ctx, "tool_calls_count", 0) or 0)
    return {
        "tool_calls_count_before": before,
        "tool_calls_count_after": after,
        "tool_calls_count_delta": max(0, after - before),
    }


def _with_tool_calls(input_payload: dict[str, Any], result_obj: Any) -> dict[str, Any]:
    """Return a copy of ``input_payload`` with a ``tool_calls`` summary attached.

    The summary is a list of ``{tool_name, args, result_summary}`` dicts derived
    from the SDK ``RunResult.new_items`` (preferred) or ``raw_responses``. We
    keep this in ``StageRunAudit.input_json`` rather than its own column so v1
    eval cases stay schema-compatible.
    """

    summary = _extract_tool_calls(result_obj)
    if not summary:
        return dict(input_payload)
    return {**input_payload, "tool_calls": summary}


def _extract_tool_calls(result_obj: Any) -> list[dict[str, Any]]:
    if result_obj is None:
        return []
    items = getattr(result_obj, "new_items", None) or []
    summary: list[dict[str, Any]] = []
    # Track tool_call_id → entry to attach matching outputs.
    by_call_id: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, ToolCallItem) or _looks_like(item, "tool_call_item"):
            entry = {
                "tool_name": _safe_get(item, "tool_name") or _safe_raw_attr(item, "name"),
                "args": _safe_raw_attr(item, "arguments"),
                "result_summary": None,
            }
            summary.append(entry)
            call_id = _safe_get(item, "call_id") or _safe_raw_attr(item, "call_id") or _safe_raw_attr(item, "id")
            if call_id:
                by_call_id[str(call_id)] = entry
        elif _looks_like(item, "tool_call_output_item"):
            call_id = _safe_raw_attr(item, "call_id") or _safe_get(item, "call_id")
            target = by_call_id.get(str(call_id)) if call_id else None
            if target is None and summary:
                target = summary[-1]
            if target is not None:
                target["result_summary"] = _summarise_output(getattr(item, "output", None))
    return summary


def _looks_like(item: Any, type_name: str) -> bool:
    return getattr(item, "type", None) == type_name


def _safe_get(item: Any, name: str) -> Any:
    try:
        value = getattr(item, name, None)
    except Exception:
        return None
    return value


def _safe_raw_attr(item: Any, name: str) -> Any:
    raw = getattr(item, "raw_item", None)
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw.get(name)
    return getattr(raw, name, None)


def _summarise_output(value: Any, *, limit: int = 400) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value[:limit]
    try:
        encoded = json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    except (TypeError, ValueError):
        encoded = str(value)
    return encoded[:limit]


def _extract_usage(result: Any) -> dict[str, Any]:
    for candidate in _usage_candidates(result):
        payload = _usage_payload(candidate)
        if payload:
            return payload
    return {}


def _usage_candidates(result: Any) -> list[Any]:
    if result is None:
        return []
    candidates = [
        getattr(result, "usage", None),
        getattr(getattr(result, "context_wrapper", None), "usage", None),
    ]
    for attr in ("raw_response", "response", "final_response"):
        response = getattr(result, attr, None)
        candidates.append(getattr(response, "usage", None))
        candidates.append(response)
    responses = getattr(result, "raw_responses", None) or getattr(result, "responses", None)
    if isinstance(responses, list | tuple):
        for response in responses:
            candidates.append(getattr(response, "usage", None))
            candidates.append(response)
    return candidates


def _usage_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        data = model_dump(mode="json")
        if isinstance(data, dict):
            return cast(dict[str, Any], _json_safe_usage(data))
    data = _json_safe_usage(value)
    if isinstance(data, dict):
        return data
    return {}


def _json_safe_usage(value: Any, *, depth: int = 0) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if depth > 8:
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe_usage(item, depth=depth + 1) for key, item in value.items() if item is not None}
    if isinstance(value, list | tuple):
        return [_json_safe_usage(item, depth=depth + 1) for item in value if item is not None]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        data = model_dump(mode="json")
        return _json_safe_usage(data, depth=depth + 1)
    object_values = _public_object_values(value)
    if object_values:
        return {key: _json_safe_usage(item, depth=depth + 1) for key, item in object_values.items() if item is not None}
    return str(value)


def _public_object_values(value: Any) -> dict[str, Any]:
    if not hasattr(value, "__dict__") and not hasattr(value, "__slots__"):
        return {}
    data = {}
    if hasattr(value, "__dict__"):
        data.update(
            {str(key): item for key, item in vars(value).items() if not str(key).startswith("_") and item is not None}
        )
    slot_names = set(_public_slot_names(value))
    for name in slot_names:
        if name in data:
            continue
        try:
            item = getattr(value, name)
        except AttributeError:
            continue
        if item is not None:
            data[name] = item
    for name, item in inspect.getmembers_static(value):
        if name.startswith("_") or name in data:
            continue
        if isinstance(item, property | classmethod | staticmethod):
            continue
        if isinstance(item, GetSetDescriptorType | MemberDescriptorType):
            continue
        if item is None or callable(item):
            continue
        if isinstance(item, type):
            continue
        data[name] = item
    return data


def _public_slot_names(value: Any) -> tuple[str, ...]:
    names: list[str] = []
    for cls in type(value).__mro__:
        slots = getattr(cls, "__slots__", ())
        if isinstance(slots, str):
            slot_items = (slots,)
        else:
            try:
                slot_items = tuple(slots)
            except TypeError:
                continue
        for name in slot_items:
            text = str(name)
            if text.startswith("_") or text in {"__dict__", "__weakref__"}:
                continue
            names.append(text)
    return tuple(names)


__all__ = [
    "AGENT_NAME",
    "WORKFLOW_NAME",
    "OpenAIAgentsPulseDecisionClient",
    "PulseDecisionAgentResult",
    "_extract_usage",
]
