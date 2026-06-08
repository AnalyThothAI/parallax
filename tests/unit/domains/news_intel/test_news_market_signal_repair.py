from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from parallax.domains.news_intel.services.news_market_signal_repair import repair_news_market_signal


class FakeNews:
    def __init__(self) -> None:
        self.repair_rows = [
            {
                "news_item_id": "news-1",
                "published_at_ms": 3_600_000,
                "lifecycle_status": "processed",
                "content_class": "us_equity",
                "content_classification_json": {"policy_version": "test"},
                "provider_signal_json": {"source": "provider", "score": 95},
                "source_enabled": True,
                "source_watermark_ms": 3_600_000,
                "title": "Nvidia shares rise after AI server guidance",
                "summary": "US equity and AI semiconductor sentiment improves.",
            }
        ]
        self.contexts: dict[str, dict[str, Any]] = {}
        self.context_items: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []

    def list_news_market_signal_repair_candidates(self, **kwargs: Any) -> list[dict[str, Any]]:
        assert kwargs["since_ms"] == 3_600_000
        assert kwargs["min_score"] == 80
        return list(self.repair_rows)

    def load_agent_admission_repair_contexts(self, **kwargs: Any) -> dict[str, dict[str, Any]]:
        self.context_items = [dict(item) for item in kwargs["items"]]
        assert kwargs["now_ms"] == 7_200_000
        return dict(self.contexts)

    def update_item_market_scope_and_agent_admission(self, **kwargs: Any) -> int:
        self.updated.append(kwargs)
        return 1


class FakeDirtyTargets:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, Any]] = []

    def enqueue_targets(self, targets: list[dict[str, Any]], **kwargs: Any) -> int:
        self.enqueued.append({"targets": list(targets), "kwargs": dict(kwargs)})
        return len(targets)


def test_repair_news_market_signal_dry_run_reports_without_writes() -> None:
    repos = SimpleNamespace(news=FakeNews(), news_projection_dirty_targets=FakeDirtyTargets())

    result = repair_news_market_signal(repos, since_hours=1, min_score=80, execute=False, now_ms=7_200_000)

    assert result["dry_run"] is True
    assert result["matched_items"] == 1
    assert result["updated_items"] == 0
    assert result["enqueued_dirty_targets"] == 0
    assert result["eligible_items"] == 1
    assert result["suppressed_items"] == 0
    assert repos.news.updated == []
    assert repos.news_projection_dirty_targets.enqueued == []


def test_repair_news_market_signal_execute_updates_state_and_enqueues_dirty_targets() -> None:
    repos = SimpleNamespace(news=FakeNews(), news_projection_dirty_targets=FakeDirtyTargets())

    result = repair_news_market_signal(repos, since_hours=1, min_score=80, execute=True, now_ms=7_200_000)

    assert result["dry_run"] is False
    assert result["matched_items"] == 1
    assert result["updated_items"] == 1
    assert result["enqueued_dirty_targets"] == 2
    assert result["eligible_items"] == 1
    assert result["suppressed_items"] == 0
    assert repos.news.updated[0]["news_item_id"] == "news-1"
    assert repos.news.updated[0]["market_scope"].primary == "us_equity"
    assert repos.news.updated[0]["admission"].status == "eligible"
    assert repos.news.context_items[0]["story_key"].startswith("news-story:")
    assert [call["targets"][0]["projection_name"] for call in repos.news_projection_dirty_targets.enqueued] == [
        "page",
        "brief_input",
    ]


def test_repair_news_market_signal_execute_does_not_enqueue_brief_for_suppressed_item() -> None:
    repos = SimpleNamespace(news=FakeNews(), news_projection_dirty_targets=FakeDirtyTargets())
    repos.news.repair_rows[0]["provider_signal_json"] = {"source": "provider", "score": 75}

    result = repair_news_market_signal(repos, since_hours=1, min_score=80, execute=True, now_ms=7_200_000)

    assert result["matched_items"] == 1
    assert result["eligible_items"] == 0
    assert result["suppressed_items"] == 1
    assert result["enqueued_dirty_targets"] == 1
    assert [call["targets"][0]["projection_name"] for call in repos.news_projection_dirty_targets.enqueued] == ["page"]


def test_repair_news_market_signal_suppresses_exact_duplicate_context() -> None:
    repos = SimpleNamespace(news=FakeNews(), news_projection_dirty_targets=FakeDirtyTargets())
    repos.news.contexts["news-1"] = {
        "exact_duplicate": {
            "exact_duplicate": True,
            "match_type": "same_content_hash",
            "matched_news_item_id": "news-representative",
            "representative_news_item_id": "news-representative",
        },
        "similar_story": {},
        "material_delta": {"has_delta": False, "reasons": [], "evidence": {}},
    }

    result = repair_news_market_signal(repos, since_hours=1, min_score=80, execute=True, now_ms=7_200_000)

    assert result["eligible_items"] == 0
    assert result["suppressed_items"] == 1
    assert result["agent_admission_status_counts"] == {"exact_duplicate": 1}
    assert repos.news.updated[0]["admission"].status == "exact_duplicate"
    assert repos.news.updated[0]["admission"].representative_news_item_id == "news-representative"
    assert [call["targets"][0]["projection_name"] for call in repos.news_projection_dirty_targets.enqueued] == ["page"]


def test_repair_news_market_signal_suppresses_similar_story_without_material_delta() -> None:
    repos = SimpleNamespace(news=FakeNews(), news_projection_dirty_targets=FakeDirtyTargets())
    repos.news.contexts["news-1"] = {
        "exact_duplicate": {},
        "similar_story": {
            "similar_story": True,
            "reason": "same_story_key_current_brief",
            "story_key": "news-story:subject:nvidia-ai:t1",
            "representative_news_item_id": "news-representative",
        },
        "material_delta": {"has_delta": False, "reasons": [], "evidence": {}},
    }

    result = repair_news_market_signal(repos, since_hours=1, min_score=80, execute=True, now_ms=7_200_000)

    assert result["eligible_items"] == 0
    assert result["suppressed_items"] == 1
    assert result["agent_admission_status_counts"] == {"similar_story_covered": 1}
    assert repos.news.updated[0]["admission"].status == "similar_story_covered"
    assert repos.news.updated[0]["admission"].representative_news_item_id == "news-representative"
    assert [call["targets"][0]["projection_name"] for call in repos.news_projection_dirty_targets.enqueued] == ["page"]


def test_repair_news_market_signal_brief_watermark_uses_representative_target_id() -> None:
    repos = SimpleNamespace(news=FakeNews(), news_projection_dirty_targets=FakeDirtyTargets())
    repos.news.contexts["news-1"] = {
        "exact_duplicate": {},
        "similar_story": {
            "similar_story": True,
            "reason": "same_story_key_current_brief",
            "story_key": "news-story:subject:nvidia-ai:t1",
            "representative_news_item_id": "news-representative",
        },
        "material_delta": {"has_delta": True, "reason": "material_delta", "evidence": {"score_upgrade": True}},
    }

    result = repair_news_market_signal(repos, since_hours=1, min_score=80, execute=True, now_ms=7_200_000)

    assert result["eligible_items"] == 1
    assert result["agent_admission_status_counts"] == {"eligible_refresh": 1}
    brief_target = repos.news_projection_dirty_targets.enqueued[1]["targets"][0]
    assert brief_target == {
        "projection_name": "brief_input",
        "target_kind": "news_item",
        "target_id": "news-representative",
        "source_watermark_ms": 3_600_000,
        "priority": 5,
    }
