from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    full_path = ROOT / path
    assert full_path.exists(), f"{path} is missing; implement the token/equity WorkerSpace root-fix contract"
    return full_path.read_text(encoding="utf-8")


def _function_source(text: str, function_name: str, *, context: str) -> str:
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == function_name:
            assert node.end_lineno is not None
            lines = text.splitlines()
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"{context} must define {function_name}")


def _worker_manifest_call(manifest: str, worker_name: str) -> ast.Call:
    tree = ast.parse(manifest)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "WorkerManifest":
            continue
        name_keyword = next((keyword for keyword in node.keywords if keyword.arg == "name"), None)
        if name_keyword is None:
            continue
        if isinstance(name_keyword.value, ast.Constant) and name_keyword.value.value == worker_name:
            return node
    raise AssertionError(f"WorkerManifest {worker_name!r} is missing")


def _worker_manifest_block(manifest: str, worker_name: str) -> str:
    marker = f'name="{worker_name}"'
    name_index = manifest.find(marker)
    assert name_index != -1, f"WorkerManifest {worker_name!r} is missing"
    start = manifest.rfind("WorkerManifest(", 0, name_index)
    assert start != -1, f"WorkerManifest {worker_name!r} call start is missing"
    end = manifest.find("WorkerManifest(", name_index + len(marker))
    if end == -1:
        end = manifest.find("\n)\n\n\ndef ", name_index)
    assert end != -1, f"WorkerManifest {worker_name!r} call end is missing"
    return manifest[start:end]


def _current_read_model_identity_columns(manifest: str, *, worker_name: str, table_name: str) -> tuple[str, ...]:
    manifest_call = _worker_manifest_call(manifest, worker_name)
    identity_keyword = next(
        (keyword for keyword in manifest_call.keywords if keyword.arg == "current_read_model_identities"),
        None,
    )
    assert identity_keyword is not None, f"{worker_name} must declare current_read_model_identities"
    assert isinstance(identity_keyword.value, ast.Tuple), f"{worker_name} identities must be a tuple literal"
    for entry in identity_keyword.value.elts:
        table, columns = ast.literal_eval(entry)
        if table == table_name:
            return tuple(columns)
    raise AssertionError(f"{worker_name} must declare identity columns for {table_name}")


def test_token_rank_source_manifest_identity_matches_runtime_key() -> None:
    manifest = _text("src/gmgn_twitter_intel/app/runtime/worker_manifest.py")
    rank_identity = _current_read_model_identity_columns(
        manifest,
        worker_name="token_radar_projection",
        table_name="token_radar_rank_source_events",
    )

    assert "intent_id" not in rank_identity
    for column in (
        "projection_version",
        "window",
        "scope",
        "lane",
        "target_type_key",
        "identity_id",
        "source_kind",
        "source_id",
    ):
        assert column in rank_identity


def test_token_dirty_targets_preserve_source_and_market_dirty_kinds() -> None:
    repo = _text(
        "src/gmgn_twitter_intel/domains/token_intel/repositories/"
        "token_radar_dirty_target_repository.py"
    )
    payload_hash_helper = _function_source(
        repo,
        "_payload_hash",
        context="token_radar_dirty_target_repository",
    )

    assert "source_dirty" in repo
    assert "market_dirty" in repo
    assert "dirty_at_ms" not in payload_hash_helper


def test_token_hashes_use_shared_canonicalizer() -> None:
    repo = _text("src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py")
    helper = _text("src/gmgn_twitter_intel/domains/token_intel/services/token_radar_payload_hash.py")

    assert "canonical_token_radar_payload" in helper
    assert "provenance.computed_at_ms" in helper
    assert "canonical_token_radar_payload" in repo


def test_equity_process_worker_uses_process_jobs_not_document_scan() -> None:
    worker = _text(
        "src/gmgn_twitter_intel/domains/equity_event_intel/runtime/"
        "equity_event_process_worker.py"
    )

    assert "claim_due_process_jobs" in worker
    assert "load_process_packets_for_claims" in worker
    assert "unit_of_work()" in worker
    assert "list_event_documents_for_processing" not in worker


def test_equity_process_and_page_hot_paths_do_not_select_raw_payload() -> None:
    repo = _text(
        "src/gmgn_twitter_intel/domains/equity_event_intel/repositories/"
        "equity_event_repository.py"
    )
    process_loader = _function_source(
        repo,
        "load_process_packets_for_claims",
        context="equity_event_repository",
    )
    page_loader = _function_source(
        repo,
        "_list_event_documents",
        context="equity_event_repository",
    )

    assert "raw_payload_json" not in process_loader
    assert "raw_payload_json" not in page_loader


def test_enforcement_workers_use_runtime_context_not_raw_worker_session() -> None:
    enforcement_files = (
        "src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py",
        "src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_fetch_worker.py",
        "src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_evidence_hydration_worker.py",
        "src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_process_worker.py",
        "src/gmgn_twitter_intel/domains/asset_market/runtime/event_anchor_backfill_worker.py",
    )

    for path in enforcement_files:
        text = _text(path)
        assert "runtime_context" in text
        assert "self.db.worker_session" not in text


def test_event_anchor_and_equity_process_manifests_declare_leased_queues() -> None:
    manifest = _text("src/gmgn_twitter_intel/app/runtime/worker_manifest.py")
    event_anchor = _worker_manifest_block(manifest, "event_anchor_backfill")
    equity_process = _worker_manifest_block(manifest, "equity_event_process")

    assert "uses_provider_io=True" in event_anchor
    assert 'queue_depth_table="event_anchor_backfill_jobs"' in event_anchor
    assert 'queue_depth_table="equity_event_process_jobs"' in equity_process
    assert '"equity_event_process_jobs"' in equity_process
