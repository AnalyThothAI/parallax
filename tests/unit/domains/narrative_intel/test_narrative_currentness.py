from parallax.domains.narrative_intel.types.narrative_currentness import unsupported_admission_sentinel


def test_unsupported_admission_sentinel_is_missing_without_digest_semantics() -> None:
    snapshot = unsupported_admission_sentinel(
        target_type="Asset",
        target_id="asset-1",
        window="5m",
        scope="all",
        schema_version="narrative_intel_v1",
    )

    assert snapshot["status"] == "missing"
    assert snapshot["reason"] == "narrative_not_supported_for_window"
    assert snapshot["is_current"] is False
    assert snapshot["currentness"] == {
        "display_status": "unsupported_window",
        "reason": "narrative_not_supported_for_window",
    }
    assert "epoch_id" not in snapshot["currentness"]
    assert "semantic_coverage" not in snapshot
