from __future__ import annotations

from typing import Any

from parallax.domains.news_intel.services.news_item_research_executor import execute_news_research_plan
from parallax.domains.news_intel.types.news_item_brief import (
    NewsContextTargetRef,
    NewsItemBriefBasePacket,
    NewsItemBriefBudgetReport,
    NewsItemBriefNewsItem,
    NewsItemResearchBudget,
    NewsItemResearchPlan,
    NewsItemResearchToolCall,
    news_research_tool_material_hash,
)

NOW_MS = 1_779_000_000_000


class FakeNewsRepo:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_handlers: set[str] = set()

    def get_news_observation_history(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self._record("get_news_observation_history", kwargs)

    def search_news_archive(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self._record("search_news_archive", kwargs)

    def get_source_quality_context_for_item(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self._record("get_source_quality_context_for_item", kwargs)

    def get_target_news_context(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self._record("get_target_news_context", kwargs)

    def get_fact_context(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self._record("get_fact_context", kwargs)

    def _record(self, name: str, kwargs: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append((name, kwargs))
        if name in self.fail_handlers:
            raise TimeoutError(f"{name} timed out")
        return [
            {
                "news_item_id": "news-2",
                "title": "ETF follow-up",
                "provider_item_id": "raw-provider-id",
                "raw_payload_json": {"body": "raw"},
                "nested": {"api_key": "secret", "kept": "visible"},
                "token": "credential-token",
                "result_basis": "exact_target",
                "evidence_ref": "archive:news-2",
            }
        ]


def test_executor_rejects_unknown_and_mutation_tool_calls_without_repo_call() -> None:
    repo = FakeNewsRepo()
    plan = _plan(
        [
            _call("call-1", "delete_news_items", {"limit": 1}),
            _call("call-2", "get_fact_context", {"limit": 2}),
        ]
    )

    result = execute_news_research_plan(repo, plan, now_ms=NOW_MS)

    assert result.status == "partial"
    assert "unknown_tool" in result.error_codes
    assert repo.calls == [("get_fact_context", {"limit": 2})]
    assert result.tool_results[0].status == "failed"
    assert result.tool_results[0].skipped_reason == "unknown_tool"


def test_executor_rejects_target_context_refs_outside_base_allowlist_before_repo_call() -> None:
    repo = FakeNewsRepo()
    plan = _plan(
        [
            _call(
                "call-1",
                "get_target_news_context",
                {
                    "target_refs": [{"target_type": "CexToken", "target_id": "cex_token:FAKE"}],
                    "limit": 12,
                },
            )
        ]
    )

    result = execute_news_research_plan(repo, plan, base_packet=_base_packet(), now_ms=NOW_MS)

    assert result.status == "failed"
    assert result.error_codes == ["target_ref_not_allowed"]
    assert repo.calls == []
    assert result.tool_results[0].status == "failed"
    assert result.tool_results[0].skipped_reason == "target_ref_not_allowed"


def test_executor_redacts_sensitive_fields_and_computes_sha256_result_hash() -> None:
    repo = FakeNewsRepo()
    plan = _plan([_call("call-1", "search_news_archive", {"query_terms": ["ETF"], "limit": 4})])

    result = execute_news_research_plan(repo, plan, now_ms=NOW_MS)

    tool_result = result.tool_results[0]
    assert tool_result.status == "ok"
    assert tool_result.result_hash == news_research_tool_material_hash(tool_result)
    assert tool_result.result_hash.startswith("sha256:")
    assert tool_result.generated_at_ms == NOW_MS
    assert tool_result.query_version == "search_news_archive_v1"
    assert tool_result.rows == [
        {
            "news_item_id": "news-2",
            "title": "ETF follow-up",
            "nested": {"kept": "visible"},
            "result_basis": "exact_target",
            "evidence_ref": "archive:news-2",
        }
    ]
    assert {"provider_item_id", "raw_payload_json"}.isdisjoint(tool_result.rows[0])
    assert "redacted:provider_item_id" in tool_result.redaction_notes
    assert "redacted:nested.api_key" in tool_result.redaction_notes
    assert "redacted:token" in tool_result.redaction_notes


def test_executor_clamps_archive_target_fact_and_observation_inputs() -> None:
    repo = FakeNewsRepo()
    plan = _plan(
        [
            _call(
                "archive",
                "search_news_archive",
                {
                    "query_terms": ["a", "b", "c", "d", "e", "f"],
                    "symbols": ["BTC", "ETH", "SOL", "DOGE", "XRP", "ADA"],
                    "window_hours": 999,
                    "limit": 99,
                },
            ),
            _call(
                "target",
                "get_target_news_context",
                {
                    "target_refs": [
                        {"target_type": "CexToken", "target_id": "cex_token:SOL"},
                        {"target_type": "CexToken", "target_id": "cex_token:BTC"},
                        {"target_type": "CexToken", "target_id": "cex_token:ETH"},
                        {"target_type": "CexToken", "target_id": "cex_token:DOGE"},
                        {"target_type": "CexToken", "target_id": "cex_token:XRP"},
                        {"target_type": "CexToken", "target_id": "cex_token:ADA"},
                    ],
                    "symbol_fallbacks": ["SOL", "BTC", "ETH", "DOGE"],
                    "window_hours": 999,
                    "limit": 99,
                },
            ),
            _call("fact", "get_fact_context", {"limit": 99}),
            _call("history", "get_observation_history", {"limit": 99}),
        ]
    )

    result = execute_news_research_plan(repo, plan, base_packet=_base_packet(extra_allowed=True), now_ms=NOW_MS)

    assert result.error_codes == []
    assert repo.calls[0] == (
        "search_news_archive",
        {
            "query_terms": ["a", "b", "c", "d", "e"],
            "symbols": ["BTC", "ETH", "SOL", "DOGE", "XRP"],
            "window_hours": 168,
            "limit": 8,
        },
    )
    assert repo.calls[1] == (
        "get_target_news_context",
        {
            "target_refs": [
                {"target_type": "CexToken", "target_id": "cex_token:SOL"},
                {"target_type": "CexToken", "target_id": "cex_token:BTC"},
                {"target_type": "CexToken", "target_id": "cex_token:ETH"},
                {"target_type": "CexToken", "target_id": "cex_token:DOGE"},
                {"target_type": "CexToken", "target_id": "cex_token:XRP"},
            ],
            "symbol_fallbacks": ["SOL", "BTC", "ETH"],
            "window_hours": 168,
            "limit": 12,
        },
    )
    assert repo.calls[2] == ("get_fact_context", {"limit": 20})
    assert repo.calls[3] == ("get_news_observation_history", {"limit": 25})
    assert [tool.input for tool in result.tool_results] == [call[1] for call in repo.calls]


def test_executor_applies_archive_and_total_tool_call_caps() -> None:
    repo = FakeNewsRepo()
    plan = _plan(
        [
            _call("archive-1", "search_news_archive", {"query_terms": ["a"]}),
            _call("archive-2", "search_news_archive", {"query_terms": ["b"]}),
            _call("archive-3", "search_news_archive", {"query_terms": ["c"]}),
            _call("fact", "get_fact_context", {}),
            _call("history", "get_observation_history", {}),
            _call("quality", "get_source_quality", {}),
        ]
    )

    result = execute_news_research_plan(repo, plan, now_ms=NOW_MS)

    assert len(result.tool_results) == 5
    assert len(repo.calls) == 4
    assert [name for name, _ in repo.calls].count("search_news_archive") == 2
    assert {"max_archive_searches_exceeded", "max_tool_calls_exceeded"}.issubset(set(result.error_codes))
    assert result.skipped_call_count == 2


def test_executor_handles_repo_exceptions_as_failed_tool_result_without_raising() -> None:
    repo = FakeNewsRepo()
    repo.fail_handlers.add("get_fact_context")
    plan = _plan([_call("call-1", "get_fact_context", {"limit": 5})])

    result = execute_news_research_plan(repo, plan, now_ms=NOW_MS)

    assert result.status == "failed"
    assert result.error_codes == ["repo_exception"]
    assert result.tool_results[0].status == "failed"
    assert result.tool_results[0].skipped_reason == "repo_exception"
    assert result.tool_results[0].rows == []


def _plan(calls: list[NewsItemResearchToolCall]) -> NewsItemResearchPlan:
    budget = NewsItemResearchBudget(
        max_tool_calls=5,
        max_total_chars=3000,
        hard_max_total_chars=6000,
        max_rows_per_tool=25,
    )
    if len(calls) > 5:
        return NewsItemResearchPlan.model_construct(
            status="ready",
            research_todos=[],
            tool_calls=calls,
            budget=budget,
            policy_notes_zh="",
            skip_reason_zh="",
            evidence_refs=[],
        )
    return NewsItemResearchPlan(
        status="ready",
        tool_calls=calls,
        budget=budget,
    )


def _call(tool_call_id: str, tool_name: str, tool_input: dict[str, Any]) -> NewsItemResearchToolCall:
    return NewsItemResearchToolCall(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        input=tool_input,
        purpose_zh="补充上下文",
    )


def _base_packet(*, extra_allowed: bool = False) -> NewsItemBriefBasePacket:
    allowed = [
        NewsContextTargetRef(
            target_type="CexToken",
            target_id="cex_token:SOL",
            display_symbol="SOL",
            resolution_status="unique_by_context",
            confidence=0.91,
            target_scope="crypto",
        ),
    ]
    if extra_allowed:
        allowed.extend(
            [
                NewsContextTargetRef(target_type="CexToken", target_id=f"cex_token:{symbol}")
                for symbol in ["BTC", "ETH", "DOGE", "XRP", "ADA"]
            ]
        )
    return NewsItemBriefBasePacket(
        packet_id="packet-1",
        news_item=NewsItemBriefNewsItem(
            news_item_id="news-1",
            title="SEC is said to approve spot SOL ETF filings",
            summary="ETF filing update.",
        ),
        allowed_context_targets=allowed,
        base_budget_report=NewsItemBriefBudgetReport(
            material_budget_chars=12_000,
            material_chars=2400,
            original_token_count=2,
            kept_token_count=1,
            original_fact_count=0,
            kept_fact_count=0,
        ),
        prompt_version="news-item-brief-synthesizer-v1",
        schema_version="news_item_brief_v2",
    )
