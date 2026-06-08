from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"

ALLOWED_DIRTY_STRING_FILES = {
    "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py",
    "src/parallax/domains/news_intel/runtime/news_projection_work.py",
    "src/parallax/app/runtime/projection_dirty_targets.py",
}

ALLOWED_RETIRED_TOOL_MARKER_FILES = {
    "src/parallax/domains/news_intel/repositories/news_intel_hard_cut_cleanup_repository.py",
}

RAW_PROJECTION_STRINGS = {"brief_input", "page", "source_quality"}
RETIRED_RESEARCH_TOOL_TOKENS = {
    "get_target_news_context",
    "search_news_archive",
    "get_observation_history",
}
HARD_CUT_CLEANUP_DELETE_TABLES = {
    "news_item_agent_briefs",
    "news_item_agent_runs",
    "news_page_rows",
    "news_projection_dirty_targets",
    "notifications",
}


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _function_source(path: str, function_name: str) -> str:
    source = _read(path)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            segment = ast.get_source_segment(source, node)
            assert segment is not None
            return segment
    raise AssertionError(f"{path} has no function {function_name}")


def test_news_fetch_has_no_agent_brief_admission_dependency() -> None:
    source = _read("src/parallax/domains/news_intel/runtime/news_fetch_worker.py")
    tree = ast.parse(source)
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "parallax.domains.news_intel.services.news_item_agent_policy"
    ]
    assert imports == []
    assert "brief_input" not in source
    assert "news_item_agent_brief_eligibility" not in source
    assert "NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS" not in source


def test_news_item_agent_policy_does_not_gate_on_legacy_analysis_admission() -> None:
    source = _read("src/parallax/domains/news_intel/services/news_item_agent_policy.py")
    assert "analysis_admission_status" not in source
    assert "analysis_not_admitted" not in source
    assert "NEWS_ITEM_AGENT_BRIEF_MIN_ADMITTED_PROVIDER_SCORE" not in source
    assert "_has_explicit_crypto_admission_basis" not in source


def test_news_item_brief_contract_has_no_legacy_crypto_only_surface() -> None:
    paths = [
        "src/parallax/domains/news_intel/types/news_item_brief.py",
        "src/parallax/domains/news_intel/services/news_item_brief_input.py",
        "src/parallax/domains/news_intel/services/news_item_brief_validation.py",
        "src/parallax/domains/news_intel/services/news_page_projection.py",
        "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
        "src/parallax/domains/news_intel/prompts/news_item_brief.md",
        "src/parallax/domains/notifications/services/notification_rules.py",
        "web/src/shared/model/newsIntel.ts",
        "web/src/lib/api/client.ts",
        "web/src/features/news/ui/NewsItemEvidencePage.tsx",
    ]
    forbidden = {
        "affected_assets",
        "NewsItemBriefTokenLane",
        "NewsItemBriefProviderTokenImpact",
        "NewsItemBriefAssetResolutionStatus",
        "provider_signal_evidence.token_impacts",
        "crypto-market transmission",
    }
    offenders = [f"{path} contains {token}" for path in paths for token in forbidden if token in _read(path)]
    assert offenders == []


def test_fetch_process_brief_constructors_do_not_accept_source_quality_windows() -> None:
    paths = [
        "src/parallax/domains/news_intel/runtime/news_fetch_worker.py",
        "src/parallax/domains/news_intel/runtime/news_item_process_worker.py",
        "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
        "src/parallax/app/runtime/worker_factories/news_intel.py",
    ]
    offenders = [path for path in paths if "source_quality_windows" in _read(path)]
    assert offenders == []


def test_news_runtime_workers_do_not_use_raw_dirty_projection_strings() -> None:
    offenders: list[str] = []
    for path in (SRC / "domains/news_intel/runtime").glob("news_*worker.py"):
        rel = _rel(path)
        if rel in ALLOWED_DIRTY_STRING_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders.extend(
            f"{rel}:{node.lineno}:{node.value}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and node.value in RAW_PROJECTION_STRINGS
        )
    assert offenders == []


def test_news_item_brief_stage_adapter_has_hard_cut_name() -> None:
    old_path = SRC / "domains/news_intel/services/news_item_brief_runtime.py"
    new_path = SRC / "domains/news_intel/services/news_item_brief_stage.py"
    assert not old_path.exists()
    assert new_path.exists()


def test_news_has_single_item_brief_llm_lane() -> None:
    lane_names: set[str] = set()
    for path in SRC.rglob("*.py"):
        if "alembic" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
                continue
            if not node.value.value.startswith("news."):
                continue
            if any(isinstance(target, ast.Name) and target.id.endswith("_LANE") for target in node.targets):
                lane_names.add(node.value.value)
    assert sorted(lane_names) == ["news.item_brief"]


def test_news_item_brief_input_has_no_provider_signal_field_aliases() -> None:
    source = _function_source(
        "src/parallax/domains/news_intel/services/news_item_brief_input.py",
        "_provider_signal_evidence",
    )
    forbidden = {
        'item.get("provider_signal")',
        'item.get("provider_token_impacts")',
        'item.get("source_ids")',
        'item.get("source_domains")',
        'item.get("provider_article_keys")',
    }
    offenders = sorted(token for token in forbidden if token in source)
    assert offenders == []


def test_news_page_row_payload_has_no_retired_public_field_aliases() -> None:
    source = _function_source(
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "_page_row_payload",
    )
    forbidden = {
        'payload.get("title")',
        'payload.get("url")',
        'payload.get("token_lanes_json",',
        'payload.get("fact_lanes_json",',
        'payload.get("token_impacts_json",',
        'payload.get("content_tags_json",',
        'payload.get("content_classification_json",',
        'payload.get("source_json",',
        'payload.get("agent_brief_json",',
        'payload.get("agent_brief_status")',
        'payload.get("signal_json",',
    }
    offenders = sorted(token for token in forbidden if token in source)
    assert offenders == []


def test_news_page_projection_outputs_semantic_fields_only() -> None:
    source = _function_source(
        "src/parallax/domains/news_intel/services/news_page_projection.py",
        "build_news_page_row",
    )
    forbidden = {
        '"content_tags_json":',
        '"content_classification_json":',
        '"agent_brief_json":',
        '"agent_brief_status":',
    }
    offenders = sorted(token for token in forbidden if token in source)
    assert offenders == []


def test_news_runtime_has_no_retired_research_tool_path() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        rel = _rel(path)
        if rel in ALLOWED_RETIRED_TOOL_MARKER_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{rel} contains retired News research tool token {token}"
            for token in RETIRED_RESEARCH_TOOL_TOKENS
            if token in text
        )

    assert offenders == []


def test_news_hard_cut_cleanup_is_delete_only_for_retired_artifacts() -> None:
    source = _read("src/parallax/domains/news_intel/repositories/news_intel_hard_cut_cleanup_repository.py")
    forbidden_write_ops = sorted(
        match.group(0)
        for match in re.finditer(
            r"\b(?:INSERT\s+INTO|UPDATE\s+[A-Za-z_][A-Za-z0-9_]*|TRUNCATE\s+TABLE|DROP\s+TABLE)\b",
            source,
            re.IGNORECASE,
        )
    )
    delete_tables = {
        match.group(1)
        for match in re.finditer(
            r"\bDELETE\s+FROM\s+([A-Za-z_][A-Za-z0-9_]*)\b",
            source,
            re.IGNORECASE,
        )
    }

    assert forbidden_write_ops == []
    assert delete_tables == HARD_CUT_CLEANUP_DELETE_TABLES


def test_news_runtime_product_paths_do_not_use_legacy_analysis_admission_gate() -> None:
    paths = [
        "src/parallax/domains/news_intel/services/news_page_projection.py",
        "src/parallax/domains/news_intel/services/news_story_identity.py",
        "src/parallax/domains/news_intel/runtime/news_item_process_worker.py",
        "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "src/parallax/domains/notifications/services/notification_rules.py",
        "src/parallax/app/surfaces/api/schemas.py",
        "src/parallax/app/surfaces/api/routes_news.py",
        "web/src/shared/model/newsIntel.ts",
        "web/src/lib/api/client.ts",
        "web/src/features/news/model/newsSignalViewModel.ts",
        "web/src/features/news/ui/NewsTape.tsx",
        "web/src/features/news/ui/NewsItemEvidencePage.tsx",
    ]
    forbidden = {
        "analysis_admission",
        "non_crypto_subject",
        "no_crypto_native_evidence",
        "provider_evidence_only",
        "analysis_not_admitted",
        "page_material_not_admitted",
    }
    offenders = [f"{path} contains {token}" for path in paths for token in forbidden if token in _read(path)]
    assert offenders == []
