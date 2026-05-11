from gmgn_twitter_intel.domains.token_intel.scoring import baseline_scoring


def test_baseline_v2_reports_ready_ewma_and_robust_surprise():
    baseline = baseline_scoring.token_baseline_v2(slot_counts=[2, 2, 3, 2, 3, 2], current_mentions=9)

    assert baseline["baseline_version"] == "token_baseline_v2"
    assert baseline["baseline_status"] == "ready"
    assert baseline["nonzero_sample_count"] == 6
    assert baseline["z_ewma"] > 1.0
    assert baseline["robust_z"] >= 6.0
    assert baseline["data_health"]["history_ready"] is True


def test_baseline_v2_robust_z_resists_single_historical_outlier():
    baseline = baseline_scoring.token_baseline_v2(slot_counts=[2, 2, 2, 2, 80, 2], current_mentions=8)

    assert baseline["baseline_status"] == "ready"
    assert baseline["robust_z"] >= 5.0
    assert baseline["z_ewma"] < baseline["robust_z"]


def test_baseline_v2_sparse_history_uses_new_burst_score():
    baseline = baseline_scoring.token_baseline_v2(slot_counts=[0, 0, 0, 0, 0, 0], current_mentions=4)

    assert baseline["baseline_status"] == "insufficient_history"
    assert baseline["sample_count"] == 6
    assert baseline["nonzero_sample_count"] == 0
    assert baseline["new_burst_score"] > 0
    assert baseline["z_ewma"] is None
    assert baseline["robust_z"] is None
    assert baseline["data_health"]["sparse_history"] is True
