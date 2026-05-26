from __future__ import annotations

from typing import Any

import pytest

from gmgn_twitter_intel.app.runtime.runtime_worker_dirty_targets import enqueue_runtime_worker_dirty_targets
from gmgn_twitter_intel.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION

NOW_MS = 1_700_000_100_000


def test_enqueue_runtime_worker_dirty_targets_dry_run_counts_candidates_without_writing() -> None:
    repos = _FakeRepos(
        rows=[
            _row("Asset", "asset-1", source_watermark_ms=NOW_MS - 1_000, payload_hash="row-hash-1"),
            _row("Asset", "asset-2", source_watermark_ms=NOW_MS - 2_000, payload_hash="row-hash-2"),
        ]
    )

    result = enqueue_runtime_worker_dirty_targets(
        repos,
        work="pulse_trigger",
        window="1h",
        scope="all",
        since_hours=4,
        target_id="",
        limit=500,
        execute=False,
        now_ms=NOW_MS,
    )

    assert result == {
        "work": "pulse_trigger",
        "window": "1h",
        "scope": "all",
        "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
        "dry_run": True,
        "execute": False,
        "since_hours": 4.0,
        "since_ms": NOW_MS - 4 * 60 * 60 * 1000,
        "target_id": None,
        "limit": 500,
        "candidate_count": 2,
        "would_enqueue_count": 2,
        "current_queue_depth": 0,
        "due_queue_depth": 0,
        "downstream_job_depth": 0,
        "downstream_window_scope_job_depth": 0,
        "guardrail_violations": [],
        "enqueued_count": 0,
        "target_sample_count": 2,
        "target_sample": [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "window": "1h",
                "scope": "all",
                "source_watermark_ms": NOW_MS - 1_000,
                "current_row_payload_hash": "row-hash-1",
                "payload_hash": result["target_sample"][0]["payload_hash"],
            },
            {
                "target_type": "Asset",
                "target_id": "asset-2",
                "window": "1h",
                "scope": "all",
                "source_watermark_ms": NOW_MS - 2_000,
                "current_row_payload_hash": "row-hash-2",
                "payload_hash": result["target_sample"][1]["payload_hash"],
            },
        ],
    }
    assert repos.pulse_trigger_dirty_targets.enqueued == []
    assert repos.conn.calls == [
        {
            "now_ms": NOW_MS,
        },
        {
            "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
            "window": "1h",
            "scope": "all",
            "since_ms": NOW_MS - 4 * 60 * 60 * 1000,
            "target_id": None,
            "limit": 500,
        },
    ]


def test_enqueue_runtime_worker_dirty_targets_execute_enqueues_pulse_trigger_targets() -> None:
    repos = _FakeRepos(
        rows=[_row("Asset", "asset-1", source_watermark_ms=NOW_MS - 1_000, window="4h", scope="matched")]
    )

    result = enqueue_runtime_worker_dirty_targets(
        repos,
        work="pulse_trigger",
        window="4h",
        scope="matched",
        since_hours=None,
        target_id="asset-1",
        limit=25,
        execute=True,
        now_ms=NOW_MS,
    )

    assert result["dry_run"] is False
    assert result["execute"] is True
    assert result["candidate_count"] == 1
    assert result["enqueued_count"] == 1
    assert result["target_id"] == "asset-1"
    assert repos.pulse_trigger_dirty_targets.enqueued == [
        {
            "targets": [
                {
                    "target_type": "Asset",
                    "target_id": "asset-1",
                    "window": "4h",
                    "scope": "matched",
                    "source_watermark_ms": NOW_MS - 1_000,
                    "payload_hash": result["target_sample"][0]["payload_hash"],
                }
            ],
            "reason": "ops_runtime_worker_repair",
            "now_ms": NOW_MS,
            "commit": False,
        }
    ]
    assert repos.conn.commits == 1


def test_enqueue_runtime_worker_dirty_targets_dry_run_counts_narrative_admission_candidates() -> None:
    repos = _FakeRepos(
        rows=[
            _row("Asset", "asset-1", source_watermark_ms=NOW_MS - 1_000, payload_hash="row-hash-1"),
            _row("Asset", "asset-2", source_watermark_ms=NOW_MS - 2_000, payload_hash="row-hash-2"),
        ]
    )

    result = enqueue_runtime_worker_dirty_targets(
        repos,
        work="narrative_admission",
        window="1h",
        scope="all",
        since_hours=4,
        target_id="",
        limit=500,
        execute=False,
        now_ms=NOW_MS,
    )

    assert result["work"] == "narrative_admission"
    assert result["candidate_count"] == 2
    assert result["would_enqueue_count"] == 2
    assert result["schema_version"] == NARRATIVE_SCHEMA_VERSION
    assert result["target_sample_count"] == 2
    assert result["target_sample"][0]["projection_version"] == TOKEN_RADAR_PROJECTION_VERSION
    assert result["target_sample"][0]["schema_version"] == NARRATIVE_SCHEMA_VERSION
    assert repos.narrative_admission_dirty_targets.enqueued == []


def test_enqueue_runtime_worker_dirty_targets_execute_enqueues_narrative_admission_targets() -> None:
    repos = _FakeRepos(rows=[_row("Asset", "asset-1", source_watermark_ms=NOW_MS - 1_000)])

    result = enqueue_runtime_worker_dirty_targets(
        repos,
        work="narrative_admission",
        window="1h",
        scope="all",
        since_hours=None,
        target_id="asset-1",
        limit=25,
        execute=True,
        now_ms=NOW_MS,
    )

    assert result["dry_run"] is False
    assert result["execute"] is True
    assert result["candidate_count"] == 1
    assert result["enqueued_count"] == 1
    assert repos.narrative_admission_dirty_targets.enqueued == [
        {
            "targets": [
                {
                    "target_type": "Asset",
                    "target_id": "asset-1",
                    "window": "1h",
                    "scope": "all",
                    "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                    "schema_version": NARRATIVE_SCHEMA_VERSION,
                    "source_watermark_ms": NOW_MS - 1_000,
                    "payload_hash": result["target_sample"][0]["payload_hash"],
                }
            ],
            "reason": "ops_runtime_worker_repair",
            "now_ms": NOW_MS,
            "commit": False,
        }
    ]
    assert repos.conn.commits == 1


def test_enqueue_runtime_worker_dirty_targets_dry_run_counts_discussion_digest_candidates() -> None:
    repos = _FakeRepos(
        rows=[
            _row("chain_token", "solana:So111", source_watermark_ms=NOW_MS - 1_000, payload_hash="source-fp-1"),
            _row("chain_token", "solana:Bonk", source_watermark_ms=NOW_MS - 2_000, payload_hash="source-fp-2"),
        ]
    )

    result = enqueue_runtime_worker_dirty_targets(
        repos,
        work="discussion_digest",
        window="1h",
        scope="matched",
        since_hours=4,
        target_id="",
        limit=500,
        execute=False,
        now_ms=NOW_MS,
    )

    assert result["work"] == "discussion_digest"
    assert result["candidate_count"] == 2
    assert result["would_enqueue_count"] == 2
    assert result["schema_version"] == NARRATIVE_SCHEMA_VERSION
    assert result["target_sample_count"] == 2
    assert result["target_sample"][0]["projection_version"] == TOKEN_RADAR_PROJECTION_VERSION
    assert result["target_sample"][0]["schema_version"] == NARRATIVE_SCHEMA_VERSION
    assert repos.discussion_digest_dirty_targets.enqueued == []


def test_enqueue_runtime_worker_dirty_targets_execute_enqueues_discussion_digest_targets() -> None:
    repos = _FakeRepos(rows=[_row("chain_token", "solana:So111", source_watermark_ms=NOW_MS - 1_000)])

    result = enqueue_runtime_worker_dirty_targets(
        repos,
        work="discussion_digest",
        window="1h",
        scope="matched",
        since_hours=None,
        target_id="solana:So111",
        limit=25,
        execute=True,
        now_ms=NOW_MS,
    )

    assert result["dry_run"] is False
    assert result["execute"] is True
    assert result["candidate_count"] == 1
    assert result["enqueued_count"] == 1
    assert repos.discussion_digest_dirty_targets.enqueued == [
        {
            "targets": [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "1h",
                    "scope": "matched",
                    "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                    "schema_version": NARRATIVE_SCHEMA_VERSION,
                    "source_watermark_ms": NOW_MS - 1_000,
                    "payload_hash": result["target_sample"][0]["payload_hash"],
                }
            ],
            "reason": "ops_runtime_worker_repair",
            "now_ms": NOW_MS,
            "commit": False,
        }
    ]
    assert repos.conn.commits == 1


def test_enqueue_runtime_worker_dirty_targets_execute_requires_explicit_limit() -> None:
    repos = _FakeRepos(rows=[_row("Asset", "asset-1", source_watermark_ms=NOW_MS - 1_000)])

    with pytest.raises(ValueError, match="requires explicit --limit"):
        enqueue_runtime_worker_dirty_targets(
            repos,
            work="pulse_trigger",
            window="1h",
            scope="all",
            since_hours=4,
            target_id="",
            limit=None,
            execute=True,
            now_ms=NOW_MS,
        )


def test_enqueue_runtime_worker_dirty_targets_rejects_overwide_agent_window() -> None:
    repos = _FakeRepos(rows=[])

    with pytest.raises(ValueError, match="<= 4"):
        enqueue_runtime_worker_dirty_targets(
            repos,
            work="pulse_trigger",
            window="1h",
            scope="all",
            since_hours=5,
            target_id="",
            limit=500,
            execute=False,
            now_ms=NOW_MS,
        )


def test_enqueue_runtime_worker_dirty_targets_rejects_overwide_narrative_admission_window() -> None:
    repos = _FakeRepos(rows=[])

    with pytest.raises(ValueError, match="<= 4"):
        enqueue_runtime_worker_dirty_targets(
            repos,
            work="narrative_admission",
            window="1h",
            scope="all",
            since_hours=5,
            target_id="",
            limit=500,
            execute=False,
            now_ms=NOW_MS,
        )


def test_enqueue_runtime_worker_dirty_targets_rejects_unsupported_narrative_window_scope() -> None:
    repos = _FakeRepos(rows=[])

    with pytest.raises(ValueError, match="unsupported narrative_admission repair window"):
        enqueue_runtime_worker_dirty_targets(
            repos,
            work="narrative_admission",
            window="4h",
            scope="all",
            since_hours=4,
            target_id="",
            limit=500,
            execute=False,
            now_ms=NOW_MS,
        )


def test_enqueue_runtime_worker_dirty_targets_rejects_unsupported_discussion_digest_window_scope() -> None:
    repos = _FakeRepos(rows=[])

    with pytest.raises(ValueError, match="unsupported discussion_digest repair window"):
        enqueue_runtime_worker_dirty_targets(
            repos,
            work="discussion_digest",
            window="4h",
            scope="matched",
            since_hours=4,
            target_id="",
            limit=500,
            execute=False,
            now_ms=NOW_MS,
        )


def test_enqueue_runtime_worker_dirty_targets_execute_refuses_backlog_guardrail() -> None:
    repos = _FakeRepos(
        rows=[_row("Asset", "asset-1", source_watermark_ms=NOW_MS - 1_000)],
        downstream_job_depth=101,
    )

    with pytest.raises(ValueError, match="downstream_job_depth"):
        enqueue_runtime_worker_dirty_targets(
            repos,
            work="pulse_trigger",
            window="1h",
            scope="all",
            since_hours=4,
            target_id="",
            limit=500,
            execute=True,
            now_ms=NOW_MS,
        )


def test_enqueue_runtime_worker_dirty_targets_requires_bounded_target_or_since_hours() -> None:
    repos = _FakeRepos(rows=[])

    with pytest.raises(ValueError, match="requires --since-hours or --target-id"):
        enqueue_runtime_worker_dirty_targets(
            repos,
            work="pulse_trigger",
            window="1h",
            scope="all",
            since_hours=None,
            target_id="",
            limit=500,
            execute=False,
            now_ms=NOW_MS,
        )


def test_enqueue_runtime_worker_dirty_targets_uses_stable_payload_hash() -> None:
    repos = _FakeRepos(rows=[_row("Asset", "asset-1", source_watermark_ms=NOW_MS - 1_000)])
    first = enqueue_runtime_worker_dirty_targets(
        repos,
        work="pulse_trigger",
        window="1h",
        scope="all",
        since_hours=4,
        target_id="",
        limit=500,
        execute=False,
        now_ms=NOW_MS,
    )
    second = enqueue_runtime_worker_dirty_targets(
        repos,
        work="pulse_trigger",
        window="1h",
        scope="all",
        since_hours=4,
        target_id="",
        limit=500,
        execute=False,
        now_ms=NOW_MS,
    )

    assert first["target_sample"][0]["payload_hash"] == second["target_sample"][0]["payload_hash"]


def test_enqueue_runtime_worker_dirty_targets_execute_enqueues_profile_current_target() -> None:
    repos = _FakeRepos(rows=[])

    result = enqueue_runtime_worker_dirty_targets(
        repos,
        work="profile_current",
        window="1h",
        scope="all",
        since_hours=None,
        target_id="cex_token:BTC",
        limit=25,
        execute=True,
        now_ms=NOW_MS,
    )

    assert result["work"] == "profile_current"
    assert result["target_type"] == "CexToken"
    assert result["candidate_count"] == 1
    assert result["enqueued_count"] == 1
    assert repos.token_profile_current_dirty_targets.enqueued[0]["targets"] == [
        {
            "target_type": "CexToken",
            "target_id": "cex_token:BTC",
            "source_watermark_ms": NOW_MS,
            "priority": 100,
        }
    ]
    assert repos.conn.commits == 1


def test_enqueue_runtime_worker_dirty_targets_execute_enqueues_image_source_manual_target() -> None:
    repos = _FakeRepos(rows=[])

    result = enqueue_runtime_worker_dirty_targets(
        repos,
        work="image_source",
        window="1h",
        scope="all",
        since_hours=None,
        target_id="asset:eip155:1:erc20:0xabc",
        target_type="Asset",
        source_url="https://gmgn.ai/external-res/abc.png",
        limit=25,
        execute=True,
        now_ms=NOW_MS,
    )

    assert result["work"] == "image_source"
    assert result["candidate_count"] == 1
    assert result["enqueued_count"] == 1
    target = repos.token_image_source_dirty_targets.enqueued[0]["targets"][0]
    assert target["source_url"] == "https://gmgn.ai/external-res/abc.png"
    assert target["target_type"] == "Asset"
    assert target["target_id"] == "asset:eip155:1:erc20:0xabc"
    assert repos.conn.commits == 1


def test_enqueue_runtime_worker_dirty_targets_asset_profile_refresh_requires_provider() -> None:
    repos = _FakeRepos(rows=[])

    with pytest.raises(ValueError, match="requires --provider"):
        enqueue_runtime_worker_dirty_targets(
            repos,
            work="asset_profile_refresh",
            window="1h",
            scope="all",
            since_hours=4,
            target_id="",
            limit=25,
            execute=False,
            now_ms=NOW_MS,
        )


def test_enqueue_runtime_worker_dirty_targets_execute_enqueues_asset_profile_refresh_targets() -> None:
    repos = _FakeRepos(
        rows=[
            {
                "provider": "gmgn_dex_profile",
                "target_type": "Asset",
                "target_id": "asset:eip155:1:erc20:0xabc",
                "chain_id": "eip155:1",
                "address": "0xabc",
                "symbol": "ABC",
                "source_watermark_ms": NOW_MS - 1_000,
                "priority": 100,
            }
        ]
    )

    result = enqueue_runtime_worker_dirty_targets(
        repos,
        work="asset_profile_refresh",
        window="1h",
        scope="all",
        provider="gmgn_dex_profile",
        since_hours=4,
        target_id="",
        limit=25,
        execute=True,
        now_ms=NOW_MS,
    )

    assert result["work"] == "asset_profile_refresh"
    assert result["candidate_count"] == 1
    assert result["enqueued_count"] == 1
    assert repos.asset_profile_refresh_targets.enqueued[0]["targets"][0]["provider"] == "gmgn_dex_profile"
    assert repos.conn.commits == 1


def test_enqueue_runtime_worker_dirty_targets_execute_enqueues_capture_tier_global_target() -> None:
    repos = _FakeRepos(rows=[])

    result = enqueue_runtime_worker_dirty_targets(
        repos,
        work="capture_tier",
        window="1h",
        scope="all",
        since_hours=None,
        target_id="",
        limit=1,
        execute=True,
        now_ms=NOW_MS,
    )

    assert result["work"] == "capture_tier"
    assert result["candidate_count"] == 1
    assert result["enqueued_count"] == 1
    assert repos.token_capture_tier_dirty_targets.enqueued == [
        {"reason": "ops_runtime_worker_repair", "now_ms": NOW_MS, "commit": False}
    ]
    assert repos.conn.commits == 1


def _row(
    target_type: str,
    target_id: str,
    *,
    source_watermark_ms: int,
    payload_hash: str = "row-hash",
    window: str = "1h",
    scope: str = "all",
) -> dict[str, Any]:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "window": window,
        "scope": scope,
        "source_watermark_ms": source_watermark_ms,
        "current_row_payload_hash": payload_hash,
    }


class _FakeRepos:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]],
        current_queue_depth: int = 0,
        due_queue_depth: int = 0,
        downstream_job_depth: int = 0,
        downstream_window_scope_job_depth: int = 0,
    ) -> None:
        self.conn = _FakeConn(
            rows,
            current_queue_depth=current_queue_depth,
            due_queue_depth=due_queue_depth,
        )
        self.pulse_trigger_dirty_targets = _FakePulseTriggerDirtyTargets()
        self.narrative_admission_dirty_targets = _FakeNarrativeAdmissionDirtyTargets()
        self.discussion_digest_dirty_targets = _FakeDiscussionDigestDirtyTargets()
        self.token_profile_current_dirty_targets = _FakeGenericDirtyTargets()
        self.token_image_source_dirty_targets = _FakeGenericDirtyTargets()
        self.asset_profile_refresh_targets = _FakeGenericDirtyTargets()
        self.token_capture_tier_dirty_targets = _FakeCaptureTierDirtyTargets()
        self.pulse_jobs = _FakePulseJobs(
            downstream_job_depth=downstream_job_depth,
            downstream_window_scope_job_depth=downstream_window_scope_job_depth,
        )


class _FakeConn:
    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        current_queue_depth: int,
        due_queue_depth: int,
    ) -> None:
        self.rows = rows
        self.current_queue_depth = current_queue_depth
        self.due_queue_depth = due_queue_depth
        self.calls: list[dict[str, Any]] = []
        self.commits = 0

    def execute(self, _sql: str, params: dict[str, Any]):
        self.calls.append(dict(params))
        if (
            "FROM pulse_trigger_dirty_targets" in _sql
            or "FROM narrative_admission_dirty_targets" in _sql
            or "FROM discussion_digest_dirty_targets" in _sql
            or "FROM token_profile_current_dirty_targets" in _sql
            or "FROM token_image_source_dirty_targets" in _sql
            or "FROM asset_profile_refresh_targets" in _sql
            or "FROM token_capture_tier_dirty_targets" in _sql
        ):
            return _FakeCursor(
                [
                    {
                        "current_queue_depth": self.current_queue_depth,
                        "due_queue_depth": self.due_queue_depth,
                    }
                ]
            )
        rows = [
            {
                **row,
                "window": str(params.get("window", row.get("window", "1h"))),
                "scope": str(params.get("scope", row.get("scope", "all"))),
            }
            for row in self.rows
        ]
        return _FakeCursor(rows)

    def commit(self) -> None:
        self.commits += 1


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _FakePulseTriggerDirtyTargets:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, Any]] = []

    def enqueue_targets(self, targets: list[dict[str, Any]], *, reason: str, now_ms: int, commit: bool):
        self.enqueued.append(
            {
                "targets": targets,
                "reason": reason,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return {"targets": len(targets)}


class _FakeNarrativeAdmissionDirtyTargets:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, Any]] = []

    def enqueue_targets(self, targets: list[dict[str, Any]], *, reason: str, now_ms: int, commit: bool):
        self.enqueued.append(
            {
                "targets": targets,
                "reason": reason,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return {"targets": len(targets)}


class _FakeDiscussionDigestDirtyTargets:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, Any]] = []

    def enqueue_targets(self, targets: list[dict[str, Any]], *, reason: str, now_ms: int, commit: bool):
        self.enqueued.append(
            {
                "targets": targets,
                "reason": reason,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return {"targets": len(targets)}


class _FakeGenericDirtyTargets:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, Any]] = []

    def enqueue_targets(self, targets: list[dict[str, Any]], *, reason: str, now_ms: int, commit: bool):
        self.enqueued.append(
            {
                "targets": targets,
                "reason": reason,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return {"targets": len(targets)}


class _FakeCaptureTierDirtyTargets:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, Any]] = []

    def enqueue_global(self, *, reason: str, now_ms: int, commit: bool):
        self.enqueued.append({"reason": reason, "now_ms": now_ms, "commit": commit})
        return {"targets": 1}


class _FakePulseJobs:
    def __init__(self, *, downstream_job_depth: int, downstream_window_scope_job_depth: int) -> None:
        self.downstream_job_depth = downstream_job_depth
        self.downstream_window_scope_job_depth = downstream_window_scope_job_depth

    def pending_agent_job_count(self) -> int:
        return self.downstream_job_depth

    def pending_agent_job_count_for_window_scope(self, *, window: str, scope: str) -> int:
        return self.downstream_window_scope_job_depth
