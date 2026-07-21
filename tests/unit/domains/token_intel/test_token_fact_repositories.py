from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from psycopg import pq

from parallax.domains.token_intel.repositories.intent_resolution_repository import IntentResolutionRepository
from parallax.domains.token_intel.repositories.token_evidence_repository import TokenEvidenceRepository
from parallax.domains.token_intel.repositories.token_intent_lookup_repository import TokenIntentLookupRepository
from parallax.domains.token_intel.repositories.token_intent_repository import TokenIntentRepository
from parallax.domains.token_intel.services.deterministic_token_resolver import DeterministicResolution
from parallax.domains.token_intel.services.token_evidence_builder import TokenEvidenceInput
from parallax.domains.token_intel.services.token_intent_builder import TokenIntentEvidenceLink, TokenIntentInput

NOW_MS = 1_779_000_000_000
MISSING_ROWCOUNT = object()


def test_token_fact_mutations_require_explicit_transaction_before_sql() -> None:
    cases = _repository_cases(NoTransactionTokenFactConnection())
    for case in cases:
        conn = NoTransactionTokenFactConnection()
        with pytest.raises(RuntimeError, match="requires_explicit_transaction"):
            case.write(conn)
        assert conn.sql == []


def test_token_fact_writes_run_inside_caller_owned_transaction() -> None:
    cases = _repository_cases(FakeTokenFactConnection())
    for case in cases:
        conn = FakeTokenFactConnection(active_transaction=False)
        with conn.transaction():
            case.write(conn)
        assert conn.transaction_entries == 1
        assert conn.transaction_exits == ["ok"]
        assert conn.manual_commits == 0
        assert conn.sql, case.name


def _repository_cases(conn: Any) -> list[RepositoryCase]:
    return [
        RepositoryCase(
            name="token_evidence",
            error="token_evidence_repository_transaction_required",
            write=lambda active_conn: TokenEvidenceRepository(active_conn).insert_many([_evidence_payload()]),
        ),
        RepositoryCase(
            name="token_intents",
            error="token_intent_repository_transaction_required",
            write=lambda active_conn: TokenIntentRepository(active_conn).insert_many([_intent_payload()]),
        ),
        RepositoryCase(
            name="token_intent_lookup",
            error="token_intent_lookup_repository_transaction_required",
            write=lambda active_conn: TokenIntentLookupRepository(active_conn).replace_lookup_keys(
                intent_id="intent-1",
                event_id="event-1",
                keys=["symbol:AAA", "address:solana:asset-1"],
                source_evidence_id="evidence-1",
                created_at_ms=1_778_162_002_774,
            ),
        ),
        RepositoryCase(
            name="intent_resolutions",
            error="intent_resolution_repository_transaction_required",
            write=lambda active_conn: IntentResolutionRepository(active_conn).insert_resolution(_resolution_payload()),
        ),
    ]


@pytest.mark.parametrize(
    ("operation", "error_code"),
    (
        pytest.param(
            lambda conn: TokenEvidenceRepository(conn).insert(_evidence_payload()),
            "token_evidence_repository_rowcount_invalid",
            id="token_evidence_insert",
        ),
        pytest.param(
            lambda conn: TokenEvidenceRepository(conn).delete_by_event_id("event-1"),
            "token_evidence_repository_rowcount_invalid",
            id="token_evidence_delete",
        ),
        pytest.param(
            lambda conn: TokenIntentRepository(conn).insert(_intent_payload()),
            "token_intent_repository_rowcount_invalid",
            id="token_intent_insert",
        ),
        pytest.param(
            lambda conn: TokenIntentRepository(conn).delete_by_event_id("event-1"),
            "token_intent_repository_rowcount_invalid",
            id="token_intent_delete",
        ),
        pytest.param(
            lambda conn: TokenIntentLookupRepository(conn).replace_lookup_keys(
                intent_id="intent-1",
                event_id="event-1",
                keys=["symbol:AAA"],
                source_evidence_id="evidence-1",
                created_at_ms=1_778_162_002_774,
            ),
            "token_intent_lookup_repository_rowcount_invalid",
            id="token_intent_lookup_replace",
        ),
        pytest.param(
            lambda conn: IntentResolutionRepository(conn).insert_resolution(_resolution_payload()),
            "intent_resolution_repository_rowcount_invalid",
            id="intent_resolution_insert",
        ),
    ),
)
def test_token_fact_writes_require_cursor_rowcount(
    operation: Callable[[Any], Any],
    error_code: str,
) -> None:
    conn = FakeTokenFactConnection(rowcounts=[MISSING_ROWCOUNT])

    with pytest.raises(TypeError, match=error_code):
        operation(conn)


@pytest.mark.parametrize("bad_rowcount", ("bad", True, -1))
@pytest.mark.parametrize(
    ("operation", "error_code"),
    (
        pytest.param(
            lambda conn: TokenEvidenceRepository(conn).insert(_evidence_payload()),
            "token_evidence_repository_rowcount_invalid",
            id="token_evidence_insert",
        ),
        pytest.param(
            lambda conn: TokenEvidenceRepository(conn).delete_by_event_id("event-1"),
            "token_evidence_repository_rowcount_invalid",
            id="token_evidence_delete",
        ),
        pytest.param(
            lambda conn: TokenIntentRepository(conn).insert(_intent_payload()),
            "token_intent_repository_rowcount_invalid",
            id="token_intent_insert",
        ),
        pytest.param(
            lambda conn: TokenIntentRepository(conn).delete_by_event_id("event-1"),
            "token_intent_repository_rowcount_invalid",
            id="token_intent_delete",
        ),
        pytest.param(
            lambda conn: TokenIntentLookupRepository(conn).replace_lookup_keys(
                intent_id="intent-1",
                event_id="event-1",
                keys=["symbol:AAA"],
                source_evidence_id="evidence-1",
                created_at_ms=1_778_162_002_774,
            ),
            "token_intent_lookup_repository_rowcount_invalid",
            id="token_intent_lookup_replace",
        ),
        pytest.param(
            lambda conn: IntentResolutionRepository(conn).insert_resolution(_resolution_payload()),
            "intent_resolution_repository_rowcount_invalid",
            id="intent_resolution_insert",
        ),
    ),
)
def test_token_fact_writes_reject_invalid_cursor_rowcount(
    operation: Callable[[Any], Any],
    error_code: str,
    bad_rowcount: object,
) -> None:
    conn = FakeTokenFactConnection(rowcounts=[bad_rowcount])

    with pytest.raises(TypeError, match=error_code):
        operation(conn)


@pytest.mark.parametrize("bad_rowcount", (0, 2))
@pytest.mark.parametrize(
    ("operation", "error_code", "rowcounts"),
    (
        pytest.param(
            lambda conn: TokenEvidenceRepository(conn).insert(_evidence_payload()),
            "token_evidence_repository_rowcount_invalid",
            None,
            id="token_evidence_insert",
        ),
        pytest.param(
            lambda conn: TokenIntentRepository(conn).insert(_intent_payload()),
            "token_intent_repository_rowcount_invalid",
            None,
            id="token_intent_insert",
        ),
        pytest.param(
            lambda conn: TokenIntentLookupRepository(conn).replace_lookup_keys(
                intent_id="intent-1",
                event_id="event-1",
                keys=["symbol:AAA"],
                source_evidence_id="evidence-1",
                created_at_ms=1_778_162_002_774,
            ),
            "token_intent_lookup_repository_rowcount_invalid",
            [0],
            id="token_intent_lookup_replace_insert",
        ),
        pytest.param(
            lambda conn: IntentResolutionRepository(conn).insert_resolution(_resolution_payload()),
            "intent_resolution_repository_rowcount_invalid",
            None,
            id="intent_resolution_insert",
        ),
    ),
)
def test_token_fact_single_row_writes_require_one_affected_row(
    operation: Callable[[Any], Any],
    error_code: str,
    rowcounts: list[object] | None,
    bad_rowcount: int,
) -> None:
    conn = FakeTokenFactConnection(rowcounts=[*(rowcounts or []), bad_rowcount])

    with pytest.raises(TypeError, match=error_code):
        operation(conn)


def test_token_evidence_insert_accepts_formal_input_contract() -> None:
    conn = FakeTokenFactConnection(rowcounts=[1])

    row = TokenEvidenceRepository(conn).insert(_formal_evidence())

    assert row["evidence_id"] == "evidence-1"


def test_token_evidence_insert_rejects_loose_slots_object_before_sql() -> None:
    conn = FakeTokenFactConnection(rowcounts=[1])

    with pytest.raises(TypeError, match="token_evidence_repository_input_contract_required"):
        TokenEvidenceRepository(conn).insert(_loose_evidence())

    assert conn.sql == []


def test_intent_resolution_insert_accepts_formal_decision_contract() -> None:
    conn = FakeTokenFactConnection(rowcounts=[1])

    row = IntentResolutionRepository(conn).insert_resolution(_formal_resolution())

    assert row["resolution_id"] == "resolution-1"


def test_intent_resolution_insert_rejects_loose_slots_object_before_sql() -> None:
    conn = FakeTokenFactConnection(rowcounts=[1])

    with pytest.raises(TypeError, match="intent_resolution_repository_input_contract_required"):
        IntentResolutionRepository(conn).insert_resolution(_loose_resolution())

    assert conn.sql == []


def test_token_intent_evidence_links_allow_do_nothing_zero_rowcount() -> None:
    conn = FakeTokenFactConnection(rowcounts=[1, 0])

    row = TokenIntentRepository(conn).insert(_formal_intent_with_evidence_links())

    assert row["intent_id"] == "intent-1"


def test_token_intent_insert_rejects_loose_slots_object_before_sql() -> None:
    conn = FakeTokenFactConnection(rowcounts=[1, 0])

    with pytest.raises(TypeError, match="token_intent_repository_input_contract_required"):
        TokenIntentRepository(conn).insert(_intent_with_evidence_links())

    assert conn.sql == []


def test_token_evidence_for_intents_batches_keyset_and_groups_evidence() -> None:
    conn = EvidenceBatchReadConnection(
        rows=[
            {
                "intent_id": "intent-1",
                "evidence_id": "evidence-1",
                "event_id": "event-1",
                "raw_value": "$ONE",
            },
            {
                "intent_id": "intent-1",
                "evidence_id": "evidence-2",
                "event_id": "event-1",
                "raw_value": "ONE",
            },
        ]
    )

    result = TokenEvidenceRepository(conn).evidence_for_intents(["intent-1", "intent-2", "intent-1"])

    assert result == {
        "intent-1": [
            {"evidence_id": "evidence-1", "event_id": "event-1", "raw_value": "$ONE"},
            {"evidence_id": "evidence-2", "event_id": "event-1", "raw_value": "ONE"},
        ],
        "intent-2": [],
    }
    assert len(conn.calls) == 1
    assert conn.calls[0]["params"] == (["intent-1", "intent-2"],)
    assert "WITH input_intents AS" in conn.calls[0]["sql"]
    assert "WITH ORDINALITY" in conn.calls[0]["sql"]
    assert "JOIN token_intent_evidence" in conn.calls[0]["sql"]
    assert "ORDER BY distinct_intents.ordinality ASC" in conn.calls[0]["sql"]


@pytest.mark.parametrize(
    ("bad_rowcount", "error_code"),
    (
        pytest.param(MISSING_ROWCOUNT, "token_intent_repository_rowcount_invalid", id="missing"),
        pytest.param(2, "token_intent_repository_rowcount_invalid", id="multirow"),
    ),
)
def test_token_intent_evidence_links_require_optional_single_rowcount(
    bad_rowcount: object,
    error_code: str,
) -> None:
    conn = FakeTokenFactConnection(rowcounts=[1, bad_rowcount])

    with pytest.raises(TypeError, match=error_code):
        TokenIntentRepository(conn).insert(_formal_intent_with_evidence_links())


@pytest.mark.parametrize(
    ("bad_rowcount", "error_code"),
    (
        pytest.param(MISSING_ROWCOUNT, "intent_resolution_repository_rowcount_invalid", id="missing"),
        pytest.param(0, "intent_resolution_repository_rowcount_invalid", id="zero"),
        pytest.param(2, "intent_resolution_repository_rowcount_invalid", id="multirow"),
    ),
)
def test_intent_resolution_supersede_requires_single_row_update_count(
    bad_rowcount: object,
    error_code: str,
) -> None:
    conn = FakeTokenFactConnection(
        rowcounts=[bad_rowcount],
        active_resolution_row={"resolution_id": "old-resolution", "decision_time_ms": 0},
    )

    with pytest.raises(TypeError, match=error_code):
        IntentResolutionRepository(conn).insert_resolution(_resolution_payload())


def test_token_intent_recent_unresolved_zero_limit_returns_empty_without_sql() -> None:
    conn = FakeTokenFactConnection()

    rows = TokenIntentRepository(conn).recent_unresolved(since_ms=NOW_MS - 1_000, limit=0)

    assert rows == []
    assert conn.sql == []


@pytest.mark.parametrize("limit", [-1, True, "10"])
def test_token_intent_recent_unresolved_rejects_malformed_limit_before_sql(limit: object) -> None:
    conn = FakeTokenFactConnection()

    with pytest.raises(ValueError, match="token_intent_recent_unresolved_limit_required"):
        TokenIntentRepository(conn).recent_unresolved(since_ms=NOW_MS - 1_000, limit=limit)  # type: ignore[arg-type]

    assert conn.sql == []


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda repo, limit: repo.recent_intents_for_lookup_keys(
                ["symbol:BTC"],
                since_ms=NOW_MS - 1_000,
                limit=limit,
            ),
            id="all",
        ),
        pytest.param(
            lambda repo, limit: repo.recent_unresolved_intents_for_lookup_keys(
                ["symbol:BTC"],
                since_ms=NOW_MS - 1_000,
                limit=limit,
            ),
            id="unresolved",
        ),
    ],
)
@pytest.mark.parametrize("limit", [0, -1, True, "10"])
def test_token_intent_lookup_reads_reject_malformed_limit_before_sql(
    operation: Callable[[TokenIntentLookupRepository, object], object],
    limit: object,
) -> None:
    conn = FakeTokenFactConnection()

    with pytest.raises(ValueError, match="token_intent_lookup_limit_required"):
        operation(TokenIntentLookupRepository(conn), limit)

    assert conn.sql == []


class RepositoryCase:
    def __init__(self, *, name: str, error: str, write: Callable[[Any], Any]) -> None:
        self.name = name
        self.error = error
        self.write = write


class FakeTokenFactConnection:
    def __init__(
        self,
        *,
        rowcounts: list[object] | None = None,
        active_resolution_row: dict[str, Any] | None = None,
        active_transaction: bool = True,
    ) -> None:
        self.sql: list[str] = []
        self.transaction_entries = 0
        self.transaction_exits: list[str] = []
        self.manual_commits = 0
        self.rowcounts = list(rowcounts or [])
        self.active_resolution_row = active_resolution_row
        self.info = SimpleNamespace(
            transaction_status=(pq.TransactionStatus.INTRANS if active_transaction else pq.TransactionStatus.IDLE)
        )

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    def execute(self, sql: str, params: Any = None) -> FakeResult:
        self.sql.append(sql)
        normalized = " ".join(sql.split())
        if normalized.startswith("INSERT INTO token_evidence"):
            return FakeResult({"evidence_id": str(params["evidence_id"])}, rowcount=self._next_rowcount())
        if normalized.startswith("DELETE FROM token_evidence"):
            return FakeResult(None, rowcount=self._next_rowcount())
        if normalized.startswith("INSERT INTO token_intents("):
            return FakeResult({"intent_id": str(params["intent_id"])}, rowcount=self._next_rowcount())
        if normalized.startswith("INSERT INTO token_intent_evidence"):
            return FakeResult(None, rowcount=self._next_rowcount())
        if normalized.startswith("DELETE FROM token_intents"):
            return FakeResult(None, rowcount=self._next_rowcount())
        if normalized.startswith("DELETE FROM token_intent_lookup_keys"):
            return FakeResult(None, rowcount=self._next_rowcount())
        if normalized.startswith("INSERT INTO token_intent_lookup_keys"):
            return FakeResult(None, rowcount=self._next_rowcount())
        if normalized.startswith("UPDATE token_intent_resolutions"):
            return FakeResult(None, rowcount=self._next_rowcount())
        if normalized.startswith("INSERT INTO token_intent_resolutions"):
            return FakeResult({"resolution_id": "resolution-1"}, rowcount=self._next_rowcount())
        if "FROM token_intent_resolutions" in normalized and "WHERE intent_id = %s AND is_current = true" in normalized:
            return FakeResult(self.active_resolution_row)
        if "SELECT * FROM token_evidence WHERE evidence_id" in sql:
            return FakeResult({"evidence_id": str(params[0])})
        if "SELECT * FROM token_intents WHERE intent_id" in sql:
            return FakeResult({"intent_id": str(params[0])})
        if "WHERE resolution_id = %s" in sql:
            return FakeResult({"resolution_id": str(params[0])})
        return FakeResult(None)

    def commit(self) -> None:
        self.manual_commits += 1
        raise AssertionError("manual commit should not be called")

    def _next_rowcount(self) -> object:
        if self.rowcounts:
            return self.rowcounts.pop(0)
        return 1


class NoTransactionTokenFactConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.info = SimpleNamespace(transaction_status=pq.TransactionStatus.IDLE)

    def execute(self, sql: str, params: Any = None) -> FakeResult:
        self.sql.append(sql)
        return FakeResult(None)

    def commit(self) -> None:
        raise AssertionError("manual commit should not be called")


class EvidenceBatchReadConnection:
    def __init__(self, *, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> EvidenceBatchReadResult:
        self.calls.append({"sql": sql, "params": params})
        return EvidenceBatchReadResult(self.rows)


class EvidenceBatchReadResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class FakeTransaction:
    def __init__(self, conn: FakeTokenFactConnection) -> None:
        self.conn = conn

    def __enter__(self) -> None:
        self.conn.transaction_entries += 1
        self.conn.info.transaction_status = pq.TransactionStatus.INTRANS

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any) -> bool:
        self.conn.transaction_exits.append(exc_type.__name__ if exc_type else "ok")
        self.conn.info.transaction_status = pq.TransactionStatus.IDLE
        return False


class FakeResult:
    def __init__(self, row: dict[str, Any] | None, *, rowcount: object = MISSING_ROWCOUNT) -> None:
        self.row = row
        if rowcount is not MISSING_ROWCOUNT:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


def _evidence_payload() -> dict[str, Any]:
    return {
        "evidence_id": "evidence-1",
        "event_id": "event-1",
        "source_kind": "twitter",
        "source_id": "event-1",
        "evidence_type": "symbol",
        "raw_value": "$AAA",
        "normalized_symbol": "AAA",
        "chain_hint": None,
        "address_hint": None,
        "provider": None,
        "provider_ref": None,
        "text_surface": "primary",
        "span_start": 0,
        "span_end": 4,
        "sentence_id": None,
        "local_group_key": None,
        "strength": 1.0,
        "confidence": 0.9,
        "created_at_ms": 1_778_162_002_774,
    }


class LooseEvidence:
    __slots__ = tuple(_evidence_payload().keys())

    def __init__(self) -> None:
        for key, value in _evidence_payload().items():
            setattr(self, key, value)


def _loose_evidence() -> LooseEvidence:
    return LooseEvidence()


def _formal_evidence() -> TokenEvidenceInput:
    payload = _evidence_payload()
    return TokenEvidenceInput(
        evidence_id=str(payload["evidence_id"]),
        event_id=str(payload["event_id"]),
        source_kind=str(payload["source_kind"]),
        source_id=str(payload["source_id"]),
        evidence_type=str(payload["evidence_type"]),
        raw_value=str(payload["raw_value"]),
        normalized_symbol=str(payload["normalized_symbol"]) if payload["normalized_symbol"] is not None else None,
        chain_hint=str(payload["chain_hint"]) if payload["chain_hint"] is not None else None,
        address_hint=str(payload["address_hint"]) if payload["address_hint"] is not None else None,
        provider=str(payload["provider"]) if payload["provider"] is not None else None,
        provider_ref=str(payload["provider_ref"]) if payload["provider_ref"] is not None else None,
        text_surface=str(payload["text_surface"]),
        span_start=int(payload["span_start"]),
        span_end=int(payload["span_end"]),
        sentence_id=int(payload["sentence_id"]) if payload["sentence_id"] is not None else 0,
        local_group_key=str(payload["local_group_key"]) if payload["local_group_key"] is not None else "",
        strength=str(payload["strength"]),
        confidence=float(payload["confidence"]),
        created_at_ms=int(payload["created_at_ms"]),
    )


def _intent_payload() -> dict[str, Any]:
    return {
        "intent_id": "intent-1",
        "event_id": "event-1",
        "intent_key": "symbol:AAA",
        "construction_policy": "test",
        "primary_evidence_id": "evidence-1",
        "display_symbol": "AAA",
        "display_name": None,
        "chain_hint": None,
        "address_hint": None,
        "intent_status": "pending_resolution",
        "intent_confidence": 0.9,
        "created_at_ms": 1_778_162_002_774,
        "updated_at_ms": 1_778_162_002_774,
    }


class IntentWithEvidenceLinks:
    __slots__ = (
        "address_hint",
        "chain_hint",
        "construction_policy",
        "created_at_ms",
        "display_name",
        "display_symbol",
        "event_id",
        "evidence_links",
        "intent_confidence",
        "intent_id",
        "intent_key",
        "intent_status",
        "primary_evidence_id",
        "updated_at_ms",
    )

    def __init__(self) -> None:
        for key, value in _intent_payload().items():
            setattr(self, key, value)
        self.evidence_links = [SimpleNamespace(evidence_id="evidence-1", role="primary_identity")]


def _intent_with_evidence_links() -> IntentWithEvidenceLinks:
    return IntentWithEvidenceLinks()


def _formal_intent_with_evidence_links() -> TokenIntentInput:
    payload = _intent_payload()
    return TokenIntentInput(
        intent_id=str(payload["intent_id"]),
        event_id=str(payload["event_id"]),
        intent_key=str(payload["intent_key"]),
        construction_policy=str(payload["construction_policy"]),
        primary_evidence_id=str(payload["primary_evidence_id"]) if payload["primary_evidence_id"] is not None else None,
        display_symbol=str(payload["display_symbol"]) if payload["display_symbol"] is not None else None,
        display_name=str(payload["display_name"]) if payload["display_name"] is not None else None,
        chain_hint=str(payload["chain_hint"]) if payload["chain_hint"] is not None else None,
        address_hint=str(payload["address_hint"]) if payload["address_hint"] is not None else None,
        intent_status=str(payload["intent_status"]),
        intent_confidence=float(payload["intent_confidence"]),
        created_at_ms=int(payload["created_at_ms"]),
        updated_at_ms=int(payload["updated_at_ms"]),
        evidence_links=[TokenIntentEvidenceLink(evidence_id="evidence-1", role="primary_identity")],
    )


def _resolution_payload() -> dict[str, Any]:
    return {
        "intent_id": "intent-1",
        "event_id": "event-1",
        "resolution_status": "UNIQUE_BY_CONTEXT",
        "resolver_policy_version": "test-v1",
        "target_type": "Asset",
        "target_id": "asset-1",
        "pricefeed_id": None,
        "reason_codes": ["TEST"],
        "candidate_ids": ["asset-1"],
        "lookup_keys": ["symbol:AAA"],
        "decision_time_ms": 1_778_162_002_774,
        "created_at_ms": 1_778_162_002_774,
    }


class LooseResolution:
    __slots__ = tuple(_resolution_payload().keys())

    def __init__(self) -> None:
        for key, value in _resolution_payload().items():
            setattr(self, key, value)


def _loose_resolution() -> LooseResolution:
    return LooseResolution()


def _formal_resolution() -> DeterministicResolution:
    payload = _resolution_payload()
    return DeterministicResolution(
        intent_id=str(payload["intent_id"]),
        event_id=str(payload["event_id"]),
        resolution_status=str(payload["resolution_status"]),
        target_type=str(payload["target_type"]) if payload["target_type"] is not None else None,
        target_id=str(payload["target_id"]) if payload["target_id"] is not None else None,
        pricefeed_id=str(payload["pricefeed_id"]) if payload["pricefeed_id"] is not None else None,
        resolver_policy_version=str(payload["resolver_policy_version"]),
        reason_codes=[str(item) for item in payload["reason_codes"]],
        candidate_ids=[str(item) for item in payload["candidate_ids"]],
        lookup_keys=[str(item) for item in payload["lookup_keys"]],
        decision_time_ms=int(payload["decision_time_ms"]),
        created_at_ms=int(payload["created_at_ms"]),
    )
