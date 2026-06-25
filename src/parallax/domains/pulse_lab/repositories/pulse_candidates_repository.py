from __future__ import annotations

from typing import Any

from parallax.domains.pulse_lab.repositories._pulse_repository_shared import (
    _json,
    _normalize_subject,
    _normalize_symbol,
    _now_ms,
    _row,
    _run_repository_write,
)
from parallax.domains.pulse_lab.types.pulse_state import PUBLIC_DISPLAY_STATUSES


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("pulse_candidates_repository_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int) or rowcount < 0:
        raise TypeError("pulse_candidates_repository_rowcount_invalid")
    return rowcount


def _optional_returning_row(cursor: Any, row: Any) -> dict[str, Any] | None:
    count = _cursor_rowcount(cursor)
    if count > 1 or (count == 0 and row is not None) or (count == 1 and row is None):
        raise TypeError("pulse_candidates_repository_rowcount_invalid")
    return _row(row) if row is not None else None


def _required_nonnegative_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(error_code)
    return int(value)


class PulseCandidatesRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_candidate(
        self,
        *,
        candidate_id: str,
        candidate_type: str,
        subject_key: str,
        window: str,
        scope: str,
        pulse_status: str,
        verdict: str,
        social_phase: str,
        candidate_score: float,
        score_band: str,
        trigger_signature: str,
        timeline_signature: str,
        pulse_version: str,
        gate_version: str,
        prompt_version: str,
        schema_version: str,
        factor_snapshot_json: dict[str, Any],
        gate_json: dict[str, Any],
        decision_route: str,
        decision_recommendation: str,
        decision_confidence: float,
        decision_stage_count: int,
        decision_json: dict[str, Any],
        target_type: str | None = None,
        target_id: str | None = None,
        symbol: str | None = None,
        decision_abstain_reason: str | None = None,
        gate_reasons_json: list[Any] | None = None,
        risk_reasons_json: list[Any] | None = None,
        evidence_event_ids_json: list[Any] | None = None,
        source_event_ids_json: list[Any] | None = None,
        last_edge_events_json: list[Any] | None = None,
        evidence_packet_hash: str | None = None,
        evidence_status: str = "insufficient",
        decision_status: str = "invalid",
        display_status: str = "hidden_insufficient_evidence",
        claim_verification_json: dict[str, Any] | None = None,
        evidence_gate_json: dict[str, Any] | None = None,
        created_at_ms: int | None = None,
        updated_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        parsed_decision_stage_count = _required_nonnegative_int(
            decision_stage_count,
            "pulse_candidate_decision_stage_count_required",
        )

        def _upsert_candidate() -> dict[str, Any] | None:
            now = int(updated_at_ms if updated_at_ms is not None else _now_ms())
            created = int(created_at_ms if created_at_ms is not None else now)
            cursor = self.conn.execute(
                """
                INSERT INTO pulse_candidates(
                  candidate_id, candidate_type, subject_key, target_type, target_id, symbol,
                  "window", scope, pulse_status, verdict, social_phase,
                  candidate_score, score_band, trigger_signature, timeline_signature,
                  factor_snapshot_json, gate_json, decision_route, decision_recommendation,
                  decision_confidence, decision_abstain_reason, decision_stage_count, decision_json,
                  gate_reasons_json, risk_reasons_json, evidence_event_ids_json, source_event_ids_json,
                  last_edge_events_json, pulse_version, gate_version, prompt_version, schema_version,
                  evidence_packet_hash, evidence_status, decision_status, display_status,
                  claim_verification_json, evidence_gate_json, created_at_ms, updated_at_ms
                )
                VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT(candidate_type, "window", scope, target_type, target_id)
                  WHERE target_type IS NOT NULL AND target_id IS NOT NULL
                DO UPDATE SET
                  candidate_id = excluded.candidate_id,
                  candidate_type = excluded.candidate_type,
                  subject_key = excluded.subject_key,
                  target_type = excluded.target_type,
                  target_id = excluded.target_id,
                  symbol = excluded.symbol,
                  "window" = excluded."window",
                  scope = excluded.scope,
                  pulse_status = excluded.pulse_status,
                  verdict = excluded.verdict,
                  social_phase = excluded.social_phase,
                  candidate_score = excluded.candidate_score,
                  score_band = excluded.score_band,
                  trigger_signature = excluded.trigger_signature,
                  timeline_signature = excluded.timeline_signature,
                  factor_snapshot_json = excluded.factor_snapshot_json,
                  gate_json = excluded.gate_json,
                  decision_route = excluded.decision_route,
                  decision_recommendation = excluded.decision_recommendation,
                  decision_confidence = excluded.decision_confidence,
                  decision_abstain_reason = excluded.decision_abstain_reason,
                  decision_stage_count = excluded.decision_stage_count,
                  decision_json = excluded.decision_json,
                  gate_reasons_json = excluded.gate_reasons_json,
                  risk_reasons_json = excluded.risk_reasons_json,
                  evidence_event_ids_json = excluded.evidence_event_ids_json,
                  source_event_ids_json = excluded.source_event_ids_json,
                  last_edge_events_json = excluded.last_edge_events_json,
                  pulse_version = excluded.pulse_version,
                  gate_version = excluded.gate_version,
                  prompt_version = excluded.prompt_version,
                  schema_version = excluded.schema_version,
                  evidence_packet_hash = excluded.evidence_packet_hash,
                  evidence_status = excluded.evidence_status,
                  decision_status = excluded.decision_status,
                  display_status = excluded.display_status,
                  claim_verification_json = excluded.claim_verification_json,
                  evidence_gate_json = excluded.evidence_gate_json,
                  updated_at_ms = excluded.updated_at_ms
                WHERE (
                  pulse_candidates.candidate_id,
                  pulse_candidates.candidate_type,
                  pulse_candidates.subject_key,
                  pulse_candidates.target_type,
                  pulse_candidates.target_id,
                  pulse_candidates.symbol,
                  pulse_candidates."window",
                  pulse_candidates.scope,
                  pulse_candidates.pulse_status,
                  pulse_candidates.verdict,
                  pulse_candidates.social_phase,
                  pulse_candidates.candidate_score,
                  pulse_candidates.score_band,
                  pulse_candidates.trigger_signature,
                  pulse_candidates.timeline_signature,
                  pulse_candidates.factor_snapshot_json,
                  pulse_candidates.gate_json,
                  pulse_candidates.decision_route,
                  pulse_candidates.decision_recommendation,
                  pulse_candidates.decision_confidence,
                  pulse_candidates.decision_abstain_reason,
                  pulse_candidates.decision_json,
                  pulse_candidates.gate_reasons_json,
                  pulse_candidates.risk_reasons_json,
                  pulse_candidates.evidence_event_ids_json,
                  pulse_candidates.source_event_ids_json,
                  pulse_candidates.last_edge_events_json,
                  pulse_candidates.pulse_version,
                  pulse_candidates.gate_version,
                  pulse_candidates.prompt_version,
                  pulse_candidates.schema_version,
                  pulse_candidates.evidence_packet_hash,
                  pulse_candidates.evidence_status,
                  pulse_candidates.decision_status,
                  pulse_candidates.display_status,
                  pulse_candidates.claim_verification_json,
                  pulse_candidates.evidence_gate_json
                ) IS DISTINCT FROM (
                  excluded.candidate_id,
                  excluded.candidate_type,
                  excluded.subject_key,
                  excluded.target_type,
                  excluded.target_id,
                  excluded.symbol,
                  excluded."window",
                  excluded.scope,
                  excluded.pulse_status,
                  excluded.verdict,
                  excluded.social_phase,
                  excluded.candidate_score,
                  excluded.score_band,
                  excluded.trigger_signature,
                  excluded.timeline_signature,
                  excluded.factor_snapshot_json,
                  excluded.gate_json,
                  excluded.decision_route,
                  excluded.decision_recommendation,
                  excluded.decision_confidence,
                  excluded.decision_abstain_reason,
                  excluded.decision_json,
                  excluded.gate_reasons_json,
                  excluded.risk_reasons_json,
                  excluded.evidence_event_ids_json,
                  excluded.source_event_ids_json,
                  excluded.last_edge_events_json,
                  excluded.pulse_version,
                  excluded.gate_version,
                  excluded.prompt_version,
                  excluded.schema_version,
                  excluded.evidence_packet_hash,
                  excluded.evidence_status,
                  excluded.decision_status,
                  excluded.display_status,
                  excluded.claim_verification_json,
                  excluded.evidence_gate_json
                )
                RETURNING *
                """,
                (
                    candidate_id,
                    candidate_type,
                    _normalize_subject(subject_key),
                    target_type,
                    target_id,
                    _normalize_symbol(symbol),
                    window,
                    scope,
                    pulse_status,
                    verdict,
                    social_phase,
                    float(candidate_score),
                    score_band,
                    trigger_signature,
                    timeline_signature,
                    _json(factor_snapshot_json),
                    _json(gate_json),
                    decision_route,
                    decision_recommendation,
                    float(decision_confidence),
                    decision_abstain_reason,
                    parsed_decision_stage_count,
                    _json(decision_json),
                    _json(gate_reasons_json or []),
                    _json(risk_reasons_json or []),
                    _json(evidence_event_ids_json or []),
                    _json(source_event_ids_json or []),
                    _json(last_edge_events_json or []),
                    pulse_version,
                    gate_version,
                    prompt_version,
                    schema_version,
                    evidence_packet_hash,
                    evidence_status,
                    decision_status,
                    display_status,
                    _json(claim_verification_json or {}),
                    _json(evidence_gate_json or {}),
                    created,
                    now,
                ),
            )
            row = cursor.fetchone()
            return _optional_returning_row(cursor, row)

        return _run_repository_write(self.conn, commit, _upsert_candidate)

    def hide_public_candidate_for_low_information(
        self,
        *,
        candidate_id: str,
        candidate_score: float,
        trigger_signature: str,
        factor_snapshot_json: dict[str, Any],
        gate_json: dict[str, Any],
        gate_reasons_json: list[Any] | None = None,
        risk_reasons_json: list[Any] | None = None,
        evidence_event_ids_json: list[Any] | None = None,
        source_event_ids_json: list[Any] | None = None,
        last_edge_events_json: list[Any] | None = None,
        updated_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        def _hide_public_candidate_for_low_information() -> dict[str, Any] | None:
            now = int(updated_at_ms if updated_at_ms is not None else _now_ms())
            cursor = self.conn.execute(
                """
                UPDATE pulse_candidates
                SET pulse_status = 'blocked_low_information',
                    verdict = 'blocked_low_information',
                    candidate_score = %s,
                    score_band = 'blocked',
                    trigger_signature = %s,
                    factor_snapshot_json = %s,
                    gate_json = %s,
                    gate_reasons_json = %s,
                    risk_reasons_json = %s,
                    evidence_event_ids_json = %s,
                    source_event_ids_json = %s,
                    last_edge_events_json = %s,
                    evidence_status = 'insufficient',
                    decision_status = 'invalid',
                    display_status = 'hidden_blocked_low_information',
                    updated_at_ms = %s
                WHERE candidate_id = %s
                  AND display_status = ANY(%s)
                RETURNING *
                """,
                (
                    float(candidate_score),
                    trigger_signature,
                    _json(factor_snapshot_json),
                    _json(gate_json),
                    _json(gate_reasons_json or []),
                    _json(risk_reasons_json or []),
                    _json(evidence_event_ids_json or []),
                    _json(source_event_ids_json or []),
                    _json(last_edge_events_json or []),
                    now,
                    candidate_id,
                    list(PUBLIC_DISPLAY_STATUSES),
                ),
            )
            row = cursor.fetchone()
            return _optional_returning_row(cursor, row)

        return _run_repository_write(self.conn, commit, _hide_public_candidate_for_low_information)
