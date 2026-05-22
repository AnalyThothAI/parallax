from __future__ import annotations

from gmgn_twitter_intel.domains.equity_event_intel.services.story_grouping import choose_story_assignment

NOW_MS = 1_765_900_000_000


def test_same_company_period_and_event_family_joins_existing_story() -> None:
    assignment = choose_story_assignment(
        event=event_payload(event_type="quarterly_report", fiscal_period="2026Q1"),
        candidates=[
            story_candidate(
                story_id="story-1",
                event_type="earnings_release",
                fiscal_period="2026Q1",
            )
        ],
    )

    assert assignment.story_id == "story-1"
    assert assignment.relation == "same_story"
    assert assignment.match_reason == "same_company_period_event_family"


def test_different_fiscal_period_creates_new_story() -> None:
    assignment = choose_story_assignment(
        event=event_payload(event_type="quarterly_report", fiscal_period="2026Q2"),
        candidates=[
            story_candidate(
                story_id="story-1",
                event_type="earnings_release",
                fiscal_period="2026Q1",
            )
        ],
    )

    assert assignment.story_id is None
    assert assignment.relation == "representative"
    assert assignment.match_reason == "new_story"


def test_fallback_title_matching_records_title_time_company_overlap() -> None:
    assignment = choose_story_assignment(
        event=event_payload(
            fiscal_period=None,
            summary="Microsoft announces quarterly results",
            event_time_ms=NOW_MS + 60_000,
        ),
        candidates=[
            story_candidate(
                story_id="story-1",
                fiscal_period=None,
                representative_headline="Microsoft announces quarterly results",
                latest_seen_at_ms=NOW_MS,
            )
        ],
    )

    assert assignment.story_id == "story-1"
    assert assignment.match_reason == "title_time_company_overlap"


def event_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "company_event_id": "company-event-1",
        "company_id": "market_instrument:us_equity:MSFT",
        "ticker": "MSFT",
        "event_type": "earnings_release",
        "fiscal_period": "2026Q1",
        "event_time_ms": NOW_MS,
        "summary": "Microsoft quarterly results",
    }
    payload.update(overrides)
    return payload


def story_candidate(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "story_id": "story-1",
        "company_id": "market_instrument:us_equity:MSFT",
        "ticker": "MSFT",
        "event_type": "earnings_release",
        "fiscal_period": "2026Q1",
        "representative_headline": "Microsoft quarterly results",
        "latest_seen_at_ms": NOW_MS,
    }
    payload.update(overrides)
    return payload
