from __future__ import annotations

import re
from pathlib import Path

import pytest

from parallax.app.runtime.worker_manifest import all_worker_manifests

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"

CANONICAL_LIFECYCLE_DOCS = (
    ROOT / "AGENTS.md",
    ROOT / "CLAUDE.md",
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "docs" / "CONTRACTS.md",
    ROOT / "docs" / "RELIABILITY.md",
    ROOT / "docs" / "WORKERS.md",
    ROOT / "docs" / "references" / "POSTGRES_PERFORMANCE.md",
    SRC / "domains" / "macro_intel" / "ARCHITECTURE.md",
    SRC / "domains" / "cex_market_intel" / "ARCHITECTURE.md",
)


@pytest.mark.architecture
def test_no_runtime_compatibility_fallbacks_for_agent_contracts() -> None:
    source = (SRC / "domains/pulse_lab/services/pulse_candidate_job_service.py").read_text()

    assert "DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT" not in source
    assert re.search(r"\bclient\.model\b", source) is None
    assert 'getattr(self.decision_client, "model"' not in source
    assert 'getattr(client, "model_for_lane", None)' not in source
    assert 'getattr(client, "_agent_gateway", None)' not in source
    assert "fallback" not in source.lower()

    pulse_provider_sources = "\n".join(
        (
            (SRC / "app/runtime/provider_wiring/model_execution.py").read_text(),
            (SRC / "integrations/model_execution/pulse_decision_agent_client.py").read_text(),
        )
    )
    assert "return self.model" not in pulse_provider_sources
    assert 'getattr(gateway, "model_for_lane", None)' not in pulse_provider_sources
    assert 'getattr(client, "model_for_lane", None)' not in pulse_provider_sources

    agent_worker_sources = "\n".join(
        (
            (SRC / "domains/narrative_intel/runtime/mention_semantics_worker.py").read_text(),
            (SRC / "domains/narrative_intel/runtime/token_discussion_digest_worker.py").read_text(),
            (SRC / "domains/news_intel/runtime/news_item_brief_worker.py").read_text(),
        )
    )
    assert "_fallback_request_audit" not in agent_worker_sources
    assert '"_client"' not in agent_worker_sources


@pytest.mark.architecture
def test_canonical_lifecycle_docs_do_not_republish_retired_runtime_contracts() -> None:
    retired_contract_tokens = (
        "cex_oi_radar_runs",
        "macro_observation_series_active_generation",
    )
    violations = []
    for path in CANONICAL_LIFECYCLE_DOCS:
        text = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(ROOT)} still mentions {token}" for token in retired_contract_tokens if token in text
        )

    assert violations == []


@pytest.mark.architecture
def test_active_superpower_docs_do_not_republish_retired_runtime_contracts() -> None:
    active_docs = list((ROOT / "docs/superpowers/specs/active").glob("*.md"))
    active_docs += list((ROOT / "docs/superpowers/plans/active").glob("*.md"))
    retired_contract_tokens = (
        "cex_oi_radar_runs",
        "macro_observation_series_active_generation",
        "active generation",
        "active-generation",
        "generation pointer",
        "generation pointers",
        "staging/generation",
    )
    violations = []
    for path in active_docs:
        text = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(ROOT)} still mentions {token}" for token in retired_contract_tokens if token in text
        )

    assert violations == []


@pytest.mark.architecture
def test_generated_docs_do_not_republish_retired_runtime_contracts() -> None:
    generated_docs = list((ROOT / "docs/generated").glob("**/*.md"))
    retired_contract_tokens = (
        "cex_oi_radar_runs",
        "macro_observation_series_active_generation",
    )
    violations = []
    for path in generated_docs:
        text = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(ROOT)} still mentions {token}" for token in retired_contract_tokens if token in text
        )

    assert violations == []


@pytest.mark.architecture
def test_cex_failure_attempts_do_not_clear_current_board_rows() -> None:
    worker_source = (SRC / "domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py").read_text()
    repository_source = (SRC / "domains/cex_market_intel/repositories/cex_oi_radar_repository.py").read_text()

    assert "record_attempt_failure" in worker_source
    assert 'status="failed"' not in worker_source
    assert "def record_attempt_failure" in repository_source
    failure_method = repository_source.split("def record_attempt_failure", maxsplit=1)[1].split(
        "def latest_board", maxsplit=1
    )[0]
    assert "DELETE FROM cex_oi_radar_rows" not in failure_method
    assert "current_published_at_ms = excluded.current_published_at_ms" not in failure_method


@pytest.mark.architecture
def test_agent_dirty_queue_claims_do_not_consume_business_attempts() -> None:
    paths = (SRC / "domains/news_intel/repositories/news_projection_dirty_target_repository.py",)
    for path in paths:
        source = path.read_text()
        claim_method = source.split("def claim_due", maxsplit=1)[1].split("def mark_done", maxsplit=1)[0]
        mark_error_method = source.split("def mark_error", maxsplit=1)[1].split("def queue_depth", maxsplit=1)[0]
        assert "attempt_count + 1" not in claim_method
        assert "attempt_increment" in mark_error_method

    worker_sources = "\n".join(((SRC / "domains/news_intel/runtime/news_item_brief_worker.py").read_text(),))
    assert "def _claim_owner" in worker_sources
    assert "retry_counts_attempt=False" in worker_sources


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
