from __future__ import annotations

import pytest

from parallax.domains.token_intel.interfaces import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    TOKEN_RADAR_FACTOR_FAMILIES,
)
from parallax.domains.token_intel.repositories.token_factor_evaluation_repository import (
    TokenFactorEvaluationRepository,
)
from parallax.domains.token_intel.services.token_factor_evaluation import settle_token_factor_scores


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
            market_key("a"): (100.0, 90.0),
            market_key("b"): (100.0, 120.0),
            market_key("c"): (100.0, 150.0),
            market_key("d"): (100.0, None),
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
    max_lag_ms = 24 * 60 * 60 * 1000
    assert repos.market_ticks.latest_calls == [
        {"target_type": "chain_token", "target_id": market_target_id("a"), "at_ms": base_ms, "max_lag_ms": max_lag_ms},
        {"target_type": "chain_token", "target_id": market_target_id("b"), "at_ms": base_ms, "max_lag_ms": max_lag_ms},
        {"target_type": "chain_token", "target_id": market_target_id("c"), "at_ms": base_ms, "max_lag_ms": max_lag_ms},
        {"target_type": "chain_token", "target_id": market_target_id("d"), "at_ms": base_ms, "max_lag_ms": max_lag_ms},
    ]
    assert repos.market_ticks.bounded_exit_calls == [
        {
            "target_type": "chain_token",
            "target_id": market_target_id("a"),
            "start_ms": base_ms + horizon_ms,
            "end_ms": base_ms + horizon_ms + 1,
        },
        {
            "target_type": "chain_token",
            "target_id": market_target_id("b"),
            "start_ms": base_ms + horizon_ms,
            "end_ms": base_ms + horizon_ms + 1,
        },
        {
            "target_type": "chain_token",
            "target_id": market_target_id("c"),
            "start_ms": base_ms + horizon_ms,
            "end_ms": base_ms + horizon_ms + 1,
        },
        {
            "target_type": "chain_token",
            "target_id": market_target_id("d"),
            "start_ms": base_ms + horizon_ms,
            "end_ms": base_ms + horizon_ms + 1,
        },
    ]


def test_settle_token_factor_scores_requires_formal_rank_score_without_zero_bucket():
    base_ms = 1_700_000_000_000
    row = radar_row("bad", score=10, computed_at_ms=base_ms)
    del row["factor_snapshot_json"]["composite"]["rank_score"]
    repos = FakeRepos(rows=[row], prices={market_key("bad"): (100.0, 120.0)})

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.composite\.rank_score is required"):
        settle_token_factor_scores(
            repos=repos,
            horizon="1h",
            window="1h",
            scope="all",
            generated_at_ms=base_ms + 60 * 60 * 1000 + 1,
            limit=100,
        )

    assert repos.token_factor_evaluations.upserts == []
    assert repos.market_ticks.latest_calls == []
    assert repos.market_ticks.bounded_exit_calls == []


def test_settle_token_factor_scores_requires_formal_subject_identity_without_row_fallback():
    base_ms = 1_700_000_000_000
    row = {
        **radar_row("bad-subject", score=10, computed_at_ms=base_ms),
        "target_type": "Asset",
        "target_id": "asset:bad-subject",
    }
    del row["factor_snapshot_json"]["subject"]["target_id"]
    repos = FakeRepos(rows=[row], prices={market_key("bad-subject"): (100.0, 120.0)})

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.subject\.target_id is required"):
        settle_token_factor_scores(
            repos=repos,
            horizon="1h",
            window="1h",
            scope="all",
            generated_at_ms=base_ms + 60 * 60 * 1000 + 1,
            limit=100,
        )

    assert repos.token_factor_evaluations.upserts == []
    assert repos.market_ticks.latest_calls == []
    assert repos.market_ticks.bounded_exit_calls == []


@pytest.mark.parametrize(
    ("subject_type", "subject_id", "prices"),
    (
        pytest.param(
            "chain_token",
            "eip155:1:0xlegacy-chain",
            {("chain_token", "eip155:1:0xlegacy-chain"): (100.0, 120.0)},
            id="chain-token",
        ),
        pytest.param(
            "cex_symbol",
            "binance:BTCUSDT",
            {("cex_symbol", "binance:BTCUSDT"): (100.0, 120.0)},
            id="cex-symbol",
        ),
    ),
)
def test_settle_token_factor_scores_rejects_direct_market_tick_subject_types_without_legacy_passthrough(
    subject_type,
    subject_id,
    prices,
):
    base_ms = 1_700_000_000_000
    row = radar_row("legacy-subject", score=70, computed_at_ms=base_ms)
    row["factor_snapshot_json"]["subject"] = {
        "target_type": subject_type,
        "target_id": subject_id,
    }
    repos = FakeRepos(rows=[row], prices=prices)

    with pytest.raises(ValueError, match=r"factor_snapshot_json\.subject\.target_type is invalid"):
        settle_token_factor_scores(
            repos=repos,
            horizon="1h",
            window="1h",
            scope="all",
            generated_at_ms=base_ms + 60 * 60 * 1000 + 1,
            limit=100,
        )

    assert repos.token_factor_evaluations.upserts == []
    assert repos.market_ticks.latest_calls == []
    assert repos.market_ticks.bounded_exit_calls == []


@pytest.mark.parametrize(
    ("remove_field", "alias_field", "alias_value"),
    (
        pytest.param("chain", "chain_id", "eip155:1", id="chain-id-alias"),
        pytest.param("address", "asset_address", "0xlegacyasset", id="asset-address-alias"),
    ),
)
def test_settle_token_factor_scores_requires_asset_chain_and_address_without_legacy_aliases(
    remove_field,
    alias_field,
    alias_value,
):
    base_ms = 1_700_000_000_000
    row = radar_row("legacyasset", score=70, computed_at_ms=base_ms)
    subject = row["factor_snapshot_json"]["subject"]
    subject[alias_field] = alias_value
    del subject[remove_field]
    repos = FakeRepos(rows=[row], prices={market_key("legacyasset"): (100.0, 120.0)})

    result = settle_token_factor_scores(
        repos=repos,
        horizon="1h",
        window="1h",
        scope="all",
        generated_at_ms=base_ms + 60 * 60 * 1000 + 1,
        limit=100,
    )

    diagnostics = repos.token_factor_evaluations.upserts[0]["diagnostics_json"]
    assert result["settled_count"] == 0
    assert diagnostics["unsettled_reasons"] == {"missing_market_target": 1}
    assert repos.market_ticks.latest_calls == []
    assert repos.market_ticks.bounded_exit_calls == []


def test_settle_token_factor_scores_uses_snapshot_provenance_time_without_row_timestamp_fallback():
    base_ms = 1_700_000_000_000
    horizon_ms = 60 * 60 * 1000
    row = radar_row("time", score=45, computed_at_ms=base_ms)
    del row["computed_at_ms"]
    repos = FakeRepos(rows=[row], prices={market_key("time"): (100.0, 125.0)})

    result = settle_token_factor_scores(
        repos=repos,
        horizon="1h",
        window="1h",
        scope="all",
        generated_at_ms=base_ms + horizon_ms + 1,
        limit=100,
    )

    assert result["settled_count"] == 1
    assert repos.market_ticks.latest_calls == [
        {
            "target_type": "chain_token",
            "target_id": market_target_id("time"),
            "at_ms": base_ms,
            "max_lag_ms": 24 * 60 * 60 * 1000,
        }
    ]
    assert repos.market_ticks.bounded_exit_calls == [
        {
            "target_type": "chain_token",
            "target_id": market_target_id("time"),
            "start_ms": base_ms + horizon_ms,
            "end_ms": base_ms + horizon_ms + 1,
        }
    ]
    by_label = {summary["bucket_label"]: summary for summary in repos.token_factor_evaluations.upserts}
    assert by_label["40-59"]["sample_start_ms"] == base_ms
    assert by_label["40-59"]["sample_end_ms"] == base_ms


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
            market_key("a"): (100.0, 110.0),
            market_key("b"): (100.0, 120.0),
            market_key("c"): (100.0, 130.0),
            market_key("d"): (100.0, 130.0),
            market_key("e"): (100.0, 120.0),
            market_key("f"): (100.0, 110.0),
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


def test_settle_token_factor_scores_records_family_rank_ic_diagnostics():
    base_ms = 1_700_000_000_000
    horizon_ms = 60 * 60 * 1000
    rows = [
        radar_row(
            "a",
            score=20,
            computed_at_ms=base_ms,
            family_scores={
                "social_heat": 10,
                "social_propagation": 90,
                "semantic_catalyst": 40,
                "timing_risk": 0,
            },
        ),
        radar_row(
            "b",
            score=40,
            computed_at_ms=base_ms,
            family_scores={
                "social_heat": 50,
                "social_propagation": 50,
                "semantic_catalyst": 60,
                "timing_risk": 0,
            },
        ),
        radar_row(
            "c",
            score=60,
            computed_at_ms=base_ms,
            family_scores={
                "social_heat": 90,
                "social_propagation": 10,
                "semantic_catalyst": 80,
                "timing_risk": 0,
            },
        ),
    ]
    repos = FakeRepos(
        rows=rows,
        prices={
            market_key("a"): (100.0, 90.0),
            market_key("b"): (100.0, 100.0),
            market_key("c"): (100.0, 110.0),
        },
    )

    settle_token_factor_scores(
        repos=repos,
        horizon="1h",
        window="1h",
        scope="all",
        generated_at_ms=base_ms + horizon_ms + 1,
        limit=100,
    )

    diagnostics = repos.token_factor_evaluations.upserts[0]["diagnostics_json"]
    assert set(diagnostics["family_rank_ic"]) == set(TOKEN_RADAR_FACTOR_FAMILIES)
    assert set(diagnostics["family_coverage"]) == set(TOKEN_RADAR_FACTOR_FAMILIES)
    assert diagnostics["family_rank_ic"]["social_heat"] == pytest.approx(1.0)
    assert diagnostics["family_rank_ic"]["social_propagation"] == pytest.approx(-1.0)
    assert diagnostics["family_rank_ic"]["timing_risk"] is None
    assert diagnostics["family_coverage"]["social_heat"] == 1.0
    assert diagnostics["family_coverage"]["social_propagation"] == 1.0
    assert diagnostics["family_coverage"]["semantic_catalyst"] == 1.0
    assert diagnostics["family_coverage"]["timing_risk"] == 1.0


def test_settle_token_factor_scores_reads_family_scores_from_formal_families_without_composite_alias():
    base_ms = 1_700_000_000_000
    horizon_ms = 60 * 60 * 1000
    rows = [
        radar_row(
            "a",
            score=20,
            computed_at_ms=base_ms,
            family_scores={
                "social_heat": 10,
                "social_propagation": 90,
                "semantic_catalyst": 40,
                "timing_risk": 0,
            },
        ),
        radar_row(
            "b",
            score=40,
            computed_at_ms=base_ms,
            family_scores={
                "social_heat": 50,
                "social_propagation": 50,
                "semantic_catalyst": 60,
                "timing_risk": 0,
            },
        ),
        radar_row(
            "c",
            score=60,
            computed_at_ms=base_ms,
            family_scores={
                "social_heat": 90,
                "social_propagation": 10,
                "semantic_catalyst": 80,
                "timing_risk": 0,
            },
        ),
    ]
    for row in rows:
        del row["factor_snapshot_json"]["composite"]["family_scores"]
    repos = FakeRepos(
        rows=rows,
        prices={
            market_key("a"): (100.0, 90.0),
            market_key("b"): (100.0, 100.0),
            market_key("c"): (100.0, 110.0),
        },
    )

    settle_token_factor_scores(
        repos=repos,
        horizon="1h",
        window="1h",
        scope="all",
        generated_at_ms=base_ms + horizon_ms + 1,
        limit=100,
    )

    diagnostics = repos.token_factor_evaluations.upserts[0]["diagnostics_json"]
    assert diagnostics["family_rank_ic"]["social_heat"] == pytest.approx(1.0)
    assert diagnostics["family_rank_ic"]["social_propagation"] == pytest.approx(-1.0)
    assert diagnostics["family_coverage"]["social_heat"] == 1.0
    assert diagnostics["family_coverage"]["social_propagation"] == 1.0


def test_settle_token_factor_scores_does_not_fallback_to_dropped_target_json_for_cex_market_target():
    base_ms = 1_700_000_000_000
    horizon_ms = 60 * 60 * 1000
    row = {
        "row_id": "row:btc",
        "window": "1h",
        "scope": "all",
        "target_type": "CexToken",
        "target_id": "cex_token:BTC",
        "computed_at_ms": base_ms,
        "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "target_json": {
            "provider": "binance",
            "native_market_id": "BTCUSDT",
        },
        "factor_snapshot_json": {
            "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
            "subject": {
                "target_type": "CexToken",
                "target_id": "cex_token:BTC",
                "symbol": "BTC",
                "target_market_type": "cex",
            },
            "market": {
                "event_anchor": None,
                "decision_latest": {
                    "provider": "binance",
                    "price_usd": 70_000.0,
                },
                "readiness": _market_readiness(),
            },
            "families": _factor_families(),
            "gates": {
                "eligible_for_high_alert": False,
                "blocked_reasons": [],
                "risk_reasons": [],
                "max_decision": "high_alert",
            },
            "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
            "normalization": {},
            "composite": {"rank_score": 80, "family_scores": {}, "recommended_decision": "high_alert"},
            "provenance": {"source_event_ids": ["event-btc"], "computed_at_ms": base_ms},
        },
    }
    repos = FakeRepos(rows=[row], prices={("cex_symbol", "binance:BTCUSDT"): (100.0, 120.0)})

    result = settle_token_factor_scores(
        repos=repos,
        horizon="1h",
        window="1h",
        scope="all",
        generated_at_ms=base_ms + horizon_ms + 1,
        limit=100,
    )

    diagnostics = repos.token_factor_evaluations.upserts[0]["diagnostics_json"]
    assert result["settled_count"] == 0
    assert diagnostics["unsettled_reasons"] == {"missing_market_target": 1}
    assert repos.market_ticks.latest_calls == []
    assert repos.market_ticks.bounded_exit_calls == []


def test_settle_token_factor_scores_requires_cex_provider_in_snapshot_subject_without_market_context_fallback():
    base_ms = 1_700_000_000_000
    horizon_ms = 60 * 60 * 1000
    row = cex_radar_row("btc", computed_at_ms=base_ms)
    del row["factor_snapshot_json"]["subject"]["provider"]
    repos = FakeRepos(rows=[row], prices={("cex_symbol", "binance:BTCUSDT"): (100.0, 120.0)})

    result = settle_token_factor_scores(
        repos=repos,
        horizon="1h",
        window="1h",
        scope="all",
        generated_at_ms=base_ms + horizon_ms + 1,
        limit=100,
    )

    diagnostics = repos.token_factor_evaluations.upserts[0]["diagnostics_json"]
    assert result["settled_count"] == 0
    assert diagnostics["unsettled_reasons"] == {"missing_market_target": 1}
    assert repos.market_ticks.latest_calls == []
    assert repos.market_ticks.bounded_exit_calls == []


def test_settle_token_factor_scores_requires_cex_native_market_id_without_instrument_alias():
    base_ms = 1_700_000_000_000
    horizon_ms = 60 * 60 * 1000
    row = cex_radar_row("btc", computed_at_ms=base_ms)
    row["factor_snapshot_json"]["subject"]["instrument"] = "BTCUSDT"
    del row["factor_snapshot_json"]["subject"]["native_market_id"]
    repos = FakeRepos(rows=[row], prices={("cex_symbol", "binance:BTCUSDT"): (100.0, 120.0)})

    result = settle_token_factor_scores(
        repos=repos,
        horizon="1h",
        window="1h",
        scope="all",
        generated_at_ms=base_ms + horizon_ms + 1,
        limit=100,
    )

    diagnostics = repos.token_factor_evaluations.upserts[0]["diagnostics_json"]
    assert result["settled_count"] == 0
    assert diagnostics["unsettled_reasons"] == {"missing_market_target": 1}
    assert repos.market_ticks.latest_calls == []
    assert repos.market_ticks.bounded_exit_calls == []


def test_evaluation_repository_does_not_read_retired_snapshot_audit_for_settlement():
    conn = FakeConn(rows=[{"row_id": "row:a"}])

    rows = TokenFactorEvaluationRepository(conn).historical_radar_rows(
        factor_version=TOKEN_FACTOR_SNAPSHOT_VERSION,
        window="1h",
        scope="all",
        horizon_ms=3_600_000,
        generated_at_ms=1_700_003_600_001,
        limit=50,
    )

    assert rows == []
    assert conn.sql == ""
    assert conn.params == ()


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


def test_evaluation_repository_upsert_requires_connection_transaction_before_sql_when_committing():
    conn = NoTransactionConn(row=None)

    with pytest.raises(RuntimeError, match="token_factor_evaluation_repository_transaction_required"):
        TokenFactorEvaluationRepository(conn).upsert_score_evaluation(
            _summary(bucket_label="0-19", bucket_min=0, bucket_max=19)
        )

    assert conn.sqls == []


def test_evaluation_repository_commit_owned_upsert_uses_connection_transaction_without_manual_commit():
    conn = FakeConn(row=None)

    TokenFactorEvaluationRepository(conn).upsert_score_evaluation(
        _summary(bucket_label="0-19", bucket_min=0, bucket_max=19)
    )

    assert "INSERT INTO token_score_evaluations" in conn.sql
    assert conn.sql_transaction_depths == [1]
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


def radar_row(suffix: str, *, score: int, computed_at_ms: int, family_scores: dict | None = None) -> dict:
    return {
        "row_id": f"row:{suffix}",
        "window": "1h",
        "scope": "all",
        "computed_at_ms": computed_at_ms,
        "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "factor_snapshot_json": {
            "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
            "subject": {
                "target_type": "Asset",
                "target_id": f"asset:{suffix}",
                "symbol": suffix.upper(),
                "target_market_type": "dex",
                "chain": "eip155:1",
                "address": f"0x{suffix}",
            },
            "market": {
                "event_anchor": None,
                "decision_latest": None,
                "readiness": _market_readiness(),
            },
            "families": _factor_families(family_scores=family_scores),
            "gates": {
                "eligible_for_high_alert": score >= 70,
                "blocked_reasons": [],
                "risk_reasons": [],
                "max_decision": "high_alert",
            },
            "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
            "normalization": {},
            "composite": {
                "rank_score": score,
                "family_scores": family_scores or {},
                "recommended_decision": "high_alert" if score >= 70 else "watch" if score >= 35 else "discard",
            },
            "provenance": {"source_event_ids": [f"event:{suffix}"], "computed_at_ms": computed_at_ms},
        },
    }


def cex_radar_row(suffix: str, *, computed_at_ms: int, score: int = 80) -> dict:
    symbol = suffix.upper()
    native_market_id = f"{symbol}USDT"
    return {
        "row_id": f"row:{suffix}",
        "window": "1h",
        "scope": "all",
        "computed_at_ms": computed_at_ms,
        "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "factor_snapshot_json": {
            "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
            "subject": {
                "target_type": "CexToken",
                "target_id": f"cex_token:{symbol}",
                "symbol": symbol,
                "target_market_type": "cex",
                "provider": "binance",
                "native_market_id": native_market_id,
            },
            "market": {
                "event_anchor": None,
                "decision_latest": {
                    "provider": "binance",
                    "price_usd": 70_000.0,
                },
                "readiness": _market_readiness(),
            },
            "families": _factor_families(),
            "gates": {
                "eligible_for_high_alert": True,
                "blocked_reasons": [],
                "risk_reasons": [],
                "max_decision": "high_alert",
            },
            "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
            "normalization": {},
            "composite": {
                "rank_score": score,
                "family_scores": {},
                "recommended_decision": "high_alert",
            },
            "provenance": {"source_event_ids": [f"event:{suffix}"], "computed_at_ms": computed_at_ms},
        },
    }


def _market_readiness() -> dict:
    return {
        "anchor_status": "ready",
        "latest_status": "live",
        "dex_floor_status": "ready",
        "missing_fields": [],
        "stale_fields": [],
    }


def _factor_families(*, family_scores: dict | None = None) -> dict:
    scores = family_scores or {}
    return {family: _factor_family(scores.get(family, 0.0)) for family in TOKEN_RADAR_FACTOR_FAMILIES}


def _factor_family(score: object) -> dict:
    return {
        "raw_score": score,
        "score": score,
        "weight": 1.0,
        "data_health": "ready",
        "facts": {},
        "factors": {},
    }


def market_key(suffix: str) -> tuple[str, str]:
    return ("chain_token", market_target_id(suffix))


def market_target_id(suffix: str) -> str:
    return f"eip155:1:0x{suffix}"


class FakeRepos:
    def __init__(self, *, rows, prices):
        self.token_factor_evaluations = FakeEvaluationRepository(rows)
        self.market_ticks = FakeMarketTicks(prices)


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


class FakeMarketTicks:
    def __init__(self, prices):
        self.prices = prices
        self.latest_calls = []
        self.bounded_exit_calls = []

    def latest_at_or_before(self, *, target_type, target_id, at_ms, max_lag_ms):
        self.latest_calls.append(
            {"target_type": target_type, "target_id": target_id, "at_ms": at_ms, "max_lag_ms": max_lag_ms}
        )
        entry, _ = self.prices.get((target_type, target_id), (None, None))
        if entry is None:
            return None
        return {"tick_id": f"entry:{target_id}", "observed_at_ms": at_ms, "price_usd": entry}

    def latest_price_for_subject_at_or_before(self, **kwargs):
        raise AssertionError("settlement must use latest_at_or_before")

    def first_for_subject_at_or_after(self, **kwargs):
        raise AssertionError("settlement must use first_between")

    def first_between(self, *, target_type, target_id, start_ms, end_ms):
        self.bounded_exit_calls.append(
            {
                "target_type": target_type,
                "target_id": target_id,
                "start_ms": start_ms,
                "end_ms": end_ms,
            }
        )
        _, exit_price = self.prices.get((target_type, target_id), (None, None))
        if exit_price is None:
            return None
        return {"tick_id": f"exit:{target_id}", "observed_at_ms": start_ms, "price_usd": exit_price}


class FakeTransaction:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.transaction_enter_count += 1
        self.conn.transaction_depth += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.conn.transaction_depth -= 1
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
        self.transaction_depth = 0
        self.sql_transaction_depths = []

    def execute(self, sql, params=None):
        self.sql = str(sql)
        self.sqls.append(self.sql)
        self.sql_transaction_depths.append(self.transaction_depth)
        self.params = params or ()
        return self

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows

    def commit(self):
        self.commit_count += 1
        raise AssertionError("manual commit is not allowed in repository tests")

    def transaction(self):
        return FakeTransaction(self)


class NoTransactionConn(FakeConn):
    transaction = None
