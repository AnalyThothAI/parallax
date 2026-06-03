from __future__ import annotations

from typing import Any

from parallax.domains.news_intel.repositories.news_repository import NewsRepository
from parallax.domains.news_intel.types.news_item_brief import NewsContextTargetRef

_FORBIDDEN_RESEARCH_SQL = (
    "token_radar",
    "pulse_candidates",
    "market_ticks",
    "asset_identity_current",
    "news_story_groups",
    "news_story_members",
    "news_context_items",
    "raw_payload_json",
    "provider_item_id",
    "provider_article_key",
    "source_item_key",
    "feed_url",
    "sync_cursor",
    "credential",
    "secret",
)


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


def test_research_reads_are_select_only_and_avoid_forbidden_tables_and_fields() -> None:
    calls = (
        (
            "get_news_observation_history",
            {"news_item_id": "news-1"},
        ),
        (
            "search_news_archive",
            {
                "current_news_item_id": "news-1",
                "query_terms": ["ETF"],
                "symbols": ["SOL"],
                "window_hours": 168,
                "match_modes": ["title", "token", "fact", "source_title"],
                "limit": 8,
                "now_ms": 1_779_000_000_000,
            },
        ),
        (
            "get_source_quality_context_for_item",
            {"news_item_id": "news-1"},
        ),
        (
            "get_target_news_context",
            {
                "current_news_item_id": "news-1",
                "target_refs": [
                    NewsContextTargetRef(target_type="cex_token", target_id="binance:SOL", display_symbol="SOL")
                ],
                "symbol_fallbacks": ["SOL"],
                "window_hours": 72,
                "limit": 12,
                "now_ms": 1_779_000_000_000,
            },
        ),
        (
            "get_fact_context",
            {"news_item_id": "news-1"},
        ),
    )

    for method_name, kwargs in calls:
        conn = CapturingConnection()
        repo = NewsRepository(conn)

        result = getattr(repo, method_name)(**kwargs)

        assert result in ([], {}) or isinstance(result, dict | list)
        sql = conn.sql.lower()
        assert sql.lstrip().startswith(("select", "with")), method_name
        assert "insert " not in sql
        assert "update " not in sql
        assert "delete " not in sql
        assert "notify " not in sql
        assert "pg_advisory" not in sql
        assert conn.commit_count == 0
        for forbidden in _FORBIDDEN_RESEARCH_SQL:
            assert forbidden not in sql, method_name


def test_archive_search_uses_bounded_union_branches_and_excludes_current_item() -> None:
    conn = CapturingConnection()
    repo = NewsRepository(conn)

    rows = repo.search_news_archive(
        current_news_item_id="news-current",
        query_terms=["SOL ETF"],
        symbols=["SOL"],
        window_hours=999,
        match_modes=["title", "token", "fact", "source_title", "unknown"],
        limit=99,
        now_ms=1_779_000_000_000,
    )

    assert rows == []
    sql = conn.sql.lower()
    assert "title_branch" in sql
    assert "token_branch" in sql
    assert "fact_branch" in sql
    assert "source_title_branch" in sql
    assert sql.count("union all") >= 3
    assert "recent_items as" not in sql
    assert "lower(items.title) like" not in sql
    assert "items.title ilike" in sql
    token_branch = sql[sql.index("token_branch") : sql.index("fact_branch")]
    fact_branch = sql[sql.index("fact_branch") : sql.index("source_title_branch")]
    assert token_branch.index("from news_token_mentions as mentions") < token_branch.index(
        "join news_items as items"
    )
    assert fact_branch.index("from news_fact_candidates as facts") < fact_branch.index(
        "join news_items as items"
    )
    assert "items.news_item_id <> %s" in sql
    assert "body_text" not in sql
    assert "raw_payload_json" not in sql
    assert "current_news_item_id" not in sql
    assert conn.params is not None
    assert "news-current" in _flatten_params(conn.params)


def test_archive_search_defaults_empty_match_modes_to_all_allowed_branches() -> None:
    conn = CapturingConnection()
    repo = NewsRepository(conn)

    repo.search_news_archive(
        current_news_item_id="news-current",
        query_terms=["ETF"],
        symbols=["SOL"],
        window_hours=168,
        match_modes=[],
        limit=8,
        now_ms=1_779_000_000_000,
    )

    params = _flatten_params(conn.params)
    assert [params[index] for index in (2, 6, 10, 14)] == [True, True, True, True]


def test_target_context_exact_refs_use_index_led_mentions_branches() -> None:
    conn = CapturingConnection()
    repo = NewsRepository(conn)

    rows = repo.get_target_news_context(
        current_news_item_id="news-current",
        target_refs=[{"target_type": "cex_token", "target_id": "binance:SOL", "display_symbol": "SOL"}],
        symbol_fallbacks=["SOL"],
        window_hours=72,
        limit=12,
        now_ms=1_779_000_000_000,
    )

    assert rows == {
        "counts": {"total": 0, "exact_target": 0, "symbol_heuristic": 0},
        "top_items": [],
        "latest_items": [],
        "source_domain_count": 0,
        "high_score_count": 0,
        "matching_basis": [],
        "truncated": False,
        "result_basis": "",
        "evidence_refs": [],
    }
    sql = conn.sql.lower()
    assert "recent_items as" not in sql
    assert "mentions.target_type" in sql
    assert "mentions.target_id" in sql
    assert "exact_ref_matches" in sql
    assert "symbol_fallback_matches" in sql
    exact_branch = sql[sql.index("exact_ref_matches") : sql.index("symbol_fallback_matches")]
    assert exact_branch.index("from news_token_mentions as mentions") < exact_branch.index("join exact_refs")
    assert exact_branch.index("join exact_refs") < exact_branch.index("join news_items as items")
    fallback_branch = sql[sql.index("symbol_fallback_matches") : sql.index("matched_rows")]
    assert fallback_branch.index("from news_token_mentions as mentions") < fallback_branch.index(
        "join fallback_symbols"
    )
    assert fallback_branch.index("join fallback_symbols") < fallback_branch.index("join news_items as items")
    assert fallback_branch.index("items.published_at_ms >=") > fallback_branch.index("join news_items as items")
    assert "'symbol_heuristic'" in sql
    assert "display_symbol" in sql


def test_research_queries_match_index_support_expressions() -> None:
    archive_conn = CapturingConnection()
    repo = NewsRepository(archive_conn)

    repo.search_news_archive(
        current_news_item_id="news-current",
        query_terms=["ETF"],
        symbols=["SOL"],
        window_hours=168,
        match_modes=["token", "fact"],
        limit=8,
        now_ms=1_779_000_000_000,
    )

    archive_sql = archive_conn.sql.lower()
    assert "upper(coalesce(mentions.display_symbol, mentions.observed_symbol, '')) = symbols.symbol" in archive_sql
    assert "facts.claim ilike '%%' || terms.term || '%%'" in archive_sql
    assert "facts.validation_status <> 'rejected'" in archive_sql

    target_conn = CapturingConnection()
    repo = NewsRepository(target_conn)
    repo.get_target_news_context(
        current_news_item_id="news-current",
        target_refs=[{"target_type": "cex_token", "target_id": "binance:SOL", "display_symbol": "SOL"}],
        symbol_fallbacks=["ARB"],
        window_hours=72,
        limit=12,
        now_ms=1_779_000_000_000,
    )

    target_sql = target_conn.sql.lower()
    fallback_branch = target_sql[target_sql.index("symbol_fallback_matches") : target_sql.index("matched_rows")]
    assert "upper(coalesce(mentions.display_symbol, mentions.observed_symbol, '')) = symbols.symbol" in fallback_branch


def test_source_quality_context_is_targeted_to_item_sources() -> None:
    conn = CapturingConnection()
    repo = NewsRepository(conn)

    result = repo.get_source_quality_context_for_item(news_item_id="news-1")

    assert result == {}
    sql = conn.sql.lower()
    assert "news_source_quality_rows" in sql
    assert "news_item_observation_edges" in sql
    assert "where edges.news_item_id = %s" in sql
    assert "multi_source_confirmed" not in sql
    assert "independent_source_confirmed" not in sql


class CapturingConnection:
    def __init__(self) -> None:
        self.sql = ""
        self.params: object = None
        self.commit_count = 0

    def execute(self, sql: str, params: object = None) -> CapturingCursor:
        self.sql = sql
        self.params = params
        return CapturingCursor()

    def commit(self) -> None:
        self.commit_count += 1


class CapturingCursor:
    def fetchall(self) -> list[dict[str, Any]]:
        return []

    def fetchone(self) -> dict[str, Any] | None:
        return None


def _flatten_params(params: object) -> list[object]:
    if isinstance(params, dict):
        return [value for item in params.items() for value in _flatten_params(item)]
    if isinstance(params, list | tuple):
        flattened: list[object] = []
        for item in params:
            flattened.extend(_flatten_params(item))
        return flattened
    return [params]
