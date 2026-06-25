from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from parallax.domains.news_intel.repositories.news_repository import NewsRepository, _source_status_payload
from parallax.domains.news_intel.runtime.news_source_quality_projection_worker import (
    NewsSourceQualityProjectionWorker,
    _future_source_quality_targets,
)
from parallax.domains.news_intel.services.source_quality_projection import (
    SOURCE_QUALITY_PROJECTION_VERSION,
    build_source_quality_row,
    build_source_quality_rows,
    quality_score,
    quality_status,
)

NOW_MS = 1_779_000_000_000
DAY_MS = 24 * 60 * 60 * 1000


def _source_status_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "source_id": "coindesk",
        "provider_type": "rss",
        "source_domain": "coindesk.com",
        "source_name": "CoinDesk",
        "source_role": "specialist_media",
        "trust_tier": "high",
        "coverage_tags_json": ["crypto_market"],
        "source_quality_status": "healthy",
        "enabled": True,
        "managed_by_config": True,
        "refresh_interval_seconds": 300,
        "item_count": 4,
        "sync_high_watermark_ms": 0,
        "sync_overlap_ms": 0,
        "next_fetch_after_ms": 0,
        "consecutive_failures": 0,
    }
    row.update(overrides)
    return row


def _latest_quality_json(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "row_id": "news-source-quality:coindesk:24h",
        "source_id": "coindesk",
        "window": "24h",
        "computed_at_ms": NOW_MS,
        "fetch_success_rate": 1,
        "items_fetched": 10,
        "items_inserted": 8,
        "duplicate_rate": 0.2,
        "process_success_rate": 1,
        "resolved_token_rate": 0.75,
        "attention_rate": 0.25,
        "accepted_fact_rate": 0.5,
        "brief_ready_rate": 0.5,
        "median_lag_ms": 500,
        "quality_score": 82.5,
        "diagnostics_json": {
            "counts": {"fetch_run_count": 4},
            "status": "healthy",
        },
        "projection_version": SOURCE_QUALITY_PROJECTION_VERSION,
    }
    row.update(overrides)
    return row


def _source_quality_write_row(**overrides: object) -> dict[str, object]:
    row = _latest_quality_json()
    row["diagnostics_json"] = {"status": "healthy"}
    row.update(overrides)
    return row


def test_source_quality_score_is_deterministic() -> None:
    metrics = {
        "fetch_success_rate": 1.0,
        "process_success_rate": 1.0,
        "resolved_token_rate": 0.8,
        "brief_ready_rate": 0.5,
        "duplicate_rate": 0.2,
        "normalized_freshness": 0.9,
        "useful_fact_rate": 0.6,
    }

    row = build_source_quality_row(
        source_id="coindesk",
        window="24h",
        computed_at_ms=1_000,
        metrics=metrics,
        counts={"items_fetched": 10, "items_inserted": 8, "median_lag_ms": 500},
    )

    assert quality_score(metrics) == 82.5
    assert row["row_id"] == "news-source-quality:coindesk:24h"
    assert row["quality_score"] == 82.5
    assert row["projection_version"] == SOURCE_QUALITY_PROJECTION_VERSION
    assert row["diagnostics_json"]["metrics"] == metrics
    assert row["diagnostics_json"]["status"] == "healthy"


def test_build_source_quality_rows_derives_metrics_from_aggregate_inputs() -> None:
    rows = build_source_quality_rows(
        aggregate_inputs=[
            {
                "source_id": "coindesk",
                "fetch_run_count": 4,
                "fetch_success_count": 3,
                "items_fetched": 10,
                "items_inserted": 6,
                "items_duplicate": 2,
                "item_count": 5,
                "processed_item_count": 4,
                "mention_count": 4,
                "resolved_mention_count": 3,
                "attention_fact_count": 1,
                "accepted_fact_count": 2,
                "fact_count": 4,
                "ready_brief_count": 2,
                "useful_item_count": 2,
                "latest_item_published_at_ms": NOW_MS - 6 * 60 * 60 * 1000,
                "median_lag_ms": 3_000,
            }
        ],
        window="24h",
        window_ms=DAY_MS,
        computed_at_ms=NOW_MS,
    )

    assert rows == [
        {
            "row_id": "news-source-quality:coindesk:24h",
            "source_id": "coindesk",
            "window": "24h",
            "computed_at_ms": NOW_MS,
            "fetch_success_rate": 0.75,
            "items_fetched": 10,
            "items_inserted": 6,
            "duplicate_rate": 0.2,
            "process_success_rate": 0.8,
            "resolved_token_rate": 0.75,
            "attention_rate": 0.25,
            "accepted_fact_rate": 0.5,
            "brief_ready_rate": 0.4,
            "median_lag_ms": 3_000,
            "quality_score": 67.5,
            "diagnostics_json": {
                "counts": {
                    "accepted_fact_count": 2,
                    "attention_fact_count": 1,
                    "fact_count": 4,
                    "fetch_run_count": 4,
                    "fetch_success_count": 3,
                    "items_duplicate": 2,
                    "items_fetched": 10,
                    "items_inserted": 6,
                    "item_count": 5,
                    "median_lag_ms": 3_000,
                    "mention_count": 4,
                    "processed_item_count": 4,
                    "ready_brief_count": 2,
                    "resolved_mention_count": 3,
                    "useful_item_count": 2,
                },
                "metrics": {
                    "accepted_fact_rate": 0.5,
                    "attention_rate": 0.25,
                    "brief_ready_rate": 0.4,
                    "duplicate_rate": 0.2,
                    "fetch_success_rate": 0.75,
                    "normalized_freshness": 0.75,
                    "process_success_rate": 0.8,
                    "resolved_token_rate": 0.75,
                    "useful_fact_rate": 0.4,
                },
                "status": "watch",
                "window_ms": DAY_MS,
            },
            "projection_version": SOURCE_QUALITY_PROJECTION_VERSION,
        }
    ]


@pytest.mark.parametrize("value", [True, "4", 4.5, -1])
def test_build_source_quality_rows_rejects_malformed_present_count_without_int_repair(value: object) -> None:
    with pytest.raises(ValueError, match="news_source_quality_projection_count_item_count_required"):
        build_source_quality_rows(
            aggregate_inputs=[
                {
                    "source_id": "coindesk",
                    "fetch_run_count": 4,
                    "fetch_success_count": 3,
                    "items_fetched": 10,
                    "items_inserted": 6,
                    "items_duplicate": 2,
                    "item_count": value,
                    "processed_item_count": 4,
                    "mention_count": 4,
                    "resolved_mention_count": 3,
                    "attention_fact_count": 1,
                    "accepted_fact_count": 2,
                    "fact_count": 4,
                    "ready_brief_count": 2,
                    "useful_item_count": 2,
                    "latest_item_published_at_ms": NOW_MS - 6 * 60 * 60 * 1000,
                    "median_lag_ms": 3_000,
                }
            ],
            window="24h",
            window_ms=DAY_MS,
            computed_at_ms=NOW_MS,
        )


@pytest.mark.parametrize("value", [True, "3000", 3000.5, -1])
def test_build_source_quality_rows_rejects_malformed_optional_timing_without_int_repair(value: object) -> None:
    with pytest.raises(ValueError, match="news_source_quality_projection_latest_item_published_at_ms_required"):
        build_source_quality_rows(
            aggregate_inputs=[
                {
                    "source_id": "coindesk",
                    "fetch_run_count": 4,
                    "fetch_success_count": 3,
                    "items_fetched": 10,
                    "items_inserted": 6,
                    "items_duplicate": 2,
                    "item_count": 5,
                    "processed_item_count": 4,
                    "mention_count": 4,
                    "resolved_mention_count": 3,
                    "attention_fact_count": 1,
                    "accepted_fact_count": 2,
                    "fact_count": 4,
                    "ready_brief_count": 2,
                    "useful_item_count": 2,
                    "latest_item_published_at_ms": value,
                    "median_lag_ms": 3_000,
                }
            ],
            window="24h",
            window_ms=DAY_MS,
            computed_at_ms=NOW_MS,
        )


@pytest.mark.parametrize("value", [True, "3000", 3000.5, -1])
def test_build_source_quality_row_rejects_malformed_median_lag_without_int_repair(value: object) -> None:
    with pytest.raises(ValueError, match=r"news_source_quality_projection_(count_)?median_lag_ms_required"):
        build_source_quality_row(
            source_id="coindesk",
            window="24h",
            computed_at_ms=NOW_MS,
            metrics={"fetch_success_rate": 1.0},
            counts={"items_fetched": 10, "items_inserted": 8, "median_lag_ms": value},
        )


def test_quality_status_buckets_unknown_and_operational_ranges() -> None:
    assert quality_status(None) == "unknown"
    assert quality_status(24.99) == "poor"
    assert quality_status(25.0) == "degraded"
    assert quality_status(50.0) == "watch"
    assert quality_status(75.0) == "healthy"


def test_useful_item_count_is_not_double_counted_by_projection() -> None:
    rows = build_source_quality_rows(
        aggregate_inputs=[
            {
                "source_id": "coindesk",
                "fetch_run_count": 1,
                "fetch_success_count": 1,
                "items_fetched": 1,
                "items_inserted": 1,
                "items_duplicate": 0,
                "item_count": 2,
                "processed_item_count": 2,
                "mention_count": 0,
                "resolved_mention_count": 0,
                "fact_count": 1,
                "accepted_fact_count": 1,
                "attention_fact_count": 0,
                "ready_brief_count": 0,
                "useful_item_count": 1,
                "latest_item_published_at_ms": NOW_MS,
            }
        ],
        window="24h",
        window_ms=DAY_MS,
        computed_at_ms=NOW_MS,
    )

    assert rows[0]["diagnostics_json"]["metrics"]["useful_fact_rate"] == 0.5


def test_source_quality_projection_worker_builds_rows_for_configured_windows() -> None:
    repo = FakeSourceQualityRepository()
    db = FakeSourceQualityDB(
        repo,
        claimed=[_source_quality_claim("coindesk", window="_refresh")],
    )
    worker = NewsSourceQualityProjectionWorker(
        name="news_source_quality_projection",
        settings=SimpleNamespace(
            batch_size=100,
            lease_ms=120_000,
            retry_ms=30_000,
            max_attempts=3,
            statement_timeout_seconds=30,
            windows=("4h", "24h"),
        ),
        db=db,
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync()

    assert result.processed == 2
    assert db.sessions == ["news_source_quality_projection"]
    assert repo.list_calls == [
        {"source_windows": [("coindesk", "4h"), ("coindesk", "24h")], "now_ms": NOW_MS},
    ]
    assert [row["window"] for row in repo.rows] == ["4h", "24h"]
    assert repo.status_windows == ["4h"]
    assert all(row["source_id"] == "coindesk" for row in repo.rows)
    assert db.dirty.marked_done == [[_source_quality_claim("coindesk", window="_refresh")]]


def test_source_quality_page_dirty_uses_latest_item_watermark_not_worker_now() -> None:
    latest_item_published_at_ms = NOW_MS - 40_000
    repo = FakeSourceQualityRepository(
        changed_source_ids=["coindesk"],
        item_ids_by_source={"coindesk": ["news-1", "news-2"]},
        latest_item_published_at_ms=latest_item_published_at_ms,
    )
    db = FakeSourceQualityDB(
        repo,
        claimed=[_source_quality_claim("coindesk", window="24h")],
    )
    worker = NewsSourceQualityProjectionWorker(
        name="news_source_quality_projection",
        settings=SimpleNamespace(
            batch_size=100,
            lease_ms=120_000,
            retry_ms=30_000,
            max_attempts=3,
            statement_timeout_seconds=30,
            windows=("24h",),
        ),
        db=db,
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync()

    page_dirty = [call for call in db.dirty.enqueued if call["reason"] == "source_quality_status_changed"]
    assert result.notes["page_dirty"] == 2
    assert len(page_dirty) == 1
    assert [row["target_id"] for row in page_dirty[0]["rows"]] == ["news-1", "news-2"]
    assert {row["source_watermark_ms"] for row in page_dirty[0]["rows"]} == {latest_item_published_at_ms}


def test_source_quality_projection_worker_empty_dirty_queue_does_not_scan_sources() -> None:
    repo = FakeSourceQualityRepository()
    db = FakeSourceQualityDB(repo, claimed=[])
    worker = NewsSourceQualityProjectionWorker(
        name="news_source_quality_projection",
        settings=SimpleNamespace(
            batch_size=100,
            lease_ms=120_000,
            retry_ms=30_000,
            max_attempts=3,
            statement_timeout_seconds=30,
            windows=("24h", "7d"),
        ),
        db=db,
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync()

    assert result.processed == 0
    assert result.notes["claimed"] == 0
    assert repo.list_calls == []


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        pytest.param("source_id", None, "news_source_quality_future_target_source_id_required", id="source_none"),
        pytest.param("source_id", "", "news_source_quality_future_target_source_id_required", id="source_blank"),
        pytest.param("window", None, "news_source_quality_future_target_window_required", id="window_none"),
        pytest.param("window", "", "news_source_quality_future_target_window_required", id="window_blank"),
        pytest.param("item_count", None, "news_source_quality_future_target_item_count_required", id="count_none"),
        pytest.param("item_count", True, "news_source_quality_future_target_item_count_required", id="count_bool"),
        pytest.param("item_count", "1", "news_source_quality_future_target_item_count_required", id="count_string"),
    ],
)
def test_future_source_quality_targets_require_explicit_aggregate_identity_and_count(
    field: str,
    value: object,
    match: str,
) -> None:
    row: dict[str, object] = {
        "source_id": "coindesk",
        "window": "24h",
        "item_count": 1,
        "latest_item_published_at_ms": NOW_MS - 1_000,
    }
    row[field] = value

    with pytest.raises(ValueError, match=match):
        _future_source_quality_targets([row], now_ms=NOW_MS)


def test_future_source_quality_targets_allow_zero_item_count_without_reschedule() -> None:
    assert (
        _future_source_quality_targets(
            [{"source_id": "coindesk", "window": "24h", "item_count": 0}],
            now_ms=NOW_MS,
        )
        == []
    )


def test_source_status_payload_uses_plain_quality_diagnostics() -> None:
    payload = _source_status_payload(
        {
            "source_id": "coindesk",
            "provider_type": "rss",
            "source_domain": "coindesk.com",
            "source_name": "CoinDesk",
            "source_role": "specialist_media",
            "trust_tier": "high",
            "coverage_tags_json": ["crypto_market"],
            "source_quality_status": "healthy",
            "enabled": True,
            "managed_by_config": True,
            "refresh_interval_seconds": 300,
            "item_count": 4,
            "latest_item_published_at_ms": NOW_MS - 40_000,
            "latest_item_fetched_at_ms": NOW_MS - 30_000,
            "latest_fetch_run_json": {
                "status": "failed",
                "started_at_ms": NOW_MS - 10_000,
                "finished_at_ms": NOW_MS - 9_000,
                "http_status": 503,
                "fetched_count": 0,
                "inserted_count": 0,
                "updated_count": 0,
                "duplicate_count": 0,
                "error": "upstream timeout",
            },
            "last_success_at_ms": NOW_MS - 50_000,
            "sync_high_watermark_ms": 0,
            "sync_overlap_ms": 0,
            "next_fetch_after_ms": 0,
            "consecutive_failures": 1,
            "last_error": "upstream timeout",
            "latest_quality_json": {
                "row_id": "news-source-quality:coindesk:24h",
                "source_id": "coindesk",
                "window": "24h",
                "computed_at_ms": NOW_MS,
                "fetch_success_rate": 1,
                "items_fetched": 10,
                "items_inserted": 8,
                "duplicate_rate": 0.2,
                "process_success_rate": 1,
                "resolved_token_rate": 0.75,
                "attention_rate": 0.25,
                "accepted_fact_rate": 0.5,
                "brief_ready_rate": 0.5,
                "median_lag_ms": 500,
                "quality_score": 82.5,
                "diagnostics_json": {
                    "counts": {"fetch_run_count": 4},
                    "status": "healthy",
                },
                "projection_version": SOURCE_QUALITY_PROJECTION_VERSION,
            },
        }
    )

    assert payload["coverage_tags"] == ["crypto_market"]
    assert payload["quality"]["diagnostics_json"]["status"] == "healthy"
    assert payload["latest_quality_counts"] == {"fetch_run_count": 4}
    assert payload["latest_item_published_at_ms"] == NOW_MS - 40_000
    assert payload["latest_item_fetched_at_ms"] == NOW_MS - 30_000
    assert payload["last_seen_at_ms"] == NOW_MS - 30_000
    assert payload["latest_fetch_run"] == {
        "status": "failed",
        "started_at_ms": NOW_MS - 10_000,
        "finished_at_ms": NOW_MS - 9_000,
        "http_status": 503,
        "fetched_count": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "duplicate_count": 0,
        "error": "upstream timeout",
    }
    assert payload["provider_health"] == {
        "status": "failing",
        "reason": "consecutive_failures",
        "last_error": "upstream timeout",
        "consecutive_failures": 1,
        "last_success_at_ms": NOW_MS - 50_000,
        "last_seen_at_ms": NOW_MS - 30_000,
    }
    assert payload["provider_capability_tags"] == [
        "poll_primary_items",
        "http_cache",
        "high_trust",
    ]
    json.dumps(payload)


@pytest.mark.parametrize(
    "coverage_tags_json",
    [
        "crypto_market",
        {"tag": "crypto_market"},
        ["crypto_market", {"tag": "macro"}],
    ],
)
def test_source_status_payload_rejects_malformed_present_coverage_tags(
    coverage_tags_json: object,
) -> None:
    with pytest.raises(ValueError, match="news_source_status_coverage_tags_json_required"):
        _source_status_payload(_source_status_row(coverage_tags_json=coverage_tags_json, latest_quality_json=None))


@pytest.mark.parametrize(
    ("field_name", "value", "error"),
    [
        ("source_id", None, "news_source_status_source_id_required"),
        ("source_id", " ", "news_source_status_source_id_required"),
        ("provider_type", None, "news_source_status_provider_type_required"),
        ("provider_type", " ", "news_source_status_provider_type_required"),
        ("source_domain", None, "news_source_status_source_domain_required"),
        ("source_domain", 123, "news_source_status_source_domain_required"),
        ("source_name", None, "news_source_status_source_name_required"),
        ("source_role", None, "news_source_status_source_role_required"),
        ("trust_tier", None, "news_source_status_trust_tier_required"),
        ("source_quality_status", None, "news_source_status_source_quality_status_required"),
        ("source_quality_status", " ", "news_source_status_source_quality_status_required"),
    ],
)
def test_source_status_payload_rejects_malformed_source_identity_fields(
    field_name: str,
    value: object,
    error: str,
) -> None:
    row = _source_status_row(latest_quality_json=None)
    row[field_name] = value

    with pytest.raises(ValueError, match=error):
        _source_status_payload(row)


@pytest.mark.parametrize(
    ("field_name", "value", "error"),
    [
        ("enabled", None, "news_source_status_enabled_required"),
        ("enabled", "true", "news_source_status_enabled_required"),
        ("managed_by_config", None, "news_source_status_managed_by_config_required"),
        ("managed_by_config", 1, "news_source_status_managed_by_config_required"),
    ],
)
def test_source_status_payload_rejects_malformed_boolean_fields(
    field_name: str,
    value: object,
    error: str,
) -> None:
    row = _source_status_row(latest_quality_json=None)
    row[field_name] = value

    with pytest.raises(ValueError, match=error):
        _source_status_payload(row)


@pytest.mark.parametrize(
    ("field_name", "value", "error"),
    [
        ("refresh_interval_seconds", None, "news_source_status_refresh_interval_seconds_required"),
        ("refresh_interval_seconds", "300", "news_source_status_refresh_interval_seconds_required"),
        ("refresh_interval_seconds", True, "news_source_status_refresh_interval_seconds_required"),
        ("refresh_interval_seconds", -1, "news_source_status_refresh_interval_seconds_required"),
        ("item_count", None, "news_source_status_item_count_required"),
        ("sync_high_watermark_ms", None, "news_source_status_sync_high_watermark_ms_required"),
        ("sync_overlap_ms", "0", "news_source_status_sync_overlap_ms_required"),
        ("next_fetch_after_ms", None, "news_source_status_next_fetch_after_ms_required"),
        ("consecutive_failures", "0", "news_source_status_consecutive_failures_required"),
    ],
)
def test_source_status_payload_rejects_malformed_counter_fields(
    field_name: str,
    value: object,
    error: str,
) -> None:
    row = _source_status_row(latest_quality_json=None)
    row[field_name] = value

    with pytest.raises(ValueError, match=error):
        _source_status_payload(row)


@pytest.mark.parametrize(
    ("field_name", "value", "error"),
    [
        ("latest_quality_json", "ready", "news_source_status_latest_quality_json_required"),
        ("latest_fetch_run_json", ["failed"], "news_source_status_latest_fetch_run_json_required"),
        ("sync_diagnostics_json", "{}", "news_source_status_sync_diagnostics_json_required"),
        ("dedup_diagnostics_json", ["dedup"], "news_source_status_dedup_diagnostics_json_required"),
    ],
)
def test_source_status_payload_rejects_malformed_present_diagnostic_sections(
    field_name: str,
    value: object,
    error: str,
) -> None:
    row = _source_status_row(latest_quality_json=None)
    row[field_name] = value
    with pytest.raises(ValueError, match=error):
        _source_status_payload(row)


@pytest.mark.parametrize(
    ("field_name", "error"),
    [
        ("latest_quality_json", "news_source_status_latest_quality_row_id_required"),
        ("latest_fetch_run_json", "news_source_status_latest_fetch_run_status_required"),
    ],
)
def test_source_status_payload_rejects_empty_present_optional_sections(field_name: str, error: str) -> None:
    row = _source_status_row(latest_quality_json=None)
    row[field_name] = {}

    with pytest.raises(ValueError, match=error):
        _source_status_payload(row)


@pytest.mark.parametrize(
    ("latest_fetch_run_update", "error"),
    [
        ({"status": None}, "news_source_status_latest_fetch_run_status_required"),
        ({"status": " "}, "news_source_status_latest_fetch_run_status_required"),
        ({"fetched_count": None}, "news_source_status_latest_fetch_run_fetched_count_required"),
        ({"fetched_count": "0"}, "news_source_status_latest_fetch_run_fetched_count_required"),
        ({"inserted_count": None}, "news_source_status_latest_fetch_run_inserted_count_required"),
        ({"updated_count": True}, "news_source_status_latest_fetch_run_updated_count_required"),
        ({"duplicate_count": -1}, "news_source_status_latest_fetch_run_duplicate_count_required"),
    ],
)
def test_source_status_payload_rejects_malformed_latest_fetch_run_scalars(
    latest_fetch_run_update: dict[str, object],
    error: str,
) -> None:
    latest_fetch_run_json: dict[str, object] = {
        "status": "failed",
        "started_at_ms": NOW_MS - 10_000,
        "finished_at_ms": NOW_MS - 9_000,
        "http_status": 503,
        "fetched_count": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "duplicate_count": 0,
    }
    latest_fetch_run_json.update(latest_fetch_run_update)

    with pytest.raises(ValueError, match=error):
        _source_status_payload(
            _source_status_row(latest_quality_json=None, latest_fetch_run_json=latest_fetch_run_json)
        )


@pytest.mark.parametrize(
    ("latest_quality_json", "error"),
    [
        (
            _latest_quality_json(diagnostics_json="healthy"),
            "news_source_status_latest_quality_diagnostics_json_required",
        ),
        (
            {key: value for key, value in _latest_quality_json().items() if key != "diagnostics_json"},
            "news_source_status_latest_quality_diagnostics_json_required",
        ),
        (
            _latest_quality_json(diagnostics_json={"counts": {"fetch_run_count": 1}}),
            "news_source_status_latest_quality_diagnostics_status_required",
        ),
        (
            _latest_quality_json(diagnostics_json={"status": " "}),
            "news_source_status_latest_quality_diagnostics_status_required",
        ),
    ],
)
def test_source_status_payload_rejects_malformed_latest_quality_diagnostics(
    latest_quality_json: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        _source_status_payload(_source_status_row(latest_quality_json=latest_quality_json))


@pytest.mark.parametrize(
    ("latest_quality_update", "error"),
    [
        ({"row_id": None}, "news_source_status_latest_quality_row_id_required"),
        ({"row_id": " "}, "news_source_status_latest_quality_row_id_required"),
        ({"source_id": None}, "news_source_status_latest_quality_source_id_required"),
        ({"source_id": 123}, "news_source_status_latest_quality_source_id_required"),
        ({"window": ""}, "news_source_status_latest_quality_window_required"),
        ({"projection_version": None}, "news_source_status_latest_quality_projection_version_required"),
        ({"computed_at_ms": None}, "news_source_status_latest_quality_computed_at_ms_required"),
        ({"computed_at_ms": True}, "news_source_status_latest_quality_computed_at_ms_required"),
        ({"computed_at_ms": "1000"}, "news_source_status_latest_quality_computed_at_ms_required"),
        ({"items_fetched": None}, "news_source_status_latest_quality_items_fetched_required"),
        ({"items_fetched": "10"}, "news_source_status_latest_quality_items_fetched_required"),
        ({"items_fetched": True}, "news_source_status_latest_quality_items_fetched_required"),
        ({"items_fetched": -1}, "news_source_status_latest_quality_items_fetched_required"),
        ({"items_inserted": None}, "news_source_status_latest_quality_items_inserted_required"),
        ({"items_inserted": "8"}, "news_source_status_latest_quality_items_inserted_required"),
        ({"items_inserted": -1}, "news_source_status_latest_quality_items_inserted_required"),
        ({"median_lag_ms": "500"}, "news_source_status_latest_quality_median_lag_ms_required"),
        ({"median_lag_ms": True}, "news_source_status_latest_quality_median_lag_ms_required"),
        ({"median_lag_ms": -1}, "news_source_status_latest_quality_median_lag_ms_required"),
    ],
)
def test_source_status_payload_rejects_malformed_latest_quality_scalars(
    latest_quality_update: dict[str, object],
    error: str,
) -> None:
    latest_quality_json = _latest_quality_json()
    latest_quality_json.update(latest_quality_update)

    with pytest.raises(ValueError, match=error):
        _source_status_payload(_source_status_row(latest_quality_json=latest_quality_json))


def test_source_status_payload_redacts_secret_error_fragments() -> None:
    secret_error = (
        "GET https://api.example.test/feed?api_key=sk-live&token=raw-token\n"
        "https://api-token@example.test failed\n"
        "upstream says Bearer bearer-secret expired\n"
        "Authorization: Basic basic-secret\n"
        "Cookie: sid=session-secret; refresh=refresh-secret\n"
        "api_key='quoted secret with spaces'\n"
        "postgres://user:pg-secret@db"
    )

    payload = _source_status_payload(
        {
            "source_id": "coindesk",
            "provider_type": "rss",
            "source_domain": "coindesk.com",
            "source_name": "CoinDesk",
            "source_role": "specialist_media",
            "trust_tier": "high",
            "coverage_tags_json": [],
            "source_quality_status": "unknown",
            "enabled": True,
            "managed_by_config": True,
            "refresh_interval_seconds": 300,
            "item_count": 0,
            "sync_high_watermark_ms": 0,
            "sync_overlap_ms": 0,
            "next_fetch_after_ms": 0,
            "consecutive_failures": 1,
            "last_error": secret_error,
            "latest_fetch_run_json": {
                "status": "failed",
                "started_at_ms": NOW_MS,
                "finished_at_ms": NOW_MS + 1,
                "fetched_count": 0,
                "inserted_count": 0,
                "updated_count": 0,
                "duplicate_count": 0,
                "error": secret_error,
            },
            "latest_quality_json": None,
        }
    )

    returned_errors = (
        payload["last_error"],
        payload["provider_health"]["last_error"],
        payload["latest_fetch_run"]["error"],
    )
    for returned_error in returned_errors:
        assert returned_error is not None
        assert "sk-live" not in returned_error
        assert "raw-token" not in returned_error
        assert "api-token" not in returned_error
        assert "bearer-secret" not in returned_error
        assert "basic-secret" not in returned_error
        assert "session-secret" not in returned_error
        assert "refresh-secret" not in returned_error
        assert "quoted secret" not in returned_error
        assert "pg-secret" not in returned_error
        assert "<redacted>" in returned_error


def test_source_status_payload_marks_disabled_and_api_backed_capabilities() -> None:
    payload = _source_status_payload(
        {
            "source_id": "cryptopanic",
            "provider_type": "cryptopanic",
            "source_domain": "cryptopanic.com",
            "source_name": "CryptoPanic",
            "source_role": "aggregator",
            "trust_tier": "standard",
            "coverage_tags_json": [],
            "source_quality_status": "unknown",
            "enabled": False,
            "managed_by_config": True,
            "refresh_interval_seconds": 300,
            "item_count": 0,
            "sync_high_watermark_ms": 0,
            "sync_overlap_ms": 0,
            "next_fetch_after_ms": 0,
            "consecutive_failures": 0,
            "last_error": "disabled by config",
            "latest_quality_json": None,
        }
    )

    assert payload["last_seen_at_ms"] is None
    assert payload["latest_fetch_run"] is None
    assert payload["latest_quality_counts"] == {}
    assert payload["provider_health"] == {
        "status": "disabled",
        "reason": "source_disabled",
        "last_error": "disabled by config",
        "consecutive_failures": 0,
        "last_success_at_ms": None,
        "last_seen_at_ms": None,
    }
    assert payload["provider_capability_tags"] == ["poll_primary_items", "api_backed"]


def test_replace_source_quality_rows_updates_source_status_freshness() -> None:
    conn = CapturingQualityConnection()
    repo = NewsRepository(conn)

    repo.replace_source_quality_rows(rows=[_source_quality_write_row()], status_window="24h")

    status_update = next(sql for sql, _ in conn.calls if "UPDATE news_sources" in sql)
    status_params = next(params for sql, params in conn.calls if "UPDATE news_sources" in sql)
    assert "updated_at_ms = GREATEST(updated_at_ms, %s)" in status_update
    assert "source_quality_status IS DISTINCT FROM %s" in status_update
    assert status_params == ("healthy", NOW_MS, "coindesk", "healthy")
    assert conn.commits == 0
    assert conn.transaction_enter_count == 1
    assert conn.transaction_exit_count == 1


@pytest.mark.parametrize(
    ("row_update", "error"),
    [
        ({"row_id": None}, "news_source_quality_payload_row_id_required"),
        ({"row_id": " "}, "news_source_quality_payload_row_id_required"),
        ({"source_id": 123}, "news_source_quality_payload_source_id_required"),
        ({"window": ""}, "news_source_quality_payload_window_required"),
        ({"projection_version": None}, "news_source_quality_payload_projection_version_required"),
        ({"computed_at_ms": None}, "news_source_quality_payload_computed_at_ms_required"),
        ({"computed_at_ms": True}, "news_source_quality_payload_computed_at_ms_required"),
        ({"computed_at_ms": "1000"}, "news_source_quality_payload_computed_at_ms_required"),
        ({"items_fetched": None}, "news_source_quality_payload_items_fetched_required"),
        ({"items_fetched": "10"}, "news_source_quality_payload_items_fetched_required"),
        ({"items_fetched": -1}, "news_source_quality_payload_items_fetched_required"),
        ({"items_inserted": None}, "news_source_quality_payload_items_inserted_required"),
        ({"items_inserted": True}, "news_source_quality_payload_items_inserted_required"),
        ({"items_inserted": -1}, "news_source_quality_payload_items_inserted_required"),
        ({"median_lag_ms": "500"}, "news_source_quality_payload_median_lag_ms_required"),
        ({"median_lag_ms": True}, "news_source_quality_payload_median_lag_ms_required"),
        ({"median_lag_ms": -1}, "news_source_quality_payload_median_lag_ms_required"),
        ({"diagnostics_json": None}, "news_source_quality_payload_diagnostics_json_required"),
        ({"diagnostics_json": "healthy"}, "news_source_quality_payload_diagnostics_json_required"),
        ({"diagnostics_json": {}}, "news_source_quality_payload_diagnostics_status_required"),
        ({"diagnostics_json": {"status": None}}, "news_source_quality_payload_diagnostics_status_required"),
        ({"diagnostics_json": {"status": " "}}, "news_source_quality_payload_diagnostics_status_required"),
    ],
)
def test_source_quality_write_payload_rejects_malformed_required_scalars(
    row_update: dict[str, object],
    error: str,
) -> None:
    conn = CapturingQualityConnection()
    repo = NewsRepository(conn)
    row = _source_quality_write_row()
    row.update(row_update)

    with pytest.raises(ValueError, match=error):
        repo.replace_source_quality_rows(rows=[row], status_window="24h")

    assert conn.calls == []
    assert conn.commits == 0


def test_source_quality_payload_hash_rejects_legacy_diagnostics_keys() -> None:
    conn = CapturingQualityConnection()
    repo = NewsRepository(conn)

    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        repo.replace_source_quality_rows(
            rows=[
                {
                    "row_id": "news-source-quality:coindesk:24h",
                    "source_id": "coindesk",
                    "window": "24h",
                    "computed_at_ms": NOW_MS,
                    "fetch_success_rate": 1,
                    "items_fetched": 10,
                    "items_inserted": 8,
                    "duplicate_rate": 0.2,
                    "process_success_rate": 1,
                    "resolved_token_rate": 0.75,
                    "attention_rate": 0.25,
                    "accepted_fact_rate": 0.5,
                    "brief_ready_rate": 0.5,
                    "median_lag_ms": 500,
                    "quality_score": 82.5,
                    "diagnostics_json": {123: "legacy", "status": "healthy"},
                    "projection_version": SOURCE_QUALITY_PROJECTION_VERSION,
                }
            ],
            commit=True,
        )

    assert conn.calls == []
    assert conn.commits == 0


def test_source_quality_repository_query_uses_narrow_item_and_fact_hotpaths() -> None:
    conn = CapturingQualityConnection()
    repo = NewsRepository(conn)

    rows = repo.list_source_quality_inputs_for_targets(source_windows=[("coindesk", "24h")], now_ms=NOW_MS)

    assert rows == []
    query = next(sql for sql, _ in conn.calls if "WITH source_rows AS" in sql)
    normalized_query = " ".join(query.split())
    assert "SELECT items.*" not in query
    assert (
        "SELECT items.news_item_id, items.source_id, items.published_at_ms, items.fetched_at_ms, "
        "items.lifecycle_status, items.story_key, items.story_identity_version "
        "FROM source_rows AS sources JOIN news_items AS items"
    ) in normalized_query
    assert "JOIN news_fact_candidates AS facts ON facts.news_item_id = items.news_item_id" in normalized_query
    assert "JOIN news_story_agent_briefs AS briefs" in normalized_query
    assert "briefs.story_key = items.story_key" in normalized_query
    assert "briefs.story_identity_version = items.story_identity_version" in normalized_query
    assert "briefs.member_news_item_ids_json ? items.news_item_id" in normalized_query
    assert "news_item_agent_briefs" not in normalized_query
    assert "news_context_items" not in normalized_query
    assert "context_items" not in normalized_query


def test_source_status_query_uses_preaggregated_source_hotpaths() -> None:
    conn = CapturingQualityConnection()
    repo = NewsRepository(conn)

    rows = repo.list_source_status()

    assert rows == []
    query = conn.calls[0][0]
    normalized_query = " ".join(query.split())
    assert "WITH edge_item_aggregate AS" in query
    assert "page_row_aggregate AS" in query
    assert "latest_fetch_run AS" in query
    assert "LEFT JOIN LATERAL" not in query
    assert "COUNT(DISTINCT edges.news_item_id)::int AS canonical_item_count" in normalized_query
    assert "COUNT(DISTINCT rows.row_id)::int AS serving_row_count" in normalized_query
    assert "ORDER BY fetch_runs.source_id, fetch_runs.started_at_ms DESC, fetch_runs.fetch_run_id DESC" in (
        normalized_query
    )


def _source_quality_claim(
    source_id: str,
    *,
    window: str,
    payload_hash: str = "hash",
    attempt_count: int = 1,
) -> dict[str, object]:
    return {
        "projection_name": "source_quality",
        "target_kind": "source",
        "target_id": source_id,
        "window": window,
        "payload_hash": payload_hash,
        "lease_owner": "news_source_quality_projection",
        "attempt_count": attempt_count,
    }


class FakeSourceQualityDB:
    def __init__(self, repo: FakeSourceQualityRepository, *, claimed: list[dict[str, object]]) -> None:
        self.repo = repo
        self.conn = CapturingQualityConnection()
        self.dirty = FakeDirtyTargets(claimed)
        self.sessions: list[str] = []

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        assert statement_timeout_seconds == 30
        self.sessions.append(name)
        yield SimpleNamespace(
            news=self.repo,
            news_projection_dirty_targets=self.dirty,
            conn=self.conn,
            transaction=self.conn.transaction,
        )


class FakeSourceQualityRepository:
    def __init__(
        self,
        *,
        changed_source_ids: list[str] | None = None,
        item_ids_by_source: dict[str, list[str]] | None = None,
        latest_item_published_at_ms: int | None = None,
    ) -> None:
        self.list_calls: list[dict[str, int]] = []
        self.rows: list[dict[str, object]] = []
        self.changed_source_ids = list(changed_source_ids or [])
        self.item_ids_by_source = {str(key): list(value) for key, value in (item_ids_by_source or {}).items()}
        self.latest_item_published_at_ms = latest_item_published_at_ms
        self.status_windows: list[str | None] = []

    def list_source_quality_inputs_for_targets(self, *, source_windows, now_ms: int):
        normalized = [(str(source_id), str(window)) for source_id, window in source_windows]
        self.list_calls.append({"source_windows": normalized, "now_ms": now_ms})
        return [
            {
                "source_id": source_id,
                "window": window,
                "fetch_run_count": 1,
                "fetch_success_count": 1,
                "items_fetched": 2,
                "items_inserted": 1,
                "items_duplicate": 1,
                "item_count": 1,
                "processed_item_count": 1,
                "mention_count": 1,
                "resolved_mention_count": 1,
                "attention_fact_count": 0,
                "accepted_fact_count": 1,
                "fact_count": 1,
                "ready_brief_count": 1,
                "useful_item_count": 1,
                "latest_item_published_at_ms": self.latest_item_published_at_ms or now_ms,
                "median_lag_ms": 0,
            }
            for source_id, window in normalized
        ]

    def replace_source_quality_rows(self, *, rows, status_window: str | None = None, commit: bool = True) -> list[str]:
        assert commit is False
        self.status_windows.append(status_window)
        self.rows.extend(dict(row) for row in rows)
        return list(self.changed_source_ids)

    def list_news_item_ids_for_sources(self, *, source_ids):
        return [item_id for source_id in source_ids for item_id in self.item_ids_by_source.get(str(source_id), [])]

    def servable_news_item_ids(self, news_item_ids):
        return [str(news_item_id) for news_item_id in news_item_ids]


class FakeDirtyTargets:
    def __init__(self, claimed: list[dict[str, object]]) -> None:
        self.claimed = [dict(row) for row in claimed]
        self.marked_done: list[list[dict[str, object]]] = []
        self.enqueued: list[dict[str, object]] = []

    def claim_due(self, **kwargs):
        assert kwargs["projection_name"] == "source_quality"
        assert kwargs["commit"] is False
        return [dict(row) for row in self.claimed[: kwargs["limit"]]]

    def mark_done(self, rows, *, now_ms: int, commit: bool = True):
        assert commit is False
        self.marked_done.append([dict(row) for row in rows])
        return len(rows)

    def mark_error(
        self,
        rows,
        *,
        error: str,
        retry_ms: int,
        now_ms: int,
        count_attempt: bool = True,
        commit: bool = True,
    ):
        del count_attempt
        raise AssertionError(f"source quality worker should not mark error: {error}")

    def enqueue_targets(self, rows, *, reason: str, now_ms: int, commit: bool = True, due_at_ms: int | None = None):
        self.enqueued.append(
            {
                "rows": [dict(row) for row in rows],
                "reason": reason,
                "now_ms": now_ms,
                "commit": commit,
                "due_at_ms": due_at_ms,
            }
        )
        return len(rows)


class CapturingQualityConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.commits = 0
        self.transaction_enter_count = 0
        self.transaction_exit_count = 0

    def execute(self, sql: str, params: object = None) -> CapturingQualityCursor:
        self.calls.append((sql, params))
        return CapturingQualityCursor()

    def commit(self) -> None:
        self.commits += 1

    @contextmanager
    def transaction(self):
        self.transaction_enter_count += 1
        try:
            yield
        finally:
            self.transaction_exit_count += 1


class CapturingQualityCursor:
    rowcount = 1

    def fetchall(self):
        return []
