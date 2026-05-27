from __future__ import annotations

def test_api_macro_currentness_uses_publication_state_without_sync_run() -> None:
    from gmgn_twitter_intel.app.surfaces.api.routes_macro import _macro_currentness

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
