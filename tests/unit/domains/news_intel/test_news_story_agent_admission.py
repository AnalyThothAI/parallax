from __future__ import annotations

from parallax.domains.news_intel.services.news_item_agent_admission import (
    NewsItemAgentAdmissionContext,
    decide_news_item_agent_admission,
)

NOW_MS = 2_000_000_000_000


def _story_item(**overrides):
    item = {
        "news_item_id": "news-1",
        "published_at_ms": NOW_MS - 60_000,
        "lifecycle_status": "processed",
        "content_classification_json": {"policy_version": "news_content_classification_v1"},
        "provider_signal_json": {"source": "provider", "status": "ready", "score": 95},
        "source_role": "news",
        "story_key": "story:hormuz",
    }
    item.update(overrides)
    return item


def test_similar_story_without_material_delta_skips_model() -> None:
    admission = decide_news_item_agent_admission(
        item=_story_item(source_role="news"),
        entities=[{"normalized_value": "iran", "entity_type": "country"}],
        token_mentions=[],
        fact_candidates=[{"event_type": "geopolitical_risk", "validation_status": "accepted"}],
        context=NewsItemAgentAdmissionContext(
            story_candidates=[
                {
                    "news_item_id": "news-rep",
                    "story_key": "story:hormuz",
                    "source_role": "news",
                    "provider_signal_json": {"score": 96},
                    "current_brief": {"status": "ready"},
                    "entities": [{"normalized_value": "iran", "entity_type": "country"}],
                    "fact_candidates": [{"event_type": "geopolitical_risk", "validation_status": "accepted"}],
                }
            ],
        ),
        now_ms=NOW_MS,
    )

    assert admission.eligible is False
    assert admission.status == "similar_story_covered"
    assert admission.representative_news_item_id == "news-rep"
    assert admission.basis["material_delta"]["has_delta"] is False


def test_material_delta_refreshes_one_story_current_brief() -> None:
    admission = decide_news_item_agent_admission(
        item=_story_item(source_role="official_exchange"),
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        context=NewsItemAgentAdmissionContext(
            story_candidates=[
                {
                    "news_item_id": "news-rep",
                    "story_key": "story:hormuz",
                    "source_role": "specialist_media",
                    "current_brief": {"status": "ready"},
                }
            ],
        ),
        now_ms=NOW_MS,
    )

    assert admission.eligible is True
    assert admission.status == "eligible_refresh"
    assert admission.representative_news_item_id == "news-1"
    assert admission.basis["material_delta"]["has_delta"] is True
    assert admission.basis["material_delta"]["reasons"] == ["source_role_upgrade"]
