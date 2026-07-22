from __future__ import annotations


def test_api_macro_currentness_uses_publication_state_without_sync_run() -> None:
    from parallax.app.surfaces.api.routes_macro import _macro_currentness

    payload = _macro_currentness(
        snapshot={
            "asof_date": "2026-05-26",
            "source_coverage_json": {"latest_observed_at": "2026-05-27"},
        },
        publication_state={
            "latest_attempt_status": "published",
            "row_count": 318,
            "latest_attempt_finished_at_ms": 1_779_000_000_000,
        },
    )

    assert payload == {
        "publication_status": "published",
        "publication_row_count": 318,
        "publication_finished_at_ms": 1_779_000_000_000,
        "facts_max_observed_at": "2026-05-27",
        "projection_lag_days": 1,
        "projection_behind_facts": True,
    }


def test_api_macro_currentness_rejects_timestamp_latest_observed_at() -> None:
    from parallax.app.surfaces.api.routes_macro import _macro_currentness

    payload = _macro_currentness(
        snapshot={
            "asof_date": "2026-05-26",
            "source_coverage_json": {"latest_observed_at": "2026-05-27T08:30:00Z"},
        },
        publication_state={
            "latest_attempt_status": "published",
            "row_count": 318,
            "latest_attempt_finished_at_ms": 1_779_000_000_000,
        },
    )

    assert payload["facts_max_observed_at"] is None
    assert payload["projection_lag_days"] is None
    assert payload["projection_behind_facts"] is False


def test_api_macro_currentness_rejects_non_yyyy_mm_dd_date_text() -> None:
    from parallax.app.surfaces.api.routes_macro import _macro_currentness

    for latest_observed_at in ("20260528", "2026-W22-4"):
        payload = _macro_currentness(
            snapshot={
                "asof_date": "2026-05-26",
                "source_coverage_json": {"latest_observed_at": latest_observed_at},
            },
            publication_state=None,
        )

        assert payload["facts_max_observed_at"] is None
        assert payload["projection_lag_days"] is None
        assert payload["projection_behind_facts"] is False
