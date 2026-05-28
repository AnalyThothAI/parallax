from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel.repositories import equity_event_repository as repo_module
from gmgn_twitter_intel.domains.equity_event_intel.repositories.equity_event_repository import (
    EquityEventRepository,
)

NOW_MS = 1_700_000_000_000


def test_process_input_payload_hash_uses_only_stable_document_and_artifact_fields() -> None:
    hash_input = _process_input_payload_hash(
        document=_document() | {"updated_at_ms": NOW_MS + 99, "raw_payload_json": {"body": "ignore me"}},
        artifacts=[
            _artifact("artifact-2", artifact_kind="xbrl", artifact_payload_hash="payload-2"),
            _artifact("artifact-1", artifact_payload_hash="payload-1", fetched_at_ms=NOW_MS + 10),
        ],
    )

    reordered_with_lifecycle_churn = _process_input_payload_hash(
        document=_document() | {"processed_at_ms": NOW_MS + 123, "raw_payload_json": {"body": "changed"}},
        artifacts=[
            _artifact("artifact-1", artifact_payload_hash="payload-1", fetched_at_ms=NOW_MS + 20),
            _artifact("artifact-2", artifact_kind="xbrl", artifact_payload_hash="payload-2"),
        ],
    )
    changed_artifact = _process_input_payload_hash(
        document=_document(),
        artifacts=[
            _artifact("artifact-1", artifact_payload_hash="payload-1-changed"),
            _artifact("artifact-2", artifact_kind="xbrl", artifact_payload_hash="payload-2"),
        ],
    )

    assert reordered_with_lifecycle_churn == hash_input
    assert changed_artifact != hash_input


def test_enqueue_process_job_loads_document_artifacts_and_upserts_pending_hash() -> None:
    document = _document()
    artifacts = [_artifact("artifact-1"), _artifact("artifact-2", artifact_kind="xbrl")]
    input_hash = _process_input_payload_hash(document=document, artifacts=artifacts)
    conn = _ScriptedConnection(
        [
            [document],
            artifacts,
            [
                {
                    "event_document_id": "event-doc-1",
                    "status": "pending",
                    "due_at_ms": NOW_MS + 5_000,
                    "attempt_count": 0,
                    "input_payload_hash": input_hash,
                }
            ],
        ]
    )

    row = EquityEventRepository(conn).enqueue_process_job_for_document(
        event_document_id="event-doc-1",
        due_at_ms=NOW_MS + 5_000,
        now_ms=NOW_MS,
        commit=False,
    )

    assert row["input_payload_hash"] == input_hash
    assert "FROM equity_event_documents AS documents" in conn.sql[0]
    assert "raw_payload_json" not in conn.sql[0]
    assert "FROM equity_event_evidence_artifacts AS artifacts" in conn.sql[1]
    assert "artifact_payload_hash" in conn.sql[1]
    upsert_sql = conn.sql[2]
    assert "INSERT INTO equity_event_process_jobs" in upsert_sql
    assert "ON CONFLICT (event_document_id) DO UPDATE SET" in upsert_sql
    assert "input_payload_hash IS DISTINCT FROM EXCLUDED.input_payload_hash" in upsert_sql
    assert "status IN ('pending', 'failed_retryable')" in upsert_sql
    assert "lease_owner = CASE" in upsert_sql
    assert conn.params[2]["event_document_id"] == "event-doc-1"
    assert conn.params[2]["input_payload_hash"] == input_hash
    assert conn.commits == 0


def test_enqueue_process_job_changed_hash_preserves_running_claim_sql_contract() -> None:
    document = _document()
    artifacts = [_artifact("artifact-1", artifact_payload_hash="changed-payload")]
    conn = _ScriptedConnection(
        [
            [document],
            artifacts,
            [
                {
                    "event_document_id": "event-doc-1",
                    "status": "running",
                    "lease_owner": "process-a",
                    "leased_until_ms": NOW_MS + 60_000,
                    "attempt_count": 1,
                    "input_payload_hash": "old-running-hash",
                }
            ],
        ]
    )

    row = EquityEventRepository(conn).enqueue_process_job_for_document(
        event_document_id="event-doc-1",
        due_at_ms=NOW_MS + 5_000,
        now_ms=NOW_MS,
        commit=False,
    )

    upsert_sql = conn.sql[2]
    assert row["status"] == "running"
    for column in (
        "status",
        "attempt_count",
        "input_payload_hash",
        "started_at_ms",
        "lease_owner",
        "leased_until_ms",
    ):
        assert _running_preserve_branch(column) in upsert_sql


def test_claim_due_process_jobs_moves_due_rows_to_running_with_attempt_token() -> None:
    conn = _ScriptedConnection(
        [
            [
                {
                    "event_document_id": "event-doc-1",
                    "status": "running",
                    "lease_owner": "process-a",
                    "leased_until_ms": NOW_MS + 60_000,
                    "attempt_count": 1,
                    "input_payload_hash": "hash-1",
                }
            ]
        ]
    )

    rows = EquityEventRepository(conn).claim_due_process_jobs(
        now_ms=NOW_MS,
        limit=10,
        lease_owner="process-a",
        lease_ms=60_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert rows[0]["status"] == "running"
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "status IN ('pending', 'failed_retryable')" in sql
    assert "attempt_count = jobs.attempt_count + 1" in sql
    assert "leased_until_ms = %(leased_until_ms)s" in sql
    assert conn.params[-1]["leased_until_ms"] == NOW_MS + 60_000
    assert conn.params[-1]["lease_owner"] == "process-a"
    assert conn.params[-1]["limit"] == 10


def test_load_process_packets_for_claims_matches_current_lease_and_omits_raw_payload() -> None:
    conn = _ScriptedConnection(
        [
            [
                {
                    "event_document_id": "event-doc-1",
                    "lease_owner": "process-a",
                    "attempt_count": 1,
                    "input_payload_hash": "hash-1",
                    "provider_title": "MSFT 10-Q",
                    "provider_summary": "Quarterly results",
                    "primary_document_url": "https://example.test/msft-10q.htm",
                    "evidence_artifacts": [{"id": "artifact-1", "artifact_payload_hash": "artifact-hash"}],
                }
            ]
        ]
    )

    packets = EquityEventRepository(conn).load_process_packets_for_claims(
        claims=[
            {
                "event_document_id": "event-doc-1",
                "lease_owner": "process-a",
                "attempt_count": 1,
                "input_payload_hash": "hash-1",
            }
        ]
    )

    sql = conn.sql[-1]
    assert packets[0]["event_document_id"] == "event-doc-1"
    assert "jsonb_to_recordset" in sql
    assert "JOIN equity_event_process_jobs AS jobs" in sql
    assert "jobs.status = 'running'" in sql
    assert "jobs.lease_owner = claims.lease_owner" in sql
    assert "jobs.attempt_count = claims.attempt_count" in sql
    assert "jobs.input_payload_hash = claims.input_payload_hash" in sql
    assert "provider.raw_payload_json" not in sql
    assert "raw_payload_json" not in sql
    assert "documents.provider_title" in sql
    assert "documents.provider_summary" in sql
    assert "documents.primary_document_url" in sql
    assert "artifacts.artifact_payload_hash" in sql


def test_finish_process_job_success_requires_matching_lease_attempt_and_hash() -> None:
    conn = _ScriptedConnection([[], [{"event_document_id": "event-doc-1"}]])
    repo = EquityEventRepository(conn)

    stale = repo.finish_process_job_success(
        event_document_id="event-doc-1",
        lease_owner="process-a",
        attempt_count=1,
        input_payload_hash="stale-hash",
        now_ms=NOW_MS,
        commit=False,
    )
    fresh = repo.finish_process_job_success(
        event_document_id="event-doc-1",
        lease_owner="process-a",
        attempt_count=1,
        input_payload_hash="fresh-hash",
        now_ms=NOW_MS,
        commit=False,
    )

    sql = conn.sql[-1]
    assert stale is False
    assert fresh is True
    assert "SET status = 'done'" in sql
    assert "AND status = 'running'" in sql
    assert "AND lease_owner = %(lease_owner)s" in sql
    assert "AND attempt_count = %(attempt_count)s" in sql
    assert "AND input_payload_hash = %(input_payload_hash)s" in sql
    assert conn.params[0]["input_payload_hash"] == "stale-hash"
    assert conn.params[1]["input_payload_hash"] == "fresh-hash"


def test_finish_process_job_failure_guards_hash_and_terminalizes_exhausted_attempts() -> None:
    conn = _ScriptedConnection([[{"event_document_id": "event-doc-1"}]])

    updated = EquityEventRepository(conn).finish_process_job_failure(
        event_document_id="event-doc-1",
        lease_owner="process-a",
        attempt_count=3,
        input_payload_hash="hash-1",
        error="provider failed",
        now_ms=NOW_MS,
        retry_ms=30_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert updated is True
    assert "WHEN attempt_count >= max_attempts THEN 'failed_terminal'" in sql
    assert "ELSE 'failed_retryable'" in sql
    assert "terminal_reason = CASE" in sql
    assert "AND input_payload_hash = %(input_payload_hash)s" in sql
    assert conn.params[-1]["due_at_ms"] == NOW_MS + 30_000
    assert conn.params[-1]["last_error"] == "provider failed"


def test_expire_stale_process_jobs_reschedules_retryable_and_terminalizes_exhausted_jobs() -> None:
    conn = _ScriptedConnection(
        [
            [
                {
                    "event_document_id": "retryable-doc",
                    "status": "failed_retryable",
                    "lease_owner": None,
                    "leased_until_ms": None,
                    "due_at_ms": NOW_MS,
                },
                {
                    "event_document_id": "terminal-doc",
                    "status": "failed_terminal",
                    "lease_owner": None,
                    "leased_until_ms": None,
                    "terminal_reason": "process_job_lease_expired",
                },
            ]
        ]
    )

    rows = EquityEventRepository(conn).expire_stale_process_jobs(now_ms=NOW_MS, limit=25, commit=False)

    sql = conn.sql[-1]
    assert [row["event_document_id"] for row in rows] == ["retryable-doc", "terminal-doc"]
    assert "status = 'running'" in sql
    assert "leased_until_ms <= %(now_ms)s" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "WHEN jobs.attempt_count >= jobs.max_attempts THEN 'failed_terminal'" in sql
    assert "ELSE 'failed_retryable'" in sql
    assert "lease_owner = NULL" in sql
    assert "leased_until_ms = NULL" in sql
    assert "terminal_reason = CASE" in sql
    assert conn.params[-1]["now_ms"] == NOW_MS
    assert conn.params[-1]["limit"] == 25


def _process_input_payload_hash(*, document: dict[str, Any], artifacts: list[dict[str, Any]]) -> str:
    return repo_module._process_input_payload_hash(document=document, artifacts=artifacts)


def _running_preserve_branch(column: str) -> str:
    return (
        "WHEN equity_event_process_jobs.status = 'running'\n"
        f"                  THEN equity_event_process_jobs.{column}"
    )


def _document() -> dict[str, Any]:
    return {
        "event_document_id": "event-doc-1",
        "provider_document_id": "provider-doc-1",
        "company_id": "company-msft",
        "ticker": "MSFT",
        "cik": "0000789019",
        "source_id": "sec:MSFT",
        "source_role": "official_regulator",
        "document_type": "sec_filing",
        "form_type": "10-Q",
        "accession_number": "0000789019-26-000001",
        "fiscal_period": "2026Q1",
        "document_url": "https://example.test/msft-10q.htm",
        "event_time_ms": NOW_MS - 10_000,
        "discovered_at_ms": NOW_MS - 9_000,
        "content_hash": "document-content-hash",
        "evidence_status": "ready",
        "evidence_reason": "",
        "created_at_ms": NOW_MS - 8_000,
        "updated_at_ms": NOW_MS - 7_000,
    }


def _artifact(
    evidence_artifact_id: str,
    *,
    artifact_kind: str = "html_text",
    artifact_payload_hash: str = "artifact-payload-hash",
    fetched_at_ms: int = NOW_MS,
) -> dict[str, Any]:
    return {
        "evidence_artifact_id": evidence_artifact_id,
        "event_document_id": "event-doc-1",
        "artifact_kind": artifact_kind,
        "extraction_status": "ready",
        "content_hash": f"content-{evidence_artifact_id}",
        "artifact_payload_hash": artifact_payload_hash,
        "content_text": f"text {evidence_artifact_id}",
        "fetched_at_ms": fetched_at_ms,
        "updated_at_ms": fetched_at_ms + 1,
    }


class _ScriptedConnection:
    def __init__(self, results: list[list[dict[str, Any]]]) -> None:
        self.results = list(results)
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.commits = 0

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        if not self.results:
            return []
        return self.results.pop(0)

    def fetchone(self) -> dict[str, Any] | None:
        rows = self.fetchall()
        return rows[0] if rows else None

    def commit(self) -> None:
        self.commits += 1
