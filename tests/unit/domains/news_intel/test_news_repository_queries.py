from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from parallax.domains.news_intel.repositories.news_repository import NewsRepository


def test_page_projection_loader_reads_source_payload_for_claimed_targets() -> None:
    conn = CapturingConnection()
    repo = NewsRepository(conn)

    rows = repo.load_items_for_page_projection(news_item_ids=["news-1"])

    assert rows == []
    assert "WHERE items.news_item_id = ANY(%s::text[])" in conn.sql
    assert "JOIN LATERAL" in conn.sql
    assert "edge_sources.enabled = true" in conn.sql
    assert "'provider_type', source_rep.provider_type" in conn.sql
    assert "'source_quality_status', source_rep.source_quality_status" in conn.sql
    assert "'coverage_tags_json', source_rep.coverage_tags_json" in conn.sql
    assert "news_story_members" not in conn.sql
    assert "news_story_groups" not in conn.sql


def test_brief_target_loader_includes_provider_duplicate_aggregation() -> None:
    conn = CapturingConnection()
    repo = NewsRepository(conn)

    rows = repo.load_items_for_brief_targets(news_item_ids=["news-1"])

    assert rows == []
    assert "edge_summary.duplicate_count" in conn.sql
    assert "'duplicate_count', COALESCE(edge_summary.duplicate_count, 1)" in conn.sql
    assert "'source_ids_json', COALESCE(edge_summary.source_ids_json, '[]'::jsonb)" in conn.sql
    assert "'source_domains_json', COALESCE(edge_summary.source_domains_json, '[]'::jsonb)" in conn.sql
    assert "'provider_article_keys_json', COALESCE(edge_summary.provider_article_keys_json, '[]'::jsonb)" in conn.sql
    assert "edge_sources.enabled = true" in conn.sql
    assert "story_member_rows" not in conn.sql
    assert "news_story_groups AS stories" not in conn.sql


def test_unprocessed_item_loader_selects_provider_article_keys_for_story_identity() -> None:
    conn = CapturingConnection()
    repo = NewsRepository(conn)

    rows = repo.list_unprocessed_items(limit=10, now_ms=1_000, commit=False)

    assert rows == []
    assert "claimed.provider_article_keys_json" in conn.sql
    assert "sources.provider_type" in conn.sql


def test_update_item_analysis_and_story_identity_rejects_unsupported_payload_shape() -> None:
    conn = CapturingConnection()
    repo = NewsRepository(conn)

    try:
        repo.update_item_analysis_and_story_identity(
            news_item_id="news-1",
            admission=object(),
            story_identity={
                "story_key": "news-story:opennews-article:2367422",
                "confidence": "strong",
                "basis": {},
                "version": "news_story_identity_v1",
            },
            now_ms=1_000,
            commit=False,
        )
    except ValueError as exc:
        assert "analysis admission payload" in str(exc)
    else:
        raise AssertionError("expected unsupported admission payload shape to raise")

    assert conn.statements == []


def test_update_item_analysis_and_story_identity_rejects_unsupported_story_identity_shape() -> None:
    conn = CapturingConnection()
    repo = NewsRepository(conn)

    with pytest.raises(ValueError, match="story identity payload"):
        repo.update_item_analysis_and_story_identity(
            news_item_id="news-1",
            admission=_valid_admission_payload(),
            story_identity=object(),
            now_ms=1_000,
            commit=False,
        )

    assert conn.statements == []


@pytest.mark.parametrize(
    ("admission", "story_identity", "match"),
    [
        (
            {"status": "", "reason": "crypto_native_evidence", "basis": {}, "version": "news_analysis_admission_v1"},
            {
                "story_key": "news-story:opennews-article:2367422",
                "confidence": "strong",
                "basis": {"method": "opennews_article_key"},
                "version": "news_story_identity_v1",
            },
            "blank status",
        ),
        (
            {
                "status": "admitted",
                "reason": "crypto_native_evidence",
                "basis": {"crypto_evidence": ["resolved_crypto_target:cex:BTC"]},
                "version": "news_analysis_admission_v1",
            },
            {"story_key": "", "confidence": "strong", "basis": {}, "version": "news_story_identity_v1"},
            "blank story_key",
        ),
    ],
)
def test_update_item_analysis_and_story_identity_rejects_blank_required_fields(
    admission: dict[str, object],
    story_identity: dict[str, object],
    match: str,
) -> None:
    conn = CapturingConnection()
    repo = NewsRepository(conn)

    with pytest.raises(ValueError, match=match):
        repo.update_item_analysis_and_story_identity(
            news_item_id="news-1",
            admission=admission,
            story_identity=story_identity,
            now_ms=1_000,
            commit=False,
        )

    assert conn.statements == []


@pytest.mark.parametrize(
    ("admission", "story_identity", "match"),
    [
        (
            {
                "status": "admitted",
                "reason": "crypto_native_evidence",
                "basis": ["crypto_evidence"],
                "version": "news_analysis_admission_v1",
            },
            {
                "story_key": "news-story:opennews-article:2367422",
                "confidence": "strong",
                "basis": {"method": "opennews_article_key"},
                "version": "news_story_identity_v1",
            },
            "analysis admission payload.*basis must be mapping",
        ),
        (
            {
                "status": "admitted",
                "reason": "crypto_native_evidence",
                "basis": {"crypto_evidence": ["resolved_crypto_target:cex:BTC"]},
                "version": "news_analysis_admission_v1",
            },
            {
                "story_key": "news-story:opennews-article:2367422",
                "confidence": "strong",
                "basis": ["opennews_article_key"],
                "version": "news_story_identity_v1",
            },
            "story identity payload.*basis must be mapping",
        ),
    ],
)
def test_update_item_analysis_and_story_identity_rejects_non_mapping_basis(
    admission: dict[str, object],
    story_identity: dict[str, object],
    match: str,
) -> None:
    conn = CapturingConnection()
    repo = NewsRepository(conn)

    with pytest.raises(ValueError, match=match):
        repo.update_item_analysis_and_story_identity(
            news_item_id="news-1",
            admission=admission,
            story_identity=story_identity,
            now_ms=1_000,
            commit=False,
        )

    assert conn.statements == []


def test_material_duplicate_lock_covers_candidate_window_without_symbol_partition() -> None:
    conn = CapturingConnection()
    repo = NewsRepository(conn)

    repo._lock_material_duplicate_candidate_window(
        source_id="opennews-news",
        material_fingerprint="bitcoin crashes as billions of longs get liquidated",
        published_at_ms=1_200_000,
    )

    lock_keys = [
        json.loads(params[0])
        for sql, params in conn.statements
        if "pg_advisory_xact_lock" in sql and isinstance(params, tuple)
    ]
    assert lock_keys == [
        [
            "news-material-duplicate-v2",
            "opennews-news",
            "bitcoin crashes as billions of longs get liquidated",
            600_000,
        ],
        [
            "news-material-duplicate-v2",
            "opennews-news",
            "bitcoin crashes as billions of longs get liquidated",
            1_200_000,
        ],
        [
            "news-material-duplicate-v2",
            "opennews-news",
            "bitcoin crashes as billions of longs get liquidated",
            1_800_000,
        ],
    ]


def test_edge_remap_cleanup_locks_old_news_item_row_before_delete() -> None:
    conn = CapturingConnection()
    repo = NewsRepository(conn)

    assert repo._lock_news_item_for_edge_remap_cleanup(news_item_id="news-old") is True

    assert "FROM news_items" in conn.sql
    assert "WHERE news_item_id = %s" in conn.sql
    assert "FOR UPDATE" in conn.sql
    assert conn.params == ("news-old",)


def test_upsert_canonical_news_item_wraps_autocommit_connection_in_transaction() -> None:
    conn = TransactionRecordingConnection()
    repo = NewsRepository(conn)
    original = repo.upsert_canonical_news_item

    with patch.object(repo, "upsert_canonical_news_item", return_value={"news_item_id": "news-1"}) as inner_call:
        result = original(
            provider_item_id="provider-1",
            canonical_url="https://example.com/news/1",
            title="Headline",
            fetched_at_ms=1,
            content_hash="content-1",
            title_fingerprint="headline",
            now_ms=2,
            commit=True,
        )

    assert result == {"news_item_id": "news-1"}
    assert conn.events == ["begin", "commit"]
    assert inner_call.call_args.kwargs["commit"] is False
    assert inner_call.call_args.kwargs["provider_item_id"] == "provider-1"


class CapturingConnection:
    def __init__(self) -> None:
        self.sql = ""
        self.params: object = None
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> CapturingCursor:
        self.sql = sql
        self.params = params
        self.statements.append((sql, params))
        return CapturingCursor()


def _valid_admission_payload() -> dict[str, object]:
    return {
        "status": "admitted",
        "reason": "crypto_native_evidence",
        "basis": {"crypto_evidence": ["resolved_crypto_target:cex:BTC"]},
        "version": "news_analysis_admission_v1",
    }


def _valid_story_identity_payload() -> dict[str, object]:
    return {
        "story_key": "news-story:opennews-article:2367422",
        "confidence": "strong",
        "basis": {"method": "opennews_article_key"},
        "version": "news_story_identity_v1",
    }


class CapturingCursor:
    def fetchone(self) -> dict[str, Any]:
        return {"news_item_id": "news-old", "has_edges": False}

    def fetchall(self) -> list[dict[str, Any]]:
        return []


class TransactionRecordingConnection:
    autocommit = True

    def __init__(self) -> None:
        self.events: list[str] = []

    def transaction(self) -> TransactionRecorder:
        return TransactionRecorder(self.events)


class TransactionRecorder:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __enter__(self) -> None:
        self.events.append("begin")

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.events.append("rollback" if exc_type else "commit")
