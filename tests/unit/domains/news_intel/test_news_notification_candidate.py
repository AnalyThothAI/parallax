from __future__ import annotations

import pytest

from parallax.domains.news_intel.interfaces import NewsNotificationCandidate


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "row_id": "row-1",
        "news_item_id": "news-1",
        "representative_news_item_id": "news-1",
        "story_key": "story-1",
        "latest_at_ms": 1_700_000_000_000,
        "headline": "Headline",
        "source_domain": "example.test",
        "canonical_url": "https://example.test/news-1",
        "direction": "bullish",
        "decision_class": "driver",
        "title_zh": "标题",
        "projected_title_zh": "投影标题",
        "summary_zh": "摘要",
        "affected_entities": [{"symbol": "$btc"}, {"target_symbol": "BTC"}, {"label": "market"}],
        "token_impacts": [{"symbol": "xyz-eth"}],
        "external_push_ready": True,
        "external_push_basis": "agent_brief",
        "external_push_block_reason": None,
    }
    row.update(overrides)
    return row


def test_repository_row_is_parsed_once_into_an_immutable_narrow_candidate() -> None:
    candidate = NewsNotificationCandidate.from_repository_row(_row())

    assert candidate.affected_symbols == ("BTC",)
    assert candidate.token_symbols == ("XYZ-ETH",)
    assert candidate.external_push_ready is True
    assert not hasattr(candidate, "story")
    assert not hasattr(candidate, "market_scope")
    assert not hasattr(candidate, "agent_brief")
    with pytest.raises(AttributeError):
        candidate.story_key = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field_name", "bad_value", "error"),
    [
        ("row_id", "", "row_id_required"),
        ("news_item_id", None, "news_item_id_required"),
        ("story_key", 1, "story_key_required"),
        ("latest_at_ms", True, "latest_at_ms_required"),
        ("source_domain", " ", "source_domain_required"),
        ("direction", None, "direction_required"),
        ("affected_entities", {}, "affected_entities_required"),
        ("token_impacts", [1], "token_impacts_invalid"),
        ("external_push_ready", "true", "external_push_ready_required"),
    ],
)
def test_candidate_boundary_rejects_malformed_projection_values(
    field_name: str,
    bad_value: object,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=f"news_notification_candidate_{error}"):
        NewsNotificationCandidate.from_repository_row(_row(**{field_name: bad_value}))
