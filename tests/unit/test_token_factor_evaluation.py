from __future__ import annotations

import pytest

from gmgn_twitter_intel.domains.asset_market.repositories.price_observation_repository import PriceObservationRepository
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_FACTOR_SNAPSHOT_VERSION
from gmgn_twitter_intel.domains.token_intel.repositories.token_factor_evaluation_repository import (
    TokenFactorEvaluationRepository,
)
from gmgn_twitter_intel.domains.token_intel.services.token_factor_evaluation import settle_token_factor_scores


def test_settle_token_factor_scores_writes_deterministic_bucket_summaries():
    base_ms = 1_700_000_000_000
    horizon_ms = 60 * 60 * 1000
    rows = [
        radar_row("a", score=10, computed_at_ms=base_ms),
        radar_row("b", score=30, computed_at_ms=base_ms),
        radar_row("c", score=70, computed_at_ms=base_ms),
        radar_row("d", score=90, computed_at_ms=base_ms),
    ]
    repos = FakeRepos(
        rows=rows,
        prices={
            ("Asset", "asset:a"): (100.0, 90.0),
            ("Asset", "asset:b"): (100.0, 120.0),
            ("Asset", "asset:c"): (100.0, 150.0),
            ("Asset", "asset:d"): (100.0, None),
        },
    )

    result = settle_token_factor_scores(
        repos=repos,
        horizon="1h",
        window="1h",
        scope="all",
        generated_at_ms=base_ms + horizon_ms + 1,
        limit=100,
    )

    by_label = {summary["bucket_label"]: summary for summary in repos.token_factor_evaluations.upserts}
    assert repos.token_factor_evaluations.batch_call_count == 1
    assert repos.token_factor_evaluations.single_upsert_count == 0
    assert result["eligible_count"] == 4
    assert result["settled_count"] == 3
    assert result["unsettled_count"] == 1
    assert result["spearman_ic"] == pytest.approx(1.0)
    assert set(by_label) == {"0-19", "20-39", "40-59", "60-79", "80-100"}
    assert by_label["0-19"]["settled_count"] == 1
    assert by_label["0-19"]["directional_hit_rate"] == 0.0
    assert by_label["20-39"]["avg_actual_return"] == pytest.approx(0.2)
    assert by_label["60-79"]["directional_hit_rate"] == 1.0
    assert by_label["80-100"]["snapshot_count"] == 1
    assert by_label["80-100"]["settled_count"] == 0
    assert by_label["80-100"]["settlement_coverage"] == 0.0
    assert by_label["0-19"]["sample_start_ms"] == base_ms
    assert by_label["0-19"]["sample_end_ms"] == base_ms
    assert by_label["0-19"]["spearman_ic"] == pytest.approx(1.0)
    assert by_label["0-19"]["icir"] is None
    assert by_label["0-19"]["score_stddev"] == 0.0
    assert by_label["80-100"]["diagnostics_json"]["unsettled_reasons"] == {"missing_exit_price": 1}
    assert by_label["80-100"]["diagnostics_json"]["bucket_unsettled_reasons"] == {"missing_exit_price": 1}
    assert repos.price_observations.latest_price_calls == [
        {"subject_type": "Asset", "subject_id": "asset:a", "at_or_before_ms": base_ms},
        {"subject_type": "Asset", "subject_id": "asset:b", "at_or_before_ms": base_ms},
        {"subject_type": "Asset", "subject_id": "asset:c", "at_or_before_ms": base_ms},
        {"subject_type": "Asset", "subject_id": "asset:d", "at_or_before_ms": base_ms},
    ]
    assert repos.price_observations.bounded_exit_calls == [
        {
            "subject_type": "Asset",
            "subject_id": "asset:a",
            "at_or_after_ms": base_ms + horizon_ms,
            "at_or_before_ms": base_ms + horizon_ms + 1,
        },
        {
            "subject_type": "Asset",
            "subject_id": "asset:b",
            "at_or_after_ms": base_ms + horizon_ms,
            "at_or_before_ms": base_ms + horizon_ms + 1,
        },
        {
            "subject_type": "Asset",
            "subject_id": "asset:c",
            "at_or_after_ms": base_ms + horizon_ms,
            "at_or_before_ms": base_ms + horizon_ms + 1,
        },
        {
            "subject_type": "Asset",
            "subject_id": "asset:d",
            "at_or_after_ms": base_ms + horizon_ms,
            "at_or_before_ms": base_ms + horizon_ms + 1,
        },
    ]


def test_settle_token_factor_scores_computes_daily_icir_when_daily_ics_vary():
    base_ms = 1_700_000_000_000
    day_ms = 24 * 60 * 60 * 1000
    horizon_ms = 60 * 60 * 1000
    rows = [
        radar_row("a", score=10, computed_at_ms=base_ms),
        radar_row("b", score=30, computed_at_ms=base_ms),
        radar_row("c", score=70, computed_at_ms=base_ms),
        radar_row("d", score=10, computed_at_ms=base_ms + day_ms),
        radar_row("e", score=30, computed_at_ms=base_ms + day_ms),
        radar_row("f", score=70, computed_at_ms=base_ms + day_ms),
    ]
    repos = FakeRepos(
        rows=rows,
        prices={
            ("Asset", "asset:a"): (100.0, 110.0),
            ("Asset", "asset:b"): (100.0, 120.0),
            ("Asset", "asset:c"): (100.0, 130.0),
            ("Asset", "asset:d"): (100.0, 130.0),
            ("Asset", "asset:e"): (100.0, 120.0),
            ("Asset", "asset:f"): (100.0, 110.0),
        },
    )

    result = settle_token_factor_scores(
        repos=repos,
        horizon="1h",
        window="1h",
        scope="all",
        generated_at_ms=base_ms + day_ms + horizon_ms + 1,
        limit=100,
    )

    assert result["daily_ics"] == pytest.approx([1.0, -1.0])
    assert result["icir_daily"] == pytest.approx(0.0)


def test_price_exit_lookup_filters_null_price_usd():
    conn = FakeConn(row=None)

    result = PriceObservationRepository(conn).first_for_subject_at_or_after(
        subject_type="Asset",
        subject_id="asset:a",
        at_or_after_ms=1_700_000_000_000,
    )

    assert result is None
    assert "price_usd IS NOT NULL" in conn.sql
    assert conn.params == ("Asset", "asset:a", 1_700_000_000_000)


def test_bounded_price_exit_lookup_filters_null_price_usd_and_bounds_read_time():
    conn = FakeConn(row={"observation_id": "exit:a", "price_usd": 120.0})

    result = PriceObservationRepository(conn).first_price_for_subject_between(
        subject_type="Asset",
        subject_id="asset:a",
        at_or_after_ms=1_700_000_000_000,
        at_or_before_ms=1_700_003_600_000,
    )

    assert result == {"observation_id": "exit:a", "price_usd": 120.0}
    assert "price_usd IS NOT NULL" in conn.sql
    assert "observed_at_ms >= %s" in conn.sql
    assert "observed_at_ms <= %s" in conn.sql
    assert "ORDER BY observed_at_ms ASC, observation_id ASC" in conn.sql
    assert conn.params == ("Asset", "asset:a", 1_700_000_000_000, 1_700_003_600_000)


def test_price_entry_lookup_filters_null_price_usd():
    conn = FakeConn(row={"observation_id": "entry:a", "price_usd": 100.0})

    result = PriceObservationRepository(conn).latest_price_for_subject_at_or_before(
        subject_type="Asset",
        subject_id="asset:a",
        at_or_before_ms=1_700_000_000_000,
    )

    assert result == {"observation_id": "entry:a", "price_usd": 100.0}
    assert "price_usd IS NOT NULL" in conn.sql
    assert "observed_at_ms <= %s" in conn.sql
    assert "ORDER BY observed_at_ms DESC, observation_id DESC" in conn.sql
    assert conn.params == ("Asset", "asset:a", 1_700_000_000_000)


def test_evaluation_repository_selects_point_in_time_rows_for_settlement():
    conn = FakeConn(rows=[{"row_id": "row:a"}])

    rows = TokenFactorEvaluationRepository(conn).historical_radar_rows(
        factor_version=TOKEN_FACTOR_SNAPSHOT_VERSION,
        window="1h",
        scope="all",
        horizon_ms=3_600_000,
        generated_at_ms=1_700_003_600_001,
        limit=50,
    )

    assert rows == [{"row_id": "row:a"}]
    assert "computed_at_ms + %s <= %s" in conn.sql
    assert "ORDER BY computed_at_ms DESC, rank ASC, lane ASC, row_id ASC" in conn.sql
    assert conn.params == (TOKEN_FACTOR_SNAPSHOT_VERSION, "1h", "all", 3_600_000, 1_700_003_600_001, 50)


def test_evaluation_repository_upsert_persists_diagnostics_columns():
    conn = FakeConn(row=None)
    summary = {
        "horizon": "1h",
        "window": "1h",
        "scope": "all",
        "score_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "bucket_label": "20-39",
        "bucket_min": 20,
        "bucket_max": 39,
        "snapshot_count": 1,
        "settled_count": 1,
        "settlement_coverage": 1.0,
        "avg_actual_return": 0.2,
        "avg_abnormal_return": 0.2,
        "avg_normalized_outcome": 0.2,
        "directional_hit_rate": 1.0,
        "wilson_low": 0.0,
        "wilson_high": 1.0,
        "generated_at_ms": 1_700_000_000_000,
    }

    TokenFactorEvaluationRepository(conn).upsert_score_evaluation(summary, commit=False)

    assert "INSERT INTO token_score_evaluations" in conn.sql
    assert "sample_start_ms" in conn.sql
    assert "spearman_ic" in conn.sql
    assert "diagnostics_json" in conn.sql
    assert conn.params["bucket_label"] == "20-39"
    assert conn.params["diagnostics_json"].obj == {}


def test_evaluation_repository_batch_upsert_uses_transaction_once():
    conn = FakeConn(row=None)
    summaries = [
        _summary(bucket_label="0-19", bucket_min=0, bucket_max=19),
        _summary(bucket_label="20-39", bucket_min=20, bucket_max=39),
    ]

    TokenFactorEvaluationRepository(conn).upsert_score_evaluations(summaries)

    assert len([sql for sql in conn.sqls if "INSERT INTO token_score_evaluations" in sql]) == 2
    assert conn.transaction_enter_count == 1
    assert conn.transaction_exit_count == 1
    assert conn.commit_count == 0


def _summary(*, bucket_label: str, bucket_min: int, bucket_max: int) -> dict:
    return {
        "horizon": "1h",
        "window": "1h",
        "scope": "all",
        "score_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "bucket_label": bucket_label,
        "bucket_min": bucket_min,
        "bucket_max": bucket_max,
        "snapshot_count": 1,
        "settled_count": 1,
        "settlement_coverage": 1.0,
        "avg_actual_return": 0.2,
        "avg_abnormal_return": 0.2,
        "avg_normalized_outcome": 0.2,
        "directional_hit_rate": 1.0,
        "wilson_low": 0.0,
        "wilson_high": 1.0,
        "generated_at_ms": 1_700_000_000_000,
    }


def radar_row(suffix: str, *, score: int, computed_at_ms: int) -> dict:
    return {
        "row_id": f"row:{suffix}",
        "window": "1h",
        "scope": "all",
        "computed_at_ms": computed_at_ms,
        "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "factor_snapshot_json": {
            "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
            "subject": {"target_type": "Asset", "target_id": f"asset:{suffix}", "symbol": suffix.upper()},
            "families": {},
            "gates": {},
            "data_health": {},
            "normalization": {},
            "composite": {"rank_score": score},
            "provenance": {"computed_at_ms": computed_at_ms},
        },
    }


class FakeRepos:
    def __init__(self, *, rows, prices):
        self.token_factor_evaluations = FakeEvaluationRepository(rows)
        self.price_observations = FakePriceObservations(prices)


class FakeEvaluationRepository:
    def __init__(self, rows):
        self.rows = rows
        self.upserts = []
        self.batch_call_count = 0
        self.single_upsert_count = 0

    def historical_radar_rows(self, **kwargs):
        self.historical_call = dict(kwargs)
        return self.rows[: kwargs["limit"]]

    def upsert_score_evaluations(self, summaries):
        self.batch_call_count += 1
        self.upserts.extend(dict(summary) for summary in summaries)

    def upsert_score_evaluation(self, summary):
        self.single_upsert_count += 1
        raise AssertionError("settlement must batch upsert score evaluations")


class FakePriceObservations:
    def __init__(self, prices):
        self.prices = prices
        self.latest_price_calls = []
        self.bounded_exit_calls = []

    def latest_price_for_subject_at_or_before(self, *, subject_type, subject_id, at_or_before_ms):
        self.latest_price_calls.append(
            {"subject_type": subject_type, "subject_id": subject_id, "at_or_before_ms": at_or_before_ms}
        )
        entry, _ = self.prices.get((subject_type, subject_id), (None, None))
        if entry is None:
            return None
        return {"observation_id": f"entry:{subject_id}", "observed_at_ms": at_or_before_ms, "price_usd": entry}

    def latest_for_subject_at_or_before(self, *, subject_type, subject_id, at_or_before_ms):
        raise AssertionError("settlement must use latest_price_for_subject_at_or_before")

    def first_for_subject_at_or_after(self, *, subject_type, subject_id, at_or_after_ms):
        raise AssertionError("settlement must use first_price_for_subject_between")

    def first_price_for_subject_between(self, *, subject_type, subject_id, at_or_after_ms, at_or_before_ms):
        self.bounded_exit_calls.append(
            {
                "subject_type": subject_type,
                "subject_id": subject_id,
                "at_or_after_ms": at_or_after_ms,
                "at_or_before_ms": at_or_before_ms,
            }
        )
        _, exit_price = self.prices.get((subject_type, subject_id), (None, None))
        if exit_price is None:
            return None
        return {"observation_id": f"exit:{subject_id}", "observed_at_ms": at_or_after_ms, "price_usd": exit_price}


class FakeTransaction:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.transaction_enter_count += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.conn.transaction_exit_count += 1
        return False


class FakeConn:
    def __init__(self, *, row=None, rows=None):
        self.row = row
        self.rows = rows or []
        self.sql = ""
        self.sqls = []
        self.params = ()
        self.commit_count = 0
        self.transaction_enter_count = 0
        self.transaction_exit_count = 0

    def execute(self, sql, params=None):
        self.sql = str(sql)
        self.sqls.append(self.sql)
        self.params = params or ()
        return self

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows

    def commit(self):
        self.commit_count += 1

    def transaction(self):
        return FakeTransaction(self)
