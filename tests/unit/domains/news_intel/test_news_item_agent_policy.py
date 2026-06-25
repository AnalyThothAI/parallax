from __future__ import annotations

import pytest

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
            agent_admission_json={
                "status": "eligible",
                "reason": "eligible",
                "basis": {"material_delta": {"status": "material", "changed_fields": ["market_scope"]}},
            },
        ),
    )
    refresh = news_item_agent_brief_priority(
        item=_item(agent_admission_json={"status": "eligible_refresh", "reason": "material_delta"}),
    )

    assert refresh < material < regular


def test_news_item_agent_brief_priority_ignores_sidecar_material_delta_without_admission_basis() -> None:
    assert news_item_agent_brief_priority(
        item=_item(
            agent_admission_json={"status": "eligible", "reason": "eligible"},
            material_delta_json={"status": "material", "changed_fields": ["market_scope"]},
        ),
    ) == news_item_agent_brief_priority(
        item=_item(agent_admission_json={"status": "eligible", "reason": "eligible"}),
    )


def test_news_item_agent_brief_priority_does_not_restore_status_from_scalar_alias() -> None:
    assert (
        news_item_agent_brief_priority(
            item=_item(
                agent_admission_status="eligible_refresh",
                agent_admission_json={"reason": "material_delta"},
            ),
        )
        == 100
    )


def test_news_item_agent_brief_priority_does_not_restore_scope_from_legacy_aliases() -> None:
    alias_priority = news_item_agent_brief_priority(
        item=_item(
            agent_admission_json={"status": "eligible", "reason": "eligible"},
            market_scope=["crypto", "macro_rates", "us_equity"],
        ),
    )
    nested_alias_priority = news_item_agent_brief_priority(
        item=_item(
            agent_admission_json={"status": "eligible", "reason": "eligible"},
            market_scope_json={"market_scope": ["crypto", "macro_rates", "us_equity"]},
        ),
    )
    formal_priority = news_item_agent_brief_priority(
        item=_item(
            agent_admission_json={"status": "eligible", "reason": "eligible"},
            market_scope_json={"scope": ["crypto", "macro_rates", "us_equity"]},
        ),
    )

    assert alias_priority > formal_priority
    assert nested_alias_priority > formal_priority


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        pytest.param(
            {"agent_admission_json": '{"status":"eligible"}'},
            "news_item_agent_policy_agent_admission_json_required",
            id="admission_string",
        ),
        pytest.param(
            {"agent_admission_json": {"status": "eligible", "basis": '{"material_delta":true}'}},
            "news_item_agent_policy_basis_required",
            id="basis_string",
        ),
        pytest.param(
            {
                "agent_admission_json": {
                    "status": "eligible",
                    "basis": {"material_delta": {"status": "material", "changed_fields": "market_scope"}},
                }
            },
            "news_item_agent_policy_material_delta_changed_fields_required",
            id="changed_fields_string",
        ),
        pytest.param(
            {"agent_admission_json": {"status": "eligible"}, "market_scope_json": "crypto"},
            "news_item_agent_policy_market_scope_json_required",
            id="market_scope_string",
        ),
        pytest.param(
            {"agent_admission_json": {"status": "eligible"}, "market_scope_json": {"scope": "crypto"}},
            "news_item_agent_policy_market_scope_json_scope_required",
            id="market_scope_scope_string",
        ),
    ],
)
def test_news_item_agent_brief_priority_rejects_malformed_present_policy_fields(
    overrides: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        news_item_agent_brief_priority(item=_item(**overrides))


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


def test_news_item_agent_brief_priority_rejects_loose_runtime_admission_object() -> None:
    class LooseAdmission:
        def __init__(self) -> None:
            self.status = "eligible"
            self.reason = "eligible"
            self.basis = {"market_scope": ["crypto", "macro_rates", "us_equity"]}

    with pytest.raises(TypeError, match="news_item_agent_policy_admission_contract_required"):
        news_item_agent_brief_priority(item=_item(), admission=LooseAdmission())


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
