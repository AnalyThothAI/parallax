from __future__ import annotations

import pytest

from parallax.app.surfaces.api.routes_notifications import _notification_payload, _public_notification_payload


def test_news_notification_exposes_only_the_delivery_contract() -> None:
    public = _public_notification_payload(
        "news_high_signal",
        {
            "news_item_id": "news-1",
            "representative_news_item_id": "news-1",
            "story_key": "story-1",
            "decision_class": "driver",
            "direction": "bullish",
            "symbols": ["$bov", "BOV"],
            "semantic_signature": "semantic-1",
            "display_title": "Title",
            "summary": "Summary",
            "canonical_url": "https://example.test/news-1",
            "source_domain": "example.test",
            "external_push_signature": "external-1",
            "external_push_eligible": True,
            "external_push_suppression_reason": None,
            "agent_brief": {"artifact_version_hash": "retired"},
            "story": {"member_news_item_ids": ["retired"]},
            "provider_signal": {"score": 99},
        },
    )

    assert public == {
        "news_item_id": "news-1",
        "representative_news_item_id": "news-1",
        "story_key": "story-1",
        "decision_class": "driver",
        "direction": "bullish",
        "semantic_signature": "semantic-1",
        "display_title": "Title",
        "summary": "Summary",
        "external_push_signature": "external-1",
        "canonical_url": "https://example.test/news-1",
        "source_domain": "example.test",
        "symbols": ["BOV"],
        "external_push_eligible": True,
    }


@pytest.mark.parametrize(
    "payload_json",
    [
        pytest.param("{not-json", id="invalid-json-text"),
        pytest.param('{"story_key":"story-1"}', id="json-text-is-not-db-jsonb"),
        pytest.param(None, id="missing"),
        pytest.param([], id="list"),
    ],
)
def test_news_notification_requires_a_jsonb_object(payload_json: object) -> None:
    row = {"rule_id": "news_high_signal", "channels_json": ["in_app"]}
    if payload_json is not None:
        row["payload_json"] = payload_json

    with pytest.raises(ValueError, match="news_high_signal_payload_json_required"):
        _notification_payload(row)


@pytest.mark.parametrize(
    "field_name",
    [
        "news_item_id",
        "representative_news_item_id",
        "story_key",
        "decision_class",
        "direction",
        "semantic_signature",
        "display_title",
        "summary",
        "external_push_signature",
        "external_push_suppression_reason",
        "canonical_url",
        "source_domain",
    ],
)
def test_news_notification_rejects_malformed_present_text(field_name: str) -> None:
    with pytest.raises(ValueError, match=f"news_high_signal_{field_name}_required"):
        _public_notification_payload("news_high_signal", {field_name: 123})


@pytest.mark.parametrize("symbols", ({"BTC": True}, ["BTC", 123], [" "]))
def test_news_notification_rejects_malformed_symbols(symbols: object) -> None:
    with pytest.raises(ValueError, match="news_high_signal_symbols_required"):
        _public_notification_payload("news_high_signal", {"symbols": symbols})


@pytest.mark.parametrize("value", (0, 1, "true", []))
def test_news_notification_rejects_malformed_delivery_eligibility(value: object) -> None:
    with pytest.raises(ValueError, match="news_high_signal_external_push_eligible_required"):
        _public_notification_payload("news_high_signal", {"external_push_eligible": value})


def test_non_news_notification_keeps_generic_payload_json_parsing() -> None:
    payload = _notification_payload(
        {
            "rule_id": "watched_account_activity",
            "payload_json": '{"event_id":"event-1"}',
            "channels_json": '["in_app"]',
        }
    )

    assert payload["payload"] == {"event_id": "event-1"}
    assert payload["channels"] == ["in_app"]


def test_non_news_invalid_json_is_empty_instead_of_becoming_a_compatibility_shape() -> None:
    payload = _notification_payload(
        {
            "rule_id": "watched_account_activity",
            "payload_json": "{not-json",
            "channels_json": ["in_app"],
        }
    )

    assert payload["payload"] == {}
