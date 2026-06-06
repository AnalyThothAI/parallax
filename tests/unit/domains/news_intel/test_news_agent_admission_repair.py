from __future__ import annotations

from typing import Any

from parallax.domains.news_intel.runtime.news_projection_work import ITEM_BRIEF_INPUT, PAGE_PROJECTION
from parallax.domains.news_intel.services.news_agent_admission_repair import repair_news_agent_market_admission

NOW_MS = 2_000_000


def test_repair_news_agent_market_admission_dry_run_reports_new_policy_without_mutating() -> None:
    repos = _FakeRepos(
        [
            _candidate("news-1"),
            _candidate(
                "news-2",
                provider_article_keys=["provider:duplicate"],
                exact_duplicate_candidates=[
                    {
                        "news_item_id": "news-representative",
                        "provider_article_keys": ["provider:duplicate"],
                        "story_key": "story-duplicate",
                        "lifecycle_status": "processed",
                        "agent_admission_status": "eligible",
                    }
                ],
            ),
        ]
    )

    result = repair_news_agent_market_admission(
        repos=repos,
        since_ms=NOW_MS - 8_000,
        until_ms=NOW_MS,
        min_provider_score=80,
        limit=50,
        dry_run=True,
        now_ms=NOW_MS,
    )

    assert result["mode"] == "dry_run"
    assert result["evaluated"] == 2
    assert result["would_enqueue"] == 1
    assert result["updated"] == 0
    assert result["enqueued"] == 0
    assert result["counts_by_status"] == {"eligible": 1, "exact_duplicate": 1}
    assert result["counts_by_previous_reason"] == {"non_crypto_subject": 2}
    assert repos.news.updates == []
    assert repos.news_projection_dirty_targets.enqueue_calls == []


def test_repair_news_agent_market_admission_execute_persists_and_enqueues_eligible_work() -> None:
    repos = _FakeRepos([_candidate("news-1")])

    result = repair_news_agent_market_admission(
        repos=repos,
        since_ms=NOW_MS - 8_000,
        until_ms=NOW_MS,
        min_provider_score=80,
        limit=50,
        dry_run=False,
        now_ms=NOW_MS,
    )

    assert result["mode"] == "execute"
    assert result["evaluated"] == 1
    assert result["would_enqueue"] == 1
    assert result["updated"] == 1
    assert result["enqueued"] == 1
    assert result["counts_by_status"] == {"eligible": 1}
    assert repos.news.updates[0]["news_item_id"] == "news-1"
    assert repos.news.updates[0]["admission"].status == "eligible"
    assert [call["targets"][0]["projection_name"] for call in repos.news_projection_dirty_targets.enqueue_calls] == [
        PAGE_PROJECTION,
        ITEM_BRIEF_INPUT,
    ]


def _candidate(
    news_item_id: str,
    *,
    provider_article_keys: list[str] | None = None,
    exact_duplicate_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    item = {
        "news_item_id": news_item_id,
        "title": "Nvidia shares rise after AI semiconductor demand update",
        "summary": "Nvidia shares rose after a provider-scored update on AI semiconductor demand.",
        "lifecycle_status": "processed",
        "published_at_ms": NOW_MS - 1_000,
        "content_classification_json": {"event_type": "company_update"},
        "provider_signal_json": {"source": "provider", "score": 91},
        "analysis_admission_status": "page_only",
        "analysis_admission_reason": "non_crypto_subject",
        "provider_article_keys": provider_article_keys or [f"provider:{news_item_id}"],
        "canonical_url": f"https://example.com/news/{news_item_id}",
        "url_identity_kind": "article",
        "story_key": f"story-{news_item_id}",
    }
    return {
        "item": item,
        "entities": [{"entity_type": "equity", "symbol": "NVDA", "name": "Nvidia"}],
        "token_mentions": [],
        "fact_candidates": [],
        "exact_duplicate_candidates": exact_duplicate_candidates or [],
        "story_candidates": [],
        "current_brief": None,
    }


class _FakeRepos:
    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.news = _FakeNewsRepository(candidates)
        self.news_projection_dirty_targets = _FakeDirtyTargetRepository()


class _FakeNewsRepository:
    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.candidates = candidates
        self.updates: list[dict[str, Any]] = []

    def list_agent_admission_repair_candidates(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.last_candidate_query = dict(kwargs)
        return self.candidates

    def update_item_agent_admission(self, **kwargs: Any) -> int:
        self.updates.append(dict(kwargs))
        return 1

    def servable_news_item_ids(self, news_item_ids: list[str]) -> list[str]:
        return list(news_item_ids)


class _FakeDirtyTargetRepository:
    def __init__(self) -> None:
        self.enqueue_calls: list[dict[str, Any]] = []

    def enqueue_targets(self, targets: list[dict[str, Any]], **kwargs: Any) -> int:
        self.enqueue_calls.append({"targets": list(targets), **kwargs})
        return len(targets)
