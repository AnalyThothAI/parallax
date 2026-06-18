from __future__ import annotations

from parallax.domains.news_intel.services.news_item_agent_policy import news_item_agent_brief_priority
from parallax.domains.news_intel.types.news_item_agent_admission import NewsItemAgentAdmission


def _item(**overrides):
    item = {
        "news_item_id": "news-1",
        "agent_admission_json": {"status": "eligible", "reason": "eligible"},
        "provider_signal_json": {
            "source": "provider",
            "status": "ready",
            "score": 80,
        },
    }
    item.update(overrides)
    return item


def test_news_item_agent_brief_priority_ignores_provider_scores() -> None:
    assert news_item_agent_brief_priority(
        item=_item(provider_signal_json={"source": "provider", "score": 95}),
    ) == news_item_agent_brief_priority(
        item=_item(provider_signal_json={"source": "provider", "score": 80}),
    )


def test_news_item_agent_brief_priority_ignores_provider_ready_status() -> None:
    assert news_item_agent_brief_priority(
        item=_item(provider_signal_json={"source": "provider", "status": "ready"}),
    ) == news_item_agent_brief_priority(item=_item(provider_signal_json={}))


def test_news_item_agent_brief_priority_prefers_refresh_and_material_delta() -> None:
    regular = news_item_agent_brief_priority(
        item=_item(agent_admission_json={"status": "eligible", "reason": "eligible"}),
    )
    material = news_item_agent_brief_priority(
        item=_item(
            agent_admission_json={"status": "eligible", "reason": "eligible"},
            material_delta_json={"status": "material", "changed_fields": ["market_scope"]},
        ),
    )
    refresh = news_item_agent_brief_priority(
        item=_item(agent_admission_json={"status": "eligible_refresh", "reason": "material_delta"}),
    )

    assert refresh < material < regular


def test_news_item_agent_brief_priority_uses_runtime_admission_basis() -> None:
    priority = news_item_agent_brief_priority(
        item=_item(),
        admission=NewsItemAgentAdmission(
            eligible=True,
            status="eligible",
            reason="eligible",
            representative_news_item_id="news-1",
            basis={
                "market_scope": ["crypto", "macro_rates", "us_equity"],
                "material_delta": {"has_delta": True, "reasons": ["new_accepted_fact"]},
            },
        ),
    )

    assert priority <= 18


def test_news_item_agent_brief_priority_prefers_authoritative_multi_scope_items() -> None:
    ordinary = news_item_agent_brief_priority(
        item=_item(
            source_role="observed_source",
            trust_tier="standard",
            market_scope_json={"scope": ["unknown"], "primary": "unknown"},
            content_class="other",
        ),
    )
    authoritative = news_item_agent_brief_priority(
        item=_item(
            source_role="official_exchange",
            trust_tier="high",
            market_scope_json={"scope": ["crypto", "macro_rates", "us_equity"], "primary": "crypto"},
            content_class="exchange_listing",
        ),
    )

    assert authoritative < ordinary


def test_news_item_agent_brief_priority_deprioritizes_non_executable_statuses() -> None:
    assert (
        news_item_agent_brief_priority(
            item=_item(agent_admission_json={"status": "similar_story_covered", "reason": "similar_story_covered"})
        )
        == 100
    )
