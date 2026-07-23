from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy.exc import DBAPIError

from parallax.platform.db.postgres_migrations import alembic_config
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import test_postgres_dsn as _test_postgres_dsn


def test_macro_evidence_ai_hard_cut_migrates_nonempty_0190_state(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO public")
        conn.commit()
        config = alembic_config()
        config.attributes["database_url"] = _test_postgres_dsn()
        command.upgrade(config, "20260722_0190")

        conn.execute(
            """
            INSERT INTO news_sources(
              source_id, provider_type, feed_url, source_domain, source_name,
              config_payload_hash, created_at_ms, updated_at_ms
            ) VALUES (
              'source-hard-cut', 'rss', 'https://example.test/feed',
              'example.test', 'Example',
              'sha256:0000000000000000000000000000000000000000000000000000000000000000',
              10, 10
            );
            INSERT INTO news_fetch_runs(fetch_run_id, source_id, started_at_ms, status)
            VALUES ('fetch-hard-cut', 'source-hard-cut', 10, 'success');
            INSERT INTO news_provider_items(
              provider_item_id, source_id, fetch_run_id, source_item_key,
              canonical_url, payload_hash, raw_payload_json, fetched_at_ms
            ) VALUES (
              'provider-hard-cut', 'source-hard-cut', 'fetch-hard-cut', 'article-1',
              'https://example.test/article-1', 'provider-payload',
              '{"title":"Fact headline"}'::jsonb, 20
            );
            INSERT INTO news_items(
              news_item_id, provider_item_id, source_id, source_domain, canonical_url,
              title, published_at_ms, fetched_at_ms, content_hash, title_fingerprint,
              lifecycle_status, story_key, story_identity_version,
              agent_admission_status, agent_admission_reason, agent_admission_json,
              agent_admission_version, agent_representative_news_item_id,
              agent_admission_computed_at_ms, created_at_ms, updated_at_ms
            ) VALUES (
              'news-hard-cut', 'provider-hard-cut', 'source-hard-cut', 'example.test',
              'https://example.test/article-1', 'Fact headline', 20, 20,
              'content-hash', 'title-hash', 'processed', 'story-hard-cut', 'story-v2',
              'eligible', 'agent_ready', '{"status":"eligible"}'::jsonb,
              'agent-policy-v1', 'news-hard-cut', 30, 20, 30
            );
            INSERT INTO news_page_rows(
              row_id, news_item_id, latest_at_ms, lifecycle_status, headline, summary,
              source_domain, canonical_url, source_json, computed_at_ms,
              projection_version, payload_hash, agent_brief_json, agent_status,
              agent_brief_computed_at_ms, signal_json, token_impacts_json,
              story_key, story_json, agent_admission_status, agent_admission_reason,
              agent_admission_json, agent_representative_news_item_id,
              macro_event_flow_json
            ) VALUES (
              'news-hard-cut', 'news-hard-cut', 20, 'processed', 'Fact headline', '',
              'example.test', 'https://example.test/article-1', '{}'::jsonb, 30,
              'news_page_rows_v5', 'page-payload',
              '{"status":"ready","direction":"bullish","decision_class":"driver"}'::jsonb,
              'ready', 30,
              '{"source":"agent","method":"news_story_brief"}'::jsonb,
              '[{"symbol":"BTC"}]'::jsonb, 'story-hard-cut',
              '{"member_news_item_ids":["news-hard-cut"]}'::jsonb,
              'eligible', 'agent_ready', '{"status":"eligible"}'::jsonb,
              'news-hard-cut', '{"impact":"mainline_driver"}'::jsonb
            );
            INSERT INTO news_story_agent_runs(
              run_id, story_brief_key, story_key, story_identity_version,
              representative_news_item_id, member_news_item_ids_json, provider, model,
              backend, workflow_name, agent_name, lane, artifact_version_hash,
              prompt_version, schema_version, validator_version, guardrail_version,
              input_hash, output_hash, execution_started, status, outcome, request_json,
              response_json, validation_errors_json, trace_metadata_json, usage_json,
              latency_ms, started_at_ms, finished_at_ms, created_at_ms
            ) VALUES (
              'run-hard-cut', 'brief-hard-cut', 'story-hard-cut', 'story-v2',
              'news-hard-cut', '["news-hard-cut"]'::jsonb, 'litellm', 'retired-model',
              'litellm_sdk', 'news-story', 'story-brief', 'news.story_brief',
              'artifact-v1', 'prompt-v1', 'schema-v1', 'validator-v1', 'guard-v1',
              'input-hash', 'output-hash', true, 'success', 'success', '{}'::jsonb,
              '{}'::jsonb, '[]'::jsonb, '{}'::jsonb, '{}'::jsonb, 10, 30, 40, 40
            );
            INSERT INTO news_story_agent_briefs(
              story_brief_key, story_key, story_identity_version,
              representative_news_item_id, member_news_item_ids_json, agent_run_id,
              status, direction, decision_class, brief_json, input_hash,
              artifact_version_hash, prompt_version, schema_version, validator_version,
              computed_at_ms, created_at_ms, updated_at_ms
            ) VALUES (
              'brief-hard-cut', 'story-hard-cut', 'story-v2', 'news-hard-cut',
              '["news-hard-cut"]'::jsonb, 'run-hard-cut', 'ready', 'bullish', 'driver',
              '{"summary":"retired"}'::jsonb, 'input-hash', 'artifact-v1',
              'prompt-v1', 'schema-v1', 'validator-v1', 40, 40, 40
            );
            INSERT INTO news_projection_dirty_targets(
              projection_name, target_kind, target_id, "window", dirty_reason,
              payload_hash, source_watermark_ms, due_at_ms, first_dirty_at_ms, updated_at_ms
            ) VALUES (
              'story_brief', 'story', 'story-hard-cut', '', 'story_changed',
              'story-dirty', 30, 30, 30, 30
            );
            INSERT INTO notifications(
              notification_id, dedup_key, rule_id, severity, title, body,
              source_table, source_id, first_seen_at_ms, last_seen_at_ms,
              created_at_ms, updated_at_ms
            ) VALUES (
              'notification-hard-cut', 'notification-hard-cut', 'news_high_signal',
              'high', 'Retired', 'Retired AI notification', 'news_page_rows',
              'news-hard-cut', 40, 40, 40, 40
            );
            INSERT INTO notification_deliveries(
              delivery_id, notification_id, channel_id, provider, status,
              attempt_count, max_attempts, next_run_at_ms, last_attempt_at_ms,
              delivered_at_ms, last_error, created_at_ms, updated_at_ms
            ) VALUES (
              'delivery-hard-cut', 'notification-hard-cut', 'pushdeer', 'apprise',
              'pending', 2, 5, 50, 40, NULL, 'provider_unavailable', 40, 50
            );
            INSERT INTO worker_queue_terminal_events(
              terminal_id, worker_name, source_table, target_key, source_row_json,
              source_row_hash, final_status, final_reason, final_reason_bucket,
              attempt_count, payload_hash, first_seen_at_ms, last_attempted_at_ms,
              terminalized_at_ms, terminal_generation
            ) VALUES (
              'terminal-news-hard-cut', 'news_story_brief',
              'news_projection_dirty_targets', 'story-hard-cut',
              '{"projection_name":"story_brief","target_id":"story-hard-cut"}'::jsonb,
              'md5:terminal-news-hard-cut', 'failed', 'retry_budget_exhausted',
              'retry_budget_exhausted', 3, 'story-dirty', 30, 40, 40, 1
            );

            INSERT INTO token_radar_target_features(
              projection_version, "window", scope, lane, target_type_key, identity_id,
              target_type, target_id, latest_event_received_at_ms, factor_snapshot_json,
              source_event_ids_json, source_intent_ids_json, source_resolution_ids_json,
              payload_hash, last_scored_at_ms, created_at_ms, updated_at_ms,
              semantic_catalyst_raw_score, semantic_catalyst_weight,
              intent_json, resolution_json
            ) VALUES (
              'token-radar-v13-social-attention', '24h', 'all', 'resolved',
              'Asset', 'asset-hard-cut', 'Asset', 'asset-hard-cut', 100,
              '{"families":{"semantic_catalyst":{"score":0.9}}}'::jsonb,
              '["event-hard-cut"]'::jsonb, '["intent-hard-cut"]'::jsonb,
              '["resolution-hard-cut"]'::jsonb, 'feature-hash', 100, 100, 100,
              0.9, 0.3, '{"intent_id":"intent-hard-cut"}'::jsonb,
              '{"status":"EXACT","reason_codes":[],"candidate_ids":[],"lookup_keys":[]}'::jsonb
            );
            INSERT INTO token_radar_rank_source_events(
              projection_version, target_type_key, identity_id, source_kind, source_id,
              event_received_at_ms, projected_at_ms, source_payload_hash, is_watched
            ) VALUES (
              'token-radar-v13-social-attention', 'Asset', 'asset-hard-cut',
              'event', 'event-hard-cut', 100, 100, 'source-hash', true
            );
            INSERT INTO token_radar_target_first_seen(
              projection_version, "window", scope, venue, target_type_key, identity_id,
              first_seen_ms, last_seen_ms, first_row_id, latest_row_id,
              created_at_ms, updated_at_ms
            ) VALUES
              (
                'token-radar-v12', '24h', 'all', 'all', 'Asset', 'asset-hard-cut',
                40, 80, 'row-first', 'row-middle', 40, 80
              ),
              (
                'token-radar-v13-social-attention', '24h', 'all', 'all',
                'Asset', 'asset-hard-cut', 50, 100, 'row-later', 'row-latest',
                50, 100
              );

            INSERT INTO macro_observations(
              observation_id, source_name, series_key, observed_at, value_numeric,
              unit, frequency, data_quality, raw_payload_json, ingested_at_ms,
              concept_key, source_priority, fact_payload_hash
            ) VALUES (
              'macro-fact-hard-cut', 'fred', 'fred:DGS10', '2026-07-22', 4.25,
              'percent', 'daily', 'ok', '{}'::jsonb, 100,
              'rates:dgs10', 100, 'macro-fact-hash'
            );
            INSERT INTO macro_observation_series_rows(
              projection_version, concept_key, observed_at, value_numeric,
              source_name, series_key, unit, frequency, data_quality,
              event_metadata_json
            ) VALUES
              (
                'macro_regime_v4', 'rates:dgs10', '2026-07-22', 4.25,
                'fred', 'fred:DGS10', 'percent', 'daily', 'ok', '{}'::jsonb
              ),
              (
                'macro_evidence_v1', 'retired:macro_concept', '2026-07-22', 1,
                'retired', 'retired:series', 'index', 'daily', 'ok', '{}'::jsonb
              );
            INSERT INTO macro_observation_series_publication_state(
              projection_version, source_signature, row_count,
              latest_attempt_status, latest_attempt_started_at_ms,
              latest_attempt_finished_at_ms, updated_at_ms
            ) VALUES
              ('macro_regime_v4', 'legacy-signature', 1, 'published', 100, 100, 100),
              ('macro_evidence_v1', 'stale-signature', 1, 'published', 100, 100, 100);
            INSERT INTO macro_projection_dirty_targets(
              projection_name, projection_version, target_kind, target_id,
              payload_hash, dirty_reason, source_watermark_ms, priority,
              due_at_ms, created_at_ms, updated_at_ms, concept_key,
              min_observed_at, max_observed_at, source_watermark_date
            ) VALUES (
              'macro_evidence', 'macro_evidence_v1', 'concept',
              'retired:macro_concept', 'stale-dirty-hash', 'stale_partition',
              100, 0, 100, 100, 100, 'retired:macro_concept',
              '2026-07-22', '2026-07-22', '2026-07-22'
            );
            INSERT INTO macro_view_snapshots(
              projection_version, asof_date, status, regime, computed_at_ms,
              payload_hash, module_views_json
            ) VALUES (
              'macro_regime_v4', '2026-07-22', 'ready', 'risk_on', 100,
              'legacy-macro-hash', '{"overview":{"status":"ready"}}'::jsonb
            );
            """
        )
        conn.commit()

        fact_counts_before = _fact_counts(conn)
        command.upgrade(config, "20260723_0191")

        tables = _tables(conn)
        page_columns = _columns(conn, "news_page_rows")
        item_columns = _columns(conn, "news_items")
        target_feature_columns = _columns(conn, "token_radar_target_features")
        macro_columns = _columns(conn, "macro_view_snapshots")
        indexes = _indexes(conn)
        queue_constraint = conn.execute(
            """
            SELECT pg_get_constraintdef(oid) AS definition
            FROM pg_constraint
            WHERE conrelid = 'news_projection_dirty_targets'::regclass
              AND conname = 'news_projection_dirty_targets_projection_name_check'
            """
        ).fetchone()["definition"]
        token_dirty = conn.execute(
            """
            SELECT repair_dirty, leased_until_ms, attempt_count, last_error
            FROM token_radar_dirty_targets
            WHERE target_type_key = 'Asset' AND identity_id = 'asset-hard-cut'
            """
        ).fetchone()
        macro_dirty = conn.execute(
            """
            SELECT projection_version, target_kind, target_id
            FROM macro_projection_dirty_targets
            WHERE projection_name = 'macro_evidence'
            """
        ).fetchall()
        macro_series_rows = conn.execute("SELECT COUNT(*) AS count FROM macro_observation_series_rows").fetchone()[
            "count"
        ]
        macro_series_publications = conn.execute(
            "SELECT COUNT(*) AS count FROM macro_observation_series_publication_state"
        ).fetchone()["count"]
        page_dirty = conn.execute(
            """
            SELECT projection_name, target_kind, target_id
            FROM news_projection_dirty_targets
            WHERE target_id = 'news-hard-cut'
            """
        ).fetchone()
        remaining_notification = conn.execute(
            "SELECT notification_id FROM notifications WHERE rule_id = 'news_high_signal'"
        ).fetchone()
        remaining_delivery = conn.execute(
            "SELECT delivery_id FROM notification_deliveries WHERE delivery_id = 'delivery-hard-cut'"
        ).fetchone()
        archived_news_terminal = conn.execute(
            """
            SELECT operator_action, operator_reason, operator_action_at_ms
            FROM worker_queue_terminal_events
            WHERE terminal_id = 'terminal-news-hard-cut'
            """
        ).fetchone()
        archived_delivery_terminal = conn.execute(
            """
            SELECT worker_name, source_table, target_key, final_status,
                   final_reason, attempt_count, payload_hash,
                   operator_action, operator_reason, operator_action_at_ms,
                   source_row_json
            FROM worker_queue_terminal_events
            WHERE source_table = 'notification_deliveries'
              AND target_key = 'delivery-hard-cut'
            """
        ).fetchone()
        first_seen = conn.execute(
            """
            SELECT projection_version, first_seen_ms, last_seen_ms,
                   first_row_id, latest_row_id, created_at_ms, updated_at_ms
            FROM token_radar_target_first_seen
            WHERE "window" = '24h'
              AND scope = 'all'
              AND venue = 'all'
              AND target_type_key = 'Asset'
              AND identity_id = 'asset-hard-cut'
            """
        ).fetchone()
        fact_counts_after = _fact_counts(conn)
    finally:
        conn.close()

    assert {"news_story_agent_briefs", "news_story_agent_runs"}.isdisjoint(tables)
    assert {
        "agent_brief_json",
        "agent_status",
        "agent_brief_computed_at_ms",
        "signal_json",
        "token_impacts_json",
        "agent_admission_status",
        "agent_admission_reason",
        "agent_admission_json",
        "agent_representative_news_item_id",
        "macro_event_flow_json",
    }.isdisjoint(page_columns)
    assert {
        "agent_admission_status",
        "agent_admission_reason",
        "agent_admission_json",
        "agent_admission_version",
        "agent_representative_news_item_id",
        "agent_admission_computed_at_ms",
    }.isdisjoint(item_columns)
    assert {
        "idx_news_page_rows_direction_time",
        "ix_news_page_rows_alert_ready_latest",
        "ix_news_page_rows_agent_admission",
        "ix_news_page_rows_macro_event_flow_latest",
        "ix_news_page_rows_signal_direction",
        "ix_news_page_rows_signal_score",
        "ix_news_items_agent_admission_published",
    }.isdisjoint(indexes)
    assert "story_brief" not in queue_constraint
    assert "projection_name = 'page'" in queue_constraint
    assert {"semantic_catalyst_raw_score", "semantic_catalyst_weight"}.isdisjoint(target_feature_columns)
    assert token_dirty == {
        "repair_dirty": True,
        "leased_until_ms": None,
        "attempt_count": 0,
        "last_error": None,
    }
    assert fact_counts_after == fact_counts_before
    assert macro_columns == {
        "snapshot_key",
        "projection_version",
        "fact_watermark",
        "market_cutoff",
        "computed_at_ms",
        "overview_json",
        "cross_asset_json",
        "rates_inflation_json",
        "growth_labor_json",
        "liquidity_funding_json",
        "credit_json",
        "payload_hash",
    }
    assert macro_dirty == [
        {
            "projection_version": "macro_evidence_v1",
            "target_kind": "current",
            "target_id": "current",
        }
    ]
    assert macro_series_rows == 0
    assert macro_series_publications == 0
    assert page_dirty == {
        "projection_name": "page",
        "target_kind": "news_item",
        "target_id": "news-hard-cut",
    }
    assert remaining_notification is None
    assert remaining_delivery is None
    assert archived_news_terminal["operator_action"] == "archive"
    assert archived_news_terminal["operator_reason"] == "queue_retired_by_0191"
    assert archived_news_terminal["operator_action_at_ms"] is not None
    assert archived_delivery_terminal is not None
    archived_delivery_fields = {
        key: archived_delivery_terminal[key] for key in archived_delivery_terminal if key != "source_row_json"
    }
    assert archived_delivery_fields == {
        "worker_name": "notification_delivery",
        "source_table": "notification_deliveries",
        "target_key": "delivery-hard-cut",
        "final_status": "pending",
        "final_reason": "notification_rule_retired_by_0191",
        "attempt_count": 2,
        "payload_hash": "notification-hard-cut",
        "operator_action": "archive",
        "operator_reason": "queue_retired_by_0191",
        "operator_action_at_ms": archived_delivery_terminal["operator_action_at_ms"],
    }
    assert archived_delivery_terminal["operator_action_at_ms"] is not None
    assert archived_delivery_terminal["source_row_json"]["delivery_id"] == "delivery-hard-cut"
    assert archived_delivery_terminal["source_row_json"]["notification"]["rule_id"] == "news_high_signal"
    assert first_seen == {
        "projection_version": "token-radar-v14-transparent-factors",
        "first_seen_ms": 40,
        "last_seen_ms": 100,
        "first_row_id": "row-first",
        "latest_row_id": "row-latest",
        "created_at_ms": 40,
        "updated_at_ms": 100,
    }


def test_macro_evidence_ai_hard_cut_fails_closed_for_running_retired_delivery(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO public")
        conn.commit()
        config = alembic_config()
        config.attributes["database_url"] = _test_postgres_dsn()
        command.upgrade(config, "20260722_0190")
        conn.execute(
            """
            INSERT INTO notifications(
              notification_id, dedup_key, rule_id, severity, title, body,
              source_table, source_id, first_seen_at_ms, last_seen_at_ms,
              created_at_ms, updated_at_ms
            ) VALUES (
              'notification-running-hard-cut', 'notification-running-hard-cut',
              'news_high_signal', 'high', 'Retired', 'In flight',
              'news_page_rows', 'news-running-hard-cut', 40, 40, 40, 40
            );
            INSERT INTO notification_deliveries(
              delivery_id, notification_id, channel_id, provider, status,
              attempt_count, max_attempts, next_run_at_ms, last_attempt_at_ms,
              delivered_at_ms, last_error, created_at_ms, updated_at_ms
            ) VALUES (
              'delivery-running-hard-cut', 'notification-running-hard-cut',
              'pushdeer', 'apprise', 'running', 1, 5, 40, 40, NULL, NULL, 40, 40
            )
            """
        )
        conn.commit()

        with pytest.raises(DBAPIError, match="cannot retire news_high_signal while notification delivery is running"):
            command.upgrade(config, "20260723_0191")

        conn.rollback()
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()["version_num"]
        delivery = conn.execute(
            "SELECT status FROM notification_deliveries WHERE delivery_id = 'delivery-running-hard-cut'"
        ).fetchone()
    finally:
        conn.close()

    assert revision == "20260722_0190"
    assert delivery == {"status": "running"}


def _fact_counts(conn) -> dict[str, int]:
    return {
        table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
        for table in ("news_provider_items", "news_items", "macro_observations")
    }


def _tables(conn) -> set[str]:
    return {
        row["table_name"]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
    }


def _columns(conn, table_name: str) -> set[str]:
    return {
        row["column_name"]
        for row in conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table_name,),
        ).fetchall()
    }


def _indexes(conn) -> set[str]:
    return {
        row["indexname"]
        for row in conn.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'").fetchall()
    }
