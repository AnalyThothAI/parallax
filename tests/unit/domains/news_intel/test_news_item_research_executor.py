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
        self.mapping_handlers: set[str] = set()
        self.rows_by_handler: dict[str, Any] = {}

    def get_news_observation_history(self, *, news_item_id: str, limit: int) -> list[dict[str, Any]] | dict[str, Any]:
        return self._record("get_news_observation_history", {"news_item_id": news_item_id, "limit": limit})

    def search_news_archive(
        self,
        *,
        current_news_item_id: str,
        query_terms: list[str],
        symbols: list[str],
        window_hours: int,
        match_modes: list[str],
        limit: int,
        now_ms: int,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        return self._record(
            "search_news_archive",
            {
                "current_news_item_id": current_news_item_id,
                "query_terms": query_terms,
                "symbols": symbols,
                "window_hours": window_hours,
                "match_modes": match_modes,
                "limit": limit,
                "now_ms": now_ms,
            },
        )

    def get_source_quality_context_for_item(self, *, news_item_id: str) -> list[dict[str, Any]] | dict[str, Any]:
        return self._record("get_source_quality_context_for_item", {"news_item_id": news_item_id})

    def get_target_news_context(
        self,
        *,
        current_news_item_id: str,
        target_refs: list[dict[str, str]],
        symbol_fallbacks: list[str],
        window_hours: int,
        limit: int,
        now_ms: int,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        return self._record(
            "get_target_news_context",
            {
                "current_news_item_id": current_news_item_id,
                "target_refs": target_refs,
                "symbol_fallbacks": symbol_fallbacks,
                "window_hours": window_hours,
                "limit": limit,
                "now_ms": now_ms,
            },
        )

    def get_fact_context(
        self,
        *,
        news_item_id: str,
        include_rejected: bool,
        limit: int,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        return self._record(
            "get_fact_context",
            {"news_item_id": news_item_id, "include_rejected": include_rejected, "limit": limit},
        )

    def _record(self, name: str, kwargs: dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
        self.calls.append((name, kwargs))
        if name in self.fail_handlers:
            raise TimeoutError(f"{name} timed out")
        if name in self.rows_by_handler:
            return self.rows_by_handler[name]
        row = {
            "news_item_id": "news-2",
            "title": "ETF follow-up",
            "summary": "Public summary",
            "provider_item_id": "raw-provider-id",
            "raw_payload_json": {"body": "raw"},
            "nested": {"api_key": "secret", "kept": "visible"},
            "token": "credential-token",
            "unexpected_internal_column": "internal",
            "result_basis": "exact_target",
            "evidence_ref": "archive:news-2",
        }
        if name in self.mapping_handlers:
            return row
        return [row]


def test_executor_rejects_unknown_and_mutation_tool_calls_without_repo_call() -> None:
    repo = FakeNewsRepo()
    plan = _plan(
        [
            _call("call-1", "delete_news_items", {"limit": 1}),
            _call("call-2", "get_fact_context", {"limit": 2}),
        ]
    )

    result = execute_news_research_plan(repo, plan, base_packet=_base_packet(), now_ms=NOW_MS)

    assert result.status == "partial"
    assert "unknown_tool" in result.error_codes
    assert repo.calls == [("get_fact_context", {"news_item_id": "news-1", "include_rejected": False, "limit": 2})]
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


def test_executor_requires_base_packet_for_contextual_repo_dispatch_before_repo_call() -> None:
    repo = FakeNewsRepo()
    plan = _plan([_call("call-1", "get_source_quality", {})])

    result = execute_news_research_plan(repo, plan, now_ms=NOW_MS)

    assert result.status == "failed"
    assert result.error_codes == ["base_packet_required"]
    assert repo.calls == []
    assert result.tool_results[0].skipped_reason == "base_packet_required"


def test_executor_redacts_sensitive_fields_and_computes_sha256_result_hash() -> None:
    repo = FakeNewsRepo()
    plan = _plan([_call("call-1", "search_news_archive", {"query_terms": ["ETF"], "limit": 4})])

    result = execute_news_research_plan(repo, plan, base_packet=_base_packet(), now_ms=NOW_MS)

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
            "summary": "Public summary",
            "result_basis": "exact_target",
            "evidence_ref": "archive:news-2",
        }
    ]
    assert {
        "provider_item_id",
        "raw_payload_json",
        "nested",
        "token",
        "unexpected_internal_column",
    }.isdisjoint(tool_result.rows[0])
    assert "filtered:unexpected_internal_column" in tool_result.redaction_notes
    assert "redacted:provider_item_id" in tool_result.redaction_notes
    assert "redacted:raw_payload_json" in tool_result.redaction_notes
    assert "redacted:nested.api_key" in tool_result.redaction_notes
    assert "redacted:token" in tool_result.redaction_notes


def test_executor_normalizes_mapping_repo_output_into_one_public_row() -> None:
    repo = FakeNewsRepo()
    repo.mapping_handlers.add("get_source_quality_context_for_item")
    plan = _plan([_call("call-1", "get_source_quality", {})])

    result = execute_news_research_plan(repo, plan, base_packet=_base_packet(), now_ms=NOW_MS)

    assert result.status == "ok"
    assert result.tool_results[0].row_count == 1
    assert result.tool_results[0].rows == [
        {"news_item_id": "news-2", "result_basis": "exact_target", "evidence_ref": "archive:news-2"}
    ]


def test_executor_preserves_target_context_aggregate_envelope_and_redacts_nested_fields() -> None:
    repo = FakeNewsRepo()
    repo.rows_by_handler["get_target_news_context"] = {
        "counts": {"items": 4, "sources": 3},
        "top_items": [
            {
                "news_item_id": "news-2",
                "title": "SOL ETF update",
                "summary": "Compact summary",
                "published_at_ms": 1_778_999_000_000,
                "source_domain": "example.com",
                "source_name": "Example",
                "source_role": "primary",
                "trust_tier": "tier_1",
                "target_type": "CexToken",
                "target_id": "cex_token:SOL",
                "display_symbol": "SOL",
                "matching_basis": "target_ref",
                "match_reason": "resolved token mention",
                "match_confidence": 0.93,
                "brief_status": "ready",
                "novelty_status": "update",
                "confirmation_state": "multi_source_confirmed",
                "result_basis": "exact_target",
                "evidence_ref": "target:news-2",
                "raw_payload_json": {"body": "raw"},
                "unexpected_internal_column": "internal",
                "nested": {"api_key": "secret", "public_note": "drop whole internal nesting"},
            }
        ],
        "latest_items": [
            {
                "news_item_id": "news-3",
                "title": "Latest SOL note",
                "source_domain": "latest.example",
                "matching_basis": "symbol_heuristic",
                "match_confidence": 0.71,
                "result_basis": "symbol_heuristic",
                "secret": "drop",
            }
        ],
        "source_domain_count": 3,
        "high_score_count": 2,
        "matching_basis": ["target_ref", "symbol_heuristic"],
        "truncated": False,
        "result_basis": "exact_target",
        "evidence_refs": ["target:news-2", "target:news-3"],
        "provider_item_id": "raw-provider-id",
        "unexpected_internal_column": "internal",
    }
    plan = _plan(
        [
            _call(
                "target",
                "get_target_news_context",
                {"target_refs": [{"target_type": "CexToken", "target_id": "cex_token:SOL"}]},
            )
        ]
    )

    result = execute_news_research_plan(repo, plan, base_packet=_base_packet(), now_ms=NOW_MS)

    assert result.status == "ok"
    assert result.tool_results[0].rows == [
        {
            "counts": {"items": 4, "sources": 3},
            "top_items": [
                {
                    "news_item_id": "news-2",
                    "title": "SOL ETF update",
                    "summary": "Compact summary",
                    "published_at_ms": 1_778_999_000_000,
                    "source_domain": "example.com",
                    "source_name": "Example",
                    "source_role": "primary",
                    "trust_tier": "tier_1",
                    "target_type": "CexToken",
                    "target_id": "cex_token:SOL",
                    "display_symbol": "SOL",
                    "matching_basis": "target_ref",
                    "match_reason": "resolved token mention",
                    "match_confidence": 0.93,
                    "brief_status": "ready",
                    "novelty_status": "update",
                    "confirmation_state": "multi_source_confirmed",
                    "result_basis": "exact_target",
                    "evidence_ref": "target:news-2",
                }
            ],
            "latest_items": [
                {
                    "news_item_id": "news-3",
                    "title": "Latest SOL note",
                    "source_domain": "latest.example",
                    "matching_basis": "symbol_heuristic",
                    "match_confidence": 0.71,
                    "result_basis": "symbol_heuristic",
                }
            ],
            "source_domain_count": 3,
            "high_score_count": 2,
            "matching_basis": ["target_ref", "symbol_heuristic"],
            "truncated": False,
            "result_basis": "exact_target",
            "evidence_refs": ["target:news-2", "target:news-3"],
        }
    ]
    assert "filtered:unexpected_internal_column" in result.tool_results[0].redaction_notes
    assert "redacted:provider_item_id" in result.tool_results[0].redaction_notes
    assert "redacted:top_items.0.raw_payload_json" in result.tool_results[0].redaction_notes
    assert "redacted:top_items.0.nested.api_key" in result.tool_results[0].redaction_notes
    assert "redacted:latest_items.0.secret" in result.tool_results[0].redaction_notes


def test_executor_preserves_archive_compact_public_fields() -> None:
    repo = FakeNewsRepo()
    repo.rows_by_handler["search_news_archive"] = [
        {
            "news_item_id": "news-4",
            "title": "Archive title",
            "summary": "Archive summary",
            "published_at_ms": 1_778_990_000_000,
            "canonical_url": "https://example.com/news-4",
            "source_domain": "example.com",
            "source_name": "Example",
            "source_role": "primary",
            "trust_tier": "tier_1",
            "matched_terms": ["ETF"],
            "match_reason": "title term",
            "matching_basis": "title",
            "match_confidence": 0.82,
            "brief_status": "ready",
            "novelty_status": "repeat",
            "confirmation_state": "multi_source_confirmed",
            "source_consensus_zh": "多来源确认",
            "result_basis": "similar_news",
            "evidence_ref": "archive:news-4",
            "unexpected_internal_column": "internal",
        }
    ]
    plan = _plan([_call("archive", "search_news_archive", {"query_terms": ["ETF"]})])

    result = execute_news_research_plan(repo, plan, base_packet=_base_packet(), now_ms=NOW_MS)

    assert result.tool_results[0].rows == [
        {
            "news_item_id": "news-4",
            "title": "Archive title",
            "summary": "Archive summary",
            "published_at_ms": 1_778_990_000_000,
            "canonical_url": "https://example.com/news-4",
            "source_domain": "example.com",
            "source_name": "Example",
            "source_role": "primary",
            "trust_tier": "tier_1",
            "matched_terms": ["ETF"],
            "match_reason": "title term",
            "matching_basis": "title",
            "match_confidence": 0.82,
            "brief_status": "ready",
            "novelty_status": "repeat",
            "confirmation_state": "multi_source_confirmed",
            "source_consensus_zh": "多来源确认",
            "result_basis": "similar_news",
            "evidence_ref": "archive:news-4",
        }
    ]
    assert "filtered:unexpected_internal_column" in result.tool_results[0].redaction_notes


def test_executor_preserves_source_quality_compact_public_fields() -> None:
    repo = FakeNewsRepo()
    repo.rows_by_handler["get_source_quality_context_for_item"] = {
        "source_domain": "example.com",
        "source_name": "Example",
        "source_role": "primary",
        "trust_tier": "tier_1",
        "window": "7d",
        "computed_at_ms": 1_778_999_999_000,
        "items_fetched": 42,
        "duplicate_rate": 0.12,
        "quality_score": 91,
        "diagnostics_json": {"freshness": "ok", "token": "drop nested token"},
        "source_quality_status": "healthy",
        "provider_health_status": "ok",
        "provider_status": "active",
        "source_health": "ok",
        "result_basis": "source_quality",
        "evidence_ref": "source:example.com",
        "sync_cursor": "cursor",
        "unexpected_internal_column": "internal",
    }
    plan = _plan([_call("quality", "get_source_quality", {})])

    result = execute_news_research_plan(repo, plan, base_packet=_base_packet(), now_ms=NOW_MS)

    assert result.tool_results[0].rows == [
        {
            "source_domain": "example.com",
            "source_name": "Example",
            "source_role": "primary",
            "trust_tier": "tier_1",
            "window": "7d",
            "computed_at_ms": 1_778_999_999_000,
            "items_fetched": 42,
            "duplicate_rate": 0.12,
            "quality_score": 91,
            "diagnostics_json": {"freshness": "ok"},
            "source_quality_status": "healthy",
            "provider_health_status": "ok",
            "provider_status": "active",
            "source_health": "ok",
            "result_basis": "source_quality",
            "evidence_ref": "source:example.com",
        }
    ]
    assert "redacted:diagnostics_json.token" in result.tool_results[0].redaction_notes
    assert "redacted:sync_cursor" in result.tool_results[0].redaction_notes
    assert "filtered:unexpected_internal_column" in result.tool_results[0].redaction_notes


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
                    "match_modes": ["fact", "unknown", "title", "token", "summary", "source_title", "body"],
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
            _call("fact", "get_fact_context", {"include_rejected": "yes", "limit": 99}),
            _call("history", "get_observation_history", {"limit": 99}),
        ]
    )

    result = execute_news_research_plan(repo, plan, base_packet=_base_packet(extra_allowed=True), now_ms=NOW_MS)

    assert result.error_codes == []
    assert repo.calls[0] == (
        "search_news_archive",
        {
            "current_news_item_id": "news-1",
            "query_terms": ["a", "b", "c", "d", "e"],
            "symbols": ["BTC", "ETH", "SOL", "DOGE", "XRP"],
            "window_hours": 168,
            "match_modes": ["fact", "title", "token", "source_title"],
            "limit": 8,
            "now_ms": NOW_MS,
        },
    )
    assert repo.calls[1] == (
        "get_target_news_context",
        {
            "current_news_item_id": "news-1",
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
            "now_ms": NOW_MS,
        },
    )
    assert repo.calls[2] == ("get_fact_context", {"news_item_id": "news-1", "include_rejected": False, "limit": 20})
    assert repo.calls[3] == ("get_news_observation_history", {"news_item_id": "news-1", "limit": 25})
    assert [tool.input for tool in result.tool_results] == [
        {
            "query_terms": ["a", "b", "c", "d", "e"],
            "symbols": ["BTC", "ETH", "SOL", "DOGE", "XRP"],
            "match_modes": ["fact", "title", "token", "source_title"],
            "window_hours": 168,
            "limit": 8,
        },
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
        {"include_rejected": False, "limit": 20},
        {"limit": 25},
    ]


def test_executor_clamps_search_terms_symbols_and_fallback_string_lengths() -> None:
    repo = FakeNewsRepo()
    plan = _plan(
        [
            _call(
                "archive",
                "search_news_archive",
                {"query_terms": ["x" * 80], "symbols": ["S" * 80]},
            ),
            _call(
                "target",
                "get_target_news_context",
                {
                    "target_refs": [{"target_type": "CexToken", "target_id": "cex_token:SOL"}],
                    "symbol_fallbacks": ["F" * 80],
                },
            ),
        ]
    )

    execute_news_research_plan(repo, plan, base_packet=_base_packet(), now_ms=NOW_MS)

    assert repo.calls[0][1]["query_terms"] == ["x" * 64]
    assert repo.calls[0][1]["symbols"] == ["S" * 32]
    assert repo.calls[0][1]["match_modes"] == ["title", "token", "fact", "source_title"]
    assert repo.calls[1][1]["symbol_fallbacks"] == ["F" * 32]


def test_executor_passes_include_rejected_true_only_when_explicit_true() -> None:
    repo = FakeNewsRepo()
    plan = _plan(
        [
            _call("default", "get_fact_context", {}),
            _call("explicit", "get_fact_context", {"include_rejected": True}),
        ]
    )

    execute_news_research_plan(repo, plan, base_packet=_base_packet(), now_ms=NOW_MS)

    assert repo.calls[0] == ("get_fact_context", {"news_item_id": "news-1", "include_rejected": False, "limit": 20})
    assert repo.calls[1] == ("get_fact_context", {"news_item_id": "news-1", "include_rejected": True, "limit": 20})


def test_executor_reports_truncated_when_public_row_exceeds_material_budget() -> None:
    repo = FakeNewsRepo()
    repo.rows_by_handler["search_news_archive"] = [
        {
            "news_item_id": "news-huge",
            "title": "x" * 2_000,
            "summary": "oversized public row",
            "result_basis": "similar_news",
            "evidence_ref": "archive:news-huge",
        }
    ]
    plan = _plan([_call("archive", "search_news_archive", {"query_terms": ["ETF"]})])

    result = execute_news_research_plan(repo, plan, base_packet=_base_packet(), now_ms=NOW_MS)

    tool_result = result.tool_results[0]
    assert tool_result.status == "truncated"
    assert tool_result.truncated is True
    assert tool_result.row_count == 0
    assert tool_result.rows == []
    assert result.truncated is True


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

    result = execute_news_research_plan(repo, plan, base_packet=_base_packet(), now_ms=NOW_MS)

    assert len(result.tool_results) == 5
    assert len(repo.calls) == 4
    assert [name for name, _ in repo.calls].count("search_news_archive") == 2
    assert {"max_archive_searches_exceeded", "max_tool_calls_exceeded"}.issubset(set(result.error_codes))
    assert result.skipped_call_count == 2


def test_executor_handles_repo_exceptions_as_failed_tool_result_without_raising() -> None:
    repo = FakeNewsRepo()
    repo.fail_handlers.add("get_fact_context")
    plan = _plan([_call("call-1", "get_fact_context", {"limit": 5})])

    result = execute_news_research_plan(repo, plan, base_packet=_base_packet(), now_ms=NOW_MS)

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
