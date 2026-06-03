"""Add payload hash gates to narrative read models."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20260603_0144"
down_revision = "20260603_0143"
branch_labels = None
depends_on = None

_BACKFILL_BATCH_SIZE = 1_000


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute("ALTER TABLE narrative_admissions ADD COLUMN IF NOT EXISTS payload_hash TEXT")
    op.execute("ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS payload_hash TEXT")
    _backfill_narrative_admission_payload_hashes()
    _backfill_token_discussion_digest_payload_hashes()
    op.execute("ALTER TABLE narrative_admissions ALTER COLUMN payload_hash SET NOT NULL")
    op.execute("ALTER TABLE token_discussion_digests ALTER COLUMN payload_hash SET NOT NULL")
    op.execute("ANALYZE narrative_admissions")
    op.execute("ANALYZE token_discussion_digests")


def downgrade() -> None:
    op.execute("ALTER TABLE token_discussion_digests DROP COLUMN IF EXISTS payload_hash")
    op.execute("ALTER TABLE narrative_admissions DROP COLUMN IF EXISTS payload_hash")


def narrative_admission_payload_hash(row: Mapping[str, Any]) -> str:
    return _stable_payload_hash(
        {
            "target_type": row.get("target_type"),
            "target_id": row.get("target_id"),
            "window": row.get("window"),
            "scope": row.get("scope"),
            "schema_version": row.get("schema_version"),
            "status": row.get("status"),
            "reason": row.get("reason"),
            "priority": row.get("priority"),
            "last_radar_rank": row.get("last_radar_rank"),
            "last_rank_score": row.get("last_rank_score"),
            "source_event_ids_json": row.get("source_event_ids_json"),
            "source_fingerprint": row.get("source_fingerprint"),
            "source_max_received_at_ms": row.get("source_max_received_at_ms"),
            "source_window_start_ms": row.get("source_window_start_ms"),
            "source_window_end_ms": row.get("source_window_end_ms"),
            "source_event_count": row.get("source_event_count"),
            "independent_author_count": row.get("independent_author_count"),
        }
    )


def token_discussion_digest_payload_hash(row: Mapping[str, Any]) -> str:
    return _stable_payload_hash(
        {
            "target_type": row.get("target_type"),
            "target_id": row.get("target_id"),
            "window": row.get("window"),
            "scope": row.get("scope"),
            "schema_version": row.get("schema_version"),
            "model_version": row.get("model_version"),
            "status": row.get("status"),
            "epoch_policy_version": row.get("epoch_policy_version"),
            "source_event_ids_json": row.get("source_event_ids_json"),
            "source_window_start_ms": row.get("source_window_start_ms"),
            "source_window_end_ms": row.get("source_window_end_ms"),
            "refresh_reason": row.get("refresh_reason"),
            "source_fingerprint": row.get("source_fingerprint"),
            "label_fingerprint": row.get("label_fingerprint"),
            "headline_zh": row.get("headline_zh"),
            "dominant_narratives_json": row.get("dominant_narratives_json"),
            "bull_view_json": row.get("bull_view_json"),
            "bear_view_json": row.get("bear_view_json"),
            "stance_mix_json": row.get("stance_mix_json"),
            "attention_valence_mix_json": row.get("attention_valence_mix_json"),
            "propagation_read_json": row.get("propagation_read_json"),
            "reflexivity_read_json": row.get("reflexivity_read_json"),
            "watch_triggers_json": row.get("watch_triggers_json"),
            "invalidation_conditions_json": row.get("invalidation_conditions_json"),
            "data_gaps_json": row.get("data_gaps_json"),
            "semantic_coverage": row.get("semantic_coverage"),
            "source_event_count": row.get("source_event_count"),
            "labeled_event_count": row.get("labeled_event_count"),
            "independent_author_count": row.get("independent_author_count"),
            "evidence_refs_json": row.get("evidence_refs_json"),
        }
    )


def _backfill_narrative_admission_payload_hashes() -> None:
    bind = op.get_bind()
    select_rows = sa.text(
        """
        SELECT
          ctid::text AS row_ctid,
          target_type,
          target_id,
          "window",
          scope,
          schema_version,
          status,
          reason,
          priority,
          last_radar_rank,
          last_rank_score,
          source_event_ids_json,
          source_fingerprint,
          source_max_received_at_ms,
          source_window_start_ms,
          source_window_end_ms,
          source_event_count,
          independent_author_count
        FROM narrative_admissions
        WHERE payload_hash IS NULL OR payload_hash = ''
        ORDER BY target_type, target_id, "window", scope, schema_version
        LIMIT :limit
        """
    )
    update_hash = sa.text(
        """
        UPDATE narrative_admissions
        SET payload_hash = :payload_hash
        WHERE ctid = CAST(:row_ctid AS tid)
        """
    )
    while True:
        rows = bind.execute(select_rows, {"limit": _BACKFILL_BATCH_SIZE}).mappings().all()
        if not rows:
            break
        for row in rows:
            bind.execute(
                update_hash,
                {
                    "row_ctid": row["row_ctid"],
                    "payload_hash": narrative_admission_payload_hash(row),
                },
            )


def _backfill_token_discussion_digest_payload_hashes() -> None:
    bind = op.get_bind()
    select_rows = sa.text(
        """
        SELECT
          ctid::text AS row_ctid,
          target_type,
          target_id,
          "window",
          scope,
          schema_version,
          model_version,
          status,
          epoch_policy_version,
          source_event_ids_json,
          source_window_start_ms,
          source_window_end_ms,
          refresh_reason,
          source_fingerprint,
          label_fingerprint,
          headline_zh,
          dominant_narratives_json,
          bull_view_json,
          bear_view_json,
          stance_mix_json,
          attention_valence_mix_json,
          propagation_read_json,
          reflexivity_read_json,
          watch_triggers_json,
          invalidation_conditions_json,
          data_gaps_json,
          semantic_coverage,
          source_event_count,
          labeled_event_count,
          independent_author_count,
          evidence_refs_json
        FROM token_discussion_digests
        WHERE payload_hash IS NULL OR payload_hash = ''
        ORDER BY target_type, target_id, "window", scope, schema_version, computed_at_ms, digest_id
        LIMIT :limit
        """
    )
    update_hash = sa.text(
        """
        UPDATE token_discussion_digests
        SET payload_hash = :payload_hash
        WHERE ctid = CAST(:row_ctid AS tid)
        """
    )
    while True:
        rows = bind.execute(select_rows, {"limit": _BACKFILL_BATCH_SIZE}).mappings().all()
        if not rows:
            break
        for row in rows:
            bind.execute(
                update_hash,
                {
                    "row_ctid": row["row_ctid"],
                    "payload_hash": token_discussion_digest_payload_hash(row),
                },
            )


def _stable_payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(_json_ready(payload), ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(inner) for key, inner in value.items()}
    if isinstance(value, tuple | list):
        return [_json_ready(inner) for inner in value]
    if isinstance(value, set | frozenset):
        return sorted(_json_ready(inner) for inner in value)
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
