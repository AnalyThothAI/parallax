from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import date
from types import SimpleNamespace

from parallax.app.surfaces.api.routes_macro import _daily_judgment_payload
from parallax.app.surfaces.api.schemas import DailyMacroJudgmentReadData
from parallax.domains.macro_intel.runtime.daily_macro_judgment_worker import DailyMacroJudgmentWorker
from parallax.domains.macro_intel.services.daily_macro_judgment import (
    DailyMacroJudgment,
    MacroAgentAnalysis,
    MacroEvidencePack,
    ReviewerResult,
)
from parallax.domains.macro_intel.services.macro_cross_asset_rules import (
    market_session_advance,
    market_session_close_ms,
)
from parallax.platform.config.settings import DailyMacroJudgmentWorkerSettings
from tests.postgres_test_utils import (
    connect_postgres_test,
    repository_session_for_connection,
)
from tests.postgres_test_utils import reset_postgres_schema as migrate

SESSION = date(2026, 7, 22)
NOW_MS = market_session_close_ms(SESSION) + 31 * 60 * 1_000


def test_point_in_time_facts_publish_one_immutable_judgment_and_append_outcomes(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_spy(conn, session_date=SESSION, close=625.10, ingested_at_ms=NOW_MS - 1)
        agent = _FakeAgent(conn)
        worker = _worker(conn, agent=agent)

        first = worker.run_once_sync(now_ms=NOW_MS)
        publication = conn.execute(
            """
            SELECT publications.*, jobs.evidence_pack_json, jobs.status AS job_status
            FROM macro_judgment_publications AS publications
            JOIN macro_judgment_jobs AS jobs USING (session_date)
            WHERE publications.session_date = %s
            """,
            (SESSION,),
        ).fetchone()
        conn.commit()

        second = worker.run_once_sync(now_ms=NOW_MS + 1)
        publication_count = conn.execute(
            "SELECT COUNT(*) AS count FROM macro_judgment_publications WHERE session_date = %s",
            (SESSION,),
        ).fetchone()["count"]
        conn.commit()

        target_5 = market_session_advance(SESSION, sessions=5)
        target_20 = market_session_advance(SESSION, sessions=20)
        _seed_spy(conn, session_date=target_5, close=630.00, ingested_at_ms=NOW_MS + 2)
        _seed_spy(conn, session_date=target_20, close=650.00, ingested_at_ms=NOW_MS + 3)
        conn.commit()
        maturity_now = market_session_close_ms(target_20) + 31 * 60 * 1_000
        matured_writes = worker._mature_outcomes(now_ms=maturity_now)
        outcomes = conn.execute(
            """
            SELECT horizon_sessions, target_session_date, start_close, target_close, realized_return_pct
            FROM macro_judgment_outcomes
            WHERE session_date = %s
            ORDER BY horizon_sessions
            """,
            (SESSION,),
        ).fetchall()
        judgment_after_outcome = conn.execute(
            "SELECT judgment_json, memo_text FROM macro_judgment_publications WHERE session_date = %s",
            (SESSION,),
        ).fetchone()
        conn.commit()
        with repository_session_for_connection(conn) as repos:
            read_payload = _daily_judgment_payload(
                repos.daily_macro_judgments,
                requested_session=SESSION,
                now_ms=NOW_MS,
            )
        conn.commit()
        typed_read = DailyMacroJudgmentReadData.model_validate(read_payload)
    finally:
        conn.close()

    assert first.processed == 1
    assert first.failed == 0
    assert first.notes["publication"] == "published"
    assert first.notes["publication_rows_written"] == 1
    assert publication is not None
    assert publication["job_status"] == "published"
    assert publication["judgment_json"]["spy_5d"]["direction"] == "no_call"
    assert publication["judgment_json"]["spy_20d"]["direction"] == "no_call"
    assert publication["evidence_pack_json"]["session_date"] == SESSION.isoformat()
    assert publication["memo_text"].startswith("# 每日宏观 SPY 研判")

    assert second.notes["publication"] == "unchanged"
    assert second.notes["model_calls"] == 0
    assert second.notes["publication_rows_written"] == 0
    assert publication_count == 1
    assert agent.calls == 1

    assert matured_writes == 2
    assert [(row["horizon_sessions"], row["target_session_date"]) for row in outcomes] == [
        (5, target_5),
        (20, target_20),
    ]
    assert outcomes[0]["start_close"] == 625.10
    assert outcomes[0]["target_close"] == 630.00
    assert outcomes[1]["target_close"] == 650.00
    assert judgment_after_outcome["judgment_json"] == publication["judgment_json"]
    assert judgment_after_outcome["memo_text"] == publication["memo_text"]
    assert typed_read.state == "current"
    assert typed_read.publication is not None
    assert typed_read.publication.evidence_pack.pack_hash == publication["evidence_pack_hash"]
    assert [outcome.horizon_sessions for outcome in typed_read.publication.outcomes] == [5, 20]


class _FakeAgent:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.calls = 0

    async def analyze(self, evidence_pack: MacroEvidencePack) -> MacroAgentAnalysis:
        assert not self.conn.in_transaction
        self.calls += 1
        ref = next(iter(evidence_pack.evidence_refs))
        required_no_call = set(evidence_pack.health.no_call_horizons)
        judgment = DailyMacroJudgment.model_validate(
            {
                "experimental_marker": "experimental_shadow_research",
                "session_date": evidence_pack.session_date.isoformat(),
                "market_cutoff_ms": evidence_pack.market_cutoff_ms,
                "data_health": "degraded" if evidence_pack.health.status.value == "degraded" else "ready",
                "macro_state": "现有 point-in-time 证据不足以形成方向优势。",
                "pressures": [
                    {
                        "axis": "growth",
                        "state": "unclear",
                        "mechanism": "增长证据不足，不能推导确定方向。",
                        "evidence_refs": [ref],
                    }
                ],
                "spy_5d": {
                    "horizon_sessions": 5,
                    "direction": "no_call" if 5 in required_no_call else "range",
                    "thesis": "短期证据不足。",
                    "evidence_refs": [ref],
                },
                "spy_20d": {
                    "horizon_sessions": 20,
                    "direction": "no_call" if 20 in required_no_call else "range",
                    "thesis": "中期证据不足。",
                    "evidence_refs": [ref],
                },
                "counterevidence": [{"statement": "只有 SPY 收盘事实可用。", "evidence_refs": [ref]}],
                "audit_versions": {
                    "evidence_pack_hash": evidence_pack.pack_hash,
                    "schema_version": "daily_macro_judgment_v1",
                    "prompt_version": "macro_analyst_v1",
                    "workflow_version": "deepagents_analyst_reviewer_v1",
                },
            }
        )
        return MacroAgentAnalysis(
            judgment=judgment,
            reviewer=ReviewerResult(disposition="pass"),
            audit={
                "runtime": "fake-publication-seam",
                "native_task_calls": 1,
                "reviewer_dispositions": ["pass"],
            },
            model_name="fake-model",
            prompt_version="macro_analyst_v1",
            workflow_version="deepagents_analyst_reviewer_v1",
        )


def _worker(conn, *, agent: _FakeAgent) -> DailyMacroJudgmentWorker:
    return DailyMacroJudgmentWorker(
        settings=DailyMacroJudgmentWorkerSettings(
            enabled=True,
            interval_seconds=0,
            settle_delay_seconds=30 * 60,
            statement_timeout_seconds=120,
            lease_ms=600_000,
            retry_ms=1,
            max_attempts=3,
            lookback_days=1095,
            limit_per_series=800,
            news_limit=24,
            outcome_batch_size=32,
            model="fake-model",
            model_timeout_seconds=10,
            max_tokens=1000,
        ),
        db=_SingleConnectionDB(conn),
        telemetry=SimpleNamespace(),
        agent=agent,
        clock_ms=lambda: NOW_MS,
    )


class _SingleConnectionDB:
    def __init__(self, conn) -> None:
        self.conn = conn

    def worker_session(
        self,
        _name: str,
        *,
        statement_timeout_seconds: float,
    ) -> AbstractContextManager:
        assert statement_timeout_seconds == 120
        return repository_session_for_connection(self.conn)


def _seed_spy(conn, *, session_date: date, close: float, ingested_at_ms: int) -> None:
    conn.execute(
        """
        INSERT INTO macro_observations(
          observation_id, source_name, concept_key, series_key, source_priority,
          observed_at, value_numeric, unit, frequency, data_quality, source_ts,
          raw_payload_json, ingested_at_ms, fact_payload_hash
        )
        VALUES (%s, 'test', 'asset:spy', 'test:SPY', 1, %s, %s, 'price',
                'daily', 'ok', %s, '{}'::jsonb, %s, %s)
        """,
        (
            f"spy:{session_date.isoformat()}",
            session_date,
            close,
            session_date.isoformat(),
            ingested_at_ms,
            f"hash:{session_date.isoformat()}",
        ),
    )
    conn.commit()
