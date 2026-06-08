from __future__ import annotations

from parallax.domains.news_intel._constants import NEWS_MARKET_SCOPE_VERSION, NEWS_PAGE_PROJECTION_VERSION
from parallax.domains.news_intel.repositories.news_repository import NewsRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_600_000_000
AGENT_ADMISSION_VERSION = "news_item_agent_admission_market_v2"


def test_update_item_agent_admission_persists_without_touching_market_scope(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _seed_processed_news_item(repo, suffix="page-only", primary_scope="us_equity")

        updated = repo.update_item_agent_admission(
            news_item_id=news_item_id,
            admission=_agent_admission_fixture(
                status="eligible",
                reason="provider_score_high",
                representative_news_item_id=news_item_id,
            ),
            now_ms=NOW_MS + 2_000,
        )
        row = repo.get_news_item_detail(news_item_id=news_item_id)
    finally:
        conn.close()

    assert row is not None
    assert updated == 1
    assert row["agent_admission"]["status"] == "eligible"
    assert row["agent_admission"]["reason"] == "provider_score_high"
    assert row["agent_admission"]["version"] == AGENT_ADMISSION_VERSION
    assert row["agent_admission_status"] == "eligible"
    assert row["agent_representative_news_item_id"] == news_item_id
    assert row["agent_admission_computed_at_ms"] == NOW_MS + 2_000
    assert row["market_scope"]["primary"] == "us_equity"


def test_page_row_persists_agent_admission_fields(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _seed_processed_news_item(repo, suffix="page-row", primary_scope="us_equity")
        row = _page_row_fixture(
            news_item_id=news_item_id,
            agent_admission_status="similar_story_covered",
            agent_admission_reason="same_story_representative_exists",
            agent_representative_news_item_id="representative-page-row",
        )

        repo.replace_page_rows_for_items(news_item_ids=[news_item_id], rows=[row])
        listed = repo.list_news_page_rows(limit=10)
    finally:
        conn.close()

    assert listed[0]["agent_admission_status"] == "similar_story_covered"
    assert listed[0]["agent_admission_reason"] == "same_story_representative_exists"
    assert listed[0]["agent_admission"]["status"] == "similar_story_covered"
    assert listed[0]["agent_representative_news_item_id"] == "representative-page-row"


def test_list_agent_admission_repair_candidates_includes_page_only_items_without_score_gate(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        page_only_id = _seed_processed_news_item(
            repo,
            suffix="page-only-high-score",
            provider_score=88,
            primary_scope="us_equity",
        )
        below_threshold_id = _seed_processed_news_item(
            repo,
            suffix="page-only-low-score",
            provider_score=79,
            primary_scope="us_equity",
        )

        candidates = repo.list_agent_admission_repair_candidates(
            since_ms=NOW_MS - 60_000,
            until_ms=NOW_MS + 60_000,
        )
    finally:
        conn.close()

    candidate_ids = [str(candidate["item"]["news_item_id"]) for candidate in candidates]
    assert page_only_id in candidate_ids
    assert below_threshold_id in candidate_ids
    page_only_candidate = next(
        candidate for candidate in candidates if candidate["item"]["news_item_id"] == page_only_id
    )
    low_score_candidate = next(
        candidate for candidate in candidates if candidate["item"]["news_item_id"] == below_threshold_id
    )
    assert page_only_candidate["provider_score"] == 88
    assert low_score_candidate["provider_score"] == 79
    assert page_only_candidate["item"]["market_scope_json"]["primary"] == "us_equity"


def test_load_agent_admission_contexts_exposes_duplicate_provider_article_keys(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        target_id = _seed_processed_news_item(
            repo,
            suffix="provider-evidence-target",
            provider_type="opennews",
            provider_article_id="2511056",
            content_hash="shared-provider-evidence-content",
            published_at_ms=NOW_MS,
        )
        duplicate_id = _seed_processed_news_item(
            repo,
            suffix="provider-evidence-duplicate",
            provider_type="opennews",
            provider_article_id="2511057",
            content_hash="shared-provider-evidence-content",
            published_at_ms=NOW_MS - 1_000,
        )
        repo.update_item_agent_admission(
            news_item_id=duplicate_id,
            admission=_agent_admission_fixture(
                status="eligible",
                reason="eligible",
                representative_news_item_id=duplicate_id,
            ),
            now_ms=NOW_MS + 1_000,
        )

        contexts = repo.load_agent_admission_contexts(news_item_ids=[target_id], now_ms=NOW_MS + 2_000)
    finally:
        conn.close()

    assert len(contexts) == 1
    assert contexts[0]["item"]["provider_article_keys_json"] == ["opennews:2511056"]
    duplicate_candidate = next(
        candidate
        for candidate in contexts[0]["exact_duplicate_candidates"]
        if candidate["news_item_id"] == duplicate_id
    )
    assert duplicate_candidate["provider_article_keys"] == ["opennews:2511057"]


def test_load_agent_admission_contexts_excludes_unready_exact_duplicate_representatives(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        target_id = _seed_processed_news_item(
            repo,
            suffix="provider-evidence-ready-target",
            provider_type="opennews",
            provider_article_id="2511058",
            content_hash="shared-unready-duplicate-content",
            published_at_ms=NOW_MS,
        )
        duplicate_id = _seed_processed_news_item(
            repo,
            suffix="provider-evidence-unready-duplicate",
            provider_type="opennews",
            provider_article_id="2511059",
            content_hash="shared-unready-duplicate-content",
            published_at_ms=NOW_MS - 1_000,
        )

        contexts = repo.load_agent_admission_contexts(news_item_ids=[target_id], now_ms=NOW_MS + 2_000)
    finally:
        conn.close()

    duplicate_candidate_ids = {
        str(candidate["news_item_id"]) for candidate in contexts[0]["exact_duplicate_candidates"]
    }
    assert duplicate_id not in duplicate_candidate_ids


def test_load_agent_admission_contexts_orders_story_representatives_by_quality_before_recency(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        target_id = _seed_processed_news_item(
            repo,
            suffix="story-target",
            provider_score=91,
            story_key="story:shared-quality",
            published_at_ms=NOW_MS,
        )
        representative_id = _seed_processed_news_item(
            repo,
            suffix="story-representative",
            provider_score=94,
            source_role="specialist_media",
            trust_tier="high",
            story_key="story:shared-quality",
            published_at_ms=NOW_MS - 20_000,
        )
        newer_aggregator_id = _seed_processed_news_item(
            repo,
            suffix="story-newer-aggregator",
            provider_score=81,
            source_role="aggregator",
            trust_tier="standard",
            story_key="story:shared-quality",
            published_at_ms=NOW_MS - 1_000,
        )
        repo.update_item_agent_admission(
            news_item_id=representative_id,
            admission=_agent_admission_fixture(
                status="eligible",
                reason="eligible",
                representative_news_item_id=representative_id,
            ),
            now_ms=NOW_MS + 1_000,
        )

        contexts = repo.load_agent_admission_contexts(news_item_ids=[target_id], now_ms=NOW_MS + 2_000)
    finally:
        conn.close()

    story_candidate_ids = [str(candidate["news_item_id"]) for candidate in contexts[0]["story_candidates"]]
    assert story_candidate_ids[:2] == [representative_id, newer_aggregator_id]


def _seed_processed_news_item(
    repo: NewsRepository,
    *,
    suffix: str = "1",
    primary_scope: str = "crypto",
    provider_score: int = 88,
    source_enabled: bool = True,
    published_at_ms: int = NOW_MS,
    provider_type: str = "rss",
    provider_article_id: str | None = None,
    content_hash: str | None = None,
    canonical_url: str | None = None,
    source_role: str = "observed_source",
    trust_tier: str = "standard",
    story_key: str | None = None,
) -> str:
    source_id = f"agent-admission-source-{suffix}"
    source_item_key = f"agent-admission-guid-{suffix}"
    item_url = canonical_url or f"https://example.com/{source_item_key}"
    repo.upsert_source(
        source_id=source_id,
        provider_type=provider_type,
        feed_url=f"https://example.com/{suffix}.xml",
        source_domain="example.com",
        source_name="Example",
        source_role=source_role,
        trust_tier=trust_tier,
        enabled=source_enabled,
        refresh_interval_seconds=300,
        now_ms=NOW_MS,
    )
    fetch_run_id = repo.start_fetch_run(source_id=source_id, started_at_ms=NOW_MS)
    provider = repo.upsert_provider_item(
        source_id=source_id,
        fetch_run_id=fetch_run_id,
        source_item_key=source_item_key,
        canonical_url=item_url,
        payload_hash=f"payload-hash-{suffix}",
        raw_payload_json={"title": f"Market item {suffix}"},
        provider_article_id=provider_article_id,
        fetched_at_ms=NOW_MS,
    )
    news = repo.upsert_canonical_news_item(
        provider_item_id=provider["provider_item_id"],
        canonical_url=item_url,
        title=f"Market item {suffix}",
        summary="Provider-scored market news.",
        body_text="Provider-scored market news.",
        language="en",
        published_at_ms=published_at_ms,
        fetched_at_ms=NOW_MS,
        content_hash=content_hash or f"content-hash-{suffix}",
        title_fingerprint=f"market item {suffix}",
        now_ms=NOW_MS,
        provider_signal={"source": "provider", "status": "ready", "score": provider_score},
    )
    news_item_id = str(news["news_item_id"])
    repo.mark_item_processed(news_item_id=news_item_id, processed_at_ms=NOW_MS)
    repo.update_item_market_scope_and_story_identity(
        news_item_id=news_item_id,
        market_scope=_market_scope_fixture(primary=primary_scope),
        story_identity={
            "story_key": story_key or f"story:{suffix}",
            "confidence": "weak",
            "basis": {"test": True},
            "version": "news_story_identity_v1",
        },
        now_ms=NOW_MS,
    )
    return news_item_id


def _agent_admission_fixture(
    *,
    status: str = "eligible",
    reason: str = "provider_score_high",
    representative_news_item_id: str = "",
) -> dict[str, object]:
    return {
        "status": status,
        "reason": reason,
        "basis": {"provider_score": 88},
        "version": AGENT_ADMISSION_VERSION,
        "representative_news_item_id": representative_news_item_id,
    }


def _page_row_fixture(
    *,
    news_item_id: str,
    agent_admission_status: str = "eligible",
    agent_admission_reason: str = "provider_score_high",
    agent_representative_news_item_id: str = "",
) -> dict[str, object]:
    return {
        "row_id": f"row-{news_item_id}",
        "news_item_id": news_item_id,
        "latest_at_ms": NOW_MS,
        "lifecycle_status": "processed",
        "headline": "Market item",
        "summary": "Provider-scored market news.",
        "source_domain": "example.com",
        "canonical_url": f"https://example.com/{news_item_id}",
        "token_lanes_json": [],
        "fact_lanes_json": [],
        "source_json": {"source_id": "agent-admission-source-page-row"},
        "agent_brief_json": {"status": "pending"},
        "agent_status": "pending",
        "agent_brief_computed_at_ms": None,
        "computed_at_ms": NOW_MS,
        "projection_version": NEWS_PAGE_PROJECTION_VERSION,
        "market_scope": _market_scope_fixture(primary="us_equity"),
        "agent_admission_status": agent_admission_status,
        "agent_admission_reason": agent_admission_reason,
        "agent_admission": {
            "status": agent_admission_status,
            "reason": agent_admission_reason,
            "version": AGENT_ADMISSION_VERSION,
        },
        "agent_representative_news_item_id": agent_representative_news_item_id or news_item_id,
    }


def _market_scope_fixture(*, primary: str = "crypto") -> dict[str, object]:
    return {
        "scope": [primary],
        "primary": primary,
        "status": "classified",
        "reason": f"{primary}_context",
        "basis": {"test": True},
        "version": NEWS_MARKET_SCOPE_VERSION,
    }
