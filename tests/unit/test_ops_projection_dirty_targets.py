from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from parallax.app.runtime.projection_dirty_targets import enqueue_projection_dirty_targets
from parallax.app.surfaces.cli.parser import build_parser

NOW_MS = 1_779_000_000_000


def test_enqueue_projection_dirty_targets_dry_run_reports_counts_without_writes() -> None:
    repos = FakeRepos()

    result = enqueue_projection_dirty_targets(
        repos,
        domain="all",
        execute=False,
        now_ms=NOW_MS,
        projection="all",
    )

    assert result["execute"] is False
    assert result["news"]["news_item_ids"] == 3
    assert result["news"]["news_item_targets"] == 5
    assert result["news"]["source_quality_targets"] == 2
    assert repos.news_dirty.enqueued == []
    assert repos.conn.transactions == 0


def test_enqueue_projection_dirty_targets_execute_enqueues_only_dirty_targets() -> None:
    repos = FakeRepos()

    result = enqueue_projection_dirty_targets(
        repos,
        domain="all",
        execute=True,
        now_ms=NOW_MS,
        projection="all",
        since_ms=NOW_MS - 24 * 60 * 60 * 1000,
    )

    assert result["execute"] is True
    assert repos.conn.transactions == 1
    assert repos.news_dirty.enqueued[0]["rows"] == [
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-1",
            "source_watermark_ms": NOW_MS - 1_000,
        },
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-2",
            "source_watermark_ms": NOW_MS - 2_000,
        },
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-3",
            "source_watermark_ms": NOW_MS - 3_000,
        },
    ]
    assert repos.news_dirty.enqueued[1]["rows"] == [
        {
            "projection_name": "brief_input",
            "target_kind": "news_item",
            "target_id": "news-2",
            "source_watermark_ms": NOW_MS - 2_000,
            "priority": 12,
        },
        {
            "projection_name": "brief_input",
            "target_kind": "news_item",
            "target_id": "news-3",
            "source_watermark_ms": NOW_MS - 3_000,
            "priority": 8,
        },
    ]
    assert repos.news_dirty.enqueued[2]["rows"] == [
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "_refresh"},
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-2", "window": "_refresh"},
    ]


def test_enqueue_projection_dirty_targets_parser_requires_explicit_mode() -> None:
    args = build_parser().parse_args(
        [
            "ops",
            "enqueue-projection-dirty-targets",
            "--domain",
            "news",
            "--projection",
            "brief_input",
            "--since-hours",
            "24",
            "--dry-run",
        ]
    )

    assert args.command == "ops"
    assert args.ops_command == "enqueue-projection-dirty-targets"
    assert args.domain == "news"
    assert args.projection == "brief_input"
    assert args.since_hours == 24
    assert args.dry_run is True
    assert args.execute is False


def test_enqueue_projection_dirty_targets_execute_requires_bounded_brief_repair() -> None:
    repos = FakeRepos()

    try:
        enqueue_projection_dirty_targets(
            repos,
            domain="all",
            execute=True,
            now_ms=NOW_MS,
            projection="all",
        )
    except ValueError as exc:
        assert "--since-hours" in str(exc)
    else:
        raise AssertionError("expected unbounded brief_input repair to fail")


def test_enqueue_projection_dirty_targets_page_repair_can_run_unbounded_for_page_only_rows() -> None:
    repos = FakeRepos()

    result = enqueue_projection_dirty_targets(
        repos,
        domain="news",
        execute=True,
        now_ms=NOW_MS,
        projection="page",
    )

    assert result["projection"] == "page"
    assert result["news"]["news_item_targets"] == 3
    assert repos.news_dirty.enqueued[0]["rows"] == [
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-1",
            "source_watermark_ms": NOW_MS - 1_000,
        },
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-2",
            "source_watermark_ms": NOW_MS - 2_000,
        },
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-3",
            "source_watermark_ms": NOW_MS - 3_000,
        },
    ]


def test_enqueue_projection_dirty_targets_can_scope_brief_input_repair() -> None:
    repos = FakeRepos()

    result = enqueue_projection_dirty_targets(
        repos,
        domain="news",
        execute=True,
        now_ms=NOW_MS,
        projection="brief_input",
        since_ms=NOW_MS - 24 * 60 * 60 * 1000,
    )

    assert result["projection"] == "brief_input"
    assert result["news"]["news_item_targets"] == 2
    assert repos.news_dirty.enqueued[0]["rows"] == [
        {
            "projection_name": "brief_input",
            "target_kind": "news_item",
            "target_id": "news-2",
            "source_watermark_ms": NOW_MS - 2_000,
            "priority": 12,
        },
        {
            "projection_name": "brief_input",
            "target_kind": "news_item",
            "target_id": "news-3",
            "source_watermark_ms": NOW_MS - 3_000,
            "priority": 8,
        },
    ]


class FakeRepos:
    def __init__(self) -> None:
        self.conn = FakeConn()
        self.news_dirty = FakeDirtyRepo()
        self.news_projection_dirty_targets = self.news_dirty


class FakeConn:
    def __init__(self) -> None:
        self.transactions = 0

    def execute(self, sql: str, _params: dict[str, Any] | None = None) -> FakeCursor:
        if "FROM news_items" in sql:
            return FakeCursor(
                [
                    {
                        "news_item_id": "news-1",
                        "published_at_ms": NOW_MS - 1_000,
                        "source_watermark_ms": NOW_MS - 1_000,
                        "lifecycle_status": "processed",
                        "content_class": "other",
                        "content_classification_json": {},
                        "analysis_admission_status": "page_only",
                        "analysis_admission_reason": "provider_evidence_only",
                        "analysis_admission_json": {
                            "status": "page_only",
                            "basis": {"provider_evidence": ["provider_score:95"]},
                        },
                        "analysis_admission_version": "news_analysis_admission_v1",
                        "story_key": "news-story:item:news-1",
                        "story_identity_json": {"story_key": "news-story:item:news-1"},
                        "story_identity_version": "news_story_identity_v1",
                        "provider_type": "rss",
                        "source_domain": "example.com",
                        "source_name": "Example",
                        "source_role": "observed_source",
                        "coverage_tags_json": [],
                        "trust_tier": "standard",
                        "authority_scope_json": {},
                        "provider_signal_json": {},
                        "token_mentions_json": [],
                        "fact_candidates_json": [],
                    },
                    {
                        "news_item_id": "news-2",
                        "published_at_ms": NOW_MS - 2_000,
                        "source_watermark_ms": NOW_MS - 2_000,
                        "lifecycle_status": "processed",
                        "content_class": "exchange_listing",
                        "content_classification_json": {"policy_version": "news_content_classification_v1"},
                        "analysis_admission_status": "admitted",
                        "analysis_admission_reason": "crypto_native_evidence",
                        "analysis_admission_json": {
                            "status": "admitted",
                            "basis": {"crypto_evidence": ["resolved_crypto_target:cex:BTC"]},
                        },
                        "analysis_admission_version": "news_analysis_admission_v1",
                        "story_key": "news-story:item:news-2",
                        "story_identity_json": {"story_key": "news-story:item:news-2"},
                        "story_identity_version": "news_story_identity_v1",
                        "provider_type": "opennews",
                        "source_domain": "6551.io",
                        "source_name": "OpenNews",
                        "source_role": "observed_source",
                        "coverage_tags_json": ["crypto"],
                        "trust_tier": "standard",
                        "authority_scope_json": {},
                        "provider_signal_json": {"source": "provider", "provider": "opennews", "score": 88},
                        "token_mentions_json": [{"resolution_status": "known_symbol", "display_symbol": "BTC"}],
                        "fact_candidates_json": [],
                    },
                    {
                        "news_item_id": "news-3",
                        "published_at_ms": NOW_MS - 3_000,
                        "source_watermark_ms": NOW_MS - 3_000,
                        "lifecycle_status": "processed",
                        "content_class": "other",
                        "content_classification_json": {"policy_version": "news_content_classification_v1"},
                        "analysis_admission_status": "page_only",
                        "analysis_admission_reason": "provider_evidence_only",
                        "analysis_admission_json": {
                            "status": "page_only",
                            "basis": {"provider_evidence": ["provider_score:92"]},
                        },
                        "analysis_admission_version": "news_analysis_admission_v1",
                        "story_key": "news-story:item:news-3",
                        "story_identity_json": {"story_key": "news-story:item:news-3"},
                        "story_identity_version": "news_story_identity_v1",
                        "provider_type": "opennews",
                        "source_domain": "6551.io",
                        "source_name": "OpenNews",
                        "source_role": "observed_source",
                        "coverage_tags_json": ["equities"],
                        "trust_tier": "standard",
                        "authority_scope_json": {},
                        "provider_signal_json": {"source": "provider", "provider": "opennews", "score": 92},
                        "token_mentions_json": [],
                        "fact_candidates_json": [],
                    },
                ]
            )
        if "FROM news_sources" in sql:
            return FakeCursor([{"source_id": "source-1"}, {"source_id": "source-2"}])
        raise AssertionError(f"unexpected SQL: {sql}")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.transactions += 1
        yield


class FakeCursor:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, str]]:
        return list(self.rows)


class FakeDirtyRepo:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, Any]] = []

    def enqueue_targets(
        self,
        rows: list[dict[str, Any]],
        *,
        reason: str,
        now_ms: int,
        commit: bool = True,
        due_at_ms: int | None = None,
    ) -> int:
        del due_at_ms
        self.enqueued.append(
            {
                "rows": [dict(row) for row in rows],
                "reason": reason,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return len(rows)
