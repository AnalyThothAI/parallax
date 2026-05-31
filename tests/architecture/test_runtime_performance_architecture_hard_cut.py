from __future__ import annotations

import ast
import re
from pathlib import Path

from parallax.app.runtime.worker_manifest import all_worker_manifests

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_token_radar_old_batch_query_is_deleted() -> None:
    old_query = SRC / "domains/token_intel/queries" / ("token_radar_target" + "_feature_query.py")
    assert not old_query.exists()


def test_token_radar_projection_does_not_call_old_hot_sql() -> None:
    text = _read("src/parallax/domains/token_intel/services/token_radar_projection.py")
    module = ast.parse(text)

    old_imports: list[str] = []
    old_calls: list[str] = []
    old_module = "parallax.domains.token_intel.queries." + "token_radar_target" + "_feature_query"
    old_method = "source_rows" + "_for_requests"
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module == old_module:
            old_imports.extend(alias.name for alias in node.names)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == old_method:
            old_calls.append(node.func.attr)

    assert ("TokenRadarTarget" + "FeatureBatchQuery") not in old_imports
    assert old_calls == []


def test_token_radar_rank_source_has_single_owner_manifest_entry() -> None:
    owners = [
        manifest.name
        for manifest in all_worker_manifests()
        if "token_radar_rank_source_events" in manifest.writes_read_models
    ]
    assert owners == ["token_radar_projection"]


def test_macro_projection_refresh_is_current_only_with_source_signature() -> None:
    repo = _read("src/parallax/domains/macro_intel/repositories/macro_intel_repository.py")
    replace_current_pattern = re.compile(
        r"DELETE\s+FROM\s+macro_observation_series_rows\s+WHERE\s+projection_version\s*=\s*%s\s*(?=\"\"\")",
        re.IGNORECASE,
    )

    assert "macro_observation_series_active_generation" not in repo
    assert "macro_observation_series_generations" not in repo
    assert "_generation_id" not in repo
    assert "_series_source_signature" in repo
    assert "macro_observation_series_publication_state" in repo
    assert replace_current_pattern.search(repo) is None


def test_news_fetch_validates_provider_contract_before_reconcile() -> None:
    worker = _read("src/parallax/domains/news_intel/runtime/news_fetch_worker.py")
    validate_at = worker.index("validate_news_provider_contract")
    reconcile_at = worker.index("reconcile_configured_sources")
    assert validate_at < reconcile_at


def test_opennews_client_runtime_reports_rest_transport_without_fetch_mode_surface() -> None:
    client = _read("src/parallax/integrations/news_feeds/opennews_client.py")

    assert '"transport": "rest"' in client
    assert '"fetch_mode": "rest"' not in client
    assert "_reject_removed_websocket_policy(policy)" in client


def test_opennews_provider_signal_never_reenters_news_brief_input_hot_path() -> None:
    policy = "needs_news_item_agent_brief"
    hot_path_files = (
        "src/parallax/domains/news_intel/runtime/news_fetch_worker.py",
        "src/parallax/domains/news_intel/runtime/news_item_process_worker.py",
        "src/parallax/app/runtime/projection_dirty_targets.py",
    )

    for path in hot_path_files:
        assert policy in _read(path), f"{path} must apply the provider-signal brief policy"
