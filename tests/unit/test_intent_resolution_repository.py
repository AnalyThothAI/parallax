from __future__ import annotations

from parallax.domains.token_intel.interfaces import TOKEN_RADAR_RESOLVER_POLICY_VERSION
from parallax.domains.token_intel.repositories.intent_resolution_repository import IntentResolutionRepository
from parallax.domains.token_intel.services.deterministic_token_resolver import DeterministicResolution


def test_insert_resolution_serializes_current_row_by_intent_before_superseding() -> None:
    conn = RecordingConn()
    repo = IntentResolutionRepository(conn)

    repo.insert_resolution(
        DeterministicResolution(
            intent_id="intent-1",
            event_id="event-1",
            resolution_status="UNIQUE_BY_CONTEXT",
            target_type="Asset",
            target_id="asset:eip155:1:erc20:0x44b28991b167582f18ba0259e0173176ca125505",
            pricefeed_id=None,
            resolver_policy_version=TOKEN_RADAR_RESOLVER_POLICY_VERSION,
            reason_codes=["MARKET_DOMINANT_CHAIN_ASSET"],
            candidate_ids=["asset:eip155:1:erc20:0x44b28991b167582f18ba0259e0173176ca125505"],
            lookup_keys=["symbol:UPEG"],
            decision_time_ms=2_000,
            created_at_ms=2_000,
        ),
        commit=False,
    )

    assert "pg_advisory_xact_lock(hashtextextended(%s, 0))" in conn.statements[0][0]
    assert conn.statements[0][1] == ("intent-1",)
    assert "FOR UPDATE" in conn.statements[1][0]
    assert "UPDATE token_intent_resolutions" in conn.statements[2][0]


class RecordingConn:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[object, ...] | None]] = []

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> RecordingResult:
        self.statements.append((sql, params))
        if "SELECT *" in sql and "FOR UPDATE" in sql:
            return RecordingResult(
                {
                    "resolution_id": "old-resolution",
                    "intent_id": "intent-1",
                    "decision_time_ms": 1_000,
                },
                rowcount=1,
            )
        if "UPDATE token_intent_resolutions" in sql:
            return RecordingResult(rowcount=1)
        if "INSERT INTO token_intent_resolutions" in sql:
            return RecordingResult(
                {
                    "resolution_id": "new-resolution",
                    "intent_id": "intent-1",
                    "decision_time_ms": 2_000,
                },
                rowcount=1,
            )
        return RecordingResult(rowcount=0)

    def commit(self) -> None:
        raise AssertionError("commit should not be called when commit=False")


class RecordingResult:
    def __init__(self, row: dict[str, object] | None = None, *, rowcount: int) -> None:
        self._row = row
        self.rowcount = rowcount

    def fetchone(self) -> dict[str, object] | None:
        return self._row
