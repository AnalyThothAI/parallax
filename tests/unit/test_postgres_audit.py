from __future__ import annotations

from typing import Any

from parallax.platform.db.postgres_audit import ProjectionValidationAudit


def test_projection_validation_audit_batches_token_radar_reference_checks() -> None:
    conn = RecordingProjectionValidationConn(
        radar_rows=[
            {
                "row_id": "row-ok",
                "intent_id": "intent-ok",
                "target_type": "Asset",
                "target_id": "asset-ok",
            },
            {
                "row_id": "row-missing-intent",
                "intent_id": "intent-missing",
                "target_type": "Asset",
                "target_id": "asset-ok",
            },
            {
                "row_id": "row-missing-asset",
                "intent_id": "intent-asset-missing",
                "target_type": "Asset",
                "target_id": "asset-missing",
            },
        ],
        intent_ids={"intent-ok", "intent-asset-missing"},
        asset_ids={"asset-ok"},
        latest_computed_at_ms=1_700_000_000_000,
    )

    payload = ProjectionValidationAudit(conn).run(sample=50)

    assert payload["ok"] is False
    assert payload["status"] == "ready"
    assert payload["checked_count"] == 3
    assert payload["mismatch_count"] == 2
    assert payload["checks"]["token_radar_current_rows_missing_refs"] == 2
    reference_sql = [sql for sql in conn.executed_sql if "WITH sampled_radar_rows AS" in sql]
    assert len(reference_sql) == 1
    assert "LEFT JOIN token_intents" in reference_sql[0]
    assert "LEFT JOIN registry_assets" in reference_sql[0]
    assert all(
        "SELECT 1 AS ok FROM token_intents WHERE intent_id = %s" not in sql
        for sql in conn.executed_sql
    )
    assert all(
        "SELECT 1 AS ok FROM registry_assets WHERE asset_id = %s" not in sql
        for sql in conn.executed_sql
    )


class RecordingProjectionValidationConn:
    def __init__(
        self,
        *,
        radar_rows: list[dict[str, Any]],
        intent_ids: set[str],
        asset_ids: set[str],
        latest_computed_at_ms: int | None,
    ) -> None:
        self._radar_rows = radar_rows
        self._intent_ids = intent_ids
        self._asset_ids = asset_ids
        self._latest_computed_at_ms = latest_computed_at_ms
        self.executed_sql: list[str] = []

    def execute(
        self, sql: str, params: tuple[object, ...] | None = None
    ) -> RecordingRows:
        self.executed_sql.append(sql)
        params_tuple = tuple(params or ())
        if "WITH sampled_radar_rows AS" in sql:
            sample = max(0, int(params_tuple[0] if params_tuple else 0))
            rows = self._radar_rows[:sample]
            missing_intents = sum(
                1 for row in rows if str(row.get("intent_id") or "") not in self._intent_ids
            )
            missing_assets = sum(
                1
                for row in rows
                if row.get("target_type") == "Asset"
                and str(row.get("target_id") or "") != ""
                and str(row.get("target_id") or "") not in self._asset_ids
            )
            return RecordingRows(
                [
                    {
                        "computed_at_ms": self._latest_computed_at_ms,
                        "checked_count": len(rows),
                        "mismatch_count": missing_intents + missing_assets,
                    }
                ]
            )
        if "SELECT row_id, intent_id, target_type, target_id" in sql:
            sample = max(0, int(params_tuple[0] if params_tuple else 0))
            return RecordingRows(self._radar_rows[:sample])
        if "SELECT 1 AS ok FROM token_intents WHERE intent_id = %s" in sql:
            intent_id = str(params_tuple[0] if params_tuple else "")
            return RecordingRows([{"ok": True}] if intent_id in self._intent_ids else [])
        if "SELECT 1 AS ok FROM registry_assets WHERE asset_id = %s" in sql:
            asset_id = str(params_tuple[0] if params_tuple else "")
            return RecordingRows([{"ok": True}] if asset_id in self._asset_ids else [])
        if "SELECT MAX(computed_at_ms)" in sql:
            return RecordingRows([{"computed_at_ms": self._latest_computed_at_ms}])
        raise AssertionError(f"unexpected SQL: {sql}")


class RecordingRows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)
