from gmgn_twitter_intel.domains.narrative_intel.queries.narrative_backlog_health_query import (
    NarrativeBacklogHealthQuery,
)


def test_narrative_backlog_health_aggregates_semantic_runs_and_pending_digests():
    query = NarrativeBacklogHealthQuery(FakeConn())

    health = query.health(now_ms=10_000, since_hours=4, schema_version="narrative_intel_v1")

    assert health["semantic_backlog"] == {
        "total_pending": 5,
        "queued": 3,
        "retryable": 2,
        "stale": 0,
        "unavailable": 1,
        "oldest_due_age_ms": 4_000,
    }
    assert health["recent_runs"]["mention_semantics"] == {"success": 4, "failure": 2, "timeout": 1}
    assert health["recent_runs"]["discussion_digest"] == {"success": 1, "failure": 1, "timeout": 1}
    assert health["admissions"] == {
        "current_admissions": 8,
        "suppressed_admissions": 2,
        "current_source_events": 42,
        "current_independent_authors": 17,
    }
    assert health["digest_status_counts"] == {"pending": 7, "ready": 3}
    assert health["digest_reason_counts"] == {"semantic_labeling_pending": 7}
    assert health["pending_digest_count"] == 7


class FakeConn:
    def execute(self, sql, params=()):
        if "FROM narrative_admissions" in sql:
            return FakeCursor(
                [
                    {
                        "current_admissions": 8,
                        "suppressed_admissions": 2,
                        "current_source_events": 42,
                        "current_independent_authors": 17,
                    }
                ]
            )
        if "FROM token_mention_semantics" in sql:
            return FakeCursor(
                [
                    {
                        "queued": 3,
                        "retryable": 2,
                        "stale": 0,
                        "unavailable": 1,
                        "oldest_due_at_ms": 6_000,
                    }
                ]
            )
        if "FROM narrative_model_runs" in sql:
            return FakeCursor(
                [
                    {"stage": "mention_semantics", "success": 4, "failure": 2, "timeout": 1},
                    {"stage": "discussion_digest", "success": 1, "failure": 1, "timeout": 1},
                ]
            )
        if "GROUP BY status" in sql:
            return FakeCursor([{"status": "pending", "count": 7}, {"status": "ready", "count": 3}])
        if "jsonb_array_elements" in sql:
            return FakeCursor([{"reason": "semantic_labeling_pending", "count": 7}])
        if "pending_digest_count" in sql:
            return FakeCursor([{"pending_digest_count": 7}])
        raise AssertionError(f"unexpected SQL: {sql}")


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows
