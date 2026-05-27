from __future__ import annotations

from pathlib import Path

import pytest

from gmgn_twitter_intel.app.runtime.worker_manifest import all_worker_manifests

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"


@pytest.mark.architecture
def test_no_runtime_compatibility_fallbacks_for_agent_contracts() -> None:
    source = (SRC / "domains/pulse_lab/services/pulse_candidate_job_service.py").read_text()

    assert "DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT" not in source
    assert "client.model" not in source
    assert "fallback" not in source.lower()


@pytest.mark.architecture
def test_macro_surfaces_do_not_read_control_plane_runs_as_product_truth() -> None:
    paths = (
        SRC / "app/surfaces/api/routes_macro.py",
        SRC / "app/surfaces/cli/commands/macro.py",
        SRC / "domains/macro_intel/services/macro_module_views.py",
    )
    forbidden = (
        "latest_macro_sync_run",
        "latest_import_run",
        "latest_sync_run",
        "macro_observations_max_observed_at",
    )

    for path in paths:
        source = path.read_text()
        for token in forbidden:
            assert token not in source


@pytest.mark.architecture
def test_token_case_market_live_uses_durable_ticks_only() -> None:
    paths = (
        SRC / "domains/token_intel/read_models/token_case_service.py",
        SRC / "domains/token_intel/read_models/search_inspect_service.py",
        SRC / "app/surfaces/api/routes_search.py",
    )

    for path in paths:
        source = path.read_text()
        assert "live_price_gateway" not in source
        assert ".snapshot(" not in source


@pytest.mark.architecture
def test_manifest_classifies_cache_and_delivery_without_product_fact_drift() -> None:
    manifests = {manifest.name: manifest for manifest in all_worker_manifests()}

    live_price_gateway = manifests["live_price_gateway"]
    assert live_price_gateway.input_contract == ("token_capture_tier", "market_ticks")
    assert live_price_gateway.writes_facts == ()
    assert live_price_gateway.writes_read_models == ()
    assert live_price_gateway.writes_control_plane == ()
    assert live_price_gateway.wakes_out == ()

    notification_rule = manifests["notification_rule"]
    assert notification_rule.writes_facts == ("notifications",)
    assert "notification_deliveries" in notification_rule.writes_control_plane

    notification_delivery = manifests["notification_delivery"]
    assert notification_delivery.writes_facts == ()
    assert notification_delivery.writes_control_plane == ("notification_deliveries",)
