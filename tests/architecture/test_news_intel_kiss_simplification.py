from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"

ALLOWED_DIRTY_STRING_FILES = {
    "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py",
    "src/parallax/domains/news_intel/runtime/news_projection_work.py",
    "src/parallax/app/runtime/projection_dirty_targets.py",
}

RAW_PROJECTION_STRINGS = {"brief_input", "page", "source_quality"}
RETIRED_RESEARCH_TOOL_TOKENS = {
    "get_target_news_context",
    "search_news_archive",
    "get_observation_history",
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


def test_ops_projection_dirty_repair_does_not_recompute_news_agent_admission() -> None:
    source = _read("src/parallax/app/runtime/projection_dirty_targets.py")
    forbidden = {
        "decide_news_item_agent_admission",
        "NewsItemAgentAdmissionContext",
        "load_agent_admission_contexts",
    }
    offenders = sorted(token for token in forbidden if token in source)
    assert offenders == []


def test_news_brief_input_cleanup_runtime_surface_is_removed() -> None:
    paths = {
        "src/parallax/app/surfaces/cli/parser.py",
        "src/parallax/app/surfaces/cli/commands/ops.py",
        "src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py",
    }
    forbidden = {"cleanup-news-brief-input", "cleanup_stale_brief_input_targets"}
    offenders = [f"{path} contains {token}" for path in paths for token in forbidden if token in _read(path)]
    assert offenders == []


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
    source = _read("src/parallax/domains/news_intel/services/news_item_brief_input.py")
    forbidden = {
        "_provider_signal_evidence",
        'item.get("provider_signal")',
        'item.get("provider_token_impacts")',
        'item.get("provider_signal_json")',
        'item.get("provider_token_impacts_json")',
        'item.get("source_ids")',
        'item.get("source_domains")',
        'item.get("provider_article_keys")',
    }
    offenders = sorted(token for token in forbidden if token in source)
    assert offenders == []


def test_opennews_provider_signal_is_not_news_agent_evidence_or_priority() -> None:
    paths = [
        "src/parallax/domains/news_intel/types/news_item_brief.py",
        "src/parallax/domains/news_intel/services/news_item_brief_input.py",
        "src/parallax/domains/news_intel/services/news_item_agent_policy.py",
        "src/parallax/domains/news_intel/services/news_item_agent_admission.py",
        "src/parallax/domains/news_intel/services/news_item_brief_validation.py",
        "src/parallax/domains/news_intel/services/news_item_brief_entity_support.py",
        "src/parallax/domains/news_intel/services/news_market_scope.py",
        "src/parallax/domains/news_intel/services/news_material_delta.py",
        "src/parallax/domains/news_intel/prompts/news_item_brief.md",
    ]
    forbidden = {
        "provider_signal_evidence",
        "provider_signal_json",
        "provider_token_impacts_json",
        "provider:signal",
        "provider:impact",
        "provider_score",
        "provider evidence",
        "provider-native",
        "provider fields",
    }
    offenders = [f"{path} contains {token}" for path in paths for token in forbidden if token in _read(path)]
    assert offenders == []


def test_opennews_provider_signal_only_reaches_news_page_as_provider_rating_evidence() -> None:
    page_projection = _read("src/parallax/domains/news_intel/services/news_page_projection.py")
    notification_rules = _read("src/parallax/domains/notifications/services/notification_rules.py")

    assert "provider_rating" in page_projection
    assert "provider_rating" not in notification_rules

    forbidden_everywhere = {
        "provider_score",
        "provider_score_band",
        "provider_status",
        "Score:",
        "_provider_signal_payload",
        "_merge_provider_impact",
    }
    forbidden_notification = {
        "provider_signal_json",
        "provider_token_impacts_json",
        "provider_signal",
    }
    offenders = [
        f"page projection contains {token}"
        for token in forbidden_everywhere
        if token in page_projection
    ] + [
        f"notification rules contains {token}"
        for token in forbidden_everywhere | forbidden_notification
        if token in notification_rules
    ]
    assert offenders == []


def test_news_page_compact_agent_brief_does_not_emit_audit_identity_fields() -> None:
    source = _function_source(
        "src/parallax/domains/news_intel/services/news_page_projection.py",
        "_compact_agent_brief",
    )
    forbidden = {
        "agent_run_id",
        "artifact_version_hash",
        "input_hash",
        "output_hash",
        "prompt_version",
        "schema_version",
        "validator_version",
    }
    offenders = sorted(token for token in forbidden if token in source)
    assert offenders == []


def test_news_detail_signal_fallbacks_do_not_emit_provider_signal_fields() -> None:
    functions = [
        "_signal_from_agent_brief",
        "_projection_missing_signal",
    ]
    forbidden = {
        "provider_signal",
        "provider_token_impacts",
    }
    offenders: list[str] = []
    for function_name in functions:
        source = _function_source("src/parallax/domains/news_intel/repositories/news_repository.py", function_name)
        offenders.extend(f"{function_name} contains {token}" for token in forbidden if token in source)
    assert offenders == []


def test_news_edge_remap_cleanup_dirties_page_projection_instead_of_deleting_rows() -> None:
    paths = [
        "src/parallax/domains/news_intel/repositories/news_repository.py",
    ]
    offenders = [path for path in paths if "_delete_item_scoped_page_rows" in _read(path)]
    assert offenders == []


def test_news_duplicate_hard_cut_repair_runtime_surface_is_removed() -> None:
    removed_paths = [
        SRC / "domains/news_intel/services/news_duplicate_hard_cut_repair.py",
        SRC / "domains/news_intel/repositories/news_duplicate_hard_cut_repair_repository.py",
    ]
    assert [str(path.relative_to(ROOT)) for path in removed_paths if path.exists()] == []

    forbidden_sources = [
        "src/parallax/app/surfaces/cli/parser.py",
        "src/parallax/app/surfaces/cli/commands/ops.py",
        "docs/WORKERS.md",
    ]
    forbidden_tokens = {
        "repair-news-duplicates-hard-cut",
        "repair_news_duplicates_hard_cut",
        "NewsDuplicateHardCutRepairAbort",
        "news_duplicate_hard_cut_repair",
        "ops_news_duplicate_hard_cut_repair",
    }
    offenders = [
        f"{path} contains {token}" for path in forbidden_sources for token in forbidden_tokens if token in _read(path)
    ]
    assert offenders == []


def test_news_agent_admission_contexts_do_not_rank_by_provider_score() -> None:
    functions = [
        "load_agent_admission_contexts",
        "_agent_similar_story_context",
    ]
    forbidden = {
        "provider_score",
        "provider_signal_json ->> 'score'",
        "provider_score DESC",
    }
    offenders: list[str] = []
    for function_name in functions:
        source = _function_source("src/parallax/domains/news_intel/repositories/news_repository.py", function_name)
        offenders.extend(f"{function_name} contains {token}" for token in forbidden if token in source)
    assert offenders == []


def test_news_item_brief_worker_requires_repository_admission_contexts() -> None:
    load_source = _function_source(
        "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
        "_load_candidates",
    )
    admission_source = _function_source(
        "src/parallax/domains/news_intel/runtime/news_item_brief_worker.py",
        "_admission_from_candidate",
    )

    assert 'getattr(repos.news, "load_agent_admission_contexts"' not in load_source
    assert "return candidates" not in load_source
    assert '"exact_duplicate_candidates": []' not in admission_source
    assert '"story_candidates": []' not in admission_source


def test_news_item_agent_policy_does_not_gate_on_legacy_analysis_admission() -> None:
    admission_source = _read("src/parallax/domains/news_intel/services/news_item_agent_admission.py")
    policy_source = _read("src/parallax/domains/news_intel/services/news_item_agent_policy.py")
    cli_parser_source = _read("src/parallax/app/surfaces/cli/parser.py")
    brief_worker_source = _read("src/parallax/domains/news_intel/runtime/news_item_brief_worker.py")
    assert not (SRC / "domains/news_intel/services/news_agent_admission_repair.py").exists()
    forbidden = {
        "analysis_admission_status",
        "analysis_not_admitted",
        "NEWS_ITEM_AGENT_MIN_PROVIDER_SCORE",
        "NEWS_ITEM_AGENT_BRIEF_MIN_ADMITTED_PROVIDER_SCORE",
        "_has_explicit_crypto_admission_basis",
        "provider_score_without_crypto_admission",
        "crypto_admission_basis",
        "score_below_threshold",
        "below_score_threshold",
        "min_provider_score",
    }
    assert sorted(token for token in forbidden if token in admission_source) == []
    assert sorted(token for token in forbidden if token in policy_source) == []
    assert sorted(token for token in forbidden if token in cli_parser_source) == []
    assert sorted(token for token in forbidden if token in brief_worker_source) == []


def test_news_item_brief_prompt_uses_market_wide_schema_without_affected_assets() -> None:
    prompt = _read("src/parallax/domains/news_intel/prompts/news_item_brief.md")
    required = {
        "market-wide",
        "`market_domains[]`",
        "`transmission_paths[]`",
        "`affected_entities[].reason_zh`",
    }
    forbidden = {
        "affected_assets",
        "crypto-market transmission",
        "crypto only",
    }
    assert sorted(token for token in required if token not in prompt) == []
    assert sorted(token for token in forbidden if token in prompt) == []


def test_news_page_row_payload_has_no_retired_public_field_aliases() -> None:
    source = _function_source(
        "src/parallax/domains/news_intel/repositories/news_repository.py",
        "_page_row_payload",
    )
    forbidden = {
        'payload.get("title")',
        'payload.get("url")',
        'payload.get("story_json")',
        'payload.get("token_lanes_json")',
        'payload.get("fact_lanes_json")',
        'payload.get("token_impacts_json")',
        'payload.get("content_tags_json")',
        'payload.get("content_classification_json")',
        'payload.get("source_json")',
        'payload.get("agent_brief_json")',
        'payload.get("agent_brief_status")',
        'payload.get("signal_json")',
        'payload.get("market_scope_json")',
        'payload.get("agent_admission_json")',
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


def test_news_api_signal_filter_has_no_retired_long_short_aliases() -> None:
    source = _read("src/parallax/app/surfaces/api/routes_news.py")
    forbidden = {
        'normalized == "long"',
        'normalized == "short"',
        'return "bullish"',
        'return "bearish"',
    }
    offenders = sorted(token for token in forbidden if token in source)
    assert offenders == []


def test_news_runtime_has_no_retired_research_tool_path() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        rel = _rel(path)
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{rel} contains retired News research tool token {token}"
            for token in RETIRED_RESEARCH_TOOL_TOKENS
            if token in text
        )

    assert offenders == []


def test_news_hard_cut_cleanup_runtime_surface_is_removed() -> None:
    removed_paths = [
        SRC / "domains/news_intel/services/news_intel_hard_cut_cleanup.py",
        SRC / "domains/news_intel/repositories/news_intel_hard_cut_cleanup_repository.py",
    ]
    assert [str(path.relative_to(ROOT)) for path in removed_paths if path.exists()] == []

    forbidden_sources = [
        "src/parallax/app/surfaces/cli/parser.py",
        "src/parallax/app/surfaces/cli/commands/ops.py",
        "docs/WORKERS.md",
        "docs/generated/cli-help.md",
    ]
    forbidden_tokens = {
        "cleanup-news-intel-hard-cut",
        "cleanup_news_intel_hard_cut",
        "NewsIntelHardCutCleanupAbort",
        "news_intel_hard_cut_cleanup",
        "news_intel_hard_cut_runtime_guard",
    }
    offenders = [
        f"{path} contains {token}" for path in forbidden_sources for token in forbidden_tokens if token in _read(path)
    ]
    assert offenders == []


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


def test_news_current_brief_schema_gate_uses_column_schema_version_only() -> None:
    source = _read("src/parallax/domains/news_intel/repositories/news_repository.py")
    forbidden = {
        "brief_json ->> 'schema_version'",
        'brief_json ->> "schema_version"',
        "brief_json->>'schema_version'",
        'brief_json->>"schema_version"',
    }
    offenders = sorted(token for token in forbidden if token in source)

    assert offenders == []
