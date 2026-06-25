from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.app.runtime.projection_dirty_targets import enqueue_projection_dirty_targets
from parallax.domains.news_intel.repositories import (
    news_projection_dirty_target_repository as dirty_target_repository_module,
)
from parallax.domains.news_intel.repositories.news_projection_dirty_target_repository import (
    NewsProjectionDirtyTargetRepository,
)
from parallax.domains.news_intel.repositories.news_repository import NewsRepository
from parallax.domains.news_intel.runtime.news_fetch_worker import NewsFetchWorker
from parallax.domains.news_intel.runtime.news_item_brief_worker import NewsItemBriefWorker
from parallax.domains.news_intel.runtime.news_item_process_worker import NewsItemProcessWorker
from parallax.domains.news_intel.runtime.news_page_projection_worker import NewsPageProjectionWorker
from parallax.domains.news_intel.runtime.news_source_quality_projection_worker import (
    NewsSourceQualityProjectionWorker,
)
from parallax.domains.news_intel.types.source_provider import (
    NewsProviderFetchResult,
    NewsProviderObservation,
    NewsSourceSnapshot,
)
from parallax.domains.token_intel.interfaces import TokenIdentityLookupResult
from parallax.platform.config.settings import (
    NewsFetchWorkerSettings,
    NewsItemProcessWorkerSettings,
    NewsPageProjectionWorkerSettings,
    NewsSourceQualityProjectionWorkerSettings,
)

NOW_MS = 1_779_000_000_000
NEWS_SOURCE_PROVIDER_SCHEMA_TYPES = ("atom", "cryptopanic", "json_feed", "opennews", "rss")
_MISSING = object()


def _page_projection_settings(**overrides: Any) -> NewsPageProjectionWorkerSettings:
    payload: dict[str, Any] = {
        "batch_size": 10,
        "lease_ms": 60_000,
        "retry_ms": 30_000,
        "statement_timeout_seconds": 30,
    }
    payload.update(overrides)
    return NewsPageProjectionWorkerSettings(**payload)


def _news_fetch_settings(**overrides: Any) -> NewsFetchWorkerSettings:
    payload = {
        "batch_size": 10,
        "statement_timeout_seconds": 30,
    }
    payload.update(overrides)
    return NewsFetchWorkerSettings(**payload)


def _item_process_settings(**overrides: Any) -> NewsItemProcessWorkerSettings:
    payload: dict[str, Any] = {
        "batch_size": 10,
        "lease_ms": 120_000,
        "max_attempts": 3,
        "retry_delay_ms": 60_000,
        "statement_timeout_seconds": 30,
    }
    payload.update(overrides)
    return NewsItemProcessWorkerSettings(**payload)


def _source_quality_projection_settings(**overrides: Any) -> NewsSourceQualityProjectionWorkerSettings:
    payload: dict[str, Any] = {
        "batch_size": 10,
        "lease_ms": 60_000,
        "retry_ms": 30_000,
        "statement_timeout_seconds": 30,
        "windows": ("24h",),
    }
    payload.update(overrides)
    return NewsSourceQualityProjectionWorkerSettings(**payload)


def _raw_page_projection_settings(**overrides: object) -> SimpleNamespace:
    values = {
        "enabled": True,
        "interval_seconds": 5.0,
        "soft_timeout_seconds": 120.0,
        "hard_timeout_seconds": 180.0,
        "batch_size": 10,
        "lease_ms": 60_000,
        "retry_ms": 30_000,
        "max_attempts": 3,
        "statement_timeout_seconds": 30,
        "backoff": SimpleNamespace(base_ms=1, max_ms=5),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _raw_source_quality_projection_settings(**overrides: object) -> SimpleNamespace:
    values = {
        "enabled": True,
        "interval_seconds": 60.0,
        "soft_timeout_seconds": 120.0,
        "hard_timeout_seconds": 180.0,
        "batch_size": 10,
        "lease_ms": 60_000,
        "retry_ms": 30_000,
        "max_attempts": 3,
        "statement_timeout_seconds": 30,
        "windows": ("24h",),
        "backoff": SimpleNamespace(base_ms=1, max_ms=5),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_dirty_target_repository_rejects_retired_story_projection_name() -> None:
    repo = NewsProjectionDirtyTargetRepository(object())

    with pytest.raises(ValueError, match="unsupported news projection_name: story"):
        repo.enqueue_targets(
            [
                {
                    "projection_name": "story",
                    "target_kind": "news_item",
                    "target_id": "news-1",
                }
            ],
            reason="legacy_story_projection",
            now_ms=NOW_MS,
        )


def test_dirty_target_repository_accepts_story_brief_story_targets() -> None:
    conn = TransactionalScriptedConnection([[]], rowcount=1)
    repo = NewsProjectionDirtyTargetRepository(conn)

    changed = repo.enqueue_targets(
        [
            {
                "projection_name": "story_brief",
                "target_kind": "story",
                "target_id": "story:v2:listing:binance:foo",
                "source_watermark_ms": NOW_MS - 1_000,
            }
        ],
        reason="news_story_brief_input_changed",
        now_ms=NOW_MS,
    )

    assert changed == 1
    params = conn.params[-1]
    assert params["projection_names"] == ["story_brief"]
    assert params["target_kinds"] == ["story"]
    assert params["target_ids"] == ["story:v2:listing:binance:foo"]
    assert params["windows"] == [""]
    assert params["source_watermark_ms_values"] == [NOW_MS - 1_000]


def test_dirty_target_repository_rejects_story_brief_item_targets() -> None:
    repo = NewsProjectionDirtyTargetRepository(object())

    with pytest.raises(ValueError, match="unsupported news projection target: story_brief/news_item"):
        repo.enqueue_targets(
            [
                {
                    "projection_name": "story_brief",
                    "target_kind": "news_item",
                    "target_id": "news-1",
                    "source_watermark_ms": NOW_MS - 1_000,
                }
            ],
            reason="news_story_brief_input_changed",
            now_ms=NOW_MS,
        )


@pytest.mark.parametrize("field", ["projection_name", "target_kind", "target_id"])
@pytest.mark.parametrize(
    "value",
    [
        pytest.param(_MISSING, id="missing"),
        pytest.param("", id="blank"),
        pytest.param(None, id="none"),
        pytest.param(1, id="non_string"),
    ],
)
def test_news_projection_dirty_enqueue_requires_target_identity_before_sql(field: str, value: object) -> None:
    conn = TransactionalScriptedConnection([])
    repo = NewsProjectionDirtyTargetRepository(conn)
    target: dict[str, Any] = {
        "projection_name": "page",
        "target_kind": "news_item",
        "target_id": "news-1",
        "source_watermark_ms": NOW_MS - 1_000,
    }
    if value is _MISSING:
        target.pop(field)
    else:
        target[field] = value

    with pytest.raises(ValueError, match=f"news_projection_dirty_target_{field}_required"):
        repo.enqueue_targets([target], reason="unit", now_ms=NOW_MS)

    assert conn.sql == []


def test_news_projection_dirty_enqueue_rejects_window_for_windowless_targets_before_sql() -> None:
    conn = TransactionalScriptedConnection([])
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(ValueError, match="news_projection_dirty_target_window_empty_required"):
        repo.enqueue_targets(
            [
                {
                    "projection_name": "story_brief",
                    "target_kind": "story",
                    "target_id": "story:v2:listing:binance:foo",
                    "window": "24h",
                    "source_watermark_ms": NOW_MS - 1_000,
                }
            ],
            reason="unit",
            now_ms=NOW_MS,
        )

    assert conn.sql == []


def test_dirty_target_terminalize_requires_connection_transaction_before_delete_or_ledger_sql() -> None:
    conn = MissingTransactionConnection()
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(RuntimeError, match="news_projection_dirty_target_transaction_required"):
        repo.terminalize_targets(
            [_claim("news-1", payload_hash="hash-1", attempt_count=2)],
            worker_name="news_page_projection",
            final_reason="projection_terminal",
            final_reason_bucket="missing_fact",
            now_ms=NOW_MS,
        )

    assert conn.sql == []
    assert conn.commits == 0


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(
            lambda repo: repo.enqueue_targets(
                [
                    {
                        "projection_name": "page",
                        "target_kind": "news_item",
                        "target_id": "news-1",
                        "source_watermark_ms": NOW_MS - 1_000,
                    }
                ],
                reason="unit",
                now_ms=NOW_MS,
            ),
            id="enqueue_targets",
        ),
        pytest.param(
            lambda repo: repo.claim_due(limit=1, lease_ms=60_000, now_ms=NOW_MS, lease_owner="news_page_projection"),
            id="claim_due",
        ),
        pytest.param(
            lambda repo: repo.mark_done([_claim("news-1")], now_ms=NOW_MS),
            id="mark_done",
        ),
        pytest.param(
            lambda repo: repo.mark_error(
                [_claim("news-1")],
                error="projection failed",
                retry_ms=30_000,
                now_ms=NOW_MS,
            ),
            id="mark_error",
        ),
    ],
)
def test_news_projection_dirty_target_mutations_require_connection_transaction_before_sql_when_committing(
    mutation: Callable[[NewsProjectionDirtyTargetRepository], object],
) -> None:
    conn = MissingTransactionConnection()
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(RuntimeError, match="news_projection_dirty_target_transaction_required"):
        mutation(repo)

    assert conn.sql == []
    assert conn.commits == 0


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        pytest.param({"limit": -1}, "news_projection_dirty_target_claim_limit_required", id="limit-negative"),
        pytest.param({"limit": True}, "news_projection_dirty_target_claim_limit_required", id="limit-bool"),
        pytest.param({"limit": "1"}, "news_projection_dirty_target_claim_limit_required", id="limit-string"),
        pytest.param({"lease_ms": 0}, "news_projection_dirty_target_claim_lease_ms_required", id="lease-zero"),
        pytest.param({"lease_ms": True}, "news_projection_dirty_target_claim_lease_ms_required", id="lease-bool"),
        pytest.param(
            {"lease_ms": "60000"},
            "news_projection_dirty_target_claim_lease_ms_required",
            id="lease-string",
        ),
    ],
)
def test_news_projection_dirty_claim_due_rejects_malformed_parameters_before_transaction(
    overrides: dict[str, object],
    error_code: str,
) -> None:
    conn = TransactionalScriptedConnection([[]], rowcount=0)
    repo = NewsProjectionDirtyTargetRepository(conn)
    params = {
        "limit": 1,
        "lease_ms": 60_000,
        "now_ms": NOW_MS,
        "lease_owner": "news_page_projection",
    }
    params.update(overrides)

    with pytest.raises(ValueError, match=error_code):
        repo.claim_due(**params)

    assert conn.sql == []
    assert conn.transaction_enter_count == 0


@pytest.mark.parametrize(
    "retry_ms",
    [0, True, "30000"],
)
def test_news_projection_dirty_mark_error_rejects_malformed_retry_before_transaction(
    retry_ms: object,
) -> None:
    conn = TransactionalScriptedConnection([], rowcount=0)
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(ValueError, match="news_projection_dirty_target_retry_ms_required"):
        repo.mark_error(
            [_claim("news-1")],
            error="projection failed",
            retry_ms=retry_ms,  # type: ignore[arg-type]
            now_ms=NOW_MS,
        )

    assert conn.sql == []
    assert conn.transaction_enter_count == 0


@pytest.mark.parametrize(
    ("count_attempt", "expected_increment"),
    [
        pytest.param(True, 1, id="count-failed-attempt"),
        pytest.param(False, 0, id="release-no-start-claim"),
    ],
)
def test_news_projection_dirty_mark_error_counts_attempt_only_on_failure(
    count_attempt: bool,
    expected_increment: int,
) -> None:
    conn = TransactionalScriptedConnection([[]], rowcount=1)
    repo = NewsProjectionDirtyTargetRepository(conn)

    changed = repo.mark_error(
        [_claim("news-1", payload_hash="hash-1", attempt_count=2)],
        error="projection failed",
        retry_ms=30_000,
        now_ms=NOW_MS,
        count_attempt=count_attempt,
    )

    assert changed == 1
    assert "attempt_count = queue.attempt_count + %(attempt_increment)s" in conn.sql[0]
    assert conn.params[0]["attempt_increment"] == expected_increment


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(lambda repo, token: repo.mark_done([token], now_ms=NOW_MS), id="mark_done"),
        pytest.param(
            lambda repo, token: repo.mark_error(
                [token],
                error="projection failed",
                retry_ms=30_000,
                now_ms=NOW_MS,
            ),
            id="mark_error",
        ),
        pytest.param(
            lambda repo, token: repo.terminalize_targets(
                [token],
                worker_name="news_page_projection",
                final_reason="projection_terminal",
                final_reason_bucket="missing_fact",
                now_ms=NOW_MS,
            ),
            id="terminalize_targets",
        ),
    ],
)
def test_news_projection_dirty_target_completion_requires_claim_attempt_contract_before_sql(
    mutation: Callable[[NewsProjectionDirtyTargetRepository, dict[str, Any]], object],
) -> None:
    conn = TransactionalScriptedConnection([])
    repo = NewsProjectionDirtyTargetRepository(conn)
    token = _claim("news-1", payload_hash="hash-1")
    token.pop("attempt_count")

    with pytest.raises(ValueError, match="news projection dirty target completion requires attempt_count"):
        mutation(repo, token)

    assert conn.sql == []
    assert conn.transaction_enter_count == 0
    assert conn.commits == 0


@pytest.mark.parametrize("attempt_count", [-1, True, "1"])
def test_news_projection_dirty_target_completion_rejects_malformed_attempt_count_before_sql(
    attempt_count: object,
) -> None:
    conn = TransactionalScriptedConnection([])
    repo = NewsProjectionDirtyTargetRepository(conn)
    token = _claim("news-1", payload_hash="hash-1", attempt_count=2)
    token["attempt_count"] = attempt_count

    with pytest.raises(ValueError, match="news projection dirty target completion requires attempt_count"):
        repo.mark_done([token], now_ms=NOW_MS)

    assert conn.sql == []
    assert conn.transaction_enter_count == 0
    assert conn.commits == 0


def test_news_projection_dirty_target_completion_accepts_zero_claim_attempt_count() -> None:
    conn = TransactionalScriptedConnection([[]], rowcount=1)
    repo = NewsProjectionDirtyTargetRepository(conn)

    changed = repo.mark_done([_claim("news-1", payload_hash="hash-1", attempt_count=0)], now_ms=NOW_MS)

    assert changed == 1
    assert conn.params[0]["attempt_counts"] == [0]


@pytest.mark.parametrize("field", ["projection_name", "target_kind", "target_id"])
@pytest.mark.parametrize(
    "value",
    [
        pytest.param(_MISSING, id="missing"),
        pytest.param("", id="blank"),
        pytest.param(None, id="none"),
        pytest.param(1, id="non_string"),
    ],
)
def test_news_projection_dirty_target_completion_requires_claim_identity_before_sql(
    field: str,
    value: object,
) -> None:
    conn = TransactionalScriptedConnection([])
    repo = NewsProjectionDirtyTargetRepository(conn)
    token = _claim("news-1", payload_hash="hash-1", attempt_count=2)
    if value is _MISSING:
        token.pop(field)
    else:
        token[field] = value

    with pytest.raises(ValueError, match="news projection dirty target completion requires full target key"):
        repo.mark_done([token], now_ms=NOW_MS)

    assert conn.sql == []
    assert conn.transaction_enter_count == 0
    assert conn.commits == 0


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(_MISSING, id="missing"),
        pytest.param(None, id="none"),
        pytest.param(1, id="non_string"),
        pytest.param("24h", id="non_empty"),
    ],
)
def test_news_projection_dirty_target_completion_requires_windowless_claim_window_before_sql(
    value: object,
) -> None:
    conn = TransactionalScriptedConnection([])
    repo = NewsProjectionDirtyTargetRepository(conn)
    token = _claim("news-1", payload_hash="hash-1", attempt_count=2)
    if value is _MISSING:
        token.pop("window")
    else:
        token["window"] = value

    with pytest.raises(
        ValueError,
        match=r"news projection dirty target completion requires (?:empty )?window from claim_due",
    ):
        repo.mark_done([token], now_ms=NOW_MS)

    assert conn.sql == []
    assert conn.transaction_enter_count == 0
    assert conn.commits == 0


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(_MISSING, id="missing"),
        pytest.param("", id="blank"),
        pytest.param(" ", id="whitespace"),
        pytest.param(None, id="none"),
        pytest.param(1, id="non_string"),
    ],
)
def test_news_projection_dirty_target_completion_requires_source_quality_claim_window_before_sql(
    value: object,
) -> None:
    conn = TransactionalScriptedConnection([])
    repo = NewsProjectionDirtyTargetRepository(conn)
    token = _source_quality_claim("source-1", payload_hash="hash-1", attempt_count=2)
    if value is _MISSING:
        token.pop("window")
    else:
        token["window"] = value

    with pytest.raises(ValueError, match="requires window from claim_due"):
        repo.mark_done([token], now_ms=NOW_MS)

    assert conn.sql == []
    assert conn.transaction_enter_count == 0
    assert conn.commits == 0


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(lambda repo: repo.mark_done([_claim("news-1")], now_ms=NOW_MS), id="mark_done"),
        pytest.param(
            lambda repo: repo.mark_error(
                [_claim("news-1")],
                error="projection failed",
                retry_ms=30_000,
                now_ms=NOW_MS,
            ),
            id="mark_error",
        ),
    ],
)
def test_news_projection_dirty_completion_counts_require_cursor_rowcount(
    mutation: Callable[[NewsProjectionDirtyTargetRepository], int],
) -> None:
    conn = TransactionalScriptedConnection([[]], omit_rowcount=True)
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="news_projection_dirty_target_rowcount_required"):
        mutation(repo)


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(lambda repo: repo.mark_done([_claim("news-1")], now_ms=NOW_MS), id="mark_done"),
        pytest.param(
            lambda repo: repo.mark_error(
                [_claim("news-1")],
                error="projection failed",
                retry_ms=30_000,
                now_ms=NOW_MS,
            ),
            id="mark_error",
        ),
    ],
)
@pytest.mark.parametrize("rowcount", ["bad", True, -1])
def test_news_projection_dirty_completion_counts_reject_invalid_cursor_rowcount(
    mutation: Callable[[NewsProjectionDirtyTargetRepository], int],
    rowcount: object,
) -> None:
    conn = TransactionalScriptedConnection([[]], rowcount=rowcount)
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="news_projection_dirty_target_rowcount_invalid"):
        mutation(repo)


def test_news_projection_dirty_terminal_returning_counts_require_cursor_rowcount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claimed = _claim("news-1", payload_hash="hash-1", attempt_count=2)
    conn = TransactionalScriptedConnection([[claimed]], omit_rowcount=True)
    repo = NewsProjectionDirtyTargetRepository(conn)
    terminal_ledger_calls = 0

    def fake_terminalize_source_row(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal terminal_ledger_calls
        terminal_ledger_calls += 1
        raise AssertionError("terminal ledger must wait for RETURNING rowcount validation")

    monkeypatch.setattr(dirty_target_repository_module, "terminalize_source_row", fake_terminalize_source_row)

    with pytest.raises(TypeError, match="news_projection_dirty_target_rowcount_required"):
        repo.terminalize_targets(
            [claimed],
            worker_name="news_page_projection",
            final_reason="projection_terminal",
            final_reason_bucket="missing_fact",
            now_ms=NOW_MS,
        )

    assert terminal_ledger_calls == 0


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_news_projection_dirty_terminal_returning_counts_reject_invalid_or_mismatched_rowcount(
    monkeypatch: pytest.MonkeyPatch,
    rowcount: object,
) -> None:
    claimed = _claim("news-1", payload_hash="hash-1", attempt_count=2)
    conn = TransactionalScriptedConnection([[claimed]], rowcount=rowcount)
    repo = NewsProjectionDirtyTargetRepository(conn)
    terminal_ledger_calls = 0

    def fake_terminalize_source_row(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal terminal_ledger_calls
        terminal_ledger_calls += 1
        raise AssertionError("terminal ledger must wait for RETURNING rowcount validation")

    monkeypatch.setattr(dirty_target_repository_module, "terminalize_source_row", fake_terminalize_source_row)

    with pytest.raises(TypeError, match="news_projection_dirty_target_rowcount_invalid"):
        repo.terminalize_targets(
            [claimed],
            worker_name="news_page_projection",
            final_reason="projection_terminal",
            final_reason_bucket="missing_fact",
            now_ms=NOW_MS,
        )

    assert terminal_ledger_calls == 0


def test_news_projection_dirty_enqueue_counts_require_cursor_rowcount() -> None:
    conn = TransactionalScriptedConnection([[]], omit_rowcount=True)
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="news_projection_dirty_target_rowcount_required"):
        repo.enqueue_targets(
            [
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-1",
                    "source_watermark_ms": NOW_MS - 1_000,
                }
            ],
            reason="unit",
            now_ms=NOW_MS,
        )


@pytest.mark.parametrize("rowcount", ["bad", True, -1])
def test_news_projection_dirty_enqueue_counts_reject_invalid_cursor_rowcount(rowcount: object) -> None:
    conn = TransactionalScriptedConnection([[]], rowcount=rowcount)
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="news_projection_dirty_target_rowcount_invalid"):
        repo.enqueue_targets(
            [
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-1",
                    "source_watermark_ms": NOW_MS - 1_000,
                }
            ],
            reason="unit",
            now_ms=NOW_MS,
        )


def test_news_projection_dirty_enqueue_count_uses_postgres_rowcount_not_candidate_count() -> None:
    conn = TransactionalScriptedConnection([[]], rowcount=0)
    repo = NewsProjectionDirtyTargetRepository(conn)

    changed = repo.enqueue_targets(
        [
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
        ],
        reason="unit",
        now_ms=NOW_MS,
    )

    assert changed == 0


@pytest.mark.parametrize("projection_name", ["page", "brief_input"])
@pytest.mark.parametrize(
    "source_watermark_ms",
    [
        pytest.param(_MISSING, id="missing"),
        pytest.param(None, id="none"),
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(True, id="bool"),
        pytest.param("10", id="string"),
    ],
)
def test_news_item_projection_dirty_enqueue_requires_positive_source_watermark(
    projection_name: str,
    source_watermark_ms: object,
) -> None:
    conn = TransactionalScriptedConnection([[]], rowcount=0)
    repo = NewsProjectionDirtyTargetRepository(conn)
    target: dict[str, Any] = {
        "projection_name": projection_name,
        "target_kind": "news_item",
        "target_id": "news-1",
    }
    if source_watermark_ms is not _MISSING:
        target["source_watermark_ms"] = source_watermark_ms

    with pytest.raises(ValueError, match="news_projection_dirty_target_source_watermark_required"):
        repo.enqueue_targets([target], reason="unit", now_ms=NOW_MS)

    assert conn.sql == []


@pytest.mark.parametrize(
    "source_watermark_ms",
    [
        pytest.param(_MISSING, id="missing"),
        pytest.param(None, id="none"),
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(True, id="bool"),
        pytest.param("10", id="string"),
    ],
)
def test_news_source_quality_window_dirty_enqueue_requires_positive_source_watermark(
    source_watermark_ms: object,
) -> None:
    conn = TransactionalScriptedConnection([[]], rowcount=0)
    repo = NewsProjectionDirtyTargetRepository(conn)
    target: dict[str, Any] = {
        "projection_name": "source_quality",
        "target_kind": "source",
        "target_id": "source-1",
        "window": "24h",
    }
    if source_watermark_ms is not _MISSING:
        target["source_watermark_ms"] = source_watermark_ms

    with pytest.raises(ValueError, match="news_projection_dirty_target_source_watermark_required"):
        repo.enqueue_targets([target], reason="unit", now_ms=NOW_MS)

    assert conn.sql == []


@pytest.mark.parametrize("priority", [True, "7", 7.5, ""])
def test_news_projection_dirty_enqueue_rejects_malformed_priority_without_int_repair(priority: object) -> None:
    conn = TransactionalScriptedConnection([[]], rowcount=0)
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(ValueError, match="news_projection_dirty_target_priority_required"):
        repo.enqueue_targets(
            [
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-1",
                    "source_watermark_ms": NOW_MS - 1_000,
                    "priority": priority,
                }
            ],
            reason="unit",
            now_ms=NOW_MS,
        )

    assert conn.sql == []


@pytest.mark.parametrize("due_at_ms", [True, "1800000", 1_800_000.5, 0])
def test_news_projection_dirty_enqueue_rejects_malformed_row_due_at_without_int_repair(due_at_ms: object) -> None:
    conn = TransactionalScriptedConnection([[]], rowcount=0)
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(ValueError, match="news_projection_dirty_target_due_at_ms_required"):
        repo.enqueue_targets(
            [
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-1",
                    "source_watermark_ms": NOW_MS - 1_000,
                    "due_at_ms": due_at_ms,
                }
            ],
            reason="unit",
            now_ms=NOW_MS,
        )

    assert conn.sql == []


@pytest.mark.parametrize("due_at_ms", [True, "1800000", 1_800_000.5, 0])
def test_news_projection_dirty_enqueue_rejects_malformed_default_due_at_without_int_repair(due_at_ms: object) -> None:
    conn = TransactionalScriptedConnection([[]], rowcount=0)
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(ValueError, match="news_projection_dirty_target_due_at_ms_required"):
        repo.enqueue_targets(
            [
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-1",
                    "source_watermark_ms": NOW_MS - 1_000,
                }
            ],
            reason="unit",
            now_ms=NOW_MS,
            due_at_ms=due_at_ms,  # type: ignore[arg-type]
        )

    assert conn.sql == []


def test_news_projection_dirty_claim_due_returning_rows_require_cursor_rowcount() -> None:
    conn = TransactionalScriptedConnection([[_claim("news-1")]], omit_rowcount=True)
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="news_projection_dirty_target_rowcount_required"):
        repo.claim_due(
            limit=1,
            lease_ms=60_000,
            now_ms=NOW_MS,
            lease_owner="news_page_projection",
        )

    assert "UPDATE news_projection_dirty_targets" in conn.sql[0]
    assert "RETURNING news_projection_dirty_targets.*" in conn.sql[0]


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_news_projection_dirty_claim_due_returning_rows_reject_invalid_or_mismatched_rowcount(
    rowcount: object,
) -> None:
    conn = TransactionalScriptedConnection([[_claim("news-1")]], rowcount=rowcount)
    repo = NewsProjectionDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="news_projection_dirty_target_rowcount_invalid"):
        repo.claim_due(
            limit=1,
            lease_ms=60_000,
            now_ms=NOW_MS,
            lease_owner="news_page_projection",
        )


def test_news_projection_dirty_claim_due_returning_rows_accept_zero_row_noop() -> None:
    conn = TransactionalScriptedConnection([[]], rowcount=0)
    repo = NewsProjectionDirtyTargetRepository(conn)

    rows = repo.claim_due(
        limit=1,
        lease_ms=60_000,
        now_ms=NOW_MS,
        lease_owner="news_page_projection",
    )

    assert rows == []


def test_news_projection_dirty_claim_due_returning_rows_accept_matching_claim_rows() -> None:
    claimed = _claim("news-1", payload_hash="hash-1", attempt_count=3)
    conn = TransactionalScriptedConnection([[claimed]], rowcount=1)
    repo = NewsProjectionDirtyTargetRepository(conn)

    rows = repo.claim_due(
        limit=1,
        lease_ms=60_000,
        now_ms=NOW_MS,
        lease_owner="news_page_projection",
    )

    assert rows == [claimed]
    assert "attempt_count + 1" not in conn.sql[0]
    assert "RETURNING news_projection_dirty_targets.*" in conn.sql[0]


def test_page_projection_worker_empty_dirty_queue_does_not_scan() -> None:
    repos = FakePageRepos(claimed=[])
    worker = _page_worker(repos)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert result.notes["claimed"] == 0
    assert result.notes["projected"] == 0
    assert repos.news.scan_calls == 0
    assert repos.news.loaded_ids == []
    assert repos.dirty.marked_done == []
    assert repos.dirty.marked_error == []


def test_page_projection_worker_loads_only_claimed_news_item_targets_and_marks_done_with_tokens() -> None:
    token_1 = _claim("news-1", payload_hash="hash-1", attempt_count=1)
    token_2 = _claim("news-2", payload_hash="hash-2", attempt_count=2)
    repos = FakePageRepos(claimed=[token_1, {**token_1}, token_2])
    repos.news.payloads = [_page_payload("news-2"), _page_payload("news-1")]
    worker = _page_worker(repos)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 2
    assert result.notes["claimed"] == 3
    assert result.notes["projected"] == 2
    assert result.notes["deleted"] == 0
    assert repos.news.scan_calls == 0
    assert repos.news.loaded_ids == ["news-1", "news-2"]
    assert repos.news.replacements == [
        {
            "news_item_ids": ["news-1", "news-2"],
            "row_ids": ["news-1", "news-2"],
            "commit": False,
        }
    ]
    assert repos.dirty.marked_done == [[token_1, token_1, token_2]]
    assert repos.dirty.marked_error == []


def test_page_projection_worker_marks_error_with_full_claim_token_when_projection_write_fails() -> None:
    token = _claim("news-1", payload_hash="hash-1", attempt_count=2)
    repos = FakePageRepos(claimed=[token])
    repos.news.payloads = [_page_payload("news-1")]
    repos.news.raise_on_replace = RuntimeError("write failed")
    worker = _page_worker(repos)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert result.notes["claimed"] == 1
    assert result.notes["marked_error"] == 1
    assert repos.news.replacements == []
    assert repos.dirty.marked_done == []
    assert repos.dirty.marked_error == [[token]]
    assert repos.dirty.terminalized == []


def test_page_projection_worker_terminalizes_exhausted_dirty_target_when_projection_write_fails() -> None:
    token = _claim("news-1", payload_hash="hash-1", attempt_count=3)
    repos = FakePageRepos(claimed=[token])
    repos.news.payloads = [_page_payload("news-1")]
    repos.news.raise_on_replace = RuntimeError("write failed")
    worker = _page_worker(repos)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert result.notes["claimed"] == 1
    assert result.notes["marked_error"] == 1
    assert repos.news.replacements == []
    assert repos.dirty.marked_done == []
    assert repos.dirty.marked_error == []
    assert repos.dirty.mark_error_calls == []
    assert repos.dirty.terminalized == [
        {
            "rows": [token],
            "worker_name": "news_page_projection",
            "final_reason": "news_projection_dirty_retry_budget_exhausted: write failed",
            "final_reason_bucket": "retry_budget_exhausted",
            "now_ms": NOW_MS,
            "commit": False,
        }
    ]


def test_page_projection_worker_rejects_member_item_missing_identity_without_partial_projection() -> None:
    token = _claim("news-1", payload_hash="hash-1", attempt_count=2)
    repos = FakePageRepos(claimed=[token])
    payload = _page_payload("news-1")
    payload["member_items"].append({"title": "missing identity"})
    repos.news.payloads = [payload]
    worker = _page_worker(repos)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert result.notes["claimed"] == 1
    assert result.notes["marked_error"] == 1
    assert repos.news.replacements == []
    assert repos.dirty.marked_done == []
    assert repos.dirty.marked_error == [[token]]
    assert repos.dirty.mark_error_calls == [
        {
            "error": "news_page_projection_member_item_news_item_id_required:news-1",
            "retry_ms": 30_000,
            "now_ms": NOW_MS,
            "commit": False,
        }
    ]


def test_page_projection_worker_rejects_claim_missing_target_id_without_marking_done() -> None:
    token = _claim("news-1", payload_hash="hash-1", attempt_count=2)
    token.pop("target_id")
    repos = FakePageRepos(claimed=[token])
    worker = _page_worker(repos)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert result.notes["claimed"] == 1
    assert result.notes["marked_error"] == 1
    assert repos.news.loaded_ids == []
    assert repos.news.replacements == []
    assert repos.dirty.marked_done == []
    assert repos.dirty.marked_error == [[token]]
    assert repos.dirty.mark_error_calls == [
        {
            "error": "news_page_projection_claim_target_id_required",
            "retry_ms": 30_000,
            "now_ms": NOW_MS,
            "commit": False,
        }
    ]


def test_page_projection_worker_reads_formal_settings_for_claim_session_and_retry() -> None:
    token = _claim("news-1", payload_hash="hash-1", attempt_count=2)
    repos = FakePageRepos(claimed=[token])
    repos.news.payloads = [_page_payload("news-1")]
    repos.news.raise_on_replace = RuntimeError("write failed")
    worker = NewsPageProjectionWorker(
        name="news_page_projection",
        settings=_page_projection_settings(
            batch_size=7,
            lease_ms=45_000,
            retry_ms=90_000,
            statement_timeout_seconds=17,
        ),
        db=FakeDB("news_page_projection", repos, expected_statement_timeout=17),
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert repos.dirty.claim_calls == [
        {
            "projection_name": "page",
            "limit": 7,
            "lease_ms": 45_000,
            "now_ms": NOW_MS,
            "lease_owner": "news_page_projection",
            "commit": False,
        }
    ]
    assert repos.dirty.mark_error_calls == [
        {"error": "write failed", "retry_ms": 90_000, "now_ms": NOW_MS, "commit": False}
    ]


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        pytest.param({"batch_size": 0}, "news_page_projection_batch_size_required", id="batch-zero"),
        pytest.param({"batch_size": True}, "news_page_projection_batch_size_required", id="batch-bool"),
        pytest.param({"batch_size": "10"}, "news_page_projection_batch_size_required", id="batch-string"),
        pytest.param({"lease_ms": 0}, "news_page_projection_lease_ms_required", id="lease-zero"),
        pytest.param({"lease_ms": True}, "news_page_projection_lease_ms_required", id="lease-bool"),
        pytest.param({"lease_ms": "60000"}, "news_page_projection_lease_ms_required", id="lease-string"),
        pytest.param({"retry_ms": 0}, "news_page_projection_retry_ms_required", id="retry-zero"),
        pytest.param({"retry_ms": True}, "news_page_projection_retry_ms_required", id="retry-bool"),
        pytest.param({"retry_ms": "30000"}, "news_page_projection_retry_ms_required", id="retry-string"),
        pytest.param({"max_attempts": 0}, "news_page_projection_max_attempts_required", id="attempts-zero"),
        pytest.param({"max_attempts": True}, "news_page_projection_max_attempts_required", id="attempts-bool"),
        pytest.param({"max_attempts": "3"}, "news_page_projection_max_attempts_required", id="attempts-string"),
    ],
)
def test_page_projection_worker_rejects_malformed_runtime_settings_before_session(
    overrides: dict[str, object],
    error_code: str,
) -> None:
    repos = FakePageRepos(claimed=[_claim("news-1")])
    worker = NewsPageProjectionWorker(
        name="news_page_projection",
        settings=_raw_page_projection_settings(**overrides),
        db=FakeDB("news_page_projection", repos),
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )

    with pytest.raises(RuntimeError, match=error_code):
        worker.run_once_sync(now_ms=NOW_MS)

    assert repos.conn.events == []
    assert repos.dirty.claim_calls == []


def test_page_projection_worker_deletes_missing_claimed_items_without_fallback_scan() -> None:
    token_1 = _claim("news-1")
    token_2 = _claim("news-deleted")
    repos = FakePageRepos(claimed=[token_1, token_2])
    repos.news.payloads = [_page_payload("news-1")]
    worker = _page_worker(repos)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 2
    assert result.notes["projected"] == 1
    assert result.notes["deleted"] == 1
    assert repos.news.scan_calls == 0
    assert repos.news.loaded_ids == ["news-1", "news-deleted"]
    assert repos.news.replacements == [
        {
            "news_item_ids": ["news-1"],
            "row_ids": ["news-1"],
            "commit": False,
        },
        {
            "news_item_ids": ["news-deleted"],
            "row_ids": [],
            "commit": False,
        },
    ]
    assert repos.dirty.marked_done == [[token_1, token_2]]


def test_page_projection_worker_requires_repository_session_transaction_before_claiming() -> None:
    repos = FakePageRepos(claimed=[_claim("news-1")])
    repos.news.payloads = [_page_payload("news-1")]
    worker = NewsPageProjectionWorker(
        name="news_page_projection",
        settings=_page_projection_settings(),
        db=MissingSessionTransactionDB("news_page_projection", repos),
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )

    with pytest.raises(AttributeError, match="transaction"):
        worker.run_once_sync(now_ms=NOW_MS)

    assert repos.dirty.claim_calls == []
    assert repos.news.loaded_ids == []
    assert repos.news.replacements == []
    assert repos.dirty.marked_done == []
    assert repos.dirty.marked_error == []


def test_load_items_for_page_projection_filters_target_items_before_projection_joins() -> None:
    conn = ScriptedConnection([[]])

    rows = NewsRepository(conn).load_items_for_page_projection(news_item_ids=["news-1", "news-2"])

    assert rows == []
    sql = conn.sql[-1]
    assert "WITH target_items AS (" in sql
    assert "WHERE items.news_item_id = ANY(%s::text[])" in sql
    assert "FROM target_items AS items" in sql
    assert "news_story_members" not in sql
    assert "news_story_groups" not in sql
    assert "news_item_agent_briefs" not in sql
    assert "current_brief" not in sql
    assert "page.computed_at_ms" not in sql
    assert "page.projection_version" not in sql
    assert "HAVING page.row_id IS NULL" not in sql
    assert conn.params[-1] == (["news-1", "news-2"],)


@pytest.mark.parametrize(
    ("method_name", "kwargs", "row"),
    [
        pytest.param(
            "list_news_item_source_watermarks_for_sources",
            {"source_ids": ["source-1"]},
            {"news_item_id": "news-1"},
            id="source_metadata_changed",
        ),
        pytest.param(
            "list_news_item_source_watermarks",
            {"news_item_ids": ["news-1"]},
            {"news_item_id": "news-1"},
            id="written_news_item",
        ),
        pytest.param(
            "list_news_items_for_canonical_rebuild",
            {"limit": 10},
            {"news_item_id": "news-1", "story_key": "story:v2:listing:binance:foo"},
            id="canonical_rebuild",
        ),
    ],
)
@pytest.mark.parametrize(
    "source_watermark_ms",
    [
        pytest.param(None, id="none"),
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(True, id="bool"),
        pytest.param("10", id="string"),
    ],
)
def test_news_item_source_watermark_loaders_require_positive_int_before_dirty_enqueue(
    method_name: str,
    kwargs: dict[str, Any],
    row: dict[str, Any],
    source_watermark_ms: object,
) -> None:
    conn = ScriptedConnection([[{**row, "source_watermark_ms": source_watermark_ms}]])
    method = getattr(NewsRepository(conn), method_name)

    with pytest.raises(ValueError, match="news_item_source_watermark_required:source_watermark_ms"):
        method(**kwargs)


def test_fetch_worker_enqueues_news_item_and_source_quality_dirty_for_inserted_and_updated_news_items_only() -> None:
    source = _source()
    repos = FakeFetchRepos(
        source=source,
        news_statuses=[
            {"news_item_id": "news-inserted", "status": "inserted", "affected_news_item_ids": ["news-inserted"]},
            {"news_item_id": "news-updated", "status": "updated", "affected_news_item_ids": ["news-updated"]},
            {"news_item_id": "news-duplicate", "status": "duplicate"},
        ],
    )
    worker = _fetch_worker(repos, observations=[_observation("a"), _observation("b"), _observation("c")])

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 2
    assert repos.dirty.enqueued == [
        {
            "rows": [
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-inserted",
                    "source_watermark_ms": NOW_MS,
                },
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-updated",
                    "source_watermark_ms": NOW_MS,
                },
            ],
            "reason": "news_item_written",
            "now_ms": NOW_MS,
            "commit": False,
        },
        {
            "rows": [
                {
                    "projection_name": "source_quality",
                    "target_kind": "source",
                    "target_id": "source-1",
                    "window": "_refresh",
                },
            ],
            "reason": "news_fetch_run_finished",
            "now_ms": NOW_MS,
            "commit": False,
        },
    ]
    assert "tx:upsert_canonical_news_item" in repos.conn.events
    assert "tx:dirty:news_item_written" in repos.conn.events
    assert "autocommit:dirty:news_item_written" not in repos.conn.events
    assert "direct_commit" not in repos.conn.events


def test_fetch_worker_enqueues_page_and_source_quality_dirty_for_material_source_metadata_changes_only() -> None:
    source = _source()
    repos = FakeFetchRepos(
        source=source,
        reconcile_rows=[
            {"source_id": "source-noop", "status": "duplicate"},
            {"source_id": "source-updated", "status": "updated"},
        ],
        existing_items_by_source={"source-updated": ["news-1", "news-2"]},
    )
    wake_bus = FakeWakeBus(transaction_events=repos.conn.events)
    worker = _fetch_worker(repos, observations=[], wake_bus=wake_bus)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert repos.news_item_ids_requested_for_sources == [["source-updated"]]
    assert repos.dirty.enqueued == [
        {
            "rows": [
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-1",
                    "source_watermark_ms": NOW_MS,
                },
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-2",
                    "source_watermark_ms": NOW_MS,
                },
            ],
            "reason": "source_metadata_changed",
            "now_ms": NOW_MS,
            "commit": False,
        },
        {
            "rows": [
                {
                    "projection_name": "source_quality",
                    "target_kind": "source",
                    "target_id": "source-updated",
                    "window": "_refresh",
                },
            ],
            "reason": "source_metadata_changed",
            "now_ms": NOW_MS,
            "commit": False,
        },
        {
            "rows": [
                {
                    "projection_name": "source_quality",
                    "target_kind": "source",
                    "target_id": "source-1",
                    "window": "_refresh",
                },
            ],
            "reason": "news_fetch_run_finished",
            "now_ms": NOW_MS,
            "commit": False,
        },
    ]
    assert "tx:source_reconcile" in repos.conn.events
    assert "tx:dirty:source_metadata_changed" in repos.conn.events
    assert "autocommit:dirty:source_metadata_changed" not in repos.conn.events
    assert "direct_commit" not in repos.conn.events
    assert wake_bus.notifications == [
        {
            "count": 2,
            "reason": "source_metadata_changed",
            "events_before_notify": [
                "begin",
                "tx:source_reconcile",
                "tx:dirty:source_metadata_changed",
                "tx:dirty:source_metadata_changed",
                "commit",
            ],
        }
    ]


def test_fetch_worker_requires_news_page_dirty_wake_contract_after_metadata_dirty_enqueue() -> None:
    source = _source()
    repos = FakeFetchRepos(
        source=source,
        reconcile_rows=[{"source_id": "source-updated", "status": "updated"}],
        existing_items_by_source={"source-updated": ["news-1"]},
    )
    worker = _fetch_worker(repos, observations=[], wake_bus=object())

    with pytest.raises(AttributeError, match="notify_news_page_dirty"):
        worker.run_once_sync(now_ms=NOW_MS)

    assert repos.dirty.enqueued[0]["reason"] == "source_metadata_changed"
    assert repos.conn.events[-1] == "commit"


def test_news_repository_source_reconcile_noop_does_not_update_timestamp() -> None:
    source = _source()
    existing = {
        **source,
        "source_role": "observed_source",
        "trust_tier": "standard",
        "managed_by_config": True,
        "enabled": True,
        "refresh_interval_seconds": 300,
        "coverage_tags_json": [],
        "asset_universe_json": [],
        "authority_scope_json": {},
        "fetch_policy_json": {},
        "cost_policy_json": {},
        "updated_at_ms": NOW_MS - 1_000,
    }
    conn = ScriptedConnection([[existing], existing, []])

    rows = NewsRepository(conn).reconcile_configured_sources([source], now_ms=NOW_MS, commit=False)

    assert rows[0]["status"] == "duplicate"
    assert rows[0]["updated_at_ms"] == NOW_MS - 1_000
    assert not any("ON CONFLICT (source_id) DO UPDATE" in sql for sql in conn.sql)


def test_news_repository_material_source_reconcile_reports_updated_status() -> None:
    source = {**_source(), "source_name": "Example Renamed"}
    existing = {
        **_source(),
        "source_role": "observed_source",
        "trust_tier": "standard",
        "managed_by_config": True,
        "enabled": True,
        "refresh_interval_seconds": 300,
        "coverage_tags_json": [],
        "asset_universe_json": [],
        "authority_scope_json": {},
        "fetch_policy_json": {},
        "cost_policy_json": {},
        "updated_at_ms": NOW_MS - 1_000,
    }
    updated = {**existing, "source_name": "Example Renamed", "updated_at_ms": NOW_MS}
    conn = ScriptedConnection([[existing], updated, []])

    rows = NewsRepository(conn).reconcile_configured_sources([source], now_ms=NOW_MS, commit=False)

    assert rows[0]["status"] == "updated"
    assert rows[0]["updated_at_ms"] == NOW_MS
    assert any("ON CONFLICT (source_id) DO UPDATE SET" in sql for sql in conn.sql)


@pytest.mark.parametrize("refresh_interval_seconds", [0, True, "300"])
def test_news_repository_upsert_source_rejects_malformed_refresh_interval_before_sql(
    refresh_interval_seconds: object,
) -> None:
    conn = ScriptedConnection([])

    with pytest.raises(ValueError, match="news_source_refresh_interval_seconds_required"):
        NewsRepository(conn).upsert_source(
            **_source(),
            refresh_interval_seconds=refresh_interval_seconds,  # type: ignore[arg-type]
            now_ms=NOW_MS,
            commit=False,
        )

    assert conn.sql == []


def test_news_repository_writes_require_connection_transaction_before_sql_when_committing() -> None:
    conn = MissingNewsRepositoryTransactionConnection()

    with pytest.raises(RuntimeError, match="news_repository_transaction_required"):
        NewsRepository(conn).upsert_source(**_source(), now_ms=NOW_MS)

    assert conn.sql == []
    assert conn.commits == 0


def test_news_repository_commit_owned_writes_use_connection_transaction_without_manual_commit() -> None:
    source = _source()
    inserted = {
        **source,
        "coverage_tags_json": [],
        "asset_universe_json": [],
        "authority_scope_json": {},
        "fetch_policy_json": {},
        "cost_policy_json": {},
        "updated_at_ms": NOW_MS,
    }
    conn = TransactionalScriptedConnection([[], inserted])

    row = NewsRepository(conn).upsert_source(**source, now_ms=NOW_MS)

    assert row["status"] == "inserted"
    assert conn.transaction_enter_count == 1
    assert conn.transaction_exit_count == 1
    assert conn.commits == 0
    assert conn.sql_transaction_depths == [1, 1]


def test_news_repository_caller_owned_writes_do_not_open_inner_transaction() -> None:
    source = _source()
    inserted = {
        **source,
        "coverage_tags_json": [],
        "asset_universe_json": [],
        "authority_scope_json": {},
        "fetch_policy_json": {},
        "cost_policy_json": {},
        "updated_at_ms": NOW_MS,
    }
    conn = TransactionalScriptedConnection([[], inserted])

    row = NewsRepository(conn).upsert_source(**source, now_ms=NOW_MS, commit=False)

    assert row["status"] == "inserted"
    assert conn.transaction_enter_count == 0
    assert conn.transaction_exit_count == 0
    assert conn.commits == 0
    assert conn.sql_transaction_depths == [0, 0]


def test_process_worker_enqueues_page_and_story_brief_dirty_in_same_transaction_after_writes() -> None:
    repos = FakeProcessRepos()
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=_item_process_settings(),
        db=FakeDB("news_item_process", repos),
        telemetry=object(),
        identity_lookup=FakeIdentityLookup(),
        wake_emitter=None,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert repos.news.write_commits == [False, False, False, False, False, False, False]
    assert repos.dirty.enqueued == [
        {
            "rows": [
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-1",
                    "source_watermark_ms": NOW_MS - 1_000,
                }
            ],
            "reason": "news_item_processed",
            "now_ms": NOW_MS,
            "commit": False,
        },
        {
            "rows": [
                {
                    "projection_name": "story_brief",
                    "target_kind": "story",
                    "target_id": "news-story:item:news-1",
                    "source_watermark_ms": NOW_MS - 1_000,
                    "priority": 34,
                }
            ],
            "reason": "news_item_processed",
            "now_ms": NOW_MS,
            "commit": False,
        },
    ]
    assert "direct_commit" not in repos.conn.events
    assert "tx:release_expired_processing_items" in repos.conn.events
    assert "tx:claim_unprocessed_items" in repos.conn.events
    assert "tx:replace_item_entities" in repos.conn.events
    assert "tx:dirty:news_item_processed" in repos.conn.events
    assert "autocommit:dirty:news_item_processed" not in repos.conn.events


def test_ops_projection_repair_enqueues_provider_signal_story_brief_dirty_target() -> None:
    repos = FakeOpsProjectionRepos()

    result = enqueue_projection_dirty_targets(
        repos,
        domain="news",
        execute=True,
        now_ms=NOW_MS,
        projection="story_brief",
        since_ms=NOW_MS - 60_000,
    )

    assert result["news"]["news_item_targets"] == 1
    assert repos.dirty.enqueued == [
        {
            "rows": [
                {
                    "projection_name": "story_brief",
                    "target_kind": "story",
                    "target_id": "story-provider",
                    "source_watermark_ms": NOW_MS - 1_000,
                    "priority": 48,
                }
            ],
            "reason": "ops_projection_dirty_repair",
            "now_ms": NOW_MS,
            "commit": False,
        }
    ]


def test_ops_projection_repair_enqueues_eligible_refresh_story_brief_dirty_target() -> None:
    repos = FakeOpsProjectionRepos(
        row_overrides={
            "agent_admission_status": "eligible_refresh",
            "agent_admission_reason": "material_delta",
            "agent_admission_json": {
                "eligible": True,
                "status": "eligible_refresh",
                "reason": "material_delta",
                "representative_news_item_id": "news-provider",
                "basis": {"market_scope": ["crypto"]},
                "version": "news_item_agent_admission_market_v2",
            },
        }
    )

    result = enqueue_projection_dirty_targets(
        repos,
        domain="news",
        execute=True,
        now_ms=NOW_MS,
        projection="story_brief",
        since_ms=NOW_MS - 60_000,
    )

    assert result["news"]["news_item_targets"] == 1
    assert repos.dirty.enqueued[0]["rows"] == [
        {
            "projection_name": "story_brief",
            "target_kind": "story",
            "target_id": "story-provider",
            "source_watermark_ms": NOW_MS - 1_000,
            "priority": 10,
        }
    ]


def test_brief_worker_does_not_enqueue_page_dirty_after_current_brief_write() -> None:
    repos = FakeBriefRepos()
    worker = object.__new__(NewsItemBriefWorker)
    WorkerAttrs = {
        "name": "news_item_brief",
        "settings": SimpleNamespace(statement_timeout_seconds=30),
        "db": FakeDB("news_item_brief", repos),
    }
    for key, value in WorkerAttrs.items():
        setattr(worker, key, value)
    packet = SimpleNamespace(
        news_item=SimpleNamespace(news_item_id="news-1", published_at_ms=NOW_MS - 1_000),
        input_hash="input-1",
    )

    worker._upsert_current(
        run_id="run-1",
        packet=packet,
        agent_config=SimpleNamespace(
            artifact_version_hash="artifact-v1",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
            validator_version="validator-v1",
        ),
        payload={"status": "ready", "direction": "bullish", "decision_class": "watch"},
        computed_at_ms=NOW_MS,
    )

    assert repos.news.brief_commits == [False]
    assert repos.dirty.enqueued == []
    assert "tx:upsert_news_item_agent_brief" in repos.conn.events
    assert "tx:dirty:news_item_brief_updated" not in repos.conn.events
    assert "autocommit:dirty:news_item_brief_updated" not in repos.conn.events
    assert "direct_commit" not in repos.conn.events


def test_source_quality_worker_enqueues_page_dirty_when_source_quality_status_changes() -> None:
    repos = FakeSourceQualityRepos()
    wake_bus = FakeWakeBus(transaction_events=repos.conn.events)
    worker = NewsSourceQualityProjectionWorker(
        name="news_source_quality_projection",
        settings=_source_quality_projection_settings(),
        db=FakeDB("news_source_quality_projection", repos),
        telemetry=object(),
        wake_emitter=wake_bus,
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.notes["claimed"] == 1
    assert result.notes["rescheduled"] == 1
    assert repos.news_item_ids_requested_for_sources == [["source-1"]]
    assert repos.dirty.enqueued == [
        {
            "rows": [
                {
                    "projection_name": "page",
                    "target_kind": "news_item",
                    "target_id": "news-1",
                    "source_watermark_ms": NOW_MS - 1_000,
                }
            ],
            "reason": "source_quality_status_changed",
            "now_ms": NOW_MS,
            "commit": False,
        },
        {
            "rows": [
                {
                    "projection_name": "source_quality",
                    "target_kind": "source",
                    "target_id": "source-1",
                    "window": "24h",
                    "due_at_ms": NOW_MS + 60 * 60 * 1000,
                    "source_watermark_ms": NOW_MS - 1_000,
                }
            ],
            "reason": "source_quality_window_due",
            "now_ms": NOW_MS,
            "commit": False,
            "due_at_ms": NOW_MS + 60 * 60 * 1000,
        },
    ]
    assert "tx:replace_source_quality_rows" in repos.conn.events
    assert "tx:dirty:source_quality_status_changed" in repos.conn.events
    assert "tx:dirty:source_quality_window_due" in repos.conn.events
    assert "autocommit:dirty:source_quality_status_changed" not in repos.conn.events
    assert "direct_commit" not in repos.conn.events
    assert wake_bus.notifications == [
        {
            "count": 1,
            "reason": "source_quality_status_changed",
            "events_before_notify": [
                "begin",
                "begin",
                "tx:replace_source_quality_rows",
                "tx:dirty:source_quality_status_changed",
                "tx:dirty:source_quality_window_due",
                "commit",
                "commit",
            ],
        }
    ]


def test_source_quality_worker_requires_repository_session_transaction_before_claiming() -> None:
    repos = FakeSourceQualityRepos()
    worker = NewsSourceQualityProjectionWorker(
        name="news_source_quality_projection",
        settings=_source_quality_projection_settings(),
        db=MissingSessionTransactionDB("news_source_quality_projection", repos),
        telemetry=object(),
        wake_emitter=None,
        clock_ms=lambda: NOW_MS,
    )

    with pytest.raises(AttributeError, match="transaction"):
        worker.run_once_sync(now_ms=NOW_MS)

    assert repos.dirty.claim_calls == []
    assert repos.news_item_ids_requested_for_sources == []
    assert repos.dirty.enqueued == []
    assert repos.dirty.marked_done == []
    assert repos.dirty.marked_error == []


def test_source_quality_worker_requires_news_page_dirty_wake_contract_after_page_dirty_enqueue() -> None:
    repos = FakeSourceQualityRepos()
    worker = NewsSourceQualityProjectionWorker(
        name="news_source_quality_projection",
        settings=_source_quality_projection_settings(),
        db=FakeDB("news_source_quality_projection", repos),
        telemetry=object(),
        wake_emitter=object(),
        clock_ms=lambda: NOW_MS,
    )

    with pytest.raises(AttributeError, match="notify_news_page_dirty"):
        worker.run_once_sync(now_ms=NOW_MS)

    assert repos.dirty.enqueued[0]["reason"] == "source_quality_status_changed"
    assert repos.conn.events[-1] == "commit"


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        pytest.param({"batch_size": 0}, "news_source_quality_projection_batch_size_required", id="batch-zero"),
        pytest.param({"batch_size": True}, "news_source_quality_projection_batch_size_required", id="batch-bool"),
        pytest.param({"batch_size": "10"}, "news_source_quality_projection_batch_size_required", id="batch-string"),
        pytest.param({"lease_ms": 0}, "news_source_quality_projection_lease_ms_required", id="lease-zero"),
        pytest.param({"lease_ms": True}, "news_source_quality_projection_lease_ms_required", id="lease-bool"),
        pytest.param(
            {"lease_ms": "60000"},
            "news_source_quality_projection_lease_ms_required",
            id="lease-string",
        ),
        pytest.param({"retry_ms": 0}, "news_source_quality_projection_retry_ms_required", id="retry-zero"),
        pytest.param({"retry_ms": True}, "news_source_quality_projection_retry_ms_required", id="retry-bool"),
        pytest.param(
            {"retry_ms": "30000"},
            "news_source_quality_projection_retry_ms_required",
            id="retry-string",
        ),
        pytest.param(
            {"max_attempts": 0},
            "news_source_quality_projection_max_attempts_required",
            id="attempts-zero",
        ),
        pytest.param(
            {"max_attempts": True},
            "news_source_quality_projection_max_attempts_required",
            id="attempts-bool",
        ),
        pytest.param(
            {"max_attempts": "3"},
            "news_source_quality_projection_max_attempts_required",
            id="attempts-string",
        ),
    ],
)
def test_source_quality_worker_rejects_malformed_runtime_settings_before_session(
    overrides: dict[str, object],
    error_code: str,
) -> None:
    repos = FakeSourceQualityRepos()
    worker = NewsSourceQualityProjectionWorker(
        name="news_source_quality_projection",
        settings=_raw_source_quality_projection_settings(**overrides),
        db=FakeDB("news_source_quality_projection", repos),
        telemetry=object(),
        wake_emitter=None,
        clock_ms=lambda: NOW_MS,
    )

    with pytest.raises(RuntimeError, match=error_code):
        worker.run_once_sync(now_ms=NOW_MS)

    assert repos.conn.events == []
    assert repos.dirty.claim_calls == []


def _page_worker(repos: FakePageRepos) -> NewsPageProjectionWorker:
    return NewsPageProjectionWorker(
        name="news_page_projection",
        settings=_page_projection_settings(),
        db=FakeDB("news_page_projection", repos),
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )


def _claim(news_item_id: str, *, payload_hash: str = "hash", attempt_count: int = 1) -> dict[str, Any]:
    return {
        "projection_name": "page",
        "target_kind": "news_item",
        "target_id": news_item_id,
        "window": "",
        "payload_hash": payload_hash,
        "lease_owner": "news_page_projection",
        "attempt_count": attempt_count,
    }


def _source_quality_claim(
    source_id: str,
    *,
    window: str = "24h",
    payload_hash: str = "hash",
    attempt_count: int = 1,
) -> dict[str, Any]:
    return {
        "projection_name": "source_quality",
        "target_kind": "source",
        "target_id": source_id,
        "window": window,
        "payload_hash": payload_hash,
        "lease_owner": "news_source_quality_projection",
        "attempt_count": attempt_count,
    }


def _page_payload(news_item_id: str) -> dict[str, Any]:
    story_key = f"news-story:{news_item_id}"
    item = {
        "news_item_id": news_item_id,
        "title": f"Title {news_item_id}",
        "summary": "",
        "source_id": "source-1",
        "provider_type": "rss",
        "source_domain": "example.com",
        "source_name": "Example",
        "canonical_url": f"https://example.com/{news_item_id}",
        "canonical_item_key": f"canonical-url:https://example.com/{news_item_id}",
        "published_at_ms": 1000,
        "lifecycle_status": "processed",
        "source_quality_status": "healthy",
        "content_class": "crypto_market",
        "content_tags_json": ["crypto"],
        "content_classification_json": {"policy_version": "news_content_classification_v1"},
        "market_scope_json": {
            "scope": ["crypto"],
            "primary": "crypto",
            "status": "classified",
            "reason": "crypto_evidence",
            "basis": {"crypto_evidence": ["text:crypto_subject"]},
            "version": "news_market_scope_v1",
        },
        "agent_admission_status": "eligible",
        "agent_admission_reason": "eligible",
        "agent_admission_json": {
            "eligible": True,
            "status": "eligible",
            "reason": "eligible",
            "representative_news_item_id": news_item_id,
            "basis": {"market_scope": ["crypto"], "crypto_evidence": ["text:crypto_subject"]},
            "version": "news_item_agent_admission_market_v2",
        },
        "agent_admission_version": "news_item_agent_admission_market_v2",
        "agent_representative_news_item_id": news_item_id,
        "story_key": story_key,
        "story_identity_json": {
            "story_key": story_key,
            "confidence": "strong",
            "basis": {"method": "unit_fixture"},
            "version": "news_story_identity_v1",
        },
        "story_identity_version": "news_story_identity_v1",
    }
    return {
        "item": item,
        "current_brief": None,
        "story": {
            "story_key": story_key,
            "representative_news_item_id": news_item_id,
            "member_news_item_ids": [news_item_id],
            "member_count": 1,
            "source_domains": ["example.com"],
        },
        "member_items": [dict(item)],
        "token_mentions": [],
        "fact_candidates": [],
    }


class FakePageRepos:
    def __init__(self, *, claimed: list[dict[str, Any]]) -> None:
        self.conn = FakeConn()
        self.news = FakePageNewsRepository()
        self.dirty = FakeDirtyRepository(claimed)
        self.news_projection_dirty_targets = self.dirty

    def transaction(self) -> Iterator[None]:
        return self.conn.transaction()


class FakeOpsProjectionRepos:
    def __init__(self, *, row_overrides: Mapping[str, Any] | None = None) -> None:
        self.conn = FakeOpsProjectionConn(row_overrides=row_overrides)
        self.news = self
        self.dirty = FakeDirtyRepository(expected_projection_name=None)
        self.news_projection_dirty_targets = self.dirty

    def servable_news_item_ids(self, news_item_ids: list[str]) -> list[str]:
        return [str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)]


class FakeOpsProjectionConn:
    def __init__(self, *, row_overrides: Mapping[str, Any] | None = None) -> None:
        self.row_overrides = dict(row_overrides or {})

    def execute(self, sql: str, _params: dict[str, Any] | None = None) -> Any:
        if "FROM news_items" in sql:
            row = {
                "news_item_id": "news-provider",
                "story_key": "story-provider",
                "published_at_ms": NOW_MS - 1_000,
                "source_watermark_ms": NOW_MS - 1_000,
                "lifecycle_status": "processed",
                "content_class": "crypto_market",
                "content_tags_json": ["crypto"],
                "content_classification_json": {"policy_version": "news_content_classification_v1"},
                "market_scope_json": {
                    "scope": ["crypto"],
                    "primary": "crypto",
                    "status": "classified",
                    "reason": "crypto_evidence",
                    "basis": {"crypto_evidence": ["resolved_crypto_target:cex:BTC"]},
                    "version": "news_market_scope_v1",
                },
                "agent_admission_status": "eligible",
                "agent_admission_reason": "eligible",
                "agent_admission_json": {
                    "eligible": True,
                    "status": "eligible",
                    "reason": "eligible",
                    "representative_news_item_id": "news-provider",
                    "basis": {"market_scope": ["crypto"]},
                    "version": "news_item_agent_admission_market_v2",
                },
                "agent_admission_version": "news_item_agent_admission_market_v2",
                "provider_type": "opennews",
                "provider_signal_json": {
                    "source": "provider",
                    "provider": "opennews",
                    "status": "ready",
                    "score": 95,
                },
                "token_mentions_json": [{"resolution_status": "known_symbol", "display_symbol": "BTC"}],
                "fact_candidates_json": [],
            }
            row.update(self.row_overrides)
            return FakeRowsCursor([row])
        if "FROM news_sources" in sql:
            return FakeRowsCursor([])
        raise AssertionError(f"unexpected SQL: {sql}")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        yield


class FakeRowsCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self.rows)


class FakePageNewsRepository:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.loaded_ids: list[str] = []
        self.replacements: list[dict[str, Any]] = []
        self.raise_on_replace: Exception | None = None
        self.scan_calls = 0

    def list_items_for_page_projection(self, *, limit: int) -> list[dict[str, Any]]:
        self.scan_calls += 1
        raise AssertionError("legacy page scan must not be called")

    def load_items_for_page_projection(self, *, news_item_ids: list[str]) -> list[dict[str, Any]]:
        self.loaded_ids = list(news_item_ids)
        return _payloads_in_requested_order(self.payloads, news_item_ids)

    def load_story_projection_payloads_for_items(self, *, news_item_ids: list[str]) -> list[dict[str, Any]]:
        self.loaded_ids = list(news_item_ids)
        return _payloads_in_requested_order(self.payloads, news_item_ids)

    def replace_page_rows_for_items(
        self,
        *,
        news_item_ids: list[str],
        rows: list[dict[str, Any]],
        commit: bool,
    ) -> None:
        if self.raise_on_replace is not None:
            raise self.raise_on_replace
        self.replacements.append(
            {
                "news_item_ids": list(news_item_ids),
                "row_ids": [str(row["news_item_id"]) for row in rows],
                "commit": commit,
            }
        )
        return {"deleted": max(0, len(news_item_ids) - len(rows)), "unchanged": 0}

    def replace_page_rows_for_story_targets(
        self,
        *,
        news_item_ids: list[str],
        story_keys: list[str],
        rows: list[dict[str, Any]],
        commit: bool,
    ) -> dict[str, int]:
        del story_keys
        self.replace_page_rows_for_items(news_item_ids=news_item_ids, rows=rows, commit=commit)
        return {"deleted": max(0, len(news_item_ids) - len(rows)), "unchanged": 0}


def _payloads_in_requested_order(payloads: list[dict[str, Any]], news_item_ids: list[str]) -> list[dict[str, Any]]:
    payload_by_id = {str((payload.get("item") or payload).get("news_item_id") or ""): payload for payload in payloads}
    return [payload_by_id[news_item_id] for news_item_id in news_item_ids if news_item_id in payload_by_id]


class FakeDirtyRepository:
    def __init__(
        self,
        claimed: list[dict[str, Any]] | None = None,
        *,
        expected_projection_name: str | None = "page",
    ) -> None:
        self.claimed = claimed or []
        self.expected_projection_name = expected_projection_name
        self.enqueued: list[dict[str, Any]] = []
        self.claim_calls: list[dict[str, Any]] = []
        self.marked_done: list[list[dict[str, Any]]] = []
        self.marked_error: list[list[dict[str, Any]]] = []
        self.mark_error_calls: list[dict[str, Any]] = []
        self.terminalized: list[dict[str, Any]] = []
        self.conn: FakeConn | None = None

    def claim_due(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.claim_calls.append(dict(kwargs))
        if self.expected_projection_name is not None:
            assert kwargs["projection_name"] == self.expected_projection_name
        assert kwargs["commit"] is False
        return [dict(row) for row in self.claimed[: kwargs["limit"]]]

    def enqueue_targets(
        self,
        rows: list[Mapping[str, Any]],
        *,
        reason: str,
        now_ms: int,
        commit: bool = True,
        due_at_ms: int | None = None,
    ) -> int:
        if self.conn is not None:
            self.conn.record(f"dirty:{reason}")
        payload = {
            "rows": [dict(row) for row in rows],
            "reason": reason,
            "now_ms": now_ms,
            "commit": commit,
        }
        if due_at_ms is not None:
            payload["due_at_ms"] = due_at_ms
        self.enqueued.append(payload)
        return len(rows)

    def mark_done(self, rows: list[Mapping[str, Any]], *, now_ms: int, commit: bool = True) -> int:
        self.marked_done.append([dict(row) for row in rows])
        return len(rows)

    def mark_error(
        self,
        rows: list[Mapping[str, Any]],
        *,
        error: str,
        retry_ms: int,
        now_ms: int,
        count_attempt: bool = True,
        commit: bool = True,
    ) -> int:
        del count_attempt
        self.mark_error_calls.append({"error": error, "retry_ms": retry_ms, "now_ms": now_ms, "commit": commit})
        self.marked_error.append([dict(row) for row in rows])
        return len(rows)

    def terminalize_targets(
        self,
        rows: list[Mapping[str, Any]],
        *,
        worker_name: str,
        final_reason: str,
        final_reason_bucket: str,
        now_ms: int,
        commit: bool = True,
        **_kwargs: Any,
    ) -> int:
        self.terminalized.append(
            {
                "rows": [dict(row) for row in rows],
                "worker_name": worker_name,
                "final_reason": final_reason,
                "final_reason_bucket": final_reason_bucket,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return len(rows)


def _fetch_worker(
    repos: FakeFetchRepos,
    *,
    observations: list[NewsProviderObservation],
    wake_bus: Any | None = None,
) -> NewsFetchWorker:
    return NewsFetchWorker(
        name="news_fetch",
        settings=_news_fetch_settings(),
        db=FakeDB("news_fetch", repos),
        telemetry=object(),
        news_settings=SimpleNamespace(sources=(SimpleNamespace(provider_type="rss"),)),
        wake_emitter=wake_bus,
        feed_client=FakeProvider(observations),
    )


class FakeFetchRepos:
    def __init__(
        self,
        *,
        source: dict[str, Any],
        news_statuses: list[dict[str, Any]] | None = None,
        reconcile_rows: list[dict[str, Any]] | None = None,
        existing_items_by_source: dict[str, list[str]] | None = None,
        item_watermarks_by_item: dict[str, int] | None = None,
    ) -> None:
        self.conn = FakeConn()
        self.source = source
        self.news_statuses = list(news_statuses or [])
        self.reconcile_rows = list(reconcile_rows or [])
        self.existing_items_by_source = dict(existing_items_by_source or {})
        self.item_watermarks_by_item = dict(item_watermarks_by_item or {})
        self.news_item_ids_requested_for_sources: list[list[str]] = []
        self.news = self
        self.dirty = FakeDirtyRepository()
        self.dirty.conn = self.conn
        self.news_projection_dirty_targets = self.dirty
        self.sync_cursors: dict[str, dict[str, Any]] = {}
        self.sync_updates: list[dict[str, Any]] = []

    def transaction(self) -> Iterator[None]:
        return self.conn.transaction()

    def reconcile_configured_sources(
        self,
        sources: tuple[dict[str, Any], ...],
        *,
        now_ms: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        assert commit is False
        self.conn.record("source_reconcile")
        return [dict(row) for row in self.reconcile_rows]

    def news_source_provider_constraint_values(self) -> tuple[str, ...]:
        return NEWS_SOURCE_PROVIDER_SCHEMA_TYPES

    def claim_due_sources(
        self,
        *,
        now_ms: int,
        limit: int,
        claim_lease_ms: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        del claim_lease_ms
        assert commit is False
        return [dict(self.source)]

    def list_news_item_ids_for_sources(self, *, source_ids: list[str]) -> list[str]:
        self.news_item_ids_requested_for_sources.append(list(source_ids))
        result: list[str] = []
        for source_id in source_ids:
            result.extend(self.existing_items_by_source.get(source_id, []))
        return result

    def list_news_item_source_watermarks_for_sources(self, *, source_ids: list[str]) -> list[dict[str, Any]]:
        self.news_item_ids_requested_for_sources.append(list(source_ids))
        return [
            {"news_item_id": news_item_id, "source_watermark_ms": NOW_MS}
            for source_id in source_ids
            for news_item_id in self.existing_items_by_source.get(source_id, [])
        ]

    def list_news_item_source_watermarks(self, *, news_item_ids: list[str]) -> list[dict[str, Any]]:
        return [
            {
                "news_item_id": news_item_id,
                "source_watermark_ms": self.item_watermarks_by_item.get(news_item_id, NOW_MS),
            }
            for news_item_id in news_item_ids
        ]

    def servable_news_item_ids(self, news_item_ids: list[str]) -> list[str]:
        return [str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)]

    def start_fetch_run(self, *, source_id: str, started_at_ms: int, commit: bool = True) -> str:
        assert commit is False
        self.conn.record("start_fetch_run")
        return "fetch-run-1"

    def source_sync_cursor(self, source_id: str) -> dict[str, Any]:
        return dict(self.sync_cursors.get(source_id, {}))

    def update_source_sync_state(
        self,
        source_id: str,
        next_cursor: dict[str, Any],
        *,
        now_ms: int,
        commit: bool = True,
    ) -> None:
        assert commit is False
        self.conn.record("update_source_sync_state")
        self.sync_updates.append(
            {"source_id": source_id, "next_cursor": dict(next_cursor), "now_ms": now_ms, "commit": commit}
        )

    def upsert_provider_item(self, **payload: Any) -> dict[str, Any]:
        self.conn.record("upsert_provider_item")
        provider_article_id = str(payload["raw_payload"].get("id") or "")
        return {
            "provider_item_id": f"provider-{payload['source_item_key']}",
            "provider_article_id": provider_article_id,
            "provider_article_key": f"fake:{provider_article_id}" if provider_article_id else "",
            "status": "inserted",
        }

    def upsert_canonical_news_item(self, **payload: Any) -> dict[str, Any]:
        self.conn.record("upsert_canonical_news_item")
        assert payload["canonical_identity"].canonical_item_key.startswith("canonical-url:")
        result = dict(self.news_statuses.pop(0))
        self._record_item_source_watermarks(result, payload)
        return result

    def _record_item_source_watermarks(self, result: dict[str, Any], payload: dict[str, Any]) -> None:
        status = str(result.get("status") or "")
        if status not in {"inserted", "updated"}:
            return
        published_at_ms = payload.get("published_at_ms")
        fetched_at_ms = payload.get("fetched_at_ms")
        source_watermark_ms = int(published_at_ms if published_at_ms is not None else fetched_at_ms)
        for news_item_id in result.get("affected_news_item_ids") or [result.get("news_item_id")]:
            item_id = str(news_item_id or "")
            if item_id and item_id not in self.item_watermarks_by_item:
                self.item_watermarks_by_item[item_id] = source_watermark_ms

    def update_source_http_cache(self, **payload: Any) -> None:
        self.conn.record("update_source_http_cache")

    def finish_fetch_run(self, **payload: Any) -> dict[str, Any]:
        self.conn.record("finish_fetch_run")
        return dict(payload)


class FakeProvider:
    provider_type = "fake"

    def __init__(self, observations: list[NewsProviderObservation]) -> None:
        self.observations = observations

    def fetch(self, source: NewsSourceSnapshot, **kwargs: Any) -> NewsProviderFetchResult:
        return NewsProviderFetchResult(status_code=200, observations=self.observations)


def _source() -> dict[str, Any]:
    return {
        "source_id": "source-1",
        "provider_type": "rss",
        "feed_url": "https://example.com/rss.xml",
        "source_domain": "example.com",
        "source_name": "Example",
    }


def _observation(key: str) -> NewsProviderObservation:
    return NewsProviderObservation(
        source_item_key=key,
        canonical_url=f"https://example.com/news/{key}",
        title=f"Title {key}",
        summary="",
        body_text="",
        language="en",
        published_at_ms=NOW_MS,
        raw_payload={"id": key},
    )


class FakeProcessRepos:
    def __init__(self) -> None:
        self.conn = FakeConn()
        self.news = self
        self.dirty = FakeDirtyRepository()
        self.dirty.conn = self.conn
        self.news_projection_dirty_targets = self.dirty
        self.write_commits: list[bool] = []
        self.items = [
            {
                "news_item_id": "news-1",
                "source_id": "source-1",
                "source_role": "official_exchange",
                "source_domain": "coinbase.com",
                "authority_scope_json": {"event_types": ["exchange_listing"], "domains": ["coinbase.com"]},
                "title": "Coinbase lists $BTC for trading",
                "summary": "",
                "body_text": "",
                "published_at_ms": NOW_MS - 1_000,
                "processing_attempts": 1,
                "processing_lease_owner": "news_item_process",
                "provider_signal_json": {
                    "source": "provider",
                    "provider": "opennews",
                    "status": "ready",
                    "score": 86,
                },
            }
        ]
        self.entities: dict[str, list[dict[str, Any]]] = {}
        self.mentions: dict[str, list[dict[str, Any]]] = {}
        self.fact_candidates: dict[str, list[dict[str, Any]]] = {}
        self.content_classifications: dict[str, dict[str, Any]] = {}
        self.market_scope_story_updates: dict[str, dict[str, Any]] = {}

    def transaction(self) -> Iterator[None]:
        return self.conn.transaction()

    def release_expired_processing_items(self, *, now_ms: int, commit: bool = True) -> int:
        self.conn.record("release_expired_processing_items")
        return 0

    def claim_unprocessed_items(
        self,
        *,
        limit: int,
        lease_owner: str,
        lease_ms: int,
        now_ms: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        del lease_ms, commit
        self.conn.record("claim_unprocessed_items")
        self.items[0]["processing_lease_owner"] = lease_owner
        return [dict(row) for row in self.items[:limit]]

    def replace_item_entities(self, news_item_id: str, entities: list[Any], *, commit: bool = True) -> None:
        self.conn.record("replace_item_entities")
        self.write_commits.append(commit)
        self.entities[news_item_id] = [_object_payload(entity) for entity in entities]

    def replace_token_mentions(self, news_item_id: str, mentions: list[Any], *, commit: bool = True) -> None:
        self.conn.record("replace_token_mentions")
        self.write_commits.append(commit)
        self.mentions[news_item_id] = [_object_payload(mention) for mention in mentions]

    def replace_fact_candidates(self, news_item_id: str, candidates: list[Any], *, commit: bool = True) -> None:
        self.conn.record("replace_fact_candidates")
        self.write_commits.append(commit)
        self.fact_candidates[news_item_id] = [_object_payload(candidate) for candidate in candidates]

    def update_item_content_classification(self, **payload: Any) -> None:
        self.conn.record("update_item_content_classification")
        self.write_commits.append(payload["commit"])
        self.content_classifications[str(payload["news_item_id"])] = dict(payload)

    def update_item_market_scope_and_story_identity(self, **payload: Any) -> None:
        self.conn.record("update_item_market_scope_and_story_identity")
        self.write_commits.append(payload["commit"])
        self.market_scope_story_updates[str(payload["news_item_id"])] = dict(payload)

    def load_agent_admission_contexts(self, *, news_item_ids: list[str], now_ms: int) -> list[dict[str, Any]]:
        del now_ms
        rows: list[dict[str, Any]] = []
        for news_item_id in news_item_ids:
            item = next((dict(row) for row in self.items if row.get("news_item_id") == news_item_id), None)
            if item is None:
                continue
            classification = self.content_classifications.get(news_item_id, {})
            story_update = self.market_scope_story_updates.get(news_item_id, {})
            market_scope = story_update.get("market_scope")
            story_identity = story_update.get("story_identity")
            item.update(
                {
                    "lifecycle_status": "processed",
                    "content_class": classification.get("content_class") or "",
                    "content_tags_json": classification.get("content_tags") or [],
                    "content_classification_json": classification.get("classification_payload") or {},
                    "market_scope_json": (
                        market_scope.to_payload()
                        if hasattr(market_scope, "to_payload")
                        else getattr(market_scope, "__dict__", {})
                    ),
                    "agent_admission_status": item.get("agent_admission_status", ""),
                    "agent_admission_reason": item.get("agent_admission_reason", ""),
                    "agent_admission_json": item.get("agent_admission_json", {}),
                    "story_key": getattr(story_identity, "story_key", item.get("story_key", "")),
                }
            )
            rows.append(
                {
                    "item": item,
                    "entities": list(self.entities.get(news_item_id, [])),
                    "token_mentions": list(self.mentions.get(news_item_id, [])),
                    "fact_candidates": list(self.fact_candidates.get(news_item_id, [])),
                    "current_brief": None,
                    "exact_duplicate_candidates": [],
                    "story_candidates": [],
                }
            )
        return rows

    def servable_news_item_ids(self, news_item_ids: list[str]) -> list[str]:
        return [str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)]

    def update_item_agent_admission(self, **payload: Any) -> int:
        self.conn.record("update_item_agent_admission")
        self.write_commits.append(payload["commit"])
        return 1

    def mark_item_processed(
        self,
        *,
        news_item_id: str,
        processed_at_ms: int,
        lease_owner: str,
        processing_attempts: int,
        commit: bool = True,
    ) -> int:
        del lease_owner, processing_attempts
        self.conn.record("mark_item_processed")
        self.write_commits.append(commit)
        return 1

    def mark_item_process_retryable(self, **payload: Any) -> int:
        raise AssertionError("process should not fail")

    def mark_item_process_terminal_failed(self, **payload: Any) -> int:
        raise AssertionError("process should not fail")


class FakeIdentityLookup:
    def resolve_address(self, *, chain_id: str | None, address: str) -> Any:
        raise AssertionError("address lookup should not be called")

    def resolve_symbol(self, *, symbol: str) -> TokenIdentityLookupResult:
        return TokenIdentityLookupResult(
            resolution_status="EXACT",
            target_type="CexToken",
            target_id=f"cex:{symbol}",
            display_symbol=symbol,
            display_name="Bitcoin",
            reason_codes=["CONFIRMED_CEX_TOKEN"],
            candidate_targets=[],
        )


def _object_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return dict(asdict(value))
    return dict(getattr(value, "__dict__", {}))


class FakeBriefRepos:
    def __init__(self) -> None:
        self.conn = FakeConn()
        self.news = self
        self.dirty = FakeDirtyRepository()
        self.dirty.conn = self.conn
        self.news_projection_dirty_targets = self.dirty
        self.brief_commits: list[bool] = []

    def transaction(self) -> Iterator[None]:
        return self.conn.transaction()

    def upsert_news_item_agent_brief(self, **payload: Any) -> dict[str, Any]:
        self.conn.record("upsert_news_item_agent_brief")
        self.brief_commits.append(payload["commit"])
        return dict(payload)

    def list_source_ids_for_news_items(self, *, news_item_ids: list[str]) -> list[str]:
        assert news_item_ids == ["news-1"]
        return ["source-1"]

    def servable_news_item_ids(self, news_item_ids: list[str]) -> list[str]:
        return [str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)]


class FakeSourceQualityRepos:
    def __init__(self) -> None:
        self.conn = FakeConn()
        self.news = self
        self.dirty = FakeDirtyRepository(
            [_source_quality_claim("source-1")],
            expected_projection_name="source_quality",
        )
        self.dirty.conn = self.conn
        self.news_projection_dirty_targets = self.dirty
        self.news_item_ids_requested_for_sources: list[list[str]] = []

    def transaction(self) -> Iterator[None]:
        return self.conn.transaction()

    def list_source_quality_inputs_for_targets(
        self,
        *,
        source_windows: list[tuple[str, str]],
        now_ms: int,
    ) -> list[dict[str, Any]]:
        assert source_windows == [("source-1", "24h")]
        return [
            {
                "source_id": "source-1",
                "window": "24h",
                "fetch_run_count": 1,
                "fetch_success_count": 1,
                "items_fetched": 1,
                "items_inserted": 1,
                "items_duplicate": 0,
                "item_count": 1,
                "processed_item_count": 1,
                "mention_count": 1,
                "resolved_mention_count": 1,
                "fact_count": 1,
                "attention_fact_count": 0,
                "accepted_fact_count": 1,
                "ready_brief_count": 1,
                "useful_item_count": 1,
                "latest_item_published_at_ms": NOW_MS - 1_000,
                "median_lag_ms": 100,
            }
        ]

    def replace_source_quality_rows(
        self,
        *,
        rows: list[Mapping[str, Any]],
        status_window: str,
        commit: bool = True,
    ) -> list[str]:
        assert commit is False
        self.conn.record("replace_source_quality_rows")
        return ["source-1"]

    def list_news_item_ids_for_sources(self, *, source_ids: list[str]) -> list[str]:
        self.news_item_ids_requested_for_sources.append(list(source_ids))
        return ["news-1"]

    def servable_news_item_ids(self, news_item_ids: list[str]) -> list[str]:
        return [str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)]


class FakeDB:
    def __init__(self, expected_name: str, repos: Any, *, expected_statement_timeout: float | None = 30) -> None:
        self.expected_name = expected_name
        self.repos = repos
        self.expected_statement_timeout = expected_statement_timeout

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None) -> Iterator[Any]:
        assert name == self.expected_name
        assert statement_timeout_seconds == self.expected_statement_timeout
        yield self.repos


class MissingSessionTransactionDB:
    def __init__(self, expected_name: str, repos: Any) -> None:
        self.expected_name = expected_name
        self.repos = repos

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None) -> Iterator[Any]:
        assert name == self.expected_name
        assert statement_timeout_seconds == 30
        yield SimpleNamespace(
            conn=object(),
            news=self.repos.news,
            news_projection_dirty_targets=self.repos.news_projection_dirty_targets,
        )


class FakeWakeBus:
    def __init__(self, *, transaction_events: list[str]) -> None:
        self.transaction_events = transaction_events
        self.notifications: list[dict[str, Any]] = []

    def notify_news_page_dirty(self, *, count: int, reason: str) -> None:
        self.notifications.append(
            {
                "count": int(count),
                "reason": str(reason),
                "events_before_notify": list(self.transaction_events),
            }
        )


class FakeConn:
    def __init__(self) -> None:
        self.commits = 0
        self.events: list[str] = []
        self._transaction_depth = 0

    def commit(self) -> None:
        self.commits += 1
        self.events.append("direct_commit")

    def record(self, label: str) -> None:
        prefix = "tx" if self._transaction_depth else "autocommit"
        self.events.append(f"{prefix}:{label}")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.events.append("begin")
        self._transaction_depth += 1
        try:
            yield
        except Exception:
            self.events.append("rollback")
            raise
        else:
            self.events.append("commit")
        finally:
            self._transaction_depth -= 1


_DEFAULT_CURSOR_ROWCOUNT = object()


class ScriptedConnection:
    def __init__(
        self,
        results: list[Any],
        *,
        rowcount: object = _DEFAULT_CURSOR_ROWCOUNT,
        omit_rowcount: bool = False,
    ) -> None:
        self.results = list(results)
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.commits = 0
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount

    def execute(self, sql: str, params: Any = None) -> ScriptedCursor:
        self.sql.append(sql)
        self.params.append(params)
        result = self.results.pop(0) if self.results else []
        return ScriptedCursor(result, rowcount=self.rowcount, omit_rowcount=self.omit_rowcount)

    def commit(self) -> None:
        self.commits += 1


class TransactionalScriptedConnection(ScriptedConnection):
    def __init__(
        self,
        results: list[Any],
        *,
        rowcount: object = _DEFAULT_CURSOR_ROWCOUNT,
        omit_rowcount: bool = False,
    ) -> None:
        super().__init__(results, rowcount=rowcount, omit_rowcount=omit_rowcount)
        self.transaction_depth = 0
        self.transaction_enter_count = 0
        self.transaction_exit_count = 0
        self.sql_transaction_depths: list[int] = []

    def execute(self, sql: str, params: Any = None) -> ScriptedCursor:
        self.sql_transaction_depths.append(self.transaction_depth)
        return super().execute(sql, params)

    def transaction(self) -> TransactionalScriptedConnectionTransaction:
        return TransactionalScriptedConnectionTransaction(self)

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError("news repository must not manually commit when commit is owned")


class TransactionalScriptedConnectionTransaction:
    def __init__(self, conn: TransactionalScriptedConnection) -> None:
        self.conn = conn

    def __enter__(self) -> TransactionalScriptedConnectionTransaction:
        self.conn.transaction_enter_count += 1
        self.conn.transaction_depth += 1
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.conn.transaction_exit_count += 1
        self.conn.transaction_depth -= 1


class MissingNewsRepositoryTransactionConnection:
    transaction = None

    def __init__(self) -> None:
        self.sql: list[str] = []
        self.commits = 0

    def execute(self, sql: str, params: Any = None) -> ScriptedCursor:
        self.sql.append(sql)
        raise AssertionError("news repository must fail before SQL when transaction is missing")

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError("news repository must not manually commit when transaction is missing")


class MissingTransactionConnection:
    transaction = None

    def __init__(self) -> None:
        self.sql: list[str] = []
        self.commits = 0

    def execute(self, sql: str, params: Any = None) -> ScriptedCursor:
        self.sql.append(sql)
        raise AssertionError("dirty target repository must fail before SQL when transaction is missing")

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError("dirty target repository must not manually commit when transaction is missing")


class ScriptedCursor:
    def __init__(
        self,
        result: Any,
        *,
        rowcount: object = _DEFAULT_CURSOR_ROWCOUNT,
        omit_rowcount: bool = False,
    ) -> None:
        self.result = result
        if not omit_rowcount:
            if rowcount is _DEFAULT_CURSOR_ROWCOUNT:
                self.rowcount = len(result) if isinstance(result, list) else 1
            else:
                self.rowcount = rowcount

    def fetchone(self) -> Any:
        if isinstance(self.result, list):
            return self.result[0] if self.result else None
        return self.result

    def fetchall(self) -> list[Any]:
        if isinstance(self.result, list):
            return self.result
        return [self.result]
