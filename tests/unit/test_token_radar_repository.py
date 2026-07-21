from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from psycopg import pq

from parallax.domains.token_intel.interfaces import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    TOKEN_RADAR_DEFAULT_VENUE,
)
from parallax.domains.token_intel.repositories.token_radar_repository import (
    TokenRadarRepository,
    _json_payload,
    _payload_hash,
    _runtime_row_payload,
    stable_generation_id,
)


def test_json_payload_converts_decimal_values_before_jsonb_binding():
    row = _valid_factor_row()
    snapshot = _valid_factor_snapshot(rank_score=12.5)
    snapshot["families"]["social_heat"]["facts"]["volume_24h_usd"] = Decimal("123.45")
    row["factor_snapshot_json"] = snapshot
    row["rank_score"] = 12.5
    payload = _json_payload(row)

    assert payload["factor_snapshot_json"].obj["composite"]["rank_score"] == 12.5
    assert payload["factor_snapshot_json"].obj["families"]["social_heat"]["facts"]["volume_24h_usd"] == 123.45
    assert payload["degraded_reasons_json"].obj == []
    for dropped_column in (
        "asset_json",
        "primary_venue_json",
        "target_json",
        "attention_json",
        "market_json",
        "price_json",
        "score_json",
    ):
        assert dropped_column not in payload


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        pytest.param("intent_json", None, "token_radar_current_row_required:intent_json", id="missing-intent"),
        pytest.param("intent_json", {}, "token_radar_current_row_invalid:intent_json", id="empty-intent"),
        pytest.param(
            "resolution_json", None, "token_radar_current_row_required:resolution_json", id="missing-resolution"
        ),
        pytest.param("resolution_json", [], "token_radar_current_row_invalid:resolution_json", id="resolution-list"),
        pytest.param(
            "data_health_json", None, "token_radar_current_row_required:data_health_json", id="missing-health"
        ),
        pytest.param("data_health_json", {}, "token_radar_current_row_invalid:data_health_json", id="empty-health"),
        pytest.param(
            "source_event_ids_json",
            None,
            "token_radar_current_row_required:source_event_ids_json",
            id="missing-source",
        ),
        pytest.param(
            "source_event_ids_json",
            {},
            "token_radar_current_row_invalid:source_event_ids_json",
            id="source-mapping",
        ),
        pytest.param(
            "source_event_ids_json",
            [],
            "token_radar_current_row_invalid:source_event_ids_json",
            id="empty-source",
        ),
        pytest.param("intent_id", "", "token_radar_current_identity_required", id="empty-intent-id"),
        pytest.param("event_id", "", "token_radar_current_identity_required", id="empty-event-id"),
        pytest.param(
            "degraded_reasons_json",
            None,
            "token_radar_current_row_required:degraded_reasons_json",
            id="missing-reasons",
        ),
        pytest.param(
            "degraded_reasons_json",
            "market_missing",
            "token_radar_current_row_invalid:degraded_reasons_json",
            id="reasons-string",
        ),
    ],
)
def test_json_payload_rejects_missing_or_malformed_current_row_json_contract(field, value, error):
    row = _valid_factor_row()
    if value is None:
        row.pop(field, None)
    else:
        row[field] = value

    with pytest.raises(ValueError, match=error):
        _json_payload(row)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("status", None, id="missing-status"),
        pytest.param("reason_codes", None, id="missing-reason-codes"),
        pytest.param("candidate_ids", {}, id="candidate-ids-mapping"),
        pytest.param("lookup_keys", "symbol:BOV", id="lookup-keys-string"),
    ],
)
def test_json_payload_rejects_malformed_resolution_contract(field, value):
    row = _valid_factor_row()
    resolution = dict(row["resolution_json"])
    if value is None:
        resolution.pop(field, None)
    else:
        resolution[field] = value
    row["resolution_json"] = resolution

    with pytest.raises(ValueError, match=f"token_radar_current_resolution_(required|invalid):{field}"):
        _json_payload(row)


def test_publish_current_generation_upserts_current_rows_and_marks_ready_publication_state():
    conn = FakePublishConn()
    row = _valid_factor_row()

    result = TokenRadarRepository(conn).publish_current_generation(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        generation_id="gen-1h-1778",
        published_at_ms=1_778_000_000_000,
        source_frontier_ms=1_778_000_030_000,
        rows=[row],
    )

    joined_sql = "\n".join(conn.sqls)
    assert result == {"status": "published", "generation_id": "gen-1h-1778", "rows_written": 1}
    assert "DELETE FROM token_radar_current_rows" not in joined_sql
    assert "INSERT INTO token_radar_current_rows" in joined_sql
    assert 'ON CONFLICT(projection_version, "window", scope, venue, lane, target_type_key, identity_id)' in joined_sql
    assert "WHERE token_radar_current_rows.payload_hash IS DISTINCT FROM excluded.payload_hash" in joined_sql
    assert "INSERT INTO token_radar_publication_state" in joined_sql
    assert "INSERT INTO token_radar_rank_history" not in joined_sql
    assert "INSERT INTO token_radar_snapshot_audit" not in joined_sql
    assert "token_radar_projection_coverage" not in joined_sql
    assert "token_radar_rows" not in joined_sql
    assert conn.current_insert_params["target_type_key"] == "Asset"
    assert conn.current_insert_params["identity_id"] == "asset-1"
    assert conn.current_insert_params["generation_id"] == "gen-1h-1778"
    assert conn.current_insert_params["published_at_ms"] == 1_778_000_000_000
    assert conn.current_insert_params["source_frontier_ms"] == 1_778_000_030_000
    assert conn.current_insert_params["payload_hash"]
    assert conn.current_insert_params["listed_at_ms"] == 1_778_000_000_000
    assert conn.current_insert_params["rank_score"] == 12
    assert conn.current_insert_params["quality_status"] == "ready"
    assert conn.current_insert_params["degraded_reasons_json"].obj == []
    for dropped_column in (
        "asset_json",
        "primary_venue_json",
        "target_json",
        "attention_json",
        "market_json",
        "price_json",
        "score_json",
    ):
        assert dropped_column not in conn.current_insert_params
    assert conn.publication_state_params["current_generation_id"] == "gen-1h-1778"
    assert conn.publication_state_params["current_published_at_ms"] == 1_778_000_000_000
    assert conn.publication_state_params["current_source_frontier_ms"] == 1_778_000_030_000
    assert conn.publication_state_params["current_row_count"] == 1
    assert conn.publication_state_params["current_source_rows"] == 1
    assert conn.publication_state_params["latest_attempt_status"] == "ready"


def test_token_radar_repository_mutations_require_explicit_transaction_before_sql():
    write_cases = (
        (
            "publish_current_generation",
            lambda repo: repo.publish_current_generation(
                projection_version="token-radar-v13-social-attention",
                window="1h",
                scope="all",
                venue=TOKEN_RADAR_DEFAULT_VENUE,
                generation_id="gen-1h-1778",
                published_at_ms=1_778_000_000_000,
                source_frontier_ms=1_778_000_030_000,
                rows=[_valid_factor_row()],
            ),
        ),
        (
            "upsert_target_feature",
            lambda repo: repo.upsert_target_feature(
                projection_version="token-radar-v13-social-attention",
                window="1h",
                scope="all",
                row=_valid_factor_row(),
                computed_at_ms=1_778_000_000_000,
            ),
        ),
        (
            "delete_target_feature",
            lambda repo: repo.delete_target_feature(
                projection_version="token-radar-v13-social-attention",
                window="1h",
                scope="all",
                lane="resolved",
                target_type_key="Asset",
                identity_id="asset-1",
            ),
        ),
        (
            "prune_target_features",
            lambda repo: repo.prune_target_features(
                projection_version="token-radar-v13-social-attention",
                window="1h",
                scope="all",
                latest_event_before_ms=1_778_000_000_000,
                limit=100,
            ),
        ),
        (
            "upsert_first_seen_batch",
            lambda repo: repo.upsert_first_seen_batch(
                projection_version="token-radar-v13-social-attention",
                window="1h",
                scope="all",
                venue=TOKEN_RADAR_DEFAULT_VENUE,
                rows=[_valid_factor_row()],
                computed_at_ms=1_778_000_000_000,
            ),
        ),
        (
            "mark_publication_failed",
            lambda repo: repo.mark_publication_failed(
                projection_version="token-radar-v13-social-attention",
                window="1h",
                scope="all",
                venue=TOKEN_RADAR_DEFAULT_VENUE,
                generation_id="gen-failed",
            ),
        ),
    )

    for name, write in write_cases:
        conn = NoTransactionConn()
        with pytest.raises(RuntimeError, match="requires_explicit_transaction"):
            write(TokenRadarRepository(conn))
        assert conn.sqls == [], name


def test_token_radar_repository_publication_runs_inside_caller_owned_transaction():
    conn = TransactionalFakePublishConn()

    with conn.transaction():
        result = TokenRadarRepository(conn).publish_current_generation(
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            generation_id="gen-1h-1778",
            published_at_ms=1_778_000_000_000,
            source_frontier_ms=1_778_000_030_000,
            rows=[_valid_factor_row()],
        )

    assert result["status"] == "published"
    assert conn.transaction_entries == 1
    assert "SELECT pg_advisory_xact_lock" in conn.sqls[0]


def test_stable_generation_id_is_content_addressed_not_time_addressed():
    first = _valid_factor_row()
    second = _valid_factor_row()
    second["row_id"] = "row-factor-same-semantic-later"
    second["created_at_ms"] = 1_778_000_060_000

    first_generation_id = stable_generation_id(
        projection_version="token-radar-v13-social-attention",
        window="5m",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        rows=[first],
    )
    second_generation_id = stable_generation_id(
        projection_version="token-radar-v13-social-attention",
        window="5m",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        rows=[second],
    )

    assert first_generation_id == second_generation_id


def test_runtime_row_payload_hash_ignores_factor_snapshot_computed_at_noise():
    first = _valid_factor_row()
    second = _valid_factor_row()
    second_snapshot = dict(second["factor_snapshot_json"])
    second_snapshot["provenance"] = {
        "computed_at_ms": 1_778_000_060_000,
        "source_event_ids": ["event-1"],
    }
    second["factor_snapshot_json"] = second_snapshot

    first_payload = _runtime_row_payload(
        first,
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        generation_id="gen-1",
        published_at_ms=1_778_000_000_000,
        source_frontier_ms=1_778_000_030_000,
        listed_at_ms=1_778_000_000_000,
    )
    second_payload = _runtime_row_payload(
        second,
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        generation_id="gen-1",
        published_at_ms=1_778_000_000_000,
        source_frontier_ms=1_778_000_030_000,
        listed_at_ms=1_778_000_000_000,
    )

    assert second_payload["payload_hash"] == first_payload["payload_hash"]


def test_runtime_row_payload_hash_keeps_non_factor_provenance_computed_at_significant():
    first = _valid_factor_row()
    second = _valid_factor_row()
    first["intent_json"] = {
        "display_symbol": "BOV",
        "analysis": {
            "subject": {"kind": "non-factor"},
            "provenance": {"computed_at_ms": 1_778_000_000_000, "source": "audit"},
        },
    }
    second["intent_json"] = {
        "display_symbol": "BOV",
        "analysis": {
            "subject": {"kind": "non-factor"},
            "provenance": {"computed_at_ms": 1_778_000_060_000, "source": "audit"},
        },
    }

    first_payload = _runtime_row_payload(
        first,
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        generation_id="gen-1",
        published_at_ms=1_778_000_000_000,
        source_frontier_ms=1_778_000_030_000,
        listed_at_ms=1_778_000_000_000,
    )
    second_payload = _runtime_row_payload(
        second,
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        generation_id="gen-1",
        published_at_ms=1_778_000_000_000,
        source_frontier_ms=1_778_000_030_000,
        listed_at_ms=1_778_000_000_000,
    )

    assert second_payload["payload_hash"] != first_payload["payload_hash"]


def test_stable_generation_id_changes_when_row_quality_changes_even_with_same_payload_hash():
    ready = {**_valid_factor_row(), "payload_hash": "same-payload-hash"}
    degraded = {
        **_valid_factor_row(),
        "payload_hash": "same-payload-hash",
        "quality_status": "degraded",
        "degraded_reasons_json": ["market_anchor_missing"],
    }

    ready_generation_id = stable_generation_id(
        projection_version="token-radar-v13-social-attention",
        window="5m",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        rows=[ready],
    )
    degraded_generation_id = stable_generation_id(
        projection_version="token-radar-v13-social-attention",
        window="5m",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        rows=[degraded],
    )

    assert ready_generation_id != degraded_generation_id


def test_token_radar_serving_identity_requires_formal_current_key_without_target_or_intent_fallback():
    row = {
        **_valid_factor_row(),
        "target_type_key": "",
        "identity_id": "",
        "target_type": "Asset",
        "target_id": "asset-legacy",
        "intent_id": "intent-legacy",
    }

    with pytest.raises(ValueError, match="token_radar_current_identity_required"):
        stable_generation_id(
            projection_version="token-radar-v13-social-attention",
            window="5m",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            rows=[row],
        )

    with pytest.raises(ValueError, match="token_radar_current_identity_required"):
        _runtime_row_payload(
            row,
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            generation_id="gen-invalid",
            published_at_ms=1_778_000_000_000,
            source_frontier_ms=1_778_000_030_000,
            listed_at_ms=1_778_000_000_000,
        )

    conn = FakeConn()
    with pytest.raises(ValueError, match="token_radar_current_identity_required"):
        TokenRadarRepository(conn).upsert_target_feature(
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            row=row,
            computed_at_ms=1_778_000_000_000,
        )
    assert conn.calls == 0


def test_publish_current_generation_rewrites_when_only_row_quality_changes():
    ready = _valid_factor_row()
    degraded = {
        **_valid_factor_row(),
        "quality_status": "degraded",
        "degraded_reasons_json": ["market_anchor_missing"],
    }
    incoming_payload_hash = _runtime_row_payload(
        degraded,
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        generation_id="gen-degraded",
        published_at_ms=1_778_000_060_000,
        source_frontier_ms=1_778_000_030_000,
        listed_at_ms=1_778_000_000_000,
    )["payload_hash"]
    existing_current = _runtime_row_payload(
        ready,
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        generation_id="gen-existing",
        published_at_ms=1_778_000_000_000,
        source_frontier_ms=1_778_000_030_000,
        listed_at_ms=1_778_000_000_000,
    )
    existing_current["payload_hash"] = incoming_payload_hash
    conn = FakePublishConn(
        existing_current=existing_current,
        publication_state={
            "current_generation_id": "gen-existing",
            "current_published_at_ms": 1_778_000_000_000,
        },
    )

    result = TokenRadarRepository(conn).publish_current_generation(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        generation_id="gen-degraded",
        published_at_ms=1_778_000_060_000,
        source_frontier_ms=1_778_000_030_000,
        rows=[degraded],
    )

    joined_sql = "\n".join(conn.sqls)
    assert result == {"status": "published", "generation_id": "gen-degraded", "rows_written": 1}
    assert "DELETE FROM token_radar_current_rows" not in joined_sql
    assert "INSERT INTO token_radar_current_rows" in joined_sql
    assert "quality_status IS DISTINCT FROM excluded.quality_status" in joined_sql


def test_publish_current_generation_unchanged_does_not_delete_insert_or_emit_current_changes():
    row = _valid_factor_row()
    existing_current = _runtime_row_payload(
        row,
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        generation_id="gen-existing",
        published_at_ms=1_778_000_000_000,
        source_frontier_ms=1_778_000_030_000,
        listed_at_ms=1_778_000_000_000,
    )
    conn = FakePublishConn(
        existing_current=existing_current,
        publication_state={
            "current_generation_id": "gen-existing",
            "current_published_at_ms": 1_778_000_000_000,
        },
    )
    current_changes: list[dict[str, Any]] = []

    result = TokenRadarRepository(conn).publish_current_generation(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        generation_id="gen-incoming-stable",
        published_at_ms=1_778_000_060_000,
        source_frontier_ms=1_778_000_030_000,
        rows=[row],
        on_current_changes=lambda **kwargs: current_changes.append(kwargs),
    )

    joined_sql = "\n".join(conn.sqls)
    assert result == {"status": "unchanged", "generation_id": "gen-existing", "rows_written": 0}
    assert "DELETE FROM token_radar_current_rows" not in joined_sql
    assert "INSERT INTO token_radar_current_rows" not in joined_sql
    assert current_changes == []
    assert conn.publication_state_params["current_generation_id"] == "gen-existing"
    assert conn.publication_state_params["latest_attempt_generation_id"] == "gen-existing"
    assert conn.publication_state_params["latest_attempt_status"] == "ready"


def test_publish_current_generation_upserts_rows_without_payload_hash_retry_path():
    row = _valid_factor_row()
    existing_payload = _payload_hash(
        _runtime_row_payload(
            row,
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            generation_id="gen-existing",
            published_at_ms=1_778_000_000_000,
            source_frontier_ms=1_778_000_000_000,
            listed_at_ms=1_778_000_000_000,
        )
    )
    conn = FakePublishConn(
        existing_current={
            "row_id": "row-factor-existing",
            "projection_version": "token-radar-v13-social-attention",
            "window": "1h",
            "scope": "all",
            "lane": "resolved",
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "payload_hash": existing_payload,
            "rank": 1,
            "decision": "discard",
        }
    )

    result = TokenRadarRepository(conn).publish_current_generation(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        generation_id="gen-next",
        published_at_ms=1_778_000_060_000,
        source_frontier_ms=1_778_000_060_000,
        rows=[row],
    )

    assert result == {"status": "published", "generation_id": "gen-next", "rows_written": 1}
    assert conn.current_insert_params["generation_id"] == "gen-next"
    current_sql = next(sql for sql in conn.sqls if "INSERT INTO token_radar_current_rows" in sql)
    assert "payload_hash IS DISTINCT FROM" in current_sql
    assert "ON CONFLICT" in current_sql
    assert existing_payload


def test_publish_current_generation_requires_real_cursor_rowcount_for_current_row_upsert():
    conn = FakePublishConn(omit_current_rowcount=True)

    with pytest.raises(TypeError, match="token_radar_repository_rowcount_invalid"):
        TokenRadarRepository(conn).publish_current_generation(
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            generation_id="gen-rowcount-required",
            published_at_ms=1_778_000_060_000,
            source_frontier_ms=1_778_000_060_000,
            rows=[_valid_factor_row()],
        )


@pytest.mark.parametrize("rowcount", ("not-an-int", "1"))
def test_publish_current_generation_rejects_invalid_current_row_upsert_rowcount(rowcount: Any):
    conn = FakePublishConn(current_rowcount=rowcount)

    with pytest.raises(TypeError, match="token_radar_repository_rowcount_invalid"):
        TokenRadarRepository(conn).publish_current_generation(
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            generation_id="gen-rowcount-invalid",
            published_at_ms=1_778_000_060_000,
            source_frontier_ms=1_778_000_060_000,
            rows=[_valid_factor_row()],
        )


def test_publish_rows_requires_factor_snapshot_json_before_insert():
    conn = FakePublishConn()
    row = _valid_factor_row()
    del row["factor_snapshot_json"]

    with pytest.raises(ValueError, match="factor_snapshot_json is required"):
        TokenRadarRepository(conn).publish_current_generation(
            projection_version="token-radar-v9-factor-snapshot",
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            generation_id="gen-invalid",
            published_at_ms=1_778_000_000_000,
            source_frontier_ms=1_778_000_000_000,
            rows=[row],
        )

    assert conn.current_insert_params == {}


def test_publish_rows_rejects_empty_factor_snapshot_json_before_insert():
    conn = FakePublishConn()
    row = _valid_factor_row()
    row["factor_snapshot_json"] = {}

    with pytest.raises(ValueError, match="factor_snapshot_json must be non-empty"):
        TokenRadarRepository(conn).publish_current_generation(
            projection_version="token-radar-v9-factor-snapshot",
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            generation_id="gen-invalid",
            published_at_ms=1_778_000_000_000,
            source_frontier_ms=1_778_000_000_000,
            rows=[row],
        )

    assert conn.current_insert_params == {}


def test_publish_rows_requires_factor_version_before_insert():
    conn = FakePublishConn()
    row = _valid_factor_row()
    del row["factor_version"]

    with pytest.raises(ValueError, match="factor_version is required"):
        TokenRadarRepository(conn).publish_current_generation(
            projection_version="token-radar-v9-factor-snapshot",
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            generation_id="gen-invalid",
            published_at_ms=1_778_000_000_000,
            source_frontier_ms=1_778_000_000_000,
            rows=[row],
        )

    assert conn.current_insert_params == {}


def test_publish_rows_rejects_hard_gates_before_insert():
    conn = FakePublishConn()
    row = _valid_factor_row()
    row["factor_snapshot_json"]["hard_gates"] = {"eligible_for_high_alert": True}

    with pytest.raises(ValueError, match="hard_gates"):
        TokenRadarRepository(conn).publish_current_generation(
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            generation_id="gen-invalid",
            published_at_ms=1_778_000_000_000,
            source_frontier_ms=1_778_000_000_000,
            rows=[row],
        )

    assert conn.current_insert_params == {}


def test_publish_rows_rejects_missing_v3_factor_family_before_insert():
    conn = FakePublishConn()
    row = _valid_factor_row()
    del row["factor_snapshot_json"]["families"]["semantic_catalyst"]

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.families\.semantic_catalyst is required"):
        TokenRadarRepository(conn).publish_current_generation(
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            generation_id="gen-invalid",
            published_at_ms=1_778_000_000_000,
            source_frontier_ms=1_778_000_000_000,
            rows=[row],
        )

    assert conn.current_insert_params == {}


@pytest.mark.parametrize(
    ("section", "field", "error"),
    (
        ("composite", "rank_score", r"factor_snapshot_json\.composite\.rank_score is required"),
        ("composite", "recommended_decision", r"factor_snapshot_json\.composite\.recommended_decision is required"),
        ("gates", "max_decision", r"factor_snapshot_json\.gates\.max_decision is required"),
    ),
)
def test_upsert_target_feature_requires_factor_snapshot_core_score_decision_fields_before_sql(
    section: str,
    field: str,
    error: str,
):
    conn = FakeConn()
    row = _valid_factor_row()
    del row["factor_snapshot_json"][section][field]

    with pytest.raises(ValueError, match=error):
        TokenRadarRepository(conn).upsert_target_feature(
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            row=row,
            computed_at_ms=1_778_000_000_000,
        )

    assert conn.calls == 0


def test_publish_rows_rejects_factor_snapshot_version_mismatch_before_insert():
    conn = FakePublishConn()
    row = _valid_factor_row()
    row["factor_snapshot_json"]["schema_version"] = "token_factor_snapshot_legacy"

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.schema_version must match factor_version"):
        TokenRadarRepository(conn).publish_current_generation(
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            generation_id="gen-invalid",
            published_at_ms=1_778_000_000_000,
            source_frontier_ms=1_778_000_000_000,
            rows=[row],
        )

    assert conn.current_insert_params == {}


def test_latest_current_rows_limits_each_lane_independently():
    conn = FakeConn()

    rows = TokenRadarRepository(conn).latest_current_rows(
        window="5m",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        limit=8,
        projection_version="token-radar-v13-social-attention",
    )

    assert rows == []
    assert "FROM token_radar_current_rows current_rows" in conn.sql
    assert "JOIN token_radar_publication_state state" in conn.sql
    assert "state.current_generation_id = current_rows.generation_id" not in conn.sql
    assert "state.current_generation_id IS NOT NULL" in conn.sql
    assert "state.latest_attempt_status = 'ready'" not in conn.sql
    assert "PARTITION BY lane" in conn.sql
    assert "lane_rank <= %s" in conn.sql
    assert conn.params[-2:] == (8, 16)


@pytest.mark.parametrize("limit", [-1, True, "8"])
def test_latest_current_rows_rejects_malformed_limit_before_sql(limit: object) -> None:
    conn = FakeConn()

    with pytest.raises(ValueError, match="token_radar_latest_current_rows_limit_required"):
        TokenRadarRepository(conn).latest_current_rows(
            window="5m",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            limit=limit,  # type: ignore[arg-type]
            projection_version="token-radar-v13-social-attention",
        )

    assert conn.calls == 0


def test_latest_current_rows_reads_materialized_listed_at_without_history_lateral():
    conn = FakeConn()

    TokenRadarRepository(conn).latest_current_rows(
        window="1h",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        limit=50,
        projection_version="token-radar-v13-social-attention",
    )

    assert "LEFT JOIN LATERAL" not in conn.sql
    assert "token_radar_rows" not in conn.sql


def test_current_row_for_target_reads_last_good_generation_after_failed_attempt():
    conn = FakeConn(rows=[{"row_id": "row-1"}])

    row = TokenRadarRepository(conn).current_row_for_target(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        target_type="Asset",
        target_id="asset-1",
    )

    assert row == {"row_id": "row-1"}
    assert "JOIN token_radar_publication_state state" in conn.sql
    assert "state.current_generation_id = current_rows.generation_id" not in conn.sql
    assert "state.current_generation_id IS NOT NULL" in conn.sql
    assert "state.latest_attempt_status = 'ready'" not in conn.sql
    assert "token_radar_projection_coverage" not in conn.sql


def test_upsert_target_feature_writes_compact_projection_row():
    conn = FakeConn()
    row = _valid_factor_row()

    count = TokenRadarRepository(conn).upsert_target_feature(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        row=row,
        computed_at_ms=1_778_000_000_000,
    )

    assert count == 1
    assert "INSERT INTO token_radar_target_features" in conn.sql
    assert 'ON CONFLICT(projection_version, "window", scope, lane, target_type_key, identity_id)' in conn.sql
    assert conn.params["target_type_key"] == "Asset"
    assert conn.params["identity_id"] == "asset-1"
    assert conn.params["source_event_ids_json"].obj == ["event-1"]
    assert conn.params["source_intent_ids_json"].obj == ["intent-1"]
    assert conn.params["intent_json"].obj == {
        "intent_id": "intent-1",
        "event_id": "event-1",
        "display_symbol": "BOV",
    }
    assert conn.params["resolution_json"].obj == {
        "status": "EXACT",
        "reason_codes": [],
        "candidate_ids": [],
        "lookup_keys": [],
    }
    assert "intent_json, resolution_json" in conn.sql
    assert conn.params["payload_hash"]
    assert conn.params["social_heat_raw_score"] == 12.0
    assert conn.params["social_heat_weight"] == 1.0
    assert conn.params["social_propagation_raw_score"] == 10.0
    assert conn.params["cohort_high_confidence_mentions"] == 0
    assert conn.params["cohort_symbol"] == "BOV"
    assert conn.params["recommended_decision"] == "discard"
    assert conn.params["gates_max_decision"] == "discard"
    assert "WHERE token_radar_target_features.payload_hash IS DISTINCT FROM excluded.payload_hash" in conn.sql
    assert "rank_input_version" not in conn.sql
    assert "last_scored_at_ms < excluded.last_scored_at_ms" not in conn.sql


_MISSING = object()


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("lane", _MISSING, "token_radar_target_feature_payload_required:lane"),
        ("lane", "", "token_radar_target_feature_payload_invalid:lane"),
        ("lane", "legacy", "token_radar_target_feature_payload_invalid:lane"),
        (
            "source_max_received_at_ms",
            _MISSING,
            "token_radar_target_feature_payload_required:source_max_received_at_ms",
        ),
        (
            "source_max_received_at_ms",
            "bad",
            "token_radar_target_feature_payload_invalid:source_max_received_at_ms",
        ),
        (
            "source_event_ids_json",
            _MISSING,
            "token_radar_target_feature_payload_required:source_event_ids_json",
        ),
        (
            "source_event_ids_json",
            "event-1",
            "token_radar_target_feature_payload_invalid:source_event_ids_json",
        ),
        ("intent_json", _MISSING, "token_radar_target_feature_payload_required:intent_json"),
        ("intent_json", {}, "token_radar_target_feature_payload_invalid:intent_json"),
        ("resolution_json", _MISSING, "token_radar_target_feature_payload_required:resolution_json"),
        ("resolution_json", [], "token_radar_target_feature_payload_invalid:resolution_json"),
        ("created_at_ms", _MISSING, "token_radar_target_feature_payload_required:created_at_ms"),
        ("created_at_ms", "bad", "token_radar_target_feature_payload_invalid:created_at_ms"),
    ),
)
def test_upsert_target_feature_requires_formal_projection_payload_fields_without_defaults(
    field: str,
    value: object,
    error: str,
):
    conn = FakeConn()
    row = _valid_factor_row()
    if value is _MISSING:
        row.pop(field)
    else:
        row[field] = value

    with pytest.raises(ValueError, match=error):
        TokenRadarRepository(conn).upsert_target_feature(
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            row=row,
            computed_at_ms=1_778_000_000_000,
        )

    assert conn.calls == 0


def test_upsert_target_feature_returns_actual_rowcount_for_unchanged_payload():
    conn = FakeConn(rowcount=0)
    row = _valid_factor_row()

    count = TokenRadarRepository(conn).upsert_target_feature(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        row=row,
        computed_at_ms=1_778_000_060_000,
    )

    assert count == 0


@pytest.mark.parametrize(
    ("rowcount", "omit_rowcount", "error"),
    (
        (1, True, "token_radar_repository_rowcount_invalid"),
        ("bad", False, "token_radar_repository_rowcount_invalid"),
        ("1", False, "token_radar_repository_rowcount_invalid"),
    ),
)
def test_upsert_target_feature_requires_real_cursor_rowcount(rowcount: Any, omit_rowcount: bool, error: str):
    conn = FakeConn(rowcount=rowcount, omit_rowcount=omit_rowcount)

    with pytest.raises(TypeError, match=error):
        TokenRadarRepository(conn).upsert_target_feature(
            projection_version="token-radar-v13-social-attention",
            window="1h",
            scope="all",
            row=_valid_factor_row(),
            computed_at_ms=1_778_000_060_000,
        )


def test_delete_target_feature_uses_projection_identity_key():
    conn = FakeConn()

    TokenRadarRepository(conn).delete_target_feature(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        lane="resolved",
        target_type_key="Asset",
        identity_id="asset-1",
    )

    assert "DELETE FROM token_radar_target_features" in conn.sql
    assert "target_type_key = %s" in conn.sql
    assert conn.params == ("token-radar-v13-social-attention", "1h", "all", "resolved", "Asset", "asset-1")


def test_prune_target_features_deletes_only_projection_window_scope_before_cutoff():
    conn = FakeConn(rowcount=7)

    deleted = TokenRadarRepository(conn).prune_target_features(
        projection_version="token-radar-v13-social-attention",
        window="5m",
        scope="matched",
        latest_event_before_ms=1_777_800_000_000,
        limit=25,
    )

    assert deleted == 7
    assert "DELETE FROM token_radar_target_features" in conn.sql
    assert "projection_version = %s" in conn.sql
    assert '"window" = %s' in conn.sql
    assert "scope = %s" in conn.sql
    assert "latest_event_received_at_ms < %s" in conn.sql
    assert "LIMIT %s" in conn.sql
    assert "token_radar_current_rows" not in conn.sql
    assert conn.params == (
        "token-radar-v13-social-attention",
        "5m",
        "matched",
        1_777_800_000_000,
        25,
    )


@pytest.mark.parametrize("limit", [0, -1, True, "25"])
def test_prune_target_features_rejects_malformed_limit_before_sql(limit: object) -> None:
    conn = FakeConn(rowcount=7)

    with pytest.raises(ValueError, match="token_radar_prune_target_features_limit_required"):
        TokenRadarRepository(conn).prune_target_features(
            projection_version="token-radar-v13-social-attention",
            window="5m",
            scope="matched",
            latest_event_before_ms=1_777_800_000_000,
            limit=limit,  # type: ignore[arg-type]
        )

    assert conn.calls == 0


def test_list_rank_inputs_for_rank_set_reads_private_projection_rows_without_version_gate():
    conn = FakeConn(
        rows=[
            {
                "projection_version": "token-radar-v13-social-attention",
                "window": "1h",
                "scope": "all",
                "lane": "resolved",
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "target_type": "Asset",
                "target_id": "asset-1",
                "pricefeed_id": "pf-1",
                "latest_event_received_at_ms": 1_778_000_000_000,
                "latest_market_observed_at_ms": 1_778_000_030_000,
                "social_heat_raw_score": 12.0,
                "social_heat_weight": 1.0,
                "social_propagation_raw_score": 10.0,
                "social_propagation_weight": 1.0,
                "semantic_catalyst_raw_score": 10.0,
                "semantic_catalyst_weight": 1.0,
                "timing_risk_raw_score": 10.0,
                "timing_risk_weight": 1.0,
                "cohort_high_confidence_mentions": 1,
                "cohort_kol_mentions": 0,
                "cohort_public_followup_authors": 0,
                "cohort_first_seen_global_24h": False,
                "cohort_symbol": "BOV",
                "social_heat_watched_mentions": 1,
                "social_heat_mentions_1h": 5,
                "social_propagation_mentions": 0,
                "social_heat_latest_seen_ms": 1_778_000_000_000,
                "raw_composite_score": 12.0,
                "recommended_decision": "discard",
                "gates_max_decision": "watch",
                "factor_snapshot_json": _valid_factor_snapshot(rank_score=12.0),
                "intent_json": {"intent_id": "intent-1", "event_id": "event-1", "display_symbol": "BOV"},
                "resolution_json": {
                    "status": "EXACT",
                    "reason_codes": ["CHAIN_ADDRESS_EXACT"],
                    "candidate_ids": [],
                    "lookup_keys": ["address:eip155:1:0xabc"],
                },
                "source_event_ids_json": ["event-1"],
                "source_intent_ids_json": ["intent-1"],
                "source_resolution_ids_json": ["resolution-1"],
                "payload_hash": "feature-hash",
                "last_scored_at_ms": 1_778_000_060_000,
            }
        ]
    )

    rows = TokenRadarRepository(conn).list_rank_inputs_for_rank_set(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        min_latest_event_received_at_ms=1_778_000_000_000,
    )

    assert "FROM token_radar_target_features" in conn.sql
    assert "SELECT *" not in conn.sql
    assert "factor_snapshot_json" in conn.sql
    assert "intent_json" in conn.sql
    assert "resolution_json" in conn.sql
    assert "source_event_ids_json" in conn.sql
    assert "rank_input_version" not in conn.sql
    assert "latest_event_received_at_ms >= %s" in conn.sql
    assert conn.params == (
        "token-radar-v13-social-attention",
        "1h",
        "all",
        1_778_000_000_000,
    )
    assert rows[0]["target_type_key"] == "Asset"
    assert rows[0]["identity_id"] == "asset-1"
    assert rows[0]["payload_hash"] == "feature-hash"


def test_list_rank_inputs_for_rank_set_filters_by_latest_event_cutoff():
    conn = FakeConn(rows=[])
    cutoff_ms = 1_778_000_300_000

    rows = TokenRadarRepository(conn).list_rank_inputs_for_rank_set(
        projection_version="token-radar-v13-social-attention",
        window="5m",
        scope="matched",
        min_latest_event_received_at_ms=cutoff_ms,
    )

    assert rows == []
    assert "FROM token_radar_target_features" in conn.sql
    assert "AND latest_event_received_at_ms >= %s" in conn.sql
    assert "ORDER BY lane DESC, rank_score DESC, latest_event_received_at_ms DESC, identity_id ASC" in conn.sql
    assert conn.params == (
        "token-radar-v13-social-attention",
        "5m",
        "matched",
        cutoff_ms,
    )


def test_publish_current_generation_rejects_stale_projection_writer():
    conn = FakeStalePublishConn(existing_computed_at_ms=1_700_000_100_000)

    result = TokenRadarRepository(conn).publish_current_generation(
        projection_version="token-radar-v13-social-attention",
        window="5m",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        generation_id="gen-old",
        published_at_ms=1_700_000_000_000,
        source_frontier_ms=1_700_000_000_000,
        rows=[],
    )

    assert result == {"status": "stale_skipped", "generation_id": "gen-old", "rows_written": 0}
    assert not any("DELETE FROM" in sql for sql in conn.sqls)


def test_publish_current_generation_rejects_stale_writer_after_newer_zero_row_publication():
    conn = FakeStalePublishConn(existing_computed_at_ms=1_700_000_100_000)

    result = TokenRadarRepository(conn).publish_current_generation(
        projection_version="token-radar-v13-social-attention",
        window="5m",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        generation_id="gen-old",
        published_at_ms=1_700_000_000_000,
        source_frontier_ms=1_700_000_000_000,
        rows=[_valid_factor_row()],
    )

    assert result == {"status": "stale_skipped", "generation_id": "gen-old", "rows_written": 0}
    watermark_sql = conn.sqls[1]
    assert "FROM token_radar_publication_state" in watermark_sql
    assert "current_published_at_ms" in watermark_sql
    assert "token_radar_projection_coverage" not in watermark_sql
    assert not any("INSERT INTO token_radar_current_rows" in sql for sql in conn.sqls)


def test_mark_publication_failed_records_failed_attempt_without_replacing_current_generation():
    conn = FakeConn()

    TokenRadarRepository(conn).mark_publication_failed(
        projection_version="token-radar-v13-social-attention",
        window="1h",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        generation_id="gen-failed",
        started_at_ms=1_778_000_000_000,
        finished_at_ms=1_778_000_060_000,
        error="payload_hash changed during selected-row hydration",
    )

    assert "INSERT INTO token_radar_publication_state" in conn.sql
    assert "latest_attempt_status" in conn.sql
    assert "current_generation_id" not in conn.sql.split("DO UPDATE SET", 1)[1]
    assert conn.params[4] == "gen-failed"
    assert conn.params[5] == "failed"


def test_latest_publication_state_reads_state_for_requested_sets():
    conn = FakeConn(
        rows=[
            {
                "window": "1h",
                "scope": "all",
                "venue": TOKEN_RADAR_DEFAULT_VENUE,
                "latest_attempt_status": "failed",
                "latest_attempt_started_at_ms": 1_778_000_000_000,
                "latest_attempt_finished_at_ms": 1_778_000_001_000,
                "updated_at_ms": 1_778_000_002_000,
            }
        ]
    )

    state = TokenRadarRepository(conn).latest_publication_state(
        projection_version="token-radar-v13-social-attention",
        windows=("1h",),
        scopes=("all",),
        venues=(TOKEN_RADAR_DEFAULT_VENUE,),
    )

    assert state[("1h", "all", TOKEN_RADAR_DEFAULT_VENUE)]["latest_attempt_status"] == "failed"
    assert state[("1h", "all", TOKEN_RADAR_DEFAULT_VENUE)]["latest_attempt_started_at_ms"] == 1_778_000_000_000
    assert state[("1h", "all", TOKEN_RADAR_DEFAULT_VENUE)]["latest_attempt_finished_at_ms"] == 1_778_000_001_000
    assert state[("1h", "all", TOKEN_RADAR_DEFAULT_VENUE)]["updated_at_ms"] == 1_778_000_002_000
    assert "FROM requested" in conn.sql
    assert "JOIN token_radar_publication_state state" in conn.sql
    assert "token_radar_projection_coverage" not in conn.sql


class FakeConn:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        *,
        rowcount: Any = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self.sql = ""
        self.params = ()
        self.calls = 0
        self.rows = rows or []
        self.info = SimpleNamespace(transaction_status=pq.TransactionStatus.INTRANS)
        if not omit_rowcount:
            self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.calls += 1
        self.sql = str(sql)
        self.params = params or ()
        return self

    def fetchone(self):
        if self.rows:
            return self.rows[0]
        return {"computed_at_ms": 1_700_000_000_000}

    def fetchall(self):
        return self.rows


class FakePublishConn:
    def __init__(
        self,
        *,
        existing_current: dict[str, Any] | None = None,
        publication_state: dict[str, Any] | None = None,
        current_rowcount: Any = 1,
        omit_current_rowcount: bool = False,
        active_transaction: bool = True,
    ) -> None:
        self.sqls: list[str] = []
        self.existing_current = existing_current
        self.publication_state = publication_state or {
            "current_generation_id": None,
            "current_published_at_ms": None,
        }
        self.current_insert_params: dict[str, Any] = {}
        self.publication_state_params: dict[str, Any] = {}
        self._last_rows: list[dict[str, Any]] = []
        self._current_rowcount = current_rowcount
        self._omit_current_rowcount = omit_current_rowcount
        if not self._omit_current_rowcount:
            self.rowcount = self._current_rowcount
        self.info = SimpleNamespace(
            transaction_status=(pq.TransactionStatus.INTRANS if active_transaction else pq.TransactionStatus.IDLE)
        )

    def execute(self, sql, params=None):
        text = str(sql)
        self.sqls.append(text)
        self._last_rows = []
        if "FROM token_radar_publication_state" in text:
            self._last_rows = [self.publication_state]
        if "SELECT *" in text and "FROM token_radar_current_rows" in text:
            self._last_rows = [self.existing_current] if self.existing_current is not None else []
        if "INSERT INTO token_radar_current_rows" in text:
            self.current_insert_params = dict(params or {})
            if self._omit_current_rowcount:
                if hasattr(self, "rowcount"):
                    delattr(self, "rowcount")
            else:
                self.rowcount = self._current_rowcount
        if "INSERT INTO token_radar_publication_state" in text:
            self.publication_state_params = dict(params or {})
            if not self._omit_current_rowcount:
                self.rowcount = 1
        return self

    def fetchone(self):
        if self._last_rows:
            return self._last_rows[0]
        return {"current_published_at_ms": None}

    def fetchall(self):
        return self._last_rows


class NoTransactionConn:
    def __init__(self) -> None:
        self.sqls: list[str] = []
        self.info = SimpleNamespace(transaction_status=pq.TransactionStatus.IDLE)

    def execute(self, sql, params=None):
        self.sqls.append(str(sql))
        raise AssertionError("repository-owned writes must require conn.transaction() before SQL")


class FakeTransaction:
    def __init__(self, conn: TransactionalFakePublishConn) -> None:
        self.conn = conn

    def __enter__(self):
        self.conn.transaction_entries += 1
        self.conn.info.transaction_status = pq.TransactionStatus.INTRANS
        return self

    def __exit__(self, exc_type, exc, tb):
        self.conn.info.transaction_status = pq.TransactionStatus.IDLE
        return False


class TransactionalFakePublishConn(FakePublishConn):
    def __init__(self) -> None:
        super().__init__(active_transaction=False)
        self.transaction_entries = 0

    def transaction(self):
        return FakeTransaction(self)

    def commit(self):
        raise AssertionError("repository-owned writes must use conn.transaction(), not conn.commit()")


class FakeStalePublishConn:
    def __init__(self, *, existing_computed_at_ms: int):
        self.existing_computed_at_ms = existing_computed_at_ms
        self.sqls: list[str] = []
        self.info = SimpleNamespace(transaction_status=pq.TransactionStatus.INTRANS)

    def execute(self, sql, params=None):
        self.sqls.append(str(sql))
        return self

    def fetchone(self):
        return {"current_published_at_ms": self.existing_computed_at_ms}

    def commit(self):
        raise AssertionError("stale writer should not commit")


def _valid_factor_row() -> dict[str, object]:
    return {
        "row_id": "row-factor-1",
        "source_max_received_at_ms": 1_778_000_000_000,
        "lane": "resolved",
        "rank": 1,
        "intent_id": "intent-1",
        "event_id": "event-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "target_type": "Asset",
        "target_id": "asset-1",
        "pricefeed_id": "feed-1",
        "intent_json": {"intent_id": "intent-1", "event_id": "event-1", "display_symbol": "BOV"},
        "resolution_json": {
            "status": "EXACT",
            "reason_codes": [],
            "candidate_ids": [],
            "lookup_keys": [],
        },
        "factor_snapshot_json": _valid_factor_snapshot(),
        "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "decision": "discard",
        "rank_score": 12,
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "data_health_json": {"factor_snapshot": "ready"},
        "source_event_ids_json": ["event-1"],
        "created_at_ms": 1_778_000_000_000,
    }


def _valid_factor_snapshot(*, rank_score: object = 12) -> dict[str, object]:
    return {
        "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "subject": {
            "target_type": "Asset",
            "target_id": "asset-1",
            "symbol": "BOV",
            "target_market_type": "dex",
            "chain": "solana",
            "address": "asset-address-1",
            "pricefeed_id": "feed-1",
        },
        "market": {
            "event_anchor": {
                "target_type": "Asset",
                "target_id": "asset-1",
                "observed_at_ms": 1_778_000_000_000,
                "received_at_ms": 1_778_000_000_000,
                "source": "event_anchor",
                "provider": "okx",
                "pricefeed_id": "feed-1",
                "price_usd": 1.0,
                "price_quote": None,
                "quote_symbol": "USD",
                "price_basis": "usd",
                "market_cap_usd": None,
                "liquidity_usd": None,
                "holders": None,
                "volume_24h_usd": None,
                "open_interest_usd": None,
            },
            "decision_latest": {
                "target_type": "Asset",
                "target_id": "asset-1",
                "observed_at_ms": 1_778_000_030_000,
                "received_at_ms": 1_778_000_030_000,
                "source": "decision_latest",
                "provider": "okx",
                "pricefeed_id": "feed-1",
                "price_usd": 1.1,
                "price_quote": None,
                "quote_symbol": "USD",
                "price_basis": "usd",
                "market_cap_usd": 1_000_000,
                "liquidity_usd": 250_000,
                "holders": 1000,
                "volume_24h_usd": 12_000,
                "open_interest_usd": None,
            },
            "readiness": {
                "anchor_status": "ready",
                "latest_status": "fresh",
                "dex_floor_status": "ready",
                "missing_fields": [],
                "stale_fields": [],
            },
        },
        "families": {
            "social_heat": {
                "raw_score": rank_score,
                "score": rank_score,
                "weight": 1,
                "data_health": "ready",
                "facts": {"volume_24h_usd": 1000},
                "factors": {},
            },
            "social_propagation": {
                "raw_score": 10,
                "score": 10,
                "weight": 1,
                "data_health": "ready",
                "facts": {},
                "factors": {},
            },
            "semantic_catalyst": {
                "raw_score": 10,
                "score": 10,
                "weight": 1,
                "data_health": "ready",
                "facts": {},
                "factors": {},
            },
            "timing_risk": {
                "raw_score": 10,
                "score": 10,
                "weight": 1,
                "data_health": "ready",
                "facts": {},
                "factors": {},
            },
        },
        "composite": {
            "raw_alpha_score": rank_score,
            "rank_score": rank_score,
            "family_scores": {
                "social_heat": rank_score,
                "social_propagation": 10,
                "semantic_catalyst": 10,
                "timing_risk": 10,
            },
            "recommended_decision": "discard",
        },
        "gates": {
            "eligible_for_high_alert": False,
            "max_decision": "discard",
            "blocked_reasons": [],
            "risk_reasons": [],
        },
        "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
        "normalization": {
            "status": "ranked",
            "cohort_status": "ready",
            "cohort": {},
            "factor_ranks": {
                "social_heat": None,
                "social_propagation": None,
                "semantic_catalyst": None,
                "timing_risk": None,
            },
            "alpha_rank": None,
        },
        "provenance": {
            "computed_at_ms": 1_778_000_000_000,
            "source_event_ids": ["event-1"],
        },
    }
