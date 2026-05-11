"""Phase 2.0 Goal G1: same input -> same output for token-radar rebuild.

This test runs rebuild() twice with the same fixed now_ms and frozen source
rows, then asserts that the resulting factor_snapshot_json blobs are byte-identical
(after stripping wall-clock fields like computed_at_ms).

The live-DB variant freezes `_source_rows` via monkeypatch so that new events
arriving between the two rebuild calls cannot affect the comparison.  Without
freezing, `total_window_events` and cohort size both shift as the live stream
grows — that is correct DB behaviour, not a code bug.

Skips cleanly if GMGN_PROD_POSTGRES_DSN or GMGN_TEST_POSTGRES_DSN is not set,
so CI without a live container will not break.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any
from unittest.mock import patch

import pytest

from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import TokenRadarProjection
from gmgn_twitter_intel.platform.db.postgres_client import connect_postgres


def _strip_wall_clock(factor_snapshot_json: dict[str, Any]) -> dict[str, Any]:
    """Remove fields that legitimately differ across runs due to wall time."""
    cleaned = json.loads(json.dumps(factor_snapshot_json, default=str))
    for key in ("computed_at_ms", "rebuilt_at_ms", "generated_at_ms"):
        cleaned.pop(key, None)
    cohort = cleaned.get("cohort")
    if isinstance(cohort, dict):
        cohort.pop("computed_at_ms", None)
    return cleaned


def _live_pg_dsn() -> str | None:
    """Return the DSN for the live postgres container, or None if unavailable."""
    return os.environ.get("GMGN_PROD_POSTGRES_DSN") or os.environ.get("GMGN_TEST_POSTGRES_DSN")


def test_token_radar_rebuild_is_idempotent_against_live_db():
    """Two consecutive rebuild() calls with the same frozen source snapshot and
    the same now_ms must produce byte-identical factor_snapshot_json for every row (G1).

    The source rows are frozen after the first DB fetch so that new live events
    arriving between the two Python-level rebuild() invocations cannot affect
    the comparison.  This isolates the test to code-level determinism.
    """
    dsn = _live_pg_dsn()
    if not dsn:
        pytest.skip("No live PG DSN available — set GMGN_PROD_POSTGRES_DSN or GMGN_TEST_POSTGRES_DSN")

    try:
        conn = connect_postgres(dsn)
    except Exception as exc:
        pytest.skip(f"Could not connect to live PG: {exc}")

    # Capture now_ms once so both rebuilds see the same analysis window.
    fixed_now_ms = int(time.time() * 1000)

    try:
        repos = repositories_for_connection(conn)
        projector = TokenRadarProjection(repos=repos)

        # Pull source rows once — this is the frozen snapshot for both runs.
        from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import (
            WINDOW_MS,
            _analysis_since_ms,
        )

        window_ms = WINDOW_MS["1h"]
        analysis_since_ms = _analysis_since_ms(computed_at_ms=fixed_now_ms, window_ms=window_ms)
        frozen_rows = projector._source_rows(
            since_ms=analysis_since_ms,
            scope="all",
            now_ms=fixed_now_ms,
        )

        assert frozen_rows, "No source rows — nothing to score"

        # Both rebuilds use the same frozen source list.
        def _frozen_source_rows(self, *, since_ms, scope, now_ms):
            return frozen_rows

        with patch.object(TokenRadarProjection, "_source_rows", _frozen_source_rows):
            # First rebuild.
            projector.rebuild(window="1h", scope="all", now_ms=fixed_now_ms, limit=10)
            rows_first = conn.execute(
                """
                SELECT target_id, factor_snapshot_json
                FROM token_radar_rows
                WHERE "window" = '1h' AND scope = 'all'
                ORDER BY target_id
                """
            ).fetchall()

            # Second rebuild — same now_ms and same frozen source rows.
            projector.rebuild(window="1h", scope="all", now_ms=fixed_now_ms, limit=10)
            rows_second = conn.execute(
                """
                SELECT target_id, factor_snapshot_json
                FROM token_radar_rows
                WHERE "window" = '1h' AND scope = 'all'
                ORDER BY target_id
                """
            ).fetchall()
    finally:
        conn.close()

    assert rows_first, "No rows written by first rebuild — nothing to compare"
    assert len(rows_first) == len(rows_second), (
        f"Row count diverged: first={len(rows_first)}, second={len(rows_second)}"
    )

    diffs: list[str] = []
    for r1, r2 in zip(rows_first, rows_second, strict=True):
        tid1 = r1["target_id"]
        tid2 = r2["target_id"]
        if tid1 != tid2:
            diffs.append(f"target_id mismatch: {tid1!r} vs {tid2!r}")
            continue
        s1 = _strip_wall_clock(dict(r1["factor_snapshot_json"]))
        s2 = _strip_wall_clock(dict(r2["factor_snapshot_json"]))
        if s1 != s2:
            # Identify which top-level keys differ for actionable diagnostics.
            differing_keys = sorted(k for k in set(list(s1) + list(s2)) if s1.get(k) != s2.get(k))
            diffs.append(f"factor_snapshot_json diverged for {tid1!r}: differing_keys={differing_keys}")

    assert not diffs, "Idempotency violated (G1):\n" + "\n".join(diffs[:10])
