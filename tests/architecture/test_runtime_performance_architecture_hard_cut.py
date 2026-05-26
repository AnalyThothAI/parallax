from __future__ import annotations

import ast
import re
from pathlib import Path

from gmgn_twitter_intel.app.runtime.worker_manifest import all_worker_manifests


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_token_radar_old_batch_query_is_deleted() -> None:
    old_query = SRC / "domains/token_intel/queries/token_radar_target_feature_query.py"
    assert not old_query.exists()


def test_token_radar_projection_does_not_call_old_hot_sql() -> None:
    text = _read("src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py")
    module = ast.parse(text)

    old_imports: list[str] = []
    old_calls: list[str] = []
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module == (
            "gmgn_twitter_intel.domains.token_intel.queries.token_radar_target_feature_query"
        ):
            old_imports.extend(alias.name for alias in node.names)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "source_rows_for_requests":
                old_calls.append(node.func.attr)

    assert "TokenRadarTargetFeatureBatchQuery" not in old_imports
    assert old_calls == []


def test_token_radar_rank_source_has_single_owner_manifest_entry() -> None:
    owners = [
        manifest.name
        for manifest in all_worker_manifests()
        if "token_radar_rank_source_events" in manifest.writes_read_models
    ]
    assert owners == ["token_radar_projection"]


def test_macro_projection_refresh_uses_generation_swap() -> None:
    repo = _read("src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py")
    assert "macro_observation_series_active_generation" in repo
    normalized = re.sub(r"\s+", " ", repo)
    delete_all_pattern = re.compile(
        r"DELETE\s+FROM\s+macro_observation_series_rows\s+WHERE\s+projection_version\s*=",
        re.IGNORECASE,
    )
    assert delete_all_pattern.search(normalized) is None


def test_equity_fetch_worker_does_not_hydrate_document_evidence() -> None:
    fetch_worker = _read(
        "src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_fetch_worker.py"
    )
    assert "hydrate_document_evidence" not in fetch_worker
    assert "replace_evidence_artifacts" not in fetch_worker


def test_equity_evidence_hydration_worker_exists() -> None:
    path = SRC / "domains/equity_event_intel/runtime/equity_event_evidence_hydration_worker.py"
    assert path.exists()


def test_news_fetch_validates_provider_contract_before_reconcile() -> None:
    worker = _read("src/gmgn_twitter_intel/domains/news_intel/runtime/news_fetch_worker.py")
    validate_at = worker.index("validate_news_provider_contract")
    reconcile_at = worker.index("reconcile_configured_sources")
    assert validate_at < reconcile_at
