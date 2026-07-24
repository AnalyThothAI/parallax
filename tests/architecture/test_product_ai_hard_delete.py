from __future__ import annotations

import ast
import inspect
from pathlib import Path

from parallax.app.surfaces.api.routes_search import target_posts
from parallax.app.surfaces.api.schemas import (
    TargetPostsQueryData,
    WatchlistHandleOverviewData,
    WatchlistOverviewCluster,
    WatchlistOverviewMetrics,
)
from parallax.domains.token_intel.read_models.token_target_posts_service import TokenTargetPostsService

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"
PRODUCTION_ROOTS = (
    SRC / "app",
    SRC / "domains",
)
DORMANT_LLM_PATHS = (
    "src/parallax/integrations/model_execution/execution_gateway.py",
    "src/parallax/integrations/model_execution/output_schema.py",
    "src/parallax/integrations/model_execution/structured_json_strategy.py",
    "src/parallax/integrations/model_execution/usage.py",
    "src/parallax/platform/agent_capabilities.py",
    "src/parallax/platform/agent_execution.py",
    "src/parallax/platform/agent_hashing.py",
)
MODEL_RUNTIME_IMPORT_PREFIXES = (
    "deepagents",
    "langchain",
    "langchain_litellm",
    "langgraph.checkpoint.postgres",
    "parallax.integrations.model_execution",
)
PRODUCT_AI_SYMBOLS = frozenset(
    {
        "ChatLiteLLM",
        "AsyncPostgresSaver",
        "MacroResearchDeepAgent",
    }
)
AUTHORIZED_PRODUCT_AI_RUNTIME = {
    "src/parallax/app/runtime/worker_factories/macro_intel.py": {
        "imports": {
            "langchain_litellm",
            "langgraph.checkpoint.postgres.aio",
            "parallax.integrations.model_execution.macro_research_deepagent",
        },
        "symbols": {"AsyncPostgresSaver", "ChatLiteLLM", "MacroResearchDeepAgent"},
    }
}
RETIRED_PYTHON_SEMANTICS = frozenset(
    {
        "SearchAgentBrief",
        "TokenTargetPostsSortError",
        "agent_execution",
        "agent_execution_gateway",
        "llm_configured",
        "narrative_admission",
        "news.story_brief",
        "news_high_signal",
        "news_story_brief",
        "semantic_catalyst",
        "story_brief_provider",
    }
)


def _python_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and "alembic/versions" not in path.as_posix()
    )


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports(tree: ast.AST) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _semantic_atoms(tree: ast.AST) -> set[str]:
    atoms = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    atoms.update(node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute))
    atoms.update(
        node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )
    return atoms


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_current_product_ai_runtime_and_contracts_are_absent() -> None:
    retired_paths = (
        "src/parallax/agent_knowledge/market_research_harness.md",
        "src/parallax/platform/agent_knowledge.py",
        "src/parallax/app/runtime/provider_wiring/model_execution.py",
        "src/parallax/domains/news_intel/prompts/news_story_brief.md",
        "src/parallax/domains/news_intel/runtime/news_story_brief_worker.py",
        "src/parallax/domains/news_intel/services/news_story_brief_stage.py",
        "src/parallax/integrations/model_execution/news_story_brief_agent_client.py",
        "src/parallax/domains/token_intel/read_models/search_agent_brief.py",
        "src/parallax/domains/token_intel/read_models/token_radar_narrative_admission.py",
        "tests/live/test_agent_model_capabilities_live.py",
        "web/src/shared/model/narrativeDataGaps.ts",
        "web/tests/unit/shared/model/narrativeDataGaps.test.ts",
    )
    present = [path for path in retired_paths if (ROOT / path).exists()]
    present.extend(_relative(path) for path in sorted((SRC / "domains").glob("*/prompts/*")) if path.is_file())
    present.extend(_relative(path) for path in sorted((SRC / "agent_knowledge").glob("**/*")) if path.is_file())

    assert present == []


def test_current_python_product_contract_contains_no_retired_ai_semantics() -> None:
    violations: dict[str, list[str]] = {}
    for root in PRODUCTION_ROOTS:
        for path in _python_files(root):
            matches = sorted(_semantic_atoms(_tree(path)) & RETIRED_PYTHON_SEMANTICS)
            if matches:
                violations[_relative(path)] = matches

    assert violations == {}


def test_fact_only_token_and_watchlist_public_models_are_exact() -> None:
    assert "sort" not in inspect.signature(target_posts).parameters
    assert "sort" not in inspect.signature(TokenTargetPostsService.target_posts).parameters
    assert set(TargetPostsQueryData.model_fields) == {
        "target_type",
        "target_id",
        "window",
        "scope",
        "post_range",
    }
    assert set(WatchlistOverviewMetrics.model_fields) == {
        "source_event_count",
        "resolved_token_count",
        "candidate_mention_count",
        "hashtag_count",
        "last_source_event_at_ms",
    }
    assert set(WatchlistHandleOverviewData.model_fields) == {
        "query",
        "metrics",
        "resolved_token_clusters",
        "candidate_mention_clusters",
        "hashtag_clusters",
        "clusters_truncated",
        "risk_notes",
    }
    kind_schema = WatchlistOverviewCluster.model_json_schema()["properties"]["kind"]
    assert kind_schema["enum"] == ["resolved_token", "candidate_mention", "hashtag"]


def test_dormant_llm_library_is_hard_deleted() -> None:
    assert [path for path in DORMANT_LLM_PATHS if (ROOT / path).exists()] == []


def test_only_macro_research_worker_factory_may_import_product_model_runtime() -> None:
    violations: dict[str, dict[str, list[str]]] = {}
    for root in PRODUCTION_ROOTS:
        for path in _python_files(root):
            tree = _tree(path)
            forbidden_imports = sorted(
                name for name in _imports(tree) if name.startswith(MODEL_RUNTIME_IMPORT_PREFIXES)
            )
            forbidden_symbols = sorted(
                {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id in PRODUCT_AI_SYMBOLS}
                | {
                    node.attr
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Attribute) and node.attr in PRODUCT_AI_SYMBOLS
                }
            )
            relative = _relative(path)
            authorized = AUTHORIZED_PRODUCT_AI_RUNTIME.get(relative, {"imports": set(), "symbols": set()})
            extra_imports = sorted(set(forbidden_imports) - authorized["imports"])
            extra_symbols = sorted(set(forbidden_symbols) - authorized["symbols"])
            if extra_imports or extra_symbols:
                violations[relative] = {
                    "imports": extra_imports,
                    "symbols": extra_symbols,
                }

    assert violations == {}
    for relative, expected in AUTHORIZED_PRODUCT_AI_RUNTIME.items():
        tree = _tree(ROOT / relative)
        assert {name for name in _imports(tree) if name.startswith(MODEL_RUNTIME_IMPORT_PREFIXES)} == expected[
            "imports"
        ]
        assert {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id in PRODUCT_AI_SYMBOLS
        } == expected["symbols"]
