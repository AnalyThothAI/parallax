from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_manifest import require_worker_manifest
from gmgn_twitter_intel.app.runtime.worker_space import WorkerSpaceContract, contract_from_manifest
from gmgn_twitter_intel.domains.equity_event_intel.repositories.equity_event_repository import (
    EquityEventRepository,
)
from gmgn_twitter_intel.domains.equity_event_intel.runtime import (
    equity_event_process_worker as process_module,
)
from gmgn_twitter_intel.domains.equity_event_intel.runtime import (
    equity_event_source_reconcile_worker as reconcile_module,
)
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_brief_worker import (
    EquityEventBriefWorker,
)
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_page_projection_worker import (
    EquityEventPageProjectionWorker,
)
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_process_worker import (
    EquityEventProcessWorker,
)
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_source_reconcile_worker import (
    EquityEventSourceReconcileWorker,
)

NOW_MS = 1_700_000_000_000


def _worker_contract(worker_name: str) -> WorkerSpaceContract:
    return contract_from_manifest(require_worker_manifest(worker_name))


def test_empty_dirty_queue_does_not_call_broad_discovery() -> None:
    equity_repo = _FakeProjectionEquityRepository()
    dirty_repo = _FakeDirtyTargetRepository(claimed=[])
    worker = _projection_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert result.notes["claimed"] == 0
    assert "event_scan" not in result.notes
    assert dirty_repo.claimed_projection_names == ["page", "timeline", "alert", "calendar"]


def test_claimed_company_event_loads_only_claimed_ids_and_writes_scoped_rows() -> None:
    event_id = "event-1"
    equity_repo = _FakeProjectionEquityRepository(
        event_payloads=[
            _event_projection_payload(
                company_event_id=event_id,
                source_watermark_ms=NOW_MS - 100,
            )
        ]
    )
    dirty_repo = _FakeDirtyTargetRepository(
        claimed=[
            _claim("page", "company_event", event_id),
            _claim("timeline", "company_event", event_id),
            _claim("alert", "company_event", event_id),
        ]
    )
    worker = _projection_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert equity_repo.loaded_company_event_ids == [[event_id]]
    assert equity_repo.replaced_page_scopes == [[event_id]]
    assert equity_repo.replaced_timeline_scopes == [[event_id]]
    assert equity_repo.replaced_alert_scopes == [[event_id]]
    assert len(equity_repo.page_rows) == 1
    assert len(equity_repo.timeline_rows) == 1
    assert len(equity_repo.alert_rows) == 1
    assert dirty_repo.done == dirty_repo.claimed
    assert dirty_repo.errors == []


def test_page_only_company_event_claim_writes_only_page_rows() -> None:
    event_id = "event-page-only"
    equity_repo = _FakeProjectionEquityRepository(
        event_payloads=[_event_projection_payload(company_event_id=event_id, source_watermark_ms=NOW_MS - 100)]
    )
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("page", "company_event", event_id)])
    worker = _projection_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert equity_repo.loaded_company_event_ids == [[event_id]]
    assert equity_repo.replaced_page_scopes == [[event_id]]
    assert equity_repo.replaced_timeline_scopes == []
    assert equity_repo.replaced_alert_scopes == []
    assert len(equity_repo.page_rows) == 1
    assert equity_repo.timeline_rows == []
    assert equity_repo.alert_rows == []
    assert dirty_repo.done == dirty_repo.claimed


def test_timeline_only_company_event_claim_writes_only_timeline_rows() -> None:
    event_id = "event-timeline-only"
    equity_repo = _FakeProjectionEquityRepository(
        event_payloads=[_event_projection_payload(company_event_id=event_id, source_watermark_ms=NOW_MS - 100)]
    )
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("timeline", "company_event", event_id)])
    worker = _projection_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert equity_repo.loaded_company_event_ids == [[event_id]]
    assert equity_repo.replaced_page_scopes == []
    assert equity_repo.replaced_timeline_scopes == [[event_id]]
    assert equity_repo.replaced_alert_scopes == []
    assert equity_repo.page_rows == []
    assert len(equity_repo.timeline_rows) == 1
    assert equity_repo.alert_rows == []
    assert dirty_repo.done == dirty_repo.claimed


def test_alert_only_company_event_claim_writes_only_alert_rows() -> None:
    event_id = "event-alert-only"
    equity_repo = _FakeProjectionEquityRepository(
        event_payloads=[_event_projection_payload(company_event_id=event_id, source_watermark_ms=NOW_MS - 100)]
    )
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("alert", "company_event", event_id)])
    worker = _projection_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert equity_repo.loaded_company_event_ids == [[event_id]]
    assert equity_repo.replaced_page_scopes == []
    assert equity_repo.replaced_timeline_scopes == []
    assert equity_repo.replaced_alert_scopes == [[event_id]]
    assert equity_repo.page_rows == []
    assert equity_repo.timeline_rows == []
    assert len(equity_repo.alert_rows) == 1
    assert dirty_repo.done == dirty_repo.claimed


def test_claimed_expected_event_loads_only_claimed_ids_and_writes_calendar_rows() -> None:
    expected_event_id = "expected-1"
    equity_repo = _FakeProjectionEquityRepository(
        calendar_payloads=[_calendar_projection_payload(expected_event_id=expected_event_id)]
    )
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("calendar", "expected_event", expected_event_id)])
    worker = _projection_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert equity_repo.loaded_expected_event_ids == [[expected_event_id]]
    assert equity_repo.loaded_calendar_now_ms == [NOW_MS]
    assert equity_repo.replaced_page_scopes == []
    assert equity_repo.replaced_timeline_scopes == []
    assert equity_repo.replaced_alert_scopes == []
    assert equity_repo.replaced_calendar_scopes == [[expected_event_id]]
    assert len(equity_repo.calendar_rows) == 1
    assert dirty_repo.done == dirty_repo.claimed


def test_missing_or_ineligible_page_claim_deletes_only_scoped_page_rows_and_marks_done() -> None:
    event_id = "event-missing"
    equity_repo = _FakeProjectionEquityRepository(event_payloads=[])
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("page", "company_event", event_id)])
    worker = _projection_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.notes["deleted"] == 1
    assert equity_repo.replaced_page_scopes == [[event_id]]
    assert equity_repo.replaced_timeline_scopes == []
    assert equity_repo.replaced_alert_scopes == []
    assert equity_repo.page_rows == []
    assert equity_repo.timeline_rows == []
    assert equity_repo.alert_rows == []
    assert dirty_repo.done == dirty_repo.claimed


def test_missing_or_ineligible_timeline_claim_deletes_only_scoped_timeline_rows_and_marks_done() -> None:
    event_id = "event-missing"
    equity_repo = _FakeProjectionEquityRepository(event_payloads=[])
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("timeline", "company_event", event_id)])
    worker = _projection_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.notes["deleted"] == 1
    assert equity_repo.replaced_page_scopes == []
    assert equity_repo.replaced_timeline_scopes == [[event_id]]
    assert equity_repo.replaced_alert_scopes == []
    assert dirty_repo.done == dirty_repo.claimed


def test_missing_or_ineligible_alert_claim_deletes_only_scoped_alert_rows_and_marks_done() -> None:
    event_id = "event-missing"
    equity_repo = _FakeProjectionEquityRepository(event_payloads=[])
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("alert", "company_event", event_id)])
    worker = _projection_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.notes["deleted"] == 1
    assert equity_repo.replaced_page_scopes == []
    assert equity_repo.replaced_timeline_scopes == []
    assert equity_repo.replaced_alert_scopes == [[event_id]]
    assert dirty_repo.done == dirty_repo.claimed


def test_missing_or_inactive_expected_event_deletes_scoped_calendar_row_and_marks_done() -> None:
    expected_event_id = "expected-missing"
    equity_repo = _FakeProjectionEquityRepository(calendar_payloads=[])
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("calendar", "expected_event", expected_event_id)])
    worker = _projection_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.notes["deleted"] == 1
    assert equity_repo.replaced_calendar_scopes == [[expected_event_id]]
    assert equity_repo.calendar_rows == []
    assert dirty_repo.done == dirty_repo.claimed


def test_projection_failure_marks_error_and_does_not_mark_done() -> None:
    equity_repo = _FakeProjectionEquityRepository(load_error=RuntimeError("loader failed"))
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("page", "company_event", "event-1")])
    worker = _projection_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert dirty_repo.done == []
    assert dirty_repo.errors == [dirty_repo.claimed]
    assert "loader failed" in dirty_repo.error_messages[0]


def test_projection_write_failure_rolls_back_prior_scoped_writes_and_marks_error() -> None:
    event_id = "event-1"
    equity_repo = _FakeProjectionEquityRepository(
        event_payloads=[_event_projection_payload(company_event_id=event_id, source_watermark_ms=NOW_MS - 100)],
        fail_replacements={"timeline"},
    )
    dirty_repo = _FakeDirtyTargetRepository(
        claimed=[
            _claim("page", "company_event", event_id),
            _claim("timeline", "company_event", event_id),
        ]
    )
    worker = _projection_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 2
    assert equity_repo.replaced_page_scopes == []
    assert equity_repo.page_rows == []
    assert dirty_repo.done == []
    assert dirty_repo.errors == [dirty_repo.claimed]
    assert "rollback_savepoint" in equity_repo.conn.transaction_events


def test_future_calendar_boundary_survives_current_claim_done_and_is_not_due_early() -> None:
    expected_event_id = "expected-future"
    expected_at_ms = NOW_MS + 10_000
    equity_repo = _FakeProjectionEquityRepository(
        calendar_payloads=[
            _calendar_projection_payload(expected_event_id=expected_event_id, expected_at_ms=expected_at_ms)
        ]
    )
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("calendar", "expected_event", expected_event_id)])
    worker = _projection_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    first_result = worker.run_once_sync(now_ms=NOW_MS)
    idle_result = worker.run_once_sync(now_ms=NOW_MS + 1_000)

    assert first_result.processed == 1
    assert idle_result.processed == 0
    assert dirty_repo.pending_keys() == [("calendar", "expected_event", expected_event_id)]
    assert dirty_repo.pending[0]["due_at_ms"] == expected_at_ms + 1
    assert dirty_repo.done[0]["target_id"] == expected_event_id
    assert dirty_repo.enqueue_calls[-1]["reason"] == "calendar_status_boundary"


def test_batch_size_one_rotates_claims_to_calendar_after_page() -> None:
    event_id = "event-1"
    expected_event_id = "expected-1"
    equity_repo = _FakeProjectionEquityRepository(
        event_payloads=[_event_projection_payload(company_event_id=event_id, source_watermark_ms=NOW_MS - 100)],
        calendar_payloads=[_calendar_projection_payload(expected_event_id=expected_event_id)],
    )
    dirty_repo = _FakeDirtyTargetRepository(
        claimed=[
            _claim("page", "company_event", event_id),
            _claim("calendar", "expected_event", expected_event_id),
        ]
    )
    worker = _projection_worker(equity_repo=equity_repo, dirty_repo=dirty_repo, batch_size=1)

    first_result = worker.run_once_sync(now_ms=NOW_MS)
    second_result = worker.run_once_sync(now_ms=NOW_MS + 1)

    assert first_result.processed == 1
    assert second_result.processed == 1
    assert dirty_repo.done[0]["projection_name"] == "page"
    assert dirty_repo.done[1]["projection_name"] == "calendar"
    assert dirty_repo.pending == []


def test_event_processing_enqueues_projection_and_matching_calendar_targets_in_same_transaction(monkeypatch) -> None:
    event_id = "event-1"
    document_id = "doc-1"
    equity_repo = _FakeProcessEquityRepository(
        document={"event_document_id": document_id, "source_id": "source-1", "body_text": "Revenue was up."},
        old_event_ids=["old-event-1"],
        matching_expected_event_ids=["expected-1"],
    )
    dirty_repo = _FakeDirtyTargetRepository()
    monkeypatch.setattr(
        process_module,
        "validate_company_identity",
        lambda _document: SimpleNamespace(validation_status="accepted"),
    )
    monkeypatch.setattr(
        process_module,
        "classify_equity_event",
        lambda _document: SimpleNamespace(
            company_event_id=event_id,
            company_id="company-1",
            ticker="MSFT",
            primary_document_id=document_id,
            event_type="quarterly_report",
            priority="P0",
            source_role="official_issuer",
            fiscal_period="2026Q1",
            event_time_ms=NOW_MS - 1_000,
            discovered_at_ms=NOW_MS - 900,
            lifecycle_status="processed",
            summary="MSFT report",
        ),
    )
    monkeypatch.setattr(process_module, "build_source_spans", lambda **_kwargs: [SimpleNamespace(span_id="span-1")])
    monkeypatch.setattr(process_module, "build_fact_candidates", lambda **_kwargs: [])
    worker = EquityEventProcessWorker(
        name="equity_event_process",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=None),
        db=_FakeDb(equity_repo=equity_repo, dirty_repo=dirty_repo),
        telemetry=SimpleNamespace(),
        worker_space_contract=_worker_contract("equity_event_process"),
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert equity_repo.conn.commits == 1
    assert dirty_repo.enqueue_commits == [False]
    target_keys = {(row["projection_name"], row["target_kind"], row["target_id"]) for row in dirty_repo.enqueued}
    assert ("brief_input", "company_event", event_id) in target_keys
    for projection_name in ("story", "page", "timeline", "alert"):
        assert (projection_name, "company_event", event_id) in target_keys
        assert (projection_name, "company_event", "old-event-1") in target_keys
    assert ("calendar", "expected_event", "expected-1") in target_keys


def test_brief_write_enqueues_page_timeline_alert_targets() -> None:
    event_id = "event-brief-1"
    equity_repo = _FakeBriefEquityRepository()
    dirty_repo = _FakeDirtyTargetRepository()
    worker = EquityEventBriefWorker(
        name="equity_event_brief",
        settings=SimpleNamespace(statement_timeout_seconds=None),
        db=_FakeDb(equity_repo=equity_repo, dirty_repo=dirty_repo),
        telemetry=SimpleNamespace(),
        provider=SimpleNamespace(provider="fake", model="fake", artifact_version_hash="artifact"),
    )
    packet = _brief_packet(event_id)
    agent_config = SimpleNamespace(
        artifact_version_hash="artifact",
        prompt_version="prompt",
        schema_version="schema",
        validator_version="validator",
    )

    worker._upsert_current(
        run_id="run-1",
        packet=packet,
        agent_config=agent_config,
        payload={"status": "ready", "summary": "brief"},
        validation_status="accepted",
        computed_at_ms=NOW_MS,
    )

    assert equity_repo.conn.commits == 1
    assert dirty_repo.enqueue_commits == [False]
    assert {(row["projection_name"], row["target_kind"], row["target_id"]) for row in dirty_repo.enqueued} == {
        ("page", "company_event", event_id),
        ("timeline", "company_event", event_id),
        ("alert", "company_event", event_id),
    }


def test_source_reconcile_enqueues_calendar_due_at_status_boundary_and_universe_targets(monkeypatch) -> None:
    first_expected_at_ms = NOW_MS + 5_000
    second_expected_at_ms = NOW_MS + 15_000
    equity_repo = _FakeReconcileEquityRepository(
        expected_rows=[
            {
                "expected_event_id": "expected-1",
                "company_id": "company-1",
                "expected_at_ms": first_expected_at_ms,
                "updated_at_ms": NOW_MS,
            },
            {
                "expected_event_id": "expected-2",
                "company_id": "company-1",
                "expected_at_ms": second_expected_at_ms,
                "updated_at_ms": NOW_MS,
            },
        ],
        affected_company_event_ids=["event-1"],
        affected_expected_event_ids=["expected-1", "expected-2"],
    )
    dirty_repo = _FakeDirtyTargetRepository()
    monkeypatch.setattr(
        reconcile_module,
        "build_source_reconcile_payloads",
        lambda **_kwargs: SimpleNamespace(
            sources=[],
            universe_members=[{"company_id": "company-1", "ticker": "MSFT"}],
            expected_events=[
                {
                    "expected_event_id": "expected-1",
                    "company_id": "company-1",
                    "ticker": "MSFT",
                    "event_type": "quarterly_report",
                    "expected_at_ms": first_expected_at_ms,
                    "source_id": "calendar-source",
                    "source_role": "calendar",
                },
                {
                    "expected_event_id": "expected-2",
                    "company_id": "company-1",
                    "ticker": "MSFT",
                    "event_type": "quarterly_report",
                    "expected_at_ms": second_expected_at_ms,
                    "source_id": "calendar-source",
                    "source_role": "calendar",
                },
            ],
            expected_event_source_ids=["calendar-source"],
        ),
    )
    worker = EquityEventSourceReconcileWorker(
        name="equity_event_source_reconcile",
        settings=SimpleNamespace(statement_timeout_seconds=None),
        db=_FakeDb(equity_repo=equity_repo, dirty_repo=dirty_repo),
        telemetry=SimpleNamespace(),
        equity_settings=SimpleNamespace(),
        wake_bus=None,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.notes["expected_events"] == 2
    assert equity_repo.conn.commits == 1
    assert not any(call["reason"] == "expected_event_status_boundary" for call in dirty_repo.enqueue_calls)
    target_keys = {(row["projection_name"], row["target_kind"], row["target_id"]) for row in dirty_repo.enqueued}
    assert ("calendar", "expected_event", "expected-1") in target_keys
    assert ("calendar", "expected_event", "expected-2") in target_keys
    for projection_name in ("page", "timeline", "alert"):
        assert (projection_name, "company_event", "event-1") in target_keys


def test_source_reconcile_duplicate_payload_preserves_existing_future_calendar_boundary(monkeypatch) -> None:
    expected_event_id = "expected-future"
    future_due_at_ms = NOW_MS + 10_000
    equity_repo = _FakeReconcileEquityRepository(
        expected_rows=[
            {
                "expected_event_id": expected_event_id,
                "company_id": "company-1",
                "expected_at_ms": future_due_at_ms - 1,
                "updated_at_ms": NOW_MS - 1_000,
                "reconcile_status": "duplicate",
            }
        ],
        affected_company_event_ids=[],
        affected_expected_event_ids=[],
    )
    dirty_repo = _FakeDirtyTargetRepository(
        claimed=[
            {
                "projection_name": "calendar",
                "target_kind": "expected_event",
                "target_id": expected_event_id,
                "payload_hash": "future-boundary",
                "lease_owner": "",
                "attempt_count": 0,
                "due_at_ms": future_due_at_ms,
            }
        ]
    )
    monkeypatch.setattr(
        reconcile_module,
        "build_source_reconcile_payloads",
        lambda **_kwargs: SimpleNamespace(
            sources=[],
            universe_members=[{"company_id": "company-1", "ticker": "MSFT"}],
            expected_events=[
                {
                    "expected_event_id": expected_event_id,
                    "company_id": "company-1",
                    "ticker": "MSFT",
                    "event_type": "quarterly_report",
                    "expected_at_ms": future_due_at_ms - 1,
                    "source_id": "calendar-source",
                    "source_role": "calendar",
                }
            ],
            expected_event_source_ids=["calendar-source"],
        ),
    )
    worker = EquityEventSourceReconcileWorker(
        name="equity_event_source_reconcile",
        settings=SimpleNamespace(statement_timeout_seconds=None),
        db=_FakeDb(equity_repo=equity_repo, dirty_repo=dirty_repo),
        telemetry=SimpleNamespace(),
        equity_settings=SimpleNamespace(),
        wake_bus=None,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.notes["expected_events"] == 0
    assert dirty_repo.enqueue_calls == []
    assert dirty_repo.pending_keys() == [("calendar", "expected_event", expected_event_id)]
    assert dirty_repo.pending[0]["due_at_ms"] == future_due_at_ms


def test_source_reconcile_expected_material_change_enqueues_calendar_due_now(monkeypatch) -> None:
    expected_event_id = "expected-updated"
    equity_repo = _FakeReconcileEquityRepository(
        expected_rows=[
            {
                "expected_event_id": expected_event_id,
                "company_id": "company-1",
                "expected_at_ms": NOW_MS + 5_000,
                "updated_at_ms": NOW_MS,
                "reconcile_status": "updated",
            }
        ],
        affected_company_event_ids=[],
        affected_expected_event_ids=[],
    )
    dirty_repo = _FakeDirtyTargetRepository()
    monkeypatch.setattr(
        reconcile_module,
        "build_source_reconcile_payloads",
        lambda **_kwargs: SimpleNamespace(
            sources=[],
            universe_members=[],
            expected_events=[
                {
                    "expected_event_id": expected_event_id,
                    "company_id": "company-1",
                    "ticker": "MSFT",
                    "event_type": "quarterly_report",
                    "expected_at_ms": NOW_MS + 5_000,
                    "source_id": "calendar-source",
                    "source_role": "calendar",
                }
            ],
            expected_event_source_ids=["calendar-source"],
        ),
    )
    worker = EquityEventSourceReconcileWorker(
        name="equity_event_source_reconcile",
        settings=SimpleNamespace(statement_timeout_seconds=None),
        db=_FakeDb(equity_repo=equity_repo, dirty_repo=dirty_repo),
        telemetry=SimpleNamespace(),
        equity_settings=SimpleNamespace(),
        wake_bus=None,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.notes["expected_events"] == 1
    assert dirty_repo.enqueue_calls[0]["reason"] == "expected_event_reconciled"
    assert dirty_repo.enqueue_calls[0]["due_at_ms"] is None
    assert dirty_repo.pending == [
        {
            "projection_name": "calendar",
            "target_kind": "expected_event",
            "target_id": expected_event_id,
            "source_watermark_ms": NOW_MS,
            "due_at_ms": NOW_MS,
        }
    ]


def test_source_reconcile_universe_metadata_dirty_only_when_materially_changed(monkeypatch) -> None:
    changed_repo = _FakeReconcileEquityRepository(
        expected_rows=[],
        affected_company_event_ids=["event-1"],
        affected_expected_event_ids=["expected-1"],
        changed_company_ids=["company-1"],
    )
    unchanged_repo = _FakeReconcileEquityRepository(
        expected_rows=[],
        affected_company_event_ids=["event-1"],
        affected_expected_event_ids=["expected-1"],
        changed_company_ids=[],
    )
    monkeypatch.setattr(
        reconcile_module,
        "build_source_reconcile_payloads",
        lambda **_kwargs: SimpleNamespace(
            sources=[],
            universe_members=[{"company_id": "company-1", "ticker": "MSFT"}],
            expected_events=[],
            expected_event_source_ids=[],
        ),
    )

    dirty_changed = _FakeDirtyTargetRepository()
    changed_worker = EquityEventSourceReconcileWorker(
        name="equity_event_source_reconcile",
        settings=SimpleNamespace(statement_timeout_seconds=None),
        db=_FakeDb(equity_repo=changed_repo, dirty_repo=dirty_changed),
        telemetry=SimpleNamespace(),
        equity_settings=SimpleNamespace(),
        wake_bus=None,
    )
    dirty_unchanged = _FakeDirtyTargetRepository()
    unchanged_worker = EquityEventSourceReconcileWorker(
        name="equity_event_source_reconcile",
        settings=SimpleNamespace(statement_timeout_seconds=None),
        db=_FakeDb(equity_repo=unchanged_repo, dirty_repo=dirty_unchanged),
        telemetry=SimpleNamespace(),
        equity_settings=SimpleNamespace(),
        wake_bus=None,
    )

    changed_worker.run_once_sync(now_ms=NOW_MS)
    unchanged_worker.run_once_sync(now_ms=NOW_MS)

    changed_keys = {(row["projection_name"], row["target_kind"], row["target_id"]) for row in dirty_changed.enqueued}
    assert ("calendar", "expected_event", "expected-1") in changed_keys
    assert ("page", "company_event", "event-1") in changed_keys
    assert dirty_unchanged.enqueue_calls == []


def test_explicit_repository_loaders_filter_by_any_before_stale_discovery_predicates() -> None:
    conn = _ScriptedConnection([[], []])
    repo = EquityEventRepository(conn)

    repo.load_event_page_projection_payloads(company_event_ids=["event-1"])
    repo.load_expected_calendar_projection_payloads(expected_event_ids=["expected-1"], now_ms=NOW_MS)

    event_sql = conn.sql[0]
    calendar_sql = conn.sql[1]
    assert "WITH target_events AS" in event_sql
    assert "FROM target_events AS events" in event_sql
    assert event_sql.index("company_event_id = ANY(%s::text[])") < event_sql.index("LEFT JOIN LATERAL")
    assert "WITH target_expected AS" in calendar_sql
    assert "FROM target_expected AS expected" in calendar_sql
    assert calendar_sql.index("expected_event_id = ANY(%s::text[])") < calendar_sql.index("LEFT JOIN LATERAL")
    assert "page_rows.row_id IS NULL" not in event_sql
    assert "calendar_rows.row_id IS NULL" not in calendar_sql


def test_matching_expected_event_ids_includes_rejected_company_events_for_dirtying() -> None:
    conn = _ScriptedConnection([[{"expected_event_id": "expected-1"}]])
    repo = EquityEventRepository(conn)

    assert repo.matching_expected_event_ids_for_company_events(company_event_ids=["old-rejected-event"]) == [
        "expected-1"
    ]
    sql = conn.sql[0]
    assert "events.company_event_id = ANY(%s::text[])" in sql
    assert "events.validation_status <> 'rejected'" not in sql


def _projection_worker(
    *,
    equity_repo: _FakeProjectionEquityRepository,
    dirty_repo: _FakeDirtyTargetRepository,
    batch_size: int = 10,
) -> EquityEventPageProjectionWorker:
    return EquityEventPageProjectionWorker(
        name="equity_event_page_projection",
        settings=SimpleNamespace(
            batch_size=batch_size,
            statement_timeout_seconds=None,
            lease_ms=60_000,
            retry_ms=30_000,
        ),
        db=_FakeDb(equity_repo=equity_repo, dirty_repo=dirty_repo),
        telemetry=SimpleNamespace(),
    )


def _claim(projection_name: str, target_kind: str, target_id: str) -> dict[str, Any]:
    return {
        "projection_name": projection_name,
        "target_kind": target_kind,
        "target_id": target_id,
        "payload_hash": f"hash:{projection_name}:{target_id}",
        "lease_owner": "worker-a",
        "attempt_count": 1,
    }


def _event_projection_payload(*, company_event_id: str, source_watermark_ms: int) -> dict[str, Any]:
    return {
        "event": {
            "company_event_id": company_event_id,
            "company_id": "company-1",
            "ticker": "MSFT",
            "event_type": "quarterly_report",
            "priority": "P0",
            "source_role": "official_issuer",
            "fiscal_period": "2026Q1",
            "event_time_ms": NOW_MS - 1_000,
            "lifecycle_status": "processed",
            "validation_status": "accepted",
            "summary": "MSFT report",
            "updated_at_ms": source_watermark_ms,
        },
        "company": {"company_id": "company-1", "ticker": "MSFT", "company_name": "Microsoft", "priority": "P0"},
        "facts": [
            {
                "fact_candidate_id": "fact-1",
                "validation_status": "accepted",
                "claim": "Revenue was up",
                "source_role": "official_issuer",
            }
        ],
        "documents": [],
        "story": None,
        "brief": None,
    }


def _calendar_projection_payload(*, expected_event_id: str, expected_at_ms: int = NOW_MS - 1_000) -> dict[str, Any]:
    return {
        "expected_event": {
            "expected_event_id": expected_event_id,
            "company_id": "company-1",
            "ticker": "MSFT",
            "event_type": "quarterly_report",
            "priority": "P0",
            "source_role": "calendar",
            "fiscal_period": "2026Q1",
            "expected_at_ms": expected_at_ms,
            "status": "expected",
            "source_id": "calendar-source",
            "updated_at_ms": NOW_MS - 500,
        },
        "observed_event": None,
        "company": {"company_id": "company-1", "ticker": "MSFT", "company_name": "Microsoft", "priority": "P0"},
    }


class _FakeProjectionEquityRepository:
    def __init__(
        self,
        *,
        event_payloads: list[dict[str, Any]] | None = None,
        calendar_payloads: list[dict[str, Any]] | None = None,
        load_error: Exception | None = None,
        fail_replacements: set[str] | None = None,
    ) -> None:
        self.event_payloads = event_payloads or []
        self.calendar_payloads = calendar_payloads or []
        self.load_error = load_error
        self.fail_replacements = fail_replacements or set()
        self.conn = _FakeConn()
        self.loaded_company_event_ids: list[list[str]] = []
        self.loaded_expected_event_ids: list[list[str]] = []
        self.loaded_calendar_now_ms: list[int] = []
        self.replaced_page_scopes: list[list[str]] = []
        self.replaced_timeline_scopes: list[list[str]] = []
        self.replaced_alert_scopes: list[list[str]] = []
        self.replaced_calendar_scopes: list[list[str]] = []
        self.page_rows: list[dict[str, Any]] = []
        self.timeline_rows: list[dict[str, Any]] = []
        self.alert_rows: list[dict[str, Any]] = []
        self.calendar_rows: list[dict[str, Any]] = []

    def load_event_page_projection_payloads(self, *, company_event_ids: list[str]) -> list[dict[str, Any]]:
        self.loaded_company_event_ids.append(list(company_event_ids))
        if self.load_error is not None:
            raise self.load_error
        wanted = set(company_event_ids)
        return [row for row in self.event_payloads if row["event"]["company_event_id"] in wanted]

    def load_expected_calendar_projection_payloads(
        self, *, expected_event_ids: list[str], now_ms: int
    ) -> list[dict[str, Any]]:
        self.loaded_expected_event_ids.append(list(expected_event_ids))
        self.loaded_calendar_now_ms.append(int(now_ms))
        if self.load_error is not None:
            raise self.load_error
        wanted = set(expected_event_ids)
        return [row for row in self.calendar_payloads if row["expected_event"]["expected_event_id"] in wanted]

    def replace_page_rows(
        self, *, company_event_ids: list[str], rows: list[dict[str, Any]], commit: bool = True
    ) -> None:
        if "page" in self.fail_replacements:
            raise RuntimeError("page replacement failed")
        self.conn.record_write(lambda: self.replaced_page_scopes.append(list(company_event_ids)))
        self.conn.record_write(lambda: setattr(self, "page_rows", list(rows)))

    def replace_company_timeline_rows(
        self, *, rows: list[dict[str, Any]], company_event_ids: list[str], commit: bool = True
    ) -> None:
        if "timeline" in self.fail_replacements:
            raise RuntimeError("timeline replacement failed")
        self.conn.record_write(lambda: self.replaced_timeline_scopes.append(list(company_event_ids)))
        self.conn.record_write(lambda: setattr(self, "timeline_rows", list(rows)))

    def replace_alert_candidates(
        self, *, company_event_ids: list[str], rows: list[dict[str, Any]], commit: bool = True
    ) -> None:
        if "alert" in self.fail_replacements:
            raise RuntimeError("alert replacement failed")
        self.conn.record_write(lambda: self.replaced_alert_scopes.append(list(company_event_ids)))
        self.conn.record_write(lambda: setattr(self, "alert_rows", list(rows)))

    def replace_calendar_rows(
        self, *, expected_event_ids: list[str], rows: list[dict[str, Any]], commit: bool = True
    ) -> None:
        if "calendar" in self.fail_replacements:
            raise RuntimeError("calendar replacement failed")
        self.conn.record_write(lambda: self.replaced_calendar_scopes.append(list(expected_event_ids)))
        self.conn.record_write(lambda: setattr(self, "calendar_rows", list(rows)))


class _FakeDirtyTargetRepository:
    def __init__(self, *, claimed: list[dict[str, Any]] | None = None) -> None:
        self.claimed = claimed or []
        self.pending = [dict(row) for row in self.claimed]
        self.claimed_projection_names: list[str] = []
        self.done: list[dict[str, Any]] = []
        self.errors: list[list[dict[str, Any]]] = []
        self.error_messages: list[str] = []
        self.enqueued: list[dict[str, Any]] = []
        self.enqueue_calls: list[dict[str, Any]] = []
        self.enqueue_commits: list[bool] = []

    def claim_due(
        self,
        *,
        limit: int,
        lease_ms: int,
        now_ms: int,
        lease_owner: str,
        projection_name: str | None = None,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        self.claimed_projection_names.append(str(projection_name))
        rows = [
            row
            for row in self.pending
            if row["projection_name"] == projection_name and int(row.get("due_at_ms") or 0) <= int(now_ms)
        ][:limit]
        return [dict(row) for row in rows]

    def mark_done(self, keys: list[dict[str, Any]], *, now_ms: int, commit: bool = True) -> int:
        def apply() -> None:
            self.done.extend(dict(key) for key in keys)
            done_keys = {_target_key(key) for key in keys}
            self.pending = [row for row in self.pending if _target_key(row) not in done_keys]

        self.conn.record_write(apply)
        return len(keys)

    def mark_error(
        self,
        keys: list[dict[str, Any]],
        *,
        error: str,
        retry_ms: int,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        def apply() -> None:
            self.errors.append([dict(key) for key in keys])
            self.error_messages.append(error)

        self.conn.record_write(apply)
        return len(keys)

    def enqueue_targets(
        self,
        rows: list[dict[str, Any]],
        *,
        reason: str,
        now_ms: int,
        due_at_ms: int | None = None,
        commit: bool = True,
    ) -> int:
        self.enqueue_calls.append(
            {"rows": [dict(row) for row in rows], "reason": reason, "now_ms": now_ms, "due_at_ms": due_at_ms}
        )
        self.enqueue_commits.append(commit)

        def apply() -> None:
            for row in rows:
                record = dict(row)
                record["due_at_ms"] = int(due_at_ms if due_at_ms is not None else now_ms)
                self.enqueued.append(record)
                key = _target_key(record)
                self.pending = [item for item in self.pending if _target_key(item) != key]
                self.pending.append(record)

        self.conn.record_write(apply)
        return len(rows)

    def pending_keys(self) -> list[tuple[str, str, str]]:
        return [_target_key(row) for row in self.pending]


class _FakeConn:
    def __init__(self) -> None:
        self.commits = 0
        self.transaction_events: list[str] = []
        self._frames: list[list[Any]] = []

    def commit(self) -> None:
        self.commits += 1

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self)

    def record_write(self, apply: Any) -> None:
        if self._frames:
            self._frames[-1].append(apply)
            return
        apply()


class _FakeTransaction:
    def __init__(self, conn: _FakeConn) -> None:
        self.conn = conn
        self.depth = 0

    def __enter__(self) -> _FakeTransaction:
        self.depth = len(self.conn._frames)
        self.conn._frames.append([])
        self.conn.transaction_events.append("begin" if self.depth == 0 else "savepoint")
        return self

    def __exit__(self, exc_type: Any, _exc: Any, _tb: Any) -> bool:
        frame = self.conn._frames.pop()
        if exc_type is not None:
            self.conn.transaction_events.append("rollback" if self.depth == 0 else "rollback_savepoint")
            return False
        if self.conn._frames:
            self.conn._frames[-1].extend(frame)
            self.conn.transaction_events.append("release_savepoint")
        else:
            for apply in frame:
                apply()
            self.conn.transaction_events.append("commit")
        return False


class _FakeSession:
    def __init__(self, *, equity_repo: Any, dirty_repo: _FakeDirtyTargetRepository) -> None:
        self.equity_events = equity_repo
        self.equity_projection_dirty_targets = dirty_repo
        self.conn = equity_repo.conn if hasattr(equity_repo, "conn") else _FakeConn()
        if not hasattr(equity_repo, "conn"):
            equity_repo.conn = self.conn
        dirty_repo.conn = self.conn
        self.registry = SimpleNamespace(find_us_equity_symbol=lambda *_args, **_kwargs: None)

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def unit_of_work(self) -> _FakeTransaction:
        return self.conn.transaction()


class _FakeDb:
    def __init__(self, *, equity_repo: Any, dirty_repo: _FakeDirtyTargetRepository) -> None:
        self.equity_repo = equity_repo
        self.dirty_repo = dirty_repo

    def worker_session(self, *_args: Any, **_kwargs: Any) -> _FakeSession:
        return _FakeSession(equity_repo=self.equity_repo, dirty_repo=self.dirty_repo)


class _FakeProcessEquityRepository:
    def __init__(
        self,
        *,
        document: dict[str, Any],
        old_event_ids: list[str],
        matching_expected_event_ids: list[str],
    ) -> None:
        self.document = document
        self.old_event_ids = old_event_ids
        self.matching_expected_event_ids = matching_expected_event_ids
        self.conn = _FakeConn()

    def expire_stale_process_jobs(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    def claim_due_process_jobs(self, *, lease_owner: str, **_kwargs: Any) -> list[dict[str, Any]]:
        return [
            {
                "event_document_id": self.document["event_document_id"],
                "lease_owner": lease_owner,
                "attempt_count": 1,
                "input_payload_hash": "process-input-hash",
            }
        ]

    def load_process_packets_for_claims(self, *, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not claims:
            return []
        document = self.list_event_documents_for_processing(limit=1)[0]
        document.update(
            {
                "lease_owner": claims[0]["lease_owner"],
                "attempt_count": claims[0]["attempt_count"],
                "input_payload_hash": claims[0]["input_payload_hash"],
            }
        )
        return [document]

    def list_event_documents_for_processing(self, *, limit: int) -> list[dict[str, Any]]:
        document = dict(self.document)
        document.setdefault("evidence_status", "ready")
        document.setdefault("evidence_reason", "")
        document.setdefault(
            "evidence_artifacts",
            [{"extraction_status": "ready", "content_text": "Revenue was up."}],
        )
        return [document]

    def company_event_ids_for_document(self, *, event_document_id: str) -> list[str]:
        return list(self.old_event_ids)

    def clear_story_members_for_document(self, **_kwargs: Any) -> int:
        return 0

    def upsert_company_event(self, **kwargs: Any) -> dict[str, Any]:
        return {"company_event_id": kwargs["company_event_id"], "updated_at_ms": kwargs["now_ms"]}

    def replace_source_spans(self, **_kwargs: Any) -> None:
        return None

    def replace_fact_candidates(self, **_kwargs: Any) -> None:
        return None

    def mark_event_document_evidence_status(self, **_kwargs: Any) -> None:
        return None

    def mark_event_document_fact_extraction_status(self, **_kwargs: Any) -> None:
        return None

    def mark_event_document_processed(self, **_kwargs: Any) -> None:
        return None

    def mark_event_document_process_failed(self, **_kwargs: Any) -> None:
        return None

    def finish_process_job_success(self, **_kwargs: Any) -> bool:
        return True

    def finish_process_job_failure(self, **_kwargs: Any) -> bool:
        return True

    def matching_expected_event_ids_for_company_events(self, *, company_event_ids: list[str]) -> list[str]:
        return list(self.matching_expected_event_ids)


class _FakeBriefEquityRepository:
    def __init__(self) -> None:
        self.conn = _FakeConn()

    def upsert_equity_event_agent_brief(self, **_kwargs: Any) -> None:
        return None


class _FakeReconcileEquityRepository:
    def __init__(
        self,
        *,
        expected_rows: list[dict[str, Any]],
        affected_company_event_ids: list[str],
        affected_expected_event_ids: list[str],
        changed_company_ids: list[str] | None = None,
    ) -> None:
        self.expected_rows = expected_rows
        self.affected_company_event_ids = affected_company_event_ids
        self.affected_expected_event_ids = affected_expected_event_ids
        self.changed_company_ids = changed_company_ids
        self.conn = _FakeConn()

    def reconcile_sources(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    def reconcile_source_catalog(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "sources": [],
            "changed_company_ids": (
                list(self.changed_company_ids)
                if self.changed_company_ids is not None
                else _dedupe_ids(self.affected_company_event_ids)
            ),
        }

    def expected_event_ids_for_sources(self, *, source_ids: list[str]) -> list[str]:
        return []

    def reconcile_expected_events(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return list(self.expected_rows)

    def company_event_ids_for_companies(self, *, company_ids: list[str]) -> list[str]:
        if not company_ids:
            return []
        return list(self.affected_company_event_ids)

    def expected_event_ids_for_companies(self, *, company_ids: list[str]) -> list[str]:
        if not company_ids:
            return []
        return list(self.affected_expected_event_ids)


class _ScriptedConnection:
    def __init__(self, results: list[list[dict[str, Any]]]) -> None:
        self.results = list(results)
        self.sql: list[str] = []

    def execute(self, sql: str, *_args: Any) -> _ScriptedCursor:
        self.sql.append(sql)
        rows = self.results.pop(0) if self.results else []
        return _ScriptedCursor(rows)


class _ScriptedCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


def _brief_packet(company_event_id: str) -> Any:
    return SimpleNamespace(
        input_hash="input-hash",
        current_event=SimpleNamespace(company_event_id=company_event_id),
    )


def _target_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row["projection_name"]), str(row["target_kind"]), str(row["target_id"]))


def _dedupe_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
