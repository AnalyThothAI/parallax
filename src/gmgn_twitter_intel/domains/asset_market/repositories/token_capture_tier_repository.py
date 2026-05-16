from __future__ import annotations

from decimal import Decimal
from typing import Any, cast


class TokenCaptureTierRepository:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def upsert_tier(
        self,
        *,
        target_type: str,
        target_id: str,
        tier: int,
        reason: str,
        score: Decimal,
        updated_at_ms: int,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO token_capture_tier(
                target_type,
                target_id,
                tier,
                reason,
                score,
                updated_at_ms
            )
            VALUES (
                %(target_type)s,
                %(target_id)s,
                %(tier)s,
                %(reason)s,
                %(score)s,
                %(updated_at_ms)s
            )
            ON CONFLICT(target_type, target_id) DO UPDATE SET
                tier = EXCLUDED.tier,
                reason = EXCLUDED.reason,
                score = EXCLUDED.score,
                updated_at_ms = EXCLUDED.updated_at_ms
            """,
            {
                "target_type": target_type,
                "target_id": target_id,
                "tier": tier,
                "reason": reason,
                "score": score,
                "updated_at_ms": updated_at_ms,
            },
        )

    def list_by_tier(self, tier: int, limit: int) -> list[dict[str, Any]]:
        return list(
            self._conn.execute(
                """
                SELECT *
                FROM token_capture_tier
                WHERE tier = %(tier)s
                ORDER BY score DESC, updated_at_ms DESC, target_id ASC
                LIMIT %(limit)s
                """,
                {"tier": tier, "limit": limit},
            ).fetchall()
        )

    def get(self, target_type: str, target_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM token_capture_tier
            WHERE target_type = %(target_type)s
              AND target_id = %(target_id)s
            """,
            {"target_type": target_type, "target_id": target_id},
        ).fetchone()
        return cast("dict[str, Any] | None", row)
