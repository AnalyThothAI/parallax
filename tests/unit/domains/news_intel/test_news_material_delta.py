from __future__ import annotations

from parallax.domains.news_intel.services.news_material_delta import decide_news_material_delta


def test_same_story_without_new_entity_or_fact_has_no_material_delta() -> None:
    delta = decide_news_material_delta(
        item={"news_item_id": "news-new", "source_role": "observed_source", "provider_signal_json": {"score": 90}},
        representative_item={
            "news_item_id": "news-rep",
            "source_role": "observed_source",
            "provider_signal_json": {"score": 91},
        },
        entities=[{"normalized_value": "iran", "entity_type": "country"}],
        representative_entities=[{"normalized_value": "iran", "entity_type": "country"}],
        fact_candidates=[{"event_type": "geopolitical_risk", "validation_status": "accepted"}],
        representative_fact_candidates=[{"event_type": "geopolitical_risk", "validation_status": "accepted"}],
        current_brief={"status": "ready"},
    )

    assert delta.has_delta is False
    assert delta.reasons == []


def test_missing_representative_brief_is_not_material_delta_by_itself() -> None:
    delta = decide_news_material_delta(
        item={"news_item_id": "news-new", "source_role": "observed_source", "content_hash": "same"},
        representative_item={"news_item_id": "news-rep", "source_role": "observed_source", "content_hash": "same"},
        entities=[{"normalized_value": "iran", "entity_type": "country"}],
        representative_entities=[{"normalized_value": "iran", "entity_type": "country"}],
        fact_candidates=[{"event_type": "geopolitical_risk", "validation_status": "accepted"}],
        representative_fact_candidates=[{"event_type": "geopolitical_risk", "validation_status": "accepted"}],
        current_brief=None,
    )

    assert delta.has_delta is False
    assert delta.reasons == []


def test_official_source_upgrade_is_material_delta() -> None:
    delta = decide_news_material_delta(
        item={"news_item_id": "news-new", "source_role": "official_exchange", "provider_signal_json": {"score": 93}},
        representative_item={
            "news_item_id": "news-rep",
            "source_role": "specialist_media",
            "provider_signal_json": {"score": 90},
        },
        entities=[],
        representative_entities=[],
        fact_candidates=[],
        representative_fact_candidates=[],
        current_brief={"status": "ready"},
    )

    assert delta.has_delta is True
    assert "source_role_upgrade" in delta.reasons
