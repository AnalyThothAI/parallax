from __future__ import annotations

from typing import Any

from parallax.domains.narrative_intel.read_models.narrative_read_model import NarrativeReadModel


def test_token_case_exposes_admission_coverage_and_preserves_raw_posts() -> None:
    repository = _Repository(status="admitted")
    posts = {"items": [{"event_id": "event-1", "text": "raw evidence"}]}

    hydrated = NarrativeReadModel(repository).hydrate_token_case(
        {
            "target": {"target_type": "Asset", "target_id": "asset-1"},
            "posts": posts,
        },
        window="1h",
        scope="all",
    )

    assert hydrated["posts"] is posts
    assert "semantic" not in hydrated["posts"]["items"][0]
    assert hydrated["narrative_admission"] == {
        "status": "admitted",
        "is_current": True,
        "reason": "radar_row",
        "computed_at_ms": 1_900,
        "currentness": {"display_status": "current", "reason": "radar_row"},
        "coverage": {"source_mentions": 4, "independent_authors": 3},
        "data_gaps": [],
    }


def test_token_radar_maps_missing_admission_without_legacy_digest_fields() -> None:
    repository = _Repository(status=None)
    hydrated = NarrativeReadModel(repository).hydrate_token_radar(
        {"targets": [{"target": {"target_type": "Asset", "target_id": "asset-1"}}], "attention": []},
        window="1h",
        scope="all",
    )

    admission = hydrated["targets"][0]["narrative_admission"]
    assert admission["status"] == "missing"
    assert admission["coverage"] == {"source_mentions": 0, "independent_authors": 0}
    assert admission["currentness"] == {"display_status": "not_ready", "reason": "no_current_admission"}
    assert "dominant_narratives" not in admission
    assert "semantic_coverage" not in admission["coverage"]


class _Repository:
    def __init__(self, *, status: str | None) -> None:
        self.status = status

    def current_narrative_admissions_for_targets(
        self,
        targets: list[dict[str, str]],
        *,
        window: str,
        scope: str,
        schema_version: str,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        target = targets[0]
        key = (target["target_type"], target["target_id"])
        if self.status is None:
            return {}
        return {
            key: {
                "target_type": key[0],
                "target_id": key[1],
                "window": window,
                "scope": scope,
                "schema_version": schema_version,
                "status": "admitted",
                "is_current": True,
                "reason": "radar_row",
                "source_event_count": 4,
                "independent_author_count": 3,
                "computed_at_ms": 1_900,
                "currentness": {"display_status": "current", "reason": "radar_row"},
                "data_gaps_json": [],
            }
        }
