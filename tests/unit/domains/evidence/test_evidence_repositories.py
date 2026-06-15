from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.domains.evidence.interfaces import EVM_QUERY_CHAINS
from parallax.domains.evidence.repositories.entity_repository import EntityRepository
from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository, event_to_row
from parallax.domains.evidence.types.entity import ExtractedEntity
from tests.factories import make_event

NOW_MS = 1_779_000_000_000
_ROWCOUNT_MISSING = object()


def test_evidence_fact_mutations_require_connection_transaction_before_sql_when_committing() -> None:
    cases = _repository_cases()
    for case in cases:
        conn = NoTransactionEvidenceConnection()

        with pytest.raises(RuntimeError, match=case.error):
            case.write(conn)

        assert conn.sql == []


def test_evidence_fact_commit_owned_writes_use_connection_transaction_without_manual_commit() -> None:
    cases = _repository_cases()
    for case in cases:
        conn = FakeEvidenceConnection()

        case.write(conn)

        assert conn.transaction_entries == 1, case.name
        assert conn.transaction_exits == ["ok"], case.name
        assert conn.manual_commits == 0, case.name
        assert conn.sql, case.name
        assert set(conn.sql_depths) == {1}, case.name


def test_recent_events_pushes_since_window_to_postgres() -> None:
    conn = ReadEvidenceConnection()

    rows = EvidenceRepository(conn).recent_events(limit=12, watched_only=True, since_ms=NOW_MS - 3_600_000)

    assert rows == []
    assert len(conn.executions) == 1
    sql, params = conn.executions[0]
    assert "e.is_watched = true" in sql
    assert "e.received_at_ms >= %s" in sql
    assert "ORDER BY e.received_at_ms DESC LIMIT %s" in sql
    assert params == (NOW_MS - 3_600_000, 12)


def test_recent_events_for_token_filters_uses_single_keyset_sql_with_bucket_budget() -> None:
    conn = ReadEvidenceConnection()

    rows = EvidenceRepository(conn).recent_events_for_token_filters(
        limit=10,
        per_filter_limit=3,
        cas={
            ("evm_unknown", "0x0000000000000000000000000000000000000abc"),
            ("solana", "So11111111111111111111111111111111111111112"),
        },
        symbols={"eth", "BTC"},
        watched_only=True,
        since_ms=NOW_MS - 3_600_000,
    )

    assert rows == []
    assert len(conn.executions) == 1
    sql, params = conn.executions[0]
    assert "WITH input_filters AS" in sql
    assert "unnest(%s::text[], %s::text[], %s::text[]) WITH ORDINALITY" in sql
    assert "distinct_filters AS" in sql
    assert "ROW_NUMBER() OVER ( PARTITION BY filters.filter_kind, filters.filter_chain, filters.filter_value" in sql
    assert "event_rank <= %s" in sql
    assert "ee.chain = ANY(%s::text[])" in sql
    assert "e.received_at_ms >= %s" in sql
    assert params[-4:] == (sorted(EVM_QUERY_CHAINS), NOW_MS - 3_600_000, 3, 10)


def _repository_cases() -> list[RepositoryCase]:
    event = make_event("event-evidence-transaction")
    return [
        RepositoryCase(
            name="raw_frame",
            error="evidence_repository_transaction_required",
            write=lambda conn: EvidenceRepository(conn).insert_raw_frame(
                source="gmgn",
                channel="twitter_monitor_basic",
                received_at_ms=event.received_at_ms,
                raw_payload_json='{"id":"frame-1"}',
            ),
        ),
        RepositoryCase(
            name="event_entities",
            error="entity_repository_transaction_required",
            write=lambda conn: EntityRepository(conn).insert_event_entities(
                event,
                [_entity()],
                is_watched=True,
            ),
        ),
    ]


def _rowcount_cases() -> list[RowcountCase]:
    event = make_event("event-evidence-rowcount")
    return [
        RowcountCase(
            name="raw_frame",
            required_error="evidence_repository_rowcount_required",
            invalid_error="evidence_repository_rowcount_invalid",
            write=lambda conn: EvidenceRepository(conn).insert_raw_frame(
                source="gmgn",
                channel="twitter_monitor_basic",
                received_at_ms=event.received_at_ms,
                raw_payload_json='{"id":"frame-rowcount"}',
                commit=False,
            ),
        ),
        RowcountCase(
            name="event",
            required_error="evidence_repository_rowcount_required",
            invalid_error="evidence_repository_rowcount_invalid",
            write=lambda conn: EvidenceRepository(conn).insert_event_without_commit(
                event_to_row(event, is_watched=True, now_ms=NOW_MS)
            ),
        ),
        RowcountCase(
            name="event_entities",
            required_error="entity_repository_rowcount_required",
            invalid_error="entity_repository_rowcount_invalid",
            write=lambda conn: EntityRepository(conn).insert_event_entities(
                event,
                [_entity()],
                is_watched=True,
                commit=False,
            ),
        ),
    ]


class RepositoryCase:
    def __init__(self, *, name: str, error: str, write: Callable[[Any], Any]) -> None:
        self.name = name
        self.error = error
        self.write = write


class RowcountCase:
    def __init__(
        self,
        *,
        name: str,
        required_error: str,
        invalid_error: str,
        write: Callable[[Any], Any],
    ) -> None:
        self.name = name
        self.required_error = required_error
        self.invalid_error = invalid_error
        self.write = write


@pytest.mark.parametrize("case", _rowcount_cases(), ids=lambda case: case.name)
def test_evidence_fact_write_counts_require_cursor_rowcount(case: RowcountCase) -> None:
    conn = RowcountEvidenceConnection(rowcount=_ROWCOUNT_MISSING)

    with pytest.raises(TypeError, match=case.required_error):
        case.write(conn)

    assert conn.sql, case.name


@pytest.mark.parametrize("rowcount", (True, False, "1", None, -1, 2))
@pytest.mark.parametrize("case", _rowcount_cases(), ids=lambda case: case.name)
def test_evidence_fact_write_counts_reject_invalid_cursor_rowcount(case: RowcountCase, rowcount: object) -> None:
    conn = RowcountEvidenceConnection(rowcount=rowcount)

    with pytest.raises(TypeError, match=case.invalid_error):
        case.write(conn)

    assert conn.sql, case.name


class FakeEvidenceConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.sql_depths: list[int] = []
        self.transaction_entries = 0
        self.transaction_depth = 0
        self.transaction_exits: list[str] = []
        self.manual_commits = 0

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    def execute(self, sql: str, params: Any = None) -> FakeResult:
        self.sql.append(" ".join(str(sql).split()))
        self.sql_depths.append(self.transaction_depth)
        return FakeResult(rowcount=1)

    def commit(self) -> None:
        self.manual_commits += 1
        raise AssertionError("repository-owned writes must use conn.transaction(), not conn.commit()")


class NoTransactionEvidenceConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def execute(self, sql: str, params: Any = None) -> FakeResult:
        self.sql.append(" ".join(str(sql).split()))
        return FakeResult(rowcount=1)

    def commit(self) -> None:
        raise AssertionError("repository-owned writes must use conn.transaction(), not conn.commit()")


class RowcountEvidenceConnection:
    def __init__(self, *, rowcount: object) -> None:
        self.rowcount = rowcount
        self.sql: list[str] = []

    def execute(self, sql: str, params: Any = None) -> RowcountResult:
        self.sql.append(" ".join(str(sql).split()))
        return RowcountResult(rowcount=self.rowcount)


class ReadEvidenceConnection:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: Any = None) -> ReadEvidenceCursor:
        self.executions.append((" ".join(str(sql).split()), tuple(params or ())))
        return ReadEvidenceCursor()


class ReadEvidenceCursor:
    def fetchall(self) -> list[dict[str, Any]]:
        return []


class FakeTransaction:
    def __init__(self, conn: FakeEvidenceConnection) -> None:
        self.conn = conn

    def __enter__(self) -> None:
        self.conn.transaction_entries += 1
        self.conn.transaction_depth += 1

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any) -> bool:
        self.conn.transaction_depth -= 1
        self.conn.transaction_exits.append(exc_type.__name__ if exc_type else "ok")
        return False


class FakeResult:
    def __init__(self, *, rowcount: int) -> None:
        self.rowcount = rowcount


class RowcountResult:
    def __init__(self, *, rowcount: object) -> None:
        if rowcount is not _ROWCOUNT_MISSING:
            self.rowcount = rowcount


def _entity() -> ExtractedEntity:
    return ExtractedEntity(
        entity_type="symbol",
        raw_value="$AAA",
        normalized_value="AAA",
        chain=None,
        token_resolution_status="symbol_pending_resolution",
        confidence=0.9,
        source="test",
    )
