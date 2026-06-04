from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.news_intel._constants import (
    NEWS_ITEM_BRIEF_GUARDRAIL_VERSION,
    NEWS_ITEM_BRIEF_PROMPT_VERSION,
    NEWS_ITEM_BRIEF_SCHEMA_VERSION,
    NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
    NEWS_PAGE_PROJECTION_VERSION,
)
from parallax.domains.news_intel.repositories.news_repository import NewsRepository
from parallax.domains.news_intel.services.news_duplicate_hard_cut_repair import (
    NewsDuplicateHardCutRepairAbort,
    repair_news_duplicates_hard_cut,
)
from parallax.domains.news_intel.services.news_intel_hard_cut_cleanup import NEWS_WORKER_ADVISORY_LOCK_KEYS
from parallax.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_BRIEF_AGENT_NAME,
    NEWS_ITEM_BRIEF_LANE,
    NEWS_ITEM_BRIEF_WORKFLOW_NAME,
)
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000


def test_repair_news_duplicates_dry_run_reports_candidates_without_mutation(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        repos = _seed_repair_fixture(conn)
        before = _repair_state(conn)

        result = repair_news_duplicates_hard_cut(repos, limit=20, execute=False, now_ms=NOW_MS + 10_000)

        after = _repair_state(conn)
    finally:
        conn.close()

    assert result["mode"] == "dry_run"
    assert result["hard_url_groups_repaired"] == 0
    assert result["generic_urls_rewritten"] == 0
    assert result["material_duplicate_groups_repaired"] == 0
    assert result["candidate_hard_url_groups"] == 1
    assert result["candidate_generic_urls"] == 1
    assert result["candidate_material_duplicate_groups"] == 1
    assert before == after


def test_repair_news_duplicates_execute_merges_rewrites_and_requeues_survivors(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        repos = _seed_repair_fixture(conn)

        result = repair_news_duplicates_hard_cut(repos, limit=20, execute=True, now_ms=NOW_MS + 10_000)

        rows = conn.execute(
            """
            SELECT news_item_id, canonical_item_key, canonical_url, duplicate_observation_count,
                   provider_article_keys_json
              FROM news_items
             ORDER BY canonical_url, news_item_id
            """
        ).fetchall()
        edges = conn.execute(
            """
            SELECT provider_item_id, news_item_id, match_type
              FROM news_item_observation_edges
             ORDER BY provider_item_id
            """
        ).fetchall()
        hard_rep = conn.execute(
            """
            SELECT news_item_id
              FROM news_items
             WHERE canonical_item_key = %s
            """,
            ("canonical-url:https://www.coindesk.com/markets/2026/06/03/btc-liquidations-hard-url",),
        ).fetchone()
        material_rep = conn.execute(
            """
            SELECT news_item_id
              FROM news_items
             WHERE canonical_item_key = %s
            """,
            ("canonical-url:https://www.coindesk.com/markets/2026/06/03/eth-treasury-material",),
        ).fetchone()
        agent_runs = conn.execute(
            """
            SELECT run_id, news_item_id, trace_metadata_json
              FROM news_item_agent_runs
             ORDER BY run_id
            """
        ).fetchall()
        briefs = conn.execute(
            """
            SELECT news_item_id, agent_run_id, brief_json
              FROM news_item_agent_briefs
             ORDER BY news_item_id
            """
        ).fetchall()
        dirty_targets = conn.execute(
            """
            SELECT projection_name, target_id, dirty_reason, leased_until_ms, lease_owner, attempt_count
              FROM news_projection_dirty_targets
             ORDER BY projection_name, target_id
            """
        ).fetchall()
        blocked_provider = conn.execute(
            """
            SELECT canonical_url, raw_payload_json
              FROM news_provider_items
             WHERE provider_article_id = 'live-1'
            """
        ).fetchone()
        old_item_count = conn.execute(
            """
            SELECT COUNT(*) AS count
              FROM news_items
             WHERE news_item_id = ANY(%s::text[])
            """,
            (["old-hard-a", "old-hard-b", "old-material-fallback"],),
        ).fetchone()["count"]
        old_page_rows = conn.execute(
            """
            SELECT COUNT(*) AS count
              FROM news_page_rows
             WHERE news_item_id = ANY(%s::text[])
            """,
            (["old-hard-b", "old-material-fallback"],),
        ).fetchone()["count"]
    finally:
        conn.close()

    assert result["mode"] == "execute"
    assert result["hard_url_groups_repaired"] == 1
    assert result["generic_urls_rewritten"] == 1
    assert result["material_duplicate_groups_repaired"] == 1
    assert result["edges_remapped"] >= 2
    assert result["zero_edge_items_deleted"] >= 3
    assert result["page_rows_deleted"] >= 1
    assert result["stale_dirty_targets_deleted"] >= 2
    assert result["agent_audit_rows_remapped"] >= 2
    assert result["dirty_targets_enqueued"] >= 4
    assert old_item_count == 0
    assert old_page_rows == 0
    assert hard_rep is not None
    assert material_rep is not None
    assert dict(blocked_provider) == {
        "canonical_url": "opennews://item/live-1",
        "raw_payload_json": {
            "id": "live-1",
            "link": "https://www.coindesk.com/news/index.html",
            "opennews_method": "news",
            "provider_article_id": "live-1",
        },
    }
    assert all(row["canonical_item_key"].startswith(("canonical-url:", "provider:opennews:")) for row in rows)
    hard_edge_item_ids = {
        row["news_item_id"] for row in edges if row["provider_item_id"] in {"provider-hard-a", "provider-hard-b"}
    }
    material_edge_item_ids = {
        row["news_item_id"]
        for row in edges
        if row["provider_item_id"] in {"provider-material-public", "provider-material-fallback"}
    }
    assert hard_edge_item_ids == {hard_rep["news_item_id"]}
    assert material_edge_item_ids == {material_rep["news_item_id"]}
    assert [dict(row) for row in agent_runs] == [
        {
            "run_id": "run-old-hard-b",
            "news_item_id": hard_rep["news_item_id"],
            "trace_metadata_json": {
                "attempt": 1,
                "news_item_remap_reason": "canonical_news_item_merge",
                "remapped_from_news_item_id": "old-hard-b",
                "remapped_to_news_item_id": hard_rep["news_item_id"],
                "remapped_at_ms": NOW_MS + 10_000,
            },
        }
    ]
    assert [dict(row) for row in briefs] == [
        {
            "news_item_id": hard_rep["news_item_id"],
            "agent_run_id": "run-old-hard-b",
            "brief_json": {"summary_zh": "历史重复项上的 brief 必须迁到代表 item。"},
        }
    ]
    assert {row["target_id"] for row in dirty_targets}.isdisjoint({"old-hard-b", "old-material-fallback"})
    assert all(row["leased_until_ms"] is None and row["lease_owner"] is None for row in dirty_targets)
    assert all(row["attempt_count"] == 0 for row in dirty_targets)


def test_repair_news_duplicates_execute_aborts_when_news_runtime_is_active(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        repos = _seed_repair_fixture(conn)
        repos.news.start_fetch_run(source_id="opennews-news", started_at_ms=NOW_MS + 20_000)
        before = _repair_state(conn)

        try:
            repair_news_duplicates_hard_cut(repos, limit=20, execute=True, now_ms=NOW_MS + 20_001)
        except NewsDuplicateHardCutRepairAbort as exc:
            error = str(exc)
        else:  # pragma: no cover - assertion path
            raise AssertionError("repair should abort while a News fetch run is active")

        after = _repair_state(conn)
    finally:
        conn.close()

    assert "running_fetch_runs" in error
    assert before == after


def test_repair_news_duplicates_execute_aborts_when_dirty_target_is_leased(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        repos = _seed_repair_fixture(conn)
        conn.execute(
            """
            UPDATE news_projection_dirty_targets
               SET leased_until_ms = %s,
                   lease_owner = 'news-page-worker'
             WHERE projection_name = 'page'
               AND target_id = 'old-hard-b'
            """,
            (NOW_MS + 30_000,),
        )
        conn.commit()
        before = _repair_state(conn)

        try:
            repair_news_duplicates_hard_cut(repos, limit=20, execute=True, now_ms=NOW_MS + 20_001)
        except NewsDuplicateHardCutRepairAbort as exc:
            error = str(exc)
        else:  # pragma: no cover - assertion path
            raise AssertionError("repair should abort while a News dirty target is leased")

        after = _repair_state(conn)
    finally:
        conn.close()

    assert "active_dirty_leases" in error
    assert before == after


def test_repair_news_duplicates_execute_aborts_when_worker_advisory_lock_is_unavailable(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    holder = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    lock_tx = holder.transaction()
    try:
        repos = _seed_repair_fixture(conn)
        lock_tx.__enter__()
        holder.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (NEWS_WORKER_ADVISORY_LOCK_KEYS["news_fetch"],),
        )
        before = _repair_state(conn)

        try:
            repair_news_duplicates_hard_cut(repos, limit=20, execute=True, now_ms=NOW_MS + 20_001)
        except NewsDuplicateHardCutRepairAbort as exc:
            error = str(exc)
        else:  # pragma: no cover - assertion path
            raise AssertionError("repair should abort when a News worker advisory lock is unavailable")

        after = _repair_state(conn)
    finally:
        lock_tx.__exit__(None, None, None)
        holder.close()
        conn.close()

    assert "advisory_lock_unavailable" in error
    assert before == after


def _seed_repair_fixture(conn):
    migrate(conn)
    repos = repositories_for_connection(conn)
    repo = repos.news
    repo.upsert_source(
        source_id="opennews-news",
        provider_type="opennews",
        feed_url="opennews://news",
        source_domain="6551.io",
        source_name="OpenNews",
        refresh_interval_seconds=60,
        now_ms=NOW_MS,
    )

    hard_url = "https://www.coindesk.com/markets/2026/06/03/btc-liquidations-hard-url"
    hard_a = _insert_provider(repo, provider_item_id="provider-hard-a", article_id="hard-a", canonical_url=hard_url)
    hard_b = _insert_provider(repo, provider_item_id="provider-hard-b", article_id="hard-b", canonical_url=hard_url)
    _insert_historical_item(
        conn,
        provider=hard_a,
        news_item_id="old-hard-a",
        canonical_url=hard_url,
        canonical_item_key="provider:opennews:hard-a",
        dedup_key_kind="provider_article_id",
        title="Bitcoin liquidations pressure major crypto markets",
        published_at_ms=NOW_MS,
        token_impacts=[{"symbol": "BTC", "signal": "short", "score": 86}],
    )
    _insert_historical_item(
        conn,
        provider=hard_b,
        news_item_id="old-hard-b",
        canonical_url=hard_url,
        canonical_item_key="provider:opennews:hard-b",
        dedup_key_kind="provider_article_id",
        title="Bitcoin liquidations pressure major crypto markets",
        published_at_ms=NOW_MS + 1,
        token_impacts=[{"symbol": "BTC", "signal": "short", "score": 86}],
    )
    _insert_agent_run(repo, news_item_id="old-hard-b", run_id="run-old-hard-b")
    repo.upsert_news_item_agent_brief(
        news_item_id="old-hard-b",
        agent_run_id="run-old-hard-b",
        status="ready",
        direction="bearish",
        decision_class="driver",
        brief_json={"summary_zh": "历史重复项上的 brief 必须迁到代表 item。"},
        input_hash="input-brief-1",
        artifact_version_hash="artifact-brief-1",
        prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
        schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
        validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
        computed_at_ms=NOW_MS + 100,
        created_at_ms=NOW_MS + 100,
        updated_at_ms=NOW_MS + 100,
    )
    repos.news_projection_dirty_targets.enqueue_targets(
        [
            {
                "projection_name": "brief_input",
                "target_kind": "news_item",
                "target_id": "old-hard-b",
                "source_watermark_ms": NOW_MS,
                "priority": 5,
                "due_at_ms": NOW_MS + 120,
            },
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": "old-hard-b",
                "source_watermark_ms": NOW_MS,
                "priority": 10,
                "due_at_ms": NOW_MS + 130,
            },
        ],
        reason="test_old_duplicate",
        now_ms=NOW_MS + 110,
    )
    _insert_page_row(repo, news_item_id="old-hard-b", row_id="row-old-hard-b", headline="Old hard duplicate")

    material_url = "https://www.coindesk.com/markets/2026/06/03/eth-treasury-material"
    material_public = _insert_provider(
        repo,
        provider_item_id="provider-material-public",
        article_id="material-public",
        canonical_url=material_url,
    )
    repo.upsert_canonical_news_item(
        provider_item_id=material_public["provider_item_id"],
        canonical_url=material_url,
        title="Ethereum treasury company adds more ETH after financing round",
        summary="",
        body_text="Ethereum treasury company adds more ETH after financing round",
        language="en",
        published_at_ms=NOW_MS + 2_000,
        fetched_at_ms=NOW_MS + 2_000,
        content_hash="hash-material-public",
        title_fingerprint="ethereum treasury company adds more eth after financing round",
        now_ms=NOW_MS + 2_000,
        provider_token_impacts=[{"symbol": "ETH", "signal": "long", "score": 83}],
    )
    material_fallback = _insert_provider(
        repo,
        provider_item_id="provider-material-fallback",
        article_id="material-fallback",
        canonical_url="opennews://item/material-fallback",
    )
    _insert_historical_item(
        conn,
        provider=material_fallback,
        news_item_id="old-material-fallback",
        canonical_url="opennews://item/material-fallback",
        canonical_item_key="provider:opennews:material-fallback",
        dedup_key_kind="provider_article_id",
        title="COINDESK: Ethereum treasury company adds more ETH after financing round",
        published_at_ms=NOW_MS + 2_010,
        token_impacts=[{"symbol": "ETH", "signal": "long", "score": 83}],
    )
    _insert_page_row(
        repo,
        news_item_id="old-material-fallback",
        row_id="row-old-material-fallback",
        headline="Old material duplicate",
    )

    blocked = _insert_provider(
        repo,
        provider_item_id="provider-blocked-live",
        article_id="live-1",
        canonical_url="https://www.coindesk.com/news/index.html",
        raw_payload={
            "id": "live-1",
            "link": "https://www.coindesk.com/news/index.html",
            "opennews_method": "news",
            "provider_article_id": "live-1",
        },
    )
    _insert_historical_item(
        conn,
        provider=blocked,
        news_item_id="old-blocked-live",
        canonical_url="https://www.coindesk.com/live",
        canonical_item_key="provider:opennews:live-1",
        dedup_key_kind="provider_article_id",
        title="OpenNews live page placeholder with provider article id",
        published_at_ms=NOW_MS + 4_000,
        token_impacts=[{"symbol": "BTC", "signal": "neutral", "score": 40}],
    )
    conn.commit()
    return repos


def _insert_provider(
    repo: NewsRepository,
    *,
    provider_item_id: str,
    article_id: str,
    canonical_url: str,
    raw_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fetch_run_id = repo.start_fetch_run(source_id="opennews-news", started_at_ms=NOW_MS)
    provider = repo.upsert_provider_item(
        source_id="opennews-news",
        fetch_run_id=fetch_run_id,
        source_item_key=article_id,
        canonical_url=canonical_url,
        payload_hash=f"payload-{provider_item_id}",
        raw_payload_json=raw_payload
        or {
            "id": article_id,
            "link": canonical_url,
            "opennews_method": "news",
            "provider_article_id": article_id,
        },
        fetched_at_ms=NOW_MS,
        provider_article_id=article_id,
    )
    repo.conn.execute(
        "UPDATE news_provider_items SET provider_item_id = %s WHERE provider_item_id = %s",
        (provider_item_id, provider["provider_item_id"]),
    )
    repo.finish_fetch_run(
        fetch_run_id=fetch_run_id,
        source_id="opennews-news",
        status="success",
        finished_at_ms=NOW_MS + 1,
        fetched_count=1,
        inserted_count=1,
        updated_count=0,
        duplicate_count=0,
        http_status=200,
    )
    row = repo.conn.execute(
        "SELECT * FROM news_provider_items WHERE provider_item_id = %s",
        (provider_item_id,),
    ).fetchone()
    return dict(row)


def _insert_historical_item(
    conn,
    *,
    provider: dict[str, Any],
    news_item_id: str,
    canonical_url: str,
    canonical_item_key: str,
    dedup_key_kind: str,
    title: str,
    published_at_ms: int,
    token_impacts: list[dict[str, Any]],
) -> None:
    provider_item_id = str(provider["provider_item_id"])
    title_fingerprint = str(title).lower().replace(":", "").replace(",", "").replace("$", "").replace("-", " ")
    payload = {
        "canonical_url": canonical_url,
        "title": title,
        "summary": "",
        "body_text": title,
        "language": "en",
        "published_at_ms": int(published_at_ms),
        "fetched_at_ms": int(provider["fetched_at_ms"]),
        "content_hash": f"content-{news_item_id}",
        "title_fingerprint": title_fingerprint,
        "provider_signal_json": {"status": "ready", "direction": "neutral"},
        "provider_token_impacts_json": token_impacts,
        "url_identity_kind": "article" if canonical_url.startswith("http") else "unknown",
    }
    conn.execute(
        """
        INSERT INTO news_items (
          news_item_id, provider_item_id, source_id, source_domain, canonical_url,
          title, summary, body_text, language, published_at_ms, fetched_at_ms,
          content_hash, title_fingerprint, provider_signal_json, provider_token_impacts_json,
          canonical_item_key, dedup_key_kind, dedup_key_confidence, url_identity_kind,
          canonical_policy_version, created_at_ms, updated_at_ms
        )
        VALUES (
          %(news_item_id)s, %(provider_item_id)s, 'opennews-news', '6551.io', %(canonical_url)s,
          %(title)s, '', %(title)s, 'en', %(published_at_ms)s, %(fetched_at_ms)s,
          %(content_hash)s, %(title_fingerprint)s, %(provider_signal_json)s, %(provider_token_impacts_json)s,
          %(canonical_item_key)s, %(dedup_key_kind)s, 'strong', %(url_identity_kind)s,
          'news_canonical_item_v1', %(created_at_ms)s, %(updated_at_ms)s
        )
        """,
        {
            **payload,
            "news_item_id": news_item_id,
            "provider_item_id": provider_item_id,
            "canonical_item_key": canonical_item_key,
            "dedup_key_kind": dedup_key_kind,
            "provider_signal_json": Jsonb(payload["provider_signal_json"]),
            "provider_token_impacts_json": Jsonb(payload["provider_token_impacts_json"]),
            "created_at_ms": int(published_at_ms),
            "updated_at_ms": int(published_at_ms),
        },
    )
    conn.execute(
        """
        INSERT INTO news_item_observation_edges (
          provider_item_id, news_item_id, source_id, provider_article_key, match_type,
          match_confidence, policy_version, evidence_json, first_seen_at_ms, last_seen_at_ms
        )
        VALUES (%s, %s, 'opennews-news', %s, %s, 'strong', 'news_canonical_item_v1', %s, %s, %s)
        """,
        (
            provider_item_id,
            news_item_id,
            str(provider["provider_article_key"] or ""),
            "same_provider_article_id",
            Jsonb(
                {
                    "provider_article_key": str(provider["provider_article_key"] or ""),
                    "item_payload": payload,
                }
            ),
            int(published_at_ms),
            int(published_at_ms),
        ),
    )


def _insert_agent_run(repo: NewsRepository, *, news_item_id: str, run_id: str) -> dict[str, object]:
    return repo.insert_news_item_agent_run(
        run_id=run_id,
        news_item_id=news_item_id,
        provider="litellm",
        model="gpt-5-mini",
        execution_trace_id=f"trace-{run_id}",
        workflow_name=NEWS_ITEM_BRIEF_WORKFLOW_NAME,
        agent_name=NEWS_ITEM_BRIEF_AGENT_NAME,
        lane=NEWS_ITEM_BRIEF_LANE,
        artifact_version_hash="artifact-brief-1",
        prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
        schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
        validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
        guardrail_version=NEWS_ITEM_BRIEF_GUARDRAIL_VERSION,
        input_hash="input-brief-1",
        output_hash="output-brief-1",
        execution_started=True,
        status="completed",
        outcome="ready",
        request_json={"redacted": True},
        response_json={"summary_zh": "raw provider response should not be in detail"},
        validation_errors_json=[],
        trace_metadata_json={"attempt": 1},
        usage_json={"input_tokens": 10, "output_tokens": 5},
        latency_ms=10,
        started_at_ms=NOW_MS + 90,
        finished_at_ms=NOW_MS + 100,
        created_at_ms=NOW_MS + 90,
    )


def _insert_page_row(repo: NewsRepository, *, news_item_id: str, row_id: str, headline: str) -> None:
    repo.replace_page_rows_for_items(
        news_item_ids=[news_item_id],
        rows=[
            {
                "row_id": row_id,
                "news_item_id": news_item_id,
                "latest_at_ms": NOW_MS,
                "lifecycle_status": "raw",
                "headline": headline,
                "summary": "",
                "source_domain": "6551.io",
                "canonical_url": "https://example.com/stale",
                "token_lanes": [],
                "fact_lanes": [],
                "signal": {"source": "partial", "status": "partial", "direction": "neutral"},
                "token_impacts": [],
                "source": {
                    "source_id": "opennews-news",
                    "provider_type": "opennews",
                    "source_domain": "6551.io",
                    "source_name": "OpenNews",
                    "source_role": "observed_source",
                    "trust_tier": "standard",
                    "coverage_tags": [],
                    "source_quality_status": "unknown",
                },
                "computed_at_ms": NOW_MS,
                "projection_version": NEWS_PAGE_PROJECTION_VERSION,
            }
        ],
    )


def _repair_state(conn) -> dict[str, Any]:
    return {
        "items": [
            dict(row)
            for row in conn.execute(
                """
                SELECT news_item_id, canonical_item_key, canonical_url
                  FROM news_items
                 ORDER BY news_item_id
                """
            ).fetchall()
        ],
        "providers": [
            dict(row)
            for row in conn.execute(
                """
                SELECT provider_item_id, canonical_url, raw_payload_json
                  FROM news_provider_items
                 ORDER BY provider_item_id
                """
            ).fetchall()
        ],
        "edges": [
            dict(row)
            for row in conn.execute(
                """
                SELECT provider_item_id, news_item_id, match_type
                  FROM news_item_observation_edges
                 ORDER BY provider_item_id
                """
            ).fetchall()
        ],
        "dirty": [
            dict(row)
            for row in conn.execute(
                """
                SELECT projection_name, target_id, dirty_reason
                  FROM news_projection_dirty_targets
                 ORDER BY projection_name, target_id
                """
            ).fetchall()
        ],
        "agent_runs": [
            dict(row)
            for row in conn.execute(
                """
                SELECT run_id, news_item_id, trace_metadata_json
                  FROM news_item_agent_runs
                 ORDER BY run_id
                """
            ).fetchall()
        ],
    }
