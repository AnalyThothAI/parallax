from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import pytest
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage

from parallax.domains.macro_intel.services.daily_macro_judgment import (
    EvidenceAvailability,
    EvidencePackHealth,
    MacroEvidenceItem,
    MacroEvidencePack,
)
from parallax.domains.macro_intel.services.macro_cross_asset_rules import market_session_close_ms
from parallax.integrations.model_execution.macro_judgment_deepagent import (
    MacroJudgmentDeepAgent,
    _agent_pack_view,
)


def test_analyst_uses_create_deep_agent_and_native_task_for_isolated_review() -> None:
    pack = _pack()
    payload = _judgment_payload(pack)
    fake_model = FakeMessagesListChatModel(responses=[AIMessage(content="unused")])
    fake_reviewer_model = FakeMessagesListChatModel(responses=[AIMessage(content="unused")])
    captured: dict[str, Any] = {}

    def agent_factory(**kwargs: Any) -> _FakeGraph:
        captured.update(kwargs)
        return _FakeGraph(kwargs=kwargs, payload=payload)

    adapter = MacroJudgmentDeepAgent(
        model=fake_model,
        model_name="fake-model",
        reviewer_model=fake_reviewer_model,
        reviewer_model_name="fake-reviewer-model",
        timeout_seconds=5,
        agent_factory=agent_factory,
    )

    result = asyncio.run(adapter.analyze(pack))

    assert captured["model"] is fake_model
    assert captured["name"] == "macro-analyst"
    assert [type(item) for item in captured["middleware"][1:]] == [
        ModelCallLimitMiddleware,
        ToolCallLimitMiddleware,
        ToolCallLimitMiddleware,
        ToolCallLimitMiddleware,
    ]
    assert captured["middleware"][0].__class__.__name__ == "enforce_macro_workflow"
    assert captured["middleware"][1].run_limit == 16
    assert captured["middleware"][2].run_limit == 6
    assert captured["middleware"][3].run_limit == 6
    assert [tool.name for tool in captured["tools"]] == [
        "read_macro_evidence_pack",
        "submit_daily_macro_judgment",
    ]
    submit_schema = captured["tools"][1].args_schema.model_json_schema()
    assert submit_schema["properties"]["judgment"]["type"] == "object"
    assert "$defs" not in submit_schema
    assert len(captured["subagents"]) == 1
    reviewer = captured["subagents"][0]
    assert reviewer["name"] == "macro-reviewer"
    assert reviewer["model"] is fake_reviewer_model
    assert [type(item) for item in reviewer["middleware"][1:]] == [
        ModelCallLimitMiddleware,
        ToolCallLimitMiddleware,
        ToolCallLimitMiddleware,
    ]
    assert reviewer["middleware"][0].__class__.__name__ == "enforce_reviewer_inputs"
    assert reviewer["middleware"][1].run_limit == 5
    assert reviewer["middleware"][2].run_limit == 1
    assert [tool.name for tool in reviewer["tools"]] == [
        "read_macro_evidence_pack",
        "read_submitted_daily_macro_judgment",
    ]
    assert result.reviewer.disposition == "pass"
    assert result.judgment.spy_5d.direction.value == "range"
    assert result.judgment.all_evidence_refs <= pack.evidence_refs
    assert result.audit["native_task_calls"] == 1
    assert result.audit["reviewer_dispositions"] == ["pass"]
    assert result.audit["analyst_model_name"] == "fake-model"
    assert result.audit["reviewer_model_name"] == "fake-reviewer-model"
    assert result.audit["workflow_model_call_limit"] == 16
    assert result.audit["reviewer_model_call_limit"] == 5
    assert result.audit["reviewer_pack_read_limit"] == 1
    assert result.audit["workflow_pack_read_limit"] == 6
    assert result.audit["workflow_submit_call_limit"] == 6
    assert result.audit["submission_validation_failures"] == 0
    assert result.audit["analyst_pack_sections_read"] == ["full"]
    assert result.audit["reviewer_pack_sections_read"] == ["full"]
    assert result.audit["allowed_main_tools"] == [
        "read_macro_evidence_pack",
        "submit_daily_macro_judgment",
        "task",
    ]
    assert set(result.audit["excluded_tools"]) >= {
        "execute",
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "grep",
    }


def test_revision_is_bounded_to_one_submission_and_one_closure_review() -> None:
    pack = _pack()
    payload = _judgment_payload(pack)
    fake_model = FakeMessagesListChatModel(responses=[AIMessage(content="unused")])
    adapter = MacroJudgmentDeepAgent(
        model=fake_model,
        model_name="fake-model",
        reviewer_model=fake_model,
        reviewer_model_name="fake-reviewer-model",
        timeout_seconds=5,
        agent_factory=lambda **kwargs: _RevisionGraph(kwargs=kwargs, payload=payload),
    )

    result = asyncio.run(adapter.analyze(pack))

    assert result.reviewer.disposition == "pass"
    assert result.audit["analyst_submissions"] == 2
    assert result.audit["native_task_calls"] == 2
    assert result.audit["reviewer_dispositions"] == ["revise", "pass"]


def test_second_reviewer_cannot_reopen_revision_loop() -> None:
    pack = _pack()
    payload = _judgment_payload(pack)
    fake_model = FakeMessagesListChatModel(responses=[AIMessage(content="unused")])
    adapter = MacroJudgmentDeepAgent(
        model=fake_model,
        model_name="fake-model",
        reviewer_model=fake_model,
        reviewer_model_name="fake-reviewer-model",
        timeout_seconds=5,
        agent_factory=lambda **kwargs: _RevisionGraph(
            kwargs=kwargs,
            payload=payload,
            second_disposition="revise",
        ),
    )

    with pytest.raises(RuntimeError, match="second_review_must_close"):
        asyncio.run(adapter.analyze(pack))


def test_agent_pack_view_is_bounded_to_pack_owned_analysis_fields() -> None:
    pack = _pack()

    view = _agent_pack_view(pack)

    assert view["agent_view_version"] == "macro_agent_pack_view_v1"
    assert view["evidence_pack_hash"] == pack.pack_hash
    assert view["agent_view_hash"]
    assert view["evidence_policy"] == "latest_for_page_referenced_concepts_v1"
    assert view["full_pack_evidence_count"] == 1
    assert view["agent_view_evidence_count"] == 1
    assert set(view["pages"]) == {
        "overview",
        "cross_asset",
        "rates_inflation",
        "growth_labor",
        "liquidity_funding",
        "credit",
    }
    assert view["evidence"][0]["citation_id"] == "E001"
    assert view["citation_map"]["asset:spy"] == "E001"
    assert "evidence_ref" not in view["evidence"][0]
    assert "ingested_at_ms" not in view["evidence"][0]


class _FakeGraph:
    def __init__(self, *, kwargs: dict[str, Any], payload: dict[str, object]) -> None:
        self._kwargs = kwargs
        self._payload = payload

    async def ainvoke(self, _input: dict[str, Any]) -> dict[str, Any]:
        await _read_full_pack(self._kwargs["tools"][0])
        await _read_full_pack(self._kwargs["subagents"][0]["tools"][0])
        submit = self._kwargs["tools"][1]
        await submit.ainvoke({"judgment": self._payload})
        call_id = "native-review-1"
        return {
            "structured_response": self._payload,
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "task",
                            "args": {"description": "review", "subagent_type": "macro-reviewer"},
                            "id": call_id,
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(
                    content='{"disposition":"pass","issues":[]}',
                    tool_call_id=call_id,
                ),
            ],
        }


class _RevisionGraph:
    def __init__(
        self,
        *,
        kwargs: dict[str, Any],
        payload: dict[str, object],
        second_disposition: str = "pass",
    ) -> None:
        self._kwargs = kwargs
        self._payload = payload
        self._second_disposition = second_disposition

    async def ainvoke(self, _input: dict[str, Any]) -> dict[str, Any]:
        await _read_full_pack(self._kwargs["tools"][0])
        await _read_full_pack(self._kwargs["tools"][0])
        reviewer_read = self._kwargs["subagents"][0]["tools"][0]
        await _read_full_pack(reviewer_read)
        await _read_full_pack(reviewer_read)
        submit = self._kwargs["tools"][1]
        await submit.ainvoke({"judgment": self._payload})
        await submit.ainvoke({"judgment": self._payload})
        first_id = "native-review-1"
        second_id = "native-review-2"
        second_issues = (
            "[]"
            if self._second_disposition == "pass"
            else '[{"code":"causal_jump","message":"still open","evidence_refs":[]}]'
        )
        return {
            "structured_response": self._payload,
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "task",
                            "args": {"description": "review", "subagent_type": "macro-reviewer"},
                            "id": first_id,
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(
                    content=(
                        '{"disposition":"revise","issues":'
                        '[{"code":"causal_jump","message":"close the chain","evidence_refs":[]}]}'
                    ),
                    tool_call_id=first_id,
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "task",
                            "args": {"description": "closure", "subagent_type": "macro-reviewer"},
                            "id": second_id,
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(
                    content=(f'{{"disposition":"{self._second_disposition}","issues":{second_issues}}}'),
                    tool_call_id=second_id,
                ),
            ],
        }


async def _read_full_pack(read_tool: Any) -> None:
    await read_tool.ainvoke({})


def _pack() -> MacroEvidencePack:
    session = date(2026, 7, 22)
    cutoff = market_session_close_ms(session)
    item = MacroEvidenceItem(
        evidence_ref="macro:asset:spy:2026-07-22:test",
        page_id="cross_asset",
        source_name="test",
        concept_key="asset:spy",
        series_key="test:SPY",
        observed_at=session,
        available_at_ms=cutoff,
        availability=EvidenceAvailability.SESSION_CLOSE,
        source_timestamp=session.isoformat(),
        ingested_at_ms=cutoff + 1,
        data_quality="ok",
        selection_rule="session_close_market_fact",
        content_hash="a" * 64,
        content={"value_numeric": "625.10"},
    )
    return MacroEvidencePack(
        session_date=session,
        market_cutoff_ms=cutoff,
        sealed_at_ms=cutoff + 2,
        projection_version="macro_decision_v2",
        pages={
            "overview": {"page_id": "overview"},
            "cross_asset": {
                "page_id": "cross_asset",
                "drivers": [{"code": "spy", "evidence_refs": ["asset:spy"]}],
            },
            "rates_inflation": {"page_id": "rates_inflation"},
            "growth_labor": {"page_id": "growth_labor"},
            "liquidity_funding": {"page_id": "liquidity_funding"},
            "credit": {"page_id": "credit"},
        },
        evidence=(item,),
        health=EvidencePackHealth(status="ready"),
    )


def _judgment_payload(pack: MacroEvidencePack) -> dict[str, object]:
    ref = "E001"
    return {
        "experimental_marker": "experimental_shadow_research",
        "session_date": pack.session_date.isoformat(),
        "market_cutoff_ms": pack.market_cutoff_ms,
        "data_health": "ready",
        "macro_state": "增长放缓，但信用与流动性尚未形成系统压力。",
        "pressures": [
            {
                "axis": "growth",
                "state": "easing",
                "mechanism": "增长放缓温和压制盈利预期。",
                "evidence_refs": [ref],
            }
        ],
        "spy_5d": {
            "horizon_sessions": 5,
            "direction": "range",
            "thesis": "短期信号相互抵消。",
            "evidence_refs": [ref],
        },
        "spy_20d": {
            "horizon_sessions": 20,
            "direction": "up",
            "thesis": "信用稳定支持中期风险偏好。",
            "evidence_refs": [ref],
        },
        "counterevidence": [{"statement": "增长仍可能继续走弱。", "evidence_refs": [ref]}],
        "audit_versions": {
            "evidence_pack_hash": pack.pack_hash,
            "schema_version": "daily_macro_judgment_v1",
            "prompt_version": "macro_analyst_v1",
            "workflow_version": "deepagents_analyst_reviewer_v1",
        },
    }
