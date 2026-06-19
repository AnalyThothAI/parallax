from __future__ import annotations

import pytest

from parallax.app.surfaces.api.routes_notifications import _notification_payload, _public_notification_payload


def test_news_high_signal_notification_rejects_malformed_agent_brief() -> None:
    with pytest.raises(ValueError, match="news_high_signal_agent_brief_required"):
        _public_notification_payload("news_high_signal", {"agent_brief": ["bad"]})


@pytest.mark.parametrize(
    "payload_json",
    [
        pytest.param("{not-json", id="invalid_json_text"),
        pytest.param('{"agent_brief": {}}', id="json_text_mapping"),
        pytest.param(None, id="missing_payload_json"),
    ],
)
def test_news_high_signal_notification_rejects_malformed_payload_json(payload_json: object) -> None:
    row = {
        "rule_id": "news_high_signal",
        "channels_json": ["in_app"],
    }
    if payload_json is not None:
        row["payload_json"] = payload_json

    with pytest.raises(ValueError, match="news_high_signal_payload_json_required"):
        _notification_payload(row)


def test_non_news_notification_keeps_generic_payload_json_parsing() -> None:
    assert (
        _notification_payload(
            {
                "rule_id": "watched_account_activity",
                "payload_json": "{not-json",
                "channels_json": ["in_app"],
            }
        )["payload"]
        == {}
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        pytest.param("affected_entities", {"label": "BTC"}, id="entities_mapping"),
        pytest.param("affected_entities", ["bad"], id="entities_scalar_member"),
        pytest.param("token_impacts", {"symbol": "BTC"}, id="impacts_mapping"),
        pytest.param("token_impacts", ["bad"], id="impacts_scalar_member"),
    ],
)
def test_news_high_signal_notification_rejects_malformed_present_lists(field_name: str, value: object) -> None:
    with pytest.raises(ValueError, match=f"news_high_signal_{field_name}_required"):
        _public_notification_payload("news_high_signal", {field_name: value})


@pytest.mark.parametrize(
    "field_name",
    [
        "news_item_id",
        "representative_news_item_id",
        "story_key",
        "agent_admission_status",
        "agent_admission_reason",
        "decision_class",
        "direction",
        "semantic_signature",
        "display_title",
        "external_push_signature",
        "external_push_suppression_reason",
        "canonical_url",
        "source_domain",
    ],
)
def test_news_high_signal_notification_rejects_malformed_top_level_text_fields(field_name: str) -> None:
    with pytest.raises(ValueError, match=f"news_high_signal_{field_name}_required"):
        _public_notification_payload("news_high_signal", {field_name: 123})


@pytest.mark.parametrize("field_name", ["story", "market_scope", "agent_admission"])
def test_news_high_signal_notification_rejects_malformed_top_level_mapping_fields(field_name: str) -> None:
    with pytest.raises(ValueError, match=f"news_high_signal_{field_name}_required"):
        _public_notification_payload("news_high_signal", {field_name: "bad"})


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        pytest.param(
            {"story": {"story_key": 123, "member_count": 1}},
            "news_high_signal_story_story_key_required",
            id="story_key_non_string",
        ),
        pytest.param(
            {"story": {"story_key": "news-story:unit:btc", "member_count": "1"}},
            "news_high_signal_story_member_count_required",
            id="story_member_count_non_int",
        ),
        pytest.param(
            {
                "market_scope": {
                    "scope": ["crypto", 123],
                    "primary": "crypto",
                    "status": "classified",
                    "reason": "test",
                    "basis": {},
                    "version": "test",
                }
            },
            "news_high_signal_market_scope_scope_required",
            id="market_scope_member_non_string",
        ),
        pytest.param(
            {
                "market_scope": {
                    "scope": ["crypto"],
                    "primary": 123,
                    "status": "classified",
                    "reason": "test",
                    "basis": {},
                    "version": "test",
                }
            },
            "news_high_signal_market_scope_primary_required",
            id="market_scope_primary_non_string",
        ),
        pytest.param(
            {
                "market_scope": {
                    "scope": ["crypto"],
                    "primary": "crypto",
                    "status": 123,
                    "reason": "test",
                    "basis": {},
                    "version": "test",
                }
            },
            "news_high_signal_market_scope_status_required",
            id="market_scope_status_non_string",
        ),
        pytest.param(
            {
                "market_scope": {
                    "scope": ["crypto"],
                    "primary": "crypto",
                    "status": "classified",
                    "reason": 123,
                    "basis": {},
                    "version": "test",
                }
            },
            "news_high_signal_market_scope_reason_required",
            id="market_scope_reason_non_string",
        ),
        pytest.param(
            {
                "market_scope": {
                    "scope": ["crypto"],
                    "primary": "crypto",
                    "status": "classified",
                    "reason": "test",
                    "basis": "bad",
                    "version": "test",
                }
            },
            "news_high_signal_market_scope_basis_required",
            id="market_scope_basis_non_mapping",
        ),
        pytest.param(
            {
                "market_scope": {
                    "scope": ["crypto"],
                    "primary": "crypto",
                    "status": "classified",
                    "reason": "test",
                    "basis": {},
                    "version": 123,
                }
            },
            "news_high_signal_market_scope_version_required",
            id="market_scope_version_non_string",
        ),
        pytest.param(
            {
                "agent_admission": {
                    "status": 123,
                    "reason": "test",
                    "representative_news_item_id": "news-1",
                }
            },
            "news_high_signal_agent_admission_status_required",
            id="agent_admission_status_non_string",
        ),
        pytest.param(
            {
                "agent_admission": {
                    "status": "eligible",
                    "reason": 123,
                    "representative_news_item_id": "news-1",
                }
            },
            "news_high_signal_agent_admission_reason_required",
            id="agent_admission_reason_non_string",
        ),
        pytest.param(
            {
                "agent_admission": {
                    "status": "eligible",
                    "reason": "test",
                    "representative_news_item_id": 123,
                }
            },
            "news_high_signal_agent_admission_representative_news_item_id_required",
            id="agent_admission_representative_non_string",
        ),
        pytest.param(
            {
                "agent_admission": {
                    "status": "eligible",
                    "reason": "test",
                    "representative_news_item_id": "news-1",
                    "basis": "bad",
                }
            },
            "news_high_signal_agent_admission_basis_required",
            id="agent_admission_basis_non_mapping",
        ),
        pytest.param(
            {
                "agent_admission": {
                    "status": "eligible",
                    "reason": "test",
                    "representative_news_item_id": "news-1",
                    "version": 123,
                }
            },
            "news_high_signal_agent_admission_version_required",
            id="agent_admission_version_non_string",
        ),
        pytest.param(
            {
                "agent_admission": {
                    "status": "eligible",
                    "reason": "test",
                    "representative_news_item_id": "news-1",
                    "eligible": 1,
                }
            },
            "news_high_signal_agent_admission_eligible_required",
            id="agent_admission_eligible_non_bool",
        ),
    ],
)
def test_news_high_signal_notification_rejects_malformed_top_level_mapping_member_fields(
    payload: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        _public_notification_payload("news_high_signal", payload)


def test_news_high_signal_notification_mapping_payloads_drop_unknown_fields_without_passthrough() -> None:
    payload = {
        "story": {
            "story_key": "news-story:unit:btc",
            "member_count": 2,
            "source_domains": ["example.test"],
            "legacy_story_passthrough": {"bad": True},
        },
        "market_scope": {
            "scope": ["crypto"],
            "primary": "crypto",
            "status": "classified",
            "reason": "test",
            "basis": {},
            "version": "test",
            "legacy_scope_passthrough": "bad",
        },
        "agent_admission": {
            "status": "eligible",
            "reason": "test",
            "representative_news_item_id": "news-1",
            "legacy_admission_passthrough": "bad",
        },
    }

    public = _public_notification_payload("news_high_signal", payload)

    assert public["story"] == {
        "story_key": "news-story:unit:btc",
        "member_count": 2,
        "source_domains": ["example.test"],
    }
    assert "legacy_scope_passthrough" not in public["market_scope"]
    assert "legacy_admission_passthrough" not in public["agent_admission"]


@pytest.mark.parametrize("value", [1, "true"])
def test_news_high_signal_notification_rejects_malformed_external_push_eligible(value: object) -> None:
    with pytest.raises(ValueError, match="news_high_signal_external_push_eligible_required"):
        _public_notification_payload("news_high_signal", {"external_push_eligible": value})


@pytest.mark.parametrize("value", ["1", True, -1])
def test_news_high_signal_notification_rejects_malformed_duplicate_count(value: object) -> None:
    with pytest.raises(ValueError, match="news_high_signal_duplicate_count_required"):
        _public_notification_payload("news_high_signal", {"duplicate_count": value})


@pytest.mark.parametrize("field_name", ["status", "direction", "decision_class", "title_zh", "summary_zh"])
def test_news_high_signal_notification_rejects_malformed_agent_brief_text_fields(field_name: str) -> None:
    agent_brief = {"status": "ready"}
    agent_brief[field_name] = 123
    with pytest.raises(ValueError, match=f"news_high_signal_agent_brief_{field_name}_required"):
        _public_notification_payload("news_high_signal", {"agent_brief": agent_brief})


def test_news_high_signal_notification_requires_agent_brief_status_when_present() -> None:
    with pytest.raises(ValueError, match="news_high_signal_agent_brief_status_required"):
        _public_notification_payload("news_high_signal", {"agent_brief": {"summary_zh": "Ready projected brief"}})


@pytest.mark.parametrize("field_name", ["label", "symbol", "name", "entity_type", "reason_zh"])
def test_news_high_signal_notification_rejects_malformed_affected_entity_text_fields(field_name: str) -> None:
    payload = {
        "affected_entities": [
            {
                "label": "BTC",
                "symbol": "BTC",
                field_name: 123,
            }
        ]
    }

    with pytest.raises(ValueError, match=f"news_high_signal_affected_entities_{field_name}_required"):
        _public_notification_payload("news_high_signal", payload)


def test_news_high_signal_notification_rejects_malformed_affected_entity_evidence_refs() -> None:
    with pytest.raises(ValueError, match="news_high_signal_affected_entities_evidence_refs_required"):
        _public_notification_payload(
            "news_high_signal",
            {"affected_entities": [{"symbol": "BTC", "evidence_refs": ["news:item", 123]}]},
        )


@pytest.mark.parametrize("field_name", ["symbol", "market_type"])
def test_news_high_signal_notification_rejects_malformed_token_impact_text_fields(field_name: str) -> None:
    payload = {
        "token_impacts": [
            {
                "symbol": "BTC",
                field_name: 123,
            }
        ]
    }

    with pytest.raises(ValueError, match=f"news_high_signal_token_impacts_{field_name}_required"):
        _public_notification_payload("news_high_signal", payload)
