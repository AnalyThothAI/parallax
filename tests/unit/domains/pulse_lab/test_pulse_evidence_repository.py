from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.pulse_lab.repositories.pulse_evidence_repository import PulseEvidenceRepository
from parallax.domains.pulse_lab.types import (
    IdentityEvidence,
    MarketEvidence,
    PulseEvidencePacket,
    PulseEvidenceQualityMetrics,
    SocialEvidence,
)

NOW_MS = 1_779_000_000_000
_ROWCOUNT_MISSING = object()


class PulseEvidenceReturningCursor:
    def __init__(self, rows: list[dict[str, Any]], *, rowcount: object = _ROWCOUNT_MISSING) -> None:
        self._rows = rows
        if rowcount is not _ROWCOUNT_MISSING:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class PulseEvidenceReturningConnection:
    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        rowcount: object = _ROWCOUNT_MISSING,
        run_link_rowcount: object = 1,
    ) -> None:
        self.rows = rows
        self.rowcount = rowcount
        self.run_link_rowcount = run_link_rowcount
        self.sql: list[str] = []

    def execute(self, sql: str, params: Any = None) -> PulseEvidenceReturningCursor:
        del params
        self.sql.append(sql)
        if "RETURNING evidence_packet_id" in sql:
            return PulseEvidenceReturningCursor(self.rows, rowcount=self.rowcount)
        if "UPDATE pulse_agent_runs" in sql:
            return PulseEvidenceReturningCursor([], rowcount=self.run_link_rowcount)
        raise AssertionError(f"unexpected SQL: {sql}")


def _packet_row() -> dict[str, Any]:
    return {"evidence_packet_id": "packet-1"}


def test_pulse_evidence_packet_returning_write_requires_cursor_rowcount() -> None:
    conn = PulseEvidenceReturningConnection(rows=[_packet_row()])

    with pytest.raises(TypeError, match="pulse_evidence_repository_rowcount_required"):
        PulseEvidenceRepository(conn).upsert_packet(_evidence_packet(), commit=False)

    assert len(conn.sql) == 1


@pytest.mark.parametrize(
    ("rowcount", "rows", "expected_error"),
    [
        pytest.param(True, [_packet_row()], "invalid", id="bool-true"),
        pytest.param(False, [], "invalid", id="bool-false"),
        pytest.param("1", [_packet_row()], "invalid", id="numeric-string"),
        pytest.param(-1, [], "invalid", id="negative"),
        pytest.param(0, [], "invalid", id="zero-without-row"),
        pytest.param(0, [_packet_row()], "invalid", id="zero-with-row"),
        pytest.param(1, [], "invalid", id="one-without-row"),
        pytest.param(2, [_packet_row()], "invalid", id="multi-row"),
    ],
)
def test_pulse_evidence_packet_returning_write_rejects_invalid_or_mismatched_rowcount(
    rowcount: object,
    rows: list[dict[str, Any]],
    expected_error: str,
) -> None:
    conn = PulseEvidenceReturningConnection(rows=rows, rowcount=rowcount)

    with pytest.raises(TypeError, match=f"pulse_evidence_repository_rowcount_{expected_error}"):
        PulseEvidenceRepository(conn).upsert_packet(_evidence_packet(), commit=False)

    assert len(conn.sql) == 1


def test_pulse_evidence_packet_returning_write_accepts_valid_single_rowcount() -> None:
    conn = PulseEvidenceReturningConnection(rows=[_packet_row()], rowcount=1)

    PulseEvidenceRepository(conn).upsert_packet(_evidence_packet(), commit=False)

    assert len(conn.sql) == 2
    assert "UPDATE pulse_agent_runs" in conn.sql[1]


def test_pulse_evidence_run_link_update_requires_cursor_rowcount() -> None:
    conn = PulseEvidenceReturningConnection(
        rows=[_packet_row()],
        rowcount=1,
        run_link_rowcount=_ROWCOUNT_MISSING,
    )

    with pytest.raises(TypeError, match="pulse_evidence_repository_rowcount_required"):
        PulseEvidenceRepository(conn).upsert_packet(_evidence_packet(), commit=False)

    assert len(conn.sql) == 2
    assert "UPDATE pulse_agent_runs" in conn.sql[1]


@pytest.mark.parametrize(
    "rowcount",
    [
        pytest.param(True, id="bool-true"),
        pytest.param(False, id="bool-false"),
        pytest.param("1", id="numeric-string"),
        pytest.param(-1, id="negative"),
        pytest.param(0, id="zero"),
        pytest.param(2, id="multi-row"),
    ],
)
def test_pulse_evidence_run_link_update_requires_single_rowcount(rowcount: object) -> None:
    conn = PulseEvidenceReturningConnection(
        rows=[_packet_row()],
        rowcount=1,
        run_link_rowcount=rowcount,
    )

    with pytest.raises(TypeError, match="pulse_evidence_repository_rowcount_invalid"):
        PulseEvidenceRepository(conn).upsert_packet(_evidence_packet(), commit=False)

    assert len(conn.sql) == 2
    assert "UPDATE pulse_agent_runs" in conn.sql[1]


def _evidence_packet() -> PulseEvidencePacket:
    return PulseEvidencePacket(
        evidence_packet_id="packet-1",
        run_id="run-1",
        evidence_packet_hash="sha256:packet",
        schema_version="schema-v1",
        candidate_id="candidate-1",
        target_type="asset",
        target_id="asset-1",
        symbol="ABC",
        window="1h",
        scope="default",
        snapshot_at_ms=NOW_MS,
        source_event_ids=("event-1",),
        allowed_evidence_refs=(),
        social_evidence=SocialEvidence(status="complete"),
        market_evidence=MarketEvidence(status="complete", route="dex", target_market_type="spot"),
        identity_evidence=IdentityEvidence(status="complete"),
        quality_metrics=PulseEvidenceQualityMetrics(
            ref_count=0,
            high_quality_ref_count=0,
            fresh_ref_count=0,
        ),
    )
