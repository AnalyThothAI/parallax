from __future__ import annotations

from typing import Any

from parallax.domains.pulse_lab.repositories._pulse_repository_shared import (
    _json,
    _now_ms,
    _optional_row,
    _row,
    _run_repository_write,
)
from parallax.domains.pulse_lab.types import PulseEvidencePacket


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("pulse_evidence_repository_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int) or rowcount < 0:
        raise TypeError("pulse_evidence_repository_rowcount_invalid")
    return rowcount


def _required_returning_row(cursor: Any, row: Any) -> dict[str, Any]:
    if _cursor_rowcount(cursor) != 1 or row is None:
        raise TypeError("pulse_evidence_repository_rowcount_invalid")
    return _row(row)


def _required_single_rowcount(cursor: Any) -> int:
    rowcount = _cursor_rowcount(cursor)
    if rowcount != 1:
        raise TypeError("pulse_evidence_repository_rowcount_invalid")
    return rowcount


class PulseEvidenceRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_packet(self, packet: PulseEvidencePacket, *, commit: bool = True) -> None:
        def _upsert_packet() -> None:
            if not packet.run_id:
                raise ValueError("PulseEvidencePacket.run_id is required for persistence")
            cursor = self.conn.execute(
                """
                INSERT INTO pulse_evidence_packets(
                  evidence_packet_id, run_id, candidate_id, target_type, target_id,
                  "window", scope, schema_version, evidence_packet_hash, packet_json,
                  summary_json, source_fingerprints_json, created_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(evidence_packet_id) DO UPDATE SET
                  run_id = excluded.run_id,
                  candidate_id = excluded.candidate_id,
                  target_type = excluded.target_type,
                  target_id = excluded.target_id,
                  "window" = excluded."window",
                  scope = excluded.scope,
                  schema_version = excluded.schema_version,
                  evidence_packet_hash = excluded.evidence_packet_hash,
                  packet_json = excluded.packet_json,
                  summary_json = excluded.summary_json,
                  source_fingerprints_json = excluded.source_fingerprints_json,
                  created_at_ms = excluded.created_at_ms
                RETURNING evidence_packet_id
                """,
                (
                    packet.evidence_packet_id,
                    packet.run_id,
                    packet.candidate_id,
                    packet.target_type,
                    packet.target_id,
                    packet.window,
                    packet.scope,
                    packet.schema_version,
                    packet.evidence_packet_hash,
                    _json(packet.packet_json),
                    _json(packet.summary_json),
                    _json(packet.source_fingerprints_json),
                    int(packet.snapshot_at_ms or _now_ms()),
                ),
            )
            row = cursor.fetchone()
            _required_returning_row(cursor, row)
            run_link_cursor = self.conn.execute(
                """
                UPDATE pulse_agent_runs
                SET evidence_packet_id = %s,
                    evidence_packet_hash = %s
                WHERE run_id = %s
                """,
                (packet.evidence_packet_id, packet.evidence_packet_hash, packet.run_id),
            )
            _required_single_rowcount(run_link_cursor)

        _run_repository_write(self.conn, commit, _upsert_packet)

    def get_packet_by_hash(self, hash: str) -> PulseEvidencePacket | None:
        return self._packet_from_row(
            _optional_row(
                self.conn.execute(
                    """
                    SELECT packet_json, summary_json
                    FROM pulse_evidence_packets
                    WHERE evidence_packet_hash = %s
                    """,
                    (hash,),
                ).fetchone()
            )
        )

    def get_packet_for_run(self, run_id: str) -> PulseEvidencePacket | None:
        return self._packet_from_row(
            _optional_row(
                self.conn.execute(
                    """
                    SELECT packet_json, summary_json
                    FROM pulse_evidence_packets
                    WHERE run_id = %s
                    ORDER BY created_at_ms DESC, evidence_packet_id DESC
                    LIMIT 1
                    """,
                    (run_id,),
                ).fetchone()
            )
        )

    def latest_packet_for_candidate(self, candidate_id: str) -> PulseEvidencePacket | None:
        return self._packet_from_row(
            _optional_row(
                self.conn.execute(
                    """
                    SELECT packet_json, summary_json
                    FROM pulse_evidence_packets
                    WHERE candidate_id = %s
                    ORDER BY created_at_ms DESC, evidence_packet_id DESC
                    LIMIT 1
                    """,
                    (candidate_id,),
                ).fetchone()
            )
        )

    def _packet_from_row(self, row: dict[str, Any] | None) -> PulseEvidencePacket | None:
        if row is None:
            return None
        packet_json = row["packet_json"]
        if not isinstance(packet_json, dict):
            return None
        payload = {**packet_json, "summary_json": row.get("summary_json") or {}}
        return PulseEvidencePacket.model_validate(payload)
