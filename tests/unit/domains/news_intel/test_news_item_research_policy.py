from __future__ import annotations

from parallax.domains.news_intel.services.news_item_research_policy import (
    classify_news_item_research_policy,
)
from parallax.domains.news_intel.types.news_item_brief import (
    NewsContextTargetRef,
    NewsItemBriefBasePacket,
    NewsItemBriefBudgetReport,
    NewsItemBriefFactLane,
    NewsItemBriefNewsItem,
    NewsItemBriefProviderSignalEvidence,
    NewsItemBriefTokenLane,
)


def test_policy_selects_fact_context_for_fact_truncated_item() -> None:
    decision = classify_news_item_research_policy(
        _base_packet(
            content_class="exchange_listing",
            fact_lanes=[_fact("fact-1")],
            budget_reasons=["fact_lanes_budget"],
            original_fact_count=30,
            kept_fact_count=1,
        )
    )

    tool_names = [call.tool_name for call in decision.research_plan.tool_calls]
    assert decision.needs_research is True
    assert "get_fact_context" in tool_names
    assert "fact_lanes_truncated" in decision.reasons


def test_policy_returns_skip_plan_for_low_signal_without_facts_provider_or_targets() -> None:
    decision = classify_news_item_research_policy(
        _base_packet(content_class="low_signal", fact_lanes=[], allowed_context_targets=[])
    )

    assert decision.needs_research is False
    assert decision.research_plan.status == "skip"
    assert decision.research_plan.tool_calls == []
    assert decision.research_plan.skip_reason_zh


def test_policy_resolved_target_selects_target_context_and_bounded_archive() -> None:
    decision = classify_news_item_research_policy(
        _base_packet(
            content_class="etf",
            token_lanes=[_token("mention-sol", "SOL")],
            allowed_context_targets=[
                NewsContextTargetRef(
                    target_type="CexToken",
                    target_id="cex_token:SOL",
                    display_symbol="SOL",
                    resolution_status="unique_by_context",
                    confidence=0.9,
                    target_scope="crypto",
                )
            ],
        )
    )

    calls = decision.research_plan.tool_calls
    by_name = {call.tool_name: call for call in calls}
    assert "get_target_news_context" in by_name
    assert by_name["get_target_news_context"].input["target_refs"] == [
        {"target_type": "CexToken", "target_id": "cex_token:SOL"}
    ]
    assert by_name["get_target_news_context"].input["symbol_fallbacks"] == []
    assert by_name["search_news_archive"].input["window_hours"] == 168
    assert by_name["search_news_archive"].input["limit"] == 8
    assert "SOL" in by_name["search_news_archive"].input["symbols"]


def test_policy_never_emits_unknown_tools_and_keeps_stable_bounded_ordering() -> None:
    first = classify_news_item_research_policy(
        _base_packet(
            content_class="regulation",
            fact_lanes=[_fact("fact-1")],
            provider_signal_evidence=NewsItemBriefProviderSignalEvidence(provider="opennews", status="ready"),
            token_lanes=[_token("mention-btc", "BTC")],
            allowed_context_targets=[
                NewsContextTargetRef(target_type="asset", target_id="asset:btc", display_symbol="BTC")
            ],
        )
    )
    second = classify_news_item_research_policy(
        _base_packet(
            content_class="regulation",
            fact_lanes=[_fact("fact-1")],
            provider_signal_evidence=NewsItemBriefProviderSignalEvidence(provider="opennews", status="ready"),
            token_lanes=[_token("mention-btc", "BTC")],
            allowed_context_targets=[
                NewsContextTargetRef(target_type="asset", target_id="asset:btc", display_symbol="BTC")
            ],
        )
    )

    allowed = {
        "get_fact_context",
        "get_observation_history",
        "get_source_quality",
        "get_target_news_context",
        "search_news_archive",
    }
    first_calls = [(call.tool_call_id, call.tool_name, call.input) for call in first.research_plan.tool_calls]
    second_calls = [(call.tool_call_id, call.tool_name, call.input) for call in second.research_plan.tool_calls]
    assert len(first.research_plan.tool_calls) <= 5
    assert {call.tool_name for call in first.research_plan.tool_calls}.issubset(allowed)
    assert first_calls == second_calls


def _base_packet(
    *,
    content_class: str,
    fact_lanes: list[NewsItemBriefFactLane] | None = None,
    token_lanes: list[NewsItemBriefTokenLane] | None = None,
    allowed_context_targets: list[NewsContextTargetRef] | None = None,
    provider_signal_evidence: NewsItemBriefProviderSignalEvidence | None = None,
    budget_reasons: list[str] | None = None,
    original_fact_count: int = 0,
    kept_fact_count: int = 0,
) -> NewsItemBriefBasePacket:
    resolved_facts = fact_lanes or []
    return NewsItemBriefBasePacket(
        packet_id="base:item-1",
        news_item=NewsItemBriefNewsItem(
            news_item_id="item-1",
            title="SOL ETF filing expands market access",
            summary="Issuer files for a SOL ETF.",
            body_excerpt="Issuer files for a SOL ETF.",
            published_at_ms=1_779_000_000_000,
            content_hash="sha256:item",
        ),
        token_lanes=token_lanes or [],
        fact_lanes=resolved_facts,
        provider_signal_evidence=provider_signal_evidence,
        evidence_refs=["item:title"],
        allowed_context_targets=allowed_context_targets or [],
        content_class=content_class,
        base_budget_report=NewsItemBriefBudgetReport(
            material_budget_chars=12_000,
            material_chars=2400,
            original_token_count=len(token_lanes or []),
            kept_token_count=len(token_lanes or []),
            original_fact_count=original_fact_count or len(resolved_facts),
            kept_fact_count=kept_fact_count or len(resolved_facts),
            truncation_reasons=budget_reasons or [],
        ),
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        input_hash="sha256:base",
    )


def _fact(fact_id: str) -> NewsItemBriefFactLane:
    return NewsItemBriefFactLane(
        fact_candidate_id=fact_id,
        event_type="listing",
        claim="Issuer files for a SOL ETF.",
        realis="actual",
        validation_status="accepted",
        evidence_quote="files for a SOL ETF",
    )


def _token(mention_id: str, symbol: str) -> NewsItemBriefTokenLane:
    return NewsItemBriefTokenLane(
        mention_id=mention_id,
        observed_symbol=symbol,
        display_symbol=symbol,
        resolution_status="known_symbol",
        target_type="asset",
        target_id=f"asset:{symbol.lower()}",
    )
