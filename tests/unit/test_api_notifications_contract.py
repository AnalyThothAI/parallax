from __future__ import annotations

import pytest

from parallax.app.surfaces.api.routes_notifications import _notification_payload


def test_watched_account_notification_preserves_native_fact_payload() -> None:
    payload = _notification_payload(
        {
            "rule_id": "watched_account_activity",
            "payload_json": {"event_id": "event-1", "author_handle": "alice"},
            "channels_json": ["in_app"],
        }
    )

    assert payload == {
        "rule_id": "watched_account_activity",
        "payload": {"event_id": "event-1", "author_handle": "alice"},
        "channels": ["in_app"],
    }


def test_notification_payload_is_a_plain_fact_mapping() -> None:
    payload = _notification_payload(
        {
            "rule_id": "watched_account_token_alert",
            "payload_json": {
                "event_id": "event-1",
                "alert_id": "alert-1",
            },
            "channels_json": ["in_app"],
        }
    )

    assert payload["payload"] == {
        "event_id": "event-1",
        "alert_id": "alert-1",
    }


@pytest.mark.parametrize(
    ("field_name", "value", "error"),
    [
        ("payload_json", '{"event_id":"event-1"}', "notification_payload_json_mapping_required"),
        ("payload_json", [], "notification_payload_json_mapping_required"),
        ("channels_json", '["in_app"]', "notification_channels_json_list_required"),
        ("channels_json", [], "notification_channels_json_list_required"),
        ("channels_json", [""], "notification_channels_json_list_required"),
    ],
)
def test_notification_rejects_non_jsonb_or_malformed_shapes(
    field_name: str,
    value: object,
    error: str,
) -> None:
    row = {
        "rule_id": "watched_account_activity",
        "payload_json": {"event_id": "event-1"},
        "channels_json": ["in_app"],
    }
    row[field_name] = value

    with pytest.raises(ValueError, match=error):
        _notification_payload(row)
