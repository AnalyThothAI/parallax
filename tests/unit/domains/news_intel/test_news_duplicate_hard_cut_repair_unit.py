from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from parallax.domains.news_intel.repositories import news_duplicate_hard_cut_repair_repository as repair


def test_execute_guard_runs_before_candidate_scans(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = RecordingConnection()
    repos = SimpleNamespace(conn=conn, news=object(), news_projection_dirty_targets=object())

    monkeypatch.setattr(
        repair,
        "news_intel_hard_cut_runtime_guard",
        lambda conn, *, now_ms: {
            "active_state": {"running_fetch_runs": 1, "active_dirty_leases": []},
            "advisory_locks": {},
            "blockers": [{"type": "running_fetch_runs", "count": 1}],
        },
    )

    def fail_scan(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("candidate scans must not run before execute guard")

    monkeypatch.setattr(repair, "_generic_blocked_opennews_rewrite_candidates", fail_scan)
    monkeypatch.setattr(repair, "_hard_public_url_groups", fail_scan)
    monkeypatch.setattr(repair, "_opennews_material_duplicate_groups", fail_scan)

    with pytest.raises(repair.NewsDuplicateHardCutRepairAbort):
        repair.repair_news_duplicates_hard_cut(repos, limit=10, execute=True, now_ms=100)

    assert conn.events == ["begin", "rollback"]


def test_generic_rewrite_candidate_scan_continues_past_allowed_rows_until_limit() -> None:
    conn = PagedProviderConnection(
        [
            {
                "provider_item_id": "provider-allowed",
                "provider_article_id": "allowed-1",
                "provider_article_key": "opennews:allowed-1",
                "canonical_url": "https://www.coindesk.com/markets/2026/06/03/allowed-article",
                "news_item_id": "news-allowed",
            },
            {
                "provider_item_id": "provider-blocked",
                "provider_article_id": "blocked-1",
                "provider_article_key": "opennews:blocked-1",
                "canonical_url": "https://www.coindesk.com/news/index.html",
                "news_item_id": "news-blocked",
            },
        ]
    )

    candidates = repair._generic_blocked_opennews_rewrite_candidates(conn, limit=1)

    assert len(candidates) == 1
    assert candidates[0].provider_item_id == "provider-blocked"
    assert candidates[0].fallback_url == "opennews://item/blocked-1"
    assert conn.offsets == [0, 1]


def test_hard_public_url_scan_continues_past_non_candidate_rows_until_group_limit() -> None:
    duplicate_url = "https://www.coindesk.com/markets/2026/06/03/btc-liquidations-hard-url"
    conn = PagedProviderConnection(
        [
            {
                "news_item_id": "single-hard",
                "canonical_url": "https://www.coindesk.com/markets/2026/06/03/single-hard-url",
                "canonical_item_key": "canonical-url:https://www.coindesk.com/markets/2026/06/03/single-hard-url",
                "dedup_key_kind": "canonical_url",
                "provider_item_ids": ["provider-single"],
            },
            {
                "news_item_id": "old-hard-a",
                "canonical_url": duplicate_url,
                "canonical_item_key": "provider:opennews:hard-a",
                "dedup_key_kind": "provider_article_id",
                "provider_item_ids": ["provider-hard-a"],
            },
            {
                "news_item_id": "old-hard-b",
                "canonical_url": duplicate_url,
                "canonical_item_key": "provider:opennews:hard-b",
                "dedup_key_kind": "provider_article_id",
                "provider_item_ids": ["provider-hard-b"],
            },
        ]
    )

    groups = repair._hard_public_url_groups(conn, limit=1)

    assert len(groups) == 1
    assert groups[0].group_key == f"canonical-url:{duplicate_url}"
    assert set(groups[0].news_item_ids) == {"old-hard-a", "old-hard-b"}
    assert set(groups[0].provider_item_ids) == {"provider-hard-a", "provider-hard-b"}
    assert conn.offsets == [0, 1, 2, 3]


def test_material_duplicate_scan_continues_past_non_candidate_rows_until_group_limit() -> None:
    title = "Ethereum treasury company adds more ETH after financing round"
    conn = PagedProviderConnection(
        [
            {
                "news_item_id": "single-material",
                "source_id": "opennews-news",
                "canonical_url": "opennews://item/single-material",
                "canonical_item_key": "provider:opennews:single-material",
                "dedup_key_kind": "provider_article_id",
                "title": "Solana foundation publishes routine weekly ecosystem update",
                "published_at_ms": 1_779_000_000_000,
                "provider_token_impacts_json": [{"symbol": "SOL"}],
                "provider_item_ids": ["provider-single-material"],
            },
            {
                "news_item_id": "old-material-a",
                "source_id": "opennews-news",
                "canonical_url": "opennews://item/material-a",
                "canonical_item_key": "provider:opennews:material-a",
                "dedup_key_kind": "provider_article_id",
                "title": title,
                "published_at_ms": 1_779_000_001_000,
                "provider_token_impacts_json": [{"symbol": "ETH"}],
                "provider_item_ids": ["provider-material-a"],
            },
            {
                "news_item_id": "old-material-b",
                "source_id": "opennews-news",
                "canonical_url": "opennews://item/material-b",
                "canonical_item_key": "provider:opennews:material-b",
                "dedup_key_kind": "provider_article_id",
                "title": f"COINDESK: {title}",
                "published_at_ms": 1_779_000_002_000,
                "provider_token_impacts_json": [{"symbol": "ETH"}],
                "provider_item_ids": ["provider-material-b"],
            },
        ]
    )

    groups = repair._opennews_material_duplicate_groups(conn, limit=1)

    assert len(groups) == 1
    assert set(groups[0].news_item_ids) == {"old-material-a", "old-material-b"}
    assert set(groups[0].provider_item_ids) == {"provider-material-a", "provider-material-b"}
    assert conn.offsets == [0, 1, 2, 3]


def test_repair_candidates_applies_material_limit_after_hard_provider_exclusion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hard_title = "Bitcoin liquidations pressure major crypto markets"
    material_title = "Ethereum treasury company adds more ETH after financing round"
    conn = PagedProviderConnection(
        [
            {
                "news_item_id": "old-hard-a",
                "source_id": "opennews-news",
                "canonical_url": "opennews://item/hard-a",
                "canonical_item_key": "provider:opennews:hard-a",
                "dedup_key_kind": "provider_article_id",
                "title": hard_title,
                "published_at_ms": 1_779_000_001_000,
                "provider_token_impacts_json": [{"symbol": "BTC"}],
                "provider_item_ids": ["provider-hard-a"],
            },
            {
                "news_item_id": "old-hard-b",
                "source_id": "opennews-news",
                "canonical_url": "opennews://item/hard-b",
                "canonical_item_key": "provider:opennews:hard-b",
                "dedup_key_kind": "provider_article_id",
                "title": hard_title,
                "published_at_ms": 1_779_000_002_000,
                "provider_token_impacts_json": [{"symbol": "BTC"}],
                "provider_item_ids": ["provider-hard-b"],
            },
            {
                "news_item_id": "old-material-a",
                "source_id": "opennews-news",
                "canonical_url": "opennews://item/material-a",
                "canonical_item_key": "provider:opennews:material-a",
                "dedup_key_kind": "provider_article_id",
                "title": material_title,
                "published_at_ms": 1_779_000_003_000,
                "provider_token_impacts_json": [{"symbol": "ETH"}],
                "provider_item_ids": ["provider-material-a"],
            },
            {
                "news_item_id": "old-material-b",
                "source_id": "opennews-news",
                "canonical_url": "opennews://item/material-b",
                "canonical_item_key": "provider:opennews:material-b",
                "dedup_key_kind": "provider_article_id",
                "title": f"COINDESK: {material_title}",
                "published_at_ms": 1_779_000_004_000,
                "provider_token_impacts_json": [{"symbol": "ETH"}],
                "provider_item_ids": ["provider-material-b"],
            },
        ]
    )
    monkeypatch.setattr(repair, "_generic_blocked_opennews_rewrite_candidates", lambda conn, *, limit: [])
    monkeypatch.setattr(
        repair,
        "_hard_public_url_groups",
        lambda conn, *, limit: [
            repair._RepairGroup(
                group_key="canonical-url:https://example.com/hard",
                news_item_ids=("old-hard-a", "old-hard-b"),
                provider_item_ids=("provider-hard-a", "provider-hard-b"),
            )
        ],
    )

    candidates = repair._repair_candidates(conn, limit=1)

    assert len(candidates.material_groups) == 1
    assert set(candidates.material_groups[0].news_item_ids) == {"old-material-a", "old-material-b"}
    assert set(candidates.material_groups[0].provider_item_ids) == {"provider-material-a", "provider-material-b"}
    assert conn.offsets == [0, 1, 2, 3, 4]


class RecordingConnection:
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


class PagedProviderConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.offsets: list[int] = []

    def execute(self, sql: str, params: object = None) -> PagedCursor:
        _limit, offset = params
        self.offsets.append(int(offset))
        return PagedCursor(self.rows[int(offset) : int(offset) + 1])


class PagedCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows
