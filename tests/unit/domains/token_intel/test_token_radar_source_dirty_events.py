from __future__ import annotations

from importlib import import_module
from typing import ClassVar


def test_source_dirty_event_queue_coalesces_by_source_event_edge() -> None:
    module = import_module(
        "gmgn_twitter_intel.domains.token_intel.repositories.token_radar_source_dirty_event_repository"
    )
    repo = module.TokenRadarSourceDirtyEventRepository(_ScriptedConnection())

    count = repo.enqueue_events(
        [
            {"source_event_id": "event-1", "target_type_key": "Asset", "identity_id": "asset-1"},
            {"event_id": "event-1", "target_type": "Asset", "target_id": "asset-1"},
            {"source_event_id": "", "target_type_key": "Asset", "identity_id": "asset-2"},
        ],
        reason="resolution_updated",
        now_ms=1_700_000_000_000,
        commit=False,
    )

    sql = "\n".join(_ScriptedConnection.last_sql)
    assert count == 1
    assert "INSERT INTO token_radar_source_dirty_events" in sql
    assert "ON CONFLICT(projection_version, source_event_id, target_type_key, identity_id) DO UPDATE SET" in sql
    assert "source_event_ids_json" not in sql
    assert "jsonb_agg" not in sql
    assert _ScriptedConnection.last_params[-1]["source_event_ids"] == ["event-1"]
    assert _ScriptedConnection.last_params[-1]["target_type_keys"] == ["Asset"]
    assert _ScriptedConnection.last_params[-1]["identity_ids"] == ["asset-1"]


def test_source_dirty_event_payload_hash_ignores_lease_lifecycle() -> None:
    module = import_module(
        "gmgn_twitter_intel.domains.token_intel.repositories.token_radar_source_dirty_event_repository"
    )

    first = module.source_dirty_event_payload_hash(
        {
            "source_event_id": "event-1",
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "dirty_at_ms": 1,
            "leased_until_ms": 2,
            "attempt_count": 3,
        }
    )
    second = module.source_dirty_event_payload_hash(
        {
            "source_event_id": "event-1",
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "dirty_at_ms": 9,
            "leased_until_ms": 10,
            "attempt_count": 11,
        }
    )

    assert second == first


class _ScriptedConnection:
    last_sql: ClassVar[list[str]] = []
    last_params: ClassVar[list[dict[str, object]]] = []

    def __init__(self) -> None:
        self.rowcount = 0
        self.commits = 0
        _ScriptedConnection.last_sql = []
        _ScriptedConnection.last_params = []

    def execute(self, sql: str, params: dict[str, object] | None = None) -> _ScriptedConnection:
        _ScriptedConnection.last_sql.append(str(sql))
        _ScriptedConnection.last_params.append(params or {})
        return self

    def fetchall(self) -> list[dict[str, object]]:
        return []

    def commit(self) -> None:
        self.commits += 1
